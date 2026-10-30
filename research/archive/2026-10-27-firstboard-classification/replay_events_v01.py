import csv,json,hashlib,math,statistics,itertools,html
from pathlib import Path
import duckdb
p=Path(__file__).parent;out=p/'event-replay-v01';out.mkdir(exist_ok=True)
VERSION='replay-v01-discussion-20261028'
def load(f):return list(csv.DictReader(f.open(encoding='utf-8')))
def dump(f,x):f.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def writecsv(f,rs):
 if not rs:return
 with f.open('w',newline='',encoding='utf-8') as h:
  w=csv.DictWriter(h,fieldnames=list(rs[0]));w.writeheader()
  for r in rs:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()})
base=load(p/'shape-selection-paths.csv');flags=load(p/'platform-firstboard-flags.csv');lists=json.loads((p/'platform-firstboard-date-lists.json').read_text(encoding='utf-8'))
codes=sorted({x['code'] for x in lists});events=sorted({(x['code'],d) for x in lists if x['window']=='长图' for d in x['dates']})
# Read raw prices separately; fixed adjusted input remains authoritative for structure.
c=duckdb.connect();q="SELECT symbol,date,open,high,low,close,amount FROM read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet',hive_partitioning=true) WHERE date BETWEEN DATE '2025-01-01' AND DATE '2026-10-23' AND symbol IN ('000810.SZ','002687.SZ','600785.SH','002354.SZ') ORDER BY symbol,date"
cur=c.execute(q);cols=[x[0] for x in cur.description];rawrows=[dict(zip(cols,r)) for r in cur.fetchall()]
for r in rawrows:r['date']=str(r['date'])
writecsv(out/'raw-price-snapshot.csv',rawrows);raw={(r['symbol'],r['date']):r for r in rawrows}
by={code:[] for code in codes};boards={code:{r['date'] for r in flags if r['symbol']==code and r['consecutive_limit_ups']=='1'} for code in codes}
for r in base:
 if r['symbol'] in by:
  z=dict(r)
  for k in ['open','high','low','close','volume','raw_close']:z[k]=float(z[k])
  assert abs(raw[(z['symbol'],z['date'])]['close']-z['raw_close'])<1e-8
  by[z['symbol']].append(z)
def factors(rs):
 t=rs[-1];b=t['close'];f={'asof':t['date'],'price_basis':'fixed adjusted snapshot; ratios scale invariant','amount':raw[(t['symbol'],t['date'])]['amount'],'volume':t['volume'],'turnover_rate':None,'turnover_reason':'PIT_SHARE_CAPITAL_UNCERTIFIED','industry_environment':None,'industry_reason':'PIT_INDUSTRY_UNCERTIFIED','market_environment':None,'market_reason':'ALIGNED_MARKET_SNAPSHOT_NOT_IN_THIS_EXPORT'}
 for n in [5,20,60,120,250]:
  f['return_'+str(n)]=b/rs[-n-1]['close']-1 if len(rs)>n else None
  w=rs[-n:];f['coverage_'+str(n)]=len(w)
  f['position_'+str(n)]=(b-min(x['low'] for x in w))/(max(x['high'] for x in w)-min(x['low'] for x in w)) if len(w)==n and max(x['high'] for x in w)>min(x['low'] for x in w) else None
  f['ma_bias_'+str(n)]=b/statistics.mean(x['close'] for x in w)-1 if len(w)==n else None
  rets=[rs[i]['close']/rs[i-1]['close']-1 for i in range(max(1,len(rs)-n),len(rs))]
  f['daily_return_std_'+str(n)]=statistics.stdev(rets) if len(rets)==n else None
 prior=rs[-6:-1];f['volume_ratio_vs_prior5']=t['volume']/statistics.mean(x['volume'] for x in prior) if len(prior)==5 and sum(x['volume'] for x in prior)>0 else None
 f['volume_ratio_definition']='current volume / mean previous 5 observed sessions; research-derived, not platform real-time volume ratio'
 return f
