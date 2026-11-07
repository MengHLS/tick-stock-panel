# -*- coding: utf-8 -*-
"""Map the user's own roundtrips onto the nine patterns, using the same
daily-bar features as the market-wide test."""
import duckdb, pandas as pd, sqlite3, os, io

con = duckdb.connect()
D = r"D:\TSP\data\kline_daily_enriched\**\*.parquet"
OUT = r"C:\work\sourcecode\tick-stock-panel\research\pattern-review-20261107"
buf = io.StringIO()
def p(*a): print(*a, file=buf)

# 1) 建特征表：每只票每天的关键状态
con.execute("""CREATE TEMP TABLE feat AS
WITH d AS (
  SELECT symbol, date, open, high, low, close, amount, turnover_rate,
         consecutive_limit_ups AS lc,
         LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS pc,
         AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20,
         LAG(close,20) OVER (PARTITION BY symbol ORDER BY date) AS c20,
         LAG(close,60) OVER (PARTITION BY symbol ORDER BY date) AS c60
  FROM read_parquet(?, union_by_name=true) WHERE date >= DATE '2024-06-01')
SELECT symbol, date, open, high, low, close, amount, turnover_rate, lc, pc, ma20, c20, c60,
  CASE WHEN pc IS NULL THEN NULL ELSE (close/pc-1)*100 END AS pct,
  CASE WHEN c20 IS NULL THEN NULL ELSE (close/c20-1)*100 END AS r20,
  CASE WHEN c60 IS NULL THEN NULL ELSE (close/c60-1)*100 END AS r60,
  CASE WHEN ma20 IS NULL THEN NULL ELSE (close/ma20-1)*100 END AS dev,
  CASE WHEN symbol LIKE '30%' OR symbol LIKE '688%' THEN 1 ELSE 0 END AS is20
FROM d""", [D])

# 2) 读用户回合
c2 = sqlite3.connect(r"D:\TSP\data\user_data\trade_ledger\ledger.sqlite")
rt = pd.read_sql("SELECT seq, code, name, open_time, close_time, qty, buy_px, sell_px, pnl, ret, hold_td FROM roundtrip", c2)
rt["date"] = pd.to_datetime(rt.open_time.str[:10])
rt["symbol"] = rt.code.astype(str).str.zfill(6)
# 补交易所后缀
def to_sym(c):
    c = str(c).zfill(6)
    if c.startswith(("60", "68", "90")): return c + ".SH"
    if c.startswith(("00", "30", "20")): return c + ".SZ"
    if c.startswith(("8", "4", "92")): return c + ".BJ"
    return c
rt["symbol"] = rt.code.map(to_sym)
rt["date"] = pd.to_datetime(rt.open_time.str[:10]).dt.date
p("回合数: %d, 有买入日期: %d" % (len(rt), rt.date.notna().sum()))

f = con.execute("SELECT * FROM feat").fetchdf()
f["date"] = pd.to_datetime(f["date"]).dt.date
m = rt.merge(f, on=["symbol", "date"], how="left")
p("匹配到日线的回合: %d / %d" % (m.pct.notna().sum(), len(m)))

# 3) 打标
def tag_row(r):
    tags = []
    if pd.notna(r.lc) and r.lc >= 1: tags.append("买入日涨停")
    if pd.notna(r.r60) and r.r60 >= 100: tags.append("60日翻倍")
    if pd.notna(r.r20) and r.r20 >= 40: tags.append("20日涨40%+")
    if pd.notna(r.dev) and r.dev < -10: tags.append("跌破MA20超10%")
    if pd.notna(r.pct) and r.pct >= 5 and pd.notna(r.lc) and r.lc == 0: tags.append("当日涨5%+未涨停")
    if r.is20 == 1: tags.append("20cm")
    return "|".join(tags)
m["tags"] = m.apply(tag_row, axis=1)

p("")
p("=" * 78)
p("你的 441 回合 按特征分组（实际盈亏）")
p("=" * 78)
p("%-28s %5s %10s %10s %7s" % ("分组", "笔数", "合计盈亏", "每笔", "胜率"))
p("-" * 78)
def grp(mask, label):
    s = m[mask]
    if len(s) == 0: return
    p("%-28s %5d %10.0f %10.0f %7.1f%%" % (label, len(s), s.pnl.sum(), s.pnl.mean(), (s.pnl > 0).mean() * 100))

grp(m.index == m.index, "全部")
grp(m.lc >= 1, "买入日涨停")
grp((m.lc >= 1) & (m.hold_td <= 1), "  └ 持1日就走")
grp((m.lc >= 1) & (m.hold_td > 1), "  └ 持超1日")
grp(m.r60 >= 100, "60日翻倍（高位）")
grp(m.r20 >= 40, "20日涨40%+（追高）")
grp(m.dev < -10, "跌破MA20超10%（抄跌）")
grp(m.is20 == 1, "20cm 创业板/科创")
grp((m.pct >= 5) & (m.lc == 0), "当日涨5%+未涨停（追涨）")
grp(m.hold_td <= 1, "持有<=1日")
grp(m.hold_td > 5, "持有>5日")

p("")
p("--- 按持有天数 ---")
for lo, hi, lab in [(0,1,"<=1日"),(2,2,"2日"),(3,3,"3日"),(4,5,"4-5日"),(6,999,">5日")]:
    grp((m.hold_td >= lo) & (m.hold_td <= hi), lab)

p("")
p("--- 标签组合 ---")
m["ntag"] = m.tags.apply(lambda s: 0 if s == "" else len(s.split("|")))
for k in [0,1,2,3,4]:
    grp(m.ntag == k, "标签数=%d" % k)

open(os.path.join(OUT, "user_patterns.txt"), "w", encoding="utf-8").write(buf.getvalue())
print("done")
