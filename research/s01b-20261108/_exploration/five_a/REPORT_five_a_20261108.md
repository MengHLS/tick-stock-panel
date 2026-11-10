# ⑤-a 单臂分解实施记录（S01 / custom_mw7fvp17 生产文件，默认口径基线）

生成方式：`gen_report.py` 直接读取各臂 `arms_table.json` / `manifest.json` / `control7_diagnosis.json`，数字不经手抄。

## 摘要（先看这四条）

1. 七个 run 目录 + `base_nodefaults_gross` 全部跑完，每臂 `result.json` 内嵌 `effective_config` 全量键值，且 `resolved_matcher_config` 证明**每臂只动一个开关**。
2. 移动最大的是 `block_limit_open`（总收益 −51.47% → +12.13%，+63.60pp），其次是 `exit_signal_requires_profit`（+18.85pp），其余三项 |Δ| ≤ 5.06pp，`trailing_peak_price` 完全为 0。**各臂不可相加。**
3. 对照组：第 6 项 `trailing_peak_price` **惰性通过**（三张 parquet 与基线逐字节同 hash）；第 7 项 `exit_signal_requires_profit` **不惰性（+18.85pp）**——已查明不是夹具漏键，而是该键生产默认就是 `False`，打开它是真实加闸。按令停下报告，等裁定。
4. 任务 B：默认口径下 gross 全期年化 **−8.67%**，为负。

## 0. 口径与前提

- 基线 = **生产文件原样、不注入任何 `backtest_defaults`** ⇒ 208 笔（本任务基线）。
- 区间 2019-07-01…2026-10-30，初始 1,000,000 元，最大 5 仓，60% 敞口上限，次日开盘执行，成本 10bp（佣金 3e-4 + 印花 1e-3 + 滑点 10bp）。
- 单臂 = 只注入一个开关（`execution_costs` 记为一项，含 `min_commission` + `transfer_fee_pct` 两个子键）。每臂仅一个进程、一个策略文件、一条管道。
- 策略文件（磁盘，未改）：`D:\TSP\data\strategies\custom\custom_mw7fvp17.py` = 3,478 B / `85ae72a5318523d1515903314a817ca5a75cd07b33790cefe0d7b5acea794a07`。

## 1. 单臂总表

| # | 臂（目录名） | 单一开关 | 笔数 | 总收益 | 年化(252) | MDD | Sharpe | 期末权益 | buy_limit_up | sell_suspended | sell_limit_down | sell_invalid_price | pending_exit | 同键笔数 | 同键 pnl Δ | 仅本臂笔数 | 仅本臂 pnl | vs 基线 | 三 parquet |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 基线 | `base_nodefaults_10bp` | `baseline` | 208 | -51.47% | -9.73% | -71.95% | -0.28 | 485,293.78 | 226 | 1 | 0 | 0 | 1 | 208 | 0.00 | 0 | 0.00 | +0.00pp | 逐字节相同 |
| 2 | `only_entry_price_basis_raw` | `{"entry_price_basis": "raw"}` | 208 | -56.53% | -11.13% | -74.31% | -0.34 | 434,710.53 | 225 | 1 | 1 | 0 | 2 | 195 | -7,122.88 | 13 | -55,748.24 | -5.06pp | 不同 |
| 3 | `only_block_limit_open` | `{"block_limit_open": true}` | 198 | +12.13% | +1.64% | -40.12% | 0.19 | 1,121,259.36 | 534 | 0 | 0 | 0 | 0 | 113 | -49,962.74 | 85 | 492,109.18 | +63.60pp | 不同 |
| 4 | `only_finalize_open_at_end` | `{"finalize_open_at_end": true}` | 208 | -52.18% | -9.92% | -71.95% | -0.29 | 478,212.34 | 226 | 1 | 0 | 0 | 1 | 208 | 32,536.62 | 0 | 0.00 | -0.71pp | 不同 |
| 5 | `only_execution_costs` | `{"execution_costs": {"min_commission": 5.0, "transfer_fee_pct": 2e-06}}` | 208 | -51.46% | -9.73% | -71.94% | -0.28 | 485,420.69 | 226 | 1 | 0 | 0 | 1 | 208 | 126.87 | 0 | 0.00 | +0.01pp | 不同 |
| 6 | `only_trailing_peak_price_close` | `{"trailing_peak_price": "close"}` | 208 | -51.47% | -9.73% | -71.95% | -0.28 | 485,293.78 | 226 | 1 | 0 | 0 | 1 | 208 | 0.00 | 0 | 0.00 | +0.00pp | 逐字节相同 |
| 7 | `only_exit_signal_requires_profit` | `{"exit_signal_requires_profit": true}` | 178 | -32.62% | -5.44% | -61.77% | -0.11 | 673,798.76 | 225 | 1 | 1 | 0 | 2 | 52 | 40,463.25 | 126 | -10,499.85 | +18.85pp | 不同 |
| B | `base_nodefaults_gross` | `成本全零（gross）` | 208 | -47.29% | -8.67% | -71.08% | -0.23 | 527,074.75 | 226 | 1 | 0 | 0 | 1 | 208 | 41,831.53 | 0 | 0.00 | +4.18pp | 不同 |

