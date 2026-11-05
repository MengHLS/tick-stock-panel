from datetime import date

import polars as pl

from app.custom.industry_chain.defaults import build_default_graph
from app.custom.industry_chain.descriptions import NODE_DESCRIPTIONS
from app.custom.industry_chain.pool_import import (
    PoolObservation,
    merge_pool_observations,
    read_pool_observations,
    three_month_start,
)

START = date(2026, 8, 4)
END = date(2026, 11, 4)
NAMES = {"000001.SZ": "甲公司", "000002.SZ": "乙公司"}


def observation(text: str, symbol: str = "000001.SZ", **changes) -> PoolObservation:
    return PoolObservation(
        day=changes.get("day", END),
        symbol=symbol,
        name=changes.get("name", NAMES.get(symbol, "未知公司")),
        source=changes.get("source", "limit_board_events"),
        text=text,
    )


def imported_links(graph):
    return [link for link in graph.stock_links if link.id.startswith("pool-")]


def test_calendar_month_window_handles_month_end():
    assert three_month_start(END) == START
    assert three_month_start(date(2026, 5, 31)) == date(2026, 2, 28)


def test_maps_specific_topics_without_promoting_generic_topics_to_ai():
    graph, report = merge_pool_observations(
        build_default_graph(),
        [observation("AI服务器+先进封装"), observation("半导体+人工智能+PCB", "000002.SZ")],
        NAMES, START, END,
    )
    pairs = {(link.node_id, link.symbol) for link in imported_links(graph)}
    assert pairs == {
        ("ai-server-other", "000001.SZ"),
        ("semi-advanced", "000001.SZ"),
        ("pcb-multilayer", "000002.SZ"),
    }
    assert report["unmatched_records"] == 0
    assert all(link.evidence_status == "pending" for link in imported_links(graph))


def test_generic_mlcc_and_optical_modules_do_not_imply_ai_membership():
    graph, _ = merge_pool_observations(
        build_default_graph(),
        [observation("MLCC+光模块")], NAMES, START, END,
    )
    nodes = {node.id: node for node in graph.nodes}
    chains = {nodes[link.node_id].chain_id for link in imported_links(graph)}
    assert chains == {"mlcc", "optical-communication"}


def test_supply_materials_and_power_do_not_imply_finished_products():
    graph, _ = merge_pool_observations(
        build_default_graph(),
        [observation("AI服务器电源+AI PCB微钻+固态电池材料+光模块测试")],
        NAMES, START, END,
    )
    assert {link.node_id for link in imported_links(graph)} == {
        "ai-power", "ai-pcb-support", "bat-solid-material", "oc-test", "pcb-drill",
    }


def test_specific_new_energy_topics_map_to_leaf_nodes_without_generic_noise():
    graph, report = merge_pool_observations(
        build_default_graph(),
        [
            observation("光伏玻璃+海缆+储能PCS+电解槽+特高压"),
            observation("风电齿轮箱+换电站", "000002.SZ"),
        ],
        NAMES, START, END,
    )
    assert {link.node_id for link in imported_links(graph)} == {
        "ne-pv-glass",
        "ne-wind-cable",
        "ne-storage-pcs",
        "ne-hydrogen-electrolyzer",
        "ne-grid-uhv",
        "ne-wind-drivetrain",
        "ne-grid-swap",
    }
    assert report["added_links"] == 7

    generic, _ = merge_pool_observations(
        build_default_graph(),
        [observation("光伏+风电+电网+新能源")],
        NAMES, START, END,
    )
    assert imported_links(generic) == []


def test_specific_space_robot_vehicle_and_battery_topics_map_to_leaf_nodes():
    graph, report = merge_pool_observations(
        build_default_graph(),
        [observation(
            "火箭发动机+星敏感器+谐波减速器+行星滚柱丝杠"
            "+一体化压铸+磷酸铁锂+复合集流体+固态电解质"
        )],
        NAMES, START, END,
    )
    assert {link.node_id for link in imported_links(graph)} == {
        "cs-rocket-engine",
        "cs-attitude",
        "rb-harmonic",
        "rb-roller-screw",
        "nev-casting",
        "bat-cathode-lfp",
        "bat-composite-foil",
        "bat-solid-material",
    }
    assert report["added_links"] == 8


