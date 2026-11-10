# S01 跨管道差异归因（研究管道 vs 生产管道）

- 生成：2026-11-08 · 量化研究员
- 名义入场规则：MA20 上穿 MA60 入场、MA20 下穿 MA60 出场、最长持有 60 个交易日（两侧参数相同）
- 研究管道：`research/strategy-search-20261107/results/run_S01_ma_cross_20_60_10.json`（registry tag `S01_ma_cross_20_60@10`）
- 生产管道：`research/s01b-20261108/results/a0_10bp/trades.parquet`（臂 0，10bp、raw 价、挡涨停开盘、期末强平）
- 本报告只读：未改任何策略文件、未写 `D:\TSP`、未重跑已注册 tag。唯一代码改动在**本目录内**（`counterfactual.py`，见 §3.1）。
- 全部数字出处均为本目录 `results/` 下文件；命令见各节。

---

## 1. 匹配键与重叠

**键定义**：`(symbol, entry_date)`。`entry_date` = 实际成交日（信号日下一交易日开盘价成交），两侧字段同名同义。研究侧另有 `entry_signal_date`，生产侧亦有，用 `(symbol, entry_signal_date)` 做键得到同样的 3 笔重合，说明 3 笔不是"日历年移位"造成的。

| 量 | 值 | 出处 |
|---|---|---|
| 研究侧成交数 | 252 | `results/gap_sets.json` `research_all.n` |
| 生产侧成交数 | 199 | `results/gap_sets.json` `prod_all.n` |
| 重合 | **3** | `gap_sets.json` `research_common.n` / `prod_common.n` |
| 仅研究侧 | 249 | `gap_sets.json` `research_only.n` |
| 仅生产侧 | 196 | `gap_sets.json` `prod_only.n` |

3 笔为：`002463.SZ@2019-07-02`、`002938.SZ@2019-07-02`、`002124.SZ@2019-10-31`。

**为什么只有 3 笔，而不是多**：两侧都在"5 格满仓 + 候选远多于仓位"的状态下运行，因此成交集由**填格顺序**决定，而不是由入场规则决定。

- 候选数远大于成交数：研究侧 24,902 个入场信号 / 252 笔成交（`registry.json` runs.`S01_ma_cross_20_60@10`.signals / n_trades）；生产侧 85,379 个 `strategy_matches` / 199 笔成交（`s01b-20261108/results/a0_10bp/result.json` stats.selection）。
- 因满仓被拒：生产 `buy_no_slot=78422`（result.json stats.execution），研究 `buy_no_slot=22138`（registry.json 同 run 的 execution 字段）。
- 排序规则不同：研究侧 `run_continuous` 只用 `build_market_matrix(seg, entry, exit, ...)` 传布尔矩阵，不传 score（`research/strategy-search-20261107/scripts/common.py:361-364`），同分排序退化为矩阵列序（symbol 升序）；生产侧 `META.order_by="score"`、`descending=True`（`research/s01b-20261108/strategies/custom/s01b_a0.py:46-47`）。实测研究侧 `entry_score` 全为 `0.0`（唯一值 1 个），生产侧 70 个不同值（`results/trade_shape.json` entry_score）。

**3 笔的逐项核对**（`results/common_check.json`，`results/common_3_detail.json`，`results/common_3_fee_check.json`）

| 字段 | 差异笔数 / 3 |
|---|---|
| entry_price / exit_date / exit_price / exit_reason / duration | 0 / 0 / 0 / 0 / 0 |
| pnl_pct | 3（差 3.0e-5、2.2e-5、1.2e-5，生产侧略高） |
| pnl_amount | 3（+2.77、+2.20、+9,862.46 元） |
| shares | 1（002124：研究 7,800 股 / 生产 5,400 股） |

**结论：同一价格的相同交易，差异只在成本与份额口径，而且成本差可逐项对上，不是佣金档位差。**

