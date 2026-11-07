# E1 / E2 可执行判定规格（规范性附件）

被 `PROTOCOL.md` v2 §10 引用。两个判定器分工不同：

- **E1 = 数据有效性前提**（全批跑一次）：先证明「停更/消失的股票」对基准收益的影响可忽略，否则任何策略结论都建在不可靠的样本上。
- **E2 = 逐策略候选门槛**：10bp 成本下的净 Sharpe 与换手。

两者都只读已有产物或调用现有研究代码，**不修改生产源码**。

---

## A.1 E1：停更偏差基准

### A.1.1 问题定义

面板里某些证券会"跑到一半就没了"（停更/退市/数据缺失）。如果回测宇宙只保留活到期末的股票，收益会被系统性抬高（幸存者偏差）；如果面板保留了它们但引擎只能按最后收盘价挂账，则又可能低估退市损失。E1 量化第一个方向，并对第二个方向做敏感性。

### A.1.2 输入

| 输入 | 来源 | 要求 |
| --- | --- | --- |
| 日线面板 | `common.load_panel(m)` | 已含 `raw_close`/`close`/`volume`/`amount`/ST 与涨跌停信号 |
| 观察窗口 | `EVAL_START=2019-07-01` ~ `EVAL_END=2026-10-30` | 与 `registry.json:meta` 一致 |
| 股票池规则 | `common.add_universe` | 不改动任何阈值 |
| 账户/成本 | `common.make_config(slippage_bps=10)` | 与 PROTOCOL §2 完全一致 |
| 组合规则 | C00：月末取前 20 日均成交额最大的 5 只，等权，`max_hold=20` | 不含 alpha，差异只可能来自样本集 |

### A.1.3 两个样本集的定义

```
T_end        = 2026-10-30
缓冲         = 20 个交易日（用面板内交易日序列计算）
last_bar(s)  = 证券 s 在面板中的最后一个交易日
bars(s)      = 证券 s 在 [EVAL_START-预热, T_end] 内的非空 bar 数

S_stale = { s | last_bar(s) < T_end - 20 交易日  且  bars(s) >= 120 }
组 A（含停更）= 当前完整宇宙（不做任何剔除）
组 B（仅存续）= 组 A - S_stale
```

实现要点（关键）：剔除必须在 `add_universe` **之前**完成：

```python
panel_B = panel.filter(~pl.col("symbol").is_in(list(S_stale)))
prepared = add_universe(add_indicators(panel_B))
```

因为指标是 per-symbol trailing，剔除整只证券不会污染其他证券；C00 不使用 `market_breadth`，所以宽度列不受影响。

### A.1.4 输出（`results/e1_survivorship.json`）

```json
{
  "window": {"start": "2019-07-01", "end": "2026-10-30", "n_days": 1778},
  "counts": {"n_symbols_A": 0, "n_symbols_B": 0, "n_stale": 0, "n_stale_bars_ge_120": 0},
  "A": {"cagr": 0.0, "sharpe": 0.0, "max_drawdown": 0.0, "n_closed_trades": 0,
        "open_at_end": 0, "open_at_end_share": 0.0},
  "B": {同上},
  "diff": {"cagr_pp": 0.0, "sharpe": 0.0, "mdd_pp": 0.0},
  "yearly": [{"year": 2019, "cagr_A": 0.0, "cagr_B": 0.0, "diff_pp": 0.0}],
  "haircut_sensitivity": [{"haircut": 0.0, "cagr_A": 0.0}, {"haircut": -0.3, "cagr_A": 0.0},
                          {"haircut": -0.5, "cagr_A": 0.0}, {"haircut": -1.0, "cagr_A": 0.0}],
  "verdict": "PASS",
  "reasons": ["..."],
  "exit_code": 0
}
```

`diff.cagr_pp = (A.cagr - B.cagr) × 100`。`open_at_end_share` = 期末未平仓市值 / 期末权益。

### A.1.5 判定规则

| 结果 | 条件（全部用 `|·|` 绝对值） |
| --- | --- |
| **PASS** | \|cagr_pp\| < 1.0 **且** 每个自然年 \|diff_pp\| < 2.0 **且** 两组 `open_at_end_share` 差 < 5pp |
| **WARN** | 1.0 ≤ \|cagr_pp\| < 3.0（结论可引用，但必须附上 diff 与方向） |
| **FAIL** | \|cagr_pp\| ≥ 3.0，或 A 组 `open_at_end_share` > 2%（基准收益依赖"最后价挂账"） |

退出码：`0 = PASS`、`2 = WARN`、`3 = FAIL`、`1 = 输入/运行错误`。

方向解释（必须写进报告）：

