# 12 条策略的因子化映射与缺口 v1

状态：**v1，待因子工程师与系统架构师确认**。生成日期 2026-11-07。
本文件是**规格**，不是实现、不是回测结果。全文不含任何收益/Sharpe 数字。

---

## 0. 本文件的定位

2026-11-07 起团队规则变更：策略必须以因子组合表达，代码实现只能落在系统代码里。这改变了我的交付物：

| 项 | 变更前（已作废的形态） | 变更后（本文件的形态） |
| --- | --- | --- |
| 我的产出 | 可跑通的研究脚本 `scripts/*.py` | 因子组合表达式 + 参数 + 判据 |
| 策略信号 | 我在 pandas/polars 里手算 `rolling_mean/std/shift` | 注册因子 id + DSL 算子（`ts_*` / `rank`） |
| 实现者 | 我 | 系统开发工程师（`matrix_strategy` 插件） |
| 我的验证角色 | 写也验 | **只验不写**：独立复核信号等价性、样本外表现、成交可行性 |

本文件回答一个问题：**已冻结的 12 条策略（`STRATEGIES.md` v2），能不能在现有因子体系里被无歧义地表达？** 能的部分给出 DSL 表达式，不能的部分给出缺口。

`scripts/*.py` 里既有的研究脚本（`run_suite.py`、`common.py` 等）在规则变更后**不再是正式实现路径**，它们是历史探索性证据的生成器，保留不动、不再扩展。已跑完的 36 次 v0 结果按 `PROTOCOL.md` §0.2 仍是 exploratory。

---

## 1. 事实基线（可复算）

| 事实 | 值 | 来源 |
| --- | --- | --- |
| 注册因子总数 | **178** | `app.factors.registry.all_factors()` |
| base / virtual | 117 / 61 | 同上 |
| 因子分组 | 15 组（扩展数据 85、量价 11、均线偏离 10、趋势 9、首板事件链 9、动量 8、波动率 8、价格位置 8、财务 7、截面联动 7、收益形态 5、超买超卖 4、流动性 4、涨停基因 2、规模 1） | 同上 |
| DSL 算子 | 时序 13 个（`ts_mean/std/sum/max/min/delay/delta/rank/zscore/corr/cov/quantile`、`decay_linear`）+ 截面 3 个（`rank`/`zscore`/`winsorize`）+ `if_else/min/max/log/abs/sign/sqrt/power/clamp` | `app/factors/dsl.py` `OPERATORS` |
| 截面算子实现 | `rank(x)` = `x.rank("average").over("date") / x.count().over("date")` | `dsl.py:506-508` |
| 表达式编译入口 | `compile_formula()`，返回 `referenced_factors` / `warmup_bars` / `cross_sectional` | `dsl.py:563` |
| 生产侧是否有消费方 | 有：`app/api/factors.py`、`app/factors/store.py`、`app/strategy/scoring.py` | `grep compile_formula` |

**关键事实：12 条策略里 10 条的入场条件今天就能编译通过**（实测见 §3），不需要等任何新因子。这不是估计，是跑出来的。

---

## 2. 逐条因子化映射（12 行）

记号：`rk(x)` 是截面百分位；`delay(x,n)` = `ts_delay(x,n)`；`maxT(x,n)` = `ts_max(x,n)`。表达式一律为**收盘后可知**，执行仍在次日开盘（`PROTOCOL.md` §2）。

