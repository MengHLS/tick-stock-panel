"""Contracts for the frozen D+5 loss-attribution helper."""

from datetime import date

import polars as pl
import pytest

from scripts import auction_d5_loss_attribution as study


def test_load_d5_trades_filters_variant_and_casts_numeric_columns(tmp_path):
    path = tmp_path / "trades.csv"
    pl.DataFrame({
        "period": ["validation", "validation"],
        "variant": ["d5_fixed", "d3_fixed"],
        "symbol": ["600001.SH", "600002.SH"],
        "date": [date(2024, 9, 2)] * 2,
        "gap_bucket": ["2-4"] * 2,
        "combined_rank": ["0.80", "0.70"],
        "entry_vwap": [10.0, 10.0],
        "entry_volume": [1_000_000.0, 1_000_000.0],
        "exit_date": [date(2024, 9, 9)] * 2,
        "net_return": ["0.01", "0.02"],
        "allocated": ["50000", "50000"],
    }).write_csv(path)
    result = study.load_d5_trades(path)
    assert result.height == 1
    assert result["combined_rank"].dtype == pl.Float64
    assert result["net_return"].dtype == pl.Float64
    assert result["allocated"].dtype == pl.Float64


def test_attach_d5_gross_returns_rejects_net_mismatch(tmp_path):
    trades = pl.DataFrame({
        "symbol": ["600001.SH"],
        "date": [date(2024, 9, 2)],
        "net_return": [0.02],
    })
    outcomes = tmp_path / "d5.parquet"
    pl.DataFrame({
        "symbol": ["600001.SH"],
        "date": [date(2024, 9, 2)],
        "gross_return": [0.03],
        "net_return": [0.01],
    }).write_parquet(outcomes)
    with pytest.raises(ValueError, match="do not match"):
        study.attach_d5_gross_returns(trades, outcomes)
