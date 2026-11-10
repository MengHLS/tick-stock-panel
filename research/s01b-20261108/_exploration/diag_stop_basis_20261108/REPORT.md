# S01b 臂1 止损口径诊断：H1（raw 入价 vs 复权收盘）× H2（无新信号回补）

**只读诊断**：未改 `backend/app/backtest/engine.py`、测试、`D:\TSP` 生产策略文件、其它 11 条策略、生产库 strategy row；未跑 8 臂全量；未覆盖 `results/` 与 `five_a/`。本目录全部产物为新增文件。

## 0. 开局自检（实测，与派单锚点一致）

| 项 | 实测 | 派单 |
|---|---|---|
| `backend/app/backtest/engine.py` | 268,800 B / sha256 `ecc3d8261c5605ed…` / mtime 2026-11-07 00:01 | 一致 |
| git HEAD / 工作树脏改动 | `22ed822a` / 112 条 | 一致 |
| `research/s01b-20261108/metrics_table.md` | 2,738 B / `d025d8ce…` | 未动（脚本每次校验） |
| `research/s01b-20261108/REPORT.md` | 52,097 B / `e60cd0b8…` | 未动（脚本每次校验） |

## 1. 结论

| 假设 | 结论 | 一句话数字 |
|---|---|---|
| **H1** raw 入场价对前复权收盘价比 → 假止损 | **不成立（REFUTED）** | `entry_price_basis="raw"` 时执行平面整块换成原始价（不只有入场价）；同一批 519 笔按「全 raw」与「全复权」重算止损触发率 **82.47% vs 82.08%，差 0.39pp** |
| **H2** 止损后不等新金叉就回补同一标的 | **不成立（REFUTED）** | 同标的相邻两笔 **23 对**，**23/23 = 100%** 之间都有新金叉且严格晚于上一笔出场；同日回补计数 **0** |

成立与否的判定口径写在 §4、§7；H1 不成立，故不触发「若 H1 成立」的单臂重算条款，**没有作废 metrics_table.md 的任何条目**（§6）。

## 2. H1 证据①：臂1 全部 stop_loss 出场逐笔（425 笔）

文件 `stop_loss_trades_evidence.csv`（148,813 B / 425 行 + 表头 / 36 列）。列含：`symbol, name, entry_date, exit_date, entry_price_fill, entry_price_ex_slippage, entry_day_open_raw, entry_day_close_raw, entry_day_adj_ratio, adj_factor_entry, exit_day_close_raw, exit_day_adj_ratio, adj_factor_exit, stop_line_raw, stop_line_adj, trigger_day_raw, trigger_offset_raw, trigger_rule_raw, trigger_day_adj, trigger_rule_adj, trigger_plane, entry_day_trigger, first_session_trigger, exit_on_first_session_after_entry, pnl_pct, exit_price_fill, …`。
`adj_factor_*` = 前复权价 / 原始价 = `close/raw_close`（≤1）；`entry_day_adj_ratio` 是其倒数（还原比例）。

臂1（519 笔）：`stop_loss 425`（81.9%）、`max_hold 50`、`signal 42`、`end 2`。425 笔 stop 的形态：

| 项 | 数字 |
|---|---|
| 触发规则（原始价口径） | `low_touch`（当日最低 ≤ 停损价）**320** / `open_gap`（开盘直接穿价）**67** / `entry_close`（建仓日收盘 ≤ 停损价）**38** |
| 触发日 = 出场日 | **374 / 425 = 88.0%** |
| `pnl_pct` | p50 **−8.2394%**、p10 −11.3938%、p90 −8.2391%；**99.53%** 落在 −7.74% 及以下 |
| 成交价 = 停损价×0.999（停损价再扣 10bp 滑点） | 332 / 425 = **78.1%**（±0.5% 内） |

## 3. H1 证据②③：首日即止损的笔数、两套口径的触发率

**②「建仓后第 1 个交易日即止损」**：**94 笔 = 占 425 笔 stop 的 22.12% = 占 519 笔的 18.11%**（`trigger_offset_raw == 1`）。
另两项同族数字：建仓**当日收盘**触发 **38 笔 = 8.94% / 7.32%**；出场日就是建仓后第 1 个交易日 **129 笔 = 30.35% / 24.86%**。

**③ 同一批 519 笔，两套口径各重算一次止损触发率**（窗口 = 该笔 entry→exit 实际持仓窗）：

