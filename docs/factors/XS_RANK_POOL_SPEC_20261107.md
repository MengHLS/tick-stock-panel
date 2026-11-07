# 截面排名因子族可执行规格（决定四 · v1）

状态：**生效**，2026-11-07 14:30。依据 `docs/research/caliber-decisions-20261107.md` §7「决定四」（v1.1 修订）。
作者：因子研究员（策略研究部）。口径依据：`docs/research/caliber-decisions-20261107.md` §7 决定四 v1.2（2026-11-07 14:40）。本文件给**口径与验收判据**；不含实现代码、不含收益数字、未注册因子、未改引擎。
生效即意味着：`xs_rank_pool` 是**唯一**策略可用的截面排名口径；另两个 id 一律 `strategy_usable = false`。

---

## 0. 先看这张，再看 §1–§3

| id | 一句话 | 值域上界 | strategy_usable | 策略可引用 |
| --- | --- | --- | --- | --- |
| `xs_rank_pool` | 池内平均名次 ÷ 池内**非空**家数 | 1（当日 max 恒为 1） | **true** | 是，唯一 |
| `xs_rank_market` | 全样本平均名次 ÷ 全样本非空家数 | 1 | false | 否（仅诊断） |
| `xs_rank_pct` | 全样本平均名次 ÷ 池内家数 | ≈2.15–2.17（**>1**） | false | 否（仅历史/差异证明） |

### 0.1 判口径只看两个维度：分子作用域 × 分母

本次事故的形态是「同一个 `rk` 值在不同池下不可比、且可以 >1」。要杜绝复现，口径必须能被两个字段自检：`scope`（分子分母是否同一批样本）与 `denominator`（分母到底数了谁）。四种组合，三种已命名，一种明令禁止：

| # | 分子 | 分母 | 对应 id | 判定 |
| --- | --- | --- | --- | --- |
| ① | 池内名次 | 池内**非空**家数 | `xs_rank_pool` | **唯一策略可用** |
| ② | 全样本名次 | 全样本非空家数 | `xs_rank_market`（数值上 ≡ 现存 `rank`） | 仅诊断 |
| ③ | 全样本名次 | 池内家数（含 x 为空者） | `xs_rank_pct`（与研究 `rk_*` 同构） | 仅历史 |
| ④ | 池内名次 | 池内**全部**家数（`in_universe.sum()`） | **无 id** | **禁止**（见 §1.4-A5） |

④ 为什么单独列：它是「看起来最像 ①」的写法，也是唯一会导致**系统性偏低**的写法——池内某只票当日 `x` 为空时，`in_universe.sum()` 仍把它算进分母。例：池内 3 只、1 只 `x` 为空、名次 1 与 2 → 正确输出 `{0.5, 1.0}`；④ 输出 `{0.333, 0.667}`。这个指纹是 A5 的判据来源。

### 0.2 「现存实现」一词的两种含义（不要混用）

决定四 §7.3-3 把 `xs_rank_pct` 记为 `semantics = global_rank_over_pool_count`，即**研究侧 `rk_*` 的公式形态**。两处事实必须先对齐，否则下一个人会拿错数字：

1. `xs_rank_pct` 这个 id **尚未存在于 `dsl.py`**（证据：`CROSS_OPERATORS = frozenset({"rank","zscore","winsorize"})`，`backend/app/factors/dsl.py:74`；`grep -n "xs_rank" backend/app/factors/dsl.py` 为空）。
2. 系统今天**实际输出**的截面排名是 `dsl.py:506-508` 的 `rank`：`x.rank("average").over("date") / x.count().over("date")` = 全样本名次 / 全样本非空家数（分母 3,076–3,095），对应上表 ②，**不是** ③。

因此本文一律用「研究 `rk_*`」指 ③，「`rank` 算子」指 ②。把两者当同一个东西，会把「系统偏松」误说成「系统偏紧」。

---

## 1. `xs_rank_pool`（池内分位）— 唯一策略可用口径

### 1.1 五字段（缺一不成立）

