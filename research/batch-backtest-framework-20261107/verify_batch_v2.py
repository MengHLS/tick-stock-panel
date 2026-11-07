#!/usr/bin/env python
"""一致性验证 v2 — 修独立审核 F1（验证器盲点）与 F3（代码/数据世代绑定）。

v1（``verify_batch.py``）的缺陷已由独立审核 MATRIX-NATIVE-E2E-20261107.md 复现：
把一笔 ``pnl_amount``、一个权益点 ``value``、账户 ``total_return`` 与某折
``oos_stats.total_return`` 全部改坏，v1 仍然报 ``result_diffs=0``。原因是
``SKIP_KEYS`` 按**字段名在任意深度**跳过 ``total_return`` / ``continuous_account``，
而且只比生命周期计数与末值，从来没有比过完整曲线、逐笔与每折收益。

v2 的对应修复：

F1-1 豁免按**精确路径**管理（``EXEMPT_PATTERNS`` / ``DEVICE_PATTERNS`` /
     ``ANNOTATION_PATTERNS``），不再有"按名字全局跳过"的子句。
F1-2 完整权益曲线、逐笔、回撤：两侧用**同一个** ``run_batch.canonical_hash``
     计算规范化摘要并比对；摘要不等时再做元素级定位（有 ``--keep-raw`` 的批量
     原文时连字段值都逐点打印）。
F1-3 必需字段缺失即失败（``missing_required``）；只有批量侧多出的键、且路径在
     ``ANNOTATION_PATTERNS`` 里，才算注解。
F1-4 段收益与累计收益（``oos_stats.total_return`` / ``account_total_return_cumulative``）
     直接逐折比对，不再跳过。
F1-5 矩阵维度/内存差异**不算遥测**：必须给出有效交易域证明
     （``slice_axis.tradable_days_by_symbol`` × 生产侧真实装载轴），否则计入
     ``unproven_diffs`` 并使验证失败。

F3  入口与出口各校验一次：代码 SHA256（backend 源码 + 本仓脚本）、
     ``data_generation``、groups 清单哈希、策略定义/依赖文件哈希、override 内容。
    任何一项在比较时段内漂移 → 退出码 2，且不产出"通过"结论。
    同时把 ``verify_batch_v2.py`` 自身哈希写进绑定证据。

用法（在仓库根目录）::

    backend/.venv/Scripts/python.exe research/batch-backtest-framework-20261107/verify_batch_v2.py \
        --registry research/batch-backtest-framework-20261107/out_v2/registry.json

退出码：0 = 结果差异 0 且无未证明差异且绑定稳定；1 = 有结果/未证明差异；
2 = 代码/数据/输入漂移；3 = registry 版本或绑定不可用。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Self

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
HERE = Path(__file__).resolve().parent
for _path in (str(BACKEND), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import run_batch
from app.backtest.engine import BacktestEngine
from app.backtest.optimizer import StrategyOptimizer
from app.backtest.strategy import StrategyBacktestService
from app.backtest.walkforward import WalkForwardConfig, WalkForwardService
from app.config import settings
from app.factors.ext_factors import ensure_synced
from app.factors.store import load_into_registry
from app.strategy import config as strategy_config
from app.strategy.engine import StrategyEngine
from app.tickflow.repository import DataStore, KlineRepository

SCHEMA_REQUIRED = "batch-backtest-registry/2"

#: 墙钟/计时字段：与"结果是否一致"无关，但必须逐条列出并计数，不能静默丢弃。
EXEMPT_PATTERNS = (
    "oos_folds[*].elapsed_ms",
    "oos_folds[*].oos_stats.elapsed_ms",
    "oos_folds[*].oos_stats.timing_ms.*",
    "oos_folds[*].oos_stats.shared_prepare_timing_ms.*",
    "oos_folds[*].oos_stats.matrix_data_cache_timing_ms.*",
    "oos_folds[*].oos_stats.cache_timing_ms.*",
    "oos_folds[*].oos_stats.matrix_compute_cache.fingerprint_ms",
    "oos_folds[*].oos_stats.matrix_compute_cache.operations.*.compute_ms",
)

#: 每条豁免的语义（审核要求“不能一律遥测忽略”，所以逐条写明）。
EXEMPT_REASONS = {
    "oos_folds[*].elapsed_ms": "单折墙钟耗时",
    "oos_folds[*].oos_stats.elapsed_ms": "段回测墙钟耗时",
    "oos_folds[*].oos_stats.timing_ms": "prepare/评分/模拟/统计分段耗时",
    "oos_folds[*].oos_stats.shared_prepare_timing_ms": "共享矩阵 prepare 各子阶段耗时",
    "oos_folds[*].oos_stats.matrix_data_cache_timing_ms": "矩阵盘缓存扫描/布局/刷盘耗时",
    "oos_folds[*].oos_stats.cache_timing_ms": "其余缓存耗时字段",
    "oos_folds[*].oos_stats.matrix_compute_cache.fingerprint_ms": "缓存指纹计算耗时",
    "oos_folds[*].oos_stats.matrix_compute_cache.operations.*.compute_ms": "单项算子计算耗时",
}

#: 资源/维度字段：物理矩阵按装载窗口裁剪，长度与字节数必然不同。这类差异**必须**
#: 由有效交易域证明消除（见 ``build_axis_proof``），证明不成立就算失败。
DEVICE_PATTERNS = (
    "oos_folds[*].oos_stats.market_matrix_shape[*]",
    "oos_folds[*].oos_stats.market_matrix_bytes",
    "oos_folds[*].oos_stats.shared_market_data_bytes",
    "oos_folds[*].oos_stats.matrix_compute_cache.current_bytes",
    "oos_folds[*].oos_stats.matrix_compute_cache.peak_bytes",
    "oos_folds[*].oos_stats.matrix_compute_cache.computed_bytes",
    "oos_folds[*].oos_stats.matrix_compute_cache.operations.*.computed_bytes",
)

#: 只有批量侧才有的键（生产 run() 不返回）。每一个都要写清为什么它不参与比对。
ANNOTATION_PATTERNS = (
    "oos_folds[*].segment_return",
    "oos_folds[*].elapsed_ms",
    "continuous_account.n_folds_total",
    "continuous_account.n_curve_points",
    "continuous_account.n_trade_records",
    "continuous_account.n_drawdown_points",
    "continuous_account.equity_curve_sha256",
    "continuous_account.trades_sha256",
    "continuous_account.drawdown_curve_sha256",
)

ANNOTATION_REASONS = {
    "oos_folds[*].segment_return": "段收益与 continuous_account.boundaries[*].segment_return 比对，此键为折记录内的回声",
    "oos_folds[*].elapsed_ms": "生产折记录不含单折耗时",
    "continuous_account.n_folds_total": "生产 run() 用顶层 n_planned_folds 表达计划折数",
    "continuous_account.n_curve_points": "批量侧计数注解，与生产曲线长度单独核对",
    "continuous_account.n_trade_records": "批量侧计数注解，与生产逐笔长度单独核对",
    "continuous_account.n_drawdown_points": "批量侧计数注解，与生产回撤曲线长度单独核对",
    "continuous_account.equity_curve_sha256": "批量侧规范化摘要，用于替代原文存储",
    "continuous_account.trades_sha256": "批量侧规范化摘要，用于替代原文存储",
    "continuous_account.drawdown_curve_sha256": "批量侧规范化摘要，用于替代原文存储",
}

CURVE_FIELDS = {
    "equity_curve": "equity_curve_sha256",
    "trades": "trades_sha256",
    "drawdown_curve": "drawdown_curve_sha256",
}
CURVE_COUNTS = {
    "equity_curve": "n_curve_points",
    "trades": "n_trade_records",
    "drawdown_curve": "n_drawdown_points",
}

REQUIRED_ENTRY = (
    "run_id",
    "group",
    "strategy_id",
    "params",
    "status",
    "data_generation",
    "code_sha256",
    "folds",
    "is_runs",
    "oos_folds",
    "oos_summary",
    "continuous_account",
    "engine_execution_count",
    "hypothesis_count",
)
REQUIRED_ACCOUNT = (
    "final_equity",
    "final_cash",
    "final_positions",
    "final_market_value",
    "stats",
    "boundaries",
    "invariants",
    "trade_lifecycle",
    "duplicate_dates",
    "timeline",
    "replay_span",
    "equity_curve_sha256",
    "trades_sha256",
    "drawdown_curve_sha256",
)
REQUIRED_PROD = (
    "objective",
    "direction",
    "window_basis",
    "n_trading_days",
    "n_folds",
    "n_skipped",
    "n_planned_folds",
    "folds",
    "skipped",
    "summary",
    "continuous_account",
    "shared_market_data",
)


# --------------------------------------------------------------------------- #
# 路径分类
# --------------------------------------------------------------------------- #
def _segment_match(pattern: str, segment: str) -> bool:
    if pattern == "*":
        return True
    if pattern.endswith("[*]"):
        head = pattern[:-3]
        return segment.startswith(f"{head}[") and segment.endswith("]")
    return pattern == segment


def path_matches(pattern: str, path: str) -> bool:
    """逐段精确匹配；``*`` 只匹配单段，``[*]`` 只匹配带下标的同一段。"""
    pattern_segments = pattern.split(".")
    path_segments = path.split(".")
    if len(pattern_segments) != len(path_segments):
        return False
    return all(
        _segment_match(p, s) for p, s in zip(pattern_segments, path_segments, strict=True)
    )


def _matches_any(patterns: tuple[str, ...], path: str) -> bool:
    return any(path_matches(pattern, path) for pattern in patterns)


def is_exempt(path: str) -> bool:
    return _matches_any(EXEMPT_PATTERNS, path)


def is_device(path: str) -> bool:
    return _matches_any(DEVICE_PATTERNS, path)


def is_annotation(path: str) -> bool:
    return _matches_any(ANNOTATION_PATTERNS, path)


class Sink:
    """差异收集器：结果差异完整落盘；单个结构最多保留 60 条明细，但计数不受限。"""

    def __init__(self, detail_limit: int = 60) -> None:
        self.result: list[dict[str, Any]] = []
        self.device: list[dict[str, Any]] = []
        self.exempt: list[dict[str, Any]] = []
        self.annotation: list[dict[str, Any]] = []
        self.n_result = 0
        self.detail_limit = detail_limit

    def add(self, kind: str, path: str, batch: Any, prod: Any, **extra: Any) -> None:
        self.n_result += 1
        if len(self.result) < self.detail_limit:
            self.result.append(
                {"field": path, "kind": kind, "batch": batch, "prod": prod, **extra}
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_result_diffs": self.n_result,
            "n_device_diffs": len(self.device),
            "n_exempt_diffs": len(self.exempt),
            "n_annotation_keys": len(self.annotation),
            "result_diffs": self.result,
            "device_diffs": self.device,
            "exempt_diffs": self.exempt,
            "annotations": self.annotation,
        }


def walk(path: str, batch: Any, prod: Any, sink: Sink) -> None:
    """递归比对：生产是基准，少键即失败；多键必须命中注解白名单。"""
    if is_exempt(path):
        sink.exempt.append(
            {"field": path, "reason": _exempt_reason(path), "batch": batch, "prod": prod}
        )
        return
    if is_device(path):
        sink.device.append({"field": path, "batch": batch, "prod": prod})
        return
    if isinstance(batch, dict) and isinstance(prod, dict):
        for key in sorted(set(batch) | set(prod), key=str):
            sub = f"{path}.{key}" if path else str(key)
            in_batch = key in batch
            in_prod = key in prod
            if in_batch and not in_prod:
                if is_annotation(sub):
                    sink.annotation.append(
                        {
                            "field": sub,
                            "reason": _annotation_reason(sub),
                            "batch": batch[key],
                        }
                    )
                    continue
                sink.add("extra_in_batch", sub, batch[key], "<missing>")
                continue
            if in_prod and not in_batch:
                sink.add("missing_required", sub, "<missing>", prod[key])
                continue
            walk(sub, batch[key], prod[key], sink)
        return
    if isinstance(batch, list) and isinstance(prod, list):
        if len(batch) != len(prod):
            sink.add("length", path, len(batch), len(prod))
            return
        for index, (left, right) in enumerate(zip(batch, prod, strict=True)):
            walk(f"{path}[{index}]", left, right, sink)
        return
    if isinstance(batch, bool) or isinstance(prod, bool):
        if bool(batch) != bool(prod):
            sink.add("value", path, batch, prod)
        return
    if isinstance(batch, (int, float)) and isinstance(prod, (int, float)):
        if float(batch) != float(prod):
            sink.add("value", path, batch, prod, delta=float(batch) - float(prod))
        return
    if batch != prod:
        sink.add("value", path, batch, prod)


def _annotation_reason(path: str) -> str:
    for pattern, reason in ANNOTATION_REASONS.items():
        if path_matches(pattern, path):
            return reason
    return "未登记"


def _exempt_reason(path: str) -> str:
    for pattern, reason in EXEMPT_REASONS.items():
        if path_matches(pattern, path) or (
            pattern.endswith(".*") and _prefix_match(pattern[:-2], path)
        ):
            return reason
    return "未登记"


def _prefix_match(prefix: str, path: str) -> bool:
    prefix_segments = prefix.split(".")
    path_segments = path.split(".")
    if len(prefix_segments) >= len(path_segments):
        return False
    return all(
        _segment_match(p, s)
        for p, s in zip(prefix_segments, path_segments[: len(prefix_segments)], strict=True)
    )


# --------------------------------------------------------------------------- #
# 运行时
# --------------------------------------------------------------------------- #
def build_runtime():
    data_dir = Path(settings.data_dir)
    load_into_registry(data_dir)
    ensure_synced(data_dir)
    repo = KlineRepository(DataStore(data_dir))
    strategy_engine = StrategyEngine(
        strategy_dirs=[data_dir / "strategies"],
        override_loader=lambda sid: strategy_config.load_override(data_dir, sid),
    )
    service = StrategyBacktestService(BacktestEngine(repo), strategy_engine)
    optimizer = StrategyOptimizer(service, strategy_engine)
    return (
        repo,
        service,
        strategy_engine,
        WalkForwardService(optimizer, service, strategy_engine),
    )


class MatrixLoadRecorder:
    """记录生产侧**真实**加载的矩阵轴（不改变行为，只旁观调用）。

    审核指出 v1 的维度豁免是"一律遥测忽略"；要替换它，就必须拿到生产侧真正
    装载出来的证券集合，才能证明批量并集轴多出来的列在正式区间内 0 个可交易日。
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.visible: list[frozenset[str]] = []
        self._original = None

    def __enter__(self) -> Self:
        self._original = BacktestEngine.load_market_data_matrix_for_backtest
        recorder = self

        def patched(engine_self, symbols, start, end, *args, **kwargs):
            market = recorder._original(engine_self, symbols, start, end, *args, **kwargs)
            labels = [str(label)[:10] for label in market.timestamp_labels]
            symbol_tuple = tuple(str(symbol) for symbol in market.symbols)
            recorder.calls.append(
                {
                    "n_symbols": len(symbol_tuple),
                    "n_dates": len(labels),
                    "window": [labels[0], labels[-1]] if labels else [None, None],
                    "requested_symbols": None if symbols is None else len(symbols),
                    "cache_status": getattr(market, "cache_status", None),
                    "symbols_sha256": run_batch.canonical_hash(sorted(symbol_tuple)),
                }
            )
            recorder.visible.append(frozenset(symbol_tuple))
            return market

        BacktestEngine.load_market_data_matrix_for_backtest = patched
        return self

    def __exit__(self, *exc_info: object) -> bool:
        if self._original is not None:
            BacktestEngine.load_market_data_matrix_for_backtest = self._original
        return False


