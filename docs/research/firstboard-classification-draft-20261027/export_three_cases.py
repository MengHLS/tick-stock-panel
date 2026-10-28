import duckdb,csv,json,hashlib,gzip
from pathlib import Path
p=Path(__file__).parent
c=duckdb.connect()
q="""SELECT symbol,date,open,high,low,close,volume,raw_close,raw_high,raw_low FROM read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet',hive_partitioning=true) WHERE date BETWEEN DATE '2025-08-01' AND DATE '2026-10-23' AND symbol IN ('002687.SZ','002241.SZ','002945.SZ') ORDER BY symbol,date"""
result=c.execute(q); names=[x[0] for x in result.description];rows=[dict(zip(names,x)) for x in result.fetchall()]
if not rows: raise RuntimeError('No matching symbols; inspect symbol format')
for r in rows:r['date']=str(r['date'])
f=p/'three-case-paths.csv'
with f.open('w',encoding='utf-8',newline='') as out:
 w=csv.DictWriter(out,fieldnames=names);w.writeheader();w.writerows(rows)
# Computation below uses ONLY frozen rows reloaded from exported file.
rows=list(csv.DictReader(f.open(encoding='utf-8')))
oldpath=Path('C:/work/sourcecode/stock-limit-up-analyzer/docs/research/FIRSTBOARD-20261023-RECURSIVE-2019-V1-20261026/target-chain-summary.csv')
old={x['stockCode']:x for x in csv.DictReader(oldpath.open(encoding='utf-8-sig'))}
links=Path('C:/work/sourcecode/stock-limit-up-analyzer/docs/research/FIRSTBOARD-20261023-RECURSIVE-2019-V1-20261026/candidate-links.csv.gz')
with gzip.open(links,'rt',encoding='utf-8-sig') as inp:
 reader=csv.DictReader(inp); linkcols=reader.fieldnames; sample=list(reader)
(p/'candidate-links-schema.json').write_text(json.dumps({'columns':linkcols,'example':sample[:1]},ensure_ascii=False,indent=2),encoding='utf-8')
reports=[]
for code in ['002687.SZ','002241.SZ','002945.SZ']:
 o=old[code]; allrows=[x for x in rows if x['symbol']==code]; anchor=o['selectedAnchorDate'];nearest=o['nearestEligiblePrior']; target=allrows[-1];before=allrows[:-1]
 traces=[]
 for a in sorted(set([anchor,nearest])):
  rs=[x for x in before if x['date']>=a]
  decline=next((i for i in range(1,len(rs)) if float(rs[i]['close'])<float(rs[i-1]['close'])),None)
  versions=[]
  for include in [False,True]:
   if decline is None: versions.append({'include_decline_high':include,'state':'no_first_decline','P':None});continue
   peakrows=rs[:decline+int(include)];peak=max(peakrows,key=lambda x:float(x['high']));P=float(peak['high'])
   afterpeak=[x for x in allrows if peak['date']<x['date']<=target['date']]
   br=next((x for x in afterpeak if float(x['close'])>P),None)
   setup=[x for x in before if peak['date']<x['date'] and (br is None or x['date']<br['date'])]
   low=min(setup,key=lambda x:float(x['low'])) if setup else None
   after=[x for x in before if br is not None and x['date']>br['date']]
   la=min(after,key=lambda x:float(x['low'])) if after else None
   d=(P-float(low['low']))/P if low else None
   prior=bool(br and br['date']<target['date'])
   state='prior_close_break' if prior else 'no_setup' if low is None else 'shallow_pullback' if d<.05 else 'left_low_below_P' if float(before[-1]['close'])>float(low['low']) else 'at_or_below_setup_low'
   versions.append({'include_decline_high':include,'P':P,'P_date':peak['date'],'P_known_at':rs[decline]['date'],'P_window':max(float(x['high']) for x in rs),'P_window_date':max(rs,key=lambda x:float(x['high']))['date'],'L_setup':float(low['low']) if low else None,'L_setup_date':low['date'] if low else None,'L_after':float(la['low']) if la else None,'L_after_date':la['date'] if la else None,'depth':d,'first_break_date':br['date'] if br else None,'C_T_minus_1':float(before[-1]['close']),'T_minus_1':before[-1]['date'],'path_state_T_minus_1':state,'break_event_T':{'first_break_on_T':bool(br and br['date']==target['date']),'prior_break':prior,'relation':'above' if float(target['close'])>P else 'below' if float(target['close'])<P else 'equal'},'reason_code':'CANDIDATE_RULE_NOT_FINAL'})
  traces.append({'anchor':a,'versions':versions})
 reports.append({'code':code,'target':target['date'],'close_T':float(target['close']),'basis':'enriched unrounded forward-adjusted snapshot upper date 2026-10-27; frozen CSV values','firstboard_identity':'HISTORICAL_REGIME_UNCERTIFIED','legacy_selected_anchor':anchor,'legacy_nearest_anchor':nearest,'anchor_selection':'legacy externally provided; not re-certified','recursion_reason':'See frozen legacy candidate links; current candidate traces only cover nearest and selected, not full recursion' if nearest!=anchor else 'nearest equals legacy selected','traces':traces})
(p/'three-case-results.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
# Preserve full legacy links separately for independent audit, without guessing schema fields.
selected=[x for x in sample if any(code in str(x) for code in ['002687.SZ','002241.SZ','002945.SZ'])]
(p/'three-case-legacy-links.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding='utf-8')
manifest={'path_csv_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'rows':len(rows),'source':'D:/TSP/data/kline_daily_enriched','snapshot_upper_date':'2026-10-27','query':q,'legacy_summary_sha256':hashlib.sha256(oldpath.read_bytes()).hexdigest(),'legacy_links_sha256':hashlib.sha256(links.read_bytes()).hexdigest(),'limitations':['No full source table freeze','No historical regime certification','Nearest and selected anchors externally supplied','Candidates A/B remain undecided']}
(p/'three-case-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('Frozen rows:',len(rows),'legacy candidate links:',len(selected))
for r in reports:
 print(r['code'],json.dumps(r['traces'],ensure_ascii=False))