def test_ai_server_topics_are_refined_instead_of_all_falling_into_broad_node():
    graph, _ = merge_pool_observations(
        build_default_graph(),
        [
            observation("AI服务器+PCB"),
            observation("AI服务器+覆铜板", "000002.SZ"),
            observation("AI服务器+液冷", "000001.SZ"),
            observation("AI服务器+MLCC镍粉", "000002.SZ"),
            observation("AI服务器+服务器测试", "000001.SZ"),
            observation("AI服务器", "000002.SZ"),
        ],
        NAMES, START, END,
    )
    imported = [link for link in imported_links(graph) if link.node_id.startswith("ai-")]
    pairs = {(link.node_id, link.symbol) for link in imported}
    assert pairs == {
        ("ai-pcb", "000001.SZ"),
        ("ai-pcb-support", "000002.SZ"),
        ("ai-cooling", "000001.SZ"),
        ("ai-mlcc-material", "000002.SZ"),
        ("ai-server-test", "000001.SZ"),
        ("ai-server-other", "000002.SZ"),
    }
    assert all(link.basis == "theme_clue" for link in imported)


def test_context_rules_cover_ai_hardware_optical_and_energy_without_generic_false_positives():
    graph, _ = merge_pool_observations(
        build_default_graph(),
        [
            observation("PCB+HDI+AI算力"),
            observation("AI硬件+HVLP铜箔", "000002.SZ"),
            observation("数据中心+液冷微通道", "000001.SZ"),
            observation("AI应用+AI4S", "000002.SZ"),
            observation("光通信+空芯光纤", "000001.SZ"),
            observation("半导体+HBM+长鑫存储", "000002.SZ"),
            observation("电力+绿电+储能布局+风电运营", "000001.SZ"),
            observation("电力+绿色电力+氢能", "000002.SZ"),
        ],
        NAMES, START, END,
    )
    pairs = {(link.node_id, link.symbol) for link in imported_links(graph)}
    assert pairs == {
        ("ai-pcb", "000001.SZ"),
        ("ai-pcb-support", "000002.SZ"),
        ("ai-cooling", "000001.SZ"),
        ("ai-science", "000002.SZ"),
        ("oc-fiber", "000001.SZ"),
        ("semi-memory", "000002.SZ"),
        ("ne-storage-system", "000001.SZ"),
        ("ne-wind-construction", "000001.SZ"),
        ("ne-hydrogen", "000002.SZ"),
        ("pcb-hdi", "000001.SZ"),
        ("pcb-copper-foil", "000002.SZ"),
    }


def test_listing_suffix_and_st_prefix_are_not_name_conflicts():
    graph, _ = merge_pool_observations(
        build_default_graph(), [observation("AI服务器", name="*ST甲公司")],
        {"000001.SZ": "甲公司-U"}, START, END,
    )
    assert len(imported_links(graph)) == 1


def test_adds_needed_subsegments_and_deduplicates_source_dates():
    observations = [
        observation("AI漫剧+固态电池"),
        observation("AI漫剧+固态电池", source="ext_limit_up_platform"),
        observation("AI漫剧", day=START),
    ]
    graph, report = merge_pool_observations(build_default_graph(), observations, NAMES, START, END)
    links = imported_links(graph)
    assert {link.node_id for link in links} == {"ai-media", "bat-solid"}
    media = next(link for link in links if link.node_id == "ai-media")
    media_node = next(node for node in graph.nodes if node.id == "ai-media")
    assert media_node.description == NODE_DESCRIPTIONS["ai-media"]
    assert "2026-08-04" in media.note and "2026-11-04" in media.note
    assert "2 个交易日" in media.note
    assert "limit_board_events" in media.note and "ext_limit_up_platform" in media.note
    assert report["added_links"] == 2
    again, repeated = merge_pool_observations(graph, observations, NAMES, START, END)
    assert again == graph
    assert repeated["added_links"] == 0


