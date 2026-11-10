# ⑤-c 两问只读诊断（2026-11-08）

范围：只读复算，不改引擎、不改任何收益数字、不改 `REPORT.md`。产物目录 `research/s01b-20261108/five_a/five_c_20261108/`。

## 0 · 结论

**问 1（1,722.56）→ 证成。** 开发经理的算术逐项对上：该笔期末持仓在 trades 里按 2026-10-30 **开盘价 109.90** 虚拟成交并扣卖出费，落成 `exit_value = 21929.45`；末行权益却按**收盘价 118.26** 盯市，市值 `23652.00`。差 `1722.55 = 价基差 1672.00（200×8.36）+ 卖出费 50.55`。独立口径 Σpnl − 权益变动 = `-1722.56`，与 1,722.56 差 0.01（分位取整）。

**问 2（两臂同键价格全不同）→ 三个选项里是 ③（+①）。** `a0_10bp` 臂的策略 META 带了 `execution_costs` 策略，引擎 `_fill_price()` 把 10bp 滑点乘进**成交价**再落盘；⑤-a 的单键 raw 臂没有成本策略，滑点走 `_core_buy_cost_pct/_core_sell_cost_pct()` 的**现金成本**，`trades.entry_price` 存的是**报价**。同名列存了两个不同的量。两臂都真吃了 `raw`（a0 价格 ÷ 1.001 与 raw 臂价格 102/102 逐笔相等），② 不成立。证据是 102/102 笔比值恒为 1.001、208/208 笔同族对照也恒为 1.001。

## 1 · 诊断 1：期末权益 1,722.56

### 1.1 与开发经理给的数逐项对账

| 开发经理的数 | 本诊断实测 | 一致 |
|---|---|---|
| trades 208 笔 Σpnl = −516,428.78 | -516428.78 | ✅ |
| 权益 1,000,000 → 485,293.78，变动 −514,706.22 | -514706.22 | ✅ |
| 差 1,722.56 | -1722.56 | ✅ |
| 末行 value 485,293.78 / cash 461,641.78 / 持仓市值 23,652.00 | 485293.78 / 461641.78 / 23652.00 | ✅ |
| 在仓 688143.SH，200 股，exit_price 109.90，exit_value 21,929.45，`open_at_end=False`，`exit_reason=end` | 200 股 / 109.90 / 21929.45 / False / end | ✅ |
| 23,652.00 − 21,929.45 = 1,722.55 | 1722.55 | ✅（差 0.01） |
| 1,000,000 − Σentry + Σexit = 483,571.12，末现金 461,641.78，差 21,929.34 | 闭式 483571.12 / 末现金 461641.78 / 差 -21929.34 | ✅ |

### 1.2 ① 行情核对（`D:\TSP\data\kline_daily`，date=2026-10-30）

| symbol | 开 | 高 | 低 | 收 | 前收 | 开/前收 | 收/前收 | 成交量 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 688143.SH | 109.90 | 128.82 | 109.90 | 118.26 | 123.01 | -10.66% | -3.86% | 129,029 |
| 301513.SZ | 44.51 | 47.28 | 44.30 | 44.38 | 46.25 | -3.76% | -4.04% | 23,829 |
| 601858.SH | 21.72 | 21.88 | 20.13 | 20.13 | 22.37 | -2.91% | -10.01% | 141,462 |
| 301313.SZ | 63.20 | 66.50 | 58.86 | 59.60 | 64.82 | -2.50% | -8.05% | 251,704 |
| 301428.SZ | 40.88 | 44.30 | 39.52 | 40.99 | 42.50 | -3.81% | -3.55% | 224,677 |

688143.SH 当日**开盘 109.90、收盘 118.26**，成交量 129,029 股。trades 的 `exit_price` 恰等于开盘价（差 <1e-6）；末行权益的持仓市值恰等于 200×收盘（差 <0.02）。两条都命中。

### 1.3 缺口分解

| 项 | 值 |
|---|---:|
| 收盘盯市值 200×118.26 | 23652.00 |
| trades 记的 exit_value | 21929.45 |
| **缺口** | **1722.55** |
| ├ 价基差 200×(118.26−109.90) | 1672.00 |
| └ 卖出费用 200×109.90 − 21,929.45 | 50.55 |
| 分解校验 | 1722.55 |

末现金 461641.78 + 该笔 exit_value 21929.45 = finalize 后现金 483571.23；闭式 `1,000,000 − Σentry + Σexit` = 483571.12，差 +0.11（208 笔逐个 round 2dp 的舍入）。也就是说：**这笔钱最终确实进账了，只是没进末行权益。**

