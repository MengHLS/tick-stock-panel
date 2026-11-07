#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""F 类八只因子 —— 系统 DSL 求值 vs 研究侧 add_indicators 逐位对账（F-A3）。

口径与判据来源：
  - docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md §7.1（公式原文）/ §7.3 V3 / §7.6 F-A3
  - docs/research/caliber-decisions-20261107.md §1.4（逐因子口径）/ §1.7（逐位验收判据）

做法（单次全帧、不分块、不抽样）：
  1. 用研究侧 common.open_market() + common.load_panel() 取工作帧
     （2018-01-08 ~ 2026-10-30，60/00 开头，含 ST 与涨跌停标记）。只读 import，不改该文件。
  2. common.add_indicators() 得到研究列。
  3. 同一帧上跑系统侧 compile_formula(...).frame_transform(...) —— 与
     app/strategy/scoring.py:391 生产物化路径同一个函数；本脚本刻意不经
     materialize_cache（否则会往 data_dir 缓存目录写 parquet），计算路径一致。
  4. 在窗口 2019-07-01 ~ 2026-10-30 内逐值比对。

输出：docs/factors/evidence/F_CLASS_PARITY_20261107.json

运行：
  cd <repo> && backend/.venv/Scripts/python.exe docs/factors/evidence/scripts/f_class_parity.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "research" / "strategy-search-20261107" / "scripts"))

import common  # noqa: E402  （研究侧工作帧；只读 import）
from app.config import settings  # noqa: E402
from app.factors import store as factor_store  # noqa: E402
from app.factors.dsl import FACTOR_COLUMN, compile_formula  # noqa: E402

EVAL_START = date(2019, 7, 1)
EVAL_END = date(2026, 10, 30)
TOL = 1e-12

# (因子 id, 契约 §7.1 公式原文, 研究侧列名, 契约期望 warmup)
FACTORS = [
    ("uf_vol60", "ts_std(close / ts_delay(close, 1) - 1, 60)", "vol60", 61),
    ("uf_ma120", "ts_mean(close, 120)", "ma120", 121),
    ("uf_ma200", "ts_mean(close, 200)", "ma200", 201),
    ("uf_prior_high_20", "ts_max(ts_delay(high, 1), 20)", "prior_high20", 21),
    ("uf_prior_high_55", "ts_max(ts_delay(high, 1), 55)", "prior_high55", 56),
    ("uf_prior_high_250", "ts_max(ts_delay(high, 1), 250)", "prior_high250", 251),
    ("uf_prior_low_10", "ts_min(ts_delay(low, 1), 10)", "prior_low10", 11),
    ("uf_prior_vol_20", "ts_mean(ts_delay(volume, 1), 20)", "prior_vol20", 21),
]

# 判定一致率（口径决定 §1.7 第 2 条）
JUDGMENTS = [
    # 名称, 系统侧表达式列, 研究侧表达式列, 说明
    ("close_gt_prior_high_20", ("close", "sys_uf_prior_high_20", ">"),
     ("close", "prior_high20", ">"), "close > 此前20日最高价"),
    ("close_gt_prior_high_55", ("close", "sys_uf_prior_high_55", ">"),
     ("close", "prior_high55", ">"), "close > 此前55日最高价"),
    ("close_lt_prior_low_10", ("close", "sys_uf_prior_low_10", "<"),
     ("close", "prior_low10", "<"), "close < 此前10日最低价"),
    ("volume_gt_1p5_prior_vol_20", ("volume", "sys_uf_prior_vol_20", ">1.5x"),
     ("volume", "prior_vol20", ">1.5x"), "volume > 1.5 × 此前20日均量"),
    ("close_gt_ma200", ("close", "sys_uf_ma200", ">"),
     ("close", "ma200", ">"), "close > 200日均价（状态比较）"),
]


def _cmp(a: pl.Series, b: pl.Series, op: str) -> pl.Series:
    if op == ">1.5x":
        return a > (b * 1.5)
    if op == ">":
        return a > b
    if op == "<":
        return a < b
    raise AssertionError(op)


