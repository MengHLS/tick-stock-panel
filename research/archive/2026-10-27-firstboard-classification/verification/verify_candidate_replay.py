"""Independent re-derivation of the 27-event / 432-row candidate replay table.

The replay table (event-replay-v01) ships with a self-check that compares
``classify(prefix)`` against ``classify(batch)`` where ``batch`` is the same
rows as ``prefix``; that only proves determinism, not causality.  So this
script re-implements the candidate rules from the written spec and compares
every field of every row against the delivered table.

It also records the backend file fingerprints the result was produced against,
because an uncommitted working tree cannot be identified by HEAD alone.

Run from the repository root:
    cd backend && uv run --frozen python \
        ../docs/research/firstboard-classification-draft-20261027/verification/verify_candidate_replay.py
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRAFT = HERE.parent
REPO = DRAFT.parents[2]
OUT_JSON = HERE / "candidate-replay-check.json"
OUT_MD = HERE / "CANDIDATE-REPLAY-CHECK.md"

PATHS = DRAFT / "shape-selection-paths.csv"
FLAGS = DRAFT / "platform-firstboard-flags.csv"
CANDIDATES = DRAFT / "event-replay-v01" / "candidate-classifications.json"
ENGINE = REPO / "backend" / "app" / "backtest" / "engine.py"
STRATEGY = REPO / "backend" / "app" / "backtest" / "strategy.py"
CHAIN = REPO / "backend" / "app" / "factors" / "event_chain.py"

FIELDS = [
    "P", "P_date", "P_known_at", "L_setup", "L_setup_date", "first_break",
    "path_state", "skip", "new_high_after_anchor", "depth",
    "recovery_raw", "recovery_applicable",
]
TOP_FIELDS = ["nearest_anchor", "examined", "stop"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def trajectory(prefix, anchor, include, q, gate):
    pre = prefix[:-1]
    day = prefix[-1]
    ar = [row for row in pre if row["date"] >= anchor]
    version = {
        "anchor": anchor, "P": None, "P_date": None, "P_known_at": None,
        "L_setup": None, "L_setup_date": None, "first_break": None,
        "path_state": "no_first_decline", "break_event": None, "skip": True,
        "new_high_after_anchor": None, "depth": None,
        "recovery_raw": None, "recovery_applicable": False,
    }
    decline = next(
        (i for i in range(1, len(ar)) if float(ar[i]["close"]) < float(ar[i - 1]["close"])),
        None,
    )
    if decline is None:
        return version
    window = ar[: decline + (1 if include else 0)]
    peak = max(window, key=lambda row: float(row["high"]))
    price = float(peak["high"])
    known = ar[decline]["date"]
    new_high = price > float(ar[0]["high"])
    version.update(P=price, P_date=peak["date"], P_known_at=known, new_high_after_anchor=new_high)
    if gate and not new_high:
        version["path_state"] = "no_post_anchor_high"
        return version
    breakout = next(
        (row for row in prefix if row["date"] >= known and float(row["close"]) > price),
        None,
    )
    setup = [
        row for row in pre
        if row["date"] > peak["date"]
        and (breakout is None or row["date"] < breakout["date"])
    ]
    if not setup:
        version["path_state"] = "no_setup"
        return version
    low = min(setup, key=lambda row: float(row["low"]))
    low_price = float(low["low"])
    depth = (price - low_price) / price
    prior = bool(breakout and breakout["date"] < day["date"])
    if prior:
        state = "prior_close_break"
    elif depth < q:
        state = "shallow_pullback"
    elif float(pre[-1]["close"]) > low_price:
        state = "left_low_below_P"
    else:
        state = "at_or_below_setup_low"
    version.update(
        L_setup=low_price, L_setup_date=low["date"], depth=depth,
        first_break=breakout["date"] if breakout else None, path_state=state,
        break_event={
            "first_break_on_D": bool(breakout and breakout["date"] == day["date"]),
            "prior_break": prior,
            "relation": "above" if float(day["close"]) > price
            else "below" if float(day["close"]) < price else "equal",
        },
        skip=(not prior) and depth < q,
        recovery_raw=(float(pre[-1]["close"]) - low_price) / (price - low_price)
        if price > low_price else None,
        recovery_applicable=(not prior) and float(pre[-1]["close"]) >= low_price,
    )
    return version


def classify(prefix, board_dates, include, q, gate, recursive):
    prior = [row["date"] for row in prefix[-251:-1] if row["date"] in board_dates]
    trace = []
    for anchor in reversed(prior):
        version = trajectory(prefix, anchor, include, q, gate)
        trace.append(version)
        if not recursive or not version["skip"]:
            break
    return {
        "nearest_anchor": prior[-1] if prior else None,
        "selected": trace[-1] if trace else None,
        "trace": trace,
        "examined": len(trace),
        "stop": "nearest_only" if not recursive else "first_non_skippable_or_history_exhausted",
        "reason": "CANDIDATE_RULE_UNFINALIZED" if prior else "NO_PRIOR_BOARD_IN_AVAILABLE_250_WINDOW",
    }


def main() -> int:
    rows_by_symbol: dict[str, list[dict[str, str]]] = {}
    for row in load(PATHS):
        rows_by_symbol.setdefault(row["symbol"], []).append(row)
    for symbol_rows in rows_by_symbol.values():
        symbol_rows.sort(key=lambda row: row["date"])
    board_dates: dict[str, set[str]] = {}
    for row in load(FLAGS):
        if row["consecutive_limit_ups"] == "1":
            board_dates.setdefault(row["symbol"], set()).add(row["date"])

    delivered = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    mismatches: list[dict[str, object]] = []
    absent_fields: list[dict[str, object]] = []
    compared_fields = 0
    compared_rows = 0

    for record in delivered:
        code, day = record["event_id"].split("@")
        symbol_rows = rows_by_symbol[code]
        index = next(i for i, row in enumerate(symbol_rows) if row["date"] == day)
        prefix = symbol_rows[: index + 1]
        match = next(
            (r for r in itertools.product([False, True], [0.03, 0.05], [False, True], [False, True])
             if f"P{'B' if r[0] else 'A'}_q{r[1]}_G{int(r[2])}_R{int(r[3])}" == record["rule"]),
            None,
        )
        if match is None:
            raise SystemExit(f"unknown rule label: {record['rule']}")
        include, q, gate, recursive = match
        mine = classify(prefix, board_dates.get(code, set()), include, q, gate, recursive)
        theirs = record["classification"]
        compared_rows += 1

        for key in TOP_FIELDS:
            compared_fields += 1
            if mine[key] != theirs.get(key):
                mismatches.append({"event": record["event_id"], "rule": record["rule"],
                                   "field": key, "mine": mine[key], "delivered": theirs.get(key)})

        mine_selected = mine["selected"]
        their_selected = theirs.get("selected")
        if (mine_selected is None) != (their_selected is None):
            mismatches.append({"event": record["event_id"], "rule": record["rule"],
                               "field": "selected_null", "mine": mine_selected is None,
                               "delivered": their_selected is None})
            continue
        if mine_selected is None:
            continue
        for key in FIELDS:
            compared_fields += 1
            a = mine_selected.get(key)
            if key not in their_selected:
                # Early-return rows (no_first_decline / no_post_anchor_high /
                # no_setup) omit the field instead of emitting an explicit null.
                absent_fields.append({"event": record["event_id"], "rule": record["rule"],
                                      "field": key, "path_state": their_selected.get("path_state")})
                continue
            b = their_selected.get(key)
            if isinstance(a, float) and isinstance(b, (int, float)):
                if abs(a - b) > 1e-9:
                    mismatches.append({"event": record["event_id"], "rule": record["rule"],
                                       "field": key, "mine": a, "delivered": b})
            elif a != b:
                mismatches.append({"event": record["event_id"], "rule": record["rule"],
                                   "field": key, "mine": a, "delivered": b})

    fingerprints = {
        "engine.py": sha256(ENGINE),
        "strategy.py": sha256(STRATEGY),
        "event_chain.py": sha256(CHAIN),
        "shape-selection-paths.csv": sha256(PATHS),
        "platform-firstboard-flags.csv": sha256(FLAGS),
        "verify_candidate_replay.py": sha256(Path(__file__).resolve()),
    }
    expected_prefixes = {
        "engine.py": "FBC27443DF15AC3C",
        "strategy.py": "9AB50B399D1F5C89",
    }
    prefix_checks = {
        name: fingerprints[name][:16].upper() == expected
        for name, expected in expected_prefixes.items()
    }

    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "method": "independent re-implementation from the written candidate rules; "
                  "compared against event-replay-v01/candidate-classifications.json",
        "delivered_self_check_note": (
            "the delivered self-check compares classify(prefix) with classify(batch) "
            "where batch contains exactly the rows of prefix, so it tests determinism, not causality"
        ),
        "rows_compared": compared_rows,
        "fields_compared": compared_fields,
        "mismatches": len(mismatches),
        "mismatch_details": mismatches[:50],
        "absent_fields": len(absent_fields),
        "absent_field_details": absent_fields[:20],
        "fingerprints": fingerprints,
        "fingerprint_prefix_checks": prefix_checks,
        "scope": {
            "events": 27,
            "candidate_rows": 432,
            "not_covered": [
                "forward outcomes and daily tracking tables (evaluated separately)",
                "factor point-in-time integrity beyond the sampled fields",
                "first-board identity / historical ST / board regime",
            ],
        },
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 27事件/432条候选分类·独立复核",
        "",
        f"生成时间：{report['generated']}",
        "",
        "方法：按规则文字独立重实现，与 `event-replay-v01/candidate-classifications.json` 逐字段比对。",
        "",
        f"- 比对行数：{compared_rows}",
        f"- 比对字段：{compared_fields}",
        f"- 数值/标签不一致：{len(mismatches)}",
        f"- 交付行缺字段（早退分支未写 null）：{len(absent_fields)}",
        "",
        "## 交付方自检的局限",
        "",
        "交付的 `self_check_prefix_comparisons=432` 比较的是 `classify(prefix)` 与 "
        "`classify(batch)`，而 `batch` 与 `prefix` 是同一批行，只能证明确定性，不能证明因果性。"
        "因此需要本次独立重算。",
        "",
        "## 文件指纹",
        "",
        "| 文件 | SHA256 前16 | 与终审记录一致 |",
        "|---|---|---|",
    ]
    for name in ("engine.py", "strategy.py"):
        lines.append(
            f"| {name} | `{fingerprints[name][:16].upper()}` | {prefix_checks[name]} |"
        )
    lines.append(f"| event_chain.py | `{fingerprints['event_chain.py'][:16].upper()}` | 记录用 |")
    lines += ["", "## 未覆盖", ""]
    lines += [f"- {item}" for item in report["scope"]["not_covered"]]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"rows={compared_rows} fields={compared_fields} mismatches={len(mismatches)}")
    print(f"fingerprint prefixes: {prefix_checks}")
    for item in mismatches[:10]:
        print("  DIFF", item)
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