### 1.4 ② 为什么只有这只没在循环里被平掉

2026-10-30（time_id 1778）生产引擎的真实调用序列（`sys.settrace` 抓取，`trace_end_position.json`；asset 4962 = 688143.SH，pos 202）：

| 函数 | asset | pos | reason | 返回 | 当时持仓数 |
|---|---|---:|---|---|---:|
| _exit_signal_at | 4962 | None | None | None | None |
| _exit_signal_at_return | 4962 | None | None | True | None |
| _exit_signal_at | 2939 | None | None | None | None |
| _exit_signal_at_return | 2939 | None | None | False | None |
| _try_sell | None | 204 | end | None | 5 |
| _sell | None | 204 | end | None | 5 |
| _sell_return | 2939 | None | None | None | None |
| _try_sell_return | 2939 | None | None | True | None |
| _exit_signal_at | 4049 | None | None | None | None |
| _exit_signal_at_return | 4049 | None | None | False | None |
| _try_sell | None | 205 | end | None | 4 |
| _sell | None | 205 | end | None | 4 |
| _sell_return | 4049 | None | None | None | None |
| _try_sell_return | 4049 | None | None | True | None |
| _exit_signal_at | 2836 | None | None | None | None |
| _exit_signal_at_return | 2836 | None | None | False | None |
| _try_sell | None | 206 | end | None | 3 |
| _sell | None | 206 | end | None | 3 |
| _sell_return | 2836 | None | None | None | None |
| _try_sell_return | 2836 | None | None | True | None |
| _exit_signal_at | 2909 | None | None | None | None |
| _exit_signal_at_return | 2909 | None | None | False | None |
| _try_sell | None | 207 | end | None | 2 |
| _sell | None | 207 | end | None | 2 |
| _sell_return | 2909 | None | None | None | None |
| _try_sell_return | 2909 | None | None | True | None |
| _sell | None | 202 | end | None | 1 |
| _sell_return | 4962 | None | None | None | None |

链条（行号为 `backend/app/backtest/engine.py`，只读引用，未修改）：

1. 日内循环 `for position_id in list(positions)`（:4100）对每个持仓调 `_exit_signal_at`（:4161）。4 只（301513 / 601858 / 301313 / 301428）返回 **False**，于是走到 :4243-4249 的 `time_id == time_count-1 and not finalize_open_at_end` 分支拿到 `reason='end'`，在**循环内**按开盘价卖出、现金入账。
2. 688143.SH 的 `_exit_signal_at` 返回 **True** 且 `_exit_signal_profit_armed` 通过，命中 :4164-4167 的 `open_t+1` 分支：只写 `pos['next_open_exit_reason']='signal'` 然后 **`continue`**——直接跳过后面的 `end` 分支，循环内根本没卖。
3. 循环内 4 笔卖完后，:4342 才追加当天的权益行：`cash = 461,641.78`（4 笔已入账）、`positions = 1`、`value = cash + 200×118.26 = 485,293.78`。**这一行是「四笔按开盘成交 + 一笔按收盘盯市」的混合口径。**
4. 循环结束后（:4400 的 `else` 分支，`finalize_open_at_end=False`）再对剩余持仓调 `_sell(last_time, …, reason='end')`——按最后一个有效日的**开盘价**成交、扣费；现金变成 483,571.23。**但权益行早已写死。**

所以：不是停牌、不是跌停（当日 −10.66%，科创板 ±20%）、不是额度，而是**末日信号闩锁 `continue` 抢先吃掉了 `end` 出口**。

### 1.5 ③ 判定：这是「trades 记虚拟成交、权益不认这笔现金」的口径不一致

**判缺陷（P3：量级小，但破坏 trades↔权益的可对账性）。** 两种自洽口径的末值都算得出来（诊断 3，明细见 1.5b）：纯收盘盯市 **B = 478,212.34**、全按末日开盘虚拟清算 **C = 483,571.23**；报告值 **D = 485,293.78** 既不等于 B（+7,081.44），也不等于 C（+1,722.55），是「4 笔已成交 + 1 笔未成交」的混合值。后果：报告口径 total_return -51.4700% 比「全部按期末开盘价清仓」的 -51.6429% 高估 0.1729pp；年化 -9.73% vs -9.78%。任何 Σpnl↔权益 对账都会差这一笔。

### 1.5b 三种口径的末值对账（诊断 3）

