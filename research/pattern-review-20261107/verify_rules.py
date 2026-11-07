# -*- coding: utf-8 -*-
"""Verify the exact rules that will appear in Monday 2026-11-09 checklist."""
import duckdb, pandas as pd, os, io

con = duckdb.connect()
D = r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
M = r"D:\TSP\data\kline_minute\**\*.parquet"
LB = r"D:\TSP\data\ext_data\limit_board_events\**\*.parquet"
OUT = r"C:\work\sourcecode\tick-stock-panel\research\pattern-review-20261107"
os.makedirs(OUT, exist_ok=True)
buf = io.StringIO()
def p(*a): print(*a, file=buf)

# ---------- R1: 首封<10:00 + 连板>=1, 次日开盘买, 持1日 ----------
# 用日线+分钟重建：某日涨停，首封时间<10:00，则次日开盘买入，次日收盘卖出
p("=" * 70)
p("R1 打板规则检验：首封<10:00 的涨停股，次日开盘买入")
p("=" * 70)

rule = """
WITH d0 AS (
  SELECT symbol, date, open, high, low, close, amount, turnover_rate,
         consecutive_limit_ups AS lc,
         LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS pc,
         LEAD(open,1) OVER (PARTITION BY symbol ORDER BY date) AS nopen,
         LEAD(close,1) OVER (PARTITION BY symbol ORDER BY date) AS n1c,
         LEAD(close,2) OVER (PARTITION BY symbol ORDER BY date) AS n2c
  FROM read_parquet(?, union_by_name=true) WHERE date >= DATE '2024-06-01' AND date <= DATE '2026-10-10'
),
sig AS (
  SELECT *, CASE WHEN symbol LIKE '30%' OR symbol LIKE '688%' THEN 0.20 ELSE 0.10 END AS lim
  FROM d0 WHERE pc IS NOT NULL
),
lu AS (
  SELECT * FROM sig
  WHERE close/pc - 1 >= lim - 0.005 AND close >= high - 0.001 AND amount > 5e7 AND lc >= 1
)
SELECT symbol, date, lc, close, pc, lim, nopen, n1c, n2c FROM lu
"""
lu = con.execute(rule, [D]).fetchdf()
p("涨停样本(2024-06~2026-10-10, 连板>=1, 额>5000万): %d 条" % len(lu))

# 首封时间 from minute
sealq = """
SELECT symbol, date, min(datetime) AS first_seal
FROM read_parquet(?, union_by_name=true)
WHERE date >= DATE '2024-06-01' AND date <= DATE '2026-10-10'
GROUP BY symbol, date
"""
# 需要涨停价；先取 minute 的最高价>=涨停价的最早时间
m = con.execute("""
WITH lu AS (
  SELECT symbol, date, round(pc*(1+lim), 2) AS limpx
  FROM (%s) x
)
SELECT mm.symbol, mm.date, min(mm.datetime) AS first_seal
FROM read_parquet(?, union_by_name=true) mm
JOIN lu ON lu.symbol = mm.symbol AND lu.date = mm.date
WHERE mm.high >= lu.limpx - 0.011
GROUP BY mm.symbol, mm.date
""" % rule, [D, M]).fetchdf()
p("有首封时间的: %d 条" % len(m))

lu2 = lu.merge(m, on=["symbol", "date"], how="left")
lu2["seal_hm"] = lu2.first_seal.dt.strftime("%H:%M")
lu2["has_seal"] = lu2.first_seal.notna()
lu2["d1"] = (lu2.n1c / lu2.nopen - 1) * 100
lu2["d2"] = (lu2.n2c / lu2.nopen - 1) * 100
lu2["gap"] = (lu2.nopen / lu2.close - 1) * 100

p("")
p("分组：首封时间 vs 次日开盘买持1日")
def stat(sub, label):
    s = sub.dropna(subset=["d1"])
    if len(s) == 0:
        p("%-22s n=0" % label); return
    p("%-22s n=%6d  D1均值%+6.2f%%  D1胜率%5.1f%%  D2均值%+6.2f%%  隔夜跳空%+5.2f%%" %
      (label, len(s), s.d1.mean(), (s.d1 > 0).mean() * 100,
       s.d2.mean() if s.d2.notna().any() else float("nan"), s.gap.mean()))

stat(lu2, "全部涨停(连板>=1)")
for lo, hi, lab in [("09:30","09:31","09:30 一字/开盘封"),
                    ("09:31","10:00","09:31-10:00"),
                    ("10:00","11:00","10:00-11:00"),
                    ("11:00","13:00","11:00-13:00"),
                    ("13:00","15:01","13:00 以后")]:
    stat(lu2[(lu2.seal_hm >= lo) & (lu2.seal_hm < hi)], lab)

p("")
p("首封<10:00 且 连板>=2：")
stat(lu2[(lu2.seal_hm < "10:00") & (lu2.lc >= 2)], "  首封<10:00 & lc>=2")
p("首封<10:00 且 连板==1：")
stat(lu2[(lu2.seal_hm < "10:00") & (lu2.lc == 1)], "  首封<10:00 & lc==1")

# ---------- R2: 温和主升 更严参数 ----------
p("")
p("=" * 70)
p("R2 温和主升规则检验（次日开盘买）")
p("=" * 70)
BT = """
WITH b AS (
 SELECT symbol,date,open,close,high,low,amount,turnover_rate,consecutive_limit_ups AS lc,
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
base AS (SELECT *, (close/pc-1)*100 AS pct, (close/c20-1)*100 AS r20, (close/c60-1)*100 AS r60,
   (close/ma20-1)*100 AS dev, amount/NULLIF(ama20,0) AS vr
 FROM b WHERE c60 IS NOT NULL AND c20 IS NOT NULL AND ma20 IS NOT NULL)
SELECT
 CASE
  WHEN r60>0 AND r60<20 AND r20>10 AND dev>0 AND dev<12 AND turnover_rate>3 AND turnover_rate<15
       AND amount>2e8 AND lc=0 AND pct>0 AND pct<9.5 AND vr>1.2 THEN 'A 严版主升'
  WHEN r60<30 AND r60>-5 AND r20>10 AND dev>0 AND dev<15 AND turnover_rate>1 AND amount>1e8
       AND lc=0 AND pct>0 AND pct<9.5 THEN 'B 宽版主升'
  ELSE 'C 全市场' END AS grp,
 count(*) AS n,
 round(avg((n1c/nopen-1)*100),2) AS d1,
 round(avg((n3c/nopen-1)*100),2) AS d3,
 round(avg((n5c/nopen-1)*100),2) AS d5,
 round((avg(CASE WHEN n1c>nopen THEN 100.0 ELSE 0 END)),1) AS win1
FROM base WHERE nopen IS NOT NULL GROUP BY 1 ORDER BY 1
"""
p(con.execute(BT, [D]).fetchdf().to_string(index=False))

open(os.path.join(OUT, "rule_verify.txt"), "w", encoding="utf-8").write(buf.getvalue())
print("done")
