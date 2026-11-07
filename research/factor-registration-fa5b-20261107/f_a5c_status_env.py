"""F-A5 收尾验收 —— status 不被 create 打回 / 扩展列前置条件 / 生产目录零漂移。

依据 (开发经理 2026-11-07 三件收尾裁定):
  【1】POST /custom 创建路径不得把线上 active 定义打回 draft:
       盘上已有该 id 时 status 沿用盘上值; 调用方显式给出则以调用方为准;
       真改内容时才回 draft (编辑即回 draft, 属 /update 语义)。
  【3】auction 因子的幂等判定依赖 ext_ 扩展列已注册: 缺扩展列的进程里同内容
       重提交是硬错误 (ValueError), 不是 unchanged。服务启动路径是否有保证要查清。

判据:
  S1  active 定义 + API 形状 (无 status) 重提交: unchanged=true / v 不变 /
      sha256 与 mtime 不变 / status 仍 active / lang+unit+tags 保留
  S1b 同上但 lang="python"
  S2  active 定义 + 真改公式: v+1 / status=draft / lang+unit+tags 保留
  S3  draft 定义 + API 形状: unchanged=true, 全字段不变
  S4  composite 定义 (active) + API 形状: unchanged=true / status 仍 active
  S5  调用方显式给不同 status (watch): 以调用方为准 / v+1 / status=watch
  S6  回归 (旧判据 H): draft 定义 + 显式 status=active: v+1 / status=active
  S7  路由层 create_custom_factor: active 定义同内容重提交 → unchanged=true,
      **试算 0 次**, status 仍 active
  S8  路由层: active 定义真改公式 → 试算 1 次, v+1, status=draft, lang 保留
  S9  生产目录 15 个 json: 全脚本运行前后 sha256/version/mtime 全等 (附 64 位)
  E1  无扩展列 (无配置、未同步) 的进程: auction 因子同内容重提交 → ValueError
      (记录异常文本), 且盘上文件字节与 mtime 不变 (fail-closed, 没写坏)
  E2  装扩展配置 + ensure_synced 后同一份定义: unchanged=true
  E3  配置在盘但注册表被清空 (等价「进程未同步扩展列」): ValueError; 同步后 unchanged
  E4  启动路径静态事实: load_into_registry 首条语句是 ensure_synced(data_dir);
      main.py 只有一处 load_into_registry(store.data_dir); 启动期无更早的定义注册入口;
      _data_dir(request) 与 store.data_dir 同一根
  E5  启动镜像: 临时目录有扩展配置 → 15/15 加载零告警; 无扩展配置 → 只 auction 6+1
      失败并告警 (隔离, 不阻断)

安全边界: 所有写操作只在 tempfile 临时 data_dir 内 (含 user_data/custom_factors
这一层); 生产目录 D:\\TSP\\data\\user_data\\custom_factors 只读 listdir + read。
不提交、不部署、不重启。

用法: backend\\.venv\\Scripts\\python.exe -X utf8 research\\factor-registration-fa5b-20261107\\f_a5c_status_env.py
退出码: 0 = 全部判据通过; 1 = 有判据失败。
"""
from __future__ import annotations

import ast
import hashlib
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(PROJECT / "backend"))

from app.factors import store  # noqa: E402
from app.factors.registry import get_factor, unregister_factor  # noqa: E402

PROD_DIR = Path(r"D:\TSP\data\user_data\custom_factors")
OUT_DIR = PROJECT / "research" / "factor-registration-fa5b-20261107"
LOG_DIR = OUT_DIR / "logs"
EVIDENCE_FILE = LOG_DIR / "f_a5c_status_env_evidence.json"
NOW = "2026-11-07T16:30:00"
SUBDIR = Path("user_data") / "custom_factors"

RESULTS: list[dict] = []
EVIDENCE: dict[str, object] = {"cases": RESULTS}


