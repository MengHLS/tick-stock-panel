
import sys, pathlib
sys.path.insert(0, r"C:\work\sourcecode\tick-stock-panel\backend")
from app.factors import gate, registry
from app.factors.registry import FactorSpec
import dataclasses
cu = gate._column_universe()
print("column_universe n", len(cu))
for i in ["ma20","ma60","sd20","boll_lower","boll_upper","prior_amount_20","market_breadth","close","ma60"]:
    print("  in cu:", i, i in cu)
print("EXEMPT_KINDS", gate.EXEMPT_KINDS, "STATUSES", gate.STATUSES)
print("FactorSpec fields n:", len([f.name for f in dataclasses.fields(FactorSpec)]))
print([f.name for f in dataclasses.fields(FactorSpec)])
print("has 'status' field:", any(f.name=="status" for f in dataclasses.fields(FactorSpec)))
# BEFORE pack load: what does facts() say for ma20?
facts = gate.RegistryFacts("D:/TSP/data")
for i in ["ma20","ma60","sd20","boll_lower","boll_upper","prior_amount_20"]:
    f = facts.facts(i)
    print("pre-pack-load facts", i, "reg=%s kind=%s status=%r"%(f.registered,f.kind,f.status))
