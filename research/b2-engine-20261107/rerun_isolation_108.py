"""隔离矩阵重测 (108 口径测试已落地后)。

三态 = all_on / b0_only / none, 每态跑同一组 5 个 factor 测试文件 + 目录探针。
pack 目录 mv 到临时目录, try/finally 保证一定移回。只读 + 可逆。
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
B2 = ROOT / "research" / "b2-engine-20261107"
LOGS = B2 / "logs"
CUSTOM = ROOT / "backend" / "app" / "custom"
TMP = B2 / "_iso_tmp"
PACKS = {
    "research_factor_pack": CUSTOM / "research_factor_pack",
    "research_universe_pack": CUSTOM / "research_universe_pack",
}
PYREL = str(ROOT / "backend/.venv/Scripts/python.exe")
TESTS = [
    "tests/test_factor_dsl.py",
    "tests/test_factor_registry.py",
    "tests/test_factor_api.py",
    "tests/test_factor_store.py",
    "tests/test_factor_provider_contracts.py",
]


def purge_cache(p: Path) -> None:
    for d in list(p.rglob("__pycache__")):
        shutil.rmtree(d, ignore_errors=True)


def suite() -> dict:
    p = subprocess.run(
        [PYREL, "-m", "pytest", *TESTS, "-q"],
        cwd=ROOT / "backend",
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    out = p.stdout + p.stderr
    mp = re.search(r"(\d+) passed", out)
    mf = re.search(r"(\d+) failed", out)
    names = sorted(set(re.findall(r"FAILED\s+(\S+)", out)))
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    return {
        "passed": int(mp.group(1)) if mp else 0,
        "failed": int(mf.group(1)) if mf else 0,
        "failed_tests": names,
        "rc": p.returncode,
        "tail": lines[-1] if lines else "",
    }


def probe(tag: str) -> dict:
    subprocess.run(
        [str(ROOT / "backend/.venv/Scripts/python.exe"),
         "research/b2-engine-20261107/probe_catalog_support.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONUTF8": "1", "PROBE_TAG": tag},
    )
    dest = LOGS / f"catalog_support_{tag}.json"
    return json.loads(dest.read_text(encoding="utf-8")) if dest.exists() else {}


results: dict[str, dict] = {}
TMP.mkdir(exist_ok=True)
moved: list[tuple[Path, Path]] = []
try:
    results["all_on"] = {"setup": "B0 + B2 全在 (工作区现状)", **suite()}
    results["all_on"]["probe"] = probe("all_on")

    src = PACKS["research_universe_pack"]
    dst = TMP / src.name
    purge_cache(src)
    shutil.move(str(src), str(dst))
    moved.append((dst, src))
    results["b0_only"] = {"setup": "只留 research_factor_pack, 无 research_universe_pack", **suite()}
    results["b0_only"]["probe"] = probe("b0_only")

    src2 = PACKS["research_factor_pack"]
    dst2 = TMP / src2.name
    purge_cache(src2)
    shutil.move(str(src2), str(dst2))
    moved.append((dst2, src2))
    results["none"] = {"setup": "两个 pack 目录都移出 (93 基线)", **suite()}
    results["none"]["probe"] = probe("none")
finally:
    for dst, src in reversed(moved):
        if dst.exists():
            shutil.move(str(dst), str(src))
    shutil.rmtree(TMP, ignore_errors=True)
    for p in PACKS.values():
        purge_cache(p)

summary = {
    k: {
        "catalog_size": v.get("probe", {}).get("catalog_size"),
        "matrix_unsupported": v.get("probe", {}).get("matrix_unsupported"),
        "has_b0_pack": v.get("probe", {}).get("has_b0_pack"),
        "has_universe_pack": v.get("probe", {}).get("has_universe_pack"),
        "suite": f"{v['failed']} failed / {v['passed']} passed",
        "failed_tests": v["failed_tests"],
    }
    for k, v in results.items()
}
out = {
    "measured_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    "tests_version": "按 108 口径更新后的现盘测试 (test_factor_registry.py / test_factor_store.py, mtime 2026-11-07 20:48:59)",
    "states": results,
    "summary": summary,
    "restored": all(p.exists() for p in PACKS.values()),
}
(LOGS / "isolation_recheck_108.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
)
print(json.dumps(summary, ensure_ascii=False, indent=1))
print("restored:", out["restored"])
