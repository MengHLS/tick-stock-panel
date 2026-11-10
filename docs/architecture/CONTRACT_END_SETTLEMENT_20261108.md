# 末期持仓口径契约与修复规格（D-EOS）

| 项 | 值 |
|---|---|
| 文件 | `docs/architecture/CONTRACT_END_SETTLEMENT_20261108.md` |
| 版本 | **v1.0**（首版，2026-11-08） |
| 生效对象 | `backend/app/backtest/engine.py` → `_simulate_portfolio_matrix()`（`matrix_native` 生产路径；`simulate_portfolio` 与 `simulate_market_matrix` 都汇入它） |
| 依据基线 | engine.py **268,800 B / 5,670 行 / sha256 `ecc3d8261c5605edd877f5a48863cb239700486a9167de610ea0db82ec184cbe`**；git HEAD `22ed822ac5a6aa21e2333a424f3d62b33680065f`；该文件在工作区**未修改**（`git status` 空） |
| 口径争议裁定人 | 开发经理 |
| 本文件效力 | **契约条款 + 决策记录**。不含补丁、不含验收结论；实现由系统开发工程师执行，判定由独立审核工程师出具。本文件不写 PASS/FAIL。 |
| 写入时间 | 2026-11-08 20:2x（Asia/Shanghai） |

---

## §0 结论摘要（先看这六条）

1. **缺陷成立，但根因不是"某处 `continue` 写错"，而是结算步的位置错**：末日的强制结算发生在"该 bar 的权益行已写入之后"（权益行 `:4339` / `:4342`，结算 `:4437-4453`），而 `end` 判定（`:4245-4250`）又排在 **3 个 `continue` 守卫 + 2 个 if/elif 分支之后**。本批 8 臂命中的只是其中一条路径（末日信号闩锁 `:4164-4167`）。
2. **口径裁决（D-1）**：默认臂（`finalize_open_at_end=false`）**维持"末日强制清算"，清算价基不变**；把"末日仍有持仓"收敛为**两个终态**：`SETTLED`（已清算，进现金、trade 闭环）或 `MARKED`（盯市，trade 记 `open_at_end=True`）。**不允许第三态**。两臂（有/无 finalize）走同一状态机，开关只决定"是否尝试清算"。
3. **本批影响**：6 臂各命中 1 笔；末值一律下降 1,672.01 ~ 3,445.11 元，总收益 −0.17 ~ −0.35pp；`only_entry_price_basis_raw` 的 MDD 由 −74.31% 变为 −74.41%（该臂回撤谷底恰在末行）。另 2 臂与 `a0_10bp`（199 笔、finalize=true）必须**逐字节不变**。
4. **缺陷 B（末日清算用末日开盘价）本次不改**，单列 §8。它是口径选择、不是自相矛盾；改它会把 8 臂末值再移动 5,894.42 元。**改 A 会把 B 的暴露面由 4 笔扩到 5 笔**（本臂），这是必须显式承认的代价。
5. **方案 A 与方案 B 在"重写末行"的语形下其实收敛**（§3.1）：若重写发生在 post-loop 清算之后，末值必然 = 口径 C，与方案 A 等价，但多一次写入、且丢掉"末日不可成交"的区分能力。真正的分歧是"末值算清算额还是盯市额"，不是"在哪一行写"。
6. **三条可直接复核的恒等式**（§9，一条命令）：`D−C = 1,722.55`、`B−C′ = −535.53`（= 卖出费）、`C−B = 5,358.89`。

---

## §1 缺陷定义

### 1.1 实测三口径（同一份回测：1,000,000 起始，2019-07-01…2026-10-30，10bp 成本）

| 口径 | 末值（元） | 总收益 | 算法 |
|---|---:|---:|---|
| **B** 全按末日收盘盯市 | 478,212.34 | −52.18% | 末行 cash 245,373.34 + Σ 股数×末日收盘 232,839.00 |
| **C** 全按末日开盘虚拟清算（扣卖出费） | 483,571.23 | −51.64% | 末行 cash 461,641.78 + 被递延那笔按开盘 109.90 的 `exit_value` 21,929.45 |
| **C′** 全按末日收盘虚拟清算（扣卖出费） | 477,676.81 | −52.23% | 2026-10-29 收盘现金 245,373.34 + 232,839.00 ×(1−0.0023) |
| **D** 引擎实报（4 笔按开盘 + 1 笔按收盘） | 485,293.78 | −51.47% | `base_nodefaults_10bp/equity.parquet` 末行 |

- 交叉验证：B = `only_finalize_open_at_end` 臂末值 **478,212.34**（逐位相同），两条路径可对撞。
- 恒等式：`B − C′ = 535.53`（= 5 笔按收盘计的卖出费，费率 23bp = 佣金 3bp + 印花 10bp + 滑点 10bp）；`C − B = 5,358.89`（= Σ股数×(开盘−收盘) 5,908.00 − 卖出费 549.11）；`D − C = 1,722.55`。
- 分位取整：逐笔 `exit_value` 是 2 位展示值、现金按未取整累计，故"Σ逐笔 − 现金变动"常差 0.01 ~ 0.04 元（本臂账务口径 1,722.56 vs 权益口径 1,722.55）。**验收一律用权益口径**，账务口径只作旁证。

### 1.2 机制（调用序已由实现方 `sys.settrace` 取证：`five_c_20261108/trace_end_position.json` 第 221-248 条；我按算术复核）

末根 K 线 `time_id=1778`（2026-10-30）、5 只持仓：

