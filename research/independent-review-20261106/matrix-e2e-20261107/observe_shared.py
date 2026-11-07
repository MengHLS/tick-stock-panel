import sys,json,time
from pathlib import Path
import numpy as np
P=Path(r'C:\work\sourcecode\tick-stock-panel');D=P/'research/independent-review-20261106/matrix-e2e-20261107'
sys.path[:0]=[str(P/'backend'),str(P/'research/batch-backtest-framework-20261107')]
import run_batch as b
from app.backtest.engine import BacktestEngine
from app.backtest.strategy import StrategyBacktestService
calls=[];prepares=[]
orig=BacktestEngine.load_market_data_matrix_for_backtest
op=StrategyBacktestService.prepare_matrix_optimization
def load(self,*a,**k):
 m=orig(self,*a,**k);calls.append({'id':id(m),'shape':[len(m.timestamp_labels),len(m.symbols)]});return m
def prep(self,configs,*a,**k):
 r=op(self,configs,*a,**k);override=k.get('market_data_override');m=r.market_data
 prepares.append({'override_id':id(override) if override is not None else None,'shares_close':bool(np.shares_memory(m.close,override.close)) if override is not None else None,'read_only':not m.close.flags.writeable,'config':repr(configs[0])});return r
BacktestEngine.load_market_data_matrix_for_backtest=load
StrategyBacktestService.prepare_matrix_optimization=prep
t=time.time()
code=b.main(['--groups',str(P/'research/batch-backtest-framework-20261107/groups.json'),'--start','2024-12-02','--end','2026-10-31','--train-days','252','--test-days','63','--out',str(D/'instrumented-out')])
result={'exit_code':code,'elapsed_s':time.time()-t,'loads':calls,'prepares':prepares}
(D/'shared-observation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(code)
