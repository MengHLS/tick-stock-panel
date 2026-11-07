# 因子化引擎与生产侧执行器 —— 接口契约 v0.3（2026-11-07）

状态：**契约草案，待系统开发工程师据以实现、独立审核工程师据以验收**。作者：系统架构师。
本文件只定义接口（输入、输出、口径、空值/边界、幂等与确定性、禁止事项、验收判据、兼容性），**不含实现代码、不含收益数字、不下验收结论**。

依据（只读引用，均由因子工程师/因子研究员落盘）：
- `docs/factors/FACTOR_GAP_SPEC_20261107.md`（19 项缺口，D/F/E/X/G）
- `docs/factors/STRATEGY_INPUT_FACTOR_MAP_20261107.md`（12 条策略逐输入映射）
- `docs/factors/FACTOR_REGISTRY_CORE_93_20261107.md`（93 项台账）
- 研究侧权威口径实现：`research/strategy-search-20261107/scripts/common.py`（`add_indicators` / `add_universe` / `build_signals`）
- `docs/factors/XS_RANK_POOL_SPEC_20261107.md`（截面排名族可执行规格：三口径五字段 + 判据 A1–A8 / B1–B3 / C1–C3）
- `docs/research/caliber-decisions-20261107.md` §7「决定四」（v1.2，2026-11-07 14:40，截面排名口径的裁定方）

**修订记录**

| 版本 | 日期 | 变更 | 依据 |
| --- | --- | --- | --- |
| v0.1 | 2026-11-07 | 初稿（E1–E4 / X1 / F 六类契约） | 缺口规格、策略输入映射、93 项台账 |
| v0.2 | 2026-11-07 | §3 重写：E2 由单一 `xs_rank_pct` 扩为三个 id（`xs_rank_pool` 唯一策略可用 / `xs_rank_market` 仅诊断 / `xs_rank_pct` 仅历史），逐 id 定边界与判据 `XS-A/B/C`；冲突处置 `E2-K1`–`E2-K5` 见 §3.8；§2.6 `A3` 同步修正（同类第 6 处缺陷）；`rank_version` 递增为 `xs-rank/20261107.1` | 决定四 v1.2 + `XS_RANK_POOL_SPEC` |
| v0.3 | 2026-11-07 | 六处证据回灌（R2）：§7.1 坑 3 改为「同名不同单位」事实陈述；§7.6 `F-A6` 改为分位口径 `F-A6a/b/c`；`F-A5` 补实现现状；新增 §7.7 `status` 闸门（含 `FS01/FS02` 与 `F-A7`–`F-A9`）；§8 新增 D2 `rsi_14_pct` 行 + §8.1 落点裁定（base 列，否决扩 DSL 算子）；§2.2/§2.3/§2.6/§4.4/§6.4/§9 补 ST 数据事实与硬规则（含 §6.4 新增「全不可判定 → no-op」）。逐条原句/新句/依据见 `docs/architecture/CONTRACT_REVISION_R2_20261107.md` | 开发经理批一证据回灌（2026-11-07）+ 架构师独立复算 |


---

## 0. 编号对齐（先读，避免歧义）

任务书与缺口规格对 E 类编号不一致，本文件以**缺口规格的编号为准**，并在此显式登记差异：

| 本契约编号 | 含义 | 缺口规格编号 | 任务书写法 | 说明 |
| --- | --- | --- | --- | --- |
| **E3** | 股票池掩码因子 `in_universe` | E3 | （未单独列） | E1/E2 的**共同前置**，本契约必写 |
| **E2** | 截面排名族（掩码截面 rank） | E2 | E2 掩码截面 rank | 一致；决定四定稿后拆为三个 id：`xs_rank_pool`（唯一策略可用）/ `xs_rank_market`（仅诊断）/ `xs_rank_pct`（仅历史），见 §3 |
| **E1** | 全市场宽度 `market_breadth`（截面聚合） | E1 | E1 全市场宽度 | 一致 |
| **E4** | 调仓日 `month_end` / `week_end` | E4 | **写成 E3** | 上调仓日一律称 E4 |
| **X1** | 生产侧组合级调仓执行器 | X1 | X1 | 一致 |
| **F** | F1–F7 表达式因子注册入口 | F1–F7 | F 类因子注册入口 | 一致 |

不在本契约内：D1/D2/D3（口径决策，属因子工程师）、X2（`max_hold_days` 生产侧，P1，另立契约）、G1–G3（台账治理）、任何收益/选股效果判断。

---

## 1. 全局口径（所有条款共用，逐条可验收）

以下 8 条是 E1/E2/E3/E4/X1/F 的共同前提，任何一项被违反，对应能力的验收即视为不成立。

**G1 交易日轴（axis）**
交易日轴 = 全市场实际有 K 线的日期序列，升序、去重。权威来源：行情库当日分区（矩阵路径即 `MarketDataMatrix.timestamps` / `timestamp_labels`；面板路径即 `panel["date"].unique().sort()`）。
禁止用自然日、禁止用「月末最后一天」、禁止用 `app/services/trading_day.py#is_trading_day`（该函数是**实时探针**，可能返回 `None`，只回答「今天是否交易日」，不提供历史日历）。

**G2 as-of 语义**
信号在 T 日**收盘后**产生，只用 T 日及以前可知的信息；最早成交在 T+1 开盘（`entry_fill="open_t+1"`，`entry_price_basis="raw"`）。任何在 T 日使用 T+1 数据的实现，验收直接不通过。

**G3 掩码三态**
掩码元素 ∈ {True, False, **null**}。`null` 语义 =「口径不可判定」（如历史 ST 表缺该日），**不等价于 False**：
- 在计数、排名、占比中一律按「不入选」处理（不进分子也不进分母）；
- 但必须在审计输出中单独计数（`universe_unknown_count`），禁止静默折成 False。

**G4 空值策略**
全链路 `keep`：任一输入为空则输出为空；不填 0、不前向填充、不插值。策略侧的布尔化一律显式 `fill_null(False)`，且必须写在策略表达式里，不得在因子层偷偷补。

**G5 确定性**
同输入必须得到逐位相同的输出。所有排序必须给显式 tie-break：**数值降序 → symbol 字典序（`str` 比较）**；禁止依赖引擎默认顺序、字典插入顺序、哈希顺序。

**G6 幂等**
同一 (口径参数, 口径版本, 输入数据) 重算 → 同一结果；同一 (策略, 信号日) 重复执行调仓 → 同一计划，不产生重复订单（见 X1 §6.6）。

**G7 版本化**
每类口径带独立版本号：`universe_version`、`rank_version`、`breadth_version`、`rebalance_version`、因子 `version`。
**任何参数或定义变更必须递增版本号并写变更记录**；内容寻址缓存的键必须含版本号，禁止跨版本复用旧缓存（现 `app/factors/materialize_cache.py#cache_key` 已含 `spec.version`，参数变更时应体现为注册版本递增，而不是改常量）。

**G8 fail-closed**
输入缺失、口径冲突、页面/文件不可信 → 返回明确错误（中文可读）或空结果 + 原因码，**不得**返回一个「看起来正常」的近似值。所有「近似口径」必须在台账标 `approx`，且禁止用于策略判据。

---

## 2. E3 `in_universe` —— 股票池掩码因子（E1/E2 的前置）

### 2.1 语义
逐 (date, symbol) 判定「当日该标的是否属于公共股票池」。权威口径 = 研究侧 `research/strategy-search-20261107/scripts/common.py#add_universe`（第 175–184 行）：

```text
in_universe = (observed_bars >= 120)
            & (st_flag == False)                 # 历史 ST 标志，as-of 当日
            & (raw_close >= 3.0)                 # 不复权收盘
            & (prior_amount20 >= 1e8)            # 此前 20 日均成交额（元）
            & (volume > 0)
```

注意三条容易写错的点：
1. `observed_bars` 在研究中 = `date.cum_count().over("symbol")`，即**该标的在已加载面板内的 bar 行数**，不是「上市自然日」。系统侧等价且更稳的实现是「以当日为末端的滚动可交易日计数 ≥ 120」，前提是计算时**前置了 ≥120 根 bar 的 warmup 数据**。
2. 研究面板只保留 `60*` / `00*` 前缀（沪主板、深主板/中小板），**不含** `30*`（创业板）、`688*`（科创板）、`8*/4*`（北交所）。这是 1,429 vs 3,095 的差异来源之一，必须在池定义里显式声明，不能靠「基础过滤默认值」隐式实现。
3. `prior_amount20` 是**此前**口径（`amount.shift(1).rolling_mean(20)`，不含当日）；系统现有 `amount_mean_20d`（`app/strategy/scoring.py:241`）是**含当日**且单位**亿元**，`jaccard=0.977` 不可替代。

### 2.2 接口（字段级）

**输入**（逐行，均须 as-of 当日可得）

| 字段 | 类型 | 来源列 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `symbol` | str | 面板/矩阵 symbol 轴 | 是 | `600000.SH` / `000001.SZ` |
| `date` | date | 交易日轴 | 是 | 交易日，非自然日 |
| `raw_close` | float | 行情 `raw_close`（不复权） | 是 | 价格门槛用它，**不是** `close` |
| `volume` | float | 行情 `volume`（股） | 是 | `> 0` |
| `amount` | float | 行情 `amount`（元） | 是 | 用于 `prior_amount20` |
| `st_flag` | int 0/1 **或 null** | 历史 ST 表 as-of 合并（`app/tickflow/security_status.py#attach_st_history`） | 否（缺失有显式策略，不得填默认值） | 缺失 / 超出覆盖期末端 / 落在 `st_unknown_windows` 时一律按 §2.3 的三态处理：输出 `null`，**不**回退成「非 ST」 |
| `bar_present` | bool | 该 (date, symbol) 是否有 bar 行 | 是 | 无 bar = 停牌/未上市，本日无该行 |
| warmup | — | ≥120 根前置 bar | 是 | 不足则前 119 日全为 0 |

**参数（带版本）**

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `min_observed_bars` | `120` | 池内最少可交易 bar 数 |
| `min_price_raw` | `3.0` | 不复权收盘下限（元） |
| `min_prior_amount20` | `1e8` | 此前 20 日均额下限（元） |
| `require_volume_gt0` | `true` | `volume > 0` |
| `symbol_prefixes` | `("60", "00")` | 板块范围，显式参数，不写死在代码里 |
| `exclude_st` | `true` | 是否剔除 ST（`false` 仅供研究对照） |
| `st_flag_missing_policy` | `"unknown"` | `"unknown"` = 输出 null（生产默认）；`"treat_non_st"` = 按非 ST 处理（**仅对账/复现研究时显式传入**） |
| `st_unknown_windows` | `(("2026-10-20","2026-10-29"),)` | 强制置 `null` 的日期闭区间（含首尾，按**交易日**判定），见 §2.3 注 2；该参数变更必须递增 `universe_version` |
| `universe_version` | 起始 `1` | 任一参数变化必须递增。v0.3 起因新增 `st_unknown_windows` 与「末端不外推」两条硬规则，实际生效版本标 `2`（口径变了，缓存必须重算） |

**输出**

| 字段 | 类型 | 值域 | 说明 |
| --- | --- | --- | --- |
| `in_universe` | float64（DSL 可见）/ bool（内部适配视图） | `1.0` / `0.0` / `null` | 1=在池；0=确定不在池；null=口径不可判定（见 §2.4） |

同时必须能导出布尔视图 `mask`（`1.0 → True`、`0.0 → False`、`null → null`）供 `xs_rank_pool` / `xs_rank_pct` / `xs_mean` 的第 2 参数（`mask`）使用。

### 2.3 空值 / 边界
| 场景 | 输出 | 理由 |
| --- | --- | --- |
| 前置 bar < 120（含刚上市/长期停牌） | `0.0` | 确定不在池，不是不可判定 |
| `raw_close` / `prior_amount20` 为 null（但 bar 足够） | `0.0` | 与研究 `fill_null(False)` 一致，且可解释：条件不成立 |
| `volume == 0`（有行无成交） | `0.0` | 停牌半日/一字板另由撮合处理 |
| `st_flag` 缺失 且 `st_flag_missing_policy="unknown"` | `null` | 不把「未知 ST」当「非 ST」（研究侧的 `fill_null(False)` 是宽容处理，系统生产口径不沿用） |
| `st_flag` 缺失 且 `="treat_non_st"` | 按非 ST 继续计算 | 仅用于与研究的 1,429 对账，结果必须标 `approx=false, reconciliation_mode=true` |
| **`date` ∈ `st_unknown_windows`**（默认 `2026-10-20`…`2026-10-29`，共 **8** 个交易日：10-20/21/22/23/26/27/28/29） | `null`（**当日全部** symbol，不是 `0.0`/`False`） | ST 表在该窗口被批量覆写，口径不可判定（注 2）；按 G3 三态，`in_universe` 相应位置必须是 `null` |
| **`date` > ST 表 `coverageEnd`**（当前 `2026-10-29`） | `null` | 末端之后无数据，**禁止**用 `join_asof(backward)` 外推末值（注 3） |
| 该日全市场无任何合格标的 | 全部 `0.0`（不是 null） | 「池空」是确定结论，由上层（E1/rank）输出 null |
| 非 stock 资产（ETF 等） | `null` | 本因子只定义于 stock 域；`asset_types={"stock"}` |

