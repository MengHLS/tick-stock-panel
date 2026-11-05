"""Resolve industry-chain membership without copying it into theme storage."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.custom.industry_chain.store import load_graph

from .store import MAX_SYMBOLS_PER_THEME


def resolve_theme(data_dir: Path, theme: dict[str, Any], *, strict: bool = False) -> dict[str, Any]:
    source = theme.get("industry_source") or {}
    manual = list(theme["symbols"])
    inherited: list[str] = []
    memberships: dict[str, list[str]] = {}
    source_name = ""
    source_error = None
    if source:
        try:
            graph = load_graph(data_dir)
            chain = next(
                (item for item in graph["chains"] if item["id"] == source["chain_id"]), None,
            )
            if chain is None:
                raise ValueError("关联的产业链已不存在，请重新选择股票池来源")
            nodes = {
                item["id"]: item for item in graph["nodes"]
                if item["chain_id"] == chain["id"]
            }
            selected = set(source.get("node_ids") or [])
            if not selected.issubset(nodes):
                raise ValueError("关联的产业链环节已不存在，请重新选择股票池来源")
            scope = set(selected) if selected else set(nodes)
            while True:
                children = {
                    node["id"] for node in nodes.values() if node.get("parent_id") in scope
                }
                if children.issubset(scope):
                    break
                scope.update(children)
            for link in graph["stock_links"]:
                if link["node_id"] in scope:
                    memberships.setdefault(link["symbol"], []).append(nodes[link["node_id"]]["name"])
            inherited = sorted(memberships)
            source_name = chain["name"] + (
                " / " + "、".join(nodes[node_id]["name"] for node_id in sorted(selected))
                if selected else " / 整条产业链"
            )
        except (ValueError, KeyError, TypeError) as exc:
            source_error = str(exc)
            if strict:
                raise ValueError(source_error) from exc
    excluded = set(theme.get("excluded_symbols") or [])
    effective = list(dict.fromkeys(symbol for symbol in [*inherited, *manual] if symbol not in excluded))
    if len(effective) > MAX_SYMBOLS_PER_THEME:
        source_error = f"关联后股票池超过 {MAX_SYMBOLS_PER_THEME} 只，请缩小环节范围"
        if strict:
            raise ValueError(source_error)
        effective = []
    return {
        **theme,
        "industry_source": source or None,
        "symbols": effective,
        "manual_symbols": manual,
        "inherited_symbols": inherited,
        "stock_segments": {symbol: list(dict.fromkeys(names)) for symbol, names in memberships.items()},
        "source_name": source_name,
        "source_error": source_error,
    }
