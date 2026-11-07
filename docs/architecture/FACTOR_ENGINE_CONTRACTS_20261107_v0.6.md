# 因子化引擎与生产侧执行器 —— 接口契约 v0.5（2026-11-07）

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
| v0.4 | 2026-11-07 | 三处裁定（R3）：①§7.4 改为「允许 store 新增幂等入口、禁止改既有写盘语义与 fail-closed」，并与 §7.6 `F-A5` 自洽；②新增 §7.8 双 id / 别名 / 不可复算因子的闸门契约（`alias_of` 解析、`FS03`–`FS06`、按可复算性分类、`lang="python"` 分支、过渡期存量豁免、`F-A14`–`F-A17`）；③§8.1 预热拆成两套语义（引擎/矩阵 `warmup_bars=600`；研究/策略首可用 bar + `min_history_bars=15`），并写死 `al=0 → 100`、`ag=0∧al=0 → null` 与两个报数项。逐条原句/新句/依据/可复跑命令见 `docs/architecture/CONTRACT_REVISION_R3_20261107.md`；**v0.3 冻结态（89,833 B / 914 行 / 全文 `5eb97724…565903`）已逐字节归档**至 `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`（sha256 相同），原审核绑定对象不销毁 | 开发经理批一b/批二前置三点 + 架构师本机实测复算 |
| v0.4（冻结） | 2026-11-07 | **R4（冻结版定稿）**：①§7.4 改为**函数级允许面**，对 `store.py` 的引用改按符号（行号仅参考，锚定快照 19,502 B / 409 行 / `de77eae6…701199`），并写死「允许的新增 9 个符号 + 允许的既有变更 1 处 + 禁止面 5 条」；②新增 **§7.9** `POST /custom` 对既有定义的 `status` 处置（保留盘上状态；内容变化才回 `draft`；四分支 R1–R4 + `F-A18`–`F-A21`）；③新增 **§7.10** `referenced_factor_inventory` 先行 + L0–L3 分级放行（含命名空间优先级 N1–N3、逐 id 结论、`F-A22`–`F-A29`）。逐条原句/新句/依据/可复跑命令见 `docs/architecture/CONTRACT_REVISION_R4_20261107.md`；**本版冻结，此后不再改动** | 开发经理批二前置四点 + 架构师本机实测复算（16:30–16:42）|
| v0.5（追认） | 2026-11-07 | **R5（只追加，不改 v0.4 正文语义）**：①§7.4.2 允许面补 2 项 —— 新增只读包装 `load_one`（HEAD `65c6e42f` 中 `def load_one` 命中 0，v0.4 §7.4.3-1 把它写成「语义不变」是事实错误）；调用方变更由 1 处扩为 2 处（`POST /custom` + `POST /composite`，并按 `F-A5` 未限定端口说明为何 `/composite` 不回退）；②新增 **§7.11** `POST /custom/{id}/status` 的 V3 校验（证据视图 `factor_v3_index.json`、`FS07`、`F-A30`–`F-A33`、排在 L1 之后 L2 之前），收口 §7.9.4 末条「尚未闭环」；③§9 增补 v0.5 绑定行与绑定声明。**v0.4 仍为 `F-A5` 的绑定对象；v0.5 只追认允许面，不改判据语义**。逐条原句/新句/依据见 `docs/architecture/CONTRACT_REVISION_R5_20261107.md` | 开发经理 v0.4 验收后派单 + 架构师本机实测（`git diff`、HEAD 符号表）|
| v0.6（追认） | 2026-11-07 | **R6（只追加，不改 v0.5 正文语义）**：①§7.10.2 字段表补 `path_divergence`/`both_collision`（实施已产出、表未列），新增 `side`/`ref_name`/`record_kind`/`path_base` 与可选 `side_key`，顶层加 `canonical_digest`，`schema_version` 升 `"2"`；②§7.10.3 新增 **N4**：`path_scope` 只记真实求值路径（`custom_signals.py:646-647`），`both` 需两入口同时编译的证据，撤回期望表把 `kind:"both"` 读成路径的 7 条；③新增 **§7.12** 清单 v2 规格（一出现一记录、伴生一一对应、槽位与结构键拆分、canonical digest、`summary` 分层、v1 兼容逐条、17:10 产物实测差距）+ `F-A34`–`F-A39`。**v0.4 仍为 `F-A5` 绑定对象；v0.5 不改** | 开发经理 v0.5 验收后派单（五条本机实测）+ 架构师本机复算（16:58–17:15）|


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

### 7.4 幂等与允许的 store 改动面

- 现状问题（陈述）：同一 `(id, formula 摘要, dependencies, warmup)` 重复 POST，v0.3 及其前每次 `_next_version()` +1，**不幂等**，且会让 `materialize_cache` 的键（含 `spec.version`）全部失效 → 整表重算。
- 要求：内容未变则返回既有定义、`version` 不变、响应标 `unchanged=true`；仅内容变化才 +1。
- 状态处置（`POST /custom` 遇到已存在定义是否保留盘上 `status`）：**保留**，判定规则见 **§7.9**。本节只管「允许改哪些代码」。

#### 7.4.1 引用口径（v0.4 冻结版先改这一条）

对 `store.py` 的引用**一律按符号（函数名/常量名）**，行号只作参考、**不作判据**。理由是可复跑的：`store.py` 在 16:23:11（17,315 B）→ 16:33:52（19,502 B）之间被改写两次，按行号写的允许面 10 分钟内过期两次，审核无法据以判越界。**审核判据 = 符号存在性 + `git diff` 的 hunk 归属**；下文行号锚定于本节声明的快照。

快照：`backend/app/factors/store.py` = **19,502 B / 409 行 / 全文 sha256 `de77eae6815adecd5e6f75a97329967752bd6b3fe52208a412a88c5641701199`**，mtime `2026-11-07 16:33:52`，`git diff --numstat` = `+187/−1`（HEAD `65c6e42f`）。

#### 7.4.2 允许面（函数级，唯一）

| 符号 | 行 | 类别 | 约束 |
| --- | --- | --- | --- |
| `_NON_CONTENT_FIELDS` | `:199` | 新增常量 | 只含 `version`/`created_at`/`updated_at` |
| `_GROUP_DEFAULT` | `:200` | 新增常量 | `group` 缺省映射（custom→自定义、composite→组合）|
| `_canonical(value)` | `:203` | 新增 | 纯函数，无 I/O |
| `content_signature(definition)` | `:218` | 新增 | 内部调 `to_spec`；非法即 `ValueError`（fail-closed）|
| `is_same_content(stored, incoming)` | `:247` | 新增 | 任一侧投影失败返回 `False`，**不得返回 True** |
| `_merge_for_write(stored, definition)` | `:261` | 新增 | 以盘上为底合并；跳过 `_NON_CONTENT_FIELDS`；保留非 API 字段 |
| `resolve_status(stored, definition)` | `:276` | 新增 | 四分支见 §7.9.3 |
| `is_unchanged_definition(stored, definition)` | `:298` | 新增 | 与 `upsert_definition` **同口径**预判，供路由决定是否重跑试算 |
| `upsert_definition(data_dir, definition)` | `:310` | 新增 | 幂等落库唯一入口；**status 归一化必须排在判等之前** |
| `load_one(data_dir, factor_id)` | `:39` | **新增只读包装**（v0.5 补） | `return _STORE.load_one(data_dir, factor_id)`，5 行（含 docstring）；无写、无校验、无路径变更；不存在或损坏返回 `None`（与 `load_all` 同隔离口径）。**HEAD `65c6e42f` 中 `def load_one` 命中 0** —— 它是新增符号，不是「既有函数」 |

**允许的既有函数变更（唯一一处）**：`register_definition`（`:169`）新增幂等跳过 —— `if get_factor(spec.id) == spec: return spec`。边界写死：**只跳过「同 spec」**（`FactorSpec` 21 字段逐个全等）；不同 spec 仍走 `register_factor` 的「版本未提升」拒绝；**不**新增 `try/except` 吞错、**不**放宽任何校验、**不**改返回类型。

**允许的调用方变更（2 处；v0.5 由 1 处扩为 2 处）**：①`POST /custom` 保存分支经 `upsert_definition` 落库，并在试算前用 `is_unchanged_definition` 预判（现 `:360-362`，行号仅参考，同 §7.4.1 口径）；②`POST /composite` 保存分支经 `upsert_definition` 落库（成员校验与环检不变；无试算，不需要预判）。两处共同的两项附带变更：**删除私有助手 `_next_version`**（版本号改由 `upsert_definition` 裁决，是幂等的必要部分）；**响应新增 `unchanged` 布尔**（纯增字段，既有消费方不破）。理由：`F-A5` 原文「同内容二次注册：`version` 不变、响应 `unchanged=true`、盘上文件字节与 mtime 均不变」**未限定端口**；只让 `/custom` 幂等会留下第二个「保存一次涨一版」的端口，与 §7.9.2 第 2 条直接冲突。API 层不得新增其它 store 调用。

#### 7.4.3 未改面（禁止，5 条）

1. `save_one`（`:35`）/`load_one`（`:39`）/`delete_one`（`:44`）语义不变：原子覆盖写；单文件损坏返回 `None` 且不阻断启动。其中 **`load_one` 在 HEAD `65c6e42f` 中不存在**，属**新增只读包装**（已列入 §7.4.2 允许面）；本条对它只约束「语义等同 `_STORE.load_one`」：不得加写、不得加校验、不得改返回契约（`dict | None`）。
2. `to_spec`（`:52`）校验不放宽：id 正则（`:63-65`）、`status` 取值（`:66-68`）、`lang` 取值（`:73-74`）、DSL/Python 编译失败即抛（`:79-81`、`:97-99`）。
3. `_STORE` 路径与 JSON 结构不变（`:27`，`user_data/custom_factors/*.json`）；**不得新增落盘字段** —— `needs_revalidation` 一类标记不得写进 JSON，只能进应用日志。
4. 幂等**不得变成跳过校验**：`unchanged=true` 分支仍须先 `to_spec(stored)`；`is_same_content` 投影失败返回 `False` 而不是 `True`。
5. `load_into_registry`（`:356`）/`_validate_definition`（`:393`）/`_definition_dependencies`（`:398`）三个既有函数不得改签名或语义；本轮若必须改，须在修订对照里逐行说明，否则审核按越界处理。

#### 7.4.4 自洽性

§7.6 `F-A5` 描述的这份实现**属于本节允许面**，不构成对 §7.4 的违例；§7.4 也不得以「不动 store」为由判它越界。v0.3 的「不动 store」与 §7.6 的「已实现」互相打架，v0.4 起以本节为准。
### 7.5 禁止事项
1. **禁止**把 `prior_*` 写成不含 `ts_delay` 的形式。
2. **禁止**跨层取数构造因子：不得把 API/展示层返回值（`api/intraday.py:72` 等百分点字段）或 provider 原始百分数字段直接喂进因子帧；一个因子只能引用因子帧内的列。`change_pct` 在因子帧内是小数（`pipeline.py:156`），可直接引用（v0.3 更正）。
3. **禁止**同一口径起两个 id 并用于同一策略；研究名 ↔ `uf_` id 映射必须唯一并登记在 `docs/factors/` 台账。同一口径若已存在两个**均已注册**的 id（现状 8 组，见 §7.8.1 #6），必须按 §7.8.2 指定单一 canonical，另一个 id 声明 `alias_of`（运行时）与 `superseded_by`（台账）；未声明即按 §7.8.4 的 `FS06` 处理。
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
| F-A5 | 幂等 | 同内容二次注册：`version` 不变、响应 `unchanged=true`、盘上文件字节与 mtime 均不变（→ 目录指纹不变 → 依赖指纹的缓存不全表失效）。**实现现状（2026-11-07 15:44 复核）**：工作区已有**未提交**实现 `store.py` 的 `content_signature`/`is_same_content`/`resolve_status`/`is_unchanged_definition`/`upsert_definition`（符号定位，见 §7.4.1）（`content_signature` / `is_same_content` / `upsert_definition`）+ `api/factors.py` 的 `POST /custom`（`:333-366`）；HEAD `65c6e42f`（2026-11-07 12:56:05 +0800）中**没有**这部分（`git show HEAD:backend/app/factors/store.py` 内 `unchanged` 命中数 = 0）；`git status` 显示两文件为 `M`，mtime 16:33:52。**判据状态 = 待独立审核**，通过前不得记为已满足；靶值（version 不变 + `unchanged=true` + 文件未写）可直接按现实现复跑。**该实现属 §7.4 v0.4 允许面**（`upsert_definition`/`content_signature`），不构成对「不动 store」的例外。 |
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
| `kind` ∈ {`base`, `virtual`} | 不适用（两者都无 `status`；准入由台账 G1–G3 与代码审核承担，见 §7.8.3） | 同左 |

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