# --------------------------------------------------------------------------- #
# 有效交易域证明（替代"维度差异一律忽略"）
# --------------------------------------------------------------------------- #
def build_axis_proof(
    entry: dict[str, Any],
    production: dict[str, Any],
    recorder: MatrixLoadRecorder,
    registry: dict[str, Any],
) -> dict[str, Any]:
    slice_axis = registry.get("slice_axis") or {}
    batch_map: dict[str, int] = slice_axis.get("tradable_days_by_symbol") or {}
    batch_symbols = set(batch_map)
    prod_union: set[str] = set()
    for visible in recorder.visible:
        prod_union |= set(visible)

    shapes = [
        (record.get("oos_stats") or {}).get("market_matrix_shape")
        for record in production.get("folds") or []
    ]
    prod_columns = sorted({int(shape[1]) for shape in shapes if shape})
    batch_only = sorted(batch_symbols - prod_union)
    prod_only = sorted(prod_union - batch_symbols)
    batch_only_tradable = {
        symbol: int(batch_map[symbol]) for symbol in batch_only if int(batch_map.get(symbol, 0)) > 0
    }
    proof = {
        "batch_axis_symbols": len(batch_symbols) if batch_symbols else None,
        "batch_axis_symbols_sha256": slice_axis.get("symbols_sha256"),
        "batch_tradable_symbols_in_official_span": slice_axis.get(
            "n_symbols_tradable_in_official_span"
        ),
        "official_span": slice_axis.get("official_span"),
        "batch_matrix_window": (registry.get("slice_load") or {}).get("matrix_window"),
        "production_load_count": len(recorder.calls),
        "production_load_axes": recorder.calls,
        "production_matrix_shape_columns": prod_columns,
        "production_shared_market_data": bool(production.get("shared_market_data")),
        "n_batch_only_symbols": len(batch_only),
        "batch_only_symbols": batch_only,
        "n_production_only_symbols": len(prod_only),
        "production_only_symbols": prod_only,
        "batch_only_with_tradable_days_in_official_span": batch_only_tradable,
        "compared_group": entry["group"],
    }
    ok = True
    reasons: list[str] = []
    if not batch_map:
        ok = False
        reasons.append("registry 缺 slice_axis.tradable_days_by_symbol（批量侧未提供有效交易域证据）")
    if not recorder.calls:
        ok = False
        reasons.append("未观测到生产侧矩阵装载，无法取得真实证券轴")
    if prod_only:
        ok = False
        reasons.append(f"存在 {len(prod_only)} 个生产侧独有的证券，批量并集轴未覆盖")
    if batch_only_tradable:
        ok = False
        reasons.append(
            f"{len(batch_only_tradable)} 个批量侧独有证券在正式区间内仍有可交易日，"
            "不能作为轴差异解释"
        )
    if prod_columns and batch_map and max(prod_columns) > len(batch_map):
        ok = False
        reasons.append("生产侧列数大于批量并集轴列数，轴包含关系不成立")
    if not production.get("shared_market_data"):
        ok = False
        reasons.append("生产侧未走共享矩阵路径（shared_market_data=false）")
    # 时间轴同理: 生产装载窗口必须被批量窗口覆盖, 否则 shape[0] 差异就无法解释
    batch_window = (registry.get("slice_load") or {}).get("matrix_window") or [None, None]
    window_covered = True
    for call in recorder.calls:
        window = call.get("window") or [None, None]
        if not batch_window[0] or not window[0]:
            window_covered = False
            continue
        if not (batch_window[0] <= window[0] and window[1] <= batch_window[1]):
            window_covered = False
    if not window_covered:
        ok = False
        reasons.append("生产装载窗口未被批量并集窗口覆盖，shape[0] 差异无法解释")
    proof["window_covered_by_batch"] = window_covered
    proof["proven"] = ok
    proof["reasons"] = reasons
    proof["scope"] = (
        "只证明：批量并集轴中多出的证券列在该组正式 IS/OOS 区间内 0 个可交易日，"
        "且不存在生产侧独有证券、生产确实走了共享矩阵。不证明两侧物理矩阵同轴同窗口。"
    )
    return proof


