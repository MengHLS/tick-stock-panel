# 契约修订记录 R2（v0.2 → v0.3）：批一证据回灌六处

作者：系统架构师 · 2026-11-07 · 性质：**只改契约文字与表格**。未改策略口径、未改因子定义与台账、未改任何代码、未提交、未部署、未跑收益回测。
用途：给开发经理与独立审核做「改了什么 / 为什么改 / 依据在哪」的一页对照；契约正文仍是唯一权威（`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md` v0.3）。

## 1. 绑定版本（派发方与审核方请按此核对）

| 项 | 修订前 | 修订后 |
| --- | --- | --- |
| 文件 | `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md` v0.2 | 同文件 **v0.3** |
| 字节 / 行数 | 65,865 B / 778 行 | **89,833 B / 914 行** |
| 全文 sha256 | （v0.2 footer 只记录了正文前 65,626 B 的 `29c0aea8…daeca6a`；全文未留） | `5eb9772411f723576b657f85af7c0aa26427137a41fb53b5774b935942565903` |
| 正文（footer 之前）sha256 | — | `b082d902e08df2dc902f97d694dcd2e1ae96d93bd79485a66647470915f9bfef`（`head -c 89350`，**字节口径**，见 §8-S3） |
| 修订时刻 | — | 2026-11-07 15:23–15:51（Asia/Shanghai） |
| **冻结时刻** | — | **2026-11-07 15:51（Asia/Shanghai）**；此后不再改动，任何改动必须按新正文重算 footer 四字段并递增版本（v0.4） |
| git 状态 | `docs/architecture/` 整体未跟踪（`??`），无 git 基线可 diff | 同左；**本文件也未提交** |

> **绑定只认上表最终四元组**：`89,833 B / 914 行 / 全文 `5eb97724…565903` / 正文 `b082d902…f9bfef`（`head -c 89350`）`。
> 修订过程中出现过五个中间态（88,348 B/`3ceeb4e0…`、88,360 B/`ed5d28ca…`、89,498 B/`3749e603…`+`head -n 913`/`c70d4493…`、89,709 B/`c3c41277…`+`head -n 913`/`d8ca6de5…`，以及我本人在 15:45 写下的 89,740 B/`9dffb36e…` 被同一文件的另一轮写入覆盖），**一律作废，不得作为审核绑定**。

> 说明：`docs/architecture/` 与 `docs/factors/`、`docs/research/` 均未纳入 git，因此「原句」以 v0.2 当时的文件内容为准，本文照抄。

## 2. 六处逐条（原句 → 新句 → 依据）

### R2-1 §7.1「坑 3」：从「会大 100 倍」改为「同名不同单位」的事实陈述

**原句（v0.2 §7.1 坑 3，整段）**
> 3. **`vol60` 不要用 `change_pct`**。`change_pct` 是已注册 base 因子，但工程内该字段单位不统一（`app/api/intraday.py:72` 计算时 `*100`，即百分数）。`ts_std(change_pct,60)` 会得到比研究大 100 倍的数值——而分位排名不变，**只在跨因子加权或阈值处爆掉**，最难发现。用上表的 `close / ts_delay(close,1) - 1` 显式自洽（`deps={close}`），或注册前先做单位对账。

**新句（v0.3 §7.1 坑 3，摘要；全文见契约）**
> 3. **`change_pct` 的真实风险是「同名不同单位」，不是「数值大 100 倍」**（v0.3 更正，原表述已作废）。三处实测：因子/策略/指标路径 = 小数（`pipeline.py:538-539`、字段串 `:156`「小数, 如 0.05 = 5%」、`matrix.py:4264 → :4685-4694`）；展示/API 路径 = 百分点（`api/intraday.py:72`、`api/overview.py:282`、`services/market_overview_builder.py:130`）；provider 适配层有显式换算（`plugins/fuyao/provider.py:273-275`、`plugins/tdxquant/provider.py:18`）。研究 `ret1` 与系统 `change_pct` 的 `max_abs_diff = 2.22e-16` → **因子路径同口径**。→ 因子帧内引用 `change_pct` 合法；禁止的是**跨层取数**与**按同名推断单位**。`vol60` 仍建议用显式公式，理由改为「依赖面更小、与研究同源、不受未来口径变更影响」。

**依据（逐条可复跑）**

