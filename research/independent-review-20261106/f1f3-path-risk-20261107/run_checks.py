"""Independent orchestration. All evidence writes confined to reviewer directory."""
from pathlib import Path
import subprocess, json, hashlib, time
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
DEV=ROOT/'research/batch-backtest-framework-20261107'
PY=ROOT/'backend/.venv/Scripts/python.exe'
WATCH=[DEV/'verify_batch_v2.py',DEV/'run_batch.py',DEV/'mutation_checks.py',DEV/'REPORT-F1F3.md',ROOT/'research/strategy-search-20261107/results/PATH_RISK.md',ROOT/'backend/app/backtest/engine.py',ROOT/'backend/app/backtest/walkforward.py']
def fingerprints():
 return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in WATCH}
state={'before':fingerprints(),'commands':[]}
(HERE/'execution.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
commands=[
 [str(PY),str(DEV/'verify_batch_v2.py'),'--registry',str(DEV/'out_v3/registry.json'),'--out',str(HERE/'fresh-verify')],
 [str(PY),str(DEV/'mutation_checks.py'),'--registry',str(DEV/'out_v3/registry.json'),'--verify-dir',str(HERE/'fresh-verify'),'--out',str(HERE/'mutation-report.json')],
]
for n,command in enumerate(commands,1):
 start=time.time()
 with (HERE/f'command-{n}.log').open('w',encoding='utf-8') as log:
  r=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
 state['commands'].append({'argv':command,'exit_code':r.returncode,'elapsed_s':round(time.time()-start,2),'log':f'command-{n}.log'})
 (HERE/'execution.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
state['after']=fingerprints()
state['unchanged']=state['before']==state['after']
(HERE/'execution.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
