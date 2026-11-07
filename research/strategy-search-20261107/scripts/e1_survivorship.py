"""E1 only: stale-membership diagnostic, not an alpha search."""
from __future__ import annotations

import json
import sys
import traceback
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

import numpy as np
import polars as pl

import common

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'results' / 'e1_v3'


def judge(diff_pp, yearly_pp, share_a, share_b):
    # FAIL has priority over PASS/WARN; uncovered combinations fail closed to WARN.
    if abs(diff_pp) >= 3 or share_a > .02:
        return 'FAIL', 3
    if abs(diff_pp) < 1 and all(abs(x) < 2 for x in yearly_pp) and abs(share_a-share_b) < .05:
        return 'PASS', 0
    return 'WARN', 2


def stats(values):
    v = np.asarray(values, dtype=float)
    if len(v) < 3 or not np.all(np.isfinite(v)) or np.any(v <= 0):
        raise ValueError('invalid equity series')
    r = np.diff(v)/v[:-1]
    return {'cagr': float((v[-1]/v[0])**(252/len(r))-1),
            'sharpe': float(r.mean()/r.std(ddof=1)*np.sqrt(252)) if r.std(ddof=1)>0 else 0.,
            'max_drawdown': float((v/np.maximum.accumulate(v)-1).min())}


