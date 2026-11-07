"""F-A47-1 / F-A47-3 路由层最小证据 + `gate.py` 写盘=0 静态证明（2026-11-08）。

跑法（仓库根）：
    backend/.venv/Scripts/python.exe research/gate-fa43-20261108/evidence_route_20261108.py

约定：
* **不起服务**。ASGI 在进程内用 `TestClient` 打；探针 app、探针 handler 都只在本脚本
  里构造，`backend/app/**` 一行未改（§7.17.6 接线约束：接线不在本单）。
* 只读盘上事实：15 个生产 `custom_factors/*.json` 前后取 sha256 + mtime，验证闸门
  全量跑一遍后 0 字节变化。

输出：evidence_route_20261108.json + 标准输出摘要（交付报告直接引用）。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402

from app.factors import gate  # noqa: E402

GATE = BACKEND / "app" / "factors" / "gate.py"
APP_DIR = BACKEND / "app"
STORE = Path(r"D:\TSP\data\user_data\custom_factors")

NS = "F-A47"  # 报告前缀，便于逐条对照


# --------------------------------------------------------------- 工具


def files_under(root: Path):
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def count_matches(paths, pattern: str) -> dict:
    """逐文件 `re.finditer` 计数（等价 grep -c，但不依赖 shell 里的 grep）。"""
    rx = re.compile(pattern)
    per_file: dict[str, int] = {}
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits = len(rx.findall(text))
        if hits:
            per_file[str(path.relative_to(REPO))] = hits
    return {"total": sum(per_file.values()), "files": per_file}


def snapshot_json_dir(path: Path) -> dict:
    rows = {}
    for item in sorted(path.glob("*.json")):
        raw = item.read_bytes()
        rows[item.name] = {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "mtime_ns": item.stat().st_mtime_ns,
        }
    return rows


def comparable(snapshot: dict) -> dict:
    return {k: (v["bytes"], v["sha256"], v["mtime_ns"]) for k, v in snapshot.items()}


def check(results: list, name: str, ok: bool, detail) -> None:
    results.append({"check": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)


# --------------------------------------------------------------- A 静态接线面


def static_wiring(results: list) -> dict:
    outside = [p for p in files_under(APP_DIR) if p.resolve() != GATE.resolve()]
    calls = count_matches(outside, r"\bassert_factors_usable\s*\(")
    errs = count_matches(outside, r"\bGateError\b")
    handlers = count_matches(outside, r"add_exception_handler|exception_handler")
    handler_gate = count_matches(outside, r"exception_handler[^\n]*GateError|GateError[^\n]*exception_handler")

    check(results, f"{NS}-静态/1 assert_factors_usable 生产调用点（backend/app 排除 gate.py）", calls["total"] == 0, calls)
    check(results, f"{NS}-静态/2 GateError 在 backend/app 其它文件的引用数", errs["total"] == 0, errs)
    check(results, f"{NS}-静态/3 现有 exception_handler 注册（其它文件）", True, handlers)
    check(results, f"{NS}-静态/4 把 GateError 注册成 handler 的行", handler_gate["total"] == 0, handler_gate)

    gate_text = GATE.read_text(encoding="utf-8")
    nie = len(re.findall(r"raise\s+NotImplementedError", gate_text))
    check(results, f"{NS}-2 (F-A47-2) gate.py 内 raise NotImplementedError 条数", nie == 0, nie)

    return {"calls": calls, "gate_error_refs": errs, "handlers": handlers}


# --------------------------------------------------------------- B 类型事实


def type_facts(results: list) -> dict:
    facts = {
        "GateError_is_Exception": issubclass(gate.GateError, Exception),
        "GateError_is_fastapi_HTTPException": issubclass(gate.GateError, HTTPException),
        "GateError_is_starlette_HTTPException": issubclass(gate.GateError, StarletteHTTPException),
        "mro": [c.__name__ for c in gate.GateError.__mro__],
    }
    check(
        results,
        f"{NS}-类型/1 GateError 是否是 HTTP 异常（决定 FastAPI 是否自动 400）",
        facts["GateError_is_Exception"] and not facts["GateError_is_starlette_HTTPException"],
        facts,
    )
    return facts


# --------------------------------------------------------------- C 路由层探针


def _dual_detail() -> dict:
    """与 `gate._detail("FS04", ...)` 同形的 detail（含 `dual_ids`）。"""
    return gate._detail(
        "FS04",
        "production",
        "vol60",
        "vol60",
        None,
        None,
        "同一策略内混用同口径两个 id: vol60 / uf_vol60 都指向 vol60",
    ) | {"dual_ids": ["vol60", "uf_vol60"]}


def _report() -> gate.GateReport:
    return gate.GateReport(
        ok=False,
        blocked=(("vol60", None, "FS04"),),
        non_active=(),
        unknown=(),
        mode="production",
        historical_only=False,
    )


def route_probe(results: list) -> dict:
    out: dict = {}

    # --- C1：今日 app 的形状 = 无 handler，路由里抛 GateError
    app_raw = FastAPI()

    @app_raw.get("/gate-error")
    def _raise_gate_error():
        raise gate.GateError("FS04", _dual_detail(), _report(), entry="probe")

    @app_raw.get("/runtime-error")
    def _raise_runtime_error():
        raise RuntimeError("注入的运行时错误")

    with TestClient(app_raw, raise_server_exceptions=False) as client:
        r_gate = client.get("/gate-error")
        r_runtime = client.get("/runtime-error")
    out["unmapped"] = {"gate_error": r_gate.status_code, "runtime_error": r_runtime.status_code}
    check(
        results,
        f"{NS}-路由/1 无 handler 时 GateError 的 HTTP 状态（今日 app 若接线就是这个数）",
        r_gate.status_code == 500,
        f"GateError -> {r_gate.status_code}；RuntimeError -> {r_runtime.status_code}",
    )

    # --- C2：按 §7.16.6 / F-A47 契约最小映射（只在探针 app 内，未落 app/**）
    app_map = FastAPI()

    @app_map.exception_handler(gate.GateError)
    def _gate_error_handler(_request, exc: gate.GateError):  # noqa: ANN001
        return JSONResponse(status_code=400, content={"detail": exc.detail})

    @app_map.get("/gate-error")
    def _raise_gate_error_mapped():
        raise gate.GateError("FS04", _dual_detail(), _report(), entry="probe")

    @app_map.get("/runtime-error")
    def _raise_runtime_error_mapped():
        raise RuntimeError("注入的运行时错误")

    with TestClient(app_map, raise_server_exceptions=False) as client:
        r_gate_m = client.get("/gate-error")
        r_runtime_m = client.get("/runtime-error")

    body = r_gate_m.json() if r_gate_m.headers.get("content-type", "").startswith("application/json") else {}
    detail = body.get("detail") or {}
    dual = detail.get("dual_ids") or []
    out["mapped"] = {
        "gate_error_status": r_gate_m.status_code,
        "gate_error_detail": detail,
        "runtime_error_status": r_runtime_m.status_code,
    }
    check(
        results,
        f"{NS}-1 (F-A47-1 判定式) 有 handler 时 GateError -> 400 + detail.code",
        r_gate_m.status_code == 400 and detail.get("code") == "FS04",
        f"status={r_gate_m.status_code} code={detail.get('code')!r}",
    )
    check(
        results,
        f"{NS}-1b detail.dual_ids 集合 == {{vol60, uf_vol60}} 且 table_row is None",
        set(dual) == {"vol60", "uf_vol60"} and detail.get("table_row", "missing") is None,
        {"dual_ids": dual, "table_row": detail.get("table_row", "missing")},
    )
    check(
        results,
        f"{NS}-3 (F-A47-3 判定式) RuntimeException 不被洗成 400，仍是 500",
        r_runtime_m.status_code == 500,
        f"RuntimeError -> {r_runtime_m.status_code}",
    )
    return out


# --------------------------------------------------------------- D 写盘面


WRITE_PATTERNS = {
    "open( 任意形态": r"\bopen\s*\(",
    "open( 写模式": r"open\s*\([^)\n]*[\"'][rwaxb+]*[wax][+]?b?[\"']",
    "write_text": r"\bwrite_text\b",
    "write_bytes": r"\bwrite_bytes\b",
    "json.dump": r"\bjson\.dump\b",
    "save_one": r"\bsave_one\b",
    "save_definition": r"\bsave_definition\b",
    "upsert_definition": r"\bupsert_definition\b",
    "mkdir": r"\bmkdir\b",
    "os.remove / unlink": r"\bos\.remove\b|\.unlink\b",
    "shutil": r"\bshutil\b",
    "touch": r"\.touch\b",
}


def write_surface(results: list) -> dict:
    text = GATE.read_text(encoding="utf-8")
    table = {}
    for label, pattern in WRITE_PATTERNS.items():
        hits = re.findall(pattern, text)
        lines = [
            i + 1
            for i, line in enumerate(text.splitlines())
            if re.search(pattern, line)
        ]
        table[label] = {"count": len(hits), "lines": lines}
    check(
        results,
        f"{NS}-写盘/1 gate.py 内写盘调用数（open/write_text/write_bytes/json.dump/save_*/upsert_*/mkdir/unlink/touch）",
        all(v["count"] == 0 for k, v in table.items() if k != "mkdir"),
        {k: v["count"] for k, v in table.items()},
    )
    check(
        results,
        f"{NS}-写盘/2 唯一命中的 mkdir 是注释而不是调用",
        table["mkdir"]["count"] == 1
        and all("#" in text.splitlines()[n - 1] for n in table["mkdir"]["lines"]),
        {"mkdir": table["mkdir"]},
    )
    return table


# --------------------------------------------------------------- E 生产 json 只读


def readonly_15(results: list) -> dict:
    if not STORE.is_dir():
        check(results, f"{NS}-只读/0 生产目录存在", False, str(STORE))
        return {}
    before = snapshot_json_dir(STORE)
    # 全部定义 id 过一遍闸门（production / research / diagnostic × 两个命名面），
    # 把 RegistryFacts(data_dir=...) 的只读路径整个走一遍。
    source = gate.RegistryFacts(STORE.parent)
    ids = [json.loads(p.read_text(encoding="utf-8")).get("id") for p in sorted(STORE.glob("*.json"))]
    ids = [i for i in ids if i]
    for mode in ("production", "research", "diagnostic"):
        for face in ("factor", "column"):
            try:
                gate.assert_factors_usable(ids, mode, shadow=True, facts=source, namespace=face)
            except gate.GateError:
                pass
    after = snapshot_json_dir(STORE)
    same = comparable(before) == comparable(after)
    check(
        results,
        f"{NS}-只读/1 闸门全量跑后 15 个生产 json 字节/mtime 未变",
        same and len(before) == 15,
        {"files": len(before), "changed": [k for k in before if before[k] != after.get(k)], "ids": len(ids)},
    )
    return {"files": len(before), "ids": len(ids), "unchanged": same, "before": before, "after": after}


# --------------------------------------------------------------- main


def main() -> int:
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    results: list[dict] = []
    payload = {
        "script": "research/gate-fa43-20261108/evidence_route_20261108.py",
        "started_at": started,
        "python": sys.version.split()[0],
        "gate_py": {
            "bytes": GATE.stat().st_size,
            "sha256": hashlib.sha256(GATE.read_bytes()).hexdigest(),
        },
        "note": "路由层证据用 TestClient 在进程内打 ASGI，未起服务；探针 app/handler 只在本脚本内，未落 backend/app/**。",
    }
    payload["static_wiring"] = static_wiring(results)
    payload["type_facts"] = type_facts(results)
    payload["route_probe"] = route_probe(results)
    payload["write_surface"] = write_surface(results)
    payload["readonly_15"] = readonly_15(results)

    passed = sum(1 for r in results if r["ok"])
    payload["summary"] = {"total": len(results), "passed": passed, "failed": len(results) - passed}
    payload["checks"] = results

    out_path = Path(__file__).with_suffix(".json")
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{passed}/{len(results)} PASS  ->  {out_path.relative_to(REPO)}", flush=True)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