1. `:4100` 逐持仓进入循环（预插入点：`:4104` 之后、`:4105` 之前）。
2. 688143.SH（`position_id=202`）走到 `:4160`，`_exit_signal_at` 返回 **True**（trace 第 221-222 条）；因 `exit_fill == "open_t+1"`，`:4164-4167` 只写 `next_open_exit_reason="signal"` 后 **`continue`**，不调用 `_try_sell`。
3. 其余 4 只信号为 False（trace 第 223 / 229 / 235 / 241 条），落到链底 `:4245-4250` 得 `reason="end"`，在 `:4251-4258` 按 `exit_prices[末日]` = **末日开盘**卖出并进账（trace 第 225-246 条）。
4. `:4332-4348` 写末行权益：`cash` 461,641.78、`positions=1`、`value = 461,641.78 + 200×118.26 = 485,293.78`、`exposure 0.0487`。
5. 循环结束后 `:4436-4453`（`carry_out` 与 `finalize_open_at_end` 两个分支都不成立时的 `else`）才把 688143 按同一末日开盘 109.90 补卖（trace 第 247 条），现金变 483,571.23，**但权益行已经写完**。

⇒ 同一张末行里，4 只按开盘价、1 只按收盘价；末行的现金不含最后一笔卖出，却计入了该笔的持仓市值。

### 1.3 根因的准确说法（三条缺一不可，修一条不够）

**D-EOS-1（结构）** 末日结算写在权益行之后。任何"结算后才进现金"的路径都会与已写好的权益行冲突。
**D-EOS-2（可达性）** `end` 判定是 if/elif 链的最后一支，且前面有 3 个 `continue` 守卫。**任何先命中前面分支的持仓都拿不到 `end`**（下表 6 条）。
**D-EOS-3（价基）** 清算价取 `exit_prices[末日]`（`:2617-2621`：`open_t+1 ⇒ execution_open`，其余 `⇒ execution_close`）。这是 §8 单列的口径问题，不是矛盾。

末日能"逃过 `end`"的 6 条路径（行号对 `ecc3d826…`）：

| # | 早于 `end` 的分支/守卫 | 行号 | 后果 | 本批 8 臂是否命中 |
|---|---|---|---|---|
| P1 | 建仓日分支（`entry_date == date_text`）→ `continue` | `:4105` → `:4137` | 末日建仓：不进现金、按收盘盯市，随后 post-loop 按开盘卖 | 否（8 臂末日建仓 0 笔） |
| P2 | `pending_exit_reason` → `continue` | `:4138` → `:4149` | 挂单未成：同上 | 否 |
| P3 | `risk_exit_reason` → `continue` | `:4150` → `:4157` | 风控已登记未执行：同上 | 否 |
| **P4** | **信号闩锁（`open_t+1`）→ `continue`** | **`:4160` → `:4167`** | **本缺陷主路径** | **是：6 臂各 1 笔** |
| P5 | `hold_extension_policy` 到期/转强分支（写 `next_open_exit_reason` 后不设 `reason`） | `:4170` → `:4236` / `:4242` | 延展策略到期闩锁：同上 | 否（策略未启用 hold policy） |
| P6 | 链底 `_try_sell(..., "end")` 被 `_can_sell` 拒（停牌/一字跌停） | `:4251` → `:3286-3297` | 末日不可成交：留在 `positions` | 否（`blocked_exit_days=0`） |

**结论**：把 `end` 只"提到信号闩锁之前"能修 P4，但 P1/P2/P3/P5/P6 仍复现同一症状。规格必须落在"每持仓体顶部的一次性终结结算步"（§4 S-1 / S-2），而不是移动某个 `elif`。

### 1.4 同一缺陷的第二处实现（另案，见 §10）

`simulate_portfolio_legacy()`：权益行 `:5185-5192`，post-loop 清算 `:5197-5210`，`end` 判定 `:4988-4989`，与 matrix 路径同型 ⇒ 缺陷同型。**额外一处不一致**：该路径全文不出现 `finalize_open_at_end`（引擎内仅 `:261` / `:352` / `:370` / `:388` / `:4247` / `:4400` 引用），即**开关在 legacy 路径上无效**。生产调用只走 matrix（`backend/app/backtest/strategy.py:2305`、`:2691` 均调 `simulate_market_matrix`），legacy 目前只被测试的 `path="legacy"` 参数触达。

---

## §2 不变量（本契约的全部要求都能化归到这四条）

**I1（末行自洽）** 末行 `value = cash + Σ_{剩余持仓} 股数 × 该持仓的末日估值价`；且 `cash` 必须已包含同一 bar 内所有进入 trades 的成交额。不存在"已记入 trades 但未进末行现金"的成交。

**I2（单一价）** 同一末日、同一持仓只能有一个估值价。禁止 D 那种"4 只按开盘、1 只按收盘"。

**I3（两终态）** 末日每一只持仓恰好处于且只处于两个终态之一：

| 终态 | 条件 | 末行 `cash` | 末行 `positions`/`exposure` | trades | `exit_price` | `pnl_amount` | `open_at_end` | `exit_reason` |
|---|---|---|---|---|---|---|---|---|
| **SETTLED** 已清算 | `finalize_open_at_end=false` 且 末日 `_can_sell` 通过 | 含清算所得 | 不含该股（全部清算则 0 / 0.0） | 1 条 | 该臂 `exit_fill` 的末根价（`open_t+1`⇒开盘；`close_t`/`signal_next_minute`⇒收盘） | 实算 | `False` | `"end"` |
| **MARKED** 盯市 | `finalize_open_at_end=true`；或 `false` 但末日不可成交（P6） | 不含 | 含该股，按末日收盘 | 1 条 | 末日收盘（无效则回退：最后有效收盘 → `entry_price`） | `0.0` | `True` | `"end"` |

