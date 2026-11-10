"""P0 缺省事实源 + §7.16.4 组合键 7 组：可复跑证据脚本（2026-11-08 返工）。

跑法（在 backend/ 下）：
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe ../research/gate-facts-20261108/evidence_facts_20261108.py

只读：不写 D:/TSP 一个字节，不改任何源码。输出 JSON 到同目录 evidence_facts_20261108.json。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, ".")

from app.factors import gate, store  # noqa: E402

DATA = Path("D:/TSP/data")
ACTIVE = [
    "uf_vol60",
    "uf_ma120",
    "uf_ma200",
    "uf_prior_high_20",
    "uf_prior_high_55",
    "uf_prior_high_250",
    "uf_prior_low_10",
    "uf_prior_vol_20",
]
COMBOS = [
    (["vol60"], "G1_single_alias_vol60"),
    (["ma120"], "G1_single_alias_ma120"),
    (["prior_high_20"], "G1_single_alias_prior_high_20"),
    (["ma20"], "G2_single_collision_ma20"),
    (["vol60", "uf_vol60"], "G3_dual_id"),
    (["uf_dist_prior_high_250", "cf_auction_resonance"], "G4_two_ids_both_FS01"),
    (["uf_dist_prior_high_250", "vol60"], "G5_FS01_then_FS03"),
    (["uf_dist_prior_high_250", "cf_auction_resonance", "vol60"], "G6_three_ids"),
    (["vol60", "uf_vol60", "uf_dist_prior_high_250"], "G7_FS04_plus_third_id"),
]


def sha(path: str) -> tuple[int, str]:
    blob = Path(path).read_bytes()
    return len(blob), hashlib.sha256(blob).hexdigest()


def main() -> int:
    store.load_into_registry(DATA)
    explicit = gate.RegistryFacts(DATA)
    out: dict[str, object] = {
        "contract": "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.15.md §7.16.4",
        "data_dir": str(DATA),
        "facts_forms": {},
        "combo_detail_shapes": {},
        "disk_status": {},
        "default_source": {},
        "file_sizes": {},
    }

    # ---- 1. 三种 facts 形态（P0 回归的主要判据） ----
    for form in ("omitted", "none_kwarg", "explicit_path"):
        row: dict[str, object] = {}
        for mode in ("production", "research", "diagnostic"):
            kw = {}
            if form == "none_kwarg":
                kw = {"facts": None}
            elif form == "explicit_path":
                kw = {"facts": explicit}
            report = gate.assert_factors_usable(list(ACTIVE), mode, **kw)
            row[mode] = {
                "ok": report.ok,
                "blocked": list(report.blocked),
                "non_active": list(report.non_active),
            }
        out["facts_forms"][form] = row

    # ---- 2. 七组 detail 键形态 ----
    for ids, label in COMBOS:
        try:
            gate.assert_factors_usable(ids, "production", facts=explicit)
            out["combo_detail_shapes"][label] = {"outcome": "ok"}
        except gate.GateError as err:
            out["combo_detail_shapes"][label] = {
                "code": err.code,
                "n_keys": len(err.detail),
                "keys": sorted(err.detail),
                "has_status": "status" in err.detail,
                "has_violations": "violations" in err.detail,
                "has_dual_ids": "dual_ids" in err.detail,
            }

    # ---- 3. 盘上 status 对账 ----
    source = gate.default_facts_source()
    out["default_source"]["_data_dir"] = str(getattr(source, "_data_dir", None))
    counts: dict[str, int] = {}
    for path in sorted((DATA / "user_data" / "custom_factors").glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        status = raw.get("status")
        counts[str(status)] = counts.get(str(status), 0) + 1
        out["disk_status"][raw.get("id", path.stem)] = {
            "status": status,
            "version": raw.get("version"),
            "updated_at": raw.get("updated_at"),
            "file_mtime_ns": path.stat().st_mtime_ns,
        }
    out["default_source"]["disk_status_counts"] = counts
    out["default_source"]["active_ids_read_back"] = {
        fid: source.facts(fid).status for fid in ACTIVE
    }

    # ---- 4. 文件指纹（只记录不改动） ----
    for path in (
        "app/factors/gate.py",
        "tests/test_factor_gate.py",
        "app/factors/dsl.py",
        "app/factors/store.py",
        "app/api/backtest.py",
    ):
        size, digest = sha(path)
        out["file_sizes"][path] = {
            "bytes": size,
            "sha256": digest,
            "mtime_ns": os.stat(path).st_mtime_ns,
        }

    (Path(__file__).parent / "evidence_facts_20261108.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: out[k] for k in ("facts_forms", "default_source")},
                     ensure_ascii=False, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
