#!/usr/bin/env python
"""只读核查：S01b 基准（a0_10bp，199 笔）到底有没有「10% 止损」。

只读：不改 engine / strategy / results / 生产文件；不重跑回测。
产物全部落在本目录。

用法（仓库根）：
    backend\\.venv\\Scripts\\python.exe research\\s01b-20261108\\_exploration\\stop-loss-check-20261109\\stop_loss_check.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(r"C:\work\sourcecode\tick-stock-panel")
RES = ROOT / "research" / "s01b-20261108" / "_exploration" / "results"
OUT = ROOT / "research" / "s01b-20261108" / "_exploration" / "stop-loss-check-20261109"
DATA = Path(r"D:\TSP\data")
ENRICHED = DATA / "kline_daily_enriched"

STOP = -0.10           # 待核查的「10% 止损」档位
STOP8 = -0.08          # 实际存在的 S01b 风控变体档位（对照）
PANEL_LO = "2019-06-01"
PANEL_HI = "2026-11-02"


def load_trades() -> pl.DataFrame:
    p = RES / "a0_10bp" / "trades.parquet"
    df = pl.read_parquet(p)
    return df.with_columns(
        pl.col("entry_date").str.to_date(),
        pl.col("exit_date").str.to_date(),
        pl.col("exit_signal_date").cast(pl.Utf8).str.to_date(),
    )


def load_panel(symbols: list[str]) -> pl.DataFrame:
    df = (
        pl.scan_parquet(str(ENRICHED / "date=*" / "*.parquet"))
        .select(["symbol", "date", "open", "close", "low", "raw_close"])
        .filter(
            pl.col("symbol").is_in(symbols)
            & (pl.col("date") >= pl.lit(PANEL_LO).str.to_date())
            & (pl.col("date") <= pl.lit(PANEL_HI).str.to_date())
        )
        .collect()
        .sort(["symbol", "date"])
    )
    # engine.py:1412-1443 _raw_execution_prices：raw 平面 = 复权价 x (raw_close/close)，保留 2 位
    ratio = pl.col("raw_close") / pl.col("close")
    df = df.with_columns(
        (pl.col("open") * ratio).round(2).alias("raw_open_d"),
        (pl.col("low") * ratio).round(2).alias("raw_low_d"),
    )
    return df


def main() -> int:
    tr = load_trades()
    symbols = tr["symbol"].unique().to_list()
    panel = load_panel(symbols)

    # ---- 每标的的日期序列 ----
    by_sym: dict[str, dict[str, np.ndarray]] = {}
    for sym, g in panel.group_by("symbol", maintain_order=True):
        s = sym[0] if isinstance(sym, tuple) else sym
        by_sym[s] = {
            "date": g["date"].to_numpy(),
            "open": g["raw_open_d"].to_numpy(),
            "low": g["raw_low_d"].to_numpy(),
            "close": g["raw_close"].to_numpy(),
        }

    rows = []
    for r in tr.iter_rows(named=True):
        sym = r["symbol"]
        s = by_sym.get(sym)
        entry = float(r["entry_price"])            # 已含 10bp 滑点的成交价 = risk_entry_price
        stop_line = entry * (1 + STOP)             # 10% 档
        stop_line8 = entry * (1 + STOP8)           # 8% 档（对照）
        ed, xd = r["entry_date"], r["exit_date"]

        rec = {
            "symbol": sym,
            "entry_date": str(ed),
            "exit_date": str(xd),
            "exit_reason": r["exit_reason"],
            "entry_price": round(entry, 4),
            "exit_price": round(float(r["exit_price"]), 4),
            "pnl_pct": round(float(r["pnl_pct"]), 6),
            "pnl_amount": round(float(r["pnl_amount"]), 2),
            "duration": r["duration"],
            "blocked_exit_days": r["blocked_exit_days"],
            "stop_line_10": round(stop_line, 4),
            "stop_line_8": round(stop_line8, 4),
            "bars_in_window": 0,
            "hit10_close_date": None,
            "hit10_close_ret": None,
            "hit10_low_date": None,
            "hit10_low_ret": None,
            "hit8_close_date": None,
            "hit8_low_date": None,
            "days_past_stop10": None,
            "exit_day_open": None,
            "exit_day_open_ret": None,
            "exit_day_gap_below_stop10": None,
            "exit_day_bar_missing": None,
            "signal_to_exit_td": None,
        }

        if s is not None:
            d = s["date"]; o = s["open"]; lo = s["low"]; c = s["close"]
            m = (d >= ed) & (d <= xd)
            idx = np.flatnonzero(m)
            rec["bars_in_window"] = int(idx.size)
            if idx.size:
                cw = c[idx]
                lw = lo[idx]
                dw = d[idx]
                # 10%：日收盘口径
                h = np.flatnonzero(cw <= stop_line)
                if h.size:
                    k = int(h[0])
                    rec["hit10_close_date"] = str(dw[k])
                    rec["hit10_close_ret"] = round(float(cw[k] / entry - 1), 6)
                # 10%：盘中最低价口径（引擎非建仓日实际比较方式）
                h2 = np.flatnonzero(lw <= stop_line)
                if h2.size:
                    k = int(h2[0])
                    rec["hit10_low_date"] = str(dw[k])
                    rec["hit10_low_ret"] = round(float(lw[k] / entry - 1), 6)
                # 8%：日收盘口径（对照）
                h3 = np.flatnonzero(cw <= stop_line8)
                if h3.size:
                    rec["hit8_close_date"] = str(dw[int(h3[0])])
                h4 = np.flatnonzero(lw <= stop_line8)
                if h4.size:
                    rec["hit8_low_date"] = str(dw[int(h4[0])])
                # 出场日开盘
                ex = np.flatnonzero(d == xd)
                if ex.size:
                    k = int(ex[0])
                    rec["exit_day_open"] = round(float(o[k]), 2)
                    rec["exit_day_open_ret"] = round(float(o[k] / entry - 1), 6)
                    rec["exit_day_gap_below_stop10"] = bool(o[k] < stop_line)
                    rec["exit_day_bar_missing"] = False
                else:
                    rec["exit_day_bar_missing"] = True
        else:
            rec["exit_day_bar_missing"] = True

        if s is not None and r.get("exit_signal_date") is not None:
            d = s["date"]
            a = np.flatnonzero(d == r["exit_signal_date"])
            b = np.flatnonzero(d == xd)
            if a.size and b.size:
                rec["signal_to_exit_td"] = int(b[0] - a[0])
        # 越过 -10% 线之后又持有了多少个交易日
        if s is not None and rec["hit10_close_date"] is not None:
            d = s["date"]
            a = np.flatnonzero(d == np.datetime64(rec["hit10_close_date"]))
            b = np.flatnonzero(d == xd)
            if a.size and b.size:
                rec["days_past_stop10"] = int(b[0] - a[0])
        rows.append(rec)

    detail = pl.DataFrame(rows)

    # ---- ③ 汇总 ----
    n = detail.height
    stop_cnt = int((detail["exit_reason"] == "stop_loss").sum())
    hit10_close = int(detail["hit10_close_date"].is_not_null().sum())
    hit10_low = int(detail["hit10_low_date"].is_not_null().sum())
    hit8_close = int(detail["hit8_close_date"].is_not_null().sum())

    # ---- ④ 死叉（signal）出场 ----
    sig = detail.filter(pl.col("exit_reason") == "signal")
    sig_n = sig.height
    deep = sig.filter(pl.col("pnl_pct") < -0.10)
    deep_n = deep.height
    deep_blocked = int((deep["blocked_exit_days"] > 0).sum())
    deep_gap = int(deep["exit_day_gap_below_stop10"].fill_null(False).sum())
    deep_missing = int(deep["exit_day_bar_missing"].fill_null(True).sum())

    hit8_low = int(detail["hit8_low_date"].is_not_null().sum())
    sig_lag = sig.filter(pl.col("signal_to_exit_td").is_not_null())["signal_to_exit_td"]
    deep_days = deep.filter(pl.col("days_past_stop10").is_not_null())["days_past_stop10"]

    summary = {
        "trades_file": str(RES / "a0_10bp" / "trades.parquet"),
        "n_trades": n,
        "exit_reason_counts": {
            k: int(v) for k, v in detail["exit_reason"].value_counts().rows()
        },
        "stop_loss_exit_count": stop_cnt,
        "counterfactual_10pct": {
            "hit_by_daily_close": hit10_close,
            "hit_rate_by_daily_close": round(hit10_close / n, 4),
            "hit_by_intraday_low": hit10_low,
            "hit_rate_by_intraday_low": round(hit10_low / n, 4),
            "window": "entry_date..exit_date inclusive, raw plane, stop_line = entry_price*(1-0.10)",
        },
        "counterfactual_8pct_by_close": {
            "hit": hit8_close,
            "hit_rate": round(hit8_close / n, 4),
            "hit_by_intraday_low": hit8_low,
            "hit_rate_by_intraday_low": round(hit8_low / n, 4),
        },
        "signal_exits": {
            "n": sig_n,
            "mean_pnl_pct": round(float(sig["pnl_pct"].mean()), 6),
            "median_pnl_pct": round(float(sig["pnl_pct"].median()), 6),
            "sum_pnl_amount": round(float(sig["pnl_amount"].sum()), 2),
            "losers_lt_10pct": deep_n,
            "losers_lt_10pct_share_of_signal": round(deep_n / sig_n, 4),
            "losers_lt_10pct_blocked_exit_days_gt0": deep_blocked,
            "losers_lt_10pct_exit_open_gap_below_stop10": deep_gap,
            "losers_lt_10pct_exit_bar_missing": deep_missing,
            "losers_lt_10pct_median_pnl": round(float(deep["pnl_pct"].median()), 6) if deep_n else None,
            "losers_lt_10pct_mean_pnl": round(float(deep["pnl_pct"].mean()), 6) if deep_n else None,
            "signal_exits_blocked_exit_days_gt0": int((sig["blocked_exit_days"] > 0).sum()),
            "signal_exits_sum_blocked_days": int(sig["blocked_exit_days"].sum()),
            "signal_exits_would_hit_10pct_close": int(sig["hit10_close_date"].is_not_null().sum()),
            "signal_to_exit_td_dist": {
                "min": int(sig_lag.min()) if sig_lag.len() else None,
                "p50": float(sig_lag.median()) if sig_lag.len() else None,
                "max": int(sig_lag.max()) if sig_lag.len() else None,
            },
            "deep_losers_days_past_stop10": {
                "n": int(deep_days.len()),
                "p10": float(deep_days.quantile(0.10)) if deep_days.len() else None,
                "p50": float(deep_days.median()) if deep_days.len() else None,
                "p90": float(deep_days.quantile(0.90)) if deep_days.len() else None,
                "max": int(deep_days.max()) if deep_days.len() else None,
            },
        },
        "all_trades_pnl": {
            "mean": round(float(detail["pnl_pct"].mean()), 6),
            "sum_pnl_amount": round(float(detail["pnl_amount"].sum()), 2),
        },
    }

    detail.write_csv(OUT / "trade_level_stoploss_counterfactual.csv")
    # ④ 明细：136 笔死叉出场
    sig.write_csv(OUT / "signal_exits_136.csv")
    deep.write_csv(OUT / "signal_losers_lt_minus10pct.csv")
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