**注 2（ST 数据事实，v0.3 新增；独立复算，非转述）**
`D:/TSP/data/st_history/part.parquet`（`symbol` / `flag_date` / `st_flag`，7,758 行、5,817 只、`2019-01-01`–`2026-10-29`；`manifest.json` 的 `absencePolicy = absence_of_ST_interval_is_non_ST`）在 **2026-10-20 有 198 行批量 `st_flag=false`**（当日全部 198 行都是 `false`）。按 as-of（每只取 `flag_date <= date` 的最后一行）复算的 ST 家数：**2026-10-19 = 218 → 2026-10-20 = 20**，并维持 20 到末端 2026-10-29；被这些行闭合的「真 ST 区间」恰为 **198** 个，末端仍开着的真 ST 区间为 **20** 个。窗口内其余 4 行（`301718.SZ`、`920296.BJ`、`920285.BJ`、`920306.BJ` 各 1 行，均为 `false`）是新上市标的的基线行，与本次批量写入无关。
→ 硬规则：**窗口内 ST 判定一律输出 `null`，禁止输出 `False`/`0`**；`in_universe` 相应位置必须是 `null`（三态），**不得静默当「非 ST 在池」**。修数据源不在本部门范围（属行情数据工程师）。
→ 代价（写清）：窗口 8 个交易日内整池不可判定 → E1 宽度为 `null`、E2 `xs_rank_pool` 为 `null`（池空）、X1 无新目标（见 §6.4 新增行）。这是 G8 的正确失败方向，不是缺陷。
→ 已登记但**未采用**的更窄口径：只对那 198 只输出 `null`、其余按 as-of 正常。前置条件 = 行情数据工程师书面确认「该日 198 行是唯一异常写入」+ 受影响名单 digest 落盘 + `universe_version` 递增。本契约不采用，因为本部门无法自证「唯一」，且名单会随数据修订变化。

**注 3（末端不外推，v0.3 新增）**
现实现 `app/tickflow/security_status.py:64-82`（`join_asof(strategy="backward")`）与 `:93-101`（`searchsorted(side="right")-1`、`known = indices >= 0`）都只判断「前面有没有行」，**不判断末端是否覆盖**；因此 `2026-10-30` 及以后会静默沿用 10-29 的状态（= 20 只 ST，而真实应为约 218 只）。规则：`date > coverageEnd` 一律 `null`，并在运维可见面报 `st_history_stale`（当前数据末端 2026-10-29，今日 2026-11-07 已滞后 9 个自然日）。
→ 代价：数据末端之后 `in_universe` 全 `null` → 生产不出新信号。这是**正确的失败方向**（宁可停信号，也不在「198 只 ST 被当非 ST」的池子上建仓），但必须让运维看见原因，而不是表现为「策略今天没选到票」。

### 2.4 幂等与确定性
- 纯函数：`(symbol, date, 参数, universe_version, 输入列内容)` → 唯一输出。同输入重复计算逐位相同。
- 不依赖当日之后任何数据（含 ST 表未来修订、复权因子未来变化）——若 ST 表被回溯修订，必须递增 `universe_version` 并重算，禁止混用。
- 缓存键必须包含：`universe_version` + 参数集 + 输入列 digest（`raw_close`,`volume`,`amount`,`st_flag`）+ 交易日轴 digest。

### 2.5 禁止事项
1. **禁止**用 `close`（前复权）替代 `raw_close` 判价格门槛。
2. **禁止**用含当日的 `amount_mean_20d` / `amount_ratio_5d` 替代 `prior_amount20`。
3. **禁止**用证券名称含 `ST/退` 判断替代历史 `st_flag`（名称是当前值，会前视；实时近似必须显式标 `approx`）。
4. **禁止**把池定义塞进 `DEFAULT_BASIC_FILTER`（`app/strategy/engine.py:38`）冒充——那会改动所有既有策略的样本口径。
5. **禁止**在策略文件里另写一份池实现；必须经注册表引用的单一实现。
6. **禁止**用「上市日期 + 自然日 120」替代「120 个交易日 bar」。

### 2.6 验收判据
| # | 判据 | 度量 |
| --- | --- | --- |
| A1 | 对账模式（`treat_non_st`）下逐日池内家数与研究一致 | 1,779 个交易日，日均 **1,429**，逐日 `diff == 0` |
| A2 | 池内标的的 bar 覆盖率 | ST 命中标的的 bar 覆盖率 **100%**（无静默丢弃） |
| A3 | 池内家数 vs 池内该列非空家数 | 逐日打印 `count(in_universe)` 与 `count(in_universe & x 非空)` 并逐条归因差异；这是 XS-A5 的上游。**E3 侧不得用 E2 的选股数作靶值**（v0.2 修订；原「复现 S07 = 55.5 ± 1」说的是 `xs_rank_pct` 的错口径） |
| A4 | 空值可解释 | `universe_unknown_count` 逐日为 0 或可逐条归因（哪只、哪天、缺哪列） |
| A5 | 版本自洽 | `universe_version` 变化时缓存不复用（构造一次参数变更，验证输出确实变化且新旧结果都留痕） |
| A6 | 时间不可逆 | 用区间尾部数据回放历史，任一历史日输出与全量计算逐位相同（无前视） |
| A7 | ST 窗口不可判定 | `2026-10-20`…`2026-10-29` 共 8 个交易日：断言 `count(in_universe ∈ {0.0, 1.0}) == 0`、`universe_unknown_count == 当日有 bar 的行数`；同窗口内 E1 输出 `null`、E2 `xs_rank_pool` 输出 `null`、X1 不产生订单（§6.4） |
| A8 | 末端不外推 | `date > coverageEnd` 的行必须 `null`；断言「把 10-29 状态外推到 10-30 及以后的行数 == 0」；`st_history_stale` 告警存在 |

### 2.7 与现有模块的兼容性
- **纯新增列**：不改变任何既有因子、既有 `basic_filter` 语义、既有评分。
- 面板路径：在 `app/indicators/pipeline.py#compute_indicators` 追加一列（新增 Pass，不改既有列）。
- 矩阵路径：在 `app/backtest/matrix.py#_MATRIX_COMPUTED_FEATURES` + `#_compute_matrix_feature` 增加分支，数值必须与面板路径逐位一致（两条路径同一实现，只做适配）。
- 与 `basic_filter` 的关系：**逻辑与**，不是替代。X1 中两道掩码都应用，并在审计里分别记账（`basic_filter_pass` / `in_universe_pass`）。

---

## 3. E2 截面排名族（`xs_rank_pool` / `xs_rank_market` / `xs_rank_pct`）

**状态（v0.2 重写，2026-11-07）**：口径裁定权不在架构侧。口径由研究侧「决定四」定稿（`docs/research/caliber-decisions-20261107.md` §7，**v1.2，2026-11-07 14:40**），可执行规格与判据编号由因子工程师落盘（`docs/factors/XS_RANK_POOL_SPEC_20261107.md`；机器可读 `docs/factors/evidence/xs_rank_family_specs_20261107.json`）。本节只做三件事：把决定四翻译成字段级接口、逐 id 定边界、把判据编号锚定。**本节与决定四冲突时以决定四为准**（G8：冲突即报错，不静默择一）。

**编号命名空间**（本节判据一律带前缀，避免与本文件其他节的 A/B 判据、与冲突登记撞号）：

| 前缀 | 含义 | 对应规格编号 |
| --- | --- | --- |
| `XS-A1`…`XS-A8` | `xs_rank_pool` 验收判据 | `XS_RANK_POOL_SPEC` §1.5 的 A1–A8 |
| `XS-B1`…`XS-B3` | `xs_rank_market` 验收判据 | 同上 §2.3 的 B1–B3 |
| `XS-C1`…`XS-C3` | `xs_rank_pct` 验收判据（`XS-C1` = 原 §3.4 的 R1–R5） | 同上 §3.3 的 C1–C3 |
| `E2-K1`…`E2-K5` | 本次修订的冲突处置登记（§3.8） | 同上 §6 的 C1–C5 |

### 3.1 口径事实（陈述事实，不裁定）

研究侧 `add_universe`（`research/strategy-search-20261107/scripts/common.py:196-200`，函数整体 `:175-202`）的截面排名原文：

```python
pl.when(pl.col("in_universe") & pl.col(col).is_not_null())
  .then(pl.col(col).rank("average").over("date") / pl.col("in_universe").sum().over("date"))
  .otherwise(None)
```

`when().then()` 只决定「哪些行留下值」，**不改变 `rank()` 的作用域**。四行样例（池内 a/c）：

| symbol | x | in_universe | rk |
| --- | --- | --- | --- |
| a | 10 | true | **0.5** |
| b | 20 | false | null |
| c | 30 | true | **1.5** |
| d | 40 | false | null |

三条已确证事实：

1. **该写法的分子是当日全样本名次、分母是池内家数**，所以值可以 >1。决定四 §7.7 实测（2021-06-30 / 2024-06-28 / 2026-09-30）：`max(rk_vol60)` = 2.513 / 3.057 / 1.778，且 `max(rk) × 池内家数` 恰等于当日全样本非空行数（3,041=3,041 / 3,170≈3,171 / 3,182=3,182）。
2. **系统现网 `rank` 是另一种东西**：`x.rank("average").over("date") / x.count().over("date")`（`app/factors/dsl.py:506-508`）= 全样本名次 ÷ 全样本非空家数（分母 3,076–3,095）；与上一条只有分母不同。
3. **两侧都错、方向相反**（决定四 §7.2）：研究实测选股数为名义 `t×P` 的 3.5% / 3.9% / 6.5% / 1.03%，系统实测为池内 10.8% / 21.5% / 21.6% / 14.5%。「研究侧是对的、系统侧偏松」的框架不成立，研究侧 `rk_*` **不是基准**。

**因此**（决定四 §7.3；架构侧照此落地，不再保留「先复现再讨论」的中间态）：唯一策略可用口径 = `xs_rank_pool`；`xs_rank_market` 仅诊断；`xs_rank_pct` 仅历史与差异证明。分子×分母只有下表四种组合，④ 明令禁止：

| # | 分子 | 分母 | id | 判定 |
| --- | --- | --- | --- | --- |
| ① | 池内平均名次 | 池内**非空**家数 | `xs_rank_pool` | **唯一策略可用**（`strategy_usable=true`） |
| ② | 全样本平均名次 | 全样本非空家数 | `xs_rank_market`（数值上 ≡ 现 `rank`） | 仅诊断（`false`） |
| ③ | 全样本平均名次 | 池内家数（含池内 x 为空者） | `xs_rank_pct` | 仅历史/差异证明（`false`） |
| ④ | 池内平均名次 | 池内**全部**家数（`in_universe.sum()`） | — | **禁止**（XS-A5 指纹） |

④ 单列的理由：它是最像 ① 的写法，也是唯一会**系统性偏低**的写法。池内 3 只、其中 1 只 `x` 为空、名次 1 与 2 → 正确输出 `{0.5, 1.0}`，④ 得 `{0.333, 0.667}`。

### 3.2 接口（逐 id 字段级）

三 id 共同项（不再逐表重复）：`cross_sectional = True`；无常量参数；归入截面算子族（与 `rank`/`zscore`/`winsorize` 同族，不得嵌进时序窗口，沿用 `E009`；`x`/`mask` 子树含窗口时走临时列机制 `dsl.py:614-725`）；空值策略 `keep`；不做 float32 收敛（矩阵路径如用 float32 必须在对账报告里声明精度损失）；`financial_pit = False`（量价因子）。

#### 3.2.1 `xs_rank_pool(x, mask)` —— 唯一策略可用口径

