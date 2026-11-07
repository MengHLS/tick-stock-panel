"""可达上界独立复算（修正版）+ 矩阵反例 + alias 生产可达性。

修正要点：warmup 应在**全历史**上滚动后再取评估窗，不得在评估窗内重新滚动
（后者会人为制造 warmup 缺失，把上界压低 ~530k 行）。上一版 indep_b0_final.py
的 reachable_bound() 有此方法错误，本文件更正。

每只股票的精确可达上界:
  v_i = b_i - max(0, w - p_i)   （下限 0）
  b_i = 评估窗内 bar 数, p_i = 评估窗之前该股 bar 数, w = 全局首个非空前 null 数
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
EVAL_START, EVAL_END = date(2019, 7, 1), date(2026, 10, 30)
IDS = ["ma20", "ma60", "boll_lower", "boll_upper", "sd20", "prior_high_20",
       "prior_low_10", "prior_high_55", "prior_vol_20", "ma120", "vol60",
       "prior_high_250", "prior_amount_20", "ma200"]


def rec(section, **kv):
    OUT.setdefault(section, {}).update(kv)
    print(f"[{section}] " + " ".join(f"{k}={v}" for k, v in kv.items()), flush=True)


def reachable_bound():
    from app.config import settings
    from app.extensions.adapters import FileMarketData
    from app.strategy.scoring import materialize_scoring_columns

    m = FileMarketData(settings.data_dir)
    f = m.get_daily_batch([], date(2016, 1, 4), EVAL_END, BASE)
    f = f.filter(pl.col("symbol").str.starts_with("60")
                 | pl.col("symbol").str.starts_with("00")).sort(["symbol", "date"])
    print(f"[data] rows={f.height} symbols={f['symbol'].n_unique()}", flush=True)

    # 全历史滚动（关键：不是评估窗内滚动）
    full = materialize_scoring_columns(f.select(BASE), IDS)
    full = full.with_columns(pl.col("date").is_between(EVAL_START, EVAL_END).alias("__in"))
    ev = full.filter(pl.col("__in"))

    grp = ev.group_by("symbol").agg(
        pl.len().alias("b"),
        pl.col("date").min().alias("d0"),
    )
    pre = f.filter(pl.col("date") < EVAL_START).group_by("symbol").agg(
        pl.len().alias("p"), pl.col("date").max().alias("dlast"))
    meta = grp.join(pre, on="symbol", how="left").fill_null(0)

    detail, all_ok = {}, True
    for fid in IDS:
        # 独立算 w: 全样本按 symbol 找首个非空 index，取最小者（各股一致）
        col = full[fid].cast(pl.Float64).fill_nan(None)
        tmp = full.select(pl.col("symbol"), col.alias("v")).with_columns(
            pl.int_range(pl.len()).over("symbol").alias("i"))
        fv = tmp.filter(pl.col("v").is_not_null()).group_by("symbol").agg(
            pl.col("i").min().alias("first"))
        w_global = int(fv["first"].min())

        # 每股精确可达上界
        nb = ev.group_by("symbol").agg(
            pl.col(fid).cast(pl.Float64).fill_nan(None).is_not_null().sum().alias("v")
        )
        j = meta.join(nb, on="symbol", how="left").fill_null(0)
        j = j.with_columns(
            pl.col("b").cast(pl.Int64).alias("b64"),
            pl.col("p").cast(pl.Int64).alias("p64"),
        ).with_columns(
            (pl.col("b64")
             - pl.max_horizontal(pl.lit(0, dtype=pl.Int64), pl.lit(w_global, dtype=pl.Int64) - pl.col("p64")))
            .clip(0).alias("upper"))
        upper = int(j["upper"].sum())
        actual = int(j["v"].sum())
        ok = upper == actual
        all_ok &= ok
        detail[fid] = {"w_first_valid_index": w_global, "upper": upper,
                       "actual_nonnull": actual, "eq": ok, "diff": actual - upper}
        print(f"  {fid:17s} w={w_global:3d} upper={upper:>9d} actual={actual:>9d} eq={ok}",
              flush=True)
    rec("reachable_bound_v2", rows_eval=ev.height,
        symbols=ev["symbol"].n_unique(), all_eq=all_ok, detail=detail)

    # 与作者自报 n_both 对照
    ev_json = json.loads((PROJECT / "docs/factors/evidence/registration_b0_20261107.json")
                         .read_text(encoding="utf-8"))
    author = {k: v["n_both"] for k, v in ev_json["fidelity"]["per_factor"].items()}
    cmp = {fid: {"author_n_both": author.get(fid),
                 "my_actual_nonnull": detail[fid]["actual_nonnull"],
                 "match": author.get(fid) == detail[fid]["actual_nonnull"]} for fid in IDS}
    rec("author_n_vs_mine", match_all=all(v["match"] for v in cmp.values()), detail=cmp)

    # 空跑: 是否有 bar 充足却仍 null 的真缺陷
    worst = []
    for fid in IDS:
        nb = ev.group_by("symbol").agg(
            pl.col(fid).cast(pl.Float64).fill_nan(None).is_not_null().sum().alias("v"))
        j = meta.join(nb, on="symbol", how="left").fill_null(0)
        w = detail[fid]["w_first_valid_index"]
        bad = j.filter((pl.col("p") >= w) & (pl.col("v") < pl.col("b")))
        if bad.height:
            worst.append({"id": fid, "n_bad_symbols": bad.height})
    rec("no_spurious_null_when_history_sufficient", bad=worst, clean=(len(worst) == 0))


def matrix_gap():
    from app.backtest.matrix import _MATRIX_COMPUTED_FEATURES
    from app.extensions.factors import materialize_matrix_factor_field, FactorProviderContext
    from app.custom.research_factor_pack.factor_provider import ResearchFactorPackProvider

    pack = ResearchFactorPackProvider()
    overrides = "materialize_matrix_field" in ResearchFactorPackProvider.__dict__
    print(f"[matrix] pack overrides materialize_matrix_field={overrides}", flush=True)

    from app.extensions.factors import factor_provider_for
    probes = list(IDS)
    got, routed = {}, {}
    for p in probes:
        prov = factor_provider_for(p)
        routed[p] = (prov.provider_id if prov is not None else None)
        try:
            v = materialize_matrix_factor_field(object(), p)
            got[p] = "None" if v is None else str(type(v).__name__)
        except Exception as e:  # noqa: BLE001
            got[p] = f"ERR:{type(e).__name__}:{e}"
    rec("matrix_provider_result", overrides=overrides,
        n_none=sum(1 for v in got.values() if v == "None"), n_total=len(got),
        routed_to=dict(list(routed.items())), detail=got)

    feats = set(_MATRIX_COMPUTED_FEATURES)
    cov = {p: p in feats for p in probes}
    covered = [p for p in probes if cov[p]]
    rec("matrix_coverage", n_features=len(feats), covered=covered,
        missing=[p for p in probes if not cov[p]],
        coverage=f"{len(covered)}/{len(probes)}")


def alias_reachability():
    from app.factors.dsl import compile_formula
    from app.factors.registry import all_factors, get_factor

    ids = [s.id for s in all_factors()]
    uf = sorted(i for i in ids if i.startswith(("uf_", "cf_")))
    pairs = {"vol60": "uf_vol60", "ma120": "uf_ma120", "ma200": "uf_ma200",
             "prior_high_20": "uf_prior_high_20", "prior_high_55": "uf_prior_high_55",
             "prior_high_250": "uf_prior_high_250", "prior_low_10": "uf_prior_low_10",
             "prior_vol_20": "uf_prior_vol_20"}
    both = {k: [get_factor(k) is not None, get_factor(v) is not None] for k, v in pairs.items()}
    comp = {}
    for k, v in pairs.items():
        a, b = compile_formula(f"{k} > 0"), compile_formula(f"{v} > 0")
        comp[k] = {"pack_ok": bool(a.ok), "uf_ok": bool(b.ok)}
    # 两套 id 都能编译 => 都能被策略表达式引用 => 都能进生产评分路径
    rec("alias", n_uf=len(uf), uf_ids=uf,
        both_in_registry=both,
        both_compile=comp,
        all_pair_both_present=all(v[0] and v[1] for v in both.values()),
        all_pair_both_compile=all(v["pack_ok"] and v["uf_ok"] for v in comp.values()),
        uf_prior_amount_20_exists=(get_factor("uf_prior_amount_20") is not None))

    # 生产口子: 策略表达式引用 uf_vol60 与 vol60 能否都通过校验
    from app.strategy.scoring import materialize_scoring_columns
    import polars as pl
    from datetime import date as D
    from app.config import settings
    from app.extensions.adapters import FileMarketData
    f = FileMarketData(settings.data_dir).get_daily_batch(
        ["600000.SH"], D(2025, 1, 2), D(2026, 6, 30), BASE)
    f = f.sort(["symbol", "date"])
    out = {}
    for nm in ("vol60", "uf_vol60"):
        try:
            r = materialize_scoring_columns(f.select(BASE), [nm])
            c = r[nm].cast(pl.Float64).fill_nan(None)
            out[nm] = {"ok": True, "nonnull": int(c.is_not_null().sum())}
        except Exception as e:  # noqa: BLE001
            out[nm] = {"ok": False, "err": f"{type(e).__name__}: {e}"}
    rec("alias_production_materialize", detail=out)


def main():
    t0 = time.perf_counter()
    reachable_bound()
    matrix_gap()
    alias_reachability()
    OUT["elapsed_s"] = round(time.perf_counter() - t0, 1)
    OUT["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    p = Path(__file__).with_suffix(".json")
    p.write_text(json.dumps(OUT, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[done] -> {p} ({OUT['elapsed_s']}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
