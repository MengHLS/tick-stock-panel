"""FIFO trade pairing and per-roundtrip quantitative review."""
from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from datetime import date, datetime
from typing import Any

ANALYSIS_VERSION = 2


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _trade_key(close_id: str, open_ids: list[str]) -> str:
    payload = close_id + "|" + ",".join(sorted(open_ids))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:24]


def _fill_fees(fill: dict[str, Any]) -> float:
    return (
        float(fill["commission"]) + float(fill["other_fee"])
        + float(fill["stamp_tax"]) + float(fill["transfer_fee"])
    )


def compute_roundtrips(fills: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pair one complete position cycle: first buy → position back to zero.

    A cycle may contain multiple adds and partial exits. Only the final sell that
    flattens the position closes the cycle, so one "trade" matches one holding
    decision from entry to exit.
    """
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fill in fills:
        by_symbol[fill["symbol"]].append(fill)

    trades: list[dict[str, Any]] = []
    open_positions: list[dict[str, Any]] = []
    for symbol, rows in by_symbol.items():
        rows.sort(key=lambda item: (item["trade_date"], item["trade_time"], item["id"]))
        position = 0
        cost = 0.0
        remaining_cost = 0.0
        proceeds = 0.0
        fees = 0.0
        legs: list[dict[str, Any]] = []
        buy_ids: list[str] = []
        open_date = ""
        open_time = ""
        name = ""
        started = False

        for fill in rows:
            qty = int(fill["qty"])
            fill_fee = _fill_fees(fill)
            if fill["side"] == "B":
                if position == 0:
                    position = 0
                    cost = 0.0
                    remaining_cost = 0.0
                    proceeds = 0.0
                    fees = 0.0
                    legs = []
                    buy_ids = []
                    open_date = fill["trade_date"]
                    open_time = fill["trade_time"]
                    name = fill["name"]
                    started = True
                position += qty
                cost += -float(fill["cash_flow"])
                remaining_cost += -float(fill["cash_flow"])
                fees += fill_fee
                buy_ids.append(fill["id"])
                legs.append({
                    "date": fill["trade_date"],
                    "time": fill["trade_time"],
                    "side": "B",
                    "qty": qty,
                    "price": float(fill["price"]),
                    "cash_flow": float(fill["cash_flow"]),
                    "fees": fill_fee,
                })
                continue

            if position <= 0:
                continue
            matched_qty = min(qty, position)
            ratio = matched_qty / qty
            average_cost = remaining_cost / position if position > 0 else 0.0
            remaining_cost -= average_cost * matched_qty
            position -= matched_qty
            proceeds += float(fill["cash_flow"]) * ratio
            fees += fill_fee * ratio
            legs.append({
                "date": fill["trade_date"],
                "time": fill["trade_time"],
                "side": "S",
                "qty": matched_qty,
                "price": float(fill["price"]),
                "cash_flow": float(fill["cash_flow"]) * ratio,
                "fees": fill_fee * ratio,
            })
            if position > 0:
                continue

            if started and cost > 0:
                trade_qty = sum(item["qty"] for item in legs if item["side"] == "B")
                hold_days = max(
                    (_date(fill["trade_date"]) - _date(open_date)).days
                    if _date(fill["trade_date"]) and _date(open_date) else 0,
                    0,
                )
                buy_count = sum(1 for item in legs if item["side"] == "B")
                sell_count = sum(1 for item in legs if item["side"] == "S")
                pnl = proceeds - cost
                trades.append({
                    "trade_key": _trade_key(fill["id"], buy_ids),
                    "symbol": symbol,
                    "name": fill["name"] or name,
                    "open_date": open_date,
                    "open_time": open_time,
                    "close_date": fill["trade_date"],
                    "close_time": fill["trade_time"],
                    "qty": trade_qty,
                    "buy_price": cost / trade_qty if trade_qty else 0.0,
                    "sell_price": proceeds / trade_qty if trade_qty else 0.0,
                    "cost": cost,
                    "proceeds": proceeds,
                    "pnl": pnl,
                    "ret": pnl / cost if cost > 0 else None,
                    "fees": fees,
                    "hold_days": hold_days,
                    "buy_count": buy_count,
                    "sell_count": sell_count,
                    "legs": legs,
                    "open_ids": buy_ids,
                    "close_id": fill["id"],
                })
            position = 0
            cost = 0.0
            remaining_cost = 0.0
            proceeds = 0.0
            fees = 0.0
            legs = []
            buy_ids = []
            started = False

        if position > 0:
            open_positions.append({
                "symbol": symbol,
                "name": name,
                "qty": position,
                "avg_cost": remaining_cost / position if position else 0.0,
                "open_date": open_date,
                "open_time": open_time,
            })

    trades.sort(key=lambda item: (item["close_date"], item["close_time"], item["symbol"]), reverse=True)
    open_positions.sort(key=lambda item: (item["open_date"], item["symbol"]), reverse=True)
    return trades, open_positions


def normalize_bars(frame: Any) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "is_empty", lambda: True)():
        return []
    result = []
    for row in frame.sort("date").to_dicts():
        day = _date(row.get("date"))
        if day is None:
            continue
        high = _finite(row.get("high"))
        low = _finite(row.get("low"))
        close = _finite(row.get("close"))
        if high is None or low is None or close is None:
            continue
        result.append({
            "date": day,
            "open": _finite(row.get("open")),
            "high": high,
            "low": low,
            "close": close,
        })
    deduped = {item["date"]: item for item in result}
    return [deduped[key] for key in sorted(deduped)]


def _ratio(value: float | None, base: float) -> float | None:
    if value is None or base <= 0:
        return None
    return value / base - 1


def analyze_trade(
    trade: dict[str, Any],
    bars: list[dict[str, Any]],
) -> dict[str, Any]:
    open_day = _date(trade["open_date"])
    close_day = _date(trade["close_date"])
    buy_price = float(trade["buy_price"])
    sell_price = float(trade["sell_price"])
    legs = trade.get("legs") or []
    first_buy_price = (
        float(legs[0]["price"]) if legs and legs[0].get("side") == "B" else buy_price
    )
    hold_bars = [
        item for item in bars
        if open_day is not None and close_day is not None and open_day <= item["date"] <= close_day
    ]
    before = [item for item in bars if open_day is not None and item["date"] < open_day]
    after = [item for item in bars if close_day is not None and item["date"] > close_day]

    hold_td = max(len(hold_bars) - 1, 0) if hold_bars else None
    mfe = max((item["high"] / buy_price - 1 for item in hold_bars), default=None)
    mae = min((item["low"] / buy_price - 1 for item in hold_bars), default=None)
    open_bar = next((item for item in bars if item["date"] == open_day), None)
    exit_bar = next((item for item in bars if item["date"] == close_day), None)

    def range_position(bar: dict[str, Any] | None, price: float) -> float | None:
        if bar is None or bar["high"] <= bar["low"]:
            return None
        return min(max((price - bar["low"]) / (bar["high"] - bar["low"]), 0.0), 1.0)

    buy_range = range_position(open_bar, first_buy_price)
    exit_range = range_position(exit_bar, sell_price)
    ma5 = sum(item["close"] for item in before[-5:]) / len(before[-5:]) if len(before) >= 5 else None
    ma20 = sum(item["close"] for item in before[-20:]) / len(before[-20:]) if len(before) >= 20 else None
    post5 = _ratio(after[4]["close"], sell_price) if len(after) >= 5 else None
    post10 = _ratio(after[9]["close"], sell_price) if len(after) >= 10 else None
    ma5_dev = _ratio(first_buy_price, ma5) if ma5 else None
    ma20_dev = _ratio(first_buy_price, ma20) if ma20 else None
    fee_ratio = float(trade["fees"]) / float(trade["cost"]) if trade["cost"] else None
    ret = trade["ret"]

    tags: list[str] = ["盈利" if float(trade["pnl"]) >= 0 else "亏损"]
    if int(trade.get("buy_count") or 1) > 1:
        tags.append("分批建仓")
    if int(trade.get("sell_count") or 1) > 1:
        tags.append("分批卖出")
    if hold_td is not None:
        if hold_td <= 3:
            tags.append("短线")
        elif hold_td >= 20:
            tags.append("长持")
        else:
            tags.append("波段")
    if buy_range is not None and buy_range >= 0.75:
        tags.append("追高")
    elif buy_range is not None and buy_range <= 0.3:
        tags.append("低吸")
    if post5 is not None and ret is not None and post5 > 0.05 and post5 - ret > 0.05:
        tags.append("卖飞")
    if ret is not None and mae is not None and ret < -0.03 and mae < ret - 0.05:
        tags.append("止损偏慢")
    if fee_ratio is not None and fee_ratio > 0.01:
        tags.append("费用偏高")

    buy_count = int(trade.get("buy_count") or 1)
    sell_count = int(trade.get("sell_count") or 1)
    parts = [
        f"{trade['open_date']} 建仓 {trade['symbol']}，{trade['close_date']} 清仓；"
        f"共 {buy_count} 次买入、{sell_count} 次卖出，累计 {trade['qty']} 股，"
        f"均价买入 {buy_price:.2f}、卖出 {sell_price:.2f}。",
        f"持有 {hold_td if hold_td is not None else trade['hold_days']} 个交易日，"
        f"净收益 {ret * 100:+.2f}%（{trade['pnl']:+.2f} 元）。" if ret is not None else
        f"净收益 {trade['pnl']:+.2f} 元。",
    ]
    context: list[str] = []
    if buy_range is not None:
        context.append(f"建仓价位于建仓日振幅 {buy_range * 100:.0f}% 分位")
    if ma5_dev is not None:
        context.append(f"较 5 日均线 {ma5_dev * 100:+.1f}%")
    if context:
        parts.append("，".join(context) + "。")
    excursion: list[str] = []
    if mfe is not None:
        excursion.append(f"最大浮盈 {mfe * 100:+.1f}%")
    if mae is not None:
        excursion.append(f"最大浮亏 {mae * 100:+.1f}%")
    if excursion:
        parts.append("持仓期间（相对均价）" + "、".join(excursion) + "。")
    outcome: list[str] = []
    if exit_range is not None:
        outcome.append(f"卖在当日振幅 {exit_range * 100:.0f}% 分位")
    if post5 is not None:
        outcome.append(f"卖后 5 日 {post5 * 100:+.1f}%")
    if post10 is not None:
        outcome.append(f"卖后 10 日 {post10 * 100:+.1f}%")
    if outcome:
        parts.append("，".join(outcome) + "。")

    return {
        "analysis": "".join(parts),
        "analysis_status": "full" if bars else "basic",
        "tags": tags[:6],
        "hold_td": hold_td,
        "mfe": mfe,
        "mae": mae,
        "buy_range_pct": buy_range,
        "exit_range_pct": exit_range,
        "ma5_dev": ma5_dev,
        "ma20_dev": ma20_dev,
        "post5": post5,
        "post10": post10,
        "fee_ratio": fee_ratio,
    }
