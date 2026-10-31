"""Pre-registered score-tail stability study for frozen auction signals.

Only score selection changes. Portfolio construction stays at the frozen 2/2/1
bucket quota, and validation/stress outcomes never define score bands or gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

from scripts.auction_high_open_study import PERIODS, _partitions, _write_json, summarize
from scripts.auction_portfolio_construction_study import (
    BUCKET_QUOTAS,
    PORTFOLIO_DEFAULTS,
    _with_baseline,
    load_calendar,
    load_daily_closes,
    select_candidates,
    simulate_daily_mark_portfolio,
)

VERSION = "auction-tail-stability-v1"
GAP_BUCKETS = ["2-4", "4-6", "6-8"]
PRIMARY_VARIANT = "band70_90_quota"
VARIANTS = {
    "top30_quota": {
        "signal_column": "_tail_risk_blend",
        "score_column": "combined_rank",
        "selection": "bucket_quota",
    },
    "band70_90_quota": {
        "signal_column": "_band70_90",
        "score_column": "combined_rank",
        "selection": "bucket_quota",
    },
    "band70_90_lowvol_quota": {
        "signal_column": "_band70_90_lowvol",
        "score_column": "combined_rank",
        "selection": "bucket_quota",
    },
    "consensus70_quota": {
        "signal_column": "_consensus70",
        "score_column": "consensus_score",
        "selection": "bucket_quota",
    },
}
DECISION_GATE = {
    "periods": ["validation", "retrospective_stress"],
    "selected_incremental_ci_lower_positive": True,
    "portfolio_total_return_positive": True,
    "portfolio_max_drawdown_floor": -0.15,
}


def _finite(column: str) -> pl.Expr:
    value = pl.col(column)
    return pl.when(value.is_not_null() & value.is_finite()).then(value).otherwise(None)


def load_events(path: Path) -> pl.DataFrame:
    required = [
        "symbol",
        "date",
        "gap_bucket",
        "tail_strength_signal",
        "tail_strength_rank",
        "risk_rank",
        "_risk_coverage",
        "combined_rank",
        "_risk_signal",
        "_tail_risk_intersection",
        "_tail_risk_blend",
        "entry_reason",
        "exit_reason",
        "entry_vwap",
        "entry_volume",
        "exit_date",
        "net_return",
    ]
    return pl.read_parquet(path, columns=required).filter(
        pl.col("gap_bucket").is_in(GAP_BUCKETS),
    )


def build_market_features(
    data_dir: Path,
    start: date,
    end: date,
) -> pl.DataFrame:
    files = _partitions(
        data_dir / "kline_index_daily",
        start - timedelta(days=60),
        end,
    )
    if not files:
        raise ValueError("No index sessions for market features")
    index = (
        pl.scan_parquet(files, hive_partitioning=False)
        .filter(pl.col("symbol") == "000001.SH")
        .select("date", "close")
        .collect()
    )
    return compute_market_features(index)


def compute_market_features(index: pl.DataFrame) -> pl.DataFrame:
    return (
        index.sort("date")
        .with_columns(
            (pl.col("close") / pl.col("close").shift(1) - 1).alias("_return"),
        )
        .with_columns(
            pl.col("_return").rolling_std(20).alias("_vol20"),
            (pl.col("close") / pl.col("close").shift(20) - 1).alias("_ret20"),
        )
        .with_columns(
            pl.col("_vol20").shift(1).alias("market_vol_20d"),
            pl.col("_ret20").shift(1).alias("market_ret_20d"),
        )
        .select("date", "market_vol_20d", "market_ret_20d")
    )


def development_vol_threshold(events: pl.DataFrame) -> float:
    development = events.filter(
        pl.col("date").is_between(*PERIODS[0][1:])
        & _finite("market_vol_20d").is_not_null(),
    ).select("date", "market_vol_20d").unique("date")
    if development.is_empty():
        raise ValueError("No development market volatility observations")
    return float(development["market_vol_20d"].median())


def add_stability_signals(
    events: pl.DataFrame,
    *,
    vol_threshold: float,
) -> pl.DataFrame:
    low_vol = _finite("market_vol_20d") <= vol_threshold
    band = (
        pl.col("_tail_risk_blend").fill_null(False)
        & pl.col("combined_rank").is_between(0.70, 0.90, closed="left")
    )
    consensus = (
        (pl.col("risk_rank") >= 0.70)
        & (pl.col("tail_strength_rank") >= 0.70)
    ).fill_null(False)
    return events.with_columns(
        band.fill_null(False).alias("_band70_90"),
        (band & low_vol.fill_null(False)).alias("_band70_90_lowvol"),
        consensus.alias("_consensus70"),
        pl.min_horizontal("risk_rank", "tail_strength_rank").alias("consensus_score"),
    )


def _selected_event_results(
    events: pl.DataFrame,
    selections: dict[str, dict[str, tuple[pl.DataFrame, int]]],
    *,
    bootstrap_samples: int,
    seed: int,
) -> list[dict]:
    rows = []
    for period, start, end in PERIODS[:4]:
        period_frame = events.filter(pl.col("date").is_between(start, end))
        baseline = _with_baseline(period_frame)
        for variant in VARIANTS:
            selected, candidate_n = selections[period][variant]
            exact = baseline.join(
                selected.select("symbol", "date"),
                on=["symbol", "date"],
                how="semi",
            )
            rows.append({
                "period": period,
                "variant": variant,
                "candidate_n": candidate_n,
                "selected_n": selected.height,
                **summarize(
                    exact,
                    bootstrap_samples=bootstrap_samples,
                    seed=seed,
                ),
            })
    return rows


def decision_gate(selected_results: list[dict], portfolio: dict) -> dict:
    checks = {}
    for period in DECISION_GATE["periods"]:
        selected = next(
            row for row in selected_results
            if row["period"] == period and row["variant"] == PRIMARY_VARIANT
        )
        interval = (selected.get("cluster_bootstrap_95") or {}).get(
            "mean_incremental_return",
        )
        result = portfolio[PRIMARY_VARIANT][period]
        checks[period] = {
            "selected_incremental_ci_lower_positive": (
                interval is not None and interval[0] > 0
            ),
            "portfolio_total_return_positive": (
                result.get("total_return") is not None
                and result["total_return"] > 0
            ),
            "portfolio_max_drawdown_above_floor": (
                result.get("max_drawdown_mtm") is not None
                and result["max_drawdown_mtm"]
                >= DECISION_GATE["portfolio_max_drawdown_floor"]
            ),
            "no_stale_marks": result.get("stale_marks", 1) == 0,
        }
        checks[period]["passed"] = all(checks[period].values())
    return {
        "primary_variant": PRIMARY_VARIANT,
        "rules": DECISION_GATE,
        "periods": checks,
        "passed": all(row["passed"] for row in checks.values()),
    }


def write_results(path: Path, report: dict) -> None:
    lines = [
        "# Auction score-tail stability study",
        "",
        f"Algorithm: `{VERSION}`.",
        "",
        f"Development volatility threshold: `{report['vol_threshold']:.6f}`.",
        "",
        "## Selected event results",
        "",
        "| Period | Variant | Selected | Net | Delta | Delta 95% CI |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in report["selected_results"]:
        interval = (row.get("cluster_bootstrap_95") or {}).get(
            "mean_incremental_return",
        )
        interval_text = (
            f"{interval[0] * 100:.3f}% to {interval[1] * 100:.3f}%"
            if interval else "NA"
        )
        lines.append(
            f"| {row['period']} | {row['variant']} | {row['n']} | "
            f"{row['mean_net_return'] * 100:.3f}% | "
            f"{row['mean_incremental_return'] * 100:.3f}% | {interval_text} |",
        )
    lines.extend([
        "",
        "## Daily mark-to-market portfolio",
        "",
        "| Period | Variant | Filled | Total | Max drawdown | Mean exposure |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for variant, periods in report["portfolio"].items():
        for period, row in periods.items():
            lines.append(
                f"| {period} | {variant} | {row['filled_n']} | "
                f"{row['total_return'] * 100:.3f}% | "
                f"{row['max_drawdown_mtm'] * 100:.3f}% | "
                f"{row['mean_exposure'] * 100:.3f}% |",
            )
    lines.extend([
        "",
        "## Decision gate",
        "",
        f"Primary variant: `{report['decision_gate']['primary_variant']}`.",
        "",
        f"Passed: `{report['decision_gate']['passed']}`.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_study(args: argparse.Namespace) -> dict:
    if args.output.exists():
        raise FileExistsError("Use a NEW output directory; existing runs are never overwritten")
    if args.bootstrap_samples < 0:
        raise ValueError("bootstrap_samples must be non-negative")
    started = time.perf_counter()
    event_stat = [args.events.stat().st_size, args.events.stat().st_mtime_ns]
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.mkdir(parents=True)
    _write_json(args.output / "manifest.json", {
        "status": "running",
        "version": VERSION,
        "script_sha256": script_hash,
        "parameters": vars(args),
        "bucket_quotas": BUCKET_QUOTAS,
        "portfolio_defaults": PORTFOLIO_DEFAULTS,
        "variants": VARIANTS,
        "primary_variant": PRIMARY_VARIANT,
        "decision_gate": DECISION_GATE,
        "created_at": datetime.now().isoformat(),
    })
    events = load_events(args.events)
    market = build_market_features(
        args.data_dir,
        events["date"].min(),
        events["date"].max(),
    )
    events = events.join(market, on="date", how="left")
    vol_threshold = development_vol_threshold(events)
    events = add_stability_signals(events, vol_threshold=vol_threshold)

    selections: dict[str, dict[str, tuple[pl.DataFrame, int]]] = {}
    selected_rows_for_closes = []
    for period, start, end in PERIODS[:4]:
        period_frame = events.filter(pl.col("date").is_between(start, end))
        selections[period] = {}
        for variant, contract in VARIANTS.items():
            selected, candidate_n = select_candidates(
                period_frame,
                start=start,
                end=end,
                contract=contract,
                max_new_per_day=PORTFOLIO_DEFAULTS["max_new_per_day"],
            )
            selections[period][variant] = (selected, candidate_n)
            selected_rows_for_closes.append(selected.select("symbol", "date", "exit_date"))

    selected_results = _selected_event_results(
        events,
        selections,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    symbols = sorted(set(pl.concat(selected_rows_for_closes)["symbol"].to_list()))
    start_date = min(
        selected["date"].min()
        for period_rows in selections.values()
        for selected, _ in period_rows.values()
        if not selected.is_empty()
    )
    end_date = max(
        selected["exit_date"].max()
        for period_rows in selections.values()
        for selected, _ in period_rows.values()
        if not selected.is_empty()
    )
    calendar = load_calendar(args.data_dir, start_date, end_date)
    daily_closes = load_daily_closes(args.data_dir, symbols, start_date, end_date)

    portfolio: dict[str, dict] = {}
    trades = []
    curves = []
    for period, start, end in PERIODS[:4]:
        for variant in VARIANTS:
            selected, _ = selections[period][variant]
            summary, filled, curve = simulate_daily_mark_portfolio(
                selected,
                calendar=calendar,
                daily_closes=daily_closes,
                start=start,
                end=end,
            )
            portfolio.setdefault(variant, {})[period] = summary
            trades.extend({"period": period, "variant": variant, **row} for row in filled)
            curves.extend({"period": period, "variant": variant, **row} for row in curve)

    report = {
        "version": VERSION,
        "scope": {
            "gap_buckets": GAP_BUCKETS,
            "horizon": 3,
            "event_rows": events.height,
            "event_days": events["date"].n_unique(),
        },
        "vol_threshold": vol_threshold,
        "bucket_quotas": BUCKET_QUOTAS,
        "portfolio_defaults": PORTFOLIO_DEFAULTS,
        "variants": VARIANTS,
        "decision_gate": decision_gate(selected_results, portfolio),
        "selected_results": selected_results,
        "portfolio": portfolio,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "warnings": [
            "Score bands and the volatility threshold use development data only.",
            "Portfolio construction remains the frozen 2/2/1 bucket quota.",
            "Validation and stress periods do not alter score bands or market gates.",
            "Daily marks use raw daily closes and estimated liquidation costs.",
        ],
    }
    if [args.events.stat().st_size, args.events.stat().st_mtime_ns] != event_stat:
        raise RuntimeError("Input event table changed during study")
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != script_hash:
        raise RuntimeError("Study source changed during execution")
    _write_json(args.output / "study.json", report)
    _write_json(args.output / "manifest.json", {
        **json.loads((args.output / "manifest.json").read_text(encoding="utf-8")),
        "status": "complete",
        "inputs_unchanged": True,
        "source_unchanged": True,
        "elapsed_seconds": report["elapsed_seconds"],
    })
    flat_selected = [
        {
            "period": row["period"],
            "variant": row["variant"],
            "candidate_n": row["candidate_n"],
            "selected_n": row["selected_n"],
            **{
                key: (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                )
                for key, value in row.items()
                if key not in {"period", "variant", "candidate_n", "selected_n"}
            },
        }
        for row in selected_results
    ]
    pl.DataFrame(flat_selected, infer_schema_length=None).write_csv(
        args.output / "selected_results.csv",
    )
    flat_portfolio = [
        {
            "variant": variant,
            "period": period,
            **{
                key: (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                )
                for key, value in row.items()
            },
        }
        for variant, periods in portfolio.items()
        for period, row in periods.items()
    ]
    pl.DataFrame(flat_portfolio, infer_schema_length=None).write_csv(
        args.output / "portfolio.csv",
    )
    pl.DataFrame(trades, infer_schema_length=None).write_csv(args.output / "trades.csv")
    pl.DataFrame(curves, infer_schema_length=None).write_csv(args.output / "equity_curve.csv")
    write_results(args.output / "RESULTS.md", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args()
    report = run_study(args)
    print(json.dumps({
        "event": "complete",
        "vol_threshold": report["vol_threshold"],
        "gate_passed": report["decision_gate"]["passed"],
        "elapsed_seconds": report["elapsed_seconds"],
    }), flush=True)


if __name__ == "__main__":
    main()
