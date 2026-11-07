# -*- coding: utf-8 -*-
"""The realistic 打板 execution: buy at limit price on the day it seals,
sell next day. Compare with 次日开盘买."""
import duckdb, pandas as pd, os, io

con = duckdb.connect()
D = r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
M = r"D:\TSP\data\kline_minute\**\*.parquet"
OUT = r"C:\work\sourcecode\tick-stock-panel\research\pattern-review-20261107"
buf = io.StringIO()
def p(*a): print(*a, file=buf)

con.execute("""CREATE TEMP TABLE lu AS
WITH d0 AS (
  SELECT symbol, date, open, high, low, close, amount, turnover_rate,
         consecutive_limit_ups AS lc,
         LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS pc,
         LEAD(open,1) OVER (PARTITION BY symbol ORDER BY date) AS nopen,
         LEAD(close,1) OVER (PARTITION BY symbol ORDER BY date) AS n1c,
         LEAD(close,2) OVER (PARTITION BY symbol ORDER BY date) AS n2c,
         LEAD(low,1) OVER (PARTITION BY symbol ORDER BY date) AS n1l
  FROM read_parquet(?, union_by_name=true) WHERE date >= DATE '2024-06-01' AND date <= DATE '2026-10-10')
SELECT *, CASE WHEN symbol LIKE '30%' OR symbol LIKE '688%' THEN 0.20 ELSE 0.10 END AS lim
FROM d0 WHERE pc IS NOT NULL""", [D])

lu = con.execute("""
SELECT symbol, date, lc, close, pc, lim, nopen, n1c, n2c, n1l, amount, turnover_rate,
       round(pc*(1+lim),2) AS limpx
FROM lu WHERE close/pc-1 >= lim-0.005 AND close >= high-0.001 AND amount > 5e7 AND lc >= 1
""").fetchdf()

seal = con.execute("""
WITH l AS (SELECT symbol, date, round(pc*(1+lim),2) AS limpx FROM lu)
SELECT mm.symbol, mm.date, min(mm.datetime) AS first_seal, count(*) AS bars
FROM read_parquet(?, union_by_name=true) mm
JOIN l ON l.symbol = mm.symbol AND l.date = mm.date
WHERE mm.high >= l.limpx - 0.011
GROUP BY mm.symbol, mm.date
""", [M]).fetchdf()

df = lu.merge(seal, on=["symbol", "date"], how="left")
df["seal_hm"] = df.first_seal.dt.strftime("%H:%M")
# 打板口径: 以涨停价买入（封板成交）, 次日开盘卖 / 次日收盘卖
df["d1_open"] = (df.nopen / df.limpx - 1) * 100     # 次日开盘卖
df["d1_close"] = (df.n1c / df.limpx - 1) * 100      # 次日收盘卖
df["touch_low"] = (df.n1l / df.limpx - 1) * 100     # 次日最低（最坏）

def stat(sub, label):
    s = sub.dropna(subset=["d1_open"])
    if len(s) == 0:
        p("%-26s n=0" % label); return
    p("%-26s n=%6d  次开卖%+6.2f%%  次收卖%+6.2f%%  胜率%5.1f%%  次日最坏%+6.2f%%" %
      (label, len(s), s.d1_open.mean(), s.d1_close.mean(),
       (s.d1_close > 0).mean() * 100, s.touch_low.mean()))

p("=" * 78)
p("打板真实口径：当日以涨停价买入（封板成交），次日卖出")
p("样本 2024-06~2026-10-10，连板>=1，成交额>5000万")
p("=" * 78)
stat(df, "全部")
for lo, hi, lab in [("09:30","09:31","09:30 开盘封"),
                    ("09:31","10:00","09:31-10:00 封"),
                    ("10:00","11:00","10:00-11:00 封"),
                    ("11:00","13:00","11:00-13:00 封"),
                    ("13:00","15:01","13:00 后封")]:
    stat(df[(df.seal_hm >= lo) & (df.seal_hm < hi)], lab)

p("")
p("--- 按连板数（全部封板时间）---")
for k in [1,2,3,4]:
    sub = df[df.lc == k] if k < 4 else df[df.lc >= 4]
    stat(sub, "%d板" % k if k < 4 else ">=4板")

p("")
p("--- 首封<10:00 且 连板>=2 且 换手>3% ---")
stat(df[(df.seal_hm < "10:00") & (df.lc >= 2) & (df.turnover_rate > 3)], "组合条件")

p("")
p("--- 首封<10:00 且 连板>=2 且 成交额>5亿 ---")
stat(df[(df.seal_hm < "10:00") & (df.lc >= 2) & (df.amount > 5e8)], "组合条件2")

open(os.path.join(OUT, "daban_real.txt"), "w", encoding="utf-8").write(buf.getvalue())
print("done", len(df))
