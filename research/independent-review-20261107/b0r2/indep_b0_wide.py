"""独立复算 B0 第二轮 — 3 万行以上保真 + 幂等 + 双 id 生产路径并存实测。

不使用作者的 verify_b0.py。参考值在本文件独立书写。
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

EVAL_START = date(2019, 7, 1)
EVAL_END = date(2026, 10, 30)
BASE = ["symbol", "date", "open", "high", "low", "close", "volume", "amount"]

FACTORS = [
    "ma20", "ma60", "boll_lower", "boll_upper", "sd20",
    "prior_high_20", "prior_low_10", "prior_high_55", "prior_vol_20",
    "ma120", "vol60", "prior_high_250", "prior_amount_20", "ma200",
]
REF_MAP = {
    "ma20": "r_ma20", "ma60": "r_ma60", "ma120": "r_ma120", "ma200": "r_ma200",
    "sd20": "r_sd20", "boll_lower": "r_bb_lower", "boll_upper": "r_bb_upper",
    "prior_high_20": "r_ph20", "prior_low_10": "r_pl10", "prior_high_55": "r_ph55",
    "prior_high_250": "r_ph250", "prior_vol_20": "r_pv20",
    "prior_amount_20": "r_pa20", "vol60": "r_vol60",
}


def ref_columns(f: pl.DataFrame) -> pl.DataFrame:
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
        ((pl.col("close") - pl.col("close").shift(1)) / pl.col("close").shift(1))
        .rolling_std(60).over("symbol").alias("r_vol60"),
    ).with_columns(
        (pl.col("r_ma20") - 2 * pl.col("r_sd20")).alias("r_bb_lower"),
        (pl.col("r_ma20") + 2 * pl.col("r_sd20")).alias("r_bb_upper"),
    )


def clean(s: pl.Series) -> pl.Series:
    return s.cast(pl.Float64).fill_nan(None)


def main() -> int:
    t0 = time.perf_counter()
    m = FileMarketData(settings.data_dir)
    f = m.get_daily_batch([], date(2018, 1, 8), EVAL_END, BASE)
    f = f.filter(
        pl.col("symbol").str.starts_with("60") | pl.col("symbol").str.starts_with("00")
    ).sort(["symbol", "date"])
    print(f"[data] rows={f.height} symbols={f['symbol'].n_unique()}", flush=True)

    # 25 只等间距抽样 -> 评估窗内约 4 万行 (>= 3 万)
    syms = f["symbol"].unique().sort().to_list()
    step = max(1, len(syms) // 25)
    picks = sorted(set(syms[::step][:25]))
    part = f.filter(pl.col("symbol").is_in(picks)).sort(["symbol", "date"])
    keep = (part["date"] >= EVAL_START) & (part["date"] <= EVAL_END)
    print(f"[sample] n_symbols={len(picks)} eval_rows={int(keep.sum())}", flush=True)

    ref = ref_columns(part)
    plat = materialize_scoring_columns(part.select(BASE), FACTORS)

    per = {}
    tot = 0
    for fid in FACTORS:
        a = clean(plat[fid]).filter(keep)
        b = clean(ref[REF_MAP[fid]]).filter(keep)
        both = a.is_not_null() & b.is_not_null()
        d = (a - b).abs().filter(both)
        mx = float(d.max()) if d.len() else 0.0
        nz = int((d > 0).sum())
        nb = int(both.sum())
        per[fid] = {
            "max_abs_diff": mx, "n_both": nb, "nonzero_rows": nz,
            "bit_equal": nz == 0,
            "ref_notnull_platform_null": int((b.is_not_null() & a.is_null()).sum()),
            "ref_null_platform_notnull": int((b.is_null() & a.is_not_null()).sum()),
        }
        tot += nb
        print(f"{fid:18s} diff={mx:.6g} n={nb:>8d} nonzero={nz}", flush=True)

    # ---- 幂等: 重复 provider 注册 ----
    from app.custom.research_factor_pack.factor_provider import FACTOR_PROVIDERS
    from app.extensions.factors import ensure_factor_providers, register_factor_provider
    from app.factors.registry import all_factors, get_factor
    from app.factors.store import load_into_registry

    snap0 = len(all_factors())
    v0 = {k: get_factor(k).version for k in FACTORS}
    ensure_factor_providers()
    ensure_factor_providers()
    register_factor_provider(FACTOR_PROVIDERS[0])
    load_into_registry(Path(str(settings.data_dir)))
    load_into_registry(Path(str(settings.data_dir)))
    snap1 = len(all_factors())
    v1 = {k: get_factor(k).version for k in FACTORS}
    counts = {k: sum(1 for s in all_factors() if s.id == k) for k in FACTORS}
    dup_all = {}
    for s in all_factors():
        dup_all[s.id] = dup_all.get(s.id, 0) + 1
    idem = {
        "total_before": snap0, "total_after": snap1,
        "versions_before": v0, "versions_after": v1,
        "counts": counts,
        "versions_stable": v0 == v1,
        "total_stable": snap0 == snap1,
        "no_dup_pack_ids": all(v == 1 for v in counts.values()),
        "dup_ids_anywhere": {k: v for k, v in dup_all.items() if v > 1},
    }
    print(f"[idem] {snap0} -> {snap1}  versions_stable={idem['versions_stable']} "
          f"no_dup={idem['no_dup_pack_ids']}  dup={idem['dup_ids_anywhere']}", flush=True)

    # ---- 双 id 并存: 同一口径两套实现都在生产物化路径上 ----
    both_names = ["vol60", "uf_vol60", "ma120", "uf_ma120", "prior_high_20", "uf_prior_high_20"]
    bothplat = materialize_scoring_columns(part.select(BASE), both_names)
    dual = {}
    for a, b in (("vol60", "uf_vol60"), ("ma120", "uf_ma120"),
                 ("prior_high_20", "uf_prior_high_20")):
        x, y = clean(bothplat[a]).filter(keep), clean(bothplat[b]).filter(keep)
        bb = x.is_not_null() & y.is_not_null()
        d = (x - y).abs().filter(bb)
        mx = float(d.max()) if d.len() else 0.0
        dual[f"{a}|{b}"] = {
            "both_computed": int(bb.sum()),
            "max_abs_diff": mx,
            "nonzero_rows": int((d > 0).sum()),
            "a_notnull": int(x.is_not_null().sum()),
            "b_notnull": int(y.is_not_null().sum()),
        }
        print(f"[dual] {a:16s} vs {b:18s} both={int(bb.sum()):>8d} "
              f"diff={mx:.6g} nz={int((d>0).sum())}", flush=True)

    # ---- alias 是否被生产入口拒绝? FactorSpec 有无相关字段 ----
    import dataclasses
    from app.factors.registry import FactorSpec
    spec_fields = [fl.name for fl in dataclasses.fields(FactorSpec)]

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_symbols": len(picks), "eval_rows": int(keep.sum()),
        "rows_compared_total": tot,
        "per_factor": per,
        "idempotent": idem,
        "dual_id_same_caliber": dual,
        "factorspec_fields": spec_fields,
        "elapsed_s": round(time.perf_counter() - t0, 1),
    }
    p = Path(__file__).with_suffix(".json")
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {tot} rows compared -> {p} ({out['elapsed_s']}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
