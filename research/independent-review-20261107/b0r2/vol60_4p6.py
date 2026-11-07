"""按 REGISTRATION_B0:219 的确切定义复算 4.6%：vol60 列本身，pct_change 式 vs 减法式，
60 只标的 / 116,287 行探针。"""
import sys
from pathlib import Path
PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(PROJECT / "backend"))
sys.path.insert(0, str(PROJECT / "research" / "strategy-search-20261107" / "scripts"))
import common, polars as pl

m = common.open_market(); f = common.load_panel(m)
syms = f["symbol"].unique().sort().to_list()[:60]
base = f.filter(pl.col("symbol").is_in(syms)).sort(["symbol", "date"]).select(
    ["symbol", "date", "open", "high", "low", "close", "volume", "amount"])
print("probe rows:", base.height, "symbols:", len(syms))

def vol60(ret_expr):
    return (base.with_columns(ret_expr.alias("ret"))
                .with_columns(pl.col("ret").rolling_std(60).over("symbol").alias("v"))["v"])

prev = pl.col("close").shift(1).over("symbol")
a = vol60(pl.col("close") / prev - 1)                 # 文字式 x/shift-1
b = vol60((pl.col("close") - prev) / prev)            # 减法式（B0 采用）
d = a.cast(pl.Float64) - b.cast(pl.Float64)
mask = a.is_not_null() & b.is_not_null()
nb = int(mask.sum())
neq = int(((d.abs() > 0) & mask).sum())
print(f"vol60 literal vs subtraction: n_both={nb} nonzero={neq} share={100*neq/nb:.3f}%")
print(f"other denominators: /{base.height} rows = {100*neq/base.height:.3f}%")
print("author claims 4.6% on 116,287 rows (probe_vol60.py)")
