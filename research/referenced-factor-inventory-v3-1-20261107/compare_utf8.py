import json, io, sys, collections
sys.stdout.reconfigure(encoding='utf-8')
A=json.load(open('docs/architecture/evidence/referenced_factor_inventory.json',encoding='utf-8'))
E=json.load(open('docs/factors/evidence/referenced_factor_inventory_expected_20261107.json',encoding='utf-8'))
live_paths=set(A['summary']['live_config'] and [] )
print('artifact records', len(A['records']))
print('expected records', len(E['records']), 'companion', len(E.get('companion_records',[])))
print('expected summary keys', list(E['summary'].keys()) if isinstance(E['summary'],dict) else type(E['summary']))
print('expected signature_triple', json.dumps(E.get('signature_triple'),ensure_ascii=False))
# live identification: records whose source_path in live sources
lv=A['summary']['live_config']
print('live summary', json.dumps(lv,ensure_ascii=False))
