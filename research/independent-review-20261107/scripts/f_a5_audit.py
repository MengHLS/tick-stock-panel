# -*- coding: utf-8 -*-
"""F-A5 独立审核脚本 v2（审核方自写，不使用被审方脚本）。

判据：docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md §7.6 F-A5
      89,833 B / 914 行 / 全文 sha256 5eb9772411f723576b657f85af7c0aa26427137a41fb53b5774b935942565903

v1 勘误：store 的落盘路径是 ``data_dir/user_data/custom_factors/*.json``
（JsonDefinitionStore(subdir="user_data/custom_factors")，definitions.py:55-61），
v1 把临时目录直接当 data_dir 用，导致 load_one 恒为 None、写盘落在
tmp/user_data/custom_factors、而哈希取的是 tmp/*.json —— v1 的 T1/T2/T3 数字作废。
v2 起每个测试用独立的 root：root/user_data/custom_factors/*.json，并用
registry.isolated_registry() 隔离全局注册表。

纪律：生产目录 D:\\TSP\\data\\user_data\\custom_factors 只读（首尾 sha256+mtime 对照）。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(REPO / "backend"))

PROD = Path(r"D:\TSP\data\user_data\custom_factors")
SUBDIR = Path("user_data") / "custom_factors"
TARGETS = [
    "uf_vol60",
    "uf_ma120",
    "uf_ma200",
    "uf_prior_high_20",
    "uf_prior_high_55",
    "uf_prior_high_250",
    "uf_prior_low_10",
    "uf_prior_vol_20",
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def snap(dirpath: Path) -> dict[str, tuple[str, int]]:
    return {p.name: (sha(p), p.stat().st_mtime_ns) for p in sorted(dirpath.glob("*.json"))}


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def fresh_root(ids) -> tuple[Path, Path]:
    """建 root/user_data/custom_factors 并复制指定定义；返回 (root, def_dir)。"""
    root = Path(tempfile.mkdtemp(prefix="fa5v2_"))
    d = root / SUBDIR
    d.mkdir(parents=True)
    for fid in ids:
        shutil.copy2(PROD / f"{fid}.json", d / f"{fid}.json")
    return root, d


def api_shape(disk: dict, store) -> dict:
    """按 backend/app/api/factors.py:332-352 create_custom_factor 的字典构造复刻。

    字段只有 id/kind/version/label/group/formula/description/direction/status/
    created_at/updated_at —— **没有 lang**。
    """
    return {
        "id": disk["id"],
        "kind": "custom",
        "version": 1,
        "label": disk["label"],
        "group": disk["group"],
        "formula": disk["formula"],
        "description": disk.get("description", ""),
        "direction": disk.get("direction", "none"),
        "status": "draft",
        "created_at": store._now(),
        "updated_at": store._now(),
    }


def main() -> int:
    from app.factors import store
    from app.factors.registry import isolated_registry

    prod_before = snap(PROD)
    print(f"P0|prod_files={len(prod_before)}|prod_dir={PROD}")

    # ================= T0/T1：盘上形状（含 lang）同内容二次注册 =================
    root, ddir = fresh_root(TARGETS)
    print(f"P0|root_t1={root}")
    with isolated_registry():
        loaded = store.load_into_registry(root)
        print(f"T0|load_into_registry={len(loaded)}|ids={sorted(loaded)}")
        for fid in TARGETS:
            spec = store.get_factor(fid)
            print(
                f"T0|{fid}|registry_version={getattr(spec, 'version', None)}"
                f"|disk_version={load_json(ddir / (fid + '.json'))['version']}"
            )
        t1_fail = 0
        for fid in TARGETS:
            p = ddir / (fid + ".json")
            defn = load_json(p)  # 与盘上同源（含 lang:"dsl"）
            b0, m0 = sha(p), p.stat().st_mtime_ns
            res = store.upsert_definition(root, defn)
            b1, m1 = sha(p), p.stat().st_mtime_ns
            ok = res["unchanged"] is True and res["version"] == 1 and b0 == b1 and m0 == m1
            t1_fail += 0 if ok else 1
            print(
                f"T1|{fid}|unchanged={res['unchanged']}|returned_version={res['version']}"
                f"|bytes_same={b0 == b1}|mtime_same={m0 == m1}|PASS={ok}"
            )
        print(f"T1|summary|pass={len(TARGETS) - t1_fail}/{len(TARGETS)}")

        # ============ T2：API 形状（无 lang）打到盘上形状 ============
        for fid in TARGETS:
            p = ddir / (fid + ".json")
            disk = load_json(PROD / f"{fid}.json")  # 原始盘上语义
            b0 = sha(p)
            res = store.upsert_definition(root, api_shape(disk, store))
            after = load_json(p)
            print(
                f"T2|{fid}|unchanged={res['unchanged']}|returned_version={res['version']}"
                f"|file_version={after['version']}|file_lang={after.get('lang', '<absent>')}"
                f"|bytes_changed={b0 != sha(p)}"
            )

        # ============ T5：语义等价证明 ============
        sample = load_json(PROD / "uf_ma120.json")
        with_lang = dict(sample)
        no_lang = {k: v for k, v in sample.items() if k != "lang"}
        sig_same = store.content_signature(with_lang) == store.content_signature(no_lang)
        spec_a, spec_b = store.to_spec(with_lang), store.to_spec(no_lang)
        print(
            f"T5|default_lang_for_missing={spec_b.lang}|content_signature_equal={sig_same}"
            f"|to_spec_equal={spec_a == spec_b}|warmup_a={spec_a.warmup_bars}|warmup_b={spec_b.warmup_bars}"
        )
        print(f"T5|sig_with_lang={store.content_signature(with_lang)[:120]}")
        print(f"T5|sig_no_lang__={store.content_signature(no_lang)[:120]}")

    # ================= T3/T4：交替与收敛 =================
    root3, ddir3 = fresh_root(["uf_ma120"])
    p3 = ddir3 / "uf_ma120.json"
    with isolated_registry():
        store.load_into_registry(root3)
        seq = []
        for i in range(4):
            if i % 2 == 0:
                incoming, tag = load_json(PROD / "uf_ma120.json"), "disk(lang)"
            else:
                incoming, tag = api_shape(load_json(PROD / "uf_ma120.json"), store), "api(no-lang)"
            res = store.upsert_definition(root3, incoming)
            seq.append((tag, res["version"], res["unchanged"], load_json(p3)["version"],
                        load_json(p3).get("lang", "<absent>")))
        print("T3|ping-pong|" + " -> ".join(
            f"{t}:ret_v{v}:unchanged={u}:file_v{fv}:lang={lg}" for t, v, u, fv, lg in seq))
        r1 = store.upsert_definition(root3, api_shape(load_json(PROD / "uf_ma120.json"), store))
        r2 = store.upsert_definition(root3, api_shape(load_json(PROD / "uf_ma120.json"), store))
        print(f"T4|same_api_shape_twice|first=unchanged={r1['unchanged']},v={r1['version']}"
              f"|second=unchanged={r2['unchanged']},v={r2['version']}")

    # ================= T6：负向对照（真改公式必须被识别） =================
    root6, ddir6 = fresh_root(["uf_vol60"])
    p6 = ddir6 / "uf_vol60.json"
    with isolated_registry():
        store.load_into_registry(root6)
        base = load_json(p6)
        b0 = sha(p6)
        r = store.upsert_definition(root6, dict(base))
        print(f"T6|same|unchanged={r['unchanged']}|v={r['version']}|bytes_changed={sha(p6) != b0}")
        changed = dict(base)
        changed["formula"] = "ts_std(close, 60) / ts_mean(close, 60)"
        b1 = sha(p6)
        r = store.upsert_definition(root6, changed)
        print(f"T6|formula_changed|unchanged={r['unchanged']}|v={r['version']}"
              f"|bytes_changed={sha(p6) != b1}|file_formula={load_json(p6)['formula']}")

        # ============ T7：register_definition 层 ============
        try:
            store.register_definition(dict(base))
            store.register_definition(dict(base))
            print(f"T7|same_content_twice|version={store.get_factor('uf_vol60').version}|no_exception")
        except Exception as exc:  # noqa: BLE001
            print(f"T7|same_content_twice|EXC={type(exc).__name__}:{exc}")
        bumped = dict(base)
        bumped["label"] = base["label"] + "改"
        try:
            store.register_definition(bumped)
            print("T7|same_version_diff_content|accepted(未拒绝)")
        except Exception as exc:  # noqa: BLE001
            print(f"T7|same_version_diff_content|rejected={type(exc).__name__}:{exc}")

    # ================= T8：端点层（data_dir 指向临时目录） =================
    from app.api import factors as api_mod

    root8, ddir8 = fresh_root(["uf_vol60"])
    p8 = ddir8 / "uf_vol60.json"
    trial_calls = {"n": 0}
    orig_trial = api_mod._trial_nonempty

    def stub_trial(request, formula, asset_type="stock"):
        trial_calls["n"] += 1

    api_mod._trial_nonempty = stub_trial
    try:
        with isolated_registry():
            store.load_into_registry(root8)
            req_obj = SimpleNamespace(
                app=SimpleNamespace(state=SimpleNamespace(
                    repo=SimpleNamespace(store=SimpleNamespace(data_dir=root8))))
            )
            disk = load_json(PROD / "uf_vol60.json")
            body = api_mod.CustomFactorCreateRequest(
                id="uf_vol60", label=disk["label"], group=disk["group"],
                formula=disk["formula"], description=disk.get("description", ""),
                direction=disk.get("direction", "none"),
            )
            for i in (1, 2, 3):
                r = api_mod.create_custom_factor(body, req_obj)
                after = load_json(p8)
                print(f"T8|post#{i}|resp_version={r.get('version')}|unchanged={r.get('unchanged')}"
                      f"|trial_calls={trial_calls['n']}|file_version={after['version']}"
                      f"|file_lang={after.get('lang', '<absent>')}")
    finally:
        api_mod._trial_nonempty = orig_trial

    # ================= T9：生产目录未变 =================
    prod_after = snap(PROD)
    same = prod_before == prod_after
    print(f"T9|prod_unchanged={same}|files_before={len(prod_before)}|files_after={len(prod_after)}")
    if not same:
        for k in sorted(set(prod_before) | set(prod_after)):
            if prod_before.get(k) != prod_after.get(k):
                print(f"T9|CHANGED|{k}|before={prod_before.get(k)}|after={prod_after.get(k)}")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
