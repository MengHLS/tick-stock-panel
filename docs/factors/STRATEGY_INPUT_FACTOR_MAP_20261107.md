# 12 条策略「输入 → 系统因子」映射与口径差异

状态：**v1，只读盘点**。生成日期 2026-11-07。作者：因子工程师（本文件不含任何收益数字，只有口径与信号判定差异）。

策略规格来源：`research/strategy-search-20261107/scripts/common.py`（`add_indicators` / `add_universe` / `build_signals` / `STRATEGIES`）。
系统口径来源：`backend/app/indicators/pipeline.py#compute_indicators`、`backend/app/strategy/scoring.py#scoring_value_expr`、`backend/app/factors/dsl.py`、`backend/app/backtest/engine.py`。

## 0. 结论

| 判定 | 项数 | 含义 |
| --- | --- | --- |
| 可直接复用 | 16 | 公式与口径逐位一致，注册引用即可 |
| 口径不一致 | 6 | 系统有近义因子，但价基/窗口/shift/掩码不同；下方给出实测差异 |
| 系统缺失 | 23 | 系统没有该因子或该执行能力 |

三句话概括：

1. **纯量价中间量几乎全部可以逐位复用**（`momentum_*`、`ma20/ma60`、`boll_*`、`change_pct` 平均绝对差为 0）。S01/S05 今天就能用系统因子无损表达。
2. **真正卡住策略的是 4 类东西**：`vol60`、`ma120/ma200`、`prior_high*`/`prior_low*`/`prior_vol20` 这类「此前」语义、以及带股票池掩码的截面排名；其中前三类都能用现有 DSL 算子注册（无需改引擎），第四类需要引擎给出「掩码后的 rank」。
3. **`high_60d` 不能当 `prior_high55` 用**：`high_60d` 用收盘价且含当日，`close > high_60d` 在 5 470 011 行里一次都不成立（S09 入场条件会整体失效）。`low_60d` 同理（触发率 0.000%）。

## 1. 复算基线

| 项 | 值 |
| --- | --- |
| 行情面板 | 6,422,875 行 / 3,384 只 / 2018-01-08 ~ 2026-10-30 |
| 评估区间 | 2019-07-01 ~ 2026-10-30（5,510,001 行） |
| 股票池门槛（研究） | min_price_raw=3.0, min_prior_amount20=100000000.0, min_observed_bars=120 |
| 判定阈值 | 全部取自 `common.py#build_signals`，不调参 |
| 复算脚本 | `docs/research/factor-audit-20261107/scripts/audit_compare.py`、`audit_xs_rank.py` |

## 2. 逐策略映射

### S01_ma_cross_20_60 — 双均线 20/60 金叉（持有至死叉或最长 60 交易日）

| 研究中间量 | 研究定义 | 系统对应 | 判定 | 实现路径 | 数值差异 / 证据 |
| --- | --- | --- | --- | --- | --- |
| ma20 | `close.rolling_mean(20)` | `ma20`（base，含当日） | **可直接复用** | 已注册，直接引用 | 逐位相同（平均绝对差 0）（n=5,497,082；corr=1.000000；spearman=1.000000；平均绝对差=0；p95=0；均值 14.17 vs 14.17） |
| ma60 | `close.rolling_mean(60)` | `ma60`（base，含当日） | **可直接复用** | 已注册，直接引用 | 逐位相同（平均绝对差 0）（n=5,470,011；corr=1.000000；spearman=1.000000；平均绝对差=0；p95=0；均值 14.08 vs 14.08） |
| ret20（信号打分） | `close/close.shift(20)-1` | `momentum_20d` | **可直接复用** | 已注册，直接引用 | 逐位相同（平均绝对差 0）（n=5,496,401；corr=1.000000；spearman=1.000000；平均绝对差=0；p95=0；均值 0.00931 vs 0.00931） |
| in_universe | 观察 bar≥120 & 非 ST & raw_close≥3 & 20日均额≥1亿 & volume>0 | **无**（系统无股票池掩码因子） | **系统缺失** | 仅缺因子 | 见 §5 横向输入；影响 12 条策略全部 |
| max_hold_days=60 强制平仓 | 回测引擎按持有天数强制出场 | **生产侧无**（回测引擎有 `max_hold_days`；监控/模拟盘无） | **系统缺失** | 需生产侧执行器 | 见 §5；`app/strategy/paper_auto.py` 无持有期上限逻辑 |

