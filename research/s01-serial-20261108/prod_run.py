"""S01 账户门/信号门 —— 经生产路径 StrategyBacktestService 跑全期。

用法（必须用项目 venv）:
    backend\\.venv\\Scripts\\python.exe research\\s01-serial-20261108\\prod_run.py
    backend\\.venv\\Scripts\\python.exe research\\s01-serial-20261108\\prod_run.py --start 2023-01-01 --end 2023-06-30 --tag smoke

要点:
- data_dir 指向 research/s01-serial-20261108/data_root（junction 只读挂生产数据，
  自身 user_data 独立），因此不会写 D:\\TSP\\data 下的任何 strategy row / 覆盖。
- 生产引擎与策略都走正式加载器（StrategyEngine 从 strategies/custom/*.py 读定义、
  compute_indicators/compute_signals 注入 csg/signal_ 列、_evaluate_panel_decisions
  产候选/买点/卖点、simulate_market_matrix 撮合）。
- 决策掩码通过 evidence 钩子（check_panel 收到的 decision frame）原样落盘，
  供信号门逐日比对；不改任何源码。
"""
from __future__ import annotations

import argparse
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

# 必须在 import app.config 之前设置（Settings 从环境变量读 data_dir）
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

STRATEGY_ID = "s01_ma_cross_20_60"


class Capture:
    """evidence 钩子: 抓 decision frame（候选/买点/卖点），其余检查全部跳过。"""

    def __init__(self) -> None:
        self.decisions: pl.DataFrame | None = None
        self.frame_sizes: dict[str, int] = {}

    def check_panel(self, baseline, evaluate) -> None:
        self.decisions = baseline.clone()

    def check_matrix(self, *args, **kwargs) -> None:
        return None

    def record_frame(self, name, frame) -> None:
        try:
            self.frame_sizes[name] = int(frame.height)
        except Exception:
            self.frame_sizes[name] = -1

    def __getattr__(self, item):  # 其余可选钩子一律 no-op
        def _noop(*args, **kwargs):
            return None

        return _noop


class PeakMem:
    """采样进程 RSS 峰值（只读 psutil，不改任何业务代码）。"""

    def __init__(self, interval: float = 1.0) -> None:
        self.interval = interval
        self.peak = 0.0
        self.samples = 0
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
                rss = proc.memory_info().rss / 2**30
                self.peak = max(self.peak, rss)
                self.samples += 1
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


def build_service() -> StrategyBacktestService:
    store = DataStore(settings.data_dir)
    repo = KlineRepository(store)
    engine = BacktestEngine(repo)
    strategy_engine = StrategyEngine(
        strategy_dirs=[HERE / "strategies" / "custom"],
    )
    return StrategyBacktestService(engine, strategy_engine)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2019-07-01")
    ap.add_argument("--end", default="2026-10-30")
    ap.add_argument("--tag", default="full")
    ap.add_argument("--slippage-bps", type=float, default=10.0)
    ap.add_argument("--gross", action="store_true", help="零成本零滑点（仅残差归因用）")
    args = ap.parse_args()

    print(f"[env] settings.data_dir={settings.data_dir}")
    assert Path(settings.data_dir) == DATA_ROOT, "data_dir 不是研究侧独立根，拒绝运行"

    service = build_service()
    print("[strategy] loaded:", [d.get("id") for d in service.strategy_engine.list_strategies()])
    s = service.strategy_engine.get(STRATEGY_ID)
    print("[strategy] entry_signals", s.entry_signals, "exit_signals", s.exit_signals,
          "max_hold_days", s.max_hold_days, "backend", s.execution_backend)
    print("[strategy] backtest_defaults", json.dumps(s.meta.get("backtest_defaults"), ensure_ascii=False))

    gross = args.gross
    config = StrategyBacktestConfig(
        strategy_id=STRATEGY_ID,
        symbols=None,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        params={},
        overrides={},
        matching="open_t+1",
        commission_pct=0.0 if gross else 0.0003,
        stamp_tax_pct=0.0 if gross else 0.001,
        slippage_bps=0.0 if gross else float(args.slippage_bps),
        max_positions=5,
        max_exposure_pct=0.6,
        initial_capital=1_000_000.0,
        position_sizing="equal",
        mode="position",
        asset_type="stock",
        holding_days=60,
        minute_fill=False,
    )

    cap = Capture()
    mem = PeakMem().start()
    t0 = time.perf_counter()
    try:
        result = service.run(config, evidence=cap)
    finally:
        peak_gb = mem.stop()
    elapsed = time.perf_counter() - t0
    print(f"[mem] peak_rss_gb={peak_gb} samples={mem.samples}")

    out = {
        "tag": args.tag,
        "data_dir": str(settings.data_dir),
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
        "config": result.config,
        "run_id": result.run_id,
        "n_trades": len(result.trades or []),
        "n_equity": len(result.equity_curve or []),
        "frame_sizes": cap.frame_sizes,
    }
    (HERE / f"prod_{args.tag}_result.json").write_text(
        json.dumps({k: v for k, v in out.items() if k != "trades"}, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8",
    )

    if result.error:
        print("[ERROR]", result.error)
        return 1

    trades = pl.DataFrame(result.trades) if result.trades else pl.DataFrame()
    trades.write_parquet(HERE / f"prod_{args.tag}_trades.parquet")
    equity = pl.DataFrame(result.equity_curve) if result.equity_curve else pl.DataFrame()
    equity.write_parquet(HERE / f"prod_{args.tag}_equity.parquet")

    print(f"[run] trades={len(trades)} equity={len(equity)} elapsed={elapsed:.1f}s")
    if not trades.is_empty():
        print("[run] exit_reason:", trades.group_by("exit_reason").len().sort("exit_reason").to_dicts())
        print("[run] first trade:", trades.head(1).to_dicts())
    print("[run] last equity:", equity.tail(1).to_dicts())
    print("[stats] keys:", sorted(result.stats))
    print("[stats] entry_candidates/strategy_matches:",
          result.stats.get("entry_candidates"), result.stats.get("strategy_matches"),
          "execution:", json.dumps(result.stats.get("execution"), ensure_ascii=False))

    if cap.decisions is not None:
        d = cap.decisions
        cols = [c for c in ("symbol", "date", "_audit_candidate", "_audit_entry", "_audit_exit") if c in d.columns]
        slim = d.select(cols)
        slim.write_parquet(HERE / f"prod_{args.tag}_decisions.parquet")
        print("[decisions] rows", d.height, "cols", [c for c in d.columns if c in {"ma20", "ma60", "in_universe"}])
        print("[decisions] entry", int(slim["_audit_entry"].sum()), "exit", int(slim["_audit_exit"].sum()),
              "candidate", int(slim["_audit_candidate"].sum()))
        for col in ("ma20", "ma60", "in_universe"):
            if col in d.columns:
                non_null = d.height - d[col].null_count()
                print(f"[decisions] {col}: non_null={non_null} nulls={d[col].null_count()}")
        if "in_universe" in d.columns:
            print("[decisions] in_universe==1:", int((d["in_universe"] == 1.0).sum()),
                  "==0:", int((d["in_universe"] == 0.0).sum()))
    else:
        print("[decisions] capture missing")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
