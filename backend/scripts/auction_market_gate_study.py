"""Pre-registered D-1 market-regime gate for the D-day auction veto list.

All market features are shifted by one completed session before joining to the
D-day signal. The selected event set is filtered without replacement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

from scripts.auction_d_day_veto_study import _zero_portfolio_summary, flatten_csv_row
from scripts.auction_high_open_study import _partitions, _write_json, summarize
from scripts.auction_portfolio_construction_study import (
    PORTFOLIO_DEFAULTS,
    _with_baseline,
    load_calendar,
    load_daily_closes,
    simulate_daily_mark_portfolio,
)
from scripts.auction_walkforward_study import FOLDS, chain_portfolio_curves, load_panel

VERSION = "auction-market-gate-v1"
KEYS = ["symbol", "date"]
BASE_VARIANT = "balanced_veto"
PRIMARY_VARIANT = "trend_vol_gate"
VARIANTS = (
    "balanced_veto",
    "trend_gate",
    "vol_gate",
    "trend_vol_gate",
)
DECISION_GATE = {
    "primary_variant": PRIMARY_VARIANT,
    "minimum_selected_events": 200,
    "minimum_candidate_reduction": 0.50,
    "maximum_mean_daily_candidates": 1.0,
    "mean_net_return_positive": True,
    "incremental_ci_lower_positive": True,
    "portfolio_total_return_positive": True,
    "portfolio_max_drawdown_floor": -0.15,
    "no_stale_marks": True,
}


def build_market_features(
    data_dir: Path,
    start: date,
    end: date,
) -> pl.DataFrame:
    files = _partitions(
        data_dir / "kline_index_daily",
        start - timedelta(days=180),
        end,
    )
    if not files:
        raise ValueError("No index sessions for market features")
    index = (
        pl.scan_parquet(files, hive_partitioning=False, extra_columns="ignore")
        .filter(pl.col("symbol") == "000001.SH")
        .select("date", "close")
        .collect()
        .sort("date")
    )
    if index["date"].is_duplicated().any():
        raise ValueError("Duplicate index dates")
    return compute_market_features(index)


def compute_market_features(index: pl.DataFrame) -> pl.DataFrame:
    return (
        index.sort("date")
        .with_columns(
            (pl.col("close") / pl.col("close").shift(1) - 1).alias("_ret1"),
            (pl.col("close") / pl.col("close").shift(20) - 1).alias("_ret20"),
            pl.col("close").rolling_mean(20).alias("_ma20"),
        )
        .with_columns(
            pl.col("_ret1").rolling_std(20).alias("_vol20"),
        )
        .with_columns(
            pl.col("_vol20").rolling_median(60).alias("_vol_median60"),
        )
        .with_columns(
            pl.col("_ret20").shift(1).alias("market_ret20"),
            pl.col("_vol20").shift(1).alias("market_vol20"),
            pl.col("_vol_median60").shift(1).alias("market_vol_median60"),
            pl.col("close").shift(1).alias("market_prev_close"),
            pl.col("_ma20").shift(1).alias("market_ma20"),
        )
        .with_columns(
            (
                pl.col("market_prev_close").is_not_null()
                & pl.col("market_ma20").is_not_null()
                & (pl.col("market_prev_close") >= pl.col("market_ma20"))
            ).alias("trend_gate"),
            (pl.col("market_ret20") >= 0).fill_null(False).alias("positive_ret20_gate"),
            (
                pl.col("market_vol20").is_not_null()
                & pl.col("market_vol_median60").is_not_null()
                & (pl.col("market_vol20") <= pl.col("market_vol_median60"))
            ).alias("vol_gate"),
        )
        .with_columns(
            (
                pl.col("trend_gate")
                & pl.col("positive_ret20_gate")
            ).alias("trend_gate"),
        )
        .select(
            "date",
            "market_ret20",
            "market_vol20",
            "market_vol_median60",
            "market_prev_close",
            "market_ma20",
            "trend_gate",
            "vol_gate",
        )
    )


def load_base(
    selected_path: Path,
    market: pl.DataFrame,
) -> pl.DataFrame:
    selected = (
        pl.read_parquet(selected_path)
        .filter(pl.col("variant") == BASE_VARIANT)
        .drop("variant")
    )
    if selected.select(pl.struct(KEYS).is_duplicated().any()).item():
        raise ValueError("Duplicate balanced-veto event keys")
    frame = selected.join(market, on="date", how="left")
    if frame.filter(pl.col("market_vol20").is_null()).height:
        raise ValueError("Selected events without D-1 market features")
    return frame


def apply_market_variant(frame: pl.DataFrame, variant: str) -> pl.DataFrame:
    if variant == "balanced_veto":
        return frame
    if variant == "trend_gate":
        return frame.filter(pl.col("trend_gate"))
    if variant == "vol_gate":
        return frame.filter(pl.col("vol_gate"))
    if variant == "trend_vol_gate":
        return frame.filter(pl.col("trend_gate") & pl.col("vol_gate"))
    raise ValueError(f"Unknown market-gate variant: {variant}")


def select_variants(frame: pl.DataFrame) -> dict[str, pl.DataFrame]:
    return {variant: apply_market_variant(frame, variant) for variant in VARIANTS}


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
    return [
        {
            "variant": variant,
            "selected_n": selected.height,
            **summarize(
                baseline.join(selected.select(KEYS), on=KEYS, how="semi"),
                bootstrap_samples=bootstrap_samples,
                seed=seed,
            ),
        }
        for variant, selected in variants.items()
    ]


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
    baseline_n = variants[BASE_VARIANT].height
    primary_n = variants[PRIMARY_VARIANT].height
    event = next(row for row in events if row["variant"] == PRIMARY_VARIANT)
    interval = (event.get("cluster_bootstrap_95") or {}).get(
        "mean_incremental_return",
    )
    result = portfolio[PRIMARY_VARIANT]["oos"]
    reduction = 1 - primary_n / baseline_n if baseline_n else 0.0
    mean_daily = primary_n / session_count if session_count else float("inf")
    checks = {
        "minimum_selected_events": (
            primary_n >= DECISION_GATE["minimum_selected_events"]
        ),
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
        "# D-1 market-regime gate",
        "",
        f"Algorithm: `{VERSION}`.",
        "",
        "The balanced D-day veto list is filtered with prior-close index data.",
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
    source = pl.read_parquet(args.selected, columns=["variant", "date"])
    start_date = source["date"].min()
    end_date = source["date"].max()
    market = build_market_features(args.data_dir, start_date, end_date)
    selected = load_base(args.selected, market)
    variants = select_variants(selected)
    panel, _ = load_panel(args.events, args.factor_admission, args.d5_outcomes)

    all_selected = variants[BASE_VARIANT]
    symbols = sorted(set(all_selected["symbol"].to_list()))
    calendar = load_calendar(
        args.data_dir,
        all_selected["date"].min(),
        all_selected["exit_date"].max(),
    )
    daily_closes = load_daily_closes(
        args.data_dir,
        symbols,
        all_selected["date"].min(),
        all_selected["exit_date"].max(),
    )
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
        "market_rules": {
            "trend": "D-1 index close >= D-1 MA20 and D-1 20-session return >= 0",
            "volatility": "D-1 20-session vol <= D-1 rolling 60-session median",
        },
        "decision_gate": gate,
        "events": events,
        "portfolio": portfolio,
        "session_count": session_count,
        "portfolio_defaults": PORTFOLIO_DEFAULTS,
        "elapsed_seconds": elapsed,
        "warnings": [
            "All market features use completed D-1 index data shifted by one session.",
            "Rejected candidates are not refilled from lower ranks.",
            "The balanced D-day veto list and D+5 outcomes are frozen.",
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
