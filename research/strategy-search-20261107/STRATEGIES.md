# 公开策略候选库 v2（12 条可检验规格 + 逐条出处）

状态：**v2 冻结**（2026-11-06）。相对 v1 的变化：为每条策略补可核出处、标明「出处支持什么 / 不支持什么」、把无文献支撑的参数与规则显式标为「无出处·仅按名称实现」。sha256 见 `FREEZE.json`。

所有策略共用同一套账户、宇宙、成本与时序（`PROTOCOL.md` §2–4）。参数为**运行前写死的固定值**，脚本不提供按结果调参的入口。

## 0. 出处总表（逐条）

核验状态说明：**文献存在性 = 高置信**（作者/年份/期刊为公开经典文献）；**卷期页码与 DOI 未在本轮联网核对**，故不提供 DOI，避免编造标识符。核查方式：按「作者 + 年份 + 标题」检索即可定位原文。

| # | 策略 | 族 | 出处（作者·年份·标题·出处） | 该出处支持什么 | 参数是否原样来自出处 |
| --- | --- | --- | --- | --- | --- |
| S01 | 双均线 20/60 | 趋势 | Brock, Lakonishok & LeBaron (1992), *Simple Technical Trading Rules and the Stochastic Properties of Stock Returns*, Journal of Finance 47(5) | 均线交叉规则族在指数序列上有预测力（美股/道指，1885–1987） | 否。20/60 不是该文唯一设定，是该族最常见组合之一 |
| S02 | 唐奇安 20/10 | 趋势 | Donchian 通道规则（Richard Donchian，1950s，未见系统论文）；可核二次文献：Faith (2003), *Way of the Turtle*, McGraw-Hill；Kaufman (2013), *Trading Systems and Methods* 5th ed., Wiley | 通道突破的入场/出场定义（20 日与 55 日通道、10 日反向出场） | 部分。20 日入场 + 10 日出场取自 Turtle System 1 的变体 |
| S03 | 时序动量 60 日 + 月末 | 时序动量 | Moskowitz, Ooi & Pedersen (2012), *Time Series Momentum*, Journal of Financial Economics 104(2) | 时序动量（过去 1–12 月收益为正则做多）+ 月度再平衡 | **否**。该文用 1–12 月窗口；60 日是本实现的缩短版 |
| S04 | RSI(14) 超卖反转 | 均值回归 | Wilder (1978), *New Concepts in Technical Trading Systems*, Trend Research Institute（RSI 定义与 14 日默认）；阈值用法：Connors & Alvarez (2008), *Short Term Trading Strategies That Work*, TradingMarkets | RSI 指标定义（Wilder 平滑、14 日）；「超卖买入、回中轴卖出」的均值回归用法 | 指标是；**阈值 30/55 不是 Wilder 原文（原文 70/30）** |
| S05 | 布林带 (20,2) 下轨 | 均值回归 | Bollinger (2001), *Bollinger on Bollinger Bands*, McGraw-Hill；学术检验：Lento, Gradojevic & Wright (2007), *Investment information content in Bollinger Bands?*, Applied Financial Economics Letters 3(4) | 20 日均线 ±2 标准差的带构造（作者默认参数） | 是（20,2）；「回中轨出场」是常见用法，非原文强制 |
| S06 | 截面 5 日反转 | 截面反转 | Jegadeesh (1990), *Evidence of Predictable Behavior of Security Returns*, Journal of Finance 45(3)；Lehmann (1990), *Fads, Martingales, and Market Efficiency*, Quarterly Journal of Economics 105(1) | 1 周–1 月的短期反转（美股个股横截面） | 否。「5 日」与「最弱 5%」是实现选择，文献只给方向 |
| S07 | 截面 60 日低波动 | 截面因子 | Ang, Hodrick, Xing & Zhang (2006), *The Cross-Section of Volatility and Expected Returns*, Journal of Finance 61(1)；Baker, Bradley & Wurgler (2011), *Benchmarks as Limits to Arbitrage*, Financial Analysts Journal 67(1) | 低波动/低 beta 组合的风险调整后收益异象（**美股样本**） | 否。60 日窗口与 10% 分位是实现选择 |
| S08 | 52 周新高附近 | 动量 | George & Hwang (2004), *The 52-Week High and Momentum Investing*, Journal of Finance 59(5) | 「距 52 周高点的距离」比历史收益率更好的动量代理 | 否。-3% 阈值与 MA120 过滤是实现选择 |
| S09 | 55 日新高 + 1.5× 量 | 趋势 | 组合来源：(a) 55 日通道 = Faith (2003) *Way of the Turtle* / Donchian 规则；(b) 量价确认方向 = Karpoff (1987), *The Relation Between Price Changes and Trading Volume: A Survey*, JFQA 22(1) | (a) 55 日突破的入场定义；(b) 「价格变动伴随成交量放大」的经验关系（**不提供任何阈值**） | **否**。1.5× 量比与 MA20 出场无文献来源 → 见 §3 标注 |
| S10 | 截面 20 日反转 | 截面反转 | Jegadeesh (1990)；Lehmann (1990)；月度反转亦见 Nagel (2012), *Evaporating Liquidity*, Review of Financial Studies 25(7) | 1 个月反转（横截面） | 否。「20 日」「最弱 10%」「月末调仓」是实现选择 |
| S11 | 低波动 + 20 日反转复合 | 截面因子 | 合成方法：Asness, Moskowitz & Pedersen (2013), *Value and Momentum Everywhere*, Journal of Finance 68(3)；低波动腿：Frazzini & Pedersen (2014), *Betting Against Beta*, JFE 111(1) | 多因子合成（等权/排名标准化后相加）是标准做法；低波动腿的构造 | **否**。两条腿 GP 等权（各 50%）与 30% 分位阈值均无文献来源 → 见 §3 标注 |
| S12 | 低波动 + 市场宽度择时 | 截面因子+择时 | 低波动腿同 S07；宽度：Murphy (1999), *Technical Analysis of the Financial Markets*, NYIF（市场宽度指标）；MA 择时：Faber (2007), *A Quantitative Approach to Tactical Asset Allocation*, Journal of Wealth Management 9(4) | 宽度指标（收盘在均线上方的股票占比）的定义与用法；趋势/MA 择时的可行性 | **否**。「宽度 ≥ 0.5 才建仓」的阈值无文献来源 → 见 §3 标注 |

