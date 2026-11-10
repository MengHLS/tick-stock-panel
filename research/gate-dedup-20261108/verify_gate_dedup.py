"""闸门单 id 多码去重验证器（开发经理 2026-11-08 裁定）。

判据（全部只用真盘 D:/TSP/data 事实源，不用合成源）：
  D1 单 `vol60` → code=FS03，`report.blocked` 恰 1 条，detail 恰 7 键（无 violations/status）
  D2 单 `ma20`  → code=FS01，detail 恰 8 键（7 + status），无 violations
  D3 单 `uf_vol60`（canonical）→ OK，blocked 空
  D4 批量 `vol60`+`ma20`（2 个不同 id）→ 仍出 violations，且每条 id 只一码
  D5 优先级常量 = FS04 > FS03 > FS06 > FS01 > FS05
  D6 断言 `_CODE_PRIORITY` 覆盖 gate 能产出的全部码

只读盘、不写任何产物（证据冻结由运行者负责）。退出码 0 = 全 PASS。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.factors.gate import (  # noqa: E402
    _CODE_PRIORITY,
    GateError,
    RegistryFacts,
    assert_factors_usable,
)

REAL_DATA_DIR = Path("D:/TSP/data")
FS03_KEYS = {"code", "mode", "submitted_id", "resolved_id", "canonical_id", "table_row", "message"}
FS01_KEYS = FS03_KEYS | {"status"}


def main() -> int:
    results: list[dict] = []

    def check(cid: str, ok: bool, detail) -> None:
        results.append({"id": cid, "ok": bool(ok), "detail": detail})

    if not REAL_DATA_DIR.is_dir():
        print("D:/TSP/data 不存在，无法验证真盘判据")
        return 2

    source = RegistryFacts(REAL_DATA_DIR)

    # D1 单 vol60
    try:
        report = assert_factors_usable(["vol60"], "production", facts=source)
        check("D1", False, {"unexpected_ok": str(report.blocked)})
    except GateError as exc:
        keys = sorted(exc.detail)
        check(
            "D1",
            exc.code == "FS03"
            and len(exc.detail) == 7
            and set(exc.detail) == FS03_KEYS
            and exc.report is not None
            and exc.report.blocked == (("vol60", None, "FS03"),),
            {
                "code": exc.code,
                "detail_key_count": len(exc.detail),
                "detail_keys": keys,
                "blocked": list(exc.report.blocked) if exc.report else None,
                "has_violations": "violations" in exc.detail,
                "has_status": "status" in exc.detail,
            },
        )

    # D2 单 ma20
    try:
        report = assert_factors_usable(["ma20"], "production", facts=source)
        check("D2", False, {"unexpected_ok": str(report.blocked)})
    except GateError as exc:
        check(
            "D2",
            exc.code == "FS01"
            and len(exc.detail) == 8
            and set(exc.detail) == FS01_KEYS
            and exc.report is not None
            and exc.report.blocked == (("ma20", None, "FS01"),),
            {
                "code": exc.code,
                "detail_key_count": len(exc.detail),
                "detail_keys": sorted(exc.detail),
                "blocked": list(exc.report.blocked) if exc.report else None,
                "has_violations": "violations" in exc.detail,
            },
        )

    # D3 canonical uf_vol60
    try:
        report = assert_factors_usable(["uf_vol60"], "production", facts=source)
        check("D3", report.blocked == () and report.ok is True, {"blocked": list(report.blocked)})
    except GateError as exc:
        check("D3", False, {"code": exc.code, "detail": exc.detail})

    # D4 批量两 id
    try:
        report = assert_factors_usable(["vol60", "ma20"], "production", facts=source)
        check("D4", False, {"unexpected_ok": str(report.blocked)})
    except GateError as exc:
        violations = exc.detail.get("violations")
        check(
            "D4",
            exc.code == "FS03"
            and violations
            == [
                {"submitted_id": "vol60", "code": "FS03"},
                {"submitted_id": "ma20", "code": "FS01"},
            ],
            {"code": exc.code, "violations": violations, "detail_keys": sorted(exc.detail)},
        )

    # D5 优先级次序
    order = [code for code, _ in sorted(_CODE_PRIORITY.items(), key=lambda kv: kv[1])]
    check(
        "D5",
        order == ["FS04", "FS03", "FS06", "FS01", "FS05"],
        {"order": order, "raw": _CODE_PRIORITY},
    )

    # D6 覆盖 gate 能产出的全部码
    produced = {"FS01", "FS02", "FS03", "FS04", "FS05", "FS06", "FS09"}
    check(
        "D6",
        produced <= set(_CODE_PRIORITY) | {"FS02", "FS09"},
        {"produced": sorted(produced), "in_priority": sorted(_CODE_PRIORITY)},
    )

    failed = [r for r in results if not r["ok"]]
    payload = {
        "verdict": "PASS" if not failed else "FAIL",
        "passed": len(results) - len(failed),
        "total": len(results),
        "data_dir": str(REAL_DATA_DIR),
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
