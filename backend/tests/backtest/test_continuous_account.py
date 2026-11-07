"""连续账户 replay: 折边界结转现金/持仓/计划, 不重复成交, 缺标的 fail-closed。"""
from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from app.backtest.engine import (
    BacktestEngine,
    MatcherConfig,
    PortfolioCarryState,
    SimulationOptions,
)
from app.backtest.matrix import build_market_matrix


def _panel(days: int, symbol: str = "A") -> pl.DataFrame:
    start = date(2025, 1, 2)
    prices = [10.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0]
    rows = []
    for index in range(days):
        price = prices[index]
        rows.append({
            "symbol": symbol,
            "name": symbol,
            "date": start + timedelta(days=index),
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": 100_000,
            "score": 1.0,
            "signal_limit_up": False,
            "signal_limit_down": False,
            "amount": 3_000_000_000.0,
            "raw_close": price,
        })
    return pl.DataFrame(rows).sort(["symbol", "date"])


def _run(
    panel: pl.DataFrame,
    *,
    entry_rows: set[int],
    exit_rows: set[int],
    carry_in: PortfolioCarryState | None = None,
    carry_out: bool = False,
):
    entries = pl.Series([i in entry_rows for i in range(len(panel))])
    exits = pl.Series([i in exit_rows for i in range(len(panel))])
    matrix = build_market_matrix(
        panel,
        entries,
        exits,
        entry_delay_bars=1,
        exit_delay_bars=1,
    )
    config = MatcherConfig(
        matching="open_t+1",
        commission_pct=0.00025,
        stamp_tax_pct=0.0005,
        slippage_bps=5.0,
        max_positions=5,
        max_exposure_pct=1.0,
        initial_capital=100_000.0,
        finalize_open_at_end=False,
    )
    return BacktestEngine(repo=None).simulate_market_matrix(  # type: ignore[arg-type]
        matrix,
        config,
        options=SimulationOptions(
            include_monte_carlo=False,
            carry_in=carry_in,
            carry_out=carry_out,
        ),
    )


def test_split_segments_equal_one_continuous_run() -> None:
    """同一持仓跨段结转时, 两段回放的期末权益必须等于一次连续回放。"""
    whole = _panel(8)
    single = _run(whole, entry_rows={1}, exit_rows={4})
    assert single.trades, "单段回放必须产生一笔交易"
    trade = single.trades[0]
    assert str(trade.entry_date) == "2025-01-04"   # 信号 01-03 收盘 → 次日开盘
    assert str(trade.exit_date) == "2025-01-07"    # 信号 01-06 收盘 → 次日开盘
    assert trade.open_at_end is False

    # 折边界设在持仓期间 (第 5 根 K 线前), 卖点信号落在第一段末日。
    first = _run(whole.head(5), entry_rows={1}, exit_rows={4}, carry_out=True)
    assert first.carry_state is not None
    assert len(first.carry_state.positions) == 1
    assert first.carry_state.positions[0]["symbol"] == "A"
    assert first.carry_state.positions[0]["pending_exit_reason"] == "signal"

    second = _run(
        whole.tail(3),
        entry_rows=set(),
        exit_rows=set(),
        carry_in=first.carry_state,
    )
    assert len(second.trades) == 1
    carried_trade = second.trades[0]
    assert str(carried_trade.entry_date) == str(trade.entry_date)
    assert str(carried_trade.exit_date) == str(trade.exit_date)
    assert abs(second.stats["final_equity"] - single.stats["final_equity"]) < 0.01
    # 费用只收一次: 同一笔交易的现金盈亏一致。
    assert abs(carried_trade.pnl_amount - trade.pnl_amount) < 0.01


def test_last_day_entry_signal_carries_to_next_segment_open() -> None:
    """段末买入信号在单段内无次日可成交, 连续模式必须结转到下一段开盘。"""
    whole = _panel(8)
    first = _run(whole.head(4), entry_rows={3}, exit_rows=set(), carry_out=True)
    assert not first.trades
    assert first.carry_state is not None
    assert len(first.carry_state.pending_buy_plans) == 1
    plan = first.carry_state.pending_buy_plans[0]
    assert plan["symbol"] == "A"
    assert plan["signal_date"] == "2025-01-05"

    second = _run(
        whole.tail(4),
        entry_rows=set(),
        exit_rows=set(),
        carry_in=first.carry_state,
        carry_out=True,
    )
    assert len(second.trades) == 0
    assert second.carry_state is not None
    assert len(second.carry_state.positions) == 1
    assert second.carry_state.positions[0]["entry_signal_date"] == "2025-01-05"
    assert second.carry_state.positions[0]["entry_date"] == "2025-01-06"


