# 因子缺口规格 v1.4（2026-11-07；v1.3 于 2026-11-08 00:40 追加 §9 准入载体缺口；v1.4 于 2026-11-08 01:10 把 §9 G4 升为裁定并订正 G5 的常量处数，§0–§8 一字未改）

状态：**规格草案；按项分别 —— E2 已定：接口与验收判据由契约 v0.3 §3 冻结（2026-11-07 15:51），判据 `XS-A1`–`XS-A8`（策略可用 id `xs_rank_pool`；`xs_rank_pct` 仅诊断，`xs_rank_market` 为现网 `rank` 别名），此处「已定」指接口与判据已冻结，不代表已实现或已验收；其余各项（D1–D3、F1–F7、E1、E3、E4、X1–X2、G1–G3）仍待总体规划负责人排期、系统架构师定接口**。作者：因子工程师。
本文件只做四件事：给需求、定口径、写验收判据、估量级与影响面。**不含实现代码，不含收益数字**。
依据的实测数据：`docs/research/factor-audit-20261107/compare_stats.json`、`xs_rank_stats.json`、`factors_inventory.csv`（复算命令见 §7）。
**修订记录**：v1.1（2026-11-07）——§3-E2 的验收判据改为契约 v0.3 §3.4.1 `XS-A1`–`XS-A8`，研究侧选股数与 `jaccard` 降级为 `xs_rank_pct` 诊断值（见该节「删除记录」与「实测锚」）；§0 表 E2 行改用正式 id；其余各节未动。**v1.2（2026-11-07 17:09）**——§3-E2 补两条：① 旧集合 = 「全样本名次 ≤ `t×P`」与池子的**交集**，不是「池内最低 `t`」的更严格子集；② 因此调阈值只改计数、不改排序依据（证据 `research/strategy-search-20261107/results/e2_caliber_check_20261107.json`）；表头与导语统一改称「旧口径诊断参照」。§4-X2 与 §0 表 X2 行改为「扩展包已实现、生产默认路径未启用」，撤销「建议关闭」的指向。**（17:12 补）** §4-X2 增「加载方式」「实机证据」两条并更正原「`data/user_data/extensions` 不存在」——数据根为 `D:\TSP\data`，其下 `user_data/extensions/paper_execution/runner.sqlite` 存在但 0 字节；§0 表 X2 行补「随默认应用启动自动挂载 `main.py:838`」。**（17:26 补）** §4-X2 与 §3-E2 的契约引用补版本/行号对照——X2：`:40`/`:1209` 是**活文件 v0.4** 的行号（v0.5 为 `:41`/`:1279`、v0.6 为 `:42`/`:1433`）；`XS-A1`–`XS-A8`：§3.4.1（v0.4 `:328`、v0.6 `:330`）。跨版本引用必须写版本，否则下一个读者按 v0.6 查会落空。其余各节未动。

---

## 0. 一张总表

级别：**P0** = 不解决则对应策略无法在系统里表达；**P1** = 能表达但数值不保真；**P2** = 台账治理。

| GAP | 名称 | 级别 | 阻断/影响策略 | 实现路径 | 量级 |
| --- | --- | --- | --- | --- | --- |
| D1 | `high_60d` / `low_60d` 口径冲突（含当日 + 收盘价）与「此前」语义 | P0 | S02、S09 | 新增因子 + 决策记录，**不改既有因子语义** | S |
| D2 | `rsi_14` 涨跌幅口径（`close.diff()` vs `pct_change`） | P1 | S04 | 新增 `rsi_14_pct` 并迁移 | S |
| D3 | 「此前 N 日」语义族命名与定义统一 | P1 | S02、S09 | 注册规范（无代码） | S |
| F1 | `vol60`（60 日收益标准差，日频未年化） | P0 | S07、S11、S12 | 表达式因子注册 | S |
| F2 | `ma120` | P0 | S03、S08 | 表达式因子注册 | S |
| F3 | `ma200` | P1 | 暂无（S03/S08 只用 120） | 表达式因子注册 | S |
| F4 | `prior_high_20` / `prior_high_55` / `prior_high_250` | P0 | S02、S08、S09 | 表达式因子注册 | S |
| F5 | `prior_low_10` | P0 | S02 出场 | 表达式因子注册 | S |
| F6 | `prior_vol_20` | P0 | S09 | 表达式因子注册 | S |
| F7 | `prior_amount_20`（此前口径的 20 日均额） | P1 | 股票池门槛 | 表达式因子注册 | S |
| E1 | `market_breadth`（全市场宽度，掩码口径） | P0 | S12 | 引擎新增截面聚合能力 | M |
| E2 | 掩码截面排名 `xs_rank_pool`（唯一策略可用；`xs_rank_market` / `xs_rank_pct` 仅诊断） | P0 | S06、S07、S10、S11、S12 | 引擎 rank 支持掩码 + 股票池因子 | M |
| E3 | 股票池掩码因子 `in_universe` | P0 | 全部 12 条 | 引擎/因子层新增（ST、bar 数、价格、流动性） | M |
| E4 | 调仓日因子 `month_end` / `week_end` | P0 | S03、S06、S07、S08、S10、S11、S12 | 引擎提供日历列 / 因子化 | S–M |
| X1 | 组合级调仓执行器（生产侧：调仓日 + 截面选股 + 排序 + 容量） | P0 | S06/S07/S08/S10/S11/S12 | 新执行器模块 | L |
| X2 | 生产侧持有期上限（`max_hold_days`）— **扩展包已实现、生产默认路径未启用** | P1 | 12 条（全部；`COMMON:284-308` 逐条带 `max_hold_days`） | 核心默认路径接入（扩展路径已存在、**随默认应用启动自动挂载** `main.py:838`、有条件生效；**不并入「已有能力」**） | S–M |
| G1 | 18 个因子 `warmup_bars` 声明低于实需 | P2 | 全部（早期信号失真） | 注册表元数据修订 | S |
| G2 | 台账范围：85 个 `ext_*` 扩展数据因子未审计 | P2 | 引用 `ext_*` 的策略 | 台账补全 | M |
| G3 | 多重检验计数 N 跨批次累加 | P2 | DSR/去偏 | 数据落库 | S |

量级口径：**S** = 单个表达式因子/元数据级，1 人日内可含证据完成；**M** = 触及引擎算子或数据层，需接口契约 + 独立审核；**L** = 新模块 + 与现有模拟盘/监控集成 + 对账。

---

## 1. 口径决策项（需要拍板，不是纯开发）

