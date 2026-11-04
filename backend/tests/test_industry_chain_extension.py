from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.custom.industry_chain.defaults import build_default_graph
from app.custom.industry_chain.migration import (
    expand_market_chains,
    expand_new_energy_chain,
    refine_ai_server_chain,
    reorganize_industry_chains,
)
from app.custom.industry_chain.models import (
    IndustryChainGraph,
    IndustryChainStockLink,
    validate_graph,
)
from app.custom.industry_chain.routes import build_router
from app.custom.industry_chain.service import analyze_graph
from app.custom.industry_chain.store import ConflictError, load_graph, save_graph
from app.extensions.contracts import BACKEND_EXTENSION_API_VERSION
from app.extensions.registry import BackendExtensionRegistrar


class FakeMarketData:
    def __init__(self, frame: pl.DataFrame, latest: date) -> None:
        self.frame = frame
        self.latest = latest
        self.calls: list[tuple] = []

    def latest_daily_date(self) -> date:
        return self.latest

    def get_daily_batch(self, symbols, start, end, columns=None):
        self.calls.append((symbols, start, end, columns))
        return self.frame.filter(
            pl.col("symbol").is_in(symbols)
            & (pl.col("date") >= start)
            & (pl.col("date") <= end)
        )


def _graph() -> dict:
    return {
        "version": 1,
        "updated_at": "",
        "categories": [{"id": "cat", "name": "测试分类", "order": 10}],
        "chains": [{"id": "chain", "category_id": "cat", "name": "测试链", "order": 10}],
        "nodes": [
            {"id": "root", "chain_id": "chain", "parent_id": None, "name": "根节点"},
            {"id": "mid", "chain_id": "chain", "parent_id": "root", "name": "中间节点"},
            {"id": "leaf-a", "chain_id": "chain", "parent_id": "mid", "name": "叶子 A"},
            {"id": "leaf-b", "chain_id": "chain", "parent_id": "mid", "name": "叶子 B"},
        ],
        "stock_links": [
            _link("l1", "leaf-a", "000001.SZ", "提供测试产品与服务"),
            _link("l2", "leaf-b", "000001.SZ", "布局另一测试细分环节"),
            _link("l3", "leaf-b", "000002.SZ", "提供测试配套产品"),
        ],
    }


def _link(
    link_id: str,
    node_id: str,
    symbol: str,
    reason: str,
) -> dict:
    return {
        "id": link_id,
        "node_id": node_id,
        "symbol": symbol,
        "reason_short": reason,
        "note": "",
        "source_url": "",
        "evidence_status": "pending",
        "sort_order": 10,
    }


def _daily_frame() -> tuple[pl.DataFrame, date]:
    start = date(2026, 10, 1)
    rows = []
    for index in range(30):
        day = start + timedelta(days=index)
        rows.append({"symbol": "000001.SZ", "date": day, "close": 100.0 + index, "amount": 1000.0 + index})
        rows.append({"symbol": "000002.SZ", "date": day, "close": 200.0 - index, "amount": 2000.0 + index})
    return pl.DataFrame(rows), start + timedelta(days=29)


def test_analyze_recurses_dedupes_and_aggregates() -> None:
    frame, latest = _daily_frame()
    market = FakeMarketData(frame, latest)

    result = analyze_graph(
        _graph(),
        chain_id="chain",
        node_id="mid",
        start=date(2026, 10, 1),
        end=latest,
        market_data=market,
        name_for=lambda symbol: {"000001.SZ": "甲公司", "000002.SZ": "乙公司"}[symbol],
    )

    assert result["scope_node_ids"] == ["leaf-a", "leaf-b", "mid"]
    assert result["link_count"] == 3
    assert result["stock_count"] == 2
    assert result["coverage"]["priced_count"] == 2
    assert result["windows"]["d1"]["return_pct"] == pytest.approx(
        ((1 / 128) + (-1 / 172)) / 2,
        abs=1e-8,
    )
    assert result["windows"]["d1"]["up_count"] == 1
    assert result["windows"]["d1"]["down_count"] == 1
    assert [stock["symbol"] for stock in result["stocks"]] == ["000001.SZ", "000002.SZ"]
    assert len(result["stocks"][0]["links"]) == 2
    assert result["stocks"][0]["name"] == "甲公司"
    assert market.calls[0][3] == ["symbol", "date", "close", "amount"]


