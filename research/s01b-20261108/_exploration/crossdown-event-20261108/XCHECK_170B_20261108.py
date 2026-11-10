# -*- coding: utf-8 -*-
"""XCHECK ⑤-b: independent recompute of a0/c0 trades reconciliation (read-only).

Run:
    cd /c/work/sourcecode/tick-stock-panel
    ./backend/.venv/Scripts/python.exe research/s01b-20261108/crossdown-event-20261108/XCHECK_170B_20261108.py

Reads only:
    research/s01b-20261108/crossdown-event-20261108/results/{a0_10bp,c0_10bp}/{trades,equity}.parquet
    D:/TSP/data/kline_daily_enriched/date=*/part.parquet   (panel prices: adjusted + raw_close)
    D:/TSP/data/adj_factor/all.parquet                     (vendor ex-rights events)
Writes nothing.
"""
import glob
import numpy as np
import pandas as pd

pd.set_option("display.width", 320)
pd.set_option("display.max_columns", 80)
pd.set_option("display.max_rows", 300)

BASE = "research/s01b-20261108/crossdown-event-20261108/results/"
ENR = "D:/TSP/data/kline_daily_enriched/date=%s/part.parquet"
ADJ = "D:/TSP/data/adj_factor/all.parquet"


def hr(t):
    print("\n" + "=" * 100 + "\n" + t + "\n" + "=" * 100)


a = pd.read_parquet(BASE + "a0_10bp/trades.parquet")
c = pd.read_parquet(BASE + "c0_10bp/trades.parquet")
ea = pd.read_parquet(BASE + "a0_10bp/equity.parquet")
ec = pd.read_parquet(BASE + "c0_10bp/equity.parquet")
for d in (a, c):
    d["key"] = d["symbol"].astype(str) + "|" + d["entry_date"].astype(str)

# ---------------------------------------------------------------- A. counts
hr("A. 笔数与键 (key = symbol|entry_date)")
print("rows a0=%d  c0=%d" % (len(a), len(c)))
print("dup keys: a0=%d  c0=%d" % (a.duplicated("key").sum(), c.duplicated("key").sum()))
ka, kc = set(a.key), set(c.key)
print("shared=%d  only_a0=%d  only_c0=%d" % (len(ka & kc), len(ka - kc), len(kc - ka)))
print("alt keys (symbol|entry_date|entry_signal_date): shared=%d only_a0=%d only_c0=%d" % (
    len(set(zip(a.symbol, a.entry_date, a.entry_signal_date)) & set(zip(c.symbol, c.entry_date, c.entry_signal_date))),
    len(set(zip(a.symbol, a.entry_date, a.entry_signal_date)) - set(zip(c.symbol, c.entry_date, c.entry_signal_date))),
    len(set(zip(c.symbol, c.entry_date, c.entry_signal_date)) - set(zip(a.symbol, a.entry_date, a.entry_signal_date)))))

A = a.set_index("key")
C = c.set_index("key")
sh = A.index.intersection(C.index)
m = A.loc[sh].join(C.loc[sh], lsuffix="_a", rsuffix="_c").reset_index()

# ------------------------------------------------- B. pnl_pct on shared keys
hr("B. 共有 111 笔的 pnl_pct 逐笔比较")
m["pd_pct"] = m.pnl_pct_c - m.pnl_pct_a
m["pd_abs"] = m.pd_pct.abs()
print("exact equal        :", int((m.pd_abs == 0).sum()))
print("|diff| <= 1e-5     :", int((m.pd_abs <= 1e-5).sum()))
print("|diff| <= 1e-4     :", int((m.pd_abs <= 1e-4).sum()))
print("|diff| >  1e-4     :", int((m.pd_abs > 1e-4).sum()))
print("|diff| >  1e-2     :", int((m.pd_abs > 1e-2).sum()))
print("max |diff| = %.6f  median = %.2e" % (m.pd_abs.max(), m.pd_abs.median()))

