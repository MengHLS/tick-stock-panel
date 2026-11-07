import sys, re
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd, numpy as np

BASE='C:/work/sourcecode/tick-stock-panel/research/trade-ledger-20261107/pattern_review/'
bars=pd.read_parquet(BASE+'bars_feat.parquet')
bars['date']=pd.to_datetime(bars['date'])
inst=pd.read_parquet('D:/TSP/data/instruments/instruments.parquet')
inst['listing_date']=pd.to_datetime(inst['listing_date'],errors='coerce')
inst['code']=inst['code'].astype(str).str.zfill(6)
instm=inst.drop_duplicates('code').set_index('code')

raw=pd.read_csv('D:/TSP/data/user_data/trade_ledger/inbox/jiaogedan_full_20261107.csv',encoding='gbk',dtype=str)
raw.columns=[c.strip() for c in raw.columns]
raw['code']=raw['证券代码'].str.extract(r'(\d{6})')[0]
raw['name']=raw['证券名称'].str.strip()
raw['date']=pd.to_datetime(raw['发生日期'],errors='coerce')
raw['time']=raw['发生时间'].str.strip()
for c in ['成交数量','成交均价','成交金额','发生金额','佣金','其他费用','印花税','过户费']:
    raw[c]=pd.to_numeric(raw[c],errors='coerce')
raw=raw[raw['code'].notna()]

buys=raw[raw['交易类别'].str.contains('买入')].copy()
buys=buys.rename(columns={'成交均价':'px','成交数量':'qty','成交金额':'amt'})
buys=buys[['date','time','code','name','px','qty','amt','佣金','其他费用','印花税','过户费']].reset_index(drop=True)

# prev close for limit price
prevmap=bars.set_index(['code','date'])['raw_close']
def prev_close(code,d):
    sub=bars[(bars.code==code)&(bars.date<d)]
    return sub['raw_close'].iloc[-1] if len(sub) else np.nan

rows=[]
for i,r in buys.iterrows():
    d=r['date']; c=r['code']
    b=bars[(bars.code==c)&(bars.date==d)]
    if len(b)==0:
        rows.append(dict(idx=i,found=False)); continue
    b=b.iloc[0]
    pc=prev_close(c,d)
    if c[:3] in ('300','688'): lp=0.20
    elif c[:2] in ('30','68'): lp=0.20
    elif c[0] in ('4','8'): lp=0.30
    else: lp=0.10
    limit_px=round(pc*(1+lp),2) if pd.notna(pc) else np.nan
    rows.append(dict(idx=i,found=True,pct=b['pct'],ret20=b['ret20'],ret60=b['ret60'],
        close=b['close'],ma20=b['ma20'],clu=b['consecutive_limit_ups'],lu20=b['lu20'],lu60=b['lu60'],
        limit_px=limit_px,pc=pc,high=b['high'],low=b['low'],open=b['open']))
feat=pd.DataFrame(rows).set_index('idx')
buys=buys.join(feat)

def is_gem(c): return c[:3] in ('300','301','688','689')
buys['gem']=buys['code'].map(is_gem)
def listdd(c):
    try:
        v=instm.loc[c,'listing_date']
        return v if pd.notna(v) else pd.NaT
    except Exception: return pd.NaT
buys['listing_date']=buys['code'].map(listdd)
buys['listed_days']=(buys['date']-buys['listing_date']).dt.days

buys['day_pct']=buys['pct']
buys['is_lu']=buys['clu'].fillna(0)>0
buys['at_limit_px']=(buys['px']>=buys['limit_px']*0.995)
buys['at_limit_px']=buys['at_limit_px']&buys['limit_px'].notna()

