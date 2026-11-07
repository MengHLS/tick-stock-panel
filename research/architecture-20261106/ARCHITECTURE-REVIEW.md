# 威科夫日线研究模式独立架构评审与拟议接口契约

状态：架构设计提案，尚未实施。作者责任：系统架构师。检查日期：2026-11-06（北京时间）。

本评审独立读取项目实际代码，参考 `research/wyckoff-system-design-20261106/INTEGRATION-DESIGN.md`，不把开发设计当作现行接口。当前基线 HEAD 为 `848bd04b7266f6645fabdfdc4b2c0cdf404eb643`，分支 dev；工作区存在大量未提交修改，HEAD 不能代表被检查的全部内容。本文及同目录证据清单是本次唯一写入范围。

## 1. 架构结论及状态边界

采用独立后端扩展、纯规则计算模块和独立前端研究页。第一阶段只显示研究事件，默认关闭；规则与冻结验收样本交齐前，计算状态为 spec_missing。研究事件不自动变成可交易策略。后续才考虑统一策略提供者和现有回测链路，不新建撮合器。

生产源码 backend/app 和 frontend/src 的 .py/.ts/.tsx 文件逐行搜索 wyckoff/威科夫，本次未发现命中。这只支持该搜索范围尚无具名正式接入；不覆盖忽略目录、动态装载用户代码或其他成员尚未写入的交付。本次未创建正式规则、API、页面或策略注册。

独立于原设计的必要收紧：历史图表不能直接采用 StockDailyKChart 的独立行情查询。其后端读取链路实际存在不受请求历史 end 约束的实时蜡烛追加，不能仅以传入 dateRange 证明历史画面安全。首版应由研究接口返回与事件同源、同截止日、同 generation 的受控 candles，页面复用底层 EChartsCandlestick。若改用上层图表，必须先补出可验证的快照约束能力，届时另行评审。

## 2. 实际代码证据

行号来自检查时工作区，后续并行修改可能移动；同目录 EVIDENCE.json 记录关键文件 SHA-256。

| 模块 | 实际位置 | 已核对行为及架构影响 |
| --- | --- | --- |
| 扩展数据读取 | backend/app/extensions/contracts.py:87、:101、:109；adapters.py:164 | enriched range(start,end,symbols,columns) 返回 DataFrame 或 None；没有 asset_type 参数，首版只支持 stock。generation 接口允许 None，不能把未知当成可复现版本 |
| 请求期依赖 | backend/app/extensions/runtime.py:60 | ExtensionRuntime 包含 market_data/enriched_panel/backtest_results，没有 backtest_read。API 通过实际请求依赖获取只读服务，不从启动上下文猜字段 |
| 注册 | backend/app/extensions/registry.py:57、:92 | include_router 与 register_strategy_provider 是不同入口，研究路由无需策略注册；不订阅 quote observer、通知或监控规则 |
| 参考扩展 | backend/app/custom/strategy_research/__init__.py:9；frontend/src/custom/strategy-research/extension.tsx:7 | 已有扩展能注册独立路由和菜单，可参照形态，不能覆盖现有模块 |
| 历史策略 | backend/app/strategy/engine.py:1089、:1121 | filter_history_fn 先接收 history 计算，再按 date == as_of 筛输出。外层未在该分支替插件保证历史输入截断，插件须自行保证前缀不变性 |
| 回测 API | backend/app/api/backtest.py:350、:412 | StrategyBacktestRequest 和 /strategy/run 已存在，入场/退出填价可单独指定；不能将研究事件 JSON 直接传作策略信号 |
| 回测配置 | backend/app/backtest/strategy.py:709、:744 | matching 默认 open_t+1，entry_fill/exit_fill 为空时继承 matching；现有系统也支持 close_t，未来适配器必须显式校验，不能只依赖默认值 |
| 图表封装 | frontend/src/components/StockDailyKChart.tsx:28、:161、:163 | 有 markers/ranges/priceLines/dateRange；独立查询行情后直接转换 rows，无 generation 注入能力，无研究快照输入字段 |
| 底层图表 | frontend/src/components/EChartsCandlestick.tsx:31、:41、:48 | ChartMarker 仅 date/kind/label/above/color；范围 start/end，价格线 value 等。解释与失效详情必须在事件表展示 |
| 行情接口 | backend/app/api/kline.py:527、:550、:552、:563、:685 | 本地空数据时走同步拉取与 tail(days)，随后注入实时行；本地有数据也注入。注入函数按今日行覆盖或追加，没有请求 end 参数，历史日期约束不能据此保证 |
| 审计能力 | backend/app/backtest/evidence.py 的 audit_matrix/audit_frame/audit_trade_timing | 现有审计可复用，但不替代新状态机的全部逐日前缀验收 |

