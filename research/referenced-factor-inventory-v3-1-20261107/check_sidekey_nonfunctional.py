# -*- coding: utf-8 -*-
"""证明 side_key 确实「不参与判据 / 不进 allowlist / 不进唯一键」——不是靠注释，靠注入扰动。"""
import json, copy, hashlib, collections, pathlib, sys

p = pathlib.Path("docs/architecture/evidence/referenced_factor_inventory.json")
d = json.loads(p.read_text(encoding="utf-8"))
recs = d["records"]

# 1) 唯一键：契约 F-A34 键 = path+evidence+side+ref_name+record_kind，不含 side_key
def uniq(records):
    return [(r["source_path"], r["evidence"], r["side"], r["ref_name"], r["record_kind"]) for r in records]
keys = uniq(recs)
print(f"[F-A34] {len(keys)} 条 / 去重 {len(set(keys))} 条 → 重复 {len(keys)-len(set(keys))}")
dups = [k for k, v in collections.Counter(keys).items() if v > 1]
print("       重复键:", dups or "无")

# 2) 注入：把 side_key 全部替换成另一个合法值，verdict / code / namespace / class 必须一点不变
alt = copy.deepcopy(d)
for r in alt["records"]:
    r["side_key"] = "scoring" if r["side_key"] != "scoring" else "formula"
same = all((a["verdict"], a["code"], a["ref_namespace"], a["class"], a["resolved_id"])
           == (b["verdict"], b["code"], b["ref_namespace"], b["class"], b["resolved_id"])
           for a, b in zip(alt["records"], d["records"]))
print(f"[不参与判据] side_key 全部改写后 verdict/code/namespace/class/resolved_id 全等: {same}")
print(f"[不进唯一键] 改写后唯一键集合相同: {set(uniq(alt['records'])) == set(keys)}")

# 3) 唯一键集合与 v3 产物（side_key 全 null）是否相同 —— 直接证明 v3→v3.1 只动了 side_key
prev = json.loads(pathlib.Path("research/referenced-factor-inventory-v3-1-20261107/final_run_v3_prev.json")
                  .read_text(encoding="utf-8"))
print(f"[v3 对比] 记录数 {len(prev['records'])} → {len(recs)}；唯一键集合相同: "
      f"{set(uniq(prev['records'])) == set(keys)}")
diff_fields = collections.Counter()
for a, b in zip(prev["records"], recs):
    for f in a:
        if a[f] != b.get(f):
            diff_fields[f] += 1
print("[v3 对比] 逐字段变化:", dict(diff_fields) or "无")
# summary 是否变化
print("[v3 对比] summary 相同:", prev["summary"] == d["summary"])
print("[v3 对比] stale_count:", prev["stale_count"], "→", d["stale_count"])
sys.exit(0 if (len(set(keys)) == len(keys) and same and set(uniq(alt["records"])) == set(keys)) else 1)