| 字段 | 值 |
| --- | --- |
| `semantics` | `pool_percentile`：池内平均名次 ÷ 池内非空家数。语义可读作「该值在本日股票池内的分位」，`rk ≤ t` 即「池内最低 t」 |
| `scope` | **池内**：`in_universe == True` 且 `x` 非空。分子分母同一批样本 |
| `denominator` | `count(x, over date, 限定 in_universe & x 非空)` —— 池内**非空**家数，逐日重算。**禁止**用 `in_universe.sum()`（§0.1 ④） |
| `strategy_usable` | **true** |
| `replaced_by` | 不适用（本 id 是终态口径，不得被任何 id 取代） |

### 1.2 完整口径（登记所需八项）

| 项 | 值 |
| --- | --- |
| 算子签名 | `xs_rank_pool(x, mask)`；`mask` **必填**，无默认值。传字面 `true` 不构成合法池（那就是 `xs_rank_market`，应直接改用那个 id） |
| 等价式（口径式，非代码） | 令 `m = (mask == True) & x.is_not_null()`；先对 `m` 之外的行置 null，再在**同一列**上同时取 `rank("average").over("date")` 与 `count().over("date")`，两者相除 |
| 价基 | 继承 `x`。`x = momentum_5d` → 前复权 `close`；`x = vol60` → 前复权 `close` 的日收益 |
| 含当日 | **是**（当日收盘后可知当日截面；算子内部不 shift） |
| shift | **无**（算子内不 shift）。「此前」语义必须由 `x` 自带（如 `ts_delay(x,1)`），不得靠掩码或算子参数模拟 |
| 窗口 | 算子自身**不加窗口**（`0`）；窗口只在 `x` 内部 |
| `warmup_bars` 实需 | `max(warmup_bars(x), warmup_bars(in_universe))`。`x = momentum_5d` → `max(5,121)=121`；`x = vol60` → `max(61,121)=121`（`vol60` 需 `ret1` 1 根 + 60 根）。E3 的 121 随 `in_universe` 落地值变化，不得写死 |
| 数据源列 | `x` 的依赖列 + `in_universe` 的依赖列（`st_flag`、`raw_close`、`prior_amount_20`、`volume`、`observed_bars`） |
| 空值策略 | `keep`：`x` 为空、`mask` 非 True、`mask` 为 null、池外 → 输出 null。**不填 0、不前向填充、不折成 False 参与排名** |
| 财务 PIT | 否（量价因子）。`in_universe` 内 `prior_amount_20` 已按 shift(1) 口径，`st_flag`/`raw_close` 用当日 |
| 值域 | 池内非空家数 `n ≥ 1` 时，取值 ⊆ `{k/n}`，**max 恒为 1**，min = `1/n > 0`（即 `(0,1]`） |
| tie 规则 | `average`。4 只同值 → 全部 `2.5/4 = 0.625` |
| 定义域 | 仅主板 `60`/`00` 前缀（研究 `common.py:98-101`）。创业板/科创板/北交所从未进入排名样本，**不要用 5,000 只去复算** |
| 登记形态 | 族 id + 必填参数：策略引用写作 `xs_rank_pool(x=vol60, mask=in_universe)`。**不为每个 x 派生新 id**（首选）。若注册表只能「一条表达式一个 id」，则派生 `xs_rank_pool__<x>`，其 `semantics/scope/denominator` 必须与族 id 逐字相同、仅 `x` 不同，且必须由模板生成、禁止手写（防口径漂移） |

### 1.3 分子与分母必须同时改（这是与 `xs_rank_pct` 的全部差别）

| | 分子 | 分母 |
| --- | --- | --- |
| `xs_rank_pct` | 全样本非空名次 | 池内家数（含池内 x 为空者） |
| `xs_rank_pool` | **池内非空名次** | **池内非空家数** |

只改分母、或只改分子，都会得到上表以外的第五种口径。实现与验收必须同时断言两项。

### 1.4 边界与空值（逐条可断言）

| 场景 | 正确输出 | 理由 |
| --- | --- | --- |
| 当日池内非空家数 = 0 | 全 `null` | 不可算，不是 0 也不是 1 |
| 池内非空家数 = 1 | 该成员 `1.0` | 分母=1、名次=1 |
| 池内某成员 `x` 为空 | 该成员 `null`；**不进分母** | 这是与 `xs_rank_pct` 的关键差异 |
| `mask` 为 null | `null`；不进分母 | 与 research `fill_null(False)` 等价（池外） |
| 池外成员 | `null` | 不参与分子分母 |

### 1.5 验收判据

**1.5.1 抄自决定四 §7.3-5（缺一不通过）**

