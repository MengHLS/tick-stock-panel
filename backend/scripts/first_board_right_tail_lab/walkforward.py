"""Expanding-window model predictions with event-level right-tail ranking."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date

import polars as pl

from .model import (
    PREDICTION_COLUMNS,
    CalibrationChoice,
    ModelConfig,
    fit_calibrated_bundle,
    predict_model_bundle,
    prepare_model_frame,
)
from .splits import (
    DEFAULT_FOLDS,
    assign_expanding_folds,
    event_top_decile_decisions,
    first_top_decile_decisions,
    freeze_top_decile_threshold,
)

_ACTUAL_COLUMNS = (
    "decision_id",
    "event_id",
    "symbol",
    "decision_date",
    "signal_available_time",
    "market_fillable",
    "label_observable",
    "stop_first",
    "fast_strong",
    "mfe_touch_20d",
    "mfe_exec_20d",
    "exec_return",
    "peak_day",
    "sample_weight",
    "fold",
    "role",
)


@dataclass(frozen=True)
class WalkforwardResult:
    predictions: pl.DataFrame
    folds: pl.DataFrame
    top_decisions: pl.DataFrame
    frozen_threshold_decisions: pl.DataFrame
    calibration: pl.DataFrame
    model_status: pl.DataFrame


def _attach_predictions(
    actual: pl.DataFrame,
    predicted: pl.DataFrame,
) -> pl.DataFrame:
    required = {"decision_id", *PREDICTION_COLUMNS}
    missing = required - set(predicted.columns)
    if missing:
        raise ValueError(
            f"model predictions missing required columns: {sorted(missing)}"
        )
    if predicted["decision_id"].n_unique() != predicted.height:
        raise ValueError("model predictions contain duplicate decision_id")
    joined = actual.select(
        column for column in _ACTUAL_COLUMNS if column in actual.columns
    ).join(
        predicted.select("decision_id", *PREDICTION_COLUMNS),
        on="decision_id",
        how="left",
        validate="1:1",
    )
    if joined.height != actual.height:
        raise ValueError("prediction join changed row count")
    missing_predictions = joined.select(
        pl.any_horizontal(
            pl.col(column).is_null()
            for column in PREDICTION_COLUMNS
        )
    ).to_series()
    if missing_predictions.any():
        raise ValueError("some decisions are missing model predictions")
    return joined


def _mean(frame: pl.DataFrame, column: str) -> float | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    values = frame[column].cast(pl.Float64)
    values = values.filter(values.is_not_null() & values.is_finite())
    return float(values.mean()) if values.len() else None


def _rate(
    frame: pl.DataFrame,
    predicate: pl.Expr,
) -> float | None:
    eligible = frame.filter(
        pl.col("label_observable").fill_null(False)
    )
    if eligible.is_empty():
        return None
    return float(eligible.select(predicate.mean()).item())


def _boolean_rate(
    frame: pl.DataFrame,
    predicate: pl.Expr,
) -> float | None:
    if frame.is_empty():
        return None
    values = (
        frame.select(predicate.cast(pl.Float64).alias("_value"))["_value"]
        .drop_nulls()
    )
    return float(values.mean()) if values.len() else None


def _selection_metrics(
    prefix: str,
    selected: pl.DataFrame,
    validation_events: int,
) -> dict:
    label_observable = selected.filter(
        pl.col("label_observable").fill_null(False)
    )
    return {
        f"{prefix}_events": selected.height,
        f"{prefix}_event_fraction": (
            selected.height / validation_events
            if validation_events
            else None
        ),
        f"{prefix}_actual_fillable_rate": _boolean_rate(
            selected,
            pl.col("market_fillable"),
        ),
        f"{prefix}_stop_first_rate": _rate(
            label_observable,
            pl.col("stop_first") == 1,
        ),
        f"{prefix}_mean_mfe_touch": _mean(
            label_observable,
            "mfe_touch_20d",
        ),
        f"{prefix}_mfe_touch_30_rate": _rate(
            label_observable,
            pl.col("mfe_touch_20d") >= 0.30,
        ),
        f"{prefix}_mfe_touch_50_rate": _rate(
            label_observable,
            pl.col("mfe_touch_20d") >= 0.50,
        ),
        f"{prefix}_mean_peak_day": _mean(
            label_observable,
            "peak_day",
        ),
        f"{prefix}_mean_score": _mean(selected, "score"),
    }


def _fold_metric(
    *,
    fold: str,
    train: pl.DataFrame,
    validation_scored: pl.DataFrame,
    top: pl.DataFrame,
    frozen: pl.DataFrame,
    threshold: float,
) -> dict:
    validation_events = validation_scored["event_id"].n_unique()
    return {
        "fold": fold,
        "train_decisions": train.height,
        "train_events": train["event_id"].n_unique(),
        "validation_decisions": validation_scored.height,
        "validation_events": validation_events,
        "threshold": float(threshold),
        **_selection_metrics("top", top, validation_events),
        **_selection_metrics(
            "frozen_threshold",
            frozen,
            validation_events,
        ),
    }


def _calibration_frame(
    fold: str,
    choices: dict[str, CalibrationChoice],
) -> pl.DataFrame:
    rows = [
        {"fold": fold, **asdict(choice)}
        for choice in choices.values()
    ]
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def _model_status_frame(
    fold: str,
    bundle,
    choices: dict[str, CalibrationChoice],
) -> pl.DataFrame:
    rows = [
        {
            "fold": fold,
            "target": target,
            "status": bundle.statuses[target],
            "training_rows": bundle.training_rows[target],
            "training_events": bundle.training_events[target],
            "calibration_method": (
                choices[target].method
                if target in choices
                else None
            ),
        }
        for target in bundle.statuses
    ]
    return pl.DataFrame(rows)


def run_model_walkforward(
    decisions: pl.DataFrame,
    config: ModelConfig | None = None,
    folds: Sequence[dict] = DEFAULT_FOLDS,
    *,
    sessions: Sequence[date] | None = None,
    purge_sessions: int = 30,
) -> WalkforwardResult:
    """Fit each fold on prior events and rank its validation events."""
    if sessions is None:
        raise ValueError(
            "authoritative trading sessions are required for walkforward "
            "folds"
        )
    ordered_sessions = sorted(set(sessions))
    if not ordered_sessions:
        raise ValueError("trading sessions must not be empty")
    config = config or ModelConfig()
    assigned = assign_expanding_folds(
        decisions,
        ordered_sessions,
        folds=folds,
        purge_sessions=purge_sessions,
    )
    prepared = prepare_model_frame(assigned)
    prediction_frames: list[pl.DataFrame] = []
    top_frames: list[pl.DataFrame] = []
    frozen_frames: list[pl.DataFrame] = []
    metric_rows: list[dict] = []
    calibration_frames: list[pl.DataFrame] = []
    model_status_frames: list[pl.DataFrame] = []

    for fold in folds:
        name = str(fold["name"])
        fold_rows = prepared.filter(pl.col("fold") == name)
        train = fold_rows.filter(pl.col("role") == "train")
        validation = fold_rows.filter(pl.col("role") == "validation")
        if validation.is_empty():
            continue
        if train.is_empty():
            raise ValueError(
                f"fold {name} has validation rows but no training rows"
            )

        bundle, choices = fit_calibrated_bundle(train, config)
        train_scored = _attach_predictions(
            train,
            predict_model_bundle(train, bundle),
        )
        validation_scored = _attach_predictions(
            validation,
            predict_model_bundle(validation, bundle),
        )
        threshold = freeze_top_decile_threshold(train_scored)
        top = event_top_decile_decisions(
            validation_scored,
        ).with_columns(pl.lit(name).alias("fold"))
        frozen = first_top_decile_decisions(
            validation_scored,
            threshold,
            eligible=(
                pl.col("prob_market_fillable")
                >= config.min_fill_probability
            ),
        ).with_columns(pl.lit(name).alias("fold"))

        prediction_frames.append(validation_scored)
        top_frames.append(top)
        frozen_frames.append(frozen)
        calibration_frames.append(_calibration_frame(name, choices))
        model_status_frames.append(
            _model_status_frame(name, bundle, choices)
        )
        metric_rows.append(
            _fold_metric(
                fold=name,
                train=train,
                validation_scored=validation_scored,
                top=top,
                frozen=frozen,
                threshold=threshold,
            )
        )

    if not metric_rows:
        raise ValueError("no fold has validation decisions")

    predictions = pl.concat(
        prediction_frames,
        how="diagonal_relaxed",
    ).sort(["fold", "decision_date", "decision_id"])
    top_decisions = pl.concat(
        top_frames,
        how="diagonal_relaxed",
    ).sort(["fold", "signal_available_time", "event_id"])
    frozen_threshold_decisions = pl.concat(
        frozen_frames,
        how="diagonal_relaxed",
    ).sort(["fold", "signal_available_time", "event_id"])
    calibration = pl.concat(
        calibration_frames,
        how="diagonal_relaxed",
    ).sort(["fold", "target"])
    model_status = pl.concat(
        model_status_frames,
        how="diagonal_relaxed",
    ).sort(["fold", "target"])
    return WalkforwardResult(
        predictions=predictions,
        folds=pl.DataFrame(metric_rows).sort("fold"),
        top_decisions=top_decisions,
        frozen_threshold_decisions=frozen_threshold_decisions,
        calibration=calibration,
        model_status=model_status,
    )
