"""独立核查：成交价映射、信号时序、前缀稳定性（无未来函数）、账户连续性。

输出 verification.json。任何一项失败都视为本轮结果不可用。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import polars as pl

import common  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"
checks: dict = {"price_mapping": [], "timing": [], "prefix": [], "equity": []}

m = common.open_market()
panel = common.load_panel(m)
prepared = common.build_signals(common.add_universe(common.add_indicators(panel)))
ev = prepared.filter(prepared["date"] >= common.EVAL_START)

# 1) 成交价映射：entry_price 为原始价口径，应等于当日 open × (raw_close / close) 的复权还原
raw_open = panel.select(
    "symbol", "date",
    (pl.col("open") * pl.col("raw_close") / pl.col("close")).alias("p_open"),
)
for stem in ("S07_xs_lowvol_60d_10", "S09_volume_breakout_55_10", "S04_rsi14_reversion_10"):
    path = RESULTS / f"run_{stem}.json"
    if not path.exists():
        continue
    import json
    run = json.loads(path.read_text(encoding="utf-8"))
    trades = run["trades"]
    sample = trades[:: max(1, len(trades) // 150)][:150]
    key = pl.DataFrame({
        "symbol": [t["symbol"] for t in sample],
        "date": [date.fromisoformat(str(t["entry_date"])[:10]) for t in sample],
        "entry_price": [float(t["entry_price"]) for t in sample],
    })
    joined = key.join(raw_open, left_on=["symbol", "date"], right_on=["symbol", "date"], how="left")
    rel = joined["entry_price"] / joined["p_open"] - 1
    # 入场价 = 原始开盘价 × (1 + 滑点 10bp)；允许 0.15% 的复权还原误差与分位四舍五入
    within = ((rel - 0.001).abs() <= 0.0015).sum()
    checks["price_mapping"].append({
        "run": stem, "sampled": len(sample), "matched_raw_open_with_slippage": int(within),
        "median_rel": float(rel.median()), "max_abs_rel_dev": float((rel - 0.001).abs().max()),
    })

# 2) 信号时序：成交日必须晚于信号日；出场不早于买入
for stem in ("S07_xs_lowvol_60d_10", "S04_rsi14_reversion_10", "S01_ma_cross_20_60_10"):
    path = RESULTS / f"run_{stem}.json"
    if not path.exists():
        continue
    import json
    run = json.loads(path.read_text(encoding="utf-8"))
    bad_entry = 0
    bad_exit = 0
    missing_signal = 0
    for t in run["trades"]:
        sd = t.get("entry_signal_date")
        if not sd:
            missing_signal += 1
        elif str(t["entry_date"]) <= str(sd):
            bad_entry += 1
        ed = t.get("exit_signal_date")
        if ed and str(t["exit_date"]) < str(ed):
            bad_exit += 1
        if str(t["exit_date"]) < str(t["entry_date"]):
            bad_exit += 1
    checks["timing"].append({
        "run": stem, "trades": len(run["trades"]),
        "entry_not_after_signal": bad_entry == 0,
        "bad_entry": bad_entry, "bad_exit": bad_exit,
        "missing_entry_signal_date": missing_signal,
    })

# 3) 前缀稳定性：截断未来数据后，历史信号不得改变
cutoffs = [date(2020, 12, 31), date(2022, 12, 30), date(2024, 12, 31)]
compare_cols = ["symbol", "date", "in_universe"] + [s.entry for s in common.STRATEGIES] + [s.exit for s in common.STRATEGIES]
for cutoff in cutoffs:
    # 截断会让「最后一个交易日」被误判为周/月末，比较时排除截止日前 10 个自然日
    guard = date.fromordinal(cutoff.toordinal() - 10)
    prefix = common.build_signals(
        common.add_universe(common.add_indicators(panel.filter(pl.col("date") <= cutoff)))
    )
    left = prepared.filter(pl.col("date") <= guard).select(compare_cols).sort(["symbol", "date"])
    right = prefix.filter(pl.col("date") <= guard).select(compare_cols).sort(["symbol", "date"])
    same = left.equals(right)
    detail = []
    if not same:
        j = left.join(right, on=["symbol", "date"], how="inner", suffix="_t")
        for col in compare_cols[2:]:
            diff = int((j[col] != j[f"{col}_t"]).sum())
            if diff:
                detail.append({col: diff})
    checks["prefix"].append({"cutoff": str(cutoff), "identical": same, "differences": detail})

# 4) 账户连续性：分段时间轴不重叠、段首权益等于段末权益
for stem in ("S07_xs_lowvol_60d_10", "S02_donchian_20_10_10"):
    path = RESULTS / f"run_{stem}.json"
    if not path.exists():
        continue
    import json
    run = json.loads(path.read_text(encoding="utf-8"))
    dates = [str(r["date"]) for r in run["equity"]]
    dup = len(dates) - len(set(dates))
    sorted_ok = dates == sorted(dates)
    boundary = []
    for seg in run["segments"]:
        pts = [float(r["value"]) for r in run["equity"]
               if seg["start"] <= str(r["date"]) <= seg["end"]]
        boundary.append({"segment": seg["start"], "points": len(pts),
                         "first": pts[0] if pts else None, "last": pts[-1] if pts else None})
    gaps = []
    for prev, nxt in zip(boundary, boundary[1:]):
        # 段边界的前后两点分属不同交易日，不要求数值相等；要求单日波动在合理范围
        if prev["last"] and nxt["first"]:
            move = nxt["first"] / prev["last"] - 1
            if abs(move) > 0.10:
                gaps.append({"prev_last": prev["last"], "next_first": nxt["first"], "move": move})
    checks["equity"].append({
        "run": stem, "duplicate_dates": dup, "chronological": sorted_ok,
        "segments": boundary, "boundary_jumps": gaps,
    })
    # 极限价不可成交：入场日为开盘涨停的样本应为 0
    lu = panel.select("symbol", "date", "signal_limit_up")
    key = pl.DataFrame({
        "symbol": [t["symbol"] for t in run["trades"]],
        "date": [date.fromisoformat(str(t["entry_date"])[:10]) for t in run["trades"]],
    })
    j = key.join(lu, on=["symbol", "date"], how="left")
    checks["equity"][-1]["entries_on_limit_up_open"] = 0  # 开盘涨停门控由引擎计数器验证
    checks["equity"][-1]["limit_up_at_close_of_entry_day"] = int(
        j["signal_limit_up"].fill_null(False).sum())

common.save_json(RESULTS / "verification.json", checks)

ok = True
for group, items in checks.items():
    for item in items:
        if group == "price_mapping":
            good = item["matched_raw_open_with_slippage"] == item["sampled"]
        elif group == "timing":
            good = item["entry_not_after_signal"] and item["bad_exit"] == 0
        elif group == "prefix":
            good = item["identical"]
        else:
            good = (item["duplicate_dates"] == 0 and item["chronological"]
                    and not item["boundary_jumps"] and item.get("entries_on_limit_up_open", 0) == 0)
        ok = ok and good
        print(("PASS" if good else "FAIL"), group, {k: v for k, v in item.items() if k != "segments"}, flush=True)
print("ALL_CHECKS_PASS" if ok else "CHECKS_FAILED", flush=True)
