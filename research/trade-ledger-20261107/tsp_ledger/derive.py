"""派生层：FIFO 回合、日频权益与持仓、单票/行业暴露。

口径（与 docs/FIELD_DICT.md 一致）
----------------------------------
1. 现金 = Σ 发生金额（已含佣金/印花税/过户费，不重复扣费）。
2. 权益 = 现金 + 持仓市值；市值按**不复权收盘价**逐日重估。
3. 资金余额栏只作为核对项，不参与权益计算：该栏是逐笔事件的即时余额（含 T+1 在途，
   卖出款次日入账），且本单 2025-09-04 发生过一次台账切换（台账间现金划转取 −10,000
   → 余额 0.00；存 +10,000 → 新台账余额 10,758.03），新台账继承了 758.03 元期初余额，
   而它未以任何发生金额记录。因此切换行 10,758.03 与累计发生金额 44.34 相差
   10,713.67 元；文件最新一笔（2026-11-06 14:53:24 证券转银行）余额 1,937.57 与累计
   发生金额 44.34 相差 1,893.23 元。两边都对不上，所以权益一律用"Σ发生金额 + 持仓市值"。
4. 回合 = FIFO：卖出按买入时间先后逐笔消耗，一笔卖出可拆成多行。
5. 未配对 = 有卖出但同代码无买入：本单 6 笔转债卖出（对应 6 笔配售缴款 + 6 笔新股
   入账）。券商把可转债配售拆成两行且代码不同（缴款记发债代码 754019/371132…，
   到账记转债代码 113708/123287…），FIFO 无法自然配对，因此按 (发生日期, 数量,
   名称前两字) 把缴款成本 100 元/张挂到转债代码上，pnl 为推算值并标
   ``unmatched_sell``，不进胜率分母。
"""
from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, Sequence

from .parse import Event


# ── 交易日历 ─────────────────────────────────────────────────────────


class TradingCalendar:
    """交易日历。优先用系统行情库的日期分区，缺失时退化为工作日。"""

    def __init__(self, days: Sequence[str] | None = None):
        self._days = sorted(set(days or []))
        self._index = {d: i for i, d in enumerate(self._days)}
        self.approx = not self._days

    def between(self, start: str, end: str) -> int:
        """两个日期之间的交易日数（不含 start，含 end）。"""
        if start == end:
            return 0
        if self.approx:
            return self._approx_between(start, end)
        i, j = self._index.get(start), self._index.get(end)
        if i is None or j is None:
            return self._approx_between(start, end)
        return max(0, j - i)

    @staticmethod
    def _approx_between(start: str, end: str) -> int:
        d0 = datetime.strptime(start, "%Y-%m-%d").date()
        d1 = datetime.strptime(end, "%Y-%m-%d").date()
        if d1 <= d0:
            return 0
        n = 0
        cur = d0
        while cur < d1:
            cur += timedelta(days=1)
            if cur.weekday() < 5:
                n += 1
        return n

    def span(self, start: str, end: str) -> list[str]:
        """返回 [start, end] 内的交易日列表（含两端）。"""
        if self.approx:
            out, cur = [], datetime.strptime(start, "%Y-%m-%d").date()
            stop = datetime.strptime(end, "%Y-%m-%d").date()
            while cur <= stop:
                if cur.weekday() < 5:
                    out.append(cur.isoformat())
                cur += timedelta(days=1)
            return out
        return [d for d in self._days if start <= d <= end]


# ── FIFO 回合 ────────────────────────────────────────────────────────


@dataclass
class Lot:
    open_time: str
    qty: int
    unit_cost: float      # 含费单价
    event_uid: str


@dataclass
class RoundTrip:
    code: str
    name: str
    open_time: str | None
    close_time: str
    qty: int
    buy_px: float | None
    sell_px: float
    cost: float | None
    pnl: float | None
    ret: float | None
    kind: str
    hold_days: float
    hold_td: float
    sell_event_uid: str = ""
    buy_event_uids: str = ""
    unmatched_qty: int = 0        # 该卖出里没有买入来源的股数
    pnl_adj: float | None = None  # 转债按配售缴款成本修正后的盈亏
    flags: str = ""


