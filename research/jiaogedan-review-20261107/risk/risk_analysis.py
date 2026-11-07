# -*- coding: utf-8 -*-
"""持仓风险体检：集中度 / 风险预算执行 / 回撤路径 / 三档上限越界清单
口径说明见 README_risk.md
"""
import csv, os, json
import numpy as np
import pandas as pd

BASE = r"C:\work\sourcecode\tick-stock-panel\research\jiaogedan-review-20261107"
DATA, OUT = os.path.join(BASE, "data"), os.path.join(BASE, "risk")
os.makedirs(OUT, exist_ok=True)
MIN_EQ = 1000.0   # 权益低于此值的日子不参与权重/占比统计（账户近乎清空）

eq = pd.read_csv(os.path.join(DATA, "daily_equity.csv"), parse_dates=["date"]).set_index("date")
pos = pd.read_csv(os.path.join(OUT, "positions_mv.csv"), parse_dates=["date"])
tr = pd.read_csv(os.path.join(DATA, "trades_clean.csv"), parse_dates=["date"])
rt = pd.read_csv(os.path.join(DATA, "roundtrips.csv"))

pos["code"] = pos["code"].astype(str).str.zfill(6)
tr["code"] = tr["code"].astype(str).str.zfill(6)

# ---------- 品种 ----------
def kind_of(c):
    if c.startswith(("110", "111", "113", "118", "123", "127", "128")):
        return "转债"
    if c.startswith(("15", "16", "50", "51", "56", "58")):
        return "ETF/LOF"
    if c.startswith(("688", "689")):
        return "科创板"
    if c.startswith(("300", "301")):
        return "创业板"
    if c.startswith(("4", "8")):
        return "北交所"
    return "主板"


pos["kind"] = pos["code"].map(kind_of)
pos["sector2"] = pos["hy"].fillna("").replace("", np.nan)
pos["sector1"] = pos["hy_code"].fillna("").str[:3].replace("", np.nan)
pos.loc[pos["sector2"].isna(), "sector2"] = pos.loc[pos["sector2"].isna(), "kind"] + "(未分类)"
pos.loc[pos["sector1"].isna(), "sector1"] = pos.loc[pos["sector1"].isna(), "kind"] + "(未分类)"

# ---------- 日频权益（修正口径，含 ETF/转债） ----------
mv_all = pos.groupby("date")["mv"].sum().rename("mv_all")
agg = eq.join(mv_all).fillna({"mv_all": 0.0})
agg["equity_corr"] = agg["cash"] + agg["mv_all"]
agg["pnl_corr"] = agg["equity_corr"] - agg["cumdep"]
agg["pnl_stated"] = agg["pnl"]
agg["ok_eq"] = agg["equity_corr"] >= MIN_EQ
agg.to_csv(os.path.join(OUT, "equity_corrected.csv"), encoding="utf-8-sig")

pos = pos.merge(agg[["equity_corr", "mv_all", "ok_eq"]], left_on="date", right_index=True, how="left")
pos["w_eq"] = np.where(pos["ok_eq"], pos["mv"] / pos["equity_corr"], np.nan)
pos["w_mv"] = np.where(pos["mv_all"] > 0, pos["mv"] / pos["mv_all"], np.nan)

# ---------- 1 集中度 ----------
g = pos.dropna(subset=["w_eq"])
day = g.groupby("date").agg(
    npos=("code", "nunique"),
    max_w_eq=("w_eq", "max"),
    max_w_mv=("w_mv", "max"),
    hhi_mv=("w_mv", lambda s: float((s.dropna() ** 2).sum())),
).join(agg[["equity_corr", "mv_all"]])

idx = g.groupby("date")["w_eq"].idxmax()
day = day.join(g.loc[idx].set_index("date")[["code", "name", "kind"]])

for col, key in [("sector2", "sec2"), ("sector1", "sec1"), ("kind", "kindg")]:
    s = g.groupby(["date", col], as_index=False).agg(mv=("mv", "sum"))
    s["w"] = s["mv"] / s["date"].map(agg["equity_corr"])
    i2 = s.groupby("date")["w"].idxmax()
    day = day.join(s.loc[i2].set_index("date")[[col, "w"]].rename(
        columns={col: key + "_name", "w": key + "_w"}))
day.to_csv(os.path.join(OUT, "concentration_daily.csv"), encoding="utf-8-sig")


def qs(s, ps=(10, 25, 50, 75, 90, 95, 100)):
    return {f"p{p}": round(float(np.nanpercentile(s.dropna(), p)), 1) for p in ps}


conc = {
    "统计交易日数(有持仓且权益>=1000)": int(len(day)),
    "最大单票权重_占权益_分位": qs(day["max_w_eq"] * 100),
    "最大单票权重_占权益_均值": round(float(day["max_w_eq"].mean() * 100), 1),
    "最大单票权重_占持仓市值_分位": qs(day["max_w_mv"] * 100),
    "最大单票权重_占持仓市值_均值": round(float(day["max_w_mv"].mean() * 100), 1),
    "HHI(占持仓市值)_中位": round(float(day["hhi_mv"].median()), 3),
    "HHI_均值": round(float(day["hhi_mv"].mean()), 3),
    "有效只数1/HHI_中位": round(float(1 / day["hhi_mv"].median()), 2),
    "持仓只数分布": {int(k): int(v) for k, v in day["npos"].value_counts().sort_index().items()},
    "持仓只数_均值": round(float(day["npos"].mean()), 2),
    "单票>=20%天数": int((day["max_w_eq"] >= 0.2).sum()),
    "单票>=30%天数": int((day["max_w_eq"] >= 0.3).sum()),
    "单票>=50%天数": int((day["max_w_eq"] >= 0.5).sum()),
    "单票>=80%天数": int((day["max_w_eq"] >= 0.8).sum()),
    "单票>=95%天数": int((day["max_w_eq"] >= 0.95).sum()),
    "一级行业>=40%天数": int((day["sec1_w"] >= 0.4).sum()),
    "一级行业>=50%天数": int((day["sec1_w"] >= 0.5).sum()),
    "二级行业>=40%天数": int((day["sec2_w"] >= 0.4).sum()),
    "二级行业>=50%天数": int((day["sec2_w"] >= 0.5).sum()),
    "行业分类覆盖率(持仓市值)": round(float(pos.loc[pos["hy"].notna(), "mv"].sum() / pos["mv"].sum() * 100), 1),
}
pd.Series(conc, name="value").to_csv(os.path.join(OUT, "concentration_summary.csv"), encoding="utf-8-sig")

