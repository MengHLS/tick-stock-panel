#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""F 类 6 对因子 V3 补充对账：20 symbol x 近 250 交易日逐值 + 末交易日截面名次漂移。

依据：契约 §7.6 F-A3（20 symbol x 近 250 交易日，max_abs_diff < 1e-12）；
     裁定 ARCH_DECISION_FACTOR_ID_CANONICAL_20261107（canonical = uf_*）。
只读：研究侧 common.add_indicators（只 import）；系统侧 compile_formula().frame_transform()。
输出：docs/factors/evidence/F_CLASS_RANK_PARITY_20261107.json
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "research" / "strategy-search-20261107" / "scripts"))

import common  # noqa: E402
from app.config import settings  # noqa: E402
from app.factors.dsl import FACTOR_COLUMN, compile_formula  # noqa: E402

TOL = 1e-12
DAYS = 250
N_SYMBOLS = 20

PAIRS = [
    ("vol60", "uf_vol60", "ts_std(close / ts_delay(close, 1) - 1, 60)", "vol60"),
    ("prior_high_20", "uf_prior_high_20", "ts_max(ts_delay(high, 1), 20)", "prior_high20"),
    ("prior_high_55", "uf_prior_high_55", "ts_max(ts_delay(high, 1), 55)", "prior_high55"),
    ("prior_high_250", "uf_prior_high_250", "ts_max(ts_delay(high, 1), 250)", "prior_high250"),
    ("prior_low_10", "uf_prior_low_10", "ts_min(ts_delay(low, 1), 10)", "prior_low10"),
    ("prior_vol_20", "uf_prior_vol_20", "ts_mean(ts_delay(volume, 1), 20)", "prior_vol20"),
    # 补齐 F-A3 的 8 只（本轮重点是被策略直接使用的 6 对，这两只一并跑，避免「8 只」口径留缺口）
    ("ma120", "uf_ma120", "ts_mean(close, 120)", "ma120"),
    ("ma200", "uf_ma200", "ts_mean(close, 200)", "ma200"),
]


def pick_symbols(univ_last, n):
    syms = sorted(univ_last["symbol"].to_list())
    if len(syms) <= n:
        return syms
    step = (len(syms) - 1) / (n - 1)
    return [syms[int(round(i * step))] for i in range(n)]


def rank_block(df, sys_col, res_col):
    sub = df.filter(pl.col(sys_col).is_not_null() & pl.col(res_col).is_not_null())
    n = sub.height
    if n == 0:
        return {"n": 0, "rank_change_max": None, "n_swapped": 0}
    sub = sub.with_columns(
        pl.col(sys_col).rank(method="average").alias("_rk_s"),
        pl.col(res_col).rank(method="average").alias("_rk_r"),
    ).with_columns((pl.col("_rk_s") - pl.col("_rk_r")).abs().alias("_d"))
    d = sub["_d"]
    nt_s = int(sub["_rk_s"].n_unique())
    nt_r = int(sub["_rk_r"].n_unique())
    worst = sub.filter(pl.col("_d") > 0).sort("_d", descending=True).head(3)
    return {
        "n": n,
        "rank_change_max": float(d.max()),
        "n_swapped": int((d > 0).sum()),
        "n_distinct_rank_sys": nt_s,
        "n_distinct_rank_res": nt_r,
        "tie_structure_changed": nt_s != nt_r,
        "worst_swaps": [
            {
                "symbol": r["symbol"],
                "date": r["date"].isoformat() if hasattr(r["date"], "isoformat") else str(r["date"]),
                "sys": r[sys_col],
                "res": r[res_col],
                "rank_sys": r["_rk_s"],
                "rank_res": r["_rk_r"],
                "rank_diff": r["_d"],
            }
            for r in worst.to_dicts()
        ],
    }


