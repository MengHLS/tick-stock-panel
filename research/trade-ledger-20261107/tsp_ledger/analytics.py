"""统计与对账：暴露、绩效指标、权益→回合的桥接表。

所有函数都是纯计算，不写库、不读网络。
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

from .derive import DailyRow, RoundTrip

INDUSTRY_GRAPH = Path(r"D:\TSP\data\user_data\industry_chain\graph.json")


def load_industry_map(path: Path | str = INDUSTRY_GRAPH) -> dict[str, dict[str, str]]:
    """从系统产业链图谱读取 代码 → 一级分类/产业链。

    同一只股票可能挂多条链，按 (category.order, chain.order, sort_order) 取首条为主，
    其余并列写入 ``chains``。缺失的代码在暴露表里标 ``未分类``。
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    cats = {c["id"]: c for c in data.get("categories", [])}
    chains = {c["id"]: c for c in data.get("chains", [])}
    nodes = {n["id"]: n for n in data.get("nodes", [])}

    def chain_of(node_id: str) -> str | None:
        seen = 0
        cur = nodes.get(node_id)
        while cur and seen < 10:
            if cur.get("chain_id"):
                return cur["chain_id"]
            cur = nodes.get(cur.get("parent_id")) if cur.get("parent_id") else None
            seen += 1
        return None

    best: dict[str, tuple[tuple, dict[str, str], set[str]]] = {}
    for link in data.get("stock_links", []):
        sym = link.get("symbol") or ""
        code = sym.split(".")[0]
        chain_id = chain_of(link.get("node_id") or "")
        if not code or not chain_id:
            continue
        chain = chains.get(chain_id, {"name": chain_id, "order": 999, "category_id": ""})
        cat = cats.get(chain.get("category_id", ""), {"name": "未分类", "order": 999})
        key = (
            cat.get("order", 999),
            chain.get("order", 999),
            link.get("sort_order", 999),
            link.get("id", ""),
        )
        item = {"category": cat.get("name", "未分类"), "chain": chain.get("name", chain_id)}
        prev = best.get(code)
        if prev is None or key < prev[0]:
            best[code] = (key, item, {chain.get("name", chain_id)} | (prev[2] if prev else set()))
        else:
            prev[2].add(chain.get("name", chain_id))
    return {
        code: {**item, "chains": ";".join(sorted(chain_names))}
        for code, (_, item, chain_names) in best.items()
    }


def build_exposure(
    detail_rows: Sequence[dict],
    industry: dict[str, dict[str, str]] | None = None,
) -> list[dict]:
    """单票暴露（占当日权益比重）。"""
    industry = industry or {}
    out = []
    for r in detail_rows:
        equity = r.get("equity") or 0.0
        meta = industry.get(r["code"], {})
        out.append(
            {
                "date": r["date"],
                "code": r["code"],
                "name": r.get("name", ""),
                "category": meta.get("category", "未分类"),
                "chain": meta.get("chain", ""),
                "mv": r.get("mv", 0.0),
                "equity": equity,
                "weight": (r["mv"] / equity) if equity else 0.0,
            }
        )
    return out


def industry_exposure(exposure_rows: Sequence[dict]) -> list[dict]:
    """按 (date, category) 汇总行业暴露。"""
    agg: dict[tuple[str, str], dict] = {}
    for r in exposure_rows:
        key = (r["date"], r["category"])
        item = agg.setdefault(
            key, {"date": r["date"], "category": r["category"], "mv": 0.0, "equity": r["equity"], "codes": []}
        )
        item["mv"] += r["mv"]
        item["equity"] = r["equity"]
        item["codes"].append(r["code"])
    out = []
    for (date, cat), item in sorted(agg.items()):
        out.append(
            {
                "date": date,
                "category": cat,
                "mv": round(item["mv"], 2),
                "equity": item["equity"],
                "weight": (item["mv"] / item["equity"]) if item["equity"] else 0.0,
                "codes": ";".join(sorted(item["codes"])),
            }
        )
    return out


#: 计算回撤时忽略权益低于该值的交易日（期初现金 0.02 元，分母过小会让回撤虚高到 100%）
DD_EQUITY_FLOOR = 1000.0


def _drawdown(daily: Sequence[DailyRow], floor: float = 0.0) -> float:
    peak = 0.0
    worst = 0.0
    for d in daily:
        if d.equity < floor:
            continue
        peak = max(peak, d.equity)
        if peak > 0:
            worst = max(worst, (peak - d.equity) / peak)
    return worst