def check(case: str, ok: bool, detail: str) -> bool:
    RESULTS.append({"case": case, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {case}: {detail}", flush=True)
    return bool(ok)


def snapshot(folder: Path) -> dict[str, dict]:
    """目录快照: id/version/status/lang/unit/tags/sha256/mtime/keys。只读。"""
    rows: dict[str, dict] = {}
    for path in sorted(folder.glob("*.json")):
        raw = path.read_bytes()
        definition = json.loads(raw.decode("utf-8"))
        rows[path.name] = {
            "id": definition.get("id"),
            "version": definition.get("version"),
            "status": definition.get("status"),
            "lang": definition.get("lang"),
            "unit": definition.get("unit"),
            "tags": definition.get("tags"),
            "formula": definition.get("formula"),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "mtime_ns": path.stat().st_mtime_ns,
            "keys": sorted(definition.keys()),
        }
    return rows


def prod_definitions() -> dict[str, dict]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(PROD_DIR.glob("*.json"))
    }


def prep_dir(definitions: dict[str, dict]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="fa5c_"))
    target = root / SUBDIR
    target.mkdir(parents=True)
    for name, definition in definitions.items():
        (target / name).write_text(
            json.dumps(definition, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return root


def install_ext_configs(root: Path) -> None:
    """装竞价扩展字段配置再同步 (与 backend/tests/test_auction_factor_pack.py 同路径)。"""
    from app.factors import ext_factors
    from app.services.ext_data import ExtConfig, ExtConfigStore, ExtField

    configs = ExtConfigStore(root)
    configs.upsert(ExtConfig(
        id="auction_preopen",
        label="早盘竞价过程",
        mode="timeseries",
        fields=[
            ExtField("last_imbalance", "float"),
            ExtField("last_minute_matched_growth", "float"),
            ExtField("post0920_matched_growth", "float"),
        ],
    ))
    configs.upsert(ExtConfig(
        id="auction_result",
        label="早盘竞价结果",
        mode="timeseries",
        fields=[ExtField("volume_shares", "float")],
    ))
    ext_factors.ensure_synced(root)


def ext_ids() -> list[str]:
    from app.factors.registry import _REGISTRY

    return [fid for fid in list(_REGISTRY) if fid.startswith("ext_")]


def clear_ext_registry() -> int:
    removed = 0
    for fid in ext_ids():
        try:
            unregister_factor(fid)
            removed += 1
        except ValueError:
            pass
    return removed


def clear_registry(ids: list[str]) -> None:
    for fid in sorted({i for i in ids if i}, key=lambda x: (not x.startswith("cf_"), x)):
        try:
            if get_factor(fid) is not None:
                unregister_factor(fid)
        except ValueError:
            pass


def api_shape(disk: dict) -> dict:
    """新版 API 形状: 照 create_custom_factor / create_composite_factor 构造, 无 lang, 无 status。"""
    common = {
        "id": disk["id"],
        "version": 1,
        "label": disk["label"],
        "group": disk.get("group"),
        "description": disk.get("description", ""),
        "direction": disk.get("direction", "none"),
        "created_at": NOW,
        "updated_at": NOW,
    }
    if str(disk.get("kind", "custom")) == "composite":
        return {"kind": "composite", "members": dict(disk["members"]), **common}
    return {"kind": "custom", "formula": disk["formula"], **common}


def with_status(definition: dict, status: str) -> dict:
    payload = dict(definition)
    payload["status"] = status
    return payload


def run_upsert(root: Path, payload: dict) -> tuple[dict | None, str]:
    try:
        return store.upsert_definition(root, payload), ""
    except Exception as exc:  # noqa: BLE001 — 判据要保留异常文本
        return None, f"{type(exc).__name__}: {exc}"


def dir_defs_for(definition: dict, definitions: dict[str, dict]) -> dict[str, dict]:
    """自定义因子只看自身; composite 连带成员定义 (加载时成员须可投影)。"""
    name = f"{definition['id']}.json"
    if str(definition.get("kind", "custom")) == "composite":
        return {name: definition, **{
            f"{m}.json": definitions[f"{m}.json"] for m in definition["members"]
            if f"{m}.json" in definitions
        }}
    return {name: definition}


# ── S 组: status 语义 ────────────────────────────────────────────────


def case_status_unchanged(
    label: str, disk: dict, definitions: dict[str, dict], *,
    as_python: bool = False, disk_shape: bool = False,
) -> None:
    """盘上 active 定义重提交: 必须完全不变, status 仍 active。

    disk_shape=True 时入参就是盘上定义本身 (含 lang) —— python 定义只能走这条形状:
    API 形状没有 lang 键, 语义上真的不是同一个因子 (报告 §7.5 已写明), 那种情况
    判等说「变了」是正确行为, 不能拿来当 status 判据。
    """
    active = dict(disk)
    active["status"] = "active"
    active["unit"] = "ratio"
    active["tags"] = ["fa5c", "status"]
    if as_python:
        active["lang"] = "python"
        active["formula"] = "ctx.col('close') / ctx.col('open') - 1"
        active["warmup_bars"] = 1
    dir_defs = dir_defs_for(active, definitions)
    root = prep_dir(dir_defs)
    try:
        install_ext_configs(root)
        store.load_into_registry(root)
        folder = root / SUBDIR
        before = snapshot(folder)[f"{active['id']}.json"]
        payload = json.loads(json.dumps(active)) if disk_shape else api_shape(active)
        result, error = run_upsert(root, payload)
        after = snapshot(folder)[f"{active['id']}.json"]
        spec = get_factor(str(active["id"]))
        ok = (
            result is not None
            and result.get("unchanged") is True
            and result.get("version") == before["version"]
            and after["version"] == before["version"]
            and after["sha256"] == before["sha256"]
            and after["mtime_ns"] == before["mtime_ns"]
            and after["status"] == "active"
            and (after["lang"] or "dsl") == (before["lang"] or "dsl")
            and after["unit"] == "ratio"
            and after["tags"] == ["fa5c", "status"]
            and spec is not None
            and spec.version == before["version"]
        )
        check(
            label,
            ok,
            f"unchanged={None if result is None else result.get('unchanged')} "
            f"ret_v={None if result is None else result.get('version')} "
            f"disk v {before['version']}→{after['version']} "
            f"status {before['status']}→{after['status']} lang={after['lang']} "
            f"unit={after['unit']} tags={after['tags']} "
            f"sha_same={after['sha256'] == before['sha256']} "
            f"mtime_same={after['mtime_ns'] == before['mtime_ns']} "
            f"spec_v={None if spec is None else spec.version} {error}",
        )
    finally:
        clear_registry([str(d.get("id")) for d in dir_defs.values()])
        shutil.rmtree(root, ignore_errors=True)


def case_status_changed_formula(label: str, disk: dict, definitions: dict[str, dict]) -> None:
    """盘上 active 定义真改公式: v+1 且回 draft, 非 API 字段保留。"""
    active = dict(disk)
    active["status"] = "active"
    active["unit"] = "ratio"
    active["tags"] = ["fa5c", "status"]
    dir_defs = dir_defs_for(active, definitions)
    root = prep_dir(dir_defs)
    try:
        install_ext_configs(root)
        store.load_into_registry(root)
        folder = root / SUBDIR
        before = snapshot(folder)[f"{active['id']}.json"]
        payload = api_shape(active)
        payload["formula"] = str(active["formula"]) + " + 0"
        result, error = run_upsert(root, payload)
        after = snapshot(folder)[f"{active['id']}.json"]
        ok = (
            result is not None
            and result.get("unchanged") is False
            and result.get("version") == before["version"] + 1
            and after["version"] == before["version"] + 1
            and after["status"] == "draft"
            and after["formula"] == payload["formula"]
            and (after["lang"] or "dsl") == (before["lang"] or "dsl")
            and after["unit"] == "ratio"
            and after["tags"] == ["fa5c", "status"]
        )
        check(
            label,
            ok,
            f"unchanged={None if result is None else result.get('unchanged')} "
            f"v {before['version']}→{after['version']} status {before['status']}→{after['status']} "
            f"formula_new={after['formula'] == payload['formula']} lang={after['lang']} "
            f"unit={after['unit']} tags={after['tags']} {error}",
        )
    finally:
        clear_registry([str(d.get("id")) for d in dir_defs.values()])
        shutil.rmtree(root, ignore_errors=True)


def case_explicit_status(
    label: str, disk: dict, definitions: dict[str, dict], status: str, disk_status: str = "active"
) -> None:
    """调用方显式给出 status: 以调用方为准 (不管内容是否同)。"""
    active = dict(disk)
    active["status"] = disk_status
    dir_defs = dir_defs_for(active, definitions)
    root = prep_dir(dir_defs)
    try:
        install_ext_configs(root)
        store.load_into_registry(root)
        folder = root / SUBDIR
        before = snapshot(folder)[f"{active['id']}.json"]
        payload = with_status(api_shape(active), status)
        result, error = run_upsert(root, payload)
        after = snapshot(folder)[f"{active['id']}.json"]
        check(
            label,
            result is not None
            and result.get("unchanged") is False
            and after["version"] == before["version"] + 1
            and after["status"] == status,
            f"explicit_status={status} unchanged={None if result is None else result.get('unchanged')} "
            f"v {before['version']}→{after['version']} status {before['status']}→{after['status']} {error}",
        )
    finally:
        clear_registry([str(d.get("id")) for d in dir_defs.values()])
        shutil.rmtree(root, ignore_errors=True)


def case_draft_untouched(label: str, disk: dict, definitions: dict[str, dict]) -> None:
    """盘上 draft 定义经 API 形状重提交: 一切不变。"""
    dir_defs = dir_defs_for(dict(disk), definitions)
    root = prep_dir(dir_defs)
    try:
        install_ext_configs(root)
        store.load_into_registry(root)
        folder = root / SUBDIR
        before = snapshot(folder)[f"{disk['id']}.json"]
        result, error = run_upsert(root, api_shape(disk))
        after = snapshot(folder)[f"{disk['id']}.json"]
        check(
            label,
            result is not None
            and result.get("unchanged") is True
            and after["version"] == before["version"]
            and after["sha256"] == before["sha256"]
            and after["mtime_ns"] == before["mtime_ns"]
            and after["status"] == "draft"
            and after["keys"] == before["keys"],
            f"unchanged={None if result is None else result.get('unchanged')} "
            f"v {before['version']}→{after['version']} status={after['status']} "
            f"sha_same={after['sha256'] == before['sha256']} "
            f"mtime_same={after['mtime_ns'] == before['mtime_ns']} {error}",
        )
    finally:
        clear_registry([str(d.get("id")) for d in dir_defs.values()])
        shutil.rmtree(root, ignore_errors=True)


def case_first_create(definitions: dict[str, dict]) -> None:
    """首次创建 (盘上无该 id) 且不传 status: 落 draft (create 不是生命周期操作)。"""
    for label, name, kind in (
        ("S10 首次创建 custom (无 status) → draft", "uf_ma120.json", "custom"),
        ("S11 首次创建 composite (无 status) → draft", "cf_auction_resonance.json", "composite"),
    ):
        disk = definitions[name]
        payload = api_shape(disk)
        payload["id"] = f"uf_fa5c_first_{kind}" if kind == "custom" else f"cf_fa5c_first"
        payload["label"] = f"fa5c 首次{kind}"
        payload["formula" if kind == "custom" else "members"] = (
            "close / ts_delay(close, 5) - 1" if kind == "custom" else {"uf_ma120": 1.0, "uf_vol60": 1.0}
        )
        deps = {f"{m}.json": definitions[f"{m}.json"] for m in payload.get("members", {}) if f"{m}.json" in definitions}
        root = prep_dir(deps)
        try:
            install_ext_configs(root)
            store.load_into_registry(root)
            folder = root / SUBDIR
            result, error = run_upsert(root, payload)
            written = json.loads((folder / f"{payload['id']}.json").read_text(encoding="utf-8")) if (
                folder / f"{payload['id']}.json"
            ).exists() else {}
            check(
                label,
                result is not None
                and result.get("unchanged") is False
                and result.get("version") == 1
                and written.get("status") == "draft"
                and "status" in written,
                f"ret_v={None if result is None else result.get('version')} "
                f"unchanged={None if result is None else result.get('unchanged')} "
                f"disk_status={written.get('status')} keys={sorted(written)} {error}",
            )
        finally:
            clear_registry([payload["id"], *payload.get("members", {})])
            shutil.rmtree(root, ignore_errors=True)


# ── E 组: 扩展列前置条件 ─────────────────────────────────────────────


def case_env_auction(definitions: dict[str, dict]) -> None:
    name = "uf_auction_volume_surprise.json"
    disk = definitions[name]
    payload = api_shape(disk)

    # E1 无扩展配置、未同步 (进程里没有 ext_ 列)
    root = prep_dir({name: disk})
    try:
        folder = root / SUBDIR
        before = snapshot(folder)[name]
        removed = clear_ext_registry()
        result, error = run_upsert(root, payload)
        after = snapshot(folder)[name]
        check(
            "E1 无扩展列进程: 同内容重提交是硬错误 (不是 unchanged)",
            result is None
            and error.startswith("ValueError")
            and "ext_auction_" in error
            and after["sha256"] == before["sha256"]
            and after["mtime_ns"] == before["mtime_ns"]
            and after["version"] == before["version"],
            f"exc={error} ext_ids_before={removed} "
            f"file_unchanged={after['sha256'] == before['sha256'] and after['mtime_ns'] == before['mtime_ns']}",
        )
    finally:
        clear_registry([str(disk.get("id"))])
        shutil.rmtree(root, ignore_errors=True)

    # E2 装扩展配置 + 同步后同一份定义
    root = prep_dir({name: disk})
    try:
        install_ext_configs(root)
        store.load_into_registry(root)
        folder = root / SUBDIR
        before = snapshot(folder)[name]
        result, error = run_upsert(root, payload)
        after = snapshot(folder)[name]
        check(
            "E2 扩展列已注册: 同一份定义 unchanged=true",
            result is not None
            and result.get("unchanged") is True
            and after["sha256"] == before["sha256"]
            and after["mtime_ns"] == before["mtime_ns"]
            and get_factor(str(disk["id"])) is not None,
            f"unchanged={None if result is None else result.get('unchanged')} "
            f"v {before['version']}→{after['version']} "
            f"sha_same={after['sha256'] == before['sha256']} {error}",
        )
    finally:
        clear_registry([str(disk.get("id"))])
        shutil.rmtree(root, ignore_errors=True)

    # E3 配置在盘但注册表没有 ext_ 条目 (= 一个从未同步过扩展列的进程)。
    # 注意: ensure_synced 按 (root, 配置签名) 幂等缓存, 手动清空注册表后必须同时
    # 置空它的 sync 状态, 否则再调一次也直接 return —— 这条缓存行为本身也记进报告。
    root = prep_dir({name: disk})
    try:
        from app.factors import ext_factors

        install_ext_configs(root)
        removed = clear_ext_registry()
        cached = ext_factors._sync_state is not None
        ext_factors._sync_state = None
        folder = root / SUBDIR
        before = snapshot(folder)[name]
        result, error = run_upsert(root, payload)
        after = snapshot(folder)[name]
        hard_error = result is None and error.startswith("ValueError")
        ext_factors.ensure_synced(root)
        result2, error2 = run_upsert(root, payload)
        after2 = snapshot(folder)[name]
        check(
            "E3 配置在盘但未同步 (注册表无 ext_ 条目): 硬错误; 同步后 unchanged",
            hard_error
            and result2 is not None
            and result2.get("unchanged") is True
            and after["sha256"] == before["sha256"]
            and after2["sha256"] == before["sha256"]
            and after2["mtime_ns"] == before["mtime_ns"],
            f"ext_removed={removed} sync_state_was_cached={cached} exc_before_sync={error} "
            f"unchanged_after_sync={None if result2 is None else result2.get('unchanged')} "
            f"sha_same={after2['sha256'] == before['sha256']} {error2}",
        )
    finally:
        clear_registry([str(disk.get("id"))])
        shutil.rmtree(root, ignore_errors=True)


def case_startup_static_facts() -> None:
    store_src = (PROJECT / "backend" / "app" / "factors" / "store.py").read_text(encoding="utf-8")
    main_src = (PROJECT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    api_src = (PROJECT / "backend" / "app" / "api" / "factors.py").read_text(encoding="utf-8")
    tree = ast.parse(store_src)
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "load_into_registry")
    prefix: list[str] = []
    first_src = ""
    for stmt in func.body:
        seg = ast.get_source_segment(store_src, stmt) or ""
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            first_src = seg
            break
        prefix.append(type(stmt).__name__)
    prefix_ok = all(
        name in {"Expr", "Import", "ImportFrom"} for name in prefix
    ) and not first_src.startswith("logger")
    lines = [i + 1 for i, line in enumerate(main_src.splitlines()) if "load_into_registry(" in line]
    check(
        "E4a load_into_registry 首条调用语句是 ensure_synced(data_dir)",
        "ensure_synced(data_dir)" in first_src and prefix_ok,
        f"prefix={prefix} first_call={first_src.strip() if first_src else '<none>'}",
    )
    check(
        "E4b main.py 只有一处 load_into_registry(store.data_dir)",
        len(lines) == 1 and "load_into_registry(store.data_dir)" in main_src,
        f"main_lines={lines}",
    )
    earlier = [
        kw for kw in ("register_definition(", "upsert_definition(", "register_factor(", "save_one(")
        if kw in main_src
    ]
    check(
        "E4c 启动路径无更早的定义注册入口 (main.py 不直接调注册/落库函数)",
        not earlier,
        f"hits={earlier or 'none'}",
    )
    same_root = (
        "repo = KlineRepository(store)" in main_src
        and "app.state.repo = repo" in main_src
        and "load_into_registry(store.data_dir)" in main_src
        and 'getattr(getattr(request.app.state, "repo", None), "store", None)' in api_src
        and 'getattr(data_dir, "data_dir", None)' in api_src
    )
    check(
        "E4d 请求侧 _data_dir 与启动注册同一 data_dir (repo.store.data_dir)",
        same_root,
        "main: app.state.repo=repo, repo=KlineRepository(store), load_into_registry(store.data_dir); "
        "api: request.app.state.repo.store.data_dir",
    )
    fail_open = "if sig is None:" in (PROJECT / "backend" / "app" / "factors" / "ext_factors.py").read_text(encoding="utf-8")
    EVIDENCE["ensure_synced_fail_open"] = fail_open


def case_startup_mimic(definitions: dict[str, dict]) -> None:
    """启动镜像: 加载器在同一条调用里先同步扩展列再注册定义。"""

    class Capture(logging.Handler):
        def __init__(self) -> None:
            super().__init__(level=logging.WARNING)
            self.records: list[str] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.records.append(record.getMessage())

    def load_with_capture(root: Path) -> tuple[list[str], list[str]]:
        logger = logging.getLogger("app.factors.store")
        handler = Capture()
        logger.addHandler(handler)
        try:
            loaded = store.load_into_registry(root)
        finally:
            logger.removeHandler(handler)
        return loaded, handler.records

    all_defs = dict(definitions)
    root = prep_dir(all_defs)
    try:
        install_ext_configs(root)
        clear_registry([str(d.get("id")) for d in all_defs.values()])
        loaded, warnings = load_with_capture(root)
        check(
            "E5a 有扩展配置的启动镜像: 15/15 加载, 零告警",
            len(loaded) == len(all_defs) and not warnings,
            f"loaded={len(loaded)}/{len(all_defs)} warnings={warnings}",
        )
    finally:
        clear_registry([str(d.get("id")) for d in all_defs.values()])
        shutil.rmtree(root, ignore_errors=True)

    root = prep_dir(all_defs)
    try:
        clear_registry([str(d.get("id")) for d in all_defs.values()])
        clear_ext_registry()
        loaded, warnings = load_with_capture(root)
        failed = sorted(
            fid for fid in (str(d.get("id")) for d in all_defs.values()) if get_factor(fid) is None
        )
        check(
            "E5b 无扩展配置的启动镜像: 仅引用 ext_ 的定义失败并告警, 其余照常",
            failed == sorted([
                "cf_auction_resonance",
                "uf_auction_post0920_match_growth",
                "uf_auction_tail_imbalance",
                "uf_auction_tail_match_growth",
                "uf_auction_volume_surprise",
                "uf_auction_volume_vs_prev",
            ])
            and len(warnings) == len(failed)
            and "未知标识符" in " ".join(warnings),
            f"loaded={len(loaded)}/{len(all_defs)} failed={failed} warnings={len(warnings)}",
        )
    finally:
        clear_registry([str(d.get("id")) for d in all_defs.values()])
        shutil.rmtree(root, ignore_errors=True)


# ── 路由层 ───────────────────────────────────────────────────────────


def case_route(definitions: dict[str, dict]) -> None:
    import app.api.factors as factors_api

    disk = definitions["uf_ma120.json"]
    active = dict(disk)
    active["status"] = "active"
    active["unit"] = "ratio"
    active["tags"] = ["fa5c", "route"]
    root = prep_dir({"uf_ma120.json": active})
    calls = {"trial": 0}
    original = factors_api._trial_nonempty

    def fake_trial(*_a, **_k):
        calls["trial"] += 1

    factors_api._trial_nonempty = fake_trial
    try:
        install_ext_configs(root)
        store.load_into_registry(root)
        folder = root / SUBDIR
        before = snapshot(folder)["uf_ma120.json"]
        request_stub = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            repo=SimpleNamespace(store=SimpleNamespace(data_dir=root)))))
        req = factors_api.CustomFactorCreateRequest(
            id=active["id"], label=active["label"], group=active["group"],
            formula=active["formula"], description=active.get("description", ""),
            direction=active.get("direction", "none"),
        )
        result = factors_api.create_custom_factor(req, request_stub)
        after = snapshot(folder)["uf_ma120.json"]
        check(
            "S7 路由 create_custom_factor: active 同内容重提交 unchanged=true / 试算 0 次 / status 仍 active",
            result.get("unchanged") is True
            and result.get("version") == before["version"]
            and after["sha256"] == before["sha256"]
            and after["mtime_ns"] == before["mtime_ns"]
            and after["status"] == "active"
            and after["unit"] == "ratio"
            and after["tags"] == ["fa5c", "route"]
            and calls["trial"] == 0,
            f"unchanged={result.get('unchanged')} v={result.get('version')} "
            f"status={after['status']} trial_calls={calls['trial']} "
            f"sha_same={after['sha256'] == before['sha256']}",
        )
        req2 = factors_api.CustomFactorCreateRequest(
            id=active["id"], label=active["label"], group=active["group"],
            formula=str(active["formula"]) + " + 0", description=active.get("description", ""),
            direction=active.get("direction", "none"),
        )
        result2 = factors_api.create_custom_factor(req2, request_stub)
        written = json.loads((folder / "uf_ma120.json").read_text(encoding="utf-8"))
        check(
            "S8 路由: active 真改公式 → 试算 1 次 / v+1 / status=draft / lang 保留",
            result2.get("unchanged") is False
            and result2.get("version") == before["version"] + 1
            and calls["trial"] == 1
            and written.get("status") == "draft"
            and written.get("lang") == "dsl"
            and written.get("unit") == "ratio"
            and written.get("tags") == ["fa5c", "route"],
            f"unchanged={result2.get('unchanged')} v={result2.get('version')} "
            f"status={written.get('status')} lang={written.get('lang')} "
            f"unit={written.get('unit')} tags={written.get('tags')} trial_calls={calls['trial']}",
        )
    finally:
        factors_api._trial_nonempty = original
        clear_registry(["uf_ma120"])
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    prod_before = snapshot(PROD_DIR)
    definitions = prod_definitions()
    print(f"生产样本 {len(definitions)} 个定义; 全部写操作只在临时 data_dir 内\n", flush=True)

    case_status_unchanged("S1 active + API 形状重提交 (lang=dsl)", definitions["uf_ma120.json"], definitions)
    case_status_unchanged(
        "S1b active + 盘上形状重提交 (lang=python)", definitions["uf_prior_high_20.json"],
        definitions, as_python=True, disk_shape=True,
    )
    case_status_changed_formula("S2 active + 真改公式", definitions["uf_prior_high_55.json"], definitions)
    case_draft_untouched("S3 draft + API 形状重提交", definitions["uf_prior_high_250.json"], definitions)
    case_status_unchanged("S4 composite active + API 形状重提交", definitions["cf_auction_resonance.json"], definitions)
    case_explicit_status("S5 显式 status=watch (与盘上 active 不同)", definitions["uf_prior_low_10.json"], definitions, "watch")
    case_explicit_status(
        "S6 回归: draft + 显式 status=active",
        definitions["uf_vol60.json"], definitions, "active", disk_status="draft",
    )
    case_route(definitions)
    case_first_create(definitions)

    case_env_auction(definitions)
    case_startup_static_facts()
    case_startup_mimic(definitions)

    prod_after = snapshot(PROD_DIR)
    names = sorted(set(prod_before) | set(prod_after))
    drift = [
        name for name in names
        if (
            prod_before.get(name, {}).get("sha256") != prod_after.get(name, {}).get("sha256")
            or prod_before.get(name, {}).get("version") != prod_after.get(name, {}).get("version")
            or prod_before.get(name, {}).get("mtime_ns") != prod_after.get(name, {}).get("mtime_ns")
        )
    ]
    check(
        "S9 生产目录 15 个 json 本脚本前后一致",
        not drift and len(prod_after) == 15,
        f"files_before={len(prod_before)} files_after={len(prod_after)} drift={drift}",
    )
    EVIDENCE["prod_sha256_64"] = {
        name: {"sha256": row["sha256"], "version": row["version"], "status": row["status"]}
        for name, row in prod_after.items()
    }
    EVIDENCE["prod_drift"] = drift

    total = len(RESULTS)
    passed = sum(1 for row in RESULTS if row["ok"])
    EVIDENCE["summary"] = {
        "total": total, "passed": passed, "failed": total - passed,
        "prod_files": len(prod_after), "generated_at": NOW,
    }
    EVIDENCE_FILE.write_text(json.dumps(EVIDENCE, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== {passed}/{total} 判据通过; 生产 {len(prod_after)} 个 json, drift={drift} ===", flush=True)
    print(f"证据: {EVIDENCE_FILE}", flush=True)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
