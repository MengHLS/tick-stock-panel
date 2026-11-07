"""独立复跑 #4: E3-A1 的「行级」等价性 (不止逐日家数), 两模式各一遍。"""
from __future__ import annotations
import json, sys
from datetime import date
from pathlib import Path
sys.path.insert(0, "backend"); sys.path.insert(0, "research/strategy-search-20261107/scripts")
import polars as pl
from app.config import settings
from app.custom.research_universe_pack.universe import UniverseParams, compute_in_universe
from app.tickflow.security_status import read_st_history
import common as R

EVAL_START, EVAL_END = date(2019,7,1), date(2026,10,30)
m = R.open_market()
frame = R.load_panel(m, R.WARMUP_START, EVAL_END).with_columns(pl.col("date").cast(pl.Date))
r = R.add_universe(R.add_indicators(frame)).select(
    "symbol","date", pl.col("in_universe").cast(pl.Float64).alias("res_iu"))
hist = read_st_history(settings.data_dir)
base = frame.select("symbol","date","close","volume","amount","raw_close")
out = {}
for mode, params in (("unknown", UniverseParams()),
                     ("treat_non_st", UniverseParams(st_flag_missing_policy="treat_non_st"))):
    p = compute_in_universe(base, st_history=hist, params=params).join(r, on=["symbol","date"], how="left")
    w = p.filter((pl.col("date")>=pl.lit(EVAL_START)) & (pl.col("date")<=pl.lit(EVAL_END)))
    known = w.filter(pl.col("in_universe").is_not_null())
    mism = known.filter(pl.col("in_universe") != pl.col("res_iu"))
    out[mode] = {"rows_known": known.height, "row_mismatches": mism.height,
                 "mismatch_days": mism["date"].n_unique(),
                 "mismatch_symbols": mism["symbol"].n_unique()}
    if mism.height:
        out[mode]["sample_mismatch"] = mism.head(5).select("symbol","date","in_universe","res_iu").rows()
    out[mode]["null_rows"] = w.filter(pl.col("in_universe").is_null()).height
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
Path("research/independent-review-20261107/b2/step4.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