- `status` 变更**不改数值**。当前内容签名把 `status` 计入（`store.py:183-198` 节注释；`_NON_CONTENT_FIELDS` 定义在 `:199`，只排除 `version/created_at/updated_at`）→ 改状态会抬版本 → 该因子 `materialize_cache` 键变化 → **单因子重算一次**。这是**可接受的代价**（数值逐位不变，只花一次算力），本条按现状登记，不要求改实现。
- 硬要求：`status` 变更后重算结果必须与变更前**逐位相同**（`max_abs_diff == 0`）；若不同，说明 status 实际影响了计算，属缺陷。
- 若后续把 `status` 移出内容签名（省掉这次重算），**必须同时**落状态审计（`status_history`：谁 / 何时 / 依据哪份报告 digest），否则治理链断裂。

#### 7.7.7 验收判据（与 §7.6 同表编号）

| # | 判据 | 度量 |
| --- | --- | --- |
| F-A7 | 运行时可见 | `get_factor("<uf_*>").status` 返回四个合法值之一（字段已落 `FactorSpec`）；`getattr(..., "status", None)` 不再是 `None` |
| F-A8 | 闸门可判 | 同一因子依次置 `draft/watch/active/retired`，`assert_factors_usable` 在 `production`/`research` 两模式下的 8 个组合逐个等于 7.7.2 矩阵；`FS01`/`FS02` 逐字匹配 |
| F-A9 | 不可绕过 | `production` 模式引用 `draft` 因子：X1 计划不生成、`paper_auto` 规则装载失败；断言「订单数 == 0」且报告含 `FS01` |

---

### 7.8 双 id、别名与「不可复算因子」的闸门契约（v0.4 新增；批二前置，不落地则闸门一上就误判）

本节回答三个问题：**同一口径两个 id 谁是 canonical、旧 id 被闸门怎么对待、没有 DSL 公式的因子怎么判**。

#### 7.8.1 事实（逐条实测；2026-11-07 16:10–16:25 本机复跑）

| # | 事实 | 依据（可复跑） |
| --- | --- | --- |
| 1 | `backend/app/custom/research_factor_pack/`（未跟踪，14:33–14:42）经 Provider 注册 **14 个研究原名 id，14/14 均可 `get_factor`**；不是「只注册 4 个、另 10 个未注册」 | `factor_provider.py:42-46`、`factor_specs.py:38-76`（`_DEFINITIONS` 14 条）、`:92-98`；运行时 dump：`ma20/ma60/boll_lower/boll_upper/sd20/prior_high_20/prior_low_10/prior_high_55/prior_vol_20/ma120/vol60/prior_high_250/prior_amount_20/ma200` 全部非 `None` |
| 2 | 这 14 个是 `kind="custom"` + `lang="dsl"` + `formula_text` = **DSL 原文**（非空、可编译），warmup 由 DSL 推导；`stability="stable"`、`version=1` | `factor_specs.py:78-87`、`:26`；实测 warmup 依次 21/61/21/21/21/21/11/56/21/121/61/251/21/201 |
| 3 | **`FactorSpec` 没有 `formula` 字段**（只有 `formula_text`）：`getattr(spec,"formula",None) is None` 是「字段不存在」，不是「公式为空」 | `registry.py:33-57`（21 字段）；`[a for a in dir(spec) if "form" in a]` → `["__format__","formula_text"]` |
| 4 | 真正「没有可编译公式」的是 `kind="composite"`：`formula_text` 是合成描述串 `"w*zscore(member) + …"`，**不可编译**（成员引用不走 DSL 语法） | `store.py:156-166`；`cf_auction_resonance` 实测 |
| 5 | `lang="python"`（T2）由 `compile_python_expression` 给出 **`dependencies` 与 `warmup_bars`**（`warmup=max(declared, compiled)`），所以「依赖推断不成立」不成立；缺的是**研究侧参考实现** | `store.py:74-100`；`py_expr.py:99-113` |
| 6 | 同口径双 id 已是事实，**8 组**（v0.4 自纠：本节初稿写「4 组且含 `prior_amount_20`」，与目录实测不符，逐文件读 `id` 后更正）：`ma120`/`ma200`/`vol60`/`prior_high_20`/`prior_high_250`/`prior_high_55`/`prior_low_10`/`prior_vol_20` 在 pack（研究原名）与 store（`uf_*`，14:30:24 落盘 `D:/TSP/data/user_data/custom_factors/`）各一份；**`prior_amount_20` 没有 `uf_` 对应件**，`uf_dist_prior_high_250` 没有 pack 对应件，二者各为单侧 | 目录 15 个 json（14 `uf_` + 1 `cf_`，逐个 `json.load` 读 `id`）；装载后 `all_factors()` 192→**207**；配对 = `[i for i in RESEARCH_BASELINE_FACTOR_IDS if "uf_"+i in store_ids]` → 8 项 |
| 7 | 8 组里**只有 2 组表达式完全相同**（`ma120`/`ma200`）。`vol60` 差 1 ULP：pack 用 `(close - ts_delay(close,1)) / ts_delay(close,1)`，store 用 `close / ts_delay(close,1) - 1`；另 5 组 `prior_*` 是**同窗口不同写法**：pack `ts_delay(ts_max(high,N),1)` vs store `ts_max(ts_delay(high,1),N)`——窗口同为 `[t-N, t-1]`，差异只在边缘 NaN 传播与 1 ULP | `factor_specs.py` 头注；`F_CLASS_PARITY_20261107.md:37` 记 1.11e-16 / 4.6% 行不等；逐文件读 `formula` 对照 |
| 8 | `status` 不进运行时对象，但 `to_spec` 把它**单向投影成 `stability`**：`active→stable`，`draft/watch/retired→experimental`（三态塌陷，`retired` 失去否决力） | `store.py:94`、`:110`、`:165`；实测 `get_factor("uf_vol60").stability == "experimental"`、`hasattr(...,"status") == False` |
| 9 | pack 的 14 个自报 `stability="stable"`，**没有经过任何 status 流程**（不来自 store、无 JSON 定义、无 `POST /custom`） | `factor_specs.py:26`、`:87` |
| 10 | 注册表规模两态实测：catalog **77** + pack **14** + `ext_*` **85** + 其它 Provider **16** = **192**（repo 的 `data/`，store 未装载）；装载 `D:/TSP/data` 的 **15** 个定义后 = **207**（与台账「206 条」差 1，因 `uf_dist_prior_high_250` 16:07 才落盘） | `len(all_factors())`；`load_into_registry(Path("D:/TSP/data"))` 返回 15 |
| 11 | pack 的 14 个 id 在 `factor_columns_view()` 中位于 catalog 之后（idx 86–99），**前 48 条顺序未变**（`mining_schedule` 取前 48，重排即回归） | `[r["id"] for r in factor_columns_view()].index("ma20") == 86`；catalog 长度 77 |
| 12 | 现存引用面（`D:/TSP/data/user_data` 98 个 json）：pack 原名命中 `preferences.json`（`ma20`/`ma60`/`boll_lower`）与 `custom_signals/ma_golden_20_60.json`（`ma20`/`ma60`）；`rsi_14` 的 15 次命中**全在** `firstboard_discovery/runs/*/report.json`（历史运行产物，非活配置） | 逐文件 `grep -l` 枚举 |

#### 7.8.2 裁定 A：canonical = 台账 id（`uf_*` / `cf_*`），研究原名 = alias

三条机制性理由（不是偏好）：

1. **只有 store 侧 id 能带状态与版本**：`status`/`version`/`created_at` 活在 JSON 定义里；Provider 注册的 spec 没有这些字段，改口径在 Provider 侧只能改代码（版本 = 一次提交），无法逐因子审计、无法逐因子回滚。
2. **只有 store 侧 id 有命名空间约束**：`CUSTOM_ID_PATTERN = ^uf_[a-z0-9_]{1,40}$`（`store.py:22`）阻止与研究名、与内置 base 列名相撞；Provider 用任意 id（`factor_provider.py` 头注「任意 id + 元数据」），今天是「名字恰好不撞」，不是「不可能撞」。
3. **G7 可穷举版本化**：口径组合必须可穷举，前提是每个口径一条可版本化记录。

配套硬规则：
- **A-1** 每个口径**恰好一个** canonical；`docs/factors/` 台账逐行写 `canonical_id`、`aliases[]`、`superseded_by`、`canonical_reason`。若某行把 canonical 定为研究原名（非 `uf_*`），必须在该行写理由，且**仍只能有一个**。
- **A-2** alias 只能解析到 canonical，**不得各自持有一套实现**：alias 命中即返回 canonical 的列，数值归属 canonical。生产入口不允许别名（`FS03`），研究入口允许但记 `deprecated_alias_used`。
- **A-3** `FactorSpec` 新增 `alias_of: str | None = None`（P2，与 §7.7.2 的 `status` 同批）；解析规则写死：传递解析上限 **4 跳**、环检测、目标必须是已登记 spec，任一不满足 → `FS06`；解析结果写入策略元数据 `resolved_id`，同时保留 `submitted_id` 供审计。
- **A-4** **alias 生效的数值代价必须报**：`vol60`（pack）与 `uf_vol60` 差 1 ULP（1.11e-16，4.6% 行不等，`F_CLASS_PARITY_20261107.md:37`）。alias 解析到 canonical 后，原引用研究名的策略**必须重跑对账**：判据统一按 `F-A3` 的 `max_abs_diff < 1e-12`；`1.11e-16` / `2.22e-16` 只作实测记录（`uf_vol60` 1 ULP、非零行占比 4.6%），不得写成门槛（把某一次实测的 ULP 值当门槛，会让「同一公式换个求和顺序」的正确实现判失败，属凭空收紧）。非零行占比与 4.6% 同量级作为**辅助观察项**上报，不单独构成判据；超差即视为口径变更，按 G8 走变更流程，不得静默上线。
- **A-5** store 侧 6 个定义（`uf_auction_*` 5 个 + `cf_auction_resonance` 1 个）依赖 `ext_*` 拍卖列，**没有研究侧等价实现** → 走 §7.8.3 的 `reference_missing` 分支，**不得**用 `F-A3` 式逐值对账判它们不合格。

#### 7.8.3 裁定 B：闸门按「可复算性」分类，**不按 `kind`**

| 类 | 判定依据（机械可判） | 数值判据 | `verifiable` / `reference_missing` |
| --- | --- | --- | --- |
| base / virtual（catalog 77） | 不 gate（§7.7.2） | 台账 G1–G3 | `n/a` |
| custom-dsl（store `uf_*`、pack 14 个） | `compile_formula(spec.formula_text).ok == True`；`dependencies` 闭包必须落到 `BASE_COLUMNS` 或已物化 `ext_*` 列 | 同一实现两遍 `max_abs_diff == 0`；有研究参考的另加 `F-A3`/`F-A10` 式对账 | `true` / `false` |
| custom-python（`lang="python"`） | `compile_python_expression(spec.formula_text).ok`；`warmup_bars ≥ compiled.warmup_bars` | **没有 DSL 表达式 → 不能走 `compile_formula`、不能与研究对账**；只做「同输入两遍逐位一致」+ 声明测试向量 | `true` / **`true`** → `FS05` |
| composite（`cf_*`） | **不编译** `formula_text`（描述串）；判据 = 成员全部 `usable`（递归）+ 权重非零 + 无环 | 两遍一致；成员可复算性逐个继承 | `true` / `false` |
| 未登记 | — | — | 拒绝 `FS02` |