- `cagr_A > cagr_B`（diff > 0）：剔除停更股会**低估**收益 → 幸存者偏差方向为正，保留它们更保守。
- `cagr_A < cagr_B`（diff < 0）：停更股是**拖累** → 只保留存续股会高估收益，必须用组 A。

### A.1.6 E1-b：退市损失敏感性（诊断，非门槛）

对 `S_stale` 内期末仍持有的仓位，把最后可得价乘以 `(1 + haircut)`，`haircut ∈ {0, −30%, −50%, −100%}`，重算 `cagr_A`。若 `−50%` 下 `cagr_A` 下降 > 2pp，则任何"全期年化"结论必须同时报出该区间。

### A.1.7 已知局限（必须与结论一起引用）

1. 无权威退市记录与停牌表（`coverage_report.json: security_lifecycle_coverage = unknown`），`S_stale` 只能近似"停更"，无法区分退市/长期停牌/数据缺失。
2. 面板起点之前（2018-01-08 以前）已上市的 3,060 只在窗口起点被截断 → **窗口前的退市损失完全测不到**，E1 不能声称"已消除幸存者偏差"。
3. E1 的两个组都用同一套成本与撮合，因此只隔离「样本集」差异，不能隔离「数据供应商自身对退市股的处理」。

---

## A.2 E2：10bp 净 Sharpe 与换手

### A.2.1 输入

| 输入 | 路径/字段 | 说明 |
| --- | --- | --- |
| 登记表 | `results/registry.json` 的 `runs[key]` | 取 `ALL`、`OOS`（= T2）的 `sharpe`/`cagr`/`max_drawdown`/`n_days` |
| 明细 | `results/run_<strategy>_10.json` | 取 `equity[].value` 与 `trades[].entry_value/exit_value` |
| 情景 | `slippage_bps = 10` 且 `gross = false` | 30bp/gross 不参与 E2 |

### A.2.2 公式

```
r_t   = V_t / V_{t-1} - 1                    # V = 引擎权益曲线，已扣佣金/印花税/过户费/滑点
Sharpe_ann = mean(r) / std(r, ddof=1) * sqrt(252)     # rf = 0，与 PROTOCOL §2 一致

# 年换手（单边，one-way）
TO_annual = [ Σ(entry_value) + Σ(exit_value) ] / ( 2 × mean(V_t) ) / ( n_days / 252 )
```

注意：

1. **不需要再扣一次成本**：权益曲线已经是净额（含全部费用与滑点），二次扣减会双重计费。
2. 用 `mean(V_t)` 而不是初始权益做分母：权益在 7 年内会漂移，用初值会系统性高估或低估换手。
3. 未平仓持仓按期末市值计入权益，不计入 `entry_value`/`exit_value` 分母以外的任何调整。
4. 交叉核对：`registry.ALL.gross_traded_over_initial / years` 必须与 `2 × TO_annual` 同量级（偏差 > 20% 说明明细与汇总不一致，判 `DATA_MISMATCH`）。

### A.2.3 换手阈值的经济含义（为何是 30×）

按本轮实测的单边成本率（佣金 3bp + 过户费 0.1bp + 滑点 10bp 买入侧；卖出再加印花税 10bp），**每 1× 单边年换手 ≈ 0.38% 年成本**（由 S07 的 gross 与 10bp 差反推：14.4pp/7.06 年 ÷ 5.3× ≈ 0.385%）。因此：

| 单边年换手 | 10bp 下滑点+税费年成本 |
| --- | --- |
| 5× | ≈ 1.9% |
| 12× | ≈ 4.6% |
| 30×（门槛） | **≈ 11.5%** |

含义：30× 是"成本可行性"的上限，不是目标値。能过 30× 但超过 12× 的策略，必须在毛收益上多赚 5% 以上/年，不推荐进入实现讨论。

### A.2.4 输出（`results/e2_judgement.json`）

```json
{
  "generated_at": "2026-11-06T...",
  "criteria": {"min_sharpe": 0.5, "max_turnover": 30.0, "scenario_bps": 10},
  "results": [
    {"strategy": "S07_xs_lowvol_60d",
     "all": {"sharpe": 0.031, "sharpe_recomputed": 0.031, "cagr": -0.001, "max_drawdown": -0.299, "n_days": 1778},
     "t2":  {"sharpe": 0.97, "sharpe_recomputed": 0.97, "cagr": 0.04, "max_drawdown": -0.15, "n_days": 925},
     "turnover": {"annual_one_way": 5.30, "years": 7.06, "mean_equity": 1000000.0,
                  "gross_traded_over_initial": 66.28, "cross_check_ratio": 1.0},
     "checks": {"t2_sharpe_gt_0.5": true, "all_sharpe_gt_0.5": false, "turnover_lt_30": true},
     "verdict": "FAIL", "reasons": ["ALL Sharpe 0.031 ≤ 0.50"]}
  ],
  "summary": {"n_strategies": 12, "n_pass": 0, "n_warn": 0, "n_fail": 12},
  "exit_code": 2
}
```