### D1 `high_60d` / `low_60d` 与「此前 N 日」语义冲突 — P0

**需求**：12 条策略里有 4 处用「此前高点/低点」（`prior_high20`、`prior_high55`、`prior_high250`、`prior_low10`），系统的 `high_60d`/`low_60d` 是「收盘价 + 含当日 + 60 窗口」，两者**语义不同、窗口不同、价基不同**，不能互相替代。

**现状（确证，读码）**：
- `backend/app/indicators/pipeline.py:451-454`：`high_60d = close.rolling_max(60)`、`low_60d = close.rolling_min(60)`（收盘价、含当日）。
- `backend/app/backtest/matrix.py:4363-4366`：矩阵路径同样用 `valid_rolling_max(market.close, …, 60)` —— 两条路径口径**一致**，不存在分叉。
- 现有种子策略 `app/strategy/seeds/breakout_new_high_60d.py:65` 自己在策略层 `shift(high_60d, 1)` 补偿，说明「含当日」语义已是既成事实并被绕过。

**两套口径的实测差异（同一份数据，n=5,470,011）**：

| 对比 | corr | 平均绝对差 | 突破判定一致率（jaccard） | 仅研究侧成立 | 仅系统侧成立 |
| --- | --- | --- | --- | --- | --- |
| `prior_high55` vs `high_60d` | 0.999642 | 0.423 元 | **0.000** | 143,747 行 | 0 行 |
| `prior_high55` vs `prior_high60`（收盘价 + shift1 + 60） | 0.999609 | 0.436 元 | 0.504 | 3,893 行 | 130,975 行 |
| `prior_high55` vs `prior_high60`（**最高价** + shift1 + 60） | 0.999714 | 0.130 元 | — | — | — |
| `close < low_60d` 触发率 | — | — | 0.000% | — | — |
| `close < prior_low10` 触发率（研究） | — | — | 8.853% | — | — |

结论：`close > high_60d` 结构上几乎不可能成立（当日收盘不可能高于含当日收盘的最大值），**S09 入场条件用 `high_60d` 会整体失效**；`low_60d` 同理会杀死 S02 的出场。窗口 55 vs 60 只差 0.130 元（最高价口径），**真正的分歧来自「含当日」和「收盘价 vs 最高价」，不是窗口长度**。

**口径决定（本文件主张，需架构师确认后生效）**：
1. **权威口径 = `highest(high, N).shift(1)`**（最高价、不含当日、此前 N 根 bar）。理由：突破类信号的经济含义是「价格超过此前区间上沿」，用收盘价最大值的当日值会自我吞掉突破。
2. **不修改 `high_60d`/`low_60d`**：已被 `app/strategy/seeds/breakout_new_high_60d.py`、`trend_breakout.py`、`signal_seeds.py`、`monitor.py`、`custom_signals.py`、`app/api/watchlist.py`、`app/services/market_overview_builder.py` 引用，改语义属破坏性变更。
3. **新增独立因子**（见 F4/F5），命名带 `prior_` 前缀，`price_basis=前复权最高/最低`，`shift=1`，在台账里显式标注「与 `high_60d` 的区别」。
4. 变更影响记录：新增因子使既有种子策略的 `shift(1)` 补偿变成冗余（不产生错误，只是重复），**无需回改**；若未来要统一，须走 G2 台账与版本号递增。

**验收标准**：
- 新增因子在 2019-07-01~2026-10-30 上与研究侧 `prior_high55` **逐位相同**（`max_abs_diff = 0`，n=5,470,011）；
- `close > prior_high55` 判定与研究侧 jaccard = 1.000；
- 台账里 `high_60d` 与 `prior_high_*` 两条记录互相引用差异说明；
- 复算命令见 §7。

**影响面**：S02（入场 + 出场）、S09（入场）；种子策略 2 条；监控规则引用的 `high_60d` 语义不变。
**量级**：S（3 个新因子 + 1 条决策记录）。

### D2 `rsi_14` 涨跌幅口径 — P1

**需求**：研究侧 `rsi14` 用 `ret1 = close.pct_change()` 的涨跌幅；系统 `rsi_14` 用 `close.diff()` 的绝对价差。两者都用 `ewm(alpha=1/14, adjust=False)`，**算法同族但输入不同**，且系统在「平均跌幅=0」处用 `1e-12` 护栏（`pipeline.py:568-579`）。

**实测差异（n=5,509,321）**：corr 0.998312 / spearman 0.998772；平均绝对差 **0.892 个 RSI 点**，p95 1.967；均值 50.19（研究） vs 49.34（系统）。
**阈值判定分歧**：`RSI<30` jaccard 0.948（仅研究成立 2,162 行、仅系统成立 9,768 行）；`RSI>55` jaccard **0.898**（仅研究成立 190,170 行、仅系统成立 0 行）。

**口径决定**：以**涨跌幅（pct_change）**为权威口径（跨标的可比、与「相对强弱」定义一致）。**不改 `rsi_14`**，新增 `rsi_14_pct` 并在 S04 迁移；`rsi_6`/`rsi_24` 同族问题一并登记（本次未实测）。
**验收标准**：`rsi_14_pct` 与研究 `rsi14` 逐位相同（`max_abs_diff < 1e-10`）；`RSI<30` 判定 jaccard ≥ 0.999。
**影响面**：S04；`rsi_14` 既有引用方（`rsi_14_delta_5d`、scoring、监控）不受影响。
**量级**：S。

### D3 「此前 N 日」语义族命名规范 — P1

**需求**：本次缺口里 7 个因子都是「shift(1) + 窗口 + 特定价基」，历史上被临时命名成 `high_60d`/`low_60d`/`vol_ma10`/`amount_mean_20d`，读者无法从名字判断是否含当日。

**规范（主张）**：
- 含当日：`xxx_Nd`（现状保留）；
- 不含当日（此前）：`prior_xxx_N`，台账 `shift` 字段必须为 `shift(1)`；
- 窗口数值与 `warmup_bars` 必须满足 `warmup_bars ≥ N+1`（此前语义自带 1 根位移）。

**验收标准**：注册表内所有 `prior_*` 因子 `shift` 字段非空且 `warmup_bars ≥ N+1`；`build_inventory.py` 复跑后自检 0 违例。
**量级**：S（规范 + 自检脚本）。

---

## 2. 因子缺口（可用现有 DSL 注册，无需改引擎）

这 9 项都能用 `app/factors/dsl.py` 现成算子表达，编译已实测通过（`compile_formula` 返回 `ok=True`）：

