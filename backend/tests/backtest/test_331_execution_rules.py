from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from app.backtest.engine import (
    BacktestEngine,
    ExecutionCostPolicy,
    HoldExtensionPolicy,
    MatcherConfig,
)
from app.backtest.matrix import build_market_matrix
from app.backtest.strategy import StrategyBacktestConfig, StrategyBacktestService
from app.strategy.engine import StrategyEngine

STRATEGY_DIR = (
    Path(__file__).resolve().parents[2] / "app" / "strategy" / "research"
)


def _panel(
    symbols: list[str],
    days: int,
    overrides: dict[tuple[str, int], dict] | None = None,
    scores: dict[str, float] | None = None,
) -> pl.DataFrame:
    overrides = overrides or {}
    scores = scores or {}
    start = date(2025, 1, 2)
    rows = []
    for symbol in symbols:
        for index in range(days):
            patch = overrides.get((symbol, index), {})
            price = float(patch.get("price", 10.0))
            rows.append({
                "symbol": symbol,
                "name": symbol,
                "date": start + timedelta(days=index),
                "open": patch.get("open", price),
                "high": patch.get("high", price),
                "low": patch.get("low", price),
                "close": patch.get("close", price),
                "volume": patch.get("volume", 100_000),
                "score": scores.get(symbol, 0.0),
                "signal_limit_up": patch.get("signal_limit_up", False),
                "signal_limit_down": patch.get("signal_limit_down", False),
                "amount": patch.get("amount", 3_000_000_000.0),
                "raw_close": patch.get("raw_close", patch.get("close", price)),
            })
    return pl.DataFrame(rows).sort(["symbol", "date"])


def _mask(panel: pl.DataFrame, marks: set[tuple[str, int]]) -> pl.Series:
    base = panel["date"][0]
    return pl.Series([
        (row["symbol"], (row["date"] - base).days) in marks
        for row in panel.select(["symbol", "date"]).iter_rows(named=True)
    ])


def test_score_tier_sizes_positions_at_twenty_and_twenty_five_percent() -> None:
    panel = _panel(["A", "B"], days=5, scores={"A": 0.80, "B": 0.60})
    result = BacktestEngine(repo=None).simulate_portfolio(  # type: ignore[arg-type]
        panel,
        _mask(panel, {("A", 0), ("B", 0)}),
        _mask(panel, {("A", 2), ("B", 2)}),
        MatcherConfig(
            matching="open_t+1",
            fees_pct=0.0,
            slippage_bps=0.0,
            max_positions=5,
            initial_capital=100_000.0,
            position_sizing="score_tier",
            score_tiers=((0.0, 0.0), (0.55, 0.20), (43 / 60, 0.25)),
        ),
    )

    by_symbol = {trade.symbol: trade for trade in result.trades}
    assert by_symbol["A"].entry_value == 25_000.0
    assert by_symbol["B"].entry_value == 20_000.0
    assert by_symbol["A"].position_pct == 0.25
    assert by_symbol["B"].position_pct == 0.20


def test_entry_open_gap_blocks_buy_without_backfill() -> None:
    panel = _panel(
        ["A", "B"],
        days=4,
        overrides={("A", 1): {"open": 10.5}},
        scores={"A": 0.8, "B": 0.7},
    )
    result = BacktestEngine(repo=None).simulate_portfolio(  # type: ignore[arg-type]
        panel,
        _mask(panel, {("A", 0), ("B", 0)}),
        _mask(panel, {("A", 2), ("B", 2)}),
        MatcherConfig(
            matching="open_t+1",
            fees_pct=0.0,
            slippage_bps=0.0,
            max_positions=5,
            initial_capital=100_000.0,
            entry_open_gap_range=(-0.04, 0.04),
        ),
    )

    assert [trade.symbol for trade in result.trades] == ["B"]
    assert result.stats["execution"]["buy_open_gap"] == 1


def test_new_high_three_extends_time_exit_to_runner_horizon() -> None:
    panel = _panel(
        ["A"],
        days=10,
        overrides={
            ("A", 5): {"high": 12.0, "close": 10.1},
            ("A", 8): {"close": 9.5},
        },
    )
    result = BacktestEngine(repo=None).simulate_portfolio(  # type: ignore[arg-type]
        panel,
        _mask(panel, {("A", 0)}),
        _mask(panel, {("A", 8)}),
        MatcherConfig(
            matching="open_t+1",
            fees_pct=0.0,
            slippage_bps=0.0,
            max_positions=1,
            initial_capital=100_000.0,
            hold_extension_policy=HoldExtensionPolicy(
                decision_days=5,
                strong_hold_days=10,
                runner_new_high_days=3,
                runner_extend_days=74,
            ),
        ),
    )

    trade = result.trades[0]
    assert trade.exit_signal_date == "2025-01-10"
    assert trade.exit_date == "2025-01-11"
    assert trade.duration >= 8


