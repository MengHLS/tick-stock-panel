import csv,json,hashlib,subprocess
from pathlib import Path
from decimal import Decimal as D
p=Path(__file__).parent
cases=json.loads((p/'cases.json').read_text(encoding='utf-8'))
src=Path('C:/work/sourcecode/stock-limit-up-analyzer/docs/research/FIRSTBOARD-20261023-RECURSIVE-2019-V1-20261026/target-chain-summary.csv')
old={r['stockCode']:r for r in csv.DictReader(src.open(encoding='utf-8-sig'))}
for c in cases:
 code=c['code']; reason='PATH_EVIDENCE_PENDING'
 if code=='603448.SH': reason='HISTORY_COVERAGE_INSUFFICIENT';c['evidence_role']='历史覆盖不足，不能认证无前次首板'
 if code=='000700.SZ': reason='LEGACY_ANOMALY_NOT_REPRODUCED';c['evidence_role']='旧报告异常在当前数据中未复现；不是已认证缺行样本'
 if code=='002612.SZ': reason='DISTANCE_DIRECTION_CONFLICT';c['evidence_role']='距P方向冲突：旧+8.25%，面板近似规则−1.57%；原因未归因'
 c['quality_reason_codes']=[reason,'HISTORICAL_REGIME_UNCERTIFIED']
 c['firstboard_identity']={'value':None,'reason_code':'HISTORICAL_REGIME_UNCERTIFIED','note':'形态价格数值可复现不等于首板身份可认证；不默认历史非ST'}
 c['nearest_stage']={'value':old[code]['nearestStage'] if code in old else None,'scope':'legacy','reason_code':'LEGACY_ONLY' if code in old else 'SOURCE_STAGE_NOT_MAPPED'}
 c['recursion_steps']={'value':None,'reason_code':'CANDIDATE_TRACE_PENDING' if c['anchor'] else 'HISTORY_COVERAGE_INSUFFICIENT'}
 for k in ['P_episode','P_window','L_setup','L_after','path_state_T_minus_1','break_event_T']:
  c[k]['reason_code']=reason
  if code=='603448.SH': c[k]['status']='历史覆盖不足；不能据此判断结构不适用'
  if code=='000700.SZ': c[k]['status']='旧异常未复现，待跨版本字段和路径核对'
 c['price_basis']['current_snapshot_ref']='DATA-MANIFEST.json'
 c['price_basis']['legacy_basis_status']='LEGACY_FACTOR_BASE_PENDING'
 c['L_breakday']={'value':None,'date':c['legacy']['breakdate'] or None,'reason_code':reason}
 if code in ['000559.SZ','002241.SZ','002612.SZ']:
  c['discrepancy_hypotheses']={'status':'未归因','candidates':['下降日高价归属','峰值定义','锚点选择','原始行情/公司行动/复权版本差异'],'note':'均需逐项复算，未排除数据差异'}
(p/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
f=json.loads((p/'boundary-fixtures.json').read_text(encoding='utf-8'))
b=next(x for x in f if x['id']=='B13');r=next(x for x in b['rows'] if x['session']=='S3');r.update(close='96',low='94')
b['expected_by_candidate']['recurse_on_shallow']['nearest_depth']=str((D('98')-D('94'))/D('98'))
b['expected_by_candidate']['recurse_on_shallow']['nearest_state']='shallow_pullback'
def row(s,o,h,l,c): return dict(session=s,open=str(o),high=str(h),low=str(l),close=str(c),volume='1000')
for id_,rows,st,prior,relation in [
 ('B14',[row('S0',98,100,97,99),row('S1',98,99,90,92),row('T-1',93,97,92,96),row('T',98,103,97,102)],'left_low_below_P',False,'above'),
 ('B15',[row('S0',98,100,97,99),row('S1',98,99,94,95),row('T-1',94,95,90,90),row('T',95,103,94,102)],'at_low',False,'above'),
 ('B16',[row('S0',98,100,97,99),row('S1',98,99,90,92),row('S2',98,103,97,102),row('T-1',101,102,99,100),row('T',99,100,97,98)],'prior_close_break',True,'below')]:
 f.append({'id':id_,'purpose':'T−1路径与T日事件分离','rows':rows,'context':{'P_frozen':'100','L_setup':'90','recovery_definition':'仅验证是否离开低点，不认证有效回攻'},'expected':{'path_state_T_minus_1':st,'break_event_T':{'prior_break':prior,'first_break_on_T':not prior,'current_relation':relation}}})
(p/'boundary-fixtures.json').write_text(json.dumps(f,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
manifest={'status':'逻辑快照指纹；共享存储未物理冻结，缺全表内容哈希，不足以保证后续完全复现','source':'DATA-EVIDENCE.md','data_root':'D:/TSP/data','observed_upper_date':'2026-10-27','adjustment_base':'当前面板数据快照上界2026-10-27；旧案例因子基准未认证','tables':{'daily':{'rows':9728665,'symbols':5810,'start':'2018-01-08','end':'2026-10-27'},'enriched':{'rows':9728665,'start':'2018-01-08','end':'2026-10-27','reported_mtime':'2026-10-27 10:28'},'adj_factor':{'rows':32840,'symbols':5183,'start':'2018-01-11','end':'2026-10-27'},'instruments':{'symbols':5889,'as_of':'2026-10-26','history':False},'index_daily':{'sessions':243,'start':'2025-10-27','end':'2026-10-27'},'union_calendar':{'sessions':2133,'official':False}},'limitations':['历史ST未知','早期创业板制度漏判风险','历史股票池不可完整还原','缺官方长历史交易日历'],'source_hashes':{str(src):hashlib.sha256(src.read_bytes()).hexdigest(),'DATA-EVIDENCE.md':hashlib.sha256((p/'DATA-EVIDENCE.md').read_bytes()).hexdigest()},'code_head':'待登记；本轮未执行引擎计算','code_dirty_status':'未冻结工作区，HEAD不代表实际执行代码全状态'}
(p/'DATA-MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for x in f:
 for r in x['rows']:
  o,h,l,c=[D(r[k]) for k in ['open','high','low','close']];assert l<=min(o,c)<=max(o,c)<=h
b=next(x for x in f if x['id']=='B13');assert D(b['rows'][3]['close'])<D(b['rows'][2]['close'])
assert (D('98')-D('94'))/D('98')<D('.05')
for x in f[-3:]:
 rows=x['rows'];P=D(x['context']['P_frozen']);L=D(x['context']['L_setup']);e=x['expected']; prior=any(D(r['close'])>P for r in rows[:-1]);ct=D(rows[-1]['close']);cm=D(rows[-2]['close'])
 state='prior_close_break' if prior else ('at_low' if cm==L else 'left_low_below_P')
 assert state==e['path_state_T_minus_1']
 assert prior==e['break_event_T']['prior_break']
 assert (ct>P and not prior)==e['break_event_T']['first_break_on_T']
 assert ('above' if ct>P else 'below' if ct<P else 'equal')==e['break_event_T']['current_relation']
print('PASS: 8 fixture OHLC checks; corrected B13 decline; B14-B16 independent path/break assertions; 12 case statuses updated. No engine validation.')
