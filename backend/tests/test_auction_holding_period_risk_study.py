"""Contracts for the D+5 and risk-budget research helper."""

from datetime import date, timedelta

import polars as pl
import pytest

from scripts import auction_holding_period_risk_study as study


def test_d5_join_replaces_frozen_d3_exit_fields():
    scored = pl.DataFrame({
        "symbol": ["600001.SH"],
        "date": [date(2024, 9, 2)],
        "entry_reason": ["ok"],
        "exit_reason": ["ok"],
        "exit_date": [date(2024, 9, 5)],
        "net_return": [0.01],
        "combined_rank": [0.8],
    })
    d5 = pl.DataFrame({
        "symbol": ["600001.SH"],
        "date": [date(2024, 9, 2)],
        "entry_reason": ["ok"],
        "exit_reason": ["ok"],
        "exit_date": [date(2024, 9, 9)],
        "gross_return": [0.03],
        "net_return": [0.025],
        "horizon": [5],
    })
    result = study.attach_d5_outcomes(scored, d5)
    assert result["exit_date"].to_list() == [date(2024, 9, 9)]
    assert result["net_return"].to_list() == [0.025]
    assert result["combined_rank"].to_list() == [0.8]


def test_risk_budget_sizes_high_volatility_smaller_than_low_volatility():
    rows = []
    start = date(2024, 1, 1)
    for symbol, daily_return in (("HIGH.SH", 0.05), ("LOW.SH", 0.01)):
        close = 100.0
        for day in range(25):
            if day:
                close *= 1 + (daily_return if day % 2 else -daily_return)
            rows.append({"symbol": symbol, "date": start + timedelta(days=day), "close": close})
    closes = pl.DataFrame(rows)
    selected = pl.DataFrame({
        "symbol": ["HIGH.SH", "LOW.SH"],
        "date": [start + timedelta(days=24)] * 2,
    })
    sized = study.add_risk_budget_size(selected, closes).sort("symbol")
    high = sized.filter(pl.col("symbol") == "HIGH.SH")["position_pct"].item()
    low = sized.filter(pl.col("symbol") == "LOW.SH")["position_pct"].item()
    assert high < low
    assert 0.02 < high < 0.03
    assert low == pytest.approx(0.05)


def test_position_column_overrides_fixed_target_size():
    row = {
        "symbol": "600001.SH",
        "date": date(2024, 9, 2),
        "exit_date": date(2024, 9, 3),
        "entry_vwap": 10.0,
        "entry_volume": 1_000_000.0,
        "net_return": 0.10,
        "position_pct": 0.025,
    }
    closes = pl.DataFrame({
        "symbol": ["600001.SH", "600001.SH"],
        "date": [date(2024, 9, 2), date(2024, 9, 3)],
        "close": [10.0, 10.5],
    })
    summary, filled, _ = study.simulate_daily_mark_with_position_column(
        pl.DataFrame([row]),
        calendar=[date(2024, 9, 2), date(2024, 9, 3)],
        daily_closes=closes,
        start=date(2024, 9, 2),
        end=date(2024, 9, 3),
    )
    assert len(filled) == 1
    assert summary["total_return"] == pytest.approx(0.025 * 0.10)
