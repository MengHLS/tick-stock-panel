"""F-A5 返工验收 —— 两形状判等 (盘上形状 / API 形状) + 写盘保留非 API 字段。

返工依据 (开发经理 2026-11-07 判 FAIL 的事实):
  - 盘上形状 (json 原样重提交): 8/8 unchanged=true —— 旧实现这条是对的;
  - API 形状 (照 api/factors.py create_custom_factor 构造, 无 lang 键): 8/8 被判
    「变了」, 版本 1→2, 文件被重写, 盘上 lang 被抹掉。
根因: 旧判等是「原始键集黑名单比对」, 盘上多一个 lang 就必然不等。
本返工把判等域改成 to_spec() 的语义投影 (缺省值由编译器/校验器补齐), 写盘改成
「以盘上定义为底合并入参」。

判据:
  A 盘上形状 × 15 个生产定义: unchanged=true / version 不变 / sha256 不变 / mtime 不变;
  B API 形状 × 15 个生产定义: 同上;
  C lang="python" 盘上定义同内容重提交: unchanged=true, 不抛 (不得 400);
  D 反向对照 (真改一个字符): unchanged=false / version+1 / 盘上 lang 仍在;
  E 反向对照 (python 定义改字符): version+1, lang 仍是 python;
  F 惰性附加字段 (tags/unit/scale_free): 不参与判等 (同内容仍 unchanged), 但真改
    内容时写盘必须保留它们;
  G fail-closed: 非法输入仍被拒 (不因判等短路而放行), 且文件字节不变;
  H status 变化 (draft→active) 算内容变化: version+1;
  I API 层 (create_custom_factor) 对盘上已有定义同内容重提交: unchanged=true,
    不重跑试算, 版本不变;
  J 生产目录 15 个 json 前后逐字节等价 (version + sha256 + mtime)。

安全边界: 全部用例跑在 tempfile 临时 data_dir (内含 user_data/custom_factors 这一层,
加载器会拼这一层); 生产目录 D:\\TSP\\data\\user_data\\custom_factors 只读 listdir +
read, 不写不删不 touch。不提交、不部署、不重启。

用法: backend\\.venv\\Scripts\\python.exe -X utf8 research\\factor-registration-fa5b-20261107\\f_a5b_two_shapes.py
退出码: 0 = 全部判据通过; 1 = 有判据失败。
"""
from __future__ import annotations

import hashlib
import json
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
NOW = "2026-11-07T16:20:00"
SUBDIR = Path("user_data") / "custom_factors"

RESULTS: list[dict] = []
EVIDENCE: dict[str, object] = {"cases": RESULTS}


