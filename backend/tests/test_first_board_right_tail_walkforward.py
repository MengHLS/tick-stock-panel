from __future__ import annotations

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import numpy as np
import polars as pl

import scripts.first_board_right_tail_lab.walkforward as walkforward_module
from scripts.first_board_right_tail_lab import model as model_module
from scripts.first_board_right_tail_lab.model import ModelConfig
from scripts.first_board_right_tail_lab.walkforward import (
    run_model_walkforward,
)


def _sessions(count: int = 120) -> list[date]:
    start = date(2022, 1, 1)
    return [start + timedelta(days=index) for index in range(count)]


def _decision(
    sessions: list[date],
    index: int,
    *,
    event_id: str | None = None,
    rank: float | None = None,
    market_fillable: bool = True,
) -> dict:
    day = sessions[index]
    signal = datetime.combine(day, time(10, 0))
    target_rank = float(index) if rank is None else rank
    return {
        "decision_id": f"decision-{day.isoformat()}-{target_rank}",
        "event_id": event_id or f"event-{index:03d}",
        "candidate_id": f"candidate-{index:03d}",
        "symbol": "000001.SZ",
        "decision_date": day,
        "decision_time": signal,
        "trigger_rule": "A",
        "trigger_bar_end": signal,
        "signal_available_time": signal,
        "days_waited": 1,
        "market_fillable": market_fillable,
        "label_observable": market_fillable,
        "entry_exec_adj": 10.0 if market_fillable else None,
        "mfe_touch_20d": 0.35 if index % 3 == 0 else 0.12,
        "mae_touch_20d": -0.05,
        "peak_day": 5 if index % 2 == 0 else 15,
        "stop_first": index % 7 == 0,
        "ordering_ambiguous": False,
        "mfe_exec_20d": 0.31 if index % 4 == 0 else 0.10,
        "mae_exec_20d": -0.04,
        "exec_return": 0.03 if index % 2 == 0 else -0.01,
        "exit_status": "closed",
        "label_maturity_time": datetime.combine(
            sessions[index + 20],
            time(15, 0),
        ),
        "feature__factor__rank": target_rank,
        "feature__factor__aux": float(index % 5),
    }


def _walkforward_frame() -> tuple[pl.DataFrame, list[date], list[dict]]:
    sessions = _sessions()
    rows = [
        _decision(sessions, index)
        for index in range(10, 50)
    ]
    rows.extend(
        [
            _decision(sessions, 20, event_id="train-duplicate", rank=20.5),
            _decision(sessions, 21, event_id="train-duplicate", rank=21.5),
            _decision(sessions, 80, event_id="validation-duplicate", rank=99.0),
            _decision(sessions, 81, event_id="validation-duplicate", rank=98.0),
        ]
    )
    rows.extend(
        _decision(sessions, index, rank=float(100 + index))
        for index in range(82, 100)
    )
    rows.append(
        _decision(
            sessions,
            82,
            event_id="validation-unfillable",
            rank=1000.0,
            market_fillable=False,
        )
    )
    folds = [
        {
            "name": "fold-1",
            "test_start": sessions[80],
            "test_end": sessions[99],
        }
    ]
    return pl.DataFrame(rows), sessions, folds