| 口径 | 末值 | 与别人的关系 |
|---|---:|---|
| B 纯收盘盯市（5 只全按 2026-10-30 收盘） | 478,212.34 | = `only_finalize_open_at_end` 臂末值 478,212.34（True，跨臂交叉验证） |
| C 全按末日开盘虚拟清算 | 483,571.23 | 闭式 483,571.12，差 +0.11（208 笔 2dp 舍入） |
| D 报告值（4 笔已成交 + 1 笔盯市） | 485,293.78 | 比 B 高 +7,081.44、比 C 高 +1,722.55 |

末行现金 461,641.78 的构成也拼得出：2026-10-29 现金 245,373.34 + 循环内 4 笔 exit_value 216,268.43（301513.SZ, 601858.SH, 301313.SZ, 301428.SZ）= 当日入账 216,268.44；未入账的那一笔就是 688143.SH 的 21,929.45，finalize 后现金 483,571.23。**B 恰好等于 finalize 臂的末值**，说明「全部按收盘盯市」是一个引擎自己就能产出的自洽口径，而默认臂的末值落在 B 与 C 之间，谁都不是。

各臂同一恒等式（D = 循环内未卖、由 finalize 分支按开盘价卖掉的持仓，用「shares×close 子集和 == value−cash」暴力匹配确定，不靠人眼挑）：

| 臂 | 单一开关 | finalize | 成本策略 | 末行持仓 | 末行市值 | Σpnl | 权益变动 | gap | 延后卖出 | 含义 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| `base_nodefaults_10bp` | 基线（不注入） | False | False | 1 | 23652.00 | -516428.78 | -514706.22 | -1722.56 | 1 | 期末延后卖出 |
| `only_entry_price_basis_raw` | entry_price_basis=raw | False | False | 1 | 23652.00 | -567012.05 | -565289.47 | -1722.58 | 1 | 期末延后卖出 |
| `only_block_limit_open` | block_limit_open=true | False | False | 1 | 47304.00 | 117814.21 | 121259.36 | -3445.15 | 1 | 期末延后卖出 |
| `only_finalize_open_at_end` | finalize_open_at_end=true | True | False | 5 | 232839.00 | -483892.16 | -521787.66 | 37895.50 | 0 | n/a：finalize 臂的 pnl 记 0，gap 是另一件事 |
| `only_execution_costs` | min_commission=5 + transfer_fee_pct=2e-06 | False | True | 1 | 23652.00 | -516301.91 | -514579.31 | -1722.60 | 1 | 期末延后卖出 |
| `only_trailing_peak_price_close` | trailing_peak_price=close | False | False | 1 | 23652.00 | -516428.78 | -514706.22 | -1722.56 | 1 | 期末延后卖出 |
| `only_exit_signal_requires_profit` | exit_signal_requires_profit=true | False | False | 0 | 0.00 | -326201.22 | -326201.24 | 0.02 | 0 | 期末延后卖出 |
| `base_nodefaults_gross` | 成本全零（gross） | False | False | 1 | 23652.01 | -474597.25 | -472925.25 | -1672.00 | 1 | 期末延后卖出 |
| `a0_10bp_199` | S01b 199 笔注入臂（对照） | True | True | 5 | 699318.00 | 326858.21 | 242725.28 | 84132.93 | 0 | n/a：finalize 臂的 pnl 记 0，gap 是另一件事 |

读法：非 finalize 臂的 `gap` 全部由「延后卖出的那一笔」贡献，`gap = −(shares×close − exit_value)`。gross 臂 `gap = −1,672.00` 正好等于纯价基差（成本全零 ⇒ 无 50.55 费用），是这条恒等式最干净的验证。`only_exit_signal_requires_profit` 臂末日没有延后持仓（末日无 signal），`gap ≈ 0`。`only_finalize_open_at_end` / `a0_10bp_199` 是 finalize 臂：期末持仓按 `open_at_end` 落账、`pnl_amount` 记 0，它们的 gap 属于另一类（价差法 vs pnl 法），不在本缺陷范围内。

### 1.6 修法与影响面（只报，未实施）

**方案 A（推荐，改一处顺序）**：:4243 的 `end` 判定提到信号闩锁之前——`time_id == time_count-1 and not finalize_open_at_end and not carry_out` 时直接取 `reason='end'`，不再让 :4164 的 `continue` 抢先。收益：交易日少一次循环外用 `_sell`，权益行与 trades 同口径。风险：末日信号出场的 `exit_reason` 会从 `end` 保持 `end`（现在是 `end`，不变），但 `next_open_exit_reason` 不再被写入，跨段 carry_out 路径需回归。
**方案 B（改一处收尾）**：finalize 之后把最后一行权益/回撤按 finalize 现金重写，并同步 `statistics`；影响 `len(equity_values)`（年化用 252/len），会动到所有年化数字，风险更大。
**影响面**：凡是 `finalize_open_at_end=False`（生产默认）且**末根 K 线持仓仍有已武装卖点**的回测都会命中。本批 8 臂里 6 臂命中（各 1 笔），量级 1722.56 元 / 0.17pp；`block_limit_open` 臂因为股数 400，量级翻倍到 3445.15 元 / 0.35pp。对相对结论（臂间排序）无影响，但**所有引用绝对收益的地方都带这 0.17~0.35pp 的高估**。

