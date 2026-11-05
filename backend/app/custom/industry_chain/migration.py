"""Explicit migration from the merged AI catalog to independent industry chains."""
from __future__ import annotations

import hashlib

from app.custom.industry_chain.defaults import build_default_graph
from app.custom.industry_chain.descriptions import NODE_DESCRIPTIONS
from app.custom.industry_chain.models import (
    CURRENT_GRAPH_CONTENT_VERSION,
    IndustryChainGraph,
    validate_graph,
)
from app.custom.industry_chain.pool_import import NODE_SPECS

AI_SERVER_LINK_TARGETS: dict[str, tuple[str, str]] = {
    "000977.SZ": ("ai-server-oem", "AI服务器与智算整机"),
    "603019.SH": ("ai-server-oem", "高性能计算与AI服务器"),
    "601138.SH": ("ai-server-odm", "AI服务器与云计算设备"),
    "000636.SZ": ("ai-mlcc-product", "服务器MLCC"),
    "002463.SZ": ("ai-pcb", "AI服务器高速PCB"),
    "002484.SZ": ("ai-passive", "服务器铝电解电容"),
    "002578.SZ": ("ai-cooling", "液冷服务器用铝型材"),
    "002591.SZ": ("ai-cloud", "AI算力租赁与云计算"),
    "002636.SZ": ("ai-pcb-support", "AI服务器覆铜板"),
    "002815.SZ": ("ai-pcb", "AI服务器PCB制造"),
    "002913.SZ": ("ai-pcb", "AI服务器HDI板"),
    "002937.SZ": ("ai-server-structure", "服务器连接器与结构件"),
    "002938.SZ": ("ai-pcb", "AI服务器PCB"),
    "002965.SZ": ("ai-cooling", "液冷服务器结构件"),
    "002975.SZ": ("ai-server-test", "AI服务器测试设备"),
    "002992.SZ": ("ai-pcb-support", "AI服务器HVLP铜箔"),
    "300464.SZ": ("ai-cooling", "液冷服务器液冷板"),
    "301626.SZ": ("ai-cooling", "服务器微通道液冷"),
    "600183.SH": ("ai-pcb-support", "AI服务器高速覆铜板"),
    "600601.SH": ("ai-pcb", "AI服务器PCB"),
    "600666.SH": ("ai-cloud", "算力租赁与云计算"),
    "600703.SH": ("ai-optical", "光芯片与化合物半导体"),
    "600745.SH": ("ai-power", "功率半导体配套"),
    "601231.SH": ("ai-server-board", "AI加速卡与SiP模组"),
    "603115.SH": ("ai-passive-material", "电容电极箔"),
    "603118.SH": ("ai-switch", "800G交换机与光模块"),
    "603186.SH": ("ai-pcb-support", "AI服务器高速覆铜板"),
    "603200.SH": ("ai-cooling", "液冷服务器水处理"),
    "603228.SH": ("ai-pcb", "AI服务器HDI板"),
    "603920.SH": ("ai-pcb", "AI服务器PCB"),
    "603956.SH": ("ai-cooling", "液冷服务器水处理"),
    "603989.SH": ("ai-passive", "铝电解电容"),
    "605058.SH": ("ai-pcb", "AI服务器HDI板"),
    "605358.SH": ("ai-server-other", "半导体硅片配套待核验"),
    "605376.SH": ("ai-mlcc-material", "MLCC镍粉"),
    "688600.SH": ("ai-cooling", "液冷服务器检测"),
}