**I4（统计定义不动）** 不得改 `_calc_portfolio_stats_from_values`（`:5589-5643`）任何定义；尤其 `annual_return = (1+total)^{252/len(equity_values)}−1`（`:5603`）与 `closed_trades = [t for t in trades if not t.open_at_end]`（`:5611`）。⇒ **禁止追加结算行**（那会把 252/1779 变 252/1780）。

---

## §3 口径决策

### 3.1 先纠正一个前提：方案 A 与"重写末行"方案在语形下是同一件事

派单把选择描述为"方案 A：把 `end` 判定提到信号闩锁之前" vs "方案 B：finalize 后重写末行权益并同步 statistics"。按现码结构，post-loop 的 `else` 分支（`:4437-4453`）**先把现金改掉了**（461,641.78 → 483,571.23）。所以"在它之后重写末行"得到的**必然是口径 C（483,571.23）**，不是 B。也就是说：

- 若"重写"发生在清算之后 ⇒ 结果 = 方案 A，只是多一次写入，且仍无法表达"末日不可成交"（重写会把残余持仓也一并抹平）。
- 若"重写"要得到 B（478,212.34）⇒ 必须**不结算**，那是**默认口径变更**（等于把 `finalize_open_at_end` 默认值改成 true），不是"修数"。

⇒ 真正的分歧点只有一句：**末值算"清算额"还是"盯市额"**。"在哪一行写"是实现细节，"写什么"才是口径。

同时纠正第二处前提：**重写末行不会改 `len(equity_values)`**（仍 1779），只会改末行的 `value/cash/positions/exposure`，因此 `final_equity / total_return / annual_return / MDD / Sharpe / Calmar / avg_exposure` 会动，但年化分母不动。**只有"追加一行结算"才会动分母**：本例 252/1779 → 252/1780，年化 −9.7800% → −9.7747%（+0.0052pp）——数值虽小，属定义变更，本契约禁止（I4）。

### 3.2 决策 D-1：默认臂走 SETTLED（清算），价基不变

**选定**：`finalize_open_at_end=false` ⇒ 末日一律先尝试 SETTLED（清算价 = 该臂 `exit_fill` 的末根价）；清算不了的转 MARKED。`finalize_open_at_end=true` ⇒ 全部 MARKED（行为与今天逐字节相同）。

**理由（四条，按权重排序）**

1. **恢复开关自称的语义，而不是替换默认口径**。`:352` 的标签是「期末未平仓按收盘估值」、`:4354-4356` 的注释是「默认按最后一个价格有效日强制落账；T74 原始执行模型则保留为 openAtEnd」。翻成一句话：**默认 = 强制落账，true = 不伪造卖出**。现状是"默认臂对其中一只既伪造了卖出、又在账面留了市值"——修它应该让默认回到"强制落账"，而不是把默认改成 true。若把默认改成盯市，`finalize_open_at_end` 就失去区分力，`only_finalize_open_at_end` 臂会退化成与基线**逐字节相同**，8 臂的"单一开关分解"设计当场作废。
2. **研究侧要的是"每笔闭环"**。默认口径下 208 笔全部有 `exit_price/exit_date/pnl`，`win_rate` 分母 208、`profit_factor`/`avg_pnl`/Monte Carlo 用全部笔。改成盯市后最后一笔 `open_at_end=True`，被 `:5611` 从 `closed_trades` 剔除：分母 208→207，`completed_trade_count` 208→207，`open_at_end_count` 0→1。这是**统计口径变更**，必须由策略负责人裁定，不属于缺陷修复。
3. **改动面最小**：3 个落点（S-1 / S-3 / 价基不动），不触碰 `equity_values` 长度、不触碰统计函数、不触碰 `next_open_exit_reason` 的读取方。
4. **可对撞**：C 与 B 之间存在 §1.1 的三条恒等式，验收不必"跑一遍看数字像不像"，而是可以逐式对平。

### 3.3 两臂"同一规则"的精确表述

"同一规则" = **同一状态机（I3）、同一价基（S-5）、同一记账顺序（I1）**；两臂唯一的差别是**是否尝试清算**这一步：

```
末根 K 线，权益行写入之前：
  if carry_out:                      → 不做末日结算（S-7），原样结转
  for 每个持仓:
      if not finalize_open_at_end:   → 尝试 SETTLED（_can_sell 通过则成交并进现金）
      仍留在 positions 的            → MARKED（按末日收盘计入末行市值）
  写末行权益（此时 cash / positions / exposure 已终局）
  循环结束后：
      只为 MARKED 的持仓补 open_at_end 的 trade 记录（不再调用 _sell）
```

⇒ 默认臂在"全部可成交"时末行 `positions=0 / exposure=0.0`；true 臂恒为 `positions>0`。**两臂都不允许出现"第三态"**（今天默认臂里混着 4 只按开盘、1 只按收盘）。

### 3.4 放弃的选项（留痕）