| 口径 | 触发笔数 | 触发率 |
|---|---|---|
| 全 raw（原始入价 vs 原始收盘/最低） | 428 | **82.47%** |
| 全复权（复权入价 vs 复权收盘/最低） | 426 | **82.08%** |
| **差值** | 2 | **0.39pp** |

固定 60 交易日观察窗：raw **84.97%**(441) vs 复权 **84.78%**(440)，差 **0.19pp**。全窗只有 **2 例**分歧（`600985.SH` 2024-04-23，signal 出场；`001210.SZ` 2026-05-18，stop 出场），列在 `summary_h1.json → trigger_rate.disagreements`。
⇒ 两套口径几乎不可区分（<0.5pp）；且**引擎实际用的就是全 raw**，不存在混比。

## 4. H1 证据④：停损比较处与基准价处的准确行号（逐处是否乘 adj_factor）

| # | 位置 | 做什么 | adj_factor |
|---|---|---|---|
| 1 | `backend/app/backtest/engine.py:2591-2607` | `entry_price_basis=="raw"` ⇒ `execution_open/high/low/**close**` 整块取 `_raw_execution_prices`；否则取 `matrix.close` 等 | **是**：原始平面由前复权 OHLC × 当日 `raw_close/close` 还原（`engine.py:1395-1444`，`_RAW_PRICE_DECIMALS=2` 四舍五入） |
| 2 | `engine.py:1528-1542` `_resolve_entry_prices` | 入场基准价：raw 基准下 `base = raw_prices[0]`（原始开盘，`open_t+1`） | **是**（同上整块还原） |
| 3 | `engine.py:3695-3697` + `:2807-2817` | 入场成交价 = 基准价 × 滑点/成本（`execution_costs` 存在时 `fill_price` 把 10bp 乘进价格） | 否（价格已是原始价，只乘 1.001） |
| 4 | `engine.py:3415` / `:3739` | `risk_entry_price` = 入场成交价 | 否（承接 ③） |
| 5 | `engine.py:4106-4111`（**建仓日停损判定**） | `stop_line = risk_entry_price × (1−|−8%|)`；比较价 `current_close = execution_close[time_id, asset_id]` | 两侧同为 raw 平面 ⇒ **无混比** |
| 6 | `engine.py:4017-4019` + `:4027-4028` + `:4054-4067`（**非建仓日停损计划**） | `open/low/high` 取自 `execution_*`；`open ≤ stop` 按开盘价、`low ≤ stop` 按停损价成交 | 同为 raw 平面 |
| 7 | `engine.py:3831-3833` + `:1488-1512` | 除权日 `risk_entry_price ×= price_factor`（`price_factor` = 含分红的 `total_return_factor`） | **是**：随事件同步缩放，保持 raw 口径连续（否则送股日必假触发） |
| 8 | `backend/app/backtest/strategy.py:3586-3587 / :1601 / :1592,:1871 / :1850` | `backtest_defaults.entry_price_basis="raw"` → `MatcherConfig.entry_price_basis`；`STOP_LOSS=-0.08` → `stop_loss_pct` | 策略侧不做价格换算（只传参数） |
| 9 | `research/s01b-20261108/strategies/custom/s01b_a1.py:19 / :53` | 臂1 的 `"entry_price_basis": "raw"` 与 `STOP_LOSS = -0.08` | — |
| 10 | `backend/app/backtest/engine.py:1256-1263 / :1304-1309`（`simulate`）、`:4541-4544`（`simulate_portfolio_legacy`） | legacy 段落用 `panel["close"]/["open"]`（前复权），两边同口径；**但不读 `entry_price_basis`** | 登记 **X-2**，未改 |

`matrix.close` 确为前复权、`matrix.raw_close` 为原始价：`backend/app/indicators/pipeline.py:251-260`（`adjusted = raw × cum(≤date)/cum_total`，前复权）→ `kline_daily_enriched.close`；`engine.py:1056` 取 `raw_close`。复权表事实见 `data_adjfactor/evidence.md`（496 标的 800,539 行上 `close/raw_close` 与因子表偏差 **0 行 >1e-4**，**0 只**被默认成 1.0；519 笔里持仓期内真发生除权 **25 笔 = 4.82%**）。

**入场价口径实测**：519 笔中 **517 笔（99.6%）** `entry_price/1.001` 落在当日原始开盘 ±0.5% 内（偏差中位 **+10.0bp** = 滑点）⇒ 入场价确实用原始价。2 笔例外**不是**价基错配，是**送股后 `entry_price` 按股数重算**（`engine.py:3823-3833`）：

