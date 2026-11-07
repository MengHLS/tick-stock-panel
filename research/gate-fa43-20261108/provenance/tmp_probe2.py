
import sys
sys.path.insert(0, r"C:\work\sourcecode\tick-stock-panel\backend")
from app.factors import registry, dsl
print("ALL_FACTORS", len(registry.ALL_FACTORS) if hasattr(registry,'ALL_FACTORS') else '?')
names=[n for n in dir(registry) if n.isupper()]
print("UPPER", names)
try:
    cat = registry._CATALOG
    print("CATALOG", len(cat))
except Exception as e:
    print("cat err", e)
print("compile_formula sig", dsl.compile_formula.__doc__)
print("dsl funcs", sorted(dsl._FUNCS.keys()) if hasattr(dsl,'_FUNCS') else [n for n in dir(dsl) if not n.startswith('_')])
