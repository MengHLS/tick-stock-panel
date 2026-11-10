# S01b 基准「10% 止损」只读核查（2026-11-09）

**判定：声明本身不存在。** 不是「声明了但不生效」，也不是「有声明但被 null 覆盖」——基准臂从未绑过任何止损，全库也没有任何一处 10% 止损声明。

只读核查：未改策略/引擎/生产文件，未重跑回测，未动 `results/`、`five_a/`、registry。本目录全部为新增产物。

## 0. 核查对象

| 项 | 值 |
|---|---|
| 保存记录 | `saved_id eaaf69683a248d06`（API：`GET http://127.0.0.1:13011/api/backtest/strategy/results/eaaf69683a248d06`，HTTP 200 / 539,197 B） |
| 策略 | `custom_mw7fvp17`「双均线 20/60 金叉」，`definition_sha256 deb5eb59…`（与生产快照 `custom_mw7fvp17.py.prod_3793B_deb5eb59.py` 同一份） |
| 区间 / 配置 | 2019-07-01 ~ 2026-10-30，`max_positions 5`，`max_exposure 0.6`，`slippage 10bp`，`entry_price_basis raw`，`max_hold_days 60` |
| 系统数字 | 199 笔 / `total_return 0.2427` / `win_rate 0.3351` / `avg_pnl 0.0131` / `median_pnl −0.0964` |

> 注：后端不在 `127.0.0.1:3019`（该端口无监听），API 实际由 `127.0.0.1:13011` 提供，路径不变。以系统返回为准，未做任何重算替代。

## ① 「10% 止损」声明在哪：**五条可能路径逐一落空**

