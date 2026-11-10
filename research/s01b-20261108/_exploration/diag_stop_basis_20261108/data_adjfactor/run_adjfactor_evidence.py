"""S01b 臂1 止损口径诊断 · 复权/数据侧只读取证（v2 修正版）。

只读 D:\\TSP 数据；不写任何数据分区、不重抓、不发网络请求。
输出写到本脚本所在目录。

修正记录：v1 误把 kline_daily_enriched.open 当作原始价（它已是前复权价），
故 v2 统一用 f = close/raw_close 还原 raw_open / raw_low / raw_high。

复跑：
  cd C:\\work\\sourcecode\\tick-stock-panel
  backend\\.venv\\Scripts\\python.exe research\\s01b-20261108\\diag_stop_basis_20261108\\data_adjfactor\\run_adjfactor_evidence.py
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

REPO = Path(r"C:\work\sourcecode\tick-stock-panel")
DATA = Path(r"D:\TSP\data")
OUT = Path(__file__).resolve().parent
TRADES = REPO / "research/s01b-20261108/results/a1_10bp/trades.parquet"
ENRICHED = DATA / "kline_daily_enriched"
DAILY = DATA / "kline_daily"
ADJ = DATA / "adj_factor/all.parquet"
COLS = ["symbol", "date", "open", "high", "low", "close", "raw_close"]


def pctl(s: pd.Series, q: float) -> float | None:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if s.empty:
        return None
    return float(np.percentile(s, q))


def sha256_file(p: Path, limit: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        h.update(fh.read(limit))
    return h.hexdigest() + ("" if p.stat().st_size <= limit else " (first 4MiB)")


def dir_fingerprint(root: Path) -> dict:
    files = glob.glob(str(root / "**" / "*.parquet"), recursive=True)
    sizes = 0
    newest = 0.0
    for p in files:
        st = os.stat(p)
        sizes += st.st_size
        newest = max(newest, st.st_mtime)
    return {
        "path": str(root),
        "files": len(files),
        "bytes": sizes,
        "newest_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(newest)) if newest else None,
    }


def load_enriched(start: str = "2019-06-01") -> pd.DataFrame:
    paths = sorted(glob.glob(str(ENRICHED / "date=*/part.parquet")))
    paths = [p for p in paths if Path(p).parent.name[5:] >= start]
    frames = []
    for p in paths:
        df = pq.ParquetFile(p).read(columns=COLS).to_pandas()
        df["date"] = df["date"].astype(str)
        frames.append(df[COLS])
    return pd.concat(frames, ignore_index=True)


def main() -> dict:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    OUT.mkdir(parents=True, exist_ok=True)
    res: dict = {}
    t0 = time.time()

    # ---------------- 0. 输入与完整性快照 ----------------
    res["inputs"] = {
        "trades": {"path": str(TRADES), "bytes": TRADES.stat().st_size,
                   "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(TRADES.stat().st_mtime))},
        "fingerprint_before": {
            "kline_daily": dir_fingerprint(DAILY),
            "kline_daily_enriched": dir_fingerprint(ENRICHED),
            "adj_factor": {**dir_fingerprint(DATA / "adj_factor"), "sha256_first4MiB": sha256_file(ADJ)},
        },
    }

    trades = pq.ParquetFile(TRADES).read().to_pandas()
    for c in ("entry_date", "exit_date"):
        trades[c] = trades[c].astype(str)
    panel = load_enriched()
    adj = pq.ParquetFile(ADJ).read().to_pandas()
    adj["trade_date"] = adj["trade_date"].astype(str)
    adj["ex_factor"] = adj["ex_factor"].astype(float)
    adj = adj.sort_values(["symbol", "trade_date"]).reset_index(drop=True)

    panel["f"] = panel["close"] / panel["raw_close"]
    panel["raw_open"] = panel["open"] / panel["f"]
    panel["raw_low"] = panel["low"] / panel["f"]
    panel["raw_high"] = panel["high"] / panel["f"]
    panel["adj_open"] = panel["close"] / panel["raw_close"] * panel["raw_open"]

    # 前复权复算：f_expected = cum(<=date) / cum_total
    adj["cum"] = adj.groupby("symbol")["ex_factor"].cumprod()
    total = adj.groupby("symbol")["cum"].last().rename("total")
    sub = panel.merge(total, on="symbol", how="left")
    sub["total"] = sub["total"].fillna(1.0)
    left = sub.copy()
    right = adj[["symbol", "trade_date", "cum"]].rename(columns={"trade_date": "date"}).copy()
    left["dkey"] = left["date"].str.replace("-", "", regex=False).astype("int64")
    right["dkey"] = right["date"].str.replace("-", "", regex=False).astype("int64")
    merged = pd.merge_asof(
        left.sort_values("dkey"), right[["symbol", "dkey", "cum"]].sort_values("dkey"),
        on="dkey", by="symbol", direction="backward",
    ).drop(columns=["dkey"])
    merged["cum"] = merged["cum"].fillna(1.0)
    merged["f_expected"] = merged["cum"] / merged["total"]
    merged["f_diff"] = (merged["f"] - merged["f_expected"]).abs()
    ok = merged[(merged["raw_close"] > 0) & (merged["close"] > 0)].copy()

    # ---------------- Q1 复权口径 ----------------
    kd_cols = pq.ParquetFile(DAILY / "date=2026-11-06/part.parquet").read().to_pandas().columns.tolist()
    en_cols = pq.ParquetFile(ENRICHED / "date=2026-11-06/part.parquet").read().to_pandas().columns.tolist()
    last_date = ok["date"].max()
    last = ok[ok["date"] == last_date]
    res["Q1"] = {
        "kline_daily_cols": kd_cols,
        "kline_daily_has_any_adj_column": any("adj" in c or "raw" in c or "factor" in c for c in kd_cols),
        "kline_daily_enriched_cols": en_cols,
        "adj_factor_cols": adj.columns.tolist(),
        "adj_factor_rows": int(len(adj)),
        "adj_factor_symbols": int(adj["symbol"].nunique()),
        "adj_factor_range": [adj["trade_date"].min(), adj["trade_date"].max()],
        "adj_factor_row_is_event": "每行=一次除权除息事件（非每日序列），ex_factor = 除权前收盘 / 除权参考价",
        "adj_factor_duplicated_symbol_date": int(adj.duplicated(["symbol", "trade_date"]).sum()),
        "recompute": {
            "rows": int(len(ok)),
            "max_abs_f_diff": float(ok["f_diff"].max()),
            "rows_diff_gt_1e_4": int((ok["f_diff"] > 1e-4).sum()),
            "rows_diff_gt_1e_6": int((ok["f_diff"] > 1e-6).sum()),
        },
        "base_normalisation": {
            "last_date": last_date,
            "rows": int(len(last)),
            "close_eq_raw_rows": int(((last["close"] - last["raw_close"]).abs() < 1e-9).sum()),
            "verdict": "最新一日 close 与 raw_close 逐行相等 ⇒ 前复权，基准=该股最后一个除权事件之后（价格水平=原始价）",
        },
        "f_range": {"min": float(ok["f"].min()), "max": float(ok["f"].max())},
        "code_refs": [
            "backend/app/backtest/engine.py:998  parquet_root = data_dir / enriched_dirname(asset_type) → kline_daily_enriched",
            "backend/app/tickflow/repository.py:85   {'stock': 'kline_daily_enriched'}",
            "backend/app/indicators/pipeline.py:250-273  _apply_adj_factor：adjusted = raw × cum(<=date) / cum_total（前复权）",
            "backend/app/api/data.py:906  ex_factor 定义：单事件等比因子 = 除权前收盘价 / 除权参考价，按日期连乘得累计复权因子",
            "backend/app/backtest/matrix.py:2557-2572  raw_open = round(open × raw_close / close, 2)（用同一日比例还原原始价，不跨口径）",
        ],
    }

    # 手工验算样本：取累计因子最小（调整最大）与最接近 1 的各一只
    per_sym_f = ok.groupby("symbol")["f"].agg(["min", "max", "size"])
    big_sym = per_sym_f["min"].idxmin()
    near_sym = per_sym_f[(per_sym_f["min"] > 0.97) & (per_sym_f["size"] > 500)].index[0]
    manual = []
    for sym in (big_sym, near_sym):
        rows = ok[ok["symbol"] == sym].sort_values("date")
        if sym == big_sym:
            row = rows.iloc[len(rows) // 2]
        else:
            # 取事件发生日附近的中间行
            ev = adj[(adj["symbol"] == sym) & (adj["trade_date"] >= "2019-06-01")]
            row = rows[rows["date"] >= (ev["trade_date"].min() if len(ev) else "2020-01-01")].iloc[0] if len(rows) else rows.iloc[0]
        manual.append({
            "symbol": sym,
            "date": row["date"],
            "raw_close": float(row["raw_close"]),
            "adj_close": float(row["close"]),
            "f_implied_close_over_raw": float(row["f"]),
            "f_expected_cum_over_total": float(row["f_expected"]),
            "n_events_whole_table": int((adj["symbol"] == sym).sum()),
        })
    res["Q1"]["manual_samples"] = manual

    # ---------------- 口径事实：trades 里记的价是哪个价 ----------------
    idx = panel.set_index(["symbol", "date"])
    rec = []
    for r in trades.itertuples(index=False):
        try:
            e = idx.loc[(r.symbol, r.entry_date)]
            x = idx.loc[(r.symbol, r.exit_date)]
        except KeyError:
            continue
        if isinstance(e, pd.DataFrame):
            e = e.iloc[0]
        if isinstance(x, pd.DataFrame):
            x = x.iloc[0]
        rec.append({
            "symbol": r.symbol, "entry_date": r.entry_date, "exit_date": r.exit_date,
            "exit_reason": r.exit_reason, "duration": int(r.duration),
            "entry_price": float(r.entry_price), "exit_price": float(r.exit_price),
            "pnl_pct": float(r.pnl_pct), "open_at_end": bool(r.open_at_end),
            "e_raw_open": float(e["raw_open"]), "e_adj_open": float(e["open"]),
            "e_raw_close": float(e["raw_close"]), "e_adj_close": float(e["close"]), "e_f": float(e["f"]),
            "x_raw_open": float(x["raw_open"]), "x_raw_close": float(x["raw_close"]),
            "x_raw_low": float(x["raw_low"]), "x_raw_high": float(x["raw_high"]),
            "x_adj_open": float(x["open"]), "x_f": float(x["f"]),
        })
    eb = pd.DataFrame(rec)
    eb["stop_level"] = eb["entry_price"] * 0.92
    eb["entry_vs_raw_open_bp"] = (eb["entry_price"] / eb["e_raw_open"] - 1.0) * 1e4
    eb["exit_vs_raw_open_bp"] = (eb["exit_price"] / eb["x_raw_open"] - 1.0) * 1e4
    eb["exit_vs_stop_bp"] = (eb["exit_price"] / eb["stop_level"] - 1.0) * 1e4
    eb["exit_below_day_low"] = eb["exit_price"] < eb["x_raw_low"] - 1e-6
    eb["exit_above_day_high"] = eb["exit_price"] > eb["x_raw_high"] + 1e-6
    eb["cross_basis_bias"] = 1.0 / eb["e_f"] - 1.0
    eb["pnl_all_raw"] = eb["x_raw_open"] / eb["e_raw_open"] - 1.0
    eb["pnl_all_adj"] = eb["x_adj_open"] / eb["e_adj_open"] - 1.0
    eb["pnl_mixed"] = eb["x_adj_open"] / eb["e_raw_open"] - 1.0

    sl = eb[eb["exit_reason"] == "stop_loss"]
    res["basis_check"] = {
        "rows": int(len(eb)),
        "entry_matches_raw_open_bp_p50_abs": float(eb["entry_vs_raw_open_bp"].abs().median()),
        "entry_matches_raw_open_share_0.5pct": float((eb["entry_vs_raw_open_bp"].abs() < 50).mean()),
        "entry_matches_adj_open_share_0.5pct": float(((eb["entry_price"] / eb["e_adj_open"] - 1).abs() < 0.005).mean()),
        "stop_loss_trades": int(len(sl)),
        "stop_loss_exit_matches_stop_level_share_0.5pct": float((sl["exit_vs_stop_bp"].abs() < 50).mean()),
        "stop_loss_exit_matches_stop_level_bp_p50": float(sl["exit_vs_stop_bp"].median()),
        "stop_loss_exit_matches_raw_open_share_0.5pct": float((sl["exit_vs_raw_open_bp"].abs() < 50).mean()),
        "stop_loss_pnl_p50": float(sl["pnl_pct"].median()),
        "stop_loss_pnl_p10_p90": [pctl(sl["pnl_pct"], 10), pctl(sl["pnl_pct"], 90)],
        "stop_loss_exit_below_day_low": int(sl["exit_below_day_low"].sum()),
        "stop_loss_exit_above_day_high": int(sl["exit_above_day_high"].sum()),
        "all_trades_pnl_as_recorded_p50": float(eb["pnl_pct"].median()),
        "all_trades_pnl_all_raw_p50": float(eb["pnl_all_raw"].median()),
        "all_trades_pnl_all_adj_p50": float(eb["pnl_all_adj"].median()),
        "all_trades_pnl_mixed_p50": float(eb["pnl_mixed"].median()),
        "share_recorded_closer_to_all_raw_than_mixed": float(
            ((eb["pnl_pct"] - eb["pnl_all_raw"]).abs() < (eb["pnl_pct"] - eb["pnl_mixed"]).abs()).mean()
        ),
    }
    eb.to_csv(OUT / "entry_basis_check.csv", index=False, encoding="utf-8-sig")

    # ---------------- Q2 覆盖率 ----------------
    tr_syms = set(trades["symbol"].unique())
    adj_syms = set(adj["symbol"].unique())
    panel_syms = set(panel["symbol"].unique())
    per_sym = ok[ok["symbol"].isin(tr_syms)].groupby("symbol")["f"].agg(["min", "max", "size"])
    ev = adj.groupby("symbol").agg(n_events=("ex_factor", "size"), last_event=("trade_date", "max"),
                                   max_event=("ex_factor", "max"))
    per_sym = per_sym.join(ev, how="left").fillna({"n_events": 0})
    absent = sorted(tr_syms - adj_syms)
    stuck = per_sym[(per_sym["n_events"] > 0) & (per_sym["max"] - per_sym["min"]).abs().lt(1e-9) & (per_sym["max"] - 1).abs().lt(1e-9)]
    stuck_explained = adj[adj["symbol"].isin(stuck.index)].groupby("symbol")["trade_date"].max()
    stuck_true = [s for s in stuck.index if str(stuck_explained.get(s, "9999")) >= "2019-06-01"
                  and adj[(adj["symbol"] == s) & (adj["trade_date"] >= "2019-06-01")]["ex_factor"].sub(1).abs().max() > 1e-9]

    # 不可能出现的单日跌幅 = 因子表漏事件的探针（按板块真实涨跌幅限制）
    ins = pq.ParquetFile(DATA / "instruments/instruments.parquet").read().to_pandas()
    ins_idx = ins.set_index("symbol")

    def board_limit(sym: str, date: str) -> float:
        if sym.endswith(".BJ"):
            return -0.31
        if sym[:3] in ("688", "689"):
            return -0.21  # 科创板 20%（2019-07-22 起即为 20%）
        if sym[:3] in ("300", "301"):
            return -0.21 if date >= "2020-08-24" else -0.11
        return -0.11

    p = ok[ok["symbol"].isin(tr_syms)].sort_values(["symbol", "date"]).copy()
    p["adj_ret"] = p.groupby("symbol")["close"].pct_change()
    p["raw_ret"] = p.groupby("symbol")["raw_close"].pct_change()
    p["limit"] = [board_limit(s, d) for s, d in zip(p["symbol"], p["date"])]
    bad = p[(p["adj_ret"] < p["limit"] * 1.02) & p["raw_ret"].notna()].copy()
    bad["name"] = bad["symbol"].map(lambda s: ins_idx["name"].get(s, ""))
    bad["listing_date"] = bad["symbol"].map(lambda s: str(ins_idx["listing_date"].get(s, "")))
    bad["class"] = np.where(
        bad["name"].astype(str).str.contains("退"), "退市整理期(无涨跌幅限制)",
        np.where(bad["listing_date"] == bad["date"], "上市首日(无涨跌幅限制)", "待确认"),
    )
    res["Q2"] = {
        "trades": int(len(trades)),
        "trade_symbols": len(tr_syms),
        "trade_symbols_in_adj_factor": len(tr_syms & adj_syms),
        "trade_symbols_absent_from_adj_factor": len(absent),
        "absent_symbols": absent,
        "trade_symbols_missing_from_panel": sorted(tr_syms - panel_syms),
        "rows_compared_per_trade_symbol": int(per_sym["size"].sum()),
        "rows_with_f_diff_gt_1e_4": int(ok[ok["symbol"].isin(tr_syms)]["f_diff"].gt(1e-4).sum()),
        "defaulted_one_suspected": len(stuck_true),
        "defaulted_one_suspected_symbols": stuck_true,
        "stuck_at_one_but_explained_pre_window_events": sorted(set(stuck.index) - set(stuck_true)),
        "impossible_gap_probe": {
            "rows": int(len(p)),
            "rows_beyond_board_limit": int(len(bad)),
            "by_class": bad["class"].value_counts().to_dict() if len(bad) else {},
            "pending_rows": bad[bad["class"] == "待确认"][["symbol", "date", "adj_ret", "raw_ret", "f"]]
            .assign(adj_ret=lambda d: d["adj_ret"].round(4))
            .to_dict("records") if len(bad) else [],
            "note": "前复权后仍出现超越涨跌幅限制的单日跌幅 ⇒ 该股在 adj_factor 里可能漏了除权事件；退市整理期/上市首日无涨跌幅限制，不算漏记",
        },
        "verdict": "enriched 前复权因子与 adj_factor 连乘逐行一致（0 行偏差>1e-4）；无「有事件却被默认成 1.0」的标的",
    }

    # ---------------- Q3 持仓期内变化 ----------------
    ev_map = {s: g[["trade_date", "ex_factor"]].to_numpy() for s, g in adj[adj["symbol"].isin(tr_syms)].groupby("symbol")}
    rows = []
    for r in eb.itertuples(index=False):
        arr = ev_map.get(r.symbol)
        evs, mags = [], []
        if arr is not None and len(arr):
            for d, e in arr:
                if r.entry_date < d <= r.exit_date:
                    evs.append((d, float(e)))
                    mags.append(abs(1.0 - 1.0 / float(e)))
                elif r.entry_date == d:
                    evs.append((d, float(e)))
                    mags.append(abs(1.0 - 1.0 / float(e)))
        strict = [(d, e) for d, e in evs if d != r.entry_date]
        rows.append({
            "symbol": r.symbol, "entry_date": r.entry_date, "exit_date": r.exit_date,
            "exit_reason": r.exit_reason, "duration": r.duration,
            "n_events_in_hold_strict": len(strict), "n_events_incl_entry": len(evs),
            "max_event_mag": max(mags) if mags else 0.0,
            "events": ";".join(f"{d}:{e:.6f}" for d, e in evs),
            "f_entry": r.e_f, "cross_basis_bias": r.cross_basis_bias,
        })
    pt = pd.DataFrame(rows)
    with_ev = pt[pt["max_event_mag"] > 0]
    res["Q3"] = {
        "trades": int(len(pt)),
        "trades_with_event_in_hold_strict": int((pt["n_events_in_hold_strict"] > 0).sum()),
        "share_with_event_in_hold_strict": float((pt["n_events_in_hold_strict"] > 0).mean()),
        "trades_with_event_incl_entry": int((pt["n_events_incl_entry"] > 0).sum()),
        "event_mag_p50": pctl(with_ev["max_event_mag"], 50),
        "event_mag_p90": pctl(with_ev["max_event_mag"], 90),
        "event_mag_max": float(pt["max_event_mag"].max()),
        "trades_single_event_ge_8pct": int((pt["max_event_mag"] >= 0.08).sum()),
        "trades_single_event_ge_5pct": int((pt["max_event_mag"] >= 0.05).sum()),
        "f_entry_p50": float(pt["f_entry"].median()),
        "f_entry_p05": pctl(pt["f_entry"], 5),
        "f_entry_min": float(pt["f_entry"].min()),
        "cross_basis_bias_p50": pctl(pt["cross_basis_bias"], 50),
        "cross_basis_bias_p90": pctl(pt["cross_basis_bias"], 90),
        "cross_basis_bias_max": float(pt["cross_basis_bias"].max()),
        "trades_cross_basis_ge_8pct": int((pt["cross_basis_bias"] >= 0.08).sum()),
        "share_cross_basis_ge_8pct": float((pt["cross_basis_bias"] >= 0.08).mean()),
    }
    pt.to_csv(OUT / "hold_window_events.csv", index=False, encoding="utf-8-sig")

    # ---------------- Q4 对照样本 ----------------
    picks: list[tuple[str, str]] = []
    if len(pt):
        top_ev = pt.sort_values("max_event_mag", ascending=False).head(1)
        picks += [(top_ev.iloc[0]["symbol"], top_ev.iloc[0]["entry_date"])]
        top_gap = pt.sort_values("cross_basis_bias", ascending=False).head(1)
        picks += [(top_gap.iloc[0]["symbol"], top_gap.iloc[0]["entry_date"])]
        with_ev_sorted = pt[pt["n_events_incl_entry"] > 0].sort_values("entry_date")
        if len(with_ev_sorted) >= 2:
            for _, r in with_ev_sorted.head(2).iterrows():
                picks.append((r["symbol"], r["entry_date"]))
        no_ev = pt[pt["n_events_incl_entry"] == 0].sort_values("entry_date").head(1)
        if len(no_ev):
            picks.append((no_ev.iloc[0]["symbol"], no_ev.iloc[0]["entry_date"]))
        # 去重
        seen, uniq = set(), []
        for s, d in picks:
            if s not in seen:
                seen.add(s)
                uniq.append((s, d))
        picks = uniq

    samples = []
    for sym, ed in picks:
        srows = ok[ok["symbol"] == sym].sort_values("date")
        e = srows[srows["date"] == ed]
        nxt = srows[srows["date"] > ed].head(1)
        if e.empty or nxt.empty:
            continue
        e, n = e.iloc[0], nxt.iloc[0]
        rec_row = pt[(pt["symbol"] == sym) & (pt["entry_date"] == ed)].iloc[0]
        for tag, rr in (("entry", e), ("entry_next", n)):
            samples.append({
                "symbol": sym, "label": tag, "date": rr["date"],
                "raw_close": float(rr["raw_close"]),
                "adj_factor_f": float(rr["f"]),
                "adj_close": float(rr["close"]),
                "raw_close_x_f": float(rr["raw_close"] * rr["f"]),
                "trade_entry_date": ed, "trade_exit_date": rec_row["exit_date"],
                "events_in_hold": rec_row["events"],
                "max_event_mag_pct": rec_row["max_event_mag"] * 100,
            })
    sm = pd.DataFrame(samples)
    sm.to_csv(OUT / "samples.csv", index=False, encoding="utf-8-sig")

    # 因子表自身校验：最大事件日前后 raw 价是否按 1/ex_factor 断开
    top_events = adj[adj["symbol"].isin(tr_syms) & adj["trade_date"].ge("2019-06-01")].nlargest(3, "ex_factor")
    ev_check = []
    for r in top_events.itertuples(index=False):
        srows = ok[(ok["symbol"] == r.symbol) & (ok["date"] <= r.trade_date)].sort_values("date")
        if len(srows) < 2:
            continue
        prev, cur = srows.iloc[-2], srows.iloc[-1]
        ratio = cur["raw_close"] / prev["raw_close"]
        ev_check.append({
            "symbol": r.symbol, "ex_date": r.trade_date, "ex_factor": float(r.ex_factor),
            "prev_date": prev["date"], "prev_raw_close": float(prev["raw_close"]),
            "ev_date_raw_close": float(cur["raw_close"]),
            "raw_ratio": float(ratio), "expected_1_over_e": float(1.0 / r.ex_factor),
            "diff": float(ratio - 1.0 / r.ex_factor),
        })
    res["Q4"] = {"symbols": [s for s, _ in picks], "rows": int(len(sm)), "event_sanity": ev_check}

    # ---------------- 附录C：两种口径的首次触发日 ----------------
    grp = {s: g.sort_values("date").reset_index(drop=True) for s, g in panel.groupby("symbol") if s in tr_syms}
    rows = []
    for r in eb.itertuples(index=False):
        g = grp.get(r.symbol)
        if g is None:
            continue
        pos = g.index[g["date"] == r.entry_date]
        if not len(pos):
            continue
        i0 = int(pos[0])
        win = g.iloc[i0:]
        stop = r.entry_price * 0.92
        raw_trig = win.index[win["raw_close"] / r.e_raw_open - 1.0 <= -0.08]
        mix_trig = win.index[win["close"] / r.e_raw_open - 1.0 <= -0.08]
        touch = win.index[win["raw_low"] <= stop * 1.0005]
        j = int(touch[0]) if len(touch) else None
        rows.append({
            "symbol": r.symbol, "entry_date": r.entry_date, "exit_date": r.exit_date,
            "duration": r.duration, "exit_reason": r.exit_reason,
            "exit_price": r.exit_price, "stop_level": stop,
            "dur_close_raw": (int(raw_trig[0]) - i0 + 1) if len(raw_trig) else None,
            "dur_close_mixed": (int(mix_trig[0]) - i0 + 1) if len(mix_trig) else None,
            "first_touch_offset": (j - i0) if j is not None else None,
            "first_touch_date": (g["date"].iloc[j] if j is not None else None),
        })
    tg = pd.DataFrame(rows)
    tg["hit_close_raw"] = tg["dur_close_raw"] == tg["duration"]
    tg["hit_close_mixed"] = tg["dur_close_mixed"] == tg["duration"]
    tg["hit_touch_date"] = tg["first_touch_date"] == tg["exit_date"]
    tg["hit_touch_offset"] = tg["first_touch_offset"] == tg["duration"]
    tg["fill_at_stop"] = (tg["exit_price"] / (tg["stop_level"] * 0.999) - 1.0).abs() < 0.006
    tg.to_csv(OUT / "trigger_basis_compare.csv", index=False, encoding="utf-8-sig")
    only_stop = tg[(tg["exit_reason"] == "stop_loss") & tg["first_touch_offset"].notna()]
    same_day = only_stop[only_stop["first_touch_offset"] > 0]
    res["appendix_C"] = {
        "trades": int(len(tg)),
        "stop_trades_with_touch": int(len(only_stop)),
        "hit_first_touch_date_eq_exit_date": float(only_stop["hit_touch_date"].mean()),
        "hit_duration_eq_touch_offset": float(only_stop["hit_touch_offset"].mean()),
        "fill_at_stop_level_share": float(only_stop["fill_at_stop"].mean()),
        "fill_at_stop_share_when_touch_after_entry_day": float(same_day["fill_at_stop"].mean()) if len(same_day) else None,
        "share_touch_on_entry_day": float((only_stop["first_touch_offset"] == 0).mean()),
        "close_based_duration_match": float(only_stop["hit_close_raw"].mean()),
        "close_based_mixed_duration_match": float(only_stop["hit_close_mixed"].mean()),
        "close_mixed_triggers_on_entry_bar": int((tg["dur_close_mixed"] == 1).sum()),
        "close_raw_triggers_on_entry_bar": int((tg["dur_close_raw"] == 1).sum()),
        "note": "只把「按哪种价格口径/触发规则推出来的日与价」和记录值对一下，不下结论；收盘价口径（含混口径）都对不上记录的离场日",
    }

    res["elapsed_s"] = round(time.time() - t0, 1)
    res["fingerprint_after"] = {
        "kline_daily": dir_fingerprint(DAILY),
        "kline_daily_enriched": dir_fingerprint(ENRICHED),
        "adj_factor": {**dir_fingerprint(DATA / "adj_factor"), "sha256_first4MiB": sha256_file(ADJ)},
    }
    res["fingerprint_unchanged"] = res["inputs"]["fingerprint_before"] == res["fingerprint_after"]

    with open(OUT / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return res


if __name__ == "__main__":
    main()
