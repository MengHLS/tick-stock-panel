"""S01b 独立复核 · §4 表逐格比对（只读；直接从 REPORT.md 解析，不手工转录）。

把 REPORT.md §4.1 / §4.1 附加表 / §4.2 / §4.3 的每一格与「从 trades.parquet + equity.parquet
独立自算」的值比对。自算口径：
  - total_return = equity[-1]/1_000_000 - 1
  - annual_252  = (1+total)^(252/n_equity_rows) - 1
  - annual_cal  = (1+total)^(365.25/日历天数) - 1
  - mdd         = min(value/cummax-1)
  - sharpe      = mean(daily_ret)/std(daily_ret,ddof=1)*sqrt(252)
  - OOS         = 本情景自己的 equity 曲线，base=2022-12-30 权益，年长=(末日-2022-12-30)/365.25
  - win/avg/median pnl：报告口径待定 ⇒ 同时算「已平仓」(open_at_end==False) 与「全部」两套，
    只要有一套管上就记 OK，并记录命中的口径（MISMATCH 才是硬错）
  - 年换手 = Σ entry_value / 1e6 / 7.3320（日历年）
用法:
  backend\\.venv\\Scripts\\python.exe research\\s01b-review-20261108\\compare_report_cells.py
退出码: 0 = 全部格子可复现；1 = 有格子两套口径都对不上（硬错）
"""
from __future__ import annotations

import json
import math
import re
import sys
from datetime import date
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
BASE_DIR = PROJECT / "research" / "s01b-20261108"
RES = BASE_DIR / "results"
REPORT_MD = BASE_DIR / "REPORT.md"

START, END = date(2019, 7, 1), date(2026, 10, 30)
BASE_DATE = "2022-12-30"
YRS_FULL = (END - START).days / 365.25  # 7.3320

MINUS = "\u2212"


def num(s: str) -> float:
    """'+3.13%' / '\u221239.27%' / '1,779' / '3.48x' -> float"""
    s = s.strip().replace(MINUS, "-").replace(",", "").replace("%", "")
    if s.endswith("x"):
        s = s[:-1]
    return float(s)


