"""Check the v0.1.1 schema fix: completeness, reason codes, and no value drift.

Also reconciles the two counts that disagreed in the group: 170 (my earlier
absent-key count on the selected object) versus 480 (the delivered count over
all JSON nodes).

Run from the repository root:
    cd backend && uv run --frozen python \
        ../docs/research/firstboard-classification-draft-20261027/verification/verify_schema_v011.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRAFT = HERE.parent
V01 = DRAFT / "event-replay-v01" / "candidate-classifications.json"
V011 = DRAFT / "event-replay-v011-schema" / "candidate-classifications.json"
DIFFS = DRAFT / "event-replay-v011-schema" / "schema-differences.json"
OUT_JSON = HERE / "schema-v011-check.json"
OUT_MD = HERE / "SCHEMA-V011-CHECK.md"

NEW_FIELDS = ("depth", "recovery_raw", "recovery_applicable")
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
    """Remove the fields/codes introduced by v0.1.1."""
    out = json.loads(json.dumps(record))
    for _, node in nodes(out):
        node.pop("null_reason_codes", None)
        for field in NEW_FIELDS:
            if node.get(field) is None:
                node.pop(field, None)
    return out


def main() -> int:
    old = json.loads(V01.read_text(encoding="utf-8"))
    new = json.loads(V011.read_text(encoding="utf-8"))
    diffs = json.loads(DIFFS.read_text(encoding="utf-8"))

    key = lambda record: (record["event_id"], record["rule"])  # noqa: E731
    old_map = {key(record): record for record in old}
    new_map = {key(record): record for record in new}

    problems: list[str] = []
    if len(old_map) != 432 or len(new_map) != 432:
        problems.append(f"row count old={len(old_map)} new={len(new_map)}")
    if set(old_map) != set(new_map):
        problems.append("record key sets differ")

    added_fields = 0
    missing_codes: list[str] = []
    wrong_codes: list[str] = []
    by_path: dict[str, int] = {}
    rows_with_additions = 0
    my_absent_on_selected = 0

    for record_key, new_record in new_map.items():
        old_record = old_map[record_key]
        additions = 0
        for (path, new_node), (_, old_node) in zip(nodes(new_record), nodes(old_record)):
            for field in NEW_FIELDS:
                if field in old_node:
                    if new_node.get(field) != old_node[field]:
                        problems.append(f"{record_key} {path} {field} value changed")
                    continue
                if new_node.get(field, "absent") != None:  # noqa: E711
                    problems.append(f"{record_key} {path} {field} not null after fix")
                    continue
                additions += 1
                added_fields += 1
                by_path[path.split("[")[0]] = by_path.get(path.split("[")[0], 0) + 1
                if path == "selected":
                    my_absent_on_selected += 1
                code = (new_node.get("null_reason_codes") or {}).get(field)
                expected = EXPECTED_CODE.get(new_node.get("path_state"))
                if code is None:
                    missing_codes.append(f"{record_key} {path} {field}")
                elif expected and code != expected:
                    wrong_codes.append(f"{record_key} {path} {field} {code}!={expected}")
        if additions:
            rows_with_additions += 1

    stripped_mismatch = []
    for record_key in old_map:
        if strip(new_map[record_key]) != old_map[record_key]:
            stripped_mismatch.append(str(record_key))

    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "records": {"old": len(old_map), "new": len(new_map)},
        "rows_with_additions": rows_with_additions,
        "added_null_fields": added_fields,
        "added_by_node_type": by_path,
        "my_earlier_count_selected_only": my_absent_on_selected,
        "delivered_difference_entries": len(diffs) if isinstance(diffs, list) else None,
        "missing_reason_codes": len(missing_codes),
        "wrong_reason_codes": len(wrong_codes),
        "stripped_rows_that_differ_from_v01": len(stripped_mismatch),
        "problems": problems[:20],
        "count_explanation": (
            "170 was the absent-key count on the selected node only; the delivered 480 "
            "counts the same three fields over selected plus every trace node"
        ),
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# v0.1.1 模式修正·独立核对",
        "",
        f"生成时间：{report['generated']}",
        "",
        f"- 记录数：v0.1 {len(old_map)} / v0.1.1 {len(new_map)}",
        f"- 含新增空值的记录：{rows_with_additions}",
        f"- 新增 null 处数：{added_fields}（selected {by_path.get('selected', 0)}，trace {by_path.get('trace', 0)}）",
        f"- 我此前的缺键计数（仅 selected）：{my_absent_on_selected}",
        f"- 原因码缺失：{len(missing_codes)}；原因码与状态不符：{len(wrong_codes)}",
        f"- 移除新增项后与 v0.1 不一致的记录：{len(stripped_mismatch)}",
        f"- 其他问题：{len(problems)}",
        "",
        "计数差异：170 只统计 selected 节点上缺失的字段；480 统计 selected 与全部 trace 节点上"
        "同样三个字段的新增 null 数，两者不是同一口径，不能互相印证也不能互相否定。",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in
                      ("rows_with_additions", "added_null_fields", "added_by_node_type",
                       "my_earlier_count_selected_only", "missing_reason_codes",
                       "wrong_reason_codes", "stripped_rows_that_differ_from_v01")},
                     ensure_ascii=False))
    if problems:
        print("PROBLEMS", problems[:5])
    return 0 if not problems and not missing_codes and not wrong_codes and not stripped_mismatch else 1


if __name__ == "__main__":
    raise SystemExit(main())