**各臂不可相加**：上表只回答「单独打开这一项，数字移动多少」，不做占比合成。开两项以上不是两项之和（路径依赖）。

## 2. 每臂「只开一项」的证明（证据 ①）

比较口径：`result.json` 里嵌入的 `effective_config`，取 **`resolved_matcher_config`**（= 引擎实际用的，不是我们要求的）与基线逐键对比；`single_toggle_injected` 是注入回显，`strategy_meta_backtest_defaults_effective_raw` 是 META 原样，二者只作旁证。

| 臂 | 实际改变的配置键（resolved） | 仅由该键派生的字段 |
|---|---|---|
| `base_nodefaults_10bp` | （无，基线） | — |
| `only_entry_price_basis_raw` | `entry_price_basis`: adjusted → raw | — |
| `only_block_limit_open` | `block_limit_open`: False → True | — |
| `only_finalize_open_at_end` | `finalize_open_at_end`: False → True | — |
| `only_execution_costs` | `execution_costs`: None → {'min_commission': 5.0, 'transfer_fee_pct': 2e-06, 'buy_slippage_tiers': [], 'price_decimals': 4} | — |
| `only_trailing_peak_price_close` | `trailing_peak_price`: high → close | — |
| `only_exit_signal_requires_profit` | `exit_signal_requires_profit`: False → True | `exit_signal_profit_basis`: None → holding_peak_close |
| `base_nodefaults_gross` | `commission_pct`: 0.0003 → 0.0, `slippage_bps`: 10.0 → 0.0, `stamp_tax_pct`: 0.001 → 0.0 | — |

`effective_config.json` 另外记录了完整未截断的 `request` / 归一化后的 `execution_policy_normalized` / `resolved_matcher_config` / 策略文件哈希与算法版本；每臂同时嵌在 `result.json.effective_config` 里（现存 a0 侧 result.json 缺这一块）。

## 3. 双价基（证据 ②）

每臂 `trades_priced.parquet` 44 列，含 `entry_price_raw` / `entry_price_adj` / `exit_price_raw` / `exit_price_adj`，以及当日复权因子 `cf_entry` / `cf_exit`，另有 `entry_open_adj|raw`、`exit_open_adj|raw`、`entry_close_adj|raw`、`exit_close_adj|raw`、`entry_price_engine`/`exit_price_engine`（引擎实际记账价）与 `entry_price_check`/`exit_price_check`（逐笔核对结论）。

核对结果（`entry_price_check` / `exit_price_check` 分类计数，`unexplained` 必须为 0）：

| 臂 | basis | entry 核对 | exit 核对 | unexplained |
|---|---|---|---|---|
| `base_nodefaults_10bp` | adjusted | {"ok": 208} | {"ok": 208} | 0 |
| `only_entry_price_basis_raw` | raw | {"corp_action_restated(x1.3000)": 2, "corp_action_restated(x1.4000)": 1, "corp_action_restated(x1.5000)": 1, "ok": 204} | {"ok": 208} | 0 |
| `only_block_limit_open` | adjusted | {"ok": 198} | {"ok": 198} | 0 |
| `only_finalize_open_at_end` | adjusted | {"ok": 208} | {"close_valuation(end)": 5, "ok": 203} | 0 |
| `only_execution_costs` | adjusted | {"slippage_in_price": 208} | {"slippage_in_price": 208} | 0 |
| `only_trailing_peak_price_close` | adjusted | {"ok": 208} | {"ok": 208} | 0 |
| `only_exit_signal_requires_profit` | adjusted | {"ok": 178} | {"ok": 178} | 0 |
| `base_nodefaults_gross` | adjusted | {"ok": 208} | {"ok": 208} | 0 |

