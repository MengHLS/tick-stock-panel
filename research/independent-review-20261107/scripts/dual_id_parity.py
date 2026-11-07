# -*- coding: utf-8 -*-
"""Q2 附：同口径双 id 的数值是否一致（审核方自写，只读数据）。

对比对象：
  A 侧 = 契约 §7.1 / 盘上 uf_*.json 的公式文本（已过 F-A3）
  B 侧 = app/custom/research_factor_pack/factor_specs.py 里注册成活因子的公式文本
逐帧用同一个 compile_formula(...).frame_transform 求值，比较 max_abs_diff 与空值位形。

注意：两套公式文本对 6 只并不相同（prior_* 是 ts_delay(ts_max(...)) vs
ts_max(ts_delay(...))；vol60 是 (x-x1)/x1 vs x/x1-1），因此必须逐位比，不能靠"文本不同但等价"推断。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "research" / "strategy-search-20261107" / "scripts"))

import polars as pl  # noqa: E402

from app.factors.dsl import FACTOR_COLUMN, compile_formula  # noqa: E402

TOL = 1e-12
N_SYMBOLS = 20
N_DAYS = 250

PAIRS = [
    ("uf_ma120", "ts_mean(close, 120)", "ma120", "ts_mean(close, 120)"),
    ("uf_ma200", "ts_mean(close, 200)", "ma200", "ts_mean(close, 200)"),
    ("uf_vol60", "ts_std(close / ts_delay(close, 1) - 1, 60)", "vol60",
     "ts_std((close - ts_delay(close, 1)) / ts_delay(close, 1), 60)"),
    ("uf_prior_high_20", "ts_max(ts_delay(high, 1), 20)", "prior_high_20",
     "ts_delay(ts_max(high, 20), 1)"),
    ("uf_prior_high_55", "ts_max(ts_delay(high, 1), 55)", "prior_high_55",
     "ts_delay(ts_max(high, 55), 1)"),
    ("uf_prior_high_250", "ts_max(ts_delay(high, 1), 250)", "prior_high_250",
     "ts_delay(ts_max(high, 250), 1)"),
    ("uf_prior_low_10", "ts_min(ts_delay(low, 1), 10)", "prior_low_10",
     "ts_delay(ts_min(low, 10), 1)"),
    ("uf_prior_vol_20", "ts_mean(ts_delay(volume, 1), 20)", "prior_vol_20",
     "ts_delay(ts_mean(volume, 20), 1)"),
]


def main() -> int:
    import common  # research/strategy-search-20261107/scripts/common.py

    t0 = time.time()
    market = common.open_market()
    frame = common.load_panel(market).sort(["symbol", "date"])
    days = frame["date"].unique().sort().tail(N_DAYS).to_list()
    symbols = sorted(frame["symbol"].unique().to_list())
    step = max(1, len(symbols) // N_SYMBOLS)
    sample = symbols[::step][:N_SYMBOLS]
    sub = frame.filter(pl.col("symbol").is_in(sample) & pl.col("date").is_in(days))
    print(f"PANEL|rows_full={frame.height}|slice_rows={sub.height}|symbols={len(sample)}|days={len(days)}")

    for uf_id, uf_formula, pack_id, pack_formula in PAIRS:
        ca, cb = compile_formula(uf_formula), compile_formula(pack_formula)
        if not ca.ok or not cb.ok:
            print(f"PAIR|{uf_id}|{pack_id}|COMPILE_FAIL|a={ca.errors}|b={cb.errors}")
            continue
        fa, fb = ca.frame_transform(sub), cb.frame_transform(sub)
        a, b = fa[FACTOR_COLUMN].alias("a"), fb[FACTOR_COLUMN].alias("b")
        joined = pl.DataFrame({"a": a, "b": b})
        d = (pl.col("a") - pl.col("b")).abs()
        row = joined.select(
            n_both=(pl.col("a").is_not_null() & pl.col("b").is_not_null()).sum(),
            max_diff=d.max(),
            n_over=(d > TOL).sum(),
            n_null_mismatch=(pl.col("a").is_null() != pl.col("b").is_null()).sum(),
            n_nonnull_a=pl.col("a").is_not_null().sum(),
            n_nonnull_b=pl.col("b").is_not_null().sum(),
        ).row(0)
        first_a = fa.filter(pl.col(FACTOR_COLUMN).is_not_null())["date"].min()
        first_b = fb.filter(pl.col(FACTOR_COLUMN).is_not_null())["date"].min()
        print(f"PAIR|{uf_id}|{pack_id}|text_same={uf_formula == pack_formula}"
              f"|max_abs_diff={row[1]}|n_over_tol={row[2]}|n_null_mismatch={row[3]}"
              f"|n_a={row[4]}|n_b={row[5]}|first_a={first_a}|first_b={first_b}")
    print(f"ELAPSED={time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
