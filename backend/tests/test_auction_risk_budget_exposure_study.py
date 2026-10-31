"""Contracts for the risk-budget and market-exposure study."""

from datetime import date

import polars as pl
import pytest

from scripts import auction_risk_budget_exposure_study as study


def _base_frame() -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": ["600001.SH", "600002.SH", "600003.SH", "600004.SH"],
        "date": [date(2024, 1, 2)] * 4,
        "fold": ["test_2024"] * 4,
        "_selection_order": [1, 2, 3, 4],
        "trend_gate": [True, True, False, False],
        "vol_gate": [True, False, True, False],
    })


def test_market_regime_uses_fixed_one_half_zero_multipliers():
    frame = study.add_market_regime(_base_frame())

    assert frame["market_regime"].to_list() == [
        "risk_on",
        "mixed",
        "mixed",
        "risk_off",
    ]
    assert frame["market_size_multiplier"].to_list() == [1.0, 0.5, 0.5, 0.0]


def test_load_event_panel_uses_only_d5_outcome(tmp_path):
    events_path = tmp_path / "events.parquet"
    d5_path = tmp_path / "d5.parquet"
    pl.DataFrame({
        "symbol": ["600001.SH", "600001.SH"],
        "date": [date(2024, 1, 2), date(2024, 1, 2)],
        "gap_bucket": ["2-4", "2-4"],
        "horizon": [3, 5],
        "signal_eligible": [True, True],
    }).write_parquet(events_path)
    pl.DataFrame({
        "symbol": ["600001.SH"],
        "date": [date(2024, 1, 2)],
        "entry_reason": ["ok"],
        "exit_reason": ["ok"],
        "exit_date": [date(2024, 1, 9)],
        "net_return": [0.02],
        "horizon": [5],
    }).write_parquet(d5_path)

    panel = study.load_event_panel(events_path, d5_path)

    assert panel.height == 1
    assert panel["net_return"].item() == pytest.approx(0.02)


def test_cash_gate_keeps_only_both_market_gates():
    frame, signal_n = study.prepare_portfolio_input(
        _base_frame(),
        "cash_gate",
        daily_closes=pl.DataFrame(),
    )

    assert signal_n == 4
    assert frame["symbol"].to_list() == ["600001.SH"]


def test_regime_scaled_filters_zero_exposure_and_scales_position(monkeypatch):
    monkeypatch.setattr(study, "PORTFOLIO_DEFAULTS", {"position_pct": 0.05})

    frame, signal_n = study.prepare_portfolio_input(
        _base_frame(),
        "regime_scaled",
        daily_closes=pl.DataFrame(),
    )

    assert signal_n == 4
    assert frame["symbol"].to_list() == ["600001.SH", "600002.SH", "600003.SH"]
    assert frame["position_pct"].to_list() == pytest.approx([0.05, 0.025, 0.025])


def test_regime_vol_budget_multiplies_frozen_risk_budget(monkeypatch):
    monkeypatch.setattr(
        study,
        "add_risk_budget_size",
        lambda frame, _closes: frame.with_columns(
            pl.lit(0.04).alias("position_pct"),
        ),
    )

    frame, signal_n = study.prepare_portfolio_input(
        _base_frame(),
        "regime_vol_budget",
        daily_closes=pl.DataFrame(),
    )

    assert signal_n == 4
    assert frame["symbol"].to_list() == ["600001.SH", "600002.SH", "600003.SH"]
    assert frame["position_pct"].to_list() == pytest.approx([0.04, 0.02, 0.02])
