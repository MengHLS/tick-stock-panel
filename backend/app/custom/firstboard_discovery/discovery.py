"""Tie-aware factor screening and bounded explainable rule search."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Literal

import numpy as np
import polars as pl

from app.backtest.stats_v2 import bh_fdr_qvalues

_MIN_TRAIN_HITS = 30
_MIN_VALIDATION_HITS = 15
_MIN_COVERAGE = 0.60
_MAX_FACTORS = 8
_MAX_RULES = 8


@dataclass(frozen=True)
class FactorScore:
    factor_id: str
    snapshot: str
    direction: Literal["high", "low"] | None
    auc: float | None
    p_value: float | None
    q_value: float | None
    coverage: float
    train_count: int


def score_factor(
    factor_id: str,
    snapshot: str,
    values: Sequence[float | None],
    labels: Sequence[bool | None],
) -> FactorScore:
    """Score one factor with binary rank AUC and a tie-aware p-value."""
    if len(values) != len(labels):
        raise ValueError("factor values and labels must have the same length")
    pairs = [
        (float(value), bool(label))
        for value, label in zip(values, labels, strict=True)
        if value is not None
        and label is not None
        and math.isfinite(float(value))
    ]
    coverage = len(pairs) / len(values) if values else 0.0
    if not pairs:
        return FactorScore(factor_id, snapshot, None, None, None, None, coverage, 0)
    factor_values = np.asarray([pair[0] for pair in pairs], dtype=float)
    binary_labels = np.asarray([pair[1] for pair in pairs], dtype=bool)
    auc, p_value = _rank_auc(factor_values, binary_labels)
    direction: Literal["high", "low"] | None = None
    if auc is not None and abs(auc - 0.5) > 1e-12:
        direction = "high" if auc > 0.5 else "low"
    return FactorScore(
        factor_id=factor_id,
        snapshot=snapshot,
        direction=direction,
        auc=auc,
        p_value=p_value,
        q_value=None,
        coverage=coverage,
        train_count=len(pairs),
    )


def search_rules(
    events: pl.DataFrame,
    factor_columns: Sequence[tuple[str, str]],
    *,
    train_end: date,
    base_rate: float,
) -> list[dict[str, Any]]:
    """Select explainable rules on training dates and evaluate validation only."""
    required = {
        "date", "strong",
        "mfe_5d", "close_return_5d", "mae_5d",
        "mfe_10d", "close_return_10d", "mae_10d",
        "mfe_20d", "close_return_20d", "mae_20d",
    }
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f"rule search events missing columns: {missing}")
    if events.is_empty():
        return []

    valid_label = pl.col("strong").is_not_null()
    train = events.filter((pl.col("date") <= train_end) & valid_label)
    validation = events.filter((pl.col("date") > train_end) & valid_label)
    if train.is_empty() or validation.is_empty():
        return []

    scores = _factor_scores(train, factor_columns)
    eligible = [
        score
        for score in scores
        if score.auc is not None
        and score.direction is not None
        and score.coverage >= _MIN_COVERAGE
        and score.train_count >= _MIN_TRAIN_HITS
    ]
    eligible.sort(
        key=lambda score: (
            -abs((score.auc if score.auc is not None else 0.5) - 0.5),
            -score.coverage,
            score.factor_id,
        )
    )
    selected = eligible[:_MAX_FACTORS]
    if not selected:
        return []

    candidates: list[dict[str, Any]] = []
    for score in selected:
        candidates.extend(_single_factor_rules(events, score, train_end))

    top_four = selected[:4]
    for left_index, left in enumerate(top_four):
        for right in top_four[left_index + 1:]:
            candidates.extend(_multi_factor_rules(events, [left, right], train_end))
    if train.height >= 600:
        candidates.extend(_multi_factor_rules(events, selected[:3], train_end))

    evaluated: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        rule = _evaluate_candidate(
            candidate,
            events,
            train_end=train_end,
            base_rate=base_rate,
        )
        if rule is None:
            continue
        evaluated[rule["id"]] = rule

    ranked = sorted(
        evaluated.values(),
        key=lambda rule: (
            -float(rule["train_priority"]),
            -float(rule["train_strong_rate"]),
            -int(rule["train_hits"]),
            rule["id"],
        ),
    )
    return ranked[:_MAX_RULES]


def _factor_scores(
    train: pl.DataFrame,
    factor_columns: Sequence[tuple[str, str]],
) -> list[FactorScore]:
    labels = train["strong"].to_list()
    scores: list[FactorScore] = []
    for factor_id, snapshot in factor_columns:
        column = f"{snapshot}__{factor_id}"
        if column not in train.columns:
            continue
        scores.append(
            score_factor(factor_id, snapshot, train[column].to_list(), labels)
        )
    q_values = bh_fdr_qvalues([score.p_value for score in scores])
    return [
        replace(score, q_value=q_value)
        for score, q_value in zip(scores, q_values, strict=True)
    ]


def _single_factor_rules(
    events: pl.DataFrame,
    score: FactorScore,
    train_end: date,
) -> list[dict[str, Any]]:
    column = f"{score.snapshot}__{score.factor_id}"
    train_values = _finite_values(events, column, train_end, training=True)
    if train_values.size == 0 or score.direction is None:
        return []
    result = []
    for quantile in (0.2, 0.4, 0.6, 0.8):
        threshold = float(np.quantile(train_values, quantile))
        operator = ">=" if score.direction == "high" else "<="
        condition = {
            "factor_id": score.factor_id,
            "snapshot": score.snapshot,
            "operator": operator,
            "threshold": threshold,
        }
        result.append({
            "conditions": [condition],
            "dimension": 1,
            "uses": [(column, operator, threshold)],
        })
    return result


def _multi_factor_rules(
    events: pl.DataFrame,
    scores: Sequence[FactorScore],
    train_end: date,
) -> list[dict[str, Any]]:
    if not scores:
        return []
    factor_data: list[tuple[FactorScore, str, float, float]] = []
    for score in scores:
        column = f"{score.snapshot}__{score.factor_id}"
        values = _finite_values(events, column, train_end, training=True)
        if values.size == 0:
            return []
        lower, upper = np.quantile(values, [1 / 3, 2 / 3])
        factor_data.append((score, column, float(lower), float(upper)))

    results: list[dict[str, Any]] = []
    for buckets in _cartesian_buckets(len(factor_data)):
        conditions = []
        uses = []
        for (score, column, lower, upper), bucket in zip(
            factor_data,
            buckets,
            strict=True,
        ):
            if bucket == 0:
                bucket_lower, bucket_upper = None, lower
            elif bucket == 1:
                bucket_lower, bucket_upper = lower, upper
            else:
                bucket_lower, bucket_upper = upper, None
            conditions.append({
                "factor_id": score.factor_id,
                "snapshot": score.snapshot,
                "operator": "between",
                "lower": bucket_lower,
                "upper": bucket_upper,
                "bucket": bucket,
            })
            uses.append((column, "bucket", (lower, upper, bucket)))
        results.append({
            "conditions": conditions,
            "dimension": len(factor_data),
            "uses": uses,
        })
    return results


def _cartesian_buckets(size: int):
    if size == 0:
        yield ()
        return
    for prefix in _cartesian_buckets(size - 1):
        for bucket in range(3):
            yield (*prefix, bucket)


def _evaluate_candidate(
    candidate: dict[str, Any],
    events: pl.DataFrame,
    *,
    train_end: date,
    base_rate: float,
) -> dict[str, Any] | None:
    hit = _candidate_mask(events, candidate["uses"])
    valid_label = pl.col("strong").is_not_null()
    train = events.filter((pl.col("date") <= train_end) & valid_label)
    validation = events.filter((pl.col("date") > train_end) & valid_label)
    train_hit = hit.filter(pl.col("date") <= train_end)
    validation_hit = hit.filter(pl.col("date") > train_end)
    if train_hit.height < _MIN_TRAIN_HITS:
        return None

    train_labels = train_hit["strong"].fill_null(False).to_numpy()
    validation_labels = validation_hit["strong"].fill_null(False).to_numpy()
    train_rate = float(np.mean(train_labels))
    validation_rate = (
        float(np.mean(validation_labels)) if validation_labels.size else None
    )
    validation_base = float(
        validation["strong"].drop_nulls().cast(pl.Float64).mean() or 0.0
    )
    validation_lift = (
        validation_rate / validation_base
        if validation_rate is not None and validation_base > 0
        else None
    )
    condition_key = json.dumps(
        candidate["conditions"],
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    rule_id = "fbr_" + hashlib.sha1(condition_key.encode("utf-8")).hexdigest()[:12]
    wilson = _wilson_lower_bound(int(train_labels.sum()), train_hit.height)
    rule = {
        "id": rule_id,
        "conditions": candidate["conditions"],
        "dimension": int(candidate["dimension"]),
        "hit_count": train_hit.height + validation_hit.height,
        "train_hits": train_hit.height,
        "validation_hits": validation_hit.height,
        "validation_eligible": validation_hit.height >= _MIN_VALIDATION_HITS,
        "coverage": (train_hit.height + validation_hit.height) / events.height,
        "train_strong_rate": train_rate,
        "validation_strong_rate": validation_rate,
        "lift": train_rate / base_rate if base_rate > 0 else None,
        "validation_lift": validation_lift,
        "train_auc": _binary_rule_auc(train, train_hit),
        "validation_auc": _binary_rule_auc(validation, validation_hit),
        "wilson_lower_bound": wilson,
        "train_priority": wilson - base_rate,
    }
    for horizon in (5, 10, 20):
        rule[f"mean_mfe_{horizon}d"] = _mean(validation_hit[f"mfe_{horizon}d"])
        rule[f"mean_close_return_{horizon}d"] = _mean(
            validation_hit[f"close_return_{horizon}d"]
        )
        rule[f"mean_mae_{horizon}d"] = _mean(validation_hit[f"mae_{horizon}d"])
    return rule


def _candidate_mask(events: pl.DataFrame, uses: Sequence[tuple]) -> pl.DataFrame:
    mask = pl.lit(True)
    for use in uses:
        column, operator, value = use
        mask = mask & pl.col(column).is_not_null() & pl.col(column).is_finite()
        if operator == ">=":
            mask = mask & (pl.col(column) >= value)
        elif operator == "<=":
            mask = mask & (pl.col(column) <= value)
        elif operator == "range":
            lower, upper = value
            mask = mask & pl.col(column).is_not_null() & pl.col(column).is_finite()
            if lower is not None:
                mask = mask & (pl.col(column) >= lower)
            if upper is not None:
                mask = mask & (pl.col(column) < upper)
        else:
            lower, upper, bucket = value
            bucket_expression = (
                (pl.col(column) >= lower).cast(pl.Int32)
                + (pl.col(column) >= upper).cast(pl.Int32)
            )
            mask = mask & (bucket_expression == bucket)
    return events.filter(mask.fill_null(False))


def _binary_rule_auc(all_events: pl.DataFrame, hit_events: pl.DataFrame) -> float | None:
    all_labels = all_events["strong"].drop_nulls().cast(pl.Boolean)
    hit_labels = hit_events["strong"].drop_nulls().cast(pl.Boolean)
    if all_labels.is_empty() or hit_labels.is_empty():
        return None
    total_positives = int(all_labels.sum() or 0)
    total_negatives = all_labels.len() - total_positives
    hit_positives = int(hit_labels.sum() or 0)
    hit_negatives = hit_labels.len() - hit_positives
    if total_positives == 0 or total_negatives == 0:
        return None
    true_positive_rate = hit_positives / total_positives
    true_negative_rate = (total_negatives - hit_negatives) / total_negatives
    return float((true_positive_rate + true_negative_rate) / 2.0)


def _finite_values(
    events: pl.DataFrame,
    column: str,
    train_end: date,
    *,
    training: bool,
) -> np.ndarray:
    frame = events.filter(pl.col("date") <= train_end) if training else events
    if column not in frame.columns:
        return np.asarray([], dtype=float)
    values = frame[column].cast(pl.Float64, strict=False).to_numpy()
    return values[np.isfinite(values)]


def _rank_auc(values: np.ndarray, labels: np.ndarray) -> tuple[float | None, float | None]:
    positives = int(labels.sum())
    negatives = int(labels.size - positives)
    if positives == 0 or negatives == 0 or values.size < 2:
        return None, None
    ranks = _average_ranks(values)
    u_stat = float(ranks[labels].sum() - positives * (positives + 1) / 2.0)
    auc = u_stat / (positives * negatives)
    tie_counts = np.unique(values, return_counts=True)[1]
    tie_sum = float(np.sum(tie_counts.astype(float) ** 3 - tie_counts))
    total = values.size
    variance = positives * negatives / 12.0 * (
        (total + 1.0) - tie_sum / (total * (total - 1.0))
    )
    if variance <= 0:
        return float(auc), None
    z_value = (u_stat - positives * negatives / 2.0) / math.sqrt(variance)
    p_value = math.erfc(abs(z_value) / math.sqrt(2.0))
    return float(auc), float(min(1.0, p_value))


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    ranks = np.empty(values.size, dtype=float)
    start = 0
    while start < values.size:
        stop = start + 1
        while stop < values.size and sorted_values[stop] == sorted_values[start]:
            stop += 1
        average_rank = (start + 1 + stop) / 2.0
        ranks[order[start:stop]] = average_rank
        start = stop
    return ranks


def _wilson_lower_bound(successes: int, total: int, z_value: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    proportion = successes / total
    denominator = 1.0 + z_value * z_value / total
    centre = proportion + z_value * z_value / (2.0 * total)
    margin = z_value * math.sqrt(
        proportion * (1.0 - proportion) / total
        + z_value * z_value / (4.0 * total * total)
    )
    return max(0.0, (centre - margin) / denominator)


def _mean(series: pl.Series) -> float | None:
    values = series.cast(pl.Float64, strict=False).drop_nulls().to_numpy()
    values = values[np.isfinite(values)]
    return float(np.mean(values)) if values.size else None
