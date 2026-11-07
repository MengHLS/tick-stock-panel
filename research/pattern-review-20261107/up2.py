# -*- coding: utf-8 -*-
"""Corrected: 当日涨5%+未涨停 组 全市场检验（修复 CASE 顺序 + 聚合报错）"""
import duckdb, io, os
con=duckdb.connect()
D = r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
buf=io.StringIO()
def p(*a): print(*a, file=buf)

con.execute("""CREATE TEMP TABLE x AS
WITH b AS (
 SELECT symbol,date,open,high,low,close,amount,turnover_rate,consecutive_limit_ups AS lc,
   AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20,
   AVG(amount) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ama20,
   LAG(close,20) OVER (PARTITION BY symbol ORDER BY date) AS c20,
   LAG(close,60) OVER (PARTITION BY symbol ORDER BY date) AS c60,
   LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS pc,
   LEAD(open,1) OVER (PARTITION BY symbol ORDER BY date) AS nopen,
   LEAD(close,1) OVER (PARTITION BY symbol ORDER BY date) AS n1c,
   LEAD(close,3) OVER (PARTITION BY symbol ORDER BY date) AS n3c,
   LEAD(close,5) OVER (PARTITION BY symbol ORDER BY date) AS n5c
 FROM read_parquet(?, union_by_name=true) WHERE date >= DATE '2024-06-01' AND date <= DATE '2026-10-10')
SELECT *, (close/pc-1)*100 AS pct, (close/c20-1)*100 AS r20, (close/c60-1)*100 AS r60,
  (close/ma20-1)*100 AS dev, amount/NULLIF(ama20,0) AS vr,
  CASE WHEN symbol LIKE '30%' OR symbol LIKE '688%' THEN 1 ELSE 0 END AS is20
FROM b WHERE c60 IS NOT NULL AND c20 IS NOT NULL AND ma20 IS NOT NULL AND amount>5e7""",[D])

def run(label, where):
    df=con.execute("""SELECT count(*) n, round(avg((n1c/nopen-1)*100),2) d1,
      round(avg((n3c/nopen-1)*100),2) d3, round(avg((n5c/nopen-1)*100),2) d5,
      round(avg(CASE WHEN n1c>nopen THEN 100.0 ELSE 0 END),1) w1,
      round(avg(CASE WHEN n5c>nopen THEN 100.0 ELSE 0 END),1) w5
      FROM x WHERE nopen IS NOT NULL AND """+where).fetchdf()
    r=df.iloc[0]
    p("%-38s n=%7d  D1%+6.2f%%  D3%+6.2f%%  D5%+6.2f%%  W1%5.1f%%  W5%5.1f%%"%(label,r.n,r.d1,r.d3,r.d5,r.w1,r.w5))

p("="*118)
p("你自己最赚钱的一组：当日涨5%+但没涨停 —— 全市场检验（次日开盘买，持1/3/5日）")
p("2024-06~2026-10-10，全A，成交额>5000万")
p("="*118)
run("基准 全市场",                       "1=1")
run("A 主板 当日涨5-9.4% 未涨停",        "pct BETWEEN 5 AND 9.4 AND lc=0 AND is20=0")
run("  A1 + 20日涨幅<20%",               "pct BETWEEN 5 AND 9.4 AND lc=0 AND is20=0 AND r20<20")
run("  A2 + 20日涨幅>=20%",              "pct BETWEEN 5 AND 9.4 AND lc=0 AND is20=0 AND r20>=20")
run("  A3 + 贴近MA20 (0<dev<10)",        "pct BETWEEN 5 AND 9.4 AND lc=0 AND is20=0 AND dev>0 AND dev<10")
run("  A4 + 量比>1.2",                   "pct BETWEEN 5 AND 9.4 AND lc=0 AND is20=0 AND vr>1.2")
run("  A5 + 成交额>3亿",                 "pct BETWEEN 5 AND 9.4 AND lc=0 AND is20=0 AND amount>3e8")
run("  A6 + 20日<20% 且 量比>1.2",       "pct BETWEEN 5 AND 9.4 AND lc=0 AND is20=0 AND r20<20 AND vr>1.2")
run("B 20cm 当日涨8-19% 未涨停",         "pct BETWEEN 8 AND 19 AND lc=0 AND is20=1")
run("C 主板 当日涨5-9.4% 连板>=1(涨停续)", "pct BETWEEN 5 AND 9.4 AND lc>=1 AND is20=0")
p("")
p("对照：涨停股（收盘买入价，非可成交）")
run("D 涨停 主板",                        "lc>=1 AND is20=0")
open(os.path.join(r"C:\work\sourcecode\tick-stock-panel\research\pattern-review-20261107","uptrend_test2.txt"),"w",encoding="utf-8").write(buf.getvalue())
print(buf.getvalue())
