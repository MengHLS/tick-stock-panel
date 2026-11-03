from __future__ import annotations

from datetime import date, datetime, time, timedelta

import polars as pl
import pytest

import scripts.first_board_right_tail_lab as lab
from scripts.first_board_right_tail_lab.event_policy import (
    EventPolicyConfig,
    build_event_samples,
    event_feature_columns,
    fit_event_policy,
    predict_event_policy,
    select_event_candidates,
)


def _decision(
    event_index: int,
    *,
    fillable: bool,
    minute: int = 35,
    factor_return: float | None = 0.02,
) -> dict:
    event_day = date(2022, 1, 3) + timedelta(days=event_index * 2)
    decision_day = event_day + timedelta(days=1)
    signal = datetime.combine(decision_day, time(9, minute))
    return {
        "decision_id": f"event-{event_index}:{minute}",
        "event_id": f"event-{event_index}",
        "symbol": f"{event_index:06d}.SZ",
        "decision_date": decision_day,
        "signal_available_time": signal,
        "trigger_rule": "A" if minute < 60 else "B",
        "market_fillable": fillable,
        "label_observable": fillable,
        "mfe_touch_20d": 0.20 if fillable else None,
        "mae_touch_20d": -0.08 if fillable else None,
        "peak_day": 5.0 if fillable else None,
        "stop_first": False if fillable else None,
        "exec_return": 0.03 if fillable else None,
        "exit_status": "closed" if fillable else None,
        "label_maturity_time": (
            datetime.combine(
                decision_day + timedelta(days=30),
                time(15, 0),
            )
            if fillable
            else None
        ),
        "feature__factor__daily__ret_1d": factor_return,
        "feature__factor__linkage__deviate_3d": 0.1,
        "feature__price_vs_t_high": 0.05,
    }


def test_build_event_samples_uses_first_fill_and_zero_for_unfilled():
    decisions = pl.DataFrame(
        [
            _decision(0, fillable=False, minute=35),
            _decision(0, fillable=True, minute=45),
            _decision(1, fillable=False, minute=35),
            _decision(1, fillable=False, minute=45),
        ]
    )

    events = build_event_samples(decisions).sort("event_id")

    assert events.height == 2
    first = events.row(0, named=True)
    assert first["event_id"] == "event-0"
    assert first["market_fillable"] is True
    assert first["fill_decision_id"] == "event-0:45"
    assert first["exec_return"] == pytest.approx(0.03)
    assert first["policy_net_return"] == pytest.approx(0.03)
    assert first["decision_id"] == "event-0"
    second = events.row(1, named=True)
    assert second["event_id"] == "event-1"
    assert second["market_fillable"] is False
    assert second["exec_return"] is None
    assert second["policy_net_return"] == 0.0
    assert set(events.columns).issuperset(
        {
            "event_id",
            "decision_id",
            "decision_date",
            "signal_available_time",
            "label_maturity_time",
            "sample_weight",
        }
    )


def test_event_features_only_include_t_day_factor_columns():
    events = build_event_samples(
        pl.DataFrame([_decision(0, fillable=True)])
    )

    features = event_feature_columns(events)

    assert features == [
        "feature__factor__daily__ret_1d",
        "feature__factor__linkage__deviate_3d",
    ]


def test_event_features_reject_non_factor_or_non_numeric_columns():
    events = build_event_samples(
        pl.DataFrame([_decision(0, fillable=True)])
    ).with_columns(
        pl.lit("bad").alias("feature__factor__daily__bad"),
    )

    with pytest.raises(ValueError, match="must be numeric"):
        event_feature_columns(events)


def test_event_features_ignore_all_null_factor_columns():
    events = build_event_samples(
        pl.DataFrame([_decision(0, fillable=True)])
    ).with_columns(
        pl.Series(
            "feature__factor__daily__empty",
            [None],
            dtype=pl.Null,
        )
    )

    assert "feature__factor__daily__empty" not in (
        event_feature_columns(events)
    )


def test_event_builder_rejects_factor_values_that_change_within_event():
    decisions = pl.DataFrame(
        [
            _decision(0, fillable=False, minute=35, factor_return=0.01),
            _decision(0, fillable=True, minute=45, factor_return=0.02),
        ]
    )

    with pytest.raises(
        ValueError,
        match="event factors are not constant",
    ):
        build_event_samples(decisions)


