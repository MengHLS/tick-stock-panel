"""因子口径一致性核对脚本（只读）。

目的：把 research/strategy-search-20261107/scripts/common.py 的 add_indicators /
add_universe 手算列，与系统实现（app.indicators.pipeline.compute_indicators、
app.strategy.scoring.materialize_scoring_columns、app.factors.dsl）在同一份行情数据上
逐项对比，输出可复现的数值差异（compare_stats.json）。

纪律：
- 不写任何系统源码与数据目录；只读 parquet（与 research 脚本同一读接口）。
- 不按结果调参；窗口/阈值全部取自 research 现有冻结规格。
- 系统侧列统一加 sys_ 前缀，避免与 research 同名冲突。

运行：
  cd C:\\work\\sourcecode\\tick-stock-panel\\backend
  .\\.venv\\Scripts\\python.exe ..\\docs\\research\\factor-audit-20261107\\scripts\\audit_compare.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve()
PROJECT = HERE.parents[4]           # .../<repo>/docs/research/<dir>/scripts/x.py
BACKEND = PROJECT / "backend"
RESEARCH_SCRIPTS = PROJECT / "research" / "strategy-search-20261107" / "scripts"
OUT_DIR = HERE.parents[1]
for p in (str(BACKEND), str(RESEARCH_SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import common as C  # noqa: E402  (research 只读设施)

from app.factors.dsl import FACTOR_COLUMN, compile_formula_cached  # noqa: E402
from app.indicators.pipeline import compute_indicators  # noqa: E402
from app.strategy.scoring import materialize_scoring_columns  # noqa: E402

STATS: dict = {"meta": {}, "pairs": {}, "signals": {}, "capability": {}, "series": {}}


def _stats(d: pl.DataFrame, a: str, b: str) -> dict:
    n = d.height
    if n == 0:
        return {"n": 0}
    diff = (d[a] - d[b]).abs()
    rel = (d[a] - d[b]).abs() / d[b].abs().clip(lower_bound=1e-12)
    return {
        "n": n,
        "corr_pearson": float(d.select(pl.corr(a, b)).item()),
        "corr_spearman": float(d.select(pl.corr(a, b, method="spearman")).item()),
        "mean_a": float(d[a].mean()),
        "mean_b": float(d[b].mean()),
        "mean_abs_diff": float(diff.mean()),
        "median_abs_diff": float(diff.median()),
        "p95_abs_diff": float(diff.quantile(0.95)),
        "max_abs_diff": float(diff.max()),
        "mean_rel_diff": float(rel.mean()),
        "p95_rel_diff": float(rel.quantile(0.95)),
    }


def pair(df: pl.DataFrame, a: str, b: str) -> dict:
    d = df.select(a, b).drop_nulls()
    out = _stats(d, a, b)
    if out["n"]:
        out["samples"] = (
            df.select("symbol", "date", a, b)
            .drop_nulls()
            .with_columns((pl.col(a) - pl.col(b)).abs().alias("abs_diff"))
            .sort("abs_diff", descending=True)
            .head(5)
            .to_dicts()
        )
    return out


def sig_diff(df: pl.DataFrame, cond_a: pl.Expr, cond_b: pl.Expr) -> dict:
    """两个布尔条件的判定差异（只在两侧都可判定的行上比较）。"""
    d = df.select(
        cond_a.alias("a"), cond_b.alias("b")
    ).drop_nulls()
    if d.height == 0:
        return {"n": 0}
    both_true = int(d.select((pl.col("a") & pl.col("b")).sum()).item())
    both_false = int(d.select((~pl.col("a") & ~pl.col("b")).sum()).item())
    only_a = int(d.select((pl.col("a") & ~pl.col("b")).sum()).item())
    only_b = int(d.select((~pl.col("a") & pl.col("b")).sum()).item())
    return {
        "n": d.height,
        "both_true": both_true,
        "only_a": only_a,
        "only_b": only_b,
        "both_false": both_false,
        "jaccard": both_true / max(both_true + only_a + only_b, 1),
        "disagree_share": (only_a + only_b) / d.height,
    }


def main() -> None:
    t0 = time.time()
    m = C.open_market()
    frame = C.load_panel(m)
    STATS["meta"] = {
        "rows": frame.height,
        "symbols": frame["symbol"].n_unique(),
        "date_min": str(frame["date"].min()),
        "date_max": str(frame["date"].max()),
        "eval_start": str(C.EVAL_START),
        "project": str(PROJECT),
    }
    STATS["meta"]["load_seconds"] = round(time.time() - t0, 1)

    # ---------- research 口径 ----------
    f = C.add_indicators(frame)
    f = C.add_universe(f)

    # ---------- 系统口径（全部加 sys_ 前缀） ----------
    base_cols = [
        "symbol", "date", "open", "high", "low", "close",
        "volume", "amount", "raw_close", "raw_high", "raw_low",
    ]
    need = {
        "rsi_14", "high_60d", "low_60d", "annual_vol_20d",
        "boll_upper", "boll_lower", "ma20", "ma60", "ma120", "ma200", "vol60",
        "vol_ma5", "vol_ma10", "vol_ratio_5d", "amplitude", "atr_14",
        "momentum_5d", "momentum_20d", "momentum_60d", "momentum_120d", "change_pct",
    }
    g = compute_indicators(f.select(base_cols), needed=need, assume_sorted=True)
    STATS["capability"]["compute_indicators_columns"] = sorted(g.columns)
    for absent in ("ma120", "ma200", "vol60", "prior_high55", "prior_low10",
                   "prior_vol20", "prior_amount20", "sd20", "market_breadth"):
        STATS["capability"][f"present_{absent}"] = absent in g.columns

    virt = [
        "amount_mean_20d", "distance_to_high_240d", "boll_position", "position_240d",
        "vol_ratio_10d", "turnover_mean_20d", "momentum_120d",
    ]
    g = materialize_scoring_columns(g, virt)
    STATS["capability"]["virtual_columns"] = {v: (v in g.columns) for v in virt}

    rename = {
        c: f"sys_{c}" for c in g.columns
        if c not in ("symbol", "date") and c not in base_cols
    }
    g = g.rename(rename)
    g = g.select(["symbol", "date"] + [v for v in rename.values() if v in g.columns])
    df = f.join(g, on=["symbol", "date"], how="left").filter(
        pl.col("date") >= C.EVAL_START
    )
    STATS["meta"]["eval_rows"] = df.height

    # ============ A. 精确一致核对（应逐位相同） ============
    STATS["pairs"]["ret20_vs_momentum_20d"] = pair(df, "ret20", "sys_momentum_20d")
    STATS["pairs"]["ret5_vs_momentum_5d"] = pair(df, "ret5", "sys_momentum_5d")
    STATS["pairs"]["ret60_vs_momentum_60d"] = pair(df, "ret60", "sys_momentum_60d")
    STATS["pairs"]["ret120_vs_momentum_120d"] = pair(df, "ret120", "sys_momentum_120d")
    STATS["pairs"]["ret1_vs_change_pct"] = pair(df, "ret1", "sys_change_pct")
    STATS["pairs"]["ma20_research_vs_system"] = pair(df, "ma20", "sys_ma20")
    STATS["pairs"]["ma60_research_vs_system"] = pair(df, "ma60", "sys_ma60")
    STATS["pairs"]["bb_lower_vs_boll_lower"] = pair(df, "bb_lower", "sys_boll_lower")
    STATS["pairs"]["bb_upper_vs_boll_upper"] = pair(df, "bb_upper", "sys_boll_upper")

    # ============ B. 口径不一致（数值差异） ============
    # rsi14 的分母 _al 为 0 时 research 侧产出 inf/NaN（无零保护），系统侧为 0.0；
    # 先在有限值子集上比对数值，再单独统计非有限值占比。
    STATS["capability"]["rsi14_null_rows"] = int(df["rsi14"].is_null().sum())
    STATS["capability"]["rsi14_nonfinite_or_null_rows"] = int(
        df.select((~pl.col("rsi14").is_finite().fill_null(False)).sum()).item()
    )
    finite = df.filter(pl.col("rsi14").is_finite().fill_null(False))
    STATS["capability"]["rsi14_finite_rows"] = finite.height
    STATS["pairs"]["rsi14_vs_rsi_14"] = pair(finite, "rsi14", "sys_rsi_14")
    STATS["signals"]["rsi_lt30"] = sig_diff(
        df, pl.col("rsi14") < 30, pl.col("sys_rsi_14") < 30
    )
    STATS["signals"]["rsi_gt55"] = sig_diff(
        df, pl.col("rsi14") > 55, pl.col("sys_rsi_14") > 55
    )

    # high_60d：三种口径对照
    d2 = df.with_columns(
        pl.col("high").shift(1).rolling_max(60).over("symbol").alias("prior_high60_H"),
        pl.col("close").shift(1).rolling_max(60).over("symbol").alias("prior_high60_C"),
    )
    STATS["pairs"]["prior_high55_vs_high_60d"] = pair(d2, "prior_high55", "sys_high_60d")
    STATS["pairs"]["prior_high55_vs_prior_high60_C"] = pair(d2, "prior_high55", "prior_high60_C")
    STATS["pairs"]["prior_high55_vs_prior_high60_H"] = pair(d2, "prior_high55", "prior_high60_H")
    STATS["pairs"]["high_60d_vs_prior_high60_C"] = pair(d2, "sys_high_60d", "prior_high60_C")
    STATS["signals"]["s09_break_vs_high_60d"] = sig_diff(
        d2, pl.col("close") > pl.col("prior_high55"), pl.col("close") > pl.col("sys_high_60d")
    )
    STATS["signals"]["s09_break_vs_prior_high60_C"] = sig_diff(
        d2, pl.col("close") > pl.col("prior_high55"), pl.col("close") > pl.col("prior_high60_C")
    )

    # 52 周新高
    STATS["pairs"]["dist_52w_high_vs_distance_to_high_240d"] = pair(
        df, "dist_52w_high", "sys_distance_to_high_240d"
    )
    STATS["signals"]["near_high_3pct"] = sig_diff(
        df, pl.col("dist_52w_high") >= -0.03,
        pl.col("sys_distance_to_high_240d") >= -0.03,
    )

    # 波动率
    STATS["pairs"]["vol60_vs_annual_vol_20d"] = pair(df, "vol60", "sys_annual_vol_20d")
    d3 = df.with_columns((pl.col("vol60") * (252 ** 0.5)).alias("vol60_ann"))
    STATS["pairs"]["vol60_ann_vs_annual_vol_20d"] = pair(d3, "vol60_ann", "sys_annual_vol_20d")
    STATS["pairs"]["sd20_vs_implied_sd"] = pair(
        df.with_columns(((pl.col("sys_boll_upper") - pl.col("sys_boll_lower")) / 4.0).alias("implied_sd")),
        "sd20", "implied_sd",
    )

    # 布林 z 分数与 boll_position 的可逆关系
    d4 = df.with_columns((4.0 * (pl.col("sys_boll_position") - 0.5)).alias("z_from_position"))
    STATS["pairs"]["bb_z_vs_4x_boll_position_minus_2"] = pair(d4, "bb_z", "z_from_position")

    # 量能阈值
    d5 = df.with_columns(
        pl.col("volume").rolling_mean(20).over("symbol").alias("vol_ma20_incl_today")
    )
    STATS["pairs"]["prior_vol20_vs_vol_ma20_incl_today"] = pair(
        d5, "prior_vol20", "vol_ma20_incl_today"
    )
    STATS["signals"]["s09_vol_1p5"] = sig_diff(
        d5,
        pl.col("volume") > 1.5 * pl.col("prior_vol20"),
        pl.col("sys_vol_ratio_5d") > 1.5,
    )
    STATS["signals"]["s09_vol_1p5_vs_ma10"] = sig_diff(
        d5,
        pl.col("volume") > 1.5 * pl.col("prior_vol20"),
        pl.col("volume") > 1.5 * pl.col("sys_vol_ma10"),
    )
    STATS["pairs"]["prior_vol20_vs_vol_ma10"] = pair(df, "prior_vol20", "sys_vol_ma10")
    STATS["pairs"]["prior_vol20_vs_vol_ma5"] = pair(df, "prior_vol20", "sys_vol_ma5")

    # 成交额
    d6 = df.with_columns(
        (pl.col("amount") / 1e8).alias("amount_yi"),
        (pl.col("prior_amount20") / 1e8).alias("prior_amount20_yi"),
    )
    STATS["pairs"]["prior_amount20_yi_vs_amount_mean_20d"] = pair(
        d6, "prior_amount20_yi", "sys_amount_mean_20d"
    )
    STATS["signals"]["universe_amount_1e8"] = sig_diff(
        d6,
        pl.col("prior_amount20") >= 1e8,
        pl.col("sys_amount_mean_20d") >= 1.0,
    )

    # ============ C. 截面排名：research vs DSL ============
    compiled = compile_formula_cached("rank(momentum_20d)")
    STATS["capability"]["dsl_rank_ok"] = bool(getattr(compiled, "ok", False))
    STATS["capability"]["dsl_rank_warmup"] = int(getattr(compiled, "warmup_bars", -1))
    if getattr(compiled, "ok", False):
        df = df.with_columns(pl.col("sys_momentum_20d").alias("momentum_20d"))
        transformed = compiled.frame_transform(df)
        if transformed is not None and FACTOR_COLUMN in transformed.columns:
            df = df.join(
                transformed.select("symbol", "date", pl.col(FACTOR_COLUMN).alias("rk_dsl")),
                on=["symbol", "date"], how="left",
            )
            df = df.with_columns(
                pl.when(pl.col("in_universe") & pl.col("ret20").is_not_null())
                .then(pl.col("rk_dsl"))
                .otherwise(None)
                .alias("rk_dsl_univ")
            )
            STATS["pairs"]["rk_ret20_vs_rk_dsl"] = pair(df, "rk_ret20", "rk_dsl")
            STATS["pairs"]["rk_ret20_vs_rk_dsl_univ"] = pair(df, "rk_ret20", "rk_dsl_univ")
            STATS["signals"]["xs_top10_ret20"] = sig_diff(
                df.filter(pl.col("month_end")),
                pl.col("rk_ret20") <= 0.10,
                pl.col("rk_dsl_univ") <= 0.10,
            )

    # ============ D. 市场宽度（无系统对应） ============
    breadth = (
        df.filter(pl.col("market_breadth").is_not_null())
        .group_by("date")
        .agg(pl.col("market_breadth").first().alias("breadth"))
        .sort("date")
    )
    STATS["series"]["market_breadth"] = {
        "n_days": breadth.height,
        "mean": float(breadth["breadth"].mean()),
        "p05": float(breadth["breadth"].quantile(0.05)),
        "p50": float(breadth["breadth"].quantile(0.50)),
        "p95": float(breadth["breadth"].quantile(0.95)),
        "share_days_below_0p5": float((breadth["breadth"] < 0.5).mean()),
    }
    me = df.filter(pl.col("month_end")).select("date", "market_breadth").unique()
    STATS["series"]["market_breadth_month_end"] = {
        "n_month_ends": me.height,
        "share_pass_ge_0p5": float((me["market_breadth"] >= 0.5).mean()),
    }

    # ============ E. 缺失项的量级参考 ============
    d7 = df.with_columns(
        (pl.col("close") / pl.col("close").rolling_mean(120).over("symbol") - 1).alias("ma120_bias_ref"),
        (pl.col("close") / pl.col("close").rolling_mean(200).over("symbol") - 1).alias("ma200_bias_ref"),
    )
    for col in ("ma120_bias_ref", "ma200_bias_ref"):
        STATS["series"][col] = {
            "mean": float(d7[col].mean()),
            "p05": float(d7[col].quantile(0.05)),
            "p50": float(d7[col].quantile(0.50)),
            "p95": float(d7[col].quantile(0.95)),
            "share_above": float((d7[col] > 0).mean()),
        }
    STATS["series"]["prior_low10_missing"] = {
        "note": "系统只有 low_60d(收盘, 含当日, 60 窗口)；prior_low10 为 low+shift(1)+10 窗口",
        "share_rows_where_close_below_prior_low10": float(
            (df["close"] < df["prior_low10"]).mean()
        ),
        "share_rows_where_close_below_low_60d": float(
            (df["close"] < df["sys_low_60d"]).mean()
        ),
    }
    STATS["series"]["vol60_dist"] = {
        "p10": float(df["vol60"].quantile(0.10)),
        "p50": float(df["vol60"].median()),
        "p90": float(df["vol60"].quantile(0.90)),
    }
    STATS["meta"]["seconds"] = round(time.time() - t0, 1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "compare_stats.json"
    out.write_text(
        json.dumps(STATS, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"wrote {out} in {STATS['meta']['seconds']}s")


if __name__ == "__main__":
    main()