def compare_series(df: pl.DataFrame, sys_col: str, res_col: str) -> dict:
    """逐位比较两列（df 已限定在评估窗口内，行序一致）。"""
    s = df[sys_col]
    r = df[res_col]
    both = s.is_not_null() & r.is_not_null()
    diff = (s - r).abs()
    over_tol = (diff > TOL).fill_null(False)
    sys_only = s.is_not_null() & r.is_null()
    res_only = s.is_null() & r.is_not_null()
    n_both = int(both.sum())
    nonzero = (diff > 0).fill_null(False) & both
    n_nonzero = int(nonzero.sum())
    rel = (diff / r.abs()).filter(nonzero & (r.abs() > 0))
    samples = []
    if n_nonzero:
        picked = (
            df.select("symbol", "date")
            .with_columns(s.alias("sys"), r.alias("res"), diff.alias("abs_diff"))
            .filter(nonzero)
            .sort("abs_diff", descending=True)
            .head(5)
        )
        for row in picked.to_dicts():
            samples.append({
                "symbol": row["symbol"],
                "date": row["date"].isoformat(),
                "sys": row["sys"],
                "res": row["res"],
                "abs_diff": row["abs_diff"],
            })
    return {
        "n_both_nonnull": n_both,
        "n_sys_nonnull": int(s.is_not_null().sum()),
        "n_res_nonnull": int(r.is_not_null().sum()),
        "n_null_mismatch": int(sys_only.sum()) + int(res_only.sum()),
        "n_sys_only_nonnull": int(sys_only.sum()),
        "n_res_only_nonnull": int(res_only.sum()),
        "max_abs_diff": float(diff.max()) if n_both else None,
        "mean_abs_diff": float(diff.mean()) if n_both else None,
        "p95_abs_diff": float(diff.quantile(0.95, "nearest")) if n_both else None,
        "n_nonzero_diff": n_nonzero,
        "n_over_tol": int(over_tol.sum()),
        "max_rel_diff_on_nonzero": float(rel.max()) if len(rel) else 0.0,
        "nonzero_samples": samples,
        "sys_mean": float(s.mean()) if n_both else None,
        "sys_p01": float(s.quantile(0.01, "nearest")) if n_both else None,
        "sys_p50": float(s.quantile(0.50, "nearest")) if n_both else None,
        "sys_p99": float(s.quantile(0.99, "nearest")) if n_both else None,
        "tol": TOL,
    }


def first_nonnull(df: pl.DataFrame, sys_col: str, res_col: str) -> dict:
    """每 symbol 首根非空位置（1-based，按 symbol 内交易日序号），系统 vs 研究。"""
    indexed = df.with_columns(pl.col("date").cum_count().over("symbol").alias("_bar_index"))
    per_symbol = indexed.group_by("symbol").agg(
        pl.when(pl.col(sys_col).is_not_null()).then(pl.col("_bar_index")).min().alias("sys_first"),
        pl.when(pl.col(res_col).is_not_null()).then(pl.col("_bar_index")).min().alias("res_first"),
    )
    known = per_symbol.filter(
        pl.col("sys_first").is_not_null() & pl.col("res_first").is_not_null()
    ).with_columns((pl.col("sys_first") - pl.col("res_first")).alias("delta"))
    mism = known.filter(pl.col("delta") != 0)
    samples = [
        {"symbol": row["symbol"], "sys_first_bar": int(row["sys_first"]), "res_first_bar": int(row["res_first"])}
        for row in mism.sort("symbol").head(5).to_dicts()
    ]
    return {
        "n_symbols_compared": int(known.height),
        "n_symbols_mismatch": int(mism.height),
        "max_bar_index_delta": int(known["delta"].abs().max()) if known.height else None,
        "mismatch_samples": samples,
        "panel_first_nonnull_date_sys": df.filter(pl.col(sys_col).is_not_null())["date"].min().isoformat()
        if df.filter(pl.col(sys_col).is_not_null()).height else None,
        "panel_first_nonnull_date_res": df.filter(pl.col(res_col).is_not_null())["date"].min().isoformat()
        if df.filter(pl.col(res_col).is_not_null()).height else None,
    }