def performance(roundtrips: Sequence[RoundTrip], calendar_days: Sequence[str], daily: Sequence[DailyRow], events: Sequence) -> dict:
    """回合级与账户级绩效指标。

    胜负统计只取 FIFO 完整配对的回合（``flags`` 为空且 ``pnl`` 非空）；
    ``unmatched_sell``（卖出无买入来源、成本按配售缴款推算）单列，不进胜率分母，
    避免用估算成本影响胜率与盈亏比。
    """
    paired = [r for r in roundtrips if r.pnl is not None and not r.flags]
    unmatched = [r for r in roundtrips if r.flags]
    pnls = [r.pnl for r in paired]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    equity = daily[-1].equity if daily else 0.0
    max_dd = _drawdown(daily, DD_EQUITY_FLOOR)
    max_dd_raw = _drawdown(daily)
    avg_equity = sum(d.equity for d in daily) / len(daily) if daily else 0.0
    buy_amt = sum(abs(e.amount) for e in events if e.category == "trade_buy")
    sell_amt = sum(abs(e.amount) for e in events if e.category == "trade_sell")
    fees = sum(e.comm + e.other_fee + e.stamp + e.transfer_fee for e in events if e.category in {"trade_buy", "trade_sell"})
    holds = sorted(_hold_bucket(r) for r in paired)
    rets = [r.ret for r in paired if r.ret is not None]
    pnl_unmatched = sum((r.pnl or 0.0) for r in unmatched)
    return {
        "roundtrips": len(roundtrips),
        "roundtrips_paired": len(paired),
        "roundtrips_unmatched": len(unmatched),
        "roundtrips_unmatched_sell": len(unmatched),
        "pnl_realized": round(sum(pnls), 2),
        "pnl_unmatched_est": round(pnl_unmatched, 2),
        "pnl_total_est": round(sum(pnls) + pnl_unmatched, 2),
        "win_rate": (len(wins) / len(paired)) if paired else 0.0,
        "avg_win": (gross_win / len(wins)) if wins else 0.0,
        "avg_loss": (gross_loss / len(losses)) if losses else 0.0,
        "payoff": (gross_win / len(wins)) / (gross_loss / len(losses)) if wins and losses and gross_loss else 0.0,
        "profit_factor": (gross_win / gross_loss) if gross_loss else float("inf"),
        "expectancy": (sum(pnls) / len(paired)) if paired else 0.0,
        "avg_ret": (sum(rets) / len(rets)) if rets else 0.0,
        "hold_median_td": _median(holds),
        "buy_amount": round(buy_amt, 2),
        "sell_amount": round(sell_amt, 2),
        "turnover_x": (buy_amt + sell_amt) / avg_equity if avg_equity else 0.0,
        "fees": round(fees, 2),
        "fee_ratio": fees / avg_equity if avg_equity else 0.0,
        "avg_equity": round(avg_equity, 2),
        "equity_end": equity,
        "cum_deposit": daily[-1].cumdep if daily else 0.0,
        "cum_pnl": daily[-1].pnl if daily else 0.0,
        "max_drawdown": max_dd,
        "max_drawdown_raw": max_dd_raw,
        "drawdown_equity_floor": DD_EQUITY_FLOOR,
        "trading_days": len(calendar_days),
    }


def _hold_bucket(r: RoundTrip) -> float:
    return 0.0 if (r.hold_td is None or (isinstance(r.hold_td, float) and math.isnan(r.hold_td))) else r.hold_td


def _median(v: Sequence[float]) -> float:
    if not v:
        return 0.0
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def pnl_bridge(roundtrips: Sequence[RoundTrip], daily: Sequence[DailyRow], events: Sequence, detail_rows: Sequence[dict] | None = None) -> dict:
    """把"权益口径累计盈亏"拆解成可核对的桥接表。

    权益口径：cum_pnl = 期末权益 − 累计净入金 − 期初现金
    桥接：已实现回合盈亏（仅完整配对）+ 未配对卖出净额 − 对应成本 + 其他损益 + 期末浮盈
    = 权益口径。未配对回合的盈亏已经在"净额 − 成本"里体现，不能再计入已实现，否则重复计。
    """
    paired_matched = [r for r in roundtrips if r.pnl is not None and not r.flags]
    matched = [r for r in roundtrips if r.flags != "unmatched_sell"]
    unmatched = [r for r in roundtrips if r.flags == "unmatched_sell"]
    unmatched_net = sum(r.qty * r.sell_px for r in unmatched)
    bond_cost = sum((r.cost or 0.0) for r in unmatched)
    other = sum(e.cash for e in events if e.category in {"dividend", "dividend_tax", "interest", "advisory_fee"})
    last_day = daily[-1].date if daily else None
    unrealized = 0.0
    if detail_rows and last_day:
        unrealized = sum(r.get("upnl", 0.0) for r in detail_rows if r.get("date") == last_day)
    realized = sum(r.pnl for r in paired_matched)
    adj_realized = sum((r.pnl_adj if r.pnl_adj is not None else (r.pnl or 0.0)) for r in roundtrips)
    cum_pnl = daily[-1].pnl if daily else 0.0
    derived = realized + unmatched_net - bond_cost + other + unrealized
    return {
        "roundtrip_pnl": round(realized, 2),
        "roundtrip_pnl_adj": round(adj_realized, 2),
        "unmatched_sell_proceeds": round(unmatched_net, 2),
        "unmatched_bond_cost": round(bond_cost, 2),
        "other_pnl": round(other, 2),
        "unrealized_end": round(unrealized, 2),
        "derived_total": round(derived, 2),
        "equity_cum_pnl": round(cum_pnl, 2),
        "residual": round(cum_pnl - derived, 2),
        "matched_roundtrips": len(matched),
        "unmatched_roundtrips": len(unmatched),
    }
