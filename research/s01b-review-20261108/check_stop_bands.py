"""S01b 独立复核 · 臂 1 止损击穿分档（两套口径同时给，只读）。

REPORT §4.2 的分档写的是 `exit_price / entry_price - 1`（价格口径），不是 pnl_pct（净口径）。
本脚本同时算两套，避免口径混用造成的「0 笔 / 315 笔」之争。
用法: backend\\.venv\\Scripts\\python.exe research\\s01b-review-20261108\\check_stop_bands.py
退出码: 0 = 价格口径下 425 / 315 / 0 / 22 / 1 全部命中；1 = 任一分档对不上
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
RES = PROJECT / "research" / "s01b-20261108" / "results"


def bands(s: pd.Series) -> dict:
    return {
        "n": int(len(s)),
        "in_-8.10_-8.00": int(((s >= -0.0810) & (s <= -0.0800)).sum()),
        "in_-8.085_-8.00": int(((s >= -0.08085) & (s <= -0.0800)).sum()),
        "lt_-15pct": int((s < -0.15).sum()),
        "gt_0": int((s > 0).sum()),
        "min": round(float(s.min()) * 100, 4),
        "max": round(float(s.max()) * 100, 4),
        "median": round(float(s.median()) * 100, 4),
        "mode_top5": {f"{k * 100:.4f}%": int(v) for k, v in
                      s.round(6).value_counts().head(5).items()},
    }


def main() -> int:
    t = pd.read_parquet(RES / "a1_10bp" / "trades.parquet")
    sl = t[t.exit_reason == "stop_loss"]
    price = sl.exit_price / sl.entry_price - 1          # 报告口径
    net = sl.pnl_pct.astype(float)                       # 含成本
    bp, bn = bands(price), bands(net)

    print(f"a1_10bp stop_loss 笔数 = {len(sl)}")
    print("\n--- 口径 A：exit_price/entry_price - 1（REPORT §4.2 用的就是这个）---")
    for k, v in bp.items():
        print(f"  {k}: {v}")
    print("\n--- 口径 B：pnl_pct（含佣金+印花+滑点，净口径）---")
    for k, v in bn.items():
        print(f"  {k}: {v}")

    line = sl.entry_price * 0.92
    at_line = int(((sl.exit_price - line).abs() < 1e-9).sum())
    gap = int((sl.exit_price < line - 1e-9).sum())
    above = int((sl.exit_price > line + 1e-9).sum())
    print(f"\n线价 entry*(1-0.08)：恰在线价 {at_line} 笔 / 跳空低于线价 {gap} 笔 / 高于线价 {above} 笔")
    print(f"理论价口径读数 = 0.92*0.999-1 = {(0.92 * 0.999 - 1) * 100:.4f}%")

    pos = sl[price > 0]
    print("\n唯一为正的一笔:")
    for _, r in pos.iterrows():
        print(f"  {r.symbol} {r.entry_date} -> {r.exit_date} price={float(price[_]) * 100:+.2f}% "
              f"net={float(r.pnl_pct) * 100:+.2f}% blocked_exit_days={getattr(r, 'blocked_exit_days', 'n/a')}")

    ok = (bp["n"] == 425 and bp["in_-8.10_-8.00"] == 315 and bp["in_-8.085_-8.00"] == 0
          and bp["lt_-15pct"] == 22 and bp["gt_0"] == 1)
    print(f"\nREPORT §4.2 表格（425/315/0/22/1）在价格口径下可复现 = {ok}")
    print("旧句『330 笔落在 [-8.085%, -8.0]』可复现 = "
          f"{bp['in_-8.085_-8.00'] == 330}（实测 {bp['in_-8.085_-8.00']} 笔）")
    (HERE / "check_stop_bands.json").write_text(json.dumps(
        {"price_basis": bp, "net_basis": bn, "at_line": at_line, "gap_below_line": gap,
         "above_line": above, "theoretical_pct": round((0.92 * 0.999 - 1) * 100, 4),
         "report_4_2_reproducible": bool(ok)}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
