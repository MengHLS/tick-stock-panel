# 数据边界审计：四类阻塞 + 「616 只无因子」口径定论

| 项 | 值 |
|---|---|
| 生成时间 | 2026-11-07 00:45:53 +0800（中国时间） |
| 代码库 | `C:\work\sourcecode\tick-stock-panel`，分支 `dev`，HEAD `848bd04b`（本次只新增 `research/data-gaps-20261107/`，未改动任何既有文件） |
| 数据根 | `D:\TSP\data` |
| 审计脚本 | `research/data-gaps-20261107/scripts/audit_data_gaps.py`（只读；只写本目录 `results/`） |
| 汇总脚本 | `research/data-gaps-20261107/scripts/build_summary.py` |
| 独立复核脚本 | `research/data-gaps-20261107/scripts/independent_recheck.py`（不复用上面脚本的任何代码路径，第二条独立 DuckDB 会话重算列出的14项数字及若干补充事实） |
| 机器可读结论 | `research/data-gaps-20261107/results/summary.json` |
| 独立复核证据 | `research/data-gaps-20261107/results/independent_recheck.json`（`all_match=true`，`diffs={}`） |
| 逐项原始证据 | `research/data-gaps-20261107/results/check_{industry,index,etf,short,universe616}.json` |

按顺序复现全部：

```bash
cd C:/work/sourcecode/tick-stock-panel
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/data-gaps-20261107/scripts/verify_delivery.py industry
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/data-gaps-20261107/scripts/verify_delivery.py index
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/data-gaps-20261107/scripts/verify_delivery.py etf
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/data-gaps-20261107/scripts/verify_delivery.py short
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/data-gaps-20261107/scripts/verify_delivery.py universe616
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/data-gaps-20261107/scripts/verify_delivery.py independent_recheck
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/data-gaps-20261107/scripts/verify_delivery.py build_summary
```

以上七阶段本轮实际退出码均为 0。`results/execution_log.json` 记录每次子进程的参数、退出码、耗时和日志路径，汇总脚本读取实际记录，不预设成功。`results/run_*.log` 保留关键输出。独立复核覆盖 14 个列出的数字，做空执行路径结论来自主审计的静态代码证据。


**退出码口径（重要）**：脚本的 `0` 只表示「审计命令跑通、JSON 已写出」，不表示数据可用。数据结论看 JSON 里的 `status` / `verdict`。

---

## 0. 结论一览

| # | 策略族 | 判定 | status | verdict | 一句话依据 | 证据文件 |
|---|---|---|---|---|---|---|
| 1 | 行业中性 / 行业轮动 | **不可做**（历史） | blocked | 确证 | 行业归属只有 2026-11-01~06 六个时点快照，落在面板 2,141 个交易日里的 **5 天（0.23%）**；其余来源全部前视或无日期维度 | `results/check_industry.json` |
| 2 | 指数增强 / 成分轮动 | **不可做** | blocked | 确证 | 599 个指数**只有价格**，本地零成分、零权重；概念快照里 `沪深300/中证500/中证1000/上证50` 标签证券数均为 0 | `results/check_index.json` |
| 3 | ETF 全族 | **不可做** | blocked | 确证 | `kline_etf_daily` / `_enriched` / `_minute` 均 **0 文件 0 字节**；股票面板与全量分钟线里 **0 只 ETF** | `results/check_etf.json` |
| 4 | 做空 / 对冲 / 市场中性 | **不可做** | blocked | 确证 | 撮合器只有 `buy`/`sell`、无 `allow_short`；仓位非负；无两融/券源/保证金任何表 | `results/check_short.json` |
| 5 | 「616 只无因子」争议 | **可精确复现，语义需改写** | available | 确证 | 616 = 面板 5,813 只中在 `adj_factor`（复权因子**事件**表）里没有任何一行的证券数；不是「没有因子数据」 | `results/check_universe616.json` |

`status` 枚举：`blocked` = 不能支撑该族任何可信（无前视）检验（有限可用切片另记在 `partial_capability`）／`partial` = 有有限切片但不足以出结论／`available` = 可做。

---

## 1. 行业中性 / 行业轮动 —— 不可做（历史）

**查法**：`--check industry`（exit 0）。列目录 + 逐分区 DuckDB 聚合 + 财务表列名扫描 + 代码静态取证。

