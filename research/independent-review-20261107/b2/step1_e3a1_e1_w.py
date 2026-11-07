"""独立复跑 #1: E3-A1 (逐日池内家数 vs 研究侧) + E1 market_breadth + W1-W4。
不采信交付方脚本输出; 研究侧直接调用 common.py 自己的 add_indicators/add_universe。
"""
from __future__ import annotations
import json, sys, time
from datetime import date
from pathlib import Path

sys.path.insert(0, "backend")
sys.path.insert(0, "research/strategy-search-20261107/scripts")

import polars as pl
from app.config import settings
from app.custom.research_universe_pack.universe import (
    FACTOR_COLUMN_IN_UNIVERSE, UniverseParams, compute_in_universe, universe_diagnostics,
)
from app.tickflow.security_status import read_st_history
from app.extensions.factors import ensure_factor_providers
from app.factors import dsl

import common as R          # 研究侧官方模块

EVAL_START, EVAL_END = date(2019, 7, 1), date(2026, 10, 30)
PANEL_END = date(2026, 11, 6)
OUT = {}

t0 = time.perf_counter()
m = R.open_market()
print("[1] load research panel via common.load_panel", flush=True)
frame = R.load_panel(m, R.WARMUP_START, PANEL_END)
print(f"    rows={frame.height:,} sym={frame['symbol'].n_unique():,} "
      f"days={frame['date'].n_unique()} {time.perf_counter()-t0:.0f}s", flush=True)
frame = frame.with_columns(pl.col("date").cast(pl.Date))
OUT["panel"] = {"rows": frame.height, "symbols": frame["symbol"].n_unique(),
                "days": frame["date"].n_unique()}

_d = frame.filter(pl.col("date") >= pl.lit(EVAL_START))["date"]
print("     >=EVAL_START range:", str(_d.min()), str(_d.max()), "days=", _d.n_unique(), flush=True)

# 研究侧: 官方 add_indicators + add_universe
t1 = time.perf_counter()
r = R.add_universe(R.add_indicators(frame))
print(f"[2] research add_universe {time.perf_counter()-t1:.0f}s", flush=True)
OUT["research_cols_ok"] = all(c in r.columns for c in ("in_universe","market_breadth"))

# 生产侧: in_universe (两态) + E1
ensure_factor_providers()
hist = read_st_history(settings.data_dir)
base = frame.select("symbol","date","close","volume","amount","raw_close")

prod_unknown = compute_in_universe(base, st_history=hist, params=UniverseParams())
prod_recon   = compute_in_universe(base, st_history=hist,
                                   params=UniverseParams(st_flag_missing_policy="treat_non_st"))

# 研究侧 in_universe 转 0/1
res = r.with_columns(pl.col("date").cast(pl.Date)).select("symbol","date",
               pl.col("in_universe").cast(pl.Int8).alias("res_iu"),
               pl.col("market_breadth").alias("res_breadth"),
               pl.col("ma60").alias("res_ma60"),
               pl.col("close").alias("res_close"))

def daily_counts(df, col):
    return (df.filter((pl.col("date")>=pl.lit(EVAL_START)) & (pl.col("date")<=pl.lit(EVAL_END)))
              .group_by("date")
              .agg((pl.col(col)==1.0).sum().cast(pl.Int64).alias("p"),
                   pl.col(col).is_not_null().sum().cast(pl.Int64).alias("known"))
              .sort("date"))

# ---- E3-A1: recon 模式 (契约 §2.3 对账口径) vs 研究侧
prod_recon = prod_recon.join(res.select("symbol","date"), on=["symbol","date"], how="left")
a1 = daily_counts(prod_recon, FACTOR_COLUMN_IN_UNIVERSE).join(
        res.group_by("date").agg(pl.col("res_iu").sum().cast(pl.Int64).alias("r")).sort("date"),
        on="date", how="inner")
a1 = a1.with_columns((pl.col("p")-pl.col("r")).alias("d"),
                     pl.when(pl.col("known")>0).then(pl.col("p")).otherwise(None).alias("p_known"))
both = a1.filter(pl.col("known")>0)
OUT["E3A1_recon"] = {
    "compared_days": both.height,
    "days_with_diff": int(both.filter(pl.col("d")!=0).height),
    "diff_days_list": both.filter(pl.col("d")!=0)["date"].cast(str).to_list(),
    "null_days": int(a1.filter(pl.col("known")==0).height),
    "null_days_list": a1.filter(pl.col("known")==0)["date"].cast(str).to_list(),
    "first_day": str(a1["date"].min()), "last_day": str(a1["date"].max()),
    "mean_pool_prod": float(both["p"].mean()), "mean_pool_research": float(both["r"].mean()),
}

