
---

## 12. 裁定补记 v1.7（2026-11-07 22:4x）：S09 → S02 解冻重跑（D1 定稿后，canonical 口径）

**触发**：D1（`prior_X_N = ts_delay(ts_max(high,N),1)`）13:58 定稿 → §3.3 的重跑解冻，顺序 S09 → S02。本节只回答这两条现在的准入问题，不改 §1 / §2 / §7 / §10 / §11 任何已生效条款。

### 12.1 用的 id：canonical（`uf_*`），不是 alias

| 用途 | canonical id（本次实跑） | 对应 alias（pack 研究原名，禁用） |
| --- | --- | --- |
| S09 入场·高点腿 | `uf_prior_high_55` | `prior_high_55` |
| S09 入场·量能腿 | `uf_prior_vol_20`（`volume > 1.5 * uf_prior_vol_20`） | `prior_vol_20` |
| S09 出场 | `ma20`（`close < ma20`；单侧 canonical，无 `uf_` 双胞胎） | — |
| S02 入场 | `uf_prior_high_20` | `prior_high_20` |
| S02 出场 | `uf_prior_low_10` | `prior_low_10` |

走的是真 frame 路径：`store.load_into_registry(settings.data_dir)` → `materialize_scoring_columns(frame, [...])` → `dsl.compile_formula(...).frame_transform(...)`；研究侧是 `research/strategy-search-20261107/scripts/common.py` 原样（36 次运行的同一套表达式）。两侧**共用同一个 `in_universe` 列**，把 E3 池子差排除在外，只比因子口径。

复现（只读，约 3 分钟）：

```bash
cd /c/work/sourcecode/tick-stock-panel
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/s09-s02-rerun-20261107/rerun.py
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/s09-s02-rerun-20261107/account_check.py
```

证据：`research/s09-s02-rerun-20261107/RESULT.json`（信号层）、`ACCOUNT_CHECK.json`（账户层）、`run.log` / `account.log`（原始输出）。面板 6,422,875 行 / 3,384 只 / 2,136 日 / 2018-01-08…2026-10-30，`panel_hash = fda82b47b6d5b92e0cc4b6d481020ee9a5cb328b282645c647697927c0f6dfe3`——**与 `registry.json#meta.panel_hash` 逐字相同**，故本节任何差异都不能归因于面板数据变动。

### 12.2 信号层：jaccard 全 1.000，且是逐位相同（不是"接近"）

| 判据 | 结果 |
| --- | --- |
| S09 入场 jaccard | **1.000** |
| S09 高点腿（`close > prior_high_55`） | **1.000** |
| S09 量能腿（`volume > 1.5 × prior_vol_20`） | **1.000** |
| S09 出场（`close < ma20`；另测 `ma20_bias < 0` 同值） | **1.000 / 1.000** |
| S02 入场 / 出场 | **1.000 / 1.000** |
| 入场序列 sha256（canonical vs 研究侧） | S09 `52c70ceb…43c7` = `52c70ceb…43c7`；S02 `4cc32c5d…7529` = `4cc32c5d…7529` |
| 出场序列 sha256 | S09 `a0307980…8391` 两侧相同；S02 `38b2d7db…f6c7` 两侧相同 |
| 逐日计数差（4 项全部） | 有差日 **0**、单日最大差 **0**、均值差 **0.0** |

选股数分布（评估窗 1,779 交易日，池内）：

| 项 | 总额 | 有信号日 | 均值 | 中位 | 最小 | 最大 | registry 登记 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| S09 入场（canonical） | **52,965** | 1,776 | 29.82 | 22 | 1 | 818 | 52,965 ✅ |
| S02 入场（canonical） | **127,877** | 1,779 | 71.88 | 56 | 3 | 988 | 127,877 ✅ |
| S09 出场（canonical） | 2,861,205 | 1,779 | 1,608.3 | 1,646 | 20 | 3,002 | —（不入账） |
| S02 出场（canonical） | 487,212 | 1,771 | 275.1 | 113 | 1 | 2,770 | —（不入账） |

因子值层（canonical vs 研究侧，全窗）：

