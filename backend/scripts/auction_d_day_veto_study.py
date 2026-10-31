"""Pre-registered D-day auction veto overlay for frozen walk-forward signals.

The ranked signal is unchanged. This study only removes already-selected
events before the D-day 09:30-09:35 entry when negative auction evidence is
present. Rejected candidates are not replaced by the next ranked stock.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date, datetime
from pathlib import Path

import polars as pl

from scripts.auction_high_open_study import _write_json, summarize
from scripts.auction_portfolio_construction_study import (
    PORTFOLIO_DEFAULTS,
    _with_baseline,
    load_calendar,
    load_daily_closes,
    simulate_daily_mark_portfolio,
)
from scripts.auction_walkforward_study import FOLDS, chain_portfolio_curves, load_panel

VERSION = "auction-d-day-veto-v1"
KEYS = ["symbol", "date"]
PRIMARY_VARIANT = "balanced_veto"
VARIANTS = (
    "baseline",
    "tail_signal",
    "no_sell_expansion",
    "balanced_veto",
)
AUCTION_COLUMNS = [
    "last_imbalance",
    "last_unmatched_sell_shares",
    "c0924_unmatched_sell_shares",
    "last_age_ms",
    "c0924_age_ms",
    "population_sell_expansion",
]
DECISION_GATE = {
    "primary_variant": PRIMARY_VARIANT,
    "minimum_candidate_reduction": 0.25,
    "maximum_mean_daily_candidates": 2.0,
    "mean_net_return_positive": True,
    "incremental_ci_lower_positive": True,
    "portfolio_total_return_positive": True,
    "portfolio_max_drawdown_floor": -0.15,
    "no_stale_marks": True,
}


def _finite(column: str) -> pl.Expr:
    value = pl.col(column)
    return value.is_not_null() & value.is_finite()


def add_veto_columns(frame: pl.DataFrame) -> pl.DataFrame:
    sell_data_valid = (
        _finite("last_imbalance")
        & _finite("last_unmatched_sell_shares")
        & _finite("c0924_unmatched_sell_shares")
        & pl.col("last_age_ms").is_not_null()
        & (pl.col("last_age_ms") <= 30_000)
        & pl.col("c0924_age_ms").is_not_null()
        & (pl.col("c0924_age_ms") <= 30_000)
        & pl.col("population_sell_expansion").is_not_null()
        & (pl.col("population_sell_expansion") >= 4)
    ).fill_null(False)
    sell_expansion = (
        sell_data_valid
        & (pl.col("last_unmatched_sell_shares") > pl.col("c0924_unmatched_sell_shares"))
        & (pl.col("last_imbalance") < 0)
    ).fill_null(False)
    return frame.with_columns(
        pl.col("tail_strength_signal").fill_null(False).alias("tail_signal"),
        sell_data_valid.alias("sell_data_valid"),
        sell_expansion.alias("sell_expansion"),
    )


def apply_variant(frame: pl.DataFrame, variant: str) -> pl.DataFrame:
    if variant == "baseline":
        return frame
    if variant == "tail_signal":
        return frame.filter(pl.col("tail_signal"))
    if variant == "no_sell_expansion":
        return frame.filter(
            pl.col("sell_data_valid") & ~pl.col("sell_expansion"),
        )
    if variant == "balanced_veto":
        return frame.filter(
            pl.col("tail_signal")
            & pl.col("sell_data_valid")
            & ~pl.col("sell_expansion")
            & _finite("last_imbalance")
            & (pl.col("last_imbalance") >= 0),
        )
    raise ValueError(f"Unknown veto variant: {variant}")


def load_selected(selected_path: Path, events_path: Path) -> pl.DataFrame:
    selected = pl.read_parquet(selected_path)
    duplicate = selected.select(pl.struct(KEYS).is_duplicated().any()).item()
    if duplicate:
        raise ValueError("Duplicate selected event keys")
    auction = (
        pl.scan_parquet(events_path)
        .filter(pl.col("horizon") == 3)
        .join(selected.lazy().select(KEYS), on=KEYS, how="semi")
        .select(*KEYS, *AUCTION_COLUMNS)
        .collect()
    )
    if auction.select(pl.struct(KEYS).is_duplicated().any()).item():
        raise ValueError("Duplicate auction keys")
    frame = selected.join(auction, on=KEYS, how="left")
    missing = frame.filter(pl.col("last_age_ms").is_null()).height
    if missing:
        raise ValueError(f"Selected events without auction source rows: {missing}")
    return add_veto_columns(frame)


def assign_fold(frame: pl.DataFrame) -> pl.DataFrame:
    pieces = []
    assigned = None
    for fold in FOLDS:
        mask = pl.col("date").is_between(fold["test_start"], fold["test_end"])
        piece = frame.filter(mask).with_columns(pl.lit(fold["name"]).alias("fold"))
        if piece.is_empty():
            raise ValueError(f"No selected events for {fold['name']}")
        pieces.append(piece)
        assigned = mask if assigned is None else assigned | mask
    if frame.filter(~assigned).height:
        raise ValueError("Selected events fall outside configured test folds")
    return pl.concat(pieces)


def _zero_portfolio_summary() -> dict:
    return {
        "status": "no_selected_events",
        "candidate_n": 0,
        "filled_n": 0,
        "total_return": 0.0,
        "max_drawdown_mtm": 0.0,
        "stale_marks": 0,
    }


def flatten_csv_row(row: dict) -> dict:
    return {
        key: (
            json.dumps(value, ensure_ascii=False)
            if isinstance(value, (dict, list))
            else value
        )
        for key, value in row.items()
    }


def select_variants(frame: pl.DataFrame) -> dict[str, pl.DataFrame]:
    return {variant: apply_variant(frame, variant) for variant in VARIANTS}


def event_results(
    panel: pl.DataFrame,
    variants: dict[str, pl.DataFrame],
    *,
    bootstrap_samples: int,
    seed: int,
) -> list[dict]:
    oos = panel.filter(
        pl.col("date").is_between(FOLDS[0]["test_start"], FOLDS[-1]["test_end"]),
    )
    baseline = _with_baseline(oos)
    rows = []
    for variant in VARIANTS:
        selected = variants[variant]
        exact = baseline.join(selected.select(KEYS), on=KEYS, how="semi")
        rows.append({
            "variant": variant,
            "selected_n": selected.height,
            **summarize(
                exact,
                bootstrap_samples=bootstrap_samples,
                seed=seed,
            ),
        })
    return rows


def portfolio_results(
    variants: dict[str, pl.DataFrame],
    *,
    calendar: list[date],
    daily_closes: pl.DataFrame,
) -> tuple[dict[str, dict[str, dict]], dict[str, list[dict]], dict[str, list[dict]]]:
    portfolio: dict[str, dict[str, dict]] = {}
    trades: dict[str, list[dict]] = {}
    curves: dict[str, list[dict]] = {}
    for variant in VARIANTS:
        fold_portfolios = []
        trades[variant] = []
        curves[variant] = []
        portfolio[variant] = {}
        for fold in FOLDS:
            selected = variants[variant].filter(pl.col("fold") == fold["name"])
            if selected.is_empty():
                summary = _zero_portfolio_summary()
                filled = []
                curve = []
            else:
                summary, filled, curve = simulate_daily_mark_portfolio(
                    selected,
                    calendar=calendar,
                    daily_closes=daily_closes,
                    start=fold["test_start"],
                    end=fold["test_end"],
                )
            summary["candidate_n"] = selected.height
            portfolio[variant][fold["name"]] = summary
            trades[variant].extend({"fold": fold["name"], **row} for row in filled)
            curves[variant].extend({"fold": fold["name"], **row} for row in curve)
            fold_portfolios.append({
                "name": fold["name"],
                "portfolio": summary,
                "curve": curve,
            })
        chained = chain_portfolio_curves(fold_portfolios)
        portfolio[variant]["oos"] = {
            key: value for key, value in chained.items() if key != "curve"
        }
    return portfolio, trades, curves


def decision_gate(
    variants: dict[str, pl.DataFrame],
    events: list[dict],
    portfolio: dict[str, dict[str, dict]],
    *,
    session_count: int,
) -> dict:
    baseline_n = variants["baseline"].height
    primary_n = variants[PRIMARY_VARIANT].height
    event = next(row for row in events if row["variant"] == PRIMARY_VARIANT)
    interval = (event.get("cluster_bootstrap_95") or {}).get(
        "mean_incremental_return",
    )
    result = portfolio[PRIMARY_VARIANT]["oos"]
    reduction = 1 - primary_n / baseline_n if baseline_n else 0.0
    mean_daily = primary_n / session_count if session_count else float("inf")
    checks = {
        "candidate_reduction": reduction >= DECISION_GATE["minimum_candidate_reduction"],
        "mean_daily_candidates": (
            mean_daily <= DECISION_GATE["maximum_mean_daily_candidates"]
        ),
        "mean_net_return_positive": (
            event.get("mean_net_return") is not None
            and event["mean_net_return"] > 0
        ),
        "incremental_ci_lower_positive": interval is not None and interval[0] > 0,
        "portfolio_total_return_positive": result["total_return"] > 0,
        "portfolio_max_drawdown_above_floor": (
            result["max_drawdown_mtm"] >= DECISION_GATE["portfolio_max_drawdown_floor"]
        ),
        "no_stale_marks": result["stale_marks"] == 0,
    }
    return {
        "rules": DECISION_GATE,
        "candidate_reduction": reduction,
        "mean_daily_candidates": mean_daily,
        "checks": checks,
        "passed": all(checks.values()),
    }


def write_results(path: Path, report: dict) -> None:
    lines = [
        "# D-day auction veto overlay",
        "",
        f"Algorithm: `{VERSION}`.",
        "",
        "The frozen ranked shortlist is filtered before the same-day open.",
        "Rejected candidates are not replaced by lower-ranked stocks.",
        "",
        "| Variant | Selected | Mean/day | Net | Delta | Delta 95% CI |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    sessions = report["session_count"]
    for row in report["events"]:
        interval = (row.get("cluster_bootstrap_95") or {}).get(
            "mean_incremental_return",
        )
        interval_text = (
            f"{interval[0] * 100:.3f}% to {interval[1] * 100:.3f}%"
            if interval else "NA"
        )
        lines.append(
            f"| {row['variant']} | {row['selected_n']} | "
            f"{row['selected_n'] / sessions:.3f} | "
            f"{row['mean_net_return'] * 100:.3f}% | "
            f"{row['mean_incremental_return'] * 100:.3f}% | {interval_text} |",
        )
    lines.extend([
        "",
        "| Variant | Portfolio | Max drawdown | Filled | Stale marks |",
        "|---|---:|---:|---:|---:|",
    ])
    for variant in VARIANTS:
        row = report["portfolio"][variant]["oos"]
        lines.append(
            f"| {variant} | {row['total_return'] * 100:.3f}% | "
            f"{row['max_drawdown_mtm'] * 100:.3f}% | "
            f"{row['filled_n']} | {row['stale_marks']} |",
        )
    lines.extend([
        "",
        f"Primary variant: `{PRIMARY_VARIANT}`.",
        "",
        f"Gate passed: `{report['decision_gate']['passed']}`.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_study(args: argparse.Namespace) -> dict:
    if args.output.exists():
        raise FileExistsError("Use a NEW output directory; existing runs are never overwritten")
    if args.bootstrap_samples < 0:
        raise ValueError("bootstrap_samples must be non-negative")
    started = time.perf_counter()
    selected = assign_fold(load_selected(args.selected, args.events))
    variants = select_variants(selected)
    panel, _ = load_panel(args.events, args.factor_admission, args.d5_outcomes)

    all_selected = variants["baseline"]
    symbols = sorted(set(all_selected["symbol"].to_list()))
    start_date = all_selected["date"].min()
    end_date = all_selected["exit_date"].max()
    calendar = load_calendar(args.data_dir, start_date, end_date)
    daily_closes = load_daily_closes(args.data_dir, symbols, start_date, end_date)
    session_count = sum(
        fold["test_start"] <= day <= fold["test_end"]
        for fold in FOLDS
        for day in calendar
    )
    events = event_results(
        panel,
        variants,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    portfolio, trades, curves = portfolio_results(
        variants,
        calendar=calendar,
        daily_closes=daily_closes,
    )
    gate = decision_gate(
        variants,
        events,
        portfolio,
        session_count=session_count,
    )
    elapsed = round(time.perf_counter() - started, 3)
    report = {
        "version": VERSION,
        "primary_variant": PRIMARY_VARIANT,
        "variants": VARIANTS,
        "decision_gate": gate,
        "events": events,
        "portfolio": portfolio,
        "session_count": session_count,
        "portfolio_defaults": PORTFOLIO_DEFAULTS,
        "elapsed_seconds": elapsed,
        "warnings": [
            "All veto rules use D-day 09:25 auction information only.",
            "Rejected candidates are not refilled from lower ranks.",
            "The ranked shortlist and D+5 outcomes are frozen from the prior walk-forward study.",
            "This remains quasi-out-of-sample because the historical period was previously observed.",
        ],
    }
    args.output.mkdir(parents=True)
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    _write_json(args.output / "manifest.json", {
        "status": "running",
        "version": VERSION,
        "script_sha256": script_hash,
        "parameters": vars(args),
        "created_at": datetime.now().isoformat(),
    })
    _write_json(args.output / "study.json", report)

    event_rows = [flatten_csv_row(row) for row in events]
    pl.DataFrame(event_rows, infer_schema_length=None).write_csv(
        args.output / "events.csv",
    )
    portfolio_rows = [
        flatten_csv_row({"variant": variant, "fold": fold, **row})
        for variant, folds in portfolio.items()
        for fold, row in folds.items()
    ]
    pl.DataFrame(portfolio_rows, infer_schema_length=None).write_csv(
        args.output / "portfolio.csv",
    )
    trade_rows = [
        flatten_csv_row({"variant": variant, **row})
        for variant, rows in trades.items()
        for row in rows
    ]
    pl.DataFrame(trade_rows, infer_schema_length=None).write_csv(
        args.output / "trades.csv",
    )
    curve_rows = [
        flatten_csv_row({"variant": variant, **row})
        for variant, rows in curves.items()
        for row in rows
    ]
    pl.DataFrame(curve_rows, infer_schema_length=None).write_csv(
        args.output / "equity_curve.csv",
    )
    pl.concat([
        frame.with_columns(pl.lit(variant).alias("variant"))
        for variant, frame in variants.items()
    ]).write_parquet(
        args.output / "selected_variants.parquet",
        compression="zstd",
    )
    write_results(args.output / "RESULTS.md", report)
    _write_json(args.output / "manifest.json", {
        "status": "complete",
        "version": VERSION,
        "script_sha256": script_hash,
        "parameters": vars(args),
        "created_at": datetime.now().isoformat(),
        "elapsed_seconds": elapsed,
    })
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--factor-admission", type=Path, required=True)
    parser.add_argument("--d5-outcomes", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args()
    report = run_study(args)
    selected_n = next(
        row["selected_n"]
        for row in report["events"]
        if row["variant"] == report["primary_variant"]
    )
    print(json.dumps({
        "event": "complete",
        "primary": report["primary_variant"],
        "gate_passed": report["decision_gate"]["passed"],
        "portfolio_return": report["portfolio"][report["primary_variant"]]["oos"][
            "total_return"
        ],
        "selected_n": selected_n,
    }), flush=True)


if __name__ == "__main__":
    main()
