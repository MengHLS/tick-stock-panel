from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import polars as pl

from app.backtest.execution_policy import parse_backtest_defaults
from app.backtest.matrix import (
    MatrixPipelineConfig,
    MatrixStrategyPipeline,
    build_market_data_matrix,
)
from app.strategy.engine import StrategyEngine

STRATEGY_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "khunter_strategies"
    / "custom_khunter_limit_up_pullback.py"
)


def _panel(
    limit_up_close: float = 11.0,
    *,
    exchange_limit_up: bool = True,
) -> pl.DataFrame:
    start = date(2025, 1, 2)
    closes = [
        10.00,
        10.01,
        10.00,
        10.02,
        10.01,
        10.00,
        limit_up_close,
        10.80,
        10.65,
        11.15,
    ]
    volumes = [100.0] * 6 + [250.0, 120.0, 90.0, 180.0]
    rows = []
    for index, (close, volume) in enumerate(zip(closes, volumes, strict=True)):
        rows.append(
            {
                "symbol": "000001.SZ",
                "name": "测试股份",
                "date": start + timedelta(days=index),
                "open": close * 1.01,
                "high": close * 1.02,
                "low": close * 0.99,
                "close": close,
                "raw_close": close,
                "volume": volume,
                "signal_limit_up": index == 6 and exchange_limit_up,
            }
        )
    return pl.DataFrame(rows)


def _signals(panel: pl.DataFrame):
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    market = build_market_data_matrix(panel, field_columns={"raw_close"})
    return MatrixStrategyPipeline().run(
        strategy.matrix_strategy,
        market,
        {},
        MatrixPipelineConfig(
            basic_filter=strategy.basic_filter,
            scoring={},
            order_by="score",
            descending=True,
        ),
    )


def test_emits_after_limit_up_shrink_pullback_and_volume_recovery() -> None:
    signals = _signals(_panel())

    assert signals.entry[:-1].sum() == 0
    assert signals.entry[-1].tolist() == [1]
    assert signals.score[-1, 0] > 0


def test_fixed_9_9_percent_rise_is_not_treated_as_limit_up() -> None:
    signals = _signals(
        _panel(limit_up_close=10.99, exchange_limit_up=False)
    )

    assert signals.entry.sum() == 0


def test_historical_prefix_is_unchanged_by_future_bars() -> None:
    panel = _panel()
    prefix = _signals(panel.head(9))
    full = _signals(panel)

    assert prefix.entry.tolist() == full.entry[:9].tolist()


def test_daily_signal_uses_next_open_execution() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    policy = parse_backtest_defaults(strategy.meta["backtest_defaults"])

    assert strategy.meta["backtest_defaults"]["entry_fill"] == "open_t+1"
    assert strategy.meta["backtest_defaults"]["exit_fill"] == "open_t+1"
    assert policy.plan_at_signal_close is True
    assert policy.score_tiers == ((0.0, 0.0), (0.55, 0.20), (0.72, 0.25))