### 1.1 本地到底存在哪些「行业归属」数据

| 来源 | 路径 | 形态 | 有日期维度？ | 覆盖 | 能否 PIT |
|---|---|---|---|---|---|
| 行业时点快照 | `D:/TSP/data/ext_data/ext_hy_ths_pit/timeseries/date=*/part.parquet` | 5,578 / 5,579 行 × 6 个分区 | **是**（`date=` 分区，2026-11-01…06） | 6 天 | 仅 6 天，向前累积中 |
| 行业当前快照 | `D:/TSP/data/ext_data/ext_hy_ths/part.parquet` | 5,580 行，列 `股票代码/股票简称/所属同花顺行业/symbol/code` | **否**（无日期列） | 当前一次 | 不可（前视） |
| 概念快照 | `D:/TSP/data/ext_data/ext_gn_ths/part.parquet` | 概念成员 | 否 | 当前一次 | 不可（前视） |
| 产业链图谱 | `D:/TSP/data/user_data/industry_chain/graph.json` | 431 节点 / 9 条链 / 3,539 条股票映射，键含 `basis`、`evidence_status` | **否**（只有 `updated_at` = 2026-11-06 与 11-04/05 备份） | 当前一次 | 不可（前视） |
| 财务表（想用主营构成重构） | `D:/TSP/data/financials/{balance_sheet,income,cash_flow,metrics}` | 见 1.3 | 按期 | 5,577 只 | **无主营/行业字段**，重构路走不通 |
| 预计算行业因子 | `D:/TSP/data/kline_daily_linkage` | 9,752,990 行 / 2,136 分区 | 是 | 2018→2026 | 已算，但见 1.3 第 6 条 |

`ext_hy_ths_pit/config.json` 的拉取配方**没有任何日期/时间窗口参数**（`date_param: null`、`time_window_*: null`），表明本地配置没有历史日期入参。已有快照只能向后累积；无法据此判断上游有无其他历史接口或过去是否漏采。

### 1.2 覆盖到什么程度（逐日）

| 快照日 | 行数 | 证券数 | 行业标签数 | 当日面板证券 | 有标签且在面板 |
|---|---|---|---|---|---|
| 2026-11-01 | 5,578 | 5,578 | 257 | —（周日，非交易日） | — |
| 2026-11-02 | 5,578 | 5,578 | 257 | 5,570 | 5,570 |
| 2026-11-03 | 5,578 | 5,578 | 257 | 5,569 | 5,569 |
| 2026-11-04 | 5,578 | 5,578 | 257 | 5,571 | 5,571 |
| 2026-11-05 | 5,579 | 5,579 | 257 | 5,570 | 5,570 |
| 2026-11-06 | 5,579 | 5,579 | 257 | 5,572 | 5,572 |

- 面板共 **5,813 只证券 / 2,141 个交易日**；快照与面板**同日对齐只有 5 天 → 5 / 2,141 = 0.23%**。
- 快照内的证券 **100% 落在面板内**（`h_not_in_panel = 0`），即不存在「标签对象不在面板」的错配。
- 全期看，面板 5,813 只中 **5,579 只有过行业标签，234 只从未有过**（此处只指已扫描六个快照，不能据此判定历史生命周期）。

### 1.3 「除了回填，还有没有合规路径」——逐条查，逐条否

1. **用当前快照倒推历史**：`ext_hy_ths` 无日期列 → 前视，**否**。
2. **用产业链图谱倒推历史**：`graph.json` 无 `date` 维度，只有 `updated_at` 与同周备份，备份是同一快照的版本，**否**。
3. **用财务/主营构成字段重构**：四张财务表的列名全量扫描，匹配 `主营|segment|industry|行业|business` 的结果为**空集**（`balance_sheet/income/cash_flow/metrics` 全为 `[]`），**否**。
4. **用 `mainline_history` 的行业维度**（本次新查的候选捷径）：该表确实有 `kind='industry'` 的**6,476 行、2018-01-10…2026-11-05、237 个行业、1,698 个交易日**——看上去像历史行业数据，但：
   - 它是**涨停梯队聚合**（`limit_up_count / max_boards / rungs_filled / rank`），`member` 是行业名，**不含 symbol→行业映射**，无法做个股行业中性；
   - 它的行业标签来自**当前快照**：`backend/app/services/rps_rotation.py:108`「维度成分股是 snapshot」；`backend/app/services/market_mainline.py:31` 处作者自己写明「概念成分为当前快照回看历史(本地自 2026-07 起留存, 无历史版本)」；
   - 结论：**自带前视声明，否决**。
