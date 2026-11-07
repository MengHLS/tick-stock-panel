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

repo,service,se,wf=verify.build_runtime()
from app.backtest.walkforward import WalkForwardConfig
cfg=WalkForwardConfig(strategy_id='first_limit_pullback_3f_runner_t74',symbols=None,start=date(2024,12,2),end=date(2026,10,31),param_grid={'min_score_pct':[55.]},backtest_kwargs={'mode':'position','initial_capital':1000000.,'asset_type':'stock'})
prep=wf._prepare_shared_matrix(cfg,slice_.folds)
m=prep.market_data
si={s:i for i,s in enumerate(union.symbols)};ti={s:i for i,s in enumerate(union.timestamp_labels)}
ui=np.ix_([ti[t] for t in m.timestamp_labels],[si[s] for s in m.symbols])
findings={}
for k in ['limit_up_locked','limit_down_locked']:
 a=getattr(union,k)[ui];b=getattr(m,k)
 rows,cols=np.nonzero(a!=b)
 findings[k]={'count':len(rows),'dates':sorted(set(m.timestamp_labels[i] for i in rows)),'count_IS_OOS':sum('2024-12-02'<=m.timestamp_labels[i][:10]<='2026-09-22' for i in rows),'examples':[{'date':m.timestamp_labels[i],'symbol':m.symbols[j],'union':bool(a[i,j]),'single':bool(b[i,j])} for i,j in list(zip(rows,cols))[:5]]}
(D/'mask-difference.json').write_text(json.dumps(findings,ensure_ascii=False,indent=2),encoding='utf-8')
prep.compute_cache.close()
print(json.dumps(findings,ensure_ascii=False))
