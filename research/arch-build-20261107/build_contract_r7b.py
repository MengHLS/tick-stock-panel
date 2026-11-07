# -*- coding: utf-8 -*-
"""v0.7 落盘构建器：v0.6 逐字节为底 + R7 追加块 + 本批四处并入（仍是同一版 v0.7）。

只读 v0.6，只写 v0.7。不改 v0.3/v0.4/v0.5/v0.6。
锚点全部做唯一性断言，任一漂移即退出（不静默改行）。
"""
from __future__ import annotations
import argparse, hashlib, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_contract_r7 as R7

ROOT = R7.ROOT
V06 = R7.V06
OUT_NAME = "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md"
MARK = R7.MARK
crlf = R7.crlf
sha = R7.sha

# ---------------------------------------------------------------- 并入 ②：§4.6.1
BLK_461 = crlf("""#### 4.6.1 `B1`/`B2` 的 null 日减法（v0.7 并入；原表述在这批数据上不可达）

原 `B1` 写「1,779 个交易日 `max_abs_diff < 1e-12`」，`B2` 写「`month_end` 日通过率 **53.4%**」。两者都取自研究侧样本（`EVAL_START=2019-07-01` … `EVAL_END=2026-10-30`，`n_days=1,779`，`docs/factors/evidence/xs_rank_stats.json#market_breadth`）。**该样本必然包含生产侧输出 `null` 的日子**，故「逐位一致」不可能覆盖 1,779 天：

| 项 | 实测（2026-11-07 17:4x 本机复跑，可独立复现） |
| --- | --- |
| 研究侧逐日宽度复现 | `n_days = 1779`、均值 `0.5407417151801761` —— 与 `xs_rank_stats.json#market_breadth.mean_research` **逐位相同**（研究侧值本身没有错） |
| 生产侧必为 `null` 的日子（落在评估窗内） | **9 天**：`2026-10-20`…`2026-10-29`（8 天，`st_unknown_windows`，§2.3 注 2）＋ `2026-10-30`（1 天，`date > coverageEnd`，§2.3 注 3） |
| 两侧均非 `null` 的子集 | **1,770** 天；该子集研究侧均值 **`0.5422520639953171`** |
| 这 9 天研究侧宽度 | 全部远低于 0.5 阈值：min **0.184562**（`2026-10-30`）/ max **0.303326**（`2026-10-20`）/ 均值 0.243706 |
| 月末 | 研究侧 `month_end` 共 **88** 个；其中 `2026-10-30` 恰是月末且在生产侧为 `null` |

**判定（两项各自二选一，本契约取「减法式」）**

- `B1`：判据改为「**两侧均非 `null` 的交易日**逐位 `max_abs_diff < 1e-12`」，靶值 = 该子集 `n_days = 1,770`、均值 `0.542252`；同时**必须单列 null 日清单**（日期 + 生产侧 `null` 原因码 + 研究侧当日值），清单条数必须等于「`st_unknown_windows` ∩ 评估窗」＋「`date > coverageEnd` ∩ 评估窗」。
- `B2`：分母改为「两侧均非 `null` 的月末」= **87**，通过 **47**，通过率 **`0.5402298850574713`**；**`null` 月末不得按 fail 计入分母**（那是把「数据不可用」记成「策略判定未通过」，方向错）。替代口径（88 分母、`null` 记 fail）= 47/88 = `0.534091` 仅用于**复现旧值**，不得作判据。
- **不改走 `treat_non_st` 对账的理由**：`treat_non_st` 只解 §2.3 注 2 那 8 天的 ST 缺失，**解不了** `date > coverageEnd` 的 1 天（注 3 是「无数据」不是「ST 未知」）；且它会把生产口径改成研究口径，`B3` 视图一致与 `F-A11d` 权威判定都会失去意义。代价写清：减法式让 `B1`/`B2` 的靶值与「全期 1,779 天」解耦，**评估窗一延长靶值就变**，故 `n_days`/`n_month_end`/两个均值必须由判据脚本**现算并打印**，不得硬编码。
- 判据编号沿用 `B1`/`B2`（不新增 `B7`/`B8`）：语义从「全期一致」收窄为「可比集一致」，收窄方向是**更严**（每个可比日仍要 `<1e-12`），故不构成放宽。""")