def test_leaf_scope_and_parent_relative_are_separate() -> None:
    frame, latest = _daily_frame()
    result = analyze_graph(
        _graph(),
        chain_id="chain",
        node_id="leaf-a",
        start=None,
        end=latest,
        market_data=FakeMarketData(frame, latest),
        name_for=lambda symbol: symbol,
    )

    assert result["stock_count"] == 1
    assert result["relative"]["parent"]["node_id"] == "mid"
    assert result["relative"]["parent"]["windows"]["d1"] > 0
    assert result["relative"]["chain"]["windows"]["d1"] > 0
    assert result["node"]["path"] == [
        {"id": "root", "name": "根节点"},
        {"id": "mid", "name": "中间节点"},
        {"id": "leaf-a", "name": "叶子 A"},
    ]


def test_graph_validation_rejects_bad_reason_dangling_and_duplicates() -> None:
    bad_reason = _graph()
    bad_reason["stock_links"][0]["reason_short"] = "太短"
    with pytest.raises(ValueError):
        validate_graph(IndustryChainGraph.model_validate(bad_reason))

    dangling = _graph()
    dangling["stock_links"][0]["node_id"] = "missing"
    with pytest.raises(ValueError, match="不存在"):
        validate_graph(IndustryChainGraph.model_validate(dangling))

    duplicate = _graph()
    duplicate["stock_links"].append(_link("l4", "leaf-a", "000001.SZ", "重复关联同一节点股票"))
    with pytest.raises(ValueError, match="重复关联"):
        validate_graph(IndustryChainGraph.model_validate(duplicate))


def test_store_seeds_default_and_rejects_stale_writes(tmp_path: Path) -> None:
    seeded = load_graph(tmp_path)
    assert seeded["chains"][0]["name"] == "AI 产业链"
    assert (tmp_path / "user_data" / "industry_chain" / "graph.json").is_file()

    graph = IndustryChainGraph.model_validate(seeded)
    first = save_graph(tmp_path, graph, expected_updated_at=seeded["updated_at"])
    assert first["updated_at"]
    with pytest.raises(ConflictError):
        save_graph(tmp_path, graph, expected_updated_at=seeded["updated_at"])


def test_default_graph_includes_ai_industry_chain() -> None:
    graph = build_default_graph()
    validate_graph(graph)

    chain = next(item for item in graph.chains if item.id == "ai-industry")
    assert chain.category_id == "hard-tech"
    ai_nodes = [node for node in graph.nodes if node.chain_id == chain.id]
    ai_node_ids = {node.id for node in ai_nodes}
    ai_links = [link for link in graph.stock_links if link.node_id in ai_node_ids]

    assert {node.name for node in ai_nodes if node.parent_id is None} == {
        "基础层",
        "模型与平台层",
        "终端层",
        "应用层",
    }
    parents = {node.id: node.parent_id for node in ai_nodes}
    assert parents["ai-chip"] == "ai-hardware"
    assert parents["ai-server"] == "ai-hardware"
    assert parents["ai-memory"] == "ai-hardware"
    assert parents["ai-optical"] == "ai-interconnect"
    assert parents["ai-pcb"] == "ai-interconnect"
    assert parents["ai-mlcc"] == "ai-components"
    assert parents["ai-data"] == "ai-compute"
    ai_node_by_id = {node.id: node for node in ai_nodes}
    assert ai_node_by_id["ai-pcb"].name == "AI 服务器高速 PCB"
    assert "PCB 产业链" in ai_node_by_id["ai-pcb"].description
    assert "光通信产业链" in ai_node_by_id["ai-optical"].description
    assert "MLCC 产业链" in ai_node_by_id["ai-mlcc"].description
    assert "国产半导体产业链" in ai_node_by_id["ai-chip"].description
    assert not any(node.id.startswith(("oc-", "mlcc-")) for node in ai_nodes)
    assert any(link.symbol == "300408.SZ" for link in ai_links)


