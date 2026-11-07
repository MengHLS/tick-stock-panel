# 威科夫日线研究模式：系统接入设计

状态：设计提案，未实现。维护责任：系统开发工程师。检查日期：2026-11-06，北京时间。

基线 HEAD：`848bd04b7266f6645fabdfdc4b2c0cdf404eb643`，检查对象包含现有未提交修改，不能将 HEAD 单独当作本次测试基线。

## 1. 结论与职责

量化研究员负责规则定义、参考实现/研究脚本、冻结样本、独立验证和研究局限；系统开发工程师负责正式代码、API、页面、图表、回测适配和回归测试。参考研究代码不能直接作为正式系统交付。数据工程师负责数据质量及可用性；复盘工程师维护其独立复盘工具。

本次仅交付架构检查和接入设计，不修改任何正式信号，不选择威科夫交易参数，不宣称策略有效。首版目标为默认关闭的日线研究模式，研究状态显示确认时间、依据与失效条件。未完成规则与研究验收前，不注册可交易策略，不连接实时监控、通知、模拟跟单或真实交易。

已完整读取根目录 AGENTS.md、CONTRIBUTING.md、docs/secondary-development.md、docs/README.md。依文档维护规则，本次过程性设计保存在独立 research 目录，不修改现行功能文档及公共索引。

## 2. 实际代码证据与可复用接口

下列行号来自本次检查，后续并行修改可能使其移动。

| 层 | 实际文件与定义 | 接入结论 |
| --- | --- | --- |
| 行情读取 | backend/app/extensions/contracts.py:22，MarketDataRead.get_daily_batch/list_trading_dates；adapters.py:24 转发仓库读取 | 批量读取标准数据，不接供应商 SDK，不自行扫描 parquet |
| enriched | contracts.py:87，EnrichedPanelRead.range/data_generation；adapters.py:164 | 首版可用 range 获取指定股票日线 enriched；当前 range 无 asset_type 参数，首版限制 stock，不能假装支持 ETF/指数 |
| 请求期依赖 | backend/app/extensions/runtime.py:60，ExtensionRuntime.market_data/enriched_panel/backtest_results | API 使用 get_extension_runtime 注入；该请求期对象没有 backtest_read，不能按启动期 ExtensionContext 字段猜接口 |
| 启动期依赖 | contracts.py:204，ExtensionContext 包含 market_data/enriched_panel/backtest_read/backtest_results | 如确需后台任务，可使用实际启动钩子；首版不另建调度循环 |
| 后端扩展 | backend/app/extensions/registry.py:57 include_router；:92 register_strategy_provider | 独立源码扩展注册路由，不改 main.py；参考 custom/strategy_research/__init__.py:9 的 setup，但不修改该既有模块 |
| 策略定义 | backend/app/strategy/engine.py:152 StrategyDataContext；:195 StrategyDef；:343 provider 发现 | 规则冻结后走统一策略定义。不能把任意研究事件 JSON 直接当作交易信号 |
| 历史策略 | engine.py:1089-1123，先调用 filter_history，再筛选 as_of 行 | 输出日期过滤不能证明内部无未来信息；必须先在威科夫计算边界截断输入，并验证批量回算与逐日回放一致 |
| 策略扩展策略 | backend/app/extensions/strategies.py:40/52/65/89，CandidateFilter/ScoringPolicy/RiskPolicy/StrategyProvider | 仅过滤器不能实现完整形态状态机。优先独立纯计算模块，再由正式适配器复用，避免 UI/选股/回测各算一份 |
| 回测入口 | backend/app/api/backtest.py:350 StrategyBacktestRequest；:412 strategy_run | 复用现有 /api/backtest/strategy/run 和 worker/StrategyBacktestConfig，不另写撮合器 |
| 回测配置 | backend/app/backtest/strategy.py:709 StrategyBacktestConfig；:982 StrategyBacktestService | 现有参数区分 entry_fill/exit_fill；收盘确认研究信号的工程验收使用确认后的交易时点，不允许回填到形态发生日成交 |
| 证据 | backend/app/backtest/evidence.py:154 audit_matrix、:256 audit_frame、:343 audit_trade_timing | 复用前缀截断/未来扰动和交易时间证据；现有抽样审计不能替代威科夫确定性逐日验收 |
| 图表 | frontend/src/components/StockDailyKChart.tsx:28 Props 有 markers/ranges/priceLines/dateRange；:160 查询共享 K 线 | 首版独立扩展页复用图表，确认日作为 marker.date；不需要先改公共图表源码 |
| 标记结构 | frontend/src/components/EChartsCandlestick.tsx:31 ChartMarker 仅 date/kind/label/above/color | 完整研究依据、确认时间和失效条件由页面事件表承载；不能假设已有自定义 tooltip 元数据或 marker 点击回调 |
| 前端扩展 | frontend/src/custom/strategy-research/extension.tsx 已实际注册静态路由和菜单 | 可参照注册形态建立独立扩展页，不复制现有研究页或回测页 |