| 选项 | 为什么不选 |
|---|---|
| **D-2** 默认改成全盯市（默认值改 true，或直接删开关） | 移动全部 208 笔臂末值 −7,081.44 元 / −0.71pp；改变 `win_rate` 等统计分母；作废"单一开关分解"设计；属研究口径决策，须策略负责人裁定（§7.2 给回滚边界） |
| **D-3** 追加一行"末日结算"权益行 | 改 `len(equity_values)` ⇒ 全部年化/Sharpe 的分母与时序定义变化（I4 禁止），且 1779↔1780 无法与历史读数对照 |
| **D-4** 事后重写末行（在 post-loop 清算之后） | 与 A 等价但多一次写入；丧失"末日不可成交"的表达能力；无法阻止未来新增的逃逸路径 |
| **D-5** 把 `end` 判定上移到信号闩锁之前 | 只修 P4，P1/P2/P3/P5/P6 仍复现；把"结构位置错"当成"顺序错" |

---

## §4 规格条款（可机械判定）

> 落点一律相对 `ecc3d826…` 的行号。本文件不给补丁，只给"必须成立什么"。

**S-1 结算时点**。末日结算必须在该 bar 权益行写入（`:4339` / `:4342`）**之前**完成。落点：`:4100` 的持仓循环体内、`:4104` 之后、`:4105` 之前（这样 P1~P6 全部被覆盖）。*判据*：命中场景下末行 `cash` 与"按 `exit_value` 累计的现金"一致（±0.02，分位取整），且末行 `value` 不含任何已记入 trades 的持仓市值。

**S-2 可达性**。末日结算不得依赖任何闩锁状态（`next_open_exit_reason` / `pending_exit_reason` / `risk_exit_reason` / `hold_plan`）。落点后的 `end` 分支（`:4243-4250`）在该守卫下不可达：**实现方须二选一**——删除，或保留但加一行断言并在交付说明里写明"防御性重复"。*判据*：§6 的 T-EOS-1 ~ T-EOS-4 逐条通过。

**S-3 两终态收敛**。`elif config.finalize_open_at_end:`（`:4400-4435`）与 `else:`（`:4436-4453`）合并为一个"MARKED 记账号"：只为仍在 `positions` 的持仓追加 `TradeRecord(open_at_end=True, exit_price=末日收盘, pnl_amount=0.0, exit_reason="end")`，**不再调用 `_sell`**（现金与市值已在末行前定稿）。`exit_price` 取值与今天 `:4411` 完全一致（`execution_close[last_time]`，`last_time` = 最后一个有效收盘），以保证 true 臂逐字节不变。*判据*：`only_finalize_open_at_end` 臂 4 个产物 sha256 全部不变（§6 R-3）。

**S-4 单一价**。见 I2。*判据*：末日 `positions>0` ⇒ 该股 trades 必为 `open_at_end=True` 且 `exit_price` = 末日收盘；末日 `positions=0` ⇒ 该股 trades 的 `open_at_end` 必须为 `False`。

**S-5 价基不变**。SETTLED 的成交价继续取 `exit_prices[末日]`（`:2617-2621`），**不得**改为收盘。本次改动集不允许触碰这两行。*判据*：命中笔的 `exit_price` 与改前逐位相同（本臂 109.9，保留 4 位小数）。

**S-6 reason 语义**。SETTLED 的 `exit_reason` 固定 `"end"`，**覆盖**先前 `pending_exit_reason` / `risk_exit_reason` 的表述；`exit_signal_date` 取末日日期（与今天 post-loop 的 `matrix.timestamp_labels[last_time][:10]` 一致）。*建议（非阻塞）*：加 `_count("end_overrode_pending")`，让"末日清算覆盖了某个未执行意图"在 `stats["execution"]` 里可见。*判据*：P2/P3 场景用例中 trades 的 `exit_reason == "end"`。

**S-7 carry_out 不变**。`options.carry_out=True` 时**不得**触发末日结算（守卫必须保留 `not options.carry_out`）。`next_open_exit_reason` 在末日不再被写入：该字段全库只有 `:3887`、`:3925` 两个读取点，都在**下一 bar 的开盘阶段**，非结转路径在末日之后没有读者 ⇒ 语义不变。*判据*：`backend/tests/backtest/test_continuous_account.py` 全量逐值不变（§6 R-4）。

**S-8 finalize 臂不变**。`finalize_open_at_end=true` 的产物必须逐字节不变（§6 R-3）。

**S-9 统计不动**。见 I4。*判据*：`git diff` 不得命中 `:5589-5643` 区间。

**S-10 不改默认值**。`MatcherConfig.finalize_open_at_end` 默认仍是 `False`（`:261`）。*判据*：改后 `resolved_matcher_config.finalize_open_at_end` 对 6 臂仍为 `false`。

---

## §5 影响面（本批 8 臂，`research/s01b-20261108/five_a/`）

### 5.1 命中臂（6/8）

