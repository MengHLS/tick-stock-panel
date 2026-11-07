"""问 1 实验 ②: 五文件套件 20 次, 统计是否有任何一次不是 74 passed.

每次跑前用独立进程探一次目录条数, 以同时记录「pack 是否装载」。
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import time

BACKEND = pathlib.Path(__file__).resolve().parents[3] / "backend"
PY = str(BACKEND / ".venv" / "Scripts" / "python.exe")
FILES = [
    "tests/test_factor_registry.py",
    "tests/test_factor_store.py",
    "tests/test_factor_provider_contracts.py",
    "tests/test_factor_api.py",
    "tests/test_factor_dsl.py",
]

PROBE = (
    "import app.factors.registry as reg, app.extensions.factors as ext;"
    "ids=[s.id for s in reg.all_factors()];"
    "print(len(ids), len(ext._PROVIDERS), 'in_universe' in ids)"
)

rows = []
started = time.strftime("%H:%M:%S")
for i in range(1, 21):
    probe = subprocess.run([PY, "-c", PROBE], cwd=BACKEND, capture_output=True, text=True)
    cat = probe.stdout.strip().split()
    p = subprocess.run(
        [PY, "-m", "pytest", *FILES, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONUTF8": "1"},
    )
    out = p.stdout + p.stderr
    m = re.search(r"^(?:=+\s*)?(\d+) failed.*?(\d+) passed", out, re.M)
    m2 = re.search(r"(\d+) passed", out)
    failed = re.findall(r"^FAILED (\S+)", out, re.M)
    passed = int(m.group(2)) if m else (int(m2.group(1)) if m2 else -1)
    nfailed = int(m.group(1)) if m else (0 if m2 else -1)
    rows.append(
        {
            "run": i,
            "catalog": cat[0] if cat else "?",
            "providers": cat[1] if len(cat) > 1 else "?",
            "in_universe": cat[2] if len(cat) > 2 else "?",
            "passed": passed,
            "failed": nfailed,
            "failed_names": failed,
            "rc": p.returncode,
        }
    )
    print(json.dumps(rows[-1], ensure_ascii=False), flush=True)

summary = {
    "started": started,
    "ended": time.strftime("%H:%M:%S"),
    "runs": len(rows),
    "not_74": [r["run"] for r in rows if r["passed"] != 74 or r["failed"] != 0],
    "distinct_catalog_counts": sorted({r["catalog"] for r in rows}),
    "rows": rows,
}
pathlib.Path(__file__).with_name("p3_twenty_runs.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("SUMMARY", json.dumps({k: summary[k] for k in ("started", "ended", "runs", "not_74", "distinct_catalog_counts")}, ensure_ascii=False))