**对「`formula=None` 的 python 因子怎么判」的正面回答**：按 `lang` 分支，**不按「`formula` 是否为空」**（该字段不存在，见 7.8.1 #3）。python 因子的 `dependencies`/`warmup` 由 `compile_python_expression` 给出，`factor_columns_view()` 对所有 spec 一视同仁（`factor_columns_view()` 在 `registry.py:408`，行内只看 `id/label/group/formula_text`，`column_view()` 在 `:61`），所以「依赖推断与列视图不成立」不成立；真正不成立的是**「对研究参考实现复算 `max_abs_diff`」**——python 因子没有研究侧等价物，只能是 `reference_missing=true`，判据降级为「自洽双跑 + 测试向量」。现状**实测 0 个 python 因子**（`D:/TSP/data` 15 个定义的 `lang` 全为 `dsl` 或缺省），但分支必须写死：第一只 python 因子进线时，闸门不能靠「今天没有」来决定走哪条路。

#### 7.8.4 闸门模式位与新增错误码（续 §7.7.5）

`assert_factors_usable(factor_ids, mode, ...)` 的 `mode` 增加第三个取值 `diagnostic`（仅供诊断/差异证明路径），判定矩阵在 §7.7.2 的 `status` 维度上**叠加 `verifiable` 与「是否 alias」两个布尔维度**（不是新的状态机）：

| 情形 | `production` | `research` | `diagnostic` |
| --- | --- | --- | --- |
| canonical `active` + `verifiable=true` | 允许 | 允许 | 允许 |
| canonical `active` + `reference_missing=true` | **拒绝 `FS05`** | 允许，报告标 `reference_missing` | 允许 |
| 提交的是 alias（可解析） | **拒绝 `FS03`**（生产只认 canonical id） | 允许，标 `deprecated_alias_used` | 允许 |
| 同一策略内 alias 与 canonical 并存 | **拒绝 `FS04`** | **拒绝 `FS04`** | 允许（标 `dual_id`） |
| 两个 id 都自称 canonical / 台账未裁定 / 别名成环 | **拒绝 `FS06`** | **拒绝 `FS06`** | 允许（标 `ambiguous_canonical`） |
| Provider 注册且**无 `status`**（现状：pack 14 个） | **拒绝 `FS01`**（按 `draft` 处理） | 允许，标 `non_active` | 允许 |

| 码 | 含义 | 处置 |
| --- | --- | --- |
| `FS03` | 生产入口引用了 alias 而非 canonical | 400；`detail` 含 `submitted_id` / `resolved_id` |
| `FS04` | 同一策略混用同口径两个 id | 400；`detail` 含两个 id 与台账行号 |
| `FS05` | 无可复算参考实现且未声明测试向量 | 400；`detail` 含 `lang` 与 `reference_missing` |
| `FS06` | canonical 未裁定 / 冲突 / 别名成环（解析不可判定） | 400，fail-closed |

**硬规则：不得用 `stability` 反推 `active`。** `stability` 是 `status` 的单向投影（7.8.1 #8）。反向不成立：pack 的 14 个 `stability="stable"` 没有任何 status 支撑。若闸门拿 `stability` 判准入，这 14 个会被当成已验收放行进生产——**误放行比判死更危险**，也是本节最容易被实现者图省事做错的一处。

#### 7.8.5 过渡期（不做这一段，批二一上线就停产）

- 闸门对**新写入**的配置 fail-closed：`POST /api/strategy/config`、`PATCH`、X1 计划生成、`paper_auto` **新**规则装载。
- 对**存量**规则：加载时只告警，并在运行报告写 `degraded=true`，不阻断；存量清单（`referenced_factor_inventory`：文件 + 提交 id + `resolved_id` + 状态）由因子工程师在批二**前**产出，本契约只要求这份清单存在且机器可读。
- 存量清理完成后，由开发经理把 `enforce_existing=true` 打开，新旧一视同仁。
- 现状最小事实（7.8.1 #12）：活配置里 pack 原名的引用只有 2 个文件；`rsi_14` 的 15 次命中全在历史报告里 → D2「`rsi_14` 不得被策略引用」在活配置上目前 **0 违例**，但闸门必须能拦住**新写入**。

#### 7.8.6 验收判据（续 §7.6 编号）

| # | 判据 | 度量 |
| --- | --- | --- |
| F-A14 | 14 个 pack id 分类正确 | 逐一 `compile_formula(formula_text).ok == True`、`kind=="custom"`、`lang=="dsl"`、warmup = 21/61/21/21/21/21/11/56/21/121/61/251/21/201 |
| F-A15 | alias 解析 | 造 3 组（一跳、两跳、成环）：解析结果分别 = canonical / canonical / `FS06`；`resolved_id` 与 `submitted_id` 同时落库 |
| F-A16 | python 不误判 | 造一个 `lang="python"` 因子：闸门返回 `reference_missing=true`，`production` 给 `FS05`，且**不进入** `compile_formula` 分支 |
| F-A17 | 存量不阻断、新写入拦住 | 存量规则加载：计划/订单生成未被阻断且报告含 `degraded=true`；同内容的新写入被 `FS01`/`FS03` 拒绝 |

---

### 7.9 `POST /custom` 对既有定义的 `status` 处置（v0.4 冻结版裁定）

#### 7.9.1 问题（事实）

`content_signature` 把 `status` 计入投影（`store.py:233`；`_NON_CONTENT_FIELDS` 只排除 `version`/时间戳，`:199`）。若 create 路由硬编码 `status="draft"`：盘上 `active` 定义经 create 形状重提交 → 签名不等 → 判为内容变化 → `version + 1` 且落盘 `draft`。**闸门上线后，一次保存等于一次隐形停机**（该因子在 `production` 立刻 `FS01`），且触发一次该因子的缓存重算。

#### 7.9.2 裁定：保留盘上 `status`；只有「内容变化」才回 `draft`

三条理由：

1. **create 不是生命周期操作。** `status` 的写入口只有 `POST /custom/{id}/status`（`api/factors.py:514-535`）和「编辑即回 draft」语义。
2. **`status` 参与内容签名**，路由层任何隐式 status 写入都会被翻译成「版本 +1 + 缓存失效」，代价与「用户只是保存了一下」不成比例。
3. **与 §7.5-5 不冲突：保留 ≠ 放宽。** 新定义仍强制 `draft`；`draft` 因子在生产仍被 `FS01` 拒。保留只是不让「一次保存」改变治理状态。

#### 7.9.3 判定规则（`resolve_status(stored, definition)` 的唯一四分支，机械可判）

| # | 条件 | 写入的 `status` | `version` | 响应 |
| --- | --- | --- | --- | --- |
| R1 | 盘上无该 id（真新建）| `draft`（**忽略**入参 status）| 入参 version（仅首建生效）| `unchanged=false` |
| R2 | 盘上有，入参**显式**给 status | 以入参为准（API 上不可达，见 7.9.4）| +1 | — |
| R3 | 盘上有，未给 status，**除 status 外内容等价** | **沿用盘上 status** | **不变** | `unchanged=true`，**不写盘** |
| R4 | 盘上有，未给 status，**除 status 外内容有变化** | **`draft`**（编辑即回 draft）| +1 | `unchanged=false` |

两条硬规则（顺序错了就退化成「保存一次涨一个版本」）：

- **R3 的判等必须先做 status 归一化**：把入参 status 置为盘上 status 之后再比签名；先判等后归一化会让每个 `active` 定义都被判成「变了」。
- **`updated_at` 不参与判等**，且 R3 不写盘 → 文件字节与 mtime 都不变。这是 `F-A5` 判据「盘上文件字节与 mtime 均不变」成立的前提，不是附带效果。

#### 7.9.4 与 §7.5 生命周期的一致性

- **一致**：R4 就是「编辑即回 draft」，与 `POST /custom/{id}/update` 的既有语义（`api/factors.py:427`：公式变化 → `status="draft"`；仅改名称/分组 → 保留）**是同一条规则**。两个端口不得有两种语义。
- **R2 在 API 上不可达**：`CustomFactorCreateRequest`（`api/factors.py:236-242`）**没有 `status` 字段**，Pydantic 丢弃未知字段，create 永远不带 status。因此「一次保存把 active 打回 draft」的根因不是入参带了 status，而是**判等口径忘了归一化**。
- **将来若给该模型加 `status` 字段，必须同时加「非 `draft` 一律 400」的拒绝**，否则 create 会变成绕过 §7.5-5 的自助激活通道。
- **登记一处尚未闭环（不圆）**：`POST /custom/{id}/status` 接受任意 `draft|active|watch|retired`（`:511` 正则），**没有任何 V3 校验**。所以 §7.5-5「未过 V3 不得标 active」目前仍是人工纪律，不是代码约束。§7.7 的闸门只保证「标了 active 之后谁还能用」，不保证「谁能标 active」。

#### 7.9.5 判据（续 §7.6 编号）

| # | 判据 | 度量 |
| --- | --- | --- |
| F-A18 | create 不降级 | 盘上造一个 `active` 定义，用 create 形状（无 status）原样重提交：`status` 仍 `active`、`version` 不变、`unchanged=true`、文件字节与 mtime 均不变 |
| F-A19 | 编辑回 draft | 同一 id 改公式重提交：`version + 1`、`status` 变 `draft`、`unchanged=false` |
| F-A20 | 仅改元数据不降级 | 只改 `label`：`status` 保留、`version + 1` |
| F-A21 | 无自助激活 | 向 `POST /custom` 传 `status="active"`：不生效（字段不存在）或 400；盘上 status 恒为 `draft` |

---

### 7.10 闸门落地顺序：`referenced_factor_inventory` 先行 + L0–L3 分级放行（v0.4 冻结版裁定）

#### 7.10.1 为什么必须先有清单（事实，本机复跑 16:30–16:36）

- `gate.py` 不存在；`alias_of` / `FS03` / `assert_factors_usable` 在 `backend/app/**` 命中 **0**。
- 存量 status：`custom_factors` **15/15 `draft`、`active = 0`**；pack 14 个 `kind="custom"` 无 `status`（`hasattr(spec,"status") == False`）。
- 按 §7.7.2 矩阵直接上生产：**生产可用因子 = 0 → 全站停产**。
- §7.8.5 的过渡期缓冲，前置条件正是这份清单；而它**不存在**：`referenced_factor_inventory` 全仓命中 4 处 = 本契约 1 处 + 独立审核报告 3 处（`research/independent-review-20261107/BATCH2_ABC_AUDIT_20261107.md:15,215,217`），**0 个产物**。

#### 7.10.2 产物（唯一路径与字段，闸门的第一个交付）

- 路径：`docs/architecture/evidence/referenced_factor_inventory.json` + 同名 `.sha256`。
- 生成：脚本 `backend/scripts/build_referenced_factor_inventory.py`（系统开发工程师实现）。
- 角色分工：**生成 = 系统开发工程师（唯一实现者）；签认 = 因子工程师（口径归属）；消费 = 闸门（只读）**。原因：因子工程师不写代码，系统开发工程师不裁口径。
- 顺序硬约束：**它是闸门实现的第一个交付，必须先于 `assert_factors_usable` 接线**。理由：分级放行的名单从这个文件读；没有它只能手写白名单，而手写白名单等于绕过治理。

顶层字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | str | `"2"`（v0.6 起）。读到 `"1"` 的降级读取规则见 §7.12.6；`"1"` 只许用于 L0/L1 |
| `generated_at` | str | ISO8601 +08:00 |
| `repo_head` | str | `git rev-parse HEAD` |
| `data_root` | str | 被扫描的 `user_data` 绝对路径 |
| `scanned_sources` | int | 被解析的文件数 |
| `records` | list | 见下表 |
| `summary` | obj | 按 `verdict` / `code` / `namespace` 计数 |
| `stale_count` | int | `source_sha256` 与盘上不符的条数 |
| `canonical_digest` | str | **v0.6 新增**。内容指纹：先剔除 `generated_at` / `repo_head` / `data_root` / `canonical_digest` 自身，再按 §7.12.4 规范化取 sha256。**签认、两份产物比对、闸门读取一律用它**；旁挂 `.sha256` 因含 `generated_at` 每次必变，只证明「本次运行字节完整」|

`records[]` 逐条字段：

