"""Independent event-ledger reconstruction + as-of quotes; reads original frozen artifacts."""
from pathlib import Path
from collections import defaultdict
import json,hashlib,bisect,sys
import polars as pl
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
RES=ROOT/'research/strategy-search-20261107/results'
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
report=json.loads((RES/'path_risk/path_risk.json').read_text(encoding='utf-8'))
panel_path=ROOT/report['panel']['path']
quotes=pl.read_ipc(panel_path).select('symbol',pl.col('date').cast(pl.String).alias('quote_date'),'raw_close','volume').sort('symbol','quote_date')
calendar=sorted(quotes['quote_date'].unique().to_list()); calidx={d:i for i,d in enumerate(calendar)}
all_records=[]; exit_records=[]; paths=[]; bypath={}
for ref in report['paths']:
 run=json.loads((ROOT/ref['input_file']).read_text(encoding='utf-8')); bypath[ref['path_id']]=run
 eq=run['equity']; dates=[r['date'] for r in eq]; events=defaultdict(list)
 for t in run['trades']:
  events[bisect.bisect_left(dates,t['entry_date'])].append((t['symbol'],float(t['shares'])))
  if t['exit_date'] is not None:
   events[bisect.bisect_left(dates,t['exit_date'])].append((t['symbol'],-float(t['shares'])))
   exit_records.append({'path':ref['path_id'],'date':t['exit_date'],'symbol':t['symbol'],'entry_date':t['entry_date'],'shares':float(t['shares']),'exit_price':float(t['exit_price'])})
 opens=(run.get('carry') or {}).get('positions') or run.get('final_positions') or []
 if ref['kind']=='S': opens=[]
 for t in opens:
  events[bisect.bisect_left(dates,t['entry_date'])].append((t['symbol'],float(t['shares'])))
 held={}; unknown=0; proportional=0; conservative=0; unknown_dates=[]
 for i,row in enumerate(eq):
  for sym,delta in events[i]:
   held[sym]=held.get(sym,0)+delta
   if abs(held[sym])<0.00001: held.pop(sym)
  gap=max(0,row['positions']-len(held)); unknown+=gap
  if gap:
   proportional+=row['exposure']*gap/row['positions']
   conservative+=row['exposure']; unknown_dates.append(row['date'])
  for sym,shares in held.items():
   all_records.append({'path':ref['path_id'],'date':row['date'],'symbol':sym,'shares':shares,'equity':row['value'],'cash':row['cash'],'reported_positions':row['positions'],'identified_positions':len(held)})
 paths.append({'path':ref['path_id'],'unidentified':unknown,'proportional_exposure_weight_days':proportional,'total_exposure_on_unidentified_days':conservative,'input_hash_ok':digest(ROOT/ref['input_file'])==ref['input_sha256']})
positions=pl.DataFrame(all_records).sort('symbol','date').join_asof(quotes,left_on='date',right_on='quote_date',by='symbol',strategy='backward',check_sortedness=False)
positions=positions.with_columns((pl.col('shares')*pl.col('raw_close')).alias('market_value'),(pl.col('date').replace_strict(calidx)-pl.col('quote_date').replace_strict(calidx)).alias('age')).with_columns((pl.col('market_value')/pl.col('equity')).alias('weight'))
stale=positions.filter(pl.col('age')>0)
reconciled=positions.filter(pl.col('reported_positions')==pl.col('identified_positions')).group_by('path','date').agg(pl.col('market_value').sum().alias('mv'),pl.col('cash').first(),pl.col('equity').first()).with_columns((pl.col('cash')+pl.col('mv')-pl.col('equity')).alias('err'))
# Examine seller exposure excluded by end-of-day convention; derive preceding available EOD stale record.
lookup={(r['path'],r['symbol'],r['date']):r for r in stale.iter_rows(named=True)}
exits=pl.DataFrame(exit_records).sort('symbol','date').join_asof(quotes,left_on='date',right_on='quote_date',by='symbol',strategy='backward',check_sortedness=False)
sell_examples=[]
for t in exits.iter_rows(named=True):
 idx=calidx.get(t['date'],0)
 prev=calendar[idx-1] if idx else None
 r=lookup.get((t['path'],t['symbol'],prev))
 if r and t['quote_date']==t['date']:
  gap=t['raw_close']/r['raw_close']-1
  realized=t['exit_price']/r['raw_close']-1
  sell_examples.append({'path':t['path'],'symbol':t['symbol'],'previous_date':prev,'sell_date':t['date'],'last_quote':r['quote_date'],'last_mark':r['raw_close'],'sell_price':t['exit_price'],'new_bar_raw_close':t['raw_close'],'hypothetical_close_return':gap,'realized_fill_return_vs_last_mark':realized,'hypothetical_equity_impact':r['weight']*gap,'realized_equity_impact_before_fees':r['weight']*realized,'exit_day_in_position_days':False})
summary={'panel_sha256':digest(panel_path),'panel_sha_matches':digest(panel_path)==report['panel']['sha256'],'all_run_hashes_match':all(p['input_hash_ok'] for p in paths),'paths':paths,'identified_position_days':positions.height,'stale_position_days':stale.height,'stale_weight_days':stale['weight'].sum(),'max_quote_age':stale['age'].max(),'unidentified_position_days':sum(p['unidentified'] for p in paths),'unidentified_proportional_weight_days':sum(p['proportional_exposure_weight_days'] for p in paths),'total_exposure_on_unidentified_days':sum(p['total_exposure_on_unidentified_days'] for p in paths),'valuation':{'days_checked':reconciled.height,'days_over_1_cny':reconciled.filter(pl.col('err').abs()>1).height,'max_abs_err':reconciled['err'].abs().max(),'max_abs_err_fraction_of_same_day_equity':reconciled.select((pl.col('err').abs()/pl.col('equity')).max()).item(),'largest_errors':reconciled.sort(pl.col('err').abs(),descending=True).head(5).to_dicts()},'sell_on_first_bar_after_stale_endofday':len(sell_examples),'sell_examples':sorted(sell_examples,key=lambda x:abs(x['hypothetical_equity_impact']),reverse=True)[:10],'exit_days_without_bar':exits.filter(pl.col('date')!=pl.col('quote_date')).height}
# all sums above are measured on identified EOD positions only; no lifecycle inference.
(HERE/'probe-path-risk.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k not in ['paths','sell_examples']},ensure_ascii=False,default=str))
print(json.dumps({'sell_examples':summary['sell_examples'][:3]},ensure_ascii=False))
