"""Contracts for the D-1 market absolute-return model."""

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from scripts import auction_market_return_model_study as study


def test_market_features_use_only_prior_completed_session():
    start = date(2024, 1, 1)
    closes = [100.0 + index for index in range(80)]
    index = pl.DataFrame({
        "date": [start + timedelta(days=offset) for offset in range(80)],
        "close": closes,
        "volume": [1_000.0 + index for index in range(80)],
        "amount": [10_000.0 + index for index in range(80)],
    })

    features = study.compute_market_features(index)

    assert features["market_ret_1"][-1] == pytest.approx(
        closes[-2] / closes[-3] - 1,
    )
    assert features["market_ret_5"][-1] == pytest.approx(
        closes[-2] / closes[-7] - 1,
    )


def test_market_targets_require_matured_exits_and_group_by_date_gap():
    panel = pl.DataFrame({
        "symbol": ["600001.SH", "600002.SH", "600003.SH"],
        "date": [date(2024, 1, 2), date(2024, 1, 2), date(2024, 1, 3)],
        "gap_bucket": ["2-4", "2-4", "4-6"],
        "entry_reason": ["ok"] * 3,
        "exit_reason": ["ok"] * 3,
        "exit_date": [date(2024, 1, 9), date(2024, 1, 9), date(2024, 1, 10)],
        "net_return": [0.01, 0.03, 0.02],
    })

    targets = study.build_market_targets(
        panel,
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        train_end=date(2024, 1, 9),
    )

    assert targets.height == 1
    assert targets["market_target_return"].item() == pytest.approx(0.02)
    assert targets["market_event_n"].item() == 2


def test_market_ridge_learns_linear_target(monkeypatch):
    monkeypatch.setattr(study, "MIN_TRAIN_ROWS", 20)
    values = np.linspace(-2, 2, 100)
    frame = pl.DataFrame({
        **{feature: values for feature in study.FEATURES},
        "_target_return": 0.01 * values,
    })

    model = study.fit_market_ridge(frame)
    prediction = study.predict_market_ridge(frame, model)

    assert study.rank_correlation(
        frame["_target_return"].to_numpy(),
        prediction,
    ) > 0.99


def test_gate_variants_filter_without_refilling():
    frame = pl.DataFrame({
        "symbol": ["600001.SH", "600002.SH", "600003.SH"],
        "trend_gate": [True, False, True],
        "vol_gate": [True, False, True],
        "market_prediction": [0.01, -0.01, 0.02],
    })

    assert frame.filter(pl.col("trend_gate") & pl.col("vol_gate"))[
        "symbol"
    ].to_list() == ["600001.SH", "600003.SH"]
    assert frame.filter(pl.col("market_prediction") > 0)["symbol"].to_list() == [
        "600001.SH",
        "600003.SH",
    ]


def test_alpha_adjusted_gate_can_keep_more_events():
    frame = pl.DataFrame({
        "symbol": ["600001.SH", "600002.SH", "600003.SH"],
        "market_prediction": [-0.004, -0.009, 0.001],
    })
    training_alpha = 0.005

    selected = frame.filter(
        pl.col("market_prediction") + training_alpha > 0,
    )

    assert selected["symbol"].to_list() == ["600001.SH", "600003.SH"]