| 项 | 定义 |
| --- | --- |
| 签名 | `xs_rank_pool(x, mask)`；**`x` 与 `mask` 都必填、无默认值** |
| 语义 | `pool_percentile`：池内平均名次 ÷ 池内**非空**家数；分子分母是同一批样本 |
| 口径式（口径语言，非代码） | 令 `m = (mask == True) & x.is_not_null()`；`m` 之外置 null，然后在**同一列**上同时取 `rank("average").over("date")` 与 `count().over("date")`，两者相除 |
| 分母 | `count(x, over date, 限定 mask & x 非空)`，逐日重算；**禁止** `in_universe.sum()` |
| 输出 | float64，值域 `(0, 1]`；当日 `max == 1`、`min == 1/n > 0`（`n` = 当日池内非空家数）。**出现任何 >1 即不通过（XS-A1）** |
| `strategy_usable` | **true**（终态，`replaced_by = null`，不得被任何 id 取代） |
| `x` | 数值表达式（可含窗口、可引用已注册因子）；布尔按 `1.0/0.0` 参与 |
| `mask` | 布尔表达式；`mask` 非布尔（如直接传数值列）→ **新增 `E017`**；元数不对 → `E004`。传字面 `true` **不构成合法池**：那是 `xs_rank_market`，应改用该 id |
| warmup | `max(warmup(x), warmup(mask))`，算子自身不加窗口。`x = momentum_5d` → 121；`x = vol60` → 121（E3 的 121 随 `in_universe` 落地值变化，不得写死） |
| 依赖列 | `x` 的依赖列 + `mask` 的依赖列（`st_flag`、`raw_close`、`prior_amount_20`、`volume`、`observed_bars`） |
| 幂等 / 缓存 | 纯函数，同输入逐位相同；缓存键 = `(算子名, rank_version, 公式文本, x 依赖列 digest, mask 依赖列 digest)` |
| 登记形态 | 族 id + 必填参数，策略引用写作 `xs_rank_pool(x=vol60, mask=in_universe)`，**不为每个 x 派生新 id**。若注册表只能「一条表达式一个 id」，派生 `xs_rank_pool__<x>`，其 `semantics/scope/denominator` 必须与族 id 逐字相同、仅 `x` 不同，且必须由模板生成、禁止手写（防口径漂移） |

**边界与空值（`xs_rank_pool` 专属，逐条可断言）**

| 场景 | 正确输出 | 理由 |
| --- | --- | --- |
| 当日池内非空家数 = 0 | 全 `null` | 不可算，不是 0 也不是 1（XS-A6） |
| 池内非空家数 = 1 | 该成员 `1.0` | 分母 = 1、名次 = 1 |
| 池内某成员 `x` 为空 | 该成员 `null`；**不进分母** | 与 ③ 的关键差异（XS-A5） |
| `mask` 为 null | `null`；不进分母 | G3 三态：不折成 False |
| 池外成员 | `null` | 不参与分子分母 |
| tie（4 只同值） | 全部 `0.625` | `average`；`ordinal` / `min` / `max` 均不通过（XS-A8） |

#### 3.2.2 `xs_rank_market(x)` —— 仅诊断

| 项 | 定义 |
| --- | --- |
| 签名 | `xs_rank_market(x)`；**不接受 mask 参数**（有掩码就该用 `xs_rank_pool`） |
| 语义 | `market_percentile`：全样本平均名次 ÷ 全样本非空家数；与现 `rank` 同式。等价性**按公式推断，未逐位实测**（XS-B1 待跑） |
| 样本范围 | 当日面板内 `x` 非空的主板 `60`/`00` 标的（约 3,077–3,095 只）。**写「全市场」是错的**：创业板/科创板/北交所从未进入排名样本 |
| 输出 | float64，`(0, 1]`，当日 max = 1（非空家数 ≥ 1 时） |
| `strategy_usable` | **false**；`replaced_by = xs_rank_pool` |
| 台账 | `numeric_alias_of = rank`：与 `rank` **只计 1 个因子**，不得重复计入因子总数（否则 178 会被虚增） |
| 边界 | 与现 `rank` 完全一致（`count(x)==0` → 全 `null`；`x` 为空 → `null`）。本 id 不引入新边界 |

**边界与空值（`xs_rank_market` 专属）**

| 场景 | 正确输出 | 理由 |
| --- | --- | --- |
| 当日全样本非空家数 = 0 | 全 `null` | 不可算；与现 `rank` 一致（XS-B1） |
| 全样本非空家数 = 1 | 该成员 `1.0` | 分母 = 1、名次 = 1 |
| `x` 为空 | `null` | keep 策略；空值不占名次（决定四 §7.1 修正 2，polars 1.44.1 实测） |
| 传两个参数（带 mask） | 编译期报错 `E004` | 有掩码必须改用 `xs_rank_pool`，不允许隐式忽略 `mask` |
| 值域 | `(0, 1]`，当日 max = 1（非空家数 ≥ 1 时） | 分子分母同一批样本，**不会 >1**（与 `xs_rank_pct` 的区别） |

#### 3.2.3 `xs_rank_pct(x, mask)` —— 历史与差异证明

| 项 | 定义 |
| --- | --- |
| 签名 | `xs_rank_pct(x, mask)`；`mask` 必填 |
| 语义 | `global_rank_over_pool_count`：全样本平均名次 ÷ 池内家数。分子分母**不是同一批样本**——这是缺陷的形态，不是设计选择 |
| 分母 | 池内家数，**含池内 `x` 为空的成员**（≈1,429/1,430，等价 `in_universe.sum()`） |
| 输出 | float64，上界 = 全样本非空家数 ÷ 池内家数：周末 `3095.35 / 1428.95 ≈ 2.166`、月末 `3076.55 / 1429.74 ≈ 2.152`。**可以 >1，且必须能产出 >1 的样本**（产不出说明它已被悄悄改成 ①，XS-C2 不通过） |
| `strategy_usable` | **false**；`replaced_by = xs_rank_pool` |
| 用途 | ① 差异证明（解释研究实测选股数为何系统性低于 `t×P`）；② 原 `R1`–`R5` 的历史复现（= `XS-C1`，仅诊断） |

**边界与空值（`xs_rank_pct` 专属；与 `xs_rank_pool` 的差别只有两行）**

| 场景 | 输出 | 与 `xs_rank_pool` 的差别 |
| --- | --- | --- |
| 池内某成员 `x` 为空 | 该成员 `null`；**分母仍计入它** | **保留计入**（③ 的定义；`xs_rank_pool` 是不进分母） |
| 池内仅 1 只且 `x` 非空 | 该成员 = 当日**全样本平均名次**（可达 3,095），**不是 1.0** | 分母 = 1、分子仍是全样本名次；与 `xs_rank_pool` 的 `1.0` 相反，这正是「池内 1 只、全样本 6 个非空 → rk=4.0」反例的形态 |
| 当日池内家数 = 0（即使全样本有非空 x） | 全 `null` | 与 pool 相同 |
| 池内家数 ≥ 1 但池内 `x` 全空 | 全 `null` | 与 pool 相同（分母 >0、无有效名次） |
| `x` 为空 / `mask` 非 True / `mask` 为 null / 池外 | `null` | 与 pool 相同（`mask` 为 null 不计入分母） |
| 值域 | `(0, 全样本非空 ÷ 池内家数]`，max ≈ 2.15–2.17 | **可 >1**（pool 恒 ≤1） |

### 3.3 禁止事项

1. **禁止**用「池外置 null + 现有 `rank`」冒充 `xs_rank_pct`，或把它宣称成研究侧基准。（**v0.2 修订，v0.1 原为「一律禁止」**：该写法本身**就是 `xs_rank_pool` 的权威定义**，见 §3.2.1 口径式与决定四 §7.3-3；被禁的是「用它冒充另一个 id / 冒充研究口径」。）量级差异仍成立：池内最低者 ① 给 `1/n ≈ 0.0007`，③ 会给「全样本名次 ÷ 池内家数」，可到 0.35 量级——两者不可互换。
2. **禁止**用 `in_universe.sum()` 作 `xs_rank_pool` 的分母（XS-A5 指纹：`{0.333,0.667}` vs `{0.5,1.0}`）。
3. **禁止**给 `rank` 加隐式默认掩码（会让所有既有 `rank` 调用方输变，违反 §3.5 回归保护与 XS-A3）。
4. **禁止**把 `mask` 省成字面 `true` 走 `xs_rank_pool`（无掩码 = `xs_rank_market`，另一个 id）。
5. **禁止**在策略文件、seed、执行器里手写 `rank()`/`count()` 重现三者任一（踩「策略必须经因子实现」）。
6. **禁止**用 `xs_rank_pool` 表达「此前 N 日」而不给 `x` 加 `ts_delay`（本算子含当日、算子内不 shift）。
7. **禁止**跨 id 混用于同一策略的验收：尤其不得用 `xs_rank_pct` 的数字验收 `xs_rank_pool`，也不得用 `xs_rank_pool` 去复现 `XS-C1`。

### 3.4 验收判据（逐 id）

**门禁总则**：本节只看**逐位与计数**，不看相关性/平均差（决定四 §1.2-3 已把这条升级为通用规则）。`XS-A4` 依赖 E3：E3 未通过时 `xs_rank_pool` **可以实现、可以过 A1/A2/A3/A5/A6/A7/A8，但策略不得引用**。

#### 3.4.1 `xs_rank_pool`

| # | 判据 | 度量 |
| --- | --- | --- |
| XS-A1 | 值域 | 逐日断言 `max == 1` 且 `min > 0`；**出现任何 `rk > 1` 直接不通过**（一条即可拦住本次事故，无需读实现） |
| XS-A2 | 单日计数恒等式 | `count(rk ≤ t)` 逐日等于「池内 `rank ≤ t×P`」的真实计数，两实现相减**容差 0**；逐日打印 `P`、`count`、`t×P` 三数。`t ∈ {0.05, 0.10, 0.30}`（就是 S06/S07/S10/S11/S12 现用阈值，不新增） |
| XS-A3 | 回归保护 | 无掩码 `rank(x)` 输出与现状**逐位相同**；93 只台账因子抽 20 只做列 hash 对比，逐位不变 |
| XS-A4 | 池内家数逐日与研究一致 | 日均 1,429、逐日差 0。**依赖 E3；E3 未通过 → E2 不可验收**（`P` 本身不可信） |
| XS-A5 | 分母只数池内非空 | 构造单日「池内 3 只、其中 1 只 `x` 为空」→ `{0.5, 1.0}`；得 `{0.333, 0.667}` 则不通过（= 用了 `in_universe.sum()`） |
| XS-A6 | 池空日 | 全 `null`（不是 0，不是 1） |
| XS-A7 | 双路径一致 | 面板 `pipeline.py` 与矩阵 `matrix.py` 逐位差 ≤ `1e-12`，或显式记录 float32 误差来源 |
| XS-A8 | tie 规则 | 4 只同值 → 全部 `0.625`；`{0.25,0.5,0.75,1.0}`（ordinal）或 `{0.25,0.25,0.75,0.75}`（min/max）均不通过 |

#### 3.4.2 `xs_rank_market`

| # | 判据 | 度量 |
| --- | --- | --- |
| XS-B1 | 与 `rank(x)` 逐位相同 | 同输入、同日期、float64，差 0（**待测**，规格侧未实测） |
| XS-B2 | 值域 | `(0, 1]`，逐日 max = 1（当日非空家数 ≥ 1 时） |
| XS-B3 | 策略侧引用计数 = 0 | 扫描策略文件 / seed / 执行器，不得出现该 id |

#### 3.4.3 `xs_rank_pct`

| # | 判据 | 度量 |
| --- | --- | --- |
| XS-C1 | 逐位复现研究 `rk_*`（= 原 `R1`–`R5`） | S07 88 个月末 **55.5 ± 1**、S06 376 个周末 **49.7 ± 1**、S10 88 个月末 **92.8 ± 1**、S11 **14.7 ± 1**；S06/S07/S10/S11 逐调仓日 `jaccard ≥ 0.99`。**仅证明「复现了研究侧的错口径」**：不是策略验收、不是「研究侧已复现」的证据、不得用于任何方向判断 |
| XS-C2 | 必须能产出 `rk > 1` | 取任一调仓日断言 `max > 1`（实测区间 1.78–3.06）；产不出说明它其实是 ① |
| XS-C3 | 策略侧引用计数 = 0 | 同 XS-B3 |

### 3.5 对现有调用方的兼容性

- **纯新增算子**：`rank` / `zscore` / `winsorize` 签名与语义不变；`OPERATORS` 只增三个键。
- 受影响的既有行为：无。`/api/factors/validate` 会多回显 `cross_sectional=true`（仅展示）。
- **策略侧现状**：`backend/app/strategy/seeds/` 25 个 seed 无一引用截面排名（`grep -rl "rank(" backend/app/strategy/` 只命中研究脚本），所以本批不是「改 5 个策略文件」，而是「5 条策略首次落地时必须用对 id」。一旦落地，把 `rank(...)` 写进 `META.scoring` 属策略变更，需研究侧评审。
- `rank_version` 必须递增（G7）：本批口径变更登记为 `rank_version = "xs-rank/20261107.1"`；三 id 的缓存键与 §6.3.3 的 `plan_id` 都含它，旧缓存不得复用。

### 3.6 登记与去重