| # | 策略 | 入场（因子表达式） | 出场 | 排序 | 调仓日历 | 缺口 |
| --- | --- | --- | --- | --- | --- | --- |
| S01 | 双均线 20/60 | `ma20_bias < ma60_bias and delay(ma20_bias,1) >= delay(ma60_bias,1)` | `ma20_bias > ma60_bias` | `momentum_20d` 降 | 事件驱动 | 无（预热声明需修，见 C3） |
| S02 | 唐奇安 20/10 | `close > delay(maxT(high,20),1)` | `close < delay(ts_min(low,10),1)` | `momentum_20d` 降 | 事件驱动 | 建议注册 `breakout_dist_20d`（可复用，非阻塞） |
| S03 | 时序动量 60/月末 | `momentum_60d > 0 and close > ts_mean(close,120) and ma20_bias < ma60_bias` | `momentum_60d <= 0 or close < ts_mean(close,120)` | `momentum_60d` 降 | 月末 | **G2** `ma120_bias`（现最大 60） |
| S04 | RSI(14) 超卖 | `rsi_14 < 30` | `rsi_14 > 55` | `rsi_14` 升 | 事件驱动 | 无（定义口径见 C2） |
| S05 | 布林 (20,2) 下轨 | `boll_position < 0` | `boll_position > 0.5` | `boll_position` 升 | 事件驱动 | **G6** `boll_position` 标度未定 |
| S06 | 截面 5 日反转 | `rk(momentum_5d) <= 0.05` | 无 | `momentum_5d` 升 | 周末 | **G7** rank 分母语义 |
| S07 | 截面 60 日低波动 | `rk(ts_std(close/prev_close-1,60)) <= 0.10` | 无 | 同式 升 | 月末 | **G1** `vol60`；G7；**G8** `prev_close` 口径 |
| S08 | 52 周新高附近 | `distance_to_high_250d >= -0.03 and close > ts_mean(close,120)` | 无 | 同式 降 | 月末 | **G3** 250 vs 240 口径；G2 |
| S09 | 55 日新高 + 1.5× 量 | `close > delay(maxT(high,55),1) and volume > 1.5*delay(ts_mean(volume,20),1)` | `ma20_bias < 0` | `momentum_60d` 降 | 事件驱动 | **G4** `vol_ratio_20d`；G3 同族 |
| S10 | 截面 20 日反转 | `rk(momentum_20d) <= 0.10` | 无 | `momentum_20d` 升 | 月末 | 仅 G7 |
| S11 | 低波动 + 反转复合 | `rk(ts_std(close/prev_close-1,60)) <= 0.30 and rk(momentum_20d) <= 0.30` | 无 | `rk(vol60)+rk(momentum_20d)` 升 | 月末 | G1、G7 |
| S12 | 低波动 + 宽度择时 | `rk(ts_std(close/prev_close-1,60)) <= 0.10 and market_breadth >= 0.5` | 无 | 同 S07 | 月末 | G1、**G5** `market_breadth`（市场级） |

三处等价性说明（都已逐位核对，不是近似）：
- **`ma20 > ma60` ⟺ `ma20_bias < ma60_bias`**：两者同除当日 `close`，序不变，零信息损失。
- **`prior_high20` ⟺ `delay(maxT(high,20),1)`**：v0 写的是 `high.shift(1).rolling_max(20)` = `max(high[t-20..t-1])`，DSL 写法展开后相同。
- **`close < ma20` ⟺ `ma20_bias < 0`**：`ma20_bias = close/ma20 - 1`。

---

## 3. 可编译性实测（`factor_map_build.py`，EXIT=1 因 2 条缺因子）

| # | 编译 | 声明预热 | 截面 | 引用注册因子 | 未注册标识符 |
| --- | --- | ---: | --- | --- | --- |
| S01 | OK | 2 | 否 | `ma20_bias`,`ma60_bias` | — |
| S02 | OK | 21 | 否 | —（只用 base 列 high/low/close） | — |
| S03 | OK | 121 | 否 | `ma20_bias`,`ma60_bias`,`momentum_60d` | — |
| S04 | OK | 1 | 否 | `rsi_14` | — |
| S05 | OK | 1 | 否 | `boll_position` | — |
| S06 | OK | 1 | **是** | `momentum_5d` | — |
| S07 | OK | 61 | **是** | —（内联 vol60 表达式） | — |
| **S08** | **ERR E001** | — | — | — | **`distance_to_high_250d`** |
| S09 | OK | 56 | 否 | — | — |
| S10 | OK | 1 | **是** | `momentum_20d` | — |
| S11 | OK | 61 | **是** | `momentum_20d` | — |
| **S12** | **ERR E001** | — | — | — | **`market_breadth`** |

