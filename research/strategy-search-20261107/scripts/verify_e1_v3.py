"""Independent arithmetic and artifact verification; never runs a backtest."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]
OUT = BASE/'results'/'e1_v3'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def main():
    e = read(OUT/'e1_survivorship.json')
    execution = read(OUT/'execution.json')
    freeze = read(BASE/'FREEZE_v3_E1.json')
    checks = {}
    checks['frozen_files_unchanged'] = all(sha(ROOT/p)==h for p, h in freeze['files_sha256'].items())
    checks['old_freeze_preserved'] = sha(BASE/'FREEZE.json')==freeze['old_freeze_sha256']
    checks['old_protocol_archive_matches_old_freeze'] = sha(BASE/'PROTOCOL_v2_ARCHIVE.md')==read(BASE/'FREEZE.json')['docs'][0]['sha256']
    checks['execution_hashes'] = all(sha(OUT/p)==h for p,h in execution['outputs'].items())
    checks['panel_ipc_hash'] = sha(OUT/'panel_input.arrow')==e['panel_ipc_sha256']
    values = {}
    stale = set(e['stale_symbols'])
    for g in ['A', 'B']:
        payload = read(OUT/f'run_C00_{g}.json')
        v = np.array([float(x['value']) for x in payload['equity']])
        values[g] = v
        cagr = (v[-1]/v[0])**(252/(len(v)-1))-1
        checks[f'{g}_cagr'] = abs(cagr-e[g]['cagr'])<1e-12
        mv = sum(float(p['shares'])*float(p['mark']) for p in payload['final_positions'])
        checks[f'{g}_accounting'] = abs(payload['final_cash']+mv-v[-1])<=.05
        checks[f'{g}_share'] = abs(mv/v[-1]-e[g]['open_at_end_share'])<1e-12
        if g=='A':
            stale_mv = sum(p['market_value'] for p in payload['final_positions'] if p['symbol'] in stale)
            checks['haircuts_recomputed'] = all(abs(((v[-1]+x['haircut']*stale_mv)/v[0])**(252/(len(v)-1))-1-x['cagr_A'])<1e-12 for x in e['haircut_sensitivity'])
    raw_a = read(OUT/'run_C00_A.json')
    dates = [str(x['date'])[:10] for x in raw_a['equity']]
    yearly_ok = True
    for y in e['yearly']:
        ids = [i for i,d in enumerate(dates) if int(d[:4])==y['year']]
        lo, hi = max(0, ids[0]-1), ids[-1]
        diff = ((values['A'][hi]/values['A'][lo]-1)-(values['B'][hi]/values['B'][lo]-1))*100
        yearly_ok &= abs(diff-y['diff_pp'])<1e-12
    checks['yearly_recomputed'] = bool(yearly_ok)
    checks['fail_trigger'] = e['A']['open_at_end_share']>.02
    checks['actual_exit_matches_machine_judgement'] = execution['actual_exit_code']==e['exit_code']==3 and e['verdict']=='FAIL'
    checks = {key: bool(value) for key, value in checks.items()}
    report = {'verification_verdict': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks,
              'e1_verdict': e['verdict'], 'e1_actual_exit_code': execution['actual_exit_code'],
              'reason': 'A全部未平仓市值/权益47.3177%超过原协议2%；其中停更仓位市值为0。FAIL不是显著幸存者收益差异或退市挂账损失的证据，原门槛混合正常持仓与停更风险。不得事后改门槛使本次PASS。',
              'blocked': '停止后续策略回测；若拟修订E1指标，应先登记新版本并保留本次FAIL，不选择性重跑。',
              'alpha_hypothesis_delta': 0, 'global_N_exact': None, 'global_N_lower_bound': 15}
    (OUT/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