**未标注出处的项一律不得写成「公开策略」**：本文只允许两种表述——「有出处（作者·年份·标题）」或「无出处·仅按名称实现」。

## 1. 通用字段说明

- **signal**（收盘后可知）→ **execute**（次日开盘）。
- **score**：候选排序键，同日候选多于可用仓位时按此降序取。
- **max_hold**：持有上限（交易日），到期强制平仓。
- **失效条件**：预先写死的判死条件，命中即判失效，不再迭代。

## 2. 逐条规格

### S01 双均线 20/60 金叉（趋势）

| 项 | 规格 |
| --- | --- |
| 入场 | `in_universe` 且 `ma20 > ma60` 且当日发生金叉（前一日 `ma20 <= ma60`） |
| 出场 | `ma20 < ma60`（死叉） |
| 排序 | 20 日收益（`ret20`）降序 |
| 持有 | 至死叉或最长 60 交易日 |
| 数据 | 复权收盘（60 根预热） |
| 出处 | Brock, Lakonishok & LeBaron (1992)（规则族）；20/60 参数为实现选择 |
| 失效条件 | 全期年化 < 0 且 T2 Sharpe < 0.2；或零成本情景仍为负 |

### S02 唐奇安 20/10 突破（趋势）

| 项 | 规格 |
| --- | --- |
| 入场 | `close > prior_high20`（前 20 日最高价 rolling max，不含当日） |
| 出场 | `close < prior_low10` |
| 排序 | `ret20` 降序 |
| 持有 | 至跌破 10 日低或最长 60 交易日 |
| 数据 | 复权 high/low |
| 出处 | Donchian 规则；Faith (2003) *Way of the Turtle*（Turtle System 1）；Kaufman (2013) |
| 失效条件 | 同 S01；额外：入场日开盘涨停拦截次数 > 入场成交笔数 |

### S03 时序动量 60 日 + 月末调仓（时序动量）