def build_roundtrips(
    events: Iterable[Event],
    calendar: TradingCalendar,
    bond_cost: dict[str, float] | None = None,
    newbond_as_sell: bool = False,
    compat_newbond: bool = False,
) -> list[RoundTrip]:
    """按 FIFO 生成回合表。

    ``bond_cost``: {转债代码: 每张成本}，用于把"配售缴款"的成本挂到"新股入账"
    得到的转债上（两者代码不同，FIFO 无法自然配对）。
    """
    lots: dict[str, deque[Lot]] = defaultdict(deque)
    out: list[RoundTrip] = []
    names: dict[str, str] = {}
    bond_cost = bond_cost or {}

    for ev in sorted(events, key=lambda e: (e.trade_date, e.trade_time, e.row_no * -1)):
        if ev.category == "trade_buy" and ev.qty > 0:
            names[ev.code] = ev.name or names.get(ev.code, "")
            lots[ev.code].append(Lot(ev.ts, ev.qty, ev.net_px, ev.event_uid))
        elif ev.category == "security_in" and compat_newbond:
            # 兼容口径：把"新股入账"当成一笔 0 价卖出，复刻临时 CSV 的 447 回合。
            # 这是临时口径的缺陷（无买入来源却能卖），仅供与历史基准对比，不作默认。
            names[ev.code] = ev.name or names.get(ev.code, "")
            out.append(
                RoundTrip(
                    code=ev.code, name=ev.name, open_time=None, close_time=ev.ts,
                    qty=ev.qty, buy_px=None, sell_px=0.0, cost=None, pnl=None, ret=None,
                    kind=ev.kind, hold_days=float("nan"), hold_td=float("nan"),
                    sell_event_uid=ev.event_uid, unmatched_qty=ev.qty,
                    flags="unmatched_newbond",
                )
            )
        elif ev.category == "security_in" and newbond_as_sell:
            names[ev.code] = ev.name or names.get(ev.code, "")
            lots[ev.code].append(Lot(ev.ts, ev.qty, 0.0, ev.event_uid))
        elif ev.category == "trade_sell" and ev.qty > 0:
            names[ev.code] = ev.name or names.get(ev.code, "")
            remaining = ev.qty
            queue = lots[ev.code]
            while remaining > 0 and queue:
                lot = queue[0]
                take = min(remaining, lot.qty)
                cost = take * lot.unit_cost
                pnl = take * (ev.net_px - lot.unit_cost)
                out.append(
                    RoundTrip(
                        code=ev.code,
                        name=names[ev.code],
                        open_time=lot.open_time,
                        close_time=ev.ts,
                        qty=take,
                        buy_px=lot.unit_cost,
                        sell_px=ev.net_px,
                        cost=round(cost, 2),
                        pnl=round(pnl, 2),
                        ret=pnl / cost if cost else None,
                        kind=ev.kind,
                        hold_days=_elapsed_days(lot.open_time, ev.ts),
                        hold_td=float(calendar.between(lot.open_time[:10], ev.trade_date)),
                        sell_event_uid=ev.event_uid,
                        buy_event_uids=lot.event_uid,
                    )
                )
                lot.qty -= take
                remaining -= take
                if lot.qty == 0:
                    queue.popleft()
            if remaining > 0:
                # 无买入来源：仅记卖出侧，盈亏留空（前端展示为"数据缺口"）
                unit_cost = bond_cost.get(ev.code)
                cost = remaining * unit_cost if unit_cost is not None else None
                pnl = remaining * (ev.net_px - unit_cost) if unit_cost is not None else None
                out.append(
                    RoundTrip(
                        code=ev.code,
                        name=names[ev.code] or ev.name,
                        open_time=None,
                        close_time=ev.ts,
                        qty=remaining,
                        buy_px=unit_cost,
                        sell_px=ev.net_px,
                        cost=round(cost, 2) if cost is not None else None,
                        pnl=round(pnl, 2) if pnl is not None else None,
                        ret=(pnl / cost) if (pnl is not None and cost) else None,
                        kind=ev.kind,
                        hold_days=float("nan"),
                        hold_td=float("nan"),
                        sell_event_uid=ev.event_uid,
                        unmatched_qty=remaining,
                        flags="unmatched_sell",
                    )
                )
    return out


