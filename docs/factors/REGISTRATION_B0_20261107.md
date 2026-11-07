# 批 B0 因子注册交付 — 14 个研究基线因子

- 交付人：系统开发工程师（唯一实现者）
- 日期：2026-11-07
- 依据：`docs/factors/FACTOR_ENTRY_RULE_20261107.md` §4.1（批 A1，9 个）+ §4.2（批 A2，5 个）；
  注册字段规则 `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md` §7
- 证据：`docs/factors/evidence/registration_b0_20261107.json`（21,959 B，由 `verify_b0.py` 生成）
- 日志：`research/factor-registration-20261107/logs/verify_b0.log`、`logs/demo_refs.log`

## 0. 结论

**14/14 注册完成，可被 DSL 直接引用；数值保真只在 pack 侧逐位（`max_abs_diff = 0`）；canonical `uf_vol60` 侧与 pack 差 1 ULP（1.11e-16，落在 §7.6 `F-A3` 的 `<1e-12` 内），全帧 77.06% 行不等（4,214,876 / 5,469,335，超 `1e-12` 行 0），不得写成「逐位相同」。既有 178 个因子与内核零改动。**

| 判据 | 结果 |
| --- | --- |
| `compile_formula("<id> > 0").ok` | 14/14 True |
| 保真 `max_abs_diff` | 14/14 严格等于 `0.0`（原 `vol60` 为 1.11e-16，已按研究代码口径修正，见 §4.1） |
| 平台缺值（参考有值/平台 null） | 14/14 = 0 |
| 平台多值（参考 null/平台有值） | 14/14 = 0 |
| `n > 5.4e6` | 12/14 满足；`ma200`、`prior_high_250` 因 warmup 199/250 根，窗口内可达上界只有 5.371e6 / 5.333e6（见 §4.2） |
| 幂等（连注两次） | 通过：总因子数 192 → 192，14 个 id 版本均为 1，无重复 id，无异常 |
| 既有因子 | 178 个全部 `version=1` 未变（因子注册表重复 id 会抛错，注册未抛错即未覆盖） |
| 内核 | `git status --porcelain -- backend` 只有 `?? backend/app/custom/research_factor_pack/` |

## 1. 注册路径：为什么走 Provider，不走 `POST /api/factors/custom`

走的是既有扩展点 **`app/extensions/factors.py` 的 FactorProvider 自动发现**（扫描 `app/custom/*/factor_provider.py`），
新增包 `backend/app/custom/research_factor_pack/`（3 个文件，全部新增）。

理由（两条都实测过）：

1. `app/factors/store.py#CUSTOM_ID_PATTERN` 把自定义因子 id 限定为 `uf_*` / `cf_*`。研究侧策略表达式引用的是
   `ma20`、`prior_high_55` 这类**原名**（§2.1 R1 引用闭合），改名成 `uf_ma20` 会让策略提交物与研究规格对不上。
2. Provider 入口允许任意 id + 元数据，且是现成的（`ensure_factor_providers()` 由 `app/factors/registry.py:434-437`
   在 `get_factor` / `all_factors` 等访问点上惰性触发，生产路径自动生效），**不需要改 registry / dsl / store 任何一个字**。

计算没有第二套实现：每个因子只持有一条 DSL 公式（`factor_specs.py`），物化时用 `compile_formula_cached(...).frame_transform`
（与 `app/strategy/scoring.py#materialize_scoring_columns` 的 pending 分支同一条路径），因此与因子检验、评分、回测共用同一实现。
`warmup_bars` / `dependencies` 由 DSL 编译结果推导，不手填。

文件：

| 文件 | 作用 |
| --- | --- |
| `backend/app/custom/research_factor_pack/factor_specs.py` | 14 条 `FactorSpec`（id/label/group=研究补充/formula_text/warmup/deps/unit/scale_free/version=1） |
| `backend/app/custom/research_factor_pack/factor_provider.py` | `ResearchFactorPackProvider`（`provider_id=official.research-factor-pack-b0`, `kind=frame`, v1） |
| `backend/app/custom/research_factor_pack/__init__.py` | 包说明 |

