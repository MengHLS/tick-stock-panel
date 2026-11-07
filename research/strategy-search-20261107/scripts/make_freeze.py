#!/usr/bin/env python
"""生成/重写 FREEZE.json：冻结清单（sha256 + mtime + 大小）。

用法：python scripts/make_freeze.py
不跑回测，只读文件元数据。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DOCS = ["PROTOCOL.md", "STRATEGIES.md", "E1_E2_SPEC.md", "DATA-BOUNDARY.md", "README.md"]
CODE = ["scripts/common.py", "scripts/run_suite.py", "scripts/judge_e2.py", "scripts/make_freeze.py"]
RESULTS = ["results/registry.json", "results/e2_judgement.json"]


def info(rel: str) -> dict:
    p = ROOT / rel
    if not p.exists():
        return {"path": rel, "exists": False}
    data = p.read_bytes()
    return {
        "path": rel,
        "exists": True,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
    }


def main() -> None:
    reg = ROOT / "results" / "registry.json"
    meta = {}
    if reg.exists():
        meta = json.loads(reg.read_text(encoding="utf-8")).get("meta", {})

    out = {
        "schema": "strategy-search-freeze/1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "protocol_version": "v2",
        "freeze_rule": "确认性 run 需：run mtime > PROTOCOL.md mtime；代码 sha256 与本文件一致；且策略已在 STRATEGIES.md 登记",
        "n_trials": {
            "baseline_v0": 12,
            "prior_search_same_project": 3,
            "total": 15,
            "basis": "PROTOCOL.md §6.2；prior = research/strategy-reliability-20261106 T03 的 3 条固定规则",
            "policy": "只增不减；参数邻域每格 +1；情景间择优 +2",
        },
        "dsr": {"sr_variance_daily": 0.000818, "sr0_daily": 0.0506, "sr0_annual": 0.804, "threshold": 0.95},
        "lockbox": {
            "burned_history": ["2019-07-01", "2026-10-30"],
            "burned_note": "T1+T2 已全部被观测（含逐年表），不得重新称为样本外",
            "prospective_start": "2026-11-09",
            "min_quarters": 4,
            "earliest_confirmatory_date": "2027-09-30",
        },
        "panel": {
            "rows": meta.get("panel_rows"),
            "symbols": meta.get("panel_symbols"),
            "dates": meta.get("panel_dates"),
            "hash": meta.get("panel_hash"),
            "eval_window": [meta.get("eval_start"), meta.get("eval_end")],
            "git_head": meta.get("head"),
        },
        "docs": [info(x) for x in DOCS],
        "code": [info(x) for x in CODE],
        "results": [info(x) for x in RESULTS],
        "verification": {
            "runs_in_registry": len(json.loads(reg.read_text(encoding="utf-8")).get("runs", {})) if reg.exists() else 0,
            "all_runs_exploratory": True,
            "reason": "PROTOCOL.md v1 mtime 23:25:33 > 首个 run 22:51:55；common.py 于 23:07:02 中途修改",
            "reproduced_on_final_code": ["S07_xs_lowvol_60d@10"],
        },
        "e2_judgement": None,
    }

    judgement = ROOT / "results" / "e2_judgement.json"
    if judgement.exists():
        j = json.loads(judgement.read_text(encoding="utf-8"))
        out["e2_judgement"] = {"summary": j.get("summary"), "exit_code": j.get("exit_code")}

    dst = ROOT / "FREEZE.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written {dst} ({dst.stat().st_size} bytes)")
    for d in out["docs"]:
        print(f"  {d['path']:22s} {d.get('bytes', 0):7d} B  {d.get('sha256', 'MISSING')[:16]}  {d.get('mtime', '')}")


if __name__ == "__main__":
    main()
