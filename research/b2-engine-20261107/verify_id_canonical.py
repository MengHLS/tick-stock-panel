"""REFS-CANON: B2 交付里引用的因子 id, 逐个按 ARCH_DECISION_FACTOR_ID_CANONICAL §2.1 分类。

判据:
  1) 交付的实现/formula 引用的每个 id 都必须在注册表里存在 (不得凭空写 id)
  2) 凡属「8 组双 id」中任一口径, 必须引 canonical (uf_*); 引 alias 即 FAIL
  3) 只存在于 pack 一侧的 6 个 (ma20/ma60/sd20/boll_lower/boll_upper/prior_amount_20)
     允许用 pack id, 但必须在 evidence 里标注 pack_only=true

引用面 (实测, 不靠文档):
  - E1 formula 的 referenced factors (从 dsl.compile_formula 取, 与 verify_e1 同源)
  - E3 in_universe 的 dependencies (Provider 声明)
  - dsl.py 新增算子本身不是因子, 不计
只读。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.custom.research_universe_pack.factor_provider import (  # noqa: E402
    IN_UNIVERSE_DEPENDENCIES,
)
from app.factors import dsl  # noqa: E402
from app.factors import registry as R  # noqa: E402

# 架构裁定 §2.1: 8 组双 id (canonical = uf_*)
DOUBLE_ID = {
    "vol60": "uf_vol60",
    "ma120": "uf_ma120",
    "ma200": "uf_ma200",
    "prior_high_20": "uf_prior_high_20",
    "prior_high_55": "uf_prior_high_55",
    "prior_high_250": "uf_prior_high_250",
    "prior_low_10": "uf_prior_low_10",
    "prior_vol_20": "uf_prior_vol_20",
}
# 裁定 §1.2 + brief: 只有 pack 一侧
PACK_ONLY = {"ma20", "ma60", "sd20", "boll_lower", "boll_upper", "prior_amount_20"}

E1_FORMULA = "xs_mean(close > ma60, in_universe)"

R._ensure_factor_providers()
known = {spec.id for spec in R._ordered_specs()}

compiled = dsl.compile_formula(E1_FORMULA)
e1_refs = list(compiled.referenced_factors or ())


def classify(fid: str) -> dict:
    canonical = DOUBLE_ID.get(fid)
    if canonical is not None:
        return {"id": fid, "role": "alias", "must_use": canonical,
                "ok": False, "reason": "双 id 口径不得引 alias"}
    if fid in DOUBLE_ID.values():
        return {"id": fid, "role": "canonical", "pack_only": False, "ok": True}
    return {"id": fid, "role": "single_id", "pack_only": fid in PACK_ONLY,
            "ok": True, "reason": "只有 pack 一侧" if fid in PACK_ONLY else ""}


items = [dict(surface="E1 formula", **classify(f)) for f in e1_refs]
# E3 的 dependencies 是面板列名, 不是因子 id; 单独记录, 不参与 id 判定
dep_cols = sorted(IN_UNIVERSE_DEPENDENCIES)
dep_are_columns = [c for c in dep_cols if c in known]

out = {
    "e1_formula": E1_FORMULA,
    "e1_referenced_factors": e1_refs,
    "items": items,
    "all_ids_known": all(i["id"] in known for i in items),
    "unknown_ids": [i["id"] for i in items if i["id"] not in known],
    "alias_violations": [i["id"] for i in items if i["role"] == "alias"],
    "pack_only_used": [i["id"] for i in items if i.get("pack_only")],
    "e3_dependencies": dep_cols,
    "e3_dependencies_that_are_factor_ids": dep_are_columns,
    "canonical_table_version": "ARCH_DECISION_FACTOR_ID_CANONICAL_20261107.md §2.1",
    "pass": (all(i["ok"] for i in items) and all(i["id"] in known for i in items)),
}
print(json.dumps(out, ensure_ascii=False, indent=1))
(Path(__file__).resolve().parent / "logs" / "id_canonical_20261107.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
)