def trajectory(prefix,anchor,include,q,gate):
 pre=prefix[:-1];D=prefix[-1];ar=[r for r in pre if r['date']>=anchor];v={'anchor':anchor,'P':None,'P_date':None,'P_known_at':None,'L_setup':None,'L_setup_date':None,'first_break':None,'path_state':'no_first_decline','break_event':None,'skip':True}
 d=next((i for i in range(1,len(ar)) if ar[i]['close']<ar[i-1]['close']),None)
 if d is None:return v
 peak=max(ar[:d+int(include)],key=lambda x:x['high']);P=peak['high'];known=ar[d]['date'];v.update(P=P,P_date=peak['date'],P_known_at=known,new_high_after_anchor=P>ar[0]['high'])
 if gate and not v['new_high_after_anchor']:v['path_state']='no_post_anchor_high';return v
 br=next((r for r in prefix if r['date']>=known and r['close']>P),None)
 setup=[r for r in pre if r['date']>peak['date'] and (br is None or r['date']<br['date'])]
 if not setup:v['path_state']='no_setup';return v
 low=min(setup,key=lambda x:x['low']);depth=(P-low['low'])/P;prior=bool(br and br['date']<D['date']);st='prior_close_break' if prior else 'shallow_pullback' if depth<q else 'left_low_below_P' if pre[-1]['close']>low['low'] else 'at_or_below_setup_low'
 v.update(L_setup=low['low'],L_setup_date=low['date'],depth=depth,first_break=br['date'] if br else None,path_state=st,break_event={'first_break_on_D':bool(br and br['date']==D['date']),'prior_break':prior,'relation':'above' if D['close']>P else 'below' if D['close']<P else 'equal'},skip=not prior and depth<q,recovery_raw=(pre[-1]['close']-low['low'])/(P-low['low']) if P>low['low'] else None,recovery_applicable=not prior and pre[-1]['close']>=low['low'])
 return v
def classify(prefix,code,include,q,gate,recursive):
 prior=[r['date'] for r in prefix[-251:-1] if r['date'] in boards[code]];trace=[]
 for a in reversed(prior):
  v=trajectory(prefix,a,include,q,gate);trace.append(v)
  if not recursive or not v['skip']:break
 return {'nearest_anchor':prior[-1] if prior else None,'selected':trace[-1] if trace else None,'trace':trace,'examined':len(trace),'stop':'nearest_only' if not recursive else 'first_non_skippable_or_history_exhausted','reason':'CANDIDATE_RULE_UNFINALIZED' if prior else 'NO_PRIOR_BOARD_IN_AVAILABLE_250_WINDOW'}
