#!/usr/bin/env python
"""一致性验证: 批量底座 vs 生产单跑 (WalkForwardService.run)。

做法: 用 registry 里同一组的配置, 走**生产现有入口**
``WalkForwardService.run(cfg, continuous_account=True)`` 独立单跑一遍
(它自己按矩阵原生路径构建共享矩阵), 然后与 ``run_batch.py`` 的结果逐字段比对,
差异必须为 0。

同时这也是「matrix_native + 共享基础矩阵 + 连续回放」的端到端留证:
``continuous_account.duplicate_dates`` 与 ``invariants.timeline_complete``
由生产代码 (``WalkForwardService._run_continuous_oos``) 产出, 批量侧的值只作为对照。

用法::

    backend/.venv/Scripts/python.exe research/batch-backtest-framework-20261107/verify_batch.py \
        --registry research/batch-backtest-framework-20261107/out/registry.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

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

#: 比较时跳过的键: 生产连续回放会覆盖 total_return (改成段收益并另加账户累计),
#: 以及所有纯计时字段 (墙钟时间天然不同, 不是结果差异)。
#: summary.continuous_account 也跳过: 生产把整段 equity_curve/trades 嵌进 summary,
#: 批量侧用 sha256 摘要代替 (内存裁剪), 那段已在连续账户小节单独逐字段比对。
SKIP_KEYS = {
    "total_return",
    "account_total_return_cumulative",
    "timing_ms",
    "shared_prepare_timing_ms",
    "matrix_data_cache_timing_ms",
    "elapsed_ms",
    "elapsed_s",
    "loaded_at",
    "started_at",
    "finished_at",
    "cache_path",
    "cache_timing_ms",
    "continuous_account",
}

#: 遥测键 (机器状态, 不是策略结果): 两侧装载窗口/进程缓存不同, 这些值必然不同。
#: 逐个列名而不是通配, 保证新出现的结果字段默认落在「必须为 0」那一侧 (fail-closed)。
TELEMETRY_KEYS = {
    "matrix_compute_cache",
    "shared_market_data_bytes",
    "market_matrix_shape",
    "market_matrix_bytes",
    "matrix_data_cache_hit",
    "matrix_data_cache_status",
    "panel_rows",
    "panel_columns",
}


def is_telemetry(field: str) -> bool:
    """路径段命中遥测名单即视为遥测; 段名先去下标 (matrix_shape[1] -> matrix_shape)。"""
    for segment in field.split("."):
        name = segment.split("[", 1)[0]
        if name in TELEMETRY_KEYS:
            return True
    return False


def diff_values(path: str, left: Any, right: Any, out: list[dict[str, Any]]) -> None:
    """递归比对, 差异写入 out (差异即失败, 不做容差)。"""
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            if key in SKIP_KEYS:
                continue
            sub = f"{path}.{key}" if path else key
            if key not in left or key not in right:
                out.append(
                    {
                        "field": sub,
                        "left": left.get(key, "<missing>"),
                        "right": right.get(key, "<missing>"),
                        "kind": "missing_key",
                    }
                )
                continue
            diff_values(sub, left[key], right[key], out)
        return
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            out.append(
                {"field": f"{path}.length", "left": len(left), "right": len(right), "kind": "length"}
            )
            return
        for index, (l_item, r_item) in enumerate(zip(left, right, strict=True)):
            diff_values(f"{path}[{index}]", l_item, r_item, out)
        return
    if isinstance(left, bool) or isinstance(right, bool):
        if bool(left) != bool(right):
            out.append({"field": path, "left": left, "right": right, "kind": "value"})
        return
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if float(left) != float(right):
            out.append(
                {
                    "field": path,
                    "left": left,
                    "right": right,
                    "kind": "value",
                    "delta": float(left) - float(right),
                }
            )
        return
    if left != right:
        out.append({"field": path, "left": left, "right": right, "kind": "value"})


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
    return repo, service, strategy_engine, WalkForwardService(optimizer, service, strategy_engine)


def compare_entry(entry: dict[str, Any], production: dict[str, Any], group_cfg: dict[str, Any]) -> dict[str, Any]:
    diffs: list[dict[str, Any]] = []

    # 1) fold 边界
    prod_folds = [
        {
            "index": rec["index"],
            "train_start": rec["train_start"],
            "train_end": rec["train_end"],
            "test_start": rec["test_start"],
            "test_end": rec["test_end"],
        }
        for rec in production.get("folds", [])
    ]
    diff_values("folds", entry["folds"], prod_folds, diffs)

    # 2) 逐折 IS/OOS
    prod_by_index = {rec["index"]: rec for rec in production.get("folds", [])}
    for record in entry["oos_folds"]:
        prod = prod_by_index.get(record["index"])
        if prod is None:
            diffs.append(
                {
                    "field": f"oos_folds[{record['index']}]",
                    "left": "present",
                    "right": "<missing>",
                    "kind": "missing_fold",
                }
            )
            continue
        prefix = f"oos_folds[{record['index']}]"
        diff_values(f"{prefix}.is_score", record["is_score"], prod.get("is_score"), diffs)
        diff_values(
            f"{prefix}.oos_objective", record["oos_objective"], prod.get("oos_objective"), diffs
        )
        diff_values(
            f"{prefix}.trade_gate_ok", record["trade_gate_ok"], prod.get("trade_gate_ok"), diffs
        )
        diff_values(
            f"{prefix}.best_params", record["best_params"], prod.get("best_params"), diffs
        )
        diff_values(f"{prefix}.oos_stats", record["oos_stats"], prod.get("oos_stats"), diffs)

    # 3) 连续账户 (生产值是权威: duplicate_dates / timeline_complete 由它产出)
    prod_account = production.get("continuous_account") or {}
    batch_account = entry["continuous_account"]
    diff_values(
        "continuous_account.duplicate_dates",
        batch_account.get("duplicate_dates"),
        prod_account.get("duplicate_dates"),
        diffs,
    )
    diff_values(
        "continuous_account.n_folds_replayed",
        batch_account.get("n_folds_replayed"),
        prod_account.get("n_folds_replayed"),
        diffs,
    )
    diff_values(
        "continuous_account.final_equity",
        batch_account.get("final_equity"),
        prod_account.get("final_equity"),
        diffs,
    )
    diff_values(
        "continuous_account.invariants",
        batch_account.get("invariants"),
        prod_account.get("invariants"),
        diffs,
    )
    diff_values(
        "continuous_account.stats", batch_account.get("stats"), prod_account.get("stats"), diffs
    )
    prod_boundaries = [
        {
            "index": b["index"],
            "equity_start": b["equity_start"],
            "equity_end": b["equity_end"],
            "segment_return": b["segment_return"],
            "carried_in_positions": b["carried_in_positions"],
            "carried_out_positions": b["carried_out_positions"],
        }
        for b in prod_account.get("boundaries", [])
    ]
    batch_boundaries = [
        {
            "index": b["index"],
            "equity_start": b["equity_start"],
            "equity_end": b["equity_end"],
            "segment_return": b["segment_return"],
            "carried_in_positions": b["carried_in_positions"],
            "carried_out_positions": b["carried_out_positions"],
        }
        for b in batch_account.get("boundaries", [])
    ]
    diff_values("continuous_account.boundaries", batch_boundaries, prod_boundaries, diffs)
    diff_values(
        "continuous_account.trade_lifecycle",
        batch_account.get("trade_lifecycle"),
        prod_account.get("trade_lifecycle"),
        diffs,
    )

    # 4) 聚合摘要
    prod_summary = production.get("summary") or {}
    diff_values("summary", entry["oos_summary"], prod_summary, diffs)

    reported = {
        "group": entry["group"],
        "run_id": entry["run_id"],
        "strategy_id": entry["strategy_id"],
        "params": entry["params"],
        "n_diffs": len(diffs),
        "n_result_diffs": len([d for d in diffs if not is_telemetry(d["field"])]),
        "n_telemetry_diffs": len([d for d in diffs if is_telemetry(d["field"])]),
        "diffs": diffs[:80],
        "result_diffs": [d for d in diffs if not is_telemetry(d["field"])],
        "telemetry_diffs": [d for d in diffs if is_telemetry(d["field"])],
        "production": {
            "duplicate_dates": prod_account.get("duplicate_dates"),
            "timeline_complete": (prod_account.get("invariants") or {}).get("timeline_complete"),
            "timeline": prod_account.get("timeline"),
            "n_folds_replayed": prod_account.get("n_folds_replayed"),
            "final_equity": prod_account.get("final_equity"),
            "shared_market_data": bool(
                (production.get("folds") or [{}])[0].get("oos_stats", {}).get("shared_market_data")
            ),
            "matrix_data_cache_status": [
                (rec.get("oos_stats") or {}).get("matrix_data_cache_status")
                for rec in production.get("folds", [])
            ],
        },
        "batch": {
            "duplicate_dates": batch_account.get("duplicate_dates"),
            "timeline_complete": (batch_account.get("invariants") or {}).get("timeline_complete"),
            "final_equity": batch_account.get("final_equity"),
        },
        "config": group_cfg,
    }
    return reported


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="批量底座 vs 生产单跑逐字段一致性验证")
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--group", action="append", default=None, help="只验指定组名 (可多次)")
    parser.add_argument("--max-workers", type=int, default=1, help="生产单跑的优化器并发 (固定 1 保证可比)")
    args = parser.parse_args(argv)

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    out_dir = args.registry.parent
    repo, _service, _strategy_engine, wf = build_runtime()
    slice_info = registry["slice"]
    settings_info = registry["settings"]
    start = date.fromisoformat(slice_info["start"])
    end = date.fromisoformat(slice_info["end"])
    trading_days = repo.list_enriched_dates(start, end, asset_type=slice_info["asset_type"])

    entries = registry["runs"]
    if args.group:
        wanted = set(args.group)
        entries = [e for e in entries if e["group"] in wanted]
        missing = wanted - {e["group"] for e in entries}
        if missing:
            raise SystemExit(f"registry 里没有这些组: {sorted(missing)}")

    reports = []
    exit_code = 0
    for entry in entries:
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
        print(json.dumps({"verify": entry["group"], "phase": "production_run_start"}, ensure_ascii=False), flush=True)
        production = wf.run(cfg)
        report = compare_entry(entry, production, {
            "strategy_id": cfg.strategy_id,
            "param_grid": cfg.param_grid,
            "train_days": cfg.train_days,
            "test_days": cfg.test_days,
            "step_days": cfg.step_days,
            "objective": cfg.objective,
            "min_trades_oos": cfg.min_trades_oos,
            "continuous_account": cfg.continuous_account,
            "trading_days": len(cfg.trading_days),
        })
        reports.append(report)
        (out_dir / f"compare_{entry['group']}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "group": report["group"],
                    "n_result_diffs": report["n_result_diffs"],
                    "n_telemetry_diffs": report["n_telemetry_diffs"],
                    "production_duplicate_dates": report["production"]["duplicate_dates"],
                    "production_timeline_complete": report["production"]["timeline_complete"],
                    "production_shared_market_data": report["production"]["shared_market_data"],
                    "result_diffs": report["result_diffs"][:5],
                    "telemetry_diffs": report["telemetry_diffs"][:5],
                },
                ensure_ascii=False,
                default=str,
            ),
            flush=True,
        )
        # 只有「结果字段」差异才让验证失败; 遥测差异逐条列出供人工核对, 不计入结论。
        if report["n_result_diffs"]:
            exit_code = 1

    (out_dir / "compare_summary.json").write_text(
        json.dumps(
            {
                "registry": str(args.registry),
                "n_groups": len(reports),
                "total_result_diffs": sum(r["n_result_diffs"] for r in reports),
                "total_telemetry_diffs": sum(r["n_telemetry_diffs"] for r in reports),
                "telemetry_keys": sorted(TELEMETRY_KEYS),
                "groups": [
                    {
                        "group": r["group"],
                        "n_result_diffs": r["n_result_diffs"],
                        "n_telemetry_diffs": r["n_telemetry_diffs"],
                        "production_duplicate_dates": r["production"]["duplicate_dates"],
                        "production_timeline_complete": r["production"]["timeline_complete"],
                    }
                    for r in reports
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "total_result_diffs": sum(r["n_result_diffs"] for r in reports),
                "total_telemetry_diffs": sum(r["n_telemetry_diffs"] for r in reports),
                "groups": len(reports),
            },
            ensure_ascii=False,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
