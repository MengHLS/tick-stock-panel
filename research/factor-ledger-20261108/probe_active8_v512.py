# -*- coding: utf-8 -*-
"""v5.12 留痕实测：8 只 uf_* 的盘上 status/updated_at/version + production 闸门（canonical 侧）。"""
from __future__ import annotations
import json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
DATA_DIR = Path("D:/TSP/data")
CDIR = DATA_DIR / "user_data" / "custom_factors"
IDS = ["uf_vol60","uf_ma120","uf_ma200","uf_prior_high_20","uf_prior_high_55",
       "uf_prior_high_250","uf_prior_low_10","uf_prior_vol_20"]

def main() -> int:
    from app.factors import gate, store
    from app.factors.store import load_into_registry
    from app.extensions.factors import ensure_factor_providers
    load_into_registry(DATA_DIR); ensure_factor_providers()
    facts = gate.RegistryFacts(DATA_DIR)
    rows=[]
    for fid in IDS:
        d=json.loads((CDIR/(fid+".json")).read_text(encoding="utf-8"))
        row={"id":fid,"disk_status":d.get("status"),"updated_at":d.get("updated_at"),
             "version":d.get("version")}
        try:
            rep=gate.assert_factors_usable([fid],"production",facts=facts,shadow=True)
            row["code"]=None; row["blocked"]=[]
        except gate.GateError as e:
            row["code"]=e.code; row["blocked"]=[b[2] for b in e.report.blocked]
        row["fact_status"]=getattr(facts.facts(fid),"status","<none>")
        rows.append(row)
    print(json.dumps(rows,ensure_ascii=False,indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
