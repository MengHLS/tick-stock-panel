"""Contracts for the score-tail stability research helper."""

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from scripts import auction_tail_stability_study as study


def test_market_features_use_only_prior_completed_session():
    dates = [date(2024, 1, 1) + timedelta(days=index) for index in range(25)]
    closes = [100.0 + index + (index % 3) * 0.2 for index in range(25)]
    features = study.compute_market_features(
        pl.DataFrame({"date": dates, "close": closes}),
    )
    values = features["market_vol_20d"].to_list()
    assert values[:21] == [None] * 21
    closes_array = np.asarray(closes)
    returns = closes_array[1:] / closes_array[:-1] - 1
    expected = float(np.std(returns[0:20], ddof=1))
    assert values[21] == pytest.approx(expected)
    assert features["market_ret_20d"][21] == pytest.approx(closes[20] / closes[0] - 1)


def test_stability_signals_use_left_closed_band_and_both_consensus_ranks():
    frame = pl.DataFrame({
        "combined_rank": [0.69, 0.70, 0.89, 0.90],
        "_tail_risk_blend": [True, True, True, True],
        "risk_rank": [0.69, 0.70, 0.80, 0.90],
        "tail_strength_rank": [0.80, 0.70, 0.60, 0.90],
        "market_vol_20d": [0.10, 0.10, 0.30, 0.20],
    })
    result = study.add_stability_signals(frame, vol_threshold=0.20)
    assert result["_band70_90"].to_list() == [False, True, True, False]
    assert result["_band70_90_lowvol"].to_list() == [False, True, False, False]
    assert result["_consensus70"].to_list() == [False, True, False, True]
    assert result["consensus_score"].to_list() == pytest.approx([0.69, 0.70, 0.60, 0.90])


def test_development_volatility_threshold_weights_dates_once():
    day1 = date(2021, 1, 4)
    day2 = date(2021, 1, 5)
    day3 = date(2021, 1, 6)
    frame = pl.DataFrame({
        "date": [day1, day1, day2, day2, day3],
        "market_vol_20d": [0.10, 0.10, 0.30, 0.30, 0.20],
    })
    assert study.development_vol_threshold(frame) == pytest.approx(0.20)