def simulate(m, panel, group):
    # Removal is already complete before any universe or indicator computation.
    f = common.add_universe(common.add_indicators(panel)).with_columns(
        (pl.col('in_universe') & pl.col('month_end')).fill_null(False).alias('e_ctl'),
        pl.col('month_end').fill_null(False).alias('x_ctl'),
        pl.col('prior_amount20').fill_null(0).alias('score'),
    )
    carry = None
    equity, trades, segments = [], [], []
    for start, end in common.year_segments():
        seg = f.filter(pl.col('date').is_between(start, end)).sort(['date', 'symbol'])
        matrix = common.build_market_matrix(seg, seg['e_ctl'], seg['x_ctl'],
                                            entry_delay_bars=1, exit_delay_bars=1)
        if matrix.score is None:
            raise AssertionError('liquidity ranking score missing')
        res = m.engine.simulate_market_matrix(
            matrix, common.make_config(10., 20),
            options=common.SimulationOptions(include_monte_carlo=False, carry_in=carry, carry_out=True))
        carry = res.carry_state
        equity.extend(res.equity_curve)
        trades.extend(asdict(t) for t in res.trades)
        segments.append({'start': str(start), 'end': str(end), 'stats': res.stats})
        print(group, start.year, len(res.trades), flush=True)
    if carry is None:
        raise ValueError('empty carry')
    marks = []
    for p in carry.positions:
        symbol = p['symbol']
        mark = carry.last_close.get(symbol, p['entry_price'])
        marks.append({'symbol': symbol, 'shares': float(p['shares']), 'mark': float(mark),
                      'market_value': float(p['shares']*mark), 'fallback_entry_price': symbol not in carry.last_close})
    payload = {'equity': equity, 'trades': trades, 'segments': segments,
               'final_cash': carry.cash, 'final_positions': marks,
               'carry': asdict(carry), 'group': group, 'slippage_bps': 10,
               'score_mapping': 'prior_amount20 -> score'}
    common.save_json(OUT/f'run_C00_{group}.json', payload)
    return payload


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # Numeric boundary checks before expensive simulation.
    assert judge(.99, [1.99], .02, .02) == ('PASS', 0)
    assert judge(1., [0.], 0., 0.) == ('WARN', 2)
    assert judge(3., [0.], 0., 0.) == ('FAIL', 3)
    assert judge(0., [0.], .02001, 0.) == ('FAIL', 3)
    assert judge(0., [2.], 0., 0.) == ('WARN', 2)
    assert judge(0., [0.], 0., .05) == ('WARN', 2)
    assert abs(stats([100., 110., 121.])['cagr'] - (1.21**126-1)) < 1e-5
    freeze = json.loads((BASE/'FREEZE_v3_E1.json').read_text(encoding='utf8'))
    from hashlib import sha256
    for rel, expected in freeze['files_sha256'].items():
        if sha256((common.PROJECT/rel).read_bytes()).hexdigest() != expected:
            raise ValueError(f'frozen input changed: {rel}')
    m = common.open_market()
    print('loading panel', flush=True)
    panel = common.load_panel(m)
    days = panel['date'].unique().sort().to_list()
    if days[-1] != common.EVAL_END:
        raise ValueError('panel end mismatch')
    cutoff = days[-21]
    lifecycle = panel.group_by('symbol').agg(pl.col('date').max().alias('last_bar'), pl.len().alias('bars'))
    stale = lifecycle.filter((pl.col('last_bar') < cutoff) & (pl.col('bars') >= 120))['symbol'].sort().to_list()
    panel_hash = common.fingerprint(panel)
    # Semantic Polars hash + complete persisted input frame hash.
    panel.write_ipc(OUT/'panel_input.arrow', compression='zstd')
    ipc_hash = sha256((OUT/'panel_input.arrow').read_bytes()).hexdigest()
    meta = {'generated_at': datetime.now().astimezone().isoformat(), 'window': {'start': str(common.EVAL_START), 'end': str(common.EVAL_END)},
            'panel_hash': panel_hash, 'panel_ipc_sha256': ipc_hash, 'rows': panel.height,
            'stale_cutoff_exclusive': str(cutoff), 'stale_symbols': stale,
            'python': sys.version, 'polars': pl.__version__, 'data_dir': str(common.settings.data_dir),
            'freeze_sha256': sha256((BASE/'FREEZE_v3_E1.json').read_bytes()).hexdigest()}
    common.save_json(OUT/'inputs.json', meta)
    a = simulate(m, panel, 'A')
    bpanel = panel.filter(~pl.col('symbol').is_in(stale))
    b = simulate(m, bpanel, 'B')
    dates_a = [str(x['date'])[:10] for x in a['equity']]
    dates_b = [str(x['date'])[:10] for x in b['equity']]
    if dates_a != dates_b or len(set(dates_a)) != len(dates_a):
        raise ValueError('equity calendars differ or duplicate')
    groups = {}
    for key, result in [('A', a), ('B', b)]:
        values = [float(x['value']) for x in result['equity']]
        sm = stats(values)
        mv = sum(x['market_value'] for x in result['final_positions'])
        if abs(result['final_cash']+mv-values[-1]) > .05:
            raise ValueError(f'{key}: terminal cash+positions != equity')
        sm.update(n_closed_trades=len([t for t in result['trades'] if not t.get('open_at_end')]),
                  open_at_end=len(result['final_positions']), open_at_end_share=mv/values[-1],
                  final_equity=values[-1])
        groups[key] = sm
    yearly = []
    for year in sorted(set(x[:4] for x in dates_a)):
        inds = [i for i, d in enumerate(dates_a) if d[:4] == year]
        lo, hi = max(0, inds[0]-1), inds[-1]
        ra = float(a['equity'][hi]['value'])/float(a['equity'][lo]['value'])-1
        rb = float(b['equity'][hi]['value'])/float(b['equity'][lo]['value'])-1
        yearly.append({'year': int(year), 'return_A': ra, 'return_B': rb, 'diff_pp': (ra-rb)*100})
    stale_mv = sum(x['market_value'] for x in a['final_positions'] if x['symbol'] in stale)
    vals = [float(x['value']) for x in a['equity']]
    haircut = []
    for h in [0., -.3, -.5, -1.]:
        final = vals[-1] + h*stale_mv
        ca = (final/vals[0])**(252/(len(vals)-1))-1
        haircut.append({'haircut': h, 'cagr_A': ca, 'final_equity': final,
                        'decline_pp': (groups['A']['cagr']-ca)*100})
    diff = (groups['A']['cagr']-groups['B']['cagr'])*100
    verdict, code = judge(diff, [x['diff_pp'] for x in yearly], groups['A']['open_at_end_share'], groups['B']['open_at_end_share'])
    changed = [rel for rel, expected in freeze['files_sha256'].items()
               if sha256((common.PROJECT/rel).read_bytes()).hexdigest() != expected]
    if changed:
        raise ValueError(f'code/docs changed during execution: {changed}')
    result = {**meta, 'window': {**meta['window'], 'n_days': len(vals)-1},
              'counts': {'n_symbols_A': panel['symbol'].n_unique(), 'n_symbols_B': bpanel['symbol'].n_unique(), 'n_stale': len(stale)},
              **groups, 'diff': {'cagr_pp': diff, 'sharpe': groups['A']['sharpe']-groups['B']['sharpe'],
                               'mdd_pp': (groups['A']['max_drawdown']-groups['B']['max_drawdown'])*100},
              'yearly': yearly, 'haircut_sensitivity': haircut, 'stale_terminal_market_value': stale_mv,
              'verdict': verdict, 'exit_code': code, 'checks': {'judge_boundaries': True, 'code_unchanged': True, 'cash_position_reconciliation': True, 'aligned_calendars': True},
              'direction': '剔除停更股低估收益' if diff>0 else ('仅保留存续股高估收益' if diff<0 else '本基准无收益差异'),
              'limitations': ['停更并非权威退市/停牌标签；不能消除供应商幸存者偏差', '2018前消失证券无法检验',
                              'haircut仅对期末仍持有的停更仓位作终值压力，不模拟历史强制清算',
                              'C00集中流动性最大5只，不能代表其他策略持有停更股风险',
                              '交易约束沿用现有引擎；未独立审计引擎全部成交路径；日线不能证明盘中可成交',
                              '历史区间均已观测；本诊断不是独立盈利验证']}
    common.save_json(OUT/'e1_survivorship.json', result)
    print(json.dumps({'verdict': verdict, 'exit_code': code, 'cagr_pp': diff, 'A': groups['A'], 'B': groups['B']}, ensure_ascii=False), flush=True)
    return code


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        OUT.mkdir(parents=True, exist_ok=True)
        common.save_json(OUT/'error.json', {'verdict': 'INPUT_OR_RUN_ERROR', 'exit_code': 1, 'error': repr(exc), 'traceback': traceback.format_exc()})
        traceback.print_exc()
        sys.exit(1)
