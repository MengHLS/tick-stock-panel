# 因子清单：定义、历史覆盖、可知时点、数据版本

2026-10-28；只读核查，未改代码、未改数据。用于"逐事件回放增加因子快照"的第一批选型。

## 1. 数据版本（本次核查）

| 项 | 取值 |
|---|---|
| 因子注册表 | `backend/app/factors/registry.py`，`_CATALOG` 共 **86** 个因子（base 25 / virtual 61） |
| 行情 | `D:\TSP\data\kline_daily_enriched`，2018-01-08 ~ 2026-10-27，9,728,665 行 |
| 财务 | `D:\TSP\data\financials\{balance_sheet,income,cash_flow,metrics,shares}` **全部为空目录，无 parquet** |
| 行业/概念 | `ext_data/ext_hy_ths`（5,577 行）、`ext_data/ext_gn_ths`（5,579 行），**均无日期列，单快照** |
| 维表 | `instruments`，as_of 2026-10-26 单快照 |
| 换手率空值率 | 全表 0.15% |

## 2. 因子分组（86 个）

| 组 | 数量 | 因子 | 依赖与可知时点 |
|---|---:|---|---|
| 动量 | 8 | momentum_5/10/20/30/60d、momentum_120d、change_pct、mom_accel_20_60 | 收盘价派生，D 收盘可知 |
| 均线偏离 | 10 | ma5/10/20/30/60_bias、ema5/10/20/30/60_bias | close + MA，D 收盘可知 |
| 趋势 | 9 | macd_dif/dea/hist(±pct)、kdj_k/d/j、kdj_kd_diff、boll_position | D 收盘可知 |
| 波动率 | 8 | annual_vol_20d、atr_14、atr_pct、amplitude、boll_width、downside_vol_20d、vol_regime_5_60、amplitude_trend_20_60 | D 收盘可知 |
| 超买超卖 | 4 | rsi_6/14/24、rsi_14_delta_5d | D 收盘可知 |
| 量价 | 11 | vol_ratio_5d/10d、vol_trend_5_10、obv_trend_20d、vol_price_corr_20d、vol_trend_5_60、amount_ratio_5d、log_amount、amount_mean_20d、vwap_bias、turnover_rate | 成交量/额当日盘后可知 |
| 价格位置 | 8 | gap_return、intraday_return、close_position、vwap_bias、distance_to_high_60d/240d、position_240d、distance_from_low_60d | D 收盘可知 |
| 收益形态 | 5 | max_ret_20d、ret_skew_20d、up_days_20d、overnight_ret_20d、intraday_ret_20d | D 收盘可知 |
| 流动性 | 4 | amihud_20d、turnover_z_60d、turnover_mean_20d、turnover_std_20d | 见 §3 换手率问题 |
| 涨停基因 | 2 | limit_up_count_20d/60d | 依赖 `consecutive_limit_ups`，见 §3 |
| 首板事件链 | 9 | chain_stage、anchor_distance、pullback_pct、target_above_reference_pct、strict_rebreak、early_breakout、recovered_not_breakout、seed_close/low_preserved | 预热 251 根，D 收盘可知 |
| 财务 | 7 | pb_latest、roe_latest、gross_margin_latest、net_margin_latest、revenue_yoy_latest、net_income_yoy_latest、debt_ratio_latest | `pit=True`（公告日），但**本地无数据** |
| 规模 | 1 | log_float_mv | 依赖 turnover_rate，见 §3 |

## 3. 三个必须先处理的数据问题

### 3.1 换手率及其派生用的是**当前流通股本**（不是当时股本）

- `share_capital.load_share_history` 读 `financials/shares/part.parquet`；该目录为空 → 返回空表 → 历史日期回退到 `instruments` 的**当前** `float_shares`。
- 实证：600785.SH 2024-03-01 存储 `turnover_rate=1.773975`，用当前 `float_shares=315,883,792` 复算 `volume×100/float_shares×100` 得 1.773975，逐位一致；2026-10-23 同样一致。**历史上从未按当时股本折算。**
- 影响：`turnover_rate`、`turnover_ratio_5d`、`turnover_z_60d`、`turnover_mean_20d`、`turnover_std_20d`、`log_float_mv` 全部受污染；股本变动越多误差越大（送转、增发、解禁）。
- 处理：本批**不纳入因子快照**，或标注 `SHARE_CAPITAL_CURRENT_ONLY` 仅作对照。