5. **用公开的历史行业分类落盘文件**：在 `D:/TSP/data` 全量目录普查（43 个顶层目录）中**未找到**任何历史行业分类文件/数据集；仓库里唯一成分接口是 `backend/app/services/ext_presets.py:46` 的 `ths-stock-list`（当前成分、无历史版本参数）。外部是否可得**未验证**，不在本次范围。
6. **用预计算行业因子**（`kline_daily_linkage` 的 `industry_relative_momentum_20d` / `industry_rank_momentum_20d` / `industry_corr_60d` / `industry_beta_60d`）：9,752,990 行里**非空数全为 0**，2,136 个分区中**含任一非空行业因子的分区为 0** —— 列存在但从未产出值，等同于没有。
7. **系统自身的口径也否决回填**：`backend/app/custom/cross_sectional_linkage/store.py:363` 明写「snapshot 行业归属不能回填历史」，`compute.py:49` 用 `join_asof backward` + 最大 30 天时效 —— 快照只能向前覆盖 30 天。

### 1.4 判定

- **历史不可做（blocked / 确证）**：2019–2026 的行业中性化、行业轮动回测，在**不产生前视**的前提下无输入。
- 唯一**合规可用切片**（`partial_capability`）：2026-11-02~06 共 5 个交易日的**当日截面**行业相对强弱。它只能做「今天各行业强弱排名」这类当日展示，不能做任何跨期检验（5 天，无法估计月度轮动的换手与持续性）。

### 1.5 未知

- 供应商是否存在「历史行业成员关系」接口：仓库里只有 catalog + constituents(当前) 两个端点；历史端点**未知**（属外部能力/采购问题）。
- 产业链图谱的来源与更新规则未审计（只有当前版本，无法当历史归属）。

---

## 2. 指数增强 / 指数成分轮动 —— 不可做

**查法**：`--check index`（exit 0）。数据根目录名普查 + 三个指数数据集列名扫描 + `ext_data/*/config.json` 逐文件正则 + 概念快照按指数名打标探测。

| 检查 | 结果 |
|---|---|
| 指数日线 `kline_index_daily` | **599 个指数 / 2,435 个交易日 / 2016-10-28…2026-11-06**；列 = `symbol,date,open,high,low,close,volume,amount` |
| 指数增强行情 `kline_index_enriched` | 列 = OHLCV + `raw_close/raw_high/raw_low`（复权价），**无成分、无权重** |
| 指数元数据 `instruments_index` | 599 行，列 = `symbol,name,code,asset_type`，**无成分、无权重** |
| 数据根下目录名含 `constituent/weight/member/成分/权重` | **未找到** |
| 三个指数数据集里的权重/成分列 | 三张表匹配结果全为 **空列表** |
| `ext_data/*/config.json` 命中「成分/权重」 | 3 个文件命中，**但命中词都是 `constituent`，片段为** `https://fuyao.aicubes.cn/api/a-share-index/constituents/ths-stock-list` —— 这是**同花顺板块（概念/行业）成分端点**，不是指数权重配方；`is_index_weight_recipe` 逐条为 `false` |
| 概念快照里以宽基指数名打标 | `沪深300 = 0`、`中证500 = 0`、`中证1000 = 0`、`上证50 = 0` —— 连「当前成分的快照代理」都不存在 |

> 口径更正：上一轮我自己的脚本把「config 命中 `成分/权重`」直接列为「有成分类配方」，本次把它拆成命中片段 + 语义判定，结论是**这些命中与指数成分无关**。这一点在 `check_index.json` 的 `ext_data 配置中提及 成分/权重 的配方文件` 事实里逐条留档。

**判定**：**不可做（blocked / 确证）**。指数增强需要「某日某指数的成分与权重」；本地只有指数价格。用今天的成分回测 2019 年即前视；用等权近似日线收益也不成立（缺成分就无法定义被增强的宇宙）。

**未知**：本审计只能证明「当前不存在」，**无法证明「历史上从未存在过」**（可能采过后被清理，无法从现存文件判定）。