def bond_cost_map(events: Iterable[Event]) -> dict[str, float]:
    """把"配售缴款"的每张成本映射到"新股入账"得到的转债代码上。

    券商把可转债配售拆成两行且代码不同：
    * 配售缴款：代码 072125/370763/754019…（发债代码），qty 10，现金 −1000
    * 新股入账：代码 127109/123259/113708…（转债代码），qty 10，现金 0

    配对规则（按优先级）：
    1. (发生日期, 数量, 名称前两字) 全等 —— 本单 6 组均如此；
    2. 日期对不上时，退化为 (数量, 名称前两字) 且两侧候选唯一 —— 避免跨标的错配，
       有歧义就不猜，宁可留空。
    """
    alloc: list[Event] = []
    bonds: list[Event] = []
    for ev in events:
        if ev.category == "allocation_pay" and ev.qty > 0:
            alloc.append(ev)
        elif ev.category == "security_in" and ev.qty > 0:
            bonds.append(ev)

    def unit_cost(ev: Event) -> float:
        return abs(ev.cash) / ev.qty

    def same(name_a: str, name_b: str) -> bool:
        a, b = (name_a or "")[:2], (name_b or "")[:2]
        return bool(a) and bool(b) and a == b

    out: dict[str, float] = {}
    used = [False] * len(alloc)
    pending: list[Event] = []

    for b in bonds:
        hit = None
        for i, pay in enumerate(alloc):
            if used[i] or pay.qty != b.qty or pay.trade_date != b.trade_date:
                continue
            if same(pay.name, b.name):
                hit = i
                break
        if hit is None:
            pending.append(b)
            continue
        used[hit] = True
        out[b.code] = unit_cost(alloc[hit])

    for b in pending:
        cands = [
            (i, pay) for i, pay in enumerate(alloc)
            if not used[i] and pay.qty == b.qty and same(pay.name, b.name)
        ]
        if len(cands) == 1:
            i, pay = cands[0]
            used[i] = True
            out[b.code] = unit_cost(pay)
    return out


def _elapsed_days(open_time: str, close_time: str) -> float:
    fmt = "%Y-%m-%d %H:%M:%S"
    a = datetime.strptime(_norm_ts(open_time), fmt)
    b = datetime.strptime(_norm_ts(close_time), fmt)
    return float(math.floor((b - a).total_seconds() / 86400))


def _norm_ts(ts: str) -> str:
    ts = ts.strip()
    return ts if len(ts) >= 19 else f"{ts} 00:00:00"


# ── 日频权益与持仓 ───────────────────────────────────────────────────


@dataclass
class DailyRow:
    date: str
    equity: float
    mv: float
    cash: float
    dep: float
    cumdep: float
    pnl: float
    npos: int


