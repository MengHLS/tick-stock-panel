# -*- coding: utf-8 -*-
"""F-A5 附带风险探针：API 形状重存会抹掉哪些"非 API 字段"（审核方自写）。

用合成定义（不落生产目录），验证：
 1) lang="python" 的定义经 API 形状重存 → lang 是否丢失、语言是否被静默改成 dsl；
 2) unit / scale_free / stability / tags 等 API 未暴露的字段是否同样被判"内容变了"并丢失。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(REPO / "backend"))
SUBDIR = Path("user_data") / "custom_factors"


def main() -> int:
    from app.factors import store
    from app.factors.registry import isolated_registry

    root = Path(tempfile.mkdtemp(prefix="fa5_lang_"))
    d = root / SUBDIR
    d.mkdir(parents=True)

    with isolated_registry():
        # ---- 1) lang="python" 的已存定义 ----
        py_def = {
            "id": "uf_probe_py", "kind": "custom", "version": 1,
            "label": "探针python", "group": "自定义", "formula": 'ctx.col("close")',
            "lang": "python", "description": "", "direction": "none",
            "status": "draft", "created_at": store._now(), "updated_at": store._now(),
        }
        store.save_one(root, py_def)
        store.register_definition(py_def)
        print(f"PROBE|python_spec_lang={store.get_factor('uf_probe_py').lang}")

        api = {k: v for k, v in py_def.items() if k != "lang"}
        api["version"] = 1
        api["created_at"] = store._now()
        api["updated_at"] = store._now()
        try:
            res = store.upsert_definition(root, api)
            after = store._STORE.load_one(root, "uf_probe_py")
            print(f"PROBE|python_resave|unchanged={res['unchanged']}|v={res['version']}"
                  f"|file_lang={after.get('lang', '<absent>')}"
                  f"|registry_lang={store.get_factor('uf_probe_py').lang}")
        except Exception as exc:  # noqa: BLE001
            after = store._STORE.load_one(root, "uf_probe_py")
            print(f"PROBE|python_resave|REJECTED={type(exc).__name__}:{exc}"
                  f"|file_still_lang={after.get('lang', '<absent>')}"
                  f"|registry_lang={store.get_factor('uf_probe_py').lang}")

        # ---- 2) 带 API 未暴露字段的定义 ----
        rich = {
            "id": "uf_probe_rich", "kind": "custom", "version": 1,
            "label": "探针富字段", "group": "自定义", "formula": "ts_mean(close, 5)",
            "lang": "dsl", "description": "", "direction": "none", "status": "draft",
            "created_at": store._now(), "updated_at": store._now(),
            "unit": "ratio", "scale_free": False, "stability": "stable", "tags": ["x"],
        }
        store.save_one(root, rich)
        store.register_definition(rich)
        api2 = {  # API 形状：只有 create_custom_factor 构造的那些键
            "id": rich["id"], "kind": "custom", "version": 1, "label": rich["label"],
            "group": rich["group"], "formula": rich["formula"], "description": "",
            "direction": "none", "status": "draft",
            "created_at": store._now(), "updated_at": store._now(),
        }
        res2 = store.upsert_definition(root, api2)
        after2 = store._STORE.load_one(root, "uf_probe_rich")
        lost = sorted(set(rich) - set(after2))
        print(f"PROBE|rich_resave|unchanged={res2['unchanged']}|v={res2['version']}"
              f"|lost_keys={lost}")

        # ---- 3) content_signature 对"缺键 vs 显式 null"的判定 ----
        a = {"id": "x", "formula": "f", "lang": "dsl"}
        b = {"id": "x", "formula": "f", "lang": "dsl", "unit": None}
        print(f"PROBE|missing_vs_null_equal={store.content_signature(a) == store.content_signature(b)}"
              f"|num_int_float_equal="
              f"{store.content_signature({'id': 'x', 'v': 1}) == store.content_signature({'id': 'x', 'v': 1.0})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
