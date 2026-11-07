"""R11 撞名条款取证：只读，不写 D:/TSP、不写任何产物、不改 backend。

测量项：
  P1  活配置 allowlist 的 19 个引用名
  P2  每个名的 RegistryFacts（kind / status / registered）
  P3  _column_universe() 规模与 19 名成员关系
  P4  ALLOWED_FIELDS 成员关系（N2 的四个冲突名）
  P5  三种 mode 下的判定（shadow=True，不抛异常）
  P6  assert_factors_usable 的实际签名（是否已有 namespace 入参）
  P7  反证：把非列名当成 column 面会发生什么（当前实现没有入参，只能证明无门）
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

REPO = Path(r"C:/work/sourcecode/tick-stock-panel")
sys.path.insert(0, str(REPO / "backend"))

from app.factors import gate  # noqa: E402
from app.factors.dsl import BASE_COLUMNS  # noqa: E402
from app.strategy.custom_signals import ALLOWED_FIELDS  # noqa: E402

DATA_DIR = Path(r"D:/TSP/data")

out: dict = {}

# P1
allow = gate.load_live_config_allowlist()
ids = list(allow.ids)
out["P1_allowlist"] = {
    "records": allow.records,
    "sources": allow.sources,
    "primary": allow.primary,
    "companion": allow.companion,
    "n_ids": len(ids),
    "ids": ids,
}

# P2
src = gate.RegistryFacts(DATA_DIR)
facts = {fid: src.facts(fid) for fid in ids}
out["P2_facts"] = {
    fid: {"kind": f.kind, "status": f.status, "registered": f.registered, "lang": f.lang}
    for fid, f in facts.items()
}

# P3
universe = gate._column_universe()
out["P3_column_universe"] = {
    "n": len(universe),
    "BASE_COLUMNS_n": len(BASE_COLUMNS),
    "ids_in_universe": [fid for fid in ids if fid in universe],
    "ids_not_in_universe": [fid for fid in ids if fid not in universe],
}

# P4
out["P4_allowed_fields"] = {
    "n_ALLOWED_FIELDS": len(ALLOWED_FIELDS),
    "ids_in_ALLOWED_FIELDS": [fid for fid in ids if fid in ALLOWED_FIELDS],
    "collision_4": {name: name in ALLOWED_FIELDS for name in ("ma20", "ma60", "boll_lower", "boll_upper")},
}

# P5
def verdict(mode: str, **kw) -> dict:
    rep = gate.assert_factors_usable(ids, mode, shadow=True, facts=src, **kw)
    return {
        "ok": rep.ok,
        "blocked": [[b[0], b[1], b[2]] for b in rep.blocked],
        "n_blocked": len(rep.blocked),
        "non_active": list(rep.non_active),
        "unknown": list(rep.unknown),
    }


out["P5_production"] = verdict("production")
out["P5_research_default"] = verdict("research")
out["P5_research_allow"] = verdict("research", allow_non_active=True)
out["P5_diagnostic"] = verdict("diagnostic")

# P6
sig = inspect.signature(gate.assert_factors_usable)
out["P6_signature"] = {
    "text": str(sig),
    "params": [
        {"name": p.name, "kind": str(p.kind), "default": None if p.default is inspect._empty else repr(p.default)}
        for p in sig.parameters.values()
    ],
    "has_namespace": "namespace" in sig.parameters,
}

# P7：当前实现没有命名面入参 → column 面无法被声明；同名 spec 恒压过列全集
out["P7_collision_mechanism"] = {
    "gate_py_order": "RegistryFacts.facts: spec/definition 非空时走 provider 分支，_column_universe 只在 spec 与 definition 都为空时才被查",
    "facts_for_collision_4": {
        name: {"kind": facts[name].kind, "status": facts[name].status} for name in ("ma20", "ma60", "boll_lower", "boll_upper")
    },
    "in_universe": {name: name in universe for name in ("ma20", "ma60", "boll_lower", "boll_upper")},
}

print(json.dumps(out, ensure_ascii=False, indent=2))
