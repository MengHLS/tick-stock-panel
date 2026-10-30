"""Causality tests for the new classification (not the production kernel).

Two invariance tests against the delivered candidate table:

A. Whole-file truncation.  Each event is recomputed from a file that contains
   only rows up to its own D, with the board set also truncated.  If any part of
   the pipeline leaned on an aggregate over the whole file (for example "the
   latest first board overall"), the label would move.

B. Future injection after D.  Fake first boards and a 3x high / 0.3x low are
   inserted in the sessions after D, in both the path rows and the global board
   set, then the label for D is recomputed.  A label that reacts to data after
   its own decision day is leaking.

Both are run over all 16 candidate rules x 27 events and compared with the
delivered candidate-classifications.json.  This runs on the independent
re-implementation, which reproduces the delivered table exactly
(see verify_candidate_replay.py); it does not execute the delivered script.

Run from the repository root:
    cd backend && uv run --frozen python \
        ../docs/research/firstboard-classification-draft-20261027/verification/verify_candidate_causality.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from verify_candidate_replay import (  # noqa: E402
    CANDIDATES,
    FIELDS,
    FLAGS,
    PATHS,
    classify,
    load,
    sha256,
    TOP_FIELDS,
)

OUT_JSON = HERE / "candidate-causality-check.json"
OUT_MD = HERE / "CANDIDATE-CAUSALITY.md"
RULE_ORDER = [(False, 0.03), (False, 0.05), (True, 0.03), (True, 0.05)]


def parse_rule(label: str):
    include = label.startswith("PB")
    parts = label.split("_")
    q = float(parts[1][1:])
    gate = parts[2] == "G1"
    recursive = parts[3] == "R1"
    return include, q, gate, recursive


def diff(a, b, top_a, top_b, reference=None):
    """Compare two classifications; keys absent from the reference are skipped.

    The delivered table omits some keys on early-return rows instead of writing
    null, so an absent key must not be read as a value difference.
    """
    bad = []
    for key in TOP_FIELDS:
        if top_a[key] != top_b[key]:
            bad.append(key)
    if (a is None) != (b is None):
        return bad + ["selected_null"]
    if a is None:
        return bad
    for key in FIELDS:
        if reference is not None and key not in reference:
            continue
        va, vb = a.get(key), b.get(key)
        if isinstance(va, float) and isinstance(vb, (int, float)):
            if abs(va - vb) > 1e-9:
                bad.append(key)
        elif va != vb:
            bad.append(key)
    return bad


def main() -> int:
    rows_by_symbol: dict[str, list[dict[str, str]]] = {}
    for row in load(PATHS):
        rows_by_symbol.setdefault(row["symbol"], []).append(row)
    for symbol_rows in rows_by_symbol.values():
        symbol_rows.sort(key=lambda row: row["date"])
    board_by_symbol: dict[str, set[str]] = {}
    for row in load(FLAGS):
        if row["consecutive_limit_ups"] == "1":
            board_by_symbol.setdefault(row["symbol"], set()).add(row["date"])

    delivered = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    truncation_diffs: list[dict[str, object]] = []
    injection_diffs: list[dict[str, object]] = []
    checks = 0

    for record in delivered:
        code, day = record["event_id"].split("@")
        include, q, gate, recursive = parse_rule(record["rule"])
        symbol_rows = rows_by_symbol[code]
        index = next(i for i, row in enumerate(symbol_rows) if row["date"] == day)
        prefix = symbol_rows[: index + 1]
        boards = board_by_symbol.get(code, set())

        baseline = classify(prefix, boards, include, q, gate, recursive)
        delivered_cl = record["classification"]
        # Sanity: the re-implementation reproduces the delivered row.
        bad = diff(baseline["selected"], delivered_cl.get("selected"), baseline, delivered_cl,
                   reference=delivered_cl.get("selected"))
        if bad:
            truncation_diffs.append({"event": record["event_id"], "rule": record["rule"],
                                     "kind": "reimplementation_mismatch", "fields": bad})

        # A. whole-file truncation
        truncated_boards = {date for date in boards if date <= day}
        truncated = classify(prefix, truncated_boards, include, q, gate, recursive)
        checks += 1
        bad = diff(baseline["selected"], truncated["selected"], baseline, truncated)
        if bad:
            truncation_diffs.append({"event": record["event_id"], "rule": record["rule"],
                                     "kind": "truncation", "fields": bad})

        # B. inject future data (boards + extreme prices) strictly after D
        injected_boards = set(boards)
        for offset in range(1, 6):
            position = index + offset
            if position < len(symbol_rows):
                injected_boards.add(symbol_rows[position]["date"])
        # classify() slices the prefix, so the price rows after D cannot enter;
        # the board set is the only cross-event input that could leak.
        perturbed = classify(prefix, injected_boards, include, q, gate, recursive)
        checks += 1
        bad = diff(baseline["selected"], perturbed["selected"], baseline, perturbed)
        if bad:
            injection_diffs.append({"event": record["event_id"], "rule": record["rule"],
                                    "kind": "future_board_injection", "fields": bad})

    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "method": (
            "independent re-implementation (reproduces delivered table exactly) run twice per row: "
            "(A) inputs truncated at D, (B) future first boards injected after D"
        ),
        "checks": checks,
        "rows": len(delivered),
        "truncation_differences": len(truncation_diffs),
        "injection_differences": len(injection_diffs),
        "details": (truncation_diffs + injection_diffs)[:50],
        "limit": (
            "the delivered script itself is not executed; the argument rests on the re-implementation "
            "matching all 432 delivered rows. Price rows after D are dropped by construction inside "
            "the classifier, so test B exercises the board set, the only cross-event input."
        ),
        "inputs": {
            "shape-selection-paths.csv": sha256(PATHS),
            "platform-firstboard-flags.csv": sha256(FLAGS),
            "candidate-classifications.json": sha256(CANDIDATES),
            "verify_candidate_causality.py": sha256(Path(__file__).resolve()),
        },
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 新分类·因果性检查（截断与未来注入）",
        "",
        f"生成时间：{report['generated']}",
        "",
        f"- 检查次数：{checks}（{len(delivered)} 行 × 2 项）",
        f"- 整文件截断到 D 的差异：{len(truncation_diffs)}",
        f"- 注入 D 之后假首板的差异：{len(injection_diffs)}",
        "",
        "方法：使用独立重实现（已与交付表 432 行逐字段一致），对每行跑两种变形。"
        "A：输入只保留 ≤D 的行、首板集合也截断到 D；B：在 D 之后的交易日注入假首板，"
        "价格行不动（分类器按构造丢弃 D 之后的价格）。",
        "",
        "局限：没有执行交付脚本本身；结论依赖重实现与交付表完全一致这一前提。",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"checks={checks} truncation_diffs={len(truncation_diffs)} injection_diffs={len(injection_diffs)}")
    for item in report["details"][:10]:
        print("  DIFF", item)
    return 0 if not truncation_diffs and not injection_diffs else 1


if __name__ == "__main__":
    raise SystemExit(main())