records=[];candidates=[];outcomes=[];tracking=[];pages=[];checks=0
for code,D in events:
 rs=by[code];idx=next(i for i,r in enumerate(rs) if r['date']==D);prefix=rs[:idx+1];pre=prefix[:-1];t=prefix[-1];rp=raw[(code,D)];prev=raw[(code,pre[-1]['date'])];eid=code+'@'+D
 # Original exchange preclose not supplied: previous observed raw close is explicitly distinct.
 rec={'event_id':eid,'code':code,'date':D,'version':VERSION,'raw_open':rp['open'],'raw_high':rp['high'],'raw_low':rp['low'],'raw_close':rp['close'],'previous_observed_raw_close':prev['close'],'exchange_preclose':None,'preclose_reason':'EXCHANGE_PRECLOSE_NOT_IN_SOURCE','raw_change_vs_previous_observed_close':rp['close']/prev['close']-1,'board_identity_certification':'HISTORICAL_REGIME_UNCERTIFIED','shape_certification':'CANDIDATE_REPLAY_PENDING_INDEPENDENT_REVIEW','factors_D_minus_1':factors(pre),'factors_D_close':factors(prefix),'coverage_reason':'AVAILABLE_SYMBOL_BARS_NOT_OFFICIAL_CALENDAR','structural_price_basis':'fixed adjusted snapshot; P/L also rebased to D raw close scale; point-in-time factor integrity pending data audit'}
 records.append(rec);chosen=None
 for include,q,gate,recurse in itertools.product([False,True],[.03,.05],[False,True],[False,True]):
  rule=f'P{"B" if include else "A"}_q{q}_G{int(gate)}_R{int(recurse)}';cl=classify(prefix,code,include,q,gate,recurse)
  # Prefix-alone versus progressive batch result; not independent certification.
  batch=[r for r in rs if r['date']<=D];assert cl==classify(batch,code,include,q,gate,recurse);checks+=1
  scale=t['raw_close']/t['close'];sel=cl['selected'];export={'event_id':eid,'rule_version':VERSION,'rule':rule,'classification_asof':D+' close','background_asof':pre[-1]['date']+' close','classification':cl,'P_on_D_raw_scale':sel['P']*scale if sel and sel['P'] is not None else None,'L_on_D_raw_scale':sel['L_setup']*scale if sel and sel['L_setup'] is not None else None,'D_distance_to_P':t['close']/sel['P']-1 if sel and sel['P'] else None,'D_distance_to_L':t['close']/sel['L_setup']-1 if sel and sel['L_setup'] else None};candidates.append(export)
  if include and q==.05 and not gate and not recurse:chosen=export
 for n in [1,3,5,10,20]:
  future=rs[idx+1:idx+n+1];complete=len(future)==n
  outcomes.append({'event_id':eid,'horizon_observed_sessions':n,'available_sessions':len(future),'complete':complete,'horizon_end':future[-1]['date'] if complete else None,'close_return':future[-1]['close']/t['close']-1 if complete else None,'max_high_return':max(r['high'] for r in future)/t['close']-1 if complete else None,'min_low_return':min(r['low'] for r in future)/t['close']-1 if complete else None,'reason':'DESCRIPTIVE_PRICE_PATH_NOT_EXECUTABLE_RETURN' if complete else 'RIGHT_CENSORED_AT_2026_10_23','price_basis':'adjusted path / adjusted D close; no costs or fill simulation'})
 sel=chosen['classification']['selected'];frozenP=sel['P'] if sel else None
 for step,r in enumerate(rs[idx+1:idx+21],1):
  seen=rs[idx+1:idx+step+1];broke=bool(frozenP and (t['close']>frozenP or any(x['close']>frozenP for x in seen)))
  relation=None if not frozenP else 'above' if r['close']>frozenP else 'below' if r['close']<frozenP else 'equal'
  tracking.append({'event_id':eid,'asof':r['date']+' close','step_observed_sessions':step,'judgment_version':VERSION,'reference_rule':chosen['rule'],'frozen_D_P':frozenP,'current_relation_to_frozen_P':relation,'tracking_label':'reference_unavailable' if not frozenP else 'broke_then_fell_below' if broke and relation=='below' else 'above_frozen_P' if relation=='above' else 'below_or_equal_frozen_P','return_since_D':r['close']/t['close']-1,'D_record_overwritten':False,'factors_asof_tracking_day':factors(rs[:idx+step+1])})
 # Chart contains only <=D candles; no outcome fields embedded.
 chart=prefix[-121:];lo=min(r['low'] for r in chart);hi=max(r['high'] for r in chart);pad=(hi-lo)*.08;lo-=pad;hi+=pad
 def y(v):return 215-(v-lo)/(hi-lo)*185
 svg=['<svg viewBox="0 0 900 255">']
 for i,r in enumerate(chart):
  xx=35+820*(i+.5)/len(chart);co='#dc2626' if r['close']>=r['open'] else '#059669';svg.append(f'<g><title>{r["date"]} adj O{r["open"]:.3f} H{r["high"]:.3f} L{r["low"]:.3f} C{r["close"]:.3f}</title><line x1="{xx}" x2="{xx}" y1="{y(r["high"])}" y2="{y(r["low"])}" stroke="{co}"/><rect x="{xx-2}" y="{min(y(r["open"]),y(r["close"]))}" width="4" height="{max(1,abs(y(r["open"])-y(r["close"])))}" fill="{co}"/></g>')
  if r['date'] in boards[code]:svg.append(f'<circle cx="{xx}" cy="{min(225,y(r["low"])+8)}" r="3" fill="#2563eb"><title>平台首板 {r["date"]}</title></circle>')
 if sel:
  for lab,val in [('P',sel['P']),('L_setup',sel['L_setup'])]:
   if val and lo<=val<=hi:svg.append(f'<line x1="35" x2="855" y1="{y(val)}" y2="{y(val)}" stroke="#7c3aed" stroke-dasharray="4 4"/><text x="855" y="{y(val)}">{lab} {val:.2f}</text>')
 svg.append(f'<text x="35" y="246">{chart[0]["date"]} → {D}（只画当时可见行情）</text></svg>')
 pages.append(f'<article><h2>{eid}</h2><p>原始开/高/低/收：{rp["open"]:.2f} / {rp["high"]:.2f} / {rp["low"]:.2f} / {rp["close"]:.2f}；上一可观测交易收盘 {prev["close"]:.2f}（非交易所除权昨收）。</p>'+''.join(svg)+'<details><summary>D−1背景因子、D收盘因子与展示候选标签</summary><pre>'+html.escape(json.dumps({'factors_D_minus_1':rec['factors_D_minus_1'],'factors_D_close':rec['factors_D_close'],'candidate':chosen},ensure_ascii=False,indent=2))+'</pre></details></article>')
