# S01b 风控变体：实施 + 四臂验证报告

- 日期：2026-11-08（Asia/Shanghai）
- 任务来源：开发经理派单（规格来自策略经理 S01b）
- 仓库：`C:\work\sourcecode\tick-stock-panel`；数据根 `D:\TSP`
- 纪律：未提交、未部署、未重启服务、未写 `D:\TSP` 生产库 strategy row、未碰 `dsl.py` / 信号链 / 回测引擎核心 / `store.py`、未改其它 11 条策略、未改研究侧台账文件。

## 0. 结论摘要

1. **策略文件已改好**（`D:\TSP\data\strategies\custom\custom_mw7fvp17.py`，5,510 B / `918254f0…`；备份 `.bak_20261108` 原样 3,449 B / `61c237c6…`。5,392 B / `4118aa61…` 是**加 `META.description` 状态标注前**的版本，已存 `research/s01b-20261108/prod_file_snapshots/custom_mw7fvp17.py.pre_note_5392B_4118aa61.py`，重跑证明两者交易逐笔相同），前端策略列表实测可直接选到「双均线 20/60 金叉 · 风控退出（S01b 变体）」。另把四臂用的 4 项撮合/成本口径写进 `META.backtest_defaults`，**用生产文件自身重跑 = 臂 3 逐字段相同、trades 表 `equals()=True`**（§1.1）——否则前端选它直接跑会走 adjusted 价、最低佣金 0，跑出与四臂表不同的数。
2. **cross_down 改事件式后逐笔完全一致**：臂 0 与臂 3 两个配置下，事件式与水平式逐笔（symbol/entry_date/exit_date/exit_reason/pnl…）全等（199/199、1135/1135）。
3. **移动止盈首次启用的已知答案用例通过**：`exit_reason="trailing_take_profit"` 原值、成交价 = 峰值 × 0.92（close 口径）、触发日 = 最低价跌破线当日。
4. **`trailing_peak_price` 不能在策略模块固定**（模块常量入口只有 5 个名字，无此项）；只能写在 `META["backtest_defaults"]["trailing_peak_price"]="close"`，请求体 `StrategyBacktestRequest` 没有该字段。
5. **四臂结果：全部风控出场臂都严重劣化，F1/F2/F4 成立，F3 判据前提不满足（不成立）**。10bp 全期年化（交易日/252 口径）：臂 0 +3.13% → 臂 1 −15.56% / 臂 2 −23.91% / 臂 3 −24.39%；日历年 7.33 年口径为 +3.01% / −15.03% / −23.14% / −23.60%（两个口径同列于 §4.1）。附加对照臂「只把 MAX_HOLD_DAYS 改 45」也是 −15.03%（日历年 −14.52%）：**该入场上的收益来自少数长持大赢家，任何提前出场都在毁收益**。
6. **臂 0 与派单给的基线不是同一条管道**：生产路径臂 0 = 199 笔 / +24.27%，派单引用的研究侧 `S01_ma_cross_20_60@10` = 252 笔 / −32.09%。差异来自策略定义（研究侧 `basic_filter.enabled=False` + `in_universe` 信号；生产策略文件用引擎 `basic_filter` 股票池），不是引擎或跑法。**需上层裁定四臂比较基准**（我用生产路径臂 0 作对照，已写进预注册）。
7. **第 3 改动集（服务端量级校验）已落地并回归**：`|stop_loss| > 0.5` 与 `max_hold_days < 1` 在 4 处入口报错；`pytest tests/backtest` 可复现基线 **737 passed + 1 条 spawn 用例偶发（该用例单跑 2/2 通过）**，本机另有 3 次整轮 738 passed（条件见 §5.2）；新增校验用例 22 passed；生产装载 7 条策略 0 load_errors、量级全合规。

## 1. 改动集 1：策略文件

**备份**：`custom_mw7fvp17.py.bak_20261108`，3,449 B，sha256 `61c237c6cdb2a439…`，mtime 2026-11-08 14:19:54（改动前原样）。

**改后（最终版）**：5,510 B，sha256 `918254f0e2bec567…`，mtime 2026-11-08 17:18:28，125 行，`META.id` 仍为 `custom_mw7fvp17`。
（版本链：改动集 1 完成 4,472 B / `2cc00778…`；改动集 1+2 4,751 B / `5879a6df…`；加 §1.1 撮合口径默认项 5,392 B / `4118aa61…`（17:06:10）；再加 `META.description` 状态标注 → 最终版 5,510 B / `918254f0…`（17:18:28）。前两版存 `prod_file_snapshots/`，`2cc00778…` 即已移出生产目录的 `.step1`。）

写入的模块级常量（`backend/app/strategy/engine.py:648-652` 只读这五个名字）：

| 常量 | 值 | 说明 |
|---|---|---|
| `STOP_LOSS` | `-0.08` | 小数口径；`-8` 会被 `_valid_price` 过滤而静默永不触发 |
| `TRAILING_TAKE_PROFIT_ACTIVATE` | `0.10` | 激活式移动止盈激活线 |
| `TRAILING_TAKE_PROFIT_DRAWDOWN` | `0.08` | 峰值回撤止盈线 |
| `TRAILING_STOP` | `None` | 明确不启用（与激活式移动止盈同为棘轮，同开会污染 exit_reason 归因），注释已写清 |
| `MAX_HOLD_DAYS` | `45` | 原 60 |

元数据（与 S01 脱钩）：`name` =「双均线 20/60 金叉 · 风控退出（S01b 变体）」；`description` 明写「非 S01 复现体，S01 复现见 research/s01-serial-20261108/」；`tags` = `["趋势","双均线","S01b"]`；`backtest_defaults` = `trailing_peak_price:"close"` + 四项撮合/成本默认（理由与证据见 §1.1）。

**状态标注（17:18 追加，唯一一处文本改动）**：`META.description` 末尾加一句事实陈述——「四臂预注册判据 F1/F4 成立、该变体未达基线，明细见 research/s01b-20261108/REPORT.md。」只加状态陈述，未改任何策略逻辑、参数与因子口径；改后重跑 `prod_file_10bp` 复现同值（§1.1），前端列表重查通过（§1.1）。

出场优先级用引擎既有语义（未改引擎）：`risk_exit > 策略卖点 > max_hold`。

### 1.1 为什么 `META.backtest_defaults` 里还多了四项（超出派单列表的一处主动决定）

