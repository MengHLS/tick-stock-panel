# 威科夫页面：本仓库复用核对

状态：只读调研，未修改产品代码，未运行测试或构建。核对日期：2026-11-08，北京时间。

## 已确认存在的接入设计

- `research/wyckoff-system-design-20261106/INTEGRATION-DESIGN.md` 已提出默认关闭的日线研究模式、只读事件 API、前后端源码扩展目录和事件时间字段；文档明确标注“未实现”。
- 该设计禁止把概念名直接当成交易规则，要求先冻结事件、窗口、阈值、确认日、失效与冲突口径；首版不接监控、通知、模拟跟单或真实交易。
- 当前 `frontend/src` 与 `backend/app` 未搜索到 Wyckoff 页面或事件实现，不能把设计提案当成已有 API。

## 可直接复用的前端能力

| 能力 | 代码证据 | 复用方式 |
| --- | --- | --- |
| 源码级页面注册 | `frontend/src/custom/stock-analysis/extension.tsx:8`、`frontend/src/custom/strategy-research/extension.tsx:8` | 新建独立扩展清单，懒加载页面；不改核心路由。 |
| 股票搜索与最近标的 | `frontend/src/custom/stock-analysis/Page.tsx:6`、`:35`、`:49` | 复用 `StockFinancialSearch`、`LastStockChip`、`useLastStock`。 |
| 日 K + 成交量 + 事件图层 | `frontend/src/components/stock-analysis/AnalysisKChart.tsx:80`、`:93`、`:206`、`:216` | 已有 `markers`、`ranges`、`onDateClick`，可承载事件标记和区间高亮。 |
| 带日期边界的日 K | `frontend/src/components/StockDailyKChart.tsx:28`、`:158`、`:161` | 已有 `dateRange`、`markers`、`ranges`、`priceLines`；研究快照须验证 live candle 注入与截止日过滤。 |
| 底层 K 线渲染 | `frontend/src/components/EChartsCandlestick.tsx:31`、`:41`、`:48` | 若上层组件无法满足研究快照，复用底层渲染同一受控数据，不复制图表。 |
| 共享查询 | `frontend/src/custom/stock-analysis/Page.tsx:178`、`:191`、`frontend/src/lib/queryKeys.ts:154`、`:161` | 沿用 `QK.kline`、`QK.stockLevels`；新增事件键必须集中维护。 |
| 研究页形态 | `frontend/src/custom/strategy-research/Page.tsx:68` | 参考只读研究页的页头、空态和事件表组织，不复制其业务逻辑。 |
| 主题 | `frontend/src/index.css:11`、`:30` | 使用现有暗/亮主题变量；A 股红涨绿跌，不引入另一套配色。 |

## 可直接复用的后端能力

| 能力 | 代码证据 | 复用方式 |
| --- | --- | --- |
| 后端扩展路由 | `backend/app/custom/strategy_research/__init__.py:9`、`backend/app/extensions/registry.py:57` | 通过 registrar 注册只读 router，不改 `main.py`。 |
| 请求期读取面 | `backend/app/extensions/runtime.py:60`、`:204` | 使用 `get_extension_runtime`，不直接访问 `app.state` 或具体 repository。 |
| 标准日线与交易日 | `backend/app/extensions/contracts.py:22` | 使用 `MarketDataRead.get_daily_batch`、`list_trading_dates`，不绑定供应商 SDK。 |
| enriched 与 generation | `backend/app/extensions/contracts.py:87` | 使用 `EnrichedPanelRead.range`、`data_generation`；当前 `range` 无 `asset_type` 参数，首版不能宣称支持 ETF/指数。 |
| 筹码密集区 / POC | `backend/app/indicators/levels.py:62` | 可作为区间证据参考；它是换手率衰减筹码模型，不等同于无衰减 Volume Profile。 |
| 前高前低与 swing | `backend/app/indicators/levels.py:219` | 可复用局部转折思想；现有 swing 使用左右窗口，研究输出必须换算到右侧确认日。 |
| 均量、量比、ATR | `backend/app/indicators/pipeline.py:442`、`:448`、`:501` | 复用已有指标列；量比分母为前 5 日均量，盘中含时间折算，不能直接当历史收盘量比。 |
| 北京交易日边界 | `backend/app/api/stock_analysis.py` 的 `cn_today()`、`backend/tests/test_stock_analysis_beijing_today.py` | 沿用北京日期口径，并补 `as_of` 截断测试。 |

## 不能直接照搬的部分

- `compute_levels` 是“当前关键价位”摘要，不是威科夫状态机；不能把 POC、前高前低直接标成吸筹/派发。
- `AnalysisKChart` 的 marker 只有日期、标签、颜色、位置；完整证据、确认时间和失效条件应放在事件表或新增受控契约中，不能假设已有自定义 tooltip。
- `StockDailyKChart` 会合并涨跌停标记并读取行情；历史研究模式必须验证外部 `dateRange` 能排除未来 K 线和当日未完成 K 线。
- 现有 `vol_ratio_5d` 的盘中折算适合实时看盘；历史威科夫规则应使用完成日线的明确口径。
- 首版不新增持久化事件库或后台扫描；按需有界读取和计算。若后续缓存，键必须覆盖 symbol、asset_type、timeframe、as_of、窗口、rule_version、params_hash、data_generation。

## 外部调研与工具边界

- 外部原始资料与开源实现核对见同目录 `EXTERNAL-REUSE-20261108.md`。
- Open Design MCP 已经注册，但当前任务未暴露其工具；本机 Open Design 可执行文件签名校验结果为 `NotSigned`。未绕过签名边界执行安装/注册，也未改用其他设计模式。

## 已确认与仍待冻结

- 用户已选择 A：独立“威科夫研究”页；页面 brief 已补入 `INTEGRATION-DESIGN.md` 第 9 节，待确认。
- 事件枚举、窗口、阈值、确认延迟、失效与冲突规则仍待研究规格冻结。
- 页面设计稿在 Open Design 可用连接恢复后生成。