def check(case: str, ok: bool, detail: str) -> bool:
    RESULTS.append({"case": case, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {case}: {detail}", flush=True)
    return bool(ok)


def snapshot(folder: Path) -> dict[str, dict]:
    """目录快照: 文件 → id / version / size / sha256 / mtime_ns / lang。只读。"""
    rows: dict[str, dict] = {}
    for path in sorted(folder.glob("*.json")):
        raw = path.read_bytes()
        definition = json.loads(raw.decode("utf-8"))
        rows[path.name] = {
            "id": definition.get("id"),
            "version": definition.get("version"),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "mtime_ns": path.stat().st_mtime_ns,
            "keys": sorted(definition.keys()),
            "lang": definition.get("lang"),
        }
    return rows


def prod_definitions() -> dict[str, dict]:
    """生产目录只读读取: 文件名 → 定义 (样本来源, 不写)。"""
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(PROD_DIR.glob("*.json"))
    }


def prep_dir(definitions: dict[str, dict]) -> Path:
    """临时 data_dir + user_data/custom_factors 这一层 (加载器会拼这一层)。"""
    root = Path(tempfile.mkdtemp(prefix="fa5b_"))
    target = root / SUBDIR
    target.mkdir(parents=True)
    for name, definition in definitions.items():
        (target / name).write_text(
            json.dumps(definition, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return root


def install_ext_configs(root: Path) -> None:
    """在临时 data_dir 里装两份竞价扩展字段配置, 再同步进注册表。

    6 个 auction 因子与 1 个 composite 引用 ext_auction_* 列, 没有这份配置时 DSL
    编译会以「未知标识符」拒绝 —— 那是测试环境缺 provider, 不是判等问题。这里按
    backend/tests/test_auction_factor_pack.py 的同一条路径装配置, 与生产一致。
    """
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


def clear_registry(ids: list[str]) -> None:
    for fid in sorted({i for i in ids if i}, key=lambda x: (not x.startswith("cf_"), x)):
        try:
            if get_factor(fid) is not None:
                unregister_factor(fid)
        except ValueError:
            pass


def api_shape(disk: dict) -> dict:
    """照 api/factors.py create_custom_factor / create_composite_factor 构造入参定义。

    与路由一致: 没有 lang, status 固定 draft, version 固定 1, 时间戳新给。
    """
    common = {
        "id": disk["id"],
        "version": 1,
        "label": disk["label"],
        "group": disk.get("group"),
        "description": disk.get("description", ""),
        "direction": disk.get("direction", "none"),
        "status": "draft",
        "created_at": NOW,
        "updated_at": NOW,
    }
    if str(disk.get("kind", "custom")) == "composite":
        return {"kind": "composite", "members": dict(disk["members"]), **common}
    return {"kind": "custom", "formula": disk["formula"], **common}


def one_unchanged_case(label: str, dir_defs: dict[str, dict], target: str, payload_fn) -> None:
    """在全新临时目录里对 target 跑一次 upsert, 比对「不变」五项。"""
    root = prep_dir(dir_defs)
    try:
        install_ext_configs(root)
        store.load_into_registry(root)
        folder = root / SUBDIR
        before_all = snapshot(folder)
        before = before_all[target]
        payload = payload_fn(dir_defs[target])
        try:
            result = store.upsert_definition(root, payload)
            error = ""
        except Exception as exc:  # noqa: BLE001 — 判据里要看到异常文本
            result, error = None, f"{type(exc).__name__}: {exc}"
        after_all = snapshot(folder)
        after = after_all[target]
        spec = get_factor(str(before["id"]))
        ok = (
            result is not None
            and result.get("unchanged") is True
            and result.get("version") == before["version"]
            and after["version"] == before["version"]
            and after["sha256"] == before["sha256"]
            and after["mtime_ns"] == before["mtime_ns"]
            and spec is not None
            and spec.version == before["version"]
        )
        check(
            label,
            ok,
            f"unchanged={None if result is None else result.get('unchanged')} "
            f"ret_v={None if result is None else result.get('version')} "
            f"disk {before['version']}→{after['version']} "
            f"sha_same={after['sha256'] == before['sha256']} "
            f"mtime_same={after['mtime_ns'] == before['mtime_ns']} "
            f"lang={after['lang']} spec_v={None if spec is None else spec.version} {error}",
        )
    finally:
        clear_registry([str(d.get("id")) for d in dir_defs.values()])
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    prod_before = snapshot(PROD_DIR)
    definitions = prod_definitions()
    print(f"生产样本 {len(definitions)} 个定义, 全部用例在临时 data_dir 内跑\n")

    # ── A 盘上形状 × 15 / B API 形状 × 15 ────────────────────────
    for name, definition in definitions.items():
        target = str(definition.get("id"))
        if str(definition.get("kind", "custom")) == "composite":
            members = sorted(definition["members"])
            dir_defs = {name: definition, **{f"{m}.json": definitions[f"{m}.json"] for m in members}}
        else:
            dir_defs = {name: definition}
        one_unchanged_case(
            f"A 盘上形状 {target}", dir_defs, name, lambda d: json.loads(json.dumps(d))
        )
        one_unchanged_case(f"B API 形状 {target}", dir_defs, name, api_shape)

    # ── C lang=python 同内容重提交 (含首次创建) ──────────────────
    py_def = {
        "id": "uf_fa5b_py",
        "kind": "custom",
        "version": 1,
        "label": "F-A5 python 口径",
        "group": "研究补充",
        "formula": "ctx.col('close') / ctx.col('open') - 1",
        "lang": "python",
        "warmup_bars": 1,
        "description": "lang=python 的盘上定义",
        "direction": "none",
        "status": "draft",
    }
    root = prep_dir({})
    try:
        folder = root / SUBDIR
        first = store.upsert_definition(root, dict(py_def))
        before = snapshot(folder)["uf_fa5b_py.json"]
        try:
            second = store.upsert_definition(root, dict(py_def))
            err = ""
        except Exception as exc:  # noqa: BLE001
            second, err = None, f"{type(exc).__name__}: {exc}"
        after = snapshot(folder)["uf_fa5b_py.json"]
        check(
            "C lang=python 盘上定义同内容重提交",
            first.get("unchanged") is False
            and second is not None
            and second.get("unchanged") is True
            and after["version"] == before["version"] == 1
            and after["sha256"] == before["sha256"]
            and after["lang"] == "python",
            f"first_v={first['version']} second_unchanged={None if second is None else second.get('unchanged')} "
            f"v {before['version']}→{after['version']} sha_same={after['sha256'] == before['sha256']} "
            f"lang={after['lang']} {err}",
        )

        # ── E 反向对照: python 定义改一个字符 ──────────────────────
        changed = dict(py_def)
        changed["formula"] = "ctx.col('close') / ctx.col('open') - 1.5"
        result = store.upsert_definition(root, changed)
        after2 = snapshot(folder)["uf_fa5b_py.json"]
        check(
            "E 反向对照 python 真改一字符",
            result.get("unchanged") is False
            and result.get("version") == 2
            and after2["version"] == 2
            and after2["lang"] == "python"
            and after2["sha256"] != after["sha256"],
            f"unchanged={result.get('unchanged')} v {after['version']}→{after2['version']} "
            f"lang={after2['lang']} sha_changed={after2['sha256'] != after['sha256']}",
        )
    finally:
        clear_registry(["uf_fa5b_py"])
        shutil.rmtree(root, ignore_errors=True)

    # ── D 反向对照: 盘上 lang=dsl 的定义被 API 形状真改一个字符 ──
    disk = definitions["uf_vol60.json"]
    root = prep_dir({"uf_vol60.json": disk})
    try:
        install_ext_configs(root)
        store.load_into_registry(root)
        folder = root / SUBDIR
        before = snapshot(folder)["uf_vol60.json"]
        payload = api_shape(disk)
        payload["formula"] = disk["formula"] + " + 0"
        result = store.upsert_definition(root, payload)
        after = snapshot(folder)["uf_vol60.json"]
        written = json.loads((folder / "uf_vol60.json").read_text(encoding="utf-8"))
        check(
            "D 反向对照 (无 lang 入参) 真改一字符",
            result.get("unchanged") is False
            and result.get("version") == before["version"] + 1
            and after["version"] == before["version"] + 1
            and after["sha256"] != before["sha256"]
            and written.get("lang") == "dsl"
            and written.get("formula") == payload["formula"]
            and written.get("created_at") == disk.get("created_at"),
            f"unchanged={result.get('unchanged')} v {before['version']}→{after['version']} "
            f"lang={written.get('lang')} formula={written.get('formula')!r} "
            f"created_at_kept={written.get('created_at') == disk.get('created_at')}",
        )
    finally:
        clear_registry([str(disk.get("id"))])
        shutil.rmtree(root, ignore_errors=True)

    # ── F 惰性附加字段: 不参与判等, 但写盘保留 ──────────────────
    disk = json.loads(json.dumps(definitions["uf_ma120.json"]))
    disk["tags"] = ["研究", "b0"]
    disk["unit"] = "currency"
    disk["scale_free"] = False
    root = prep_dir({"uf_ma120.json": disk})
    try:
        store.load_into_registry(root)
        folder = root / SUBDIR
        before = snapshot(folder)["uf_ma120.json"]
        result = store.upsert_definition(root, api_shape(disk))  # 入参无 tags/unit/scale_free
        after = snapshot(folder)["uf_ma120.json"]
        check(
            "F1 惰性附加字段不参与判等",
            result.get("unchanged") is True
            and after["version"] == before["version"] == 1
            and after["sha256"] == before["sha256"],
            f"unchanged={result.get('unchanged')} v {before['version']}→{after['version']} "
            f"sha_same={after['sha256'] == before['sha256']}",
        )
        payload = api_shape(disk)
        payload["formula"] = "ts_mean(close, 120) * 1.0000001"
        result2 = store.upsert_definition(root, payload)
        written = json.loads((folder / "uf_ma120.json").read_text(encoding="utf-8"))
        check(
            "F2 真改内容时附加字段被保留",
            result2.get("unchanged") is False
            and written.get("version") == 2
            and written.get("tags") == ["研究", "b0"]
            and written.get("unit") == "currency"
            and written.get("scale_free") is False
            and written.get("lang") == "dsl",
            f"unchanged={result2.get('unchanged')} v={written.get('version')} tags={written.get('tags')} "
            f"unit={written.get('unit')} scale_free={written.get('scale_free')} lang={written.get('lang')}",
        )
    finally:
        clear_registry([str(disk.get("id"))])
        shutil.rmtree(root, ignore_errors=True)

    # ── G fail-closed: 非法输入仍被拒, 文件字节不变 ─────────────
    disk = definitions["uf_ma120.json"]
    root = prep_dir({"uf_ma120.json": disk})
    try:
        store.load_into_registry(root)
        folder = root / SUBDIR
        before = snapshot(folder)["uf_ma120.json"]
        bad_payloads = {
            "G1 公式编译不过": {**api_shape(disk), "formula": "ts_mean(close,"},
            "G2 id 不合规": {**api_shape(disk), "id": "bad_id"},
            "G3 label 为空": {**api_shape(disk), "label": "  "},
            "G4 未知 lang": {**api_shape(disk), "lang": "sql"},
            "G5 status 非法": {**api_shape(disk), "status": "unknown"},
        }
        for label, payload in bad_payloads.items():
            try:
                store.upsert_definition(root, payload)
                raised = ""
            except ValueError as exc:
                raised = f"ValueError: {exc}"
            except Exception as exc:  # noqa: BLE001
                raised = f"{type(exc).__name__}: {exc}"
            after = snapshot(folder)["uf_ma120.json"]
            check(
                label,
                raised.startswith("ValueError") and after["sha256"] == before["sha256"],
                f"raised={raised[:80]} file_same={after['sha256'] == before['sha256']}",
            )
    finally:
        clear_registry([str(disk.get("id"))])
        shutil.rmtree(root, ignore_errors=True)

    # ── H status 变化算内容变化 ─────────────────────────────────
    disk = definitions["uf_ma200.json"]
    root = prep_dir({"uf_ma200.json": disk})
    try:
        store.load_into_registry(root)
        folder = root / SUBDIR
        before = snapshot(folder)["uf_ma200.json"]
        result = store.upsert_definition(root, {**api_shape(disk), "status": "active"})
        after = snapshot(folder)["uf_ma200.json"]
        written = json.loads((folder / "uf_ma200.json").read_text(encoding="utf-8"))
        check(
            "H status 变化 → version+1",
            result.get("unchanged") is False
            and after["version"] == before["version"] + 1
            and written.get("status") == "active"
            and written.get("lang") == "dsl",
            f"unchanged={result.get('unchanged')} v {before['version']}→{after['version']} "
            f"status={written.get('status')} lang={written.get('lang')}",
        )
    finally:
        clear_registry([str(disk.get("id"))])
        shutil.rmtree(root, ignore_errors=True)

    # ── I API 层: 盘上已有定义同内容重提交 ──────────────────────
    import app.api.factors as factors_api

    disk = definitions["uf_ma120.json"]
    root = prep_dir({"uf_ma120.json": disk})
    calls = {"trial": 0}
    original = factors_api._trial_nonempty

    def fake_trial(*_a, **_k):
        calls["trial"] += 1

    factors_api._trial_nonempty = fake_trial
    try:
        store.load_into_registry(root)
        folder = root / SUBDIR
        before = snapshot(folder)["uf_ma120.json"]
        request_stub = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            repo=SimpleNamespace(store=SimpleNamespace(data_dir=root)))))
        req = factors_api.CustomFactorCreateRequest(
            id=disk["id"], label=disk["label"], group=disk["group"],
            formula=disk["formula"], description=disk.get("description", ""),
            direction=disk.get("direction", "none"),
        )
        result = factors_api.create_custom_factor(req, request_stub)
        after = snapshot(folder)["uf_ma120.json"]
        check(
            "I1 API 同内容重提交 → unchanged=true, 不重跑试算",
            result.get("unchanged") is True
            and result.get("version") == before["version"] == 1
            and after["sha256"] == before["sha256"]
            and after["mtime_ns"] == before["mtime_ns"]
            and calls["trial"] == 0,
            f"unchanged={result.get('unchanged')} version={result.get('version')} "
            f"trial_calls={calls['trial']} sha_same={after['sha256'] == before['sha256']}",
        )
        req2 = factors_api.CustomFactorCreateRequest(
            id=disk["id"], label=disk["label"], group=disk["group"],
            formula=disk["formula"] + " + 0", description=disk.get("description", ""),
            direction=disk.get("direction", "none"),
        )
        result2 = factors_api.create_custom_factor(req2, request_stub)
        written = json.loads((folder / "uf_ma120.json").read_text(encoding="utf-8"))
        check(
            "I2 API 真改公式 → version+1, 走试算, lang 保留",
            result2.get("unchanged") is False
            and result2.get("version") == 2
            and calls["trial"] == 1
            and written.get("lang") == "dsl"
            and written.get("formula") == disk["formula"] + " + 0",
            f"unchanged={result2.get('unchanged')} version={result2.get('version')} "
            f"trial_calls={calls['trial']} lang={written.get('lang')}",
        )
    finally:
        factors_api._trial_nonempty = original
        clear_registry([str(disk.get("id"))])
        shutil.rmtree(root, ignore_errors=True)

    # ── J 生产目录前后对照 ─────────────────────────────────────
    prod_after = snapshot(PROD_DIR)
    names = sorted(set(prod_before) | set(prod_after))
    drift = [
        name for name in names
        if prod_before.get(name, {}).get("sha256") != prod_after.get(name, {}).get("sha256")
        or prod_before.get(name, {}).get("version") != prod_after.get(name, {}).get("version")
        or prod_before.get(name, {}).get("mtime_ns") != prod_after.get(name, {}).get("mtime_ns")
    ]
    check(
        "J 生产目录 json 前后逐字节一致",
        not drift and len(prod_after) == len(prod_before),
        f"files {len(prod_before)}→{len(prod_after)} drift={drift}",
    )

    # ── 汇总 ──────────────────────────────────────────────────
    passed = sum(1 for r in RESULTS if r["ok"])
    total = len(RESULTS)
    print("\n" + "=" * 100)
    print(f"判据: {passed}/{total} 通过")
    for row in RESULTS:
        if not row["ok"]:
            print(f"  FAILED {row['case']}: {row['detail']}")
    print("=" * 100)

    EVIDENCE["prod_before"] = prod_before
    EVIDENCE["prod_after"] = prod_after
    EVIDENCE["summary"] = {"passed": passed, "total": total}
    out = LOG_DIR / "f_a5b_evidence.json"
    out.write_text(json.dumps(EVIDENCE, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"证据: {out}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
