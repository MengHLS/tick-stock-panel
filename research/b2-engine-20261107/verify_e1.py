"""E1 `market_breadth` = xs_mean(close > ma60, in_universe) 判据 (契约 v0.7 §4.6).

走**真实 frame 路径**: 注册 universe Provider (E3) → 物化 in_universe → DSL 编译
xs_mean(...) → frame_transform。对照研究侧 research/.../common.py:186-191 逐日比。
只读数据: 不写库、不注册新因子、不跑收益回测。
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, "backend")

import duckdb
import polars as pl

from app.config import settings
from app.custom.research_universe_pack.universe import (
    FACTOR_COLUMN_IN_UNIVERSE,
    UniverseParams,
    compute_in_universe,
    universe_diagnostics,
)
from app.extensions.factors import ensure_factor_providers, factor_provider_for
from app.factors import dsl
from app.tickflow.security_status import read_st_history

PANEL = "read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet')"
EVAL_START, EVAL_END = date(2019, 7, 1), date(2026, 10, 30)
PANEL_END = date(2026, 11, 6)
WARMUP_START = date(2018, 1, 8)
RESULT = {}
LOGS = Path("research/b2-engine-20261107/logs")

ensure_factor_providers()
RESULT["provider_registered"] = factor_provider_for(FACTOR_COLUMN_IN_UNIVERSE) is not None

print("[1] load panel ...", flush=True)
t0 = time.perf_counter()
con = duckdb.connect()
con.sql("SET enable_progress_bar=false")
con.sql("SET temp_directory='D:/TSP/duckdb_tmp'")
con.sql("SET max_temp_directory_size='40GB'")
con.sql(
    "create view bars as select symbol, date, close, volume, amount, raw_close from "
    + PANEL
    + " where (symbol like '60%' or symbol like '00%')"
    + " and date between date '" + str(WARMUP_START) + "' and date '" + str(PANEL_END) + "'"
)
frame = con.sql("select * from bars order by symbol, date").pl()
con.close()
print("    rows=%d symbols=%d %.1fs" % (frame.height, frame["symbol"].n_unique(), time.perf_counter() - t0), flush=True)
RESULT["panel_rows"] = frame.height
RESULT["panel_symbols"] = frame["symbol"].n_unique()

history = read_st_history(settings.data_dir)

print("[2] E3 in_universe ...", flush=True)
prod = compute_in_universe(frame, st_history=history, params=UniverseParams())
diag = universe_diagnostics(frame, st_history=history).select("date", "unknown_reason")

ma60 = dsl.compile_formula("ts_mean(close, 60)")
assert ma60.ok, [e.message for e in ma60.errors]
RESULT["ma60_warmup"] = ma60.warmup_bars

BREADTH = "xs_mean(close > ma60, in_universe)"
print("[3] compile " + BREADTH, flush=True)
compiled = dsl.compile_formula(BREADTH)
assert compiled.ok, [(e.code, e.message) for e in compiled.errors]
RESULT["formula"] = BREADTH
RESULT["formula_cross_sectional"] = compiled.cross_sectional
RESULT["formula_warmup_bars"] = compiled.warmup_bars
RESULT["formula_referenced_factors"] = sorted(compiled.referenced_factors)
RESULT["formula_dependencies"] = sorted(compiled.dependencies)


def run_breadth(src):
    w = src.with_columns(pl.col("close").cast(pl.Float64))
    w = ma60.frame_transform(w).rename({dsl.FACTOR_COLUMN: "ma60"})
    o = compiled.frame_transform(w)
    assert o is not None, "frame_transform missing deps"
    return o.with_columns(pl.col(dsl.FACTOR_COLUMN).alias("breadth_prod"))


out = run_breadth(prod)
win = out.filter((pl.col("date") >= pl.lit(EVAL_START)) & (pl.col("date") <= pl.lit(EVAL_END)))

print("[4] research side ...", flush=True)
research = (
    frame.sort(["symbol", "date"])
    .with_columns(
        pl.col("date").cum_count().over("symbol").alias("observed_bars"),
        pl.col("amount").shift(1).rolling_mean(20).over("symbol").alias("prior_amount20"),
    )
    .with_columns(pl.col("close").rolling_mean(60).over("symbol").alias("ma60_research"))
)
research = research.with_row_index("__r").sort("date").join_asof(
    history.sort("flag_date"), left_on="date", right_on="flag_date",
    by="symbol", strategy="backward", check_sortedness=False,
).sort("__r").drop("__r", "flag_date")
research = research.with_columns(
    (
        (pl.col("observed_bars") >= 120)
        & (pl.col("st_flag").fill_null(False) == False)
        & (pl.col("raw_close") >= 3.0)
        & (pl.col("prior_amount20") >= 1e8)
        & (pl.col("volume") > 0)
    ).fill_null(False).alias("in_universe_research")
)
research = research.with_columns(
    pl.when(pl.col("in_universe_research") & pl.col("ma60_research").is_not_null())
    .then((pl.col("close") > pl.col("ma60_research")).cast(pl.Float64))
    .otherwise(None)
    .mean().over("date").alias("breadth_research")
)

ma60_cmp = (
    out.select("symbol", "date", "ma60")
    .join(research.select("symbol", "date", "ma60_research"), on=["symbol", "date"], how="inner")
    .filter((pl.col("date") >= pl.lit(EVAL_START)) & (pl.col("date") <= pl.lit(EVAL_END)))
)
both_ma = ma60_cmp.filter(pl.col("ma60").is_not_null() & pl.col("ma60_research").is_not_null())
RESULT["ma60_n_both"] = both_ma.height
RESULT["ma60_max_abs_diff"] = float((both_ma["ma60"] - both_ma["ma60_research"]).abs().max()) if both_ma.height else None
RESULT["ma60_null_mismatch"] = ma60_cmp.filter(pl.col("ma60").is_null() != pl.col("ma60_research").is_null()).height

print("[5] B1 ...", flush=True)
prod_daily = win.group_by("date").agg(pl.col("breadth_prod").first().alias("prod")).sort("date")
res_daily = (
    research.filter((pl.col("date") >= pl.lit(EVAL_START)) & (pl.col("date") <= pl.lit(EVAL_END)))
    .group_by("date").agg(pl.col("breadth_research").first().alias("research")).sort("date")
)
merged = prod_daily.join(res_daily, on="date", how="full", coalesce=True).sort("date")
merged = merged.join(diag, on="date", how="left")
RESULT["B1_n_days_research"] = res_daily.height
RESULT["B1_n_days_prod"] = prod_daily.filter(pl.col("prod").is_not_null()).height
null_days = merged.filter(pl.col("prod").is_null())
covered = merged.filter(pl.col("prod").is_not_null() & pl.col("research").is_not_null())
covered = covered.with_columns((pl.col("prod") - pl.col("research")).alias("d"))
RESULT["B1_n_compared_days"] = covered.height
RESULT["B1_max_abs_diff"] = float(covered["d"].abs().max()) if covered.height else None
RESULT["B1_mean_abs_diff"] = float(covered["d"].abs().mean()) if covered.height else None
RESULT["B1_days_over_tol"] = int((covered["d"].abs() >= 1e-12).sum()) if covered.height else 0
RESULT["B1_mean_research_subset"] = float(covered["research"].mean()) if covered.height else None
RESULT["B1_mean_prod_subset"] = float(covered["prod"].mean()) if covered.height else None
RESULT["B1_null_days"] = null_days.height
RESULT["B1_null_days_list"] = [
    {"date": str(r["date"]), "reason": r["unknown_reason"], "research_value": r["research"]}
    for r in null_days.sort("date").to_dicts()
]
RESULT["B1_null_reason_counts"] = {
    (r["unknown_reason"] or "none"): r["len"]
    for r in null_days.group_by("unknown_reason").len().to_dicts()
}
RESULT["B1_null_equals_expected"] = bool(
    null_days.height
    == sum(1 for r in null_days.to_dicts() if r["unknown_reason"] in {"st_unknown_window", "beyond_coverage"})
)
RESULT["B1_pass"] = bool(covered.height > 0 and RESULT["B1_days_over_tol"] == 0 and RESULT["B1_null_equals_expected"])
RESULT["diag_mean_research_full"] = float(res_daily["research"].drop_nulls().mean())

print("[6] B2 ...", flush=True)
dates = pl.DataFrame({"date": research["date"].unique().sort()})
dates = dates.with_columns(pl.Series("next_date", dates["date"].shift(-1))).with_columns(
    (pl.col("next_date").is_null() | (pl.col("next_date").dt.month() != pl.col("date").dt.month())).alias("month_end")
).select("date", "month_end")
me = merged.join(dates, on="date", how="left").filter(pl.col("month_end") == True).sort("date")
me_null = me.filter(pl.col("prod").is_null())
me_cmp = me.filter(pl.col("prod").is_not_null())
RESULT["B2_n_month_end_research"] = me.height
RESULT["B2_n_month_end_compared"] = me_cmp.height
RESULT["B2_pass_count"] = int((me_cmp["prod"] >= 0.5).sum())
RESULT["B2_pass_rate"] = float(RESULT["B2_pass_count"]) / me_cmp.height if me_cmp.height else None
RESULT["B2_null_month_end_list"] = [
    {"date": str(r["date"]), "reason": r["unknown_reason"]} for r in me_null.to_dicts()
]
RESULT["B2_old_denominator_rate"] = float(RESULT["B2_pass_count"]) / me.height if me.height else None
RESULT["B2_pass"] = bool(
    me_cmp.height > 0
    and int((me_cmp["research"] >= 0.5).sum()) == RESULT["B2_pass_count"]
    and len(RESULT["B2_null_month_end_list"]) == me_null.height
)

print("[7] B3 ...", flush=True)
b3 = win.group_by("date").agg(
    pl.col("breadth_prod").min().alias("mn"),
    pl.col("breadth_prod").max().alias("mx"),
    pl.col("breadth_prod").null_count().alias("nulls"),
    pl.len().alias("rows"),
)
RESULT["B3_days_with_spread"] = int(b3.filter((pl.col("mx") - pl.col("mn")).abs() > 0).height)
RESULT["B3_max_spread"] = float((b3["mx"] - b3["mn"]).abs().max()) if b3.height else None
b3_pool = win.filter((pl.col(FACTOR_COLUMN_IN_UNIVERSE) == 0.0) & pl.col("breadth_prod").is_not_null()).select("date").unique().height
RESULT["B3_days_with_out_of_pool_broadcast"] = b3_pool
RESULT["B3_days_with_any_nonnull"] = int(b3.filter(pl.col("nulls") < pl.col("rows")).height)
RESULT["B3_pass"] = bool(RESULT["B3_days_with_spread"] == 0 and b3_pool == RESULT["B3_days_with_any_nonnull"])

print("[8] B4 / B5 / B6 ...", flush=True)
empty_pool = pl.DataFrame({
    "symbol": ["a", "b"], "date": [date(2026, 6, 30)] * 2,
    "close": [10.0, 11.0], "volume": [1.0, 1.0], "amount": [1.0, 1.0],
    "raw_close": [10.0, 11.0], "ma60": [9.0, 12.0], "in_universe": [0.0, 0.0],
})
r4 = compiled.frame_transform(empty_pool)
vals = r4[dsl.FACTOR_COLUMN].to_list() if r4 is not None else None
RESULT["B4_empty_pool_values"] = vals
RESULT["B4_all_null_not_zero"] = bool(vals is not None and all(v is None for v in vals))


def table_hash(t):
    return hashlib.sha256(
        pl.DataFrame({"date": t["date"], "v": t["prod"]}).hash_rows(seed=91).to_numpy().tobytes()
    ).hexdigest()


RESULT["B5_hash_run1"] = table_hash(prod_daily)
out2 = run_breadth(compute_in_universe(frame, st_history=history, params=UniverseParams()))
prod_daily2 = (
    out2.filter((pl.col("date") >= pl.lit(EVAL_START)) & (pl.col("date") <= pl.lit(EVAL_END)))
    .group_by("date").agg(pl.col("breadth_prod").first().alias("prod")).sort("date")
)
RESULT["B5_hash_run2"] = table_hash(prod_daily2)
RESULT["B5_idempotent"] = RESULT["B5_hash_run1"] == RESULT["B5_hash_run2"]
RESULT["B6_warmup_bars"] = compiled.warmup_bars
RESULT["B6_pass"] = bool(compiled.warmup_bars == 120)

print("\n=== E1 RESULT ===")
print(json.dumps(RESULT, ensure_ascii=False, indent=1, default=str))
LOGS.mkdir(parents=True, exist_ok=True)
(LOGS / "e1_verify.json").write_text(
    json.dumps(RESULT, ensure_ascii=False, indent=1, default=str, sort_keys=True), encoding="utf-8"
)
