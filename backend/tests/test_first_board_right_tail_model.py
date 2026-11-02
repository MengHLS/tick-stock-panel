from __future__ import annotations

from datetime import date, datetime, time, timedelta
from math import exp

import numpy as np
import polars as pl
import pytest

pytest.importorskip("sklearn")

import scripts.first_board_right_tail_lab as lab
from scripts.first_board_right_tail_lab import model as model_module
from scripts.first_board_right_tail_lab.model import (
    TARGET_SPECS,
    ModelConfig,
    brier_score,
    feature_columns,
    fit_calibrated_bundle,
    fit_model_bundle,
    predict_model_bundle,
    prepare_model_frame,
)


def _row(
    index: int,
    *,
    market_fillable: bool = True,
    label_observable: bool = True,
    stop_first: bool | None = False,
    mfe_touch: float | None = 0.2,
    mfe_exec: float | None = 0.18,
    peak_day: int | None = 10,
    exec_return: float | None = 0.02,
    role: str = "train",
) -> dict:
    day = date(2025, 1, 1) + timedelta(days=index)
    signal_time = datetime.combine(day, time(10, 0))
    return {
        "decision_id": f"decision-{index:03d}",
        "event_id": f"event-{index // 2:03d}",
        "candidate_id": f"candidate-{index:03d}",
        "symbol": "000001.SZ",
        "decision_date": day,
        "decision_time": signal_time,
        "trigger_rule": "A",
        "trigger_bar_end": signal_time,
        "signal_available_time": signal_time,
        "days_waited": 1,
        "market_fillable": market_fillable,
        "label_observable": label_observable,
        "entry_exec_adj": 10.0 if market_fillable else None,
        "mfe_touch_20d": mfe_touch,
        "mae_touch_20d": -0.05,
        "peak_day": peak_day,
        "stop_first": stop_first,
        "ordering_ambiguous": False,
        "mfe_exec_20d": mfe_exec,
        "mae_exec_20d": -0.04,
        "exec_return": exec_return,
        "exit_status": "closed",
        "label_maturity_time": (
            datetime.combine(day + timedelta(days=30), time(15, 0))
        ),
        "role": role,
        "sample_weight": 1.0,
        "feature__price_vs_t_high": float(index % 7) / 100.0,
        "feature__volume_ratio_20": 1.0 + float(index % 5),
        "feature__factor__roe": (
            None if index % 11 == 0 else float(index % 13) / 100.0
        ),
    }


def _training_frame(count: int = 40) -> pl.DataFrame:
    rows = []
    for index in range(count):
        fillable = index % 5 != 0
        stop_first = fillable and index % 7 == 0
        touch = 0.35 if index % 3 == 0 else 0.12
        rows.append(
            _row(
                index,
                market_fillable=fillable,
                stop_first=stop_first if fillable else None,
                mfe_touch=touch if fillable else None,
                mfe_exec=(0.31 if index % 4 == 0 else 0.11)
                if fillable
                else None,
                peak_day=(6 if index % 2 == 0 else 14) if fillable else None,
                exec_return=(0.03 if index % 3 == 0 else -0.01)
                if fillable
                else None,
            )
        )
    return pl.DataFrame(rows)


def test_feature_columns_never_include_targets_or_label_columns():
    frame = _training_frame(3).with_columns(
        pl.col("stop_first").alias("mfe_touch_30")
    )

    features = feature_columns(frame)

    assert features == [
        "feature__factor__roe",
        "feature__price_vs_t_high",
        "feature__volume_ratio_20",
    ]
    assert "stop_first" not in features
    assert "mfe_touch_20d" not in features


def test_feature_columns_reject_a_target_masquerading_behind_feature_prefix():
    frame = _training_frame(2).with_columns(
        pl.lit(1.0).alias("feature__stop_first")
    )

    with pytest.raises(ValueError, match="target leakage"):
        feature_columns(frame)


@pytest.mark.parametrize(
    "column",
    [
        "feature__future_return",
        "feature__label_observable",
        "feature__mfe_touch_50d",
    ],
)
def test_feature_columns_reject_label_like_prefix_variants(column: str):
    frame = _training_frame(2).with_columns(
        pl.lit(1.0).alias(column)
    )

    with pytest.raises(ValueError, match="target leakage"):
        feature_columns(frame)


def test_feature_columns_accept_v3_decision_time_features():
    frame = pl.DataFrame(
        {
            "feature__opening_gap": [0.01],
            "feature__first5_return_vs_t_close": [0.02],
            "feature__first5_high_vs_t_high": [0.03],
            "feature__first5_low_vs_t_close": [-0.01],
            "feature__first5_range_pct": [0.04],
            "feature__first5_volume_share_t": [0.10],
            "feature__minutes_above_vwap_ratio": [0.80],
            "feature__locked_minute_ratio": [0.00],
            "feature__current_vs_first5_high": [0.01],
            "feature__volume_growth_last5_vs_first5": [1.20],
            "feature__factor__market__up_ratio": [0.60],
        }
    )

    features = feature_columns(frame)

    assert features == sorted(frame.columns)