- 佣金两侧均 3bp、最低 5 元；印花税两侧均 10bp（研究 `common.py` ACCOUNT `commission_pct=0.0003`、`stamp_tax_pct=0.001`、`min_commission=5.0`；生产 `a0_10bp/result.json` `commission_pct=0.0003`、`stamp_tax_pct=0.001`，`s01b_a0.py` `min_commission 5.0`）→ **佣金档位相同，pnl 差不是佣金档位差**。
- 过户费率不同：研究 `transfer_fee_pct=0.00001`（`common.py` ACCOUNT），生产 `transfer_fee_pct=0.000002`（`s01b_a0.py:23`），Δ=8e-6（0.08bp）× 双边成交额：002463 预测 2.76 元 / 实差 2.77 元，002938 预测 2.21 元 / 实差 2.20 元，残差均 ≤0.01 元。
- 002124 的 9,862.46 元差额来自份额：2,400 股 × 每股亏损 4.0881 元 = 9,811.44 元，其余 51.02 元是按成交额计的成本随规模放大（同费率，非不同费率）。

复算命令：`backend\.venv\Scripts\python.exe research\s01-caliber-gap-20261108\inspect_common.py`、`key_variants.py`。

---

## 2. 差集两侧画像：符号反转来自交易集不同

| 集合 | n | 平均 pnl_pct | 胜率 | 中位 pnl_pct | pnl_amount 合计 |
|---|---|---|---|---|---|
| research_all | 252 | −1.143% | 30.16% | −5.131% | −336,088.06 |
| research_only | 249 | −1.556% | 29.72% | −5.163% | −451,814.99 |
| research_common | 3 | +33.098% | 66.67% | +33.948% | +115,726.93 |
| prod_all | 199 | +1.274% | 32.66% | −8.110% | +326,858.21 |
| prod_only | 196 | +0.787% | 32.14% | −8.317% | +201,263.85 |
| prod_common | 3 | +33.100% | 66.67% | +33.950% | +125,594.36 |

出处：`results/gap_sets.json`。研究侧 252 笔与 registry 的 ALL 段一致（`registry.json` runs.`S01_ma_cross_20_60@10`.ALL：n_closed_trades 252、avg_pnl_pct −0.01143、win_rate 0.3016）。

**判读**

1. 两侧共有的 3 笔上，平均 pnl_pct 差 2.1e-5、胜率相同、逐笔价格与日期完全相同 → 撮合、撮合价基、持有期规则、成本规则在"同一笔交易"上不产生差异。符号反转不可能来自撮合/引擎。
2. 反转来自交易集本身：249 笔平均 −1.556% vs 196 笔平均 +0.787%。两侧胜率几乎相同（29.7% vs 32.1%）、中位数都是负的（−5.2% vs −8.3%），差异全在右尾（`results/tails.json`）：
   - 研究侧 252 笔中 pnl_pct>50% 的 8 笔合计 **+721,159.76**；其余 244 笔合计 −1,057,247.82。
   - 生产侧 199 笔中 >50% 的 19 笔合计 **+2,106,739.57**；其余 180 笔合计 −1,779,881.36。
   → 两侧都是"少数大赢家撑起全部收益"的结构，谁的 5 个格子恰好撞上多倍股，谁就是正的。生产侧抓到 19 笔、研究侧 8 笔，且两批几乎不重叠（生产 19 笔中只有 1 笔出现在 §3 的 C1）。
3. 差集内部结构不是"研究池更宽"：研究侧 249 笔差集**全部**满足生产池价格门槛（`close≥2`）且当日确有金叉信号（`results/research_only_classified.parquet`：`in_prod_pool_price=True` 与 `prod_signal=True` 各 249/249），其中 235 笔发生时生产侧已持有 5 个仓位（`prod_open_positions=5`）。也就是说，差集主体是"生产侧当时没格子"，不是"生产侧看不见"。
4. 生产侧 196 笔差集按研究侧门槛分桶（`results/prod_only_classified.parquet` gate 字段）：非 60/00 板块 94 笔 +506,439.24；研究池内但研究侧未选中 67 笔 −270,292.32；`prior_amount20<1e8` 31 笔 +25,422.02；`raw_close<3` 3 笔 −44,656.84；`observed_bars<120` 1 笔 −15,648.25。生产侧 199 笔的板块构成：00:49、60:56、30:57、68:33、92:4（`trade_shape.json`），研究侧只有 00:223、60:29。

复算命令：`backend\.venv\Scripts\python.exe research\s01-caliber-gap-20261108\key_variants.py`（生成 gap_sets 口径的聚合与 sorts）、`ro_breakdown.py`、`trade_shape.py`、`tails.py`。

---

## 3. 反事实：只换股票池，差异并未消失

