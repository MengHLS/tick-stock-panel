"""matrix_native 风控常量实测：STOP_LOSS=None vs STOP_LOSS=-0.08（同区间同参数）。

用法（项目 venv）:
    backend\\.venv\\Scripts\\python.exe research\\matrix-native-risk-20261108\\run_risk_probe.py \
        --variant base --start 2019-07-01 --end 2021-06-30 --tag base

要点:
- data_dir 指向 research/matrix-native-risk-20261108/data_root（行情目录是 junction，
  strategies/ 是本目录内的真实目录，不是 junction），不写 D:\TSP 下任何文件。
- 走生产路径 StrategyBacktestService.run → simulate_market_matrix；不改源码。
- 在测试侧包一层 simulate_market_matrix，把撮合器实际收到的 MatcherConfig 关键风控
  字段原样打印并落盘，作为「常量是否真的进了撮合器」的运行时证据。
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
PROJECT = HERE.parents[1]
DATA_ROOT = HERE / "data_root"
STRATEGY_ID = "custom_mw7fvp17"

os.environ["DATA_DIR"] = str(DATA_ROOT)
sys.path.insert(0, str(PROJECT / "backend"))

import polars as pl  # noqa: E402

from app.backtest.engine import BacktestEngine, MatcherConfig  # noqa: E402
from app.backtest.strategy import (  # noqa: E402
    StrategyBacktestConfig,
    StrategyBacktestService,
)
from app.config import settings  # noqa: E402
from app.strategy.engine import StrategyEngine  # noqa: E402
from app.tickflow.repository import DataStore, KlineRepository  # noqa: E402

RISK_FIELDS = (
    "stop_loss_pct",
    "take_profit_pct",
    "trailing_stop_pct",
    "trailing_take_profit_activate_pct",
    "trailing_take_profit_drawdown_pct",
    "max_hold_days",
    "exit_fill",
    "entry_fill",
    "matching",
)


def install_matcher_probe(sink: dict) -> None:
    """记录撮合器实际收到的 MatcherConfig（测试侧猴子补丁，不改仓库源码）。"""
    original = BacktestEngine.simulate_market_matrix

    def wrapper(self, matrix, config, *args, **kwargs):
        sink["matcher_config"] = {
            name: getattr(config, name, "<missing>") for name in RISK_FIELDS
        }
        sink["matrix_shape"] = list(matrix.shape)
        return original(self, matrix, config, *args, **kwargs)

    BacktestEngine.simulate_market_matrix = wrapper


def build_service(variant: str) -> StrategyBacktestService:
    store = DataStore(settings.data_dir)
    repo = KlineRepository(store)
    engine = BacktestEngine(repo)
    strategy_dir = DATA_ROOT / "strategies" / variant
    if not strategy_dir.is_dir():
        raise SystemExit(f"strategy dir missing: {strategy_dir}")
    strategy_engine = StrategyEngine(strategy_dirs=[strategy_dir])
    return StrategyBacktestService(engine, strategy_engine)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True,
                    choices=["custom", "custom_sl", "custom_tp", "custom_ts", "custom_mh"])
    ap.add_argument("--start", default="2019-07-01")
    ap.add_argument("--end", default="2021-06-30")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--slippage-bps", type=float, default=10.0)
    args = ap.parse_args()

    assert Path(settings.data_dir) == DATA_ROOT, "data_dir 不是研究侧独立根，拒绝运行"
    service = build_service(args.variant)
    s = service.strategy_engine.get(STRATEGY_ID)
    strategy_facts = {
        "id": s.meta.get("id"),
        "execution_backend": s.execution_backend,
        "entry_signals": s.entry_signals,
        "exit_signals": s.exit_signals,
        "stop_loss": s.stop_loss,
        "trailing_stop": s.trailing_stop,
        "trailing_take_profit_activate": s.trailing_take_profit_activate,
        "trailing_take_profit_drawdown": s.trailing_take_profit_drawdown,
        "max_hold_days": s.max_hold_days,
        "file_path": str(s.file_path),
    }
    print("[strategy]", json.dumps(strategy_facts, ensure_ascii=False))

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
        slippage_bps=float(args.slippage_bps),
        max_positions=5,
        max_exposure_pct=0.6,
        initial_capital=1_000_000.0,
        position_sizing="equal",
        mode="position",
        asset_type="stock",
        holding_days=60,
        minute_fill=False,
    )

    sink: dict = {}
    install_matcher_probe(sink)
    t0 = time.perf_counter()
    result = service.run(config)
    elapsed = time.perf_counter() - t0

    rows = [dict(t) if isinstance(t, dict) else dict(vars(t)) for t in (result.trades or [])]
    trades = pl.DataFrame(rows) if rows else pl.DataFrame()
    if not trades.is_empty():
        trades.write_parquet(HERE / f"trades_{args.tag}.parquet")
        durations = trades["duration"].to_list()
        reason_rows = (
            trades.group_by("exit_reason").len().sort("exit_reason").to_dicts()
        )
        hold = {
            "avg_holding_days": round(sum(durations) / len(durations), 2),
            "max_holding_days": int(max(durations)),
            "min_holding_days": int(min(durations)),
        }
        pnl = trades["pnl_pct"].to_list()
        trade_stats = {
            "n_trades": len(durations),
            "avg_pnl_pct": round(sum(pnl) / len(pnl), 6),
            "win_rate": round(sum(1 for v in pnl if v > 0) / len(pnl), 4),
        }
    else:
        reason_rows, hold, trade_stats = [], {}, {}

    stats = result.stats or {}
    out = {
        "tag": args.tag,
        "variant": args.variant,
        "start": args.start,
        "end": args.end,
        "elapsed_s": round(elapsed, 1),
        "error": result.error,
        "run_id": result.run_id,
        "strategy_facts": strategy_facts,
        "matcher_config_seen_by_engine": sink.get("matcher_config"),
        "matrix_shape": sink.get("matrix_shape"),
        "headline": {
            k: stats.get(k)
            for k in (
                "total_return",
                "annual_return",
                "max_drawdown",
                "sharpe",
                "n_trades",
                "completed_trade_count",
                "open_at_end_count",
                "avg_holding_days",
                "final_equity",
            )
        },
        "trade_stats_recomputed": trade_stats,
        "holding_days_recomputed": hold,
        "exit_reason_counts": reason_rows,
        "execution": stats.get("execution"),
        "stats_full": stats,
    }
    (HERE / f"result_{args.tag}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    print("[result]", json.dumps({k: out[k] for k in ("error", "headline", "trade_stats_recomputed",
                                                     "holding_days_recomputed", "exit_reason_counts",
                                                     "matcher_config_seen_by_engine")},
                                 ensure_ascii=False, default=str))
    return 0 if not result.error else 1


if __name__ == "__main__":
    raise SystemExit(main())
