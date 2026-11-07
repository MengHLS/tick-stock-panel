# -*- coding: utf-8 -*-
"""v5.11 订正实测：6 个 pack 单侧件在两个命名面（factor / column）下 production 的闸门码。

只读真盘，不改任何文件。目的：核实「4 个撞名名字接线后被打成什么码」，
把 FS01 / FS03 / 0 码 三种可能分开，不许用推断替代实测。

用法：cd backend && PYTHONUTF8=1 ./.venv/Scripts/python.exe ../research/factor-ledger-20261108/probe_namespace_v511.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
DATA_DIR = Path("D:/TSP/data")

SIX = ["ma20", "ma60", "sd20", "boll_lower", "boll_upper", "prior_amount_20"]
COLLIDE4 = ["ma20", "ma60", "boll_lower", "boll_upper"]


def main() -> int:
    from app.factors import gate, registry, store
    from app.extensions.factors import ensure_factor_providers

    store.load_into_registry(DATA_DIR)
    ensure_factor_providers()
    facts = gate.RegistryFacts(DATA_DIR)

    def probe(fid: str, ns: str) -> dict:
        row = {"id": fid, "namespace": ns}
        try:
            rep = gate.assert_factors_usable([fid], "production", facts=facts,
                                             namespace=ns, shadow=True)
            blocked = [(b[0], b[1], b[2]) for b in rep.blocked]
            row["error_code"] = blocked[0][2] if blocked else None
            row["blocked_codes"] = [b[2] for b in blocked]
        except gate.GateError as exc:
            codes = [item[2] for item in exc.report.blocked]
            row["error_code"] = exc.code
            row["blocked_codes"] = codes
            row["detail_status"] = exc.detail.get("status") if isinstance(exc.detail, dict) else None
        except Exception as exc:  # noqa: BLE001
            row["error_code"] = "EXC:" + type(exc).__name__
            row["msg"] = str(exc)[:200]
        spec = registry.get_factor(fid)
        row["registered"] = spec is not None
        row["spec_kind"] = None if spec is None else spec.kind
        row["spec_alias_of"] = None if spec is None else spec.alias_of
        row["fact_status"] = getattr(facts.facts(fid), "status", "<no-fact>")
        return row

    out = {"data_dir": str(DATA_DIR), "rows": []}
    for fid in SIX:
        for ns in ("factor", "column"):
            out["rows"].append(probe(fid, ns))
    # 对照组：一只已升 active 的 canonical，证明真盘 status 读取本身是通的
    out["control"] = probe("uf_vol60", "factor")
    # 对照：alias 走 factor 面应是 FS03
    out["control_alias"] = probe("vol60", "factor")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
