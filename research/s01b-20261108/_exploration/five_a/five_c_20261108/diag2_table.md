# ⑤-c 诊断 2：两臂同键价格为何全不同

## 结论

**③ + ①**：199 笔臂（`a0_10bp`，策略文件 `s01b_a0.py` 内 6 个 `backtest_defaults` 键）打开了 `execution_costs` 策略，引擎在 `_fill_price()` 里把 10bp 滑点乘进**成交价**再落盘；⑤-a 的单键 raw 臂（`only_entry_price_basis_raw`）没有成本策略，滑点走 `_core_buy_cost_pct()/_core_sell_cost_pct()` 的**现金成本**，`trades.entry_price` 存的是**报价**。同名列存了两个不同的量。

**② 不成立**：两臂都真的吃到 raw。a0 的价格 ÷ 1.001 与 raw 臂价格逐笔相等（102/102）。

## 判据

| 判据 | 实测 | 结果 |
|---|---|---|
| T1 a0/raw 入场价比 == 1.001 | 102/102 命中，极值 1.0009885 ~ 1.0010163 | 成立 |
| T2 a0/raw 出场价比 == 0.999 | 99/102 命中，3 笔为例外（期末未平仓，口径不同） | 成立 |
| T3 同族对照 base→only_execution_costs 比值 == 1.001 | 208/208 命中 | 成立（与价基无关） |
| T4 a0 META 有 execution_costs | 是 {'min_commission': 5.0, 'transfer_fee_pct': 2e-06} | 成立 |
| T4 raw 臂 resolved execution_costs | None | 成本策略缺席 |
| T5 a0 ÷ 1.001 == raw 臂价格 | 102/102 | 成立（raw 真吃到） |

## 代码位置（只读引用）

| 位置 | 作用 |
|---|---|
| `engine.py:2807-2817` `_fill_price` | `config.execution_costs` 非空时调用 `policy.fill_price(price, side, slippage_bps)`——滑点乘进价格 |
| `engine.py:211-222` `ExecutionPolicy.fill_price` | `price × (1 ± bps/10000)`，`_round_half_up(..., price_decimals)` |
| `engine.py:318-325` `_core_buy_cost_pct/_core_sell_cost_pct` | 无成本策略时 `佣金 + 印花税 + slippage_bps/10000` 走现金成本 |
| `engine.py:2819-2825` `_trade_cost` | 两条路的费用分量不同 |

## 例外 3 笔（出场腿）

| symbol | entry | exit | raw 臂出场价 | a0 出场价 | 比值 |
|---|---|---|---:|---:|---:|
| 301513.SZ | 2026-10-13 | 2026-10-30 | 44.51 | 44.38 | 0.997079 |
| 601858.SH | 2026-10-16 | 2026-10-30 | 21.72 | 20.13 | 0.926796 |
| 301428.SZ | 2026-10-29 | 2026-10-30 | 40.88 | 40.99 | 1.002691 |

## 对引用口径的影响

1. ⑤-a 臂 1 的 **−5.06pp** 是「单键 raw + 滑点走现金成本」的位移，**可以**作为 raw 价基的单项位移引用；但不可与 199 笔臂的任何 Δ 互换，因为 199 笔臂的滑点在价上、股数按含滑点价折算。
2. 任何跨臂比价必须先除/乘 `1 ± slippage_bps/10000`，否则会读出 0.1% 的伪价差（102/102 笔）。
3. `trades.entry_price` 的含义随臂变：有成本策略=成交价，无成本策略=报价。跨臂汇总必须带「该臂是否有 execution_costs」。
