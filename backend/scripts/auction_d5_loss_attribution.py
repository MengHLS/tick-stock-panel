"""Immutable loss attribution for the frozen D+5 auction portfolio."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

import polars as pl

from scripts.auction_high_open_study import PERIODS, _write_json
from scripts.auction_holding_period_risk_study import (
    FROZEN_SELECTION,
    attach_d5_outcomes,
    load_frozen_threshold,
    prepare_scored_events,
)
from scripts.auction_portfolio_construction_study import (
    PORTFOLIO_DEFAULTS,
    select_candidates,
)
from scripts.auction_tail_loss_attribution import (
    add_return_components,
    add_score_band,
    attach_market_returns,
    concentration_stats,
    estimate_market_beta,
    grouped_attribution,
    period_attribution,
    selection_execution_comparison,
)
from scripts.auction_tail_stability_study import VARIANTS as STABILITY_VARIANTS

VERSION = "auction-d5-loss-attribution-v1"
FROZEN_VARIANT = "d5_fixed"
EXPECTED_STUDY_VERSION = "auction-holding-risk-v1"


def load_d5_trades(path: Path) -> pl.DataFrame:
    frame = pl.read_csv(path, try_parse_dates=True).filter(
        pl.col("variant") == FROZEN_VARIANT,
    )
    required = {
        "period",
        "symbol",
        "date",
        "gap_bucket",
        "combined_rank",
        "entry_vwap",
        "entry_volume",
        "exit_date",
        "net_return",
        "allocated",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"D+5 trades are missing columns: {sorted(missing)}")
    if frame.select(pl.struct(["symbol", "date"]).is_duplicated().any()).item():
        raise ValueError("Duplicate D+5 filled trade keys")
    return frame.with_columns(
        pl.col("combined_rank").cast(pl.Float64),
        pl.col("net_return").cast(pl.Float64),
        pl.col("allocated").cast(pl.Float64),
    ).sort(["date", "symbol"])


def attach_d5_gross_returns(
    trades: pl.DataFrame,
    d5_outcomes: Path,
) -> pl.DataFrame:
    d5 = pl.read_parquet(d5_outcomes).select(
        "symbol",
        "date",
        pl.col("gross_return"),
        pl.col("net_return").alias("_d5_net_return"),
    )
    joined = trades.drop("gross_return", strict=False).join(
        d5,
        on=["symbol", "date"],
        how="left",
    )
    if joined["gross_return"].null_count():
        raise ValueError("Filled D+5 trades are missing gross returns")
    mismatch = joined.filter(
        (pl.col("net_return") - pl.col("_d5_net_return")).abs() > 1e-10,
    )
    if mismatch.height:
        raise ValueError("Frozen D+5 net returns do not match outcome table")
    return joined.drop("_d5_net_return")


def reconstruct_d5_selected(
    events_path: Path,
    d5_outcomes: Path,
    *,
    vol_threshold: float,
) -> dict[str, pl.DataFrame]:
    scored = prepare_scored_events(events_path, vol_threshold)
    d5 = pl.read_parquet(d5_outcomes)
    scored_d5 = attach_d5_outcomes(scored, d5)
    contract = STABILITY_VARIANTS[FROZEN_SELECTION]
    selected = {}
    for period, start, end in PERIODS[:4]:
        frame = scored_d5.filter(pl.col("date").is_between(start, end))
        chosen, _ = select_candidates(
            frame,
            start=start,
            end=end,
            contract=contract,
            max_new_per_day=PORTFOLIO_DEFAULTS["max_new_per_day"],
        )
        selected[period] = chosen.with_columns(pl.lit(period).alias("period"))
    return selected


def write_results(path: Path, report: dict) -> None:
    lines = [
        "# Auction D+5 loss attribution",
        "",
        f"Algorithm: `{VERSION}`.",
        "",
        f"Frozen variant: `{FROZEN_VARIANT}`. Development beta: "
        f"`{report['market_beta']:.4f}`.",
        "",
        "| Period | Filled | Actual | Market | Stock residual | Cost |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["period_attribution"]:
        lines.append(
            f"| {row['period']} | {row['filled_n']} | "
            f"{row['actual_return'] * 100:.3f}% | "
            f"{row['market_return_contribution'] * 100:.3f}% | "
            f"{row['stock_return_contribution'] * 100:.3f}% | "
            f"{row['cost_return_contribution'] * 100:.3f}% |",
        )
    lines.extend([
        "",
        "Bucket, score-band and month attribution are in the CSV artifacts.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_study(args: argparse.Namespace) -> dict:
    if args.output.exists():
        raise FileExistsError("Use a NEW output directory; existing runs are never overwritten")
    started = time.perf_counter()
    frozen = json.loads(
        (args.frozen_study / "study.json").read_text(encoding="utf-8"),
    )
    if frozen.get("version") != EXPECTED_STUDY_VERSION:
        raise ValueError("Unexpected frozen holding-study version")
    trades = load_d5_trades(args.frozen_study / "trades.csv")
    trades = attach_d5_gross_returns(trades, args.d5_outcomes)
    trades = attach_market_returns(trades, args.data_dir)
    beta = estimate_market_beta(trades)
    attributed = add_score_band(add_return_components(trades, beta))
    selected = reconstruct_d5_selected(
        args.events,
        args.d5_outcomes,
        vol_threshold=load_frozen_threshold(args.stability_study),
    )
    comparison = selection_execution_comparison(selected, attributed)
    period_rows = period_attribution(
        attributed,
        initial_capital=PORTFOLIO_DEFAULTS["initial_capital"],
    )
    bucket_rows = grouped_attribution(attributed, ["period", "gap_bucket"])
    score_rows = grouped_attribution(attributed, ["period", "score_band"])
    month_rows = grouped_attribution(attributed, ["period", "month"])
    concentration = concentration_stats(attributed)
    for period, _, _ in PERIODS[:4]:
        actual = period_rows.filter(pl.col("period") == period)["actual_return"][0]
        expected = frozen["portfolio"][FROZEN_VARIANT][period]["total_return"]
        if abs(actual - expected) > 1e-10:
            raise AssertionError(
                f"D+5 attribution does not reconcile for {period}: "
                f"{actual} vs {expected}",
            )
    report = {
        "version": VERSION,
        "frozen_study_version": frozen["version"],
        "frozen_variant": FROZEN_VARIANT,
        "market_beta": beta,
        "market_return_proxy": "000001.SH open-to-open from entry date to exit date",
        "period_attribution": period_rows.to_dicts(),
        "selection_vs_filled": comparison.to_dicts(),
        "concentration": concentration.to_dicts(),
        "market_return_missing_n": int(
            attributed["market_return_missing"].sum(),
        ),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "warnings": [
            "This is attribution only; no holding period or portfolio parameter changes.",
            "Market beta is fitted on development D+5 gross returns and clipped to [0, 2].",
            "The open-to-open index return is a proxy for the five-minute execution windows.",
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
    period_rows.write_csv(args.output / "attribution_by_period.csv")
    bucket_rows.write_csv(args.output / "attribution_by_bucket.csv")
    score_rows.write_csv(args.output / "attribution_by_score_band.csv")
    month_rows.write_csv(args.output / "attribution_by_month.csv")
    comparison.write_csv(args.output / "selected_vs_filled.csv")
    concentration.write_csv(args.output / "concentration.csv")
    attributed.write_parquet(
        args.output / "trades_attributed.parquet",
        compression="zstd",
    )
    write_results(args.output / "RESULTS.md", report)
    _write_json(args.output / "manifest.json", {
        "status": "complete",
        "version": VERSION,
        "script_sha256": script_hash,
        "parameters": vars(args),
        "created_at": datetime.now().isoformat(),
        "elapsed_seconds": report["elapsed_seconds"],
    })
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--d5-outcomes", type=Path, required=True)
    parser.add_argument("--frozen-study", type=Path, required=True)
    parser.add_argument("--stability-study", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_study(args)
    print(json.dumps({
        "event": "complete",
        "market_beta": report["market_beta"],
        "elapsed_seconds": report["elapsed_seconds"],
    }), flush=True)


if __name__ == "__main__":
    main()
