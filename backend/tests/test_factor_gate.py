"""闸门（`app.factors.gate`）判据测试 —— 契约 §7.7 / §7.8 / §7.16。

闸门本轮**未接线**（§7.7.3 / §7.16.3 的 9 个调用点一个都没改），所以这里只测判定
逻辑本身，不碰任何 API。事实来源用 `MappingFacts` 注入，真实盘上事实只在
`RegistryFacts` 与清单 allowlist 两处出现（都是只读）。
"""
from __future__ import annotations

import dataclasses
import inspect
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
    """§7.17.4 C4（v0.12）：mode 域外由 ValueError 改判 `FS09`（`GateError` → HTTP 400）。

    旧断言押 ValueError，已被 §7.17.4「入参非法 → `FS09`」与 C1「`ValueError` 不得
    逃出闸门」明文取代；此处只改「异常类型 + 错误码」的期待，不放宽任何强度。
    """
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["x"], "prodcution", shadow=True, facts=gate.MappingFacts({}))
    assert excinfo.value.code == "FS09"
    assert excinfo.value.detail["submitted_id"] == "mode"


def test_report_is_deterministic() -> None:
    source = _source(uf_x={"status": "draft"}, uf_y={"status": "watch"})
    first = _report(["uf_x", "uf_y"], "research", source)
    second = _report(["uf_x", "uf_y"], "research", source)
    assert first == second


def test_ledger_consistency_check_fails_closed_with_fs06() -> None:
    """§7.17.4 C3（v0.12）：台账判不出来 → `GateError(FS06)`，不再抛 `NotImplementedError`。

    旧断言押 NotImplementedError，已被 C1「出口唯一」与 C3「FS06 fail-closed」明文取代。
    """
    with pytest.raises(gate.GateError) as excinfo:
        gate.check_ledger_consistency()
    assert excinfo.value.code == "FS06"
    assert set(excinfo.value.detail) == FS03_DETAIL_KEYS
    assert excinfo.value.report is None


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

# ------------------------------------------- F-A43–F-A47：命名面 / 豁免集 / FS09（v0.12 §7.17）

#: 契约 §7.17.1(3) / F-A44-2 的 4 个撞名负样本（它们同时是列名与 kind=custom 的因子 id）。
NAMESPACE_NEGATIVE_IDS = ("boll_lower", "boll_upper", "ma20", "ma60")

#: F-A44-4 的 7 条活信号（`custom_signals/<id>.json`）。
LIVE_SIGNAL_IDS = (
    "boll_breakdown_lower",
    "boll_breakout_upper",
    "ma20_breakdown",
    "ma20_breakout",
    "ma_dead_5_20",
    "ma_golden_20_60",
    "ma_golden_5_20",
)


def _live_ids() -> list[str]:
    """活配置的 19 名（契约 §7.17.5 末段：取「当时」的清单，不写死名字）。"""
    ids = list(gate.load_live_config_allowlist().ids)
    assert ids, "清单 summary.live_config 为空，先重跑 referenced_factor_inventory"
    assert all(item in gate._column_universe() for item in ids), "19 名应全在列全集内"
    return ids


def _blocked_map(ids: list[str], mode: str, **kwargs) -> dict[str, tuple[str | None, str]]:
    report = gate.assert_factors_usable(
        ids, mode, shadow=True, facts=gate.RegistryFacts(), **kwargs
    )
    return {row[0]: (row[1], row[2]) for row in report.blocked}


def test_f_a43_1_signature_appends_keyword_only_namespace_only() -> None:
    params = list(inspect.signature(gate.assert_factors_usable).parameters.values())
    assert [(p.name, p.kind, p.default) for p in params[:2]] == [
        ("factor_ids", inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.empty),
        ("mode", inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.empty),
    ]
    keywords = params[2:]
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in keywords)
    # 既有 6 个 keyword-only 参数名与缺省值一字不改，namespace 只追加在尾部。
    assert [(p.name, p.default) for p in keywords] == [
        ("allow_non_active", False),
        ("allow_retired", False),
        ("require_status", True),
        ("shadow", False),
        ("entry", None),
        ("facts", None),
        ("namespace", "factor"),
    ]


@pytest.mark.parametrize("bad", ["base", "virtual", "COLUMN", None, "Column", "factor "])
def test_f_a43_2_namespace_domain_is_fail_closed_with_fs09(bad) -> None:
    """§7.17.2 S5 + §7.17.4 C4：域外取值（含 kind 与大小写变体）→ FS09，不进 blocked。"""
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(
            ["close"], "production", namespace=bad, facts=gate.MappingFacts({})
        )
    error = excinfo.value
    assert error.code == "FS09"
    assert set(error.detail) == FS03_DETAIL_KEYS
    assert error.detail["submitted_id"] == "namespace"
    assert error.detail["table_row"] is None
    assert error.report is None


