"""test_factor_gate.py 的 F-A43–F-A47 补丁（一次性）。

1) 顶部 import inspect；
2) 两处既有断言按 v0.12 更新（mode 域外 ValueError→FS09；ledger NotImplementedError→FS06）
   —— 这两条的旧断言已被 §7.17.4 C3/C4 明文取代，无法同时保留；
3) 文件末尾追加 F-A43–F-A47 判据块（19 名正样本 / 4 名负样本 / 15 名边界 / 7 条活信号）。
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path("tests/test_factor_gate.py")

EDITS: list[tuple[str, str, str]] = []

EDITS.append((
    "T1-import-inspect",
    """import dataclasses
import json
from pathlib import Path""",
    """import dataclasses
import inspect
import json
from pathlib import Path""",
))

EDITS.append((
    "T2-unknown-mode",
    '''def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ValueError):
        gate.assert_factors_usable(["x"], "prodcution", shadow=True, facts=gate.MappingFacts({}))''',
    '''def test_unknown_mode_is_rejected() -> None:
    """§7.17.4 C4（v0.12）：mode 域外由 ValueError 改判 `FS09`（`GateError` → HTTP 400）。

    旧断言押 ValueError，已被 §7.17.4「入参非法 → `FS09`」与 C1「`ValueError` 不得
    逃出闸门」明文取代；此处只改「异常类型 + 错误码」的期待，不放宽任何强度。
    """
    with pytest.raises(gate.GateError) as excinfo:
        gate.assert_factors_usable(["x"], "prodcution", shadow=True, facts=gate.MappingFacts({}))
    assert excinfo.value.code == "FS09"
    assert excinfo.value.detail["submitted_id"] == "mode"''',
))

EDITS.append((
    "T3-ledger",
    '''def test_ledger_consistency_check_is_explicitly_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        gate.check_ledger_consistency()''',
    '''def test_ledger_consistency_check_fails_closed_with_fs06() -> None:
    """§7.17.4 C3（v0.12）：台账判不出来 → `GateError(FS06)`，不再抛 `NotImplementedError`。

    旧断言押 NotImplementedError，已被 C1「出口唯一」与 C3「FS06 fail-closed」明文取代。
    """
    with pytest.raises(gate.GateError) as excinfo:
        gate.check_ledger_consistency()
    assert excinfo.value.code == "FS06"
    assert set(excinfo.value.detail) == FS03_DETAIL_KEYS
    assert excinfo.value.report is None''',
))

for name, old, new in EDITS:
    raw = TARGET.read_bytes().decode("utf-8")
    text = raw.replace("\r\n", "\n")
    break

for name, old, new in EDITS:
    count = text.count(old)
    if count != 1:
        print(f"[FAIL] {name}: matched {count}", flush=True)
        sys.exit(1)
    text = text.replace(old, new)
    print(f"[ok] {name}", flush=True)

BLOCK = '''

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
    """F-A44-3：另外 15 名逐 id 结论不变，本次改动只应改变那 4 个 id。"""
    ids = _live_ids()
    before = _blocked_map(ids, "production")
    after = _blocked_map(ids, "production", namespace="column")
    assert set(before) - set(after) == set(NAMESPACE_NEGATIVE_IDS)
    assert set(after) == set()
    for factor_id in ids:
        if factor_id in NAMESPACE_NEGATIVE_IDS:
            continue
        assert before.get(factor_id) == after.get(factor_id), factor_id


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
    assert gate.EXEMPT_KINDS == frozenset({"base", "virtual"})


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
'''

text = text.rstrip("\n") + BLOCK
TARGET.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
print(f"[done] {TARGET} {TARGET.stat().st_size} B", flush=True)