for col, fn in [("sector1", "sector1_exposure.csv"), ("sector2", "sector2_exposure.csv"), ("kind", "kind_exposure.csv")]:
    t = pos.groupby(col).agg(mv_sum=("mv", "sum"), days=("date", "nunique")).sort_values("mv_sum", ascending=False)
    t["share"] = t["mv_sum"] / t["mv_sum"].sum()
    t.to_csv(os.path.join(OUT, fn), encoding="utf-8-sig")

# 单票累计暴露 top
stock_tot = pos.groupby(["code", "name", "kind"]).agg(
    持仓日数=("date", "nunique"), 市值合计=("mv", "sum"), 最大权重=("w_eq", "max"),
    最大市值=("mv", "max"), 最大市值日=("date", lambda s: str(s.max().date()))).reset_index()
stock_tot.sort_values("市值合计", ascending=False).to_csv(os.path.join(OUT, "stock_exposure.csv"),
                                                       index=False, encoding="utf-8-sig")

# ---------- 2 风险预算执行 ----------
buys = tr[(tr["side"] == "B") & (tr["amt"] > 0)].copy()
eqmap = agg["equity_corr"]
prevmap = agg["equity_corr"].shift(1)
buys["eq_today"] = buys["date"].map(eqmap)
buys["eq_prev"] = buys["date"].map(prevmap)
buys["r_today"] = buys["amt"] / buys["eq_today"]
buys["r_prev"] = buys["amt"] / buys["eq_prev"]
buys["r_valid"] = (buys["eq_prev"] >= MIN_EQ) & (buys["eq_today"] >= MIN_EQ)
bv = buys[buys["r_valid"]]

budget = {
    "买入笔数(含全部)": int(len(buys)),
    "买入笔数(占比可算)": int(len(bv)),
    "单笔占前一日权益_中位": round(float(bv["r_prev"].median() * 100), 1),
    "单笔占前一日权益_p75": round(float(bv["r_prev"].quantile(0.75) * 100), 1),
    "单笔占前一日权益_p90": round(float(bv["r_prev"].quantile(0.90) * 100), 1),
    "单笔占前一日权益_p95": round(float(bv["r_prev"].quantile(0.95) * 100), 1),
    "单笔占前一日权益_最大": round(float(bv["r_prev"].max() * 100), 1),
    "单笔金额_元_中位": int(round(float(buys["amt"].median()))),
    "单笔金额_元_p90": int(round(float(buys["amt"].quantile(0.9)))),
    "单笔金额_元_最大": int(round(float(buys["amt"].max()))),
    "超20%_笔数": int((bv["r_prev"] > 0.2).sum()),
    "超20%_占比": round(float((bv["r_prev"] > 0.2).mean() * 100), 1),
    "超30%_笔数": int((bv["r_prev"] > 0.3).sum()),
    "超30%_占比": round(float((bv["r_prev"] > 0.3).mean() * 100), 1),
    "超50%_笔数": int((bv["r_prev"] > 0.5).sum()),
    "超50%_占比": round(float((bv["r_prev"] > 0.5).mean() * 100), 1),
    "超100%_笔数": int((bv["r_prev"] > 1.0).sum()),
}
pd.Series(budget, name="value").to_csv(os.path.join(OUT, "trade_budget_summary.csv"), encoding="utf-8-sig")
buys.sort_values("r_prev", ascending=False).to_csv(os.path.join(OUT, "buy_orders.csv"), index=False,
                                                   encoding="utf-8-sig")

# 连续加仓
tr_s = tr.sort_values(["date", "time"]).copy()
run, rows = {}, []
for r in tr_s.itertuples():
    c = r.code
    if r.side == "B":
        run[c] = run.get(c, 0) + 1
        rows.append((c, r.name, r.date, run[c], r.amt))
    elif int(r.bal_sh or 0) == 0:
        run[c] = 0
adds = pd.DataFrame(rows, columns=["code", "name", "date", "seq", "amt"])
adds.to_csv(os.path.join(OUT, "consecutive_adds.csv"), index=False, encoding="utf-8-sig")
maxadd = adds.groupby(["code", "name"]).agg(最大连续加仓笔数=("seq", "max"),
                                            首笔=("date", "min"), 末笔=("date", "max")).reset_index()
maxadd = maxadd.sort_values("最大连续加仓笔数", ascending=False)
maxadd.to_csv(
    os.path.join(OUT, "max_consecutive_adds.csv"), index=False, encoding="utf-8-sig")

# 单票最大暴露时点
top_exp = g.sort_values("w_eq", ascending=False).head(25)[
    ["date", "code", "name", "kind", "shares", "price", "mv", "equity_corr", "w_eq", "w_mv"]]
top_exp.to_csv(os.path.join(OUT, "max_stock_exposure.csv"), index=False, encoding="utf-8-sig")

# ---------- 3 回撤 ----------
def dd_path(s):
    run_max = s.cummax()
    dd = s - run_max
    trough = dd.idxmin()
    peak = s.loc[:trough].idxmax()
    after = s.loc[trough:]
    rec = after[after >= s.loc[peak]]
    return {
        "峰值日": str(peak.date()), "峰值": round(float(s.loc[peak]), 2),
        "低点日": str(trough.date()), "低点": round(float(s.loc[trough]), 2),
        "最大回撤_元": round(float(dd.min()), 2),
        "持续交易日": int(s.loc[peak:trough].shape[0] - 1),
        "修复日": str(rec.index[0].date()) if len(rec) else "未修复",
        "修复交易日": int(s.loc[peak:rec.index[0]].shape[0] - 1) if len(rec) else None,
    }


