
import dataclasses
import importlib.util
import inspect
import json
import sys
from types import SimpleNamespace
import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import backtest
from app.backtest.engine import (
    BacktestEngine, MatcherConfig, SimulationOptions, HoldExtensionPolicy,
)
from app.backtest.matrix import build_market_matrix
from app.backtest.walkforward import WalkForwardConfig, WalkForwardService

for name, file in [
    ('m', 'tests/backtest/test_continuous_account.py'),
    ('w', 'tests/backtest/test_walkforward.py'),
]:
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    globals()[name] = module

# R1：只注册实际路由，不启动项目 lifespan/worker。
app = FastAPI()
app.include_router(backtest.router)
path = next(r.path for r in app.routes if r.path.endswith('/walkforward/stream'))
params = dict(strategy_id='audit_dummy', param_grid='{"x":[1]}',
              start='2025-01-01', end='2025-12-31', continuous_account='true')
print('continuous parameter declared:',
      'continuous_account' in inspect.signature(backtest.walkforward_stream).parameters)
with TestClient(app, raise_server_exceptions=False) as client:
    response = client.get(path, params=params)
    print('R1', response.status_code, response.text)

# 真实撮合适配：输入样本、信号及规则可控，收益由生产引擎计算。
def run(part, entries=(), carry=None, out=False, hold=None, stop=None):
    matrix = build_market_matrix(
        part, pl.Series([i in entries for i in range(len(part))]),
        pl.Series([False] * len(part)), entry_delay_bars=1, exit_delay_bars=1,
    )
    config = MatcherConfig(
        matching='open_t+1', entry_fill='open_t+1', exit_fill='open_t+1',
        initial_capital=100000, finalize_open_at_end=True,
        hold_extension_policy=hold, stop_loss_pct=stop,
    )
    return BacktestEngine(repo=None).simulate_market_matrix(
        matrix, config, options=SimulationOptions(
            include_monte_carlo=False, carry_in=carry, carry_out=out,
        ),
    )

columns = ['open', 'high', 'low', 'close', 'raw_close']
panel = m._panel(10).with_columns(*[pl.lit(10.).alias(k) for k in columns])
hold = HoldExtensionPolicy(decision_days=5)
full = run(panel, {0}, hold=hold)
first = run(panel.head(4), {0}, out=True, hold=hold)
second = run(panel.tail(6), carry=first.carry_state, hold=hold)
for name, result in [('R2 full', full), ('R2 split', second)]:
    print(name, [(str(t.entry_date), str(t.exit_date), t.exit_reason, t.duration)
                 for t in result.trades])

panel = m._panel(8).with_row_index('idx').with_columns(*[
    pl.when(pl.col('idx') == 4).then(5.).otherwise(10.).alias(k)
    for k in columns
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
service = Service()
config = WalkForwardConfig(
    strategy_id='s', symbols=None, start=days[0], end=days[-1],
    param_grid={'p': [1]}, train_days=1, test_days=3, step_days=4,
    trading_days=days, backtest_kwargs={'initial_capital': 100000},
)
result = WalkForwardService(w._FakeOptimizer(), service, strategy_engine=None).run(config)
account = result['continuous_account']
full = run(panel.tail(7), {0}, stop=.1)
print('R3', json.dumps({
    'windows': [[str(x), str(y)] for x, y in service.calls],
    'curve_dates': [p['date'] for p in account['equity_curve']],
    'wfo_equity': account['final_equity'],
    'full_equity': full.stats['final_equity'],
    'full_trades': [(str(t.exit_date), t.exit_reason) for t in full.trades],
    'stopped_early': account['stopped_early'],
    'invariants': account['invariants'],
}, default=str))
