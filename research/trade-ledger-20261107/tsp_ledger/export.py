"""导出层：把库内事件与派生结果写成 CSV，并给出与基准目录的差异报告。"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Iterable, Sequence

from .derive import DailyRow, RoundTrip
from .parse import Event

TRADES_COLUMNS = ["date", "time", "code", "name", "type", "qty", "price", "amt", "cash",
                  "comm", "oth", "stamp", "tfr", "bal_sh", "bal_cash", "side", "netpx"]
ROUNDTRIP_COLUMNS = ["code", "name", "open_time", "close_time", "qty", "buy_px", "sell_px",
                     "cost", "pnl", "ret", "kind", "hold_days", "hold_td"]
EQUITY_COLUMNS = ["date", "equity", "mv", "cash", "dep", "cumdep", "pnl", "npos"]


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        return f"{v:.6f}".rstrip("0").rstrip(".") if v != int(v) else f"{int(v)}"
    return v


def _write(path: Path, columns: Sequence[str], rows: Iterable[Sequence]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(columns)
        for r in rows:
            w.writerow([_fmt(x) for x in r])
            n += 1
    return n


def write_events(events: Sequence[Event], path: Path) -> int:
    """事件级明细（含类别，便于人工核对每一行）。"""
    cols = ["trade_date", "trade_time", "code", "name", "raw_type", "category", "side", "qty",
            "price", "amount", "cash", "comm", "other_fee", "stamp", "transfer_fee",
            "net_px", "kind", "shares_after", "cash_after", "deal_no", "event_uid"]
    return _write(path, cols, ([getattr(e, c) for c in cols] for e in events))


def write_trades_clean(events: Sequence[Event], path: Path) -> int:
    """与临时基准同列的成交表（仅 买/卖/新股入账/配售缴款）。"""
    rows = []
    for e in events:
        if e.category not in {"trade_buy", "trade_sell", "security_in", "allocation_pay"}:
            continue
        rows.append([e.trade_date, e.trade_time, e.code, e.name, e.raw_type, e.qty, e.price,
                     e.amount, e.cash, e.comm, e.other_fee, e.stamp, e.transfer_fee,
                     e.shares_after, e.cash_after, e.side, e.net_px])
    return _write(path, TRADES_COLUMNS, rows)


def write_roundtrips(roundtrips: Sequence[RoundTrip], path: Path) -> int:
    rows = [[r.code, r.name, r.open_time, r.close_time, r.qty, r.buy_px, r.sell_px, r.cost,
             r.pnl, r.ret, r.kind, r.hold_days, r.hold_td] for r in roundtrips]
    return _write(path, ROUNDTRIP_COLUMNS, rows)


def write_daily_equity(rows: Sequence[DailyRow], path: Path) -> int:
    return _write(path, EQUITY_COLUMNS, ([getattr(r, c) for c in EQUITY_COLUMNS] for r in rows))


def write_daily_positions(positions_by_day: dict[str, dict[str, int]], path: Path) -> int:
    codes = sorted({c for day in positions_by_day.values() for c in day})
    out = []
    for day in sorted(positions_by_day):
        out.append([day] + [positions_by_day[day].get(c, 0) for c in codes])
    return _write(path, ["date"] + codes, out)


def write_exposure(exposure_rows: Sequence[dict], path: Path) -> int:
    cols = ["date", "code", "name", "category", "chain", "mv", "equity", "weight"]
    return _write(path, cols, ([r.get(c) for c in cols] for r in exposure_rows))


def write_industry_exposure(rows: Sequence[dict], path: Path) -> int:
    cols = ["date", "category", "mv", "equity", "weight", "codes"]
    return _write(path, cols, ([r.get(c) for c in cols] for r in rows))


def dump_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