| # | 可能声明位置 | 实测 | 证据 |
|---|---|---|---|
| 1 | 策略 .py 的 `STOP_LOSS` | **`None`** | `research\s01b-20261108\prod_file_snapshots\custom_mw7fvp17.py.prod_3793B_deb5eb59.py:69` `STOP_LOSS = None` |
| 2 | `META.backtest_defaults` | **无 stop_loss 字段** | 同上 `:57-64`，只有 `trailing_peak_price / entry_price_basis / block_limit_open / finalize_open_at_end / exit_signal_requires_profit / execution_costs`；API 的 `backtest_defaults` 返回同 6 键 |
| 3 | 策略池保存的 override（策略设置页保存值） | **显式 `null`** | 盘上文件 `D:\TSP\data\user_data\strategy_overrides\custom_mw7fvp17.json` → `"stop_loss": null`、`"max_hold_days": 60`；`GET /api/strategies?include_research=true` 返回该策略 `stop_loss: null` |
| 4 | 回退链本身 | 两处都回落到策略定义值 null | `backend\app\api\strategy.py:221` `"stop_loss": overrides.get("stop_loss", s.stop_loss) if overrides else s.stop_loss`；`backend\app\backtest\strategy.py:1601` `stop_loss = self._override_value(overrides, "stop_loss", s.stop_loss)` → `:1850 stop_loss_pct=stop_loss` |
| 5 | 回测请求的 `stop_loss_pct` | **未传** | 见 ② |
| 6 | 任何文档 | **无 10% 止损** | 全仓检索 `research\` + `docs\` + `backend\`：`STOP_LOSS = -0.1`、`stop_loss = -0.1`、「10% 止损」命中 **0**；S01b 家族文档一律写 −8% |

**口径差异登记（不替使用者改口）**：S01b 家族**唯一存在的**止损声明是 **−8%**，且只绑在风控变体上——
`s01b_a1.py:53`、`s01b_a2.py:53`、`s01b_a2h.py:53`、`s01b_a3.py:53`、`s01b_a3ev.py:53` 均为 `STOP_LOSS = -0.08`；
基准 `s01b_a0.py:53`、`s01b_a0ev.py:53`、`s01b_a4.py:53` 与生产件均为 `STOP_LOSS = None`。
「10% 止损」既不是 8% 的口误来源（量级不同），也不是任何一臂的配置——系统内没有这档参数。

## ② 保存记录的实际运行配置：三处全为 null / 未传

| 字段（saved record 内） | 值 |
|---|---|
| `result.config.overrides` | `null`（整个 overrides 未传） |
| `result.strategy_info.stop_loss` | `null`（take_profit / trailing_stop / trailing_take_profit_activate / trailing_take_profit_drawdown 同为 null） |
| `result.provenance.execution.stop_loss_pct` | `null`（同段 `max_hold_days: 60`、`entry_price_basis: "raw"`、`slippage_bps: 10.0`） |
| `meta` | 只有 strategy_id / start / end / mode / asset_type，无 overrides 键 |

⇒ 引擎侧 `if config.stop_loss_pct is not None`（`engine.py:1305 / 1711 / 2179 / 4027 / 4121 / 4841`）整条分支本次运行**根本未进入**，不是「进入后被跳过」。

## ③ 199 笔的止损触发

| 项 | 数字 |
|---|---|
| `exit_reason` 分布 | `signal 136` / `max_hold 58` / `end 5` / **`stop_loss 0`** |
| 事后套用 −10%（日收盘口径，`entry_price×(1−0.10)` vs raw 收盘，窗口 entry..exit） | **125 / 199 = 62.81%** 会命中 |
| 事后套用 −10%（盘中最低价口径，引擎非建仓日的实际比较方式） | **141 / 199 = 70.85%** |
| 对照：−8% 日收盘 / 盘中最低 | 140（70.35%）/ **153（76.88%）** |

> 口径自校验：−8% 盘中最低口径的 **153 笔 = 76.88%** 与 `diag_stop_basis_20261108\REPORT.md §5` 独立算出的「153 笔 / 76.88%」**完全一致**，说明本核查的价格基（raw 平面）、窗口（entry..exit）与该诊断同口径，可交叉引用。

## ④ 死叉 136 笔为什么平均 −14.4%：**没有闸门**，不是阻塞/跳空/停牌

| 项 | 数字 |
|---|---|
| 136 笔（`exit_reason=signal`） | 均值 **−14.3808%**、中位 **−15.7253%**、合计 **−2,435,133.35**（＝派单的 −244 万） |
| 其中出场亏损 < −10% | **92 笔（67.65%）**，均值 −22.23%、中位 −20.94% |
| 这 92 笔里 `blocked_exit_days > 0` | **1 笔**（136 笔全体的 blocked 天数合计 **1 天**） |
| 这 92 笔里出场日**开盘已低于 −10% 止损价** | **91 笔（98.9%）** |
| 这 92 笔里出场日**无 K 线 / 停牌无成交** | **0 笔** |
| 跌停无法成交（`sell_limit_down`，系统统计） | **1 笔**（全 199 笔） |
| 死叉信号 → 实际成交滞后 | p50 **1** 个交易日（min 1 / max 2）＝正常 T+1 开盘成交 |
| 首次跌破 −10% 线之后**仍持有**的交易日数 | p10 **6** / p50 **20** / p90 **41** / max **56** |

**归因（按贡献排序）**：
1. **无止损闸门（决定性）**：`stop_loss_pct=null`，价格跌破任何档位都不会触发卖出，仓位只能等死叉信号出场；死叉由 MA20 下穿 MA60 定义，本质上发生在持续下跌之后，因此出场亏损天然深于任何止损档。92 笔深亏里有 91 笔在出场日开盘时早已在 −10% 线下方，中位已在线下停留 **20 个交易日**。
2. **死叉信号滞后**：信号日到成交日是正常 T+1（p50 = 1 日），不是异常延迟；但均线交叉本身滞后，叠加 60 日最长持有上限，构成 −14.4% 的分布主体。
3. **可排除**：跌停阻塞（1 笔 / 合计 1 天）、跳空穿透止损价（不是原因——因为没有止损可被穿透，91 笔只是「早就在线下」）、停牌无成交（0 笔）、数据缺行（0 笔）。

## 5. 产物与复跑

| 文件 | 内容 |
|---|---|
| `stop_loss_check.py` | 本次核查脚本（只读；`backend\.venv\Scripts\python.exe` 运行，退出码 0） |
| `summary.json` | 全部汇总数字 |
| `trade_level_stoploss_counterfactual.csv` | 199 笔逐笔：止损线、是否命中 −10%/−8%、命中日、出场日开盘、越过线后持有天数 |
| `signal_exits_136.csv` | 136 笔死叉出场明细 |
| `signal_losers_lt_minus10pct.csv` | 其中 92 笔深亏明细 |

复跑：
```
cd C:\work\sourcecode\tick-stock-panel
backend\.venv\Scripts\python.exe research\s01b-20261108\_exploration\stop-loss-check-20261109\stop_loss_check.py
```

## 6. 未确证

「10%」这个数字在系统内**找不到任何来源**：本轮检索到的唯一出处是派单文本本身。是使用者记忆偏差、还是别处（会话/口头）的表述，盘上无据可查，未做推断。
