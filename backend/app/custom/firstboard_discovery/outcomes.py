"""T+1 based outcome labels for first-board events."""
from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date
from typing import Any

import numpy as np
import polars as pl

OUTCOME_HORIZONS = (5, 10, 20)

_OUTCOME_SCHEMA: dict[str, pl.DataType] = {
    "event_id": pl.Utf8,
    "symbol": pl.Utf8,
    "name": pl.Utf8,
    "date": pl.Date,
    "row_index": pl.UInt32,
    "entry_date": pl.Date,
    "outcome_end": pl.Date,
    "entry_open": pl.Float64,
    "sessions_observed": pl.UInt32,
    "right_censored": pl.Boolean,
    "entry_unavailable": pl.Boolean,
    "entry_limit_locked": pl.Boolean,
    "outcome_unavailable": pl.Boolean,
    "scale_break_suspected": pl.Boolean,
    "mfe_5d": pl.Float64,
    "close_return_5d": pl.Float64,
    "mae_5d": pl.Float64,
    "mfe_10d": pl.Float64,
    "close_return_10d": pl.Float64,
    "mae_10d": pl.Float64,
    "mfe_20d": pl.Float64,
    "close_return_20d": pl.Float64,
    "mae_20d": pl.Float64,
    "early_fail_5d": pl.Boolean,
    "stop_touched": pl.Boolean,
    "strong": pl.Boolean,
}


def empty_event_samples() -> pl.DataFrame:
    return pl.DataFrame(schema=_OUTCOME_SCHEMA)


def build_event_samples(
    panel: pl.DataFrame,
    *,
    horizon: int = 20,
    strong_threshold: float = 0.20,
    sessions: Sequence[date] | None = None,
) -> pl.DataFrame:
    """Build first-board outcomes using the next observed bar as entry.

    Features are intentionally not read here. This function only projects the
    event identity and future outcome fields used by the discovery service.
    """
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    if not math.isfinite(strong_threshold) or not 0.0 < strong_threshold < 1.0:
        raise ValueError("strong_threshold must be in (0, 1)")
    required = {
        "symbol",
        "date",
        "open",
        "high",
        "low",
        "close",
        "raw_open",
        "raw_close",
        "consecutive_limit_ups",
    }
    missing = sorted(required - set(panel.columns))
    if missing:
        raise ValueError(f"first-board outcome panel missing columns: {missing}")
    if panel.is_empty():
        return empty_event_samples()

    ordered = panel.sort(["symbol", "date"]).with_row_index("__row_index")
    market_sessions = _market_sessions(ordered, sessions)
    session_index = {day: index for index, day in enumerate(market_sessions)}
    records: list[dict[str, Any]] = []
    for group in ordered.partition_by("symbol", maintain_order=True):
        records.extend(
            _symbol_events(
                group, horizon=horizon, strong_threshold=strong_threshold,
                sessions=market_sessions, session_index=session_index,
            )
        )
    if not records:
        return empty_event_samples()
    return pl.DataFrame(records, schema=_OUTCOME_SCHEMA)


def _market_sessions(
    panel: pl.DataFrame,
    sessions: Sequence[date] | None,
) -> list[date]:
    panel_dates = set(panel["date"].to_list())
    if sessions is None:
        return sorted(panel_dates)
    market_sessions = sorted(set(sessions))
    if not market_sessions:
        raise ValueError("全市场交易日序列为空，无法构造 T+1 收益标签")
    missing = sorted(panel_dates - set(market_sessions))
    if missing:
        raise ValueError(f"行情日期不在全市场交易日序列中: {missing[0]}")
    return market_sessions


