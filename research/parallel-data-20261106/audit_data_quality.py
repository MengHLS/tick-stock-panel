#!/usr/bin/env python3
"""Read-only data quality and coverage audit for tick-stock-panel history.

Design rules
------------
* Read only. This module never writes into the data root, never repairs a
  partition, never backfills a factor, never rewrites an industry snapshot.
* Evidence only. Every finding carries counts and a bounded sample so the claim
  can be re-checked by hand. A check that cannot be settled from local files is
  reported as ``unknown`` with an explicit reason; it is never reported as
  ``pass``.
* No fabricated history. Current point-in-time industry membership is never
  treated as historical membership, and a missing listing/delisting record is
  never inferred from the panel boundary.

Exit codes
----------
* 0  every required check passed
* 1  at least one required check failed (confirmed anomaly in local data)
* 2  no confirmed anomaly, but at least one required check is inconclusive

The check functions are pure: they consume plain summaries so that
``test_audit_data_quality.py`` can exercise them with synthetic fixtures.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

SCHEMA_VERSION = "1.0.0"

EXIT_OK = 0
EXIT_ANOMALY = 1
EXIT_INSUFFICIENT = 2

# Contract mirrored from backend/app/indicators/price_quality.py (read-only
# import avoided on purpose: that module requires polars, which is unusable on
# this host, and this audit must not couple to backend import time).
MIN_EX_FACTOR = 0.2
MAX_EX_FACTOR = 5.0

MAX_SAMPLE = 5

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def parse_iso_date(value: Any) -> date | None:
    """Best-effort ISO date parse. Returns None when the value is not a date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _sorted_sample(items: Iterable[Any], limit: int = MAX_SAMPLE) -> list[Any]:
    return sorted(items, key=lambda x: str(x))[:limit]


def _check(
    check_id: str,
    title: str,
    *,
    required: bool,
    status: str,
    evidence: dict[str, Any] | None = None,
    findings: Sequence[str] = (),
    unknown_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "title": title,
        "required": required,
        "status": status,
        "evidence": evidence or {},
        "findings": list(findings),
        "unknown_reason": unknown_reason,
    }


# --------------------------------------------------------------------------- #
# calendar
# --------------------------------------------------------------------------- #
def build_calendar(
    index_dates: Iterable[str],
    panel_dates: Iterable[str],
) -> dict[str, Any]:
    """Compare the provider index calendar with the panel partition calendar."""
    index_set = {d for d in (parse_iso_date(x) for x in index_dates) if d}
    panel_set = {d for d in (parse_iso_date(x) for x in panel_dates) if d}

    if not index_set:
        return {
            "source": "kline_index_daily_partition_names",
            "available": False,
            "trading_days": sorted(panel_set),
            "trading_day_set": panel_set,
            "missing_from_panel": [],
            "extra_in_panel": [],
            "index_days": 0,
            "panel_days": len(panel_set),
        }

    window_start = min(panel_set) if panel_set else min(index_set)
    window_end = max(panel_set) if panel_set else max(index_set)

    return {
        "source": "kline_index_daily_partition_names",
        "available": True,
        "trading_days": sorted(index_set),
        "trading_day_set": index_set,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "index_days": len(index_set),
        "panel_days": len(panel_set),
        "missing_from_panel": sorted(
            d.isoformat() for d in index_set - panel_set if window_start <= d <= window_end
        ),
        "extra_in_panel": sorted(
            d.isoformat() for d in panel_set - index_set if window_start <= d <= window_end
        ),
        "panel_outside_index_range": sorted(
            d.isoformat() for d in panel_set - index_set if not (window_start <= d <= window_end)
        ),
    }


# --------------------------------------------------------------------------- #
# panel summary (streaming, O(symbols) memory)
# --------------------------------------------------------------------------- #
def summarize_panel(
    partitions: Iterable[tuple[str, Iterable[tuple[Any, Any]]]],
    calendar_days: set[date] | None = None,
) -> dict[str, Any]:
    """Summarise the daily panel.

    ``partitions`` yields ``(partition_name, rows)`` where each row is
    ``(symbol, raw_date)``. Rows are consumed partition by partition so a
    multi-million row panel never has to be held in memory at once.
    """
    calendar_lookup = calendar_days or set()

    partition_rows: dict[str, int] = {}
    partition_symbols: dict[str, int] = {}
    duplicate_rows = 0
    duplicate_sample: list[dict[str, Any]] = []
    mismatched_rows = 0
    mismatched_sample: list[dict[str, Any]] = []
    unparsable = 0
    total_rows = 0
    off_calendar_rows = 0

    # symbol -> [first_on_calendar, last_on_calendar, rows_total, rows_on_calendar]
    symbol_stats: dict[str, list[Any]] = {}

    # Only local signal for a halted session: the project treats a row whose
    # open and high are both 0 as a suspension row (see
    # backend/app/indicators/pipeline.py). There is no independent suspension
    # calendar, so counting these rows is the whole evidence base.
    price_rows = {
        "rows_with_prices": 0,
        "open_zero_and_high_zero": 0,
        "open_zero_only": 0,
        "high_zero_only": 0,
        "negative_price_rows": 0,
    }

    for partition_name, rows in partitions:
        part_date = parse_iso_date(partition_name)
        seen: set[str] = set()
        part_dups = 0
        part_row_count = 0

        for row in rows:
            symbol, raw_date = row[0], row[1]
            part_row_count += 1
            total_rows += 1
            if len(row) >= 4:
                open_value, high_value = row[2], row[3]
                price_rows["rows_with_prices"] += 1
                open_zero = open_value is not None and float(open_value) == 0.0
                high_zero = high_value is not None and float(high_value) == 0.0
                if open_zero and high_zero:
                    price_rows["open_zero_and_high_zero"] += 1
                elif open_zero:
                    price_rows["open_zero_only"] += 1
                elif high_zero:
                    price_rows["high_zero_only"] += 1
                if (open_value is not None and float(open_value) < 0) or (
                    high_value is not None and float(high_value) < 0
                ):
                    price_rows["negative_price_rows"] += 1
            row_date = parse_iso_date(raw_date)
            if row_date is None:
                unparsable += 1
            elif part_date is not None and row_date != part_date:
                mismatched_rows += 1
                if len(mismatched_sample) < MAX_SAMPLE:
                    mismatched_sample.append(
                        {"partition": partition_name, "symbol": symbol, "row_date": row_date.isoformat()}
                    )

            if symbol in seen:
                part_dups += 1
                if len(duplicate_sample) < MAX_SAMPLE:
                    duplicate_sample.append({"partition": partition_name, "symbol": symbol})
            else:
                seen.add(symbol)

            on_calendar = row_date is not None and (not calendar_lookup or row_date in calendar_lookup)
            if not on_calendar:
                off_calendar_rows += 1

            stat = symbol_stats.get(symbol)
            if stat is None:
                symbol_stats[symbol] = [None, None, 1, 1 if on_calendar else 0]
                if on_calendar:
                    symbol_stats[symbol][0] = row_date
                    symbol_stats[symbol][1] = row_date
                continue

            stat[2] += 1
            if on_calendar:
                stat[3] += 1
                if stat[0] is None or row_date < stat[0]:
                    stat[0] = row_date
                if stat[1] is None or row_date > stat[1]:
                    stat[1] = row_date

        duplicate_rows += part_dups
        partition_rows[partition_name] = part_row_count
        partition_symbols[partition_name] = len(seen)

    return {
        "partition_count": len(partition_rows),
        "row_count": total_rows,
        "symbol_count": len(symbol_stats),
        "duplicate_symbol_rows": duplicate_rows,
        "duplicate_sample": duplicate_sample,
        "row_partition_date_mismatch": mismatched_rows,
        "row_partition_date_mismatch_sample": mismatched_sample,
        "unparsable_row_dates": unparsable,
        "rows_off_calendar": off_calendar_rows,
        "price_rows": price_rows,
        "partition_rows": partition_rows,
        "partition_symbols": partition_symbols,
        "symbol_stats": symbol_stats,
    }


