# -*- coding: utf-8 -*-
"""独立复算 §7.12.4（契约代码原样，不用产物里的 canonical_digest 函数）+ 四类扰动。"""
import json, hashlib, copy, pathlib, sys

p = pathlib.Path("docs/architecture/evidence/referenced_factor_inventory.json")
d = json.loads(p.read_text(encoding="utf-8"))
DROP = {"generated_at", "repo_head", "data_root", "canonical_digest"}
rk = lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def digest(obj):
    q = {k: v for k, v in obj.items() if k not in DROP}
    q["records"] = sorted(q.get("records", []), key=rk)
    blob = json.dumps(q, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

got = digest(d)
print("落盘 canonical_digest :", d["canonical_digest"])
print("独立复算(契约原样)     :", got)
print("一致                   :", got == d["canonical_digest"])

# 1) 改 generated_at/repo_head/data_root → 不变
t = copy.deepcopy(d)
t["generated_at"] = "1999-01-01T00:00:00+08:00"
t["repo_head"] = "0" * 40
t["data_root"] = "X:/elsewhere/user_data"
print("扰动(生成时刻/head/数据根) → 不变:", digest(t) == got)

# 2) records 倒序 → 不变
t2 = copy.deepcopy(d); t2["records"] = list(reversed(t2["records"]))
print("扰动(records 倒序)         → 不变:", digest(t2) == got)

# 3) records 随机重排（固定种子）→ 不变
import random
t3 = copy.deepcopy(d); random.Random(20261107).shuffle(t3["records"])
print("扰动(records 随机重排)     → 不变:", digest(t3) == got)

# 4) 改一条 primary 的 verdict → 必变
t4 = copy.deepcopy(d)
for r in t4["records"]:
    if r["record_kind"] == "primary":
        r["verdict"] = "block" if r["verdict"] != "block" else "allow"
        break
print("扰动(改 1 条 verdict)      → 必变:", digest(t4) != got)

# 5) 只有 side_key 变（模拟 v3→v3.1 的回退：全置 null）→ 必变
t5 = copy.deepcopy(d)
for r in t5["records"]:
    r["side_key"] = None
print("扰动(side_key 全置 null)   → 必变:", digest(t5) != got)
sys.exit(0 if got == d["canonical_digest"] else 1)
