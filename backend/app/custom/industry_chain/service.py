"""Industry-chain scoping and equal-weight market aggregation."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import fmean
from typing import Any

import polars as pl

WINDOWS: tuple[tuple[str, int], ...] = (("d1", 1), ("d5", 5), ("d20", 20))
_FETCH_LOOKBACK_DAYS = 120


def analyze_graph(
    graph: dict[str, Any],
    *,
    chain_id: str,
    node_id: str | None,
    start: date | None,
    end: date | None,
    market_data: Any,
    name_for: Any,
) -> dict[str, Any]:
    chain = next((item for item in graph["chains"] if item["id"] == chain_id), None)
    if chain is None:
        raise ValueError(f"产业链不存在: {chain_id}")

    chain_nodes = [item for item in graph["nodes"] if item["chain_id"] == chain_id]
    node_by_id = {item["id"]: item for item in chain_nodes}
    if node_id is not None and node_id not in node_by_id:
        raise ValueError(f"节点不存在或不属于该产业链: {node_id}")

    selected_scope = _scope_ids(chain_nodes, node_id)
    parent_node = node_by_id.get(node_by_id[node_id]["parent_id"]) if node_id and node_by_id[node_id].get("parent_id") else None
    parent_scope = _scope_ids(chain_nodes, parent_node["id"]) if parent_node else set()
    chain_scope = set(node_by_id)

    scoped_links = [
        link for link in graph["stock_links"] if link["node_id"] in selected_scope
    ]
    chain_links = [
        link for link in graph["stock_links"] if link["node_id"] in chain_scope
    ]
    parent_links = [
        link for link in graph["stock_links"] if link["node_id"] in parent_scope
    ]
    symbols = sorted({link["symbol"] for link in scoped_links})
    chain_symbols = sorted({link["symbol"] for link in chain_links})
    parent_symbols = sorted({link["symbol"] for link in parent_links})

    latest = market_data.latest_daily_date()
    end_date = min(end or latest or date.today(), latest or end or date.today())
    if start is not None and start > end_date:
        raise ValueError("开始日期不能晚于结束日期")
    fetch_start = end_date - timedelta(days=_FETCH_LOOKBACK_DAYS)
    if start is not None and start < fetch_start:
        fetch_start = start

    frame = _read_daily(market_data, sorted({*symbols, *parent_symbols, *chain_symbols}), fetch_start, end_date)
    metrics = _symbol_metrics(frame, end_date)

    selected_symbols = symbols
    windows = {
        key: _aggregate(selected_symbols, metrics, key)
        for key, _ in WINDOWS
    }
    parent_windows = {
        key: _aggregate(parent_symbols, metrics, key)
        for key, _ in WINDOWS
    }
    chain_windows = {
        key: _aggregate(chain_symbols, metrics, key)
        for key, _ in WINDOWS
    }
    relative_parent = {
        key: _difference(windows[key].get("return_pct"), parent_windows[key].get("return_pct"))
        for key, _ in WINDOWS
    }
    relative_chain = {
        key: _difference(windows[key].get("return_pct"), chain_windows[key].get("return_pct"))
        for key, _ in WINDOWS
    }

    category_name = next(
        (item["name"] for item in graph["categories"] if item["id"] == chain["category_id"]),
        chain["category_id"],
    )
    links_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for link in scoped_links:
        links_by_symbol[link["symbol"]].append({
            **link,
            "node_name": node_by_id[link["node_id"]]["name"],
        })

    stocks = []
    for symbol in selected_symbols:
        item = metrics.get(symbol, {})
        links = sorted(
            links_by_symbol[symbol],
            key=lambda link: (link.get("sort_order", 100), link["id"]),
        )
        stocks.append({
            "symbol": symbol,
            "name": name_for(symbol) or symbol,
            "latest_close": item.get("latest_close"),
            "amount": item.get("amount"),
            "returns": {key: item.get(key) for key, _ in WINDOWS},
            "missing_price": symbol not in metrics,
            "links": links,
        })
    stocks.sort(key=lambda item: (
        item["returns"]["d1"] is None,
        -(item["returns"]["d1"] or 0.0),
        item["symbol"],
    ))

    requested_start = start or fetch_start
    series = _equal_weight_series(selected_symbols, metrics, requested_start, end_date)
    priced_symbols = sorted(symbol for symbol in selected_symbols if symbol in metrics)
    missing_symbols = sorted(set(selected_symbols) - set(priced_symbols))
    path = _node_path(node_by_id, node_id)

    return {
        "chain": {
            "id": chain["id"],
            "name": chain["name"],
            "category_id": chain["category_id"],
            "category_name": category_name,
        },
        "node": None if node_id is None else {
            "id": node_id,
            "name": node_by_id[node_id]["name"],
            "parent_id": node_by_id[node_id].get("parent_id"),
            "path": path,
        },
        "scope_node_ids": sorted(selected_scope),
        "start": requested_start.isoformat(),
        "end": end_date.isoformat(),
        "method": {
            "return_basis": "forward_adjusted_close",
            "aggregation": "equal_weight",
            "membership": "current_graph",
        },
        "link_count": len(scoped_links),
        "stock_count": len(selected_symbols),
        "coverage": {
            "priced_count": len(priced_symbols),
            "missing_count": len(missing_symbols),
            "missing_symbols": missing_symbols,
        },
        "windows": windows,
        "relative": {
            "parent": {
                "node_id": parent_node["id"] if parent_node else None,
                "name": parent_node["name"] if parent_node else None,
                "windows": relative_parent,
            },
            "chain": {
                "windows": relative_chain,
            },
        },
        "stocks": stocks,
        "series": series,
    }


def _scope_ids(nodes: list[dict[str, Any]], root_id: str | None) -> set[str]:
    if root_id is None:
        return {node["id"] for node in nodes}
    children: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        if node.get("parent_id"):
            children[node["parent_id"]].append(node["id"])
    scope = {root_id}
    stack = [root_id]
    while stack:
        current = stack.pop()
        for child in children.get(current, []):
            if child not in scope:
                scope.add(child)
                stack.append(child)
    return scope


def _node_path(node_by_id: dict[str, dict[str, Any]], node_id: str | None) -> list[dict[str, str]]:
    if node_id is None:
        return []
    path: list[dict[str, str]] = []
    current: str | None = node_id
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        node = node_by_id[current]
        path.append({"id": node["id"], "name": node["name"]})
        current = node.get("parent_id")
    return list(reversed(path))


def _read_daily(market_data: Any, symbols: list[str], start: date, end: date) -> pl.DataFrame:
    if not symbols:
        return pl.DataFrame()
    frame = market_data.get_daily_batch(
        symbols,
        start,
        end,
        columns=["symbol", "date", "close", "amount"],
    )
    if frame is None or frame.is_empty():
        return pl.DataFrame()
    required = {"symbol", "date", "close"}
    if not required.issubset(set(frame.columns)):
        return pl.DataFrame()
    if "amount" not in frame.columns:
        frame = frame.with_columns(pl.lit(None, dtype=pl.Float64).alias("amount"))
    return (
        frame.select(["symbol", "date", "close", "amount"])
        .with_columns(pl.col("date").cast(pl.Date, strict=False))
        .filter(
            pl.col("symbol").is_in(symbols)
            & (pl.col("date") >= start)
            & (pl.col("date") <= end)
            & pl.col("close").is_not_null()
            & (pl.col("close") > 0)
        )
        .unique(subset=["symbol", "date"], keep="last")
        .sort(["symbol", "date"])
    )


def _symbol_metrics(frame: pl.DataFrame, end: date) -> dict[str, dict[str, Any]]:
    if frame.is_empty():
        return {}
    result: dict[str, dict[str, Any]] = {}
    for (symbol,), group in frame.group_by(["symbol"], maintain_order=True):
        group = group.sort("date")
        closes = [float(value) for value in group["close"].to_list() if value is not None]
        if not closes:
            continue
        latest_row = group.tail(1).row(0, named=True)
        item: dict[str, Any] = {
            "latest_close": closes[-1],
            "latest_date": latest_row["date"],
            "amount": _finite(latest_row.get("amount")),
            "series": {
                row["date"]: float(row["close"])
                for row in group.iter_rows(named=True)
                if row.get("close") is not None
            },
        }
        for key, days in WINDOWS:
            item[key] = (
                round(closes[-1] / closes[-(days + 1)] - 1, 8)
                if len(closes) > days
                else None
            )
        result[str(symbol)] = item
    return result


def _aggregate(symbols: list[str], metrics: dict[str, dict[str, Any]], key: str) -> dict[str, Any]:
    values = [
        metrics[symbol][key]
        for symbol in symbols
        if symbol in metrics and metrics[symbol].get(key) is not None
    ]
    up = sum(1 for value in values if value > 0)
    down = sum(1 for value in values if value < 0)
    flat = len(values) - up - down
    return {
        "return_pct": round(fmean(values), 8) if values else None,
        "up_count": up,
        "down_count": down,
        "flat_count": flat,
        "priced_count": len(values),
        "stock_count": len(symbols),
        "amount": round(sum(
            metrics[symbol].get("amount") or 0.0
            for symbol in symbols
            if symbol in metrics
        ), 2),
    }


def _difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return round(left - right, 8)


def _equal_weight_series(
    symbols: list[str],
    metrics: dict[str, dict[str, Any]],
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    series_by_symbol: dict[str, dict[date, float]] = {}
    for symbol in symbols:
        item = metrics.get(symbol)
        if not item:
            continue
        points = {
            day: close
            for day, close in item["series"].items()
            if start <= day <= end
        }
        if not points:
            continue
        baseline = points[sorted(points)[0]]
        if baseline <= 0:
            continue
        series_by_symbol[symbol] = {
            day: close / baseline - 1 for day, close in points.items()
        }
    if not series_by_symbol:
        return []
    dates = sorted({day for points in series_by_symbol.values() for day in points})
    result = []
    for day in dates:
        values = [
            points[day]
            for points in series_by_symbol.values()
            if day in points
        ]
        if values:
            result.append({
                "date": day.isoformat(),
                "return_pct": round(fmean(values), 8),
                "sample_count": len(values),
            })
    return result


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None
