"""截面排名口径差异与市场宽度口径差异（只读）。

目的：把 research add_universe() 的「股票池掩码 + 截面排名 + 市场宽度」与系统
DSL rank() 的语义（全样本排名、分母=当日非空样本数、无掩码）以及「无掩码市场宽度」
放在同一份行情上对照，量化两套口径在实际选股上的差异。

输出：xs_rank_stats.json
运行：
  cd C:\\work\\sourcecode\\tick-stock-panel\\backend
  .\\.venv\\Scripts\\python.exe ..\\docs\\research\\factor-audit-20261107\\scripts\\audit_xs_rank.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve()
PROJECT = HERE.parents[4]
BACKEND = PROJECT / "backend"
RESEARCH_SCRIPTS = PROJECT / "research" / "strategy-search-20261107" / "scripts"
OUT_DIR = HERE.parents[1]
for p in (str(BACKEND), str(RESEARCH_SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import common as C  # noqa: E402

OUT = {"meta": {}, "xs_rank": {}, "market_breadth": {}, "vol60_substitution": {}}

# 策略阈值全部取自 research/strategy-search-20261107/scripts/common.py build_signals
THRESH = {
    "S06_ret5_le_0.05": ("rk_ret5", 0.05, "week_end"),
    "S07_vol60_le_0.10": ("rk_vol60", 0.10, "month_end"),
    "S10_ret20_le_0.10": ("rk_ret20", 0.10, "month_end"),
}


def _jacc(a: int, b: int, ab: int) -> float:
    union = a + b - ab
    return float(ab / union) if union else float("nan")


def main() -> None:
    t0 = time.time()
    m = C.open_market()
    frame = C.load_panel(m)
    f = C.add_indicators(frame)
    f = C.add_universe(f)
    f = f.filter(
        (pl.col("date") >= C.EVAL_START) & (pl.col("date") <= C.EVAL_END)
    )
    OUT["meta"] = {
        "rows": f.height,
        "symbols": f["symbol"].n_unique(),
        "date_min": str(f["date"].min()),
        "date_max": str(f["date"].max()),
        "eval_start": str(C.EVAL_START),
        "eval_end": str(C.EVAL_END),
        "universe": dict(C.UNIVERSE),
        "thresh_source": "research/strategy-search-20261107/scripts/common.py#build_signals",
    }

    # 系统 annual_vol_20d 口径（app/indicators/pipeline.py Pass4）: 日收益标准差×√252，窗口 20
    f = f.with_columns(
        (pl.col("ret1").rolling_std(20).over("symbol") * (252 ** 0.5)).alias("annual_vol_20d")
    )

    # 系统 DSL rank 语义: x.rank("average").over("date") / x.count().over("date")
    sys_rank = []
    for col in ("ret5", "ret20", "vol60", "ret60", "dist_52w_high", "annual_vol_20d"):
        if col not in f.columns:
            continue
        sys_rank.append(
            (pl.col(col).rank("average").over("date")
             / pl.col(col).count().over("date")).alias(f"sys_rk_{col}")
        )
    f = f.with_columns(sys_rank)

    # ---------------- 截面排名：研究口径 vs 系统 DSL 口径
    for name, (rk_col, thr, cal) in THRESH.items():
        col = rk_col[3:]  # rk_ret5 -> ret5
        sel_a = (pl.col("in_universe") & (pl.col(rk_col) <= thr)).fill_null(False)
        sel_b = (pl.col(f"sys_rk_{col}") <= thr).fill_null(False)
        d = (
            f.filter(pl.col(cal))
            .group_by("date")
            .agg(
                sel_a.sum().alias("a"),
                sel_b.sum().alias("b"),
                (sel_a & sel_b).sum().alias("ab"),
                pl.col(f"sys_rk_{col}").count().alias("n_sys"),
                pl.col("in_universe").sum().alias("n_univ"),
            )
            .with_columns(
                pl.struct(["a", "b", "ab"]).map_elements(
                    lambda s: _jacc(s["a"], s["b"], s["ab"]), return_dtype=pl.Float64
                ).alias("jaccard"),
                (pl.col("ab") / pl.col("a").clip(lower_bound=1)).alias("recall_of_research"),
                (pl.col("ab") / pl.col("b").clip(lower_bound=1)).alias("precision_vs_system"),
            )
        )
        OUT["xs_rank"][name] = {
            "rebuild_dates": d.height,
            "thr": thr,
            "mean_sel_research": float(d["a"].mean()),
            "mean_sel_system": float(d["b"].mean()),
            "mean_jaccard": float(d["jaccard"].mean()),
            "median_jaccard": float(d["jaccard"].median()),
            "mean_recall_of_research": float(d["recall_of_research"].mean()),
            "mean_universe_size": float(d["n_univ"].mean()),
            "mean_system_denominator": float(d["n_sys"].mean()),
        }

    # S11 复合: 两个排名都 <= 0.30
    sel_a11 = (pl.col("in_universe") & (pl.col("rk_vol60") <= 0.30)
               & (pl.col("rk_ret20") <= 0.30)).fill_null(False)
    sel_b11 = ((pl.col("sys_rk_vol60") <= 0.30) & (pl.col("sys_rk_ret20") <= 0.30)).fill_null(False)
    d11 = (
        f.filter(pl.col("month_end"))
        .group_by("date")
        .agg(
            sel_a11.sum().alias("a"), sel_b11.sum().alias("b"), (sel_a11 & sel_b11).sum().alias("ab"),
        )
        .with_columns(
            pl.struct(["a", "b", "ab"]).map_elements(
                lambda s: _jacc(s["a"], s["b"], s["ab"]), return_dtype=pl.Float64
            ).alias("jaccard"),
        )
    )
    OUT["xs_rank"]["S11_both_le_0.30"] = {
        "rebuild_dates": d11.height,
        "mean_sel_research": float(d11["a"].mean()),
        "mean_sel_system": float(d11["b"].mean()),
        "mean_jaccard": float(d11["jaccard"].mean()),
    }

    # ---------------- 市场宽度：研究口径(仅 in_universe) vs 无掩码口径(全样本可算 MA60)
    d = f.group_by("date").agg(
        pl.when(pl.col("in_universe") & pl.col("ma60").is_not_null())
        .then((pl.col("close") > pl.col("ma60")).cast(pl.Float64))
        .otherwise(None).mean().alias("breadth_research"),
        pl.when(pl.col("ma60").is_not_null())
        .then((pl.col("close") > pl.col("ma60")).cast(pl.Float64))
        .otherwise(None).mean().alias("breadth_unmasked"),
    ).drop_nulls().sort("date")
    diff = (d["breadth_research"] - d["breadth_unmasked"]).abs()
    me = f.filter(pl.col("month_end")).select("date").unique()
    dme = d.join(me, on="date", how="semi")
    OUT["market_breadth"] = {
        "n_days": d.height,
        "mean_research": float(d["breadth_research"].mean()),
        "mean_unmasked": float(d["breadth_unmasked"].mean()),
        "corr_pearson": float(d.select(pl.corr("breadth_research", "breadth_unmasked")).item()),
        "corr_spearman": float(
            d.select(pl.corr("breadth_research", "breadth_unmasked", method="spearman")).item()
        ),
        "mean_abs_diff": float(diff.mean()),
        "p95_abs_diff": float(diff.quantile(0.95)),
        "max_abs_diff": float(diff.max()),
        "share_days_threshold_flip": float(
            ((d["breadth_research"] >= 0.5) != (d["breadth_unmasked"] >= 0.5)).mean()
        ),
        "month_ends": dme.height,
        "share_month_ends_research_ge_0p5": float((dme["breadth_research"] >= 0.5).mean()),
        "share_month_ends_unmasked_ge_0p5": float((dme["breadth_unmasked"] >= 0.5).mean()),
        "month_end_flip_share": float(
            ((dme["breadth_research"] >= 0.5) != (dme["breadth_unmasked"] >= 0.5)).mean()
        ),
    }

    # ---------------- vol60 替代性：research vol60 vs 系统 annual_vol_20d（同为月内选 10% 低波）
    sel_a = (pl.col("in_universe") & (pl.col("rk_vol60") <= 0.10)).fill_null(False)
    sel_b = (pl.col("sys_rk_annual_vol_20d") <= 0.10).fill_null(False)
    dv = (
        f.filter(pl.col("month_end"))
        .group_by("date")
        .agg(sel_a.sum().alias("a"), sel_b.sum().alias("b"), (sel_a & sel_b).sum().alias("ab"))
        .with_columns(
            pl.struct(["a", "b", "ab"]).map_elements(
                lambda s: _jacc(s["a"], s["b"], s["ab"]), return_dtype=pl.Float64
            ).alias("jaccard"),
        )
    )
    OUT["vol60_substitution"] = {
        "note": "research vol60(60日收益标准差) 的低波十分位 vs 系统 annual_vol_20d(20日年化) 的低波十分位",
        "rebuild_dates": dv.height,
        "mean_sel_research": float(dv["a"].mean()),
        "mean_sel_system": float(dv["b"].mean()),
        "mean_jaccard": float(dv["jaccard"].mean()),
        "median_jaccard": float(dv["jaccard"].median()),
    }

    OUT["meta"]["seconds"] = round(time.time() - t0, 1)
    (OUT_DIR / "xs_rank_stats.json").write_text(
        json.dumps(OUT, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(OUT, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
