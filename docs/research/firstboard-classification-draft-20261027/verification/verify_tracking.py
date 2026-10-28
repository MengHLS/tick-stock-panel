"""Independent check of the daily tracking table (forward-tracking.json).

Each tracking row should be a follow-up judgment for a given event on a later
session, referencing the frozen D-day P, and must never overwrite the D record.
This script recomputes every row from the frozen price path.

Run from the repository root:
    cd backend && uv run --frozen python \
        ../docs/research/firstboard-classification-draft-20261027/verification/verify_tracking.py
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
TRACKING = DRAFT / "event-replay-v01" / "forward-tracking.json"
CANDIDATES = DRAFT / "event-replay-v01" / "candidate-classifications.json"
OUT_JSON = HERE / "tracking-check.json"
OUT_MD = HERE / "TRACKING-CHECK.md"
WINDOWS = [5, 20, 60, 120, 250]
REFERENCE_RULE = "PB_q0.05_G0_R0"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def factors(rows: list[dict[str, str]]) -> dict[str, object]:
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

    frozen_p: dict[str, float | None] = {}
    for record in json.loads(CANDIDATES.read_text(encoding="utf-8")):
        if record["rule"] == REFERENCE_RULE:
            selected = record["classification"].get("selected")
            frozen_p[record["event_id"]] = selected.get("P") if selected else None

    tracking = json.loads(TRACKING.read_text(encoding="utf-8"))
    problems: list[dict[str, object]] = []
    fields_compared = 0

    for row in tracking:
        event = row["event_id"]
        code, day = event.split("@")
        symbol_rows = rows_by_symbol[code]
        d_index = next(i for i, item in enumerate(symbol_rows) if item["date"] == day)
        step = int(row["step_observed_sessions"])
        observed = d_index + step

        if observed >= len(symbol_rows):
            problems.append({"event": event, "step": step, "issue": "tracking beyond frozen path"})
            continue
        asof_day = symbol_rows[observed]["date"]
        if row["asof"] != f"{asof_day} close":
            problems.append({"event": event, "step": step, "issue": "asof mismatch",
                             "delivered": row["asof"], "expected": f"{asof_day} close"})

        if row["D_record_overwritten"] is not False:
            problems.append({"event": event, "step": step, "issue": "D record marked overwritten"})

        expected_p = frozen_p.get(event)
        if expected_p is not None and abs(float(row["frozen_D_P"]) - expected_p) > 1e-9:
            problems.append({"event": event, "step": step, "issue": "frozen P mismatch",
                             "delivered": row["frozen_D_P"], "expected": expected_p})

        close_d = float(symbol_rows[d_index]["close"])
        close_t = float(symbol_rows[observed]["close"])
        expected_return = close_t / close_d - 1
        fields_compared += 1
        if abs(float(row["return_since_D"]) - expected_return) > 1e-9:
            problems.append({"event": event, "step": step, "issue": "return mismatch",
                             "delivered": row["return_since_D"], "expected": expected_return})

        relation = None if expected_p is None else (
            "above" if close_t > expected_p else "below" if close_t < expected_p else "equal"
        )
        if row["current_relation_to_frozen_P"] != relation:
            problems.append({"event": event, "step": step, "issue": "relation mismatch",
                             "delivered": row["current_relation_to_frozen_P"], "expected": relation})

        mine = factors(symbol_rows[: observed + 1])
        delivered_factors = row["factors_asof_tracking_day"]
        if delivered_factors.get("asof") != asof_day:
            problems.append({"event": event, "step": step, "issue": "factor asof mismatch",
                             "delivered": delivered_factors.get("asof"), "expected": asof_day})
        for key, value in mine.items():
            if key == "asof":
                continue
            fields_compared += 1
            delivered_value = delivered_factors.get(key)
            if isinstance(value, float) and isinstance(delivered_value, (int, float)):
                if abs(value - delivered_value) > 1e-9:
                    problems.append({"event": event, "step": step, "issue": f"factor {key}",
                                     "delivered": delivered_value, "expected": value})
            elif value != delivered_value:
                problems.append({"event": event, "step": step, "issue": f"factor {key}",
                                 "delivered": delivered_value, "expected": value})

    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "rows": len(tracking),
        "fields_compared": fields_compared,
        "problems": len(problems),
        "problem_details": problems[:50],
        "checks": [
            "asof equals D + step_observed_sessions",
            "frozen_D_P equals the D-day P of the reference rule",
            "return_since_D recomputed from the frozen path",
            "current relation to frozen P",
            "factors_asof_tracking_day recomputed from rows <= that session",
            "D_record_overwritten is False",
        ],
        "inputs": {
            "shape-selection-paths.csv": sha256(PATHS),
            "forward-tracking.json": sha256(TRACKING),
            "candidate-classifications.json": sha256(CANDIDATES),
            "verify_tracking.py": sha256(Path(__file__).resolve()),
        },
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 每日跟踪表·独立复核",
        "",
        f"生成时间：{report['generated']}",
        "",
        f"- 行数：{len(tracking)}",
        f"- 比对字段：{fields_compared}",
        f"- 问题：{len(problems)}",
        "",
        "检查项：" + "；".join(report["checks"]) + "。",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"rows={len(tracking)} fields={fields_compared} problems={len(problems)}")
    for item in problems[:10]:
        print("  ", item)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