数据流：只读扩展适配器 → 有界数据快照/校验 → 纯规则状态机 → 研究事件和同源蜡烛 → 研究 API → 扩展页面/底层图表。未来可交易适配器只复用同一状态机，并走统一策略引擎 → 现有回测服务 → 现有撮合器。研究脚本、前瞻收益标签和数据提供商 SDK 不进入正式规则依赖链。

## 3. 模块责任与最小文件范围

| 交付方 | 可交付内容 | 放行边界 |
| --- | --- | --- |
| 量化研究员 | 冻结规则、公式/窗口/阈值/等号、状态与事件字典、失效/冲突/重入、参考脚本、版本化输入与逐日期望输出、独立研究验证 | 未交付精确规格不得代填常见参数；研究结论不等于系统已实现 |
| 系统架构师 | 依赖边界、事件/时间/API 契约、实施文件范围、兼容性与验收门槛 | 本次只写 architecture-20261106；不改正式源码或其他研究交付 |
| 系统开发工程师 | 生产计算、薄 API、前端、适配器与工程回归；逐条映射规格 | 对照冻结样本；不得以参考脚本直接替代正式集成与测试 |
| 独立审核工程师 | 独立核对实际 diff、样本、未来扰动、图表快照、回归与未解决问题 | 验收基于确切源码/数据版本；架构评审不能代替实现审核 |
| 行情数据工程师 | 数据口径、缺失与可用性、版本和质量证据 | 已在进行的行情审计更正由其原任务负责，本次不重派或覆盖 |

未来候选文件（当前未创建）：

- backend/app/custom/wyckoff_research/{__init__,models,routes,service,rules}.py；service 负责快照/缓存/校验，rules 为无 I/O 的确定性计算，routes 不直接访问仓库或供应商。
- backend/tests/test_wyckoff_research.py 及专用 fixtures：冻结样本、API/开关、时间/失效/缺数据测试。
- frontend/src/custom/wyckoff-research/{extension,Page}.tsx 及对应测试：页面、同源 candles、事件表。
- frontend/src/lib/api.ts、queryKeys.ts 仅最小类型/请求/查询键接线，两文件已有未提交改动，先协调当前维护者并复核最新 diff。
- 后续 strategy_provider.py 必须单独通过可交易规则验收后加入，第一阶段不创建。

第一阶段不需要改 main、核心策略引擎、撮合器、walkforward、行情 API、公共图表。发现现有接口无法支持时再提出有证据的核心修改，不能预先扩大文件范围。后端开关存放于扩展自己的配置读取层，缺省 false；具体与现有配置系统接线由开发检查确定，本文不虚构现有配置字段。

## 4. 拟议 API v1（不是现行接口）

路径沿用开发设计的候选：GET /api/custom/wyckoff-research/events。显式参数 symbol、start、end、as_of、rule_version；asset_type 固定 stock，timeframe 固定 1d。日期均 ISO YYYY-MM-DD，中国交易日口径；as_of 表示已完成的交易日收盘快照，不表示当天任意时刻。显式要求 start <= end <= as_of；预热区间由规则规格给出，显示区间不能改变事件身份或已有状态。服务器不能把盘中 as_of=今日当作完成日线，须返回可识别的不可用状态。实际交易日与完成状态依据需开发/数据方验证，不能仅用周一至周五推断。

响应顶层拟议字段：

| 字段 | 类型与语义 |
| --- | --- |
| schema_version | 固定字符串 wyckoff-research.v1 |
| status | ready / disabled / spec_missing / insufficient_data / data_unavailable / version_unavailable |
| reason_codes | 字符串数组，可机读原因；不以空事件掩盖缺数据 |
| meta | 请求参数、effective_as_of、rule_version、params_hash、data_generation、snapshot_id、price_basis、volume_unit、availability_basis、warmup_start、replay_origin、chart_state_as_of=end、event_state_as_of=as_of、as_of_cutoff_at |
| events | 从规格冻结的 replay_origin 至 as_of 的完整事件流，不按显示 start/end 裁剪；按 (knowledge_session,transition_order,event_id) 稳定排序；transition_order 由冻结规格及依赖拓扑确定 |
| candles | 与事件同一已验证快照的完成日线，限定显示区间；包含 date/open/high/low/close/volume，不注入实时行 |

