"""Contracts for the D+5 expected-return model."""

from datetime import date

import numpy as np
import polars as pl
import pytest

from scripts import auction_expected_return_model_study as study


def test_ridge_model_ranks_expected_returns(monkeypatch):
    monkeypatch.setattr(study, "MIN_TRAIN_ROWS", 20)
    values = np.linspace(-3, 3, 200)
    frame = pl.DataFrame({
        "return_feature": values,
        "_target_return": 0.02 * values,
    })
    model = study.fit_ridge(frame, ["return_feature"], alpha=1.0)
    prediction = study.predict_ridge(frame, model)

    assert prediction[-1] > prediction[0]
    assert study.rank_correlation(
        frame["_target_return"].to_numpy(),
        prediction,
    ) > 0.99


def test_rank_correlation_is_one_for_perfect_ranking():
    assert study.rank_correlation(
        np.array([-0.05, 0.01, 0.02, 0.08]),
        np.array([-0.3, -0.1, 0.2, 0.4]),
    ) == pytest.approx(1.0)


def test_prediction_thresholds_keep_declared_tail():
    predictions = np.arange(1, 101, dtype=float)

    thresholds = study.prediction_thresholds(predictions)

    assert thresholds["keep_top_70"] == pytest.approx(30.7)
    assert thresholds["keep_top_50"] == pytest.approx(50.5)
    assert thresholds["keep_top_30"] == pytest.approx(70.3)


def test_downside_base_filters_variant_and_preserves_order(tmp_path):
    panel = pl.DataFrame({
        "symbol": ["600001.SH", "600002.SH", "600003.SH"],
        "date": [date(2024, 1, 2)] * 3,
        "net_return": [0.01, 0.02, 0.03],
    })
    selected_path = tmp_path / "selected.parquet"
    pl.DataFrame({
        "symbol": ["600003.SH", "600001.SH", "600002.SH"],
        "date": [date(2024, 1, 2)] * 3,
        "variant": ["reject_top_50", "baseline", "reject_top_50"],
    }).write_parquet(selected_path)

    base = study.load_downside_base(
        panel,
        selected_path,
        downside_variant="reject_top_50",
    )

    assert base["symbol"].to_list() == ["600003.SH", "600002.SH"]