def refine_ai_server_chain(graph: IndustryChainGraph) -> IndustryChainGraph:
    """Move broad AI-server theme links into concrete subsegments."""
    updated = validate_graph(graph).model_copy(deep=True)
    defaults = build_default_graph()
    default_nodes = {node.id: node for node in defaults.nodes if node.chain_id == "ai-industry"}

    existing_nodes = {node.id for node in updated.nodes}
    updated.nodes.extend(
        node.model_copy(deep=True)
        for node in defaults.nodes
        if node.chain_id == "ai-industry" and node.id not in existing_nodes
    )
    by_id = {node.id: node for node in updated.nodes}
    for node_id in ("ai-server", "ai-mlcc"):
        node = by_id.get(node_id)
        seed = default_nodes.get(node_id)
        if node is not None and seed is not None and node.kind != seed.kind:
            node.kind = seed.kind

    for link in updated.stock_links:
        if (
            link.id.startswith("pool-")
            or "[涨停题材合并" in link.note
            or (link.evidence_status == "pending" and not link.source_url)
        ):
            link.basis = "theme_clue"

    pairs = {
        (link.node_id, link.symbol): link
        for link in updated.stock_links
        if link.node_id != "ai-server"
    }
    next_order = {
        node_id: max(
            (link.sort_order for link in updated.stock_links if link.node_id == node_id),
            default=0,
        )
        for node_id in {target[0] for target in AI_SERVER_LINK_TARGETS.values()}
    }
    retained = []
    for link in updated.stock_links:
        if link.node_id != "ai-server":
            retained.append(link)
            continue
        target_id, target_reason = AI_SERVER_LINK_TARGETS.get(
            link.symbol,
            ("ai-server-other", "AI服务器主题待核验"),
        )
        existing = pairs.get((target_id, link.symbol))
        if existing is not None:
            if existing.reason_short.startswith("涨停题材："):
                existing.reason_short = target_reason
            if link.note and link.note not in existing.note:
                existing.note = f"{existing.note}\n\n{link.note}".strip()[:2000]
            continue
        next_order[target_id] = next_order.get(target_id, 0) + 10
        link.node_id = target_id
        link.sort_order = next_order[target_id]
        if link.reason_short.startswith("涨停题材："):
            link.reason_short = target_reason
        link.basis = "main_business" if link.evidence_status == "verified" else "theme_clue"
        pairs[(target_id, link.symbol)] = link
        retained.append(link)
    updated.stock_links = retained
    return validate_graph(updated)


def expand_new_energy_chain(graph: IndustryChainGraph) -> IndustryChainGraph:
    """Expand the legacy power-battery chain without replacing user edits."""
    updated = validate_graph(graph).model_copy(deep=True)
    defaults = build_default_graph()

    category = next(item for item in defaults.categories if item.id == "new-energy")
    if not any(item.id == category.id for item in updated.categories):
        updated.categories.append(category.model_copy(deep=True))

    seed_chain = next(item for item in defaults.chains if item.id == "power-battery")
    chain = next((item for item in updated.chains if item.id == seed_chain.id), None)
    if chain is None:
        updated.chains.append(seed_chain.model_copy(deep=True))
    elif chain.name in {"动力电池", "电池与材料"}:
        chain.name = seed_chain.name

    existing_nodes = {node.id for node in updated.nodes}
    energy_nodes = [node for node in defaults.nodes if node.chain_id == seed_chain.id]
    updated.nodes.extend(
        node.model_copy(deep=True) for node in energy_nodes if node.id not in existing_nodes
    )

    by_id = {node.id: node for node in updated.nodes}
    for node_id in ("bat-material", "bat-cell", "bat-demand"):
        node = by_id.get(node_id)
        if node is not None and node.parent_id is None:
            node.parent_id = "ne-battery"

    existing_link_ids = {link.id for link in updated.stock_links}
    existing_pairs = {(link.node_id, link.symbol) for link in updated.stock_links}
    energy_node_ids = {node.id for node in energy_nodes}
    for link in defaults.stock_links:
        if link.node_id not in energy_node_ids:
            continue
        pair = (link.node_id, link.symbol)
        if link.id in existing_link_ids or pair in existing_pairs:
            continue
        updated.stock_links.append(link.model_copy(deep=True))
        existing_link_ids.add(link.id)
        existing_pairs.add(pair)
    return validate_graph(updated)


AI_REFERENCE_DESCRIPTIONS = {
    "ai-chip": "完整产业链见「国产半导体产业链」：芯片设计、制造与封测。",
    "ai-memory": "完整产业链见「国产半导体产业链」：存储芯片设计与制造。",
    "ai-package": "完整产业链见「国产半导体产业链」：先进封装与测试。",
    "ai-optical": "完整产业链见「光通信产业链」：光芯片、光模块、光网络与光纤光缆。",
    "ai-pcb": "完整产业链见「PCB 产业链」：高频高速板、HDI、封装基板、材料与设备。",
    "ai-mlcc": "完整产业链见「MLCC 产业链」：材料、制造与下游应用。",
}