def test_f_a43_3_mapping_form_needs_every_id_and_ignores_extra_keys() -> None:
    """§7.17.2 S3：逐 id 取面；缺键即 FS09，多余键忽略。"""
    ids = _live_ids()
    source = gate.RegistryFacts()
    plain = gate.assert_factors_usable(ids, "production", namespace="column", shadow=True, facts=source)
    mapped = gate.assert_factors_usable(
        ids, "production", namespace=dict.fromkeys(ids, "column"), shadow=True, facts=source
    )
    assert mapped == plain

    with_extra = dict.fromkeys(ids, "column") | {"__not_a_live_id__": "column"}
    assert gate.assert_factors_usable(
        ids, "production", namespace=with_extra, shadow=True, facts=source
    ) == plain

    for broken in ({}, {**dict.fromkeys(ids, "column"), ids[0]: None}):
        with pytest.raises(gate.GateError) as excinfo:
            gate.assert_factors_usable(ids, "production", namespace=broken, facts=source)
        assert excinfo.value.code == "FS09"
        assert excinfo.value.detail["submitted_id"] == "namespace"

    missing = dict.fromkeys(ids, "column")
    missing.pop(ids[0])
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(ids, "production", namespace=missing, facts=source)
    assert excinfo.value.code == "FS09"
    assert ids[0] in excinfo.value.detail["message"]


def test_f_a43_4_column_face_is_closed_over_the_column_universe() -> None:
    """§7.17.2 S4：列面且 id ∉ `_column_universe()` → FS02；列全集内不拦。"""
    source = gate.RegistryFacts()
    assert "uf_vol60" not in gate._column_universe()
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["uf_vol60"], "production", namespace="column", facts=source)
    assert excinfo.value.code == "FS02"

    allowed = gate.assert_factors_usable(["close"], "production", namespace="column", facts=source)
    assert allowed.ok is True
    assert allowed.blocked == ()


def test_f_a44_1_live_config_ids_all_pass_on_the_column_face() -> None:
    """F-A44-1：19 名 `production` + `namespace="column"` 全过。"""
    ids = _live_ids()
    report = gate.assert_factors_usable(ids, "production", namespace="column", facts=gate.RegistryFacts())
    assert report.ok is True
    assert report.blocked == ()
    assert report.non_active == ()
    assert report.unknown == ()
    assert report.mode == "production"


def test_f_a44_2_the_four_collision_names_stay_fs01_on_the_factor_face() -> None:
    """F-A44-2：同 4 名在缺省因子面 production / research 仍是 FS01（kind=custom、无 status）。"""
    ids = _live_ids()
    assert set(NAMESPACE_NEGATIVE_IDS) <= set(ids), "4 个撞名负样本仍在活配置里"
    for mode in ("production", "research"):
        blocked = _blocked_map(list(NAMESPACE_NEGATIVE_IDS), mode)
        assert set(blocked) == set(NAMESPACE_NEGATIVE_IDS)
        assert set(blocked.values()) == {(None, "FS01")}


def test_f_a44_3_only_the_four_collision_names_change_conclusion() -> None:
    """F-A44-3：另外 15 名逐 id 结论不变，本次改动只应改变那 4 个 id。

    15 名的构成按盘上事实判：14 个靠列回落（`kind=base` 且 `lang is None`，即不是
    spec、由列全集回落）+ `vol_ratio_5d` 是**注册 base**（`kind=base` 且 `lang` 非空）。
    这既钉住「改的只有那 4 个」，也钉住「14+1 的分类没有被顺手改掉」。
    """
    ids = _live_ids()
    before = _blocked_map(ids, "production")
    after = _blocked_map(ids, "production", namespace="column")
    assert set(before) - set(after) == set(NAMESPACE_NEGATIVE_IDS)
    assert set(after) == set()
    for factor_id in ids:
        if factor_id in NAMESPACE_NEGATIVE_IDS:
            continue
        assert before.get(factor_id) == after.get(factor_id), factor_id

    source = gate.RegistryFacts()
    changed = {fid for fid in ids if before.get(fid) != after.get(fid)}
    assert changed == set(NAMESPACE_NEGATIVE_IDS)
    # 4 个撞名负样本的盘上事实：kind=custom、status 空（无 status → 按 draft 判 FS01）。
    for factor_id in NAMESPACE_NEGATIVE_IDS:
        facts = source.facts(factor_id)
        assert facts.kind == "custom", factor_id
        assert facts.status is None, factor_id

    untouched = [fid for fid in ids if fid not in NAMESPACE_NEGATIVE_IDS]
    assert len(untouched) == 15
    fallback = [fid for fid in untouched if source.facts(fid).lang is None]
    registered = [fid for fid in untouched if source.facts(fid).lang is not None]
    assert len(fallback) == 14, fallback
    assert registered == ["vol_ratio_5d"], registered
    for factor_id in untouched:
        assert source.facts(factor_id).kind == "base", factor_id