# ---------------------------------------------------------------- 并入 ③：§2.6 A7
A7_NEW = crlf("""| A7 | ST 窗口不可判定（**窗口终点 = 数据末端，不是固定的 8 天**） | 自 `2026-10-20` 起至**数据末端**（当前 `2026-11-06`）共 **14** 个交易日：断言 `count(in_universe ∈ {0.0, 1.0}) == 0`、`universe_unknown_count == 当日有 bar 的行数`；同区间内 E1 输出 `null`、E2 `xs_rank_pool` 输出 `null`、X1 不产生订单（§6.4）。**14 = 8 + 6**：8 天 = `st_unknown_windows` 默认 `2026-10-20`…`2026-10-29`（§2.3 注 2）；6 天 = `date > coverageEnd`（当前 `coverageEnd = 2026-10-29`，即 `10-30`/`11-02`/`11-03`/`11-04`/`11-05`/`11-06`，§2.3 注 3）。**该计数由两条规则现算，禁止硬编码 8 或 14**：ST 表修复后 `coverageEnd` 前移，第二个集合自动收缩。证据：`docs/factors/E3_DATA_AVAILABILITY_20261107.md`（行情数据工程师 2026-11-07 实跑） |""")

A7_EVID = crlf("""**注 2b（窗口终点的实测证据，v0.7 追加；此前写「8 个交易日」是只看了注 2 那一段）**

`docs/factors/E3_DATA_AVAILABILITY_20261107.md`（2026-11-07，行情数据工程师实跑）给出三条可复核事实，本文据此把 A7 的窗口终点从「`2026-10-29` 固定的 8 天」改为「至数据末端、当前 14 天」：

1. `flag_date = 2026-10-20` 一次性写入 **198 行 `st_flag = False`**；此后到 `2026-10-29` 只有 **4 条 `False`、0 条 `True`**；窗口内 `st_flag = True` 记录 **0 条** → 无法反映真实 ST 变动。
2. 按 as-of 复算，末端 `st_flag = True` 家数由 **218 家降到 20 家**（掉 198 只），并**维持到 `2026-11-06`**（该证据文件的最后一个交易日），不只到 `10-29`。
3. 交易日轴 = `kline_daily` 全部 distinct `date` = **2,141 天（`2018-01-08`…`2026-11-06`）**，评估窗 `2019-07-01`…`2026-10-30` 内 **1,779 天**。本架构师用 `D:/TSP/data/kline_daily_enriched` 的 2,141 个分区独立复算：`2026-10-20`…`2026-11-06` 恰为 **14** 个交易日（`10-20/21/22/23/26/27/28/29/30` + `11-02/03/04/05/06`），`2026-10-20`…`2026-10-29` 为 **8** 个。

→ 代价（不变，只是数字变准）：窗口从 8 天扩到 14 天，多出 6 个交易日整池不可判定 → E1 宽度 `null`、E2 `xs_rank_pool` `null`、X1 无新目标。这仍是 G8 的正确失败方向。若按旧文本只判 8 天，`10-30`…`11-06` 的「198 只真 ST 被当非 ST」会**通过**判据（偏差 198 只/日 × 6 日 = 1,188 标的日被漏检）。""")

