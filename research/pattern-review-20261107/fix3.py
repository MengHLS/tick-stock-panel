# -*- coding: utf-8 -*-
import duckdb, pandas as pd, io, os
con=duckdb.connect(); buf=io.StringIO()
def p(*a): print(*a, file=buf)
D=r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
M=r"D:\TSP\data\kline_minute\**\*.parquet"
GN=r"D:\TSP\data\ext_data\ext_gn_ths\**\*.parquet"

_g=con.execute("SELECT * FROM read_parquet(?, union_by_name=true)",[GN]).fetchdf()
sym=_g.iloc[:,0].astype(str); cn=_g.iloc[:,2].astype(str)
rows=[]
for a,b in zip(sym,cn):
    for t in b.split(";"):
        t=t.strip()
        if t and t!="nan": rows.append((a,t))
gl=pd.DataFrame(rows,columns=["symbol","cname"]); con.register("gl",gl)
p("概念表: %d 只股票 -> %d 个 股票-概念 对, %d 个概念"%(len(_g),len(gl),gl.cname.nunique()))

con.execute("""CREATE TEMP TABLE cw AS
SELECT g.cname, d.date, count(DISTINCT d.symbol) lu_n FROM gl g
JOIN read_parquet(?, union_by_name=true) d ON d.symbol=g.symbol
 AND d.consecutive_limit_ups>=1 AND d.close>=d.high-0.001
 AND d.date BETWEEN DATE '2024-06-01' AND DATE '2026-10-10'
GROUP BY 1,2""",[D])
p("cw 行数: %d"%con.execute("SELECT count(*) FROM cw").fetchone()[0])
con.execute("""CREATE TEMP TABLE gw AS
SELECT g.symbol, cw.date, max(cw.lu_n)::INTEGER lu_n FROM gl g
JOIN cw ON cw.cname=g.cname GROUP BY 1,2""")
p("gw 行数: %d"%con.execute("SELECT count(*) FROM gw").fetchone()[0])

con.execute("""CREATE TEMP TABLE x AS
WITH d AS (
 SELECT symbol,date,open,high,low,close,amount,consecutive_limit_ups lc,
  LAG(close) OVER (PARTITION BY symbol ORDER BY date) pc,
  LAG(close,20) OVER (PARTITION BY symbol ORDER BY date) c20,
  LAG(close,60) OVER (PARTITION BY symbol ORDER BY date) c60,
  LEAD(open,1) OVER (PARTITION BY symbol ORDER BY date) nopen,
  LEAD(close,1) OVER (PARTITION BY symbol ORDER BY date) n1c,
  LEAD(close,3) OVER (PARTITION BY symbol ORDER BY date) n3c,
  LEAD(close,5) OVER (PARTITION BY symbol ORDER BY date) n5c,
  LEAD(low,1) OVER (PARTITION BY symbol ORDER BY date) n1l
 FROM read_parquet(?, union_by_name=true) WHERE date BETWEEN DATE '2024-06-01' AND DATE '2026-10-10')
SELECT d.*, (close/pc-1)*100 pct, (close/c20-1)*100 r20,
 round(pc*(1+CASE WHEN symbol LIKE '30%' OR symbol LIKE '688%' THEN 0.20 ELSE 0.10 END),2) limpx
FROM d WHERE c60 IS NOT NULL AND c20 IS NOT NULL AND amount>5e7""",[D])
con.execute("ALTER TABLE x ADD COLUMN lu_n INTEGER")
con.execute("UPDATE x SET lu_n=g.lu_n FROM gw g WHERE g.symbol=x.symbol AND g.date=x.date")
p("lu_n 非空: %d / %d"%(con.execute("SELECT count(lu_n) FROM x").fetchone()[0],con.execute("SELECT count(*) FROM x").fetchone()[0]))

def run(label, where):
    r=con.execute("""SELECT count(*) n, round(avg((n1c/nopen-1)*100),2) d1,
      round(avg((n3c/nopen-1)*100),2) d3, round(avg((n5c/nopen-1)*100),2) d5,
      round(avg(CASE WHEN n1c>nopen THEN 100.0 ELSE 0 END),1) w1
      FROM x WHERE nopen IS NOT NULL AND """+where).fetchdf().iloc[0]
    p("%-42s n=%7d  D1%+6.2f  D3%+6.2f  D5%+6.2f  W1%5.1f%%"%(label,r.n,r.d1,r.d3,r.d5,r.w1))

