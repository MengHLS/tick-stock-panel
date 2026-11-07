"""冻结 OBSFIX 轮的协议、代码与输入指纹（必须在复算之前运行一次）。

写入 `obs-fix-20261107/FREEZE_OBSFIX.json`。复算与验证脚本都会校验本文件，
不符即 exit 2。

用法（项目根目录）
    set PYTHONUTF8=1
    backend\\.venv\\Scripts\\python.exe research\\strategy-search-20261107\\obs-fix-20261107\\scripts\\freeze_obsfix.py

退出码
    0 成功
    4 必填输入缺失
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve()
PKG = HERE.parents[1]
STRATEGY_DIR = HERE.parents[2]
PROJECT = HERE.parents[4]

PANEL_HASH = "fda82b47b6d5b92e0cc4b6d481020ee9a5cb328b282645c647697927c0f6dfe3"
LEGACY = [
    "results/PATH_RISK.md",
    "results/path_risk/path_risk.json",
    "results/path_risk/path_position_days.parquet",
    "results/path_risk/path_risk_verification.json",
]


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main() -> None:
    required = {
        "protocol": PKG / "PROTOCOL_OBSFIX_v1.md",
        "replay_script": PKG / "scripts" / "replay_s07_obs.py",
        "verify_script": PKG / "scripts" / "verify_obsfix.py",
        "common_py": STRATEGY_DIR / "scripts" / "common.py",
        "engine_py": PROJECT / "backend/app/backtest/engine.py",
        "matrix_py": PROJECT / "backend/app/backtest/matrix.py",
        "old_run": STRATEGY_DIR / "results" / "run_S07_xs_lowvol_60d_10.json",
    }
    missing = [k for k, p in required.items() if not p.exists()]
    if missing:
        print(json.dumps({"error": "missing", "keys": missing}, ensure_ascii=False), flush=True)
        raise SystemExit(4)

    legacy = {p: sha256(STRATEGY_DIR / p) for p in LEGACY}
    missing_legacy = [p for p, h in legacy.items() if h is None]
    if missing_legacy:
        print(json.dumps({"error": "missing legacy", "paths": missing_legacy},
                         ensure_ascii=False), flush=True)
        raise SystemExit(4)

    status = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=PROJECT, text=True,
        encoding="utf-8", errors="replace",
    )
    status_norm = "\n".join(
        sorted(line for line in status.splitlines() if "obs-fix-20261107" not in line)
    )

    freeze = {
        "schema": "obsfix-freeze/1",
        "created_at": datetime.now().astimezone().isoformat(),
        "purpose": "S07@10bp 期末持仓可观测性补全的最小闭环（复现，非新试验）",
        "panel_hash": PANEL_HASH,
        "panel": {"rows": 6422875, "symbols": 3384, "dates": 2136,
                  "window": ["2018-01-08", "2026-10-30"]},
        "n_trials": {"before": 15, "after": 15, "new_alpha_hypotheses": 0,
                     "reason": "仅改产物持久化，信号/参数/宇宙/成本/时序不变"},
        "sha256": {k: sha256(p) for k, p in required.items()},
        "sizes": {k: p.stat().st_size for k, p in required.items()},
        "mtimes": {
            k: datetime.fromtimestamp(p.stat().st_mtime).isoformat()
            for k, p in required.items()
        },
        "legacy_artifacts": legacy,
        "git_status_hash_excluding_obsfix": hashlib.sha256(
            status_norm.encode("utf-8")
        ).hexdigest(),
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
        ).strip(),
        "note": "复算与验证脚本必须与本文件 sha256 一致；不一致即 exit 2，不得改本文件迁就结果",
    }
    out = PKG / "FREEZE_OBSFIX.json"
    out.write_text(json.dumps(freeze, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "freeze": str(out),
        "created_at": freeze["created_at"],
        "sha256": {k: (v or "")[:16] for k, v in freeze["sha256"].items()},
        "legacy": {p: (h or "")[:16] for p, h in legacy.items()},
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