### S02_donchian_20_10 — 唐奇安 20 日突破 / 10 日退出

| 研究中间量 | 研究定义 | 系统对应 | 判定 | 实现路径 | 数值差异 / 证据 |
| --- | --- | --- | --- | --- | --- |
| prior_high20 | `high.shift(1).rolling_max(20)` | **无**；最近的是 `high_60d`（`close.rolling_max(60)`，含当日） | **系统缺失** | 注册即可 | 可用 `ts_delay(ts_max(high,20),1)` 注册；不可用 `high_60d` 替代 |
| prior_low10（出场） | `low.shift(1).rolling_min(10)` | **无**；最近的是 `low_60d`（`close.rolling_min(60)`，含当日） | **系统缺失** | 注册即可 | `close < low_60d` 在研究数据上触发率 **0.000%**（研究侧 prior_low10 触发 8.85%）——用 `low_60d` 会让 S02 出场永不触发 |
| ret20（信号打分） | `close/close.shift(20)-1` | `momentum_20d` | **可直接复用** | 已注册，直接引用 | 逐位相同（平均绝对差 0） |

### S03_tsmom_60_m — 60 日时序动量 + 月末调仓

| 研究中间量 | 研究定义 | 系统对应 | 判定 | 实现路径 | 数值差异 / 证据 |
| --- | --- | --- | --- | --- | --- |
| ret60 | `close/close.shift(60)-1` | `momentum_60d` | **可直接复用** | 已注册，直接引用 | 逐位相同（平均绝对差 0）（n=5,469,335；corr=1.000000；spearman=1.000000；平均绝对差=0；p95=0；均值 0.02587 vs 0.02587） |
| ma120 | `close.rolling_mean(120)` | **无**（只有 `ma20`/`ma60` 与 `deviate_*d` 偏离因子） | **系统缺失** | 注册即可 | `ts_mean(close,120)` 编译通过，warmup=121；参考统计：站上 MA120 的样本占比 46.8% |
| ma20 / ma60 | 同 S01 | `ma20` / `ma60` | **可直接复用** | 已注册，直接引用 | 逐位相同（平均绝对差 0） |
| month_end（调仓日） | 全市场交易日历，下一交易日跨月即月末 | **无**（无调仓日因子，也无组合级调仓执行器） | **系统缺失** | 需生产侧执行器 | 12 条策略中 7 条依赖月末/周末再平衡（S03/S06/S07/S08/S10/S11/S12），见 §5 |

### S04_rsi14_reversion — RSI(14) < 30 超卖反转（最长 10 交易日）

| 研究中间量 | 研究定义 | 系统对应 | 判定 | 实现路径 | 数值差异 / 证据 |
| --- | --- | --- | --- | --- | --- |
| rsi14 | `gains/losses 来自 ret1(pct_change)` + `ewm(alpha=1/14, adjust=False)` | `rsi_14`（同 ewm，但 gains/losses 来自 `close.diff()` 绝对价差；零损失处用 1e-12 护栏） | **口径不一致** | 仅缺因子 | n=5,509,321；corr=0.998312；spearman=0.998772；平均绝对差=0.8922；p95=1.967；均值 50.19 vs 49.34；阈值判定差异：判定一致率 jaccard=0.948；仅研究侧成立 2,162 行；仅系统侧成立 9,768 行（n=5,510,001） / RSI>55：判定一致率 jaccard=0.898；仅研究侧成立 190,170 行；仅系统侧成立 0 行（n=5,510,001） |
| rsi14 的 warmup | ewm 无固定窗口，理论无界 | 注册表声明 warmup=1 | **口径不一致** | 仅缺因子 | ewm(alpha=1/14) 权重衰减到 1e-3 需约 95 根 bar；声明 1 会让早期 RSI 明显失真 |

### S05_bollinger_20_2 — 布林带(20,2) 下轨反转

