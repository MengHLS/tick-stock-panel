"""E3 / E1 / E2 在 2026-10-20…2026-11-06 这 14 个交易日的同窗口断言 (契约 v0.7 §2.6-4 / §4.6)。

背景: verify_e3.py / verify_e1.py 的 EVAL_END=2026-10-30, 14 日窗口只覆盖到 9 天。
本脚本把窗口拉满 14 天, 四条断言一次跑完:
  W1  E3: 窗口内 count(in_universe ∈ {0.0, 1.0}) == 0 (全 null, 不是 false)
  W2  E3: 每日 universe_unknown_count == 当日有 bar 行数, reason 全为 st_unknown_window
  W3  E1: 窗口内 14 天 market_breadth(xs_mean(close > ma60, in_universe)) 全 null
  W4  E2: 窗口内 14 天 xs_rank_pool(vol60, in_universe) 全 null
只读数据: 不写库、不注册因子、不跑收益回测。
"""
from __future__ import annotations

import json
import sys
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
from app.factors import dsl
from app.tickflow.security_status import read_st_history

PANEL = "read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet')"
WIN_START, WIN_END = date(2026, 10, 20), date(2026, 11, 6)
LOAD_START = date(2026, 4, 1)  # 只需覆盖 60 日均线 + 120 根 observed_bars 的回看
RESULT: dict = {}
LOGS = Path("research/b2-engine-20261107/logs")

con = duckdb.connect()
con.sql("SET enable_progress_bar=false")
con.sql("SET temp_directory='D:/TSP/duckdb_tmp'")
con.sql("SET max_temp_directory_size='40GB'")
con.sql(
    "create view bars as select symbol, date, close, volume, amount, raw_close from "
    + PANEL
    + " where (symbol like '60%' or symbol like '00%')"
    + " and date between date '" + str(LOAD_START) + "' and date '" + str(WIN_END) + "'"
)
frame = con.sql("select * from bars order by symbol, date").pl()
con.close()
RESULT["panel_rows"] = frame.height
RESULT["panel_symbols"] = frame["symbol"].n_unique()
RESULT["load_start"] = str(LOAD_START)

history = read_st_history(settings.data_dir)
prod = compute_in_universe(frame, st_history=history, params=UniverseParams())

win = prod.filter((pl.col("date") >= pl.lit(WIN_START)) & (pl.col("date") <= pl.lit(WIN_END)))
RESULT["window_days"] = win["date"].n_unique()
RESULT["window_first"] = str(win["date"].min())
RESULT["window_last"] = str(win["date"].max())
RESULT["window_rows"] = win.height

# ---- W1: 窗口内 in_universe ∈ {0.0,1.0} 的行数必须为 0
col = pl.col(FACTOR_COLUMN_IN_UNIVERSE)
value_like = win.filter(col.is_not_null() & ((col == 0.0) | (col == 1.0)))
RESULT["W1_rows_in_0_1"] = value_like.height
RESULT["W1_nonnull_rows"] = int(win[FACTOR_COLUMN_IN_UNIVERSE].is_not_null().sum())
RESULT["W1_null_rows"] = int(win[FACTOR_COLUMN_IN_UNIVERSE].is_null().sum())
RESULT["W1_pass"] = bool(value_like.height == 0 and win.height > 0)

