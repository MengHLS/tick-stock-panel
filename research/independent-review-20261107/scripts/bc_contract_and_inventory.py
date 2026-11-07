#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""独立审核脚本 B+C：契约 v0.4 完整性与自洽 + 存量 draft 盘点。

只读。不写 D:\\TSP；不调用 f_class_parity.py；不 import 被审方的任何脚本。
运行：backend/.venv/Scripts/python.exe -X utf8 research/independent-review-20261107/scripts/bc_contract_and_inventory.py
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

LIVE = ROOT / "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md"
ARCH = ROOT / "docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md"
CUSTOM_DIR = Path(r"D:\TSP\data\user_data\custom_factors")

FROZEN = {
    "bytes": 89833,
    "lines": 914,
    "sha256": "5eb9772411f723576b657f85af7c0aa26427137a41fb53b5774b935942565903",
    "body_prefix_bytes": 89350,
    "body_prefix_sha256": "b082d902e08df2dc902f97d694dcd2e1ae96d93bd79485a66647470915f9bfef",
}

out: dict[str, object] = {}


def rec(k: str, v) -> None:
    out[k] = v
    print(f"{k}: {v}")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ───────────────────────────── B1 归档副本逐字节
def b1() -> None:
    ab = ARCH.read_bytes()
    al = len(ab.decode("utf-8").splitlines())
    rec("B1_archive_bytes", len(ab))
    rec("B1_archive_lines", al)
    rec("B1_archive_sha256", sha(ab))
    rec("B1_archive_mtime", str(ARCH.stat().st_mtime))
    rec("B1_bytes_match_frozen", len(ab) == FROZEN["bytes"])
    rec("B1_lines_match_frozen", al == FROZEN["lines"])
    rec("B1_sha_match_frozen", sha(ab) == FROZEN["sha256"])
    body = ab[: FROZEN["body_prefix_bytes"]]
    rec("B1_body_prefix_sha256", sha(body))
    rec("B1_body_prefix_match", sha(body) == FROZEN["body_prefix_sha256"])

    lb = LIVE.read_bytes()
    rec("B1_live_bytes", len(lb))
    rec("B1_live_lines", len(lb.decode("utf-8").splitlines()))
    rec("B1_live_sha256", sha(lb))
    rec("B1_live_version_header", lb.decode("utf-8").splitlines()[0])


# ───────────────────────────── B2 §7.1 逐字未变
def section(text: str, start: str, end: str) -> str:
    i = text.index(start)
    j = text.index(end, i)
    return text[i:j]


def b2() -> None:
    v3 = ARCH.read_text(encoding="utf-8")
    v4 = LIVE.read_text(encoding="utf-8")
    s3 = section(v3, "### 7.1 实测结论", "### 7.2 注册元数据字段")
    s4 = section(v4, "### 7.1 实测结论", "### 7.2 注册元数据字段")
    rec("B2_s71_len_v3", len(s3))
    rec("B2_s71_len_v4", len(s4))
    rec("B2_s71_sha_v3", sha(s3.encode()))
    rec("B2_s71_sha_v4", sha(s4.encode()))
    rec("B2_s71_identical", s3 == s4)
    r3 = [ln for ln in s3.splitlines() if ln.startswith("| `") and "ts_" in ln]
    r4 = [ln for ln in s4.splitlines() if ln.startswith("| `") and "ts_" in ln]
    rec("B2_formula_rows_v3", len(r3))
    rec("B2_formula_rows_v4", len(r4))
    rec("B2_formula_rows_identical", r3 == r4)
    # 抽出 8 行里的 formula / warmup 做机械断言
    parsed = []
    for ln in r4:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        parsed.append({"id": cells[0].strip("`"), "formula": cells[1].strip("`"),
                       "warmup": cells[2].strip("*").strip(), "deps": cells[3].strip("`")})
    rec("B2_rows_parsed", parsed)


# ───────────────────────────── B3 §7.4 vs §7.6 F-A5
def b3() -> None:
    v4 = LIVE.read_text(encoding="utf-8")
    s74 = section(v4, "### 7.4 幂等", "### 7.5 禁止事项")
    s76 = section(v4, "### 7.6 验收判据", "### 7.7 ")
    rec("B3_s74_mentions_old_prohibition", "不动 store" in s74)
    rec("B3_s74_replaces_old", "替换 v0.3 的「不动 store」" in s74)
    rec("B3_s74_self_consistency_clause", "不构成对 §7.4 的违例" in s74)
    rec("B3_s76_says_allowed_surface", "该实现属 §7.4 v0.4 允许面" in s76)
    rec("B3_s74_declared_allowed_funcs",
        [n for n in ("content_signature", "is_same_content", "upsert_definition") if n in s74])
    # 契约引用的行号 vs 实际行号
    st = (ROOT / "backend/app/factors/store.py").read_text(encoding="utf-8").splitlines()
    def find_def(name: str) -> int:
        for i, ln in enumerate(st, 1):
            if ln.startswith(f"def {name}("):
                return i
        return -1
    actual = {n: find_def(n) for n in
              ("content_signature", "is_same_content", "_merge_for_write", "upsert_definition",
               "load_one", "register_definition", "load_into_registry")}
    rec("B3_store_actual_line_numbers", actual)
    cited = [int(m) for m in re.findall(r"store\.py:(\d+)", s74)]
    rec("B3_store_cited_line_numbers", cited)
    rec("B3_citation_content_signature_ok", cited[0] == actual["content_signature"] if cited else None)
    # 差分实际改动面（函数级）
    rec("B3_actual_new_store_symbols",
        ["load_one", "_canonical", "content_signature", "is_same_content",
         "_merge_for_write", "upsert_definition"])


