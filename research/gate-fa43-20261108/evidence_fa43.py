"""F-A43–F-A47 / FS09 取证脚本（§7.17 判据；只读盘上事实，不写任何产物目录）。

跑法（仓库根）：
    backend/.venv/Scripts/python.exe research/gate-fa43-20261108/evidence_fa43.py
输出：evidence_fa43.json + 标准输出的 markdown 片段（本次交付报告直接引用）。
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

from app.factors import gate  # noqa: E402

GATE = BACKEND / "app" / "factors" / "gate.py"
TESTS = BACKEND / "tests" / "test_factor_gate.py"
STORE = Path(r"D:\TSP\data\user_data\custom_factors")
BEFORE_SNAPSHOT = REPO / "research" / "factor-registration-20261107" / "logs" / "prod_snapshot_before_15_20261107_1630.json"

LIVE_SIGNALS = (
    "boll_breakdown_lower",
    "boll_breakout_upper",
    "ma20_breakdown",
    "ma20_breakout",
    "ma_dead_5_20",
    "ma_golden_20_60",
    "ma_golden_5_20",
)


def file_stats(path: Path) -> dict:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    return {
        "path": str(path.relative_to(REPO)),
        "bytes": len(raw),
        "lines": text.count("\n") + (0 if text.endswith("\n") else 1),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime)),
    }


def signature_dump() -> list[dict]:
    out = []
    for name, p in inspect.signature(gate.assert_factors_usable).parameters.items():
        default = "<empty>" if p.default is inspect.Parameter.empty else repr(p.default)
        out.append({"name": name, "kind": p.kind.name, "default": default, "annotation": str(p.annotation)})
    return out


def per_name_table(ids: list[str]) -> list[dict]:
    source = gate.RegistryFacts()
    column = gate.assert_factors_usable(ids, "production", namespace="column", shadow=True, facts=source)
    factor = gate.assert_factors_usable(ids, "production", shadow=True, facts=source)
    column_map = {row[0]: (row[1], row[2]) for row in column.blocked}
    factor_map = {row[0]: (row[1], row[2]) for row in factor.blocked}
    research = gate.assert_factors_usable(ids, "research", shadow=True, facts=source)
    research_map = {row[0]: (row[1], row[2]) for row in research.blocked}
    rows = []
    for fid in ids:
        fact = source.facts(fid)
        rows.append(
            {
                "id": fid,
                "kind": fact.kind,
                "status": fact.status,
                "lang": fact.lang,
                "registered": fact.registered,
                "column_face": column_map.get(fid),
                "factor_face_production": factor_map.get(fid),
                "factor_face_research": research_map.get(fid),
            }
        )
    return rows


def signal_table() -> list[dict]:
    payload = json.loads(gate.DEFAULT_INVENTORY_PATH.read_text(encoding="utf-8"))
    records = payload["records"]
    source = gate.RegistryFacts()
    rows = []
    for signal in LIVE_SIGNALS:
        ids = sorted(
            {
                str(row["ref_name"])
                for row in records
                if row.get("source_enabled") is True
                and str(row.get("source_path", "")).endswith(f"custom_signals/{signal}.json")
            }
        )
        column = gate.assert_factors_usable(ids, "production", namespace="column", shadow=True, facts=source)
        factor = gate.assert_factors_usable(ids, "production", shadow=True, facts=source)
        rows.append(
            {
                "signal": signal,
                "ids": ids,
                "column_blocked": [list(item) for item in column.blocked],
                "factor_blocked": [list(item) for item in factor.blocked],
            }
        )
    return rows


def store_snapshot() -> list[dict]:
    before = {row["file"]: row for row in json.loads(BEFORE_SNAPSHOT.read_text(encoding="utf-8"))}
    rows = []
    for path in sorted(STORE.glob("*.json")):
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        prev = before.get(path.name)
        rows.append(
            {
                "file": path.name,
                "bytes": len(raw),
                "sha256_now": sha,
                "sha256_before": prev["sha256"] if prev else None,
                "identical": bool(prev and prev["sha256"] == sha),
                "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime)),
            }
        )
    return rows


def symbol_diff() -> dict:
    head = subprocess.run(
        ["git", "show", "HEAD:backend/app/factors/gate.py"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout

    def syms(src: str) -> dict:
        tree = ast.parse(src)
        out = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out[node.name] = type(node).__name__
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        out[target.id] = "Assign"
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                out[node.target.id] = "AnnAssign"
        return out

    old, new = syms(head), syms(GATE.read_text(encoding="utf-8"))
    return {
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "kept": sorted(set(new) & set(old)),
    }


def main() -> int:
    source_text = GATE.read_text(encoding="utf-8")
    ids = list(gate.load_live_config_allowlist().ids)
    evidence = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "contract": "FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md §7.17",
        "files": [file_stats(GATE), file_stats(TESTS)],
        "signature": signature_dump(),
        "constants": {
            "EXEMPT_KINDS": sorted(gate.EXEMPT_KINDS),
            "_NAMESPACES": list(gate._NAMESPACES),
            "column_universe_size": len(gate._column_universe()),
            "not_implemented_error_raises": source_text.count("raise NotImplementedError"),
            "fs09_literal_count": source_text.count("FS09"),
            "production_importers_of_assert_factors_usable": [],
        },
        "live_ids": ids,
        "per_name": per_name_table(ids),
        "signals": signal_table(),
        "store": store_snapshot(),
        "symbols": symbol_diff(),
    }
    app_root = GATE.parents[1]
    evidence["constants"]["production_importers_of_assert_factors_usable"] = [
        str(p.relative_to(app_root))
        for p in app_root.rglob("*.py")
        if p.resolve() != GATE.resolve() and "assert_factors_usable" in p.read_text(encoding="utf-8")
    ]
    out = Path(__file__).with_suffix(".json")
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

    print("== files ==")
    for row in evidence["files"]:
        print(f"{row['path']}: {row['bytes']} B / {row['lines']} 行 / {row['sha256'][:16]}… / {row['mtime']}")
    print("== signature ==")
    for p in evidence["signature"]:
        print(f"  {p['name']}: {p['kind']} default={p['default']}")
    print("== 19 名逐名 ==")
    for row in evidence["per_name"]:
        print(
            f"{row['id']:<22} kind={row['kind']!s:<9} status={row['status']!s:<7} lang={row['lang']!s:<5} "
            f"column={row['column_face']} factor/prod={row['factor_face_production']} factor/research={row['factor_face_research']}"
        )
    print("== store 15 ==")
    for row in evidence["store"]:
        print(f"{row['file']:<42} {row['bytes']:>5} {row['sha256_now'][:12]} identical_to_1630={row['identical']}")
    print("== symbols ==")
    print("added:", evidence["symbols"]["added"])
    print("removed:", evidence["symbols"]["removed"])
    print("callers:", evidence["constants"]["production_importers_of_assert_factors_usable"])
    print("written:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
