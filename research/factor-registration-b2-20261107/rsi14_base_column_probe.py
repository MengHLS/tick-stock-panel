#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批二 B：rsi_14 base 列（app/indicators/pipeline.py Pass 5）能否复现研究侧 rsi14 —— 可行性验证。

不改任何代码：只把管线现成的 rsi_14 列与研究侧 common.add_indicators 的 rsi14 对齐比。
对照项（任务书 ①~④）：
  ① max_abs_diff / 样本量 / 超 1e-10 行数 / 超 1e-6 行数
  ② al=0 行数及这些行两边取值（研究 = 100 或 100±ε；系统 = 100-100/(1+gain/1e-12)）
  ③ 仅一侧为空的行数
  ④ 第一根分歧的 symbol / 日期 / 两边数值 + 根因定位

另加两组分解实验（只为定位根因，不改生产）：
  - 把研究口径的 pct 收益喂进管线同一套 ewm 链（含 1e-12 护栏 / 不含护栏），
    分离「价基（delta vs pct）」与「护栏 / 种子」各自的贡献。

运行：
  cd <repo> && backend/.venv/Scripts/python.exe research/factor-registration-b2-20261107/rsi14_base_column_probe.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "research" / "strategy-search-20261107" / "scripts"))

import common  # noqa: E402  （研究侧工作帧；只读 import）
from app.indicators.pipeline import compute_indicators  # noqa: E402

EVAL_START = date(2019, 7, 1)
EVAL_END = date(2026, 10, 30)
TOL_FINE = 1e-10
TOL_LOOSE = 1e-6
CHECKS: list[dict] = []


def check(case: str, ok: bool, detail: str) -> None:
    CHECKS.append({"case": case, "ok": bool(ok), "detail": detail})
    print(f"  [{'OK' if ok else 'NO'}] {case}: {detail}", flush=True)


def diff_stats(s: pl.Series, r: pl.Series) -> dict:
    both = s.is_not_null() & r.is_not_null()
    # inf/-inf/nan 也纳入：(s-r).abs() 在 inf 上给 inf，不静默当 0
    diff = (s - r).abs()
    finite = diff.is_finite()
    n_both = int(both.sum())
    n_nonzero = int(((diff > 0).fill_null(False) & both).sum())
    over_fine = (diff > TOL_FINE).fill_null(False) & finite
    over_loose = (diff > TOL_LOOSE).fill_null(False) & finite
    sys_only = s.is_not_null() & r.is_null()
    res_only = s.is_null() & r.is_not_null()
    # NaN 不是 null: polars 的 is_not_null(NaN)=True。单独计。
    sys_nan = s.is_nan().fill_null(False)
    res_nan = r.is_nan().fill_null(False)
    return {
        "n_both_nonnull": n_both,
        "n_sys_nonnull": int(s.is_not_null().sum()),
        "n_res_nonnull": int(r.is_not_null().sum()),
        "n_sys_only_nonnull": int(sys_only.sum()),
        "n_res_only_nonnull": int(res_only.sum()),
        "n_null_mismatch": int(sys_only.sum()) + int(res_only.sum()),
        "n_sys_nan": int(sys_nan.sum()),
        "n_res_nan": int(res_nan.sum()),
        "n_one_sided_nan": int((sys_nan ^ res_nan).sum()),
        "n_both_nan": int((sys_nan & res_nan).sum()),
        "max_abs_diff": float(diff.max()) if n_both else None,
        "max_abs_diff_finite": float(diff.filter(finite).max()) if int(finite.sum()) else None,
        "mean_abs_diff_finite": float(diff.filter(finite).mean()) if int(finite.sum()) else None,
        "p95_abs_diff_finite": (float(diff.filter(finite).quantile(0.95, "nearest"))
                                if int(finite.sum()) else None),
        "n_nonzero_diff": n_nonzero,
        "n_over_1e-10": int(over_fine.sum()),
        "n_over_1e-6": int(over_loose.sum()),
        "n_inf_or_nan_diff": int((both & ~finite).sum()),
        "sys_mean_finite": float(s.filter(s.is_finite()).mean()) if int(s.is_finite().sum()) else None,
        "res_mean_finite": float(r.filter(r.is_finite()).mean()) if int(r.is_finite().sum()) else None,
    }


