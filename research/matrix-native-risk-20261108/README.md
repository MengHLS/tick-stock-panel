# matrix_native 能否按模块级常量吃风控（止损/止盈/最长持有）

只读查证 + 研究侧隔离跑批。**未改 `backend/app/**`、未提交、未部署、未重启、未写 `D:\TSP`。**

- 时间：2026-11-08 15:5x–16:0x（Asia/Shanghai）
- 代码仓库：`C:\work\sourcecode\tick-stock-panel`（`D:\TSP` 只是 data_root）
- 被测策略：`D:\TSP\data\strategies\custom\custom_mw7fvp17.py`（3449 B，sha256 `61c237c6cdb2a4391524c48982cd7529606f1ce9d6dabf235527ff702f94b2dd`，mtime 2026-11-08 14:19:54，**跑批前后未变**）

## 0. 结论（先给答案）

**能吃。** `EXECUTION_BACKEND = "matrix_native"` 的策略，五个模块级常量
`STOP_LOSS / TRAILING_STOP / TRAILING_TAKE_PROFIT_ACTIVATE / TRAILING_TAKE_PROFIT_DRAWDOWN / MAX_HOLD_DAYS`
全部进入 `MatcherConfig` 并在 `_simulate_portfolio_matrix` 主循环里被真实消费，**没有一个「仅 polars_expr 生效」，也没有「实现缺口」**。四类风控各有运行时证据：

| 常量 | 运行时证据（同区间同参数，各变体仅改一行常量） |
| --- | --- |
| `STOP_LOSS=-0.08` | `exit_reason=stop_loss` **94** 笔（基线 0 笔），成交笔数 56→124 |
| `TRAILING_STOP=0.05` | `exit_reason=trailing_stop` **996** 笔 |
| `TRAILING_TAKE_PROFIT_ACTIVATE=0.10 / DRAWDOWN=0.05` | `exit_reason=trailing_take_profit` **94** 笔 |
| `MAX_HOLD_DAYS=20`（原 60） | `exit_reason=max_hold` 16→**103** 笔，最长持有 60→**24** 交易日 |

## 1. 证据快照（读取时刻的字节事实）

| 文件 | 字节 | 行数 | sha256(前 16) | mtime |
| --- | --- | --- | --- | --- |
| `backend/app/strategy/engine.py` | 104,076 | **2,359** | `44ef5884a339790b` | 2026-11-05 01:57:44 |
| `backend/app/backtest/strategy.py` | 173,615 | 3,909 | `c3bfb254969efcc6` | 2026-11-07 00:01:33 |
| `backend/app/backtest/engine.py` | 268,800 | 5,670 | `ecc3d8261c5605ed` | 2026-11-07 00:01:33 |
| `backend/app/services/backtest.py` | 16,947 | 440 | `9ef30140ee555e2e` | 2026-10-26 18:07:02 |

> 派单写 `strategy/engine.py` = 104,076 B / 2,176 行：**字节数对上，行数对不上**（实测 2,359 行 = `wc -l` 与 `bytes.count(b"\n")` 同值，纯 LF）。派单里那批 `backtest/engine.py` 行号（1267-1280、1854、2295 …）本期也对不上实测（见 §3）。下文行号一律为本次实测值。

## 2. Q1：五个字段的读取点 → 转换点 → 消费点

### 2.1 读取（StrategyDef → 模块常量）

- `backend/app/strategy/engine.py:201-205`：`StrategyDef` 字段声明（`stop_loss` / `trailing_stop` / `trailing_take_profit_activate` / `trailing_take_profit_drawdown` / `max_hold_days`）
- `backend/app/strategy/engine.py:648-652`：`stop_loss=getattr(mod,"STOP_LOSS",None)`、`trailing_stop=getattr(mod,"TRAILING_STOP",None)`、`trailing_take_profit_activate=getattr(mod,"TRAILING_TAKE_PROFIT_ACTIVATE",None)`、`trailing_take_profit_drawdown=getattr(mod,"TRAILING_TAKE_PROFIT_DRAWDOWN",None)`、`max_hold_days=getattr(mod,"MAX_HOLD_DAYS",None)`