| 臂 | 命中笔数 | 命中标的 / 股数 | 末值 D → C | ΔV（元） | 总收益 D → C | Δpp | 年化 D → C | MDD D → C | Sharpe | 末行 positions/exposure |
|---|---:|---|---:|---:|---|---:|---|---|---|---|
| `base_nodefaults_10bp` | 1 | 688143.SH / 200 | 485,293.78 → **483,571.23** | −1,722.55 | −51.47% → **−51.64%** | −0.1700 | −9.73% → −9.78% | −71.95% → −71.95% | −0.28 → −0.28 | 1 / 0.0487 → 0 / 0.0 |
| `only_trailing_peak_price_close` | 1 | 688143.SH / 200 | 485,293.78 → **483,571.23** | −1,722.55 | −51.47% → **−51.64%** | −0.1700 | −9.73% → −9.78% | −71.95% → −71.95% | −0.28 → −0.28 | 1 / 0.0487 → 0 / 0.0 |
| `only_execution_costs` | 1 | 688143.SH / 200 | 485,420.69 → **483,698.12** | −1,722.57 | −51.46% → **−51.63%** | −0.1700 | −9.73% → −9.78% | −71.94% → −71.94% | −0.28 → −0.28 | 1 / 0.0487 → 0 / 0.0 |
| `only_entry_price_basis_raw` | 1 | 688143.SH / 200 | 434,710.53 → **432,987.98** | −1,722.55 | −56.53% → **−56.70%** | −0.1700 | −11.13% → −11.18% | **−74.31% → −74.41%** | −0.34 → −0.34 | 1 / 0.0544 → 0 / 0.0 |
| `base_nodefaults_gross` | 1 | 688143.SH / 200 | 527,074.75 → **525,402.74** | −1,672.01 | −47.29% → **−47.46%** | −0.1700 | −8.67% → −8.71% | −71.08% → −71.08% | −0.23 → −0.23 | 1 / 0.0449 → 0 / 0.0 |
| `only_block_limit_open` | 1 | 688143.SH / **400** | 1,121,259.36 → **1,117,814.25** | −3,445.11 | +12.13% → **+11.78%** | −0.3500 | +1.63% → +1.59% | −40.12% → −40.12% | 0.19 → 0.19 | 1 / 0.0422 → 0 / 0.0 |

- **命中判据**：末行 `positions=1`，且该股在末日 trades 中 `exit_reason="end"` 而末行 `cash` 不含它 ⇒ 命中。6 臂都是 688143.SH，与 §1.2 的 P4 一致。
- **方向性警告（写进任何引用本表的文档）**：本例末值一律下降，是因为末日**收盘 118.26 > 开盘 109.90**；若末日收盘 < 开盘，同一修复会让末值**上升**。禁止把"修复使收益下降 0.17pp"写成通用结论。
- `avg_exposure` 只在第 4 位小数动：base 0.568971→0.568944（报表 0.569→0.5689）、raw 0.5692→0.5691，其余 4 臂 4 位内不变；`max_exposure` 6 臂全不变（0.7184 / 0.7368 / 0.7183 / 0.7191 / 0.7387 / 0.7184）。
- 上表 C 列与 `diag1_result.json → arms.<arm>.final_cash_after_finalize` 逐臂一致（6/6 对平），ΔV 由 `C − equity.parquet 末行 value` 得出。

### 5.2 必须逐值不变的臂（2/8 + 1）

| 臂 | 为什么不变 | 判据 |
|---|---|---|
| `only_finalize_open_at_end` | 走 MARKED 全路径，S-3 只合并代码不改输出 | 4 个产物 sha256 与 `five_a/manifest.json` 一致；末值仍 478,212.34 |
| `only_exit_signal_requires_profit` | 末行 `positions=0`（4 笔 `end` 全在循环内成交），无逃逸 | 同上；末值仍 673,798.76 |
| `results/a0_10bp`（199 笔，`finalize_open_at_end=true`） | 同 finalize 臂 | 末值仍 1,242,725.28；5 只持仓按收盘盯市 |

### 5.3 其它消费者（不在 8 臂里，但会看到变化）

| 消费者 | 变化 | 处置 |
|---|---|---|
| 权益/仓位曲线（前端、`equity.parquet`） | 末点 `cash` 461,641.78 → 483,571.23、`positions` 1 → 0、`exposure` 0.0487 → 0.0 | 属预期；若前端有"期末持仓"列表会变空 |
| `stats["pending_exit_positions"]`（`:4357`、`:4468`） | 语义收紧为"末日不可结算的持仓数"；本批仍 0 | 同步注释；数字不变 |
| `stats["execution"]` 计数 | 命中笔不再产生 post-loop 成交；只有 P6 场景才会新增 `pending_exit` | 逐臂比对 `execution` 字典，只允许 P6 相关键变化 |
| `research/s01b-20261108/REPORT.md`（52,097 B / `e60cd0b8…`）的 8 臂表 | 6 臂的"期末权益/总收益/年化"3 列 + raw 臂 MDD 1 列会变 | **本契约不改报表**；实现方重跑后由研究侧一次性换数，并在表脚写口径字样 |

---

## §6 回归清单（可执行命令 + 判据 + 失败处置）

> 前置：`cd C:\work\sourcecode\tick-stock-panel`；解释器一律 `backend\.venv\Scripts\python.exe`（3.11.15 / polars 1.44.1 / pytest 9.0.3）。**先做 R-0 快照，再动手。**

**R-0 基线快照（改前必做）**
```
git status --porcelain backend/app/backtest/engine.py      # 必须为空
sha256sum backend/app/backtest/engine.py                   # ecc3d826…
sha256sum research/s01b-20261108/five_a/manifest.json      # 8 臂 4 产物 sha256 都在里面
```
*判据*：engine.py 哈希 = `ecc3d826…`，`manifest.json` 含 8 臂 `artifacts_sha256`。失败 ⇒ 停止，先回到基线。

**R-1 单元测试（全量）**
```
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
backend\.venv\Scripts\python.exe -m pytest backend\tests\backtest -q
```
*判据*：`0 failed`；用例数与改前一致，**唯一允许的差异是本次新增的用例**。*失败处置*：逐条二分——(a) 该用例断言的是缺陷行为（同时满足"末日有卖点信号"且"断言末行权益/final_equity"）⇒ 随契约更新并在交付说明逐条列出；(b) 其它 ⇒ 返工。
*已静态核查*：`backend/tests/backtest` 中**断言权益数值的用例共 9 个**（`test_331_execution_rules.py::test_finalize_open_at_end_…`、`test_continuous_account.py` 6 个、`test_robustness_metrics.py` 1 个、`test_empty_fold…` 1 个），**其中 0 个覆盖"默认臂 + 末日有卖点信号"**（多数是 `carry_out=True`，被 S-7 排除）。⇒ 现代码**没有用例守着这个缺陷**，R-2 的新增用例是必须项，不是可选。

