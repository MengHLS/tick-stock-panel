import sys, inspect
sys.path.insert(0, 'backend')
from app.factors import registry as R, gate

R._ensure_factor_providers()
specs = R.all_factors()
print('registry size:', len(specs))
print('namespace param:', 'namespace' in inspect.signature(gate.assert_factors_usable).parameters)

def dump(name):
    s = R.get_factor(name)
    if s is None:
        return f'{name:18s} ABSENT'
    return f'{name:18s} kind={s.kind:9s} alias_of={str(s.alias_of):14s} usable={s.strategy_usable}'

ALIAS = ['vol60','uf_vol60','ma120','uf_ma120','ma200','uf_ma200',
         'prior_high_20','uf_prior_high_20','prior_low_20','uf_prior_low_20']
COLL = ['ma20','ma60','boll_lower','boll_upper']
print('\n--- §7.15.1 rows 1-8 ---')
for n in ALIAS: print(dump(n))
print('\n--- §1.3 collision names ---')
for n in COLL: print(dump(n))

print('\n--- verdicts production mode ---')
for n in ALIAS + COLL:
    try:
        res = gate.assert_factors_usable([n], 'production')
        print(f'{n:18s} blocked={res.blocked}')
    except Exception as e:
        print(f'{n:18s} EXC {type(e).__name__}: {str(e)[:80]}')
