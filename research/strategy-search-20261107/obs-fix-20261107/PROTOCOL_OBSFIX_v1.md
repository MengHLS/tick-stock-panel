# 预注册：S07 期末持仓可观测性补全（OBSFIX v1，2026-11-07）

> **本文件在复算之前写定并冻结**（`FREEZE_OBSFIX.json` 记录 sha256 与时刻）。它约束本轮**一次**执行，不改 `PROTOCOL.md` v3、不改 `E1_E2_SPEC.md`、不改 `E1_REPORT_v3.md` 的 FAIL、不改任何门槛数字。

## 0. 这一轮是什么、不是什么

**是**：一次**可观测性**修补 + 一次**同参复算**。旧产物只保存期末未平仓仓位的**数量**（`final_positions`），不保存标的；因此 36 条 S 路径上有 1,839 个持仓日无法归属（`path_risk.json` → `cross_path.total_unidentified_position_days`）。本轮把这条链路的持久化补全，并用 S07@10bp 单组验证补全后的明细足以重建期末前持仓与逐日 `现金+市值=权益`。

**不是**：新策略、新参数、新宇宙、新成本、新门槛、新的样本外证据、新的盈利结论。**不产生**任何 alpha 结论；**不**宣称为确认性回测；**不**扫参；**不**重跑 12 条。

## 1. 身份与试验计数

| 项 | 值 |
| --- | --- |
| 策略 key | `S07_xs_lowvol_60d`（`STRATEGIES.md` 已登记的同一项，定义与参数逐字不变） |
| 成本情景 | 10bp（主结论情景，与旧 run 同名同参） |
| 本次性质 | **复现（reproduction）**，非新试验 |
| `n_trials` 变化 | **0**（保持 15）。理由：信号列、参数、宇宙、成本、时序、撮合口径全部不变；本轮唯一改动是**产物持久化**（把 `carry_state` 里已存在但被丢弃的字段写下来），不构成新的假设空间。按 `PROTOCOL.md` §6.1「诊断脚本…不计」与「同一定义的重跑不计」，N 不变。**若本轮出现任何参数/规则改动，则必须作为新试验 N+1 并重算 DSR 零假设线**——本轮不出现。 |
| 新增 alpha 假设 | **0**。若有人质疑"改了代码就是新试验"，回答是：改的是**写出什么**，不是**算出什么**；这一点由 §4 的 V3 检查（同引擎下 count/full 两模式信号、交易、权益逐字节相同）机器证明。 |
| 样本性质 | **历史已见数据**。不得重新命名为样本外；不得作为 OOS 宣称。 |
| 唯一可确证区间 | 仍是 2026-11-09 起的前瞻锁箱（未开始）。本轮**不缩短、不替代**它的等待期。 |

## 2. 冻结输入与代码指纹（复算前记录，复算时校验）

| 输入 | 冻结方式 | 不符时 |
| --- | --- | --- |
| 面板 | `panel_hash = fda82b47b6d5b92e0cc4b6d481020ee9a5cb328b282645c647697927c0f6dfe3`（6,422,875 行 / 3,384 只 / 2,136 日 / 2018-01-08–2026-10-30） | exit 2 |
| 研究代码 | `scripts/common.py` sha256（= `FREEZE.json` 中 `523986f1…`）**必须不变**（本轮**不修改 common.py**，否则旧 36 次的 R2 代码冻结全部作废） | exit 2 |
| 撮合/矩阵 | `backend/app/backtest/engine.py`、`matrix.py` 的 sha256 **只记录不干预**（生产源码由系统开发工程师维护，本轮只读） | 记录；若与复算时不同则 exit 2 |
| 旧 S07 产物 | `results/run_S07_xs_lowvol_60d_10.json` 的 sha256 与大小（复算前记录） | exit 2（说明旧件被人改动） |
| 旧 PATH_RISK 件 | 4 个文件 sha256（见 `CORRECTION_PATH_RISK.md` §5） | exit 2 |
| 协议 | 本文件 sha256 | exit 2 |

**已知漂移风险（必须随结果一起报）**：`engine.py` 的 mtime 为 `2026-11-07 00:01:33`，**晚于**旧 S07@10 产物的 `2026-11-06 23:19:26`。旧 run 没有记录 engine 哈希，因此**无法证明**两者同引擎。故本轮把"可观测性改动是否改变行为"与"旧件是否同引擎"拆成两个检查（V3 与 V4），不把二者混为一谈。

## 3. 执行与产物