# --------------------------------------------------------------------------- #
# 分段比对
# --------------------------------------------------------------------------- #
def compare_continuous(
    entry: dict[str, Any],
    production: dict[str, Any],
    sink: Sink,
) -> dict[str, Any]:
    batch_account = entry["continuous_account"]
    prod_account = production.get("continuous_account") or {}

    batch_view = {
        key: value
        for key, value in batch_account.items()
        if key not in CURVE_FIELDS and key not in CURVE_COUNTS.values()
    }
    prod_view = {key: value for key, value in prod_account.items() if key not in CURVE_FIELDS}
    walk("continuous_account", batch_view, prod_view, sink)

    batch_raw = (entry.get("raw") or {}) if isinstance(entry.get("raw"), dict) else {}
    curves: dict[str, Any] = {}
    for field, hash_key in CURVE_FIELDS.items():
        prod_list = prod_account.get(field)
        batch_hash = batch_account.get(hash_key)
        if prod_list is None or batch_hash is None:
            sink.add(
                "missing_required",
                f"continuous_account.{field}",
                batch_hash,
                "<present>" if prod_list is not None else "<missing>",
            )
            continue
        actual = run_batch.canonical_hash(prod_list)
        equal = actual == batch_hash
        record = {
            "n_prod": len(prod_list),
            "n_batch": batch_account.get(CURVE_COUNTS[field]),
            "prod_sha256": actual,
            "batch_sha256": batch_hash,
            "equal": equal,
        }
        if not equal:
            sink.add("canonical_hash", f"continuous_account.{field}", batch_hash, actual)
            raw_list = batch_raw.get(field)
            if isinstance(raw_list, list):
                record["first_value_diffs"] = _first_element_diffs(prod_list, raw_list, limit=5)
            else:
                record["first_value_diffs"] = "无批量原文（未使用 --keep-raw），仅摘要可判不等"
        elif batch_account.get(CURVE_COUNTS[field]) != len(prod_list):
            sink.add(
                "count",
                f"continuous_account.{CURVE_COUNTS[field]}",
                batch_account.get(CURVE_COUNTS[field]),
                len(prod_list),
            )
        curves[field] = record

    invariants = prod_account.get("invariants") or {}
    failed = sorted(name for name, value in invariants.items() if not value)
    if failed:
        sink.add("invariant_failed", "continuous_account.invariants", "<all true>", failed)
    if prod_account.get("duplicate_dates") not in (0, None):
        sink.add(
            "invariant_failed",
            "continuous_account.duplicate_dates",
            0,
            prod_account.get("duplicate_dates"),
        )
    if not (prod_account.get("timeline") or {}).get("complete"):
        sink.add(
            "invariant_failed",
            "continuous_account.timeline.complete",
            True,
            (prod_account.get("timeline") or {}).get("complete"),
        )
    return {"curves": curves, "invariants_failed": failed}