big = m[m.pd_abs > 1e-5].sort_values("pd_abs", ascending=False)
print("\n-- %d 笔超出 1e-5，逐笔 --" % len(big))
print(big[["symbol_a", "entry_date_a", "exit_date_a", "exit_date_c", "duration_a", "duration_c",
           "entry_price_a", "exit_price_a", "entry_price_c", "exit_price_c",
           "pnl_pct_a", "pnl_pct_c", "pd_pct", "exit_reason_a", "open_at_end_c",
           "blocked_exit_days_a", "blocked_exit_days_c"]].to_string(index=False))

# -------------------------------------------------------------- C. price basis
hr("C. 价格字段来源：a0 = 面板 adjusted open；c0 = 面板重建 raw open × (1±10bp)")
m["gross_a"] = m.exit_price_a / m.entry_price_a - 1
m["gross_c"] = m.exit_price_c / m.entry_price_c - 1
m["gross_d"] = m.gross_c - m.gross_a
print("价格口径毛收益 √(exit/entry)-1 相同 (|diff|<=1e-6): %d/111 ; |diff|>1e-4: %d ; median diff=%.5f" % (
    int((m.gross_d.abs() <= 1e-6).sum()), int((m.gross_d.abs() > 1e-4).sum()), m.gross_d.median()))

dates = sorted(set(m.entry_date_a) | set(m.exit_date_a))
bars = []
for d in dates:
    b = pd.read_parquet(ENR % d)
    b["d"] = d
    bars.append(b[["symbol", "d", "open", "close", "raw_close"]])
B = pd.concat(bars, ignore_index=True)
B["cf"] = B.raw_close / B.close            # panel 自己的复权比 (raw / adjusted)
B["k"] = B.symbol + "|" + B.d
BI = B.set_index("k")
en = BI.reindex(m.symbol_a + "|" + m.entry_date_a)
ex = BI.reindex(m.symbol_a + "|" + m.exit_date_a)
m["open_en_adj"] = en.open.values
m["cf_en"] = en.cf.values
m["open_ex_adj"] = ex.open.values
m["cf_ex"] = ex.cf.values
m["a_en_vs_open"] = m.entry_price_a / m.open_en_adj - 1
m["a_ex_vs_open"] = m.exit_price_a / m.open_ex_adj - 1
m["c_en_over_recon"] = m.entry_price_c / (m.open_en_adj * m.cf_en) - 1   # 期望 +0.001
m["c_ex_over_recon"] = m.exit_price_c / (m.open_ex_adj * m.cf_ex) - 1    # 期望 -0.001
for col in ["a_en_vs_open", "a_ex_vs_open", "c_en_over_recon", "c_ex_over_recon"]:
    s = m[col].abs()
    print("%-16s <=1e-4: %3d/111   <=1e-2: %3d/111   median %+.2e   max %.2e" % (
        col, int((s <= 1e-4).sum()), int((s <= 1e-2).sum()), m[col].median(), s.max()))

# factor table check: panel cf vs vendor cumprod(ex_factor) after the same date
f = pd.read_parquet(ADJ)
f["td"] = f.trade_date.astype(str).str[:10]
ev = {s: g[["td", "ex_factor", "dividend", "bonus"]].values.tolist() for s, g in f.groupby("symbol")}


def cum_after(sym, d):
    xs = [(t, float(x)) for t, x, _, _ in ev.get(sym, []) if t > d]
    return float(np.prod([x for _, x in xs])) if xs else 1.0


def events_in(sym, d0, d1):
    return [(t, float(x), float(dv), float(b)) for t, x, dv, b in ev.get(sym, []) if d0 <= t <= d1]


m["cum_en"] = [cum_after(s, d) for s, d in zip(m.symbol_a, m.entry_date_a)]
m["cum_ex"] = [cum_after(s, d) for s, d in zip(m.symbol_a, m.exit_date_a)]
m["cf_vs_cum_en"] = m.cf_en / m.cum_en - 1
m["n_ev_in_window"] = [len(events_in(s, d0, d1)) for s, d0, d1 in
                       zip(m.symbol_a, m.entry_date_a, m.exit_date_a)]