## 2 · 诊断 2：两臂「都声明 raw」却同键价格全不同

裁定：**③ + ①**。③ 第三支键（execution_costs 策略）+ ① 同名列存不同量（成交价 vs 报价）；② 不成立——两臂都真吃了 raw（见 T5）。

| 判据 | 实测 | 结论 |
|---|---|---|
| T1 a0/单键 raw 臂入场价比 == 1.001 | 102/102 笔命中，极值 1.0009885 ~ 1.0010163 | 成立 |
| T2 出场价比 == 0.999 | 99/102 命中，3 笔例外 | 成立 |
| T3 同族对照 base→only_execution_costs 比值 == 1.001 | 208/208 | 成立（与价基无关） |
| T4 a0 META 有 execution_costs | {'min_commission': 5.0, 'transfer_fee_pct': 2e-06} | 成立 |
| T4 单键 raw 臂 resolved.execution_costs | None | 成本策略缺席 |
| T5 a0 ÷ 1.001 == raw 臂价格 | 102/102 | 成立 ⇒ raw 真吃到，排除 ② |

3 笔出场例外全部是 a0 的期末未平仓（`finalize_open_at_end=True` 按最后收盘价落账），与 raw 臂的「次日开盘虚拟成交」本来就不同口径，不是价基问题：

| symbol | entry | exit | raw 臂出场价 | a0 出场价 | 比值 |
|---|---|---|---:|---:|---:|
| 301513.SZ | 2026-10-13 | 2026-10-30 | 44.51 | 44.38 | 0.997079 |
| 601858.SH | 2026-10-16 | 2026-10-30 | 21.72 | 20.13 | 0.926796 |
| 301428.SZ | 2026-10-29 | 2026-10-30 | 40.88 | 40.99 | 1.002691 |

机制（只读引用）：

| 位置 | 作用 |
|---|---|
| `engine.py:2807-2817` `_fill_price` | `config.execution_costs` 非空 ⇒ `policy.fill_price(price, side, slippage_bps)`，滑点乘进价格 |
| `engine.py:211-222` `ExecutionPolicy.fill_price` | `price × (1 ± bps/10000)`，`_round_half_up(..., price_decimals)` |
| `engine.py:318-325` `_core_buy_cost_pct/_core_sell_cost_pct` | 无成本策略 ⇒ `佣金 + 印花税 + slippage_bps/10000` 进现金成本，价格保持报价 |

### 对引用口径的影响

1. 第 1 臂的 **−5.06pp** 是「单键 raw + 滑点走现金成本」的位移，可以作为 raw 价基的单项位移引用；但**不可与 199 笔臂的任何 Δ 互换**——199 笔臂的滑点在价上、股数按含滑点价折算（同键股数只有 9/102 相同）。
2. 任何跨臂比价先除/乘 `1 ± slippage_bps/10000`，否则会读出 0.1% 的伪价差（102/102 笔）。
3. `trades.entry_price` 的含义随臂变：有 `execution_costs` 策略=**成交价**，无成本策略=**报价**。跨臂汇总必须标注「该臂是否有 execution_costs」。

### 2.5 199 臂 vs 208 基线：同键价全不同属于价基（诊断 3）

开发经理另算的「199 臂 vs 208 基线同键 111 笔：`entry_price`/`exit_price` 111/111 不同、shares 105/111 不同」不是异常：两臂的 `entry_price_basis` 本来就不同（base resolved = **adjusted**，a0 = **raw**），再加上 a0 的 1.001 滑点。逐笔验证：a0 入场价 ÷ base 入场价 × (adj/raw) = 1.001 命中 109/111 笔。

| 例外 symbol | entry | a0 入场价 | raw×1.001 应为 | 差 | 成因 |
|---|---|---:|---:|---:|---|
| 300530.SZ | 2020-03-25 | 26.5599 | 39.84 | -13.28 | ÷1.5000 送股重算（entry_price 按送股后重算） |
| 920262.BJ | 2025-04-15 | 26.9500 | 35.03 | -8.08 | ÷1.3000 送股重算（entry_price 按送股后重算） |