PCB_LINK_SOURCE_NODES = {"ai-pcb", "ai-pcb-support"}


def _pcb_target_for_link(link) -> str:
    text = f"{link.reason_short} {link.note}".upper()
    if link.node_id == "ai-pcb":
        if "HDI" in text:
            return "pcb-hdi"
        if "封装基板" in text or "载板" in text:
            return "pcb-substrate"
        if "FPC" in text or "柔性" in text:
            return "pcb-fpc"
        if "高速" in text or "高频" in text or "算力" in text or "AI服务器" in text:
            return "pcb-high-speed"
        return "pcb-multilayer"

    if "覆铜板" in text or "CCL" in text:
        return "pcb-ccl"
    if "铜箔" in text:
        return "pcb-copper-foil"
    if "电子布" in text or "玻纤布" in text or "玻璃纤维布" in text:
        return "pcb-glass-fabric"
    if "树脂" in text or "PTFE" in text or "CBF" in text or "油墨" in text or "干膜" in text:
        return "pcb-resin"
    if "化学品" in text or "电镀液" in text or "清洗剂" in text:
        return "pcb-chemicals"
    if "微钻" in text or "钻针" in text or "钻孔" in text:
        return "pcb-drill"
    if "曝光" in text or "LDI" in text or "直接成像" in text:
        return "pcb-exposure"
    if "电镀" in text or "清洗" in text:
        return "pcb-plating"
    if "检测" in text or "测试" in text:
        return "pcb-testing"
    if "PCB设备" in text or "PCB专用设备" in text:
        return "pcb-equipment-other"
    return "pcb-material-other"


def _pcb_link_id(target_id: str, symbol: str) -> str:
    digest = hashlib.sha256(f"{target_id}|{symbol}".encode()).hexdigest()[:24]
    return f"pcb-{digest}"


def _add_pcb_links(updated: IndustryChainGraph, defaults: IndustryChainGraph) -> None:
    """Copy AI PCB demand evidence into the independent PCB chain."""
    existing_ids = {link.id for link in updated.stock_links}
    existing_pairs = {(link.node_id, link.symbol) for link in updated.stock_links}
    next_order: dict[str, int] = {}
    for node_id in {node.id for node in updated.nodes if node.chain_id == "pcb"}:
        next_order[node_id] = max(
            (link.sort_order for link in updated.stock_links if link.node_id == node_id),
            default=0,
        )

    for link in list(updated.stock_links):
        if link.node_id not in PCB_LINK_SOURCE_NODES:
            continue
        target_id = _pcb_target_for_link(link)
        pair = (target_id, link.symbol)
        if pair in existing_pairs:
            continue
        link_id = _pcb_link_id(target_id, link.symbol)
        if link_id in existing_ids:
            continue
        copied = link.model_copy(deep=True)
        copied.id = link_id
        copied.node_id = target_id
        next_order[target_id] = next_order.get(target_id, 0) + 10
        copied.sort_order = next_order[target_id]
        updated.stock_links.append(copied)
        existing_ids.add(link_id)
        existing_pairs.add(pair)

    for link in defaults.stock_links:
        if not link.node_id.startswith("pcb-"):
            continue
        pair = (link.node_id, link.symbol)
        if link.id in existing_ids or pair in existing_pairs:
            continue
        updated.stock_links.append(link.model_copy(deep=True))
        existing_ids.add(link.id)
        existing_pairs.add(pair)


