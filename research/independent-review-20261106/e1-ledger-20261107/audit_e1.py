"""Independent read-only audit of persisted E1 artifacts; never executes a strategy."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import bisect
import csv
import hashlib
import json
import math
from pathlib import Path
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / 'research/strategy-search-20261107'
OUT = Path(__file__).resolve().parent
INPUT_HASHES = {}
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def load(rel):
    p = ROOT / rel
    INPUT_HASHES[rel] = sha(p)
    return json.loads(p.read_text(encoding='utf-8'))
def src(rel):
    return load('research/strategy-search-20261107/' + rel)
def dump(name, data):
    (OUT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

freeze = src('FREEZE_v3_E1.json')
execution = src('results/e1_v3/execution.json')
meta = src('results/e1_v3/inputs.json')
summary = src('results/e1_v3/e1_survivorship.json')
oldfreeze = src('FREEZE.json')
checks = {}
checks['freeze_hash_matches_execution'] = sha(SRC/'FREEZE_v3_E1.json') == execution['freeze_sha256'] == meta['freeze_sha256']
checks['old_freeze_preserved'] = sha(SRC/'FREEZE.json') == freeze['old_freeze_sha256']
checks['old_protocol_archive_matches_old_freeze'] = sha(SRC/'PROTOCOL_v2_ARCHIVE.md') == next(x['sha256'] for x in oldfreeze['docs'] if x['path']=='PROTOCOL.md')
checks['output_hashes'] = {rel: sha(SRC/'results/e1_v3'/rel) == digest for rel,digest in execution['outputs'].items()}
checks['currently_matches_frozen_files'] = {rel: (ROOT/rel).is_file() and sha(ROOT/rel)==digest for rel,digest in freeze['files_sha256'].items()}
checks['internal_freeze_time_precedes_execution'] = freeze['created_at'] < execution['started_at']
panelpath=SRC/'results/e1_v3/panel_input.arrow'
INPUT_HASHES[str(panelpath.relative_to(ROOT))]=sha(panelpath)
checks['panel_ipc_hash'] = sha(panelpath)==meta['panel_ipc_sha256']
panel = pl.read_ipc(panelpath, memory_map=False)
checks['panel_semantic_hash']=hashlib.sha256(panel.hash_rows(seed=74).to_numpy().tobytes()).hexdigest()==meta['panel_hash']
checks['unique_symbol_date']=panel.unique(subset=['symbol','date']).height==panel.height
calendar=panel['date'].unique().sort().to_list()
lifecycle=panel.group_by('symbol').agg(pl.col('date').max().alias('last_bar'),pl.len().alias('bars'))
stale=set(lifecycle.filter((pl.col('last_bar')<calendar[-21]) & (pl.col('bars')>=120))['symbol'].to_list())
checks['stale_definition']=sorted(stale)==meta['stale_symbols'] and str(calendar[-21])==meta['stale_cutoff_exclusive']
checks['panel_rows']=panel.height==meta['rows']
checks['panel_symbol_counts']=panel['symbol'].n_unique()==summary['counts']['n_symbols_A'] and panel.filter(~pl.col('symbol').is_in(stale))['symbol'].n_unique()==summary['counts']['n_symbols_B']
runs={g:src(f'results/e1_v3/run_C00_{g}.json') for g in ['A','B']}
checks['aligned_equity_dates']=[x['date'] for x in runs['A']['equity']]==[x['date'] for x in runs['B']['equity']]
# Quote-age diagnostics below classify observable data, not actual delisting or executable exits.
held_symbols=set(t['symbol'] for d in runs.values() for t in d['trades']) | set(p['symbol'] for d in runs.values() for p in d['carry']['positions'])
quotes={s:{} for s in held_symbols}
for row in panel.filter(pl.col('symbol').is_in(held_symbols)).iter_rows(named=True):
    quotes[row['symbol']][str(row['date'])]=row
quote_days={s:sorted(bisect.bisect_left(calendar,row['date']) for row in panel.filter(pl.col('symbol')==s).select('date','close').iter_rows(named=True) if row['close'] is not None and math.isfinite(row['close']) and row['close']>0) for s in held_symbols}
metrics={}; observations=[]
for group,d in runs.items():
    eq=d['equity']; vals=[x['value'] for x in eq]
    cagr=(vals[-1]/vals[0])**(252/(len(vals)-1))-1
    mv=sum(p['market_value'] for p in d['final_positions'])
    metrics[group]={'cagr':cagr,'final_equity':vals[-1],'normal_and_stale_terminal_mv':mv,'all_terminal_share':mv/vals[-1], 'stale_terminal_mv':sum(p['market_value'] for p in d['final_positions'] if p['symbol'] in stale),'closed_trades':len(d['trades']), 'terminal_positions':len(d['final_positions']), 'cash_plus_terminal_mv_error':d['final_cash']+mv-vals[-1]}
    intervals=[{**t,'terminal':False} for t in d['trades']] + [{**p,'exit_date':None,'terminal':True} for p in d['carry']['positions']]
    counts={'closed_intervals':len(d['trades']),'terminal_intervals':len(d['carry']['positions']),'eod_position_sessions':0,'missing_row_sessions':0,'invalid_close_sessions':0,'zero_or_invalid_volume_sessions':0,'no_positive_open_sessions':0,'quote_age_gt0_sessions':0,'max_quote_age_sessions':0,'ever_stale_member_intervals':0,'ever_stale_member_eod_sessions':0,'closed_trade_blocked_exit_days':sum(t.get('blocked_exit_days',0) for t in d['trades']),'terminal_blocked_exit_days':sum(p.get('blocked_exit_days',0) for p in d['carry']['positions'])}
    for ix,t in enumerate(intervals):
        symbol=t['symbol']; entry=str(t['entry_date'])[:10]; exit_date=str(t['exit_date'])[:10] if t['exit_date'] else None
        if symbol in stale:counts['ever_stale_member_intervals']+=1
        for e in eq:
            day=str(e['date'])[:10]
            if day<entry or (exit_date and day>=exit_date):continue
            counts['eod_position_sessions']+=1
            if symbol in stale:counts['ever_stale_member_eod_sessions']+=1
            row=quotes[symbol].get(day); day_id=bisect.bisect_left(calendar,__import__('datetime').date.fromisoformat(day)); q=quote_days[symbol]; prior=bisect.bisect_right(q,day_id)-1; age=day_id-q[prior] if prior>=0 else None
            flags=[]
            if row is None:counts['missing_row_sessions']+=1;flags.append('missing_row')
            else:
                for field,count in [('close','invalid_close_sessions'),('volume','zero_or_invalid_volume_sessions'),('open','no_positive_open_sessions')]:
                    val=row[field]
                    if val is None or not math.isfinite(val) or val<=0:counts[count]+=1;flags.append(count)
            if age is not None:
                counts['max_quote_age_sessions']=max(counts['max_quote_age_sessions'],age)
                if age>0:counts['quote_age_gt0_sessions']+=1
            if flags or age or symbol in stale:
                observations.append({'group':group,'interval':ix,'symbol':symbol,'entry_date':entry,'exit_date':exit_date,'date':day,'end_stale_member':symbol in stale,'quote_age_sessions':age,'flags':flags})
    metrics[group]['path_observation_proxy']=counts
    metrics[group]['terminal_quote_dates']={p['symbol']:max(k for k in quotes[p['symbol']] if k<=str(eq[-1]['date'])[:10]) for p in d['final_positions']}
    metrics[group]['blocked_exit_trades']=[{k:t[k] for k in ['symbol','entry_date','exit_date','blocked_exit_days']} for t in d['trades'] if t.get('blocked_exit_days')]
    metrics[group]['stale_member_closed_trades']=[{k:t[k] for k in ['symbol','entry_date','exit_date','pnl_amount']} for t in d['trades'] if t['symbol'] in stale]
    checks[group+'_summary_cagr']=abs(cagr-summary[group]['cagr'])<1e-12
    checks[group+'_terminal_reconciliation']=abs(metrics[group]['cash_plus_terminal_mv_error'])<.05
    checks[group+'_share']=abs(mv/vals[-1]-summary[group]['open_at_end_share'])<1e-12
metrics['delta_cagr_pp']=(metrics['A']['cagr']-metrics['B']['cagr'])*100
metrics['annual_differences_pp']={}
for year in sorted(set(x['date'][:4] for x in runs['A']['equity'])):
    idx=[i for i,x in enumerate(runs['A']['equity']) if x['date'].startswith(year)]; lo=max(0,idx[0]-1); hi=idx[-1]
    metrics['annual_differences_pp'][year]=100*((runs['A']['equity'][hi]['value']/runs['A']['equity'][lo]['value'])-(runs['B']['equity'][hi]['value']/runs['B']['equity'][lo]['value']))
checks['yearly_differences_recomputed']=all(abs(metrics['annual_differences_pp'][str(x['year'])]-x['diff_pp'])<1e-10 for x in summary['yearly'])
checks['haircuts_recomputed']=all(abs(((metrics['A']['final_equity']+h['haircut']*metrics['A']['stale_terminal_mv'])/runs['A']['equity'][0]['value'])**(252/(len(runs['A']['equity'])-1))-1-h['cagr_A'])<1e-12 for h in summary['haircut_sensitivity'])
metrics['old_fail_trigger_all_positions_gt2pct']=metrics['A']['all_terminal_share']>.02
metrics['old_fail_trigger_abs_cagr_diff_ge3pp']=abs(metrics['delta_cagr_pp'])>=3
checks['old_verdict_reproduced']=summary['verdict']=='FAIL' and execution['actual_exit_code']==3 and metrics['old_fail_trigger_all_positions_gt2pct']
checks['inputs_unchanged_during_audit']={rel:sha(ROOT/rel)==digest for rel,digest in INPUT_HASHES.items()}
dump('e1-independent-evidence.json',{'method':'No simulation; recompute hashes, arithmetic and interval/quote observations from persisted results. Path metrics are EOD position-session proxies; exclude exit-date intraday exposure and cannot establish real executability or share-action accounting.', 'checks':checks,'metrics':metrics,'path_observations':observations,'input_sha256':INPUT_HASHES})
def all_true(value):
    return all(all_true(x) for x in value.values()) if isinstance(value,dict) else value is True
assert all_true(checks), 'Independent evidence checks failed; inspect e1-independent-evidence.json'
print(json.dumps({'metrics':metrics,'hash_failed':[k for k,v in checks['output_hashes'].items() if not v], 'frozen_file_mismatches':[k for k,v in checks['currently_matches_frozen_files'].items() if not v], 'scalar_checks':{k:v for k,v in checks.items() if isinstance(v,bool)},'path_observation_rows':len(observations)},ensure_ascii=False,indent=2))