def build_daily(
    events: Sequence[Event],
    calendar: TradingCalendar,
    prices: "PriceBook",
    opening_cash: float = 0.02,
) -> tuple[list[DailyRow], dict[str, dict[str, int]], list[dict]]:
    """逐日推进现金与持仓，按收盘价重估市值。

    返回 (日频权益, {date: {code: qty}}, 持仓明细)。持仓明细含成本、市值、
    浮动盈亏，供单票/行业暴露使用。
    """
    by_date: dict[str, list[Event]] = defaultdict(list)
    for ev in events:
        by_date[ev.trade_date].append(ev)

    days = calendar.span(min(by_date), max(by_date)) if by_date else []
    cash = opening_cash
    cumdep = 0.0
    pos: dict[str, int] = defaultdict(int)
    # FIFO 批次：{code: deque[[qty, unit_cost]]}，与 build_roundtrips 同一口径，
    # 保证"剩余持仓成本"与"已实现回合盈亏"能拼成权益变化（不混用平均成本）
    lots: dict[str, deque[list[float]]] = defaultdict(deque)
    pos_detail: dict[str, dict] = {}
    rows: list[DailyRow] = []
    positions_by_day: dict[str, dict[str, int]] = {}
    detail_rows: list[dict] = []

    for day in days:
        dep_today = 0.0
        for ev in by_date.get(day, []):
            cash += ev.cash
            if ev.category in {"trade_buy", "security_in"} and ev.qty:
                pos[ev.code] += ev.qty
                unit = 0.0 if ev.category == "security_in" else ev.net_px
                lots[ev.code].append([ev.qty, unit])
                d = pos_detail.setdefault(ev.code, {"name": ev.name, "qty": 0, "cost": 0.0, "kind": ev.kind})
                d["qty"] += ev.qty
            elif ev.category == "trade_sell" and ev.qty:
                remaining = ev.qty
                queue = lots[ev.code]
                while remaining > 0 and queue:
                    take = min(remaining, queue[0][0])
                    queue[0][0] -= take
                    remaining -= take
                    if queue[0][0] <= 0:
                        queue.popleft()
                pos[ev.code] -= ev.qty
                d = pos_detail.setdefault(ev.code, {"name": ev.name, "qty": 0, "cost": 0.0, "kind": ev.kind})
                d["qty"] = max(0, d["qty"] - ev.qty)
            if ev.category in {"deposit_in", "deposit_out"}:
                dep_today += ev.cash
        cumdep += dep_today
        mv = 0.0
        npos = 0
        detail_start = len(detail_rows)
        for code, qty in pos.items():
            if qty <= 0:
                continue
            npos += 1
            px = prices.close(code, day)
            value = qty * px
            mv += value
            d = pos_detail.setdefault(code, {"name": "", "qty": 0, "cost": 0.0, "kind": ""})
            cost = sum(q * unit for q, unit in lots[code])
            d["cost"] = cost
            detail_rows.append(
                {
                    "date": day,
                    "code": code,
                    "name": d["name"],
                    "kind": d["kind"],
                    "qty": qty,
                    "cost": round(cost, 2),
                    "price": px,
                    "price_src": prices.source(code, day),
                    "mv": round(value, 2),
                    "upnl": round(value - cost, 2),
                }
            )
        equity = cash + mv
        for dr in detail_rows[detail_start:]:
            dr["equity"] = round(equity, 2)
        rows.append(
            DailyRow(
                date=day,
                equity=round(equity, 2),
                mv=round(mv, 2),
                cash=round(cash, 2),
                dep=round(dep_today, 2),
                cumdep=round(cumdep, 2),
                pnl=round(equity - cumdep - opening_cash, 2),
                npos=npos,
            )
        )
        positions_by_day[day] = {c: q for c, q in pos.items() if q > 0}
    return rows, positions_by_day, detail_rows


# ── 价格源 ───────────────────────────────────────────────────────────


class PriceBook:
    """收盘价簿。支持三种取值策略：

    * ``close``   —— 当日不复权收盘价（默认，与既有 CSV 口径一致）
    * ``ffill``   —— 停牌/缺数据时用最近可用收盘价
    * ``last_trade`` —— 再退回本次导入里该代码最后一个成交价（用于 ETF/转债等
      行情库未收录的品种）
    """

    def __init__(self, closes: dict[str, dict[str, float]], last_trade: dict[str, list[tuple[str, float]]] | None = None, mode: str = "close"):
        self._closes = closes
        self._hist = last_trade or {}
        self.mode = mode

    def close(self, code: str, day: str) -> float:
        series = self._closes.get(code)
        if series and day in series:
            return series[day]
        if self.mode == "ffill" and series:
            prior = [d for d in series if d <= day]
            if prior:
                return series[max(prior)]
        if self.mode == "last_trade":
            hist = self._hist.get(code, [])
            prior = [p for d, p in hist if d <= day]
            if prior:
                return prior[-1]
            if series:
                prior_days = [d for d in series if d <= day]
                if prior_days:
                    return series[max(prior_days)]
        return 0.0

    def coverage(self) -> dict:
        """价格簿覆盖度（用于派生前的健全性检查，避免"缺 polars → 市值全 0"静默出错）。"""
        days = {d for series in self._closes.values() for d in series}
        return {
            "codes": len(self._closes),
            "days": len(days),
            "day_min": min(days) if days else None,
            "day_max": max(days) if days else None,
            "mode": self.mode,
        }

    def source(self, code: str, day: str) -> str:
        series = self._closes.get(code)
        if series and day in series:
            return "close"
        if self.mode == "ffill" and series:
            return "ffill"
        if self.mode == "last_trade" and self._hist.get(code):
            return "last_trade"
        return "missing"

    @property
    def codes(self) -> set[str]:
        return set(self._closes)
