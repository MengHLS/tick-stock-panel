import json
from pathlib import Path
import polars as pl
P = Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent/"results"
R = json.loads((P/"research/strategy-search-20261107/results/run_S01_ma_cross_20_60_10.json").read_text(encoding="utf-8"))
r = pl.DataFrame(R["trades"])
p = pl.read_parquet(P/"research/s01b-20261108/results/a0_10bp/trades.parquet")
out={}
for name, df in (("research", r), ("prod", p)):
    s = df.sort("pnl_amount", descending=True)
    tot = float(s["pnl_amount"].sum())
    out[name] = {"n": s.height, "pnl_sum": round(tot,2),
        "top5_pnl": round(float(s["pnl_amount"].head(5).sum()),2),
        "top5_share": round(float(s["pnl_amount"].head(5).sum())/tot,4) if tot else None,
        "top10_pnl": round(float(s["pnl_amount"].head(10).sum()),2),
        "top1": s.select("symbol","entry_date","pnl_pct","pnl_amount").head(3).to_dicts(),
        "best_pnl_pct": round(float(s["pnl_pct"].max()),4),
        "worst_pnl_pct": round(float(s["pnl_pct"].min()),4),
        "n_gt_50pct": int((s["pnl_pct"]>0.5).sum()),
        "pnl_from_gt_50pct": round(float(s.filter(pl.col("pnl_pct")>0.5)["pnl_amount"].sum()),2)}
for k,v in out.items(): print(k, json.dumps(v, ensure_ascii=False, default=str))
(OUT/"tails.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
