"""S01 账户门: 经生产路径 StrategyBacktestService 的分段连续账户回放。

为什么分段: 全期单进程在本机 32 GB 上 OOM（实测 1 年峰值 9.99 GB / 2 年 11.32 GB，
7.3 年单段在 141,904,752 B 的分配上失败，见 log_full.txt / prod_full10 失败日志）。
分段用的是引擎自带、专为 walk-forward 设计的结转机制
（StrategyBacktestConfig.carry_state / carry_out → SimulationOptions.carry_in/carry_out）:
现金、持仓、peak、挂单、last_close 全部原样交给下一段，段末不清算、不重置，
持有会话年龄也随 carry_state 结转（engine.py:4172 注释）。即「连续账户」而非按年重置。

用法:
  python prod_run_carry.py --start 2019-07-01 --end 2020-06-30 --tag c1 \
      [--carry-in carry_in.json] --carry-out carry_out.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import threading
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
DATA_ROOT = HERE / "data_root"
os.environ["DATA_DIR"] = str(DATA_ROOT)
sys.path.insert(0, str(PROJECT / "backend"))

import polars as pl  # noqa: E402

from app.backtest.engine import BacktestEngine, PortfolioCarryState  # noqa: E402
from app.backtest.strategy import (  # noqa: E402
    StrategyBacktestConfig,
    StrategyBacktestService,
)
from app.config import settings  # noqa: E402
from app.strategy.engine import StrategyEngine  # noqa: E402
from app.tickflow.repository import DataStore, KlineRepository  # noqa: E402

STRATEGY_ID = "s01_ma_cross_20_60"


class Capture:
    def __init__(self) -> None:
        self.decisions: pl.DataFrame | None = None

    def check_panel(self, baseline, evaluate) -> None:
        self.decisions = baseline.clone()

    def check_matrix(self, *args, **kwargs) -> None:
        return None

    def record_frame(self, name, frame) -> None:
        return None

    def __getattr__(self, item):
        def _noop(*args, **kwargs):
            return None

        return _noop


class PeakMem:
    def __init__(self, interval: float = 1.0) -> None:
        self.interval = interval
        self.peak = 0.0
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def _loop(self) -> None:
        try:
            import psutil

            proc = psutil.Process()
        except Exception:
            return
        while not self._stop.is_set():
            try:
                self.peak = max(self.peak, proc.memory_info().rss / 2**30)
            except Exception:
                return
            self._stop.wait(self.interval)

    def start(self) -> "PeakMem":
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        return self

    def stop(self) -> float:
        self._stop.set()
        if self._t is not None:
            self._t.join(timeout=2)
        return round(self.peak, 2)


def load_carry(path: Path) -> PortfolioCarryState | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return PortfolioCarryState(**payload)


def dump_carry(state: PortfolioCarryState | None, path: Path) -> dict | None:
    if state is None:
        return None
    payload = dataclasses.asdict(state)
    path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    return {
        "cash": payload.get("cash"),
        "peak": payload.get("peak"),
        "n_positions": len(payload.get("positions") or []),
        "n_pending": len(payload.get("pending_buy_plans") or []),
        "symbols": [p.get("symbol") for p in (payload.get("positions") or [])],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--carry-in", default="")
    ap.add_argument("--carry-out", default="")
    args = ap.parse_args()

    store = DataStore(settings.data_dir)
    engine = BacktestEngine(KlineRepository(store))
    strategy_engine = StrategyEngine(strategy_dirs=[HERE / "strategies" / "custom"])
    service = StrategyBacktestService(engine, strategy_engine)

    carry_in = load_carry(Path(args.carry_in)) if args.carry_in else None
    config = StrategyBacktestConfig(
        strategy_id=STRATEGY_ID,
        symbols=None,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        params={},
        overrides={},
        matching="open_t+1",
        commission_pct=0.0003,
        stamp_tax_pct=0.001,
        slippage_bps=10.0,
        max_positions=5,
        max_exposure_pct=0.6,
        initial_capital=1_000_000.0,
        position_sizing="equal",
        mode="position",
        asset_type="stock",
        holding_days=60,
        minute_fill=False,
        carry_state=carry_in,
        carry_out=True,
    )

    cap = Capture()
    mem = PeakMem().start()
    t0 = time.perf_counter()
    try:
        result = service.run(config, evidence=cap)
    finally:
        peak_gb = mem.stop()
    elapsed = time.perf_counter() - t0

    trades = pl.DataFrame(result.trades) if result.trades else pl.DataFrame()
    equity = pl.DataFrame(result.equity_curve) if result.equity_curve else pl.DataFrame()
    if not trades.is_empty():
        trades.write_parquet(HERE / f"carry_{args.tag}_trades.parquet")
    if not equity.is_empty():
        equity.write_parquet(HERE / f"carry_{args.tag}_equity.parquet")
    if cap.decisions is not None:
        d = cap.decisions
        cols = [c for c in ("symbol", "date", "_audit_candidate", "_audit_entry", "_audit_exit") if c in d.columns]
        d.select(cols).write_parquet(HERE / f"carry_{args.tag}_decisions.parquet")

    carry_info = dump_carry(result.carry_state, Path(args.carry_out)) if args.carry_out else None
    out = {
        "tag": args.tag,
        "start": args.start,
        "end": args.end,
        "carry_in_symbols": [p.get("symbol") for p in (carry_in.positions if carry_in else [])],
        "carry_out": carry_info,
        "error": result.error,
        "elapsed_s": round(elapsed, 1),
        "peak_rss_gb": peak_gb,
        "n_trades": len(trades),
        "n_equity": len(equity),
        "stats_subset": {k: result.stats.get(k) for k in (
            "total_return", "final_equity", "max_drawdown", "n_trades",
            "open_at_end_count", "completed_trade_count", "execution",
            "panel_rows", "panel_columns", "market_matrix_shape", "timing_ms",
        )},
        "run_id": result.run_id,
    }
    (HERE / f"carry_{args.tag}_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return 0 if not result.error else 1


if __name__ == "__main__":
    raise SystemExit(main())