## 2. 14 行登记表

| # | id | 已注册 DSL 公式 | 注册路径 | `max_abs_diff` | n（比对行数） | 指标层对照 | 幂等 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `ma20` | `ts_mean(close, 20)` | Provider | **0** | 5,497,082 | `compute_indicators.ma20` → 0 | v1 / 无重复 |
| 2 | `ma60` | `ts_mean(close, 60)` | Provider | **0** | 5,470,011 | `compute_indicators.ma60` → 0 | v1 / 无重复 |
| 3 | `boll_lower` | `ts_mean(close, 20) - 2 * ts_std(close, 20)` | Provider | **0** | 5,497,082 | `boll_lower` → 0 | v1 / 无重复 |
| 4 | `boll_upper` | `ts_mean(close, 20) + 2 * ts_std(close, 20)` | Provider | **0** | 5,497,082 | `boll_upper` → 0 | v1 / 无重复 |
| 5 | `sd20` | `ts_std(close, 20)` | Provider | **0** | 5,497,082 | 参考 `common.sd20`（ddof=1，与 DSL 同） | v1 / 无重复 |
| 6 | `prior_high_20` | `ts_delay(ts_max(high, 20), 1)` | Provider | **0** | 5,496,401 | 参考 `prior_high20` | v1 / 无重复 |
| 7 | `prior_low_10` | `ts_delay(ts_min(low, 10), 1)` | Provider | **0** | 5,503,218 | 参考 `prior_low10` | v1 / 无重复 |
| 8 | `prior_high_55` | `ts_delay(ts_max(high, 55), 1)` | Provider | **0** | 5,472,715 | 参考 `prior_high55` | v1 / 无重复 |
| 9 | `prior_vol_20` | `ts_delay(ts_mean(volume, 20), 1)` | Provider | **0** | 5,496,401 | 参考 `prior_vol20` | v1 / 无重复 |
| 10 | `ma120` | `ts_mean(close, 120)` | Provider | **0** | 5,428,988 | 参考 `ma120` | v1 / 无重复 |
| 11 | `vol60` | `ts_std((close - ts_delay(close, 1)) / ts_delay(close, 1), 60)` | Provider | **0** | 5,469,335 | 参考 `vol60`（日频未年化） | v1 / 无重复 |
| 12 | `prior_high_250` | `ts_delay(ts_max(high, 250), 1)` | Provider | **0** | 5,332,523 | 参考 `prior_high250` | v1 / 无重复 |
| 13 | `prior_amount_20` | `ts_delay(ts_mean(amount, 20), 1)` | Provider | **0** | 5,496,401 | 参考 `prior_amount20` | v1 / 无重复 |
| 14 | `ma200` | `ts_mean(close, 200)` | Provider | **0** | 5,371,122 | 参考 `ma200` | v1 / 无重复 |

`prior_*` 一律带 `ts_delay(...,1)`：语义 = 此前 N 根、不含当日（契约 §7.1 坑 1），标 v1「复现口径」，等研究侧 D1 定稿。
`boll_*` 写成 `ma20 ± 2*sd20` 的展开式而不是引用 `ma20`/`sd20` 两个因子 id：DSL 对缺列 fail-closed，展开后只依赖基础列 `close`，
物化时不依赖别的因子列（数值与研究 `bb_lower = ma20 - 2*sd20` 逐位一致，已由指标层对照证明）。

## 3. 验收：命令与输出

### 3.1 主验收脚本（判据 1/2/3/4/5 一次跑完）

```
cd C:\work\sourcecode\tick-stock-panel
backend\.venv\Scripts\python.exe research\factor-registration-20261107\verify_b0.py
```

输出（完整见 `research/factor-registration-20261107/logs/verify_b0.log`；全样本 6,422,875 行 / 3,384 只 / 12 分块，21.0s）：