| 字段 | 取值 | 说明 |
| --- | --- | --- |
| `source_kind` | `custom_signal` / `strategy_override` / `strategy_config` / `monitor_rule` / `custom_factor` / `research_strategy` | 扫描域六类 |
| `source_path` | str | 相对仓库根或 `data_root` |
| `source_id` | str | 该配置的 id |
| `source_sha256` | str | 文件字节哈希（判 `stale`）|
| `source_enabled` | true/false/null | 活配置判定 |
| `path_scope` | `history` / `intraday` / `both` | 见 7.10.3 N3 |
| `ref_raw` | str | 原始引用文本（如 `ma20`）|
| `ref_namespace` | `column` / `factor` / `signal` / `prose` / `unknown` | **必须由结构化字段解析得出**，不得全文 grep |
| `resolved_id` | str/null | `namespace=factor` 时的因子 id |
| `class` | `base` / `virtual` / `custom_dsl` / `custom_python` / `composite` / `unregistered` | 可复算性分类（§7.8.3）|
| `verifiable` | bool/null | §7.8.3 |
| `gate_mode` | `production` / `research` / `diagnostic` / `none` | 该引用所在的消费入口 |
| `verdict` | `allow` / `block` / `shadow` / `exempt` / `unknown` | 分级放行的唯一输入 |
| `code` | `FS01`–`FS07` / null | 拒绝码 |
| `evidence` | str | `file:line` |
| `path_divergence` | bool | **v0.6 补表**（实施已产出、v0.4/v0.5 表未列）。N3 两路径结论不一致时为 `true`；为 `true` 的条不得判 `allow` |
| `both_collision` | bool | **v0.6 补表**（同上）。主记录恒 `false`，伴生记录恒 `true`（§7.12.2）|
| `side` | `L` / `R` / `F` | **v0.6 新增·必填**。表达式槽位：`left` = `L`、`right` = `R`、monitor 规则的 `conditions[].field` = `F`。**只允许这三个值**；结构键路径（`scoring` / `fields.entry` / `members` / `formula` 等）不属于本字段，见 `side_key` |
| `ref_name` | str | **v0.6 新增·必填**。归一化名：`ref_raw` 去掉 `field:` / `column:` / `signal:` 前缀并 trim。**allowlist 与闸门比对的键** |
| `record_kind` | `primary` / `companion` | **v0.6 新增·必填**。`companion` = F-A24 的伴生记录；主/伴生共用同一 `(source_path, evidence, side, ref_name)` 元组，靠本字段区分 |
| `side_key` | str / null | **v0.6 新增·可选**。引用所在的结构键路径（人读定位，如 `fields.entry`、`scoring`、`members`）。**不参与任何判据、不进 allowlist、不得用于唯一键** |
| `path_base` | `repo` / `data` | **v0.6 新增·必填**。`source_path` 的基准：`repo` = 仓库根；`data` = `data_root` 下的相对路径（`data_root` 在仓库外，不能统一成仓库根；其值已含 `user_data`，故路径**不带** `user_data/` 前缀）|

#### 7.10.3 命名空间优先级（先于一切分类）

- **N1**：配置里的 `field:X` **先查** `ALLOWED_FIELDS`（基础指标列，`custom_signals.py:41-67`）。命中 → `namespace=column`，**不进入因子闸门**。仅当 `X ∉ ALLOWED_FIELDS` 时才回落到 `factors.registry`。现实现是两者的**并集**（`custom_signals.py:92-103`），集合语义本身不表达「先列后因子」，**实现必须显式排序**。
- **N2**：`namespace=column` 的引用**不得**因「名字恰好等于某因子 id」而判 status。四个冲突名同时存在于 `ALLOWED_FIELDS` 与 pack 14 个 id：`ma20`、`ma60`、`boll_lower`、`boll_upper`。按因子判 → 7 条活信号静默停摆（7.10.5）。
- **N3（登记一处真实分叉，不圆）**：历史路径（`compute_signals`）基础列存在 → `column`；盘中单日快照无滚动窗口 → 同名基础列缺失 → `materialize_factor_columns` 会把**同名因子**补算出来（`custom_signals.py:106-134`）→ 同一信号在两条路径上 `namespace` 可能不同。清单必须按 `path_scope` 逐路径记录；两路径结论不一致标 `path_divergence=true`，**该条不得判 `allow`**。

- **N4（v0.6 裁定：`path_scope` 只记真实求值路径，`both` 需编译证据）**：`path_scope` 由「该 source 实际被哪条编译入口编译」决定，不由 `kind` 或任何声明决定。代码事实（HEAD `65c6e42f`）：`custom_signals.py:646-647` 的 `build_intraday_expressions` 对 `sig.get("timeframe") != TIMEFRAME_INTRADAY` 直接 `continue`；`custom_signals.py:717-719` 的 `_load_intraday` 也只取 `timeframe == intraday`；`definitions.py:234-235` 与 `services/resource_bundle.py:708` 同样按 `timeframe == TIMEFRAME_INTRADAY` 分支。故 **`timeframe=daily` 的 source 只走历史路径**（`build_expressions` / `compute_signals`），盘中单日快照根本轮不到它 —— `materialize_factor_columns` 那条「同名因子补算」对它们不可达。
- **N4.1 取值判据（按 source_kind）**：`custom_signal` → 按 `timeframe`：`daily` → `history`、`intraday` → `intraday`；`monitor_rule` → `intraday`（该规则**没有 `timeframe` 字段**，执行入口是实时 enriched 快照：`strategy/monitor.py:659-663` 的 `evaluate(df…)` 与其 docstring「df: 实时 enriched 数据」，调用方 `services/quote_service.py:1359`）；`custom_factor` / `research_strategy` / `strategy_config` / `strategy_override` → `history`。
- **N4.2 `both` 只在一种情形允许**：同一 `source_path` 真的被 `build_expressions` 与 `build_intraday_expressions` **同时编译**（可判：两次编译都返回含该 source 的非空表达式）。除此之外 `both` 一律不得出现；当前 **`both` 计数必须为 0**（生成器已自检「path_scope 无悬空 both」，取值集合 ⊆ `{history, intraday}`）。
- **N4.3 一处已撤回的误读（事实）**：`kind` 与 `timeframe` 是不同字段 —— `kind ∈ {entry, exit, both}` 是「进/出/两者」（`custom_signals.py:229` 校验），`timeframe ∈ {daily, intraday}` 才是路径（`:231-233` 校验）。21 条活信号里 `kind` 为 `both` 20 条、`exit` 1 条，`timeframe` **全部 `daily`**，`intraday` **0 条**（本机 17:08 实测）。故 F-A24 的 7 条冲突源 `path_scope=history`、`path_divergence=false`、`verdict=allow`，与 §7.10.5「按 N1/N2 被 `FS01` 拦的 = 0 条」一致。研究侧期望表把这 7 条记成 `path_scope=both` / `path_divergence=true` / `verdict=shadow`，是把 `kind:"both"` 读成了路径 —— **该 7 条按本裁定改判**；期望表在 `docs/factors/evidence/`，写权归因子工程师，本契约不改其文件。
- **N4.4 一处不构成 `path_divergence` 的分叉（登记）**：历史路径上基础列缺失时，`materialize_factor_columns` 会补同名因子（`custom_signals.py:95` 注释、`indicators/pipeline.py:684` 调用）。这改变的是「值由谁算」，不改变 N1 的命名空间（`field:X` 命中 `ALLOWED_FIELDS` 仍是 `column`），故**不记 `path_divergence`**；若实测同一帧上两者数值不等，属另一类问题，记入 §9。本轮未实跑。

#### 7.10.4 分级放行（L0–L3，逐级有判据与退出条件）

| 级 | 闸门行为 | 放行依据 | 进入条件 | 退出条件 |
| --- | --- | --- | --- | --- |
| L0 观测 | 只生成清单，**不接任何入口** | 无 | 本契约冻结 | F-A22–F-A26 全过 |
| L1 影子 | 入口都调 `assert_factors_usable`，但**只写报告不阻断**，报告标 `shadow=true` | 全量 | L0 过 | 连续 5 个交易日报告里的 `block` 集合**逐 id 相等**（集合相等，不是计数相等）|
| L2 有名单阻断 | `production` 入口按清单阻断；allowlist 来自 `verdict=shadow` 的条目，每条带 `expires_on` | `allowlist` ∪ `active` | L1 过 + allowlist 已签认 | allowlist 全部过期或被清空 |
| L3 全量 fail-closed | 非 `active` 一律拒；allowlist 必须为空 | 仅 `active` | L2 过 | —（终态）|

三条硬约束：

- **allowlist 只许缩小**。唯一允许的新增路径是「研究侧新因子经审核后进入 `active`」，不得把存量 `draft` 加进名单。
- **allowlist 不得手写**：必须由清单生成，`expires_on` 必填（缺省即拒绝启动）。
- **L2 期间 `verdict=shadow` 的因子必须在运行报告写 `degraded=true`**（沿用 §7.8.5）。

#### 7.10.5 今天的具体结论（逐 id）

- `enabled=true` 的活配置共 **22 条** = `custom_signals` **21** + `monitor_rules` **1**。另有 2 个 `strategy_overrides` 仅在 `basic_filter.enabled` 上为 true，不是顶层开关，不计入 22。
- **按 N1/N2，被 `FS01` 拦的 = 0 条。**
- **若实现违反 N2（把 `allowed_fields()` 的因子并集当因子引用），会误拦 7 条**，逐 id：`boll_breakdown_lower`、`boll_breakout_upper`、`ma20_breakdown`、`ma20_breakout`、`ma_dead_5_20`、`ma_golden_20_60`、`ma_golden_5_20`。
- **拦了会怎样：不是 400，是静默停机。** 缺列走「优雅降级」跳过（`custom_signals.py:95-97`）→ 这 7 条信号恒为 `null` → 依赖它们的策略 entry/exit 永不触发，**不报错、不告警**。所以「误判」比「判死」更危险：判死给 400，误判给静默。
- `monitor_rules/lot_1a1aa285978_521c_p`：只引用 `close` → 0 影响。
- 2 个 `strategy_overrides`（`custom_factor_first_board_chain_strict_rebreak`、`custom_mvoa5yy6`）引用 `distance_to_high_60d` / `limit_up_count_20d`，二者 `kind="virtual"` → 按 §7.8.3 不 gate → 0 影响。若把它们当 `draft`，会误拦 2 个活策略。
- 15 个 `custom_factors` 全 `draft`，且**当前 0 条活配置引用**：14 个 pack 原名在 `user_data` 的命中全部落在 `column` 命名空间或散文里（`preferences.json:197-212` 是展示列、`custom_mvoa5yy6.json:3` 的「MA20」在 description 文字里）。

#### 7.10.6 判据（续 §7.6 编号）

| # | 判据 | 度量 |
| --- | --- | --- |
| F-A22 | 清单幂等 | 同输入连跑两次，除 `generated_at` 外逐字节相同；且两次 `canonical_digest` 必须相等。签认与比对一律用 canonical digest —— 旁挂 `.sha256` 取全文哈希、含 `generated_at`，每次重跑必变，只证明本次运行字节完整，不得作比对基准（§7.12.4）|
| F-A23 | 结构化解析、不全文 grep | 两个反例必须**不**被计为引用：`strategy_overrides/custom_mvoa5yy6.json:3` 的 description（散文）、`preferences.json:197-212` 的 `builtin:ma20`（展示列）|
| F-A24 | 命名空间冲突必须报 | `ma20`/`ma60`/`boll_lower`/`boll_upper` 四处必须 `ref_namespace=column`，并另出一条 `both_collision=true` 的伴生记录 |
| F-A25 | 无 `unknown` | `verdict=unknown` 条数必须 **0**；非 0 时闸门拒绝启动（fail-closed 在清单上，不在业务上）|
| F-A26 | 新鲜度 | `stale_count > 0` 时 L2 及以上拒绝启动 |
| F-A27 | 清单先于闸门 | 交付顺序可验证：清单存在且 F-A22–F-A26 通过，`gate.py` 才允许接线 |
| F-A28 | 分级可回退 | L0→L1→L2→L3 逐级可回退；任一级 allowlist 为空时可退回上一级，且数值结果不变 |
| F-A29 | 误拦可探测 | 构造「因子 id 恰与基础列同名」的信号：`verdict` 必须是 `allow`（column），且运行结果与未接闸门时**逐位相同**（`max_abs_diff == 0`）|

