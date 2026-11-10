"""末期持仓结算契约 (D-EOS) 的守护用例：T-EOS-1~5 + 六条逃逸路径 + carry_out 反例。

契约：`docs/architecture/CONTRACT_END_SETTLEMENT_20261108.md`（v1.0）
实现：`backend/app/backtest/engine.py` 的 "末日终结结算步"（持仓体顶部，权益行
写入之前）+ "MARKED 记账号"（post-loop，只为仍在 positions 的持仓补 open_at_end）。

本文件守的四条不变量：
  I1 末行自洽  value = cash + Σ 剩余持仓×末日估值价，且 cash 已含同一 bar 内所有
              进入 trades 的成交额（不存在"已记 trades 但未进现金"的成交）。
  I2 单一价    同一末日、同一持仓只有一个估值价（不再出现"4 只按开盘、1 只按收盘"）。
  I3 两终态    每只持仓恰为 SETTLED（卖出进现金/exit_price=该臂末根 exit_fill 价）
              或 MARKED（末日收盘盯市/open_at_end=True/pnl_amount=0）。
  I4 统计不动  不改 equity_values 长度、不改统计定义。

逃逸路径 → 用例（契约 §1.3 的 P1~P6）：
  P1 末日建仓        -> test_t_eos_3_last_bar_entry_settles_same_open_price
  P2 pending 挂单    -> test_t_eos_2_pending_exit_is_settled_as_end
  P3 risk 闸门       -> test_p3_risk_latch_on_entry_day_does_not_escape_settlement
  P4 信号闩锁        -> test_t_eos_1_signal_latch_on_last_bar_is_settled
  P5 延展策略到期    -> test_p5_hold_policy_decision_on_last_bar_does_not_escape
  P6 末日不可成交    -> test_t_eos_4_blocked_sell_on_last_bar_is_marked
  finalize 臂不变    -> test_t_eos_5_finalize_open_at_end_still_marks
  carry_out 不触发   -> test_carry_out_segment_does_not_settle
"""
from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from app.backtest.engine import (
    BacktestEngine,
    HoldExtensionPolicy,
    MatcherConfig,
    PortfolioCarryState,
    SimulationOptions,
)
from app.backtest.matrix import build_market_matrix


START = date(2025, 1, 2)


