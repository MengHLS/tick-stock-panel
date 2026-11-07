import sys
from pathlib import Path

PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(PROJECT / "backend"))
sys.path.insert(0, str(PROJECT / "research" / "strategy-search-20261107" / "scripts"))
import common
import polars as pl
from app.factors.dsl import compile_formula
from app.factors.registry import get_factor
from app.strategy.scoring import materialize_scoring_columns

c = compile_formula("ts_std((close - ts_delay(close, 1)) / ts_delay(close, 1), 60)")
print("compile ok:", c.ok, "warmup:", c.warmup_bars, "deps:", sorted(c.dependencies))

m = common.open_market(); f = common.load_panel(m)
syms = f["symbol"].unique().sort().to_list()[:60]
part = f.filter(pl.col("symbol").is_in(syms)).sort(["symbol","date"])
base = part.select(["symbol","date","open","high","low","close","volume","amount"])
plat = materialize_scoring_columns(base, ("vol60",))
ref = common.add_indicators(part)["vol60"]
d = (plat["vol60"].cast(pl.Float64).fill_nan(None) - ref.cast(pl.Float64).fill_nan(None)).abs()
print("vol60 max_abs_diff:", d.max(), "neq:", int((d > 0).sum()), "n:", int(plat["vol60"].is_not_null().sum()))
print("warmup_bars:", get_factor("vol60").warmup_bars, "first_valid:", int(plat["vol60"].is_not_null().to_numpy().argmax()))