def _fake_predictions(frame: pl.DataFrame) -> pl.DataFrame:
    score = frame["feature__factor__rank"].cast(pl.Float64)
    fill_probability = (
        pl.when(pl.col("feature__factor__rank") >= 500)
        .then(0.1)
        .otherwise(0.9)
    )
    return frame.with_columns(
        fill_probability.alias("prob_market_fillable"),
        pl.lit(0.1).alias("prob_stop_first"),
        pl.lit(0.2).alias("prob_fast_strong"),
        pl.lit(0.3).alias("prob_mfe_touch_30"),
        pl.lit(0.25).alias("prob_mfe_exec_30"),
        (score / 0.9).alias("expected_utility"),
        (score / 100.0).alias("expected_exec_return"),
        pl.lit(8.0).alias("expected_peak_day"),
        score.alias("score"),
    ).select(
        "decision_id",
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


def _fake_choice(target: str) -> model_module.CalibrationChoice:
    return model_module.CalibrationChoice(
        target=target,
        method="raw",
        raw_brier=0.2,
        calibrated_brier=0.2,
        sample_count=12,
        event_count=12,
        fit_sample_count=32,
        fit_event_count=32,
    )


def _fake_bundle() -> SimpleNamespace:
    return SimpleNamespace(
        statuses={
            target: "hist_gradient_boosting"
            for target in model_module.TARGET_SPECS
        },
        training_rows={
            target: 32
            for target in model_module.TARGET_SPECS
        },
        training_events={
            target: 32
            for target in model_module.TARGET_SPECS
        },
    )


def test_walkforward_fits_only_training_rows_and_freezes_threshold(
    monkeypatch,
):
    frame, sessions, folds = _walkforward_frame()
    fitted_frames: list[pl.DataFrame] = []

    def fake_fit(training_frame, config):
        fitted_frames.append(training_frame)
        return _fake_bundle(), {
            target: _fake_choice(target)
            for target in model_module.PROBABILITY_TARGETS
        }

    monkeypatch.setattr(
        walkforward_module,
        "fit_calibrated_bundle",
        fake_fit,
    )
    monkeypatch.setattr(
        walkforward_module,
        "predict_model_bundle",
        lambda frame, bundle: _fake_predictions(frame),
    )

    result = run_model_walkforward(
        frame,
        ModelConfig(max_iter=5),
        folds=folds,
        sessions=sessions,
        purge_sessions=30,
    )

    assert len(fitted_frames) == 1
    assert fitted_frames[0]["role"].unique().to_list() == ["train"]
    assert "validation-duplicate" not in set(
        fitted_frames[0]["event_id"].to_list()
    )
    weights = (
        fitted_frames[0]
        .group_by("event_id")
        .agg(pl.col("sample_weight").sum())
    )
    assert weights.filter(
        pl.col("event_id") == "train-duplicate"
    )["sample_weight"][0] == 1.0

    train_scores = fitted_frames[0].filter(
        pl.col("market_fillable")
    )["feature__factor__rank"].to_numpy()
    expected_threshold = float(
        np.quantile(train_scores, 0.9, method="linear")
    )
    assert result.folds["threshold"][0] == expected_threshold
    assert result.predictions["role"].unique().to_list() == ["validation"]
    assert result.predictions["fold"].unique().to_list() == ["fold-1"]
    assert result.predictions["score"].min() >= expected_threshold


def test_walkforward_emits_event_top_decile_and_frozen_threshold_sets(
    monkeypatch,
):
    frame, sessions, folds = _walkforward_frame()
    monkeypatch.setattr(
        walkforward_module,
        "fit_calibrated_bundle",
        lambda frame, config: (
            _fake_bundle(),
            {
                target: _fake_choice(target)
                for target in model_module.PROBABILITY_TARGETS
            },
        ),
    )
    monkeypatch.setattr(
        walkforward_module,
        "predict_model_bundle",
        lambda frame, bundle: _fake_predictions(frame),
    )

    result = run_model_walkforward(
        frame,
        ModelConfig(max_iter=5),
        folds=folds,
        sessions=sessions,
        purge_sessions=30,
    )

    duplicate_rows = result.predictions.filter(
        pl.col("event_id") == "validation-duplicate"
    )
    top = result.top_decisions
    frozen = result.frozen_threshold_decisions
    frozen_duplicate = frozen.filter(
        pl.col("event_id") == "validation-duplicate"
    )
    assert duplicate_rows.height == 2
    assert frozen_duplicate.height == 1
    assert frozen_duplicate["decision_id"][0] == duplicate_rows.sort(
        "signal_available_time"
    )["decision_id"][0]
    validation_events = result.predictions["event_id"].n_unique()
    assert top.height == np.ceil(validation_events * 0.1)
    assert top["event_id"].n_unique() == top.height
    assert frozen["event_id"].n_unique() == frozen.height
    assert "validation-unfillable" not in set(
        frozen["event_id"].to_list()
    )
    assert result.folds["top_events"][0] == top.height
    assert result.folds["frozen_threshold_events"][0] == frozen.height
    assert result.folds["frozen_threshold_actual_fillable_rate"][0] == 1.0
    assert set(result.calibration["target"].to_list()) == set(
        model_module.PROBABILITY_TARGETS
    )
    assert set(result.model_status["target"].to_list()) == set(
        model_module.TARGET_SPECS
    )
