# -*- coding: utf-8 -*-
import json
from pathlib import Path

p = Path("C:/work/sourcecode/tick-stock-panel/docs/architecture/evidence/referenced_factor_inventory.json")
d = json.loads(p.read_text(encoding="utf-8"))
print("top keys:", list(d.keys()))
print("schema_version:", d.get("schema_version"))
print("records:", len(d.get("records", [])))
print("sources:", len(d.get("sources", [])))
lc = (d.get("summary") or {}).get("live_config") or {}
print("live_config keys:", list(lc.keys()))
for k, v in lc.items():
    if isinstance(v, list):
        print("  ", k, "->", len(v))
    else:
        print("  ", k, "->", v)
prim = lc.get("primary") or []
print("primary sample:", prim[:5])
print("unique primary ids:", len({(r.get("factor_id") or r.get("id")) for r in prim if isinstance(r, dict)}))
