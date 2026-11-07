
import sys
sys.path.insert(0, r"C:\work\sourcecode\tick-stock-panel\backend")
from app.factors import store, registry, gate
import inspect
# Does RegistryFacts have any status source other than store definitions?
print("RegistryFacts MRO:", [c.__name__ for c in gate.RegistryFacts.__mro__])
print("STORE subdir:", store._STORE.subdir)
# Check store.save_one signature / any API that accepts arbitrary id
print("save_one sig:", inspect.signature(store._STORE.save_one))
# can we register a spec directly (bypassing id regex)?
from app.factors.registry import FactorSpec, register_factor, peek_factor
existing = peek_factor("market_breadth")
print("peek market_breadth:", existing)
# Check what pack provides
from app.custom.research_factor_pack.factor_specs import RESEARCH_BASELINE_FACTOR_IDS, SPEC_BY_ID
print("pack ids:", sorted(RESEARCH_BASELINE_FACTOR_IDS))
for i in ["ma20","ma60","sd20","boll_lower","boll_upper","prior_amount_20"]:
    s=SPEC_BY_ID.get(i)
    print(i, "kind=",s.kind if s else None,"alias_of=",s.alias_of if s else None,"su=",s.strategy_usable if s else None, "warmup=",s.warmup_bars if s else None)