def test_f_a44_4_the_seven_live_signals_are_not_newly_blocked_on_the_column_face() -> None:
    """F-A44-4：7 条活信号引用的 id 在列面下结论与未接线前一致（都放行）。"""
    payload = json.loads(gate.DEFAULT_INVENTORY_PATH.read_text(encoding="utf-8"))
    rows = [row for row in payload["records"] if row.get("source_enabled") is True]
    source = gate.RegistryFacts()
    for signal in LIVE_SIGNAL_IDS:
        ids = sorted({
            str(row["ref_name"])
            for row in rows
            if str(row.get("source_path", "")).endswith(f"custom_signals/{signal}.json")
        })
        assert ids, f"清单里找不到活信号 {signal} 的引用"
        report = gate.assert_factors_usable(ids, "production", namespace="column", shadow=True, facts=source)
        assert report.blocked == (), (signal, report.blocked)


def test_f_a44_4_gate_is_not_wired_into_production_so_signal_values_cannot_change() -> None:
    """F-A44-4 的前置事实：闸门零生产调用方，信号与回测数值不可能因本单改变。

    接线（§7.7.3 / §7.16.3 的 9 个调用点）之后必须重做 F-A44-4 的数值取证 —— 本用例
    就是那条提醒：一旦出现调用方它就红。
    """
    gate_path = Path(gate.__file__).resolve()
    app_root = gate_path.parents[1]
    callers = [
        str(path.relative_to(app_root))
        for path in app_root.rglob("*.py")
        if path.resolve() != gate_path and "assert_factors_usable" in path.read_text(encoding="utf-8")
    ]
    assert callers == []


def test_f_a45_1_default_namespace_equals_the_explicit_factor_face() -> None:
    """F-A45-1：不传 namespace ≡ `namespace="factor"`，四个组合逐项相等。"""
    ids = _live_ids()
    source = gate.RegistryFacts()
    for mode, kwargs in (
        ("production", {}),
        ("research", {}),
        ("research", {"allow_non_active": True}),
        ("diagnostic", {}),
    ):
        default = gate.assert_factors_usable(ids, mode, shadow=True, facts=source, **kwargs)
        explicit = gate.assert_factors_usable(
            ids, mode, namespace="factor", shadow=True, facts=source, **kwargs
        )
        assert default == explicit
        if mode == "production":
            assert {row[0] for row in default.blocked} == set(NAMESPACE_NEGATIVE_IDS)


@pytest.mark.parametrize("kind", ["custom", "composite", "frame", "sidecar", None, "weird"])
def test_f_a46_1_kind_never_changes_the_verdict(kind) -> None:
    """F-A46-1：同一 id 换 kind，production 六次都是同一个 FS03。"""
    source = _source(
        vol60={"kind": kind, "alias_of": "uf_vol60", "strategy_usable": False},
        uf_vol60={},
    )
    assert _report(["vol60"], "production", source).codes() == ("FS03",)


def test_f_a46_2_missing_kind_is_not_exempt() -> None:
    """F-A46-2：`kind=None`（事实缺失）按 custom 判 → FS01，不是放行。"""
    source = gate.MappingFacts({"x": gate.FactorFacts(factor_id="x", registered=True)})
    assert _report(["x"], "production", source).codes() == ("FS01",)


def test_f_a46_3_exempt_kinds_is_exactly_the_contract_set() -> None:
    """F-A46-3：豁免集 = {base, virtual}，与 §7.8.3 第一行同步且闭合。"""
    assert frozenset({"base", "virtual"}) == gate.EXEMPT_KINDS