# --------------------------------------------------------------------------- #
# individual checks
# --------------------------------------------------------------------------- #
def check_panel_partition_integrity(
    summary: dict[str, Any],
    *,
    calendar_days: set[date],
    as_of: date,
) -> dict[str, Any]:
    partition_dates = {
        d for d in (parse_iso_date(p) for p in summary["partition_rows"]) if d is not None
    }
    bad_names = sorted(p for p in summary["partition_rows"] if parse_iso_date(p) is None)
    non_trading = sorted(d.isoformat() for d in partition_dates - calendar_days) if calendar_days else []
    future = sorted(d.isoformat() for d in partition_dates if d > as_of)

    findings: list[str] = []
    if summary["duplicate_symbol_rows"]:
        findings.append(f"{summary['duplicate_symbol_rows']} duplicate symbol rows inside a partition")
    if summary["row_partition_date_mismatch"]:
        findings.append(
            f"{summary['row_partition_date_mismatch']} rows carry a date different from their partition"
        )
    if summary["unparsable_row_dates"]:
        findings.append(f"{summary['unparsable_row_dates']} rows have an unparsable date")
    if bad_names:
        findings.append(f"{len(bad_names)} partition directories are not ISO dates")
    if non_trading:
        findings.append(f"{len(non_trading)} partitions are not trading days on the index calendar")
    if future:
        findings.append(f"{len(future)} future partitions dated after as_of")

    failed = bool(findings)
    status = STATUS_FAIL if failed else (STATUS_PASS if calendar_days else STATUS_UNKNOWN)

    return _check(
        "panel_partition_integrity",
        "daily panel partitions, duplicate rows, row/partition date agreement",
        required=True,
        status=status,
        evidence={
            "partitions": summary["partition_count"],
            "rows": summary["row_count"],
            "symbols": summary["symbol_count"],
            "duplicate_symbol_rows": summary["duplicate_symbol_rows"],
            "duplicate_sample": summary["duplicate_sample"],
            "row_partition_date_mismatch": summary["row_partition_date_mismatch"],
            "row_partition_date_mismatch_sample": summary["row_partition_date_mismatch_sample"],
            "unparsable_row_dates": summary["unparsable_row_dates"],
            "partitions_not_iso_date": bad_names[:MAX_SAMPLE],
            "partitions_off_calendar": non_trading,
            "future_partitions": future,
            "rows_off_calendar": summary["rows_off_calendar"],
            "as_of": as_of.isoformat(),
        },
        findings=findings,
        unknown_reason=None if calendar_days else "no calendar available to judge off-calendar partitions",
    )


def check_price_row_integrity(summary: dict[str, Any]) -> dict[str, Any]:
    """Zero-price rows: the only local marker of a halted session.

    The project filters a daily row as "suspended" when open and high are both
    0. That convention is the only suspension signal in the local data, so this
    check quantifies it and flags the rows that break its own shape.
    """
    price_rows = summary.get("price_rows") or {}
    with_prices = int(price_rows.get("rows_with_prices") or 0)
    both_zero = int(price_rows.get("open_zero_and_high_zero") or 0)
    open_only = int(price_rows.get("open_zero_only") or 0)
    high_only = int(price_rows.get("high_zero_only") or 0)
    negative = int(price_rows.get("negative_price_rows") or 0)

    findings: list[str] = []
    if open_only or high_only:
        findings.append(
            f"{open_only + high_only} rows have exactly one of open/high at zero, which the local "
            "suspension convention does not cover"
        )
    if negative:
        findings.append(f"{negative} rows carry a negative open or high")

    if not with_prices:
        return _check(
            "price_row_integrity",
            "zero-price rows versus the local suspension convention",
            required=True,
            status=STATUS_UNKNOWN,
            evidence={"rows_with_prices": 0},
            unknown_reason="price columns were not read, so the suspension-shaped rows could not be counted",
        )

    return _check(
        "price_row_integrity",
        "zero-price rows versus the local suspension convention",
        required=True,
        status=STATUS_FAIL if findings else STATUS_PASS,
        evidence={
            "rows_with_prices": with_prices,
            "open_zero_and_high_zero": both_zero,
            "open_zero_and_high_zero_share": round(both_zero / with_prices, 6),
            "open_zero_only": open_only,
            "high_zero_only": high_only,
            "negative_price_rows": negative,
            "convention": "a daily row is treated as suspended when open == 0 and high == 0",
            "note": "this is a value convention on rows that exist; it says nothing about a "
            "trading day for which the symbol has no row at all",
        },
        findings=findings,
    )


