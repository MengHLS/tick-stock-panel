#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""F 类八只因子 —— 独立审核方的自有对账脚本（不调用被审方的 f_class_parity.py）。

目的：独立审核（F-A3）不复用被审脚本，自写一份最小实现：
  1) 研究侧：只 import research/strategy-search-20261107/scripts/common.py 的
     open_market / load_panel / add_indicators（不改其文件）。
  2) 系统侧：app.factors.dsl.compile_formula(契约 §7.1 原文).frame_transform(同一帧)。
  3) 并按契约 F-A3 的字面度量（8 只 × 20 symbol × 近 250 交易日）单独切片复核，
     同时给出全评估窗口的数字作为上界参考。
  4) 额外给 vol60 的分位数分布，用于 F-A6 量级判定的独立依据。

只读 D:\\TSP\\data；不写缓存、不写任何被审文件。

运行：
  cd <repo> && backend/.venv/Scripts/python.exe \
      research/independent-review-20261107/scripts/independent_f_class_check.py <out.json>
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "research" / "strategy-search-20261107" / "scripts"))

import common  # noqa: E402  （研究侧工作帧，只 import）

from app.factors.dsl import FACTOR_COLUMN, compile_formula  # noqa: E402

EVAL_START = date(2019, 7, 1)
EVAL_END = date(2026, 10, 30)
TOL = 1e-12
N_SYMBOLS = 20
N_DAYS = 250

# (uf_ id, 契约 §7.1 原文, 研究列名, 契约 warmup)
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


def main(out_path: Path) -> int:
    t0 = time.time()
    market = common.open_market()
    frame = common.load_panel(market)
    frame = frame.sort(["symbol", "date"])
    ind = common.add_indicators(frame)

    eval_frame = ind.filter(
        (pl.col("date") >= pl.lit(EVAL_START)) & (pl.col("date") <= pl.lit(EVAL_END))
    )
    days = eval_frame["date"].unique().sort()
    last_days = days.tail(N_DAYS).to_list()
    symbols = sorted(eval_frame["symbol"].unique().to_list())
    step = max(1, len(symbols) // N_SYMBOLS)
    sample_symbols = symbols[::step][:N_SYMBOLS]
    sample = eval_frame.filter(
        pl.col("symbol").is_in(sample_symbols) & pl.col("date").is_in(last_days)
    )

    result: dict = {
        "panel": {
            "rows_full": frame.height,
            "symbols_full": frame["symbol"].n_unique(),
            "date_min": str(frame["date"].min()),
            "date_max": str(frame["date"].max()),
            "rows_eval": eval_frame.height,
            "symbols_eval": eval_frame["symbol"].n_unique(),
            "trading_days_eval": len(days),
        },
        "sample_slice": {
            "n_symbols": len(sample_symbols),
            "symbols": sample_symbols,
            "n_days": len(last_days),
            "day_min": str(min(last_days)),
            "day_max": str(max(last_days)),
            "rows": sample.height,
        },
        "factors": {},
    }

    for fid, formula, col, warmup in FACTORS:
        compiled = compile_formula(formula)
        if not compiled.ok or compiled.frame_transform is None:
            result["factors"][fid] = {"error": "compile_failed", "ok": False}
            continue
        # 必须整帧变换（含预热段）后再切评估窗口，否则每只 symbol 的首 N 根会被人为置空
        full = compiled.frame_transform(ind).filter(
            (pl.col("date") >= pl.lit(EVAL_START)) & (pl.col("date") <= pl.lit(EVAL_END))
        )
        diff = (pl.col(FACTOR_COLUMN) - pl.col(col)).abs()
        null_mismatch = (pl.col(FACTOR_COLUMN).is_null() != pl.col(col).is_null()).sum()
        agg = full.select(
            n_both_nonnull=(
                pl.col(FACTOR_COLUMN).is_not_null() & pl.col(col).is_not_null()
            ).sum(),
            max_abs_diff=diff.max(),
            n_over_tol=(diff > TOL).sum(),
            n_null_mismatch=null_mismatch,
        ).row(0)

        sm = compiled.frame_transform(ind).filter(
            pl.col("symbol").is_in(sample_symbols) & pl.col("date").is_in(last_days)
        )
        sdiff = (pl.col(FACTOR_COLUMN) - pl.col(col)).abs()
        sagg = sm.select(
            n=((pl.col(FACTOR_COLUMN).is_not_null() & pl.col(col).is_not_null())).sum(),
            max_abs_diff=sdiff.max(),
            n_over_tol=(sdiff > TOL).sum(),
            n_null_mismatch=(
                pl.col(FACTOR_COLUMN).is_null() != pl.col(col).is_null()
            ).sum(),
        ).row(0)
        result["factors"][fid] = {
            "formula": formula,
            "warmup_compiled": compiled.warmup_bars,
            "warmup_contract": warmup,
            "warmup_match": compiled.warmup_bars == warmup,
            "dependencies": sorted(compiled.dependencies),
            "eval_full": {
                "n_both_nonnull": int(agg[0]),
                "max_abs_diff": float(agg[1]) if agg[1] is not None else None,
                "n_over_tol": int(agg[2]),
                "n_null_mismatch": int(agg[3]),
            },
            "sample_20x250": {
                "n_both_nonnull": int(sagg[0]),
                "max_abs_diff": float(sagg[1]) if sagg[1] is not None else None,
                "n_over_tol": int(sagg[2]),
                "n_null_mismatch": int(sagg[3]),
            },
        }

    # F-A6：vol60 分布（评估窗口，独立复算）
    v = eval_frame["vol60"].drop_nulls()
    qs = [0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
    quantiles = {f"p{int(q * 100):02d}": float(v.quantile(q)) for q in qs}
    outside = ((v < 0.015) | (v > 0.06)).sum()
    result["vol60_distribution"] = {
        "n": int(v.len()),
        "mean": float(v.mean()),
        "min": float(v.min()),
        "max": float(v.max()),
        **quantiles,
        "share_outside_0_015_0_06": float(outside) / float(v.len()),
        "n_outside": int(outside),
    }
    result["elapsed_seconds"] = round(time.time() - t0, 2)
    result["polars_version"] = pl.__version__

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "factors"}, ensure_ascii=False))
    for fid, r in result["factors"].items():
        if "error" in r:
            print(fid, r)
            continue
        print(
            f"{fid:20s} warmup={r['warmup_compiled']}(exp {r['warmup_contract']}) "
            f"deps={r['dependencies']} full: max={r['eval_full']['max_abs_diff']} "
            f"over={r['eval_full']['n_over_tol']} nullmis={r['eval_full']['n_null_mismatch']} | "
            f"20x250: n={r['sample_20x250']['n_both_nonnull']} max={r['sample_20x250']['max_abs_diff']} "
            f"over={r['sample_20x250']['n_over_tol']}"
        )
    return 0


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/independent_f_class.json")
    raise SystemExit(main(out))
