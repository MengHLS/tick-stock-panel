#!/usr/bin/env python
"""补充证据（只读）：解释「臂1 胜率 33.5%→15.1%」的形状是不是口径bug。

两项：
  A. 池子基准率：全池 (symbol, 交易日) 上，以当日原始开盘为参照、其后 60 个交易日内
     原始最低价是否触及 -8%。这是「-8% 止损在这个池子里有多容易被打到」的基准。
  B. 单标的持有窗反事实：臂1 全部 519 笔各自的 entry 后第 60 个交易日（或末行）原始收盘
     相对建仓成交价的收益；分别看被止损的 425 笔与全部 519 笔里「本会为正」的比例。
     该反事实不含槽位/资金约束，只说明「止损砍掉的是不是潜在盈利单」。

只读：不写 results/、five_a/、engine.py。产物：summary_winrate.json + explain_winrate.csv

用法（仓库根）：
    backend\\.venv\\Scripts\\python.exe research\\s01b-20261108\\diag_stop_basis_20261108\\explain_winrate.py
退出码：0
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(r"C:\work\sourcecode\tick-stock-panel")
RES = ROOT / "research" / "s01b-20261108" / "results"
OUT = ROOT / "research" / "s01b-20261108" / "diag_stop_basis_20261108"
ENRICHED = Path(r"D:\TSP\data") / "kline_daily_enriched"

STOP_LOSS_PCT = -0.08
HORIZON = 60
PANEL_LO = dt.date(2019, 1, 1)
PANEL_HI = dt.date(2026, 11, 2)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_panel() -> pl.DataFrame:
    df = (
        pl.scan_parquet(str(ENRICHED / "date=*" / "*.parquet"))
        .select(["symbol", "date", "open", "low", "close", "raw_close", "raw_low"])
        .filter((pl.col("date") >= PANEL_LO) & (pl.col("date") <= PANEL_HI))
        .collect()
        .sort(["symbol", "date"])
    )
    return df.with_columns(
        (pl.col("open") * pl.col("raw_close") / pl.col("close")).round(2).alias("raw_open_d"),
        (pl.col("low") * pl.col("raw_close") / pl.col("close")).round(2).alias("raw_low_d"),
    )


def universe_base_rate(panel: pl.DataFrame) -> dict:
    """每个 (symbol, day)：其后 min(HORIZON, 剩余) 个交易日内 raw_low_d 的最小值 / 当日 raw_open_d。"""
    out = {"windows": 0, "touch_le_-8pct": 0, "share": None, "horizon_sessions": HORIZON}
    tot = 0
    hit = 0
    ratios: list[float] = []
    for _sym, g in panel.group_by("symbol", maintain_order=True):
        low = g["raw_low_d"].to_numpy().astype(float)
        opn = g["raw_open_d"].to_numpy().astype(float)
        n = len(low)
        if n < 2:
            continue
        ok = np.isfinite(low) & np.isfinite(opn) & (low > 0) & (opn > 0)
        # 前向窗最小值：fwd[i] = min(low[i : i+HORIZON])，NaN 不参与
        fwd = np.full(n, np.inf)
        for k in range(HORIZON):
            if k >= n:
                break
            fwd[: n - k] = np.fmin(fwd[: n - k], low[k:])
        valid = ok & np.isfinite(fwd)
        if not valid.any():
            continue
        tot += int(valid.sum())
        ratio = fwd[valid] / opn[valid]
        hit += int((ratio <= 1.0 + STOP_LOSS_PCT).sum())
        ratios.append(ratio)
    allr = np.concatenate(ratios) if ratios else np.array([])
    out["windows"] = tot
    out["touch_le_-8pct"] = hit
    out["share"] = round(hit / tot, 6) if tot else None
    if allr.size:
        out["ratio_p50"] = round(float(np.percentile(allr, 50)), 6)
        out["ratio_p10"] = round(float(np.percentile(allr, 10)), 6)
        out["ratio_p90"] = round(float(np.percentile(allr, 90)), 6)
    return out


def main() -> int:
    trades = pl.read_parquet(RES / "a1_10bp" / "trades.parquet")
    trades = trades.with_columns(
        pl.col("entry_date").str.to_date().alias("ed"),
        pl.col("exit_date").str.to_date().alias("xd"),
    )
    symbols = sorted(set(trades["symbol"].to_list()))
    panel = load_panel()
    series: dict[str, dict[str, np.ndarray]] = {}
    for key, g in panel.filter(pl.col("symbol").is_in(symbols)).group_by("symbol", maintain_order=True):
        sym = key[0] if isinstance(key, tuple) else key
        series[sym] = {
            "date": g["date"].to_numpy(),
            "raw_close": g["raw_close"].to_numpy().astype(float),
            "raw_low_d": g["raw_low_d"].to_numpy().astype(float),
            "adj_ratio": (g["raw_close"] / g["close"]).to_numpy().astype(float),
        }

    rows = []
    for r in trades.iter_rows(named=True):
        s = series.get(r["symbol"])
        if s is None:
            rows.append({"symbol": r["symbol"], "status": "symbol_missing"})
            continue
        dates = s["date"]
        i0 = int(np.searchsorted(dates, np.datetime64(r["ed"])))
        if i0 >= len(dates) or dates[i0] != np.datetime64(r["ed"]):
            rows.append({"symbol": r["symbol"], "status": "entry_missing"})
            continue
        i1 = min(i0 + HORIZON, len(dates) - 1)
        ret_h = s["raw_close"][i1] / float(r["entry_price"]) - 1.0
        w = s["raw_low_d"][i0 : i1 + 1]
        w = w[np.isfinite(w) & (w > 0)]
        touched = bool(w.size and w.min() <= (1.0 + STOP_LOSS_PCT) * float(r["entry_price"]))
        entry_low = float(s["raw_low_d"][i0])
        entry_close = float(s["raw_close"][i0])
        line = (1.0 + STOP_LOSS_PCT) * float(r["entry_price"])
        rows.append(
            {
                "symbol": r["symbol"],
                "name": r["name"],
                "entry_date": str(r["ed"]),
                "exit_date": str(r["xd"]),
                "exit_reason": r["exit_reason"],
                "entry_price_fill": float(r["entry_price"]),
                "pnl_pct": float(r["pnl_pct"]),
                "horizon_date": str(dates[i1]),
                "horizon_sessions": int(i1 - i0),
                "horizon_ret_raw": float(ret_h),
                "touched_minus8_in_window": touched,
                "entry_day_low_raw": entry_low,
                "entry_day_close_raw": entry_close,
                "entry_day_low_touch": bool(np.isfinite(entry_low) and entry_low <= line),
                "entry_day_close_touch": bool(np.isfinite(entry_close) and entry_close <= line),
                "status": "ok",
            }
        )
    df = pl.DataFrame(rows, infer_schema_length=None)
    df.write_csv(OUT / "explain_winrate.csv")
    ok = df.filter(pl.col("status") == "ok")
    stops = ok.filter(pl.col("exit_reason") == "stop_loss")

    base = universe_base_rate(panel)

    def share_pos(d: pl.DataFrame) -> dict:
        n = d.height
        pos = int((d["horizon_ret_raw"] > 0).sum())
        return {
            "n": n,
            "horizon_ret_positive": pos,
            "share_positive": round(pos / n, 6) if n else None,
            "median_horizon_ret": round(float(d["horizon_ret_raw"].median()), 6) if n else None,
            "share_horizon_ret_gt_minus8": (
                round(float((d["horizon_ret_raw"] > -0.08).mean()), 6) if n else None
            ),
        }

    summary = {
        "generated_by": "explain_winrate.py",
        "generated_at": dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "inputs": {
            "a1_trades_sha256": sha256(RES / "a1_10bp" / "trades.parquet"),
            "a1_trades_bytes": (RES / "a1_10bp" / "trades.parquet").stat().st_size,
            "panel_source": str(ENRICHED),
            "horizon_sessions": HORIZON,
        },
        "A_universe_base_rate": base,
        "B_counterfactual_hold_60": {
            "all_519": share_pos(ok),
            "stop_loss_425": share_pos(stops),
            "non_stop_94": share_pos(ok.filter(pl.col("exit_reason") != "stop_loss")),
        },
        "C_stop_trade_pnl_concentration": {
            "n_stop": stops.height,
            "share_pnl_within_50bp_of_minus8_24": round(
                float((stops["pnl_pct"] <= -0.0774).mean()), 6
            ),
            "pnl_p50": round(float(stops["pnl_pct"].median()), 6),
            "pnl_p10": round(float(np.percentile(stops["pnl_pct"].to_numpy(), 10)), 6),
            "pnl_p90": round(float(np.percentile(stops["pnl_pct"].to_numpy(), 90)), 6),
        },
        "D_entry_day_trigger_basis": {
            "note": "建仓日引擎按收盘判（engine.py:4110），其余交易日按开盘/最低价判（:4017-4067）",
            "entry_day_close_touch": int(ok["entry_day_close_touch"].sum()),
            "entry_day_low_touch_if_intraday": int(ok["entry_day_low_touch"].sum()),
            "share_close": round(float(ok["entry_day_close_touch"].mean()), 6),
            "share_low": round(float(ok["entry_day_low_touch"].mean()), 6),
        },
    }
    (OUT / "summary_winrate.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