| 目标因子 | DSL 表达式 | 编译 warmup | 与研究口径关系 |
| --- | --- | --- | --- |
| `vol60` | `ts_std(change_pct, 60)` | 61 | 等价（`change_pct` ≡ `ret1`，实测平均绝对差 0） |
| `ma120` | `ts_mean(close, 120)` | 121 | 等价（`ma20`/`ma60` 已证 0 差） |
| `ma200` | `ts_mean(close, 200)` | 201 | 同上 |
| `prior_high_20` | `ts_delay(ts_max(high, 20), 1)` | 21 | 逐位等价（待注册后验证） |
| `prior_high_55` | `ts_delay(ts_max(high, 55), 1)` | 56 | 逐位等价（待验证） |
| `prior_high_250` | `ts_delay(ts_max(high, 250), 1)` | 251 | 逐位等价（待验证） |
| `prior_low_10` | `ts_delay(ts_min(low, 10), 1)` | 11 | 逐位等价（待验证） |
| `prior_vol_20` | `ts_delay(ts_mean(volume, 20), 1)` | 21 | 逐位等价（待验证） |
| `prior_amount_20` | `ts_delay(ts_mean(amount, 20), 1)` | 21 | 研究用「元」，系统 `amount` 量纲需确认（见 F7） |

### F1 `vol60` — P0

- **需求**：S07/S11/S12 的低波动选股核心量；系统现有 `annual_vol_20d`（20 日、年化）**不可替代**。
- **口径定义**：`std(close.pct_change(), ddof=1, 窗口=60, 交易日)`，**日频、不年化**、含当日（当日收盘可知）。权威口径 = 研究侧 `add_indicators`（`common.py:140`）。
- **数值证据**：`vol60` vs `annual_vol_20d` corr 0.777 / spearman 0.789，平均绝对差 0.372；即使把 `vol60` 年化后再比，平均绝对差仍有 **0.092（9.2 个百分点）**，p95 0.247；低波十分位选股集合 jaccard 仅 **0.136**。→ 用 `annual_vol_20d` 替代时：研究侧选出的 55.5 只里约 43.5 只仍被命中（21.6% 被换成别的标的），但系统口径会选出 308.7 只（**5.6 倍**），等于把「最低 10% 低波」放宽成「最低 55%」。
- **量级参考**：研究口径分位 p10 1.41% / p50 2.47% / p90 3.98%（日频）。
- **验收标准**：注册后与研究 `vol60` 逐位相同（`max_abs_diff = 0`，n=5,469,335）；`warmup_bars ≥ 61`；单因子证据（IC/IR、逐年 IC、分层净值、多空、换手）由 `backend/app/backtest/factor.py` 产出并落 `custom/strategy_research`。
- **影响面**：S07、S11、S12（3 条）；未来低波因子族复用。
- **量级**：S。

### F2 `ma120` / F3 `ma200` — P0 / P1

- **需求**：S03、S08 的长期趋势过滤（`close > ma120`）；`ma200` 目前无策略使用，但「120/200 日均线」是文档与用户口头常引用的口径，缺失会被临时手算绕过。
- **口径定义**：`close.rolling_mean(N)`，前复权、含当日、N 交易日、`min_samples=N`（不足即 null，不填充）。
- **验收标准**：与研究 `ma120`/`ma200` 逐位相同；`warmup_bars ≥ N`；`ma120` 站上占比应复现 46.8%（研究实证值，用作交叉检查）。
- **影响面**：S03、S08（ma120）；`ma200` 无阻断。
- **量级**：S。

### F4 `prior_high_20/55/250`、F5 `prior_low_10`、F6 `prior_vol_20` — P0

- **需求**：见 D1。S02 需要 20 日此前高点 + 10 日此前低点；S09 需要 55 日此前最高价 + 1.5 倍 20 日此前均量；S08 需要 250 日此前最高价。
- **口径定义**：`agg(price, N).shift(1)`，`agg ∈ {max(high), min(low), mean(volume)}`，前复权、**不含当日**。
- **现状替代品的实测不宜性**：
  - `prior_vol_20` 用 `vol_ma10` 替代：corr 0.956、1.5 倍量条件 jaccard 0.601（仅研究成立 269,878 行 / 仅系统成立 93,177 行）；
  - `vol_ma20` 不存在（系统只有 `vol_ma5`/`vol_ma10`/`vol_ratio_5d`/`vol_ratio_10d`）。
- **验收标准**：5 个因子逐位相同（`max_abs_diff = 0`）；S09 入场判定 jaccard = 1.000（当前 0.000）；`warmup_bars ≥ N+1`。
- **影响面**：S02、S08、S09；种子策略可去掉自建 `shift(1)` 补偿。
- **量级**：S（5 个表达式因子，1 批）。

### F7 `prior_amount_20` — P1

- **需求**：研究股票池门槛 `prior_amount20 ≥ 1 亿`（此前 20 日均额，元）。
- **现状**：系统有 `amount_mean_20d`（含当日、单位**亿元**，`scoring.py:241-242`）。用 1 亿门槛复算：判定 jaccard 0.977，分歧 1.14%（仅研究成立 31,052 行 / 仅系统成立 31,533 行），均值差 0.083 亿元。
- **口径定义**：`mean(amount, 20).shift(1)`，**单位必须与台账统一**（建议沿用系统「亿元」并在 `unit` 字段写死）。
- **验收标准**：与研究 `prior_amount20/1e8` 逐位相同（相对误差 < 1e-12）；1 亿门槛判定 jaccard ≥ 0.999。
- **影响面**：全部 12 条策略的股票池（与 E3 配套）。
- **量级**：S。

---

## 3. 引擎能力缺口

### E1 `market_breadth`（全市场宽度）— P0

- **需求**：S12 的择时闸门（宽度 < 0.5 当月不建仓）。DSL 只有逐行算子 + 截面 `rank/zscore/winsorize`，**没有「按日期的全市场聚合」算子**，表达式因子无法表达。
- **口径定义**：`share(close > ma60 | 当日可算 ma60 且属于股票池)`，按交易日、**含当日**（当日收盘可知）。权威口径 = 研究 `add_universe`（`common.py:186-191`）。
- **数值证据（掩码 vs 无掩码，1,779 个交易日）**：均值 **0.5407** vs 0.4643；corr 0.942 / spearman 0.931；平均绝对差 0.085，p95 0.203；**19.1% 的交易日会在 0.5 阈值上翻转**；月末通过率 **53.4% vs 34.1%**，月末翻转 23.9%。
- **口径决定**：权威口径**必须带股票池掩码**（否则 S12 的建仓月份从 53% 掉到 34%，且不是随机丢月）；若短期只能上无掩码版本，**必须在台账标注「近似口径」并禁止用于策略判据**。
- **验收标准**：逐日与研究方向量相同（`max_abs_diff < 1e-12`，n_days=1779，均值 0.540742）；月末通过率 53.4%；引擎需给出「聚合类因子」的口径与 warmup 声明（`max(ma60.warmup)=60`）。
- **影响面**：S12；未来所有择时/宽度类因子。`limit_up_count_20d` 等是「单标的滚动计数」，不是全市场宽度，不可替代。
- **量级**：M（引擎新增聚合能力 + 注册 + 单测 + 独立审核）。