四臂的撮合口径是：`entry_price_basis=raw`（不复权原始价）、`block_limit_open=True`（涨停开盘不追）、`finalize_open_at_end=True`（期末按收盘强制平仓计入）、`execution_costs={min_commission:5.0, transfer_fee_pct:0.000002}`（最低佣金 5 元/笔、过户 0.02bp）。这四项之前只写在 `research/s01b-20261108/strategies/custom/s01b_a*.py` 的实验臂模板里，**生产策略文件没写**。后果很具体：从策略下拉里选本策略直接跑，引擎会用 `entry_price_basis=adjusted`、不挡涨停开盘、期末不强制平仓、最低佣金 0 ⇒ 同一份策略会跑出与四臂表不同的数（这才是真正的坑，不是装饰）。

所以把这四项一并写进 `META.backtest_defaults`，让「生产文件本身」就是四臂口径。**没有改口径，只是把已有口径落到落盘文件上**；成本项与派单口径一致（过户 2e-06 = 0.02bp），`min_commission 5 元`是沿用 S01 串行实验夹具的同一项，且 1,000,000 元账户单笔约 12 万名义额 × 3bp ≈ 36 元 > 5 元，最低佣金对本组合实际不生效。

**复现证明（新增）**：直接用 `D:\TSP\data\strategies\custom`（即生产文件，未经任何实验模板包装）跑同口径一次——

```
python research\s01b-20261108\prod_run_s01b.py --strategy-id custom_mw7fvp17 \
    --strategies-dir "D:\TSP\data\strategies\custom" --tag prod_file_10bp
```

退出码 0、`error=None`，产物 `results/prod_file_10bp/`：**1,135 笔 / 总收益 −86.11% / 年化 −24.39% / MDD −91.00% / Sharpe −1.01 / 平均暴露 51.73% / 最大暴露 68.42%**，与臂 3（`a3_10bp`）逐字段相同，且 `trades.parquet` 与 `a3_10bp` 的 **1,135×22 表 `DataFrame.equals() = True`（含全部列名与单元格）**；`META` 加状态标注后（17:2x）用同一命令重跑，七项数字一字不变，且 `trades.parquet` / `equity.parquet` 与 `a3_10bp` **字节相同**（trades sha256 前 16 位 `3c0f27e9…`）⇒ 标注只动描述文本 ⇒ 生产文件 = 臂 3，不是"另一条跑法"。

**前端可直接选到（实测，只读、不重启）**：`verify_list.py` exit 0，用与 `backend/app/main.py:481-486` 相同的 4 个策略目录 + `list_strategies(include_research=False)`（前端策略下拉的数据源），结果落 `verify_list_result.json`：

```
"n_strategies_in_list": 5
"ids": ["custom_factor_first_board_chain_strict_rebreak","custom_khunter_limit_up_pullback",
        "custom_mvoa5yy6","custom_mw7fvp17","first_limit_pullback_3f_runner_t74"]
"target": [{"id":"custom_mw7fvp17","name":"双均线 20/60 金叉 · 风控退出（S01b 变体）",
            "tags":["趋势","双均线","S01b"],
            "backtest_defaults":{"trailing_peak_price":"close","entry_price_basis":"raw",
                                 "block_limit_open":true,"finalize_open_at_end":true,
                                 "execution_costs":{"min_commission":5.0,"transfer_fee_pct":2e-06}},…}]
```

**台账登记（研究侧文件我没动，请转因子研究员登记）**——登记名 `S01b_ma_cross_20_60_risk_exit`，试验计数 +3（= 臂 1 / 臂 2 / 臂 3 三次参数试验），建议条目原文（键名沿用 `registry.runs` 的 `策略@情景` 约定）：

```
"S01b_ma_cross_20_60_risk_exit/stop_loss-8@10"            {variant:"arm1", stop_loss:-0.08, max_hold_days:60, trailing:null, slippage_bps:10}
"S01b_ma_cross_20_60_risk_exit/stop_loss-8@30"            {同上, slippage_bps:30}
"S01b_ma_cross_20_60_risk_exit/stop_loss-8@gross"         {同上, slippage_bps:0, commission/stamp/transfer/slippage=0}
"S01b_ma_cross_20_60_risk_exit/stop_loss-8+ttp_10_8@10"   {variant:"arm2", stop_loss:-0.08, trailing_take_profit:{activate:0.10, drawdown:0.08}, peak:"close", max_hold_days:60, slippage_bps:10}
"S01b_ma_cross_20_60_risk_exit/stop_loss-8+ttp_10_8@30"   {同上, slippage_bps:30}
"S01b_ma_cross_20_60_risk_exit/stop_loss-8+ttp_10_8@gross"{同上, gross}
"S01b_ma_cross_20_60_risk_exit/stop_loss-8+ttp_10_8+hold45@10"    {variant:"arm3", …, max_hold_days:45, slippage_bps:10}
"S01b_ma_cross_20_60_risk_exit/stop_loss-8+ttp_10_8+hold45@30"    {同上, slippage_bps:30}
"S01b_ma_cross_20_60_risk_exit/stop_loss-8+ttp_10_8+hold45@gross" {同上, gross}
meta.n_trials: 原值 + 3
```

口径提醒（登记必须带上，否则后续会被误当可比值）：**以上都是生产路径（matrix_native + 引擎 basic_filter 股票池）数字，与研究侧 `S01_ma_cross_20_60@*` 不是同一入场管道**；研究侧若要按 registry 口径复核，需在研究侧管道重跑。

## 2. 改动集 2：`cross_down` 语义修正

策略文件里 `cross_down` 由水平式 `fast < slow` 改为事件式 `(fast < slow) & (prev_fast >= prev_slow)`（文件内注释已说明）。

核对：`compare_trades.py`（exit 0），产物 `results/compare_cross_down.json`：

| 配置 | 水平式笔数 | 事件式笔数 | 逐笔全等 | 差异列 |
|---|---|---|---|---|
| 臂 0（无风控出场，MAX_HOLD 60） | 199 | 199 | **true** | 无（`{}`） |
| 臂 3（止损+移动止盈+45 天） | 1135 | 1135 | **true** | 无（`{}`） |

「全等」= 两张 trades 表按 `(symbol, entry_date, exit_date, exit_reason, pnl_pct, exit_price, duration)` 逐行比对，行数相同且无任何列差异（脚本输出 `same_row_count: true, exact_equal: true, diff_columns: {}`）。⇒ 金叉入场路径下事件式等价，无需停下。

第三重证据（最直接）：生产策略文件本身就是事件式，`prod_file_10bp`（§1.1）与臂 3 的**水平式** `a3_10bp` 的 trades 表 `DataFrame.equals() = True`（1,135×22 全列全单元格）⇒ 事件式与水平式在同一入场路径上确实完全一致。