在 Git 跟踪及非忽略的 backend/app、frontend/src、docs、research 文本文件中搜索 wyckoff/威科夫（排除两个并行工作目录），未发现命中。该结果不覆盖被 Git 忽略的用户策略/数据，也不能证明其他成员尚未写入的研究交付不存在。

## 3. 最小实施范围及文件归属

首版采用 L2：独立后端扩展 + 独立前端页面，复用既有组件及读取接口。下表是未来候选文件，不表示已创建。

| 文件范围 | 责任与用途 | 写入条件 |
| --- | --- | --- |
| backend/app/custom/wyckoff_research/__init__.py、routes.py、service.py、models.py、rules.py | 系统开发：注册、薄 API、只读编排、版本化契约、纯规则计算 | 规则及样例冻结后创建；修改前复查目录是否已被占用 |
| backend/tests/test_wyckoff_research.py 与专用 fixtures | 系统开发：API、时间语义、边界、失效与缺数据验收 | 样例来自研究员冻结交付，不自造关键交易规则 |
| frontend/src/custom/wyckoff-research/extension.tsx、Page.tsx 及测试 | 系统开发：默认关闭开关、事件表、确认日图表标记 | 沿用注册和现有视觉体系 |
| frontend/src/lib/api.ts、queryKeys.ts | 系统开发的最小请求/类型及集中查询键接线 | 两文件已有他人改动，归属未确认；实施前先核对最新差异并协调，禁止覆盖 |
| backend/app/custom/wyckoff_research/strategy_provider.py | 后续正式策略适配，复用同一 rules 计算 | 只有研究员给出明确入场、出场、排序、风控和独立验证后才接入 |
| 既有 strategy/engine、backtest/engine、strategy、walkforward、api/backtest、main、router、公共 K 线组件 | 首版原则上无需修改 | 若真实契约无法表达需求，再单列 L3 改动与兼容回归；不能预先改大类 |

本次唯一新增文件为本设计文档。以下目录和对应 docs/research 目录均不修改：parallel-review-20261106、parallel-data-20261106。既有 strategy_research、industry_chain、研究员参考脚本和其他研究成果也不覆盖。Git 状态不能证明具体作者，本次不推断已有修改归属。

## 4. 拟议事件与 API 契约（尚不存在）

拟议只读接口：`GET /api/custom/wyckoff-research/events`，参数为 symbol、start、end、as_of、rule_version。首版仅 stock、1d，范围和回溯上限在实现时按既有 API 约束设置；缺少规则版本或未启用时返回明确状态，不能默认为有效交易信号。

事件最小字段：event_id、symbol、asset_type、timeframe、rule_version、params_hash、data_generation、as_of、pattern_date、confirmed_at、available_at、event_type、evidence、invalidation_rule。事件类型枚举须等研究规格确定。evidence 应含条件名、实际观测值、比较阈值及所用窗口，值缺失时标为不可计算。

pattern_date 仅表示形态位置；confirmed_at 表示可确认时点；available_at 表示数据实际可用时点。日线资料没有真实发布时间时必须明确这种限制，不能伪造精确到秒的历史可用性。截止 as_of 只能输出当时可知信息。后续失效采用独立失效事件关联原事件，不把未来的 invalidated 状态、失效日期或最终区间边界提前写进旧快照。

