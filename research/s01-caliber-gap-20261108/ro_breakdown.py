import json
from pathlib import Path
import polars as pl
HERE = Path(__file__).resolve().parent; OUT = HERE/"results"
ro = pl.read_parquet(OUT/"research_only_classified.parquet")
po = pl.read_parquet(OUT/"prod_only_classified.parquet")
print("ro cols:", ro.columns); print("po cols:", po.columns)
def agg(df, by=None):
    return (df.group_by(by).agg(pl.len().alias("n"), pl.col("pnl_amount").sum().round(2).alias("pnl_sum"),
            pl.col("pnl_pct").mean().round(6).alias("avg_pnl_pct"), (pl.col("pnl_pct")>0).mean().round(4).alias("win"))
            .sort("n", descending=True).to_dicts())
out = {}
for c in ["prod_signal","in_prod_pool_price","prod_open_positions","prod_buys_on_entry_date","board"]:
    if c in ro.columns:
        out[f"research_only_by_{c}"] = agg(ro, c)
for c in ["res_open_positions","res_buys_on_sig_date"]:
    if c in po.columns:
        out[f"prod_only_by_{c}"] = agg(po, c)
for k,v in out.items():
    print("\n===", k); [print(x) for x in v]
# 研究池内但未被研究侧选中 / 研究池外的划分汇总
if "in_prod_pool_price" in ro.columns:
    print("\nresearch_only in_prod_pool_price share:", ro["in_prod_pool_price"].mean())
(OUT/"gap_profiles2.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
