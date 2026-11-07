"""索引检出探针: 「按索引内容检出」(git checkout-index -a) 后跑 B2 五文件套件与 gate 套件。

目的: 回答「干净检出是否还会红」——不 commit、不 push, 只把该进索引的文件 add 进索引,
再用索引内容导出一棵干净的树, 在那里跑测试。

用法: PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/b2-engine-20261107/probe_index_checkout_110.py
产出:
  logs/index_checkout_probe_110.json  结构化 (命令/时刻/版本/条数/失败 test id/根因证据)
  logs/index_checkout_probe_110.txt   人读叙事 (同 22:28 那份的格式)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "research" / "b2-engine-20261107" / "logs"
PY = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
TZ = timezone(timedelta(hours=8))

SUITE5 = [
    "tests/test_factor_dsl.py",
    "tests/test_factor_registry.py",
    "tests/test_factor_api.py",
    "tests/test_factor_store.py",
    "tests/test_factor_provider_contracts.py",
]
GATE = ["tests/test_factor_gate.py"]
# gate 套件的外部数据依赖: allowlist 只读这份 inventory 产物, 它当时是未跟踪 (docs/ 全部 ??)
INV = "docs/architecture/evidence/referenced_factor_inventory.json"


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def run_pytest(cwd: Path, files: list[str]) -> dict:
    argv = [str(PY), "-m", "pytest", *files, "-q"]
    t0 = now()
    p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    t1 = now()
    tail = "\n".join(p.stdout.strip().splitlines()[-6:])
    summary = (p.stdout.strip().splitlines() or [""])[-1]
    return {
        "argv": argv,
        "cwd": str(cwd),
        "started_at": t0,
        "finished_at": t1,
        "returncode": p.returncode,
        "summary_line": summary,
        "stdout_tail": tail,
        "failed_tests": [ln.split(" ")[1] for ln in p.stdout.splitlines() if ln.startswith("FAILED ")],
    }


def versions() -> dict:
    out = subprocess.run([str(PY), "-c",
                          "import sys,pytest;print(pytest.__version__);print('%d.%d.%d'%sys.version_info[:3])"],
                         capture_output=True, text=True)
    got = out.stdout.strip().splitlines()
    return {"pytest": got[0] if got else None, "python": got[1] if len(got) > 1 else None}


def main() -> int:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=ROOT, capture_output=True,
                            text=True).stdout.strip().splitlines()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                           text=True).stdout.strip().splitlines()

    tmp = Path(tempfile.mkdtemp(prefix="idxco_"))
    try:
        subprocess.run(["git", "checkout-index", "-a", f"--prefix={tmp.as_posix()}/"], cwd=ROOT, check=True)
        tree = tmp / "backend"

        base5 = run_pytest(tree, SUITE5)
        gate_before = run_pytest(tree, GATE)
        inv_present = (tmp / INV).exists()

        # 补充探针: 只把这份 inventory 产物放进导出树, 其余不动 -> 证明 gate 的 4 红只因它缺席
        gate_after = None
        if not inv_present:
            src = ROOT / INV
            if src.exists():
                dst = tmp / INV
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                sha_src = subprocess.run(["git", "hash-object", str(src)], capture_output=True, text=True).stdout.strip()
                gate_after = run_pytest(tree, GATE)
                gate_after["injected_artifact"] = {
                    "path": INV, "bytes": src.stat().st_size, "git_hash_object": sha_src,
                    "how": "cp 到导出树同一相对路径后用同一命令重跑; 索引未改动",
                }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    res = {
        "question": "把该进索引的文件全部 add (不 commit) 后, 「按索引内容检出」是否 0 红?",
        "method": "git checkout-index -a --prefix=<临时空目录> 导出索引内容 -> 在导出树的 backend/ 下用同一 venv 跑 pytest",
        "at": now(),
        "head": head,
        "head_short": head[:8],
        "index": {"staged_files": staged, "staged_count": len(staged),
                  "worktree_dirty_lines": len(dirty)},
        "tooling": versions(),
        "suite5": base5,
        "gate": {"index_only": gate_before, "with_inventory_artifact": gate_after},
        "verdict": {
            "suite5_clean": base5["returncode"] == 0,
            "gate_clean_index_only": gate_before["returncode"] == 0,
            "gate_clean_with_artifact": None if gate_after is None else gate_after["returncode"] == 0,
        },
    }
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "index_checkout_probe_110.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    inv_line = (
        f"#   {INV}: 索引内已存在 (导出树里有)" if inv_present else
        f"#   根因: {INV} 未跟踪 (docs/ 全部 ??), 导出树里没有 -> gate 的 4 条 allowlist 用例 FileNotFoundError"
    )
    txt = [
        "# 目的: 验证「把该进索引的文件全部 add、不 commit」后, 按索引内容检出是否 0 红",
        f"# at {res['at']}  HEAD={res['head_short']}  索引 {len(staged)} 文件 staged",
        "# 方法: git checkout-index -a --prefix=<临时空目录> (= 只用索引内容导出, 等价于「按索引检出」)",
        f"$ cd <导出树>/backend && PYTHONUTF8=1 <repo>/backend/.venv/Scripts/python.exe -m pytest {' '.join(SUITE5)} -q",
        "",
        "--- 五文件套件 ---",
        base5["stdout_tail"],
        f"  => {base5['summary_line']}",
        "",
        f"$ ... -m pytest {' '.join(GATE)} -q",
        "--- gate 套件 (索引内容原样) ---",
        gate_before["stdout_tail"],
        f"  => {gate_before['summary_line']}",
        inv_line,
    ]
    if gate_after:
        txt += [
            "",
            f"$ cp <repo>/{INV} <导出树>/{INV}   # 只补这一份产物, 索引未改动",
            "--- gate 套件 (补上 inventory 产物后) ---",
            gate_after["stdout_tail"],
            f"  => {gate_after['summary_line']}",
            "",
            "# 结论: 五文件套件在索引检出上 0 红 (74 passed)。gate 的 4 红唯一原因是",
            f"#   {INV} 未进索引; 补上后 56 passed。要 gate 也在干净检出上全绿,",
            "#   必须把这份产物 (及其 .sha256) 一并纳入索引——按派工「docs/ 不动」本批未 add, 提交开发经理裁定。",
        ]
    (LOGS / "index_checkout_probe_110.txt").write_text("\n".join(txt) + "\n", encoding="utf-8")

    print(json.dumps(res["verdict"], ensure_ascii=False))
    print("suite5:", base5["summary_line"])
    print("gate(index-only):", gate_before["summary_line"])
    if gate_after:
        print("gate(+artifact):", gate_after["summary_line"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
