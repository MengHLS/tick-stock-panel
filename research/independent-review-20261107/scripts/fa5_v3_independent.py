# -*- coding: utf-8 -*-
"""F-A5 独立判定 v3（审核方自写，零复用被审方脚本）。

绑定对象（本轮实测 mtime/sha，见报告 §0）：
  backend/app/factors/store.py      2026-11-07 16:33:52
  backend/app/api/factors.py        2026-11-07 16:33:57
判据：docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md §7.6 F-A5
  （冻结四元组 89,833 B / 914 行 / 全文 sha256 5eb9772411f723576b657f85af7c0aa26427137a41fb53b5774b935942565903）

判据清单（brief 1-5）：
  1 两形状 × 全部落盘定义（15 个）同内容重提交 → unchanged/版本/字节/mtime/lang
  2 lang="python" 定义同内容重提交
  3 反向对照：真改一字符 → unchanged=False、v+1、盘上 lang/unit/tags 仍在
  4 status 语义：draft→active 视为内容变化；create 形状重提交 active 定义
  5 环境依赖：未注册 ext_auction_* 的进程里跑 6 个 auction 因子

纪律：生产目录 D:\\TSP\\data 只读（首尾 sha256+mtime 对照）；写操作只落在 tempfile 目录。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(r"C:\work\sourcecode\tick-stock-panel\backend")
PROD_ROOT = Path(r"D:\TSP\data")
PROD = PROD_ROOT / "user_data" / "custom_factors"
OUT_DIR = Path(r"C:\work\sourcecode\tick-stock-panel\research\independent-review-20261107\artifacts")
sys.path.insert(0, str(BACKEND))

STORE_FILES = [BACKEND / "app" / "factors" / "store.py", BACKEND / "app" / "api" / "factors.py"]


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snap(paths) -> dict:
    out = {}
    for p in sorted(Path(x) for x in paths):
        out[p.name] = {
            "size": p.stat().st_size,
            "mtime_ns": p.stat().st_mtime_ns,
            "sha256": sha(p),
        }
    return out


def state_of(p: Path) -> dict:
    return {"size": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns, "sha256": sha(p)}


# ── 环境 ────────────────────────────────────────────────────────────────
from app.factors import store  # noqa: E402
from app.factors.ext_factors import ensure_synced  # noqa: E402
from app.factors.registry import (  # noqa: E402
    all_factors,
    get_factor,
    isolated_registry,
)

RESULTS: list[dict] = []


def rec(case: str, verdict: str, **kv):
    row = {"case": case, "verdict": verdict, **kv}
    RESULTS.append(row)
    print(json.dumps(row, ensure_ascii=False, default=str))


def fresh_root(tag: str) -> Path:
    """新建一个 data_dir 树：root/user_data/custom_factors/，可选复制落盘定义。"""
    root = Path(tempfile.mkdtemp(prefix=f"fa5v3_{tag}_"))
    (root / "user_data" / "custom_factors").mkdir(parents=True, exist_ok=True)
    return root


def disk_path(root: Path, fid: str) -> Path:
    return root / "user_data" / "custom_factors" / f"{fid}.json"


def copy_defs(root: Path, ids: list[str] | None = None) -> list[str]:
    ids = ids if ids is not None else sorted(p.stem for p in PROD.glob("*.json"))
    for fid in ids:
        shutil.copyfile(PROD / f"{fid}.json", disk_path(root, fid))
    return ids


PROD_DEFS = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in PROD.glob("*.json")}
ORDER = [  # 依赖顺序：先 custom，再 composite（cf_ 引用 uf_auction_*）
    "uf_auction_post0920_match_growth", "uf_auction_tail_imbalance",
    "uf_auction_tail_match_growth", "uf_auction_volume_surprise",
    "uf_auction_volume_vs_prev", "uf_ma120", "uf_ma200", "uf_prior_high_20",
    "uf_prior_high_250", "uf_prior_high_55", "uf_prior_low_10",
    "uf_prior_vol_20", "uf_vol60", "uf_dist_prior_high_250",
    "cf_auction_resonance",
]
assert set(ORDER) == set(PROD_DEFS), (sorted(set(ORDER) ^ set(PROD_DEFS)))

# API 形状 = create_custom_factor / create_composite_factor 构造的键集（16:33 版：无 status）
API_KEYS_CUSTOM = ["id", "kind", "version", "label", "group", "formula", "description", "direction"]
API_KEYS_COMP = ["id", "kind", "version", "label", "group", "members", "description", "direction"]


def api_shape(d: dict, with_status: bool = False) -> dict:
    kind = str(d.get("kind", "custom"))
    keys = API_KEYS_COMP if kind == "composite" else API_KEYS_CUSTOM
    out = {k: d[k] for k in keys if k in d}
    out["version"] = 1  # 路由硬编码（版本由 upsert 裁决）
    out.setdefault("group", "自定义" if kind == "custom" else "组合")
    out.setdefault("description", "")
    out.setdefault("direction", "none")
    if with_status:
        out["status"] = "draft"  # 16:23 版路由的形状
    now = store._now()
    out["created_at"] = now
    out["updated_at"] = now
    return out


def preload(root: Path, skip: str | None = None) -> tuple[list[str], list[str]]:
    """模拟启动期 load_into_registry（不调 ensure_synced(root)，避免清掉 ext_）。

    skip 指定时跳过该 id（构造「注册表里缺这个 id」的态，从盘上仍可读取）。
    """
    ok, deferred = [], [d for d in store.load_all(root) if str(d["id"]) != skip]
    for _ in range(3):
        nxt = []
        for d in deferred:
            try:
                store.register_definition(d)
                ok.append(str(d["id"]))
            except ValueError:
                nxt.append(d)
        deferred = nxt
        if not deferred:
            break
    return ok, [str(d["id"]) for d in deferred]


def main() -> int:
    t0 = time.time()
    stamp_start = {p.name: state_of(p) for p in STORE_FILES}
    prod_before = snap(PROD.glob("*.json"))
    print(json.dumps({"stage": "start", "store_files": stamp_start,
                      "prod_n": len(prod_before)}, ensure_ascii=False, indent=1))

    ensure_synced(PROD_ROOT)  # 扩展列 = 生产配置（只读），进进程注册表供 isolated 快照继承
    base_count = len(all_factors())
    ext_n = sum(1 for s in all_factors() if s.id.startswith("ext_"))
    rec("T0_env", "info", all_factors=base_count, ext=ext_n,
        auction_ext_registered=get_factor("ext_auction_preopen_last_imbalance") is not None)

    # ── T1 盘上形状 × 15（注册表缺目标 / 已含目标 两态）────────────────
    for mode in ("minus_target", "preloaded"):
        for fid in ORDER:
            d = PROD_DEFS[fid]
            root = fresh_root(f"{mode}_{fid}"[:40])
            copy_defs(root)  # 15 个文件全在盘上（组合成员依赖可解析），只重提交 fid
            f = disk_path(root, fid)
            before = state_of(f)
            with isolated_registry():
                ok, bad = preload(root, skip=None if mode == "preloaded" else fid)
                res = store.upsert_definition(root, json.loads(json.dumps(d)))
                after = state_of(f)
                same_bytes = before["sha256"] == after["sha256"]
                same_mtime = before["mtime_ns"] == after["mtime_ns"]
                cur = json.loads(f.read_text(encoding="utf-8"))
                verdict = "PASS" if (res["unchanged"] is True
                                     and res["version"] == int(d.get("version", 1))
                                     and same_bytes and same_mtime
                                     and cur.get("lang") == d.get("lang")) else "FAIL"
                rec(f"T1_{mode}_{fid}", verdict,
                    unchanged=res["unchanged"], version_in=int(d.get("version", 1)),
                    version_out=res["version"], bytes_same=same_bytes,
                    mtime_same=same_mtime, lang_before=d.get("lang"),
                    lang_after=cur.get("lang"), size=after["size"],
                    preload_fail=bad)

    # ── T2 API 形状 × 15（16:33 形状：无 status）────────────────────────
    for fid in ORDER:
        d = PROD_DEFS[fid]
        root = fresh_root(f"api_{fid}"[:40])
        copy_defs(root)
        f = disk_path(root, fid)
        before = state_of(f)
        with isolated_registry():
            preload(root)
            res = store.upsert_definition(root, api_shape(d))
            after = state_of(f)
            cur = json.loads(f.read_text(encoding="utf-8"))
            verdict = "PASS" if (res["unchanged"] is True
                                 and res["version"] == int(d.get("version", 1))
                                 and before["sha256"] == after["sha256"]
                                 and before["mtime_ns"] == after["mtime_ns"]
                                 and cur.get("lang") == d.get("lang")) else "FAIL"
            rec(f"T2_api_{fid}", verdict, unchanged=res["unchanged"],
                version_in=int(d.get("version", 1)), version_out=res["version"],
                bytes_same=before["sha256"] == after["sha256"],
                mtime_same=before["mtime_ns"] == after["mtime_ns"],
                lang_after=cur.get("lang"), len_diff=len(cur) - len(d))

    # ── T2b 对称性：两侧签名互等（15 例 × 双向）────────────────────────
    sym_root = fresh_root("sym")
    copy_defs(sym_root)
    with isolated_registry():
        preload(sym_root)  # 组合因子需要成员在册才能投影
        asym = []
        for fid in ORDER:
            d = PROD_DEFS[fid]
            a = api_shape(d)
            s1 = store.content_signature(d) == store.content_signature(a)
            s2 = store.is_same_content(d, a)
            s3 = store.is_same_content(a, d)
            if not (s1 and s2 and s3):
                asym.append({"id": fid, "sig_eq": s1, "d_to_a": s2, "a_to_d": s3})
        rec("T2b_symmetry", "PASS" if not asym else "FAIL", cases=len(ORDER), asymmetric=asym)
        # 任一侧改 description 必须双向判不等
        flip = []
        for fid in ORDER:
            d = PROD_DEFS[fid]
            a = api_shape(d)
            a["description"] = (d.get("description") or "") + "x"
            d2 = dict(d)
            d2["description"] = (d.get("description") or "") + "y"
            if store.is_same_content(d, a) or store.is_same_content(a, d2):
                flip.append(fid)
        rec("T2b_neg", "PASS" if not flip else "FAIL", leaked=flip)

    # ── T2c API 形状与路由源码绑定（AST 提取定义字典的键集）──────────────
    import ast
    src = (BACKEND / "app" / "api" / "factors.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    route_keys = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in (
                "create_custom_factor", "create_composite_factor"):
            keys = None
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == "definition" for t in sub.targets) \
                        and isinstance(sub.value, ast.Dict):
                    keys = [k.value for k in sub.value.keys if isinstance(k, ast.Constant)]
            route_keys[node.name] = keys
    my_custom = api_shape(PROD_DEFS["uf_vol60"]).keys()
    my_comp = api_shape(PROD_DEFS["cf_auction_resonance"]).keys()
    ok_custom = set(route_keys.get("create_custom_factor") or []) <= set(my_custom)
    ok_comp = set(route_keys.get("create_composite_factor") or []) <= set(my_comp)
    rec("T2c_shape_binding", "PASS" if (ok_custom and ok_comp) else "FAIL",
        route_custom=sorted(route_keys.get("create_custom_factor") or []),
        route_composite=sorted(route_keys.get("create_composite_factor") or []),
        my_custom=sorted(my_custom), my_composite=sorted(my_comp))

    # ── T3 lang=python ─────────────────────────────────────────────────
    py_def = {
        "id": "uf_py_probe", "kind": "custom", "version": 1,
        "label": "审核用 py 探针", "group": "审核",
        "formula": '(ctx.col("close") / ctx.col("close").shift(1) - 1).rolling_std(60)',
        "lang": "python", "warmup_bars": 80, "unit": "none",
        "tags": ["audit", "py"], "scale_free": True,
        "description": "审核自建，仅临时目录", "direction": "none", "status": "draft",
        "created_at": store._now(), "updated_at": store._now(),
    }
    root = fresh_root("py")
    f = disk_path(root, "uf_py_probe")
    with isolated_registry():
        r1 = store.upsert_definition(root, json.loads(json.dumps(py_def)))
        b1 = state_of(f)
        r2 = store.upsert_definition(root, json.loads(json.dumps(py_def)))
        a2 = state_of(f)
        cur = json.loads(f.read_text(encoding="utf-8"))
        verdict = "PASS" if (r1["unchanged"] is False and r2["unchanged"] is True
                             and r2["version"] == 1 and b1["sha256"] == a2["sha256"]
                             and b1["mtime_ns"] == a2["mtime_ns"]
                             and cur.get("lang") == "python"
                             and cur.get("warmup_bars") == 80) else "FAIL"
        rec("T3_python_same", verdict, first_unchanged=r1["unchanged"],
            second_unchanged=r2["unchanged"], version=r2["version"],
            bytes_same=b1["sha256"] == a2["sha256"],
            mtime_same=b1["mtime_ns"] == a2["mtime_ns"],
            lang=cur.get("lang"), warmup=cur.get("warmup_bars"),
            unit=cur.get("unit"), tags=cur.get("tags"))

        # T3b API 形状（无 lang）重存 python 定义
        try:
            r3 = store.upsert_definition(root, api_shape(py_def))
            rec("T3b_api_shape_python", "DEFECT" if not r3["unchanged"] else "PASS",
                unchanged=r3["unchanged"], version=r3["version"], error=None)
        except Exception as exc:  # noqa: BLE001
            rec("T3b_api_shape_python", "DEFECT", error_type=type(exc).__name__, error=str(exc)[:160])
        # T3b2 诊断：为何 API 形状被归为「变了」
        probe = {}
        for tag, obj in (("stored", json.loads(f.read_text(encoding="utf-8"))), ("api", api_shape(py_def))):
            try:
                store.content_signature(obj)
                probe[tag] = "ok"
            except Exception as exc:  # noqa: BLE001
                probe[tag] = f"{type(exc).__name__}: {exc}"[:120]
        rec("T3b2_probe", "OBSERVE", sig_status=probe,
            same=store.is_same_content(json.loads(f.read_text(encoding="utf-8")), api_shape(py_def)))

        # T3c API 形状 + 显式 lang=python，但省略 warmup_bars（声明值 80 > 推断 61）
        s = api_shape(py_def)
        s["lang"] = "python"
        try:
            r4 = store.upsert_definition(root, s)
            cur2 = json.loads(f.read_text(encoding="utf-8"))
            rec("T3c_python_warmup_omitted", "OBSERVE", unchanged=r4["unchanged"],
                version=r4["version"], disk_warmup=cur2.get("warmup_bars"),
                disk_lang=cur2.get("lang"))
        except Exception as exc:  # noqa: BLE001
            rec("T3c_python_warmup_omitted", "RAISE", error_type=type(exc).__name__,
                error=str(exc)[:160])

    # ── T4 反向对照 ─────────────────────────────────────────────────────
    d = PROD_DEFS["uf_vol60"]
    root = fresh_root("neg")
    copy_defs(root, ["uf_vol60"])
    f = disk_path(root, "uf_vol60")
    b = state_of(f)
    changed = json.loads(json.dumps(d))
    changed["formula"] = changed["formula"].replace(", 60)", ", 61)")
    with isolated_registry():
        preload(root)
        res = store.upsert_definition(root, changed)
        after = state_of(f)
        cur = json.loads(f.read_text(encoding="utf-8"))
        verdict = "PASS" if (res["unchanged"] is False and res["version"] == 2
                             and after["sha256"] != b["sha256"]
                             and cur.get("lang") == "dsl"
                             and cur.get("formula") == changed["formula"]) else "FAIL"
        rec("T4_reverse_formula", verdict, unchanged=res["unchanged"], version=res["version"],
            bytes_changed=after["sha256"] != b["sha256"], lang=cur.get("lang"),
            mtime_changed=after["mtime_ns"] != b["mtime_ns"])

        # T4b 非 API 存储字段在真改内容后不被抹掉
        rich = json.loads(json.dumps(d))
        rich.update({"id": "uf_rich_probe", "unit": "pct", "tags": ["audit"],
                     "scale_free": True, "note": "自定义附加键"})
        root2 = fresh_root("rich")
        f2 = disk_path(root2, "uf_rich_probe")
        store.upsert_definition(root2, json.loads(json.dumps(rich)))
        rich2 = json.loads(json.dumps(rich))
        rich2["formula"] = rich2["formula"].replace(", 60)", ", 62)")
        r = store.upsert_definition(root2, rich2)
        cur2 = json.loads(f2.read_text(encoding="utf-8"))
        keep = all(cur2.get(k) == rich.get(k) for k in ("unit", "tags", "scale_free", "note", "lang"))
        rec("T4b_extra_fields_kept", "PASS" if (r["unchanged"] is False and r["version"] == 2 and keep) else "FAIL",
            version=r["version"], kept=keep, unit=cur2.get("unit"), tags=cur2.get("tags"),
            scale_free=cur2.get("scale_free"), note=cur2.get("note"))

    # ── T5 status 语义：draft → active 视为内容变化 ─────────────────────
    root = fresh_root("status")
    copy_defs(root, ["uf_vol60"])
    f = disk_path(root, "uf_vol60")
    with isolated_registry():
        preload(root)
        act = json.loads(json.dumps(d))
        act["status"] = "active"
        r1 = store.upsert_definition(root, act)
        cur = json.loads(f.read_text(encoding="utf-8"))
        r2 = store.upsert_definition(root, json.loads(json.dumps(act)))
        cur2 = json.loads(f.read_text(encoding="utf-8"))
        spec = get_factor("uf_vol60")
        rec("T5_draft_to_active", "PASS" if (r1["unchanged"] is False and r1["version"] == 2
                                            and cur["status"] == "active"
                                            and r2["unchanged"] is True and r2["version"] == 2
                                            and spec is not None and spec.stability == "stable") else "FAIL",
            first_unchanged=r1["unchanged"], version_after=r1["version"],
            disk_status=cur["status"], second_unchanged=r2["unchanged"],
            second_version=r2["version"], stability=spec.stability if spec else None,
            disk_status_after=cur2["status"])

        # ── T6 create 形状（16:33：无 status）重提交 active 定义 ────────
        r3 = store.upsert_definition(root, api_shape(d))
        cur3 = json.loads(f.read_text(encoding="utf-8"))
        rec("T6_create_shape_vs_active", "PASS" if (r3["unchanged"] is True
                                                    and r3["version"] == 2
                                                    and cur3["status"] == "active") else "FAIL",
            unchanged=r3["unchanged"], version=r3["version"], disk_status=cur3["status"],
            lang=cur3.get("lang"))

        # ── T6b 旧 16:23 形状（显式 status="draft"）重提交 active 定义 ──
        r4 = store.upsert_definition(root, api_shape(d, with_status=True))
        cur4 = json.loads(f.read_text(encoding="utf-8"))
        rec("T6b_old_shape_explicit_draft", "OBSERVE", unchanged=r4["unchanged"],
            version=r4["version"], disk_status=cur4["status"])

    # ── T7 环境依赖：无 ext_auction_* 的进程 ───────────────────────────
    bare = Path(tempfile.mkdtemp(prefix="fa5v3_bare_"))
    (bare / "user_data" / "custom_factors").mkdir(parents=True, exist_ok=True)
    copy_defs(bare, ["uf_auction_tail_imbalance"])
    f = disk_path(bare, "uf_auction_tail_imbalance")
    b = state_of(f)
    sub = f"""
