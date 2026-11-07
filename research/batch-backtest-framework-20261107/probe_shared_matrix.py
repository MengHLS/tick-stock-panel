"""探针: 切片级共享矩阵装载 + 单次 matrix_native 回测耗时/内存。

只读调用生产代码, 不写入任何生产数据 (矩阵磁盘缓存由生产逻辑自行管理)。
用法:
    backend/.venv/Scripts/python.exe research/batch-backtest-framework-20261107/probe_shared_matrix.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

import psutil
from app.backtest.engine import BacktestEngine
from app.backtest.strategy import (
    BacktestResultPolicy,
    ResolvedFeaturePlan,
    StrategyBacktestConfig,
    StrategyBacktestService,
    build_matrix_cache_profile,
)
from app.config import settings
from app.factors.ext_factors import ensure_synced
from app.factors.store import load_into_registry
from app.strategy import config as strategy_config
from app.strategy.engine import StrategyEngine
from app.tickflow.repository import DataStore, KlineRepository

START = date(2024, 12, 2)
END = date(2026, 10, 31)
BASE_COLUMNS = frozenset(
    {"symbol", "date", "open", "high", "low", "close", "volume", "raw_close", "raw_high"}
)


def rss_mb() -> float:
    return psutil.Process().memory_info().rss / 1024 / 1024


def main() -> int:
    data_dir = Path(settings.data_dir)
    load_into_registry(data_dir)
    ensure_synced(data_dir)
    repo = KlineRepository(DataStore(data_dir))
    strategy_engine = StrategyEngine(
        strategy_dirs=[data_dir / "strategies"],
        override_loader=lambda sid: strategy_config.load_override(data_dir, sid),
    )
    engine = BacktestEngine(repo)
    service = StrategyBacktestService(engine, strategy_engine)

    trading_days = repo.list_enriched_dates(START, END)
    print(json.dumps({"trading_days": len(trading_days)}, ensure_ascii=False))

    t0 = time.perf_counter()
    profile = build_matrix_cache_profile(strategy_engine, "stock", requested_forward_bars=0)
    t_profile = time.perf_counter() - t0
    print(json.dumps({
        "profile_elapsed_s": round(t_profile, 2),
        "field_columns": sorted(profile.field_columns),
        "warmup_bars": profile.warmup_bars,
        "forward_bars": profile.forward_bars,
        "generation": profile.generation,
    }, ensure_ascii=False))

    plan = ResolvedFeaturePlan(
        base_columns=BASE_COLUMNS,
        intermediate_columns=frozenset(),
        indicator_columns=frozenset(),
        signal_columns=frozenset(),
        matrix_columns=frozenset(profile.field_columns) | BASE_COLUMNS,
        instrument_columns=frozenset({"name"}),
        warmup_bars=profile.warmup_bars,
        full_feature_fallback=False,
        execution_backend="matrix_native",
        historical_st=True,
    )
    warmup_days = max(120, int(profile.warmup_bars * 1.6))
    coverage_start = START - timedelta(days=warmup_days)

    rss_before = rss_mb()
    t0 = time.perf_counter()
    market = engine.load_market_data_matrix_for_backtest(
        None,
        START,
        END,
        plan,
        asset_type="stock",
        cache_profile=profile,
        coverage_start=coverage_start,
        coverage_end=END,
    )
    t_load = time.perf_counter() - t0
    print(json.dumps({
        "load_elapsed_s": round(t_load, 2),
        "shape": list(market.shape) if hasattr(market, "shape") else [
            len(market.timestamp_labels), len(market.symbols)
        ],
        "n_labels": len(market.timestamp_labels),
        "n_symbols": len(market.symbols),
        "bytes_mb": round(market.nbytes / 1024 / 1024, 1),
        "cache_status": market.cache_status,
        "cache_path": str(market.cache_path),
        "rss_before_mb": round(rss_before, 1),
        "rss_after_mb": round(rss_mb(), 1),
    }, ensure_ascii=False))

    first_label = market.timestamp_labels[0][:10]
    last_label = market.timestamp_labels[-1][:10]
    print(json.dumps({"label_first": first_label, "label_last": last_label}))

    # 单策略单次回测 (共享矩阵视图)
    sid = "first_board_chain_rebreak"
    cfg = StrategyBacktestConfig(
        strategy_id=sid,
        symbols=None,
        start=date(2026, 1, 5),
        end=date(2026, 3, 31),
        params={},
        mode="position",
    )
    t0 = time.perf_counter()
    prepared = service.prepare_matrix_optimization([cfg], market_data_override=market)
    t_prep = time.perf_counter() - t0
    policy = BacktestResultPolicy(
        required_stats=None,
        include_monte_carlo=False,
        include_curves=False,
        include_trades=False,
        include_per_symbol_stats=False,
        include_return_distribution=False,
        include_benchmark=False,
        include_strategy_info=False,
    )
    t0 = time.perf_counter()
    res = service.run(cfg, prepared=prepared, result_policy=policy)
    t_run = time.perf_counter() - t0
    prepared.compute_cache.close()
    print(json.dumps({
        "prepare_slice_s": round(t_prep, 2),
        "run_s": round(t_run, 2),
        "error": res.error,
        "stats_keys": sorted(res.stats)[:40],
        "n_trades": res.stats.get("n_trades"),
        "sortino": res.stats.get("sortino"),
        "total_return": res.stats.get("total_return"),
    }, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
