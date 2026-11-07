"""E3 `in_universe` 判据 (契约 v0.7 §2.6 A1-A8) 的自跑脚本。

只读数据: 不写库、不改因子、不跑收益回测。
"""
from __future__ import annotations

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
from app.tickflow.security_status import read_st_history

PANEL = "read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet')"
EVAL_START, EVAL_END = date(2019, 7, 1), date(2026, 10, 30)
PANEL_END = date(2026, 11, 6)   # A7 要验到数据末端 (契约 §2.6 A7: 当前 14 个交易日)
WARMUP_START = date(2018, 1, 8)          # 面板起点, 与 AXIS_MIN 一致
RESULT: dict[str, object] = {}

print("[1] 载入面板 ...", flush=True)
t0 = time.perf_counter()
con = duckdb.connect()
con.sql("SET enable_progress_bar=false")
con.sql("SET temp_directory='D:/TSP/duckdb_tmp'")
con.sql("SET max_temp_directory_size='40GB'")
con.sql(f"""create view bars as
  select symbol, date, volume, amount, raw_close from {PANEL}
  where (symbol like '60%' or symbol like '00%')
    and date between date '{WARMUP_START}' and date '{PANEL_END}'""")
frame = con.sql("select * from bars order by symbol, date").pl()
con.close()
print(f"    rows={frame.height:,} symbols={frame['symbol'].n_unique():,} "
      f"{time.perf_counter()-t0:.1f}s", flush=True)

history = read_st_history(settings.data_dir)

# ---------------------------------------------------------------- A1 / A4 / A7
print("[2] 生产口径 vs 研究对账口径 ...", flush=True)
prod = compute_in_universe(frame, st_history=history)                       # unknown
recon = compute_in_universe(
    frame, st_history=history,
    params=UniverseParams(st_flag_missing_policy="treat_non_st"),
)
for name, computed in (("unknown", prod), ("treat_non_st", recon)):
    win = computed.filter(
        (pl.col("date") >= pl.lit(EVAL_START)) & (pl.col("date") <= pl.lit(EVAL_END))
    )
    pool_daily = (
        win.group_by("date")
        .agg((pl.col(FACTOR_COLUMN_IN_UNIVERSE) == 1.0).sum().cast(pl.Int64).alias("p"))
        .sort("date")
    )
    RESULT[f"daily_mean_pool_{name}"] = round(float(pool_daily["p"].mean()), 6)
    RESULT[f"n_days_{name}"] = pool_daily.height

# 研究侧 in_universe 复算 (common.py 口径, ST 缺失 fill_null(False))
print("[3] 研究侧复算 ...", flush=True)
research = (
    frame.sort(["symbol", "date"])
    .with_columns(
        pl.col("date").cum_count().over("symbol").alias("observed_bars"),
        pl.col("amount").shift(1).rolling_mean(20).over("symbol").alias("prior_amount20"),
    )
)
research = research.with_row_index("__r").sort("date").join_asof(
    history.sort("flag_date"), left_on="date", right_on="flag_date",
    by="symbol", strategy="backward", check_sortedness=False,
).sort("__r").drop("__r", "flag_date")
research = research.with_columns(
    (
        (pl.col("observed_bars") >= 120)
        & (pl.col("st_flag").fill_null(False) == False)  # noqa: E712
        & (pl.col("raw_close") >= 3.0)
        & (pl.col("prior_amount20") >= 1e8)
        & (pl.col("volume") > 0)
    ).fill_null(False).alias("research_in_universe")
)
win_r = research.filter(
    (pl.col("date") >= pl.lit(EVAL_START)) & (pl.col("date") <= pl.lit(EVAL_END))
)
rd = (
    win_r.group_by("date")
    .agg(pl.col("research_in_universe").sum().cast(pl.Int64).alias("p"))
    .sort("date")
)
RESULT["daily_mean_pool_research"] = round(float(rd["p"].mean()), 6)
RESULT["n_days_research"] = rd.height

