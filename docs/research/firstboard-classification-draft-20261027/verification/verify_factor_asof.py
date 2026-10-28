"""Whole-table check of the delivered factor snapshots (D-1 background vs D close).

The delivered replay ships two factor snapshots per event.  A spot check of one
field is not enough for acceptance, so this script recomputes every computable
factor from the frozen price path and compares both snapshots, and verifies the
``asof`` date of each snapshot is exactly the intended one.

Fields depending on ``amount`` are skipped: the frozen path file carries volume
but not amount, so they cannot be reproduced from the frozen inputs alone.

Run from the repository root:
    cd backend && uv run --frozen python \
        ../docs/research/firstboard-classification-draft-20261027/verification/verify_factor_asof.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import statistics
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRAFT = HERE.parent
PATHS = DRAFT / "shape-selection-paths.csv"
EVENTS = DRAFT / "event-replay-v01" / "historical-events.json"
OUT_JSON = HERE / "factor-asof-check.json"
OUT_MD = HERE / "FACTOR-ASOF-CHECK.md"

WINDOWS = [5, 20, 60, 120, 250]
COMPARED_PREFIXES = ("return_", "coverage_", "position_", "ma_bias_", "daily_return_std_")
SPECIAL = ["volume_ratio_vs_prior5"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute(rows: list[dict[str, str]]) -> dict[str, object]:
    last = rows[-1]
    close = float(last["close"])
    out: dict[str, object] = {"asof": last["date"]}
    for n in WINDOWS:
        out[f"return_{n}"] = close / float(rows[-n - 1]["close"]) - 1 if len(rows) > n else None
        window = rows[-n:]
        out[f"coverage_{n}"] = len(window)
        low = min(float(row["low"]) for row in window)
        high = max(float(row["high"]) for row in window)
        out[f"position_{n}"] = (
            (close - low) / (high - low) if len(window) == n and high > low else None
        )
        out[f"ma_bias_{n}"] = (
            close / statistics.mean(float(row["close"]) for row in window) - 1
            if len(window) == n else None
        )
        returns = [
            float(rows[i]["close"]) / float(rows[i - 1]["close"]) - 1
            for i in range(max(1, len(rows) - n), len(rows))
        ]
        out[f"daily_return_std_{n}"] = statistics.stdev(returns) if len(returns) == n else None
    prior = rows[-6:-1]
    out["volume_ratio_vs_prior5"] = (
        float(last["volume"]) / statistics.mean(float(row["volume"]) for row in prior)
        if len(prior) == 5 and sum(float(row["volume"]) for row in prior) > 0 else None
    )
    return out


def main() -> int:
    rows_by_symbol: dict[str, list[dict[str, str]]] = {}
    with PATHS.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows_by_symbol.setdefault(row["symbol"], []).append(row)
    for symbol_rows in rows_by_symbol.values():
        symbol_rows.sort(key=lambda row: row["date"])

    events = json.loads(EVENTS.read_text(encoding="utf-8"))
    mismatches: list[dict[str, object]] = []
    asof_issues: list[dict[str, object]] = []
    compared = 0

    for event in events:
        code = event["code"]
        day = event["date"]
        symbol_rows = rows_by_symbol[code]
        index = next(i for i, row in enumerate(symbol_rows) if row["date"] == day)
        prefix = symbol_rows[: index + 1]
        background = symbol_rows[:index]

        for label, source, expected_asof, delivered in (
            ("D-1", background, background[-1]["date"], event["factors_D_minus_1"]),
            ("D", prefix, day, event["factors_D_close"]),
        ):
            mine = compute(source)
            if mine["asof"] != expected_asof or delivered.get("asof") != expected_asof:
                asof_issues.append({
                    "event": event["event_id"], "snapshot": label,
                    "expected_asof": expected_asof, "delivered_asof": delivered.get("asof"),
                })
            keys = [
                key for key in mine
                if key.startswith(COMPARED_PREFIXES) or key in SPECIAL
            ]
            for key in keys:
                compared += 1
                a = mine[key]
                b = delivered.get(key)
                if isinstance(a, float) and isinstance(b, (int, float)):
                    if abs(a - b) > 1e-9:
                        mismatches.append({"event": event["event_id"], "snapshot": label,
                                           "field": key, "mine": a, "delivered": b})
                elif a != b:
                    mismatches.append({"event": event["event_id"], "snapshot": label,
                                       "field": key, "mine": a, "delivered": b})

    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "events": len(events),
        "snapshots_per_event": 2,
        "fields_compared": compared,
        "mismatches": len(mismatches),
        "mismatch_details": mismatches[:50],
        "asof_issues": asof_issues,
        "skipped_fields": ["amount (not present in the frozen path file)"],
        "inputs": {
            "shape-selection-paths.csv": sha256(PATHS),
            "historical-events.json": sha256(EVENTS),
            "verify_factor_asof.py": sha256(Path(__file__).resolve()),
        },
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 因子快照时点·整表复算",
        "",
        f"生成时间：{report['generated']}",
        "",
        f"- 事件：{len(events)}，每事件两套快照（D−1 背景 / D 收盘）",
        f"- 比对字段：{compared}",
        f"- 数值不一致：{len(mismatches)}",
        f"- asof 日期不符：{len(asof_issues)}",
        "",
        "字段：`return_5/20/60/120/250`、`coverage_*`、`position_*`、`ma_bias_*`、"
        "`daily_return_std_*`、`volume_ratio_vs_prior5`。",
        "",
        "未比对：`amount`（冻结行情文件无该列，无法仅凭冻结输入复现）。",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"events={len(events)} fields={compared} mismatches={len(mismatches)} asof_issues={len(asof_issues)}")
    for item in mismatches[:10]:
        print("  DIFF", item)
    for item in asof_issues[:5]:
        print("  ASOF", item)
    return 0 if not mismatches and not asof_issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
