"""Stock-code calibration for the platform limit-up table.

Only repairs proven by the candidate symbol's own limit-up close are applied;
everything else must stay untouched (fail-closed).
"""
from __future__ import annotations

import polars as pl

from app.custom.limit_up_platform.calibrate import plan_code_calibration


def _instruments() -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": ["000011.SZ", "600202.SH", "603023.SH", "603106.SH", "603661.SH"],
        "name": ["深物业A", "哈空调", "威帝股份", "恒银科技", "恒林股份"],
        "code": ["000011", "600202", "603023", "603106", "603661"],
    })


def _frame() -> pl.DataFrame:
    return pl.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "date": ["2026-09-30", "2026-10-22", "2026-09-16", "2026-08-04", "2026-08-04"],
        "symbol": ["00011.SZ", "600202.SZ", "603023.SZ", "603106.SH", "603106.SH"],
        "code": ["00011", "600202", "603023", "603106", "603106"],
        "name": ["深物业A", "哈空调", "威帝股份", "恒银科技", "恒林股份"],
    })


def test_repairs_pad_and_suffix_when_price_confirms() -> None:
    confirmed = {("2026-09-30", "000011.SZ"), ("2026-10-22", "600202.SH")}
    corrected, changes = plan_code_calibration(_frame(), _instruments(), confirmed)
    by_id = {row["id"]: row for row in corrected.to_dicts()}
    assert by_id[1]["symbol"] == "000011.SZ" and by_id[1]["code"] == "000011"
    assert by_id[2]["symbol"] == "600202.SH" and by_id[2]["code"] == "600202"
    assert {c.rule for c in changes if c.record_id in (1, 2)} == {"pad", "suffix"}


def test_unconfirmed_candidate_is_left_untouched() -> None:
    corrected, changes = plan_code_calibration(_frame(), _instruments(), set())
    by_id = {row["id"]: row for row in corrected.to_dicts()}
    assert by_id[1]["symbol"] == "00011.SZ"
    assert by_id[2]["symbol"] == "600202.SZ"
    unresolved = {c.record_id for c in changes if c.action == "unresolved"}
    assert {1, 2} <= unresolved


def test_duplicate_keeps_row_matching_instrument_name() -> None:
    confirmed = {("2026-08-04", "603106.SH")}
    corrected, changes = plan_code_calibration(_frame(), _instruments(), confirmed)
    rows = corrected.filter(pl.col("date") == "2026-08-04")
    assert rows.height == 1
    assert rows["name"].to_list() == ["恒银科技"]
    quarantined = [c for c in changes if c.action == "quarantine"]
    assert [c.record_id for c in quarantined] == [5]


def test_duplicate_is_reassigned_when_the_other_symbol_confirms() -> None:
    confirmed = {("2026-08-04", "603106.SH"), ("2026-08-04", "603661.SH")}
    corrected, changes = plan_code_calibration(_frame(), _instruments(), confirmed)
    rows = corrected.filter(pl.col("date") == "2026-08-04")
    assert rows.height == 2
    assert set(rows["symbol"].to_list()) == {"603106.SH", "603661.SH"}
    assert any(
        c.rule == "duplicate-name" and c.new_symbol == "603661.SH"
        for c in changes
    )


def _valid_symbol_frame() -> pl.DataFrame:
    return pl.DataFrame({
        "id": [10],
        "date": ["2026-08-03"],
        "symbol": ["600549.SH"],
        "code": ["600549"],
        "name": ["厦工股份"],
    })


def _valid_symbol_instruments() -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": ["600549.SH", "600815.SH"],
        "name": ["厦门钨业", "厦工股份"],
        "code": ["600549", "600815"],
    })


def test_repairs_valid_symbol_when_name_points_to_confirmed_stock() -> None:
    confirmed = {("2026-08-03", "600815.SH")}
    corrected, changes = plan_code_calibration(
        _valid_symbol_frame(), _valid_symbol_instruments(), confirmed,
    )
    row = corrected.to_dicts()[0]
    assert row["symbol"] == "600815.SH" and row["code"] == "600815"
    assert [(c.rule, c.action) for c in changes] == [("name", "repair")]


def test_valid_symbol_is_kept_when_it_confirms_even_if_name_differs() -> None:
    confirmed = {("2026-08-03", "600549.SH")}
    corrected, changes = plan_code_calibration(
        _valid_symbol_frame(), _valid_symbol_instruments(), confirmed,
    )
    assert corrected.equals(_valid_symbol_frame())
    assert changes == []