### 2.2 转换点（StrategyDef → MatcherConfig，不是 BacktestConfig）

- `backend/app/backtest/strategy.py:1601`：`stop_loss = self._override_value(overrides, "stop_loss", s.stop_loss)`（overrides 为空时就是模块常量）
- `backend/app/backtest/strategy.py:1602-1622`：`take_profit` / `trailing_stop` / `trailing_take_profit_activate` / `trailing_take_profit_drawdown` / `max_hold_days` 同法取值（前四个过 `_normalize_pct`）
- `backend/app/backtest/strategy.py:1842-1855`：构造 `MatcherConfig(... stop_loss_pct=stop_loss, take_profit_pct=take_profit, trailing_stop_pct=trailing_stop, trailing_take_profit_activate_pct=..., trailing_take_profit_drawdown_pct=..., max_hold_days=max_hold_days ...)`

**matrix_native 走这条转换点**：`matrix_native` 分支只决定「进出场信号由策略协议 `compute_signals` 生成」，随后与日线矩阵路径合流到同一个 `MatcherConfig`，再调 `engine.simulate_market_matrix`（`strategy.py:2305`）→ `_simulate_portfolio_matrix`（`engine.py:2578`）。本次实测在测试侧给 `simulate_market_matrix` 打了只读探针，撮合器**实际收到**：

```
"matcher_config_seen_by_engine": {"stop_loss_pct": -0.08, "take_profit_pct": null,
  "trailing_stop_pct": null, "trailing_take_profit_activate_pct": null,
  "trailing_take_profit_drawdown_pct": null, "max_hold_days": 60,
  "exit_fill": "open_t+1", "entry_fill": "open_t+1", "matching": "open_t+1"}
```

（`result_sl_2y.json` 内同名字段；另三个变体分别见 `result_tp_2y.json` / `result_ts_2y.json` / `result_mh_2y.json`。）

### 2.3 消费点（逐字段判定）

主循环 = `backend/app/backtest/engine.py:2578 _simulate_portfolio_matrix`。一个交易日内分四段（`engine.py:3850-3853` 的注释即官方口径）：开盘 → 同日开盘跳空风控 → 建仓 → 日内 high/low 风控 → 收盘。

| 字段 | 消费点（文件:行号） | 判定 |
| --- | --- | --- |
| `stop_loss` → `stop_loss_pct` | `engine.py:4027-4028`（日内线 `entry*(1-abs(sl))`）、`4066-4067`（低点触及按线价成交）、`3951-3971`+`3057-3119`（次日开盘跳空越线，先于计划卖单）、`4106-4123`（建仓日收盘跌破→登记次日开盘止损） | **生效** |
| `trailing_stop` → `trailing_stop_pct` | `engine.py:4029-4039`（线 = 峰值×(1-abs(ts))，峰值取 `max_close`/`max_high` 由 `trailing_peak_price` 定）、`3077-3087`（同日开盘跳空） | **生效** |
| `trailing_take_profit_activate` / `..._drawdown` | `engine.py:4040-4053`（需 `峰值/入场-1 >= activate` 才启用，回撤线 = 峰值×(1-abs(drawdown))）、`3088-3105`（同日开盘跳空） | **生效** |
| `max_hold_days` | `engine.py:4243-4244`（收盘阶段 `hold_days >= max_hold_days` → `reason="max_hold"`）；`hold_days` 计数：`3427`（建仓日置 1）、`3846`（每日开盘 +1） | **生效** |

补充：`mode="full"` 时走独立候选路径 `_simulate_independent_matrix`（`engine.py:1544`），同一批字段在 `1711-1716`、`1892` 消费，同样生效；本期实测用的是 `mode="position"`（生产默认）。

