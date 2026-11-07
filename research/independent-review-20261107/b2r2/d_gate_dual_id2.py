"""D2: 修正 kind 后的逐组结论 + 真实 catalog 的 kind 分布"""
from collections import Counter

from app.factors import gate
from app.factors.gate import FactorFacts, MappingFacts, assert_factors_usable, resolve_alias
from app.factors.registry import all_factors

PAIRS = [
    ("vol60", "uf_vol60"), ("ma120", "uf_ma120"), ("ma200", "uf_ma200"),
    ("prior_high_20", "uf_prior_high_20"), ("prior_high_55", "uf_prior_high_55"),
    ("prior_high_250", "uf_prior_high_250"), ("prior_low_10", "uf_prior_low_10"),
    ("prior_vol_20", "uf_prior_vol_20"),
]
SIDE = ["ma20", "ma60", "sd20", "boll_lower", "boll_upper", "prior_amount_20"]

specs = {s.id: s for s in all_factors()}
print("=== 真实 catalog 的 kind 分布 ===")
print(dict(Counter(s.kind for s in specs.values())))
print("GATED_KINDS =", gate.GATED_KINDS)
ungated = [i for i, s in specs.items() if s.kind not in gate.GATED_KINDS]
print("不在 GATED_KINDS 的因子数 =", len(ungated), " 样例:", ungated[:8])
print("in_universe kind =", specs["in_universe"].kind if "in_universe" in specs else "<无>")
print("vol60 kind =", specs["vol60"].kind, "| ma20 kind =", specs["ma20"].kind)


def build(kind_alias, kind_canon):
    m = {}
    for alias, canon in PAIRS:
        m[canon] = FactorFacts(factor_id=canon, registered=True, kind=kind_canon, status="active",
                               alias_of=None, lang="dsl", strategy_usable=True)
        m[alias] = FactorFacts(factor_id=alias, registered=True, kind=kind_alias, status="active",
                               alias_of=canon, lang="dsl", strategy_usable=False)
    for fid in SIDE:
        m[fid] = FactorFacts(factor_id=fid, registered=True, kind=kind_alias, status="active",
                             alias_of=None, lang="dsl", strategy_usable=True)
    return MappingFacts(m)


for ka, kc in [("custom", "custom"), ("frame", "custom"), ("custom", "frame")]:
    facts = build(ka, kc)
    print(f"\n=== kind(alias)={ka} / kind(canonical)={kc} ; mode=production ===")
    print(f"{'alias':16} {'codes':16} {'resolved':18} | {'canonical':20} codes")
    for alias, canon in PAIRS:
        ra = assert_factors_usable([alias], "production", facts=facts, shadow=True)
        rc = assert_factors_usable([canon], "production", facts=facts, shadow=True)
        ca = [c for (_i, _s, c) in ra.blocked]
        cc = [c for (_i, _s, c) in rc.blocked]
        try:
            res = resolve_alias(alias, facts)[0]
        except Exception as e:
            res = f"<{type(e).__name__}>"
        print(f"{alias:16} {str(ca):16} {res:18} | {canon:20} {str(cc)}")

print("\n=== 模式敏感性 (kind=custom) ===")
facts = build("custom", "custom")
for mode in ("production", "research", "diagnostic", "none"):
    r = assert_factors_usable(["vol60"], mode, facts=facts, shadow=True)
    print(f"  {mode:12} blocked={[c for (_i,_s,c) in r.blocked]}")

print("\n=== FS04: alias + canonical 同集合 (kind=custom) ===")
for mode in ("production", "research", "diagnostic"):
    try:
        r = assert_factors_usable(["vol60", "uf_vol60"], mode, facts=facts, shadow=True)
        print(f"  {mode:12} blocked={[c for (_i,_s,c) in r.blocked]}")
    except Exception as e:
        print(f"  {mode:12} raised {type(e).__name__}: {str(e)[:90]}")

print("\n=== 真盘 (无 alias_of 元数据) 上对 8 个 alias 的实际判定 ===")
for alias, canon in PAIRS:
    r = assert_factors_usable([alias], "production", shadow=True)
    print(f"  {alias:16} blocked={[c for (_i,_s,c) in r.blocked]}")