| id | 登记状态 | `strategy_usable` | `replaced_by` | 去重 |
| --- | --- | --- | --- | --- |
| `xs_rank_pool` | **待注册**（2026-11-07 决定四生效） | **true** | — | 独立因子 |
| `xs_rank_market` | 待注册（仅诊断） | false | `xs_rank_pool` | `numeric_alias_of = rank`，与 `rank` 合计算 1 个因子 |
| `xs_rank_pct` | 待注册（仅差异证明） | false | `xs_rank_pool` | 独立因子（分子分母均与 ① 不同） |

- **`xs_rank_in_pool`（v0.1 §3.6 的「E2-alt，登记但不实现」）废止**：它是 `xs_rank_pool` 的旧名别名，**不得作为独立 id 另行登记**；任何已写入该名的台账改为 `deprecated_alias_of = xs_rank_pool`、`strategy_usable = false`、不计数。实现与 `xs_rank_pool` **同批**，「登记但不实现」这一态不再存在（决定四 §7.5 明确不接受）。
- **两条死列不注册**：`rk_ret60`、`rk_near_high`（研究 `common.py:193-194` 定义行之外引用数 0）。若已登记，标 `strategy_usable = false` 并备注「当前无引用」。
- **试验次数 N = 0**：本批不新增策略、不新增阈值、不新增组合；5 条策略是**重验**，不重置 N。

### 3.7 实施与验收顺序（架构建议；排期由开发经理定，冻结由独立审核 PASS 触发）

| 批次 | 内容 | 可放行判据 |
| --- | --- | --- |
| 1（先，最急） | `xs_rank_pool` + `rank` 回归保护；`xs_rank_market` 随批（同式、低成本） | XS-A1 / A2 / A3 / A5 / A6 / A7 / A8 + XS-B1 / B2 / B3 |
| 2（后补） | `xs_rank_pct`，**仅**差异证明与历史复现 | XS-C1 / C2 / C3 |
| 3（依赖 E3/E4） | 策略引用解禁（顺序 S07 → S11 → S12 → S10 → S06，由研究侧定） | XS-A4 通过 + E4 通过 |

批次 2 可以晚，但**不得把批次 2 的数字当批次 1 的验收**——这正是本次事故的形态。

### 3.8 冲突处置登记（`E2-K1`…`E2-K5`，对应 `XS_RANK_POOL_SPEC` §6 的 C1–C5）

| # | 冲突位置（v0.1 原文） | 处置 | 落点 / 依据 |
| --- | --- | --- | --- |
| E2-K1 | §3.1 末段「先逐位复现…不授权任何一方切换」 | **已改**：删去「先复现 + 双侧保留」的中间态；决定四已授权 `xs_rank_pool` 为唯一策略可用口径，`xs_rank_pct` 降为后补的差异证明 | §3.1 三条事实 + §3.7 批次 2；决定四 §7.3-1、§7.5 |
| E2-K2 | §3.2 边界表「池内有成员 x 为 null → 该成员 null；**分母仍计入它**」 | **已改**：按 id 拆表。该行保留为 `xs_rank_pct` 的定义（§3.2.3）；`xs_rank_pool` 改为「不进分母」（§3.2.1，XS-A5 指纹） | §3.2.1 / §3.2.3 |
| E2-K3 | §3.3-1「**禁止**用『池外置 null + 现有 `rank`』近似（该写法 = 池内分位）」 | **已改（最急）**：该写法就是 `xs_rank_pool` 的权威定义；禁止范围收窄为「禁止用它冒充 `xs_rank_pct` / 冒充研究口径」 | §3.3-1；决定四 §7.3-3 |
| E2-K4 | §3.6 E2-alt `xs_rank_in_pool`「登记但不实现」 | **已改**：废止该名（= `xs_rank_pool` 别名，不得独立登记），`xs_rank_pool` 同批实现 | §3.6 |
| E2-K5 | §3.4 `R1`–`R5`（55.5 / 49.7 / 92.8 / 14.7 ±1、jaccard ≥ 0.99）作为 E2 验收判据 | **已改**：整组移入 `xs_rank_pct` 名下，改编号 `XS-C1`，并注明「仅证明复现了研究的错口径」；`xs_rank_pool` 改用 XS-A1–A8 | §3.4.3 / §3.4.1 |

**未列入 C1–C5、但同类的第 6 处缺陷（架构侧自查，一并修正）**：v0.1 §2.6 `A3`「与 E2 联合复现 S07 = 55.5 ± 1」——E3 的验收不应用 E2 错口径的选股数当靶值。已改为「池内家数 vs 池内该列非空家数逐日可比对、差异可归因」（= XS-A5 的上游）。E3 与研究的池对账仍由 §2.6 `A1`（日均 1,429、逐日 diff 0）承担，不受影响。

---

## 4. E1 全市场宽度 `market_breadth`（截面聚合）

### 4.1 语义
研究口径（`common.py:186-191`）：当日「池内且可算 MA60」的标的中，`close > ma60` 的占比，含当日（收盘可知），广播给当日全部行。

### 4.2 接口（字段级）

**算子**：`xs_mean(x, mask)`

| 项 | 定义 |
| --- | --- |
| `x` | 数值表达式（布尔按 0/1）；通常是 `close > ma60` 这类当日可得谓词 |
| `mask` | 布尔表达式，必填（同上，本算子不接受无掩码形式） |
| 输出 | float64 ∈ `[0,1]`（`x` 为布尔时），**当日所有行同值**（含池外行）；`null` 当 `count(mask & x notnull)==0` |
| 语义 | `mean(x) over date, 仅统计 mask==True 且 x 非空的行` |
| warmup | `max(warmup(x), warmup(mask))`；对 S12 的组合即 `max(60, 120) = 120`，**台账必须登记 120，不得写 60** |
| `cross_sectional` | `True`；同样不得嵌在 TS 窗口内 |

**装配**：`market_breadth = xs_mean(close > ma60, in_universe)`
（`in_universe` 见 §2；`ma60` 是既有注册因子，warmup 60）

**两个视图必须同时提供且逐位一致**
| 视图 | 形态 | 用途 |
| --- | --- | --- |
| 标量表 | `date → float64`（每日一行） | 缓存、复算、对账、月度闸门统计 |
| 广播列 | `(date, symbol) → float64`（同日内恒定） | 与策略谓词同行使用（`market_breadth >= 0.5`） |

一致性判据：对每个 date，广播列的所有值必须等于标量表的值（`max_abs_diff == 0`），且池外行的值也必须广播（不是 null）。

### 4.3 按日一次算、可缓存、可复算
- **最小计算单元 = 一个交易日**；禁止跨日累积状态（宽度与前一日的宽度无关）。
- 缓存键：`(breadth_version, date, 池参数&版本, x 依赖列 digest, mask 依赖列 digest)`；单日命中即跳过重算。
- 复算：给定同一区间与同一版本，重算结果逐位相同（`sha256` over 标量表可比）；**版本或参数变化必须使旧缓存自然失效**（键含版本，不做手工清理）。
- 增量：新增交易日只算新增日；**不得**因为新增一天而改变历史日的值（若历史变化 → 说明用了未来信息或数据被回溯修订，必须报错并递增版本的修订记录）。

### 4.4 空值 / 边界
| 场景 | 输出 | 理由 |
| --- | --- | --- |
| 池空 | `null`（不是 0） | 0 会被 S12 读成「宽度极低，禁止建仓」，是错误结论 |
| 池内全员 `ma60` 为 null | `null` | 分母为 0 |
| `close == ma60` | 计入分母、不计入分子（`>` 严格） | 与研究一致 |
| 首次达到 120 根 bar 的日期之前 | `null` | warmup 不足 |
| 数据缺该交易日 | 该日无行，不插值 | G1/G4 |
| `mask`（`in_universe`）当日全为 `null`（例：`2026-10-20`…`2026-10-29`，见 §2.3 注 2） | `null` | 分母为 0 的另一种成因；**不得**回退成「全样本宽度」——那正是 §4.5-4 禁止的 `approx` 版本 |

### 4.5 禁止事项
1. **禁止**用 `limit_up_count_20d`、`vol_ratio_5d` 等**单标的滚动计数**冒充全市场宽度（语义完全不同）。
2. **禁止**池空返回 0；**禁止**把每日宽度回填到历史日。
3. **禁止**只在月末算宽度再用月末值倒推（研究用的是**当月任一日**的宽度，S12 的闸门按调仓日当日值判定）。
4. **禁止**无掩码版本用于策略判据：无掩码版（全样本可算 ma60 的占比）实测均值 0.4643 vs 掩码 0.5407、19.1% 交易日阈值翻转、月末通过率 34.1% vs 53.4%。若因排期先上无掩码版，台账必须标 `approx=true`，且**不得**被任何策略引用（factor 准入检查拒绝）。

### 4.6 验收判据
| # | 判据 | 度量 |
| --- | --- | --- |
| B1 | 逐日一致 | 1,779 个交易日 `max_abs_diff < 1e-12`；全期均值 **0.540742** |
| B2 | 月末闸门 | `month_end` 日 `breadth ≥ 0.5` 的通过率 **53.4%** |
| B3 | 视图一致 | 标量表 vs 广播列 `max_abs_diff == 0`（含池外行） |
| B4 | 池空语义 | 构造池空日，断言 `null`（非 0）且 S12 当日不建仓 |
| B5 | 复算幂等 | 同区间两次计算结果 hash 相同；增量重算不改历史日 |
| B6 | warmup 声明 | 台账 `warmup_bars = 120`（不是 60），且 `docs/research/factor-audit-20261107/scripts/build_inventory.py` 复跑无「声明 < 实需」 |

---

## 5. E4 调仓日 `rebalance_day`（调仓日历）

### 5.1 先钉死一个已验证的冲突：现网与研究的调仓日不是同一批日期

| 口径 | 定义 | 出处 | 首批日期示例（同一区间） |
| --- | --- | --- | --- |
| **研究口径（本契约采用）** | **每周期最后一个交易日**，信号在该日收盘产生 | `research/strategy-search-20261107/scripts/common.py:161-170` | 2024-01 月 → `2024-01-31` |
| 现网因子回测口径 | **每周期第一个交易日** | `backend/app/backtest/factor.py:1121-1152`（docstring 写「下个周调仓日」，实现取 `seen_weeks`/`seen_months` 首个） | 2024-01 月 → `2024-01-02` |

结论：**`app/backtest/factor.py#_calc_period_return` 的 `rebalance` 不可复用为策略执行调仓日**。它是 IC/分组统计的分组周期，且首日口径与研究相反；直接复用会让 12 条策略的调仓日整体错位一个周期，选股集合与净值全部对不上。本契约要求 E4 是**独立能力**，`factor.py` 保持现状不改（见 §9 对照表「不改」）。

另一处不可用：`app/services/trading_day.py#is_trading_day` 是**实时探针**（可能返回 `None`），只回答「今天是否交易日」，不提供历史日历。历史日历只能来自 G1 的交易日轴。

### 5.2 接口（字段级）

**函数**：`rebalance_calendar(mode, axis, week_rule="dt_week") -> DataFrame`

| 项 | 定义 |
| --- | --- |
| `mode` | `"month_end"` / `"week_end"` / `"month_start"` / `"week_start"` / `"custom"`；**必填，无默认值** |
| `axis` | G1 交易日轴：**完整**（见 §5.3 截断约束），升序去重 `date` 序列 |
| `week_rule` | `"dt_week"`（研究口径，仅比周号不跨年判年）/ `"iso_year_week"`（含年份）；默认 `"dt_week"` 以复现研究 |
| 输出列 | `date`（日期轴全量，一行一日）、`is_rebalance`（bool）、`period_key`（`"YYYY-MM"` 或 `"YYYY-Www"`，`week_rule` 决定周号是否带年）、`next_rebalance_date`（可空） |
| 语义 | `is_rebalance[t] = (next_trading_day(t) 为空) or (period_key(t) != period_key(next_trading_day(t)))` |
| `custom` | 由外部给定 `dates: list[date]`，仅校验「必须是轴上的日期」，**不允许**把非交易日塞进日历 |
| 版本 | `rebalance_version`（G7）；`mode`/`week_rule`/日历算法任何变动递增 |

**单标的可用性不参与日历定义**：调仓日由日历唯一决定，不因为「当日无一只可买」而顺延到下一天（顺延会让回测与实盘产生不可复现的漂移）。当日不可买的标的表现为该标的 `mask=False` 或 `score=null`，日历本身不变。

### 5.3 边界（逐条可断言）