### E2 掩码截面排名 `xs_rank_pool`（族内 ret5/ret60/vol60/dist_52w_high；诊断用 `xs_rank_market` / `xs_rank_pct`）— P0

- **需求**：S06/S07/S10/S11/S12 的选股全部依赖「股票池内排名」。系统 `rank(x)` 的实现是 `x.rank("average").over("date") / x.count().over("date")`（`dsl.py:506-508`），分母是全样本非空数、**无掩码**。
- **因子 id 归属**：`xs_rank_ret20` / `xs_rank_vol60`（及同族 ret5/ret60/dist_52w_high）是**族内用法示例，不是因子 id**（v1.0 的标题与 §0 表曾这样写，v1.1 已改）。正式 id 与登记态见契约 v0.3 §3.6：`xs_rank_pool`（唯一 `strategy_usable=true`）/ `xs_rank_market`（诊断，`numeric_alias_of = rank`）/ `xs_rank_pct`（差异证明）。实现不得另立这些示例名，也不得再把 `xs_rank_in_pool` 当独立 id 登记。
- **旧口径诊断参照（不是靶值，也不是「研究侧已正确」的证据）**：下表三列一律称「旧口径诊断参照」，任何一列都**不得**当验收靶值或「正确基准」。研究侧 `rk_*` = 全样本名次 ÷ 池内家数（即契约里的 `xs_rank_pct`，可 >1，`strategy_usable=false`，只作批次 2 的差异证明）；系统 `rank(x)` = 全样本名次 ÷ 全样本非空数（即 `xs_rank_market`，诊断）。两者**都不是策略可用口径**——策略只能引用 `xs_rank_pool`（池内平均名次 ÷ 池内**非空**家数）。本表只承担一件事：说明两种旧口径各自偏到什么程度。

| 选股规则 | 旧口径诊断参照 ①：研究侧 `rk_*` 复现值（= `xs_rank_pct`，`strategy_usable=false`，作废） | 旧口径诊断参照 ②：系统 `rank` 口径平均选股数（= `xs_rank_market`，诊断） | jaccard（诊断） | 分母（① 池内家数 vs ② 全样本非空） |
| --- | --- | --- | --- | --- |
| `rk_ret5 ≤ 0.05`（S06，376 个周末） | 49.7 | 154.3 | **0.319** | 1,429 vs 3,095 |
| `rk_vol60 ≤ 0.10`（S07/S12，88 个月末） | 55.5 | 307.2 | **0.178** | 1,430 vs 3,077 |
| `rk_ret20 ≤ 0.10`（S10，88 个月末） | 92.8 | 308.8 | **0.298** | 1,430 vs 3,092 |
| S11 复合（两项 ≤0.30） | 14.7 | 207.2 | **0.049** | 同上 |

  即：系统口径下 S11 的选股数放大 **14 倍**，S07 放大 5.5 倍。这不是「轻微口径差」，会直接改变策略性质。**但「放大」不等于研究侧口径正确**：两者是两种不同的错口径，差别只在错法不同；正确口径的准入判据是下面的 `XS-A1`–`XS-A8`，不是本表任何数字。

- **旧集合的准确形状（D9 的实质，不许再写成「更严格子集」）**：旧口径选出的集合 = 「**全样本**名次 ≤ `t×P`」与「属于池子」两个条件的**交集**——它既不是「池内名次 ≤ `t×P`」的更严格子集，也不是它的超集，包含关系**未知**。2021-06-30 实测（`P=1,210`，`t×P=121`）：按 `rk_vol60 ≤ 0.10` 当日实际入选 **26 只**，即全样本名次 ≤ 121 的那 121 只里只有 **26 只**落在池内（`e2_caliber_check_20261107.json` → `rows[0].P=1210`、`rows[0].rk_vol60.nominal_count_times_P=121.0`、`rows[0].rk_vol60.count=26`、`rows[0].rk_vol60.ratio=0.02149`；同日全样本非空 3,041 行）。另两抽样日：2024-06-28 `P=1,037` → 名义 103.7 只、实选 56 只；2026-09-30 `P=1,790` → 名义 179 只、实选 90 只（同文件 `rows[1]`/`rows[2]`）。
- **推论（排期相关）**：旧集合由**全样本名次**决定，所以**调阈值只改计数、不改排序依据**——把 `t` 调大只会多纳入「全样本排名靠后、但仍在池内」的标的，不会把集合还原成「池内最低 `t`」。要拿到「池内最低 `t`」只能换口径（`xs_rank_pool`），不能靠调参。
- **口径决定**：`rank` 增加可选掩码参数（或引入「股票池因子」作为布尔列参与），分母 = 掩码内非空样本数；**无需掩码的调用方保持现状**（向后兼容）。
- **验收标准**（验收对象 = `xs_rank_pool`，判据 = 契约 §3.4.1 `XS-A1`–`XS-A8`（15:51 版 v0.3 冻结；活文件 v0.4 `:328`、v0.6 `:330` 同号）；**本项不以任何研究选股数为靶值、不以 jaccard 作为准入条件**）：① `XS-A1` 逐日断言 `max == 1` 且 `min > 0`，**出现任何 `rk > 1` 直接不通过**（一条即可拦住本次事故）；② `XS-A2` 单日 `count(rk ≤ t)` 与参考实现「池内 `rank ≤ t×P`」的真实计数逐日相减，**容差 0**（`t ∈ {0.05, 0.10, 0.30}`，逐日打印 `P` / `count` / `t×P` 三数）；③ `XS-A5` 构造单日「池内 3 只、其中 1 只 `x` 为空」→ `{0.5, 1.0}`（得 `{0.333, 0.667}` 即不通过，= 用了 `in_universe.sum()`）；④ `XS-A8` 4 只同值 → 全部 `0.625`（`ordinal` / `min` / `max` 均不通过）；⑤ `XS-A6` 池空日全 `null`（不是 0，不是 1）；⑥ `XS-A3` **`rank` 无掩码调用的输出与现状逐位相同**（回归保护：93 只台账因子抽 20 只做列 hash 对比）；⑦ `XS-A4` 池内家数逐日与研究一致（日均 1,429、逐日差 0；**依赖 E3**，E3 未通过 → E2 不可验收，`P` 本身不可信）；⑧ `XS-A7` 面板 `pipeline.py` 与矩阵 `matrix.py` 双路径逐位差 ≤ `1e-12`。
- **删除记录（不是判据）：原「`55.5 / 49.7 / 92.8 / 14.7 ± 1`」与「jaccard 0.99」那组判据已从本项验收移出**：它们在契约 §3.4.3 里是 `xs_rank_pct` 的复现判据 `XS-C1`，只证明「复现了研究侧的错口径」——不是策略验收，不是「研究侧已复现」的证据，不得用于任何方向判断。
- **实测锚（`XS-A2` 逐日打印用）**：`P` 逐日不等——已实测 2021-06-30 = **1,210**、2024-06-28 = **1,037**、2026-09-30 = **1,790**（这三个抽样日的均值为 1,345.7；88 个月末的池内家数均值 1,429.74 见契约 §3.4.1 `XS-A4`——两者是不同量，不得互换）；逐日均满足 `max(rk_vol60) × P` = 当日该列全样本非空行数（3,041 = 3,041；3,170 ≈ 3,171；3,182 = 3,182，差 ±1 由 `average` 并列造成）。→ **任何 `t × P` 推算必须用当日 `P`**，不得用均值反推。证据：`research/strategy-search-20261107/results/e2_caliber_check_20261107.json`（`rows[].P`、`rows[].rk_vol60.rk_max_times_P`、`rows[].rk_vol60.nonnull_all_rows`）。
- **影响面**：S06、S07、S10、S11、S12（5 条）；所有未来截面因子。
- **量级**：M（DSL 算子签名 + 编译期 warmup + 单测 + 回归测试）。

