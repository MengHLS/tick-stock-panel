"""B0 第三轮独立复核 — 幂等分阶段、可达上界、矩阵反例、alias 生产可达性。

作者 verify_b0.py 一律不用。所有参考值在本文件独立书写。
UTF-8 显式写盘。
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


def rec(section: str, **kv):
    OUT.setdefault(section, {}).update(kv)
    print(f"[{section}] " + " ".join(f"{k}={v}" for k, v in kv.items()), flush=True)


# ---------------------------------------------------------------- 1. 幂等分阶段
def idempotency() -> None:
    from app.config import settings
    from app.custom.research_factor_pack.factor_provider import FACTOR_PROVIDERS
    from app.extensions.factors import ensure_factor_providers, register_factor_provider
    from app.factors.registry import all_factors, get_factor
    from app.factors.store import load_into_registry

    PACK = [
        "ma20", "ma60", "boll_lower", "boll_upper", "sd20",
        "prior_high_20", "prior_low_10", "prior_high_55", "prior_vol_20",
        "ma120", "vol60", "prior_high_250", "prior_amount_20", "ma200",
    ]

    def snap():
        f = all_factors()
        d: dict[str, int] = {}
        for s in f:
            d[s.id] = d.get(s.id, 0) + 1
        return len(f), d, {k: get_factor(k).version for k in PACK}

    # S0: 冷启动 —— ensure_factor_providers 自带 store 载入
    t0, d0, v0 = snap()
    rec("idem_s0_cold", total=t0, dup=len([k for k, n in d0.items() if n > 1]))
    ensure_factor_providers()
    t1, d1, v1 = snap()
    rec("idem_s1_after_ensure", total=t1, delta=t1 - t0,
        pack_counts={k: d1.get(k, 0) for k in PACK},
        versions_stable=(v0 == v1), dup_ids=[k for k, n in d1.items() if n > 1])
    # 再连调 3 次
    for _ in range(3):
        ensure_factor_providers()
    t2, d2, v2 = snap()
    rec("idem_s2_ensure_x3_more", total=t2, delta_vs_s1=t2 - t1,
        versions_stable=(v1 == v2),
        pack_counts={k: d2.get(k, 0) for k in PACK},
        dup_ids=[k for k, n in d2.items() if n > 1])
    # 显式重复注册同一个 provider 实例
    register_factor_provider(FACTOR_PROVIDERS[0])
    register_factor_provider(FACTOR_PROVIDERS[0])
    t3, d3, v3 = snap()
    rec("idem_s3_register_same_instance_x2", total=t3, delta_vs_s2=t3 - t2,
        versions_stable=(v2 == v3),
        pack_counts={k: d3.get(k, 0) for k in PACK},
        dup_ids=[k for k, n in d3.items() if n > 1][:12])
    # 重复 load_into_registry（store 侧）
    for _ in range(2):
        load_into_registry(Path(str(settings.data_dir)))
    t4, d4, v4 = snap()
    rec("idem_s4_load_store_x2", total=t4, delta_vs_s3=t4 - t3,
        versions_stable=(v3 == v4),
        pack_counts={k: d4.get(k, 0) for k in PACK},
        dup_ids=[k for k, n in d4.items() if n > 1][:12])
    rec("idem_verdict",
        total_stable_all_phases=len({t0, t1, t2, t3, t4}) == 1,
        versions_all_stable=(v0 == v1 == v2 == v3 == v4),
        pack_id_unique=all(d4.get(k, 0) == 1 for k in PACK))


# ---------------------------------------------------------- 2. 可达上界（独立算）
def reachable_bound() -> None:
    """每个因子的 n 上界 = 全样本该因子非空行数（在给定 warmup 下可达的最大值）。

    独立算法: 按 (symbol,date) 全量取数 -> 逐只算 first_valid -> 每只的
    (bars - first_valid - 1) 计入不可达 -> 上界 = 总行 - 不可达。
    与平台实现的 n 比较，验证作者「n 等于该 warmup 下可达上界」的判据修订。
    """
    from app.config import settings
    from app.extensions.adapters import FileMarketData
    from app.strategy.scoring import materialize_scoring_columns

    BASE = ["symbol", "date", "open", "high", "low", "close", "volume", "amount"]
    EVAL_START, EVAL_END = date(2019, 7, 1), date(2026, 10, 30)
    WARMUP = {
        "ma20": 19, "ma60": 59, "boll_lower": 19, "boll_upper": 19, "sd20": 19,
        "prior_high_20": 20, "prior_low_10": 10, "prior_high_55": 55,
        "prior_vol_20": 20, "ma120": 119, "vol60": 60, "prior_high_250": 250,
        "prior_amount_20": 20, "ma200": 199,
    }
    m = FileMarketData(settings.data_dir)
    f = m.get_daily_batch([], date(2018, 1, 8), EVAL_END, BASE)
    f = f.filter(
        pl.col("symbol").str.starts_with("60") | pl.col("symbol").str.starts_with("00")
    ).sort(["symbol", "date"])
    keep = (f["date"] >= EVAL_START) & (f["date"] <= EVAL_END)
    ev = f.filter(keep)
    n_rows = ev.height
    n_sym = ev["symbol"].n_unique()
    print(f"[bound] universe rows={n_rows} symbols={n_sym}", flush=True)

    # 每只评估窗内的 bar 数
    per_sym_bars = ev.group_by("symbol").len()["len"]
    tot = int(per_sym_bars.sum())

    bound = {}
    for fid, w in WARMUP.items():
        # 该因子在评估窗内 首根非空位置 = w（0-based），故每只不可达 = min(w+1, bars)
        # 上界 = 总行 - sum(min(w+1, bars_i))
        unreach = int(per_sym_bars.clip(0, w + 1).sum())
        bound[fid] = tot - unreach

    # 平台实际非空数（全样本，不做抽样）
    ids = list(WARMUP)
    plat = materialize_scoring_columns(ev.select(BASE), ids)
    actual = {}
    for fid in ids:
        c = plat[fid]
        actual[fid] = int(c.cast(pl.Float64).fill_nan(None).is_not_null().sum())

    dial = {}
    for fid in ids:
        dial[fid] = {
            "warmup_0based_last_null": WARMUP[fid],
            "reachable_bound_independent": bound[fid],
            "platform_nonnull": actual[fid],
            "eq": bound[fid] == actual[fid],
            "diff": actual[fid] - bound[fid],
        }
    rec("reachable_bound", rows=n_rows, symbols=n_sym, detail=dial)
    rec("reachable_bound_verdict",
        all_eq=all(d["eq"] for d in dial.values()),
        ma200_bound=bound["ma200"], ma200_actual=actual["ma200"],
        ph250_bound=bound["prior_high_250"],
        ph250_actual=actual["prior_high_250"])


# ----------------------------------------------------------- 3. 矩阵路径反例
def matrix_gap() -> None:
    from app.backtest.matrix import _MATRIX_COMPUTED_FEATURES  # noqa: PLC2701
    from app.extensions.factors import FactorProviderContext, materialize_matrix_factor_field
    from app.custom.research_factor_pack.factor_provider import ResearchFactorPackProvider

    pack = ResearchFactorPackProvider()
    # 基类实现是否被覆写
    base_override = type(pack).materialize_matrix_field is not object.__getattribute__(
        ResearchFactorPackProvider, "materialize_matrix_field"
    ) and "materialize_matrix_field" in ResearchFactorPackProvider.__dict__
    rec("matrix_override", provider_overrides_materialize_matrix_field=base_override)

    ctx = FactorProviderContext(provider_id=pack.provider_id, data_dir=None) if True else None
    probes = [
        "ma20", "ma60", "ma120", "ma200", "boll_lower", "boll_upper",
        "sd20", "vol60", "prior_high_20", "prior_high_55", "prior_high_250",
        "prior_low_10", "prior_vol_20", "prior_amount_20",
    ]
    try:
        res = materialize_matrix_factor_field(pack, probes, ctx)
        got = {k: (v is not None) for k, v in res.items()} if hasattr(res, "items") else res
    except Exception as e:  # noqa: BLE001
        got = {"__error__": f"{type(e).__name__}: {e}"}
    rec("matrix_provider_result", detail={str(k): str(v) for k, v in got.items()}
        if isinstance(got, dict) else {"raw": str(got)})

    feats = sorted(_MATRIX_COMPUTED_FEATURES)
    in_feats = {p: (p in _MATRIX_COMPUTED_FEATURES) for p in probes}
    rec("matrix_computed_features", n=len(feats), head=feats[:40],
        coverage=in_feats,
        covered=[p for p in probes if in_feats[p]],
        missing=[p for p in probes if not in_feats[p]])


# ------------------------------------- 4. alias 生产可达性 (strategy 表达式能否引用 uf_*)
def alias_reachability() -> None:
    from app.factors.dsl import compile_formula
    from app.factors.registry import get_factor, all_factors

    ids = [s.id for s in all_factors()]
    uf = sorted(i for i in ids if i.startswith("uf_") or i.startswith("cf_"))
    pack_pairs = {
        "vol60": "uf_vol60", "ma120": "uf_ma120", "ma200": "uf_ma200",
        "prior_high_20": "uf_prior_high_20", "prior_high_55": "uf_prior_high_55",
        "prior_high_250": "uf_prior_high_250", "prior_low_10": "uf_prior_low_10",
        "prior_vol_20": "uf_prior_vol_20",
    }
    both_present = {k: (get_factor(k) is not None, get_factor(v) is not None)
                    for k, v in pack_pairs.items()}
    # 两套 id 是否都能编译进策略表达式（= 都能进生产策略路径）
    comp = {}
    for k, v in pack_pairs.items():
        a = compile_formula(f"{k} > 0")
        b = compile_formula(f"{v} > 0")
        comp[k] = {"pack_ok": bool(a.ok), "uf_ok": bool(b.ok),
                   "pack_err": (a.errors[0].code if not a.ok else None),
                   "uf_err": (b.errors[0].code if not b.ok else None)}
    # prior_amount_20 是否只有 pack 一侧
    pa_uf = get_factor("uf_prior_amount_20")
    rec("alias", uf_ids=uf, n_uf=len(uf),
        both_present={k: list(v) for k, v in both_present.items()},
        both_compile=comp,
        uf_prior_amount_20_exists=(pa_uf is not None),
        all_pair_both=(all(v[0] and v[1] for v in both_present.values())))


# --------------------------------------------------------------- 5. vol60 两式差
def vol60_two_ways() -> None:
    from app.config import settings
    from app.extensions.adapters import FileMarketData
    from app.strategy.scoring import materialize_scoring_columns

    BASE = ["symbol", "date", "open", "high", "low", "close", "volume", "amount"]
    m = FileMarketData(settings.data_dir)
    f = m.get_daily_batch([], date(2024, 1, 2), date(2026, 10, 30), BASE)
    f = f.filter(pl.col("symbol").str.starts_with("60") | pl.col("symbol").str.starts_with("00")
                 ).sort(["symbol", "date"])
    plat = materialize_scoring_columns(f.select(BASE), ["vol60"])
    a = plat["vol60"].cast(pl.Float64).fill_nan(None)

    ret = (pl.col("close") - pl.col("close").shift(1)) / pl.col("close").shift(1)
    # 式一: 先算 ret1 再 rolling_std（研究 common.py 写法）
    b1 = f.with_columns(ret.alias("r1")).with_columns(
        pl.col("r1").rolling_std(60).over("symbol").alias("v")).get_column("v") \
        .cast(pl.Float64).fill_nan(None)
    # 式二: 直接在 close 上算 (close/shift-1) 的 std —— 数学等价但浮点不同路径
    d1 = (a - b1).abs()
    both = a.is_not_null() & b1.is_not_null()
    rec("vol60_two_ways", n_both=int(both.sum()),
        max_abs_diff=float(d1.filter(both).max()) if both.any() else None,
        nonzero=int((d1.filter(both) > 0).sum()),
        within_1e12=bool(float(d1.filter(both).max() or 0) < 1e-12))


def main() -> int:
    t0 = time.perf_counter()
    idempotency()
    reachable_bound()
    matrix_gap()
    alias_reachability()
    vol60_two_ways()
    OUT["elapsed_s"] = round(time.perf_counter() - t0, 1)
    OUT["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    p = Path(__file__).with_suffix(".json")
    p.write_text(json.dumps(OUT, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[done] -> {p} ({OUT['elapsed_s']}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
