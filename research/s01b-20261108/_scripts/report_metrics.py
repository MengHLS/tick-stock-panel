"""S01b 四臂指标汇总：全期/OOS 年化、MDD、Sharpe、持仓分位、年换手、暴露、exit_reason、
延后退出笔数（与臂 0 逐笔配对口径）。只读 results/ 下的 result.json + equity/trades.parquet。

延后退出口径（写死）：把被测臂每笔交易与臂 0 按 (symbol, entry_date) 配对 ——
entry_date 相同视为同一次入场；配对成功且 exit_date 更晚 => 计 1 笔延后退出。
配对不上的笔数单独报 unpaired（不计入延后）。
"""
from __future__ import annotations
import json, math, pathlib
import polars as pl

HERE = pathlib.Path(__file__).resolve().parent
RES = HERE / "results"
START, END = "2019-07-01", "2026-10-30"
OOS_START = "2023-01-01"
OOS_BASE_DATE = "2022-12-30"
ARMS = [
    ("臂 0 基线（无风控出场）", "a0_10bp", "a0ev_10bp"),
    ("臂 1 + 止损 -8%", "a1_10bp", "a0ev_10bp"),
    ("臂 2 + 止损 + 移动止盈 10/8", "a2_10bp", "a0ev_10bp"),
    ("臂 3 + 上路 + 最长持有 45", "a3_10bp", "a0ev_10bp"),
    ("对照 臂2 peak=high", "a2h_10bp", "a0ev_10bp"),
    ("附加 只改 MAX_HOLD_DAYS=45", "a4_10bp", "a0ev_10bp"),
]
SCEN = [("10bp", "{arm}"), ("30bp", "{arm30}"), ("gross", "{armg}")]


def years(a: str, b: str) -> float:
    from datetime import date
    return (date.fromisoformat(b) - date.fromisoformat(a)).days / 365.25


def equity_metrics(tag: str) -> dict:
    p = RES / tag / "equity.parquet"
    e = pl.read_parquet(p).sort("date")
    e = e.with_columns(pl.col("value").cast(pl.Float64))
    base_rows = e.filter(pl.col("date") <= OOS_BASE_DATE)
    base = float(base_rows["value"][-1]) if base_rows.height else float(e["value"][0])
    oos = e.filter(pl.col("date") >= OOS_START)
    v0, v1 = base, float(oos["value"][-1])
    d0 = str(oos["date"][0]); d1 = str(oos["date"][-1])
    yrs = years(OOS_BASE_DATE, d1)
    ann = (v1 / v0) ** (1 / yrs) - 1 if v0 > 0 and v1 > 0 else float("nan")
    peak = -1e18; mdd = 0.0
    for v in oos["value"].to_list():
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    rets = (oos["value"] / oos["value"].shift(1) - 1).drop_nulls()
    mu, sd = float(rets.mean()), float(rets.std())
    sharpe = mu / sd * math.sqrt(252) if sd else float("nan")
    return {"oos_start_value": round(v0, 2), "oos_end_value": round(v1, 2),
            "oos_first_date": d0, "oos_last_date": d1, "oos_years": round(yrs, 3),
            "oos_annual": round(ann, 4), "oos_mdd": round(mdd, 4),
            "oos_sharpe_self": round(sharpe, 3), "oos_days": oos.height}


def pair_delay(tag: str, base: str = "a0ev_10bp") -> dict:
    a = pl.read_parquet(RES / base / "trades.parquet").select(
        ["symbol", "entry_date", "exit_date", "exit_reason"]).rename(
        {"exit_date": "exit_date_base", "exit_reason": "reason_base"})
    b = pl.read_parquet(RES / tag / "trades.parquet").select(
        ["symbol", "entry_date", "exit_date", "exit_reason"])
    # 同一 (symbol, entry_date) 在臂 0 里若出现多次，取第一条
    a = a.unique(subset=["symbol", "entry_date"], keep="first")
    j = b.join(a, on=["symbol", "entry_date"], how="left")
    paired = j.filter(pl.col("exit_date_base").is_not_null())
    later = paired.filter(pl.col("exit_date") > pl.col("exit_date_base"))
    earlier = paired.filter(pl.col("exit_date") < pl.col("exit_date_base"))
    same = paired.height - later.height - earlier.height
    return {"trades": b.height, "paired": paired.height, "unpaired": b.height - paired.height,
            "delayed": later.height, "advanced": earlier.height, "same_exit_date": same,
            "delayed_share_of_paired": round(later.height / paired.height, 4) if paired.height else None,
            "base_trades": a.height}