- `E001` = 未知标识符（`dsl.py` 语义检查）。
- S07/S11 之所以 OK，是因为我把 `vol60` **内联**成 `ts_std(close/prev_close-1,60)`，而不是引用因子 id。**这只是"能编译"，不是"口径已定"**——正因如此 G1 仍是阻塞项：内联会让同一经济量的定义散落在每个策略里，与"因子为单一权威"的规则直接冲突。

---

## 4. 缺口清单（按阻塞度排序）

| ID | 缺口 | 阻塞谁 | 性质 | 建议归属 |
| --- | --- | --- | --- | --- |
| **G1** | `vol60`（60 日收益波动）未注册。现状：有 `annual_vol_20d`(20 日)、`vol_regime_5_60`（5/60 比），没有 60 日波动水平 | S07、S11、S12（整个低波动族） | 因子缺口 | 因子工程师定义 + 证据；口径须与 v0 `ret1.rolling_std(60)` 对齐 |
| **G2** | 均线级别因子只有 `ma5/10/20/30/60_bias`，无 120/200 | S03、S08 | 因子缺口 | 因子工程师 |
| **G3** | `distance_to_high_240d` 是 240 日、**收盘价口径**；v0 的 `dist_52w_high` 是 250 日、**high 口径** | S08、S09 | 口径冲突（与团队已知的 `high_60d` 冲突同族） | 因子工程师定口径，行情数据工程师确认字段 |
| **G4** | 缺 `vol_ratio_20d`（有 5d/10d）、`breakout_dist_55d` | S09 | 因子缺口（非阻塞，可内联） | 因子工程师 |
| **G5** | `market_breadth` 是**市场级按日聚合**（宇宙内 `close > ma60` 的占比），不是逐股因子；DSL 无截面均值算子 | S12 | **引擎能力缺口**，不是因子缺口 | 系统架构师定契约 → 开发工程师实现 |
| **G6** | `boll_position` 只写"下轨到上轨之间的位置"，未写标度（是 0–1 还是 -1~1 还是 0–100） | S05 | 定义未定 | 因子工程师确认；确认前 S05 的 `-2sd` 阈值无法翻译 |
| **G7** | **截面 rank 的分母**：DSL = 当日**非空**样本数；v0 = 当日 **in_universe** 样本数 | S06、S07、S10、S11、S12 | 语义风险（会改变 0.05/0.10/0.30 阈值边界上的信号集合） | 架构师定契约：宇宙过滤必须在表达式求值**之前**施加 |
| **G8** | `prev_close` 是复权昨收还是交易所昨收；v0 用 `close.pct_change()`（复权序列） | S07、S11、S12 | 数据口径风险（除权日会差） | 行情数据工程师 |
| **G9** | 组合级调仓执行器（月末/周末换仓 + `max_hold` 强平 + 5 持仓/60% 敞口） | S03、S06、S07、S08、S10、S11、S12（7 条） | 已知引擎缺口（团队台账已记） | 架构师 + 开发工程师 |

**结论**：12 条里 **S01/S02/S04 三条零因子缺口**（只依赖已注册因子或 base 列），其余 9 条卡在 G1–G3 或 G5/G9。低波动族（S07/S11/S12）是唯一必须新增因子才能开工的族，而它同时也是 v0 里唯一出现过正样本外的族——这个巧合值得注意：**别让"缺口最难"变成"唯一有望的先不做"**。

---

## 5. 三处会让"同一策略"变样的口径风险（必须在实现前钉死）

这三条不是理论担忧，是从代码里读出来的差异点。

