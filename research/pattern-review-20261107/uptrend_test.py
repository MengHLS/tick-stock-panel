# -*- coding: utf-8 -*-
"""The one group that made money for the user: buy on a day the stock rises
5-9.5% WITHOUT hitting the limit. Test it market-wide."""
import duckdb, pandas as pd, os, io

con = duckdb.connect()
D = r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
OUT = r"C:\work\sourcecode\tick-stock-panel\research\pattern-review-20261107"
buf = io.StringIO()
def p(*a): print(*a, file=buf)

BT = """
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
 FROM read_parquet(?, union_by_name=true) WHERE date >= DATE '2024-06-01' AND date <= DATE '2026-10-10'),
x AS (SELECT *, (close/pc-1)*100 AS pct, (close/c20-1)*100 AS r20, (close/c60-1)*100 AS r60,
   (close/ma20-1)*100 AS dev, amount/NULLIF(ama20,0) AS vr,
   CASE WHEN symbol LIKE '30%' OR symbol LIKE '688%' THEN 1 ELSE 0 END AS is20
 FROM b WHERE c60 IS NOT NULL AND c20 IS NOT NULL AND ma20 IS NOT NULL)
SELECT grp, count(*) n, round(d1,2) d1, round(d3,2) d3, round(d5,2) d5, round(w1,1) win1 FROM (
 SELECT CASE
   WHEN pct BETWEEN 5 AND 9.4 AND lc=0 AND is20=0 THEN 'A 主板当日涨5-9.4%未涨停'
   WHEN pct BETWEEN 8 AND 19 AND lc=0 AND is20=1 THEN 'B 20cm板涨8-19%未涨停'
   WHEN pct BETWEEN 5 AND 9.4 AND lc=0 AND is20=0 AND r20<20 THEN '  A1 加20日涨幅<20%'
   WHEN pct BETWEEN 5 AND 9.4 AND lc=0 AND is20=0 AND r20>=20 THEN '  A2 加20日涨幅>=20%'
   WHEN pct BETWEEN 5 AND 9.4 AND lc=0 AND is20=0 AND dev>0 AND dev<10 THEN '  A3 加贴近MA20'
   WHEN pct BETWEEN 5 AND 9.4 AND lc=0 AND is20=0 AND vr>1.2 THEN '  A4 加量比>1.2'
   WHEN pct BETWEEN 5 AND 9.4 AND lc=0 AND is20=0 AND amount>3e8 THEN '  A5 加成交额>3亿'
   ELSE NULL END AS grp,
  avg((n1c/nopen-1)*100) d1, avg((n3c/nopen-1)*100) d3, avg((n5c/nopen-1)*100) d5,
  avg(CASE WHEN n1c>nopen THEN 100.0 ELSE 0 END) w1
 FROM x WHERE nopen IS NOT NULL GROUP BY 1
) WHERE grp IS NOT NULL ORDER BY grp
"""
p("=" * 84)
p("你自己数据里唯一赚钱的一组：当日涨5%+但没涨停 → 全市场检验")
p("次日开盘买，持1/3/5日。2024-06~2026-10-10，全A")
p("=" * 84)
p(con.execute(BT, [D]).fetchdf().to_string(index=False))

p("")
p("基准：全市场次日开盘买 持1/3/5日")
p(con.execute("""
WITH b AS (
 SELECT symbol,date,close,consecutive_limit_ups AS lc,
   LEAD(open,1) OVER (PARTITION BY symbol ORDER BY date) AS nopen,
   LEAD(close,1) OVER (PARTITION BY symbol ORDER BY date) AS n1c,
   LEAD(close,3) OVER (PARTITION BY symbol ORDER BY date) AS n3c,
   LEAD(close,5) OVER (PARTITION BY symbol ORDER BY date) AS n5c
 FROM read_parquet(?, union_by_name=true) WHERE date >= DATE '2024-06-01' AND date <= DATE '2026-10-10')
SELECT count(*) n, round(avg((n1c/nopen-1)*100),2) d1, round(avg((n3c/nopen-1)*100),2) d3,
 round(avg((n5c/nopen-1)*100),2) d5, round(avg(CASE WHEN n1c>nopen THEN 100.0 ELSE 0 END),1) win1
FROM b WHERE nopen IS NOT NULL""", [D]).fetchdf().to_string(index=False))

open(os.path.join(OUT, "uptrend_test.txt"), "w", encoding="utf-8").write(buf.getvalue())
print("done")
