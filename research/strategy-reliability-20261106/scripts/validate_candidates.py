from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl

PROJECT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT / "backend"))

from app.backtest.engine import (  # noqa: E402
    BacktestEngine,
    ExecutionCostPolicy,
    MatcherConfig,
    SimulationOptions,
)
from app.backtest.matrix import build_market_matrix  # noqa: E402
from app.config import settings  # noqa: E402
from app.extensions.adapters import FileMarketData  # noqa: E402
from app.indicators.pipeline import compute_limit_signals  # noqa: E402
from app.price_limits import polars_price_limit_pct  # noqa: E402
from app.tickflow.repository import DataStore, KlineRepository  # noqa: E402
from app.tickflow.security_status import attach_st_history  # noqa: E402

COLUMNS = [
    "symbol", "date", "open", "high", "low", "close",
    "raw_close", "raw_high", "raw_low", "volume", "amount",
]
VARIANTS = ("momentum", "breakout_volume", "breakout_volume_market")


def fingerprint(frame: pl.DataFrame) -> str:
    return hashlib.sha256(frame.hash_rows(seed=74).to_numpy().tobytes()).hexdigest()


def signals(frame: pl.DataFrame) -> pl.DataFrame:
    frame = frame.sort(["symbol", "date"]).with_columns(
        pl.col("close").rolling_mean(20).over("symbol").alias("ma20"),
        pl.col("close").rolling_mean(60).over("symbol").alias("ma60"),
        (pl.col("close") / pl.col("close").shift(60).over("symbol") - 1).alias("mom60"),
        pl.col("high").shift(1).rolling_max(55).over("symbol").alias("prior_high55"),
        pl.col("volume").shift(1).rolling_mean(20).over("symbol").alias("prior_vol20"),
        pl.col("amount").shift(1).rolling_mean(20).over("symbol").alias("prior_amount20"),
        pl.col("date").cum_count().over("symbol").alias("observed_bars"),
    )
    frame = frame.with_columns(
        (pl.col("mom60").rank("average").over("date")
         / pl.col("mom60").count().over("date")).alias("rs"),
    )
    breadth = frame.group_by("date").agg(
        (pl.col("close") > pl.col("ma60")).filter(
            pl.col("ma60").is_not_null()
        ).mean().alias("market_breadth"),
    )
    frame = frame.join(breadth, on="date", how="left")
    eligible = (
        (pl.col("observed_bars") >= 120)
        & (pl.col("st_flag") == False)  # noqa: E712
        & (pl.col("raw_close") >= 3)
        & (pl.col("prior_amount20") >= 100_000_000)
        & (pl.col("volume") > 0)
        & (pl.col("rs") >= 0.9)
        & (pl.col("close") > pl.col("ma60"))
        & (pl.col("ma20") > pl.col("ma60"))
    )
    breakout = (
        eligible
        & (pl.col("close") > pl.col("prior_high55"))
        & (pl.col("volume") > 1.5 * pl.col("prior_vol20"))
    )
    return frame.with_columns(
        eligible.fill_null(False).alias("momentum"),
        breakout.fill_null(False).alias("breakout_volume"),
        (breakout & (pl.col("market_breadth") >= 0.5)).fill_null(False)
        .alias("breakout_volume_market"),
        (pl.col("close") < pl.col("ma20")).fill_null(False).alias("exit"),
        pl.col("mom60").fill_null(0).alias("score"),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", default="2023,2024,2025,2026")
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 10, 30))
    parser.add_argument(
        "--output", type=Path,
        default=PROJECT / "research/strategy-reliability-20261106/results/validation.json",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    market = FileMarketData(settings.data_dir)
    instruments = market.get_instruments()
    history = market.get_st_history()
    store = DataStore(settings.data_dir)
    engine = BacktestEngine(KlineRepository(store))
    config = MatcherConfig(
        matching="open_t+1", initial_capital=1_000_000,
        max_positions=5, max_exposure_pct=0.6,
        commission_pct=0.0003, stamp_tax_pct=0.001, slippage_bps=10,
        max_hold_days=20, entry_price_basis="raw",
        block_limit_open=True, finalize_open_at_end=True,
        execution_costs=ExecutionCostPolicy(min_commission=5, transfer_fee_pct=0.00001),
    )
    datasets = {}
    for dataset in (
        "kline_daily", "kline_daily_enriched", "kline_minute",
        "kline_index_daily", "kline_etf_daily", "adj_factor",
    ):
        dates = market.dataset_partition_dates(dataset, date.min, args.end)
        datasets[dataset] = {
            "partitions": len(dates),
            "first": str(min(dates)) if dates else None,
            "last": str(max(dates)) if dates else None,
            "flat_parquet_files": len(list((settings.data_dir / dataset).glob("*.parquet"))),
        }
    report = {
        "created_at": datetime.now().astimezone().isoformat(),
        "head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True,
        ).strip(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python": sys.version, "polars": pl.__version__,
        "status": "exploratory_temporal_validation_not_independent_oos",
        "datasets": datasets, "instruments": instruments.height,
        "st_rows": history.height, "st_hash": fingerprint(history),
        "instruments_hash": fingerprint(instruments),
        "costs": asdict(config), "folds": [], "minute_samples": [],
        "limitations": [
            "No frozen pre-research holdout or independent forward sample.",
            "Historical delisted-universe completeness is unproven.",
            "Main-board SH/SZ only; no STAR/ChiNext/Beijing/ETF.",
            "No point-in-time industry membership; industry signal deferred.",
            "Daily bars cannot prove open-auction queue fills or participation capacity.",
            "Stamp tax is a fixed conservative scenario, not historical tax reconstruction.",
            "Each annual account resets; no compounded continuous-equity claim.",
            "Open positions use mark-to-market and are not executable terminal sales.",
            "Frozen raw data copies are not included; content hashes cannot restore data.",
        ],
    }

    def save() -> None:
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    save()
    try:
        for year in map(int, args.years.split(",")):
            start = date(year, 1, 1)
            end = min(date(year, 12, 31), args.end)
            if start > end:
                continue
            print(f"load {year}", flush=True)
            frame = market.get_daily_batch([], start - timedelta(days=400), end, COLUMNS)
            frame = frame.filter(
                pl.col("symbol").str.starts_with("60")
                | pl.col("symbol").str.starts_with("00")
            ).sort(["symbol", "date"])
            duplicates = frame.select(pl.struct("symbol", "date").is_duplicated().sum()).item()
            if duplicates:
                raise ValueError(f"duplicate symbol/date rows: {duplicates}")
            frame = attach_st_history(frame, history)
            frame = compute_limit_signals(
                frame, instruments, needed={"limit_up_price", "limit_down_price"},
            ).with_columns(
                (pl.col("raw_close") >= pl.col("limit_up_price")).fill_null(False)
                .alias("signal_limit_up"),
                (pl.col("raw_close") <= pl.col("limit_down_price")).fill_null(False)
                .alias("signal_limit_down"),
                polars_price_limit_pct(
                    pl.col("symbol"), pl.col("date"), pl.col("st_flag"),
                ).alias("price_limit_pct"),
            )
            identity = fingerprint(frame)
            prepared = signals(frame)
            available = sorted(prepared.filter(pl.col("date") >= start)["date"].unique())
            if not available:
                raise ValueError(f"no dates for {year}")
            cutoff = available[len(available) // 2]
            prefix = signals(frame.filter(pl.col("date") <= cutoff))
            compare = ["symbol", "date", "score", "exit", *VARIANTS]
            prefix_stable = prepared.filter(pl.col("date") <= cutoff).select(compare).equals(
                prefix.select(compare),
            )
            if not prefix_stable:
                raise ValueError("signal prefix changed after removing future rows")
            fold = {
                "year": year, "start": str(available[0]), "end": str(available[-1]),
                "rows_including_warmup": frame.height,
                "symbols_including_warmup": frame["symbol"].n_unique(),
                "data_hash": identity, "prefix_cutoff": str(cutoff),
                "prefix_stable": prefix_stable,
                "unknown_st_rows": frame["st_flag"].null_count(), "variants": [],
            }
            sim = prepared.filter(pl.col("date") >= start)
            index_frames = [
                market.read_dataset_partition("kline_index_daily", day)
                for day in (available[0], available[-1])
            ]
            if all(not part.is_empty() for part in index_frames):
                benchmark = index_frames[0].select("symbol", pl.col("close").alias("first")).join(
                    index_frames[1].select("symbol", pl.col("close").alias("last")),
                    on="symbol", how="inner",
                )
                fold["index_price_returns"] = benchmark.with_columns(
                    (pl.col("last") / pl.col("first") - 1).alias("return"),
                ).filter(pl.col("symbol") == "000001.SH").to_dicts()
            else:
                fold["index_price_returns"] = None
            report["folds"].append(fold)
            for variant in VARIANTS:
                for slippage in (10, 30):
                    config.slippage_bps = slippage
                    matrix = build_market_matrix(
                        sim, sim[variant], sim["exit"],
                        entry_delay_bars=1, exit_delay_bars=1,
                    )
                    result = engine.simulate_market_matrix(
                        matrix, config,
                        options=SimulationOptions(include_monte_carlo=False),
                    )
                    closed = [trade for trade in result.trades if not trade.open_at_end]
                    turnover = sum(
                        trade.entry_value + (0 if trade.open_at_end else trade.exit_value)
                        for trade in result.trades
                    ) / config.initial_capital
                    pnl = np.array([trade.pnl_amount for trade in closed], dtype=float)
                    loss = -float(pnl[pnl < 0].sum())
                    record = {
                        "name": variant, "slippage_bps": slippage,
                        "signals": int(sim[variant].sum()), "stats": result.stats,
                        "gross_traded_over_initial_capital": turnover,
                        "cash_profit_factor": float(pnl[pnl > 0].sum()) / loss if loss else None,
                        "closed_pnl_ge20pct": sum(trade.pnl_pct >= 0.2 for trade in closed),
                        "trade_samples": [asdict(trade) for trade in result.trades[:5]],
                    }
                    fold["variants"].append(record)
                    trades_path = args.output.parent / f"trades-{year}-{variant}-{slippage}.json"
                    trades_path.write_text(json.dumps(
                        [asdict(trade) for trade in result.trades],
                        ensure_ascii=False, indent=2, default=str,
                    ), encoding="utf-8")
                    print(year, variant, slippage, result.stats["total_return"],
                          result.stats.get("max_drawdown"), len(closed), flush=True)
                    save()
            save()
        minute_dates = market.list_minute_dates(date(2026, 1, 1), args.end)
        for day in minute_dates[-2:]:
            minute = market.get_minute_batch([], day)
            report["minute_samples"].append({
                "date": str(day), "rows": minute.height,
                "symbols": minute["symbol"].n_unique() if "symbol" in minute.columns else None,
                "columns": minute.columns,
            })
        report["completed"] = True
    except Exception as exc:
        report["completed"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        save()
        store.db.close()
    print(args.output, flush=True)


if __name__ == "__main__":
    main()
