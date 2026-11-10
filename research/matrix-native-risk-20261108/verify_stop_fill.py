"""从 trades_sl_2y.parquet 反查止损成交价口径。

判据:
  1) exit_price 是否 == entry_price*(1-0.08)（止损线价），误差仅为 4 位小数舍入；
  2) 是否存在「优于止损线」的成交（若存在, 说明不是按线价/开盘价成交）；
  3) 跳空低于止损线的成交是否更差（open 成交）；
  4) exit_date 与 exit_signal_date 是否同日。

用法: backend\\.venv\\Scripts\\python.exe research\\matrix-native-risk-20261108\\verify_stop_fill.py
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
TOL = 2e-5  # 4 位小数舍入的容差


def main() -> int:
    trades = pl.read_parquet(HERE / "trades_sl_2y.parquet")
    sl = trades.filter(pl.col("exit_reason") == "stop_loss").with_columns(
        (pl.col("entry_price") * 0.92).alias("stop_line"),
        (pl.col("exit_price") / (pl.col("entry_price") * 0.92) - 1).alias("rel_vs_line"),
        (pl.col("exit_date").cast(pl.Utf8) == pl.col("exit_signal_date").cast(pl.Utf8)).alias("same_day"),
    )
    exact = sl.filter(pl.col("rel_vs_line").abs() <= TOL)
    below = sl.filter(pl.col("rel_vs_line") < -TOL)
    above = sl.filter(pl.col("rel_vs_line") > TOL)

    out = {
        "n_stop_loss": sl.height,
        "at_stop_line_count": exact.height,
        "below_stop_line_count": below.height,
        "above_stop_line_count": above.height,
        "rel_min": round(float(sl["rel_vs_line"].min()), 6),
        "rel_max": round(float(sl["rel_vs_line"].max()), 6),
        "below_pnl_min": round(float(below["pnl_pct"].min()), 6) if below.height else None,
        "below_pnl_mean": round(float(below["pnl_pct"].mean()), 6) if below.height else None,
        "same_day_exit_count": int(sl["same_day"].sum()),
        "not_same_day": sl.filter(~pl.col("same_day"))
        .select("symbol", "entry_date", "exit_signal_date", "exit_date", "duration", "exit_price", "pnl_pct")
        .to_dicts(),
        "at_line_sample": exact.select(
            "symbol", "entry_date", "exit_date", "entry_price", "stop_line", "exit_price", "pnl_pct", "duration"
        ).head(5).to_dicts(),
        "below_line_sample": below.select(
            "symbol", "entry_date", "exit_date", "entry_price", "stop_line", "exit_price", "rel_vs_line", "pnl_pct"
        ).head(5).to_dicts(),
    }
    (HERE / "stop_fill_check.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
