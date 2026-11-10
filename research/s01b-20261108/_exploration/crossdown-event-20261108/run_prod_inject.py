"""Same pipeline as research/s01b-20261108/prod_run_s01b.py (identical StrategyBacktestConfig,
identical data_root junction, identical costs/matching), plus one extra, OPTIONAL knob:

    --inject-defaults <json>

It sets `strategy.meta["backtest_defaults"]` on the already-loaded StrategyDef **in memory only**
(the file on disk is never touched) so we can run the production strategy file under the S01
experiment's execution口径 (entry_price_basis=raw / block_limit_open / finalize_open_at_end /
min_commission=5 + transfer 2e-6) and check whether the 199-trade reference reproduces.

Why it is needed: the production baseline file declares no `backtest_defaults`, so
app/backtest/execution_policy.py falls back to its own defaults
(entry_price_basis="adjusted", block_limit_open=False, finalize_open_at_end=False,
execution_costs=None) — a different execution口径 from the S01b research arms.
The A/B (before vs after the cross_down change) is unaffected: both sides run the same policy.
"""
from __future__ import annotations

import argparse
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


def build_service(strategy_dir: Path) -> StrategyBacktestService:
    store = DataStore(settings.data_dir)
    engine = BacktestEngine(KlineRepository(store))
    return StrategyBacktestService(engine, StrategyEngine(strategy_dirs=[strategy_dir]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy-id", default="custom_mw7fvp17")
    ap.add_argument("--strategies-dir", default=r"D:\TSP\data\strategies\custom")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--start", default="2019-07-01")
    ap.add_argument("--end", default="2026-10-30")
    ap.add_argument("--slippage-bps", type=float, default=10.0)
    ap.add_argument("--max-positions", type=int, default=5)
    ap.add_argument("--max-exposure-pct", type=float, default=0.6)
    ap.add_argument("--holding-days", type=int, default=60)
    ap.add_argument("--inject-defaults", default="")
    args = ap.parse_args()

    assert Path(settings.data_dir) == DATA_ROOT, "data_dir is not the research root; refusing"
    outdir = HERE / "results" / args.tag
    outdir.mkdir(parents=True, exist_ok=True)

    service = build_service(Path(args.strategies_dir))
    s = service.strategy_engine.get(args.strategy_id)

    injected = None
    if args.inject_defaults:
        injected = json.loads(Path(args.inject_defaults).read_text(encoding="utf-8"))
        s.meta["backtest_defaults"] = injected  # in-memory only, file untouched
        print(f"[inject] backtest_defaults <- {json.dumps(injected, ensure_ascii=False)}")

    print(f"[strategy] id={s.meta['id']} name={s.meta['name']} backend={s.execution_backend}")
    print(f"[strategy] stop_loss={s.stop_loss} max_hold={s.max_hold_days}")

    config = StrategyBacktestConfig(
        strategy_id=args.strategy_id, symbols=None,
        start=date.fromisoformat(args.start), end=date.fromisoformat(args.end),
        params={}, overrides={}, matching="open_t+1",
        commission_pct=0.0003, stamp_tax_pct=0.001, slippage_bps=float(args.slippage_bps),
        max_positions=args.max_positions, max_exposure_pct=args.max_exposure_pct,
        initial_capital=1_000_000.0, position_sizing="equal", mode="position",
        asset_type="stock", holding_days=args.holding_days, minute_fill=False,
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
        "tag": args.tag, "strategy_id": args.strategy_id, "start": args.start, "end": args.end,
        "slippage_bps": args.slippage_bps, "injected_defaults": injected,
        "elapsed_s": round(elapsed, 1), "error": result.error, "stats": result.stats,
        "n_trades": len(trades), "n_equity": len(equity), "run_id": result.run_id,
        "effective_config": result.config,
    }
    (outdir / "result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"[run] error={result.error} trades={len(trades)} equity={len(equity)} "
          f"elapsed={elapsed:.1f}s")
    if not trades.is_empty():
        print("[run] exit_reason:", trades.group_by("exit_reason").len().sort("exit_reason").to_dicts())
    for k in ("total_return", "annual_return", "max_drawdown", "sharpe", "n_trades",
              "completed_trade_count", "open_at_end_count", "avg_holding_days", "final_equity"):
        print(f"[stat] {k}={result.stats.get(k)}")
    return 0 if not result.error else 1


if __name__ == "__main__":
    sys.exit(main())