**没有「仅 polars_expr 生效」的字段。** matrix_native 与 polars_expr 共用同一个撮合器与同一个 `MatcherConfig`，风控口径完全一致，差别只在信号来源（列信号 vs `compute_signals`）。

## 3. 平行通路的澄清（派单里有两处归因需要更正）

1. **`backend/app/backtest/engine.py` 里那些 `config.stop_loss_pct` 不是 `BacktestConfig`，是 `MatcherConfig`**。`MatcherConfig` 定义在同文件 `226-243`（`stop_loss_pct` 在 `238`，`max_hold_days` 在 `243`）；`simulate()` 的签名 `engine.py:1225-1230` 明确写 `config: MatcherConfig`。所以 `engine.py:1305`、`1711`、`2179`、`3073`、`4027`、`4106`、`4837` 这些命中全部是撮合器字段，**没有一处是 BacktestConfig**。
2. **真正的 `BacktestConfig` 在 `backend/app/services/backtest.py:79`**（`stop_loss_pct` 在 `:88`，`max_hold_days` 在 `:89`），消费方式是 vectorbt 参数 `sl_stop` + 自造 `_build_max_hold_exits`（`:313-318`、`:126-145`）。这条是旧 vectorbt 通路，**matrix_native 完全不经过它**，两者互不影响：模块常量不会、也不需要被改写成 `BacktestConfig.stop_loss_pct`。
3. 派单给的 `engine.py` 行号（1267-1280、1673-1677、1854、2141-2146、2295、2951-2966、3859-3872、3938、4071、4601-4605、4750）与本仓 HEAD 实测不一致（文件 mtime 2026-11-07 00:01:33，5,670 行）。这些行号可能是旧版本读数，本节一律以实测行号为准。

## 4. Q3：同一天多个出场条件的判定顺序与成交价

全部依据 `engine.py:2578 _simulate_portfolio_matrix`（`exit_fill="open_t+1"`，本次实测配置）。

### 4.1 一日之内的分段顺序（`engine.py:3850-3853` 注释 + 代码）

1. **开盘段**（`3855-3937`）：挂单重试（`3866-3882`）→ 建仓日收盘卖点的次日补执行（`3911-3924`）→ 前一日登记的次日开盘退出（`3925-3937`）。
2. **同日开盘跳空风控**（`3951-3986`）：开盘价已越风控线 → 按开盘价卖出（`_open_risk_decision` `3057-3119`、`_open_risk_trigger_price` `2991-3010`）；否则开盘价 ≥ 止盈线按开盘价止盈（`3973-3986`）。**跳空越线优先于前一日计划的次日开盘卖单**（`3901-3906`：有跳空风控就直接 `continue`，让风控段处理）。
3. **建仓**（`3993-3999`，`entry_fill="open_t+1"` 用当日开盘价）。
4. **日内风控**（`4003-4097`）：只用截至上一交易日的峰值（`4001-4002` 注释 + `4021-4025`），先止损/移动止损/移动止盈，再止盈。
5. **收盘段**（`4100-4258`）：建仓日止损登记（`4105-4123`）→ 挂单 `close_t` 重试（`4138-4149`）→ 已登记的 `risk_exit_reason`（`4150-4157`）→ 策略卖点 `exit_signals`（`4160-4169`）→ 持仓延展策略 `hold_policy`（`4170-4242`）→ `max_hold_days`（`4243-4244`）→ 段末 `end`（`4245-4250`）。

### 4.2 谁优先（同日冲突时）