# 逐日 diff: 只在对账模式下比较, 且剔出 ST 不可判定窗口 (研究侧无此概念)
merged = (
    recon.filter((pl.col("date") >= pl.lit(EVAL_START)) & (pl.col("date") <= pl.lit(EVAL_END)))
    .group_by("date")
    .agg(
        (pl.col(FACTOR_COLUMN_IN_UNIVERSE) == 1.0).sum().cast(pl.Int64).alias("prod_cnt"),
        # 全 null 日 sum()==0, 必须用非空计数区分「池空」与「不可判定」
        pl.col(FACTOR_COLUMN_IN_UNIVERSE).is_not_null().sum().cast(pl.Int64).alias("prod_known"),
    )
    .with_columns(
        pl.when(pl.col("prod_known") > 0)
        .then(pl.col("prod_cnt").cast(pl.Int64))
        .otherwise(pl.lit(None, dtype=pl.Int64))
        .alias("prod")
    )
    .join(rd.rename({"p": "research"}), on="date", how="inner")
    .sort("date")
)
all_days = merged.with_columns((pl.col("prod") - pl.col("research")).alias("d"))
null_days = all_days.filter(pl.col("prod").is_null())
covered = all_days.filter(pl.col("prod").is_not_null())
diff = covered
RESULT["A1_n_compared_days"] = diff.height
RESULT["A1_mean_abs_diff"] = float(diff["d"].abs().mean())
RESULT["A1_max_abs_diff"] = int(diff["d"].abs().max())
RESULT["A1_days_with_diff"] = int((diff["d"].abs() > 0).sum())
RESULT["A1_null_days"] = null_days.height
RESULT["A1_null_days_list"] = [str(v) for v in null_days["date"].to_list()]
RESULT["A1_strict_pass"] = bool(RESULT["A1_days_with_diff"] == 0)
RESULT["A1_covered_mean_prod"] = round(float(covered["prod"].mean()), 6)
RESULT["A1_covered_mean_research"] = round(float(covered["research"].mean()), 6)
RESULT["A1_prod_mean"] = round(float(covered["prod"].mean()), 6)
RESULT["A1_diff_days"] = [
    {"date": str(r["date"]), "prod": r["prod"], "research": r["research"]}
    for r in diff.filter(pl.col("d").abs() > 0).sort("date").to_dicts()
]

# ---------------------------------------------------------------- A7 / A8
print("[4] ST 不可判定窗口 ...", flush=True)
diag = universe_diagnostics(frame, st_history=history)
window = diag.filter(pl.col("unknown_reason").is_not_null())
RESULT["A7_window_days"] = window.height
RESULT["A7_window_first"] = str(window["date"].min())
RESULT["A7_window_last"] = str(window["date"].max())
RESULT["A7_all_values_null"] = bool(
    window.select((pl.col("in_pool") == 0) & (pl.col("not_in_pool") == 0)).to_series().all()
)
RESULT["A7_unknown_equals_bars"] = bool(
    window.select(pl.col("unknown") == pl.col("bars")).to_series().all()
)
RESULT["A7_reason_counts"] = {
    row["unknown_reason"]: row["len"]
    for row in window.group_by("unknown_reason").len().sort("unknown_reason").to_dicts()
}
RESULT["A7_dates"] = [str(v) for v in window["date"].to_list()]
_a7 = diag.filter(
    (pl.col("date") >= pl.lit(date(2026, 10, 20))) & (pl.col("date") <= pl.lit(date(2026, 11, 6)))
)
RESULT["A7_window_2026_10_20_to_11_06_days"] = _a7.height
RESULT["A7_window_dates"] = [str(v) for v in _a7["date"].to_list()]
RESULT["A7_window_all_null"] = bool(
    _a7.select(((pl.col("in_pool") == 0) & (pl.col("not_in_pool") == 0)).all()).item()
)
RESULT["A7_window_unknown_eq_bars"] = bool(
    _a7.select((pl.col("unknown") == pl.col("bars")).all()).item()
)
RESULT["A7_window_reasons"] = {
    r["unknown_reason"]: r["len"] for r in _a7.group_by("unknown_reason").len().to_dicts()
}
_sm = diag.filter(pl.col("unknown_reason") == pl.lit("st_missing"))
RESULT["st_missing_days"] = _sm.height
RESULT["st_missing_first"] = str(_sm["date"].min()) if _sm.height else None
RESULT["st_missing_last"] = str(_sm["date"].max()) if _sm.height else None
RESULT["st_missing_in_eval"] = _sm.filter(
    (pl.col("date") >= pl.lit(EVAL_START)) & (pl.col("date") <= pl.lit(EVAL_END))
).height

