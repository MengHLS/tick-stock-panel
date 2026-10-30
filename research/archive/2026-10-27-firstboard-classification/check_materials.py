"""独立材料自检；不导入或认证生产分类引擎。"""
import json
from decimal import Decimal as D
from pathlib import Path
p=Path(__file__).parent
fs=json.loads((p/'boundary-fixtures.json').read_text(encoding='utf-8'))
for f in fs:
    for r in f['rows']:
        o,h,l,c=[D(r[k]) for k in ['open','high','low','close']]
        assert l<=min(o,c)<=max(o,c)<=h, (f['id'],r)
f={x['id']:x for x in fs}
for key in ['B10','B11','B12']:
    x=f[key]; price=D(x['context']['P_frozen']); c=D(x['rows'][-1]['close'])
    assert (c>price)==x['expected']['close_above_P']
assert D(f['B10']['rows'][2]['close'])>D('100')
assert D(f['B10']['rows'][-1]['close'])==D('100')
assert D(f['B12']['rows'][-1]['high'])>D('100')
assert (D('100')-D('100'))/D('100')==0
assert f['B11']['expected']['recovery_ratio'] is None
b9=f['B9'];assert D(b9['rows'][1]['close'])<D(b9['rows'][0]['close'])
assert max(D(r['high']) for r in b9['rows'][:-1])==D('110')
assert D('100')<D(b9['rows'][-1]['close'])<D('110')
assert (D('98')-D('96'))/D('98')<D('0.05')
assert (D('100')-D('90'))/D('100')>=D('0.05')
cases=json.loads((p/'cases.json').read_text(encoding='utf-8'))
assert len(cases)==12
assert sum(x['evidence_role']=='旧标签顺序冲突反例' for x in cases)==2
for x in cases:
    assert x['P_window']['value'] is None
    assert x['path_state_T_minus_1']['value'] is None
print('PASS: 5 fixture OHLC checks, determined comparison assertions, candidate numerical differences, and case evidence completeness checks. Production classification not tested.')