# ---------------------------------------------------------------- 并入 ④：§7.15
BLK_715 = crlf("""### 7.15 canonical id 表（v0.7 新增；契约正文规范，权威登记在 `ARCH_DECISION_FACTOR_ID_CANONICAL_20261107.md` §2.1）

本节把 id 裁定写成**契约正文可引用的一张表**，策略规格、实现与审核一律按本表取 id，不再各自对照决策文件。登记编号 `ID-CANON-1`（沿用决策文件 §3，不新开号）。

**7.15.1 14 个口径逐行（口径数 = 8 组双 id + 6 个 pack 单侧件）**

| # | 口径（研究名） | `canonical_id` | `alias`（若有） | canonical `strategy_usable` | alias `strategy_usable` | 载体 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `vol60` | `uf_vol60` | `vol60` | `true` | `false` | store（canonical）+ pack（alias） |
| 2 | `ma120` | `uf_ma120` | `ma120` | `true` | `false` | store + pack |
| 3 | `ma200` | `uf_ma200` | `ma200` | `true` | `false` | store + pack |
| 4 | `prior_high_20` | `uf_prior_high_20` | `prior_high_20` | `true` | `false` | store + pack |
| 5 | `prior_high_55` | `uf_prior_high_55` | `prior_high_55` | `true` | `false` | store + pack |
| 6 | `prior_high_250` | `uf_prior_high_250` | `prior_high_250` | `true` | `false` | store + pack |
| 7 | `prior_low_10` | `uf_prior_low_10` | `prior_low_10` | `true` | `false` | store + pack |
| 8 | `prior_vol_20` | `uf_prior_vol_20` | `prior_vol_20` | `true` | `false` | store + pack |
| 9 | `ma20` | `ma20` | — | `true` | —（无 alias） | pack（唯一载体） |
| 10 | `ma60` | `ma60` | — | `true` | —（无 alias） | pack（唯一载体） |
| 11 | `sd20` | `sd20` | — | `true` | —（无 alias） | pack（唯一载体） |
| 12 | `boll_lower` | `boll_lower` | — | `true` | —（无 alias） | pack（唯一载体） |
| 13 | `boll_upper` | `boll_upper` | — | `true` | —（无 alias） | pack（唯一载体） |
| 14 | `prior_amount_20` | `prior_amount_20` | — | `true` | —（无 alias，canonical = 研究原名，例外见决策文件 §2.3） | pack（唯一载体） |

**读表规则（4 条，机械可判）**

1. 第 1–8 行：`canonical_id` 一律 `uf_*`；研究原名是 **alias**，标 `alias_of` + `strategy_usable = false`，生产入口 `FS03` 拒（§7.8.2 A-2）。**禁止用 `replaced_by` 表达别名**（`replaced_by` 只表跨口径取代，§7.8.2 A-1）。
2. 第 9–14 行：pack 是**唯一载体**，`canonical_id` 就是研究原名，**不得**为它们新登记 `uf_*`（否则立刻制造新的双 id，决策文件 §2.3 已就 `prior_amount_20` 明文禁止）。
3. 一个口径**恰好一行**、一个 `canonical_id`。表里出现同一口径两行、或同一 `canonical_id` 挂两个口径，即违反 §7.5-3 全局唯一性。
4. `strategy_usable` 在**每个口径上只能有一个 `true`**。第 1–8 行的 alias 列必须是 `false`，不是「未填」。

**7.15.2 硬约束 ①：`vol60` 两式差 1 ULP，禁止写「逐位相同」**

- 两式：pack／契约 §7.1 原文 `ts_std((close - ts_delay(close, 1)) / ts_delay(close, 1), 60)` 与 store 侧 `ts_std(close / ts_delay(close, 1) - 1, 60)`。
- 实测差 `max_abs_diff = 1.1102230246251565e-16`（`F_CLASS_PARITY_20261107.json#factor_parity.uf_vol60`，`n_both_nonnull = 5,469,335`，`n_nonzero_diff = 4,214,876`，`n_over_tol = 0`）。
- **表述规范**：一律写「按 `F-A3` 的 `max_abs_diff < 1e-12` 判」，**不得**写「逐位相同」、**不得**把 `1.11e-16`／`2.22e-16` 写成门槛（§7.8 A-4 已定；把某次实测的 ULP 当门槛会让「同公式换个求和顺序」的正确实现判失败）。
- 「逐位相同」只在 `max_abs_diff == 0` 成立的口径上用（如 `ma120`/`ma200` 文本逐字相同、5 组 `prior_*` 实测 `0.0`）。

**7.15.3 硬约束 ②：登记元数据缺口（P2，不阻塞 B2）**

本架构师 2026-11-07 17:4x 在 `backend/.venv` 下用 `store.load_into_registry(Path("D:/TSP/data"))`（注册表 192 → **207**，装载 15 个盘上定义）实测 14 个 id 的元数据，**结论与派单时的转述不同，按实测写**：

| 事实 | 实测 | 含义 |
| --- | --- | --- |
| **14 只全部**无 `status` | `FactorSpec` 数据类**没有 `status` 字段**（字段表 21 项，无 status）；store 侧 `status` 只活在盘上 JSON（15 个文件都是 `"status": "draft"`），pack 侧从未有 | 按 §7.7.2，provider 注册且无 `status` 一律 `FS01`（按 `draft` 处理）→ 这 14 只在 `production` **全部被拒**，不是「只有 6 只缺」 |
| **6 只 pack 单侧件**的 `version`/`unit`/`scale_free` **已齐全** | `ma20/ma60/sd20/boll_lower/boll_upper` → `unit = 'currency'`、`scale_free = False`；`prior_amount_20` → `unit = 'currency'`；`prior_vol_20` → `unit = 'count'`；`version` 全为 `1` | 派单所述「6 只缺 `status`/`version`/`unit`/`scale_free`」中，后三项**不成立**，只有 `status` 成立 |
| **8 只 `uf_*`** 的 `unit`/`scale_free` **未随盘落库** | 盘上 JSON 键集固定 11 个（`created_at`/`description`/`direction`/`formula`/`group`/`id`/`kind`/`label`/`status`/`updated_at`/`version`），**无 `unit`/`scale_free`**；registry 因此取数据类默认 → 8 只全是 `unit = 'none'`、`scale_free = True`（`uf_ma120` 应为价格类 `scale_free = False`，实测 `True`） | 真正缺元数据的是 **canonical 侧**，与派单方向相反；台账 8/8 的 `unit` 只存在于台账，未进注册定义 |

- **登记 P2**（不阻塞 B2，不进本批验收）：①为 `FactorSpec` 增 `status`（或为 provider 注册路径显式给 `status`），使 14 只可从 `draft` 走 §7.11 的 V3 闸门升 `active`；②盘上定义 schema 增 `unit`/`scale_free` 两键并回填 8 只（值取台账，不取数据类默认）。
- **为什么写进契约而不是只留决策文件**：这两项决定「14 只在生产能不能跑」，属准入事实，不是 id 命名的附属说明。""")