| 研究中间量 | 研究定义 | 系统对应 | 判定 | 实现路径 | 数值差异 / 证据 |
| --- | --- | --- | --- | --- | --- |
| bb_lower / bb_upper | `ma20 ∓ 2*sd20`（sd20 = `close.rolling_std(20)`） | `boll_lower` / `boll_upper`（base） | **可直接复用** | 已注册，直接引用 | 逐位相同（平均绝对差 0）（n=5,497,082；corr=1.000000；spearman=1.000000；平均绝对差=0；p95=0；均值 12.83 vs 12.83） |
| sd20 | `close.rolling_std(20)` | 无独立字段；`(boll_upper-boll_lower)/4` 反推 | **可直接复用** | 已注册，直接引用 | 反推值与 sd20 逐位相同（平均绝对差 2.7e-16） |
| bb_z（信号打分） | `(close-ma20)/sd20` | `boll_position`：`(close-boll_lower)/(boll_upper-boll_lower)`，`bb_z = 4*boll_position-2` | **可直接复用** | 已注册，直接引用 | 恒等关系逐位验证（平均绝对差 8.0e-16） |
| ma20 | `close.rolling_mean(20)` | `ma20` | **可直接复用** | 已注册，直接引用 | 逐位相同（平均绝对差 0） |

### S06_xs_reversal_5d — 5 日收益最弱 5% 周度反转

| 研究中间量 | 研究定义 | 系统对应 | 判定 | 实现路径 | 数值差异 / 证据 |
| --- | --- | --- | --- | --- | --- |
| rk_ret5（截面排名） | `in_universe` 内 `rank(average)/池内家数` | `rank(momentum_5d)`：全样本 `rank(average)/当日非空家数`，**无掩码** | **口径不一致** | 需引擎能力 | 376 个调仓日；平均选股数 研究 49.7 vs 系统 154.3；jaccard=0.319；分母：池内 1429 vs 全样本 3095 |
| ret5 | `close/close.shift(5)-1` | `momentum_5d` | **可直接复用** | 已注册，直接引用 | 逐位相同（平均绝对差 0）（n=5,506,617；corr=1.000000；spearman=1.000000；平均绝对差=0；p95=0；均值 0.002261 vs 0.002261） |
| week_end（调仓日） | 周最后一个交易日 | **无** | **系统缺失** | 需生产侧执行器 | 见 §5 |

### S07_xs_lowvol_60d — 60 日波动最低 10% 月度持有

| 研究中间量 | 研究定义 | 系统对应 | 判定 | 实现路径 | 数值差异 / 证据 |
| --- | --- | --- | --- | --- | --- |
| vol60 | `ret1.rolling_std(60)`（日频，未年化） | **无**；最近的 `annual_vol_20d` = `ret1.rolling_std(20)*√252` | **系统缺失** | 注册即可 | 不可替代：n=5,469,335；corr=0.777195；spearman=0.788756；平均绝对差=0.3724；p95=0.7296；均值 0.02607 vs 0.3984；年化后仍不可替代：n=5,469,335；corr=0.777195；spearman=0.788756；平均绝对差=0.09191；p95=0.247；均值 0.4138 vs 0.3984；低波十分位重叠 jaccard=0.136 |
| rk_vol60 | 池内 `rank(vol60)/池内家数` | **双重缺口**：`vol60` 未注册 + `rank()` 无股票池掩码 | **系统缺失** | 需引擎能力 | 88 个调仓日；平均选股数 研究 55.5 vs 系统 307.2；jaccard=0.178 |
| month_end | 月末最后交易日 | **无** | **系统缺失** | 需生产侧执行器 | 见 §5 |
| vol60 的量级 | 日频标准差 | — | **—** | — | 研究口径分位：p10=0.0141 / p50=0.0247 / p90=0.0398 |

### S08_high_52w — 52 周新高附近月度持有（距 250 日高点 3% 内）

| 研究中间量 | 研究定义 | 系统对应 | 判定 | 实现路径 | 数值差异 / 证据 |
| --- | --- | --- | --- | --- | --- |
| dist_52w_high | `close/prior_high250-1`，`prior_high250 = high.shift(1).rolling_max(250)` | `distance_to_high_240d`：`close/close.rolling_max(240)-1`（**收盘价、含当日、240**） | **口径不一致** | 注册即可 | n=5,332,523；corr=0.985987；spearman=0.986034；平均绝对差=0.02744；p95=0.06824；均值 -0.2683 vs -0.2416；「距高点 3% 内」判定：判定一致率 jaccard=0.530；仅研究侧成立 0 行；仅系统侧成立 133,101 行（n=5,332,523） |
| ma120 | `close.rolling_mean(120)` | **无** | **系统缺失** | 注册即可 | 同上 S03 |
| month_end | 月末 | **无** | **系统缺失** | 需生产侧执行器 | 见 §5 |