**关于派单里「应 252 笔全同」**：252 笔是**研究侧管道**（`signal_s01_ma_golden_20_60` / `signal_s01_ma20_below_ma60` 两个物化信号列 + `basic_filter.enabled=False`）的笔数；生产路径同一入场是 199 笔（§6 第 1 条）。研究侧那条出场是**已物化的信号列**（水平式写在列里），要做事件式的 252 笔 A/B 得**新增一条自定义信号列**——那属于改信号链，派单 §7 明令不许。所以等价值是在可控的两个生产配置上证的（无风控 199 笔 + 全风控 1135 笔，两端都全等），没有硬改研究侧信号。

## 3. 前置检查（首次启用前置）

### 3.1 移动止盈最小用例（已知答案）

`mini_trailing_tp.py`（exit 0）→ `mini_trailing_tp_result.json`。合成序列：d0 close 10.00 建仓；d1 close 11.20（+12%，high 11.60）；d2 最低价按用例填 10.20 或 10.35。直接调 `BacktestEngine.simulate_market_matrix` + `MatcherConfig`（不读 parquet，可复算）。

| 用例 | 峰值口径 | 峰值 | 8% 止盈线 | d2 最低价 | 触发 | 成交日 | 成交价 | pnl | exit_reason 原值 |
|---|---|---|---|---|---|---|---|---|---|
| A（low 10.20） | close | 11.20 | 10.304 | 10.20 | 是 | 2024-01-04 | **10.304** | +3.04% | `trailing_take_profit` |
| A（low 10.20） | high | 11.60 | 10.672 | 10.20 | 是 | 2024-01-04 | 10.672 | +6.72% | `trailing_take_profit` |
| B（low 10.35） | close | 11.20 | 10.304 | 10.35 | **否** | 2024-01-08 | 10.50 | +5.00% | `end` |
| B（low 10.35） | high | 11.60 | 10.672 | 10.35 | 是 | 2024-01-04 | 10.672 | +6.72% | `trailing_take_profit` |

⇒ 触发日 = 最低价跌破线当日，成交价 = 线价（`峰值 × (1 − 0.08)`，跳空穿越时按开盘价），`exit_reason` 原值确为 `trailing_take_profit`。用例 B 同时证明 **close / high 口径会改变出场**，不能混用。

### 3.2 `trailing_peak_price` 能不能在策略模块固定？

**不能。** 证据链：

- `backend/app/strategy/engine.py:648-652`（装载层读模块常量）只 `getattr` 五个名字：`STOP_LOSS / TRAILING_STOP / TRAILING_TAKE_PROFIT_ACTIVATE / TRAILING_TAKE_PROFIT_DRAWDOWN / MAX_HOLD_DAYS`；`grep -n "PEAK_PRICE\|trailing_peak_price" backend/app/strategy/engine.py` 无命中 ⇒ 模块常量入口不存在这一项。
- 能设的位置只有策略 `META["backtest_defaults"]`：`backend/app/backtest/strategy.py:3585-3587` `_strategy_execution_policy()` = `parse_backtest_defaults(s.meta.get("backtest_defaults"), …)` → `backend/app/backtest/execution_policy.py:42`（`"trailing_peak_price"` 在允许键里）、`:72`（默认 `"high"`）、`:136-138`（解析）、`:190`（进 policy）→ `backtest/strategy.py:1566` 取 policy、`:1587 / :1865 / :2638` 写入 `MatcherConfig(trailing_peak_price=…)` → `backend/app/backtest/engine.py:253`（字段）+ `:3026 / :3031 / :3069 / :4023`（消费）。
- 请求体没有该字段：`backend/app/api/backtest.py:350-392` 的 `StrategyBacktestRequest` 无 `trailing_peak_price`，`grep -r trailing_peak_price backend/app/api` 无命中 ⇒ **正常一次回测请求无法直接传 close**，只能靠策略 META 声明。

⇒ 已把 `"trailing_peak_price": "close"` 写进策略 `META.backtest_defaults`（生效实测见 3.3）。

### 3.3 close / high 单列对照（绝不悄悄用 high 当 close）

同配置只换峰值口径（10bp，其余完全一致）：

| 臂 | 峰值口径 | 全期年化 | 总收益 | MDD | 笔数 | 移动止盈出场 | 止损出场 | 年换手 |
|---|---|---|---|---|---|---|---|---|
| 臂 2 | **close**（规格） | −23.91% | −85.48% | −90.58% | 1126 | 393 | 718 | 6.42x |
| 对照 a2h | high（引擎默认） | −23.72% | −85.22% | −90.64% | 1487 | 691 | 776 | 10.91x |

⇒ 两臂数字确实不同（口径真的生效，不是空设）；high 口径换手高 70%、移动止盈出场多 76%。**四臂全部用 close。**

## 4. 四臂验证

口径：1,000,000 元 / 最多 5 仓 / 60% 敞口 / 次日开盘撮合 / 等权 / `entry_price_basis=raw` / `block_limit_open` / 佣金 3bp×2 + 印花 10bp + 过户 0.02bp + 滑点 10bp×2（`--slippage-bps 30` 换 30bp，`--gross` 四项成本全零）。区间 2019-07-01…2026-10-30（1,779 交易日）。

跑法：`backend\.venv\Scripts\python.exe research\s01b-20261108\prod_run_s01b.py --strategy-id <sid> --tag <tag> [--slippage-bps 30 | --gross] [--strategies-dir …]`，每臂退出码 0、`error=None`。

### 4.1 主表（10bp / 30bp / gross）

