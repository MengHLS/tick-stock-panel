# 与现有模块的接入点对照表 v0.2（2026-11-07）

配套文件：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md`（主契约 v0.3，条款编号 E1/E2/E3/E4/X1/F 见其 §0）。

**v0.2 变更（2026-11-07）**：E2 按决定四拆为三个 id（`xs_rank_pool` 唯一策略可用 / `xs_rank_market` 诊断 / `xs_rank_pct` 历史），本表 E2 相关行同步改为三算子；原先按 `xs_rank_pct`（`mask.sum()` 作分母）实现的口径**只保留给历史/差异证明，不得作为策略口径**。判据编号见主契约 §3.4。
本表只回答一件事：**每条契约要动哪个文件的哪个符号，改动性质是什么**（新增 / 扩参 / 不改）。

约定：
- 行号基于 2026-11-07 工作区（含未提交改动），实现时以符号名为准，行号仅作定位参考。
- 「不改」= 契约明确禁止改动；若实现方认为必须改，需回到架构复核，不得顺手改。
- 「扩参」= 新增可选字段/默认值，现有调用方输出不变。
- 「改引擎」= 触碰共享内核（DSL/回测引擎），必须附回归保护证据。

---

## 1. 总表

| # | 契约 | 文件 | 符号 | 改动性质 |
| --- | --- | --- | --- | --- |
| 1 | E2 | `backend/app/factors/dsl.py` | `OPERATORS`（L43-68） | 扩参（新增 `xs_rank_pool` / `xs_rank_market` / `xs_rank_pct` 三键） |
| 2 | E2 | `backend/app/factors/dsl.py` | `CROSS_OPERATORS`（L74） | 改引擎（加入三键；`xs_rank_market` 单参、另两个双参） |
| 3 | E2 | `backend/app/factors/dsl.py` | 编译期参数校验（`_check_call` L305-365）、求值分支（`_rolling_apply` L394-427；截面分支在 `_compile_call` L476-508） | 改引擎（新增单参 + 两参算子分支） |
| 4 | E2 | `backend/app/factors/dsl.py` | `warmup`/依赖推导（L482-500、L616-700） | 改引擎（`max(warmup(x), warmup(mask))`；`xs_rank_market` 为 `warmup(x)`） |
| 5 | E1 | 同 #1-#4 | 新增 `xs_mean` | 扩参 + 改引擎（与 E2 同批） |
| 6 | E2/E1 | `backend/app/api/factors.py` | `_compiled_payload`（L69-77） | 不改（`cross_sectional` 字段已存在，自动透出） |
| 7 | E3 | `backend/app/factors/registry.py` | `_CATALOG` / Provider 注册 | 扩参（新增掩码因子定义） |
| 8 | E4 | `backend/app/backtest/rebalance_calendar.py`（新） | `rebalance_calendar()` | **新增模块** |
| 9 | X1 | `backend/app/strategy/rebalance.py`（新） | `build_target_portfolio` / `diff_to_orders` / `execute_plan` | **新增模块** |
| 10 | X1 | `backend/app/strategy/paper.py` | `create_order`（L368） | 不改（X1 的唯一下单入口） |
| 11 | X1 | `backend/app/strategy/paper_auto.py` | `on_rule_events`（L210） | 不改（禁止在此加排序） |
| 12 | F | `backend/app/api/factors.py` | `CustomFactorCreateRequest`（L236）/ `_next_version`（L280） | 扩参（幂等判定）+ 不改字段 |
| 13 | F | `backend/app/factors/store.py` | `to_spec`（L42） | 不改（`unit`/`scale_free` 若要落盘才扩参） |
| 14 | 全局 | `backend/app/backtest/engine.py` | `_plan_buys`（L3455）/ `MatcherConfig`（L226） | **不改**（排序与权重的语义权威） |
| 15 | 全局 | `backend/app/backtest/factor.py` | `_calc_period_return`（L1121） | **不改**（首日口径，与 E4 冲突，见主契约 §5.1） |
| 16 | 全局 | `backend/app/services/trading_day.py` | `is_trading_day` | **不改、也不得用作历史日历**（实时探针） |
| 17 | E4 | `backend/app/services/data_integrity.py` | `_trading_calendar`（L393） | **不改**；仅作 E4 的缺口校验器（主契约 §5.8），不决定调仓日 |

---

## 2. E1/E2：DSL 内核（唯一的「改引擎」项）

### 2.1 `backend/app/factors/dsl.py`

| 位置 | 符号 | 现状 | 要加什么 | 风险 |
| --- | --- | --- | --- | --- |
| L43-68 | `OPERATORS: dict[str, tuple[int, tuple[str,...]]]` | `("ts_mean", (1, ("n",)))` 形式：元数 + 常量参数名 | `"xs_rank_pool": (2, ())`、`"xs_rank_pct": (2, ())`、`"xs_rank_market": (1, ())`、`"xs_mean": (2, ())` | 低：只增键 |
| L70-73 | `TS_OPERATORS` | 13 个时序算子 | 不加（截面算子不得进时序族） | — |
| L74 | `CROSS_OPERATORS` | `{rank, zscore, winsorize}` | 加 `xs_rank_pool`、`xs_rank_market`、`xs_rank_pct`、`xs_mean` | **中**：该集合决定「能否嵌进时序窗口」（`E009`）与是否需要临时列机制（L614-725），必须确认新算子走与 `rank` 完全相同的分支 |
| L309-361 | 编译期校验（元数、常量、窗口区间） | 单参/双参混合 | 双参**均为表达式**，且第 2 参必须能判为布尔 → 新增 `E017` | 中：错误码需与 `E001-E016` 不冲突（已确认 E017 空闲） |
| L394-427 / L476-508 | 求值分支 `_rolling_apply`（时序算子）+ `_compile_call`（截面分支 L500-508） | 逐算子 `if` | `xs_rank_pool`：先按 `m = mask & x 非空` 把 `m` 外置 null，再在同一列上取 `rank("average").over(date) / count().over(date)`（**分母是池内非空家数，不是 `mask.sum()`**）；`xs_rank_pct`：`rank_avg(x).over(date) / mask.sum().over(date)`（仅历史/差异证明，`strategy_usable=false`）；`xs_rank_market`：与现有 `rank` 同式；`xs_mean`：`x.filter(mask).mean().over(date)` | **高**：这是唯一真正有数值风险的地方。`xs_rank_pool` 必须过主契约 §3.4.1 的 XS-A1/A5/A8（`max==1`、分母只数池内非空、tie=average）；`xs_rank_pct` 只做差异证明 |
| L482-500 | 依赖推导 | 按算子收集列 | 两参都要收集（`x` 与 `mask` 的列进 `dependencies`） | 中：漏了 `mask` 的列会导致物化缺列 |
| L616-700 | `warmup` 推导 | 时序取 `n+1` | 截面算子：`max(warmup(x), warmup(mask))`，自身不加窗口 | 低 |
| L563 | `compile_formula` | 入口 | 不改签名 | 低 |

**回归保护（改引擎的必付成本）**：改完后必须给出「93 只台账因子中抽 20 只，输出列 hash 逐位不变」的证据，以及「`rank(x)` 无掩码输出逐位不变」。没有这两条证据，独立审核不应放行。

### 2.2 为什么不能绕开内核

三种绕法都不成立，记录在此避免重复讨论：
1. **策略层后处理**：`materialize_scoring_columns`（`app/strategy/scoring.py:287`）会把窗口补算路径吃掉，且 `/api/factors/validate` 无法提前拦住错误公式。
2. **Provider 扩展**（`app/extensions/factors`）：Provider 只能产出**单标的时序列**，无法表达「同一天跨标的」的分母。
3. **新策略模板**：违反「策略只能经因子表达」的既有决定（团队记忆 2026-11-07）。

---

## 3. E3：股票池掩码的数据接入点

`in_universe` 不是表达式能算出来的，它依赖「停牌 / 涨停买不进 / 退市 / 上市不足 N 日」这些**状态数据**。接入点候选（需行情数据工程师确认哪一个可得）：

| 数据 | 现有落点（候选） | 状态 |
| --- | --- | --- |
| 停牌 | 行情库当日分区是否存在该 symbol 行 | 未验证 |
| 涨停/跌停价 | `app/strategy/paper.py#limit_prices`（L322，按 `limit_pct` 推算） | 已有**推算**逻辑，非交易所公布值 |
| ST / 退市整理 | 无（历史 ST 表缺失 → 正是主契约 §1 G3 要求 `null` 三态的原因） | **缺** |
| 上市天数 | 无独立字段，只能由「该 symbol 首根 K 线」推算 | 可推算 |