def test_prepare_model_frame_maps_ordered_labels_and_separates_execution():
    frame = pl.DataFrame(
        [
            _row(
                0,
                stop_first=False,
                mfe_touch=0.35,
                mfe_exec=0.20,
                peak_day=5,
            ),
            _row(
                1,
                stop_first=False,
                mfe_touch=0.35,
                mfe_exec=0.31,
                peak_day=12,
            ),
            _row(
                2,
                stop_first=True,
                mfe_touch=0.50,
                mfe_exec=0.45,
                peak_day=3,
            ),
            _row(
                3,
                market_fillable=False,
                label_observable=False,
                stop_first=None,
                mfe_touch=9.0,
                mfe_exec=9.0,
                peak_day=1,
                exec_return=9.0,
            ),
        ]
    )

    prepared = prepare_model_frame(frame)

    assert set(TARGET_SPECS) == {
        "market_fillable",
        "stop_first",
        "fast_strong",
        "mfe_touch_30",
        "mfe_exec_30",
        "utility",
        "exec_return",
        "peak_day",
    }
    assert prepared["fast_strong"][:3].to_list() == [1, 0, 0]
    assert prepared["mfe_touch_30"][:3].to_list() == [1, 1, 1]
    assert prepared["mfe_exec_30"][:3].to_list() == [0, 1, 1]
    assert prepared["utility"][:3].to_list() == pytest.approx(
        [0.35, 0.35 * exp(-0.7), 0.0]
    )
    for target in TARGET_SPECS:
        if target == "market_fillable":
            assert prepared[target][3] == 0
        else:
            assert prepared[target][3] is None


def test_fit_model_bundle_handles_constant_targets_and_prediction_contract():
    frame = _training_frame(12).with_columns(
        pl.lit(0).alias("fast_strong"),
    )
    config = ModelConfig(max_iter=5)
    features = feature_columns(frame)

    bundle = fit_model_bundle(frame, config, features)
    predicted = predict_model_bundle(frame, bundle)

    assert bundle.statuses["fast_strong"].startswith("constant_")
    assert predicted.height == frame.height
    expected_columns = {
        "prob_market_fillable",
        "prob_stop_first",
        "prob_fast_strong",
        "prob_mfe_touch_30",
        "prob_mfe_exec_30",
        "expected_utility",
        "expected_exec_return",
        "expected_peak_day",
        "score",
    }
    assert expected_columns.issubset(predicted.columns)
    assert predicted["decision_id"].to_list() == frame["decision_id"].to_list()
    for column in (
        "prob_market_fillable",
        "prob_stop_first",
        "prob_fast_strong",
        "prob_mfe_touch_30",
        "prob_mfe_exec_30",
    ):
        assert predicted[column].min() >= 0.0
        assert predicted[column].max() <= 1.0
    assert predicted["score"].to_list() == pytest.approx(
        (
            predicted["prob_market_fillable"]
            * predicted["expected_utility"]
        ).to_list()
    )


def test_training_fallback_uses_events_not_correlated_rows():
    frame = _training_frame(20).with_columns(
        pl.lit("one-event").alias("event_id")
    )

    bundle = fit_model_bundle(
        frame,
        ModelConfig(max_iter=5),
        feature_columns(frame),
    )

    assert bundle.training_rows["market_fillable"] == 20
    assert bundle.training_events["market_fillable"] == 1
    assert bundle.statuses["market_fillable"] == (
        "constant_insufficient_samples"
    )


def test_fit_model_bundle_is_deterministic_and_rejects_missing_features():
    frame = _training_frame(40)
    config = ModelConfig(max_iter=8)
    features = feature_columns(frame)

    first = predict_model_bundle(
        frame,
        fit_model_bundle(frame, config, features),
    )
    second = predict_model_bundle(
        frame,
        fit_model_bundle(frame, config, features),
    )

    assert first.equals(second)
    with pytest.raises(ValueError, match="missing feature columns"):
        fit_model_bundle(frame, config, [*features, "feature__not_present"])


def test_brier_score_clips_invalid_probability_bounds():
    assert brier_score(
        np.array([1, 0, 1]),
        np.array([1.2, -0.2, 0.5]),
    ) == pytest.approx((0.0 + 0.0 + 0.25) / 3.0)


def test_brier_score_honors_event_weights():
    assert brier_score(
        np.array([1.0, 0.0]),
        np.array([0.0, 0.0]),
        np.array([3.0, 1.0]),
    ) == pytest.approx(0.75)


