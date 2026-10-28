import csv,json,hashlib,statistics,math
from pathlib import Path
p=Path(__file__).parent;o=p/'event-replay-v01';source=p/'four-case-paths.csv'
rows=list(csv.DictReader(source.open(encoding='utf-8')));events=json.loads((o/'historical-events.json').read_text(encoding='utf-8'));snap=[]
for e in events:
 rs=[r for r in rows if r['symbol']==e['code'] and r['date']<=e['date']]
 for role,window in [('background_D_minus_1',rs[:-1]),('event_D_close',rs)]:
  last=window[-1];C=float(last['close']);asof=last['date'];cols=[]
  def add(name,value,formula,n,reason='OK'):
   cols.append({'event_id':e['event_id'],'snapshot_role':role,'asof':asof+' close','factor':name,'value':value,'unit':'ratio_decimal' if name!='amount' else 'currency_as_stored','formula':formula,'window':n,'available_bars':min(len(window),n) if n else len(window),'reason_code':reason,'source':'four-case-paths.csv','classification_usage':'background' if role.startswith('background') else 'event_description_and_optional_incremental_feature'})
  for n in [240,250]:
   w=window[-n:];hi=max(float(r['high']) for r in w);lo=min(float(r['low']) for r in w);reason='WARMUP_INSUFFICIENT' if len(w)<n else 'ZERO_DENOMINATOR' if hi==lo else 'OK'
   add('position_highlow_'+str(n)+'d',(C-lo)/(hi-lo) if reason=='OK' else None,'(close_asof-min(low,n))/(max(high,n)-min(low,n)); includes asof bar',n,reason)
  for n in [20,60,120]:
   reason='OK' if len(window)>n else 'WARMUP_INSUFFICIENT';add('momentum_close_'+str(n)+'d',C/float(window[-n-1]['close'])-1 if reason=='OK' else None,'close_asof/close_n_observed_sessions_ago-1',n+1,reason)
  for n in [20,60]:
   w=window[-n:];mean=statistics.mean(float(r['close']) for r in w);reason='WARMUP_INSUFFICIENT' if len(w)<n else 'ZERO_DENOMINATOR' if mean==0 else 'OK';add('ma_bias_'+str(n)+'d',C/mean-1 if reason=='OK' else None,'close_asof/mean(close,n)-1; includes asof',n,reason)
  returns=[float(window[i]['close'])/float(window[i-1]['close'])-1 for i in range(max(1,len(window)-20),len(window))];add('daily_return_std_20d',statistics.stdev(returns) if len(returns)==20 else None,'sample std(ddof=1) of 20 daily close returns; not annualized',21,'OK' if len(returns)==20 else 'WARMUP_INSUFFICIENT')
  prev=window[-6:-1];mean=statistics.mean(float(r['volume']) for r in prev) if prev else 0;reason='WARMUP_INSUFFICIENT' if len(prev)<5 else 'ZERO_DENOMINATOR' if mean==0 else 'OK';add('volume_ratio_prior5_excluding_asof',float(last['volume'])/mean if reason=='OK' else None,'volume_asof/mean(volume of previous 5 bars); denominator EXCLUDES asof',6,reason)
  add('amount',float(last['amount']) if last['amount'] else None,'stored daily amount',1,'OK' if last['amount'] else 'SOURCE_MISSING')
  for name,why in [('turnover_rate','SHARE_CAPITAL_CURRENT_ONLY'),('industry_environment','PIT_INDUSTRY_UNAVAILABLE'),('financial_factors','FINANCIAL_SOURCE_EMPTY'),('market_environment','ALIGNED_MARKET_SNAPSHOT_NOT_INCLUDED')]:add(name,None,'excluded or unavailable; no current snapshot backfill',0,why)
  snap.extend(cols)
file=o/'factor-snapshots-long.csv'
with file.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(snap[0]));w.writeheader();w.writerows(snap)
assert len(events)==27 and len(snap)==27*2*14
assert all(r['asof'][:10] < r['event_id'].split('@')[1] if r['snapshot_role']=='background_D_minus_1' else r['asof'][:10]==r['event_id'].split('@')[1] for r in snap)
(o/'factor-snapshot-manifest.json').write_text(json.dumps({'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'events':27,'snapshot_times':54,'factor_records':len(snap),'version':'factor-sidecar-v01-20261028','scope':'27 chart-window events; longer data only supplies warmup; no 63-event expansion','compatibility':'240 and 250 research formulas explicit; not claimed to be registry position_240d implementation until independent comparison','priority':'this sidecar is authoritative for warmed-up factor comparisons; original event JSON retains earlier short-input snapshot for audit'},ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS:',len(snap),'factor records / 54 snapshots; explicit 240/250 windows and null reason codes')