**契约要求**：`in_universe` 必须作为**因子**（可被策略引用的列）存在，不允许策略内部用 `close > 0` 之类近似。
- 若数据齐 → 走 Provider 因子（`app/extensions/factors`），`deps` 含状态列，`null_policy="keep"`。
- 若数据缺 → **不可**用「行情里有行 = 可交易」冒充；必须标 `approx=true` 并在主契约 §4.5 第 4 条约束下禁止被策略引用。

---

## 4. E4：调仓日历（新增模块）

| 项 | 内容 |
| --- | --- |
| 新文件 | `backend/app/backtest/rebalance_calendar.py`（建议；若 X1 需要复用，可放在 `backend/app/strategy/` 下由两者共同 import） |
| 公开符号 | `rebalance_calendar(mode, axis, week_rule="dt_week") -> DataFrame`、`RebalanceCalendar`（可选 dataclass） |
| 依赖 | 只依赖传入的 `axis`（G1），**不读** `trading_day.py`、不读系统时区、不读自然日历 |
| 调用方（预期） | `app/strategy/rebalance.py`（X1）、后续回测驱动的调仓模式；**不接** `app/backtest/factor.py` |
| 不改 | `app/backtest/factor.py#_calc_period_return`、`app/api/backtest.py` 的 `rebalance` 字段 |
| UI | 需在因子回测页与策略页分别措辞：前者「统计分组周期」，后者「调仓日」 |