事件范围与状态截止日：v1 选择返回从 replay_origin 到 as_of 的完整可知事件流，包括显示区间之前的确认和区间之后、as_of 之前的失效；所有 invalidates_event_id 及其他转移依赖必须在响应内闭合。replay_origin 是研究规格冻结的状态初始化起点，不随 start/end 改变；有限预热是否足以重建状态必须由规格与逐日样本证明，不能仅因预热数据齐全就假定此前无活动状态。未能证明完整重建时返回 insufficient_data，原因 STATE_HISTORY_INCOMPLETE；超过工程资源上限则明确拒绝，不静默截断事件或返回 ready。

图表只使用 knowledge_session <= end 的事件重建 end 收盘状态；逐根历史蜡烛 d 的状态仅折叠 knowledge_session <= d 的事件。marker 还须 confirmed_session 落在 candles 日期集合中；区间外依赖事件保留在事件表，不生成无对应蜡烛的标记。对于 end 之后才可知的事件，即使它的 confirmed_session 位于显示区间，也不得回填该历史图。事件表可展示截至 as_of 的完整事件，并显式标注“截至 as_of”，区分区间外依赖和 end 后事件；不得用该表的最终状态覆盖历史图。相同知识日内存在依赖时按规格转移顺序折叠，缺少确定顺序不得 ready。

HTTP 200 用于上述明确业务状态。请求格式/不支持资产/日期关系无效为 422；未知规则版本为 422 并给明确代码。数据读取中途换代为 409（DATA_GENERATION_CHANGED），服务异常为 500/503；错误不得返回 ready 或复用旧标记。最终错误模型需沿用实际项目统一错误结构，本契约只冻结原因语义，不杜撰既有 envelope。

disabled、spec_missing 在任何行情读取/规则执行前返回，events/candles 为空；后端直接调用也不能绕过。前端开关初始 false、关闭不查询；后端为 false 时前端开关不能开启服务。ready 且 events=[] 才代表快照可算但没有事件。generation 缺失不能 ready；返回 version_unavailable。range=None/空数据、缺少必要字段、预热不足须分清原因。

generation 读取前后相同只是检测换代，不构成数据库事务或真实历史时点版本证明。首版须冻结读取到的输入为同一内存快照，并记录快照内容摘要；若底层不能证明读取期间的一致性，则拒绝 ready，而不是声称两次 token 相同即可证明一致。snapshot_id 至少覆盖规范化输入内容、规则版本、参数及截止日；data_generation 指当前读取版本，不冒充历史当日可用数据版本。

数据读取/请求范围应有资源上限及超限错误，具体上限由开发基于现有护栏与性能证据确定，属于工程配置，不是研究阈值。缓存键包含 symbol/asset_type/timeframe/start/end/as_of/warmup_start/rule_version/params_hash/data_generation/schema_version；前端集中查询键覆盖请求全部维度，不复用仅 symbol 的键。切换查询时旧事件和蜡烛必须一起清空或明确标旧，不能新图配旧事件。

## 5. 事件身份、确认和失效时间

以下为架构字段建议，业务 event_type/state/condition 枚举由研究员冻结：

| 字段 | 约束 |
| --- | --- |
| event_id | 同一数据版本/规则/参数下确定生成；覆盖 symbol、事件类型、pattern_date、确认日及同日序号。不包含查询 as_of/start/end，扩大查询不能改变原事件 ID |
| symbol/asset_type/timeframe | 与 meta 一致；首版 stock/1d |
| rule_version/params_hash/data_generation | 必须可追溯到冻结规格与输入；不接受可变 latest 作为可复现规则版本 |
| pattern_date | 形态定位的交易日，允许早于确认日，仅作解释 |
| confirmed_session | 确认成立的完成交易日，也是图表 marker.date；不回填到 pattern_date |
| confirmed_at | 若有可靠时点证据为含 +08:00 的 ISO 时间；仅有日线时为 null，并使用 confirmed_session，不伪造收盘秒数 |
| available_at | 可靠历史发布/入库可用时间，否则 null；meta.availability_basis 明确为 session_close_assumption 或 verified_timestamp |
| knowledge_session | 最早可知交易日，不得早于 confirmed_session。verified_timestamp 模式按下文收盘截止公式映射，并要求 available_at <= as_of_cutoff_at；收盘假设模式按下文计算，available_at 为 null。两种模式均只返回 knowledge_session <= as_of 的事件 |
| transition_order | 同一 knowledge_session 内确定的非负整数顺序，满足依赖先于引用者；规则冲突顺序由研究员冻结，不使用 event_id 字典序替代业务顺序 |
| event_type/evidence | 业务字典来自研究规格；证据包含条件 ID、实际值、阈值引用、比较符、窗口起止和满足与否。缺必需值不生成已确认事件 |
| invalidates_event_id | 普通确认事件为 null；失效事件引用当时已存在的原事件 ID |
| invalidation_rule_id | 版本化失效规则标识；失效何时成立由规格决定，不能现场补阈值 |

