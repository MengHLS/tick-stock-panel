# -*- coding: utf-8 -*-
"""v5.12 追问：新增 1 个已登记因子，会让哪些 110 断言变红。

只读 + 进程内临时注册（不写盘、不改代码；进程结束即消失）。
口径：先把 factor_columns_view() 调两次到稳定值，再注册 1 个 spec，再测两次。
"""
from __future__ import annotations
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))


def main() -> int:
    from app.factors import registry
    from app.extensions.factors import ensure_factor_providers
    ensure_factor_providers()
    v1 = len(registry.factor_columns_view())
    v2 = len(registry.factor_columns_view())          # 稳定值
    a1 = len(registry.all_factors())
    spec = registry.FactorSpec(
        id="market_breadth_probe",
        formula_text="xs_mean(close > ma60, in_universe)",
        kind="custom",
        label="probe",
        group="probe",
        dependencies=frozenset({"close", "ma60", "in_universe"}),
        warmup_bars=120,
    )
    registry.register_factor(spec)
    v3 = len(registry.factor_columns_view())
    v4 = len(registry.factor_columns_view())
    a2 = len(registry.all_factors())
    out = {
        "view_calls": [v1, v2, v3, v4],
        "view_stable_before": v2, "view_stable_after": v4,
        "delta_view": v4 - v2,
        "all_before": a1, "all_after": a2, "delta_all": a2 - a1,
        "registered_id_present": any(s.id == "market_breadth_probe" for s in registry.all_factors()),
        "note": "view 与 all 是两套口径（110 快照 vs 含动态注册），但两者对「新增 1 个已登记因子」都 +1",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
