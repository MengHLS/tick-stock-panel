"""Freeze independent E1 inputs, run once, persist actual subprocess exit code."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]
OUT = BASE/'results'/'e1_v3'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf8')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    freeze_path = BASE/'FREEZE_v3_E1.json'
    if freeze_path.exists():
        raise RuntimeError('freeze already exists; no silent rerun or overwrite')
    old = json.loads((BASE/'FREEZE.json').read_text(encoding='utf8'))
    batch_path = ROOT/'research'/'batch-backtest-framework-20261107'/'out'/'registry.json'
    batch = json.loads(batch_path.read_text(encoding='utf8'))
    ledger = {'created_at': datetime.now().astimezone().isoformat(), 'scope': 'global search accounting reconciliation, not batch-local execution counter',
              'old_freeze_sha256': digest(BASE/'FREEZE.json'), 'baseline_global_hypotheses': old['n_trials'],
              'batch_registry_sha256': digest(batch_path), 'batch_id': batch.get('batch_id'),
              'batch_local_execution_trials': batch.get('totals', {}).get('n_trials'),
              'batch_rules': [{'strategy_id': x['strategy_id'], 'params': x['params'], 'n_trials_execution': x.get('n_trials'),
                               'n_trials_cumulative_local': x.get('n_trials_cumulative')} for x in batch['runs']],
              'reconciliation': '旧全局12+3=15；批量局部12=两组各6次IS/OOS折执行，不是12个独立规则。批量2条与旧prior3的参数/数据/选择沿革重叠尚未独立证实。全局已知下限15，精确全局N未核定，禁止用局部12或未经核实的15直接重算DSR并验收。',
              'global_N_exact': None, 'global_N_lower_bound': 15,
              'e1_entry': {'id': 'E1-v3-C00', 'type': 'data_diagnostic', 'alpha_hypothesis_delta': 0,
                           'planned_replays': 2, 'haircuts': [0, -.3, -.5, -1], 'status': 'frozen_before_run'},
              'policy': '纯复现不新增独立假设；参数邻域每格、规则改变、数据版本改变和情景择优按协议登记；禁止减少累计试验数。此次不执行DSR或新alpha搜索。'}
    save(BASE/'GLOBAL_LEDGER_v3.json', ledger)
    files = [BASE/'PROTOCOL.md', BASE/'PROTOCOL_v2_ARCHIVE.md', BASE/'FREEZE.json', BASE/'E1_E2_SPEC.md',
             BASE/'STRATEGIES.md', BASE/'DATA-BOUNDARY.md', BASE/'GLOBAL_LEDGER_v3.json',
             BASE/'scripts'/'e1_survivorship.py', BASE/'scripts'/'launch_e1_v3.py', BASE/'scripts'/'common.py',
             ROOT/'AGENTS.md', ROOT/'CONTRIBUTING.md']
    # Freeze all backend Python to cover indirect read/execution imports in a dirty workspace.
    files += list((ROOT/'backend'/'app').rglob('*.py'))
    hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(set(files))}
    save(freeze_path, {'schema': 'strategy-search-e1-freeze/3', 'created_at': datetime.now().astimezone().isoformat(),
                       'protocol_version': 'v3', 'purpose': 'E1 only, no retrospective preregistration or profit confirmation',
                       'old_freeze_sha256': digest(BASE/'FREEZE.json'), 'files_sha256': hashes,
                       'prospective_candidate_freeze': None, 'prospective_start': None, 'earliest_confirmatory_date': None,
                       'observations': {'annual': '完整一年 AND >=240交易日 AND 四个完整自然季度', 'lockbox': '随后互斥>=60交易日，一次检验'},
                       'global_N_exact': None, 'global_N_lower_bound': 15, 'e1_alpha_hypothesis_delta': 0})
    git = subprocess.run(['git', '-C', str(ROOT), 'status', '--short'], capture_output=True, text=True)
    (OUT/'git_before.txt').write_text(git.stdout+git.stderr, encoding='utf8')
    command = [sys.executable, str(BASE/'scripts'/'e1_survivorship.py')]
    started = datetime.now().astimezone().isoformat()
    save(OUT/'execution_started.json', {'command': command, 'cwd': str(ROOT), 'started_at': started, 'status': 'started', 'git_status_exit_code': git.returncode})
    env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}
    with (OUT/'execution.log').open('w', encoding='utf8') as log:
        proc = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    result = {'command': command, 'cwd': str(ROOT), 'started_at': started,
              'ended_at': datetime.now().astimezone().isoformat(), 'actual_exit_code': proc.returncode,
              'log_sha256': digest(OUT/'execution.log'), 'freeze_sha256': digest(freeze_path),
              'outputs': {p.name: digest(p) for p in OUT.iterdir() if p.is_file() and p.name not in ('panel_input.arrow', 'execution.json')}}
    save(OUT/'execution.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return proc.returncode


if __name__ == '__main__':
    sys.exit(main())
