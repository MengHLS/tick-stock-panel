"""Contracts for the frozen auction loss-attribution helper."""

from datetime import date

import polars as pl
import pytest

from scripts import auction_tail_loss_attribution as study


def test_market_beta_is_fitted_on_development_trades_only():
    market = [0.01, 0.02, -0.01, 0.03] * 8
    frame = pl.DataFrame({
        "period": ["development"] * len(market) + ["validation"] * 2,
        "market_return": [*market, 0.50, -0.40],
        "gross_return": [
            *[2 * value for value in market],
            1.00,
            -0.80,
        ],
    })
    assert study.estimate_market_beta(frame) == pytest.approx(2.0)


def test_return_components_reconcile_to_actual_pnl():
    frame = pl.DataFrame({
        "allocated": [1000.0],
        "gross_return": [0.02],
        "net_return": [0.017],
        "market_return": [0.01],
    })
    result = study.add_return_components(frame, beta=1.5)
    assert result["actual_pnl"][0] == pytest.approx(17.0)
    assert result["market_pnl"][0] == pytest.approx(15.0)
    assert result["stock_pnl"][0] == pytest.approx(5.0)
    assert result["cost_pnl"][0] == pytest.approx(-3.0)
    assert (
        result["market_pnl"][0]
        + result["stock_pnl"][0]
        + result["cost_pnl"][0]
    ) == pytest.approx(result["actual_pnl"][0])


def test_score_bands_are_left_closed_half_open():
    frame = pl.DataFrame({
        "combined_rank": [0.70, 0.7499, 0.75, 0.80, 0.8499, 0.85, 0.8999],
        "date": [date(2024, 9, 2)] * 7,
    })
    bands = study.add_score_band(frame)["score_band"].to_list()
    assert bands == [
        "70-75", "70-75", "75-80", "80-85", "80-85", "85-90", "85-90",
    ]


def test_concentration_counts_fractional_tail_trades():
    trades = pl.DataFrame({
        "period": ["validation"] * 5,
        "actual_pnl": [-3.0, -2.0, 1.0, 4.0, 5.0],
    })
    result = study.concentration_stats(trades, fraction=0.4)
    assert result.row(0, named=True) == {
        "period": "validation",
        "n": 5,
        "tail_n": 2,
        "worst_tail_pnl": -5.0,
        "best_tail_pnl": 9.0,
        "total_pnl": 5.0,
    }