---

## 3. ETF 全族 —— 不可做

**查法**：`--check etf`（exit 0）。文件系统 census（`os.walk`，非 glob，含隐藏文件）+ DuckDB 交叉核对 + 全量分钟线 `symbol` 列范围扫描。

| 目标 | 路径 | 文件数 | 字节数 | 非空文件 |
|---|---|---|---|---|
| ETF 日线 | `D:/TSP/data/kline_etf_daily` | **0** | **0** | 0 |
| ETF 增强 | `D:/TSP/data/kline_etf_enriched` | **0** | **0** | 0 |
| ETF 分钟 | `D:/TSP/data/kline_etf_minute` | **0** | **0** | 0 |
| ETF 复权因子 | `D:/TSP/data/adj_factor_etf` | **0** | **0** | 0 |

- 三个目录**存在但从未落过任何分区**（不是路径写错）。
- `instruments_etf`：**1,769 条 ETF 代码**（19 个前缀，最多 `159`=718、`588`=88、`561`=84、`560`=84、`512`=82…）—— **有代码表，没有任何行情**。
- 库内是否有替代表：
  - 股票日线面板里 ETF 代码数 = **0**；前缀 `51/15/56/58/16` 在面板里**不存在**。
  - **全量分钟线**（2,389 个文件、约 24 GB）扫 `symbol` 列：**5,917 只代码，其中 ETF 形态代码 = 0** —— 分钟线也只有股票。
- 因此：ETF 轮动、ETF 套利（一二级/折溢价）、ETF 作为基准净值，**全族无输入**。

**判定**：**不可做（blocked / 确证）**。

**未知**：ETF 行情是「从未采购」还是「曾有后被清理」——目录存在但无写入，无法从现存文件判定原因。

---

## 4. 做空 / 对冲 / 市场中性 —— 不可做

**查法**：`--check short`（exit 0）。`backend/app/**/*.py` 全量正则命中 + 逐处语义判定 + 数据根目录名普查 + 概念快照打标计数。

| 检查项 | 结果 | 语义 |
|---|---|---|
| `allow_short` / `short_selling` / `sell_short` | **0 命中** | 撮合器没有空头开关 |
| `"buy"` / `"sell"` 字面量（`backtest/engine.py`） | 14 / 9 | 委托方向只有买卖两向（`engine.py:218`）；`engine.py` 内 `"short"` 出现 **0 次** |
| 仓位权重 | 全部 `>= 0`（`1/n` 或 `max(score,0)` 归一），受 `equity * max_exposure_pct - market_value` 约束（`engine.py:3509`） | 不存在负仓位 |
| `做空` / `卖空` / `空头` 中文命中 | **7 条**（全量清单见 `check_short.json` → `facts[0].value`） | 2 条**因子分组记账**（`backtest/factor.py:1447` docstring「做多最高组 + 做空最低组」、`:1474` 注释、`:1478-1481` `ls_ret=(top_ret-bot_ret)/2` 的 50/50 两腿净价差）；1 条**方向标签字典**（`strategy/prompt_builder.py:22` `DIRECTION_CN` 的 `short→做空`）；3 条**文案**（`services/market_recap.py:87`、`services/stock_analyzer.py:137`「均线空头排列」、`:183`）；1 条**假阳性**（`services/market_recap.py:101`「只做~~空值~~回退」）。全部**不进入撮合** |
| `对冲` / `套保` / `套期` | **0 命中** | 无对冲语义 |
| `hedge` | 带词边界 **0**；naive 子串 **70** | **70 条全是假阳性**：`EnrichedGenerationUnavailableError` 里 `...hed` + `Ge...` 跨词边界拼出 `hedGe`。这条留档是为了防止后来人用 `grep -i hedge` 得出「有对冲路径」的错误结论 |
| `两融` / `融资余额` / `融券` | 3 条命中，全在**注释**里（板块过滤名单：`market_mainline.py:132`、`preferences.py:479`、`sector_rotation.py:63`） | 只是把「融资融券」当成一个超大概念板块来过滤，不是两融数据 |
| 数据根下 `margin/rzrq/lending/borrow/short` 目录 | **未找到** | 无两融余额、融券余额、券源、保证金、借券费表 |
| 概念快照中的相关标签 | `融资融券 = 3,891 只`、`转融券 = 0` | 「标的身分」的当前快照，**无余额、无费率、无券源、无历史** |

