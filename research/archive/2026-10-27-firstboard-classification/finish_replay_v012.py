import json,copy,hashlib,csv,html
from pathlib import Path
p=Path(__file__).parent;old=p/'event-replay-v011-schema';new=p/'event-replay-v012-schema';new.mkdir(exist_ok=True)
src=old/'candidate-classifications.json';before=json.loads(src.read_text(encoding='utf-8'));after=copy.deepcopy(before);changes=[]
for i,r in enumerate(after):
 cl=r['classification'];nodes=([('selected',cl['selected'])] if cl['selected'] else [])+[(f'trace[{j}]',v) for j,v in enumerate(cl['trace'])]
 for scope,v in nodes:
  if 'new_high_after_anchor' not in v:
   assert v['path_state']=='no_first_decline'
   v['new_high_after_anchor']=None;v.setdefault('null_reason_codes',{})['new_high_after_anchor']='NO_FIRST_DECLINE_BEFORE_D'
   changes.append({'row':i,'event_id':r['event_id'],'rule':r['rule'],'path':'classification.'+scope+'.new_high_after_anchor','before':'KEY_ABSENT','after':None,'reason':'NO_FIRST_DECLINE_BEFORE_D'})
assert len(changes)==24
restored=copy.deepcopy(after)
for ch in changes:
 cl=restored[ch['row']]['classification'];part=ch['path'].split('.')[1];v=cl['selected'] if part=='selected' else cl['trace'][int(part[6:-1])];del v['new_high_after_anchor'];del v['null_reason_codes']['new_high_after_anchor']
assert restored==before
f=new/'candidate-classifications.json';f.write_text(json.dumps(after,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(new/'schema-differences.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(new/'manifest.json').write_text(json.dumps({'schema_version':'v0.1.2','calculation_version':'v0.1 unchanged','source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'added_nulls':24,'selected':8,'trace':16,'validation':'removing these 24 additions and their reason entries gives exact v0.1.1 equality','amount':'not independently verified','prior_versions':'preserved'},ensure_ascii=False,indent=2),encoding='utf-8')
# Read reviewed outputs only; no calculation or market-data queries.
o=p/'event-replay-v01';events=json.loads((o/'historical-events.json').read_text(encoding='utf-8'));tracking=json.loads((o/'forward-tracking.json').read_text(encoding='utf-8'));outcomes=list(csv.DictReader((o/'forward-outcomes.csv').open(encoding='utf-8')))
chart=(o/'event-price-charts.html').read_text(encoding='utf-8');import re
articles=re.findall(r'<article>.*?</article>',chart,flags=re.S);assert len(articles)==27
plots={}
for article in articles:
 eid=re.search(r'<h2>(.*?)</h2>',article).group(1);svg=re.search(r'<svg.*?</svg>',article,flags=re.S).group(0);plots[eid]=svg
factors=list(csv.DictReader((o/'factor-snapshots-long.csv').open(encoding='utf-8')))
def pretty(x):return '<pre>'+html.escape(json.dumps(x,ensure_ascii=False,indent=2))+'</pre>'
def fmt(v):
 if v is None or v=='':return '缺失'
 return f'{float(v)*100:+.2f}%'
