# 独立工程审核：连续 WFO 账户与接口

审核日期：2026-11-06，北京时间；独立审核工程师。结论：**阻断验收，不建议合并当前回测相关改动**。确认 3 项 P1；需由系统开发工程师修复并由独立审核复验。本次不修改被审核源码。

## 1. 基线、范围与边界

项目 HEAD：`848bd04b7266f6645fabdfdc4b2c0cdf404eb643`。审核对象为该 HEAD 加当前未提交工作区，不能只用 HEAD 复现。起始存在 40 个已跟踪修改/删除以及多批未跟踪研究、扩展和测试文件。保留全部并行修改，未整理或删除任何他人成果。

已读根 AGENTS.md、CONTRIBUTING.md、docs/README.md、docs/secondary-development.md，以及 research/wyckoff-system-design-20261106/INTEGRATION-DESIGN.md。实际检查 API → WalkForwardService → StrategyBacktestConfig/Service → SimulationOptions → 撮合引擎结转路径、相关核心差异、前端连续账户类型/显示与已有测试。该变更属于 L3 核心撮合与编排变更。

威科夫设计文档明确“设计提案，未实现”。本次不把架构提案、研究脚本或既有 WFO 改动当作威科夫实现，不对其默认关闭、确认日期、未来扰动或盈利能力作实现通过验收。研究有效性仍由量化研究员独立验收，架构责任仍在系统架构师。

核心文件检查时 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| backend/app/api/backtest.py | 769a0cfadb99e98061e523265e055e1e89d32547cf659d8aa802f2fa7bc1a286 |
| backend/app/backtest/engine.py | 2b650ca978961abba54df15c7f164cdfb3fe6e2080ab8073d8ad5c4f7d9514bb |
| backend/app/backtest/strategy.py | 769404dbb27378d70451d07a55bb73c349027363cc8b9ee282141ecb8dcb2583 |
| backend/app/backtest/walkforward.py | ec4b8d5bcdff778beca77b8e0ce83c389c98592e7f561768b83f4de2a28164ae |

## 2. 确认的阻断缺陷

### R1 — P1：正常流式 WFO 请求直接 HTTP 500

精确位置：`backend/app/api/backtest.py:1361` 的 walkforward_stream 参数列表缺少 continuous_account；`:1443` 把未定义名称传入任务键；`:1506` 再用于配置构造。

触发：合法 sortino、position 请求，提供 start/end，正常执行到任务键计算。即使查询串明确提供 continuous_account=true，FastAPI 也不会将未声明参数注入该函数。

独立证据：用 FastAPI 单独注册实际 backtest.router，通过 TestClient 请求 `/api/backtest/walkforward/stream`，参数 strategy_id=audit_dummy、param_grid={"x":[1]}、start=2025-01-01、end=2025-12-31、continuous_account=true。响应 **500 Internal Server Error**；打开 TestClient 异常传播后为 **NameError: name 'continuous_account' is not defined**。此故障发生在任务启动前，不依赖策略存在或行情仓库，也没有启动真实 worker。inspect.signature 同时证实参数不存在。独立 Ruff F821 返回上述两处错误，退出码 1。

影响：正常核心 WFO SSE 流无法建立。已有非法 objective/full mode 拒绝测试会提前返回，覆盖不到该路径。

修复建议：由开发工程师在真实 API 查询契约中声明布尔参数，明确兼容默认值，贯通任务键和 WalkForwardConfig。补正常成功路径的 API 测试（用受控 worker，不仅测试早期拒绝）；分别验证 true/false/省略参数、任务键隔离和 SSE job/done/error。不要以模块全局常量掩盖请求参数缺失。

### R2 — P1：跨折重置局部入场索引，改变持有期延长规则的退出日期

精确位置：`backend/app/backtest/engine.py:2665` 将结转持仓 entry_time_id 重置为 -1；`:4100` 又使用 `time_id - entry_time_id + 1` 计算 holding_day；`:4102` 仅在等于 decision_days 时作持有决策。