def check_calendar_coverage(calendar: dict[str, Any]) -> dict[str, Any]:
    if not calendar.get("available"):
        return _check(
            "calendar_coverage",
            "index trading calendar versus panel partition dates",
            required=True,
            status=STATUS_UNKNOWN,
            evidence={"calendar_source": calendar.get("source")},
            unknown_reason="no index calendar partition found; panel completeness cannot be proven from the panel itself",
        )

    missing = calendar["missing_from_panel"]
    extra = calendar["extra_in_panel"]
    findings: list[str] = []
    if missing:
        findings.append(f"{len(missing)} index trading days have no panel partition")
    if extra:
        findings.append(f"{len(extra)} panel partitions are not index trading days")
    if calendar["panel_outside_index_range"]:
        findings.append(
            f"{len(calendar['panel_outside_index_range'])} panel partitions fall outside the index calendar range"
        )

    return _check(
        "calendar_coverage",
        "index trading calendar versus panel partition dates",
        required=True,
        status=STATUS_FAIL if findings else STATUS_PASS,
        evidence={
            "calendar_source": calendar["source"],
            "window_start": calendar.get("window_start"),
            "window_end": calendar.get("window_end"),
            "index_days": calendar["index_days"],
            "panel_days": calendar["panel_days"],
            "missing_from_panel": missing[:MAX_SAMPLE],
            "missing_from_panel_count": len(missing),
            "extra_in_panel": extra[:MAX_SAMPLE],
            "extra_in_panel_count": len(extra),
            "note": "both sides come from the same provider, so this proves internal agreement, not exchange truth",
        },
        findings=findings,
    )


def check_enriched_parity(
    panel_partitions: Iterable[str],
    enriched_partitions: Iterable[str],
) -> dict[str, Any]:
    panel = {p for p in panel_partitions}
    enriched = {p for p in enriched_partitions}
    only_panel = sorted(panel - enriched)
    only_enriched = sorted(enriched - panel)
    findings = []
    if only_panel:
        findings.append(f"{len(only_panel)} daily partitions have no enriched counterpart")
    if only_enriched:
        findings.append(f"{len(only_enriched)} enriched partitions have no raw daily counterpart")

    return _check(
        "enriched_parity",
        "raw daily partitions versus adjusted (enriched) partitions",
        required=True,
        status=STATUS_FAIL if findings else STATUS_PASS,
        evidence={
            "panel_partitions": len(panel),
            "enriched_partitions": len(enriched),
            "only_in_panel": only_panel[:MAX_SAMPLE],
            "only_in_enriched": only_enriched[:MAX_SAMPLE],
            "only_in_panel_count": len(only_panel),
            "only_in_enriched_count": len(only_enriched),
        },
        findings=findings,
    )


def check_adj_factors(
    records: Sequence[dict[str, Any]],
    *,
    panel_symbols: Iterable[str],
    as_of: date,
) -> dict[str, Any]:
    seen: dict[tuple[str, date], float] = {}
    duplicates: list[str] = []
    conflicts: list[str] = []
    duplicate_count = 0
    conflict_count = 0
    invalid: list[dict[str, Any]] = []
    future: list[str] = []
    unparsable = 0
    min_factor: float | None = None
    max_factor: float | None = None
    factor_symbols: set[str] = set()
    dates: list[date] = []

    for rec in records:
        symbol = rec.get("symbol")
        trade_date = parse_iso_date(rec.get("trade_date"))
        value = rec.get("ex_factor")
        if symbol is None or trade_date is None:
            unparsable += 1
            continue
        factor_symbols.add(str(symbol))
        dates.append(trade_date)
        if trade_date > as_of and len(future) < MAX_SAMPLE:
            future.append(f"{symbol}@{trade_date.isoformat()}")

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            if len(invalid) < MAX_SAMPLE:
                invalid.append({"symbol": symbol, "trade_date": trade_date.isoformat(), "value": str(value)})
            continue

        if numeric != numeric or numeric in (float("inf"), float("-inf")):
            if len(invalid) < MAX_SAMPLE:
                invalid.append({"symbol": symbol, "trade_date": trade_date.isoformat(), "value": str(numeric)})
            continue
        if numeric < MIN_EX_FACTOR or numeric > MAX_EX_FACTOR:
            if len(invalid) < MAX_SAMPLE:
                invalid.append({"symbol": symbol, "trade_date": trade_date.isoformat(), "value": numeric})
            continue

        min_factor = numeric if min_factor is None else min(min_factor, numeric)
        max_factor = numeric if max_factor is None else max(max_factor, numeric)

        key = (str(symbol), trade_date)
        if key in seen:
            if abs(seen[key] - numeric) > 1e-12:
                conflict_count += 1
                if len(conflicts) < MAX_SAMPLE:
                    conflicts.append(f"{symbol}@{trade_date.isoformat()}")
            else:
                duplicate_count += 1
                if len(duplicates) < MAX_SAMPLE:
                    duplicates.append(f"{symbol}@{trade_date.isoformat()}")
            continue
        seen[key] = numeric

    panel_symbol_set = {str(s) for s in panel_symbols}
    without_factor = sorted(panel_symbol_set - factor_symbols)
    factor_only = sorted(factor_symbols - panel_symbol_set)

    findings: list[str] = []
    if duplicate_count:
        findings.append(f"{duplicate_count} exact duplicate factor rows (symbol, trade_date)")
    if conflict_count:
        findings.append(f"{conflict_count} conflicting factor values for one (symbol, trade_date)")
    if invalid:
        findings.append(f"{len(invalid)}+ factor values outside the {MIN_EX_FACTOR}..{MAX_EX_FACTOR} contract or non-finite")
    if future:
        findings.append(f"{len(future)}+ factor rows dated after as_of")
    if unparsable:
        findings.append(f"{unparsable} factor rows have an unparsable symbol or trade_date")

    unknown_reason = None
    if without_factor:
        unknown_reason = (
            "factor rows are event based; without a corporate-action ledger a symbol with no "
            "factor row cannot be proven to have had no adjustment event"
        )

    return _check(
        "adj_factor_integrity",
        "adjustment factor duplicates, conflicts, value contract and panel alignment",
        required=True,
        status=STATUS_FAIL if findings else STATUS_PASS,
        evidence={
            "rows": len(records),
            "distinct_symbols": len(factor_symbols),
            "native_rows": len(seen),
            "date_min": min(dates).isoformat() if dates else None,
            "date_max": max(dates).isoformat() if dates else None,
            "ex_factor_min": min_factor,
            "ex_factor_max": max_factor,
            "contract": f"{MIN_EX_FACTOR} <= ex_factor <= {MAX_EX_FACTOR}",
            "duplicate_pairs": duplicate_count,
            "duplicate_sample": duplicates,
            "conflicting_pairs": conflict_count,
            "conflicting_sample": conflicts,
            "invalid_values": len(invalid),
            "invalid_sample": invalid,
            "future_rows": len(future),
            "future_sample": future,
            "panel_symbols_without_factor": len(without_factor),
            "panel_symbols_without_factor_sample": without_factor[:MAX_SAMPLE],
            "factor_symbols_not_in_panel": len(factor_only),
            "factor_symbols_not_in_panel_sample": factor_only[:MAX_SAMPLE],
            "as_of": as_of.isoformat(),
        },
        findings=findings,
        unknown_reason=unknown_reason,
    )


