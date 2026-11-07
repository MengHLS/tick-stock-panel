# -*- coding: utf-8 -*-
import duckdb, pandas as pd, sqlite3, numpy as np
pd.set_option("display.width",200)
D = r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
con=duckdb.connect()
con.execute("""CREATE TEMP TABLE feat AS
WITH d AS (SELECT symbol,date,close,consecutive_limit_ups lc,
  LAG(close) OVER (PARTITION BY symbol ORDER BY date) pc,
  LAG(close,20) OVER (PARTITION BY symbol ORDER BY date) c20,
  LAG(close,60) OVER (PARTITION BY symbol ORDER BY date) c60
 FROM read_parquet(?, union_by_name=true) WHERE date>=DATE '2024-06-01')
SELECT symbol,date,lc,(close/pc-1)*100 pct,(close/c20-1)*100 r20,(close/c60-1)*100 r60 FROM d""",[D])
f=con.execute("SELECT * FROM feat").fetchdf(); f["date"]=pd.to_datetime(f.date).dt.date

c=sqlite3.connect(r"D:\TSP\data\user_data\trade_ledger\ledger.sqlite")
rt=pd.read_sql("SELECT seq,code,name,open_time,qty,buy_px,sell_px,pnl,ret,hold_td FROM roundtrip",c)
def sym(x):
    x=str(x).zfill(6)
    return x+".SH" if x[:2] in ("60","68","90") else (x+".SZ" if x[:2] in ("00","30","20") else x+".BJ")
rt["symbol"]=rt.code.map(sym); rt["date"]=pd.to_datetime(rt.open_time.str[:10]).dt.date
m=rt.merge(f,on=["symbol","date"],how="left")

g=m[(m.pct>=5)&(m.lc==0)&(m.pct<9.5)]
print("== 当日涨5%+未涨停 组：盈亏集中度 ==")
print("笔数 %d  合计 %.0f  均值 %.0f  中位 %.0f  胜率 %.1f%%"%(len(g),g.pnl.sum(),g.pnl.mean(),g.pnl.median(),(g.pnl>0).mean()*100))
print("去掉最赚的3笔后：合计 %.0f （3笔贡献 %.0f）"%(g.pnl.sum()-g.pnl.nlargest(3).sum(), g.pnl.nlargest(3).sum()))
print(g.nlargest(6,"pnl")[["code","name","open_time","pnl","ret","hold_td","pct","r20"]].to_string(index=False))
print()
print("== 全部回合 盈亏集中度 ==")
print("笔数 %d 合计 %.0f 中位 %.0f"%(len(m),m.pnl.sum(),m.pnl.median()))
print("最赚5笔合计 %.0f，最亏5笔合计 %.0f"%(m.pnl.nlargest(5).sum(),m.pnl.nsmallest(5).sum()))
print()
print("== 2026年内 vs 之前 ==")
m["yr"]=pd.to_datetime(m.open_time).dt.year
print(m.groupby("yr").agg(n=("pnl","size"),sum=("pnl","sum"),med=("pnl","median"),win=("pnl",lambda s:(s>0).mean()*100)).round(1).to_string())
print()
print("== 603618 台账持仓 ==")
pos=pd.read_sql("SELECT * FROM daily_position WHERE date=(SELECT max(date) FROM daily_position)",c)
print(pos.to_string(index=False))
print()
print("== 603618 全部回合 ==")
print(m[m.code.astype(str).str.zfill(6)=="603618"][["seq","open_time","qty","buy_px","sell_px","pnl","ret","hold_td"]].to_string(index=False))
