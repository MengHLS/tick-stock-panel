#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""独立审核脚本 A：uf_dist_prior_high_250 vs 研究侧 dist_52w_high。

独立实现（不复用 research/factor-registration-b2-*/dist_prior_high_250_parity.py，
也不调用 common.add_indicators）：研究侧用 polars 原生 shift+rolling_max 现写，
系统侧只用 app.factors.dsl.compile_formula 编译**磁盘上那份 json 的 formula 文本**。

口径：docs/research/caliber-decisions-20261107.md
  prior_high_250 = ts_delay(ts_max(high, 250), 1)
  dist_prior_high_250 = close / prior_high_250 - 1
  判据：max_abs_diff < 1e-12；jaccard(dist >= -0.03)；分母 <=0 / 空值；首根非空。

只读：D:\\TSP\\data 仅读取；脚本内含前后 sha256 对照，零写操作。
运行：backend/.venv/Scripts/python.exe -X utf8 research/independent-review-20261107/scripts/a_dist_prior_high_250_parity.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings  # noqa: E402
from app.extensions.adapters import FileMarketData  # noqa: E402
from app.factors.dsl import FACTOR_COLUMN, compile_formula  # noqa: E402

FACTOR_ID = "uf_dist_prior_high_250"
CUSTOM_DIR = Path(settings.data_dir) / "user_data" / "custom_factors"
TARGET_JSON = CUSTOM_DIR / f"{FACTOR_ID}.json"

WARMUP_START = date(2018, 1, 8)
EVAL_START = date(2019, 7, 1)
EVAL_END = date(2026, 10, 30)
TOL = 1e-12
THRESHOLD = -0.03
COLS = ["symbol", "date", "high", "close", "volume", "amount", "raw_close", "open", "low"]


def snapshot_prod() -> dict:
    out = {}
    for fn in sorted(os.listdir(CUSTOM_DIR)):
        p = CUSTOM_DIR / fn
        b = p.read_bytes()
        out[fn] = {
            "bytes": len(b),
            "sha256": hashlib.sha256(b).hexdigest(),
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
        }
    return out