def reorganize_industry_chains(graph: IndustryChainGraph) -> IndustryChainGraph:
    updated = validate_graph(graph).model_copy(deep=True)
    defaults = build_default_graph()
    tech_chain_ids = {
        "ai-industry", "semiconductor", "optical-communication", "mlcc", "pcb", "power-battery",
    }
    existing_category_ids = {item.id for item in updated.categories}
    updated.categories.extend(
        item.model_copy(deep=True)
        for item in defaults.categories
        if item.id in {"hard-tech", "new-energy"} and item.id not in existing_category_ids
    )
    existing_chain_ids = {item.id for item in updated.chains}
    updated.chains.extend(
        item.model_copy(deep=True)
        for item in defaults.chains
        if item.id in tech_chain_ids and item.id not in existing_chain_ids
    )
    node_chain_ids = {"optical-communication", "mlcc", "semiconductor", "pcb"}
    existing_node_ids = {item.id for item in updated.nodes}
    updated.nodes.extend(
        item.model_copy(deep=True)
        for item in defaults.nodes
        if item.chain_id in node_chain_ids and item.id not in existing_node_ids
    )

    by_node = {node.id: node for node in updated.nodes}
    restored = set()
    for seed in defaults.nodes:
        if seed.chain_id not in {"optical-communication", "mlcc"}:
            continue
        node = by_node[seed.id]
        node.chain_id = seed.chain_id
        node.parent_id = seed.parent_id
        restored.add(node.id)

    remaining = [node for node in updated.nodes if node.id not in restored]
    while remaining:
        children = [node for node in remaining if node.parent_id in restored]
        if not children:
            break
        for node in children:
            node.chain_id = by_node[node.parent_id].chain_id
            restored.add(node.id)
        remaining = [node for node in remaining if node.id not in restored]

    for node_id, previous_name in (("ai-optical", "光通信"), ("ai-mlcc", "MLCC")):
        node = by_node[node_id]
        seed = next(item for item in defaults.nodes if item.id == node_id)
        if node.name == previous_name:
            node.name = seed.name
            node.kind = seed.kind

    for node_id, description in AI_REFERENCE_DESCRIPTIONS.items():
        node = by_node.get(node_id)
        if node is not None and not node.description:
            node.description = description
    ai_pcb = by_node.get("ai-pcb")
    if ai_pcb is not None and ai_pcb.name in {"高速 PCB", "高速PCB"}:
        ai_pcb.name = "AI 服务器高速 PCB"

    hard_tech_ids = tech_chain_ids - {"power-battery"}
    for chain in updated.chains:
        if chain.id in hard_tech_ids:
            chain.category_id = "hard-tech"
    default_chains = {chain.id: chain for chain in defaults.chains}
    legacy_names = {
        "semiconductor": {"半导体产业链", "半导体"},
        "optical-communication": {"光通信"},
        "mlcc": {"MLCC"},
    }
    for chain_id, names in legacy_names.items():
        chain = next((item for item in updated.chains if item.id == chain_id), None)
        seed = default_chains.get(chain_id)
        if chain is not None and seed is not None and chain.name in names:
            chain.name = seed.name

    existing_ids = {link.id for link in updated.stock_links}
    existing_pairs = {(link.node_id, link.symbol) for link in updated.stock_links}
    for link in defaults.stock_links:
        if not link.node_id.startswith("semi-") and link.id not in {
            "l-verisilicon-ai", "l-jcet-ai", "l-sanhuan-ai-mlcc",
        }:
            continue
        pair = (link.node_id, link.symbol)
        if link.id not in existing_ids and pair not in existing_pairs:
            updated.stock_links.append(link.model_copy(deep=True))
            existing_ids.add(link.id)
            existing_pairs.add(pair)

    _add_pcb_links(updated, defaults)
    used_categories = {chain.category_id for chain in updated.chains}
    updated.categories = [
        category for category in updated.categories if category.id in used_categories
    ]
    return validate_graph(updated)


NEW_CHAIN_IDS = {"commercial-space", "robotics", "new-energy-vehicle"}
NEW_CATEGORY_IDS = {"aerospace", "advanced-manufacturing", "automotive"}

