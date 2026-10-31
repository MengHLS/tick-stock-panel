"""Contracts for the D-day downside-probability model."""

from datetime import date

import numpy as np
import polars as pl
import pytest

from scripts import auction_downside_model_study as study


def test_logistic_model_ranks_severe_downside_risk(monkeypatch):
    monkeypatch.setattr(study, "MIN_TRAIN_ROWS", 20)
    values = np.linspace(-3, 3, 200)
    frame = pl.DataFrame({
        "risk_feature": values,
        "_severe_downside": values > 0,
    })
    model = study.fit_logistic(frame, ["risk_feature"], max_iter=30)
    probability = study.predict_logistic(frame, model)

    assert probability[-1] > probability[0]
    assert study.roc_auc(
        frame["_severe_downside"].to_numpy(),
        probability,
    ) > 0.9


def test_roc_auc_is_one_for_perfect_ranking():
    assert study.roc_auc(
        np.array([False, False, True, True]),
        np.array([0.1, 0.2, 0.8, 0.9]),
    ) == pytest.approx(1.0)


def test_feature_columns_include_daily_and_auction_inputs():
    features = study.feature_columns(["momentum_5d"])

    assert "rank__momentum_5d" in features
    assert "auction_rank__last_imbalance" in features
    assert "opening_gap" in features
    assert "sell_expansion" in features


def test_selected_base_preserves_frozen_ranking_order(tmp_path):
    panel = pl.DataFrame({
        "symbol": ["600001.SH", "600002.SH", "600003.SH"],
        "date": [date(2024, 1, 2)] * 3,
        "net_return": [0.01, 0.02, 0.03],
    })
    selected_path = tmp_path / "selected.parquet"
    pl.DataFrame({
        "symbol": ["600003.SH", "600001.SH"],
        "date": [date(2024, 1, 2), date(2024, 1, 2)],
    }).write_parquet(selected_path)

    base = study.load_selected_base(panel, selected_path)

    assert base["symbol"].to_list() == ["600003.SH", "600001.SH"]
