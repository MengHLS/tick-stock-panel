from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import polars as pl

PROJECT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT / "backend"))

from app.config import settings  # noqa: E402
from app.extensions.adapters import FileMarketData  # noqa: E402


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    results = root / "results"
    report = json.loads((results / "constrained-validation.json").read_text(encoding="utf-8"))
    source = root / "scripts/validate_candidates.py"
    checks = {
        "source_matches_run": (
            hashlib.sha256(source.read_bytes()).hexdigest() == report["source_sha256"]
        ),
        "completed": report.get("completed") is True,
        "all_prefix_samples_stable": all(fold["prefix_stable"] for fold in report["folds"]),
        "fold_count": len(report["folds"]),
        "variants": [],
        "core_hashes": {},
    }
    for name in (
        "backend/app/backtest/engine.py",
        "backend/app/backtest/matrix.py",
        "backend/app/price_limits.py",
        "backend/app/indicators/pipeline.py",
        "backend/app/tickflow/security_status.py",
    ):
        checks["core_hashes"][name] = hashlib.sha256((PROJECT / name).read_bytes()).hexdigest()
    for fold in report["folds"]:
        for variant in fold["variants"]:
            path = results / (
                f"trades-{fold['year']}-{variant['name']}-{variant['slippage_bps']}.json"
            )
            trades = json.loads(path.read_text(encoding="utf-8"))
            checks["variants"].append({
                "year": fold["year"], "name": variant["name"],
                "slippage_bps": variant["slippage_bps"],
                "records": len(trades),
                "entry_not_after_signal": sum(
                    trade["entry_date"] <= trade["entry_signal_date"] for trade in trades
                ),
                "closed_same_day_or_before": sum(
                    trade["exit_date"] <= trade["entry_date"]
                    for trade in trades if not trade["open_at_end"]
                ),
                "exit_reasons": dict(Counter(trade["exit_reason"] for trade in trades)),
                "trades_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    action_path = settings.data_dir / "adj_factor/all.parquet"
    if action_path.exists():
        actions = pl.scan_parquet(action_path)
        schema = actions.collect_schema().names()
        checks["corporate_actions"] = {
            "columns": schema,
            "rows": actions.select(pl.len()).collect().item(),
            "first": str(actions.select(pl.col("trade_date").min()).collect().item()),
            "last": str(actions.select(pl.col("trade_date").max()).collect().item()),
        }
    market = FileMarketData(settings.data_dir)
    last = market.latest_daily_date()
    latest = market.get_daily_batch([], last, last, ["symbol", "date"])
    instruments = market.get_instruments()
    checks["latest_daily"] = {
        "date": str(last), "rows": latest.height,
        "symbols_missing_current_instruments": latest.select("symbol").unique().join(
            instruments.select("symbol").unique(), on="symbol", how="anti",
        ).height,
    }
    symbol_stats = pl.scan_parquet(
        str(settings.data_dir / "kline_daily_enriched/date=*/part.parquet")
    ).select(["symbol", "date"]).group_by("symbol").agg(
        pl.col("date").min().alias("first"),
        pl.col("date").max().alias("last"),
        pl.len().alias("bars"),
    ).collect()
    not_in_instruments = symbol_stats.join(
        instruments.select("symbol"), on="symbol", how="anti",
    )
    stopped = symbol_stats.filter(pl.col("last") < date(2026, 9, 1))
    checks["universe"] = {
        "panelled_symbols": symbol_stats.height,
        "instrument_symbols": instruments.height,
        "stopped_before_2026_09": stopped.height,
        "stopped_main_board": stopped.filter(
            pl.col("symbol").str.starts_with("60")
            | pl.col("symbol").str.starts_with("00")
        ).height,
        "not_in_current_instruments": not_in_instruments.height,
        "not_in_current_instruments_all_beijing": (
            not_in_instruments.height
            == not_in_instruments.filter(
                pl.col("symbol").str.ends_with(".BJ")
            ).height
        ),
        "stopped_samples": stopped.sort("last").head(5)["symbol"].to_list(),
        "stopped_examples_missing_from_instruments": stopped.join(
            instruments.select("symbol"), on="symbol", how="anti",
        ).height,
    }
    pit_dates = sorted(
        path.parent.name.removeprefix("date=")
        for path in (
            settings.data_dir / "ext_data/ext_hy_ths_pit/timeseries"
        ).glob("date=*/part.parquet")
    )
    checks["industry_pit"] = {
        "dates": pit_dates,
        "n_dates": len(pit_dates),
        "historical_industry_reconstruction_available": len(pit_dates) >= 250,
    }
    baseline_path = PROJECT / ".artifacts/331-parity-20261102/event_positions_rerun33.json"
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        trades = [
            trade for trade in baseline["trades"] if not trade.get("open_at_end")
        ]
        gains = sum(
            trade.get("pnl_amount", 0) for trade in trades
            if trade.get("pnl_amount", 0) > 0
        )
        losses = -sum(
            trade.get("pnl_amount", 0) for trade in trades
            if trade.get("pnl_amount", 0) < 0
        )
        checks["t74_331"] = {
            "stats": baseline["stats"],
            "event_allowlist": len(
                baseline["config"]["params"].get("_event_allowlist", [])
            ),
            "legacy_preclose_gaps": len(
                baseline["config"]["params"].get("_legacy_preclose_gaps", {})
            ),
            "legacy_corporate_action_gaps": baseline["config"]["params"].get(
                "_legacy_corporate_action_gaps", []
            ),
            "cash_profit_factor": gains / losses if losses else None,
            "closed_pnl_ge20pct": sum(
                trade.get("pnl_pct", 0) >= 0.2 for trade in trades
            ),
            "terminal_equity": baseline["equity_curve"][-1],
        }
    wfo_path = results / "wfo-t74-baseline.json"
    if wfo_path.exists():
        wfo = json.loads(wfo_path.read_text(encoding="utf-8"))
        checks["wfo_t74"] = {
            "window_basis": wfo["window_basis"],
            "n_trading_days": wfo["n_trading_days"],
            "n_folds": wfo["n_folds"],
            "n_skipped": wfo["n_skipped"],
            "summary": wfo["summary"],
            "folds": [
                {
                    "index": fold["index"],
                    "train_start": fold["train_start"],
                    "train_end": fold["train_end"],
                    "test_start": fold["test_start"],
                    "test_end": fold["test_end"],
                    "total_return": fold["oos_stats"].get("total_return"),
                    "max_drawdown": fold["oos_stats"].get("max_drawdown"),
                    "n_trades": fold["oos_stats"].get("n_trades"),
                    "statistically_insufficient": fold["statistically_insufficient"],
                }
                for fold in wfo["folds"]
            ],
        }
    ext_config = settings.data_dir / "ext_data/limit_board_events/config.json"
    try:
        json.loads(ext_config.read_text(encoding="utf-8"))
        checks["limit_board_events_config"] = "valid_json"
    except (OSError, ValueError) as exc:
        checks["limit_board_events_config"] = f"{type(exc).__name__}: {exc}"
    checks["passed"] = (
        checks["source_matches_run"]
        and checks["completed"]
        and checks["all_prefix_samples_stable"]
        and len(checks["variants"]) == 24
        and checks["t74_331"]["stats"]["total_return"] == 3.3104
        and checks["wfo_t74"]["window_basis"] == "trading_days"
        and checks["wfo_t74"]["n_folds"] == checks["wfo_t74"]["summary"]["n_folds"]
        and checks["universe"]["panelled_symbols"] > checks["universe"]["instrument_symbols"]
        and checks["universe"]["not_in_current_instruments_all_beijing"]
        and all(
            item["entry_not_after_signal"] == item["closed_same_day_or_before"] == 0
            for item in checks["variants"]
        )
    )
    target = results / "audit-checks.json"
    target.write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        key: value for key, value in checks.items() if key not in {"variants", "core_hashes"}
    }, ensure_ascii=False, indent=2))
    if not checks["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
