# -*- coding: utf-8 -*-
"""Q1/Q2 独立取证（审核方自写）。

Q1  注册表载入路径事实：未调 load_into_registry 时 all_factors() 计数与 8 只 uf_*
    是否 MISSING；load_into_registry(Path) 之后计数与命中；传 str 的行为。
    以及 app/main.py:221 是否真的在启动期调用它（源码 + 行号）。
Q2  backend/app/custom/research_factor_pack/ 动态加载后注册了哪些 id、它们的
    kind / formula_text / lang / warmup_bars / stability，是否与 uf_* 构成同口径双 id。

纪律：只读 D:\\TSP\\data（本脚本不写任何落盘文件）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(REPO / "backend"))

UF = [
    "uf_vol60", "uf_ma120", "uf_ma200", "uf_prior_high_20",
    "uf_prior_high_55", "uf_prior_high_250", "uf_prior_low_10", "uf_prior_vol_20",
]
PACK = ["ma20", "ma60", "boll_lower", "boll_upper", "sd20", "prior_high_20",
        "prior_low_10", "prior_high_55", "prior_vol_20", "ma120", "vol60",
        "prior_high_250", "prior_amount_20", "ma200"]


def census(reg, ids):
    total = len(reg.all_factors())
    found = [i for i in ids if reg.get_factor(i) is not None]
    return total, found


def main() -> int:
    from app.factors import registry as reg

    t0 = time.time()
    total0 = len(reg.all_factors())
    missing0 = [i for i in UF if reg.get_factor(i) is None]
    print(f"Q1|before_load|all_factors={total0}|uf_found={8 - len(missing0)}/8|uf_missing={missing0}")
    print(f"Q1|before_load|pack_ids_present={[i for i in PACK if reg.get_factor(i) is not None]}")

    # --- str vs Path ---
    from app.factors import store as store_mod
    try:
        store_mod.load_into_registry(r"D:\TSP\data")  # str
        print("Q1|str_argument|accepted(未按预期抛错)")
    except Exception as exc:  # noqa: BLE001
        print(f"Q1|str_argument|EXC={type(exc).__name__}: {exc}")

    # --- Path ---
    ids = store_mod.load_into_registry(Path(r"D:\TSP\data"))
    total1 = len(reg.all_factors())
    missing1 = [i for i in UF if reg.get_factor(i) is None]
    print(f"Q1|after_load|returned={len(ids)}|ids={sorted(ids)}|all_factors={total1}"
          f"|uf_found={8 - len(missing1)}/8|uf_missing={missing1}")
    print(f"Q1|after_load|versions={ {i: reg.get_factor(i).version for i in UF} }")
    print(f"Q1|after_load|spec_kind={ {i: reg.get_factor(i).kind for i in UF} }")
    print(f"Q1|after_load|spec_lang={ {i: reg.get_factor(i).lang for i in UF} }")

    # --- Q1 幂等面：再载一次 ---
    ids2 = store_mod.load_into_registry(Path(r"D:\TSP\data"))
    print(f"Q1|second_load|returned={len(ids2)}|all_factors={len(reg.all_factors())}"
          f"|versions={ {i: reg.get_factor(i).version for i in UF} }")

    # --- Q2 provider 动态加载 ---
    from app.extensions import factors as ext
    before = len(reg.all_factors())
    ext.ensure_factor_providers()
    after = len(reg.all_factors())
    print(f"Q2|providers|all_factors {before} -> {after}|providers={sorted(ext._PROVIDERS)}")
    for fid in PACK:
        spec = reg.get_factor(fid)
        if spec is None:
            print(f"Q2|{fid}|NOT_REGISTERED")
            continue
        ft = getattr(spec, "formula_text", "<no attr>")
        print(
            f"Q2|{fid}|kind={spec.kind}|lang={spec.lang}|warmup={spec.warmup_bars}"
            f"|stability={spec.stability}|status={getattr(spec, 'status', '<no attr>')}"
            f"|formula_text={ft!r}"
        )
    # 双 id 共存
    both = [i for i in PACK if reg.get_factor(i) is not None and reg.get_factor("uf_" + i) is not None]
    print(f"Q2|dual_id_coexist={both}")
    print(f"Q2|total_after_providers={len(reg.all_factors())}")
    print(f"Q2|elapsed_s={time.time() - t0:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
