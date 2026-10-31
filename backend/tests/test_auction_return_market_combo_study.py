"""Contracts for the expected-return and market-gate combination."""

from datetime import date

import polars as pl
import pytest

from scripts import auction_return_market_combo_study as study


def test_load_base_filters_expected_primary_and_joins_market(tmp_path):
    selected_path = tmp_path / "selected.parquet"
    pl.DataFrame({
        "symbol": ["600002.SH", "600001.SH", "600003.SH"],
        "date": [date(2024, 1, 2)] * 3,
        "variant": ["keep_top_50", "keep_top_70", "keep_top_50"],
        "fold": ["test_2024"] * 3,
        "_selection_order": [2, 1, 3],
    }).write_parquet(selected_path)
    market = pl.DataFrame({
        "date": [date(2024, 1, 2)],
        "trend_gate": [True],
        "vol_gate": [False],
        "market_vol20": [0.01],
    })

    base = study.load_base(selected_path, market)

    assert base["symbol"].to_list() == ["600002.SH", "600003.SH"]
    assert base["market_vol20"].to_list() == [0.01, 0.01]


def test_load_base_fails_closed_without_market_features(tmp_path):
    selected_path = tmp_path / "selected.parquet"
    pl.DataFrame({
        "symbol": ["600001.SH"],
        "date": [date(2024, 1, 2)],
        "variant": ["keep_top_50"],
        "fold": ["test_2024"],
        "_selection_order": [1],
    }).write_parquet(selected_path)
    market = pl.DataFrame({
        "date": [date(2024, 1, 3)],
        "trend_gate": [True],
        "vol_gate": [True],
        "market_vol20": [0.01],
    })

    with pytest.raises(ValueError, match="without D-1 market features"):
        study.load_base(selected_path, market)


def test_market_variants_filter_without_refilling():
    frame = pl.DataFrame({
        "symbol": ["600001.SH", "600002.SH", "600003.SH", "600004.SH"],
        "trend_gate": [True, False, True, False],
        "vol_gate": [True, True, False, False],
    })

    assert study.apply_market_variant(
        frame,
        "expected_return_top_50",
    )["symbol"].to_list() == [
        "600001.SH",
        "600002.SH",
        "600003.SH",
        "600004.SH",
    ]
    assert study.apply_market_variant(frame, "trend_gate")["symbol"].to_list() == [
        "600001.SH",
        "600003.SH",
    ]
    assert study.apply_market_variant(frame, "vol_gate")["symbol"].to_list() == [
        "600001.SH",
        "600002.SH",
    ]
    assert study.apply_market_variant(
        frame,
        "trend_vol_gate",
    )["symbol"].to_list() == ["600001.SH"]


def test_decision_gate_requires_reduction_and_profit():
    base = pl.DataFrame({"symbol": [f"{index:06d}.SH" for index in range(400)]})
    primary = pl.DataFrame({"symbol": [f"{index:06d}.SH" for index in range(200)]})
    variants = {
        study.BASE_VARIANT: base,
        study.PRIMARY_VARIANT: primary,
    }
    events = [{
        "variant": study.PRIMARY_VARIANT,
        "mean_net_return": 0.001,
        "cluster_bootstrap_95": {
            "mean_incremental_return": [0.001, 0.004],
        },
    }]
    portfolio = {
        study.PRIMARY_VARIANT: {
            "oos": {
                "total_return": 0.02,
                "max_drawdown_mtm": -0.10,
                "stale_marks": 0,
            },
        },
    }

    gate = study.decision_gate(
        variants,
        events,
        portfolio,
        session_count=1_000,
    )

    assert gate["candidate_reduction"] == pytest.approx(0.5)
    assert gate["passed"] is True
