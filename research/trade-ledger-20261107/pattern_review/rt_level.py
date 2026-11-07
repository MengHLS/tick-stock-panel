
import sys
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd, numpy as np
BASE='C:/work/sourcecode/tick-stock-panel/research/trade-ledger-20261107/pattern_review/'
b=pd.read_pickle(BASE+'buys_tagged.pkl'); rt=pd.read_pickle(BASE+'rt.pkl')
rt['code']=rt['code'].astype(str).str.zfill(6)
b['code']=b['code'].astype(str).str.zfill(6)
rt['open_time']=pd.to_datetime(rt['open_time'])
rt['key']=rt['code']+'|'+rt['open_time'].dt.strftime('%Y-%m-%d %H:%M:%S')
b['key']=b['code']+'|'+pd.to_datetime(b['date']).dt.strftime('%Y-%m-%d')+' '+b['time'].astype(str)
bm=b.drop_duplicates('key').set_index('key')
cols=['day_pct','clu','is_lu','at_limit_px','tags','verdict','exp_ref','ret20','ret60','listed_days']
m=rt['key'].isin(bm.index)
print('rt rows',len(rt),'matched',int(m.sum()),flush=True)
for c in cols: rt[c]=rt['key'].map(bm[c])
rt['tags']=rt['tags'].fillna('无买入记录')
rt['verdict']=rt['verdict'].fillna('X 无买入记录')
rt['exp_ref']=rt['exp_ref'].fillna('-')
print(rt['verdict'].value_counts().to_string(),flush=True)
g=rt.groupby('verdict').agg(n=('pnl','size'),pnl=('pnl','sum'),per=('pnl','mean'),win=('pnl',lambda s:(s>0).mean()*100),hold=('hold_td','mean')).round(1)
print(g.to_string(),flush=True)
print('TOTAL',round(rt['pnl'].sum(),2),flush=True)
rt.to_pickle(BASE+'rt_tagged.pkl')
