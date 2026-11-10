"""后台启动 prod_run.py 的分离进程启动器（父 shell 退出后子进程continue运行）。

用法:
  python launch_bg.py --tag full --start 2019-07-01 --end 2026-10-30
日志: log_<tag>.txt，结果: prod_<tag>_result.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = HERE.parents[1] / "backend" / ".venv" / "Scripts" / "python.exe"
DETACHED = 0x00000008 | 0x00000200


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--start", default="2019-07-01")
    ap.add_argument("--end", default="2026-10-30")
    ap.add_argument("--gross", action="store_true")
    args = ap.parse_args()

    log = HERE / f"log_{args.tag}.txt"
    cmd = [
        str(PY), str(HERE / "prod_run.py"),
        "--start", args.start, "--end", args.end, "--tag", args.tag,
    ]
    if args.gross:
        cmd.append("--gross")
    fh = open(log, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        cmd,
        stdout=fh,
        stderr=subprocess.STDOUT,
        cwd=str(HERE.parents[1]),
        creationflags=DETACHED,
        close_fds=True,
    )
    print(json.dumps({"pid": proc.pid, "log": str(log), "cmd": cmd}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
