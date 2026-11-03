"""Pure A/B/C/D trigger evaluation for live first-board observation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

import polars as pl

_CUTOFF = time(14, 56)


@dataclass(frozen=True)
class TriggerSignal:
    rule: str
    signal_time: datetime
    order_time: datetime
    price_adj: float
    reason: str

    def __post_init__(self) -> None:
        if self.rule not in {"A", "B", "C", "D"}:
            raise ValueError(f"unknown trigger rule: {self.rule}")
        if self.signal_time.tzinfo is not None or self.order_time.tzinfo is not None:
            raise ValueError("trigger timestamps must be naive Beijing wall-clock")
        if self.order_time < self.signal_time + timedelta(minutes=1):
            raise ValueError("order must be at least one minute after the signal")


def _session_minute(value: datetime) -> int:
    current = value.hour * 60 + value.minute
    morning = 9 * 60 + 30
    afternoon = 13 * 60
    if current >= afternoon:
        return 120 + (current - afternoon)
    return current - morning


def aggregate_five_minutes(minute_df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate completed 1m bars to completed 5m bars using bar-end time."""
    required = {"symbol", "datetime", "open", "high", "low", "close", "volume", "amount"}
    if minute_df.is_empty() or not required.issubset(minute_df.columns):
        return pl.DataFrame()
    return (
        minute_df.sort(["symbol", "datetime"])
        .with_columns(
            pl.col("datetime").dt.date().alias("date"),
            pl.col("datetime").map_elements(_session_minute, return_dtype=pl.Int64).alias("_session_minute")
        )
        .filter(pl.col("_session_minute") >= 1)
        .with_columns((((pl.col("_session_minute") - 1) // 5)).alias("_bucket"))
        .group_by(["symbol", "date", "_bucket"], maintain_order=True)
        .agg(
            pl.col("datetime").last().alias("datetime"),
            pl.col("open").first().alias("open"),
            pl.col("high").max().alias("high"),
            pl.col("low").min().alias("low"),
            pl.col("close").last().alias("close"),
            pl.col("volume").sum().alias("volume"),
            pl.col("amount").sum().alias("amount"),
        )
        .sort(["symbol", "datetime"])
    )


def evaluate_intraday_rules(
    event: dict[str, Any],
    minute_df: pl.DataFrame,
    *,
    auction: dict[str, Any] | None = None,
    decision_day: int = 1,
) -> list[TriggerSignal]:
    """Evaluate all rules and return trigger edges in chronological order."""
    required = {"symbol", "datetime", "open", "high", "low", "close", "volume", "amount"}
    if minute_df.is_empty() or not required.issubset(minute_df.columns):
        return []
    symbol = str(event["symbol"])
    frame = (
        minute_df.filter(pl.col("symbol") == symbol)
        .sort("datetime")
        .with_columns(pl.col("datetime").dt.date().alias("date"))
        .with_columns(
            pl.col("volume")
            .rolling_mean(20)
            .shift(1)
            .over("date")
            .alias("_prior_20m_avg_volume")
        )
    )
    if frame.is_empty():
        return []

    signals: list[TriggerSignal] = []
    t_high = float(event["t_high_adj"])
    t_close = float(event["t_close_adj"])

    # A: one-minute breakout on an inactive -> active edge.
    active_a = False
    for row in frame.iter_rows(named=True):
        signal_time = row["datetime"]
        if signal_time.time() > _CUTOFF:
            break
        avg_volume = row["_prior_20m_avg_volume"]
        if avg_volume is None:
            active_a = False
            continue
        current = float(row["close"] > t_high and row["volume"] > float(avg_volume) * 2.0)
        if current and not active_a:
            signals.append(
                TriggerSignal(
                    rule="A",
                    signal_time=signal_time,
                    order_time=signal_time + timedelta(minutes=1),
                    price_adj=float(row["close"]),
                    reason="1分钟收盘突破T日最高，成交量大于前20分钟均量2倍",
                )
            )
        active_a = bool(current)

    cumulative = frame.with_columns(
        pl.col("amount").cum_sum().over("date").alias("_cum_amount"),
        pl.col("volume").cum_sum().over("date").alias("_cum_volume"),
    ).with_columns(
        pl.when(pl.col("_cum_volume") > 0)
        .then(pl.col("_cum_amount") / (pl.col("_cum_volume") * 100.0))
        .otherwise(None)
        .alias("_day_vwap")
    )
    five = aggregate_five_minutes(frame)
    if five.is_empty():
        return sorted(signals, key=lambda item: (item.signal_time, item.rule))
    five = five.join(
        cumulative.select("symbol", "datetime", "_day_vwap"),
        on=["symbol", "datetime"],
        how="left",
    ).rename({"_day_vwap": "vwap"}).with_columns(
        pl.col("close").rolling_mean(5).alias("ma5"),
        pl.col("close").shift(1).alias("_prev_close"),
        pl.col("vwap").shift(1).alias("_prev_vwap"),
    )
    closer = five["close"].to_list()
    lows = five["low"].to_list()

    active_b = False
    active_c = False
    two_above = 0
    for index, row in enumerate(five.iter_rows(named=True)):
        signal_time = row["datetime"]
        if signal_time.time() > _CUTOFF:
            break
        close = float(row["close"])
        vwap = row["vwap"]
        previous_vwap = row["_prev_vwap"]
        if vwap is None:
            two_above = 0
            active_b = False
        else:
            two_above = two_above + 1 if close > float(vwap) else 0
            current_b = (
                two_above >= 2
                and previous_vwap is not None
                and float(vwap) > float(previous_vwap)
            )
            if current_b and not active_b:
                signals.append(
                    TriggerSignal(
                        rule="B",
                        signal_time=signal_time,
                        order_time=signal_time + timedelta(minutes=1),
                        price_adj=close,
                        reason="连续2根5分钟收盘站上VWAP，且VWAP斜率向上",
                    )
                )
            active_b = current_b

        ma5 = row["ma5"]
        current_c = False
        if index >= 5 and ma5 is not None:
            previous_ma5 = sum(closer[index - 5:index]) / 5.0
            current_c = (
                row["_prev_close"] is not None
                and float(row["_prev_close"]) < previous_ma5
                and close > float(ma5)
                and min(lows[index - 4:index + 1]) > t_close * 0.94
            )
        if current_c and not active_c:
            signals.append(
                TriggerSignal(
                    rule="C",
                    signal_time=signal_time,
                    order_time=signal_time + timedelta(minutes=1),
                    price_adj=close,
                    reason="5分钟收盘重新站上MA5，且未跌破T日收盘-6%",
                )
            )
        active_c = current_c

    if decision_day == 1 and auction and five.height:
        first = five.row(0, named=True)
        gap = auction.get("opening_gap")
        volume_ratio = auction.get("volume_ratio")
        auction_price = auction.get("auction_price")
        first_vwap = (
            float(first["amount"]) / (float(first["volume"]) * 100.0)
            if first["volume"] and first["volume"] > 0
            else None
        )
        signal_time = first["datetime"]
        if (
            gap is not None
            and volume_ratio is not None
            and auction_price is not None
            and 0 <= float(gap) <= 0.04
            and float(volume_ratio) > 1.0
            and first_vwap is not None
            and first_vwap >= float(auction_price)
            and signal_time.time() <= _CUTOFF
        ):
            signals.append(
                TriggerSignal(
                    rule="D",
                    signal_time=signal_time,
                    order_time=signal_time + timedelta(minutes=1),
                    price_adj=float(first["close"]),
                    reason="竞价缺口0%-4%、量比>1，首根5分钟均价不低于竞价均价",
                )
            )

    return sorted(signals, key=lambda item: (item.signal_time, item.rule))