**判定**：**不可做（blocked / 确证）**。不只是数据问题——引擎侧没有空头账户（保证金、借券费、强平、T+1 卖出限制），数据侧没有券源与费率；两腿策略只能测多头腿，其 Sharpe 天然含市场 beta，**不能当中性策略的结论**。

**未知**：A 股实际券源可得性无法从行情数据推断；即使采购两融明细，也无法对 2019–2022 的个股逐日券源做判定。

---

## 5. 「616 只无因子」口径争议 —— 定论

### 5.1 四个数字的精确口径（全部可复现，互不同义）

| 数字 | 精确口径 | 分母 | 复算结果 | 说明 |
|---|---|---|---|---|
| **616** | 日线面板 5,813 只中，在 `adj_factor`（**复权因子事件表**）里**没有任何一行**的证券数 | 5,813 | `5,813 − 5,197 = 616` ✅ | 语义 = 「**无复权因子事件行**」，**不是**「没有因子数据」 |
| **78** | 元数据 5,536 只中，在日线面板 5,813 里**完全没有日线**的证券数 | 5,536 | 78 ✅ | 1990 年代上市、2018 年前已退市/更名（15 只名称含「退」），最早上市 1990-12-19 |
| **355** | 日线面板 5,813 只中，**元数据里没有**的证券数 | 5,813 | 355 ✅ | **全部是北交所 92x** |
| **236** | 日线面板 5,813 只中，四张财务表（`balance_sheet/income/cash_flow/metrics`）**都没有任何记录**的证券数 | 5,813 | 236 ✅ | 样例：`000004.SZ 国华退`、`000005.SZ ST星源`、`000016.SZ *ST康佳A` |
| 663 | 上一轮报告里出现过的一个数 | — | **无法复现** | 候选口径 236 / 313 / 266 / 628 / 802 / 1,079，**没有一个等于 663**（差异 ≥ 35） |

补充口径：**面板 ∩ 元数据 = 5,458**。

### 5.2 复算命令（可原样重跑）

```bash
cd C:/work/sourcecode/tick-stock-panel
PYTHONUTF8=1 backend/.venv/Scripts/python.exe research/data-gaps-20261107/scripts/audit_data_gaps.py --check universe616   # exit 0
```

核心 SQL（模块内的第一条，`summary.json` 的 `dispute_616` 亦收录）：

```sql
-- 616：面板证券中在 adj_factor 里没有一行的
with panel as (select distinct symbol from read_parquet('D:/TSP/data/kline_daily/**/*.parquet'))
select count(*) from panel where symbol not in (select distinct symbol from read_parquet('D:/TSP/data/adj_factor/**/*.parquet'));
-- → 616     （panel=5813, adj_factor=5197, adj_factor 全部落在面板内）
```

本次另用**独立会话**（`scripts/independent_recheck.py`，不复用本目录审计脚本的任何函数）重算核对，结果一致：`panel 5813 / ins 5536 / adj 5197 → 616`，`ins not in panel = 78`，`panel not in ins = 355`，`panel 无任何财务 = 236`，`ins no adj = 650`。该脚本自带 `EXPECTED` 常量逐项比对，本轮输出 `all_match=true, diffs={}`（exit 0），证据：`results/independent_recheck.json`。

### 5.3 616 是怎么算出来的（出处可核）

- 原始出处：`docs/research/parallel-data-20261106/DATA_QUALITY.md:74` —— 原文是「复权因子覆盖｜5,813 只面板证券中 **616 只**完全没有因子行」，**表述本身就是准确的**。
- 计算点：`research/parallel-data-20261106/audit_data_quality.py:1171`（读 `adj_factor/all.parquet`）→ `:1205`（`check_adj_factors(..., panel_symbols=...)`），证据字段名 **`panel_symbols_without_factor`**。
- 所以 616 不是「另一个人的算法错了」，而是**这句话在后续转述里被简写成「616 只无因子」，再被读成「616 只没有因子数据」**。两字之差，把「复权因子事件缺失」变成了「因子库缺失」。

### 5.4 为什么 78 + 355 + 236 = 669 ≠ 616

三者是**三个不同维度上的缺口**，不是对同一集合的互补分解：