| 场景 | 规定 | 理由 |
| --- | --- | --- |
| **轴被区间截断** | **禁止**用 `[start, end]` 截断后的轴计算 `is_rebalance`。判定 `t` 是否周期末必须看 `t` 的**下一个交易日**是否跨周期；因此 `axis` 必须至少多取「区间末之后一个周期」的尾部 | 否则每个回测段末的日期都会被判为 `month_end`/`week_end`（因 `next_date` 为空而恒真），分段回测与连续回测的调仓日集合不同，X1 与回测永久对不上 |
| 样本最后一天 | 按研究口径 `next_date is null → True`，即**确实是**调仓日 | 全样本最后一个交易日没有下一天，研究中就是调仓日；该条与上一行不冲突：上一行禁的是「人为截断造成的假末尾」 |
| 节假日 | 不特殊处理。节假日不是交易日，天然不在轴上 → 月末即「节前最后一个交易日」 | 用自然日或工作日历会产生「无数据调仓日」 |
| 停牌 | 不特殊处理（同上，停牌日仍有 K 线的标的按 G1 处理；**整日无数据**才从轴上消失） | 停牌是标的问题不是日历问题 |
| 半日市 / 临时休市 | 以行情库当日分区是否有数据为准，不引入交易所日历表 | 单一权威来源（G1） |
| 未上市/已退市标的 | 其 `symbol` 在轴上无行 → 自然不参与 | — |
| 数据缺一天（应交易而未交易） | 该日不在轴上 → 该日不构成调仓日；同时必须报 `data_gap` 审计项 | 静默吞掉会让月末判定错误 |

### 5.4 幂等与确定性
- 纯函数：`(mode, week_rule, axis 内容 hash, rebalance_version)` → 逐位相同输出。同一轴两次调用结果 `sha256` 相同。
- 轴顺序无关（函数内部排序），但**轴的成员集合**必须一致；少了成员就是不同输入。
- 新增交易日只能改变「新交易日及其前一个交易日」的 `is_rebalance` 与 `next_rebalance_date`，**不得**改变更早的历史判定；若改变 → 说明轴被回溯修订，必须报错并递增版本。

### 5.5 禁止事项
1. **禁止**用 `pandas`/`numpy` 的 `MonthEnd`、`resample("M")`、`is_month_end` 等自然日/工作日日历生成调仓日。
2. **禁止**用 `app/backtest/factor.py#_calc_period_return` 复用或改造为执行日历（口径相反，见 §5.1）。
3. **禁止**在调仓日为空仓/无可买标的时顺延或跳过（日历是日历，执行是执行）。
4. **禁止**把 `mode` 默认为 `monthly` 之类的隐式默认；策略必须显式声明。
5. **禁止**在盘中（非收盘后）计算调仓日并用当日未完成 K 线判定月末。

### 5.6 验收判据
| # | 判据 | 度量 |
| --- | --- | --- |
| E4-A1 | 月末计数 | S07 同区间 `month_end` 个数 **88**（与 §3.4.3 `XS-C1` 的 88 个月末同一个集合） |
| E4-A2 | 周末计数 | S06 同区间 `week_end` 个数 **376** |
| E4-A3 | 分段一致 | 把同一区间切成 4 段分别算（每段多取一个周期尾部），并集 == 整段结果；段末无假 `month_end`（构造断言：切点若在月中，切点日 `is_rebalance == False`） |
| E4-A4 | 节假日月 | 春节所在月（如 2024-02）`month_end` == 节前最后一个交易日，`2/29` 不存在于轴上 |
| E4-A5 | 与现网差异可解释 | 同一区间 `factor.py` 首日口径 vs 本契约末日常口径：两集合交集为空、个数相等（除首尾），差异在报告中逐月列出 |
| E4-A6 | 周号规则 | `week_rule="dt_week"` 与 `"iso_year_week"` 在跨年周（如 2023-12-29 / 2024-01-02）的判定差异被显式记录；策略侧必须显式选一个 |

### 5.7 对现有调用方的兼容性
- **纯新增模块**，`rebalance` 字段（`app/api/backtest.py:149`、`app/backtest/factor.py:54,112`）语义不变、不改名。
- 风险提示：新能力上线后，UI 上会同时存在两个「调仓周期」概念（因子统计周期 / 策略执行日历）。**必须在 UI 文案上区分**，否则用户会把「因子回测的月度分组」当成「策略月度调仓」。这是本次契约要求的最小前端改动（文案，不改逻辑）。

### 5.8 与缺口规格的一处口径差异（登记，不隐藏）

`docs/factors/FACTOR_GAP_SPEC_20261107.md:202` 写「以项目交易日历表为唯一权威」。本契约改为「**以行情库当日分区（K 线轴）为唯一权威**」，理由与边界：

| 点 | 缺口规格 | 本契约 | 理由 |
| --- | --- | --- | --- |
| 权威源 | 项目交易日历表 | K 线轴（G1） | 日历「有」而数据「缺」时，用日历会产生一个无数据可算的调仓日 → 该日 `score` 全空 → 空目标 → **错误清仓**。K 线轴天然保证「调仓日必有数据」 |
| 日历的用途 | 作为权威 | **降级为校验器**：`app/services/data_integrity.py#_trading_calendar`（fuyao，可能返回 `None`）若可得，用于发现「应交易而无 K 线」的缺口，报 `data_gap` 审计项 | 保留缺口检测能力，但不让它决定调仓日 |
| 日历不可得 | — | 允许，不影响调仓日计算 | `_trading_calendar()` 返回 `None` 是已知状态 |

---

## 6. X1 生产侧组合级调仓执行器

### 6.1 缺口定位（事实，非判断）

| 能力 | 回测侧 | 生产侧 |
| --- | --- | --- |
| 截面排序 | ✅ `app/backtest/engine.py#_plan_buys`：`candidates.sort(key=lambda i: (-i[1], matrix.symbols[i[0]]))`（第 3496 行） | ❌ 无 |
| 席位上限 | ✅ `slots = max_positions - len(positions)` + `max_daily_entries` 截断 | ⚠️ 仅 `paper_auto` 的 `max_positions`（`paper_auto.py:239-241`，按「已持仓+待成交」计数，逐事件判断） |
| 仓位方式 | ✅ `position_sizing = equal / score_weight / score_tier / policy` | ❌ 仅 `size_mode = fixed_amount / pct_equity`（单笔金额） |
| 触发时点 | ✅ 每个信号日 | ❌ 纯事件驱动（`on_rule_events`），无调仓日概念 |
| 目标持仓 | ✅ 隐含在 `pending_buy_plans` | ❌ 无「目标组合」，只有「这一笔买/卖」 |

结论：**缺的是「目标组合 → 差异 → 订单」这一层**，不是排序算法（排序与权重语义回测侧已有且正确）。因此 X1 的实现原则是**语义单一来源**：排序键、席位、权重、tier 权重公式**必须与 `_plan_buys` 完全一致**，`_plan_buys` 不改；X1 是它的生产侧镜像，不是第二套实现。

### 6.2 边界划分：X1 不含策略语义

X1 只做「把策略在调仓日给出的**可投资集合 + 排序分 + 权重分**变成目标持仓，再变成订单」。
- 买什么：由策略（= 已注册因子 + 参数）在调仓日给出的 `signal`/`score` 决定；
- 卖什么：由策略给出的 `target`（是否仍在目标集合内）决定；
- **X1 不得自己发明卖出规则**（例如「跌出前 N 名就卖」「持有满 N 日就卖」）——那属于策略规格或另一项缺口 X2（`max_hold_days` 生产侧），另立契约。X1 只提供「目标集合变化 → 卖单」的机械转换。

### 6.3 接口（字段级）

**模块（新增）**：`backend/app/strategy/rebalance.py`（名称待系统开发工程师确认，**不得**放进 `paper_auto.py`）

#### 6.3.1 `build_target_portfolio`

```text
build_target_portfolio(
    as_of: date,                 # 调仓日（必须是 §5 日历上的日期，且必须是 G1 轴上的交易日）
    scores: Mapping[str, float | None],   # symbol -> score（排序键，降序）；None = 不可排序
    tier_scores: Mapping[str, float | None],  # symbol -> ranking_score（权重键）；缺省回退 = scores
    eligible: Mapping[str, bool | None],      # symbol -> 是否可投（§2 掩码，三态）
    config: RebalanceConfig,
) -> TargetPortfolio
```

`RebalanceConfig` 字段（与 `MatcherConfig` 同名同义，**只取 X1 需要的子集**）：

| 字段 | 类型 | 默认 | 语义（必须与回测逐字一致） |
| --- | --- | --- | --- |
| `max_positions` | int | 10 | 目标持仓数上限；`<=0` → 空目标（不做任何买入） |
| `position_sizing` | `"equal"`/`"score_weight"`/`"score_tier"` | `"equal"` | `equal`：`1/n`；`score_weight`：`max(tier,0)` 归一（全 0 则回退 `1/n`）；`score_tier`：按 `score_tiers` 分档 |
| `score_tiers` | tuple[(lo,hi,weight)] 或 None | None | 与 `MatcherConfig.score_tiers` 同结构 |
| `score_min` / `score_max` | float 或 None | None | 按 `tier_score` 过滤（回测第 3480-3486 行语义） |
| `max_daily_entries` | int 或 None | None | 单日最多新开仓数 |
| `max_exposure_pct` | float | 1.0 | 目标总仓位上限 |

`TargetPortfolio` 输出：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `as_of` | date | 回显 |
| `picked` | list[{symbol, score, tier_score}] | 已按 `(-score, symbol)` 排序、已截断到 `min(max_positions, max_daily_entries)` |
| `weights` | dict[str, float] | 目标权重（和为 1，或 ≤ `max_exposure_pct`） |
| `skipped` | dict[str, int] | 原因计数：`ineligible` / `score_null` / `score_filtered` / `no_slot` |
| `universe_unknown_count` | int | §1 G3 审计项 |
| `version` | str | `rebalance_version` |

#### 6.3.2 `diff_to_orders`

```text
diff_to_orders(
    target: TargetPortfolio,
    positions: Mapping[str, dict],   # paper.load_positions 原样
    pending_orders: list[dict],      # 未成交订单（含 next_open）
    cash: float,
    lot_size: int = 100,
) -> RebalancePlan
```

`RebalancePlan`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `plan_id` | str | 幂等键（见 §6.5） |
| `sells` | list[{symbol, qty, reason}] | 目标外标的全部卖出（`qty` 受 `paper.sell_capacity` 可用量约束） |
| `buys` | list[{symbol, amount, qty, ref_price, weight_target}] | 排序 = `TargetPortfolio.picked` 顺序 |
| `keeps` | list[str] | 目标内且已持有（不再下单，**不做再平衡加仓**） |
| `unfilled` | list[{symbol, reason}] | `no_cash` / `limit_up` / `suspended` 等 |
| `diagnostics` | dict | 目标权重 vs 现状权重、现金占用、换手估计 |

#### 6.3.3 `execute_plan`

```text
execute_plan(data_dir: Path, plan: RebalancePlan, account_id: str) -> ExecutionReport
```

- **必须**逐笔调用 `app/strategy/paper.py#create_order`（`source=f"rebalance:{plan_id}"`），由 paper 域完成资金/涨跌停/T+1/冻结校验，X1 **不得**自行计算成交或改写持仓。
- 卖单先于买单（释放资金）；同一 `symbol` 不允许同时出现在 `sells` 与 `buys`（`TargetPortfolio` 与现状一致时自然满足；冲突时 fail-closed 报错）。
- `order_type` 固定 `"next_open"`（对齐 G2：T 日收盘产生信号，T+1 开盘成交）；`ref_price` = T 日收盘价（仅供金额换算与校验，不是成交价）。

### 6.4 空值 / 边界

| 场景 | 规定 |
| --- | --- |
| 当日无可投标的（`picked` 空） | 输出空目标：**卖出全部现有持仓**（若 `max_positions>0` 且策略确实给了空集合），并记 `reason="empty_target"`。不得「保持不动」——保持不动等于策略失效时静默持有 |
| `max_positions <= 0` | 不产生任何买单；卖单是否执行由策略目标决定（空目标 → 全卖） |
| `score` 为 null | 该标的不进 `picked`（G4 keep，不填 0 排到末位） |
| `tier_score` 为 null | 权重回退到 `equal` 分配（不得当 0 权重把票投给别人） |
| `eligible` 为 null | 按不可投处理（G3），计入 `universe_unknown_count` |
| 持仓标的不在 `scores` 里（当日无行） | 视为「不在目标集合」→ 卖单；若该标的当日**停牌**（无行），`paper.sell_capacity` 会拒单 → 记 `unfilled`，**次日仍在目标外则继续尝试卖出**（不丢失意图） |
| 目标集合含已持有标的 | `keeps`，不追买至目标权重（首次实现不做再平衡加仓；若要做需递增 `rebalance_version` 并写变更记录） |
| 资金不足 | 按 `picked` 顺序分配，逐个尝试，`unfilled` 记 `no_cash`；**不得**降级为「少买几只但仍等权」这类隐式改口径 |
| 100 股整手 | 由 `paper.qty_from_amount`/`normalize_qty` 处理，X1 不重复实现 |
| 目标权重之和 < 1（`max_exposure_pct<1`） | 按比例缩放，不把剩余资金买最后一只 |
| **全部标的 `eligible` 为 `null`（口径不可判定，不是「空集」）**（v0.3 新增） | **不产生任何订单**（no-op），记 `reason="input_unknown"`，`universe_unknown_count = len(scores)`；**禁止**走 `empty_target` 全卖路径。理由：数据不可用 ≠ 策略判定为空，全卖会把「ST 表被污染」翻译成清仓（判据见 X1-A4 第 5 项） |