- **止损 / 移动止损 / 移动止盈三者之间不排序，取「最紧的那条线」**：`4054-4056`（`stop_price, reason = max(valid_lines, key=价格)`）与 `3106-3111`（开盘段同逻辑）。价格最高 = 最靠近当前价 = 最先被触及。
- **日内风控整体优先于策略卖点**：日内段（`4003-4097`）在收盘段（`4160+`）之前执行，且 `4130-4131` 要求「无 `next_open_exit_reason` 且无 `risk_exit_reason`」才允许登记卖点。
- **策略卖点 `exit_signals` 优先于 `max_hold_days`**：`4160` 的 `if` 分支先判卖点，`4243` 的 `max_hold` 在同一 `elif` 链上，卖点命中即跳过。
- **建仓日收盘已跌破止损线时，止损优先于同日卖点**：`4124-4136`（风控计划先写 `next_open_exit_reason`，卖点被 `not pos.get("next_open_exit_reason")` 挡掉）。
- **已挂单优先于一切重新决策**：`3866`、`4138`。
- 止盈（`take_profit_pct`）排在风控线之后、收盘条件之前（`4078-4097` / `3973-3986`）。

### 4.3 成交价口径

| 出场类型 | 触发价依据 | 成交价 | 代码 |
| --- | --- | --- | --- |
| 策略卖点 `exit_signals`（本策略的 `cross_down`） | 信号日**收盘**（`source_exit`，`2855-2868`） | **次日开盘**（`4164-4167` 登记 → `3925-3937` 次日开盘执行；`exit_prices=execution_open` 见 `2617-2621`） | `engine.py:4164-4167`、`3925-3937`、`2617-2621` |
| 止损 / 移动止损 / 移动止盈 | **当日最低价触及**（`low <= line`），或开盘即低于线 | **止损线价**；跳空开盘低于线则按**开盘价**（`4058-4067`、`2991-3010`） | `engine.py:4058-4067`、`3951-3971` |
| 止盈 `take_profit_pct` | 开盘 ≥ 线 → 开盘价；否则当日最高价 ≥ 线 → 线价（`4078-4097`） | 开盘价 / 止盈线价 | `engine.py:4078-4097` |
| `max_hold_days` | 持仓会话数（与价格无关） | **当日开盘价**（`override=None` → `exit_prices[time_id] = execution_open`，`3194-3197` + `2617-2621`） | `engine.py:4243-4244`、`3194-3197` |
| 段末 `end` | 区间末日 | 同上（当日开盘价） | `engine.py:4245-4250` |

- **止损是「当日最低价触及」，不是「收盘跌破」**（`4066`），成交价即线价，因此**不是 T+1 开盘**；只有「建仓日收盘」这一种例外会顺延到次日开盘（`4106-4123`，T+1 无法当日卖出）。
- 称 `exit_fill="open_t+1"` 只约束**信号类**出场与建仓（次日开盘），风控类出场是当日盘中价——两者口径不同，这是实现现状，不是缺陷，但会让人误以为「全部 T+1」。

### 4.4 止损成交口径的实测复核（94 笔 stop_loss）

`verify_stop_fill.py` → `stop_fill_check.json`（读 `trades_sl_2y.parquet`，止损线 = `entry_price × 0.92`，4 位小数容差 2e-5）：

| 判据 | 实测 |
| --- | --- |
| `stop_loss` 笔数 | 94 |
| 成交价 == 止损线（舍入内） | **68** |
| 成交价 **低于** 止损线（跳空，按开盘价） | **26**（最差 -19.95%，低于线均值 -13.74%） |
| 成交价 **优于** 止损线 | **0** |
| `exit_date == exit_signal_date`（当日成交） | **91** |
| 次日成交 | 3（均为建仓日收盘即跌破，按 `4106-4123` 顺延到次日开盘；样本见 `stop_fill_check.json` 的 `not_same_day`） |

0 笔「优于止损线」是这条口径的关键证据：既不是按次日开盘，也不是按收盘，而是按线价（或跳空开盘）。

## 5. Q3 实测：STOP_LOSS=None vs STOP_LOSS=-0.08

### 5.1 对比表（区间同为 2019-07-01～2021-06-30，参数完全相同）