writecsv(out/'historical-events.csv',records);dump(out/'historical-events.json',records);dump(out/'candidate-classifications.json',candidates);writecsv(out/'forward-outcomes.csv',outcomes);dump(out/'forward-tracking.json',tracking)
(out/'event-price-charts.html').write_text('<!doctype html><meta charset="utf-8"><title>历史首板逐事件回放</title><style>body{font:15px system-ui;max-width:1150px;margin:24px auto;background:#f8fafc}article{background:white;border:1px solid #ddd;padding:16px;margin:16px 0}svg{width:100%}text{font:12px system-ui}pre{white-space:pre-wrap;font-size:12px}</style><h1>四股全部窗口首板：逐事件截断与价格</h1><p>27个平台候选首板，含原目标日4例；不按后续收益挑样本。每张图只到自身D日，展示121根已有行情以内；蓝点为当时已发生平台首板。图上结构采用B/5%/不强制新峰值/仅最近候选，全部16种候选另表保存；未定稿、非交易回测。图价为固定复权基准，交易原始价格单列。首板身份、官方日历、历史因子时点未完全认证；状态允许不明确。后续表现及跟踪另表，不倒灌本页。</p>'+''.join(pages),encoding='utf-8')
assert len(records)==27 and len(candidates)==432 and len(outcomes)==135
files=['historical-events.csv','historical-events.json','candidate-classifications.json','forward-outcomes.csv','forward-tracking.json','event-price-charts.html','raw-price-snapshot.csv']
dump(out/'manifest.json',{'version':VERSION,'event_count':len(records),'candidate_rows':len(candidates),'outcome_rows':len(outcomes),'tracking_rows':len(tracking),'cutoff':'2026-10-23','input_hashes':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [p/'shape-selection-paths.csv',p/'platform-firstboard-flags.csv']},'output_hashes':{f:hashlib.sha256((out/f).read_bytes()).hexdigest() for f in files},'self_check_prefix_comparisons':checks,'self_check_scope':'same function on identical event prefixes; independent verifier still required','data_policy':'fixed past cutoff; censored outcomes not backfilled; no actual fill simulation','raw_query':q,'factor_limitations':['exchange preclose absent','PIT float shares unknown','PIT industry unknown','market alignment not supplied','snapshot adjusted ratios not proof of historical factor availability']})
print('PASS:',len(records),'events;',len(candidates),'candidate records;',len(outcomes),'outcomes;',len(tracking),'daily follow-ups;',checks,'prefix comparisons. Not an independent certification.')
