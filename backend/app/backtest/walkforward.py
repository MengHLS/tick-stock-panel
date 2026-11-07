"""Walk-forward 优化 — 滚动窗口的样本内优化 + 样本外验证。

每折在训练区间用参数网格优化选出最优参数, 再在紧邻的测试区间用该参数做样本外(OOS)
回测。滚动前移。核心产出是 OOS 拼接净值 + 每折 IS-vs-OOS 退化 —— 样本内漂亮、样本外
崩溃即过拟合信号, 单次样本内回测看不到。

依赖 PR2a 的 StrategyOptimizer 做每折训练区间的网格优化。
"""
from __future__ import annotations

import logging
import time
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.backtest.guards import trades_ok

logger = logging.getLogger(__name__)


@dataclass
class Fold:
    index: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date


def generate_folds(
    start: date,
    end: date,
    train_days: int,
    test_days: int,
    step_days: int,
    trading_days: Sequence[date] | None = None,
) -> list[Fold]:
    """滚动窗口 fold 切分: 训练窗口固定长度, 测试窗口紧接其后, 按 step 前移。

    传入 trading_days 时, train/test/step 均按实际交易日计数; 这是 WFO 生产
    路径的唯一口径。未传时保留自然日口径, 仅用于旧调用兼容和纯函数测试。
    测试区间与训练区间按日期严格错开, 区间均为闭区间。
    """
    if train_days <= 0 or test_days <= 0 or step_days <= 0:
        raise ValueError("train_days / test_days / step_days 必须为正")
    if step_days < test_days:
        raise ValueError("step_days 必须不小于 test_days，样本外测试区间不能重叠")

    if trading_days is not None:
        dates = sorted({
            day for day in trading_days
            if start <= day <= end
        })
        if len(dates) < train_days + test_days:
            raise ValueError(
                f"交易日区间不足以切出至少一折 "
                f"(需 train+test={train_days + test_days} 个交易日, 实有 {len(dates)} 个)"
            )
        folds: list[Fold] = []
        cursor = 0
        index = 0
        while cursor + train_days + test_days <= len(dates):
            train_end_index = cursor + train_days - 1
            test_start_index = train_end_index + 1
            test_end_index = test_start_index + test_days - 1
            folds.append(Fold(
                index,
                dates[cursor],
                dates[train_end_index],
                dates[test_start_index],
                dates[test_end_index],
            ))
            cursor += step_days
            index += 1
        if not folds:
            raise ValueError("交易日区间不足以切出至少一折")
        return folds

    folds: list[Fold] = []
    i = 0
    train_start = start
    while True:
        train_end = train_start + timedelta(days=train_days)
        # 测试区间从训练末日的次日开始: 回测区间是闭区间, 若 test_start==train_end 则
        # 该日 K 线同时进训练优化与 OOS 首日, 构成前视泄漏。后移一天隔断。
        test_start = train_end + timedelta(days=1)
        test_end = test_start + timedelta(days=test_days - 1)
        if test_end > end:
            break
        folds.append(Fold(i, train_start, train_end, test_start, test_end))
        i += 1
        train_start = train_start + timedelta(days=step_days)

    if not folds:
        raise ValueError(
            f"数据区间不足以切出至少一折 (需 train+test={train_days + test_days}天, "
            f"实有 {(end - start).days}天)"
        )
    return folds


def _norm(v: float, direction: str) -> float:
    """把目标值归一到"越大越好"空间, 以便跨目标一致地算退化 (min 类目标取负)。"""
    return -v if direction == "min" else v


