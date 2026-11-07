# 只读盘点：现有回测与数据能力（2026-11-06）

盘点方式：只读 `backend/app/backtest/*`、`backend/app/extensions/adapters.py`、`backend/app/tickflow/*`、`app.price_limits`、`app.indicators.pipeline`，并直接统计 `D:/TSP/data` 的分区与行数。**未修改任何正式文件**（`git status` 中本目录外无新增改动）。

## 1. 撮合与账户能力（可支持）

| 能力 | 事实依据 | 对策略类型的影响 |
| --- | --- | --- |
| 信号/成交分离 | `build_market_matrix(..., entry_delay_bars=1, exit_delay_bars=1)` | 收盘决策、次日开盘成交；不允许当日收盘价成交 |
| 撮合模式 | `MatcherConfig(matching="open_t+1")` | 只有开盘价口径，无 VWAP/TWAP |
| 成本 | 佣金/印花税/过户费/最低佣金 + `slippage_bps` 单边滑点 | 支持 0/10/30bp 情景 |
| 涨跌停不可买 | `block_limit_open=True` → 计数器 `buy_limit_up` | 突破类策略会被真实拦截（见 REPORT 表 3） |
| 停牌 | 无价即不成交（`buy_suspended` / `sell_suspended`） | 停牌股不会被动成交 |
| 跌停不可卖 | 卖出遇跌停不成交（`sell_limit_down`） | 反转类策略的尾部风险不会被低估 |
| 连续单账户 | `SimulationOptions(carry_in=..., carry_out=True)` | 年度分段回放不清算，权益连续（已核对 8 段） |
| 最大持仓/敞口 | `max_positions`、`max_exposure_pct` | 本轮固定 5 只 / 60% |
| 复权 | `kline_daily` 同时给出 `close`（复权）与 `raw_close`；`entry_price_basis="raw"` | 成交价用真实价，收益计算用复权价 |
| ST 与涨跌幅 | `attach_st_history` + `polars_price_limit_pct` | 主板 10%/ST 5%/创业板科创板 20% 区分 |
| 生产 WFO | `backend/app/backtest/walkforward.py` 存在并可运行 | 本轮未用，原因见 PROTOCOL.md 第 7 节 |

## 2. 数据清单（实测行数/分区）

| 数据集 | 覆盖 | 量级 | 可用性 |
| --- | --- | --- | --- |
| `kline_daily` | 2018-01-08 ~ 2026-11-06（2,141 分区） | 最新日 5,572 只：60x 1,700、00x 1,490、30x 1,411、68x 616、92x 355 | 日线 OHLCV+amount+quote_ts，**本轮主数据源** |
| `kline_minute` | 2017-01-03 ~（2,389 分区） | 分钟级 | 存在，但撮合器只吃日线矩阵 |
| `kline_index_daily` | 2016-10-28 ~（2,435 分区） | 指数行情 | 可做基准参照，**无成分股历史** |
| `instruments` | 5,536 行 | symbol/name/listing_date/total_shares/float_shares/tick_size | 可算市值、上市日 |
| `st_history` | 单文件 | — | ST 判定 |
| `financials/balance_sheet` | period_end 2022-06-30 ~ 2026-09-30（14 期） | 37,872 行 | 公告日 2022-12-29 起 |
| `financials/income` | 11 期 | 44,616 行 | 公告日**仅 2025-04-25 起** |
| `financials/cash_flow` | 11 期 | 41,784 行 | 公告日**仅 2025-04-25 起** |
| `financials/metrics` | 单期快照（2026-06-30 ~ 09-30） | 5,577 行（每股 1 行） | **无历史** |
| `user_data/industry_chain/graph.json` | 当前快照 | 431 节点 / 3,539 条股票映射 | **无日期维度** |
| `depth5` | 4 个交易日 | 盘口五档 | 只能做点状核查 |
| `dragon_tiger` | 1 个文件（2026-10-23） | 龙虎榜 | 不可做时间序列 |
| `kline_etf_daily` / `kline_etf_enriched` | **空**（0 分区） | — | ETF 轮动不可做 |

## 3. 能做什么 / 不能做什么

**可直接做（本轮已覆盖）**
1. 日线趋势跟踪：双均线、唐奇安通道、时序动量、放量突破。
2. 均值回归：RSI 超卖、布林带下轨。
3. 截面因子：5/20 日反转、60 日低波动、52 周新高、低波动+反转复合。
4. 择时与仓位：市场宽度过滤（MA60 上方比例）、月度/周度再平衡。
5. 组合约束下的可成交性检验：涨跌停、停牌、5 持仓容量、60% 敞口。

**受限（可做但成本高/精度低）**
6. 分钟级信号：数据在，但撮合矩阵是日线；需要另建分钟矩阵，本轮未做。
7. 市值因子：`instruments.total_shares × raw_close` 可算，但 `total_shares` 是**当前快照**，历史市值会引入未来信息（股本变化）。本轮未使用。
8. 波动率目标仓位：日收益可算，但杠杆/融券成本无数据，只能做降仓版本。

**不可做（数据不支持，本轮未尝试）**
9. 价值/质量因子（PB/PE/ROE 时序）：财务报表只有 11–14 期且利润表/现金流公告日仅 2025-04 起，无法覆盖 2019–2022；`metrics` 只有单期快照 —— 用它回测等于把 2026 年的财务数据搬到 2019 年，是典型未来函数。
10. 行业中性/行业轮动：行业归属只有当前快照（`graph.json`），无历史成分。任务说明中的"行业快照仅 6 个交易日"与此一致，本轮未复算该数字。
11. 事件驱动（公告、龙虎榜、涨停板事件）：龙虎榜 1 天、`ext_data` 事件序列不完整，无法构成可用面板。
12. 指数增强：无指数成分股历史，无法做基准对齐与跟踪误差约束。
13. ETF/可转债轮动：`kline_etf_daily` 为空。
14. 做空/融券、T+0：撮合器与账户模型都不支持。

## 4. 结论

现有引擎足以支撑**日线级、价格与成交量驱动、多空仅做多、5 持仓集中组合**的策略检验，且可成交性与成本口径是真实拦截而非假设。
真正的缺口不在撮合，而在数据：**历史财务、行业归属、指数成分、事件流这四类"非价格数据"都只有当期快照或极短历史**。这决定了下一阶段的高价值方向是"把价格类策略做扎实并做稳健性分解"，而不是急着上基本面因子。