即：**① 同名列存不同量（base 存 adjusted、a0 存含滑点 raw）+ 2 笔送股重算**；不是定价错，也不是任一臂没吃到 `raw`。任何跨臂比价先 `/ (adj÷raw)` 再 `/ 1.001`。

## 3 · 复跑命令与退出码

工作目录 `research/s01b-20261108/five_a/five_c_20261108/`，解释器 `backend/.venv/Scripts/python.exe`：

| 命令 | 作用 | 退出码 |
|---|---|---|
| `python diag1_end_gap.py` | 诊断 1 全量复算 → `diag1_result.json` / `diag1_table.md` | 0 |
| `python diag2_price_basis.py` | 诊断 2 判据 T1–T5 → `diag2_result.json` / `diag2_table.md` | 0 |
| `python diag3_reconcile.py` | 诊断 3 三种口径对账 + 199/208 价基归属 → `diag3_result.json` / `diag3_table.md` | 0 |
| `python verify_five_c.py` | 60 项断言 + 产物清单 → `verify_five_c_result.txt`（pass=60） | 0 |
| `python gen_report.py` | 生成本报告 + `manifest_five_c.json` | 0 |

`diag_end_position.py` 是上一轮的 trace 采集器（`python diag_end_position.py`，退出码 0，实测 208 笔 / 10.7s / 22,584 事件），`trace_end_position.json` 由它产出，本报告 1.4 节的调用序列直接从该文件读。

## 4 · 产物 sha256

| 文件 | 字节 | sha256 |
|---|---:|---|
| `diag1_end_gap.py` | 16,787 | `563fe26b0d14c104a8cad36ea50b1360…` |
| `diag1_result.json` | 16,990 | `8f1ca647d751e06fa099f9b40f460ad1…` |
| `diag1_table.md` | 4,495 | `bf0092b7c0e1904031ca470dff86fa93…` |
| `diag1_stdout.txt` | 1,517 | `565a7b0dbab2373db46d6a58a7ba778c…` |
| `diag2_price_basis.py` | 10,425 | `6080dff3ff0f37a9f41e9effb14abf87…` |
| `diag2_result.json` | 2,224 | `14a89a5aa62538c313ea9c26e0c4305e…` |
| `diag2_table.md` | 2,744 | `d044264c6e38b520babfdcee99ea5da5…` |
| `diag3_reconcile.py` | 10,794 | `257fdc21ebc8d6e7d0f6f5d90cd9878b…` |
| `diag3_result.json` | 2,739 | `6df45b581d124c4d4ead8ac90a5b1f18…` |
| `diag3_table.md` | 1,479 | `04e8c6b5b808107dd89c79c245a23aeb…` |
| `diag3_stdout.txt` | 2,741 | `c57ec53f31b85825a1e603119ddec0ec…` |
| `verify_five_c.py` | 12,870 | `c137c9cf3398e26274e8bbdb0cd94aa6…` |
| `verify_five_c_result.txt` | 6,297 | `ac695429d49c518f8d5302eda25d3b9b…` |
| `gen_report.py` | 21,168 | `18a67d5dfe84ce21355e1d07a86730c8…` |
| `price_20261030.csv` | 684 | `e711cb810d9fa5d8a10b70721bbfbdb6…` |
| `diag_end_position.py` | 5,495 | `d74e7032fc012b69fbaf8beb183bcc0e…` |
| `trace_end_position.json` | 207,627 | `899787c6ad54f177eb812af5a3f913ef…` |
| `trace_run.log` | 936 | `3e81ac1cc7a05db4a915f0be7ee324b4…` |

完整 64 位与报告自身 sha 见 `manifest_five_c.json`。

## 5 · 未验证 / 未做

1. 未改引擎、未实施 1.6 的修法，等批。影响面是「同一恒等式的命中条件」，未做全仓（其它策略、其它区间）的命中率统计。
2. 199 笔臂的价格差异已由「价基 adjusted vs raw × 1.001 滑点」完整解释（109/111 精确命中，2 笔例外是送股重算），但**未穷举验证**是否还存在其它同样会改价的键（例如 `entry_fill` / limit 相关的键）；111/111 的闭合已使其没有余地。
3. `a0_10bp` 无 `effective_config.json`，其 finalize/成本策略取自策略文件 META（`strategies/custom/s01b_a0.py`），不是引擎 resolved 值。
4. 跨臂一律权益锚定口径（`pnl_amount`，`open_at_end` 笔用 `exit_value−entry_value`）；`12.18%` / `2.61%` 已撤回，本报告未再使用。