# ---------------------------------------------------------------- 修订行
D_ROW_V2 = crlf("""| v0.7（裁定） | 2026-11-07 | **R7（只追加；不改冻结 v0.3、不改 v0.4/v0.5/v0.6 正文）**：①§1 插入 **`G2.1`**（`entry_fill`/`exit_fill`/`entry_price_basis` 必须显式传入，缺省即 `FS08`；3 条例外显式打标；判据 `F-A40`）；②新增 **§7.13** 矩阵路径能力清单与准入前置（6/14，**点名 8 个未同步因子**：`sd20`/`prior_high_20`/`prior_low_10`/`prior_high_55`/`prior_vol_20`/`prior_high_250`/`vol60`/`prior_amount_20`；准入 `FS10`；判据 `F-A41`）；③新增 **§7.14** 把 `F-A11` 的 `1e-10` 绝对容差替换为 `F-A11a`–`F-A11d` 分层判据（结构零容忍 / 相对 `2^-23` / 决策等价 / 面板 `float64` 为唯一权威）。本批并入四处（**同一版 v0.7，不另开 R8**）：④标题行版本号 v0.5 → v0.7（v0.6 追加时漏同步 H1）；⑤**新增 §4.6.1** 并改写 `B1`/`B2`——判据收窄为「两侧均非 `null` 的交易日/月末」（`n_days` 1,779 → **1,770**、均值 0.540742 → **0.542252**；`n_month_end` 88 → **87**、通过率 53.4% → **0.540230**），null 日单列清单 9 天，否决 `treat_non_st` 对账路线；⑥**§2.6 `A7` 重写 + 注 2b**——窗口终点由「固定的 8 天」改为「至数据末端、当前 **14** 天（8 + 6，现算不硬编码）」，证据 `docs/factors/E3_DATA_AVAILABILITY_20261107.md`；⑦**新增 §7.15** canonical id 表（14 个口径逐行 + 读表规则 4 条 + `vol60` 两式 `1.11e-16` 的表述硬约束 + 登记元数据缺口 P2：14 只全无 `status`、8 只 `uf_*` 的 `unit`/`scale_free` 未落库，6 只 pack 单侧件该三项**已齐全**）。逐条原句、新句与实测见 `docs/architecture/CONTRACT_REVISION_R7_20261107.md` | 开发经理 G-A2 开门条件（D5）+ B0b 交付范围（矩阵路径点名）+ 开发经理 17:33 落盘决定与四处并入（策略经理 §4.6 表述洞、行情数据工程师 ST 实跑证据、`ID-CANON-1` 正文规范）+ 架构师本机实测（14 个 id 矩阵解析、1.75M 行 `float32` 量化、语义错反例、逐日宽度复算、15 个盘上定义装载、2,141 天交易日轴）|""")

