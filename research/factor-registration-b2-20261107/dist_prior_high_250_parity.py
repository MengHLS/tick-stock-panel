#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批二 A：注册 uf_dist_prior_high_250 并逐位对账（零引擎改动）。

口径来源：
  - docs/research/caliber-decisions-20261107.md §1.1（距离型：close / prior_high_250 - 1）
    / §1.4 / §8.3.1；prior_high_250 = ts_delay(ts_max(high, N), 1)
  - 验收：§1.7 逐位判据（max_abs_diff、jaccard、首根非空、null 口径）
  - 注册：契约 §7.2 + F-A5（必须走 app.factors.store.upsert_definition 幂等入口）

做法：
  1. 生产目录 D:\\TSP\\data\\user_data\\custom_factors 只读快照（14 个 json 的
     version / bytes / sha256）——开工前。
  2. 研究侧 common.open_market/load_panel/add_indicators 同一帧取 dist_52w_high
     （= close / prior_high250 - 1，即规格里的 dist_prior_high_250）。
  3. 系统侧 app.factors.dsl.compile_formula(...).frame_transform(...)
     ——与 app/strategy/scoring.py 生产物化同一函数；两种等价写法都测。
  4. upsert_definition 注册（status=draft），再二次提交验证 unchanged=true。
  5. 比对：max_abs_diff / 超容差行数 / jaccard(dist>=-0.03) / 分母<=0 或空行数 /
     首根非空日期与非空行数。
  6. 生产目录再快照——14 个必须逐字节不变，只允许多出第 15 个新文件。

运行：
  cd <repo> && backend/.venv/Scripts/python.exe research/factor-registration-b2-20261107/dist_prior_high_250_parity.py
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
from app.config import settings  # noqa: E402
from app.factors import store as factor_store  # noqa: E402
from app.factors.dsl import FACTOR_COLUMN, compile_formula  # noqa: E402
from app.factors.registry import get_factor  # noqa: E402

EVAL_START = date(2019, 7, 1)
EVAL_END = date(2026, 10, 30)
TOL = 1e-12
THRESHOLD = -0.03          # S08 的 −3% 门槛
FACTOR_ID = "uf_dist_prior_high_250"

# 本次注册的公式（= 任务书字面写法）；分母 = prior_high_250
FORMULA = "close / ts_delay(ts_max(high, 250), 1) - 1"
# 等价写法（B0 的 prior_high_250 用这一种）：ts_max(ts_delay(high,1),250)
FORMULA_ALT = "close / ts_max(ts_delay(high, 1), 250) - 1"
RESEARCH_COL = "dist_52w_high"   # common.py add_indicators 里的实现列名

DEFINITION = {
    "id": FACTOR_ID,
    "kind": "custom",
    "label": "距此前250日最高价",
    "group": "研究补充",
    "formula": FORMULA,
    "lang": "dsl",
    "description": (
        "close / prior_high_250 - 1，prior_high_250 = ts_delay(ts_max(high,250),1)。"
        "输出为小数不是百分比（-3% = -0.03）。分子为当日 close，与分母同一复权序列；"
        "分母为 0 或空时由 DSL _safe_div 给 null。口径见 docs/research/"
        "caliber-decisions-20261107.md §1.1/§1.4/§8.3.1；研究源 "
        "research/strategy-search-20261107/scripts/common.py add_indicators。"
    ),
    "direction": "none",
    "status": "draft",
}

CHECKS: list[dict] = []