def test_f_a46_4_exempt_kinds_are_not_dragged_into_the_gate() -> None:
    """F-A46-4：base / virtual（含 14 个列回落名与 vol_ratio_5d）production 仍全放行。"""
    ids = _live_ids()
    source = gate.RegistryFacts()
    exempt = [fid for fid in ids if source.facts(fid).kind in gate.EXEMPT_KINDS]
    assert "vol_ratio_5d" in exempt
    assert len(exempt) == len(ids) - len(NAMESPACE_NEGATIVE_IDS)
    report = gate.assert_factors_usable(exempt, "production", facts=source)
    assert report.ok is True
    assert report.blocked == ()
    assert report.non_active == ()


def test_f_a47_2_no_not_implemented_error_is_left_in_the_gate() -> None:
    """F-A47-2：代码文本里 `raise NotImplementedError` 计数为 0；台账分支改抛 FS06。"""
    source_text = Path(gate.__file__).read_text(encoding="utf-8")
    assert source_text.count("raise NotImplementedError") == 0
    with pytest.raises(gate.GateError) as excinfo:
        gate.check_ledger_consistency()
    assert excinfo.value.code == "FS06"


def test_f_a47_3_only_gate_error_leaves_the_gate() -> None:
    """F-A47-3 / C1：入参非法与 status 域外都只出 `GateError`，`ValueError` 不逃逸。"""
    bad_status = gate.MappingFacts({
        "x": gate.FactorFacts(factor_id="x", registered=True, kind="custom", status="zzz"),
    })
    for call in (
        lambda: gate.assert_factors_usable(["x"], "prodcution", facts=gate.MappingFacts({})),
        lambda: gate.assert_factors_usable(["x"], "production", facts=bad_status),
        lambda: gate.assert_factors_usable(["x"], "production", namespace=None, facts=gate.MappingFacts({})),
    ):
        with pytest.raises(gate.GateError) as excinfo:
            call()
        assert excinfo.value.code == "FS09"


def test_f_a47_4_fs09_detail_shape_is_the_section_7_16_4_shape() -> None:
    """F-A47-4：FS09 的 detail 键集合 = §7.16.4 形状，`submitted_id="namespace"`。"""
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["close"], "production", namespace="COLUMN", facts=gate.MappingFacts({}))
    error = excinfo.value
    assert error.code == "FS09"
    assert set(error.detail) == FS03_DETAIL_KEYS
    assert error.detail["submitted_id"] == "namespace"
    assert error.detail["resolved_id"] is None
    assert error.detail["canonical_id"] is None
    assert error.detail["table_row"] is None
    assert "namespace" in error.detail["message"]


# ---------------------------------- §7.16.4 单 id 多码去重（开发经理 2026-11-08 裁定）
#: FS01 的 detail = §7.16.4 的 7 键 + status（§7.7.5）。
FS01_DETAIL_KEYS = FS03_DETAIL_KEYS | {"status"}


@pytest.mark.skipif(not REAL_DATA_DIR.is_dir(), reason="本机无 D:/TSP/data 生产目录")
def test_real_disk_single_alias_id_reports_only_one_code_and_exactly_seven_keys() -> None:
    """真盘单 `vol60`：alias 来自 pack 无 status 载体 → 必然同时成立 FS03 与 FS01。

    裁定：同一 `submitted_id` 多码只报最高优先级一码（FS03 > FS01），**不写**
    `violations`，detail 恒为 7 键（§7.16.4）。本用例只用真盘事实源，不用合成源。
    """
    source = gate.RegistryFacts(REAL_DATA_DIR)
    facts = source.facts("vol60")
    assert facts.registered and facts.alias_of == "uf_vol60"
    assert facts.status is None, "pack 注册的 alias 没有 status 载体（前提变了要重审）"

    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["vol60"], "production", facts=source)
    error = excinfo.value

    assert error.code == "FS03", error.code
    assert error.detail["code"] == "FS03"
    assert error.detail["resolved_id"] == "uf_vol60"
    assert error.detail["canonical_id"] == "uf_vol60"
    # 核心：恰好 7 键，且没有 violations / status 追加键。
    assert set(error.detail) == FS03_DETAIL_KEYS
    assert len(error.detail) == 7
    assert "violations" not in error.detail
    assert "status" not in error.detail
    # 单 id 单码：report.blocked 长度 1，不触发批量 violations 门槛。
    assert error.report is not None
    assert error.report.blocked == (("vol60", None, "FS03"),)


