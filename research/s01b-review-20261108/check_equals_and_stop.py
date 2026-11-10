"""S01b 独立复核 · 逐笔等价 / 止损区间 / 生产文件一致性（只读）。

用法: backend\\.venv\\Scripts\\python.exe research\\s01b-review-20261108\check_equals_and_stop.py
退出码: 0 = 全部检查完成；1 = 有硬性不一致
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
RES = PROJECT / "research" / "s01b-20261108" / "results"

PAIRS = [
    ("a0_10bp", "a0ev_10bp", "cross_down: 水平式 vs 事件式（无风控配置）"),
    ("a3_10bp", "a3ev_10bp", "cross_down: 水平式 vs 事件式（全风控配置）"),
    ("prod_file_10bp", "a3_10bp", "生产文件自跑 vs 臂 3（水平式臂模板）"),
    ("prod_file_10bp", "a3ev_10bp", "生产文件自跑 vs 臂 3 事件式"),
]


def main() -> int:
    bad = 0
    print("=== 逐笔等价（pandas DataFrame.equals，含列名/列序/dtype） ===")
    for a, b, label in PAIRS:
        da = pd.read_parquet(RES / a / "trades.parquet")
        db = pd.read_parquet(RES / b / "trades.parquet")
        eq = da.equals(db)
        print(f"  {label}\n    {a} {da.shape} vs {b} {db.shape} -> equals={eq}")
        if not eq:
            bad += 1
            print(f"    列差: {list(da.columns) == list(db.columns)}, "
                  f"dtypes 差: {[c for c in da.columns if da[c].dtype != db[c].dtype]}")
            if da.shape == db.shape:
                diff = {c: int((da[c].astype(str) != db[c].astype(str)).sum()) for c in da.columns}
                print("    差异单元格:", {k: v for k, v in diff.items() if v})
    # equity 也一并比对（生产文件 vs 臂3）
    ea = pd.read_parquet(RES / "prod_file_10bp" / "equity.parquet")
    eb = pd.read_parquet(RES / "a3_10bp" / "equity.parquet")
    print(f"  equity: prod_file_10bp {ea.shape} vs a3_10bp {eb.shape} -> equals={ea.equals(eb)}")
    if not ea.equals(eb):
        bad += 1

    print("\n=== 臂 1（a1_10bp）stop_loss 425 笔的 pnl_pct 分布 ===")
    t = pd.read_parquet(RES / "a1_10bp" / "trades.parquet")
    sl = t[t.exit_reason == "stop_loss"]["pnl_pct"] * 100.0  # pnl_pct 是小数
    n = len(sl)
    print(f"  n_stop_loss={n}  min={sl.min():.4f}%  max={sl.max():.4f}%  median={sl.median():.4f}%")
    in_8085 = int(((sl >= -8.085) & (sl <= -8.0)).sum())
    in_810 = int(((sl >= -8.10) & (sl <= -8.0)).sum())
    in_812 = int(((sl >= -8.12) & (sl <= -7.99)).sum())
    w082 = int(((sl >= -8.2) & (sl < -8.0)).sum())
    worse15 = int((sl < -15).sum())
    pos = int((sl > 0).sum())
    mode = sl.round(4).value_counts().head(5)
    print(f"  [-8.085%, -8.000%] : {in_8085}   <- REPORT §4.2 声称 330")
    print(f"  [-8.100%, -8.000%] : {in_810}   <- 开发经理复算 315")
    print(f"  [-8.200%, -8.000%) : {w082}")
    print(f"  < -15%             : {worse15}   <- REPORT 声称 22")
    print(f"  > 0                : {pos}      <- REPORT 声称 1")
    print("  众数 top5 (rounded 4dp):")
    for v, c in mode.items():
        print(f"    {v:.4f}%  x{c}")
    # 把 425 笔按区间直方
    bins = [-100, -30, -20, -15, -12, -10, -9, -8.5, -8.2, -8.1, -8.09, -8.085, -8.0, 0, 100]
    print("  直方:")
    for lo, hi in zip(bins, bins[1:]):
        c = int(((sl > lo) & (sl <= hi)).sum())
        if c:
            print(f"    ({lo:>8}, {hi:>8}] : {c}")

    print("\n=== 若按 line 计算 should-be 区间：entry_price*(1-0.08) 与 exit_price ===")
    slrows = t[t.exit_reason == "stop_loss"].copy()
    slrows["line"] = slrows["entry_price"] * 0.92
    slrows["at_line"] = (slrows["exit_price"] - slrows["line"]).abs() < 1e-9
    slrows["gap_open"] = slrows["exit_price"] < slrows["line"] - 1e-9
    print(f"  exit_price == 线价 (1e-9): {int(slrows['at_line'].sum())} / {len(slrows)}")
    print(f"  exit_price <  线价 (跳空): {int(slrows['gap_open'].sum())}")
    print(f"  exit_price >  线价        : {int((slrows['exit_price'] > slrows['line'] + 1e-9).sum())}")

    out = {
        "pairs": {f"{a}__vs__{b}": bool(pd.read_parquet(RES / a / "trades.parquet").equals(
            pd.read_parquet(RES / b / "trades.parquet"))) for a, b, _ in PAIRS},
        "stop_loss_n": n,
        "in_-8.085_-8.0": in_8085,
        "in_-8.10_-8.0": in_810,
        "worse_than_-15pct": worse15,
        "positive": pos,
        "at_line_exact": int(slrows["at_line"].sum()),
        "gap_below_line": int(slrows["gap_open"].sum()),
        "above_line": int((slrows["exit_price"] > slrows["line"] + 1e-9).sum()),
        "min_pct": round(float(sl.min()), 4),
        "max_pct": round(float(sl.max()), 4),
        "mode": {f"{float(k):.4f}": int(v) for k, v in mode.items()},
    }
    (HERE / "check_equals_and_stop.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