def check_st_history(
    records: Sequence[dict[str, Any]],
    *,
    calendar_days: set[date],
    window_start: date | None,
    window_end: date | None,
) -> dict[str, Any]:
    seen: dict[tuple[str, date], str] = {}
    conflicts: list[str] = []
    dates: list[date] = []
    symbols: set[str] = set()
    unparsable = 0

    for rec in records:
        symbol = rec.get("symbol")
        flag_date = parse_iso_date(rec.get("flag_date"))
        flag = rec.get("st_flag")
        if symbol is None or flag_date is None:
            unparsable += 1
            continue
        symbols.add(str(symbol))
        dates.append(flag_date)
        key = (str(symbol), flag_date)
        if key in seen and str(seen[key]) != str(flag):
            if len(conflicts) < MAX_SAMPLE:
                conflicts.append(f"{symbol}@{flag_date.isoformat()}")
        seen[key] = flag

    flag_days = {d for d in dates}
    window_days = sorted(
        d for d in calendar_days if (window_start is None or d >= window_start) and (window_end is None or d <= window_end)
    )
    missing_days = [d.isoformat() for d in window_days if d not in flag_days]
    first_flag = min(dates) if dates else None
    last_flag = max(dates) if dates else None
    before_first = sum(1 for d in window_days if first_flag is not None and d < first_flag)
    after_last = sum(1 for d in window_days if last_flag is not None and d > last_flag)

    findings: list[str] = []
    if conflicts:
        findings.append(f"{len(conflicts)}+ conflicting st_flag values for one (symbol, flag_date)")
    if unparsable:
        findings.append(f"{unparsable} st_history rows have an unparsable symbol or flag_date")

    unknown_reason = None
    if missing_days:
        unknown_reason = (
            "st_history rows exist only on change dates; trading days with no row cannot be "
            "distinguished between 'not ST' and 'state not recorded' without a per-day state table"
        )

    return _check(
        "st_history_integrity",
        "historical ST flag table: conflicts and per-trading-day coverage",
        required=True,
        status=STATUS_FAIL if findings else STATUS_PASS,
        evidence={
            "rows": len(records),
            "distinct_symbols": len(symbols),
            "date_min": min(dates).isoformat() if dates else None,
            "date_max": max(dates).isoformat() if dates else None,
            "flag_days": len(flag_days),
            "trading_days_in_window": len(window_days),
            "trading_days_without_state": len(missing_days),
            "trading_days_before_first_flag": before_first,
            "trading_days_after_last_flag": after_last,
            "trading_days_without_state_sample": missing_days[:MAX_SAMPLE],
            "conflicting_flags": len(conflicts),
            "conflicting_sample": conflicts,
        },
        findings=findings,
        unknown_reason=unknown_reason,
    )


def check_instruments(
    records: Sequence[dict[str, Any]],
    *,
    panel_symbols: Iterable[str],
    panel_window_start: date | None,
    truncated_symbols: Iterable[str] = (),
) -> dict[str, Any]:
    as_of_values: set[str] = set()
    missing_listing: list[str] = []
    symbols: set[str] = set()
    listing_by_symbol: dict[str, date] = {}
    listed_on_or_before_start: list[str] = []

    for rec in records:
        symbol = rec.get("symbol")
        if symbol is None:
            continue
        symbols.add(str(symbol))
        if rec.get("as_of") is not None:
            as_of_values.add(str(rec["as_of"])[:19])
        listing = parse_iso_date(rec.get("listing_date"))
        if listing is None:
            missing_listing.append(str(symbol))
            continue
        listing_by_symbol[str(symbol)] = listing
        if panel_window_start is not None and listing <= panel_window_start:
            listed_on_or_before_start.append(str(symbol))

    panel_symbol_set = {str(s) for s in panel_symbols}
    missing_from_instruments = sorted(panel_symbol_set - symbols)

    truncated = [str(s) for s in truncated_symbols]
    already_listed = [
        s for s in truncated if s in listing_by_symbol and listing_by_symbol[s] < (panel_window_start or date.max)
    ]
    bars_before_listing = [
        s for s in truncated if s in listing_by_symbol and listing_by_symbol[s] > (panel_window_start or date.min)
    ]

    findings: list[str] = []
    if missing_listing:
        findings.append(f"{len(missing_listing)} instruments rows have no usable listing_date")
    if bars_before_listing:
        findings.append(
            f"{len(bars_before_listing)} symbols have a daily bar dated before their recorded listing_date"
        )
    unknown_reason = None
    if missing_from_instruments:
        unknown_reason = (
            "panel symbols absent from the instrument snapshot have no local listing metadata; "
            "their lifecycle cannot be verified from this project"
        )

    return _check(
        "instruments_snapshot_integrity",
        "current instrument snapshot: as_of, listing dates, panel membership",
        required=True,
        status=STATUS_FAIL if findings else STATUS_PASS,
        evidence={
            "rows": len(records),
            "distinct_symbols": len(symbols),
            "as_of_values": sorted(as_of_values)[:MAX_SAMPLE],
            "missing_listing_date": len(missing_listing),
            "missing_listing_date_sample": sorted(missing_listing)[:MAX_SAMPLE],
            "listed_on_or_before_panel_start": len(listed_on_or_before_start),
            "panel_symbols_not_in_instruments": len(missing_from_instruments),
            "panel_symbols_not_in_instruments_sample": missing_from_instruments[:MAX_SAMPLE],
            "panel_start_truncated_symbols": len(truncated),
            "panel_start_truncated_with_earlier_listing": len(already_listed),
            "panel_start_truncated_with_earlier_listing_sample": sorted(already_listed)[:MAX_SAMPLE],
            "bars_before_listing_date": len(bars_before_listing),
            "bars_before_listing_date_sample": sorted(bars_before_listing)[:MAX_SAMPLE],
            "note": "a single snapshot describes today; it is not a historical membership table",
        },
        findings=findings,
        unknown_reason=unknown_reason,
    )