---

### 7.11 `POST /custom/{id}/status` 的 V3 校验与排期（v0.5 追认；收口 §7.9.4 末条「尚未闭环」）

行号口径同 §7.4.1：对 `api/factors.py` 与 `store.py` 一律按符号引用，行号仅作参考。

#### 7.11.1 问题（事实，2026-11-07 16:42–16:45 本机复核）

- 端点 `POST /api/factors/custom/{factor_id}/status`（`update_factor_status`）接受 `draft|active|watch|retired` 四态（`FactorStatusRequest.status` 正则），**只做存在性检查（404）与 `register_definition` 的 schema 校验，不校验任何 V3 证据**：任一 store 定义都能被直接标成 `active`。
- 因此 §7.5-5「禁止给未通过 V3 的因子标 `active`」仍是**人工纪律**，不是代码约束；§7.7 的闸门保证「标了 `active` 之后谁还能用」，**不保证「谁能标 `active`」**。
- 后果不是理论问题：§7.10.4 的 **L2 放行依据 = `allowlist ∪ active`**。L2 一旦开启，`status=active` 本身就是**放行凭据**；激活不受控等于把门锁装在内侧 —— 调一次 status 端点即可绕过「allowlist 只许缩小」。
- 现状规模（本机实测）：`D:\TSP\data\user_data\custom_factors` **15/15 全为 `draft`、0 个 `active`**；`docs/factors/evidence/f_class_registry.json` 的 8 只 F 类同为 `draft`。故本节校验**今天上线零迁移风险**（没有 `active` 会被挡住或降级）。

#### 7.11.2 裁定：V3 是激活的唯一附加条件，证据必须是落盘物、不进 store

- **允许激活当且仅当**：`v3_status = pass` ∧ `max_abs_diff < 1e-12`（沿用 §7.6 `F-A3` 容差；**不是** `0`，也不是某次实测的 1 ULP）∧ `signed_by` 非空 ∧ 未过期。其余一律 `400 FS07`，盘上 `status` 不变。
- **不得新增落盘字段**：§7.4.3 第 3 条禁止给 store JSON 加字段，`v3_passed` 一类标记**不得**写进 `user_data/custom_factors/*.json`。证据只能来自只读落盘物。
- **证据视图（唯一）**：`docs/factors/evidence/factor_v3_index.json`，`schema = "factor_v3_index/1"`。字段级定义（顶层 4 + `records[]` 8）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema` | str | 固定 `factor_v3_index/1`；不匹配即 fail-closed |
| `generated_at` | ISO8601 | 生成时间 |
| `sources[]` | array | `{path, sha256, covers[]}`：每条来源报告（如 `F_CLASS_PARITY_20261107.json`）的路径、哈希、覆盖的 id |
| `records[]` | array | 逐因子记录，主键 `factor_id` |
| `records[].factor_id` | str | canonical id（`uf_*` / `cf_*`）|
| `records[].v3_status` | enum | `pass` / `fail` / `missing` |
| `records[].criterion` | str | 固定 `F-A3` |
| `records[].max_abs_diff` | float/null | 实测值；`v3_status=pass` 时必须非空且 `< 1e-12` |
| `records[].tolerance` | float | 固定 `1e-12`（不得写成 0，也不得写成 1.11e-16）|
| `records[].report_path` / `report_sha256` | str | 原始报告路径与字节哈希 |
| `records[].evidence` | str | `file:jsonpointer`，如 `docs/factors/evidence/F_CLASS_PARITY_20261107.json:#/factor_parity/uf_vol60` |
| `records[].signed_by` / `signed_at` / `expires_on` | str/null | 签认人（独立审核）、签认时间、失效日；`expires_on` 为空表示不过期 |

- **生成与签认分离**（角色分工同 §7.10.2）：生成 = **系统开发工程师**（纯聚合：从既有报告的 `factor_parity[].max_abs_diff` 取数，**不重算、不裁口径**）；签认 `signed_by` = **独立审核工程师**（`F-A3` 的 PASS 结论已在 `research/independent-review-20261107/F_CLASS_AUDIT_20261107.md`）；消费 = 端点（只读）。**因子工程师不经手该文件**（其写权在台账）。
- **fail-closed 三条**：索引缺失或不可解析 → 一律 `FS07`（不得因「读不到证据」而放行）；`v3_status=missing` 与 `fail` 同待遇；`expires_on` 过期视同 `missing`。
- **只读与缓存**：启动时读一次，索引 `sha256` 变化即重载；请求路径**不得**重新聚合。

#### 7.11.3 降级不设闸、激活幂等（方向性）

- `draft`/`watch`/`retired` 任意互转、以及从 `active` 降到任一态：**不看 V3，一律 200**。激活是唯一需要证据的方向；给降级加闸会在事故时挡住止损动作。
- **幂等**：`status` 已是目标态时重复提交 → `200`、响应 `unchanged=true`、**不写盘**（文件字节与 mtime 均不变）。现实现每次都 `unregister_factor` → `register_definition` → `save_one`，会刷 `updated_at` 与 mtime；本条与该端点的 V3 校验**并入同一处改动**，不单独排期。

#### 7.11.4 排期：**L1 之后、L2 之前**（L2 的进入条件追加一条）

- **不能排在 L2 之后**：L2 的放行凭据是 `allowlist ∪ active`（§7.10.4）。激活不受控 = 凭据可自造，与「allowlist 只许缩小、不得手写」直接冲突。
- **不必排在 L0/L1 之前**：L0 只生成清单、L1 只写影子报告，都不按 `active` 放行，此时弱激活**不产生放行后果**；提前接只是多一次无收益的改动窗口。
- **与清单的关系**：互不依赖（清单管「谁被引用」，本节管「谁能标 `active`」），可并行开发；**但 L2 启动前两者都必须通过**。
- 本条为 §7.10.4 `L2` 行的**追加**进入条件（不改该表原文）：`L2 进入条件 = L1 过 + allowlist 已签认 + F-A30–F-A32 通过`。

#### 7.11.5 判据（续 §7.6 编号，接 §7.10.6 的 `F-A29`）

| # | 判据 | 度量 |
| --- | --- | --- |
| F-A30 | 未过 V3 不得激活 | 对 `v3_status ∈ {fail, missing}` 或索引无记录的 id 提交 `{status:"active"}`：`400`、`detail.code="FS07"`、盘上 `status` 不变、文件字节与 mtime 均不变 |
| F-A31 | 降级与三态不受限 | `draft`/`watch`/`retired` 任意互转、`active`→任一态：`200`；把索引整体删掉后重跑本行仍 `200`（降级不因证据缺失被挡）|
| F-A32 | 索引 fail-closed | 删除索引后重试 `F-A30` 第一例：仍 `400 FS07`；启动日志含 1 条 `v3_index_unavailable`；损坏 JSON 与缺失同待遇 |
| F-A33 | 排期可验证 | L2 生效期在 `active` 定义上重放 `F-A30` 第一例：仍 `400`；L2 启动配置若缺 `F-A30`–`F-A32` 的通过记录，`gate` 拒绝以 L2 启动 |

**错误码**：`FS07` = 「未通过 V3 对账即要求标 `active`」，`400`，`detail` 含 `factor_id` / `requested_status` / `v3_status` / `evidence`。`FS07` 在 §7.10.2 的 `code` 枚举里已预留（`FS01`–`FS07`），本节只是给它定义，不新增码位。

**范围**：仅 store 定义（`kind=custom|composite`）。pack 14 个与 `kind=virtual` 无盘上定义，本端点对其仍返回 `404`（现状不变），其准入按 §7.8.4 走。

#### 7.11.6 一处事实校正（不改判据）

- §7.7.6 第 1 条说「改状态会抬版本」。实测：`update_factor_status` 走 `target["status"]=...` → `unregister_factor` → `register_definition(target)` → `save_one`，`version` **不变**、`updated_at` 与 mtime 变；该路径**不触发** `materialize_cache` 键变化（键含 `spec.version`）。「抬版本」只适用于经 `upsert_definition` 的路径（显式带 `status` 的提交）。§7.7.6 的两条硬要求不变：数值逐位相同、`status` 变更不得改变计算结果。

### 7.12 清单 v2 规格：粒度、记录身份、canonical digest、`summary` 分层与 v1 兼容（v0.6 追认）

#### 7.12.1 问题（事实，2026-11-07 16:58–17:12 本机实测）

盘上同时存在两份同名产物，谁也判不了谁：

- **实施产物** `docs/architecture/evidence/referenced_factor_inventory.json`：17:03 版为 `schema_version="1"`、`records` **167** 条，其中 `source_enabled=true` **53** 条、`both_collision=true` **8** 条、`path_divergence=true` **0** 条，`summary` 扁平 `by_verdict {allow 63, exempt 104}`。**该版已于 17:10:10 被重生成覆盖**（现状见下一条），其字节不再存在。
- **实施产物现状**（17:10:10，152,826 B，全文 sha256 `2b9bb771…e8c1`）：`schema_version="2"`、`records` **218** 条、`source_enabled=true` **93** 条（= 主 79 + 伴生 14）、`both_collision=true` **14** 条、`path_divergence=true` **0** 条；`summary` 已分层（`live_config` / `all_records`）。粒度这一项已按逐出现对齐（§7.12.2 的口径即由此确定），但字段与定位符仍有差距，见 §7.12.8。
- **研究侧期望表** `docs/factors/evidence/referenced_factor_inventory_expected_20261107.json`（16:58，`kind="expected_table_not_artifact"`）：`records` **79** 条，只覆盖 22 条活配置。

17:03 那版「两份产物不可机械比对」的根因三处，均可定位到代码：

1. **去重粒度**：`backend/scripts/build_referenced_factor_inventory.py` 的 `_dedup()`（`:323-328`）与 `emit()` 的 `seen` 集合（`:268-272`）按「同一 source + 同一原始串」去重。`ma_golden_20_60.json` 有两条条件（`:9` 的 `ma20`/`field:ma60`、`:16` 的 `ma20`/`field:ma60`），17:03 版只留前一对（`:9`/`:11`），后一对丢弃。
2. **字面量被改写**：`_condition_refs()` 把 `field:` 前缀剥掉（`:342-343`），落成 `ref_raw="ma60"`；期望表保留字面量 `field:ma60`（79 条中 38 条带前缀）。`ref_raw` 的含义两边不同 —— **17:10 版仍未改**（键里带 `field:` 的 `ref_raw` 为 **0** 条，前缀被搬进 `side` 写成 `"R:field"`）。
3. **路径基准混用**：`source_path` 同时出现仓库内相对路径（`backend/app/strategy/seeds/…`、`research/strategy-search-20261107/…`）与 `data_root` 相对路径（`custom_signals/…`）。v0.4 写的是「相对仓库根或 data_root」，两个基准共存，消费方无法判定。

后果不是好看的差别，而是**不可机械比对**：4 个冲突名在 17:03 版共 16 条记录（8 个 (源,名) 组合 × 主/伴生）、在期望侧 14 条；数字接近但定义不同，任何逐条 diff 都以失败告终，`F-A22`（幂等）与 `F-A24`（冲突必须报）的计数也不可比。

#### 7.12.2 口径：一条记录 = 一个结构化引用出现处

