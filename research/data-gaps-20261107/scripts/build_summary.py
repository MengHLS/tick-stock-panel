#!/usr/bin/env python
"""把 results/check_*.json 汇总成一份机器可读的 results/summary.json。

字段契约（供其他成员/流水线直接消费）：
  families[].family / status(blocked|partial|available) / verdict(确证|未知)
  families[].evidence_path     —— 该判定的证据 JSON（目录相对路径）
  families[].evidence_command  —— 可原样重跑复现该 JSON 的命令
  families[].exit_code         —— 该命令的退出码（0 = 命令跑通，不代表数据可用）
  families[].key_sql           —— 该判定所依赖的第一条关键 SQL（可直接在 DuckDB 跑）
  families[].needs             —— 补齐这项分别需要什么

用法（项目根目录为工作目录）：
  PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/data-gaps-20261107/scripts/build_summary.py

退出码：0 = 写出成功；3 = 有 check_*.json 缺失。
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RESEARCH_DIR = SCRIPT_DIR.parent
REPO_ROOT = RESEARCH_DIR.parents[1]
RESULTS_DIR = RESEARCH_DIR / "results"
REPO_REL = Path("research") / RESEARCH_DIR.name

CHECK_IDS = ("industry", "index", "etf", "short", "universe616")

# 退出码从 verify_delivery.py 实际子进程记录读取，不预设成功。


def git(*args: str) -> str:
    try:
        out = subprocess.run(("git", *args), cwd=REPO_ROOT, capture_output=True,
                             text=True, encoding="utf-8", errors="replace", check=False)
        return out.stdout.strip()
    except OSError:
        return ""


def load(cid: str) -> dict:
    p = RESULTS_DIR / f"check_{cid}.json"
    if not p.exists():
        print(f"[MISS] {p}", file=sys.stderr)
        raise SystemExit(3)
    return json.loads(p.read_text(encoding="utf-8"))


def load_recheck() -> dict | None:
    """第二条独立路径的可选证据；不存在则记 null（不阻断汇总）。"""
    p = RESULTS_DIR / "independent_recheck.json"
    if not p.exists():
        print(f"[WARN] {p} missing; run independent_recheck.py first", file=sys.stderr)
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    checks = {cid: load(cid) for cid in CHECK_IDS}
    log_path = RESULTS_DIR / "execution_log.json"
    runs = {x["id"]: x for x in json.loads(log_path.read_text(encoding="utf-8"))["runs"]}
    required = (*CHECK_IDS, "independent_recheck")
    if any(cid not in runs or runs[cid]["exit_code"] != 0 for cid in required):
        print("[FAIL] Missing or failed actual verification stage", file=sys.stderr)
        return 3
    families = []
    for cid in CHECK_IDS:
        c = checks[cid]
        sqls = c.get("sql_log") or []
        families.append({
            "family": c["family"],
            "id": cid,
            "status": c["status"],
            "verdict": c["verdict"],
            "partial_capability": c.get("partial_capability"),
            "one_line": c["conclusion"],
            "evidence_path": f"{REPO_REL.as_posix()}/results/check_{cid}.json",
            "evidence_command": (
                "cd C:/work/sourcecode/tick-stock-panel && PYTHONUTF8=1 "
                "backend/.venv/Scripts/python.exe "
                f"{REPO_REL.as_posix()}/scripts/audit_data_gaps.py --check {cid}"
            ),
            "exit_code": runs[cid]["exit_code"],
            "execution_log": f"{REPO_REL.as_posix()}/results/execution_log.json",
            "output_path": runs[cid]["output_path"],
            "remediation": "可补" if cid == "universe616" else "不可补",
            "remediation_scope": "仅澄清统计口径" if cid == "universe616" else "限本次检查的现存本地文件与历史回测区间",
            "external_free_history": "未验证" if cid != "universe616" else "不适用",
            "purchase_required": "未知" if cid != "universe616" else "不需要",
            "key_sql": sqls[0] if sqls else None,
            "sql_count": len(sqls),
            "code_evidence": c.get("code_evidence") or [],
            "unknown": c.get("unknown") or [],
            "needs": c.get("needs_without_purchase"),
            "evidence_paths": c.get("evidence_paths") or [],
        })

    u = checks["universe616"]
    facts = {f["name"]: f["value"] for f in u.get("facts", [])}
    dispute = {
        "id": "universe616",
        "verdict": u["verdict"],
        "settlement": u.get("settlement") or "616 可精确复现＝无复权因子事件行的证券数；不是「无因子数据」",
        "definition": {
            "616": "面板 5,813 只中在 adj_factor 里没有任何一行的证券数（5,813 − 5,197）",
            "78": "元数据 5,536 只中在日线面板 5,813 里完全没有日线的证券数",
            "355": "日线面板中有、元数据中没有的证券数（北交所 92x）",
            "236": "日线面板中四张财务表都没有任何记录的证券数",
            "663": "无法复现（本审计候选口径 236/313/266/628/802/1,079 均不等于 663）",
        },
        "cross_check": {
            "matrix": facts.get("缺表矩阵：面板 5,813 只 / 元数据 5,536 只 对各数据集的缺口"),
            "panel_vs_adj_factor_by_prefix": facts.get("616 只无复权因子行的证券（按代码前缀）"),
            "adjusted_equals_raw": facts.get("616 只的 复权价 vs 原始价 一致性"),
            "sse_star_daily_count_20261106": facts.get("2026-11-06 当日各板块证券数"),
        },
        "sum_check": {
            "78+355+236": 669,
            "note": "669 ≠ 616：三个数字口径互不相同，不是同一分解，不能互相印证",
        },
        "evidence_path": f"{REPO_REL.as_posix()}/results/check_universe616.json",
        "provenance": [
            "docs/research/parallel-data-20261106/DATA_QUALITY.md:74 —— 原始表述是「完全没有因子行」",
            "research/parallel-data-20261106/audit_data_quality.py:1171-1205 —— panel_symbols_without_factor 的计算点",
        ],
    }

    summary = {
        "schema_version": "1",
        "topic": "data-gaps-20261107",
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "generated_by": "research/data-gaps-20261107/scripts/build_summary.py",
        "data_root": checks["universe616"].get("data_root"),
        "repo": str(REPO_ROOT).replace("\\", "/"),
        "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_head": git("rev-parse", "--short", "HEAD"),
        "status_legend": {
            "blocked": "不能支撑该族任何可信（无前视）检验；若存在有限可用切片，记在 partial_capability",
            "partial": "存在可用的有限切片，但不足以支持该族结论",
            "available": "可做（本目录内仅 616 口径定论属此档，它本身不是策略族）",
        },
        "verdict_legend": {"确证": "已用可重跑命令本地复核", "未知": "无法用本地数据判定"},
        "families": families,
        "dispute_616": dispute,
        "independent_recheck": (
            None if (rc := load_recheck()) is None else {
                "role": "第二条独立路径：不复用 audit_data_gaps.py 任何代码，独立 DuckDB 会话重算",
                "all_match": rc.get("all_match"),
                "diffs": rc.get("diffs"),
                "got": rc.get("got"),
                "evidence_path": f"{REPO_REL.as_posix()}/results/independent_recheck.json",
                "evidence_command": (
                    "cd C:/work/sourcecode/tick-stock-panel && PYTHONUTF8=1 "
                    f"backend/.venv/Scripts/python.exe {REPO_REL.as_posix()}/scripts/independent_recheck.py"
                ),
                "exit_code": runs["independent_recheck"]["exit_code"],
                "exit_code_on_diff": 2,
            }
        ),
        "reproduce_all": [
            "cd C:/work/sourcecode/tick-stock-panel",
            *["PYTHONUTF8=1 backend/.venv/Scripts/python.exe "
              f"{REPO_REL.as_posix()}/scripts/verify_delivery.py {stage}"
              for stage in (*CHECK_IDS, "independent_recheck", "build_summary")],
        ],
    }
    out = RESULTS_DIR / "summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] wrote {out}")
    for f in families:
        print(f"  {f['id']:12s} status={f['status']:9s} verdict={f['verdict']} exit={f['exit_code']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