| 对 | n（双双非空） | `max_abs_diff` | 非零差行 | null 不一致 |
| --- | ---: | ---: | ---: | ---: |
| `uf_prior_high_55` vs `prior_high55` | 6,237,186 | **0.0** | 0 | 0 |
| `uf_prior_vol_20` vs `prior_vol20` | 6,355,214 | **0.0** | 0 | 0 |
| `uf_prior_high_20` vs `prior_high20` | 6,355,214 | **0.0** | 0 | 0 |
| `uf_prior_low_10` vs `prior_low10` | 6,389,042 | **0.0** | 0 | 0 |
| `ma20` vs 研究侧 `ma20` | 6,358,596 | **0.0** | 0 | 0 |
| `uf_prior_high_250` vs `prior_high250` | 5,584,049 | **0.0** | 0 | 0 |
| `uf_vol60` vs `vol60` | 6,220,352 | **1.11e-16**（1 ULP） | 4,781,712 | 0 |

→ **§3.4-1 判据（信号层 jaccard = 1.000）对 S09、S02 都成立**，且不是"接近"：序列哈希相同、逐日计数零差。`vol60` 的 1 ULP 与台账 V3 记的 2.78e-17 数值不同（窗口不同：本节为 2018-01-08…2026-10-30 全窗），两者都 ≪ 1e-12，且 V3 已证 250 个交易日名次零换位，不影响任何 rank 阈值。

### 12.3 账户层：canonical 与研究侧逐笔一致（差异 0，不是"已归因的残差"）

| 项 | S09 canonical | S09 研究侧（今日） | S02 canonical | S02 研究侧（今日） |
| --- | ---: | ---: | ---: | ---: |
| 建仓笔数 | **679** | **679** | **442** | **442** |
| 期末权益 | **36,187.24** | **36,187.24** | **111,695.81** | **111,695.81** |
| 逐年笔数 | 33/87/80/118/86/93/96/86 | 同左 | 24/60/57/73/51/62/58/57 | 同左 |
| 逐年信号数 | 1752/7756/7082/5678/5313/7812/10775/6797 | 同左 | 4773/17206/16750/14671/12139/17870/24920/19548 | 同左 |

→ **迁移到 canonical 的收益差 = 0（逐笔、逐段、终点权益全等）**，§3.4-2「不允许未解释残差」满足，且不是"残差足够小"。

### 12.4 重跑里发现的第二件事：**S09 的 registry 数字在今天的 HEAD 上不可复现**

同一进程、同一帧、同一引擎，只换列名（研究列 vs canonical 列）结果完全相同，但**两者都与 registry 不一致**（S02 则完全一致）：

| 项 | registry（S09@10） | 今日实跑（两侧同值） |
| --- | ---: | ---: |
| 建仓笔数 | 732 | **679** |
| 期末权益 | 59,011.37 | **36,187.24** |
| 全期总收益 | −94.10% | **−96.38%** |
| 逐年笔数 | 42/94/85/117/91/101/103/99 | **33/87/80/118/86/93/96/86** |
| 逐年**信号**数 | 1752/7756/7082/5678/5313/7812/10775/6797 | **完全相同** |

**已确证**：入场 / 出场信号与研究侧、与 registry 的逐年信号数**三者完全一致**；面板哈希与 registry `meta.panel_hash` 相同；S02 的 442 笔 / 111,695.81 与 registry **逐位相同**——所以不是重跑脚本的问题，也不是面板数据的问题，差异只可能出在**撮合 / 账户层**。

**已核到的事实**：`registry.json#meta.head = 848bd04b`，当前 `HEAD = 65c6e42f`；`backend/app/backtest/engine.py` 在 **2026-11-07 12:54:24（commit `15717100`「feat(backtest): add continuous accounts and trading-day walk-forward」）** 被改过 298 行，加入 `PortfolioCarryState` / 段末 carry / `pending_buy_plans` 跨段撮合。registry 生成于 **11-06 23:19**，在那次改动之前。

**未确证**：差异是否就由 `15717100` 引起。S09 的出场信号覆盖 97% 的持仓日、对 carry / 同日重入最敏感，S02 只有 17%，这与「S09 变、S02 不变」的形状吻合，但仍是推断。settle 的办法：在 `848bd04b` 的引擎上跑一遍 S09@10，或在现 HEAD 上重跑 36 次并重钉 `registry.meta.head`。

**这条不属于口径问题，但它决定"哪份数字可用"**：S09 的 `research-v1` 数字（−94.10% / 732 笔）在今天的仓库上不可复现；今天的数字是 −96.38% / 679 笔。两者方向一致（都是灾难级），**准入结论不变**，但引用时必须写明是哪一天的引擎。

