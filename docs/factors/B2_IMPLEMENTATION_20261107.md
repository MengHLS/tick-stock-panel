# B2 实现交付：E3 `in_universe` → E2 截面排名族 → E1 `market_breadth`

- 批次：B2（B3 已作废并入本批，未另开）
- 契约依据：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md` §2.6 / §3 / §4.6；XS 口径另依 `docs/factors/XS_RANK_POOL_SPEC_20261107.md`；id 口径依 `docs/architecture/ARCH_DECISION_FACTOR_ID_CANONICAL_20261107.md` §2.1
- 仓库 HEAD：`65c6e42f`
- 证据 JSON：`research/b2-engine-20261107/EVIDENCE_20261107.json`（49 条：**48 PASS / 0 FAIL / 1 INFO**，**66,348 B**，sha256 `d4815e2b9bb17e95d050d7f6ba38c2a19049c67708da69b384d9bc6bb824c00f`）。该 JSON 不含 `generated_at`，dump 用 `sort_keys=True`，实测重建两次 sha 完全相同（`d4815e2b…` ×2，2026-11-07 22:41 连续两次跑 `evidence_build.py`；前一版 `2fe8e83f…` 亦为 ×2 相同、`e986f22a…` 为 ×3 相同），可复算。**本版为 B-1b 第三次收尾（索引补齐 + gate 套件入证）**：① 49,293 B / `020ff5c3…`（20:37 冻结）的 `test_status` 与 `unchanged_on_purpose` 停在测试更新前，作废；② 56,866 B / `580824ea…`（21:50）记的是「catalog=108」时的测试与隔离矩阵，而同批 B4 的日历包（`month_end` / `week_end`）注册即进目录使 catalog 变 110、测试于 22:01:47 再更新一次，故该版也随之作废（同一缺陷 B-1 的第二次发生）；③ 61,248 B / `2fe8e83f…`（22:29）的检出探针记的是「只 add 三个 pack 目录」时的结果（6 failed / 68 passed），索引补齐后该结论已翻转（见 §11），作废但保留为过程证据；④ **现版** = 110 口径 + 索引补齐（16 文件 staged，HEAD 仍 `65c6e42f`）+ 五文件套件在**索引检出**上 74 passed / 0 failed + gate 套件 56 passed，见 §6 / §11
- 路径：**只走 frame 路径**。矩阵路径未动（`materialize_matrix_field` 仍为基类默认 `None`）。
- 未做：未提交、未部署、未重启、未跑收益回测、未向生产因子目录注册任何新因子、未改 `high_60d`/`low_60d`、测试文件本部门**两次**更新过 2 个的**过期计数断言**：20:48:59 按「catalog 93→108」（B0 14 + B2 `in_universe`）、22:01:47 按「catalog 108→110」（B4 的 `month_end`/`week_end`）；两次都只动计数数字与 `GOLDEN_COLUMNS` 追加，`assert ` 条数 45→45 / 20→20，0 删除、无 `skip`/`xfail`/`-k`，仍用确定值 110（未改成 `>=93` 这类无判别力写法），详见 §6 与证据 `test_status`。

---

## 1. 改动文件

| 文件 | 改动 | 关键位置 | bytes | sha256(前12) | 行数 |
|---|---|---|---|---|---|
| `backend/app/factors/dsl.py` | 改 **+108 / −12** | 见 §1.1 | 36,785 | `49f3a1106095` | 850 |
| `backend/app/custom/research_universe_pack/__init__.py` | 新增 | `FACTOR_PROVIDERS` 自动发现入口 | 371 | `b2b210631907` | 7 |
| `backend/app/custom/research_universe_pack/factor_provider.py` | 新增 | `ResearchUniverseProvider`（`provider_id=official.research-universe-pack-e3`, `kind=frame`） | 4,894 | `90dbc6ca46f3` | 128 |
| `backend/app/custom/research_universe_pack/universe.py` | 新增 | `compute_in_universe`(:95) / `UniverseParams`(:41) / `universe_diagnostics`(:229) / `_st_unknown_mask`(:86) | 11,957 | `c45d0bcc26c7` | 268 |

`registry.py` **未改**，故目录原有 93 条的顺序与内容不变；`in_universe` 由 Provider 机制追加在末尾（与 B0 的 14 个同机制）。

### 1.0 本批**没有**改动的 `git status` 条目（避免审核误算）

`git status --porcelain backend/` 除上表 4 项外还列出以下 2 个 **M**，它们是**前批（F-A5 注册幂等）遗留的未提交改动**，不是本批产出，本批一个字节都没碰：

| 文件 | mtime | 归属 | 依据 |
|---|---|---|---|
| `backend/app/factors/store.py` | 2026-11-07 **16:33:52** | 前批 F-A5（`upsert_definition` / `content_signature` / `resolve_status`） | 本批开工时间 18:0x，晚于该 mtime；`dsl.py` 内 `grep 'F-A5\|resolve_status\|content_signature'` 为 0 命中，两条链无交叉 |
| `backend/app/api/factors.py` | 2026-11-07 **16:33:57** | 前批 F-A5（`POST /custom`、`/composite` 接线） | 同上 |

另 `backend/scripts/build_referenced_factor_inventory.py`（**??** 未跟踪）属 17:xx 的清单批次，亦非本批。

**本批真实改动面 = 4 项**：`dsl.py`（+108/−12，`git diff --numstat` 实测）与 `research_universe_pack/` 3 个新文件。矩阵路径（`backend/app/backtest/matrix.py`）、`high_60d`/`low_60d` 相关文件在 `git status` 中**无条目**。

**22:39 索引补齐（§11 批次 E）把上述 `M` 条目与 gate 一并 `git add`，只动索引、文件内容未动**；`store.py` / `api/factors.py` 仍是前批 F-A5 的改动，本批没有改它们一个字节。

### 1.1 `dsl.py` 逐处（`git diff -U0` hunk 头，行号为**新文件**）

| 位置 | 内容 |
|---|---|
| `:4-8` | 模块 docstring：`E001-E017` 与 E017 语义 |
| `:65-68` | `OPERATORS` 增 `xs_rank_pool(2)` / `xs_rank_market(1)` / `xs_rank_pct(2)` / `xs_mean(2)` |
| `:86-92` | `XS_OPERATORS` / `XS_ALL_OPERATORS` / `XS_MASK_ARG_INDEX` / `MASK_FACTOR_TAG="mask"` |
| `:382-390` | `_check_call` 内 E017 静态类型检查 |
| `:413-430` | `_is_mask_boolean()`：允许比较/逻辑表达式，或 `tags` 含 `mask` 的已注册因子；未知 id → 不通过（fail-closed） |
| `:562-605` | `_compile_call` 内 4 个截面算子的 Polars 实现 |
| `:704` `:729` `:739` `:774-790` | `compile_formula` 的依赖 / 预热 / `cross_sectional` 推导纳入 `XS_ALL_OPERATORS` 与掩码依赖 |

**为什么 `in_universe` 是 Provider 而不是纯 DSL 因子**：它需要 `st_history` 这个外部有状态数据集做 as-of 合并，DSL 只能表达逐行表达式、拿不到 `data_dir`。Provider 是既有扩展点（`FactorProviderContext.data_dir`）。

---

## 2. E3 `in_universe`（契约 §2.6）

### 2.1 口径实现

| 输入 | 实现 | 依据 |
|---|---|---|
| 停牌 | **当日无 bar 行**（不是 `volume=0`；全库 `volume=0` 实测 0 行） | 契约 §2.6 |
| 涨跌停 | `price_limits` + `compute_limit_signals` 现算，不读不存在的 `limit_up_price` 列 | 同上 |
| 上市天数 | `observed_bars = date.cum_count().over("symbol")` | **见 §7 D-B2-1** |
| 当日 ST | `st_history` 按 `(symbol, date)` as-of 合并；`st_flag` 缺失 → **null**（不是 False） | 契约 §2.5-3 |
| ST 不可判窗 | `st_unknown_windows` 强制 `2026-10-20`…`2026-11-06` 共 **14 个交易日**一律 null | 契约 §2.6 |
| 退市 | **不建字段**；用「无 bar 行 + `bar_present=False`」表达，`universe_unknown` 记不可判 | 契约 §2.6（不可得） |
| 覆盖期末端 | 覆盖期后（`2026-10-30` 之后）不外推 | 契约 §2.6 A8 |

值域 `{1.0, 0.0, null}`（Float64），`direction="none"`，`tags` 含 `mask`（E017 静态判定依据），`warmup_bars=120`。

**实现踩过的一个坑（已修，留档）**：`st_history` 的 as-of 合并最初用 `join_asof`，但左侧帧按 `(symbol, date)` 排序而 `join_asof` 要求左侧按**全局 `date`** 升序，导致 ST 合并大面积失效（248 天全 null）。修正左侧排序后逐日差归零。

### 2.2 判据（A1–A8 全 PASS）

| 判据 | 观测量 | 结论 |
|---|---|---|
| **E3-A1** 逐日池内家数 vs 研究侧 | 比对 **1,770** 天；`max_abs_diff=0`、`mean_abs_diff=0.0`、差异天数 **0**；两侧覆盖日均值 `1428.162147` 完全相同 | PASS |
| E3-A2 池内无空值 | 池内 2,527,847 行（3,271 只），`raw_close` 空 **0**、`volume` 空 **0** | PASS |
| E3-A3 池内家数 vs 非空家数可比对 | 池内均 `1420.937043` | PASS |
| **E3-A4** 空值可解释（§2.6 A4） | 2,141 天逐日守恒 `bars == in_pool + not_in_pool + unknown`，违例 **0**；有未知值的 **253** 天**全部**有非空原因码、无未知值的 1,888 天原因码全 null（两个方向违例均 0）；原因码恰为 `st_unknown_window`(8) / `beyond_coverage`(6) / `st_missing`(239) 三码且**无死码**；`st_missing` 样例日 2018-01-08 的 2,422 只未知标的在 `st_history` 中**均无当日记录**（缺列 = `st_flag`） | PASS |
| E3-A5 参数未被写死 | 改 `min_observed_bars` → 池内均 `1420.937` → **`1274.922`** | PASS |
| E3-A6 尾部截断回放（PIT） | 4,028,810 行，`mismatch=0` | PASS |
| **E3-A7** ST 不可判日必须 null | 不可判窗 253 天全 null；**2026-10-20…11-06 恰 14 天**，全 null 且 `unknown == 当日 bar 行数` | PASS |
| E3-A8 覆盖期末端不外推 | 覆盖期后 6 行，非 null **0** | PASS |

`A1_null_days = 9`：`2026-10-20`…`2026-10-30`，全部落在 ST 不可判窗（8 天）+ `beyond_coverage`（1 天，`2026-10-30`），按契约应 null，不计入差异。

---

## 3. E2 截面排名族（契约 §3）

### 3.1 算子与可用性

| 算子 | 定义 | 策略可用 |
|---|---|---|
| `xs_rank_pool(x, mask)` | 池内**平均名次** ÷ 池内**非空**家数 | ✅ 唯一 `strategy_usable=true` |
| `xs_rank_market(x)` | 全样本平均名次 ÷ 全样本非空家数 | ❌ 仅诊断 |
| `xs_rank_pct(x, mask)` | 全样本名次 ÷ **池内**家数 | ❌ 仅历史差异证明（可 >1） |
| `xs_mean(x, mask)` | 池内均值，**池外行同值广播**；池内无有效样本 → null | E1 用 |

新增错误码 **E017**（原表到 E016）：掩码参数不是布尔值 → 结构化错误。

### 3.2 判据（XS-A1–A8、XS-B1–B3 全 PASS）

| 判据 | 观测量 | 结论 |
|---|---|---|
| XS-A1 逐日 `max==1` 且 `min>0` | 1,770 天；`max≠1` 天 **0**、`min×n≠1` 天 **0**、`max_max_err=0.0`；池外非 null **0** | PASS |
| XS-A2 分母 = 池内**非空**家数 | `pool vs pct` 差异 **2,523,399** 行 / `max_abs_diff=3.368` | PASS |
| **XS-A3** `rank` 无掩码输出逐位不变 | 7 个截面表达式 + 14 个 B0 因子，改动前后 `baseline_before.json == baseline_after.json` | PASS |
| XS-A4 E3 依赖由 Provider 物化 | 已注册 | PASS |
| XS-A5 池内 x 为 null → 该成员 null 且不进分母 | 合成 fixture | PASS |
| XS-A6 空池 → 全 null | 是 | PASS |
| XS-A7 14 日窗口 | `pool` 非 null **0**、`pct` 非 null **0**、`market` 仍非 null **44,570** | PASS |
| XS-A8 并列取平均名次 | `average` | PASS |
| XS-B1 `xs_rank_market` == `rank` | 逐位相同 | PASS |
| XS-B2 `xs_rank_market` 值域 `(0,1]` | 1,779 天 `max≠1` **0** | PASS |
| XS-B3 / XS-C3 策略侧引用计数 | `xs_rank_market` / `xs_rank_pct` 硬面 **0**（144 个文件）；软面 1 处为注释 | PASS |
| XS-C2 `xs_rank_pct` 可 >1 | `max=4.368`，>1 共 1,619,560 行 | PASS |

### 3.3 负样本（证明没把全样本名次当池内名次）

| 负样本 | 断言 | 结果 |
|---|---|---|
| `NEG-3.1-4rows` | 契约 §3.1 四行样例：`pool={0.5,1.0}`、`pct={0.5,1.5}` → 两者不等 | PASS |
| `NEG-pool3of6` | 6 行 3 只入池：`pool` 分母 3 vs `pct` 分母 6 | PASS |
| `NEG-pool1` | 池内仅 1 只时 `pool == pct == 1.0`（**不可区分，如实记录**，不作合格线） | PASS |

> **重要限定**：`XS-A2` 在真实全样本上**不可区分**——池内无空 `vol60`，故「池内非空家数」与「池内成员数」逐位同值（`days_with_pool_member_null=0`）。区分力只由合成 fixture（`XS-A5`、`NEG-pool3of6`）提供。此点写进证据 `XS-A2_note`，**不得把 XS-A2 当合格线**。

---

## 4. E1 `market_breadth`（契约 §4.6）

- 定义：`xs_mean(close > ma60, in_universe)`
- `count(mask & x notnull) == 0` → **null（不是 0）**
- `close == ma60` 计入**分母、不计入分子**（严格 `>`）
- `warmup = 120`（`in_universe` 与 `ma60` 的最大值），实测 `formula_warmup_bars=120`

### 4.1 与研究侧逐日比（`research/strategy-search-20261107/scripts/common.py:179-182`）

| 项 | 值 |
|---|---|
| 两侧均非 null 的交易日 | **1,770** |
| `max_abs_diff` | **0.0** |
| `mean_abs_diff` | **0.0** |
| 超 1e-12 天数 | **0** |
| 子集均值（两侧） | 均 `0.5422520639953171` |

`ma60` 前置核对：`n_both=5,470,011`、`max_abs_diff=0.0`、null 错配 **0**。

### 4.2 null 日清单（9 天，单列原因）

| 日期 | 原因 | 研究侧值 |
|---|---|---|
| 2026-10-20 ~ 2026-10-29（8 天） | `st_unknown_window` | 0.3033 / 0.2995 / 0.2165 / 0.2457 / 0.2604 / 0.2181 / 0.2490 / 0.2163 |
| 2026-10-30 | `beyond_coverage` | 0.1846 |

研究侧这些日有值、产品侧按契约给 null——差异来自契约强制的不可判窗口，不是实现偏差。

### 4.3 B2–B6

| 判据 | 观测量 | 结论 |
|---|---|---|
| B2 月末通过率 | 88 个月末中 87 可比 → 通过 **47**，`0.5402298850574713`（靶值复现；旧分母口径 `0.5340909091`） | PASS |
| B3 当日所有行同值 | 池外广播 **1,770** 天，跨行离散 **0** | PASS |
| B4 空池 → null 不是 0 | `[null, null]` | PASS |
| B5 确定性 | 两跑哈希均 `820a0929…` | PASS |
| B6 `warmup == 120` | 是 | PASS |

> `0.5407417` 是**诊断参照**（研究侧全样本均值），不是靶值。

---

## 5. 接线验证（W-A…W-I，走生产入口）

用 `materialize_factor_columns(frame, {"in_universe"})`，不直调 `compute_in_universe`：

| 判据 | 观测量 | 结论 |
|---|---|---|
| W-A | Float64；非 null 值域 `{0.0, 1.0}`；646,943 行中 null 44,654 | PASS |
| W-B | 生产入口 vs 直调同帧 sha256 相同（`94866b8e…`） | PASS |
| W-C | 无 `st_history` → `ValueError`（**fail-closed，不静默当非 ST**） | PASS |
| W-D | 已物化帧重复调用幂等 | PASS |
| W-E | DSL 端到端 `xs_rank_pool(close, in_universe)` 池内 `(0,1]`，与手工逐位同 | PASS |
| W-E2 | 池外行 **null**（不是 0） | PASS |
| W-F | `tags` 含 `mask` | PASS |
| W-G | E017 负样本：`xs_rank_pool(close, volume)` 被拒 | PASS |
| W-H | 14 日窗经生产入口同样全 null | PASS |
| W-I | E009 对四个新键生效：`ts_mean(<xs…>)` 全部 `E009`（`xs_rank_pool` / `xs_rank_market` / `xs_rank_pct` / `xs_mean`），对照 `rank` / `zscore` 同为 `E009` 不变；且 `xs_rank_pool(close, in_universe)`、`xs_mean(close, in_universe)` 编译通过（掩码标签被接受） | PASS |

> W-I 是补 v0.8 §10.2「未确证③」（`E009` 对四新键只读了代码分支、未构造嵌入用例实跑）：8 个用例全部实跑，期望码与实际码逐条相等。v0.8 §10.2「未确证②」（`xs_rank_market` 是否真等价 `rank`）由 XS-B1 逐位比对已覆盖。

---

## 6. 既有测试红灯的归因（T-A / T-B，实测隔离矩阵）

把两个 pack 目录 `mv` 出 `app/custom` 后重跑同一组 pytest。**下表是 22:04 用「已按 110 口径更新的现盘测试」重测的四态结果**（`logs/isolation_recheck_110.json`，`measured_at 2026-11-07T22:04:54+08:00`，试验后四态均已还原、`restored=true`）：

| 状态 | 目录条数 | 矩阵不可物化 | factor 套件 | 矩阵目录测试 |
|---|---|---|---|---|
| `none`（无任何 pack） | 93 | 14 | **6 failed / 68 passed** | **PASSED**（30 passed） |
| `calendar_only`（仅 B4 日历包） | 95 | 16 | **6 failed / 68 passed**（**同一 6 条**） | — |
| `b0_only`（仅 B0） | 109 | 24 | **6 failed / 68 passed**（**同一 6 条**） | FAILED — `unsupported matrix feature: prior_amount_20` |
| `all_on`（B0+B2+B4，现状） | 110 | 25 | **74 passed / 0 failed** | FAILED — `in_universe 缺少必需列: ['raw_close']` |

> **口径提醒（本节 20:37 那版曾把这张表写反）**：旧表「`none` 全绿 / `all_on` 6 红」是**测试还押 93 的时候**测的。测试按新事实更新断言后方向反过来：**押 110 的测试只在 `all_on`(110) 绿**，`none`(93) / `calendar_only`(95) / `b0_only`(109) 三态都红，且红的永远是同一 6 条（test id 逐字相同，见证据 `isolation.same_red_set_in_three_red_states`）。别把这张表当回归看 —— 它是「断言里的数与目录条数是否相符」的指示器，不是代码质量指示器。

**结论：本批对既有红灯零新增。**

- 6 条 factor 红灯全部是「目录条数硬编码」类断言（`test_factor_registry` 5 条 + `test_factor_store` 1 条）。**红/绿只由目录条数决定，与哪个 pack 在场无关**，也没有任何一条失败来自 B2 的实现代码：`none`(93) / `calendar_only`(95) / `b0_only`(109) 各 6 红（同一 6 条），`all_on`(110) 0 红。
- 因此**pack 目录必须进版本库**：不进库的干净检出 = 93，而断言是 110，这 6 条会一直红。本批据此把三个 pack 目录（`research_factor_pack/`、`research_universe_pack/`、`research_calendar_pack/`，共 9 个文件）`git add`（只 add，不 commit、不 push；HEAD 仍 `65c6e42f`），`git status --porcelain` 前后对比见 §11。第 3 个目录是第 3 件 B4 的产物：只 add 前两个则干净检出 = 108，而断言 110，同样 6 红。
- 矩阵目录测试在 `none` 状态**全绿**，`b0_only` 即红 → **B0 引入**。B2 让首个失败点从 `prior_amount_20` 前移到 `in_universe`（前面仍压着 8 个 B0 frame 因子）。
- 归因证据：`logs/isolation_recheck_110.json`（四态 + 失败 test id 逐字 + 目录探针）、`logs/catalog_support_{none,calendar_only,b0_only,all_on}_110.json`、`logs/pytest_after_110_run.json`（现盘 74 passed 的 argv / 起止时刻 / 完整 stdout）。
- 测试**改过两次**（20:48:59 → 108；22:01:47 → 110，均按开发经理裁定「不重定基线、按新事实更新过期断言值」）：只动计数数字与 `GOLDEN_COLUMNS` 追加；`assert ` 条数 `test_factor_registry.py` 45→45、`test_factor_store.py` 20→20，0 删除、无 `skip`/`xfail`/`-k`、未把精确计数改成 `>=93`、仍用确定值 110。现盘 `test_factor_registry.py` 28,187 B / 403 行 / `81e4b1f9…` / `+25−6`；`test_factor_store.py` 6,793 B / 171 行 / `79de1eca…` / `+3−3`（`git diff --numstat` vs HEAD）。明细见证据 `test_status.test_files_changed`。
- 矩阵侧修法属 B0b（补 `materialize_matrix_field`）或由架构裁定排除表；本批未改 `matrix.py`、未接入 B0b。

---

## 7. 需裁定的口径（3 项，已写入证据 JSON `decisions_needed`）

| 编号 | 冲突 | 我的取法 | 若被推翻 |
|---|---|---|---|
| **D-B2-1** | brief 写「上市天数 = `instruments.listing_date` + 交易日轴（**不要** bar 序号）」；契约 v0.7:125 明确 `observed_bars = date.cum_count().over("symbol")`，即面板内 bar 行数，并写明「不是上市自然日」 | 按**契约与因子研究员定义**实现（`cum_count`），E3-A1 与研究侧逐日 **0 差** | 改输入后需重跑 E3/E1/E2 全部判据；差异已量化：**40,717 标的日**不同（评估窗内 **17,499**），全部是「listing ≥120 而 bar <120」 |
| D-B2-2 | `in_universe` 是否该进 `/api/factors` 对外目录 | Provider 注册即进目录（扩展点既定行为，B0 的 14 个同理），故 107→108；B4 日历包落地后 110 | 若要它不进目录，需改扩展点语义（会影响 B0 与 B4 的日历列） |
| D-B2-3 | `xs_rank_pct` 的登记形态 | 已实现为诊断形态；`strategy_usable=false` / `replaced_by` 属台账口径，`registry` 无该字段 | 是否入台账、以何种 status 登记由因子工程师定；本批不进验收 |

---

## 8. canonical id 核对（REFS-CANON）

E1 formula 实际引用 `in_universe` + `ma60`：

- `in_universe`：本批新增的单 id，已在注册表。
- `ma60`：属「**只有 pack 一侧**」的 6 个之一（裁定 §2.1 双 id 表里没有 `uf_ma60`），**已标注 `pack_only=true`**。
- 8 组双 id 口径（`vol60`/`ma120`/`ma200`/`prior_high_20`/`prior_high_55`/`prior_high_250`/`prior_low_10`/`prior_vol_20`）本批**一个都没引**，故无 alias 违规。
- E3 的 `dependencies` 是面板列名（`amount`/`date`/`raw_close`/`symbol`/`volume`），不参与 id 判定；`in_universe` 内部按 `amount.shift(1).rolling_mean(20)` 现算 `prior_amount20`，不引用因子 id。

证据：`logs/id_canonical_20261107.json`。

---

## 9. 复现命令

```bash
cd C:/work/sourcecode/tick-stock-panel

