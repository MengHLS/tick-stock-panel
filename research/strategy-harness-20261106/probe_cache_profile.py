"""诊断：预热 profile 与各策略 prepare 时的 cache profile 是否同代。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.backtest.engine import BacktestEngine
from app.backtest.strategy import (
    StrategyBacktestService,
    StrategyDependencyResolver,
    build_matrix_cache_profile,
)
from app.config import settings
from app.strategy.engine import StrategyEngine
from app.tickflow.repository import DataStore, KlineRepository

repo = KlineRepository(DataStore(settings.data_dir))
engine = BacktestEngine(repo)
sengine = StrategyEngine(strategy_dirs=[])
service = StrategyBacktestService(engine, sengine)

base = build_matrix_cache_profile(
    sengine, "stock", max_disk_bytes=settings.backtest_matrix_cache_max_mb * 1024 * 1024
)
print("prewarm-profile generation:", base.generation)
print("  fields:", sorted(base.field_columns))
print("  warmup", base.warmup_bars, "fwd", base.forward_bars)

for sid in ("first_limit_pullback_3f_runner_t74", "first_board_chain_rebreak"):
    s = sengine.get(sid)
    overrides = {}
    from app.strategy.engine import StrategyEngine as SE  # noqa: F401
    basic_filter = service._effective_basic_filter(s, overrides)
    entry = s.entry_signals
    exit_ = s.exit_signals
    plan = StrategyDependencyResolver().resolve(
        s,
        params=service._normalize_params({}, s),
        basic_filter=basic_filter,
        entry_signals=entry,
        exit_signals=exit_,
        overrides=overrides,
        minute_fill=False,
        asset_type="stock",
    )
    prof = build_matrix_cache_profile(
        sengine,
        "stock",
        requested_plan=plan,
        requested_forward_bars=max(int(getattr(s, "max_hold_days", 0) or 5), 1),
        max_disk_bytes=settings.backtest_matrix_cache_max_mb * 1024 * 1024,
    )
    print(f"\n{sid}: prepare-profile generation {prof.generation} match_prewarm={prof.generation == base.generation}")
    print("  plan matrix cols:", sorted(plan.matrix_columns))
    print("  linkage cols:", sorted(plan.linkage_columns))
    extra = set(prof.field_columns) - set(base.field_columns)
    missing = set(base.field_columns) - set(prof.field_columns)
    print("  prof有base无:", sorted(extra), " base有prof无:", sorted(missing))
