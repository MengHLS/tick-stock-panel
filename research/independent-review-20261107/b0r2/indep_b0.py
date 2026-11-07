"""独立复算 B0 —— 不使用作者的 verify_b0.py, 不复用其判据函数。

参考实现: 本文件内自写 polars 表达式 (与 research common.add_indicators 同口径但独立书写),
平台实现: app.strategy.scoring.materialize_scoring_columns (生产物化入口)。

输出 JSON -> 同目录 indep_b0.json
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
for extra in (PROJECT / "backend",):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import numpy as np
import polars as pl

from app.config import settings
from app.extensions.adapters import FileMarketData
from app.strategy.scoring import materialize_scoring_columns

EVAL_START = date(2019, 7, 1)
EVAL_END = date(2026, 10, 30)

FACTORS = [
    "ma20", "ma60", "boll_lower", "boll_upper", "sd20",
    "prior_high_20", "prior_low_10", "prior_high_55", "prior_vol_20",
    "ma120", "vol60", "prior_high_250", "prior_amount_20", "ma200",
]
BASE = ["symbol", "date", "open", "high", "low", "close", "volume", "amount"]


def ref_columns(f: pl.DataFrame) -> pl.DataFrame:
    """独立书写的参考口径 (trailing only, shift(1)=此前)。"""
    return f.with_columns(
        pl.col("close").rolling_mean(20).over("symbol").alias("r_ma20"),
        pl.col("close").rolling_mean(60).over("symbol").alias("r_ma60"),
        pl.col("close").rolling_mean(120).over("symbol").alias("r_ma120"),
        pl.col("close").rolling_mean(200).over("symbol").alias("r_ma200"),
        pl.col("close").rolling_std(20).over("symbol").alias("r_sd20"),
        pl.col("high").shift(1).rolling_max(20).over("symbol").alias("r_ph20"),
        pl.col("low").shift(1).rolling_min(10).over("symbol").alias("r_pl10"),
        pl.col("high").shift(1).rolling_max(55).over("symbol").alias("r_ph55"),
        pl.col("high").shift(1).rolling_max(250).over("symbol").alias("r_ph250"),
        pl.col("volume").shift(1).rolling_mean(20).over("symbol").alias("r_pv20"),
        pl.col("amount").shift(1).rolling_mean(20).over("symbol").alias("r_pa20"),
        # vol60: pct_change 的显式写法 (x - x.shift(1))/x.shift(1), 与 polars pct_change 同路径
        ((pl.col("close") - pl.col("close").shift(1)) / pl.col("close").shift(1))
        .rolling_std(60).over("symbol").alias("r_vol60"),
    ).with_columns(
        (pl.col("r_ma20") - 2 * pl.col("r_sd20")).alias("r_bb_lower"),
        (pl.col("r_ma20") + 2 * pl.col("r_sd20")).alias("r_bb_upper"),
    )


REF_MAP = {
    "ma20": "r_ma20", "ma60": "r_ma60", "ma120": "r_ma120", "ma200": "r_ma200",
    "sd20": "r_sd20", "boll_lower": "r_bb_lower", "boll_upper": "r_bb_upper",
    "prior_high_20": "r_ph20", "prior_low_10": "r_pl10", "prior_high_55": "r_ph55",
    "prior_high_250": "r_ph250", "prior_vol_20": "r_pv20",
    "prior_amount_20": "r_pa20", "vol60": "r_vol60",
}

WARMUP = {
    "ma20": 20, "ma60": 60, "ma120": 120, "ma200": 200, "sd20": 20,
    "boll_lower": 20, "boll_upper": 20,
    "prior_high_20": 21, "prior_low_10": 11, "prior_high_55": 56,
    "prior_high_250": 251, "prior_vol_20": 21, "prior_amount_20": 21,
    "vol60": 61,
}


def clean(s: pl.Series) -> pl.Series:
    return s.cast(pl.Float64).fill_nan(None)


def load_panel() -> pl.DataFrame:
    """与作者同一数据入口(同宇宙: 60/00 主板, 同窗口), 但参考值由本文件独立书写。"""
    m = FileMarketData(settings.data_dir)
    f = m.get_daily_batch([], date(2018, 1, 8), EVAL_END, BASE)
    f = f.filter(
        pl.col("symbol").str.starts_with("60") | pl.col("symbol").str.starts_with("00")
    ).sort(["symbol", "date"])
    dup = f.select(pl.struct("symbol", "date").is_duplicated().sum()).item()
    if dup:
        raise ValueError(f"duplicate symbol/date rows: {dup}")
    return f


def main() -> int:
    t0 = time.perf_counter()
    frame = load_panel()
    print(f"[data] rows={frame.height} symbols={frame['symbol'].n_unique()} "
          f"{time.perf_counter()-t0:.1f}s", flush=True)

    syms = frame["symbol"].unique().sort().to_list()
    # 独立抽样: 取 3 个互不相关的中段区块 (不是作者的前 300 只固定分块)
    idx = [len(syms) // 7, len(syms) // 2, (len(syms) * 6) // 7]
    picks = sorted({syms[i] for i in idx})
    sample_syms = set(picks)
    print(f"[sample] total_symbols={len(syms)} picked={sorted(sample_syms)}", flush=True)

    part = frame.filter(pl.col("symbol").is_in(list(sample_syms))).sort(["symbol", "date"])
    ref = ref_columns(part)
    keep = (ref["date"] >= EVAL_START) & (ref["date"] <= EVAL_END)

    platform = materialize_scoring_columns(part.select(BASE), FACTORS)

    per = {}
    for fid in FACTORS:
        a = clean(platform[fid]).filter(keep)
        b = clean(ref[REF_MAP[fid]]).filter(keep)
        both = a.is_not_null() & b.is_not_null()
        diff = (a - b).abs().filter(both)
        dmax = float(diff.max()) if diff.len() else 0.0
        per[fid] = {
            "max_abs_diff": dmax,
            "n_both": int(both.sum()),
            "ref_notnull_platform_null": int((b.is_not_null() & a.is_null()).sum()),
            "ref_null_platform_notnull": int((b.is_null() & a.is_not_null()).sum()),
            "n_eval_rows": int(keep.sum()),
        }
        print(f"{fid:18s} diff={dmax:.6g} n={per[fid]['n_both']:>9d} "
              f"miss={per[fid]['ref_notnull_platform_null']} "
              f"extra={per[fid]['ref_null_platform_notnull']}", flush=True)

    # ---- 可达上界: 该 warmup 下"理论可非空"的行数, 与作者无关地独立计算 ----
    # 定义: 每只股票按 (warmup - 1) 之前的 bar 数计, 即首根非空位置 = warmup-1,
    # 故可非空行数 = max(0, bar数 - (warmup-1)), 仅在评估窗口内累加。
    bars = (
        ref.filter(keep)
        .with_columns(pl.int_range(pl.len()).over("symbol").alias("pos_in_eval"))
        .select(["symbol", "date", "pos_in_eval"])
    )
    # 更严谨: 用全序列位置而非窗口内位置
    pos = ref.with_row_index("__r").with_columns(
        pl.int_range(pl.len()).over("symbol").alias("pos_full")
    ).select(["symbol", "date", "pos_full"])
    pos = pos.filter((pos["date"] >= EVAL_START) & (pos["date"] <= EVAL_END))

    reach = {}
    for fid, w in WARMUP.items():
        n = int((pos["pos_full"] >= (w - 1)).sum())
        reach[fid] = n
        print(f"[reach] {fid:18s} warmup={w:3d} n_reachable={n}", flush=True)

    # ---- warmup 实证: 最长标的逐因子首个非空位置 ----
    longest = (
        frame.group_by("symbol").len().sort(["len", "symbol"], descending=[True, False])
        .head(1)["symbol"][0]
    )
    one = frame.filter(pl.col("symbol") == longest).sort("date")
    plat_one = materialize_scoring_columns(one.select(BASE), FACTORS)
    ref_one = ref_columns(one)
    warm = []
    for fid in FACTORS:
        v = clean(plat_one[fid]).to_numpy()
        fin = np.flatnonzero(np.isfinite(v))
        fv = int(fin[0]) if fin.size else -1
        prev_null = bool(fv <= 0 or not np.isfinite(v[fv - 1]))
        vr = clean(ref_one[REF_MAP[fid]]).to_numpy()
        finr = np.flatnonzero(np.isfinite(vr))
        fvr = int(finr[0]) if finr.size else -1
        warm.append({
            "id": fid, "symbol": longest, "bars": int(plat_one.height),
            "first_valid_0based": fv, "expected": WARMUP[fid] - 1,
            "match": fv == WARMUP[fid] - 1, "prev_is_null": prev_null,
            "ref_first_valid_0based": fvr, "ref_match": fvr == WARMUP[fid] - 1,
        })
        print(f"[warm] {fid:18s} got={fv:4d} exp={WARMUP[fid]-1:4d} "
              f"match={fv == WARMUP[fid]-1} prev_null={prev_null}", flush=True)

    # ---- prior_* vs high_60d: 数值不同证不是改名 ----
    h60 = part.with_columns(
        pl.col("high").rolling_max(60).over("symbol").alias("h60")
    )
    close = clean(h60["close"])
    hh = clean(h60["h60"])
    jac = {}
    for fid in ("prior_high_20", "prior_high_55", "prior_high_250"):
        pv = clean(platform[fid])
        valid = close.is_not_null() & pv.is_not_null() & hh.is_not_null()
        ca = (close > pv).fill_null(False)
        cb = (close > hh).fill_null(False)
        both_t = int((ca & cb & valid).sum())
        union_t = int(((ca | cb) & valid).sum())
        eq = int(((pv == hh) & valid).sum())
        jac[fid] = {
            "jaccard": (both_t / union_t) if union_t else None,
            "union": union_t, "both_true": both_t,
            "n_exact_equal_vs_h60": eq,
            "n_valid": int(valid.sum()),
        }
        print(f"[jacc] {fid:18s} jaccard={jac[fid]['jaccard']} "
              f"exact_equal={eq}/{int(valid.sum())}", flush=True)

    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "sample_symbols": sorted(sample_syms),
        "n_symbols_total": len(syms),
        "n_eval_rows_sample": int(keep.sum()),
        "per_factor": per,
        "n_reachable": reach,
        "warmup": warm,
        "jaccard_vs_high_60d": jac,
        "elapsed_s": round(time.perf_counter() - t0, 1),
    }
    out = Path(__file__).with_suffix(".json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] -> {out} ({result['elapsed_s']}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
