
import sys
sys.path.insert(0, r"C:\work\sourcecode\tick-stock-panel\backend")
from app.factors import registry, dsl, gate
print("registry len", len(registry._REGISTRY))
print("get market_breadth:", registry.get_factor("market_breadth"))
print("in BASE_COLUMNS:", "market_breadth" in dsl.BASE_COLUMNS)
print("in _column_universe:", "market_breadth" in gate._column_universe())
print("BASE_COLUMNS n", len(dsl.BASE_COLUMNS))
print("column_universe n", len(gate._column_universe()))
print("registry ids n", len(registry.list_factors()) if hasattr(registry,'list_factors') else '?')
# XS operator xs_mean arity
c = dsl.compile_formula("xs_mean(close > ma60, in_universe)")
print("compile xs_mean ok?", c.ok, c.errors[:2])
print("deps", sorted(c.dependencies) if c.ok else None, "warmup", c.warmup_bars if c.ok else None)
