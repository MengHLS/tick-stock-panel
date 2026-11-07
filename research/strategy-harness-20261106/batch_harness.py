"""策略批量评估底座 — N 条策略 × M 个成本档，逐次试验留痕。

设计约束（对应 INTERFACE-MAP.md 的 5 个最小改动点）：
1. 每次试验强制传 BacktestResultPolicy，裁掉净值曲线/逐笔/分股统计/分布/基准，
   只留组合账户口径指标与诊断字段。
2. 同一数据切片共享一次行情装载：成本档不进 `_matrix_prepare_signature`，
   因此一个 (策略, 窗口) 只 prepare 一次，M 个成本档共用同一份 prepared 对象；
   批次开始前用 build_matrix_cache_profile + prewarm_matrix_cache 预热锁矩阵。
   跨策略共享同一 prepared 对象做不到（signature 含 strategy_id，run 里 fail-closed），
   需生产代码改动，见 README 的「需要生产改动的部分」。
3. 折边界只来自 list_enriched_dates + generate_folds(trading_days=...)，并断言
   每个折边界都落在真实交易日上；不自造日历。
4. 指标只取组合账户口径（引擎 _calc_portfolio_stats_from_values 产出的 stats）；
   多重检验用 stats_v2.deflated_sharpe_psr + expected_max_sharpe，n_trials 进入校正，
   跨试验再做 BH-FDR q 值。
5. 每个 trial 绑定 data_generation 与 prepared 数据指纹（面板哈希/矩阵内容摘要），
   整批落 registry + evidence 清单，任一数字可反查。

用法：
    backend/.venv/Scripts/python.exe research/strategy-harness-20261106/batch_harness.py \
        --spec research/strategy-harness-20261106/specs/demo-2x2.json

退出码：0 全部试验成功且数据世代稳定；2 部分试验失败或数据世代漂移；1 致命错误。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import numpy as np
import psutil
from app.backtest.engine import BacktestEngine
from app.backtest.stats_v2 import (
    bh_fdr_qvalues,
    deflated_sharpe_psr,
    expected_max_sharpe,
)
from app.backtest.strategy import (
    BacktestResultPolicy,
    PreparedMatrixBacktest,
    PreparedPanelBacktest,
    StrategyBacktestConfig,
    StrategyBacktestService,
    build_matrix_cache_profile,
    prewarm_matrix_cache,
)
from app.backtest.walkforward import generate_folds
from app.config import settings
from app.strategy.engine import StrategyEngine
from app.tickflow.repository import DataStore, KlineRepository, enriched_dirname

EULER_GAMMA = 0.5772156649015329

# 组合账户口径里参与跨策略比较的字段（引擎 _calc_portfolio_stats_from_values）。
COMPARABLE_STATS = (
    "total_return",
    "annual_return",
    "max_drawdown",
    "sharpe",
    "sortino",
    "calmar",
    "win_rate",
    "profit_factor",
    "n_trades",
    "completed_trade_count",
    "avg_pnl",
    "avg_win",
    "avg_loss",
    "final_equity",
    "avg_exposure",
    "max_exposure",
)

# 裁剪后的结果契约：无曲线、无逐笔、无分股、无分布、无基准（内存 O(1) per trial）。
LIGHT_POLICY = BacktestResultPolicy(
    required_stats=None,  # None = 保留引擎产出的全部标量指标（不是 None 就没有曲线）
    include_monte_carlo=False,
    include_curves=False,
    include_trades=False,
    include_per_symbol_stats=False,
    include_return_distribution=False,
    include_benchmark=False,
    include_strategy_info=False,
)


# ────────────────────────── 日志 ──────────────────────────
class RunLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")

    def __call__(self, message: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        print(line, flush=True)
        self._fh.write(line + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


# ────────────────────────── 资源采样 ──────────────────────────
class Rss:
    def __init__(self) -> None:
        self.proc = psutil.Process()
        self.start = self.peak = self.proc.memory_info().rss
        self.marks: list[dict[str, Any]] = []

    def _sample(self) -> tuple[int, int | None]:
        """返回 (当前 RSS, OS 记录的峰值工作集)。

        标记点采样会漏掉 prepare 内部的瞬时尖峰（同一批次不同进程实测可差 3 倍），
        所以峰值一律以 Windows 的 peak_wset 为准，采样值只作为轨迹参考。
        """
        info = self.proc.memory_info()
        return info.rss, getattr(info, "peak_wset", None)

    def mark(self, label: str) -> None:
        current, _ = self._sample()
        self.peak = max(self.peak, current)
        self.marks.append(
            {"label": label, "rss_mb": round(current / 1e6, 1), "t": time.time()}
        )

    def summary(self) -> dict[str, Any]:
        current, peak_wset = self._sample()
        return {
            "rss_start_mb": round(self.start / 1e6, 1),
            "rss_peak_mb": round(self.peak / 1e6, 1),
            "rss_peak_sampled_mb": round(self.peak / 1e6, 1),
            "rss_peak_wset_mb": None if peak_wset is None else round(peak_wset / 1e6, 1),
            "rss_end_mb": round(current / 1e6, 1),
            "marks": self.marks,
        }


# ────────────────────────── 规格 ──────────────────────────
@dataclass
class BatchSpec:
    name: str
    asset_type: str
    start: date
    end: date
    strategies: list[dict[str, Any]]
    cost_tiers: list[dict[str, Any]]
    base: dict[str, Any]
    walkforward: dict[str, int]
    symbols: dict[str, Any] | None
    prewarm_years: int
    windows: list[str]
    fold_used: int
    raw: dict[str, Any] = field(default_factory=dict)


def _as_date(value: Any) -> date:
    return date.fromisoformat(str(value)[:10])


def load_spec(path: Path) -> BatchSpec:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("spec 必须是 JSON 对象")
    strategies = raw.get("strategies") or []
    if not strategies:
        raise ValueError("spec.strategies 不能为空")
    tiers = raw.get("cost_tiers") or []
    if not tiers:
        raise ValueError("spec.cost_tiers 不能为空")
    for tier in tiers:
        if not tier.get("id"):
            raise ValueError("每个成本档必须有 id")
    ids = [tier["id"] for tier in tiers]
    if len(set(ids)) != len(ids):
        raise ValueError("成本档 id 必须唯一")
    wf = raw.get("walkforward") or {}
    # holdout 缺省：训练 250 交易日 / 测试 60 / 步进 60（全部按交易日计数）
    wf = {
        "train_days": int(wf.get("train_days", 250)),
        "test_days": int(wf.get("test_days", 60)),
        "step_days": int(wf.get("step_days", 60)),
    }
    if wf["step_days"] < wf["test_days"]:
        raise ValueError("walkforward.step_days 必须 >= test_days（样本外区间不能重叠）")
    windows = raw.get("windows") or ["IS", "OOS", "ALL"]
    unknown = set(windows) - {"IS", "OOS", "ALL"}
    if unknown:
        raise ValueError(f"未知窗口: {sorted(unknown)}")
    return BatchSpec(
        name=str(raw.get("name") or path.stem),
        asset_type=str(raw.get("asset_type") or "stock"),
        start=_as_date(raw["start"]),
        end=_as_date(raw["end"]),
        strategies=strategies,
        cost_tiers=tiers,
        base=raw.get("base") or {},
        walkforward=wf,
        symbols=raw.get("symbols"),
        prewarm_years=int(raw.get("prewarm_years", 0)),
        windows=windows,
        fold_used=int(raw.get("fold_used", 0)),
        raw=raw,
    )


# ────────────────────────── 数据指纹 ──────────────────────────
def _matrix_fingerprint(prepared: PreparedMatrixBacktest) -> dict[str, Any]:
    """矩阵内容摘要：形状 + 轴端点 + close 的确定性数值摘要。"""
    md = prepared.market_data
    labels = md.timestamp_labels
    close = md.close
    total = float(np.nansum(close)) if close.size else 0.0
    payload = {
        "kind": "market_matrix",
        "shape": list(close.shape),
        "first_label": labels[0][:10] if len(labels) else None,
        "last_label": labels[-1][:10] if len(labels) else None,
        "n_symbols": len(md.symbols) if getattr(md, "symbols", None) is not None else None,
        "close_nansum": round(total, 3),
        "feature_width": prepared.feature_width,
        "nbytes": int(md.nbytes),
    }
    digest = hashlib.blake2b(
        json.dumps(payload, sort_keys=True).encode(), digest_size=12
    ).hexdigest()
    return {**payload, "digest": digest}


def _panel_fingerprint(prepared: PreparedPanelBacktest) -> dict[str, Any]:
    panel = prepared.panel
    payload = {
        "kind": "feature_panel",
        "shape": [panel.height, panel.width],
        "columns": sorted(panel.columns),
    }
    try:
        hashed = int(panel.hash_rows().sum())
        payload["rows_hash"] = hashed
    except Exception:  # noqa: BLE001 — 指纹是附证，失败不阻断
        payload["rows_hash"] = None
    digest = hashlib.blake2b(
        json.dumps(payload, sort_keys=True, default=str).encode(), digest_size=12
    ).hexdigest()
    return {**payload, "digest": digest}


# ────────────────────────── 统计校验 ──────────────────────────
def psr_and_p(
    sharpe: float,
    n_obs: int,
    skewness: float,
    kurtosis: float,
    expected_max: float,
) -> tuple[float | None, float | None, float | None]:
    """返回 (z, psr, 单侧 p)。psr 与 stats_v2.deflated_sharpe_psr 对齐并就地校验。

    PSR = Φ(z), z = (SR - SR*)·sqrt(n-1)/sqrt(1 - γ3·SR + (γ4-1)/4·SR²)；
    单侧 p = Φ(-z) = 0.5·erfc(z/√2)，与 PSR 严格互补。
    """
    ref = deflated_sharpe_psr(sharpe, n_obs, skewness, kurtosis, expected_max)
    if ref is None or n_obs < 5 or not math.isfinite(sharpe):
        return None, None, None
    denominator = 1.0 - skewness * sharpe + (kurtosis - 1.0) / 4.0 * sharpe * sharpe
    if denominator <= 0:
        return None, None, None
    z = (sharpe - expected_max) * math.sqrt(n_obs - 1) / math.sqrt(denominator)
    psr = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    if abs(psr - ref) > 1e-9:  # 公式漂移即失败，不静默出数
        raise AssertionError(f"PSR 与 stats_v2 不一致: {psr} vs {ref}")
    p_one_sided = 0.5 * math.erfc(z / math.sqrt(2.0))
    return z, psr, p_one_sided


# ────────────────────────── 主流程 ──────────────────────────
class BatchHarness:
    def __init__(self, spec: BatchSpec, out_dir: Path) -> None:
        self.spec = spec
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.batch_id = f"{spec.name}-{datetime.now().strftime('%Y%m%dT%H%M%S')}"
        self.log = RunLog(out_dir / "run.log")
        self.rss = Rss()
        self.repo = KlineRepository(DataStore(settings.data_dir))
        self.engine = BacktestEngine(self.repo)
        self.sengine = StrategyEngine(strategy_dirs=[])
        self.service = StrategyBacktestService(self.engine, self.sengine)
        self.trials: list[dict[str, Any]] = []
        self.prepares: list[dict[str, Any]] = []
        self.t_start = time.perf_counter()
        self.generation_before: str | None = None
        self.generation_after: str | None = None

    # ── 环境 ──
    def _git(self, *args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30, check=False
            ).stdout.strip()
        except Exception:  # noqa: BLE001
            return ""

    def environment(self) -> dict[str, Any]:
        return {
            "git_branch": self._git("rev-parse", "--abbrev-ref", "HEAD"),
            "git_head": self._git("rev-parse", "HEAD"),
            "git_dirty_tracked": len(
                [ln for ln in self._git("status", "--short").splitlines() if ln.strip()]
            ),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": np.__version__,
            "data_dir": str(settings.data_dir),
            "cwd": str(ROOT),
        }

    # ── 交易日与折 ──
    def trading_days(self) -> list[date]:
        days = self.repo.list_enriched_dates(self.spec.start, self.spec.end, self.spec.asset_type)
        if not days:
            raise ValueError(
                f"{self.spec.start}..{self.spec.end} 内没有 enriched 分区，先跑盘后管道"
            )
        return days

    def folds(self, days: list[date]) -> list[Any]:
        wf = self.spec.walkforward
        folds = generate_folds(
            self.spec.start,
            self.spec.end,
            wf["train_days"],
            wf["test_days"],
            wf["step_days"],
            trading_days=days,
        )
        day_set = set(days)
        for fold in folds:  # 折边界必须是真实交易日，不自造日历
            for edge in (fold.train_start, fold.train_end, fold.test_start, fold.test_end):
                if edge not in day_set:
                    raise AssertionError(f"折 {fold.index} 边界 {edge} 不在交易日清单内")
        if self.spec.fold_used >= len(folds):
            raise ValueError(f"fold_used={self.spec.fold_used} 超出可用折数 {len(folds)}")
        return folds

    # ── 标的池 ──
    def universe(self, days: list[date]) -> tuple[list[str] | None, dict[str, Any]]:
        cfg = self.spec.symbols
        if not cfg:
            return None, {"mode": "all", "n": None}
        mode = str(cfg.get("mode") or "even_stride")
        n = int(cfg.get("n") or 200)
        if mode != "even_stride":
            raise ValueError(f"不支持的 symbols.mode: {mode}")
        ref = _as_date(cfg.get("reference_date") or self.spec.start)
        candidates = [d for d in days if d <= ref]
        if not candidates:
            raise ValueError(f"参考日 {ref} 之前没有可用交易日")
        ref_day = candidates[-1]
        path = settings.data_dir / enriched_dirname(self.spec.asset_type) / f"date={ref_day}" / "part.parquet"
        import polars as pl

        symbols = sorted(
            pl.read_parquet(path, columns=["symbol"]).get_column("symbol").unique().to_list()
        )
        if n >= len(symbols):
            picked = symbols
        else:
            stride = len(symbols) / n
            picked = [symbols[int(i * stride)] for i in range(n)]
        digest = hashlib.blake2b(json.dumps(picked).encode(), digest_size=8).hexdigest()
        return picked, {
            "mode": mode,
            "n": len(picked),
            "reference_date": ref_day.isoformat(),
            "universe_size": len(symbols),
            "symbols_digest": digest,
            "note": "等距抽样，仅为吞吐量演示；按参考日现存标的枚举，含存续偏差",
        }

    # ── 成本档 → config 覆盖 ──
    @staticmethod
    def cost_kwargs(tier: dict[str, Any]) -> dict[str, Any]:
        return {
            "fees_pct": float(tier.get("fees_pct", 0.0002)),
            "commission_pct": (
                None if tier.get("commission_pct") is None else float(tier["commission_pct"])
            ),
            "stamp_tax_pct": (
                None if tier.get("stamp_tax_pct") is None else float(tier["stamp_tax_pct"])
            ),
            "slippage_bps": float(tier.get("slippage_bps", 0.0)),
        }

    def build_config(
        self,
        strategy: dict[str, Any],
        window: tuple[date, date],
        tier: dict[str, Any],
        symbols: list[str] | None,
    ) -> StrategyBacktestConfig:
        base = self.spec.base
        return StrategyBacktestConfig(
            strategy_id=str(strategy["id"]),
            symbols=symbols,
            start=window[0],
            end=window[1],
            params=dict(strategy.get("params") or {}),
            overrides=dict(strategy.get("overrides") or {}),
            mode=str(base.get("mode", "position")),
            holding_days=int(base.get("holding_days", 5)),
            max_positions=int(base.get("max_positions", 5)),
            max_exposure_pct=float(base.get("max_exposure_pct", 1.0)),
            initial_capital=float(base.get("initial_capital", 1_000_000.0)),
            position_sizing=str(base.get("position_sizing", "equal")),
            entry_fill=base.get("entry_fill") or "open_t+1",
            exit_fill=base.get("exit_fill") or "open_t+1",
            asset_type=self.spec.asset_type,
            **self.cost_kwargs(tier),
        )

    # ── 单批 ──
    def run(self) -> int:  # 编排流程，分段注释已足够
        spec = self.spec
        self.log(f"批次 {self.batch_id} 开始：{spec.name}")
        self.log(
            f"区间 {spec.start}..{spec.end} 资产 {spec.asset_type} "
            f"策略 {len(spec.strategies)} × 成本档 {len(spec.cost_tiers)} = "
            f"{len(spec.strategies) * len(spec.cost_tiers)} 个决策单元"
        )
        env = self.environment()
        self.log(f"git {env['git_branch']}@{env['git_head'][:8]} 未提交改动 {env['git_dirty_tracked']} 行")

        days = self.trading_days()
        self.log(f"交易日 {len(days)} 个：{days[0]}..{days[-1]}（来源 list_enriched_dates）")
        folds = self.folds(days)
        fold = folds[spec.fold_used]
        self.log(
            f"折 {len(folds)} 个，使用 fold#{fold.index}："
            f"IS {fold.train_start}..{fold.train_end} / OOS {fold.test_start}..{fold.test_end}"
        )
        symbols, universe_meta = self.universe(days)
        self.log(f"标的池 {universe_meta['mode']} n={universe_meta['n']} ref={universe_meta.get('reference_date')}")

        windows: dict[str, tuple[date, date]] = {}
        if "IS" in spec.windows:
            windows["IS"] = (fold.train_start, fold.train_end)
        if "OOS" in spec.windows:
            windows["OOS"] = (fold.test_start, fold.test_end)
        if "ALL" in spec.windows:
            windows["ALL"] = (spec.start, spec.end)

        self.generation_before = self.engine.data_generation(spec.asset_type)
        self.log(f"data_generation(before) {self.generation_before}")
        self.rss.mark("batch_start")

        # ── 点 2：锁矩阵预热（一批一次）──
        prewarm_info: dict[str, Any] = {"enabled": spec.prewarm_years > 0}
        if spec.prewarm_years > 0:
            t0 = time.perf_counter()
            try:
                profile = build_matrix_cache_profile(
                    self.sengine,
                    spec.asset_type,
                    max_disk_bytes=settings.backtest_matrix_cache_max_mb * 1024 * 1024,
                )
                # 预热必须覆盖正式窗口 + 特征预热天数，否则 prepare 仍会冷建。
                # 预热函数按自然年对齐 (formal_start = latest_year - years + 1)，
                # 这里反推所需年份并断言覆盖，避免「预热了但没用上」被静默过关。
                warmup_days = max(120, int(max(profile.warmup_bars, 1) * 1.6))
                needed_start = min(w[0] for w in windows.values()) - timedelta(days=warmup_days)
                years_needed = max(1, days[-1].year - (needed_start + timedelta(days=warmup_days)).year + 1)
                prewarm_info["profile"] = {
                    "field_columns": sorted(profile.field_columns),
                    "warmup_bars": profile.warmup_bars,
                    "forward_bars": profile.forward_bars,
                    "generation": profile.generation,
                }
                prewarm_info["coverage"] = {
                    "needed_start": needed_start.isoformat(),
                    "warmup_days": warmup_days,
                    "years_requested": spec.prewarm_years,
                    "years_needed_for_full_coverage": years_needed,
                }
                result = prewarm_matrix_cache(
                    self.engine,
                    self.sengine,
                    asset_type=spec.asset_type,
                    latest_date=days[-1],
                    years=spec.prewarm_years,
                )
                prewarm_info.update({"ok": True, **{k: str(v) for k, v in result.items()}})
                covered = _as_date(str(result.get("start"))) <= needed_start
                prewarm_info["coverage"]["covers_needed_start"] = covered
                if not covered:
                    self.log(
                        f"[WARN] 预热起点 {result.get('start')} 晚于所需 {needed_start}，"
                        f"首批 prepare 仍会冷建；要全覆盖把 prewarm_years 提到 {years_needed}"
                    )
            except Exception as exc:  # noqa: BLE001 — 预热失败只退化为冷装载
                prewarm_info.update({"ok": False, "error": repr(exc)})
            prewarm_info["wall_s"] = round(time.perf_counter() - t0, 2)
            self.log(f"矩阵预热 {prewarm_info['wall_s']}s ok={prewarm_info['ok']}")
            self.rss.mark("after_prewarm")

        # ── 点 1/2/3：按 (策略, 窗口) prepare 一次，供全部成本档共用 ──
        prepare_ms_total = 0.0
        run_ms_total = 0.0
        failures = 0
        for strategy in spec.strategies:
            sid = str(strategy["id"])
            try:
                sdef = self.sengine.get(sid)
            except ValueError as exc:
                self.log(f"[FAIL] 策略 {sid} 未注册: {exc}")
                for window_key, window_period in windows.items():
                    for tier in spec.cost_tiers:
                        self.trials.append(
                            self._error_trial(sid, strategy, window_key, tier, window_period, f"未注册: {exc}")
                        )
                failures += 1
                continue
            backend = getattr(sdef, "execution_backend", "polars_expr")
            path_kind = (
                "matrix"
                if backend == "matrix_native"
                else ("direct" if backend in ("composite", "minute_filter") else "panel")
            )
            self.log(f"策略 {sid} 后端 {backend} 共享路径 {path_kind}")

            for window_key, (w_start, w_end) in windows.items():
                configs = [
                    self.build_config(strategy, (w_start, w_end), tier, symbols)
                    for tier in spec.cost_tiers
                ]
                prepared = None
                prepared_panel = None
                prepare_ms = 0.0
                fingerprint: dict[str, Any] | None = None
                prepare_error: str | None = None
                if path_kind != "direct":
                    t_prep = time.perf_counter()
                    try:
                        if path_kind == "matrix":
                            prepared = self.service.prepare_matrix_optimization(
                                configs, matrix_cache_max_bytes=128 * 1024 * 1024
                            )
                            fingerprint = _matrix_fingerprint(prepared)
                        else:
                            prepared_panel = self.service.prepare_panel_optimization(configs)
                            fingerprint = _panel_fingerprint(prepared_panel)
                    except Exception as exc:  # noqa: BLE001 — 报错即整组标记，不静默回退
                        prepare_error = repr(exc)
                        self.log(f"[FAIL] prepare {sid}/{window_key}: {prepare_error}")
                    prepare_ms = round((time.perf_counter() - t_prep) * 1000, 1)
                    prepare_ms_total += prepare_ms
                    self.rss.mark(f"prepare:{sid}:{window_key}")
                    self.prepares.append({
                        "strategy_id": sid,
                        "window": window_key,
                        "period": {"start": w_start.isoformat(), "end": w_end.isoformat()},
                        "path": path_kind,
                        "n_configs_shared": len(configs),
                        "prepare_ms": prepare_ms,
                        "source_generation": getattr(
                            prepared if prepared is not None else prepared_panel,
                            "source_generation",
                            None,
                        ),
                        "fingerprint": fingerprint,
                        "error": prepare_error,
                    })
                    if prepare_error is not None:
                        for tier in spec.cost_tiers:
                            self.trials.append(
                                self._error_trial(sid, strategy, window_key, tier, (w_start, w_end), prepare_error)
                            )
                        failures += 1
                        continue
                    self.log(
                        f"prepare {sid}/{window_key} {prepare_ms}ms 共享 {len(configs)} 个成本档"
                        + (f" 指纹 {fingerprint['digest']}" if fingerprint else "")
                    )
                else:
                    self.log(f"{sid}/{window_key} 后端无共享装载入口，逐档独立运行")

                for tier, cfg in zip(spec.cost_tiers, configs, strict=True):
                    trial = self._run_trial(
                        strategy, window_key, tier, cfg, prepared, prepared_panel,
                        prepare_ms, fingerprint, path_kind, len(configs),
                    )
                    run_ms_total += trial["timing_ms"]["run"]
                    if trial["error"]:
                        failures += 1
                    self.trials.append(trial)
                    self.rss.mark("after_trial")
                    status = "OK" if not trial["error"] else f"FAIL {trial['error'][:80]}"
                    m = trial["metrics"]
                    self.log(
                        f"  {trial['trial_id']} {sid}/{window_key}/{tier['id']} {status} "
                        f"ret={m.get('total_return')} sharpe={m.get('sharpe')} "
                        f"trades={m.get('n_trades')} {trial['timing_ms']['run']:.0f}ms"
                    )

        self.generation_after = self.engine.data_generation(spec.asset_type)
        generation_stable = (
            self.generation_before is not None
            and self.generation_before == self.generation_after
        )
        self.log(
            f"data_generation(after) {self.generation_after} stable={generation_stable}"
        )

        self._apply_multiple_testing(days)
        registry = self._build_registry(
            env=env,
            days=days,
            folds=folds,
            fold=fold,
            universe_meta=universe_meta,
            windows=windows,
            prewarm=prewarm_info,
            prepare_ms_total=prepare_ms_total,
            run_ms_total=run_ms_total,
            generation_stable=generation_stable,
        )
        self._write_outputs(registry)
        self.log(
            f"完成：{len(self.trials)} 个 trial，失败 {failures}，"
            f"prepare {prepare_ms_total/1000:.1f}s run {run_ms_total/1000:.1f}s "
            f"峰值 RSS {registry['resource'].get('rss_peak_wset_mb') or registry['resource']['rss_peak_mb']}MB"
        )
        self.log(f"输出目录 {self.out_dir}")
        self.log.close()
        if not generation_stable:
            return 2
        return 0 if failures == 0 else 2

    # ── 单次试验 ──
    def _run_trial(
        self,
        strategy: dict[str, Any],
        window_key: str,
        tier: dict[str, Any],
        cfg: StrategyBacktestConfig,
        prepared: PreparedMatrixBacktest | None,
        prepared_panel: PreparedPanelBacktest | None,
        prepare_ms: float,
        fingerprint: dict[str, Any] | None,
        path_kind: str,
        n_shared: int,
    ) -> dict[str, Any]:
        trial_id = f"t{len(self.trials) + 1:04d}"
        n_days = len(
            self.repo.list_enriched_dates(cfg.start, cfg.end, self.spec.asset_type)
        )
        t0 = time.perf_counter()
        error: str | None = None
        stats: dict[str, Any] = {}
        run_id = None
        try:
            kwargs: dict[str, Any] = {"result_policy": LIGHT_POLICY}
            if prepared is not None:
                kwargs["prepared"] = prepared
            elif prepared_panel is not None:
                kwargs["prepared_panel"] = prepared_panel
            result = self.service.run(cfg, **kwargs)
            run_id = result.run_id
            error = result.error
            stats = result.stats or {}
        except Exception as exc:  # noqa: BLE001 — 单次失败隔离，不拖垮整批
            error = f"{type(exc).__name__}: {exc}"
            self.log(traceback.format_exc(limit=3))
        run_ms = round((time.perf_counter() - t0) * 1000, 1)
        metrics = {k: stats.get(k) for k in COMPARABLE_STATS}
        metrics["execution"] = stats.get("execution")
        # 诊断字段：证明本次试验真的复用了共享矩阵（cache_hit/status 由引擎给出）
        metrics["diagnostics"] = {
            key: stats.get(key)
            for key in (
                "shared_market_data",
                "matrix_data_cache_hit",
                "matrix_data_cache_status",
                "matrix_data_cache_timing_ms",
                "market_matrix_shape",
                "market_matrix_bytes",
                "panel_rows",
                "feature_columns",
                "execution_backend",
            )
        }
        return {
            "trial_id": trial_id,
            "run_id": run_id,
            "strategy_id": cfg.strategy_id,
            "window": window_key,
            "cost_tier": tier["id"],
            "cost": self.cost_kwargs(tier),
            "params": dict(cfg.params or {}),
            "overrides": dict(cfg.overrides or {}),
            "period": {
                "start": cfg.start.isoformat(),
                "end": cfg.end.isoformat(),
                "n_trading_days": n_days,
            },
            "data_generation": self.generation_before,
            "prepared_fingerprint": fingerprint,
            "shared_prepare": {
                "path": path_kind,
                "n_configs_shared": n_shared,
                "prepare_ms": prepare_ms,
                "amortized_prepare_ms": round(prepare_ms / max(n_shared, 1), 1),
            },
            "metrics": metrics,
            "timing_ms": {"run": run_ms, "total": round(prepare_ms + run_ms, 1)},
            "error": error,
        }

    def _error_trial(
        self,
        sid: str,
        strategy: dict[str, Any],
        window_key: str,
        tier: dict[str, Any],
        window: tuple[date, date],
        error: str,
    ) -> dict[str, Any]:
        return {
            "trial_id": f"t{len(self.trials) + 1:04d}",
            "run_id": None,
            "strategy_id": sid,
            "window": window_key,
            "cost_tier": tier["id"],
            "cost": self.cost_kwargs(tier),
            "params": dict(strategy.get("params") or {}),
            "overrides": dict(strategy.get("overrides") or {}),
            "period": {
                "start": window[0].isoformat(),
                "end": window[1].isoformat(),
                "n_trading_days": None,
            },
            "data_generation": self.generation_before,
            "prepared_fingerprint": None,
            "shared_prepare": None,
            "metrics": {},
            "timing_ms": {"run": 0.0, "total": 0.0},
            "error": error,
        }

    # ── 点 4：多重检验（n_trials 进校正）──
    def _apply_multiple_testing(self, days: list[date]) -> None:
        """同一窗口内跨试验做 DSR + BH-FDR；n_trials = 该窗口内成功试验数。

        口径说明：
        - n_trials 按「策略×成本档」计（决策单元），不把 IS/OOS/ALL 当作独立试验，
          否则同一策略的同一份信号会被重复计数。
        - 夏普方差取同窗口内全部成功试验的样本方差，EM 由 expected_max_sharpe 给出。
        - 偏度/峰度按正态假设（0/3）代入，除非 trial 里带 curve_moments；
          record 中 moment_source 明确标注，不把假设当实测。
        """
        for window_key in {t["window"] for t in self.trials}:
            group = [
                t for t in self.trials
                if t["window"] == window_key and not t["error"] and t.get("metrics")
            ]
            sharpes = [t["metrics"].get("sharpe") for t in group]
            usable = [s for s in sharpes if isinstance(s, (int, float)) and math.isfinite(s)]
            variance = float(np.var(usable, ddof=1)) if len(usable) > 1 else 0.0
            n_trials = len(usable)
            em = expected_max_sharpe(n_trials, variance)
            p_values: list[float | None] = []
            for trial in group:
                sharpe = trial["metrics"].get("sharpe")
                n_obs = trial["period"]["n_trading_days"] or 0
                if not isinstance(sharpe, (int, float)) or not math.isfinite(sharpe):
                    trial["significance"] = {"error": "无有效 sharpe"}
                    p_values.append(None)
                    continue
                z, psr, p_one = psr_and_p(sharpe, int(n_obs), 0.0, 3.0, em)
                trial["significance"] = {
                    "sharpe": sharpe,
                    "n_obs": int(n_obs),
                    "moment_source": "assumed_normal(0,3)",
                    "n_trials": n_trials,
                    "sharpe_variance": round(variance, 6),
                    "expected_max_sharpe": round(em, 6),
                    "z": None if z is None else round(z, 4),
                    "psr": None if psr is None else round(psr, 6),
                    "p_one_sided": None if p_one is None else round(p_one, 6),
                }
                p_values.append(p_one)
            q_values = bh_fdr_qvalues(p_values)
            for trial, q in zip(group, q_values, strict=True):
                trial["significance"]["bh_q"] = None if q is None else round(q, 6)
            for trial in self.trials:
                if trial["window"] == window_key and trial["error"]:
                    trial["significance"] = {"error": "trial 失败，未参与校正"}

    # ── registry ──
    def _build_registry(
        self,
        *,
        env: dict[str, Any],
        days: list[date],
        folds: list[Any],
        fold: Any,
        universe_meta: dict[str, Any],
        windows: dict[str, tuple[date, date]],
        prewarm: dict[str, Any],
        prepare_ms_total: float,
        run_ms_total: float,
        generation_stable: bool,
    ) -> dict[str, Any]:
        evidence_id = uuid.uuid4().hex[:16]
        return {
            "schema": "strategy-harness/1",
            "batch_id": self.batch_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "environment": env,
            "spec": {
                "name": self.spec.name,
                "asset_type": self.spec.asset_type,
                "start": self.spec.start.isoformat(),
                "end": self.spec.end.isoformat(),
                "strategies": self.spec.strategies,
                "cost_tiers": self.spec.cost_tiers,
                "base": self.spec.base,
                "walkforward": self.spec.walkforward,
                "fold_used": self.spec.fold_used,
                "windows": self.spec.windows,
                "prewarm_years": self.spec.prewarm_years,
            },
            "data": {
                "asset_type": self.spec.asset_type,
                "generation_before": self.generation_before,
                "generation_after": self.generation_after,
                "generation_stable": generation_stable,
                "trading_days": {
                    "start": days[0].isoformat(),
                    "end": days[-1].isoformat(),
                    "n": len(days),
                },
                "universe": universe_meta,
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
                "fold_used": fold.index,
                "windows": {
                    k: {"start": v[0].isoformat(), "end": v[1].isoformat()}
                    for k, v in windows.items()
                },
                "basis": "list_enriched_dates + generate_folds(trading_days=...)",
            },
            "sharing": {
                "prewarm": prewarm,
                "prepares": self.prepares,
                "prepare_ms_total": round(prepare_ms_total, 1),
                "run_ms_total": round(run_ms_total, 1),
                "amortization": (
                    round(prepare_ms_total / max(len(self.trials), 1), 1)
                    if self.trials else None
                ),
            },
            "trials": self.trials,
            "resource": {
                **self.rss.summary(),
                "wall_s": round(time.perf_counter() - self.t_start, 1),
            },
            "evidence": {
                "run_id": evidence_id,
                "saved": False,
                "path": None,
                "error": None,
            },
        }

    def _write_outputs(self, registry: dict[str, Any]) -> None:
        reg_json = self.out_dir / "registry.json"
        reg_jsonl = self.out_dir / "registry.jsonl"
        summary = self.out_dir / "summary.md"

        # evidence 清单（与 app 的 backtest_runs 同 schema_version/run_id 契约）
        evidence = {
            "schema_version": 1,
            "run_id": registry["evidence"]["run_id"],
            "kind": "strategy_harness_batch",
            "created_at": registry["created_at"],
            "batch_id": self.batch_id,
            "data": registry["data"],
            "spec": registry["spec"],
            "sharing": registry["sharing"],
            "trial_count": len(self.trials),
            "trials": [
                {
                    "trial_id": t["trial_id"],
                    "strategy_id": t["strategy_id"],
                    "window": t["window"],
                    "cost_tier": t["cost_tier"],
                    "metrics": t["metrics"],
                    "significance": t.get("significance"),
                    "error": t["error"],
                }
                for t in self.trials
            ],
        }
        evidence_path = self.out_dir / f"evidence-{registry['evidence']['run_id']}.json"
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        registry["evidence"]["path"] = str(evidence_path)
        try:
            from app.backtest.evidence import save_evidence

            save_evidence(settings.data_dir, evidence)
            registry["evidence"].update({"saved": True, "saved_to": "data_dir/backtest_runs"})
        except Exception as exc:  # noqa: BLE001 — 落盘失败要如实标记
            registry["evidence"].update({"saved": False, "error": repr(exc)})

        registry["resource"]["wall_s"] = round(time.perf_counter() - self.t_start, 1)
        reg_json.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        with reg_jsonl.open("w", encoding="utf-8") as handle:
            for trial in self.trials:
                handle.write(json.dumps(trial, ensure_ascii=False, default=str) + "\n")
        summary.write_text(self._summary_md(registry), encoding="utf-8")

    def _summary_md(self, registry: dict[str, Any]) -> str:
        lines = [
            f"# 批量评估 {self.batch_id}",
            "",
            (
                f"- 区间：{registry['spec']['start']} .. {registry['spec']['end']}"
                f"（交易日 {registry['data']['trading_days']['n']} 个）"
            ),
            f"- 折：{len(registry['data']['folds'])} 个，使用 fold#{registry['data']['fold_used']}",
            f"- 标的池：{registry['data']['universe'].get('mode')} n={registry['data']['universe'].get('n')}",
            (
                f"- data_generation：`{registry['data']['generation_before']}`"
                f" → stable={registry['data']['generation_stable']}"
            ),
            (
                f"- 共享装载：prepare {registry['sharing']['prepare_ms_total']/1000:.1f}s /"
                f" run {registry['sharing']['run_ms_total']/1000:.1f}s /"
                f" 每 trial 摊销 {registry['sharing']['amortization']}ms"
            ),
            (
                f"- 峰值内存：OS peak_wset {registry['resource'].get('rss_peak_wset_mb')}MB"
                f"（标记点采样峰值 {registry['resource']['rss_peak_sampled_mb']}MB），"
                f"墙钟 {registry['resource']['wall_s']}s"
            ),
            "",
            "| trial | 策略 | 窗口 | 成本档 | 收益 | 年化 | 最大回撤 | Sharpe | 交易数 | 命中缓存 | PSR(DSR) | n_trials | EM | BH q |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for t in self.trials:
            m = t.get("metrics") or {}
            sig = t.get("significance") or {}
            if t["error"]:
                lines.append(
                    f"| {t['trial_id']} | {t['strategy_id']} | {t['window']} |"
                    f" {t['cost_tier']} | ERR | | | | | | | | | {t['error'][:60]} |"
                )
                continue
            hit = (m.get("diagnostics") or {}).get("matrix_data_cache_hit")
            lines.append(
                "| {id} | {st} | {w} | {c} | {ret} | {ann} | {dd} | {sr} | {n} | {hit} | {psr} | {nt} | {em} | {q} |".format(
                    id=t["trial_id"],
                    st=t["strategy_id"],
                    w=t["window"],
                    c=t["cost_tier"],
                    ret=m.get("total_return"),
                    ann=m.get("annual_return"),
                    dd=m.get("max_drawdown"),
                    sr=m.get("sharpe"),
                    n=m.get("n_trades"),
                    hit="-" if hit is None else ("Y" if hit else "N"),
                    psr="-" if sig.get("psr") is None else f"{sig['psr']:.4f}",
                    nt=sig.get("n_trials", "-"),
                    em="-" if sig.get("expected_max_sharpe") is None else f"{sig['expected_max_sharpe']:.3f}",
                    q="-" if sig.get("bh_q") is None else f"{sig['bh_q']:.3f}",
                )
            )
        lines.append("")
        lines.append(
            "> PSR 即已对 EM 校正的 deflated Sharpe（stats_v2.deflated_sharpe_psr，"
            "偏度/峰度按正态假设代入，`moment_source` 逐条标注）；BH q 为该窗口内跨试验的 "
            "Benjamini-Hochberg q 值，n_trials = 该窗口成功试验数（策略×成本档）。"
        )
        return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="策略批量评估底座")
    parser.add_argument("--spec", required=True, help="批次规格 JSON 路径")
    parser.add_argument("--out", default=None, help="输出目录（默认 runs/<批次id>）")
    args = parser.parse_args(argv)

    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = (ROOT / spec_path).resolve()
    try:
        spec = load_spec(spec_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] 规格无法加载: {exc}", file=sys.stderr)
        return 1

    out_dir = Path(args.out) if args.out else (
        Path(__file__).resolve().parent / "runs" / f"{spec.name}-{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    )
    harness = BatchHarness(spec, out_dir)
    try:
        return harness.run()
    except Exception as exc:  # noqa: BLE001 — 致命错误也要留痕
        harness.log(f"[FATAL] {type(exc).__name__}: {exc}")
        harness.log(traceback.format_exc())
        harness.log.close()
        return 1


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