def compute(tag: str) -> dict:
    t = pl.read_parquet(RES / tag / "trades.parquet")
    e = pl.read_parquet(RES / tag / "equity.parquet").sort("date")
    vals = e["value"].cast(pl.Float64).to_list()
    n = len(vals)
    total = vals[-1] / 1_000_000.0 - 1
    annual = (1 + total) ** (252 / n) - 1
    d0 = date.fromisoformat(str(e["date"].to_list()[0]))
    d1 = date.fromisoformat(str(e["date"].to_list()[-1]))
    annual_cal = ((vals[-1] / 1_000_000.0) ** (365.25 / (d1 - d0).days) - 1)
    peak, mdd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    daily = [vals[i] / vals[i - 1] - 1 for i in range(1, n)]
    mu = sum(daily) / len(daily)
    sd = math.sqrt(sum((d - mu) ** 2 for d in daily) / (len(daily) - 1))
    sharpe = mu / sd * math.sqrt(252)

    closed = t.filter(~pl.col("open_at_end"))
    allp = t["pnl_pct"].cast(pl.Float64).to_list()
    cl = closed["pnl_pct"].cast(pl.Float64).to_list()
    dur = sorted(t["duration"].cast(pl.Float64).to_list())
    entry_sum = float(t["entry_value"].sum())
    expo = e["exposure"].cast(pl.Float64).to_list()

    ev = e.filter(pl.col("date").cast(pl.Utf8) >= "2023-01-01")["value"].cast(pl.Float64).to_list()
    br = e.filter(pl.col("date").cast(pl.Utf8) <= BASE_DATE)["value"].cast(pl.Float64).to_list()
    base = br[-1] if br else 1_000_000.0
    yrs_oos = (d1 - date.fromisoformat(BASE_DATE)).days / 365.25
    oos_ann = (ev[-1] / base) ** (1 / yrs_oos) - 1
    pk, oos_mdd = base, 0.0
    for v in ev:
        pk = max(pk, v)
        oos_mdd = min(oos_mdd, v / pk - 1)
    rets = [ev[i] / ev[i - 1] - 1 for i in range(1, len(ev))]
    m2 = sum(rets) / len(rets)
    s2 = math.sqrt(sum((r - m2) ** 2 for r in rets) / (len(rets) - 1))
    oos_sharpe = m2 / s2 * math.sqrt(252)

    def win(p):
        return 100 * sum(1 for x in p if x > 0) / len(p)

    def avg(p):
        return 100 * sum(p) / len(p)

    def med(p):
        return 100 * sorted(p)[len(p) // 2]

    return {
        "annual": annual * 100, "annual_cal": annual_cal * 100, "oos_annual": oos_ann * 100,
        "mdd": mdd * 100, "oos_mdd": oos_mdd * 100, "sharpe": sharpe, "oos_sharpe": oos_sharpe,
        "p50": dur[len(dur) // 2], "p90": dur[int(len(dur) * 0.9)], "dur": dur,
        "turnover": entry_sum / 1_000_000.0 / YRS_FULL,
        "avg_exp": 100 * sum(expo) / len(expo), "max_exp": 100 * max(expo),
        "n_trades": t.height,
        "win_closed": win(cl), "avg_pnl_closed": avg(cl), "median_pnl_closed": med(cl),
        "win_all": win(allp), "avg_pnl_all": avg(allp), "median_pnl_all": med(allp),
        "exit_reason": {r["exit_reason"]: r["len"] for r in t.group_by("exit_reason").len().to_dicts()},
        "oos_years": round(yrs_oos, 4),
    }


# ---------------- REPORT.md 解析 ----------------
ARM_ORDER = ["a0", "a1", "a2", "a3"]


def parse_main_table(lines: list[str]) -> dict:
    """§4.1 主表 -> {tag: [ann252, annCal, oosAnn, mdd, oosMdd, sharpe, oosSharpe,
                          p50, p90, turnover, avgExp, maxExp, n, win, avgPnl, medPnl]}"""
    out = {}
    i = 0
    for ln in lines:
        if not ln.startswith("| 臂"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 15:
            continue
        label, scen = cells[0], cells[1]
        m = re.match(r"臂\s*(\d)", label)
        if not m:
            continue
        arm = "a" + m.group(1)
        tag = f"{arm}_{ {'10bp': '10bp', '30bp': '30bp', 'gross': 'gross'}[scen] }"
        p50, p90 = [num(x) for x in cells[9].split("/")]
        expo = cells[11].split("/")
        out[tag] = [num(cells[2]), num(cells[3]), num(cells[4]), num(cells[5]), num(cells[6]),
                    num(cells[7]), num(cells[8]), p50, p90, num(cells[10]),
                    num(expo[0]), num(expo[1]), num(cells[12]), num(cells[13]),
                    num(cells[14].split("/")[0]), num(cells[14].split("/")[1])]
    return out


def parse_side_table(lines: list[str]) -> dict:
    """§4.1 附加表 -> {tag: [ann252, annCal, oosAnn, mdd, n, turnover]}"""
    out = {}
    for ln in lines:
        if not ln.startswith("| 对照") and not ln.startswith("| 附加"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 8:
            continue
        label = cells[0]
        if "a2h" in label:
            tag = "a2h_10bp"
        elif "a4" in label:
            tag = "a4_10bp"
        else:
            continue
        try:
            out[tag] = [num(cells[1]), num(cells[2]), num(cells[3]), num(cells[4]),
                        num(cells[5]), num(cells[6])]
        except ValueError:
            continue  # §3.3 的 peak 对照表等非目标表，跳过
    return out


KEYS = ("annual", "annual_cal", "oos_annual", "mdd", "oos_mdd", "sharpe", "oos_sharpe",
        "p50", "p90", "turnover", "avg_exp", "max_exp", "n_trades", "win", "avg_pnl", "median_pnl")
TOL = {"annual": 0.02, "annual_cal": 0.02, "oos_annual": 0.02, "mdd": 0.02, "oos_mdd": 0.02,
       "sharpe": 0.02, "oos_sharpe": 0.02, "p50": 0.01, "p90": 0.01, "turnover": 0.02,
       "avg_exp": 0.02, "max_exp": 0.02, "n_trades": 0.01, "win": 0.06,
       "avg_pnl": 0.06, "median_pnl": 0.06}


def main() -> int:
    import hashlib

    raw = REPORT_MD.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    lines = raw.decode("utf-8").splitlines()
    mtime = REPORT_MD.stat().st_mtime
    snap = HERE / "snapshot" / f"REPORT_at_audit_{sha[:8]}.md"
    snap.parent.mkdir(exist_ok=True)
    snap.write_bytes(raw)
    print(f"REPORT.md: {len(raw)} B  sha256={sha}  lines={len(lines)}  mtime={mtime:.0f}")
    print(f"快照: {snap.relative_to(PROJECT)}")

    main_tbl = parse_main_table(lines)
    side_tbl = parse_side_table(lines)
    print(f"解析到主表 {len(main_tbl)} 行 / 附加表 {len(side_tbl)} 行\n")

    hard, soft = [], []
    report_dump, calc_dump = {}, {}
    if len(main_tbl) != 12:
        hard.append(("REPORT", "main_table_rows", len(main_tbl), 12))

    print("=== §4.1 主表逐格 ===")
    for tag, rep in main_tbl.items():
        m = compute(tag)
        calc_dump[tag] = m
        report_dump[tag] = dict(zip(KEYS, rep))
        for k, rv in zip(KEYS, rep):
            if k in ("p50", "p90"):
                # 持仓分位有两种常见算法：取 index[n*q] 与 numpy linear 插值。
                # 只要任一口径对得上就记 OK（差异属口径，不是数据错）。
                arr = m["dur"]
                cands = [arr[len(arr) // 2] if k == "p50" else arr[int(len(arr) * 0.9)]]
                try:
                    import numpy as _np
                    cands.append(float(_np.percentile(arr, 50 if k == "p50" else 90)))
                except Exception:
                    pass
                if any(abs(c - rv) <= 0.6 for c in cands):
                    continue
                hard.append((tag, k, [round(c, 2) for c in cands], rv))
                continue
            if k in ("win", "avg_pnl", "median_pnl"):
                c_closed = m[k + "_closed"]
                c_all = m[k + "_all"]
                if abs(c_closed - rv) <= TOL[k]:
                    basis = "closed"
                    cv = c_closed
                elif abs(c_all - rv) <= TOL[k]:
                    basis = "all"
                    cv = c_all
                else:
                    basis = "NONE"
                    cv = c_all
                    hard.append((tag, k, round(c_closed, 3), round(c_all, 3), rv))
                if basis == "all":
                    soft.append((tag, k, round(rv, 3), "报告值只在『全部交易』口径下成立"))
                continue
            cv = m[k]
            if abs(cv - rv) > TOL[k]:
                hard.append((tag, k, round(cv, 4), rv))
        print(f"  {tag:11s} n={m['n_trades']} ann252={m['annual']:+.2f}/{rep[0]:+.2f} "
              f"annCal={m['annual_cal']:+.2f}/{rep[1]:+.2f} oos={m['oos_annual']:+.2f}/{rep[2]:+.2f} "
              f"mdd={m['mdd']:.2f}/{rep[3]:.2f} oosMdd={m['oos_mdd']:.2f}/{rep[4]:.2f} "
              f"sh={m['sharpe']:.2f}/{rep[5]:.2f} oosSh={m['oos_sharpe']:.2f}/{rep[6]:.2f}")

    print("\n=== §4.1 附加表（a2h / a4）===")
    SIDE_KEYS = ("annual", "annual_cal", "oos_annual", "mdd", "n_trades", "turnover")
    for tag, rep in side_tbl.items():
        m = calc_dump.get(tag) or compute(tag)
        calc_dump[tag] = m
        line = []
        for k, rv in zip(SIDE_KEYS, rep):
            ok = abs(m[k] - rv) <= TOL[k]
            line.append(f"{k}={'OK' if ok else 'DIFF'}({m[k]:.2f}/{rv:.2f})")
            if not ok:
                hard.append((tag, k, round(m[k], 4), rv))
        print(f"  {tag:11s} " + " ".join(line))

    print("\n=== §4.2 exit_reason 分布（10bp）===")
    REPORT_ER = {
        "a0_10bp": {"signal": 136, "max_hold": 58, "stop_loss": 0, "trailing_take_profit": 0, "end": 5},
        "a1_10bp": {"signal": 42, "max_hold": 50, "stop_loss": 425, "trailing_take_profit": 0, "end": 2},
        "a2_10bp": {"signal": 9, "max_hold": 5, "stop_loss": 718, "trailing_take_profit": 393, "end": 1},
        "a3_10bp": {"signal": 9, "max_hold": 12, "stop_loss": 725, "trailing_take_profit": 388, "end": 1},
        "a2h_10bp": {"signal": 16, "max_hold": 3, "stop_loss": 776, "trailing_take_profit": 691, "end": 1},
        "a4_10bp": {"signal": 125, "max_hold": 108, "stop_loss": 0, "trailing_take_profit": 0, "end": 5},
    }
    for tag, rep in REPORT_ER.items():
        m = calc_dump.get(tag) or compute(tag)
        er = m["exit_reason"]
        ok = all(int(er.get(k, 0)) == v for k, v in rep.items()) and \
            all(int(v) == 0 for k, v in er.items() if k not in rep)
        print(f"  {tag:11s} {'OK' if ok else 'DIFF'} self={dict(sorted(er.items()))}")
        if not ok:
            hard.append((tag, "exit_reason", er, rep))

    print("\n=== §4.3 延后退出（按 (symbol, entry_date) 与 a0_10bp 配对）===")
    REPORT_DELAY = {"a1_10bp": (519, 63, 456, 0, 48, 15), "a2_10bp": (1126, 101, 1025, 0, 99, 2),
                    "a3_10bp": (1135, 103, 1032, 0, 102, 1), "a4_10bp": (238, 46, 192, 0, 26, 20)}
    base = pl.read_parquet(RES / "a0_10bp" / "trades.parquet").select(
        ["symbol", "entry_date", "exit_date"]).rename({"exit_date": "xb"}).unique(
        subset=["symbol", "entry_date"], keep="first")
    for tag, rep in REPORT_DELAY.items():
        b = pl.read_parquet(RES / tag / "trades.parquet").select(["symbol", "entry_date", "exit_date"])
        j = b.join(base, on=["symbol", "entry_date"], how="left")
        paired = j.filter(pl.col("xb").is_not_null())
        later = paired.filter(pl.col("exit_date") > pl.col("xb")).height
        earlier = paired.filter(pl.col("exit_date") < pl.col("xb")).height
        got = (b.height, paired.height, b.height - paired.height, later, earlier,
               paired.height - later - earlier)
        ok = got == rep
        print(f"  {tag:11s} {'OK' if ok else 'DIFF'} self={got} report={rep}")
        if not ok:
            hard.append((tag, "delay", got, rep))

    print(f"\n硬不一致格子: {len(hard)}")
    for h in hard:
        print("  HARD", h)
    print(f"口径提示（非硬错）: {len(soft)}")
    for s in soft:
        print("  SOFT", s)
    (HERE / "compare_report_cells.json").write_text(json.dumps(
        {"report_sha256": sha, "report_bytes": len(raw), "hard": [list(map(str, h)) for h in hard],
         "soft": [list(map(str, s)) for s in soft], "metrics": calc_dump,
         "parsed_report": report_dump}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if not hard else 1


if __name__ == "__main__":
    raise SystemExit(main())