def test_carried_position_missing_from_next_matrix_fails_closed() -> None:
    """下一段矩阵没有该标的时必须报错, 不能静默丢弃持仓。"""
    whole = _panel(8)
    first = _run(whole.head(5), entry_rows={1}, exit_rows=set(), carry_out=True)
    other = _panel(3, symbol="B")
    with pytest.raises(ValueError, match="结转持仓"):
        _run(other, entry_rows=set(), exit_rows=set(), carry_in=first.carry_state)


def test_no_carry_out_still_settles_positions_at_end() -> None:
    """普通单段行为不变: 不结转时仍按原逻辑在段末处理持仓。"""
    whole = _panel(6)
    segment = _run(whole.head(5), entry_rows={1}, exit_rows=set(), carry_out=False)
    assert segment.carry_state is None
    assert segment.trades and segment.trades[0].exit_reason == "end"


def test_empty_fold_is_a_flat_segment_not_an_error() -> None:
    """连续回放允许空仓空信号的一段: 产出平线权益并继续结转。"""
    whole = _panel(3)
    result = _run(whole, entry_rows=set(), exit_rows=set(), carry_out=True)
    assert not result.stats.get("error")
    assert result.carry_state is not None
    assert result.carry_state.cash == pytest.approx(100_000.0)
    assert len(result.equity_curve) == len(whole)
    assert all(point["value"] == pytest.approx(100_000.0) for point in result.equity_curve)


# ---------------------------------------------------------------
# 持有期延展: 跨折结转的会话年龄必须与一次完整回放一致 (审核 R2)
# ---------------------------------------------------------------

from app.backtest.engine import HoldExtensionPolicy  # noqa: E402


def _policy_run(
    panel: pl.DataFrame,
    *,
    entry_rows: set[int],
    exit_rows: set[int] | None = None,
    carry_in: PortfolioCarryState | None = None,
    carry_out: bool = False,
    hold: HoldExtensionPolicy | None = None,
    plan_at_signal_close: bool = False,
    stop_loss_pct: float | None = None,
    commission_pct: float = 0.0,
    stamp_tax_pct: float = 0.0,
    slippage_bps: float = 0.0,
):
    entries = pl.Series([i in entry_rows for i in range(len(panel))])
    exits = pl.Series([i in (exit_rows or set()) for i in range(len(panel))])
    matrix = build_market_matrix(
        panel,
        entries,
        exits,
        entry_delay_bars=1,
        exit_delay_bars=1,
    )
    config = MatcherConfig(
        matching="open_t+1",
        entry_fill="open_t+1",
        exit_fill="open_t+1",
        fees_pct=0.0,
        commission_pct=commission_pct,
        stamp_tax_pct=stamp_tax_pct,
        slippage_bps=slippage_bps,
        max_positions=1,
        initial_capital=100_000.0,
        finalize_open_at_end=True,
        hold_extension_policy=hold,
        plan_at_signal_close=plan_at_signal_close,
        stop_loss_pct=stop_loss_pct,
    )
    return BacktestEngine(repo=None).simulate_market_matrix(  # type: ignore[arg-type]
        matrix,
        config,
        options=SimulationOptions(
            include_monte_carlo=False,
            carry_in=carry_in,
            carry_out=carry_out,
        ),
    )


def _flat_panel(days: int = 10) -> pl.DataFrame:
    """价格恒为 10: 既不新高也不强持有, 只有决策日到期的 time_exit。"""
    columns = ("open", "high", "low", "close", "raw_close")
    return _panel(days).with_columns(*[pl.lit(10.0).alias(name) for name in columns])


def _trade_signature(result):
    return [
        (trade.entry_date, trade.exit_date, trade.exit_reason, trade.duration)
        for trade in result.trades
    ]