def test_default_graph_refines_ai_server_subsegments() -> None:
    graph = validate_graph(build_default_graph())
    nodes = {node.id: node for node in graph.nodes}

    assert nodes["ai-server"].kind == "segment"
    assert {node.name for node in graph.nodes if node.parent_id == "ai-server"} == {
        "品牌服务器",
        "ODM/代工",
        "服务器主板/加速卡",
        "连接器与结构件",
        "服务器测试",
        "其他/待核验",
    }
    assert nodes["ai-switch"].parent_id == "ai-network"
    assert nodes["ai-mlcc"].kind == "segment"
    assert nodes["ai-mlcc-product"].parent_id == "ai-mlcc"
    assert nodes["ai-mlcc-material"].parent_id == "ai-mlcc"
    assert nodes["ai-passive"].parent_id == "ai-components"
    assert nodes["ai-passive-material"].parent_id == "ai-components"

    by_symbol = {
        link.symbol: link for link in graph.stock_links if link.node_id.startswith("ai-server-")
    }
    assert by_symbol["000977.SZ"].node_id == "ai-server-oem"
    assert by_symbol["603019.SH"].node_id == "ai-server-oem"
    assert by_symbol["601138.SH"].node_id == "ai-server-odm"
    assert not any(link.node_id == "ai-server" for link in graph.stock_links)
    mlcc = next(link for link in graph.stock_links if link.symbol == "300408.SZ" and link.node_id.startswith("ai-mlcc"))
    assert mlcc.node_id == "ai-mlcc-product"


def test_refine_ai_server_moves_links_merges_duplicates_and_is_idempotent() -> None:
    original = build_default_graph()
    original.stock_links.extend([
        IndustryChainStockLink(
            id="legacy-server-pcb",
            node_id="ai-server",
            symbol="002463.SZ",
            reason_short="涨停题材：AI服务器",
            note="PCB 历史题材记录",
            evidence_status="pending",
            basis="theme_clue",
            sort_order=10,
        ),
        IndustryChainStockLink(
            id="legacy-server-new-pcb",
            node_id="ai-server",
            symbol="002815.SZ",
            reason_short="涨停题材：AI服务器",
            note="PCB 新分类记录",
            evidence_status="pending",
            basis="theme_clue",
            sort_order=20,
        ),
        IndustryChainStockLink(
            id="legacy-server-test",
            node_id="ai-server",
            symbol="002975.SZ",
            reason_short="涨停题材：AI服务器",
            note="测试设备待核验",
            evidence_status="pending",
            basis="theme_clue",
            sort_order=30,
        ),
    ])
    snapshot = original.model_copy(deep=True)

    refined = refine_ai_server_chain(original)

    assert original == snapshot
    assert refine_ai_server_chain(refined) == refined
    assert not any(link.node_id == "ai-server" for link in refined.stock_links)
    by_symbol = {link.symbol: link for link in refined.stock_links}
    assert by_symbol["002463.SZ"].node_id == "ai-pcb"
    assert "PCB 历史题材记录" in by_symbol["002463.SZ"].note
    assert by_symbol["002815.SZ"].node_id == "ai-pcb"
    assert by_symbol["002975.SZ"].node_id == "ai-server-test"


def test_default_graph_includes_new_energy_industry_chain() -> None:
    graph = validate_graph(build_default_graph())

    chain = next(item for item in graph.chains if item.id == "power-battery")
    assert chain.name == "新能源产业链"
    energy_nodes = [node for node in graph.nodes if node.chain_id == chain.id]
    assert {node.name for node in energy_nodes if node.parent_id is None} == {
        "光伏",
        "风电",
        "电池与材料",
        "储能系统",
        "氢能",
        "电网与充换电",
    }
    parents = {node.id: node.parent_id for node in energy_nodes}
    assert parents["bat-material"] == "ne-battery"
    assert parents["bat-cell"] == "ne-battery"
    assert parents["bat-demand"] == "ne-battery"
    assert parents["ne-pv-inverter"] == "ne-pv-system"
    assert parents["ne-wind-cable"] == "ne-wind-offshore-engineering"
    assert parents["ne-storage-pcs"] == "ne-storage-equipment"
    assert parents["ne-hydrogen-electrolyzer"] == "ne-hydrogen-production"
    assert parents["ne-grid-uhv"] == "ne-grid-transmission"