**R-2 新增判据用例（5 条，必须与实现同批交付）**

| 用例 | 构造 | 断言 |
|---|---|---|
| T-EOS-1（P4 主路径） | 4 根 K 线，`(A,0)` 建仓信号、`(A,3)` 卖点信号，`exit_fill="open_t+1"`，`finalize_open_at_end=False` | 末行 `positions==0`、`cash==value`、`exposure==0.0`；trades 恰 1 笔 `exit_reason="end"`、`exit_date==末日`、`exit_price==末日开盘`、`open_at_end=False` |
| T-EOS-2（P2/P3） | 末日持仓带 `pending_exit_reason`（用停牌造） | trades `exit_reason=="end"`（覆盖 pending 原因）；末行 `cash` 已含清算额 |
| T-EOS-3（P1） | 末日建仓（`(A,last-1)` 入场信号） | 末行 `positions==0`；该笔 `duration==0`；现金含双边费用；**现金与改前相同**（只改记账位置，不改经济结果） |
| T-EOS-4（P6 兜底） | 末日一字跌停（`signal_limit_down` + 全价相等） | 末行含该股按收盘、`exposure>0`；trades `open_at_end=True`、`exit_price==末日收盘`、`pnl_amount==0.0`；`cash` 不含该股 |
| T-EOS-5（finalize 不变） | 同 T-EOS-1，但 `finalize_open_at_end=True` | 末行 `positions==1`、`value==cash+市值`；trades `open_at_end=True`、`pnl_amount==0.0`、`completed_trade_count==0` |

**R-3 8 臂 + a0 重跑（禁止覆盖现有产物）**
```
cd research\s01b-20261108\five_a
..\..\..\backend\.venv\Scripts\python.exe run_arm.py --tag postfix_20261108\base_nodefaults_10bp
..\..\..\backend\.venv\Scripts\python.exe run_arm.py --tag postfix_20261108\base_nodefaults_gross --gross
..\..\..\backend\.venv\Scripts\python.exe run_arm.py --tag postfix_20261108\only_block_limit_open            --inject-file inject/only_block_limit_open.json
..\..\..\backend\.venv\Scripts\python.exe run_arm.py --tag postfix_20261108\only_entry_price_basis_raw      --inject-file inject/only_entry_price_basis_raw.json
..\..\..\backend\.venv\Scripts\python.exe run_arm.py --tag postfix_20261108\only_execution_costs            --inject-file inject/only_execution_costs.json
..\..\..\backend\.venv\Scripts\python.exe run_arm.py --tag postfix_20261108\only_exit_signal_requires_profit --inject-file inject/only_exit_signal_requires_profit.json
..\..\..\backend\.venv\Scripts\python.exe run_arm.py --tag postfix_20261108\only_finalize_open_at_end        --inject-file inject/only_finalize_open_at_end.json
..\..\..\backend\.venv\Scripts\python.exe run_arm.py --tag postfix_20261108\only_trailing_peak_price_close  --inject-file inject/only_trailing_peak_price_close.json
```
*判据（逐臂）*：
1. `equity.parquet` 前 1778 行**逐单元格相同**，仅末行 `value/cash/positions/exposure` 变；
2. `trades.parquet` **按 `(entry_date, symbol)` 排序后逐单元格相同**（值集不变；末笔 `end` 改为循环内成交后会**提前到该股在列表中的位置**，故不能用 parquet 字节相等作判据）；
3. 6 臂末行 `value` = §5.1 的 C 列（±0.01）；2 臂末行恒等；`results/a0_10bp` 4 产物 sha256 不变；
4. `drawdown.parquet` 只允许末行变（raw 臂末行即谷底）。

**R-4 跨段回归（carry_out，必须逐值不变）**
```
backend\.venv\Scripts\python.exe -m pytest backend\tests\backtest\test_continuous_account.py backend\tests\backtest\test_walkforward.py -q
```
*判据*：全绿且**逐值不变**（这两套断言"分段 == 一次连续回放"，是 S-7 的唯一守护）。

**R-5 恒等式对平（不用重跑就能判）**
```
backend\.venv\Scripts\python.exe -c "import polars as pl,json;e=pl.read_parquet(r'research/s01b-20261108/five_a/base_nodefaults_10bp/equity.parquet');d=json.load(open(r'research/s01b-20261108/five_a/five_c_20261108/diag1_result.json',encoding='utf-8'))['arms']['base_nodefaults_10bp'];D=e['value'][-1];C=d['final_cash_after_finalize'];B=pl.read_parquet(r'research/s01b-20261108/five_a/only_finalize_open_at_end/equity.parquet')['value'][-1];print('B',B,'C',C,'D',D,'D-C',round(D-C,2),'B-C',round(B-C,2))"
```
*期望输出*：`B 478212.34 C 483571.23 D 485293.78 D-C 1722.55 B-C -5358.89`。改后重跑的新目录里 `D` 应变成 `C`，而 `C`、`B` 不变 ⇒ 三者塌成两点，缺口 0.00。

**R-6 生产口径护栏**
```
backend\.venv\Scripts\python.exe -m pytest backend\tests\backtest\test_matrix_strategy.py backend\tests\backtest\test_331_execution_rules.py -q
```
*判据*：全绿。这两套里的 `end` 用例只断言 `exit_reason` 与价格，改后仍应成立（价格未变，仅记账位置变）。