- **计数单位**：`left` 与 `right` 各算一处；monitor 规则的 `conditions[].field` 各算一处；`field:` / `column:` 前缀不改变计数（它只是字面量的一部分）。
- **不合并重复名**：同一 source 内同一名字出现 n 次 = n 条**主记录**。理由：`evidence` 是 `file:line`，去重就是**丢行号**；行号既是审核复现的唯一凭据，也是「同一名字两处、条件不同」的唯一区分手段。
- **伴生记录与主记录一一对应**：`both_collision` 名在第 k 个出现处 → 主记录 1 条 + 伴生 1 条。故 `records` 总数 = 主记录数 + 伴生记录数。
- **唯一键**：`(source_path, evidence, side, ref_name, record_kind)` 在一个产物内必须唯一；重复即生成失败（不是警告）。
- **今日实测计数**（活配置 22 源 = `custom_signal` 21 + `monitor_rule` 1）：主记录 **79**（`custom_signal` 77 + `monitor_rule` 2）+ 伴生 **14** = **93**。伴生 14 = 4 个冲突名逐出现展开：`ma20` 10 + `ma60` 2 + `boll_lower` 1 + `boll_upper` 1。17:10 产物已实测出 **93 = 79 + 14**，与本口径一致。
- **三个版本的对照**：17:03 版 53 条 / 伴生 8 条（8 是「(源,名) 组合」不是「出现处」）；17:10 版 93 条 / 伴生 14 条（口径已对齐）；期望表 79 条（只数主记录）。**只有 17:10 版与期望表的差是可解释的（79 = 主记录）**。
- **`evidence` 严格可解析**：`path:line`，跨行写 `path:start-end`，**不得夹注释**。反例（17:03 与 17:10 版均有）：`custom_signals/ma_golden_20_60.json:9  # N2 伴生记录: 同名基础列优先, 不参与放行` —— 定位符被注释污染，任何按 `:` 切分的消费方都会错。实测 17:10 版仍有 **14 条** `evidence` 含 `#`。
- **伴生记录固定取值**：`record_kind=companion`、`both_collision=true`、`verdict=exempt`、`code=null`；**不参与** allowlist、不参与放行判定、不计入任何层的 `by_verdict`（§7.12.5）。

#### 7.12.3 五个字面量字段的唯一写法

| 字段 | 定义 | 反例（17:10 产物）| 正确写法 |
| --- | --- | --- | --- |
| `ref_raw` | 配置文件里的**字面量**，保留 `field:` / `column:` / `signal:` 前缀 | `ma60`（前缀被搬进 `side`）| `field:ma60` |
| `ref_name` | 归一化名：去前缀 + trim | （缺字段）| `ma60` |
| `side` | 表达式槽位，只允许 `L` / `R` / `F` | `R:field`、`scoring`、`fields.entry`、`members`、`formula`（实测 9 种取值）| `R` |
| `side_key` | 结构键路径（人读定位，可选，不判）| （现占用 `side`）| `fields.entry` |
| `path_base` | 路径基准 | （缺字段，路径混用）| `data` + `custom_signals/ma_golden_20_60.json` |

monitor 规则的 `side`：引用写在 `conditions[].field`（`monitor_rules/lot_1a1aa285978_521c_p.json:11-14` 两条 `close`），按 `F` 计，仍**逐条** —— 两条 `close` = 2 条记录，与实测 `monitor_rule` 主记录 = 2、`path_scope=intraday` 记录 = 2 一致。

**为什么把「槽位」与「结构键」拆成两个字段**：17:10 版把两者塞进一个 `side`，实测 9 种取值 —— `L` / `R:field` 是槽位+前缀，`scoring` / `formula` / `fields.entry` / `fields.score` / `fields.exit` / `members` / `field` 是结构键。一个字段两种维度，就没法机械判「左值还是右值」，也没法做唯一键。拆开后：`side` 三值可判、`side_key` 只做人读。

#### 7.12.4 canonical digest（唯一签认对象，可复算）

定义（缺一项都不是同一口径）：

1. 取产物 JSON 对象，**剔除** `generated_at`、`repo_head`、`data_root`、`canonical_digest` 四个键（前三个与内容无关或与机器相关，第四个是自指）。
2. `records` 按每条记录自身的规范化 JSON 排序（`rk(x) = json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`），得到与输入顺序无关的全序。
3. 余下对象整体 `json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`，UTF-8 编码后取 sha256。

复算命令（逐字执行；`ensure_ascii=True` 或默认分隔符会得到另一个稳定值，不是同一口径）：

```bash
python - <<'PY'
import json, hashlib
p = 'docs/architecture/evidence/referenced_factor_inventory.json'
DROP = {'generated_at', 'repo_head', 'data_root', 'canonical_digest'}
rk = lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
d = json.load(open(p, encoding='utf-8'))
q = {k: v for k, v in d.items() if k not in DROP}
q['records'] = sorted(q.get('records', []), key=rk)
blob = json.dumps(q, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
print(hashlib.sha256(blob.encode('utf-8')).hexdigest())
PY
```

稳定性实测（对 **17:10:10 产物**跑上式，四类扰动）：

| 扰动 | canonical digest |
| --- | --- |
| 原样 | `9d34fef766da94f6a87ef5ed0b40863209f013a1a0390c47491e6766dc1ced3b` |
| 改 `generated_at` / `repo_head` / `data_root` | **不变** |
| `records` 整体倒序 | **不变** |
| `records` 随机重排（`random.seed(7)`）| **不变** |
| 改任意一条 `verdict`（`allow`→`block`）| `faec112db19ffc9e7383f4fda912f46eccd579463f4f7275f5c5df9be2f6c83b` |

配套三条硬规则：

- `canonical_digest` **写入产物顶层**，但计算时剔除自身（否则自指无解）；校验方重算后与落盘值比对，不等即 fail-closed。
- **旁挂 `.sha256` 降级为「本次运行字节完整性」**：它取全文哈希，含 `generated_at`，重跑一次必变（开发经理实测重跑得到 `6f528bcb…`，按原字节还原后侧车须手写回 `3c9a186a…` 才与文件一致；17:10 版侧车与字节一致，为 `2b9bb771…`）。**不得作签认对象、不得作 `F-A22` 比对基准、闸门不得读它**。
- 签认对象 = `canonical_digest` + `schema_version` + `scanned_sources` 三元组；因子工程师签这三个值即可，不必签文件字节。

#### 7.12.5 `summary` 必须分层

v0.4 的 `summary` 扁平（`by_verdict` / `by_code` / `by_namespace`），覆盖**全仓六类源**。17:03 版实测 `by_verdict {allow 63, exempt 104}` = **167 条混算**，读者从中读不出「闸门会拦谁」—— L2 要的是活配置的判词。

规定结构（两层 + v1 兼容别名）：

| 层 | 键 | 含义 |
| --- | --- | --- |
| `summary.live_config` | `sources` / `unique_sources` / `records` / `by_verdict` / `by_record_kind` / `by_namespace` / `by_class` / `by_path_scope` / `by_verdict_sources` | 只统计 `source_enabled=true` 的源；`by_verdict` **只按 `record_kind=primary` 计数**；`by_verdict_sources` = 每源取最坏 verdict（`block` > `shadow` > `allow`）|
| `summary.all_records` | `records` / `by_verdict` / `by_code` / `by_namespace` / `by_class` / `by_path_scope` / `by_record_kind` | 全仓六类源；`by_verdict` 同样只按 primary 计数，伴生只计入 `by_record_kind.companion` |
| `summary.by_verdict` / `by_code` / `by_namespace`（顶层）| 同 v1 | **v1 兼容别名**，值与 `summary.all_records` 对应项相等（`F-A35` 断言）|

三条使用规则：

- **L2 构建 allowlist 只许读 `summary.live_config`**，并按逐记录条件 `source_enabled=true AND record_kind=primary` 复算；读 `all_records` 或顶层别名建名单 = 违规（会混进研究侧与种子策略的条目）。
- `source_enabled` 为 `null` 的源（该源无顶层开关字段）**不进** `live_config`，只在 `all_records`。今天六类源里 `strategy_config` / `strategy_override` / `custom_factor` / `research_strategy` 全为 `null`，故 `live_config.sources = 22`（17:10 版实测 22，一致）。
- 伴生记录在任何层的 `by_verdict` 里都不出现，只在 `by_record_kind.companion` 计数 —— 这是「伴生不参与放行」的机械保证。

#### 7.12.6 对清单 v1 是否向后兼容（逐条，五项）

| # | v0.6 的改动 | 对 `schema_version="1"` 产物 | 结论 |
| --- | --- | --- | --- |
| 1 | 字段表补 `path_divergence` / `both_collision`，新增 `side` / `ref_name` / `record_kind` / `path_base`（+ 可选 `side_key`）| 前两项 v1 **已实际产出**（实施超表），契约只是追平，读取无影响；`side` / `ref_name` / `record_kind` / `path_base` v1 均缺失 | **格式兼容（前两项）/ 不兼容（四项新增）**：v1 只能在 L0/L1 用，L2 起必须 `"2"` |
| 2 | 粒度改为一出现一记录 | v1 是「(源,名) 去重」，同一 22 源 53 条 ≠ 93 条 | **计数不兼容，判词语义兼容**：v1 按 `(source_id, ref_name)` 折叠后 `verdict` 与 v2 逐 id 相等（可机械验证）。不翻转任何放行结论，只影响可追溯性 |
| 3 | 新增 `canonical_digest` | v1 无此字段 | **不兼容（新增必填）**。迁移不是重算：v1 可用同一 recipe 从外部算出，故签认可对 v1 先做一次；闸门读顶层字段时读不到 → L2 起必须 `"2"` |
| 4 | `path_scope` 裁定为 `history`（N4）| v1 产物已是 `history 166 / intraday 1`（17:10 版 `216 / 2`），无 `both` | **完全兼容（格式与取值）**。要撤回的是研究侧期望表的 `both`/`shadow`，那是口径文件不是产物（N4.3）|
| 5 | `summary` 分层 | v1 扁平键仍在，语义 = `all_records` | **完全兼容**：顶层三键保留为别名（`F-A35` 断言等值），新增两层不删旧键 |

一句话：**格式上 v1 缺 `side` / `ref_name` / `record_kind` / `path_base` / `canonical_digest` 与分层 `summary`；语义上一条结论都不翻转。** 重生成一次即可，不需要改判据、不需要重跑任何数值。

#### 7.12.7 判据（续 §7.10.6 / §7.11.5 编号，接 `F-A33`）

| # | 判据 | 度量 |
| --- | --- | --- |
| F-A34 | 粒度与唯一键 | `ma_golden_20_60.json` 必须出 **4 条主记录**（`ma20`@`:9` `L`、`field:ma60`@`:11` `R`、`ma20`@`:16` `L`、`field:ma60`@`:18` `R`）；全产物无 `(source_path, evidence, side, ref_name, record_kind)` 重复；活配置 `records = 93 = 79 主 + 14 伴生` |
| F-A35 | `summary` 分层自洽 | `sum(all_records.by_verdict) == all_records.by_record_kind.primary`；`live_config` 同式；`summary.by_verdict == all_records.by_verdict`（别名等值）；`live_config.sources == 22`。反例必须失败：把伴生计入任一层 `by_verdict` 时不通过 |
| F-A36 | canonical digest 可复算且稳定 | 按 §7.12.4 代码复算 == 落盘 `canonical_digest`；扰动 `generated_at`/`repo_head`/`data_root` 与记录顺序后不变；改任一 `verdict` 必变；把旁挂 `.sha256` 当签认对象时不通过 |
| F-A37 | 字面量与定位符 | `ref_raw` 保留前缀（`:11` 必须 `field:ma60`）、`ref_name=ma60`；`side ∈ {L,R,F}` 且必填；`evidence` 可按 `path:line` 解析、不含 `#`；结构键只许进 `side_key` |
| F-A38 | `path_scope` 与 `both` | 取值集合 ⊆ `{history, intraday}`（今日 `both` 计数 **0**）；21 条日线信号全 `history`、1 条 monitor 规则 `intraday`；`path_divergence=true` 计数 **0**；7 条冲突源 `verdict=allow` |
| F-A39 | v1 兼容与降级边界 | `schema_version="1"`：可读（`ref_name:=ref_raw`、`side:=null`、`record_kind:=primary`）、只许 L0/L1；读 `"1"` 却要求 L2/L3 → 拒绝启动。`"2"` 且缺任一新增字段 → 拒绝加载 |

#### 7.12.8 对 17:10 产物的实测差距（只报事实，不判验收）

实施侧 17:10:10 已重生成，六条判据的现状实测如下。**本表不是验收结论**（验收归独立审核工程师），只标出还差什么：