def test_new_window_replaces_generated_note_without_losing_user_notes():
    original = build_default_graph()
    link = next(item for item in original.stock_links if item.id == "l-wus-pcb")
    link.note = (
        "用户保留的核验记录\n\n"
        "[涨停题材合并 2026-08-04..2026-11-04]\n"
        "首次 2026-08-04；最近 2026-08-04；1 个交易日；1 条来源记录。\n"
        "扩展数据：ext_limit_up_platform\n"
        "匹配题材：AI服务器PCB\n"
        "历史涨停题材线索，未核验当前主营、产品或供货关系。\n"
        "2026-08-04 [ext_limit_up_platform] AI服务器PCB"
    )
    graph, _ = merge_pool_observations(
        original,
        [
            observation("AI服务器PCB", "002463.SZ", name="沪电股份", day=date(2025, 10, 16)),
            observation("AI服务器PCB", "002463.SZ", name="沪电股份"),
        ],
        {"002463.SZ": "沪电股份"},
        date(2025, 10, 16),
        END,
    )
    updated = next(item for item in graph.stock_links if item.id == link.id)
    assert updated.note.startswith("用户保留的核验记录")
    assert "[涨停题材合并 2025-10-16..2026-11-04]" in updated.note
    assert "[涨停题材合并 2026-08-04..2026-11-04]" not in updated.note
    assert updated.note.count("[涨停题材合并") == 1


def test_preserves_existing_reason_status_notes_and_source():
    original = build_default_graph()
    link = next(item for item in original.stock_links if item.id == "l-wus-pcb")
    link.note = "用户保留的研究记录"
    snapshot = link.model_copy(deep=True)
    graph, report = merge_pool_observations(
        original, [observation("AI服务器PCB", "002463.SZ", name="沪电股份")],
        {"002463.SZ": "沪电股份"}, START, END,
    )
    updated = next(item for item in graph.stock_links if item.id == link.id)
    assert updated.reason_short == snapshot.reason_short
    assert updated.evidence_status == snapshot.evidence_status
    assert updated.source_url == snapshot.source_url
    assert updated.note.startswith(snapshot.note)
    assert link == snapshot
    pcb = next(
        link for link in graph.stock_links
        if link.node_id == "pcb-high-speed" and link.symbol == "002463.SZ"
    )
    assert pcb.note.startswith("[涨停题材合并")
    assert report["enriched_links"] == 2


def test_rejects_bad_codes_name_conflicts_out_of_window_and_negations():
    observations = [
        observation("AI服务器", "602587.SH"),
        observation("AI服务器", name="其他公司"),
        observation("AI服务器", day=date(2026, 8, 3)),
        observation("不涉及AI服务器+未布局光模块"),
    ]
    graph, report = merge_pool_observations(build_default_graph(), observations, NAMES, START, END)
    assert imported_links(graph) == []
    assert {item["reason"] for item in report["review"]} >= {"unknown_symbol", "name_conflict", "outside_window"}


def test_long_user_note_is_not_truncated():
    original = build_default_graph()
    link = next(item for item in original.stock_links if item.id == "l-wus-pcb")
    link.note = "用户记录" * 499
    graph, report = merge_pool_observations(
        original, [observation("AI服务器PCB", "002463.SZ", name="沪电股份")],
        {"002463.SZ": "沪电股份"}, START, END,
    )
    assert next(item for item in graph.stock_links if item.id == link.id).note == link.note
    assert report["note_capacity_skips"] == 1


class FakePoolData:
    def dataset_partition_dates(self, dataset, start, end):
        return [END]

    def read_dataset_partition(self, dataset, day, columns=None):
        if "ext_limit_up_platform" in dataset:
            return pl.DataFrame({
                "date": ["2026-11-04", "2026-11-05"],
                "symbol": ["000001.SZ", "000002.SZ"], "name": ["甲公司", "乙公司"],
                "sector": ["算力", "算力"], "keywords": ["AI服务器", "AI服务器"],
            })
        return pl.DataFrame({
            "trade_date": ["2026-11-04"] * 2,
            "symbol": ["000001.SZ", "000002.SZ"], "name": ["甲公司", "乙公司"],
            "limit_up_reason": ["AI服务器", "先进封装"],
            "in_limit_up_pool": [1, 0],
        })


def test_reader_excludes_break_only_rows_and_wrong_partition_dates():
    observations, coverage = read_pool_observations(FakePoolData(), START, END)
    assert len(observations) == 2
    assert {item.symbol for item in observations} == {"000001.SZ"}
    assert coverage["excluded_break_only_rows"] == 1
    assert coverage["excluded_date_rows"] == 1
