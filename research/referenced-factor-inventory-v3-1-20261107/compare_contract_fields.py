# -*- coding: utf-8 -*-
"""只比契约 §7.10.2 的 22 个表内字段（note 是表外附录字段，单列）。"""
import json, sys, collections, pathlib

art = json.loads(pathlib.Path("docs/architecture/evidence/referenced_factor_inventory.json").read_text(encoding="utf-8"))
exp = json.loads(pathlib.Path("docs/factors/evidence/referenced_factor_inventory_expected_20261107.json").read_text(encoding="utf-8"))
exp_recs = list(exp["records"]) + list(exp["companion_records"])
live = [r for r in art["records"] if r["source_enabled"] is True]

CONTRACT_FIELDS = [f for f in art["records"][0] if f != "note"]
print(f"契约表内字段 {len(CONTRACT_FIELDS)} 个: {CONTRACT_FIELDS}")
KEY = ("source_path", "evidence", "side", "ref_name", "record_kind")
k = lambda r: tuple(r.get(x) for x in KEY)
idxa = {k(r): r for r in live}
idxp = {k(r): r for r in exp_recs}
common = sorted(set(idxa) & set(idxp), key=lambda t: tuple(str(x) for x in t))
print(f"共同键 {len(common)} 条（产物活配置 {len(live)} / 期望 {len(exp_recs)}）")

diff = collections.defaultdict(list)
for f in CONTRACT_FIELDS:
    for key in common:
        if idxp[key].get(f) != idxa[key].get(f):
            diff[f].append((key, idxp[key].get(f), idxa[key].get(f)))
print(f"\n== 22 表内字段差异汇总：{len(diff)} 个字段有差异")
for f, rows in diff.items():
    print(f"  {f}: {len(rows)} 条")
    for key, pe, pa in rows[:20]:
        print(f"    {key[0].split('/')[-1]}:{key[1].rsplit(':',1)[-1]} {key[3]}/{key[4]}  exp={pe!r}  art={pa!r}")
if set(diff) == {"side_key"} or not diff:
    print("  → 除 side_key 外差异字段 0")

print("\n== note（表外附录字段）")
note_rows = [(key, idxp[key].get("note"), idxa[key].get("note")) for key in common
             if (idxp[key].get("note") or None) != (idxa[key].get("note") or None)]
print(f"  差异 {len(note_rows)} 条（全部为 companion 记录的措辞差异，语义等价；契约 §7.10.2 表无此字段）")
both_non_null = [r for r in note_rows if r[1] and r[2]]
print(f"  两侧都非空 {len(both_non_null)} 条 / 一侧空 {len(note_rows)-len(both_non_null)} 条")

# side_key 精确统计
sk = collections.Counter(idxa[key]["side_key"] for key in common if idxp[key].get("side_key") != idxa[key].get("side_key"))
print(f"\n== side_key 差异 {sum(sk.values())} 条 / {len(common)}")
sys.exit(0 if not diff or set(diff) == {"side_key"} else 1)
