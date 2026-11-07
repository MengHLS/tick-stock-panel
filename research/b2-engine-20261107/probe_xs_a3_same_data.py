"""XS-A3 的数据漂移免疫版: 同一份当前数据, 旧 dsl.py (B2 前) vs 新 dsl.py (B2 后) 逐列哈希对比。

背景: baseline_before.json (18:16) 与 baseline_after.json 在 21:36 重算后不一致, 原因是
行情数据在 20:46:42 (kline_daily/date=2026-11-06) 与 20:54:07 (kline_daily_enriched/date=2026-11-06)
被重建, 该日落在面板区间内 => 跨时间的哈希对比测到的是数据漂移, 不是代码变更。

做法: 临时把 backup/dsl.py.orig 换进 backend/app/factors/dsl.py, 跑一次哈希, 再换回并校验 sha。
try/finally + sha 校验保证一定还原。只读数据, 不改任何其他文件。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
B2 = ROOT / "research" / "b2-engine-20261107"
DSL = ROOT / "backend/app/factors/dsl.py"
ORIG = B2 / "backup/dsl.py.orig"
PY = str(ROOT / "backend/.venv/Scripts/python.exe")
EXPECT_DSL_SHA = "49f3a1106095ad0cf4a6c1cb8ccde42283957756f89ac1f226bf1624fea0c78b"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_hashes(dest: Path) -> dict:
    import os

    p = subprocess.run([PY, str(B2 / "baseline_hashes_after.py")], cwd=ROOT,
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONUTF8": "1"})
    if p.returncode != 0:
        raise RuntimeError(p.stdout[-2000:] + p.stderr[-2000:])
    data = json.loads((B2 / "baseline_after.json").read_text(encoding="utf-8"))
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


current_bytes = DSL.read_bytes()
cur_sha = hashlib.sha256(current_bytes).hexdigest()
assert cur_sha == EXPECT_DSL_SHA, f"现盘 dsl.py sha 不符: {cur_sha}"
orig_sha = sha(ORIG)

old = None
try:
    shutil.copyfile(ORIG, DSL)
    got = sha(DSL)
    assert got == orig_sha, f"换入后 sha 不符: {got}"
    old = run_hashes(B2 / "baseline_old_dsl.json")
finally:
    DSL.write_bytes(current_bytes)
    back = sha(DSL)
    if back != EXPECT_DSL_SHA:
        raise SystemExit(f"!! dsl.py 还原失败: {back}")

restored_sha = sha(DSL)
new = json.loads((B2 / "baseline_after.json").read_text(encoding="utf-8"))


def flat(d: dict, pre: str = "") -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flat(v, pre + k + "."))
        else:
            out[pre + k] = v
    return out


fo, fn = flat(old), flat(new)
keys = sorted(set(fo) | set(fn))
diffs = [k for k in keys if fo.get(k) != fn.get(k)]
res = {
    "why": "同一份当前数据 (含 20:54 重建的 2026-11-06), 只换 dsl.py 版本",
    "old_dsl": {"path": "research/b2-engine-20261107/backup/dsl.py.orig", "sha256": orig_sha,
                "bytes": ORIG.stat().st_size, "has_xs_ops": False},
    "new_dsl": {"path": "backend/app/factors/dsl.py", "sha256": EXPECT_DSL_SHA,
                "bytes": len(current_bytes), "has_xs_ops": True},
    "rows": new.get("rows"), "symbols": new.get("symbols"),
    "compared_keys": len(keys), "diff_keys": diffs, "n_diff": len(diffs),
    "identical": len(diffs) == 0,
    "dsl_restored_sha256": restored_sha,
    "dsl_restored_ok": restored_sha == EXPECT_DSL_SHA,
    "old_hashes": {k: v for k, v in fo.items() if k.endswith(".sha256")},
    "new_hashes": {k: v for k, v in fn.items() if k.endswith(".sha256")},
}
(B2 / "logs" / "xs_a3_same_data_old_vs_new_dsl.json").write_text(
    json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
print(json.dumps({k: res[k] for k in ("rows", "symbols", "compared_keys", "n_diff", "identical",
                                      "dsl_restored_ok")}, ensure_ascii=False))
for k in diffs[:10]:
    print("DIFF", k, fo.get(k), "->", fn.get(k))