def test_strong_hold_extends_from_five_to_ten_holding_days() -> None:
    closes = [
        10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0,
        10.1, 10.2, 10.3, 10.5, 10.55, 10.6, 10.62, 10.64, 10.66, 10.68,
    ]
    panel = _panel(
        ["A"],
        days=len(closes),
        overrides={
            ("A", index): {
                "open": close,
                "high": 10.8 if index == 7 else close + 0.08,
                "low": close - 0.08,
                "close": close,
                "price": close,
            }
            for index, close in enumerate(closes)
        },
    )
    result = BacktestEngine(repo=None).simulate_portfolio(  # type: ignore[arg-type]
        panel,
        _mask(panel, {("A", 5)}),
        _mask(panel, set()),
        MatcherConfig(
            matching="open_t+1",
            fees_pct=0.0,
            slippage_bps=0.0,
            max_positions=1,
            initial_capital=100_000.0,
            hold_extension_policy=HoldExtensionPolicy(
                decision_days=5,
                strong_hold_days=10,
                strong_hold_min_return=0.03,
                runner_new_high_days=3,
                runner_extend_days=74,
            ),
        ),
    )

    trade = result.trades[0]
    assert trade.exit_reason == "time_exit"
    assert trade.duration == 10


def _original_config(**overrides) -> MatcherConfig:
    values = {
        "matching": "open_t+1",
        "fees_pct": 0.0,
        "slippage_bps": 0.0,
        "max_positions": 5,
        "initial_capital": 100_000.0,
        "position_sizing": "score_tier",
        "score_tiers": ((0.0, 0.0), (0.55, 0.20), (43 / 60, 0.25)),
        "max_daily_entries": 2,
        "plan_at_signal_close": True,
    }
    values.update(overrides)
    return MatcherConfig(**values)


def test_planned_runner_decision_uses_fifth_holding_session():
    panel = _panel(["A"], 10, overrides={
        ("A", 5): {"high": 12.0, "close": 10.1},
        ("A", 8): {"close": 9.5},
    }, scores={"A": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 8)}),
        _original_config(hold_extension_policy=HoldExtensionPolicy()),
    )
    trade = result.trades[0]
    assert trade.entry_date == "2025-01-03"
    assert trade.exit_reason == "signal"
    assert trade.exit_signal_date == "2025-01-10"
    assert trade.exit_date == "2025-01-11"


@pytest.mark.parametrize(
    ("horizon", "signal_date", "exit_date", "duration"),
    [(5, "2025-01-07", "2025-01-08", 6),
     (74, "2025-03-17", "2025-03-18", 75)],
)
def test_planned_time_exit_executes_after_inclusive_holding_horizon(
    horizon, signal_date, exit_date, duration,
):
    overrides = {("A", 5): {"high": 12.0}} if horizon == 74 else {}
    panel = _panel(["A"], 78, overrides=overrides, scores={"A": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 0)}), _mask(panel, set()),
        _original_config(hold_extension_policy=HoldExtensionPolicy()),
    )
    trade = result.trades[0]
    assert trade.exit_reason == "time_exit"
    assert trade.exit_signal_date == signal_date
    assert trade.exit_date == exit_date
    assert trade.duration == duration


def test_planned_strong_hold_exits_after_tenth_holding_session():
    closes = [
        10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0,
        10.1, 10.2, 10.3, 10.5, 10.55, 10.6, 10.62, 10.64, 10.66, 10.68,
    ]
    panel = _panel(["A"], len(closes), overrides={
        ("A", index): {
            "price": close, "high": 10.8 if index == 7 else close + 0.08,
            "low": close - 0.08,
        }
        for index, close in enumerate(closes)
    }, scores={"A": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 5)}), _mask(panel, set()),
        _original_config(hold_extension_policy=HoldExtensionPolicy()),
    )
    trade = result.trades[0]
    assert trade.entry_date == "2025-01-08"
    assert trade.exit_reason == "time_exit"
    assert trade.exit_signal_date == "2025-01-17"
    assert trade.exit_date == "2025-01-18"
    assert trade.duration == 11


def test_original_trailing_keeps_fixed_stop_and_uses_completed_close_peak() -> None:
    panel = _panel(["A"], 5, overrides={
        ("A", 2): {"close": 10.4, "high": 12.0},
        ("A", 3): {"open": 10.3, "low": 9.5, "high": 10.3, "close": 10.0},
    }, scores={"A": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 0)}), _mask(panel, set()),
        _original_config(
            stop_loss_pct=-0.06, trailing_peak_price="close",
            trailing_take_profit_activate_pct=0.03,
            trailing_take_profit_drawdown_pct=0.08,
        ),
    )
    trade = result.trades[0]
    assert trade.exit_date == "2025-01-05"
    assert trade.exit_price == pytest.approx(10.4 * 0.92, abs=1e-4)
    assert trade.exit_reason == "trailing_take_profit"


