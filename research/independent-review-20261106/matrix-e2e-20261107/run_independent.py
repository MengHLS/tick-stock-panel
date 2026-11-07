import subprocess,json,time
from pathlib import Path
p=Path('C:\\work\\sourcecode\\tick-stock-panel')
d=Path('C:\\work\\sourcecode\\tick-stock-panel\\research\\independent-review-20261106\\matrix-e2e-20261107')
args=['C:\\work\\sourcecode\\tick-stock-panel\\backend\\.venv\\Scripts\\python.exe', 'research/batch-backtest-framework-20261107/run_batch.py', '--groups', 'research/batch-backtest-framework-20261107/groups.json', '--start', '2024-12-02', '--end', '2026-10-31', '--train-days', '252', '--test-days', '63', '--keep-raw', '--out', 'C:\\work\\sourcecode\\tick-stock-panel\\research\\independent-review-20261106\\matrix-e2e-20261107\\out']
t=time.time()
with (d/"batch.log").open("w",encoding="utf-8") as f:
 r=subprocess.run(args,cwd=p,stdout=f,stderr=subprocess.STDOUT,env=__import__("os").environ|{"PYTHONIOENCODING":"utf-8"})
(d/"batch-exit.json").write_text(json.dumps({"command":args,"exit_code":r.returncode,"elapsed_s":time.time()-t}),encoding="utf-8")