### A.2.5 判定规则

| 结果 | 条件 |
| --- | --- |
| **PASS** | T2 Sharpe > 0.50 **且** 全期 Sharpe > 0.50 **且** 单边年换手 < 30× |
| **WARN** | 两个 Sharpe 中仅一个 > 0.50 且另一个 > 0.30，且换手 < 30×（记为"单边强、全期弱"或反之） |
| **FAIL** | 其余 |

退出码：`0 = 至少一条 PASS`、`2 = 无 PASS（判定完成）`、`1 = 输入错误`；明细与汇总不一致时额外置 `DATA_MISMATCH = true`。

### A.2.6 E2 不负责的事（不重不漏声明）

E2 只回答"净 Sharpe 是否够高、换手是否可行"。候选还必须同时过 `PROTOCOL.md` §10 的第 1、4、5、6、7、8、9 项（DSR、30bp 耐受、年度集中度、回撤、交易笔数、拒单敏感性、前瞻锁箱）。**E2 PASS 不得单独输出为"已找到可盈利策略"。**

---

## A.3 已实现的判定器

`scripts/judge_e2.py`（本目录，只读现有 JSON，**不跑回测**）：

```
backend\.venv\Scripts\python.exe research\strategy-search-20261107\scripts\judge_e2.py
# 可选：--scenario 10|30  --out results/e2_judgement.json
```

E1 判定器（`scripts/e1_survivorship.py`）**尚未实现**，因为它需要跑两次 C00 基准回测，而本轮已被明确禁止开新回测。实现前需人工放行，实现时严格按 A.1.3 的剔除顺序。


## A.4 v3 E1 执行补充（2026-11-07，运行前写定）

本次任务已授权仅执行 E1 A/B；A.3 的旧人工放行待办保留为历史说明。新脚本 `scripts/e1_survivorship.py`，输出 `results/e1_v3/`，不覆盖旧结果。

- 原 `common.run_continuous` 未将 `strat.score` 映射为矩阵读取的 `score`，旧 C00 不能据此证明按流动性排序。本次独立包装保持相同逐年 carry/账户/成本/信号延迟，显式 `prior_amount20 -> score`；不改 common 或生产引擎。这是实现纠错，旧 C00 不能伪装为新规则的预注册结果。
- A 为原面板；B 在指标和宇宙计算前整只剔除 S_stale。阈值为全日期轴终点往前20个实际交易日，last_bar 严格小于阈值，bars>=120。S_stale 只用于回顾偏差诊断，B 具有刻意使用期末存续信息的性质，不能部署为实时池。
- 月末信号收盘确认，下一交易日开盘撮合；不将同日收盘计算的信号视为同日成交。交易金额排序使用此前20条证券 bar；停牌跨度局限沿用旧定义。月末仍按已有面板日期轴推导，非新增权威交易日历。
- A.1.5 逻辑空档更正：FAIL 优先（|CAGR差|>=3pp 或 A期末持仓市值占权益>2%）；其余仅所有 PASS 条件满足才 PASS，其他一律 WARN。WARN 也不放行后续策略回测。这里 A 的2%依旧按原文全部未平仓持仓计算，不偷换为仅停更持仓。
- 自然年差值从连续权益重算简单收益，首年从评估首日权益起算，此后以前一年末权益为基准，避免分段 stats 及逐年漏掉首个交易日收益。局部年度不年化；字段明确为 return_A/B。
- haircut只减少A期末仍持有的S_stale仓位终值，不收取虚构清算费用，不回写历史路径；年化沿用252交易日和权益相邻收益数量。若无该类仓位，各haircut相同也必须报告。
- 输入保留完整面板IPC SHA256和既有Polars行哈希；代码与读取链路、规范及账本先冻结再执行，结束再检验哈希。校验排序非空、两组日历一致、现金加持仓与权益误差<=0.05元；边界数值校验先于回放。出现变更或错误输出 INPUT_OR_RUN_ERROR/1，不据此放行。
- E1是数据诊断，C00 A/B及四个终值压力不增加独立alpha假设计数；不得择优选择某组作为盈利策略，不执行12策略重跑。无停更暴露只说明本C00不敏感，不能外推至全部策略或声称排除幸存者偏差。
