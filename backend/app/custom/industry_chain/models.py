"""Industry-chain graph contracts and structural validation."""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SYMBOL_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")

# Bump when seeded structure or descriptions need a one-time upgrade for
# existing user graph.json files. User edits made after the upgrade are kept.
CURRENT_GRAPH_CONTENT_VERSION = 2


class IndustryChainCategory(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=40)
    order: int = 100

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError(f"非法分类 ID: {value}")
        return value


class IndustryChain(BaseModel):
    id: str
    category_id: str
    name: str = Field(min_length=1, max_length=40)
    order: int = 100

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError(f"非法产业链 ID: {value}")
        return value


class IndustryChainNode(BaseModel):
    id: str
    chain_id: str
    parent_id: str | None = None
    name: str = Field(min_length=1, max_length=40)
    kind: Literal["segment", "product", "application"] = "segment"
    description: str = Field(default="", max_length=500)
    order: int = 100

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError(f"非法节点 ID: {value}")
        return value


class IndustryChainStockLink(BaseModel):
    id: str
    node_id: str
    symbol: str
    reason_short: str = Field(min_length=5, max_length=20)
    note: str = Field(default="", max_length=2000)
    source_url: str = Field(default="", max_length=500)
    evidence_status: Literal["verified", "pending"] = "pending"
    basis: Literal["main_business", "supply", "theme_clue"] = "main_business"
    sort_order: int = 100

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError(f"非法关联 ID: {value}")
        return value

    @field_validator("symbol")
    @classmethod
    def _valid_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not _SYMBOL_RE.match(normalized):
            raise ValueError(f"非法股票代码: {value}")
        return normalized

    @field_validator("reason_short")
    @classmethod
    def _valid_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not 5 <= len(normalized) <= 20:
            raise ValueError("关联理由需为 5～20 个字符")
        return normalized

    @field_validator("source_url")
    @classmethod
    def _valid_source_url(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and not normalized.startswith(("http://", "https://")):
            raise ValueError("来源链接只允许 http(s) 地址")
        return normalized


class IndustryChainGraph(BaseModel):
    version: Literal[1] = 1
    content_version: int = Field(default=0, ge=0)
    updated_at: str = ""
    categories: list[IndustryChainCategory] = Field(default_factory=list)
    chains: list[IndustryChain] = Field(default_factory=list)
    nodes: list[IndustryChainNode] = Field(default_factory=list)
    stock_links: list[IndustryChainStockLink] = Field(default_factory=list)


class IndustryChainGraphSave(BaseModel):
    graph: IndustryChainGraph
    expected_updated_at: str | None = None


def validate_graph(graph: IndustryChainGraph) -> IndustryChainGraph:
    """Reject duplicate IDs, dangling references and parent cycles."""
    category_ids = _unique_ids(graph.categories, "分类")
    chain_ids = _unique_ids(graph.chains, "产业链")
    node_ids = _unique_ids(graph.nodes, "节点")
    _unique_ids(graph.stock_links, "股票关联")

    for chain in graph.chains:
        if chain.category_id not in category_ids:
            raise ValueError(f"产业链 {chain.id} 引用了不存在的分类 {chain.category_id}")

    node_chain: dict[str, str] = {}
    for node in graph.nodes:
        if node.chain_id not in chain_ids:
            raise ValueError(f"节点 {node.id} 引用了不存在的产业链 {node.chain_id}")
        if node.parent_id is not None:
            if node.parent_id not in node_ids:
                raise ValueError(f"节点 {node.id} 引用了不存在的父节点 {node.parent_id}")
            parent = next(item for item in graph.nodes if item.id == node.parent_id)
            if parent.chain_id != node.chain_id:
                raise ValueError(f"节点 {node.id} 与父节点不属于同一产业链")
        node_chain[node.id] = node.chain_id

    _assert_acyclic(graph.nodes)

    link_pairs: set[tuple[str, str]] = set()
    for link in graph.stock_links:
        if link.node_id not in node_ids:
            raise ValueError(f"股票关联 {link.id} 引用了不存在的节点 {link.node_id}")
        pair = (link.node_id, link.symbol)
        if pair in link_pairs:
            raise ValueError(f"节点 {link.node_id} 重复关联股票 {link.symbol}")
        link_pairs.add(pair)
    return graph


def _unique_ids(items: list[Any], label: str) -> set[str]:
    ids: set[str] = set()
    for item in items:
        item_id = str(item.id)
        if item_id in ids:
            raise ValueError(f"{label} ID 重复: {item_id}")
        ids.add(item_id)
    return ids


def _assert_acyclic(nodes: list[IndustryChainNode]) -> None:
    parents = {node.id: node.parent_id for node in nodes}
    for node_id in parents:
        seen: set[str] = set()
        current: str | None = node_id
        while current is not None:
            if current in seen:
                raise ValueError(f"节点父子关系存在环: {node_id}")
            seen.add(current)
            current = parents.get(current)