def resolve_industry_columns(column_names: Sequence[str]) -> tuple[str | None, str | None]:
    """Resolve the symbol and industry columns of a THS point-in-time snapshot.

    The snapshot mixes raw vendor headers (股票代码 / 股票简称 / 所属同花顺行业)
    with canonical ones (symbol / code / date). The industry column is picked by
    meaning, not by position: an explicit 行业/industry match wins, and only when
    no such header exists does it fall back to the first remaining column.
    """
    names = list(column_names)
    symbol_col = "symbol" if "symbol" in names else None
    ignored = {"symbol", "code", "date", "股票代码", "股票名称", "股票简称"}
    candidates = [n for n in names if n not in ignored]
    industry_col = next((n for n in candidates if ("行业" in n or "industry" in n.lower())), None)
    if industry_col is None and candidates:
        industry_col = candidates[0]
    return symbol_col, industry_col


def check_industry_pit(
    snapshots: dict[str, Sequence[dict[str, Any]]],
    *,
    industry_col: str | None,
    calendar_days: set[date],
    panel_dates: set[date],
    as_of: date,
) -> list[dict[str, Any]]:
    """Integrity, calendar alignment and history depth of industry snapshots."""
    snapshot_dates = {d for d in (parse_iso_date(k) for k in snapshots) if d is not None}
    bad_names = sorted(k for k in snapshots if parse_iso_date(k) is None)

    duplicates = 0
    conflicts = 0
    conflict_sample: list[str] = []
    per_day_symbols: dict[str, int] = {}
    empty_days: list[str] = []
    membership: dict[str, set[str]] = {}

    for day_name, rows in snapshots.items():
        seen: dict[str, str] = {}
        symbols: set[str] = set()
        for rec in rows:
            symbol = rec.get("__symbol__")
            industry = rec.get("__industry__") if industry_col else None
            if symbol is None:
                continue
            symbols.add(str(symbol))
            if industry is None:
                continue
            key = str(symbol)
            if key in seen:
                if str(seen[key]) != str(industry):
                    conflicts += 1
                    if len(conflict_sample) < MAX_SAMPLE:
                        conflict_sample.append(f"{key}@{day_name}")
                else:
                    duplicates += 1
            seen[key] = str(industry)
        per_day_symbols[day_name] = len(symbols)
        membership[day_name] = symbols
        if not symbols:
            empty_days.append(day_name)

    off_calendar = sorted(d.isoformat() for d in snapshot_dates - calendar_days) if calendar_days else []
    future = sorted(d.isoformat() for d in snapshot_dates if d > as_of)

    integrity_findings: list[str] = []
    if duplicates:
        integrity_findings.append(f"{duplicates} duplicate symbol rows inside one industry snapshot")
    if conflicts:
        integrity_findings.append(f"{conflicts} symbols carry two different industries on one snapshot day")
    if bad_names:
        integrity_findings.append(f"{len(bad_names)} snapshot directories are not ISO dates")
    if empty_days:
        integrity_findings.append(f"{len(empty_days)} snapshot partitions are empty")
    if future:
        integrity_findings.append(f"{len(future)} snapshot partitions are dated after as_of")

    integrity = _check(
        "industry_pit_integrity",
        "industry snapshot duplicates, conflicts, empty and future partitions",
        required=True,
        status=STATUS_FAIL if integrity_findings else STATUS_PASS,
        evidence={
            "snapshot_days": len(snapshot_dates),
            "date_min": min(snapshot_dates).isoformat() if snapshot_dates else None,
            "date_max": max(snapshot_dates).isoformat() if snapshot_dates else None,
            "symbols_per_day": dict(sorted(per_day_symbols.items())),
            "duplicate_rows": duplicates,
            "conflicting_symbol_days": conflicts,
            "conflicting_sample": conflict_sample,
            "partitions_not_iso_date": bad_names[:MAX_SAMPLE],
            "empty_partitions": empty_days[:MAX_SAMPLE],
            "future_partitions": future,
            "industry_column": industry_col,
        },
        findings=integrity_findings,
    )

    align_findings: list[str] = []
    if off_calendar:
        align_findings.append(
            f"{len(off_calendar)} industry snapshots are dated on non-trading days; a daily join would "
            "inject a pseudo trading date"
        )
    alignment = _check(
        "industry_pit_calendar_alignment",
        "industry snapshot dates versus trading calendar",
        required=True,
        status=STATUS_FAIL if align_findings else (STATUS_PASS if calendar_days else STATUS_UNKNOWN),
        evidence={
            "snapshot_days": len(snapshot_dates),
            "non_trading_snapshot_days": off_calendar,
            "trading_snapshot_days": len(snapshot_dates & calendar_days) if calendar_days else None,
        },
        findings=align_findings,
        unknown_reason=None if calendar_days else "no trading calendar available to judge snapshot dates",
    )

    usable_days = snapshot_dates & panel_dates
    ratio = (len(usable_days) / len(panel_dates)) if panel_dates else 0.0
    depth_findings: list[str] = []
    if ratio < 0.9:
        depth_findings.append(
            f"industry snapshots cover {len(usable_days)} of {len(panel_dates)} panel trading days "
            f"({ratio:.2%}); a multi-year industry backtest has no point-in-time membership for the rest"
        )
    depth = _check(
        "industry_pit_history_depth",
        "industry snapshot history depth versus panel history",
        required=True,
        status=STATUS_FAIL if depth_findings else STATUS_PASS,
        evidence={
            "panel_trading_days": len(panel_dates),
            "snapshot_days_in_panel": len(usable_days),
            "coverage_ratio": round(ratio, 6),
            "available_at_column": False,
            "note": "snapshot rows carry only a date; the intraday moment the membership became "
            "knowable is not recorded anywhere in the dataset",
        },
        findings=depth_findings,
        unknown_reason=(
            "no available_at/as_of column and no vendor publication log, so intraday availability "
            "for a historical decision time is unknown"
        ),
    )

    return [integrity, alignment, depth]