| 项 | 规格 |
| --- | --- |
| 入场 | 仅月末交易日：`ret60 > 0` 且 `close > ma120` 且 `ma20 > ma60` |
| 出场 | 月末且（`ret60 <= 0` 或 `close < ma120`） |
| 排序 | `ret60` 降序 |
| 持有 | 至动量转负或最长 60 交易日 |
| 数据 | 复权收盘（120 根预热） |
| 出处 | Moskowitz, Ooi & Pedersen (2012)（时序动量）；**60 日窗口非原文设定**（原文 1–12 月） |
| 失效条件 | 同 S01 |

### S04 RSI(14) 超卖反转（均值回归）

| 项 | 规格 |
| --- | --- |
| 入场 | `rsi14 < 30` |
| 出场 | `rsi14 > 55` |
| 排序 | RSI 升序 |
| 持有 | 至 RSI > 55 或最长 10 交易日 |
| 数据 | 复权收盘；RSI 用 `ewm(alpha=1/14, adjust=False)` 近似 Wilder |
| 出处 | Wilder (1978)（指标定义与 14 日）；Connors & Alvarez (2008)（超卖阈值用法）；**30/55 非同源参数** |
| 失效条件 | 10bp 年化 < 0 且零成本年化 < +2%；或年换手 > 30× |

### S05 布林带 (20,2) 下轨反转（均值回归）

| 项 | 规格 |
| --- | --- |
| 入场 | `close < ma20 - 2×sd20` |
| 出场 | `close > ma20` |
| 排序 | 布林 z 值升序 |
| 持有 | 至回中轨或最长 10 交易日 |
| 数据 | 复权收盘 |
| 出处 | Bollinger (2001)（20,2 作者默认）；Lento, Gradojevic & Wright (2007)（学术检验） |
| 失效条件 | 同 S04 |

### S06 截面 5 日反转（截面反转）

| 项 | 规格 |
| --- | --- |
| 入场 | 仅周末交易日：`rk_ret5 <= 0.05`（当日截面 5 日收益最弱 5%） |
| 出场 | 无出场信号，靠换仓与 max_hold |
| 排序 | `-ret5` |
| 持有 | 周度换仓，最长 5 交易日 |
| 数据 | 复权收盘；排名在当日 `in_universe` 内 |
| 出处 | Jegadeesh (1990)；Lehmann (1990)（短周期反转）；**5 日/5% 为实现选择** |
| 失效条件 | 年换手 > 25× 且 30bp 年化 < −5%；或 T2 Sharpe < −0.5 |

### S07 截面 60 日低波动（截面因子）

| 项 | 规格 |
| --- | --- |
| 入场 | 仅月末：`rk_vol60 <= 0.10`（60 日收益波动最低 10%） |
| 出场 | 无出场信号 |
| 排序 | `-vol60` |
| 持有 | 月度换仓，最长 20 交易日 |
| 数据 | 复权收盘（60 日波动需 60 根预热） |
| 出处 | Ang, Hodrick, Xing & Zhang (2006)；Baker, Bradley & Wurgler (2011)；**美股样本，A 股方向未验证** |
| 失效条件 | 单一年份贡献 > 50% 总收益；或 30bp T2 Sharpe < 0.3 |

### S08 52 周新高附近（动量）

| 项 | 规格 |
| --- | --- |
| 入场 | 仅月末：`dist_52w_high >= -3%` 且 `close > ma120` |
| 出场 | 无出场信号 |
| 排序 | `dist_52w_high` 降序 |
| 持有 | 月度换仓，最长 20 交易日 |
| 数据 | 复权 high（250 根预热） |
| 出处 | George & Hwang (2004)；**-3% 阈值与 MA120 为实现选择** |
| 失效条件 | 入场日平均跳空 > +0.5% 且 30bp 年化 < 0 |

### S09 55 日新高 + 1.5 倍量能突破（趋势）