| symbol | entry_date | 记录 entry_price | 当日原始开盘 | 持有期内送股事件 | 验算 |
|---|---|---|---|---|---|
| 300671.SZ | 2021-04-14 | 35.42 | 46.00 | 2021-05-27 10转3（`bonus .3`） | 46.00/1.3×1.001 = 35.42 ✅ |
| 001210.SZ | 2026-05-18 | 20.5205 | 28.70 | 2026-06-05 10转4派2.5（`bonus .4`） | 28.70/1.4×1.001 = 20.52 ✅ |

## 5. 那么 33.5% → 15.1% 是怎么来的（数字，不是猜测）

止损触发率就是 **81.9%**，这是真实触及，不是口径造出来的。三道独立佐证：

1. **池子基准率**：全池 9,002,802 个 (symbol, 交易日) 窗口上，以当日原始开盘为参照、其后 60 个交易日内原始最低价触及 −8% 的占 **67.94%**（`summary_winrate.json → A`）。−8% 在本池是「大概率会发生」的回撤，不是尾部事件。
2. **同一规则套在臂0（不设止损）的 199 笔上**：按其各自持仓窗，**76.88%（153 笔）** 也会触及 −8%（`a0_counterfactual_stop8.csv`）。
3. **单标的持有窗反事实（entry 后 60 个交易日的原始收盘 vs 建仓成交价，不含槽位约束）**：

| 组 | 笔数 | 60 日后为正 | 中位收益 |
|---|---|---|---|
| 被止损的 425 笔 | 425 | **24.24%**（103） | **−13.26%** |
| 未止损的 94 笔 | 94 | 79.79%（75） | +23.07% |
| 全部 519 笔 | 519 | 34.30%（178） | −9.37% |

把 519 笔按「不设止损、持满 60 日」重建的胜率 = (75+103)/519 = **34.30%**，与臂 0 实测 **33.5%** 相差 **0.8pp** ⇒ 止损砍掉的不是「本会盈利的单」，而是把 **76% 本来就会亏**的单提前钉在 −8.24%；剩下 24% 本会转正的单也被钉住，于是胜率从 33.5% 掉到 15.1%，median 被压到 −8.24%。
另：建仓日引擎按**收盘**判、其余交易日按**开盘/最低价**判 ⇒ 建仓日更宽松（收盘触发 38 笔；若按最低价会是 66 笔），不存在「建仓日误杀、次日不误杀」的怪形状。

## 6. metrics_table.md 的影响：**0 臂 / 0 列作废**

H1 不成立 ⇒ 不触发单臂重算，`metrics_table.md` 与上游 `REPORT.md` 一字未动。逐条对齐：

| metrics_table 条目（臂1 10bp） | 处置 | 依据 |
|---|---|---|
| 笔数 519、胜率 15.1%、avg/median −1.45%/−8.24%、持仓 p50/p90 5/59、换手 5.39x | **保留** | 触发率 82.47%（raw）与实测 425/519=81.9% 一致；p50 pnl −8.2394% 与「−8% 停损价 + 双边成本」闭式一致 |
| 臂0 胜率 33.5% / median −9.64% | **保留** | 反事实重建 34.30%，Δ0.8pp |
| 臂2/臂3 的 median −8.24% 三行同值 | **保留**（同上，止损价成交） | 99.53% 的 stop pnl 集中在 −8.24% |
| 需在报告口径里补一句的话（研究侧裁量，非实现改动） | 建议 | −8% 相对本池 60 日基准率 67.94% 属过紧参数；要评估止损优劣，应至少加 −15%/−20% 档，否则四臂里「臂1..3 vs 臂0」的差主要度量的是参数过紧，不是风控设计 |

## 7. H2：止损后是否必须等新金叉才回补同一标的 → 不成立

**判定「新金叉」**：`research/s01b-20261108/strategies/custom/s01b_a1.py:81`（`cross_up = (fast > slow) & (prev_fast <= prev_slow)`）→ `:87` `entry = cross_up`；`backend/app/backtest/matrix.py:2502-2507` + `:3184-3208` 把 `entry` 右移 1 个 bar（`open_t+1`）。
**判定「可回补/可再建仓」**：`backend/app/backtest/engine.py:3593-3616`（矩阵态：已有同标的持仓跳过 `:3595-3597`、当日已卖该标的计数跳过 `:3598-3600`、槽位不足 `:3614-3616`）；计划态同一套限制 `:3333-3358`。