| # | 事实 | 位置 / 数字 |
| --- | --- | --- |
| 1 | `change_pct` 是 base 因子 | `get_factor("change_pct")` → `kind="base"`, `version=1`, label 日涨跌幅 |
| 2 | 面板口径 = 小数，且字段文档明写 | `backend/app/indicators/pipeline.py:538-539`（`close/close.shift(1)-1`）、`:156`（「日涨跌幅(小数, 如 0.05 = 5%)」） |
| 3 | 矩阵口径 = 小数 | `backend/app/backtest/matrix.py:4264` → `_valid_return_over_bars`（`:4685-4694`，`close/prev - 1`） |
| 4 | 策略按小数比较 | `seeds/oversold_reversal.py:77`、`strong_open.py:81`、`active_limit_gene.py:72`、`breakout_new_high_60d.py:67`、`high_turnover_surge.py:73`、`limit_up_momentum.py:61`、`ma_convergence_breakout.py:89` 均 `threshold/100.0`；`broken_board_recovery.py:75-76` 直接写 `0.03` |
| 5 | 展示路径 = 百分点 | `api/intraday.py:72`、`api/overview.py:282`、`services/market_overview_builder.py:130`（均 `*100`） |
| 6 | provider 层已归一 | `plugins/fuyao/provider.py:273-275`（`pct / 100.0`，注释「百分数 (1.74 = +1.74%) → 小数制」）；`plugins/tdxquant/provider.py:18`（「小数制」） |
| 7 | 因子路径与研究同值 | 因子工程师实测 `max_abs_diff = 2.22e-16` |

**同时改了 §7.5-2 的禁止条款**（原「禁止用 `change_pct` 构造 `vol60`（单位不统一）」→「禁止跨层取数；因子帧内可直接引用」）：否则禁止条款与 §7.1 的新事实自相矛盾。

### R2-2 §7.6 `F-A6`：从「典型值区间」改为分位双重量纲判定

**原句（v0.2 §7.6 最后一行）**
> | F-A6 | 单位量级 | `vol60` 典型值 0.015–0.06（百分点口径会是 1.5–6），越界即 fail |

**新句（v0.3 §7.6，拆为四条）**
> F-A6a 量纲（中位数）：评估域 = `60*`/`00*` × `2019-01-01` 起 × 逐 symbol `ret1` 的 `rolling_std(60, min_samples=60, ddof=1)` × 非空 × `n ≥ 5.0e6`；判据 `p50 ∈ [0.015, 0.06]`。
> F-A6b 上尾：`p99 < 0.10`。
> F-A6c 下尾：`p01 ∈ (0, 0.02)`。
> F-A6 判定：三者同时成立 = pass；任一不满足 = fail，失败报告必须打印实测 `p01/p50/p99` 与「百分点口径的预期值（×100）」。

**依据（实测，两次独立复算）**

| 复算人 | 样本 | n | mean | p01 | p50 | p99 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 系统架构师（本次，`backend/.venv` polars，raw close） | `60*`/`00*`，2019-01-01–2026-10-29 | 5,639,581 | 0.026555 | 0.009244 | 0.025096 | 0.056152 |
| 开发经理（批一证据） | 全样本 | 5,469,335 | 0.0261 | 0.0090 | 0.0247 | 0.0549 |

两次差异（p50 2.3%、p99 2.3%）来自样本窗与是否用复权价，量级一致。**原句按字面会误判**：p01 = 0.0090–0.0092 < 0.015，全样本约 1% 的行合法地落在「典型区间」之外。
判据区分力（用于机械定位错口径）：百分点口径 p50≈2.5（破上界 40 倍）、方差口径 p50≈0.0006（破下界 25 倍）、年化口径 p50≈0.39（破上界 6 倍）。

### R2-3 §7.6 `F-A5`：把「未实现」改成「工作区有未提交实现、HEAD 没有」

**原句（v0.2 §7.6）**
> | F-A5 | 幂等 | 同内容二次注册：`version` 不变、`unchanged=true`、缓存未全表失效 |

**新句（v0.3 §7.6）**
> | F-A5 | 幂等 | ……（靶值不变）**实现现状（2026-11-07 15:44 复核）**：工作区已有**未提交**实现 `backend/app/factors/store.py:207-257`（`content_signature` / `is_same_content` / `upsert_definition`）+ `backend/app/api/factors.py:333-360`；HEAD `65c6e42f`（12:56:05 +0800）中没有这部分（`git show HEAD:backend/app/factors/store.py` 内 `unchanged` 命中数 = 0）；`git status` 两文件为 `M`，mtime 15:35:28。**判据状态 = 待独立审核**，通过前不得记为已满足。