### 6.5 幂等与确定性
- `plan_id = sha256(strategy_id, params_digest, as_of, universe_version, rank_version, rebalance_version, account_positions_digest)[:16]`。
- `execute_plan` 前必须查「是否已存在 `source == f"rebalance:{plan_id}"` 的订单」：存在则**直接返回既有报告**，不重复下单（G6）。这是幂等的唯一实现方式，禁止依赖内存标志。
- 同一 `plan_id` 的目标组合必须逐位相同；`account_positions_digest` 变化（期间成交过）会产生新 `plan_id`，属正常重算，不得视为幂等破坏。
- 排序 tie-break：`(-score, symbol)`，与回测 `engine.py:3496` **逐字一致**（G5）。

### 6.6 禁止事项
1. **禁止**在 `paper_auto.py#on_rule_events` 内部加截面排序或占比仓位（会形成第二套语义，事件到达顺序会污染优先级）。
2. **禁止**用监控事件的到达顺序决定买谁（排序只认 `score`）。
3. **禁止** X1 自己写持仓/资金记账（必须经 `paper.create_order` → `paper._fill_order`）。
4. **禁止**在生产侧使用与研究不同的掩码（§2）：同日同策略，回测与生产必须同一 `universe_version`。
5. **禁止**把 `score_weight` 的负分直接取绝对值或加常数平移（回测是 `max(tier,0)`）。
6. **禁止**在盘中用快照价重算当日 `score` 并执行盘中调仓（G2：调仓只在收盘后）。

### 6.7 验收判据
| # | 判据 | 度量 |
| --- | --- | --- |
| X1-A1 | **与回测同一目标** | 取 S07 任一 `month_end`：回测 `_plan_buys` 选中集合 vs X1 `picked` 集合 `jaccard == 1.0`；`weights` 逐位 `max_abs_diff < 1e-12` |
| X1-A2 | 全期一致 | S07 全部 88 个调仓日，逐日集合相等（不是「平均相等」） |
| X1-A3 | 幂等 | 同一 `plan_id` 连续 `execute_plan` 两次：订单数不变、报告 `idempotent_hit=true` |
| X1-A4 | 边界 | 空目标 → 全卖；`max_positions=0` → 无买；`score=null` 不入选；停牌持仓保留卖单意图；**全部 `eligible` 为 `null` → no-op（订单数 0，`reason="input_unknown"`）**；五项各一条断言 |
| X1-A5 | 不越权 | X1 代码路径内不得调用 `save_account`/`replay_positions` 等写接口；资金/涨跌停拒单必须出现在 `unfilled` 而非异常 |
| X1-A6 | 与 paper_auto 不冲突 | 同一账户同时存在 `auto:*` 规则与 `rebalance:*` 计划：同 `symbol+side+同日` 去重，冲突记 `conflict` |

### 6.8 对现有调用方的兼容性
- **新增模块**：`paper_auto.py` / `paper.py` / `monitor.py` 签名与行为**不改**。X1 是新的可选调用方（由调度器在调仓日收盘后触发）。
- `paper_auto` 的 `max_positions`（逐笔守卫，`paper_auto.py:239-241`）与本契约的 `max_positions`（目标席位）字面相同、层次不同。**必须在 UI/规则说明中标明**，否则用户会以为两者等价。同时启用时按 `X1-A6` 去重。

---

## 7. F 类表达式因子注册入口（F1–F7）

### 7.1 实测结论（本契约依据，2026-11-07 复跑 `compile_formula`）

下列公式**全部编译通过**，且 `warmup_bars` 与 `dependencies` 与研究侧 `common.py` 的滚动窗口**逐一吻合**：

| 因子 | `formula_text`（可注册原文） | `warmup_bars` | `dependencies` | 研究侧原文 |
| --- | --- | --- | --- | --- |
| `vol60` | `ts_std(close / ts_delay(close, 1) - 1, 60)` | **61** | `{close}` | `ret1.rolling_std(60)`（`common.py:140`） |
| `ma120` | `ts_mean(close, 120)` | **121** | `{close}` | `close.rolling_mean(120)` |
| `ma200` | `ts_mean(close, 200)` | **201** | `{close}` | `close.rolling_mean(200)` |
| `prior_high_20` | `ts_max(ts_delay(high, 1), 20)` | **21** | `{high}` | `high.shift(1).rolling_max(20)`（`:131`） |
| `prior_high_55` | `ts_max(ts_delay(high, 1), 55)` | **56** | `{high}` | `:132` |
| `prior_high_250` | `ts_max(ts_delay(high, 1), 250)` | **251** | `{high}` | `:133` |
| `prior_low_10` | `ts_min(ts_delay(low, 1), 10)` | **11** | `{low}` | `low.shift(1).rolling_min(10)`（`:134`） |
| `prior_vol_20` | `ts_mean(ts_delay(volume, 1), 20)` | **21** | `{volume}` | `volume.shift(1).rolling_mean(20)`（`:136`） |

**三条必须写进台账的坑（全部实测）**：

1. **`prior_*` 必须带 `ts_delay(...,1)`**。写成 `ts_max(high, 20)` 也编译通过，但**含当日 bar**，与研究 `shift(1)` 差一根 K 线；对 `close > prior_high_20` 这类突破判据会在「创当日新高」时误触发。这是「能编译 ≠ 口径对」的典型，验收必须数值对账，不能只看编译通过。
2. **`prior_vol_20` 是「前 20 日均量」，不是波动率**。名字里 "vol" = volume。写成 `ts_std(close...,20)` 同样编译通过，会得到一个看似合理的波动率因子，且无任何报错。
3. **`change_pct` 的真实风险是「同名不同单位」，不是「数值大 100 倍」**（v0.3 更正，原表述已作废）。三处实测：
   - **因子/策略/指标路径 = 小数**：`change_pct` 是已注册 base 因子（`get_factor("change_pct")` → `kind="base"`, `version=1`）；面板口径 `app/indicators/pipeline.py:538-539` 为 `close / close.shift(1) - 1`，字段文档串 `:156` 明写「日涨跌幅(小数, 如 0.05 = 5%)」；矩阵口径 `app/backtest/matrix.py:4264` → `_valid_return_over_bars`（`:4685-4694`）同为 `close/prev - 1`。研究侧 `ret1` 与系统 `change_pct` 的 `max_abs_diff = 2.22e-16`（因子工程师实测）→ **在因子路径上两者是同一口径，`ts_std(change_pct, 60)` 不会大 100 倍**。
   - **展示/API 路径 = 百分点**：`app/api/intraday.py:72`、`app/api/overview.py:282`、`app/services/market_overview_builder.py:130` 均为 `amount / prev_close * 100`。这些是快照响应字段，不进入因子帧。
   - **provider 适配层有显式换算**：`app/plugins/fuyao/provider.py:273-275` 把外部百分数 `/100` 归一到小数制；`app/plugins/tdxquant/provider.py:18` 声明「小数制」。
   → 因此：**在因子帧内引用 `change_pct` 是合法的**；被禁止的是**跨层取数**（把 API/展示层返回值、或第三方 provider 原始百分数字段塞进因子帧）与**按同名推断单位**。`vol60` 仍建议用上表的 `close / ts_delay(close,1) - 1`，理由改为「依赖面更小（`deps={close}` 而非 `{change_pct}`）、与研究 `common.py:140` 逐字同源、不受 `change_pct` 未来口径变更影响」。

另注：研究侧 `vol60` **未年化**。若要年化口径，必须是**另一个因子 id**（如 `uf_vol60_ann`），禁止原地改公式。

### 7.2 注册元数据字段（`FactorSpec` 逐字段填写规则）

`backend/app/factors/registry.py:33-56` 的 `FactorSpec` 是唯一权威；F 类作为 `kind="custom"` 经 `app/factors/store.py#to_spec` 落盘。

| 字段 | F 类必填 | 规则 | 现状 |
| --- | --- | --- | --- |
| `id` | ✅ | **必须匹配 `^uf_[a-z0-9_]{1,40}$`**（`store.py:22`）→ `uf_vol60`、`uf_prior_high_250` | ✅ 已校验 |
| `label` | ✅ | 中文可读名，≤32 字 | ✅ |
| `group` | ✅ | 建议单列 `"研究补充"`，不要塞进既有分组（会打乱前端分组顺序） | ✅ |
| `formula` / `formula_text` | ✅ | §7.1 原文，≤2000 字符 | ✅ |
| `kind` | ✅ | 固定 `"custom"` | ✅ |
| `lang` | ✅ | 固定 `"dsl"` | ✅ |
| `version` | ✅ | 从 1 起；**公式文本任何字符变化必须 +1** | ✅ `register_factor` 拒绝版本未提升 |
| `warmup_bars` | ⛔ 不手填 | DSL 路径由编译推导（`to_spec` 直接取 `compiled.warmup_bars`），手填无效 | ✅ 自动 |
| `dependencies` | ⛔ 不手填 | 同上；§7.1 表用于**对账**，不是输入 | ✅ 自动 |
| `null_policy` | — | 固定 `"keep"`（G4）；`to_spec` 不暴露 → 默认即 keep | ✅ 默认 |
| `direction` | ✅ | `high`/`low`/`none`；**未经检验一律 `none`** | ✅ |
| `status` | ✅ | `draft`/`active`/`watch`/`retired`；`active` → `stability="stable"` | ⚠️ **只落在 JSON 定义；`FactorSpec` 无 `status` 字段**（`registry.py:33-56` 的 21 个字段里没有它），`to_spec` 仅投影为 `stability`（`store.py:94`、`:110`、`:165`）后丢弃 → 见 §7.7 |
| `unit` | ⚠️ 不落盘 | `to_spec` 不读，P1 统一 `"none"`。`vol60` 是 ratio、`prior_high_20` 是价格 → 只能在台账文档登记 | ⚠️ 缺口 |
| `scale_free` | ⚠️ 不落盘 | 同上；`prior_high_*` 是价格量纲（非 scale-free），`vol60` 是 scale-free，注册时无法声明 | ⚠️ 缺口 |
| `asset_types` | ⚠️ 不落盘 | 默认 `{stock, etf}`；八只对 ETF 同样成立，可接受 | ⚠️ |
| `pit`/`pit_source` | — | 全部 `False`/`"none"`（日频量价，无公告时点） | ✅ 默认 |
| `tags` | ⚠️ 不落盘 | `to_spec` 不读 | ⚠️ |

**结论（区分「现有已够 / 需扩参」）**
- **链路已够**：`compile_formula` → `store.to_spec` → `register_factor` 三段齐全；`id/label/group/formula/version/status/direction` 六字段足以把 §7.1 八只注册进去，**不需要改引擎**。
- **需扩参（P2，可选）**：`unit`/`scale_free`/`asset_types`/`tags` 在 `to_spec` 中缺失，导致「价格量纲因子」与「比率因子」在注册表里不可区分。这是**新增可选字段**（`FactorSpec` 已有默认值），不改任何现有调用方语义。本期若不做，必须在台账 md 手工登记，并禁止任何自动加权逻辑依赖这些字段。

### 7.3 注册前置校验（逐条）
| # | 校验 | 现状 |
| --- | --- | --- |
| V1 | `compile_formula(...).ok` | ✅ `store.to_spec`、`api/factors.py:293` |
| V2 | 保存前最近 40 交易日有非空输出 | ✅ `api/factors.py#_trial_nonempty` |
| V3 | **与研究工作帧数值对账**：同 symbol 区间逐值 `max_abs_diff < 1e-12` | ❌ **无**；本次契约要求补，但可作为人工步骤 + 落盘报告，不必进 API |
| V4 | `warmup_bars` ≥ 实需 | ✅ DSL 推导即实需；python 路径 `max(declared, compiled)` |
| V5 | 注册后 `docs/research/factor-audit-20261107/scripts/build_inventory.py` 复跑无「声明 < 实需」告警 | ✅ 已有流程 |

### 7.4 幂等
- 同一 `(id, formula 摘要, dependencies, warmup)` 重复 POST：现状每次 `_next_version()` +1，**不幂等**，且会让 `materialize_cache` 的键（含 `spec.version`）全部失效 → 整表重算。
- 要求：内容未变则返回既有定义、`version` 不变、响应标 `unchanged=true`；仅内容变化才 +1。改动点仅在 `api/factors.py` 保存分支，**不动 `registry`/`dsl`/`store`**。

