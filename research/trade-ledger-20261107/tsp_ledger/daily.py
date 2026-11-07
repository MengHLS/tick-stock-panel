"""每日复盘入口：一条命令产出某交易日的复盘包。

输入：交易日 + 交割单文件（可选，重复导入幂等）
输出：
    <out>/<date>/events.csv          当日全部事件（含转账/利息）
    <out>/<date>/fills.csv           当日成交明细（含费用拆分、含费净价）
    <out>/<date>/roundtrips.csv      当日平仓回合（FIFO）+ 当日开仓仍未平的部分
    <out>/<date>/equity.csv          当日权益变化（较前一交易日）
    <out>/<date>/positions.csv       当日日终持仓
    <out>/<date>/reconcile.csv       与系统信号的对账表（实际列已填，计划/信号列留空待填）
    <out>/<date>/summary.md          一页纸复盘摘要
"""
from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .derive import DailyRow, RoundTrip
from .parse import Event

RECONCILE_COLUMNS = [
    "date", "time", "code", "name", "side", "actual_qty", "actual_px", "actual_amt", "fees",
    "signal_id", "plan_time", "plan_side", "plan_qty", "plan_px",
    "deviation_type", "deviation_reason", "link_status", "note",
]


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        if v != v:
            return ""
        return f"{v:.6f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return v