# E3 (契约 §2.6 A1-A3/A5-A8)
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/b2-engine-20261107/verify_e3.py

# E3 A4 空值可解释 (逐日守恒 + 归因完备 + 原因码无死码 + 可追到标的)
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/b2-engine-20261107/verify_e3_a4.py

# E2 fixtures (XS-A5/A6/A8 + 3 条负样本 + E017)
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/b2-engine-20261107/verify_e2_fixtures.py

# E2 全样本 (XS-A1/A2/A7, XS-B1/B2/B3, XS-C2)
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/b2-engine-20261107/verify_e2_full.py

# E1 (B1-B6, 对照研究侧 common.py:179-182)
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/b2-engine-20261107/verify_e1.py

# 14 日窗口 (W1-W4)
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/b2-engine-20261107/verify_window.py

# 生产入口接线 (W-A..W-I)
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/b2-engine-20261107/verify_wiring.py

# 旧口径回归 (rank 无掩码逐位不变)
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/b2-engine-20261107/baseline_hashes_after.py

# canonical id 核对
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/b2-engine-20261107/verify_id_canonical.py

# 目录/矩阵能力隔离探针 (PROBE_TAG=none|b0_only|all_on)
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/b2-engine-20261107/probe_catalog_support.py

# 汇总证据
PYTHONUTF8=1 python research/b2-engine-20261107/evidence_build.py
```

---

## 10. 未做项（明确边界）

1. **矩阵路径 `in_universe`**（`materialize_matrix_field`）——契约 §7.13/§7.14 归 **B0b**，等 v0.7 落盘后按 `F-A11a`–`d` 做。本批刻意保持基类 `None`。
2. 矩阵路径 `xs_*`——本批只做 frame。
3. `E4`（`month_end` / `week_end` 轴）**不在 B2 范围**：已由同批第 3 件 B4 另行实现并交付，见 `docs/factors/E4_CALENDAR_20261107.md`（只走 frame 路径；矩阵路径同本批归 B0b）。
4. 未注册任何新因子到生产目录；未跑收益回测；未提交、未部署、未重启。
5. 6 条计数断言已两次按新事实更新（93→108→110），现盘 74 passed / 0 failed；矩阵目录测试仍红——**既有**（见 §6），需裁定：由 B0b 补矩阵能力，或由架构出排除表。
6. `high_60d` / `low_60d` 未动（`git status backend/app/backtest/ backend/app/strategy/` 为空）。

---

## 11. 可交付性：索引补齐 + 索引检出探针（只 add，不 commit）

**目的**：干净检出的 tests 押目录条数，而目录条数由 pack 是否在树里决定；把该进索引的文件全部放进索引后，按索引内容检出的树就能直接跑绿。

### 11.1 索引进度（五个 add 批次，均为 `git add`，无 commit/push）

| 批次 | 时刻 | 动作 | `--porcelain` 前 | `--porcelain` 后 |
|---|---|---|---|---|
| A | 21:52:57→21:53 | `git add` `research_factor_pack/` `research_universe_pack/` | 两目录各 1 行 `?? …/` | 6 行 `A  …/<file>.py` |
| B | 22:12→22:12 | `git add` `research_calendar_pack/`（B4 产物） | 1 行 `?? …/` | 3 行 `A  …/<file>.py` |
| C | 22:25:42→22:25:43 | 三目录 `restore --staged` 后重 add（复核重做） | 3 行 `?? …/`（三包全未跟踪） | 9 行 `A  …/<file>.py` |
| D | 22:28:50 | 检出探针（索引只有三包） | 索引 = 110 条 pack + tests 押 93 | **6 failed / 68 passed** — 见 §11.3 |
| **E** | **22:39:5x** | **`git add` 补齐本批 7 个文件** | `M backend/app/factors/dsl.py`、`M backend/app/factors/store.py`、`M backend/app/api/factors.py`、`M backend/tests/test_factor_registry.py`、`M backend/tests/test_factor_store.py`、`?? backend/app/factors/gate.py`、`?? backend/tests/test_factor_gate.py` | 7 行全部变 `M `/`A `（`??` 归零），索引 16 文件 |

批次 E 补齐的 7 个文件（正是 D 探针 6 红的根因链条）：`backend/app/factors/dsl.py`（`M`）、`backend/app/factors/store.py`（`M`）、`backend/app/api/factors.py`（`M`）、`backend/tests/test_factor_registry.py`（`M`）、`backend/tests/test_factor_store.py`（`M`）、`backend/app/factors/gate.py`（`A`）、`backend/tests/test_factor_gate.py`（`A`）。

**当前索引**：`git diff --cached --shortstat` = **16 files changed, 2353 insertions(+), 40 deletions(-)**；`git diff --cached --name-status` 16 行；**HEAD 仍 `65c6e42f`**、`git log --oneline -1` 未变、**未 commit、未 push**。`docs/` 整目录保持未跟踪（本次未 add 任何 docs 文件）。他人未提交改动（`M research/strategy-search-20261107/**` 5 个文件）**未被 add、内容未动**。

### 11.2 检出探针（22:39，补齐索引后跑的这一次）

方法：`git checkout-index -a --prefix=<临时空目录>` 把**索引内容**导出成一棵干净的树（等价于按索引检出），在导出树的 `backend/` 下用**同一个** `backend/.venv` 跑 pytest。脚本 `research/b2-engine-20261107/probe_index_checkout_110.py`，产物 `logs/index_checkout_probe_110.json`（4,821 B / `fa603d00…`）+ `logs/index_checkout_probe_110.txt`（2,600 B / `a24cecbf…`）。

| 套件 | 结果 | 判定 |
|---|---|---|
| 五文件（dsl / registry / api / store / provider_contracts） | **74 passed / 0 failed** / 1 warning in 8.09s | **0 红** |
| gate（`tests/test_factor_gate.py`，索引内容原样） | **52 passed / 4 failed** / 1 warning in 3.94s | 4 红，根因见下 |
| gate（只把那份 inventory 产物 cp 进导出树，索引未改动） | **56 passed** / 1 warning in 2.54s | 证明 4 红唯一原因是该产物缺席 |

gate 那 4 条红的 test id（逐字）：

- `tests/test_factor_gate.py::test_live_config_allowlist_shape_matches_the_artifact`
- `tests/test_factor_gate.py::test_live_config_allowlist_reads_only_the_inventory_json`
- `tests/test_factor_gate.py::test_live_config_allowlist_fails_closed_on_summary_mismatch`
- `tests/test_factor_gate.py::test_live_config_ids_are_all_known_and_never_blocked_as_columns`

根因：这 4 条只读 `docs/architecture/evidence/referenced_factor_inventory.json`（allowlist 的唯一读取面），而 `docs/` 整目录当时未跟踪（`?? docs/architecture/`），导出树里没有这份产物 → `FileNotFoundError`。索引里的 `gate.py` 与 `test_factor_gate.py` 本身没问题。按派工「`docs/` 不动」，本批**未**把这份产物纳入索引；要 gate 在干净检出上也全绿，需 add `docs/architecture/evidence/referenced_factor_inventory.json`（186,343 B）+ 其 `.sha256` 两行，**裁定权在开发经理**。

### 11.3 历史：22:28 那次探针（已翻转，保留为过程证据）

批次 D 那次只 add 了三个 pack 目录，`tests/` 与 `dsl.py` 仍是未 staged 的 `M`，索引里 pack 已 110 条而 tests 押 93 → `assert len(factor_columns_view()) == 93` / `AssertionError: assert 110 == 93`（`test_factor_store.py:88`），**6 failed / 68 passed**（`logs/clean_checkout_probe_110.txt`，1,543 B / `332603e2…`）。该结论「只 add 不 commit 不足以 0 红」在批次 E 补齐索引后**已不成立**，只作过程证据。

### 11.4 结论

1. **五文件套件在索引检出上 0 红**：74 passed / 0 failed（实际条数）。
2. **gate 在索引检出上 52 passed / 4 failed**，4 红全部由未跟踪的证据产物缺席引起；补该两行文件即 56 passed（已实测）。
3. **未 commit、未 push，HEAD 仍 `65c6e42f`**；`matrix.py`、alias/`FS03`、`rsi_14_pct`、B6、B0b 均未触碰；`gate.py` 未接线（`assert_factors_usable(` 生产调用点 0）。