@pytest.mark.skipif(not REAL_DATA_DIR.is_dir(), reason="本机无 D:/TSP/data 生产目录")
def test_real_disk_single_status_missing_id_reports_fs01_with_exactly_eight_keys() -> None:
    """真盘单 `ma20`：kind=custom、无 status → 只有 FS01，detail = 7 键 + status = 8 键。

    `status` 追加键只跟**最终** `code` 走：FS01 才有，FS03 没有（上一条用例）。
    """
    source = gate.RegistryFacts(REAL_DATA_DIR)
    facts = source.facts("ma20")
    assert facts.registered and facts.alias_of is None
    assert facts.kind == "custom"

    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["ma20"], "production", facts=source)
    error = excinfo.value

    assert error.code == "FS01", error.code
    assert set(error.detail) == FS01_DETAIL_KEYS
    assert len(error.detail) == 8
    assert "violations" not in error.detail
    assert error.detail["status"] is None  # 无 status 载体 → 按 draft 判（§7.8.4 末行）
    assert error.report is not None
    assert error.report.blocked == (("ma20", None, "FS01"),)


@pytest.mark.skipif(not REAL_DATA_DIR.is_dir(), reason="本机无 D:/TSP/data 生产目录")
def test_real_disk_multi_id_batch_still_reports_violations() -> None:
    """`violations` 的门槛是「>=2 个**不同 id**」，不是「>=2 条 blocked」。

    真盘 `vol60` + `ma20`：两个不同 id 各一码 → violations 两条，detail 7+violations。
    """
    source = gate.RegistryFacts(REAL_DATA_DIR)
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["vol60", "ma20"], "production", facts=source)
    error = excinfo.value

    assert error.code == "FS03"  # 取 blocked[0] 的码（输入顺序首条）
    assert set(error.detail) == FS03_DETAIL_KEYS | {"violations"}
    assert error.detail["violations"] == [
        {"submitted_id": "vol60", "code": "FS03"},
        {"submitted_id": "ma20", "code": "FS01"},
    ]


def test_code_priority_constant_is_the_ruled_order() -> None:
    """裁定次序 FS04 > FS03 > FS06 > FS01 > FS05 写死在常量里，且被 _judge 使用。"""
    order = gate._CODE_PRIORITY
    assert [code for code, _ in sorted(order.items(), key=lambda kv: kv[1])] == [
        "FS04",
        "FS03",
        "FS06",
        "FS01",
        "FS05",
    ]
    source = gate.MappingFacts({
        "ali": gate.FactorFacts(
            factor_id="ali", registered=True, kind="custom", status="draft",
            alias_of="canon", lang="python",
        ),
        "canon": gate.FactorFacts(factor_id="canon", registered=True, kind="custom", status="active"),
    })
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["ali"], "production", facts=source)
    # FS03 / FS01 / FS05 三码同时成立 → 只报 FS03。
    assert excinfo.value.code == "FS03"
    assert len(excinfo.value.detail) == 7


# ---------------------------- §7.16.4 组合键形态（开发经理 2026-11-08 实测的 7 组）
#: 开发经理在真盘（`RegistryFacts(D:/TSP/data)`、`production`）实测的 7 组 detail 形态。
#: 契约 v0.15 §7.16.4 的「追加键穷举表」只给了单一变体（7 / 8 / 8 / 8 / 7），**没有 9 键
#: 这一行** —— 9 键 = `status`（FS01 追加）与 `violations`（批量追加）**并存**。已派
#: 架构师出 v0.16 补组合行；本组用例按当前实现钉死形态，**不为了对齐那张表把
#: `violations` 压掉**（表缺行，不是实现多写）。
DETAIL_KEYS_7 = FS03_DETAIL_KEYS
DETAIL_KEYS_8_STATUS = DETAIL_KEYS_7 | {"status"}
DETAIL_KEYS_8_DUAL = DETAIL_KEYS_7 | {"dual_ids"}
DETAIL_KEYS_9 = DETAIL_KEYS_7 | {"status", "violations"}

#: 真盘上 8 个 active canonical（2026-11-08 盘上实测：15 json = 8 active + 7 draft）。
REAL_ACTIVE_IDS = (
    "uf_vol60",
    "uf_ma120",
    "uf_ma200",
    "uf_prior_high_20",
    "uf_prior_high_55",
    "uf_prior_high_250",
    "uf_prior_low_10",
    "uf_prior_vol_20",
)


def _real_source() -> gate.RegistryFacts:
    return gate.RegistryFacts(REAL_DATA_DIR)


@pytest.mark.skipif(not REAL_DATA_DIR.is_dir(), reason="本机无 D:/TSP/data 生产目录")
@pytest.mark.parametrize("alias_id", ["vol60", "ma120", "prior_high_20"])
def test_real_disk_group1_single_alias_is_fs03_with_seven_keys(alias_id) -> None:
    """组 1：单 id alias → FS03，**恰 7 键**（无 status、无 violations）。"""
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable([alias_id], "production", facts=_real_source())
    error = excinfo.value
    assert error.code == "FS03"
    assert set(error.detail) == DETAIL_KEYS_7
    assert len(error.detail) == 7