| 臂 | 情景 | 全期年化(交易日/252) | 全期年化(日历年7.33年) | OOS 年化(日历年) | MDD | OOS MDD | Sharpe | OOS Sharpe* | 持仓 p50/p90 | 年换手 | 均/最大暴露 | 笔数 | 胜率 | avg/median pnl |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 臂 0 基线（无风控出场，MH 60） | 10bp | +3.13% | +3.01% | +4.73% | −39.27% | −29.54% | +0.25 | +0.30 | 48/60 | 3.48x | 57.15%/73.13% | 199 | 33.5% | +1.31%/−9.64% |
| 臂 0 | 30bp | +1.80% | +1.73% | +3.32% | −40.89% | −30.33% | +0.20 | +0.24 | 48/60 | 3.33x | 57.18%/73.21% | 199 | 33.0% | +0.90%/−10.00% |
| 臂 0 | gross | +4.21% | +4.05% | +5.90% | −38.02% | −28.98% | +0.29 | +0.34 | 48/60 | 3.61x | 57.11%/73.22% | 199 | 33.5% | +1.67%/−9.32% |
| 臂 1 + 止损 −8% | 10bp | −15.56% | −15.03% | −22.97% | −83.86% | −75.02% | −0.51 | −0.87 | 5/59 | 5.39x | 56.54%/68.58% | 519 | 15.1% | −1.45%/−8.24% |
| 臂 1 | 30bp | −16.84% | −16.27% | −18.54% | −82.71% | −70.71% | −0.55 | −0.62 | 5/60 | 4.57x | 56.51%/70.69% | 521 | 14.5% | −1.89%/−8.42% |
| 臂 1 | gross | −9.18% | −8.86% | −16.94% | −76.37% | −67.72% | −0.22 | −0.56 | 5/60 | 6.63x | 56.73%/69.78% | 525 | 15.5% | −0.42%/−8.00% |
| 臂 2 + 止损 + 移动止盈 10/8 | 10bp | −23.91% | −23.14% | −13.83% | −90.58% | −65.04% | −0.99 | −0.46 | 4/18 | 6.42x | 51.94%/67.36% | 1126 | 35.3% | −1.39%/−8.24% |
| 臂 2 | 30bp | −24.61% | −23.82% | −11.01% | −91.02% | −60.56% | −1.00 | −0.30 | 3/18 | 5.88x | 51.58%/67.45% | 1142 | 35.2% | −1.42%/−8.42% |
| 臂 2 | gross | −19.07% | −18.43% | −6.83% | −86.97% | −58.08% | −0.73 | −0.14 | 3/18 | 7.35x | 52.27%/68.78% | 1134 | 35.8% | −1.03%/−8.00% |
| 臂 3 + 上路 + MH 45 | 10bp | −24.39% | −23.60% | −14.57% | −91.00% | −66.22% | −1.01 | −0.48 | 3/18 | 6.32x | 51.73%/68.42% | 1135 | 34.8% | −1.46%/−8.24% |
| 臂 3 | 30bp | −25.38% | −24.56% | −14.56% | −91.42% | −65.23% | −1.03 | −0.46 | 3/18 | 6.19x | 51.51%/67.62% | 1158 | 34.7% | −1.43%/−8.42% |
| 臂 3 | gross | −20.55% | −19.87% | −9.17% | −87.36% | −58.02% | −0.81 | −0.24 | 3/18 | 7.18x | 52.22%/67.72% | 1148 | 35.4% | −1.11%/−8.00% |

**年化口径（写死；复算式见 §4.5）**：`全期年化(交易日/252)` = `(末值/初值)^(252/交易日数) − 1`（1,779 交易日 → 7.0595 年）；`全期年化(日历年7.33年)` = `(末值/初值)^(365.25/日历天数) − 1`（2019-07-01…2026-10-30 共 2,678 天 → 7.3320 年）；`OOS 年化(日历年)` = `(段末权益/2022-12-30 权益)^(365.25/OOS 天数) − 1`（1,400 天 → 3.8330 年）。**同一张表两种年长并用，读数时看列名**；判据方向（F1/F2/F4 成立、F3 不成立）在两种口径下结论相同。「全期年化(交易日/252)」列取自各臂 `result.json` 的 `stats.annual_return`，与上式在 0.01pp 内一致（个别行第 4 位小数有引擎内部取整差，如 a3_gross 引擎 −20.55% vs 本式 −20.5550%）。

\* `OOS 年化 / OOS MDD / OOS Sharpe` 由**连续账户** equity 曲线切片自算：OOS = 2023-01-03…2026-10-30（3.833 年），段首权益 = 2022-12-30 权益（沿用 `research/strategy-search-20261107` 的 `IS_END=2022-12-30` 切分）；OOS Sharpe = 日收益均值/标准差 × √252（自算口径，非引擎 `stats.sharpe`，两者不可混比）。引擎 `stats.sharpe` 只作全期列。`OOS 年化 / OOS MDD / OOS Sharpe` 三列**按该行成本档自己的 equity 曲线**自算（30bp、gross 行不与 10bp 行共用读数；17:0x 版曾复用 10bp 值，2026-11-08 复核后改为逐档自算，见 §8 第 5 条）。

对照与附加（同口径 10bp）：

| 配置 | 全期年化(交易日/252) | 全期年化(日历年7.33年) | OOS 年化(日历年) | MDD | 笔数 | 年换手 | 说明 |
|---|---|---|---|---|---|---|---|
| 对照 a2h：臂 2 但 peak=high | −23.72% | −22.95% | −20.23% | −90.64% | 1487 | 10.91x | 峰值口径专属对照（3.3） |
| 附加 a4：**只**把 MAX_HOLD_DAYS 60→45（无止损/无止盈） | −15.03% | −14.52% | −14.65% | −71.30% | 238 | 2.41x | 检验 F4 的「退回只做 45 天上限」 |

### 4.2 exit_reason 分布（10bp）与风控线击穿时刻

| 臂 | signal | max_hold | stop_loss | trailing_take_profit | end |
|---|---|---|---|---|---|
| 臂 0 | 136 | 58 | 0 | 0 | 5 |
| 臂 1 | 42 | 50 | **425** | 0 | 2 |
| 臂 2 | 9 | 5 | 718 | 393 | 1 |
| 臂 3 | 9 | 12 | 725 | 388 | 1 |
| 对照 a2h | 16 | 3 | 776 | 691 | 1 |
| 附加 a4 | 125 | 108 | 0 | 0 | 5 |

**击穿时刻口径**：`stop_loss` / `trailing_take_profit` 的击穿日 = `trades.parquet` 的 `exit_date`（引擎当日撮合：最低价触线按线价成交，跳空穿越按当日开盘价）。臂 1 的 425 笔止损，按 `exit_price / entry_price − 1` 分档：

| 区间（`exit_price/entry_price − 1`） | 笔数 |
|---|---|
| `[−8.10%, −8.00%]` | **315** |
| `[−8.085%, −8.00%]` | 0 |
| `< −15%` | 22 |
| `> 0` | 1 |

众数为 −8.0919%（88 笔）/ −8.0920%（85 笔）；落在 −8.092% ± 0.05pp 内（比率 ±0.0005）合计 **315 笔**。理论值 = `0.92 × 0.999 − 1 = −8.0920%`（止损线 = 建仓价 × (1 − 0.08)，卖出滑点 10bp 作用在**线价**上）；实测极值 −8.0916% / −8.0923%，残差在 ±0.0005pp 以内，来自 0.01 元最小价位取整。唯一为正的一笔：`002900.SZ`，2021-03-24 入 / 2021-03-31 出，`exit_price/entry_price − 1 = +13.20%`（毛价）/ `pnl_pct = +13.02%`（含成本），`blocked_exit_days = 1`（触发后被停牌挡下、复牌按更高开盘价成交）。所有 `exit_date` / `exit_reason` 原值都在各臂 `trades.parquet`，可逐笔核对。

