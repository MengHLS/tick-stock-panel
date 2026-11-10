"""因子门: ma20 / ma60 / momentum_20d / in_universe 的 canonical id 实测。

产出 research/s01-serial-20261108/gate_factor.json:
- 每个 id: 注册出处、kind、warmup、get_factor 是否可得
- 闸门: mode=production / namespace=factor（因子面）与 namespace=column（列面）两面的 code 序列
不改任何代码，只调用既有闸门 API。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

from app.factors import registry  # noqa: E402
from app.factors.gate import GateError, assert_factors_usable  # noqa: E402

IDS = ["ma20", "ma60", "momentum_20d", "in_universe"]

out: dict = {"ids": {}, "gate": {}, "evidence": {}}
for fid in IDS:
    spec = registry.get_factor(fid)
    out["ids"][fid] = None if spec is None else {
        "id": spec.id,
        "label": getattr(spec, "label", None),
        "group": getattr(spec, "group", None),
        "kind": getattr(spec, "kind", None),
        "warmup_bars": getattr(spec, "warmup_bars", None),
        "formula": getattr(spec, "formula_text", None) or getattr(spec, "formula", None),
        "provider": getattr(spec, "provider_id", None),
    }

for ns in ("factor", "column"):
    row = {}
    for fid in IDS:
        try:
            rep = assert_factors_usable([fid], "production", namespace=ns)
            row[fid] = {"pass": True, "codes": list(rep.codes())}
        except GateError as exc:
            row[fid] = {"pass": False, "codes": list(exc.report.codes()), "detail": exc.to_detail()}
        except Exception as exc:  # 参数错误等
            row[fid] = {"pass": False, "error": f"{type(exc).__name__}: {exc}"}
    out["gate"][ns] = row

(HERE / "gate_factor.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