图表研究标记用 neutral，marker.date 为确认日，标签名称以研究规格为准；形态日期在事件表展示。不得因后续确认把买卖箭头倒标到历史极值。range 如需展示，只能使用该 as_of 当时已知的边界；不能回放时使用未来完成的区间。明确区分研究中、候选、已确认和已失效，枚举和迁移条件等待研究员冻结。

输出元信息至少区分 disabled、spec_missing、insufficient_data、ready 和 error。字段、价格复权或必要交易日缺失时拒绝计算相应事件，不能返回零分或虚假“无形态”。上述名称为设计建议，当前没有这些返回字段。

前端开关初始关闭；关闭时查询不发起。指定历史日期时，图表和计算共用截止日期，排除盘中未收盘 K 线。StockDailyKChart 通过现有 K 线接口读取，实施时须测试当日 live candle 注入、未来日期过滤和复权版本一致性，不能只约束事件查询。若该组件无法保证研究快照，应使用共享底层 EChartsCandlestick 渲染同一受控快照，不复制图表实现。

## 5. 数据、缓存与无未来信息约束

- 价格、成交量和窗口必须由研究员明确。enriched 的 OHLC 为前复权，raw_* 为原始价；涨跌停和可成交判断遵守原始价规则。历史 ST、上市期、停牌、缺量与缺历史处理不得猜测。
- 数据在计算入口按 symbol/date 排序、去重校验并截断到 as_of；仅完成的日线可确认。状态机逐交易日推进，禁止全样本极值或后续标签改变历史确认记录。
- 复权数据重建可能改变早期数值；冻结数据版本或记录 generation，避免把重算变化说成原历史时点信号。当前数据是否完整具备时点版本并未验证。
- 不把前瞻收益、未来 MFE/MAE 或完整形态结束日期放进特征。backtest/strategy.py:2815 的负 shift 在候选后收益统计路径，不据此单独认定信号泄漏；需检查使用边界。
- 初版不增加持久化事件库或后台扫描，优先有界批量读取与按需计算。后续若引入缓存，键覆盖 symbol、asset_type、timeframe、as_of、范围/预热长度、rule_version、params_hash、data_generation。前端集中查询键同样覆盖这些维度。
- 每次请求应绑定同一数据 generation；读取前后换代则重试或返回明确状态，不能混合新旧数据。参数或规则版本变化同时使研究查询和后续策略矩阵缓存失效。
- 不在行情回调线程计算日线全历史；不自动创建监控规则、通知或跟单。

## 6. 研究员必须交付的规格

| 必须冻结的内容 | 必须能回答的问题 |
| --- | --- |
| 范围和数据 | 股票池、历史成员、资产类型、日线口径、复权、量价单位、ST/退市/新股排除及交易日定义是什么？ |
| 状态及事件定义 | 首版究竟包含哪些阶段和事件？每个条件的公式、窗口、阈值、严格/包含等号、最短历史是什么？概念名不足以实现 |
| 区间与极值确认 | 箱体/趋势/支撑阻力如何形成和更新？若需右侧若干根确认，何日才可输出？历史候选是否允许撤销，怎样留痕？ |
| 同日冲突和重入 | 多个阶段/事件同日满足时的优先级、去重、冷却、重复进入、超时和失效条件是什么？ |
| 输出与解释 | 每事件证据字段、形态日、确认日、可用时间、失效原因和边界变化的期望值是什么？ |
| 可交易规则（后续） | 哪个确认事件转入场/退出？仓位、排序、并列决策、止损、持有期、跳空及不可成交如何处理？未交付则只做研究显示 |
| 参数与验证 | 固定参数或搜索区间、参数冻结日期、训练/验证/样本外划分、成本假设、基准、失败定义及局限是什么？ |
| 可复现实验 | 数据来源/区间/generation、规则版本、脚本命令、固定输入与逐行期望输出、独立验证报告是什么？ |

研究员可在其独立研究目录提交规则说明、JSON/CSV 验收样本及参考脚本；系统实现不能让研究脚本反向依赖或写入正式运行环境。关键规则缺失时不采用“常见威科夫参数”补齐。

## 7. 验收样例和工程门槛

以下是应由研究员提供数值和期望结果的场景，尚非已完成测试：

