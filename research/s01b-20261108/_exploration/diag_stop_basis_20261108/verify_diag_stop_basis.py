#!/usr/bin/env python
"""本诊断的自校验（只读）：用另一套实现重算关键数字，并核对上游文件字节未变。

用法（仓库根）：
    backend\\.venv\\Scripts\\python.exe research\\s01b-20261108\\diag_stop_basis_20261108\\verify_diag_stop_basis.py
退出码：0 全部通过；1 有判据失败（逐条打印）。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import polars as pl

ROOT = Path(r"C:\work\sourcecode\tick-stock-panel")
RES = ROOT / "research" / "s01b-20261108" / "results"
OUT = ROOT / "research" / "s01b-20261108" / "diag_stop_basis_20261108"
DATA = Path(r"D:\TSP\data")

# 开工自检时记录的锚点（派单给定 + 本次实测）
ANCHORS = {
    "backend/app/backtest/engine.py": (268800, "ecc3d8261c5605edd877f5a48863cb239700486a9167de610ea0db82ec184cbe"),
    "research/s01b-20261108/metrics_table.md": (2738, "d025d8ce96f98cc2a204d6a60c82b693306cdb15d0f597b6627d0070a915cf3a"),
    "research/s01b-20261108/REPORT.md": (52097, "e60cd0b857f40fb227dad704e62c6d132fbba9e5107f1c53ba3870c436d7ca9b"),
}

FAILS: list[str] = []
PASSES: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    (PASSES if ok else FAILS).append(f"{name}: {detail}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    # ---- 0. 上游文件字节未变 ----
    for rel, (size, digest) in ANCHORS.items():
        p = ROOT / rel
        check(f"unchanged {rel}", p.stat().st_size == size and sha256(p) == digest, f"{p.stat().st_size} B / {sha256(p)[:16]}…")

    # ---- 1. 输入/产物存在 ----
    for name in (
        "stop_loss_trades_evidence.csv",
        "all_519_basis_recompute.csv",
        "a0_counterfactual_stop8.csv",
        "summary_h1.json",
        "h2_pairs.csv",
        "summary_h2.json",
    ):
        check(f"artifact {name}", (OUT / name).stat().st_size > 0, f"{(OUT / name).stat().st_size} B")

    trades = pl.read_parquet(RES / "a1_10bp" / "trades.parquet")
    stats = json.loads((RES / "a1_10bp" / "result.json").read_text(encoding="utf-8"))
    ev = pl.read_csv(OUT / "stop_loss_trades_evidence.csv", infer_schema_length=0)
    allr = pl.read_csv(OUT / "all_519_basis_recompute.csv", infer_schema_length=0)
    h1 = json.loads((OUT / "summary_h1.json").read_text(encoding="utf-8"))
    h2 = json.loads((OUT / "summary_h2.json").read_text(encoding="utf-8"))
    pairs = pl.read_csv(OUT / "h2_pairs.csv", infer_schema_length=0)

    # ---- 2. 逐笔证据完整 ----
    check("trades_total", trades.height == 519 == allr.height, f"{trades.height} / {allr.height}")
    check(
        "stop_loss_count",
        ev.height == 425 == trades.filter(pl.col("exit_reason") == "stop_loss").height,
        f"evidence {ev.height}, trades {trades.filter(pl.col('exit_reason') == 'stop_loss').height}",
    )
    check(
        "evidence_all_stop_loss",
        ev.join(
            trades.select(["symbol", "entry_date", "exit_date", "exit_reason"]),
            on=["symbol", "entry_date", "exit_date"],
            how="left",
        )
        .filter(pl.col("exit_reason") != "stop_loss")
        .height
        == 0,
        "evidence 行回连 trades 后非 stop_loss 行数 = "
        + str(
            ev.join(
                trades.select(["symbol", "entry_date", "exit_date", "exit_reason"]),
                on=["symbol", "entry_date", "exit_date"],
                how="left",
            )
            .filter(pl.col("exit_reason") != "stop_loss")
            .height
        ),
    )
    check(
        "evidence_no_null_trigger",
        ev["trigger_day_raw"].null_count() == 0
        and ev["trigger_day_adj"].null_count()
        == sum(
            1
            for d in h1["trigger_rate"]["disagreements"]
            if d["trigger_day_adj"] is None and d["exit_reason"] == "stop_loss"
        ),
        f"raw nulls {ev['trigger_day_raw'].null_count()}, adj nulls {ev['trigger_day_adj'].null_count()}"
        f"（应为 raw=0 / adj=stop_loss 分歧数 {sum(1 for d in h1['trigger_rate']['disagreements'] if d['trigger_day_adj'] is None and d['exit_reason'] == 'stop_loss')}）",
    )
    required_cols = {
        "symbol",
        "entry_date",
        "exit_date",
        "entry_price_fill",
        "entry_day_close_raw",
        "exit_day_close_raw",
        "entry_day_adj_ratio",
        "adj_factor_entry",
        "exit_day_close_raw",
        "exit_day_adj_ratio",
        "adj_factor_exit",
        "stop_line_raw",
        "trigger_plane",
        "exit_on_first_session_after_entry",
    }
    check("evidence_columns", required_cols.issubset(set(ev.columns)), f"{len(ev.columns)} cols")

    # ---- 3. 用向量化另一套实现重算两套口径的触发率 ----
    symbols = sorted(set(trades["symbol"].to_list()))
    panel = (
        pl.scan_parquet(str(DATA / "kline_daily_enriched" / "date=*" / "*.parquet"))
        .select(["symbol", "date", "open", "high", "low", "close", "raw_close", "raw_low"])
        .filter(
            pl.col("symbol").is_in(symbols)
            & (pl.col("date") >= dt.date(2018, 12, 1))
            & (pl.col("date") <= dt.date(2026, 11, 2))
        )
        .collect()
    )
    panel = panel.with_columns(
        (pl.col("open") * pl.col("raw_close") / pl.col("close")).round(2).alias("raw_open_d"),
        (pl.col("low") * pl.col("raw_close") / pl.col("close")).round(2).alias("raw_low_d"),
    )
    tr = trades.with_columns(
        pl.col("entry_date").str.to_date().alias("ed"), pl.col("exit_date").str.to_date().alias("xd")
    ).select(["symbol", "ed", "xd", "entry_price"])
    w = panel.join(tr, on="symbol", how="inner").filter(
        (pl.col("date") >= pl.col("ed")) & (pl.col("date") <= pl.col("xd"))
    )
    w = w.with_columns(
        pl.when(pl.col("date") == pl.col("ed"))
        .then(pl.col("raw_close"))
        .otherwise(
            pl.min_horizontal(
                pl.col("raw_open_d").fill_nan(None), pl.col("raw_low_d").fill_nan(None)
            )
        )
        .alias("cand_raw"),
        pl.when(pl.col("date") == pl.col("ed"))
        .then(pl.col("close"))
        .otherwise(pl.min_horizontal(pl.col("open").fill_nan(None), pl.col("low").fill_nan(None)))
        .alias("cand_adj"),
        (pl.col("raw_close") / pl.col("close")).alias("ratio"),
    )
    first_ratio = (
        w.filter(pl.col("date") == pl.col("ed"))
        .select(["symbol", "ed", "ratio"])
        .rename({"ratio": "ratio0"})
    )
    w = w.join(first_ratio, on=["symbol", "ed"], how="left")
    agg = (
        w.group_by(["symbol", "ed", "xd", "entry_price", "ratio0"])
        .agg(pl.col("cand_raw").min().alias("min_raw"), pl.col("cand_adj").min().alias("min_adj"))
        .with_columns(
            ((1.0 - 0.08) * pl.col("entry_price") >= pl.col("min_raw")).alias("trig_raw"),
            ((1.0 - 0.08) * (pl.col("entry_price") / pl.col("ratio0")) >= pl.col("min_adj")).alias(
                "trig_adj"
            ),
        )
    )
    n = agg.height
    alt_raw = int(agg["trig_raw"].sum())
    alt_adj = int(agg["trig_adj"].sum())
    check("row_count_vectorised", n == 519, f"{n}")
    check(
        "trigger_rate_raw_reproduced",
        alt_raw == h1["trigger_rate"]["window_entry_to_exit"]["raw"]["n"],
        f"alt {alt_raw} vs summary {h1['trigger_rate']['window_entry_to_exit']['raw']['n']}",
    )
    check(
        "trigger_rate_adj_reproduced",
        alt_adj == h1["trigger_rate"]["window_entry_to_exit"]["adj"]["n"],
        f"alt {alt_adj} vs summary {h1['trigger_rate']['window_entry_to_exit']['adj']['n']}",
    )
    check(
        "basis_diff_below_half_point",
        abs(100.0 * (alt_raw - alt_adj) / n) < 0.5,
        f"{100.0 * (alt_raw - alt_adj) / n:.2f}pp（{alt_raw} vs {alt_adj}）",
    )

    # ---- 4. 建仓价 = raw 开盘 x 1.001 ----
    ev_match = ev.with_columns(pl.col("entry_price_vs_raw_open").cast(pl.Float64).abs()).filter(
        pl.col("entry_price_vs_raw_open") < 0.02
    )
    share = ev_match.height / ev.height
    check("entry_price_is_raw_open", share > 0.99, f"{share:.4f} of {ev.height} 笔 |diff|<0.02")

    # ---- 5. 形状数字与 summary 一致 ----
    check(
        "entry_day_trigger_count",
        int((ev["trigger_offset_raw"].cast(pl.Int64) == 0).sum())
        == h1["stop_trade_shape"]["entry_day_close_trigger"],
        f"{int((ev['trigger_offset_raw'].cast(pl.Int64) == 0).sum())}",
    )
    check(
        "first_session_trigger_count",
        int((ev["trigger_offset_raw"].cast(pl.Int64) == 1).sum())
        == h1["stop_trade_shape"]["first_session_trigger"],
        f"{int((ev['trigger_offset_raw'].cast(pl.Int64) == 1).sum())}",
    )
    check(
        "trigger_day_equals_exit_day",
        int((ev["trigger_day_raw"] == ev["exit_date"]).sum())
        == h1["stop_trade_shape"]["trigger_day_equals_exit_day"],
        f"{int((ev['trigger_day_raw'] == ev['exit_date']).sum())}",
    )

    # ---- 6. H2 ----
    check("h2_pairs_count", pairs.height == 23 == h2["pairs"]["same_symbol_pairs"], f"{pairs.height}")
    check(
        "h2_all_pairs_have_new_cross",
        int((pairs["new_cross_up_in_window"].cast(pl.Int64) >= 1).sum()) == pairs.height,
        f"{int((pairs['new_cross_up_in_window'].cast(pl.Int64) >= 1).sum())}/{pairs.height}",
    )
    check(
        "h2_no_reuse_of_old_signal",
        int((pairs["reuses_prev_signal"] == "true").sum()) == 0,
        f"{int((pairs['reuses_prev_signal'] == 'true').sum())}",
    )
    check(
        "h2_entries_all_cross_up",
        h2["entry_signal_is_cross_up"]["exact_true"] == 519,
        f"{h2['entry_signal_is_cross_up']['exact_true']}/519",
    )
    check(
        "h2_same_day_reentry_zero",
        stats["stats"]["execution"].get("buy_same_day_reentry") == 0,
        f"buy_same_day_reentry={stats['stats']['execution'].get('buy_same_day_reentry')}",
    )

    # ---- 7. 补充证据（胜率形状）----
    wr = json.loads((OUT / "summary_winrate.json").read_text(encoding="utf-8"))
    ex = pl.read_csv(OUT / "explain_winrate.csv", infer_schema_length=0)
    check("explain_rows", ex.height == 519, f"{ex.height}")
    check(
        "explain_base_rate_windows",
        wr["A_universe_base_rate"]["windows"] == 9002802,
        f"{wr['A_universe_base_rate']['windows']}",
    )
    check(
        "explain_counterfactual_n",
        wr["B_counterfactual_hold_60"]["all_519"]["n"] == 519
        and wr["B_counterfactual_hold_60"]["stop_loss_425"]["n"] == 425,
        f"{wr['B_counterfactual_hold_60']['all_519']['n']}/{wr['B_counterfactual_hold_60']['stop_loss_425']['n']}",
    )
    check(
        "explain_entry_day_close_touch",
        wr["D_entry_day_trigger_basis"]["entry_day_close_touch"]
        == h1["stop_trade_shape"]["entry_day_close_trigger"],
        f"{wr['D_entry_day_trigger_basis']['entry_day_close_touch']}",
    )

    # ---- 8. 结论口径 ----
    check("verdict_h1_refuted", h1["verdict_h1"] == "REFUTED", h1["verdict_h1"])
    check("verdict_h2_refuted", h2["verdict_h2"] == "REFUTED", h2["verdict_h2"])

    print(f"PASS {len(PASSES)}  FAIL {len(FAILS)}")
    for line in PASSES:
        print("  PASS", line)
    for line in FAILS:
        print("  FAIL", line)
    print("VERDICT=" + ("ALL_PASS" if not FAILS else "FAILED"))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