def _symbol_events(
    group: pl.DataFrame,
    *,
    horizon: int,
    strong_threshold: float,
    sessions: list,
    session_index: dict,
) -> list[dict[str, Any]]:
    symbol = str(group.item(0, "symbol"))
    names = group["name"] if "name" in group.columns else None
    dates = group["date"].to_list()
    row_indices = group["__row_index"].to_list()
    open_values = _float_array(group["open"])
    high_values = _float_array(group["high"])
    low_values = _float_array(group["low"])
    close_values = _float_array(group["close"])
    raw_open_values = _float_array(group["raw_open"])
    raw_close_values = _float_array(group["raw_close"])
    boards = _float_array(group["consecutive_limit_ups"])
    limit_prices = (
        _float_array(group["limit_up_price"])
        if "limit_up_price" in group.columns
        else np.full(group.height, np.nan, dtype=np.float64)
    )

    records: list[dict[str, Any]] = []
    event_rows = np.flatnonzero(np.isfinite(boards) & (boards == 1.0))
    for event_index in event_rows:
        event_index = int(event_index)
        event_date = dates[event_index]
        event_id = f"{symbol}@{event_date.isoformat()}"
        entry_index = event_index + 1
        record: dict[str, Any] = {
            "event_id": event_id,
            "symbol": symbol,
            "name": str(names[event_index]) if names is not None else symbol,
            "date": event_date,
            "row_index": int(row_indices[event_index]),
            "entry_date": None,
            "outcome_end": None,
            "entry_open": None,
            "sessions_observed": 0,
            "right_censored": True,
            "entry_unavailable": True,
            "entry_limit_locked": False,
            "outcome_unavailable": False,
            "scale_break_suspected": False,
            "mfe_5d": None,
            "close_return_5d": None,
            "mae_5d": None,
            "mfe_10d": None,
            "close_return_10d": None,
            "mae_10d": None,
            "mfe_20d": None,
            "close_return_20d": None,
            "mae_20d": None,
            "early_fail_5d": None,
            "stop_touched": None,
            "strong": None,
        }
        records.append(record)
        if entry_index >= group.height:
            continue
        calendar_index = session_index[event_date] + 1
        expected = sessions[calendar_index:calendar_index + horizon]
        record["sessions_observed"] = len(expected)
        record["right_censored"] = len(expected) < horizon
        record["entry_date"] = dates[entry_index]
        if not expected or dates[entry_index] != expected[0]:
            continue
        entry_open = _positive(open_values[entry_index])
        record["entry_open"] = entry_open
        if entry_open is None:
            continue

        limit_price = _positive(limit_prices[entry_index])
        raw_entry_open = _positive(raw_open_values[entry_index])
        record["entry_limit_locked"] = bool(
            limit_price is not None
            and raw_entry_open is not None
            and raw_entry_open >= limit_price - 1e-9
        )

        stop = entry_index
        while stop < group.height and dates[stop] <= expected[-1]:
            stop += 1
        observed = stop - entry_index
        record["sessions_observed"] = observed
        record["outcome_end"] = dates[stop - 1] if observed else None
        observed_dates = dates[entry_index:stop]
        if observed_dates != expected[:observed]:
            record["entry_unavailable"] = False
            record["outcome_unavailable"] = not record["right_censored"]
            continue
        record["entry_unavailable"] = False
        for window_horizon in OUTCOME_HORIZONS:
            if observed < window_horizon:
                continue
            end = entry_index + window_horizon
            window_open = open_values[entry_index:end]
            window_high = high_values[entry_index:end]
            window_low = low_values[entry_index:end]
            window_close = close_values[entry_index:end]
            valid = (
                np.isfinite(window_open)
                & np.isfinite(window_high)
                & np.isfinite(window_low)
                & np.isfinite(window_close)
                & (window_open > 0)
                & (window_high > 0)
                & (window_low > 0)
                & (window_close > 0)
            )
            if not bool(valid.all()):
                continue
            mfe = float(np.max(window_high)) / entry_open - 1.0
            close_return = float(window_close[-1]) / entry_open - 1.0
            mae = float(np.min(window_low)) / entry_open - 1.0
            record[f"mfe_{window_horizon}d"] = mfe
            record[f"close_return_{window_horizon}d"] = close_return
            record[f"mae_{window_horizon}d"] = mae

        event_ratio = _ratio(close_values[event_index], raw_close_values[event_index])
        if event_ratio is not None:
            ratios = close_values[entry_index:stop] / raw_close_values[entry_index:stop]
            finite = np.isfinite(ratios)
            record["scale_break_suspected"] = bool(
                finite.any() and np.any(np.abs(ratios[finite] - event_ratio) > 0.001)
            )

        mfe = record["mfe_20d"]
        mae = record["mae_20d"]
        record["outcome_unavailable"] = not record["right_censored"] and mfe is None
        record["stop_touched"] = (
            mae <= -0.08 if isinstance(mae, float) and math.isfinite(mae) else None
        )
        early_mae = record["mae_5d"]
        if (
            not record["entry_unavailable"]
            and not record["entry_limit_locked"]
            and not record["scale_break_suspected"]
            and isinstance(early_mae, float)
            and math.isfinite(early_mae)
        ):
            record["early_fail_5d"] = early_mae <= -0.08 + 1e-12
        eligible = (
            not record["right_censored"]
            and not record["entry_limit_locked"]
            and not record["scale_break_suspected"]
        )
        if eligible and isinstance(mfe, float) and math.isfinite(mfe):
            record["strong"] = mfe + 1e-12 >= strong_threshold
    return records


def _float_array(series: pl.Series) -> np.ndarray:
    return series.cast(pl.Float64, strict=False).to_numpy()


def _positive(value: float) -> float | None:
    return float(value) if math.isfinite(value) and value > 0 else None


def _ratio(close: float, raw_close: float) -> float | None:
    if not math.isfinite(close) or not math.isfinite(raw_close) or raw_close <= 0:
        return None
    return float(close / raw_close)
