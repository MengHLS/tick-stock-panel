from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from app.backtest.engine import BacktestEngine, MatcherConfig
from app.backtest.factor import FactorBacktestService, FactorConfig
from app.backtest.matrix import (
    build_market_data_matrix,
    build_market_matrix_from_signals,
)
from app.custom.first_board_event_chain.compute import (
    EVENT_CHAIN_FIELDS,
    compute_event_chain_outputs,
    materialize_event_chain_columns,
)
from app.strategy.engine import StrategyEngine

STRATEGY_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "custom"
    / "first_board_event_chain"
    / "strategy_rebreak.py"
)


def _panel() -> pl.DataFrame:
    start = date(2026, 1, 5)
    closes = [10.0, 10.8, 11.7, 11.5, 10.9, 11.2, 12.1, 12.5, 12.4]
    highs = [10.2, 11.0, 12.0, 11.8, 11.3, 11.5, 12.2, 12.6, 12.5]
    lows = [9.8, 10.5, 11.2, 11.0, 10.5, 10.8, 11.9, 12.2, 12.1]
    opens = [10.0, 10.6, 11.0, 11.7, 11.2, 10.9, 11.4, 13.0, 12.45]
    boards = [1, 0, 0, 0, 0, 0, 1, 0, 0]
    return pl.DataFrame({
        "symbol": ["000001.SZ"] * len(closes),
        "name": ["测试股"] * len(closes),
        "date": [start + timedelta(days=index) for index in range(len(closes))],
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [100_000.0] * len(closes),
        "consecutive_limit_ups": boards,
    })


def _market():
    return build_market_data_matrix(
        _panel(),
        field_columns={"consecutive_limit_ups"},
    )


def test_research_strategy_enters_on_strict_rebreak_and_delays_fill_to_next_open() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    assert strategy.meta["research_only"] is True
    assert strategy.execution_backend == "matrix_native"
    assert strategy.meta["stability"] == "experimental"

    market = _market()
    assert strategy.matrix_strategy is not None
    signals = strategy.matrix_strategy.compute_signals(market, {})

    assert signals.entry[:, 0].tolist() == [0, 0, 0, 0, 0, 0, 1, 0, 0]
    assert signals.entry_signal_ids == ("signal_first_board_chain_rebreak",)

    market_matrix = build_market_matrix_from_signals(
        market,
        signals,
        entry_delay_bars=1,
    )
    assert market_matrix.entry[:, 0].tolist() == [0, 0, 0, 0, 0, 0, 0, 1, 0]

    result = BacktestEngine(repo=None).simulate_market_matrix(  # type: ignore[arg-type]
        market_matrix,
        MatcherConfig(
            matching="open_t+1",
            fees_pct=0.0,
            slippage_bps=0.0,
            max_positions=1,
            max_exposure_pct=1.0,
            max_hold_days=1,
            stop_loss_pct=0.5,
            initial_capital=100_000.0,
        ),
    )
    assert len(result.trades) == 1
    assert result.trades[0].entry_date == "2026-01-12"
    assert result.trades[0].entry_price == pytest.approx(13.0)


def test_strategy_parameters_control_lookback_and_pullback_threshold() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH).matrix_strategy
    market = _market()

    within_boundary = strategy.compute_signals(market, {"lookback_days": 6})
    outside_boundary = strategy.compute_signals(market, {"lookback_days": 5})
    too_deep = strategy.compute_signals(market, {"min_pullback_pct": 20.0})

    assert within_boundary.entry[:, 0].sum() == 1
    assert outside_boundary.entry[:, 0].sum() == 0
    assert too_deep.entry[:, 0].sum() == 0


def test_strategy_factor_and_matrix_adapters_share_the_same_kernel() -> None:
    panel = _panel()
    materialized = materialize_event_chain_columns(panel, EVENT_CHAIN_FIELDS)
    market = build_market_data_matrix(
        panel,
        field_columns={"consecutive_limit_ups"},
    )
    from app.backtest.matrix import matrix_feature

    outputs = compute_event_chain_outputs(
        panel["open"].to_numpy().reshape(-1, 1),
        panel["high"].to_numpy().reshape(-1, 1),
        panel["low"].to_numpy().reshape(-1, 1),
        panel["close"].to_numpy().reshape(-1, 1),
        panel["consecutive_limit_ups"].to_numpy().reshape(-1, 1),
    )
    for name in EVENT_CHAIN_FIELDS:
        np.testing.assert_allclose(
            matrix_feature(market, name)[:, 0],
            outputs[name][:, 0],
            rtol=1e-6,
            atol=1e-6,
            equal_nan=True,
            err_msg=name,
        )
        np.testing.assert_allclose(
            materialized[name].to_numpy(),
            outputs[name][:, 0],
            rtol=1e-6,
            atol=1e-6,
            equal_nan=True,
            err_msg=name,
        )


class _FactorEngine:
    def __init__(self, panel: pl.DataFrame) -> None:
        self.panel = panel
        self.load_starts: list[date] = []

    def load_panel(self, symbols, start, end, columns, asset_type):
        del symbols, end, asset_type
        self.load_starts.append(start)
        selected = [column for column in columns if column in self.panel.columns]
        return self.panel.select(selected)


def test_factor_backtest_service_loads_and_materializes_event_chain() -> None:
    panel = _panel()
    engine = _FactorEngine(panel)
    service = FactorBacktestService(engine)
    config = FactorConfig(
        factor_name="first_board_chain_stage",
        symbols=None,
        start=panel["date"][0],
        end=panel["date"][-1],
        n_groups=2,
        rebalance="daily",
        fees_pct=0.0,
        slippage_bps=0.0,
    )

    loaded = service._load_factor_panel(config, [config.factor_name])
    result = service.run(config)

    assert "consecutive_limit_ups" in loaded.columns
    assert engine.load_starts[0] <= panel["date"][0] - timedelta(days=400)
    assert loaded.filter(pl.col("date") == date(2026, 1, 11))[
        "first_board_chain_stage"
    ][0] == 5
    assert result.error is None
    assert result.n_symbols == 1
    assert result.n_dates == 2