> 更正：17:1x 版本此处原写「一批止损落在 [−8.085%, −8.0]」，该区间与计数**均不可复现**（按 [−8.085%, −8.00%] 实测 0 笔，按 [−8.10%, −8.00%] 实测 315 笔）。原句作废，旧数字只留在 `REPORT_pre_rework_1720.md.bak` 存档里（本报告不再出现），本节表格为唯一口径。

### 4.3 延后退出笔数（口径写死）

口径：被测臂每笔交易与臂 0 按 `(symbol, entry_date)` 配对（同标的同日入场视为同一次入场），配对成功且 `exit_date` 更晚记 1 笔延后。

| 臂 | 总笔数 | 配对成功 | 配不上 | 延后 | 提前 | 同日 |
|---|---|---|---|---|---|---|
| 臂 1 | 519 | 63 | 456 | **0** | 48 | 15 |
| 臂 2 | 1126 | 101 | 1025 | **0** | 99 | 2 |
| 臂 3 | 1135 | 103 | 1032 | **0** | 102 | 1 |
| 附加 a4 | 238 | 46 | 192 | **0** | 26 | 20 |

**逐笔配对不可行**（配对率仅 12%–20%：风控出场改变仓位占用与再入场时点，同标的同日入场的笔本来就少）。按派单允许的替代口径改用「中位持仓位移 + exit_reason 结构变化」：

- 中位持仓：臂 0 **48 天** → 臂 1 **5 天** / 臂 2 **4 天** / 臂 3 **3 天**（平均 45.3 → 16.4 / 7.1 / 7.1 天）。
- exit_reason 结构：臂 0 以 `signal`(136)+`max_hold`(58) 为主 → 臂 1/2/3 变成 `stop_loss` 主导（425/718/725）。
- 在能配对的子集里延后 **0 笔**、提前 48/99/102 笔 ⇒ 风控出场只让退出提前，没有一笔推后。

### 4.4 预注册判死条件判定（判据未改）

预注册 `PREREG_S01B_20261108.md`，2,871 B，sha256 `cf95a0b7ae2298b4…`，落盘 2026-11-08 16:23:36。
**披露**：臂 0（基线，无风控出场，16:21:47）在预注册落盘前已跑完；被测的臂 1/2/3（16:24:00 / 16:24:16 / 16:24:33）与 30bp、gross 全部在预注册之后。判据开跑前写死、跑完未改。

| 判据 | 原文要点 | 判定 | 证据 |
|---|---|---|---|
| **F1** 成本敏感性 | 10bp 全期年化为负且 30bp 更负 → 无效，不得再调出场参数 | **成立** | 臂 1 −15.56%→−16.84%；臂 2 −23.91%→−24.61%；臂 3 −24.39%→−25.38%（三臂全为负且 30bp 更负） |
| **F2** 入场 alpha | gross 全期年化仍为负 → 入场无 alpha，停止在该入场上调出场 | **按被测臂成立；机制不同** | 臂 1 −9.18%、臂 2 −19.07%、臂 3 −20.55% 全负；**但臂 0 gross = +4.21% 为正** ⇒ 入场本身有弱正 gross alpha，负值是风控出场叠加造成。判据按字面成立、结论方向一致（停止在该入场上调出场参数），机制描述以本行为准 |
| **F3** 改进来源 | 亏损减少全来自换手/暴露下降而非单笔改善 → 不算改进 | **不成立（前提不满足）** | 判据要求「avg_pnl 与 median_pnl 均未上升」且「年换手或 avg_exposure 下降」。臂 1：avg_pnl +1.31%→**−1.45%**（降）、median −9.64%→**−8.24%**（升）、年换手 3.48x→**5.39x**（升）、avg_exposure 57.15%→56.54%（微降）⇒ 前提不成立。且亏损并未减少（总收益 +24.27%→−69.69%），本条在那个方向无意义 |
| **F4** 止损是否噪声收割 | 臂 1 的 OOS 比基线更差且换手 > 1.5× → 止损是噪声收割机，退回只做 45 天上限 | **成立** | OOS 年化 −22.97% vs 基线 +4.73%（更差）；换手比 5.39/3.48 = **1.55× > 1.5×**。**附加证据**：F4 建议的「退回只做 45 天上限」已按同口径加跑 a4（只把 MH 60→45，无任何止损/止盈）= 全期 −15.03%、OOS −14.65%、MDD −71.30% ⇒ **该退路同样致命**；真正读数是「这个入场只靠长持右尾盈利，任何提前出场都不成立」 |
### 4.5 复算式（可直接跑，2026-11-08 17:3x 实测输出）

```python
import pandas as pd
B = "research/s01b-20261108/results/"

# ① 臂 1 止损击穿分布（§4.2）
t = pd.read_parquet(B + "a1_10bp/trades.parquet")
r = (t.exit_price / t.entry_price - 1)[t.exit_reason == "stop_loss"]      # 425 笔
print(len(r), ((r >= -0.0810) & (r <= -0.0800)).sum(), (r < -0.15).sum(), (r > 0).sum())
# -> 425 315 22 1

# ② 全期年化：交易日/252 与 日历年 两种年长（§4.1 两个全期列）
for tag in ["a0_10bp", "a1_30bp", "a2_gross", "a3_10bp"]:
    e = pd.read_parquet(B + tag + "/equity.parquet")
    v0, v1 = e.value.iloc[0], e.value.iloc[-1]
    y_td  = len(e) / 252                                                        # 7.0595 年
    y_cal = (pd.Timestamp(e.date.iloc[-1]) - pd.Timestamp(e.date.iloc[0])).days / 365.25   # 7.3320 年
    print(tag, f"{(v1/v0)**(1/y_td)-1:+.4%}", f"{(v1/v0)**(1/y_cal)-1:+.4%}")

# ③ OOS 年化（§4.1 OOS 列，日历年口径）：逐成本档自算，三档不共用同一读数
for tag in ["a0_10bp", "a0_30bp", "a0_gross"]:
    e = pd.read_parquet(B + tag + "/equity.parquet"); e["date"] = pd.to_datetime(e.date)
    v0 = float(e.loc[e.date <= "2022-12-30", "value"].iloc[-1]); seg = e[e.date > "2022-12-30"]
    y = (seg.date.iloc[-1] - pd.Timestamp("2022-12-30")).days / 365.25      # 3.8330 年
    print(tag, f"{(seg.value.iloc[-1]/v0)**(1/y)-1:+.4%}", f"{(seg.value/seg.value.cummax()-1).min():+.4%}")
# -> a0_10bp +4.7298% -29.5429% / a0_30bp +3.3241% -30.3341% / a0_gross +5.9027% -28.9817%
```