def test_default_graph_includes_commercial_space_chain() -> None:
    graph = validate_graph(build_default_graph())

    chain = next(item for item in graph.chains if item.id == "commercial-space")
    assert chain.category_id == "aerospace"
    nodes = [node for node in graph.nodes if node.chain_id == chain.id]
    assert {node.name for node in nodes if node.parent_id is None} == {
        "材料与元器件",
        "火箭与卫星制造",
        "地面系统",
        "发射与空间应用",
    }
    parents = {node.id: node.parent_id for node in nodes}
    assert parents["cs-rocket-engine"] == "cs-rocket"
    assert parents["cs-attitude"] == "cs-sat-platform"
    assert parents["cs-remote-data"] == "cs-remote"
    node_ids = {node.id for node in nodes}
    links = [link for link in graph.stock_links if link.node_id in node_ids]
    assert any(link.node_id == "cs-attitude" for link in links)
    assert any(link.node_id == "cs-rf" for link in links)


def test_default_graph_includes_robotics_chain() -> None:
    graph = validate_graph(build_default_graph())

    chain = next(item for item in graph.chains if item.id == "robotics")
    assert chain.category_id == "advanced-manufacturing"
    nodes = [node for node in graph.nodes if node.chain_id == chain.id]
    assert {node.name for node in nodes if node.parent_id is None} == {
        "核心零部件",
        "软件与智能",
        "整机制造",
        "系统集成与应用",
        "上游材料与装备",
    }
    parents = {node.id: node.parent_id for node in nodes}
    assert parents["rb-harmonic"] == "rb-reducer"
    assert parents["rb-roller-screw"] == "rb-screw"
    assert parents["rb-humanoid"] == "rb-body"
    assert parents["rb-embodied"] == "rb-software"
    assert any(link.node_id == "rb-harmonic" for link in graph.stock_links)


def test_default_graph_includes_new_energy_vehicle_chain() -> None:
    graph = validate_graph(build_default_graph())

    chain = next(item for item in graph.chains if item.id == "new-energy-vehicle")
    assert chain.category_id == "automotive"
    nodes = [node for node in graph.nodes if node.chain_id == chain.id]
    assert {node.name for node in nodes if node.parent_id is None} == {
        "上游资源与材料",
        "电池系统",
        "电驱系统",
        "高压与补能",
        "热管理",
        "底盘与车身",
        "智能驾驶",
        "智能座舱",
        "整车",
        "后市场与补能",
        "支撑",
    }
    parents = {node.id: node.parent_id for node in nodes}
    assert parents["nev-casting"] == "nev-chassis"
    assert parents["nev-ad-compute"] == "nev-ad"
    assert parents["nev-bev"] == "nev-passenger"
    assert any(link.node_id == "nev-casting" for link in graph.stock_links)


def test_battery_chain_is_refined_under_existing_new_energy_chain() -> None:
    graph = validate_graph(build_default_graph())
    nodes = {node.id: node for node in graph.nodes}

    assert nodes["ne-battery"].parent_id is None
    assert nodes["bat-resource"].parent_id == "ne-battery"
    assert nodes["bat-material"].parent_id == "ne-battery"
    assert nodes["bat-cathode"].kind == "segment"
    assert nodes["bat-cathode-lfp"].parent_id == "bat-cathode"
    assert nodes["bat-anode-silicon"].parent_id == "bat-anode"
    assert nodes["bat-separator-wet"].parent_id == "bat-separator"
    assert nodes["bat-electrolyte-lipf6"].parent_id == "bat-electrolyte"
    assert nodes["bat-equipment"].parent_id == "ne-battery"
    assert nodes["bat-recycle"].parent_id == "ne-battery"
    assert nodes["bat-tech"].parent_id == "ne-battery"

    pairs = {(link.node_id, link.symbol) for link in graph.stock_links}
    assert ("bat-cathode-lfp", "301358.SZ") in pairs
    assert ("bat-anode-silicon", "603659.SH") in pairs
    assert ("bat-separator-wet", "002812.SZ") in pairs
    assert ("bat-electrolyte-lipf6", "002709.SZ") in pairs
    assert ("bat-composite-foil", "600110.SH") in pairs