---

## 5. X1：生产侧调仓执行器（新增模块）

### 5.1 新文件 `backend/app/strategy/rebalance.py`

| 公开符号 | 职责 | 依赖（只读） |
| --- | --- | --- |
| `RebalanceConfig` | 配置 dataclass（字段见主契约 §6.3.1） | — |
| `TargetPortfolio` | 目标组合 dataclass | — |
| `RebalancePlan` | 计划 dataclass（含 `plan_id`） | — |
| `build_target_portfolio(...)` | 排序 + 席位 + 权重 | `app/factors` 物化结果、E3 掩码、E4 日历 |
| `diff_to_orders(...)` | 目标 vs 现状 → 买卖清单 | `paper.load_positions`、`paper.load_orders` |
| `execute_plan(...)` | 逐笔下单 | `paper.create_order` |

### 5.2 必须复用、禁止重写的既有能力

| 能力 | 权威实现 | 为什么不能重写 |
| --- | --- | --- |
| 排序键 | `engine.py:3496` `candidates.sort(key=lambda i: (-i[1], matrix.symbols[i[0]]))` | 差一个 tie-break 就会与回测的持仓集合分歧（X1-A1 判据直接失败） |
| 席位与单日上限 | `engine.py:3490-3499`（`slots`、`max_daily_entries`） | — |
| 权重（equal/score_weight/score_tier） | `engine.py:3514-3518` | 负分处理 `max(tier,0)`、全 0 回退等权，细节多 |
| 下单校验（资金/涨跌停/T+1/冻结） | `paper.create_order`（L368） | 唯一写持仓的合法路径 |
| 整手换算 | `paper.qty_from_amount`（L335）/`normalize_qty`（L330） | — |
| 卖出可用量 | `paper.sell_capacity`（L579） | T+1 可用量口径 | 
 
### 5.3 触发点（需要一个新钩子，不改造 paper_auto）

| 方案 | 描述 | 取舍 |
| --- | --- | --- |
| **A（推荐）** | 定时任务在调仓日收盘后调用 `build_target_portfolio` → `diff_to_orders` → `execute_plan` | 与盘中事件链完全解耦；幂等靠 `plan_id` |
| B | 让 `on_rule_events` 识别「调仓事件」并转调 X1 | 会让事件链依赖截面计算，盘中性能与语义都变差；**否决** |

---

## 6. F：注册入口（现有已够 + 一处扩参）

| 项 | 现状 | 结论 |
| --- | --- | --- |
| 单条注册 | `POST /api/factors/custom`（`CustomFactorCreateRequest`，L236-242） | **已够**：`id/label/group/formula/description/direction` 六字段覆盖主契约 §7.2 必填项 |
| 编译校验 | `compile_formula`（`api/factors.py:293`） | 已够 |
| 非空校验 | `_trial_nonempty`（L293 后） | 已够 |
| 版本 | `_next_version`（L280） | 需**扩参**：内容未变则返回既有版本（主契约 §7.4） |
| 批量注册八只 | 无 | 非阻塞：八次 POST 即可 |
| 数值对账（V3） | 无 | 作为人工步骤 + 报告，不进 API |

