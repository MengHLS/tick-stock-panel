"""只读验证: 生产策略目录加载后, S01b 变体是否出现在前端可选的策略列表里。

用 StrategyEngine + 与 backend/app/main.py:481-486 完全相同的目录列表,
调 list_strategies(include_research=False)（前端策略下拉的数据源）。
不启动服务、不重启、不写任何文件。
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
os.environ.setdefault("DATA_DIR", r"D:\TSP")
sys.path.insert(0, str(PROJECT / "backend"))
os.environ["DATA_DIR"] = r"D:\TSP\data"
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
out = {
    "n_dirs": [str(d) for d in dirs],
    "n_strategies_in_list": len(items),
    "ids": sorted(i.get("id") for i in items),
    "target": target,
}
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
Path(__file__).with_name("verify_list_result.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
)
raise SystemExit(0 if target else 3)