def aggregate_oos(fold_records: list[dict], objective: str, direction: str = "max") -> dict:
    """从**已完成折** (IS 与 OOS 都成功) 聚合诊断统计。

    调用方传所有 OOS 成功折, 包括交易数不足的折; 后者用
    statistically_insufficient 标记, 不剔除其经济结果。

    - compounded_oos_return: 各折独立账户收益按折顺序的数学拼接, 不是连续账户净值
    - degradation: 归一空间下 IS 目标均值 - OOS 目标均值, 正值 = 样本外退化 (过拟合信号),
      对"越小越好"目标 (max_drawdown 等) 方向也正确
    - consistency: 所有已完成折中 OOS 总收益 > 0 的占比
    - consistency_sufficient: 仅交易数达标折的同一比例
    """
    n = len(fold_records)
    if n == 0:
        return {
            "n_folds": 0,
            "n_sufficient_trades": 0,
            "n_insufficient_trades": 0,
            "compounded_oos_return": 0.0,
            "return_kind": "compounded_fold_returns_not_continuous_account",
            "avg_is_objective": None,
            "avg_oos_objective": None,
            "degradation": None,
            "consistency": 0.0,
            "consistency_sufficient": None,
            "oos_equity_curve": [],
        }

    equity = 1.0
    curve: list[dict] = []
    n_positive = 0
    n_sufficient = 0
    n_insufficient = 0
    sufficient_positive = 0
    for f in fold_records:
        r = float(f["oos_stats"].get("total_return", 0.0) or 0.0)
        equity *= (1 + r)
        if r > 0:
            n_positive += 1
        insufficient = bool(f.get("statistically_insufficient"))
        if insufficient:
            n_insufficient += 1
        else:
            n_sufficient += 1
            if r > 0:
                sufficient_positive += 1
        curve.append({
            "fold": f["index"],
            "date": str(f["test_end"]),
            "value": round(equity, 4),
            "fold_return": round(r, 4),
            "statistically_insufficient": insufficient,
        })

    is_vals = [f["is_score"] for f in fold_records if f["is_score"] is not None]
    oos_vals = [f["oos_objective"] for f in fold_records if f["oos_objective"] is not None]
    avg_is = round(float(sum(is_vals) / len(is_vals)), 4) if is_vals else None
    avg_oos = round(float(sum(oos_vals) / len(oos_vals)), 4) if oos_vals else None
    degradation = (
        round(_norm(avg_is, direction) - _norm(avg_oos, direction), 4)
        if (avg_is is not None and avg_oos is not None) else None
    )

    return {
        "n_folds": n,
        "n_sufficient_trades": n_sufficient,
        "n_insufficient_trades": n_insufficient,
        "compounded_oos_return": round(equity - 1.0, 4),
        "return_kind": "compounded_fold_returns_not_continuous_account",
        "avg_is_objective": avg_is,
        "avg_oos_objective": avg_oos,
        "degradation": degradation,
        "consistency": round(n_positive / n, 4),
        "consistency_sufficient": (
            round(sufficient_positive / n_sufficient, 4)
            if n_sufficient else None
        ),
        "oos_equity_curve": curve,
    }


@dataclass
class WalkForwardConfig:
    strategy_id: str
    symbols: list[str] | None
    start: date
    end: date
    param_grid: dict
    objective: str = "sortino"
    train_days: int = 252
    test_days: int = 63
    step_days: int = 63
    direction: str | None = None
    min_trades_oos: int = 10            # 每折 OOS 段最小交易数 (<=0 关闭)
    max_workers: int = 4
    base_params: dict = field(default_factory=dict)
    overrides: dict | None = None
    backtest_kwargs: dict = field(default_factory=dict)
    matrix_cache_max_mb: int = 512
    # 生产路径由 repository 的实际 enriched 交易日解析; 显式传入用于
    # 离线复算和契约测试, 不改变 API 合同。
    trading_days: tuple[date, ...] = ()
    # 连续账户: 折边界结转现金/持仓/费用, 在唯一时间线上回放。
    # 关闭时保留旧的逐折独立账户口径 (仅用于对照, 不能当账户收益)。
    continuous_account: bool = True


