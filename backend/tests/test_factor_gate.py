"""闸门（`app.factors.gate`）判据测试 —— 契约 §7.7 / §7.8 / §7.16。

闸门本轮**未接线**（§7.7.3 / §7.16.3 的 9 个调用点一个都没改），所以这里只测判定
逻辑本身，不碰任何 API。事实来源用 `MappingFacts` 注入，真实盘上事实只在
`RegistryFacts` 与清单 allowlist 两处出现（都是只读）。
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from app.factors import gate

#: 生产目录 `D:/TSP/data/user_data/custom_factors` 现有的 15 个定义（status 全 draft）。
#: 只在测试里出现（gate.py 不写死任何 id）；这里用它们造同形状的临时目录。
REAL_STORE_IDS = (
    "cf_auction_resonance",
    "uf_auction_post0920_match_growth",
    "uf_auction_tail_imbalance",
    "uf_auction_tail_match_growth",
    "uf_auction_volume_surprise",
    "uf_auction_volume_vs_prev",
    "uf_dist_prior_high_250",
    "uf_ma120",
    "uf_ma200",
    "uf_prior_high_20",
    "uf_prior_high_250",
    "uf_prior_high_55",
    "uf_prior_low_10",
    "uf_prior_vol_20",
    "uf_vol60",
)

#: §7.8.1 #6 / §7.15.1 第 1-8 行的 8 组同口径双 id：(alias, canonical)。
ALIAS_PAIRS = (
    ("vol60", "uf_vol60"),
    ("ma120", "uf_ma120"),
    ("ma200", "uf_ma200"),
    ("prior_high_20", "uf_prior_high_20"),
    ("prior_high_55", "uf_prior_high_55"),
    ("prior_high_250", "uf_prior_high_250"),
    ("prior_low_10", "uf_prior_low_10"),
    ("prior_vol_20", "uf_prior_vol_20"),
)

#: §7.16.4 定的 detail 键集合（FS03 / FS04 / FS06 共用）。
FS03_DETAIL_KEYS = {
    "code",
    "mode",
    "submitted_id",
    "resolved_id",
    "canonical_id",
    "table_row",
    "message",
}


def _facts(factor_id: str, **overrides) -> gate.FactorFacts:
    payload = {
        "factor_id": factor_id,
        "registered": True,
        "kind": "custom",
        "status": "active",
        "alias_of": None,
        "lang": "dsl",
        "strategy_usable": True,
        "table_row": None,
    }
    payload.update(overrides)
    return gate.FactorFacts(**payload)


def _source(**entries) -> gate.MappingFacts:
    mapping = {}
    for factor_id, overrides in entries.items():
        mapping[factor_id] = _facts(factor_id, **overrides)
    return gate.MappingFacts(mapping)


def _report(factor_ids, mode, source, **kwargs) -> gate.GateReport:
    return gate.assert_factors_usable(list(factor_ids), mode, shadow=True, facts=source, **kwargs)


def _write_store(data_dir: Path, ids, status: str = "draft") -> Path:
    directory = data_dir / "user_data" / "custom_factors"
    directory.mkdir(parents=True, exist_ok=True)
    for factor_id in ids:
        payload = {
            "id": factor_id,
            "kind": "custom",
            "label": factor_id,
            "formula": "close",
            "status": status,
            "version": 1,
        }
        (directory / f"{factor_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    return directory


# ---------------------------------------------------------------- 字段与形状

def test_gate_report_has_exactly_the_six_contract_fields() -> None:
    names = [item.name for item in dataclasses.fields(gate.GateReport)]
    assert names == ["ok", "blocked", "non_active", "unknown", "mode", "historical_only"]


def test_gate_error_detail_matches_section_7_16_4_shape() -> None:
    source = _source(vol60={"alias_of": "uf_vol60", "strategy_usable": False},
                     uf_vol60={})
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["vol60"], "production", facts=source)

    error = excinfo.value
    assert error.code == "FS03"
    assert error.entry is None
    assert set(error.detail) == FS03_DETAIL_KEYS
    assert error.detail["code"] == "FS03"
    assert error.detail["mode"] == "production"
    assert error.detail["submitted_id"] == "vol60"
    assert error.detail["resolved_id"] == "uf_vol60"
    assert error.detail["canonical_id"] == "uf_vol60"
    assert error.detail["table_row"] is None
    assert "uf_vol60" in error.detail["message"]
    assert error.report.ok is False
    assert error.to_detail() == error.detail


def test_gate_error_keeps_entry_label() -> None:
    source = _source(uf_x={"status": "draft"})
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(
            ["uf_x"], "production", facts=source, entry="POST /api/strategies/config"
        )
    assert excinfo.value.entry == "POST /api/strategies/config"


# ---------------------------------------------------------------- 4x2 矩阵

@pytest.mark.parametrize(
    ("status", "mode", "options", "expect_ok", "expect_codes", "expect_non_active",
     "expect_historical"),
    [
        ("active", "production", {}, True, (), False, False),
        ("watch", "production", {}, False, ("FS01",), False, False),
        ("draft", "production", {}, False, ("FS01",), False, False),
        ("retired", "production", {}, False, ("FS01",), False, False),
        ("active", "research", {}, True, (), False, False),
        ("watch", "research", {}, True, (), True, False),
        ("draft", "research", {}, False, ("FS01",), False, False),
        ("draft", "research", {"allow_non_active": True}, True, (), True, False),
        ("retired", "research", {}, False, ("FS01",), False, False),
        ("retired", "research", {"allow_retired": True}, True, (), True, True),
        ("active", "diagnostic", {}, True, (), False, False),
        ("watch", "diagnostic", {}, True, (), True, False),
        ("draft", "diagnostic", {}, True, (), True, False),
        ("retired", "diagnostic", {}, True, (), True, False),
    ],
)
def test_status_matrix_cells(
    status, mode, options, expect_ok, expect_codes, expect_non_active, expect_historical
) -> None:
    report = _report(["uf_x"], mode, _source(uf_x={"status": status}), **options)
    assert report.ok is expect_ok
    assert report.codes() == expect_codes
    assert ("uf_x" in report.non_active) is expect_non_active
    assert report.historical_only is expect_historical
    assert report.mode == mode


def test_provider_registered_without_status_is_treated_as_draft() -> None:
    source = _source(pack_only={"status": None})
    production = _report(["pack_only"], "production", source)
    assert production.codes() == ("FS01",)
    assert production.blocked == (("pack_only", None, "FS01"),)

    research = _report(["pack_only"], "research", source)
    assert research.codes() == ("FS01",)

    allowed = _report(["pack_only"], "research", source, allow_non_active=True)
    assert allowed.ok is True
    assert allowed.non_active == ("pack_only",)

    diagnostic = _report(["pack_only"], "diagnostic", source)
    assert diagnostic.ok is True
    assert diagnostic.non_active == ("pack_only",)


def test_require_status_false_skips_the_status_gate() -> None:
    source = _source(uf_x={"status": "draft"})
    assert _report(["uf_x"], "production", source, require_status=False).ok is True


def test_base_and_virtual_are_not_gated() -> None:
    for kind in ("base", "virtual"):
        source = _source(plain={"kind": kind, "status": None})
        for mode in ("production", "research", "diagnostic"):
            report = _report(["plain"], mode, source)
            assert report.ok is True
            assert report.blocked == ()
            assert report.non_active == ()


def test_unknown_id_is_fs02_in_every_mode() -> None:
    source = gate.MappingFacts({})
    for mode in ("production", "research", "diagnostic"):
        report = _report(["nope"], mode, source)
        assert report.codes() == ("FS02",)
        assert report.unknown == ("nope",)
        assert report.blocked == (("nope", None, "FS02"),)


# ---------------------------------------------------------------- 15 个 draft 定义

def test_fifteen_draft_definitions_are_fs01_in_production(tmp_path: Path) -> None:
    _write_store(tmp_path, REAL_STORE_IDS)
    source = gate.RegistryFacts(tmp_path)

    statuses = {fid: source.facts(fid).status for fid in REAL_STORE_IDS}
    assert set(statuses.values()) == {"draft"}
    assert all(source.facts(fid).kind == "custom" for fid in REAL_STORE_IDS)

    production = _report(REAL_STORE_IDS, "production", source)
    assert production.ok is False
    assert [item[0] for item in production.blocked] == list(REAL_STORE_IDS)
    assert production.codes() == ("FS01",)
    assert production.unknown == ()

    research = _report(REAL_STORE_IDS, "research", source)
    assert research.codes() == ("FS01",)
    assert len(research.blocked) == 15

    allowed = _report(REAL_STORE_IDS, "research", source, allow_non_active=True)
    assert allowed.ok is True
    assert set(allowed.non_active) == set(REAL_STORE_IDS)


def test_registry_facts_does_not_create_the_store_directory(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    gate.RegistryFacts(data_dir).facts("uf_nothing")
    assert not (data_dir / "user_data").exists()


# ---------------------------------------------------------------- alias / FS03

@pytest.mark.parametrize(("alias_id", "canonical_id"), ALIAS_PAIRS)
def test_eight_alias_pairs_are_fs03_in_production(alias_id, canonical_id) -> None:
    source = _source(
        **{
            alias_id: {"alias_of": canonical_id, "strategy_usable": False},
            canonical_id: {},
        }
    )
    report = _report([alias_id], "production", source)
    assert report.codes() == ("FS03",)
    assert report.blocked == ((alias_id, "active", "FS03"),)

    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable([alias_id], "production", facts=source)
    assert excinfo.value.detail["submitted_id"] == alias_id
    assert excinfo.value.detail["resolved_id"] == canonical_id


@pytest.mark.parametrize(("alias_id", "canonical_id"), ALIAS_PAIRS)
def test_eight_alias_pairs_pass_in_research_and_diagnostic(alias_id, canonical_id) -> None:
    source = _source(
        **{
            alias_id: {"alias_of": canonical_id, "strategy_usable": False},
            canonical_id: {},
        }
    )
    for mode in ("research", "diagnostic"):
        report = _report([alias_id], mode, source)
        assert report.ok is True
        assert report.blocked == ()


def test_canonical_id_is_never_fs03() -> None:
    source = _source(uf_vol60={"strategy_usable": True})
    assert _report(["uf_vol60"], "production", source).ok is True


def test_alias_table_row_is_carried_from_facts() -> None:
    source = _source(
        vol60={"alias_of": "uf_vol60", "strategy_usable": False, "table_row": 1},
        uf_vol60={},
    )
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["vol60"], "production", facts=source)
    assert excinfo.value.detail["table_row"] == 1


def test_alias_cycle_is_fs06_in_production_and_research() -> None:
    source = _source(
        a={"alias_of": "b", "strategy_usable": False},
        b={"alias_of": "a", "strategy_usable": False},
    )
    for mode in ("production", "research"):
        report = _report(["a"], mode, source)
        assert report.codes() == ("FS06",)
    assert _report(["a"], "diagnostic", source).ok is True


def test_alias_to_unregistered_target_is_fs06() -> None:
    source = _source(vol60={"alias_of": "uf_missing", "strategy_usable": False})
    assert _report(["vol60"], "production", source).codes() == ("FS06",)
    assert _report(["vol60"], "research", source).codes() == ("FS06",)


def test_alias_chain_limit_is_four_hops() -> None:
    four = {
        "a1": {"alias_of": "a2", "strategy_usable": False},
        "a2": {"alias_of": "a3", "strategy_usable": False},
        "a3": {"alias_of": "a4", "strategy_usable": False},
        "a4": {"alias_of": "target", "strategy_usable": False},
        "target": {},
    }
    resolved, chain = gate.resolve_alias("a1", _source(**four))
    assert resolved == "target"
    assert len(chain) == 4

    five = dict(four)
    five["a5"] = {"alias_of": "target", "strategy_usable": False}
    five["a4"] = {"alias_of": "a5", "strategy_usable": False}
    with pytest.raises(gate.AliasResolutionError):
        gate.resolve_alias("a1", _source(**five))
    assert _report(["a1"], "production", _source(**five)).codes() == ("FS06",)


def test_alias_flagged_usable_still_counts_as_alias() -> None:
    # §7.16.2 C3：交叉校验字段错配也不放行。
    source = _source(vol60={"alias_of": "uf_vol60", "strategy_usable": True}, uf_vol60={})
    assert _report(["vol60"], "production", source).codes() == ("FS03",)


def test_usable_false_without_alias_is_definition_conflict() -> None:
    # §7.16.5：strategy_usable 为 False 只可能因为 alias_of 非空。
    source = _source(uf_x={"strategy_usable": False})
    assert _report(["uf_x"], "production", source).codes() == ("FS06",)
    assert _report(["uf_x"], "research", source).codes() == ("FS06",)
    assert _report(["uf_x"], "diagnostic", source).ok is True


# ---------------------------------------------------------------- python / FS05

def test_python_factor_is_fs05_in_production_only() -> None:
    source = _source(py_factor={"lang": "python"})
    production = _report(["py_factor"], "production", source)
    assert production.codes() == ("FS05",)
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["py_factor"], "production", facts=source)
    assert excinfo.value.detail["resolved_id"] == "py_factor"
    for mode in ("research", "diagnostic"):
        assert _report(["py_factor"], mode, source).ok is True


# ---------------------------------------------------------------- 其他契约条款

def test_dual_id_in_one_call_is_not_silently_allowed() -> None:
    """§7.16.6 / B0b-1: FS04 由 NotImplementedError 改成真闸门码（GateError）。"""
    source = _source(
        vol60={"alias_of": "uf_vol60", "strategy_usable": False},
        uf_vol60={},
    )
    for mode in ("production", "research"):
        with pytest.raises(gate.GateError) as excinfo:
            gate.assert_factors_usable(["vol60", "uf_vol60"], mode, facts=source)
        assert excinfo.value.code == "FS04"
    assert _report(["vol60", "uf_vol60"], "diagnostic", source).ok is True

    # shadow=True 只报告不打断: FS03 仍在 blocked 里 (GateReport 无 FS04 槽位)。
    shadow_report = _report(["vol60", "uf_vol60"], "production", source)
    assert ("vol60", "active", "FS03") in shadow_report.blocked


def test_mode_none_does_not_judge_anything() -> None:
    source = _source(uf_x={"status": "draft"})
    report = _report(["uf_x", "nope"], "none", source)
    assert report.ok is True
    assert report.blocked == ()
    assert report.unknown == ()
    assert report.mode == "none"


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ValueError):
        gate.assert_factors_usable(["x"], "prodcution", shadow=True, facts=gate.MappingFacts({}))


def test_report_is_deterministic() -> None:
    source = _source(uf_x={"status": "draft"}, uf_y={"status": "watch"})
    first = _report(["uf_x", "uf_y"], "research", source)
    second = _report(["uf_x", "uf_y"], "research", source)
    assert first == second


def test_ledger_consistency_check_is_explicitly_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        gate.check_ledger_consistency()


# ---------------------------------------------------------------- 活配置 allowlist

def test_live_config_allowlist_shape_matches_the_artifact() -> None:
    allowlist = gate.load_live_config_allowlist()
    assert allowlist.records == 93
    assert allowlist.sources == 22
    assert allowlist.primary == 79
    assert allowlist.companion == 14
    assert len(allowlist.ids) == 19
    assert list(allowlist.ids) == sorted(allowlist.ids)
    assert allowlist.source_path.endswith("referenced_factor_inventory.json")


def test_live_config_allowlist_reads_only_the_inventory_json(monkeypatch) -> None:
    seen: list[Path] = []
    original = Path.read_text

    def spy(self, *args, **kwargs):
        seen.append(self)
        return original(self, *args, **kwargs)

    def refuse(*_args, **_kwargs):
        raise AssertionError("闸门不许写任何产物")

    monkeypatch.setattr(Path, "read_text", spy)
    monkeypatch.setattr(Path, "write_text", refuse)
    monkeypatch.setattr(Path, "write_bytes", refuse)

    gate.load_live_config_allowlist()
    assert seen
    assert all(item.name.endswith(".json") for item in seen)
    assert all(".sha256" not in item.name for item in seen)


def test_live_config_allowlist_fails_closed_on_summary_mismatch(tmp_path: Path) -> None:
    payload = json.loads(gate.DEFAULT_INVENTORY_PATH.read_text(encoding="utf-8"))
    payload["summary"]["live_config"]["records"] += 1
    tampered = tmp_path / "referenced_factor_inventory.json"
    tampered.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        gate.load_live_config_allowlist(tampered)


def test_live_config_ids_are_all_known_and_never_blocked_as_columns() -> None:
    ids = list(gate.load_live_config_allowlist().ids)
    source = gate.RegistryFacts()

    facts = {factor_id: source.facts(factor_id) for factor_id in ids}
    assert all(item.registered for item in facts.values()), "活配置 id 不应有 FS02"

    production = _report(ids, "production", source)
    blocked_ids = {item[0] for item in production.blocked}
    for factor_id in blocked_ids:
        # §7.8.3 黑名单语义: 被拦的必然是「不在豁免集」的 kind（B0b-1 由
        # 白名单 {custom, composite} 改为 EXEMPT_KINDS = {base, virtual}）。
        assert facts[factor_id].kind not in gate.EXEMPT_KINDS
        assert facts[factor_id].status != "active"

    research = _report(ids, "research", source, allow_non_active=True)
    assert research.ok is True
    assert set(research.non_active) == blocked_ids

    diagnostic = _report(ids, "diagnostic", source)
    assert diagnostic.ok is True
    assert set(diagnostic.non_active) == blocked_ids


# ------------------------------------------------- B0b-1 载体: 字段 / 黑名单 / FS04
def test_factor_spec_has_the_two_admission_fields_as_22nd_and_23rd() -> None:
    """F-A42-1: 第 22/23 字段，既有 21 个字段名一个不改。"""
    from app.factors.registry import FactorSpec

    fields = [item.name for item in dataclasses.fields(FactorSpec)]
    assert len(fields) == 23
    assert fields[-2:] == ["alias_of", "strategy_usable"]
    spec = FactorSpec(id="x", label="x", group="g", formula_text="close")
    assert spec.alias_of is None
    assert spec.strategy_usable is True
    assert spec.is_alias() is False


def test_store_reads_alias_of_and_strategy_usable_from_disk_json() -> None:
    """§7.16.5: 定义 JSON 的两键由 store 读入 spec（alias → strategy_usable False）。"""
    from app.factors import store

    alias_spec = store.to_spec({
        "id": "uf_alias_probe",
        "kind": "custom",
        "label": "别名探针",
        "formula": "close",
        "status": "draft",
        "version": 1,
        "alias_of": "uf_target_probe",
    })
    assert alias_spec.alias_of == "uf_target_probe"
    assert alias_spec.strategy_usable is False

    plain = store.to_spec({
        "id": "uf_plain_probe",
        "kind": "custom",
        "label": "普通探针",
        "formula": "close",
        "status": "draft",
        "version": 1,
    })
    assert plain.alias_of is None
    assert plain.strategy_usable is True

    # 显式错配（alias 却写 strategy_usable=true）不在读取层改写: 留给闸门交叉校验。
    mismatch = store.to_spec({
        "id": "uf_mismatch_probe",
        "kind": "custom",
        "label": "错配探针",
        "formula": "close",
        "status": "draft",
        "version": 1,
        "alias_of": "uf_target_probe",
        "strategy_usable": True,
    })
    assert mismatch.alias_of == "uf_target_probe"
    assert mismatch.strategy_usable is True


def test_gate_uses_a_blacklist_so_unknown_kinds_are_gated() -> None:
    """§7.8.3 裁定 B: 闸门按可复算性分类，不按 kind —— 新 kind 默认受约束。"""
    alias_facts = {"alias_of": "uf_vol60", "strategy_usable": False}
    for kind in ("custom", "composite", "python", "frame", "sidecar", "未知-kind"):
        source = _source(probe=dict(alias_facts, kind=kind), uf_vol60={})
        report = _report(["probe"], "production", source)
        assert report.blocked == (("probe", "active", "FS03"),), kind

    # 豁免集只有 base / virtual: 同一 alias 事实在这两个 kind 下不出码。
    for kind in ("base", "virtual"):
        source = _source(probe=dict(alias_facts, kind=kind), uf_vol60={})
        assert _report(["probe"], "production", source).blocked == (), kind


def test_fs04_raises_gate_error_and_wins_over_fs03() -> None:
    """§7.16.6: 同一策略内 alias + canonical 并存 → FS04，且优先于 FS03。"""
    source = _source(
        vol60={"alias_of": "uf_vol60", "strategy_usable": False},
        uf_vol60={},
    )
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["vol60", "uf_vol60"], "production", facts=source)
    error = excinfo.value
    assert error.code == "FS04"
    assert error.detail["code"] == "FS04"
    assert error.detail["canonical_id"] == "uf_vol60"
    assert error.detail["resolved_id"] == "uf_vol60"
    assert error.detail["dual_ids"] == ["vol60", "uf_vol60"]
    assert error.detail["table_row"] is None
    assert set(error.detail) >= FS03_DETAIL_KEYS
    assert not isinstance(error, NotImplementedError)

    # research 也拒（§7.8.4）；diagnostic 放行。
    with pytest.raises(gate.GateError) as research_error:
        gate.assert_factors_usable(["vol60", "uf_vol60"], "research", facts=source)
    assert research_error.value.code == "FS04"
    diagnostic = _report(["vol60", "uf_vol60"], "diagnostic", source)
    assert diagnostic.ok is True

    # 只有两个不相干的 canonical 时不出 FS04。
    clean = _report(["uf_vol60", "vol60"], "production", _source(uf_vol60={}, vol60={}))
    assert clean.blocked == ()


# ------------------------------------------------- 真盘: 8 组双 id
REAL_DATA_DIR = Path("D:/TSP/data")


@pytest.mark.skipif(not REAL_DATA_DIR.is_dir(), reason="本机无 D:/TSP/data 生产目录")
def test_real_disk_eight_alias_ids_are_rejected_and_canonicals_pass() -> None:
    """F-A42-2/F-A42-5: 真盘 8 个 alias → FS03；8 个 canonical 不出 FS03。"""
    source = gate.RegistryFacts(REAL_DATA_DIR)

    for alias_id, canonical_id in ALIAS_PAIRS:
        facts = source.facts(alias_id)
        assert facts.registered, alias_id
        assert facts.alias_of == canonical_id, alias_id
        assert facts.strategy_usable is False, alias_id

        with pytest.raises(gate.GateError) as excinfo:
            gate.assert_factors_usable([alias_id], "production", facts=source)
        detail = excinfo.value.detail
        assert excinfo.value.code == "FS03"
        assert detail["submitted_id"] == alias_id
        assert detail["resolved_id"] == canonical_id
        assert detail["canonical_id"] == canonical_id

        # research 放行（canonical 无 status → 按 draft 记 non_active，须显式允许；
        # deprecated_alias_used 标记的落点见 CONTRACT-GAP 4）。
        research = gate.assert_factors_usable(
            [alias_id], "research", allow_non_active=True, facts=source
        )
        assert research.ok is True

    for _alias_id, canonical_id in ALIAS_PAIRS:
        canonical_facts = source.facts(canonical_id)
        assert canonical_facts.registered, canonical_id
        assert canonical_facts.alias_of is None, canonical_id
        report = _report([canonical_id], "production", source)
        assert "FS03" not in {item[2] for item in report.blocked}, canonical_id


@pytest.mark.skipif(not REAL_DATA_DIR.is_dir(), reason="本机无 D:/TSP/data 生产目录")
def test_real_disk_six_single_sided_pack_factors_are_not_aliases() -> None:
    """F-A42-5: §7.15.1 第 9–14 行的 6 个单侧件 alias_of 必须为 None。"""
    source = gate.RegistryFacts(REAL_DATA_DIR)
    for factor_id in ("ma20", "ma60", "sd20", "boll_lower", "boll_upper", "prior_amount_20"):
        facts = source.facts(factor_id)
        assert facts.registered, factor_id
        assert facts.alias_of is None, factor_id
        report = _report([factor_id], "production", source)
        assert "FS03" not in {item[2] for item in report.blocked}, factor_id