### 3.1 运行与一处修复（本目录内）

- 首轮 `counterfactual.py` 在 C1 分支报错 `polars.exceptions.ColumnNotFoundError: unable to find column "rk_ret5"`（日志 `results/counterfactual_run.log`）：`build_signals` 需要 `add_universe` 产出的 `rk_*` / `market_breadth` 五列，而 C1 分支自行设置 `in_universe` 后直接调 `build_signals`，缺这些列。C0（研究原口径）在报错前已跑完并落盘。
- 修复方式（本目录内唯一改动）：新增 `add_cross_section()`，逐行照抄 `common.py` `add_universe` 的截面部分（`market_breadth` + 5 个 `rk_*`），只把池掩码换成调用方已设好的 `in_universe`；C1 里这些列的取值不被 S01 消费（S01 只用 `e_ma_cross`/`x_ma_cross`/`s_ma_cross`），仅为满足 `build_signals` 的列依赖。
- 命令：`backend\.venv\Scripts\python.exe research\s01-caliber-gap-20261108\counterfactual.py`，耗时 **149.8 s**（日志 `results/counterfactual_run2.log`，输出 `results/counterfactual.json`、`C0_trades.parquet`、`C1_trades.parquet`）。

### 3.2 结果

| 口径 | 笔数 | total_return | cagr | 胜率 | 平均 pnl_pct | avg_exposure | 期末权益 |
|---|---|---|---|---|---|---|---|
| C0 研究池 + 研究引擎（复现） | 252 | −32.0929% | −5.3377% | 30.16% | −1.143% | 0.5836 | 679,071.26 |
| C1 生产池 + 研究引擎 | 264 | −21.9304% | −3.4480% | 27.27% | −0.4554% | 0.5858 | 780,695.64 |
| 生产管道 a0_10bp（参照） | 199 | +24.27% | +3.13% | 32.66% | +1.274% | 0.5715 | 1,242,725.28 |

- **C0 精确复现研究管道**：252 笔、−32.0929%、cagr −5.3377%，与 `registry.json` 的 ALL 段逐位相同，且 `C0_trades.parquet` 的 `(symbol, entry_date)` 键集与 `run_S01_ma_cross_20_60_10.json` **完全相同（对称差 0）**。研究侧数字可信、可复跑。
- **C1 的候选数与生产侧几乎相等**：C1 入场信号 85,383 vs 生产 `strategy_matches` 85,379（差 4 个，量级上说明池口径确实对齐了）。
- **但 C1 的成交与生产几乎不重叠**：C1 264 笔 vs 生产 199 笔，逐笔重合 **2** 笔，Jaccard 0.0043；生产 19 笔 >50% 的赢家里只有 **1** 笔出现在 C1。
- **残余差异（本节要回答的量）**：换池只把研究侧从 −32.0929% 抬到 −21.9304%，即解释 **+10.16pp**；与生产的 +24.27% 仍差 **46.20pp**。
- 佐证机制：C1 用的是含全板块的生产池，但成交板块是 00:247、30:9、60:8、68:0 —— 与"研究引擎没有 score 排序、按 symbol 升序填格"一致（§1 第 3 条）。

**本节结论：差集不能由 `basic_filter` 股票池解释。** 股票池贡献约 10.16pp；未解释的 46.20pp 落在"候选相同、选中不同"，即满仓下的排序规则（研究侧无 score 排序、生产侧 `order_by=score` 降序）与由此产生的选股差异。

> **2026-11-08 18:2x 撤回（v1.10，见 `docs/research/caliber-decisions-20261107.md` §17.2 / §17.3）**：本句及本节「46.20pp 落在排序规则」作废。同一生产文件、同区间、同成本，仅执行口径族就能移动 75.74pp（208 笔 / −51.47% → 199 笔 / +24.27%）；该 75.74pp 中按 `pnl_amount` 口径仅 12.2% 来自同一批交易的重新定价，87.8% 来自成交集合本身改变（208 vs 199 笔、同 `(symbol, entry_date)` 键仅 111 笔）。故执行口径与排序/容量**不可加、均未分离**，46.20pp 在逐项拆开前不得归因于任何单项。`counterfactual.py` 文档里"换池后应只剩少量残差"的预判被证伪：残差是 46.20pp，不是少量。