**依据**

| 检查 | 结果 |
| --- | --- |
| `grep -n unchanged backend/app/factors/store.py` | 4 处：`:226`、`:229`（docstring 两行）、`:239`（返回 `unchanged: True`）、`:257`（返回 `unchanged: False`） |
| `git show HEAD:backend/app/factors/store.py` 内 `unchanged` | **0** 处 → HEAD 无该实现 |
| `git status --porcelain backend/` | ` M backend/app/api/factors.py`、` M backend/app/factors/store.py`（+ `?? backend/app/custom/research_factor_pack/`） |
| mtime | 两文件均 `2026-11-07 15:35:28`（15:44 复核；批一b 末次写入，晚于派单时点） |
| diffstat | `api/factors.py` +8/−16、`store.py` +91/−1（删掉 `_next_version`，改走 `upsert_definition`；`git diff --numstat` 实测） |

**为什么这条必须写清楚**：批一证据里「`git grep -n "unchanged" -- backend/app` 零命中、F-A5 属未实现、已派批一b」在**当前工作区已不成立**（结论仍对：HEAD 无；错的是「现在没有」）。若照原判断写「未实现」，审核方会按「无此功能」验收，而实现其实已经躺在工作区，容易被当成新代码重复实现或误判为越界改动。

### R2-4 §7.7（新增）：`status` 不进运行时对象 → 闸门放哪一层

**背景原句（v0.2 §7.5-5）**
> 5. **禁止**给未通过 V3 的因子标 `status="active"`。

**新句**：保留该条，并新增第 6 条 + 整节 §7.7（约 70 行）。要点：
1. 事实五条：`FactorSpec` 21 个字段无 `status`（`registry.py:33-56`）；`to_spec` 只投影成 `stability`（`store.py:94`、`:110`、`:165`）；`grep -rn status backend/app/factors/registry.py` 零命中；`POST /custom/{id}/status`（`api/factors.py:510-531`）只是改 JSON + 重注册；**结论：§7.5-5 目前只是登记纪律，运行时没有闸门**。
2. 两层落地：① 数据层 `FactorSpec.status`（默认 `"draft"`，安全方向）；② 闸门层单一实现 `app/factors/gate.py#assert_factors_usable(factor_ids, mode, allow_non_active, allow_retired) -> GateReport`。
3. 判定矩阵：`production` 只认 `active`；`research` 认 `active/watch`，`draft` 需 `allow_non_active=true`，`retired` 需 `allow_retired=true` 并标 `historical_only`；未登记一律 `FS02`。
4. 五个调用点写死：`/api/factors/validate`、策略 `POST/PATCH /config`、回测入口、X1 `build_target_portfolio`、`paper_auto#on_rule_events`；求值层**不 gate**（逐列热路径 + 结论一致性 + 回测/生产差异只有入口知道）。
5. 与 E1/E2 的关系：算子是算子不是因子，status 不参与；E2 三个 id 若登记为别名因子，`xs_rank_pct` / `xs_rank_market` 的 status 必须是 `watch` 或 `retired`，**不得 active**；批二验收分「数值段 + 闸门段」两段。
6. 错误码 `FS01`/`FS02`（新命名空间，与 `E0xx` / `E2xx` 不冲突）；判据 `F-A7`–`F-A9`。
7. 缓存代价：`status` 目前参与内容签名（`store.py:183-191` 节注释；`_NON_CONTENT_FIELDS` 定义在 `:189`，只排除 `version/created_at/updated_at`）→ 改状态抬版本 → 该因子**重算一次**。契约按现状登记为「可接受」，并要求重算前后数值 `max_abs_diff == 0`。

**依据**：见上 5 条 + `FactorSpec` 实测 `hasattr(spec,"status") == False`。

### R2-5 §8 新增一行 + §8.1 裁定：`rsi_14_pct` 是 base 列，不是扩算子

