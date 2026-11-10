"""Acceptance ①: pre-patch vs post-patch A/B on the real production pipeline.

Same config as research/s01b-20261108/prod_run_s01b.py / run_prod_inject.py:
2019-07-01..2026-10-30, 10bp, 1,000,000 cash, max 5 positions, 60% exposure,
matching=open_t+1, equal sizing, holding_days=60, S01 execution caliber injected
in memory (entry_price_basis=raw / block_limit_open / finalize_open_at_end /
min_commission=5 + transfer 2e-6).  The file on disk is never modified.

Prints, for the record:
  * the strategy file the engine actually loaded (path + sha256 + the cross_down line)
so the A/B cannot silently compare the same code twice.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
PROJECT = PARENT.parents[1]
DATA_ROOT = PARENT / "data_root"
os.environ["DATA_DIR"] = str(DATA_ROOT)
sys.path.insert(0, str(PROJECT / "backend"))

import polars as pl  # noqa: E402
from app.backtest.engine import BacktestEngine  # noqa: E402
from app.backtest.strategy import (  # noqa: E402
    StrategyBacktestConfig,
    StrategyBacktestService,
)
from app.config import settings  # noqa: E402
from app.strategy.engine import StrategyEngine  # noqa: E402
from app.tickflow.repository import DataStore, KlineRepository  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategies-dir", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--inject-defaults", default=str(HERE / "s01_defaults.json"))
    args = ap.parse_args()

    assert Path(settings.data_dir) == DATA_ROOT, "data_dir is not the research root; refusing"

    service = StrategyBacktestService(
        BacktestEngine(KlineRepository(DataStore(settings.data_dir))),
        StrategyEngine(strategy_dirs=[Path(args.strategies_dir)]),
    )
    s = service.strategy_engine.get("custom_mw7fvp17")
    src_bytes = Path(s.file_path).read_bytes()
    src_text = src_bytes.decode("utf-8")
    line = next((ln.strip() for ln in src_text.splitlines() if ln.strip().startswith("cross_down")), "<missing>")
    print(f"[file] path={s.file_path}")
    print(f"[file] size={len(src_bytes)} sha256={hashlib.sha256(src_bytes).hexdigest()}")
    print(f"[file] {line}")
    print(f"[meta] id={s.meta['id']} name={s.meta['name']} tags={s.meta['tags']} "
          f"backtest_defaults_in_file={s.meta.get('backtest_defaults')}")
    print(f"[risk] stop_loss={s.stop_loss} max_hold={s.max_hold_days}")

    injected = None
    if args.inject_defaults:
        injected = json.loads(Path(args.inject_defaults).read_text(encoding="utf-8"))
        s.meta["backtest_defaults"] = injected  # in-memory only
        print(f"[inject] backtest_defaults <- {json.dumps(injected, ensure_ascii=False)}")

    outdir = HERE / "results" / args.tag
    outdir.mkdir(parents=True, exist_ok=True)

    config = StrategyBacktestConfig(
        strategy_id="custom_mw7fvp17", symbols=None,
        start=date(2019, 7, 1), end=date(2026, 10, 30),
        params={}, overrides={}, matching="open_t+1",
        commission_pct=0.0003, stamp_tax_pct=0.001, slippage_bps=10.0,
        max_positions=5, max_exposure_pct=0.6,
        initial_capital=1_000_000.0, position_sizing="equal", mode="position",
        asset_type="stock", holding_days=60, minute_fill=False,
        carry_state=None, carry_out=False,
    )
    t0 = time.perf_counter()
    result = service.run(config)
    elapsed = time.perf_counter() - t0

    trades = pl.DataFrame(result.trades) if result.trades else pl.DataFrame()
    equity = pl.DataFrame(result.equity_curve) if result.equity_curve else pl.DataFrame()
    if not trades.is_empty():
        trades.write_parquet(outdir / "trades.parquet")
    if not equity.is_empty():
        equity.write_parquet(outdir / "equity.parquet")
    out = {
        "tag": args.tag, "strategies_dir": args.strategies_dir,
        "strategy_file": str(s.file_path),
        "strategy_file_size": len(src_bytes),
        "strategy_file_sha256": hashlib.sha256(src_bytes).hexdigest(),
        "cross_down_line": line,
        "injected_defaults": injected,
        "elapsed_s": round(elapsed, 1), "error": result.error,
        "stats": result.stats, "n_trades": len(trades), "n_equity": len(equity),
        "run_id": result.run_id, "effective_config": result.config,
    }
    (outdir / "result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str),
                                        encoding="utf-8")
    print(f"[run] error={result.error} trades={len(trades)} equity={len(equity)} elapsed={elapsed:.1f}s")
    for k in ("total_return", "annual_return", "max_drawdown", "sharpe", "n_trades",
              "completed_trade_count", "open_at_end_count", "avg_holding_days", "final_equity"):
        print(f"[stat] {k}={result.stats.get(k)}")
    return 0 if not result.error else 1


if __name__ == "__main__":
    sys.exit(main())
