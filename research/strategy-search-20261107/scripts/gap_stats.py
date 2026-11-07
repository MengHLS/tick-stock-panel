"""执行成本分解：统计每个策略入场信号次日的开盘跳空。

信号在收盘产生、次日开盘成交，跳空是这类口径的隐性成本。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import polars as pl

import common  # noqa: E402

m = common.open_market()
panel = common.load_panel(m)
prepared = common.build_signals(common.add_universe(common.add_indicators(panel)))

# 原始价口径的次日跳空：(下一交易日 open × 复权还原) / 当日 raw_close - 1
f = panel.sort(["symbol", "date"]).with_columns(
    pl.col("date").shift(-1).over("symbol").alias("next_date"),
    (pl.col("open") * pl.col("raw_close") / pl.col("close")).shift(-1).over("symbol")
    .alias("next_raw_open"),
    pl.col("raw_close").alias("cur_raw_close"),
)
f = f.with_columns((pl.col("next_raw_open") / pl.col("cur_raw_close") - 1).alias("next_gap"))

out = {}
for strat in common.STRATEGIES:
    sig = prepared.filter(pl.col(strat.entry) & (pl.col("date") >= common.EVAL_START)).select(
        "symbol", "date")
    joined = sig.join(f.select("symbol", "date", "next_gap"), on=["symbol", "date"], how="left")
    gaps = joined["next_gap"].drop_nulls().to_numpy()
    gaps = gaps[np.abs(gaps) < 0.25]
    out[strat.key] = {
        "signals": int(len(joined)), "with_next_bar": int(len(gaps)),
        "mean_gap": float(gaps.mean()) if len(gaps) else None,
        "median_gap": float(np.median(gaps)) if len(gaps) else None,
        "share_gap_gt_1pct": float((gaps > 0.01).mean()) if len(gaps) else None,
        "share_gap_lt_minus1pct": float((gaps < -0.01).mean()) if len(gaps) else None,
    }
    print(strat.key, out[strat.key], flush=True)

common.save_json(Path(__file__).resolve().parents[1] / "results" / "entry_gaps.json", out)