def table(headers,rows):return '<table><thead><tr>'+''.join('<th>'+html.escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'
sections=[];options=[]
for e in events:
 eid=e['event_id'];code=e['code'];date=e['date'];options.append(f'<option value="{eid}" data-code="{code}">{code} · {date}</option>')
 cs=[r for r in after if r['event_id']==eid];ts=[r for r in tracking if r['event_id']==eid];os=[r for r in outcomes if r['event_id']==eid];fs=[r for r in factors if r['event_id']==eid]
 price=table(['原始开','原始高','原始低','原始收','上一可观测原始收盘'],[[e['raw_open'],e['raw_high'],e['raw_low'],e['raw_close'],e['previous_observed_raw_close']]])
 ftable=table(['时点','字段','数值','窗口','原因'],[[r['snapshot_role'],r['factor'],r['value'] or '缺失',r['window'],r['reason_code']+('；amount未独立核验' if r['factor']=='amount' else '')] for r in fs])
 # Distinguish sidecar vs original independently reviewed snapshots.
 originalf=pretty({'D_minus_1':e['factors_D_minus_1'],'D_close':e['factors_D_close']})
 ct=[]
 for r in cs:
  cl=r['classification'];s=cl['selected'];ct.append([r['rule'],cl['nearest_anchor'] or '无',s['anchor'] if s else '无',s['path_state'] if s else cl['reason'],s['P'] if s and s['P'] is not None else '缺失',s['L_setup'] if s and s['L_setup'] is not None else '缺失',json.dumps(s['break_event'],ensure_ascii=False) if s else '缺失'])
 ot=table(['期限（后续可观测日K）','结束日','收盘收益','最高价相对D收盘','最低价相对D收盘','状态'],[[r['horizon_observed_sessions'],r['horizon_end'] or '未满期',fmt(r['close_return']),fmt(r['max_high_return']),fmt(r['min_low_return']),r['reason']] for r in os])
 tt=table(['观察日','步数','冻结D日P','当日相对P','更新描述','相对D收盘变化'],[[r['asof'],r['step_observed_sessions'],r['frozen_D_P'] if r['frozen_D_P'] else '缺失',r['current_relation_to_frozen_P'] or '未知',r['tracking_label'],fmt(r['return_since_D'])] for r in ts])
 sections.append(f'<section data-eid="{eid}"><h2>{eid}</h2><p>判断版本 {e["version"]}；身份：历史制度未认证。背景只到D−1，事件信息截至D收盘。</p>'+price+'<p>官方除权昨收缺失；上一可观测收盘不能冒充交易所前收。图为固定复权价格，不能直接与原始价跨基准混比。</p>'+plots[eid]+'<h3>当时的因子</h3><details><summary>已复核的原始D−1 / D快照（amount除外）</summary>'+originalf+'</details><details><summary>显式公式与原因码副表（240/250分列；此副表整体未独立验收）</summary>'+ftable+'</details><h3>16套当日候选判断</h3>'+table(['规则','最近锚点','选中锚点','D−1路径状态','P','L_setup','D事件'],ct)+'<details><summary>完整候选路径、可知日期与原因码</summary>'+pretty(cs)+'</details><details class="future"><summary>揭示后续表现（评价字段，不是可实现交易收益）</summary>'+ot+'</details><details class="future"><summary>揭示每日更新（不覆盖D日判断）</summary>'+tt+'<details><summary>逐日因子及完整跟踪记录</summary>'+pretty(ts)+'</details></details></section>')
style='body{font:15px system-ui;max-width:1250px;margin:24px auto;padding:0 16px;background:#f8fafc;color:#172033}.notice,section{background:white;border:1px solid #dbe2ea;border-radius:10px;padding:18px;margin:16px 0}section{display:none}section.active{display:block}svg{width:100%}select{padding:10px;margin:8px;font-size:15px}table{border-collapse:collapse;width:100%;font-size:12px;display:block;overflow:auto}th,td{border:1px solid #dbe2ea;padding:7px;white-space:normal}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}details{padding:12px;margin:12px 0;border:1px solid #cbd5e1}summary{cursor:pointer;font-weight:600}.future{border-color:#d97706}'
script="""const stocks=document.getElementById('stock'),dates=document.getElementById('event');function selectStock(){for(const o of dates.options)o.hidden=stocks.value!=='all'&&o.dataset.code!==stocks.value;dates.value=Array.from(dates.options).find(o=>!o.hidden).value;show();}function show(){document.querySelectorAll('section[data-eid]').forEach(s=>{s.classList.toggle('active',s.dataset.eid===dates.value);s.querySelectorAll('details.future').forEach(d=>d.open=false);});}stocks.onchange=selectStock;dates.onchange=show;show();"""
page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>27个历史首板逐次回放</title><style>'+style+'</style><h1>历史首板：先看当时，再揭示后来</h1><div class="notice">四股27个事件，432条=事件×16套候选规则，不是432个独立样本。仅作已观察样本的方法验证；未完成含成本与成交限制的策略回测。历史身份与制度未认证。<p>原计算、时点及后续表已通过报告所列独立检查；v0.1.2仅补24处模式空值，待本轮收尾复核。amount明确未核验。因子副表与原始快照分别标明验收范围，不混称全部通过。</p><label>股票<select id="stock"><option value="all">全部四股</option>'+''.join(f'<option value="{c}">{c}</option>' for c in sorted({e['code'] for e in events}))+'</select></label><label>历史首板<select id="event">'+''.join(options)+'</select></label><p>后续表现与每日更新默认折叠；切换事件时再次折叠。图只画截至该事件D日的K线。D−1路径标签与D收盘突破分别列示，尚不等同定稿的背景形态分类。</p></div>'+''.join(sections)+'<script>'+script+'</script></html>'
(p/'replay-user-v012.html').write_text(page,encoding='utf-8')
assert len(sections)==27 and len(after)==432 and len(changes)==24
assert '<details class="future" open' not in page
print('PASS: 24 schema nulls (8 selected / 16 trace), exact v011 restoration; 27-event user page, 54 future sections default collapsed.')