| # | 判据 | 度量 |
| --- | --- | --- |
| A1 | `max(xs_rank_pool) = 1` 且 `min > 0` | 逐日断言；**出现任何 `rk > 1` 直接判定不通过**（这一条就能一次性拦住本次事故，不需要人去读实现） |
| A2 | 单日计数恒等式 | `count(rk ≤ t)` 逐日等于池内 `rank ≤ t×P` 的真实计数，**容差 0**（两个实现相减为 0）；并逐日打印三个数：`P`（池内非空家数）、`count`、`t×P` |
| A3 | 回归保护 | 无掩码调用的 `rank(x)` 输出与现状**逐位相同**；对 93 个台账因子抽 20 个做列 hash 对比，逐位不变 |
| A4 | 池内家数逐日与研究一致 | 均值 1,429、逐日差 0 —— **依赖 E3（`in_universe`）；E3 未通过，E2 不可验收**（`P` 本身不可信） |

**1.5.2 因子研究员追加（不替代 A1–A4；A5/A8 是「分母数错人」与「tie 规则被换」的指纹）**

| # | 判据 | 期望 |
| --- | --- | --- |
| A5 | 分母只数池内非空 | 构造单日「池内 3 只、其中 1 只 `x` 为空」→ 输出 `{0.5, 1.0}`；若得 `{0.333, 0.667}` → 不通过（= 用了 `in_universe.sum()`） |
| A6 | 池空日 | 全 `null`（不是 0，不是 1） |
| A7 | 双路径一致 | 面板路径 `pipeline.py` 与矩阵路径 `matrix.py` 逐位差 ≤ `1e-12`，或显式记录 float32 误差来源 |
| A8 | tie 规则 | 4 只同值 → 全部 `0.625`；若得 `{0.25,0.5,0.75,1.0}`（ordinal）或 `{0.25,0.25,0.75,0.75}`（min/max）→ 不通过 |

`t` 取 `{0.05, 0.10, 0.30}`（就是 S06/S07/S10/S11/S12 现用的三个阈值，不新增）。

### 1.6 禁止事项

1. 禁止用 `in_universe.sum()` 作分母（A5 指纹）。
2. 禁止给现有 `rank` 加隐式默认掩码（违反 A3）。
3. 禁止在策略文件、策略 seed、执行器里手写 `rank()/count()` 重现本算子——踩「策略必须经因子实现」。
4. 禁止把 `mask` 省略成字面 `true` 走 `xs_rank_pool`（无掩码 = `xs_rank_market`，是另一个 id）。
5. 禁止用 `xs_rank_pool` 表达「此前 N 日」而不给 `x` 加 `ts_delay`（本算子含当日）。

### 1.7 依赖与可验收状态

| 依赖 | 状态 | 影响 |
| --- | --- | --- |
| 本 id 自身 | **未落地**（`dsl.py:74` 无 `xs_rank*`） | 待系统开发流程排期 |
| E3 `in_universe` | 未落地 | A4 不可验；`xs_rank_pool` 可先实现 + 过 A1/A2/A3/A5/A6/A7/A8，**策略引用必须等 A4** |
| F1 `vol60` | **尚未落地**（截至 2026-11-07 14:33：`dsl.py` 无该因子；`docs/factors/F_CLASS_REGISTRATION_20261107.md` 尚未生成，但 `docs/factors/evidence/f_class_registry.json` 已声明注册意图） | S07/S11/S12 即便有了 `xs_rank_pool` 也无法表达（`annual_vol_20d` 不可替代：低波十分位 jaccard=0.136） |

---

## 2. `xs_rank_market`（全样本分位）— 仅诊断

### 2.1 五字段

| 字段 | 值 |
| --- | --- |
| `semantics` | `market_percentile`：全样本平均名次 ÷ 全样本非空家数 |
| `scope` | **全样本**：当日面板内 `x` 非空的主板 60/00 标的（约 3,077–3,095 只）。写「全市场」是错的——创业板/科创板/北交所从未进入样本 |
| `denominator` | `count(x, over date)`（全样本非空家数） |
| `strategy_usable` | **false** |
| `replaced_by` | `xs_rank_pool`（策略侧需要截面排名一律改用池内口径） |

### 2.2 口径与登记要点

