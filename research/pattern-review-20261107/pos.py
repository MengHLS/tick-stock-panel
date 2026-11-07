# -*- coding: utf-8 -*-
import duckdb
con=duckdb.connect()
D = r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
LB = r"D:\TSP\data\ext_data\limit_board_events\**\*.parquet"
print("== 603618 last 12 sessions ==")
print(con.execute("""
WITH d AS (SELECT symbol,date,open,high,low,close,amount,turnover_rate,consecutive_limit_ups lc
  FROM read_parquet(?, union_by_name=true) WHERE symbol='603618.SH' AND date>=DATE '2026-10-20')
SELECT date,round(open,2) o,round(high,2) h,round(low,2) l,round(close,2) c,
  round(amount/1e8,2) amt_yi, round(turnover_rate,2) tr, lc,
  round(avg(close) OVER (ORDER BY date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),2) ma5,
  round(avg(close) OVER (ORDER BY date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW),2) ma10,
  round(avg(close) OVER (ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),2) ma20
FROM d ORDER BY date""",[D]).fetchdf().to_string())
print()
print("== name ==")
print(con.execute("SELECT DISTINCT symbol,name FROM read_parquet(?, union_by_name=true) WHERE symbol='603618.SH' AND name IS NOT NULL LIMIT 1",[LB]).fetchdf().to_string())