C_ROW_V2 = crlf("""| **R7（D5 / 矩阵路径点名 / `F-A11` 分层判据 / §4.6.1 / `A7` 14 日 / §7.15 canonical 表）** | 见 `docs/architecture/CONTRACT_REVISION_R7_20261107.md`：§1 新增 `G2.1`（`FS08`，`F-A40`）；新增 §7.13（矩阵 6/14，点名 8 个，`FS10`，`F-A41`）；新增 §7.14（`F-A11` → `F-A11a`–`F-A11d`，权威 = 面板 `float64`）；**`B1`/`B2` 收窄为可比集**（§4.6.1）；**`A7` 窗口至数据末端 14 天**（注 2b）；**§7.15 canonical id 表（14 行）**。条款级新增 + 1 条判据替换 + 2 条判据收窄 + 1 条判据窗口修正；**收窄方向均为更严，无放宽** |""")

# ---------------------------------------------------------------- footer
E_TPL = (
    "本文件正文 sha256：`@BODY_SHA@`（校验：`head -c @BODY_LEN@ \"@NAME@\" | sha256sum`）· "
    "正文 `@BODY_LEN@ B` · 行数 `@LINES@` · 版本 **v0.7（2026-11-07 R7 裁定，未冻结）**· "
    "冻结四元组（size / lines / body-prefix / full sha）见 `docs/architecture/CONTRACT_REVISION_R7_20261107.md` §7（不写进正文，避免自指）· "
    "生成 2026-11-07 v0.7 = **v0.6 逐字节为底** + R7：§1 新增 `G2.1` / 新增 §7.13 矩阵路径能力清单与准入前置 / 新增 §7.14 `F-A11` 分层判据 / "
    "**本批并入四处**：标题版本号 v0.5→v0.7 / 新增 §4.6.1 并改写 `B1`、`B2` / `§2.6 A7` 重写 + 注 2b（14 天）/ 新增 §7.15 canonical id 表 / "
    "§8.1 `F-A11` 行替换 / 修订记录与 §9 各 +1 行 · "
    "**v0.4（`FACTOR_ENGINE_CONTRACTS_20261107.md`，128,007 B / 1,226 行 / 正文 `head -c 127043` → `71708877…d16bc` / 全文 `5bd81a74…c5531`）仍为 `F-A5` 绑定对象；"
    "v0.5（138,729 B / 1,298 行 / 正文 `head -c 137598` → `082d26fa…af7fae` / 全文 `c7740508…c4a21a`）为 `F-A30`–`F-A33` 绑定对象；"
    "v0.6（162,361 B / 1,454 行 / 正文 `head -c 160819` → `e3a4db17…2576ec` / 全文 `946a1d86…616810`）为清单 v2（`F-A34`–`F-A39`）绑定对象，"
    "自 v0.7 落盘起降为**历史版本**（文件保留、不删，引用状态改「已被 v0.7 取代」，其 `F-A34`–`F-A39` 判定对象不变）** · "
    "v0.3 冻结态（89,833 B / 914 行 / 全文 `5eb97724…565903`）逐字节归档于 `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`"
)