触发：持仓使用 HoldExtensionPolicy，跨折前已持有若干交易日，而决策日或延长到期日落在后续折。同参数、同数据，仅切分位置改变。

独立撮合证据：使用现有 _panel 的 10 根受控日线，把 OHLC/raw_close 全部固定为 10，第一日收盘发买入信号，下一日开盘成交，HoldExtensionPolicy(decision_days=5)，finalize_open_at_end=True；完整回放与 head(4)/tail(6) 结转回放对照。两次均明确 entry_fill/exit_fill=open_t+1。

| 路径 | 入场日 | 退出日 | 退出原因 | duration |
| --- | --- | --- | --- | --- |
| 一次完整回放 | 2025-01-03 | 2025-01-08 | time_exit | 5 |
| 拆段后结转 | 2025-01-03 | 2025-01-10 | time_exit | 7 |

两次运行均复现该差异；第二次明确设置独立 entry_fill/exit_fill，排除 matching 兼容入口歧义。样本采用连续自然日期作为显式合成交易序列，不代表真实交易日历；错误由交易序列局部索引复位造成。

影响：边界改变实际持仓时长与退出时点，进而改变收益和风险。现有“拆段等于整段”测试覆盖普通退出信号，未覆盖 HoldExtensionPolicy。

修复建议：使用可跨段保留的累计交易日年龄/明确全局偏移，并对开盘/收盘入场的包含关系统一定义。还要核验 runner_new_high_days 的前序行情窗口在折首是否足够，避免只修年龄后遗漏历史窗口。补相同数据、同参数、不同切分点的交易逐笔/费用/现金/期末权益等价检查，覆盖决策日前后和延长持有到期。

### R3 — P1：测试窗存在间隔时，连续账户跳过持仓管理并遗漏止损

精确位置：`backend/app/backtest/walkforward.py:48` 仅拒绝 step_days < test_days，允许 step_days > test_days；`:403` 连续回放只遍历 optimized 中的测试窗；`:308`、`:309` 将每段限制为 fold.test_start/test_end。`:699` 训练失败后 continue 也可能形成同类缺口，后者本次仅确认代码路径，未单独执行训练失败探针。

独立证据：实际 WalkForwardService 编排，使用受控 _FakeOptimizer 固定训练结果；OOS service 适配到真实 build_market_matrix 和 BacktestEngine.simulate_market_matrix，不用假收益替代撮合。显式交易序列 2025-01-02 至 2025-01-09，train=1/test=3/step=4。两段 OOS 为 01-03~01-05 与 01-07~01-09。首段形成真实结转持仓；价格通常为10，间隔日 01-06 OHLC/raw_close 跌至5，随后恢复10；stop_loss_pct=0.1，初始资本100000。

| 项目 | WFO 跳窗回放 | 覆盖全部 OOS 日期的完整回放 |
| --- | --- | --- |
| 01-06 是否处理 | 否，权益曲线缺该日 | 是 |
| 止损 | 漏掉 | 01-06 stop_loss |
| 期末权益 | 99,993.70 | 95,490.55 |

实际 WFO 返回 return_kind=single_account_single_timeline、stopped_early=null，现有六项 invariants 全部 true。因而这些计数/期末代数检查不能证明时间线完整。第一版 2 日短窗探针出现额外空段影响，未用作该数值结论；本表来自 3 日测试窗的最终成功复现。

影响：正常允许的窗口配置下，持仓在缺口交易日的止损、持有期与现金变化被跳过，产出冒充连续账户的失真结果。待执行次日开盘计划也可能延迟到后续窗口首日。

修复建议：第一步可拒绝连续模式下 step_days != test_days，并在训练失败形成缺口时明确停止/拒绝，而不能无标识继续；如产品确需间隔窗，必须定义缺口内沿用何种已知参数并逐交易日回放风险和估值。加入账户日期与交易日历的完整覆盖检查，补含缺口止损、待执行订单及中间训练失败的反例测试。不得仅过滤重复日期或依赖当前 invariants。