- 签名 `xs_rank_market(x)`：**不接受 mask 参数**（有掩码就应走 `xs_rank_pool`）。
- 数值上**与现存 `rank` 算子等价**（同一公式 `rank("average").over("date") / count().over("date")`）。本条为按公式推断，**未逐位实测**。
- 登记理由不是「多一个算法」，而是把作用域写进 id 并对策略禁用。因此在台账标 `numeric_alias_of = rank`：**它与 `rank` 只计 1 个因子，不得重复计入因子总数**（否则会把 178 虚增 1）。
- 用途：差异证明的对照臂（② 与 ① 的差 = 掩码效应本身）；策略规格**不得**引用。

### 2.3 验收判据

| # | 判据 |
| --- | --- |
| B1 | 与 `rank(x)` 逐位相同（同输入、同日期、同 float64），差 0 |
| B2 | 值域 `(0,1]`，逐日 max = 1（样本非空家数 ≥ 1 时） |
| B3 | 策略侧引用计数 = 0（代码扫描：策略文件/seed/执行器不得出现该 id） |

---

## 3. `xs_rank_pct`（全样本名次 ÷ 池内家数）— 历史与差异证明

### 3.1 五字段

| 字段 | 值 |
| --- | --- |
| `semantics` | **`global_rank_over_pool_count`** |
| `scope` | **混合**：分子全样本、分母池内。分子分母**不是同一批样本**——这是缺陷的形态，不是设计选择 |
| `denominator` | 池内家数（含池内 `x` 为空的行，≈1,429/1,430；等于 `in_universe.sum()`） |
| `strategy_usable` | **false** |
| `replaced_by` | **`xs_rank_pool`** |

### 3.2 口径与登记要点

- 签名 `xs_rank_pct(x, mask)`，`mask` 必填（与 `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md` §3.2 一致）。
- 值域真实上界 = 全样本非空家数 ÷ 池内家数：周末 `3095.35 / 1428.95 ≈ 2.166`，月末 `3076.55 / 1429.74 ≈ 2.152`。**可以 >1**，这是它的定义性缺陷。
- 它与研究侧 `rk_*`（`common.py:190-201`）同构，因此**能复现研究数字**（49.7 / 55.5 / 92.8 / 14.7）。这恰恰是它不能当基准的原因：研究侧本身就是错口径。任何策略结论、任何「研究侧已复现」的说法都不得引用它。
- 保留目的两条：① 差异证明（说明研究实测选股数为何系统性低于 `t×P`）；② 契约 §3.4 R1–R5 的历史复现（仅诊断）。

### 3.3 验收判据（仅历史复现，不作策略验收）

| # | 判据 |
| --- | --- |
| C1 | 逐位复现研究 `rk_*`（S06/S07/S10/S11 逐调仓日 jaccard ≥ 0.99，平均选股数 49.7 / 55.5 / 92.8 / 14.7 ±1） |
| C2 | 必须能产出 `rk > 1` 的样本（若产不出，说明它其实不是 ③，是被悄悄改成了 ①） |
| C3 | 策略侧引用计数 = 0 |

---

## 4. 台账记录（三条注册 + 两条死列）

列口径与 `FACTOR_REGISTRY_CORE_93_20261107.md` §2 一致；`登记状态` 为本次新增列。

| id | 名称 | 类型 | 公式（口径式） | 口径（价基/含当日/shift/窗口） | warmup 声明/实需 | 数据源列 | 空值 | PIT | 登记状态 | strategy_usable | replaced_by |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `xs_rank_pool` | 池内分位截面排名 | virtual（截面算子，带必填 `x`/`mask`） | `rank_average(x over date, 限定 in_universe & x 非空) / count(x, 同一限定)` | 继承 x；含当日=True；shift=无；窗口=0（算子） | max(warmup(x),121) / 同 | x 依赖列 + `in_universe`(st_flag, raw_close, prior_amount_20, volume, observed_bars) | keep | 否 | **待注册**（2026-11-07 决定四生效） | **true** | — |
| `xs_rank_market` | 全样本分位截面排名（诊断） | virtual（截面算子，`x` 一个参数） | `rank_average(x over date) / count(x over date)`；`numeric_alias_of = rank` | 继承 x；含当日=True；shift=无；窗口=0 | max(warmup(x),1) / 同 | x 依赖列 | keep | 否 | **待注册** | false | `xs_rank_pool` |
| `xs_rank_pct` | 全样本名次/池内家数（历史） | virtual（截面算子，`x`/`mask`） | `rank_average(x over date, 全样本非空) / in_universe.sum()` | 继承 x；含当日=True；shift=无；窗口=0 | max(warmup(x),121) / 同 | x 依赖列 + `in_universe` | keep | 否 | **待注册**（只做差异证明） | false | `xs_rank_pool` |

