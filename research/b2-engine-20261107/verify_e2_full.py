"""E2 截面排名族的**全样本**判据 (契约 v0.7 §3.4.2 / §3.4.3)。

小样本判据见 verify_e2_fixtures.py (XS-A5/A6/A8/B1/B2 + 6 行负样本)。
本脚本补全样本段: XS-A1(值域) / XS-A2(分母指纹) / XS-A3(rank 回归, 见
baseline_hashes_after.py) / XS-A4(E3 依赖) / XS-A7(ST 窗口全 null) /
XS-B2(market 值域) / XS-B3(池内外 null 形态) / XS-C2(pct 可 >1)。

数据与 E1 同一份面板, 走真实 frame 路径 (Provider 物化 in_universe + DSL 编译)。
只读: 不写库、不注册新因子、不跑收益回测。
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
from app.extensions.factors import ensure_factor_providers, factor_provider_for
from app.factors import dsl
from app.tickflow.security_status import read_st_history

PANEL = "read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet')"
EVAL_START, EVAL_END = date(2019, 7, 1), date(2026, 10, 30)
PANEL_END = date(2026, 11, 6)
WARMUP_START = date(2018, 1, 8)
ST_WINDOW = (date(2026, 10, 20), date(2026, 11, 6))
RESULT = {}
LOGS = Path("research/b2-engine-20261107/logs")

ensure_factor_providers()
RESULT["XS-A4_provider_registered"] = factor_provider_for(FACTOR_COLUMN_IN_UNIVERSE) is not None

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

history = read_st_history(settings.data_dir)
prod = compute_in_universe(frame, st_history=history, params=UniverseParams())
diag = universe_diagnostics(frame, st_history=history).select("date", "unknown_reason")

# vol60 是 canonical id 的 alias 侧, 这里只用列: 用 DSL 现算 (与 pack 同一式)
VOL60 = "ts_std((close - ts_delay(close, 1)) / ts_delay(close, 1), 60)"
vol60_compiled = dsl.compile_formula(VOL60)
assert vol60_compiled.ok, [(e.code, e.message) for e in vol60_compiled.errors]

FORMULAS = {
    "xs_rank_pool": "xs_rank_pool(" + VOL60 + ", in_universe)",
    "xs_rank_market": "xs_rank_market(" + VOL60 + ")",
    "xs_rank_pct": "xs_rank_pct(" + VOL60 + ", in_universe)",
}

compiled = {}
for name, text in FORMULAS.items():
    c = dsl.compile_formula(text)
    if not c.ok:
        RESULT.setdefault("compile_errors", {})[name] = [
            {"code": e.code, "message": e.message} for e in c.errors
        ]
        continue
    compiled[name] = c
RESULT["compiled_ok"] = sorted(compiled)

print("[2] 计算列 ...", flush=True)
work = prod.with_columns(pl.col("close").cast(pl.Float64))
work = vol60_compiled.frame_transform(work).rename({dsl.FACTOR_COLUMN: "vol60"})
cols = {}
for name, c in compiled.items():
    out = c.frame_transform(work)
    assert out is not None, name
    cols[name] = out[dsl.FACTOR_COLUMN]
work = work.with_columns([s.alias(n) for n, s in cols.items()])
work = work.with_columns(pl.col(FACTOR_COLUMN_IN_UNIVERSE).alias("pool"))

win = work.filter((pl.col("date") >= pl.lit(EVAL_START)) & (pl.col("date") <= pl.lit(EVAL_END)))
print("    eval rows=%d days=%d" % (win.height, win["date"].n_unique()), flush=True)
RESULT["eval_rows"] = win.height
RESULT["eval_days"] = win["date"].n_unique()

# ------------------------------------------------------------ XS-A1 值域
print("[3] XS-A1 ...", flush=True)
pool_col = win.filter(pl.col("pool") == 1.0)
pool_nonnull = pool_col.filter(pl.col("xs_rank_pool").is_not_null())
RESULT["XS-A1_n_pool_nonnull"] = pool_nonnull.height
RESULT["XS-A1_min"] = float(pool_nonnull["xs_rank_pool"].min())
RESULT["XS-A1_max"] = float(pool_nonnull["xs_rank_pool"].max())
RESULT["XS-A1_over_1"] = int((pool_nonnull["xs_rank_pool"] > 1.0).sum())
RESULT["XS-A1_below_0"] = int((pool_nonnull["xs_rank_pool"] <= 0.0).sum())
_RESULT_A1_day = (
    pool_nonnull.group_by("date")
    .agg(
        pl.col("xs_rank_pool").max().alias("mx"),
        pl.col("xs_rank_pool").min().alias("mn"),
        pl.col("xs_rank_pool").count().alias("n"),
        (pl.col("xs_rank_pool").min() * pl.col("xs_rank_pool").count()).alias("mn_times_n"),
    )
    .with_columns((pl.col("mx") - 1.0).abs().alias("max_err"))
    .with_columns((pl.col("mn_times_n") - 1.0).abs().alias("min_err"))
)
RESULT["XS-A1_days"] = _RESULT_A1_day.height
RESULT["XS-A1_days_max_ne_1"] = int((_RESULT_A1_day["max_err"] > 1e-12).sum())
RESULT["XS-A1_days_min_times_n_ne_1"] = int((_RESULT_A1_day["min_err"] > 1e-12).sum())
RESULT["XS-A1_max_max_err"] = float(_RESULT_A1_day["max_err"].max())
RESULT["XS-A1_max_min_err"] = float(_RESULT_A1_day["min_err"].max())
RESULT["XS-A1_out_of_pool_nonnull"] = int(
    win.filter((pl.col("pool") != 1.0) & pl.col("xs_rank_pool").is_not_null()).height
)
RESULT["XS-A1_pass"] = bool(
    RESULT["XS-A1_over_1"] == 0
    and RESULT["XS-A1_below_0"] == 0
    and RESULT["XS-A1_days_max_ne_1"] == 0
    and RESULT["XS-A1_days_min_times_n_ne_1"] == 0
    and RESULT["XS-A1_out_of_pool_nonnull"] == 0
)

# ------------------------------------------------------------ XS-A2 分母指纹
print("[4] XS-A2 (④ 被禁形态对照) ...", flush=True)
# ④ 形态: 池内平均名次 / in_universe.sum()  —— 用同一份 pool 非空 rank 除以 pool 计数
fingerprint = (
    win.with_columns(
        pl.when((pl.col("pool") == 1.0) & pl.col("vol60").is_not_null())
        .then(pl.col("vol60"))
        .otherwise(None)
        .alias("member")
    )
    .with_columns(
        pl.col("member").rank(method="average").over("date").alias("rk"),
        pl.col("pool").sum().over("date").alias("pool_size"),
        pl.col("member").count().over("date").alias("member_count"),
    )
    .with_columns((pl.col("rk") / pl.col("pool_size")).alias("bad_denominator"))
)
_bd = fingerprint.filter(pl.col("pool") == 1.0)
RESULT["XS-A2_pool_size_mean"] = float(_bd["pool_size"].mean())
RESULT["XS-A2_member_count_mean"] = float(_bd["member_count"].mean())
RESULT["XS-A2_rows_bad_vs_pool_differ"] = int(
    (
        _bd.filter(pl.col("xs_rank_pool").is_not_null() & pl.col("bad_denominator").is_not_null())
        .select((pl.col("xs_rank_pool") - pl.col("bad_denominator")).abs() > 1e-12)
        .to_series()
        .sum()
    )
)
RESULT["XS-A2_distinguishable_on_full_sample"] = bool(
    RESULT["XS-A2_rows_bad_vs_pool_differ"] > 0
)
# 池内某成员 vol60 为空的日子必须存在, 否则这条判据没区分力。
# 实测: 评估窗起点 2019-07 远晚于 vol60 warmup, 池内恒无空 x -> ④ 与 ① 在真实
# 样本上恒等, 真实数据**不能**证明「没把 in_universe.sum() 当分母」。该指纹由
# verify_e2_fixtures.py 的 XS-A5 / NEG_pool_one_member 用合成样本证明
# (池内 3 只含 1 只 x 空: ① {0.5,1.0} vs ④ {0.333,0.667})。
_member_null = (
    _bd.group_by("date")
    .agg(
        (pl.col("pool_size") > pl.col("member_count")).sum().alias("days_with_null_member"),
        pl.len().alias("rows"),
    )
)
RESULT["XS-A2_days_with_pool_member_null"] = int((_member_null["days_with_null_member"] > 0).sum())
RESULT["XS-A2_note"] = (
    "真实样本上池内无空 vol60, ④ 与 ① 恒等: 区分力只由合成 fixture (XS-A5) 提供, "
    "本条不得当合格线"
)
# 与 ③ (xs_rank_pct) 的差异在真实样本上是真的 -> 用它作「口径确实不同」的实证
RESULT["XS-A2_pool_vs_pct_rows_differ"] = int(
    (
        win.filter(pl.col("xs_rank_pool").is_not_null() & pl.col("xs_rank_pct").is_not_null())
        .select((pl.col("xs_rank_pool") - pl.col("xs_rank_pct")).abs() > 1e-12)
        .to_series()
        .sum()
    )
)
RESULT["XS-A2_pool_vs_pct_max_abs_diff"] = float(
    (
        win.filter(pl.col("xs_rank_pool").is_not_null() & pl.col("xs_rank_pct").is_not_null())
        .select((pl.col("xs_rank_pool") - pl.col("xs_rank_pct")).abs().max())
        .item()
    )
)
RESULT["XS-A2_pass"] = bool(RESULT["XS-A2_pool_vs_pct_rows_differ"] > 0)

# ------------------------------------------------------------ XS-A7 / B3 / C2
print("[5] XS-A7 / B3 / C2 ...", flush=True)
# A7 窗口必须到**数据末端** (契约 §2.6 A7: 现值 14 天), 不受 EVAL_END 裁剪
window = work.filter(
    (pl.col("date") >= pl.lit(ST_WINDOW[0])) & (pl.col("date") <= pl.lit(ST_WINDOW[1]))
)
RESULT["XS-A7_window_days"] = window["date"].n_unique()
RESULT["XS-A7_window_first"] = str(window["date"].min())
RESULT["XS-A7_window_last"] = str(window["date"].max())
RESULT["XS-A7_pool_nonnull_values"] = int(window["xs_rank_pool"].is_not_null().sum())
RESULT["XS-A7_market_nonnull_values"] = int(window["xs_rank_market"].is_not_null().sum())
RESULT["XS-A7_pct_nonnull_values"] = int(window["xs_rank_pct"].is_not_null().sum())
RESULT["XS-A7_pool_all_null"] = bool(RESULT["XS-A7_pool_nonnull_values"] == 0)
# 窗口内 in_universe 全 null -> 池内 0 行, 但全样本仍有 vol60, 故 market 非 null
RESULT["XS-A7_market_still_nonnull"] = bool(RESULT["XS-A7_market_nonnull_values"] > 0)
RESULT["XS-A7_pass"] = bool(RESULT["XS-A7_pool_all_null"] and RESULT["XS-A7_pct_nonnull_values"] == 0)

# XS-B2: market 值域 (0,1], 当日 max == 1
market = win.filter(pl.col("xs_rank_market").is_not_null())
_mk = market.group_by("date").agg(
    pl.col("xs_rank_market").max().alias("mx"),
    pl.col("xs_rank_market").min().alias("mn"),
    pl.len().alias("n"),
)
RESULT["XS-B2_rows"] = market.height
RESULT["XS-B2_min"] = float(market["xs_rank_market"].min())
RESULT["XS-B2_max"] = float(market["xs_rank_market"].max())
RESULT["XS-B2_days_max_ne_1"] = int((( _mk["mx"] - 1.0).abs() > 1e-12).sum())
RESULT["XS-B2_days"] = _mk.height
RESULT["XS-B2_pass"] = bool(
    RESULT["XS-B2_min"] > 0.0 and RESULT["XS-B2_max"] <= 1.0 and RESULT["XS-B2_days_max_ne_1"] == 0
)

# XS-C2: pct 必须能产出 >1 的样本
pct = win.filter(pl.col("xs_rank_pct").is_not_null())
RESULT["XS-C2_rows"] = pct.height
RESULT["XS-C2_max"] = float(pct["xs_rank_pct"].max())
RESULT["XS-C2_over_1_rows"] = int((pct["xs_rank_pct"] > 1.0).sum())
RESULT["XS-C2_pass"] = bool(RESULT["XS-C2_over_1_rows"] > 0)

# XS-B3: 池外成员为 null, 池内非空成员有值, 池内空值成员为 null
RESULT["XS-B3_out_of_pool_nonnull"] = int(
    win.filter((pl.col("pool") != 1.0) & pl.col("xs_rank_market").is_not_null()).height
)
RESULT["XS-B3_out_of_pool_rows"] = int(win.filter(pl.col("pool") != 1.0).height)

print("\n=== E2 FULL RESULT ===")
print(json.dumps(RESULT, ensure_ascii=False, indent=1, default=str))
LOGS.mkdir(parents=True, exist_ok=True)
(LOGS / "e2_full.json").write_text(
    json.dumps(RESULT, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
)
