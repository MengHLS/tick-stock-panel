#!/usr/bin/env python
"""批量回测最小底座 (单进程) — 策略 × 参数组 逐组跑 IS/OOS 并落 registry.json。

设计边界 (只做 INTERFACE-MAP.md 里点名的 4 项能力, 不碰 backend 生产源码):

1. 切片级共享: 每个数据切片只调用一次 ``build_matrix_cache_profile`` +
   一次 ``engine.load_market_data_matrix_for_backtest``, 得到一个
   ``MarketDataMatrix``; 每个策略/每一折都用
   ``service.prepare_matrix_optimization([cfg], market_data_override=shared)``
   取只读时间视图 (``slice_market_data_matrix`` 返回视图, 不复制数组)。
   registry 里记录 ``matrix_load_count`` 与每次 prepare 的耗时/字节, 用来证明
   「同一切片的多个策略只装一次」而不是 N 策略 N 次装载。

2. 强制结果裁剪 ``BacktestResultPolicy``: IS 段裁掉曲线/逐笔/分标的/基准/MC;
   OOS 段保留曲线与逐笔 (连续账户时间线与账户级统计需要), 其余重字段裁掉,
   并在组结束后丢弃原始列表, 只落聚合值与哈希 (``--keep-raw`` 可保留)。
   ``--trim-oos`` 会把 OOS 曲线/逐笔也裁掉, 此时显式报告连续账户不可用。

3. fold 边界只用 ``repo.list_enriched_dates`` + ``generate_folds(trading_days=...)``,
   不做自然日切分。

4. 每次运行绑定 ``data_generation`` (装载前后一致才视为已绑定), 并把 evidence
   落到本目录 ``evidence/<run_id>.json``; ``registry.json`` 每个 run 含 run_id、
   策略与参数、数据版本、代码 sha256、耗时、内存峰值、n_trials 累计计数。

连续账户: 本文件的 ``_continuous_account`` 逐字段对齐
``WalkForwardService._run_continuous_oos`` 的账户口径 (结转 carry_state、
日期去重、交易日覆盖检查、``_calc_portfolio_stats_from_values`` 出统计),
并由 ``verify_batch.py`` 用生产 ``WalkForwardService.run`` 做独立单跑逐字段比对。

用法::

    backend/.venv/Scripts/python.exe research/batch-backtest-framework-20261107/run_batch.py \
        --groups research/batch-backtest-framework-20261107/groups.json \
        --start 2024-12-02 --end 2026-10-31 \
        --train-days 252 --test-days 63 \
        --out research/batch-backtest-framework-20261107/out

不提交、不部署、不重启、不写生产 data_dir (evidence 只落本目录)。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import psutil
from app.backtest.engine import BacktestEngine, TradeRecord
from app.backtest.guards import trades_ok
from app.backtest.optimizer import (
    OptimizeConfig,
    StrategyOptimizer,
    default_direction,
    expand_param_grid,
)
from app.backtest.strategy import (
    BacktestResultPolicy,
    ResolvedFeaturePlan,
    StrategyBacktestConfig,
    StrategyBacktestService,
    StrategyDependencyResolver,
    build_matrix_cache_profile,
)
from app.backtest.walkforward import Fold, aggregate_oos, generate_folds
from app.config import settings
from app.factors.ext_factors import ensure_synced
from app.factors.store import load_into_registry
from app.strategy import config as strategy_config
from app.strategy.engine import StrategyEngine
from app.tickflow.repository import DataStore, KlineRepository

BASE_COLUMNS = frozenset(
    {"symbol", "date", "open", "high", "low", "close", "volume", "raw_close", "raw_high"}
)
# 参与 code_sha256 的生产文件: 只要这些变了, 结果就不可与旧 registry 比较
CODE_FILES = (
    "backend/app/backtest/engine.py",
    "backend/app/backtest/strategy.py",
    "backend/app/backtest/walkforward.py",
    "backend/app/backtest/matrix.py",
    "backend/app/backtest/optimizer.py",
    "backend/app/backtest/evidence.py",
    "backend/app/tickflow/repository.py",
)


# --------------------------------------------------------------------------- #
# 取证小工具
# --------------------------------------------------------------------------- #
class PeakRssSampler(threading.Thread):
    """后台采样进程 RSS 峰值 (50ms), 用于报告 memory peak。"""

    def __init__(self, interval: float = 0.05) -> None:
        super().__init__(daemon=True)
        self.interval = interval
        self.peak_bytes = 0
        self._stop_event = threading.Event()
        self._proc = psutil.Process()

    def run(self) -> None:  # pragma: no cover - 线程循环
        while not self._stop_event.wait(self.interval):
            try:
                rss = self._proc.memory_info().rss
            except psutil.Error:
                return
            self.peak_bytes = max(self.peak_bytes, rss)

    def stop(self) -> float:
        self._stop_event.set()
        self.join(timeout=2.0)
        try:
            rss = self._proc.memory_info().rss
            self.peak_bytes = max(self.peak_bytes, rss)
        except psutil.Error:
            pass
        return round(self.peak_bytes / 1024 / 1024, 1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code_fingerprint() -> dict[str, Any]:
    per_file: dict[str, str] = {}
    combined = hashlib.sha256()
    for rel in CODE_FILES:
        path = REPO / rel
        if not path.exists():
            per_file[rel] = "missing"
            continue
        digest = sha256_file(path)
        per_file[rel] = digest
        combined.update(rel.encode("utf-8"))
        combined.update(digest.encode("ascii"))
    for extra in (Path(__file__).resolve(),):
        digest = sha256_file(extra)
        per_file[str(extra.name)] = digest
        combined.update(extra.name.encode("utf-8"))
        combined.update(digest.encode("ascii"))
    return {"sha256": combined.hexdigest(), "files": per_file}


def now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# 运行时
# --------------------------------------------------------------------------- #
@dataclass
class Runtime:
    data_dir: Path
    repo: KlineRepository
    engine: BacktestEngine
    strategy_engine: StrategyEngine
    service: StrategyBacktestService
    optimizer: StrategyOptimizer = None  # type: ignore[assignment]
    n_backtests: int = 0


def build_runtime() -> Runtime:
    data_dir = Path(settings.data_dir)
    load_into_registry(data_dir)
    ensure_synced(data_dir)
    repo = KlineRepository(DataStore(data_dir))
    strategy_engine = StrategyEngine(
        strategy_dirs=[data_dir / "strategies"],
        override_loader=lambda sid: strategy_config.load_override(data_dir, sid),
    )
    engine = BacktestEngine(repo)
    service = StrategyBacktestService(engine, strategy_engine)
    return Runtime(
        data_dir=data_dir,
        repo=repo,
        engine=engine,
        strategy_engine=strategy_engine,
        service=service,
        optimizer=StrategyOptimizer(service, strategy_engine),
    )


# --------------------------------------------------------------------------- #
# 切片: 一次装载, 多策略共享
# --------------------------------------------------------------------------- #
@dataclass
class Slice:
    symbols: list[str] | None
    start: date
    end: date
    asset_type: str
    trading_days: list[date]
    folds: list[Fold]
    market: Any
    plan: ResolvedFeaturePlan
    profile: Any
    generation_before: str | None
    generation_after: str | None
    bound_generation: str | None
    load_metrics: dict[str, Any] = field(default_factory=dict)
    group_plans: dict[str, ResolvedFeaturePlan] = field(default_factory=dict)
    prepare_count: int = 0

    def as_dict(self, folds: list[Fold] | None = None) -> dict[str, Any]:
        folds = self.folds if folds is None else folds
        return {
            "symbols": "all" if self.symbols is None else f"{len(self.symbols)} explicit",
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "asset_type": self.asset_type,
            "trading_days": len(self.trading_days),
            "n_folds": len(folds),
            "folds": [
                {
                    "index": f.index,
                    "train_start": f.train_start.isoformat(),
                    "train_end": f.train_end.isoformat(),
                    "test_start": f.test_start.isoformat(),
                    "test_end": f.test_end.isoformat(),
                }
                for f in folds
            ],
        }


def _effective_common_filter(strategy: Any) -> dict[str, Any]:
    """与 build_matrix_cache_profile 一致的中性基础过滤 (只用于列依赖解析)。"""
    return {
        **dict(getattr(strategy, "basic_filter", None) or {}),
        "enabled": True,
        "amount_min": 0.0,
        "turnover_min": 0.0,
        "market_cap_min": 0.0,
        "float_cap_min": 0.0,
        "exclude_st": True,
    }


def resolve_group_plan(
    rt: Runtime,
    strategy: Any,
    params: dict[str, Any],
    asset_type: str,
) -> ResolvedFeaturePlan:
    """解析某策略某参数组真正需要的字段 (与生产 prepare 同一解析器)。"""
    resolver = StrategyDependencyResolver()
    merged = StrategyEngine.resolve_params(strategy)
    merged.update(params or {})
    return resolver.resolve(
        strategy,
        params=merged,
        basic_filter=_effective_common_filter(strategy),
        entry_signals=strategy.entry_signals,
        exit_signals=strategy.exit_signals,
        overrides={},
        minute_fill=False,
        asset_type=asset_type,
    )


def prepare_slice(
    rt: Runtime,
    *,
    groups: list[dict[str, Any]],
    symbols: list[str] | None,
    start: date,
    end: date,
    asset_type: str,
    train_days: int,
    test_days: int,
    step_days: int,
    matrix_cache_max_mb: int = 512,
) -> Slice:
    t_all = time.perf_counter()
    trading_days = rt.repo.list_enriched_dates(start, end, asset_type=asset_type)
    if not trading_days:
        raise ValueError(f"{start}..{end} 没有可用的 enriched 交易日")
    folds = generate_folds(
        start, end, train_days, test_days, step_days, trading_days=trading_days
    )
    if not folds:
        raise ValueError("交易日区间切不出任何 fold")

    # 1) 注册表级并集字段画像 (生产同一个函数: prewarm/prepare 都用它定缓存世代)
    profile = build_matrix_cache_profile(
        rt.strategy_engine,
        asset_type,
        max_disk_bytes=matrix_cache_max_mb * 1024 * 1024,
    )
    profile_fields = set(profile.field_columns)

    # 2) 每个组真正需要的字段 (fail-closed: 必须被画像覆盖)
    group_plans: dict[str, ResolvedFeaturePlan] = {}
    needed: set[str] = set(BASE_COLUMNS)
    need_st = False
    warmup_bars = 0
    for group in groups:
        strategy = rt.strategy_engine.get(group["strategy_id"])
        plan = resolve_group_plan(rt, strategy, group.get("base_params") or {}, asset_type)
        group_plans[group["name"]] = plan
        needed |= set(plan.base_columns) | set(plan.matrix_columns) | set(plan.instrument_columns)
        need_st = need_st or bool(plan.historical_st)
        warmup_bars = max(warmup_bars, int(plan.warmup_bars))
    missing = needed - (profile_fields | BASE_COLUMNS)
    if missing:
        raise ValueError(
            "共享矩阵字段画像未覆盖以下必需列, 拒绝装载 (fail-closed): "
            f"{sorted(missing)}"
        )

    plan = ResolvedFeaturePlan(
        base_columns=BASE_COLUMNS & needed,
        intermediate_columns=frozenset(),
        indicator_columns=frozenset(),
        signal_columns=frozenset(),
        matrix_columns=frozenset(needed),
        instrument_columns=frozenset(),
        # 预热宽度只取「各组依赖计划的最大值」, 不掺入注册表级字段画像的
        # profile.warmup_bars: 后者是为了让缓存世代覆盖全策略字段而算的 513 根,
        # 拿来定装载起点会让共享矩阵多出两年历史。实测那会让最早一折的
        # IS 分数与单跑差 0.01 (特征在区间头部吃到额外历史), 比对不归零。
        warmup_bars=max(warmup_bars, 1),
        full_feature_fallback=False,
        execution_backend="matrix_native",
        historical_st=need_st,
    )
    warmup_days = max(120, int(plan.warmup_bars * 1.6))
    coverage_start = start - timedelta(days=warmup_days)

    generation_before = rt.engine.data_generation(asset_type)
    load_started = time.perf_counter()
    market = rt.engine.load_market_data_matrix_for_backtest(
        symbols,
        # 装载起点必须是“带预热的历史起点”, 不是正式区间起点: 生产
        # prepare_matrix_optimization 传的是 load_start = start - warmup。
        # 传正式起点会让每折的矩阵视图从区间首日开始, 首日无历史可回溯,
        # fold0 的 IS 会少 1 笔成交、分数差 0.01（已用 probe_is0.py 实测）。
        coverage_start,
        end,
        plan,
        asset_type=asset_type,
        cache_profile=profile,
        coverage_start=coverage_start,
        coverage_end=end,
    )
    load_elapsed = time.perf_counter() - load_started
    generation_after = rt.engine.data_generation(asset_type)
    bound_generation = (
        generation_before if generation_before and generation_before == generation_after else None
    )
    if bound_generation is None:
        raise ValueError(
            "装载窗口内 enriched generation 不一致, 结果无法绑定数据版本; "
            f"before={generation_before!r} after={generation_after!r} "
            "(数据正在发布时重跑)"
        )
    metrics = {
        "matrix_load_count": 1,
        "matrix_load_elapsed_s": round(load_elapsed, 3),
        "matrix_bytes_mb": round(market.nbytes / 1024 / 1024, 1),
        "matrix_shape": [len(market.timestamp_labels), len(market.symbols)],
        "matrix_window": [
            market.timestamp_labels[0] if len(market.timestamp_labels) else None,
            market.timestamp_labels[-1] if len(market.timestamp_labels) else None,
        ],
        "matrix_cache_status": market.cache_status,
        "matrix_cache_path": str(market.cache_path) if market.cache_path else None,
        "profile_generation": profile.generation,
        "profile_warmup_bars": profile.warmup_bars,
        "profile_forward_bars": profile.forward_bars,
        "field_columns": sorted(plan.matrix_columns),
        "prepare_total_s": round(time.perf_counter() - t_all, 3),
    }
    return Slice(
        symbols=symbols,
        start=start,
        end=end,
        asset_type=asset_type,
        trading_days=trading_days,
        folds=folds,
        market=market,
        plan=plan,
        profile=profile,
        generation_before=generation_before,
        generation_after=generation_after,
        bound_generation=bound_generation,
        load_metrics=metrics,
        group_plans=group_plans,
    )


# --------------------------------------------------------------------------- #
# 连续账户 (逐字段对齐 WalkForwardService._run_continuous_oos 的账户口径)
# --------------------------------------------------------------------------- #
def continuous_account_report(
    *,
    curves: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    initial_capital: float,
    trading_days: list[date],
    n_folds_total: int,
    replayed_folds: list[int],
    duplicate_dates: int,
    stopped_early: str | None,
    boundaries: list[dict[str, Any]],
    fold_records: list[dict[str, Any]],
    planned_span: tuple[str, str] | None,
) -> dict[str, Any]:
    """连续账户报告: 逐字段对齐 ``WalkForwardService._run_continuous_oos``。

    为什么不自己发明一套字段: 批量底座唯一的验收标准是「与生产单跑逐字段
    差异为 0」, 只要键名/口径/不变式任一处自创, 比对就会永久带噪。这里把
    生产那一段的 stats 增补 (execution 累加、return_kind)、9 条不变式、
    replay_span、trade_lifecycle 原样复刻, 差异才可归零。
    """
    values = [float(point["value"]) for point in curves]
    exposures = [float(point.get("exposure") or 0.0) for point in curves]
    trade_records: list[TradeRecord] = []
    for trade in trades:
        try:
            trade_records.append(TradeRecord(**trade))
        except TypeError:
            # 结构不匹配宁可少算一笔, 也不伪造
            continue
    stats = (
        BacktestEngine._calc_portfolio_stats_from_values(
            values, exposures, trade_records, initial_capital
        )
        if values
        else {}
    )

    # 段级 execution 累加 (生产同款)
    execution_totals: dict[str, int] = {}
    for record in fold_records:
        for key, value in (record["oos_stats"].get("execution") or {}).items():
            execution_totals[key] = int(execution_totals.get(key, 0)) + int(value or 0)
    stats["execution"] = execution_totals
    return_kind = (
        "partial_single_account_single_timeline"
        if stopped_early is not None
        else "single_account_single_timeline"
    )
    stats["return_kind"] = return_kind

    last_point = curves[-1] if curves else {}
    final_equity = float(last_point.get("value") or initial_capital)
    final_cash = round(float(last_point.get("cash") or 0.0), 2)
    final_positions = int(last_point.get("positions") or 0)
    final_market_value = round(final_equity - final_cash, 2)

    curve_days = [str(point.get("date")) for point in curves]
    seen = set(curve_days)
    missing_curve_dates: list[str] = []
    if curve_days and trading_days:
        first_day, last_day = curve_days[0], curve_days[-1]
        missing_curve_dates = [
            day.isoformat()
            for day in trading_days
            if first_day <= day.isoformat() <= last_day and day.isoformat() not in seen
        ]

    trade_keys = [
        (
            str(trade.get("symbol")),
            str(trade.get("entry_date")),
            str(trade.get("exit_date")),
            round(float(trade.get("entry_value") or 0.0), 2),
        )
        for trade in trades
    ]
    duplicate_trades = len(trade_keys) - len(set(trade_keys))

    open_at_end_by_fold = [
        {
            "index": record["index"],
            "n_trades": int(record["oos_stats"].get("n_trades") or 0),
            "open_at_end": int(record["oos_stats"].get("open_at_end_count") or 0),
            "open_positions_at_end": int(record.get("open_positions_at_end") or 0),
        }
        for record in fold_records
    ]
    open_at_end_total = sum(item["open_at_end"] for item in open_at_end_by_fold)

    head_gap = replayed_folds[0] if replayed_folds else None
    tail_gap = (n_folds_total - 1) - replayed_folds[-1] if replayed_folds else None
    if stopped_early is None and head_gap not in (None, 0):
        stopped_early = f"账户时间线从第 {head_gap} 折开始, 更早的交易日不计入账户。"
    if stopped_early is None and tail_gap not in (None, 0):
        stopped_early = f"账户时间线在第 {replayed_folds[-1]} 折结束, 其后 {tail_gap} 折未回放。"

    invariants = {
        "equity_equals_cash_plus_market_value": (
            abs(final_cash + final_market_value - final_equity) < 0.01
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
        # 只有这一项为 True, 上面的账户代数自洽才能当作连续账户证据
        "timeline_complete": (
            not missing_curve_dates and stopped_early is None
        ),
        "return_kind_matches_timeline": (
            (return_kind == "single_account_single_timeline")
            == (stopped_early is None)
        ),
    }

    if planned_span is not None:
        planned_start, planned_end = planned_span
    else:
        planned_start = boundaries[0]["test_start"] if boundaries else None
        planned_end = boundaries[-1]["test_end"] if boundaries else None
    replay_start = curve_days[0] if curve_days else None
    replay_end = curve_days[-1] if curve_days else None
    replay_span = {
        "start": replay_start,
        "end": replay_end,
        "n_trading_days": len(curves),
        "planned_start": planned_start,
        "planned_end": planned_end,
        "covers_planned_span": bool(
            curves and replay_start == planned_start and replay_end == planned_end
        ),
    }

    return {
        "enabled": True,
        "return_kind": return_kind,
        "replay_span": replay_span,
        "initial_capital": round(initial_capital, 2),
        "final_equity": round(final_equity, 2),
        "final_cash": final_cash,
        "final_positions": final_positions,
        "final_market_value": final_market_value,
        "n_folds_replayed": len(replayed_folds),
        "n_folds_total": n_folds_total,
        # 只数折与折之间的结转; 末折期末持仓由 final_positions 表示
        "n_boundaries_with_positions": sum(
            1 for item in boundaries[:-1] if item["carried_out_positions"] > 0
        ),
        "duplicate_dates": duplicate_dates,
        "stopped_early": stopped_early,
        "timeline": {
            "complete": not missing_curve_dates and stopped_early is None,
            "n_missing_dates": len(missing_curve_dates),
            "missing_dates": missing_curve_dates[:20],
            "trading_day_gap": None,
        },
        "trade_lifecycle": {
            "n_trades": int(stats.get("n_trades") or 0),
            "completed_trade_count": int(stats.get("completed_trade_count") or 0),
            "open_at_end_count": int(stats.get("open_at_end_count") or 0),
            "unique_trade_records": len(set(trade_keys)),
            "duplicate_trade_records": duplicate_trades,
        },
        "open_at_end_by_fold": open_at_end_by_fold,
        # 口径自述: 与生产原文一致, 便于人工对照单跑报告
        "carry_policy": (
            "折边界仅切换策略参数与信号; 现金、持仓、峰值和待执行开盘计划"
            "延续到下一折。已持仓继续按新折的风险/持有规则管理。"
        ),
        "invariants": invariants,
        "stats": stats,
        "boundaries": boundaries,
        "n_curve_points": len(curves),
        "equity_curve_sha256": hashlib.sha256(
            json.dumps(curves, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        "trades_sha256": hashlib.sha256(
            json.dumps(trades, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
    }


# --------------------------------------------------------------------------- #
# 单组执行
# --------------------------------------------------------------------------- #
def run_group(
    rt: Runtime,
    sl: Slice,
    group: dict[str, Any],
    *,
    objective: str,
    initial_capital: float,
    matrix_cache_max_mb: int,
    trim_oos: bool,
    keep_raw: bool,
    min_trades_oos: int = 10,
) -> dict[str, Any]:
    started = time.perf_counter()
    sampler = PeakRssSampler()
    sampler.start()
    run_id = uuid.uuid4().hex[:12]
    strategy_id = group["strategy_id"]
    strategy = rt.strategy_engine.get(strategy_id)
    if strategy.execution_backend != "matrix_native":
        raise ValueError(
            f"{strategy_id} 是 {strategy.execution_backend}, 本底座只承载 matrix_native 共享矩阵路径"
        )
    combos = expand_param_grid(strategy.meta.get("params", []), group.get("param_grid") or {})
    if len(combos) != 1:
        raise ValueError(
            f"组 {group['name']} 展开出 {len(combos)} 个参数组合; 本底座每组只跑 1 个参数组"
        )
    params = {**(group.get("base_params") or {}), **combos[0]}

    # IS 契约必须与生产优化器逐字段一致: optimizer.py 用
    # ``BacktestResultPolicy.optimizer_trial(objective)`` 跑每个 trial,
    # 自带 required_stats={objective, n_trades} 且只在 mc_maxdd_* 目标下开 MC。
    # 手搓一份近似政策会让 oos_folds[*].is_score 与单跑差 0.01~0.4, 比对不归零。
    # 因此 IS 一律交给生产 optimize(); evidence 里的 IS 契约由 optimizer_trial 现取,
    # 不在这里另存对象 (存了也会与生产实际调用脱节)。
    if trim_oos:
        # 显式自报代价: 曲线上限被裁, 连续账户不可重建 (报告里写明)
        oos_policy = BacktestResultPolicy(
            required_stats=None,
            include_monte_carlo=True,
            include_curves=False,
            include_trades=False,
            include_per_symbol_stats=False,
            include_return_distribution=False,
            include_benchmark=False,
            include_strategy_info=False,
        )
    else:
        # OOS 用生产 _run_oos_fold 的默认 (全量) 契约: 逐笔与曲线是连续账户
        # 回放的原料, 段级统计口径也必须一致, 否则比对不归零。裁剪发生在
        # 「组结束后释放原始列表」这一步 (keep_raw=False), 那才是内存峰值点。
        oos_policy = BacktestResultPolicy()

    def _cfg(**overrides: Any) -> StrategyBacktestConfig:
        base: dict[str, Any] = {
            "strategy_id": strategy_id,
            "symbols": sl.symbols,
            "start": sl.start,
            "end": sl.end,
            "params": params,
            "mode": "position",
            "initial_capital": initial_capital,
            "asset_type": sl.asset_type,
        }
        base.update(overrides)
        return StrategyBacktestConfig(**base)

    n_backtests_local = 0
    is_runs: list[dict[str, Any]] = []
    is_started = time.perf_counter()
    for fold in sl.folds:
        # IS 直接调生产优化器, 而不是自己 service.run 一遍:
        # optimize() 内部就是 prepare(override=共享矩阵)->trials(optimizer_trial
        # 契约)->按目标排序->best_score=round(best_raw,4)。自己重写这一段,
        # is_score 会在末位小数上与单跑不一致 (实测 1.32 vs 1.33),
        # 而"逐字段差异为 0"是底座的验收条件, 不是可选优化。
        opt_cfg = OptimizeConfig(
            strategy_id=strategy_id,
            symbols=sl.symbols,
            start=fold.train_start,
            end=fold.train_end,
            param_grid=group.get("param_grid") or {},
            objective=objective,
            direction=default_direction(objective),
            max_workers=1,
            base_params=group.get("base_params") or {},
            overrides=None,
            backtest_kwargs={
                "mode": "position",
                "initial_capital": initial_capital,
                "asset_type": sl.asset_type,
            },
            matrix_cache_max_mb=matrix_cache_max_mb,
        )
        opt_res = rt.optimizer.optimize(opt_cfg, prepared_market_data=sl.market)
        # 一次 optimize = 1 次共享 prepare (网格整组复用) + n_combinations 次 trial
        sl.prepare_count += 1
        n_combos = int(opt_res.get("n_combinations") or 1)
        rt.n_backtests += n_combos
        n_backtests_local += n_combos
        best_params = opt_res.get("best_params")
        best_backtest = opt_res.get("best_backtest") or {}
        is_runs.append(
            {
                "index": fold.index,
                "train_start": fold.train_start.isoformat(),
                "train_end": fold.train_end.isoformat(),
                "test_start": fold.test_start.isoformat(),
                "test_end": fold.test_end.isoformat(),
                "is_score": opt_res.get("best_score"),
                "is_n_trades": (best_backtest.get("stats") or {}).get("n_trades"),
                "is_params": best_params,
                "n_combinations": n_combos,
                "n_completed": int(opt_res.get("n_completed") or 0),
                "error": None if best_params is not None else "训练区间未优化出参数",
            }
        )
    is_elapsed = time.perf_counter() - is_started

    optimized = [
        {"fold": f, "record": r}
        for f, r in zip(sl.folds, is_runs, strict=True)
        if r["error"] is None and r["is_score"] is not None
    ]

    oos_started = time.perf_counter()
    curves: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    duplicate_dates = 0
    boundaries: list[dict[str, Any]] = []
    fold_records: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    stopped_early: str | None = None
    carry = None
    prev_equity = float(initial_capital)
    replayed: list[int] = []

    for position, item in enumerate(optimized):
        fold: Fold = item["fold"]
        is_last = position == len(optimized) - 1
        cfg = _cfg(
            start=fold.test_start,
            end=fold.test_end,
            carry_state=carry,
            carry_out=not is_last,
        )
        prepared = rt.service.prepare_matrix_optimization(
            [cfg],
            matrix_cache_max_bytes=matrix_cache_max_mb * 1024 * 1024,
            market_data_override=sl.market,
        )
        sl.prepare_count += 1
        try:
            res = rt.service.run(cfg, prepared=prepared, result_policy=oos_policy)
        finally:
            prepared.compute_cache.close()
        rt.n_backtests += 1
        n_backtests_local += 1
        if res.error:
            skipped.append(
                {
                    "index": fold.index,
                    "test_start": fold.test_start.isoformat(),
                    "test_end": fold.test_end.isoformat(),
                    "reason": f"OOS 回测失败: {res.error}",
                }
            )
            stopped_early = f"OOS 第 {fold.index} 折失败: {res.error}"
            break

        final_equity = float(res.stats.get("final_equity") or prev_equity)
        report_final = res.stats.get("final_equity")
        if report_final is not None:
            segment_return = final_equity / prev_equity - 1.0 if prev_equity > 0 else 0.0
        else:
            segment_return = float(res.stats.get("total_return") or 0.0)
            final_equity = prev_equity * (1.0 + segment_return)

        for point in res.equity_curve or []:
            day = str(point.get("date"))
            if day in seen_dates:
                duplicate_dates += 1
                continue
            seen_dates.add(day)
            curves.append(point)
        trades.extend(res.trades or [])

        # 生产 _run_continuous_oos 会把段收益回写到 oos_stats (aggregate_oos 就是
        # 读这两个字段拼汇总曲线/复利): 不写回去, summary.oos_equity_curve 与
        # degradation 就会与单跑差一截。
        res.stats["total_return"] = round(segment_return, 4)
        res.stats["account_total_return_cumulative"] = round(
            final_equity / initial_capital - 1.0, 4
        )

        # 期末持仓三级回退, 与 _run_continuous_oos 同口径:
        # carry_state.positions -> 曲线末点 positions -> stats.open_at_end_count。
        # 只用 stats 会让非末折恒为 0 (stats 里的 open_at_end_count 是"本段新开
        # 未平"的计数, 不含跨折结转), 单跑对照会差 4/7 笔。
        res_carry = getattr(res, "carry_state", None)
        res_curve = res.equity_curve or []
        if res_carry is not None:
            carried_out = len(getattr(res_carry, "positions", []) or [])
        elif res_curve:
            carried_out = int(res_curve[-1].get("positions") or 0)
        else:
            carried_out = int(res.stats.get("open_at_end_count") or 0)
        boundaries.append(
            {
                "index": fold.index,
                "test_start": fold.test_start.isoformat(),
                "test_end": fold.test_end.isoformat(),
                "equity_start": round(prev_equity, 2),
                "equity_end": round(final_equity, 2),
                "segment_return": round(segment_return, 4),
                "carried_in_positions": len(getattr(carry, "positions", []) or []),
                "carried_out_positions": carried_out,
                # 生产 boundaries 里没有 open_positions_at_end, 换 pending_buy_plans
                # (折末待执行开盘计划数), 否则 summary 里的 boundaries 会多出一个
                # 单跑没有的键, 比对永远是 missing_key。
                "pending_buy_plans": (
                    len(getattr(carry, "pending_buy_plans", []) or [])
                    if carry is not None
                    else 0
                ),
                "params_changed": bool(
                    position > 0 and fold_records[-1]["best_params"] != params
                ),
            }
        )
        fold_records.append(
            {
                "index": fold.index,
                "train_start": fold.train_start.isoformat(),
                "train_end": fold.train_end.isoformat(),
                "test_start": fold.test_start.isoformat(),
                "test_end": fold.test_end.isoformat(),
                "best_params": params,
                "is_score": item["record"]["is_score"],
                "oos_objective": res.stats.get(objective),
                "trade_gate_ok": trades_ok(res.stats, min_trades_oos),
                "statistically_insufficient": not trades_ok(res.stats, min_trades_oos),
                "min_trades_oos": min_trades_oos,
                "oos_stats": res.stats,
                "segment_return": round(segment_return, 4),
                "account_equity_start": round(prev_equity, 2),
                "account_equity_end": round(final_equity, 2),
                "carried_in_positions": len(getattr(carry, "positions", []) or []),
                "carried_out_positions": carried_out,
                "open_positions_at_end": carried_out,
                "continuous": True,
                "elapsed_ms": round(res.elapsed_ms, 1),
            }
        )
        replayed.append(fold.index)
        carry = getattr(res, "carry_state", None)
        prev_equity = final_equity
    oos_elapsed = time.perf_counter() - oos_started

    continuous = (
        continuous_account_report(
            curves=curves,
            trades=trades,
            initial_capital=initial_capital,
            trading_days=sl.trading_days,
            n_folds_total=len(sl.folds),
            replayed_folds=replayed,
            duplicate_dates=duplicate_dates,
            stopped_early=stopped_early,
            boundaries=boundaries,
            fold_records=fold_records,
            planned_span=(
                (sl.folds[0].test_start.isoformat(), sl.folds[-1].test_end.isoformat())
                if sl.folds
                else None
            ),
        )
        if not trim_oos and curves
        else {
            "enabled": False,
            "reason": "--trim-oos 裁掉了曲线与逐笔, 无法重建连续账户时间线",
        }
    )
    summary = aggregate_oos(fold_records, objective) if fold_records else {}
    if continuous.get("enabled"):
        # 与生产 run() 同一套汇总口径切换: 连续账户成立时它才是"账户收益",
        # 逐折复利值降级为诊断值并显式标注。
        summary["continuous_account"] = continuous
        summary["return_kind"] = continuous.get(
            "return_kind", "single_account_single_timeline"
        )
        summary["continuous_replay_span"] = continuous.get("replay_span")
        summary["compounded_oos_return_is_diagnostic"] = True
        if continuous.get("stopped_early"):
            summary["continuous_stopped_early"] = continuous["stopped_early"]

    peak_mb = sampler.stop()
    elapsed = time.perf_counter() - started
    if not keep_raw:
        # 曲线/逐笔只用于账户聚合与哈希, 落盘前释放, 避免 N 组累积
        n_curve_points = len(curves)
        n_trade_records = len(trades)
        curves.clear()
        trades.clear()
    else:
        n_curve_points = len(curves)
        n_trade_records = len(trades)

    return {
        "run_id": run_id,
        "group": group["name"],
        "strategy_id": strategy_id,
        "params": params,
        "param_grid": group.get("param_grid"),
        "base_params": group.get("base_params") or {},
        # 实际使用的两份结果裁剪契约 (真实对象现取 repr, 不写手搓描述串)
        "result_policy": {
            "is": repr(BacktestResultPolicy.optimizer_trial(objective)),
            "oos": repr(oos_policy),
        },
        "status": "ok" if fold_records and not stopped_early else ("partial" if fold_records else "failed"),
        "data_generation": sl.bound_generation,
        "code_sha256": code_fp["sha256"],
        "elapsed_s": round(elapsed, 2),
        "peak_rss_mb": peak_mb,
        "n_trials": n_backtests_local,
        "n_trials_cumulative": rt.n_backtests,
        "timing": {
            "is_s": round(is_elapsed, 2),
            "oos_s": round(oos_elapsed, 2),
            "n_prepare_calls": sl.prepare_count,
        },
        "folds": [
            {k: r[k] for k in ("index", "train_start", "train_end", "test_start", "test_end")}
            for r in fold_records
        ],
        "is_runs": is_runs,
        "oos_folds": fold_records,
        "oos_summary": summary,
        "continuous_account": continuous,
        "skipped": skipped,
        "raw": (
            {"curves": curves, "trades": trades}
            if keep_raw
            else {"n_curve_points": n_curve_points, "n_trade_records": n_trade_records}
        ),
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def load_groups(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    groups = payload["groups"] if isinstance(payload, dict) else payload
    if not groups:
        raise ValueError("groups 清单为空")
    names = set()
    for group in groups:
        for key in ("name", "strategy_id", "param_grid"):
            if key not in group:
                raise ValueError(f"组定义缺字段 {key}: {group}")
        if group["name"] in names:
            raise ValueError(f"组名重复: {group['name']}")
        names.add(group["name"])
    return groups


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="批量回测最小底座 (单进程, IS/OOS + registry)")
    parser.add_argument("--groups", required=True, type=Path)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--train-days", type=int, default=252)
    parser.add_argument("--test-days", type=int, default=63)
    parser.add_argument("--step-days", type=int, default=None, help="默认等于 --test-days")
    parser.add_argument("--objective", default="sortino")
    parser.add_argument("--asset-type", default="stock")
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0)
    parser.add_argument("--matrix-cache-max-mb", type=int, default=512)
    parser.add_argument("--symbols", type=Path, default=None, help="每行一个 symbol; 缺省=全市场")
    parser.add_argument("--max-symbols", type=int, default=0, help="调试用: 只取前 N 个 symbol")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--trim-oos", action="store_true", help="OOS 也裁掉曲线/逐笔 (连续账户不可用)")
    parser.add_argument("--min-trades-oos", type=int, default=10, help="OOS 每折最小交易数门槛 (与 WFO 默认一致)")
    parser.add_argument("--keep-raw", action="store_true", help="registry 保留 OOS 曲线与逐笔原始列表")
    args = parser.parse_args(argv)

    step_days = args.step_days if args.step_days is not None else args.test_days
    if step_days != args.test_days:
        parser.error("连续账户要求 step_days == test_days (逐日衔接), 否则时间线有缺口")

    groups = load_groups(args.groups)
    symbols = None
    if args.symbols is not None:
        symbols = [
            line.strip()
            for line in args.symbols.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if args.max_symbols:
            symbols = symbols[: args.max_symbols]
    elif args.max_symbols:
        symbols = None  # 全市场时截断没有确定语义, 明确忽略

    out_dir: Path = args.out
    (out_dir / "runs").mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence").mkdir(parents=True, exist_ok=True)

    global code_fp
    code_fp = code_fingerprint()
    batch_started = time.perf_counter()
    overall = PeakRssSampler()
    overall.start()

    rt = build_runtime()
    slice_ctx = prepare_slice(
        rt,
        groups=groups,
        symbols=symbols,
        start=args.start,
        end=args.end,
        asset_type=args.asset_type,
        train_days=args.train_days,
        test_days=args.test_days,
        step_days=step_days,
        matrix_cache_max_mb=args.matrix_cache_max_mb,
    )
    batch_id = uuid.uuid4().hex[:12]
    registry: dict[str, Any] = {
        "schema": "batch-backtest-registry/1",
        "batch_id": batch_id,
        "created_at": now_iso(),
        "command": " ".join([Path(sys.executable).name, *sys.argv]),
        "code": code_fp,
        "slice": slice_ctx.as_dict(),
        "slice_load": slice_ctx.load_metrics,
        "data_generation": {
            "before": slice_ctx.generation_before,
            "after": slice_ctx.generation_after,
            "bound": slice_ctx.bound_generation,
        },
        "settings": {
            "objective": args.objective,
            "initial_capital": args.initial_capital,
            "asset_type": args.asset_type,
            "matrix_cache_max_mb": args.matrix_cache_max_mb,
            "train_days": args.train_days,
            "test_days": args.test_days,
            "step_days": step_days,
            "min_trades_oos": args.min_trades_oos,
            "trim_oos": args.trim_oos,
            "keep_raw": args.keep_raw,
        },
        "runs": [],
    }
    try:
        for group in groups:
            entry = run_group(
                rt,
                slice_ctx,
                group,
                objective=args.objective,
                initial_capital=args.initial_capital,
                matrix_cache_max_mb=args.matrix_cache_max_mb,
                trim_oos=args.trim_oos,
                keep_raw=args.keep_raw,
                min_trades_oos=args.min_trades_oos,
            )
            registry["runs"].append(entry)
            evidence = {
                "schema": "batch-backtest-evidence/1",
                "batch_id": batch_id,
                "run_id": entry["run_id"],
                "group": entry["group"],
                "strategy_id": entry["strategy_id"],
                "params": entry["params"],
                "code": code_fp,
                "data_generation": registry["data_generation"],
                "slice": slice_ctx.as_dict(),
                "matrix": slice_ctx.load_metrics,
                "policy": entry["result_policy"],
                "folds": entry["folds"],
                "is_runs": entry["is_runs"],
                "oos_summary": entry["oos_summary"],
                "continuous_account": entry["continuous_account"],
                "skipped": entry["skipped"],
                "timing": entry["timing"],
                "peak_rss_mb": entry["peak_rss_mb"],
                "n_trials": entry["n_trials"],
                "n_trials_cumulative": entry["n_trials_cumulative"],
            }
            (out_dir / "evidence" / f"{entry['run_id']}.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            (out_dir / "runs" / f"{entry['run_id']}.json").write_text(
                json.dumps(entry, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            (out_dir / "registry.json").write_text(
                json.dumps(registry, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            ca = entry["continuous_account"]
            print(
                json.dumps(
                    {
                        "group": entry["group"],
                        "run_id": entry["run_id"],
                        "status": entry["status"],
                        "n_trades_oos": ca.get("trade_lifecycle", {}).get("n_trades"),
                        "oos_objective_mean": entry["oos_summary"].get("avg_oos_objective"),
                        "compounded_oos_return": entry["oos_summary"].get("compounded_oos_return"),
                        "degradation": entry["oos_summary"].get("degradation"),
                        "duplicate_dates": ca.get("duplicate_dates"),
                        "timeline_complete": ca.get("invariants", {}).get("timeline_complete"),
                        "peak_rss_mb": entry["peak_rss_mb"],
                        "elapsed_s": entry["elapsed_s"],
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                flush=True,
            )
    finally:
        peak = overall.stop()
        registry["totals"] = {
            "n_groups": len(registry["runs"]),
            "n_trials": rt.n_backtests,
            "matrix_load_count": 1,
            "matrix_prepare_calls": slice_ctx.prepare_count,
            "elapsed_s": round(time.perf_counter() - batch_started, 2),
            "peak_rss_mb": peak,
        }
        (out_dir / "registry.json").write_text(
            json.dumps(registry, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    print(json.dumps({"registry": str(out_dir / "registry.json"), "totals": registry["totals"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