def _first_element_diffs(prod_list: list[Any], batch_list: list[Any], limit: int) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for index, (prod_item, batch_item) in enumerate(
        zip(prod_list, batch_list, strict=False)
    ):
        if prod_item != batch_item:
            changed = sorted(
                key
                for key in set(prod_item) | set(batch_item)
                if prod_item.get(key) != batch_item.get(key)
            )
            diffs.append(
                {
                    "index": index,
                    "changed_fields": changed[:8],
                    "prod": {key: prod_item.get(key) for key in changed[:4]},
                    "batch": {key: batch_item.get(key) for key in changed[:4]},
                }
            )
            if len(diffs) >= limit:
                break
    return diffs


def compare_folds(entry: dict[str, Any], production: dict[str, Any], sink: Sink) -> dict[str, Any]:
    prod_folds = production.get("folds") or []
    batch_folds = entry["oos_folds"]
    if len(batch_folds) != len(prod_folds):
        sink.add("length", "oos_folds", len(batch_folds), len(prod_folds))
    projection = [
        {
            "index": record.get("index"),
            "train_start": record.get("train_start"),
            "train_end": record.get("train_end"),
            "test_start": record.get("test_start"),
            "test_end": record.get("test_end"),
        }
        for record in prod_folds
    ]
    walk("folds", entry["folds"], projection, sink)

    prod_by_index = {record.get("index"): record for record in prod_folds}
    matched = 0
    for record in batch_folds:
        prod = prod_by_index.get(record.get("index"))
        if prod is None:
            sink.add("missing_fold", f"oos_folds[{record.get('index')}]", "present", "<missing>")
            continue
        matched += 1
        walk(f"oos_folds[{record['index']}]", record, prod, sink)
    return {"n_batch": len(batch_folds), "n_prod": len(prod_folds), "n_matched": matched}