## 3. 已验证通过与证据限制

从 backend 目录使用现有 `.venv/Scripts/python.exe` 独立执行：

```text
-m pytest tests/backtest/test_continuous_account.py tests/backtest/test_walkforward.py tests/backtest/test_strategy_backtest_correctness.py -q -p no:cacheprovider
67 passed, 1 warning in 22.14s；退出码0
```

警告为 anyio/pytest 的 CallSpec2 弃用提示。上述结果是本审核实跑结果，未引用作者的 27+20 自测作为独立通过证据。

已验证：普通信号跨段交易的整段/拆段等价样例、段末买入计划结转、缺失持仓标的拒绝、空中间段平线、禁止 OOS 重叠、训练/测试日期分隔、最少交易门槛的诊断行为、末折持仓报告与未平仓交易数量的现有定向用例。

期末持仓专项：当前 walkforward.py:444~454 在末折无 carry_state 时读取末个权益点；:512~566 给出期末现金/持仓/市值与生命周期计数。`test_final_open_positions_come_from_last_fold_not_missing_carry_state` 已独立通过，因此不再把“末折 carry_state=None 导致误报零持仓”列为当前缺陷。额外普通默认清算探针的末点为 cash=108949.15、positions=0，与一笔已完成 end 退出一致。该证据不覆盖所有停牌、封板、公司行动或提前取消后的未平仓情况。

额外质量检查：

| 检查 | 结果 |
| --- | --- |
| API Ruff --select F821 | 2错误，退出码1，见R1 |
| git diff --check | 退出码2；已有 backend/tests/test_industry_chain_extension.py:808 文件尾额外空行，未改动该文件 |
| 相关自动任务 | 本审核机器人无自动任务 |

## 4. 未验证范围与验收门槛

- 未执行全后端回归、worker 子进程全路径、真实数据多年 WFO、性能/内存基准、前端 pnpm build 和浏览器联调；不能宣称整个工作区通过工程验收。
- R3 使用真实撮合和真实 WFO 编排，但优化器与 OOS service 外围为受控适配；不证明真实仓库数据质量或共享矩阵所有路径。R2 直接在实际引擎层复现；服务层对具体策略元数据的组合仍需开发修复后补集成测试。
- 本次没有针对全部策略输入做未来扰动和前缀一致性审计，未发现新泄漏不等于已证明无未来数据。威科夫确认日、失效事件历史快照、默认关闭无查询等尚无正式实现可验。
- 连续账户的现金/持仓结转、明确区分逐折复利诊断值是正确方向，但R2/R3破坏账户语义，当前不能作为可靠连续WFO绩效。

解除阻断要求：R1正常API路径成功并覆盖布尔参数；R2同参数跨段交易与完整回放一致；R3拒绝或真实处理时间缺口，并覆盖中间训练失败。修复由系统开发工程师完成，随后独立复验完整差异和受影响回归；本报告不授予发布/合并/交易许可。

## 5. 可复现实验代码

在 backend 目录，用已有虚拟环境运行以下 Python。代码只使用内存受控样本和本地测试模块，不访问真实账户、外部行情或启动服务。audit 文档未写入生产代码，也未新建被审核测试。

```python
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
```

未执行提交、推送、部署、重启、购买或任何交易；未写 parallel-data-20261106、parallel-review-20261106 及其 docs 镜像目录。

## 6. 报告落盘后的复核

从本报告第5节直接提取 Python 代码，经现有虚拟环境再次执行，退出码0：R1=500；R2=01-08对01-10退出；R3=99993.70对95490.55、缺01-06、stopped_early=null、六项invariants全true。证明报告所附复现实验本身可执行。最终复核的四份核心源码 SHA-256 与第1节完全一致。

最终 git status 已检查；本审核唯一主动新增的项目成果为本 REVIEW.md。并行出现的 docs/document-management、research/architecture-20261106、research/program-planning-20261106 等成果未修改、未归为本审核产出。所有既有核心修改仍保留。
