"""Leakage-safe multi-target models for first-board right-tail decisions."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import polars as pl

TargetKind = Literal["binary", "regression"]


@dataclass(frozen=True)
class TargetSpec:
    name: str
    kind: TargetKind
    eligibility: Literal["all", "observable", "executable"]


TARGET_SPECS: dict[str, TargetSpec] = {
    "market_fillable": TargetSpec(
        name="market_fillable",
        kind="binary",
        eligibility="all",
    ),
    "stop_first": TargetSpec(
        name="stop_first",
        kind="binary",
        eligibility="observable",
    ),
    "fast_strong": TargetSpec(
        name="fast_strong",
        kind="binary",
        eligibility="observable",
    ),
    "mfe_touch_30": TargetSpec(
        name="mfe_touch_30",
        kind="binary",
        eligibility="observable",
    ),
    "mfe_exec_30": TargetSpec(
        name="mfe_exec_30",
        kind="binary",
        eligibility="executable",
    ),
    "utility": TargetSpec(
        name="utility",
        kind="regression",
        eligibility="observable",
    ),
    "exec_return": TargetSpec(
        name="exec_return",
        kind="regression",
        eligibility="executable",
    ),
    "peak_day": TargetSpec(
        name="peak_day",
        kind="regression",
        eligibility="observable",
    ),
}

PROBABILITY_TARGETS = tuple(
    name for name, spec in TARGET_SPECS.items() if spec.kind == "binary"
)
PREDICTION_COLUMNS = (
    "prob_market_fillable",
    "prob_stop_first",
    "prob_fast_strong",
    "prob_mfe_touch_30",
    "prob_mfe_exec_30",
    "expected_utility",
    "expected_exec_return",
    "expected_peak_day",
    "score",
)
KEY_COLUMNS = (
    "decision_id",
    "event_id",
    "symbol",
    "decision_date",
    "signal_available_time",
    "days_waited",
    "sample_weight",
)
_FORBIDDEN_FEATURE_TARGETS = {
    *TARGET_SPECS,
    "entry_exec_adj",
    "mfe_touch_20d",
    "mae_touch_20d",
    "mfe_exec_20d",
    "mae_exec_20d",
    "ordering_ambiguous",
    "exit_status",
    "label_maturity_time",
}
_M2A_STRUCTURAL_FEATURES = {
    "current_vs_first5_high",
    "days_waited",
    "first5_high_vs_t_high",
    "first5_low_vs_t_close",
    "first5_range_pct",
    "first5_return_vs_t_close",
    "first5_volume_share_t",
    "locked_minute_ratio",
    "minutes_since_open",
    "minutes_above_vwap_ratio",
    "opening_gap",
    "price_vs_5m_ma5",
    "price_vs_t_high",
    "price_vs_vwap",
    "rule_a",
    "rule_b",
    "rule_c",
    "rule_d",
    "rule_e0",
    "volume_ratio_20",
    "volume_growth_last5_vs_first5",
}
_LABEL_LIKE_FRAGMENTS = {
    "entry_exec",
    "exec_return",
    "exit_status",
    "fast_strong",
    "future_",
    "label_",
    "mae",
    "maturity",
    "mfe",
    "peak_day",
    "stop_first",
    "utility",
}
_PREPARE_REQUIRED = {
    "decision_id",
    "event_id",
    "decision_date",
    "signal_available_time",
    "market_fillable",
    "label_observable",
    "mfe_touch_20d",
    "mfe_exec_20d",
    "peak_day",
    "stop_first",
    "exec_return",
}


@dataclass(frozen=True)
class ModelConfig:
    max_iter: int = 150
    learning_rate: float = 0.05
    max_leaf_nodes: int = 15
    random_state: int = 20261102
    min_training_samples: int = 20
    calibration_fraction: float = 0.2
    min_calibration_samples: int = 20
    min_fill_probability: float = 0.5

    def __post_init__(self) -> None:
        if self.max_iter < 1:
            raise ValueError("max_iter must be positive")
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive")
        if self.max_leaf_nodes < 2:
            raise ValueError("max_leaf_nodes must be at least two")
        if self.min_training_samples < 1:
            raise ValueError("min_training_samples must be positive")
        if not 0 < self.calibration_fraction < 1:
            raise ValueError("calibration_fraction must be between zero and one")
        if self.min_calibration_samples < 1:
            raise ValueError("min_calibration_samples must be positive")
        if not 0 <= self.min_fill_probability <= 1:
            raise ValueError("min_fill_probability must be between zero and one")


def prepare_model_frame(decisions: pl.DataFrame) -> pl.DataFrame:
    """Add explicit targets without redesigning the M2A decision rows."""
    missing = _PREPARE_REQUIRED - set(decisions.columns)
    if missing:
        raise ValueError(
            f"decisions missing required columns: {sorted(missing)}"
        )
    fillable = pl.col("market_fillable").fill_null(False)
    observable = (
        fillable
        & pl.col("label_observable").fill_null(False)
        & pl.col("mfe_touch_20d").is_not_null()
        & pl.col("mfe_touch_20d").is_finite()
        & pl.col("peak_day").is_not_null()
        & pl.col("stop_first").is_not_null()
    )
    executable = (
        observable
        & pl.col("mfe_exec_20d").is_not_null()
        & pl.col("mfe_exec_20d").is_finite()
    )
    finite_exec_return = (
        observable
        & pl.col("exec_return").is_not_null()
        & pl.col("exec_return").is_finite()
    )
    null_int = pl.lit(None, dtype=pl.Int8)
    null_float = pl.lit(None, dtype=pl.Float64)
    decay = (
        -(
            (pl.col("peak_day").cast(pl.Float64) - 5.0)
            .clip(lower_bound=0.0)
            / 10.0
        )
    ).exp()
    return decisions.with_columns(
        pl.when(observable)
        .then(pl.col("stop_first").cast(pl.Int8))
        .otherwise(null_int)
        .alias("stop_first"),
        pl.when(observable)
        .then(
            (
                ~pl.col("stop_first")
                & (pl.col("mfe_touch_20d") >= 0.30)
                & (pl.col("peak_day") <= 10)
            ).cast(pl.Int8)
        )
        .otherwise(null_int)
        .alias("fast_strong"),
        pl.when(observable)
        .then((pl.col("mfe_touch_20d") >= 0.30).cast(pl.Int8))
        .otherwise(null_int)
        .alias("mfe_touch_30"),
        pl.when(executable)
        .then((pl.col("mfe_exec_20d") >= 0.30).cast(pl.Int8))
        .otherwise(null_int)
        .alias("mfe_exec_30"),
        pl.when(observable)
        .then(
            pl.when(pl.col("stop_first"))
            .then(0.0)
            .otherwise(pl.col("mfe_touch_20d") * decay)
        )
        .otherwise(null_float)
        .alias("utility"),
        pl.when(finite_exec_return)
        .then(pl.col("exec_return").cast(pl.Float64))
        .otherwise(null_float)
        .alias("exec_return"),
        pl.when(observable)
        .then(pl.col("peak_day").cast(pl.Float64))
        .otherwise(null_float)
        .alias("peak_day"),
    )


def feature_columns(
    frame: pl.DataFrame,
    *,
    declared_features: Sequence[str] | None = None,
) -> list[str]:
    """Return contract-approved features and reject label-like names."""
    actual = sorted(
        column
        for column in frame.columns
        if column.startswith("feature__")
    )
    leaked = [
        column
        for column in actual
        if (
            column.removeprefix("feature__") in _FORBIDDEN_FEATURE_TARGETS
            or any(
                fragment
                in column.removeprefix("feature__").lower()
                for fragment in _LABEL_LIKE_FRAGMENTS
            )
        )
    ]
    if leaked:
        raise ValueError(
            f"target leakage in feature columns: {leaked}"
        )
    if declared_features is None:
        features = [
            column
            for column in actual
            if (
                column.removeprefix("feature__") in _M2A_STRUCTURAL_FEATURES
                or column.removeprefix("feature__").startswith("factor__")
            )
        ]
        unknown = sorted(set(actual) - set(features))
        if unknown:
            raise ValueError(
                f"feature columns are not declared by the M2A contract: "
                f"{unknown}"
            )
    else:
        declared = sorted(set(declared_features))
        missing = sorted(set(declared) - set(actual))
        extras = sorted(set(actual) - set(declared))
        if missing:
            raise ValueError(
                f"feature contract declares missing columns: {missing}"
            )
        if extras:
            raise ValueError(
                f"decision features are missing from the contract: {extras}"
            )
        features = declared
    return features


class ConstantModel:
    """Small explicit fallback for sparse or single-valued targets."""

    def __init__(
        self,
        kind: TargetKind,
        constant: float = 0.0,
    ) -> None:
        self.kind = kind
        self.constant = float(constant)

    def predict(self, values: np.ndarray) -> np.ndarray:
        return np.full(values.shape[0], self.constant, dtype=float)

    def predict_proba(self, values: np.ndarray) -> np.ndarray:
        probability = np.clip(self.constant, 0.0, 1.0)
        return np.column_stack(
            [
                np.full(values.shape[0], 1.0 - probability),
                np.full(values.shape[0], probability),
            ]
        )


def constant_fallback(target: TargetSpec | str) -> ConstantModel:
    spec = TARGET_SPECS[target] if isinstance(target, str) else target
    return ConstantModel(spec.kind)


@dataclass
class ModelBundle:
    config: ModelConfig
    feature_names: tuple[str, ...]
    models: dict[str, Any] = field(default_factory=dict)
    statuses: dict[str, str] = field(default_factory=dict)
    training_rows: dict[str, int] = field(default_factory=dict)
    training_events: dict[str, int] = field(default_factory=dict)
    calibrators: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CalibrationChoice:
    target: str
    method: Literal["raw", "isotonic"]
    raw_brier: float | None
    calibrated_brier: float | None
    sample_count: int
    event_count: int
    fit_sample_count: int
    fit_event_count: int


def _role_filtered(frame: pl.DataFrame) -> pl.DataFrame:
    if "role" not in frame.columns:
        return frame
    filtered = frame.filter(pl.col("role") == "train")
    if filtered.is_empty():
        raise ValueError("model fitting requires role=train rows")
    return filtered


def _feature_matrix(
    frame: pl.DataFrame,
    feature_names: Sequence[str],
) -> np.ndarray:
    missing = sorted(set(feature_names) - set(frame.columns))
    if missing:
        raise ValueError(f"missing feature columns: {missing}")
    available = set(feature_columns(frame))
    invalid = sorted(set(feature_names) - available)
    if invalid:
        raise ValueError(f"non-feature model inputs: {invalid}")
    if not feature_names:
        raise ValueError("at least one feature__* column is required")
    for column in feature_names:
        if not frame.schema[column].is_numeric():
            raise ValueError(f"feature column is not numeric: {column}")
    try:
        return frame.select(feature_names).cast(pl.Float64).to_numpy()
    except (pl.exceptions.ComputeError, pl.exceptions.InvalidOperationError) as exc:
        raise ValueError("feature columns must contain numeric values") from exc


def _eligible_mask(
    frame: pl.DataFrame,
    target: str,
) -> pl.Expr:
    spec = TARGET_SPECS[target]
    value = pl.col(target)
    if spec.eligibility == "all":
        return pl.col("market_fillable").is_not_null()
    base = (
        pl.col("market_fillable").fill_null(False)
        & pl.col("label_observable").fill_null(False)
    )
    if target == "exec_return":
        return (
            base
            & value.is_not_null()
            & value.is_finite()
        )
    return base & value.is_not_null() & value.is_finite()


def _sample_weight(
    frame: pl.DataFrame,
) -> np.ndarray | None:
    if "sample_weight" not in frame.columns:
        return None
    if frame["sample_weight"].null_count():
        raise ValueError("sample_weight contains nulls")
    values = frame["sample_weight"].cast(pl.Float64).to_numpy()
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("sample_weight must be finite and non-negative")
    if values.sum() <= 0:
        raise ValueError("sample_weight sum must be positive")
    return values


def _require_hist_gradient_boosting():
    try:
        from sklearn.ensemble import (
            HistGradientBoostingClassifier,
            HistGradientBoostingRegressor,
        )
    except ImportError as exc:
        raise RuntimeError(
            "scikit-learn is required for first-board model studies; "
            "install with `uv sync --extra research-model`"
        ) from exc
    return (
        HistGradientBoostingClassifier,
        HistGradientBoostingRegressor,
    )


def fit_model_bundle(
    frame: pl.DataFrame,
    config: ModelConfig | None = None,
    feature_names: Sequence[str] | None = None,
) -> ModelBundle:
    """Fit one estimator per target, with explicit sparse-data fallbacks."""
    config = config or ModelConfig()
    work = _role_filtered(frame)
    if not set(TARGET_SPECS).issubset(work.columns):
        work = prepare_model_frame(work)
    names = tuple(feature_names or feature_columns(work))
    matrix = _feature_matrix(work, names)
    weights = _sample_weight(work)
    classifier_cls, regressor_cls = _require_hist_gradient_boosting()

    bundle = ModelBundle(config=config, feature_names=names)
    indexed = work.with_row_index("_row")
    for target, spec in TARGET_SPECS.items():
        eligible = indexed.filter(_eligible_mask(indexed, target))
        count = eligible.height
        bundle.training_rows[target] = count
        event_count = eligible["event_id"].n_unique()
        bundle.training_events[target] = event_count
        if count == 0:
            bundle.models[target] = constant_fallback(spec)
            bundle.statuses[target] = "constant_no_samples"
            continue

        indices = eligible["_row"].to_numpy()
        target_values = (
            work[target].gather(indices).cast(pl.Float64).to_numpy()
        )
        finite = np.isfinite(target_values)
        if not finite.all():
            raise ValueError(f"target {target} contains non-finite values")
        unique = np.unique(target_values)
        constant_value = float(target_values.mean())
        if event_count < config.min_training_samples:
            bundle.models[target] = ConstantModel(
                spec.kind,
                constant_value,
            )
            bundle.statuses[target] = "constant_insufficient_samples"
            continue
        if unique.size <= 1:
            bundle.models[target] = ConstantModel(
                spec.kind,
                constant_value,
            )
            bundle.statuses[target] = "constant_single_class"
            continue
        if spec.kind == "binary" and not set(unique).issubset({0.0, 1.0}):
            raise ValueError(f"binary target {target} must be 0/1")

        target_weights = weights[indices] if weights is not None else None
        if spec.kind == "binary":
            model = classifier_cls(
                max_iter=config.max_iter,
                learning_rate=config.learning_rate,
                max_leaf_nodes=config.max_leaf_nodes,
                early_stopping=False,
                random_state=config.random_state,
            )
            model.fit(
                matrix[indices],
                target_values.astype(int),
                sample_weight=target_weights,
            )
        else:
            model = regressor_cls(
                max_iter=config.max_iter,
                learning_rate=config.learning_rate,
                max_leaf_nodes=config.max_leaf_nodes,
                early_stopping=False,
                random_state=config.random_state,
            )
            model.fit(
                matrix[indices],
                target_values,
                sample_weight=target_weights,
            )
        bundle.models[target] = model
        bundle.statuses[target] = "hist_gradient_boosting"
    return bundle


def _raw_probability(
    bundle: ModelBundle,
    target: str,
    matrix: np.ndarray,
) -> np.ndarray:
    model = bundle.models[target]
    if TARGET_SPECS[target].kind == "binary":
        values = model.predict_proba(matrix)[:, 1]
    else:
        values = model.predict(matrix)
    return np.clip(np.asarray(values, dtype=float), 0.0, 1.0)


def _raw_prediction(
    bundle: ModelBundle,
    target: str,
    matrix: np.ndarray,
) -> np.ndarray:
    if TARGET_SPECS[target].kind == "binary":
        return _raw_probability(bundle, target, matrix)
    return np.asarray(bundle.models[target].predict(matrix), dtype=float)


def predict_model_bundle(
    frame: pl.DataFrame,
    bundle: ModelBundle,
) -> pl.DataFrame:
    """Predict in input row order and keep identifier columns for joins."""
    matrix = _feature_matrix(frame, bundle.feature_names)
    probabilities: dict[str, np.ndarray] = {}
    for target in PROBABILITY_TARGETS:
        values = _raw_probability(bundle, target, matrix)
        calibrator = bundle.calibrators.get(target)
        if calibrator is not None:
            values = np.clip(
                np.asarray(calibrator.predict(values), dtype=float),
                0.0,
                1.0,
            )
        probabilities[target] = values

    utility = _raw_prediction(bundle, "utility", matrix)
    exec_return = _raw_prediction(bundle, "exec_return", matrix)
    peak_day = _raw_prediction(bundle, "peak_day", matrix)
    score = probabilities["market_fillable"] * utility
    payload = {
        **{
            column: frame[column]
            for column in KEY_COLUMNS
            if column in frame.columns
        },
        "prob_market_fillable": probabilities["market_fillable"],
        "prob_stop_first": probabilities["stop_first"],
        "prob_fast_strong": probabilities["fast_strong"],
        "prob_mfe_touch_30": probabilities["mfe_touch_30"],
        "prob_mfe_exec_30": probabilities["mfe_exec_30"],
        "expected_utility": utility,
        "expected_exec_return": exec_return,
        "expected_peak_day": peak_day,
        "score": score,
    }
    return pl.DataFrame(payload)


def brier_score(
    actual: Sequence[float] | np.ndarray,
    probability: Sequence[float] | np.ndarray,
    sample_weight: Sequence[float] | np.ndarray | None = None,
) -> float:
    labels = np.asarray(actual, dtype=float)
    values = np.asarray(probability, dtype=float)
    if labels.shape != values.shape:
        raise ValueError("actual and probability must have the same shape")
    if sample_weight is None:
        weights = np.ones(labels.shape, dtype=float)
    else:
        weights = np.asarray(sample_weight, dtype=float)
        if weights.shape != labels.shape:
            raise ValueError("sample_weight must match actual shape")
    valid = (
        np.isfinite(labels)
        & np.isfinite(values)
        & np.isfinite(weights)
        & (weights >= 0)
    )
    if not valid.any():
        raise ValueError("no finite calibration values")
    valid_weights = weights[valid]
    if valid_weights.sum() <= 0:
        raise ValueError("sample_weight sum must be positive")
    return float(
        np.average(
            (
                np.clip(values[valid], 0.0, 1.0)
                - labels[valid]
            )
            ** 2,
            weights=valid_weights,
        )
    )


def _date_split(
    frame: pl.DataFrame,
    fraction: float,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    dates = frame["decision_date"].unique().sort().to_list()
    if len(dates) < 2:
        return frame, frame.clear()
    if "event_id" not in frame.columns:
        raise ValueError("event-atomic calibration requires event_id")
    fit_count = math.floor(len(dates) * (1.0 - fraction))
    fit_count = min(max(fit_count, 1), len(dates) - 1)
    calibration_start = dates[fit_count]
    event_starts = frame.group_by("event_id").agg(
        pl.col("decision_date").min().alias("_first_decision_date")
    )
    calibration_events = event_starts.filter(
        pl.col("_first_decision_date") >= calibration_start
    ).select("event_id")
    calibration_frame = frame.join(
        calibration_events,
        on="event_id",
        how="semi",
    )
    fit_frame = frame.join(
        calibration_events,
        on="event_id",
        how="anti",
    )
    return fit_frame, calibration_frame


def fit_calibrated_bundle(
    frame: pl.DataFrame,
    config: ModelConfig | None = None,
) -> tuple[ModelBundle, dict[str, CalibrationChoice]]:
    """Choose calibration on the late portion of the training period only."""
    config = config or ModelConfig()
    work = _role_filtered(frame)
    if not set(TARGET_SPECS).issubset(work.columns):
        work = prepare_model_frame(work)
    names = tuple(feature_columns(work))
    fit_frame, calibration_frame = _date_split(
        work,
        config.calibration_fraction,
    )
    if calibration_frame.is_empty():
        final_bundle = fit_model_bundle(work, config, names)
        choices = {
            target: CalibrationChoice(
                target=target,
                method="raw",
                raw_brier=None,
                calibrated_brier=None,
                sample_count=0,
                event_count=0,
                fit_sample_count=fit_frame.height,
                fit_event_count=fit_frame["event_id"].n_unique(),
            )
            for target in PROBABILITY_TARGETS
        }
        return final_bundle, choices

    try:
        from sklearn.isotonic import IsotonicRegression
    except ImportError as exc:
        raise RuntimeError(
            "scikit-learn is required for first-board model studies; "
            "install with `uv sync --extra research-model`"
        ) from exc

    base_bundle = fit_model_bundle(fit_frame, config, names)
    calibration_matrix = _feature_matrix(calibration_frame, names)
    calibration_weights = _sample_weight(calibration_frame)
    choices: dict[str, CalibrationChoice] = {}
    calibrators: dict[str, Any] = {}
    indexed_calibration = calibration_frame.with_row_index("_row")
    for target in PROBABILITY_TARGETS:
        eligible = indexed_calibration.filter(
            _eligible_mask(indexed_calibration, target)
        )
        positions = eligible["_row"].to_numpy()
        if positions.size == 0:
            choices[target] = CalibrationChoice(
                target=target,
                method="raw",
                raw_brier=None,
                calibrated_brier=None,
                sample_count=0,
                event_count=0,
                fit_sample_count=fit_frame.height,
                fit_event_count=fit_frame["event_id"].n_unique(),
            )
            continue
        actual = (
            calibration_frame[target]
            .gather(positions)
            .cast(pl.Float64)
            .to_numpy()
        )
        raw = _raw_probability(
            base_bundle,
            target,
            calibration_matrix[positions],
        )
        weights = (
            calibration_weights[positions]
            if calibration_weights is not None
            else None
        )
        raw_brier = (
            brier_score(actual, raw, weights)
            if actual.size
            else None
        )
        event_count = eligible["event_id"].n_unique()
        method: Literal["raw", "isotonic"] = "raw"
        calibrated_brier = raw_brier
        calibrator = None
        if (
            event_count >= config.min_calibration_samples
            and np.unique(actual).size > 1
        ):
            candidate = IsotonicRegression(out_of_bounds="clip")
            candidate.fit(raw, actual, sample_weight=weights)
            calibrated = np.clip(candidate.predict(raw), 0.0, 1.0)
            calibrated_brier = brier_score(actual, calibrated, weights)
            if (
                raw_brier is not None
                and calibrated_brier < raw_brier - 1e-12
            ):
                method = "isotonic"
                calibrator = candidate
        choices[target] = CalibrationChoice(
            target=target,
            method=method,
            raw_brier=raw_brier,
            calibrated_brier=calibrated_brier,
            sample_count=int(actual.size),
            event_count=int(event_count),
            fit_sample_count=fit_frame.height,
            fit_event_count=fit_frame["event_id"].n_unique(),
        )
        if calibrator is not None:
            calibrators[target] = calibrator

    final_bundle = fit_model_bundle(work, config, names)
    final_bundle.calibrators = calibrators
    return final_bundle, choices
