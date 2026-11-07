# -*- coding: utf-8 -*-
"""独立回源：不经生成器，直接读源 JSON，按 side_key 路径取到字面量，与 ref_raw 逐条对齐。

这不复用生成器的任何解析函数；路径用正则解析成键/下标，再在 json.load 的对象上真取一次。
"""
import json, re, pathlib, sys

USER_DATA = pathlib.Path("D:/TSP/data/user_data")
art = json.loads(pathlib.Path("docs/architecture/evidence/referenced_factor_inventory.json")
                 .read_text(encoding="utf-8"))
live = [r for r in art["records"] if r["source_enabled"] is True]

PATH_RE = re.compile(r"^(?P<head>[A-Za-z_][A-Za-z0-9_]*)(?:\[(?P<idx>\d+)\])?(?:\.(?P<tail>[A-Za-z_][A-Za-z0-9_]*))?$")

def walk(obj, path):
    """按 side_key 的路径形态真取一次：dict 键 / 数组下标。取不到抛 KeyError。"""
    m = PATH_RE.match(path)
    if not m:
        raise KeyError(f"路径形态不合法: {path}")
    cur = obj[m.group("head")]
    if m.group("idx") is not None:
        cur = cur[int(m.group("idx"))]
    if m.group("tail") is not None:
        cur = cur[m.group("tail")]
    return cur

bad, checked, skipped = [], 0, []
for r in live:
    rel, sk = r["source_path"], r["side_key"]
    if r["source_kind"] not in ("custom_signal", "monitor_rule"):
        skipped.append((r["source_kind"], rel, sk)); continue
    data = json.loads((USER_DATA / rel).read_text(encoding="utf-8"))
    try:
        got = walk(data, sk)
    except (KeyError, IndexError, TypeError) as exc:
        bad.append((rel, r["evidence"], sk, f"取不到: {exc!r}")); continue
    checked += 1
    if not (isinstance(got, str) and got.strip() == r["ref_raw"]):
        bad.append((rel, r["evidence"], sk, f"源里是 {got!r}，记录 ref_raw 是 {r['ref_raw']!r}"))

print(f"活配置 93 条：回源比对 {checked} 条（custom_signal + monitor_rule），跳过 {len(skipped)} 条")
for s in skipped:
    print(f"  跳过（非条件槽位）: {s[0]} {s[1].split('/')[-1]} side_key={s[2]}")
print(f"不一致 {len(bad)} 条")
for b in bad:
    print("  MISMATCH", b)

# 期望表也做同样回源，确认它给的结构路径同样能在源里取到（只做核对，不据以填值）
exp = json.loads(pathlib.Path("docs/factors/evidence/referenced_factor_inventory_expected_20261107.json")
                 .read_text(encoding="utf-8"))
exp_bad, exp_checked = [], 0
for r in exp["records"] + exp["companion_records"]:
    if r["source_kind"] not in ("custom_signal", "monitor_rule"):
        continue
    data = json.loads((USER_DATA / r["source_path"]).read_text(encoding="utf-8"))
    try:
        got = walk(data, r["side_key"])
    except Exception as exc:
        exp_bad.append((r["source_path"], r["evidence"], r["side_key"], repr(exc))); continue
    exp_checked += 1
    if not (isinstance(got, str) and got.strip() == r["ref_raw"]):
        exp_bad.append((r["source_path"], r["evidence"], r["side_key"], got))
print(f"\n期望表 v3.2 同样回源：比对 {exp_checked} 条，不一致 {len(exp_bad)} 条")
for b in exp_bad:
    print("  EXP-MISMATCH", b)
sys.exit(0 if not bad and not exp_bad else 1)