class WalkForwardService:
    """滚动窗口 walk-forward: 每折训练区间优化 -> 测试区间 OOS 验证 -> 聚合。"""

    def __init__(self, optimizer, service, strategy_engine) -> None:
        self.optimizer = optimizer
        self.service = service
        self.strategy_engine = strategy_engine

    def _prepare_shared_matrix(
        self,
        cfg: WalkForwardConfig,
        folds: list[Fold],
        backtest_kwargs: dict | None = None,
    ):
        """Build one immutable superset matrix for every matrix-native fold.

        返回 None 时 run() 走通用路径: 每折独立优化 + OOS 回测, 正确但无共享矩阵加速。
        python_history_legacy (filter_history) 与 polars_expr (内置) 策略无法装入
        共享矩阵, 走通用路径; composite / minute_filter 仍不支持, 保持 fail-closed。
        """
        if self.strategy_engine is None or not folds:
            return None
        strategy = self.strategy_engine.get(cfg.strategy_id)
        if strategy.execution_backend != "matrix_native":
            if strategy.execution_backend in ("python_history_legacy", "polars_expr"):
                return None
            raise ValueError(
                f"步进优化暂仅支持矩阵(matrix_native)/日线历史(python_history_legacy/"
                f"polars_expr)策略; {cfg.strategy_id} 是 {strategy.execution_backend}"
            )

        from app.backtest.optimizer import expand_param_grid
        from app.backtest.strategy import StrategyBacktestConfig

        combos = expand_param_grid(strategy.meta.get("params", []), cfg.param_grid)
        shared_start = min(fold.train_start for fold in folds)
        shared_end = max(fold.test_end for fold in folds)
        configs = [
            StrategyBacktestConfig(
                strategy_id=cfg.strategy_id,
                symbols=cfg.symbols,
                start=shared_start,
                end=shared_end,
                params={**cfg.base_params, **combo},
                overrides=cfg.overrides,
                **(backtest_kwargs or cfg.backtest_kwargs),
            )
            for combo in combos
        ]
        return self.service.prepare_matrix_optimization(
            configs,
            matrix_cache_max_bytes=int(cfg.matrix_cache_max_mb) * 1024 * 1024,
        )

    def _resolve_trading_days(self, cfg: WalkForwardConfig) -> list[date]:
        if cfg.trading_days:
            return sorted({day for day in cfg.trading_days if cfg.start <= day <= cfg.end})
        repo = getattr(getattr(self.service, "engine", None), "repo", None)
        loader = getattr(repo, "list_enriched_dates", None)
        if not callable(loader):
            raise ValueError("无法解析实际交易日: 回测服务未提供 enriched 数据仓库")
        asset_type = str(cfg.backtest_kwargs.get("asset_type") or "stock")
        dates = loader(cfg.start, cfg.end, asset_type=asset_type)
        if not dates:
            raise ValueError("指定区间没有可用的 enriched 交易日")
        return sorted(set(dates))

    def _run_oos_fold(
        self,
        *,
        cfg: WalkForwardConfig,
        fold: Fold,
        base: dict,
        best_params: dict,
        is_score,
        direction: str,
        shared_market_data,
        cancel_event,
        backtest_kwargs: dict,
        carry_state=None,
        carry_out: bool = False,
    ) -> tuple[dict | None, dict | None, object]:
        """跑单折 OOS。返回 (成功记录, 跳过记录, OOS 结果)。

        ``carry_state`` 非空时把上一段账户状态交给撮合器, 段末不清算。
        """
        from app.backtest.strategy import StrategyBacktestConfig

        merged = {**cfg.base_params, **best_params}
        oos_cfg = StrategyBacktestConfig(
            strategy_id=cfg.strategy_id,
            symbols=cfg.symbols,
            start=fold.test_start,
            end=fold.test_end,
            params=merged,
            overrides=cfg.overrides,
            carry_state=carry_state,
            carry_out=carry_out,
            **backtest_kwargs,
        )
        oos_prepared = None
        try:
            if shared_market_data is not None:
                oos_prepared = self.service.prepare_matrix_optimization(
                    [oos_cfg],
                    matrix_cache_max_bytes=int(cfg.matrix_cache_max_mb) * 1024 * 1024,
                    market_data_override=shared_market_data,
                )
            if oos_prepared is None:
                oos_res = self.service.run(oos_cfg, cancel_event=cancel_event)
            else:
                oos_res = self.service.run(
                    oos_cfg,
                    cancel_event=cancel_event,
                    prepared=oos_prepared,
                )
        finally:
            if oos_prepared is not None:
                oos_prepared.compute_cache.close()

        if oos_res.error:
            return None, {
                **base,
                "best_params": best_params,
                "reason": f"OOS 回测失败: {oos_res.error}",
            }, oos_res

        oos_objective = oos_res.stats.get(cfg.objective)
        oos_degraded = (
            _norm(oos_objective, direction) < _norm(is_score, direction)
            if (oos_objective is not None and is_score is not None) else None
        )
        sufficient_trades = trades_ok(oos_res.stats, cfg.min_trades_oos)
        record = {
            **base,
            "best_params": best_params,
            "is_score": is_score,
            "oos_objective": oos_objective,
            "oos_degraded": oos_degraded,
            "trade_gate_ok": sufficient_trades,
            "statistically_insufficient": not sufficient_trades,
            "min_trades_oos": cfg.min_trades_oos,
            "oos_stats": oos_res.stats,
        }
        return record, None, oos_res

    def _run_continuous_oos(
        self,
        *,
        cfg: WalkForwardConfig,
        optimized: list[dict],
        skipped: list[dict],
        backtest_kwargs: dict,
        shared_market_data,
        cancel_event,
        progress_cb,
        done: int,
        n_total: int,
        direction: str,
        trading_days: Sequence[date] = (),
        planned_span: tuple[str, str] | None = None,
    ) -> tuple[list[dict], list[dict], dict]:
        """在同一账户、同一时间线上串行回放各折 OOS。

        折边界只切换参数, 不重置现金/持仓/峰值/费用累计。折内成交日期互不
        重叠 (生成折时已拒绝重叠测试窗), 因此不会重复计入同一天。
        """
        from app.backtest.engine import BacktestEngine, TradeRecord

        initial_capital = float(backtest_kwargs.get("initial_capital", 1_000_000.0))
        records: list[dict] = []
        equity_curve: list[dict] = []
        drawdown_curve: list[dict] = []
        all_trades: list[dict] = []
        execution_totals: dict[str, int] = {}
        boundaries: list[dict] = []
        seen_dates: set[str] = set()
        duplicate_dates = 0
        carry = None
        prev_equity = initial_capital
        stopped_early: str | None = None

        # 连续回放只允许各折测试窗在交易日历上首尾相接。中间折训练失败或无数据被
        # 跳过时, 缺口内既无参数也无行情, 持仓的止损/持有期/现金变化无法补算;
        # 在这里停止并显式报告缺口, 不用跳窗结果冒充连续账户。
        calendar = {day: i for i, day in enumerate(trading_days)}
        replay_limit = len(optimized)
        timeline_gap: dict | None = None
        missing_sessions: list[str] = []
        for position in range(1, len(optimized)):
            previous_fold = optimized[position - 1]["fold"]
            current_fold = optimized[position]["fold"]
            previous_index = calendar.get(previous_fold.test_end)
            current_index = calendar.get(current_fold.test_start)
            if previous_index is None or current_index is None:
                if not trading_days:
                    break
                replay_limit = position
                timeline_gap = {
                    "after_fold": previous_fold.index,
                    "before_fold": current_fold.index,
                    "missing_dates": [],
                    "unverifiable": True,
                }
                break
            if current_index <= previous_index + 1:
                continue
            missing_sessions = [
                day.isoformat()
                for day in trading_days[previous_index + 1:current_index]
            ]
            replay_limit = position
            timeline_gap = {
                "after_fold": previous_fold.index,
                "before_fold": current_fold.index,
                "missing_dates": missing_sessions,
            }
            break

        for index, item in enumerate(optimized[:replay_limit]):
            if cancel_event is not None and cancel_event.is_set():
                stopped_early = "cancelled"
                break
            fold = item["fold"]
            is_last = index == len(optimized) - 1
            carried_positions = list(carry.positions) if carry is not None else []
            record, skip, res = self._run_oos_fold(
                cfg=cfg,
                fold=fold,
                base=item["base"],
                best_params=item["best_params"],
                is_score=item["is_score"],
                direction=direction,
                shared_market_data=shared_market_data,
                cancel_event=cancel_event,
                backtest_kwargs=backtest_kwargs,
                carry_state=carry,
                carry_out=not is_last,
            )
            if skip is not None:
                # 连续账户一旦某折失败, 后续折的起始现金/持仓不再可信:
                # 停止回放并保留失败原因, 不用其余折拼一条假连续曲线。
                skipped.append(skip)
                stopped_early = skip["reason"]
                break

            reported_final = res.stats.get("final_equity")
            if reported_final is not None:
                final_equity = float(reported_final)
                segment_return = (
                    final_equity / prev_equity - 1.0 if prev_equity > 0 else 0.0
                )
            elif res.stats.get("total_return") is not None:
                # 只拿到段收益 (无账户权益) 时按段收益推进, 不把账户权益当作 0。
                segment_return = float(res.stats["total_return"])
                final_equity = prev_equity * (1.0 + segment_return)
            else:
                segment_return = 0.0
                final_equity = prev_equity
            stats = record["oos_stats"]
            stats["total_return"] = round(segment_return, 4)
            stats["account_total_return_cumulative"] = round(
                final_equity / initial_capital - 1.0, 4
            )
            record["account_equity_start"] = round(prev_equity, 2)
            record["account_equity_end"] = round(final_equity, 2)
            record["carried_in_positions"] = len(carried_positions)
            res_carry = getattr(res, "carry_state", None)
            res_curve = getattr(res, "equity_curve", []) or []
            if res_carry is not None:
                carried_out = len(res_carry.positions)
            elif res_curve:
                # 末折 carry_out=False, 不产出 carry_state; 真实期末持仓在权益曲线末点。
                carried_out = int(res_curve[-1].get("positions") or 0)
            else:
                carried_out = int(stats.get("open_at_end_count") or 0)
            record["carried_out_positions"] = carried_out
            record["open_positions_at_end"] = carried_out
            record["continuous"] = True
            records.append(record)

            for point in res_curve:
                day = str(point.get("date"))
                if day in seen_dates:
                    duplicate_dates += 1
                    continue
                seen_dates.add(day)
                equity_curve.append(point)
            drawdown_curve.extend(getattr(res, "drawdown_curve", []) or [])
            all_trades.extend(getattr(res, "trades", []) or [])
            for key, value in (stats.get("execution") or {}).items():
                execution_totals[key] = int(execution_totals.get(key, 0)) + int(value or 0)

            boundaries.append({
                "index": fold.index,
                "test_start": str(fold.test_start),
                "test_end": str(fold.test_end),
                "equity_start": round(prev_equity, 2),
                "equity_end": round(final_equity, 2),
                "segment_return": round(segment_return, 4),
                "carried_in_positions": len(carried_positions),
                "carried_out_positions": record["carried_out_positions"],
                "params_changed": bool(index > 0 and item["best_params"] != optimized[index - 1]["best_params"]),
                "pending_buy_plans": (
                    len(carry.pending_buy_plans) if carry is not None else 0
                ),
            })
            carry = res_carry
            prev_equity = final_equity

            if progress_cb is not None:
                progress_cb({
                    "type": "walkforward_progress",
                    "done": done,
                    "total": n_total,
                    "fold": fold.index,
                })

        if timeline_gap is not None:
            if missing_sessions:
                detail = (
                    f"缺少 {'/'.join(missing_sessions[:5])}"
                    f"{' 等' if len(missing_sessions) > 5 else ''} 共 "
                    f"{len(missing_sessions)} 个交易日未回放"
                )
            else:
                detail = "测试窗端点不在交易日历内, 无法核对衔接"
            stopped_early = (
                f"账户时间线在第 {timeline_gap['after_fold']} 折后中断: {detail}; "
                "缺口内持仓的止损/持有期无法继续管理, 已停止回放。"
            )
        elif optimized and optimized[0]["fold"].index != 0:
            # 头部缺口: 前几折没产出参数/行情, 账户从中间折开始, 之前的交易日
            # 不在账户里。必须显式说明, 不能让曲线"自身覆盖完整"冒充整段完整。
            head_gap = optimized[0]["fold"].index
            stopped_early = (
                f"账户时间线从第 {optimized[0]['fold'].index} 折 "
                f"({optimized[0]['fold'].test_start}) 开始: 此前 {head_gap} 折"
                "未产出可回放参数或行情, 更早的交易日不计入账户。"
            )
        elif optimized and optimized[-1]["fold"].index != n_total - 1:
            tail_missing = n_total - 1 - optimized[-1]["fold"].index
            stopped_early = (
                f"账户时间线停在第 {optimized[-1]['fold'].index} 折 "
                f"({optimized[-1]['fold'].test_end}): 其后 {tail_missing} 折未产出"
                "可回放参数或行情, 未回放的交易日不计入账户。"
            )

        values = [float(point["value"]) for point in equity_curve]
        exposures = [float(point.get("exposure") or 0.0) for point in equity_curve]
        trade_records = []
        for trade in all_trades:
            try:
                trade_records.append(TradeRecord(**trade))
            except TypeError:
                # 交易字典结构不匹配时宁可少算交易统计, 也不伪造一笔交易。
                continue
        stats = BacktestEngine._calc_portfolio_stats_from_values(
            values,
            exposures,
            trade_records,
            initial_capital,
        )
        stats["execution"] = execution_totals
        # stopped_early 时曲线只覆盖实际回放过的那段, 收益/年化也只覆盖该子区间;
        # 口径必须自报"部分区间", 否则读者会把子区间收益当成整段账户收益。
        return_kind = (
            "partial_single_account_single_timeline"
            if stopped_early is not None
            else "single_account_single_timeline"
        )
        stats["return_kind"] = return_kind
        last_point = equity_curve[-1] if equity_curve else {}
        final_cash = round(float(last_point.get("cash") or 0.0), 2)
        final_positions = int(last_point.get("positions") or 0)
        final_market_value = round(float(prev_equity) - final_cash, 2)
        trade_keys = [
            (
                str(trade.get("symbol")),
                str(trade.get("entry_date")),
                str(trade.get("exit_date")),
                round(float(trade.get("entry_value") or 0.0), 2),
            )
            for trade in all_trades
        ]
        duplicate_trades = len(trade_keys) - len(set(trade_keys))
        open_at_end_by_fold = [
            {
                "index": record["index"],
                "n_trades": int(record["oos_stats"].get("n_trades") or 0),
                "open_at_end": int(record["oos_stats"].get("open_at_end_count") or 0),
                "open_positions_at_end": int(record.get("open_positions_at_end") or 0),
            }
            for record in records
        ]
        open_at_end_total = sum(item["open_at_end"] for item in open_at_end_by_fold)
        # 账户日期覆盖: 回放区间内的每个交易日都必须出现在权益曲线上。计数/期末
        # 代数自洽不能证明时间线完整, 这一条才能暴露被跳过的交易日。
        curve_days = [str(point.get("date")) for point in equity_curve]
        missing_curve_dates: list[str] = []
        if curve_days and trading_days:
            first_day, last_day = curve_days[0], curve_days[-1]
            missing_curve_dates = [
                day.isoformat()
                for day in trading_days
                if first_day <= day.isoformat() <= last_day
                and day.isoformat() not in seen_dates
            ]
        invariants = {
            "equity_equals_cash_plus_market_value": (
                abs(final_cash + final_market_value - float(prev_equity)) < 0.01
            ),
            "final_positions_match_open_trades": (
                final_positions == int(stats.get("open_at_end_count") or 0)
            ),
            "trade_counts_add_up": (
                int(stats.get("completed_trade_count") or 0)
                + int(stats.get("open_at_end_count") or 0)
                == int(stats.get("n_trades") or 0)
            ),
            "fold_trade_counts_add_up": (
                sum(item["n_trades"] for item in open_at_end_by_fold)
                == int(stats.get("n_trades") or 0)
            ),
            "open_trades_come_from_last_fold": (
                open_at_end_total == int(stats.get("open_at_end_count") or 0)
                and all(item["open_at_end"] == 0 for item in open_at_end_by_fold[:-1])
            ),
            "no_duplicate_trade_records": duplicate_trades == 0,
            "timeline_covers_trading_days": not missing_curve_dates,
            # 回放区间内没有缺口, 且没有因训练失败/取消提前收尾才算完整时间线。
            # 只有这一项为 True 时, 上面的账户代数自洽才可以当作连续账户证据。
            "timeline_complete": (
                not missing_curve_dates
                and stopped_early is None
                and timeline_gap is None
            ),
            # 口径自述必须与时间线完整性一致: 提前收尾就不能再标成完整账户收益。
            "return_kind_matches_timeline": (
                (return_kind == "single_account_single_timeline")
                == (stopped_early is None)
            ),
        }
        if not all(invariants.values()):
            logger.warning("连续账户自洽性检查未通过: %s", invariants)
        # 实际回放起止: 与计划区间并列给出, 让"收益只覆盖哪几天"成为可核对字段,
        # 而不是只能从 stopped_early 的散文里推断。
        # 计划区间必须是"生成的全部折"的首/末测试窗, 不能取已回放的 boundaries ——
        # 提前停止时 boundaries 也短, 用它会算成"刚好覆盖", 把截断藏起来。
        if planned_span is not None:
            planned_start, planned_end = planned_span
        else:
            planned_start = boundaries[0]["test_start"] if boundaries else None
            planned_end = boundaries[-1]["test_end"] if boundaries else None
        replay_start = str(equity_curve[0].get("date")) if equity_curve else None
        replay_end = str(equity_curve[-1].get("date")) if equity_curve else None
        replay_span = {
            "start": replay_start,
            "end": replay_end,
            "n_trading_days": len(equity_curve),
            "planned_start": planned_start,
            "planned_end": planned_end,
            "covers_planned_span": bool(
                equity_curve
                and replay_start == planned_start
                and replay_end == planned_end
            ),
        }
        report = {
            "enabled": True,
            "return_kind": return_kind,
            "replay_span": replay_span,
            "initial_capital": round(initial_capital, 2),
            "final_equity": round(prev_equity, 2),
            "final_cash": final_cash,
            "final_positions": final_positions,
            "final_market_value": final_market_value,
            "n_folds_replayed": len(records),
            # 只数折与折之间的结转; 最后一折的期末持仓另由 final_positions 表示。
            "n_boundaries_with_positions": sum(
                1 for item in boundaries[:-1] if item["carried_out_positions"] > 0
            ),
            "duplicate_dates": duplicate_dates,
            "stopped_early": stopped_early,
            "timeline": {
                "complete": not missing_curve_dates and stopped_early is None,
                "n_missing_dates": len(missing_curve_dates),
                "missing_dates": missing_curve_dates[:20],
                "trading_day_gap": timeline_gap,
            },
            "carry_policy": (
                "折边界仅切换策略参数与信号; 现金、持仓、峰值和待执行开盘计划"
                "延续到下一折。已持仓继续按新折的风险/持有规则管理。"
            ),
            "boundaries": boundaries,
            "open_at_end_by_fold": open_at_end_by_fold,
            "trade_lifecycle": {
                "n_trades": int(stats.get("n_trades") or 0),
                "completed_trade_count": int(stats.get("completed_trade_count") or 0),
                "open_at_end_count": int(stats.get("open_at_end_count") or 0),
                "unique_trade_records": len(set(trade_keys)),
                "duplicate_trade_records": duplicate_trades,
            },
            "invariants": invariants,
            "stats": stats,
            # 账户级成交明细: 分段回放与整段回放的逐笔对照要靠它 (折记录只存统计)。
            "trades": all_trades,
            "equity_curve": equity_curve,
            "drawdown_curve": drawdown_curve,
        }
        return records, skipped, report

    def run(
        self,
        cfg: WalkForwardConfig,
        progress_cb=None,
        cancel_event=None,
    ) -> dict:
        from app.backtest.optimizer import OptimizeConfig, default_direction

        t0 = time.perf_counter()
        direction = cfg.direction or default_direction(cfg.objective)
        requested_mode = str(cfg.backtest_kwargs.get("mode") or "position")
        # 账户净值口径只在连续账户下成立: 唯一时间线必须是 position 组合账户。
        # 关闭连续账户时 (逐折复利诊断) 保留调用方 mode, 不把契约收窄扩大到公共路径。
        if cfg.continuous_account and requested_mode != "position":
            raise ValueError(
                "连续账户只支持 position 组合账户模式; full 独立候选曲线不是账户净值。"
                "需要 mode=full 请关闭 continuous_account, 该口径只作逐折复利诊断。"
            )
        if cfg.continuous_account and int(cfg.step_days) != int(cfg.test_days):
            # 跳窗 (step > test) 会在唯一账户时间线上留下未回放的交易日: 缺口内的
            # 止损、持有期、现金变化全部被跳过, 拼出来的"连续账户"不是账户净值。
            raise ValueError(
                "连续账户要求样本外区间逐日衔接: step_days 必须等于 test_days "
                f"(当前 step={cfg.step_days}, test={cfg.test_days})。"
                "需要稀疏窗口时请关闭 continuous_account, 该口径只作逐折复利诊断。"
            )
        trading_days = self._resolve_trading_days(cfg)
        folds = generate_folds(
            cfg.start, cfg.end, cfg.train_days, cfg.test_days, cfg.step_days,
            trading_days=trading_days,
        )
        n_total = len(folds)
        # 计划回放区间 = 全部生成折的首/末测试窗; 与"实际回放起止"并列报告。
        planned_span = (
            (str(folds[0].test_start), str(folds[-1].test_end)) if folds else None
        )

        # 训练恒用 position: full 的样本收益曲线不是账户净值, 且可能用正式窗口之后的
        # K 线完成退出 (前视)。连续账户的 OOS 也必须 position; 关闭连续账户时 OOS
        # 保留调用方 mode —— 该口径只作逐折复利诊断, 不作为账户净值。
        is_backtest_kwargs = {**cfg.backtest_kwargs, "mode": "position"}
        effective_backtest_kwargs = (
            is_backtest_kwargs if cfg.continuous_account else dict(cfg.backtest_kwargs)
        )
        shared_prepared = self._prepare_shared_matrix(
            cfg, folds, backtest_kwargs=effective_backtest_kwargs,
        )
        shared_market_data = (
            shared_prepared.market_data if shared_prepared is not None else None
        )
        shared_date_labels = (
            tuple(label[:10] for label in shared_market_data.timestamp_labels)
            if shared_market_data is not None
            else ()
        )

        def _shared_window_has_data(window_start: date, window_end: date) -> bool:
            index = bisect_left(shared_date_labels, window_start.isoformat())
            return index < len(shared_date_labels) and shared_date_labels[index] <= window_end.isoformat()

        # 遥测: 首尾快照 PanelCache, 量化跨折重叠区间重复扫盘的 IO 占比 (是否值得进一步优化)。
        cache_before = self.service.engine.cache_stats()

        completed_records: list[dict] = []  # IS 与 OOS 都成功, 计入聚合
        skipped: list[dict] = []          # 无优化结果 或 OOS 失败, 不计入聚合 (避免伪装成有效折)
        done = 0

        # IS 恒 position; OOS 用 effective_backtest_kwargs (连续账户下同为 position)。

        # 阶段 1: 逐折训练区间网格优化。先拿到全部折的参数, 才能在阶段 2
        # 把 OOS 串成一条连续账户时间线。
        optimized: list[dict] = []
        for f in folds:
            if cancel_event is not None and cancel_event.is_set():
                break

            base = {
                "index": f.index,
                "train_start": str(f.train_start),
                "train_end": str(f.train_end),
                "test_start": str(f.test_start),
                "test_end": str(f.test_end),
            }
            missing_window = None
            if shared_market_data is not None:
                if not _shared_window_has_data(f.train_start, f.train_end):
                    missing_window = "训练区间无可用行情数据"
                elif not _shared_window_has_data(f.test_start, f.test_end):
                    missing_window = "测试区间无可用行情数据"
            if missing_window is not None:
                skipped.append({**base, "reason": missing_window})
                done += 1
                if progress_cb is not None:
                    progress_cb({"type": "walkforward_progress", "done": done, "total": n_total, "fold": f.index})
                continue

            opt_cfg = OptimizeConfig(
                strategy_id=cfg.strategy_id,
                symbols=cfg.symbols,
                start=f.train_start,
                end=f.train_end,
                param_grid=cfg.param_grid,
                objective=cfg.objective,
                direction=cfg.direction,
                max_workers=cfg.max_workers,
                base_params=cfg.base_params,
                overrides=cfg.overrides,
                backtest_kwargs=is_backtest_kwargs,  # IS 强制 position, 堵前视泄漏
            )
            if shared_market_data is None:
                opt_res = self.optimizer.optimize(opt_cfg, cancel_event=cancel_event)
            else:
                opt_res = self.optimizer.optimize(
                    opt_cfg,
                    cancel_event=cancel_event,
                    prepared_market_data=shared_market_data,
                )
            best_params = opt_res.get("best_params")
            is_score = opt_res.get("best_score")
            done += 1

            # 训练区间没优化出参数 (全组失败/取消) -> 跳过, 不用默认参数硬跑 OOS 伪装成有效折
            if best_params is None:
                skipped.append({**base, "reason": "训练区间未优化出参数"})
                if progress_cb is not None:
                    progress_cb({"type": "walkforward_progress", "done": done, "total": n_total, "fold": f.index})
                continue
            optimized.append({
                "fold": f,
                "base": base,
                "best_params": best_params,
                "is_score": is_score,
            })

        # 阶段 2: OOS。连续账户把折边界作为参数切换点, 而不是账户重置点。
        continuous_report: dict | None = None
        if cfg.continuous_account and len(optimized) > 1:
            completed_records, skipped, continuous_report = self._run_continuous_oos(
                cfg=cfg,
                optimized=optimized,
                skipped=skipped,
                backtest_kwargs=effective_backtest_kwargs,
                shared_market_data=shared_market_data,
                cancel_event=cancel_event,
                progress_cb=progress_cb,
                done=done,
                n_total=n_total,
                direction=direction,
                trading_days=trading_days,
                planned_span=planned_span,
            )
        else:
            for item in optimized:
                if cancel_event is not None and cancel_event.is_set():
                    break
                f = item["fold"]
                record, skip, _ = self._run_oos_fold(
                    cfg=cfg,
                    fold=f,
                    base=item["base"],
                    best_params=item["best_params"],
                    is_score=item["is_score"],
                    direction=direction,
                    shared_market_data=shared_market_data,
                    cancel_event=cancel_event,
                    backtest_kwargs=effective_backtest_kwargs,
                )
                if skip is not None:
                    skipped.append(skip)
                elif record is not None:
                    completed_records.append(record)
                if progress_cb is not None:
                    progress_cb({"type": "walkforward_progress", "done": done, "total": n_total, "fold": f.index})

        summary = aggregate_oos(completed_records, cfg.objective, direction)
        if cfg.continuous_account and continuous_report is None:
            # 连续账户被请求但可回放折不足两折: 只能给逐折复利诊断值, 必须写明
            # 这不是账户净值, 而不是让调用方以为拿到了连续账户结果。
            summary["continuous_unavailable_reason"] = (
                f"连续账户共 {n_total} 折, 只有 {len(completed_records)} 折产出可回放"
                "结果, 无法构成连续时间线; 下面的汇总为逐折复利诊断值, 不是账户净值。"
            )
        if continuous_report is not None:
            # 连续账户口径是唯一可称为"账户收益"的汇总; 逐折复利值保留为诊断,
            # 两者差异本身就是旧口径忽略跨折持仓/现金的量化证据。
            summary["continuous_account"] = continuous_report
            # 跟随连续账户口径: 提前收尾时是部分区间收益, 不能对外仍标完整账户。
            summary["return_kind"] = continuous_report.get(
                "return_kind", "single_account_single_timeline"
            )
            summary["continuous_replay_span"] = continuous_report.get("replay_span")
            summary["compounded_oos_return_is_diagnostic"] = True
            if continuous_report.get("stopped_early"):
                summary["continuous_stopped_early"] = continuous_report["stopped_early"]

        shared_matrix_bytes = (
            shared_prepared.market_data.nbytes if shared_prepared is not None else 0
        )
        shared_matrix_status = (
            shared_prepared.market_data.cache_status if shared_prepared is not None else "none"
        )
        if shared_prepared is not None:
            shared_prepared.compute_cache.close()

        # 遥测收尾: 本次 WF 累计扫盘耗时 / 命中 / 复用, 与总耗时对比得出 load_panel 占比。
        cache_after = self.service.engine.cache_stats()
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        io_seconds = round(cache_after["compute_seconds"] - cache_before["compute_seconds"], 4)
        io_pct = round(io_seconds * 1000 / elapsed_ms * 100, 1) if elapsed_ms > 0 else 0.0
        cache_telemetry = {
            "load_panel_seconds": io_seconds,
            "load_panel_pct": io_pct,  # 扫盘耗时 / WF 总耗时
            "scans": cache_after["compute_count"] - cache_before["compute_count"],
            "hits": cache_after["hit_count"] - cache_before["hit_count"],
            "single_flight_reuses": cache_after["reuse_count"] - cache_before["reuse_count"],
        }
        logger.info(
            "walk-forward IO 占比: load_panel %.3fs (%.1f%% of %.1fms) | 扫盘 %d 次 命中 %d 复用 %d",
            io_seconds, io_pct, elapsed_ms,
            cache_telemetry["scans"], cache_telemetry["hits"], cache_telemetry["single_flight_reuses"],
        )

        return {
            "objective": cfg.objective,
            "direction": direction,
            "window_basis": "trading_days",
            "n_trading_days": len(trading_days),
            "n_folds": len(completed_records),
            "n_skipped": len(skipped),
            "n_planned_folds": n_total,
            "folds": completed_records,
            "skipped": skipped,
            "summary": summary,
            "continuous_account": continuous_report,
            "cache_telemetry": cache_telemetry,
            "shared_market_data": shared_prepared is not None,
            "shared_market_data_bytes": shared_matrix_bytes,
            "shared_market_data_status": shared_matrix_status,
            "elapsed_ms": elapsed_ms,
        }
