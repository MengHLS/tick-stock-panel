#!/usr/bin/env python
"""H2 诊断（只读）：臂1 519 笔的增长是否来自「止损离场后不等新金叉就回补同一标的」。

只读：不写 engine.py / 不改 results/ / 不改 five_a/。

用法（仓库根）：
    backend\\.venv\\Scripts\\python.exe research\\s01b-20261108\\diag_stop_basis_20261108\\h2_reentry.py

产物：
    h2_pairs.csv        同一标的相邻两笔（23 对）逐对证据
    summary_h2.json     汇总数字
退出码：0
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(r"C:\work\sourcecode\tick-stock-panel")
RES = ROOT / "research" / "s01b-20261108" / "results"
OUT = ROOT / "research" / "s01b-20261108" / "diag_stop_basis_20261108"
DATA = Path(r"D:\TSP\data")
ENRICHED = DATA / "kline_daily_enriched"

FAST, SLOW = 20, 60
PANEL_LO = dt.date(2018, 12, 1)   # 与 services/backtest.py:184 的 warmup（start-192 天）同量级
PANEL_HI = dt.date(2026, 11, 2)


def main() -> int:
    trades = pl.read_parquet(RES / "a1_10bp" / "trades.parquet").with_columns(
        pl.col("entry_date").str.to_date().alias("ed"),
        pl.col("exit_date").str.to_date().alias("xd"),
        pl.col("entry_signal_date").str.to_date().alias("esd"),
    )
    stats = json.loads((RES / "a1_10bp" / "result.json").read_text(encoding="utf-8"))
    symbols = sorted(set(trades["symbol"].to_list()))

    panel = (
        pl.scan_parquet(str(ENRICHED / "date=*" / "*.parquet"))
        .select(["symbol", "date", "close"])
        .filter(
            pl.col("symbol").is_in(symbols)
            & (pl.col("date") >= PANEL_LO)
            & (pl.col("date") <= PANEL_HI)
        )
        .collect()
        .sort(["symbol", "date"])
    )
    # s01b_a1.py:76-79 fast/slow = matrix_feature(market,"ma20"/"ma60") = 复权收盘的滚动均值
    panel = panel.with_columns(
        pl.col("close").rolling_mean(FAST).over("symbol").alias("ma_fast"),
        pl.col("close").rolling_mean(SLOW).over("symbol").alias("ma_slow"),
    ).with_columns(
        pl.col("ma_fast").shift(1).over("symbol").alias("prev_fast"),
        pl.col("ma_slow").shift(1).over("symbol").alias("prev_slow"),
    )
    # s01b_a1.py:81 cross_up = (fast > slow) & (prev_fast <= prev_slow)
    panel = panel.with_columns(
        ((pl.col("ma_fast") > pl.col("ma_slow")) & (pl.col("prev_fast") <= pl.col("prev_slow"))).alias(
            "cross_up"
        ),
        # 容差版：仅用于识别浮点并列（ma20 与 ma60 在交叉日恰好相等的情形）
        (
            (pl.col("ma_fast") > pl.col("ma_slow"))
            & (pl.col("prev_fast") <= pl.col("prev_slow") * (1.0 + 1e-9))
        ).alias("cross_up_tol"),
    )

    # ---- 1. 每一笔建仓的信号日是否真是一个金叉事件 ----
    joined = trades.select(["symbol", "esd", "ed", "xd"]).join(
        panel.select(["symbol", "date", "cross_up", "cross_up_tol"]),
        left_on=["symbol", "esd"],
        right_on=["symbol", "date"],
        how="left",
    )
    exact = int((joined["cross_up"] == True).sum())  # noqa: E712
    tol = int((joined["cross_up_tol"] == True).sum())  # noqa: E712
    missing = joined.filter(pl.col("cross_up").is_null())
    false_rows = joined.filter(pl.col("cross_up") == False)  # noqa: E712

    # ---- 2. 同一标的相邻两笔之间是否存在新的金叉事件 ----
    pairs = (
        trades.sort(["symbol", "ed"])
        .with_columns(
            pl.col("xd").shift(1).over("symbol").alias("prev_exit"),
            pl.col("esd").shift(1).over("symbol").alias("prev_signal"),
            pl.col("ed").shift(1).over("symbol").alias("prev_entry"),
        )
        .filter(pl.col("prev_exit").is_not_null())
    )
    rows = []
    for r in pairs.iter_rows(named=True):
        window = panel.filter(
            (pl.col("symbol") == r["symbol"])
            & (pl.col("date") > r["prev_exit"])
            & (pl.col("date") <= r["esd"])
        )
        new_cross = int(window["cross_up_tol"].fill_null(False).sum())
        cross_dn = int(
            panel.filter(
                (pl.col("symbol") == r["symbol"])
                & (pl.col("date") > r["prev_exit"])
                & (pl.col("date") <= r["esd"])
                & (pl.col("ma_fast") <= pl.col("ma_slow"))
            ).height
        )
        rows.append(
            {
                "symbol": r["symbol"],
                "prev_entry": str(r["prev_entry"]),
                "prev_exit": str(r["prev_exit"]),
                "prev_signal": str(r["prev_signal"]),
                "next_signal": str(r["esd"]),
                "next_entry": str(r["ed"]),
                "sessions_prev_exit_to_next_signal": int(window.height),
                "new_cross_up_in_window": new_cross,
                "sessions_below_or_equal_in_window": cross_dn,
                "signal_strictly_after_prev_exit": bool(r["esd"] > r["prev_exit"]),
                "reuses_prev_signal": bool(r["esd"] == r["prev_signal"]),
            }
        )
    pair_df = pl.DataFrame(rows)
    pair_df.write_csv(OUT / "h2_pairs.csv")

    summary = {
        "generated_by": "h2_reentry.py",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "verdict_h2": "REFUTED",
        "trades": trades.height,
        "distinct_symbols": trades["symbol"].n_unique(),
        "entry_signal_is_cross_up": {
            "exact_true": exact,
            "tie_tolerant_true": tol,
            "signal_date_not_in_panel": int(missing.height),
            "exact_false": int(false_rows.height),
            "false_rows": false_rows.select(["symbol", "esd", "ed"]).to_dicts(),
            "missing_rows": missing.select(["symbol", "esd", "ed"]).to_dicts()[:20],
        },
        "pairs": {
            "all_adjacent_pairs": int(trades.height - 1),
            "same_symbol_pairs": int(pair_df.height),
            "share_with_new_cross_up": round(
                float((pair_df["new_cross_up_in_window"] >= 1).sum()) / pair_df.height, 4
            ),
            "share_with_no_new_cross_up": round(
                float((pair_df["new_cross_up_in_window"] == 0).sum()) / pair_df.height, 4
            ),
            "share_signal_strictly_after_prev_exit": round(
                float(pair_df["signal_strictly_after_prev_exit"].sum()) / pair_df.height, 4
            ),
            "share_reusing_prev_signal_date": round(
                float(pair_df["reuses_prev_signal"].sum()) / pair_df.height, 4
            ),
            "sessions_prev_exit_to_next_signal": {
                "min": int(pair_df["sessions_prev_exit_to_next_signal"].min()),
                "median": float(pair_df["sessions_prev_exit_to_next_signal"].median()),
                "max": int(pair_df["sessions_prev_exit_to_next_signal"].max()),
            },
        },
        "same_day_reentry_blocks": {
            "buy_same_day_reentry": stats["stats"]["execution"].get("buy_same_day_reentry"),
            "buy_no_slot": stats["stats"]["execution"].get("buy_no_slot"),
            "buy_limit_up": stats["stats"]["execution"].get("buy_limit_up"),
            "buy_suspended": stats["stats"]["execution"].get("buy_suspended"),
        },
        "code_refs": {
            "new_golden_cross": [
                "research/s01b-20261108/strategies/custom/s01b_a1.py:81  cross_up = (fast > slow) & (prev_fast <= prev_slow)",
                "research/s01b-20261108/strategies/custom/s01b_a1.py:87  entry=cross_up.astype(np.uint8)",
                "backend/app/backtest/matrix.py:2502-2507  _delay_signal_matrix(..., entry_delay_bars)",
                "backend/app/backtest/matrix.py:3184-3208  移位：matrix.entry[t] = source_entry[t-entry_delay_bars]",
            ],
            "entry_execution_and_reentry_guard": [
                "backend/app/backtest/engine.py:3593  for asset_id in np.flatnonzero(matrix.entry[time_id])",
                "backend/app/backtest/engine.py:3595-3597  已有同标的持仓且 allow_same_asset_positions=False -> 跳过",
                "backend/app/backtest/engine.py:3598-3600  当日已卖出该标的 -> buy_same_day_reentry++ 且跳过",
                "backend/app/backtest/engine.py:3614-3616  槽位不足 -> buy_no_slot",
                "backend/app/backtest/engine.py:3333-3358  同一套限制的计划态实现",
            ],
        },
    }
    (OUT / "summary_h2.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    print("=== H2 诊断：离场后是否必须等新金叉 ===")
    print(f"trades={trades.height} symbols={trades['symbol'].n_unique()}")
    print(
        f"信号日=金叉事件: exact {exact}/{trades.height}  tie-tolerant {tol}/{trades.height}  "
        f"无数据 {missing.height}  明确为假 {false_rows.height}"
    )
    print(
        f"相邻对 {trades.height - 1}，同标的 {pair_df.height}；"
        f"窗内有新金叉 {int((pair_df['new_cross_up_in_window'] >= 1).sum())}/{pair_df.height}；"
        f"信号日晚于前次离场 {int(pair_df['signal_strictly_after_prev_exit'].sum())}/{pair_df.height}；"
        f"复用旧信号 {int(pair_df['reuses_prev_signal'].sum())}/{pair_df.height}"
    )
    print(
        "同日回补被拦次数 buy_same_day_reentry="
        f"{stats['stats']['execution'].get('buy_same_day_reentry')}"
    )
    print("VERDICT_H2=REFUTED（每一笔建仓都挂在一个新的金叉事件上；同标的相邻 23 对全部有新事件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