### E3 股票池掩码因子 `in_universe` — P0

- **需求**：E1/E2 与所有策略的样本口径都指向同一个东西：研究侧 `in_universe = bar≥120 & 非ST & raw_close≥3 & prior_amount20≥1亿 & volume>0`（`common.py:177-183`）。系统没有这个因子（`st_flag` 只是数据列）。
- **口径定义**：布尔因子，逐日 as-of 可得；ST 用当日 ST 标记；成交额门槛用 `prior_amount_20`（F7）。**不使用未来信息**。
- **实测口径后果**：研究池 1,429 只 vs 全样本 3,095 只（占 46%）。
- **验收标准**：逐日池内家数与研究一致（均值 1,429，允许 ±0 差）；ST 命中的标的 bar 覆盖率 100%（无静默丢弃）；`in_universe` 在台账中登记为 base 因子并声明 warmup=121（受 bar≥120 约束）。
- **影响面**：全部 12 条策略 + E1 + E2。
- **量级**：M（因子层 + 数据层 ST/上市日字段核查）。

### E4 调仓日因子 `month_end` / `week_end` — P0

- **需求**：7 条策略按月末/周末再平衡（S03/S06/S07/S08/S10/S11/S12）。系统无「调仓日」概念；回测侧 `app/backtest/factor.py` 有 `rebalance` 参数（因子分组回测用），但**策略信号层没有日历**。
- **口径定义**：`month_end = 下一交易日所在月份 ≠ 当日月份`；`week_end` 同理按 ISO 周。以**交易日历**为准，不用自然日。
- **验收标准**：区间内 `month_end` 天数 = 88、`week_end` 天数 = 376（与研究实测一致）；与 A 股节假日日历一致（以项目交易日历表为唯一权威）。
- **影响面**：S03、S06、S07、S08、S10、S11、S12。
- **量级**：S–M（若仅作为因子列，S；若进执行器调度，并入 X1）。

---

## 4. 执行器缺口

### X1 组合级调仓执行器（生产侧）— P0

- **需求**：S06/S07/S08/S10/S11/S12 是**组合级**策略：在调仓日做截面排序、取前 N、按 `max_positions` 与仓位约束成交、非调仓日不动。当前生产侧（监控 + 模拟盘）是**单标的信号触发**：`app/strategy/paper_auto.py#on_rule_events` 逐事件下单，`max_positions` 只做「已用槽位」上限，**没有调仓日、没有截面选股、没有排序取前 N**。
- **现状（确证）**：
  - 回测侧**已具备**组合能力：`app/backtest/engine.py#simulate_market_matrix` 支持 `score`/`ranking_score` 排序与 `max_positions` 容量约束（`_matrix_entry_score`、`Candidate` 排序、`position_sizing=equal/score_weight/score_tier`）；
  - 生产侧**没有**对应能力（`paper_auto.py` 无 `rebalance`/`max_hold`/`score` 语义，已 grep 确认）。
- **需求规格**（供架构师定契约）：
  1. 调仓日由 E4 驱动；非调仓日只处理出场（止损/持有期/信号出场）；
  2. 选股集合 = 掩码内排名前 K（E2）+ 策略入场谓词；
  3. 排序键与回测一致（同一 `score` 表达式、同一 rank 口径）；
  4. 容量与仓位复用回测 `MatcherConfig` 语义（`max_positions`、`max_exposure_pct`、等权/打分加权）；
  5. 成交价与回测对齐：`next_open` + 涨跌停不可买 + 费用/滑点参数与回测同一份配置；
  6. 全部决策落审计日志（哪一日、哪个因子值、为什么入选/落选），供复盘工程师对账。
- **验收标准**：
  - 同一策略、同一区间，回测与模拟盘的**逐日持仓集合一致率 ≥ 99%**（差异必须能用成交约束解释并留痕）；
  - 调仓日数量与 E4 一致（如月度策略 88 个）；
  - 单日下单数与 `max_positions` 约束一致，无超限；
  - 影子运行 ≥ 20 个交易日，零人工干预完成调仓。
- **影响面**：6 条组合级策略；`app/strategy/paper*.py`、`monitor*.py`；与复盘对账链路耦合。
- **量级**：L（新模块 + 集成 + 影子运行）。

### X2 生产侧持有期上限 `max_hold_days` — P1（**扩展包已实现、生产默认路径未启用**）

