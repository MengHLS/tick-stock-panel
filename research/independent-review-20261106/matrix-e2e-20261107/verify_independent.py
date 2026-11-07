import sys,json,hashlib,runpy,time,subprocess,traceback
from pathlib import Path
from datetime import date
import numpy as np
P=Path(r'C:\work\sourcecode\tick-stock-panel')
D=P/'research/independent-review-20261106/matrix-e2e-20261107'
sys.path[:0]=[str(P/'backend'),str(P/'research/batch-backtest-framework-20261107')]
import run_batch as batch
import verify_batch as verify
from app.backtest.engine import BacktestEngine
from app.backtest.walkforward import WalkForwardService
rt=batch.build_runtime()
slice_=batch.prepare_slice(rt,groups=batch.load_groups(P/'research/batch-backtest-framework-20261107/groups.json'),symbols=None,start=date(2024,12,2),end=date(2026,10,31),asset_type='stock',train_days=252,test_days=63,step_days=63)
union=slice_.market
origload=BacktestEngine.load_market_data_matrix_for_backtest
origwf=WalkForwardService.run
axes=[]
def load(self,*args,**kwargs):
 m=origload(self,*args,**kwargs)
 si={s:i for i,s in enumerate(union.symbols)};ti={s:i for i,s in enumerate(union.timestamp_labels)}
 common=[s for s in m.symbols if s in si];extra=sorted(set(union.symbols)-set(m.symbols))
 mj={s:i for i,s in enumerate(m.symbols)}
 dates=[t for t in m.timestamp_labels if t in ti];mt={s:i for i,s in enumerate(m.timestamp_labels)}
 uidx=np.ix_([ti[t] for t in dates],[si[s] for s in common]);midx=np.ix_([mt[t] for t in dates],[mj[s] for s in common])
 diffs={}
 for key in ['open','high','low','close','volume','tradable','limit_up_locked','limit_down_locked']:
  a=getattr(union,key)[uidx];b=getattr(m,key)[midx]
  diffs[key]=int(np.count_nonzero(~((a==b)|(np.isnan(a)&np.isnan(b)))))
 fields={}
 for k in sorted(set(union.fields)&set(m.fields)):
  a=union.fields[k][uidx];b=m.fields[k][midx]
  try: fields[k]=int(np.count_nonzero(~((a==b)|(np.isnan(a)&np.isnan(b)))))
  except TypeError:fields[k]=int(np.count_nonzero(a!=b))
 extras=[]
 for s in extra:
  j=si[s]; rows=np.flatnonzero(union.tradable[:,j]);labs=[union.timestamp_labels[i] for i in rows]
  extras.append({'symbol':s,'tradable_days':len(rows),'first':labs[0] if labs else None,'last':labs[-1] if labs else None,'tradable_in_production_dates':sum(t in set(dates) for t in labs),'tradable_in_IS_OOS':sum('2024-12-02'<=t[:10]<='2026-09-22' for t in labs)})
 axes.append({'requested_start':str(args[1]),'requested_end':str(args[2]),'union_shape':[len(union.timestamp_labels),len(union.symbols)],'production_shape':[len(m.timestamp_labels),len(m.symbols)],'union_window':[union.timestamp_labels[0],union.timestamp_labels[-1]],'production_window':[m.timestamp_labels[0],m.timestamp_labels[-1]],'common_symbols':len(common),'production_only':sorted(set(m.symbols)-set(union.symbols)),'array_diffs':diffs,'field_diffs':fields,'union_only':extras,'generation':self.data_generation('stock')})
 (D/'axis-comparison.json').write_text(json.dumps(axes,ensure_ascii=False,indent=2),encoding='utf-8')
 return m
BacktestEngine.load_market_data_matrix_for_backtest=load
def run(self,cfg,*a,**kw):
 out=origwf(self,cfg,*a,**kw)
 (D/('production-'+cfg.strategy_id+'.json')).write_text(json.dumps(out,ensure_ascii=False,default=str),encoding='utf-8')
 return out
WalkForwardService.run=run
meta={'before':batch.code_fingerprint(),'generation_before':rt.engine.data_generation('stock')}
t=time.time()
try: code=verify.main(['--registry',str(D/'out/registry.json')])
except BaseException:
 traceback.print_exc();code=99
meta.update({'after':batch.code_fingerprint(),'generation_after':rt.engine.data_generation('stock'),'exit_code':code,'elapsed_s':time.time()-t})
(D/'verify-exit.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(code)
