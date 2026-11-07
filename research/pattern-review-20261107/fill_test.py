# -*- coding: utf-8 -*-
"""Decisive test: can you actually get filled at the limit price?
Only boards that break open give you a fill. Compare returns of
'sealed and never opened' vs 'opened at least once'."""
import duckdb, pandas as pd, os, io

con = duckdb.connect()
D = r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
M = r"D:\TSP\data\kline_minute\**\*.parquet"
OUT = r"C:\work\sourcecode\tick-stock-panel\research\pattern-review-20261107"
buf = io.StringIO()
def p(*a): print(*a, file=buf)

con.execute("""CREATE TEMP TABLE lu AS
WITH d0 AS (
  SELECT symbol, date, open, high, low, close, amount, turnover_rate,
         consecutive_limit_ups AS lc,
         LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS pc,
         LEAD(open,1) OVER (PARTITION BY symbol ORDER BY date) AS nopen,
         LEAD(close,1) OVER (PARTITION BY symbol ORDER BY date) AS n1c,
         LEAD(low,1) OVER (PARTITION BY symbol ORDER BY date) AS n1l
  FROM read_parquet(?, union_by_name=true)
  WHERE date >= DATE '2024-06-01' AND date <= DATE '2026-10-10')
SELECT *, CASE WHEN symbol LIKE '30%' OR symbol LIKE '688%' THEN 0.20 ELSE 0.10 END AS lim
FROM d0 WHERE pc IS NOT NULL""", [D])

con.execute("""CREATE TEMP TABLE sig AS
SELECT symbol, date, lc, close, pc, lim, nopen, n1c, n1l, amount, turnover_rate,
       round(pc*(1+lim),2) AS limpx
FROM lu WHERE close/pc-1 >= lim-0.005 AND close >= high-0.001
          AND amount > 5e7 AND lc >= 1""")

# 首封时间 + 首封之后是否跌破涨停价（=开板可成交）
fill = con.execute("""
WITH fs AS (
  SELECT s.symbol, s.date, s.limpx, min(m.datetime) AS first_seal
  FROM sig s JOIN read_parquet(?, union_by_name=true) m
    ON m.symbol=s.symbol AND m.date=s.date AND m.high >= s.limpx-0.011
  GROUP BY s.symbol, s.date, s.limpx
),
after AS (
  SELECT fs.symbol, fs.date, fs.first_seal,
         min(CASE WHEN m.high < fs.limpx-0.011 THEN m.datetime END) AS break_time
  FROM fs JOIN read_parquet(?, union_by_name=true) m
    ON m.symbol=fs.symbol AND m.date=fs.date AND m.datetime >= fs.first_seal
  GROUP BY fs.symbol, fs.date, fs.first_seal
)
SELECT symbol, date, first_seal, break_time FROM after
""", [M, M]).fetchdf()

df = con.execute("SELECT * FROM sig").fetchdf().merge(fill, on=["symbol", "date"], how="left")
df["seal_hm"] = df.first_seal.dt.strftime("%H:%M")
df["opened"] = df.break_time.notna()
df["d1_open"] = (df.nopen / df.limpx - 1) * 100
df["d1_close"] = (df.n1c / df.limpx - 1) * 100
df["worst"] = (df.n1l / df.limpx - 1) * 100

def stat(sub, label):
    s = sub.dropna(subset=["d1_open"])
    if len(s) == 0:
        p("%-34s n=0" % label); return
    p("%-34s n=%6d  占比%5.1f%%  次开卖%+6.2f%%  次收卖%+6.2f%%  胜率%5.1f%%" %
      (label, len(s), len(s) / len(df) * 100, s.d1_open.mean(), s.d1_close.mean(),
       (s.d1_close > 0).mean() * 100))

p("=" * 86)
p("能不能买得到？封板后是否开板（开板才有机会在涨停价成交）")
p("=" * 86)
stat(df, "全部涨停(连板>=1,额>5000万)")
stat(df[df.opened], "  开过板（可成交）")
stat(df[~df.opened], "  封死未开板（买不到）")

p("")
p("--- 首封<10:00 分拆 ---")
sub = df[df.seal_hm < "10:00"]
stat(sub, "首封<10:00 全部")
stat(sub[sub.opened], "  开过板（可成交）")
stat(sub[~sub.opened], "  封死未开板（买不到）")

p("")
p("--- 首封<10:00 且 连板>=2 ---")
sub2 = df[(df.seal_hm < "10:00") & (df.lc >= 2)]
stat(sub2, "组合 全部")
stat(sub2[sub2.opened], "  开过板（可成交）")
stat(sub2[~sub2.opened], "  封死未开板")

p("")
p("--- 09:30 开盘即封 ---")
sub3 = df[df.seal_hm == "09:30"]
stat(sub3, "09:30 全部")
stat(sub3[sub3.opened], "  开过板（可成交）")
stat(sub3[~sub3.opened], "  封死未开板")

p("")
p("结论方向：可成交子样本的次开卖收益 = 你真正能拿到的钱")

open(os.path.join(OUT, "fill_test.txt"), "w", encoding="utf-8").write(buf.getvalue())
print("done", len(df), "opened", int(df.opened.sum()))