首版若只有 session_close_assumption，只能宣称“按完成日线收盘假设的研究回放”，不能宣称真实历史数据当时已发布。若后续交易验证要求 verified_timestamp，缺失时应阻断该验证。confirmed_at 和 available_at 未知不能用当前请求时间填充。

时间映射：C(s) 表示交易日历及市场规则确定的交易日 s 收盘截止时点，带 +08:00 时区；它是回放边界，不是伪造的 confirmed_at。verified_timestamp 模式下，available_at 应反映所需输入全部可被所声明消费链路使用的最晚可靠时间，包含适用的发布与入库延迟，不能只选较早的供应商发布时间；依赖事件的知识时间也不能晚于当前事件。knowledge_session = min{s：s >= confirmed_session 且 C(s) >= available_at}，as_of_cutoff_at=C(as_of)。盘后、休市日发布或延迟入库均映射到满足条件的下一个收盘快照，不直接截取时间戳日期。若所需时间证据不全，不得标 verified_timestamp；只能显式使用 session_close_assumption，available_at 保持 null，knowledge_session 按冻结规则的完成日线确认及依赖顺序计算，且不得声称真实时点已验证。交易日历/截止时点无法确定则 data_unavailable，不猜测下一个工作日。

失效以追加事件表达，原确认记录保持不变；事件表状态由截至 as_of 已知的事件折叠得出，图表状态按上述 end/逐根日期截止规则折叠，不能存一个被未来覆盖的最终 invalidated 字段再回放过去。候选撤销、箱体更新、超时属于规则事件/转移，研究员未定义前不设计隐含迁移。跨数据 generation 重建属于修订快照，应明确显示版本改变，不与同版本内“未来扰动不改变过去”混淆。

纯时间示意（仅适用于收盘可知假设，不是威科夫交易规则；可靠时间模式以 knowledge_session 延后可见）：形态定位 t，规格要求在 t+k 收盘确认，失效发生 u>t+k。as_of<t+k 无确认；t+k<=as_of<u 只有确认；as_of>=u 才有指向原事件的失效。k、u 的判定均等待规格。标记放 t+k，失效标记放 u；历史区间 end/支撑阻力只能取当时已知边界。

契约验收示例（日期仅为时间关系示意，实际交易日由日历验证）：

- 确认 c 发生于显示 start 之前，失效 u 在 [start,end] 内且当时可知：events 同时返回 c 与 u，u.invalidates_event_id 可解析；图表只给 u 对应蜡烛加标记，初始活动状态可由 c 重建。
- end < u <= as_of：事件表可见 u，历史图在 end 仍保持失效前状态；将 as_of 延后而保持 end 不变，不能改变 end 当时的图表状态（同一数据版本与规则下）。
- t 日确认但 t 日 18:00 才可用，且 C(t) 早于 18:00：as_of=t 不返回该事件；最早在满足截止条件的下一交易日收盘快照返回。该事件不回填至 end=t 的历史图。
- 非交易日发布的数据进入下一满足 C(s)>=available_at 的交易日快照；若周五发布、下周一才完成适用入库，则以入库可靠时间重新映射，不能默认周五已可知。
- available_at 未知：保持 null，只能走已声明的收盘假设；要求可靠时间验证的用例应阻断。

后续若批准可交易适配：日线收盘确认不能据此在该形态日或同一根日线收盘成交；工程基线显式使用下一可交易时点 open_t+1，并验证停牌、涨跌停、T+1、整手、费用与现金限制。具体入场/退出、排序和持有规则仍由研究员交付；本提案不设策略参数或收益门槛。

## 6. 集成风险与阻断项

