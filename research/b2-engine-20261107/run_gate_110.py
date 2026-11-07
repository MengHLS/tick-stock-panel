"""现盘 gate 套件实跑一次, 落 pytest_gate_110_run.json (含起止时刻与版本)。

只跑测试, 不改任何文件, 不接线 gate.py。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "research" / "b2-engine-20261107" / "logs"
TESTS = ["tests/test_factor_gate.py"]
PYREL = sys.executable  # 本脚本必须用 backend/.venv 的 python 启动

started = datetime.datetime.now().astimezone()
p = subprocess.run(
    [PYREL, "-m", "pytest", *TESTS, "-q"],
    cwd=ROOT / "backend",
    capture_output=True,
    text=True,
    env={**os.environ, "PYTHONUTF8": "1"},
)
finished = datetime.datetime.now().astimezone()


def version(args: list[str]) -> str:
    r = subprocess.run([PYREL, *args], cwd=ROOT / "backend", capture_output=True, text=True)
    return (r.stdout or r.stderr).strip().splitlines()[0].removeprefix("pytest ")


def fil(path: str) -> dict:
    f = ROOT / path
    return {
        "path": path,
        "bytes": f.stat().st_size,
        "lines": len(f.read_text(encoding="utf-8").splitlines()),
        "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
        "assert_statements": f.read_text(encoding="utf-8").count("assert "),
        "mtime": datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
    }


out = {
    "command": (
        "cd C:/work/sourcecode/tick-stock-panel/backend && PYTHONUTF8=1 ./.venv/Scripts/python.exe "
        "-m pytest " + " ".join(TESTS) + " -q"
    ),
    "argv": [PYREL, "-m", "pytest", *TESTS, "-q"],
    "started_at": started.isoformat(timespec="seconds"),
    "finished_at": finished.isoformat(timespec="seconds"),
    "pytest_version": version(["-m", "pytest", "--version"]),
    "python_version": version(["-c", "import sys;print(sys.version.split()[0])"]),
    "returncode": p.returncode,
    "stdout_tail": (p.stdout or "")[-4000:],
    "stderr_tail": (p.stderr or "")[-2000:],
    "test_files": [
        fil("backend/app/factors/gate.py"),
        fil("backend/tests/test_factor_gate.py"),
    ],
    "note": "gate.py 本批未接线: assert_factors_usable 的生产调用点 0 (只有自身 3 处 + 测试 6 处)。",
}
LOGS.mkdir(parents=True, exist_ok=True)
(LOGS / "pytest_gate_110_run.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
)
print((p.stdout or "").strip().splitlines()[-1])
print("files:", [(t["path"], t["bytes"], t["lines"], t["sha256"][:16]) for t in out["test_files"]])