**残余的边界（未确证项见 §5）**：本轮未在同一排序规则下重跑（那需要给研究引擎注入 score 矩阵，属改代码，超出本轮范围），因此 46.20pp 只能归因为"排序 + 容量交互"，不能拆成"排序 X pp / 其它 Y pp"。

---

## 4. "53 笔差集"这个数的来源核查

**结论：53 是两侧成交笔数的净差额，不是 53 笔可枚举的差集。** 两种等价的算法给出同一个 53：

- 252 − 199 = **53**（研究成交 252、生产成交 199）
- 249 − 196 = **53**（仅研究侧 249、仅生产侧 196）

出处：`results/gap_sets.json`（四个 n 字段）；`results/key_variants.json` 的 `net_count_diff: 53`。

用更松的键重算，**没有一把键能得到 53 笔重合或 53 笔差集**（`results/key_variants.json`）：

| 键 | 研究侧命中行 | 生产侧命中行 | 共同键数 | 仅研究键 | 仅生产键 |
|---|---|---|---|---|---|
| symbol + entry_date（本报告口径） | 3 | 3 | 3 | 249 | 196 |
| symbol（只比代码） | 15 | 10 | 10 | 200 | 182 |
| symbol + entry 月 | 3 | 3 | 3 | 249 | 196 |
| symbol + entry 年 | 5 | 5 | 5 | 240 | 192 |
| 只比 entry_date（不比 symbol） | 46 | 45 | 37 | 194 | 148 |
| symbol + exit_date | 3 | 3 | 3 | 249 | 196 |
| symbol + entry_signal_date | 3 | 3 | 3 | 249 | 196 |
| symbol + 持仓区间有交集 | 3 | 3 | 3 对 | 249 | 196 |
| symbol + entry_date ±1 交易日 | 3 | 3 | 3 | 249 | 196（±1 日错位命中为 0 笔） |

- 只比 symbol 也只重合 10 个代码（研究 15 行 / 生产 10 行），离 53 差得远；只比日期重合 37 个交易日，也不是 53。`±1 交易日` 松弛给出 0 笔，说明 3 笔重合是精确同日，不存在"差一天"造成的假不重合。
- 因此：若开发经理报告中的"两管道差集 53 笔"是当作可枚举的成交清单使用，口径需要改为"净笔数差 53 = 252−199"；真正的差集是**仅研究侧 249 笔 + 仅生产侧 196 笔（差额 53）**。
- 附注（巧合，不作解释）：研究侧 `exit_reason=max_hold` 的成交恰好也是 53 笔（`results/trade_shape.json`），与本问题无关。

**无法还原的部分**：开发经理那份报告的原始算法我没有拿到，只能证明"按任何一把常见键都不是 53、而净笔数差恰好是 53"。若他那侧用的是另一套交易清单或其中一份带滑点/情景差异的运行结果，需要他给出文件名才能核对。→ 记为「无法完全还原原始算法，但 53 的最省解释是净笔数差」。

---

## 5. 已确证 / 未确证

### 已确证（5 条）

1. 成交 252 vs 199；`(symbol, entry_date)` 重合 3 笔；这 3 笔的 entry_price、exit_date、exit_price、exit_reason、duration 逐笔 0 差异（`results/common_check.json`、`common_3_detail.json`）。
2. 3 笔重合的 pnl 差可由**过户费率差**逐元解释：研究 1e-5 vs 生产 2e-6，Δ8e-6×双边成交额 → 预测 2.76/2.21 元，实差 2.77/2.20 元，残差 ≤0.01 元；**不是佣金档位差**（两侧佣金均 3bp、最低 5 元、印花税均 10bp）；第 3 笔 9,862.46 元由份额 7,800 vs 5,400 决定（`results/common_3_fee_check.json`）。
3. 研究侧数字可精确复现：C0 重跑 = 252 笔 / −32.0929% / cagr −5.3377%，交易键集与 `run_S01_ma_cross_20_60_10.json` 完全相同（对称差 0）（`results/counterfactual.json`、`C0_trades.parquet`）。
4. 只换股票池不能消除差异：C1（生产池 + 研究引擎）−21.9304%，与生产 +24.27% 仍差 46.20pp；C1 与生产逐笔只重合 2/199（Jaccard 0.0043）（`results/counterfactual.json`）。
5. 两侧都受 5 格容量约束且排序规则不同：生产 `buy_no_slot=78,422`、研究 `buy_no_slot=22,138`；生产 `order_by="score"` 降序（`s01b_a0.py:46-47`），研究侧矩阵不含 score（`common.py:361-364`），实测研究侧 `entry_score` 全 0.0、生产 70 个不同值（`results/trade_shape.json`）。

