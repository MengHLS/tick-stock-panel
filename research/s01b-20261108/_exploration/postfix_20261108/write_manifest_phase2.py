"""生成 manifest_phase2.json：18 臂 C 口径三产物 sha + 复现命令 + 脚本 sha + 确定性/对照结论。"""
from __future__ import annotations

import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
PARENT = HERE.parent
PROJECT = PARENT.parents[1]
RESULTS = HERE / "results_all"
RERUN = HERE / "_determinism_rerun"
D_ROOT = PARENT / "results"
ENGINE = PROJECT / "backend" / "app" / "backtest" / "engine.py"

PY = r"backend\.venv\Scripts\python.exe"
DELIVERABLES = ["METRICS_D_vs_C_20261108.md", "delta_arms.json", "metrics_table_C_20261108.md",
                "REPORT_phase2_20261108.md", "verify_phase2_result.txt", "stale_tokens_scan.json"]
SCRIPTS = ["run_all_arms.py", "build_delta.py", "verify_phase2.py", "scan_stale_tokens.py"]


def sha(p: pathlib.Path) -> str | None:
    if not p.exists():
        return None
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def repro(tag: str) -> str:
    d = json.loads((RESULTS / tag / "result.json").read_text(encoding="utf-8"))
    ec = d["effective_config"]
    sid = d["strategy_id"]
    sdir = ec["strategy_file"]["path"]
    parts = [
        PY,
        r"research\s01b-20261108\postfix_20261108\run_all_arms.py",
        f"--only {tag}",
    ]
    note = (f"等价 prod_run_s01b.py 命令: {PY} research\\s01b-20261108\\prod_run_s01b.py "
            f"--strategy-id {sid} --tag {tag} --strategies-dir \"{sdir}\""
            + (" --gross" if d["gross"] else (f" --slippage-bps {d['slippage_bps']:g}"
                                              if d["slippage_bps"] not in (0.0, 10.0) else ""))
            + (f" --start {d['start']} --end {d['end']}"
               if (d["start"], d["end"]) != ("2019-07-01", "2026-10-30") else ""))
    return {"driver": " ".join(parts),
            "equivalent_prod_run": note,
            "batch_repro_all_18": f"{PY} research\\s01b-20261108\\postfix_20261108\\run_all_arms.py",
            "verify": f"{PY} research\\s01b-20261108\\postfix_20261108\\verify_phase2.py"}


def main() -> int:
    delta = json.loads((HERE / "delta_arms.json").read_text(encoding="utf-8"))
    dmap = {a["tag"]: a for a in delta["arms"]}
    arms = []
    for tag in [a["tag"] for a in delta["arms"]]:
        d = json.loads((RESULTS / tag / "result.json").read_text(encoding="utf-8"))
        st = d["stats"]
        m = dmap[tag]["metrics_C"]
        files = {}
        for name in ("trades.parquet", "equity.parquet", "drawdown.parquet", "result.json"):
            files[name] = {
                "C_sha256": sha(RESULTS / tag / name),
                "rerun_sha256": sha(RERUN / tag / name),
                "D_sha256": sha(D_ROOT / tag / name),
            }
        arms.append({
            "tag": tag,
            "strategy_id": d["strategy_id"],
            "strategies_dir": d["effective_config"]["strategy_file"]["path"],
            "strategy_file_sha256": d["effective_config"]["strategy_file"]["sha256"],
            "start": d["start"], "end": d["end"],
            "slippage_bps": d["slippage_bps"], "gross": d["gross"],
            "finalize_open_at_end": dmap[tag]["finalize_open_at_end"],
            "error": d["error"],
            "n_trades": st["n_trades"],
            "completed_trade_count": st["completed_trade_count"],
            "open_at_end_count": st["open_at_end_count"],
            "final_equity": round(st["final_equity"], 2),
            "total_return": round(st["total_return"], 6),
            "annual_return": round(st["annual_return"], 6),
            "max_drawdown": round(st["max_drawdown"], 6),
            "win_rate": round(st["win_rate"], 6),
            "median_pnl": round(st["median_pnl"], 6),
            "avg_holding_days": round(st["avg_holding_days"], 3),
            "oos_annual": m.get("oos_annual"), "oos_mdd": m.get("oos_mdd"),
            "execution": st.get("execution"),
            "artifacts": files,
            "determinism_parquet_identical": all(
                files[n]["C_sha256"] == files[n]["rerun_sha256"]
                for n in ("trades.parquet", "equity.parquet", "drawdown.parquet")),
            "vs_D": {
                "status": dmap[tag]["status"],
                "trades_same": dmap[tag]["parquet_sha256"]["trades.parquet"]["same"],
                "equity_same": dmap[tag]["parquet_sha256"]["equity.parquet"]["same"],
                "execution_same": dmap[tag]["execution_same"],
                "stats_diff_keys": sorted(dmap[tag]["stats_diff"].keys()),
            },
            "repro": repro(tag),
        })
    manifest = {
        "batch": "s01b/postfix_20261108/phase2/results_all",
        "purpose": "把 research/s01b-20261108/results/ 下全部臂在当前引擎（末日结算修复后）按原参数重跑",
        "engine": {"path": str(ENGINE), "bytes": ENGINE.stat().st_size, "sha256": sha(ENGINE)},
        "conclusion": {
            "arms_total": len(arms),
            "arms_changed_by_C": sum(1 for a in arms if a["vs_D"]["status"] == "CHANGED"
                                     and a["vs_D"]["trades_same"] is False),
            "arms_byte_identical_to_D": sum(1 for a in arms
                                            if a["vs_D"]["trades_same"] and a["vs_D"]["equity_same"]),
            "why_unchanged": "18 臂策略文件全部声明 finalize_open_at_end=True（末日强制清算分支），"
                             "按契约该分支本就不受末日结算缺陷影响；修复只改「不尝试清算」时的记账路径。",
            "smoke_a0_note": "唯一 stats 差异是 market_matrix_shape/bytes（59×5197 → 59×5811，数据根扩容），"
                             "trades/equity 仍逐字节相同。",
        },
        "scripts": {n: {"bytes": (HERE / n).stat().st_size, "sha256": sha(HERE / n)}
                    for n in SCRIPTS if (HERE / n).exists()},
        "deliverables": {n: {"bytes": (HERE / n).stat().st_size, "sha256": sha(HERE / n)}
                         for n in DELIVERABLES if (HERE / n).exists()},
        "anchor_six": delta["anchor_six"],
        "arms": arms,
    }
    (HERE / "manifest_phase2.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[manifest] arms={len(arms)} "
          f"byte_identical={manifest['conclusion']['arms_byte_identical_to_D']} "
          f"changed_artifacts={manifest['conclusion']['arms_changed_by_C']}")
    print(f"[manifest] {HERE / 'manifest_phase2.json'} {(HERE / 'manifest_phase2.json').stat().st_size}B "
          f"sha256={sha(HERE / 'manifest_phase2.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
