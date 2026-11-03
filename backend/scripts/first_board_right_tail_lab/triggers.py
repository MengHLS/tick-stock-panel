"""Dynamic first-board entry triggers evaluated on completed minute bars."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, time, timedelta
from typing import Any

import polars as pl

from .contracts import (
    ALL_RULES,
    CONTROL_RULE,
    EventRecord,
    RuleUnavailable,
    TriggerCandidate,
)

_RULE_PRIORITY = {rule: index for index, rule in enumerate(ALL_RULES)}
_LAST_NEW_POSITION_SIGNAL = time(14, 56)
_MARKET_OPEN_MINUTE = 9 * 60 + 30
_MORNING_CLOSE_MINUTE = 11 * 60 + 30
_AFTERNOON_OPEN_MINUTE = 13 * 60
_MARKET_CLOSE_MINUTE = 15 * 60

_REQUIRED_BAR_COLUMNS = {
    "symbol",
    "datetime",
    "bar_start",
    "bar_end",
    "volume",
    "open_raw",
    "high_raw",
    "low_raw",
    "close_raw",
    "amount_raw",
    "open_adj",
    "high_adj",
    "low_adj",
    "close_adj",
    "amount_adj",
}


def edge_is_new(previous_active: bool, current_active: bool) -> bool:
    return current_active and not previous_active


def _five_minute_slot_end() -> pl.Expr:
    minute = (
        pl.col("bar_end").dt.hour().cast(pl.Int32) * 60
        + pl.col("bar_end").dt.minute()
    )
    morning = minute.is_between(
        _MARKET_OPEN_MINUTE + 1,
        _MORNING_CLOSE_MINUTE,
    )
    afternoon = minute.is_between(
        _AFTERNOON_OPEN_MINUTE + 1,
        _MARKET_CLOSE_MINUTE,
    )
    return (
        pl.when(morning)
        .then(
            ((minute - (_MARKET_OPEN_MINUTE + 1)) // 5 + 1) * 5
            + _MARKET_OPEN_MINUTE
        )
        .when(afternoon)
        .then(
            ((minute - (_AFTERNOON_OPEN_MINUTE + 1)) // 5 + 1) * 5
            + _AFTERNOON_OPEN_MINUTE
        )
        .otherwise(None)
    )


def aggregate_five_minute(bars: pl.DataFrame) -> pl.DataFrame:
    """Aggregate exactly five contiguous 1-minute bars into bar-end 5m bars."""
    if bars.is_empty():
        return pl.DataFrame(schema=bars.schema)
    missing = _REQUIRED_BAR_COLUMNS - set(bars.columns)
    if missing:
        raise ValueError(
            f"minute bars missing required columns: {sorted(missing)}"
        )

    prepared = (
        bars.sort(["symbol", "bar_end"])
        .with_columns(_five_minute_slot_end().alias("_slot_end_minute"))
        .filter(pl.col("_slot_end_minute").is_not_null())
        .with_columns(
            (
                pl.col("bar_end").dt.truncate("1d")
                + pl.duration(minutes=pl.col("_slot_end_minute"))
            ).alias("_bucket_end")
        )
    )
    five = (
        prepared.group_by(
            ["symbol", "_bucket_end"],
            maintain_order=True,
        )
        .agg(
            pl.len().alias("_bar_count"),
            pl.col("bar_end").n_unique().alias("_unique_bars"),
            pl.col("bar_start").min().alias("bar_start"),
            pl.col("open_raw").first().alias("open_raw"),
            pl.col("high_raw").max().alias("high_raw"),
            pl.col("low_raw").min().alias("low_raw"),
            pl.col("close_raw").last().alias("close_raw"),
            pl.col("volume").sum().alias("volume"),
            pl.col("amount_raw").sum().alias("amount_raw"),
            pl.col("open_adj").first().alias("open_adj"),
            pl.col("high_adj").max().alias("high_adj"),
            pl.col("low_adj").min().alias("low_adj"),
            pl.col("close_adj").last().alias("close_adj"),
            pl.col("amount_adj").sum().alias("amount_adj"),
        )
        .filter(
            (pl.col("_bar_count") == 5)
            & (pl.col("_unique_bars") == 5)
        )
        .select(
            "symbol",
            pl.col("_bucket_end").alias("datetime"),
            "bar_start",
            pl.col("_bucket_end").alias("bar_end"),
            "volume",
            "open_raw",
            "high_raw",
            "low_raw",
            "close_raw",
            "amount_raw",
            "open_adj",
            "high_adj",
            "low_adj",
            "close_adj",
            "amount_adj",
        )
        .sort(["symbol", "bar_end"])
    )
    return five


def _prepare_bars(event: EventRecord, bars: pl.DataFrame) -> pl.DataFrame:
    if bars.is_empty():
        return bars
    missing = _REQUIRED_BAR_COLUMNS - set(bars.columns)
    if missing:
        raise ValueError(
            f"minute bars missing required columns: {sorted(missing)}"
        )
    filtered = bars
    if "symbol" in filtered.columns:
        filtered = filtered.filter(pl.col("symbol") == event.symbol)
    return (
        filtered.with_columns(
            pl.col("bar_end").dt.date().alias("_decision_date"),
            pl.col("bar_end").dt.time().alias("_bar_time"),
        )
        .sort("bar_end")
    )


def _decision_dates(
    event: EventRecord,
    bars: pl.DataFrame,
) -> list[date]:
    if bars.is_empty():
        return []
    return [
        value
        for value in bars.filter(
            pl.col("_decision_date") > event.event_date
        )["_decision_date"]
        .unique()
        .sort()
        .to_list()[:5]
    ]


def _eligible_bars(
    event: EventRecord,
    bars: pl.DataFrame,
) -> tuple[pl.DataFrame, dict[date, int]]:
    dates = _decision_dates(event, bars)
    day_by_date = {value: index + 1 for index, value in enumerate(dates)}
    if not day_by_date:
        return bars.clear(), day_by_date
    return (
        bars.filter(pl.col("_decision_date").is_in(list(day_by_date)))
        .filter(pl.col("_bar_time") <= _LAST_NEW_POSITION_SIGNAL),
        day_by_date,
    )


def _make_candidate(
    event: EventRecord,
    rule: str,
    bar_end: datetime,
    close_adj: float,
) -> TriggerCandidate | None:
    if bar_end.time() > _LAST_NEW_POSITION_SIGNAL:
        return None
    order_time = bar_end + timedelta(minutes=1)
    if order_time.date() != bar_end.date():
        return None
    return TriggerCandidate(
        event_id=event.event_id,
        symbol=event.symbol,
        rule=rule,
        bar_end=bar_end,
        signal_available_time=bar_end,
        order_time=order_time,
        signal_close_adj=float(close_adj),
    )


def _daily_groups(bars: pl.DataFrame) -> Sequence[pl.DataFrame]:
    if "_decision_date" not in bars.columns:
        bars = bars.with_columns(
            pl.col("bar_end").dt.date().alias("_decision_date")
        )
    return bars.partition_by(
        "_decision_date",
        maintain_order=True,
    )


def _rule_a_candidates(
    event: EventRecord,
    bars: pl.DataFrame,
) -> list[TriggerCandidate]:
    out: list[TriggerCandidate] = []
    for day in _daily_groups(bars):
        previous_active = False
        closes = day["close_adj"].to_list()
        volumes = day["volume"].to_list()
        bar_ends = day["bar_end"].to_list()
        for index, (bar_end, close, volume) in enumerate(
            zip(bar_ends, closes, volumes, strict=True)
        ):
            average = (
                sum(volumes[index - 20:index]) / 20
                if index >= 20
                and all(
                    value is not None
                    for value in volumes[index - 20:index]
                )
                else None
            )
            active = bool(
                average is not None
                and average > 0
                and close is not None
                and volume is not None
                and close > event.t_high_adj
                and volume > average * 2
            )
            if edge_is_new(previous_active, active):
                candidate = _make_candidate(
                    event,
                    "A",
                    bar_end,
                    close,
                )
                if candidate is not None:
                    out.append(candidate)
            previous_active = active
    return out


def _rule_b_candidates(
    event: EventRecord,
    five: pl.DataFrame,
) -> list[TriggerCandidate]:
    out: list[TriggerCandidate] = []
    for day in _daily_groups(five):
        previous_active = False
        previous_vwap: float | None = None
        previous_close: float | None = None
        cumulative_amount = 0.0
        cumulative_volume = 0.0
        for row in day.iter_rows(named=True):
            volume = row["volume"]
            amount = row["amount_adj"]
            close = row["close_adj"]
            if (
                volume is not None
                and amount is not None
                and volume > 0
            ):
                cumulative_volume += float(volume)
                cumulative_amount += float(amount)
            vwap = (
                cumulative_amount / (cumulative_volume * 100.0)
                if cumulative_volume > 0
                else None
            )
            active = bool(
                previous_vwap is not None
                and previous_close is not None
                and vwap is not None
                and close is not None
                and previous_close > previous_vwap
                and close > vwap
                and vwap > previous_vwap
            )
            if edge_is_new(previous_active, active):
                candidate = _make_candidate(
                    event,
                    "B",
                    row["bar_end"],
                    close,
                )
                if candidate is not None:
                    out.append(candidate)
            previous_active = active
            previous_vwap = vwap
            previous_close = close
    return out


def _rule_c_candidates(
    event: EventRecord,
    five: pl.DataFrame,
) -> list[TriggerCandidate]:
    out: list[TriggerCandidate] = []
    for day in _daily_groups(five):
        previous_active = False
        closes = day["close_adj"].to_list()
        bar_ends = day["bar_end"].to_list()
        for index, (bar_end, close) in enumerate(
            zip(bar_ends, closes, strict=True)
        ):
            active = False
            if index >= 5 and close is not None:
                current_window = closes[index - 4:index + 1]
                previous_window = closes[index - 5:index]
                if (
                    all(value is not None for value in current_window)
                    and all(value is not None for value in previous_window)
                ):
                    current_ma5 = sum(current_window) / 5.0
                    previous_ma5 = sum(previous_window) / 5.0
                    active = bool(
                        closes[index - 1] < previous_ma5
                        and close > current_ma5
                    )
            if edge_is_new(previous_active, active):
                candidate = _make_candidate(
                    event,
                    "C",
                    bar_end,
                    close,
                )
                if candidate is not None:
                    out.append(candidate)
            previous_active = active
    return out


def _auction_mapping(
    auction: Mapping[str, Any] | pl.DataFrame | None,
) -> Mapping[str, Any] | None:
    if auction is None:
        return None
    if isinstance(auction, pl.DataFrame):
        if auction.height != 1:
            return None
        return auction.row(0, named=True)
    if isinstance(auction, Mapping):
        return auction
    raise TypeError("auction must be a mapping, one-row DataFrame or None")


def _auction_value(
    auction: Mapping[str, Any],
    *names: str,
) -> float | None:
    for name in names:
        value = auction.get(name)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _auction_inputs(
    auction: Mapping[str, Any] | pl.DataFrame | None,
) -> tuple[float, float, float] | None:
    mapping = _auction_mapping(auction)
    if mapping is None:
        return None
    opening_gap = _auction_value(mapping, "opening_gap", "gap")
    volume_ratio = _auction_value(mapping, "volume_ratio")
    auction_price = _auction_value(
        mapping,
        "auction_price_adj",
    )
    if (
        opening_gap is None
        or volume_ratio is None
        or auction_price is None
    ):
        return None
    return opening_gap, volume_ratio, auction_price


def _rule_d_candidate(
    event: EventRecord,
    five: pl.DataFrame,
    auction_inputs: tuple[float, float, float] | None,
    day_by_date: dict[date, int],
) -> TriggerCandidate | None:
    if auction_inputs is None:
        return None
    opening_gap, volume_ratio, auction_price = auction_inputs
    if not (0.0 <= opening_gap <= 0.04 and volume_ratio > 1.0):
        return None

    first_day = [
        value for value, day_number in day_by_date.items() if day_number == 1
    ]
    if not first_day:
        return None
    first_bar = five.filter(
        (pl.col("_decision_date") == first_day[0])
        & (pl.col("bar_end").dt.time() == time(9, 35))
    )
    if first_bar.height != 1:
        return None
    row = first_bar.row(0, named=True)
    volume = row["volume"]
    amount = row["amount_adj"]
    if volume is None or amount is None or volume <= 0:
        return None
    first_five_vwap = float(amount) / (float(volume) * 100.0)
    if first_five_vwap < auction_price:
        return None
    return _make_candidate(
        event,
        "D",
        row["bar_end"],
        row["close_adj"],
    )


def _e0_candidate(
    event: EventRecord,
    bars: pl.DataFrame,
    day_by_date: dict[date, int],
) -> TriggerCandidate | None:
    first_day = [
        value for value, day_number in day_by_date.items() if day_number == 1
    ]
    if not first_day:
        return None
    first_bar = bars.filter(
        (pl.col("_decision_date") == first_day[0])
        & (pl.col("bar_end").dt.time() == time(9, 35))
    )
    if first_bar.height != 1:
        return None
    row = first_bar.row(0, named=True)
    return _make_candidate(
        event,
        CONTROL_RULE,
        row["bar_end"],
        row["close_adj"],
    )


def _unavailable_observation_time(
    event: EventRecord,
    bars: pl.DataFrame,
) -> datetime:
    dates = _decision_dates(event, bars)
    first_day = dates[0] if dates else event.event_date + timedelta(days=1)
    return datetime.combine(first_day, time(9, 35))


def iter_trigger_candidates(
    event: EventRecord,
    bars: pl.DataFrame,
    rules: Iterable[str],
    *,
    auction: Mapping[str, Any] | pl.DataFrame | None = None,
) -> tuple[list[TriggerCandidate], list[RuleUnavailable]]:
    """Evaluate selected rules and return a deterministic candidate list."""
    selected = tuple(dict.fromkeys(str(rule) for rule in rules))
    unknown = set(selected) - set(ALL_RULES)
    if unknown:
        raise ValueError(f"unknown trigger rules: {sorted(unknown)}")

    prepared = _prepare_bars(event, bars)
    eligible, day_by_date = _eligible_bars(event, prepared)
    five = aggregate_five_minute(eligible) if eligible.height else eligible
    if five.height:
        five = five.with_columns(
            pl.col("bar_end").dt.date().alias("_decision_date")
        )

    candidates: list[TriggerCandidate] = []
    unavailable: list[RuleUnavailable] = []
    for rule in selected:
        if rule == CONTROL_RULE:
            candidate = _e0_candidate(event, eligible, day_by_date)
            if candidate is not None:
                candidates.append(candidate)
        elif rule == "A":
            candidates.extend(_rule_a_candidates(event, eligible))
        elif rule == "B":
            candidates.extend(_rule_b_candidates(event, five))
        elif rule == "C":
            candidates.extend(_rule_c_candidates(event, five))
        elif rule == "D":
            auction_inputs = _auction_inputs(auction)
            candidate = _rule_d_candidate(
                event,
                five,
                auction_inputs,
                day_by_date,
            )
            if candidate is not None:
                candidates.append(candidate)
            elif auction_inputs is None:
                unavailable.append(
                    RuleUnavailable(
                        event_id=event.event_id,
                        rule="D",
                        reason="auction_unavailable",
                        observed_at=_unavailable_observation_time(
                            event,
                            prepared,
                        ),
                    )
                )

    candidates.sort(
        key=lambda candidate: (
            candidate.signal_available_time,
            _RULE_PRIORITY[candidate.rule],
        )
    )
    return candidates, unavailable