```
[config] data_dir=D:\TSP\data
[step1] compile_ok 14/14
[step5] idempotent=True error=None
[data] rows=6422875 symbols=3384 (12.9s)
[chunk 1/12] rows=596989 eval=504006 (13.6s)
[chunk 2/12] rows=465473 eval=407798 (14.1s)
[chunk 3/12] rows=618512 eval=519840 (15.1s)
[chunk 4/12] rows=606993 eval=510787 (16.1s)
[chunk 5/12] rows=619219 eval=521726 (16.7s)
[chunk 6/12] rows=551645 eval=487163 (17.3s)
[chunk 7/12] rows=607915 eval=511380 (17.9s)
[chunk 8/12] rows=588891 eval=499119 (18.9s)
[chunk 9/12] rows=578843 eval=496899 (19.5s)
[chunk 10/12] rows=477243 eval=419469 (20.2s)
[chunk 11/12] rows=593919 eval=514581 (20.8s)
[chunk 12/12] rows=117233 eval=117233 (21.0s)

== step1 compile ==
14/14 ids compile OK

== fidelity ==
id                   max_abs_diff            n  ref!null&plat_null   ind.max_abs_diff
ma20                            0      5497082                   0                  0
ma60                            0      5470011                   0                  0
boll_lower                      0      5497082                   0                  0
boll_upper                      0      5497082                   0                  0
sd20                            0      5497082                   0                nan
prior_high_20                   0      5496401                   0                nan
prior_low_10                    0      5503218                   0                nan
prior_high_55                   0      5472715                   0                nan
prior_vol_20                    0      5496401                   0                nan
ma120                           0      5428988                   0                nan
vol60                           0      5469335                   0                nan
prior_high_250                  0      5332523                   0                nan
prior_amount_20                 0      5496401                   0                nan
ma200                           0      5371122                   0                nan

== jaccard vs high_60d ==
prior_high_20_vs_high_60d: jaccard=0.0 both_true=0 union=271006
prior_high_55_vs_high_60d: jaccard=0.0 both_true=0 union=143747
prior_high_250_vs_high_60d: jaccard=0.0 both_true=0 union=59432

== value identity vs high_60d (逐位相等) ==
prior_high_20_vs_high_60d: n_both=5470011 n_exact_equal=122162 share=0.02233304466846593
prior_high_55_vs_high_60d: n_both=5470011 n_exact_equal=216858 share=0.039644892853049105
prior_high_250_vs_high_60d: n_both=5332523 n_exact_equal=80366 share=0.015070914837123065

== reachable rows / 判据 ==
id                          n  n_reachable  diff0  no_miss  no_extra  n>5.4e6
ma20                  5497082      5510001   True     True      True     True
ma60                  5470011      5510001   True     True      True     True
boll_lower            5497082      5510001   True     True      True     True
boll_upper            5497082      5510001   True     True      True     True
sd20                  5497082      5510001   True     True      True     True
prior_high_20         5496401      5510001   True     True      True     True
prior_low_10          5503218      5510001   True     True      True     True
prior_high_55         5472715      5510001   True     True      True     True
prior_vol_20          5496401      5510001   True     True      True     True
ma120                 5428988      5510001   True     True      True     True
vol60                 5469335      5510001   True     True      True     True
prior_high_250        5332523      5510001   True     True      True    False
prior_amount_20       5496401      5510001   True     True      True     True
ma200                 5371122      5510001   True     True      True    False

== warmup ==
ma20               first_valid=  19 expected=  19 match=True prev_null=True warmup=21 ok=True
ma60               first_valid=  59 expected=  59 match=True prev_null=True warmup=61 ok=True
boll_lower         first_valid=  19 expected=  19 match=True prev_null=True warmup=21 ok=True
boll_upper         first_valid=  19 expected=  19 match=True prev_null=True warmup=21 ok=True
sd20               first_valid=  19 expected=  19 match=True prev_null=True warmup=21 ok=True
prior_high_20      first_valid=  20 expected=  20 match=True prev_null=True warmup=21 ok=True
prior_low_10       first_valid=  10 expected=  10 match=True prev_null=True warmup=11 ok=True
prior_high_55      first_valid=  55 expected=  55 match=True prev_null=True warmup=56 ok=True
prior_vol_20       first_valid=  20 expected=  20 match=True prev_null=True warmup=21 ok=True
ma120              first_valid= 119 expected= 119 match=True prev_null=True warmup=121 ok=True
vol60              first_valid=  60 expected=  60 match=True prev_null=True warmup=61 ok=True
prior_high_250     first_valid= 250 expected= 250 match=True prev_null=True warmup=251 ok=True
prior_amount_20    first_valid=  20 expected=  20 match=True prev_null=True warmup=21 ok=True
ma200              first_valid= 199 expected= 199 match=True prev_null=True warmup=201 ok=True

== warmup manual ==
ma20               manual=10.480084390333293 platform=10.480084390333293 diff=0.0
prior_high_55      manual=11.32152917252099 platform=11.32152917252099 diff=0.0
vol60              manual=0.023779152622008966 platform=0.02377915262200897 diff=3.469446951953614e-18

[step5] idempotent=True total_factors=192 duplicates={1}

[evidence] C:\work\sourcecode\tick-stock-panel\docs\factors\evidence\registration_b0_20261107.json (21959 B)
```

