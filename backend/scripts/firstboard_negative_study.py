"""Create an immutable early-loss study from a saved first-board run."""
from __future__ import annotations

import argparse
import copy
import json
import math
import time
from datetime import date
from pathlib import Path

import polars as pl

from app.custom.firstboard_discovery.discovery import _evaluate_candidate, score_factor
from app.custom.firstboard_discovery.negative import (
    MAIN_COLUMN,
    MAIN_THRESHOLD,
    build_negative_research,
    predict_negative_risk,
    prepare_research_cohorts,
)
from app.custom.firstboard_discovery.service import (
    _CANDIDATE_POLICY,
    ALGORITHM_VERSION,
    _condition_use,
)
from app.custom.firstboard_discovery.storage import FirstboardDiscoveryStore

STUDY_ALGORITHM_VERSION = "firstboard-negative-study-v4"
_SUPPORTED_SOURCE_ALGORITHM_VERSIONS = frozenset({
    "firstboard-discovery-v3",
    "firstboard-discovery-v4",
    "firstboard-discovery-v5",
    ALGORITHM_VERSION,
})


def run_study(data_dir: Path, source_run_id: str) -> dict:
    """Evaluate a frozen saved snapshot and persist a separate derived run."""
    started = time.perf_counter()
    store = FirstboardDiscoveryStore(Path(data_dir))
    source = copy.deepcopy(store.load_report(source_run_id))
    _validate_source_contract(source)
    split = source.get("split") or {}
    try:
        train_end = _as_date(split["train_end"])
        validation_start = _as_date(split["validation_start"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("来源记录缺少可用的训练/验证时间边界") from exc
    try:
        cutoff = _as_date(source["params"]["end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("来源记录缺少可用的事件截止日") from exc
    source_events = pl.DataFrame(
        store.load_events(source_run_id, end_date=cutoff),
        infer_schema_length=None,
    )
    if source_events.is_empty():
        raise ValueError("来源记录没有事件")
    source_total = int((source.get("sample") or {}).get("total_events") or 0)
    lockbox_excluded = max(0, source_total - source_events.height)
    sort_columns = [
        column
        for column in ("date", "symbol", "event_id")
        if column in source_events.columns
    ]
    events = source_events.sort(sort_columns)
    if events.is_empty():
        raise ValueError("来源记录在评估截止日前没有事件")
    events = _ensure_early_fail_label(events)
    factor_columns = _factor_columns(events, source["factors"])
    cohorts = prepare_research_cohorts(
        events,
        train_end=train_end,
        validation_start=validation_start,
    )
    train = cohorts.train
    validation = cohorts.validation
    if train.is_empty() or validation.is_empty():
        raise ValueError("来源记录在评估截止日前缺少训练或验证样本")
    negative = build_negative_research(
        train,
        validation,
        factor_columns,
        train_end=train_end,
    )
    negative["evaluation_cutoff"] = cutoff
    negative["lockbox_excluded_count"] = lockbox_excluded
    probabilities = predict_negative_risk(events, negative["model"])
    threshold = negative["model"].get("decision_threshold")
    event_rows = events.to_dicts()
    train_ids = set(train["event_id"].to_list())
    validation_ids = set(validation["event_id"].to_list())
    for row, probability in zip(event_rows, probabilities, strict=True):
        row["early_fail_probability"] = (
            float(probability) if math.isfinite(probability) else None
        )
        row["negative_veto"] = (
            bool(probability >= threshold)
            if math.isfinite(probability) and threshold is not None else None
        )
        main_value = row.get(MAIN_COLUMN)
        row["frozen_main_hit"] = (
            bool(main_value >= MAIN_THRESHOLD)
            if main_value is not None and math.isfinite(main_value) else None
        )
        row["split"] = (
            "excluded" if row.get("strong") is None
            else "train" if row["event_id"] in train_ids
            else "validation" if row["event_id"] in validation_ids
            else "purged"
        )

    params = dict(source.get("params") or {})
    params["end"] = cutoff.isoformat()
    factors = _refresh_factor_statistics(source.get("factors") or [], validation)
    rules = _refresh_rule_statistics(
        source.get("rules") or [],
        train,
        validation,
        train_end=train_end,
    )
    derived = {
        **source,
        "algorithm_version": STUDY_ALGORITHM_VERSION,
        "source_run_id": source_run_id,
        "source_algorithm_version": source.get("algorithm_version"),
        "source_saved_at": source.get("saved_at"),
        "generation": source.get("generation"),
        "params": params,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "research_cutoff": cutoff,
        "lockbox_excluded_count": lockbox_excluded,
        "negative_research": negative,
        "factors": factors,
        "rules": rules,
        "sample": _sample_summary(events),
        "split": _split_summary(
            split,
            cohorts,
            train_end=train_end,
            validation_start=validation_start,
            validation_end=validation["date"].max(),
        ),
        "warnings": [
            *(source.get("warnings") or []),
            "该派生记录只使用来源快照中评估截止日前的事件；源记录保持只读。",
        ],
    }
    run_id, saved_at = store.save(derived, event_rows)
    return {**derived, "run_id": run_id, "saved_at": saved_at}


def _validate_source_contract(source: dict) -> None:
    version = source.get("algorithm_version")
    if version not in _SUPPORTED_SOURCE_ALGORITHM_VERSIONS:
        raise ValueError(f"来源算法版本不受支持: {version!r}")
    policy = source.get("candidate_policy")
    if not isinstance(policy, dict):
        raise ValueError("来源记录缺少候选策略契约")
    expected_policy = dict(_CANDIDATE_POLICY)
    if version != ALGORITHM_VERSION:
        expected_policy.pop("allowed_extension_factor_ids")
    actual_policy = {key: policy.get(key) for key in expected_policy}
    if actual_policy != expected_policy:
        raise ValueError("来源记录的候选策略与当前研究契约不一致")
    factors = source.get("factors")
    if not isinstance(factors, list) or not factors:
        raise ValueError("来源记录缺少候选因子清单")
    pairs = {
        (row.get("factor_id"), row.get("snapshot"))
        for row in factors
        if isinstance(row, dict)
    }
    if len(pairs) != len(factors):
        raise ValueError("来源记录的候选因子清单存在缺失或重复")
    if policy.get("factor_count") != len(pairs):
        raise ValueError("来源记录的候选因子数量与清单不一致")


def _factor_columns(
    events: pl.DataFrame,
    factors: list[dict],
) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for row in factors:
        factor_id = row["factor_id"]
        snapshot = row["snapshot"]
        if snapshot not in ("D_minus_1", "D_close"):
            raise ValueError(f"来源因子时点不受支持: {snapshot!r}")
        column = f"{snapshot}__{factor_id}"
        if column not in events.columns:
            raise ValueError(f"来源因子在事件快照中缺失: {column}")
        result.append((factor_id, snapshot))
    if MAIN_COLUMN not in events.columns or (
        ("boll_width", "D_minus_1") not in set(result)
    ):
        raise ValueError("来源记录缺少冻结主规则所需因子")
    return result


def _refresh_factor_statistics(
    factors: list[dict],
    validation: pl.DataFrame,
) -> list[dict]:
    labels = validation["strong"].to_list()
    refreshed: list[dict] = []
    for row in factors:
        updated = dict(row)
        column = f"{row['snapshot']}__{row['factor_id']}"
        score = score_factor(
            row["factor_id"],
            row["snapshot"],
            validation[column].to_list(),
            labels,
        )
        updated.update(
            validation_auc=score.auc,
            validation_coverage=score.coverage,
            validation_count=score.train_count,
        )
        refreshed.append(updated)
    return refreshed


def _refresh_rule_statistics(
    rules: list[dict],
    train: pl.DataFrame,
    validation: pl.DataFrame,
    *,
    train_end: date,
) -> list[dict]:
    research = pl.concat([train, validation])
    base_rate = float(train["strong"].mean() or 0.0)
    refreshed: list[dict] = []
    for row in rules:
        candidate = {
            "conditions": row["conditions"],
            "dimension": int(row.get("dimension") or len(row["conditions"])),
            "uses": [_condition_use(condition) for condition in row["conditions"]],
        }
        evaluated = _evaluate_candidate(
            candidate,
            research,
            train_end=train_end,
            base_rate=base_rate,
        )
        if evaluated is None:
            raise ValueError(f"来源规则在保留训练样本中不再可用: {row.get('id')}")
        refreshed.append(evaluated)
    return refreshed


def _split_summary(
    source: dict,
    cohorts,
    *,
    train_end: date,
    validation_start: date,
    validation_end: date,
) -> dict:
    eligible = cohorts.eligible
    train = cohorts.train
    validation = cohorts.validation
    return {
        **source,
        "train_start": eligible["date"].min(),
        "train_end": train_end,
        "validation_start": validation_start,
        "validation_end": validation_end,
        "train_count": train.height,
        "purged_count": cohorts.purged_count,
        "validation_count": validation.height,
        "train_base_rate": (
            float(train["strong"].mean()) if train.height else None
        ),
        "validation_base_rate": (
            float(validation["strong"].mean()) if validation.height else None
        ),
    }


def _ensure_early_fail_label(events: pl.DataFrame) -> pl.DataFrame:
    if "early_fail_5d" in events.columns:
        return events
    required = (
        "mae_5d",
        "entry_unavailable",
        "entry_limit_locked",
        "scale_break_suspected",
    )
    missing = [column for column in required if column not in events.columns]
    if missing:
        raise ValueError(f"来源记录无法派生 early_fail_5d，缺少字段: {missing}")
    mae = pl.col("mae_5d").cast(pl.Float64, strict=False)
    labelable = (
        mae.is_finite()
        & pl.col("entry_unavailable").eq(False)
        & pl.col("entry_limit_locked").eq(False)
        & pl.col("scale_break_suspected").eq(False)
    )
    return events.with_columns(
        pl.when(labelable)
        .then(mae <= -0.08 + 1e-12)
        .otherwise(None)
        .alias("early_fail_5d"),
    )


def _sample_summary(events: pl.DataFrame) -> dict:
    exclusion_fields = (
        "right_censored",
        "entry_unavailable",
        "entry_limit_locked",
        "outcome_unavailable",
        "scale_break_suspected",
    )
    required = ("strong", *exclusion_fields)
    missing = [column for column in required if column not in events.columns]
    if missing:
        raise ValueError(f"来源记录缺少样本质量字段: {missing}")
    eligible = events.filter(pl.col("strong").is_not_null())
    exclusions = {
        name: int(events[name].sum() or 0)
        for name in exclusion_fields
    }
    return {
        "status": "ok",
        "total_events": events.height,
        "eligible_events": eligible.height,
        "excluded_events": events.height - eligible.height,
        "excluded": exclusions,
        "base_strong_rate": float(eligible["strong"].mean()) if eligible.height else None,
    }


def _as_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("source_run_id")
    args = parser.parse_args()
    report = run_study(args.data_dir, args.source_run_id)
    print(json.dumps(report, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
