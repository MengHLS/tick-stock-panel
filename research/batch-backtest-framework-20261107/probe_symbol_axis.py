"""探针 2: 为什么不同字段计划下矩阵 symbol 轴不同 (5666 vs 5727)。

只读: 直接复用生产装载函数, 不改任何源码。
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.backtest.engine import BacktestEngine
from app.backtest.strategy import (
    ResolvedFeaturePlan,
    StrategyDependencyResolver,
    build_matrix_cache_profile,
)
from app.config import settings
from app.strategy import config as strategy_config
from app.strategy.engine import StrategyEngine
from app.tickflow.repository import DataStore, KlineRepository

START = date(2025, 12, 15)
END = date(2026, 3, 23)
BASE = frozenset({"symbol", "date", "open", "high", "low", "close", "volume", "raw_close", "raw_high"})


def main() -> int:
    data_dir = Path(settings.data_dir)
    repo = KlineRepository(DataStore(data_dir))
    engine = BacktestEngine(repo)
    se = StrategyEngine(
        strategy_dirs=[data_dir / "strategies"],
        override_loader=lambda sid: strategy_config.load_override(data_dir, sid),
    )
    profile = build_matrix_cache_profile(se, "stock")
    resolver = StrategyDependencyResolver()

    def plan_for(sid: str) -> ResolvedFeaturePlan:
        strategy = se.get(sid)
        params = StrategyEngine.resolve_params(strategy)
        return resolver.resolve(
            strategy,
            params=params,
            basic_filter={
                **dict(strategy.basic_filter or {}),
                "enabled": True,
                "amount_min": 0.0,
                "turnover_min": 0.0,
                "market_cap_min": 0.0,
                "float_cap_min": 0.0,
                "exclude_st": True,
            },
            entry_signals=strategy.entry_signals,
            exit_signals=strategy.exit_signals,
            overrides={},
            minute_fill=False,
            asset_type="stock",
        )

    cases = {}
    for sid in ("first_board_chain_rebreak", "first_limit_pullback_3f_runner_t74"):
        p = plan_for(sid)
        cases[sid] = frozenset(p.base_columns) | set(p.matrix_columns) | set(p.instrument_columns)
        print(sid, sorted(cases[sid]), "st=", p.historical_st)
    cases["union_groups"] = set().union(*cases.values())
    cases["profile"] = set(profile.field_columns)

    warmup = max(120, int(profile.warmup_bars * 1.6))
    for name, fields in cases.items():
        plan = ResolvedFeaturePlan(
            base_columns=BASE & frozenset(fields),
            intermediate_columns=frozenset(),
            indicator_columns=frozenset(),
            signal_columns=frozenset(),
            matrix_columns=frozenset(fields),
            instrument_columns=frozenset(),
            warmup_bars=profile.warmup_bars,
            full_feature_fallback=False,
            execution_backend="matrix_native",
            historical_st=True,
        )
        market = engine.load_market_data_matrix_for_backtest(
            None,
            START,
            END,
            plan,
            asset_type="stock",
            cache_profile=profile,
            coverage_start=START - timedelta(days=warmup),
            coverage_end=END,
        )
        print(
            name,
            "n_symbols=", len(market.symbols),
            "n_labels=", len(market.timestamp_labels),
            "cache=", market.cache_status,
        )
        del market
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
