"""Enumerate evidence-backed rule identities, not a guessed exact global DSR N."""
import ast
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
HASHES={}
def read(rel):
    p=ROOT/rel; raw=p.read_bytes(); HASHES[rel]=hashlib.sha256(raw).hexdigest();return raw.decode('utf8')
def load(rel):return json.loads(read(rel))
def digest(text):return hashlib.sha256(text.encode('utf8')).hexdigest()
def write(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
search='research/strategy-search-20261107/'
prior='research/strategy-reliability-20261106/'
batch='research/batch-backtest-framework-20261107/'
old=load(search+'FREEZE.json'); glob=load(search+'GLOBAL_LEDGER_v3.json')
audit=load('research/independent-review-20261106/matrix-e2e-20261107/trial-accounting.json')
registry=load(search+'results/registry.json'); br=load(batch+'out/registry.json')
common_rel=search+'scripts/common.py'; common=read(common_rel); tree=ast.parse(common)
strategy_calls=[]
for node in ast.walk(tree):
    if isinstance(node,ast.AnnAssign) and isinstance(node.target,ast.Name) and node.target.id=='STRATEGIES':strategy_calls=node.value.elts
alias_sources={}
for node in ast.walk(tree):
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='alias' and node.args and isinstance(node.args[0],ast.Constant):
        alias_sources[node.args[0].value]=(node.lineno,ast.unparse(node.func.value))
rows=[]
for call in strategy_calls:
    vals=[ast.literal_eval(x) for x in call.args]; key,family,title,entry,exit_,score,max_hold,holding=vals
    definition={'entry':alias_sources[entry][1],'exit':alias_sources[exit_][1],'score':alias_sources[score][1],'max_hold_days':max_hold,'common_universe':'common.py:175-202; shared universe/indicator dependencies included in source hash'}
    executions=[k for k,v in registry['runs'].items() if v['strategy']==key]
    rows.append({'id':key,'origin':'public-search','fixed_rule':definition,'evidence':[f'{common_rel}:{call.lineno}',f'{common_rel}:{alias_sources[entry][0]}',search+'results/registry.json#runs/'+key],'semantic_signature_sha256':digest(json.dumps(definition,sort_keys=True)),'observed_registry_execution_rows':len(executions),'execution_keys':executions,'dedup_reason':'10/30/gross are prespecified cost robustness scenarios of this rule; not 3 identities. Different entry/exit/hold definition from other S rows. Scenario choice history remains unknown.'})
prior_rel=prior+'scripts/validate_candidates.py';prior_source=read(prior_rel)
prior_defs={
 'momentum':'eligible: bars>=120, non-ST, raw price>=3, prior amount20>=1e8, volume>0, mom60 cross-sectional rs>=0.9, close>ma60 and ma20>ma60; daily entry; exit close<ma20; score mom60; max_hold20',
 'breakout_volume':'momentum eligible AND close>prior_high55 AND volume>1.5*prior_vol20; exit close<ma20; score mom60; max_hold20',
 'breakout_volume_market':'breakout_volume AND market_breadth>=0.5 (breadth from all calculable MA60 rows); exit close<ma20; score mom60; max_hold20'}
prior_regs={name:load(prior+'results/'+name+'.json') for name in ['validation','constrained-validation']}
for name,definition in prior_defs.items():
    occurrences=[{'registry':prior+'results/'+reg+'.json','year':fold['year'],'slippage_bps':v['slippage_bps']} for reg,d in prior_regs.items() for fold in d['folds'] for v in fold['variants'] if v['name']==name]
    rows.append({'id':'T03_'+name,'origin':'prior-search','fixed_rule':definition,'evidence':[prior_rel+':43-85',prior_rel+':103-109']+[prior+'results/'+name+'.json' for name in prior_regs],'semantic_signature_sha256':digest(definition),'observed_registry_execution_rows':len(occurrences),'executions':occurrences,'dedup_reason':'Years and prespecified costs are executions, not new rule families. S03 differs: monthly, MA120, no RS>=0.9; S09 differs: no RS>=0.9/MA60/MA20 eligibility; S12 lowvol entry differs. Original vs constrained execution revisions cannot be certified pure reruns: selection/accounting delta unknown.'})
prod_paths={'first_board_chain_rebreak':'backend/app/custom/first_board_event_chain/strategy_rebreak.py','first_limit_pullback_3f_runner_t74':'backend/app/custom/first_board_event_chain/first_limit_pullback_3f_runner_t74.py'}
for run in br['runs']:
    key=run['strategy_id']; rel=prod_paths[key]; text=read(rel)
    definition=('Strict first-board event-chain rebreak; pullback threshold 5%; exit MA20 cross-down; SL8%, maxhold10' if 'chain_rebreak' in key else 'First-board T1-T5 pullback, amplitude<14%, 3-factor score>=55%, Top3, daily cap2, SL6%, profit3% activates close-drawdown8%, runner extension74')
    rows.append({'id':key,'origin':'production-batch','fixed_rule':definition,'batch_explicit_params':run['params'],'full_default_source_sha256':HASHES[rel],'evidence':[rel+(':75-163' if 'chain_rebreak' in key else ':13-130'),batch+'groups.json',batch+'out/registry.json#runs/'+run['run_id']],'semantic_signature_sha256':digest(definition+json.dumps(run['params'],sort_keys=True)),'observed_registry_execution_rows':run['n_trials'],'dedup_reason':'Event-chain/first-board pullback conditions and exits differ materially from all 12 public rules and 3 T03 rules; not a name alias. 3 IS plus 3 OOS fold simulations count 6 executions for 1 parameterized rule; audit/native-vs-single reruns add zero new identities. Earlier equivalent T74 versions deduplication and historical parameter selection remain unknown.'})
assert len(rows)==17 and len(set(x['id'] for x in rows))==17
result={'scope':'Enumerated distinct rule-form lower bound, NOT exact global hypothesis count or effective independent DSR N','enumerated_lower_bound_rule_forms':17,'global_N_exact':None,'dsr_effective_independent_N':None,'counts_reconciliation':{'old_freeze_total':old['n_trials']['total'],'global_v3_lower_bound':glob['global_N_lower_bound'],'prior_independent_lower_bound':audit['identifiable_lower_bound_rule_families'],'delta_to_v3':2,'reason':'12 public fixed rules + 3 distinct T03 rules + 2 distinct first-board production rules = 17 enumerable forms; no overlap with T03 by inspected conditions, filters, and exit rules.'},'selected_execution_records':{'public_search_registry_rows':len(registry['runs']),'T03_two_registries_rows':sum(len(f['variants']) for d in prior_regs.values() for f in d['folds']),'batch_fold_simulations':br['totals']['n_trials'],'sum_of_selected_records':len(registry['runs'])+sum(len(f['variants']) for d in prior_regs.values() for f in d['folds'])+br['totals']['n_trials'],'not_global_execution_count':True,'E1_C00_replays':2,'E1_alpha_delta':0,'audit_replays_alpha_delta':0},'identities':rows,'unknowns':['Historical production parameter grids, T74 entry/exit studies and strategy revisions lack exhaustive identities and selection links; do not assume only 17 total','T03 validation vs constrained-validation have distinct source hashes and different data/results: execution revision history and selection use unresolved','Public search score mapping/final code changes and repeated S07 results are not proven pure reproductions; trial lineage and use of observations incomplete','Cost-scenario winner choice or universe/data-version choice used to improve results must be registered; no evidence of exhaustive absence','Rule-form count differs from count of selection opportunities and from effective independent trials; correlations do not justify arbitrary N reduction','Unknown missing/deleted/unregistered trials cannot be inferred from current files'], 'input_sha256':HASHES}
write('hypothesis-inventory.json',result)
md=['# 可枚举假设清单（下限17；全局精确N未知）','','| ID | 原始证据 | 已存执行行/折次数 | 不合并理由 |','| --- | --- | ---: | --- |']
for row in rows:
    reason = {'public-search':'固定信号/退出/持有形式单列；10/30/gross成本轴合并到同一形式，择优历史未知。','prior-search':'T03含RS与趋势资格等，区别于S03/S09/S12；年度与成本重复不增加规则形式，执行修订选择沿革未知。','production-batch':'首板事件规则区别于公开策略和T03；3IS+3OOS为执行次数。早期版本/参数搜索的完整去重未知。'}[row['origin']]
    md.append(f"| {row['id']} | {'; '.join(row['evidence'])} | {row['observed_registry_execution_rows']} | {reason} |")
assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in HASHES.items()), 'Inputs changed during ledger audit'
(OUT/'HYPOTHESES.md').write_text('\n'.join(md)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k not in ['identities','input_sha256','unknowns']},indent=2))
