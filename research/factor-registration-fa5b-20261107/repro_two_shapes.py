"""复现开发经理报告的 F-A5 两形状差异 (改代码前基线)。

两种提交形状:
  - 盘上形状 (disk shape): 把盘上 json 原样 (含 lang 等非 API 字段) 重提交;
  - API 形状 (API shape): 照 backend/app/api/factors.py create_custom_factor 构造,
    没有 lang 键。

只读生产目录 8 个 uf_* 作为样本; 全部写操作在 tempfile 临时 data_dir 内。
退出码: 0 = 复现成功 (即存在 API 形状差异), 2 = 未能复现。
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(PROJECT / "backend"))

from app.factors import store  # noqa: E402
from app.factors.registry import unregister_factor  # noqa: E402

PROD_DIR = Path(r"D:\TSP\data\user_data\custom_factors")
UF_IDS = [
    "uf_ma120", "uf_ma200", "uf_prior_high_20", "uf_prior_high_55",
    "uf_prior_high_250", "uf_prior_low_10", "uf_prior_vol_20", "uf_vol60",
]


def api_shape(disk: dict) -> dict:
    """照 api/factors.py create_custom_factor 的 definition 构造 (无 lang)。"""
    return {
        "id": disk["id"],
        "kind": "custom",
        "version": 1,
        "label": disk["label"],
        "group": disk.get("group"),
        "formula": disk["formula"],
        "description": disk.get("description", ""),
        "direction": disk.get("direction", "none"),
        "status": "draft",
        "created_at": "2026-11-07T16:20:00",
        "updated_at": "2026-11-07T16:20:00",
    }


def run_shape(shape_name: str, build_payload) -> list[dict]:
    rows = []
    for fid in UF_IDS:
        disk = json.loads((PROD_DIR / f"{fid}.json").read_text(encoding="utf-8"))
        tmp = Path(tempfile.mkdtemp(prefix="fa5repro_"))
        try:
            target_dir = tmp / "user_data" / "custom_factors"
            target_dir.mkdir(parents=True)
            target = target_dir / f"{fid}.json"
            target.write_text(json.dumps(disk, ensure_ascii=False, indent=2), encoding="utf-8")
            before_bytes = target.read_bytes()
            before_mtime = target.stat().st_mtime_ns
            payload = build_payload(disk)
            try:
                result = store.upsert_definition(tmp, payload)
                err = ""
            except Exception as exc:  # noqa: BLE001
                result, err = None, f"{type(exc).__name__}: {exc}"
            after = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
            rows.append({
                "shape": shape_name,
                "id": fid,
                "unchanged": None if result is None else result.get("unchanged"),
                "version_before": disk.get("version"),
                "version_after": after.get("version"),
                "bytes_identical": target.read_bytes() == before_bytes,
                "mtime_identical": target.stat().st_mtime_ns == before_mtime,
                "lang_before": disk.get("lang"),
                "lang_after": after.get("lang"),
                "error": err,
            })
        finally:
            unregister_factor(fid) if _registered(fid) else None
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
    return rows


def _registered(fid: str) -> bool:
    from app.factors.registry import get_factor
    return get_factor(fid) is not None


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    disk_rows = run_shape("disk", lambda d: dict(d))
    api_rows = run_shape("api", api_shape)
    print("=" * 100)
    print("盘上形状 (原样重提交)")
    for row in disk_rows:
        print(f"  {row['id']:<24} unchanged={row['unchanged']!s:<5} v {row['version_before']}→{row['version_after']} "
              f"bytes_same={row['bytes_identical']!s:<5} mtime_same={row['mtime_identical']!s:<5} lang={row['lang_after']} {row['error']}")
    print("API 形状 (照 api/factors.py 构造, 无 lang)")
    for row in api_rows:
        print(f"  {row['id']:<24} unchanged={row['unchanged']!s:<5} v {row['version_before']}→{row['version_after']} "
              f"bytes_same={row['bytes_identical']!s:<5} mtime_same={row['mtime_identical']!s:<5} lang={row['lang_after']} {row['error']}")
    disk_ok = all(r["unchanged"] and r["bytes_identical"] and r["mtime_identical"] for r in disk_rows)
    api_bad = sum(1 for r in api_rows if not r["unchanged"])
    print("=" * 100)
    print(f"盘上形状全部 unchanged 且字节/mtime 不变: {disk_ok} ({len(disk_rows)} 例)")
    print(f"API 形状被判为「变了」的例数: {api_bad}/{len(api_rows)}")
    out = PROJECT / "research" / "factor-registration-fa5b-20261107" / "logs" / f"repro_{label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"disk": disk_rows, "api": api_rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"证据: {out}")
    return 0 if (disk_ok and api_bad > 0) else 2


if __name__ == "__main__":
    raise SystemExit(main())