def test_exit_signal_on_fold_last_day_fills_at_next_segment_open():
    """折末收盘卖点必须转成下一段开盘挂单, 不能因为切分被吞掉一天。

    完整回放里该卖点在下一根 K 线开盘成交; 拆段后第二段首个开盘价必须同一天
    同价成交, 否则账户会多持有一天并承担额外的隔夜风险。
    """
    panel = _flat_panel(10)
    exit_rows = {4}  # 信号落在第一段末行 (split=5), 成交应在第二段首行
    full = _policy_run(panel, entry_rows={0}, exit_rows=exit_rows)
    first = _policy_run(panel.head(5), entry_rows={0}, exit_rows=exit_rows, carry_out=True)
    second = _policy_run(
        panel.tail(5),
        entry_rows=set(),
        exit_rows=exit_rows,
        carry_in=first.carry_state,
    )
    assert full.trades and full.trades[0].exit_reason == "signal"
    assert _trade_signature(first) + _trade_signature(second) == _trade_signature(full)
    assert second.trades[0].exit_date == full.trades[0].exit_date


def _execution_signature(result):
    """逐笔口径: 成交价/股数/净盈亏都要一致, 而不只是日期与退出原因。"""
    return [
        (
            trade.entry_date,
            trade.exit_date,
            round(float(trade.entry_price), 6),
            round(float(trade.exit_price), 6),
            round(float(trade.shares), 4),
            round(float(trade.pnl_amount), 4),
            trade.exit_reason,
            trade.duration,
        )
        for trade in result.trades
    ]


@pytest.mark.parametrize("split", [4, 5])
def test_hold_extension_matches_full_run_with_fees_and_cash(split):
    """含佣金/印花税/滑点: 拆段的逐笔成交、现金与期末权益都必须等于完整回放。

    审核 R2 要求的不只是退出日期: 费用与现金也要逐分对齐, 否则折边界仍可能
    通过"少收一次费用"或"晚一天释放现金"改变账户结果。
    """
    panel = _flat_panel(10)
    hold = HoldExtensionPolicy(decision_days=5)
    fees = dict(commission_pct=0.00025, stamp_tax_pct=0.0005, slippage_bps=5.0)
    full = _policy_run(panel, entry_rows={0}, hold=hold, **fees)
    first = _policy_run(
        panel.head(split), entry_rows={0}, carry_out=True, hold=hold, **fees
    )
    second = _policy_run(
        panel.tail(len(panel) - split),
        entry_rows=set(),
        carry_in=first.carry_state,
        hold=hold,
        **fees,
    )
    assert full.trades, "基准回放必须成交"
    assert _execution_signature(first) + _execution_signature(second) == _execution_signature(full)
    # 第一段末结转的现金 + 持仓市值必须等于完整回放同一交易日的账户权益
    # (价格恒为 10, 所以持仓市值 = 股数 * 10)。
    assert first.carry_state is not None
    full_equity_at_split = next(
        float(point["value"])
        for point in full.equity_curve
        if str(point["date"]) == str(first.equity_curve[-1]["date"])
    )
    carried_value = float(first.carry_state.cash) + sum(
        float(pos["shares"]) * 10.0 for pos in first.carry_state.positions
    )
    assert carried_value == pytest.approx(full_equity_at_split, abs=0.01)
    assert second.equity_curve[-1]["value"] == pytest.approx(
        full.stats["final_equity"], abs=0.01
    )


@pytest.mark.parametrize("split", [3, 4, 5, 6])
@pytest.mark.parametrize("plan_at_signal_close", [False, True])
def test_hold_extension_exit_matches_full_run_across_splits(split, plan_at_signal_close):
    """决策日 (第 5 个持有会话) 落在第几段都必须退出同一天。"""
    panel = _flat_panel(10)
    hold = HoldExtensionPolicy(decision_days=5)
    full = _policy_run(
        panel, entry_rows={0}, hold=hold, plan_at_signal_close=plan_at_signal_close
    )
    first = _policy_run(
        panel.head(split),
        entry_rows={0},
        carry_out=True,
        hold=hold,
        plan_at_signal_close=plan_at_signal_close,
    )
    second = _policy_run(
        panel.tail(len(panel) - split),
        entry_rows=set(),
        carry_in=first.carry_state,
        hold=hold,
        plan_at_signal_close=plan_at_signal_close,
    )

    assert full.trades, "基准回放必须成交"
    assert _trade_signature(second) == _trade_signature(full)
    assert second.stats["final_equity"] == pytest.approx(full.stats["final_equity"])


