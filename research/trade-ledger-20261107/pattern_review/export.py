import sys
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd, numpy as np
BASE='C:/work/sourcecode/tick-stock-panel/research/trade-ledger-20261107/pattern_review/'
b=pd.read_csv(BASE+'_buys.csv',dtype={'code':str}); rt=pd.read_csv(BASE+'_rt.csv',dtype={'code':str})
b['date']=pd.to_datetime(b['date']); b['open_time']=pd.to_datetime(b['open_time']); b['close_time']=pd.to_datetime(b['close_time'])

def yn(x): return '是' if x else '否'
U=b.copy()
U['买入日期']=U['date'].dt.strftime('%Y-%m-%d'); U['买入时间']=U['time']
U['代码']=U['code']; U['名称']=U['name']; U['买入价']=U['px'].round(3)
U['股数']=U['qty'].astype('Int64'); U['金额']=U['amt'].round(0)
U['当日涨幅%']=(U['day_pct']*100).round(2)
U['连板']=U['clu'].astype('Int64')
U['20日涨幅%']=(U['ret20']*100).round(1); U['60日涨幅%']=(U['ret60']*100).round(1)
U['是否涨停']=U['is_lu'].map(yn)
U['涨停价']=U['limit_px']
U['按涨停价买']=U['at_limit_px'].map(yn)
U['匹配模式']=U['tags']; U['历史期望']=U['exp_ref']; U['判定']=U['verdict']
U['卖出日期']=pd.to_datetime(U['close_time']).dt.strftime('%Y-%m-%d')
U['持有交易日']=U['hold_td']; U['盈亏']=U['pnl'].round(2); U['收益率%']=(U['ret']*100).round(2)
cols=['买入日期','买入时间','代码','名称','买入价','股数','金额','当日涨幅%','是否涨停','连板','按涨停价买','20日涨幅%','60日涨幅%','匹配模式','判定','历史期望','卖出日期','持有交易日','盈亏','收益率%']
U=U[cols].sort_values(['买入日期','买入时间'])
U.to_csv(BASE+'逐笔买入清单.csv',index=False,encoding='utf-8-sig')

# summary by verdict
g=U.groupby('判定').agg(笔数=('盈亏','size'),合计盈亏=('盈亏','sum'),每笔=('盈亏','mean'),
    胜率=('盈亏',lambda s: round((s>0).mean()*100,1)),平均持有=('持有交易日','mean')).round(1).reset_index()
g.loc[len(g)]=['合计',g['笔数'].sum(),round(g['合计盈亏'].sum(),2),round(U['盈亏'].sum()/U['盈亏'].notna().sum(),1),round((U['盈亏']>0).mean()*100,1),round(U['持有交易日'].mean(),1)]

# by pattern single tag
rows=[]
EXP={'P1':1.05,'P2':0.64,'P2低位':1.06,'P3':-2.14,'P4':-0.92,'P6':0.15,'P7':-1.04,'P8':0.68,'P9涨停':-1.04,'P9次新':0.99,'首板打板':1.48}
for k,e in EXP.items():
    m=U['匹配模式'].str.contains(k,regex=False)
    s=U[m]
    if len(s)==0: continue
    rows.append(dict(模式=k,涉及笔数=len(s),合计盈亏=round(s['盈亏'].sum(),2),每笔=round(s['盈亏'].mean(),1),
        胜率=round((s['盈亏']>0).mean()*100,1),平均持有=round(s['持有交易日'].mean(),1),历史期望=f'{e:+.2f}%'))
pat=pd.DataFrame(rows).sort_values('合计盈亏')

