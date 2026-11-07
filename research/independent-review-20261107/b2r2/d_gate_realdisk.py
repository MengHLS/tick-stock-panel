"""D3: 真盘 (data_dir=D:\\TSP\\data) 上 8 组双 id 的逐组判定"""
from app.factors.gate import RegistryFacts, assert_factors_usable

PAIRS = [
    ("vol60", "uf_vol60"), ("ma120", "uf_ma120"), ("ma200", "uf_ma200"),
    ("prior_high_20", "uf_prior_high_20"), ("prior_high_55", "uf_prior_high_55"),
    ("prior_high_250", "uf_prior_high_250"), ("prior_low_10", "uf_prior_low_10"),
    ("prior_vol_20", "uf_prior_vol_20"),
]
facts = RegistryFacts(r"D:\TSP\data")

print(f"{'alias':16} {'codes':20} {'status':10} {'alias_of':10} | {'canonical':20} {'codes':20} {'status'}")
for alias, canon in PAIRS:
    ra = assert_factors_usable([alias], "production", facts=facts, shadow=True)
    rc = assert_factors_usable([canon], "production", facts=facts, shadow=True)
    fa, fc = facts.facts(alias), facts.facts(canon)
    print(f"{alias:16} {str([c for (_i,_s,c) in ra.blocked]):20} {str(fa.status):10} {str(fa.alias_of):10} | "
          f"{canon:20} {str([c for (_i,_s,c) in rc.blocked]):20} {fc.status}")

print("\n=== research 模式下 ===")
for alias, canon in PAIRS[:3]:
    ra = assert_factors_usable([alias], "research", facts=facts, shadow=True)
    print(f"  {alias:16} blocked={[c for (_i,_s,c) in ra.blocked]}")
