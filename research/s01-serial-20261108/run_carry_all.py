"""分段连续账户回放驱动: 逐段串行调用 prod_run_carry.py（每段独立进程, 内存有界）。

段边界按自然半年/年切, 但账户不清算: 每段 --carry-in 上一段的 carry_out.json。
最后一段不追平仓（carry_out=True）, 与研究侧 finalize_open_at_end 语义一致。
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = HERE.parents[1] / "backend" / ".venv" / "Scripts" / "python.exe"

SEGMENTS = [
    ("c1", "2019-07-01", "2020-06-30"),
    ("c2", "2020-07-01", "2021-06-30"),
    ("c3", "2021-07-01", "2022-06-30"),
    ("c4", "2022-07-01", "2023-06-30"),
    ("c5", "2023-07-01", "2024-06-30"),
    ("c6", "2024-07-01", "2025-06-30"),
    ("c7", "2025-07-01", "2026-06-30"),
    ("c8", "2026-07-01", "2026-10-30"),
]


def main() -> int:
    log = HERE / "log_carry_all.txt"
    state = HERE / "carry_state.json"
    if state.exists():
        state.unlink()
    rc: dict[str, int] = {}
    with open(log, "w", encoding="utf-8", errors="replace") as fh:
        for tag, start, end in SEGMENTS:
            cmd = [
                str(PY), str(HERE / "prod_run_carry.py"),
                "--start", start, "--end", end, "--tag", tag,
                "--carry-out", str(state),
            ]
            if state.exists():
                cmd += ["--carry-in", str(state)]
            t0 = time.perf_counter()
            fh.write(f"\n===== {tag} {start}..{end} start {time.strftime('%H:%M:%S')} =====\n")
            fh.flush()
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            fh.write(proc.stdout or "")
            fh.write(proc.stderr or "")
            fh.flush()
            rc[tag] = proc.returncode
            fh.write(f"===== {tag} exit={proc.returncode} {time.perf_counter()-t0:.1f}s =====\n")
            fh.flush()
            if proc.returncode != 0:
                break
    (HERE / "carry_exit_codes.json").write_text(json.dumps(rc, indent=1), encoding="utf-8")
    print(json.dumps(rc))
    return 0 if all(v == 0 for v in rc.values()) and len(rc) == len(SEGMENTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