| 判据 | 17:10 产物实测 | 差什么 |
| --- | --- | --- |
| F-A34 粒度与唯一键 | 218 条；活配置 93 = 79 主 + 14 伴生；`ma_golden_20_60` 4 主 + 4 伴生（`:9`/`:11`/`:16`/`:18`）；`(source_path, evidence, side, ref_raw)` 无重复（0 组）| **字段级已达标**；缺 `ref_name` / `record_kind`，故唯一键与 `by_record_kind` 只能用代理量 |
| F-A35 summary 分层 | `live_config.by_verdict {allow 79}`（只含主记录）；`all_records.by_verdict {allow 97, exempt 107}`；`live_config.sources 22` | **大体达标**；键名不同：用 `judged_records` / `companion_records` 而非 `by_record_kind`，用 `by_source_verdict` 而非 `by_verdict_sources`，且缺 `by_path_scope`；顶层 v1 别名三键缺失 |
| F-A36 canonical digest | 无 `canonical_digest` 字段；旁挂 `.sha256` = 全文 `2b9bb771…` | **未达标**：须新增字段（值可按 §7.12.4 外部算出为 `9d34fef7…`）|
| F-A37 字面量与定位符 | `ref_raw` 带前缀 **0** 条；`side` 有 **9** 种取值（`L`/`R:field`/`scoring`/`formula`/`fields.entry`/`fields.score`/`fields.exit`/`members`/`field`）；`evidence` 含 `#` **14** 条 | **未达标**：前缀须回 `ref_raw`、`side` 须收窄为三值、结构键移 `side_key`、伴生 `evidence` 去注释 |
| F-A38 path_scope 与 both | `history 216` / `intraday 2`；`both` 0；`path_divergence` 0；活配置 `verdict` 全 `allow`（79）| **已达标**（实测）|
| F-A39 v1 兼容 | 产物已是 `"2"` | **未验证**：`"1"` 的降级读法与「读 `"1"` 却要求 L2/L3 拒绝启动」无实现 |

本轮只给规格。重生成、字段补齐、`summary` 键名、`canonical_digest` = 系统开发工程师；期望表 `both`/`shadow` 改判与 `side` 补列 = 因子工程师（`docs/factors/` 写权归其）；契约文本 = 本文件。`gate.py` 未实现，`F-A34`–`F-A39` 除上表实测项外**均未实跑**。

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
| D2 `rsi_14_pct`（Wilder 平滑、涨跌幅口径） | **新增模块（新增 base 列；不改 DSL 算子层）** | `registry.py#_CATALOG`（`:83`）新增 `_base("rsi_14_pct", …)`；`indicators/pipeline.py` 新增一列（`ewm_mean(alpha=1/14, adjust=False)`，与 `:576-577` 同法）；`backtest/matrix.py#_MATRIX_COMPUTED_FEATURES` + `#_compute_matrix_feature` 新增分支 | `dsl.py#OPERATORS` 实测 **25** 个键（`len(OPERATORS)==25`；因子工程师文档写「26」，差 1 属计数差异），**无 `ewm`/`ewma`/`wilders`**；但 `ewm_mean` 在指标层已用于 `rsi_6/14/24`（`pipeline.py:576-577`）与 `atr_14`（`:503`）→ 不必扩算子。**不新增错误码**；若强行扩算子则需 `E018`（`E017` 已被 E2 掩码占用）。落点裁定与被否决方案见 §8.1 |
| **`ewm` / Wilder 平滑算子**（引擎能力缺口，v0.3 登记） | **不改引擎：否决扩算子** | 不落 `app/factors/dsl.py#OPERATORS`（保持 **25** 键，`TS_OPERATORS` 13 / `CROSS_OPERATORS` 3 不变）；策略侧仍不能用 DSL 写 `ewm(...)`，编译期按未知算子返回 **`E002`**（判据 F-A13）；若日后改判为扩算子，则需 `TS_OPERATORS` 13→14 + 新错误码 **`E018`**（`E017` 已被 E2 掩码占用）+ 面板/矩阵两条求值路径逐位一致 | 派单把它登记为「引擎能力缺口（改引擎）」，架构裁定为**不扩**：Wilder 平滑在指标层已存在（`pipeline.py:576-577`、`:503`），`rsi_14_pct` 改走 base 列（§8.1）。故本条的真实改动性质是「新增 base 列」，不是「改算子层」；`E018` 仅预留给「改判后」的场景，**当前没有任何代码路径会返回它** |
| 因子回测 `rebalance` 字段 | **不改** | `app/api/backtest.py:149`、`app/backtest/factor.py:54,112` | 语义为统计分组周期；仅需 UI 文案区分 |
| 回测排序与仓位 | **不改** | `app/backtest/engine.py#_plan_buys`（3496 行排序、3514-3518 权重） | X1 逐字镜像它，不重写 |

**为什么 E1/E2 必须改引擎而不是新增模块**：掩码截面排名需要「分子与分母取同一批（池内非空）样本」，而另两个 id 分别是全样本口径与混合分母口径（§3.1 表），这是 polars 表达式层的一次分组聚合，必须在 DSL 编译期知道 `cross_sectional=True` 才能阻止其被嵌进时序窗口（沿用 `E009` 纪律）。放在策略层或后处理层做，会被 `materialize_scoring_columns` 的窗口补算路径吃掉，且无法被 `/api/factors/validate` 提前拦住。

### 8.1 `rsi_14_pct`（D2）落点裁定：base 列，不动 DSL 算子层（v0.3 新增；v0.4 把预热拆成两套语义并写死 `al=0` 判定）

**事实（实测）**
- `app/factors/dsl.py#OPERATORS` 现有 **25** 个键（`len(OPERATORS)==25`；`TS_OPERATORS` 13、`CROSS_OPERATORS` 3），**无 `ewm`/`ewma`/`wilders` 类算子**；`ts_mean` 是等权滑动均值，**不能**表达 Wilder 递推。（因子工程师 `F_CLASS_REGISTRATION_20261107.md:224` 写「OPERATORS 26 个」，与实测差 1，属计数差异；结论相同：没有 ewm。）
- 指标层**已有** Wilder 平滑：`rsi_6/14/24` 用 `pl.col("_gain").ewm_mean(alpha=a, adjust=False)`（`app/indicators/pipeline.py:576-577`，`a = 1/n`），`atr_14` 同法（`:503`），`ema5…ema60` 亦为 `ewm_mean`（`:417-429`）。
- `rsi_14` 已是 base 因子（`registry.py:108`）；`rsi_14_pct` 与它**只差输入**（`pct_change` vs `close.diff()`），算法同为 `ewm(alpha=1/14, adjust=False)`（`FACTOR_GAP_SPEC` §D2）。
- 既有缺口：`rsi_14` 的 `_base(...)` 未传 `warmup_bars`（`registry.py:108`，默认 1），而 Wilder 递推同样需要长预热 → 同一数值风险**已存在于 S04 现用因子**。本条只登记，不扩大范围修正既有因子。

**裁定：`rsi_14_pct` = 新增 base 列（面板 + 矩阵两条路径各一处实现），不改 `dsl.py#OPERATORS`。**
落点（字段级）：
1. `app/factors/registry.py#_CATALOG`（`:83`；v0.4 自纠：原写符号名 `FACTOR_SPECS`，模块内不存在）新增 `_base("rsi_14_pct", "RSI(14,涨跌幅)", "超买超卖", "14日相对强弱指标(涨跌幅口径)", warmup_bars=600)`；base 因子 `dependencies` 为空集（= 已物化列自身），`unit="index"`、`scale_free=false` 只能登记在台账（§7.2 的 P2 缺口）。
2. `app/indicators/pipeline.py` 新增一列：复用 `:576-577` 的 `_gain/_loss + ewm_mean(alpha=1/14, adjust=False)` 写法，输入改为 `pct_change`；`1e-12` 护栏是否沿用，须与 D2 的 `max_abs_diff < 1e-10` 对账后决定（不得为了「除零好看」改变判据）。
3. `app/backtest/matrix.py#_MATRIX_COMPUTED_FEATURES` + `#_compute_matrix_feature` 新增分支：矩阵路径是逐元素 numpy 实现，**必须与面板路径逐位一致**（这是本条最大的实现风险，见 F-A11）。
4. 台账（`docs/factors/`）登记：口径 `price_pct`、`unit="index"`、`scale_free=false`；D2 已定 `rsi_14` 不得被策略引用，`replaced_by` 反向指向 `rsi_14_pct`。

**预热是两套语义，必须分开写（v0.4 更正：v0.3 只写了一个数字 373，与策略侧「从首根 `ret1` 起算」无法共存）**

**W-A 引擎 / 矩阵侧预热（`warmup_bars`，取值 600）**

Wilder 是无限记忆递推，初值影响按 `(1-alpha)^n = (13/14)^n` 衰减。解析门槛：`(13/14)^n < 1e-12` → n ≥ 373；对 `1e-10` → n ≥ 311。**但解析门槛只算 seed 权重，没算 RSI 的导数放大**（`dRSI/dRS = 100/(1+RS)^2`，RS≈1 处放大 25 倍，上界 100 倍）——所以 373 在值域上**不够**。

实测（可复跑）：域 `D:/TSP/data/kline_daily/*/*.parquet`，2019-01-02 起，按 symbol 名排序取前 300 只（有效 279 只，其余窗口不足），在 `2024-01-02` 起比对「窗口内重启递推」与「自 symbol 首根 bar 起算」的逐行差：

| 预热根数 k | `max_abs_diff` | p95 | 中位数 | 判定 |
| --- | --- | --- | --- | --- |
| 28（`py_expr` 的 `span=2/α-1`） | **12.819** | — | 1.651 | 灾难性，`RSI<30` 成片翻转 |
| 100 | 5.40e-02 | — | 8.35e-03 | 不可用 |
| 311 | 4.20e-08 | — | 1.95e-09 | 不达 `1e-10` |
| 373 | **1.445e-10** | 6.01e-11 | 2.11e-11 | **超 `1e-10` 门槛 1.4 倍** |
| 450 | 2.56e-13 | 1.42e-13 | 5.68e-14 | 达标 |
| 500 | 2.84e-14 | 2.13e-14 | 7.11e-15 | 达标 |
| **600** | **0.0（逐位一致）** | 0.0 | 0.0 | **契约取值** |

裁定：`warmup_bars = 600`。**失效边界**：k ≥ 450 才稳定进 `1e-10`；k = 373 差 1.4 倍；k ≤ 100 误差到 `1e-2`；k = 28 到 **12.8 个 RSI 点**。**代价**：矩阵/增量路径必须比首个使用点早 600 根起算（≈2.4 年）；首个使用点早于数据首部时按 symbol 首根起算（无代价）；面板全历史路径不受影响。

**W-B 研究 / 策略侧可用区（不是 `warmup_bars`）**

- 数值上**自 symbol 首根 bar 起算**（与 `research/strategy-search-20261107/scripts/common.py:139-151` 的 `ewm_mean(adjust=False).over("symbol")` 逐位一致）。**不得**为对齐预热而截断、也**不得**用 null 掩码（截断或掩码都会直接破坏逐位一致；这是策略经理 `caliber-decisions-20261107.md` §8.3.2 的裁定，本契约采纳）。
- 首个可用值位置：实测 5,813 只全部在 `i=0` 就产出值，但 `i=0` 是 `0/0`（见 W-C），转 null 后首个可用值是 `i=1`（`ret1` 首次有定义处）——与台账 `warmup_bars=1` 的表述一致。
- `warmup_note`（台账字段，不入 runtime）：前 14 根数值未稳定，**S04 不得用于上市不足 15 根的标的** → 对应 `min_history_bars = 15`，由策略准入层按 `observed_bars` 判（`common.py:138` 同义），**不得**用 `warmup_bars` 代判。
- 硬规则：`warmup_bars` **只能**用于「重算种子点 / 缓存预热」，**禁止**用于 null 掩码或「前 N 根不可交易」判定。若实现只肯落一个数字：落 600，且不做掩码。

**W-C `al=0` / `ag=0` 的判定式（写死，禁止兜底）**

判定式固定为 `100 - 100/(1 + ag/al)`，**不得**加 `1e-12` 护栏（现网 `app/indicators/pipeline.py:580-583` 的 `rsi_6/14/24` 有护栏，`rsi_14_pct` **不得**沿用）：