# A8: 末端不外推 —— 10-30 及以后不得出现任何非 null
tail = diag.filter(pl.col("date") > pl.lit(history["flag_date"].max()))
RESULT["A8_rows_after_coverage"] = tail.height
RESULT["A8_non_null_after_coverage"] = int(
    tail.select((pl.col("in_pool") + pl.col("not_in_pool")).sum()).item()
)

# ---------------------------------------------------------------- A2 / A3
print("[5] 池内 bar 覆盖率 / count 差异归因 ...", flush=True)
win_prod = prod.filter(
    (pl.col("date") >= pl.lit(EVAL_START)) & (pl.col("date") <= pl.lit(EVAL_END))
)
pool_rows = win_prod.filter(pl.col(FACTOR_COLUMN_IN_UNIVERSE) == 1.0)
RESULT["A2_pool_rows"] = pool_rows.height
RESULT["A2_pool_rows_null_rawclose"] = int(pool_rows["raw_close"].null_count())
RESULT["A2_pool_rows_null_volume"] = int(pool_rows["volume"].null_count())
RESULT["A2_pool_symbols"] = pool_rows["symbol"].n_unique()

# A3: 池内家数 vs 池内 close 非空家数 (XS-A5 上游)
x_null = (
    win_prod.group_by("date")
    .agg(
        (pl.col(FACTOR_COLUMN_IN_UNIVERSE) == 1.0).sum().cast(pl.Int64).alias("pool"),
    )
    .sort("date")
)
RESULT["A3_pool_mean"] = round(float(x_null["pool"].mean()), 6)

# ---------------------------------------------------------------- A5 / A6
print("[6] 版本自洽 / 无前视 ...", flush=True)
alt = compute_in_universe(
    frame, st_history=history,
    params=UniverseParams(min_price_raw=5.0),
)
win_alt = alt.filter(
    (pl.col("date") >= pl.lit(EVAL_START)) & (pl.col("date") <= pl.lit(EVAL_END))
)
alt_pool = win_alt.group_by("date").agg(
    (pl.col(FACTOR_COLUMN_IN_UNIVERSE) == 1.0).sum().alias("p")
).sort("date")
RESULT["A5_param_change_pool_mean"] = round(float(alt_pool["p"].mean()), 6)
RESULT["A5_differs_from_default"] = bool(
    abs(RESULT["A5_param_change_pool_mean"] - RESULT["A3_pool_mean"]) > 1e-9
)

# A6: 用截断到某日的尾部数据回放, 历史日必须逐位相同
cutoff = date(2024, 6, 28)
trunc = compute_in_universe(
    frame.filter(pl.col("date") <= pl.lit(cutoff)), st_history=history
)
full_hist = prod.filter(pl.col("date") <= pl.lit(cutoff))
joined = (
    trunc.select("symbol", "date", pl.col(FACTOR_COLUMN_IN_UNIVERSE).alias("trunc"))
    .join(
        full_hist.select("symbol", "date", pl.col(FACTOR_COLUMN_IN_UNIVERSE).alias("full")),
        on=["symbol", "date"], how="full", coalesce=True,
    )
)
both = joined.filter(pl.col("trunc").is_not_null() | pl.col("full").is_not_null())
mismatch = both.filter(
    (pl.col("trunc").is_null() != pl.col("full").is_null())
    | (pl.col("trunc") != pl.col("full"))
)
RESULT["A6_rows"] = both.height
RESULT["A6_mismatch"] = mismatch.height

print("\n=== RESULT ===")
print(json.dumps(RESULT, ensure_ascii=False, indent=1, default=str))
Path("research/b2-engine-20261107/logs").mkdir(parents=True, exist_ok=True)
Path("research/b2-engine-20261107/logs/e3_verify.json").write_text(
    json.dumps(RESULT, ensure_ascii=False, indent=1, default=str, sort_keys=True), encoding="utf-8"
)
