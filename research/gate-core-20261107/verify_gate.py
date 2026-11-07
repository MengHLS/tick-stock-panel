"""B2 闸门核心 —— 只读实测取证（不写 D:/TSP、不写产物目录）。"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from app.factors import gate

REPO = Path(r"C:/work/sourcecode/tick-stock-panel")
DSL = REPO / "backend" / "app" / "factors" / "dsl.py"
DATA_DIR = Path(r"D:/TSP/data")
STORE_DIR = DATA_DIR / "user_data" / "custom_factors"


def signature() -> dict:
    files = sorted(STORE_DIR.glob("*.json"))
    return {
        "dir_mtime_ns": STORE_DIR.stat().st_mtime_ns,
        "files": [[f.name, f.stat().st_size, f.stat().st_mtime_ns] for f in files],
    }


def dsl_state() -> dict:
    raw = DSL.read_bytes()
    stat = DSL.stat()
    return {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "mtime": time.strftime("%H:%M:%S", time.localtime(stat.st_mtime)),
    }


evidence: dict = {"dsl_before": dsl_state(), "store_before": signature()}

store_ids = sorted(json.loads(f.read_text(encoding="utf-8"))["id"] for f in sorted(STORE_DIR.glob("*.json")))
evidence["store_ids"] = store_ids

source = gate.RegistryFacts(DATA_DIR)
facts = {fid: source.facts(fid) for fid in store_ids}
evidence["store_facts"] = {
    fid: {"kind": f.kind, "status": f.status, "lang": f.lang, "registered": f.registered}
    for fid, f in facts.items()
}

prod = gate.assert_factors_usable(store_ids, "production", shadow=True, facts=source)
evidence["store_production"] = {
    "ok": prod.ok,
    "blocked": [[bid, status, code] for bid, status, code in prod.blocked],
    "codes": list(prod.codes()),
    "unknown": list(prod.unknown),
}
res = gate.assert_factors_usable(store_ids, "research", shadow=True, facts=source)
evidence["store_research_default"] = {"ok": res.ok, "n_blocked": len(res.blocked)}
res_allow = gate.assert_factors_usable(
    store_ids, "research", shadow=True, allow_non_active=True, facts=source
)
evidence["store_research_allow_non_active"] = {
    "ok": res_allow.ok,
    "non_active": list(res_allow.non_active),
}

allowlist = gate.load_live_config_allowlist()
evidence["live_config"] = {
    "records": allowlist.records,
    "sources": allowlist.sources,
    "primary": allowlist.primary,
    "companion": allowlist.companion,
    "ids": list(allowlist.ids),
}
live = gate.assert_factors_usable(allowlist.ids, "production", shadow=True, facts=source)
evidence["live_config_production"] = {
    "ok": live.ok,
    "blocked": [[bid, status, code] for bid, status, code in live.blocked],
}
live_research = gate.assert_factors_usable(
    allowlist.ids, "research", shadow=True, allow_non_active=True, facts=source
)
evidence["live_config_research_allow_non_active"] = {
    "ok": live_research.ok,
    "non_active": list(live_research.non_active),
}
live_diag = gate.assert_factors_usable(allowlist.ids, "diagnostic", shadow=True, facts=source)
evidence["live_config_diagnostic"] = {
    "ok": live_diag.ok,
    "non_active": list(live_diag.non_active),
}

# 每个活配置 id 的 kind（证明「管线列不 gate」这条归类的实际分布）
evidence["live_config_kinds"] = {
    fid: source.facts(fid).kind for fid in allowlist.ids
}

evidence["store_after"] = signature()
evidence["dsl_after"] = dsl_state()
evidence["store_untouched"] = evidence["store_before"] == evidence["store_after"]

out = REPO / "research" / "gate-core-20261107" / "EVIDENCE_gate_realdata.json"
out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("wrote", out)
print("dsl", evidence["dsl_after"])
print("store untouched:", evidence["store_untouched"], "files", len(evidence["store_ids"]))
print("store production blocked", len(evidence["store_production"]["blocked"]), evidence["store_production"]["codes"])
print("live production blocked", [b[0] for b in evidence["live_config_production"]["blocked"]])
