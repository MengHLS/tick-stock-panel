# 威科夫量价分析外部复用核验（收敛版）

- 核验日期：2026-11-08（Asia/Shanghai）。
- 范围：仅外部原始资料与可核验开源仓库；不重复分析本仓库现有实现，不修改产品代码，不安装依赖，不复制大段第三方代码。
- 证据口径：`已核验` 指本次直接读取到原文、源码片段或 GitHub 元数据；`工程判断` 指基于这些证据的适用性推断；`未核验` 不作事实陈述。
- 收敛结果：最多 3 个来源。没有证据支持“存在一个已完整审计、可直接整体搬用、无未来函数且适配 A 股日线”的开源威科夫引擎。

## 最终推荐

| 排名 | 来源 | 已核验价值 | 建议复用形态 | 主要限制 |
| --- | --- | --- | --- | --- |
| 1 | StockCharts ChartSchool 威科夫教程 | 三定律、价格循环、吸筹/派发事件与 A–E 阶段、相对强弱、九项买卖测试、P&F 目标计数 | 复用概念、事件词表、判定清单；独立实现 | 教学示意图不是因果算法；Spring/UTAD 并非必需事件；文本/图示授权未核验 |
| 2 | Wyckoff Analytics 官方英文 PDF | 官方教学口径；确认与 StockCharts 教程同源且经许可转载 | 校准术语与阶段定义，避免把变体画法当硬规则 | 与来源 1 内容同源，不算独立算法证据；无算法源码 |
| 3 | YoungCan-Wang/WyckoffTradingAgent | A 股日线威科夫漏斗、结构触发、交易区间识别、观察-only 结构影子与测试文件 | 借鉴 A 股日线观察池、结构影子、排除当日边界的工程思路；小粒度独立重写 | AGPL-3.0；只完成部分源码核验；不能认证无未来函数/无重绘；阈值是作者启发式 |

## 1. StockCharts ChartSchool：概念与判定清单的首选

原始 URL：[The Wyckoff Method: A Tutorial][S1]。

| 核验项 | 结论 | 证据 |
| --- | --- | --- |
| 算法是否真有实现 | 否。页面是教程、示意图与规则说明，不是可执行识别器 | 页面正文为法律、阶段、事件、测试与 P&F 计数指南 [S1] |
| 许可证 | 未核验到开源代码授权；不按可搬运源码处理 | 本次只核验教程内容，未核验 StockCharts 文本/图示再利用条款 [S1] |
| 维护状态 | 当前站内教程可访问；署名 Roman Bogomazov、Michael Lipsett，示意图经 Henry O. Pruden 编辑；页面显示相对更新时间，不据此推断精确版本日期 | 教程署名与页脚 [S1] |
| A 股日线适用性 | 工程判断：可作为股票量价结构词表；原文称方法适用于存在大型机构交易者的自由交易市场，但未验证 A 股 T+1、涨跌停、停牌、复权与交易日历 | 适用范围说明 [S1] |
| 未来函数 | 无代码可审计。示意图是事后教学结构，不能直接当作盘中/收盘因果信号 | Accumulation/Distribution Schematics 与阶段说明 [S1] |
| 主观标注 | 高。原文明确 Accumulation Schematic 1 有 Spring、Schematic 2 无 Spring；Distribution Schematic 1 有 UTAD、Schematic 2 无 UTAD；无 Spring 时 Phase C 识别可能困难 | 事件变体与 Phase C/D 说明 [S1] |

最值得借鉴的内容：

- 三定律：供需决定方向；因果用横盘 P&F 计数估计后续目标；努力与结果用量价配合/背离观察转折。[S1]
- 吸筹 Phase D 的量价特征：上涨扩散放量、回调缩幅缩量；SOS 后出现 LPS 才强化结构判断。[S1]
- 派发侧 SOW/LPSY：跌破或测试支撑后弱反弹，说明需求不足或供给仍重。[S1]
- 九项买卖测试包含相对市场强弱、量价活动、趋势线突破、高低点结构、横向基底与风险收益比；其中部分测试依赖 P&F，不能假装日线 OHLCV alone 能完整覆盖。[S1]

复用边界：借鉴概念和检查清单，不复制原文段落或示意图；若产品需要图示，应基于自有数据重绘，并另行核验素材授权。

## 2. Wyckoff Analytics 官方 PDF：术语校准，而非独立算法来源

原始 URL：[Wyckoff-Method-Wyckoff-Analytics-English-V2.pdf][S2]，入口页为 [Wyckoff Method][S2-page]。

