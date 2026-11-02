"""Decision-level dataset contracts for first-board right-tail studies."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date, datetime
from typing import Any

import polars as pl

from .contracts import EventRecord, TriggerCandidate
from .labels import build_labels
from .simulator import (
    SimulationConfig,
    execute_entry,
    pre_order_capacity_base,
    simulate_exit,
)
from .triggers import aggregate_five_minute


def make_decision_id(
    event_id: str,
    rule: str,
    signal_available_time: datetime,
) -> str:
    return f"{event_id}:{rule}:{signal_available_time.isoformat()}"


@dataclass(frozen=True)
class DecisionSample:
    decision_id: str
    event_id: str
    candidate_id: str
    symbol: str
    decision_date: date
    decision_time: datetime
    trigger_rule: str
    trigger_bar_end: datetime
    signal_available_time: datetime
    days_waited: int
    market_fillable: bool
    market_blocked_reason: str | None
    label_observable: bool
    entry_exec_adj: float | None
    mfe_touch_20d: float | None
    mae_touch_20d: float | None
    peak_day: int | None
    stop_first: bool | None
    ordering_ambiguous: bool | None
    mfe_exec_20d: float | None
    mae_exec_20d: float | None
    exec_return: float | None
    exit_status: str | None
    label_maturity_time: datetime | None
    features: dict[str, float | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.decision_id or not self.event_id or not self.candidate_id:
            raise ValueError("decision_id, event_id and candidate_id are required")
        if self.days_waited < 1:
            raise ValueError("days_waited must be positive")
        if not self.market_fillable and self.market_blocked_reason is None:
            raise ValueError("unfilled decision requires market_blocked_reason")
        if self.label_observable:
            required = (
                self.entry_exec_adj,
                self.mfe_touch_20d,
                self.mae_touch_20d,
                self.peak_day,
                self.stop_first,
                self.exit_status,
                self.label_maturity_time,
            )
            if any(value is None for value in required):
                raise ValueError("observable label is missing required values")

    def to_flat_row(self) -> dict[str, Any]:
        row = {
            item.name: getattr(self, item.name)
            for item in fields(self)
            if item.name != "features"
        }
        for name in sorted(self.features):
            row[f"feature__{name}"] = self.features[name]
        return row


def decision_days_waited(
    event: EventRecord,
    candidate: TriggerCandidate,
    sessions: list[date],
) -> int:
    session_index = {
        value: index for index, value in enumerate(sorted(set(sessions)))
    }
    event_index = session_index.get(event.event_date)
    decision_index = session_index.get(candidate.signal_available_time.date())
    if event_index is None or decision_index is None:
        raise ValueError("decision date is missing from the trading calendar")
    waited = decision_index - event_index
    if waited < 1:
        raise ValueError("decision must occur after the event session")
    return waited


def _minutes_since_open(value: datetime) -> float:
    minute = value.hour * 60 + value.minute
    if 9 * 60 + 30 <= minute <= 11 * 60 + 30:
        return float(minute - (9 * 60 + 30))
    if 13 * 60 <= minute <= 15 * 60:
        return float(120 + minute - 13 * 60)
    raise ValueError("decision time is outside continuous auction")


def decision_features(
    event: EventRecord,
    candidate: TriggerCandidate,
    bars: pl.DataFrame,
    *,
    daily_factors: dict[str, float | None] | None = None,
) -> dict[str, float | None]:
    required = {"symbol", "bar_end", "volume", "close_adj", "amount_adj"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"minute bars missing required columns: {sorted(missing)}")
    available = (
        bars.filter(
            (pl.col("symbol") == event.symbol)
            & (pl.col("bar_end") <= candidate.signal_available_time)
        )
        .sort("bar_end")
    )
    if available.is_empty():
        raise ValueError("no completed bars are available at decision time")
    day_bars = available.filter(
        pl.col("bar_end").dt.date()
        == candidate.signal_available_time.date()
    )
    if day_bars.is_empty():
        raise ValueError("no completed bars are available on the decision day")

    current = day_bars.row(-1, named=True)
    close = float(current["close_adj"])
    price_vs_t_high = close / event.t_high_adj - 1.0

    total_volume = float(day_bars["volume"].sum())
    total_amount = float(day_bars["amount_adj"].sum())
    vwap = total_amount / (total_volume * 100.0) if total_volume > 0 else None
    price_vs_vwap = close / vwap - 1.0 if vwap and vwap > 0 else None

    five = aggregate_five_minute(available)
    five_closes = [
        float(value)
        for value in five["close_adj"].to_list()
        if value is not None
    ]
    ma5 = sum(five_closes[-5:]) / 5.0 if len(five_closes) >= 5 else None
    price_vs_ma5 = close / ma5 - 1.0 if ma5 and ma5 > 0 else None

    volumes = day_bars["volume"].to_list()
    prior = volumes[-21:-1] if len(volumes) >= 21 else []
    volume_ratio = None
    if (
        len(prior) == 20
        and all(value is not None for value in prior)
        and current["volume"] is not None
    ):
        average = sum(float(value) for value in prior) / 20.0
        if average > 0:
            volume_ratio = float(current["volume"]) / average

    first_five = day_bars.head(5)
    first_open = first_five["open_adj"][0]
    first_close = first_five["close_adj"][-1]
    first_high = first_five["high_adj"].max()
    first_low = first_five["low_adj"].min()
    opening_gap = (
        float(first_open) / event.t_close_adj - 1.0
        if first_open is not None
        else None
    )
    first5_return = (
        float(first_close) / event.t_close_adj - 1.0
        if first_close is not None
        else None
    )
    first5_high_vs_t_high = (
        float(first_high) / event.t_high_adj - 1.0
        if first_high is not None
        else None
    )
    first5_low_vs_t_close = (
        float(first_low) / event.t_close_adj - 1.0
        if first_low is not None
        else None
    )
    first5_range = (
        (float(first_high) - float(first_low)) / event.t_close_adj
        if first_high is not None and first_low is not None
        else None
    )
    t_volume = (daily_factors or {}).get("daily__volume")
    first5_volume = first_five["volume"].sum()
    first5_volume_share = (
        float(first5_volume) / float(t_volume)
        if t_volume is not None
        and t_volume > 0
        and first5_volume is not None
        else None
    )

    cumulative_volume = 0.0
    cumulative_amount = 0.0
    above_vwap = 0
    vwap_observations = 0
    for bar in day_bars.iter_rows(named=True):
        volume = bar["volume"]
        amount = bar["amount_adj"]
        close = bar["close_adj"]
        if volume is None or amount is None or close is None:
            continue
        cumulative_volume += float(volume)
        cumulative_amount += float(amount)
        if cumulative_volume <= 0:
            continue
        cumulative_vwap = cumulative_amount / (cumulative_volume * 100.0)
        vwap_observations += 1
        if float(close) >= cumulative_vwap:
            above_vwap += 1
    minutes_above_vwap_ratio = (
        above_vwap / vwap_observations
        if vwap_observations
        else None
    )

    locked_minute_ratio = None
    if event.price_limit_pct is not None:
        limit_up_adj = event.t_close_adj * (
            1.0 + event.price_limit_pct
        )
        locked = day_bars.select(
            (
                ((pl.col("high_adj") - pl.col("low_adj")).abs() < 1e-9)
                & (
                    pl.col("close_adj")
                    >= limit_up_adj * (1.0 - 1e-3)
                )
            )
            .cast(pl.Float64)
            .alias("_locked")
        )["_locked"]
        locked_minute_ratio = (
            float(locked.mean()) if locked.len() else None
        )

    last_five = day_bars.tail(5)
    first5_average_volume = first_five["volume"].mean()
    last5_average_volume = last_five["volume"].mean()
    volume_growth = (
        float(last5_average_volume) / float(first5_average_volume)
        if first5_average_volume
        and first5_average_volume > 0
        and last5_average_volume is not None
        else None
    )

    features: dict[str, float | None] = {
        "price_vs_t_high": price_vs_t_high,
        "price_vs_vwap": price_vs_vwap,
        "price_vs_5m_ma5": price_vs_ma5,
        "volume_ratio_20": volume_ratio,
        "opening_gap": opening_gap,
        "first5_return_vs_t_close": first5_return,
        "first5_high_vs_t_high": first5_high_vs_t_high,
        "first5_low_vs_t_close": first5_low_vs_t_close,
        "first5_range_pct": first5_range,
        "first5_volume_share_t": first5_volume_share,
        "minutes_above_vwap_ratio": minutes_above_vwap_ratio,
        "locked_minute_ratio": locked_minute_ratio,
        "current_vs_first5_high": (
            float(close) / float(first_high) - 1.0
            if first_high is not None and first_high > 0
            else None
        ),
        "volume_growth_last5_vs_first5": volume_growth,
        "minutes_since_open": _minutes_since_open(
            candidate.signal_available_time
        ),
        "rule_a": 1.0 if candidate.rule == "A" else 0.0,
        "rule_b": 1.0 if candidate.rule == "B" else 0.0,
        "rule_c": 1.0 if candidate.rule == "C" else 0.0,
        "rule_d": 1.0 if candidate.rule == "D" else 0.0,
        "rule_e0": 1.0 if candidate.rule == "E0" else 0.0,
    }
    for name, value in (daily_factors or {}).items():
        features[f"factor__{name}"] = value
    return features


def build_decision_sample(
    event: EventRecord,
    candidate: TriggerCandidate,
    bars: pl.DataFrame,
    daily_context: pl.DataFrame,
    sessions: list[date],
    config: SimulationConfig,
    *,
    daily_factors: dict[str, float | None] | None = None,
) -> DecisionSample:
    days_waited = decision_days_waited(event, candidate, sessions)
    features = decision_features(
        event,
        candidate,
        bars,
        daily_factors=daily_factors,
    )
    features["days_waited"] = float(days_waited)
    capacity = pre_order_capacity_base(
        bars,
        candidate.order_time,
        candidate.symbol,
    )
    fill = execute_entry(
        candidate,
        bars,
        daily_context,
        config,
        capacity_base_amount=capacity,
    )
    base = {
        "decision_id": make_decision_id(
            event.event_id,
            candidate.rule,
            candidate.signal_available_time,
        ),
        "event_id": event.event_id,
        "candidate_id": candidate.candidate_id,
        "symbol": event.symbol,
        "decision_date": candidate.signal_available_time.date(),
        "decision_time": candidate.signal_available_time,
        "trigger_rule": candidate.rule,
        "trigger_bar_end": candidate.bar_end,
        "signal_available_time": candidate.signal_available_time,
        "days_waited": days_waited,
        "market_fillable": fill.filled,
        "market_blocked_reason": fill.blocked_reason,
        "features": features,
    }
    if not fill.filled:
        return DecisionSample(
            **base,
            label_observable=False,
            entry_exec_adj=None,
            mfe_touch_20d=None,
            mae_touch_20d=None,
            peak_day=None,
            stop_first=None,
            ordering_ambiguous=None,
            mfe_exec_20d=None,
            mae_exec_20d=None,
            exec_return=None,
            exit_status=None,
            label_maturity_time=None,
        )

    available_label_sessions = [
        value
        for value in sorted(set(sessions))
        if value >= fill.fill_time.date()
    ]
    if len(available_label_sessions) < 20:
        return DecisionSample(
            **base,
            label_observable=False,
            entry_exec_adj=fill.entry_exec_adj,
            mfe_touch_20d=None,
            mae_touch_20d=None,
            peak_day=None,
            stop_first=None,
            ordering_ambiguous=None,
            mfe_exec_20d=None,
            mae_exec_20d=None,
            exec_return=None,
            exit_status="insufficient_label_horizon",
            label_maturity_time=None,
        )
    exit_result = simulate_exit(fill, bars, daily_context, config)
    label = build_labels(
        fill,
        exit_result,
        bars,
        config,
        daily_context=daily_context,
        trading_dates=sessions,
    )
    return DecisionSample(
        **base,
        label_observable=True,
        entry_exec_adj=label.entry_exec_adj,
        mfe_touch_20d=label.mfe_touch_20d,
        mae_touch_20d=label.mae_touch_20d,
        peak_day=label.peak_day,
        stop_first=label.stop_first,
        ordering_ambiguous=label.ordering_ambiguous,
        mfe_exec_20d=label.mfe_exec_20d,
        mae_exec_20d=label.mae_exec_20d,
        exec_return=label.exec_return,
        exit_status=label.exit_status,
        label_maturity_time=label.label_maturity_time,
    )
