"""Orchestration for path reports and research records."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from .baseline import Baseline
from .path import PathConfig, build_path_report
from .store import (
    ResearchStoreError,
    list_inbox,
    list_reports,
    new_id,
    read_report,
    write_report,
)

DAILY_COLUMNS = [
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "raw_close",
]


def create_path_report(
    *,
    data_dir: str | Any,
    market_data: Any,
    baseline: Baseline,
    horizon_sessions: int,
    thresholds: list[float],
    label: str | None,
    entry_price_basis: str = "auto",
) -> dict[str, Any]:
    if market_data is None:
        raise ResearchStoreError("行情读取接口未就绪，无法生成路径报告")
    symbols = sorted({str(trade["symbol"]) for trade in baseline.trades})
    entry_dates = [_parse_date(str(trade["entry_date"])) for trade in baseline.trades]
    start = min(entry_dates)
    latest = market_data.latest_daily_date()
    if latest is None:
        raise ResearchStoreError("本地日线数据未就绪，无法生成路径报告")
    end = min(
        latest,
        max(entry_dates) + timedelta(days=horizon_sessions * 2 + 30),
    )
    if end < start:
        raise ResearchStoreError("基线入场日期晚于本地最新日线")
    bars = market_data.get_daily_batch(
        symbols,
        start,
        end,
        columns=DAILY_COLUMNS,
    )
    if bars is None or bars.is_empty():
        raise ResearchStoreError("本地日线未能覆盖基线事件，无法生成路径报告")
    basis = (
        str((baseline.summary.get("execution") or {}).get("entry_price_basis") or "raw")
        if entry_price_basis == "auto"
        else entry_price_basis
    )
    config = PathConfig(
        horizon_sessions=int(horizon_sessions),
        thresholds=tuple(dict.fromkeys(float(value) for value in thresholds)),
        entry_price_basis=basis,
    )
    report = build_path_report(
        trades=baseline.trades,
        bars=bars,
        baseline=baseline.summary,
        config=config,
        latest_data_date=latest,
        data_identity=_daily_partition_identity(market_data, latest),
    )
    report_id = new_id("rpt")
    report["report_id"] = report_id
    report["created_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    report["label"] = (label or "").strip() or _default_report_label(baseline, config)
    write_report(data_dir, report)
    return report


def report_summary(report: dict[str, Any]) -> dict[str, Any]:
    config = report.get("config") or {}
    summary = report.get("summary") or {}
    return {
        "report_id": report.get("report_id"),
        "created_at": report.get("created_at"),
        "label": report.get("label"),
        "baseline": _baseline_brief(report.get("baseline") or {}),
        "config": config,
        "sample_ledger": report.get("sample_ledger") or {},
        "summary": summary,
        "data_quality": report.get("data_quality") or {},
    }


def filter_report_events(
    report: dict[str, Any],
    *,
    threshold: float | None,
    outcome: str,
    query: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    events = list(report.get("events") or [])
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 200))
    needle = (query or "").strip().lower()
    filtered: list[dict[str, Any]] = []
    for event in events:
        row = event
        threshold_row = None
        if threshold is not None:
            threshold_row = next(
                (
                    item
                    for item in event.get("thresholds") or []
                    if abs(float(item.get("threshold", -1)) - float(threshold)) < 1e-12
                ),
                None,
            )
        if not _matches_outcome(event, threshold_row, outcome):
            continue
        if needle and needle not in str(event.get("event_id", "")).lower():
            continue
        filtered.append(row)
    total = len(filtered)
    start = (page - 1) * page_size
    return {
        "items": filtered[start : start + page_size],
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_more": start + page_size < total,
        "threshold": threshold,
        "outcome": outcome,
    }


def get_report(data_dir: str | Any, report_id: str) -> dict[str, Any]:
    return read_report(data_dir, report_id)


def get_reports(data_dir: str | Any, *, limit: int = 50) -> list[dict[str, Any]]:
    return [report_summary(item) for item in list_reports(data_dir, limit=limit)]


def get_inbox(data_dir: str | Any) -> list[dict[str, Any]]:
    return list_inbox(data_dir)


def _matches_outcome(
    event: dict[str, Any],
    threshold_row: dict[str, Any] | None,
    outcome: str,
) -> bool:
    if outcome == "all":
        return True
    if threshold_row is None:
        return False
    hit = threshold_row.get("hit")
    tail_vs_exit = threshold_row.get("tail_vs_exit")
    if outcome == "hit":
        return bool(hit)
    if outcome == "miss":
        return hit is False
    if outcome == "stop_before_hit":
        return tail_vs_exit == "stop_before_tail"
    if outcome == "hit_before_stop":
        return tail_vs_exit == "tail_before_stop"
    if outcome == "no_hit_stop":
        return hit is False and event.get("exit_reason") == "stop_loss"
    if outcome == "same_day_ambiguous":
        return bool(threshold_row.get("target_day_also_stop"))
    return True


def _baseline_brief(baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "baseline_id": baseline.get("baseline_id"),
        "label": baseline.get("label"),
        "strategy_id": baseline.get("strategy_id"),
        "strategy_name": baseline.get("strategy_name"),
        "start": baseline.get("start"),
        "end": baseline.get("end"),
        "trade_count": baseline.get("trade_count"),
        "stats": baseline.get("stats") or {},
        "data": baseline.get("data") or {},
        "legacy_config": baseline.get("legacy_config") or {},
    }


def _default_report_label(baseline: Baseline, config: PathConfig) -> str:
    thresholds = "/".join(
        f"{value * 100:.0f}%" for value in config.thresholds
    )
    return f"{baseline.label} · {config.horizon_sessions}日 · {thresholds}"


def _daily_partition_identity(
    market_data: Any,
    latest: date,
) -> dict[str, Any] | None:
    suffix = f"date={latest.isoformat()}"
    try:
        value = market_data.dataset_partition_signature(
            "kline_daily_enriched",
            suffix,
        )
    except Exception:  # noqa: BLE001 - optional diagnostics
        return None
    return {
        "date": latest.isoformat(),
        "signature": str(value) if value else None,
    }


def _parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])
