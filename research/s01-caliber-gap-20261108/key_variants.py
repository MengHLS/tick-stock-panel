"""§4 53 来源核查 + §1/§2 差集画像聚合（只读，仅写本目录 results/）。"""
import json
from pathlib import Path
import polars as pl

P = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / "results"
R = json.loads((P/"research/strategy-search-20261107/results/run_S01_ma_cross_20_60_10.json").read_text(encoding="utf-8"))
print("research json top keys:", list(R.keys()))
r = pl.DataFrame(R["trades"]).with_columns(pl.col("entry_date").str.to_date(), pl.col("exit_date").str.to_date())
p = pl.read_parquet(P/"research/s01b-20261108/results/a0_10bp/trades.parquet").with_columns(
    pl.col("entry_date").str.to_date(), pl.col("exit_date").str.to_date())

res = {"n_research": r.height, "n_prod": p.height,
       "net_count_diff": r.height - p.height}
print(json.dumps(res))

def ov(name, keycols):
    kr = set(r.select(keycols).iter_rows())
    kp = set(p.select(keycols).iter_rows())
    return {"key": name, "research_rows_matched": sum(1 for t in r.select(keycols).iter_rows() if t in kp),
            "prod_rows_matched": sum(1 for t in p.select(keycols).iter_rows() if t in kr),
            "keys_common": len(kr & kp), "keys_r_only": len(kr-kp), "keys_p_only": len(kp-kr)}

variants = []
variants.append(ov("symbol+entry_date", ["symbol","entry_date"]))
variants.append(ov("symbol_only", ["symbol"]))
variants.append(ov("symbol+entry_month", [pl.col("symbol"), pl.col("entry_date").dt.strftime("%Y-%m")]))
variants.append(ov("symbol+entry_year", [pl.col("symbol"), pl.col("entry_date").dt.year()]))
variants.append(ov("entry_date_only", ["entry_date"]))
variants.append(ov("symbol+exit_date", ["symbol","exit_date"]))
variants.append(ov("symbol+entry_signal_date", ["symbol","entry_signal_date"]))
variants.append(ov("symbol+entry_date+exit_date", ["symbol","entry_date","exit_date"]))
for v in variants: print(v)

# ±1 交易日窗口
cal = sorted(set(r["entry_date"].to_list()) | set(p["entry_date"].to_list()))
idx = {d:i for i,d in enumerate(cal)}
rs = {(s, idx[d]) for s,d in zip(r["symbol"].to_list(), r["entry_date"].to_list())}
ps = {(s, idx[d]) for s,d in zip(p["symbol"].to_list(), p["entry_date"].to_list())}
near = sum(1 for s,i in ps if (s,i-1) in rs or (s,i+1) in rs)
variants.append({"key":"symbol+entry_date±1bar(prod→research)", "prod_rows_matched": near})
print(variants[-1])

# 同 symbol 且日期区间重叠（研究笔 vs 生产笔持仓区间有交集）
rr = r.select("symbol", pl.col("entry_date").alias("re"), pl.col("exit_date").alias("rx"))
pp = p.select("symbol", pl.col("entry_date").alias("pe"), pl.col("exit_date").alias("px"))
j = rr.join(pp, on="symbol", how="inner").filter((pl.col("re") <= pl.col("px")) & (pl.col("pe") <= pl.col("rx")))
print("overlapping-holding-interval pairs:", j.height, "distinct research trades involved:",
      j.select(pl.struct("symbol","re","rx").n_unique()).item())
variants.append({"key":"symbol+holding_interval_overlap", "pairs": j.height,
                 "research_trades_involved": int(j.select(pl.struct("symbol","re","rx").n_unique()).item()),
                 "prod_trades_involved": int(j.select(pl.struct("symbol","pe","px").n_unique()).item())})
(OUT/"key_variants.json").write_text(json.dumps({"n": res, "variants": variants}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

# ---- §1 公共 3 笔逐笔差 ----
key = ["symbol","entry_date"]
cols = ["entry_price","exit_date","exit_price","pnl_pct","pnl_amount","duration","exit_reason","shares","entry_value"]
j3 = r.select(key+cols).join(p.select(key+cols), on=key, how="inner", suffix="_p").sort("entry_date")
rows = []
for row in j3.iter_rows(named=True):
    gross = row["shares"]*(row["exit_price"]-row["entry_price"])
    rows.append({
        "symbol": row["symbol"], "entry_date": str(row["entry_date"]),
        "entry_price_eq": abs(row["entry_price"]-row["entry_price_p"])<1e-9,
        "exit_price_eq": abs(row["exit_price"]-row["exit_price_p"])<1e-9,
        "shares_r": row["shares"], "shares_p": row["shares_p"],
        "pnl_pct_r": round(row["pnl_pct"],6), "pnl_pct_p": round(row["pnl_pct_p"],6),
        "pnl_pct_diff": round(row["pnl_pct_p"]-row["pnl_pct"],7),
        "pnl_amount_r": round(row["pnl_amount"],2), "pnl_amount_p": round(row["pnl_amount_p"],2),
        "pnl_amount_diff": round(row["pnl_amount_p"]-row["pnl_amount"],2),
        "gross_pnl_by_shares_r": round(gross,2),
        "cost_r": round(gross-row["pnl_amount"],2), "cost_p": round(gross-row["pnl_amount_p"],2),
    })
for x in rows: print(x)
(OUT/"common_3_detail.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

# ---- §2 分桶（引用已有 parquet） ----
ro = pl.read_parquet(OUT/"research_only_classified.parquet")
po = pl.read_parquet(OUT/"prod_only_classified.parquet")
def agg(df, by=None):
    if by is None:
        return {"n": df.height, "avg_pnl_pct": round(float(df["pnl_pct"].mean()),6),
                "win": round(float((df["pnl_pct"]>0).mean()),4),
                "pnl_sum": round(float(df["pnl_amount"].sum()),2)}
    return (df.group_by(by).agg(pl.len().alias("n"), pl.col("pnl_amount").sum().round(2).alias("pnl_sum"),
                                pl.col("pnl_pct").mean().round(6).alias("avg_pnl_pct"),
                                (pl.col("pnl_pct")>0).mean().round(4).alias("win"))
            .sort("n", descending=True).to_dicts())
sec2 = {"research_only_total": agg(ro), "prod_only_total": agg(po)}
for c in ["prod_signal","in_prod_pool_price","fail_price_raw","fail_amount20","fail_bars120","board","gate"]:
    if c in po.columns and c in ro.columns:
        sec2[f"prod_only_by_{c}"] = agg(po, c)
        sec2[f"research_only_by_{c}"] = agg(ro, c)
    elif c in po.columns:
        sec2[f"prod_only_by_{c}"] = agg(po, c)
print(json.dumps({k:v for k,v in sec2.items() if "total" in k}, ensure_ascii=False))
(OUT/"gap_profiles.json").write_text(json.dumps(sec2, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("\n--- prod_only gate ---"); print(pl.DataFrame(sec2["prod_only_by_gate"]))
print("\n--- research_only prod_signal/in_prod_pool_price ---"); print(pl.DataFrame(sec2["research_only_by_prod_signal"]))