def test_top_three_plan_two_does_not_replace_rejected_order() -> None:
    panel = _panel(["A", "B", "C"], 4, overrides={("A", 1): {"open": 11.0}},
                   scores={"A": 0.85, "B": 0.8, "C": 0.7})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 0), ("B", 0), ("C", 0)}),
        _mask(panel, {("A", 2), ("B", 2), ("C", 2)}),
        _original_config(entry_open_gap_range=(-0.04, 0.04)),
    )
    assert [t.symbol for t in result.trades] == ["B"]
    assert result.stats["execution"]["buy_open_gap"] == 1


def test_quantity_is_planned_at_signal_close_and_cash_is_split_before_tiers() -> None:
    panel = _panel(["A", "B"], 4,
                   overrides={("A", 1): {"open": 8.0}},
                   scores={"A": 0.8, "B": 0.7})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 0), ("B", 0)}),
        _mask(panel, {("A", 2), ("B", 2)}),
        _original_config(max_exposure_pct=0.3),
    )
    trades = {t.symbol: t for t in result.trades}
    # Only 30k exposure is available at decision time; reserve half per plan.
    assert trades["A"].shares == 1500
    assert trades["B"].shares == 1500


def test_no_buy_deferred_past_a_missing_execution_day() -> None:
    panel = _panel(["A", "B"], 5, scores={"A": 0.8, "B": 0.7})
    panel = panel.filter(~((pl.col("symbol") == "A") & (pl.col("date") == date(2025, 1, 3))))
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 3)}),
        _original_config(),
    )
    assert not result.trades
    assert result.stats["execution"]["buy_suspended"] == 1


def test_raw_price_entry_gate_rejects_ex_right_change_despite_flat_adjusted_price() -> None:
    panel = _panel(["A"], 5, overrides={
        ("A", 0): {"raw_close": 20.0},
        ("A", 1): {"raw_close": 10.0},
    }, scores={"A": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 1)}), _mask(panel, {("A", 3)}),
        _original_config(entry_price_basis="raw", entry_prev_day_change_range=(-0.05, 0.05)),
    )
    assert not result.trades
    assert result.stats["execution"]["buy_prev_day_change"] == 1


def test_open_at_limit_up_is_blocked_even_if_it_trades_lower_later() -> None:
    panel = _panel(["000001.SZ"], 4, overrides={
        ("000001.SZ", 1): {"open": 11.0, "high": 11.0, "low": 10.1, "close": 10.5},
    }, scores={"000001.SZ": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("000001.SZ", 0)}), _mask(panel, {("000001.SZ", 2)}),
        _original_config(entry_price_basis="raw", block_limit_open=True),
    )
    assert not result.trades
    assert result.stats["execution"]["buy_limit_up"] == 1


@pytest.mark.parametrize(("amount", "expected_bps"), [
    (50_000_000.0, 25), (100_000_000.0, 15),
    (500_000_000.0, 10), (2_000_000_000.0, 5),
])
def test_costs_use_signal_day_amount_and_do_not_double_charge_slippage(amount, expected_bps) -> None:
    panel = _panel(["A"], 4, overrides={
        ("A", 0): {"amount": amount},
        ("A", 1): {"amount": 10.0},
    }, scores={"A": 0.8})
    policy = ExecutionCostPolicy(
        min_commission=5.0,
        transfer_fee_pct=0.00001,
        buy_slippage_tiers=((1e8, 20.0), (5e8, 10.0), (2e9, 5.0)),
    )
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 2)}),
        _original_config(
            initial_capital=20_000, commission_pct=0.00025, stamp_tax_pct=0.0005,
            slippage_bps=5, execution_costs=policy,
        ),
    )
    trade = result.trades[0]
    assert trade.entry_price == pytest.approx(round(10 * (1 + expected_bps / 10_000), 4))
    assert trade.exit_price == 9.995
    buy_gross = trade.shares * trade.entry_price
    sell_gross = trade.shares * trade.exit_price
    assert trade.entry_value == pytest.approx(round(buy_gross + 5 + buy_gross * 0.00001, 2))
    assert trade.exit_value == pytest.approx(round(sell_gross - 5 - sell_gross * 0.00051, 2))


def test_same_day_risk_exit_takes_priority_over_planned_open_exit() -> None:
    """风控先于计划出场: 次日开盘既触发止损又有开盘卖点, 以止损理由与价格成交。"""
    panel = _panel(["A"], 4, overrides={
        ("A", 2): {"open": 9.0, "high": 9.5, "low": 8.8, "close": 9.2},
    }, scores={"A": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 1)}),
        _original_config(stop_loss_pct=-0.06),
    )

    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_date == "2025-01-04"
    assert trade.exit_price == 9.0
    assert result.stats["execution"]["sell_limit_down"] == 0