- 616 是「面板 ∩ 复权因子」的差集（分母=面板）；
- 78 是「元数据 − 面板」的差集（分母=元数据）；
- 355 是「面板 − 元数据」的差集（方向相反，且全是北交所）；
- 236 是「面板 − 财务（四表任一）」的差集（分母=面板）。

把分母换成元数据，同一个「无因子行」会变成 **650**：`5,536 − 4,886（元数据 ∩ 因子）= 650`，而 `650 = 78（元数据有、面板无日线；因子全落在面板内，故必然无因子行）+ 572（面板∩元数据中无因子行）`；同时 `616 = 572 + 44（面板中既无元数据又无因子行）`。同一个缺口的三个数字都成立，只因为分母与差集方向不同——这正是不能拿它们互相对账的原因。

### 5.5 616 的实质：这 616 只究竟「缺」了没有

| 检查 | 输出 |
|---|---|
| 按代码前缀 | `00:225 / 30:92 / 60:186 / 68:69 / 92:44` |
| 首根 K 线年份 | 2018–2019: 457 / 2020–2022: 55 / 2023+: 104 |
| **复权价 vs 原始价一致性** | 扫描 **789,432 行**，`close == raw_close` 差异行 **0**，有差异的证券 **0 只** |

这证明这 616 只在本地面板内的复权价与原始价一致，不能证明真实世界没有除权事件，也不能排除供应商漏记。正确表述是「**616 只无复权因子事件行**」。616 可以复现，但单凭该数字不能判定研究因子缺失或复权收益可靠；公司行为完整性仍为未知。

**一个会造成混淆的数值巧合**：2026-11-06 当日面板按板块统计为 `00:1,490 / 30:1,411 / 60:1,700 / 68:616 / 92:355` —— **科创板当日恰好也是 616 只**。若有人按「当日 68 前缀截面」统计，会得到同一个数字但含义完全不同（这正是「同一数字两种口径」最容易踩的坑）。

### 5.6 建议统一写法（写进任何引用它的报告）

> 面板 5,813 只（分母）：元数据缺 355（北交所）、元数据有而面板无日线 78、面板无财务 236、面板无复权因子事件行 616、面板∩元数据 5,458。每写一个数必须写清分母与差集方向。

---

## 6. 补齐这四类分别需要什么？不采购前提下有没有可能？

本表的「不可补」限定为**只用本次检查的现存本地文件，补齐既有历史回测区间**，不等于已证实必须购买外部数据。「需采购(不做)」只有在证实免费来源不足、付费来源可满足时才可下结论；本次未核验外部供应商，四类均不作此断言。

| 策略族 | 补齐判定 | 必需输入或能力 | 不采购前提下的边界 |
|---|---|---|---|
| 行业中性/轮动 | **不可补（本地历史）** | 含有效日期与可知时间的逐股行业归属；若按主营重构，还需当时已披露的主营构成和稳定分类规则 | 已有六天快照可以向后累积，无法据此恢复更早历史；公开历史分类档案或披露资料是否足够，未验证，不回填当前快照 |
| 指数增强 | **不可补（本地历史）** | 历史成分、权重、生效及调样日期 | 本地未找到，当前不可做；免费来源完整性、采购必要性未知，不推测替代方案 |
| ETF 全族 | **不可补（本地历史）** | ETF 行情及复权/公司行为；分钟、折溢价等按具体策略需要 | 数据目录和读接口已存在，但行情为空；能否从免费来源补齐所需历史及取得授权，未验证 |
| 做空/对冲 | **不可补（本地历史与执行）** | 对应对冲工具行情或融券标的、券源、费率、保证金历史，加空头账户与执行支持 | 本地输入及执行路径均不足；仅有两融标签或余额不能证明可借券；外部免费或付费数据能否补齐真实券源，未知 |

补齐四类需要的分别是历史行业归属、历史指数成员与权重、ETF 自身行情，以及可执行的对冲工具/借券证据与账户模型。本地文件无法补齐这些历史缺口；行业快照可以继续积累，其他三类需要验证外部来源并完成相应采集、校验或执行工程。是否可以全程不采购，当前证据不足，不能把「本地没有」写成「只能采购」。616 的数值与集合口径已经澄清，不需要采购；它不能代替公司行为完整性审计。

---

## 7. 未知 / 未找到 / 不可复现清单