@pytest.mark.skipif(not REAL_DATA_DIR.is_dir(), reason="本机无 D:/TSP/data 生产目录")
def test_real_disk_group2_single_collision_name_is_fs01_with_eight_keys() -> None:
    """组 2：单 id 撞名 `ma20` → FS01，**8 键**（7 + status）。"""
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["ma20"], "production", facts=_real_source())
    error = excinfo.value
    assert error.code == "FS01"
    assert set(error.detail) == DETAIL_KEYS_8_STATUS
    assert len(error.detail) == 8
    assert "violations" not in error.detail


@pytest.mark.skipif(not REAL_DATA_DIR.is_dir(), reason="本机无 D:/TSP/data 生产目录")
def test_real_disk_group3_dual_id_is_fs04_with_eight_keys() -> None:
    """组 3：双 id `vol60` + `uf_vol60` → FS04，**8 键**（7 + dual_ids）。"""
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["vol60", "uf_vol60"], "production", facts=_real_source())
    error = excinfo.value
    assert error.code == "FS04"
    assert set(error.detail) == DETAIL_KEYS_8_DUAL
    assert error.detail["dual_ids"] == ["vol60", "uf_vol60"]


@pytest.mark.skipif(not REAL_DATA_DIR.is_dir(), reason="本机无 D:/TSP/data 生产目录")
def test_real_disk_group4_two_ids_both_fs01_is_nine_keys() -> None:
    """组 4：2 个不同 id 都 FS01 → FS01，**9 键**（status + violations 并存）。"""
    ids = ["uf_dist_prior_high_250", "cf_auction_resonance"]
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(ids, "production", facts=_real_source())
    error = excinfo.value
    assert error.code == "FS01"
    assert set(error.detail) == DETAIL_KEYS_9
    assert len(error.detail) == 9
    assert error.detail["status"] is not None  # 两个都是 draft，不是 None
    assert [row["submitted_id"] for row in error.detail["violations"]] == ids
    assert [row["code"] for row in error.detail["violations"]] == ["FS01", "FS01"]


@pytest.mark.skipif(not REAL_DATA_DIR.is_dir(), reason="本机无 D:/TSP/data 生产目录")
def test_real_disk_group5_first_fs01_then_fs03_is_nine_keys() -> None:
    """组 5：2 个不同 id，首码 FS01 / 次码 FS03 → FS01，**9 键**。"""
    ids = ["uf_dist_prior_high_250", "vol60"]
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(ids, "production", facts=_real_source())
    error = excinfo.value
    assert error.code == "FS01"
    assert set(error.detail) == DETAIL_KEYS_9
    assert [row["code"] for row in error.detail["violations"]] == ["FS01", "FS03"]


@pytest.mark.skipif(not REAL_DATA_DIR.is_dir(), reason="本机无 D:/TSP/data 生产目录")
def test_real_disk_group6_three_ids_is_nine_keys() -> None:
    """组 6：3 个不同 id（FS01 + FS01 + FS03）→ FS01，**9 键**（键数不随 id 数增长）。"""
    ids = ["uf_dist_prior_high_250", "cf_auction_resonance", "vol60"]
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(ids, "production", facts=_real_source())
    error = excinfo.value
    assert error.code == "FS01"
    assert set(error.detail) == DETAIL_KEYS_9
    assert len(error.detail["violations"]) == 3


@pytest.mark.skipif(not REAL_DATA_DIR.is_dir(), reason="本机无 D:/TSP/data 生产目录")
def test_real_disk_group7_fs04_wins_and_violations_absent() -> None:
    """组 7：FS04 + 第 3 个不同 id → FS04，**8 键**（FS04 优先时 `violations` 不出现）。"""
    ids = ["vol60", "uf_vol60", "uf_dist_prior_high_250"]
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(ids, "production", facts=_real_source())
    error = excinfo.value
    assert error.code == "FS04"
    assert set(error.detail) == DETAIL_KEYS_8_DUAL
    assert "violations" not in error.detail
    assert "status" not in error.detail