def test_blocked_risk_exit_keeps_reason_and_retries_next_tradable_day() -> None:
    """首次阻塞的风控理由被保留: 跌停封死延后成交时仍记 stop_loss, 不退回 signal。"""
    panel = _panel(["A"], 5, overrides={
        ("A", 2): {
            "open": 9.0, "high": 9.0, "low": 9.0, "close": 9.0,
            "signal_limit_down": True,
        },
        ("A", 3): {"open": 10.5, "high": 10.6, "low": 10.4, "close": 10.5},
    }, scores={"A": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 1)}),
        _original_config(stop_loss_pct=-0.06),
    )

    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_signal_date == "2025-01-04"
    assert trade.exit_date == "2025-01-05"
    assert trade.exit_price == 10.5
    # 同一持仓同一交易日只允许一次卖出尝试: 风控轮被跌停阻塞后, 不应在
    # 同一交易日的后续轮次重复下单, 否则拒卖统计与 blocked_exit_days 翻倍。
    assert trade.blocked_exit_days == 1
    assert result.stats["execution"]["sell_limit_down"] == 1
    assert result.stats["execution"]["pending_exit"] == 1


def test_exit_signal_profit_gate_uses_signal_day_close() -> None:
    """卖出信号的盈利门槛按信号日已完成收盘判断, 不能被次日执行位绕过。"""
    panel = _panel(["A"], 5, overrides={
        ("A", 1): {"open": 10.0, "high": 10.2, "low": 9.8, "close": 9.9},
        ("A", 2): {"open": 10.2, "high": 10.3, "low": 10.0, "close": 10.2},
    }, scores={"A": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 1)}),
        _original_config(exit_signal_requires_profit=True),
    )

    # 信号日收盘 9.9 < 建仓价 10.0 → 盈利门槛不满足, 次日开盘 10.2 不应按
    # signal 卖出; 持仓保留到回测末日的兜底离场。
    assert [trade.exit_reason for trade in result.trades] == ["end"]


def test_exit_signal_profit_gate_sells_next_open_when_signal_day_profitable() -> None:
    panel = _panel(["A"], 5, overrides={
        ("A", 1): {"open": 10.0, "high": 10.3, "low": 9.9, "close": 10.1},
        ("A", 2): {"open": 10.2, "high": 10.3, "low": 10.0, "close": 10.2},
    }, scores={"A": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 1)}),
        _original_config(exit_signal_requires_profit=True),
    )

    trade = result.trades[0]
    assert trade.exit_reason == "signal"
    assert trade.exit_signal_date == "2025-01-03"  # 信号日, 不是成交日
    assert trade.exit_date == "2025-01-04"
    assert trade.exit_price == 10.2


def test_exit_signal_stays_armed_after_prior_profitable_close_turns_to_loss():
    panel = _panel(["A"], 6, overrides={
        ("A", 1): {"open": 10.0, "high": 10.1, "low": 9.8, "close": 9.9},
        ("A", 2): {"high": 10.4, "close": 10.2},
        ("A", 3): {"low": 9.7, "close": 9.8},
        ("A", 4): {"price": 9.5},
    }, scores={"A": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 3)}),
        _original_config(exit_signal_requires_profit=True),
    )
    trade = result.trades[0]
    assert trade.exit_reason == "signal"
    assert trade.exit_signal_date == "2025-01-05"
    assert trade.exit_date == "2025-01-06"
    assert trade.exit_price == 9.5


def test_intraday_profit_without_profitable_close_does_not_arm_ma_exit():
    panel = _panel(["A"], 5, overrides={
        ("A", 1): {"open": 10.0, "high": 12.0, "low": 9.8, "close": 9.9},
        ("A", 2): {"low": 9.5, "close": 9.6},
    }, scores={"A": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 2)}),
        _original_config(exit_signal_requires_profit=True),
    )
    assert result.trades[0].exit_reason == "end"


def test_entry_day_completed_close_feeds_next_day_trailing_peak() -> None:
    """建仓日已完成收盘必须计入峰值, 次日移动止盈/回撤线才正确。"""
    panel = _panel(["A"], 4, overrides={
        ("A", 1): {"open": 10.0, "high": 10.6, "low": 9.9, "close": 10.5},
        ("A", 2): {"open": 9.8, "high": 9.9, "low": 9.5, "close": 9.6},
    }, scores={"A": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 0)}), _mask(panel, set()),
        _original_config(
            trailing_peak_price="close",
            trailing_take_profit_activate_pct=0.03,
            trailing_take_profit_drawdown_pct=0.08,
        ),
    )

    trade = result.trades[0]
    assert trade.exit_reason == "trailing_take_profit"
    assert trade.exit_date == "2025-01-04"
    # 峰值 = 建仓日收盘 10.5 (而非建仓价 10.0), 回撤 8% 触发线 10.5*0.92。
    assert trade.exit_price == pytest.approx(10.5 * 0.92, abs=1e-6)


def test_planned_open_exit_is_not_preempted_by_same_day_intraday_low() -> None:
    """开盘即可成交的计划卖单必须先于当日盘中 low 风控成交。"""
    panel = _panel(["A"], 4, overrides={
        ("A", 2): {"open": 10.3, "high": 10.4, "low": 9.0, "close": 9.2},
    }, scores={"A": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 1)}),
        _original_config(stop_loss_pct=-0.06),
    )

    trade = result.trades[0]
    assert trade.exit_reason == "signal"
    assert trade.exit_date == "2025-01-04"
    assert trade.exit_price == 10.3
    assert result.stats["execution"]["sell_limit_down"] == 0