| 类别 | 内容 | 判定 |
|---|---|---|
| 未知 | 供应商是否存在历史行业成员关系接口（仓库只有当前成分端点） | 未知（需向数据方确认） |
| 未知 | 产业链图谱的来源与更新规则（只有当前版本与同周备份） | 未知 |
| 未知 | 历史上是否曾存在指数成分文件后被删除 | 未知（只能证明"当前不存在"） |
| 未知 | ETF 行情是"从未采购"还是"曾有后被清理" | 未知 |
| 未知 | A 股个股历史券源可得性 | 未知（无法从行情推断） |
| 未知 | 供应商是否漏记除权事件（`close==raw_close` 只证明面板内部一致） | 未知 |
| 未找到 | 历史行业分类落盘文件、指数成分/权重数据集、两融/券源表、ETF 行情（任意粒度） | 在 `D:/TSP/data` 全量目录普查中**未找到** |
| 不可复现 | **663**（曾出现的"无财务"口径） | 候选口径 236/313/266/628/802/1,079 均不等于 663；**无法复现**，建议停用该数字 |

---

## 8. 对既有结论的影响

1. **四族不能进入候选筛选**：行业中性/轮动、指数增强、ETF 全族、多空对冲，在当前数据下无法产生可信的样本外结论。首轮 36 次试验里若包含这四族，其结果应标为「不可判定」而不是「失败」——「0 通过」里有多少属于数据边界、多少属于策略无效，必须按族拆开看，否则会把数据缺口误记为策略缺陷。
2. **616 必须改写**：任何写成「616 只无因子/无因子数据」的表述要改为「616 只无复权因子事件行（本地复权价与原始价一致，外部事件完整性未知）」。该数字本身**不足以证明**「复权处理不可信」或「复权处理可信」，因此不宜再作为「横截面回测不可做」的理由之一；真正支撑该结论的是样本外检验不可做（停牌/退市表缺失、行业 PIT 仅 6 天、无成交可行性审计）。
3. **可做与不可做的分界**：单标的/小组合的时序策略未必依赖这四类输入，但仍需独立校验其所需数据；只要进入「行业分层、指数基准、ETF 标的、空头腿」任一维度，即落入本报告的 blocked 区间。
4. **合法的有限产出**：2026-11-02~06 的当日行业截面（5 天）可以用于展示与管道验证，但不得用于任何绩效宣称。

---

## 9. 文件清单

```
research/data-gaps-20261107/
├── REPORT.md                       # 本报告
├── scripts/
│   ├── audit_data_gaps.py          # 五项检查，只读；--check {industry,index,etf,short,universe616,all}
│   ├── build_summary.py            # 汇总 results/check_*.json → results/summary.json
│   ├── verify_delivery.py         # 记录子进程真实退出码与原始日志
│   └── independent_recheck.py      # 独立复核：不复用审计脚本任何代码，重算列出的14项数字及若干补充事实并与 EXPECTED 对账
└── results/
    ├── check_industry.json         # 13 条事实及代码取证 + SQL 日志
    ├── check_index.json            # 7 条事实 + 1 条代码取证
    ├── check_etf.json              # 6 条事实 + 1 条代码取证
    ├── check_short.json            # 5 条事实及代码取证
    ├── check_universe616.json      # 14 条事实 + 4 个候选口径的失败对账
    ├── independent_recheck.json    # 第二条独立路径：14 项关键数字 + 616 构成分解（572/44）+ close==raw_close 扫描
    ├── execution_log.json          # 五项检查、独立复核与汇总的实际退出码
    ├── run_*.log                   # 原始命令输出
    └── summary.json                # 机器可读总表：family / status / verdict / evidence_path / evidence_command / exit_code
```

每条判定的 `evidence_command` + `exit_code` 都写在 `summary.json` 的 `families[]` 里；每条事实在对应 `check_*.json` 的 `facts[]` 里带 `sql`（可直接在 DuckDB 跑）或 `source`（文件路径），代码结论带 `path:line`。

**本次改动范围**：只新增 `research/data-gaps-20261107/`。未修改 `backend/`、未触碰 `engine.py` / `walkforward.py` / `test_walkforward.py` 等正在被其他成员改动的文件（`git status` 中这些文件的修改均非本次产生），未提交、未部署、未重启服务、未做真实交易。
