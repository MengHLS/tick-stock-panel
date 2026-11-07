# -*- coding: utf-8 -*-
"""v5.13 复核：4 个撞名名字在 2 个命名面各出什么码 + 活信号里改名的引用写法。

只读真盘 + 进程内调用闸门（不写盘、不改代码、不注册任何东西）。
输出 JSON 到 stdout；落盘副本 research/factor-ledger-20261108/probe_collision_faces.json。
"""
from __future__ import annotations
import glob, json, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
DATA_DIR = Path("D:/TSP/data")
SIG_DIR = DATA_DIR / "user_data" / "custom_signals"
NAMES = ["ma20", "ma60", "boll_lower", "boll_upper"]


def gate_codes(gate, n, face):
    """返回该 id 在该命名面上的码列表；0 码 = []。签名不支持 namespace 时如实记 TypeError。"""
    try:
        gate.assert_factors_usable([n], mode="production", entry="probe", namespace=face)
        return []
    except TypeError as e:                      # 旧签名无 namespace
        return {"_typeerror": str(e)}
    except gate.GateError as e:
        return getattr(e, "codes", None) or [getattr(e, "code", None)]


def main() -> int:
    from app.factors import gate, store
    from app.extensions.factors import ensure_factor_providers
    store.load_into_registry(DATA_DIR)
    ensure_factor_providers()

    faces = {f: [{"id": n, "codes": gate_codes(gate, n, f)} for n in NAMES]
             for f in ("factor", "column")}

    # 活信号引用写法：数 bare vs field:
    sigs, refs = [], {"total": 0, "field_prefixed": 0, "bare": []}
    for p in sorted(glob.glob(str(SIG_DIR / "*.json"))):
        d = json.load(open(p, encoding="utf-8"))
        if not any(re.search(r"\b" + n + r"\b", json.dumps(d, ensure_ascii=False)) for n in NAMES):
            continue
        per = []
        for c in d.get("conditions", []):
            for side in ("left", "right"):
                v = c.get(side, "")
                bare = v[6:] if v.startswith("field:") else v
                if bare in NAMES:
                    refs["total"] += 1
                    if v.startswith("field:"):
                        refs["field_prefixed"] += 1
                    else:
                        refs["bare"].append({"signal": d["id"], "side": side, "value": v})
                    per.append(f"{side}={v}")
        sigs.append({"id": d["id"], "kind": d.get("kind"), "enabled": d.get("enabled"), "refs": per})

    out = {
        "probe": "collision_faces_v513",
        "script": "research/factor-ledger-20261108/probe_collision_faces.py",
        "data_dir": str(DATA_DIR),
        "gate_signature_has_namespace": "namespace" in gate.assert_factors_usable.__code__.co_varnames,
        "faces": faces,
        "live_signals": {"count": len(sigs), "signals": sigs, "ref_forms": refs},
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
