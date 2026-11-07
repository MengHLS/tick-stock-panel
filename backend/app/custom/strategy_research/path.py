"""Pure event-path diagnostics for the T74 research baseline.

The label is deliberately independent from the actual exit policy: a fixed
future window is measured from the actual entry price, so a later policy cannot
change whether the opportunity existed. Realized trade returns and exit reasons
are kept beside, not substituted for, the opportunity label.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime
from statistics import median
from typing import Any

import numpy as np
import polars as pl

FULL_COVERAGE = "complete"
PARTIAL_COVERAGE = "partial"
MISSING_ENTRY = "missing_entry"
MISSING_SYMBOL = "missing_symbol"
INVALID_ENTRY = "invalid_entry_price"


@dataclass(frozen=True)
class PathConfig:
    horizon_sessions: int = 20
    thresholds: tuple[float, ...] = (0.20, 0.30, 0.50)
    entry_price_basis: str = "raw"

    def __post_init__(self) -> None:
        if not 1 <= self.horizon_sessions <= 250:
            raise ValueError("horizon_sessions must be between 1 and 250")
        if not self.thresholds:
            raise ValueError("at least one threshold is required")
        if any(not 0 < value <= 10 for value in self.thresholds):
            raise ValueError("thresholds must be in (0, 10]")
        if self.entry_price_basis not in {"raw", "adjusted"}:
            raise ValueError("entry_price_basis must be raw or adjusted")


def build_path_report(
    *,
    trades: tuple[dict[str, Any], ...],
    bars: pl.DataFrame,
    baseline: dict[str, Any],
    config: PathConfig,
    latest_data_date: date | None,
    data_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    by_symbol = _bars_by_symbol(bars)
    events: list[dict[str, Any]] = []
    duplicate_counts: dict[str, int] = {}
    stop_loss_pct = _optional_float(
        (baseline.get("execution") or {}).get("stop_loss_pct")
    )
    for trade in trades:
        event_key = f"{trade['symbol']}@{trade['entry_date']}"
        duplicate_counts[event_key] = duplicate_counts.get(event_key, 0) + 1
        suffix = duplicate_counts[event_key]
        event_id = event_key if suffix == 1 else f"{event_key}#{suffix}"
        events.append(
            _compute_event(
                trade,
                by_symbol.get(trade["symbol"]),
                config=config,
                stop_loss_pct=stop_loss_pct,
                event_id=event_id,
            )
        )

    summary = _summarize(events, config.thresholds, trades)
    return {
        "schema_version": 1,
        "config": {
            "horizon_sessions": config.horizon_sessions,
            "thresholds": list(config.thresholds),
            "entry_price_basis": config.entry_price_basis,
            "label_anchor": "actual_entry_price",
            "window_start": "entry_session",
            "high_low_basis": "adjusted",
        },
        "baseline": baseline,
        "sample_ledger": {
            "trade_rows": len(trades),
            "event_rows": len(events),
            "duplicate_event_keys": sum(
                count - 1 for count in duplicate_counts.values() if count > 1
            ),
            "candidate_universe": {
                "available": False,
                "reason": (
                    "当前基线只包含实际成交交易，未保存全部候选/排除样本；"
                    "未买入候选必须另建样本池，不能与成交事件混算。"
                ),
            },
        },
        "summary": summary,
        "data_quality": _data_quality(events, baseline, latest_data_date, data_identity),
        "events": events,
    }


def _compute_event(
    trade: dict[str, Any],
    frame: pl.DataFrame | None,
    *,
    config: PathConfig,
    stop_loss_pct: float | None,
    event_id: str,
) -> dict[str, Any]:
    base = {
        "event_id": event_id,
        "symbol": trade["symbol"],
        "entry_date": trade["entry_date"],
        "entry_price": trade["entry_price"],
        "entry_price_adjusted": None,
        "exit_date": trade.get("exit_date"),
        "exit_reason": trade.get("exit_reason"),
        "pnl_pct": trade.get("pnl_pct"),
        "pnl_amount": trade.get("pnl_amount"),
        "holding_days": trade.get("duration"),
        "open_at_end": bool(trade.get("open_at_end")),
        "entry_score": trade.get("entry_score"),
        "coverage_status": MISSING_SYMBOL,
        "horizon_end_date": None,
        "horizon_sessions_observed": 0,
        "max_favorable_excursion": None,
        "max_adverse_excursion": None,
        "thresholds": [
            {
                "threshold": threshold,
                "hit": None,
                "first_target_date": None,
                "days_to_target": None,
                "pre_target_adverse_excursion": None,
                "target_day_also_stop": None,
                "actual_realized": None,
                "tail_vs_exit": "unavailable",
            }
            for threshold in config.thresholds
        ],
    }
    if frame is None or frame.is_empty():
        return base

    dates = frame["date"].to_list()
    if not dates:
        return base
    entry_date = _as_date(trade["entry_date"])
    if entry_date is None:
        return base
    entry_index = bisect_left(dates, entry_date)
    if entry_index >= len(dates) or dates[entry_index] != entry_date:
        base["coverage_status"] = MISSING_ENTRY
        return base

    window = frame.slice(entry_index, config.horizon_sessions)
    if window.is_empty():
        base["coverage_status"] = MISSING_ENTRY
        return base
    observed = window.height
    highs = _finite_array(window["high"])
    lows = _finite_array(window["low"])
    closes = _finite_array(window["close"])
    raw_closes = (
        _finite_array(window["raw_close"])
        if "raw_close" in window.columns
        else None
    )
    entry_adj = _adjusted_entry_price(
        float(trade["entry_price"]),
        basis=config.entry_price_basis,
        adjusted_close=float(closes[0]) if closes is not None else None,
        raw_close=float(raw_closes[0]) if raw_closes is not None else None,
    )
    if entry_adj is None or not np.isfinite(entry_adj) or entry_adj <= 0:
        base["coverage_status"] = INVALID_ENTRY
        return base

    valid = (
        (highs > 0)
        & (lows > 0)
        & np.isfinite(highs)
        & np.isfinite(lows)
    )
    high_returns = np.where(valid, highs / entry_adj - 1.0, np.nan)
    low_returns = np.where(valid, lows / entry_adj - 1.0, np.nan)
    base["coverage_status"] = (
        FULL_COVERAGE if observed >= config.horizon_sessions else PARTIAL_COVERAGE
    )
    base["horizon_end_date"] = dates[entry_index + observed - 1].isoformat()
    base["horizon_sessions_observed"] = observed
    base["entry_price_adjusted"] = float(entry_adj)
    base["max_favorable_excursion"] = _nan_extreme(high_returns, max)
    base["max_adverse_excursion"] = _nan_extreme(low_returns, min)

    exit_date_text = trade.get("exit_date")
    exit_date = _as_date(exit_date_text) if exit_date_text else None
    exit_reason = str(trade.get("exit_reason") or "")
    pnl_pct = _optional_float(trade.get("pnl_pct"))
    for item in base["thresholds"]:
        threshold = float(item["threshold"])
        hit_mask = np.isfinite(high_returns) & (high_returns >= threshold - 1e-12)
        hit_index = int(np.argmax(hit_mask)) if bool(hit_mask.any()) else None
        item["actual_realized"] = (
            None if pnl_pct is None else bool(pnl_pct >= threshold)
        )
        if hit_index is None:
            item["hit"] = False
            item["tail_vs_exit"] = "no_tail"
            continue
        target_date = dates[entry_index + hit_index]
        item["hit"] = True
        item["first_target_date"] = target_date.isoformat()
        item["days_to_target"] = hit_index + 1
        item["pre_target_adverse_excursion"] = _nan_extreme(
            low_returns[: hit_index + 1],
            min,
        )
        item["target_day_also_stop"] = bool(
            stop_loss_pct is not None
            and np.isfinite(low_returns[hit_index])
            and low_returns[hit_index] <= stop_loss_pct
        )
        if exit_date is None:
            item["tail_vs_exit"] = "unknown_exit"
        elif target_date <= exit_date:
            item["tail_vs_exit"] = "tail_before_exit"
        else:
            item["tail_vs_exit"] = "tail_after_exit"
        if exit_reason == "stop_loss" and target_date <= exit_date:
            item["tail_vs_exit"] = "tail_before_stop"
        elif exit_reason == "stop_loss" and target_date > exit_date:
            item["tail_vs_exit"] = "stop_before_tail"
    return base


def _summarize(
    events: list[dict[str, Any]],
    thresholds: tuple[float, ...],
    trades: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    coverage: dict[str, int] = {}
    exit_reasons: dict[str, int] = {}
    for event in events:
        coverage[str(event["coverage_status"])] = (
            coverage.get(str(event["coverage_status"]), 0) + 1
        )
        reason = str(event.get("exit_reason") or "unknown")
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

    by_threshold: list[dict[str, Any]] = []
    for threshold in thresholds:
        rows = [
            (event, item)
            for event in events
            for item in event["thresholds"]
            if abs(float(item["threshold"]) - threshold) < 1e-12
            and item["hit"] is not None
        ]
        hits = [(event, item) for event, item in rows if item["hit"]]
        misses = [(event, item) for event, item in rows if not item["hit"]]
        stop_before = [
            item
            for _, item in hits
            if item["tail_vs_exit"] == "stop_before_tail"
        ]
        hit_before_stop = [
            item
            for _, item in hits
            if item["tail_vs_exit"] == "tail_before_stop"
        ]
        no_hit_stop = [
            item
            for event, item in misses
            if event.get("exit_reason") == "stop_loss"
        ]
        actual = [(event, item) for event, item in rows if item["actual_realized"]]
        by_threshold.append(
            {
                "threshold": threshold,
                "evaluable_count": len(rows),
                "hit_count": len(hits),
                "hit_rate": _rate(len(hits), len(rows)),
                "stopped_before_hit_count": len(stop_before),
                "stopped_before_hit_rate": _rate(len(stop_before), len(rows)),
                "hit_before_stop_count": len(hit_before_stop),
                "no_hit_stopped_count": len(no_hit_stop),
                "actual_realized_count": len(actual),
                "actual_realized_rate": _rate(len(actual), len(rows)),
                "median_days_to_target": _median(
                    [item["days_to_target"] for _, item in hits]
                ),
                "median_pre_target_adverse_excursion": _median(
                    [item["pre_target_adverse_excursion"] for _, item in hits]
                ),
                "median_pnl_hit": _median(
                    [_optional_float(event.get("pnl_pct")) for event, _ in hits]
                ),
                "median_pnl_miss": _median(
                    [_optional_float(event.get("pnl_pct")) for event, _ in misses]
                ),
                "same_day_target_and_stop_count": sum(
                    1 for _, item in hits if item["target_day_also_stop"]
                ),
            }
        )

    stop_trades = [trade for trade in trades if trade.get("exit_reason") == "stop_loss"]
    return {
        "event_count": len(events),
        "coverage_status": coverage,
        "exit_reasons": exit_reasons,
        "stop_loss_count": len(stop_trades),
        "stop_loss_rate": _rate(len(stop_trades), len(trades)),
        "stop_loss_pnl_amount": _sum_optional(
            [_optional_float(trade.get("pnl_amount")) for trade in stop_trades]
        ),
        "total_pnl_amount": _sum_optional(
            [_optional_float(trade.get("pnl_amount")) for trade in trades]
        ),
        "median_pnl_pct": _median(
            [_optional_float(trade.get("pnl_pct")) for trade in trades]
        ),
        "by_threshold": by_threshold,
    }


def _data_quality(
    events: list[dict[str, Any]],
    baseline: dict[str, Any],
    latest_data_date: date | None,
    data_identity: dict[str, Any] | None,
) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    for event in events:
        status = str(event["coverage_status"])
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "latest_data_date": (
            latest_data_date.isoformat() if latest_data_date is not None else None
        ),
        "loaded_daily_partition": data_identity,
        "baseline_data_generation": (baseline.get("data") or {}).get("generation"),
        "coverage_status": statuses,
        "missing_symbol_count": statuses.get(MISSING_SYMBOL, 0),
        "missing_entry_count": statuses.get(MISSING_ENTRY, 0),
        "invalid_entry_price_count": statuses.get(INVALID_ENTRY, 0),
        "partial_window_count": statuses.get(PARTIAL_COVERAGE, 0),
        "notes": [
            "未来空间使用复权高低价相对实际成交价的入场基准计算。",
            "窗口从实际入场交易日开始，按本地可用交易日计数；停牌/缺行会缩短观察窗口并标记 partial。",
            "同一日线同时触及目标和止损时无法仅凭日线确定先后，单独标记 target_day_also_stop。",
            "loaded_daily_partition 只标识本次读取的最后一个日线分区，不是全量历史快照指纹。",
            "历史复现基线的 legacy 兼容参数不等于未来实验默认口径。",
        ],
    }


def _bars_by_symbol(bars: pl.DataFrame) -> dict[str, pl.DataFrame]:
    if bars.is_empty() or "symbol" not in bars.columns:
        return {}
    out: dict[str, pl.DataFrame] = {}
    try:
        groups = bars.partition_by("symbol", as_dict=True)
    except TypeError:
        groups = {}
        for (symbol,), frame in bars.group_by("symbol"):
            groups[symbol] = frame
    for key, frame in groups.items():
        symbol = key[0] if isinstance(key, tuple) else key
        out[str(symbol)] = frame.sort("date")
    return out


def _adjusted_entry_price(
    entry_price: float,
    *,
    basis: str,
    adjusted_close: float | None,
    raw_close: float | None,
) -> float | None:
    if basis != "raw":
        return entry_price
    if (
        adjusted_close is None
        or raw_close is None
        or not np.isfinite(adjusted_close)
        or not np.isfinite(raw_close)
        or adjusted_close <= 0
        or raw_close <= 0
    ):
        return None
    return entry_price * adjusted_close / raw_close


def _finite_array(series: pl.Series) -> np.ndarray:
    return np.asarray(series.to_list(), dtype=np.float64)


def _nan_extreme(values: np.ndarray, reducer: Any) -> float | None:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    return float(reducer(finite))


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _median(values: list[float | None]) -> float | None:
    kept = [float(value) for value in values if value is not None]
    return float(median(kept)) if kept else None


def _rate(numerator: int, denominator: int) -> float | None:
    return float(numerator) / denominator if denominator else None


def _sum_optional(values: list[float | None]) -> float | None:
    kept = [value for value in values if value is not None]
    return float(sum(kept)) if kept else None