dd = {
    "修正口径_累计盈亏曲线": dd_path(agg["pnl_corr"]),
    "核定口径_累计盈亏曲线": dd_path(agg["pnl_stated"]),
    "累计盈亏曲线_相对峰值权益回撤%": round(
        dd_path(agg["pnl_corr"])["最大回撤_元"] / float(agg.loc[dd_path(agg["pnl_corr"])["峰值日"], "equity_corr"]) * 100, 1),
}
json.dump(dd, open(os.path.join(OUT, "drawdown.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)

agg["d_pnl"] = agg["pnl_corr"].diff()
agg["d_pnl_stated"] = agg["pnl_stated"].diff()
agg[["equity", "equity_corr", "mv_all", "cash", "dep", "cumdep", "pnl_stated", "pnl_corr",
     "d_pnl", "d_pnl_stated"]].to_csv(os.path.join(OUT, "equity_corrected.csv"), encoding="utf-8-sig")
worst = agg.assign(date=agg.index).sort_values("d_pnl").head(15)[
    ["date", "d_pnl", "d_pnl_stated", "equity_corr", "mv_all", "dep"]]
worst.to_csv(os.path.join(OUT, "worst_days.csv"), index=False, encoding="utf-8-sig")

# 单日归因
P = pos.pivot_table(index="date", columns="code", values="mv", aggfunc="sum")
P = P.reindex(index=agg.index, columns=sorted(pos["code"].unique())).fillna(0.0)
dv = P.diff().fillna(0.0)
cf = tr.copy()
cf["out"] = np.where(cf["side"] == "B",
                     cf["amt"] + cf["comm"] + cf["oth"] + cf["tfr"],
                     -(cf["amt"] - cf["comm"] - cf["stamp"] - cf["oth"] - cf["tfr"]))
C = cf.pivot_table(index="date", columns="code", values="out", aggfunc="sum")
C = C.reindex(index=P.index, columns=P.columns).fillna(0.0)
contrib = dv - C
cl = contrib.stack().rename("pnl").reset_index()
cl = cl[cl["pnl"].abs() > 0.5]
cl["date"] = pd.to_datetime(cl["date"])
name_of = pos.drop_duplicates("code").set_index("code")["name"].to_dict()
cl["name"] = cl["code"].map(name_of)
cl.to_csv(os.path.join(OUT, "daily_attribution.csv"), index=False, encoding="utf-8-sig")

chk = contrib.sum(axis=1)
recon = pd.DataFrame({"归因合计": chk, "d_pnl": agg["d_pnl"]}).dropna()
recon["差"] = recon["归因合计"] - recon["d_pnl"]
recon.to_csv(os.path.join(OUT, "attribution_check.csv"), encoding="utf-8-sig")

att = []
for d in agg["d_pnl"].nsmallest(6).index:
    sub = cl[cl["date"] == d].copy()
    tot = float(sub["pnl"].sum())
    if tot == 0:
        continue
    sub = sub.sort_values("pnl")
    for i, r in enumerate(sub.head(3).itertuples()):
        att.append({"date": str(d.date()), "排名": i + 1, "code": r.code, "name": r.name,
                    "当日盈亏": round(float(r.pnl)), "占当日亏损比%": round(float(r.pnl / tot * 100), 1),
                    "当日组合盈亏": round(tot)})
pd.DataFrame(att).to_csv(os.path.join(OUT, "worst_days_attribution.csv"), index=False, encoding="utf-8-sig")

# 单一标的是否主导亏损日
dom = []
for d in agg["d_pnl"].nsmallest(10).index:
    sub = cl[cl["date"] == d].sort_values("pnl")
    if sub.empty:
        continue
    tot = float(sub["pnl"].sum())
    r = sub.iloc[0]
    dom.append({"date": str(d.date()), "当日组合盈亏": round(tot), "最大亏损标的": r["name"],
                "代码": r["code"], "该标的盈亏": round(float(r["pnl"])),
                "占当日亏损比%": round(float(r["pnl"] / tot * 100), 1) if tot else None,
                "持仓只数": int(day["npos"].get(d, np.nan)) if d in day.index else None})
pd.DataFrame(dom).to_csv(os.path.join(OUT, "loss_day_dominance.csv"), index=False, encoding="utf-8-sig")

# ---------- 4 三档上限 ----------
def breach(series, name, caps):
    out = []
    n = int(series.notna().sum())
    for cap in caps:
        over = series[series > cap]
        out.append({
            "上限类型": name, "上限": f"{int(cap*100)}%",
            "越界天数": int(len(over)),
            "越界天数占比%": round(len(over) / n * 100, 1),
            "最严重权重%": round(float(series.max()) * 100, 1),
            "最大超额_百分点": round(float((over - cap).max()) * 100, 1) if len(over) else 0.0,
            "最大单日超额_元": int(round(float(((over - cap) * agg.loc[over.index, "equity_corr"]).max()))) if len(over) else 0,
            "平均单日超额_元": int(round(float(((over - cap) * agg.loc[over.index, "equity_corr"]).mean()))) if len(over) else 0,
        })
    return out


bt = pd.DataFrame(breach(day["max_w_eq"], "单票", [0.2, 0.3, 0.5])
                  + breach(day["sec1_w"], "行业(一级)", [0.4, 0.5])
                  + breach(day["sec2_w"], "行业(二级)", [0.4, 0.5]))
bt.to_csv(os.path.join(OUT, "cap_scenarios.csv"), index=False, encoding="utf-8-sig")

bl = g.copy()
for cap in (0.2, 0.3, 0.5):
    bl[f"excess_{int(cap*100)}"] = (bl["w_eq"] - cap).clip(lower=0) * bl["equity_corr"]
bl.sort_values("excess_20", ascending=False).head(60)[
    ["date", "code", "name", "kind", "shares", "price", "mv", "equity_corr", "w_eq", "w_mv",
     "excess_20", "excess_30", "excess_50"]].to_csv(
    os.path.join(OUT, "breach_top_stock.csv"), index=False, encoding="utf-8-sig")

for col, nm in [("sector1", "sector1"), ("sector2", "sector2")]:
    s = g.groupby(["date", col], as_index=False).agg(mv=("mv", "sum"))
    s["w_eq"] = s["mv"] / s["date"].map(agg["equity_corr"])
    s["excess_40"] = (s["w_eq"] - 0.4).clip(lower=0) * s["date"].map(agg["equity_corr"])
    s["excess_50"] = (s["w_eq"] - 0.5).clip(lower=0) * s["date"].map(agg["equity_corr"])
    s.sort_values("excess_40", ascending=False).head(40).to_csv(
        os.path.join(OUT, f"breach_top_{nm}.csv"), index=False, encoding="utf-8-sig")

bo = bv.copy()
bo["excess_25"] = (bo["r_prev"] - 0.25).clip(lower=0) * bo["eq_prev"]
bo.sort_values("excess_25", ascending=False).head(40)[
    ["date", "time", "code", "name", "amt", "eq_prev", "r_prev", "excess_25"]].to_csv(
    os.path.join(OUT, "breach_top_orders.csv"), index=False, encoding="utf-8-sig")

print(json.dumps(dd, ensure_ascii=False, indent=1, default=str))
print(json.dumps(conc, ensure_ascii=False, indent=1, default=str))
print(json.dumps(budget, ensure_ascii=False, indent=1))
print(bt.to_string(index=False))
print(worst.to_string(index=False))
print(pd.DataFrame(dom).to_string(index=False))
print("归因最大偏差:", round(float(recon["差"].abs().max()), 2), " 偏差>500天数:",
      int((recon["差"].abs() > 500).sum()))
print("期末 equity_corr:", round(float(agg["equity_corr"].iloc[-1]), 2),
      "stated:", round(float(agg["equity"].iloc[-1]), 2))
print(maxadd.head(8).to_string(index=False))

# ---------- 5 补充统计 & 报告 ----------
MAX_EQ = float(agg["equity_corr"].max())
dd["回撤占历史最高权益%"] = round(dd["修正口径_累计盈亏曲线"]["最大回撤_元"] / MAX_EQ * 100, 1)
dd["历史最高权益"] = round(MAX_EQ, 2)
json.dump(dd, open(os.path.join(OUT, "drawdown.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)

eqdiff = (agg["equity_corr"] - agg["equity"])
extra = {
    "核定与修正口径差异>200元天数": int((eqdiff.abs() > 200).sum()),
    "差异绝对值和": int(round(eqdiff.abs().sum())),
    "单日最大差异": int(round(eqdiff.abs().max())),
    "单日最大差异日": str(eqdiff.abs().idxmax().date()),
    "持有ETF天数": int(pos.loc[pos["kind"] == "ETF/LOF", "date"].nunique()),
    "持有转债天数": int(pos.loc[pos["kind"] == "转债", "date"].nunique()),
    "最长连续亏损交易日": None,
    "亏损日占比%": round(float((agg["d_pnl"] < 0).mean() * 100), 1),
    "npos=1天数占比%": round(float((day["npos"] == 1).mean() * 100), 1),
    "最长连续单票>=50%交易日": None,
}
s = (agg["d_pnl"] < 0).astype(int)
extra["最长连续亏损交易日"] = int(s.groupby((s.diff() != 0).cumsum()).sum().max())
s2 = (day["max_w_eq"] >= 0.5).astype(int)
extra["最长连续单票>=50%交易日"] = int(s2.groupby((s2.diff() != 0).cumsum()).sum().max())

# 单笔订单上限（按笔统计）
orders = []
for cap in (0.2, 0.25, 0.3, 0.5):
    orders.append({"上限类型": "单笔(占前一日权益)", "上限": f"{int(cap*100)}%",
                   "越界笔数": int((bv["r_prev"] > cap).sum()),
                   "越界笔数占比%": round(float((bv["r_prev"] > cap).mean() * 100), 1),
                   "最严重占比%": round(float(bv["r_prev"].max() * 100), 1),
                   "最大单笔超额_元": int(round(float(((bv["r_prev"] - cap).clip(lower=0) * bv["eq_prev"]).max())))})
orders = pd.DataFrame(orders)
orders.to_csv(os.path.join(OUT, "cap_scenarios_orders.csv"), index=False, encoding="utf-8-sig")

# 上限折算示意：同样价格波动、仓位压到上限后的单日亏损
scale_rows = []
for d in agg["d_pnl"].nsmallest(10).index:
    sub = cl[cl["date"] == d].sort_values("pnl")
    if sub.empty:
        continue
    r = sub.iloc[0]
    w = float(g.loc[(g["date"] == d) & (g["code"] == r["code"]), "w_eq"].iloc[0]) if \
        ((g["date"] == d) & (g["code"] == r["code"])).any() else np.nan
    row = {"date": str(d.date()), "标的": f'{r["code"]} {r["name"]}',
           "当日实际亏损": round(float(r["pnl"])), "当时权重%": round(w * 100, 1)}
    for cap in (0.2, 0.3, 0.5):
        row[f"按{int(cap*100)}%上限折算"] = round(float(r["pnl"]) * min(1.0, cap / w)) if w and w > 0 else None
    scale_rows.append(row)
scale_df = pd.DataFrame(scale_rows)
scale_df.to_csv(os.path.join(OUT, "cap_illustration.csv"), index=False, encoding="utf-8-sig")

json.dump(extra, open(os.path.join(OUT, "extra_stats.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, default=str)

# ---- Markdown 报告 ----
def md(df, cols=None, n=None, fmt=None):
    sub = df[cols] if cols else df
    if n:
        sub = sub.head(n)
    return sub.to_markdown(index=False)


ddc = dd["修正口径_累计盈亏曲线"]
dds = dd["核定口径_累计盈亏曲线"]
L = []
A = L.append
A("# 持仓风险体检（交割单 2025-03-21 ~ 2026-11-06）\n")
A("> 本文件只报事实与偏离，不含处置建议（处置由决策经理给），不改策略与因子。\n")
A("> 数据来源：`data/` 交割单重建（README 总账口径）+ 通达信本地日线收盘价；截至 2026-11-06。\n")

A("## 0. 口径与数据质量（先看这一节）\n")
A("| 项目 | 事实 |\n| --- | --- |")
A(f"| 权益口径 A（核定，`daily_equity.csv`） | 现金 + **仅股票**市值；股票部分已逐日核对，391/396 天与交割单 mv 完全一致（差≤1 元），剩 5 天为 2026-11-02~06 无行情冻结 |")
A(f"| 权益口径 B（修正） | 现金 + 全部持仓（股票+ETF/LOF+转债），本次体检的权重与回撤用它 |")
A(f"| 两口径差异 | {extra['核定与修正口径差异>200元天数']} 天差 200 元以上，绝对差合计 {extra['差异绝对值和']:,} 元；单日最大差 {extra['单日最大差异']:,} 元（{extra['单日最大差异日']}） |")
A(f"| 受影响持仓 | 持有 ETF/LOF {extra['持有ETF天数']} 天、转债 {extra['持有转债天数']} 天；这些日子核定权益里 mv=0 |")
A(f"| 期末权益 | 核定 16,249.36；修正 {float(agg['equity_corr'].iloc[-1]):,.2f}（差 {float(agg['equity'].iloc[-1] - agg['equity_corr'].iloc[-1]):.0f} 元＝603618 最后 4 个交易日无行情，用 10-30 收盘价冻结） |")
A("| 转债未上市期 | 5 笔新债在上市日前无行情，按面值 100 元/张入账（合计约 5,000 元，占权益 <5%） |")
A(f"| 行业分类 | 通达信行业（`tdxhy.cfg`），覆盖持仓市值 {conc['行业分类覆盖率(持仓市值)']}%（仅股票口径 99.1%）；ETF/转债无行业归属，单列 |")
A(f"| 归因校验 | 单日逐票归因与权益差额最大 {float(recon['差'].abs().max()):,.0f} 元，{int((recon['差'].abs() > 500).sum())} 天偏差 >500 元（转债上市首日、新股入账所致） |")
A("")
A("**两个数需要更正**（与任务简报里的例子不一致，两边数字都列出）：\n")
A("| 说法 | 核对结果 |\n| --- | --- |")
A("| 2025-08-21 单日亏 −53,010 | 当日 pnl **−1,720**（入金 2,300，权益 +580）；当日最大单笔**买入** 52,320 元（001236 弘业期货），疑与买入金额混淆 |")
A("| 2026-02-11 单日亏 −47,448 | 当日买入 512000 券商ETF 82,300 份共 46,993 元，核定口径未记 ETF 市值 → 权益从 47,459 掉到 11.77，次日回 49,782。**是口径伪亏损，真实约 −365 元** |")
A("")
A("**与 README 总账的同口径差异（两边数字都列）**\n")
A("| 指标 | README 总账 | 本体检（修正口径 380 个有持仓日） | 差异原因 |")
A("| --- | --- | --- | --- |")
A("| 最大单票权重均值 | 83.2% | 86.9% | 样本：README 含 16 个空仓日（计 0），本体检只算有持仓日；按全部 396 天复算为 83.4% |")
A("| 最大单票权重中位 | 98.3% | 97.6% | 分母：README 用核定权益（只算股票市值），本体检用修正权益（含 ETF/转债）；改用核定权益复算为 98.4% |")
A("| 平均同时持有只数 | 1.56 只 | 1.62 只 | 同上：含 16 个空仓日为 1.56 只 |")
A("")
A("> 上述三项**不是数据冲突**，只是样本与分母口径不同；凡是涉及上限越界的计算，本体检统一用修正权益（更保守，不会把 ETF 持仓误算成空仓）。\n")
A("")
A("## 1. 集中度事实\n")
A("**当前持仓快照（2026-11-06 收盘）**\n")
lastd = pos["date"].max()
lastp = pos[pos["date"] == lastd].copy()
# 2026-11-02~06 本地日线未更新：修正口径沿用 10-30 收盘价（22.24），
# 核定口径用交割单里的 11-06 收盘价 23.15（README：700×23.15=16,205，权益 16,249.36）
LAST_PX_A = {"603618": 23.15}
EQ_A, EQ_B = 16249.36, 15612.36
snap = lastp[["code", "name", "shares", "price", "hy", "kind"]].copy()
snap["收盘价_核定"] = snap.apply(lambda r: LAST_PX_A.get(r["code"], r["price"]), axis=1)
snap["收盘价_修正"] = snap["price"]
snap["市值_核定"] = (snap["shares"] * snap["收盘价_核定"]).round(2)
snap["市值_修正"] = (snap["shares"] * snap["收盘价_修正"]).round(2)
snap["权重_核定%"] = (snap["市值_核定"] / EQ_A * 100).round(1)
snap["权重_修正%"] = (snap["市值_修正"] / EQ_B * 100).round(1)
A(snap.rename(columns={"code": "代码", "name": "名称", "shares": "股数", "hy": "行业", "kind": "品种"}
  ).drop(columns=["price"]).to_markdown(index=False))
A(f"\n现金 44.36 元（占核定权益 0.3%）。按**核定权益 16,249.36** 计算，单票 20% / 30% / 50% 上限金额为 "
  f"{EQ_A*0.2:,.0f} / {EQ_A*0.3:,.0f} / {EQ_A*0.5:,.0f} 元；当前该股核定市值 {snap['市值_核定'].sum():,.0f} 元"
  f"（占 {snap['市值_核定'].sum()/EQ_A*100:.1f}%）。修正口径（15,612.36）下市值 {snap['市值_修正'].sum():,.0f} 元"
  f"（占 {snap['市值_修正'].sum()/EQ_B*100:.1f}%）。\n")
A("| 指标 | 数值 |\n| --- | --- |")
A(f"| 统计交易日 | {conc['统计交易日数(有持仓且权益>=1000)']} 天（有持仓） |")
A(f"| 最大单票权重（占权益）中位 | {conc['最大单票权重_占权益_分位']['p50']}% |")
A(f"| 最大单票权重（占权益）均值 | {conc['最大单票权重_占权益_均值']}% |")
A(f"| 最大单票权重（占持仓市值）中位/均值 | {conc['最大单票权重_占持仓市值_分位']['p50']}% / {conc['最大单票权重_占持仓市值_均值']}% |")
A(f"| HHI 中位 / 均值 | {conc['HHI(占持仓市值)_中位']} / {conc['HHI_均值']}（有效只数 1/HHI ≈ {conc['有效只数1/HHI_中位']}） |")
A(f"| 平均同时持有 | {conc['持仓只数_均值']} 只；只持 1 只占 {extra['npos=1天数占比%']}% |")
A(f"| 单票 ≥50% 天数 | {conc['单票>=50%天数']} 天（{conc['单票>=50%天数']/conc['统计交易日数(有持仓且权益>=1000)']*100:.0f}%） |")
A(f"| 单票 ≥80% 天数 | {conc['单票>=80%天数']} 天 |")
A(f"| 单票 ≥95% 天数 | {conc['单票>=95%天数']} 天 |")
A(f"| 最长连续单票 ≥50% | {extra['最长连续单票>=50%交易日']} 个交易日 |")
A(f"| 一级行业 ≥40% / ≥50% 天数 | {conc['一级行业>=40%天数']} / {conc['一级行业>=50%天数']} 天 |")
A("")
A("**单票权重分位（占权益）**\n")
A("| p10 | p25 | p50 | p75 | p90 | p95 | max |\n| --- | --- | --- | --- | --- | --- | --- |")
p = conc["最大单票权重_占权益_分位"]
A(f"| {p['p10']}% | {p['p25']}% | {p['p50']}% | {p['p75']}% | {p['p90']}% | {p['p95']}% | {p['p100']}% |")
A("")
A("**持仓只数分布**\n")
A("| 只数 | " + " | ".join(str(k) for k in conc["持仓只数分布"]) + " |")
A("| --- | " + " | ".join("---" for _ in conc["持仓只数分布"]) + " |")
A("| 天数 | " + " | ".join(str(v) for v in conc["持仓只数分布"].values()) + " |")
A("")
A("**按季度**（持仓只数均值 / 最大单票权重均值）\n")
qq = day.copy()
qq["q"] = qq.index.to_period("Q").astype(str)
qtab = qq.groupby("q").agg(交易日=("npos", "size"), 平均持仓只数=("npos", "mean"),
                           最大单票权重均值=("max_w_eq", "mean")).round(2)
A(qtab.to_markdown())
A("")
A("**行业集中（一级，按持仓市值·日累计）**\n")
s1 = pd.read_csv(os.path.join(OUT, "sector1_exposure.csv"), dtype={"sector1": str})
nm1 = {}
for line in open(r"D:\tdx\incon.dat", "rb").read().decode("gbk", "ignore").splitlines():
    if line.startswith("######"):
        sec = None
        continue
    if line.startswith("#"):
        sec = line.strip("#").strip()
        continue
    if sec == "TDXNHY" and "|" in line:
        k, v = line.split("|", 1)
        nm1[k] = v
s1["行业"] = s1["sector1"].map(lambda x: nm1.get(x, x))
s1["占比%"] = (s1["share"] * 100).round(1)
A(s1.head(10)[["行业", "days", "占比%"]].rename(columns={"days": "持仓日数"}).to_markdown(index=False))
A("")
A("> 局限：行业名来自通达信分类（一级 12 类），ETF/转债没有行业归属；同一实控人/同一题材（如「航天系」600343+600879+000547）在分类上可能分散到不同行业，实际相关性高于分类显示。**组合层面相关性无法分散**：62% 的交易日只持 1 只，此时组合与个股相关性 = 1。\n")

A("## 2. 风险预算执行（单笔 vs 权益）\n")
A("| 指标 | 数值 |\n| --- | --- |")
A(f"| 可计算占比的买入笔数 | {budget['买入笔数(占比可算)']} 笔（另有 {budget['买入笔数(含全部)']-budget['买入笔数(占比可算)']} 笔在账户近乎清空时发生，不计） |")
A(f"| 单笔占前一日权益：中位 / p75 / p90 / p95 / 最大 | {budget['单笔占前一日权益_中位']}% / {budget['单笔占前一日权益_p75']}% / {budget['单笔占前一日权益_p90']}% / {budget['单笔占前一日权益_p95']}% / **{budget['单笔占前一日权益_最大']}%** |")
A(f"| 单笔金额（元）：中位 / p90 / 最大 | {budget['单笔金额_元_中位']:,} / {budget['单笔金额_元_p90']:,} / {budget['单笔金额_元_最大']:,} |")
A(f"| 超 20% 上限 | {budget['超20%_笔数']} 笔（{budget['超20%_占比']}%） |")
A(f"| 超 30% 上限 | {budget['超30%_笔数']} 笔（{budget['超30%_占比']}%） |")
A(f"| 超 50% 上限 | {budget['超50%_笔数']} 笔（{budget['超50%_占比']}%） |")
A(f"| 超 100%（动用 T+0 卖出款） | {budget['超100%_笔数']} 笔 |")
A("")
A("> 分母统一取**前一日权益**（不是当日权益）：T+0 卖出款当日可再次买入，用当日权益会把单笔占比压成 100%、丢掉越界信息；上面 20 笔 >100% 就来自这种滚动满仓。\n")
A("")
A("**最大单笔买入 TOP8**（金额／占前一日权益）\n")
A(bv.sort_values("amt", ascending=False).head(8)
  .assign(日期=lambda x: x["date"].dt.date, 占比=lambda x: (x["r_prev"] * 100).round(1))
  [["日期", "code", "name", "amt", "eq_prev", "占比"]]
  .rename(columns={"code": "代码", "name": "名称", "amt": "金额", "eq_prev": "前一日权益"})
  .to_markdown(index=False))
A("")
A("**最大单票暴露时点**（金额口径 TOP6）\n")
A(top_exp.sort_values("mv", ascending=False).head(6)
  .assign(日期=lambda x: x["date"].dt.date, 权重=lambda x: (x["w_eq"] * 100).round(1))
  [["日期", "code", "name", "shares", "price", "mv", "equity_corr", "权重"]]
  .rename(columns={"code": "代码", "name": "名称", "shares": "股数", "price": "收盘价",
                   "mv": "市值", "equity_corr": "当日权益"})
  .to_markdown(index=False))
A("")
A("**连续加仓 TOP8**（同一标的未清仓前的连续买入笔数）\n")
A(maxadd.head(8)[["code", "name", "最大连续加仓笔数", "首笔", "末笔"]].to_markdown(index=False))
A("")
A(f"> {adds['code'].nunique()} 个标的出现过买入；其中 {int((maxadd['最大连续加仓笔数']>=2).sum())} 个标的出现过未清仓前的连续加仓，"
  f"连续 ≥3 笔的有 {int((maxadd['最大连续加仓笔数']>=3).sum())} 个、≥5 笔的有 {int((maxadd['最大连续加仓笔数']>=5).sum())} 个，"
  f"最长 {int(maxadd['最大连续加仓笔数'].max())} 笔（{maxadd.iloc[0]['code']} {maxadd.iloc[0]['name']}，{maxadd.iloc[0]['首笔'].date()} 起）。\n")
A("")

A("## 3. 回撤体检\n")
A("| 项目 | 修正口径 | 核定口径 |\n| --- | --- | --- |")
A(f"| 峰值日 / 峰值累计盈亏 | {ddc['峰值日']} / {ddc['峰值']:,.0f} | {dds['峰值日']} / {dds['峰值']:,.0f} |")
A(f"| 低点日 / 低点 | {ddc['低点日']} / {ddc['低点']:,.0f} | {dds['低点日']} / {dds['低点']:,.0f} |")
A(f"| 最大回撤（元） | **{ddc['最大回撤_元']:,.0f}** | {dds['最大回撤_元']:,.0f} |")
A(f"| 持续交易日 | {ddc['持续交易日']} | {dds['持续交易日']} |")
A(f"| 是否修复 | {ddc['修复日']} | {dds['修复日']} |")
A(f"| 占历史最高权益 {MAX_EQ:,.0f} 的 | {dd['回撤占历史最高权益%']}% | — |")
A("")
A(f"> 备注：`daily_equity` 里的权益百分比回撤会失真——账户中途多次大额出入金（峰值 113,393 在日常态只有 4 万上下），现金又被抽走过（2026-09-08~09-14 权益 0.02 元）。所以回撤用**累计盈亏金额**表达，百分比以最高权益为分母仅供参考。\n")
A("**单日最大亏损 TOP10**（修正口径，已扣出入金）\n")
A(agg.assign(日期=lambda x: x.index.date).sort_values("d_pnl").head(10)
  [["日期", "d_pnl", "equity_corr"]].rename(columns={"d_pnl": "单日盈亏", "equity_corr": "当日权益"})
  .round(0).to_markdown(index=False))
A("")
A("**亏损日是否由单一标的造成**\n")
A(pd.DataFrame(dom).to_markdown(index=False))
A("")
A("> 结论：最大回撤路径由「单票满仓 + 短线频繁换手」共同造成，TOP10 亏损日 100% 由单一标的贡献，且当日常只持 1 只。亏损不来自某一次黑天鹅，而是 56.3% 的交易日亏损、最长连亏 9 天。\n")

A("## 4. 三档上限越界对比（供使用者拍板，不预设结论）\n")
A("**单票 / 行业**\n")
A(bt.to_markdown(index=False))
A("")
A("**单笔成交金额上限**\n")
A(orders.to_markdown(index=False))
A("")
A("**同样价格波动、仓位压到上限后的单日亏损折算（示意）**\n")
A(scale_df.to_markdown(index=False))
A("")
A("**越界清单（按超额金额排序，TOP10；完整见 `breach_top_stock.csv`）**\n")
bs2 = bl.sort_values("excess_20", ascending=False).head(10).copy()
bs2["日期"] = bs2["date"].dt.date
bs2["权重%"] = (bs2["w_eq"] * 100).round(1)
bs2["超20%超额(元)"] = bs2["excess_20"].round(0)
bs2["超30%超额(元)"] = bs2["excess_30"].round(0)
bs2["超50%超额(元)"] = bs2["excess_50"].round(0)
A(bs2[["日期", "code", "name", "mv", "equity_corr", "权重%", "超20%超额(元)", "超30%超额(元)", "超50%超额(元)"]]
  .rename(columns={"code": "代码", "name": "名称", "mv": "市值", "equity_corr": "当日权益"})
  .to_markdown(index=False))
A("")
A("**行业越界清单（一级行业，按超 40% 超额排序，TOP6；完整见 `breach_top_sector1.csv`）**\n")
_g1 = g.groupby(["date", "sector1"], as_index=False).agg(mv=("mv", "sum"))
_g1["w_eq"] = _g1["mv"] / _g1["date"].map(agg["equity_corr"])
_g1["excess_40"] = (_g1["w_eq"] - 0.4).clip(lower=0) * _g1["date"].map(agg["equity_corr"])
_g1["excess_50"] = (_g1["w_eq"] - 0.5).clip(lower=0) * _g1["date"].map(agg["equity_corr"])
_g1["行业"] = _g1["sector1"].map(lambda x: nm1.get(x, x))
_t = _g1.sort_values("excess_40", ascending=False).head(6).copy()
_t["日期"] = _t["date"].dt.date
_t["权重%"] = (_t["w_eq"] * 100).round(1)
_t["超40%超额(元)"] = _t["excess_40"].round(0)
_t["超50%超额(元)"] = _t["excess_50"].round(0)
_t["当日权益"] = _t["date"].map(agg["equity_corr"]).round(0)
A(_t[["日期", "行业", "mv", "当日权益", "权重%", "超40%超额(元)", "超50%超额(元)"]]
  .rename(columns={"mv": "行业市值"}).to_markdown(index=False))
A("")

A("## 5. 文件清单\n")
A("| 文件 | 内容 |\n| --- | --- |")
for f, d in [("equity_corrected.csv", "日频权益（核定/修正两口径）、出入金、单日盈亏"),
             ("concentration_daily.csv", "逐日：持仓只数、最大单票权重（占权益/占持仓）、HHI、最大行业权重"),
             ("concentration_summary.csv", "集中度分位与计数"),
             ("cap_scenarios.csv", "单票/行业三档上限越界对比"),
             ("cap_scenarios_orders.csv", "单笔成交金额上限对比"),
             ("cap_illustration.csv", "压到上限后的单日亏损折算"),
             ("breach_top_stock.csv", "单票越界清单（按超额金额排序，含日期/代码/权重）"),
             ("breach_top_sector1.csv / sector2.csv", "行业越界清单"),
             ("breach_top_orders.csv", "单笔越界清单"),
             ("max_stock_exposure.csv", "最大单票暴露时点 TOP25"),
             ("stock_exposure.csv", "逐标的持仓日数/累计市值/最大权重"),
             ("consecutive_adds.csv / max_consecutive_adds.csv", "连续加仓明细与汇总"),
             ("worst_days.csv / worst_days_attribution.csv / loss_day_dominance.csv", "单日亏损与归因"),
             ("daily_attribution.csv / attribution_check.csv", "逐票逐日盈亏归因与校验"),
             ("drawdown.json", "回撤路径（两口径）"),
             ("positions_mv.csv", "逐日逐票市值（股数×通达信收盘价）"),
             ("build_panel.py / risk_analysis.py", "生成脚本（只读，不写系统产物）")]:
    A(f"| `{f}` | {d} |")
A("")
# ---- 顶部一页摘要（只列事实，不预设结论）----
def _cell(df, t, cap, col):
    r = df[(df["上限类型"] == t) & (df["上限"] == cap)]
    return r.iloc[0][col] if len(r) else ""

S = []
S.append("## 摘要（事实清单，可整段引用；口径见第 0 节）\n")
S.append("| # | 事实 | 数字 | 来源 |")
S.append("| --- | --- | --- | --- |")
S.append(f"| 1 | 单票集中度（{conc['统计交易日数(有持仓且权益>=1000)']} 个有持仓日） | 最大单票权重 中位 **{conc['最大单票权重_占权益_分位']['p50']}%**、均值 {conc['最大单票权重_占权益_均值']}%、p10 {conc['最大单票权重_占权益_分位']['p10']}% | 修正权益 |")
S.append(f"| 2 | 分散度 | 平均持 {conc['持仓只数_均值']} 只；只持 1 只 {conc['持仓只数分布'][1]} 天（{extra['npos=1天数占比%']}%）；HHI 中位 {conc['HHI(占持仓市值)_中位']} | 同上 |")
S.append(f"| 3 | 单票 ≥50% / ≥80% / ≥95% 天数 | {conc['单票>=50%天数']} / {conc['单票>=80%天数']} / {conc['单票>=95%天数']} 天 | 同上 |")
S.append(f"| 4 | 行业集中 | 一级行业 ≥40% 共 {conc['一级行业>=40%天数']} 天、≥50% 共 {conc['一级行业>=50%天数']} 天 | 通达信行业，覆盖 {conc['行业分类覆盖率(持仓市值)']}% 持仓市值 |")
S.append(f"| 5 | 单笔风险预算 | 单笔占前一日权益 中位 {budget['单笔占前一日权益_中位']}%、p90 {budget['单笔占前一日权益_p90']}%、最大 **{budget['单笔占前一日权益_最大']}%** | {int(budget['买入笔数(占比可算)'])} 笔可算占比的买入 |")
S.append(f"| 6 | 单笔越界笔数（20 / 25 / 30 / 50%） | {int(_cell(orders,'单笔(占前一日权益)','20%','越界笔数'))} / {int(_cell(orders,'单笔(占前一日权益)','25%','越界笔数'))} / {int(_cell(orders,'单笔(占前一日权益)','30%','越界笔数'))} / {int(_cell(orders,'单笔(占前一日权益)','50%','越界笔数'))} 笔 | `cap_scenarios_orders.csv` |")
S.append(f"| 7 | 最大回撤（盈亏曲线） | 峰值 {ddc['峰值日']} +{ddc['峰值']:,.0f} → 低点 {ddc['低点日']} {ddc['低点']:,.0f}，回撤 **{ddc['最大回撤_元']:,.0f} 元**，持续 {ddc['持续交易日']} 个交易日，未修复 | 修正口径；核定口径 {dds['最大回撤_元']:,.0f} |")
S.append(f"| 8 | 亏损是否来自个股 | 单日亏损 TOP10 **10/10** 由单一标的贡献（当日常只持 1 只） | 第 3 节 |")
S.append(f"| 9 | 当前持仓 | 603618 杭电股份 700 股，核定市值 16,205 元 = 权益的 99.7%；现金 44.36 元 | 2026-11-06 交割单 |")
S.append("")
S.append("**三档上限越界天数一览（供拍板，本报告不预设结论）**\n")
S.append(bt[["上限类型", "上限", "越界天数", "越界天数占比%", "最大单日超额_元"]].to_markdown(index=False))
S.append("")

_head = next(k for k, x in enumerate(L) if x.startswith("## 0."))
L = L[:_head] + S + L[_head:]
open(os.path.join(OUT, "README_risk.md"), "w", encoding="utf-8").write("\n".join(L))
print("报告已写:", os.path.join(OUT, "README_risk.md"), len(L), "行")

# ---- CSV 浮点收敛（4 位小数，便于直接用 Excel 排序）----
for _f in ["breach_top_stock.csv", "breach_top_sector1.csv", "breach_top_sector2.csv",
           "breach_top_orders.csv", "concentration_daily.csv", "stock_exposure.csv",
           "max_stock_exposure.csv", "cap_scenarios.csv", "cap_scenarios_orders.csv"]:
    _p = os.path.join(OUT, _f)
    if not os.path.exists(_p):
        continue
    _d = pd.read_csv(_p, dtype={"code": str})
    _num = _d.select_dtypes("number").columns
    _d[_num] = _d[_num].round(4)
    _d.to_csv(_p, index=False, encoding="utf-8-sig")
print("CSV 已收敛小数位")