去重口径：`xs_rank_market` 与 `rank` 数值等价，**只计 1 个因子**；`xs_rank_pct` 与 `xs_rank_pool` 分子分母均不同，是两个因子；契约 §3.6 的 `xs_rank_in_pool` 是 `xs_rank_pool` 的旧名，**不得作为独立 id 另行登记**。

### 4.1 两条死列（有计算、无引用 → 不注册）

| id | 位置 | 引用数 | 处置 |
| --- | --- | --- | --- |
| `rk_ret60` | 研究 `common.py:193-194`（`ret60` 的池内排名） | **0**（12 条策略无一处引用；S09 用 `ret60` 原值排序） | **不注册**。若开发侧已登记：标 `strategy_usable = false`，备注「当前无引用（死列）」 |
| `rk_near_high` | 研究 `common.py:193-194`（`dist_52w_high` 的池内排名） | **0**（S08 用 `dist_52w_high` 原值，不用该排名） | **不注册**。若开发侧已登记：标 `strategy_usable = false`，备注「当前无引用（死列）；S08 不依赖」 |

判断依据：`research/strategy-search-20261107/scripts/common.py` 全量 grep，`rk_ret60` / `rk_near_high` 只出现在定义行（193-194），未出现在 `build_signals` 的任何入场/排序/出场表达式里。

### 4.2 试验次数 N

本次登记 **新增试验次数 N = 0**：不新增策略、不新增阈值、不新增组合。5 条策略的口径修正是**重验**，不重置 N，也不因口径修正而把旧 N 作废——旧结论作废（决定四 §7.4 清单），但试验次数是已经发生的搜索成本，必须继续计在分母里。

---

## 5. 策略 id 对照表（口径修正后第一次真正表达「池内 t 分位」）

阈值**一律不变**：`0.05 / 0.10 / 0.30`。这不是「沿用旧参数」，而是这些阈值在正确口径下**第一次**等于「池内最低 t」。借修口径顺手调参 = 新增试验，须另立策略并计入 N。

| 策略 | 入场因子 id（唯一允许） | 阈值（不变） | 排序键 | 调仓 | 其它前置 | 期望选股/调仓日（`t×P`；`P` 按调仓样本分段取池内非空家数均值：`week_end` 样本（S06）**1,428.95**；月末样本（S07/S10/S12）**1,429.74**（S11 同为月末样本、均值同 `1,429.74`：`evidence/xs_rank_stats.json` 的 `S11_both_le_0.30.rebuild_dates = 88`（与 `S07`/`S10` 同日数）、`evidence/xs_rank_family_specs_20261107.json` 的 `strategy_map.S11.rebalance = month_end`；该条只是**未单列** `mean_universe_size` 字段，字段缺失≠值不同，这档均值与 S07/S10 同源同值、不降级标注。`428.92 = 0.30 × 1,429.74` 是单腿期望，交集大小仍只报实测）；两者是不同调仓样本的均值，不是矛盾，不可互相替代、不可统一成一个数，逐日实测 `P` = 1,210 / 1,037 / 1,790（2021-06-30 / 2024-06-28 / 2026-09-30），偏离均值约 ±25%；该列**仅均值口径、只作量级参考**，**逐日验收一律按 A2 逐日对账、用当日 `P`，不得用均值当判据**） | 旧研究实测（作废，仅差异证明） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **S06** 5 日反转 | `xs_rank_pool(x=momentum_5d, mask=in_universe)` | `≤ 0.05` | `−momentum_5d` 升序 | `week_end` | E3、E4 | `0.05 × 1428.95 = 71.45` | 49.7（实际 3.48%） |
| **S07** 低波 60d | `xs_rank_pool(x=vol60, mask=in_universe)` | `≤ 0.10` | `−vol60` 升序 | `month_end` | E3、E4、**F1 `vol60`** | `0.10 × 1429.74 = 142.97` | 55.5（实际 3.88%） |
| **S10** 20 日反转 | `xs_rank_pool(x=momentum_20d, mask=in_universe)` | `≤ 0.10` | `−momentum_20d` 升序 | `month_end` | E3、E4 | `142.97` | 92.8（实际 6.49%） |
| **S11** 低波+反转 | 两条腿**交集**：`xs_rank_pool(x=vol60, mask=in_universe) ≤ 0.30` **且** `xs_rank_pool(x=momentum_20d, mask=in_universe) ≤ 0.30` | `0.30` / `0.30` | `−(rk_vol60 + rk_ret20)` 升序 | `month_end` | E3、E4、**F1** | 单腿各 `0.30 × 1429.74 = 428.92`；**交集数不可由 `t×P` 推出**（取决于两腿相关性），只报实测 | 14.7（实际 1.03%） |
| **S12** 低波+宽度 | `xs_rank_pool(x=vol60, mask=in_universe) ≤ 0.10` **且** `market_breadth ≥ 0.5` | `0.10` / `0.5` | `−vol60` 升序 | `month_end` | E3、E4、**F1**、E1 | `142.97`（宽度闸门只减月份，不减候选数） | 55.5（同 S07） |