def _simulate(path: str, panel, entries, exits, config: MatcherConfig):
    engine = BacktestEngine(repo=None)  # type: ignore[arg-type]
    if path == "matrix":
        return engine.simulate_portfolio(panel, entries, exits, config)
    return engine.simulate_portfolio_legacy(panel, entries, exits, config)


@pytest.mark.parametrize("path", ["matrix", "legacy"])
def test_close_t_blocked_exit_counts_once_per_day(path: str) -> None:
    """close_t 下日内与收盘两处重试同一挂单, 每持仓每日只计一次拒卖。"""
    panel = _panel(["A"], 4, overrides={
        ("A", 1): {
            "open": 9.0, "high": 9.0, "low": 9.0, "close": 9.0,
            "signal_limit_down": True,
        },
        ("A", 2): {"open": 10.5, "high": 10.6, "low": 10.4, "close": 10.5},
    }, scores={"A": 0.8})
    result = _simulate(
        path, panel, _mask(panel, {("A", 0)}), _mask(panel, set()),
        MatcherConfig(
            matching="close_t", entry_fill="close_t", exit_fill="close_t",
            fees_pct=0.0, slippage_bps=0.0, stop_loss_pct=-0.06,
            max_positions=1, initial_capital=100_000.0,
        ),
    )

    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_date == "2025-01-04"
    assert trade.exit_price == 10.5
    assert trade.blocked_exit_days == 1
    assert result.stats["execution"]["sell_limit_down"] == 1
    assert result.stats["execution"]["pending_exit"] == 1


@pytest.mark.parametrize("path", ["matrix", "legacy"])
def test_minute_pending_retries_next_open_and_records_trade(path: str) -> None:
    """signal_next_minute 挂单两路径都在次日开盘重试, 期末不丢仓。"""
    panel = _panel(["A"], 5, overrides={
        ("A", 2): {
            "open": 9.0, "high": 9.0, "low": 9.0, "close": 9.0,
            "signal_limit_down": True,
        },
        ("A", 3): {"open": 10.5, "high": 10.6, "low": 10.4, "close": 10.5},
    }, scores={"A": 0.8})
    result = _simulate(
        path, panel, _mask(panel, {("A", 0)}), _mask(panel, set()),
        MatcherConfig(
            matching="open_t+1", entry_fill="open_t+1",
            exit_fill="signal_next_minute",
            fees_pct=0.0, slippage_bps=0.0, stop_loss_pct=-0.06,
            max_positions=1, initial_capital=100_000.0,
        ),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_date == "2025-01-05"
    assert trade.exit_price == 10.5
    assert trade.blocked_exit_days == 1
    assert result.stats["execution"]["sell_limit_down"] == 1
    assert result.stats["execution"]["pending_exit"] == 1
    assert result.stats["pending_exit_positions"] == 0


@pytest.mark.parametrize("path", ["matrix", "legacy"])
def test_close_t_entry_ignores_prebuy_high_for_peak(path: str) -> None:
    """close_t 在收盘买入, 当日买前 high 不能抬高买入后移动止损线。"""
    panel = _panel(["A"], 3, overrides={
        ("A", 0): {"open": 10.0, "high": 12.0, "low": 9.9, "close": 10.0},
        ("A", 1): {"open": 10.4, "high": 10.5, "low": 10.2, "close": 10.4},
    }, scores={"A": 0.8})
    result = _simulate(
        path, panel, _mask(panel, {("A", 0)}), _mask(panel, set()),
        MatcherConfig(
            matching="close_t", entry_fill="close_t", exit_fill="close_t",
            fees_pct=0.0, slippage_bps=0.0, trailing_stop_pct=0.1,
            max_positions=1, initial_capital=100_000.0,
        ),
    )

    # 正确峰值=10.0 → 止损线 9.0, 次日 low 10.2 不触发; 买前 high=12 时
    # 线会被错误抬到 10.8, 次日开盘 10.4 即被卖出。
    assert [trade.exit_reason for trade in result.trades] == ["end"]


@pytest.mark.parametrize("path", ["matrix", "legacy"])
def test_open_buy_does_not_use_same_day_intraday_exit_cash(path: str) -> None:
    """非计划 open_t+1 建仓不得使用同日日内卖出才释放的现金和仓位。"""
    panel = _panel(["A", "B"], 4, overrides={
        ("A", 2): {"open": 10.0, "high": 10.1, "low": 9.0, "close": 9.5},
    }, scores={"A": 0.9, "B": 0.8})
    entries = _mask(panel, {("A", 0), ("B", 1)})
    result = _simulate(
        path, panel, entries, _mask(panel, set()),
        MatcherConfig(
            matching="open_t+1", entry_fill="open_t+1", exit_fill="open_t+1",
            fees_pct=0.0, slippage_bps=0.0, stop_loss_pct=-0.06,
            max_positions=1, initial_capital=100_000.0,
        ),
    )

    # A 在 day2 开盘时仍占唯一仓位, 同日日内止损卖出后才空出仓位:
    # 以 day2 开盘价成交的 B 不能追溯使用该仓位/现金。
    assert [trade.symbol for trade in result.trades] == ["A"]
    assert result.stats["execution"]["buy_no_slot"] >= 1


@pytest.mark.parametrize("path", ["matrix", "legacy"])
def test_close_t_close_limit_down_defers_exit_to_next_day(path: str) -> None:
    """close_t 收盘价封死跌停时不可成交; 开盘成交路径不受该收盘限制影响。"""
    panel = _panel(["A"], 4, overrides={
        ("A", 1): {
            "open": 9.4, "high": 9.5, "low": 9.0, "close": 9.0,
            "signal_limit_down": True,
        },
        ("A", 2): {"open": 10.0, "high": 10.1, "low": 9.9, "close": 10.0},
    }, scores={"A": 0.8})
    result = _simulate(
        path, panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 1)}),
        MatcherConfig(
            matching="close_t", entry_fill="close_t", exit_fill="close_t",
            fees_pct=0.0, slippage_bps=0.0,
            max_positions=1, initial_capital=100_000.0,
        ),
    )

    trade = result.trades[0]
    assert trade.exit_reason == "signal"
    assert trade.exit_date == "2025-01-04"
    assert trade.exit_price == 10.0
    assert trade.blocked_exit_days == 1
    assert result.stats["execution"]["sell_limit_down"] == 1