**新增行（v0.3 §8）**
> | D2 `rsi_14_pct`（Wilder 平滑、涨跌幅口径） | **新增模块（新增 base 列；不改 DSL 算子层）** | `registry.py#FACTOR_SPECS` 新增 `_base("rsi_14_pct", …)`；`indicators/pipeline.py` 新增一列（`ewm_mean(alpha=1/14, adjust=False)`，与 `:576-577` 同法）；`backtest/matrix.py#_MATRIX_COMPUTED_FEATURES` + `#_compute_matrix_feature` 新增分支 | `dsl.py#OPERATORS` 实测 **25** 个键（`len(OPERATORS)==25`；因子工程师文档写「26」，差 1 属计数差异），**无 `ewm`/`ewma`/`wilders`**；但 `ewm_mean` 在指标层已用于 `rsi_6/14/24`（`pipeline.py:576-577`）与 `atr_14`（`:503`）→ 不必扩算子。**不新增错误码**；若强行扩算子则需 `E018`（`E017` 已被 E2 掩码占用）。落点裁定与被否决方案见 §8.1 |
>
> | **`ewm` / Wilder 平滑算子**（引擎能力缺口，v0.3 登记） | **不改引擎：否决扩算子** | 不落 `app/factors/dsl.py#OPERATORS`（保持 **25** 键，`TS_OPERATORS` 13 / `CROSS_OPERATORS` 3 不变）；策略侧仍不能用 DSL 写 `ewm(...)`，编译期按未知算子返回 **`E002`**（判据 F-A13）；若日后改判为扩算子，则需 `TS_OPERATORS` 13→14 + 新错误码 **`E018`**（`E017` 已被 E2 掩码占用）+ 面板/矩阵两条求值路径逐位一致 | 派单把它登记为「引擎能力缺口（改引擎）」，架构裁定为**不扩**：Wilder 平滑在指标层已存在（`pipeline.py:576-577`、`:503`），`rsi_14_pct` 改走 base 列（§8.1）。故本条的真实改动性质是「新增 base 列」，不是「改算子层」；`E018` 仅预留给「改判后」的场景，**当前没有任何代码路径会返回它** |

**与原派的差异（必须让排期方看见）**：派单要求「改引擎（扩算子），写清落点和错误码」。我按架构判断定为**不动算子层**，理由与被否决方案（含代价）写在 §8.1，三行摘要：
- 扩 `ewm` 要动 `OPERATORS` 25→26、`TS_OPERATORS` 13→14、常量校验、warmup 推导、`_rolling_apply` 与矩阵逐元素两条求值路径的逐位一致、与 `E009` 的交互；只为 1 个已定死 `alpha=1/14` 的因子扩语言，扩完策略侧获得「任意 alpha」自由度，台账无法穷举口径（违反 G7）。
- T2 `lang="python"` 路线看似零代码，但 `py_expr` 的 warmup 推断按 `span=2/alpha-1=27` 给 28 根，远低于 311 → `max_abs_diff < 1e-10` 必然失败。
- Wilder 的预热必须按 `(13/14)^n < 1e-12 → n ≥ 373` 声明（1e-10 门槛需 311），**不是 28**。这是本条最容易被实现者写错的地方。
- 依据：`len(OPERATORS)==25`（实测）、`pipeline.py:576-577`（Wilder 已在指标层）、`py_expr.py:106-112`（ewm warmup 推断）、`FACTOR_GAP_SPEC` §D2（口径与容差）。

### R2-6 §2.2 / §2.3 / §2.6 / §4.4 / §6.4 / §6.7：ST 窗口与末端两条硬规则

**改动清单**

| 位置 | 原 | 新 |
| --- | --- | --- |
| §2.2 参数表 | 只有 `universe_version` | 新增 `st_unknown_windows`（默认 `(("2026-10-20","2026-10-29"),)`）+ `universe_version` 建议值改 `2` |
| §2.3 表 | 无该场景 | 新增两行：窗口内 → `null`（当日**全部** symbol）；`date > coverageEnd` → `null` |
| §2.3 表后 | 无 | 新增**注 2**（ST 数据事实与硬规则、代价、未采用的窄口径）与**注 3**（末端外推风险） |
| §2.6 | A1–A6 | 新增 `A7`（窗口不可判定）、`A8`（末端不外推） |
| §4.4 | 无该行 | 新增「`mask` 当日全 `null` → 宽度 `null`，不得回退全样本版」 |
| §6.4 | 无该行 | 新增「全部 `eligible` 为 `null` → **no-op**（订单数 0，`reason="input_unknown"`），禁止走 `empty_target` 全卖」 |
| §6.7 X1-A4 | 4 项断言 | 5 项（加「全 null → no-op」） |
| §9 | 停牌/退市数据可得性一行 | 新增 ST 数据质量、status 闸门、`rsi_14` warmup、F-A5 审核状态四行 |