def compare_summary(entry: dict[str, Any], production: dict[str, Any], sink: Sink) -> dict[str, Any]:
    batch_summary = dict(entry["oos_summary"])
    prod_summary = dict(production.get("summary") or {})
    prod_account = production.get("continuous_account")
    identity = prod_summary.get("continuous_account") is prod_account
    batch_summary.pop("continuous_account", None)
    prod_summary.pop("continuous_account", None)
    walk("summary", batch_summary, prod_summary, sink)
    return {
        "production_summary_account_is_same_object": identity,
        "note": (
            "生产 summary.continuous_account 与顶层 continuous_account 是同一个对象"
            "（walkforward.py 里 summary[...] = continuous_report），因此账户字段只在"
            " continuous_account 一处比对，避免重复计数；这里记录同源事实。"
        ),
        "n_keys_batch": len(batch_summary),
        "n_keys_prod": len(prod_summary),
    }


def compare_scalars(
    entry: dict[str, Any],
    production: dict[str, Any],
    registry: dict[str, Any],
    trading_days: list[Any],
    sink: Sink,
) -> dict[str, Any]:
    slice_info = registry["slice"]
    settings_info = registry["settings"]
    checks = {
        "objective": (settings_info["objective"], production.get("objective")),
        "direction": (None, production.get("direction")),
        "window_basis": ("trading_days", production.get("window_basis")),
        "n_trading_days": (len(trading_days), production.get("n_trading_days")),
        "n_folds": (len(entry["oos_folds"]), production.get("n_folds")),
        "n_skipped": (len(entry["skipped"]), production.get("n_skipped")),
        "n_planned_folds": (len(slice_info["folds"]), production.get("n_planned_folds")),
        "shared_market_data": (True, production.get("shared_market_data")),
    }
    result: dict[str, Any] = {}
    for name, (expected, actual) in checks.items():
        if expected is None:
            result[name] = {"expected": "<not asserted>", "actual": actual}
            continue
        result[name] = {"expected": expected, "actual": actual}
        mismatch = bool(expected) != bool(actual) if isinstance(expected, bool) else expected != actual
        if mismatch:
            sink.add("scalar", name, expected, actual)
    # 生产 skipped 必须与批量逐条一致（批量只在 OOS 失败时写，生产也只在失败时写）
    walk("skipped", entry["skipped"], production.get("skipped") or [], sink)
    return result