def test_entry_day_stop_plan_not_overwritten_by_sell_signal() -> None:
    """建仓日收盘止损计划优先于同日卖点, 原因与信号日不得被改写。"""
    panel = _panel(["A"], 4, overrides={
        ("A", 1): {"open": 10.0, "high": 10.1, "low": 9.2, "close": 9.3},
        ("A", 2): {"open": 9.6, "high": 9.7, "low": 9.5, "close": 9.6},
    }, scores={"A": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(  # type: ignore[arg-type]
        panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 1)}),
        _original_config(stop_loss_pct=-0.06),
    )

    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_signal_date == "2025-01-03"
    assert trade.exit_date == "2025-01-04"
    assert trade.exit_price == 9.6


@pytest.mark.parametrize("path", ["matrix", "legacy"])
def test_minute_close_signal_falls_back_to_next_open(path: str) -> None:
    """非建仓日分钟信号无后续分钟成交时, 次日开盘按开盘价回退成交。"""
    panel = _panel(["A"], 5, overrides={
        ("A", 3): {"open": 10.5, "high": 10.6, "low": 10.4, "close": 10.0},
    }, scores={"A": 0.8})
    result = _simulate(
        path, panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 2)}),
        MatcherConfig(
            matching="open_t+1", entry_fill="open_t+1",
            exit_fill="signal_next_minute",
            fees_pct=0.0, slippage_bps=0.0,
            max_positions=1, initial_capital=100_000.0,
        ),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "signal"
    assert trade.exit_signal_date == "2025-01-04"
    assert trade.exit_date == "2025-01-05"
    assert trade.exit_price == 10.5  # 次日开盘价, 不是信号日收盘 10.0
    # 无后续分钟成交属于按计划顺延, 不是市场拒卖: 不计 blocked_exit_days。
    assert trade.blocked_exit_days == 0
    assert result.stats["execution"]["sell_minute_trigger_fallback"] == 1
    assert result.stats["pending_exit_positions"] == 0


@pytest.mark.parametrize("path", ["matrix", "legacy"])
def test_minute_entry_day_signal_defers_to_next_open_after_t_plus_one(path: str) -> None:
    """建仓日收盘信号不得当日成交; T+1 后下一交易日开盘成交并保留信号日。"""
    panel = _panel(["A"], 5, overrides={
        ("A", 1): {"open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1},
        ("A", 2): {"open": 9.0, "high": 9.2, "low": 8.9, "close": 9.2},
        ("A", 3): {"open": 8.5, "high": 8.6, "low": 8.4, "close": 8.0},
    }, scores={"A": 0.8})
    result = _simulate(
        path, panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 1)}),
        MatcherConfig(
            matching="open_t+1", entry_fill="open_t+1",
            exit_fill="signal_next_minute",
            fees_pct=0.0, slippage_bps=0.0,
            max_positions=1, initial_capital=100_000.0,
        ),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "signal"
    assert trade.exit_signal_date == "2025-01-03"  # 建仓日收盘信号
    assert trade.exit_date == "2025-01-04"  # 不能是建仓日 01-03
    assert trade.exit_price == 9.0  # 次日开盘, 不是建仓日收盘 10.1
    # 建仓日回退只是执行安排, 两路径都不计拒卖日。
    assert trade.blocked_exit_days == 0