### 12.5 准入判定（逐条，给依据）

| 策略 | 口径 / 实现层 | 依据 | 策略判定层 | 依据 |
| --- | --- | --- | --- | --- |
| **S09** | **可准入**（原来不可：系统口径入场 jaccard 0.000） | canonical id 齐备且可编译（`uf_prior_high_55` + `uf_prior_vol_20`，warmup 56）；信号 jaccard 1.000（两条腿分测也是 1.000）+ 出场 1.000；逐日计数零差 | **仍判死**（不是"变好"） | 全期 −96.38%、T2 Sharpe 远 < 0.2；CRITERIA §4 S09 的判死条件（信号级跳空不触发，但涨停拦截绝对门 1,387 > 1,000 成立；比率门 W9 为主判）仍触发；E1 = FAIL 使上限只能是 HOLD，S09 连 HOLD 都不必谈 |
| **S02** | **可准入**（原来不可：出场触发率 0.000%） | canonical 齐备（`uf_prior_high_20` + `uf_prior_low_10`，warmup 21）；信号 jaccard 1.000；账户层 442 笔 / 111,695.81 与 registry 逐位相同 | **仍判死** | 全期年化 −26.70% < 0 且 T2 Sharpe −1.303 < 0.2；gross −24.88% < 0 → CRITERIA §4 S02 两条判死条件**都**满足 |

**一句话**：这次重跑修好的是「**这条策略到底测的是什么**」，不是「这条策略能不能赚钱」。S09 / S02 从"口径不可复现（数字根本不是在测该假设）"变为"口径可复现（数字可信）"，而可信的结论是两条都判死。**别把"可准入"读成"可上线"**。

### 12.6 本节没有改变的

12 条阈值；S09 / S02 的 `void` 状态（本轮关掉的是 `void_reason` 里的口径部分，判死不是它的反义词）；五条截面策略的 `void` 与重验顺序 S07 → S11 → S12 → S10 → S06；D1 / D2 / D4 / D10 的裁定。**没有动 `registry.json`**（`void` 标注与数字由量化研究员维护）。

### 12.7 未确证

- S09 registry 数字与今日差 53 笔，归因到 `15717100` 属推断（见 §12.4）。
- 今日 S09 的 `cagr` / `sharpe` **未重算**：本节只给期末权益与总收益（36,187.24 → −96.38%），年化 / Sharpe 需按 `equity[]` 重算，属量化研究员的活。
- `vol60` 的 1 ULP 与台账 V3 记的 2.78e-17 数值不同（窗口不同），未逐值对账到那份证据文件。
- 两侧共用 `in_universe`：本节**没有**单独验 E3 池子在 canonical 路径下的行为（§11 已单列，E3-A1 `days_with_diff = 0`）。

---

## 13. 裁定补记 v1.7（2026-11-07 22:4x）：`market_breadth`（E1）**注册**成策略可用因子 id

### 13.1 现状（可核）

E1 已在 frame 路径实现并独立复核：`xs_mean(close > ma60, in_universe)`，`B1_n_compared_days = 1770`、`B1_max_abs_diff = 0.0`、9 个 null 日全为 `st_unknown_window`(8) + `beyond_coverage`(1)、`B2_pass_rate = 0.5402`、`B5_idempotent = true`、`warmup_bars = 120`、`cross_sectional = true`（`research/b2-engine-20261107/logs/e1_verify.json`）。但 `backend/app/**` 里 `market_breadth` **0 命中**——没有注册 id。S12 规格若按 id 引用会 `E001`。

### 13.2 裁定：**注册**（走法 ②），id 定为 `market_breadth`，登记在 research factor pack（单侧，**不建 `uf_market_breadth` 双胞胎**）

四条理由，判据是「让 S12 的规格只有一个定义出处」：

| # | 理由 |
| --- | --- |
| 1 | **走法 ①（S12 直接写表达式）会把掩码口径抄进策略规格。** 表达式里含着 §10 判定的掩码语义（池内 ∩ `ma60` 非空、池空 → `null`）。写进策略文本 = 同一口径两个出处（契约 §4 + S12 规格），正是今天 xs_rank 那场争议的成因。注册后该口径只活在因子定义里 |
| 2 | **成本是零**：表达式已实现且与研究生侧逐日 `max_abs_diff = 0.0`（1,770 日），注册只是把它变成 id，不改任何数值、不需要重跑 |
| 3 | **时序上不阻塞任何东西**：S12 在 E2 重验队列**末位**（S07 → S11 → S12 → S10 → S06），它今天本来就不能跑；注册可以在它排队期间完成。走法 ①"省事"省的是一个不在关键路径上的等待 |
| 4 | **没有它，S12 的依赖不可见**：S12 是五条件策略里唯一带市场级腿的一条。腿藏在表达式里，台账读者与闸门都看不到"这条策略依赖一个按日聚合的市场量" |

