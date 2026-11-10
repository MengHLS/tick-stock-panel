"""S01b 独立复核 · 指标自算脚本（只读，不写被审目录）。

从 research/s01b-20261108/results/<tag>/{trades,equity}.parquet 独立复算：
  n_trades / final_equity / total_return / 全期年化(252 交易日基准) /
  全期年化(日历年基准) / MDD / av平仓 pnl / 中位 pnl / 胜率 / 持仓 p50,p90 /
  年换手 / 均·最大暴露 / OOS 年化(日历年) / OOS 年化(252) / OOS MDD / OOS Sharpe /
  exit_reason 分布

用法:
  backend\\.venv\\Scripts\\python.exe research\\s01b-review-20261108\\recompute_metrics.py
退出码: 0 = 全部计算完成（本脚本只输出，不断言报告对错）
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
RES = PROJECT / "research" / "s01b-20261108" / "results"

TAGS = [
    "a0_10bp", "a0_30bp", "a0_gross",
    "a1_10bp", "a1_30bp", "a1_gross",
    "a2_10bp", "a2_30bp", "a2_gross",
    "a3_10bp", "a3_30bp", "a3_gross",
    "a2h_10bp", "a4_10bp", "a0ev_10bp", "a3ev_10bp", "prod_file_10bp",
]

OOS_START = date(2023, 1, 1)
IS_END = date(2022, 12, 30)
INITIAL = 1_000_000.0


def yr_252(n_days: int) -> float:
    return n_days / 252.0


def yr_cal(d0: date, d1: date) -> float:
    return (d1 - d0).days / 365.0


def metrics(tag: str) -> dict:
    tdir = RES / tag
    t = pl.read_parquet(tdir / "trades.parquet")
    e = pl.read_parquet(tdir / "equity.parquet").sort("date")
    eq = e["value"].to_list()
    dates = [date.fromisoformat(str(d)) for d in e["date"].to_list()]
    final = float(eq[-1])
    total_ret = final / INITIAL - 1.0
    n_days = len(eq)
    y252 = yr_252(n_days)
    ycal = yr_cal(dates[0], dates[-1])
    ann252 = (final / INITIAL) ** (1 / y252) - 1.0
    anncal = (final / INITIAL) ** (1 / ycal) - 1.0
    peak = -1e18
    mdd = 0.0
    for v in eq:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, v / peak - 1.0)

    # OOS from continuous account
    oos = e.filter(pl.col("date").cast(pl.Utf8) > IS_END.isoformat())
    base_rows = e.filter(pl.col("date").cast(pl.Utf8) <= IS_END.isoformat())
    base = float(base_rows["value"].to_list()[-1]) if base_rows.height else INITIAL
    oos_final = float(oos["value"].to_list()[-1])
    oos_dates = [date.fromisoformat(str(d)) for d in oos["date"].to_list()]
    oos_ycal = yr_cal(oos_dates[0], oos_dates[-1])
    oos_y252 = yr_252(len(oos_dates) - 1)
    oos_anncal = (oos_final / base) ** (1 / oos_ycal) - 1.0
    oos_ann252 = (oos_final / base) ** (1 / oos_y252) - 1.0
    oos_peak = base
    oos_mdd = 0.0
    for v in oos["value"].to_list():
        oos_peak = max(oos_peak, v)
        oos_mdd = min(oos_mdd, v / oos_peak - 1.0)
    rets = []
    vals = oos["value"].to_list()
    prev = base
    for v in vals:
        rets.append(v / prev - 1.0)
        prev = v
    mu = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / (len(rets) - 1))
    oos_sharpe = mu / sd * math.sqrt(252) if sd else float("nan")

    pnl = [float(x) for x in t["pnl_pct"].to_list()]
    dur = [float(x) for x in t["duration"].to_list()]
    entry_val = float(t["entry_value"].sum())
    exposure = [float(x) for x in e["exposure"].to_list()]
    reasons = {
        r["exit_reason"]: int(r["len"])
        for r in t.group_by("exit_reason").len().sort("exit_reason").to_dicts()
    }
    sdur = sorted(dur)
    p50 = sdur[len(sdur) // 2]
    p90 = sdur[int(len(sdur) * 0.9)]
    return {
        "tag": tag,
        "n_trades": t.height,
        "n_days": n_days,
        "final_equity": round(final, 2),
        "total_return_pct": round(total_ret * 100, 2),
        "years_252": round(y252, 4),
        "years_cal": round(ycal, 4),
        "annual_252_pct": round(ann252 * 100, 2),
        "annual_cal_pct": round(anncal * 100, 2),
        "mdd_pct": round(mdd * 100, 2),
        "oos_years_cal": round(oos_ycal, 4),
        "oos_annual_cal_pct": round(oos_anncal * 100, 2),
        "oos_annual_252_pct": round(oos_ann252 * 100, 2),
        "oos_mdd_pct": round(oos_mdd * 100, 2),
        "oos_sharpe": round(oos_sharpe, 2),
        "win_rate_pct": round(100.0 * sum(1 for x in pnl if x > 0) / len(pnl), 1),
        "avg_pnl_pct": round(sum(pnl) / len(pnl), 2),
        "median_pnl_pct": round(sorted(pnl)[len(pnl) // 2], 2),
        "dur_p50": p50,
        "dur_p90": p90,
        "turnover_252x": round(entry_val / INITIAL / y252, 2),
        "turnover_calx": round(entry_val / INITIAL / ycal, 2),
        "avg_exposure_pct": round(100.0 * sum(exposure) / len(exposure), 2),
        "max_exposure_pct": round(100.0 * max(exposure), 2),
        "exit_reason": reasons,
    }


def main() -> int:
    out = {}
    for tag in TAGS:
        if not (RES / tag / "trades.parquet").exists():
            print(f"[skip] {tag}", file=sys.stderr)
            continue
        out[tag] = metrics(tag)
    (HERE / "recompute_metrics.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    hdr = ("tag", "n", "final", "tot%", "ann252%", "anncal%", "mdd%", "oosAnnCal%",
           "oosAnn252%", "oosMDD%", "oosSh", "win%", "avg%", "med%", "p50", "p90",
           "to252", "toCal", "avgExp%", "maxExp%")
    print(" | ".join(hdr))
    for tag, m in out.items():
        print(" | ".join(str(m[k]) for k in
              ("tag", "n_trades", "final_equity", "total_return_pct", "annual_252_pct",
               "annual_cal_pct", "mdd_pct", "oos_annual_cal_pct", "oos_annual_252_pct",
               "oos_mdd_pct", "oos_sharpe", "win_rate_pct", "avg_pnl_pct", "median_pnl_pct",
               "dur_p50", "dur_p90", "turnover_252x", "turnover_calx",
               "avg_exposure_pct", "max_exposure_pct")))
    print("\nexit_reason:")
    for tag, m in out.items():
        print(f"  {tag:16s} {m['exit_reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