def test_new_energy_migration_preserves_links_and_is_idempotent() -> None:
    legacy = build_default_graph().model_copy(deep=True)
    legacy_nodes = [node for node in legacy.nodes if not node.id.startswith("ne-")]
    legacy_node_ids = {node.id for node in legacy_nodes}
    for node in legacy_nodes:
        if node.parent_id == "ne-battery":
            node.parent_id = None
    legacy.nodes = legacy_nodes
    legacy.stock_links = [
        link for link in legacy.stock_links if link.node_id in legacy_node_ids
    ]
    next(chain for chain in legacy.chains if chain.id == "power-battery").name = "动力电池"
    user_link = IndustryChainStockLink(
        id="user-energy-evidence",
        node_id="bat-power",
        symbol="000001.SZ",
        reason_short="用户保留的动力电池记录",
        note="用户核验备注",
        evidence_status="verified",
        sort_order=999,
    )
    legacy.stock_links.append(user_link)
    snapshot = legacy.model_copy(deep=True)

    migrated = expand_new_energy_chain(legacy)

    assert legacy == snapshot
    assert expand_new_energy_chain(migrated) == migrated
    assert next(chain for chain in migrated.chains if chain.id == "power-battery").name == "新能源产业链"
    nodes = {node.id: node for node in migrated.nodes}
    assert nodes["bat-material"].parent_id == "ne-battery"
    assert nodes["ne-pv-inverter"].parent_id == "ne-pv-system"
    assert next(link for link in migrated.stock_links if link.id == user_link.id) == user_link
    assert all(
        idd in {link.id for link in migrated.stock_links}
        for idd in {link.id for link in snapshot.stock_links}
    )


def test_market_chain_migration_adds_chains_and_refines_battery() -> None:
    legacy = build_default_graph().model_copy(deep=True)
    legacy.categories = [
        item for item in legacy.categories
        if item.id not in {"aerospace", "advanced-manufacturing", "automotive"}
    ]
    legacy.chains = [
        item for item in legacy.chains
        if item.id not in {"commercial-space", "robotics", "new-energy-vehicle"}
    ]
    old_battery_ids = {
        "bat-material", "bat-cathode", "bat-anode", "bat-separator",
        "bat-electrolyte", "bat-cell", "bat-power", "bat-storage",
        "bat-demand", "bat-ev", "bat-grid", "bat-lithium", "bat-solid",
        "bat-solid-material",
    }
    removed_ids = {
        node.id for node in legacy.nodes
        if node.chain_id in {"commercial-space", "robotics", "new-energy-vehicle"}
        or (node.id.startswith("bat-") and node.id not in old_battery_ids)
    }
    legacy.nodes = [node for node in legacy.nodes if node.id not in removed_ids]
    legacy.stock_links = [
        link for link in legacy.stock_links if link.node_id not in removed_ids
    ]
    by_id = {node.id: node for node in legacy.nodes}
    by_id["bat-material"].name = "上游材料"
    by_id["bat-cell"].name = "电芯与 PACK"
    by_id["bat-cathode"].kind = "product"
    by_id["bat-anode"].kind = "product"
    by_id["bat-separator"].kind = "product"
    by_id["bat-electrolyte"].kind = "product"
    by_id["bat-lithium"].parent_id = "bat-material"
    by_id["bat-solid"].parent_id = "bat-cell"
    by_id["bat-solid-material"].parent_id = "bat-material"
    by_id["bat-power"].order = 10
    by_id["bat-storage"].order = 20
    user_link = IndustryChainStockLink(
        id="user-battery-record",
        node_id="bat-power",
        symbol="000001.SZ",
        reason_short="用户保留的动力电池记录",
        note="用户核验备注",
        evidence_status="verified",
        sort_order=999,
    )
    legacy.stock_links.append(user_link)
    snapshot = legacy.model_copy(deep=True)

    migrated = expand_market_chains(legacy)

    assert legacy == snapshot
    assert expand_market_chains(migrated) == migrated
    assert {"commercial-space", "robotics", "new-energy-vehicle"} <= {
        chain.id for chain in migrated.chains
    }
    nodes = {node.id: node for node in migrated.nodes}
    assert nodes["bat-resource"].parent_id == "ne-battery"
    assert nodes["bat-lithium"].parent_id == "bat-resource"
    assert nodes["bat-solid"].parent_id == "bat-tech"
    assert nodes["bat-solid-material"].parent_id == "bat-tech"
    assert nodes["bat-cathode"].kind == "segment"
    assert nodes["bat-material"].name == "四大主材"
    assert nodes["bat-cell"].name == "电芯与系统"
    assert next(link for link in migrated.stock_links if link.id == user_link.id) == user_link
    assert any(link.node_id == "cs-attitude" for link in migrated.stock_links)


