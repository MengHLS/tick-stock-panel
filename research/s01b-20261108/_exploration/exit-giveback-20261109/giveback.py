# -*- coding: utf-8 -*-
"""S01b 出场让渡（exit giveback）只读测量 v2。

只读：不写 engine/策略/生产文件，不重跑回测。
输入（全部已落盘）：
  research/s01b-20261108/_exploration/results/a0_10bp/trades.parquet  (199 笔)
  research/s01b-20261108/_exploration/results/a0_10bp/equity.parquet  (1779 点)
  D:/TSP/data/kline_daily_enriched/date=*/*.parquet                  (日线，raw_close + 复权 close)
输出（本目录）：giveback_trades.csv / summary.json
用法：backend\.venv\Scripts\python.exe ...\giveback.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(r"C:\work\sourcecode\tick-stock-panel")
RES = ROOT / "research" / "s01b-20261108" / "_exploration" / "results" / "a0_10bp"
OUT = ROOT / "research" / "s01b-20261108" / "_exploration" / "exit-giveback-20261109"
ENRICHED = Path(r"D:\TSP\data\kline_daily_enriched")

BASE_EQUITY = 1_000_000.0
SYS_END_EQUITY = 1_242_725.28
SYS_TOTAL_PNL = 242_725.28
FRACS = (0.5, 0.6, 0.7)


def stats(v: np.ndarray) -> dict:
    v = v.astype(float)
    return {
        "mean": round(float(np.mean(v)), 6),
        "median": round(float(np.median(v)), 6),
        "p10": round(float(np.percentile(v, 10)), 6),
        "p25": round(float(np.percentile(v, 25)), 6),
        "p75": round(float(np.percentile(v, 75)), 6),
        "p90": round(float(np.percentile(v, 90)), 6),
        "max": round(float(np.max(v)), 6),
        "min": round(float(np.min(v)), 6),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    t = pl.read_parquet(RES / "trades.parquet")
    eq = pl.read_parquet(RES / "equity.parquet")

    symbols = sorted(t["symbol"].unique().to_list())
    lo, hi = t["entry_date"].min(), t["exit_date"].max()

    px = (
        pl.scan_parquet(str(ENRICHED / "date=*" / "*.parquet"))
        .select(["symbol", "date", "close", "raw_close", "raw_high"])
        .filter(
            pl.col("symbol").is_in(symbols)
            & (pl.col("date") >= pl.lit(lo).str.to_date())
            & (pl.col("date") <= pl.lit(hi).str.to_date())
        )
        .collect()
        .sort(["symbol", "date"])
    )
    panel = {}
    for (sym,), g in px.group_by(["symbol"], maintain_order=True):
        panel[sym] = {
            "date": g["date"].to_numpy(),
            "close": g["close"].to_numpy().astype(float),
            "raw_close": g["raw_close"].to_numpy().astype(float),
            "raw_high": g["raw_high"].to_numpy().astype(float),
        }

    rows, missing = [], []
    for r in t.iter_rows(named=True):
        sym = r["symbol"]
        p = panel.get(sym)
        ed, xd = np.datetime64(r["entry_date"]), np.datetime64(r["exit_date"])
        if p is None:
            missing.append(sym)
            continue
        m = (p["date"] >= ed) & (p["date"] <= xd)
        if not m.any():
            missing.append(sym)
            continue
        rc, ac, rh, dts = p["raw_close"][m], p["close"][m], p["raw_high"][m], p["date"][m]
        i = int(np.argmax(rc))
        peak_raw, peak_raw_date = float(rc[i]), str(dts[i].astype("datetime64[D]"))
        j = int(np.argmax(ac))
        peak_adj, peak_adj_date = float(ac[j]), str(dts[j].astype("datetime64[D]"))

        # 入场/出场日的复权换算比（close/raw_close），用于复权口径的敏感性
        ratio_entry = None
        k = np.where(p["date"] == ed)[0]
        if len(k):
            ratio_entry = float(p["close"][k[0]] / p["raw_close"][k[0]])
        ratio_exit = None
        k = np.where(p["date"] == xd)[0]
        if len(k):
            ratio_exit = float(p["close"][k[0]] / p["raw_close"][k[0]])

        entry, exitp, shares = float(r["entry_price"]), float(r["exit_price"]), float(r["shares"])
        peak_gain = peak_raw / entry - 1.0
        exit_gross = exitp / entry - 1.0
        # 复权口径（基一致）：entry_adj/exit_adj 由当日 adjustment ratio 换算
        if ratio_entry and ratio_exit:
            entry_adj = entry * ratio_entry
            exit_adj = exitp * ratio_exit
            peak_gain_adj = peak_adj / entry_adj - 1.0
            exit_gross_adj = exit_adj / entry_adj - 1.0
        else:
            peak_gain_adj = exit_gross_adj = float("nan")
        cost = (float(r["entry_value"]) - shares * entry) + (shares * exitp - float(r["exit_value"]))

        row = {
            "symbol": sym, "name": r["name"], "entry_date": r["entry_date"], "exit_date": r["exit_date"],
            "duration": r["duration"], "exit_reason": r["exit_reason"], "open_at_end": r["open_at_end"],
            "blocked_exit_days": r["blocked_exit_days"],
            "days_to_peak": i, "window_bars": int(m.sum()),
            "peak_pos_frac": round(i / max(int(m.sum()) - 1, 1), 4),
            "adj_ratio_change": round(ratio_exit / ratio_entry - 1.0, 6) if (ratio_entry and ratio_exit) else None,
            "entry_price_raw": round(entry, 4), "exit_price_raw": round(exitp, 4), "shares": shares,
            "position_value_raw": round(entry * shares, 2),
            "n_bars_in_hold": int(m.sum()),
            "peak_close_raw": round(peak_raw, 4), "peak_date": peak_raw_date,
            "peak_gain": round(peak_gain, 6),
            "exit_gain_gross": round(exit_gross, 6),
            "pnl_pct_net": round(float(r["pnl_pct"]), 6),
            "cost_yuan": round(cost, 4),
            "giveback_pp_vs_gross": round(peak_gain - exit_gross, 6),
            "giveback_pp_vs_net": round(peak_gain - float(r["pnl_pct"]), 6),
            "giveback_yuan": round(shares * (peak_raw - exitp), 2),
            "pnl_amount": round(float(r["pnl_amount"]), 2),
            "peak_close_adj": round(peak_adj, 4), "peak_date_adj": peak_adj_date,
            "peak_gain_adj": round(peak_gain_adj, 6) if peak_gain_adj == peak_gain_adj else None,
            "exit_gain_gross_adj": round(exit_gross_adj, 6) if exit_gross_adj == exit_gross_adj else None,
            "giveback_pp_adj": round(peak_gain_adj - exit_gross_adj, 6) if peak_gain_adj == peak_gain_adj else None,
            "giveback_yuan_adj": round(shares * (peak_adj - (exitp * ratio_exit if ratio_exit else exitp)), 2) if ratio_exit else None,
        }
        for f in FRACS:
            kk = int(f * 100)
            active = peak_gain > 0
            new_exit = round(entry * (1 + peak_gain * f), 2) if active else exitp
            new_pnl = shares * (new_exit - entry) - cost
            row[f"cf_exit_{kk}"] = new_exit
            row[f"cf_pnl_{kk}"] = round(new_pnl, 2)
            row[f"cf_delta_{kk}"] = round(new_pnl - float(r["pnl_amount"]), 2)
            row[f"cf_harmed_{kk}"] = bool(active and exit_gross > peak_gain * f)
        rows.append(row)

    df = pl.DataFrame(rows, infer_schema_length=None)
    df.write_csv(OUT / "giveback_trades.csv")

    pct_cols = ["peak_gain", "exit_gain_gross", "pnl_pct_net", "cost_yuan",
                "giveback_pp_vs_gross", "giveback_pp_vs_net", "giveback_yuan"]
    grp = []
    for reason in ["max_hold", "signal", "end", "ALL"]:
        g = df if reason == "ALL" else df.filter(pl.col("exit_reason") == reason)
        if g.height == 0:
            continue
        rec = {"exit_reason": reason, "n": g.height,
               "sum_giveback_yuan": round(float(g["giveback_yuan"].sum()), 2),
               "sum_pnl": round(float(g["pnl_amount"].sum()), 2),
               "sum_position_value": round(float(g["position_value_raw"].sum()), 2)}
        for c in pct_cols:
            rec[c] = stats(g[c].to_numpy())
        grp.append(rec)

    tiers = [0.20, 0.50, 1.00, 2.00]
    tier_out = []
    for th in tiers:
        g = df.filter(pl.col("peak_gain") >= th)
        fell = g.filter(pl.col("exit_gain_gross") < th)
        rec = {
            "tier": f"peak>={int(th*100)}%", "n_peak": g.height,
            "n_exit_below_tier": fell.height,
            "share_fell": round(fell.height / g.height, 4) if g.height else None,
            "fell_exit_gain": stats(fell["exit_gain_gross"].to_numpy()) if fell.height else None,
            "fell_drop_pp": stats(fell["giveback_pp_vs_gross"].to_numpy()) if fell.height else None,
            "fell_giveback_yuan": round(float(fell["giveback_yuan"].sum()), 2) if fell.height else 0.0,
            "by_reason": {},
        }
        for reason in ["max_hold", "signal", "end"]:
            gg, ff = g.filter(pl.col("exit_reason") == reason), fell.filter(pl.col("exit_reason") == reason)
            rec["by_reason"][reason] = {
                "n_peak": gg.height, "n_fell": ff.height,
                "fell_exit_gain_mean": round(float(np.mean(ff["exit_gain_gross"].to_numpy())), 6) if ff.height else None,
                "fell_exit_gain_median": round(float(np.median(ff["exit_gain_gross"].to_numpy())), 6) if ff.height else None,
                "fell_drop_pp_mean": round(float(np.mean(ff["giveback_pp_vs_gross"].to_numpy())), 6) if ff.height else None,
                "fell_drop_pp_median": round(float(np.median(ff["giveback_pp_vs_gross"].to_numpy())), 6) if ff.height else None,
                "fell_giveback_yuan": round(float(ff["giveback_yuan"].sum()), 2) if ff.height else 0.0,
            }
        tier_out.append(rec)

    giveback_total = float(df["giveback_yuan"].sum())
    giveback_adj_total = float(df["giveback_yuan_adj"].sum())
    completed = df.filter(~pl.col("open_at_end"))
    cf = []
    for f in FRACS:
        kk = int(f * 100)
        harmed = df.filter(pl.col(f"cf_harmed_{kk}"))
        cf.append({
            "frac": f,
            "sum_pnl_cf_all199": round(float(df[f"cf_pnl_{kk}"].sum()), 2),
            "delta_all199": round(float(df[f"cf_pnl_{kk}"].sum()) - float(df["pnl_amount"].sum()), 2),
            "sum_pnl_cf_completed194": round(float(completed[f"cf_pnl_{kk}"].sum()), 2),
            "delta_completed194": round(float(completed[f"cf_pnl_{kk}"].sum()) - float(completed["pnl_amount"].sum()), 2),
            "harm_n": harmed.height,
            "harm_yuan": round(float(harmed[f"cf_delta_{kk}"].sum()), 2),
            "harm_reasons": harmed["exit_reason"].value_counts().to_dicts() if harmed.height else [],
            "gain_n": df.filter(pl.col(f"cf_delta_{kk}") > 1e-9).height,
            "gain_yuan": round(float(df.filter(pl.col(f"cf_delta_{kk}") > 0)[f"cf_delta_{kk}"].sum()), 2),
        })

    eq_end = float(eq["value"][-1])
    open_rows = df.filter(pl.col("open_at_end"))
    open_entry_val = float(open_rows["position_value_raw"].sum())
    open_mark_val = float((open_rows["exit_price_raw"] * open_rows["shares"]).sum())
    realized = float(completed["pnl_amount"].sum())

    summary = {
        "meta": {
            "generated": "2026-11-09", "role": "研究侧只读测量，不进验收基准",
            "peak_basis_primary": "raw_close（与 entry_price/exit_price 同为不复权基；entry/exit 均取自开盘价×10bp 滑点）",
            "peak_basis_sensitivity": "复权 close（entry/exit 按当日 close/raw_close 换算）",
            "window": "entry_date..exit_date 含两端",
            "price_panel": str(ENRICHED / "date=*" / "*.parquet"),
            "trades_missing_bars": missing,
        },
        "dist_by_exit_reason": grp,
        "peak_tiers": tier_out,
        "giveback": {
            "total_yuan_raw_basis": round(giveback_total, 2),
            "total_yuan_adj_basis": round(giveback_adj_total, 2),
            "sys_total_pnl": SYS_TOTAL_PNL,
            "ratio_to_sys_total_pnl": round(giveback_total / SYS_TOTAL_PNL, 4),
            "ratio_to_sum_pnl_amount_194": round(giveback_total / realized, 4),
            "n_peak_above_entry": df.filter(pl.col("peak_gain") > 0).height,
            "avg_giveback_per_trade": round(giveback_total / df.height, 2),
            "avg_position_value": round(float(df["position_value_raw"].mean()), 2),
            "avg_cost_per_trade": round(float(df["cost_yuan"].mean()), 2),
            "total_cost": round(float(df["cost_yuan"].sum()), 2),
        },
        "counterfactual_peak_half": cf,
        "timing": {
            "days_to_peak_by_reason": {
                rname: stats((df if rname == "ALL" else df.filter(pl.col("exit_reason") == rname))["days_to_peak"].to_numpy())
                for rname in ["max_hold", "signal", "end", "ALL"]
                if rname == "ALL" or df.filter(pl.col("exit_reason") == rname).height
            },
            "peak_frac_by_reason": {
                rname: stats((df if rname == "ALL" else df.filter(pl.col("exit_reason") == rname))["peak_pos_frac"].to_numpy())
                for rname in ["max_hold", "signal", "end", "ALL"]
                if rname == "ALL" or df.filter(pl.col("exit_reason") == rname).height
            },
            "share_peak_in_last5_bars": round(float((df["days_to_peak"] >= df["window_bars"] - 5).mean()), 4),
            "n_corporate_action_windows": int(df.filter(pl.col("adj_ratio_change").is_not_null() & (pl.col("adj_ratio_change").abs() > 0.005)).height),
        },
        "consistency": {
            "sum_pnl_amount_199": round(float(df["pnl_amount"].sum()), 2),
            "sum_pnl_amount_194_completed": round(realized, 2),
            "sum_pnl_amount_5_open": round(float(open_rows["pnl_amount"].sum()), 2),
            "equity_end": eq_end, "equity_gain": round(eq_end - BASE_EQUITY, 2),
            "residual_vs_system": round(eq_end - SYS_END_EQUITY, 2),
            "recon_realized_plus_open_mark_minus_cost": round(realized + open_mark_val - open_entry_val, 2),
            "recon_gap_vs_equity": round(realized + open_mark_val - open_entry_val - (eq_end - BASE_EQUITY), 2),
        },
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("giveback", "consistency")}, ensure_ascii=False, indent=1))
    for c in cf:
        print(c)
    for g in grp:
        print(g["exit_reason"], g["n"], "peak", g["peak_gain"]["median"], "gross", g["exit_gain_gross"]["median"],
              "净", g["pnl_pct_net"]["median"], "让渡pp", g["giveback_pp_vs_gross"],
              "让渡元", g["sum_giveback_yuan"], "pnl", g["sum_pnl"])


if __name__ == "__main__":
    main()