**依据（独立复算，非转述）**

| 事实 | 数字 |
| --- | --- |
| ST 表规模 | `D:/TSP/data/st_history/part.parquet`：7,758 行 / 5,817 只 / `2019-01-01`–`2026-10-29`；`manifest.absencePolicy = absence_of_ST_interval_is_non_ST` |
| 2026-10-20 写入 | 当日 198 行，**全部** `st_flag=false` |
| as-of ST 家数 | 2026-10-19 = **218** → 2026-10-20 = **20** → 维持 20 至 2026-10-29 |
| 受影响的真 ST 区间 | 恰 **198** 个被这些 false 行闭合；末端仍开着 **20** 个 |
| 窗口内其余行 | 4 行（`301718.SZ` 10-22、`920296.BJ` 10-21、`920285.BJ` 10-23、`920306.BJ` 10-29），均 `false`，属新上市基线，与批量写入无关 |
| 窗口交易日 | 8 个：10-20/21/22/23/26/27/28/29（按 `kline_daily` 分区实测） |
| 末端 | 10-29 之后 **0** 行；`join_asof(backward)`（`security_status.py:64-82`）与 `searchsorted(...)-1`（`:93-101`）都会外推末值 |

## 3. 对派单证据的四处修正（结论不变，证据更精确）

这些不是「改口径」，而是把证据改成能复跑的形式；其中两处会直接影响审核方怎么验。

| # | 派单原话 | 实测 | 影响 |
| --- | --- | --- | --- |
| 1 | 「`git grep -n "unchanged" -- backend/app` 零命中」 | 当前工作区 **10 处 / 5 文件**（`store.py` 4、`position_policies.py` 2、`snapshot.py` 2、`main.py` 1、`minute_adapter.py` 1）；HEAD 上 6 处 / 4 文件。差异是 `store.py` 的 4 处为 15:35:28 新增 | 结论（HEAD 无 F-A5 实现）仍成立；但「零命中」已过期，见 R2-3 |
| 2 | 「`get_factor("uf_vol60")` 返回 status 为 None」 | `FactorSpec` **根本没有 `status` 字段**（21 字段清单无它），`hasattr(spec,"status") == False` | 结论相同（运行时无闸门），但写法更硬：不是「值为 None」，是「字段不存在、任何读取都会被 `AttributeError` 或 `getattr(...,None)` 吃掉」 |
| 3 | 「`app/factors/dsl.py#OPERATORS` 现有 26 个算子」 | **25** 个（`len(OPERATORS)==25`；`TS_OPERATORS` 13、`CROSS_OPERATORS` 3） | 不改变「无 ewm」的结论；但契约里若写 26，实现者会以为漏看一个 |
| 4 | 「`pullback_ma20_bounce.py:75` 以 `x/100` 与阈值比较」 | 该行是 `change_pct > 0`（**单位无关**，不涉及 /100）；真正 `/100` 的是 `oversold_reversal.py:77`、`strong_open.py:81`、`active_limit_gene.py:72`、`breakout_new_high_60d.py:67`、`high_turnover_surge.py:73`、`limit_up_momentum.py:61`、`ma_convergence_breakout.py:89`；`broken_board_recovery.py:75-76` 直接写小数 `0.03` | 结论不变（因子路径是小数），证据列更准 |

## 4. 契约外发现（架构侧自查，已写入契约或已登记）