# ---- pattern tags ----
tags=[]
for _,r in buys.iterrows():
    t=[]
    lu=r['is_lu']; p=r['day_pct']; r20=r['ret20']; r60=r['ret60']
    clu=r['clu'] if pd.notna(r['clu']) else 0
    if pd.notna(r20) and pd.notna(p) and r20>=0.30 and -0.08<=p<=-0.03: t.append('P1')
    if pd.notna(p) and not lu and 0.05<=p<=0.095:
        t.append('P2低位' if (pd.notna(r20) and r20<0.20) else 'P2')
    if lu and clu>=3: t.append('P3')
    if lu and clu==1 and r['gem']: t.append('P7')
    if pd.notna(r60) and r60>=1.00: t.append('P4')
    if pd.notna(r['lu20']) and r['lu20']>=3 and not lu: t.append('P6')
    if pd.notna(r60) and pd.notna(r20) and pd.notna(r['ma20']) and r60<0.30 and r20>0.10 and r['close']>r['ma20']: t.append('P8')
    if pd.notna(r['listed_days']) and r['listed_days']<365:
        t.append('P9涨停' if lu else 'P9次新')
    if lu and clu==1 and not r['gem']: t.append('首板打板')
    if lu and clu>=2 and not t.count('P3'): t.append(f'连板{int(clu)}打板')
    tags.append(t)
buys['tags']=['/'.join(x) if x else '无模式' for x in tags]

EXP={'P1':'+1.05%(n=18470)','P2':'+0.64%(n=92187)','P2低位':'+1.06%(n=62284)','P3':'-2.14%(n=3383)',
 'P4':'-0.92%(n=41541)','P6':'+0.15%(n=67669)','P7':'-1.04%(n=4356)','P8':'+0.68%(n=300093)',
 'P9涨停':'-1.04%(n=16838)','P9次新':'+0.99%(n=733990)','首板打板':'+1.48%(n=12810,胜率57.1%)'}

def verdict(r):
    tg=r['tags']
    if '首板打板' in tg and r['at_limit_px']: return 'A 唯一正期望：首板打板(涨停价买)'
    if '首板打板' in tg: return 'A- 首板涨停但未在涨停价买'
    if 'P1' in tg or 'P2低位' in tg: return 'B 弱有效(扣成本≈0)'
    if tg=='无模式': return 'E 计划外·不匹配任何模式'
    if any(k in tg for k in ['P3','P4','P7','P9涨停']): return 'D 负期望模式'
    return 'C 跑输基准/无优势'
buys['verdict']=buys.apply(verdict,axis=1)
buys['exp_ref']=buys['tags'].map(lambda s: ' | '.join(f'{k}:{EXP[k]}' for k in s.split('/') if k in EXP) or '无历史期望')

# ---- roundtrips ----
rt=pd.read_csv('C:/work/sourcecode/tick-stock-panel/research/trade-ledger-20261107/out/roundtrips.csv',dtype={'code':str})
rt['code']=rt['code'].str.zfill(6)
rt['open_time']=pd.to_datetime(rt['open_time'])
rt['close_time']=pd.to_datetime(rt['close_time'])
rt['open_date']=rt['open_time'].dt.normalize()
agg=rt.groupby(['code','open_date']).agg(open_time=('open_time','min'),close_time=('close_time','max'),
    qty=('qty','sum'),cost=('cost','sum'),pnl=('pnl','sum'),hold_td=('hold_td','max'),rt_n=('pnl','size')).reset_index()
buys['date']=pd.to_datetime(buys['date'])
buys=buys.merge(agg,left_on=['code','date'],right_on=['code','open_date'],how='left',suffixes=('','_rt'))
buys['ret']=buys['pnl']/buys['cost']

# names
buys['name']=buys['name'].where(buys['name'].str.len()>0)
buys['name']=buys['name'].fillna(buys['code'])
buys.to_pickle(BASE+'buys_tagged.pkl')
rt.to_pickle(BASE+'rt.pkl')

print('buys',len(buys),'matched rt',buys['pnl'].notna().sum(),flush=True)
print(buys['verdict'].value_counts().to_string(),flush=True)
g=buys.groupby('verdict').agg(n=('code','size'),pnl=('pnl','sum'),per=('pnl','mean'),win=('pnl',lambda s:(s>0).mean()),hold=('hold_td','mean'))
print(g.round(2).to_string(),flush=True)
print('--- tags ---',flush=True)
print(buys['tags'].value_counts().head(25).to_string(),flush=True)
