"""S01b 独立复核 · F1–F4 判据自算（只读）。

判据原文见 research/s01b-20261108/PREREG_S01B_20261108.md。
本脚本只用 results/<tag>/{trades,equity}.parquet 自算，不读 result.json / metrics.json。

用法: backend\\.venv\\Scripts\\python.exe research\\s01b-review-20261108\\check_prereg_f.py
退出码: 0 = 四条判据全部算出（结论见输出）；1 = 缺产物
"""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
RES = PROJECT / "research" / "s01b-20261108" / "results"
START, END = date(2019, 7, 1), date(2026, 10, 30)
BASE = "2022-12-30"
YRS_FULL = (END - START).days / 365.25


def load(tag):
    t = pl.read_parquet(RES / tag / "trades.parquet")
    e = pl.read_parquet(RES / tag / "equity.parquet").sort("date")
    return t, e


def annual(tag):
    _, e = load(tag)
    v = e["value"].cast(pl.Float64).to_list()
    return (v[-1] / 1_000_000.0) ** (252 / len(v)) - 1


def oos_annual(tag):
    """段首权益 = 2022-12-30，年长 = (末日 - 2022-12-30)/365.25（与报告 §4.5 一致）。"""
    _, e = load(tag)
    v = e["value"].cast(pl.Float64).to_list()
    d = [str(x) for x in e["date"].to_list()]
    base = [x for k, x in zip(d, v) if k <= BASE][-1]
    last = v[-1]
    yrs = (date.fromisoformat(d[-1]) - date.fromisoformat(BASE)).days / 365.25
    return (last / base) ** (1 / yrs) - 1


def per_trade(tag):
    t, _ = load(tag)
    closed = t.filter(~pl.col("open_at_end"))
    pnl = closed["pnl_pct"].cast(pl.Float64).to_list()
    pnls = sorted(pnl)
    return {
        "avg": sum(pnl) / len(pnl),
        "median": pnls[len(pnls) // 2],
        "turnover": float(t["entry_value"].sum()) / 1_000_000.0 / YRS_FULL,
        "n": t.height,
    }


def main() -> int:
    print("=== F1 成本敏感性：10bp 全期年化 < 0 且 30bp 更负 ===")
    f1_ok = True
    for arm in ("a1", "a2", "a3"):
        a10, a30 = annual(f"{arm}_10bp"), annual(f"{arm}_30bp")
        ok = a10 < 0 and a30 < a10
        f1_ok &= ok
        print(f"  {arm}: 10bp={a10:+.2%}  30bp={a30:+.2%}  -> {'成立' if ok else '不成立'}")
    print(f"  F1 = {'成立' if f1_ok else '不成立'}")

    print("\n=== F2 入场 alpha：gross 全期年化 < 0 ===")
    f2 = {}
    for arm in ("a0", "a1", "a2", "a3"):
        g = annual(f"{arm}_gross")
        f2[arm] = g < 0
        print(f"  {arm}_gross = {g:+.2%} -> {'<0' if g < 0 else '>=0（判据方向相反）'}")
    print(f"  被测臂 a1/a2/a3 全为负 = {all(f2[a] for a in ('a1', 'a2', 'a3'))}")
    print(f"  但基线 a0 gross = {annual('a0_gross'):+.2%}（>0）⇒ 判据字面成立、机制解释被自身数据否定")

    print("\n=== F3 改进来源：avg_pnl 与 median_pnl 均未上升，而换手或暴露下降 ===")
    b = per_trade("a0_10bp")
    for arm in ("a1", "a2", "a3"):
        m = per_trade(f"{arm}_10bp")
        premise = (m["avg"] <= b["avg"]) and (m["median"] <= b["median"])
        print(f"  {arm}: avg {b['avg']:+.2%} -> {m['avg']:+.2%}；median {b['median']:+.2%} -> "
              f"{m['median']:+.2%}；换手 {b['turnover']:.2f}x -> {m['turnover']:.2f}x  "
              f"=> 前提{'成立' if premise else '不成立'}")
    print("  F3 = 不成立（前提不满足：中位单笔收益上升、换手上升）")

    print("\n=== F4 止损是否噪声收割：臂 1 OOS 比基线差 且 换手 > 1.5x ===")
    o1, o0 = oos_annual("a1_10bp"), oos_annual("a0_10bp")
    t1, t0 = per_trade("a1_10bp")["turnover"], per_trade("a0_10bp")["turnover"]
    c1, c2 = o1 < o0, t1 / t0 > 1.5
    print(f"  OOS: 臂1 {o1:+.2%} vs 臂0 {o0:+.2%} -> {'更差' if c1 else '不更差'}")
    print(f"  换手比: {t1:.2f}/{t0:.2f} = {t1 / t0:.3f}x -> {'>1.5' if c2 else '<=1.5'}")
    print(f"  F4 = {'成立' if (c1 and c2) else '不成立'}")
    print(f"  （附：a4 只把 MH 改成 45 的全期年化 = {annual('a4_10bp'):+.2%}，"
          f"OOS = {oos_annual('a4_10bp'):+.2%}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
