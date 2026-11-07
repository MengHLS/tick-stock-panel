# -*- coding: utf-8 -*-
import duckdb, pandas as pd
pd.set_option("display.width",200)
con=duckdb.connect()
D=r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
I=r"D:\TSP\data\kline_index_daily\**\*.parquet"
GN=r"D:\TSP\data\ext_data\ext_gn_ths\**\*.parquet"
ML=r"D:\TSP\data\mainline_history\**\*.parquet"
LB=r"D:\TSP\data\ext_data\limit_board_events\**\*.parquet"

print("== 603618 ATR14 / 关键位 (到 11-05) ==")
print(con.execute("""
WITH d AS (SELECT date,high,low,close,LAG(close) OVER (ORDER BY date) pc
 FROM read_parquet(?, union_by_name=true) WHERE symbol='603618.SH' AND date>=DATE '2026-09-20'),
t AS (SELECT date,high,low,close, GREATEST(high-low, ABS(high-pc), ABS(low-pc)) tr FROM d WHERE pc IS NOT NULL)
SELECT date, round(high,2) h, round(low,2) l, round(close,2) c,
 round(avg(tr) OVER (ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW),3) atr14
FROM t ORDER BY date DESC LIMIT 5""",[D]).fetchdf().to_string(index=False))

print("\n== 指数 11-05 vs 20/60日均 ==")
print(con.execute("""
WITH d AS (SELECT symbol,date,close, AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) m20,
 AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) m60
 FROM read_parquet(?, union_by_name=true) WHERE date>=DATE '2026-07-01' AND symbol IN ('000001.SH','399001.SZ','399006.SZ'))
SELECT symbol, date, round(close,2) c, round(m20,2) ma20, round(m60,2) ma60,
 round((close/m20-1)*100,2) dev20, round((close/m60-1)*100,2) dev60
FROM d WHERE date=DATE '2026-11-05'""",[I]).fetchdf().to_string(index=False))

print("\n== 11-05 市场宽度（涨停/上涨家数）==")
print(con.execute("""
WITH d AS (SELECT symbol,date,close,high,LAG(close) OVER (PARTITION BY symbol ORDER BY date) pc, consecutive_limit_ups lc
 FROM read_parquet(?, union_by_name=true) WHERE date>=DATE '2026-11-03')
SELECT date, count(*) n, sum(CASE WHEN close>pc THEN 1 ELSE 0 END) up,
 sum(CASE WHEN lc>=1 AND close>=high-0.001 THEN 1 ELSE 0 END) lu,
 round(100.0*sum(CASE WHEN close>pc THEN 1 ELSE 0 END)/count(*),1) up_pct
FROM d WHERE pc IS NOT NULL AND date>=DATE '2026-11-03' GROUP BY date ORDER BY date""",[D]).fetchdf().to_string(index=False))

print("\n== 603618 所属概念 ==")
try:
    gm=con.execute("SELECT * FROM read_parquet(?, union_by_name=true)",[GN]).fetchdf()
    r=gm[gm.iloc[:,0]=="603618"]
    if len(r): print(str(r.iloc[0,2])[:400])
    else: print("概念表内无此票")
except Exception as e: print("ERR",e)

print("\n== 11-05 概念主线前10 ==")
print(con.execute("SELECT rank,member FROM read_parquet(?, union_by_name=true) WHERE date=DATE '2026-11-05' AND kind='concept' AND rank<=10 ORDER BY rank",[ML]).fetchdf().to_string(index=False))