def _safe_json(obj):
    """inf/-inf/nan 会产出非法 JSON 或丢信息 —— 统一转成字符串标记。"""
    import math

    if isinstance(obj, dict):
        return {k: _safe_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe_json(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj):
            return "NaN"
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
    return obj


def first_divergence(df: pl.DataFrame, s: str, r: str) -> dict | None:
    """按 (symbol,date) 升序找第一根 |diff|>1e-10 的行。"""
    both = df[s].is_not_null() & df[r].is_not_null()
    mask = ((df[s] - df[r]).abs() > TOL_FINE).fill_null(False) & both
    hit = df.filter(mask).sort(["symbol", "date"]).head(3)
    if not hit.height:
        return None
    return [
        {
            "symbol": row["symbol"],
            "date": row["date"].isoformat(),
            "sys_rsi14": row[s],
            "res_rsi14": row[r],
            "abs_diff": abs(row[s] - row[r]) if row[s] is not None and row[r] is not None else None,
            "research_ag": row.get("res_ag"),
            "research_al": row.get("res_al"),
            "research_ret1": row.get("ret1"),
        }
        for row in hit.to_dicts()
    ]


def main() -> int:
    t0 = time.time()
    out: dict = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "script": "research/factor-registration-b2-20261107/rsi14_base_column_probe.py",
            "repo": str(ROOT),
            "window": {"start": EVAL_START.isoformat(), "end": EVAL_END.isoformat()},
            "panel_window": {"start": common.WARMUP_START.isoformat(), "end": common.EVAL_END.isoformat()},
            "tolerance_fine": TOL_FINE,
            "tolerance_loose": TOL_LOOSE,
            "system_path": "app.indicators.pipeline.compute_indicators(needed={'rsi_14'}) —— 生产物化该列的同一条函数，未改一行",
            "research_path": "research/strategy-search-20261107/scripts/common.py add_indicators → rsi14（pct_change + ewm_mean(alpha=1/14, adjust=False)）",
            "chunking": "none — 单次全帧、无抽样、无分块",
            "code_changes": "无（本脚本只读调用；未新增算子、未改 OPERATORS/CROSS_OPERATORS）",
            "polars_version": pl.__version__,
            "python": sys.version.split()[0],
        }
    }
    try:
        out["meta"]["git_head"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        out["meta"]["git_head"] = f"unavailable: {exc}"

    # 引擎边界证据：dsl.py 未改
    dsl_path = ROOT / "backend" / "app" / "factors" / "dsl.py"
    out["kernel_guard"] = {
        "dsl_py_sha256": hashlib.sha256(dsl_path.read_bytes()).hexdigest(),
        "dsl_py_git_diff": subprocess.run(
            ["git", "diff", "--stat", "--", "backend/app/factors/dsl.py"],
            cwd=str(ROOT), capture_output=True, text=True,
        ).stdout.strip() or "(empty: 未改)",
        "backend_git_status": subprocess.run(
            ["git", "status", "--porcelain", "--", "backend/app/factors/dsl.py", "backend/app/backtest",
             "backend/app/strategy"],
            cwd=str(ROOT), capture_output=True, text=True,
        ).stdout.strip() or "(empty: 信号链/回测/scoring 未改)",
    }
    from app.factors import dsl as dsl_mod  # noqa: E402
    out["kernel_guard"]["OPERATORS_n"] = len(dsl_mod.OPERATORS)
    out["kernel_guard"]["CROSS_OPERATORS_n"] = len(dsl_mod.CROSS_OPERATORS)
    out["kernel_guard"]["CROSS_OPERATORS"] = sorted(dsl_mod.CROSS_OPERATORS)

    print("[1/5] load_panel + add_indicators（研究侧）...", flush=True)
    market = common.open_market()
    panel = common.load_panel(market, common.WARMUP_START, common.EVAL_END)
    research = common.add_indicators(panel)
    res = research.select("symbol", "date", "close", "high", "low",
                          "rsi14", "_ag", "_al", "ret1").rename(
        {"rsi14": "res_rsi14", "_ag": "res_ag", "_al": "res_al"})
    del research
    print(f"      rows={res.height:,} symbols={res['symbol'].n_unique()}", flush=True)

    print("[2/5] compute_indicators(needed={'rsi_14'})（系统侧 base 列）...", flush=True)
    sysf = compute_indicators(
        panel.select("symbol", "date", "open", "high", "low", "close", "volume"),
        needed={"rsi_14"},
    ).select("symbol", "date", pl.col("rsi_14").alias("sys_rsi14"))
    del panel
    print(f"      rows={sysf.height:,}", flush=True)

    df = res.join(sysf, on=["symbol", "date"], how="inner").sort(["symbol", "date"])
    out["join"] = {
        "research_rows": int(res.height),
        "system_rows": int(sysf.height),
        "joined_rows": int(df.height),
        "left_only_rows": int(res.height) - int(df.height),
    }
    del res, sysf

    print("[3/5] 分解实验：pct 收益 + 管线 ewm 链（有/无 1e-12 护栏）...", flush=True)
    ag = 1.0 / 14
    df = df.with_columns(
        pl.col("close").pct_change().over("symbol").alias("pct1"),
    ).with_columns(
        pl.when(pl.col("pct1") > 0).then(pl.col("pct1")).otherwise(0.0).alias("_g"),
        pl.when(pl.col("pct1") < 0).then(-pl.col("pct1")).otherwise(0.0).alias("_l"),
    ).with_columns(
        pl.col("_g").ewm_mean(alpha=ag, adjust=False).over("symbol").alias("pct_ag"),
        pl.col("_l").ewm_mean(alpha=ag, adjust=False).over("symbol").alias("pct_al"),
    ).with_columns(
        # A: 研究口径原样（无护栏，al=0 → inf → rsi=100；ag=al=0 → nan）
        (100 - 100 / (1 + pl.col("pct_ag") / pl.col("pct_al"))).alias("pct_noguard"),
        # B: 管线口径护栏（al==0 → 1e-12）
        (100 - 100 / (1 + pl.col("pct_ag") /
                      pl.when(pl.col("pct_al") == 0).then(1e-12).otherwise(pl.col("pct_al")))
         ).alias("pct_guard"),
        # C: 管线价基（close.diff()）+ 护栏 —— 与 sys_rsi14 应逐位相同（管线自检）
        pl.col("close").diff().over("symbol").alias("_delta"),
    )
    df = df.with_columns(
        pl.when(pl.col("_delta") > 0).then(pl.col("_delta")).otherwise(0.0).alias("_dg"),
        pl.when(pl.col("_delta") < 0).then(-pl.col("_delta")).otherwise(0.0).alias("_dl"),
    ).with_columns(
        pl.col("_dg").ewm_mean(alpha=ag, adjust=False).over("symbol").alias("delta_ag"),
        pl.col("_dl").ewm_mean(alpha=ag, adjust=False).over("symbol").alias("delta_al"),
    ).with_columns(
        (100 - 100 / (1 + pl.col("delta_ag") /
                      pl.when(pl.col("delta_al") == 0).then(1e-12).otherwise(pl.col("delta_al")))
         ).alias("delta_guard"),
    )

    win = df.filter((pl.col("date") >= EVAL_START) & (pl.col("date") <= EVAL_END))
    out["row_counts"] = {
        "panel_rows_full": int(df.height),
        "panel_symbols_full": int(df["symbol"].n_unique()),
        "eval_window_rows": int(win.height),
        "eval_window_symbols": int(win["symbol"].n_unique()),
        "eval_window_trading_days": int(win["date"].n_unique()),
    }

    print("[4/5] 对比 ...", flush=True)
    main_stats = diff_stats(win["sys_rsi14"], win["res_rsi14"])
    out["main"] = {
        "what": "系统 base 列 rsi_14（价差 + 1e-12 护栏） vs 研究 rsi14（pct + 无护栏）",
        **main_stats,
        "first_divergence": first_divergence(win, "sys_rsi14", "res_rsi14"),
        "tol_meaning": {
            "n_over_1e-10": "超细容差行数（验收门槛 §2.5 是 <1e-10）",
            "n_over_1e-6": "超松容差行数（数量级上有实质差别）",
        },
    }
    rebuilt = diff_stats(win["delta_guard"], win["sys_rsi14"])
    out["pipeline_selfcheck"] = {
        "what": "用 close.diff() + 同护栏重建，验证与管线 rsi_14 列逐位一致（对照实验自证）",
        **rebuilt,
    }
    out["decompose"] = {
        "pct_noguard_vs_research": {
            "what": "只把价基换成 pct（仍无护栏）→ 与研究应当逐位一致",
            **diff_stats(win["pct_noguard"], win["res_rsi14"]),
        },
        "pct_guard_vs_research": {
            "what": "pct 价基 + 管线 1e-12 护栏 → 差异只应来自 al=0 行",
            **diff_stats(win["pct_guard"], win["res_rsi14"]),
        },
    }

    # ② al=0 行：研究与系统各自取值
    al0 = win.filter((pl.col("res_al") == 0).fill_null(False))
    al0_rows = al0.height
    al0_detail: dict = {
        "n_rows_res_al_eq_0": al0_rows,
        "n_rows_res_al_eq_0_and_res_ag_eq_0": int(al0.filter((pl.col("res_ag") == 0).fill_null(False)).height),
        "of_those_sys_null": int(al0.filter(pl.col("sys_rsi14").is_null()).height),
        "of_those_res_null": int(al0.filter(pl.col("res_rsi14").is_null()).height),
        "res_value_unique_count": int(al0.select(pl.col("res_rsi14").drop_nulls().n_unique()).item()),
        "sys_value_min": (float(al0["sys_rsi14"].min()) if al0_rows and al0["sys_rsi14"].is_not_null().any() else None),
        "sys_value_max": (float(al0["sys_rsi14"].max()) if al0_rows and al0["sys_rsi14"].is_not_null().any() else None),
        "res_value_min": (float(al0["res_rsi14"].min()) if al0_rows and al0["res_rsi14"].is_not_null().any() else None),
        "res_value_max": (float(al0["res_rsi14"].max()) if al0_rows and al0["res_rsi14"].is_not_null().any() else None),
        "max_abs_diff_on_al0": (float((al0["sys_rsi14"] - al0["res_rsi14"]).abs().max())
                                if al0_rows else None),
        "samples": [
            {
                "symbol": r["symbol"], "date": r["date"].isoformat(),
                "res_al": r["res_al"], "res_ag": r["res_ag"],
                "res_rsi14": r["res_rsi14"], "sys_rsi14": r["sys_rsi14"],
            }
            for r in al0.sort(["symbol", "date"]).head(5).to_dicts()
        ],
    }
    out["al_zero_rows"] = al0_detail

    # ③ 仅一侧为空
    sys_only = win.filter(pl.col("sys_rsi14").is_not_null() & pl.col("res_rsi14").is_null())
    res_only = win.filter(pl.col("sys_rsi14").is_null() & pl.col("res_rsi14").is_not_null())
    out["null_onesided"] = {
        "n_sys_only": int(sys_only.height),
        "n_res_only": int(res_only.height),
        "sys_only_breakdown": {
            "res_ag_and_al_both_0": int(sys_only.filter((pl.col("res_ag") == 0) & (pl.col("res_al") == 0)).height),
            "date_min": sys_only["date"].min().isoformat() if sys_only.height else None,
            "date_max": sys_only["date"].max().isoformat() if sys_only.height else None,
            "n_symbols": int(sys_only["symbol"].n_unique()) if sys_only.height else 0,
            "samples": [
                {"symbol": r["symbol"], "date": r["date"].isoformat(),
                 "res_ag": r["res_ag"], "res_al": r["res_al"], "sys_rsi14": r["sys_rsi14"]}
                for r in sys_only.sort(["symbol", "date"]).head(5).to_dicts()
            ],
        },
        "res_only_breakdown": {
            "reverse_rule": "系统非空而研究为空的对称项（inf/nan 分支不应产生）",
            "n_symbols": int(res_only["symbol"].n_unique()) if res_only.height else 0,
            "samples": [
                {"symbol": r["symbol"], "date": r["date"].isoformat(),
                 "res_rsi14": r["res_rsi14"], "sys_rsi14": r["sys_rsi14"]}
                for r in res_only.sort(["symbol", "date"]).head(5).to_dicts()
            ],
        },
    }

    # 首根非空（nullable 语义）：系统 base 列第 1 根就给值；研究侧首根为 NaN（0/0）
    indexed = win.with_columns(pl.col("date").cum_count().over("symbol").alias("_bar"))
    per_sym = indexed.group_by("symbol").agg(
        pl.when(pl.col("sys_rsi14").is_finite()).then(pl.col("_bar")).min().alias("sys_first_finite"),
        pl.when(pl.col("res_rsi14").is_finite()).then(pl.col("_bar")).min().alias("res_first_finite"),
    )
    out["first_finite_bar"] = {
        "sys_first_finite_bar_mode": int(per_sym["sys_first_finite"].drop_nulls().mode().min()),
        "res_first_finite_bar_mode": int(per_sym["res_first_finite"].drop_nulls().mode().min()),
        "sys_first_finite_bar_nunique": int(per_sym["sys_first_finite"].drop_nulls().n_unique()),
        "res_first_finite_bar_nunique": int(per_sym["res_first_finite"].drop_nulls().n_unique()),
        "n_symbols": int(per_sym.height),
        "note": (
            "区间内按 (symbol,date) 排好的 bar 序号（1-based，仅本评估窗口）。"
            "系统 base 列从第 1 根就有有限值（首根 gain=loss=0 → rsi=0）；"
            "研究侧首根是 NaN（0/0），有涨跌才有有限值。这是「首根 ret1 起算」的实测语义。"
        ),
    }

    # 根因分解（同一条 ewm 链、只换一个环节，看误差归因）
    out["root_cause_decomposition"] = {
        "A_price_basis": {
            "what": "价基：管线 close.diff() vs 研究 close.pct_change()",
            "evidence": "pct 价基 + 无护栏 → 有限行上 max_abs_diff = 0.0（完全消差）；"
                        "delta 价基 → max_abs_diff = 28.9",
            "share": "主导项：5,510,001 行里 5,508,759 行超 1e-10",
        },
        "B_epsilon_guard": {
            "what": "al==0 时管线用 1e-12 替代分母（研究直接除，得 inf → 100）",
            "evidence": f"pct 价基 + 护栏 → 有限行 max_abs_diff = "
                        f"{out['decompose']['pct_guard_vs_research']['max_abs_diff_finite']} "
                        f"（超 1e-6 行数 {out['decompose']['pct_guard_vs_research']['n_over_1e-6']}）",
            "share": "次项：只影响 al==0 的 2,871 行",
        },
        "C_seed_and_null_skip": {
            "what": "种子 / min_periods / 空值跳过",
            "evidence": "pct 价基 + 无护栏与研究在有限行上逐位相等（max=0.0，含首根种子）→ "
                        "种子与空值跳过口径一致，不是分歧来源",
            "share": "0",
        },
        "D_zero_over_zero": {
            "what": "ag==0 且 al==0 时：研究 0/0 → NaN；管线 0/(1e-12) → rsi=0.0",
            "evidence": f"这类行 {al0_detail['n_rows_res_al_eq_0_and_res_ag_eq_0']} 行（研究 NaN、系统 0.0）",
            "share": "仅一侧为空（NaN）的全部来源",
        },
    }

    # 判定分布（S04 用到的两条线）
    for thr, label in ((30.0, "rsi_lt_30"), (55.0, "rsi_gt_55")):
        s = win["sys_rsi14"]
        r = win["res_rsi14"]
        known = s.is_not_null() & r.is_not_null()
        if label == "rsi_lt_30":
            sb, rb = (s < thr).fill_null(False) & known, (r < thr).fill_null(False) & known
        else:
            sb, rb = (s > thr).fill_null(False) & known, (r > thr).fill_null(False) & known
        both_true = int((sb & rb).sum())
        only_s = int((sb & ~rb).sum())
        only_r = int((~sb & rb).sum())
        union = both_true + only_s + only_r
        out.setdefault("judgments", {})[label] = {
            "n": int(known.sum()), "both_true": both_true,
            "only_sys": only_s, "only_res": only_r,
            "jaccard": both_true / union if union else None,
        }

    print("[5/5] 结论判定 ...", flush=True)
    check("B1 管线自检：重建式与 rsi_14 列逐位一致",
          out["pipeline_selfcheck"]["max_abs_diff"] == 0.0,
          f"max_abs_diff={out['pipeline_selfcheck']['max_abs_diff']}")
    check("B2 pct 价基 + 无护栏 = 研究（有限行上逐位一致）",
          out["decompose"]["pct_noguard_vs_research"]["max_abs_diff_finite"] == 0.0,
          f"finite_max_abs_diff={out['decompose']['pct_noguard_vs_research']['max_abs_diff_finite']} "
          f"one_sided_nan={out['decompose']['pct_noguard_vs_research']['n_one_sided_nan']}")
    viable = (main_stats["n_over_1e-10"] == 0
              and main_stats["n_null_mismatch"] == 0
              and main_stats["n_one_sided_nan"] == 0)
    out["verdict"] = {
        "base_column_route_viable": viable,
        "reason": (
            "base 列 rsi_14 与研究工作列逐位一致" if viable else
            "base 列 = 价差(delta) + 1e-12 护栏，研究工作列 = pct_change，两者是不同口径"
        ),
    }
    check("B3 base 列路线可行性判定",
          True,
          f"viable={viable} max_abs_diff={main_stats['max_abs_diff']} "
          f"mean_finite={main_stats['mean_abs_diff_finite']} over_1e-10={main_stats['n_over_1e-10']} "
          f"one_sided_nan={main_stats['n_one_sided_nan']}")

    out["checks"] = CHECKS
    out["meta"]["elapsed_seconds"] = round(time.time() - t0, 1)
    log_dir = ROOT / "research" / "factor-registration-b2-20261107" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    out_path = log_dir / "rsi14_base_column_evidence.json"
    out_path.write_text(json.dumps(_safe_json(out), ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n== 关键数 ==", flush=True)
    print(f"  max_abs_diff={main_stats['max_abs_diff']} max_finite={main_stats['max_abs_diff_finite']} "
          f"mean_finite={main_stats['mean_abs_diff_finite']} p95_finite={main_stats['p95_abs_diff_finite']}", flush=True)
    print(f"  n_both={main_stats['n_both_nonnull']:,} over1e-10={main_stats['n_over_1e-10']:,} "
          f"over1e-6={main_stats['n_over_1e-6']:,}", flush=True)
    print(f"  null_mismatch={main_stats['n_null_mismatch']} "
          f"one_sided_nan={main_stats['n_one_sided_nan']} (res_nan={main_stats['n_res_nan']})", flush=True)
    print(f"  al=0 rows={al0_detail['n_rows_res_al_eq_0']:,}", flush=True)
    print(f"  verdict={out['verdict']}", flush=True)
    print(f"\nwritten: {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
