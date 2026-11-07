# -*- coding: utf-8 -*-
import duckdb, glob, os
con = duckdb.connect()
def q(sql, p):
    try: return con.execute(sql, p).fetchdf()
    except Exception as e: return "ERR %s" % e

I = r"D:\TSP\data\kline_index_daily\**\*.parquet"
print("== index daily ==")
print(q("""SELECT symbol,date,round(close,2) c,round(amount/1e8,0) amt_yi,quote_ts
 FROM read_parquet(?, union_by_name=true) WHERE date>=DATE '2026-11-03' ORDER BY date,symbol LIMIT 20""",[I]).to_string())

D = r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
print("\n== quote_ts distribution on 11-05 / 11-06 ==")
print(q("""SELECT date, quote_ts, count(*) n FROM read_parquet(?, union_by_name=true)
 WHERE date>=DATE '2026-11-05' GROUP BY 1,2 ORDER BY 1,3 DESC LIMIT 12""",[D]).to_string())

LB = r"D:\TSP\data\ext_data\limit_board_events\**\*.parquet"
print("\n== limit_board_events max date ==")
print(q("SELECT max(date) mx, count(*) n FROM read_parquet(?, union_by_name=true) WHERE date>=DATE '2026-10-30'",[LB]).to_string())
print(q("SELECT * FROM read_parquet(?, union_by_name=true) LIMIT 2",[LB]).to_string())