@pytest.mark.skipif(not REAL_DATA_DIR.is_dir(), reason="本机无 D:/TSP/data 生产目录")
def test_real_disk_detail_key_shape_is_intentional_design() -> None:
    """设计说明（不是新契约）：9 键 = FS01 的 `status` 与批量的 `violations` **并存**；

    `FS04` 优先时 `violations` 不出现（`_guard_dual_id` 在 violations 计算之前抛）。
    这两条是有意设计，不是「多写了键」：`status` 跟最终 code 走（§7.16.4 去重条），
    `violations` 跟「>=2 个不同 id」走（§7.16.4 批量条），两个条件互不排斥。
    """
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(
            ["uf_dist_prior_high_250", "cf_auction_resonance"], "production", facts=_real_source()
        )
    both = set(excinfo.value.detail)
    assert {"status", "violations"} <= both
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(
            ["vol60", "uf_vol60", "uf_dist_prior_high_250"], "production", facts=_real_source()
        )
    dual = set(excinfo.value.detail)
    assert {"status", "violations"}.isdisjoint(dual)


# ---------------------------------- 缺省事实源必须绑定 data_dir（P0，2026-11-08 返工）
@pytest.mark.skipif(not REAL_DATA_DIR.is_dir(), reason="本机无 D:/TSP/data 生产目录")
def test_default_facts_source_binds_settings_data_dir_and_sees_active() -> None:
    """P0 回归：不传 facts / 显式 None / 显式 Path 三种形态结论必须逐项相同。

    缺陷原样：`RegistryFacts()` 不带 data_dir → `_load_definitions()` 返回 `{}` →
    `status=None` → 8 只 **active** 被全判 `FS01`，静默停产。
    """
    default_source = gate.default_facts_source()
    assert default_source._data_dir is not None, "缺省事实源没绑定 data_dir（P0 回归）"

    explicit = gate.RegistryFacts(REAL_DATA_DIR)
    for mode in ("production", "research", "diagnostic"):
        omitted = gate.assert_factors_usable(list(REAL_ACTIVE_IDS), mode)
        none_kwarg = gate.assert_factors_usable(list(REAL_ACTIVE_IDS), mode, facts=None)
        with_path = gate.assert_factors_usable(list(REAL_ACTIVE_IDS), mode, facts=explicit)
        assert omitted == none_kwarg == with_path
        assert omitted.ok is True, f"{mode} 下 8 只 active 应为 ok=True：{omitted.blocked}"
        assert omitted.blocked == ()


@pytest.mark.skipif(not REAL_DATA_DIR.is_dir(), reason="本机无 D:/TSP/data 生产目录")
def test_default_source_reads_eight_active_and_seven_draft_from_real_disk() -> None:
    """盘上事实对账：15 个 json = 8 active + 7 draft，缺省源必须逐只读对。"""
    source = gate.default_facts_source()
    statuses = {fid: source.facts(fid).status for fid in REAL_STORE_IDS}
    assert sorted(str(value) for value in statuses.values()) == ["active"] * 8 + ["draft"] * 7
    for fid in REAL_ACTIVE_IDS:
        assert statuses[fid] == "active"


def test_default_facts_source_raises_instead_of_empty_source(monkeypatch) -> None:
    """解析不到 data_dir 时**抛 GateError(FS09)**，不得静默退化成空事实源。"""
    import app.config as config_module

    monkeypatch.setattr(config_module.settings, "data_dir", None, raising=False)
    with pytest.raises(gate.GateError) as excinfo:
        gate.default_facts_source()
    error = excinfo.value
    assert error.code == "FS09"
    assert set(error.detail) == FS03_DETAIL_KEYS
    assert error.detail["submitted_id"] == "data_dir"
    assert "data_dir" in error.detail["message"]


def test_assert_factors_usable_uses_the_bound_default_source(monkeypatch) -> None:
    """`facts` 缺省时走 `default_facts_source()`；解析失败即 GateError，绝不静默判 draft。"""
    import app.config as config_module

    monkeypatch.setattr(config_module.settings, "data_dir", None, raising=False)
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["close"], "production")
    assert excinfo.value.code == "FS09"
    assert excinfo.value.detail["submitted_id"] == "data_dir"


# ------------------------------------------ F-A49 缺省源错误的 mode 保真（v0.16 §7.17.5）
@pytest.mark.parametrize("mode", ["production", "research", "diagnostic"])
def test_fa49_1_default_source_error_keeps_callers_mode(monkeypatch, mode: str) -> None:
    """`F-A49-1`：`data_dir` 缺失时 `detail["mode"]` 必须等于**调用方传的 mode**。

    缺陷原样（2026-11-08 03:5x 盘面）：`default_facts_source()` 内部把
    `_invalid_argument("data_dir", "production", ...)` 的 `mode` 写死成 `"production"`，
    于是 `research` / `diagnostic` 调用也报 `mode="production"`（mode 保真 1/3）。
    本用例逐模式断言，**不接受三次同为 "production"**。
    """
    import app.config as config_module

    monkeypatch.setattr(config_module.settings, "data_dir", None, raising=False)
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["ma20"], mode)
    error = excinfo.value
    assert error.code == "FS09"
    assert error.detail["mode"] == mode, (
        f"{mode} 下调用的 detail['mode'] 被改成 {error.detail['mode']!r}（mode 保真失败）"
    )


