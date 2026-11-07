
import sys, json
sys.path.insert(0, r"C:\work\sourcecode\tick-stock-panel\backend")
from app.factors import store
# 1) reject test for market_breadth
cand = {
  "id":"market_breadth","kind":"custom","label":"市场宽度(收盘>MA60占比)","group":"市场状态",
  "formula":"xs_mean(close > ma60, in_universe)","description":"按日截面聚合、按标的广播",
  "direction":"none","status":"active","version":1,
}
try:
    spec = store.to_spec(cand)
    print("to_spec OK", spec.id)
except Exception as e:
    print("to_spec REJECT:", type(e).__name__, e)
# 2) confirm id pattern for a hypothetical uf_ prefixed market breadth
for i in ["market_breadth","uf_market_breadth"]:
    import re
    print(i, "matches CUSTOM_ID_PATTERN:", bool(store.CUSTOM_ID_PATTERN.match(i)),
          "| matches _FACTOR_ID_PATTERN:", bool(store._FACTOR_ID_PATTERN.match(i)))
# 3) compile the formula
from app.factors import dsl
c = dsl.compile_formula("xs_mean(close > ma60, in_universe)")
print("compile ok", c.ok, "warmup", c.warmup_bars, "cross_sectional", getattr(c,'cross_sectional',None))
print("errors", c.errors)
print("deps", sorted(c.dependencies))