| 项 | 规格 |
| --- | --- |
| 入场 | `close > prior_high55` 且 `volume > 1.5 × prior_vol20` |
| 出场 | `close < ma20` |
| 排序 | `ret60` 降序 |
| 持有 | 至跌破 MA20 或最长 20 交易日 |
| 数据 | 复权 high/volume（55 根预热） |
| 出处 | 55 日通道：Faith (2003)/Donchian；量价确认方向：Karpoff (1987)。**1.5× 量比与 MA20 出场无文献来源 → 无出处·仅按名称实现** |
| 失效条件 | 入场日平均跳空 > +0.5% 且 30bp 年化 < 0；买入涨停拦截 > 1,000 次 |

### S10 截面 20 日反转（截面反转）

| 项 | 规格 |
| --- | --- |
| 入场 | 仅月末：`rk_ret20 <= 0.10` |
| 出场 | 无出场信号 |
| 排序 | `-ret20` |
| 持有 | 月度换仓，最长 20 交易日 |
| 数据 | 复权收盘 |
| 出处 | Jegadeesh (1990)；Lehmann (1990)；Nagel (2012)（月度反转）；**10% 分位为实现选择** |
| 失效条件 | 同 S06 |

### S11 低波动 + 20 日反转复合（截面因子）

| 项 | 规格 |
| --- | --- |
| 入场 | 仅月末：`rk_vol60 <= 0.30` 且 `rk_ret20 <= 0.30` |
| 出场 | 无出场信号 |
| 排序 | `-(rk_vol60 + rk_ret20)` 升序 |
| 持有 | 月度换仓，最长 20 交易日 |
| 数据 | 复权收盘 |
| 出处 | 合成方法：Asness, Moskowitz & Pedersen (2013)；低波动腿：Frazzini & Pedersen (2014)。**两条腿等权与 30% 分位无文献来源 → 无出处·仅按名称实现（合成权重）** |
| 失效条件 | T2 Sharpe < 0 且 30bp 年化 < −3% |

### S12 低波动 + 市场宽度择时（截面因子 + 择时）

| 项 | 规格 |
| --- | --- |
| 入场 | 仅月末：`rk_vol60 <= 0.10` 且 `market_breadth >= 0.5` |
| 出场 | 无出场信号 |
| `market_breadth` | 当日宇宙内收盘价在 MA60 上方的股票占比（只用当日及以前价格） |
| 排序 | `-vol60` |
| 持有 | 月度换仓，最长 20 交易日 |
| 数据 | 复权收盘 |
| 出处 | 低波动腿同 S07；宽度定义：Murphy (1999)；择时：Faber (2007)。**0.5 阈值无文献来源 → 阈值部分无出处** |
| 失效条件 | 相对 S07 的最大回撤改善 < 3pp；或 T2 Sharpe < 0 |

## 3. 无出处 / 仅有名称的策略与参数（必须显式标注）

| 项 | 标注 |
| --- | --- |
| S09 的「1.5 倍量能」阈值、「MA20 出场」 | 无出处·仅按名称实现（通道与量价方向有出处，阈值没有） |
| S11 的「两腿等权 + 30% 分位」 | 无出处·仅按名称实现（合成权重） |
| S12 的「宽度 ≥ 0.5」 | 阈值无出处（指标定义有出处） |
| S03 的 60 日窗口 | 参数无出处（文献为 1–12 月） |
| S04 的 30/55 阈值 | 参数无出处（Wilder 原文 70/30） |
| S06/S10 的 5%/10% 分位 | 参数无出处 |
| S08 的 -3% 阈值 | 参数无出处 |

## 4. 对照组合 C00（非候选，不计入 N）

月末按前 20 日均成交额取最大的 5 只，月度换仓，max_hold 20。用途：检验「在同样撮合口径下，随便买大票」能拿到什么，作为策略下限参照。**不计入试验次数，不参与推荐。**

## 5. 参数与假设的诚实标注

- 全部参数取自公开文献默认值或常见交易软件默认值，**未做任何邻域搜索**；因此本批结果不能说明「这条策略的最优形式如何」，只能说明「这个固定形式在 2019-07 ~ 2026-10 的 A 股主板上是否可用」。
- 截面类策略的持有期为「到下一个再平衡日」，`max_hold` 只是上限；`buy_same_day_reentry` 计数全部为 0。
- 事件/公告类策略未建立候选：数据不支持，见 `DATA-BOUNDARY.md`。