def test_fa49_1_three_modes_never_collapse_to_production(monkeypatch) -> None:
    """`F-A49-1` 汇总断言：三模式一次取齐，`detail["mode"]` 三者逐一对上、互不相同。"""
    import app.config as config_module

    monkeypatch.setattr(config_module.settings, "data_dir", None, raising=False)
    observed = {}
    for mode in ("production", "research", "diagnostic"):
        with pytest.raises(gate.GateError) as excinfo:
            gate.assert_factors_usable(["ma20"], mode)
        observed[mode] = excinfo.value.detail["mode"]
    assert observed == {
        "production": "production",
        "research": "research",
        "diagnostic": "diagnostic",
    }, f"三模式 detail['mode'] 未逐一对上：{observed}"
    assert len(set(observed.values())) == 3, "三模式 detail['mode'] 塌成同一个值"


@pytest.mark.parametrize("mode", ["production", "research", "diagnostic"])
def test_fa49_2_detail_shape_stays_seven_keys(monkeypatch, mode: str) -> None:
    """`F-A49-2`：`detail` 键集合仍**逐键等于** §7.16.4 固定 7 键，不追加任何键。"""
    import app.config as config_module

    monkeypatch.setattr(config_module.settings, "data_dir", None, raising=False)
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["ma20"], mode)
    error = excinfo.value
    assert set(error.detail) == FS03_DETAIL_KEYS
    assert len(error.detail) == 7
    assert "status" not in error.detail
    assert "violations" not in error.detail
    assert "dual_ids" not in error.detail
    assert error.detail["submitted_id"] == "data_dir"
    assert error.detail["resolved_id"] is None
    assert error.detail["canonical_id"] is None
    assert error.detail["table_row"] is None
    assert error.report is None


def test_fa49_default_source_passes_mode_through_directly() -> None:
    """`F-A49-1` 单元面：`default_facts_source(mode)` 自己透传，不依赖闸门包装。"""
    import app.config as config_module
    from unittest import mock

    with mock.patch.object(config_module.settings, "data_dir", None):
        for mode in ("production", "research", "diagnostic"):
            with pytest.raises(gate.GateError) as excinfo:
                gate.default_facts_source(mode)
            assert excinfo.value.code == "FS09"
            assert excinfo.value.detail["mode"] == mode
            assert set(excinfo.value.detail) == FS03_DETAIL_KEYS
    # 裸调（不给 mode）仍按 production，与 F-A48-3 的判据形状一致
    with mock.patch.object(config_module.settings, "data_dir", None):
        with pytest.raises(gate.GateError) as excinfo:
            gate.default_facts_source()
        assert excinfo.value.detail["mode"] == "production"


def test_fa48_4_no_disk_and_empty_disk_stay_distinguishable(monkeypatch, tmp_path: Path) -> None:
    """`F-A48-4` 不回归：「没看到盘」→FS09(7 键) 与「盘上无 status」→FS01(8 键) 两码不同。"""
    import app.config as config_module

    # ① settings.data_dir = None（没看到盘）
    monkeypatch.setattr(config_module.settings, "data_dir", None, raising=False)
    with pytest.raises(gate.GateError) as no_disk:
        gate.assert_factors_usable(["ma20"], "production")
    # ② data_dir 指向存在但无该 id JSON 的目录（盘上确实没有 status）
    monkeypatch.setattr(config_module.settings, "data_dir", str(tmp_path), raising=False)
    with pytest.raises(gate.GateError) as empty_disk:
        gate.assert_factors_usable(["ma20"], "production")

    assert no_disk.value.code == "FS09"
    assert empty_disk.value.code == "FS01"
    assert no_disk.value.code != empty_disk.value.code, "两种「没有 status」被混判成同码"
    assert len(no_disk.value.detail) == 7
    assert len(empty_disk.value.detail) == 8
    assert "status" not in no_disk.value.detail
    assert empty_disk.value.detail["status"] is None
    assert no_disk.value.detail["submitted_id"] == "data_dir"
    assert empty_disk.value.detail["submitted_id"] == "ma20"
