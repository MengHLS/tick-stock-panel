"""Seal the auction lockbox and report data readiness without reading outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date, datetime
from pathlib import Path

import polars as pl

from scripts.auction_high_open_study import _partitions, _write_json

VERSION = "auction-lockbox-readiness-v1"
LOCKBOX_START = date(2026, 10, 1)
MIN_EVENT_DAYS = 60
MIN_SIGNALS = 300
MAX_PRIMARY_TESTS = 1


def _partition_dates(root: Path) -> list[date]:
    if not root.exists():
        return []
    return sorted(
        date.fromisoformat(path.name[5:])
        for path in root.glob("date=*")
        if path.is_dir() and path.name[5:].count("-") == 2
    )


def discover_auction_dates(auction_dir: Path, start: date) -> list[date]:
    result = set(_partition_dates(auction_dir / "result"))
    preopen = set(_partition_dates(auction_dir / "preopen"))
    return sorted(day for day in result & preopen if day >= start)


def load_index_sessions(data_dir: Path, start: date, end: date) -> list[date]:
    files = _partitions(data_dir / "kline_index_daily", start, end)
    if not files:
        return []
    return (
        pl.scan_parquet(
            files,
            hive_partitioning=False,
            extra_columns="ignore",
        )
        .filter(pl.col("symbol") == "000001.SH")
        .select("date")
        .unique()
        .sort("date")
        .collect()["date"]
        .to_list()
    )


def minute_months(minute_dir: Path) -> list[str]:
    if not minute_dir.exists():
        return []
    return sorted(
        path.stem
        for path in minute_dir.glob("*.parquet")
        if len(path.stem) == 7 and path.stem[4] == "-"
    )


def factor_dates(data_dir: Path, start: date) -> tuple[list[date], list[date]]:
    daily = [day for day in _partition_dates(data_dir / "kline_daily") if day >= start]
    enriched = [
        day for day in _partition_dates(data_dir / "kline_daily_enriched")
        if day >= start
    ]
    return daily, enriched


def assess_readiness(
    *,
    auction_dates: list[date],
    sessions: list[date],
    months: set[str],
    daily_dates: list[date],
    enriched_dates: list[date],
) -> dict:
    positions = {day: index for index, day in enumerate(sessions)}
    candidates = []
    for signal_date in auction_dates:
        position = positions.get(signal_date)
        exit_date = (
            sessions[position + 5]
            if position is not None and position + 5 < len(sessions)
            else None
        )
        exit_month = exit_date.strftime("%Y-%m") if exit_date else None
        factors_ready = signal_date in daily_dates and signal_date in enriched_dates
        minute_ready = exit_month in months if exit_month else False
        candidates.append({
            "signal_date": signal_date.isoformat(),
            "exit_date": exit_date.isoformat() if exit_date else None,
            "minute_month_ready": minute_ready,
            "factors_ready": factors_ready,
            "candidate_mature": bool(exit_date and minute_ready and factors_ready),
        })
    mature_n = sum(row["candidate_mature"] for row in candidates)
    if len(auction_dates) < MIN_EVENT_DAYS:
        status = "waiting_for_more_auction_days"
    elif mature_n < MIN_EVENT_DAYS:
        status = "waiting_for_mature_outcomes"
    else:
        status = "ready_for_one_shot_evaluation"
    return {
        "status": status,
        "auction_days_available": len(auction_dates),
        "auction_days_required": MIN_EVENT_DAYS,
        "mature_candidate_days": mature_n,
        "signals_required": MIN_SIGNALS,
        "signals_observed": None,
        "outcomes_inspected": False,
        "first_auction_date": auction_dates[0].isoformat() if auction_dates else None,
        "last_auction_date": auction_dates[-1].isoformat() if auction_dates else None,
        "candidate_maturity": candidates,
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_frozen_spec(
    *,
    stability_study: Path,
    holding_study: Path,
    multifactor_study: Path,
) -> dict:
    stability = json.loads(
        (stability_study / "study.json").read_text(encoding="utf-8"),
    )
    holding = json.loads(
        (holding_study / "study.json").read_text(encoding="utf-8"),
    )
    multifactor = json.loads(
        (multifactor_study / "study.json").read_text(encoding="utf-8"),
    )
    if stability.get("version") != "auction-tail-stability-v1":
        raise ValueError("Unexpected stability-study version")
    if holding.get("version") != "auction-holding-risk-v1":
        raise ValueError("Unexpected holding-study version")
    if multifactor.get("version") != "auction-multifactor-v1":
        raise ValueError("Unexpected multifactor-study version")
    return {
        "score_band": [0.70, 0.90],
        "score_band_rule": "combined_rank >= 0.70 and combined_rank < 0.90",
        "holding_sessions": 5,
        "primary_variant": "d5_fixed",
        "bucket_quotas": holding["bucket_quotas"],
        "portfolio_defaults": holding["portfolio_defaults"],
        "risk_budget_diagnostic": holding["risk_budget"],
        "decision_gate": holding["decision_gate"]["rules"],
        "minimum_event_days": MIN_EVENT_DAYS,
        "minimum_signals": MIN_SIGNALS,
        "maximum_primary_tests": MAX_PRIMARY_TESTS,
        "factor_representatives": len(multifactor["representatives"]),
        "artifact_hashes": {
            "stability_study": _file_sha256(stability_study / "study.json"),
            "holding_study": _file_sha256(holding_study / "study.json"),
            "multifactor_study": _file_sha256(multifactor_study / "study.json"),
            "factor_representatives": _file_sha256(
                multifactor_study / "representatives.json",
            ),
        },
    }


def write_readme(path: Path, report: dict) -> None:
    readiness = report["readiness"]
    lines = [
        "# Auction prospective lockbox",
        "",
        f"Version: `{VERSION}`.",
        "",
        f"Lockbox start: `{LOCKBOX_START}`.",
        "",
        f"Status: `{readiness['status']}`.",
        "",
        f"- Auction days: {readiness['auction_days_available']} / "
        f"{readiness['auction_days_required']}",
        f"- Candidate mature days: {readiness['mature_candidate_days']}",
        f"- Signals: not inspected; require {readiness['signals_required']}",
        "- Outcomes inspected: `false`",
        "",
        "This seal must not be opened until event-day, signal and D+5 maturity gates pass.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_readiness(args: argparse.Namespace) -> dict:
    if args.output.exists():
        raise FileExistsError("Use a NEW output directory; the lockbox seal is never overwritten")
    started = time.perf_counter()
    auction_dates = discover_auction_dates(args.auction_dir, LOCKBOX_START)
    sessions = load_index_sessions(args.data_dir, LOCKBOX_START, date(2027, 12, 31))
    months = set(minute_months(args.minute_dir))
    daily_dates, enriched_dates = factor_dates(args.data_dir, LOCKBOX_START)
    readiness = assess_readiness(
        auction_dates=auction_dates,
        sessions=sessions,
        months=months,
        daily_dates=daily_dates,
        enriched_dates=enriched_dates,
    )
    frozen = load_frozen_spec(
        stability_study=args.stability_study,
        holding_study=args.holding_study,
        multifactor_study=args.multifactor_study,
    )
    report = {
        "version": VERSION,
        "lockbox_start": LOCKBOX_START.isoformat(),
        "created_at": datetime.now().isoformat(),
        "evaluation_locked": readiness["status"] != "ready_for_one_shot_evaluation",
        "frozen_spec": frozen,
        "readiness": readiness,
        "data_coverage": {
            "minute_months": sorted(months),
            "daily_factor_days": len(daily_dates),
            "enriched_factor_days": len(enriched_dates),
        },
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    args.output.mkdir(parents=True)
    _write_json(args.output / "status.json", report)
    _write_json(args.output / "manifest.json", {
        "status": "sealed",
        "version": VERSION,
        "created_at": report["created_at"],
        "evaluation_locked": report["evaluation_locked"],
        "script_sha256": _file_sha256(Path(__file__)),
    })
    write_readme(args.output / "README.md", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auction-dir", type=Path, required=True)
    parser.add_argument("--minute-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--stability-study", type=Path, required=True)
    parser.add_argument("--holding-study", type=Path, required=True)
    parser.add_argument("--multifactor-study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_readiness(args)
    print(json.dumps({
        "event": "sealed",
        "status": report["readiness"]["status"],
        "auction_days": report["readiness"]["auction_days_available"],
        "mature_days": report["readiness"]["mature_candidate_days"],
    }), flush=True)


if __name__ == "__main__":
    main()
