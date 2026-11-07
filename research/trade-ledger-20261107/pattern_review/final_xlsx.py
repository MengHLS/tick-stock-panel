import sys
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd, numpy as np
BASE='C:/work/sourcecode/tick-stock-panel/research/trade-ledger-20261107/pattern_review/'
rt=pd.read_csv(BASE+'_rt_tagged.csv',dtype={'code':str})
rt['code']=rt['code'].str.zfill(6)
rt['open_time']=pd.to_datetime(rt['open_time']); rt['close_time']=pd.to_datetime(rt['close_time'])

g=rt.groupby('verdict').agg(笔数=('pnl','size'),合计盈亏=('pnl','sum'),每笔=('pnl','mean'),
   胜率=('pnl',lambda s:round((s>0).mean()*100,1)),平均持有=('hold_td','mean'),占比=('pnl',lambda s:round(s.sum()/rt['pnl'].sum()*100,1))).round(1).reset_index()
g.columns=['判定','笔数','合计盈亏','每笔','胜率%','平均持有(交易日)','占总亏损%']
tot=pd.DataFrame([{'判定':'合计','笔数':len(rt),'合计盈亏':round(rt['pnl'].sum(),2),'每笔':round(rt['pnl'].mean(),1),
  '胜率%':round((rt['pnl']>0).mean()*100,1),'平均持有(交易日)':round(rt['hold_td'].mean(),1),'占总亏损%':100.0}])
g=pd.concat([g,tot],ignore_index=True)

EXP={'P1':1.05,'P2':0.64,'P2低位':1.06,'P3':-2.14,'P4':-0.92,'P6':0.15,'P7':-1.04,'P8':0.68,'P9涨停':-1.04,'P9次新':0.99,'首板打板':1.48,'连板2打板':1.18}
rows=[]
for k,e in EXP.items():
    m=rt['tags'].fillna('').str.contains(k,regex=False)
    s=rt[m]
    if len(s)==0: continue
    rows.append(('模式 '+k if not k.startswith(('首板','连板')) else '打板·'+k, len(s), round(s['pnl'].sum(),2), round(s['pnl'].mean(),1),
                 round((s['pnl']>0).mean()*100,1), round(s['hold_td'].mean(),1), f'{e:+.2f}%'))
m=rt['tags'].fillna('').eq('无模式'); s=rt[m]
rows.append(('无任何模式',len(s),round(s['pnl'].sum(),2),round(s['pnl'].mean(),1),round((s['pnl']>0).mean()*100,1),round(s['hold_td'].mean(),1),'—'))
pat=pd.DataFrame(rows,columns=['模式','涉及笔数','合计盈亏','每笔','胜率%','平均持有','模式历史5日期望']).sort_values('合计盈亏')

nine=pd.DataFrame([
 ('P1 总龙反抽','20日涨≥30% 且当日回调 −8%~−3%',18470,'+1.05%','50.3%','有效 +0.48pp'),
 ('P2 大题材主升','涨5–9.5%未涨停（概念涨停≥8家）',92187,'+0.64%','47.5%','无优势'),
 ('P2 低位版','同上 + 20日涨幅<20%',62284,'+1.06%','49.0%','有效 +0.49pp'),
 ('P3 主升龙头','连板≥3 涨停，次日开盘买',3383,'−2.14%','37.9%','负期望'),
 ('P4 200%虹吸','60日涨≥100%',41541,'−0.92%','47.6%','负期望'),
 ('P5 事件的潜伏','需事件日历',0,'—','—','缺数据源，不可测'),
 ('P6 出监管套利','近20日≥3涨停且当日未涨停',67669,'+0.15%','49.4%','跑输基准'),
 ('P7 20cm首板','创业板/科创首板涨停',4356,'−1.04%','44.6%','负期望'),
 ('P8 温和主升','60日<30%、20日>10%、站上MA20',300093,'+0.68%','47.9%','无优势(+0.11pp)'),
 ('P9 次新涨停','上市<365天 且涨停',16838,'−1.04%','39.4%','负期望'),
 ('P9 次新全部','上市<365天',733990,'+0.99%','50.3%','弱有效'),
 ('打板·首板开板','首板当日开过板，涨停价买、次日开盘卖',12810,'+1.48%','57.1%','唯一正期望可成交买点'),
 ('打板·封死','首板全天未开板（买不到）',21154,'+2.45%','68.2%','看得见吃不到'),
],columns=['编号','规则（可量化）','全市场样本','次日开盘买入·5日期望','胜率','判定'])

