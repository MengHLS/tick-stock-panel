"""Check v0.1.2: the remaining `new_high_after_anchor` nulls, and nothing else moved.

Scope asked for by the lead: only the 24 additions and that the original values
are unchanged.  No other check is repeated here.

Run from the repository root:
    cd backend && uv run --frozen python \
        ../docs/research/firstboard-classification-draft-20261027/verification/verify_schema_v012.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRAFT = HERE.parent
V011 = DRAFT / "event-replay-v011-schema" / "candidate-classifications.json"
V012 = DRAFT / "event-replay-v012-schema" / "candidate-classifications.json"
DIFFS = DRAFT / "event-replay-v012-schema" / "schema-differences.json"
OUT_JSON = HERE / "schema-v012-check.json"
OUT_MD = HERE / "SCHEMA-V012-CHECK.md"

FIELD = "new_high_after_anchor"
EXPECTED_CODE = {
    "no_first_decline": "NO_FIRST_DECLINE_BEFORE_D",
    "no_post_anchor_high": "POST_ANCHOR_HIGH_REQUIREMENT_FAILED",
    "no_setup": "NO_PREBREAK_SETUP_LOW",
}


def nodes(record: dict):
    classification = record["classification"]
    selected = classification.get("selected")
    if selected is not None:
        yield "selected", selected
    for index, item in enumerate(classification.get("trace") or []):
        yield f"trace[{index}]", item


def strip(record: dict) -> dict:
    out = json.loads(json.dumps(record))
    for _, node in nodes(out):
        codes = node.get("null_reason_codes")
        if isinstance(codes, dict) and FIELD in codes:
            codes.pop(FIELD)
            if not codes:
                node.pop("null_reason_codes")
        if FIELD in node and node[FIELD] is None:
            node.pop(FIELD)
    return out


def main() -> int:
    old = json.loads(V011.read_text(encoding="utf-8"))
    new = json.loads(V012.read_text(encoding="utf-8"))
    diffs = json.loads(DIFFS.read_text(encoding="utf-8"))
    key = lambda record: (record["event_id"], record["rule"])  # noqa: E731
    old_map = {key(record): record for record in old}
    new_map = {key(record): record for record in new}
    problems: list[str] = []

    if len(old_map) != 432 or len(new_map) != 432:
        problems.append(f"row count old={len(old_map)} new={len(new_map)}")
    if set(old_map) != set(new_map):
        problems.append("record key sets differ")

    added = 0
    by_node = {"selected": 0, "trace": 0}
    missing_codes: list[str] = []
    wrong_codes: list[str] = []
    rows_touched = 0

    for record_key, new_record in new_map.items():
        old_record = old_map[record_key]
        touched = False
        for (path, new_node), (_, old_node) in zip(nodes(new_record), nodes(old_record)):
            if FIELD in old_node:
                if new_node.get(FIELD) != old_node[FIELD]:
                    problems.append(f"{record_key} {path} {FIELD} changed")
                continue
            if new_node.get(FIELD, "absent") is not None:
                problems.append(f"{record_key} {path} {FIELD} not null")
                continue
            added += 1
            by_node[path.split("[")[0]] += 1
            touched = True
            code = (new_node.get("null_reason_codes") or {}).get(FIELD)
            expected = EXPECTED_CODE.get(new_node.get("path_state"))
            if code is None:
                missing_codes.append(f"{record_key} {path}")
            elif expected and code != expected:
                wrong_codes.append(f"{record_key} {path} {code}")
        rows_touched += 1 if touched else 0

    stripped_diffs = [str(k) for k in old_map if strip(new_map[k]) != old_map[k]]
    untouched_drift = [
        str(k) for k in old_map
        if k not in {r for r in set(new_map) if strip(new_map[r]) != old_map[r]}
        and strip(new_map[k]) != old_map[k]
    ]

    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "records": {"v0.1.1": len(old_map), "v0.1.2": len(new_map)},
        "added_null_fields": added,
        "added_by_node_type": by_node,
        "rows_touched": rows_touched,
        "difference_entries": len(diffs) if isinstance(diffs, list) else None,
        "missing_or_mismatched_reason_codes": len(missing_codes) + len(wrong_codes),
        "rows_that_differ_after_stripping": len(stripped_diffs),
        "problems": problems[:20],
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# v0.1.2 补键·独立核对（仅本项）",
        "",
        f"生成时间：{report['generated']}",
        "",
        f"- 新增 `{FIELD}` 空值：{added} 处（selected {by_node['selected']}、trace {by_node['trace']}），涉及 {rows_touched} 条记录",
        f"- 差异清单条目：{report['difference_entries']}",
        f"- 原因码缺失或不符：{report['missing_or_mismatched_reason_codes']}",
        f"- 移除新增项后与 v0.1.1 不一致的记录：{len(stripped_diffs)}",
        f"- 原值被改动：{len(problems)}",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({k: report[k] for k in
                      ("added_null_fields", "added_by_node_type", "rows_touched",
                       "missing_or_mismatched_reason_codes", "rows_that_differ_after_stripping")},
                     ensure_ascii=False))
    for item in problems[:5]:
        print("PROBLEM", item)
    ok = (added == 24 and not problems and not missing_codes and not wrong_codes
          and not stripped_diffs and len(new_map) == 432)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