判据逐条对应：

1. **可引用**：`[step1] compile_ok 14/14`（每个 id 走 `compile_formula(f"{id} > 0")`，同时 `get_factor(id)` 非空）。
2. **数值保真**：14 行 `max_abs_diff` 全为 `0`，`ref!null&plat_null` 全为 0（无平台漏算），
   参考列 = 研究 `common.add_indicators()`（`research/strategy-search-20261107/scripts/common.py:121-158`）同名列；
   `ma20/ma60/boll_lower/boll_upper` 另与正式指标层 `compute_indicators` 同名列对照，`ind.max_abs_diff` 亦为 0；
   窗口 2019-07-01～2026-10-30，逐因子 `n` 见上表（合计 5.510e6 评估行/因子）。
3. **不是改名**：`prior_high_20` / `prior_high_55` / `prior_high_250` 与 `high_60d` 的 jaccard 全为 `0.0`（`< 1` 通过），
   方向校验 `prior_high_55`: `both_true=0`、`union=143,747`，与已知预期一致。
   ⚠️ 该 jaccard 是**单边**的：`high_60d` 含当日 high，而 `high >= close` 恒成立，所以 `close > high_60d` 永不为真、
   `both_true` 必为 0 —— 它只能证明两者取值不同，不能证明"不像"。因此补了一道**值级判重**：
   与 `high_60d` 逐位相等且在评估窗内的行占比分别 2.23% / 3.96% / 1.51%（非 100%），排除别名。
4. **warmup**：14 个 id 首个非空位置 = 理论位置（0-based `N-1`，`prior_*` 为 `N`）、其前一根为 null、
   `warmup_bars ≥ 位置+1`，全 True。另做 3 个手算对照（`ma20` 均值、`prior_high_55` 最大值、`vol60` 的 numpy std），
   平台与手算一致（`vol60` 差 3.47e-18，为 numpy 与 polars 求和顺序差，参考列本身逐位相等，见 §4.1）。
5. **幂等**：`total_factors` 192 → 192，14 个 id `version` 全为 1，重复计数全为 1，`error=None`。

### 3.2 引用闭合演示（研究侧表达式直接可编译）

```
backend\.venv\Scripts\python.exe research\factor-registration-20261107\demo_refs.py
```

```
OK  ma20 > ma60  errors=[] deps=['close'] warmup=61
OK  close < boll_lower  errors=[] deps=['close'] warmup=21
OK  (close > prior_high_55) and (volume > 1.5 * prior_vol_20)  errors=[] deps=['close','high','volume'] warmup=56
OK  close / prior_high_250 - 1 >= -0.03  errors=[] deps=['close','high'] warmup=251
OK  (ma20 > ma60) and (close > ma120)  errors=[] deps=['close'] warmup=121
OK  ts_std((close - ts_delay(close,1)) / ts_delay(close,1), 60) > 0  errors=[] deps=['close'] warmup=61

total: 192   (研究补充 14 + 既有 178)
```

