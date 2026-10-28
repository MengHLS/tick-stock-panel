import csv,json,html,hashlib
from pathlib import Path
p=Path(__file__).parent
rows=list(csv.DictReader((p/'three-case-paths.csv').open(encoding='utf-8')))
results=json.loads((p/'three-case-results.json').read_text(encoding='utf-8'))
manifest=json.loads((p/'three-case-manifest.json').read_text(encoding='utf-8'))
assert hashlib.sha256((p/'three-case-paths.csv').read_bytes()).hexdigest()==manifest['path_csv_sha256']
colors=['#2563eb','#a855f7']
parts=[]
for report in results:
 code=report['code']; anchor=report['legacy_selected_anchor']; rs=[r for r in rows if r['symbol']==code and r['date']>=anchor]; n=len(rs)
 W=1200;H=350;left=50;right=1110;top=22;bottom=260
 lo=min(float(r['low']) for r in rs);hi=max(float(r['high']) for r in rs);pad=(hi-lo)*.1;lo-=pad;hi+=pad
 def y(v):return bottom-(float(v)-lo)/(hi-lo)*(bottom-top)
 def x(i):return left+(right-left)*(i+.5)/n
 def ix(d):return next(i for i,r in enumerate(rs) if r['date']==d)
 s=[f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{code}完整日K线">']
 for k in range(5):
  val=lo+(hi-lo)*k/4; yy=y(val);s.append(f'<line x1="{left}" x2="{right}" y1="{yy}" y2="{yy}" stroke="#e2e8f0"/><text x="3" y="{yy+4}">{val:.2f}</text>')
 width=max(1,min(14,(right-left)/n*.65))
 for i,r in enumerate(rs):
  o,h,l,c=[float(r[k]) for k in ['open','high','low','close']];co='#dc2626' if c>=o else '#059669';xx=x(i)
  s.append(f'<g><title>{r["date"]} 开{o:.4f} 高{h:.4f} 低{l:.4f} 收{c:.4f}</title><line x1="{xx}" x2="{xx}" y1="{y(h)}" y2="{y(l)}" stroke="{co}"/><rect x="{xx-width/2}" y="{min(y(o),y(c))}" width="{width}" height="{max(1,abs(y(o)-y(c)))}" fill="{co}"/></g>')
 for i in sorted(set([0,n-1]+list(range(0,n,max(1,n//6))))):s.append(f'<text x="{x(i)}" y="280" text-anchor="middle">{rs[i]["date"]}</text>')
 versions=report['traces'][0]['versions']; legends=[]
 for j,v in enumerate(versions):
  co=colors[j]; name='A 排除下降日高价' if j==0 else 'B 包含下降日高价'; yy=y(v['P']);start=x(ix(v['P_known_at']))
  s.append(f'<line x1="{start}" x2="{right}" y1="{yy}" y2="{yy}" stroke="{co}" stroke-width="1.7" stroke-dasharray="7 4"/>')
  known=ix(v['P_known_at']);s.append(f'<line x1="{x(known)}" x2="{x(known)}" y1="{top}" y2="{bottom}" stroke="{co}" opacity=".5" stroke-dasharray="2 4"/>')
  legends.append(f'{name}：P={v["P"]:.2f}，峰值日{v["P_date"]}，可知日{v["P_known_at"]}')
 v=versions[1]
 for label,date,val,co in [('L_setup',v['L_setup_date'],v['L_setup'],'#0f766e'),('首次收盘突破',v['first_break_date'],None,'#b45309'),('L_after',v['L_after_date'],v['L_after'],'#64748b')]:
  if date and date>=anchor:
   k=ix(date);yy=y(val if val is not None else rs[k]['close']);s.append(f'<circle cx="{x(k)}" cy="{yy}" r="5" fill="{co}"/><title>{label} {date}</title>');legends.append(f'{label}：{date}'+(f' / {val:.2f}' if val is not None else ''))
 pw=v['P_window'];s.append(f'<line x1="{left}" x2="{right}" y1="{y(pw)}" y2="{y(pw)}" stroke="#94a3b8" stroke-dasharray="3 6"/>');legends.append(f'P_window={pw:.2f}（{v["P_window_date"]}），仅作位置参照，不回填历史突破')
 ct=float(rs[-1]['close']);s.append(f'<text x="{right+5}" y="{y(ct)+4}" fill="#0f172a">T {ct:.2f}</text>');s.append('</svg>')
 caption={'002687.SZ':'首次突破：A/B改变P数值和峰值日期，本例首次突破标签不变。T−1已离开低点。','002241.SZ':'曾突破后跌回：L_setup=30.30与突破后19.50分开；全窗最高40.68不能抹去此前对37.17的突破。','002945.SZ':'递归对照：主图采用旧锚点07-29。最近锚点10-15的P=15.39恰等于当日high；是否要求新峰值，会改变其结构资格。'}[code]
 parts.append(f'<section><h2>{code} · {anchor} → {rs[-1]["date"]} · {n}根日K</h2><p>{caption}</p>'+''.join(s)+'<div class="facts">'+'<br>'.join(legends)+f'<br>T−1：{v["T_minus_1"]} 收{v["C_T_minus_1"]:.2f}；T收{ct:.2f}。</div></section>')
style='body{font:15px system-ui;color:#172033;background:#f8fafc;margin:24px auto;max-width:1250px;padding:0 16px}h1{font-size:25px}h2{font-size:18px;margin:0}section,.intro{background:white;border:1px solid #dbe2ea;border-radius:10px;margin:16px 0;padding:16px}svg{width:100%;display:block}svg text{font:11px system-ui}.facts{font-size:13px;columns:2;line-height:1.7}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #dbe2ea;padding:9px;text-align:left} @media print{body{margin:0;max-width:none;font-size:11px}section{break-inside:avoid;margin:5px 0;padding:8px}svg{max-height:230px}.facts{font-size:10px}h1{font-size:18px}}'
intro='''<h1>首板形态：三例完整日K线与规则对照</h1><div class="intro">指定锚点计算已通过独立复核；完整递归与首板身份尚未认证。红涨绿跌，横轴按实际存在的行情行排列；逐根悬停可查看OHLC。主图展示从各自锚点到目标日的全部已有日K，不隐藏中间行情。P水平线从可知日开始，峰值日与可知日分别列明。缺行/停牌未按官方日历认证，图上等距不代表连续自然日。<br>价格：固定面板前复权快照，上界2026-10-27；三例窗口内close与raw_close相等，不能用于验证除权处理。</div>'''
summary='''<section><h2>请判断这三项建议是否符合你想表达的形态</h2><table><tr><th>建议</th><th>改变什么</th><th>本页反例</th></tr><tr><td>P包含首次下降收盘日的最高价</td><td>保留当天实际高点，可能改变突破门槛与日期</td><td>002687：6.57→6.62；本例标签不变</td></tr><tr><td>是否超过锚点高点单列特征</td><td>峰值等于锚点高点时，仍描述回调，不默认淘汰；若坚持严格条件则该结构不合格</td><td>002945最近10-15：P=锚点high=15.39</td></tr><tr><td>最近首板与递归历史结构并列展示</td><td>避免历史突破标签覆盖最近首板的状态；递归资格和停止政策仍须另定</td><td>002945最近10-15与旧选中07-29同时保留</td></tr></table><p>已收敛：历史突破对当时可知、冻结的P_episode判断；P_window只作位置参照。尚待定：有效回攻门槛、3%/5%、窗口与递归政策。当前没有类别收益结论。</p></section>'''
(p/'three-case-kline-comparison.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>首板三例K线规则对照</title><style>'+style+'</style>'+intro+''.join(parts)+summary+'</html>',encoding='utf-8')
assert len(parts)==3
print('PASS: source hash checked; 3 full anchor-to-target candlestick panels generated, including known-at dates and rule comparison.')