def _write(path: Path, columns: Sequence[str], rows: Sequence[Sequence]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(columns)
        for r in rows:
            w.writerow([_fmt(x) for x in r])


def _day_events(events: Sequence[Event], day: str) -> list[Event]:
    return [e for e in events if e.trade_date == day]


def _equity_change(daily: Sequence[DailyRow], day: str) -> dict:
    idx = {r.date: i for i, r in enumerate(daily)}
    if day not in idx:
        return {}
    i = idx[day]
    cur = daily[i]
    prev = daily[i - 1] if i else None
    return {
        "date": day,
        "equity": cur.equity,
        "mv": cur.mv,
        "cash": cur.cash,
        "dep": cur.dep,
        "cumdep": cur.cumdep,
        "pnl": cur.pnl,
        "npos": cur.npos,
        "equity_prev": prev.equity if prev else None,
        "equity_chg": round(cur.equity - prev.equity, 2) if prev else None,
        "mv_chg": round(cur.mv - prev.mv, 2) if prev else None,
        "cash_chg": round(cur.cash - prev.cash, 2) if prev else None,
        "pnl_chg": round(cur.pnl - prev.pnl, 2) if prev else None,
    }


def _load_signals(path: Path | None) -> dict[tuple[str, str, str], dict]:
    """可选的系统信号/计划文件。列：date,time,code,side,qty,px,signal_id。"""
    if not path or not Path(path).exists():
        return {}
    out: dict[tuple[str, str, str], dict] = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            code = (r.get("code") or "").split(".")[0]
            key = ((r.get("date") or "").strip(), code, (r.get("side") or "").strip().upper())
            out[key] = r
    return out


def build_reconcile(events: Sequence[Event], day: str, signals: dict | None = None) -> list[list]:
    """对账表：实际成交已填，计划/信号列留空或有信号时回填。"""
    signals = signals or {}
    rows = []
    for e in _day_events(events, day):
        if e.category not in {"trade_buy", "trade_sell"}:
            continue
        fees = round(e.comm + e.other_fee + e.stamp + e.transfer_fee, 2)
        sig = signals.get((day, e.code, e.side))
        rows.append([
            e.trade_date, e.trade_time, e.code, e.name, e.side, e.qty, e.net_px, e.amount, fees,
            (sig or {}).get("signal_id", ""),
            (sig or {}).get("time", ""),
            (sig or {}).get("side", ""),
            (sig or {}).get("qty", ""),
            (sig or {}).get("px", ""),
            "待填", "",  # deviation_type / deviation_reason
            "matched" if sig else "no_signal",
            "",
        ])
    return rows


def daily_review(
    events: Sequence[Event],
    roundtrips: Sequence[RoundTrip],
    daily: Sequence[DailyRow],
    positions_by_day: dict[str, dict[str, int]],
    day: str,
    out_dir: Path,
    signals_path: Path | None = None,
) -> dict:
    out = Path(out_dir) / day
    out.mkdir(parents=True, exist_ok=True)

    evs = _day_events(events, day)
    _write(
        out / "events.csv",
        ["trade_date", "trade_time", "code", "name", "raw_type", "category", "side", "qty",
         "price", "amount", "cash", "comm", "other_fee", "stamp", "transfer_fee", "kind", "deal_no"],
        [[e.trade_date, e.trade_time, e.code, e.name, e.raw_type, e.category, e.side, e.qty,
          e.price, e.amount, e.cash, e.comm, e.other_fee, e.stamp, e.transfer_fee, e.kind, e.deal_no]
         for e in evs],
    )

    fills = [e for e in evs if e.category in {"trade_buy", "trade_sell"}]
    _write(
        out / "fills.csv",
        ["date", "time", "code", "name", "side", "qty", "price", "amount", "comm", "other_fee",
         "stamp", "transfer_fee", "net_px", "cash", "kind"],
        [[e.trade_date, e.trade_time, e.code, e.name, e.side, e.qty, e.price, e.amount, e.comm,
          e.other_fee, e.stamp, e.transfer_fee, e.net_px, e.cash, e.kind] for e in fills],
    )

    closed = [r for r in roundtrips if r.close_time.startswith(day)]
    opened = [
        r for r in roundtrips
        if r.open_time and r.open_time.startswith(day) and not r.close_time.startswith(day)
    ]
    _write(
        out / "roundtrips.csv",
        ["code", "name", "kind", "open_time", "close_time", "qty", "buy_px", "sell_px", "cost",
         "pnl", "ret", "hold_days", "hold_td", "flags"],
        [[r.code, r.name, r.kind, r.open_time, r.close_time, r.qty, r.buy_px, r.sell_px, r.cost,
          r.pnl, r.ret, r.hold_days, r.hold_td, r.flags] for r in closed],
    )

    change = _equity_change(daily, day)
    _write(
        out / "equity.csv",
        list(change.keys()) if change else ["date"],
        [list(change.values())] if change else [],
    )

    pos_rows = []
    for code, qty in sorted(positions_by_day.get(day, {}).items()):
        last = next((r for r in reversed([x for x in daily if x.date <= day])), None)
        pos_rows.append([day, code, qty])
    _write(out / "positions.csv", ["date", "code", "qty"], pos_rows)

    signals = _load_signals(signals_path)
    recon = build_reconcile(events, day, signals)
    _write(out / "reconcile.csv", RECONCILE_COLUMNS, recon)

    pnl_paired = sum(r.pnl or 0.0 for r in closed if not r.flags)
    pnl_est = sum(r.pnl or 0.0 for r in closed if r.flags)
    n_unmatched = sum(1 for r in closed if r.flags)
    fees_day = sum(e.comm + e.other_fee + e.stamp + e.transfer_fee for e in fills)
    lines = [
        f"# 复盘日报 {day}",
        "",
        "## 当日权益",
        "",
        f"- 权益 {change.get('equity')}（较前一日 {change.get('equity_chg')}），现金 {change.get('cash')}，持仓市值 {change.get('mv')}",
        f"- 外部净入金 {change.get('dep')}；累计净入金 {change.get('cumdep')}；累计盈亏 {change.get('pnl')}（日变动 {change.get('pnl_chg')}）",
        f"- 持仓只数 {change.get('npos')}",
        "",
        "## 成交与回合",
        "",
        f"- 成交 {len(fills)} 笔，费用 {fees_day:.2f} 元",
        f"- 当日平仓回合 {len(closed)} 个，已实现盈亏 {pnl_paired:.2f} 元"
        + (f"（另有 {n_unmatched} 个无买入来源的卖出，成本为推算值，盈亏 {pnl_est:.2f} 元）" if n_unmatched else ""),
        f"- 当日开仓且当日未平的回合片段 {len(opened)} 个",
        "",
        "## 对账",
        "",
        f"- 对账表 {len(recon)} 行；有信号回填 {sum(1 for r in recon if r[16]=='matched')} 行，无信号 {sum(1 for r in recon if r[16]=='no_signal')} 行",
        "- 偏离类型/原因列留空由决策侧填写（口径见 docs/FIELD_DICT.md）",
    ]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "date": day,
        "out_dir": str(out),
        "fills": len(fills),
        "closed_roundtrips": len(closed),
        "realized_pnl": round(pnl_paired, 2),
        "realized_pnl_est_unmatched": round(pnl_est, 2),
        "fees": round(fees_day, 2),
        "equity": change.get("equity"),
        "equity_chg": change.get("equity_chg"),
        "reconcile_rows": len(recon),
    }