def check(case: str, ok: bool, detail: str) -> None:
    CHECKS.append({"case": case, "ok": bool(ok), "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {case}: {detail}", flush=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def custom_dir() -> Path:
    return Path(settings.data_dir) / "user_data" / "custom_factors"


def snapshot_prod() -> list[dict]:
    """生产目录只读快照: 文件 / id / version / 字节数 / sha256。"""
    directory = custom_dir()
    rows: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            payload = {}
        rows.append({
            "file": path.name,
            "id": payload.get("id"),
            "version": payload.get("version"),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    return rows


def compare(sys_series: pl.Series, res_series: pl.Series) -> dict:
    """逐位比较（两列行序一致）。"""
    both = sys_series.is_not_null() & res_series.is_not_null()
    diff = (sys_series - res_series).abs()
    over_tol = (diff > TOL).fill_null(False)
    sys_only = sys_series.is_not_null() & res_series.is_null()
    res_only = sys_series.is_null() & res_series.is_not_null()
    n_both = int(both.sum())
    n_nonzero = int((((diff > 0).fill_null(False)) & both).sum())
    return {
        "n_both_nonnull": n_both,
        "n_sys_nonnull": int(sys_series.is_not_null().sum()),
        "n_res_nonnull": int(res_series.is_not_null().sum()),
        "n_sys_only_nonnull": int(sys_only.sum()),
        "n_res_only_nonnull": int(res_only.sum()),
        "n_null_mismatch": int(sys_only.sum()) + int(res_only.sum()),
        "max_abs_diff": float(diff.max()) if n_both else None,
        "mean_abs_diff": float(diff.mean()) if n_both else None,
        "p95_abs_diff": float(diff.quantile(0.95, "nearest")) if n_both else None,
        "n_nonzero_diff": n_nonzero,
        "n_over_tol": int(over_tol.sum()),
        "tol": TOL,
    }


def first_nonnull(df: pl.DataFrame, sys_col: str, res_col: str) -> dict:
    """每 symbol 首根非空 bar（1-based）系统 vs 研究。"""
    indexed = df.with_columns(pl.col("date").cum_count().over("symbol").alias("_bar"))
    per = indexed.group_by("symbol").agg(
        pl.when(pl.col(sys_col).is_not_null()).then(pl.col("_bar")).min().alias("sys_first"),
        pl.when(pl.col(res_col).is_not_null()).then(pl.col("_bar")).min().alias("res_first"),
    )
    known = per.filter(pl.col("sys_first").is_not_null() & pl.col("res_first").is_not_null())
    mism = known.filter((pl.col("sys_first") - pl.col("res_first")) != 0)
    sys_nn = df.filter(pl.col(sys_col).is_not_null())
    res_nn = df.filter(pl.col(res_col).is_not_null())
    return {
        "n_symbols_compared": int(known.height),
        "n_symbols_first_bar_mismatch": int(mism.height),
        "mismatch_samples": [
            {"symbol": r["symbol"], "sys_first_bar": int(r["sys_first"]), "res_first_bar": int(r["res_first"])}
            for r in mism.sort("symbol").head(5).to_dicts()
        ],
        "panel_first_nonnull_date_sys": sys_nn["date"].min().isoformat() if sys_nn.height else None,
        "panel_first_nonnull_date_res": res_nn["date"].min().isoformat() if res_nn.height else None,
    }


def jaccard(a: pl.Series, b: pl.Series) -> dict:
    known = a.is_not_null() & b.is_not_null()
    a_f = a.fill_null(False) & known
    b_f = b.fill_null(False) & known
    both_true = int((a_f & b_f).sum())
    only_a = int((a_f & ~b_f).sum())
    only_b = int((~a_f & b_f).sum())
    n = int(known.sum())
    union = both_true + only_a + only_b
    return {
        "n": n,
        "both_true": both_true,
        "only_sys": only_a,
        "only_res": only_b,
        "both_false": n - union,
        "jaccard": (both_true / union) if union else None,
        "trigger_rate_sys": (both_true + only_a) / n if n else None,
        "trigger_rate_res": (both_true + only_b) / n if n else None,
    }


def main() -> int:
    t0 = time.time()
    out: dict = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "script": "research/factor-registration-b2-20261107/dist_prior_high_250_parity.py",
            "repo": str(ROOT),
            "data_dir": str(settings.data_dir),
            "custom_factor_dir": str(custom_dir()),
            "factor_id": FACTOR_ID,
            "formula": FORMULA,
            "formula_alt": FORMULA_ALT,
            "window": {"start": EVAL_START.isoformat(), "end": EVAL_END.isoformat()},
            "panel_window": {"start": common.WARMUP_START.isoformat(), "end": common.EVAL_END.isoformat()},
            "tolerance": TOL,
            "threshold": THRESHOLD,
            "chunking": "none — 单次全帧、无抽样、无分块",
            "system_path": "app.factors.dsl.compile_formula(...).frame_transform(...)（与 app/strategy/scoring.py 生产物化同函数）",
            "research_path": "research/strategy-search-20261107/scripts/common.py → add_indicators（只读 import）",
            "registration_path": "app.factors.store.upsert_definition（F-A5 幂等入口）",
            "polars_version": pl.__version__,
            "python": sys.version.split()[0],
        }
    }
    try:
        out["meta"]["git_head"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True, check=True
        ).stdout.strip()
        out["meta"]["git_branch"] = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(ROOT), capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        out["meta"]["git_head"] = f"unavailable: {exc}"

    print("[0/6] 生产目录快照（开工前）...", flush=True)
    log_dir = ROOT / "research" / "factor-registration-b2-20261107" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    base = "dist_prior_high_250"
    # 首跑写正典文件名；之后再跑另存带时间戳的一份（正典证据/基线快照不被覆盖）
    first_run = not (log_dir / f"{base}_evidence.json").exists() and not (log_dir / f"{base}_before.json").exists()
    suffix = "" if first_run else "_" + datetime.now().strftime("%H%M%S")
    baseline_path = log_dir / f"{base}_before.json"
    baseline = (
        json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else None
    )
    before = snapshot_prod()
    out["prod_before"] = before
    print(f"      {len(before)} 个 json", flush=True)

    print("[1/6] load_panel + add_indicators ...", flush=True)
    market = common.open_market()
    frame = common.load_panel(market, common.WARMUP_START, common.EVAL_END)
    research = common.add_indicators(frame)
    keep = ["symbol", "date", "close", "high", "observed_bars",
            "prior_high250", "dist_52w_high"]
    df = research.select(keep)
    del research, frame
    print(f"      rows={df.height:,} symbols={df['symbol'].n_unique()}", flush=True)

    # 分母自检：研究 prior_high250 vs 两种 DSL 写法，逐位比
    den = df.select(
        "symbol", "date", "high",
        pl.col("prior_high250").alias("res_den"),
        pl.col("high").shift(1).rolling_max(250).over("symbol").alias("res_recomputed"),
    )
    den_checks: dict[str, float | None] = {}
    for tag, formula in (("ts_delay_ts_max", "ts_delay(ts_max(high, 250), 1)"),
                         ("ts_max_ts_delay", "ts_max(ts_delay(high, 1), 250)")):
        c = compile_formula(formula)
        if not c.ok:
            raise SystemExit(f"denominator compile failed: {formula}")
        den = c.frame_transform(den)
        if den is None:
            raise SystemExit(f"denominator frame_transform None: {formula}")
        den = den.with_columns(den[FACTOR_COLUMN].alias(f"sys_{tag}")).drop(FACTOR_COLUMN)
        gap = (den["res_den"] - den[f"sys_{tag}"]).abs()
        den_checks[tag] = float(gap.max()) if gap.len() else None
        den_checks[f"{tag}_warmup"] = c.warmup_bars
    out["denominator_identity_check"] = {
        **den_checks,
        "research_recompute_self_check": float(
            (den["res_den"] - den["res_recomputed"]).abs().max()
        ),
        "note": "研究 prior_high250 = high.shift(1).rolling_max(250)；任务书写法 = ts_delay(ts_max(high,250),1)；B0 写法 = ts_max(ts_delay(high,1),250)。三者应逐位一致。",
    }
    print(f"      分母写法一致性: {den_checks}", flush=True)

    print("[2/6] 系统 DSL 求值（两种等价写法）...", flush=True)
    for tag, formula, expected in (("main", FORMULA, 251), ("alt", FORMULA_ALT, 251)):
        compiled = compile_formula(formula)
        if not compiled.ok:
            raise SystemExit(f"compile failed ({tag}): {[e.to_dict() for e in compiled.errors]}")
        if compiled.warmup_bars != expected:
            raise SystemExit(f"warmup mismatch ({tag}): {compiled.warmup_bars} != {expected}")
        transformed = compiled.frame_transform(df)
        if transformed is None:
            raise SystemExit(f"frame_transform returned None ({tag})")
        df = transformed.with_columns(transformed[FACTOR_COLUMN].alias(f"sys_{tag}")).drop(FACTOR_COLUMN)
        out.setdefault("compile", {})[tag] = {
            "formula": formula,
            "warmup_bars": compiled.warmup_bars,
            "dependencies": sorted(compiled.dependencies),
        }

    print("[3/6] 注册（upsert_definition，F-A5 幂等入口）...", flush=True)
    data_dir = Path(settings.data_dir)
    # API 建因子的同一口径: created_at 由调用方落（api/factors.py:348）；
    # upsert_definition 的首次创建分支只追加 updated_at，不会补 created_at。
    definition = dict(DEFINITION, created_at=datetime.now().isoformat(timespec="seconds"))
    reg = factor_store.upsert_definition(data_dir, definition)
    file_path = custom_dir() / f"{FACTOR_ID}.json"
    first_sha = sha256(file_path)
    out["registration_first"] = {
        **reg,
        "file": str(file_path),
        "file_bytes": file_path.stat().st_size,
        "file_sha256": first_sha,
        "on_disk": json.loads(file_path.read_text(encoding="utf-8")),
    }
    spec = get_factor(FACTOR_ID)
    out["registration_first"]["spec"] = {
        "id": spec.id,
        "label": spec.label,
        "group": spec.group,
        "kind": spec.kind,
        "version": spec.version,
        "warmup_bars": spec.warmup_bars,
        "dependencies": sorted(spec.dependencies),
        "stability": spec.stability,
    }

    # 二次提交同一内容 → 必须 unchanged=true 且不抬版本
    reg2 = factor_store.upsert_definition(data_dir, definition)
    out["registration_second"] = {
        **reg2,
        "file_sha256": sha256(file_path),
        "bytes_same": sha256(file_path) == first_sha,
        "version_after": get_factor(FACTOR_ID).version,
    }

    print("[4/6] 窗口过滤 + 行数 ...", flush=True)
    win = df.filter((pl.col("date") >= EVAL_START) & (pl.col("date") <= EVAL_END))
    out["row_counts"] = {
        "panel_rows_full": int(df.height),
        "panel_symbols_full": int(df["symbol"].n_unique()),
        "eval_window_rows": int(win.height),
        "eval_window_symbols": int(win["symbol"].n_unique()),
        "eval_window_trading_days": int(win["date"].n_unique()),
    }

    print("[5/6] 逐位对账 + 判决 ...", flush=True)
    parity: dict = {}
    for tag in ("main", "alt"):
        cmp = compare(win[f"sys_{tag}"], win[RESEARCH_COL])
        fnp = first_nonnull(df, f"sys_{tag}", RESEARCH_COL)
        sys_bool = win[f"sys_{tag}"] >= THRESHOLD
        res_bool = win[RESEARCH_COL] >= THRESHOLD
        parity[tag] = {
            "formula": FORMULA if tag == "main" else FORMULA_ALT,
            **cmp,
            **fnp,
            "judgment_dist_ge_minus_3pct": jaccard(sys_bool, res_bool),
        }
        j = parity[tag]["judgment_dist_ge_minus_3pct"]
        print(f"      {tag}: n={cmp['n_both_nonnull']:,} max_abs_diff={cmp['max_abs_diff']} "
              f"over_tol={cmp['n_over_tol']} null_mismatch={cmp['n_null_mismatch']} "
              f"jaccard={j['jaccard']}", flush=True)
    out["parity"] = parity

    # 分母 <=0 / ==0 / 空 的行数（证明与研究的 inf 分支无差异）
    def den_stats(scope: pl.DataFrame, name: str) -> dict:
        den = scope["prior_high250"]
        le0 = int(((den <= 0).fill_null(False)).sum())
        eq0 = int(((den == 0).fill_null(False)).sum())
        lt0 = int(((den < 0).fill_null(False)).sum())
        nulls = int(den.is_null().sum())
        rows = scope.filter((den <= 0).fill_null(False) | den.is_null())
        samples = [
            {
                "symbol": r["symbol"],
                "date": r["date"].isoformat(),
                "prior_high250": r["prior_high250"],
                "research_value": r[RESEARCH_COL],
                "system_value": r["sys_main"],
                "research_is_inf": r[RESEARCH_COL] is not None and abs(r[RESEARCH_COL]) == float("inf"),
            }
            for r in rows.sort(["date", "symbol"]).head(8).to_dicts()
        ]
        both = scope.select("prior_high250", RESEARCH_COL, "sys_main").filter(
            pl.col("prior_high250").is_not_null()
        ).select(
            ((pl.col(RESEARCH_COL).abs() == float("inf")).fill_null(False)).sum().alias("res_inf"),
        )
        return {
            "scope": name,
            "rows": int(scope.height),
            "den_le_0": le0,
            "den_lt_0": lt0,
            "den_eq_0": eq0,
            "den_null": nulls,
            "den_le_0_or_null": le0 + nulls,
            "research_inf_rows": int(both["res_inf"][0]),
            "samples": samples,
        }

    out["denominator_rows"] = {
        "eval_window": den_stats(win, "eval_window"),
        "full_panel": den_stats(df, "full_panel"),
    }

    # 非空行数（研究侧口径 vs 系统侧）
    out["nonnull_rows"] = {
        "eval_window_research": int(win[RESEARCH_COL].is_not_null().sum()),
        "eval_window_system": int(win["sys_main"].is_not_null().sum()),
        "full_panel_research": int(df[RESEARCH_COL].is_not_null().sum()),
        "full_panel_system": int(df["sys_main"].is_not_null().sum()),
    }

    print("[6/6] 生产目录快照（收工后）+ 判定 ...", flush=True)
    after = snapshot_prod()
    out["prod_after"] = after
    before_by_name = {r["file"]: r for r in before}
    after_by_name = {r["file"]: r for r in after}
    changed = [
        name for name, row in before_by_name.items()
        if name not in after_by_name
        or (after_by_name[name]["sha256"], after_by_name[name]["version"], after_by_name[name]["bytes"])
        != (row["sha256"], row["version"], row["bytes"])
    ]
    new_files = sorted(set(after_by_name) - set(before_by_name))
    out["prod_diff"] = {
        "before_count": len(before),
        "after_count": len(after),
        "changed_baseline_files": changed,
        "new_files": new_files,
    }
    # 与「首次注册前」的 14 个基线快照比（首跑之后重跑时，本次 before 已经是 15 个）
    baseline_diff: dict = {"available": baseline is not None}
    if baseline is not None:
        base_by_name = {r["file"]: r for r in baseline}
        now_by_name = {r["file"]: r for r in after}
        baseline_diff.update({
            "baseline_count": len(baseline),
            "changed_vs_baseline": [
                name for name, row in base_by_name.items()
                if name not in now_by_name
                or (now_by_name[name]["sha256"], now_by_name[name]["version"], now_by_name[name]["bytes"])
                != (row["sha256"], row["version"], row["bytes"])
            ],
            "added_vs_baseline": sorted(set(now_by_name) - set(base_by_name)),
            "removed_vs_baseline": sorted(set(base_by_name) - set(now_by_name)),
        })
    out["prod_vs_first_run_baseline"] = baseline_diff

    main_p = parity["main"]
    j = main_p["judgment_dist_ge_minus_3pct"]
    check("A1 编译 warmup=251 且 dependencies={close,high}",
          out["compile"]["main"]["warmup_bars"] == 251
          and out["compile"]["main"]["dependencies"] == ["close", "high"],
          f"warmup={out['compile']['main']['warmup_bars']} deps={out['compile']['main']['dependencies']}")
    check("A2 id 匹配 ^uf_[a-z0-9_]{1,40}$ 且 kind=custom / status=draft",
          file_path.name == f"{FACTOR_ID}.json"
          and out["registration_first"]["on_disk"]["status"] == "draft"
          and out["registration_first"]["on_disk"]["kind"] == "custom",
          f"{FACTOR_ID}.json status={out['registration_first']['on_disk']['status']}")
    check("A3 首次注册 version=1 且已进注册表",
          out["registration_first"]["version"] == 1
          and spec is not None and spec.version == 1
          and out["registration_first"]["on_disk"]["formula"] == FORMULA,
          f"version={out['registration_first']['version']} spec.version={spec.version}")
    check("A4 同内容二次注册 unchanged=true 且文件字节不变",
          reg2.get("unchanged") is True
          and out["registration_second"]["bytes_same"]
          and out["registration_second"]["version_after"] == 1,
          f"unchanged={reg2.get('unchanged')} bytes_same={out['registration_second']['bytes_same']} "
          f"version={out['registration_second']['version_after']}")
    check("A5 与研究工作列逐位一致 max_abs_diff=0",
          main_p["max_abs_diff"] == 0.0 and main_p["n_over_tol"] == 0,
          f"max_abs_diff={main_p['max_abs_diff']} n_both={main_p['n_both_nonnull']:,} "
          f"over_tol={main_p['n_over_tol']}")
    check("A6 两种公式写法数值一致",
          parity["alt"]["max_abs_diff"] == 0.0 and parity["alt"]["n_over_tol"] == 0,
          f"alt max_abs_diff={parity['alt']['max_abs_diff']}")
    check("A7 空值口径无差异（仅一侧为空=0）",
          main_p["n_null_mismatch"] == 0,
          f"sys_only={main_p['n_sys_only_nonnull']} res_only={main_p['n_res_only_nonnull']}")
    check("A8 dist>=-0.03 判定 jaccard=1.0",
          j["jaccard"] == 1.0,
          f"jaccard={j['jaccard']} n={j['n']:,} both_true={j['both_true']:,} "
          f"only_sys={j['only_sys']} only_res={j['only_res']}")
    check("A9 分母<=0 或空后研究侧无 inf 分支",
          out["denominator_rows"]["eval_window"]["research_inf_rows"] == 0,
          f"eval den<=0={out['denominator_rows']['eval_window']['den_le_0']} "
          f"den_null={out['denominator_rows']['eval_window']['den_null']} "
          f"research_inf={out['denominator_rows']['eval_window']['research_inf_rows']}")
    check("A10 首根非空逐 symbol 一致",
          main_p["n_symbols_first_bar_mismatch"] == 0
          and main_p["panel_first_nonnull_date_sys"] == main_p["panel_first_nonnull_date_res"],
          f"symbols={main_p['n_symbols_compared']} mismatch={main_p['n_symbols_first_bar_mismatch']} "
          f"first={main_p['panel_first_nonnull_date_sys']}")
    check("A11 生产目录既有文件逐字节未变（只允许新增本因子文件）",
          changed == []
          and set(new_files) <= {f"{FACTOR_ID}.json"}
          and baseline_diff.get("changed_vs_baseline", []) == []
          and set(baseline_diff.get("added_vs_baseline", [])) <= {f"{FACTOR_ID}.json"}
          and baseline_diff.get("removed_vs_baseline", []) == [],
          f"本次 {len(before)}→{len(after)} changed={changed} new={new_files}; "
          f"对首跑基线({baseline_diff.get('baseline_count')}) changed={baseline_diff.get('changed_vs_baseline')} "
          f"added={baseline_diff.get('added_vs_baseline')} removed={baseline_diff.get('removed_vs_baseline')}")

    out["checks"] = CHECKS
    out["summary"] = {
        "passed": sum(1 for c in CHECKS if c["ok"]),
        "total": len(CHECKS),
        "all_passed": all(c["ok"] for c in CHECKS),
    }
    out["meta"]["elapsed_seconds"] = round(time.time() - t0, 1)

    log_dir = ROOT / "research" / "factor-registration-b2-20261107" / "logs"
    (log_dir / f"{base}_before{suffix}.json").write_text(
        json.dumps(before, ensure_ascii=False, indent=1), encoding="utf-8")
    (log_dir / f"{base}_after{suffix}.json").write_text(
        json.dumps(after, ensure_ascii=False, indent=1), encoding="utf-8")
    out_path = log_dir / f"{base}_evidence{suffix}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n== 判定汇总 ==", flush=True)
    for c in CHECKS:
        print(f"  {'PASS' if c['ok'] else 'FAIL'}  {c['case']}: {c['detail']}", flush=True)
    print(f"\n{out['summary']['passed']}/{out['summary']['total']} 通过, "
          f"{out['meta']['elapsed_seconds']}s\nwritten: {out_path}", flush=True)
    return 0 if out["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
