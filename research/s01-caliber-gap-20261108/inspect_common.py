import json
from pathlib import Path
import polars as pl
P = Path(__file__).resolve().parents[2]
R = json.loads((P/"research/strategy-search-20261107/results/run_S01_ma_cross_20_60_10.json").read_text(encoding="utf-8"))
r = pl.DataFrame(R["trades"])
p = pl.read_parquet(P/"research/s01b-20261108/results/a0_10bp/trades.parquet")
print("research cols:", r.columns)
print("prod cols:", p.columns)
kr = set(zip(r["symbol"].to_list(), r["entry_date"].to_list()))
kp = set(zip(p["symbol"].to_list(), p["entry_date"].to_list()))
common = sorted(kr & kp)
print("common:", common)
rc = r.with_columns(pl.struct("symbol","entry_date").is_in([{"symbol":s,"entry_date":d} for s,d in common]).alias("c")).filter(pl.col("c"))
pc = p.with_columns(pl.struct("symbol","entry_date").is_in([{"symbol":s,"entry_date":d} for s,d in common]).alias("c")).filter(pl.col("c")).sort("entry_date")
rc = rc.sort("entry_date")
pl.Config.set_tbl_cols(-1); pl.Config.set_tbl_width_chars(400); pl.Config.set_tbl_rows(50)
print("\n=== RESEARCH common rows ===")
print(rc)
print("\n=== PROD common rows ===")
print(pc)
