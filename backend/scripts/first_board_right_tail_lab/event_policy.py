"""Event-level fill gate and executable-return ranking for first-board studies."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from .model import ConstantModel, brier_score

_T_DAY_FACTOR_PREFIXES = (
    "feature__factor__daily__",
    "feature__factor__linkage__",
    "feature__factor__market__",
)
_OUTCOME_COLUMNS = (
    "label_observable",
    "entry_exec_adj",
    "mfe_touch_20d",
    "mae_touch_20d",
    "peak_day",
    "stop_first",
    "ordering_ambiguous",
    "mfe_exec_20d",
    "mae_exec_20d",
    "exec_return",
    "exit_status",
    "label_maturity_time",
)


@dataclass(frozen=True)
class EventPolicyConfig:
    max_iter: int = 150
    learning_rate: float = 0.05
    max_leaf_nodes: int = 15
    random_state: int = 20261102
    min_samples: int = 50
    calibration_fraction: float = 0.2
    min_calibration_samples: int = 30
    fill_gate_fraction: float = 0.3
    event_budget_fraction: float = 0.1
    max_entries_per_day: int = 2

    def __post_init__(self) -> None:
        if self.max_iter < 1:
            raise ValueError("max_iter must be positive")
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive")
        if self.max_leaf_nodes < 2:
            raise ValueError("max_leaf_nodes must be at least two")
        if self.min_samples < 1:
            raise ValueError("min_samples must be positive")
        if not 0 < self.calibration_fraction < 1:
            raise ValueError("calibration_fraction must be in (0, 1)")
        if self.min_calibration_samples < 1:
            raise ValueError("min_calibration_samples must be positive")
        if not 0 < self.fill_gate_fraction <= 1:
            raise ValueError("fill_gate_fraction must be in (0, 1]")
        if not 0 < self.event_budget_fraction <= 1:
            raise ValueError("event_budget_fraction must be in (0, 1]")
        if self.max_entries_per_day < 1:
            raise ValueError("max_entries_per_day must be positive")


@dataclass(frozen=True)
class EventCalibration:
    method: str
    raw_brier: float | None
    calibrated_brier: float | None
    sample_count: int


@dataclass
class EventPolicyBundle:
    config: EventPolicyConfig
    feature_names: tuple[str, ...]
    fill_model: Any
    return_model: Any
    policy_return_model: Any
    fill_threshold: float
    statuses: dict[str, str] = field(default_factory=dict)
    calibration: EventCalibration | None = None
    fill_calibrator: Any | None = None


def _event_factor_columns(frame: pl.DataFrame) -> list[str]:
    return sorted(
        column
        for column in frame.columns
        if column.startswith(_T_DAY_FACTOR_PREFIXES)
    )


def event_feature_columns(frame: pl.DataFrame) -> list[str]:
    features = [
        column
        for column in _event_factor_columns(frame)
        if not frame.height
        or frame[column].null_count() < frame.height
    ]
    non_numeric = [
        column
        for column in features
        if not frame.schema[column].is_numeric()
    ]
    if non_numeric:
        raise ValueError(
            f"event factor columns must be numeric: {non_numeric}"
        )
    return features


def _validate_event_factors(
    decisions: pl.DataFrame,
    factors: Sequence[str],
) -> None:
    if not factors:
        return
    inconsistent = (
        decisions.group_by("event_id")
        .agg(
            [
                pl.col(column).drop_nulls().n_unique().alias(column)
                for column in factors
            ]
        )
        .filter(
            pl.any_horizontal(pl.col(column) > 1 for column in factors)
        )
    )
    if inconsistent.height:
        names = [
            column
            for column in factors
            if inconsistent[column].max() > 1
        ]
        raise ValueError(
            f"event factors are not constant within event: {names}"
        )


def _first_filled_row(group: pl.DataFrame) -> dict[str, Any] | None:
    filled = group.filter(pl.col("market_fillable").fill_null(False))
    if filled.is_empty():
        return None
    return filled.sort(
        ["signal_available_time", "decision_id"]
    ).row(0, named=True)


def build_event_samples(decisions: pl.DataFrame) -> pl.DataFrame:
    required = {
        "decision_id",
        "event_id",
        "symbol",
        "decision_date",
        "signal_available_time",
        "trigger_rule",
        "market_fillable",
        "label_observable",
        "mfe_touch_20d",
        "mae_touch_20d",
        "peak_day",
        "stop_first",
        "label_maturity_time",
        "exec_return",
    }
    missing = required - set(decisions.columns)
    if missing:
        raise ValueError(
            f"decisions missing event-policy columns: {sorted(missing)}"
        )
    if decisions.is_empty():
        raise ValueError("decisions must not be empty")
    factors = event_feature_columns(decisions)
    _validate_event_factors(decisions, factors)
    rows: list[dict[str, Any]] = []
    for group in decisions.sort(
        ["event_id", "signal_available_time", "decision_id"]
    ).partition_by("event_id", maintain_order=True):
        first = group.row(0, named=True)
        filled = _first_filled_row(group)
        fillable = filled is not None
        observable = bool(
            fillable
            and filled["label_observable"]
            and filled["exec_return"] is not None
        )
        exec_return = (
            float(filled["exec_return"]) if observable else None
        )
        row: dict[str, Any] = {
            "decision_id": first["event_id"],
            "event_id": first["event_id"],
            "symbol": first["symbol"],
            "decision_date": group["decision_date"].min(),
            "signal_available_time": group[
                "signal_available_time"
            ].min(),
            "market_fillable": fillable,
            "decision_count": group.height,
            "fill_decision_id": (
                filled["decision_id"] if filled is not None else None
            ),
            "trigger_rule": (
                filled["trigger_rule"] if filled is not None else None
            ),
            "sample_weight": 1.0,
            "exec_return": exec_return,
            "policy_net_return": (
                exec_return if fillable else 0.0
            ),
        }
        for column in _OUTCOME_COLUMNS:
            row[column] = (
                filled[column]
                if filled is not None and column in filled
                else None
            )
        row["label_observable"] = observable
        for factor in factors:
            values = group[factor].drop_nulls()
            row[factor] = values[0] if values.len() else None
        rows.append(row)
    return pl.DataFrame(rows).sort("event_id")


def _require_sklearn():
    try:
        from sklearn.ensemble import (
            HistGradientBoostingClassifier,
            HistGradientBoostingRegressor,
        )
    except ImportError as exc:
        raise RuntimeError(
            "scikit-learn is required for event-policy studies; "
            "install with `uv sync --extra research-model`"
        ) from exc
    return (
        HistGradientBoostingClassifier,
        HistGradientBoostingRegressor,
    )


def _role_filtered(frame: pl.DataFrame) -> pl.DataFrame:
    if "role" not in frame.columns:
        return frame
    train = frame.filter(pl.col("role") == "train")
    if train.is_empty():
        raise ValueError("event-policy fitting requires role=train rows")
    return train


def _feature_matrix(
    frame: pl.DataFrame,
    features: Sequence[str],
) -> np.ndarray:
    missing = sorted(set(features) - set(frame.columns))
    if missing:
        raise ValueError(f"missing event features: {missing}")
    return frame.select(features).cast(pl.Float64).to_numpy()


def _constant_regressor(value: float) -> ConstantModel:
    return ConstantModel("regression", value)


def _date_split(
    frame: pl.DataFrame,
    fraction: float,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    dates = frame["decision_date"].unique().sort().to_list()
    if len(dates) < 2:
        return frame, frame.clear()
    fit_count = math.floor(len(dates) * (1.0 - fraction))
    fit_count = min(max(fit_count, 1), len(dates) - 1)
    calibration_start = dates[fit_count]
    calibration = frame.filter(
        pl.col("decision_date") >= calibration_start
    )
    fit = frame.filter(
        pl.col("decision_date") < calibration_start
    )
    return fit, calibration


def _fill_probability(model: Any, matrix: np.ndarray) -> np.ndarray:
    return np.clip(
        np.asarray(model.predict_proba(matrix)[:, 1], dtype=float),
        0.0,
        1.0,
    )


def _return_prediction(model: Any, matrix: np.ndarray) -> np.ndarray:
    return np.asarray(model.predict(matrix), dtype=float)


def _fit_fill_model(
    frame: pl.DataFrame,
    matrix: np.ndarray,
    config: EventPolicyConfig,
) -> tuple[Any, EventCalibration, Any | None]:
    classifier_cls, _ = _require_sklearn()
    labels = frame["market_fillable"].cast(pl.Int8).to_numpy()
    unique = np.unique(labels)
    if frame.height < config.min_samples or unique.size <= 1:
        model = ConstantModel("binary", float(labels.mean()))
        return (
            model,
            EventCalibration(
                method="raw",
                raw_brier=None,
                calibrated_brier=None,
                sample_count=0,
            ),
            None,
        )

    fit_frame, calibration_frame = _date_split(
        frame,
        config.calibration_fraction,
    )
    if calibration_frame.is_empty():
        model = classifier_cls(
            max_iter=config.max_iter,
            learning_rate=config.learning_rate,
            max_leaf_nodes=config.max_leaf_nodes,
            early_stopping=False,
            random_state=config.random_state,
        )
        model.fit(matrix, labels)
        return (
            model,
            EventCalibration(
                method="raw",
                raw_brier=None,
                calibrated_brier=None,
                sample_count=0,
            ),
            None,
        )

    fit_mask = frame["decision_date"].is_in(
        fit_frame["decision_date"].unique().to_list()
    ).to_numpy()
    calibration_mask = ~fit_mask
    base = classifier_cls(
        max_iter=config.max_iter,
        learning_rate=config.learning_rate,
        max_leaf_nodes=config.max_leaf_nodes,
        early_stopping=False,
        random_state=config.random_state,
    )
    fit_labels = labels[fit_mask]
    if np.unique(fit_labels).size <= 1:
        base = ConstantModel("binary", float(fit_labels.mean()))
    else:
        base.fit(matrix[fit_mask], fit_labels)
    actual = labels[calibration_mask]
    raw = _fill_probability(base, matrix[calibration_mask])
    raw_brier = brier_score(actual, raw)
    method = "raw"
    calibrated_brier = raw_brier
    calibrator = None
    if (
        calibration_frame.height >= config.min_calibration_samples
        and np.unique(actual).size > 1
    ):
        from sklearn.isotonic import IsotonicRegression

        candidate = IsotonicRegression(out_of_bounds="clip")
        candidate.fit(raw, actual)
        calibrated = np.clip(candidate.predict(raw), 0.0, 1.0)
        candidate_brier = brier_score(actual, calibrated)
        if candidate_brier < raw_brier - 1e-12:
            method = "isotonic"
            calibrated_brier = candidate_brier
            calibrator = candidate

    final_model = classifier_cls(
        max_iter=config.max_iter,
        learning_rate=config.learning_rate,
        max_leaf_nodes=config.max_leaf_nodes,
        early_stopping=False,
        random_state=config.random_state,
    )
    final_model.fit(matrix, labels)
    return (
        final_model,
        EventCalibration(
            method=method,
            raw_brier=raw_brier,
            calibrated_brier=calibrated_brier,
            sample_count=calibration_frame.height,
        ),
        calibrator,
    )


def _fit_return_model(
    frame: pl.DataFrame,
    matrix: np.ndarray,
    target: str,
    config: EventPolicyConfig,
) -> tuple[Any, str]:
    _, regressor_cls = _require_sklearn()
    values = frame[target].cast(pl.Float64)
    eligible = (
        values.is_not_null()
        & values.is_finite()
    ).to_numpy()
    targets = values.filter(eligible).to_numpy()
    if targets.size < config.min_samples or np.unique(targets).size <= 1:
        constant = float(targets.mean()) if targets.size else 0.0
        return _constant_regressor(constant), "constant"
    model = regressor_cls(
        max_iter=config.max_iter,
        learning_rate=config.learning_rate,
        max_leaf_nodes=config.max_leaf_nodes,
        early_stopping=False,
        random_state=config.random_state,
    )
    model.fit(matrix[eligible], targets)
    return model, "hist_gradient_boosting"


def fit_event_policy(
    frame: pl.DataFrame,
    config: EventPolicyConfig | None = None,
) -> EventPolicyBundle:
    config = config or EventPolicyConfig()
    train = _role_filtered(frame)
    features = event_feature_columns(train)
    if not features:
        raise ValueError("at least one T-day event factor is required")
    matrix = _feature_matrix(train, features)
    fill_model, calibration, calibrator = _fit_fill_model(
        train,
        matrix,
        config,
    )
    raw_fill = _fill_probability(fill_model, matrix)
    fill_probability = (
        np.clip(calibrator.predict(raw_fill), 0.0, 1.0)
        if calibrator is not None
        else raw_fill
    )
    fill_threshold = float(
        np.quantile(
            fill_probability,
            1.0 - config.fill_gate_fraction,
            method="linear",
        )
    )
    return_model, return_status = _fit_return_model(
        train,
        matrix,
        "exec_return",
        config,
    )
    policy_model, policy_status = _fit_return_model(
        train,
        matrix,
        "policy_net_return",
        config,
    )
    return EventPolicyBundle(
        config=config,
        feature_names=tuple(features),
        fill_model=fill_model,
        return_model=return_model,
        policy_return_model=policy_model,
        fill_threshold=fill_threshold,
        statuses={
            "fill": (
                "constant"
                if isinstance(fill_model, ConstantModel)
                else "hist_gradient_boosting"
            ),
            "return": return_status,
            "policy_return": policy_status,
        },
        calibration=calibration,
        fill_calibrator=calibrator,
    )


def predict_event_policy(
    frame: pl.DataFrame,
    bundle: EventPolicyBundle,
) -> pl.DataFrame:
    matrix = _feature_matrix(frame, bundle.feature_names)
    raw_fill = _fill_probability(bundle.fill_model, matrix)
    probability = (
        np.clip(
            bundle.fill_calibrator.predict(raw_fill),
            0.0,
            1.0,
        )
        if bundle.fill_calibrator is not None
        else raw_fill
    )
    return_if_fill = _return_prediction(bundle.return_model, matrix)
    policy_net = _return_prediction(bundle.policy_return_model, matrix)
    payload: dict[str, Any] = {
        "event_id": frame["event_id"],
        "decision_date": frame["decision_date"],
        "signal_available_time": frame["signal_available_time"],
        "prob_fill": probability,
        "expected_return_if_fill": return_if_fill,
        "expected_net_return": policy_net,
        "rank_score": policy_net,
    }
    for column in ("decision_id", "symbol", "fold", "role"):
        if column in frame.columns:
            payload[column] = frame[column]
    return pl.DataFrame(payload)


def select_event_candidates(
    predictions: pl.DataFrame,
    *,
    fill_threshold: float,
    event_fraction: float,
    max_per_day: int,
) -> pl.DataFrame:
    if not 0 < event_fraction <= 1:
        raise ValueError("event_fraction must be in (0, 1]")
    if max_per_day < 1:
        raise ValueError("max_per_day must be positive")
    required = {
        "fold",
        "event_id",
        "decision_date",
        "signal_available_time",
        "prob_fill",
        "expected_return_if_fill",
        "expected_net_return",
        "rank_score",
    }
    missing = required - set(predictions.columns)
    if missing:
        raise ValueError(
            f"predictions missing required columns: {sorted(missing)}"
        )
    gated = predictions.filter(
        (pl.col("prob_fill") >= fill_threshold)
        & pl.col("rank_score").is_not_null()
        & pl.col("rank_score").is_finite()
    )
    if gated.is_empty():
        return gated.with_columns(
            pl.lit(None, dtype=pl.UInt32).alias("selected_rank")
        )
    daily = (
        gated.sort(
            [
                "fold",
                "decision_date",
                "rank_score",
                "expected_net_return",
                "signal_available_time",
                "event_id",
            ],
            descending=[False, False, True, True, False, False],
        )
        .with_columns(
            pl.int_range(pl.len())
            .over(["fold", "decision_date"])
            .add(1)
            .alias("_daily_rank")
        )
        .filter(pl.col("_daily_rank") <= max_per_day)
    )
    budget = (
        pl.len().over("fold").cast(pl.Float64)
        * event_fraction
    ).ceil().cast(pl.Int64)
    selected = (
        daily.sort(
            [
                "fold",
                "rank_score",
                "expected_net_return",
                "signal_available_time",
                "event_id",
            ],
            descending=[False, True, True, False, False],
        )
        .with_columns(
            pl.int_range(pl.len()).over("fold").alias("_event_rank")
        )
        .filter(pl.col("_event_rank") < budget)
        .drop("_event_rank")
    )
    selected = selected.with_columns(
        pl.col("_daily_rank").cast(pl.UInt32).alias("selected_rank")
    ).drop("_daily_rank")
    return selected.sort(
        ["decision_date", "selected_rank", "event_id"]
    )