def check_lifecycle(
    summary: dict[str, Any],
    calendar: dict[str, Any],
    *,
    has_suspension_table: bool,
    window_start: date | None = None,
    window_end: date | None = None,
) -> dict[str, Any]:
    trading_days: list[date] = list(calendar.get("trading_days") or [])
    index_of = {d: i for i, d in enumerate(trading_days)}
    if window_start is None and trading_days:
        window_start = trading_days[0]
    if window_end is None and trading_days:
        window_end = trading_days[-1]

    stats = summary["symbol_stats"]
    truncated: list[str] = []
    stale: list[str] = []
    gappy: list[dict[str, Any]] = []
    total_missing = 0
    no_calendar_rows: list[str] = []

    for symbol, stat in stats.items():
        first, last, rows_total, rows_on_cal = stat
        if first is None or last is None:
            no_calendar_rows.append(str(symbol))
            continue
        if window_start is not None and first <= window_start:
            truncated.append(str(symbol))
        if window_end is not None and last < window_end:
            stale.append(str(symbol))
        if first in index_of and last in index_of:
            expected = index_of[last] - index_of[first] + 1
            gap = expected - int(rows_on_cal)
            if gap > 0:
                total_missing += gap
                gappy.append(
                    {
                        "symbol": str(symbol),
                        "first": first.isoformat(),
                        "last": last.isoformat(),
                        "rows": int(rows_on_cal),
                        "expected_trading_days": expected,
                        "missing_trading_days": gap,
                    }
                )

    gappy.sort(key=lambda r: (-r["missing_trading_days"], r["symbol"]))
    stale.sort()

    findings: list[str] = []
    if total_missing:
        findings.append(
            f"{len(gappy)} symbols have at least one trading-day hole inside their own first/last span "
            f"({total_missing} symbol-days in total)"
        )
    if stale:
        findings.append(f"{len(stale)} symbols stop updating before the panel's last trading day")

    unknown_reason = None
    if total_missing or stale:
        unknown_reason = (
            "no local suspension table and no authoritative listing/delisting record; a hole or an "
            "early stop cannot be attributed to suspension, delisting or a real gap"
        )

    return _check(
        "security_lifecycle_coverage",
        "per-symbol first/last date, stale tails and interior holes",
        required=True,
        status=STATUS_FAIL if (findings and has_suspension_table) else (STATUS_UNKNOWN if unknown_reason else STATUS_PASS),
        evidence={
            "symbols": len(stats),
            "symbols_truncated_at_window_start": len(truncated),
            "symbols_truncated_at_window_start_sample": sorted(truncated)[:MAX_SAMPLE],
            "symbols_stale_before_window_end": len(stale),
            "symbols_stale_before_window_end_sample": stale[:20],
            "symbols_with_holes": len(gappy),
            "total_missing_symbol_days": total_missing,
            "worst_holes": gappy[:20],
            "suspension_table_available": has_suspension_table,
            "note": "first date == panel start means truncation or listing; local data cannot "
            "separate the two without a listing record",
        },
        findings=findings,
        unknown_reason=unknown_reason,
    )


