#!/usr/bin/env python
"""负向变异检验（独立审核 F1 的验收要求）与正向对照。

F1 的原始复现是：把一笔 ``pnl_amount``、一个权益点 ``value``、账户
``total_return`` 与某折 ``oos_stats.total_return`` 改坏，v1 仍然报
``result_diffs=0``。这里对 v2 做同一组变异，并额外覆盖：

* 曲线点、逐笔金额/盈亏、逐笔入场金额、折段收益、账户累计收益、汇总字段；
* 删除**必需字段**（生产侧删一个 → 批量多键；批量侧删一个 → 少必需键）；
* 曲线/回撤整条缺失、曲线长度变化；
* 代码 SHA256、数据世代、groups 输入哈希被篡改（F3 绑定）；
* 有效交易域证明的正/负两个方向（证明不是橡皮图章）。

全部在**内存副本**上做，不修改任何证据文件。未变异的原始对照必须仍然
``n_result_diffs == 0``，否则整个检验作废（先修底座，再谈负向）。

用法::

    backend/.venv/Scripts/python.exe research/batch-backtest-framework-20261107/mutation_checks.py \
        --registry research/batch-backtest-framework-20261107/out_v2/registry.json

退出码：0 = 原始对照通过且每条变异都被检出；1 = 存在未检出变异或对照不干净。
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
HERE = Path(__file__).resolve().parent
for _path in (str(BACKEND), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import run_batch
import verify_batch_v2 as v2
from app.config import settings
from app.factors.ext_factors import ensure_synced
from app.factors.store import load_into_registry
from app.tickflow.repository import DataStore, KlineRepository


def load_trading_days(registry: dict[str, Any]) -> list[date]:
    data_dir = Path(settings.data_dir)
    load_into_registry(data_dir)
    ensure_synced(data_dir)
    repo = KlineRepository(DataStore(data_dir))
    slice_info = registry["slice"]
    return repo.list_enriched_dates(
        date.fromisoformat(slice_info["start"]),
        date.fromisoformat(slice_info["end"]),
        asset_type=slice_info["asset_type"],
    )


def compare_core(
    entry: dict[str, Any],
    production: dict[str, Any],
    registry: dict[str, Any],
    trading_days: list[date],
) -> dict[str, Any]:
    """与 verify_batch_v2.main 相同的比对序列（不含矩阵装载观测与绑定快照）。"""
    sink = v2.Sink()
    for key in v2.REQUIRED_ENTRY:
        if key not in entry:
            sink.add("missing_required", key, "<missing>", "<required>")
    account = entry.get("continuous_account") or {}
    for key in v2.REQUIRED_ACCOUNT:
        if key not in account:
            sink.add("missing_required", f"continuous_account.{key}", "<missing>", "<required>")
    for key in v2.REQUIRED_PROD:
        if key not in production:
            sink.add("missing_required", f"production.{key}", "<missing>", "<required>")

    v2.compare_folds(entry, production, sink)
    v2.compare_continuous(entry, production, sink)
    v2.compare_summary(entry, production, sink)
    v2.compare_scalars(entry, production, registry, trading_days, sink)
    return sink.as_dict()


# --------------------------------------------------------------------------- #
# 变异定义
# --------------------------------------------------------------------------- #
def _curve(prod: dict[str, Any]) -> list[dict[str, Any]]:
    return prod["continuous_account"]["equity_curve"]


def _trades(prod: dict[str, Any]) -> list[dict[str, Any]]:
    return prod["continuous_account"]["trades"]


def mutate_curve_value(entry, prod, registry) -> None:
    _curve(prod)[0]["value"] = float(_curve(prod)[0]["value"]) + 999.0


def mutate_curve_cash(entry, prod, registry) -> None:
    _curve(prod)[5]["cash"] = float(_curve(prod)[5]["cash"]) + 0.01


def mutate_curve_date(entry, prod, registry) -> None:
    _curve(prod)[3]["date"] = "1999-01-01"


def mutate_curve_length(entry, prod, registry) -> None:
    _curve(prod).pop()


def mutate_trade_pnl(entry, prod, registry) -> None:
    first = _trades(prod)[0]
    first["pnl_amount"] = float(first.get("pnl_amount") or 0.0) + 999.0


def mutate_trade_entry_value(entry, prod, registry) -> None:
    first = _trades(prod)[0]
    first["entry_value"] = round(float(first.get("entry_value") or 0.0) + 0.01, 2)


def mutate_fold_total_return(entry, prod, registry) -> None:
    prod["folds"][0]["oos_stats"]["total_return"] = 999.0


def mutate_fold_cumulative_return(entry, prod, registry) -> None:
    prod["folds"][1]["oos_stats"]["account_total_return_cumulative"] = 999.0


def mutate_account_stats_return(entry, prod, registry) -> None:
    stats = prod["continuous_account"]["stats"]
    key = "total_return" if "total_return" in stats else next(iter(stats))
    stats[key] = 999.0


def mutate_summary_field(entry, prod, registry) -> None:
    summary = prod["summary"]
    summary["n_folds"] = int(summary.get("n_folds") or 0) + 1


def mutate_delete_prod_required(entry, prod, registry) -> None:
    prod["continuous_account"].pop("final_equity", None)


def mutate_delete_prod_curve(entry, prod, registry) -> None:
    prod["continuous_account"].pop("drawdown_curve", None)


def mutate_delete_entry_required(entry, prod, registry) -> None:
    (entry.get("continuous_account") or {}).pop("trades_sha256", None)


def mutate_delete_entry_fold(entry, prod, registry) -> None:
    entry["oos_folds"][0]["oos_stats"].pop("n_trades", None)


def mutate_boundary_equity(entry, prod, registry) -> None:
    prod["continuous_account"]["boundaries"][0]["equity_end"] = 1.0


def mutate_duplicate_dates(entry, prod, registry) -> None:
    prod["continuous_account"]["duplicate_dates"] = 3


def mutate_timeline_incomplete(entry, prod, registry) -> None:
    prod["continuous_account"]["timeline"]["complete"] = False


def mutate_code_generation(entry, prod, registry) -> None:
    registry["binding"]["code"]["before"] = "0" * 64


def mutate_data_generation(entry, prod, registry) -> None:
    registry["binding"]["data_generation"]["bound"] = "deadbeefdeadbeef"


def mutate_groups_hash(entry, prod, registry) -> None:
    registry["inputs"]["groups_file"]["sha256"] = "0" * 64


MUTATIONS: tuple[tuple[str, Callable[[dict, dict, dict], None], str], ...] = (
    ("curve_point_value", mutate_curve_value, "第一个权益点 value += 999"),
    ("curve_point_cash", mutate_curve_cash, "第 6 个权益点 cash += 0.01"),
    ("curve_point_date", mutate_curve_date, "第 4 个权益点日期被改"),
    ("curve_length", mutate_curve_length, "曲线末尾少一个点"),
    ("trade_pnl_amount", mutate_trade_pnl, "第一笔逐笔 pnl_amount += 999"),
    ("trade_entry_value", mutate_trade_entry_value, "第一笔逐笔 entry_value += 0.01"),
    ("fold_total_return", mutate_fold_total_return, "第 1 折 oos_stats.total_return = 999"),
    (
        "fold_account_cumulative_return",
        mutate_fold_cumulative_return,
        "第 2 折 account_total_return_cumulative = 999",
    ),
    ("account_stats_return", mutate_account_stats_return, "账户 stats 收益字段 = 999"),
    ("summary_field", mutate_summary_field, "summary.n_folds +1"),
    ("delete_prod_required", mutate_delete_prod_required, "生产侧缺 final_equity"),
    ("delete_prod_curve", mutate_delete_prod_curve, "生产侧缺 drawdown_curve"),
    ("delete_entry_required", mutate_delete_entry_required, "批量侧缺 trades_sha256"),
    ("delete_entry_fold_stat", mutate_delete_entry_fold, "批量侧折缺 oos_stats.n_trades"),
    ("boundary_equity", mutate_boundary_equity, "首个折边界 equity_end = 1.0"),
    ("duplicate_dates", mutate_duplicate_dates, "duplicate_dates 改成 3"),
    ("timeline_incomplete", mutate_timeline_incomplete, "timeline.complete 改成 false"),
    ("code_sha256", mutate_code_generation, "registry 代码 SHA256 被改"),
    ("data_generation", mutate_data_generation, "registry 数据世代被改"),
    ("groups_input_hash", mutate_groups_hash, "groups 清单哈希被改"),
)

BINDING_MUTATIONS = {"code_sha256", "data_generation", "groups_input_hash"}


def axis_proof_probe(
    registry: dict[str, Any],
    entry: dict[str, Any],
    prod: dict[str, Any],
    verify_dir: Path,
) -> dict[str, Any]:
    """有效交易域证明的对照：正向用**真实**观测，负向逐一构造必须被拒。

    正向: 直接取比较器实跑落下的 ``compare_<group>.json`` 里的 ``axis_proof``
    （真实 ``production_load_axes`` / ``batch_matrix_window``），要求 ``proven=true``。
    负向: 在同一份真实观测上做三处单点破坏，每一处都必须让证明失效，
    否则这条豁免就是橡皮图章。
    """
    axis_map: dict[str, int] = (registry.get("slice_axis") or {}).get("tradable_days_by_symbol") or {}
    compare_path = verify_dir / f"compare_{entry['group']}.json"
    if not axis_map:
        return {"available": False, "reason": "registry 无 slice_axis"}
    if not compare_path.exists():
        return {"available": False, "reason": f"缺比较产物: {compare_path}"}

    real = json.loads(compare_path.read_text(encoding="utf-8")).get("axis_proof") or {}
    real_calls = [dict(call) for call in real.get("production_load_axes") or []]
    if not real_calls:
        return {"available": False, "reason": "比较产物未记录真实装载轴"}

    symbols = list(axis_map)
    tradable_symbols = [symbol for symbol in symbols if axis_map[symbol] > 0]
    if not tradable_symbols:
        return {"available": False, "reason": "正式区间内没有可交易证券, 无法构造负向样本"}

    def probe(
        visible: list[str],
        calls: list[dict[str, Any]] | None = None,
        production: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        recorder = v2.MatrixLoadRecorder()
        recorder.visible = [frozenset(visible)]
        recorder.calls = calls if calls is not None else real_calls
        return v2.build_axis_proof(entry, production if production is not None else prod, recorder, registry)

    # 正向: 真实观测 + 真实可见集合（以批量并集轴重放，因为比较产物只存摘要不存名单）
    positive = probe(symbols)
    positive_ok = bool(real.get("proven")) and bool(positive["proven"])

    # 负向 1: 把一个「有可交易日」的证券从生产可见集里摘掉 → 变成批量独有且有可交易日
    dropped = tradable_symbols[0]
    neg_symbol = probe([symbol for symbol in symbols if symbol != dropped])

    # 负向 2: 生产装载窗口越出批量并集窗口 → shape[0] 差异无法解释
    out_of_window = [dict(call) for call in real_calls]
    out_of_window[0]["window"] = ["1990-01-01", "1991-01-01"]
    neg_window = probe(symbols, calls=out_of_window)

    # 负向 3: 声称生产未走共享矩阵路径
    not_shared = dict(prod)
    not_shared["shared_market_data"] = False
    neg_shared = probe(symbols, production=not_shared)

    negatives = {
        "batch_only_tradable_symbol": {
            "proven": neg_symbol["proven"],
            "reasons": neg_symbol["reasons"],
            "dropped_symbol": dropped,
            "dropped_symbol_tradable_days": axis_map[dropped],
            "detected": not neg_symbol["proven"],
        },
        "production_window_outside_batch": {
            "proven": neg_window["proven"],
            "reasons": neg_window["reasons"],
            "detected": not neg_window["proven"],
        },
        "production_not_shared_matrix": {
            "proven": neg_shared["proven"],
            "reasons": neg_shared["reasons"],
            "detected": not neg_shared["proven"],
        },
    }
    ok = positive_ok and all(item["detected"] for item in negatives.values())
    return {
        "available": True,
        "compare_report": str(compare_path),
        "real_axis_proof": {
            "proven": real.get("proven"),
            "reasons": real.get("reasons"),
            "batch_matrix_window": real.get("batch_matrix_window"),
            "production_load_axes": real_calls,
            "n_batch_only_symbols": real.get("n_batch_only_symbols"),
            "n_production_only_symbols": real.get("n_production_only_symbols"),
            "batch_only_with_tradable_days_in_official_span": real.get(
                "batch_only_with_tradable_days_in_official_span"
            ),
            "window_covered_by_batch": real.get("window_covered_by_batch"),
        },
        "positive_proven": positive_ok,
        "positive_reasons": positive["reasons"],
        "negatives": negatives,
        "ok": ok,
    }


def _binding_runtime() -> SimpleNamespace:
    """绑定校验需要 strategy_engine（取策略文件哈希与 override），不装载矩阵。"""
    _repo, service, strategy_engine, _wf = v2.build_runtime()
    return SimpleNamespace(engine=service.engine, strategy_engine=strategy_engine)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v2 比较器的负向变异检验")
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--verify-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    registry_path = args.registry.resolve()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    verify_dir = args.verify_dir or (registry_path.parent / "verify_v2")
    out_path = args.out or (verify_dir / "mutation-report.json")

    group_entry = registry["runs"][0]
    capture_path = verify_dir / f"prod_{group_entry['group']}.json"
    if not capture_path.exists():
        print(json.dumps({"error": f"缺生产载荷快照: {capture_path}"}, ensure_ascii=False))
        return 1
    production = json.loads(capture_path.read_text(encoding="utf-8"))
    trading_days = load_trading_days(registry)
    groups_path = Path(registry["inputs"]["groups_file"]["path"])
    if not groups_path.is_absolute():
        groups_path = (REPO / groups_path).resolve()
    groups = run_batch.load_groups(groups_path)
    binding_rt = _binding_runtime()

    baseline = compare_core(group_entry, production, registry, trading_days)
    results: list[dict[str, Any]] = []
    undetected: list[str] = []

    for name, mutate, description in MUTATIONS:
        entry_copy = copy.deepcopy(group_entry)
        prod_copy = copy.deepcopy(production)
        registry_copy = copy.deepcopy(registry)
        mutate(entry_copy, prod_copy, registry_copy)
        if name in BINDING_MUTATIONS:
            violations = v2.check_registry_binding(
                registry_copy,
                v2.binding_snapshot(groups_path, groups, binding_rt, registry_copy["slice"]["asset_type"]),
                "mutation",
            )
            detected = bool(violations)
            detail = {"violations": violations}
        else:
            report = compare_core(entry_copy, prod_copy, registry_copy, trading_days)
            detected = report["n_result_diffs"] > 0
            detail = {
                "n_result_diffs": report["n_result_diffs"],
                "first": report["result_diffs"][:3],
            }
        results.append({"mutation": name, "description": description, "detected": detected, **detail})
        if not detected:
            undetected.append(name)

    axis = axis_proof_probe(registry, group_entry, production, verify_dir)
    payload = {
        "schema": "batch-mutation-report/1",
        "registry": str(registry_path),
        "production_capture": str(capture_path),
        "group": group_entry["group"],
        "baseline": {
            "n_result_diffs": baseline["n_result_diffs"],
            "clean": baseline["n_result_diffs"] == 0,
            "first": baseline["result_diffs"][:5],
        },
        "n_mutations": len(MUTATIONS),
        "n_detected": len(MUTATIONS) - len(undetected),
        "undetected": undetected,
        "axis_proof": axis,
        "mutations": results,
    }
    ok = payload["baseline"]["clean"] and not undetected and axis.get("ok", False)
    payload["ok"] = ok
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "baseline_clean": payload["baseline"]["clean"],
                "n_mutations": payload["n_mutations"],
                "n_detected": payload["n_detected"],
                "undetected": undetected,
                "axis_proof_ok": axis.get("ok"),
                "ok": ok,
                "report": str(out_path),
            },
            ensure_ascii=False,
            default=str,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