@pytest.mark.parametrize(
    ("signal_close", "expect_signal"),
    [(9.9, False), (10.1, True)],
)
def test_minute_signal_profit_gate_uses_signal_day_close(
    signal_close: float, expect_signal: bool,
) -> None:
    """分钟信号的盈利门槛同样按信号日已完成收盘判断, 双向均可成交/不成交。"""
    panel = _panel(["A"], 5, overrides={
        ("A", 2): {
            "open": 10.0, "high": 10.2, "low": 9.8,
            "close": signal_close,
        },
        ("A", 3): {"open": 10.2, "high": 10.3, "low": 10.0, "close": 10.2},
    }, scores={"A": 0.8})
    result = BacktestEngine(repo=None).simulate_portfolio(  # type: ignore[arg-type]
        panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 2)}),
        MatcherConfig(
            matching="open_t+1", entry_fill="open_t+1",
            exit_fill="signal_next_minute",
            fees_pct=0.0, slippage_bps=0.0,
            exit_signal_requires_profit=True,
            max_positions=1, initial_capital=100_000.0,
        ),
    )

    reasons = [trade.exit_reason for trade in result.trades]
    if expect_signal:
        trade = result.trades[0]
        assert reasons == ["signal"]
        assert trade.exit_date == "2025-01-05"
        assert trade.exit_price == 10.2
        assert trade.exit_signal_date == "2025-01-04"
    else:
        # 信号日亏损 → 不退出, 持有到期末兜底离场。
        assert reasons == ["end"]


@pytest.mark.parametrize("path", ["matrix", "legacy"])
def test_minute_pending_survives_blocked_open_and_records_trade(path: str) -> None:
    """分钟挂单次日开盘不可成交时保留挂单, 再次日成交并留下完整记录。"""
    panel = _panel(["A"], 5, overrides={
        ("A", 3): {
            "open": 9.0, "high": 9.0, "low": 9.0, "close": 9.0,
            "signal_limit_down": True,
        },
        ("A", 4): {"open": 10.5, "high": 10.6, "low": 10.4, "close": 10.0},
    }, scores={"A": 0.8})
    result = _simulate(
        path, panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 2)}),
        MatcherConfig(
            matching="open_t+1", entry_fill="open_t+1",
            exit_fill="signal_next_minute",
            fees_pct=0.0, slippage_bps=0.0,
            max_positions=1, initial_capital=100_000.0,
        ),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "signal"
    assert trade.exit_signal_date == "2025-01-04"
    assert trade.exit_date == "2025-01-06"
    assert trade.exit_price == 10.5
    # 只有次日一字跌停是真实市场拒卖; 信号日无分钟成交只是按计划顺延。
    assert trade.blocked_exit_days == 1
    assert result.stats["execution"]["sell_limit_down"] == 1
    assert result.stats["execution"]["pending_exit"] == 1
    assert result.stats["pending_exit_positions"] == 0


@pytest.mark.parametrize("path", ["matrix", "legacy"])
def test_minute_pending_counts_each_real_block_day_once(path: str) -> None:
    """连续两个真实一字跌停日各计一次拒卖, 顺延日不计。"""
    panel = _panel(["A"], 6, overrides={
        ("A", 3): {
            "open": 9.0, "high": 9.0, "low": 9.0, "close": 9.0,
            "signal_limit_down": True,
        },
        ("A", 4): {
            "open": 8.0, "high": 8.0, "low": 8.0, "close": 8.0,
            "signal_limit_down": True,
        },
        ("A", 5): {"open": 10.5, "high": 10.6, "low": 10.4, "close": 10.0},
    }, scores={"A": 0.8})
    result = _simulate(
        path, panel, _mask(panel, {("A", 0)}), _mask(panel, {("A", 2)}),
        MatcherConfig(
            matching="open_t+1", entry_fill="open_t+1",
            exit_fill="signal_next_minute",
            fees_pct=0.0, slippage_bps=0.0,
            max_positions=1, initial_capital=100_000.0,
        ),
    )

    trade = result.trades[0]
    assert trade.exit_signal_date == "2025-01-04"
    assert trade.exit_date == "2025-01-07"
    assert trade.exit_price == 10.5
    assert trade.blocked_exit_days == 2
    assert result.stats["execution"]["sell_limit_down"] == 2
    assert result.stats["execution"]["pending_exit"] == 1
    assert result.stats["pending_exit_positions"] == 0


# ── full 独立回测能力校验 ──────────────────────────────────────────

def _full_config(**extra) -> MatcherConfig:
    values = {
        "matching": "open_t+1",
        "fees_pct": 0.0,
        "slippage_bps": 0.0,
        "max_positions": 1,
        "initial_capital": 100_000.0,
    }
    values.update(extra)
    return MatcherConfig(**values)