def build_backtest_suitability(checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    def status_of(check_id: str) -> str:
        return checks[check_id]["status"]

    panel_ok = status_of("panel_partition_integrity") in (STATUS_PASS,) and status_of("calendar_coverage") in (
        STATUS_PASS,
        STATUS_UNKNOWN,
    )

    lifecycle_evidence = checks["security_lifecycle_coverage"]["evidence"]
    holes = lifecycle_evidence.get("total_missing_symbol_days")
    stale = lifecycle_evidence.get("symbols_stale_before_window_end")
    no_factor = checks["adj_factor_integrity"]["evidence"].get("panel_symbols_without_factor")

    cross_section_unknowns: list[str] = []
    if no_factor is not None:
        cross_section_unknowns.append(
            f"adjustment factor completeness: {no_factor} panel symbols carry no factor row at all"
        )
    elif checks["adj_factor_integrity"]["unknown_reason"]:
        cross_section_unknowns.append("adjustment factor completeness per symbol")
    cross_section_unknowns.append(
        "completeness of the historical symbol universe over time: there is no delisting record "
        "set, so survivorship bias cannot be ruled out"
    )
    holes_text = (
        f"{holes} missing symbol-days" if holes is not None else "symbol-days missing from the panel"
    )
    stale_text = (
        f"{stale} symbols that stop updating before the panel ends"
        if stale is not None
        else "symbols that stop updating before the panel ends"
    )
    cross_section_unknowns.append(
        f"attribution of {holes_text} and {stale_text}: without a suspension table the cause of a "
        "hole is unknown, and a suspension is only one of the possible causes"
    )
    cross_section_unknowns.append(
        "execution feasibility and liquidity: turnover, limit-up/limit-down tradability and capacity "
        "are not audited here"
    )

    cross_section: dict[str, Any] = {
        "supported": False,
        "permitted_use": "exploratory_research_only",
        "integrity_checks_pass": panel_ok,
        "statement": (
            "local consistency checks pass, but this is not a data-availability verdict: it permits "
            "only exploratory daily cross-section research over the audited window, with every unknown "
            "below declared in writing; any conclusion that omits them is unsupported by this evidence"
        ),
        "unknowns": cross_section_unknowns,
    }

    delisted: dict[str, Any] = {
        "supported": False,
        "reason": "no delisting record set; the panel's symbol universe over time cannot be proven complete",
    }
    if checks["security_lifecycle_coverage"]["status"] == STATUS_PASS:
        delisted = {"supported": True, "reason": "lifecycle check passed"}

    suspension: dict[str, Any] = {
        "supported": False,
        "reason": "no suspension table; execution cannot be modelled around halted days",
    }

    industry: dict[str, Any] = {
        "supported": status_of("industry_pit_history_depth") == STATUS_PASS
        and status_of("industry_pit_calendar_alignment") == STATUS_PASS,
        "reason": (
            "industry point-in-time snapshots start at "
            f"{checks['industry_pit_integrity']['evidence'].get('date_min')} and cover "
            f"{checks['industry_pit_history_depth']['evidence'].get('coverage_ratio')} of panel days"
        ),
    }

    adjustment_rebuild: dict[str, Any] = {
        "supported": status_of("adj_factor_integrity") == STATUS_PASS,
        "unknowns": [],
    }
    if checks["adj_factor_integrity"]["unknown_reason"]:
        adjustment_rebuild["unknowns"].append("economic correctness of factors without a corporate-action ledger")

    return {
        "daily_cross_section_backtest": cross_section,
        "delisted_universe_backtest": delisted,
        "suspension_aware_execution": suspension,
        "historical_industry_rotation": industry,
        "adjustment_rebuild": adjustment_rebuild,
    }


def derive_exit_code(checks: Sequence[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    required = [c for c in checks if c["required"]]
    failed = [c["id"] for c in required if c["status"] == STATUS_FAIL]
    unknown = [c["id"] for c in required if c["status"] == STATUS_UNKNOWN]
    if failed:
        code, verdict = EXIT_ANOMALY, "anomaly_detected"
    elif unknown:
        code, verdict = EXIT_INSUFFICIENT, "insufficient_evidence"
    else:
        code, verdict = EXIT_OK, "passed"
    return code, {
        "verdict": verdict,
        "exit_code": code,
        "required_failed": failed,
        "required_unknown": unknown,
        "required_total": len(required),
    }


# --------------------------------------------------------------------------- #
# disk loading (read only)
# --------------------------------------------------------------------------- #
def _read_table(path: Path, columns: Sequence[str]):
    """Read selected columns from one parquet file.

    ``ParquetFile.read`` is used instead of ``pq.read_table`` on purpose: the
    project's partitions do not all share one physical schema (``date`` is
    ``date32`` in some partitions and dictionary-encoded string in others), and
    the dataset reader would try to unify them and fail. A row-level audit must
    tolerate that spread, so each file is decoded on its own and the values are
    normalised by ``parse_iso_date`` later.
    """
    import pyarrow.parquet as pq

    handle = pq.ParquetFile(path)
    present = [c for c in columns if c in set(handle.schema_arrow.names)]
    if not present:
        return None
    return handle.read(columns=present)


def _read_columns(path: Path, columns: Sequence[str]) -> list[dict[str, Any]]:
    table = _read_table(path, columns)
    return [] if table is None else table.to_pylist()


def iter_panel_partitions(data_root: Path) -> Iterator[tuple[str, list[tuple[Any, Any]]]]:
    base = data_root / "kline_daily"
    for part in sorted(base.glob("date=*")):
        rows: list[tuple[Any, Any]] = []
        for file in sorted(part.glob("*.parquet")):
            table = _read_table(file, ["symbol", "date", "open", "high"])
            if table is None:
                continue
            columns = [table.column(name).to_pylist() for name in table.column_names]
            rows.extend(zip(*columns))
        yield part.name[len("date=") :], rows


def load_industry_snapshots(data_root: Path) -> tuple[dict[str, list[dict[str, Any]]], str | None]:
    base = data_root / "ext_data" / "ext_hy_ths_pit" / "timeseries"
    snapshots: dict[str, list[dict[str, Any]]] = {}
    industry_col: str | None = None
    for part in sorted(base.glob("date=*")):
        rows: list[dict[str, Any]] = []
        for file in sorted(part.glob("*.parquet")):
            handle_symbols, col = resolve_industry_columns(_schema_names(file))
            table = _read_table(file, [c for c in (handle_symbols, col) if c])
            if table is None or handle_symbols is None:
                continue
            if industry_col is None:
                industry_col = col
            symbols = table.column(handle_symbols).to_pylist()
            industries = table.column(col).to_pylist() if col else [None] * len(symbols)
            rows.extend(
                {"__symbol__": s, "__industry__": i} for s, i in zip(symbols, industries)
            )
        snapshots[part.name[len("date=") :]] = rows
    return snapshots, industry_col


def _schema_names(path: Path) -> list[str]:
    import pyarrow.parquet as pq

    return pq.ParquetFile(path).schema_arrow.names


def run_audit(data_root: Path, *, as_of: date, verbose: bool = False) -> dict[str, Any]:
    def say(message: str) -> None:
        if verbose:
            print(message, file=sys.stderr, flush=True)

    panel_partition_names = sorted(p.name[len("date=") :] for p in (data_root / "kline_daily").glob("date=*"))
    enriched_partition_names = sorted(
        p.name[len("date=") :] for p in (data_root / "kline_daily_enriched").glob("date=*")
    )
    index_partition_names = sorted(
        p.name[len("date=") :] for p in (data_root / "kline_index_daily").glob("date=*")
    )
    say(f"panel partitions={len(panel_partition_names)} enriched={len(enriched_partition_names)} index={len(index_partition_names)}")

    calendar = build_calendar(index_partition_names, panel_partition_names)
    calendar_days = set(calendar.get("trading_day_set") or set())

    say("summarising daily panel ...")
    summary = summarize_panel(iter_panel_partitions(data_root), calendar_days=calendar_days)
    say(f"panel rows={summary['row_count']} symbols={summary['symbol_count']}")

    panel_symbols = list(summary["symbol_stats"].keys())

    adj_path = data_root / "adj_factor" / "all.parquet"
    adj_records = _read_columns(adj_path, ["symbol", "trade_date", "ex_factor"]) if adj_path.exists() else []
    say(f"adj_factor rows={len(adj_records)}")

    st_path = data_root / "st_history" / "part.parquet"
    st_records = _read_columns(st_path, ["symbol", "flag_date", "st_flag"]) if st_path.exists() else []
    say(f"st_history rows={len(st_records)}")

    inst_path = data_root / "instruments" / "instruments.parquet"
    inst_records = _read_columns(inst_path, ["symbol", "listing_date", "as_of"]) if inst_path.exists() else []

    say("loading industry snapshots ...")
    snapshots, industry_col = load_industry_snapshots(data_root)

    panel_dates = {d for d in (parse_iso_date(p) for p in panel_partition_names) if d}
    panel_min = min(panel_dates) if panel_dates else None
    panel_max = max(panel_dates) if panel_dates else None
    # Coverage questions are asked over the panel's own span, not the wider
    # index calendar span, otherwise pre-2018 index days would be counted as
    # "missing panel days" and as "trading days without ST state".
    window_start = panel_min
    window_end = panel_max

    truncated_symbols = [
        sym
        for sym, stat in summary["symbol_stats"].items()
        if stat[0] is not None and panel_min is not None and stat[0] <= panel_min
    ]

    checks: list[dict[str, Any]] = [
        check_panel_partition_integrity(summary, calendar_days=calendar_days, as_of=as_of),
        check_price_row_integrity(summary),
        check_calendar_coverage(calendar),
        check_enriched_parity(panel_partition_names, enriched_partition_names),
        check_adj_factors(adj_records, panel_symbols=panel_symbols, as_of=as_of),
        check_st_history(
            st_records,
            calendar_days=calendar_days,
            window_start=window_start,
            window_end=window_end,
        ),
        check_instruments(
            inst_records,
            panel_symbols=panel_symbols,
            panel_window_start=window_start,
            truncated_symbols=truncated_symbols,
        ),
        *check_industry_pit(
            snapshots,
            industry_col=industry_col,
            calendar_days=calendar_days,
            panel_dates=panel_dates,
            as_of=as_of,
        ),
        check_lifecycle(
            summary,
            calendar,
            has_suspension_table=False,
            window_start=window_start,
            window_end=window_end,
        ),
    ]
    by_id = {c["id"]: c for c in checks}
    exit_code, verdict = derive_exit_code(checks)

    gaps = [
        {
            "id": c["id"],
            "status": c["status"],
            "reason": (
                "; ".join(c["findings"])
                if c["status"] == STATUS_FAIL and c["findings"]
                else c["unknown_reason"] or ("; ".join(c["findings"]) or None)
            ),
        }
        for c in checks
        if c["status"] != STATUS_PASS
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().replace(microsecond=0).isoformat(),
        "audit_as_of": as_of.isoformat(),
        "data_root": str(data_root),
        "execution": {
            "python": platform.python_version(),
            "argv": sys.argv,
            "mode": "read_only",
        },
        "inputs": {
            "kline_daily": {
                "partitions": len(panel_partition_names),
                "rows": summary["row_count"],
                "symbols": summary["symbol_count"],
                "first": calendar.get("window_start"),
                "last": calendar.get("window_end"),
            },
            "kline_daily_enriched": {"partitions": len(enriched_partition_names)},
            "kline_index_daily": {"partitions": len(index_partition_names)},
            "adj_factor": {"rows": len(adj_records)},
            "st_history": {"rows": len(st_records)},
            "instruments": {"rows": len(inst_records)},
            "ext_hy_ths_pit": {
                "snapshot_days": len(snapshots),
                "industry_column": industry_col,
            },
            "suspension_table": {"present": False},
        },
        "calendar": {
            "source": calendar.get("source"),
            "available": calendar.get("available"),
            "trading_days": len(calendar.get("trading_days") or []),
        },
        "checks": checks,
        "gaps": gaps,
        "backtest_suitability": build_backtest_suitability(by_id),
        "verdict": verdict,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only data quality audit for tick-stock-panel history.")
    parser.add_argument(
        "--data-root",
        default=r"D:\TSP\data",
        help="data root containing kline_daily/, adj_factor/, instruments/, st_history/, ext_data/",
    )
    parser.add_argument("--as-of", default=None, help="audit date in ISO form; defaults to today")
    parser.add_argument(
        "--json-out",
        default="-",
        help="write the machine readable report here; '-' prints it to stdout (default)",
    )
    parser.add_argument("--verbose", action="store_true", help="progress messages on stderr")
    args = parser.parse_args(argv)

    as_of = parse_iso_date(args.as_of) if args.as_of else date.today()
    if as_of is None:
        print(f"invalid --as-of value: {args.as_of}", file=sys.stderr)
        return EXIT_INSUFFICIENT

    data_root = Path(args.data_root)
    if not (data_root / "kline_daily").is_dir():
        print(f"data root not usable (no kline_daily): {data_root}", file=sys.stderr)
        return EXIT_INSUFFICIENT

    report = run_audit(data_root, as_of=as_of, verbose=args.verbose)
    payload = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=False)

    if args.json_out in ("-", ""):
        print(payload)
    else:
        out_path = Path(args.json_out)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(payload, encoding="utf-8")
            print(f"report written: {out_path}", file=sys.stderr)
        except OSError as exc:
            print(f"report write failed ({exc}); printing to stdout instead", file=sys.stderr)
            print(payload)

    return report["verdict"]["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
