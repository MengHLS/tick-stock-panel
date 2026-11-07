"""独立核 F-A11a-d 判别力 — 用真实面板数据构造 float32 矩阵核, 再构造漏 shift(1) 的错误核,
检查 v0.7 §7.14 的分层判据能否区分「float32 量化噪声」与「语义错」。

不调用 matrix_feature(sd20/prior_*/vol60 在矩阵路径尚不可算), 而是按 v0.7 §7.13 的口径
自己实现「正确核」与「错误核」, 二者都输出 float32 TxN, 与面板 float64 比较。
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

from app.config import settings
from app.extensions.adapters import FileMarketData
from app.strategy.scoring import materialize_scoring_columns

BASE = ["symbol", "date", "open", "high", "low", "close", "volume", "amount"]
EPS32_REL = 2.0 ** -23  # 1.1920929e-07


def rolling(a: np.ndarray, w: int, fn: str, *, shift1: bool) -> np.ndarray:
    """对 TxN float32 数组按列做 trailing 窗口; 返回 float64 供比较。"""
    T, N = a.shape
    out = np.full((T, N), np.nan, dtype=np.float64)
    src = np.vstack([np.full((1, N), np.nan), a[:-1]]) if shift1 else a
    for j in range(N):
        col = src[:, j].astype(np.float64)
        for i in range(w - 1, T):
            win = col[i - w + 1:i + 1]
            if np.isnan(win).any():
                continue
            if fn == "mean":
                out[i, j] = win.mean()
            elif fn == "std":
                out[i, j] = win.std(ddof=1)
            elif fn == "max":
                out[i, j] = win.max()
            elif fn == "min":
                out[i, j] = win.min()
    return out


def main() -> int:
    t0 = time.perf_counter()
    m = FileMarketData(settings.data_dir)
    f = m.get_daily_batch([], date(2018, 1, 8), date(2026, 10, 30), BASE)
    f = f.filter(
        pl.col("symbol").str.starts_with("60") | pl.col("symbol").str.starts_with("00")
    )
    syms = sorted(f["symbol"].unique().to_list())
    picks = syms[::max(1, len(syms) // 6)][:6]
    f = f.filter(pl.col("symbol").is_in(picks)).sort(["symbol", "date"])
    ev = (f["date"] >= date(2019, 7, 1)) & (f["date"] <= date(2026, 10, 30))
    f = f.filter(ev)
    keep = np.ones(f.height, dtype=bool)

    # 面板权威值 (float64)
    panel = materialize_scoring_columns(f.select(BASE), ["sd20", "prior_high_20", "vol60"])

    # 每只股票各自成列 -> TxN (这里按 symbol 分块处理, 每个 symbol 一路列)
    res = {}
    for fid in ("sd20", "prior_high_20", "vol60"):
        p_all, c_all, w_all = [], [], []
        for sym in picks:
            sub = f.filter(pl.col("symbol") == sym).sort("date")
            if sub.height < 300:
                continue
            T = sub.height
            close = sub["close"].to_numpy().astype(np.float32).reshape(T, 1)
            high = sub["high"].to_numpy().astype(np.float32).reshape(T, 1)
            pv = panel.filter(pl.col("symbol") == sym).sort("date")[fid]
            p = pl.Series(pv).cast(pl.Float64).fill_nan(None).to_numpy().reshape(T, 1)
            if fid == "sd20":
                good = rolling(close, 20, "std", shift1=False)
                bad = rolling(close, 20, "std", shift1=True)
            elif fid == "prior_high_20":
                good = rolling(high, 20, "max", shift1=True)
                bad = rolling(high, 20, "max", shift1=False)   # 漏 shift(1)
            else:  # vol60
                r = np.full_like(close, np.nan, dtype=np.float32)
                r[1:] = (close[1:] - close[:-1]) / close[:-1]
                good = rolling(r, 60, "std", shift1=False)
                bad = rolling(close, 60, "std", shift1=False)   # 语义错: 用价格标准差
            # float32 量化 (模拟矩阵存储)
            g32 = good.astype(np.float32).astype(np.float64)
            b32 = bad.astype(np.float32).astype(np.float64)
            p_all.append(p); c_all.append(g32); w_all.append(b32)
        P = np.vstack(p_all); C = np.vstack(c_all); W = np.vstack(w_all)

        def judge(M: np.ndarray, label: str) -> dict:
            fp = np.isfinite(P); fm = np.isfinite(M)
            struct_sym = int((fp ^ fm).sum())          # F-A11a 对称差
            both = fp & fm
            diff = np.abs(P[both] - M[both])
            rel = diff / np.maximum(np.abs(P[both]), 1e-12)
            max_rel = float(rel.max()) if rel.size else 0.0
            max_abs = float(diff.max()) if diff.size else 0.0
            col_max_p = float(np.abs(P[both]).max()) if both.any() else 0.0
            a11b = bool(max_rel <= EPS32_REL and max_abs <= EPS32_REL * col_max_p)
            # F-A11c 决策等价: close >= prior_high_20 / vol60 <= 0.10 型谓词
            # 用统一谓词: 值 >= 其中位数 作为代表谓词
            thr = np.nanmedian(P)
            dp = np.nan_to_num(P, nan=-np.inf) >= thr
            dm = np.nan_to_num(M, nan=-np.inf) >= thr
            inter = int((dp & dm).sum()); union = int((dp | dm).sum())
            jac = inter / union if union else 1.0
            flip = int((dp != dm).sum())
            a11c = bool(jac >= 0.9999 and flip == 0)
            return {
                "label": label,
                "a11a_struct_symdiff": struct_sym,
                "max_abs_diff": max_abs,
                "max_rel_diff": max_rel,
                "a11b_pass": a11b,
                "a11c_jaccard": jac,
                "a11c_flips": flip,
                "a11c_pass": a11c,
            }

        res[fid] = {"rows": int(P.size), "correct_kernel": judge(C, "correct-float32"),
                    "wrong_kernel": judge(W, "wrong-semantics")}
        ck, wk = res[fid]["correct_kernel"], res[fid]["wrong_kernel"]
        print(f"{fid:16s} correct: struct={ck['a11a_struct_symdiff']} "
              f"rel={ck['max_rel_diff']:.3g} a11b={ck['a11b_pass']} "
              f"jac={ck['a11c_jaccard']:.6f} flips={ck['a11c_flips']}", flush=True)
        print(f"{'':16s} wrong  : struct={wk['a11a_struct_symdiff']} "
              f"rel={wk['max_rel_diff']:.3g} a11b={wk['a11b_pass']} "
              f"jac={wk['a11c_jaccard']:.6f} flips={wk['a11c_flips']}", flush=True)

    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "eps32_rel": EPS32_REL, "symbols": picks, "results": res,
           "elapsed_s": round(time.perf_counter() - t0, 1)}
    p = Path(__file__).with_suffix(".json")
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {p} ({out['elapsed_s']}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
