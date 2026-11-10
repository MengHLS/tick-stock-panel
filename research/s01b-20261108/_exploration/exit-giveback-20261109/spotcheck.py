# -*- coding: utf-8 -*-
"""抽查：3 笔的持有窗口收盘序列 vs 明细里的 peak_close_raw / peak_date"""
import polars as pl
import numpy as np

OUT = r"C:\work\sourcecode\tick-stock-panel\research\s01b-20261108\_exploration\exit-giveback-20261109"
df = pl.read_csv(OUT + r"\giveback_trades.csv", infer_schema_length=None)
ENR = r"D:\TSP\data\kline_daily_enriched"

picks = [df.sort("giveback_yuan", descending=True).head(1).to_dicts()[0],
         df.filter(pl.col("exit_reason") == "signal").sort("giveback_yuan", descending=True).head(1).to_dicts()[0],
         df.filter(pl.col("peak_gain") >= 3.0).head(1).to_dicts()[0]]
lines = []
for r in picks:
    lo, hi = r["entry_date"], r["exit_date"]
    g = (pl.scan_parquet(ENR + r"\date=*\*.parquet")
         .select(["symbol", "date", "close", "raw_close"])
         .filter((pl.col("symbol") == r["symbol"]) & (pl.col("date") >= pl.lit(lo).str.to_date())
                 & (pl.col("date") <= pl.lit(hi).str.to_date()))
         .collect().sort("date"))
    rc = g["raw_close"].to_numpy().astype(float)
    i = int(np.argmax(rc))
    lines.append(f"{r['symbol']} {lo}->{hi} n={g.height} entry={r['entry_price_raw']} exit={r['exit_price_raw']} "
                 f"peak_calc={rc[i]:.4f}@{g['date'][i]} peak_csv={r['peak_close_raw']}@{r['peak_date']} "
                 f"peak_gain_csv={r['peak_gain']} giveback_yuan={r['giveback_yuan']} "
                 f"first5={[round(x,2) for x in rc[:5]]} last5={[round(x,2) for x in rc[-5:]]}")
open(OUT + r"\_spotcheck.txt", "w", encoding="utf-8").write("\n".join(lines))
print("ok")