def test_independent_chains_share_stocks_with_distinct_reasons() -> None:
    graph = validate_graph(build_default_graph())
    assert {chain.id for chain in graph.chains} == {
        "ai-industry", "optical-communication", "mlcc", "semiconductor", "pcb", "power-battery",
        "commercial-space", "robotics", "new-energy-vehicle",
    }
    assert next(chain for chain in graph.chains if chain.id == "semiconductor").name == "国产半导体产业链"
    assert next(chain for chain in graph.chains if chain.id == "pcb").category_id == "hard-tech"
    by_node = {node.id: node for node in graph.nodes}
    assert by_node["oc-chip"].chain_id == "optical-communication"
    assert by_node["oc-chip"].parent_id is None
    assert by_node["mlcc-material"].chain_id == "mlcc"
    assert by_node["mlcc-material"].parent_id is None
    assert {node.name for node in graph.nodes if node.chain_id == "semiconductor" and not node.parent_id} == {
        "设计工具与 IP", "芯片设计", "半导体材料", "半导体设备", "晶圆制造", "封装测试",
    }
    assert {node.name for node in graph.nodes if node.chain_id == "pcb" and not node.parent_id} == {
        "上游材料", "专用设备与工具", "PCB 制造", "下游应用",
    }
    for symbol in ("300308.SZ", "300408.SZ", "688041.SH", "688521.SH", "600584.SH"):
        links = [link for link in graph.stock_links if link.symbol == symbol]
        assert len({by_node[link.node_id].chain_id for link in links}) >= 2
        assert len({link.reason_short for link in links}) >= 2


def test_reorganization_preserves_edits_and_is_idempotent() -> None:
    original = build_default_graph().model_dump()
    original["categories"].extend([
        {"id": "ai", "name": "人工智能", "order": 10},
        {"id": "semiconductor", "name": "半导体", "order": 20},
        {"id": "electronics", "name": "电子与通信", "order": 30},
    ])
    original["categories"] = [
        category for category in original["categories"]
        if category["id"] != "hard-tech"
    ]
    original["chains"] = [
        chain for chain in original["chains"]
        if chain["id"] not in {"optical-communication", "mlcc", "semiconductor", "pcb"}
    ]
    for chain in original["chains"]:
        if chain["id"] == "ai-industry":
            chain["category_id"] = "ai"
        elif chain["id"] == "power-battery":
            chain["category_id"] = "new-energy"
    original["nodes"] = [
        node for node in original["nodes"]
        if node["chain_id"] not in {"semiconductor", "pcb"}
    ]
    node_ids = {node["id"] for node in original["nodes"]}
    original["stock_links"] = [link for link in original["stock_links"] if link["node_id"] in node_ids]
    original["stock_links"] = [link for link in original["stock_links"] if link["id"] != "l-tfc-passive"]
    for node in original["nodes"]:
        if node["chain_id"] in {"optical-communication", "mlcc"}:
            node["chain_id"] = "ai-industry"
            if node["parent_id"] is None:
                node["parent_id"] = "ai-optical" if node["id"].startswith("oc-") else "ai-mlcc"
    original["nodes"].append({
        "id": "user-optical", "chain_id": "ai-industry", "parent_id": "oc-module",
        "name": "用户自定义产品", "description": "保留用户备注", "kind": "product", "order": 90,
    })
    user_link = next(link for link in original["stock_links"] if link["id"] == "l-wus-pcb")
    user_link["reason_short"] = "用户编辑的高速PCB关联"
    user_link["note"] = "用户核验记录"
    for node in original["nodes"]:
        if node["chain_id"] == "ai-industry" and node["id"] in {
            "ai-chip", "ai-memory", "ai-package", "ai-optical", "ai-pcb", "ai-mlcc",
        }:
            node["description"] = ""
    snapshot = IndustryChainGraph.model_validate(original)
    migrated = reorganize_industry_chains(snapshot)
    assert snapshot.model_dump() == IndustryChainGraph.model_validate(original).model_dump()
    assert reorganize_industry_chains(migrated) == migrated
    assert not any(link.id == "l-tfc-passive" for link in migrated.stock_links)
    for link in snapshot.stock_links:
        assert next(item for item in migrated.stock_links if item.id == link.id) == link
    custom = next(node for node in migrated.nodes if node.id == "user-optical")
    assert custom.chain_id == "optical-communication"
    assert custom.description == "保留用户备注"
    assert {chain.id for chain in migrated.chains} >= {
        "ai-industry", "optical-communication", "mlcc", "semiconductor", "pcb", "power-battery",
    }
    category_ids = {category.id for category in migrated.categories}
    assert {"hard-tech", "new-energy", "aerospace", "advanced-manufacturing", "automotive"} <= category_ids
    assert not ({"ai", "semiconductor", "electronics"} & category_ids)
    assert next(node for node in migrated.nodes if node.id == "ai-pcb").description.startswith("完整产业链见")
    pcb_copy = next(
        link for link in migrated.stock_links
        if link.node_id == "pcb-high-speed" and link.symbol == "002463.SZ"
    )
    assert pcb_copy.note == "用户核验记录"
    assert pcb_copy.reason_short == user_link["reason_short"]
    assert [node for node in migrated.nodes if node.chain_id == "power-battery"] == [
        node for node in snapshot.nodes if node.chain_id == "power-battery"
    ]