- **需求**：12 条策略**全部**声明「最长 N 个交易日」退出（`COMMON:284-308`，5/10/20/60 日），不是只有 S01–S06。回测引擎支持 `MatcherConfig.max_hold_days`。
- **现状（实测 2026-11-07 17:09）**：**扩展包已实现，未进入核心/默认路径**——实现只在 `backend/app/custom/paper_execution/service.py:404-408`（`hold_days = self._holding_days(...) if snapshot["overrides"]["max_hold_days"] else {}`）与 `:418-421`（`hold_days >= snapshot["overrides"]["max_hold_days"]` → 以 `reason="max_hold"` 强平）；由该扩展的 lifespan 起后台线程（`routes.py:56-58,93-94`，`threading.Thread(name="paper-execution", daemon=True)`）。
- **生效条件（三条同时满足，缺一不生效）**：① 账户状态 `enabled` 为真（`service.py:66,240`，即「已启用的绑定」）；② 该账户快照的 `overrides` 里 `max_hold_days` 非空（`service.py:406,419`）；③ 该扩展包已安装并加载。**回测不走这条路径**（`backend/app/backtest/**` 无 `paper_execution` 引用）。
- **加载方式（2026-11-07 17:12 复核更正）**：该模块**随默认应用启动自动挂载**，不是可选安装——`backend/app/main.py:838` 调 `configure_backend_extensions(app)`，`app/extensions/loader.py:28-49` 遍历 `app/custom/*` 非下划线模块，`app/custom/paper_execution/__init__.py:5,12`（`EXTENSION_ID="official.paper-execution"`、`registrar.include_router(build_router())`），router 带 `lifespan`（`routes.py:111`）→ 线程启动（`routes.py:93-94`）。因此「生产默认路径未启用」的准确含义是：**核心策略执行路径 `app/strategy/paper_auto.py` 没有同一语义，且没有满足条件的绑定账户时该线程空转**——不是「扩展未安装」。
- **实机证据（更正原文「`data/user_data/extensions` 不存在」）**：本机配置的数据根是 **`D:\TSP\data`**（`docs/factors/evidence/registration_b0_20261107.json#data_dir`；仓库内 `data/` 不是数据根）。该目录下 `user_data/extensions/paper_execution/runner.sqlite` **存在，但为 0 字节**，旁有 512 B 的 `runner.sqlite-journal`（mtime 2026-11-06 12:15）→ 只能证明状态库被创建过，**读不出任何绑定/持仓数据**，故「是否存在已启用且带 `max_hold_days` 的绑定」仍未证。
- **仍未验证**：`app/strategy/paper_auto.py` 的持有期逻辑未逐行核对（`paper_auto` 只被扩展调用为「逐事件下单」）；部署环境与该状态库是否一致。
- **因此**：本项**不是「已有能力」**，也**不判「关闭」**。契约 v0.4 `:40`、`:1209`（活修订 v0.6 对应 `:42`、`:1433`；v0.5 `:41`、`:1279`）已明写 X2 不在引擎契约内、另立、P1 —— 本项维持 P1，表述统一为「扩展包已实现（有条件生效）、生产默认路径未启用」。
- **验收标准**：在**生产默认路径**（不依赖该扩展）上，任一持仓的持有天数 ≤ 策略上限 + 1（次日开盘平仓），且超限平仓在审计日志可见；扩展路径若保留，须单独登记其生效条件，并证明与回测 `max_hold_days` 语义一致。
- **影响面**：12 条策略（全部），不是 S01–S06。
- **量级**：S–M（默认路径接入）＋ 扩展路径的部署核验。

---

## 5. 台账治理项

### G1 18 个因子 `warmup_bars` 声明低于实需 — P2

- **证据**：`docs/factors/FACTOR_REGISTRY_CORE_93_20261107.md` §3；如 `momentum_20d` 声明 1、实需 20；`rsi_14` 声明 1（ewm 无固定窗口，权重衰减到 1e-3 需约 95 根 bar）。
- **后果**：「已预热」判定早于数据就绪，早期信号为 null 或短窗口噪声，回测/模拟盘的起始段不可比。
- **验收标准**：18 项全部修订；`build_inventory.py` 复跑后「声明 < 实需」计数为 0；变更写入台账 `version` 递增。
- **量级**：S。

### G2 台账范围：85 个 `ext_*` 未审计 — P2

- **证据**：`all_factors()` 192 个（B0 后；14:17 时点为 178），本台账覆盖 93 个（= 192 − 85 扩展数据因子 − 14 批 A 新注册）。
- **要求**：任一策略引用 `ext_*` 因子前，必须在台账登记口径与数据源，并附单因子证据；否则按「无证据因子」拒绝进入策略。
- **量级**：M（按需逐批，不是一次性）。

### G3 多重检验计数 N 跨批次累加 — P2

- **要求**：DSR/去偏依赖全局试验次数 N；N 必须机器可读、跨批次累加，不能只在单批次内累加（现状：研究批次各自计数）。
- **验收标准**：存在单一计数文件/表，任何一次因子试算或策略试算都追加一条记录（批次号、时间、试验类型、N 增量）；DSR 计算读取该值而非硬编码。
- **量级**：S。

---

## 6. 建议的推进顺序（依赖关系）

```text
D1/D3 口径拍板 ──┬─> F4/F5/F6（此前语义族） ┐
D2 rsi 口径    ──┼─> F1/F2/F3/F7            ├─> 一批注册（可并行）─> 单因子证据 ─> 策略规格冻结
E3 in_universe ──┴─> E2 掩码 rank ──────────┘
                        └─> E1 market_breadth（同属「聚合/截面」能力，建议同一契约）
E4 调仓日 ──> X1 组合级执行器 ──> 影子运行 20 日 ──> 上线评审
```

理由：F 类（9 项，表达式因子）不依赖任何引擎改动，是**唯一能在不动引擎的前提下把 S02/S03/S04/S08/S09 推成「可表达」**的一步（S07 仍依赖 E2 的掩码排名，S06/S10/S11/S12 仍依赖 E2/E3）；E 类需要契约，宜与 X1 并行设计（都涉及「掩码 + 截面 + 调仓」语义），避免两轮改引擎。

---

## 7. 复现

