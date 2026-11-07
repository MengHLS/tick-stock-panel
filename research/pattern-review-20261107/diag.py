# -*- coding: utf-8 -*-
"""Diagnose the touch test: why so many 09:30 'touches'?"""
import duckdb, pandas as pd, io

con = duckdb.connect()
D = r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
M = r"D:\TSP\data\kline_minute\**\*.parquet"
buf = io.StringIO()
def p(*a): print(*a, file=buf)

p("daily 复权 vs minute 复权一致性检查")
q = """
WITH d AS (SELECT symbol, date, close, raw_close, high, raw_high,
   LAG(close) OVER (PARTITION BY symbol ORDER BY date) pc
 FROM read_parquet(?, union_by_name=true) WHERE date = DATE '2026-11-05'),
m AS (SELECT symbol, date, max(high) mhigh, min(low) mlow, sum(volume) mvol
 FROM read_parquet(?, union_by_name=true) WHERE date = DATE '2026-11-05' GROUP BY symbol,date)
SELECT d.symbol, round(d.close,2) dclose, round(d.raw_close,2) raw_close,
 round(m.mhigh,2) minute_high, round(m.mlow,2) minute_low, round(d.high,2) dhigh
FROM d JOIN m USING(symbol,date) WHERE m.mhigh IS NOT NULL LIMIT 10
"""
p(con.execute(q, [D, M]).fetchdf().to_string(index=False))

p("")
p("minute 表 09:30 bar 的 high 是否等于当日 high（抽样）")
q2 = """
WITH m30 AS (SELECT symbol, date, high h30, open o30 FROM read_parquet(?, union_by_name=true)
  WHERE date=DATE '2026-11-05' AND strftime(datetime,'%H:%M')='09:30'),
d AS (SELECT symbol, date, high dhigh, open dopen, close dclose FROM read_parquet(?, union_by_name=true) WHERE date=DATE '2026-11-05')
SELECT count(*) n,
  sum(CASE WHEN abs(m30.h30 - d.dhigh) < 0.011 THEN 1 ELSE 0 END) h_equal,
  sum(CASE WHEN m30.h30 >= d.dhigh - 0.011 THEN 1 ELSE 0 END) h_ge
FROM m30 JOIN d USING(symbol,date)
"""
p(con.execute(q2, [M, D]).fetchdf().to_string(index=False))

p("")
p("检查：minute 是否有 09:31 之前以外的异常 bar 数")
p(con.execute("""SELECT strftime(datetime,'%H:%M') hm, count(*) n, count(DISTINCT symbol) nsym
 FROM read_parquet(?, union_by_name=true) WHERE date=DATE '2026-11-05'
 GROUP BY 1 ORDER BY n DESC LIMIT 5""", [M]).fetchdf().to_string(index=False))

open(r"C:\work\sourcecode\tick-stock-panel\research\pattern-review-20261107\diag.txt", "w", encoding="utf-8").write(buf.getvalue())
print("done")