| 步骤 | 命令 | 退出码含义 |
| --- | --- | --- |
| 冻结 | `python research\strategy-search-20261107\obs-fix-20261107\scripts\freeze_obsfix.py` | 0 ok / 2 输入缺失 |
| 复算 A（旧行为） | `...\scripts\replay_s07_obs.py --mode count` | 0 ok / 2 指纹不符 / 3 复现断言失败 / 4 输入缺失 |
| 复算 B（补全） | `...\scripts\replay_s07_obs.py --mode full` | 同上 |
| 验证 | `...\scripts\verify_obsfix.py` | 0 全通过 / 2 指纹或旧件变更 / 3 行为变更或对账失败 / 4 输入缺失 |

产物（全部在 `obs-fix-20261107/results/`，**不覆盖** `results/replay_*` 之外任何旧文件）：

| 文件 | 内容 |
| --- | --- |
| `replay_S07_xs_lowvol_60d_10_count.json` | 旧行为：只有 `final_cash`、`final_positions`、`equity`、`trades` |
| `replay_S07_xs_lowvol_60d_10_full.json` | 补全：每段 `carry_out` 全量 lot、`final_open_lots`（含估值价/基准/quote_age）、逐日现金与权益、与旧件的逐字段比较 |
| `verification.json` | 12 项检查的机器可读结果 |
| `REPORT_OBSFIX.md` | 中文报告 |
| `LEDGER_OBSFIX.json` | 账本：execution_id、是否复现、N 与理由、selection 记录 |

## 4. 验收检查（全部从原始账重算，不信任任何 `checks:true`）

| # | 检查 | 通过条件 |
| --- | --- | --- |
| V1 | 输入指纹 | 面板、`common.py`、引擎、协议、旧件的 sha256 与本文件记录一致 |
| V2 | 旧件未被改动 | PATH_RISK 4 件 + 旧 S07 run 的 sha256 不变 |
| V3 | **可观测性改动的行为等价性** | 同一引擎下 `count` 与 `full` 两模式的 `equity`、`trades`、`signals`、`final_cash` **逐字段相同** |
| V4 | **与旧产物的复现性** | `full` 与旧 `run_S07…_10.json` 的 `equity`、`trades`（314 笔）、`final_cash`、`final_positions` 相同；不同则记 `BEHAVIOR_DRIFT` 并 exit 3 |
| V5 | 逐日对账 | 用交易流水重建逐日持仓，`cash+Σ(shares×mark)` 与报告 `value` 的差 ≤1 元的天数占比；残差>1 元的日期、金额、占比全部列出，**不修补、不凑数**，未解释部分标 UNKNOWN |
| V6 | 跨年边界股份守恒 | 每段末 `carry_out` 的 shares 与该段交易流水累计净股数一致 |
| V7 | 期末 lot 完整性 | `final_open_lots` 条数 = `final_positions`；`cash+Σmv` 与最后一日权益的差；**不存在** `exit_reason="end"` 或 `open_at_end=True` 的交易（不伪造卖出） |
| V8 | 不可归属持仓日归零 | 逐日重建的持仓数与 `equity[].positions` 相同（旧产物在此处差 85 日） |
| V9 | 估值基准可追溯 | 每个期末 lot 带 `mark`、`mark_date`、`mark_source`、`quote_age_sessions`；`mark_source` 的三种取值合计 = lot 数 |
| V10 | 未识别项显式化 | 输出 `unknowns[]`，逐条说明哪些金额/因果仍未知 |
| V11 | 无新 alpha / N 不变 | `LEDGER_OBSFIX.json` 中 `n_trials_after == 15`、`new_alpha_hypotheses == 0` |
| V12 | 不越界 | `git status` 显示本轮只新增 `obs-fix-20261107/`、未改 `backend/`、未碰他人目录 |

## 5. 停机规则（stop rule）

执行过程中若出现下列任一情形，**立即停止后续步骤并如实报告**，不得调整参数重跑以"凑回"旧数字：

1. `full` 与 `count` 两模式的信号/交易/权益不等（说明我的改动碰到了交易路径）。
2. `full` 与旧产物的权益曲线或交易列表不等（说明引擎在 23:19 之后被改动，或复现失败）——此时把差异列成表，标 `BEHAVIOR_DRIFT`，**不宣称**"修复未改变行为"。
3. 逐日对账失败率高于 PATH_RISK 已记录的 1.51%（说明新增明细自身有问题）。

## 6. 本轮明确不主张

- 不主张 S07 在任何意义上有效、稳健或可盈利（旧结论原样：全期 −0.72%、Sharpe 0.031、MDD −29.93%，DSR 远低于 0.95）。
- 不主张修复后的路径风险"更低"或"更高"：修复只让**可归属度**提高，不改变任何一笔成交。
- 不主张面板能区分停牌/零量/退市（无生命周期表，UNKNOWN 照旧）。
- 不主张 E1 通过：`E1_REPORT_v3.md` 的 FAIL 原样有效。