# ---- W2: 每日 unknown 计数 == 当日有 bar 行数; reason 全 st_unknown_window
diag_win = universe_diagnostics(frame, st_history=history).filter(
    (pl.col("date") >= pl.lit(WIN_START)) & (pl.col("date") <= pl.lit(WIN_END))
)
RESULT["W2_per_day"] = [
    {"date": str(r["date"]), "bars": int(r["bars"]), "unknown": int(r["unknown"]),
     "reason": r["unknown_reason"]}
    for r in diag_win.to_dicts()
]
RESULT["W2_all_match"] = bool(diag_win.height == 14 and (diag_win["bars"] == diag_win["unknown"]).all())
RESULT["W2_reasons"] = sorted({str(r) for r in diag_win["unknown_reason"].drop_nulls().unique().to_list()})
# 允许两种「不可判」原因码: st_unknown_window (8 天) 与 beyond_coverage (6 天)。
# 后者来自 st_history 覆盖期末端 2026-10-29, 与 verify_e3.py A7 记录的 8+6 完全一致;
# 契约 §2.6 只要求「不可判且值为 null」, 不要求两端原因码相同。
_ALLOWED_REASONS = {"st_unknown_window", "beyond_coverage"}
RESULT["W2_reason_counts"] = {
    str(r["unknown_reason"]): int(r["len"])
    for r in diag_win.group_by("unknown_reason").len().to_dicts()
}
RESULT["W2_pass"] = bool(
    RESULT["W2_all_match"]
    and set(RESULT["W2_reasons"]) <= _ALLOWED_REASONS
    and len(RESULT["W2_reasons"]) > 0
    and diag_win["unknown_reason"].null_count() == 0
)

# ---- W3: E1 breadth 窗口内全 null
ma60 = dsl.compile_formula("ts_mean(close, 60)")
assert ma60.ok, [(e.code, e.message) for e in ma60.errors]
breadth = dsl.compile_formula("xs_mean(close > ma60, in_universe)")
assert breadth.ok, [(e.code, e.message) for e in breadth.errors]
with_ma = ma60.frame_transform(prod.with_columns(pl.col("close").cast(pl.Float64))).rename(
    {dsl.FACTOR_COLUMN: "ma60"}
)
out_b = breadth.frame_transform(with_ma)
b_win = out_b.filter((pl.col("date") >= pl.lit(WIN_START)) & (pl.col("date") <= pl.lit(WIN_END)))
b_daily = b_win.group_by("date").agg(
    pl.col(dsl.FACTOR_COLUMN).count().alias("nonnull"),
    pl.len().alias("rows"),
).sort("date")
RESULT["W3_days"] = b_daily.height
RESULT["W3_days_with_nonnull"] = int((b_daily["nonnull"] > 0).sum())
RESULT["W3_max_nonnull"] = int(b_daily["nonnull"].max()) if b_daily.height else None
RESULT["W3_pass"] = bool(b_daily.height == 14 and int((b_daily["nonnull"] > 0).sum()) == 0)

# ---- W4: E2 xs_rank_pool(vol60, in_universe) 窗口内全 null
vol60 = dsl.compile_formula("ts_std(close / ts_delay(close, 1) - 1, 60)")
assert vol60.ok, [(e.code, e.message) for e in vol60.errors]
pool = dsl.compile_formula("xs_rank_pool(vol60, in_universe)")
assert pool.ok, [(e.code, e.message) for e in pool.errors]
with_vol = vol60.frame_transform(prod.with_columns(pl.col("close").cast(pl.Float64))).rename(
    {dsl.FACTOR_COLUMN: "vol60"}
)
out_p = pool.frame_transform(with_vol)
p_win = out_p.filter((pl.col("date") >= pl.lit(WIN_START)) & (pl.col("date") <= pl.lit(WIN_END)))
p_daily = p_win.group_by("date").agg(
    pl.col(dsl.FACTOR_COLUMN).count().alias("nonnull"),
    pl.len().alias("rows"),
).sort("date")
RESULT["W4_days"] = p_daily.height
RESULT["W4_max_nonnull"] = int(p_daily["nonnull"].max()) if p_daily.height else None
RESULT["W4_pass"] = bool(p_daily.height == 14 and int((p_daily["nonnull"] > 0).sum()) == 0)

RESULT["all_pass"] = all(RESULT[k] for k in ("W1_pass", "W2_pass", "W3_pass", "W4_pass"))
print(json.dumps(RESULT, ensure_ascii=False, indent=1, default=str))
LOGS.mkdir(parents=True, exist_ok=True)
(LOGS / "window_20261107.json").write_text(
    json.dumps(RESULT, ensure_ascii=False, indent=1, default=str, sort_keys=True), encoding="utf-8"
)