def jaccard(a: pl.Series, b: pl.Series) -> dict:
    known = a.is_not_null() & b.is_not_null()
    a_f = a.fill_null(False) & known
    b_f = b.fill_null(False) & known
    both_true = int((a_f & b_f).sum())
    only_a = int((a_f & ~b_f).sum())
    only_b = int((~a_f & b_f).sum())
    n = int(known.sum())
    union = both_true + only_a + only_b
    return {
        "n": n,
        "both_true": both_true,
        "only_sys": only_a,
        "only_res": only_b,
        "both_false": n - union,
        "jaccard": (both_true / union) if union else None,
        "trigger_rate_sys": (both_true + only_a) / n if n else None,
        "trigger_rate_res": (both_true + only_b) / n if n else None,
    }


def main() -> int:
    t0 = time.time()
    out: dict = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "script": "docs/factors/evidence/scripts/f_class_parity.py",
            "repo": str(ROOT),
            "data_dir": str(settings.data_dir),
            "window": {"start": EVAL_START.isoformat(), "end": EVAL_END.isoformat()},
            "panel_window": {"start": common.WARMUP_START.isoformat(), "end": common.EVAL_END.isoformat()},
            "tolerance": TOL,
            "chunking": "none — 单次全帧；无抽样、无分块",
            "system_path": "app.factors.dsl.compile_formula(...).frame_transform(...)（与 app/strategy/scoring.py:391 生产物化同函数）",
            "research_path": "research/strategy-search-20261107/scripts/common.py → open_market/load_panel/add_indicators（只读 import）",
            "polars_version": pl.__version__,
            "python": sys.version.split()[0],
        }
    }
    try:
        out["meta"]["git_head"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True, check=True
        ).stdout.strip()
        out["meta"]["git_branch"] = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(ROOT), capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        out["meta"]["git_head"] = f"unavailable: {exc}"

    print("[1/5] load_panel ...", flush=True)
    market = common.open_market()
    frame = common.load_panel(market, common.WARMUP_START, common.EVAL_END)
    full_rows = frame.height
    full_symbols = frame["symbol"].n_unique()
    date_min = frame["date"].min()
    date_max = frame["date"].max()
    print(f"      full panel rows={full_rows:,} symbols={full_symbols} {date_min}..{date_max}", flush=True)

    print("[2/5] add_indicators (research side) ...", flush=True)
    research = common.add_indicators(frame)
    keep = [
        "symbol", "date", "close", "high", "low", "volume", "raw_close", "st_flag",
        "observed_bars", "prior_amount20",
    ] + [col for _, _, col, _ in FACTORS]
    df = research.select(keep)
    del research, frame

    print("[3/5] system DSL evaluation (8 formulas) ...", flush=True)
    for fid, formula, _res_col, expected in FACTORS:
        compiled = compile_formula(formula)
        if not compiled.ok:
            raise SystemExit(f"compile failed: {fid} {[e.to_dict() for e in compiled.errors]}")
        if compiled.warmup_bars != expected:
            raise SystemExit(f"warmup mismatch at compile: {fid} {compiled.warmup_bars} != {expected}")
        transformed = compiled.frame_transform(df)
        if transformed is None:
            raise SystemExit(f"frame_transform returned None (missing columns): {fid}")
        df = transformed.with_columns(transformed[FACTOR_COLUMN].alias(f"sys_{fid}")).drop(FACTOR_COLUMN)

    print("[4/5] window filter + row counts ...", flush=True)
    win = df.filter((pl.col("date") >= EVAL_START) & (pl.col("date") <= EVAL_END))
    in_universe = (
        (pl.col("observed_bars") >= common.UNIVERSE["min_observed_bars"])
        & (pl.col("st_flag").fill_null(False) == False)  # noqa: E712
        & (pl.col("raw_close") >= common.UNIVERSE["min_price_raw"])
        & (pl.col("prior_amount20") >= common.UNIVERSE["min_prior_amount20"])
        & (pl.col("volume") > 0)
    ).fill_null(False)
    win_rows = win.height
    univ_rows = int(win.with_columns(in_universe.alias("_u"))["_u"].sum())
    warmup_rows = int(df.filter(pl.col("date") < EVAL_START).height)
    out["row_counts"] = {
        "panel_rows_full": int(full_rows),
        "panel_symbols_full": int(full_symbols),
        "panel_date_min": date_min.isoformat(),
        "panel_date_max": date_max.isoformat(),
        "warmup_segment_rows": warmup_rows,
        "eval_window_rows": win_rows,
        "eval_window_symbols": int(win["symbol"].n_unique()),
        "eval_window_trading_days": int(win["date"].n_unique()),
        "eval_window_in_universe_rows": univ_rows,
        "eval_window_in_universe_share": univ_rows / win_rows if win_rows else None,
        "check_full_minus_warmup": int(full_rows) - warmup_rows,
    }

    print("[5/5] per-factor parity + jaccard ...", flush=True)
    definitions = {str(d.get("id")): d for d in factor_store.load_all(Path(settings.data_dir))}
    parity: dict = {}
    for fid, formula, res_col, expected in FACTORS:
        cmp = compare_series(win, f"sys_{fid}", res_col)
        fnp = first_nonnull(df, f"sys_{fid}", res_col)
        registered = None
        definition = definitions.get(fid)
        if definition is not None:
            try:
                registered = factor_store.to_spec(definition).warmup_bars
            except ValueError as exc:
                registered = f"to_spec failed: {exc}"
        parity[fid] = {
            "formula": formula,
            "research_column": res_col,
            "warmup_expected": expected,
            "warmup_registered": registered,
            "warmup_match": registered == expected,
            **cmp,
            **fnp,
        }
        print(
            f"      {fid}: n={cmp['n_both_nonnull']:,} max_abs_diff={cmp['max_abs_diff']} "
            f"over_tol={cmp['n_over_tol']} null_mismatch={cmp['n_null_mismatch']} "
            f"first_bar_mismatch_symbols={fnp['n_symbols_mismatch']}",
            flush=True,
        )
    out["factor_parity"] = parity

    judgments: dict = {}
    for name, (lcol, rcol, op), (lcol_r, rcol_r, op_r), desc in JUDGMENTS:
        sys_bool = _cmp(win[lcol], win[rcol], op)
        res_bool = _cmp(win[lcol_r], win[rcol_r], op_r)
        judgments[name] = {"description": desc, **jaccard(sys_bool, res_bool)}
        j = judgments[name]
        print(f"      jaccard {name}: {j['jaccard']} n={j['n']:,} only_sys={j['only_sys']} only_res={j['only_res']}", flush=True)
    out["judgment_jaccard"] = judgments

    # 数据规模口径差异：任务书 n=6,422,875 行 vs caliber §1.2 5,470,011~5,510,001
    out["row_count_note"] = {
        "task_brief_rows": 6422875,
        "task_brief_symbols": 3384,
        "caliber_section_1_2_rows": [5470011, 5510001],
        "measured": {
            "panel_rows_full": int(full_rows),
            "panel_symbols_full": int(full_symbols),
            "eval_window_rows": win_rows,
            "eval_window_symbols": int(win["symbol"].n_unique()),
            "eval_window_in_universe_rows": univ_rows,
            "warmup_segment_rows": warmup_rows,
        },
        "explanation": (
            "两者是同一工作帧的不同口径：6,422,875 是含预热段（2018-01-08~2019-06-28）的全帧行数，"
            "5,510,001 是评估窗口（2019-07-01~2026-10-30）行数，两者之差即预热段行数；"
            "5,470,011 等中间值是各因子两侧均非空的有效对比行数（预热使早期行在长窗口因子上为空）。"
            "本报告实测值见 measured。"
        ),
    }

    out["meta"]["elapsed_seconds"] = round(time.time() - t0, 1)
    out_path = ROOT / "docs" / "factors" / "evidence" / "F_CLASS_PARITY_20261107.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"written: {out_path} ({out_path.stat().st_size:,} bytes, {out['meta']['elapsed_seconds']}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
