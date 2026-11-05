# KHunter 策略借鉴可行性

研究日期：2026-11-05。范围：KHunter 源码静态核对、一个指标方向隔离实验、本仓库接入契约核对。没有执行历史收益回测，没有导入或启用用户策略。

## 结论

大部分日线选股逻辑可以按 L1 改写为本项目自定义策略，无需移植 KHunter 的 Flask、SQLite、数据抓取和回测引擎。技术可接入不代表收益有效；原策略命中集合、修正口径后的命中集合和交易收益必须分别验证。

主要来源：[KHunter](https://github.com/ling-0729/KHunter)。本次下载 main 分支源码归档；GitHub API 同期返回 main HEAD `9b2e8f0b179c4c897fac899673bf9c0751b5507e`（提交时间 2026-10-07T10:57:02Z）。逐文件与该 SHA 的远端比对因连接重置未完成，因此以下链接引用检查时的 main，不将归档宣称为已完成哈希校验的冻结快照。

## 实际策略范围

AST 检查 `strategy/` 中非下划线文件，得到直接继承 `BaseStrategy` 的 12 个候选类。注册器扫描这一层目录；实际加载仍可能受依赖、配置和导入异常影响，本次没有启动整个 KHunter 验证注册成功率。[注册器](https://github.com/ling-0729/KHunter/blob/main/strategy/strategy_registry.py#L179)

| 选股策略 | 数据与规则核对 | 借鉴判断 |
| --- | --- | --- |
| 金三角 | MA5/10/20 交叉顺序、MA60 方向、放量 | 可移植；与现有多头/金叉模式相近，新增价值在交叉时序 |
| 涨停回马枪 | 最近放量涨停、回调支撑、缩量和再次上涨 | 优先；需替换固定涨停阈值 |
| 启明星 | 三日阴线、小实体、阳线及量能 | 易移植，适合独立形态信号 |
| 多金叉共振 | MA、KDJ、MACD 在共振窗口内金叉 | 易移植，但多个技术指标不等于独立证据 |
| 多方炮 | 两阳夹一阴、缩量回调及放量确认 | 易移植，适合独立形态信号 |
| 阻力位突破 | 前 70 日平台、最高点至少距今 10 日、振幅和放量突破 | 优先；可与本项目平台突破做增量对比 |
| 仙人指路 | 前期长上影、趋势过滤，后续反包确认 | 可移植；交易信号必须标在确认日 |
| 龙头 | 严格第 2 板、早封板、换手、市值、温和放量 | 有条件；封板时间、炸板次数等需可靠历史数据 |
| 主升低吸 | 一拉、二调后，放量长阳突破反弹高点 R | 可研究；实际为突破确认，非回调日低吸 |
| 次新腰斩 | 上市以来 K 线不超过 120 根、最高价回撤至少 50% | 有条件；需完整上市历史，不能把截取窗口长度当股龄 |
| 超跌反弹 | 深度回撤、MACD 底背离和底部形态 | 暂缓原样复用；隔离实验发现倒序 EMA 问题 |
| 2560 | 突破 MA25、短长均量线交叉及放量上涨 | 易移植，规则简单但不构成收益证据 |

以上分别对应同名源码：[金三角](https://github.com/ling-0729/KHunter/blob/main/strategy/golden_triangle_strategy.py)、[回马枪](https://github.com/ling-0729/KHunter/blob/main/strategy/limit_up_pullback_strategy.py)、[启明星](https://github.com/ling-0729/KHunter/blob/main/strategy/morning_star.py)、[共振](https://github.com/ling-0729/KHunter/blob/main/strategy/multi_golden_cross.py)、[多方炮](https://github.com/ling-0729/KHunter/blob/main/strategy/multi_party_cannon.py)、[阻力突破](https://github.com/ling-0729/KHunter/blob/main/strategy/resistance_breakout.py)、[仙人指路](https://github.com/ling-0729/KHunter/blob/main/strategy/immortal_guidance_strategy.py)、[龙头](https://github.com/ling-0729/KHunter/blob/main/strategy/leader_strategy.py)、[主升低吸](https://github.com/ling-0729/KHunter/blob/main/strategy/main_uptrend_dip_buy_strategy.py)、[次新](https://github.com/ling-0729/KHunter/blob/main/strategy/new_stock_drawdown_strategy.py)、[超跌](https://github.com/ling-0729/KHunter/blob/main/strategy/oversold_rebound_strategy.py)、[2560](https://github.com/ling-0729/KHunter/blob/main/strategy/strategy_2560_selection.py)。

`strategy/disabled/` 另有 8 个直接继承策略类：底部趋势拐点、趋势加速拐点、涨停横盘、强势洗盘弱转强、趋势起点、W 底、金叉未绿、低位 TD9；根目录还有下划线开头的碗口反弹。这些不在上述扫描范围内，不能作为当前启用策略计数。不过超跌反弹仍复用了 disabled 中低位 TD9 的状态机，禁用注册不等于没有代码依赖。[目录](https://github.com/ling-0729/KHunter/tree/main/strategy/disabled)、[超跌依赖](https://github.com/ling-0729/KHunter/blob/main/strategy/oversold_rebound_strategy.py#L25)

择时工厂有 8 个分支：布林带、RSI、支撑位、海龟、低位海龟、海龟 plus、趋势回调缩量、顺势宝。它们包含持仓、加仓、卖出逻辑，不能只翻译成选股过滤器就声称完整复现。趋势回调缩量的首仓规则（趋势方向与 R²、乖离率、缩量、回撤约束）尤其适合研究；完整加仓部分需另外核对持仓状态契约。[工厂](https://github.com/ling-0729/KHunter/blob/main/trading/timing_strategies.py)、[缩量回调](https://github.com/ling-0729/KHunter/blob/main/trading/uptrend_pullback_strategy.py)

## 不能直接照搬的具体问题

1. **固定 9.5% 不是通用涨停定义。** 回马枪用 `close.pct_change() >= 0.095` 标记涨停。迁入本项目应使用原始价、当日涨跌停规则和 `limit_up_price`；形态和收益则保持一致复权口径。否则跨板块、ST、除权和无价格限制日会改变含义。[源码](https://github.com/ling-0729/KHunter/blob/main/strategy/limit_up_pullback_strategy.py#L108)、[本项目约束](../../../CONTRIBUTING.md)
2. **超跌反弹的 MACD 计算方向。** 基类 `execute_selection` 把输入规范为最新在前，超跌子类直接对该顺序 `ewm`。最新一行成为 EMA 的初值，DIF 和 MACD 为 0；若一次计算整段历史，旧行指标还会使用时间上更晚的数据。这是具体调用链的问题，不将其他所有策略或回测模式一并判定为前视。[基类](https://github.com/ling-0729/KHunter/blob/main/strategy/base_strategy.py#L143)、[指标方法](https://github.com/ling-0729/KHunter/blob/main/strategy/oversold_rebound_strategy.py#L84)
3. **突破策略带机器当前时间过滤。** 阻力突破中，最新样本日期距 `datetime.now()` 超过 5 年会直接返回空；相同历史输入可能随运行年份改变结果。迁入后停牌/退市判断应归核心按目标交易日处理。[源码](https://github.com/ling-0729/KHunter/blob/main/strategy/resistance_breakout.py#L163)
4. **主升低吸并非名称暗示的买点。** 源码要求阳线实体至少 5%、量比至少 1.8，并突破 R；局部高点需右侧 K 线确认。移植时不得把确认后才知道的高点回填成当时已知的信号。[源码](https://github.com/ling-0729/KHunter/blob/main/strategy/main_uptrend_dip_buy_strategy.py)
5. **原参数不是已证实的最优值。** 趋势回调源码注释提到按 117 笔样本分析调整过滤和退出参数。本次没有拿到可独立复现的对应行情版本、交易清单和样本外结果，因此不采纳注释中的收益描述为有效性证据。[源码](https://github.com/ling-0729/KHunter/blob/main/trading/uptrend_pullback_strategy.py)

## 实际完成的隔离实验

从超跌反弹文件 AST 中只提取 `calculate_indicators` 方法，用 pandas/numpy 构造 80 个日期顺序观测，价格为 `10 + sin(i / 3) + i * 0.04`，参数 12/26/9；未加载整个外部应用、未调用其数据源。

| 检查 | 实际结果 |
| --- | --- |
| 最新在前输入，最新行 DIF / MACD | `0.0 / 0.0` |
| 同一输入改成日期升序，最新行 MACD | `0.15405539` |
| 同一个历史日期，仅截至该日的倒序输入计算 MACD | `0.0` |
| 同一历史日期，在包含后续日期的倒序整段输入中计算 MACD | `0.00161567` |

实验验证了方法对倒序数据的非因果行为，不衡量策略收益，也不代表已运行 KHunter 全部测试。

## 本项目真实接入边界

- 自定义策略目录、保存校验、ID 冲突检查及重载已存在。可用独立 `custom_khunter_*` ID，通过已有资源导入流程安装，不绑定数据源、不改页面或核心引擎。[策略文档](../../strategy.md)、[保存入口](../../../backend/app/api/strategy.py)
- 单日规则使用 `filter`；多日形态使用 `filter_history` 并明确预热和依赖。历史过滤接收区间数据时必须按股票和日期保证因果性；不能只返回整个区间最后一日。[执行实现](../../../backend/app/strategy/engine.py)、[精简契约](../../../backend/app/strategy/prompts/strategy-guide-compact.md)
- 可直接生成买卖矩阵的策略另有 `matrix_native` 契约。可借鉴买卖条件，但持仓相关的海龟加仓不应在没有验证状态语义时被声称已经等价支持。[矩阵契约](../../../backend/app/backtest/matrix.py)
- 相近模式已有种子参考：平台突破、均线多头、缩量回踩、60 日新高。种子存在不代表用户当前已安装，也不代表公式完全相同。新装策略库为空，升级补种不会覆盖同 ID 用户文件。[种子迁移](../../../backend/app/strategy/strategy_seeds.py)、[平台](../../../backend/app/strategy/seeds/platform_consolidation_breakout.py)、[回踩](../../../backend/app/strategy/seeds/pullback_to_support.py)
- 选股信号和成交分开。日线收盘确认应按次日可成交条件验证，沿用 T+1、费用、滑点、涨跌停和停牌限制；不能把涨停收盘选中的股票当成当天可买入。[成交测试](../../../backend/tests/backtest/test_limit_up_close_fill.py)

判断优先级：涨停回马枪、趋势回调缩量首仓、阻力位突破最值得先做增量对照；主升低吸结构更复杂，作为后续研究候选；龙头精确版和次新策略必须先证明数据覆盖。启明星、多方炮、2560 可作为低成本规则参考，但本次无证据认为它们比现有模式收益更好。

“可用于交易研究”的最低证据应包含：固定样本规则断言、正反例与缺失数据、追加未来数据不改变历史信号、筛选/回测一致性，以及扣费并考虑不可成交后的样本外结果。比较多个策略时需保留未参与调参的时间段，并报告交易数、净收益、回撤、收益集中度和容量；本报告尚未完成这些收益验证。

## 来源与变更范围

KHunter 根许可证为 MIT，并声明其衍生自 a-share-quant-selector。若后续使用实质性源码，应保留相应版权和许可声明，不能把上游代码标为完全原创。[许可证](https://github.com/ling-0729/KHunter/blob/main/LICENSE)

本次仅新增研究结论并登记索引；没有修改策略、缓存、行情、API、前端和用户数据。未运行本项目 pytest 或前端构建，因为没有产品代码变更；没有导入策略，也没有获得回测收益结论。工作区原有修改全部保留。