---

## 7. 需要登记的「新名字」（避免实现时各自造词）

| 类别 | 名称 | 说明 |
| --- | --- | --- |
| DSL 算子 | `xs_rank_pool(x, mask)`（唯一策略可用）/ `xs_rank_market(x)`（诊断）/ `xs_rank_pct(x, mask)`（历史） | 主契约 §3.2.1 / §3.2.2 / §3.2.3 |
| DSL 算子 | `xs_mean(x, mask)` | 主契约 §4.2 |
| DSL 错误码 | `E017` | 「掩码必须是布尔表达式」；已确认 `E001-E016` 之外空闲 |
| 因子 id 前缀 | `uf_`（custom）/ `cf_`（composite） | `store.py:21-22` 强制，**不可**直接叫 `vol60` |
| 版本号 | `universe_version` / `rank_version` / `breadth_version` / `rebalance_version` | 主契约 §1 G7 |
| 订单 source 标签 | `rebalance:{plan_id}` | X1 幂等唯一依据；`paper_auto` 用 `auto:{rule_id}`，前缀不可混用 |
| 审计字段 | `universe_unknown_count`、`skipped{ineligible,score_null,score_filtered,no_slot}`、`unfilled{no_cash,limit_up,suspended}` | 主契约 §3/§6 |

---

## 8. 建议实现顺序（给系统开发工程师，非验收结论）

1. **F（八只因子注册）**：零改动即可做，用来先把「注册 → 物化 → 策略引用」这条路走通，并把 V3 对账脚本立起来。
2. **E4（调仓日历）**：纯新增、无共享内核风险，X1 依赖它。
3. **E3（掩码因子）**：依赖行情数据可得性，可与 1/2 并行。
4. **E2 截面排名族 + E1（DSL 算子）**：唯一改内核的一步，必须与回归证据一起提交（§2.1）。族内顺序：先 `xs_rank_pool` + `rank` 回归（主契约 §3.7 批次 1），`xs_rank_pct` 后补且只作差异证明（批次 2）。
5. **X1（生产执行器）**：最后做，因为它同时依赖 E4 与 E3/E2 的产物，且需与回测逐日对账。

---

## 9. 明确未验证的事项（不得当作已知）

| # | 未验证项 | 影响 |
| --- | --- | --- |
| U1 | 停牌/ST/退市/上市天数在行情库或 sidecar 中是否可得 | 决定 E3 是「真实现」还是「approx」，直接决定 E1/E2 能否用于策略 |
| U2 | 矩阵路径（`MarketDataMatrix`）是否 float32 | 若 float32，E2 的 1e-12 判据降级为精度声明（主契约 §3.4 R8） |
| U3 | `change_pct` 在**面板/因子物化**路径的实际单位（API 层确认 ×100） | 影响 `vol60` 若误用 `change_pct` 的偏差倍数 |
| U4 | 八只 F 因子的**数值**与研究工作帧是否逐位一致（本表只验证了编译与 warmup） | F-A3 未做，注册后必须补 |
| U5 | 生产侧是否有承载「收盘后调仓任务」的调度位（现有调度器是否支持按 G1 轴触发） | 决定 X1 是定时任务还是手动触发 |

---

## 10. 一句话结论

- **改引擎**：只有 E1/E2（`dsl.py` 两个截面算子 + 一个错误码），其余全部可在内核之外完成。
- **新增模块**：E3（掩码因子/Provider）、E4（日历）、X1（执行器）三处新文件。
- **现有已够**：F 类八只因子的注册链路（仅注册幂等与 `unit/scale_free` 落盘是可选的扩参）；回测侧的排序与权重语义（`_plan_buys`）已够，X1 只做镜像。

---

本文件正文 sha256：`e2a7965dd1cefb9328380bc9baec34cf1d3e5cb39b193b2eed2263615bab5971`（校验：`head -c 14553 "docs/architecture/FACTOR_ENGINE_INTEGRATION_MAP_20261107.md" | sha256sum`）· 行数 186 · 生成 2026-11-07 v0.2（E2 三 id 修订）；2026-11-07 15:45 校正：配套主契约版本指针 v0.2→v0.3、行数 182→186、正文 sha 重算，**表内容自 v0.2 起未改**（R2 只改契约文字，未改接入点）