## 5. 改动集 3：服务端量级校验

### 5.1 受影响文件（本改动集只有这 6 个）

| 文件 | 变化 | 作用 |
|---|---|---|
| `backend/app/strategy/risk_limits.py` | **新增** 2,953 B | 纯函数校验：`STOP_LOSS_MAX_ABS = 0.5`、`MAX_HOLD_DAYS_MIN = 1`；`validate_stop_loss / validate_max_hold_days / validate_risk_scale` |
| `backend/app/strategy/engine.py` | +13 / −2 | **装载层**：`StrategyDef` 构造前校验模块常量；不合规策略进 `_load_errors`，不静默注册 |
| `backend/app/api/backtest.py` | +33 / −2 | **请求层**：`BacktestRequest.stop_loss_pct / max_hold_days` 字段校验（422）；`StrategyBacktestRequest.overrides` 用 `model_validator(after)` 校验（422） |
| `backend/app/api/strategy.py` | +15 / −1 | **overrides 写盘层**：`SaveConfigRequest.overrides` 校验（422），避免把 `-8` 存下来等回测时静默失效 |
| `backend/app/services/backtest.py` | +9 | **请求→配置层**：`BacktestConfig.__post_init__` 校验（非 API 入口也拦） |
| `backend/tests/test_risk_limits_scale.py` | **新增** | 22 条回归用例（纯函数边界 / 装载层 / 三种请求模型 / `BacktestConfig` / 25 个种子文件量级） |

未动：`backtest/engine.py`（回测引擎核心）、`backtest/strategy.py`（信号链/撮合编排）、`dsl.py` 算子表、`store.py`。

### 5.2 回归证明

`verify_risk_limits.py`：**45 项断言全 PASS，`failures = 0`，exit 0**。

- A 纯函数：接受 `-0.08 / -0.5 / 0.5 / 0.0 / None`，拒绝 `-8 / 8 / -0.5001 / 1.0`；`max_hold_days` 接受 `1/45/60/None`，拒绝 `0 / -1 / -45`。
- B 装载层：临时目录三条策略（合规 / `STOP_LOSS=-8` / `MAX_HOLD_DAYS=0`）→ 合规策略注册成功，两条坏策略**未注册**且落 `_load_errors`，报错原文：
  `strategy rl_bad_stop.stop_loss=-8 超出量级上限 |strategy rl_bad_stop.stop_loss| <= 0.5：… 会被价格有效性过滤而静默永不触发`
  `strategy rl_bad_hold.max_hold_days=0 无效：必须 >= 1 个交易日`
- C 生产装载：4 个生产策略目录共装载 **10 条策略，`load_errors = 0`**；其中 **7 条**写了 `STOP_LOSS`/`MAX_HOLD_DAYS` 常量（另 3 条 `ai_*` 两者皆 `None` = 不在本校验射程内），量级全合规（见 5.3）。
- D 请求层：`BacktestRequest / StrategyBacktestRequest / SaveConfigRequest / BacktestConfig` 正例通过，`stop_loss=-8` 与 `max_hold_days=0` 全部被拒。

`pytest tests/test_risk_limits_scale.py -q` → **22 passed, exit 0**；`pytest tests/backtest -q` → **可复现基线 = 737 passed + 1 条 spawn 用例偶发**（`tests/backtest/test_worker_process.py::test_spawn_robust_optimize_runs_k_segments_in_worker`，单跑 **2/2 通过**；本机单跑 1/1 通过 `1 passed in 7.88s`）；本机另有 3 次整轮 **738 passed, exit 0**（250.95s / 180.10s / 200.79s，见下表）⇒ **738 只作本机观察记录、不作硬断言**（下一轮挂在这条上不算回归），判定为 `multiprocessing` spawn 抖动、非本改动集引入：该用例只涉及 `app.backtest.worker` / `app.backtest.strategy` 起停子进程，对新增的 `app/strategy/risk_limits.py` **零引用**（`grep -c risk_limits tests/backtest/test_worker_process.py` = 0）；同一用例单跑累计 3/3 通过（本机 1/1 + 开发经理 2/2），失败不可复现，且失败那一次其余 737 条全绿。

**三次 738 passed 的运行条件**（同一台机、同一条命令 `backend\.venv\Scripts\python.exe -m pytest tests/backtest -q`，工作目录 `backend`）：

| 次序 | 时段 | 用时 | 结果 | 机器状态 |
|---|---|---|---|---|
| ① | 16:5x（本报告初版） | 250.95s | 738 passed | 无并行 pytest |
| ② | 17:01:34→17:04:34（`logs/pytest_backtest.log`） | 180.10s | 738 passed, 14 warnings | 同时段只有轻量 verify 脚本，无并行 pytest |
| ③ | 17:2x（`logs/pytest_backtest_1720.log`） | 200.79s | 738 passed, 14 warnings | 无并行任务，`peak_rss` 约 1.5–1.7GB |

### 5.3 种子策略值实测表（不受影响）

内置种子 25 个文件（`backend/app/strategy/seeds/*.py`）：`STOP_LOSS ∈ {-0.05,-0.06,-0.07,-0.08}`、`MAX_HOLD_DAYS ∈ {5,10,15,20,25,30}`，越界 0 个（`seed_risk_values.json`）。生产装载共 10 条，其中带风控常量的 7 条（3 条 `ai_*` 为 `None`，不参与量级判定）：

| 策略 | STOP_LOSS | MAX_HOLD_DAYS | 合规 |
|---|---|---|---|
| custom_factor_first_board_chain_strict_rebreak | −0.08 | 30 | ✓ |
| custom_khunter_limit_up_pullback | −0.05 | 10 | ✓ |
| custom_mvoa5yy6 | −0.05 | 20 | ✓ |
| **custom_mw7fvp17（S01b 变体）** | **−0.08** | **45** | ✓ |
| factor_rank_research | −0.08 | 30 | ✓ |
| first_board_chain_rebreak | −0.08 | 10 | ✓ |
| first_limit_pullback_3f_runner_t74 | −0.06 | 74 | ✓ |

### 5.4 需要上报的既有红（不是本次改动引入）

跑「引用了本次改动模块」的 49 个测试文件：**33 failed / 652 passed / 6 skipped**。基线对照做法：`git stash` 只 stash 本次 4 个后端文件 → 同样 **33 failed**（其余 43 个文件未跑，故 passed 少），失败集合一致 → 全部是既有问题；stash 已 `pop` 还原，`git diff --stat` 与之前一致。分布：