def main():
    t0 = time.time()
    out = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "script": "docs/factors/evidence/scripts/f_class_rank_parity.py",
            "repo": str(ROOT),
            "data_dir": str(settings.data_dir),
            "contract_basis": "FACTOR_ENGINE_CONTRACTS_20261107.md 7.6 F-A3",
            "tolerance": TOL,
            "sampling": {
                "days": DAYS,
                "symbols": N_SYMBOLS,
                "window_rule": "panel last 250 trading days (inclusive)",
                "symbol_rule": "in_universe symbols on last trading day, sorted asc, evenly spaced -> 20 (deterministic)",
            },
            "rank_rule": "average rank, ascending; each side ranked independently then compared",
            "system_path": "app.factors.dsl.compile_formula(...).frame_transform(...)",
            "research_path": "research/strategy-search-20261107/scripts/common.py add_indicators (read-only import)",
            "polars_version": pl.__version__,
            "python": sys.version.split()[0],
        }
    }
    try:
        out["meta"]["git_head"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        out["meta"]["git_head"] = "unavailable: %s" % exc

    print("[1/5] load panel", flush=True)
    market = common.open_market()
    frame = common.load_panel(market, common.WARMUP_START, common.EVAL_END)
    print("      rows=%s symbols=%s %s..%s" % (frame.height, frame["symbol"].n_unique(), frame["date"].min(), frame["date"].max()), flush=True)

    print("[2/5] add_indicators", flush=True)
    research = common.add_indicators(frame)
    keep = ["symbol", "date", "close", "high", "low", "volume", "raw_close", "st_flag", "observed_bars", "prior_amount20"] + [p[3] for p in PAIRS]
    df = research.select(keep)
    del research, frame

    print("[3/5] system DSL", flush=True)
    for _res, fid, formula, _col in PAIRS:
        compiled = compile_formula(formula)
        if not compiled.ok:
            raise SystemExit("compile failed: %s %s" % (fid, [e.to_dict() for e in compiled.errors]))
        transformed = compiled.frame_transform(df)
        if transformed is None:
            raise SystemExit("frame_transform None: %s" % fid)
        df = transformed.with_columns(transformed[FACTOR_COLUMN].alias("sys_" + fid)).drop(FACTOR_COLUMN)

    dates = df["date"].unique().sort()
    win_dates = dates.tail(DAYS).to_list() if len(dates) > DAYS else dates.to_list()
    first_date, last_date = win_dates[0], win_dates[-1]
    print("      window %s..%s  days=%d" % (first_date, last_date, len(win_dates)), flush=True)

    univ = (
        (pl.col("observed_bars") >= common.UNIVERSE["min_observed_bars"])
        & (pl.col("st_flag").fill_null(False) == False)  # noqa: E712
        & (pl.col("raw_close") >= common.UNIVERSE["min_price_raw"])
        & (pl.col("prior_amount20") >= common.UNIVERSE["min_prior_amount20"])
        & (pl.col("volume") > 0)
    ).fill_null(False)
    df = df.with_columns(univ.alias("_univ"))

    win = df.filter((pl.col("date") >= first_date) & (pl.col("date") <= last_date))
    univ_last = win.filter((pl.col("date") == last_date) & pl.col("_univ"))
    syms = pick_symbols(univ_last, N_SYMBOLS)
    print("      in_universe on last date=%d ; 20 picked: %s" % (univ_last.height, ",".join(syms)), flush=True)
    sample = win.filter(pl.col("symbol").is_in(syms))

    out["sample"] = {
        "window_start": first_date.isoformat(),
        "window_end": last_date.isoformat(),
        "n_trading_days": len(win_dates),
        "symbols": syms,
        "n_symbols": len(syms),
        "universe_size_on_last_date": univ_last.height,
        "n_rows_sample": sample.height,
    }

    print("[4/5] per-pair parity + rank", flush=True)
    pairs = {}
    for res_name, fid, formula, res_col in PAIRS:
        sys_col = "sys_" + fid
        s, r = sample[sys_col], sample[res_col]
        both = s.is_not_null() & r.is_not_null()
        d = (s - r).abs().filter(both)
        n_both = int(both.sum())
        max_abs = float(d.max()) if n_both else None
        last_all = rank_block(win.filter(pl.col("date") == last_date), sys_col, res_col)
        last_univ = rank_block(win.filter((pl.col("date") == last_date) & pl.col("_univ")), sys_col, res_col)
        last_sample = rank_block(sample.filter(pl.col("date") == last_date), sys_col, res_col)
        w = win.filter(pl.col(sys_col).is_not_null() & pl.col(res_col).is_not_null()).with_columns(
            pl.col(sys_col).rank(method="average").over("date").alias("_rk_s"),
            pl.col(res_col).rank(method="average").over("date").alias("_rk_r"),
        ).with_columns((pl.col("_rk_s") - pl.col("_rk_r")).abs().alias("_d"))
        per_day = w.group_by("date").agg(
            pl.col("_d").max().alias("mx"),
            (pl.col("_d") > 0).sum().alias("sw"),
        )
        pairs[res_name] = {
            "pair": "%s <-> %s" % (res_name, fid),
            "research_name": res_name,
            "canonical_id": fid,
            "research_column": res_col,
            "formula": formula,
            "value_parity_sample": {
                "n": n_both,
                "max_abs_diff": max_abs,
                "mean_abs_diff": float(d.mean()) if n_both else None,
                "n_nonzero": int((d > 0).sum()),
                "pass_1e12": (max_abs is not None and max_abs < TOL),
            },
            "rank_last_day_full_market": last_all,
            "rank_last_day_in_universe": last_univ,
            "rank_last_day_20_symbols": last_sample,
            "rank_over_window": {
                "days": per_day.height,
                "rank_change_max_over_window": float(per_day["mx"].max()) if per_day.height else None,
                "n_days_with_any_swap": int((per_day["sw"] > 0).sum()),
                "n_days_total_swaps": int((per_day["sw"]).sum()),
            },
        }
        v = pairs[res_name]["value_parity_sample"]
        print("      %-16s n=%d max_abs_diff=%r pass=%s | rank_max(full)=%s swapped=%s | window_max=%s days_with_swap=%s"
              % (res_name, v["n"], v["max_abs_diff"], v["pass_1e12"],
                 last_all["rank_change_max"], last_all["n_swapped"],
                 pairs[res_name]["rank_over_window"]["rank_change_max_over_window"],
                 pairs[res_name]["rank_over_window"]["n_days_with_any_swap"]), flush=True)
    out["pairs"] = pairs

    out["meta"]["elapsed_seconds"] = round(time.time() - t0, 1)
    path = ROOT / "docs" / "factors" / "evidence" / "F_CLASS_RANK_PARITY_20261107.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("written: %s (%s bytes, %ss)" % (path, path.stat().st_size, out["meta"]["elapsed_seconds"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
