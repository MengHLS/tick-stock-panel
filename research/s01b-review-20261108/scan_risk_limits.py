"""S01b 独立复核 · 量级校验是否会误伤在册策略（只读）。

1) 用生产装载器（同一 4 个目录）装载，打印 load_errors / 策略数；
2) 用 ast 静态扫描「所有」策略文件（含 research / seeds / ai / composite）的
   STOP_LOSS / MAX_HOLD_DAYS 字面值，逐条跑 risk_limits 校验，报越界项。

用法: backend\\.venv\\Scripts\\python.exe research\\s01b-review-20261108\scan_risk_limits.py
退出码: 0 = 无越界、无 load_errors；1 = 有越界或装载错误
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
os.environ["DATA_DIR"] = r"D:\TSP\data"
sys.path.insert(0, str(PROJECT / "backend"))

from app.strategy.engine import StrategyEngine  # noqa: E402
from app.strategy.risk_limits import (  # noqa: E402
    STOP_LOSS_MAX_ABS,
    MAX_HOLD_DAYS_MIN,
    validate_max_hold_days,
    validate_stop_loss,
)

DATA = Path(r"D:\TSP\data")
DIRS = [
    PROJECT / "backend" / "app" / "strategy" / "research",
    DATA / "strategies" / "custom",
    DATA / "strategies" / "ai",
    DATA / "strategies" / "composite",
]
SEED_DIR = PROJECT / "backend" / "app" / "strategy" / "seeds"


def literals(path: Path) -> dict:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as exc:
        return {"_syntax_error": str(exc)}
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            if isinstance(t, ast.Name) and t.id in ("STOP_LOSS", "MAX_HOLD_DAYS"):
                try:
                    out[t.id] = ast.literal_eval(node.value)
                except Exception:
                    out[t.id] = "<non-literal>"
    return out


def main() -> int:
    problems = []
    print("=== 1) 生产装载（4 目录） ===")
    eng = StrategyEngine(strategy_dirs=DIRS)
    items = eng.list_strategies(include_research=True)
    errs = eng.load_errors()
    print(f"  strategies={len(items)} load_errors={len(errs)}")
    for e in errs:
        print("  LOAD_ERROR:", e)
        problems.append(("load_error", str(e)))
    with_consts = []
    for it in items:
        sid = it.get("id")
        try:
            s = eng.get(sid)
        except Exception as exc:  # noqa: BLE001
            print(f"  get({sid}) failed: {exc}")
            problems.append(("get", sid))
            continue
        if s.stop_loss is not None or s.max_hold_days is not None:
            with_consts.append((sid, s.stop_loss, s.max_hold_days))
    print(f"  带风控常量的策略 {len(with_consts)} 条:")
    for sid, sl, mh in with_consts:
        print(f"    {sid:52s} stop_loss={sl!r:8s} max_hold={mh!r}")

    print("\n=== 2) ast 静态扫描所有策略文件的模块常量 ===")
    rows = []
    for d in DIRS + [SEED_DIR]:
        if not d.exists():
            print(f"  [skip missing] {d}")
            continue
        for f in sorted(d.glob("*.py")):
            lits = literals(f)
            if not lits:
                continue
            rows.append((f, lits))
    bad = 0
    for f, lits in rows:
        sl, mh = lits.get("STOP_LOSS"), lits.get("MAX_HOLD_DAYS")
        try:
            validate_stop_loss(sl, context=f"{f.name}.STOP_LOSS")
            try:
                validate_max_hold_days(mh, context=f"{f.name}.MAX_HOLD_DAYS")
                ok = True
                msg = ""
            except ValueError as exc:
                ok = False
                msg = str(exc)
        except ValueError as exc:
            ok = False
            msg = str(exc)
        if not ok:
            bad += 1
            problems.append(("out_of_range", f"{f}: {msg}"))
            print(f"  [越界] {f}: {msg}")
    print(f"  扫描文件 {len(rows)} 个，越界 {bad} 个")
    sl_vals = sorted({l.get("STOP_LOSS") for _, l in rows if isinstance(l.get("STOP_LOSS"), (int, float))})
    mh_vals = sorted({l.get("MAX_HOLD_DAYS") for _, l in rows if isinstance(l.get("MAX_HOLD_DAYS"), (int, float))})
    print(f"  STOP_LOSS 字面值集合: {sl_vals}")
    print(f"  MAX_HOLD_DAYS 字面值集合: {mh_vals}")
    print(f"  阈值: |stop_loss| <= {STOP_LOSS_MAX_ABS}, max_hold_days >= {MAX_HOLD_DAYS_MIN}")
    print(f"\n问题数: {len(problems)}")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
