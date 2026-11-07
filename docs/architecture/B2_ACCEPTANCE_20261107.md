# B2 独立验收：E3 `in_universe` → E2 截面排名族 → E1 `market_breadth`

- 审核方：独立审核工程师（未参与本批实现、不改代码/契约/测试）
- 时间：2026-11-07 20:42–21:00 Asia/Shanghai
- 契约基准：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md`（§2.6 / §3 / §4.6）

## 1 结论

**六项判据 6/6 通过；但证据包不可复现，不能据此签认。**

| 范围 | 判定 |
|---|---|
| 签认「B2 实现符合契约 v0.7 §2 / §3 / §4.6」 | **PASS** |
| 签认「`EVIDENCE_20261107.json` 的 `test_status` 是本批事实、可复现」 | **FAIL** |

理由：证据的 `unchanged_on_purpose` 第 4 条（0-based `[3]`）写着「`backend/tests/**`（本批未改任何测试）」，而现盘
`backend/tests/test_factor_registry.py` 与 `test_factor_store.py` 的 mtime 是 **20:48:59**，
晚于证据冻结（20:37）与派单（20:42）：基线由 93 改成 108，并向 `GOLDEN_COLUMNS` 追加 15 条。
按证据原命令在现盘复跑得 **74 passed / 0 failed**，不是证据写的 `6 failed / 68 passed`。
详见 §4 的 B-1、B-2。

## 2 绑定与复算

四件绑定对象在我审核开始与结束各复算一次，数值一致（期间未变）：

| 对象 | 声明 | 我复算 | 一致 |
|---|---|---|---|
| 契约 v0.7 | 193,586 B / 1,696 行 / `5a87d4b090d996ab…` / 正文 `head -c 191933` = `73e15ddc…` | 193,586 B / 1,696 行 / `5a87d4b090d996abf28f` / `73e15ddc4d8e4a78` | 是 |
| B2 交付文档 | 18,384 B / `af613f5af837887f…` | 18,384 B / 282 行 / `af613f5af837887f` | 是 |
| 证据包 | 49,293 B / `020ff5c3a7825fce…` / 49 条 48 PASS 0 FAIL 1 INFO | 49,293 B / 1,427 行 / `020ff5c3a7825fce` / summary 48/0/1 | 是 |
| `backend/app/factors/dsl.py` | 36,785 B / 850 行 / `49f3a110…` | 36,785 B / 850 行 / `49f3a1106095ad0c` | 是 |

git HEAD `65c6e42f`（与证据 `git_head` 一致）。**测试文件不在绑定清单内**，这正是不复现的入口。

### 2.1 口径声明（我的复跑方式）

- 研究侧一律**直接调用研究侧自己的代码** `research/strategy-search-20261107/scripts/common.py`
  的 `open_market / load_panel / add_indicators / add_universe`，不照抄交付方的复写版；
- 生产侧走**被测实现本体**（`compute_in_universe` / `app.factors.dsl.compile_formula` +
  `frame_transform`），不读交付方日志；
- 全样本：`D:/TSP/data/kline_daily_enriched`，60/00 前缀，2018-01-08–2026-11-06，
  **6,438,822 行 / 3,385 只 / 2,141 交易日**；
- 脚本与原始日志：`research/independent-review-20261107/b2/`（见 §6）。

## 3 六项实测

### 3.1 E3-A1：逐日池内家数 vs 研究侧 —— **PASS**

对账口径（`st_flag_missing_policy="treat_non_st"`，契约 §2.3）与生产口径各跑一遍：

| 量 | 我的实测 |
|---|---|
| 比较窗口 | 2019-07-01 – 2026-10-30，窗口内 1,779 个交易日 |
| **可比天数** | **1,770** |
| **差异天数** | **0**（差异日清单：空） |
| null 日 | 9：2026-10-20/21/22/23/26/27/28/29（8 天 ST 窗口）+ 2026-10-30（超覆盖期末端） |
| 日均池内家数 | 生产 1428.1621468926553 / 研究 1428.1621468926553（同值） |
| 生产 null 而研究有值的日 | 9（即上面 9 天，全部为契约强制的不可判日） |

**行级**（比逐日家数更强的一条，交付方未给）：两种 ST 政策下，评估窗内非空 **5,481,294 行**，
`in_universe` 与研究侧 `in_universe` 逐行比较 **不一致 0 行 / 0 天 / 0 只**。
null 行 28,707 = 9 天 × 当日 bar 数，与 W2 同源。

### 3.2 XS 语义负样本 —— **PASS（附一条证据表述瑕疵 N-1）**

我自建 fixture（6 行，`close = 1,7,2,8,3,9`，掩码 `close > 5`，池内 3 只、全局名次 4/5/6）：

| 算子 | 池内 3 行取值 |
|---|---|
| `xs_rank_pool(close, close > 5)` | 0.3333333333333333 / 0.6666666666666666 / 1.0 |
| `xs_rank_pct(close, close > 5)` | 1.3333333333333333 / 1.6666666666666667 / 2.0 |

- 池内名次 / 池内家数 → 恒 ≤ 1；pct 因分母取池内家数而可越 1 → **两者可判死**，与交付方结论同向
  （交付方 fixture 取全局名次 2/4/6，得 `{0.5,1.0}` vs `{0.5,1.5}`，同一性质）。
- **NEG-pool1 的表述不成立（N-1）**：我用 `close = 1,2,3,4,5,9`（单成员全局第 6）实测得
  `pool = 1.0`、`pct = 6.0` —— **可区分**。交付方 fixture 把唯一成员放在全局第 1 位，才出现
  `1.0 == 1.0`。故「池内 1 只时 pool 与 pct 恰好同值」是 fixture 偶然，不是一般结论。

另独立复核类型闸门：`xs_rank_pool(close, volume)` → **E017**；`xs_rank_pool(close, in_universe)`、
`xs_mean(close, in_universe)`、`xs_rank_pool(close, close > 5)` → 编译通过；
`ts_mean(xs_rank_pool(...), 5)` 与 `ts_mean(rank(close), 5)` → 均 **E009**。

### 3.3 `xs_rank_market ≡ rank` 与 `rank` 不变 —— **PASS**

| 检查 | 我的实测 |
|---|---|
| 合成 8 行（含并列值 1,1） | `xs_rank_market(close)` 与 `rank(close)` **逐位相同** |
| 真实样本 258,311 行 / 81 交易日 | `n_diff = 0`，`max_abs_diff = 0.0`，两侧 null 均 0 |
| `rank(close)` 改前/改后 | HEAD 版 `dsl.py` vs 现版：**逐位相同**，哈希均 `262c011b90e535de` |
| `rank(amount)` | 逐位相同，哈希均 `adc43a3f9f23e37b` |
| `zscore(close)`（同类无掩码截面算子） | 逐位相同，哈希均 `3daec85a18efc077` |

做法：`git show HEAD:backend/app/factors/dsl.py` 取改前版本独立加载，与现版在同一份真实面板上
各算一遍后逐元素比对（`n_diff = 0`）。

### 3.4 E1 `market_breadth` —— **PASS**

| 量 | 我的实测 | 交付方 |
|---|---|---|
| 两侧均非 null 的交易日 | **1,770** | 1,770 |
| `max_abs_diff` | **0.0** | 0.0 |
| `mean_abs_diff` | **0.0** | 0.0 |
| 超 1e-12 天数 | **0** | 0 |
| 两侧子集均值 | 均 `0.5422520639953171` | 同 |
| prod null 日 | **9 天**：10-20…10-29（8 天）+ 10-30 | 同 |
| 研究侧这些日的值 | 非空（故 9 天为「prod null / research 有值」错配日） | 同 |
| 当日跨行离散（同一天所有行同值） | 离散天数 **0** | B3 同向 |

编译侧：`xs_mean(close > ma60, in_universe)` 通过，`warmup_bars = 120`、`cross_sectional = True`、
引用因子 `{in_universe, ma60}` —— 与文档 §4 一致。

### 3.5 W1–W4 十四日窗 —— **PASS**

窗口 = 2026-10-20 … 2026-11-06（14 个交易日，44,654 行）。

| 判据 | 我的实测 |
|---|---|
| W1 窗口内 `in_universe` 取到 0/1 的行数 | **0** |
| W2 `universe_unknown_count == 当日有 bar 行数` | **14/14 全等**（3191/3190/3191/3192/3188/3188/3189/3189/3189/3189/3188/3190/3190/3190） |
| W2 原因码 | 8 天 `st_unknown_window`（10-20…10-29）+ 6 天 `beyond_coverage`（10-30…11-06） |
| W3 窗口内 `market_breadth` 非空 | **0 行** |
| W4 窗口内 `xs_rank_pool(vol60, in_universe)` 非空 | **0 行**（44,654 行全 null） |

### 3.6 红灯归因：`none` / `b0_only` / `all_on` —— **PASS（归因成立），但现盘已不成立**

为避免依赖被改过的测试，本节用 **HEAD 版测试副本**（`git show HEAD:backend/tests/...`，
副本在 `/tmp/b2head/`，未写入仓库），三态用 `mv` 移出 pack 目录实测，跑完逐一还原并比对
6 个 pack 文件的 sha256（前后一致）。

| 状态 | 目录条数（builtin） | factor 套件（5 文件） | 矩阵目录测试 |
|---|---|---|---|
| `none`（无 B0、无 B2） | 93 | **74 passed / 0 failed** | **1 passed** |
| `b0_only`（仅 B0） | 107 | **6 failed / 68 passed** | **1 failed** — `unsupported matrix feature: prior_amount_20` |
| `all_on`（现状） | 108 | **6 failed / 68 passed（同一 6 条）** | **1 failed** — `in_universe 缺少必需列: ['raw_close']` |

同一 6 条失败用例（`b0_only` 与 `all_on` 名称逐条相同）：

1. `test_factor_registry.py::test_catalog_counts_and_kinds`
2. `test_factor_registry.py::test_factor_columns_snapshot`
3. `test_factor_registry.py::test_asset_type_filter`
4. `test_factor_registry.py::test_factors_api_contract`
5. `test_factor_registry.py::test_factors_api_asset_filter_and_validation`
6. `test_factor_store.py::test_custom_factor_definition_roundtrip`

→ **「B2 未新增红灯」成立**：6 条在 `b0_only` 已是同一 6 条；矩阵测试在 `none` 全绿、`b0_only`
即红，属 B0。交付方的 `T-A / T-B` 结论正确。

但现盘：测试已被改成押 108，`all_on` 复跑得 **74 passed / 0 failed**；把两个 pack 移走（`none`）
现盘却 **6 failed / 27 passed** —— 即测试已被绑定到两个**未入库**的目录上（见 B-2）。

## 4 两条附加问答

### 4.1 D-B2-2（`in_universe` 进 `/api/factors` 目录）：打破 6 条既有断言

在 HEAD 基线（`== 93`）上，把 `in_universe` 计入目录后被打断的断言共 **6 条**：

| # | 位置（HEAD 行号） | 断言 | 类型 |
|---|---|---|---|
| 1 | `backend/tests/test_factor_registry.py:270-271` | `len(specs) == 93` / id 唯一 93 | 条数 |
| 2 | `backend/tests/test_factor_registry.py:310` | `len(stock) == 93`（同测试内 `len(etf) == 70`） | 条数 |
| 3 | `backend/tests/test_factor_registry.py:358` | `/api/factors` 返回 `len(factors) == 93` | 条数 |
| 4 | `backend/tests/test_factor_registry.py`（`test_factors_api_asset_filter_and_validation`） | `asset_type=etf` → `== 70` | 条数 |
| 5 | `backend/tests/test_factor_registry.py::test_factor_columns_snapshot` | `factor_columns_view() == GOLDEN_COLUMNS` | **快照**（需追加 15 条目录项） |
| 6 | `backend/tests/test_factor_store.py:79,88` | `builtin_count = 93` / `len(...) == 93` | 条数 |

要点：

- **不是 in_universe 独有的 6 条**：`b0_only` 状态下这 6 条**已全部为红**（§3.6 实测）。
  in_universe 只是把期望值 107 → 108、并需在 `GOLDEN_COLUMNS` 追加 1 条（合计 15 条：B0 14 + B2 1）。
  若问「B2 相对 B0 新增几条被打破的断言名」——**0 条**。
- 矩阵目录测试同一条失败被「前移」：`b0_only` 首个失败点是 `prior_amount_20`，`all_on` 变为
  `in_universe`，测试仍为 1 failed（B0 的 8 个 id 仍不可物化，见 N-3）。
- **口径提醒（N-4）**：`107/108` 是 **builtin** 目录口径（`_ordered_specs()`）。本机数据目录
  另有 85 个 `ext_` 外部表因子，`/api/factors` 走 `all_factors()`，实测三态为
  **193 / 192 / 178**，不是 108/107/93。对外的「进目录后是 108」必须限定为 builtin。

### 4.2 CAL-observed_bars 与 E3-A1 是否互斥：**不互斥**

- E3-A1 比较的**两侧都用同一个 cum_count 口径**：生产 `universe.py:130-132`
  `pl.col("date").cum_count().over("symbol")`；研究 `common.py:137` 同一表达式。
  口径差异同时作用于两侧，**不会产生 A1 的 diff**。所以两件事互不否定。
- 量化方向（我自己算的，全样本 6,438,822 行）：

| 量 | 实测 |
|---|---|
| 两口径（cum_count vs `listing_date`+交易日轴）判定 `>=120` 不同的行 | **40,717**（与交付方同数） |
| 其中落在评估窗 2019-07-01…2026-10-30 | **17,499**（与交付方同数） |
| 方向 | **全部为「轴口径放行、cum_count 拦截」**：added 17,499 / **removed 0** |
| 受影响交易日 | **440 天**（单日最多 +148 只，如 2019-10-29 起连续若干日） |

结论：换口径会让池**单向变大**；只要研究侧同步换口径，A1 仍会是 0。若只换生产侧，A1 才会破。
故 CAL 是「选哪个口径」的决策，**不是 E3-A1 的反证**，也不改变本次 A1 的 0 差异结论。

## 5 缺陷清单

| 编号 | 位置 | 事实（可复核） | 阻塞? |
|---|---|---|---|
| **B-1** | `research/b2-engine-20261107/EVIDENCE_20261107.json` → `unchanged_on_purpose` 第 4 条（0-based `[3]`，全文共 4 条）；对照 `backend/tests/test_factor_registry.py`、`test_factor_store.py` mtime `20:48:59` | 证据称「`backend/tests/**` 本批未改任何测试」；现盘两文件已被改（93→108、追加 15 条 golden 列），改动发生在证据冻结（20:37）与派单（20:42）之后。按证据原命令在现盘复跑得 **74 passed / 0 failed**，与证据 `test_status`（6 failed / 68 passed）不一致 → **证据不可复现** | **阻塞（不得据此签认证据）** |
| **B-2** | `backend/tests/test_factor_registry.py:286,287,326,327,374,397`、`backend/tests/test_factor_store.py:79,88`；`?? backend/app/custom/research_factor_pack/`、`?? backend/app/custom/research_universe_pack/` | 测试期望已押 builtin 108，而两个 pack 目录**未入库**（`git status` 为 `??`）。移走目录即 6 红（实测 6 failed / 27 passed，只跑 registry+store+api 三个文件）；干净检出/CI 必然 6 红，且 `in_universe` 在干净检出里根本不存在 | **阻塞（可交付性/可复现）** |
| B-3 | `backend/app/backtest/matrix.py:4557`（`unsupported matrix feature`）、`backend/app/custom/research_universe_pack/universe.py:111` | 矩阵路径无 `in_universe` 物化；`test_research_factor_catalog_matches_matrix_features` 在 `all_on` 仍红（并掩盖 8 个 B0 id） | 非阻塞（契约已列 B0b；但结项记录必须写明该测试红） |
| N-1 | 证据 `NEG-pool1` 的 `note` | 「池内 1 只时 ① 与 ③ 恰好同值，不能用来区分」过度泛化；实测单成员全局第 6 得 `pool=1.0 / pct=6.0`，可区分 | 非阻塞（改为「本 fixture 下」） |
| N-2 | 证据 `test_status.classification` | 称 6 条全为「目录条数硬编码 93」；实际第 5 条是 `GOLDEN_COLUMNS` 快照（需追加列项），不只是条数 | 非阻塞 |
| N-3 | 证据 `test_status.matrix_catalog_test.detail` | 单条测试一次只报首个失败点；「前移」后 8 个 B0 id 的不可物化仍未被该测试覆盖 | 非阻塞 |
| N-4 | `docs/factors/B2_IMPLEMENTATION_20261107.md`（「107/108」表述） | 为 builtin 口径；本机 `/api/factors` 实测 193（含 85 个 `ext_` 因子） | 非阻塞（加限定词） |
| N-5 | `backend/app/custom/research_universe_pack/universe.py:128` 注释 | 引「`common.py:129` `date.cum_count()`」，实际该行在 `common.py:137` | 非阻塞（注释漂移） |

## 6 未验证（不得视为通过）

1. `in_universe` 被**具体策略**实际引用后的选股效果（回测/信号侧）；本批只验到因子层与目录层。
2. 矩阵路径 `in_universe` 物化（B0b 范围），及矩阵侧 `xs_rank_pool` 的等价性。
3. E2 在**真实全样本**上的区分力：交付方声明「池内无空 `vol60`，XS-A2 不可区分
   （`days_with_pool_member_null=0`）」，我未复算该计数；区分力仅由我的合成 fixture 证明。
4. E1 的 `B2`（月末通过率 47/87 = `0.5402298850574713`）与 `XS-C2` 靶值——未复算。
5. `/api/factors` 的 HTTP 端到端（我直连 TestClient 得 403 需鉴权；目录包含性由
   `test_factors_api_contract` 在测试环境覆盖，非我独立复算）。
6. `st_history` 上游数据本身的正确性（8 天窗口为何被批量写成 `st_flag=false`，属数据侧）。
7. 部署态 provider 发现（`app.custom` 扫描在打包/容器环境下的可见性）。

## 7 我的复跑脚本与原始日志

均在 `research/independent-review-20261107/b2/`（只读正式代码与数据，不写业务状态）：

| 文件 | 用途 |
|---|---|
| `step1_e3a1_e1_w.py` / `step1.json` | E3-A1、E1、W1–W3（研究侧直接 import `common.py`） |
| `step2_xs.py` / `step2.json` | XS 负样本、XS-B1、`rank/zscore` 改前改后、W4 |
| `step3_cal.py` / `step3.json` | CAL 口径差异的方向与量级 |
| `step4_rowlevel.py` / `step4.json` | E3-A1 行级等价（5,481,294 行，0 不一致） |
| `logs/{none,b0_only,all_on}_factor_head.txt`、`*_matrix_head.txt` | 三态 pytest 原始输出（HEAD 基线） |
| `logs/none_current_tests.txt` | 现盘测试在无 pack 状态下的 6 红 |

## 8 我自己的方法边界

- 三态隔离用 `mv` 移出 pack 目录，**跑完立即还原并比对 6 个文件 sha256**（前后一致）；测试副本
  取自 `git show HEAD:`，未修改仓库内任何测试。
- 我在审核开始时用 `git status | head -40` 看变更，**把被截断的 `backend/tests` 两条漏掉了**，
  这是我 20:42 时没能第一时间发现测试被改的原因；后续用 `git status -- backend/tests` 才发现。
- 研究侧我直接调用 `common.py` 的函数，因此本节结论依赖该文件自身未被改动（HEAD 无 diff，
  `git status` 未列出）——这一点我核过。

## 9 审核窗口之后契约前移（不改本报告判定，但必须登记）

我按下单绑定审的是 **v0.7 `5a87d4b0`**，全窗口未变（§2）。审完（21:00 后）目录内新出现：

| 文件 | 大小 | mtime | sha256（前 16） |
|---|---|---|---|
| `FACTOR_ENGINE_CONTRACTS_20261107_v0.8.md` | 206,608 B | 21:02:25 | `bff16cb5bf2722bc` |
| `FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md` | 228,739 B | 21:02:30 | `980e76dec91db439` |

v0.9 修订记录自述四项：`F-A11b` **收窄为列级一条**（即我在 B0 报告里提的 B0-4）、新增 §7.16 闸门条款、
新增 §2.8 `observed_bars` 口径登记（40,717 / 17,499，**不改判据**）、§2.7 追加 `in_universe` 进目录（93→107→108）。

**与本次验收的关系**：

1. 本报告的 PASS/FAIL 只对 v0.7 有效。若开发经理改绑 v0.8/v0.9，需重报——但**六项判据本身未被 v0.9 改写**
   （§2 / §3 / §4.6 的实质条款未变；`F-A11b` 收窄属 B0 范围，不影响 B2 六项）。
2. v0.9 §2.7 已把「5 处 `条数==93` 断言于 20:48:59 同步为 108（未提交）」写成
   「**这是过期断言更新，不是回归**」。这句话解释的是**动机**，不改变两件事实：
   证据包在现盘复跑不出它自己写的 `test_status`（B-1）；两个 pack 目录仍是 `??`，干净检出必 6 红（B-2）。
3. v0.9 已把 `E017` 记为「已落地」、`xs_rank_market` 改为「算子键层独立计数、因子台账层仍合计算 1」——
   与我 §3.2 / §3.3 实测一致，不产生新分歧。