_BATTERY_STRUCTURE: dict[str, tuple[str, str, int]] = {
    "bat-resource": ("ne-battery", "segment", 5),
    "bat-material": ("ne-battery", "segment", 10),
    "bat-cathode": ("bat-material", "segment", 10),
    "bat-anode": ("bat-material", "segment", 20),
    "bat-separator": ("bat-material", "segment", 30),
    "bat-electrolyte": ("bat-material", "segment", 40),
    "bat-aux": ("ne-battery", "segment", 15),
    "bat-equipment": ("ne-battery", "segment", 20),
    "bat-cell": ("ne-battery", "segment", 25),
    "bat-power": ("bat-cell", "product", 70),
    "bat-storage": ("bat-cell", "product", 80),
    "bat-demand": ("ne-battery", "segment", 30),
    "bat-recycle": ("ne-battery", "segment", 35),
    "bat-tech": ("ne-battery", "segment", 40),
    "bat-lithium": ("bat-resource", "product", 10),
    "bat-solid": ("bat-tech", "product", 10),
    "bat-solid-material": ("bat-tech", "product", 20),
}

_BATTERY_NAME_UPGRADES: dict[str, tuple[str, str]] = {
    "bat-material": ("上游材料", "四大主材"),
    "bat-cell": ("电芯与 PACK", "电芯与系统"),
}


def expand_market_chains(graph: IndustryChainGraph) -> IndustryChainGraph:
    """Add space, robotics, vehicle and refined battery nodes without replacing user edits."""
    updated = validate_graph(graph).model_copy(deep=True)
    defaults = build_default_graph()

    existing_categories = {item.id for item in updated.categories}
    updated.categories.extend(
        item.model_copy(deep=True)
        for item in defaults.categories
        if item.id in NEW_CATEGORY_IDS and item.id not in existing_categories
    )

    existing_chains = {item.id for item in updated.chains}
    updated.chains.extend(
        item.model_copy(deep=True)
        for item in defaults.chains
        if item.id in NEW_CHAIN_IDS and item.id not in existing_chains
    )

    existing_nodes = {node.id: node for node in updated.nodes}
    for seed in defaults.nodes:
        if seed.id not in existing_nodes:
            node = seed.model_copy(deep=True)
            updated.nodes.append(node)
            existing_nodes[node.id] = node

    for node_id, (parent_id, kind, order) in _BATTERY_STRUCTURE.items():
        node = existing_nodes.get(node_id)
        if node is None:
            continue
        node.parent_id = parent_id
        node.kind = kind
        node.order = order
        if node_id in _BATTERY_NAME_UPGRADES:
            old_name, new_name = _BATTERY_NAME_UPGRADES[node_id]
            if node.name == old_name:
                node.name = new_name

    new_chain_node_ids = {
        node.id for node in defaults.nodes if node.chain_id in NEW_CHAIN_IDS
    }
    battery_node_ids = {
        node.id for node in defaults.nodes if node.id.startswith("bat-")
    }
    existing_link_ids = {link.id for link in updated.stock_links}
    existing_pairs = {(link.node_id, link.symbol) for link in updated.stock_links}
    for link in defaults.stock_links:
        if link.node_id not in new_chain_node_ids and link.node_id not in battery_node_ids:
            continue
        pair = (link.node_id, link.symbol)
        if link.id in existing_link_ids or pair in existing_pairs:
            continue
        updated.stock_links.append(link.model_copy(deep=True))
        existing_link_ids.add(link.id)
        existing_pairs.add(pair)

    return validate_graph(updated)


def migrate_graph(graph: IndustryChainGraph) -> IndustryChainGraph:
    """Fill missing descriptions without replaying historical structure migrations."""
    if graph.content_version >= CURRENT_GRAPH_CONTENT_VERSION:
        return graph

    updated = validate_graph(graph).model_copy(deep=True)
    defaults = {node.id: node for node in build_default_graph().nodes}
    identities = {
        node.id: (node.chain_id, node.parent_id, node.name, node.kind)
        for node in defaults.values()
    }
    for node_id, (parent_id, name, kind, _) in NODE_SPECS.items():
        parent = defaults.get(parent_id)
        if node_id not in identities and parent is not None:
            identities[node_id] = (parent.chain_id, parent_id, name, kind)

    for node in updated.nodes:
        if not node.description and identities.get(node.id) == (
            node.chain_id, node.parent_id, node.name, node.kind,
        ):
            node.description = NODE_DESCRIPTIONS.get(node.id, "")

    updated.content_version = CURRENT_GRAPH_CONTENT_VERSION
    return validate_graph(updated)