### S09_volume_breakout_55 — 55 日新高 + 1.5 倍量能突破

| 研究中间量 | 研究定义 | 系统对应 | 判定 | 实现路径 | 数值差异 / 证据 |
| --- | --- | --- | --- | --- | --- |
| prior_high55 | `high.shift(1).rolling_max(55)` | 系统只有 `high_60d` = `close.rolling_max(60)`（**收盘价、含当日、60**） | **系统缺失** | 注册即可 | **用 high_60d 替代会让入场条件恒不成立**：判定一致率 jaccard=0.000；仅研究侧成立 143,747 行；仅系统侧成立 0 行（n=5,470,011）；若改用「收盘价+shift1+60」也只剩一半：判定一致率 jaccard=0.504；仅研究侧成立 3,893 行；仅系统侧成立 130,975 行（n=5,307,478） |
| prior_vol20 | `volume.shift(1).rolling_mean(20)` | **无 vol_ma20**；现有 `vol_ma5`/`vol_ma10`（含当日） | **系统缺失** | 注册即可 | 1.5 倍量条件用 `vol_ma10` 替代：判定一致率 jaccard=0.601；仅研究侧成立 269,878 行；仅系统侧成立 93,177 行（n=5,496,401）；量能均值本身：n=5,496,401；corr=0.956243；spearman=0.976916；平均绝对差=4.76e+04；p95=1.918e+05；均值 2.263e+05 vs 2.266e+05 |
| ma20（出场） | `close.rolling_mean(20)` | `ma20` | **可直接复用** | 已注册，直接引用 | 逐位相同（平均绝对差 0） |
| ret60（信号打分） | `close/close.shift(60)-1` | `momentum_60d` | **可直接复用** | 已注册，直接引用 | 逐位相同（平均绝对差 0） |

### S10_xs_reversal_20d — 20 日收益最弱 10% 月度持有

| 研究中间量 | 研究定义 | 系统对应 | 判定 | 实现路径 | 数值差异 / 证据 |
| --- | --- | --- | --- | --- | --- |
| rk_ret20 | 池内 `rank(ret20)/池内家数` | `rank(momentum_20d)`，无掩码 | **口径不一致** | 需引擎能力 | 88 个调仓日；平均选股数 研究 92.8 vs 系统 308.8；jaccard=0.298 |
| ret20 | `close/close.shift(20)-1` | `momentum_20d` | **可直接复用** | 已注册，直接引用 | 逐位相同（平均绝对差 0） |
| month_end | 月末 | **无** | **系统缺失** | 需生产侧执行器 | 见 §5 |

### S11_lowvol_reversal — 低波动 + 20 日反转复合（两项排名均在前 30%，按排名和排序）

| 研究中间量 | 研究定义 | 系统对应 | 判定 | 实现路径 | 数值差异 / 证据 |
| --- | --- | --- | --- | --- | --- |
| rk_vol60 / rk_ret20 | 两个池内截面排名 | `rank(vol60)` / `rank(momentum_20d)`，无掩码；且 vol60 未注册 | **系统缺失** | 需引擎能力 | 复合选股 88 个调仓日；平均选股数 研究 14.7 vs 系统 207.2；jaccard=0.049 —— 系统口径下选股数放大 14.1× |
| 排序键 -(rk_vol60+rk_ret20) | 研究侧直接对排名求和 | `score` 列可由 `rank/zscore` 组合表达，但依赖同一 rank 口径 | **口径不一致** | 需引擎能力 | 排序口径不一致会改变持仓优先级，不只是选股集合 |
| month_end | 月末 | **无** | **系统缺失** | 需生产侧执行器 | 见 §5 |

### S12_lowvol_breadth — 低波动月度 + 市场宽度 ≥ 0.5 才建仓