### 3.2 行业/概念只有当前归属，没有历史

`ext_hy_ths`、`ext_gn_ths` 无日期列，只有当前行业与当前概念名单。用它们标注历史首板的行业环境属于**前视信息**（公司会改行业归类、概念会被调入调出）。
处理：本批**不用**行业/概念做历史事件的特征；如需市场环境，只能用全市场价格派生的市场状态（由 `kline_index_daily` 计算，注意指数只有 2025-10-27 起）。

### 3.3 首板口径与财务因子

- `limit_up_count_20d/60d`、`first_board_chain_*` 都依赖 `consecutive_limit_ups`，而后者由**当前名称 ST 判定 + 前缀静态板块幅度**生成（见 DATA-EVIDENCE.md §3、§4）。因子本身时点正确，但**输入侧身份未认证**，须与 `first_board_identity` 一起记录。
- 7 个财务因子声明 `pit=True`，但本地财务目录为空，实际无值；不能作为首板特征。

## 4. 首批建议纳入（点时干净、覆盖足够）

按 Chief 的四类拆分，只取有可靠历史、不依赖当前快照的因子：

| 类别 | 因子 | 时点 |
|---|---|---|
| 量能与流动性 | `amount`、`log_amount`、`amount_ratio_5d`、`amount_mean_20d`、`vol_ratio_5d`、`vol_ratio_10d`、`vol_trend_5_10`、`amihud_20d` | D 收盘可知 |
| 趋势与波动 | `momentum_5/20/60/120d`、`ma20_bias`、`ma60_bias`、`ema20_bias`、`position_240d`、`distance_to_high_60d/240d`、`annual_vol_20d`、`atr_pct`、`amplitude`、`boll_width`、`downside_vol_20d` | D 收盘可知 |
| 局部结构 | `close_position`、`intraday_return`、`gap_return`、`rsi_14`、`boll_position`、`first_board_chain_*`（随身份标注） | D 收盘可知 |
| 市场环境 | 由指数日 K 派生的市场涨跌家数/涨停数/指数动量 | 仅 2025-10-27 起可算；更早只能标缺失 |

**D−1 背景因子**用 D−1 收盘即可算；**D 日可知因子**必须用 D 收盘（含当日涨停），不得用 D+1 及以后。跟踪判断（D+3 等）只读取新增行情，不改写 D 日快照。

### 4.1 D−1 与 D 的边界（实测，用冻结 CSV 四例）

首板日当天涨幅接近 +10%，把 D 日 K 线算进窗口会让"位置类"因子整体向极值移动。同一只股票、同一窗口，只差是否包含 D 日：

| 事件 | D 日涨幅 | 240 日位置(D−1) | 240 日位置(D) | 差 | 距 240 日最高(D−1 → D) |
|---|---:|---:|---:|---:|---|
| 002687 2026-10-08 | +10.04% | 0.5745 | 0.7782 | +0.2036 | −17.33% → −9.04% |
| 002687 2026-06-23 | +10.02% | 0.1367 | 0.4388 | +0.3022 | −22.26% → −14.47% |
| 600785 2026-09-21 | +9.98% | 0.1409 | 0.1916 | +0.0507 | −62.82% → −59.11% |
| 002354 2026-08-28 | +9.94% | 0.3574 | 0.5000 | +0.1426 | −30.95% → −24.08% |

002687 在 2026-06-23 只因包含 D 日就从 0.14 跳到 0.44，会从"低位"变成"中位"。因此：

- **背景位置、距前高、均线偏离、动量**一律用 **D−1** 计算并标注 `as_of: D-1`；D 日值只作"事件后位置"单列，两类不能混用同一个字段名。
- `change_pct`（D 日涨幅）在首板日约等于涨停本身，与标签近乎同义，**只能作描述，不能当特征**。
- `vol_ratio_5d` 是"D 当日量 ÷ 前 5 日均量"，属 D 收盘可知，不能标成 D−1 背景。
- `turnover_rate` 即便在 D 日也因为用当前股本而不成立（§3.1）。


## 5. 覆盖与局限

- 4 只股票快照：2023-10-09 ~ 2026-10-23，各 738 根，无行缺口；250 根预热的因子在窗口内事件均可算。
- 2023-10 之前的事件不在本批快照内，需扩展导出区间才能算预热。
- 财务、行业、股本三项缺失是**数据源缺口**，不是实现缺陷；补齐后需重新出因子快照并升数据版本。
