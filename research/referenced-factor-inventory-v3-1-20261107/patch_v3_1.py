# -*- coding: utf-8 -*-
"""v3.1 patch: fill real structural side_key for condition slots (conditions[i].left/right/field, overlay_filter[i].*)."""
import io, sys, pathlib

tgt = pathlib.Path("backend/scripts/build_referenced_factor_inventory.py")
src = tgt.read_text(encoding="utf-8")

def sub(old, new, label):
    global src
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"[patch] {label}: expected 1 occurrence, found {n}")
    src = src.replace(old, new, 1)
    print(f"[ok] {label}")

sub(
"""  `side_key`  = 结构键路径（`scoring` / `formula` / `members` / `fields.<名>`），可选，
                只做人读定位，**不参与任何判据、不进 allowlist、不进唯一键**；""",
"""  `side_key`  = 结构键路径（`conditions[<i>].left` / `conditions[<i>].right` /
                `conditions[<i>].field` / `overlay_filter[<i>].left` /
                `overlay_filter[<i>].right` / `scoring` / `formula` / `members` /
                `fields.<名>`），可选，只做人读定位，**不参与任何判据、不进 allowlist、
                不进唯一键**；它由扫描处的真实结构位置生成，不按名字猜；""",
"docstring side_key 取值域")

sub(
'''def _condition_occurrences(cond: dict, allowed: frozenset) -> list[tuple[str, str, str | None]]:
    """条件表达式的**逐出现**结构化引用：`(side, ref_raw, side_key)`。

    `left` → `side=L`，字面量原样；`right` 写成 `field:X` → `side=R` 且 `ref_raw="field:X"`
    （前缀保留，`ref_name` 去前缀）；`right` 直接写白名单列名 → `side=R`；数字右值不是
    引用，不产记录（与 `custom_signals._parse_right` 同口径）。条件里没有结构键，
    故 `side_key` 恒 None。
    """
    occ: list[tuple[str, str, str | None]] = []
    left = cond.get("left")
    if isinstance(left, str) and left.strip():
        occ.append(("L", left.strip(), None))
    right = cond.get("right")
    if isinstance(right, str) and right.strip():
        text = right.strip()
        name, prefix = split_prefix(text)
        if prefix is not None or name in allowed:
            occ.append(("R", text, None))
    return occ''',
'''def _condition_occurrences(cond: dict, allowed: frozenset, *, container: str,
                           index: int) -> list[tuple[str, str, str | None]]:
    """条件表达式的**逐出现**结构化引用：`(side, ref_raw, side_key)`。

    `left` → `side=L`，字面量原样；`right` 写成 `field:X` → `side=R` 且 `ref_raw="field:X"`
    （前缀保留，`ref_name` 去前缀）；`right` 直接写白名单列名 → `side=R`；数字右值不是
    引用，不产记录（与 `custom_signals._parse_right` 同口径）。

    `side_key` = 引用在源文件里的**真实结构路径**：`container`（`conditions` /
    `overlay_filter`）+ 该条件在数组里的原始下标，如 `conditions[1].right`。下标取数组
    下标而不是「第几条产出记录」，跳过的条件（非 dict / 非引用 / 数字右值）不改变其它
    条件的下标。
    """
    occ: list[tuple[str, str, str | None]] = []
    left_key = f"{container}[{index}].left"
    right_key = f"{container}[{index}].right"
    left = cond.get("left")
    if isinstance(left, str) and left.strip():
        occ.append(("L", left.strip(), left_key))
    right = cond.get("right")
    if isinstance(right, str) and right.strip():
        text = right.strip()
        name, prefix = split_prefix(text)
        if prefix is not None or name in allowed:
            occ.append(("R", text, right_key))
    return occ''',
"_condition_occurrences 结构路径")

sub(
"""        occurrences: list[tuple[str, str, str | None]] = []
        for cond in data.get("conditions") or []:
            if isinstance(cond, dict):
                occurrences.extend(_condition_occurrences(cond, resolver.allowed))
        rel = f"custom_signals/{path.name}\"""",
"""        occurrences: list[tuple[str, str, str | None]] = []
        for idx, cond in enumerate(data.get("conditions") or []):
            if isinstance(cond, dict):
                occurrences.extend(_condition_occurrences(cond, resolver.allowed,
                                                          container="conditions", index=idx))
        rel = f"custom_signals/{path.name}\"""",
"scan_custom_signals 传下标")