| 核验项 | 结论 | 证据 |
| --- | --- | --- |
| 算法是否真有实现 | 否。本次下载并解析到 20 页教学 PDF，内容为方法、示意图、定律、阶段、事件与测试 | PDF 正文与目录 [S2] |
| 许可证/来源 | PDF 第 1 页声明大部分内容原为 Wyckoff Analytics 团队给 StockCharts ChartSchool 撰写，并经 StockCharts.com 明确许可转载 | PDF 第 1 页 disclaimer [S2] |
| 维护状态 | PDF 元数据：CreationDate 2019-05-17，ModDate 2022-06-22；URL 位于官方 `/wp-content/uploads/2022/06/` | 本次解析的 PDF 元数据；原始文件 [S2] |
| A 股日线适用性 | 工程判断：可用于统一中文产品术语背后的英文定义；不提供 A 股交易制度适配证据 | PDF 适用范围与 StockCharts 同源说明 [S2] |
| 未来函数/主观标注 | 与来源 1 相同：教学示意图和阶段划分不是可执行因果算法；不能把事后完整结构回填为历史买点 | 同源教程性质 [S1][S2] |

复用价值：作为官方口径校准材料，确认 Composite Man、价格循环、吸筹/派发事件与阶段不是某个 GitHub 作者自造词。它不应被计为与 StockCharts 相互独立的实证证据。

## 3. YoungCan-Wang/WyckoffTradingAgent：A 股日线工程思路候选，不是已认证引擎

固定核验版本：`be9e2f582103376923ad2a3dc84e763079dbcf08`。仓库：[GitHub][S3]；提交：[commit][S3-commit]。

| 核验项 | 结论 | 证据 |
| --- | --- | --- |
| 算法是否真有实现 | 部分已核验为真。读取到 `core/wyckoff_structure.py` 的交易区间、Spring/LPS/SOS/EVR 触发与结构影子源码片段；`core/wyckoff_engine.py` 含五层漏斗、Spring 与 Accum_A/B/C 规则片段 | [structure.py][S3-structure]、[engine.py][S3-engine] |
| 测试 | 测试文件存在；读取到结构测试断言 `mode == "observation_only"`、`affects_formal_selection is False`。本次未运行测试 | [test_wyckoff_structure.py][S3-test] |
| 许可证 | GitHub 仓库元数据标示 `AGPL-3.0`，固定版本 README 的 License 段也链接 AGPL-3.0；tree 中存在 `LICENSE`。本次未逐字核验 LICENSE 全文 | [仓库元数据][S3-api]、[README License][S3-readme-license] |
| 维护状态 | 默认分支 `main` 所查提交时间为 2026-11-04T13:44:21Z；仓库 `pushed_at` 为 2026-11-07T11:04:44Z；`archived=false`。`pushed_at` 不等于主分支实质代码提交时间 | [仓库元数据][S3-api]、[提交元数据][S3-commit-api] |
| A 股日线 | README 明确描述 A 股日线行情、威科夫结构识别、漏斗选股与形态复盘；引擎 docstring 含 ST/板块/市值/成交额过滤和 Spring/SOS/LPS/EVR | [README][S3-readme]、[engine.py][S3-engine] |
| 未来函数 | 不能认证。已核验到局部因果防护，但关键摆动点函数与完整回测链路未审计 | 见下方源码证据与未核验项 [S3-structure][S3-engine] |
| 主观标注 | 已核验核心片段是确定性阈值打分，不是纯 LLM 包装；阈值选择仍是作者启发式。图表标注/复盘/AI 研报是否主观回填未核验 | [structure.py][S3-structure]、[engine.py][S3-engine] |

已核验源码事实：

- `identify_trading_range` 默认 `lookback=90`、`swing_window=3`、`exclude_last=1`；docstring 说明默认排除最后一根，是为了让触发检测用“今天收盘前已可见的区间”对比当日。[S3-structure]
- `_range_zone` 在 `exclude_last > 0` 时执行 `iloc[:-exclude_last]` 后再取窗口。[S3-structure]
- 结构触发含硬阈值：SOS 片段要求收盘接近/突破阻力、`last_pct >= 6.0`、量比 `>= 2.0`；Spring 片段要求低点刺穿支撑约 0.5%、收盘收回支撑上方约 0.5%、仍处区间中下部且量比达配置值。这些是作者规则，不是 StockCharts 原文给出的普适常数。[S3-structure]
- `build_structure_shadow` 比较结构信号与正式 Layer 4 信号；测试断言结构独有信号保持 observation-only，不影响正式选择。[S3-structure][S3-test]
- 引擎 `_recent_sequence_events` 片段使用 `iloc[:-1]` 取此前序列；`_detect_spring` 注释说明支撑位不应包含正在跌破测试的前一日。[S3-engine]

工程判断：