三条附注（写进对照表就算定案）：

1. **S11 保持交集，不许换成「复合排名前 30%」。** 后者是另一条策略（先按 `rk_vol60 + rk_ret20` 排序再取前 30%），语义不同、选股数不同，要另立 id、另计入 N。
2. 排序键里的 `rk_vol60`/`rk_ret20` 现在一律指 `xs_rank_pool(...)` 的输出，**不是** `rank(...)`，也**不是** `xs_rank_pct`。S11 的排序键必须与该策略入场用的同一个因子实例（同 `x`、同 `mask`、同版本）。
3. 系统侧**目前没有任何一条 S06/S07/S10/S11/S12 的策略实现**（`backend/app/strategy/seeds/` 25 个 seed 均不引用截面排名；`grep -rl "rank(" backend/app/strategy/` 只命中 `research/factor_rank_research.py`）。所以这不是「改 5 个策略文件」，而是「5 条策略首次落地时必须用对 id」。一旦落地，把 `rank(...)` 写进 `META.scoring` 属策略变更，需研究侧评审。

### 5.1 口径修正后的方向预判（不是结论，不得引用为结论）

只记录预期形态，避免「修了口径就复活了」的错觉。选股集合的变化必须按三点读，不能读成「放宽一点就接近了」：① **选股数量上升**：旧研究实测 55.5（S07）/ 49.7（S06）/ 92.8（S10）/ 14.7（S11）只，新口径名义 `t×P` 约 143（S07）/ 71（S06）/ 143（S10），S11 交集只报实测；② **新集合不是旧集合的超集**：旧集合 = 「全样本名次 ≤ `t×P`」与池子的交集（2021-06-30 全样本 `vol60` 最低的 121 只里只有 26 只在池内），新集合 = 「池内名次 ≤ `t×P`」，二者交集大小未知——不能读成「正确集合的研究子集」，也不能靠调阈值还原；③ 因此调阈值只改计数、不改排序依据，**不能**把集合恢复成「池内最低 t」。按现有研究数字，S06/S10/S11/S12 全期为负、S07 是唯一 OOS 为正的候选；口径修正只换证据集，不改变「负的仍然可能是负的」。任何方向都等重跑。

---

## 6. 与架构契约的冲突点（需系统架构师按决定四修订；本文只列冲突与依据）

