"""F-A5 验收脚本 —— 同内容二次注册的幂等性 (version 不变 / unchanged=true / 文件字节不变)。

判据来源: docs/architecture/ 因子引擎契约 §7.6 F-A5。
  - 同内容二次注册: version 不变、文件字节不变、返回 unchanged=true;
  - 内容有差异: version = 盘上版本 + 1, 走既有注册 + 失效逻辑;
  - 缓存不被全表失效: 目录指纹 (mtime 签名, screener_work.hard_identity 的输入) 不变。

安全边界:
  - 全部用例跑在 tempfile 临时 data_dir 下 (本文件同级 tmp_* 目录, 结束删除);
  - 生产目录 D:\\TSP\\data\\user_data\\custom_factors 只做 sha256/version 快照比对,
    本脚本对该目录仅执行 listdir + read, 不写、不删、不 touch;
  - 不提交、不部署、不重启。

用法: backend\\.venv\\Scripts\\python.exe research\\factor-registration-20261107\\f_a5_idempotent.py
退出码: 0 = 全部判据通过; 1 = 有判据失败。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
for extra in (PROJECT / "backend",):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from app.factors import store  # noqa: E402
from app.factors.registry import get_factor, unregister_factor  # noqa: E402

PROD_DIR = Path(r"D:\TSP\data\user_data\custom_factors")
# 基线口径 (2026-11-07 16:30 重拍, 开发经理裁定):
# - 14 文件开工基线原件保留为历史基线 prod_snapshot_before.json, 另有同内容副本
#   prod_snapshot_before_20261107_1430.json (字节与 sha256 相同, 见报告);
# - 现行基线 = 15 文件 prod_snapshot_before_15_20261107_1630.json;
# - 判据 L 拆两段: L1 drift (基线里存在的文件逐个比, 必须为空) + L2 added
#   (新增文件必须逐条登记在 JUSTIFIED_ADDITIONS 并附理由)。
BASELINE_FILE = (
    PROJECT / "research" / "factor-registration-20261107" / "logs"
    / "prod_snapshot_before_15_20261107_1630.json"
)
HISTORICAL_BASELINE = (
    PROJECT / "research" / "factor-registration-20261107" / "logs"
    / "prod_snapshot_before_20261107_1430.json"
)
# 基线之后被正式注册而合法新增的文件 → 理由 (每条都要写明来源)
JUSTIFIED_ADDITIONS = {
    "uf_dist_prior_high_250.json": (
        "批二 A 经 store.upsert_definition 正式注册 (开发经理 2026-11-07 裁定, "
        "策略经理 §8-3); 证据 research/factor-registration-b2-20261107/"
    ),
}
EVIDENCE_FILE = PROJECT / "research" / "factor-registration-20261107" / "logs" / "f_a5_evidence.json"

RESULTS: list[dict] = []


def check(case: str, ok: bool, detail: str) -> None:
    RESULTS.append({"case": case, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {case}: {detail}", flush=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mtime_ns(path: Path) -> int:
    return path.stat().st_mtime_ns


def factor_file(data_dir: Path, factor_id: str) -> Path:
    return data_dir / "user_data" / "custom_factors" / f"{factor_id}.json"


def snapshot_prod() -> list[dict]:
    """生产目录只读快照: 文件名 / id / version / 字节数 / sha256。"""
    rows: list[dict] = []
    for path in sorted(PROD_DIR.glob("*.json")):
        definition = json.loads(path.read_text(encoding="utf-8"))
        rows.append({
            "file": path.name,
            "id": definition.get("id"),
            "version": definition.get("version"),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    return rows


def custom_definition(**overrides) -> dict:
    base = {
        "id": "uf_fa5_alpha",
        "kind": "custom",
        "version": 1,
        "label": "F-A5 幂等测试",
        "group": "自定义",
        "formula": "close / ts_delay(close, 5) - 1",
        "description": "",
        "direction": "none",
        "status": "draft",
        "created_at": "2026-11-07T10:00:00",
        "updated_at": "2026-11-07T10:00:00",
    }
    base.update(overrides)
    return base


def composite_definition(members: dict, **overrides) -> dict:
    base = {
        "id": "cf_fa5_combo",
        "kind": "composite",
        "version": 1,
        "label": "F-A5 组合",
        "group": "组合",
        "members": members,
        "description": "",
        "direction": "none",
        "status": "draft",
        "created_at": "2026-11-07T10:00:00",
        "updated_at": "2026-11-07T10:00:00",
    }
    base.update(overrides)
    return base


def case_custom(data_dir: Path) -> None:
    fid = "uf_fa5_alpha"
    path = factor_file(data_dir, fid)

    # A. 首次注册
    first = store.upsert_definition(data_dir, custom_definition())
    check("A 首次注册", first["version"] == 1 and first["unchanged"] is False and path.exists(),
          f"version={first['version']} unchanged={first['unchanged']} file_exists={path.exists()}")
    sha_a, mtime_a = sha256(path), mtime_ns(path)
    fp_a = store._STORE.fingerprint(data_dir)
    reg_a = get_factor(fid).version if get_factor(fid) else None

    # B. 同内容二次注册 (时间戳与传入 version 都不同, 语义内容相同)
    time.sleep(0.02)
    second = store.upsert_definition(data_dir, custom_definition(
        version=3, created_at="2026-11-07T11:00:00", updated_at="2026-11-07T11:00:00"))
    sha_b, mtime_b = sha256(path), mtime_ns(path)
    fp_b = store._STORE.fingerprint(data_dir)
    reg_b = get_factor(fid).version if get_factor(fid) else None
    check("B 同内容二次注册",
          second["unchanged"] is True and second["version"] == 1 and sha_a == sha_b
          and mtime_a == mtime_b and fp_a == fp_b and reg_b == reg_a == 1,
          f"version={second['version']} unchanged={second['unchanged']} "
          f"sha_same={sha_a == sha_b} mtime_same={mtime_a == mtime_b} "
          f"fingerprint_same={fp_a == fp_b} registry_version={reg_b}")

    # C. 注册表被清空后同内容再注册 (模拟重启/重复加载顺序): 补注册但不抬版本
    unregister_factor(fid)
    third = store.upsert_definition(data_dir, custom_definition())
    sha_c = sha256(path)
    reg_c = get_factor(fid).version if get_factor(fid) else None
    check("C 注册表缺失时同内容再注册",
          third["unchanged"] is True and third["version"] == 1 and reg_c == 1 and sha_a == sha_c,
          f"version={third['version']} unchanged={third['unchanged']} "
          f"re_registered_version={reg_c} sha_same={sha_a == sha_c}")

    # D. 改一个字符 (formula) → version + 1、文件改写
    changed = store.upsert_definition(data_dir, custom_definition(formula="close / ts_delay(close, 6) - 1"))
    sha_d = sha256(path)
    fp_d = store._STORE.fingerprint(data_dir)
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    check("D 改一个字符",
          changed["unchanged"] is False and changed["version"] == 2 and sha_d != sha_a
          and fp_d != fp_a and on_disk["version"] == 2
          and get_factor(fid).version == 2,
          f"version={changed['version']} unchanged={changed['unchanged']} "
          f"sha_changed={sha_d != sha_a} fingerprint_changed={fp_d != fp_a} "
          f"disk_version={on_disk['version']} registry_version={get_factor(fid).version}")

    # E. 再改回原内容 (与历史版本相同、与盘上不同) → 继续 version + 1, 不回退版本
    reverted = store.upsert_definition(data_dir, custom_definition(formula="close / ts_delay(close, 5) - 1"))
    check("E 改回历史内容仍抬版本",
          reverted["unchanged"] is False and reverted["version"] == 3,
          f"version={reverted['version']} unchanged={reverted['unchanged']}")

    # F. 只改 mtime 不改字节 → 仍判等价 (证明判等不看 mtime/文件系统时间)
    path.touch()
    touched_mtime = mtime_ns(path)
    fourth = store.upsert_definition(data_dir, custom_definition())
    check("F mtime 不参与判等",
          fourth["unchanged"] is True and fourth["version"] == 3 and mtime_ns(path) == touched_mtime,
          f"version={fourth['version']} unchanged={fourth['unchanged']} "
          f"mtime_untouched={mtime_ns(path) == touched_mtime}")


def case_composite(data_dir: Path) -> None:
    fid = "cf_fa5_combo"
    path = factor_file(data_dir, fid)

    first = store.upsert_definition(data_dir, composite_definition({"close": 0.5, "volume": 0.5}))
    sha_a = sha256(path)

    # G. 成员字典键序不同 (语义相同) → 等价
    reordered = store.upsert_definition(data_dir, composite_definition({"volume": 0.5, "close": 0.5}))
    check("G 成员键序不参与判等",
          reordered["unchanged"] is True and reordered["version"] == first["version"] == 1
          and sha256(path) == sha_a,
          f"version={reordered['version']} unchanged={reordered['unchanged']} "
          f"sha_same={sha256(path) == sha_a}")

    # H. 权重 1(int) 与盘上 1.0(float) 等价
    int_first = store.upsert_definition(data_dir, composite_definition({"close": 1.0, "volume": 1.0}))
    int_same = store.upsert_definition(data_dir, composite_definition({"close": 1, "volume": 1}))
    check("H 数值 1 与 1.0 等价",
          int_same["unchanged"] is True and int_same["version"] == int_first["version"],
          f"version={int_same['version']} unchanged={int_same['unchanged']} "
          f"(前一步 version={int_first['version']}, unchanged={int_first['unchanged']})")

    # I. status 参与比对 (draft → active 是内容变化)
    activated = store.upsert_definition(data_dir, composite_definition({"close": 1, "volume": 1}, status="active"))
    check("I status 参与比对",
          activated["unchanged"] is False
          and activated["version"] == int_same["version"] + 1
          and json.loads(path.read_text(encoding="utf-8"))["status"] == "active",
          f"version={activated['version']} unchanged={activated['unchanged']}")


def case_api(data_dir: Path) -> None:
    """API 层: POST /api/factors/custom 同内容二次提交 → unchanged=true, 版本不变, 不重跑试算。"""
    import app.api.factors as factors_api

    calls = {"trial": 0}
    original = factors_api._trial_nonempty

    def fake_trial(*_args, **_kwargs):
        calls["trial"] += 1

    factors_api._trial_nonempty = fake_trial

    store_stub = SimpleNamespace(data_dir=data_dir)
    request_stub = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        repo=SimpleNamespace(store=store_stub))))

    req = factors_api.CustomFactorCreateRequest(
        id="uf_fa5_api", label="F-A5 API", group="自定义",
        formula="close / ts_delay(close, 3) - 1", description="", direction="none",
    )
    try:
        first = factors_api.create_custom_factor(req, request_stub)
        path = factor_file(data_dir, "uf_fa5_api")
        sha_a = sha256(path)
        second = factors_api.create_custom_factor(req, request_stub)
        check("J API 同内容二次提交",
              first.get("unchanged") is False and second.get("unchanged") is True
              and second["version"] == first["version"] == 1
              and sha256(path) == sha_a and calls["trial"] == 1,
              f"first=({first['version']},{first['unchanged']}) "
              f"second=({second['version']},{second['unchanged']}) "
              f"trial_calls={calls['trial']} sha_same={sha256(path) == sha_a}")
    finally:
        factors_api._trial_nonempty = original
        unregister_factor("uf_fa5_api")


def case_reload(data_dir: Path) -> None:
    """启动期连续两次 load_into_registry: 第二次不再告警、版本不变 (F-A5 重复加载)。"""
    import logging

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    target = logging.getLogger("app.factors.store")
    handler = _Capture(level=logging.WARNING)
    target.addHandler(handler)
    try:
        first = store.load_into_registry(data_dir)
        versions_first = {fid: (get_factor(fid).version if get_factor(fid) else None) for fid in first}
        second = store.load_into_registry(data_dir)
        versions_second = {fid: (get_factor(fid).version if get_factor(fid) else None) for fid in second}
    finally:
        target.removeHandler(handler)
    check("M 启动期二次 load_into_registry",
          first == second and not records and versions_first == versions_second and len(first) == 3,
          f"ids={sorted(first)} second_ids={sorted(second)} "
          f"warnings={[r.getMessage() for r in records]} versions_stable={versions_first == versions_second}")


def case_prod_untouched(before: list[dict], after: list[dict]) -> None:
    same_in_run = [row["file"] for row in before] == [row["file"] for row in after] and all(
        (a["sha256"], a["version"], a["bytes"]) == (b["sha256"], b["version"], b["bytes"])
        for a, b in zip(before, after)
    )
    check("K 生产目录本脚本运行前后一致", same_in_run,
          f"files={len(after)} all_equal={same_in_run}")

    if BASELINE_FILE.exists():
        base = json.loads(BASELINE_FILE.read_text(encoding="utf-8-sig"))
        base_by_file = {row["file"]: row for row in base}
        now_by_file = {row["file"]: row for row in after}
        drift = [
            name for name, row in base_by_file.items()
            if name not in now_by_file
            or (now_by_file[name]["sha256"], now_by_file[name]["version"]) != (row["sha256"], row["version"])
        ]
        added = [name for name in now_by_file if name not in base_by_file]
        unexplained = [name for name in added if name not in JUSTIFIED_ADDITIONS]
        check("L1 生产目录与基线 drift 为空", not drift,
              f"baseline={BASELINE_FILE.name} baseline_files={len(base_by_file)} drift={drift}")
        check("L2 新增文件逐条被点名并附理由", not unexplained,
              f"added={[(name, JUSTIFIED_ADDITIONS.get(name, '未登记!')) for name in added]} "
              f"unexplained={unexplained}")


def check_historical_baseline() -> None:
    """历史 14 文件基线仍在且未被改写 (重拍不许覆盖原件)。"""
    if not HISTORICAL_BASELINE.exists():
        return
    rows = json.loads(HISTORICAL_BASELINE.read_text(encoding="utf-8-sig"))
    check("L0 历史 14 文件基线仍在 (原件未覆盖)", len(rows) == 14,
          f"{HISTORICAL_BASELINE.name} rows={len(rows)}")


def main() -> int:
    check_historical_baseline()
    before = snapshot_prod()
    print(f"[prod] {PROD_DIR} files={len(before)} (before)", flush=True)

    tmp_root = Path(tempfile.mkdtemp(prefix="fa5tmp_", dir=str(Path(__file__).parent)))
    data_dir = tmp_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"[tmp] data_dir={data_dir}", flush=True)
    assert data_dir != PROD_DIR and PROD_DIR not in data_dir.parents

    try:
        case_custom(data_dir)
        case_composite(data_dir)
        case_api(data_dir)
        case_reload(data_dir)
    finally:
        for fid in ("uf_fa5_alpha", "cf_fa5_combo", "uf_fa5_api"):
            try:
                unregister_factor(fid)
            except ValueError:
                pass

    after = snapshot_prod()
    case_prod_untouched(before, after)
    shutil.rmtree(tmp_root, ignore_errors=True)

    print("\n== 生产目录版本 / sha256 (本脚本运行前后) ==", flush=True)
    print(f"{'file':44s} {'version':>7s}  {'sha256'}", flush=True)
    after_by_file = {row["file"]: row for row in after}
    for row in before:
        now = after_by_file.get(row["file"], {})
        flag = "same" if now.get("sha256") == row["sha256"] and now.get("version") == row["version"] else "CHANGED"
        print(f"{row['file']:44s} {row['version']!s:>7s}  {row['sha256'][:16]}… {flag}", flush=True)

    failed = [row for row in RESULTS if not row["ok"]]
    EVIDENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_FILE.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "criterion": "F-A5 注册幂等 (同内容二次注册 version 不变 / unchanged=true / 文件字节不变)",
        "cases": RESULTS,
        "prod_custom_factors": after,
        "passed": len(RESULTS) - len(failed),
        "failed": len(failed),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n== {len(RESULTS) - len(failed)}/{len(RESULTS)} 判据通过 ==", flush=True)
    for row in failed:
        print(f"  FAIL {row['case']}: {row['detail']}", flush=True)
    print(f"[evidence] {EVIDENCE_FILE}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
