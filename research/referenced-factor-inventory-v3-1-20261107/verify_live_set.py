import json,sys,collections
sys.stdout.reconfigure(encoding='utf-8')
A=json.load(open('docs/architecture/evidence/referenced_factor_inventory.json',encoding='utf-8'))
E=json.load(open('docs/factors/evidence/referenced_factor_inventory_expected_20261107.json',encoding='utf-8'))
# live = records of the 22 enabled live sources. Determine live source paths from summary? use path_base? 
# reconstruct: a record is live if its source is enabled and in live set. Check generator's notion: summary.live_config.sources=22
# Use records: count per source_path
cnt=collections.Counter(r['source_path'] for r in A['records'])
exp_paths=set(r['source_path'] for r in list(E['records'])+E['companion_records'])
print('distinct source_path in artifact:', len(cnt))
print('expected distinct:', len(exp_paths))
print('expected ⊄ artifact:', exp_paths-set(cnt))
print('artifact sources not in expected:', len(set(cnt)-exp_paths))
live_recs=[r for r in A['records'] if r['source_path'] in exp_paths]
print('records on expected sources:', len(live_recs), 'all have record_kind:', all(r.get('record_kind') for r in live_recs))
print('their record_kind counts:', collections.Counter(r['record_kind'] for r in live_recs))
print('live summary records:', A['summary']['live_config']['records'])
print('all enabled expected sources count:', len(exp_paths))
