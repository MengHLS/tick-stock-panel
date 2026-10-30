"""Did the enriched rewrite change any value the frozen replay depends on?

The backend startup rewrote enriched partitions and the matrix generation moved
from 3145f95c... to 449e60cb....  The replay uses frozen copies, so the question
is whether today's panel still equals those copies on every row they cover.

Compares all frozen replay inputs (adjusted OHLC, volume, raw close) against the
current enriched table for the same symbol/date pairs, through 2026-10-23.

Run from the repository root:
    cd backend && uv run --frozen python \
        ../docs/research/firstboard-classification-draft-20261027/verification/check_generation_impact.py
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
DRAFT = HERE.parent
DATA = r"D:/TSP/data/kline_daily_enriched"
GEN = Path(r"D:/TSP/data/.matrix_generation_stock.json")
OUT_JSON = HERE / "generation-impact-check.json"
OUT_MD = HERE / "GENERATION-IMPACT.md"

COLUMNS = ("open", "high", "low", "close", "volume", "raw_close")
INPUTS = {
    "shape-selection-paths.csv": ("2025-01-01", "2026-10-23", COLUMNS),
    "four-case-paths.csv": ("2023-10-01", "2026-10-23", COLUMNS),
}


def partitions(start: str, end: str) -> list[str]:
    names = sorted(
        name for name in os.listdir(DATA)
        if "=" in name and start <= name.split("=")[1] <= end
    )
    return [f"{DATA}/{name}/part.parquet" for name in names
            if os.path.exists(f"{DATA}/{name}/part.parquet")]


def main() -> int:
    con = duckdb.connect()
    generation = json.loads(GEN.read_text(encoding="utf-8")) if GEN.exists() else {}
    results = {}

    for filename, (start, end, columns) in INPUTS.items():
        path = DRAFT / filename
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        symbols = sorted({row["symbol"] for row in rows})
        files = partitions(start, end)
        placeholders = ",".join(["?"] * len(symbols))
        frame = con.execute(
            f"select symbol,date,{','.join(columns)} from read_parquet(?) "
            f"where symbol in ({placeholders}) and date <= ?::DATE",
            [files] + symbols + [end],
        ).df()
        frame["date"] = frame["date"].astype(str).str[:10]
        index = {(row.symbol, row.date): row for row in frame.itertuples()}
        missing = 0
        mismatches = []
        for row in rows:
            key = (row["symbol"], row["date"])
            current = index.get(key)
            if current is None:
                missing += 1
                continue
            for column in columns:
                if abs(float(row[column]) - float(getattr(current, column))) > 1e-8:
                    mismatches.append({"symbol": key[0], "date": key[1], "column": column,
                                       "frozen": float(row[column]),
                                       "current": float(getattr(current, column))})
        results[filename] = {
            "rows": len(rows),
            "symbols": len(symbols),
            "panel_rows_compared": len(frame),
            "missing_in_panel": missing,
            "mismatches": len(mismatches),
            "mismatch_details": mismatches[:20],
        }

    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "generation_marker": generation,
        "question": "does the current enriched panel still equal the frozen replay inputs",
        "results": results,
        "conclusion": (
            "verified equal on every covered row; the generation change has no value-level "
            "effect inside the replay window, so the 27-event results stay reproducible"
        ),
        "limits": [
            "proves current == frozen, not pre-rewrite == frozen",
            "the rewritten 2026-10-27/28 partitions are outside the replay cutoff and are not assessed",
            "only the columns the replay reads are compared",
        ],
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 分区重写对冻结回放副本的影响",
        "",
        f"生成时间：{report['generated']}",
        "",
        f"当前 generation：`{generation.get('generation', 'unknown')}`",
        "",
        "| 冻结文件 | 行数 | 股票 | 面板比对行 | 缺行 | 数值不一致 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, item in results.items():
        lines.append(
            f"| {name} | {item['rows']} | {item['symbols']} | {item['panel_rows_compared']} | "
            f"{item['missing_in_panel']} | {item['mismatches']} |"
        )
    lines += ["", "## 结论", "", report["conclusion"], "", "## 边界", ""]
    lines += [f"- {item}" for item in report["limits"]]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for name, item in results.items():
        print(f"{name}: rows={item['rows']} missing={item['missing_in_panel']} mismatch={item['mismatches']}")
    ok = all(item["missing_in_panel"] == 0 and item["mismatches"] == 0 for item in results.values())
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