def _dated_training_frame(count: int = 150) -> pl.DataFrame:
    rows = []
    for index in range(count):
        fillable = index % 4 != 0
        rows.append(
            _row(
                index,
                market_fillable=fillable,
                stop_first=(index % 6 == 0) if fillable else None,
                mfe_touch=(0.4 if index % 3 == 0 else 0.15)
                if fillable
                else None,
                mfe_exec=(0.35 if index % 5 == 0 else 0.14)
                if fillable
                else None,
                peak_day=(5 if index % 2 == 0 else 15) if fillable else None,
                exec_return=(0.04 if index % 3 == 0 else -0.02)
                if fillable
                else None,
            )
        )
    return pl.DataFrame(rows).with_columns(
        pl.col("decision_id").alias("event_id")
    )


def test_calibration_uses_only_training_rows_and_records_choice(
    monkeypatch: pytest.MonkeyPatch,
):
    frame = _dated_training_frame()
    outer_rows = [
        _row(
            index,
            stop_first=True,
            mfe_touch=-0.8,
            mfe_exec=-0.8,
            exec_return=-0.5,
            role="validation",
        )
        for index in range(150, 170)
    ]
    with_validation = pl.concat(
        [frame, pl.DataFrame(outer_rows)],
        how="diagonal_relaxed",
    )
    config = ModelConfig(max_iter=5)
    original_brier = model_module.brier_score

    calls = {"count": 0}

    def improving_brier(actual, probability, sample_weight=None):
        calls["count"] += 1
        return 0.2 if calls["count"] % 2 else 0.1

    monkeypatch.setattr(model_module, "brier_score", improving_brier)
    first_bundle, first_choices = fit_calibrated_bundle(frame, config)
    calls["count"] = 0
    validation_bundle, validation_choices = fit_calibrated_bundle(
        with_validation,
        config,
    )
    monkeypatch.setattr(model_module, "brier_score", original_brier)

    assert first_choices["market_fillable"].method == "isotonic"
    assert first_choices["market_fillable"].sample_count >= 20
    assert first_choices["market_fillable"].raw_brier == 0.2
    assert first_choices["market_fillable"].calibrated_brier == 0.1
    assert validation_choices == first_choices
    assert predict_model_bundle(frame, validation_bundle).equals(
        predict_model_bundle(frame, first_bundle)
    )


def test_calibration_keeps_raw_when_improvement_is_not_strict(
    monkeypatch: pytest.MonkeyPatch,
):
    frame = _dated_training_frame()
    config = ModelConfig(max_iter=5)

    monkeypatch.setattr(
        model_module,
        "brier_score",
        lambda actual, probability, sample_weight=None: 0.2,
    )

    _, choices = fit_calibrated_bundle(frame, config)

    assert all(choice.method == "raw" for choice in choices.values())
    assert choices["market_fillable"].sample_count >= 20


def test_calibration_tolerates_target_with_no_eligible_inner_rows():
    dates = _dated_training_frame()["decision_date"].unique().sort()
    calibration_start = dates[-30]
    frame = _dated_training_frame().with_columns(
        pl.when(pl.col("decision_date") >= calibration_start)
        .then(None)
        .otherwise(pl.col("mfe_exec_20d"))
        .alias("mfe_exec_20d"),
        pl.when(pl.col("decision_date") >= calibration_start)
        .then(None)
        .otherwise(pl.col("exec_return"))
        .alias("exec_return"),
    )

    _, choices = fit_calibrated_bundle(frame, ModelConfig(max_iter=5))

    assert choices["mfe_exec_30"].sample_count == 0
    assert choices["mfe_exec_30"].method == "raw"


def test_calibration_split_is_event_atomic_at_the_inner_boundary():
    frame = pl.DataFrame(
        [
            _row(index, role="train")
            for index in range(10)
        ]
    ).with_columns(pl.lit("crossing-event").alias("event_id"))

    _, choices = fit_calibrated_bundle(frame, ModelConfig(max_iter=5))

    assert choices["market_fillable"].sample_count == 0
    assert choices["market_fillable"].event_count == 0


def test_calibration_requires_minimum_unique_events_not_row_count():
    fit_rows = [_row(index) for index in range(80)]
    calibration_rows = [
        {
            **_row(index),
            "event_id": f"calibration-event-{index // 4}",
        }
        for index in range(80, 100)
    ]
    frame = pl.DataFrame([*fit_rows, *calibration_rows])

    _, choices = fit_calibrated_bundle(frame, ModelConfig(max_iter=5))

    market_choice = choices["market_fillable"]
    assert market_choice.sample_count == 20
    assert market_choice.event_count == 5
    assert market_choice.method == "raw"


def test_model_contract_is_exported_without_exporting_sklearn_objects():
    assert lab.ModelConfig is ModelConfig
