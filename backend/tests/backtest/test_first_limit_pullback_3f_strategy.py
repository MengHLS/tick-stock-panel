from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from app.backtest.matrix import (
    MatrixPipelineConfig,
    MatrixStrategyPipeline,
    build_market_data_matrix,
    build_market_matrix_from_signals,
)
from app.strategy.engine import StrategyEngine

STRATEGY_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "strategy"
    / "research"
    / "first_limit_pullback_3f_runner_t74.py"
)


def _panel() -> pl.DataFrame:
    start = date(2025, 1, 2)
    rows = []
    for symbol in ("000001.SZ", "000002.SZ", "000003.SZ"):
        closes = [
            10.00, 10.02, 9.90, 9.94, 10.00, 10.04,
            10.08, 10.12, 10.16, 10.20, 10.24, 10.28,
            10.32, 10.36, 10.40, 10.44, 9.20,
        ]
        volumes = [100.0, 210.0] + [110.0] * (len(closes) - 2)
        boards = [1.0] + [0.0] * (len(closes) - 1)
        for index, close in enumerate(closes):
            rows.append({
                "symbol": symbol,
                "name": symbol,
                "date": start + timedelta(days=index),
                "open": close - 0.01,
                "high": close + 0.04,
                "low": close - 0.04,
                "close": close,
                "volume": volumes[index],
                "consecutive_limit_ups": boards[index],
            })
    return pl.DataFrame(rows).sort(["date", "symbol"])


def test_strategy_uses_t_minus_five_first_board_and_ranks_daily_top_three() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    assert strategy.meta["id"] == "first_limit_pullback_3f_runner_t74"
    assert strategy.execution_backend == "matrix_native"

    market = build_market_data_matrix(
        _panel(),
        field_columns={"consecutive_limit_ups"},
    )
    signals = MatrixStrategyPipeline().run(
        strategy.matrix_strategy, market, {},
        MatrixPipelineConfig(basic_filter=strategy.basic_filter, scoring={}, order_by="score", descending=True),
    )

    # T=day0 is the first board; the strategy can only emit at T+5=day5.
    assert signals.entry[:5].sum() == 0
    assert signals.entry[5].tolist() == [1, 1, 1]
    assert signals.score[5].tolist() == pytest.approx([0.85, 0.85, 0.85])
    assert signals.entry_signal_ids == ("signal_first_limit_pullback_3f",)

    execution = build_market_matrix_from_signals(
        market,
        signals,
        entry_delay_bars=1,
    )
    assert execution.entry[5].sum() == 0
    assert execution.entry[6].tolist() == [1, 1, 1]


def test_original_universe_has_no_extra_price_cap_amount_or_listing_gates() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    assert strategy.basic_filter["boards"] == ["沪主板", "深主板"]
    assert strategy.basic_filter["exclude_st"] is True
    for field in ("price_min", "price_max", "market_cap_min", "amount_min", "exclude_new_days"):
        assert not strategy.basic_filter.get(field)


def test_universe_filter_runs_before_daily_ranking() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    main = _panel().with_columns(
        pl.col("symbol").str.replace("00000", "60000").str.replace(".SZ", ".SH", literal=True)
    )
    other = main.filter(pl.col("symbol") == "600001.SH").with_columns(
        pl.lit("300001.SZ").alias("symbol")
    )
    market = build_market_data_matrix(
        pl.concat([main, other]), field_columns={"consecutive_limit_ups"},
    )
    signals = MatrixStrategyPipeline().run(
        strategy.matrix_strategy, market, {},
        MatrixPipelineConfig(basic_filter=strategy.basic_filter, scoring={}, order_by="score", descending=True),
    )
    selected = [market.symbols[i] for i in signals.entry[5].nonzero()[0]]
    assert selected == ["600001.SH", "600002.SH", "600003.SH"]


def _low_score_panel() -> pl.DataFrame:
    """回踩成立但三分项都落在最低桶: 评分 0.15, 用于验证评分下限。"""
    start = date(2025, 1, 2)
    rows = []
    for index in range(6):
        if index == 0:
            close, high, low, volume = 10.00, 10.60, 9.85, 100.0
        else:
            # 振幅 0.8/约10 ≈ 8%, 最大振幅桶 0.25; 均值振幅桶 0.10。
            close, high, low = 9.95, 10.35, 9.55
            # T+1 量比 0.4 → 成交量桶 0.10。
            volume = 40.0 if index == 1 else 100.0
        rows.append({
            "symbol": "000001.SZ",
            "name": "000001.SZ",
            "date": start + timedelta(days=index),
            "open": 10.10 if index == 0 else 9.96,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "consecutive_limit_ups": 1.0 if index == 0 else 0.0,
        })
    return pl.DataFrame(rows).sort(["date", "symbol"])


def _run_low_score(params: dict):
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    market = build_market_data_matrix(
        _low_score_panel(),
        field_columns={"consecutive_limit_ups"},
    )
    return MatrixStrategyPipeline().run(
        strategy.matrix_strategy,
        market,
        params,
        MatrixPipelineConfig(
            basic_filter=strategy.basic_filter,
            scoring={},
            order_by="score",
            descending=True,
        ),
    )


def test_min_score_pct_gates_entry_candidates() -> None:
    assert _run_low_score({}).entry.sum() == 0  # 默认下限 55
    assert _run_low_score({"min_score_pct": 55.0}).entry.sum() == 0

    admitted = _run_low_score({"min_score_pct": 10.0})
    assert admitted.entry[5].tolist() == [1]
    assert float(admitted.score[5][0]) == pytest.approx(0.45 / 3, abs=1e-6)


def test_min_score_pct_lower_bound_is_inclusive() -> None:
    assert _run_low_score({"min_score_pct": 15.0}).entry[5].tolist() == [1]
    assert _run_low_score({"min_score_pct": 15.01}).entry.sum() == 0


def test_exit_requires_both_ma5_and_ma10_breakdown() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    market = build_market_data_matrix(
        _panel(),
        field_columns={"consecutive_limit_ups"},
    )
    signals = strategy.matrix_strategy.compute_signals(market, {})

    assert signals.exit[16].tolist() == [1, 1, 1]
    assert signals.exit_signal_ids == ("signal_t74_ma5_ma10_breakdown",)


def test_backtest_defaults_pin_next_open_fills() -> None:
    """331 的已验收成交口径必须写进策略默认值, 防止选中后沿用旧表单口径。"""
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    defaults = strategy.meta["backtest_defaults"]
    assert defaults["entry_fill"] == "open_t+1"
    assert defaults["exit_fill"] == "open_t+1"