def _training_events(count: int = 60) -> pl.DataFrame:
    rows = []
    for index in range(count):
        fillable = index % 4 != 0
        day = date(2024, 1, 1) + timedelta(days=index)
        rows.append(
            {
                "decision_id": f"event-{index:03d}",
                "event_id": f"event-{index:03d}",
                "decision_date": day,
                "signal_available_time": datetime.combine(
                    day,
                    time(10, 0),
                ),
                "market_fillable": fillable,
                "label_observable": fillable,
                "label_maturity_time": (
                    datetime.combine(
                        day + timedelta(days=30),
                        time(15, 0),
                    )
                    if fillable
                    else None
                ),
                "exec_return": (
                    -0.05 + (index % 7) * 0.015
                    if fillable
                    else None
                ),
                "policy_net_return": (
                    -0.05 + (index % 7) * 0.015
                    if fillable
                    else 0.0
                ),
                "sample_weight": 1.0,
                "role": "train",
                "feature__factor__daily__ret_1d": index % 11 / 100.0,
                "feature__factor__daily__volatility_20": (
                    index % 5 / 10.0
                ),
            }
        )
    return pl.DataFrame(rows)


def test_fit_event_policy_uses_only_train_role_and_is_deterministic():
    train = _training_events()
    validation = (
        _training_events(20)
        .with_columns(
            pl.lit("validation").alias("role"),
            pl.format("validation-{}", pl.col("event_id")).alias(
                "event_id"
            ),
            pl.format(
                "validation-{}",
                pl.col("decision_id"),
            ).alias("decision_id"),
            pl.lit(100.0).alias(
                "feature__factor__daily__ret_1d"
            ),
            pl.lit(0.9).alias("exec_return"),
            pl.lit(0.9).alias("policy_net_return"),
        )
    )
    config = EventPolicyConfig(
        max_iter=8,
        min_samples=10,
        calibration_fraction=0.2,
        fill_gate_fraction=0.3,
    )
    features = event_feature_columns(train)

    first = fit_event_policy(train, config)
    second = fit_event_policy(train, config)
    ignored = fit_event_policy(
        pl.concat([train, validation], how="diagonal_relaxed"),
        config,
    )

    assert first.feature_names == tuple(features)
    assert first.fill_threshold == pytest.approx(
        second.fill_threshold
    )
    assert first.fill_threshold == pytest.approx(
        ignored.fill_threshold
    )
    assert predict_event_policy(train, first).equals(
        predict_event_policy(train, second)
    )


def test_prediction_contract_and_fill_threshold_are_bounded():
    train = _training_events()
    bundle = fit_event_policy(
        train,
        EventPolicyConfig(
            max_iter=8,
            min_samples=10,
            fill_gate_fraction=0.3,
        ),
    )

    predicted = predict_event_policy(train, bundle)

    assert predicted.height == train.height
    assert predicted["prob_fill"].min() >= 0.0
    assert predicted["prob_fill"].max() <= 1.0
    assert predicted["expected_net_return"].is_finite().all()
    assert predicted["expected_return_if_fill"].is_finite().all()
    assert predicted["rank_score"].to_list() == pytest.approx(
        predicted["expected_net_return"].to_list()
    )


def test_select_event_candidates_applies_fill_gate_budget_and_daily_cap():
    rows = []
    returns = [0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02]
    for index, value in enumerate(returns):
        day = date(2025, 1, 1) + timedelta(days=index // 2)
        rows.append(
            {
                "fold": "2025",
                "event_id": f"event-{index}",
                "decision_date": day,
                "signal_available_time": datetime.combine(
                    day,
                    time(10, index % 2),
                ),
                "prob_fill": 0.9 if index != 2 else 0.1,
                "expected_return_if_fill": value,
                "expected_net_return": value * 0.8,
                "rank_score": value,
            }
        )

    selected = select_event_candidates(
        pl.DataFrame(rows),
        fill_threshold=0.5,
        event_fraction=0.6,
        max_per_day=2,
    )

    assert selected.height == 5
    assert "event-2" not in selected["event_id"].to_list()
    assert selected.filter(
        pl.col("decision_date") == date(2025, 1, 1)
    )["event_id"].to_list() == ["event-0", "event-1"]
    assert selected["selected_rank"].to_list() == [1, 2, 1, 1, 2]


def test_invalid_event_policy_config_is_rejected():
    with pytest.raises(ValueError, match="fill_gate_fraction"):
        EventPolicyConfig(fill_gate_fraction=0.0)
    with pytest.raises(ValueError, match="event_budget_fraction"):
        EventPolicyConfig(event_budget_fraction=0.0)
    with pytest.raises(ValueError, match="max_entries_per_day"):
        EventPolicyConfig(max_entries_per_day=0)


def test_event_policy_contract_is_exported():
    assert lab.EventPolicyConfig is EventPolicyConfig