FULL_UNSUPPORTED_CASES = [
    (lambda: {"exit_signal_requires_profit": True}, "盈利状态退出", "exit_signal_requires_profit"),
    (lambda: {"hold_extension_policy": HoldExtensionPolicy()}, "持仓延展", "hold_extension_policy"),
    (lambda: {"trailing_peak_price": "close"}, "收盘峰值回撤", "trailing_peak_price"),
    (lambda: {"plan_at_signal_close": True}, "收盘计划买入", "plan_at_signal_close"),
    (lambda: {"max_daily_entries": 2}, "每日买入笔数上限", "max_daily_entries"),
    (
        lambda: {
            "position_sizing": "score_tier",
            "score_tiers": ((0.0, 0.0), (0.5, 0.2)),
        },
        "评分分档仓位",
        "position_sizing",
    ),
    (lambda: {"execution_costs": ExecutionCostPolicy(min_commission=5.0)}, "执行费用策略", "execution_costs"),
    (lambda: {"entry_price_basis": "raw"}, "原始价入场口径", "entry_price_basis"),
    (lambda: {"block_limit_open": True}, "开盘涨停门控", "block_limit_open"),
]


@pytest.mark.parametrize(
    ("kwargs_factory", "rule_name", "field"),
    FULL_UNSUPPORTED_CASES,
    ids=[case[2] for case in FULL_UNSUPPORTED_CASES],
)
def test_full_matcher_rejects_each_unsupported_rule(
    kwargs_factory, rule_name: str, field: str,
) -> None:
    panel = _panel(["A"], 3, scores={"A": 0.8})
    matrix = build_market_matrix(panel, _mask(panel, {("A", 0)}), None)
    with pytest.raises(ValueError) as exc:
        BacktestEngine(repo=None).simulate_independent_market_matrix(  # type: ignore[arg-type]
            matrix, 1, _full_config(**kwargs_factory()),
        )
    message = str(exc.value)
    assert rule_name in message
    assert field in message
    assert "请改用组合回测（position）" in message
    assert "系统未执行本次回测" in message


def test_full_rejects_before_empty_candidates_and_empty_panel() -> None:
    engine = BacktestEngine(repo=None)  # type: ignore[arg-type]
    panel = _panel(["A"], 2, scores={"A": 0.8})
    matrix = build_market_matrix(
        panel, pl.Series([False] * len(panel)), None,
    )
    with pytest.raises(ValueError, match="盈利状态退出"):
        engine.simulate_independent_market_matrix(
            matrix, 0, _full_config(exit_signal_requires_profit=True),
        )
    with pytest.raises(ValueError, match="盈利状态退出"):
        engine.simulate_independent_candidates(
            panel.slice(0, 0), None, None,
            _full_config(exit_signal_requires_profit=True),
        )


def test_full_supported_config_and_declared_tiers_still_run() -> None:
    panel = _panel(["A"], 3, scores={"A": 0.8})
    matrix = build_market_matrix(panel, _mask(panel, {("A", 0)}), None)
    result = BacktestEngine(repo=None).simulate_independent_market_matrix(  # type: ignore[arg-type]
        matrix,
        1,
        _full_config(
            entry_open_gap_range=(-0.5, 0.5),
            entry_prev_day_change_range=(-0.5, 0.5),
            score_tiers=((0.0, 0.0), (0.5, 0.2)),
        ),
    )
    assert result.stats is not None


def _strategy_service() -> tuple[StrategyBacktestService, StrategyEngine]:
    strategy_engine = StrategyEngine(strategy_dirs=[STRATEGY_DIR])
    return (
        StrategyBacktestService(
            BacktestEngine(repo=None),  # type: ignore[arg-type]
            strategy_engine,
        ),
        strategy_engine,
    )


def _run_strategy_full(service: StrategyBacktestService, **extra):
    return service.run(StrategyBacktestConfig(
        strategy_id="first_limit_pullback_3f_runner_t74",
        symbols=None,
        start=date(2025, 1, 2),
        end=date(2025, 2, 1),
        mode="full",
        **extra,
    ))


def test_full_331_rejected_with_all_rules_before_data_and_equal_cannot_bypass() -> None:
    service, strategy_engine = _strategy_service()
    result = _run_strategy_full(service, position_sizing="equal")

    message = result.error or ""
    for rule_name in (
        "盈利状态退出",
        "持仓延展",
        "收盘峰值回撤",
        "收盘计划买入",
        "每日买入笔数上限",
        "执行费用策略",
        "原始价入场口径",
        "开盘涨停门控",
    ):
        assert rule_name in message
    # 请求选择 equal: 未启用的分档仓位不应误拒, 但其余执行规则仍必须拦截。
    assert "评分分档仓位" not in message
    assert "系统未执行本次回测" in message
    assert result.config["mode"] == "full"
    defaults = strategy_engine.get("first_limit_pullback_3f_runner_t74").meta[
        "backtest_defaults"
    ]
    assert defaults["position_sizing"] == "score_tier"
    assert defaults["plan_at_signal_close"] is True


def test_full_331_default_sizing_also_reports_score_tier_rule() -> None:
    service, _ = _strategy_service()
    # 生产前端会把策略默认 position_sizing 回填到请求; 这里显式模拟同一有效配置。
    result = _run_strategy_full(service, position_sizing="score_tier")
    message = result.error or ""
    assert "评分分档仓位" in message
    assert "position_sizing" in message
