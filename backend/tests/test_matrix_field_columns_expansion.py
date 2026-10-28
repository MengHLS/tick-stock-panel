"""每日信号路径的字段依赖展开回归测试。

挖掘发布的 FactorRankResearchMatrixStrategy 把因子权重放在类级 SCORING,
META["scoring"] 为空。每日信号/实时矩阵路径通过 _matrix_field_columns 决定
矩阵字段, 必须展开 required_fields_for_params 的虚拟因子依赖
(limit_up_count_* -> consecutive_limit_ups), 否则 compute_signals 抛
"MarketDataMatrix missing field: consecutive_limit_ups"。
"""
from __future__ import annotations

import types
from datetime import date, timedelta

import numpy as np
import polars as pl

from app.backtest.matrix import build_market_data_matrix
from app.backtest.strategy import StrategyBacktestService, StrategyDependencyResolver
from app.strategy.engine import StrategyDef, StrategyEngine
from app.strategy.research.factor_rank_research import FactorRankResearchMatrixStrategy


def _mined_limit_up_strategy() -> types.SimpleNamespace:
    strategy = FactorRankResearchMatrixStrategy(
        {"amplitude": 2.0, "limit_up_count_60d": 1.0},
        {"amplitude": "low", "limit_up_count_60d": "low"},
    )
    return types.SimpleNamespace(
        matrix_strategy=strategy,
        basic_filter=None,
        meta={"scoring": {}},
    )


def test_matrix_field_columns_expand_parameter_scoring_dependencies():
    strategy = _mined_limit_up_strategy()
    fields = StrategyEngine._matrix_field_columns(strategy, None, {})
    assert "consecutive_limit_ups" in fields
    assert "amplitude" in fields


def test_mined_limit_up_strategy_signals_build_from_panel_fields():
    rows = []
    start = date(2024, 1, 1)
    for offset in range(80):
        close = 10.0 + offset * 0.04
        rows.append({
            "symbol": "000001.SZ",
            "date": start + timedelta(days=offset),
            "open": close - 0.05,
            "high": close + 0.15,
            "low": close - 0.15,
            "close": close,
            "volume": 1000.0 + offset * 5.0,
            "amount": 100000.0,
            "amplitude": 1.5,
            "turnover_rate": 5.0,
            "consecutive_limit_ups": (offset % 17) + 1 if offset % 17 == 0 else 0,
        })
    panel = pl.DataFrame(rows)
    strategy = _mined_limit_up_strategy()
    market = build_market_data_matrix(
        panel,
        field_columns=StrategyEngine._matrix_field_columns(strategy, None, {}),
    )
    signals = strategy.matrix_strategy.compute_signals(market, {})
    assert signals.shape == market.shape


def _overlay_strategy() -> StrategyDef:
    return StrategyDef(
        meta={"id": "overlay", "name": "overlay", "scoring": {}},
        basic_filter={"enabled": False},
        entry_signals=[],
        exit_signals=[],
        stop_loss=None,
        trailing_stop=None,
        trailing_take_profit_activate=None,
        trailing_take_profit_drawdown=None,
        max_hold_days=None,
        filter_fn=None,
        filter_history_fn=None,
        lookback_days=1,
        source="custom",
        execution_backend="matrix_native",
        matrix_strategy=_mined_limit_up_strategy().matrix_strategy,
    )


def test_overlay_virtual_factor_expands_to_storage_dependency():
    overrides = {
        "overlay_filter": [{
            "left": "limit_up_count_60d",
            "op": "<=",
            "right": "5",
            "leftDays": 0,
            "rightDays": 0,
        }],
    }
    plan = StrategyDependencyResolver().resolve(
        _overlay_strategy(),
        params={},
        basic_filter={"enabled": False},
        entry_signals=[],
        exit_signals=[],
        overrides=overrides,
    )

    assert "consecutive_limit_ups" in plan.matrix_columns
    assert "limit_up_count_60d" not in plan.matrix_columns
    assert plan.warmup_bars >= 61


def test_overlay_matrix_mask_computes_virtual_factor_from_dependency():
    rows = []
    start = date(2024, 1, 1)
    for offset in range(70):
        rows.append({
            "symbol": "000001.SZ",
            "date": start + timedelta(days=offset),
            "open": 10.0,
            "high": 10.1,
            "low": 9.9,
            "close": 10.0,
            "volume": 1000.0,
            "consecutive_limit_ups": 1 if offset < 5 else 0,
        })
    market = build_market_data_matrix(
        pl.DataFrame(rows),
        field_columns={"consecutive_limit_ups"},
    )
    mask, error = StrategyBacktestService._overlay_matrix_mask(
        market,
        [{
            "left": "limit_up_count_60d",
            "op": "<=",
            "right": "5",
            "leftDays": 0,
            "rightDays": 0,
        }],
    )

    assert error is None
    assert mask is not None
    assert np.isfinite(mask).all()
    assert mask[-1, 0]