```bash
cd C:\work\sourcecode\tick-stock-panel\backend
.\.venv\Scripts\python.exe ..\docs\research\factor-audit-20261107\scripts\build_inventory.py       # 台账 93 项 -> factors_inventory.csv/json
.\.venv\Scripts\python.exe ..\docs\research\factor-audit-20261107\scripts\render_inventory_md.py    # -> docs/factors/FACTOR_REGISTRY_CORE_93_20261107.md
.\.venv\Scripts\python.exe ..\docs\research\factor-audit-20261107\scripts\audit_compare.py          # 口径对照 -> compare_stats.json
.\.venv\Scripts\python.exe ..\docs\research\factor-audit-20261107\scripts\audit_xs_rank.py          # 截面/宽度 -> xs_rank_stats.json
.\.venv\Scripts\python.exe ..\docs\research\factor-audit-20261107\scripts\build_strategy_map.py     # 映射表 -> docs/factors/STRATEGY_INPUT_FACTOR_MAP_20261107.md
```

DSL 表达式可编译性自查（只读，不注册）：

```bash
cd C:\work\sourcecode\tick-stock-panel\backend
.\.venv\Scripts\python.exe -c "from app.factors.dsl import compile_formula as c; [print(f, c(f).ok, c(f).warmup_bars) for f in ['ts_std(change_pct,60)','ts_mean(close,120)','ts_delay(ts_max(high,55),1)','ts_delay(ts_min(low,10),1)','ts_delay(ts_mean(volume,20),1)']]"
```

## 8. 本文件没做的事（边界）

- 没有注册任何因子、没有改任何引擎/信号链/注册表代码、没有提交。
- `ext_*` 85 个扩展数据因子未审计（G2）。
- `vol60`/`ma120`/`prior_*` 的「逐位相同」目前只有同族等价证据（`change_pct` ≡ `ret1`、`ma20`/`ma60` 已实测 0 差）与 DSL 编译通过；**其余必须在注册后按各自验收标准实测**，在此之前不得写成「已证」。
- X1 的接口契约、成本假设与影子运行口径需架构师与复盘工程师共同定，本文件只给判据。

---
## 9. 准入载体缺口（v1.3，2026-11-08 追加；§0–§8 未动）

这三个缺口是本批（F 类 8 只 status 升 `active`）跑闸门时**实测暴露**的，不是推测。判据一律来自 `mode="production"` + `RegistryFacts(data_dir=settings.data_dir)` 的实跑。

### G4 非 `uf_` 前缀的策略引用因子没有 `status` 载体 — P0

- **需求**：让 pack 单侧件 `ma20` / `ma60` / `sd20` / `boll_lower` / `boll_upper` / `prior_amount_20` 能在 `production` 入口被判为可用。
- **口径（为什么现在做不到，实测）**：`status` 只从盘上定义 JSON 读（`backend/app/factors/gate.py#_definition_status`），而盘上定义的 id 必须匹配 `^uf_[a-z0-9_]{1,40}$`（`backend/app/factors/store.py:17`、`to_spec()` :73-85）。这 6 个 id 不带 `uf_` 前缀 → **没有任何合法载体能承载它们的 status**。`FactorSpec` 数据类无 `status` 字段（`backend/app/factors/registry.py:33-68`）。
- **实测**：6 只逐只 `assert_factors_usable([id], mode="production", facts=RegistryFacts(data_dir=D:/TSP/data))` → 全部 **`FS01`**，`detail.status = None`，`message` = 「因子 X 的 status=None 不允许在 production 模式使用」。
- **契约依据**：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md` §7.15.3「登记 P2 ①：为 `FactorSpec` 增 `status`（或为 provider 注册路径显式给 `status`），使 14 只可从 `draft` 走 §7.11 的 V3 闸门升 `active`」——原定「不阻塞 B2、不进本批验收」，本批到期未落地。
- **验收判据**：①6 只在 `mode="production"` 不再出 `FS01`；②每只的 status 可追到证据行（V3 `max_abs_diff` / B0 保真 / 该口径自身的验收判据），禁止批量写 `active`；③schema 增字段不改变既有 110 只的任何数值面（用 V3 对账复跑证 `max_abs_diff` 不变）。
- **量级**：S（字段 + provider 传参 + 单测），但改的是契约 §7.2 的字段表，须走「架构契约 → 开发实现 → 独立审核」。
- **影响面**：策略经理引用这 6 个 id 的策略在 `production` 全部被拒（当前实测：全部 `FS01`）。不解除则「策略只经因子表达」在这些策略上无法落地到可运行。
- **裁定（v5.12 立 P0）**：本缺口升为**裁定**，锁定三条不做：①不补 `status`（无合法载体）；②不建 `uf_*` 双胞胎（§7.15.1 第 14 行；双胞胎会触发 §7.16.6 的 `FS04`）；③**不按 id 开白名单放行**（`EXEMPT_KINDS={base,virtual}` 是黑名单语义、按 `kind` 不按 id）。任何人要求「把这 6 个名字加白名单放行」，**必须先回来改本裁定**并留改判依据与实测，不得在闸门里按 id 开小门 —— 闸门是「策略只经因子表达」的唯一执行点。裁定全文见台账 `docs/factors/F_CLASS_REGISTRATION_20261107.md` §17；机器可读版 `docs/factors/evidence/f_class_registry.json#admission_carrier_rulings.g4_p0_ruling_v5_12`。
- **4 个撞名名字的 400 归因（v5.12 实测，2 命名面 × 6 只）**：`ma20` / `ma60` / `boll_lower` / `boll_upper` 同时在 `_column_universe()`（68 名）内 —— **当因子引用**（`namespace="factor"`，缺省）→ `FS01` → **400**（契约 §7.7.5 / `F-A47`；**不是** `FS03`，这 4 只 `alias_of=None`）；**当列引用**（`namespace="column"`，§7.17.2 / `F-A43-2`）→ **0 码放行**；`sd20` / `prior_amount_20` 不在列宇宙 → column 面是 `FS02`。**今日这 4 个名字在 7 条活信号里是列**（`D:/TSP/data/user_data/custom_signals`：`ma20_breakout` / `ma20_breakdown` / `ma_dead_5_20` / `ma_golden_5_20` / `ma_golden_20_60` / `boll_breakout_upper` / `boll_breakdown_lower`，逐条 `enabled=true`、`kind="both"`）→ 走 column 面，**今天不会被打成 400**；400 只在被当因子引用时出现。实测脚本 `research/factor-ledger-20261108/probe_namespace_v511.py`（输出同名 `.json`）。

### G5 `market_breadth` 没有登记载体（不是「没实现」）— P0