| # | 契约位置 | 契约现文 | 与决定四的冲突 | 应改为 |
| --- | --- | --- | --- | --- |
| C1 | `FACTOR_ENGINE_CONTRACTS_20261107.md` §3.1 末段 | 「先逐位复现…同时把池内分位作为另一个独立因子 id 保留…不授权任何一方切换」 | 决定四已授权：池内分位 = 唯一策略可用口径 | 先做 `xs_rank_pool` + A3 回归保护；`xs_rank_pct` 只做差异证明，后补 |
| C2 | 同上 §3.2 边界表 | 「池内有成员 x 为 null → 该成员 null；**分母仍计入它**」 | 该行只对 `xs_rank_pct` 成立；对 `xs_rank_pool` 这是失败的指纹 | 按 id 分表：`xs_rank_pct` 保留该行，`xs_rank_pool` 改为「不进分母」（A5） |
| C3 | 同上 §3.3-1 | 「**禁止**用『池外置 null + 现有 `rank`』近似（该写法 = 池内分位，非研究口径）」 | 池外置 null 后在同一列上取 rank+count **就是** `xs_rank_pool` 的定义，即权威口径 | 禁止范围收窄为「禁止用该写法冒充 `xs_rank_pct` / 冒充研究口径」 |
| C4 | 同上 §3.6 | 「E2-alt `xs_rank_in_pool`：登记但不实现」 | 决定四：判定即缺陷，应同一批实现 | 废止 `xs_rank_in_pool` 旧名（= `xs_rank_pool` 别名，不得独立登记），实现 `xs_rank_pool` |
| C5 | 同上 §3.4 R1–R5 | 选股数 55.5/49.7/92.8/14.7 ±1、jaccard ≥ 0.99 | 这组判据是「复现研究错口径」，对新口径无效（会把正确实现判成不通过） | R1–R5 移到 `xs_rank_pct` 名下（C1 判据）；`xs_rank_pool` 改用 A1–A8 |

`FACTOR_GAP_SPEC_20261107.md` §3-E2 的两处文字（原 173 行需求句、原 176–183 行「以研究平均选股数为正确基准」的读法）**已由因子工程师按决定四 §7.5 修订（gap spec v1.1，2026-11-07）**：表头改为 `xs_rank_pct` / `xs_rank_market` 诊断值，验收改为契约 §3.4.1 `XS-A1`–`XS-A8`，并补 3 个调仓日的 `P` 实测锚；**口径定义（原 184 行「分母 = 掩码内非空样本数」）保留原文，与本文一致**（现位于该文件第 189 行；v1.2 于其前插入「旧集合 = 全样本名次 ≤ `t×P` 与池子的交集」「调阈值只改计数、不改排序依据」两条，位于第 187–188 行）。

---

## 7. 本文件没做的事 / 未确证

- 没跑回测、没改代码、没注册因子、没提交。
- 本 turn 期间同仓有他人并发改动：`docs/factors/evidence/f_class_registry.json`、`F_CLASS_PARITY_20261107.json`、`evidence/scripts/*`（因子工程师的 F 类台账）、`research/strategy-search-20261107/REPORT.md` 与 `results/registry.json`。**本文与 `evidence/xs_rank_family_specs_20261107.json` 之外的任何文件都未由我写入**；`git status` 内他人改动一并未动。
- **`P` 是否恒等于 `in_universe.sum()` 未证**（池内因子空值时两者会差）。A5 就是这条的验收动作，不是已经验过。
- **`xs_rank_market ≡ rank` 是按公式推断**，未逐位实测（B1 待跑）。
- polars `count()` 忽略 null 属文档口径，本项目未逐位实测；`rank("average")` 不占 null 名次已实测（决定四 §7.1，polars 1.44.1）。
- **tie 跨 `t×P` 边界时** `count(rk ≤ t)` 与 `t×P` 会差（最多为跨界 tie 组大小 −1）；A2 的「容差 0」指两个实现的计数之差，不是与 `t×P` 之差。
- S11 交集选股数不可由 `t×P` 推出，只报实测。
- 本文不含收益数字；§5.1 是形态预判，不是结论。

## 8. 复算与证据

```bash
cd C:/work/sourcecode/tick-stock-panel
# ① 三个 id 均未落地（预期输出为空）
grep -n "xs_rank" backend/app/factors/dsl.py
grep -n "CROSS_OPERATORS" backend/app/factors/dsl.py      # dsl.py:74 只有 rank/zscore/winsorize
# ② 现存 rank 的真实公式（分子全样本、分母全样本非空）
sed -n '500,510p' backend/app/factors/dsl.py
# ③ 研究侧错口径原文
sed -n '186,202p' research/strategy-search-20261107/scripts/common.py
# ④ 本文引用的 P / 选股数 / jaccard（机器可读）
cat docs/factors/evidence/xs_rank_stats.json
```

机器可读规格：`docs/factors/evidence/xs_rank_family_specs_20261107.json`（三个 id 的五字段 + 验收判据编号 + 策略对照，供系统架构师定契约、系统开发工程师写验收用例直接消费）。