**数字**（`h2_pairs.csv` / `summary_h2.json`）：
- 519 笔 / 496 只标的；全部相邻对 **518**，其中同一标的相邻对 **23**（分母写明：23 / 518）。
- 这 23 对之间「存在新金叉（严格晚于上一笔出场）」= **23/23 = 100%**；复用上一笔的信号日 = **0**。
- 出场到下一笔信号相隔交易日：min **26** / p50 **430** / max **1491**。
- 同日回补计数 `buy_same_day_reentry = 0`；`buy_no_slot = 69,042`；`buy_limit_up = 550`。
- 519 笔的入场信号日 **519/519** 都在面板上、且当日 `cross_up` 为真。

⇒ **519 笔不是「无新信号回补」造出来的**。笔数从臂0 的 199 涨到 519，来自**槽位释放节奏**：止损早退腾出槽位，后续本已存在但因 `buy_no_slot` 被拒的信号被吃进来（同一策略、同一区间、同一信号集）。

## 8. 复跑（仓库根 `C:\work\sourcecode\tick-stock-panel`，全部只读，实测退出码）

```bat
backend\.venv\Scripts\python.exe research\s01b-20261108\diag_stop_basis_20261108\diag_stop_basis.py        :: exit 0
backend\.venv\Scripts\python.exe research\s01b-20261108\diag_stop_basis_20261108\h2_reentry.py             :: exit 0
backend\.venv\Scripts\python.exe research\s01b-20261108\diag_stop_basis_20261108\explain_winrate.py        :: exit 0
backend\.venv\Scripts\python.exe research\s01b-20261108\diag_stop_basis_20261108\data_adjfactor\run_adjfactor_evidence.py :: exit 0
backend\.venv\Scripts\python.exe research\s01b-20261108\diag_stop_basis_20261108\verify_diag_stop_basis.py  :: exit 0（PASS 33 / FAIL 0）
```

`verify_diag_stop_basis.py` 自校验 33 条：上游三文件字节未变（engine.py / metrics_table.md / REPORT.md）、产物行数与 trades 回连一致、触发率用**另一套向量化实现**重算后与 `summary_h1.json` 同值、入场价 99.6% 对齐原始开盘、H2 的 23 对与新金叉计数、两条结论口径。日志：`run_diag.log` / `run_h2.log` / `run_verify.log` / `run_explain.log` / `data_adjfactor/run.log`。

产物（重跑会刷新含时间戳的 json 哈希，数字不变）：

| 文件 | 字节 | sha256 前 16 |
|---|---|---|
| `stop_loss_trades_evidence.csv` | 148,813 | `2cf9eafd0aabe772` |
| `all_519_basis_recompute.csv` | 202,839 | `2bffa021eee4c2c8` |
| `h2_pairs.csv` | 2,185 | `7528e889f5605eb2` |
| `a0_counterfactual_stop8.csv` | 10,698 | `435b8ea1a7a6b2ac` |
| `explain_winrate.csv` | 71,102 | `8d2a8f56ed359101` |
| `summary_h1.json` / `summary_h2.json` / `summary_winrate.json` | 3,992 / 1,807 / 1,576 | `630d44f6…` / `cb473adc…` / `b1957a98…` |

## 9. 未验证 / 边界

1. §5 的 60 日反事实是**单标的持有**（无槽位、无资金约束），不是引擎复算；只用于判别「止损砍掉的是不是潜在盈利单」。
2. 池子基准率用「当日原始开盘」为参照、只看**价格触及**，未扣涨跌停/停牌不可成交 ⇒ 真实可触发率应**更低**，67.94% 是上界。
3. 43 / 496 只标的在 `adj_factor` 无任何事件行（f 全窗 1.0）；无法用价格证明「确实无分红」（现金分红 <3% 不可分辨）。
4. `matrix_data_cache_hit=true`，但盘上 4 个缓存目录形状（1,719/990/794/606 日）与 `result.json.market_matrix_shape=[1779, 5811]` 都不吻合 ⇒ **无法确认 16:24 那次跑用的是哪个缓存文件**；反向证据是 `entry_price` 与当前 `kline_daily_enriched` 原始开盘 99.6% 对齐。
5. 未在 30bp / gross 臂上重复 H1/H2（同策略、同信号、只差成本档）；若成本档改变了成交价路径，触发率可能微动，但 H1 的结论是**代码结构**（执行平面整体换 raw），与成本档无关。
6. X-2 已登记未改：`engine.py:1256-1263 / :1304-1309 / :4541-4544` legacy 段落两边都用前复权价，**不读 `entry_price_basis`**；若将来把策略切到 legacy 引擎，`raw` 声明会静默失效（这两个诊断臂走的是 matrix_native 主循环 `:2591-2607`，不受影响）。