注：DSL 的逻辑运算符是关键字 `and` / `or` / `not`，不是 `&`（用 `&` 报 `E014 语法错误: 无法识别的字符`）。
这不是本次注册引入的限制，写策略表达式时按 `and`。

## 4. 差异登记（需研究侧/契约侧回执，我没有自行改定义）

### 4.1 `vol60`：§4.2 的手写公式与研究代码差 1 ULP — 已按研究代码对齐

| 项 | 内容 |
| --- | --- |
| 研究定义 | `COMMON:126` `ret1 = close.pct_change()`；`COMMON:140` `vol60 = ret1.rolling_std(60)`（日频、未年化） |
| §4.2 文字 | `ts_std(close/ts_delay(close,1)-1,60)` |
| 实测差异 | polars 的 `pct_change()` 实现为 `(x - x.shift(1)) / x.shift(1)`；与文字式的 `x / x.shift(1) - 1` **数学恒等但二进制不等**：`max_abs_diff=1.11e-16`，且差**全部为 1 ULP**。非零差行占比按两个口径分开记：**全帧** n=5,469,335 → **4,214,876 行 = 77.06%**、超 `1e-12` 的行 **0**（`docs/factors/evidence/F_CLASS_PARITY_20261107.json#factor_parity.uf_vol60`）；**60 只标的 / 112,741 可比行**探针 → **77.914%**，分母改 116,287 行则 75.538%（`docs/architecture/B0_ACCEPTANCE_AND_V07_REVIEW_20261107.md` A5④ 表；本轮独立复算逐值相同，`research/b0-correction-20261107/logs/probe_4p6_attribution.json`（脚本同目录 `probe_4p6_attribution.py`））。**旧稿这里的「4.6% 行不等」是错的、已作废**：该数在任一 `vol60` 口径下都复现不出，也**不是**同一探针里 `ret1` 的比例（`ret1` 实测 93.685% = 108,887 / 116,227）——4.6% 与 `vol60`、`ret1` 都无关，是纯粹的错记，不得再引用。 |
| 我的处置 | 注册式写成 `ts_std((close - ts_delay(close,1)) / ts_delay(close,1), 60)`，与研究代码**逐位一致**（`max_abs_diff=0`）。语义相同、非口径变更；**请研究侧把 §4.2 的文字改成减法式**，避免后续实现者再踩这个 1 ULP。 |
| 未做 | 没有改 `common.py`，没有改 §4.2 原文；同一错记 `4.6%` 另见于 `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md` §7.15 A-4、`ARCH_DECISION_FACTOR_ID_CANONICAL_20261107.md:116`、`F_CLASS_PARITY_20261107.md:37`、`FACTOR_ENTRY_RULE_20261107.md:376`（后者还反过来引本文件 §4.1 作依据），这些不是我的文件，本轮未改，已报开发经理。 |

### 4.2 `n > 5.4e6` 门槛对 warmup ≥ 199 根的因子不可达（不是保真问题）

窗口 2019-07-01～2026-10-30 内评估行共 **5,510,001** 行/因子；warmup 会吃掉开头的行：

| 因子 | warmup_bars | 窗口内可达上界 | 实测 n | 差额 |
| --- | --- | --- | --- | --- |
| `ma200` | 201 | 5,371,122 | 5,371,122 | 138,879（= 199 根 × 有效标的） |
| `prior_high_250` | 251 | 5,332,523 | 5,332,523 | 177,478（= 250 根 × 有效标的） |

两者 `n` 已等于可达上界，`max_abs_diff=0`、无漏算无多算——**5.4e6 这条线对它们是算术上不可能的**。
请求把判据改成「`n` = 该 warmup 下的可达上界，且 `max_abs_diff=0`」，或把窗口前推以补足行数。我没有为了凑门槛改窗口。

