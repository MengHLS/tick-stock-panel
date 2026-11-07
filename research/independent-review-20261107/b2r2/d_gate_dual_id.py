"""D: gate.py 对 §7.15.1 的 8 组双 id 是否真覆盖 —— 逐组结论"""
from app.factors import gate
from app.factors.gate import FactorFacts, MappingFacts, assert_factors_usable, resolve_alias

PAIRS = [
    ("vol60", "uf_vol60"),
    ("ma120", "uf_ma120"),
    ("ma200", "uf_ma200"),
    ("prior_high_20", "uf_prior_high_20"),
    ("prior_high_55", "uf_prior_high_55"),
    ("prior_high_250", "uf_prior_high_250"),
    ("prior_low_10", "uf_prior_low_10"),
    ("prior_vol_20", "uf_prior_vol_20"),
]
SIDE = ["ma20", "ma60", "sd20", "boll_lower", "boll_upper", "prior_amount_20"]


def build():
    m = {}
    for alias, canon in PAIRS:
        m[canon] = FactorFacts(factor_id=canon, registered=True, kind="pack", status="active",
                               alias_of=None, lang="dsl", strategy_usable=True)
        m[alias] = FactorFacts(factor_id=alias, registered=True, kind="frame", status="active",
                               alias_of=canon, lang="dsl", strategy_usable=False)
    for fid in SIDE:
        m[fid] = FactorFacts(factor_id=fid, registered=True, kind="pack", status="active",
                             alias_of=None, lang="dsl", strategy_usable=True)
    return MappingFacts(m)


facts = build()

print("=== 机制层：按 §7.15.1 元数据齐全时的逐组结论 (mode=production) ===")
print(f"{'alias':16} {'期望':6} {'实得codes':22} {'resolved':18} | {'canonical':20} {'实得codes'}")
ok_all = True
for alias, canon in PAIRS:
    ra = assert_factors_usable([alias], "production", facts=facts, shadow=True)
    rc = assert_factors_usable([canon], "production", facts=facts, shadow=True)
    ca = [c for (_i, _s, c) in ra.blocked]
    cc = [c for (_i, _s, c) in rc.blocked]
    res = resolve_alias(alias, facts)[0]
    good = ca == ["FS03"] and cc == []
    ok_all &= good
    print(f"{alias:16} {'FS03':6} {str(ca):22} {res:18} | {canon:20} {str(cc)}  {'OK' if good else '*** MISMATCH'}")

print("\n=== 单侧件 (第 9–14 行) 不得触发 FS03 ===")
for fid in SIDE:
    r = assert_factors_usable([fid], "production", facts=facts, shadow=True)
    print(f"  {fid:20} blocked={[c for (_i,_s,c) in r.blocked]}")

print("\n=== 模式敏感性: 同一 alias 在 research / diagnostic 下 ===")
for mode in ("production", "research", "diagnostic"):
    r = assert_factors_usable(["vol60"], mode, facts=facts, shadow=True)
    print(f"  {mode:12} blocked={[c for (_i,_s,c) in r.blocked]}")

print("\n=== FS04: alias 与其 canonical 同时出现 ===")
for mode in ("production", "research", "diagnostic"):
    try:
        r = assert_factors_usable(["vol60", "uf_vol60"], mode, facts=facts, shadow=True)
        print(f"  {mode:12} blocked={[c for (_i,_s,c) in r.blocked]}")
    except Exception as e:
        print(f"  {mode:12} raised {type(e).__name__}: {e}")

print("\n=== 真盘: 现注册表里这 16 个 id 的实际元数据 ===")
from app.factors.registry import all_factors
specs = {s.id: s for s in all_factors()}
for alias, canon in PAIRS:
    for fid in (alias, canon):
        s = specs.get(fid)
        if s is None:
            print(f"  {fid:20} <未注册>")
        else:
            print(f"  {fid:20} kind={s.kind:8} alias_of={getattr(s,'alias_of','<无属性>'):20} "
                  f"strategy_usable={getattr(s,'strategy_usable','<无属性>')}")