sub(
"""            # monitor 规则的引用槽位固定是 `conditions[].field` → `side=F`（§7.12.3）。
            occurrences.append(("F", field.strip(), None))""",
"""            # monitor 规则的引用槽位固定是 `conditions[].field` → `side=F`（§7.12.3）。
            occurrences.append(("F", field.strip(), f"conditions[{idx}].field"))""",
"scan_monitor_rules side_key")

sub(
"""        occurrences: list[tuple[str, str, str | None]] = []
        for cond in data.get("conditions") or []:
            if not isinstance(cond, dict):
                continue
            field = cond.get("field")""",
"""        occurrences: list[tuple[str, str, str | None]] = []
        for idx, cond in enumerate(data.get("conditions") or []):
            if not isinstance(cond, dict):
                continue
            field = cond.get("field")""",
"scan_monitor_rules 传下标")

sub(
"""        cond_occ: list[tuple[str, str, str | None]] = []
        for cond in data.get("overlay_filter") or []:
            if isinstance(cond, dict):
                cond_occ.extend(_condition_occurrences(cond, resolver.allowed))""",
"""        cond_occ: list[tuple[str, str, str | None]] = []
        for idx, cond in enumerate(data.get("overlay_filter") or []):
            if isinstance(cond, dict):
                cond_occ.extend(_condition_occurrences(cond, resolver.allowed,
                                                       container="overlay_filter", index=idx))""",
"scan_strategy_overrides 传容器+下标")

sub(
"""      * `side_key` 是结构键路径（`scoring` / `formula` / `members` / `fields.<名>`），
        不参与判定、不进 allowlist、不进唯一键。""",
"""      * `side_key` 是结构键路径（`conditions[<i>].left` / `conditions[<i>].right` /
        `conditions[<i>].field` / `overlay_filter[<i>].left` / `overlay_filter[<i>].right` /
        `scoring` / `formula` / `members` / `fields.<名>`），不参与判定、不进 allowlist、
        不进唯一键。""",
"emit docstring 结构键清单")

sub(
'''    "结构键路径（scoring/formula/members/fields.<名>）只进 side_key，不参与判定、不进唯一键。",''',
'''    "结构键路径（conditions[i].left / conditions[i].right / conditions[i].field / "
    "overlay_filter[i].left / overlay_filter[i].right / scoring / formula / members / "
    "fields.<名>）只进 side_key，不参与判定、不进唯一键。",''',
"NOTES 结构键清单")

sub(
'''    bad_side_key = [r for r in records if r["side_key"] is not None
                    and not (r["side_key"] in {"scoring", "formula", "members"}
                             or r["side_key"].startswith("fields."))]''',
'''    # 结构键路径的合法形态（判据不变：side_key 里只许结构路径，不许字面量/槽位）：
    # 条件槽位 conditions[i].left|right|field、overlay_filter[i].left|right，
    # 结构块 scoring / formula / members，research 的 fields.<名>。白名单随「真实结构
    # 位置」扩了两族，判据语义（结构键只进 side_key、side 仍只 L/R/F）未变。
    bad_side_key = [r for r in records if r["side_key"] is not None
                    and not SIDE_KEY_RE.match(r["side_key"])]''',
"F-A37 side_key 白名单改为结构路径正则")

sub(
'''EVIDENCE_RE = re.compile(r"^.+?:\d+(?:-\d+)?$")''',
'''EVIDENCE_RE = re.compile(r"^.+?:\d+(?:-\d+)?$")
# §7.10.2：`side_key` 的合法取值形态 = 真实结构键路径（见 `_condition_occurrences` /
# `scan_monitor_rules` / `formula_occurrences` / `scan_research_strategies` 的产出处）。
SIDE_KEY_RE = re.compile(
    r"^(?:conditions\[\d+\]\.(?:left|right|field)"
    r"|overlay_filter\[\d+\]\.(?:left|right)"
    r"|scoring|formula|members"
    r"|fields\.[A-Za-z_][A-Za-z0-9_]*)$")''',
"新增 SIDE_KEY_RE 常量")

tgt.write_text(src, encoding="utf-8", newline="\n")
print("[done] written", tgt)
