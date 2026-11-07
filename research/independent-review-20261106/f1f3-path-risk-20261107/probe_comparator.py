"""Independent adversarial checks against delivered comparator, no source mutation."""
from pathlib import Path
import sys,json,copy,hashlib
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
DEV=ROOT/'research/batch-backtest-framework-20261107'
sys.path[:0]=[str(DEV),str(ROOT/'backend')]
import verify_batch_v2 as v
import mutation_checks as m
registry=json.loads((DEV/'out_v3/registry.json').read_text(encoding='utf-8'))
days=m.load_trading_days(registry)
rt=m._binding_runtime()
gp=Path(registry['inputs']['groups_file']['path'])
groups=v.run_batch.load_groups(gp)
snapshot=v.binding_snapshot(gp,groups,rt,registry['slice']['asset_type'])
result={'baseline_binding':v.check_registry_binding(registry,snapshot,'independent'),'groups':[],'bindings':[]}
for entry in registry['runs']:
 prod=json.loads((HERE/'fresh-verify'/f"prod_{entry['group']}.json").read_text(encoding='utf-8'))
 rec={'group':entry['group'],'baseline':m.compare_core(entry,prod,registry,days)['n_result_diffs'],'full_lists':{},'mutations':[]}
 rawrun=json.loads((DEV/'out_v3/runs'/f"{entry['run_id']}.json").read_text(encoding='utf-8'))
 for field,hkey in v.CURVE_FIELDS.items():
  # independent JSON canonical hashing, without invoking author's hash function
  payload=prod['continuous_account'][field]
  digest=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()
  rec['full_lists'][field]={'count':len(payload),'sha256':digest,'registry_equal':digest==entry['continuous_account'][hkey],'runfile_hash_equal':digest==rawrun['continuous_account'][hkey]}
 # ordinary financial mutations must be detected
 for name,change in [
  ('equity_value',lambda p:p['continuous_account']['equity_curve'][0].__setitem__('value',-9876)),
  ('trade_pnl',lambda p:p['continuous_account']['trades'][0].__setitem__('pnl_amount',-9876)),
  ('fold_return',lambda p:p['folds'][0]['oos_stats'].__setitem__('total_return',-9876)),
 ]:
  p=copy.deepcopy(prod); change(p); r=m.compare_core(entry,p,registry,days)
  rec['mutations'].append({'name':name,'result_diffs':r['n_result_diffs'],'first':r['result_diffs'][:2]})
 # single-side replacement of an actual timing leaf by nested financial results
 for container in ['timing_ms','shared_prepare_timing_ms','matrix_data_cache_timing_ms','cache_timing_ms']:
  base=prod['folds'][0]['oos_stats'].get(container)
  if not isinstance(base,dict) or not base: continue
  key=next(iter(base)); p=copy.deepcopy(prod)
  old=p['folds'][0]['oos_stats'][container][key]
  p['folds'][0]['oos_stats'][container][key]={'total_return':999.0,'equity_curve':[{'value':-9876.0}],'trades':[{'pnl_amount':-9876.0}]}
  r=m.compare_core(entry,p,registry,days)
  rec['mutations'].append({'name':'timing_leaf_replaced_with_results','path':f'oos_folds[0].oos_stats.{container}.{key}','before':old,'after':p['folds'][0]['oos_stats'][container][key],'result_diffs':r['n_result_diffs'],'exempt_records':[x for x in r['exempt_diffs'] if x['field'].endswith(f'{container}.{key}')][:1]})
 # same unknown key on both sides: unequal payloads should fail a complete comparator
 e=copy.deepcopy(entry);p=copy.deepcopy(prod)
 e['oos_folds'][0]['oos_stats']['timing_ms']['result_payload']={'total_return':1.0}
 p['folds'][0]['oos_stats']['timing_ms']['result_payload']={'total_return':999.0}
 r=m.compare_core(e,p,registry,days)
 rec['mutations'].append({'name':'new_nested_financial_payload_both_sides','result_diffs':r['n_result_diffs'],'exempt_records':[x for x in r['exempt_diffs'] if 'result_payload' in x['field']]})
 result['groups'].append(rec)
# binding checks in memory; actual repository remains untouched
for name,change in [
 ('code_snapshot',lambda s:s['code'].__setitem__('sha256','bad-code')),
 ('data_generation_snapshot',lambda s:s.__setitem__('data_generation','bad-generation')),
 ('groups_snapshot',lambda s:s.__setitem__('inputs_sha256','bad-groups')),
 ('strategy_file_snapshot',lambda s:s.__setitem__('inputs_sha256','bad-strategy')),
 ('override_snapshot',lambda s:s.__setitem__('inputs_sha256','bad-override')),
]:
 s=copy.deepcopy(snapshot); change(s)
 violations=v.check_registry_binding(registry,s,'independent-negative')
 result['bindings'].append({'name':name,'violations':violations,'detected':bool(violations)})
(HERE/'probe-comparator.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps({'baseline_binding_violations':len(result['baseline_binding']),'groups':[{'group':g['group'],'baseline_diffs':g['baseline'],'full_lists':g['full_lists'],'mutations':[{'name':m['name'],'path':m.get('path'),'diffs':m['result_diffs']} for m in g['mutations']]} for g in result['groups']],'bindings_detected':sum(x['detected'] for x in result['bindings'])},ensure_ascii=False))