- `tests/test_paper_execution_extension.py` 26 条：测试用 `write_text(...)` 无编码写含中文的临时策略 → 本机 locale 是 GBK，引擎按 UTF-8 读时报 `'utf-8' codec can't decode byte 0xc0/0xbe` → `unknown strategy: demo`；另 1 条 `KeyError: 'revision'`。
- `tests/test_strategy_seeds.py` 1 条：种子数 **26 ≠ 预期 25**。
- `tests/test_screener_etf.py` 1 条：同样 26 ≠ 25。
- `tests/test_strategy_registry.py` 1 条：来源映射 `{custom_…t74: custom} != {…: composite}`。
- `tests/test_api_strategy_bundle.py` 2 条：bundle 内容 dict 不等。

建议：编码类在测试里显式 `encoding="utf-8"`；种子数类核对 seeds 目录是否多了一条。

## 6. 需要上层裁定 / 后续

1. **四臂比较基准（需裁定）**：派单写的臂 0 = 研究侧 `S01_ma_cross_20_60@10`（252 笔 / −32.09%）；生产路径同一入场（本报告臂 0）= 199 笔 / **+24.27%**。原因已定位为策略定义不同（研究侧 `research/s01-serial-20261108/strategies/custom/s01_ma_cross_20_60.py` 用 `basic_filter.enabled=False` + `in_universe` 信号列；生产策略用引擎 `basic_filter` 股票池 price_min 2.0 / exclude_st / exclude_new_days 30 / 全板块），**不是引擎差异**。预注册里已预先声明并改用生产路径臂 0 作对照；若研究侧要求以研究侧管道为基准，需重跑一套（可以做，但要另立口径）。
2. **F4 的退路不成立**：附加臂 a4（只 45 天上限）全期 −15.03%。建议策略侧据此判断该入场是否还值得保留。
3. **台账 3 条新试验**待因子研究员登记（条目原文见 §1），研究侧 `registry.json` / `GLOBAL_LEDGER_v3.json` / `FREEZE.json` 一律未动。
4. **持久化**：策略文件已落盘 `D:\TSP\data\strategies\custom\`（前端可见），但**未写生产库 strategy row**；要进生产库我出方案再动。
5. **生产目录已清干净（17:2x）**：中途快照 `custom_mw7fvp17.py.step1`（4,472 B，`2cc00778…`）已从 `D:\TSP\data\strategies\custom` **移出**到 `research\s01b-20261108\prod_file_snapshots\custom_mw7fvp17.py.step1_4472B_2cc00778`（内容未改，sha256 前 16 位仍为 `2cc00778`）。生产目录现在只有 `custom_mw7fvp17.py`（5,510 B / `918254f0…`）与回滚点 `.bak_20261108`（3,449 B / `61c237c6…`，与既有 `custom_mvoa5yy6.py.bak-20261026-gap-filter` 同类）；loader 只 glob `*.py`，两者都不参与加载。最终文件以 `918254f0…` 为准（`5879a6df…`/`4118aa61…` 为上一轮读数）。

## 7. 复跑命令与退出码

| 步骤 | 命令 | 退出码 |
|---|---|---|
| 四臂 10bp | `… prod_run_s01b.py --strategy-id s01b_aN --tag aN_10bp` | 0 / 0 / 0 / 0 |
| 四臂 30bp | 同上 `--slippage-bps 30 --tag aN_30bp` | 0 / 0 / 0 / 0 |
| 四臂 gross | 同上 `--gross --strategies-dir research/s01b-20261108/strategies_gross/custom --tag aN_gross` | 0 / 0 / 0 / 0 |
| 峰值口径对照 | `… --strategy-id s01b_a2h --tag a2h_10bp` | 0 |
| 附加臂（只 45 天） | `… --strategy-id s01b_a4 --tag a4_10bp` | 0 |
| 指标汇总 | `… report_metrics.py` | 0 |
| 报告表逐格对账 | `… _audit_report_table.py`（§4.1 主表 12 行 × 13 列对回 metrics.json + 独立复算日历年年化） | 0（0 mismatch） |
| cross_down 等价 | `… compare_trades.py` | 0 |
| 移动止盈最小用例 | `… mini_trailing_tp.py` | 0 |
| 前端列表可选中 | `… verify_list.py` | 0 |
| 校验 4 层验证 | `… verify_risk_limits.py` | 0（failures = 0） |
| 新增回归用例 | `pytest tests/test_risk_limits_scale.py -q` | 0（22 passed） |
| 回测套件 | `pytest tests/backtest -q` | 0（可复现基线 737 passed + 1 条 spawn 偶发，单跑 2/2 通过；本机另 3 次整轮 738 passed，见 §5.2） |

### 7.1 收尾重跑（2026-11-08 17:0x–17:5x，逐项实测，非引用旧读数）

本轮结束前把全部脚本与两个 pytest 套件重跑了一遍，确认退出码与产物哈希可复现（日志落 `research/s01b-20261108/logs/`）：

| 项目 | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 校验四层 | `verify_risk_limits.py` | 0 | `failures = 0`；`risk_limits_production_table.json` 哈希不变 `b467f56036d4e257` |
| 校验回归用例 | `pytest tests/test_risk_limits_scale.py -q` | 0 | `22 passed, 1 warning in 14.00s` |
| 回测套件 | `pytest tests/backtest -q` | 0 | `738 passed, 14 warnings in 180.10s` |
| 回测套件（复核轮） | `pytest tests/backtest -q` | 0 | `738 passed, 14 warnings in 200.79s`（17:2x）；同轮单跑 spawn 用例 `1 passed in 7.88s` |
| 生产文件重跑（加标注后） | `prod_run_s01b.py --strategy-id custom_mw7fvp17 --strategies-dir D:\TSP\data\strategies\custom --tag prod_file_10bp` | 0 | 1,135 笔 / −86.11% / 年化 −24.39%，与 17:0x 一致；`trades.parquet` 与 `a3_10bp` 字节相同 `3c0f27e9` |
| 前端列表复查 | `verify_list.py` | 0 | `verify_list_result.json` → `57412ac7`（description 加了状态标注） |
| 移动止盈最小用例 | `mini_trailing_tp.py` | 0 | `mini_trailing_tp_result.json` 哈希不变 `67c2c02735bffa5a` |
| cross_down 等价 | `compare_trades.py` | 0 | 输出 `VERDICT: IDENTICAL`；`compare_cross_down.json` 哈希不变 `16e7d1c58843a76d` |
| 指标汇总 | `report_metrics.py` | 0 | 修 OOS 逐档自算后重出：`metrics.json` `6174f4da…`、`metrics_table.md` `d025d8ce…`，连跑 2 次同一哈希（对该批 result.json 确定性可复算）；旧值 `7fbfea0a` / `2bb3d55b` 是复用 10bp OOS 的旧版，作废 |
| 报告表对账 | `_audit_report_table.py` | 0 | `rows checked = 12, cells mismatched = 0`（§4.1 主表逐格对比 metrics.json 与独立复算的日历年年化） |
| 四处必改复算 | `_recheck_mgr4.py` | 0 | 止损分档 425/315/0/22/1、众数 −8.0919%(88)、双口径年化与 OOS 逐档值、`.step1` 已不在生产目录、生产文件 5,510 B / `918254f0…`，均与报告一致 |

⇒ 除 `verify_list_result.json`（因 META 内容确实变了，17:2x 重落盘为 `57412ac7`）之外，所有确定性产物（无时间戳的 JSON/MD）在重跑后 sha256 前 16 位完全一致。

**注意（口径）**：`results/<tag>/result.json` 内含 `run_id` / `elapsed_s` / `stats.timing_ms` / `peak_rss_gb`，逐次必然不同，**不能当确定性锚点**；可复现性以 `trades.parquet` / `equity.parquet` 的 sha256 为准（例：`prod_file_10bp` 与 `a3_10bp` 的 trades 同为 `3c0f27e9…` 且字节相同）。

产物哈希（`research/s01b-20261108/`，sha256 前 16 位）：`PREREG_S01B_20261108.md` cf95a0b7、`mini_trailing_tp_result.json` 67c2c027、`results/compare_cross_down.json` 16e7d1c5、`metrics.json` 6174f4da（OOS 逐档自算后重出，旧值 7fbfea0a 作废）、`metrics_table.md` d025d8ce（旧值 2bb3d55b 作废）、`verify_list_result.json` 57412ac7（META 加状态标注后重落盘，旧值 fc935db4 / 6ee1f34b 作废）、`risk_limits_production_table.json` b467f560、`seed_risk_values.json`、`REPORT.md`（本文件）。
每臂 `results/<tag>/result.json`：a0_10bp b9dbf332、a0_30bp de256c81、a0_gross 0a0c1878、a1_10bp fc499ac1、a1_30bp 5ab2a3b4、a1_gross 8d026222、a2_10bp 239f6785、a2_30bp 613f5edc、a2_gross 9a4f6b8c、a3_10bp 6503ce14、a3_30bp 050c3ce9、a3_gross 4eac0122、a2h_10bp c1f8383e、a4_10bp ae7905a3、a0ev_10bp 5657d5fb、a3ev_10bp cc8abd29、**prod_file_10bp 2aded0a6**（生产文件自跑，§1.1；17:1x 版为 8d5be642，因 result.json 带 run_id/timing 而变，交易与权益文件不变）；每臂另有 `trades.parquet` / `equity.parquet`。

## 8. 复核返工记录（2026-11-08 17:1x–17:5x，按开发经理复核对账四条 + 一条附加，另自查补正一条）

| # | 复核意见 | 处置 | 复算/证据 |
|---|---|---|---|
| 1 | §4.2 的击穿分档句不可复现（旧区间 `[−8.085%, −8.00%]` 实测 0 笔） | 整段改写为单一区间口径 + 一行 pandas 复算式，数字改 **315**；原文作废并留更正说明 | 复算：`[−8.10%, −8.00%]` = 315、`[−8.085%, −8.00%]` = 0、`< −15%` = 22、`> 0` = 1（共 425 笔）；众数 −8.0919%（88）/ −8.0920%（85）；理论值 `0.92×0.999−1 = −8.0920%` 与实盘众数吻合 |
| 2 | 全期年化与 OOS 年化混用两种年长 | §4.1 主表与对照表**各加一列**「全期年化(日历年7.33年)」；表脚写死三种年化公式与年长；新增 §4.5 复算式 | 日历年列：臂0 +3.01% / 臂1 −15.03% / 臂2 −23.14% / 臂3 −23.60% / a4 −14.52%（交易日月列不变：+3.13% / −15.56% / −23.91% / −24.39%） |
| 3 | 生产策略目录残留 `.step1` | 移到 `research/s01b-20261108/prod_file_snapshots/custom_mw7fvp17.py.step1_4472B_2cc00778`，文件名带原大小与 sha 前缀 | 移动后生产目录仅剩 `custom_mw7fvp17.py` 与 `.bak_20261108`；目标文件 4,472 B / `2cc00778…` 与原值一致 |
| 4 | 738 passed 不能作硬断言 | 全文口径改为以「**737 passed + 1 条 spawn 用例偶发（单跑 2/2 通过）**」为可复现基线，738 passed ×3 只作本机观察记录，并给出三次运行条件（§5.2） | 该用例单跑 `1 passed in 7.88s`（本机 1/1 + 开发经理 2/2）；对新增 `risk_limits` 零引用（`grep -c` = 0）⇒ 判定 spawn 抖动 |
| 附加 | 条目需状态标注 | `META.description` 末尾加一句事实陈述（F1/F4 成立、未达基线、指向本报告） | 改后文件 5,510 B / `918254f0…`；重跑 `prod_file_10bp` 七项数字不变，trades/equity 与 `a3_10bp` 字节相同；`verify_list.py` exit 0、列表 5 条含本策略 |
| 5（自查补正） | §4.1 主表 30bp / gross 行的 OOS 三列与 10bp 行**完全同值**（8 行 × 3 列 = 24 个格子） | 根因：`report_metrics.py` 里 `out["oos"] = equity_metrics(tag10)` 只按 10bp 算一次、三个成本档共用；改为 `oos_by_scen` 逐档自算并重出表，§4.1 表脚加注、§4.5 ③ 复算式改为逐档循环 | 新值（30bp → gross）：臂0 OOS 年化 +3.32%→+5.90%、OOS MDD −30.33%→−28.98%、OOS Sharpe +0.24→+0.34；臂1 −18.54%→−16.94% / −70.71%→−67.72% / −0.62→−0.56；臂2 −11.01%→−6.83% / −60.56%→−58.08% / −0.30→−0.14；臂3 −14.56%→−9.17% / −65.23%→−58.02% / −0.46→−0.24。10bp 行与 F1–F4 判据读数一字未变 |

**纪律复查**：HEAD 仍 `52ead74c`，未提交、未部署、未重启服务、未写生产库 strategy row；`D:\TSP` 只动 `custom_mw7fvp17.py` 本体与它的 `.bak_20261108`，`.step1` 已移出；研究侧台账（`registry.json` / `GLOBAL_LEDGER_v3.json` / `FREEZE.json`）本轮未触碰（工作区里这三者显示为已改，是他人此前的未提交改动，不属本轮）。