def arm_metrics(label: str, tag10: str, base: str) -> dict:
    tag30 = tag10.replace("_10bp", "_30bp")
    tagg = tag10.replace("_10bp", "_gross")
    out = {"label": label, "tags": {"10bp": tag10, "30bp": tag30, "gross": tagg}}
    for scen, tag in (("10bp", tag10), ("30bp", tag30), ("gross", tagg)):
        rj = RES / tag / "result.json"
        if not rj.exists():
            out[scen] = None
            continue
        r = json.loads(rj.read_text(encoding="utf-8"))
        st = r["stats"]
        t = pl.read_parquet(RES / tag / "trades.parquet")
        yrs = years(START, END)
        turnover = float(t["entry_value"].sum()) / 1_000_000.0 / yrs
        dur = t["duration"].cast(pl.Float64)
        er = t.group_by("exit_reason").len().sort("exit_reason").to_dicts()
        out[scen] = {
            "annual": round(st["annual_return"], 4), "total": round(st["total_return"], 4),
            "mdd": round(st["max_drawdown"], 4), "sharpe": round(st["sharpe"], 3),
            "n_trades": st["n_trades"], "win_rate": round(st["win_rate"], 4),
            "avg_pnl": round(st["avg_pnl"], 5), "median_pnl": round(st["median_pnl"], 5),
            "avg_holding": round(st["avg_holding_days"], 2),
            "hold_p50": round(float(dur.median()), 1),
            "hold_p90": round(float(dur.quantile(0.9)), 1),
            "annual_turnover": round(turnover, 2),
            "avg_exposure": round(st["avg_exposure"], 4), "max_exposure": round(st["max_exposure"], 4),
            "exit_reason": {d["exit_reason"]: d["len"] for d in er},
            "final_equity": round(st["final_equity"], 2),
            "elapsed_s": r["elapsed_s"], "error": r["error"],
        }
    # OOS 三列必须按各成本档自己的 equity 自算：30bp / gross 的曲线与 10bp 不同，
    # 复用 10bp 的 OOS 读数会让整列在三个成本档上是同一个数（2026-11-08 复核发现并修）。
    oos_by = {}
    for scen, tag in (("10bp", tag10), ("30bp", tag30), ("gross", tagg)):
        if out.get(scen) is not None and (RES / tag / "equity.parquet").exists():
            oos_by[scen] = equity_metrics(tag)
    out["oos_by_scen"] = oos_by
    # 2026-11-08 18:0x 文档级补正：删除旧键 "oos"。它恒等于 10bp 档的读数，
    # 30bp / gross 行读它就会拿到与 10bp 行相同的数 —— 即 §8 第 5 条已修缺陷的后门。
    # 逐档读数只认 oos_by_scen；本目录无其它消费方（grep 确认）。
    out["delay"] = pair_delay(tag10, base)
    return out


def main() -> int:
    rows = [arm_metrics(lbl, t10, base) for lbl, t10, base in ARMS]
    (HERE / "metrics.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    hdr = ("| 臂 | 情景 | 全期年化 | OOS 年化 | MDD | OOS MDD | Sharpe | OOS Sharpe* | "
           "持仓 p50/p90 | 年换手 | 均/最大暴露 | 笔数 | 胜率 | avg/median pnl |\n"
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    lines = [hdr]
    for r in rows:
        for scen in ("10bp", "30bp", "gross"):
            m = r.get(scen)
            if not m:
                lines.append(f"| {r['label']} | {scen} | 未跑 | | | | | | | | | | | |")
                continue
            oos = r["oos_by_scen"][scen]
            lines.append(
                f"| {r['label']} | {scen} | {m['annual']:+.2%} | {oos['oos_annual']:+.2%} | "
                f"{m['mdd']:.2%} | {oos['oos_mdd']:.2%} | {m['sharpe']:+.2f} | "
                f"{oos['oos_sharpe_self']:+.2f} | {m['hold_p50']:.0f}/{m['hold_p90']:.0f} | "
                f"{m['annual_turnover']:.2f}x | {m['avg_exposure']:.2%}/{m['max_exposure']:.2%} | "
                f"{m['n_trades']} | {m['win_rate']:.1%} | {m['avg_pnl']:+.2%}/{m['median_pnl']:+.2%} |")
    table = "\n".join(lines)
    (HERE / "metrics_table.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    print()
    for r in rows:
        m = r["10bp"]
        print(f"{r['label']}: exit_reason={m['exit_reason']} delay={r['delay']} oos={r['oos_by_scen']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
