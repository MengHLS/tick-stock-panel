import sys
from pathlib import Path

PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(PROJECT / "backend"))
from app.factors.dsl import compile_formula
from app.factors.registry import all_factors

exprs = [
    "ma20 > ma60",
    "close < boll_lower",
    "(close > prior_high_55) and (volume > 1.5 * prior_vol_20)",
    "close / prior_high_250 - 1 >= -0.03",
    "(ma20 > ma60) and (close > ma120)",
    "ts_std((close - ts_delay(close,1)) / ts_delay(close,1), 60) > 0",
]
for e in exprs:
    c = compile_formula(e)
    print(f"{'OK ' if c.ok else 'ERR'} {e}  errors={[x.code for x in c.errors]} deps={sorted(c.dependencies) if c.ok else '-'} warmup={c.warmup_bars if c.ok else '-'}")

facs = sorted(all_factors(), key=lambda s: s.id)
print("\ntotal:", len(facs))
print("ids:", [s.id for s in facs])
