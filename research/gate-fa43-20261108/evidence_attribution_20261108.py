"""`backend/app/api/backtest.py` 那行改动的归属 + 必要性证据（2026-11-08）。

跑法（仓库根）：
    backend/.venv/Scripts/python.exe research/gate-fa43-20261108/evidence_attribution_20261108.py

三件事，全部机械可复跑：
  A. 归属：把上一轮 `patch_task2.py` 的 EDITS 当数据读出来，逐条验证
     「`old` 在 HEAD 字节里恰好出现 1 次」+「`new` 在工作区字节里恰好出现 1 次」，
     并给出脚本与目标文件的 mtime 指纹（同一次写盘循环的两个文件 mtime 相差 2 ms）。
  B. 必要性：目录 110 > 陈旧上限 96 → 「整份目录可提交」这条既有能力被拒；
     再用 pydantic 直接量 110 名 / 96 / 200 / 201 三组边界。
  C. 越界面：该文件 8 处 `min_length`/`max_length` 逐行与 HEAD 对照，只有第 205 行变。

只读：不写任何业务文件、不碰 `docs/**`。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

PATCH = Path(__file__).with_name("patch_task2.py")
TARGET_REL = "app/api/backtest.py"
TARGET = BACKEND / TARGET_REL
HERE = Path(__file__).parent


def git(*args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, check=True
    )
    return out.stdout.decode("utf-8", "replace")


def lf(text: str) -> str:
    return text.replace("\r\n", "\n")


def head_bytes(rel: str) -> str:
    return lf(git("show", f"HEAD:backend/{rel}"))


def mtime_row(path: Path) -> dict:
    st = path.stat()
    return {
        "path": str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path),
        "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
        "mtime_ns": st.st_mtime_ns,
        "bytes": st.st_size,
    }


def load_edits() -> list[tuple[str, Path, str, str]]:
    spec = importlib.util.spec_from_file_location("_patch_task2", PATCH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)  # 模块级只构建 EDITS，无副作用
    return [(name, BACKEND / str(rel), old, new) for name, rel, old, new in module.EDITS]


def load_supersede() -> list[tuple[str, Path, str, str]]:
    """后来重写 `test_matrix_strategy.py` 的第二版脚本（覆盖 C/D 两处第一版修法）。"""
    path = Path(__file__).with_name("patch_matrix_v2.py")
    spec = importlib.util.spec_from_file_location("_patch_matrix_v2", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return [(name, BACKEND / str(module.TARGET), old, new) for name, old, new in module.EDITS]


def section_a(results: list) -> dict:
    edits = load_edits()
    supersede = load_supersede()
    rows = []
    for name, path, old, new in edits:
        rel = str(path.relative_to(BACKEND)).replace("\\", "/")
        head = head_bytes(rel)
        work = lf(path.read_bytes().decode("utf-8"))
        row = {
            "edit": name,
            "file": f"backend/{rel}",
            "old_in_HEAD": head.count(lf(old)),
            "new_in_worktree": work.count(lf(new)),
            "old_in_worktree": work.count(lf(old)),
        }
        row["ok"] = (
            row["old_in_HEAD"] == 1
            and row["new_in_worktree"] == 1
            and row["old_in_worktree"] == 0
        )
        if not row["ok"]:
            # 该处第一版修法后来被 patch_matrix_v2.py 整段重写：要求「v1 的 new 已被 v2 的
            # old 吃掉」且「v2 的 new 出现在工作区」，才算有覆盖链证据。
            chain = []
            for sname, spath, sold, snew in supersede:
                if spath.resolve() != path.resolve():
                    continue
                chain.append({
                    "supersede_edit": sname,
                    "v1_new_is_v2_old": lf(new) in lf(sold),
                    "v2_old_in_worktree": lf(work).count(lf(sold)),
                    "v2_new_in_worktree": lf(work).count(lf(snew)),
                })
            row["supersede_chain"] = chain
            row["ok"] = any(
                c["v2_old_in_worktree"] == 0 and c["v2_new_in_worktree"] == 1 for c in chain
            )
            row["note"] = "第一版修法已被 patch_matrix_v2.py 覆盖（不属于本行改动链）"
        rows.append(row)
    ok = all(r["ok"] for r in rows)
    results.append({"check": "归属/A1 逐条编辑的三元判据（old∈HEAD ×1, new∈工作区 ×1, old∉工作区；被 v2 覆盖的两处按覆盖链判）", "ok": ok, "detail": rows})
    print(f"[{'PASS' if ok else 'FAIL'}] 归属/A1 逐条编辑三元判据", flush=True)
    for r in rows:
        print(f"    {r['edit']:<24} {r['file']:<48} old@HEAD={r['old_in_HEAD']} new@work={r['new_in_worktree']} old@work={r['old_in_worktree']} ok={r['ok']}", flush=True)

    targets = sorted({str(p) for _n, p, _o, _w in edits})
    scripts = [
        HERE / "patch_gate.py",
        PATCH,
        HERE / "patch_tests.py",
        HERE / "patch_matrix_v2.py",
    ]
    mt_rows = [mtime_row(p) for p in scripts]
    target_rows = [{**mtime_row(Path(t)), "role": "target"} for t in targets]
    mt = sorted(target_rows + [{**r, "role": "script"} for r in mt_rows], key=lambda r: r["mtime_ns"])
    gaps = []
    for i in range(len(mt) - 1):
        a, b = mt[i], mt[i + 1]
        gaps.append({
            "from": a["path"],
            "to": b["path"],
            "delta_ms": round((b["mtime_ns"] - a["mtime_ns"]) / 1e6, 1),
            "from_role": a["role"],
            "to_role": b["role"],
        })
    pair = [g for g in gaps if g["from"].endswith("test_auction_factor_pack.py")]
    pair_ok = bool(pair) and abs(pair[0]["delta_ms"]) < 10
    results.append({
        "check": "归属/A2 patch_task2.py 的两个目标文件 mtime 相距 < 10 ms（同一次写盘循环）",
        "ok": pair_ok,
        "detail": {"pair": pair, "timeline": mt},
    })
    print(f"[{'PASS' if pair_ok else 'FAIL'}] 归属/A2 同循环 mtime 指纹: {pair}", flush=True)
    for r in mt:
        print(f"    {r['role']:<6} {r['mtime']}  {r['path']}", flush=True)

    cap = [r for r in rows if r["edit"] == "E-batch-cap"][0]
    work_line = [l for l in TARGET.read_text(encoding="utf-8").splitlines() if "factor_names: list[str]" in l][0]
    head_line = [l for l in head_bytes(TARGET_REL).splitlines() if "factor_names: list[str]" in l][0]
    a3_ok = cap["ok"] and "max_length=200" in work_line and "max_length=96" in head_line
    results.append({
        "check": "归属/A3 目标行：HEAD 是 96，工作区是 200，且与 E-batch-cap 的 old/new 同字节",
        "ok": a3_ok,
        "detail": {"head_line": head_line.strip(), "work_line": work_line.strip(), "edit": cap},
    })
    print(f"[{'PASS' if a3_ok else 'FAIL'}] 归属/A3 目标行新旧值", flush=True)
    return {"edits": rows, "timeline": mt, "gaps": gaps}


def section_b(results: list) -> dict:
    from app.api import backtest as api
    from app.backtest.factor import FACTOR_COLUMNS

    ids = [item["id"] for item in FACTOR_COLUMNS]
    n = len(ids)
    results.append({
        "check": "必要性/B1 因子目录长度",
        "ok": n == 110 and len(set(ids)) == n,
        "detail": {"len": n, "unique": len(set(ids))},
    })
    print(f"[{'PASS' if n == 110 else 'FAIL'}] 必要性/B1 FACTOR_COLUMNS = {n}（unique {len(set(ids))}）", flush=True)

    # 工作区模型：110 名可提交
    try:
        model = api.FactorBatchRequest(factor_names=ids)
        ok_now, now_len = True, len(model.factor_names)
    except Exception as exc:  # noqa: BLE001
        ok_now, now_len = False, repr(exc)[:200]
    results.append({"check": "必要性/B2 工作区模型接受整份目录（110 名）", "ok": ok_now and now_len == n, "detail": {"len": now_len}})
    print(f"[{'PASS' if ok_now else 'FAIL'}] 必要性/B2 工作区 FactorBatchRequest(110) -> {now_len}", flush=True)

    # HEAD 模型（max_length=96）：同一请求被拒
    head_src = head_bytes(TARGET_REL)
    line = [l for l in head_src.splitlines() if "factor_names: list[str]" in l][0]
    head_cap = int(re.search(r"max_length=(\d+)", line).group(1))

    from pydantic import BaseModel, Field, ValidationError

    class HeadModel(BaseModel):
        factor_names: list[str] = Field(..., min_length=1, max_length=head_cap)

    rejected = None
    try:
        HeadModel(factor_names=ids)
    except ValidationError as exc:
        rejected = {
            "type": exc.errors()[0]["type"],
            "loc": list(exc.errors()[0]["loc"]),
            "msg": exc.errors()[0]["msg"],
            "ctx": exc.errors()[0].get("ctx"),
        }
    results.append({
        "check": "必要性/B3 HEAD 上限（96）拒绝整份目录（110 名）",
        "ok": head_cap == 96 and rejected is not None and rejected["type"] == "too_long",
        "detail": {"head_cap": head_cap, "rejected": rejected},
    })
    print(f"[{'PASS' if rejected else 'FAIL'}] 必要性/B3 HEAD 上限 {head_cap} 拒绝 110 名: {rejected}", flush=True)

    # 新上限仍是兜底：201 名被拒
    over = None
    try:
        api.FactorBatchRequest(factor_names=[f"f{i}" for i in range(201)])
    except ValidationError as exc:
        over = exc.errors()[0]["type"]
    results.append({
        "check": "必要性/B4 新上限 200 仍兜底（201 名被拒）",
        "ok": over == "too_long",
        "detail": {"rejected_type": over},
    })
    print(f"[{'PASS' if over == 'too_long' else 'FAIL'}] 必要性/B4 201 名被拒: {over}", flush=True)

    # 既有测试（未被本单改动）就是用整份目录构造请求
    test_path = BACKEND / "tests" / "backtest" / "test_research_api.py"
    test_src = test_path.read_text(encoding="utf-8")
    test_rows = [
        l for l in test_src.splitlines()
        if "factor_names = [item[\"id\"] for item in FACTOR_COLUMNS]" in l
    ]
    results.append({
        "check": "必要性/B5 既有测试用整份目录构造请求（未被改动）",
        "ok": bool(test_rows),
        "detail": {"lines": test_rows},
    })
    return {"catalog": n, "head_cap": head_cap, "rejected_at_head": rejected, "over_201": over}


def section_c(results: list) -> dict:
    work = TARGET.read_text(encoding="utf-8").splitlines()
    head = head_bytes(TARGET_REL).splitlines()
    pat = re.compile(r"min_length|max_length")
    w = [(i + 1, l) for i, l in enumerate(work) if pat.search(l)]
    h = [(i + 1, l) for i, l in enumerate(head) if pat.search(l)]
    diffs = [{"line": a[0], "head": a[1], "work": b[1]} for a, b in zip(h, w) if a[1] != b[1]]
    same_count = len(w) == len(h) == 8
    ok = same_count and len(diffs) == 1 and "max_length=200" in diffs[0]["work"]
    results.append({
        "check": "越界面/C1 8 处 min/max_length 中只有 1 处变（第 205 行）",
        "ok": ok,
        "detail": {"worktree_lines": len(w), "head_lines": len(h), "diffs": diffs},
    })
    print(f"[{'PASS' if ok else 'FAIL'}] 越界面/C1 约束行 {len(w)}/{len(h)}，差异 {len(diffs)} 处", flush=True)
    for d in diffs:
        print(f"    :{d['line']} HEAD {d['head'].strip()}", flush=True)
        print(f"    :{d['line']} WORK {d['work'].strip()}", flush=True)

    # 文件级：整份 diff 只有 1 行
    diff = git("diff", "--", f"backend/{TARGET_REL}")
    plus = [l for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    minus = [l for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
    results.append({
        "check": "越界面/C2 该文件整份 diff = +1/-1 行",
        "ok": len(plus) == 1 and len(minus) == 1,
        "detail": {"plus": len(plus), "minus": len(minus), "plus_lines": plus, "minus_lines": minus},
    })
    print(f"[{'PASS' if len(plus) == 1 else 'FAIL'}] 越界面/C2 整份 diff +{len(plus)}/-{len(minus)}", flush=True)
    return {"constraint_lines": w, "diffs": diffs, "diff_plus": plus, "diff_minus": minus}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results: list[dict] = []
    payload = {
        "script": "research/gate-fa43-20261108/evidence_attribution_20260808.py".replace("20260808", "20261108"),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "python": sys.version.split()[0],
        "head": git("rev-parse", "--short", "HEAD").strip(),
        "note": "归属用 patch_task2.py 的字面量 + mtime 指纹判定；必要性用 pydantic 边界量；越界面用逐行对照量。",
    }
    payload["attribution"] = section_a(results)
    payload["necessity"] = section_b(results)
    payload["scope"] = section_c(results)
    payload["target"] = mtime_row(TARGET)
    payload["target_sha256"] = hashlib.sha256(TARGET.read_bytes()).hexdigest()

    passed = sum(1 for r in results if r["ok"])
    payload["summary"] = {"total": len(results), "passed": passed, "failed": len(results) - passed}
    payload["checks"] = results
    out = Path(__file__).with_suffix(".json")
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{passed}/{len(results)} PASS -> {out.relative_to(REPO)}", flush=True)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