print("\n面板 cf vs 厂商 cumprod(ex_factor) (entry date):  within1e-4 %d/111 ; within1e-2 %d/111" % (
    int(m.cf_vs_cum_en.abs().le(1e-4).sum()), int(m.cf_vs_cum_en.abs().le(1e-2).sum())))
bad = m[m.cf_vs_cum_en.abs() > 1e-2]
print("-- 面板复权幅度与 adj_factor 表不一致的票 --")
print(bad[["symbol_a", "entry_date_a", "cf_en", "cum_en", "cf_vs_cum_en"]].to_string(index=False))
for r in bad.itertuples():
    bonus = [x[3] for x in events_in(r.symbol_a, r.entry_date_a, "2099-01-01") if x[3] > 0]
    print("   %s: bonus 事件 %s ; cum/cf = %.4f => 等于 1+sum(bonus)=%.4f ?" % (
        r.symbol_a, bonus, r.cum_en / r.cf_en, 1 + sum(bonus)))

hr("C2. 每笔共有笔：窗口内是否有除权事件（决定 pnl_pct 是否可逐笔相同）")
m["ev_in_window"] = [str([(t, round(x, 4), dv, b) for t, x, dv, b in events_in(s, d0, d1)])
                     for s, d0, d1 in zip(m.symbol_a, m.entry_date_a, m.exit_date_a)]
cls = np.where(m.open_at_end_c, "open_at_end_in_c0",
        np.where(m.exit_date_a != m.exit_date_c, "exit_bar_differs",
        np.where(m.n_ev_in_window > 0, "ex_event_in_window", "no_event")))
m["cls"] = cls
print(m.cls.value_counts().to_string())
print("\n按分类看 |pnl_pct 差|:")
print(m.groupby("cls").pd_abs.agg(["count", "max", "median"]).to_string())
print("\n-- ex_event_in_window 全部 --")
print(m[m.cls == "ex_event_in_window"][["symbol_a", "entry_date_a", "exit_date_a", "pnl_pct_a", "pnl_pct_c",
                                        "pd_pct", "ev_in_window"]].sort_values("pd_pct", key=abs, ascending=False).to_string(index=False))

# ------------------------------------------------------------ D. notional
hr("D. 名义额是否守恒 (entry_value = shares*price*(1+cost))")
m["dval"] = m.entry_value_c - m.entry_value_a
m["dval_rel"] = m.entry_value_c / m.entry_value_a - 1
m["within_1lot"] = m.dval.abs() <= m.entry_price_c * 100
print("|Δ| <= 1 手市值: %d/111 ; |Δ|/a <=1%%: %d ; <=5%%: %d ; median |Δ|/a = %.1f%% ; max = %.0f%%" % (
    int(m.within_1lot.sum()), int((m.dval_rel.abs() <= 0.01).sum()), int((m.dval_rel.abs() <= 0.05).sum()),
    m.dval_rel.abs().median() * 100, m.dval_rel.abs().max() * 100))
m["yr"] = m.entry_date_a.str[:4]
print(m.groupby("yr").agg(n=("symbol_a", "size"), within_1lot=("within_1lot", "sum"),
                          med_abs_rel=("dval_rel", lambda s: round(s.abs().median() * 100, 1)),
                          max_abs_rel=("dval_rel", lambda s: round(s.abs().max() * 100, 1))).to_string())
print("\n-- 首日 (2019-07-02) 四笔共有笔 --")
print(m[m.entry_date_a == "2019-07-02"][["symbol_a", "entry_price_a", "shares_a", "entry_value_a",
                                         "entry_price_c", "shares_c", "entry_value_c", "dval", "dval_rel"]].to_string(index=False))

# ------------------------------------------------- E. divergence path
hr("E. 差异起点与累计路径")
print("-- a0 首日持仓 --")
print(a[a.entry_date == "2019-07-02"][["symbol", "entry_price", "shares", "entry_value", "exit_date", "exit_reason"]].to_string(index=False))
print("-- c0 首日持仓 --")
print(c[c.entry_date == "2019-07-02"][["symbol", "entry_price", "shares", "entry_value", "exit_date", "exit_reason"]].to_string(index=False))