| 变体 | 成交笔数 | 平均持有(交易日) | 最长持有 | 总收益率 | 年化 | 最大回撤 | 退出原因分布 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `STOP_LOSS=None`（基线） | **56** | **43.02** | **60** | **0.1683** | **0.0838** | -0.2351 | `end` 5 / `max_hold` 16 / `signal` 35 |
| `STOP_LOSS=-0.08` | **124** | **18.88** | **60** | **0.3067** | **0.1484** | -0.3187 | `end` 5 / `max_hold` 16 / `signal` 9 / **`stop_loss` 94** |

（另两组旁证：`TRAILING_TAKE_PROFIT 0.10/0.05` → 137 笔 / 17.32 / 60 / -0.0470 / -0.0246，`trailing_take_profit` 94 笔；`TRAILING_STOP=0.05` → 997 笔 / 1.85 / 23 / -0.6746 / -0.4406，`trailing_stop` 996 笔；`MAX_HOLD_DAYS=20` → 120 笔 / 19.36 / 24 / -0.2823 / -0.1577，`max_hold` 103 笔。）

读法：止损把亏损单提前砍掉（平均持有 43.02→18.88 交易日），腾出的仓位名额带来更多成交（56→124），总收益 16.83%→30.67%，但最大回撤同时从 -23.51% 扩大到 -31.87%（胜率 35.71%→20.97%，靠少数大赢家）。这是本次区间内的事实，不是普适结论。

### 5.2 实际命令与退出码

统一前缀 `cd C:\work\sourcecode\tick-stock-panel`：

```bash
# 基线（未改动的副本）
backend\.venv\Scripts\python.exe research\matrix-native-risk-20261108\run_risk_probe.py \
    --variant custom --start 2019-07-01 --end 2021-06-30 --tag base_2y        # rc=0
# 同上再跑一次，作为可复现性对照
backend\.venv\Scripts\python.exe research\matrix-native-risk-20261108\run_risk_probe.py \
    --variant custom --start 2019-07-01 --end 2021-06-30 --tag custom_2y      # rc=0
# STOP_LOSS=-0.08
backend\.venv\Scripts\python.exe research\matrix-native-risk-20261108\run_risk_probe.py \
    --variant custom_sl --start 2019-07-01 --end 2021-06-30 --tag sl_2y       # rc=0
# 旁证：移动止盈 / 移动止损 / 最长持有
backend\.venv\Scripts\python.exe research\matrix-native-risk-20261108\run_risk_probe.py \
    --variant custom_tp --start 2019-07-01 --end 2021-06-30 --tag tp_2y       # rc=0
backend\.venv\Scripts\python.exe research\matrix-native-risk-20261108\run_risk_probe.py \
    --variant custom_ts --start 2019-07-01 --end 2021-06-30 --tag ts_2y       # rc=0
backend\.venv\Scripts\python.exe research\matrix-native-risk-20261108\run_risk_probe.py \
    --variant custom_mh --start 2019-07-01 --end 2021-06-30 --tag mh_2y       # rc=0
# 汇总 / 止损成交口径复核
backend\.venv\Scripts\python.exe research\matrix-native-risk-20261108\summarize.py         # rc=0
backend\.venv\Scripts\python.exe research\matrix-native-risk-20261108\verify_stop_fill.py  # rc=0
```

退出码原文见 `run_exit_codes.txt`；每个变体的完整 stdout 见 `log_<tag>.txt`（含 `[strategy]` 段：策略从哪个目录加载、五个常量读到了什么）。

**可复现性**：`trades_base_2y.parquet` 与 `trades_custom_2y.parquet` sha256 完全相同（`99889cb1902e1227ed8125a9aefd95297c2d7d79e9c5310c8e80ad5ae5318686`），headline / 退出原因 / 持有天数三项逐字段相等 —— 同一输入两次跑批结果一致。