## 4. 三张 parquet 的 sha256（证据 ③，`manifest.json`）

| 臂 | trades.parquet | equity.parquet | drawdown.parquet |
|---|---|---|---|
| `base_nodefaults_10bp` | `d595d31c144a761d7286609c9b3bf4c2eace2573fe1383c3816df011365b7a56` | `b0d1612804996396bb7bf0839b28828b4fed98e419d907d8d262c3f15190bffb` | `5d26ce86767199398e2fa48100c934b77f8ce7797adcaa79eb1996bbf1592ced` |
| `only_entry_price_basis_raw` | `97b45411ead186dfdc882416679ce2a85a436cb433a21d3e678b3a6ca9385135` | `b7e6f7e5977d86aaa12a5ac2e7d55ea254a7b1c50b643ec80da6a4bea7adbac5` | `1d7ba340cc7035ce3da83d5f49336dc4b218988c14b414cf4ca8800cce138670` |
| `only_block_limit_open` | `697bf05373dd18cf343fbf372f2fbc3166862b60256fc05c66838e3ce16a84d8` | `b6ad9938ee14a2dad4cb944586f4e3704c80ca5add055ef4ff33a4c25328a297` | `36579853ec634387bea6f3df9672df27694d1f5b742baf37f4d8e74c9790cb82` |
| `only_finalize_open_at_end` | `c2f6d54c3800be23eba7b2bd83223b03502d04871f58993640e061661fefc74e` | `04989612393ab5fb3d614a86c098f86cb441e017c2378d8e2b9b98aaff988a38` | `ba0219c13d01b1e403bc0d1c65d7d33ee129772fc74d19fc5c42a6337e90d34b` |
| `only_execution_costs` | `38f07d8005d48a022aa700be11a7a601971df5b2da6f3a02c8090c51fa7d4495` | `50fa64c5893983528263cb34f01193ae2d7bc40a9b9d5854239d8d2ff51d9fbc` | `47a040bc0e5df214e6f4a5bb2b7c0131a938144ce853bb20299a968ffdf22610` |
| `only_trailing_peak_price_close` | `d595d31c144a761d7286609c9b3bf4c2eace2573fe1383c3816df011365b7a56` | `b0d1612804996396bb7bf0839b28828b4fed98e419d907d8d262c3f15190bffb` | `5d26ce86767199398e2fa48100c934b77f8ce7797adcaa79eb1996bbf1592ced` |
| `only_exit_signal_requires_profit` | `a4634cb6edd43611730f23fd6e6164db8c200e6689dedb887f8b5e0ff6b67d48` | `e21dc8fedd0c5ca20ac9b68058231c984eb368196adb6981e71eb254d254892c` | `d4593e0f5fcdbfaa035035050938647d7c10c42f1548bbad35f29abfbf0e694d` |
| `base_nodefaults_gross` | `aef69c2bf4f7459fc676306e700b98da18598dba1791e4d1ad42eddcf3433a81` | `be167d4aecffa2d2f6a9912a40cf9fe0a10304728599842af81d306db79fa46f` | `a504f0db202ffbef31e967e274f32c0ec3b3f10e6deb81e8ed4d788fdf5b9951` |

`manifest.json` 另含每臂 `result.json` / `effective_config.json` / `trades_priced.parquet` 的 sha256 与策略文件 sha256。

## 5. 对照组结论（第 6、7 项）

### 5.1 第 6 项 `only_trailing_peak_price_close` —— **惰性，通过**

- 208 笔 / 总收益 -51.47% / 年化 -9.73% / MDD -71.95% / 期末 485,293.78，与基线**完全相同**；
- **trades / equity / drawdown 三张 parquet 与基线逐字节同 hash**（见 §4），同键 208 笔、同键 pnl Δ = 0.00、仅本臂 0 笔；
- 解释：`trailing_peak_price` 只喂移动止盈/移动跟踪的峰值价，策略没有 `TRAILING_*` 阈值（`STOP_LOSS=None`、无移动止盈），该键无驱动对象 ⇒ 惰性。夹具未漏键。