**代价（明写）**：+1 条注册 + 1 行台账 + 因子计数 +1；每个消费方的 frame 会多一列按日广播的重复值（约 3,000 行/日同值）。

### 13.3 注册规格（交因子工程师执行，口径不改）

| 字段 | 取值 |
| --- | --- |
| `id` | `market_breadth`（**研究原名即 canonical**，理由同 `prior_amount_20`：pack 单侧、无 store 双胞胎；若日后落 store，必须同一次把 canonical 改为 `uf_market_breadth` 并完成引用迁移） |
| `formula` | `xs_mean(close > ma60, in_universe)` |
| `semantics` | `market_aggregate_daily`（**按日聚合、按标的广播**）；`shift = 0`；`price_basis = close`；`unit = ratio`；值域 `[0, 1]` |
| `warmup_bars` | **120**（`ma60` 60 + `xs_mean` 需 ≥120 根，实测 `B6_pass`） |
| `dependencies` | `{close, ma60, in_universe}` |
| `cross_sectional` | `true`（DSL 编译实测） |
| `strategy_usable` | `true`（唯一消费者 S12） |
| **硬约束（写进台账同一行）** | **禁止对 `market_breadth` 再做任何截面算子或排名**（`rank` / `zscore` / `winsorize` 等）：它是按日广播的标量，截面统计只会得到约 3,000 倍重复计数 |

### 13.4 若将来改判走法 ①（S12 写表达式）的前提

只有「`xs_mean` 语义连同掩码口径被写进契约、且 S12 规格引用契约章节号而不是抄表达式」时才可接受。**不接受"S12 规格里贴一遍 `xs_mean(close > ma60, in_universe)`"这种形态**——那是把口径搬到第三个地方。

### 13.5 本节未确证

- 注册后 `market_breadth` 在**矩阵回测**路径是否可用：E1 只验了 frame 路径；矩阵侧 `xs_mean` 是否有对应实现未核（若没有，S12 只能走 frame 路径，需在规格里写明）。
- 9 个 null 日（8 个 ST 未知窗 + 1 个超出覆盖）是否恰好落在月末判定日：未核（§10 已列为未确证项）。

---

## 14. 裁定补记 v1.7（2026-11-07 22:4x）：8 组 alias → canonical 迁移清单（B0b-1 接线前置）

### 14.1 结论：**迁，8/8 全迁**，且迁移本身零数值代价

依据是 §12 的实测 + 台账 V3：`uf_*` 与研究原名在 8 组上逐位相同（5 组 `max_abs_diff = 0.0`；`vol60` 差 1 ULP 且 250 个交易日名次零换位）。所以"迁 = 改名"，不触发任何重算。

### 14.2 逐条清单

| # | alias（禁用） | canonical（规格里必须写这个） | 消费者 | 谁改 | 迁移后要重跑吗 |
| --- | --- | --- | --- | --- | --- |
| 1 | `vol60` | `uf_vol60` | S07 核心、S11 排名项、S12 核心 | 策略规格（我）+ 台账 `alias_of`（因子工程师） | **不用**（本就因 E2 在重验队列里，重验时直接用 `uf_vol60`） |
| 2 | `ma120` | `uf_ma120` | S03 趋势过滤、S08 趋势过滤 | 同上 | **不用**（公式逐字相同，`max_abs_diff = 0`） |
| 3 | `ma200` | `uf_ma200` | **无策略消费者** | 台账 | 不用 |
| 4 | `prior_high_20` | `uf_prior_high_20` | S02 入场 | 策略规格 + 台账 | **已重跑**（§12：jaccard 1.000、442 笔逐位一致） |
| 5 | `prior_high_55` | `uf_prior_high_55` | S09 入场 | 策略规格 + 台账 | **已重跑**（§12：jaccard 1.000、679 笔双侧一致） |
| 6 | `prior_high_250` | `uf_prior_high_250` | **无直接消费者**（S08 用 `uf_dist_prior_high_250`） | 台账 | 不用 |
| 7 | `prior_low_10` | `uf_prior_low_10` | S02 出场 | 策略规格 + 台账 | **已重跑**（同 #4） |
| 8 | `prior_vol_20` | `uf_prior_vol_20` | S09 入场量能腿 | 策略规格 + 台账 | **已重跑**（同 #5） |