1. **X1 在「全 null」时不能清仓**（已写入 §6.4 / §6.7 X1-A4）。v0.2 §6.4 的原规则是「`picked` 空 → 卖出全部（`empty_target`）」。若 ST 窗口内 `eligible` 全为 `null`，按原规则会**因为数据缺失而清仓**——把「ST 表被污染」翻译成「策略判定空仓」。新增区分：`empty_target`（可判定的空）vs `input_unknown`（不可判定，no-op）。这是 R2-6 的直接下游，不补这条，ST 窗口规则在 X1 上会变成反向操作。
2. **ST 表末端不外推**（已写入 §2.3 注 3）。`join_asof(backward)` 与 `searchsorted` 都只看前缀，因此今天（2026-11-07）生产侧实际用的是 10-29 的 20 只 ST —— 与真实 ~218 只差 198 只。契约要求 `> coverageEnd` 一律 `null` 并报 `st_history_stale`。**副作用必须让排期方知道**：数据修好前，生产侧不出新信号。这是 fail-closed 的正确方向，但会表现为「策略今天没选到票」，需要运维可见性，不能静默。
3. **因子工程师两份文件对 `rsi_14_pct` 结论相反**：`FACTOR_ENTRY_RULE_20261107.md:215`、`:280` 明确写「不需要新算子，注册成 base 因子即可，不必让策略侧写 ewm」；而 `F_CLASS_REGISTRATION_20261107.md:224` 写「不是纯表达式因子，属引擎能力缺口（扩算子）」。§8.1 采信前者，并把后者列为被否决方案（附代价）。请开发经理在排期时以此为准，避免批二按「扩算子」估工。
4. **既有 `rsi_14` 的 warmup 未声明**（`registry.py:108` 的 `_base(...)` 未传 `warmup_bars`，默认 1）。与 §8.1 的 373 推导是同一数值问题，**已存在于 S04 现用因子**。本条只登记，不扩大范围（改它等于改既有因子口径/增量行为，需另立）。

## 5. 未确证 / 未覆盖（不用「大概」圆过去）

| 项 | 状态 |
| --- | --- |
| `rsi_14` 与现在研究侧 `rsi14` 的逐值差异 | **未确证**：沿用 D2 已记录的「平均差 0.892 个 RSI 点」基线，本次未复算；§8.1 的 F-A10 仍以 1e-10 为目标 |
| 矩阵路径新增 base 列后的既有回归 | **未确证**：仓库没有「矩阵 vs 面板」逐列一致的现成测试基线，F-A11 需实现方自建 |
| `status` 闸门落地后的性能影响 | **未确证**：闸门在入口（每次策略/回测一次），预期可忽略，但未测 |
| `input_unknown` 在调度器层的表现 | **未确证**：只定义了 X1 的返回语义，未查调度器（`paper_auto` 触发链）会不会把「无计划」当失败重试 |
| 2026-10-20 那 198 行是否**唯一**异常写入 | **未确证**：这正是 §2.3 注 2 拒绝「只 null 198 只」窄口径的原因；需行情数据工程师书面确认 |
| ST 数据修复方案与时限 | 不在本部门；属行情数据工程师 |
| `status` 现存 `draft` 的历史因子清单 | **未确证**：没有盘点现有 `custom_factors/*.json` 里各 status 的分布，闸门一旦启用，可能立刻拦住既有策略（需在批二前盘点，否则上线即停产） |

## 6. 未改动清单（边界证明）

| 范围 | 状态 |
| --- | --- |
| `docs/research/**`（含 `caliber-decisions-20261107.md`） | **未改**（只读引用） |
| `docs/factors/**`（台账、缺口规格、准入规约、证据 JSON） | **未改**（只读引用） |
| `backend/**` 代码 | **未改**（只读排查）。`git status` 里的 `M backend/app/api/factors.py`、`M backend/app/factors/store.py` 是系统开发工程师 15:35:28 的批一b 写入，早于本次修订且非我所为 |
| 策略口径 / 因子定义 | **未改**：本文件不含任何新口径裁定；`rsi_14_pct` 的算法、容差、`replaced_by` 全部引自 D2/缺口规格 |
| git 操作 | **未提交、未 add、未建分支** |
| 部署 / 重启 / 真实交易 | **未做** |

## 7. 给下游的两条执行提示（不是验收结论）

1. **批二（E1/E2）开工前**先做 §7.7 的 `status` 盘点（本文 §5 最后一行），否则闸门会撞上既有 `draft` 因子。
2. **批一b 的交付**请按 §7.6 `F-A5` 的新表述验收：靶值三条（version 不变 / `unchanged=true` / 文件字节与 mtime 不变）可直接用现工作区代码复跑；「HEAD 无此实现」不是缺陷，是提交状态问题，由开发经理决定何时入库。


## 8. 收尾修订（同批追加，改后自校验）