### 7.5 禁止事项
1. **禁止**把 `prior_*` 写成不含 `ts_delay` 的形式。
2. **禁止**跨层取数构造因子：不得把 API/展示层返回值（`api/intraday.py:72` 等百分点字段）或 provider 原始百分数字段直接喂进因子帧；一个因子只能引用因子帧内的列。`change_pct` 在因子帧内是小数（`pipeline.py:156`），可直接引用（v0.3 更正）。
3. **禁止**同一口径起两个 id 并用于同一策略；研究名 ↔ `uf_` id 映射必须唯一并登记在 `docs/factors/` 台账。
4. **禁止**手填 `warmup_bars`/`dependencies`（DSL 路径会被静默覆盖，手填值是幻觉）。
5. **禁止**给未通过 V3 的因子标 `status="active"`。
6. **禁止**把 `status` 当运行时闸门（v0.3 新增）：运行时对象 `FactorSpec` 里没有 `status`（§7.7.1），「已标 active 所以可用」在代码里没有依据；闸门落地前 `status` 仅为登记字段，准入必须走 §7.7 的 `assert_factors_usable`。

### 7.6 验收判据
| # | 判据 | 度量 |
| --- | --- | --- |
| F-A1 | 八只全部可 `get_factor` | `uf_vol60`/`uf_ma120`/`uf_ma200`/`uf_prior_high_20`/`uf_prior_high_55`/`uf_prior_high_250`/`uf_prior_low_10`/`uf_prior_vol_20` |
| F-A2 | warmup 一致 | 逐一等于 61/121/201/21/56/251/11/21 |
| F-A3 | 数值对账 | 8 只 × 20 symbol × 近 250 交易日，与研究 `add_indicators` 逐值 `max_abs_diff < 1e-12` |
| F-A4 | 命名映射唯一 | 台账中研究名 ↔ `uf_` id 一对一 |
| F-A5 | 幂等 | 同内容二次注册：`version` 不变、响应 `unchanged=true`、盘上文件字节与 mtime 均不变（→ 目录指纹不变 → 依赖指纹的缓存不全表失效）。**实现现状（2026-11-07 15:44 复核）**：工作区已有**未提交**实现 `backend/app/factors/store.py:207-257`（`content_signature` / `is_same_content` / `upsert_definition`）+ `backend/app/api/factors.py:333-360`；HEAD `65c6e42f`（2026-11-07 12:56:05 +0800）中**没有**这部分（`git show HEAD:backend/app/factors/store.py` 内 `unchanged` 命中数 = 0）；`git status` 显示两文件为 `M`，mtime 15:35:28。**判据状态 = 待独立审核**，通过前不得记为已满足；靶值（version 不变 + `unchanged=true` + 文件未写）可直接按现实现复跑。 |
| F-A6a | 量纲（中位数） | 评估域：`60*`/`00*` 前缀 × `2019-01-01` 起 × 逐 symbol `ret1 = close/close.shift(1)-1` 的 `rolling_std(60, min_samples=60, ddof=1)` × 仅非空 × `n ≥ 5.0e6`。判据：`p50 ∈ [0.015, 0.06]` |
| F-A6b | 上尾 | 同一评估域：`p99 < 0.10` |
| F-A6c | 下尾 | 同一评估域：`p01 ∈ (0, 0.02)` |
| F-A6 | 判定 | `F-A6a ∧ F-A6b ∧ F-A6c` 同时成立 = pass；任一不满足 = fail，且失败报告**必须**打印实测 `p01/p50/p99` 与「若为百分点口径的预期值（×100）」以便一眼定位。**记录值**（2026-11-07 复算）：架构师独立复算（本机 `backend/.venv` polars，raw close，`60*`/`00*`，`2019-01-01`–`2026-10-29`，`n=5,639,581`）= mean **0.026555** / p01 **0.009244** / p50 **0.025096** / p99 **0.056152**；开发经理复算（`n=5,469,335`）= 0.0261 / 0.0090 / 0.0247 / 0.0549（样本窗与是否用复权价不同，量级一致）。**原「典型值 0.015–0.06，越界即 fail」按字面会误判**：全样本 1% 的行合法地低于 0.015（p01=0.0092）。判据区分力：百分点口径 p50≈2.5、方差口径 p50≈0.0006、年化口径 p50≈0.39，三者分别落在上界/下界外 |

### 7.7 `status` 闸门（v0.3 新增；直接约束批二 E1/E2 的验收设计）

#### 7.7.1 事实（逐条实测）

| # | 事实 | 依据 |
| --- | --- | --- |
| 1 | 运行时对象 `FactorSpec` **没有** `status` 字段 | `app/factors/registry.py:33-56` 的字段清单（21 个）无 `status`；`hasattr(spec,"status") == False`，`getattr(spec,"status",None) is None` |
| 2 | `status` 只活在 JSON 定义里，并在 `to_spec` 时被**投影为 `stability`**（`active → stable`，其余 `experimental`）后丢弃 | `store.py:66-68`（取值校验）、`:94`、`:110`、`:165` |
| 3 | 没有任何计算/加载路径读 `status` 做准入 | `grep -rn "status" backend/app/factors/registry.py` 零命中 |
| 4 | `POST /custom/{id}/status` 确实存在，但只改 JSON + `unregister → register`，不构成闸门 | `api/factors.py:510-531` |
| 5 | 结论：§7.5-5「未过 V3 不得标 active」**当前只是登记纪律，运行时没有闸门**；`draft` 因子可被策略、回测、执行器直接引用 | 上 1–4 |

#### 7.7.2 决策：两层落地，闸门放在「消费入口」，不放在求值层

**数据层（P2 扩字段，与 §7.2 的 `unit`/`scale_free` 同批）**：`FactorSpec` 末尾新增 `status: Literal["draft","active","watch","retired"] = "draft"`；`store.to_spec` 的三个分支（dsl / python / composite）填入同一个值。默认 `draft` 是**安全方向**（漏填 → 拒绝，而不是放行）；新字段带默认值，现有构造调用不受影响。

**闸门层（单一实现，禁止各入口各写一遍）**：新增 `app/factors/gate.py#assert_factors_usable(factor_ids, mode, *, allow_non_active=False, allow_retired=False) -> GateReport`。
- `GateReport` 字段（固定，便于验收断言）：`ok: bool`、`blocked: tuple[(factor_id, status, code)]`、`non_active: tuple[str, ...]`、`unknown: tuple[str, ...]`、`mode: str`、`historical_only: bool`。
- 判定矩阵（机械可判）：

| status | `mode="production"` | `mode="research"` |
| --- | --- | --- |
| `active` | 允许 | 允许 |
| `watch` | **拒绝** `FS01` | 允许，记入 `non_active` |
| `draft` | **拒绝** `FS01` | 仅当 `allow_non_active=true` 允许，记入 `non_active`；否则 `FS01` |
| `retired` | **拒绝** `FS01` | 仅当 `allow_retired=true` 允许，报告标 `historical_only=true`；否则 `FS01` |
| 未登记（registry 与 custom store 都没有） | **拒绝** `FS02` | **拒绝** `FS02` |
| `kind == "base"` | 不适用（base 无 status；其准入由台账 G1–G3 承担） | 同左 |

**为什么放在入口而不是求值层**：① 求值层（`scoring.py#materialize_scoring_columns`、`matrix.py#_compute_matrix_feature`）是逐列热路径，闸门放那里等于每帧重判；② 同一因子被不同调用方引用时必须结论一致，判定只能发生在「谁在用」这一层；③ 回测允许 `draft`（研究要试）而生产不允许（钱），这个差异只有入口知道。

#### 7.7.3 调用点（逐个接，不留实现者猜）

| 入口 | 位置 | mode | 说明 |
| --- | --- | --- | --- |
| 因子校验接口 | `app/api/factors.py:78` `POST /validate` | research | `allow_non_active=true`，响应附 `non_active` |
| 策略保存/更新 | `app/api/strategy.py:473` `POST /config`、`:493` `PATCH /config` | research | 引用 `draft` 且未显式允许 → 400 `FS01`；允许时把 `non_active` 写进策略元数据 |
| 回测入口 | `app/api/backtest.py`（`FactorConfig` 解析后、`engine.run_backtest` 前） | research | 回测报告必须带 `non_active_factors`；同一次回测内不得混用两种判定 |
| X1 组合级执行 | `app/strategy/rebalance.py#build_target_portfolio`（§6.3.1） | production | 只认 `active`；拒绝即 fail-closed，整计划不生成 |
| 生产自动执行 | `app/strategy/paper_auto.py#on_rule_events` 装载规则时 | production | 同上 |
| 因子求值 | `scoring.py#materialize_scoring_columns`、`matrix.py#_compute_matrix_feature` | — | **不 gate**（见 7.7.2 理由） |

#### 7.7.4 与 E1/E2 的关系（批二验收按此设计）

1. E1（`xs_mean`）与 E2（三个 `xs_rank_*`）是**算子**，不是可登记因子，`status` 闸门看不见它们 → 它们的版本纪律由 `rank_version` / `breadth_version` 承担，**不参与 status 判定**。
2. 若 E2 的三个 id 以「别名因子」形式登记（供诊断与台账引用），同样受闸门约束：`xs_rank_pct` 的 status 必须是 `watch` 或 `retired`，**不得 `active`**（它只用于历史复现与差异证明）；`xs_rank_market` 同理。`xs_rank_pool` 在 XS-A1–A8 全过并经独立审核后方可 `active`。
3. 批二验收因此分两段：**数值段**验算子/因子的口径判据（§3.4 / §4.6），**闸门段**验「引用一个 `draft` 别名因子时生产入口拒绝、研究入口按 `allow_non_active` 放行（并回报）」。两段都过才算可用。

#### 7.7.5 错误码（新增命名空间，不与 DSL `E0xx`、T2 `E2xx` 冲突）

| 码 | 含义 | 触发 | 处置 |
| --- | --- | --- | --- |
| `FS01` | 因子状态不允许在该模式使用 | 7.7.2 矩阵 | 400；`detail` 含 `factor_id` / `status` / `mode` |
| `FS02` | 因子未登记 | 既不在 `registry` 也不在 `custom_factors` | 400，fail-closed（G8） |

#### 7.7.6 版本与缓存

- `status` 变更**不改数值**。当前内容签名把 `status` 计入（`store.py:183-191` 节注释；`_NON_CONTENT_FIELDS` 定义在 `:189`，只排除 `version/created_at/updated_at`）→ 改状态会抬版本 → 该因子 `materialize_cache` 键变化 → **单因子重算一次**。这是**可接受的代价**（数值逐位不变，只花一次算力），本条按现状登记，不要求改实现。
- 硬要求：`status` 变更后重算结果必须与变更前**逐位相同**（`max_abs_diff == 0`）；若不同，说明 status 实际影响了计算，属缺陷。
- 若后续把 `status` 移出内容签名（省掉这次重算），**必须同时**落状态审计（`status_history`：谁 / 何时 / 依据哪份报告 digest），否则治理链断裂。

#### 7.7.7 验收判据（与 §7.6 同表编号）

| # | 判据 | 度量 |
| --- | --- | --- |
| F-A7 | 运行时可见 | `get_factor("<uf_*>").status` 返回四个合法值之一（字段已落 `FactorSpec`）；`getattr(..., "status", None)` 不再是 `None` |
| F-A8 | 闸门可判 | 同一因子依次置 `draft/watch/active/retired`，`assert_factors_usable` 在 `production`/`research` 两模式下的 8 个组合逐个等于 7.7.2 矩阵；`FS01`/`FS02` 逐字匹配 |
| F-A9 | 不可绕过 | `production` 模式引用 `draft` 因子：X1 计划不生成、`paper_auto` 规则装载失败；断言「订单数 == 0」且报告含 `FS01` |

---

## 8. 改动性质总表（改引擎 / 新增模块 / 现有已够）

