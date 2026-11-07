# -*- coding: utf-8 -*-
"""Build the 2026-11-05 limit-up pool with first-seal time + mainline tag."""
import duckdb, pandas as pd, os, json

con = duckdb.connect()
D = r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
M = r"D:\TSP\data\kline_minute\**\*.parquet"
LB = r"D:\TSP\data\ext_data\limit_board_events\**\*.parquet"
ML = r"D:\TSP\data\mainline_history\**\*.parquet"
GN = r"D:\TSP\data\ext_data\ext_gn_ths\**\*.parquet"
OUT = r"C:\work\sourcecode\tick-stock-panel\research\pattern-review-20261107"
os.makedirs(OUT, exist_ok=True)

names = con.execute(
    "SELECT DISTINCT symbol, name FROM read_parquet(?, union_by_name=true) WHERE name IS NOT NULL",
    [LB]).fetchdf()

con.execute("""CREATE TEMP TABLE lu AS
WITH d AS (SELECT symbol, date, open, high, low, close, amount, turnover_rate,
   consecutive_limit_ups AS lc,
   LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS pc
 FROM read_parquet(?, union_by_name=true) WHERE date >= DATE '2026-10-28')
SELECT symbol, close, high, amount, turnover_rate, lc, pc,
   CASE WHEN symbol LIKE '30%' OR symbol LIKE '688%' THEN 0.20 ELSE 0.10 END AS lim
FROM d WHERE date = DATE '2026-11-05' AND pc IS NOT NULL""", [D])

df = con.execute("""
SELECT l.symbol, l.lc, round(l.close,2) AS c, round(l.amount/1e8,2) AS amt_yi,
       round(l.turnover_rate,2) AS tr, min(m.datetime) AS first_seal
FROM lu l JOIN read_parquet(?, union_by_name=true) m
  ON m.symbol = l.symbol AND m.date = DATE '2026-11-05'
 AND m.high >= round(l.pc*(1+l.lim),2) - 0.011
WHERE l.close/l.pc - 1 >= l.lim - 0.005 AND l.close >= l.high - 0.001 AND l.amount > 5e7
GROUP BY l.symbol, l.lc, l.close, l.amount, l.turnover_rate""", [M]).fetchdf()

df["seal_hm"] = df.first_seal.dt.strftime("%H:%M")
df = df.merge(names, on="symbol", how="left")

# concept membership: third column holds the semicolon-joined concept names
gm = con.execute("SELECT * FROM read_parquet(?, union_by_name=true)", [GN]).fetchdf()
gm = gm.rename(columns={gm.columns[2]: "cname"})[["symbol", "cname"]]

top = con.execute("""SELECT member FROM read_parquet(?, union_by_name=true)
 WHERE date = DATE '2026-11-05' AND kind = 'concept' AND rank <= 10""", [ML]).fetchdf()
topmem = list(top["member"])
cmap = dict(zip(gm["symbol"], gm["cname"].astype(str)))

def tag(sym):
    s = cmap.get(sym, "")
    return "/".join([t for t in s.split(";") if t in topmem])

df["hot"] = df["symbol"].map(tag)
df = df.sort_values(["hot", "lc", "amt_yi"], ascending=[False, False, False])
df.to_csv(os.path.join(OUT, "pool_1105_seal.csv"), index=False, encoding="utf-8-sig")

lines = []
lines.append("11-05 limit-up pool: %d rows, %d sealed before 10:00" %
             (len(df), int((df.seal_hm < "10:00").sum())))
lines.append("mainline top10 (11-05): " + " | ".join(topmem))
for _, r in df.head(50).iterrows():
    lines.append("%-12s %-10s %d板 %8.2f %6.2f亿 换%5.2f%% 首封%s  %s" %
                 (r["symbol"], str(r["name"])[:10], int(r.lc), r.c, r.amt_yi, r.tr, r.seal_hm, r.hot))
open(os.path.join(OUT, "pool_1105_seal.txt"), "w", encoding="utf-8").write("\n".join(lines))
print("done", len(df))