# ───────────────────────────── B4 F-A7 必然 FAIL
def b4() -> None:
    from app.factors.registry import FactorSpec
    fields = [f.name for f in dataclasses.fields(FactorSpec)]
    rec("B4_FactorSpec_field_count", len(fields))
    rec("B4_FactorSpec_has_status", "status" in fields)
    rec("B4_gate_py_exists", (ROOT / "backend/app/factors/gate.py").exists())
    rec("B4_factors_dir", sorted(p.name for p in (ROOT / "backend/app/factors").iterdir()
                                if p.is_file()))
    # 代码面符号扫描（不含注释/docstring 区分，只做存在性）
    pats = ["assert_factors_usable", "GateReport", "alias_of", "FS01", "FS02", "FS03",
            "FS04", "FS05", "FS06", "superseded_by", "deprecated_alias_used", "resolved_id"]
    hits = {}
    for p in (ROOT / "backend/app").rglob("*.py"):
        try:
            t = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in pats:
            if pat in t:
                hits.setdefault(pat, []).append(str(p.relative_to(ROOT)))
    rec("B4_symbol_hits", {k: len(v) for k, v in hits.items()})
    rec("B4_symbol_hit_files", hits)


# ───────────────────────────── B5 §7.8 FS03–FS06 / alias
def b5() -> None:
    rec("B5_fs03_fs06_implemented", out["B4_symbol_hits"].get("FS03", 0) > 0)
    rec("B5_alias_of_implemented", out["B4_symbol_hits"].get("alias_of", 0) > 0)
    rec("B5_note", "0 命中 = §7.8 仅条款、无实现；F-A14–F-A17 全部不可判")


# ───────────────────────────── 注册表两态 + pack
def registry_two_state() -> None:
    from app.config import settings
    from app.factors import store
    from app.factors.registry import all_factors, get_factor
    rec("R_unloaded_all_factors", len(all_factors()))
    pack = ["ma20", "ma60", "boll_lower", "boll_upper", "sd20", "prior_high_20",
            "prior_low_10", "prior_high_55", "prior_vol_20", "ma120", "vol60",
            "prior_high_250", "prior_amount_20", "ma200"]
    present = [p for p in pack if get_factor(p) is not None]
    rec("R_pack_present", len(present))
    rec("R_pack_detail", {
        p: {"kind": get_factor(p).kind, "lang": getattr(get_factor(p), "lang", None),
            "warmup": get_factor(p).warmup_bars, "stability": get_factor(p).stability,
            "formula": get_factor(p).formula_text} for p in present})
    loaded = store.load_into_registry(Path(settings.data_dir))
    rec("R_loaded_ids", sorted(loaded))
    rec("R_loaded_count", len(loaded))
    rec("R_after_all_factors", len(all_factors()))
    rec("R_uf_vol60_has_status", hasattr(get_factor("uf_vol60"), "status"))
    rec("R_pack_ma20_has_status", hasattr(get_factor("ma20"), "status"))


# ───────────────────────────── C 存量盘点
def c_inventory() -> None:
    rows = []
    for fn in sorted(os.listdir(CUSTOM_DIR)):
        p = CUSTOM_DIR / fn
        b = p.read_bytes()
        j = json.loads(b.decode("utf-8"))
        rows.append({
            "file": fn, "id": j.get("id"), "kind": j.get("kind"),
            "status": j.get("status"), "version": j.get("version"),
            "lang": j.get("lang"), "bytes": len(b), "sha256": sha(b),
            "mtime": str(p.stat().st_mtime),
        })
    rec("C_file_count", len(rows))
    rec("C_inventory", rows)
    rec("C_status_values", sorted({r["status"] for r in rows}))
    rec("C_active_count", sum(1 for r in rows if r["status"] == "active"))
    rec("C_draft_count", sum(1 for r in rows if r["status"] == "draft"))
    rec("C_no_lang", [r["id"] for r in rows if r["lang"] is None])
    rec("C_version_gt1", [r["id"] for r in rows if (r["version"] or 0) > 1])
    # 生产口径：store 侧 15 全 draft + pack 侧 14 无 status → 生产可用 0
    rec("C_production_usable_store", sum(1 for r in rows if r["status"] == "active"))
    rec("C_production_usable_pack", 0)


def main() -> int:
    b1(); b2(); b3(); b4(); b5(); registry_two_state(); c_inventory()
    p = Path(__file__).resolve().parents[1] / "artifacts" / "bc_results.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nartifact: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
