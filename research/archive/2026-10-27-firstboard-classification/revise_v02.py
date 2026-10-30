import json
from pathlib import Path
p=Path(__file__).parent
cases=json.loads((p/'cases.json').read_text(encoding='utf-8'))
for c in cases:
    conflict=bool(c['Ldate'] and c['breakdate'] and c['Ldate']>c['breakdate'])
    c['evidence_role']='旧标签顺序冲突反例' if conflict else '形态对照，非新规则正例'
    c['price_basis']={'status':'待核验','description':'源报告称使用公司行动与局部价格认证；未追溯逐例复权基准日、因子版本、全路径，不能凭小数位数判断同尺度'}
    c['P_episode']={'value':None,'date':None,'known_at':None,'status':'待核验，legacy P不能直接认证为新定义'}
    c['P_window']={'value':None,'date':None,'known_at':None,'status':'待完整OHLC路径'}
    c['L_setup']={'value':None,'date':None,'known_at':None,'status':'待完整突破前路径认证'}
    c['L_after']={'value':c['L'] if conflict else None,'date':c['Ldate'] if conflict else None,'status':'旧报告全路径最低落在突破后，未认证为新规则区间最低' if conflict else '待核验/不适用尚未判定'}
    c['path_state_T_minus_1']={'value':None,'asof':'T-1 close','status':'待路径重算，不继承T日旧标签'}
    c['break_event_T']={'value':None,'asof':c['T']+' close','status':'待P与突破历史认证；旧breakdate只保留事实来源'}
    c['legacy']={k:c[k] for k in ['P','Pdate','L','Ldate','breakdate','status']}
    for k in ['P','Pdate','L','Ldate','breakdate','status']: del c[k]
(p/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def row(d,o,h,l,c):return {'session':d,'open':str(o),'high':str(h),'low':str(l),'close':str(c),'volume':'1000'}
fixtures=[
 {'id':'B9','purpose':'下降日最高价归属','rows':[row('S0',98,100,97,99),row('S1',99,110,96,98),row('S2',98,99,90,94),row('T',100,106,99,105)],'context':{'anchor':'S0','q':'0.05','first_decline':'S1'},'expected_by_candidate':{'exclude_decline_day':{'P_episode':'100','P_window':'110','close_above_episode':True},'include_decline_day':{'P_episode':'110','P_window':'110','close_above_episode':False}},'decision':'待定；不将候选之一作为通过标准'},
 {'id':'B10','purpose':'曾突破分支目标等P','rows':[row('S0',98,100,97,99),row('S1',98,99,95,96),row('S2',99,102,98,101),row('T',101,102,99,100)],'context':{'P_frozen':'100','first_break':'S2'},'expected':{'prior_break':True,'current_relation':'equal','close_above_P':False,'first_break_on_T':False}},
 {'id':'B11','purpose':'L等P分母零','rows':[row('S0',100,100,100,100),row('S1',100,100,100,100),row('T',100,100,100,100)],'context':{'P_frozen':'100','L_setup_candidate':'100','q':'0.05'},'expected':{'drawdown':'0','qualified_pullback':False,'recovery_ratio':None,'close_above_P':False}},
 {'id':'B12','purpose':'盘中越P但收盘未过','rows':[row('S0',98,100,97,99),row('S1',98,99,94,95),row('T',98,103,97,99)],'context':{'P_frozen':'100','no_prior_close_break':True},'expected':{'intraday_above_P':True,'close_above_P':False,'first_break_on_T':False}},
 {'id':'B13','purpose':'最近锚点浅回调是否递归','rows':[row('S0',95,100,94,99),row('S1',98,99,90,92),row('S2',95,98,94,97),row('S3',97,99,96,98),row('T',98,100,97,99)],'context':{'firstboard_dates':['S0','S2'],'nearest_anchor':'S2','older_anchor':'S0','q':'0.05','price_basis':'synthetic same scale','firstboard_membership':'外部显式提供，非由这组OHLC推导'},'expected_by_candidate':{'recurse_on_shallow':{'nearest_depth':'0.02040816326530612244897959184','action':'continue','selected_anchor':'S0'},'nearest_only':{'selected_anchor':'S2','state':'shallow_pullback'}},'decision':'递归政策待定；现行浅回调继续回溯作对照'}]
(p/'boundary-fixtures.json').write_text(json.dumps(fixtures,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert len(cases)==12 and len(fixtures)==5
assert sum(c['evidence_role']=='旧标签顺序冲突反例' for c in cases)==2
print('12 cases migrated; 2 counterexamples isolated; 5 OHLCV fixtures saved')
