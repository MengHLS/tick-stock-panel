"""F-A49-1 可复跑证据：v0.16 §7.17.5 `detail["mode"]` 保真 + F-A49-2 七键 + F-A48-4 两码。

用法（在 backend/ 下）：
    .venv/Scripts/python.exe ../research/gate-facts-20261108/evidence_fa49.py

只读：不写盘、不改任何文件；`cfg.settings.data_dir` 的改动只在本进程内。
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

import app.config as cfg  # noqa: E402
import app.main  # noqa: E402,F401  (启动装配，注册全部 provider)
from app.factors.gate import (  # noqa: E402
    GateError,
    RegistryFacts,
    assert_factors_usable,
    default_facts_source,
)

SEVEN = {
    "code",
    "mode",
    "submitted_id",
    "resolved_id",
    "canonical_id",
    "table_row",
    "message",
}
MODES = ("production", "research", "diagnostic")


def sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main() -> int:
    out: dict = {
        "gate_py_sha16": sha16(BACKEND / "app/factors/gate.py"),
        "test_factor_gate_sha16": sha16(BACKEND / "tests/test_factor_gate.py"),
    }
    saved = cfg.settings.data_dir
    try:
        # --- F-A49-1 闸门面：三模式 mode 必须逐一对上且互不相同 ---
        cfg.settings.data_dir = None
        per_mode = {}
        for mode in MODES:
            try:
                assert_factors_usable(["close"], mode)
                per_mode[mode] = {"raised": False}
            except GateError as exc:
                d = exc.detail
                per_mode[mode] = {
                    "raised": True,
                    "code": exc.code,
                    "detail_mode": d["mode"],
                    "key_count": len(d),
                    "keys_equal_seven": set(d) == SEVEN,
                    "submitted_id": d["submitted_id"],
                    "resolved_id": d["resolved_id"],
                    "canonical_id": d["canonical_id"],
                    "table_row": d["table_row"],
                }
        out["fa49_1_gate"] = per_mode
        out["fa49_1_mode_matches_caller"] = all(
            per_mode[m].get("detail_mode") == m for m in MODES
        )
        out["fa49_1_three_distinct"] = (
            len({per_mode[m].get("detail_mode") for m in MODES}) == 3
        )

        # --- F-A49-1 单元面：default_facts_source(mode) 直接透传 ---
        unit = {}
        for mode in MODES:
            try:
                default_facts_source(mode)
                unit[mode] = {"raised": False}
            except GateError as exc:
                unit[mode] = {"raised": True, "detail_mode": exc.detail["mode"]}
        out["fa49_1_unit"] = unit
        out["fa49_1_unit_ok"] = all(unit[m].get("detail_mode") == m for m in MODES)

        # --- F-A49-2：7 键、无 violations ---
        out["fa49_2_all_seven_keys"] = all(
            v.get("keys_equal_seven") for v in per_mode.values()
        )
        out["fa49_2_no_violations"] = True  # 键集相等即证明未追加

        # --- F-A48-4 两码必须不同 ---
        with tempfile.TemporaryDirectory() as td:
            try:
                assert_factors_usable(
                    ["ma20"], "production", facts=RegistryFacts(Path(td))
                )
                empty_dir = {"raised": False}
            except GateError as exc:
                empty_dir = {
                    "raised": True,
                    "code": exc.code,
                    "key_count": len(exc.detail),
                    "has_status": "status" in exc.detail,
                }
        cfg.settings.data_dir = None
        try:
            assert_factors_usable(["ma20"], "production")
            no_datadir = {"raised": False}
        except GateError as exc:
            no_datadir = {
                "raised": True,
                "code": exc.code,
                "key_count": len(exc.detail),
                "has_status": "status" in exc.detail,
            }
        out["fa48_4_empty_dir"] = empty_dir
        out["fa48_4_no_data_dir"] = no_datadir
        out["fa48_4_codes_differ"] = (
            empty_dir.get("code") != no_datadir.get("code")
            and empty_dir.get("code") == "FS01"
            and no_datadir.get("code") == "FS09"
        )
    finally:
        cfg.settings.data_dir = saved

    checks = [
        out["fa49_1_mode_matches_caller"],
        out["fa49_1_three_distinct"],
        out["fa49_1_unit_ok"],
        out["fa49_2_all_seven_keys"],
        out["fa48_4_codes_differ"],
    ]
    out["all_pass"] = all(checks)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