---

## §7 风险与回滚

### 7.1 方案 A（本契约）的风险

| # | 风险 | 量级 | 缓解 |
|---|---|---|---|
| A-R1 | 末行 `positions/exposure` 变 0，前端"期末仓位"视觉变化 | 1 个点 | 交付说明点名；不属回归 |
| A-R2 | 末行恰为回撤谷底的臂 MDD 变深（raw 臂 −74.31% → −74.41%） | 0.10pp | 属真值变化；报表换数时同步 |
| A-R3 | 对已有 `pending_exit_reason` 的持仓，`exit_reason` 由 pending 原因变 `"end"` | 本批 0 例 | S-6 + 建议计数器；T-EOS-2 守 |
| A-R4 | 末日建仓的持仓改为"当日开盘买、当日开盘卖"，双边费用照收 | 经济结果**不变**（改前也是按同一开盘价 post-loop 卖出），只改记账位置 | T-EOS-3 明确断言现金流不变 |
| A-R5 | 末日停牌/一字跌停的持仓由"按更早的价清算"改为"按末日收盘盯市" | 会改该笔 `exit_price/exit_date` | 属修正（原来用陈旧价）；T-EOS-4 守 |
| A-R6 | 触碰全引擎最热的持仓循环 | 性能与回归面 | 只在末根 bar 触发一次整循环（`if time_id == time_count - 1` 短路）；R-3 逐臂对平 |

**可回滚边界（方案 A）**：**单文件、3 个落点、无数据迁移、无 schema 变更** ⇒ 回滚单元 = 一次 `git revert`（或 3 处 hunk 反向应用）。产物级回滚判据 = 8 臂 4 产物 sha256 回到 `five_a/manifest.json` 记录值。**不需要**回滚任何数据库或策略文件。

若开发经理要求"同一构建内可复现旧读数"，再加引擎级枚举 `end_settlement: {"settle","mark","legacy"}`（默认 `settle`；`legacy` 精确复现今天的 D 口径，含 post-loop `_sell`）。**该枚举不进 `ExecutionPolicy` payload**，避免前端契约与 `schema_version` 迁移。

### 7.2 方案 B（默认改盯市）的风险（备选，未采纳）

| # | 风险 | 量级 |
|---|---|---|
| B-R1 | 全部 208 笔臂末值 −7,081.44 元（−0.71pp） | 8 臂中 5 臂同时移动 |
| B-R2 | `win_rate` 分母 208→207、`completed_trade_count` 208→207、`open_at_end_count` 0→1、`avg_pnl`/`profit_factor`/Monte Carlo 样本集变化 | 统计定义变更 |
| B-R3 | `finalize_open_at_end` 失去区分力，`only_finalize_open_at_end` 臂退化 | 8 臂设计作废 |
| B-R4 | 与历史所有 D 口径读数不可对照，需一次性重述 | 不可逆 |

**可回滚边界（方案 B）**：代码上仍是单文件改动，可 revert；**但"报表已换数"这件事不可回滚**——一旦对外引用过盯市口径的收益，回滚代码不会把引用改回去。⇒ 若采纳 B，必须先做一次"口径换版"记录（`REPORT.md` 表脚 + 台账），再改代码。这是我不选 B 的第四条、也是最实用的理由。

---

## §8 缺陷 B（末日清算用末日开盘价）的处置结论

### 8.1 性质

`:2617-2621` 把 `exit_prices` 定成"`open_t+1` ⇒ 开盘"，末日清算沿用它 ⇒ **决策发生在末根收盘、成交价取该日开盘**。这与 D-EOS-1/2 不同：它**不自相矛盾**，而是一个口径选择：
- 若把"窗口末日在回测开始时已知"当作前提，则末日开盘清算 = "D−1 收盘决定、D 开盘成交"，与 `open_t+1` 自洽；
- 若要求"成交价不得早于驱动它的信息时点"，则应取末日收盘（= C′，477,676.81）。

两者都能自圆其说，差别只在"末值算哪一档价"。

### 8.2 结论：**先记录，不随本次改动集一起改**

1. **不是矛盾，是选择**。修 A 的目标是"消除自相矛盾"，B 不在此列。
2. **会移动全部 8 臂的末值**（本臂 −5,894.42 元 / −0.59pp），使本批已发布读数与重跑读数不可对撞——而 §1.1 的三条恒等式正是本次验收的骨架，改 B 会把骨架拆掉。
3. **必须显式化才能被检验**。正确做法是加显式参数 `end_settlement_price: {"last_open","last_close"}`（默认 `last_open` = 现状），并在报告里打标签；这样两种价基可以 A/B，而不是悄悄换掉。
4. **修 A 会把 B 的暴露面从 4 笔扩到 5 笔**（本臂）：改前 688143 是"账面按收盘、成交按开盘"的伪盯市，改后它与其余 4 只一样按末日开盘清算。⇒ 这个代价必须在交付说明里写出来，不能当作"顺带改善"。

### 8.3 若将来要改 B，一次改动集的边界

只动 S-5 一条 + `MatcherConfig` 新参数默认值；必须同批完成：8 臂重跑、报表换数、`B/C/C′` 三式重校、`REPORT.md` 表脚写"末日价基 = 开盘 / 收盘"。**任何引用 S01 类回测的文档必须同时写"执行口径"与"末期价基"两行**（沿用既有团队口径纪律）。

---

## §9 复现附录

