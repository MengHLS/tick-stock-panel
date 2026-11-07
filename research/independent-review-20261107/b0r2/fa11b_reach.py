"""F-A11b 容差可达性裁决 — 用真实 matrix_feature 输出算相对误差。

v0.7 §7.14.4 F-A11b: 逐列 rel = max|p-m| / max(|p|, 1e-12) <= 2^-23 = 1.192e-07
v0.7 §7.14.2 表只算了「同一 float64 值存成 float32」的单次舍入下界（5.96e-08）。
本文件算的是**真实矩阵核路径**（float32 输入 + float32 累加）的相对误差。
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(PROJECT / "backend"))

import numpy as np
import polars as pl

OUT: dict = {}
BASE = ["symbol", "date", "open", "high", "low", "close", "volume", "amount"]
EPS23 = 2.0 ** -23
EPS24 = 2.0 ** -24


def rec(s, **kv):
    OUT.setdefault(s, {}).update(kv)
    print(f"[{s}] " + " ".join(f"{k}={v}" for k, v in kv.items()), flush=True)


def main() -> int:
    from app.backtest.matrix import build_market_data_matrix, matrix_feature
    from app.config import settings
    from app.extensions.adapters import FileMarketData
    from app.strategy.scoring import materialize_scoring_columns

    ids = ["ma20", "ma60", "ma120", "ma200", "boll_lower", "boll_upper"]
    f = FileMarketData(settings.data_dir).get_daily_batch(
        ["600000.SH", "000001.SZ", "600519.SH", "000002.SZ", "600036.SH",
         "000651.SZ", "600276.SH", "002415.SZ"],
        date(2023, 1, 3), date(2026, 6, 30), BASE).sort(["symbol", "date"])
    market = build_market_data_matrix(f)
    print(f"[market] shape={market.shape} close_dtype={market.close.dtype}", flush=True)

    panel = materialize_scoring_columns(f.select(BASE), ids)
    syms = list(market.symbols)
    dates = [str(x)[:10] for x in market.timestamp_labels]

    # 每因子单独做 pivot（多 values 会出多级列名）
    daymap, cols = {}, {}
    for fid in ids:
        piv = panel.select(["date", "symbol", fid]).pivot(
            on="symbol", index="date", values=fid)
        piv = piv.with_columns(pl.col("date").cast(pl.Utf8).str.slice(0, 10))
        if not daymap:
            daymap = {d: i for i, d in enumerate(piv["date"].to_list())}
            symcols = [c for c in piv.columns if c != "date"]
        cols[fid] = {c: piv[c].to_list() for c in piv.columns if c != "date"}

    detail = {}
    for fid in ids:
        mat = np.asarray(matrix_feature(market, fid), dtype=np.float64)
        P, M = [], []
        for i, dl in enumerate(dates):
            if dl not in daymap:
                continue
            r = daymap[dl]
            for j, s in enumerate(syms):
                if s not in cols[fid]:
                    continue
                pv = cols[fid][s][r]
                mv = mat[i, j] if i < mat.shape[0] and j < mat.shape[1] else np.nan
                if pv is None or not np.isfinite(pv) or not np.isfinite(mv):
                    continue
                P.append(pv); M.append(mv)
        P = np.asarray(P); M = np.asarray(M)
        d = np.abs(P - M)
        rel = d / np.maximum(np.abs(P), 1e-12)
        max_rel = float(rel.max())
        col_max = float(np.abs(P).max())
        # F-A11b 两条并列断言
        ok_rel = max_rel <= EPS23
        ok_abs = float(d.max()) <= EPS23 * col_max
        detail[fid] = {
            "n": int(P.size), "max_abs": float(d.max()), "max_rel": max_rel,
            "col_max_abs": col_max,
            "eps23": EPS23, "eps24": EPS24,
            "rel_x_eps23": max_rel / EPS23,
            "over_eps23": max_rel > EPS23,
            "over_eps24": max_rel > EPS24,
            "a11b_pass": bool(ok_rel and ok_abs),
            "a11b_ok_rel": ok_rel, "a11b_ok_abs": ok_abs,
        }
        print(f"  {fid:12s} n={P.size:6d} max_abs={d.max():.3e} max_rel={max_rel:.3e} "
              f"= {max_rel/EPS23:.1f}x eps23  a11b={ok_rel and ok_abs}", flush=True)

    rec("a11b_reachability", eps23=EPS23, detail=detail,
        all_pass=all(v["a11b_pass"] for v in detail.values()),
        worst_rel=max(v["max_rel"] for v in detail.values()),
        worst_multiple=max(v["rel_x_eps23"] for v in detail.values()),
        verdict=("PASS" if all(v["a11b_pass"] for v in detail.values()) else "FAIL"))

    # 判别力: 漏 shift(1) 的 prior_high_20 语义错（对已覆盖 id 无法直接构造，
    # 用 ma20 的「错窗口」近似：用 19 日窗冒充 20 日）+ 正确核对照
    mis = np.asarray(matrix_feature(market, "ma20"), dtype=np.float64)
    try:
        wrong = np.asarray(
            matrix_feature(market, "ma19"), dtype=np.float64)  # 窗口错 1 天
        P2, W2, M2 = [], [], []
        for i, dl in enumerate(dates):
            if dl not in daymap:
                continue
            r = daymap[dl]
            for j, s in enumerate(syms):
                if s not in cols["ma20"]:
                    continue
                pv = cols["ma20"][s][r]
                if pv is None or not np.isfinite(pv):
                    continue
                mv = mis[i, j]; wv = wrong[i, j]
                if not np.isfinite(mv) or not np.isfinite(wv):
                    continue
                P2.append(pv); M2.append(mv); W2.append(wv)
        P2 = np.asarray(P2); M2 = np.asarray(M2); W2 = np.asarray(W2)
        thr = np.median(P2)
        flip_ok = int(((P2 >= thr) != (M2 >= thr)).sum())
        flip_bad = int(((P2 >= thr) != (W2 >= thr)).sum())
        rec("discrimination", predicate="value >= median",
            flips_correct_kernel=flip_ok, flips_wrong_window=flip_bad,
            catches_semantic_error=(flip_bad > 0))
    except Exception as e:  # noqa: BLE001
        rec("discrimination", skipped=f"{type(e).__name__}: {str(e)[:100]}")

    OUT["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    p = Path(__file__).with_suffix(".json")
    p.write_text(json.dumps(OUT, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[done] -> {p}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