# --------------------------------------------------------------------------- #
# F3: 代码 / 数据 / 输入绑定
# --------------------------------------------------------------------------- #
def binding_snapshot(groups_path: Path, groups: list[dict[str, Any]], rt: Any, asset_type: str) -> dict[str, Any]:
    inputs = run_batch.inputs_fingerprint(groups_path, groups, rt)
    return {
        "at": run_batch.now_iso(),
        "code": run_batch.code_fingerprint(),
        "data_generation": rt.engine.data_generation(asset_type),
        "groups_sha256": run_batch.sha256_file(groups_path),
        "inputs_sha256": run_batch.canonical_hash(inputs),
        "inputs": inputs,
        "verify_sha256": run_batch.sha256_file(Path(__file__).resolve()),
        "run_batch_sha256": run_batch.sha256_file(HERE / "run_batch.py"),
    }


def runtime_view(wf: WalkForwardService) -> SimpleNamespace:
    """绑定快照只需要 engine + strategy_engine 两面（不碰矩阵）。"""
    return SimpleNamespace(engine=wf.service.engine, strategy_engine=wf.strategy_engine)


def check_registry_binding(
    registry: dict[str, Any],
    snapshot: dict[str, Any],
    phase: str,
) -> list[dict[str, Any]]:
    """fail-closed：任何一项与 registry 记录不一致都记为违规，绝不降级为警告。"""
    violations: list[dict[str, Any]] = []
    binding = registry.get("binding") or {}
    if registry.get("schema") != SCHEMA_REQUIRED:
        violations.append(
            {
                "check": "schema",
                "phase": phase,
                "expected": SCHEMA_REQUIRED,
                "actual": registry.get("schema"),
                "fix": "用 v2 的 run_batch.py 重新跑批次（v1 registry 无绑定证据）",
            }
        )
        return violations
    if not binding.get("ok"):
        violations.append({"check": "binding.ok", "phase": phase, "actual": binding.get("ok")})
    code = binding.get("code") or {}
    if code.get("before") != snapshot["code"]["sha256"] or code.get("after") != snapshot["code"]["sha256"]:
        violations.append(
            {
                "check": "code_sha256",
                "phase": phase,
                "expected": [code.get("before"), code.get("after")],
                "actual": snapshot["code"]["sha256"],
                "fix": "backend 或本仓脚本已变；旧证据失效，必须重跑批次与比较",
            }
        )
    files_before = code.get("files_before") or {}
    for name, digest in files_before.items():
        current = snapshot["code"]["files"].get(name)
        if digest != current:
            violations.append(
                {
                    "check": f"code_file:{name}",
                    "phase": phase,
                    "expected": digest,
                    "actual": current,
                }
            )
    data = binding.get("data_generation") or {}
    if data.get("bound") != snapshot["data_generation"]:
        violations.append(
            {
                "check": "data_generation",
                "phase": phase,
                "expected": data.get("bound"),
                "actual": snapshot["data_generation"],
                "fix": "enriched 数据已重新发布；必须重跑批次才能比较",
            }
        )
    recorded_inputs = (registry.get("inputs") or {})
    recorded_hash = run_batch.canonical_hash(recorded_inputs) if recorded_inputs else None
    if recorded_hash != snapshot["inputs_sha256"]:
        violations.append(
            {
                "check": "inputs(groups/strategy/override)",
                "phase": phase,
                "expected": recorded_hash,
                "actual": snapshot["inputs_sha256"],
                "fix": "groups 清单、策略定义或 override 变了；批量结果不再对应同一份输入",
            }
        )
    return violations


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="批量底座 vs 生产单跑一致性验证 v2 (F1/F3 修复)")
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--group", action="append", default=None, help="只验指定组名 (可多次)")
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--out", type=Path, default=None, help="报告目录, 默认 <registry 目录>/verify_v2")
    parser.add_argument(
        "--no-capture",
        action="store_true",
        help="不落生产载荷快照 (默认落盘, 供 mutation_checks.py 离线复用)",
    )
    args = parser.parse_args(argv)

    registry_path = args.registry.resolve()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    out_dir = args.out or (registry_path.parent / "verify_v2")
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    repo, _service, _strategy_engine, wf = build_runtime()

    groups_path = Path(
        ((registry.get("inputs") or {}).get("groups_file") or {}).get("path")
        or (HERE / "groups.json")
    )
    if not groups_path.is_absolute():
        groups_path = (REPO / groups_path).resolve()
    groups = run_batch.load_groups(groups_path)
    if args.group:
        wanted = set(args.group)
        groups = [group for group in groups if group["name"] in wanted]
        if not groups:
            raise SystemExit(f"groups 里没有这些组: {sorted(wanted)}")

    slice_info = registry["slice"]
    settings_info = registry["settings"]
    start = run_batch.date.fromisoformat(slice_info["start"])
    end = run_batch.date.fromisoformat(slice_info["end"])
    trading_days = repo.list_enriched_dates(start, end, asset_type=slice_info["asset_type"])

    entry_snapshot = binding_snapshot(groups_path, groups, runtime_view(wf), slice_info["asset_type"])
    violations = check_registry_binding(registry, entry_snapshot, "entry")
    if violations:
        payload = {
            "verdict": "binding_violation",
            "phase": "entry",
            "violations": violations,
            "registry": str(registry_path),
            "snapshot": {k: v for k, v in entry_snapshot.items() if k != "inputs"},
        }
        (out_dir / "binding.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        print(json.dumps({"verdict": "binding_violation", "violations": violations}, ensure_ascii=False, default=str))
        return 2 if registry.get("schema") == SCHEMA_REQUIRED else 3

    entries = [run for run in registry["runs"] if run["group"] in {g["name"] for g in groups}]
    reports: list[dict[str, Any]] = []
    exit_code = 0
    for group in groups:
        entry = next((run for run in entries if run["group"] == group["name"]), None)
        if entry is None:
            raise SystemExit(f"registry 里没有组 {group['name']}")

        missing_entry = [key for key in REQUIRED_ENTRY if key not in entry]
        missing_account = [key for key in REQUIRED_ACCOUNT if key not in (entry.get("continuous_account") or {})]
        sink = Sink()
        for key in missing_entry:
            sink.add("missing_required", key, "<missing>", "<required>")
        for key in missing_account:
            sink.add("missing_required", f"continuous_account.{key}", "<missing>", "<required>")

        cfg = WalkForwardConfig(
            strategy_id=entry["strategy_id"],
            symbols=None,
            start=start,
            end=end,
            param_grid=entry["param_grid"],
            objective=settings_info["objective"],
            train_days=settings_info["train_days"],
            test_days=settings_info["test_days"],
            step_days=settings_info["step_days"],
            min_trades_oos=settings_info["min_trades_oos"],
            max_workers=args.max_workers,
            base_params=entry.get("base_params") or {},
            backtest_kwargs={
                "mode": "position",
                "initial_capital": settings_info["initial_capital"],
                "asset_type": settings_info["asset_type"],
            },
            matrix_cache_max_mb=settings_info["matrix_cache_max_mb"],
            trading_days=tuple(trading_days),
            continuous_account=True,
        )
        print(
            json.dumps({"verify": entry["group"], "phase": "production_run_start"}, ensure_ascii=False),
            flush=True,
        )
        with MatrixLoadRecorder() as recorder:
            production = wf.run(cfg)

        missing_prod = [key for key in REQUIRED_PROD if key not in production]
        for key in missing_prod:
            sink.add("missing_required", f"production.{key}", "<missing>", "<required>")

        fold_report = compare_folds(entry, production, sink)
        continuous_report = compare_continuous(entry, production, sink)
        summary_report = compare_summary(entry, production, sink)
        scalar_report = compare_scalars(entry, production, registry, trading_days, sink)
        axis = build_axis_proof(entry, production, recorder, registry)

        # 设备/维度差异必须有证明，否则升格为未证明差异并失败
        unproven: list[dict[str, Any]] = []
        if sink.device and not axis["proven"]:
            unproven = [
                {**item, "reason": "矩阵维度/内存差异未获有效交易域证明"} for item in sink.device
            ]
        n_unproven = len(unproven) if not axis["proven"] else 0

        report = {
            "group": entry["group"],
            "run_id": entry["run_id"],
            "strategy_id": entry["strategy_id"],
            "params": entry["params"],
            "folds": fold_report,
            "continuous_account": continuous_report,
            "summary": summary_report,
            "scalars": scalar_report,
            "axis_proof": axis,
            "n_result_diffs": sink.n_result,
            "n_unproven_diffs": n_unproven,
            "n_device_diffs": len(sink.device),
            "n_exempt_diffs": len(sink.exempt),
            "n_annotation_keys": len(sink.annotation),
            **sink.as_dict(),
            "unproven_diffs": unproven,
            "production": {
                "duplicate_dates": (production.get("continuous_account") or {}).get("duplicate_dates"),
                "timeline_complete": ((production.get("continuous_account") or {}).get("timeline") or {}).get("complete"),
                "shared_market_data": production.get("shared_market_data"),
                "n_folds": production.get("n_folds"),
                "n_planned_folds": production.get("n_planned_folds"),
                "final_equity": (production.get("continuous_account") or {}).get("final_equity"),
            },
        }
        reports.append(report)
        (out_dir / f"compare_{entry['group']}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        if not args.no_capture:
            (out_dir / f"prod_{entry['group']}.json").write_text(
                json.dumps(production, ensure_ascii=False, default=str), encoding="utf-8"
            )
        print(
            json.dumps(
                {
                    "group": report["group"],
                    "n_result_diffs": report["n_result_diffs"],
                    "n_unproven_diffs": report["n_unproven_diffs"],
                    "n_exempt_diffs": report["n_exempt_diffs"],
                    "axis_proven": axis["proven"],
                    "duplicate_dates": report["production"]["duplicate_dates"],
                    "timeline_complete": report["production"]["timeline_complete"],
                    "first_result_diffs": report["result_diffs"][:5],
                },
                ensure_ascii=False,
                default=str,
            ),
            flush=True,
        )
        if report["n_result_diffs"] or report["n_unproven_diffs"]:
            exit_code = 1

    exit_snapshot = binding_snapshot(groups_path, groups, runtime_view(wf), slice_info["asset_type"])
    exit_violations = check_registry_binding(registry, exit_snapshot, "exit")
    drift_checks = []
    for name in ("code", "data_generation", "groups_sha256", "inputs_sha256", "verify_sha256"):
        before = entry_snapshot[name]
        after = exit_snapshot[name]
        if name == "code":
            before = before["sha256"]
            after = after["sha256"]
        if before != after:
            drift_checks.append({"check": name, "before": before, "after": after})
    binding_report = {
        "schema": "batch-verify-binding/2",
        "registry": str(registry_path),
        "entry": {k: v for k, v in entry_snapshot.items() if k != "inputs"},
        "exit": {k: v for k, v in exit_snapshot.items() if k != "inputs"},
        "drift_during_verify": drift_checks,
        "registry_violations": exit_violations,
        "ok": not drift_checks and not exit_violations,
    }
    (out_dir / "binding.json").write_text(
        json.dumps(binding_report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    summary = {
        "schema": "batch-verify-report/2",
        "registry": str(registry_path),
        "groups": len(reports),
        "total_result_diffs": sum(r["n_result_diffs"] for r in reports),
        "total_unproven_diffs": sum(r["n_unproven_diffs"] for r in reports),
        "total_exempt_diffs": sum(r["n_exempt_diffs"] for r in reports),
        "binding_ok": binding_report["ok"],
        "elapsed_s": round(time.perf_counter() - started, 2),
        "axis_proven": [{"group": r["group"], "proven": r["axis_proof"]["proven"]} for r in reports],
        "groups_detail": [
            {
                "group": r["group"],
                "n_result_diffs": r["n_result_diffs"],
                "n_unproven_diffs": r["n_unproven_diffs"],
                "n_exempt_diffs": r["n_exempt_diffs"],
                "n_device_diffs": r["n_device_diffs"],
                "production_duplicate_dates": r["production"]["duplicate_dates"],
                "production_timeline_complete": r["production"]["timeline_complete"],
                "curves": r["continuous_account"]["curves"],
            }
            for r in reports
        ],
    }
    (out_dir / "compare_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({k: summary[k] for k in ("total_result_diffs", "total_unproven_diffs", "binding_ok", "elapsed_s")}, ensure_ascii=False))
    if not binding_report["ok"]:
        return 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