单侧 6 个 id（**本身即 canonical，不迁**）：`ma20`、`ma60`、`boll_lower`、`boll_upper`、`sd20`、`prior_amount_20`。单侧例外 1 个：`uf_dist_prior_high_250`（无 pack 对应件，本身即 canonical）。

### 14.3 **接线真正的阻塞不是 alias，是 `status` —— 实测，别按"迁完就通"排期**

我按 `B0b-1` 接线后的调用形态实跑了闸门（`assert_factors_usable(..., shadow=True)`）：

| 输入集合 | `mode="production"` | `mode="research"` |
| --- | --- | --- |
| 8 个 alias（`vol60` … `prior_vol_20`） | 全拒，码 **`FS01`**（不是 `FS03`） | 同 |
| 8 个 canonical（`uf_vol60` … `uf_prior_vol_20`） | **全拒，同样 `FS01`** | 同 |
| S09 规格集（alias 版 / canonical 版） | 两版都拒，`FS01` | 同 |
| S02 规格集（canonical 版） | 拒，`FS01` | 同 |
| 同上 + `require_status=False` | **全过**（`ok=True`，blocked / non_active 皆空） | 同 |

原因：**8 只 `uf_*` 的落盘定义是 `status = "draft"`**（契约 §7.5 第 5 条禁止未过 V3 标 `active`），而 pack 侧 6 个单侧 id（`ma20` / `ma60` / `sd20` / `boll_lower` / `boll_upper` / `prior_amount_20`）**根本没有 `status` 字段**，缺 status 按 draft 处理 → `FS01`。`alias_of` 目前也还没写进任何定义，所以 alias 连 `FS03` 都报不出来。

→ **结论：只做 alias → canonical 改名，接线后 5 条策略仍然全被 `FS01` 挡住。** 要让 B0b-1 真的通，必须同时做两件（都不是我的职权）：

1. **8 只 `uf_*` 升 `active`**：V3 对账已过（`F_CLASS_RANK_PARITY_20261107.json`，8 对 `pass_1e12`），由因子工程师按契约流程改 status；
2. **6 个单侧 pack id 补 `status`**（或裁定 pack id 不适用 status 并在闸门里显式豁免）——否则 `ma20` / `prior_amount_20` 这类永远 `FS01`。

### 14.4 迁移顺序（给开发侧排期用）

```text
① 因子工程师：8 只 uf_* status→active + 8 只 alias 写 alias_of / strategy_usable=false + 6 个单侧 id 补 status
② 我：策略规格文本把 8 组 alias 换成 canonical（不改公式、不改参数、不改阈值）
③ 开发侧：把 assert_factors_usable 接到生产入口（此时才可能不拒）
④ 独立审核：验 FS03 只对 alias 触发、canonical 放行
```

**① 与 ② 可并行**；③ 在前两步完成前接线只会得到"全拒"这个假阳性。

### 14.5 风险（迁移后仍需盯）

- 5 条策略规格里凡是把 `ts_std(close/prev_close-1,60)`（S07 / S11 / S12）或 `ts_mean(close,120)`（S03 / S08）**内联**的写法，必须换成 id，否则 G1 的"同一经济量散落在每个策略里"没有解决，只是绕过了闸门（内联不产生引用，闸门看不见）。
- 迁移**不改变**任何已判定的策略结论，也不改变 S07 / S11 / S12 因 E2 而 `void` 的状态。

### 14.6 未确证

- `alias_of` / `strategy_usable` 写进定义 JSON 后，闸门是否确实报 `FS03` 而非 `FS01`：**未实测**（当前盘上没有一条 `alias_of`，`check_ledger_consistency` 直接 `NotImplementedError`）。
- 矩阵回测路径对 8 只 `uf_*` 的支持：契约 §1.5 已记"矩阵缺口"，本轮未碰。
- 单侧 6 个 id 的 `status` 该"补"还是"豁免"，属契约裁定；我给的是两条路，不是结论。
