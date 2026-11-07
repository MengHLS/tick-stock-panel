# -*- coding: utf-8 -*-
import duckdb, pandas as pd, io, os
con=duckdb.connect(); buf=io.StringIO()
def p(*a): print(*a, file=buf)
D=r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
M=r"D:\TSP\data\kline_minute\**\*.parquet"
GN=r"D:\TSP\data\ext_data\ext_gn_ths\**\*.parquet"

con.execute("""CREATE TEMP TABLE x AS
WITH d AS (
 SELECT symbol,date,open,high,low,close,amount,turnover_rate,consecutive_limit_ups lc,
  LAG(close) OVER (PARTITION BY symbol ORDER BY date) pc,
  LAG(close,20) OVER (PARTITION BY symbol ORDER BY date) c20,
  LAG(close,60) OVER (PARTITION BY symbol ORDER BY date) c60,
  SUM(CASE WHEN consecutive_limit_ups>=1 THEN 1 ELSE 0 END) OVER
    (PARTITION BY symbol ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) lu20,
  LEAD(open,1) OVER (PARTITION BY symbol ORDER BY date) nopen,
  LEAD(close,1) OVER (PARTITION BY symbol ORDER BY date) n1c,
  LEAD(close,3) OVER (PARTITION BY symbol ORDER BY date) n3c,
  LEAD(close,5) OVER (PARTITION BY symbol ORDER BY date) n5c
 FROM read_parquet(?, union_by_name=true) WHERE date BETWEEN DATE '2024-06-01' AND DATE '2026-10-10')
SELECT d.*, (close/pc-1)*100 pct, (close/c20-1)*100 r20, (close/c60-1)*100 r60,
 CASE WHEN symbol LIKE '30%' OR symbol LIKE '688%' THEN 1 ELSE 0 END is20,
 round(pc*(1+CASE WHEN symbol LIKE '30%' OR symbol LIKE '688%' THEN 0.20 ELSE 0.10 END),2) limpx
FROM d WHERE c60 IS NOT NULL AND c20 IS NOT NULL AND amount>5e7""",[D])

def run(label, where):
    r=con.execute("""SELECT count(*) n, round(avg((n1c/nopen-1)*100),2) d1,
      round(avg((n3c/nopen-1)*100),2) d3, round(avg((n5c/nopen-1)*100),2) d5,
      round(avg(CASE WHEN n1c>nopen THEN 100.0 ELSE 0 END),1) w1
      FROM x WHERE nopen IS NOT NULL AND """+where).fetchdf().iloc[0]
    p("%-40s n=%7d  D1%+6.2f  D3%+6.2f  D5%+6.2f  W1%5.1f%%"%(label,r.n,r.d1,r.d3,r.d5,r.w1))

p("="*104); p("P6 断板（近20日>=3次涨停，当日未涨停）| 次日开盘买"); p("="*104)
run("基准 全市场","1=1")
run("P6 断板 lu20>=3 且 lc=0","lu20>=3 AND lc=0")
run("  断板 lu20>=4 且 lc=0","lu20>=4 AND lc=0")

# 概念宽度
_g=con.execute("SELECT * FROM read_parquet(?, union_by_name=true)",[GN]).fetchdf()
_g=_g.rename(columns={_g.columns[0]:"symbol", _g.columns[2]:"cn"})
rows=[]
for sym,cn in zip(_g["symbol"],_g["cn"].astype(str)):
    for t in cn.split(";"):
        if t: rows.append((sym,t))
gl=pd.DataFrame(rows,columns=["symbol","cname"]); con.register("gl",gl)
p(""); p("概念表: %d 只股票, %d 个 股票-概念 对"%(len(_g),len(gl)))
con.execute("""CREATE TEMP TABLE cw AS
SELECT g.cname, d.date, count(DISTINCT d.symbol) lu_n FROM gl g
JOIN read_parquet(?, union_by_name=true) d ON d.symbol=g.symbol
 AND d.consecutive_limit_ups>=1 AND d.close>=d.high-0.001
 AND d.date BETWEEN DATE '2024-06-01' AND DATE '2026-10-10'
GROUP BY 1,2""",[D])
p("cw 行数: %d" % con.execute("SELECT count(*) FROM cw").fetchone()[0])
con.execute("""CREATE TEMP TABLE gw AS
SELECT g.symbol, cw.date, max(cw.lu_n)::INTEGER lu_n FROM gl g
JOIN cw ON cw.cname=g.cname GROUP BY 1,2""")
p("gw 行数: %d" % con.execute("SELECT count(*) FROM gw").fetchone()[0])
con.execute("ALTER TABLE x ADD COLUMN lu_n INTEGER")
con.execute("UPDATE x SET lu_n=g.lu_n FROM gw g WHERE g.symbol=x.symbol AND g.date=x.date")
p("x.lu_n 非空: %d / %d" % (con.execute("SELECT count(lu_n) FROM x").fetchone()[0],
                            con.execute("SELECT count(*) FROM x").fetchone()[0]))
p(""); p("="*104); p("P2 大题材主升（所在概念当日涨停>=8家，个股涨5-9.5%未涨停）"); p("="*104)
run("基准 全市场","1=1")
for th in (8,10,15):
    run("P2 概念涨停>=%d 且 涨5-9.5%% 未涨停"%th, "lu_n>=%d AND pct BETWEEN 5 AND 9.5 AND lc=0"%th)
run("  概念涨停>=8 且 涨5-9.5%% 且 20日<20%","lu_n>=8 AND pct BETWEEN 5 AND 9.5 AND lc=0 AND r20<20")

open(os.path.join(r"C:\work\sourcecode\tick-stock-panel\research\pattern-review-20261107","fix2.txt"),"w",encoding="utf-8").write(buf.getvalue())
print(buf.getvalue())