| 研究中间量 | 研究定义 | 系统对应 | 判定 | 实现路径 | 数值差异 / 证据 |
| --- | --- | --- | --- | --- | --- |
| vol60 / rk_vol60 | 同 S07 | **无** / 无掩码 rank | **系统缺失** | 需引擎能力 | 88 个调仓日；平均选股数 研究 55.5 vs 系统 307.2；jaccard=0.178 |
| market_breadth | `in_universe` 内 `close>ma60` 的占比（收盘可知） | **无**（DSL 只有逐行算子 + 截面 rank/zscore/winsorize，没有全市场聚合） | **系统缺失** | 需引擎能力 | 掩码 0.541 vs 无掩码 0.464；corr=0.942；平均绝对差 0.085；阈值翻转日占比 19.1%；月末通过率 53.4% vs 34.1% |
| month_end | 月末 | **无** | **系统缺失** | 需生产侧执行器 | 见 §5 |

## 3. 横向输入（与具体策略无关，但每条策略都用）

| 输入 | 研究定义 | 系统对应 | 判定 | 数值差异 / 证据 |
| --- | --- | --- | --- | --- |
| 股票池 in_universe | bar≥120 / 非ST / raw_close≥3 / 20日均额≥1亿 / volume>0 | **无**股票池因子（`st_flag` 是数据列，不是因子） | **系统缺失** | 当前 1429 只 vs 全样本 3095 只；1 亿成交额门槛若用 `amount_mean_20d`(含当日) 替代，判定一致率 jaccard=0.977；仅研究侧成立 31,052 行；仅系统侧成立 31,533 行（n=5,496,401） |
| 月末/周末调仓日 | 交易日历末交易日 | **无** | **系统缺失** | 8/12 条策略依赖；回测侧由 `app/backtest/factor.py` 的 `rebalance` 处理，生产侧无 |
| max_hold_days | 回测引擎参数 | 回测有（MatcherConfig.max_hold_days）；监控/模拟盘无 | **系统缺失** | S01/S02/S03/S04/S05/S06 均依赖持有期上限 |
| 执行价 | 研究 `matching=open_t+1`、`entry_price_basis=raw` | 回测引擎同参可复现；模拟盘 `order_type=next_open` 可对齐 | **可直接复用** | 执行链路口径一致，无需新因子 |
| 涨跌停不可买 | 研究 `block_limit_open=True` | 回测引擎支持 | **可直接复用** | 同上 |

## 4. 逐条策略的可落地结论

| 策略 | 今天能否用系统因子无损表达 | 缺什么 |
| --- | --- | --- |
| S01 双均线 | 能（除股票池掩码与持有期上限） | in_universe、max_hold |
| S02 唐奇安 | 不能 | prior_high20、prior_low10 |
| S03 时序动量 | 不能 | ma120、month_end |
| S04 RSI | 近似（需接受 0.89 pt 的系统偏差） | rsi 口径统一 |
| S05 布林 | 能（除股票池掩码） | in_universe |
| S06 5 日反转 | 不能（系统口径选股数放大 3.1×） | 掩码 rank、week_end |
| S07 低波 | 不能 | vol60、掩码 rank、month_end |
| S08 52 周新高 | 不能（近高点判定差一半） | 250 日高点口径、ma120、month_end |
| S09 量能突破 | 不能（入场恒不成立） | prior_high55、prior_vol20 |
| S10 20 日反转 | 不能（系统口径选股数放大 3.3×） | 掩码 rank、month_end |
| S11 复合 | 不能（系统口径选股数放大 14.1×） | vol60、掩码 rank、month_end |
| S12 低波+宽度 | 不能 | vol60、掩码 rank、market_breadth、month_end |

## 5. 复现

```bash
cd C:\work\sourcecode\tick-stock-panel\backend
.\\.venv\\Scripts\\python.exe ..\docs\\research\\factor-audit-20261107\\scripts\\audit_compare.py    # 口径对照 -> compare_stats.json
.\\.venv\\Scripts\\python.exe ..\docs\\research\\factor-audit-20261107\\scripts\\audit_xs_rank.py    # 截面/宽度 -> xs_rank_stats.json
.\\.venv\\Scripts\\python.exe ..\docs\\research\\factor-audit-20261107\\scripts\\build_strategy_map.py  # 生成本文件 + strategy_factor_map.json
```

机器可读：`docs/research/factor-audit-20261107/strategy_factor_map.json`、`compare_stats.json`、`xs_rank_stats.json`。
