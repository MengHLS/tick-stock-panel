"""按生产启动态（main.py:217-221 的 load_into_registry 之后）复核 dual-id 与矩阵覆盖。

上一版 alias_reachability() 在冷启动态探测（未 load store），得出 n_uf=0，
那不是生产态。本文件显式先做生产启动序列，再探测。
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(PROJECT / "backend"))

import polars as pl

OUT: dict = {}
BASE = ["symbol", "date", "open", "high", "low", "close", "volume", "amount"]
PAIRS = {
    "vol60": "uf_vol60", "ma120": "uf_ma120", "ma200": "uf_ma200",
    "prior_high_20": "uf_prior_high_20", "prior_high_55": "uf_prior_high_55",
    "prior_high_250": "uf_prior_high_250", "prior_low_10": "uf_prior_low_10",
    "prior_vol_20": "uf_prior_vol_20",
}


def rec(section, **kv):
    OUT.setdefault(section, {}).update(kv)
    print(f"[{section}] " + " ".join(f"{k}={v}" for k, v in kv.items()), flush=True)


def startup_seq():
    """复刻 main.py:217-221 + worker.py:234-236 的启动序列。"""
    from app.config import settings
    from app.extensions.factors import ensure_factor_providers
    from app.factors.registry import all_factors
    from app.factors.store import load_into_registry

    ensure_factor_providers()
    loaded = load_into_registry(Path(str(settings.data_dir)))
    ids = [s.id for s in all_factors()]
    uf = sorted(i for i in ids if i.startswith(("uf_", "cf_")))
    rec("startup", loaded_count=len(loaded), loaded_ids=sorted(loaded),
        total=len(ids), n_uf_cf=len(uf), uf_cf_ids=uf)


def alias_prod():
    from app.config import settings
    from app.extensions.adapters import FileMarketData
    from app.factors.dsl import compile_formula
    from app.factors.registry import get_factor
    from app.strategy.scoring import materialize_scoring_columns

    pres = {k: [get_factor(k) is not None, get_factor(v) is not None]
            for k, v in PAIRS.items()}
    comp = {}
    for k, v in PAIRS.items():
        a, b = compile_formula(f"{k} > 0"), compile_formula(f"{v} > 0")
        comp[k] = {"pack_ok": bool(a.ok), "uf_ok": bool(b.ok),
                   "uf_err": (None if b.ok else f"{b.errors[0].code}:{b.errors[0].message}")}
    rec("alias_registry_prod", pairs=pres,
        all_pairs_present=all(v[0] and v[1] for v in pres.values()),
        compile=comp,
        uf_prior_amount_20_exists=(get_factor("uf_prior_amount_20") is not None),
        all_pairs_compile=all(v["pack_ok"] and v["uf_ok"] for v in comp.values()))

    # 两套 id 同时物化，看数值是否一致（生产评分路径可同时引用）
    f = FileMarketData(settings.data_dir).get_daily_batch(
        ["600000.SH", "000001.SZ", "600519.SH"], date(2024, 1, 2), date(2026, 6, 30), BASE
    ).sort(["symbol", "date"])
    names = []
    for k, v in PAIRS.items():
        names += [k, v]
    try:
        m = materialize_scoring_columns(f.select(BASE), names)
        dual = {}
        for k, v in PAIRS.items():
            a = m[k].cast(pl.Float64).fill_nan(None)
            b = m[v].cast(pl.Float64).fill_nan(None)
            both = a.is_not_null() & b.is_not_null()
            d = (a - b).abs().filter(both)
            dual[k] = {"both": int(both.sum()),
                       "max_abs_diff": float(d.max()) if d.len() else None,
                       "nonzero": int((d > 0).sum())}
        rec("alias_prod_values", detail=dual,
            all_coexist=True, rows=f.height)
    except Exception as e:  # noqa: BLE001
        rec("alias_prod_values", error=f"{type(e).__name__}: {e}")


def matrix_prod():
    """9 个 uf_* canonical 在矩阵路径的覆盖（生产态注册后）。"""
    from app.backtest.matrix import _MATRIX_COMPUTED_FEATURES
    from app.extensions.factors import factor_provider_for, materialize_matrix_factor_field

    feats = set(_MATRIX_COMPUTED_FEATURES)
    rows = []
    for uf in ["uf_vol60", "uf_ma120", "uf_ma200", "uf_prior_high_20",
               "uf_prior_high_55", "uf_prior_high_250", "uf_prior_low_10",
               "uf_prior_vol_20", "uf_prior_amount_20"]:
        prov = factor_provider_for(uf)
        try:
            v = materialize_matrix_factor_field(object(), uf)
            mat = "None" if v is None else type(v).__name__
        except Exception as e:  # noqa: BLE001
            mat = f"ERR:{type(e).__name__}"
        rows.append({"id": uf, "in_MATRIX_COMPUTED_FEATURES": uf in feats,
                     "provider": (prov.provider_id if prov else None),
                     "matrix_value": mat})
    rec("matrix_uf_coverage", detail=rows,
        covered=[r["id"] for r in rows if r["matrix_value"] != "None"],
        n_covered=sum(1 for r in rows if r["matrix_value"] != "None"))

    # canonical 名（无前缀）在矩阵特征表里是否存在
    canon = ["ma20", "ma60", "ma120", "ma200", "sd20", "vol60", "prior_high_20",
             "prior_high_55", "prior_high_250", "prior_low_10", "prior_vol_20",
             "prior_amount_20", "boll_lower", "boll_upper"]
    rec("matrix_canon_in_features", present=[c for c in canon if c in feats],
        absent=[c for c in canon if c not in feats], n_features=len(feats))


def main():
    t0 = time.perf_counter()
    startup_seq()
    alias_prod()
    matrix_prod()
    OUT["elapsed_s"] = round(time.perf_counter() - t0, 1)
    OUT["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    p = Path(__file__).with_suffix(".json")
    p.write_text(json.dumps(OUT, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[done] -> {p}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