本节四处在 §2–§7 定稿后追加：两处补派单要求与我方内部一致性的缺失（S1/S2），两处修证据自洽（S3 自校验定义、S4 行号引用）；不改任何口径、不改判据阈值、不改代码。

### S1 §2.2 `st_flag` 输入行：类型与空值口径对齐 §2.3

**原句**（v0.3 中途）：

> | `st_flag` | int 0/1 | 历史 ST 表 as-of 合并（`app/tickflow/security_status.py#attach_st_history`） | 是 | 缺失走 §2.4 |

**新句**：

> | `st_flag` | int 0/1 **或 null** | 历史 ST 表 as-of 合并（`app/tickflow/security_status.py#attach_st_history`） | 否（缺失有显式策略，不得填默认值） | 缺失 / 超出覆盖期末端 / 落在 `st_unknown_windows` 时一律按 §2.3 的三态处理：输出 `null`，**不**回退成「非 ST」 |

**依据**：① `st_flag` 经 as-of 合并后**可以为 null**（末端无行、窗口内被强制置 null、该 symbol 从无 ST 记录三种情形，见 §2.3 三行）；写 `int 0/1` 会让实现者按非空整数落 schema，把 null 变成 0。② 原文「缺失走 §2.4」是**错引用**：§2.4 是「幂等与确定性」，空值语义在 §2.3。③ 参数 `st_flag_missing_policy` / `st_unknown_windows` 已在 §2.2 参数表，输入行必须与之呼应。

### S2 §8 新增 `ewm` / Wilder 平滑算子行（派单第 5 条要求的表行）

**原句**：§8 无此能力行（只有 D2 `rsi_14_pct` 一行，改动性质写作「新增模块（新增 base 列；不改 DSL 算子层）」——**结论对，但没有给排期方一个以「引擎能力」命名的可查账行**）。

**新句**：

> | **`ewm` / Wilder 平滑算子**（引擎能力缺口，v0.3 登记） | **不改引擎：否决扩算子** | 不落 `app/factors/dsl.py#OPERATORS`（保持 **25** 键，`TS_OPERATORS` 13 / `CROSS_OPERATORS` 3 不变）；策略侧仍不能用 DSL 写 `ewm(...)`，编译期按未知算子返回 **`E002`**（判据 F-A13）；若日后改判为扩算子，则需 `TS_OPERATORS` 13→14 + 新错误码 **`E018`**（`E017` 已被 E2 掩码占用）+ 面板/矩阵两条求值路径逐位一致 | 派单把它登记为「引擎能力缺口（改引擎）」，架构裁定为**不扩**：Wilder 平滑在指标层已存在（`pipeline.py:576-577`、`:503`），`rsi_14_pct` 改走 base 列（§8.1）。故本条的真实改动性质是「新增 base 列」，不是「改算子层」；`E018` 仅预留给「改判后」的场景，**当前没有任何代码路径会返回它** |

**依据**：`len(OPERATORS)==25`、`TS_OPERATORS` 13、`CROSS_OPERATORS` 3（本次重跑 `backend/.venv` 确认，输出见下方复跑命令）；`pipeline.py:576-577` / `:503` 已有 `ewm_mean`；§8.1 的裁定与 F-A13 的断言（`ewm(...)` 仍返回 `E002`）。

复跑命令（两条判据的来源）：

```
cd backend && ./.venv/Scripts/python.exe -c "from app.factors.dsl import OPERATORS,TS_OPERATORS,CROSS_OPERATORS;print(len(OPERATORS),len(TS_OPERATORS),len(CROSS_OPERATORS))"
# → 25 13 3
```

**与派单的差异（排期方必须看见）**：派单写「属引擎能力缺口，改引擎（扩算子）」。架构裁定为**不扩**：Wilder 平滑在指标层已存在，`rsi_14_pct` 走 base 列（§8.1），故本条的真实改动量是「新增一列」而不是「扩语言」。若派单坚持扩算子，需按 §8.1「被否决的方案」一栏的代价重估（`TS_OPERATORS` 13→14、常量校验、warmup 推导、两条求值路径逐位一致、与 `E009` 的交互、新错误码 `E018`）。

### S3 footer 自校验口径：**最终定为字节前缀 `head -c N`**（撤回同批「必须改 `head -n`」的裁定）

