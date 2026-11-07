# -*- coding: utf-8 -*-
"""Unconditional test: place a buy at the limit price when price first TOUCHES
it intraday. Includes boards that later fail. This is the only version a real
account can execute without queue priority."""
import duckdb, pandas as pd, os, io

con = duckdb.connect()
D = r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
M = r"D:\TSP\data\kline_minute\**\*.parquet"
OUT = r"C:\work\sourcecode\tick-stock-panel\research\pattern-review-20261107"
buf = io.StringIO()
def p(*a): print(*a, file=buf)

con.execute("""CREATE TEMP TABLE base AS
WITH d0 AS (
  SELECT symbol, date, open, high, low, close, amount, turnover_rate,
         consecutive_limit_ups AS lc,
         LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS pc,
         LEAD(open,1) OVER (PARTITION BY symbol ORDER BY date) AS nopen,
         LEAD(close,1) OVER (PARTITION BY symbol ORDER BY date) AS n1c,
         LEAD(close,3) OVER (PARTITION BY symbol ORDER BY date) AS n3c,
         LEAD(low,1) OVER (PARTITION BY symbol ORDER BY date) AS n1l
  FROM read_parquet(?, union_by_name=true)
  WHERE date >= DATE '2024-06-01' AND date <= DATE '2026-10-10')
SELECT symbol, date, open, high, low, close, amount, turnover_rate, lc, pc, nopen, n1c, n3c, n1l,
       CASE WHEN symbol LIKE '30%' OR symbol LIKE '688%' THEN 0.20 ELSE 0.10 END AS lim,
       round(pc*(1+CASE WHEN symbol LIKE '30%' OR symbol LIKE '688%' THEN 0.20 ELSE 0.10 END),2) AS limpx
FROM d0 WHERE pc IS NOT NULL AND amount > 5e7""", [D])

# 当日盘中是否触及涨停价
touch = con.execute("""
SELECT b.symbol, b.date, min(m.datetime) AS touch_time
FROM base b JOIN read_parquet(?, union_by_name=true) m
  ON m.symbol=b.symbol AND m.date=b.date AND m.high >= b.limpx-0.011
GROUP BY b.symbol, b.date
""", [M]).fetchdf()

df = con.execute("SELECT * FROM base").fetchdf().merge(touch, on=["symbol", "date"], how="inner")
df["touch_hm"] = df.touch_time.dt.strftime("%H:%M")
df["sealed"] = (df.close / df.pc - 1) >= (df.lim - 0.005)
df["d1_open"] = (df.nopen / df.limpx - 1) * 100
df["d1_close"] = (df.n1c / df.limpx - 1) * 100
df["d3_close"] = (df.n3c / df.limpx - 1) * 100

def stat(sub, label):
    s = sub.dropna(subset=["d1_open"])
    if len(s) == 0:
        p("%-30s n=0" % label); return
    p("%-30s n=%6d  封板率%5.1f%%  次开卖%+6.2f%%  次收卖%+6.2f%%  胜率%5.1f%%" %
      (label, len(s), s.sealed.mean() * 100, s.d1_open.mean(), s.d1_close.mean(),
       (s.d1_close > 0).mean() * 100))

p("=" * 90)
p("无条件打板：盘中首次触及涨停价即在涨停价买入（含后来开板失败的）")
p("2024-06~2026-10-10，成交额>5000万")
p("=" * 90)
stat(df, "全部触及涨停")

p("")
p("--- 按首次触板时间 ---")
for lo, hi, lab in [("09:30","09:31","09:30 开盘触板"),
                    ("09:31","10:00","09:31-10:00 触板"),
                    ("10:00","11:00","10:00-11:00 触板"),
                    ("11:00","13:00","11:00-13:00 触板"),
                    ("13:00","15:01","13:00 后触板")]:
    stat(df[(df.touch_hm >= lo) & (df.touch_hm < hi)], lab)

p("")
p("--- 只买前一日非涨停的（首板候选，避免连板高位）---")
stat(df[df.lc == 0], "前一日未涨停(首板)")
sub = df[(df.lc == 0) & (df.touch_hm < "10:00")]
stat(sub, "  首板 & 10:00前触板")

p("")
p("--- 按最终是否封板拆分（事后验证，非交易用）---")
stat(df[df.sealed], "  最终封板")
stat(df[~df.sealed], "  最终未封（买在板上被砸）")

p("")
p("--- 首板 & 10:00前触板 的最终结果分布 ---")
s = df[(df.lc == 0) & (df.touch_hm < "10:00")]
p("  样本 %d，封板率 %.1f%%，次开卖均值 %+.2f%%，次收卖均值 %+.2f%%" %
  (len(s), s.sealed.mean() * 100, s.d1_open.mean(), s.d1_close.mean()))
p("  次收卖>0 占比 %.1f%%，次收卖<-5%% 占比 %.1f%%，最差 %.2f%%" %
  ((s.d1_close > 0).mean() * 100, (s.d1_close < -5).mean() * 100, s.d1_close.min()))
p("  分位数: 5%%=%+.2f  25%%=%+.2f  中位=%+.2f  75%%=%+.2f  95%%=%+.2f" %
  tuple(s.d1_close.quantile([0.05,0.25,0.5,0.75,0.95]).round(2).tolist()))

open(os.path.join(OUT, "touch_test.txt"), "w", encoding="utf-8").write(buf.getvalue())
print("done", len(df))
