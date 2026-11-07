"""Paired event comparison and factor-hypothesis records.

Experiments are deliberately thin: the control and variant must already be
independent research reports produced from the same frozen label definition.
This module compares their event sets; it does not run a second backtest or
rewrite the strategy.
"""
from __future__ import annotations

from datetime import UTC, datetime
from statistics import median
from typing import Any

from .store import (
    ResearchStoreError,
    new_id,
    read_experiment,
    read_factor,
    read_report,
    write_experiment,
)


def create_experiment(
    data_dir: str | Any,
    *,
    name: str,
    hypothesis: str,
    changed_decision: str,
    control_report_id: str,
    variant_report_id: str,
    factor_id: str | None,
    conclusion: str,
    notes: str | None,
) -> dict[str, Any]:
    if control_report_id == variant_report_id:
        raise ResearchStoreError("对照与变体不能是同一份报告")
    control = read_report(data_dir, control_report_id)
    variant = read_report(data_dir, variant_report_id)
    control_config = control.get("config") or {}
    variant_config = variant.get("config") or {}
    if int(control_config.get("horizon_sessions", -1)) != int(
        variant_config.get("horizon_sessions", -2)
    ):
        raise ResearchStoreError("对照与变体的未来窗口不一致，不能配对")
    if _thresholds(control) != _thresholds(variant):
        raise ResearchStoreError("对照与变体的右尾阈值不一致，不能配对")
    if factor_id:
        read_factor(data_dir, factor_id)
    comparison = compare_reports(control, variant)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    experiment = {
        "schema_version": 1,
        "experiment_id": new_id("exp"),
        "name": name.strip(),
        "hypothesis": hypothesis.strip(),
        "changed_decision": changed_decision,
        "factor_id": factor_id,
        "conclusion": conclusion,
        "notes": (notes or "").strip(),
        "created_at": now,
        "updated_at": now,
        "control": _report_ref(control),
        "variant": _report_ref(variant),
        "comparison": comparison,
    }
    write_experiment(data_dir, experiment)
    return experiment


def compare_reports(
    control: dict[str, Any],
    variant: dict[str, Any],
) -> dict[str, Any]:
    control_events = {
        str(event.get("event_id")): event for event in control.get("events") or []
    }
    variant_events = {
        str(event.get("event_id")): event for event in variant.get("events") or []
    }
    common_keys = sorted(set(control_events) & set(variant_events))
    by_threshold: list[dict[str, Any]] = []
    for threshold in _thresholds(control):
        control_rows = {
            key: _threshold_row(control_events[key], threshold)
            for key in common_keys
        }
        variant_rows = {
            key: _threshold_row(variant_events[key], threshold)
            for key in common_keys
        }
        control_hits = {
            key for key, row in control_rows.items() if row and row.get("hit")
        }
        variant_hits = {
            key for key, row in variant_rows.items() if row and row.get("hit")
        }
        lost = sorted(control_hits - variant_hits)
        gained = sorted(variant_hits - control_hits)
        both = control_hits & variant_hits
        by_threshold.append(
            {
                "threshold": threshold,
                "control_hit_count": len(control_hits),
                "variant_hit_count": len(variant_hits),
                "both_hit_count": len(both),
                "lost_tail_count": len(lost),
                "gained_tail_count": len(gained),
                "tail_retention_rate": _rate(len(both), len(control_hits)),
                "control_stop_loss_count": _count_exit(
                    control_events, common_keys, "stop_loss"
                ),
                "variant_stop_loss_count": _count_exit(
                    variant_events, common_keys, "stop_loss"
                ),
                "control_actual_realized_count": len(
                    [key for key in common_keys if control_rows[key] and control_rows[key].get("actual_realized")]
                ),
                "variant_actual_realized_count": len(
                    [key for key in common_keys if variant_rows[key] and variant_rows[key].get("actual_realized")]
                ),
                "control_median_pnl": _median_event_pnl(control_events, common_keys),
                "variant_median_pnl": _median_event_pnl(variant_events, common_keys),
                "lost_tail_events": [
                    _event_delta(control_events[key], variant_events[key])
                    for key in lost[:50]
                ],
                "gained_tail_events": [
                    _event_delta(control_events[key], variant_events[key])
                    for key in gained[:50]
                ],
            }
        )
    return {
        "control_event_count": len(control_events),
        "variant_event_count": len(variant_events),
        "common_event_count": len(common_keys),
        "control_only_count": len(set(control_events) - set(variant_events)),
        "variant_only_count": len(set(variant_events) - set(control_events)),
        "control_stats": (control.get("baseline") or {}).get("stats"),
        "variant_stats": (variant.get("baseline") or {}).get("stats"),
        "control_exit_reasons": (control.get("summary") or {}).get("exit_reasons"),
        "variant_exit_reasons": (variant.get("summary") or {}).get("exit_reasons"),
        "by_threshold": by_threshold,
        "notes": [
            "配对只使用两份报告共有的 event_id；仅出现于一侧的事件单独计数。",
            "lost_tail/gained_tail 表示右尾标签在两侧的变化，不等同于已实现收益。",
            "组合资金复用、最多5仓和每日计划上限仍须用核心回测另行验证。",
        ],
    }


def get_experiment(data_dir: str | Any, experiment_id: str) -> dict[str, Any]:
    return read_experiment(data_dir, experiment_id)


def _report_ref(report: dict[str, Any]) -> dict[str, Any]:
    baseline = report.get("baseline") or {}
    return {
        "report_id": report.get("report_id"),
        "label": report.get("label"),
        "baseline_id": baseline.get("baseline_id"),
        "baseline_label": baseline.get("label"),
        "start": baseline.get("start"),
        "end": baseline.get("end"),
        "event_count": (report.get("summary") or {}).get("event_count"),
        "config": report.get("config") or {},
    }


def _thresholds(report: dict[str, Any]) -> list[float]:
    values = (report.get("config") or {}).get("thresholds") or []
    return sorted(float(value) for value in values)


def _threshold_row(event: dict[str, Any], threshold: float) -> dict[str, Any] | None:
    for row in event.get("thresholds") or []:
        if abs(float(row.get("threshold", -1)) - threshold) < 1e-12:
            return row
    return None


def _event_delta(control: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": control.get("event_id"),
        "symbol": control.get("symbol"),
        "entry_date": control.get("entry_date"),
        "control_pnl_pct": control.get("pnl_pct"),
        "variant_pnl_pct": variant.get("pnl_pct"),
        "control_exit_reason": control.get("exit_reason"),
        "variant_exit_reason": variant.get("exit_reason"),
        "control_exit_date": control.get("exit_date"),
        "variant_exit_date": variant.get("exit_date"),
        "control_coverage": control.get("coverage_status"),
        "variant_coverage": variant.get("coverage_status"),
    }


def _count_exit(
    events: dict[str, dict[str, Any]],
    keys: list[str],
    reason: str,
) -> int:
    return sum(1 for key in keys if events[key].get("exit_reason") == reason)


def _median_event_pnl(
    events: dict[str, dict[str, Any]],
    keys: list[str],
) -> float | None:
    values = [
        float(events[key]["pnl_pct"])
        for key in keys
        if events[key].get("pnl_pct") is not None
    ]
    return float(median(values)) if values else None


def _rate(numerator: int, denominator: int) -> float | None:
    return float(numerator) / denominator if denominator else None