@pytest.mark.parametrize("split", [3, 5, 6])
def test_runner_extension_deadline_matches_full_run_across_splits(split):
    """延展到期日落在第二段时, 折边界不能把持有会话年龄清零。"""
    panel = _panel(10)  # 价格 10..18, 决策日新高 -> runner 延展
    hold = HoldExtensionPolicy(
        decision_days=5,
        strong_hold_days=10,
        strong_hold_min_return=10.0,  # 关闭强持有分支, 只留 runner
        runner_new_high_days=3,
        runner_extend_days=8,
    )
    full = _policy_run(panel, entry_rows={0}, hold=hold)
    first = _policy_run(panel.head(split), entry_rows={0}, carry_out=True, hold=hold)
    second = _policy_run(
        panel.tail(len(panel) - split),
        entry_rows=set(),
        carry_in=first.carry_state,
        hold=hold,
    )

    assert full.trades and full.trades[0].exit_reason == "time_exit"
    assert _trade_signature(second) == _trade_signature(full)
    assert second.stats["final_equity"] == pytest.approx(full.stats["final_equity"])


@pytest.mark.parametrize("split", [3, 4, 5])
def test_stop_loss_fires_on_same_session_after_carry(split):
    """止损落在第二段首日附近时, 结转持仓必须与一次完整回放同日止损、同日赎回。

    split=3 让入场成交正好落在第一段末行 (拆段最容易吞委托的位置), split=4 让
    跌停日落在第二段首行 (结转持仓的风险线), split=5 让止损发生在本段内。
    三段都按"第一段 + 第二段"的合并逐笔与期末权益对齐完整回放。
    """
    columns = ("open", "high", "low", "close", "raw_close")
    panel = _panel(8).with_row_index("idx").with_columns(*[
        pl.when(pl.col("idx") == 4).then(5.0).otherwise(10.0).alias(name)
        for name in columns
    ]).drop("idx")
    full = _policy_run(panel, entry_rows={1}, stop_loss_pct=0.1)
    first = _policy_run(panel.head(split), entry_rows={1}, carry_out=True, stop_loss_pct=0.1)
    second = _policy_run(
        panel.tail(len(panel) - split),
        entry_rows=set(),
        carry_in=first.carry_state,
        stop_loss_pct=0.1,
    )

    assert full.trades and full.trades[0].exit_reason == "stop_loss"
    assert _trade_signature(first) + _trade_signature(second) == _trade_signature(full)
    # 第二段可能是完全空仓的平段 (split=5 时止损已在第一段落账), stats 在这种
    # 形状下只保证 equity_curve, 因此用曲线末点对齐期末权益。
    assert second.equity_curve[-1]["value"] == pytest.approx(full.stats["final_equity"])


# ---------------------------------------------------------------
# 端到端: 真实撮合 + 真实 WalkForwardService 编排 (审核 R2/R3 合并验证)
# ---------------------------------------------------------------
from dataclasses import asdict  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from app.backtest.walkforward import WalkForwardConfig, WalkForwardService  # noqa: E402


class _FixedOptimizer:
    """训练段固定选同一组参数, 把注意力留给账户是否真的连续。"""

    def optimize(self, cfg, progress_cb=None, cancel_event=None):
        return {"best_params": {"p": 1}, "best_score": 1.0, "results": [], "n_completed": 1}