- **需求**：让 `market_breadth` 成为可被策略引用的已登记因子（策略经理已裁定：**单侧、不建 `uf_market_breadth` 双胞胎**，理由同 `prior_amount_20`）。
- **计算面已完成，登记面为零（实测）**：
  - 计算：`docs/factors/B2_IMPLEMENTATION_20261107.md` §4 全部 PASS —— 1,770 个交易日两侧均非 null、`max_abs_diff=0.0`、`mean_abs_diff=0.0`、超 1e-12 天数 0；9 个 null 日 = `st_unknown_window` 8 天（2026-10-20…10-29）+ `beyond_coverage` 1 天（2026-10-30）；`warmup=120`。
  - 登记：`grep -rn "market_breadth" backend/app --include=*.py` → **0 命中**；`all_factors()` 无此 id；闸门判 **`FS02`（未登记）**。
- **两条载体路都不通（实测）**：①store 盘上 JSON —— id 正则 `^uf_` 拒绝，`store.to_spec({"id":"market_breadth",…})` 抛 `ValueError: id 必须匹配 ^uf_[a-z0-9_]{1,40}$`；②目录计数 —— `all_factors()` = `_CATALOG`(77) + provider(33) = **110**（`backend/tests/test_factor_registry.py:289` 快照，实测 1 passed），要 110→111 必须新增一个 `FactorSpec`，即 `backend/app/**` 代码。
- **验收判据**：①`get_factor("market_breadth")` 非空；②`assert_factors_usable(["market_breadth"], mode="production")` 0 码；③目录计数 110→111，且 `test_catalog_counts_and_kinds` / `test_factor_store.py` 的 110 快照同步更新（否则测试红）；④若还要 `compile_formula("market_breadth")` 也通过 —— **不需要额外的层，登记即通过**（v5.10 更正：本行原写「须额外打通『已注册因子 id → DSL 标识符』，现盘上这一层本来就不成立」，并把 `compile_formula("uf_vol60")` 的 `E001` 当对照；那是**没走启动期装载的裸进程**里的假象）。实测同一 venv：裸进程 `compile_formula("uf_vol60")` → `ok=False / E001`（`get_factor` 为 None）；`store.load_all(data_dir)` + `register_factor(store.to_spec(d))` 之后同一表达式 → `ok=True / warmup_bars=61`。读代码一致：`backend/app/factors/dsl.py:676/690` 先查 `BASE_COLUMNS` 再 `get_factor(name)`，启动期由 `backend/app/main.py:217-221` / `backend/backtest/worker.py:234-236` 的 `load_into_registry` 装载。故验收只按 ①–③；另附一条可编译性事实：它的口径表达式今天就能编 —— `compile_formula("xs_mean(close > ma60, in_universe)")` → `ok=True`、`warmup_bars=120`，与 E1 声明的 120 一致。
- **量级**：M（新增 provider/`FactorSpec` + 目录快照同步 + 可选 DSL 标识符解析 + 独立审核）。
- **影响面**：所有引用 `market_breadth` 的策略（S12 择时闸门：宽度 < 0.5 当月不建仓）在 `production` 一律被拒。

**实现门票（v5.11 追加，2026-11-08 00:58）**：登记字段值已由策略经理裁定并逐项冻结在台账 `docs/factors/F_CLASS_REGISTRATION_20261107.md` §16.4（`id` / `formula_text` / `semantics` / `cross_sectional` / `warmup_bars=120` / `dependencies={close,ma60,in_universe}` / `strategy_usable=true` / 「禁止再套截面算子」），**验收判据见 §16.5（5 条，可机械判定）**，连带风险见 §16.6（`semantics`/`cross_sectional` 无消费者 → 允许两步走，但登记行必须写明该约束尚未被执行）。开发侧照 §16.4 实现即可，不需要再回头问口径。

- **状态（v5.12）**：**已派、未交付**。开发经理已于 2026-11-08 01:10 派系统开发工程师；写作时实测 `grep -rn "market_breadth" backend/app --include=*.py` 仍 **0 命中**、`all_factors()` 仍 110。登记参数（`§16.4` 门票）一字未改，只改状态写法。

**实现时必须同步改的 4 处（v5.12 订正：v1.3 写「两行」会留 2 条红）**：`backend/tests/test_factor_registry.py:289` `assert len(specs) == 110` → `111`；`backend/tests/test_factor_registry.py:290` `assert len({spec.id for spec in specs}) == 110  # id 唯一` → `111`；`backend/tests/test_factor_registry.py:329` `assert len(stock) == 110` → `111`；`backend/tests/test_factor_registry.py:377` `assert len(factors) == 110` → `111`（`grep -n "110"` 恰 4 命中，文件 403 行）。若走 provider 路线，`factor_provider_status()["factor_count"]` 会 33 → 34，须全量跑 `tests/` 确认没有以 33 为常量的断言。

### G6 `FactorSpec` 无 `semantics` / `cross_sectional` 字段 — P2

- **需求**：把「按日聚合、按标的广播」这类语义写进因子元数据，并让闸门/物化/回测真的读它；尤其是 `market_breadth` 必须随身携带「**禁止对其再做任何截面算子或排名**」这条约束（否则等于 3,000 倍重复计数）。
- **事实**：`backend/app/factors/registry.py:33-68` 的 `FactorSpec` 字段表共 23 项（含本批新用的 `alias_of` / `strategy_usable`），**没有** `semantics`、**没有** `cross_sectional`。批次要求「`semantics = market_aggregate_daily`、`cross_sectional = true`」在当前 schema **无处可写**。
- **口径**：本批**拒绝**两种假落地——①把这两个键写进盘上 JSON 但没有读者（store 的 `to_spec()` 不消费，等于装饰）；②用 `kind` 或 `group` 字符串冒充语义（不可被机械判定）。
- **验收判据**：①两个字段进契约 §7.2 字段表并有明确消费者（闸门对 `cross_sectional=true` 的因子在「再套截面算子」时 fail-closed）；②缺省值不改变既有 110 只任何行为（全量测试 + V3 复跑证）。
- **量级**：M（契约 + 消费方 + 单测）。
- **备注**：与 G5 同批做最省，但 G5 不依赖 G6（先登记后补语义是可行的两步）。

### 9.4 本节的边界

- 本节只给**需求 / 口径 / 验收判据 / 量级 / 影响面**，不含实现方案，也不含任何代码改动。
- 未在本文写「近似因子」替代方案：G4 的 6 只与 G5 的 `market_breadth` 都不能用别的已注册因子近似表达（`ma20`/`ma60`/`sd20` 是均价/标准差本身，`market_breadth` 是全市场聚合，`limit_up_count_20d` 之类的单标的滚动计数不可替代，见 §3 E1）。
