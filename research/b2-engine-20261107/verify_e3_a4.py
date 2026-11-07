"""E3 契约 §2.6 **A4「空值可解释」** 的自跑判据（B2 补漏；A1/A2/A3/A5/A6/A7/A8 已在 verify_e3.py）。

契约原文（v0.7 §2.6 A4）：`universe_unknown_count` 逐日为 0 或可逐条归因（哪只、哪天、缺哪列）。

本脚本断言四件事：
  A4-1 逐日守恒：bars == in_pool + not_in_pool + unknown（每个 bar 行恰好落一格）
  A4-2 归因完备：unknown > 0 的每一天都有非空 unknown_reason；unknown == 0 的天 reason 必为 null
  A4-3 原因码只来自白名单 {st_unknown_window, beyond_coverage, st_missing}，且每个码至少出现一次（无死码）
  A4-4 st_missing 天可追到具体标的与缺失列：打印当日未知标的数与样本，并断言这些标的在 st_history 中确实无当日记录

只读数据：不写库、不改因子、不跑收益回测。
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

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "research" / "b2-engine-20261107" / "logs" / "e3_a4.json"

PANEL = "read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet')"
WARMUP_START = date(2018, 1, 8)
PANEL_END = date(2026, 11, 6)
ALLOWED_REASONS = {"st_unknown_window", "beyond_coverage", "st_missing"}

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
computed = compute_in_universe(frame, st_history=history)
diag = universe_diagnostics(frame, st_history=history, params=UniverseParams())

# ---------------------------------------------------------------- A4-1 逐日守恒
diag = diag.with_columns(
    (pl.col("in_pool") + pl.col("not_in_pool") + pl.col("unknown")).alias("_sum")
)
viol = diag.filter(pl.col("_sum") != pl.col("bars"))
RESULT["A4_1_days"] = diag.height
RESULT["A4_1_conservation_violations"] = viol.height
RESULT["A4_1_pass"] = viol.height == 0
if viol.height:
    RESULT["A4_1_sample"] = viol.head(5).to_dicts()

# ---------------------------------------------------------------- A4-2 归因完备
has_unknown = pl.col("unknown") > 0
no_reason = pl.col("unknown_reason").is_null()
bad1 = diag.filter(has_unknown & no_reason)      # 有未知值却无归因
bad2 = diag.filter(~has_unknown & ~no_reason)    # 无未知值却给了归因
RESULT["A4_2_days_with_unknown"] = diag.filter(has_unknown).height
RESULT["A4_2_days_unknown_without_reason"] = bad1.height
RESULT["A4_2_days_reason_without_unknown"] = bad2.height
RESULT["A4_2_pass"] = bad1.height == 0 and bad2.height == 0
if bad1.height:
    RESULT["A4_2_bad_sample"] = bad1.head(5).to_dicts()

# ---------------------------------------------------------------- A4-3 原因码白名单
codes = sorted(set(diag["unknown_reason"].drop_nulls().to_list()))
RESULT["A4_3_codes"] = codes
RESULT["A4_3_unknown_codes"] = [c for c in codes if c not in ALLOWED_REASONS]
RESULT["A4_3_each_code_used"] = {c: int(diag.filter(pl.col("unknown_reason") == c).height) for c in codes}
RESULT["A4_3_pass"] = (
    not RESULT["A4_3_unknown_codes"]
    and set(codes) == ALLOWED_REASONS
    and all(v > 0 for v in RESULT["A4_3_each_code_used"].values())
)

# ---------------------------------------------------------------- A4-4 st_missing 可追到标的
st_days = diag.filter(pl.col("unknown_reason") == "st_missing")
RESULT["A4_4_st_missing_days"] = st_days.height
if st_days.height:
    sample_date = st_days["date"].to_list()[0]
    day_rows = computed.filter(pl.col("date") == pl.lit(sample_date))
    unknown_syms = (
        day_rows.filter(pl.col(FACTOR_COLUMN_IN_UNIVERSE).is_null())["symbol"].to_list()
    )
    hist = history
    if hist.schema["flag_date"] == pl.String:
        hist = hist.with_columns(pl.col("flag_date").str.to_date(strict=False))
    have = set(
        hist.filter(pl.col("flag_date") == pl.lit(sample_date))["symbol"].to_list()
    )
    covered = [s for s in unknown_syms if s in have]
    RESULT["A4_4_sample_date"] = str(sample_date)
    RESULT["A4_4_unknown_symbols_that_day"] = len(unknown_syms)
    RESULT["A4_4_of_which_have_st_record"] = len(covered)
    RESULT["A4_4_missing_column"] = "st_history.st_flag (该 (symbol, date) 无记录 → null, 不当 False)"
    RESULT["A4_4_pass"] = len(covered) == 0
else:
    RESULT["A4_4_pass"] = True

RESULT["all_pass"] = all(
    RESULT[k] for k in ("A4_1_pass", "A4_2_pass", "A4_3_pass", "A4_4_pass")
)
LOG.parent.mkdir(parents=True, exist_ok=True)
LOG.write_text(json.dumps(RESULT, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(RESULT, ensure_ascii=False, indent=1, default=str))
print("written", LOG)
