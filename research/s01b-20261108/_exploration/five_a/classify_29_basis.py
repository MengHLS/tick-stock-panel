# -*- coding: utf-8 -*-
"""⑤-a 追加裁定：199 注入臂那 29 笔「两法不等」到底是不是 pnl_amount 换了价基。

判据（不依赖任何外部假设，只用 trades.parquet 自带列 + 除权台账闭式）
  H1 价基不同：pnl_amount 的价格部分与 entry_value/exit_value 不同基
     ⇒ 逐笔 (pnl_amount − 价差) 减去该笔现金分红后，残差应显著非 0。
  H2 构成不同：同一价基，pnl_amount 多记「持仓期现金分红/送股」，少记「期末未平仓盯市」
     ⇒ 已平仓笔残差 ≤ 0.02（分位取整），未平仓笔 pnl_amount 恒 0。

本脚本只读 parquet，不改任何 run 目录与已有产物；输出
  appendix_199_29rows_classified.csv
  classify_29_result.txt
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import polars as pl

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dual_accounting as da  # noqa: E402  （有 __main__ 守卫，import 只取函数）

A0_TRADES = HERE.parent / "results" / "a0_10bp" / "trades.parquet"
TOL = 0.02  # 分（0.01 元取整 + 0.01 浮点）

checks: list[tuple[bool, str]] = []


def ck(ok: bool, msg: str) -> None:
    checks.append((bool(ok), msg))


def main() -> int:
    tr = pd.read_parquet(A0_TRADES).copy()
    tr["vd"] = tr["exit_value"] - tr["entry_value"]
    tr["gap"] = tr["pnl_amount"] - tr["vd"]
    actions = pl.read_parquet(da.DATA_ROOT / "adj_factor" / "all.parquet")

    flagged = tr[tr["gap"].abs() > TOL].copy()
    flagged = flagged.sort_values(["open_at_end", "symbol", "entry_date"], ascending=[False, True, True])

    rows = []
    for _, r in flagged.iterrows():
        is_open = bool(r["open_at_end"])
        rc = {"n_events": 0, "pred_gap": 0.0, "events": ""}
        if not is_open:
            rc = da.dividend_recon(r, actions)
        pred = round(float(rc["pred_gap"]), 2)
        gap = float(r["gap"])
        resid = round(gap - pred, 2)
        if is_open:
            cls = "H2_open_at_end_mark_not_in_pnl"
        elif abs(resid) <= TOL:
            cls = "H2_dividend_cash" if abs(pred) > TOL else "H1_OR_UNEXPLAINED"
        else:
            cls = "H1_OR_UNEXPLAINED"
        rows.append(
            {
                "symbol": r["symbol"],
                "entry_date": str(r["entry_date"])[:10],
                "exit_date": str(r["exit_date"])[:10],
                "exit_reason": r["exit_reason"],
                "open_at_end": is_open,
                "shares": float(r["shares"]),
                "entry_price": round(float(r["entry_price"]), 4),
                "exit_price": round(float(r["exit_price"]), 4),
                "entry_value": round(float(r["entry_value"]), 2),
                "exit_value": round(float(r["exit_value"]), 2),
                "pnl_amount": round(float(r["pnl_amount"]), 2),
                "vd": round(float(r["vd"]), 2),
                "gap": round(gap, 2),
                "pred_div_closed_form": pred,
                "resid": resid,
                "n_div_events": int(rc["n_events"]),
                "div_events": rc["events"],
                "class": cls,
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(HERE / "appendix_199_29rows_classified.csv", index=False, encoding="utf-8-sig")

    # ---- 判据 ----
    open5 = out[out["open_at_end"]]
    closed24 = out[~out["open_at_end"]]
    ck(len(out) == 29, f"29 笔清单行数 = {len(out)}")
    ck(len(open5) == 5, f"期末未平仓 = {len(open5)}")
    ck(len(closed24) == 24, f"已平仓 = {len(closed24)}")
    ck(bool((open5["pnl_amount"].abs() <= 0.01).all()), "5 笔未平仓 pnl_amount 全为 0")
    ck(bool((open5["exit_value"] > 0).all()), "5 笔未平仓仍带 'end' 盯市 exit_value（价差法据此入账）")
    ck(bool((closed24["resid"].abs() <= TOL).all()),
       f"24 笔已平仓：扣分红后残差全 ≤ {TOL}（实测 max |resid| = {closed24['resid'].abs().max():.2f}）")
    ck(sorted(out["class"].unique().tolist()) == ["H2_dividend_cash", "H2_open_at_end_mark_not_in_pnl"],
       f"分类只有 H2 两类，无 H1 残留：{sorted(set(out['class']))}")
    ck(int((closed24["pred_div_closed_form"].abs() <= TOL).sum()) == 0, "24 笔均确有分红/送股事件（pred>0）")

    gap_open = float(open5["gap"].sum())
    gap_closed = float(closed24["gap"].sum())
    ck(abs(gap_open - 84132.95) <= TOL, f"未平仓缺口合计 = {gap_open:.2f}（期望 84,132.95）")
    ck(abs(gap_closed - 26612.60) <= TOL, f"已平仓缺口合计 = {gap_closed:.2f}（期望 26,612.60）")
    gap_open_raw = float(tr[tr["open_at_end"]]["gap"].sum())
    gap_closed_raw = float(tr[~tr["open_at_end"]]["gap"].sum())
    ck(abs(gap_open_raw + gap_closed_raw - 110745.51) <= 0.005,
       f"两段相加（未取整）= {gap_open_raw + gap_closed_raw:.2f}（期望 110,745.51）；逐笔取整后的和为 {gap_open + gap_closed:.2f}（差 {abs(gap_open + gap_closed - 110745.51):.2f}，44 笔 ±0.01）")
    ck(abs(float(open5["pred_div_closed_form"].sum())) <= TOL, "未平仓 5 笔无分红预测混入（pred=0）")

    # 价基同一性：已平仓笔用 pnl 反推的价格部分 == 价差
    ck(abs(float(closed24["pnl_amount"].sum() - closed24["vd"].sum()) - gap_closed) <= TOL,
       "已平仓 Σpnl − Σ价差 == Σgap（同价基 + 分红现金）")

    # 权益两条桥
    eq = 1242725.28
    eq_chg = eq - 1_000_000.0
    bridge_a = eq_chg - (float(tr["pnl_amount"].sum()) - gap_open)
    bridge_b = eq_chg - (float(tr["vd"].sum()) + gap_closed)
    ck(abs(bridge_a) <= 0.05, f"桥 A：权益变化 = Σpnl − 未平仓缺口，残差 {bridge_a:+.2f}")
    ck(abs(bridge_b) <= 0.05, f"桥 B：权益变化 = Σ价差 + 已平仓分红，残差 {bridge_b:+.2f}")

    # 7 倍占比差的来源：同键对上的 gap
    j = json.load(open(HERE / "dual_accounting.json", encoding="utf-8"))
    methods = j["appendix_199_inject"]["split"]["methods"]
    a = methods["A_pnl_amount"]
    b = methods["B_value_diff"]
    d_sk = float(a["same_key_delta"]) - float(b["same_key_delta"])
    base = pd.read_parquet(HERE / "base_nodefaults_10bp" / "trades.parquet").copy()
    tr["key"] = tr["symbol"].astype(str) + "|" + tr["entry_date"].astype(str).str[:10]
    base["key"] = base["symbol"].astype(str) + "|" + base["entry_date"].astype(str).str[:10]
    common = set(tr["key"]) & set(base["key"])
    gap_sk = float(tr[tr["key"].isin(common)]["gap"].sum())
    base_sk_gap = float((base[base["key"].isin(common)]["pnl_amount"] -
                         (base[base["key"].isin(common)]["exit_value"] - base[base["key"].isin(common)]["entry_value"])).sum())
    ck(abs(gap_sk - base_sk_gap - d_sk) <= TOL,
       f"同键重定价两法之差 {d_sk:,.2f} == 同键对上 Σgap {gap_sk:,.2f} − 基线自身取整缺口 {base_sk_gap:+.2f}")
    ck(abs(float(a["same_key_share_pct"]) - 12.18) < 0.05 and abs(float(b["same_key_share_pct"]) - 2.61) < 0.05,
       f"占比 12.18% vs 2.61%（实测 {a['same_key_share_pct']:.2f}% / {b['same_key_share_pct']:.2f}%）")
    ck(abs(d_sk / 110745.51 - 0.7544) < 0.005,
       f"同键对贡献了总缺口的 {d_sk / 110745.51 * 100:.1f}%（≈75%，缺口集中在跨除权笔）")

    n_fail = sum(1 for ok, _ in checks if not ok)
    lines = []
    for ok, msg in checks:
        lines.append(("PASS  " if ok else "FAIL  ") + msg)
    lines.append("")
    lines.append(f"checks={len(checks)}  fails={n_fail}  VERDICT={'ALL_PASS' if n_fail == 0 else 'FAILED'}")
    lines.append("")
    lines.append("裁定：29 笔 = 5 笔期末未平仓（pnl_amount 只记已实现=0，价差法取 'end' 行盯市价，缺口 -84,132.95 计在 pnl 之外）")
    lines.append("      + 24 笔已平仓（pnl_amount 含持仓期现金分红/送股，闭式预测 26,612.57 对实测 26,612.60，残差 +0.03）。")
    lines.append("      ⇒ pnl_amount 的价格部分与 entry_price/exit_price 完全同基；差的是构成，不是价基。H1 不成立。")
    txt = "\n".join(lines) + "\n"
    (HERE / "classify_29_result.txt").write_text(txt, encoding="utf-8")
    print(txt)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
