"""S01b 四臂回测运行器 —— 与 research/s01-serial-20261108/prod_run.py 同一口径。

口径（与 S01 串行实验一致，只把策略换成 S01b 臂）:
  StrategyBacktestService + StrategyEngine(strategy_dirs=research 侧 custom 目录)
  1,000,000 元 / 最多 5 仓 / 最大 60% 敞口 / 次日开盘撮合 / 等权
  佣金 3bp（双边）+ 印花 10bp（卖出）+ 过户 2e-6（0.02bp，按派单口径）
  + 最低佣金 5 元/笔 + 滑点 10bp（--slippage-bps 可换 30 / --gross 归零）
  entry_price_basis=raw / block_limit_open / finalize_open_at_end 由策略 META 声明。
data_dir 指向 research/s01b-20261108/data_root（junction 只读挂生产数据），
不写 D:\TSP 下任何 strategy row / 覆盖。

用法:
  backend\.venv\Scripts\python.exe research\s01b-20261108\prod_run_s01b.py \
      --strategy-id s01b_a1 --tag a1_10bp --slippage-bps 10
"""
from __future__ import annotations
import argparse
import hashlib
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
from app.backtest.engine import BacktestEngine  # noqa: E402
from app.backtest.strategy import (  # noqa: E402
    StrategyBacktestConfig,
    StrategyBacktestService,
)
from app.config import settings  # noqa: E402
from app.strategy.engine import StrategyEngine  # noqa: E402
from app.tickflow.repository import DataStore, KlineRepository  # noqa: E402


class Capture:
    """evidence 钩子: 只抓 decision frame，其余检查 no-op。"""

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


def build_service(strategy_dir: str | Path | None = None) -> StrategyBacktestService:
    store = DataStore(settings.data_dir)
    engine = BacktestEngine(KlineRepository(store))
    sd = Path(strategy_dir) if strategy_dir else (HERE / "strategies" / "custom")
    strategy_engine = StrategyEngine(strategy_dirs=[sd])
    return StrategyBacktestService(engine, strategy_engine)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy-id", required=True)
    ap.add_argument("--start", default="2019-07-01")
    ap.add_argument("--end", default="2026-10-30")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--slippage-bps", type=float, default=10.0)
    ap.add_argument("--gross", action="store_true")
    ap.add_argument("--max-positions", type=int, default=5)
    ap.add_argument("--max-exposure-pct", type=float, default=0.6)
    ap.add_argument("--holding-days", type=int, default=60)
    ap.add_argument("--carry-in", default="")
    ap.add_argument("--carry-out", default="")
    ap.add_argument("--outdir", default="")
    ap.add_argument("--strategies-dir", default="")
    args = ap.parse_args()

    outdir = Path(args.outdir) if args.outdir else (HERE / "results" / args.tag)
    outdir.mkdir(parents=True, exist_ok=True)
    assert Path(settings.data_dir) == DATA_ROOT, "data_dir 不是研究侧独立根，拒绝运行"
    service = build_service(args.strategies_dir or None)
    s = service.strategy_engine.get(args.strategy_id)
    print(f"[strategy] id={s.meta['id']} name={s.meta['name']} backend={s.execution_backend}")
    print(f"[strategy] stop_loss={s.stop_loss} trailing_stop={s.trailing_stop} "
          f"ttp_act={s.trailing_take_profit_activate} ttp_dd={s.trailing_take_profit_drawdown} "
          f"max_hold={s.max_hold_days}")
    print(f"[strategy] backtest_defaults={json.dumps(s.meta.get('backtest_defaults'), ensure_ascii=False)}")

    gross = args.gross
    carry_in = None
    if args.carry_in and Path(args.carry_in).exists():
        from app.backtest.engine import PortfolioCarryState
        carry_in = PortfolioCarryState(**json.loads(Path(args.carry_in).read_text(encoding="utf-8")))

    config = StrategyBacktestConfig(
        strategy_id=args.strategy_id,
        symbols=None,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        params={},
        overrides={},
        matching="open_t+1",
        commission_pct=0.0 if gross else 0.0003,
        stamp_tax_pct=0.0 if gross else 0.001,
        slippage_bps=0.0 if gross else float(args.slippage_bps),
        max_positions=args.max_positions,
        max_exposure_pct=args.max_exposure_pct,
        initial_capital=1_000_000.0,
        position_sizing="equal",
        mode="position",
        asset_type="stock",
        holding_days=args.holding_days,
        minute_fill=False,
        carry_state=carry_in,
        carry_out=bool(args.carry_out),
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
        trades.write_parquet(outdir / "trades.parquet")
    if not equity.is_empty():
        equity.write_parquet(outdir / "equity.parquet")
    if cap.decisions is not None:
        cols = [c for c in ("symbol", "date", "_audit_candidate", "_audit_entry", "_audit_exit")
                if c in cap.decisions.columns]
        cap.decisions.select(cols).write_parquet(outdir / "decisions.parquet")

    carry_info = None
    if args.carry_out and result.carry_state is not None:
        import dataclasses
        payload = dataclasses.asdict(result.carry_state)
        Path(args.carry_out).write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
        carry_info = {"cash": payload.get("cash"), "peak": payload.get("peak"),
                      "n_positions": len(payload.get("positions") or []),
                      "symbols": [p.get("symbol") for p in (payload.get("positions") or [])]}

    out = {
        "tag": args.tag,
        "strategy_id": args.strategy_id,
        "start": args.start,
        "end": args.end,
        "gross": gross,
        "slippage_bps": 0.0 if gross else args.slippage_bps,
        "commission_pct": 0.0 if gross else 0.0003,
        "stamp_tax_pct": 0.0 if gross else 0.001,
        "elapsed_s": round(elapsed, 1),
        "peak_rss_gb": peak_gb,
        "error": result.error,
        "stats": result.stats,
        "carry_out": carry_info,
        "run_id": result.run_id,
        "n_trades": len(trades),
        "n_equity": len(equity),
    }
    (outdir / "result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"[run] error={result.error} trades={len(trades)} equity={len(equity)} "
          f"elapsed={elapsed:.1f}s peak_rss={peak_gb}GB")
    if result.error:
        return 1
    if not trades.is_empty():
        print("[run] exit_reason:", trades.group_by("exit_reason").len().sort("exit_reason").to_dicts())
        print("[run] cols:", trades.columns)
    st = result.stats
    st = result.stats
    keys = ("total_return", "annual_return", "max_drawdown", "sharpe", "n_trades",
            "completed_trade_count", "open_at_end_count", "avg_holding_days",
            "avg_exposure", "max_exposure", "final_equity")
    for k in keys:
        print(f"[stat] {k}={st.get(k)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