| 情形 | 结果 | 依据 |
| --- | --- | --- |
| `al == 0` 且 `ag > 0` | **100.0**（IEEE `x/0 = +inf` → `100-100/inf = 100`），**禁止兜成 null** | 实测 9,356 行，plain 恒为 `100.0` |
| `al == 0` 且 `ag == 0` | **null**（`0/0 = NaN`，必须显式 `fill_nan(None)`；NaN 不等于 null，`null_count()` 抓不到） | 实测 6,033 行 |
| `ag == 0` 且 `al > 0` | 0.0 | 实测 5,702 行 |

护栏的代价（实测）：若沿用 `1e-12` 兜底，`al=0 ∧ ag>0` 的 9,356 行会变成 `99.9999865614…99.9999999995`，`max|Δ| = 1.344e-05`，是 `F-A10` 门槛 `1e-10` 的 **约 13 万倍** → 必然判 fail。这就是「为了除零好看改判据」的反例。

**W-D 两个必须报数的项（可复算；缺一即报告不合格）**

1. **`al == 0` 行数**（并拆 `ag>0` / `ag==0` 两个子数）。本机实测：**15,389 = 9,356 + 6,033**（域 `2019-01-02`–`2026-11-06`，`9,025,084` 行 / `5,813` 只）。
2. **仅一侧为空的 `ag`/`al` 行数必须 = 0**：`(ag.is_null() XOR al.is_null()).sum() == 0`。本机实测 **0**。非 0 即说明两条 `ewm_mean` 的空值处理或分窗起算点不一致，一律 fail。
3. 附带报数：`rsi` 的 NaN 行数 = **6,033**（`i=0` 5,813 / `i=1` 218 / `i=2` 2）；转 null 后 null 行数必须等于同值。

**被否决的方案（附代价）**

| 方案 | 代价 | 为什么否决 |
| --- | --- | --- |
| 扩 DSL 算子 `ewm(x, alpha)` | `OPERATORS` 25→26、`TS_OPERATORS` 13→14；新增 `alpha∈(0,1)`/`span≥1` 常量校验（复用 `E003`/`E004`）；warmup 推导；`_rolling_apply` 与矩阵逐元素两条求值路径都要验逐位一致；与 `E009`（截面算子不得嵌入时序窗口）的交互要重验；错误码需 `E018`（`E017` 已被 E2 掩码占用） | 只为 1 个**已定死** `alpha=1/14` 的因子扩语言；扩完策略侧即获得「任意 alpha」的自由度，台账无法穷举口径组合，违反 G7 可穷举版本化 |
| 注册为 `lang="python"` 的 T2 表达式因子（`py_expr.py` 支持 `ewm_mean`） | `py_expr` 的 warmup 推断按 `span = 2/alpha - 1 = 27` 计（`py_expr.py:106-112`）→ 声明 28 根，比 311 少一个数量级 → 数值对账必然失败；T2 不承载量纲/口径治理（`unit`/`scale_free` 不落盘）；T2 是「用户自建定义」通道，不应承载策略关键口径 | 省一次代码，换来永久的 `max_abs_diff` 不稳定 |
| 用 `ts_mean(ret1, 14)` 近似 Wilder | 口径不同 | 违反 G8；`RSI<30` 的 jaccard 必掉，D2 的 `≥0.999` 直接不成立 |

**验收判据（并入 §7.6 编号）**

| # | 判据 | 度量 |
| --- | --- | --- |
| F-A10 | 口径 | 与研究 `rsi14` 逐值 `max_abs_diff < 1e-10`；`RSI<30` 判定 `jaccard ≥ 0.999`；且 §8.1 W-C 三行**逐行**成立（`al=0 ∧ ag>0` 恒为 `100.0`、`al=0 ∧ ag=0` 为 null 而非 NaN、`ag=0 ∧ al>0` 为 0.0），§8.1 W-D 的两个报数项必须出现在报告里 |
| F-A11 | 双路径一致 | 面板路径 vs 矩阵路径逐位 `max_abs_diff < 1e-10`，且 NaN 位置逐个一致 |
| F-A12 | warmup（两套语义分开验） | ① 引擎侧：`warmup_bars == 600`；构造「自 symbol 首根起算」与「预热 k 根后重启」两组，`k=600` 时 `max_abs_diff == 0`，并复跑 `k ∈ {28,100,311,373,450,500}` 得 12.819 / 5.40e-02 / 4.20e-08 / 1.445e-10 / 2.56e-13 / 2.84e-14；② 策略侧：首个可用值在 `ret1` 首次有定义处（实测 `i=1`），**null 掩码不得由 `warmup_bars` 驱动**；`observed_bars < 15` 的标的不进 S04 |
| F-A13 | 不越权 | 策略侧仍**不能**用 DSL 直接写 Wilder 平滑（`ewm(...)` 仍返回 `E002`），只能引用 `rsi_14_pct`；`rsi_14` 未被任何策略引用（D2） |

---

## 9. 未覆盖与依赖

| 项 | 状态 |
| --- | --- |
| E1/E2/E3/E4/X1/F 契约 | 本文件 **v0.4（2026-11-07 已冻结）**；v0.3 为六处证据回灌（`CONTRACT_REVISION_R2_20261107.md`），v0.4 为 R3 三处裁定（§7.4 / §7.8 / §8.1，见 `CONTRACT_REVISION_R3_20261107.md`）；**v0.3 冻结态逐字节归档**于 `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`（89,833 B / 914 行 / 全文 `5eb97724…565903`），审核绑定可继续指向该归档 |
| **版本与绑定（v0.5 追认）** | 现行 **v0.5**（本文件）：v0.4 = `FACTOR_ENGINE_CONTRACTS_20261107.md`（128,007 B / 1,226 行 / 正文 `head -c 127043` → `71708877…d16bc` / 全文 `5bd81a74…c5531`），**仍是 `F-A5`（及 §7.9 / §7.10 判据）的绑定对象**；v0.5 只追认 §7.4.2 允许面（+`load_one`、+`POST /composite` 调用方）并新增 §7.11，**不改任何判据语义** |
| `max_hold_days` 生产侧（X2） | **不在本契约**，另立 |
| D1/D2/D3 口径决策 | 属因子工程师，本文件只引用不裁定 |
| 决定四（截面排名口径） | 由研究侧定稿（v1.2）；本文件只做字段级落地与判据锚定，冲突以决定四为准 |
| G1–G3 台账治理 | 不在本契约 |
| 停牌/涨停/退市/上市天数的**数据可得性** | 未验证；E3 的实现前提是行情库或 sidecar 有这些字段，属行情数据工程师职责 |
| **ST 历史表的数据质量**（v0.3 新增） | 已确证：`2026-10-20` 批量 198 行 `st_flag=false`，as-of ST 家数 218 → 20（§2.3 注 2）；数据末端 `2026-10-29`，之后无行（注 3）。**修数据源不在本部门范围**（属行情数据工程师）。契约侧只做三件事：窗口置 `null`（§2.3）、末端不外推（注 3）、X1 不清仓（§6.4） |
| **`status` 运行时闸门**（v0.3 新增） | 契约已定（§7.7 + v0.4 §7.8 的分支），实现未落：`FactorSpec` 无 `status`（`registry.py:33-56`）、无 `alias_of`、`app/factors/gate.py` 不存在。属批二前置 |
| **`rsi_14_pct` 的既有同族风险** | 已登记未修：`rsi_14`（`registry.py:108`）未声明 warmup（默认 1），与 §8.1 W-A 的 600 预热同一问题（默认 1 远小于 600，误差按 W-A 表可达 `1e-2` 量级）；不在本契约范围 |
| **F-A5 实现的审核状态** | 工作区有未提交实现（`store.py` 按符号定位，见 §7.4.2；HEAD 无）；独立审核未覆盖 → 判据待复核 |
| **双 id / 别名 / 不可复算因子**（v0.4 新增） | 契约已定（§7.8）；实现未落：无别名解析、`FS03`–`FS06` 未落地。现状 8 组同口径双 id 已并存（§7.8.1 #6），未声明 canonical 即 `FS06` |
| **R3 三处裁定的证据** | 全部可复跑：§7.4 允许面（`git diff --numstat` → `store.py` +187/−1、`api/factors.py` +14/−18（16:33:52/16:33:57，按符号定位见 §7.4.1））；§7.8 运行时 dump（`all_factors()` 192/207）；§8.1 预热表（300 symbol 子集）与 W-D 报数（`9,025,084` 行 / `5,813` 只）。命令逐条见 `CONTRACT_REVISION_R3_20261107.md` |
| 实现与验收 | 分别由系统开发工程师、独立审核工程师承担；**本文件不下验收结论** |
| **清单 v2（v0.6 追认）** | 规格见 §7.12 + §7.10.2 字段表 + §7.10.3 N4 + `F-A34`–`F-A39`。盘上产物已由系统开发工程师于 **17:10:10 重生成**（`schema_version="2"`、218 条、活配置 93 = 79 + 14、`summary` 已分层），粒度与 `path_scope` 两项实测达标；仍缺 `ref_name`/`record_kind`/`path_base`/`canonical_digest`，`side` 仍是 9 种取值的结构键、`ref_raw` 前缀被剥、伴生 `evidence` 夹注释（§7.12.8）。**L2 起不得读 v1** |
| **研究侧期望表 7 条 `both`（v0.6 改判）** | 按 N4.3：7 条冲突源 `path_scope=history`、`path_divergence=false`、`verdict=allow`。期望表在 `docs/factors/evidence/`，写权归因子工程师；本契约只给判据、不改其文件 |

**v0.4 → v0.5 绑定声明**：`v0.4`（`FACTOR_ENGINE_CONTRACTS_20261107.md`，128,007 B / 全文 `5bd81a74…c5531`）仍为 `F-A5` 的**绑定对象**，其四元组不因本版失效；`v0.5`（本文件）**只追认允许面**（§7.4.2 的 2 项）并新增 §7.11，**不改判据语义**。`v0.5` 生效后由独立审核按 `v0.5` 重判 §7.4（允许面）；`F-A5` 的数字锚点仍取 `v0.4` 四元组。逐条对照见 `docs/architecture/CONTRACT_REVISION_R5_20261107.md` §9。

**本契约不包含**：任何收益数字、参数调优建议、策略优劣判断。§4.6 出现的「平均值/通过率」是**口径复现靶值**（证明实现与研究同源），不是绩效结论；§3.4.3 `XS-C1` 的选股数与一致率是 `xs_rank_pct` 对**研究侧历史错口径**的复现证据，既不是策略验收，也不是任何实现的合格线。

---

本文件正文 sha256：`e3a4db17095d7e7f4461a2491f036b818225831b10e98f22242b6a3a0f2576ec`（校验：`head -c 160819 "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md" | sha256sum`）· 正文 `160819 B` · 行数 `1454` · 版本 **v0.6（2026-11-07 追认，未冻结）**· 冻结四元组（size / lines / body-prefix / full sha）见 `docs/architecture/CONTRACT_REVISION_R6_20261107.md` §8（不写进正文，避免自指）· 生成 2026-11-07 v0.6 = v0.5 逐字节为底 + R6 只追加：§7.10.2 字段表 +8 行（`path_divergence`/`both_collision` 补表，`side`/`ref_name`/`record_kind`/`path_base` 新增，`side_key` 可选，`canonical_digest` 顶层）/ §7.10.3 新增 N4（`path_scope` 只记真实路径，`both` 需编译证据）/ 新增 §7.12（粒度、记录身份、槽位与结构键拆分、canonical digest、`summary` 分层、v1 兼容、17:10 产物实测差距）+ `F-A34`–`F-A39` / `F-A22` 补 canonical digest / §9 增补两行 · **v0.4 = `FACTOR_ENGINE_CONTRACTS_20261107.md`（128,007 B / 1,226 行 / 正文 `head -c 127043` → `71708877…d16bc` / 全文 `5bd81a74…c5531`）仍为 `F-A5` 的绑定对象；v0.5 = `FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md`（138,729 B / 1,298 行 / 正文 `head -c 137598` → `082d26fa…af7fae` / 全文 `c7740508…0c4a21a`）一字未改；v0.6 只追加，不改判据语义** · v0.3 冻结态（89,833 B / 914 行 / 全文 `5eb97724…565903`）逐字节归档于 `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`
