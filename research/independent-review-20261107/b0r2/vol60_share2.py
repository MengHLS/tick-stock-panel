"""用作者口径(60只票, common.load_panel 窗口)复算 pct_change vs 字面式 的不等占比。"""
import sys
from pathlib import Path
PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(PROJECT/"backend"))
sys.path.insert(0, str(PROJECT/"research"/"strategy-search-20261107"/"scripts"))
import common, polars as pl
m = common.open_market(); f = common.load_panel(m)
print("full panel rows:", f.height, "symbols:", f["symbol"].n_unique(),
      "date:", str(f["date"].min())[:10], "->", str(f["date"].max())[:10])
syms = f["symbol"].unique().sort().to_list()[:60]
part = f.filter(pl.col("symbol").is_in(syms)).sort(["symbol","date"])
print("60-symbol rows:", part.height)
prev = pl.col("close").shift(1).over("symbol")
part = part.with_columns([ (pl.col("close")/prev - 1).alias("f_lit"),
                           ((pl.col("close")-prev)/prev).alias("f_sub") ])
d = (part["f_sub"].cast(pl.Float64) - part["f_lit"].cast(pl.Float64))
v = d.drop_nulls(); n=len(v); nz=int((v!=0).sum())
print(f"AUTHOR-BASIS pct_change vs literal: n={n} nonzero={nz} share={100*nz/n:.3f}% max={float(v.abs().max()):.3e}")
# 全样本
prev2 = pl.col("close").shift(1).over("symbol")
f2 = f.sort(["symbol","date"]).with_columns([ (pl.col("close")/prev2 - 1).alias("f_lit"),
                                              ((pl.col("close")-prev2)/prev2).alias("f_sub") ])
d2=(f2["f_sub"].cast(pl.Float64)-f2["f_lit"].cast(pl.Float64)); v2=d2.drop_nulls()
n2=len(v2); nz2=int((v2!=0).sum())
print(f"FULL pct_change vs literal: n={n2} nonzero={nz2} share={100*nz2/n2:.3f}% max={float(v2.abs().max()):.3e}")