**原句（v0.3 中途两次口径）**：footer 先写 `head -c 88103`，随后改为 `head -n 913`（理由见下「旧依据」，该理由不成立）。

**新句（现行，唯一口径）**：

> 本文件正文 sha256：`b082d902…f9bfef`（校验：`head -c 89350 "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md" | sha256sum`）· 行数 914 · 生成 2026-11-07 v0.3 · 冻结 2026-11-07 15:51（Asia/Shanghai）

**旧依据（不成立，已撤回）**：「`head -c N` 的截止点与 footer 自身长度耦合——footer 里写着 N，改 footer 一个字就会移动正文边界」。实测反证：正文边界由 footer 之前的 `
---

` 分隔符固定，`N` 是分隔符之前的字节数，**与 footer 文字长度无关**。本次只重写 footer（换口径 + 加冻结标记）、正文一字未改，`head -c 89350` 的输出仍是 `b082d902…f9bfef`；把 footer 换成任意文字重跑同一命令，输出不变。故「改 footer 后正文哈希自动失效」不成立。

**为什么选字节口径**：① 派发方（策略经理）的 done_when 明确要求「`head -c <字节数> 文件 | sha256sum` = 正文 sha」；② 字节口径在正文增删行时仍自洽（今天正文从 778 → 914 行，`head -n` 的截止行号每次都要跟着改）。

**代价（保留提醒）**：读者必须严格按记录的字节数截断，不能用「倒数第二行」之类的手工近似；`行数 914` 单列保留为**辅助核对字段，不承担校验职责**。

**作废清单**：`head -n 913` + `c70d4493…332c71`（89,498 B 态）、`head -n 913` + `d8ca6de5…539f1b1`（89,709 B 态）两组值与口径一并作废，现行绑定见 §1。

### S4 行号引用校正（6 处引用 + 2 个状态数字）

**起因**：定稿后逐条回读实现文件，发现 v0.3 正文里有 6 处 `文件:行` 引用落在错误的行上；引用错不会改变任何判断，但会让审核方「照行号核对」时对不上，属必须修的证据质量问题。

| 位置 | 原引用 | 现引用 | 实测 |
| --- | --- | --- | --- |
| §7.2 `id` 字段 | `store.py:21` | `store.py:22` | `CUSTOM_ID_PATTERN = re.compile(r"^uf_[a-z0-9_]{1,40}$")` 在第 22 行（第 21 行是空行） |
| §7.2 `status` 行 / §7.7.1 第 2 条 | `store.py:87`、`:103`、`:155` | `store.py:94`、`:110`、`:165` | 三处 `stability="stable" if status == "active" else "experimental"` |
| §7.2 `status` 行 / §7.7.1 第 2 条 | `store.py:41-47`（取值校验） | `store.py:66-68` | `status = str(definition.get("status","draft"))`；`if status not in STATUSES: raise` |
| §7.7.1 第 4 条 | `api/factors.py:510-533` | `api/factors.py:510-531` | 装饰器 510、函数体 511–531（`return {"ok": True, "id": …, "status": req.status}`） |
| §7.6 F-A5 / §9 | `store.py:209-250` | `store.py:207-257` | `content_signature` 207、`is_same_content` 217、`upsert_definition` 222–257 |
| §7.6 F-A5 / §9 | `api/factors.py:333-362` | `api/factors.py:333-360` | `create_custom_factor` 333–360（返回 `store.upsert_definition(...)`，`unchanged` 由 store 返回，API 文件里没有该字面量） |

**两个状态数字校正**：

| 项 | 原写 | 实测 |
| --- | --- | --- |
| HEAD 提交 | `96ba73d0` | **`65c6e42f`**（`2026-11-07 12:56:05 +0800`）——原值取自别处的提交号，属错引 |
| 批一b 写入 mtime | `15:28:25` | **`15:35:28`**（`api/factors.py` 与 `store.py` 同）——批一b 在派单之后又写过一次，原值已过期 |

**连带修正**：`store.py` 的 diffstat 由「+83/−0」改为「**+91/−1**」（`git diff --numstat` 实测）；`grep unchanged` 的四处由 `:219/:222/:232/:250` 校正为 `:226/:229/:239/:257`。**结论未变**：HEAD 无 F-A5 实现（`git show HEAD:backend/app/factors/store.py` 内 `unchanged` 命中数 = 0），工作区有、未提交、未经独立审核。
