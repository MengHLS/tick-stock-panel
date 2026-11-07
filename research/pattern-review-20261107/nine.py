# -*- coding: utf-8 -*-
"""九条模式统一口径重判：同一批样本、同一基准、次日开盘买入（真实可成交）"""
import duckdb, io, os
con=duckdb.connect(); buf=io.StringIO()
def p(*a): print(*a, file=buf)
D=r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
GN=r"D:\TSP\data\ext_data\ext_gn_ths\**\*.parquet"

# 概念宽度：当日该概念涨停家数（先归一成 长表）
import pandas as pd
_g=con.execute("SELECT * FROM read_parquet(?, union_by_name=true)",[GN]).fetchdf()
_g=_g.rename(columns={_g.columns[0]:"symbol", _g.columns[2]:"cn"})
_rows=[]
for sym,cn in zip(_g["symbol"], _g["cn"].astype(str)):
    for t in cn.split(";"):
        if t: _rows.append((sym,t))
gl=pd.DataFrame(_rows, columns=["symbol","cname"])
con.register("gl", gl)
con.execute("""CREATE TEMP TABLE cw AS
SELECT g.cname, d.date, count(DISTINCT d.symbol) lu_n
FROM gl g JOIN read_parquet(?, union_by_name=true) d
  ON d.symbol=g.symbol AND d.consecutive_limit_ups>=1 AND d.close>=d.high-0.001
  AND d.date BETWEEN DATE '2024-06-01' AND DATE '2026-10-10'
GROUP BY 1,2""",[D])
con.execute("""CREATE TEMP TABLE gw AS
SELECT g.symbol,cw.date,max(cw.lu_n)::INTEGER lu_n FROM gl g
JOIN cw ON cw.cname=g.cname GROUP BY 1,2""")

con.execute("""CREATE TEMP TABLE x AS
WITH d AS (
 SELECT symbol,date,open,high,low,close,amount,turnover_rate,consecutive_limit_ups lc,
  AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) ma20,
  AVG(amount) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) ama20,
  LAG(close) OVER (PARTITION BY symbol ORDER BY date) pc,
  LAG(close,20) OVER (PARTITION BY symbol ORDER BY date) c20,
  LAG(close,60) OVER (PARTITION BY symbol ORDER BY date) c60,
  MIN(date) OVER (PARTITION BY symbol) first_dt,
  LEAD(open,1) OVER (PARTITION BY symbol ORDER BY date) nopen,
  LEAD(close,1) OVER (PARTITION BY symbol ORDER BY date) n1c,
  LEAD(close,2) OVER (PARTITION BY symbol ORDER BY date) n2c,
  LEAD(close,3) OVER (PARTITION BY symbol ORDER BY date) n3c,
  LEAD(close,5) OVER (PARTITION BY symbol ORDER BY date) n5c
 FROM read_parquet(?, union_by_name=true) WHERE date BETWEEN DATE '2024-06-01' AND DATE '2026-10-10')
SELECT d.*, (close/pc-1)*100 pct, (close/c20-1)*100 r20, (close/c60-1)*100 r60,
 (close/ma20-1)*100 dev, amount/NULLIF(ama20,0) vr,
 CASE WHEN symbol LIKE '30%' OR symbol LIKE '688%' THEN 1 ELSE 0 END is20,
 date-d.first_dt AS age_d
FROM d WHERE c60 IS NOT NULL AND c20 IS NOT NULL AND ma20 IS NOT NULL AND amount>5e7""",[D])
con.execute("ALTER TABLE x ADD COLUMN lu_n INTEGER")
con.execute("UPDATE x SET lu_n=g.lu_n FROM gw g WHERE g.symbol=x.symbol AND g.date=x.date")

def run(label, where):
    try:
        r=con.execute("""SELECT count(*) n, round(avg((n1c/nopen-1)*100),2) d1,
          round(avg((n3c/nopen-1)*100),2) d3, round(avg((n5c/nopen-1)*100),2) d5,
          round(avg(CASE WHEN n1c>nopen THEN 100.0 ELSE 0 END),1) w1
          FROM x WHERE nopen IS NOT NULL AND """+where).fetchdf().iloc[0]
        p("%-42s n=%7d  D1%+6.2f  D3%+6.2f  D5%+6.2f  W1%5.1f%%"%(label,r.n,r.d1,r.d3,r.d5,r.w1))
    except Exception as e:
        p("%-42s ERR %s"%(label,str(e)[:90]))

p("="*108)
p("九条模式统一重判 | 买点=次日开盘（唯一真实可成交）| 2024-06~2026-10-10 | 全A 成交额>5000万")
p("="*108)
run("基准 全市场",                                  "1=1")
run("P1 总龙反抽(20日涨>=30% 当日回调-8~-3%)",      "r20>=30 AND pct BETWEEN -8 AND -3")
run("P2 大题材主升(概念涨停>=8 当日涨5-9.5%)",       "lu_n>=8 AND pct BETWEEN 5 AND 9.5 AND lc=0")
run("P3 主升龙头(连板>=3 当日涨停)",                 "lc>=3")
run("P4 200%虹吸(60日>=100%)",                       "r60>=100")
run("P6 出监管套利(20日内>=3涨停 当日未涨停)",       "lc=0")
run("P7 20cm首板(创业板/科创 首板涨停)",             "is20=1 AND lc=1")
run("P8 涨价/温和主升(60日<30% 20日>10% 上MA20)",    "r60<30 AND r20>10 AND dev>0 AND lc=0")
run("P9 次新股(上市<365天 当日涨停)",                "age_d<365 AND lc>=1")
run("P9b 次新股(上市<365天 全部)",                   "age_d<365")
p("")
p("")
p("对照: 涨停价当日买入(仅开过板才成交)")
open(os.path.join(r"C:\work\sourcecode\tick-stock-panel\research\pattern-review-20261107","nine_patterns.txt"),"w",encoding="utf-8").write(buf.getvalue())
print(buf.getvalue())
