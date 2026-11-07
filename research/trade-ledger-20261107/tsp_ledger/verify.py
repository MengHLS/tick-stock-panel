"""与临时基准目录（research/jiaogedan-review-20261107/data）逐表比对。

用途：证明新接口可以替代临时口径，并把每一处差异量化、归因。
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from .derive import DailyRow, RoundTrip
from .parse import Event


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _code_norm(c: str) -> str:
    try:
        return f"{int(float(c)):06d}"
    except (TypeError, ValueError):
        return c


def compare_trades(events: list[Event], baseline_dir: Path) -> dict:
    base = _read(baseline_dir / "trades_clean.csv")
    mine = [
        {
            "date": e.trade_date, "time": e.trade_time, "code": e.code, "type": e.raw_type,
            "qty": e.qty, "price": e.price, "amt": e.amount, "cash": e.cash,
            "comm": e.comm, "oth": e.other_fee, "stamp": e.stamp, "tfr": e.transfer_fee,
            "bal_sh": e.shares_after, "bal_cash": e.cash_after, "netpx": e.net_px,
        }
        for e in events
        if e.category in {"trade_buy", "trade_sell", "security_in", "allocation_pay"}
    ]
    key = lambda r: (r["date"], r["time"], _code_norm(r["code"]), r["type"], str(int(float(r["qty"]))))
    bk = Counter(key(r) for r in base)
    mk = Counter(key(r) for r in mine)
    bmap = {key(r): r for r in base}
    field_diffs = Counter()
    for r in mine:
        b = bmap.get(key(r))
        if not b:
            continue
        for f in ("price", "amt", "cash", "comm", "oth", "stamp", "tfr", "bal_sh", "bal_cash", "netpx"):
            a, c = _num(b[f]), _num(r[f])
            if a is None or c is None:
                continue
            if abs(a - c) > 1e-6:
                field_diffs[f] += 1
    return {
        "rows_baseline": len(base),
        "rows_mine": len(mine),
        "only_baseline": len(bk - mk),
        "only_mine": len(mk - bk),
        "field_diffs": dict(field_diffs),
        "match": len(bk) == len(mk) and not (bk - mk) and not (mk - bk) and not field_diffs,
    }


def compare_roundtrips(roundtrips: list[RoundTrip], baseline_dir: Path) -> dict:
    base = _read(baseline_dir / "roundtrips.csv")
    key = lambda r: (r["code"], r["open_time"], r["close_time"], str(int(float(r["qty"]))))
    bk = Counter(key({**r, "code": _code_norm(r["code"])}) for r in base)
    mine_rows = [
        {"code": r.code, "open_time": r.open_time or "", "close_time": r.close_time, "qty": r.qty,
         "pnl": r.pnl, "cost": r.cost, "buy_px": r.buy_px, "sell_px": r.sell_px,
         "hold_td": r.hold_td}
        for r in roundtrips
    ]
    mk = Counter(key(r) for r in mine_rows)
    bmap = {key({**r, "code": _code_norm(r["code"])}): r for r in base}
    pnl_diff = []
    for r in mine_rows:
        b = bmap.get(key(r))
        if not b or b["pnl"] in ("", None) or r["pnl"] is None:
            continue
        if abs(float(b["pnl"]) - r["pnl"]) > 0.02:
            pnl_diff.append({"key": key(r), "baseline": float(b["pnl"]), "mine": r["pnl"]})
    extra = mk - bk
    return {
        "rows_baseline": len(base),
        "rows_mine": len(mine_rows),
        "only_baseline": len(bk - mk),
        "only_mine": len(extra),
        "only_mine_sample": [dict(zip(("code", "open_time", "close_time", "qty"), k)) for k in list(extra)[:8]],
        "pnl_diffs": pnl_diff[:8],
        "pnl_diff_count": len(pnl_diff),
        "baseline_pnl_sum": round(sum(float(r["pnl"]) for r in base if r["pnl"] not in ("", None)), 2),
        "mine_pnl_sum": round(sum(r.pnl for r in roundtrips if r.pnl is not None), 2),
    }


def compare_daily(daily: list[DailyRow], baseline_dir: Path) -> dict:
    base = _read(baseline_dir / "daily_equity.csv")
    bm = {r["date"]: r for r in base}
    diffs = []
    for row in daily:
        b = bm.get(row.date)
        if not b:
            continue
        for f in ("equity", "mv", "cash", "dep", "cumdep", "pnl"):
            a, c = _num(b[f]), getattr(row, f)
            if a is None or abs(a - c) > 0.02:
                diffs.append({"date": row.date, "field": f, "baseline": a, "mine": c})
    missing = [r.date for r in daily if r.date not in bm]
    extra = [d for d in bm if d not in {r.date for r in daily}]
    return {
        "days_baseline": len(base),
        "days_mine": len(daily),
        "missing_days": missing[:5],
        "extra_days": extra[:5],
        "field_diffs": len(diffs),
        "diff_sample": diffs[:8],
        "equity_end_baseline": _num(base[-1]["equity"]) if base else None,
        "equity_end_mine": daily[-1].equity if daily else None,
        "cumdep_baseline": _num(base[-1]["cumdep"]) if base else None,
        "cumdep_mine": daily[-1].cumdep if daily else None,
        "pnl_baseline": _num(base[-1]["pnl"]) if base else None,
        "pnl_mine": daily[-1].pnl if daily else None,
    }


def compare_positions(positions_by_day: dict[str, dict[str, int]], baseline_dir: Path) -> dict:
    base = _read(baseline_dir / "daily_positions.csv")
    diff = 0
    sample = []
    for row in base:
        day = row["date"]
        mine = positions_by_day.get(day, {})
        for code, val in row.items():
            if code == "date":
                continue
            c = _num(val) or 0
            if c == 0 and code not in mine:
                continue
            if mine.get(code, 0) != int(c):
                diff += 1
                if len(sample) < 8:
                    sample.append({"date": day, "code": code, "baseline": c, "mine": mine.get(code, 0)})
    return {"days_baseline": len(base), "days_mine": len(positions_by_day), "cell_diffs": diff, "sample": sample}


def compare_all(events, roundtrips, daily, positions_by_day, baseline_dir: Path) -> dict:
    return {
        "baseline_dir": str(baseline_dir),
        "trades": compare_trades(events, baseline_dir),
        "roundtrips": compare_roundtrips(roundtrips, baseline_dir),
        "daily_equity": compare_daily(daily, baseline_dir),
        "daily_positions": compare_positions(positions_by_day, baseline_dir),
    }
