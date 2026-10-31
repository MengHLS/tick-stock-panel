"""Immutable loss attribution for the frozen auction 70%-90% score-band model.

The script reconstructs the exact frozen selection, joins filled trades and
decomposes realised P&L into market beta, stock/factor residual and costs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl

from scripts.auction_high_open_study import PERIODS, _partitions, _write_json
from scripts.auction_portfolio_construction_study import (
    PORTFOLIO_DEFAULTS,
    select_candidates,
)
from scripts.auction_tail_stability_study import (
    VARIANTS,
    add_stability_signals,
    load_events,
)

VERSION = "auction-tail-loss-attribution-v1"
FROZEN_STUDY_VERSION = "auction-tail-stability-v1"
FROZEN_VARIANT = "band70_90_quota"
BETA_CLIP = (0.0, 2.0)
CONCENTRATION_FRACTION = 0.05


def load_frozen_study(path: Path) -> dict:
    study = json.loads((path / "study.json").read_text(encoding="utf-8"))
    if study.get("version") != FROZEN_STUDY_VERSION:
        raise ValueError(f"Unexpected frozen study version: {study.get('version')}")
    if study.get("decision_gate", {}).get("primary_variant") != FROZEN_VARIANT:
        raise ValueError("Frozen study primary variant does not match attribution target")
    return study


def load_filled_trades(path: Path) -> pl.DataFrame:
    frame = pl.read_csv(path, try_parse_dates=True).filter(
        pl.col("variant") == FROZEN_VARIANT,
    )
    required = {
        "period",
        "variant",
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
        raise ValueError(f"Frozen trades are missing columns: {sorted(missing)}")
    if frame.select(pl.struct(["symbol", "date"]).is_duplicated().any()).item():
        raise ValueError("Duplicate filled trade keys")
    return frame.sort(["date", "symbol"])


def reconstruct_selected(
    events_path: Path,
    *,
    vol_threshold: float,
) -> dict[str, pl.DataFrame]:
    events = load_events(events_path).with_columns(
        pl.lit(None, dtype=pl.Float64).alias("market_vol_20d"),
    )
    events = add_stability_signals(events, vol_threshold=vol_threshold)
    contract = VARIANTS[FROZEN_VARIANT]
    selected = {}
    for period, start, end in PERIODS[:4]:
        period_frame = events.filter(pl.col("date").is_between(start, end))
        chosen, _ = select_candidates(
            period_frame,
            start=start,
            end=end,
            contract=contract,
            max_new_per_day=PORTFOLIO_DEFAULTS["max_new_per_day"],
        )
        selected[period] = chosen.with_columns(pl.lit(period).alias("period"))
    return selected


def attach_gross_returns(
    trades: pl.DataFrame,
    source_events: Path,
) -> pl.DataFrame:
    source = (
        pl.scan_parquet(source_events)
        .filter(pl.col("horizon") == 3)
        .select(
            "symbol",
            "date",
            pl.col("gross_return"),
            pl.col("net_return").alias("_source_net_return"),
        )
        .collect()
    )
    joined = trades.join(source, on=["symbol", "date"], how="left")
    if joined["gross_return"].null_count():
        raise ValueError("Filled trades are missing gross returns")
    mismatch = joined.filter(
        (pl.col("net_return") - pl.col("_source_net_return")).abs() > 1e-10,
    )
    if mismatch.height:
        raise ValueError("Frozen net return mismatch against source event table")
    return joined.drop("_source_net_return")


def attach_market_returns(
    trades: pl.DataFrame,
    data_dir: Path,
) -> pl.DataFrame:
    start = trades["date"].min()
    end = trades["exit_date"].max()
    files = _partitions(data_dir / "kline_index_daily", start, end)
    if not files:
        raise ValueError("No index sessions for market attribution")
    index = (
        pl.scan_parquet(files, hive_partitioning=False)
        .filter(pl.col("symbol") == "000001.SH")
        .select("date", "open")
        .collect()
    )
    index = index.filter(
        pl.col("date").is_between(start, end)
        & pl.col("open").is_not_null()
        & pl.col("open").is_finite()
        & (pl.col("open") > 0),
    )
    entry = index.select(
        pl.col("date").alias("date"),
        pl.col("open").alias("_entry_market_open"),
    )
    exit_ = index.select(
        pl.col("date").alias("exit_date"),
        pl.col("open").alias("_exit_market_open"),
    )
    result = trades.join(entry, on="date", how="left").join(
        exit_,
        on="exit_date",
        how="left",
    ).with_columns(
        (
            pl.col("_exit_market_open") / pl.col("_entry_market_open") - 1
        ).alias("market_return"),
        (
            pl.col("_entry_market_open").is_null()
            | pl.col("_exit_market_open").is_null()
        ).alias("market_return_missing"),
    ).drop("_entry_market_open", "_exit_market_open")
    return result.with_columns(
        pl.col("market_return").fill_null(0.0),
    )


def estimate_market_beta(trades: pl.DataFrame) -> float:
    development = trades.filter(
        (pl.col("period") == "development")
        & pl.col("gross_return").is_finite()
        & pl.col("market_return").is_finite(),
    )
    if development.height < 30:
        return 1.0
    market = development["market_return"].to_numpy()
    returns = development["gross_return"].to_numpy()
    variance = float(np.var(market))
    if variance <= 0:
        return 1.0
    beta = float(np.cov(returns, market, ddof=1)[0, 1] / variance)
    return float(np.clip(beta, *BETA_CLIP))


def add_return_components(trades: pl.DataFrame, beta: float) -> pl.DataFrame:
    return trades.with_columns(
        (pl.col("allocated") * pl.col("net_return")).alias("actual_pnl"),
        (pl.col("allocated") * pl.col("gross_return")).alias("gross_pnl"),
        (
            pl.col("allocated")
            * (pl.col("net_return") - pl.col("gross_return"))
        ).alias("cost_pnl"),
        (
            pl.col("allocated") * beta * pl.col("market_return")
        ).alias("market_pnl"),
        (
            pl.col("allocated")
            * (pl.col("gross_return") - beta * pl.col("market_return"))
        ).alias("stock_pnl"),
    )


def add_score_band(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns(
        pl.when(pl.col("combined_rank") < 0.75).then(pl.lit("70-75"))
        .when(pl.col("combined_rank") < 0.80).then(pl.lit("75-80"))
        .when(pl.col("combined_rank") < 0.85).then(pl.lit("80-85"))
        .otherwise(pl.lit("85-90")).alias("score_band"),
        pl.col("date").dt.strftime("%Y-%m").alias("month"),
    )


def period_attribution(trades: pl.DataFrame, *, initial_capital: float) -> pl.DataFrame:
    return trades.group_by("period").agg(
        pl.len().alias("filled_n"),
        pl.col("market_return_missing").sum().alias("market_return_missing_n"),
        pl.col("actual_pnl").sum().alias("actual_pnl"),
        pl.col("market_pnl").sum().alias("market_pnl"),
        pl.col("stock_pnl").sum().alias("stock_pnl"),
        pl.col("cost_pnl").sum().alias("cost_pnl"),
        (pl.col("actual_pnl").sum() / initial_capital).alias("actual_return"),
        (pl.col("market_pnl").sum() / initial_capital).alias("market_return_contribution"),
        (pl.col("stock_pnl").sum() / initial_capital).alias("stock_return_contribution"),
        (pl.col("cost_pnl").sum() / initial_capital).alias("cost_return_contribution"),
    ).sort("period")


def grouped_attribution(
    trades: pl.DataFrame,
    keys: list[str],
) -> pl.DataFrame:
    return trades.group_by(keys).agg(
        pl.len().alias("filled_n"),
        pl.col("actual_pnl").sum().alias("actual_pnl"),
        pl.col("market_pnl").sum().alias("market_pnl"),
        pl.col("stock_pnl").sum().alias("stock_pnl"),
        pl.col("cost_pnl").sum().alias("cost_pnl"),
        pl.col("net_return").mean().alias("mean_net_return"),
        pl.col("allocated").sum().alias("allocated"),
    ).sort(keys)


def selection_execution_comparison(
    selected: dict[str, pl.DataFrame],
    filled: pl.DataFrame,
) -> pl.DataFrame:
    filled_keys = filled.select("period", "symbol", "date").with_columns(
        pl.lit("filled").alias("status"),
    )
    rows = []
    for period, chosen in selected.items():
        joined = chosen.join(
            filled_keys.filter(pl.col("period") == period),
            on=["period", "symbol", "date"],
            how="left",
        ).with_columns(pl.col("status").fill_null("selected_not_filled"))
        rows.append(joined)
    combined = pl.concat(rows, how="diagonal_relaxed")
    return combined.group_by("period", "status").agg(
        pl.len().alias("n"),
        pl.col("net_return").mean().alias("mean_net_return"),
        pl.col("net_return").median().alias("median_net_return"),
        (pl.col("net_return") > 0).mean().alias("win_rate"),
        (pl.col("net_return") * PORTFOLIO_DEFAULTS["initial_capital"]
         * PORTFOLIO_DEFAULTS["position_pct"]).sum().alias("counterfactual_5pct_pnl"),
    ).sort("period", "status")


def concentration_stats(
    trades: pl.DataFrame,
    *,
    fraction: float = CONCENTRATION_FRACTION,
) -> pl.DataFrame:
    rows = []
    for period in sorted(trades["period"].unique().to_list()):
        pnl = trades.filter(pl.col("period") == period)["actual_pnl"].sort().to_numpy()
        count = max(1, int(len(pnl) * fraction))
        rows.append({
            "period": period,
            "n": len(pnl),
            "tail_n": count,
            "worst_tail_pnl": float(pnl[:count].sum()),
            "best_tail_pnl": float(pnl[-count:].sum()),
            "total_pnl": float(pnl.sum()),
        })
    return pl.DataFrame(rows)


def write_results(path: Path, report: dict) -> None:
    lines = [
        "# Auction score-band loss attribution",
        "",
        f"Algorithm: `{VERSION}`.",
        "",
        f"Frozen variant: `{FROZEN_VARIANT}`.",
        "",
        f"Development gross market beta: `{report['market_beta']:.4f}`.",
        "",
        "## Period attribution",
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
        "## Selected versus filled",
        "",
        "| Period | Status | n | Mean net | Win rate |",
        "|---|---|---:|---:|---:|",
    ])
    for row in report["selection_vs_filled"]:
        lines.append(
            f"| {row['period']} | {row['status']} | {row['n']} | "
            f"{row['mean_net_return'] * 100:.3f}% | {row['win_rate'] * 100:.3f}% |",
        )
    lines.extend([
        "",
        "## Largest period-level components",
        "",
        "- Bucket, score-band and month tables are in the CSV artifacts.",
        "- Market component uses 000001.SH open-to-open from entry date to exit date.",
        "- Stock residual includes factor selection, industry and stock-specific effects.",
        "- Cost is the exact net-minus-gross return component.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_study(args: argparse.Namespace) -> dict:
    if args.output.exists():
        raise FileExistsError("Use a NEW output directory; existing runs are never overwritten")
    started = time.perf_counter()
    frozen = load_frozen_study(args.frozen_study)
    vol_threshold = float(frozen["vol_threshold"])
    filled = load_filled_trades(args.frozen_study / "trades.csv")
    filled = attach_gross_returns(filled, args.source_events)
    filled = attach_market_returns(filled, args.data_dir)
    beta = estimate_market_beta(filled)
    attributed = add_score_band(add_return_components(filled, beta))
    selected = reconstruct_selected(args.events, vol_threshold=vol_threshold)
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
                f"Attribution does not reconcile for {period}: {actual} vs {expected}",
            )

    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
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
            "This is attribution only; no rule, score band or portfolio parameter is changed.",
            "Market beta is fitted on development gross returns and clipped to [0, 2].",
            "The open-to-open index return is a market proxy for the 09:30 entry/exit window.",
        ],
    }
    args.output.mkdir(parents=True)
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
    parser.add_argument("--source-events", type=Path, required=True)
    parser.add_argument("--frozen-study", type=Path, required=True)
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
