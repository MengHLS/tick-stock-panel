"""只读编排：有界读取日线 enriched，按 as_of 截断后调用纯规则计算。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import polars as pl

from .rules import ASSET_TYPE, TIMEFRAME, compute_events, params_hash, rule_version
from .spec import load_spec, spec_warnings

REQUIRED_COLUMNS = ["symbol", "date", "open", "high", "low", "close", "volume"]
MAX_WINDOW_BARS = 500
MAX_LOOKBACK_DAYS = 1400


class ResearchInputError(ValueError):
    """入参越界或口径不支持。"""


def _rows(frame: pl.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in frame.sort("date").to_dicts():
        day = record.get("date")
        if isinstance(day, str):
            day = date.fromisoformat(day[:10])
        elif isinstance(day, datetime):
            day = day.date()
        if not isinstance(day, date):
            continue
        rows.append({
            "date": day,
            "open": record.get("open"),
            "high": record.get("high"),
            "low": record.get("low"),
            "close": record.get("close"),
            "volume": record.get("volume"),
        })
    deduped: dict[date, dict[str, Any]] = {}
    for row in rows:
        deduped[row["date"]] = row
    return [deduped[key] for key in sorted(deduped)]


def _missing_price_column(frame: pl.DataFrame) -> list[str]:
    return [column for column in REQUIRED_COLUMNS if column not in frame.columns]


def load_events(
    runtime: Any,
    *,
    symbol: str,
    window_bars: int,
    as_of: date | None,
    rule_version_expected: str | None,
) -> dict[str, Any]:
    if not symbol or "." not in symbol:
        raise ResearchInputError("symbol 需为带市场后缀的代码")
    if not 30 <= window_bars <= MAX_WINDOW_BARS:
        raise ResearchInputError(f"窗口长度需在 30..{MAX_WINDOW_BARS} 交易日之间")

    spec, spec_source = load_spec(runtime.data_dir)
    warnings = spec_warnings(spec)
    meta = {
        "symbol": symbol,
        "asset_type": ASSET_TYPE,
        "timeframe": TIMEFRAME,
        "rule_version": rule_version(spec),
        "params_hash": params_hash(spec),
        "spec_status": spec.get("spec_status", "unfrozen_demo"),
        "spec_source": spec_source,
        "window_bars": window_bars,
    }
    if warnings:
        return {**meta, "status": "spec_missing", "missing_fields": warnings, "events": [], "candidates": []}
    if rule_version_expected and rule_version_expected != meta["rule_version"]:
        raise ResearchInputError("rule_version 与当前装载规格不一致")

    panel = runtime.enriched_panel
    latest = panel.latest_date(ASSET_TYPE)
    if as_of is not None and latest is not None and as_of > latest:
        raise ResearchInputError("as_of 不得晚于最后一根已完成日线")
    effective_as_of = as_of or latest
    if effective_as_of is None:
        return {**meta, "status": "no_daily", "events": [], "candidates": []}

    generation_before = panel.data_generation(ASSET_TYPE)
    warmup = int(spec["warmup_bars"])
    need_bars = window_bars + warmup
    start = effective_as_of - timedelta(days=MAX_LOOKBACK_DAYS)
    frame = panel.range(start, effective_as_of, symbols=[symbol], columns=None)
    generation_after = panel.data_generation(ASSET_TYPE)
    if frame is None or frame.is_empty():
        return {**meta, "as_of": effective_as_of.isoformat(), "status": "no_daily", "events": [], "candidates": []}

    missing = _missing_price_column(frame)
    if missing:
        return {
            **meta,
            "as_of": effective_as_of.isoformat(),
            "status": "not_computable",
            "missing_columns": missing,
            "events": [],
            "candidates": [],
        }

    rows = _rows(frame.filter(pl.col("symbol") == symbol).unique(subset=["date"], keep="last"))
    rows = [row for row in rows if row["date"] <= effective_as_of]
    if len(rows) < need_bars:
        return {
            **meta,
            "as_of": effective_as_of.isoformat(),
            "status": "insufficient_data",
            "observed_bars": len(rows),
            "required_bars": need_bars,
            "events": [],
            "candidates": [],
        }

    computed = compute_events(
        rows[-need_bars:],
        symbol=symbol,
        as_of=effective_as_of,
        spec=spec,
        data_generation=generation_before,
    )
    if generation_after != generation_before:
        return {
            **meta,
            "as_of": effective_as_of.isoformat(),
            "status": "generation_changed",
            "data_generation": generation_before,
            "observed_generation": generation_after,
            "events": [],
            "candidates": [],
        }

    events = computed["events"] + computed["candidates"]
    return {
        **meta,
        "as_of": effective_as_of.isoformat(),
        "status": "ready",
        "data_generation": generation_before,
        "observed_bars": len(rows),
        "events": events,
        "candidates": computed["candidates"],
    }
