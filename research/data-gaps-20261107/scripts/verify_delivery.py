"""Run one audit stage and persist its real process result, scoped to this directory."""
from pathlib import Path
import datetime
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / 'results'
STAGE = sys.argv[1]
if STAGE in ('industry', 'index', 'etf', 'short', 'universe616'):
    args = ['backend/.venv/Scripts/python.exe', 'research/data-gaps-20261107/scripts/audit_data_gaps.py', '--check', STAGE]
elif STAGE in ('independent_recheck', 'build_summary'):
    args = ['backend/.venv/Scripts/python.exe', f'research/data-gaps-20261107/scripts/{STAGE}.py']
else:
    raise SystemExit('Unknown stage')
started = time.monotonic()
env = dict(os.environ, PYTHONUTF8='1')
proc = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8')
log = OUT / f'run_{STAGE}.log'
log.write_text(proc.stdout + proc.stderr, encoding='utf-8')
entry = {'id': STAGE, 'argv': args, 'command': 'PYTHONUTF8=1 ' + ' '.join(args), 'exit_code': proc.returncode,
         'elapsed_seconds': round(time.monotonic()-started, 3),
         'recorded_at': datetime.datetime.now().astimezone().isoformat(),
         'output_path': log.relative_to(ROOT).as_posix()}
manifest = OUT / 'execution_log.json'
existing = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'runs': []}
existing['runs'] = [x for x in existing['runs'] if x['id'] != STAGE] + [entry]
manifest.write_text(json.dumps(existing, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(entry, ensure_ascii=False))
print(proc.stdout[-1600:])
if proc.returncode:
    print(proc.stderr[-1600:])
raise SystemExit(proc.returncode)
