"""Chronological early-loss research; no execution or strategy decisions."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date

import numpy as np
import polars as pl

from app.backtest.stats_v2 import bh_fdr_qvalues
from app.custom.firstboard_discovery.discovery import score_factor

MAIN_COLUMN = "D_minus_1__boll_width"
MAIN_THRESHOLD = 0.41986322631304357
_METRICS = [
    "strong", "early_fail_5d",
    *[f"{metric}_{horizon}d" for horizon in (5, 10, 20)
      for metric in ("mfe", "close_return", "mae")],
]


@dataclass(frozen=True)
class ResearchCohorts:
    eligible: pl.DataFrame
    train: pl.DataFrame
    validation: pl.DataFrame
    unpurged_train_count: int
    purged_count: int


def prepare_research_cohorts(
    events: pl.DataFrame,
    *,
    train_end: date,
    validation_start: date,
) -> ResearchCohorts:
    """Use one complete-label cohort and purge train outcomes crossing validation."""
    if train_end >= validation_start:
        raise ValueError("训练截止日必须早于验证开始日")
    required = {"date", "outcome_end", "strong"}
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f"研究样本缺少时间/标签字段: {missing}")
    eligible = events.filter(pl.col("strong").is_not_null())
    unpurged_train = eligible.filter(pl.col("date") <= train_end)
    train = unpurged_train.filter(pl.col("outcome_end") < validation_start)
    validation = eligible.filter(pl.col("date") >= validation_start)
    return ResearchCohorts(
        eligible=eligible,
        train=train,
        validation=validation,
        unpurged_train_count=unpurged_train.height,
        purged_count=unpurged_train.height - train.height,
    )


def fit_negative_model(
    events: pl.DataFrame,
    factor_columns: Sequence[tuple[str, str]],
    *,
    train_end: date,
) -> dict:
    """Fit on early training dates and freeze a later-training risk quantile."""
    model = {
        "status": "insufficient_sample",
        "method": "ridge_logistic_v1",
        "target": "early_fail_5d",
        "features": [], "decision_threshold": None,
        "ridge": 1.0, "risk_quantile": 0.8,
        "train_end": train_end, "fit_count": 0, "calibration_count": 0,
    }
    train = events.filter(
        (pl.col("date") <= train_end) & pl.col("early_fail_5d").is_not_null(),
    ).sort("date")
    dates = train["date"].unique().sort().to_list()
    if len(dates) < 10 or train.height < 120:
        return model
    calibration_start = dates[min(int(len(dates) * 0.7), len(dates) - 1)]
    fit = train.filter(pl.col("date") < calibration_start)
    if "outcome_end" in fit.columns:
        fit = fit.filter(pl.col("outcome_end") < calibration_start)
    calibration = train.filter(pl.col("date") >= calibration_start)
    model.update(
        calibration_start=calibration_start, fit_count=fit.height,
        calibration_count=calibration.height,
    )
    y = fit["early_fail_5d"].cast(pl.Float64).to_numpy()
    if (
        fit.height < 80 or calibration.height < 30
        or min(float(y.sum()), float(len(y) - y.sum())) < 10
    ):
        return model
    candidates = []
    for factor_id, snapshot in sorted(set(factor_columns)):
        column = f"{snapshot}__{factor_id}"
        if column not in fit.columns:
            continue
        score = score_factor(
            factor_id, snapshot, fit[column].to_list(),
            fit["early_fail_5d"].to_list(),
        )
        candidates.append(asdict(score))
    q_values = bh_fdr_qvalues([row["p_value"] for row in candidates])
    for row, q_value in zip(candidates, q_values, strict=True):
        row["q_value"] = q_value
    candidates.sort(key=lambda row: (
        -abs((row["auc"] if row["auc"] is not None else 0.5) - 0.5),
        row["factor_id"], row["snapshot"],
    ))
    features: list[dict] = []
    raw_columns: list[np.ndarray] = []
    for row in candidates:
        if (
            row["auc"] is None or abs(row["auc"] - 0.5) < 0.03
            or row["coverage"] < 0.6
            or row["q_value"] is None or row["q_value"] > 0.10
            or any(f["factor_id"] == row["factor_id"] for f in features)
        ):
            continue
        column = f"{row['snapshot']}__{row['factor_id']}"
        raw = _values(fit, column)
        finite = raw[np.isfinite(raw)]
        lower, median, upper = np.quantile(finite, [0.25, 0.5, 0.75])
        scale = float(upper - lower)
        if scale < 1e-12:
            scale = float(np.std(finite))
        if scale < 1e-12:
            continue
        duplicate = False
        for previous in raw_columns:
            paired = np.isfinite(raw) & np.isfinite(previous)
            if paired.sum() < 30:
                duplicate = True
                break
            if abs(float(np.corrcoef(raw[paired], previous[paired])[0, 1])) >= 0.85:
                duplicate = True
                break
        if duplicate:
            continue
        features.append({
            **row, "column": column, "median": float(median), "scale": scale,
        })
        raw_columns.append(raw)
        if len(features) == 3:
            break
    if not features:
        return {**model, "status": "no_supported_factor"}
    x, known = _matrix(fit, features)
    x, y = x[known], y[known]
    model["fit_scored_count"] = int(known.sum())
    if len(y) < 80 or min(float(y.sum()), float(len(y) - y.sum())) < 10:
        return model
    design = np.column_stack([np.ones(len(x)), x])
    coefficients = np.zeros(design.shape[1])
    coefficients[0] = np.log((y.sum() + 0.5) / (len(y) - y.sum() + 0.5))
    penalty = np.diag([0.0, *[1.0] * x.shape[1]])
    converged = False
    for _ in range(100):
        probability = _sigmoid(design @ coefficients)
        gradient = design.T @ (probability - y) + penalty @ coefficients
        weights = np.maximum(probability * (1.0 - probability), 1e-8)
        hessian = (design.T * weights) @ design + penalty
        step = np.linalg.solve(hessian, gradient)
        coefficients -= step
        if float(np.max(np.abs(step))) < 1e-7:
            converged = True
            break
    if not converged or not bool(np.isfinite(coefficients).all()):
        return {**model, "status": "fit_failed"}
    for feature, coefficient in zip(features, coefficients[1:], strict=True):
        feature["coefficient"] = float(coefficient)
    model.update(
        status="ok", features=features, intercept=float(coefficients[0]),
        fit_end=fit["date"].max(),
        fit_outcome_end=fit["outcome_end"].max() if "outcome_end" in fit.columns else None,
    )
    fitted = predict_negative_risk(fit, model)
    model.update(_diagnostics(fit, fitted, "train"))
    calibrated = predict_negative_risk(calibration, model)
    model.update(_diagnostics(calibration, calibrated, "calibration"))
    threshold_values = calibrated[np.isfinite(calibrated)]
    threshold_source = "calibration_all"
    if MAIN_COLUMN in calibration.columns:
        main = _main_mask(calibration)
        main_scores = calibrated[main & np.isfinite(calibrated)]
        if len(main_scores) >= 30:
            threshold_values = main_scores
            threshold_source = "calibration_main"
    if len(threshold_values) < 30:
        return {**model, "status": "insufficient_calibration", "decision_threshold": None}
    model.update(
        decision_threshold=float(np.quantile(threshold_values, 0.8)),
        threshold_source=threshold_source, threshold_count=len(threshold_values),
    )
    return model


def predict_negative_risk(events: pl.DataFrame, model: dict) -> np.ndarray:
    """Unknown selected factor inputs stay unknown, never silently pass a veto."""
    result = np.full(events.height, np.nan)
    if model["status"] != "ok":
        return result
    matrix, known = _matrix(events, model["features"])
    coefficients = np.asarray([f["coefficient"] for f in model["features"]])
    result[known] = _sigmoid(matrix[known] @ coefficients + model["intercept"])
    return result


def build_negative_research(
    train: pl.DataFrame,
    validation: pl.DataFrame,
    factor_columns: Sequence[tuple[str, str]],
    *,
    train_end: date,
) -> dict:
    """Evaluate frozen main and negative signals on a common validation cohort."""
    model = fit_negative_model(train, factor_columns, train_end=train_end)
    report = {
        "status": model["status"], "model": model, "groups": [],
        "main": {"factor_id": "boll_width", "snapshot": "D_minus_1",
                 "operator": ">=", "threshold": MAIN_THRESHOLD},
        "evidence": "retrospective_exploratory",
    }
    if model["status"] != "ok":
        return report
    if MAIN_COLUMN not in validation.columns:
        return {**report, "status": "main_feature_unavailable"}
    probabilities = predict_negative_risk(validation, model)
    model.update(_diagnostics(validation, probabilities, "validation"))
    main_values = _values(validation, MAIN_COLUMN)
    paired = (
        np.isfinite(probabilities) & np.isfinite(main_values)
        & np.isfinite(_values(validation, "early_fail_5d"))
        & np.isfinite(_values(validation, "strong"))
    )
    report.update(
        validation_count=validation.height, paired_count=int(paired.sum()),
        unscored_count=validation.height - int(paired.sum()),
        risk_scored_count=int(np.isfinite(probabilities).sum()),
    )
    if not bool(paired.any()):
        return {**report, "status": "no_scorable_validation"}
    main = _main_mask(validation) & paired
    keep = (probabilities < model["decision_threshold"]) & paired
    masks = {"baseline": paired, "main_only": main,
             "negative_only": keep, "combined": main & keep}
    groups = [_group_summary(validation, mask, group_id, int(paired.sum()))
              for group_id, mask in masks.items()]
    for group in groups:
        base_rate = groups[0]["strong_rate"]
        group["strong_lift"] = group["strong_rate"] / base_rate if base_rate else None
    combined, primary = groups[3], groups[1]
    strong = _values(validation, "strong")
    early = _values(validation, "early_fail_5d")
    primary_strong = int(strong[main].sum())
    primary_early = int(early[main].sum())
    intervals = _paired_intervals(validation, masks)
    report.update(
        status="ok", groups=groups,
        main_retention=combined["count"] / primary["count"] if primary["count"] else None,
        main_strong_retention=(
            int(strong[masks["combined"]].sum()) / primary_strong if primary_strong else None
        ),
        main_early_fail_removed=(
            int(early[main & ~keep].sum()) / primary_early if primary_early else None
        ),
        combined_vs_main={
            key: value for key, value in intervals.items()
            if key not in {"status", "event_days"}
        },
        bootstrap={"unit": "moving_block_event_date", "block_dates": 20,
                   "samples": 500, "seed": 20261030,
                   "status": intervals["status"],
                   "event_days": intervals["event_days"]},
    )
    return report


def _group_summary(events: pl.DataFrame, mask: np.ndarray, group_id: str, total: int) -> dict:
    count = int(mask.sum())
    result = {
        "id": group_id, "count": count, "coverage": count / total if total else None,
        "event_days": int(events.filter(pl.Series(mask))["date"].n_unique()),
    }
    for metric in _METRICS:
        values = _values(events, metric)[mask]
        values = values[np.isfinite(values)]
        key = (
            "strong_rate" if metric == "strong"
            else "early_fail_rate" if metric == "early_fail_5d"
            else f"mean_{metric}"
        )
        result[key] = float(values.mean()) if len(values) else None
    return result


def _paired_intervals(events: pl.DataFrame, masks: dict[str, np.ndarray]) -> dict:
    """Resample consecutive event dates together, retaining paired group masks."""
    days = events["date"].unique().sort().to_list()
    if len(days) <= 20:
        return {
            "status": "insufficient_temporal_support",
            "event_days": len(days),
            "early_fail_difference_95": None,
            "early_fail_valid_draws": 0,
            "strong_difference_95": None,
            "strong_valid_draws": 0,
        }
    lookup = {day: index for index, day in enumerate(days)}
    day_index = np.asarray([lookup[day] for day in events["date"].to_list()])
    rng = np.random.default_rng(20261030)
    block_size = min(20, len(days))
    blocks = (len(days) + block_size - 1) // block_size
    starts = rng.integers(0, len(days), (500, blocks))
    indices = ((starts[:, :, None] + np.arange(block_size)) % len(days)).reshape(500, -1)
    indices = indices[:, :len(days)]
    sampled = {}
    for name in ("main_only", "combined"):
        mask = masks[name]
        counts = np.bincount(day_index, weights=mask, minlength=len(days))
        denominator = counts[indices].sum(axis=1)
        for metric in ("strong", "early_fail_5d"):
            values = _values(events, metric)
            sums = np.bincount(
                day_index, weights=np.where(mask, values, 0.0), minlength=len(days),
            )
            sampled[name, metric] = np.divide(
                sums[indices].sum(axis=1), denominator,
                out=np.full(500, np.nan), where=denominator > 0,
            )
    result = {}
    for metric, key in (("strong", "strong"), ("early_fail_5d", "early_fail")):
        differences = sampled["combined", metric] - sampled["main_only", metric]
        finite = differences[np.isfinite(differences)]
        result[f"{key}_difference_95"] = (
            np.quantile(finite, [0.025, 0.975]).tolist() if len(finite) else None
        )
        result[f"{key}_valid_draws"] = len(finite)
    return {**result, "status": "ok", "event_days": len(days)}


def _values(events: pl.DataFrame, column: str) -> np.ndarray:
    if column not in events.columns:
        return np.full(events.height, np.nan)
    return events[column].cast(pl.Float64, strict=False).to_numpy().astype(float)


def _matrix(events: pl.DataFrame, features: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    raw = np.column_stack([_values(events, feature["column"]) for feature in features])
    known = np.isfinite(raw).all(axis=1)
    scaled = np.column_stack([
        np.clip((raw[:, index] - feature["median"]) / feature["scale"], -6.0, 6.0)
        for index, feature in enumerate(features)
    ])
    return scaled, known


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -35.0, 35.0)))


def _diagnostics(events: pl.DataFrame, probabilities: np.ndarray, prefix: str) -> dict:
    y = _values(events, "early_fail_5d")
    known = np.isfinite(y) & np.isfinite(probabilities)
    labels, scores = y[known], probabilities[known]
    if not len(labels):
        return {f"{prefix}_auc": None, f"{prefix}_brier": None,
                f"{prefix}_baseline_brier": None, f"{prefix}_calibration": []}
    score = score_factor("negative", "probability", scores.tolist(), labels.astype(bool).tolist())
    bins = []
    for lower, upper in zip((0.0, 0.2, 0.4, 0.6, 0.8), (0.2, 0.4, 0.6, 0.8, 1.01), strict=True):
        selected = (scores >= lower) & (scores < upper)
        count = int(selected.sum())
        bins.append({
            "lower": lower, "upper": min(upper, 1.0), "count": count,
            "predicted": float(scores[selected].mean()) if count else None,
            "observed": float(labels[selected].mean()) if count else None,
        })
    return {
        f"{prefix}_auc": score.auc,
        f"{prefix}_brier": float(np.mean((scores - labels) ** 2)),
        f"{prefix}_baseline_brier": float(np.mean((labels - labels.mean()) ** 2)),
        f"{prefix}_calibration": bins,
    }


def _main_mask(events: pl.DataFrame) -> np.ndarray:
    values = _values(events, MAIN_COLUMN)
    return np.isfinite(values) & (values >= MAIN_THRESHOLD)
