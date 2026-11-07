"""独立审核用：复算契约 §3.4 / §4.6 / §5.6 的验收靶值（只读行情，不写研究产物）。

运行：
  cd C:\\work\\sourcecode\\tick-stock-panel\\backend
  .\\.venv\\Scripts\\python.exe ..\\research\\independent-review-20261107\\contract-review-20261107\\recheck_targets.py

输出：同目录 recheck_targets.json + stdout。
刻意不复用 docs/research/factor-audit-20261107/scripts/audit_xs_rank.py，
只复用研究侧 common.py（因为靶值的定义就是「与研究口径逐位相同」）。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve()
PROJECT = HERE.parents[3]
BACKEND = PROJECT / "backend"
RESEARCH = PROJECT / "research" / "strategy-search-20261107" / "scripts"
for p in (str(BACKEND), str(RESEARCH)):
    if p not in sys.path:
        sys.path.insert(0, p)

import common as C  # noqa: E402


def main() -> None:
    t0 = time.time()
    out: dict = {"meta": {}}
    m = C.open_market()
    f = C.add_indicators(C.load_panel(m))
    f = C.add_universe(f)
    f = f.filter((pl.col("date") >= C.EVAL_START) & (pl.col("date") <= C.EVAL_END))

    axis = f["date"].unique().sort()
    me = f.filter(pl.col("month_end"))["date"].unique()
    we = f.filter(pl.col("week_end"))["date"].unique()
    out["meta"] = {
        "rows": f.height,
        "symbols": f["symbol"].n_unique(),
        "axis_days": axis.len(),
        "month_end_days": me.len(),
        "week_end_days": we.len(),
        "date_min": str(axis.min()),
        "date_max": str(axis.max()),
        "universe": dict(C.UNIVERSE),
    }

    # ---- §3.4 选股数靶值（研究口径：分子=全样本名次，分母=池内家数）
    def sel_stats(cal: str, expr, label: str) -> dict:
        d = (
            f.filter(pl.col(cal))
            .group_by("date")
            .agg(expr.fill_null(False).sum().alias("n"))
        )
        return {"label": label, "rebuild_dates": d.height,
                "mean_sel": float(d["n"].mean()), "min_sel": int(d["n"].min()),
                "max_sel": int(d["n"].max())}

    u = pl.col("in_universe")
    out["sel_research"] = {
        "S06_ret5_le_0.05": sel_stats("week_end", u & (pl.col("rk_ret5") <= 0.05), "S06"),
        "S07_vol60_le_0.10": sel_stats("month_end", u & (pl.col("rk_vol60") <= 0.10), "S07"),
        "S10_ret20_le_0.10": sel_stats("month_end", u & (pl.col("rk_ret20") <= 0.10), "S10"),
        "S11_both_le_0.30": sel_stats(
            "month_end", u & (pl.col("rk_vol60") <= 0.30) & (pl.col("rk_ret20") <= 0.30), "S11"),
    }

    # ---- 系统现状口径（DSL rank：分母=当日非空样本数）用于对照 307.2/154.3/308.8/207.2
    f = f.with_columns([
        (pl.col(c).rank("average").over("date") / pl.col(c).count().over("date")).alias(f"sys_{c}")
        for c in ("ret5", "ret20", "vol60")
    ])
    def sys_stats(cal: str, expr) -> dict:
        d = f.filter(pl.col(cal)).group_by("date").agg(expr.fill_null(False).sum().alias("n"))
        return {"rebuild_dates": d.height, "mean_sel": float(d["n"].mean())}
    out["sel_system"] = {
        "S06": sys_stats("week_end", pl.col("sys_ret5") <= 0.05),
        "S07": sys_stats("month_end", pl.col("sys_vol60") <= 0.10),
        "S10": sys_stats("month_end", pl.col("sys_ret20") <= 0.10),
        "S11": sys_stats("month_end", (pl.col("sys_vol60") <= 0.30) & (pl.col("sys_ret20") <= 0.30)),
    }
    out["denominators"] = {
        "mean_in_universe": float(
            f.group_by("date").agg(pl.col("in_universe").sum().alias("n"))["n"].mean()),
        "mean_nonnull_vol60": float(
            f.group_by("date").agg(pl.col("vol60").count().alias("n"))["n"].mean()),
    }

    # ---- §4.6 市场宽度靶值
    d = (
        f.group_by("date")
        .agg(
            pl.when(pl.col("in_universe") & pl.col("ma60").is_not_null())
            .then((pl.col("close") > pl.col("ma60")).cast(pl.Float64))
            .otherwise(None).mean().alias("breadth_research"),
            pl.when(pl.col("ma60").is_not_null())
            .then((pl.col("close") > pl.col("ma60")).cast(pl.Float64))
            .otherwise(None).mean().alias("breadth_unmasked"),
        )
        .drop_nulls().sort("date")
    )
    dme = d.join(me.to_frame("date"), on="date", how="semi")
    out["breadth"] = {
        "n_days": d.height,
        "mean_research": float(d["breadth_research"].mean()),
        "mean_unmasked": float(d["breadth_unmasked"].mean()),
        "max_abs_diff_vs_unmasked": float(
            (d["breadth_research"] - d["breadth_unmasked"]).abs().max()),
        "month_ends": dme.height,
        "pass_rate_ge_0p5_research": float((dme["breadth_research"] >= 0.5).mean()),
        "pass_rate_ge_0p5_unmasked": float((dme["breadth_unmasked"] >= 0.5).mean()),
    }

    # ---- §3.2 值域核查：研究口径 rk 是否会 > 1
    out["rk_domain"] = {
        "max_rk_vol60": float(f["rk_vol60"].max()),
        "max_rk_ret5": float(f["rk_ret5"].max()),
        "max_rk_ret20": float(f["rk_ret20"].max()),
        "share_rows_rk_vol60_gt_1": float((f["rk_vol60"] > 1).mean()),
        "share_month_end_days_with_rk_gt_1": float(
            f.filter(pl.col("month_end")).group_by("date")
            .agg((pl.col("rk_vol60") > 1).any().alias("x"))["x"].mean()),
    }

    out["meta"]["seconds"] = round(time.time() - t0, 1)
    (HERE.parent / "recheck_targets.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