### 9.1 一条命令复现 B / C / D（不跑回测，只读现成产物）

```
cd C:\work\sourcecode\tick-stock-panel
backend\.venv\Scripts\python.exe -c "import polars as pl,json;e=pl.read_parquet(r'research/s01b-20261108/five_a/base_nodefaults_10bp/equity.parquet');d=json.load(open(r'research/s01b-20261108/five_a/five_c_20261108/diag1_result.json',encoding='utf-8'))['arms']['base_nodefaults_10bp'];D=e['value'][-1];C=d['final_cash_after_finalize'];B=pl.read_parquet(r'research/s01b-20261108/five_a/only_finalize_open_at_end/equity.parquet')['value'][-1];print('B',B,'C',C,'D',D,'D-C',round(D-C,2),'B-C',round(B-C,2))"
```
实测输出（2026-11-08 20:2x）：
```
B 478212.34 C 483571.23 D 485293.78 D-C 1722.55 B-C -5358.89
```

三个值各自的独立来源：
- **D** = `five_a/base_nodefaults_10bp/equity.parquet` 末行 `value`（同行 `cash 461641.78 / positions 1 / exposure 0.0487`）。
- **C** = `diag1_result.json → arms.base_nodefaults_10bp.final_cash_after_finalize`（= 末行 cash + 递延那笔 `exit_value 21929.45`）。
- **B** = `five_a/only_finalize_open_at_end/equity.parquet` 末行 `value`（= 245,373.34 + 232,839.00）。
- **C′** = 245,373.34 + 232,839.00×(1−0.0023) = **477,676.81**（需手算；不是现成产物）。

### 9.2 逐笔分解（末日 5 只，口径 C vs B）

| 标的 | 股数 | 末日开盘 | 末日收盘 | 开盘清算所得（扣费） | 收盘市值（盯市） | 差 |
|---|---:|---:|---:|---:|---:|---:|
| 301513.SZ | 900 | 44.51 | 44.38 | 39,966.86 | 39,942.00 | +24.86 |
| 601858.SH | 2,300 | 21.72 | 20.13 | 49,841.10 | 46,299.00 | +3,542.10 |
| 301313.SZ | 1,100 | 63.20 | 59.60 | 69,360.10 | 65,560.00 | +3,800.10 |
| 301428.SZ | 1,400 | 40.88 | 40.99 | 57,100.37 | 57,386.00 | −285.63 |
| **688143.SH** | **200** | **109.90** | **118.26** | **21,929.45** | **23,652.00** | **−1,722.55** |
| 合计 | 5,900 | | | 238,197.88 | 232,839.00 | +5,358.88 |

- 缺口 1,722.55 = 200×(118.26−109.90) 1,672.00 + 卖出费 50.55（`diag1` 的 `gap_price_basis` / `gap_fee`）。
- 合计差 5,358.88 与 `C−B=5,358.89` 差 0.01：逐笔 `exit_value` 是 2 位展示值。
- 源价：`D:\TSP\data\kline_daily\date=2026-10-30`（688143.SH 开 109.90 / 高 128.82 / 低 109.90 / 收 118.26 / 量 129,029）；同价快照见 `five_c_20261108/price_20261030.csv`。

---

## §10 另案登记（本次不动，逐项有归属）

| # | 事项 | 证据 | 建议归属 |
|---|---|---|---|
| X-1 | `simulate_portfolio_legacy()` 同型缺陷（`:5185` / `:5197-5210` / `:4988`），且**不认 `finalize_open_at_end`** | §1.4 | 系统开发工程师另单；若 legacy 长期不用于生产，应标 deprecated 而非修 |
| X-2 | 末日建仓（P1）是否该被拦 | 本批 0 例 | 策略负责人：拦掉会改 `n_trades`，属统计口径 |
| X-3 | 末日停牌/一字跌停不可结算（P6）的兜底价链（收盘 → 最后有效收盘 → `entry_price`，`:2778-2779`） | 本批 0 例 | 已在 S-3 写成显式回退链；`entry_price` 兜底属近似，需在报表脚注声明 |
| X-4 | `signal_next_minute` 下末日的 `_minute_trigger_price`（`:2827`）与 `pending_exit_next_open` 的交互 | 本批未启用 | 实现方在 S-1 落点后必须复审该分支，避免与终结结算抢成交 |
| X-5 | `REPORT.md`（52,097 B / `e60cd0b8…`）的 8 臂表按 D 口径 | §5.3 | 实现方重跑后由研究侧一次性换数；本契约不改报表 |
| X-6 | 生产策略文件 `D:\TSP\data\strategies\custom\custom_mw7fvp17.py`（3,478 B / `85ae72a5…`） | 基线 | 本次不动；缺陷在引擎侧，不在策略侧 |

---

## §11 变更记录

| 版本 | 时间 | 变更 | 依据 |
|---|---|---|---|
| v1.0 | 2026-11-08 20:2x | 首版：缺陷定义（D-EOS-1/2/3 + P1~P6）、四条不变量、口径决策 D-1（默认 SETTLED）、S-1~S-10、8 臂影响面、回归 R-0~R-6、方案 A/B 回滚边界、缺陷 B 结论（先记录）、另案 X-1~X-6 | engine.py `ecc3d826…`（268,800 B / 5,670 行）；`five_a/` 8 臂产物；`five_c_20261108/diag1_result.json`、`diag3_result.json`、`price_20261030.csv`、`trace_end_position.json`；`five_a/manifest.json` |

**本文件不含**：补丁、验收结论、报表改动。口径争议按 SOUL 纪律报开发经理裁定。