### 5.3 一个值得记录的细节：`max_hold` 阈值不是硬上界

`MAX_HOLD_DAYS=20` 变体里有 1 笔持有 24 交易日（`300748.SZ`，2019-08-26→2019-09-30，`blocked_exit_days=4`）：`max_hold` 在收盘段登记退出，但跌停/停牌被卖不出去时会走 `pending_exit` 顺延（`engine.py:3286-3297`、`3134-3145`），因此持有天数可超过阈值。基线（60）与 `-0.08` 两组的 `max_hold` 恰好都停在 60，没有超界样本。

## 6. 未证 / 边界

1. **未证**：`take_profit_pct`（固定止盈）本期没有单独跑 A/B（`TAKE_PROFIT` 不在五个字段里，`custom_mw7fvp17.py` 也未声明）。消费点仅按代码核对（`engine.py:3973-3986`、`4078-4097`），无运行时数字。
2. **未证**：`mode="full"`（独立候选路径 `_simulate_independent_matrix`）下的同一批常量，只按代码核对（`engine.py:1711-1716`、`1892`），未跑批。
3. **未证**：`close_t` 成交口径（`exit_fill="close_t"`）下的风控行为，本次全部跑批都是 `open_t+1`。
4. 未做的取舍：区间选了 2019-07-01～2021-06-30（两年、覆盖一轮完整趋势与回撤），没有跑全历史或分年；数字只代表该区间。
5. 派单里的 `strategy/engine.py` = 2,176 行、以及 `backtest/engine.py` 那批行号，与实测不一致（见 §1、§3），未追查旧版本来源。
6. 未提交、未部署、未重启服务、未接线任何生产流程；`backend/app/**` 本次零改动（四个相关文件的 mtime 均早于本次会话：2026-11-05 / 2026-11-07 / 2026-10-26），`find backend/app -newermt "2026-11-08 15:50"` 为空。
7. **`D:\TSP` 写盘归属**：本次跑批的每一处写入都落在 `research/matrix-native-risk-20261108/data_root/`（`find` 清单：矩阵缓存 + `strategies/*/__pycache__`），`D:\TSP\data\strategies\custom\custom_mw7fvp17.py` sha256 与 mtime 跑批前后一致。同期 `D:\TSP\data` 下确有 `capabilities.json` / `logs/backend.log` 在 16:01:58 被写，来自常驻后端进程的每小时 capabilities 复探（日志原文：`Job "start_scheduler.<locals>._reprobe_capabilities (trigger: interval[1:00:00], next run at: 17:01:50 CST)"`），不是本次跑批——跑批进程启动即断言 `settings.data_dir == research data_root`，否则拒绝运行。

## 7. 落盘清单

| 文件 | 内容 |
| --- | --- |
| `run_risk_probe.py` | 跑批入口：`DATA_DIR` 指向本目录 `data_root`（并断言，防写 `D:\TSP`），走生产路径 `StrategyBacktestService.run`，测试侧只读探针记录撮合器实收的 `MatcherConfig` |
| `verify_stop_fill.py` / `stop_fill_check.json` | 止损成交口径反查（线价/跳空/优于线/同日） |
| `summarize.py` / `summary.json` / `summary_table.txt` | 五变体汇总表 |
| `result_<tag>.json`、`trades_<tag>.parquet`、`log_<tag>.txt` | 每个变体的完整结果、逐笔成交、stdout |
| `run_exit_codes.txt` | 六次跑批的退出码 |
| `data_root/strategies/{custom,custom_sl,custom_tp,custom_ts,custom_mh}/custom_mw7fvp17.py` | 研究侧策略副本，与源文件逐字节相同，仅风险常量各行一行差异（`diff` 输出见 `README` 正文与各变体证据） |
| `data_root/`（其余） | 行情目录全部是 junction 指向 `D:\TSP\data\*`，只读；`strategies/` 是本目录内真实目录 |
