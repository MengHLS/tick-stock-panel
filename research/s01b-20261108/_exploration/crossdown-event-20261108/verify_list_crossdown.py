"""Step 5 (acceptance ③): read-only front-end list + production loader check.

Uses exactly the directory list backend/app/main.py wires for the API, calls
list_strategies(include_research=False) (the strategy dropdown's data source) and prints the
target entry, then loads the same dirs to report load errors.

Writes verify_list_crossdown_result.json INSIDE this experiment folder (it never touches the
s01b rollback evidence files in the parent folder).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
os.environ["DATA_DIR"] = r"D:\TSP\data"
sys.path.insert(0, str(PROJECT / "backend"))

from app.strategy.engine import StrategyEngine  # noqa: E402

DATA_ROOT = Path(r"D:\TSP\data")
dirs = [
    PROJECT / "backend" / "app" / "strategy" / "research",
    DATA_ROOT / "strategies" / "custom",
    DATA_ROOT / "strategies" / "ai",
    DATA_ROOT / "strategies" / "composite",
]
engine = StrategyEngine(strategy_dirs=dirs)
items = engine.list_strategies(include_research=False)
target = [i for i in items if i.get("id") == "custom_mw7fvp17"]

checks = {
    "list_count_is_5": len(items) == 5,
    "target_present": len(target) == 1,
}
if target:
    t = target[0]
    checks.update({
        "name_is_baseline": t.get("name") == "双均线 20/60 金叉",
        "tags_are_baseline": list(t.get("tags") or []) == ["趋势", "双均线", "S01"],
        "no_s01b_in_name": "S01b" not in str(t.get("name", "")),
        "no_s01b_in_tags": "S01b" not in (t.get("tags") or []),
        "backtest_defaults_empty": (t.get("backtest_defaults") or {}) == {},
        "description_is_baseline": "20 日均线上穿 60 日均线买入" in str(t.get("description", "")),
    })

load_errors = []
errs_attr = getattr(engine, "load_errors", None)
if errs_attr is not None:
    errs = errs_attr() if callable(errs_attr) else errs_attr
    load_errors = list(errs or [])
checks["load_errors_empty"] = load_errors == []
all_defs = sorted(engine._strategies) if hasattr(engine, "_strategies") else []

out = {
    "dirs": [str(d) for d in dirs],
    "n_strategies_in_list": len(items),
    "ids": sorted(i.get("id") for i in items),
    "target": target,
    "n_loaded": len(all_defs),
    "loaded_ids": all_defs,
    "load_errors": load_errors,
    "checks": checks,
}
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
(HERE / "verify_list_crossdown_result.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
ok = all(checks.values()) and len(all_defs) == 10
print("VERDICT:", "FRONTEND_OK" if ok else "FRONTEND_FAILED",
      "| failed:", [k for k, v in checks.items() if not v] or "none")
sys.exit(0 if ok else 3)
