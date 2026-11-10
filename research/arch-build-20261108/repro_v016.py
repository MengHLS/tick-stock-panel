#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""v0.16 取证复跑入口（架构师，2026-11-08 04:4x）。

只读 D:/TSP/data 与仓库内文件；不写 backend/**、不写 docs/factors/**、不提交。

用法：
    cd C:/work/sourcecode/tick-stock-panel
    PYTHONIOENCODING=utf-8 python research/arch-build-20261108/repro_v016.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    ev = json.loads((REPO / "research/arch-build-20261108/EVIDENCE_v016.json")
                    .read_text(encoding="utf-8"))
    matrix = ev["gap1_matrix"]
    base = set(ev["base_keys"])

    with_detail = [r for r in matrix if "keys" in r]
    no_detail = [r for r in matrix if "keys" not in r]

    bad = []
    for r in with_detail:
        keys = set(r["keys"])
        code = r["code"]
        dn = r["distinct_blocked"]
        extra = keys - base
        cs = code == "FS01"
        cd = code == "FS04"
        cv = (code != "FS04") and dn >= 2
        pred = 7 + int(cs) + int(cv) + int(cd)
        exp = ({"status"} if cs else set()) | \
              ({"violations"} if cv else set()) | \
              ({"dual_ids"} if cd else set())
        if not (pred == len(keys) == r["n_keys"] and extra == exp):
            bad.append({
                "label": r["label"], "mode": r["mode"], "code": code,
                "distinct_blocked": dn, "observed_keys": len(keys),
                "predicted": pred, "extra": sorted(extra), "expected": sorted(exp),
            })

    print("=" * 78)
    print("v0.16 取证复跑（算法 |detail| = 7 + |{status, violations, dual_ids} ∩ 实产键|）")
    print("=" * 78)
    print(f"总调用            : {len(matrix)}（14 组输入 × 3 模式）")
    print(f"抛 GateError 带 detail : {len(with_detail)}")
    print(f"diagnostic 放行不产 detail : {len(no_detail)}")
    print(f"键数实际取值      : {sorted({r['n_keys'] for r in with_detail})}")
    print(f"算法成立          : {len(with_detail) - len(bad)}/{len(with_detail)}")
    print(f"不成立明细        : {bad if bad else '无'}")
    print()
    print("§7.16.4 固定 7 键:", sorted(base), f"（{len(base)} 个）")
    print("─" * 78)

    ok = not bad and len(matrix) == 42 and sorted({r["n_keys"] for r in with_detail}) == [7, 8, 9]
    print("RESULT:", "ALGORITHM HOLDS ON ALL WITH-DETAIL CALLS" if ok else "MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