rt['yr']=rt['open_time'].dt.year
yr=rt.groupby('yr').agg(笔数=('pnl','size'),盈亏=('pnl','sum'),每笔=('pnl','mean'),胜率=('pnl',lambda s:round((s>0).mean()*100,1))).round(1).reset_index()
yr.columns=['年份','笔数','盈亏','每笔','胜率%']
rt['hd']=pd.cut(rt['hold_td'].fillna(-1),[-2,0,1,3,99],labels=['当日T+0','隔1日','2-3日','4日以上'])
hs=rt.groupby('hd',observed=True).agg(笔数=('pnl','size'),盈亏=('pnl','sum'),每笔=('pnl','mean')).round(1).reset_index()
hs.columns=['持有档','笔数','盈亏','每笔']

D=rt.copy()
D['开仓时间']=D['open_time'].dt.strftime('%Y-%m-%d %H:%M'); D['平仓时间']=D['close_time'].dt.strftime('%Y-%m-%d %H:%M')
D['代码']=D['code']; D['名称']=D['name']
D['买入价']=D['buy_px'].round(3); D['卖出价']=D['sell_px'].round(3); D['股数']=D['qty']
D['成本']=D['cost'].round(2); D['盈亏']=D['pnl'].round(2); D['收益率%']=(D['ret']*100).round(2)
D['持有交易日']=D['hold_td']
D['开仓日涨幅%']=(D['day_pct']*100).round(2)
D['连板']=D['clu']; D['开仓日涨停']=D['is_lu'].map(lambda x:'是' if x is True or x=='True' else '否')
D['按涨停价买']=D['at_limit_px'].map(lambda x:'是' if x is True or x=='True' else '否')
D['匹配模式']=D['tags']; D['判定']=D['verdict']
order=['开仓时间','代码','名称','股数','买入价','平仓时间','卖出价','成本','盈亏','收益率%','持有交易日',
 '开仓日涨幅%','开仓日涨停','连板','按涨停价买','匹配模式','判定']
D=D[order].sort_values('开仓时间')
D.to_csv(BASE+'逐笔交易清单_441.csv',index=False,encoding='utf-8-sig')

info=pd.DataFrame([['数据范围','2025-03-21 ~ 2026-11-06'],['回合数',len(rt)],['合计已实现盈亏（元）',round(rt['pnl'].sum(),2)],
 ['账户净亏损（元）','-75,824.59 (差额为费用/利息/股息)'],['判定口径','按开仓当日收盘可观测状态判定模式；历史期望取自全市场回测（次日开盘买入持5日，基准+0.57%）'],
 ['数据源','交割单 jiaogedan_full_20261107.csv + kline_daily_enriched + limit_board_events']],columns=['项目','内容'])

with pd.ExcelWriter(BASE+'交易模式清单_20261107.xlsx',engine='openpyxl') as w:
    info.to_excel(w,sheet_name='说明',index=False)
    g.to_excel(w,sheet_name='按判定汇总',index=False)
    pat.to_excel(w,sheet_name='按模式汇总',index=False)
    nine.to_excel(w,sheet_name='九条模式判定',index=False)
    yr.to_excel(w,sheet_name='分年份',index=False)
    hs.to_excel(w,sheet_name='分持有天数',index=False)
    D.to_excel(w,sheet_name='逐笔交易清单',index=False)
print(g.to_string()); print(pat.to_string())