| 能力 | 改动性质 | 落点 | 说明 |
| --- | --- | --- | --- |
| E3 掩码 `in_universe` | **新增模块** | 新因子 id（`uf_in_universe` 或 Provider 因子）+ 数据源列（停牌/涨停/退市/上市天数） | 不改 DSL 内核；若走 Provider 需 `app/extensions/factors` 注册 |
| E2 截面排名族（`xs_rank_pool` / `xs_rank_market` / `xs_rank_pct`） | **改引擎（扩算子）** | `app/factors/dsl.py#OPERATORS` + `CROSS_OPERATORS` + 编译/求值分支；`_compiled_payload` 的 `cross_sectional` 已有字段可直接复用 | 纯新增三个算子键，`rank`/`zscore`/`winsorize` 不变；需新增错误码 `E017`；`xs_rank_market` 登记为 `rank` 的数值别名（不重复计数） |
| E1 `xs_mean` | **改引擎（扩算子）** | 同上 | 与 E2 同一批改动，建议一次做完 |
| E4 调仓日历 | **新增模块** | 新模块（建议 `app/backtest/rebalance_calendar.py` 或并入 §6 的 `rebalance.py`） | **不改** `app/backtest/factor.py#_calc_period_return` |
| X1 生产侧调仓执行器 | **新增模块** | 新文件 `app/strategy/rebalance.py` | 复用 `paper.create_order`，`paper_auto` 不改 |
| F 因子注册（八只） | **现有已够** | 走 `POST /api/factors/custom`（`CustomFactorCreateRequest`） | 唯一缺口是数值对账（V3）与注册幂等（§7.4，扩参级） |
| D2 `rsi_14_pct`（Wilder 平滑、涨跌幅口径） | **新增模块（新增 base 列；不改 DSL 算子层）** | `registry.py#FACTOR_SPECS` 新增 `_base("rsi_14_pct", …)`；`indicators/pipeline.py` 新增一列（`ewm_mean(alpha=1/14, adjust=False)`，与 `:576-577` 同法）；`backtest/matrix.py#_MATRIX_COMPUTED_FEATURES` + `#_compute_matrix_feature` 新增分支 | `dsl.py#OPERATORS` 实测 **25** 个键（`len(OPERATORS)==25`；因子工程师文档写「26」，差 1 属计数差异），**无 `ewm`/`ewma`/`wilders`**；但 `ewm_mean` 在指标层已用于 `rsi_6/14/24`（`pipeline.py:576-577`）与 `atr_14`（`:503`）→ 不必扩算子。**不新增错误码**；若强行扩算子则需 `E018`（`E017` 已被 E2 掩码占用）。落点裁定与被否决方案见 §8.1 |
| **`ewm` / Wilder 平滑算子**（引擎能力缺口，v0.3 登记） | **不改引擎：否决扩算子** | 不落 `app/factors/dsl.py#OPERATORS`（保持 **25** 键，`TS_OPERATORS` 13 / `CROSS_OPERATORS` 3 不变）；策略侧仍不能用 DSL 写 `ewm(...)`，编译期按未知算子返回 **`E002`**（判据 F-A13）；若日后改判为扩算子，则需 `TS_OPERATORS` 13→14 + 新错误码 **`E018`**（`E017` 已被 E2 掩码占用）+ 面板/矩阵两条求值路径逐位一致 | 派单把它登记为「引擎能力缺口（改引擎）」，架构裁定为**不扩**：Wilder 平滑在指标层已存在（`pipeline.py:576-577`、`:503`），`rsi_14_pct` 改走 base 列（§8.1）。故本条的真实改动性质是「新增 base 列」，不是「改算子层」；`E018` 仅预留给「改判后」的场景，**当前没有任何代码路径会返回它** |
| 因子回测 `rebalance` 字段 | **不改** | `app/api/backtest.py:149`、`app/backtest/factor.py:54,112` | 语义为统计分组周期；仅需 UI 文案区分 |
| 回测排序与仓位 | **不改** | `app/backtest/engine.py#_plan_buys`（3496 行排序、3514-3518 权重） | X1 逐字镜像它，不重写 |

**为什么 E1/E2 必须改引擎而不是新增模块**：掩码截面排名需要「分子与分母取同一批（池内非空）样本」，而另两个 id 分别是全样本口径与混合分母口径（§3.1 表），这是 polars 表达式层的一次分组聚合，必须在 DSL 编译期知道 `cross_sectional=True` 才能阻止其被嵌进时序窗口（沿用 `E009` 纪律）。放在策略层或后处理层做，会被 `materialize_scoring_columns` 的窗口补算路径吃掉，且无法被 `/api/factors/validate` 提前拦住。

### 8.1 `rsi_14_pct`（D2）落点裁定：base 列，不动 DSL 算子层（v0.3 新增）

**事实（实测）**
- `app/factors/dsl.py#OPERATORS` 现有 **25** 个键（`len(OPERATORS)==25`；`TS_OPERATORS` 13、`CROSS_OPERATORS` 3），**无 `ewm`/`ewma`/`wilders` 类算子**；`ts_mean` 是等权滑动均值，**不能**表达 Wilder 递推。（因子工程师 `F_CLASS_REGISTRATION_20261107.md:224` 写「OPERATORS 26 个」，与实测差 1，属计数差异；结论相同：没有 ewm。）
- 指标层**已有** Wilder 平滑：`rsi_6/14/24` 用 `pl.col("_gain").ewm_mean(alpha=a, adjust=False)`（`app/indicators/pipeline.py:576-577`，`a = 1/n`），`atr_14` 同法（`:503`），`ema5…ema60` 亦为 `ewm_mean`（`:417-429`）。
- `rsi_14` 已是 base 因子（`registry.py:108`）；`rsi_14_pct` 与它**只差输入**（`pct_change` vs `close.diff()`），算法同为 `ewm(alpha=1/14, adjust=False)`（`FACTOR_GAP_SPEC` §D2）。
- 既有缺口：`rsi_14` 的 `_base(...)` 未传 `warmup_bars`（`registry.py:108`，默认 1），而 Wilder 递推同样需要长预热 → 同一数值风险**已存在于 S04 现用因子**。本条只登记，不扩大范围修正既有因子。

**裁定：`rsi_14_pct` = 新增 base 列（面板 + 矩阵两条路径各一处实现），不改 `dsl.py#OPERATORS`。**
落点（字段级）：
1. `app/factors/registry.py#FACTOR_SPECS` 新增 `_base("rsi_14_pct", "RSI(14,涨跌幅)", "超买超卖", "14日相对强弱指标(涨跌幅口径)", warmup_bars=373)`；base 因子 `dependencies` 为空集（= 已物化列自身），`unit="index"`、`scale_free=false` 只能登记在台账（§7.2 的 P2 缺口）。
2. `app/indicators/pipeline.py` 新增一列：复用 `:576-577` 的 `_gain/_loss + ewm_mean(alpha=1/14, adjust=False)` 写法，输入改为 `pct_change`；`1e-12` 护栏是否沿用，须与 D2 的 `max_abs_diff < 1e-10` 对账后决定（不得为了「除零好看」改变判据）。
3. `app/backtest/matrix.py#_MATRIX_COMPUTED_FEATURES` + `#_compute_matrix_feature` 新增分支：矩阵路径是逐元素 numpy 实现，**必须与面板路径逐位一致**（这是本条最大的实现风险，见 F-A11）。
4. 台账（`docs/factors/`）登记：口径 `price_pct`、`unit="index"`、`scale_free=false`；D2 已定 `rsi_14` 不得被策略引用，`replaced_by` 反向指向 `rsi_14_pct`。

**warmup 必须写 373，不是 28（推导）**
Wilder 是无限记忆递推，初值影响按 `(1-alpha)^n` 衰减；`alpha=1/14` → `(13/14)^n`。要求 `(13/14)^n < 1e-12` 得 **n ≥ 373**（`ln(1e-12)/ln(13/14) = 372.85`）；对 D2 的 `1e-10` 门槛只需 **311**。若从窗口中间起算却只预热十几根（`py_expr` 的自动推断给的是 `span = 2/alpha - 1 = 27`），窗口首段与全量计算必然不一致 → `max_abs_diff < 1e-10` 会在每只股票前约 300 行失败。允许的等价替代：**自该 symbol 首根 bar 起算**；此时 `warmup_bars` 仍须声明 373，以免增量重算时被截断。

**被否决的方案（附代价）**

| 方案 | 代价 | 为什么否决 |
| --- | --- | --- |
| 扩 DSL 算子 `ewm(x, alpha)` | `OPERATORS` 25→26、`TS_OPERATORS` 13→14；新增 `alpha∈(0,1)`/`span≥1` 常量校验（复用 `E003`/`E004`）；warmup 推导；`_rolling_apply` 与矩阵逐元素两条求值路径都要验逐位一致；与 `E009`（截面算子不得嵌入时序窗口）的交互要重验；错误码需 `E018`（`E017` 已被 E2 掩码占用） | 只为 1 个**已定死** `alpha=1/14` 的因子扩语言；扩完策略侧即获得「任意 alpha」的自由度，台账无法穷举口径组合，违反 G7 可穷举版本化 |
| 注册为 `lang="python"` 的 T2 表达式因子（`py_expr.py` 支持 `ewm_mean`） | `py_expr` 的 warmup 推断按 `span = 2/alpha - 1 = 27` 计（`py_expr.py:106-112`）→ 声明 28 根，比 311 少一个数量级 → 数值对账必然失败；T2 不承载量纲/口径治理（`unit`/`scale_free` 不落盘）；T2 是「用户自建定义」通道，不应承载策略关键口径 | 省一次代码，换来永久的 `max_abs_diff` 不稳定 |
| 用 `ts_mean(ret1, 14)` 近似 Wilder | 口径不同 | 违反 G8；`RSI<30` 的 jaccard 必掉，D2 的 `≥0.999` 直接不成立 |

**验收判据（并入 §7.6 编号）**

| # | 判据 | 度量 |
| --- | --- | --- |
| F-A10 | 口径 | 与研究 `rsi14` 逐值 `max_abs_diff < 1e-10`；`RSI<30` 判定 `jaccard ≥ 0.999` |
| F-A11 | 双路径一致 | 面板路径 vs 矩阵路径逐位 `max_abs_diff < 1e-10`，且 NaN 位置逐个一致 |
| F-A12 | warmup | 声明值 ≥ 311（1e-10 门槛），契约取值 373；构造「自首根 bar 起算」与「预热 373 根后起算」两组，逐位一致 |
| F-A13 | 不越权 | 策略侧仍**不能**用 DSL 直接写 Wilder 平滑（`ewm(...)` 仍返回 `E002`），只能引用 `rsi_14_pct`；`rsi_14` 未被任何策略引用（D2） |

---

## 9. 未覆盖与依赖

| 项 | 状态 |
| --- | --- |
| E1/E2/E3/E4/X1/F 契约 | 本文件 **v0.3（草案）**；v0.2 修订 §3 与 §2.6 `A3`；v0.3 为六处证据回灌（§2.2/§2.3/§2.6/§4.4/§6.4/§7.1/§7.6/§7.7/§8.1），逐条见 `docs/architecture/CONTRACT_REVISION_R2_20261107.md` |
| `max_hold_days` 生产侧（X2） | **不在本契约**，另立 |
| D1/D2/D3 口径决策 | 属因子工程师，本文件只引用不裁定 |
| 决定四（截面排名口径） | 由研究侧定稿（v1.2）；本文件只做字段级落地与判据锚定，冲突以决定四为准 |
| G1–G3 台账治理 | 不在本契约 |
| 停牌/涨停/退市/上市天数的**数据可得性** | 未验证；E3 的实现前提是行情库或 sidecar 有这些字段，属行情数据工程师职责 |
| **ST 历史表的数据质量**（v0.3 新增） | 已确证：`2026-10-20` 批量 198 行 `st_flag=false`，as-of ST 家数 218 → 20（§2.3 注 2）；数据末端 `2026-10-29`，之后无行（注 3）。**修数据源不在本部门范围**（属行情数据工程师）。契约侧只做三件事：窗口置 `null`（§2.3）、末端不外推（注 3）、X1 不清仓（§6.4） |
| **`status` 运行时闸门**（v0.3 新增） | 契约已定（§7.7），实现未落：`FactorSpec` 无 `status`（`registry.py:33-56`）、`app/factors/gate.py` 不存在。属批二前置 |
| **`rsi_14_pct` 的既有同族风险** | 已登记未修：`rsi_14`（`registry.py:108`）未声明 warmup（默认 1），与 §8.1 的 373 推导同一问题；不在本契约范围 |
| **F-A5 实现的审核状态** | 工作区有未提交实现（`store.py:207-257`），HEAD 无；独立审核未覆盖 → 判据待复核 |
| 实现与验收 | 分别由系统开发工程师、独立审核工程师承担；**本文件不下验收结论** |

**本契约不包含**：任何收益数字、参数调优建议、策略优劣判断。§4.6 出现的「平均值/通过率」是**口径复现靶值**（证明实现与研究同源），不是绩效结论；§3.4.3 `XS-C1` 的选股数与一致率是 `xs_rank_pct` 对**研究侧历史错口径**的复现证据，既不是策略验收，也不是任何实现的合格线。

---

本文件正文 sha256：`b082d902e08df2dc902f97d694dcd2e1ae96d93bd79485a66647470915f9bfef`（校验：`head -c 89350 "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md" | sha256sum`）· 行数 914 · 生成 2026-11-07 v0.3（六处证据回灌 R2 + 收尾三处：§2.2 `st_flag` 三态、§8 `ewm`/Wilder 缺口行、§7 行号引用校正）· 冻结 2026-11-07 15:51（Asia/Shanghai，此后不再改动；任何改动必须重算本行四字段并递增版本）
