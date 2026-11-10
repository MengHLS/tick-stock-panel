# ⑤-c 诊断 1：期末权益 1,722.56 缺口的成因

## ① 行情核对（D:\TSP\data\kline_daily）

| symbol | 开 | 高 | 低 | 收 | 前收 | 开/前收 | 收/前收 | 量 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 301313.SZ | 63.20 | 66.50 | 58.86 | 59.60 | 64.82 | -2.50% | -8.05% | 251,704 |
| 301428.SZ | 40.88 | 44.30 | 39.52 | 40.99 | 42.50 | -3.81% | -3.55% | 224,677 |
| 301513.SZ | 44.51 | 47.28 | 44.30 | 44.38 | 46.25 | -3.76% | -4.04% | 23,829 |
| 601858.SH | 21.72 | 21.88 | 20.13 | 20.13 | 22.37 | -2.91% | -10.01% | 141,462 |
| 688143.SH | 109.90 | 128.82 | 109.90 | 118.26 | 123.01 | -10.66% | -3.86% | 129,029 |

688143.SH 2026-10-30：**开盘 109.90 / 收盘 118.26**。trades 记的 exit_price=109.90（等于开盘：True）；末行权益的持仓市值 23652.00 = 200×118.26（等于收盘盯市：True）。

## ② 1,722.56 的分解

| 项 | 值 |
|---|---:|
| 收盘盯市值 shares×close | 23652.00 |
| trades 记的 exit_value | 21929.45 |
| **合计缺口** | **1722.55** |
| 其中 价基差 shares×(close−open) | 1672.00 |
| 其中 卖出费用 (shares×open − exit_value) | 50.55 |
| 分解校验（两项相加） | 1722.55 |
| Σpnl − 权益变动（独立口径） | -1722.56 |
| 开发经理的 23,652.00 − 21,929.45 | 1722.55 |

末现金 461641.78 + 该笔 exit_value 21929.45 = finalize 后现金 483571.23；闭式 (1,000,000 − Σentry + Σexit) = 483571.12，差 +0.11（分位取整）。

## ③ 各臂同一恒等式

| 臂 | finalize | 成本策略 | 末行持仓 | 末行市值 | Σpnl | 权益变动 | gap | 延后卖出笔数 | gap 含义 |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| base_nodefaults_10bp | False | False | 1 | 23652.00 | -516428.78 | -514706.22 | -1722.56 | 1 | 期末延后卖出 |
| only_entry_price_basis_raw | False | False | 1 | 23652.00 | -567012.05 | -565289.47 | -1722.58 | 1 | 期末延后卖出 |
| only_block_limit_open | False | False | 1 | 47304.00 | 117814.21 | 121259.36 | -3445.15 | 1 | 期末延后卖出 |
| only_finalize_open_at_end | True | False | 5 | 232839.00 | -483892.16 | -521787.66 | 37895.50 | 0 | n/a（finalize 臂：pnl 记 0，gap 不是本缺陷） |
| only_execution_costs | False | True | 1 | 23652.00 | -516301.91 | -514579.31 | -1722.60 | 1 | 期末延后卖出 |
| only_trailing_peak_price_close | False | False | 1 | 23652.00 | -516428.78 | -514706.22 | -1722.56 | 1 | 期末延后卖出 |
| only_exit_signal_requires_profit | False | False | 0 | 0.00 | -326201.22 | -326201.24 | 0.02 | 0 | 期末延后卖出 |
| base_nodefaults_gross | False | False | 1 | 23652.01 | -474597.25 | -472925.25 | -1672.00 | 1 | 期末延后卖出 |
| a0_10bp_199 | True | True | 5 | 699318.00 | 326858.21 | 242725.28 | 84132.93 | 0 | n/a（finalize 臂：pnl 记 0，gap 不是本缺陷） |

## ④ 2026-10-30 引擎调用序列（sys.settrace，只读）

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