1. 正例：逐根日线从候选到确认，逐日给出状态、证据和 confirmed_at；确认前所有截止日期均无已确认事件。
2. 近似反例：仅一个阈值不满足、不满足最短窗口、等于边界，明确是否触发。
3. 失效/冲突例：确认后失效、同日冲突、重复确认、冷却后重入；历史 as_of 查询不出现未来失效状态。
4. 右侧确认例：形态日在 t，确认为 t+k，t 至 t+k-1 无已确认标记，t+k 标记留在确认日；k 由规则决定。
5. 未来扰动例：对 t 之后价格和成交量作大幅扰动、截断或追加，t 及之前已知输出保持一致；全量向量计算与逐日回放相同。
6. 数据异常例：停牌、复权换代、重复日期、缺 OHLCV、空集、历史不足、盘中未完成日线、股票切换；区分无事件与不可计算。
7. 后续交易例：确认日与成交日分离、下一交易日缺行情、涨跌停不可成交、T+1、整手/现金、费用滑点、退出信号；日线不得宣称触发瞬间成交。
8. API/前端例：默认关闭无计算；启用后的空/错/加载/缺规格；切换标的/日期不显示旧标记；旧结果缺新增字段可读取；扩展注册冲突和异常隔离。

后续系统实现最低验证：专用纯规则与 API 测试、现有读取/策略扩展契约、受影响回测模块、前端组件测试与 pnpm build、图表日期联调。研究员另用冻结样本和独立实现核对输出，测试通过不等于盈利验证。

## 8. 已有未提交修改风险与实际检查结果

工作区起始有 40 个已跟踪文件修改/删除及多批未跟踪成果，涉及 backtest/engine.py、strategy.py、walkforward.py、api/backtest.py、行情新鲜度、industry_chain 和 frontend api/queryKeys。不得把这些改动算作威科夫实现。

已检查的核心差异包括：PortfolioCarryState、SimulationOptions.carry_in/carry_out、StrategyBacktestConfig/result 结转字段、空信号折的连续账户处理、交易日 fold 与前端 walk-forward 参数。它们改变撮合、跨折持仓和缓存键，是后续回测集成的兼容性复核点；本次没有对这些改动做完整审查，也未确认文件作者。

确认的问题：backend/app/api/backtest.py:1443 和 :1506 引用了 continuous_account，但 walkforward_stream 参数列表未声明该变量。定向 Ruff F821 实际返回两个错误（退出码 1）。正常执行经过相应表达式有 NameError 风险，应由该改动负责人修复，并补正常成功路径 API 测试后再接入威科夫 walk-forward。本次保留原文件，未修复。

执行命令及真实结果（在 backend 目录用已有 .venv/Scripts/python.exe）：

| 检查 | 结果 |
| --- | --- |
| -m pytest tests/test_extension_read_contracts.py tests/test_strategy_extension_contracts.py -q -p no:cacheprovider | 退出码 0，27 passed，5.09 秒 |
| -m pytest tests/backtest/test_strategy_backtest_correctness.py -q -p no:cacheprovider | 退出码 0，20 passed，20.66 秒 |
| -m ruff check app/api/backtest.py --select F821 | 退出码 1，以上两处未定义变量 |
| git diff --check | 退出码 2，已有 backend/tests/test_industry_chain_extension.py:808 文件末尾多余空行 |

两组 pytest 均有既有 pytest/anyio 弃用提示。测试使用受控样本，只证明现有扩展/回测契约在当前环境的结果，不证明真实数据完整、威科夫规则可用或整个工作区通过回归。未运行前端构建、真实数据回测、完整 walk-forward 或浏览器联调，因为本次没有实现页面/信号。

访问记录：受限文件读取器直接读取根目录 AGENTS.md 返回 outside allowed directories；随后通过正规代码运行环境读取实际文件成功。尝试读取 frontend/src/extensions/loader.ts 返回 ENOENT，实际扩展目录存在 bootstrap.ts、runtime.tsx、registry.ts 等，未据不存在的 loader 推导接入。

未执行提交、部署、重启、购买或交易。相关自动任务检查结果为本机器人没有自动任务。