alld = pd.bdate_range("2019-07-01", "2026-10-30")


def holdings(t):
    out = {}
    for r in t.itertuples():
        for d in alld[(alld >= pd.Timestamp(r.entry_date)) & (alld <= pd.Timestamp(r.exit_date))]:
            out.setdefault(d.strftime("%Y-%m-%d"), set()).add(r.symbol)
    return out


ha, hc = holdings(a), holdings(c)
rows = []
for d in sorted(set(ha) | set(hc)):
    sa, sc = ha.get(d, set()), hc.get(d, set())
    rows.append((d, len(sa), len(sc), len(sa & sc), len(sa - sc), len(sc - sa),
                 ",".join(sorted(sa - sc)), ",".join(sorted(sc - sa))))
H = pd.DataFrame(rows, columns=["date", "n_a", "n_c", "same", "only_a", "only_c", "only_a_sym", "only_c_sym"])
H["diff_any"] = (H.only_a + H.only_c) > 0
print("\n首个有差异的交易日:", H[H.diff_any].iloc[0][["date", "n_a", "n_c", "same", "only_a", "only_c"]].to_dict())
print("有差异的交易日: %d / %d" % (int(H.diff_any.sum()), len(H)))
print("avg same: %.2f / 5 ; 只在一侧出现的累计 symbol-day: %d" % (H["same"].mean(), int((H.only_a + H.only_c).sum())))
H["yr"] = H.date.str[:4]
print("\n按年: 平均 same 数 / 有差异天数 / 单侧独有 symbol-day 数")
print(H.groupby("yr").agg(avg_same=("same", "mean"), days=("date", "size"), diff_days=("diff_any", "sum"),
                          one_side=("only_a", "sum")).assign(one_side_c=H.groupby("yr").only_c.sum()).round(2).to_string())

eqm = ea[["date", "value"]].merge(ec[["date", "value"]], on="date", suffixes=("_a", "_c"))
eqm["gap"] = eqm.value_c / eqm.value_a - 1
eqm["dd_a"] = eqm.value_a / eqm.value_a.cummax() - 1
eqm["dd_c"] = eqm.value_c / eqm.value_c.cummax() - 1
print("\n-- 权益比 c0/a0 路径 --")
print("首个不等日:", eqm[(eqm.gap.abs() > 1e-12)].iloc[0][["date", "value_a", "value_c", "gap"]].to_dict())
chk = ["2019-07-02", "2019-12-31", "2020-12-31", "2021-12-31", "2022-12-30", "2023-12-29", "2024-12-31", "2025-12-31", "2026-10-30"]
print(eqm.set_index("date").reindex(chk)[["value_a", "value_c", "gap", "dd_a", "dd_c"]].round(4).to_string())
print("\n|gap| 最大 %.2f%% 于 %s ; 年均 |gap| 变化:" % (eqm.gap.abs().max() * 100, eqm.loc[eqm.gap.abs().idxmax(), "date"]))
eqm["yr"] = eqm.date.str[:4]
print(eqm.groupby("yr").apply(lambda x: pd.Series({"gap_start": round(x.gap.iloc[0] * 100, 2), "gap_end": round(x.gap.iloc[-1] * 100, 2)})).to_string())

hr("F. 出场结构 / 拦截计数（只做对照，不做归因）")
print("exit_reason  a0:", a.exit_reason.value_counts().to_dict())
print("exit_reason  c0:", c.exit_reason.value_counts().to_dict())
print("c0 open_at_end 笔:", int(c.open_at_end.sum()), c[c.open_at_end][["symbol", "entry_date", "exit_date", "pnl_pct", "exit_price"]].to_string(index=False))
print("shared 中 c0 open_at_end 的键:", m[m.open_at_end_c][["symbol_a", "entry_date_a", "exit_date_a", "pnl_pct_a", "pnl_pct_c"]].to_string(index=False))