def _one(lines, needle):
    hits = [i for i, ln in enumerate(lines) if needle in ln]
    if len(hits) != 1:
        sys.exit("锚点不唯一/缺失: %r -> %r" % (needle, hits))
    return hits[0]


B1_ANCHOR = "| B1 | 逐日一致 |"
B2_ANCHOR = "| B2 | 月末闸门 |"
B6_ANCHOR = "| B6 | warmup 声明 |"
A7_ANCHOR = "| A7 | ST 窗口不可判定 |"
NOTE2_END = "本契约不采用，因为本部门无法自证「唯一」，且名单会随数据修订变化。"
# 注 2 的代价行原写死「8 个交易日」，与 A7 的 14 天冲突；两处锚点修正（v0.7 内，不另开版本）
NOTE2_COST_ANCHOR = "窗口 8 个交易日内整池不可判定"
NOTE2_COST_NEW = crlf("""→ 代价（写清）：`st_unknown_windows`（默认 **8** 个交易日：`2026-10-20`…`2026-10-29`）**＋** `date > coverageEnd` 的末端日子（当前 **6** 个：`10-30`…`11-06`），**合计 14 个交易日**内整池不可判定 → E1 宽度为 `null`、E2 `xs_rank_pool` 为 `null`（池空）、X1 无新目标（见 §6.4 新增行）。**该合计必须现算、禁止硬编码 8 或 14**（ST 表修复后 `coverageEnd` 前移，第二个集合自动收缩）；见注 2b 与 §2.6 `A7`。这是 G8 的正确失败方向，不是缺陷。""").rstrip("\r\n")
NOTE2_WIN_ANCHOR = "ST 表在该窗口被批量覆写，口径不可判定（注 2）"
NOTE2_WIN_OLD = "ST 表在该窗口被批量覆写，口径不可判定（注 2）；按 G3 三态，`in_universe` 相应位置必须是 `null` |"
NOTE2_WIN_NEW = "ST 表在该窗口被批量覆写，口径不可判定（注 2）；按 G3 三态，`in_universe` 相应位置必须是 `null`。**本行只定义该参数自身的默认区间（8 天）；`date > coverageEnd` 的末端日子另由下一行规则覆盖，两者合计当前 14 天，见注 2b 与 §2.6 `A7`** |"


