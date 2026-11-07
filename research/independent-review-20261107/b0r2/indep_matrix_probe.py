"""矩阵路径真实覆盖实测 — 用真实 MarketDataMatrix 调 matrix_feature。

上一版只看 _MATRIX_COMPUTED_FEATURES 静态表，漏了 matrix_feature() 的动态规则
(ma*, ema*, rsi_*, momentum_*) 与 provider 分支 (matrix.py:4207-4214)。本文件逐名实调。
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
IDS = ["ma20", "ma60", "ma120", "ma200", "boll_lower", "boll_upper", "sd20",
       "vol60", "prior_high_20", "prior_high_55", "prior_high_250",
       "prior_low_10", "prior_vol_20", "prior_amount_20"]


def rec(s, **kv):
    OUT.setdefault(s, {}).update(kv)
    print(f"[{s}] " + " ".join(f"{k}={v}" for k, v in kv.items()), flush=True)


def build_matrix():
    from app.backtest.matrix import build_market_matrix
    from app.config import settings
    from app.extensions.adapters import FileMarketData

    f = FileMarketData(settings.data_dir).get_daily_batch(
        ["600000.SH", "000001.SZ", "600519.SH", "000002.SZ", "600036.SH"],
        date(2024, 1, 2), date(2026, 6, 30), BASE)
    f = f.sort(["symbol", "date"])
    print(f"[frame] rows={f.height} symbols={f['symbol'].n_unique()}", flush=True)
    import inspect
    print("[sig]", str(inspect.signature(build_market_matrix))[:300], flush=True)
    return f, build_market_matrix


def probe(f, builder):
    from app.backtest.matrix import matrix_feature
    import inspect

    # 尝试用 frame 直接构造；签名不符则退回 build_market_data_matrix
    sig = inspect.signature(builder)
    params = list(sig.parameters)
    print("[params]", params, flush=True)
    market = None
    for call in (
        lambda: builder(f),
        lambda: builder(frame=f),
        lambda: builder(f, None),
    ):
        try:
            market = call()
            break
        except Exception as e:  # noqa: BLE001
            print(f"[build-try-fail] {type(e).__name__}: {str(e)[:160]}", flush=True)
    if market is None:
        from app.backtest.matrix import build_market_data_matrix
        print("[fallback] build_market_data_matrix", flush=True)
        market = build_market_data_matrix(f)
    print(f"[market] shape={market.shape} dtype={market.close.dtype}", flush=True)

    res = {}
    for n in IDS:
        try:
            v = matrix_feature(market, n)
            arr = np.asarray(v)
            finite = int(np.isfinite(arr).sum())
            res[n] = {"ok": True, "dtype": str(arr.dtype), "finite": finite,
                      "shape": list(arr.shape)}
        except Exception as e:  # noqa: BLE001
            res[n] = {"ok": False, "err": f"{type(e).__name__}: {str(e)[:120]}"}
        print(f"  {n:16s} {res[n]}", flush=True)
    ok = [k for k, v in res.items() if v["ok"]]
    rec("matrix_feature_probe", close_dtype=str(market.close.dtype),
        covered=ok, n_covered=len(ok), n_total=len(res),
        failed=[k for k, v in res.items() if not v["ok"]], detail=res)
    return market, res


def fidelity_vs_panel(market, res):
    """矩阵值 vs 面板值（float64）差 — 给 F-A11 容差判断提供实测。"""
    from app.config import settings
    from app.extensions.adapters import FileMarketData
    from app.backtest.matrix import matrix_feature
    from app.strategy.scoring import materialize_scoring_columns

    okids = [k for k, v in res.items() if v["ok"]]
    if not okids:
        rec("matrix_vs_panel", skipped="no covered ids")
        return
    f = FileMarketData(settings.data_dir).get_daily_batch(
        ["600000.SH", "000001.SZ", "600519.SH", "000002.SZ", "600036.SH"],
        date(2024, 1, 2), date(2026, 6, 30), BASE).sort(["symbol", "date"])
    # 面板顺序与矩阵一致: 按 date 外层、symbol 内层
    panel = materialize_scoring_columns(f.select(BASE), okids)
    syms = list(market.symbols)
    dates = list(market.timestamp_labels)

    detail = {}
    for n in okids:
        mat = np.asarray(matrix_feature(market, n), dtype=np.float64)
        # 面板透视到 (T, N)
        piv = panel.pivot(on="symbol", index="date", values=n)
        piv = piv.with_columns(pl.col("date").cast(pl.Utf8))
        pl_idx = [str(d)[:10] for d in piv["date"].to_list()]
        row = {s: piv[s].to_list() for s in piv.columns if s != "date"}
        mism = 0
        mx = 0.0
        nb = 0
        for i, dl in enumerate(dates):
            key = str(dl)[:10]
            if key not in pl_idx:
                continue
            r = pl_idx.index(key)
            for j, s in enumerate(syms):
                if s not in row:
                    continue
                pv = row[s][r]
                mv = mat[i, j] if i < mat.shape[0] and j < mat.shape[1] else np.nan
                if pv is None or not np.isfinite(pv) or not np.isfinite(mv):
                    continue
                nb += 1
                d = abs(pv - mv)
                mx = max(mx, d)
                if d > 0:
                    mism += 1
        detail[n] = {"n_both": nb, "max_abs_diff": mx, "n_diff": mism,
                     "within_1e-10": bool(mx < 1e-10),
                     "within_f32_eps": bool(mx < 2 ** -23 * max(1.0, 1.0))}
        print(f"  [fid] {n:14s} n={nb} max={mx:.3e} diff_rows={mism}", flush=True)
    rec("matrix_vs_panel", detail=detail)


def main():
    t0 = time.perf_counter()
    f, builder = build_matrix()
    market, res = probe(f, builder)
    fidelity_vs_panel(market, res)
    OUT["elapsed_s"] = round(time.perf_counter() - t0, 1)
    OUT["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    p = Path(__file__).with_suffix(".json")
    p.write_text(json.dumps(OUT, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[done] -> {p}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
