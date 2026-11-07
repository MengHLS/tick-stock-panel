
import sys
sys.path.insert(0, r"C:\work\sourcecode\tick-stock-panel\backend")
from app.factors import registry, dsl, gate, store
print("registry before load:", len(registry._REGISTRY))
print("loaded:", store.load_into_registry(__import__("pathlib").Path("D:/TSP/data")))
print("registry after load:", len(registry._REGISTRY))
ids = sorted(registry._REGISTRY.keys())
print("n ids", len(ids))
print("count uf_:", sum(1 for i in ids if i.startswith("uf_")))
print("count cf_:", sum(1 for i in ids if i.startswith("cf_")))
print("== gate for 6 single ids ==")
facts = gate.RegistryFacts("D:/TSP/data")
for i in ["ma20","ma60","sd20","boll_lower","boll_upper","prior_amount_20"]:
    f = facts.facts(i)
    try:
        r = gate.assert_factors_usable([i], mode="production", facts=facts)
        print("PASS", i, "| facts reg=%s kind=%s status=%r" % (f.registered,f.kind,f.status))
    except gate.GateError as e:
        print("BLOCK", i, "codes=", e.report.codes(), "|", str(e)[:90])