p(""); p("="*104); p("P2 大题材主升 | 次日开盘买"); p("="*104)
run("基准 全市场","1=1")
for th in (5,8,12):
    run("P2 概念涨停>=%d 家 且 涨5-9.5%%未涨停"%th,"lu_n>=%d AND pct BETWEEN 5 AND 9.5 AND lc=0"%th)
run("  概念涨停>=8 且 20日<20%","lu_n>=8 AND pct BETWEEN 5 AND 9.5 AND lc=0 AND r20<20")

# ---- 最关键：涨停价当日买入（仅开过板可成交），按连板数 ----
p(""); p("="*104)
p("关键：以涨停价当日买入、次日开盘卖出 —— 只统计『开过板』（买得到）的子样本")
p("="*104)
sig = """lc>=1 AND close>=$(1-0.005) AND close>=high-0.001"""
con.execute("""CREATE TEMP TABLE s AS
SELECT symbol,date,lc,limpx,nopen,n1c,n1l FROM x
WHERE lc>=1 AND close/pc-1 >= (CASE WHEN symbol LIKE '30%' OR symbol LIKE '688%' THEN 0.195 ELSE 0.095 END)
  AND close>=high-0.001 AND amount>5e7""")
n=con.execute("SELECT count(*) FROM s").fetchone()[0]
p("涨停样本(可识别): %d"%n)
con.execute("""CREATE TEMP TABLE fl AS
WITH fs AS (
  SELECT s.symbol,s.date,s.limpx, min(m.datetime) first_seal
  FROM s JOIN read_parquet(?, union_by_name=true) m
   ON m.symbol=s.symbol AND m.date=s.date AND m.high>=s.limpx-0.011
  GROUP BY 1,2,3),
aft AS (
  SELECT fs.symbol,fs.date,fs.first_seal,
    min(CASE WHEN m.high<fs.limpx-0.011 THEN m.datetime END) break_time
  FROM fs JOIN read_parquet(?, union_by_name=true) m
   ON m.symbol=fs.symbol AND m.date=fs.date AND m.datetime>=fs.first_seal
  GROUP BY 1,2,3)
SELECT symbol,date,first_seal,break_time FROM aft""",[M,M])
df=con.execute("SELECT s.*, f.first_seal, f.break_time FROM s LEFT JOIN fl f USING(symbol,date)").fetchdf()
df["opened"]=df.break_time.notna()
df["d1o"]=(df.nopen/df.limpx-1)*100
df["worst"]=(df.n1l/df.limpx-1)*100
def st(sub,label):
    s2=sub.dropna(subset=["d1o"])
    if not len(s2): p("%-40s n=0"%label); return
    p("%-40s n=%6d 次开卖%+6.2f%% 胜率%5.1f%% 次日最坏%+6.2f%%"%(label,len(s2),s2.d1o.mean(),(s2.d1o>0).mean()*100,s2.worst.quantile(0.10)))
p("")
st(df,"全部涨停")
st(df[df.opened],"  └ 开过板（买得到）")
st(df[~df.opened],"  └ 封死未开板（买不到，虚）")
p("")
for cond,lab in [((df.lc==1),"1板"),((df.lc==2),"2板"),((df.lc==3),"3板"),((df.lc>=4),">=4板")]:
    st(df[cond&df.opened],"  %s 开过板"%lab)
st(df[(df.lc>=2)&df.opened],"  连板>=2 开过板")
st(df[(df.lc>=3)&df.opened],"  连板>=3 开过板")
fs=df.first_seal.dt.strftime("%H:%M")
st(df[df.opened&(fs<"10:00")],"  首封<10:00 开过板")
st(df[df.opened&(fs<"10:00")&(df.lc>=2)],"  首封<10:00 且 连板>=2 开过板")
st(df[df.opened&(fs>="10:00")],"  首封>=10:00 开过板")
open(os.path.join(r"C:\work\sourcecode\tick-stock-panel\research\pattern-review-20261107","fix3.txt"),"w",encoding="utf-8").write(buf.getvalue())
print(buf.getvalue())