### C1. rank 分母（G7）
```python
# dsl.py:506-508
count = inner.count().over("date")          # 非空样本数
return inner.rank(method="average").over("date") / count
```
```python
# v0 scripts/common.py:193-197
pl.col(col).rank("average").over("date") / pl.col("in_universe").sum().over("date")
```
差异出现在**预热带**：`vol60` 在上市初期为空，v0 的分母仍是当日宇宙全部股票数，DSL 的分母只数非空股票。于是同一天的 `rk_vol60` 在两边可以差到百分之几，`<= 0.10` 的边界信号集合随之不同。
→ 影响 S06/S07/S10/S11/S12 全部截面族。**不解决就无法做"复现"**，只能算新试验。

### C2. 指标定义（RSI / 布林 / 波动）
- v0 `rsi_14`：`gains/losses` 各自 `ewm_mean(alpha=1/14, adjust=False)`（Wilder 近似）。
- 注册 `rsi_14` 的公式文本只有"14日相对强弱指标"，**未写平滑方式**。
- v0 `sd20`：`rolling_std(20)`（polars 默认 `ddof=1`）；DSL `ts_std` 也是 `rolling_std` 默认 → **这一项等价**。
- `boll_position` 标度未定（G6）。
→ 影响 S04/S05。需因子工程师给出公式文本级定义，而不是"指标名"。

### C3. 声明预热与实际不符（可能是缺陷，不是口径）
- `ma20_bias` / `ma60_bias` 声明 `warmup_bars=1`，但依赖 `close`+`ma20`/`ma60`。S01 的入场表达式因此被判为 `warm=2`，而实际需要 **61 根**。
- `momentum_60d` 声明 `warmup_bars=1`，实际需要 61 根。
- 若引擎按声明预热加载数据，**首段样本会是错的**（前 60 根内 `momentum_60d` 用不足窗口算出值）。
→ 我不下"注册表有 bug"的结论，只报事实：**声明值与窗口长度不一致**。请因子工程师与架构师确认这是"base 列已在上游物化，故声明 1"的合理设计，还是遗漏。

---

## 6. 等价性验收协议（因子化 vs v0，按信号比，不按收益比）

这是规则变更后我该做的验证，也是"复现 vs 新试验"边界在因子化语境下的落地：

1. **比信号，不比收益**：对每条策略，逐 `(date, symbol)` 比对 `entry` 布尔值，要求 **0 处差异**；再比 `score` 数值，要求 `|Δ| < 1e-12`。
2. **分段比**：预热段（前 61/121/251 根）与正文段**分开报**。预热段差异只能记为 `INPUT_ERROR` 或按 §5-C3 的声明问题归因，不得计入正文段。
3. **不许用收益接近来宣称等价**：收益相同可能是两条不同信号互相抵消。信号级 0 差异才算复现。
4. **出现差异即停**：任一条在正文段出现非零差异 → 停止该批，写清差异的日期/标的/两个数值，交架构师定位。**不得**以"结果更接近"为由调整因子定义（那就是 `CRITERIA_v1.md` §5 里的 F 项违规 +2）。
5. **口径变更登记**：C1/C2/C3 任一项被改成与 v0 不同 → 该策略降级为**新试验**，须登记并累加 N（`CRITERIA_v1.md` §5 R-F / F 项）。

---

## 7. 给因子工程师的最小开工集（按优先级）

| 优先级 | 需求 | 判据 |
| --- | --- | --- |
| P0 | 确认 §5 的 C1/C2/C3 三项口径（rank 分母、`rsi_14`/`boll_position` 公式文本、预热声明语义） | 给出公式文本与一份可复算样例，不需要回测 |
| P1 | 注册 `vol60`（公式须与 v0 `ret1.rolling_std(60)` 对齐，`ddof` 明确） | 单因子证据可另行补，先要定义落地 |
| P2 | 注册 `ma120_bias`、`distance_to_high_250d`（或裁定统一到 240 日并改规格） | 口径裁定书 + 公式文本 |
| P3 | 注册 `vol_ratio_20d`、`breakout_dist_20d/55d`、`breakdown_dist_10d` | 便于复用与台账，不阻塞 |
| P4 | `market_breadth` 走引擎能力（G5），不是因子 | 需架构师先给契约 |