class _RealEngineService:
    """把每折窗口切到同一份受控行情上, 用真实撮合回放并结转账户。"""

    def __init__(self, panel: pl.DataFrame, entry_dates: set[str], hold=None,
                 stop_loss_pct: float | None = None):
        self.panel = panel
        self.entry_dates = entry_dates
        self.hold = hold
        self.stop_loss_pct = stop_loss_pct
        self.engine = BacktestEngine(repo=None)  # type: ignore[arg-type]
        self.calls: list[tuple[str, str, bool]] = []

    def run(self, config, progress_cb=None, cancel_event=None, prepared=None):
        seg = self.panel.filter(
            (pl.col("date") >= config.start) & (pl.col("date") <= config.end)
        )
        dates = [str(d) for d in seg["date"].to_list()]
        self.calls.append((str(config.start), str(config.end), bool(config.carry_out)))
        entries = pl.Series([d in self.entry_dates for d in dates])
        exits = pl.Series([False] * len(seg))
        matrix = build_market_matrix(seg, entries, exits, entry_delay_bars=1, exit_delay_bars=1)
        matcher = MatcherConfig(
            matching="open_t+1",
            entry_fill="open_t+1",
            exit_fill="open_t+1",
            fees_pct=0.0,
            commission_pct=0.00025,
            stamp_tax_pct=0.0005,
            slippage_bps=5.0,
            max_positions=1,
            initial_capital=100_000.0,
            finalize_open_at_end=False,
            hold_extension_policy=self.hold,
            stop_loss_pct=self.stop_loss_pct,
        )
        res = self.engine.simulate_market_matrix(
            matrix,
            matcher,
            options=SimulationOptions(
                include_monte_carlo=False,
                carry_in=config.carry_state,
                carry_out=bool(config.carry_out),
            ),
        )
        return SimpleNamespace(
            stats=dict(res.stats),
            equity_curve=res.equity_curve,
            drawdown_curve=res.drawdown_curve,
            trades=[asdict(trade) for trade in res.trades],
            carry_state=res.carry_state,
            error=res.stats.get("error"),
        )


def _wf_over_panel(panel: pl.DataFrame, entry_dates: set[str], hold, *, test_days: int, step_days: int):
    dates = tuple(sorted({d for d in panel["date"].to_list()}))
    cfg = WalkForwardConfig(
        strategy_id="s",
        symbols=None,
        start=dates[0],
        end=dates[-1],
        param_grid={"p": [1]},
        objective="sortino",
        train_days=2,
        test_days=test_days,
        step_days=step_days,
        min_trades_oos=0,
        trading_days=dates,
        backtest_kwargs={"mode": "position", "initial_capital": 100_000.0},
    )
    service = _RealEngineService(panel, entry_dates, hold=hold)
    out = WalkForwardService(_FixedOptimizer(), service, strategy_engine=None).run(cfg)
    return out, service


def test_walkforward_continuous_account_matches_single_replay() -> None:
    """真实 WFO 编排 + 真实撮合: 折边界结转的期末权益/成交必须等于一次完整回放。
    入场成交落在第一折首日, 持有延展的决策日 (第 5 个持有会话) 落在第二折首日,
    正是审核 R2 指出的"结转后按局部索引计日"会偏移的那一天。
    """
    panel = _flat_panel(10)
    hold = HoldExtensionPolicy(decision_days=5)
    # 入场信号必须落在第一折的测试段内 (train=2/test=4, 测试段为第 2..5 行);
    # 次日开盘成交 (第 3 行), 第 5 个持有会话的决策日落在第二折测试段 —— 正是
    # 结转后若按段内局部索引计日就会偏移的那一天。
    entry_index = 2
    entry_dates = {str(panel["date"][entry_index])}
    full = _policy_run(
        panel, entry_rows={entry_index}, hold=hold,
        commission_pct=0.00025, stamp_tax_pct=0.0005, slippage_bps=5.0,
    )
    assert full.trades and full.trades[0].exit_reason == "time_exit"

    out, service = _wf_over_panel(panel, entry_dates, hold, test_days=4, step_days=4)
    account = out["summary"]["continuous_account"]
    assert account is not None
    assert len(service.calls) >= 2
    assert account["stopped_early"] is None
    assert account["duplicate_dates"] == 0
    assert account["invariants"]["timeline_complete"] is True
    assert account["invariants"]["timeline_covers_trading_days"] is True
    # 完整回放时口径必须是完整账户, 且实际回放起止 == 计划区间 (审核 P3: 收益旁
    # 必须能直接看到它覆盖了哪几天)。
    assert account["return_kind"] == "single_account_single_timeline"
    assert account["invariants"]["return_kind_matches_timeline"] is True
    span = account["replay_span"]
    assert span["covers_planned_span"] is True
    assert span["start"] == span["planned_start"]
    assert span["end"] == span["planned_end"]
    assert span["n_trading_days"] > 0
    assert account["final_equity"] == pytest.approx(full.stats["final_equity"], abs=0.01)
    exits = [t["exit_date"] for t in account["trades"] if t.get("exit_date")]
    assert exits and exits[0] == full.trades[0].exit_date
    assert account["stats"]["total_return"] == pytest.approx(full.stats["total_return"], abs=1e-6)
