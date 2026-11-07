# -*- coding: utf-8 -*-
import duckdb
con = duckdb.connect()
D = r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
M = r"D:\TSP\data\kline_minute\**\*.parquet"
print("== daily last 6 days: rows, sum amount(亿), max quote/update ==")
try:
    print(con.execute("""SELECT date, count(*) n, round(sum(amount)/1e8,0) amt_yi
      FROM read_parquet(?, union_by_name=true) WHERE date >= DATE '2026-10-29'
      GROUP BY date ORDER BY date""",[D]).fetchdf().to_string())
except Exception as e:
    print("ERR", e)
print()
print("== daily columns ==")
print(list(con.execute("SELECT * FROM read_parquet(?, union_by_name=true) LIMIT 0",[D]).fetchdf().columns))
print()
print("== minute last days: bars, symbols, max datetime ==")
print(con.execute("""SELECT date, count(*) bars, count(DISTINCT symbol) nsym, max(datetime) mx
  FROM read_parquet(?, union_by_name=true) WHERE date >= DATE '2026-11-03'
  GROUP BY date ORDER BY date""",[M]).fetchdf().to_string())