## 5. 已知限制（不影响本次 done_when，但影响后续策略侧）

1. **矩阵回测路径只覆盖 6/14**。`app/backtest/matrix.py#matrix_feature` 对 `ma20/ma60/ma120/ma200`（`ma<数字>` 分支）与
   `boll_lower/boll_upper`（显式分支）有内置实现；其余 8 个（`sd20`、`prior_high_20`、`prior_low_10`、`prior_high_55`、
   `prior_vol_20`、`vol60`、`prior_high_250`、`prior_amount_20`）走 `materialize_matrix_field`，而 Provider 基类默认返回 `None`，
   因此矩阵路径会抛 `unsupported matrix feature: <id>`。**我没有在矩阵侧补一套 numpy 实现**——那是同一因子的第二套数值实现
   （契约 §7.1 的双实现风险），且矩阵侧是 float32，必然与 frame 侧 0 差异口径冲突，需要架构契约决定（矩阵侧 float32 容差 or 统一走 frame 物化）。
2. **只验证到 frame/DSL 层**：注册、编译、物化、保真、幂等都已实测；未做端到端 API（`GET /api/factors`、`/api/backtest/*`）与前端可见性测试。
3. `rsi_14_pct` 按令未注册（等 D2 定稿）。
4. 未提交、未部署、未跑收益回测、未改门槛。

## 6. 零改动证据

```
git status --porcelain -- backend
?? backend/app/custom/research_factor_pack/
```

（只有新增包，无任何 M/删除。仓库 HEAD `65c6e42f`，开工时 `backend` 下无自己的改动。）

内核文件 sha256（与证据 JSON `kernel_files_sha256` 一致）：

| 文件 | sha256 |
| --- | --- |
| `backend/app/factors/dsl.py` | `3d76ccdc3d5b876e1610d8db8701485252bbf7d20d95b56ab817243f224d54f2` |
| `backend/app/factors/registry.py` | `e8f27b81797184e775261a5f61b94e2c93bd4c1e4cbce52ec6c51d1d4fdbbb78` |
| `backend/app/factors/store.py` | `71306ce897b7a50b9290f4372b6a32a4802d68e606532ed0e1323c691136bfa6` |
| `backend/app/extensions/factors.py` | `fc074fd8a54ef4ae9c9edbc6dd6c468846cf802aacd39b55887b8a58003e7fe5` |
| `backend/app/strategy/scoring.py` | `ab40da595b51138e3b98d75b619a8b22dda36140c00b577ba9d4a41f77e40db6` |

既有 178 个因子：`all_factors()` 共 192，其中 `group != "研究补充"` 的 178 个全部 `version=1`；
`register_factor` 对"重复 id 且版本未提升"是抛 `ValueError` 的（`registry.py:328-334`），本次注册全程未抛错 → 未覆盖任何既有 id。
`high_60d` / `low_60d` 等既有语义未动。

## 7. 文件清单

| 路径 | 状态 |
| --- | --- |
| `backend/app/custom/research_factor_pack/__init__.py` | 新增 |
| `backend/app/custom/research_factor_pack/factor_specs.py` | 新增 |
| `backend/app/custom/research_factor_pack/factor_provider.py` | 新增 |
| `research/factor-registration-20261107/verify_b0.py` | 新增（验收脚本，判据 1–5） |
| `research/factor-registration-20261107/demo_refs.py` | 新增（引用闭合演示） |
| `research/factor-registration-20261107/probe_vol60.py` | 新增（vol60 的 1 ULP 探针） |
| `research/factor-registration-20261107/logs/verify_b0.log` | 新增 |
| `research/factor-registration-20261107/logs/demo_refs.log` | 新增 |
| `docs/factors/evidence/registration_b0_20261107.json` | 新增（证据） |
| `docs/factors/REGISTRATION_B0_20261107.md` | 本文件 |