def test_extension_setup_registers_router() -> None:
    from app.custom import industry_chain

    registrar = BackendExtensionRegistrar(
        industry_chain.EXTENSION_ID,
        api_version=BACKEND_EXTENSION_API_VERSION,
    )
    industry_chain.setup(registrar)

    assert industry_chain.EXTENSION_ID == "official.industry-chain"
    assert registrar.routers[0].prefix == "/api/custom/industry-chain"


class FakeAnalysis:
    def names(self, symbols: list[str]) -> dict[str, str]:
        return {symbol: f"名称-{symbol}" for symbol in symbols}


def _client(tmp_path: Path) -> TestClient:
    frame, latest = _daily_frame()
    app = FastAPI()
    app.include_router(build_router())
    app.state.extension_runtime = SimpleNamespace(
        data_dir=tmp_path,
        market_data=FakeMarketData(frame, latest),
        analysis=FakeAnalysis(),
    )
    return TestClient(app)


def test_api_round_trip_and_analysis(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/custom/industry-chain/graph")
    assert response.status_code == 200
    graph = response.json()
    assert any(chain["id"] == "mlcc" for chain in graph["chains"])
    assert {"commercial-space", "robotics", "new-energy-vehicle"} <= {
        chain["id"] for chain in graph["chains"]
    }
    assert graph["stock_names"]["300308.SZ"] == "名称-300308.SZ"

    graph["stock_links"][0]["reason_short"] = "更新后的高速光模块逻辑"
    response = client.put(
        "/api/custom/industry-chain/graph",
        json={"graph": graph, "expected_updated_at": graph["updated_at"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["updated_at"]

    response = client.get(
        "/api/custom/industry-chain/analysis",
        params={"chain_id": "optical-communication", "node_id": "oc-module"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["node"]["name"] == "光模块与光引擎"
    assert payload["stock_count"] == 3
    assert payload["method"]["membership"] == "current_graph"
    assert all(stock["name"].startswith("名称-") for stock in payload["stocks"])


def test_api_rejects_bad_reason_and_missing_chain(tmp_path: Path) -> None:
    client = _client(tmp_path)
    graph = client.get("/api/custom/industry-chain/graph").json()
    graph["stock_links"][0]["reason_short"] = "短"
    response = client.put(
        "/api/custom/industry-chain/graph",
        json={"graph": graph, "expected_updated_at": graph["updated_at"]},
    )
    assert response.status_code == 422

    response = client.get(
        "/api/custom/industry-chain/analysis",
        params={"chain_id": "missing"},
    )
    assert response.status_code == 400