# ---- E3-A1b: unknown(生产) 模式的 null 日 + 是否有「生产非null 但研究 null」错配
a1u = daily_counts(prod_unknown, FACTOR_COLUMN_IN_UNIVERSE)
u = a1u.join(a1.select("date","r"), on="date", how="inner")
OUT["E3A1_unknown_mode"] = {
    "days": u.height,
    "null_days": int(u.filter(pl.col("known")==0).height),
    "null_days_list": u.filter(pl.col("known")==0)["date"].cast(str).to_list(),
    "days_prod_null_but_research_has": int(u.filter((pl.col("known")==0) & (pl.col("r")>0)).height),
}

# ---- W1/W2/W3/W4 窗口 (14 日: 2026-10-20..2026-11-06)
win_days = sorted(prod_unknown.filter(pl.col("date")>=pl.lit(date(2026,10,20)))["date"].unique().to_list())
OUT["W_window_days"] = [str(d) for d in win_days]
wdf = prod_unknown.filter(pl.col("date")>=pl.lit(date(2026,10,20)))
diag = universe_diagnostics(base.filter(pl.col("date")>=pl.lit(date(2026,10,20))), st_history=hist)
OUT["W1_in_0_1"] = int(wdf.filter(pl.col(FACTOR_COLUMN_IN_UNIVERSE).is_in([0.0,1.0])).height)
OUT["W2"] = {
    "all_match": bool((diag["unknown"]==diag["bars"]).all()),
    "per_day": [{"date": str(x["date"]), "bars": int(x["bars"]), "unknown": int(x["unknown"]),
                 "reason": x["unknown_reason"]} for x in diag.iter_rows(named=True)],
}
OUT["W2_days"] = diag.height
print("[3] E1 market_breadth ...", flush=True)
ma60 = dsl.compile_formula("ts_mean(close, 60)")
assert ma60.ok, [(e.code,e.message) for e in ma60.errors]
BREADTH = "xs_mean(close > ma60, in_universe)"
cb = dsl.compile_formula(BREADTH)
OUT["E1_compile"] = {"ok": cb.ok, "errors": [(e.code,e.message) for e in cb.errors],
                    "warmup": getattr(cb,"warmup_bars",None),
                    "cross": getattr(cb,"cross_sectional",None),
                    "refs": sorted(getattr(cb,"referenced_factors",[]) or [])}
w = prod_unknown.with_columns(pl.col("close").cast(pl.Float64)).to_pandas()
w = pl.from_pandas(w)
w = ma60.frame_transform(w).rename({dsl.FACTOR_COLUMN: "ma60"})
o = cb.frame_transform(w)
o = o.with_columns(pl.col(dsl.FACTOR_COLUMN).alias("bore"), pl.col("date").cast(pl.Date))
e1 = (o.filter((pl.col("date")>=pl.lit(EVAL_START)) & (pl.col("date")<=pl.lit(EVAL_END)))
        .group_by("date").agg(pl.col("bore").first().alias("prod"),
                              pl.col("bore").n_unique().alias("nuniq"))
        .join(res.group_by("date").agg(pl.col("res_breadth").first().alias("res"),
                                        pl.col("res_ma60").n_unique().alias("_x")).select("date","res"),
              on="date", how="inner").sort("date"))
bothn = e1.filter(pl.col("prod").is_not_null() & pl.col("res").is_not_null())
diff = (bothn["prod"]-bothn["res"]).abs()
OUT["E1_breadth"] = {
    "days_total": e1.height,
    "days_both_nonnull": bothn.height,
    "max_abs_diff": float(diff.max() if diff.len() else -1),
    "mean_abs_diff": float(diff.mean() if diff.len() else -1),
    "days_gt_1e-12": int((diff>1e-12).sum()),
    "null_days_prod": e1.filter(pl.col("prod").is_null())["date"].cast(str).to_list(),
    "null_days_res":  e1.filter(pl.col("res").is_null())["date"].cast(str).to_list(),
    "mixed_null_days": e1.filter(pl.col("prod").is_null() != pl.col("res").is_null())["date"].cast(str).to_list(),
    "mean_prod": float(bothn["prod"].mean()), "mean_res": float(bothn["res"].mean()),
    "rows_with_differing_values_within_day": int(e1.filter(pl.col("nuniq")>1).height),
}
wdf2 = o.filter(pl.col("date")>=pl.lit(date(2026,10,20)))
OUT["W3_breadth_nonnull_in_window"] = int(wdf2.filter(pl.col("bore").is_not_null()).height)
OUT["W3_window_days"] = wdf2.height

# W4: xs_rank_pool 窗口内 null
cr = dsl.compile_formula("xs_rank_pool(vol60, in_universe)")
OUT["W4_compile"] = {"ok": cr.ok, "errors":[(e.code,e.message) for e in cr.errors]}
OUT["W4_compile_refs"] = sorted(getattr(cr,"referenced_factors",[]) or [])

Path("research/independent-review-20261107/b2").mkdir(parents=True, exist_ok=True)
Path("research/independent-review-20261107/b2/step1.json").write_text(
    json.dumps(OUT, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