### 5.2 第 7 项 `only_exit_signal_requires_profit` —— **不惰性：数字动了，按令停下报告**

- 178 笔 / 总收益 -32.62%（vs 基线 -51.47%，+18.85pp）/ 年化 -5.44% / MDD -61.77% / Sharpe -0.11 / 期末 673,798.76；
- 同键 52 笔、同键 pnl Δ 40,463.25，仅本臂 126 笔 / -10,499.85。

**不是夹具漏键**（先排除这一条，因为它决定要不要停）：§2 显示本臂 `resolved_matcher_config` 只有一个键变化 `exit_signal_requires_profit: False → True`，外加由它派生的 `exit_signal_profit_basis: None → holding_peak_close`；三张 parquet 虽与基线不同，但那是结果不同，不是配置多头。**夹具干净。**

**动的原因：这条开关在生产默认里是 `False`，打开它是「真实开一项」而不是惰性项。**基线 `execution_policy_normalized` 与 `resolved_matcher_config` 都写着 `exit_signal_requires_profit=False`（日志同样打印 `"exit_signal_requires_profit": false`），派单里「默认已 false ⇒ 惰性」的推断方向反了：false→true 是加了一道闸。

闸的语义（`engine.py:2865-2875 _exit_signal_profit_armed`）：信号出场只在持仓期内收盘价曾高于成本价时才放行（`max(close over holding) > entry_price`）。实测（`control7_diagnosis.json`，脚本 `diagnose_control7.py`，退出码 0）：

- 基线 150 笔 `signal` 出场中，闸门挡下 **35** 笔（持仓期峰值收盘从未高于成本），放行 115 笔；
- 被挡的 35 笔在臂 7 的去向：{"null": 24, "max_hold": 10, "signal": 1}（`null` = 该笔在新路径下不存在，因为出场日晚了/换了，后面建仓的标的与顺序整体位移）；
- 被挡 35 笔在基线 `pnl_amount` 合计 -930,342.08；其中 11 笔在臂 7 仍能按 `(symbol, entry_date)` 配上、合计 -276,847.22（已达 24 笔因路径位移不再存在，无法逐笔配对）；
- 残差：按「峰值收盘 > 成本」近似复算闸门，H1 违例 1 笔、H2 违例 1 笔（闸门用的是引擎内部 `risk_entry_price` 与持仓期口径，我这里是外部近似，1 笔对不上属近似误差，不影响「不惰性」的结论）。

按要求**没有**继续往下归因，也没有把这项与其他臂合成。请裁定：这一项在 ⑤-a 里算「真实开关」还是从对照组里剔除。

## 6. 任务 B：默认口径 gross（`base_nodefaults_gross`）

- 不注入 defaults、成本全零（`commission_pct=0`、`stamp_tax_pct=0`、`slippage_bps=0`，`gross=True`）：208 笔 / 总收益 -47.29% / 年化 -8.67% / MDD -71.08% / Sharpe -0.23 / 期末 527,074.75。

**一句话结论：默认口径下 gross 全期年化仍为负（-8.67%），不是正。** 因此 F2 那句「入场有弱正 gross alpha（+4.21%）」**必须带口径限定**：+4.21% 的出处口径由研究侧标明（本任务没有重跑那条口径的 gross，不代它发言），但同一策略在默认口径下 gross 是负年化，去掉限定就会与新读数相互矛盾。

## 7. 落地物与命令

| 文件 | 作用 |
|---|---|
| `run_arm.py` | 单臂运行器（一进程一臂；可选择性注入一个开关；落三 parquet + result.json + effective_config.json） |
| `inject/*.json` | 各臂注入载荷（`base` 无文件 = 不注入） |
| `compare_and_manifest.py` | 同键对比、双价基逐笔、sha256 清单、arms_table 四格式 |
| `diagnose_control7.py` | 第 7 项不惰性的机制证据（只读，不改任何臂） |
| `gen_report.py` | 本报告生成器 |
| `logs/*.log` | 每臂与对比、诊断的完整 stdout（UTF-16） |

退出码：七臂 + gross 运行 `run_arm.py` 全 0（`result.json.error` 均为 `null`）；`compare_and_manifest.py` 0；`diagnose_control7.py` 0；`gen_report.py` 0。

