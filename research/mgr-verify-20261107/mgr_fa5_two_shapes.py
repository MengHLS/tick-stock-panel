"""开发经理自建 F-A5 复核脚本（不复用被审方脚本）。

构造两种形状：
  disk  = 盘上 json 原样
  api   = 按 api/factors.py:236-243 CustomFactorCreateRequest 的 6 个字段构造（无 lang / kind / status / version）
在全新临时目录跑 upsert_definition，检查 unchanged / version / 字节 / mtime / lang 保留。
生产目录只读，不写。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(REPO / "backend"))

from app.factors import store  # noqa: E402

PROD = Path(r"D:\TSP\data\user_data\custom_factors")
API_FIELDS = ("id", "label", "group", "formula", "description", "direction")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def api_shape(disk: dict) -> dict:
    return {k: disk[k] for k in API_FIELDS if k in disk}


def fresh_tree() -> Path:
    root = Path(tempfile.mkdtemp(prefix="mgrfa5_"))
    (root / "user_data" / "custom_factors").mkdir(parents=True)
    return root


def put(root: Path, src: Path) -> Path:
    tgt = root / "user_data" / "custom_factors" / src.name
    tgt.write_bytes(src.read_bytes())
    return tgt


def state(p: Path) -> dict:
    d = json.loads(p.read_text(encoding="utf-8"))
    return {
        "version": d.get("version"),
        "lang": d.get("lang"),
        "status": d.get("status"),
        "sha": sha(p)[:16],
        "mtime": p.stat().st_mtime_ns,
    }


def run_case(name: str, src_file: Path, payload_fn, times: int = 2):
    root = fresh_tree()
    try:
        tgt = put(root, src_file)
        before = state(tgt)
        results = []
        for _ in range(times):
            payload = payload_fn(json.loads(tgt.read_text(encoding="utf-8")), json.loads(src_file.read_text(encoding="utf-8")))
            results.append(store.upsert_definition(root, payload))
        after = state(tgt)
        print(json.dumps({
            "case": name,
            "before": {k: before[k] for k in ("version", "lang", "status")},
            "after": {k: after[k] for k in ("version", "lang", "status")},
            "unchanged": [r.get("unchanged") for r in results],
            "versions": [r.get("version") for r in results],
            "bytes_same": before["sha"] == after["sha"],
            "mtime_same": before["mtime"] == after["mtime"],
        }, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"case": name, "EXC": type(exc).__name__, "msg": str(exc)[:200]}, ensure_ascii=False))
    finally:
        shutil.rmtree(root, ignore_errors=True)


print("== A: disk shape as-is (all json) ==")
for f in sorted(PROD.glob("*.json")):
    run_case("A:" + f.stem, f, lambda cur, orig: dict(orig))

print("== B: API shape (no lang/kind/status/version) ==")
for f in sorted(PROD.glob("*.json")):
    run_case("B:" + f.stem, f, lambda cur, orig: api_shape(orig))

print("== C: API shape, real formula change by one char ==")


def bump(cur, orig):
    p = api_shape(orig)
    p["formula"] = p["formula"] + " " if not p["formula"].endswith(" ") else p["formula"][:-1]
    return p


run_case("C:uf_ma120_changed", PROD / "uf_ma120.json", bump, times=1)

print("== D: status draft->active via API shape ==")


def activate(cur, orig):
    p = api_shape(orig)
    p["status"] = "active"
    return p


run_case("D:uf_ma120_activate", PROD / "uf_ma120.json", activate, times=1)

print("== E: lang=python definition, same content twice ==")

root = fresh_tree()
try:
    d = {
        "id": "uf_mgr_pytest",
        "kind": "custom",
        "label": "mgr pytest",
        "group": "g",
        "lang": "python",
        "formula": "close - open",
        "description": "",
        "direction": "none",
        "status": "draft",
        "version": 1,
    }
    tgt = root / "user_data" / "custom_factors" / "uf_mgr_pytest.json"
    tgt.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    before = state(tgt)
    r1 = store.upsert_definition(root, api_shape(json.loads(tgt.read_text(encoding="utf-8"))))
    mid = state(tgt)
    r2 = store.upsert_definition(root, api_shape(json.loads(tgt.read_text(encoding="utf-8"))))
    after = state(tgt)
    print(json.dumps({
        "case": "E:python",
        "before": {"version": before["version"], "lang": before["lang"]},
        "after": {"version": after["version"], "lang": after["lang"]},
        "r1": r1, "r2": r2, "mid_lang": mid["lang"],
        "bytes_same": before["sha"] == after["sha"],
    }, ensure_ascii=False))
except Exception as exc:  # noqa: BLE001
    print(json.dumps({"case": "E:python", "EXC": type(exc).__name__, "msg": str(exc)[:300]}, ensure_ascii=False))
finally:
    shutil.rmtree(root, ignore_errors=True)

print("== prod fingerprints after all (must equal before) ==")
print(json.dumps({f.stem: sha(f)[:16] for f in sorted(PROD.glob("*.json"))}, ensure_ascii=False))