import json, sys
sys.path.insert(0, r"{BACKEND}")
from pathlib import Path
from app.factors import store
from app.factors.ext_factors import ensure_synced
from app.factors.registry import _REGISTRY, get_factor, unregister_factor
root = Path(r"{bare}")
ensure_synced(root)                      # 无 ext_data 目录 → 期望清空 ext_*
ext_left = [f for f in _REGISTRY if f.startswith("ext_auction_")]
d = json.loads((root/"user_data"/"custom_factors"/"uf_auction_tail_imbalance.json").read_text(encoding="utf-8"))
out = {{"ext_auction_left": len(ext_left), "probe": get_factor("ext_auction_preopen_last_imbalance") is not None}}
try:
    r = store.upsert_definition(root, d)
    out.update({{"raised": None, "unchanged": r["unchanged"], "version": r["version"]}})
except Exception as e:
    out.update({{"raised": type(e).__name__, "msg": str(e)[:200], "unchanged": None}})
print(json.dumps(out, ensure_ascii=False))
"""
    env = dict(os.environ)
    env["DATA_DIR"] = str(bare)
    p = subprocess.run([sys.executable, "-c", sub], capture_output=True, text=True,
                       env=env, encoding="utf-8", errors="replace")
    out = None
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        pass
    a = state_of(f)
    rec("T7_bare_env_auction", "PASS" if (p.returncode == 0 and out and out.get("raised") == "ValueError"
                                          and a["sha256"] == b["sha256"]) else "FAIL",
        exit=p.returncode, parsed=out, bytes_same=a["sha256"] == b["sha256"],
        mtime_same=a["mtime_ns"] == b["mtime_ns"], stderr=p.stderr.strip()[-200:])

    # ── T10 register_definition 幂等跳过的副作用（§7.4 ②）──────────────
    root = fresh_root("reg")
    copy_defs(root, ["uf_vol60"])
    with isolated_registry():
        d0 = json.loads(json.dumps(PROD_DEFS["uf_vol60"]))
        e1 = e2 = None
        try:
            store.register_definition(json.loads(json.dumps(d0)))
            store.register_definition(json.loads(json.dumps(d0)))  # 二次同内容
        except ValueError as exc:
            e2 = str(exc)
        v_after_dup = get_factor("uf_vol60").version
        bad = json.loads(json.dumps(d0))
        bad["formula"] = bad["formula"].replace(", 60)", ", 62)")  # 内容变、版本未提
        try:
            store.register_definition(bad)
            e1 = "NO-RAISE"
        except ValueError as exc:
            e1 = str(exc)
        rec("T10_registry_gate",
            "PASS" if (e2 is None and v_after_dup == 1 and e1 and e1 != "NO-RAISE") else "FAIL",
            dup_raise=e2, version_after_dup=v_after_dup, changed_same_version=e1)
        # 启动期二次 load_into_registry 不告警、不抬版
        r1 = store.load_into_registry(root)
        v1 = get_factor("uf_vol60").version
        r2 = store.load_into_registry(root)
        v2 = get_factor("uf_vol60").version
        rec("T10b_double_startup", "PASS" if (len(r1) == 1 and len(r2) == 1 and v1 == v2 == 1) else "FAIL",
            first=r1, second=r2, v_after=[v1, v2])

        # ── T11 非法盘上定义：unchanged 分支不得静默返回成功（§7.4 ④）──
        root3 = fresh_root("illegal")
        bad_def = {"id": "uf_bad_probe", "kind": "custom", "version": 1, "label": "",
                   "group": "审核", "formula": "close", "lang": "dsl", "status": "draft"}
        p3 = disk_path(root3, "uf_bad_probe")
        p3.write_text(json.dumps(bad_def, ensure_ascii=False, indent=2), encoding="utf-8")
        b3 = state_of(p3)
        try:
            store.upsert_definition(root3, json.loads(json.dumps(bad_def)))
            rec("T11_illegal_disk", "FAIL", raised=None)
        except ValueError as exc:
            a3 = state_of(p3)
            rec("T11_illegal_disk", "PASS" if a3["sha256"] == b3["sha256"] else "FAIL",
                raised="ValueError", msg=str(exc)[:100],
                bytes_same=a3["sha256"] == b3["sha256"])

    # ── T8 生产目录只读核对 ────────────────────────────────────────────
    prod_after = snap(PROD.glob("*.json"))
    drift = [k for k in set(prod_before) | set(prod_after)
             if prod_before.get(k) != prod_after.get(k)]
    rec("T8_prod_unchanged", "PASS" if not drift else "FAIL", n=len(prod_after), drift=drift)

    stamp_end = {p.name: state_of(p) for p in STORE_FILES}
    rec("T9_impl_version_stable", "PASS" if stamp_start == stamp_end else "FAIL",
        start={k: {"mtime": v["mtime_ns"], "sha": v["sha256"][:16]} for k, v in stamp_start.items()},
        end={k: {"mtime": v["mtime_ns"], "sha": v["sha256"][:16]} for k, v in stamp_end.items()})

    fails = [r for r in RESULTS if r["verdict"] == "FAIL"]
    defects = [r for r in RESULTS if r["verdict"] == "DEFECT"]
    rec("SUMMARY", "FAIL" if fails else "PASS", total=len(RESULTS),
        fail=len(fails), fail_cases=[r["case"] for r in fails],
        defects=[r["case"] for r in defects],
        elapsed_s=round(time.time() - t0, 1))
    (OUT_DIR / "fa5v3_results.json").write_text(
        json.dumps({"store_files": stamp_start, "prod_before": prod_before,
                    "prod_after": prod_after, "results": RESULTS},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
