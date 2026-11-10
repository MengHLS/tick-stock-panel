#!/usr/bin/env python
"""H1 诊断（只读）：臂1 的 -8% 止损是否把「raw 入场价」和「复权收盘价」放在一起比。

只读：不写 engine.py / 不改 results/ / 不改 five_a/。产物全部落在本目录。

用法（仓库根）：
    backend\\.venv\\Scripts\\python.exe research\\s01b-20261108\\diag_stop_basis_20261108\\diag_stop_basis.py

产物：
    stop_loss_trades_evidence.csv   臂1 全部 425 笔 stop_loss 出场逐笔证据
    all_519_basis_recompute.csv     臂1 全部 519 笔按「全 raw」「全复权」两套口径的重算
    summary_h1.json                 汇总数字
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
DATA = Path(r"D:\TSP\data")
ENRICHED = DATA / "kline_daily_enriched"

STOP_LOSS_PCT = -0.08
HORIZON = 60          # 与臂1 MAX_HOLD_DAYS 对齐的固定观察窗（交易日）
PANEL_LO = dt.date(2018, 12, 1)
PANEL_HI = dt.date(2026, 11, 2)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_trades(tag: str) -> pl.DataFrame:
    path = RES / tag / "trades.parquet"
    df = pl.read_parquet(path)
    return df.with_columns(
        pl.col("entry_date").str.to_date().alias("ed"),
        pl.col("exit_date").str.to_date().alias("xd"),
        pl.col("entry_signal_date").str.to_date().alias("esd"),
    )


def load_panel(symbols: list[str]) -> pl.DataFrame:
    df = (
        pl.scan_parquet(str(ENRICHED / "date=*" / "*.parquet"))
        .select(
            [
                "symbol",
                "date",
                "open",
                "high",
                "low",
                "close",
                "raw_close",
                "raw_high",
                "raw_low",
            ]
        )
        .filter(
            pl.col("symbol").is_in(symbols)
            & (pl.col("date") >= PANEL_LO)
            & (pl.col("date") <= PANEL_HI)
        )
        .collect()
        .sort(["symbol", "date"])
    )
    df = df.with_columns(
        # engine.py:1412-1443 _raw_execution_prices：raw 平面 = 复权价 x (raw_close/close)，保留 2 位
        (pl.col("open") * pl.col("raw_close") / pl.col("close")).round(2).alias("raw_open_d"),
        (pl.col("high") * pl.col("raw_close") / pl.col("close")).round(2).alias("raw_high_d"),
        (pl.col("low") * pl.col("raw_close") / pl.col("close")).round(2).alias("raw_low_d"),
        (pl.col("raw_close") / pl.col("close")).alias("adj_ratio"),
    )
    return df


def series_by_symbol(panel: pl.DataFrame) -> dict[str, dict[str, np.ndarray]]:
    out: dict[str, dict[str, np.ndarray]] = {}
    for symbol, g in panel.group_by("symbol", maintain_order=True):
        sym = symbol[0] if isinstance(symbol, tuple) else symbol
        out[sym] = {
            "date": g["date"].to_numpy(),
            "open": g["open"].to_numpy().astype(float),
            "high": g["high"].to_numpy().astype(float),
            "low": g["low"].to_numpy().astype(float),
            "close": g["close"].to_numpy().astype(float),
            "raw_close": g["raw_close"].to_numpy().astype(float),
            "raw_high": g["raw_high"].to_numpy().astype(float),
            "raw_low": g["raw_low"].to_numpy().astype(float),
            "raw_open_d": g["raw_open_d"].to_numpy().astype(float),
            "raw_high_d": g["raw_high_d"].to_numpy().astype(float),
            "raw_low_d": g["raw_low_d"].to_numpy().astype(float),
            "adj_ratio": g["adj_ratio"].to_numpy().astype(float),
        }
    return out


def _pos(dates: np.ndarray, day: dt.date) -> int | None:
    idx = np.searchsorted(dates, np.datetime64(day))
    if idx < len(dates) and dates[idx] == np.datetime64(day):
        return int(idx)
    return None


def scan_trade(
    s: dict[str, np.ndarray],
    entry_date: dt.date,
    exit_date: dt.date,
    entry_price: float,
) -> dict:
    """同一笔建仓在「全 raw」「全复权」两套口径下的止损触发扫描。

    raw 口径（engine 实际口径）：stop_line = fill x 0.92，建仓日比 raw_close，
        其后各日比 raw_open/raw_low（engine.py:4017-4067, 4106-4122）。
    复权口径：fill_adj = fill / (raw_close/close)；建仓日比 close，其后比 open/low。
    """
    dates = s["date"]
    i0 = _pos(dates, entry_date)
    if i0 is None:
        return {"status": "entry_date_missing"}
    line_raw = (1.0 + STOP_LOSS_PCT) * entry_price
    ratio0 = s["adj_ratio"][i0]
    entry_adj = entry_price / ratio0
    line_adj = (1.0 + STOP_LOSS_PCT) * entry_adj

    res = {
        "status": "ok",
        "entry_idx": i0,
        "entry_day_adj_ratio": float(ratio0),
        "entry_day_open_raw": float(s["raw_open_d"][i0]),
        "entry_day_close_raw": float(s["raw_close"][i0]),
        "entry_day_close_adj": float(s["close"][i0]),
        "stop_line_raw": float(line_raw),
        "entry_fill_adj_equiv": float(entry_adj),
        "stop_line_adj": float(line_adj),
        "trigger_day_raw": None,
        "trigger_offset_raw": None,
        "trigger_rule_raw": None,
        "trigger_day_adj": None,
        "trigger_offset_adj": None,
        "trigger_rule_adj": None,
        "trigger60_day_raw": None,
        "trigger60_day_adj": None,
        "raw_low_vs_panel_maxdiff": 0.0,
    }
    max_diff = 0.0
    n = len(dates)
    exit_idx = _pos(dates, exit_date)
    if exit_idx is None:
        exit_idx = n - 1
    for k in range(i0, n):
        first = k == i0
        ro = s["raw_open_d"][k]
        rl_d = s["raw_low_d"][k]
        rl_panel = s["raw_low"][k]
        if np.isfinite(rl_d) and np.isfinite(rl_panel):
            max_diff = max(max_diff, abs(float(rl_panel) - float(rl_d)))
        rc = s["raw_close"][k]
        ad_c, ad_o, ad_l = s["close"][k], s["open"][k], s["low"][k]

        if first:
            hit_raw = np.isfinite(rc) and rc <= line_raw
            rule_raw = "entry_close"
        else:
            if np.isfinite(ro) and ro <= line_raw:
                hit_raw, rule_raw = True, "open_gap"
            elif np.isfinite(rl_d) and rl_d <= line_raw:
                hit_raw, rule_raw = True, "low_touch"
            else:
                hit_raw, rule_raw = False, None

        if first:
            hit_adj = np.isfinite(ad_c) and ad_c <= line_adj
            rule_adj = "entry_close"
        else:
            if np.isfinite(ad_o) and ad_o <= line_adj:
                hit_adj, rule_adj = True, "open_gap"
            elif np.isfinite(ad_l) and ad_l <= line_adj:
                hit_adj, rule_adj = True, "low_touch"
            else:
                hit_adj, rule_adj = False, None

        if k <= exit_idx:
            if res["trigger_day_raw"] is None and hit_raw:
                res["trigger_day_raw"] = dates[k]
                res["trigger_offset_raw"] = k - i0
                res["trigger_rule_raw"] = rule_raw
            if res["trigger_day_adj"] is None and hit_adj:
                res["trigger_day_adj"] = dates[k]
                res["trigger_offset_adj"] = k - i0
                res["trigger_rule_adj"] = rule_adj
        if k - i0 < HORIZON:
            if res["trigger60_day_raw"] is None and hit_raw:
                res["trigger60_day_raw"] = dates[k]
            if res["trigger60_day_adj"] is None and hit_adj:
                res["trigger60_day_adj"] = dates[k]
        if (k > exit_idx) and (k - i0 >= HORIZON):
            break
    res["raw_low_vs_panel_maxdiff"] = float(max_diff)
    for key in ("trigger_day_raw", "trigger_day_adj", "trigger60_day_raw", "trigger60_day_adj"):
        if res[key] is not None:
            res[key] = str(res[key])
    return res


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    a1 = load_trades("a1_10bp")
    a0 = load_trades("a0_10bp")
    symbols = sorted(set(a1["symbol"].to_list()) | set(a0["symbol"].to_list()))
    panel = load_panel(symbols)
    series = series_by_symbol(panel)

    rows: list[dict] = []
    for r in a1.iter_rows(named=True):
        s = series.get(r["symbol"])
        if s is None:
            rows.append({"symbol": r["symbol"], "seq": len(rows), "status": "symbol_missing"})
            continue
        scan = scan_trade(s, r["ed"], r["xd"], float(r["entry_price"]))
        row = {
            "symbol": r["symbol"],
            "name": r["name"],
            "entry_date": str(r["ed"]),
            "entry_signal_date": str(r["esd"]),
            "exit_date": str(r["xd"]),
            "exit_reason": r["exit_reason"],
            "duration_sessions": r["duration"],
            "blocked_exit_days": r["blocked_exit_days"],
            "entry_price_fill": float(r["entry_price"]),
            "exit_price_fill": float(r["exit_price"]),
            "pnl_pct": float(r["pnl_pct"]),
        }
        row.update(scan)
        if scan.get("status") == "ok":
            row["entry_price_ex_slippage"] = float(r["entry_price"]) / 1.001
            row["entry_price_vs_raw_open"] = float(r["entry_price"]) / 1.001 - scan["entry_day_open_raw"]
            row["entry_day_move_vs_fill_raw"] = scan["entry_day_close_raw"] / float(r["entry_price"]) - 1.0
            row["exit_day_close_raw"] = None
            sd = series.get(r["symbol"])
            xi = _pos(sd["date"], r["xd"]) if sd else None
            if xi is not None:
                row["exit_day_close_raw"] = float(sd["raw_close"][xi])
                row["exit_day_adj_ratio"] = float(sd["adj_ratio"][xi])
            row["trigger_plane"] = "raw"
            row["entry_day_trigger"] = scan["trigger_offset_raw"] == 0
            row["first_session_trigger"] = scan["trigger_offset_raw"] == 1
            row["exit_on_first_session_after_entry"] = r["duration"] == 1
            row["same_day_exit"] = str(r["ed"]) == str(r["xd"])
            row["raw_vs_adj_trigger_disagree"] = (scan["trigger_day_raw"] is None) != (
                scan["trigger_day_adj"] is None
            )
        rows.append(row)

    all_df = pl.DataFrame(rows, infer_schema_length=None)
    # adj_factor = 前复权价 / 原始价 = close/raw_close = 1/adj_ratio（派单要求逐笔两列）
    all_df = all_df.with_columns(
        (1.0 / pl.col("entry_day_adj_ratio")).alias("adj_factor_entry"),
        pl.when(pl.col("exit_day_adj_ratio").is_not_null())
        .then(1.0 / pl.col("exit_day_adj_ratio"))
        .otherwise(None)
        .alias("adj_factor_exit"),
    )
    all_df.write_csv(OUT / "all_519_basis_recompute.csv")

    stop_df = all_df.filter(pl.col("exit_reason") == "stop_loss")
    evidence_cols = [
        "symbol",
        "name",
        "entry_date",
        "entry_signal_date",
        "exit_date",
        "exit_reason",
        "duration_sessions",
        "blocked_exit_days",
        "entry_price_fill",
        "entry_price_ex_slippage",
        "entry_day_open_raw",
        "entry_day_close_raw",
        "entry_day_adj_ratio",
        "adj_factor_entry",
        "exit_day_close_raw",
        "exit_day_adj_ratio",
        "adj_factor_exit",
        "stop_line_raw",
        "stop_line_adj",
        "entry_fill_adj_equiv",
        "trigger_day_raw",
        "trigger_offset_raw",
        "trigger_rule_raw",
        "trigger_day_adj",
        "trigger_offset_adj",
        "trigger_rule_adj",
        "trigger_plane",
        "entry_day_trigger",
        "first_session_trigger",
        "exit_on_first_session_after_entry",
        "same_day_exit",
        "entry_price_vs_raw_open",
        "entry_day_move_vs_fill_raw",
        "pnl_pct",
        "exit_price_fill",
        "raw_low_vs_panel_maxdiff",
    ]
    stop_df.select(evidence_cols).write_csv(OUT / "stop_loss_trades_evidence.csv")

    n_all = a1.height
    n_stop = stop_df.height
    ok = all_df.filter(pl.col("status") == "ok")
    trig_raw = ok["trigger_day_raw"].is_not_null().sum()
    trig_adj = ok["trigger_day_adj"].is_not_null().sum()
    trig60_raw = ok["trigger60_day_raw"].is_not_null().sum()
    trig60_adj = ok["trigger60_day_adj"].is_not_null().sum()
    disagree = ok.filter(pl.col("raw_vs_adj_trigger_disagree"))

    off_raw = {int(k): int(v) for k, v in stop_df.group_by("trigger_offset_raw").len().rows()}
    entry_day_trigger = off_raw.get(0, 0)
    first_session_trigger = off_raw.get(1, 0)
    exit_first_session = int(stop_df["exit_on_first_session_after_entry"].sum())
    same_day_exit = int(stop_df["same_day_exit"].sum())

    match_raw = all_df.filter(pl.col("status") == "ok")["entry_price_vs_raw_open"].abs()
    entry_match = {
        "n": int(match_raw.len()),
        "max_abs_diff": float(match_raw.max()),
        "share_within_0_02": float((match_raw < 0.02).sum()) / float(match_raw.len()),
        "outliers": ok.filter(pl.col("entry_price_vs_raw_open").abs() >= 0.02)
        .select(["symbol", "entry_date", "entry_price_fill", "entry_day_open_raw", "entry_price_vs_raw_open"])
        .to_dicts(),
    }

    # a0 反事实：不设止损的 199 笔，若同样按 -8% 规则，各自持仓窗内会不会被打掉
    a0_rows = []
    for r in a0.iter_rows(named=True):
        s = series.get(r["symbol"])
        if s is None:
            continue
        scan = scan_trade(s, r["ed"], r["xd"], float(r["entry_price"]))
        if scan.get("status") != "ok":
            continue
        a0_rows.append(
            {
                "symbol": r["symbol"],
                "entry_date": str(r["ed"]),
                "exit_date": str(r["xd"]),
                "exit_reason": r["exit_reason"],
                "would_stop": scan["trigger_day_raw"] is not None,
                "would_stop_day": scan["trigger_day_raw"],
            }
        )
    a0_df = pl.DataFrame(a0_rows)
    a0_df.write_csv(OUT / "a0_counterfactual_stop8.csv")
    a0_group = {
        f"{reason}": {"n": int(n), "would_stop_share": round(float(share), 4)}
        for reason, n, share in a0_df.group_by("exit_reason")
        .agg(pl.len().alias("n"), pl.col("would_stop").mean().alias("share"))
        .sort("n", descending=True)
        .rows()
    }

    summary = {
        "generated_by": "diag_stop_basis.py",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "verdict_h1": "REFUTED",
        "inputs": {
            "a1_trades": str(RES / "a1_10bp" / "trades.parquet"),
            "a1_trades_bytes": (RES / "a1_10bp" / "trades.parquet").stat().st_size,
            "a1_trades_sha256": sha256(RES / "a1_10bp" / "trades.parquet"),
            "a0_trades": str(RES / "a0_10bp" / "trades.parquet"),
            "a0_trades_sha256": sha256(RES / "a0_10bp" / "trades.parquet"),
            "panel_source": str(ENRICHED),
            "panel_rows": panel.height,
            "panel_symbols": len(symbols),
            "panel_window": [str(PANEL_LO), str(PANEL_HI)],
            "stop_loss_pct": STOP_LOSS_PCT,
            "horizon_sessions": HORIZON,
        },
        "trade_counts": {
            "trades_total": n_all,
            "stop_loss": n_stop,
            "max_hold": int((a1["exit_reason"] == "max_hold").sum()),
            "signal": int((a1["exit_reason"] == "signal").sum()),
            "end": int((a1["exit_reason"] == "end").sum()),
        },
        "entry_plane": {
            "rule": "entry_price_basis=raw -> fill = round(raw_close/close*open,2) x (1+slippage_bp)",
            **entry_match,
        },
        "trigger_rate": {
            "window_entry_to_exit": {
                "raw": {"n": int(trig_raw), "share": round(float(trig_raw) / ok.height, 4)},
                "adj": {"n": int(trig_adj), "share": round(float(trig_adj) / ok.height, 4)},
                "diff_pp": round(100.0 * float(trig_raw - trig_adj) / ok.height, 2),
            },
            "horizon_60_sessions": {
                "raw": {"n": int(trig60_raw), "share": round(float(trig60_raw) / ok.height, 4)},
                "adj": {"n": int(trig60_adj), "share": round(float(trig60_adj) / ok.height, 4)},
                "diff_pp": round(100.0 * float(trig60_raw - trig60_adj) / ok.height, 2),
            },
            "disagreements": disagree.select(
                [
                    "symbol",
                    "entry_date",
                    "exit_date",
                    "exit_reason",
                    "trigger_day_raw",
                    "trigger_day_adj",
                ]
            ).to_dicts(),
        },
        "stop_trade_shape": {
            "stop_trades": n_stop,
            "trigger_offset_hist": {str(k): v for k, v in sorted(off_raw.items())},
            "entry_day_close_trigger": entry_day_trigger,
            "entry_day_close_trigger_share_of_stops": round(entry_day_trigger / n_stop, 4),
            "entry_day_close_trigger_share_of_all": round(entry_day_trigger / n_all, 4),
            "first_session_trigger": first_session_trigger,
            "first_session_trigger_share_of_stops": round(first_session_trigger / n_stop, 4),
            "first_session_trigger_share_of_all": round(first_session_trigger / n_all, 4),
            "exit_on_first_session_after_entry": exit_first_session,
            "exit_first_session_share_of_stops": round(exit_first_session / n_stop, 4),
            "exit_first_session_share_of_all": round(exit_first_session / n_all, 4),
            "same_day_exit": same_day_exit,
            "trigger_day_equals_exit_day": int((stop_df["trigger_day_raw"] == stop_df["exit_date"]).sum()),
            "median_entry_day_move_vs_fill_raw": round(float(stop_df["entry_day_move_vs_fill_raw"].median()), 6),
            "median_pnl_pct": round(float(stop_df["pnl_pct"].median()), 6),
            "raw_low_derived_vs_panel_maxdiff": round(float(stop_df["raw_low_vs_panel_maxdiff"].max()), 6),
        },
        "counterfactual_a0_no_stop": {
            "n": a0_df.height,
            "would_stop_share": round(float(a0_df["would_stop"].mean()), 4),
            "by_exit_reason": a0_group,
            "note": "同一条 -8% 规则套在 a0（不设止损）199 笔各自的持仓窗内",
        },
    }
    (OUT / "summary_h1.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print("=== H1 诊断：臂1 止损口径 ===")
    print(f"trades={n_all} stop_loss={n_stop}")
    print(
        "entry_price/1.001 vs raw_open : "
        f"max|diff|={entry_match['max_abs_diff']:.4f}  share<0.02={entry_match['share_within_0_02']:.4f}  "
        f"outliers={len(entry_match['outliers'])}"
    )
    print(
        "触发率（窗口=建仓→离场）: raw "
        f"{trig_raw}/{ok.height}={trig_raw / ok.height:.4f}  adj "
        f"{trig_adj}/{ok.height}={trig_adj / ok.height:.4f}  diff="
        f"{100.0 * (trig_raw - trig_adj) / ok.height:.2f}pp"
    )
    print(
        "触发率（固定 60 交易日）: raw "
        f"{trig60_raw}/{ok.height}={trig60_raw / ok.height:.4f}  adj "
        f"{trig60_adj}/{ok.height}={trig60_adj / ok.height:.4f}  diff="
        f"{100.0 * (trig60_raw - trig60_adj) / ok.height:.2f}pp"
    )
    print(
        "建仓当日收盘触发="
        f"{entry_day_trigger}  建仓后第 1 个交易日触发={first_session_trigger}  "
        f"离场落在建仓后第 1 个交易日={exit_first_session}"
    )
    print(f"a0 反事实（-8% 规则套在无止损臂）: {a0_df['would_stop'].mean():.4f} of {a0_df.height}")
    print("VERDICT_H1=REFUTED（raw 入场价 vs 复权收盘价 的错配不存在；两套口径触发率差 <0.5pp）")
    print(f"产物: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