# 9 patterns
nine=pd.DataFrame([
 dict(编号='P1 总龙反抽',规则='20日涨≥30% 且当日回调 −8%~−3%',样本=18470,期望5日='+1.05%',胜率='50.3%',基准='+0.57%',判定='有效 +0.48pp'),
 dict(编号='P2 大题材主升',规则='涨5–9.5%未涨停（概念涨停≥8家）',样本=92187,期望5日='+0.64%',胜率='47.5%',基准='+0.57%',判定='无优势'),
 dict(编号='P2 低位版',规则='同上 + 20日涨幅<20%',样本=62284,期望5日='+1.06%',胜率='49.0%',基准='+0.57%',判定='有效 +0.49pp'),
 dict(编号='P3 主升龙头',规则='连板≥3 涨停，次日开盘买',样本=3383,期望5日='−2.14%',胜率='37.9%',基准='+0.57%',判定='负期望'),
 dict(编号='P4 200%虹吸',规则='60日涨≥100%',样本=41541,期望5日='−0.92%',胜率='47.6%',基准='+0.57%',判定='负期望'),
 dict(编号='P5 事件的潜伏',规则='需事件日历',样本=0,期望5日='—',胜率='—',基准='—',判定='缺数据源，不可测'),
 dict(编号='P6 出监管套利',规则='近20日≥3涨停且当日未涨停',样本=67669,期望5日='+0.15%',胜率='49.4%',基准='+0.57%',判定='跑输基准'),
 dict(编号='P7 20cm首板',规则='创业板/科创首板涨停',样本=4356,期望5日='−1.04%',胜率='44.6%',基准='+0.57%',判定='负期望'),
 dict(编号='P8 温和主升',规则='60日<30%、20日>10%、站上MA20',样本=300093,期望5日='+0.68%',胜率='47.9%',基准='+0.57%',判定='无优势(+0.11pp)'),
 dict(编号='P9 次新涨停',规则='上市<365天 且涨停',样本=16838,期望5日='−1.04%',胜率='39.4%',基准='+0.57%',判定='负期望'),
 dict(编号='P9 次新全部',规则='上市<365天',样本=733990,期望5日='+0.99%',胜率='50.3%',基准='+0.57%',判定='弱有效'),
 dict(编号='打板·首板开板',规则='首板当日开过板，涨停价买、次日开盘卖',样本=12810,期望5日='+1.48%',胜率='57.1%',基准='—',判定='唯一正期望可成交买点'),
 dict(编号='打板·封死',规则='首板全天未开板（买不到）',样本=21154,期望5日='+2.45%',胜率='68.2%',基准='—',判定='看得见吃不到'),
])

# year / hold splits
b['yr']=pd.to_datetime(b['date']).dt.year
yr=b.groupby('yr').agg(笔数=('pnl','size'),盈亏=('pnl','sum'),胜率=('pnl',lambda s:round((s>0).mean()*100,1))).round(1).reset_index()
yr.columns=['年份','笔数','盈亏','胜率%']
hd=b.copy()
hd['持有档']=np.where(hd['hold_td'].fillna(0)<=0,'当日(T+0)',np.where(hd['hold_td']<=1,'隔1日',np.where(hd['hold_td']<=3,'2-3日','4日以上')))
hs=hd.groupby('持有档').agg(笔数=('pnl','size'),盈亏=('pnl','sum'),每笔=('pnl','mean')).round(1).reset_index()

rtU=rt.copy(); rtU['open_time']=pd.to_datetime(rtU['open_time']); rtU['close_time']=pd.to_datetime(rtU['close_time'])
rtU['代码']=rtU['code']; rtU['名称']=rtU['name']; rtU['买入时间']=rtU['open_time'].dt.strftime('%Y-%m-%d %H:%M:%S')
rtU['卖出时间']=rtU['close_time'].dt.strftime('%Y-%m-%d %H:%M:%S')
rtU['股数']=rtU['qty']; rtU['买入价']=rtU['buy_px'].round(3); rtU['卖出价']=rtU['sell_px'].round(3)
rtU['成本']=rtU['cost'].round(2); rtU['盈亏']=rtU['pnl'].round(2); rtU['收益率%']=(rtU['ret']*100).round(2); rtU['持有交易日']=rtU['hold_td']
RT=rtU[['买入时间','代码','名称','股数','买入价','卖出时间','卖出价','成本','盈亏','收益率%','持有交易日']].sort_values('买入时间')
RT.to_csv(BASE+'回合清单.csv',index=False,encoding='utf-8-sig')

with pd.ExcelWriter(BASE+'交易模式清单_20261107.xlsx',engine='openpyxl') as w:
    pd.DataFrame({'项目':['数据范围','买入笔数','回合数','合计盈亏','说明'],
      '值':['2025-03-21 ~ 2026-11-06',len(U),len(RT),round(U['盈亏'].sum(),2),
            '买入按交割单原始成交价与时间；模式按买入当日收盘可观测的状态判定；历史期望为全市场回测（次日开盘买入持5日，基准+0.57%）']}).to_excel(w,sheet_name='说明',index=False)
    g.to_excel(w,sheet_name='按判定汇总',index=False)
    pat.to_excel(w,sheet_name='按模式汇总',index=False)
    nine.to_excel(w,sheet_name='九条模式判定',index=False)
    yr.to_excel(w,sheet_name='分年份',index=False)
    hs.to_excel(w,sheet_name='分持有天数',index=False)
    U.to_excel(w,sheet_name='逐笔买入清单',index=False)
    RT.to_excel(w,sheet_name='回合清单',index=False)
print('ok',len(U),len(RT))
print(g.to_string()); print(pat.to_string()); print(yr.to_string()); print(hs.to_string())
print('TOTAL',U['盈亏'].sum().round(2))