def main() -> int:
    rows: list[tuple[str, object, str]] = []

    def rec(name: str, value, note: str = "") -> None:
        rows.append((name, value, note))
        print(f"{name}: {value}   {note}")

    snap0 = snapshot_prod()
    target = json.loads(TARGET_JSON.read_text(encoding="utf-8"))
    formula = target["formula"]
    rec("target_json_bytes", snap0[TARGET_JSON.name]["bytes"])
    rec("target_json_sha256", snap0[TARGET_JSON.name]["sha256"])
    rec("target_json_mtime", snap0[TARGET_JSON.name]["mtime"])
    rec("target_json_version", target.get("version"))
    rec("target_json_status", target.get("status"))
    rec("target_json_lang", target.get("lang"))
    rec("formula_text", repr(formula))

    # ---------------- 编译（系统侧真实路径）
    compiled = compile_formula(formula)
    rec("dsl_compile_ok", compiled.ok)
    rec("dsl_errors", [f"{e.code}:{e.message}" for e in compiled.errors])
    rec("dsl_dependencies", sorted(compiled.dependencies))
    rec("dsl_warmup_bars", compiled.warmup_bars)
    if not compiled.ok or compiled.frame_transform is None:
        print("FAIL: 公式无法编译，停止")
        return 2

    # ---------------- 数据（独立读取，不经 common.load_panel）
    market = FileMarketData(settings.data_dir)
    frame = market.get_daily_batch([], WARMUP_START, EVAL_END, COLS)
    frame = frame.filter(
        pl.col("symbol").str.starts_with("60") | pl.col("symbol").str.starts_with("00")
    ).sort(["symbol", "date"])
    rec("frame_rows", frame.height)
    rec("frame_symbols", frame["symbol"].n_unique())
    rec("frame_date_min", str(frame["date"].min()))
    rec("frame_date_max", str(frame["date"].max()))

    # ---------------- 研究侧（我自己的写法，等价于 common.py add_indicators 的两行）
    res = frame.select(
        "symbol", "date", "close", "high",
        (pl.col("high").shift(1).rolling_max(250).over("symbol")).alias("den_research"),
    ).with_columns(
        (pl.col("close") / pl.col("den_research") - 1).alias("dist_research")
    )

    # ---------------- 系统侧（生产物化同一函数）
    transformed = compiled.frame_transform(frame)
    if transformed is None:
        print("FAIL: frame_transform 返回 None（缺列）")
        return 3
    sysdf = transformed.select(
        "symbol", "date", "close", "high", FACTOR_COLUMN
    ).rename({FACTOR_COLUMN: "dist_system"})

    # 系统侧分母：单独再算一次（只用 DSL 的同一实现无法直接取中间量，
    # 故用第二条 DSL 公式把分母单独物化，确证分母本身而非只对最终值）
    den_compiled = compile_formula("ts_delay(ts_max(high, 250), 1)")
    den_tr = den_compiled.frame_transform(frame)
    den_sys = den_tr.select("symbol", "date", FACTOR_COLUMN).rename({FACTOR_COLUMN: "den_system"})

    # ---------------- 拼接（按 symbol/date 严格一对一对齐）
    both = res.join(sysdf, on=["symbol", "date"], how="full", coalesce=True).join(
        den_sys, on=["symbol", "date"], how="full", coalesce=True
    )
    rec("join_rows", both.height)
    rec("join_rowcount_matches_frame", both.height == frame.height)

    def stats(df: pl.DataFrame, tag: str) -> None:
        d = df.select(
            pl.len().alias("n"),
            pl.col("dist_research").is_null().sum().alias("null_res"),
            pl.col("dist_system").is_null().sum().alias("null_sys"),
            (
                pl.col("dist_research").is_null() != pl.col("dist_system").is_null()
            ).sum().alias("null_mismatch"),
            (
                (pl.col("dist_research") - pl.col("dist_system")).abs()
            ).max().alias("max_abs_diff"),
            (
                (pl.col("dist_research") - pl.col("dist_system")).abs() > TOL
            ).sum().alias("over_tol"),
            (
                (pl.col("dist_research") - pl.col("dist_system")) != 0
            ).sum().alias("nonzero_diff"),
        )
        r = d.row(0, named=True)
        for k, v in r.items():
            rec(f"{tag}_{k}", v)

        # 分母
        dd = df.select(
            (pl.col("den_system") < 0).sum().alias("den_lt0"),
            (pl.col("den_system") == 0).sum().alias("den_eq0"),
            pl.col("den_system").is_null().sum().alias("den_null"),
            (pl.col("den_research") < 0).sum().alias("den_res_lt0"),
            pl.col("den_research").is_null().sum().alias("den_res_null"),
            (pl.col("den_system") - pl.col("den_research")).abs().max().alias("den_max_abs_diff"),
            ((pl.col("den_system") - pl.col("den_research")) != 0).sum().alias("den_nonzero"),
            pl.col("dist_system").is_infinite().sum().alias("sys_inf"),
            pl.col("dist_research").is_infinite().sum().alias("res_inf"),
        )
        for k, v in dd.row(0, named=True).items():
            rec(f"{tag}_{k}", v)

        # jaccard on dist >= -0.03（null 视为 False，与研究侧 fill_null(False) 一致）
        j = df.select(
            (
                (pl.col("dist_system") >= THRESHOLD).fill_null(False)
                & (pl.col("dist_research") >= THRESHOLD).fill_null(False)
            ).sum().alias("both_true"),
            (
                (pl.col("dist_system") >= THRESHOLD).fill_null(False)
                & ~(pl.col("dist_research") >= THRESHOLD).fill_null(False)
            ).sum().alias("sys_only"),
            (
                ~(pl.col("dist_system") >= THRESHOLD).fill_null(False)
                & (pl.col("dist_research") >= THRESHOLD).fill_null(False)
            ).sum().alias("res_only"),
            (pl.col("dist_system") >= THRESHOLD).fill_null(False).sum().alias("sys_true"),
            (pl.col("dist_research") >= THRESHOLD).fill_null(False).sum().alias("res_true"),
            pl.len().alias("n"),
        ).row(0, named=True)
        union = j["both_true"] + j["sys_only"] + j["res_only"]
        jac = (j["both_true"] / union) if union else None
        for k, v in j.items():
            rec(f"{tag}_{k}", v)
        rec(f"{tag}_jaccard", f"{jac:.10f}" if jac is not None else None)
        rec(f"{tag}_sys_trigger_pct", f"{100.0 * j['sys_true'] / j['n']:.6f}")
        rec(f"{tag}_res_trigger_pct", f"{100.0 * j['res_true'] / j['n']:.6f}")

        # 首根非空
        nn = df.filter(pl.col("dist_system").is_not_null())
        rec(f"{tag}_first_nonnull_date_sys", str(nn["date"].min()) if nn.height else None)
        nnr = df.filter(pl.col("dist_research").is_not_null())
        rec(f"{tag}_first_nonnull_date_res", str(nnr["date"].min()) if nnr.height else None)
        rec(f"{tag}_nonnull_rows_sys", nn.height)

        # 逐 symbol 首根非空 bar 序号是否一致
        per = df.sort(["symbol", "date"]).with_columns(
            pl.int_range(pl.len()).over("symbol").alias("bar_idx")
        )
        f1 = per.filter(pl.col("dist_system").is_not_null()).group_by("symbol").agg(
            pl.col("bar_idx").min().alias("sys_first")
        )
        f2 = per.filter(pl.col("dist_research").is_not_null()).group_by("symbol").agg(
            pl.col("bar_idx").min().alias("res_first")
        )
        cmp = f1.join(f2, on="symbol", how="full", coalesce=True).select(
            pl.len().alias("symbols"),
            (pl.col("sys_first") != pl.col("res_first")).sum().alias("mismatch"),
        ).row(0, named=True)
        for k, v in cmp.items():
            rec(f"{tag}_first_bar_{k}", v)

    stats(both, "full")
    ev = both.filter((pl.col("date") >= EVAL_START) & (pl.col("date") <= EVAL_END))
    rec("eval_rows", ev.height)
    stats(ev, "eval")

    # ---------------- 生产目录未被我改动
    snap1 = snapshot_prod()
    rec("prod_files_before", len(snap0))
    rec("prod_files_after", len(snap1))
    rec("prod_diff_files", [k for k in snap1 if k not in snap0 or snap1[k] != snap0[k]])
    rec("target_sha256_after", snap1[TARGET_JSON.name]["sha256"])
    rec("target_unchanged", snap1[TARGET_JSON.name] == snap0[TARGET_JSON.name])

    out = Path(__file__).resolve().parents[1] / "artifacts" / "a_dist_prior_high_250_parity.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"factor": FACTOR_ID, "rows": [{"k": k, "v": str(v), "note": n} for k, v, n in rows],
                    "snapshot_before": snap0, "snapshot_after": snap1},
                   ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\nartifact: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