def _panel(
    symbols: list[str],
    days: int,
    overrides: dict[tuple[str, int], dict] | None = None,
    scores: dict[str, float] | None = None,
) -> pl.DataFrame:
    overrides = overrides or {}
    scores = scores or {}
    rows = []
    for symbol in symbols:
        for index in range(days):
            patch = overrides.get((symbol, index), {})
            price = float(patch.get("price", 10.0))
            rows.append({
                "symbol": symbol,
                "name": symbol,
                "date": START + timedelta(days=index),
                "open": patch.get("open", price),
                "high": patch.get("high", price),
                "low": patch.get("low", price),
                "close": patch.get("close", price),
                "volume": patch.get("volume", 100_000),
                "score": scores.get(symbol, 0.8),
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


def _config(**overrides) -> MatcherConfig:
    values = {
        "matching": "open_t+1",
        "entry_fill": "open_t+1",
        "exit_fill": "open_t+1",
        "fees_pct": 0.0,
        "slippage_bps": 0.0,
        "max_positions": 1,
        "max_exposure_pct": 1.0,
        "initial_capital": 100_000.0,
    }
    values.update(overrides)
    return MatcherConfig(**values)


def _run(panel, entries, exits, config: MatcherConfig):
    return BacktestEngine(repo=None).simulate_portfolio(  # type: ignore[arg-type]
        panel, _mask(panel, entries), _mask(panel, exits), config
    )


def _last_row(result):
    assert result.equity_curve, "equity_curve 必须非空（本用例都开 include_curves）"
    return result.equity_curve[-1]


# --------------------------------------------------------------------- T-EOS-1
def test_t_eos_1_signal_latch_on_last_bar_is_settled() -> None:
    """T-EOS-1 / P4：末日仍有已武装卖点（open_t+1 只能闩锁）时，末日必须清算。

    改前：:4164-4167 只写 next_open_exit_reason 后 continue，末行权益按末日收盘
    盯市、post-loop 才按开盘补卖 ⇒ 末行 cash 不含该笔、value 却含其市值。
    改后：SETTLED —— 末行 positions=0、cash=value、exposure=0，trades 一笔 end。
    """
    panel = _panel(["A"], 4, overrides={
        ("A", 1): {"price": 10.0},
        ("A", 2): {"price": 11.0},
        ("A", 3): {"price": 12.0},
    })
    result = _run(panel, {("A", 0)}, {("A", 3)}, _config())

    row = _last_row(result)
    assert row["positions"] == 0
    assert row["exposure"] == 0.0
    assert row["cash"] == row["value"]          # I1
    assert result.stats["final_equity"] == row["value"]
    assert result.stats["pending_exit_positions"] == 0

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "end"           # S-6
    assert str(trade.exit_date) == "2025-01-05"  # 末日
    assert trade.exit_price == 12.0              # S-5：末日开盘（该臂 exit_fill）
    assert trade.open_at_end is False            # I3：SETTLED 而非 MARKED
    assert trade.pnl_amount == pytest.approx(100_000.0 * 0.2, abs=0.01)
    # S-2：链底 end 分支在守卫下不可达
    assert "end_branch_reached_after_settlement" not in result.stats["execution"]


# --------------------------------------------------------------------- T-EOS-2
def test_t_eos_2_pending_exit_is_settled_as_end() -> None:
    """T-EOS-2 / P2：末日持仓带 pending_exit_reason（连续两天一字跌停造）时，
    末日清算必须覆盖 pending 原因，末行 cash 已含清算额。

    close_t 路径下 pending 的重试在 :4141，位置在终结结算步之后 ⇒ 改后由 end
    结算（改前会以 pending 原因 "stop_loss" 成交，或落到 post-loop 的 else）。
    """
    panel = _panel(["A"], 4, overrides={
        ("A", 1): {"open": 9.0, "high": 9.0, "low": 9.0, "close": 9.0,
                   "signal_limit_down": True},
        ("A", 2): {"open": 9.0, "high": 9.0, "low": 9.0, "close": 9.0,
                   "signal_limit_down": True},
        ("A", 3): {"open": 10.2, "high": 10.2, "low": 10.2, "close": 10.2},
    })
    result = _run(
        panel, {("A", 0)}, set(),
        _config(matching="close_t", entry_fill="close_t", exit_fill="close_t",
                stop_loss_pct=-0.06),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "end"            # 覆盖 pending 的 "stop_loss"
    assert str(trade.exit_date) == "2025-01-05"
    assert trade.exit_price == 10.2
    assert trade.open_at_end is False
    assert trade.blocked_exit_days == 2          # 末日清算继承了两天拒卖记录

    row = _last_row(result)
    assert row["positions"] == 0
    assert row["cash"] == row["value"]           # 末行现金已含清算额
    assert result.stats["execution"]["pending_exit"] == 1
    assert result.stats["pending_exit_positions"] == 0


# --------------------------------------------------------------------- T-EOS-3
def test_t_eos_3_last_bar_entry_settles_same_open_price() -> None:
    """T-EOS-3 / P1：末日建仓也必须收敛到 SETTLED，且现金流与改前逐分相同。

    经济结果不变（同一末日开盘价买、同一末日开盘价卖，双边费用照收），只改记账
    位置：改前是 post-loop 的 _sell，改后是权益行写之前的结算步。
    """
    # 末日建仓只能经由"收盘计划 → 次日开盘成交"（plan_at_signal_close）：
    # 开盘阶段的 _process_entries 在末根被 :3996 的 `time_id < time_count - 1` 挡住，
    # 而 pending_buy_plans 在 :3945-3948 无条件执行 —— 这正是 P1 的真实入口。
    panel = _panel(["A"], 4, overrides={("A", 3): {"price": 12.0}})
    result = _run(
        panel, {("A", 2)}, set(), _config(fees_pct=0.001, plan_at_signal_close=True)
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert str(trade.entry_date) == "2025-01-05"   # 末日开盘建仓
    assert str(trade.exit_date) == "2025-01-05"
    assert trade.exit_price == trade.entry_price    # 同一末日开盘价
    assert trade.open_at_end is False
    # 契约写 duration==0，但 matrix_native 的 hold_days 在成交日初值为 1（:3427），
    # legacy 路径才是 0；该字段语义未变，故此处按引擎现值断言。
    assert trade.duration == 1

    row = _last_row(result)
    assert row["positions"] == 0
    # 现金流恒等式：期初 − 建仓支出 + 清算所得 = 末行现金（I1）
    assert row["cash"] == pytest.approx(
        100_000.0 - trade.entry_value + trade.exit_value, abs=0.01
    )
    assert row["cash"] == row["value"]
    # 双边费用各收一次（不是"免费"）：收益为负且幅度 ≈ 两个 10bp
    assert trade.pnl_amount < 0
    assert abs(trade.pnl_amount) == pytest.approx(trade.entry_value * 0.001 * 2, abs=1.0)


# --------------------------------------------------------------------- T-EOS-4
def test_t_eos_4_blocked_sell_on_last_bar_is_marked() -> None:
    """T-EOS-4 / P6：末日一字跌停不可成交 ⇒ MARKED（不再按更早的陈旧价清算）。

    末行含该股按末日收盘、exposure>0；trades 记 open_at_end=True、pnl_amount=0；
    现金不含该股。
    """
    panel = _panel(["A"], 4, overrides={
        ("A", 3): {"open": 9.0, "high": 9.0, "low": 9.0, "close": 9.0,
                   "signal_limit_down": True},
    })
    result = _run(panel, {("A", 0)}, set(), _config())

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "end"
    assert trade.open_at_end is True             # I3：MARKED
    assert trade.pnl_amount == 0.0
    assert trade.exit_price == 9.0               # 末日收盘
    assert str(trade.exit_date) == "2025-01-05"

    row = _last_row(result)
    shares = trade.shares
    assert row["positions"] == 1
    assert row["exposure"] > 0
    assert row["value"] == pytest.approx(row["cash"] + shares * 9.0, abs=0.01)
    # 现金不含该股：等于期初减建仓支出
    assert row["cash"] == pytest.approx(100_000.0 - trade.entry_value, abs=0.01)
    assert result.stats["pending_exit_positions"] == 1
    assert result.stats["open_at_end_count"] == 1
    assert result.stats["completed_trade_count"] == 0


# --------------------------------------------------------------------- T-EOS-5
def test_t_eos_5_finalize_open_at_end_still_marks() -> None:
    """T-EOS-5 / S-8：finalize_open_at_end=True 臂逐值不变（全部 MARKED）。"""
    panel = _panel(["A"], 4, overrides={
        ("A", 1): {"price": 10.0},
        ("A", 2): {"price": 11.0},
        ("A", 3): {"price": 12.0},
    })
    result = _run(panel, {("A", 0)}, {("A", 3)}, _config(finalize_open_at_end=True))

    row = _last_row(result)
    assert row["positions"] == 1
    assert result.stats["pending_exit_positions"] == 0

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.open_at_end is True
    assert trade.pnl_amount == 0.0
    assert trade.exit_price == 12.0              # execution_close[last]
    assert row["value"] == pytest.approx(row["cash"] + trade.shares * 12.0, abs=0.01)
    assert result.stats["completed_trade_count"] == 0
    assert result.stats["open_at_end_count"] == 1


# ------------------------------------------------------------------- P3 / P5
def test_p3_risk_latch_on_entry_day_does_not_escape_settlement() -> None:
    """P3：末日建仓 + 原始价基 ⇒ 建仓日分支写 risk_exit_reason（:4119）。

    该持仓在旧链上先命中 P1/P3 的 continue，拿不到 end；改后由持仓体顶部的结算步
    统一收敛，risk 闸门不会被写成"次日到期"而漏掉末日清算。
    """
    panel = _panel(["A"], 4, overrides={
        ("A", 3): {"open": 10.0, "high": 10.0, "low": 9.0, "close": 9.0},
    })
    result = _run(
        panel, {("A", 2)}, set(),
        _config(
            entry_price_basis="raw",
            stop_loss_pct=-0.06,
            plan_at_signal_close=True,   # 末日建仓的唯一入口（见 T-EOS-3）
        ),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "end"
    assert str(trade.entry_date) == "2025-01-05"
    assert str(trade.exit_date) == "2025-01-05"
    assert trade.exit_price == 10.0              # 同一末日开盘价
    row = _last_row(result)
    assert row["positions"] == 0
    assert row["cash"] == row["value"]


def test_p5_hold_policy_decision_on_last_bar_does_not_escape() -> None:
    """P5：末日恰是延展决策日且判为"不延展"⇒ 旧链写 next_open_exit_reason 后
    continue；改后仍由终结结算步清算（exit_reason=end，不再产生"次日到期"挂单）。
    """
    panel = _panel(["A"], 4, overrides={
        ("A", 1): {"price": 10.0},
        ("A", 2): {"open": 10.3, "high": 10.5, "low": 10.2, "close": 10.4},
        ("A", 3): {"open": 10.1, "high": 10.2, "low": 10.0, "close": 10.1},
    })
    result = _run(
        panel, {("A", 0)}, set(),
        _config(hold_extension_policy=HoldExtensionPolicy(
            decision_days=3,
            strong_hold_days=4,
            strong_hold_min_return=0.03,
            runner_new_high_days=3,
            runner_extend_days=4,
        )),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "end"
    assert str(trade.exit_date) == "2025-01-05"
    assert trade.exit_price == 10.1
    row = _last_row(result)
    assert row["positions"] == 0
    assert row["cash"] == row["value"]


# ---------------------------------------------------------------- carry_out
def test_carry_out_segment_does_not_settle() -> None:
    """S-7 反例：carry_out 分段的末日持仓必须原样结转，不得触发终结结算步。"""
    panel = _panel(["A"], 4, overrides={
        ("A", 1): {"price": 10.0},
        ("A", 2): {"price": 11.0},
        ("A", 3): {"price": 12.0},
    })
    matrix = build_market_matrix(
        panel,
        _mask(panel, {("A", 0)}),
        _mask(panel, {("A", 3)}),
        entry_delay_bars=1,
        exit_delay_bars=1,
    )
    result = BacktestEngine(repo=None).simulate_market_matrix(  # type: ignore[arg-type]
        matrix,
        _config(),
        options=SimulationOptions(
            include_monte_carlo=False,
            carry_in=None,
            carry_out=True,
        ),
    )

    assert result.carry_state is not None
    assert isinstance(result.carry_state, PortfolioCarryState)
    assert len(result.carry_state.positions) == 1
    assert result.carry_state.positions[0]["symbol"] == "A"
    # 末日信号转成跨段挂单，而不是在本段成交
    assert result.carry_state.positions[0]["pending_exit_reason"] == "signal"
    assert [t for t in result.trades if t.exit_reason == "end"] == []
    assert _last_row(result)["positions"] == 1