- 适合借鉴为“A 股日线候选/观察池 + 结构证据影子”，不适合直接当作已验证买卖点引擎。
- `exclude_last=1` 是正确方向，但不足以证明无未来函数：`swing_values` 来自未读取的 `core/_price_math.py`；若摆动点用双侧窗口确认，历史标注仍可能回填或延迟确认。
- 6% 涨幅、2 倍量、0.5% 刺穿/收回等阈值必须用 A 股日线固定样本、不同涨跌停制度和前缀稳定性测试重新验证，不能原样宣称为威科夫标准。
- AGPL-3.0 代码不宜直接搬入产品；建议只借鉴思想并独立实现。若复制/改编代码，先做许可证兼容审查。
- React 图表面板与标注链路只可作为 UI 参考；本次未完整核验其交互、因果性或许可边界。

## 对 A 股日线页的收敛建议

1. 用 StockCharts/Wyckoff Analytics 统一事件与阶段词表：TR、PS、SC、AR、ST、Spring/Test、SOS、LPS；派发侧 PSY、BC、UT/UTAD、SOW、LPSY。Spring/UTAD 必须是可选变体，不是必填字段。[S1][S2]
2. 把“量价努力/结果”和“相对市场强弱”做成可解释证据，而不是只输出一个阶段标签；P&F 目标计数单列为未实现/需额外图表契约的能力。[S1]
3. 借鉴 YoungCan 的观察-only 结构影子：新结构识别先与既有正式选择隔离，记录分歧，不直接提升为交易信号。[S3-structure][S3-test]
4. 因果性验收必须独立做：逐交易日前缀重算比较历史标签是否变化；区分事件发生日、确认日、可成交日；日线收盘信号不得声称盘中即时成交；覆盖 T+1、涨跌停不可成交、停牌缺口、复权边界与交易日历。
5. UI 只参考“区间边界 + 事件标记 + 证据/反证 + 确认状态”的信息组织；不复制第三方示意图、文案或 AGPL 组件代码。

## 未核验项与访问阻塞

- YoungCan：未完整读取 `core/_price_math.py`、完整 `wyckoff_engine.py`、回测/走步验证、前端标注与 AI 研报链路；未运行其测试；未做 A 股样本实证。因此“无未来函数”“无重绘”“可直接交易”均未成立。
- YoungCan：GitHub raw 域名本次访问被重置；部分 GitHub API 请求返回 504。已核验内容来自可访问的 GitHub blob 页面、仓库元数据与提交元数据，不来自本地猜测。
- 其他 GitHub 候选：源码 blob 读取被重置/超时/中断，算法、因果性与许可证全文未核验；不计入三个推荐来源，也不作可复用事实。
- StockCharts/Wyckoff Analytics：未核验文本与图示的商业再利用授权；本报告只复用概念，不复制素材。
- 本任务没有安装依赖、没有运行产品测试、没有修改产品代码；完成标准是外部来源核验与本报告落盘，不是算法上线验收。

## 原始 URL

[S1]: https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial
[S2]: https://www.wyckoffanalytics.com/wp-content/uploads/2022/06/Wyckoff-Method-Wyckoff-Analytics-English-V2.pdf
[S2-page]: https://www.wyckoffanalytics.com/wyckoff-method/
[S3]: https://github.com/YoungCan-Wang/WyckoffTradingAgent/tree/be9e2f582103376923ad2a3dc84e763079dbcf08
[S3-api]: https://api.github.com/repos/YoungCan-Wang/WyckoffTradingAgent
[S3-commit]: https://github.com/YoungCan-Wang/WyckoffTradingAgent/commit/be9e2f582103376923ad2a3dc84e763079dbcf08
[S3-commit-api]: https://api.github.com/repos/YoungCan-Wang/WyckoffTradingAgent/commits/main
[S3-readme]: https://github.com/YoungCan-Wang/WyckoffTradingAgent/blob/be9e2f582103376923ad2a3dc84e763079dbcf08/README.md
[S3-readme-license]: https://github.com/YoungCan-Wang/WyckoffTradingAgent/blob/be9e2f582103376923ad2a3dc84e763079dbcf08/README.md#license
[S3-structure]: https://github.com/YoungCan-Wang/WyckoffTradingAgent/blob/be9e2f582103376923ad2a3dc84e763079dbcf08/core/wyckoff_structure.py
[S3-engine]: https://github.com/YoungCan-Wang/WyckoffTradingAgent/blob/be9e2f582103376923ad2a3dc84e763079dbcf08/core/wyckoff_engine.py
[S3-test]: https://github.com/YoungCan-Wang/WyckoffTradingAgent/blob/be9e2f582103376923ad2a3dc84e763079dbcf08/tests/core/test_wyckoff_structure.py
