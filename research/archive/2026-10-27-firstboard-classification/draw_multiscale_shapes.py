import csv,json,html,hashlib
from pathlib import Path
p=Path(__file__).parent; rows=list(csv.DictReader((p/'shape-selection-paths.csv').open(encoding='utf-8')));ms={x['code']:x for x in json.loads((p/'shape-selection-metrics.json').read_text(encoding='utf-8'))}
source=Path('C:/work/sourcecode/stock-limit-up-analyzer/docs/research/FIRSTBOARD-20261023-RECURSIVE-2019-V1-20261026/target-chain-summary.csv');olds={x['stockCode']:x for x in csv.DictReader(source.open(encoding='utf-8-sig'))}
choices=[('000810.SZ','下跌后的低位整理候选','长周期此前下跌，近期位于较低价格区间；只能称低位整理，尚不能证明底部完成，也不据不同长度窗口推断波动收窄。'),('002687.SZ','上涨后的偏高位震荡','前期上涨后近期推进停滞；即使局部前高被突破，背景仍可能是偏高位震荡。'),('600785.SH','长期下跌后的阶段反弹','120日方向仍向下，但近60日明显反弹；短线向上不自动等于长期上涨趋势。'),('002354.SZ','阶段上涨后的回撤候选','60/120日仍上涨、20日回撤；也可能逐步转为震荡，不能先认定回调结束。')]
art=[];evidence=[];board_lists=[]
flags=list(csv.DictReader((p/'platform-firstboard-flags.csv').open(encoding='utf-8')))
board_dates={code:{r['date'] for r in flags if r['symbol']==code and r['consecutive_limit_ups']=='1'} for code,_,_ in choices}
for code,label,desc in choices:
 rr=[x for x in rows if x['symbol']==code];o=olds[code];m=ms[code];a=o['nearestEligiblePrior'];hist=[x for x in rr if a<=x['date']<'2026-10-23'];P=None;pd=None;known=None;ld=None;lv=None;br=None
 decline=next((i for i in range(1,len(hist)) if float(hist[i]['close'])<float(hist[i-1]['close'])),None)
 if decline is not None:
  peak=max(hist[:decline+1],key=lambda x:float(x['high']));P=float(peak['high']);pd=peak['date'];known=hist[decline]['date']
  br=next((x['date'] for x in rr if x['date']>=known and float(x['close'])>P),None)
  setup=[x for x in hist if x['date']>pd and (br is None or x['date']<br)]
  if setup:l=min(setup,key=lambda x:float(x['low']));ld=l['date'];lv=float(l['low'])
 def chart(rs,title):
  W=730;H=310;L=46;R=686;U=25;B=260;n=len(rs);lo=min(float(r['low']) for r in rs);hi=max(float(r['high']) for r in rs);margin=(hi-lo)*.07;lo-=margin;hi+=margin
  def y(v):return B-(float(v)-lo)/(hi-lo)*(B-U)
  def x(i):return L+(R-L)*(i+.5)/n
  out=[f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{code} {title}"><text x="46" y="15">{title} · {rs[0]["date"]}至{rs[-1]["date"]}</text>']
  for k in range(5):
   v=lo+(hi-lo)*k/4;yy=y(v);out.append(f'<line x1="{L}" x2="{R}" y1="{yy}" y2="{yy}" stroke="#e2e8f0"/><text x="1" y="{yy+4}">{v:.2f}</text>')
  width=max(1,min(7,(R-L)/n*.65))
  for i,r in enumerate(rs):
   op,h,l,c=[float(r[k]) for k in ['open','high','low','close']];co='#dc2626' if c>=op else '#059669';xx=x(i)
   out.append(f'<g><title>{r["date"]} 开{op:.3f} 高{h:.3f} 低{l:.3f} 收{c:.3f}</title><line x1="{xx}" x2="{xx}" y1="{y(h)}" y2="{y(l)}" stroke="{co}"/><rect x="{xx-width/2}" y="{min(y(op),y(c))}" width="{width}" height="{max(1,abs(y(op)-y(c)))}" fill="{co}"/></g>')
   if r['date'] in board_dates[code] or r['date']==a:
    is_target=r['date']=='2026-10-23';is_anchor=r['date']==a
    label='目标首板' if is_target else '局部所用锚点' if is_anchor else '历史首板'
    color='#dc2626' if is_target else '#7c3aed' if is_anchor else '#2563eb';my=min(B-8,y(l)+11)
    out.append(f'<g class="board-marker" data-code="{code}" data-date="{r["date"]}" data-kind="{label}"><title>{label} {r["date"]}；平台首板标记={r["date"] in board_dates[code]}；身份未认证</title>')
    if is_target:out.append(f'<rect x="{xx-4}" y="{my-4}" width="8" height="8" fill="{color}"/>')
    elif is_anchor:out.append(f'<path d="M {xx} {my-5} L {xx+5} {my} L {xx} {my+5} L {xx-5} {my} Z" fill="{color}"/>')
    else:out.append(f'<path d="M {xx} {my-4} L {xx+4} {my+4} L {xx-4} {my+4} Z" fill="{color}"/>')
    out.append('</g>')
   
  for i in [0,n//3,n*2//3,n-1]:out.append(f'<text x="{x(i)}" y="281" text-anchor="middle">{rs[i]["date"]}</text>')
  out.append('<g class="annotations">')
  for name,date,val,color in [('最近首板',a,None,'#7c3aed'),('P',pd,P,'#2563eb'),('P可知',known,None,'#2563eb'),('L_setup',ld,lv,'#0f766e'),('首次突破',br,None,'#d97706'),('目标首板','2026-10-23',None,'#111827')]:
   if date and rs[0]['date']<=date<=rs[-1]['date']:
    ix=next((i for i,r in enumerate(rs) if r['date']==date),None)
    if ix is not None:
     xx=x(ix);out.append(f'<line x1="{xx}" x2="{xx}" y1="{U}" y2="{B}" stroke="{color}" stroke-dasharray="3 4"/><text transform="translate({xx-2},{U+6}) rotate(90)" fill="{color}">{name} {date}</text>')
     if val is not None:out.append(f'<circle cx="{xx}" cy="{y(val)}" r="4" fill="{color}"/>')
  if P and lo<=P<=hi:out.append(f'<line x1="{L}" x2="{R}" y1="{y(P)}" y2="{y(P)}" stroke="#2563eb" stroke-dasharray="6 4"/><text x="{R+2}" y="{y(P)}">P</text>')
  out.append('</g></svg>');return ''.join(out)
 annotation={'code':code,'label_for_discussion':label,'anchor_external':a,'P':P,'P_date':pd,'P_known_at':known,'L_setup':lv,'L_setup_date':ld,'first_break':br,'rule':'包含首次下降日high；以最近旧首板为外部给定锚点，不强制P超过锚点high','status':'新增局部标注未独立复核；非旧递归结构认证','metrics_asof':'2026-10-22'};evidence.append(annotation)
 f=lambda v:f'{v*100:+.1f}%'
 facts=f'截至10-22：20日 {f(m["r20"])}｜60日 {f(m["r60"])}｜120日 {f(m["r120"])}｜250日高低价区间位置 {m["pos250"]*100:.1f}%'
 before=[r for r in rr if r['date']<'2026-10-23']; C=float(before[-1]['close']); amps=[]
 for n in [20,60,120,250]:
  window=before[-n:]; high=max(float(r['high']) for r in window); low=min(float(r['low']) for r in window)
  amps.append({'window':n,'start':window[0]['date'],'end':window[-1]['date'],'high':high,'low':low,'range_over_current_close':(high-low)/C,'selection_width_over_low':high/low-1})
 annotation['range_metrics']=amps
 facts+='<br>250日高低价区间位置 = (截至日收盘价 − 250日最低low) ÷ (250日最高high − 250日最低low) × 100%；若分母为0则为空。'
 facts+='<br>全区间振幅（与验证员口径一致） = (窗口最高high − 窗口最低low) ÷ 截至日收盘价 × 100%。'
 facts+='<br>原选样区间宽度 = (窗口最高high ÷ 窗口最低low − 1) × 100%；与上述振幅分母不同，分别列示。'
 facts+='<table><tr><th>窗口</th><th>起止（截止T−1）</th><th>全区间振幅 / C</th><th>区间宽度 / 最低价</th></tr>'+''.join(f'<tr><td>{a["window"]}根日K</td><td>{a["start"]} 至 {a["end"]}</td><td>{a["range_over_current_close"]*100:.2f}%</td><td>{a["selection_width_over_low"]*100:.2f}%</td></tr>' for a in amps)+'</table>'
 facts+='<br>以上是全窗口价格跨度，非日收益波动率、非日内振幅均值。长窗口包含短窗口，不能仅凭60日小于120日断言波动正在收窄。'
 local='未找到可定义局部结构' if P is None else f'最近旧首板 {a}；局部P {P:.3f}（峰值日{pd}，可知日{known}）；突破前L '+('未形成' if lv is None else f'{lv:.3f}@{ld}')+f'；截至目标日首次突破 {br or "未出现"}'
 for window_n,window_label in [(251,'长图'),(61,'近图')]:
  window=rr[-window_n:];dates=sorted(d for d in board_dates[code] if window[0]['date']<=d<=window[-1]['date']);prior=[d for d in dates if d<'2026-10-23']
  board_lists.append({'code':code,'window':window_label,'start':window[0]['date'],'end':window[-1]['date'],'count_including_target':len(dates),'historical_count':len(prior),'dates':dates,'anchor':a,'anchor_in_platform_dates':a in dates})
  facts+=f'<br><b>{window_label}平台口径首板：共{len(dates)}次（历史{len(prior)}次，目标{int("2026-10-23" in dates)}次）</b>：'+('、'.join(dates) or '无')
 facts+='<br>两个窗口重叠，同一首板会同时出现在两图和两份清单，数量不可相加。紫色锚点为当前局部P/L使用的最近旧首板，不等于已认证递归锚点。'
 art.append(f'<section><h2>{code} {html.escape(o["stockName"])} · {label}</h2><p>{desc}</p><p class="facts">{facts}</p><div class="pair">{chart(rr[-251:],"长背景：250交易日＋目标日")}{chart(rr[-61:],"近期：60交易日＋目标日")}</div><p class="annotations">{local}。标注为候选规则计算，不是正式形态分类。</p></section>')
(p/'multi-scale-shape-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>先看背景，再看首板：四例多周期K线</title><style>body{font:15px system-ui;color:#172033;background:#f8fafc;max-width:1550px;margin:24px auto;padding:0 16px}h1{font-size:26px}h2{font-size:19px}section,.note{background:white;border:1px solid #dbe2ea;border-radius:10px;padding:18px;margin:18px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}svg{width:100%}svg text{font:10px system-ui}.facts{color:#475569}.annotations{display:none}body.overlay .annotations{display:revert}label{display:inline-block;border:1px solid #94a3b8;padding:10px;border-radius:7px;cursor:pointer}@media(max-width:950px){.pair{grid-template-columns:1fr}}@media print{.pair{grid-template-columns:1fr 1fr}section{break-inside:avoid}label{display:none}}</style><h1>先看长期背景与近期方向，再看首板起了什么作用</h1><div class="note">全部截止同一目标日 <b>2026-10-23</b>；不使用目标日之后行情。首板前数字截至10-22。左图长背景、右图近期，两图价格轴各自适配，不能靠视觉斜率直接比较涨幅。红涨绿跌，悬停查看逐日OHLC。<br><b>这些是供讨论的形态候选，不是已经定稿的四类。</b>低位不等于已见底；短线反弹不等于长期反转；回撤也可能演变成震荡。首板身份仍未按历史制度认证。<p><label><input type="checkbox" onchange="document.body.classList.toggle('overlay',this.checked)">叠加最近旧首板、局部P/L、P可知日和首次突破</label></p>默认显示窗口内全部平台口径首板：蓝色三角=历史首板，红色方块=当前目标首板，紫色菱形=局部所用锚点（同时属于历史首板时优先用紫色），悬停显示日期。首板口径为consecutive_limit_ups=1，历史制度身份尚未认证。局部P/L仍单独开关，P线延伸仅作水平参照，P在可知日前不可用于信号。</div>'''+''.join(art)+'''<div class="note"><b>本次选样如何理解</b><p>002687保留为“局部突破与偏高位震荡同时成立”的讨论例；另三例分别对照低位整理、长期下跌后的反弹、阶段上涨后的回撤。样本从旧53个目标候选中按目标日前位置、阶段涨幅和振幅挑选；属于刻意选取的讨论图例，不代表类别覆盖或预测效果。未将不清晰的走势强称典型底部或趋势回调。</p><p>原三例仍只承担计算规则核对。本页将长期位置、近期方向、首板事件分层表达，允许震荡或暂不明确。相邻K线按已存在行情行排列，未认证停牌/缺行；价格为本次读取的前复权快照，不能与其他快照绝对价格直接混用。</p></div></html>'''
(p/'platform-firstboard-date-lists.json').write_text(json.dumps(board_lists,ensure_ascii=False,indent=2),encoding='utf-8')
(p/'multi-scale-shape-comparison.html').write_text(page,encoding='utf-8')
assert len(art)==4 and all(x['date']<='2026-10-23' for x in rows)
print('PASS: 4 dual-window charts; all rows <= target; background metrics exclude target; optional overlays saved.')
