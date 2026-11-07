"""XS-B3 / XS-C3: 策略侧对 `xs_rank_market` / `xs_rank_pct` 的引用计数必须为 0。

契约 v0.7 §3.4.3: XS-B3「策略侧引用计数 = 0」(扫策略文件 / seed / 执行器), XS-C3 同。
把「引用」与「代码注释里提到这个 id」分开, 否则判据会被注释污染:

硬面 (判定项, 必须 0) —— 策略定义本身:
  1. D:/TSP/data/user_data/custom_signals        (生产活配置 JSON/JSONL)
  2. D:/TSP/data/user_data/strategy_overrides    (生产覆盖配置)
  3. D:/TSP/data/user_data/monitor_rules         (生产盘中规则)
  4. research/strategy-search-20261107           (研究侧策略定义 / seed / 参数表)
  5. backend/app/custom/strategy_research        (策略研究包)
软面 (只登记, 不判定) —— 引擎/Provider/测试代码; 命中按行打印, 逐条说明是否为注释。
排除: backend/app/factors/dsl.py (算子定义处, 必须出现), research/b2-engine-20261107 (本批脚本)。
只读。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(r"C:\work\sourcecode\tick-stock-panel")
IDS = ("xs_rank_market", "xs_rank_pct")
SKIP_DIRS = {"__pycache__", ".venv", ".git", "node_modules", ".pytest_cache"}
TEXT_EXT = {".py", ".json", ".jsonl", ".md", ".yaml", ".yml", ".toml", ".txt", ".csv", ".seed"}

HARD_ROOTS = [
    Path(r"D:/TSP/data/user_data/custom_signals"),
    Path(r"D:/TSP/data/user_data/strategy_overrides"),
    Path(r"D:/TSP/data/user_data/monitor_rules"),
    ROOT / "research" / "strategy-search-20261107",
    ROOT / "backend" / "app" / "custom" / "strategy_research",
]
SOFT_ROOTS = [
    (ROOT / "backend" / "app", {ROOT / "backend" / "app" / "factors" / "dsl.py"}),
    (ROOT / "backend" / "tests", set()),
]

RESULT: dict = {"hard": {"roots": [], "hits": [], "counts": {i: 0 for i in IDS}},
                "soft": {"roots": [], "hits": [], "counts": {i: 0 for i in IDS}},
                "excluded": []}


def scan(root: Path, skip: set[Path], bucket: dict) -> None:
    if not root.exists():
        bucket["roots"].append({"root": str(root).replace("\\", "/"), "exists": False, "files": 0})
        return
    files = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p in skip:
                RESULT["excluded"].append(str(p).replace("\\", "/"))
                continue
            if p.suffix.lower() not in TEXT_EXT:
                continue
            try:
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            files += 1
            for lineno, line in enumerate(lines, 1):
                for i in IDS:
                    if i in line:
                        bucket["counts"][i] += line.count(i)
                        bucket["hits"].append({
                            "file": str(p).replace("\\", "/"),
                            "line": lineno,
                            "id": i,
                            "text": line.strip()[:160],
                            "is_comment": line.strip().startswith(("#", "//", "*", '"""', "'''")),
                        })
    bucket["roots"].append({"root": str(root).replace("\\", "/"), "exists": True, "files": files})


for r in HARD_ROOTS:
    scan(r, set(), RESULT["hard"])
for r, skip in SOFT_ROOTS:
    scan(r, skip, RESULT["soft"])

RESULT["hard_total"] = sum(RESULT["hard"]["counts"].values())
RESULT["soft_total"] = sum(RESULT["soft"]["counts"].values())
RESULT["soft_all_comments"] = all(h["is_comment"] or "——" in h["text"] or "#" in h["text"]
                                 for h in RESULT["soft"]["hits"])
RESULT["pass"] = RESULT["hard_total"] == 0
print(json.dumps(RESULT, ensure_ascii=False, indent=1))
out = Path(__file__).resolve().parent / "logs" / "id_refs_20261107.json"
out.write_text(json.dumps(RESULT, ensure_ascii=False, indent=1), encoding="utf-8")
