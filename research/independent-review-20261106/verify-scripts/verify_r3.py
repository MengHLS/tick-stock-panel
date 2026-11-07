
import dataclasses
import importlib.util
import json
import sys
from types import SimpleNamespace
import polars as pl
from app.backtest.engine import BacktestEngine, MatcherConfig, SimulationOptions
from app.backtest.matrix import build_market_matrix
from app.backtest.walkforward import WalkForwardConfig, WalkForwardService

for name, file in [('m', 'tests/backtest/test_continuous_account.py'),
                   ('w', 'tests/backtest/test_walkforward.py')]:
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    globals()[name] = module


def run(part, entries=(), carry=None, out=False, stop=None):
    matrix = build_market_matrix(
        part, pl.Series([i in entries for i in range(len(part))]),
        pl.Series([False] * len(part)), entry_delay_bars=1, exit_delay_bars=1,
    )
    config = MatcherConfig(
        matching='open_t+1', entry_fill='open_t+1', exit_fill='open_t+1',
        initial_capital=100000, finalize_open_at_end=True, stop_loss_pct=stop,
    )
    return BacktestEngine(repo=None).simulate_market_matrix(
        matrix, config,
        options=SimulationOptions(include_monte_carlo=False,
                                  carry_in=carry, carry_out=out),
    )


columns = ['open', 'high', 'low', 'close', 'raw_close']
panel = m._panel(8).with_row_index('idx').with_columns(*[
    pl.when(pl.col('idx') == 4).then(5.).otherwise(10.).alias(k) for k in columns
]).drop('idx')


class Service:
    def __init__(self):
        self.engine = w._FakeEngine()
        self.calls = []

    def run(self, config, **kwargs):
        self.calls.append((config.start, config.end))
        part = panel.filter(pl.col('date').is_between(config.start, config.end))
        result = run(part, {0} if len(self.calls) == 1 else (),
                     carry=config.carry_state, out=config.carry_out, stop=.1)
        return SimpleNamespace(
            stats=result.stats, equity_curve=result.equity_curve,
            drawdown_curve=result.drawdown_curve,
            trades=[dataclasses.asdict(t) for t in result.trades],
            carry_state=result.carry_state, error=None,
        )


days = tuple(panel['date'].to_list())
full = run(panel.tail(7), {0}, stop=.1)
print('FULL', json.dumps({
    'equity': full.stats['final_equity'],
    'trades': [(str(t.exit_date), t.exit_reason) for t in full.trades],
}, default=str))

for train, test, step in [(1, 3, 4), (1, 3, 3)]:
    service = Service()
    config = WalkForwardConfig(
        strategy_id='s', symbols=None, start=days[0], end=days[-1],
        param_grid={'p': [1]}, train_days=train, test_days=test, step_days=step,
        trading_days=days, backtest_kwargs={'initial_capital': 100000},
    )
    try:
        result = WalkForwardService(w._FakeOptimizer(), service,
                                    strategy_engine=None).run(config)
    except ValueError as exc:
        print(f'WFO train={train} test={test} step={step} REJECTED: {exc}')
        continue
    account = result['continuous_account']
    print(f'WFO train={train} test={test} step={step}', json.dumps({
        'windows': [[str(x), str(y)] for x, y in service.calls],
        'curve_dates': [p['date'] for p in account['equity_curve']],
        'equity': account['final_equity'],
        'stopped_early': account['stopped_early'],
        'timeline_gap': account.get('timeline_gap'),
        'invariants': account['invariants'],
        'trades': [(str(t.get('exit_date')), t.get('exit_reason')) for t in account.get('trades', [])],
    }, default=str))