**我不写这些因子。** 按新规则，我只出规格、口径要求与验收判据。

---

## 8. 分批建议的变化

`CRITERIA_v1.md` §6 的 4+8 切法**在因子化之后需要改**，原因是 gate 的作用变了：

| 原 gate | 原理由 | 因子化后是否仍是 gate |
| --- | --- | --- |
| S01 | 最纯的公共层（MA + 金叉） | **是**，且现在它同时验证 C3（预热声明）——零因子缺口 |
| S06 | 成本层最先炸（15.4× 换手） | **是**，且它现在额外验证 C1（rank 分母）——唯一"截面 + 高换手"双压力 |
| S07 | 位级锚点（已复现过） | **降级**：G1 未解决前它根本编译不成因子版，只能内联，做不了 gate |
| S09 | 拦截计数器路径 | 保留，但降到第二批首 |

新 gate 建议：**S01（时序+MA，验 C3）→ S10（截面+低换手，验 C1，不依赖 G1/G5）→ S02（high 通道 + 拦截计数）**。
理由：三条都在 §3 实测为 OK、零阻塞缺口，且各自压一个不同的契约点。S07/S11/S12 必须等 G1，不放进 gate。

---

## 9. 未验证 / unknown（明确列出）

1. **本文未跑任何回测**，不含收益数字；§3 只证明"表达式被编译器接受"。
2. **未验证 DSL 表达式与 v0 的信号级等价**：需要 §6 的比对工具，本轮未做（涉及读取面板数据与逐日比对，属新工作量）。
3. **`prev_close` 语义未知**（G8）：未查数据字典，未判定除权日行为 → S07/S11/S12 的 `close/prev_close-1` 是否等于 `pct_change()` **unknown**。
4. **`boll_position` 标度未知**（G6）：按"0–1"假设翻译，未核对实现 → S05 的映射**不可视为已定**。
5. **C3 的预热声明**只核对了 3 个因子的声明值与窗口长度，未全表核对 178 个。
6. **未验证策略引擎能否直接消费 DSL 表达式**：我只确认了 DSL 编译器和 `app/api/factors.py`、`scoring.py` 有消费方；`matrix_strategy` 插件是否支持"entry = DSL 公式"这一形态，需架构师给契约。这是**本文件最大的未验证项**。
7. `market_breadth` 只在 v0 里按"宇宙内且 `ma60` 非空"取均值；若架构师定义不同（如全市场），S12 结果会变，属新试验。

---

## 10. 实际命令与退出码

```powershell
# 注册表盘点（178 因子）
backend\.venv\Scripts\python.exe -c "from app.factors import registry as R; ..."   # EXIT=0

# DSL 表达式编译试算（10 条入场式）
backend\.venv\Scripts\python.exe -c "from app.factors.dsl import compile_formula ..."  # EXIT=0

# 12 条映射全量核对 + 写 factor_map_v1.json
backend\.venv\Scripts\python.exe research\strategy-search-20261107\scripts\factor_map_build.py
#   → ALL_ENTRIES_COMPILE: False；MISSING_ID_STRATEGIES: ['S08','S12']；EXIT=1
```

`EXIT=1` 是脚本的设计行为（有策略缺因子 id 即非零），不是崩溃。

产物：`FACTOR_MAP_v1.md`（本文件）、`factor_map_v1.json`（机器可读，含每条表达式的编译结果与未注册标识符）、`scripts/factor_map_build.py`（只读核对器，不实现策略）。
