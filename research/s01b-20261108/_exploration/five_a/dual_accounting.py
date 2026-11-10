"""⑤-a 追加报数：每臂 vs 基线的「同键 / 仅本臂」拆分，两种记法同报。

追加要求（开发经理 2026-11-08 19:1x）：
  1. ``pnl_amount`` 法；
  2. ``exit_value - entry_value`` 价差法。
两法在 199 注入臂上不等（29/199），因此单记法的「同键重定价占比」一律不可引用。

本脚本只读 ``five_a/*/trades.parquet`` 与 ``data_root/adj_factor/all.parquet``，
不写任何 run 目录、不改收益数字、不碰引擎与策略文件。

输出（全部落 five_a/）：
  dual_split_by_method.csv   每臂 × 每记法 × 每块（同键 / 仅本臂 / 仅基线）
  dual_arms_table.md         单臂表（两法并列）
  dual_per_trade.csv         逐笔两法 + 分块归属
  dividend_recon.csv         价差缺口 vs 除权台账闭式预测（逐笔）
  dual_accounting.json       全部数字（含自检布尔量）
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

HERE = Path(__file__).resolve().parent
DATA_ROOT = HERE.parent / "data_root"
BASE_TAG = "base_nodefaults_10bp"
ROUNDING_TOL = 0.02          # 分位取整上限：0.01 元
FLAG_TOL = 0.02              # 记为「两法不等」的阈值

# tag, 单一开关的人读描述（与 arms_table 保持一致）
ARMS = [
    ("base_nodefaults_10bp", "基线：不注入任何 defaults（生产文件真实默认）"),
    ("only_entry_price_basis_raw", "entry_price_basis=raw"),
    ("only_block_limit_open", "block_limit_open=true"),
    ("only_finalize_open_at_end", "finalize_open_at_end=true"),
    ("only_execution_costs", "min_commission=5.0 + transfer_fee_pct=2e-06"),
    ("only_trailing_peak_price_close", "trailing_peak_price=close"),
    ("only_exit_signal_requires_profit", "exit_signal_requires_profit=true"),
    ("base_nodefaults_gross", "成本全零（佣金/印花/过户/滑点）"),
]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_arm(tag: str) -> pd.DataFrame:
    d = HERE / tag
    df = pd.read_parquet(d / "trades.parquet").copy()
    for c in ("entry_date", "exit_date"):
        df[c] = df[c].astype(str).str.slice(0, 10)
    df["vd"] = df["exit_value"] - df["entry_value"]
    df["gap"] = df["pnl_amount"] - df["vd"]
    df["key"] = df["symbol"] + "|" + df["entry_date"]
    df["arm"] = tag
    res = json.loads((d / "result.json").read_text(encoding="utf-8"))
    eq = pd.read_parquet(d / "equity.parquet")
    final_equity = float(eq["value"].iloc[-1])
    return df, res, final_equity


def block_masks(arm: pd.DataFrame, base: pd.DataFrame):
    base_keys = set(base["key"])
    arm_keys = set(arm["key"])
    same = arm["key"].isin(base_keys)
    only_arm = ~arm["key"].isin(base_keys)
    only_base = ~base["key"].isin(arm_keys)
    return same.to_numpy(), only_arm.to_numpy(), only_base.to_numpy()


def dividend_recon(row: pd.Series, actions: pl.DataFrame) -> dict:
    """按引擎口径向前回溯，闭式预测该笔现金分红：Σ shares_pre_event × dividend。"""
    sym = row["symbol"]
    sub = actions.filter(pl.col("symbol") == sym)
    if sub.height == 0:
        return {"n_events": 0, "pred_gap": 0.0, "events": ""}
    lo, hi = row["entry_date"], row["exit_date"]
    rows = [
        r for r in sub.iter_rows(named=True)
        if lo < str(r["trade_date"])[:10] <= hi
        and (abs(float(r["dividend"] or 0.0)) > 0
             or abs(float(r["bonus"] or 0.0)) > 0
             or abs(float(r["allot"] or 0.0)) > 0)
    ]
    rows.sort(key=lambda r: str(r["trade_date"])[:10])
    shares = float(row["shares"])
    total = 0.0
    desc = []
    for r in reversed(rows):
        mult = 1.0 + float(r["bonus"] or 0.0) + float(r["allot"] or 0.0)
        pre = shares / mult if mult > 0 else shares
        div = float(r["dividend"] or 0.0)
        total += pre * div
        desc.append("%s:div=%.4f,bonus=%.2f,shares=%.0f" % (str(r["trade_date"])[:10], div, float(r["bonus"] or 0.0), pre))
        shares = pre
    return {"n_events": len(rows), "pred_gap": total, "events": ";".join(reversed(desc))}


def split_two_methods(arm: pd.DataFrame, base: pd.DataFrame) -> dict:
    """同键 / 仅本臂 / 仅基线，两法各算一遍，并给恒等式残差。"""
    same, only_arm, only_base = block_masks(arm, base)
    m = arm.merge(base[["key", "pnl_amount", "vd"]], on="key", how="inner",
                  suffixes=("", "_base"))
    res = {"n_arm": len(arm), "n_same_key": int(same.sum()),
           "n_only_arm": int(only_arm.sum()), "n_only_base": int(only_base.sum()),
           "merge_rows": len(m), "methods": {}}
    for method, col, bcol in (("A_pnl_amount", "pnl_amount", "pnl_amount_base"),
                              ("B_value_diff", "vd", "vd_base")):
        same_delta = float((m[col] - m[bcol]).sum())
        arm_only_sum = float(arm.loc[only_arm, col].sum())
        base_only_pnl = float(base.loc[only_base, col].sum())
        # 计入总差的「仅基线」贡献 = −仅基线笔自身 pnl（基线独有笔被替掉时从合计里减去的就是它）
        base_only_contrib = -base_only_pnl
        arm_total = float(arm[col].sum())
        base_total = float(base[col].sum())
        total_gap = arm_total - base_total
        share = (abs(same_delta) / abs(total_gap)) if abs(total_gap) > 1e-9 else None
        res["methods"][method] = {
            "arm_total": round(arm_total, 2), "base_total": round(base_total, 2),
            "total_gap": round(total_gap, 2), "same_key_delta": round(same_delta, 2),
            "only_arm_sum": round(arm_only_sum, 2),
            "only_base_sum": round(base_only_contrib, 2),
            "only_base_raw_pnl": round(base_only_pnl, 2),
            "identity_resid": round(total_gap - (same_delta + arm_only_sum + base_only_contrib), 6),
            "same_key_share_pct": None if share is None else round(share * 100, 2),
        }
    return res


def main() -> int:
    arms = {}
    for tag, _desc in ARMS:
        arms[tag] = load_arm(tag)
    base_df, base_res, base_eq = arms[BASE_TAG]

    actions = pl.read_parquet(DATA_ROOT / "adj_factor" / "all.parquet")

    split_rows = []
    per_trade = []
    flags_rows = []
    recon_rows = []
    out = {"rounding_tol": ROUNDING_TOL, "flag_tol": FLAG_TOL, "arms": {}}

    base_sum = {"A": float(base_df["pnl_amount"].sum()), "B": float(base_df["vd"].sum())}
    base_n = len(base_df)

    for tag, desc in ARMS:
        arm, res, final_eq = arms[tag]
        same, only_arm, only_base = block_masks(arm, base_df)

        # 同键两法逐笔 delta（统一走 split_two_methods，避免两处口径漂移）
        sm = split_two_methods(arm, base_df)
        assert sm["merge_rows"] == sm["n_same_key"], "merge 出现重复键: %s" % tag
        for method, blk in sm["methods"].items():
            split_rows.append({
                "arm": tag, "method": method,
                "n_arm": sm["n_arm"], "n_same_key": sm["n_same_key"],
                "n_only_arm": sm["n_only_arm"], "n_only_base": sm["n_only_base"],
                "arm_total": blk["arm_total"], "base_total": blk["base_total"],
                "total_gap": blk["total_gap"], "same_key_delta": blk["same_key_delta"],
                "only_arm_sum": blk["only_arm_sum"], "only_base_sum": blk["only_base_sum"],
                "identity_resid": blk["identity_resid"],
                "same_key_share": None if blk["same_key_share_pct"] is None else round(blk["same_key_share_pct"] / 100.0, 6),
                "same_key_share_pct": blk["same_key_share_pct"],
            })

        # 逐笔表
        for i, r in arm.iterrows():
            per_trade.append({
                "arm": tag, "symbol": r["symbol"], "entry_date": r["entry_date"],
                "exit_date": r["exit_date"], "exit_reason": r["exit_reason"],
                "open_at_end": bool(r["open_at_end"]),
                "block": "same_key" if same[i] else "only_arm",
                "shares": r["shares"],
                "pnl_amount": round(float(r["pnl_amount"]), 2),
                "value_diff": round(float(r["vd"]), 2),
                "gap_pnl_minus_vdiff": round(float(r["gap"]), 2),
            })

        # 本臂 A−B 结构
        open_rows = arm[arm["open_at_end"]]
        gap_open = float(open_rows["gap"].sum()) if len(open_rows) else 0.0
        flagged = arm[(arm["gap"].abs() > FLAG_TOL) & (~arm["open_at_end"])]
        gap_flagged = float(flagged["gap"].sum())
        n_round = int(((arm["gap"].abs() > 0.005) & (arm["gap"].abs() <= FLAG_TOL)).sum())
        sum_round = float(arm.loc[(arm["gap"].abs() > 0.005) & (arm["gap"].abs() <= FLAG_TOL), "gap"].sum())

        preds = []
        for _, r in flagged.iterrows():
            rc = dividend_recon(r, actions)
            preds.append(rc["pred_gap"])
            recon_rows.append({
                "arm": tag, "symbol": r["symbol"], "entry_date": r["entry_date"],
                "exit_date": r["exit_date"], "shares": float(r["shares"]),
                "gap": round(float(r["gap"]), 2),
                "n_events": rc["n_events"],
                "pred_gap_closed_form": round(rc["pred_gap"], 2),
                "resid": round(float(r["gap"]) - rc["pred_gap"], 2),
                "events": rc["events"],
            })
        pred_sum = float(np.sum(preds)) if preds else 0.0

        flags_rows.append({
            "arm": tag,
            "n_rows": len(arm),
            "n_gap_gt_flag_tol": int((arm["gap"].abs() > FLAG_TOL).sum()),
            "n_gap_open_at_end": int(len(open_rows)),
            "gap_open_at_end": round(gap_open, 2),
            "n_gap_flagged_closed": int(len(flagged)),
            "gap_flagged_closed": round(gap_flagged, 2),
            "pred_div_closed_form": round(pred_sum, 2),
            "pred_resid": round(gap_flagged - pred_sum, 2),
            "n_rounding_pm_0.01": n_round,
            "sum_rounding": round(sum_round, 2),
            "sum_gap": round(float(arm["gap"].sum()), 2),
            "recon_ok": abs(gap_open + gap_flagged + sum_round - float(arm["gap"].sum())) < 1e-6,
        })

        # 权益桥
        P = float(arm["pnl_amount"].sum())
        V = float(arm["vd"].sum())
        E = final_eq - 1_000_000.0
        res_p = E - (P - gap_open)
        res_v = E - (V + gap_flagged)
        out["arms"][tag] = {
            "desc": desc,
            "n_trades": len(arm),
            "n_open_at_end": int(len(open_rows)),
            "sum_pnl_amount": round(P, 2),
            "sum_value_diff": round(V, 2),
            "sum_gap": round(float(arm["gap"].sum()), 2),
            "final_equity": round(final_eq, 2),
            "equity_change": round(E, 2),
            "stats_total_return": res["stats"]["total_return"],
            "stats_annual_return": res["stats"]["annual_return"],
            "stats_max_drawdown": res["stats"]["max_drawdown"],
            "stats_sharpe": res["stats"]["sharpe"],
            "bridge_pnl_resid": round(res_p, 2),
            "bridge_vdiff_resid": round(res_v, 2),
            "trades_sha256": sha256_file(HERE / tag / "trades.parquet"),
        }

    split = pd.DataFrame(split_rows)
    flags = pd.DataFrame(flags_rows)
    per_trade_df = pd.DataFrame(per_trade)
    recon_df = pd.DataFrame(recon_rows)

    split.to_csv(HERE / "dual_split_by_method.csv", index=False, encoding="utf-8-sig")
    flags.to_csv(HERE / "dual_gap_structure.csv", index=False, encoding="utf-8-sig")
    per_trade_df.to_csv(HERE / "dual_per_trade.csv", index=False, encoding="utf-8-sig")
    recon_df.to_csv(HERE / "dividend_recon.csv", index=False, encoding="utf-8-sig")

    # ---- markdown 表 ----
    md = []
    md.append("# ⑤-a 追加：单臂拆分两法并列（pnl_amount 法 / 价差法）\n")
    md.append("基线 = `%s`（不注入任何 defaults，208 笔）。key = (symbol, entry_date)。\n" % BASE_TAG)
    md.append("## 表 1 · 同键 / 仅本臂 / 仅基线（两法同报）\n")
    md.append("| 臂 | 记法 | 笔数 | 同键 | 仅本臂 | 仅基线 | 本臂合计 | 基线合计 | 总差 | 同键 Δ | 仅本臂 Σ | 仅基线 Σ（贡献） | 同键占比 | 恒等式残差 |")
    md.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for _, r in split.iterrows():
        share = "n/a" if pd.isna(r["same_key_share_pct"]) else "%.2f%%" % r["same_key_share_pct"]
        md.append("| `%s` | %s | %d | %d | %d | %d | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f | %s | %.4f |" % (
            r["arm"], r["method"], r["n_arm"], r["n_same_key"], r["n_only_arm"], r["n_only_base"],
            r["arm_total"], r["base_total"], r["total_gap"], r["same_key_delta"],
            r["only_arm_sum"], r["only_base_sum"], share, r["identity_resid"]))
    md.append("\n各臂不可相加：表中「总差 / 同键 Δ / 仅本臂 Σ / 仅基线 Σ」都是「单项开启时相对基线移动多少」，不是可加分量。\n")
    md.append("「仅基线 Σ（贡献）」= − 仅基线笔自身 pnl（基线独有笔被本臂替掉时，从合计里减去的就是它），故恒等式为：总差 = 同键 Δ + 仅本臂 Σ + 仅基线 Σ（贡献）。\n")
    md.append("\n## 表 2 · 本臂 A−B 缺口结构（价差法相对 pnl_amount 少了什么）\n")
    md.append("| 臂 | 笔数 | \|差\|>0.02 笔数 | 期末未平仓笔 | 期末未平仓缺口 | 已平仓不等笔 | 已平仓缺口 | 除权闭式预测 | 预测残差 | ±0.01 取整笔 | 取整净额 | Σ差 | 闭合 |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for _, r in flags.iterrows():
        md.append("| `%s` | %d | %d | %d | %.2f | %d | %.2f | %.2f | %.2f | %d | %.2f | %.2f | %s |" % (
            r["arm"], r["n_rows"], r["n_gap_gt_flag_tol"], r["n_gap_open_at_end"],
            r["gap_open_at_end"], r["n_gap_flagged_closed"], r["gap_flagged_closed"],
            r["pred_div_closed_form"], r["pred_resid"], r["n_rounding_pm_0.01"],
            r["sum_rounding"], r["sum_gap"], "OK" if r["recon_ok"] else "FAIL"))
    md.append("\n## 表 3 · 权益桥\n")
    md.append("「Σpnl 与权益差」= 权益变化 − (Σpnl_amount − 期末未平仓笔的价差)。非 0 表示期末仍有持仓未进 trades（其浮动市值不在任何一列里）；强制期末平仓的臂应当恰为 0.00，实测 `only_finalize_open_at_end` = 0.00，即该残差就是未平仓持仓的市价重估，不是记账缺陷。\n")
    md.append("| 臂 | 笔数 | Σpnl_amount | Σ价差 | Σ差 | 期末权益 | 权益变化 | Σpnl 与权益差 | Σ价差 与权益差 |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for tag, _d in ARMS:
        a = out["arms"][tag]
        md.append("| `%s` | %d | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f |" % (
            tag, a["n_trades"], a["sum_pnl_amount"], a["sum_value_diff"], a["sum_gap"],
            a["final_equity"], a["equity_change"], a["bridge_pnl_resid"], a["bridge_vdiff_resid"]))
    md.append("\n价差法口径：同一笔 `exit_value − entry_value`，其中 entry_value 含买入成本、exit_value 已扣卖出成本，**不含**持仓期现金分红，也不含期末未平仓的浮盈亏（该分支 `pnl_amount` 恒为 0）。\n")

    # ---- 附录 A：199 注入臂（results/a0_10bp）两法拆分，复现 12.2% vs 2.6% ----
    a0_dir = HERE.parent / "results" / "a0_10bp"
    a0 = pd.read_parquet(a0_dir / "trades.parquet").copy()
    for c in ("entry_date", "exit_date"):
        a0[c] = a0[c].astype(str).str.slice(0, 10)
    a0["vd"] = a0["exit_value"] - a0["entry_value"]
    a0["gap"] = a0["pnl_amount"] - a0["vd"]
    a0["key"] = a0["symbol"] + "|" + a0["entry_date"]
    a0["arm"] = "a0_10bp_199inject"
    s199 = split_two_methods(a0, base_df)
    a0_eq = float(pd.read_parquet(a0_dir / "equity.parquet")["value"].iloc[-1])

    f199 = a0[a0["gap"].abs() > FLAG_TOL].copy()
    open5 = f199[f199["open_at_end"]]
    closed24 = f199[~f199["open_at_end"]]
    pred24 = []
    for _, r in closed24.iterrows():
        pred24.append(dividend_recon(r, actions)["pred_gap"])
    pred24_sum = float(np.sum(pred24)) if pred24 else 0.0
    n_round199 = int(((a0["gap"].abs() > 0.005) & (a0["gap"].abs() <= FLAG_TOL)).sum())
    sum_round199 = float(a0.loc[(a0["gap"].abs() > 0.005) & (a0["gap"].abs() <= FLAG_TOL), "gap"].sum())
    a0[["symbol", "entry_date", "exit_date", "exit_reason", "open_at_end", "shares",
        "entry_price", "exit_price", "entry_value", "exit_value", "pnl_amount", "vd", "gap"]].assign(
        block=["same_key" if k in set(base_df["key"]) else "only_arm" for k in a0["key"]]
    ).to_csv(HERE / "appendix_199_trades.csv", index=False, encoding="utf-8-sig")
    f199.sort_values("gap", key=lambda s: s.abs(), ascending=False)[[
        "symbol", "entry_date", "exit_date", "exit_reason", "open_at_end", "shares",
        "entry_value", "exit_value", "pnl_amount", "vd", "gap"]].to_csv(
        HERE / "appendix_199_29rows.csv", index=False, encoding="utf-8-sig")

    out["appendix_199_inject"] = {
        "source": str(a0_dir / "trades.parquet"),
        "split": s199,
        "final_equity": round(a0_eq, 2),
        "equity_change": round(a0_eq - 1_000_000.0, 2),
        "sum_pnl_amount": round(float(a0["pnl_amount"].sum()), 2),
        "sum_value_diff": round(float(a0["vd"].sum()), 2),
        "sum_gap": round(float(a0["gap"].sum()), 2),
        "n_gap_gt_flag_tol": int(len(f199)),
        "n_open_at_end": int(len(open5)),
        "gap_open_at_end": round(float(open5["gap"].sum()), 2),
        "n_closed": int(len(closed24)),
        "gap_closed": round(float(closed24["gap"].sum()), 2),
        "pred_div_closed_form": round(pred24_sum, 2),
        "pred_resid": round(float(closed24["gap"].sum()) - pred24_sum, 2),
        "n_rounding_pm_0.01": n_round199,
        "sum_rounding": round(sum_round199, 2),
        "bridge_pnl_minus_open": round(a0_eq - 1_000_000.0 - (float(a0["pnl_amount"].sum()) - float(open5["gap"].sum())), 2),
        "bridge_vdiff_plus_div": round(a0_eq - 1_000_000.0 - (float(a0["vd"].sum()) + float(closed24["gap"].sum())), 2),
    }

    md.append("\n## 附录 A · 199 注入臂（`results/a0_10bp`）对同一 208 基线（供对照，不属七臂）\n")
    md.append("| 记法 | 笔数 | 同键 | 仅本臂 | 仅基线 | 本臂合计 | 基线合计 | 总差 | 同键 Δ | 仅本臂 Σ | 仅基线 Σ（贡献） | 同键占比 | 恒等式残差 |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for meth, blk in s199["methods"].items():
        share = "n/a" if blk["same_key_share_pct"] is None else "%.2f%%" % blk["same_key_share_pct"]
        md.append("| %s | %d | %d | %d | %d | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f | %s | %.4f |" % (
            meth, s199["n_arm"], s199["n_same_key"], s199["n_only_arm"], s199["n_only_base"],
            blk["arm_total"], blk["base_total"], blk["total_gap"], blk["same_key_delta"],
            blk["only_arm_sum"], blk["only_base_sum"], share, blk["identity_resid"]))
    md.append("\n199 臂 Σpnl_amount = %.2f，Σ价差 = %.2f，Σ差 = %.2f；权益 %.2f（变化 %.2f）。" % (
        out["appendix_199_inject"]["sum_pnl_amount"], out["appendix_199_inject"]["sum_value_diff"],
        out["appendix_199_inject"]["sum_gap"], a0_eq, a0_eq - 1_000_000.0))
    md.append("两法不等 %d 笔：期末未平仓 %d 笔 %+.2f、已平仓 %d 笔 %+.2f（除权闭式预测 %.2f，残差 %+.2f）、±0.01 取整 %d 笔 %+.2f。\n" % (
        len(f199), len(open5), float(open5["gap"].sum()), len(closed24), float(closed24["gap"].sum()),
        pred24_sum, float(closed24["gap"].sum()) - pred24_sum, n_round199, sum_round199))

    # ---- 表 4：单臂总表（统计 + 两法拆分并列），与 arms_table.json 交叉核对 ----
    at = json.loads((HERE / "arms_table.json").read_text(encoding="utf-8"))
    at_by = {r["arm"]: r for r in at}
    md.append("\n## 表 4 · 单臂总表（统计量 + 两法拆分并列，各臂不可相加）\n")
    md.append("| # | 臂 | 单一开关 | 笔数 | 总收益 | 年化(252) | MDD | Sharpe | buy_limit_up | sell_susp | sell_limdn | sell_badpx | pending | 同键笔 | 同键 Δ(pnl) | 同键 Δ(价差) | 仅本臂 Σ(pnl) | 仅本臂 Σ(价差) | 同键占比(pnl) | 同键占比(价差) |")
    md.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    idx = 0
    for tag, desc in ARMS:
        a = out["arms"][tag]
        r = at_by.get(tag, {})
        m = {x["arm"]: x for x in split_rows if x["arm"] == tag}
        A = [x for x in split_rows if x["arm"] == tag and x["method"] == "A_pnl_amount"][0]
        B = [x for x in split_rows if x["arm"] == tag and x["method"] == "B_value_diff"][0]
        shA = "n/a" if A["same_key_share_pct"] is None else "%.2f%%" % A["same_key_share_pct"]
        shB = "n/a" if B["same_key_share_pct"] is None else "%.2f%%" % B["same_key_share_pct"]
        md.append("| %s | `%s` | %s | %d | %.2f%% | %.2f%% | %.2f%% | %.2f | %d | %d | %d | %d | %d | %d | %.2f | %.2f | %.2f | %.2f | %s | %s |" % (
            "基线" if tag == BASE_TAG else ("gross" if "gross" in tag else str(ARMS.index((tag, desc)))),
            tag, desc, a["n_trades"],
            a["stats_total_return"] * 100, a["stats_annual_return"] * 100,
            a["stats_max_drawdown"] * 100, a["stats_sharpe"],
            r.get("buy_limit_up", -1), r.get("sell_suspended", -1), r.get("sell_limit_down", -1),
            r.get("sell_invalid_price", -1), r.get("pending_exit", -1),
            A["n_same_key"], A["same_key_delta"], B["same_key_delta"],
            A["only_arm_sum"], B["only_arm_sum"], shA, shB))
        idx += 1
    md.append("\n年化 = 按 252 交易日复利；MDD 为负值。`buy_limit_up` 等为撮合拒绝/延后计数，取自 `arms_table.json`（同一批 run）。\n")

    (HERE / "dual_arms_table.md").write_text("\n".join(md), encoding="utf-8")

    out["split"] = split_rows
    out["gap_structure"] = flags_rows
    out["artifacts_sha256"] = {
        n: sha256_file(HERE / n)
        for n in ("dual_split_by_method.csv", "dual_gap_structure.csv",
                  "dual_per_trade.csv", "dividend_recon.csv", "dual_arms_table.md",
                  "appendix_199_trades.csv", "appendix_199_29rows.csv")
    }
    (HERE / "dual_accounting.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("dual_split_by_method.csv rows=%d" % len(split))
    print("dual_gap_structure.csv rows=%d" % len(flags))
    print("dual_per_trade.csv rows=%d" % len(per_trade_df))
    print("dividend_recon.csv rows=%d" % len(recon_df))
    print()
    print(split.to_string(index=False))
    print()
    print(flags.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
