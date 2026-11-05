from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.custom.industry_chain.defaults import build_default_graph
from app.custom.industry_chain.migration import migrate_graph
from app.custom.industry_chain.models import IndustryChainGraph, validate_graph
from app.custom.industry_chain.store import graph_path, load_graph, save_graph


def test_upgrade_preserves_structure_order_and_link_evidence() -> None:
    graph = build_default_graph()
    graph.content_version = 0
    nodes = {node.id: node for node in graph.nodes}
    nodes["bat-material"].order = 777
    nodes["oc-laser"].parent_id = "oc-module"
    nodes["mlcc-ceramic"].parent_id = "mlcc-manufacture"
    graph.nodes = [node for node in graph.nodes if node.id != "ai-app-other"]
    link = next(item for item in graph.stock_links if item.evidence_status == "pending")
    link.basis = "supply"
    graph.stock_links.pop()
    before = graph.model_copy(deep=True)

    upgraded = migrate_graph(graph)

    assert graph == before
    assert upgraded.stock_links == before.stock_links
    assert {node.id for node in upgraded.nodes} == {node.id for node in before.nodes}
    updated_nodes = {node.id: node for node in upgraded.nodes}
    assert updated_nodes["bat-material"].order == 777
    assert updated_nodes["oc-laser"].parent_id == "oc-module"
    assert updated_nodes["mlcc-ceramic"].parent_id == "mlcc-manufacture"
    assert migrate_graph(upgraded) == upgraded


def test_custom_only_legacy_graph_remains_readable(tmp_path: Path) -> None:
    graph = validate_graph(IndustryChainGraph.model_validate({
        "categories": [{"id": "custom", "name": "自定义"}],
        "chains": [{"id": "custom", "category_id": "custom", "name": "自定义链"}],
        "nodes": [{"id": "custom-node", "chain_id": "custom", "name": "自定义环节"}],
    }))
    path = graph_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(graph.model_dump_json(), encoding="utf-8")

    upgraded = load_graph(tmp_path)

    assert upgraded["nodes"] == graph.model_dump()["nodes"]
    assert upgraded["chains"] == graph.model_dump()["chains"]
    assert load_graph(tmp_path) == upgraded


@pytest.mark.parametrize("operation", ["load", "save_current", "save_future"])
def test_future_version_is_rejected_without_changing_file(tmp_path: Path, operation: str) -> None:
    graph = build_default_graph()
    future = graph.model_dump()
    future.update(content_version=3, future_field={"must_survive": True})
    path = graph_path(tmp_path)
    path.parent.mkdir(parents=True)
    original = json.dumps(future, ensure_ascii=False).encode("utf-8")
    path.write_bytes(original)
    payload = IndustryChainGraph.model_validate(future) if operation == "save_future" else graph

    with pytest.raises(ValueError, match="版本"):
        if operation == "load":
            load_graph(tmp_path)
        else:
            save_graph(tmp_path, payload)

    assert path.read_bytes() == original


def test_future_request_is_rejected_even_without_existing_file(tmp_path: Path) -> None:
    graph = build_default_graph()
    graph.content_version = 3

    with pytest.raises(ValueError, match="版本"):
        save_graph(tmp_path, graph)

    assert not graph_path(tmp_path).exists()


def test_upgrade_preserves_persisted_names_and_former_default_order() -> None:
    graph = build_default_graph()
    graph.content_version = 0
    nodes = {node.id: node for node in graph.nodes}
    nodes["rb-upstream"].order = 50
    nodes["rb-upstream"].description = "用户整理的材料"
    nodes["bat-grid"].name = "储能系统"
    nodes["bat-sodium"].name = "钠离子电池"
    original = graph.model_copy(deep=True)

    upgraded = migrate_graph(graph)

    assert upgraded.nodes == original.nodes


def test_upgrade_does_not_describe_custom_node_with_seed_id(tmp_path: Path) -> None:
    graph = IndustryChainGraph.model_validate({
        "categories": [{"id": "custom", "name": "自定义"}],
        "chains": [{"id": "custom", "category_id": "custom", "name": "自定义链"}],
        "nodes": [{"id": "ai-chip", "chain_id": "custom", "name": "医疗服务"}],
    })
    path = graph_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(graph.model_dump_json(), encoding="utf-8")

    upgraded = load_graph(tmp_path)

    assert upgraded["nodes"] == graph.model_dump()["nodes"]
