"""Pre-registered close-confirmed path stop for the market-gated auction list.

Stops start from the D+1 close to respect A-share T+1. A breached close exits
at the next session's open. Events without a complete daily path are excluded
from every variant, including the baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from bisect import bisect_left
from datetime import date, datetime
from pathlib import Path

import polars as pl

from scripts.auction_d_day_veto_study import _zero_portfolio_summary, flatten_csv_row
from scripts.auction_high_open_study import _partitions, _write_json, summarize
from scripts.auction_portfolio_construction_study import (
    PORTFOLIO_DEFAULTS,
    _cost_factors,
    _with_baseline,
    load_calendar,
    simulate_daily_mark_portfolio,
)
from scripts.auction_walkforward_study import FOLDS, chain_portfolio_curves, load_panel

VERSION = "auction-path-stop-v1"
KEYS = ["symbol", "date"]
BASE_VARIANT = "trend_vol_gate"
PRIMARY_VARIANT = "close_stop_8"
VARIANTS = {
    "baseline": None,
    "close_stop_5": 0.05,
    "close_stop_8": 0.08,
}
DECISION_GATE = {
    "primary_variant": PRIMARY_VARIANT,
    "minimum_selected_events": 200,
    "minimum_path_complete_ratio": 0.98,
    "mean_net_return_positive": True,
    "incremental_ci_lower_positive": True,
    "portfolio_total_return_positive": True,
    "portfolio_max_drawdown_floor": -0.15,
    "no_stale_marks": True,
}


def load_daily_paths(
    data_dir: Path,
    symbols: list[str],
    start: date,
    end: date,
) -> pl.DataFrame:
    files = _partitions(data_dir / "kline_daily", start, end)
    if not files:
        raise ValueError("No daily bars for stop-path window")
    frame = (
        pl.scan_parquet(files, hive_partitioning=False, extra_columns="ignore")
        .filter(pl.col("symbol").is_in(symbols))
        .select("symbol", "date", "open", "close")
        .collect()
    )
    if frame.select(pl.struct(KEYS).is_duplicated().any()).item():
        raise ValueError("Duplicate daily path keys")
    return frame.filter(
        pl.col("open").is_not_null()
        & pl.col("open").is_finite()
        & (pl.col("open") > 0)
        & pl.col("close").is_not_null()
        & pl.col("close").is_finite()
        & (pl.col("close") > 0),
    )


def load_base(selected_path: Path) -> pl.DataFrame:
    selected = (
        pl.read_parquet(selected_path)
        .filter(pl.col("variant") == BASE_VARIANT)
        .drop("variant")
    )
    if selected.select(pl.struct(KEYS).is_duplicated().any()).item():
        raise ValueError("Duplicate market-gate event keys")
    return selected


def path_is_complete(
    row: dict,
    *,
    sessions: list[date],
    prices: dict[tuple[str, date], tuple[float, float]],
) -> bool:
    entry_index = bisect_left(sessions, row["date"])
    exit_index = bisect_left(sessions, row["exit_date"])
    if entry_index >= len(sessions) or sessions[entry_index] != row["date"]:
        return False
    if exit_index >= len(sessions) or sessions[exit_index] != row["exit_date"]:
        return False
    if exit_index - entry_index < 2:
        return False
    for index in range(entry_index + 1, exit_index):
        if (row["symbol"], sessions[index]) not in prices:
            return False
        if (row["symbol"], sessions[index + 1]) not in prices:
            return False
    return True


def prepare_path_universe(
    selected: pl.DataFrame,
    *,
    sessions: list[date],
    daily: pl.DataFrame,
) -> tuple[pl.DataFrame, dict, int]:
    prices = {
        (row["symbol"], row["date"]): (row["open"], row["close"])
        for row in daily.iter_rows(named=True)
    }
    complete = [
        path_is_complete(row, sessions=sessions, prices=prices)
        for row in selected.iter_rows(named=True)
    ]
    filtered = selected.filter(pl.Series("path_complete", complete))
    return filtered, prices, selected.height - filtered.height


def apply_stop_variant(
    selected: pl.DataFrame,
    *,
    sessions: list[date],
    prices: dict[tuple[str, date], tuple[float, float]],
    stop_pct: float | None,
    commission_bps: float,
    stamp_tax_bps: float,
    slippage_bps: float,
) -> pl.DataFrame:
    buy_factor, sell_factor = _cost_factors({
        "commission_bps": commission_bps,
        "stamp_tax_bps": stamp_tax_bps,
        "slippage_bps": slippage_bps,
    })
    rows = []
    for source in selected.iter_rows(named=True):
        row = {
            **source,
            "path_exit_date": source["exit_date"],
            "path_net_return": source["net_return"],
            "stop_triggered": False,
            "stop_trigger_date": None,
            "stop_trigger_close": None,
            "stop_exit_price": None,
        }
        if stop_pct is not None:
            entry_index = bisect_left(sessions, source["date"])
            exit_index = bisect_left(sessions, source["exit_date"])
            for trigger_index in range(entry_index + 1, exit_index):
                trigger_date = sessions[trigger_index]
                _, trigger_close = prices[(source["symbol"], trigger_date)]
                if trigger_close > source["entry_vwap"] * (1 - stop_pct):
                    continue
                next_index = trigger_index + 1
                exit_date = sessions[next_index]
                exit_open, _ = prices[(source["symbol"], exit_date)]
                row.update({
                    "path_exit_date": exit_date,
                    "path_net_return": (
                        exit_open / source["entry_vwap"] * sell_factor / buy_factor - 1
                    ),
                    "stop_triggered": True,
                    "stop_trigger_date": trigger_date,
                    "stop_trigger_close": trigger_close,
                    "stop_exit_price": exit_open,
                })
                break
        rows.append(row)
    return pl.DataFrame(rows, infer_schema_length=None).with_columns(
        pl.col("stop_trigger_date").cast(pl.Date),
        pl.col("stop_trigger_close").cast(pl.Float64),
        pl.col("stop_exit_price").cast(pl.Float64),
    )


def select_variants(
    selected: pl.DataFrame,
    *,
    sessions: list[date],
    prices: dict[tuple[str, date], tuple[float, float]],
) -> dict[str, pl.DataFrame]:
    return {
        variant: apply_stop_variant(
            selected,
            sessions=sessions,
            prices=prices,
            stop_pct=stop_pct,
            commission_bps=PORTFOLIO_DEFAULTS["commission_bps"],
            stamp_tax_bps=PORTFOLIO_DEFAULTS["stamp_tax_bps"],
            slippage_bps=PORTFOLIO_DEFAULTS["slippage_bps"],
        )
        for variant, stop_pct in VARIANTS.items()
    }


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
    for variant, selected in variants.items():
        exact = (
            baseline.join(
                selected.select(*KEYS, "path_net_return"),
                on=KEYS,
                how="inner",
            )
            .with_columns(
                pl.col("path_net_return").alias("net_return"),
                (pl.col("path_net_return") - pl.col("_baseline"))
                .alias("incremental_return"),
                (
                    (pl.col("path_net_return") > 0).cast(pl.Float64)
                    - pl.col("_baseline_win")
                ).alias("win_increment"),
            )
        )
        rows.append({
            "variant": variant,
            "selected_n": selected.height,
            "triggered_n": selected.filter(pl.col("stop_triggered")).height,
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
    daily: pl.DataFrame,
) -> tuple[dict[str, dict[str, dict]], dict[str, list[dict]], dict[str, list[dict]]]:
    closes = daily.select("symbol", "date", "close")
    portfolio: dict[str, dict[str, dict]] = {}
    trades: dict[str, list[dict]] = {}
    curves: dict[str, list[dict]] = {}
    for variant, selected in variants.items():
        fold_portfolios = []
        trades[variant] = []
        curves[variant] = []
        portfolio[variant] = {}
        executable = selected.with_columns(
            pl.col("path_exit_date").alias("exit_date"),
            pl.col("path_net_return").alias("net_return"),
        )
        for fold in FOLDS:
            fold_selected = executable.filter(pl.col("fold") == fold["name"])
            if fold_selected.is_empty():
                summary = _zero_portfolio_summary()
                filled = []
                curve = []
            else:
                summary, filled, curve = simulate_daily_mark_portfolio(
                    fold_selected,
                    calendar=calendar,
                    daily_closes=closes,
                    start=fold["test_start"],
                    end=fold["test_end"],
                )
            summary["candidate_n"] = fold_selected.height
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
    original_n: int,
    complete_n: int,
) -> dict:
    event = next(row for row in events if row["variant"] == PRIMARY_VARIANT)
    interval = (event.get("cluster_bootstrap_95") or {}).get(
        "mean_incremental_return",
    )
    result = portfolio[PRIMARY_VARIANT]["oos"]
    complete_ratio = complete_n / original_n if original_n else 0.0
    checks = {
        "minimum_selected_events": (
            variants[PRIMARY_VARIANT].height
            >= DECISION_GATE["minimum_selected_events"]
        ),
        "path_complete_ratio": (
            complete_ratio >= DECISION_GATE["minimum_path_complete_ratio"]
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
        "path_complete_ratio": complete_ratio,
        "checks": checks,
        "passed": all(checks.values()),
    }


def write_results(path: Path, report: dict) -> None:
    lines = [
        "# Close-confirmed path stop",
        "",
        f"Algorithm: `{VERSION}`.",
        "",
        "The D-1 market-gated list keeps D-day entry.",
        "Stops begin at the D+1 close and fill at the next session open.",
        "",
        "| Variant | Selected | Triggered | Net | Delta | Delta 95% CI |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["events"]:
        interval = (row.get("cluster_bootstrap_95") or {}).get(
            "mean_incremental_return",
        )
        interval_text = (
            f"{interval[0] * 100:.3f}% to {interval[1] * 100:.3f}%"
            if interval else "NA"
        )
        lines.append(
            f"| {row['variant']} | {row['selected_n']} | {row['triggered_n']} | "
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
    selected = load_base(args.selected)
    symbols = sorted(set(selected["symbol"].to_list()))
    start_date = selected["date"].min()
    end_date = selected["exit_date"].max()
    sessions = load_calendar(args.data_dir, start_date, end_date)
    daily = load_daily_paths(args.data_dir, symbols, start_date, end_date)
    complete, prices, excluded_n = prepare_path_universe(
        selected,
        sessions=sessions,
        daily=daily,
    )
    variants = select_variants(
        complete,
        sessions=sessions,
        prices=prices,
    )
    panel, _ = load_panel(args.events, args.factor_admission, args.d5_outcomes)

    events = event_results(
        panel,
        variants,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    portfolio, trades, curves = portfolio_results(
        variants,
        calendar=sessions,
        daily=daily,
    )
    gate = decision_gate(
        variants,
        events,
        portfolio,
        original_n=selected.height,
        complete_n=complete.height,
    )
    elapsed = round(time.perf_counter() - started, 3)
    report = {
        "version": VERSION,
        "primary_variant": PRIMARY_VARIANT,
        "variants": VARIANTS,
        "decision_gate": gate,
        "events": events,
        "portfolio": portfolio,
        "input_selected_n": selected.height,
        "path_complete_n": complete.height,
        "path_excluded_n": excluded_n,
        "portfolio_defaults": PORTFOLIO_DEFAULTS,
        "elapsed_seconds": elapsed,
        "warnings": [
            "Stops cannot trigger on the entry date because of A-share T+1.",
            "A breached daily close exits at the next session open.",
            "Events with incomplete daily paths are excluded from every variant.",
            "The market-gated signal and D+5 outcomes are frozen.",
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

    pl.DataFrame(
        [flatten_csv_row(row) for row in events],
        infer_schema_length=None,
    ).write_csv(args.output / "events.csv")
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
    event = next(
        row
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
        "selected_n": event["selected_n"],
        "triggered_n": event["triggered_n"],
    }), flush=True)


if __name__ == "__main__":
    main()