| 风险 | 证据/影响 | 解除条件 |
| --- | --- | --- |
| walk-forward 未定义变量 | backend/app/api/backtest.py:1443、:1506 引用 continuous_account，walkforward_stream 声明没有该参数；本次 Ruff 再现两个 F821 | 改动维护者修复并补正常成功路径 API 测试；阻断该路径集成验收，不代表所有回测都失败 |
| 历史图混入今日蜡烛 | kline.py:552、:563、:685 无请求截止日约束；空集回源分支也未按原历史区间重新过滤 | 首版研究接口同源 candles；或另审共享组件的快照能力并测试有数据/空集分支 |
| 多人未提交核心修改 | backtest engine/strategy/walkforward/API，行情服务、industry_chain、前端 api/queryKeys 均有修改；service.py 与 AnalysisPanel.tsx 被删除 | 保存确切 diff/文件摘要，协调文件维护者；本文不据 Git 状态推断作者，不覆盖或清理 |
| 连续账户改变回测语义 | strategy.py:739 的 carry_state/carry_out；API/前端有 walk-forward 参数改动 | 已有改动单独完成跨折持仓、现金、费用、无信号折及缓存键验收；威科夫接入不能吸收为自身实现 |
| 版本与真实时点 | generation 可为 None；未证明历史复权/数据发布时间存档 | 区分当前数据版本回放与真实历史时点验证，未知明确报告 |
| 必需研究规格尚缺 | 开发设计同样将精确规则与冻结样本列为前置项 | 研究员提供可执行定义和正反/边界/逐日样本后才实施正式规则 |
| 工作区格式问题 | git diff --check 退出 2，backend/tests/test_industry_chain_extension.py:808 文件末尾空行 | 原修改维护者处理；不修改他人测试文件 |

## 7. 可验收交付与实际运行结果

门槛 G0：研究员交付规则版本、数据口径、参数和状态/事件字典，冻结逐日输入及期望输出，说明未来可用性假设；未达到不得进入规则实施。

门槛 G1：开发交付独立模块、后端/前端双重默认关闭、版本化响应、同源蜡烛与事件，所有非 ready 状态明确区分。只有研究页验收，无可交易策略注册或通知接入。

门槛 G2：独立审核按确切源码摘要/数据 generation 重跑：每日前缀、追加/扰动未来、右侧确认延迟、确认后失效、同日冲突、阈值等号、缺数据/停牌、盘中未完成行、版本换代、开关绕过、空集回源、切换标的与日期、扩展失败隔离。逐日输出须与全量回算在同一快照上逐字段一致，不能只抽样看最终收益。

门槛 G3（后续）：研究员补完整交易规则与验证后，开发适配统一策略/回测，独立审核成交时点及风控、交易成本、连续账户/独立账户和缓存兼容。现有 F821 未解除前不得验收 walk-forward。研究显示通过不等于策略有效或盈利验证通过。

本次实际执行（backend/.venv/Scripts/python.exe，pytest 禁用 cacheprovider）：

| 命令/范围 | 本次结果 |
| --- | --- |
| -m pytest tests/test_extension_read_contracts.py tests/test_strategy_extension_contracts.py -q -p no:cacheprovider | 退出 0；27 passed，8.02 秒 |
| -m pytest tests/backtest/test_strategy_backtest_correctness.py -q -p no:cacheprovider | 退出 0；20 passed，22.50 秒 |
| -m ruff check app/api/backtest.py --select F821 | 退出 1；两个 continuous_account 未定义错误 |
| git diff --check | 退出 2；上述既有测试文件末尾空行 |

两组 pytest 有 anyio/pytest 与 asyncio fixture scope 弃用提示。测试证明当前受控样本的读取/策略扩展和回测正确性契约通过，不证明全工作区、实时系统、威科夫实现或真实数据质量已通过。未运行前端构建、浏览器联调、真实数据策略回测或完整 walk-forward；当前没有本次新增生产实现可供这些验收。

访问与工具限制记录：研究文件工具仅允许 research 与 docs/research；正式源码和规范通过正规代码执行环境只读检查。环境未找到 rg 可执行文件，改用 pathlib/re 逐行读取与搜索。初次 PowerShell 默认编码及 Python 默认输出编码导致中文不可读/UnicodeEncodeError，之后显式 UTF-8 重读；不以乱码内容推导结论。

## 8. 独立互核及契约修订记录

2026-11-06 独立审核工程师返回只读核对报告：方向与其检查的源码相符，同时指出事件范围/状态重建、可靠时间到知识日期映射两项 P2 歧义。架构师重新读取原文后确认遗漏，已在第 4、5 节补齐完整事件流及引用闭包、图表 end 与事件表 as_of 分离、收盘截止映射与跨区间/盘后/休市/入库延迟示例。上述修订属于契约设计，尚未经过实现测试，修订后的文本尚无第二次独立复核。

该审核报告还称独立复现实时行追加、重跑两项 F821 并核对原证据清单 22 个摘要；这是审核方报告，架构师本轮未重复运行这些检查，不把函数级复现表述为完整 HTTP 链路验收。第 7 节 27+20 项测试是架构师前轮实际运行记录，本轮仅修订文档，无新增源码测试通过声明。并行工作区仍未冻结，EVIDENCE.json 保留原检查时刻，不用新文档修订冒充全工作区重新取证。

未提交、部署、重启或交易；没有修改其他研究目录或生产源码。本文件是独立架构评审，不能用作开发或审核已完成的声明。
