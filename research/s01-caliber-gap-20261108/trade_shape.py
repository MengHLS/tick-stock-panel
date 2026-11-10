import json
from pathlib import Path
import polars as pl
P = Path(__file__).resolve().parents[2]; HERE=Path(__file__).resolve().parent; OUT=HERE/"results"
R = json.loads((P/"research/strategy-search-20261107/results/run_S01_ma_cross_20_60_10.json").read_text(encoding="utf-8"))
r = pl.DataFrame(R["trades"]).with_columns(pl.col("entry_date").str.to_date())
p = pl.read_parquet(P/"research/s01b-20261108/results/a0_10bp/trades.parquet").with_columns(pl.col("entry_date").str.to_date())
out = {}
out["n"] = {"research": r.height, "prod": p.height}
out["open_at_end"] = {"research": int(r["open_at_end"].sum()), "prod": int(p["open_at_end"].sum())}
out["final_positions"] = {"research": R.get("final_positions")}
out["exit_reason"] = {"research": r.group_by("exit_reason").len().sort("len",descending=True).to_dicts(),
                      "prod": p.group_by("exit_reason").len().sort("len",descending=True).to_dicts()}
out["entry_year"] = {"research": r.group_by(pl.col("entry_date").dt.year().alias("y")).len().sort("y").to_dicts(),
                     "prod": p.group_by(pl.col("entry_date").dt.year().alias("y")).len().sort("y").to_dicts()}
out["entry_score"] = {"research_unique": r["entry_score"].unique().to_list()[:5],
                      "prod_unique_n": p["entry_score"].n_unique(),
                      "prod_top": p["entry_score"].unique().sort(descending=True).to_list()[:5]}
out["date_range"] = {"research": [str(r["entry_date"].min()), str(r["entry_date"].max())],
                     "prod": [str(p["entry_date"].min()), str(p["entry_date"].max())]}
out["avg_hold"] = {"research": round(float(r["duration"].mean()),2), "prod": round(float(p["duration"].mean()),2)}
out["board_mix"] = {"research": r.group_by(pl.col("symbol").str.slice(0,2).alias("pref")).len().sort("len",descending=True).to_dicts(),
                    "prod": p.group_by(pl.col("symbol").str.slice(0,2).alias("pref")).len().sort("len",descending=True).head(8).to_dicts()}
for k,v in out.items(): print(k, "=", json.dumps(v, ensure_ascii=False, default=str))
(OUT/"trade_shape.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
