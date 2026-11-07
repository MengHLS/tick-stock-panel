import sys,json,hashlib,copy,collections
from pathlib import Path
P=Path(r'C:\work\sourcecode\tick-stock-panel');D=P/'research/independent-review-20261106/matrix-e2e-20261107'
sys.path[:0]=[str(P/'backend'),str(P/'research/batch-backtest-framework-20261107')]
import verify_batch as v
r=json.loads((D/'out/registry.json').read_text(encoding='utf-8'))
meta=json.loads((D/'verify-exit.json').read_text(encoding='utf-8'))
findings=[]
for e in r['runs']:
 p=json.loads((D/('production-'+e['strategy_id']+'.json')).read_text(encoding='utf-8'));c=p['continuous_account'];b=e['continuous_account']
 checks={'exact_curves':e['raw']['curves']==c['equity_curve'],'exact_trades':e['raw']['trades']==c['trades'],'exact_account_stats':b['stats']==c['stats'],'exact_boundaries':b['boundaries']==c['boundaries'],'exact_final_cash':b['final_cash']==c['final_cash'],'exact_final_positions':b['final_positions']==c['final_positions'],'unique_dates':len({x['date'] for x in c['equity_curve']})==len(c['equity_curve']),'timeline_complete':c['timeline']['complete'] and c['timeline']['n_missing_dates']==0,'duplicate_dates_zero':c['duplicate_dates']==0,'curve_length_189':len(c['equity_curve'])==189,'all_invariants':all(c['invariants'].values()),'closed_plus_unrealized_pnl_matches_equity':abs(1000000+sum((t['exit_value']-t['entry_value']) if t['open_at_end'] else t['pnl_amount'] for t in c['trades'])-c['final_equity'])<0.1,'all_folds_matrix_native':all(f['oos_stats']['execution_backend']=='matrix_native' for f in p['folds'])}
 for k,seq in [('equity_curve_sha256',c['equity_curve']),('trades_sha256',c['trades'])]: checks[k]=hashlib.sha256(json.dumps(seq,sort_keys=True,ensure_ascii=False).encode()).hexdigest()==b[k]
 direct=[]
 for bf,pf in zip(e['oos_folds'],p['folds'],strict=True):
  for k in ['total_return','account_total_return_cumulative']:
   if bf['oos_stats'].get(k)!=pf['oos_stats'].get(k):direct.append([bf['index'],k,bf['oos_stats'].get(k),pf['oos_stats'].get(k)])
 checks['skipped_return_fields_equal']=not direct
 before=v.compare_entry(e,p,{})['n_result_diffs'];mut=copy.deepcopy(p);mut['continuous_account']['trades'][0]['pnl_amount']+=999;mut['continuous_account']['equity_curve'][0]['value']+=999;mut['continuous_account']['stats']['total_return']=999;mut['folds'][0]['oos_stats']['total_return']=999
 after=v.compare_entry(e,mut,{})['n_result_diffs']
 findings.append({'group':e['group'],'checks':checks,'curve_points':len(c['equity_curve']),'trades':len(c['trades']),'final_equity':c['final_equity'],'equity_minus_pnl_sum':1000000+sum((t['exit_value']-t['entry_value']) if t['open_at_end'] else t['pnl_amount'] for t in c['trades'])-c['final_equity'],'blindspot_mutation':{'changed':'trade pnl+999; equity first point+999; account total_return=999; fold total_return=999','before_result_diffs':before,'after_result_diffs':after}})
hashes={}
for f,h in r['code']['files'].items():
 path=P/f if f!='run_batch.py' else P/'research/batch-backtest-framework-20261107/run_batch.py'
 actual=hashlib.sha256(path.read_bytes()).hexdigest();hashes[f]={'expected':h,'actual':actual,'match':actual==h}
source=json.loads((P/'research/batch-backtest-framework-20261107/out/registry.json').read_text(encoding='utf-8'))
evidence=[]
for f in (D/'out/evidence').glob('*.json'):
 x=json.loads(f.read_text(encoding='utf-8'));evidence.append({'file':str(f.relative_to(D)),'data_generation':x.get('data_generation'),'code':x.get('code'),'run_id':x.get('run_id')})
res={'groups':findings,'hashes':hashes,'batch_code_matches_original':r['code']==source['code'],'code_before_after_equal':meta['before']==meta['after'],'generation_before':meta['generation_before'],'generation_after':meta['generation_after'],'registry_generation':r['data_generation'],'evidence':evidence,'telemetry_original':{e['group']:collections.Counter(x['field'].split('.oos_stats.')[1].split('.')[0] for x in json.loads((P/'research/batch-backtest-framework-20261107/out'/('compare_'+e['group']+'.json')).read_text(encoding='utf-8'))['telemetry_diffs']) for e in r['runs']}}
code=0 if all(all(g['checks'].values()) for g in findings) and all(x['match'] for x in hashes.values()) and res['code_before_after_equal'] and meta['generation_before']==meta['generation_after'] else 1
res['exit_code']=code
(D/'independent-checks.json').write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'exit_code':code,'groups':findings,'all_file_hashes_match':all(x['match'] for x in hashes.values()),'generation':r['data_generation']},ensure_ascii=False))
raise SystemExit(code)