### 未确证（5 条）

1. 46.20pp 残余的**内部分解**未做：未在"研究引擎 + 生产池 + 生产 score 排序"下重跑，故不能给出"排序 X pp、容量交互 Y pp"的拆分。
2. 开盘涨停拦截：研究 189 次、生产 550 次（`registry.json` execution / `a0_10bp/result.json` execution），两侧都存在，但**未逐笔对账是否拦下同一批候选**，其对差集的贡献未测。
3. `exclude_new_days=30`（生产 `basic_filter` 有，研究 `UNIVERSE` 无）对新股段的排除幅度与对差集的贡献**未测**。
4. 复权价基：3 笔重合上 entry_price 逐笔相同 → 撮合价基未见差异；但全样本未逐笔比对 adjusted/raw（两侧池阈值分别用 raw_close≥3 与后复权 close≥2，属池口径差异，不是已测的撮合差异）。
5. 计数口径：生产 199 笔含 5 笔 `exit_reason="end"`（期末强平），研究侧 `open_at_end=0`、5 个未平仓位不计入成交（`final_positions=5`）；这 5 笔对生产 +24.27% 的单独影响**未测算**。

---

## 6. 一句话结论（供 S01b 裁定引用）

**两侧不可比，必须各自声明管道；而且任一侧都不能代表"MA20/MA60 金叉入场"这条规则本身 —— 在 5 格满仓下，结果由选中的那 5 个格子决定，股票池只解释约 10pp，剩余 46pp 来自排序规则。**

> **2026-11-08 18:2x 撤回**：上句「剩余 46pp 来自排序规则」作废（`docs/research/caliber-decisions-20261107.md` §17.2 / §17.3）。正确读法：S01 有三个互不可比的口径族 —— 研究 harness −32.09%（252 笔）、生产文件现状（= 界面点回测的真实默认）−51.47%（208 笔）、生产路径 + 注入五项执行默认 +24.27%（199 笔）；差别首先是**文件有没有声明口径**，不是策略好坏。本目录 §5「未确证」第 1 条（46.20pp 内部分解未做）仍然成立，且优先级上升。

具体到裁定：

- 不能拿生产 +24.27%（gross 年化 +4.21%）当作"该入场规则有效"的证据：它的正收益由 19 笔 >50% 的赢家（合计 +2,106,739.57）撑起，其余 180 笔合计 −1,779,881.36，且换成研究引擎的排序后只剩 −21.93%。
- 也不能拿研究 −32.09% 当作"该入场规则被否决"的证据：它的负收益同样由 8 笔 >50% 的赢家（+721,159.76）之外的全部交易贡献，换池即改到 −21.93%。
- 要判定这个入场规则，规格上必须先冻结**排序规则 + 池口径 + 容量**三件套，再谈收益；否则两侧数字都只是"规则 × 排序"的联合结果。

---

## 附：本目录文件清单

| 文件 | 来源 |
|---|---|
| `gap_attribution.py` | 上一轮（被打断前）产出，本轮未改 |
| `counterfactual.py` | 上一轮产出；本轮**修复 C1 分支缺列**（新增 `add_cross_section`），并重跑 |
| `inspect_common.py` / `key_variants.py` / `ro_breakdown.py` / `trade_shape.py` / `tails.py` | 本轮新增，只读，仅写 `results/` |
| `results/gap_sets.json`、`common_check.json`、`facts_diff.parquet`、`research_only_classified.parquet`、`prod_only_classified.parquet` | 上一轮产出（17:31） |
| `results/common_3_detail.json`、`common_3_fee_check.json`、`key_variants.json`、`gap_profiles.json`、`gap_profiles2.json`、`trade_shape.json`、`tails.json` | 本轮新增 |
| `results/counterfactual.json`、`C0_trades.parquet`、`C1_trades.parquet`、`counterfactual_run.log`（首轮失败）、`counterfactual_run2.log`（成功，149.8s） | 本轮新增 |
