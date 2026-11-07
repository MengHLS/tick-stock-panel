# -*- coding: utf-8 -*-
"""把产物与因子侧期望表 v3.2 做逐字段比对（多重集 + 逐字段），side_key 单独统计。"""
import json, sys, collections, pathlib

art_p = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                     "docs/architecture/evidence/referenced_factor_inventory.json")
exp_p = pathlib.Path("docs/factors/evidence/referenced_factor_inventory_expected_20261107.json")
art = json.loads(art_p.read_text(encoding="utf-8"))
exp = json.loads(exp_p.read_text(encoding="utf-8"))

exp_recs = list(exp["records"]) + list(exp["companion_records"])
# 期望表只覆盖 22 个活配置（93 条）；产物里取 source_enabled=true 的活配置子集
live = [r for r in art["records"] if r["source_enabled"] is True]
print(f"artifact  : {art_p}  records={len(art['records'])} live={len(live)}")
print(f"expected  : {exp_p}  v{exp['meta']['version']} records={len(exp['records'])} comp={len(exp['companion_records'])}")
print(f"live      : {len(live)}  expected total {len(exp_recs)}")

KEY = ("source_path", "evidence", "side", "ref_name", "record_kind")
def key(r):
    return tuple(r.get(k) for k in KEY)

ca, ce = collections.Counter(map(key, live)), collections.Counter(map(key, exp_recs))
print("\n== 多重集 (source_path, evidence, side, ref_name, record_kind)")
print(f"  artifact_only = {sum((ca - ce).values())}")
print(f"  expected_only = {sum((ce - ca).values())}")
for k, v in sorted((ca - ce).items()):
    print("   ART-ONLY", v, k)
for k, v in sorted((ce - ca).items()):
    print("   EXP-ONLY", v, k)

# 逐字段比对（按唯一键对齐）
idxa = {key(r): r for r in live}
idxp = {key(r): r for r in exp_recs}
common = sorted(set(idxa) & set(idxp), key=lambda t: tuple(str(x) for x in t))
fields = sorted({f for r in exp_recs for f in r} | {f for r in live for f in r})
print(f"\n== 逐字段比对（共同键 {len(common)} 条，字段并集 {len(fields)} 个）")
diffs = {}
for f in fields:
    bad = [(k, idxp[k].get(f), idxa[k].get(f)) for k in common if idxp[k].get(f) != idxa[k].get(f)]
    if bad:
        diffs[f] = bad
for f, bad in diffs.items():
    print(f"  {f}: 差异 {len(bad)} 条")
    for k, pe, pa in bad[:12]:
        print(f"     {k[0].split('/')[-1]}:{k[1].rsplit(':',1)[-1]} {k[2]}/{k[3]}/{k[4]}  expected={pe!r}  artifact={pa!r}")
if not diffs:
    print("  无差异")

print("\n== side_key 专项")
sk_bad = diffs.get("side_key", [])
print(f"  side_key 差异条数 = {len(sk_bad)} / {len(common)}")
non_none = [k for k in common if idxa[k].get("side_key")]
print(f"  产物 side_key 非 null = {len(non_none)} / {len(common)}")
print(f"  期望 side_key 非 null = {sum(1 for k in common if idxp[k].get('side_key'))}")
other = {f: v for f, v in diffs.items() if f != "side_key"}
print(f"  除 side_key 外差异字段数 = {len(other)} {sorted(other)}")

# 产物 218 条 side_key 覆盖情况
sk_all = collections.Counter("null" if r["side_key"] is None else r["side_key"] for r in art["records"])
print("\n== 产物全部 218 条的 side_key 分布")
for k, v in sorted(sk_all.items()):
    print(f"  {v:>4}  {k}")
nulls = [r for r in art["records"] if r["side_key"] is None]
print(f"\n  仍为 null: {len(nulls)} 条")
per = collections.Counter((r["source_kind"], r["source_path"].split("/")[-1]) for r in nulls)
for k, v in sorted(per.items()):
    print(f"    {v:>3}  {k[0]:<16} {k[1]}")
sys.exit(0 if not other else 1)
