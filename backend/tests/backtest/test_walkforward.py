"""Walk-forward 核心测试 — 滚动窗口 fold 生成 + OOS 聚合 + 编排。

被测:
- generate_folds: 滚动训练/测试窗口切分
- aggregate_oos: 从各折 OOS 结果聚合 (复利净值/IS-OOS 退化/一致性)
- WalkForwardService.run: 每折 训练区间优化 -> 测试区间 OOS 验证
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise

import pytest

from app.backtest.engine import PortfolioCarryState
from app.backtest.walkforward import (
    WalkForwardConfig,
    WalkForwardService,
    aggregate_oos,
    generate_folds,
)

# ---------------------------------------------------------------
# fold 生成
# ---------------------------------------------------------------

def test_folds_rolling_windows():
    # 1 年数据, 训练 90d / 测试 30d / 步进 30d
    folds = generate_folds(date(2024, 1, 1), date(2024, 12, 31), train_days=90, test_days=30, step_days=30)
    assert len(folds) > 0
    f0 = folds[0]
    assert f0.train_start == date(2024, 1, 1)
    assert f0.train_end == date(2024, 3, 31)     # +90d (2024 闰年)
    assert f0.test_start == date(2024, 4, 1)     # train_end + 1天 (隔断前视泄漏)
    assert f0.test_end == date(2024, 4, 30)
    # 滚动: 下一折训练起点 +step
    assert folds[1].train_start == date(2024, 1, 31)  # +30d


def test_folds_test_starts_day_after_train_end():
    """无前视泄漏: 每折 test_start 严格晚于 train_end (不共享同一天)。"""
    folds = generate_folds(date(2024, 1, 1), date(2024, 12, 31), train_days=90, test_days=30, step_days=30)
    for f in folds:
        assert f.test_start > f.train_end


def test_folds_no_test_beyond_end():
    folds = generate_folds(date(2024, 1, 1), date(2024, 12, 31), train_days=90, test_days=30, step_days=30)
    for f in folds:
        assert f.test_end <= date(2024, 12, 31)


def test_folds_insufficient_span_raises():
    # 训练90+测试30=120d, 但只有 100d 数据 -> 0 折
    with pytest.raises(ValueError, match=r"数据区间不足|至少"):
        generate_folds(date(2024, 1, 1), date(2024, 4, 10), train_days=90, test_days=30, step_days=30)


def test_folds_reject_nonpositive_windows():
    with pytest.raises(ValueError, match=r"必须为正"):
        generate_folds(date(2024, 1, 1), date(2024, 12, 31), train_days=0, test_days=30, step_days=30)


def test_folds_default_step_does_not_reuse_oos_dates():
    folds = generate_folds(
        date(2024, 1, 1), date(2024, 12, 31),
        train_days=90, test_days=30, step_days=30,
    )
    for previous, current in pairwise(folds):
        assert previous.test_end < current.test_start
    assert all((fold.test_end - fold.test_start).days + 1 == 30 for fold in folds)


def test_folds_reject_overlapping_oos_windows():
    with pytest.raises(ValueError, match="step_days"):
        generate_folds(
            date(2024, 1, 1), date(2024, 12, 31),
            train_days=90, test_days=30, step_days=15,
        )


def test_folds_single_day_oos_window():
    folds = generate_folds(
        date(2024, 1, 1), date(2024, 1, 10),
        train_days=2, test_days=1, step_days=1,
    )
    assert all(fold.test_start == fold.test_end for fold in folds)


def test_folds_use_actual_trading_days_not_calendar_days():
    trading_days = [
        date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4),
        date(2024, 1, 8), date(2024, 1, 9), date(2024, 1, 10),
        date(2024, 1, 11), date(2024, 1, 12),
    ]
    folds = generate_folds(
        date(2024, 1, 1), date(2024, 1, 31),
        train_days=3, test_days=2, step_days=2,
        trading_days=trading_days,
    )
    assert folds[0].train_start == date(2024, 1, 2)
    assert folds[0].train_end == date(2024, 1, 4)
    assert folds[0].test_start == date(2024, 1, 8)
    assert folds[0].test_end == date(2024, 1, 9)
    assert folds[1].test_start == date(2024, 1, 10)
    assert folds[1].test_end == date(2024, 1, 11)


def test_folds_trading_day_window_counts_are_exact():
    trading_days = [
        date(2024, 1, 2) + timedelta(days=offset) for offset in range(20)
    ]
    folds = generate_folds(
        date(2024, 1, 1), date(2024, 1, 31),
        train_days=10, test_days=5, step_days=5,
        trading_days=trading_days,
    )
    assert len(folds) == 2
    assert len([d for d in trading_days if folds[0].train_start <= d <= folds[0].train_end]) == 10
    assert len([d for d in trading_days if folds[0].test_start <= d <= folds[0].test_end]) == 5
    assert folds[0].test_end < folds[1].test_start


# ---------------------------------------------------------------
# OOS 聚合
# ---------------------------------------------------------------

def _rec(index, is_score, total_return, obj):
    return {
        "index": index,
        "test_end": date(2024, 1, 1),
        "best_params": {"p": index},
        "is_score": is_score,
        "oos_objective": obj,
        "oos_stats": {"total_return": total_return, "sortino": obj},
    }


def test_aggregate_compounds_oos_returns():
    recs = [_rec(0, 2.0, 0.10, 1.5), _rec(1, 2.0, -0.05, 0.8), _rec(2, 2.0, 0.08, 1.2)]
    agg = aggregate_oos(recs, objective="sortino")
    # 复利: 1.1 * 0.95 * 1.08 - 1
    assert abs(agg["compounded_oos_return"] - (1.10 * 0.95 * 1.08 - 1)) < 1e-9
    assert len(agg["oos_equity_curve"]) == 3


def test_aggregate_is_oos_degradation():
    # IS 目标平均远高于 OOS -> 退化为正 (过拟合信号)
    recs = [_rec(0, 3.0, 0.05, 0.5), _rec(1, 3.0, 0.02, 0.3)]
    agg = aggregate_oos(recs, objective="sortino")
    assert agg["avg_is_objective"] == 3.0
    assert abs(agg["avg_oos_objective"] - 0.4) < 1e-9
    assert agg["degradation"] > 0  # IS 3.0 - OOS 0.4 = 2.6


def test_aggregate_consistency_fraction_positive():
    # consistency 按 OOS 总收益 > 0 的折占比: total_return 0.1>0, -0.1<=0, 0.1>0 -> 2/3
    recs = [_rec(0, 1, 0.1, 1.5), _rec(1, 1, -0.1, -0.2), _rec(2, 1, 0.1, 0.8)]
    agg = aggregate_oos(recs, objective="sortino")
    assert agg["consistency"] == round(2 / 3, 4)  # 0.6667


def test_aggregate_degradation_direction_aware_for_min_objective():
    """min 类目标 (avg_holding_days, 越小越好): OOS 持仓天数更大 = 退化, degradation>0。"""
    # IS 持仓 3 天, OOS 持仓 5 天 (更长=更差) -> 退化
    recs = [{"index": 0, "test_end": date(2024, 1, 1), "is_score": 3.0,
             "oos_objective": 5.0, "oos_stats": {"total_return": 0.05}}]
    agg = aggregate_oos(recs, objective="avg_holding_days", direction="min")
    # 归一空间: norm(3)=-3, norm(5)=-5 -> degradation = -3 - (-5) = 2 > 0 = 退化
    assert agg["degradation"] == round(2.0, 4)


def test_aggregate_empty_folds():
    agg = aggregate_oos([], objective="sortino")
    assert agg["n_folds"] == 0
    assert agg["compounded_oos_return"] == 0.0


# ---------------------------------------------------------------
# 编排 (假 optimizer / service)
# ---------------------------------------------------------------

@dataclass
class _FakeResult:
    stats: dict
    error: str | None = None


class _FakeOptimizer:
    """optimize 返回受控 best_params/best_score, 记录被优化的训练区间。"""
    def __init__(self):
        self.train_ranges = []
        self.opt_kwargs = []  # 记录每折 IS 优化收到的 backtest_kwargs (验证 mode 强制)

    def optimize(self, cfg, progress_cb=None, cancel_event=None):
        self.train_ranges.append((cfg.start, cfg.end))
        self.opt_kwargs.append(dict(cfg.backtest_kwargs))
        # best_params 随训练起点变化, best_score 固定
        return {"best_params": {"p": cfg.start.month}, "best_score": 2.0, "results": [], "n_completed": 1}


# 从真实 PanelCache 取字段模板 —— 字段被重命名时本桩自动跟随, 避免 test 绿而生产 KeyError。
from app.backtest.engine import PanelCache

_ZERO_CACHE_STATS = {k: type(v)() for k, v in PanelCache().stats().items()}


class _FakeEngine:
    """最小引擎桩: 仅提供 WF 遥测所需的 cache_stats (字段同源自 PanelCache.stats)。"""
    def cache_stats(self):
        return dict(_ZERO_CACHE_STATS)


class _FakeService:
    """run 返回受控 OOS stats, 记录测试区间 + 收到的 params。

    stats 带 n_trades: 每折 OOS 交易数门槛 (fail-closed) 要求桩显式声明交易数,
    缺省 50 足以通过默认 min_trades_oos=10。
    """
    def __init__(self, n_trades=50):
        self.calls = []
        self.engine = _FakeEngine()
        self.n_trades = n_trades

    def run(self, config, progress_cb=None, cancel_event=None):
        self.calls.append({"start": config.start, "end": config.end,
                           "params": dict(config.params or {}), "mode": config.mode})
        return _FakeResult(stats={"total_return": 0.05, "sortino": 1.0, "n_trades": self.n_trades})


def _wf_cfg(**kw):
    trading_days = tuple(
        date(2024, 1, 1) + timedelta(days=offset)
        for offset in range((date(2024, 12, 31) - date(2024, 1, 1)).days + 1)
    )
    base = dict(
        strategy_id="s", symbols=None, start=date(2024, 1, 1), end=date(2024, 12, 31),
        param_grid={"p": [1, 2]}, objective="sortino",
        train_days=90, test_days=30, step_days=30,
        trading_days=trading_days,
    )
    base.update(kw)
    return WalkForwardConfig(**base)


def test_walkforward_optimizes_train_applies_oos():
    opt, svc = _FakeOptimizer(), _FakeService()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg())

    assert out["n_folds"] > 0
    # 每折: optimizer 在训练区间跑, service 在测试区间用最优参数跑
    assert len(opt.train_ranges) == out["n_folds"]
    assert len(svc.calls) == out["n_folds"]
    # OOS 回测用的是该折优化出的 best_params (来自训练起点月份)
    first_fold = out["folds"][0]
    assert svc.calls[0]["params"] == first_fold["best_params"]
    # 训练区间与测试区间不重叠 (测试在训练之后)
    assert svc.calls[0]["start"] >= opt.train_ranges[0][1]


class _CountingEngine:
    """首尾两次 cache_stats 返回不同值, 用于验证 WF 遥测差值/顺序计算 (非全零掩盖)。"""
    def __init__(self):
        self._n = 0

    def cache_stats(self):
        self._n += 1
        if self._n == 1:  # run 开头快照 (before)
            return {"compute_seconds": 1.0, "compute_count": 2, "hit_count": 0, "reuse_count": 0}
        return {"compute_seconds": 3.5, "compute_count": 7, "hit_count": 4, "reuse_count": 3}  # after


def test_walkforward_cache_telemetry_computes_deltas():
    """cache_telemetry 用首尾快照差值: scans/hits/reuses/秒数 = after - before, 且方向正确。"""
    opt, svc = _FakeOptimizer(), _FakeService()
    svc.engine = _CountingEngine()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg())

    tel = out["cache_telemetry"]
    assert tel["scans"] == 5          # 7 - 2, 顺序写反会得 -5
    assert tel["hits"] == 4           # 4 - 0
    assert tel["single_flight_reuses"] == 3  # 3 - 0
    assert abs(tel["load_panel_seconds"] - 2.5) < 1e-9  # 3.5 - 1.0
    assert tel["load_panel_pct"] >= 0.0  # 扫盘耗时 / WF总耗时, 非负


def test_walkforward_rejects_full_independent_candidate_mode():
    """full 样本曲线不是账户净值, 不得进入 WFO 复利汇总。"""
    opt, svc = _FakeOptimizer(), _FakeService()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    with pytest.raises(ValueError, match="只支持 position"):
        wf.run(_wf_cfg(backtest_kwargs={"mode": "full"}))
    assert opt.train_ranges == []
    assert svc.calls == []


def test_walkforward_forces_position_for_is_and_oos():
    opt, svc = _FakeOptimizer(), _FakeService()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    wf.run(_wf_cfg())
    assert all(kw["mode"] == "position" for kw in opt.opt_kwargs)
    assert all(c["mode"] == "position" for c in svc.calls)


def test_walkforward_reports_degradation():
    opt, svc = _FakeOptimizer(), _FakeService()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg())
    # IS best_score=2.0, OOS sortino=1.0 -> 退化 1.0
    assert out["summary"]["avg_is_objective"] == 2.0
    assert out["summary"]["avg_oos_objective"] == 1.0
    assert abs(out["summary"]["degradation"] - 1.0) < 1e-9


# ---------------------------------------------------------------
# 非矩阵后端的闸门: filter_history/内置走通用路径, 其余 fail-closed
# ---------------------------------------------------------------

class _FakeStrategyDef:
    def __init__(self, backend):
        self.execution_backend = backend


class _FakeStrategyEngine:
    def get(self, strategy_id):
        return _FakeStrategyDef(self._backend)

    def __init__(self, backend):
        self._backend = backend


def test_walkforward_supports_filter_history_strategy():
    """python_history_legacy (filter_history) 策略走通用路径:
    不建共享矩阵, 每折在训练区间独立优化、测试区间独立 OOS。"""
    opt, svc = _FakeOptimizer(), _FakeService()
    wf = WalkForwardService(opt, svc, strategy_engine=_FakeStrategyEngine("python_history_legacy"))
    out = wf.run(_wf_cfg())

    assert out["n_folds"] > 0
    assert out["shared_market_data"] is False
    assert len(opt.train_ranges) == out["n_folds"]
    assert len(svc.calls) == out["n_folds"]
    first_fold = out["folds"][0]
    assert svc.calls[0]["params"] == first_fold["best_params"]
    assert svc.calls[0]["start"] >= opt.train_ranges[0][1]


def test_walkforward_supports_polars_expr_strategy():
    """内置 polars_expr 策略同样走通用路径 (与矩阵策略共用同一套折编排)。"""
    opt, svc = _FakeOptimizer(), _FakeService()
    wf = WalkForwardService(opt, svc, strategy_engine=_FakeStrategyEngine("polars_expr"))
    out = wf.run(_wf_cfg())
    assert out["n_folds"] > 0
    assert out["shared_market_data"] is False


def test_walkforward_rejects_minute_filter_strategy():
    """minute_filter / composite 无法用日线折编排评估: 保持 fail-closed。"""
    wf = WalkForwardService(
        _FakeOptimizer(), _FakeService(),
        strategy_engine=_FakeStrategyEngine("minute_filter"),
    )
    with pytest.raises(ValueError, match=r"步进优化暂仅支持|minute_filter"):
        wf.run(_wf_cfg())


class _NoParamsOptimizer(_FakeOptimizer):
    """模拟训练区间全组失败: best_params=None。"""
    def optimize(self, cfg, progress_cb=None, cancel_event=None):
        self.train_ranges.append((cfg.start, cfg.end))
        return {"best_params": None, "best_score": None, "results": [], "n_completed": 0}


class _ErrorService(_FakeService):
    """模拟 OOS 回测失败。"""
    def run(self, config, progress_cb=None, cancel_event=None):
        self.calls.append({"start": config.start, "end": config.end, "params": dict(config.params or {})})
        return _FakeResult(stats={}, error="no data")


def test_walkforward_skips_folds_without_optimized_params():
    """训练区间没优化出参数 (best_params=None) -> 跳过, 不用默认参数硬跑 OOS 伪装成有效折。"""
    opt, svc = _NoParamsOptimizer(), _FakeService()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg())
    assert out["n_folds"] == 0           # 无有效折
    assert out["n_skipped"] > 0          # 全部跳过
    assert svc.calls == []               # 不跑 OOS
    assert out["summary"]["compounded_oos_return"] == 0.0  # 无效折不污染净值


def test_walkforward_skips_oos_error_folds():
    """OOS 回测失败的折 -> 跳过, 不把空/0 收益混入复利曲线。"""
    opt, svc = _FakeOptimizer(), _ErrorService()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg())
    assert out["n_folds"] == 0
    assert out["n_skipped"] > 0
    assert len(svc.calls) > 0            # OOS 跑了但失败
    assert out["summary"]["compounded_oos_return"] == 0.0  # 失败折不计入


def test_walkforward_cancel_stops():
    import threading
    ev = threading.Event()
    ev.set()
    opt, svc = _FakeOptimizer(), _FakeService()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg(), cancel_event=ev)
    # 取消 -> 不跑任何折
    assert svc.calls == []
    assert out["n_folds"] == 0


# ---------------------------------------------------------------
# API: job_key 回吐 + cancel 按 key 查表
# ---------------------------------------------------------------

def test_wf_job_key_distinguishes_windows():
    from app.api.backtest import _make_wf_job_key
    base = _make_wf_job_key("s", None, None, None, '{"p":[1]}', "sortino", None, "252/63/63", "sig")
    assert base != _make_wf_job_key("s", None, None, None, '{"p":[1]}', "sortino", None, "120/30/30", "sig")


def test_wf_job_key_distinguishes_params_and_overrides():
    """params/overrides 不同必须产出不同 job_key —— 否则 stream 与 cancel 会错配到别的任务。"""
    from app.api.backtest import _make_wf_job_key
    base = _make_wf_job_key("s", None, None, None, '{"p":[1]}', "sortino", None, "252/63/63", "sig")
    # params 不同 (未扫描参数固定值不同 -> 优化的策略不同)
    assert base != _make_wf_job_key(
        "s", None, None, None, '{"p":[1]}', "sortino", None, "252/63/63", "sig", params='{"x":1}')
    # overrides 不同 (basic_filter/信号/风控 不同)
    assert base != _make_wf_job_key(
        "s", None, None, None, '{"p":[1]}', "sortino", None, "252/63/63", "sig", overrides='{"score_min":5}')
    # 相同 params/overrides 必须稳定一致 (stream 端与 cancel 端对齐前提)
    k = _make_wf_job_key("s", None, None, None, '{"p":[1]}', "sortino", None, "252/63/63", "sig", params='{"x":1}')
    assert k == _make_wf_job_key(
        "s", None, None, None, '{"p":[1]}', "sortino", None, "252/63/63", "sig", params='{"x":1}')


def test_wf_job_key_distinguishes_min_trades_gate():
    from app.api.backtest import _make_wf_job_key
    base = _make_wf_job_key("s", None, None, None, '{"p":[1]}', "sortino", None, "252/63/63", "sig")
    assert base != _make_wf_job_key(
        "s", None, None, None, '{"p":[1]}', "sortino", None, "252/63/63", "sig",
        min_trades_oos=20,
    )


def test_walkforward_preview_uses_repository_trading_days():
    import asyncio
    from types import SimpleNamespace

    from app.api.backtest import walkforward_preview

    trading_days = [
        date(2024, 1, 2) + timedelta(days=offset) for offset in range(20)
    ]
    repo = SimpleNamespace(
        list_enriched_dates=lambda start, end: trading_days,
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo)))
    out = asyncio.run(walkforward_preview(
        request, "2024-01-01", "2024-01-31",
        train_days=10, test_days=5, step_days=5,
    ))
    assert out["window_basis"] == "trading_days"
    assert out["n_trading_days"] == 20
    assert out["n_folds"] == 2
    assert out["folds"][0]["test_start"] == "2024-01-12"


def test_wf_cancel_by_echoed_key():
    import asyncio

    from app.api.backtest import _BacktestJob, _running_jobs, walkforward_cancel

    class _Req:
        def __init__(self, body):
            self._body = body
        async def json(self):
            return self._body

    key = "wfkey_test_1"
    _running_jobs[key] = _BacktestJob(key)
    try:
        res = asyncio.run(walkforward_cancel(_Req({"job_key": key})))
        assert res["ok"] is True
        assert _running_jobs[key].cancel_event.is_set()
        res2 = asyncio.run(walkforward_cancel(_Req({"job_key": "nope"})))
        assert res2["ok"] is False
    finally:
        _running_jobs.pop(key, None)


# ---------------------------------------------------------------
# 每折 OOS 交易数门槛 (共享护栏 trades_ok, fail-closed)
# ---------------------------------------------------------------

def test_walkforward_oos_min_trades_keeps_thin_folds_with_warning():
    """OOS 交易数不足仍保留经济结果, 只标记统计证据不足。"""
    opt, svc = _FakeOptimizer(), _FakeService(n_trades=3)  # 3 < 默认 10
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg())

    assert out["n_planned_folds"] > 0
    assert out["n_folds"] == out["n_planned_folds"]
    assert out["n_skipped"] == 0
    assert all(fold["statistically_insufficient"] for fold in out["folds"])
    assert out["summary"]["n_insufficient_trades"] == out["n_folds"]
    assert out["summary"]["n_sufficient_trades"] == 0


def test_aggregate_oos_includes_thin_fold_economic_return():
    records = [
        {"index": 0, "test_end": date(2024, 1, 1), "is_score": 1.0,
         "oos_objective": 1.0, "statistically_insufficient": False,
         "oos_stats": {"total_return": 0.10}},
        {"index": 1, "test_end": date(2024, 2, 1), "is_score": 1.0,
         "oos_objective": 1.0, "statistically_insufficient": True,
         "oos_stats": {"total_return": -0.20}},
    ]
    summary = aggregate_oos(records, "sortino")
    assert summary["n_folds"] == 2
    assert summary["n_sufficient_trades"] == 1
    assert summary["n_insufficient_trades"] == 1
    assert summary["compounded_oos_return"] == round(1.10 * 0.80 - 1, 4)
    assert summary["consistency"] == 0.5
    assert summary["consistency_sufficient"] == 1.0
    assert summary["return_kind"] == "compounded_fold_returns_not_continuous_account"


def test_walkforward_resolves_actual_trading_days_from_repository():
    class _Repo:
        def list_enriched_dates(self, start, end, asset_type="stock"):
            assert asset_type == "stock"
            return [date(2024, 1, 2) + timedelta(days=offset) for offset in range(20)]

    class _Engine:
        repo = _Repo()
        def cache_stats(self):
            return dict(_ZERO_CACHE_STATS)

    class _Service(_FakeService):
        def __init__(self):
            super().__init__()
            self.engine = _Engine()

    opt, svc = _FakeOptimizer(), _Service()
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg(
        start=date(2024, 1, 1), end=date(2024, 1, 31),
        train_days=10, test_days=5, step_days=5, trading_days=(),
    ))
    assert out["window_basis"] == "trading_days"
    assert out["n_trading_days"] == 20
    assert out["n_planned_folds"] == 2


def test_walkforward_oos_min_trades_gate_disabled_when_zero():
    """min_trades_oos<=0 关闭门槛: 少交易折恢复计入 (向后兼容开关)。"""
    opt, svc = _FakeOptimizer(), _FakeService(n_trades=3)
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg(min_trades_oos=0))

    assert out["n_folds"] == out["n_planned_folds"]
    assert out["n_skipped"] == 0


def test_walkforward_oos_missing_n_trades_marks_insufficient():
    """stats 缺 n_trades 字段按统计证据不足标记, 不剔除其经济结果。"""
    opt, svc = _FakeOptimizer(), _FakeService(n_trades=3)
    orig_run = svc.run

    def run_without_trades(config, **kw):
        res = orig_run(config, **kw)
        res.stats.pop("n_trades")
        return res

    svc.run = run_without_trades
    wf = WalkForwardService(opt, svc, strategy_engine=None)
    out = wf.run(_wf_cfg())

    assert out["n_folds"] == out["n_planned_folds"]
    assert out["n_skipped"] == 0
    assert all(fold["statistically_insufficient"] for fold in out["folds"])


def test_walkforward_stream_rejects_degenerate_objective():
    """P4 白名单全面生效: 退化目标 (win_rate) 在 walkforward 端点层即被 400 拒绝。"""
    import asyncio

    from fastapi import HTTPException

    from app.api.backtest import walkforward_stream

    class _Req:
        def __init__(self):
            self.app = None

    with pytest.raises(HTTPException) as ei:
        asyncio.run(walkforward_stream(_Req(), strategy_id="s", param_grid='{"p":[1]}', objective="win_rate"))
    assert ei.value.status_code == 400
    assert "退化" in str(ei.value.detail) or "不适合" in str(ei.value.detail)


def test_walkforward_stream_rejects_full_mode_before_job_admission():
    import asyncio

    from fastapi import HTTPException

    from app.api.backtest import walkforward_stream

    class _Req:
        app = None

    with pytest.raises(HTTPException) as ei:
        asyncio.run(walkforward_stream(
            _Req(), strategy_id="s", param_grid='{"p":[1]}', mode="full",
        ))
    assert ei.value.status_code == 400
    assert "position" in str(ei.value.detail)


# ---------------------------------------------------------------
# 连续账户 replay
# ---------------------------------------------------------------

@dataclass
class _CarryResult:
    stats: dict
    equity_curve: list
    drawdown_curve: list
    trades: list
    carry_state: PortfolioCarryState | None
    error: str | None = None


class _CarryService:
    """按折返回递增权益, 记录每折收到的结转状态与 carry_out 标志。"""

    def __init__(self, fail_on_call: int | None = None):
        self.calls = []
        self.engine = _FakeEngine()
        self.fail_on_call = fail_on_call
        self._equity = 100_000.0

    def run(self, config, progress_cb=None, cancel_event=None):
        self.calls.append({
            "start": config.start,
            "end": config.end,
            "params": dict(config.params or {}),
            "carry_in": config.carry_state,
            "carry_out": config.carry_out,
        })
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            return _CarryResult(
                stats={"error": "boom", "n_trades": 0},
                equity_curve=[], drawdown_curve=[], trades=[],
                carry_state=None, error="boom",
            )
        self._equity += 1_000.0
        open_at_end = 0 if config.carry_out else 2
        trades = []
        for index in range(20):
            is_open = index < open_at_end
            trades.append({
                "symbol": f"S{index}.SH",
                "name": f"S{index}",
                "entry_date": str(config.start),
                "exit_date": "" if is_open else str(config.end),
                "entry_price": 10.0,
                "exit_price": 0.0 if is_open else 10.5,
                "pnl_pct": 0.0 if is_open else 0.05,
                "duration": 0 if is_open else 5,
                "exit_reason": "end" if is_open else "signal",
                "shares": 100.0, "lots": 1.0, "position_pct": 0.01,
                "entry_value": 1_000.0, "exit_value": 0.0 if is_open else 1_050.0,
                "pnl_amount": 0.0 if is_open else 50.0,
                "entry_score": 1.0,
                "entry_signal_date": str(config.start),
                "exit_signal_date": None if is_open else str(config.end),
                "blocked_exit_days": 0,
                "open_at_end": is_open,
                "entry_signal_id": None, "exit_signal_id": None,
            })
        carry = (
            PortfolioCarryState(
                cash=self._equity,
                peak=self._equity,
                positions=[{
                    "symbol": "A", "asset_id": 0, "shares": 100, "entry_price": 10.0,
                    "entry_date": str(config.start), "entry_value": 1_000.0,
                    "position_pct": 0.01, "entry_score": 1.0, "max_high": 10.0,
                    "max_close": 10.0, "risk_entry_price": 10.0, "hold_days": 1,
                    "blocked_exit_days": 0, "cash_dividends": 0.0,
                }],
            )
            if config.carry_out else None
        )
        return _CarryResult(
            stats={
                "total_return": 0.01, "sortino": 1.0, "n_trades": 20,
                "final_equity": self._equity, "n_trades_ok": True,
                "completed_trade_count": 20 - open_at_end,
                "open_at_end_count": open_at_end,
            },
            equity_curve=[{
                "date": str(config.end), "value": self._equity,
                "cash": round(self._equity * 0.5, 2),
                "positions": open_at_end, "exposure": 0.5,
            }],
            drawdown_curve=[{"date": str(config.end), "value": 0.0}],
            trades=trades,
            carry_state=carry,
        )


def test_continuous_account_carries_positions_across_folds():
    opt, svc = _FakeOptimizer(), _CarryService()
    out = WalkForwardService(opt, svc, strategy_engine=None).run(_wf_cfg())

    assert out["continuous_account"]["enabled"] is True
    assert out["summary"]["return_kind"] == "single_account_single_timeline"
    # 第一折没有结转, 中间折都从上一折持仓起步; 最后一折不再 carry_out。
    assert svc.calls[0]["carry_in"] is None
    assert svc.calls[0]["carry_out"] is True
    assert svc.calls[1]["carry_in"] is not None
    assert svc.calls[1]["carry_in"].positions[0]["symbol"] == "A"
    assert svc.calls[-1]["carry_out"] is False
    # 折边界持仓数被记录, 供审阅跨折是否真的延续。
    assert out["continuous_account"]["n_boundaries_with_positions"] == len(svc.calls) - 1
    assert out["continuous_account"]["duplicate_dates"] == 0
    # 逐折复利值保留, 但明确标注为诊断口径。
    assert out["summary"]["compounded_oos_return_is_diagnostic"] is True


def test_continuous_account_disabled_keeps_fold_local_accounts():
    opt, svc = _FakeOptimizer(), _CarryService()
    out = WalkForwardService(opt, svc, strategy_engine=None).run(
        _wf_cfg(continuous_account=False)
    )
    assert out["continuous_account"] is None
    assert out["summary"]["return_kind"] == "compounded_fold_returns_not_continuous_account"
    assert all(call["carry_in"] is None for call in svc.calls)
    assert all(call["carry_out"] is False for call in svc.calls)


def test_continuous_account_stops_replay_when_a_fold_fails():
    opt, svc = _FakeOptimizer(), _CarryService(fail_on_call=2)
    out = WalkForwardService(opt, svc, strategy_engine=None).run(_wf_cfg())

    assert out["continuous_account"]["stopped_early"]
    assert out["continuous_account"]["n_folds_replayed"] == 1
    assert len(svc.calls) == 2  # 第三折不再用失真的起始状态继续
    assert len(out["skipped"]) == 1


def test_final_open_positions_come_from_last_fold_not_missing_carry_state():
    """末折 carry_out=False 不产出 carry_state, 期末持仓必须取权益曲线末点。

    旧报告把"末折无 carry 状态"写成 0 持仓, 却同时保留 5 笔未平仓, 两者矛盾;
    本用例锁定最终头寸、现金、市值与未平仓交易数的一致性。
    """
    opt, svc = _FakeOptimizer(), _CarryService()
    out = WalkForwardService(opt, svc, strategy_engine=None).run(_wf_cfg())
    account = out["continuous_account"]

    assert account["final_positions"] == 2
    assert account["boundaries"][-1]["carried_out_positions"] == 2
    assert account["open_at_end_by_fold"][-1]["open_at_end"] == 2
    assert all(
        item["open_at_end"] == 0 for item in account["open_at_end_by_fold"][:-1]
    )
    assert account["trade_lifecycle"]["duplicate_trade_records"] == 0
    assert account["invariants"]["final_positions_match_open_trades"] is True
    assert account["invariants"]["open_trades_come_from_last_fold"] is True
    assert account["invariants"]["equity_equals_cash_plus_market_value"] is True


# ---------------------------------------------------------------
# 连续账户: 时间线必须逐日衔接 (审核 R3)
# ---------------------------------------------------------------

def test_continuous_account_rejects_sparse_windows_before_running():
    """step > test 会留下未回放的交易日, 连续账户必须拒绝而不是拼一条假曲线。"""
    opt, svc = _FakeOptimizer(), _FakeService()
    with pytest.raises(ValueError, match="step_days 必须等于 test_days"):
        WalkForwardService(opt, svc, strategy_engine=None).run(
            _wf_cfg(test_days=30, step_days=60)
        )
    assert svc.calls == []


def test_sparse_windows_still_allowed_when_continuous_account_disabled():
    """稀疏窗口只能用于逐折复利诊断; 关闭连续账户后不被误杀。"""
    opt, svc = _FakeOptimizer(), _FakeService()
    out = WalkForwardService(opt, svc, strategy_engine=None).run(
        _wf_cfg(test_days=30, step_days=60, continuous_account=False)
    )
    assert out["continuous_account"] is None
    assert out["summary"]["return_kind"] == "compounded_fold_returns_not_continuous_account"
    assert len(svc.calls) >= 2


class _GapOptimizer(_FakeOptimizer):
    """指定折的训练返回 no-best-params, 模拟中间折训练失败留下的时间缺口。"""

    def __init__(self, fail_index: int):
        super().__init__()
        self.fail_index = fail_index

    def optimize(self, cfg, progress_cb=None, cancel_event=None):
        result = super().optimize(cfg, progress_cb, cancel_event)
        if len(self.train_ranges) - 1 == self.fail_index:
            return {"best_params": None, "best_score": None, "results": [], "n_completed": 0}
        return result


def test_continuous_account_stops_at_training_gap_instead_of_skipping_days():
    """中间折训练失败 -> 缺口内无法回放, 停止并在报告里写明缺口日期。"""
    opt, svc = _GapOptimizer(fail_index=1), _CarryService()
    out = WalkForwardService(opt, svc, strategy_engine=None).run(_wf_cfg())
    account = out["continuous_account"]

    assert account["stopped_early"] and "中断" in account["stopped_early"]
    assert account["n_folds_replayed"] == 1
    assert len(svc.calls) == 1  # 缺口之后的折不再用失真的起始状态继续
    gap = account["timeline"]["trading_day_gap"]
    assert gap["after_fold"] == 0 and gap["before_fold"] == 2
    assert gap["missing_dates"][0] == "2024-04-30"
    assert len(gap["missing_dates"]) == 30
    assert account["timeline"]["complete"] is False
    # 曲线自身覆盖了它回放过的日期, 所以"日期覆盖"为 True; 真正说明不完整的是
    # timeline_complete —— 审核指出只看前面几项 invariants 会把断线当成完整账户。
    assert account["invariants"]["timeline_covers_trading_days"] is True
    assert account["invariants"]["timeline_complete"] is False
    # 提前收尾: 收益只覆盖已回放的那段, 口径必须自报部分区间, 且并列给出实际起止。
    assert account["return_kind"] == "partial_single_account_single_timeline"
    assert account["invariants"]["return_kind_matches_timeline"] is True
    span = account["replay_span"]
    assert span["covers_planned_span"] is False
    assert span["planned_end"] != span["end"]
    assert span["n_trading_days"] >= 1
    assert out["summary"]["return_kind"] == "partial_single_account_single_timeline"
    assert out["summary"]["continuous_replay_span"] == span


def test_continuous_account_reports_timeline_stopped_before_planned_end():
    """末折训练失败: 账户时间线提前结束, 必须显式标注而不是当作完整区间。"""
    folds = generate_folds(
        date(2024, 1, 1), date(2024, 12, 31),
        train_days=90, test_days=30, step_days=30,
        trading_days=tuple(
            date(2024, 1, 1) + timedelta(days=offset)
            for offset in range((date(2024, 12, 31) - date(2024, 1, 1)).days + 1)
        ),
    )
    opt, svc = _GapOptimizer(fail_index=len(folds) - 1), _CarryService()
    out = WalkForwardService(opt, svc, strategy_engine=None).run(_wf_cfg())
    account = out["continuous_account"]

    assert account["stopped_early"] and "其后 1 折" in account["stopped_early"]
    assert account["timeline"]["trading_day_gap"] is None
    assert account["timeline"]["complete"] is False
    assert account["invariants"]["timeline_complete"] is False


def test_continuous_account_reports_head_gap_when_early_folds_fail():
    """首折训练失败: 账户从第二折才开始, 必须写明更早交易日未计入。"""
    opt, svc = _GapOptimizer(fail_index=0), _CarryService()
    out = WalkForwardService(opt, svc, strategy_engine=None).run(_wf_cfg())
    account = out["continuous_account"]
    assert account["stopped_early"] and "开始" in account["stopped_early"]
    assert account["boundaries"][0]["index"] == 1
    assert account["timeline"]["complete"] is False
    assert account["invariants"]["timeline_complete"] is False


# ---------------------------------------------------------------
# 真实 API 契约: continuous_account 必须可注入并贯通配置 (审核 R1)
# ---------------------------------------------------------------

def _stream_events(client, path, params, limit=40):
    events = []
    with client.stream("GET", path, params=params) as response:
        assert response.status_code == 200, response.read()
        for line in response.iter_lines():
            if line.startswith("event: "):
                events.append(line[len("event: "):].strip())
            if events and events[-1] == "done":
                break
            if len(events) >= limit:
                break
    return events


def test_walkforward_stream_injects_continuous_account_and_emits_done(monkeypatch):
    """合法请求必须能建立 SSE 流 (旧缺陷: 未声明参数 -> NameError -> 500)。"""
    import inspect

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.backtest.worker as worker_module
    from app.api import backtest as api

    assert "continuous_account" in inspect.signature(api.walkforward_stream).parameters

    captured = {}

    def fake_make_worker_task(kind, data_dir, config):
        captured["kind"] = kind
        captured["config"] = config
        return {"kind": kind}

    def fake_run_worker_task(task, progress_cb, cancel_event):
        return {"objective": "sortino", "n_folds": 0, "folds": [], "summary": {},
                "continuous_account": None}

    class _NullSlot:
        def __call__(self, *args, **kwargs):
            return self
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False

    class _Limiter:
        def slot(self, *args, **kwargs):
            return _NullSlot()

    import app.services.heavy_job_limiter as limiter_module

    monkeypatch.setattr(worker_module, "make_worker_task", fake_make_worker_task)
    monkeypatch.setattr(worker_module, "run_worker_task", fake_run_worker_task)
    monkeypatch.setattr(limiter_module, "shared_heavy_job_limiter", _Limiter())
    monkeypatch.setattr(api, "admit_request", lambda *args, **kwargs: True)
    monkeypatch.setattr(api, "_daily_data_revisions", lambda: {})

    app = FastAPI()
    app.include_router(api.router)
    path = next(
        route.path for route in api.router.routes
        if str(getattr(route, "path", "")).endswith("/walkforward/stream")
    )
    base = {
        "strategy_id": "audit_dummy",
        "param_grid": '{"p":[1]}',
        "objective": "sortino",
        "train_days": 5,
        "test_days": 5,
        "step_days": 5,
        "start": "2025-01-01",
        "end": "2025-12-31",
        "mode": "position",
    }

    with TestClient(app) as client:
        for flag, expected in [(None, True), ("true", True), ("false", False)]:
            params = dict(base)
            if flag is not None:
                params["continuous_account"] = flag
            events = _stream_events(client, path, params)
            assert "job" in events
            assert "done" in events, events
            assert captured["kind"] == "walkforward"
            assert captured["config"].continuous_account is expected


def test_walkforward_stream_rejects_sparse_windows_for_continuous_account():
    import asyncio

    from fastapi import HTTPException

    from app.api.backtest import walkforward_stream

    class _Req:
        app = None

    with pytest.raises(HTTPException) as ei:
        asyncio.run(walkforward_stream(
            _Req(), strategy_id="s", param_grid='{"p":[1]}',
            train_days=5, test_days=5, step_days=10,
        ))
    assert ei.value.status_code == 400
    assert "step_days" in str(ei.value.detail)


def test_wf_job_key_distinguishes_continuous_account():
    from app.api.backtest import _make_wf_job_key

    args = dict(
        strategy_id="s", symbols="A", start="2025-01-01", end="2025-12-31",
        param_grid='{"p":[1]}', objective="sortino", direction=None,
        windows="5/5/5", bt_sig="bt", params=None, overrides=None,
        matrix_cache_max_mb=512, min_trades_oos=10,
    )
    key_on = _make_wf_job_key(**args, continuous_account=True)
    key_off = _make_wf_job_key(**args, continuous_account=False)
    assert key_on != key_off

# ---------------------------------------------------------------
# 契约收窄范围: 账户净值口径只在连续账户下成立 (审核 P2)
# ---------------------------------------------------------------

def test_continuous_account_rejects_full_mode():
    """连续账户 = 账户净值口径, 只接受 position; 拒绝发生在任何回放之前。"""
    opt, svc = _FakeOptimizer(), _FakeService()
    with pytest.raises(ValueError, match="连续账户只支持 position"):
        WalkForwardService(opt, svc, strategy_engine=None).run(
            _wf_cfg(backtest_kwargs={"mode": "full"})
        )
    assert svc.calls == []
    assert opt.opt_kwargs == []


def test_full_mode_still_allowed_when_continuous_account_disabled():
    """关闭连续账户 (逐折复利诊断) 时 mode=full 不被误杀, 且 OOS 真的按 full 跑。"""
    opt, svc = _FakeOptimizer(), _FakeService()
    out = WalkForwardService(opt, svc, strategy_engine=None).run(
        _wf_cfg(continuous_account=False, backtest_kwargs={"mode": "full"})
    )

    assert out["n_folds"] > 0
    # 训练恒 position: full 的样本收益曲线不是账户净值, 且可能用正式窗口后的 K 线退出。
    assert all(kw["mode"] == "position" for kw in opt.opt_kwargs)
    # OOS 保留调用方 mode, 不被静默改写为 position。
    assert all(call["mode"] == "full" for call in svc.calls)
    # 结果必须自报口径, 不能冒充账户净值。
    assert out["summary"]["return_kind"] == "compounded_fold_returns_not_continuous_account"


def test_walkforward_stream_mode_guard_limited_to_continuous_account(monkeypatch):
    """mode=full 只在连续账户下 400; 关闭连续账户后必须能入队且 mode 贯通配置。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.backtest.worker as worker_module
    from app.api import backtest as api

    captured = {}

    def fake_make_worker_task(kind, data_dir, config):
        captured["config"] = config
        return {"kind": kind}

    def fake_run_worker_task(task, progress_cb, cancel_event):
        return {"objective": "sortino", "n_folds": 0, "folds": [], "summary": {},
                "continuous_account": None}

    class _NullSlot:
        def __call__(self, *args, **kwargs):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class _Limiter:
        def slot(self, *args, **kwargs):
            return _NullSlot()

    import app.services.heavy_job_limiter as limiter_module

    monkeypatch.setattr(worker_module, "make_worker_task", fake_make_worker_task)
    monkeypatch.setattr(worker_module, "run_worker_task", fake_run_worker_task)
    monkeypatch.setattr(limiter_module, "shared_heavy_job_limiter", _Limiter())
    monkeypatch.setattr(api, "admit_request", lambda *args, **kwargs: True)
    monkeypatch.setattr(api, "_daily_data_revisions", lambda: {})

    app = FastAPI()
    app.include_router(api.router)
    path = next(
        route.path for route in api.router.routes
        if str(getattr(route, "path", "")).endswith("/walkforward/stream")
    )
    base = {
        "strategy_id": "audit_dummy",
        "param_grid": '{"p":[1]}',
        "objective": "sortino",
        "train_days": 5,
        "test_days": 5,
        "step_days": 5,
        "start": "2025-01-01",
        "end": "2025-12-31",
        "mode": "full",
    }

    with TestClient(app) as client:
        # 默认连续账户: 账户净值口径, full 直接 400 并提示关闭口径。
        rejected = client.get(path, params=base)
        assert rejected.status_code == 400, rejected.text
        assert "continuous_account=false" in rejected.text

        # 关闭连续账户: 逐折复利诊断口径, 必须放行且 mode 不被静默改写。
        events = _stream_events(client, path, {**base, "continuous_account": "false"})
        assert "job" in events and "done" in events, events
        assert captured["config"].continuous_account is False
        assert captured["config"].backtest_kwargs["mode"] == "full"
