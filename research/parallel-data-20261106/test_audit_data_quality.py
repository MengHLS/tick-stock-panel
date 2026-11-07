#!/usr/bin/env python3
"""Targeted tests for the read-only history quality audit.

Every fixture here is synthetic and in memory: the tests prove that the auditor
*recognises* each failure mode (missing trading day, per-symbol stale tail,
interior hole, duplicate snapshot, conflicting industry, future or non-trading
snapshot, bad adjustment factor) before it is pointed at real project data.

No test writes to disk: the audit itself is read only, and the assertions are
about classification only. Run with::

    python -m pytest research/parallel-data-20261106/test_audit_data_quality.py -q
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_data_quality as audit  # noqa: E402

PASS = audit.STATUS_PASS
FAIL = audit.STATUS_FAIL
UNKNOWN = audit.STATUS_UNKNOWN

AS_OF = date(2026, 11, 6)


def _trading_days(start: date, count: int) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range(count)]


def _panel(days: list[str], symbols: list[str], *, skip: dict[str, list[str]] | None = None):
    """Build (partition, rows) pairs; ``skip`` drops (day -> symbols)."""
    skip = skip or {}
    for day in days:
        rows = [(s, day) for s in symbols if s not in skip.get(day, [])]
        yield day, rows


# --------------------------------------------------------------------------- #
# calendar
# --------------------------------------------------------------------------- #
def test_calendar_detects_missing_trading_day():
    index = _trading_days(date(2026, 11, 2), 5)
    panel = [d for d in index if d != index[2]]
    cal = audit.build_calendar(index, panel)
    check = audit.check_calendar_coverage(cal)
    assert check["status"] == FAIL
    assert check["evidence"]["missing_from_panel_count"] == 1
    assert check["evidence"]["missing_from_panel"] == [index[2]]


def test_calendar_detects_extra_panel_partition():
    index = _trading_days(date(2026, 11, 2), 5)
    panel = index + ["2026-11-01"]  # a Sunday partition
    cal = audit.build_calendar(index, panel)
    check = audit.check_calendar_coverage(cal)
    assert check["status"] == FAIL
    assert check["evidence"]["extra_in_panel"] == ["2026-11-01"]


def test_calendar_without_index_is_unknown_not_pass():
    cal = audit.build_calendar([], _trading_days(date(2026, 11, 2), 5))
    check = audit.check_calendar_coverage(cal)
    assert check["status"] == UNKNOWN
    assert check["unknown_reason"]


# --------------------------------------------------------------------------- #
# panel partitions
# --------------------------------------------------------------------------- #
def test_panel_duplicate_rows_detected():
    days = _trading_days(date(2026, 11, 2), 3)
    parts = [(d, [("A", d), ("A", d), ("B", d)]) for d in days]
    summary = audit.summarize_panel(parts, calendar_days={date.fromisoformat(d) for d in days})
    check = audit.check_panel_partition_integrity(
        summary, calendar_days={date.fromisoformat(d) for d in days}, as_of=AS_OF
    )
    assert check["status"] == FAIL
    assert check["evidence"]["duplicate_symbol_rows"] == 3


def test_panel_row_partition_date_mismatch_detected():
    days = _trading_days(date(2026, 11, 2), 2)
    parts = [
        (days[0], [("A", days[0])]),
        (days[1], [("A", days[0])]),  # filed under the wrong partition
    ]
    summary = audit.summarize_panel(parts, calendar_days={date.fromisoformat(d) for d in days})
    check = audit.check_panel_partition_integrity(
        summary, calendar_days={date.fromisoformat(d) for d in days}, as_of=AS_OF
    )
    assert check["status"] == FAIL
    assert check["evidence"]["row_partition_date_mismatch"] == 1


def test_panel_future_partition_detected():
    days = _trading_days(date(2026, 11, 2), 3)
    days = days + ["2026-11-09"]  # after AS_OF
    parts = list(_panel(days, ["A"]))
    summary = audit.summarize_panel(parts, calendar_days={date.fromisoformat(d) for d in days})
    check = audit.check_panel_partition_integrity(
        summary, calendar_days={date.fromisoformat(d) for d in days}, as_of=AS_OF
    )
    assert check["status"] == FAIL
    assert check["evidence"]["future_partitions"] == ["2026-11-09"]


def test_panel_non_trading_partition_detected():
    trading = _trading_days(date(2026, 11, 2), 5)
    parts = list(_panel(trading, ["A"]))
    parts.append(("2026-11-01", [("A", "2026-11-01")]))  # Sunday
    summary = audit.summarize_panel(parts, calendar_days={date.fromisoformat(d) for d in trading})
    check = audit.check_panel_partition_integrity(
        summary, calendar_days={date.fromisoformat(d) for d in trading}, as_of=AS_OF
    )
    assert check["status"] == FAIL
    assert "2026-11-01" in check["evidence"]["partitions_off_calendar"]


# --------------------------------------------------------------------------- #
# enriched parity
# --------------------------------------------------------------------------- #
def test_enriched_parity_gap_detected():
    check = audit.check_enriched_parity(["2026-11-02", "2026-11-03"], ["2026-11-02"])
    assert check["status"] == FAIL
    assert check["evidence"]["only_in_panel"] == ["2026-11-03"]


def test_enriched_parity_clean_passes():
    assert audit.check_enriched_parity(["a", "b"], ["b", "a"])["status"] == PASS


# --------------------------------------------------------------------------- #
# adjustment factors
# --------------------------------------------------------------------------- #
def test_adj_factor_duplicate_conflict_invalid_and_future():
    records = [
        {"symbol": "A", "trade_date": "2026-11-02", "ex_factor": 1.0},
        {"symbol": "A", "trade_date": "2026-11-02", "ex_factor": 1.0},  # duplicate
        {"symbol": "B", "trade_date": "2026-11-02", "ex_factor": 1.0},
        {"symbol": "B", "trade_date": "2026-11-02", "ex_factor": 1.5},  # conflict
        {"symbol": "C", "trade_date": "2026-11-02", "ex_factor": 0.05},  # below contract
        {"symbol": "D", "trade_date": "2026-11-09", "ex_factor": 1.1},  # future
    ]
    check = audit.check_adj_factors(records, panel_symbols={"A", "B", "C", "D"}, as_of=AS_OF)
    assert check["status"] == FAIL
    assert check["evidence"]["duplicate_pairs"] == 1
    assert check["evidence"]["conflicting_pairs"] == 1
    assert check["evidence"]["invalid_values"] >= 1
    assert check["evidence"]["future_rows"] == 1


def test_adj_factor_missing_symbol_is_unknown_not_silent_pass():
    records = [
        {"symbol": "A", "trade_date": "2026-11-02", "ex_factor": 1.0},
    ]
    check = audit.check_adj_factors(records, panel_symbols={"A", "Z"}, as_of=AS_OF)
    assert check["status"] == PASS  # no confirmed anomaly ...
    assert check["evidence"]["panel_symbols_without_factor"] == 1
    assert check["unknown_reason"]  # ... but completeness stays unknown


# --------------------------------------------------------------------------- #
# ST history
# --------------------------------------------------------------------------- #
def test_st_history_conflict_detected():
    records = [
        {"symbol": "A", "flag_date": "2026-11-02", "st_flag": True},
        {"symbol": "A", "flag_date": "2026-11-02", "st_flag": False},
    ]
    days = {date(2026, 11, 2)}
    check = audit.check_st_history(records, calendar_days=days, window_start=date(2026, 11, 2), window_end=date(2026, 11, 2))
    assert check["status"] == FAIL
    assert check["evidence"]["conflicting_flags"] == 1


def test_st_history_absent_days_stay_unknown():
    records = [{"symbol": "A", "flag_date": "2026-11-02", "st_flag": True}]
    days = {date(2026, 11, 2), date(2026, 11, 3)}
    check = audit.check_st_history(records, calendar_days=days, window_start=date(2026, 11, 2), window_end=date(2026, 11, 3))
    assert check["status"] == PASS
    assert check["evidence"]["trading_days_without_state"] == 1
    assert check["unknown_reason"]


# --------------------------------------------------------------------------- #
# instruments snapshot
# --------------------------------------------------------------------------- #
def test_instruments_missing_listing_date_fails():
    records = [
        {"symbol": "A", "listing_date": "2010-01-04", "as_of": "2026-11-05"},
        {"symbol": "B", "listing_date": None, "as_of": "2026-11-05"},
    ]
    check = audit.check_instruments(records, panel_symbols={"A", "B"}, panel_window_start=date(2018, 1, 8))
    assert check["status"] == FAIL
    assert check["evidence"]["missing_listing_date"] == 1


def test_instruments_panel_symbol_absent_is_unknown():
    records = [{"symbol": "A", "listing_date": "2010-01-04", "as_of": "2026-11-05"}]
    check = audit.check_instruments(records, panel_symbols={"A", "920001.BJ"}, panel_window_start=date(2018, 1, 8))
    assert check["status"] == PASS
    assert check["evidence"]["panel_symbols_not_in_instruments"] == 1
    assert check["unknown_reason"]


def test_instruments_truncation_at_panel_start_is_flagged():
    records = [{"symbol": "A", "listing_date": "2018-01-08", "as_of": "2026-11-05"}]
    check = audit.check_instruments(records, panel_symbols={"A"}, panel_window_start=date(2018, 1, 8))
    assert check["evidence"]["listed_on_or_before_panel_start"] == 1


def test_instruments_separates_truncation_from_late_listing():
    """A bar dated before a later listing_date is a real contradiction."""
    records = [
        {"symbol": "OLD", "listing_date": "2010-01-04", "as_of": "2026-11-05"},
        {"symbol": "NEW", "listing_date": "2024-03-01", "as_of": "2026-11-05"},
    ]
    check = audit.check_instruments(
        records,
        panel_symbols={"OLD", "NEW"},
        panel_window_start=date(2018, 1, 8),
        truncated_symbols=["OLD", "NEW"],
    )
    assert check["evidence"]["panel_start_truncated_with_earlier_listing"] == 1
    assert check["evidence"]["bars_before_listing_date"] == 1
    assert check["evidence"]["bars_before_listing_date_sample"] == ["NEW"]
    assert check["status"] == FAIL


def test_industry_column_is_resolved_by_meaning_not_position():
    columns = ["股票代码", "股票简称", "所属同花顺行业", "symbol", "code", "date"]
    symbol_col, industry_col = audit.resolve_industry_columns(columns)
    assert symbol_col == "symbol"
    assert industry_col == "所属同花顺行业"


# --------------------------------------------------------------------------- #
# industry point in time
# --------------------------------------------------------------------------- #
def _pit(snapshots: dict[str, list[tuple[str, str]]]) -> dict[str, list[dict]]:
    return {
        day: [{"__symbol__": s, "__industry__": ind} for s, ind in rows]
        for day, rows in snapshots.items()
    }


def test_industry_duplicate_and_conflict_detected():
    snapshots = _pit(
        {
            "2026-11-02": [("A", "银行"), ("A", "银行"), ("B", "银行"), ("B", "券商")],
        }
    )
    checks = audit.check_industry_pit(
        snapshots,
        industry_col="所属同花顺行业",
        calendar_days={date(2026, 11, 2)},
        panel_dates={date(2026, 11, 2)},
        as_of=AS_OF,
    )
    integrity = checks[0]
    assert integrity["status"] == FAIL
    assert integrity["evidence"]["duplicate_rows"] == 1
    assert integrity["evidence"]["conflicting_symbol_days"] == 1


def test_industry_future_snapshot_detected():
    snapshots = _pit({"2026-11-09": [("A", "银行")]})
    checks = audit.check_industry_pit(
        snapshots,
        industry_col="所属同花顺行业",
        calendar_days={date(2026, 11, 2)},
        panel_dates={date(2026, 11, 2)},
        as_of=AS_OF,
    )
    assert checks[0]["status"] == FAIL
    assert checks[0]["evidence"]["future_partitions"] == ["2026-11-09"]


def test_industry_non_trading_snapshot_detected():
    trading = [date(2026, 11, 2), date(2026, 11, 3)]
    snapshots = _pit({"2026-11-01": [("A", "银行")], "2026-11-02": [("A", "银行")]})
    checks = audit.check_industry_pit(
        snapshots,
        industry_col="所属同花顺行业",
        calendar_days=set(trading),
        panel_dates=set(trading),
        as_of=AS_OF,
    )
    alignment = checks[1]
    assert alignment["status"] == FAIL
    assert alignment["evidence"]["non_trading_snapshot_days"] == ["2026-11-01"]


def test_industry_depth_blocks_historical_backtest():
    panel_dates = {date(2026, 1, 5) + timedelta(days=i) for i in range(100)}
    snapshots = _pit({d.isoformat(): [("A", "银行")] for d in sorted(panel_dates)[:5]})
    checks = audit.check_industry_pit(
        snapshots,
        industry_col="所属同花顺行业",
        calendar_days=set(panel_dates),
        panel_dates=set(panel_dates),
        as_of=AS_OF,
    )
    depth = checks[2]
    assert depth["status"] == FAIL
    assert depth["evidence"]["coverage_ratio"] < 0.9
    assert depth["unknown_reason"]  # intraday availability is not recorded


# --------------------------------------------------------------------------- #
# security lifecycle
# --------------------------------------------------------------------------- #
def _lifecycle(summary, calendar):
    return audit.check_lifecycle(summary, calendar, has_suspension_table=False)


def test_lifecycle_stale_symbol_detected():
    days = _trading_days(date(2026, 11, 2), 5)
    parts = list(_panel(days, ["A", "B"], skip={days[-1]: ["B"], days[-2]: ["B"]}))
    cal_days = {date.fromisoformat(d) for d in days}
    summary = audit.summarize_panel(parts, calendar_days=cal_days)
    calendar = audit.build_calendar(days, days)
    check = _lifecycle(summary, calendar)
    assert check["evidence"]["symbols_stale_before_window_end"] == 1
    assert check["evidence"]["symbols_stale_before_window_end_sample"] == ["B"]
    assert check["status"] == UNKNOWN  # no suspension table: cause stays unknown
    assert check["unknown_reason"]


def test_lifecycle_interior_hole_detected():
    days = _trading_days(date(2026, 11, 2), 5)
    parts = list(_panel(days, ["A", "B"], skip={days[2]: ["B"]}))
    cal_days = {date.fromisoformat(d) for d in days}
    summary = audit.summarize_panel(parts, calendar_days=cal_days)
    calendar = audit.build_calendar(days, days)
    check = _lifecycle(summary, calendar)
    assert check["evidence"]["symbols_with_holes"] == 1
    assert check["evidence"]["total_missing_symbol_days"] == 1
    assert check["evidence"]["worst_holes"][0]["symbol"] == "B"


def test_lifecycle_truncation_at_window_start_is_not_a_confirmed_hole():
    days = _trading_days(date(2026, 11, 2), 5)
    parts = list(_panel(days, ["NEW"]))  # starts exactly at window start
    cal_days = {date.fromisoformat(d) for d in days}
    summary = audit.summarize_panel(parts, calendar_days=cal_days)
    calendar = audit.build_calendar(days, days)
    check = _lifecycle(summary, calendar)
    assert check["evidence"]["symbols_truncated_at_window_start"] == 1
    assert check["evidence"]["symbols_with_holes"] == 0
    assert check["evidence"]["suspension_table_available"] is False


def test_lifecycle_with_suspension_table_becomes_a_confirmed_failure():
    days = _trading_days(date(2026, 11, 2), 5)
    parts = list(_panel(days, ["A", "B"], skip={days[2]: ["B"]}))
    cal_days = {date.fromisoformat(d) for d in days}
    summary = audit.summarize_panel(parts, calendar_days=cal_days)
    calendar = audit.build_calendar(days, days)
    check = audit.check_lifecycle(summary, calendar, has_suspension_table=True)
    assert check["status"] == FAIL


# --------------------------------------------------------------------------- #
# verdict / exit code / suitability
# --------------------------------------------------------------------------- #
def _check(status: str, required: bool = True, cid: str = "x") -> dict:
    return {
        "id": cid,
        "title": "t",
        "required": required,
        "status": status,
        "evidence": {},
        "findings": [],
        "unknown_reason": None,
    }


def test_exit_code_precedence_fail_beats_unknown():
    code, verdict = audit.derive_exit_code([_check(UNKNOWN), _check(FAIL)])
    assert code == audit.EXIT_ANOMALY == 1
    assert verdict["verdict"] == "anomaly_detected"
    assert verdict["required_unknown"] and verdict["required_failed"]


def test_exit_code_unknown_when_only_inconclusive():
    code, verdict = audit.derive_exit_code([_check(PASS), _check(UNKNOWN)])
    assert code == audit.EXIT_INSUFFICIENT == 2
    assert verdict["verdict"] == "insufficient_evidence"


def test_exit_code_zero_when_all_required_pass():
    code, verdict = audit.derive_exit_code([_check(PASS), _check(FAIL, required=False)])
    assert code == audit.EXIT_OK == 0
    assert verdict["verdict"] == "passed"


def test_backtest_suitability_blocks_industry_on_depth_failure():
    checks = {
        "panel_partition_integrity": _check(PASS, cid="panel_partition_integrity"),
        "calendar_coverage": _check(PASS, cid="calendar_coverage"),
        "adj_factor_integrity": _check(PASS, cid="adj_factor_integrity"),
        "security_lifecycle_coverage": _check(UNKNOWN, cid="security_lifecycle_coverage"),
        "industry_pit_history_depth": _check(FAIL, cid="industry_pit_history_depth"),
        "industry_pit_calendar_alignment": _check(FAIL, cid="industry_pit_calendar_alignment"),
        "industry_pit_integrity": _check(PASS, cid="industry_pit_integrity"),
    }
    checks["industry_pit_integrity"]["evidence"] = {"date_min": "2026-11-01"}
    checks["industry_pit_history_depth"]["evidence"] = {"coverage_ratio": 0.0023}
    suitability = audit.build_backtest_suitability(checks)
    assert suitability["historical_industry_rotation"]["supported"] is False
    assert suitability["delisted_universe_backtest"]["supported"] is False
    assert suitability["suspension_aware_execution"]["supported"] is False
    cross_section = suitability["daily_cross_section_backtest"]
    assert cross_section["supported"] is False
    assert cross_section["permitted_use"] == "exploratory_research_only"
    assert cross_section["integrity_checks_pass"] is True
    joined = " ".join(cross_section["unknowns"]).lower()
    assert len(cross_section["unknowns"]) >= 3
    assert "delisting" in joined or "survivorship" in joined
    assert "attribution" in joined
    assert "execution feasibility" in joined or "liquidity" in joined


def test_cross_section_suitability_declares_unknowns_and_quotes_evidence():
    """Passing local checks is not a data-availability verdict, and unexplained holes stay unknown."""
    checks = {
        "panel_partition_integrity": _check(PASS, cid="panel_partition_integrity"),
        "calendar_coverage": _check(PASS, cid="calendar_coverage"),
        "adj_factor_integrity": _check(PASS, cid="adj_factor_integrity"),
        "security_lifecycle_coverage": _check(UNKNOWN, cid="security_lifecycle_coverage"),
        "industry_pit_history_depth": _check(FAIL, cid="industry_pit_history_depth"),
        "industry_pit_calendar_alignment": _check(FAIL, cid="industry_pit_calendar_alignment"),
        "industry_pit_integrity": _check(PASS, cid="industry_pit_integrity"),
    }
    checks["industry_pit_integrity"]["evidence"] = {"date_min": "2026-11-01"}
    checks["industry_pit_history_depth"]["evidence"] = {"coverage_ratio": 0.0023}
    checks["adj_factor_integrity"]["evidence"] = {"panel_symbols_without_factor": 616}
    checks["security_lifecycle_coverage"]["evidence"] = {
        "total_missing_symbol_days": 43503,
        "symbols_stale_before_window_end": 241,
    }

    cross = audit.build_backtest_suitability(checks)["daily_cross_section_backtest"]
    assert cross["supported"] is False
    assert cross["permitted_use"] == "exploratory_research_only"
    assert cross["integrity_checks_pass"] is True
    text = " ".join(cross["unknowns"])
    # measured numbers must reach the machine-readable report, not just the prose
    assert "616" in text
    assert "43503" in text
    assert "241" in text
    # an unknown may never be reworded into a confirmed deletion stage
    assert "cause of a hole is unknown" in text
    assert "deleted at ingestion" not in text


def test_report_has_required_machine_readable_fields():
    """The report schema a consumer relies on must not silently drift."""
    days = _trading_days(date(2026, 11, 2), 3)
    cal_days = {date.fromisoformat(d) for d in days}
    summary = audit.summarize_panel(_panel(days, ["A", "B"]), calendar_days=cal_days)
    calendar = audit.build_calendar(days, days)
    checks = [
        audit.check_panel_partition_integrity(summary, calendar_days=cal_days, as_of=AS_OF),
        audit.check_calendar_coverage(calendar),
        audit.check_enriched_parity(days, days),
        audit.check_adj_factors(
            [{"symbol": s, "trade_date": days[0], "ex_factor": 1.0} for s in ("A", "B")],
            panel_symbols={"A", "B"},
            as_of=AS_OF,
        ),
        audit.check_st_history([], calendar_days=cal_days, window_start=date(2026, 11, 2), window_end=date(2026, 11, 6)),
        audit.check_instruments(
            [{"symbol": s, "listing_date": "2010-01-04", "as_of": "2026-11-05"} for s in ("A", "B")],
            panel_symbols={"A", "B"},
            panel_window_start=date(2026, 11, 2),
        ),
        *_pit_checks(days),
        audit.check_lifecycle(summary, calendar, has_suspension_table=False),
    ]
    code, verdict = audit.derive_exit_code(checks)
    for check in checks:
        assert set(check) == {"id", "title", "required", "status", "evidence", "findings", "unknown_reason"}
        assert check["status"] in (PASS, FAIL, UNKNOWN)
    assert code in (0, 1, 2)
    assert set(verdict) >= {"verdict", "exit_code", "required_failed", "required_unknown"}


def _pit_checks(days: list[str]):
    return audit.check_industry_pit(
        _pit({days[0]: [("A", "银行"), ("B", "券商")]}),
        industry_col="所属同花顺行业",
        calendar_days={date.fromisoformat(d) for d in days},
        panel_dates={date.fromisoformat(d) for d in days},
        as_of=AS_OF,
    )


# --------------------------------------------------------------------------- #
# zero-price rows (the only local suspension signal)
# --------------------------------------------------------------------------- #
def test_zero_price_rows_counted_as_suspension_shape():
    rows = [
        ("A", "2026-11-02", 10.0, 10.5),
        ("B", "2026-11-02", 0.0, 0.0),  # suspension shape
        ("C", "2026-11-02", 0.0, 9.0),  # breaks the convention
    ]
    summary = audit.summarize_panel([("2026-11-02", rows)], calendar_days={date(2026, 11, 2)})
    check = audit.check_price_row_integrity(summary)
    assert check["evidence"]["open_zero_and_high_zero"] == 1
    assert check["evidence"]["open_zero_only"] == 1
    assert check["status"] == FAIL  # the half-zero row is a confirmed anomaly


def test_zero_price_rows_clean_passes():
    rows = [("A", "2026-11-02", 10.0, 10.5), ("B", "2026-11-02", 0.0, 0.0)]
    summary = audit.summarize_panel([("2026-11-02", rows)])
    check = audit.check_price_row_integrity(summary)
    assert check["status"] == PASS
    assert check["evidence"]["open_zero_and_high_zero_share"] == 0.5


def test_zero_price_check_is_unknown_when_prices_were_not_read():
    summary = audit.summarize_panel([("2026-11-02", [("A", "2026-11-02")])])
    check = audit.check_price_row_integrity(summary)
    assert check["status"] == UNKNOWN
    assert check["unknown_reason"]
