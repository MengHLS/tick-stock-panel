"""Contracts for the D-day auction veto overlay."""

from datetime import date

import polars as pl

from scripts import auction_d_day_veto_study as study


def _veto_frame() -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": ["600001.SH", "600002.SH", "600003.SH", "600004.SH"],
        "date": [date(2024, 1, 2)] * 4,
        "tail_strength_signal": [True, True, True, True],
        "last_imbalance": [0.10, -0.20, 0.20, None],
        "last_unmatched_sell_shares": [100, 300, 100, 100],
        "c0924_unmatched_sell_shares": [200, 200, 200, 200],
        "last_age_ms": [10_000, 10_000, 40_000, 10_000],
        "c0924_age_ms": [10_000, 10_000, 10_000, 10_000],
        "population_sell_expansion": [4, 4, 4, 4],
    })


def test_veto_columns_fail_closed_on_stale_or_missing_auction_data():
    result = study.add_veto_columns(_veto_frame())

    assert result["sell_data_valid"].to_list() == [True, True, False, False]
    assert result["sell_expansion"].to_list() == [False, True, False, False]


def test_balanced_veto_keeps_only_non_negative_valid_tail_signals():
    selected = study.apply_variant(
        study.add_veto_columns(_veto_frame()),
        "balanced_veto",
    )

    assert selected["symbol"].to_list() == ["600001.SH"]


def test_fold_assignment_requires_each_configured_test_window():
    frame = pl.DataFrame({
        "symbol": [f"60000{index}.SH" for index in range(1, 6)],
        "date": [fold["test_start"] for fold in study.FOLDS],
    })

    assigned = study.assign_fold(frame)

    assert assigned["fold"].to_list() == [fold["name"] for fold in study.FOLDS]


def test_csv_rows_flatten_nested_portfolio_details():
    row = study.flatten_csv_row({"status": "ok", "rejected": {"no_slot": 2}})

    assert row == {"status": "ok", "rejected": '{"no_slot": 2}'}