def merge(raw: str, name: str):
    idx = raw.index(MARK)
    body = raw[:idx]
    lines = body.split("\r\n")
    if lines[0] != R7.H1_OLD:
        sys.exit("H1 不是预期值: %r" % lines[0])
    lines[0] = R7.H1_NEW

    # ② §4.6 B1/B2 改写 + 新增 §4.6.1
    i = _one(lines, B1_ANCHOR)
    lines[i] = crlf("""| B1 | 逐日一致（**仅两侧均非 `null` 的交易日**） | 见 §4.6.1：子集 `n_days = 1,770`，逐日 `max_abs_diff < 1e-12`，该子集研究侧均值 **0.542252**；生产 `null` 日单列清单（当前 9 天）。原「1,779 日 / 0.540742」是**含 `null` 日**的旧记录，**不作判据** |""").rstrip("\r\n")
    j = _one(lines, B2_ANCHOR)
    lines[j] = crlf("""| B2 | 月末闸门（**仅两侧均非 `null` 的月末**） | 见 §4.6.1：`n_month_end = 87`，`breadth ≥ 0.5` 通过 **47**，通过率 **0.540230**；`null` 月末（当前 `2026-10-30`）进 `null` 清单、**不按 fail 计入分母**。替代口径（88 分母、`null` 记 fail）47/88 = `0.534091` 仅用于复现旧值 |""").rstrip("\r\n")
    k = _one(lines, B6_ANCHOR)
    lines[k + 1:k + 1] = [""] + BLK_461.rstrip("\r\n").split("\r\n") + [""]

    # ③ §2.6 A7 重写 + 注 2b
    m = _one(lines, A7_ANCHOR)
    lines[m] = A7_NEW.rstrip("\r\n")
    n = _one(lines, NOTE2_END)
    lines[n + 1:n + 1] = [""] + A7_EVID.rstrip("\r\n").split("\r\n")

    # ③b 注 2 两处与新 A7 对齐（原写死 8 天，会被照抄成排期）
    p = _one(lines, NOTE2_COST_ANCHOR)
    lines[p] = NOTE2_COST_NEW
    q = _one(lines, NOTE2_WIN_ANCHOR)
    if not lines[q].rstrip("\r\n").endswith(NOTE2_WIN_OLD):
        sys.exit("注 2 窗口行不是预期值: %r" % lines[q][-80:])
    lines[q] = lines[q].rstrip("\r\n")[: -len(NOTE2_WIN_OLD)] + NOTE2_WIN_NEW

    # ① G2.1
    g = _one(lines, R7.G2_ANCHOR)
    lines[g + 2:g + 2] = R7.A_G21.rstrip("\r\n").split("\r\n") + [""]

    # ④ §7.13 / §7.14 / §7.15（插入到 §8 之前）
    s8 = _one(lines, R7.S8_ANCHOR)
    lines[s8:s8] = (R7.B_713 + "\r\n\r\n" + R7.B_714 + "\r\n\r\n" + BLK_715).rstrip("\r\n").split("\r\n") + [""]

    # §8.1 F-A11 行替换
    f = _one(lines, R7.F11_ANCHOR)
    lines[f:f + 1] = [R7.ROW_F11_NEW]

    c = _one(lines, R7.C_ANCHOR)
    lines[c + 1:c + 1] = [C_ROW_V2]
    d = _one(lines, R7.D_ANCHOR)
    lines[d + 1:d + 1] = [D_ROW_V2]

    body_new = "\r\n".join(lines)
    bb = body_new.encode("utf-8")
    footer = crlf(
        E_TPL.replace("@BODY_SHA@", sha(bb))
        .replace("@BODY_LEN@", str(len(bb)))
        .replace("@LINES@", str(body_new.count("\n") + 1))
        .replace("@NAME@", name)
    ) + "\r\n"
    return body_new, footer


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "v07_final.md"))
    ap.add_argument("--land", action="store_true")
    a = ap.parse_args()
    out = os.path.join(ROOT, OUT_NAME) if a.land else a.out
    raw = open(V06, "rb").read().decode("utf-8")
    body_new, footer = merge(raw, OUT_NAME)
    v07 = (body_new + footer).encode("utf-8")
    bb = body_new.encode("utf-8")
    open(out, "wb").write(v07)
    r = subprocess.run(["git", "diff", "--no-index", "--numstat", V06, out], cwd=ROOT, capture_output=True, text=True)
    print("OUT", out)
    print("V07_BYTES", len(v07))
    print("V07_LINES", (body_new + footer).count("\n"))
    print("V07_BODY_BYTES", len(bb))
    print("V07_BODY_SHA", sha(bb))
    print("V07_FULL_SHA", sha(v07))
    print("NUMSTAT", r.stdout.strip())
