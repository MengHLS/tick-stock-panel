# 策略批量评估底座（S3 工程支撑）

把 `research/batch-backtest-framework-20261107/INTERFACE-MAP.md` 里 5 个最小改动点落成可运行的独立脚本，
不动 `backend/` 生产源码。输出是「N 条策略 × M 个成本档」的逐次试验台账，用来把策略搜索的每一次尝试
变成可复算的试验记录，而不是一批互相矛盾的截图。

- 仓库：`C:\work\sourcecode\tick-stock-panel`，分支 `dev` @ `848bd04b`（施工时工作区有他人未提交改动 71 行）
- 运行环境：`backend/.venv/Scripts/python.exe`，numpy / polars / psutil 已就绪
- 数据：`D:\TSP\data`，enriched 交易日 2141 个（2018-01-08..2026-11-06）

## 1. 文件

| 文件 | 作用 |
| --- | --- |
| `batch_harness.py` | 编排器：规格解析 → 交易日/折 → 标的池 → 锁矩阵预热 → 每(策略,窗口)一次 prepare → 逐成本档试算 → 多重检验 → registry/evidence |
| `specs/demo-2x2.json` | 演示规格（2 策略 × 2 成本档，IS/OOS/ALL 三窗口） |
| `selftest.py` | 8 项纯函数/契约自检，不碰行情数据 |
| `runs/<批次>/registry.json` | 整批台账（规格、环境、数据世代、折、预处理、全部 trial、资源） |
| `runs/<批次>/registry.jsonl` | 一行一个 trial，便于直接扫读/入库 |
| `runs/<批次>/summary.md` | 人读表格 |
| `runs/<批次>/evidence-<run_id>.json` | 证据清单，同时按 app 契约写入 `data_dir/backtest_runs/<hex>.json` |

## 2. 用法

```powershell
cd C:\work\sourcecode\tick-stock-panel
backend\.venv\Scripts\python.exe research\strategy-harness-20261106\batch_harness.py `
    --spec research\strategy-harness-20261106\specs\demo-2x2.json
# 退出码 0=全部成功且数据世代稳定；2=有 trial 失败或世代漂移；1=致命错误
backend\.venv\Scripts\python.exe research\strategy-harness-20261106\selftest.py
```

规格字段：`start/end`、`asset_type`、`strategies[]`（`id/params/overrides`）、`cost_tiers[]`
（`fees_pct/commission_pct/stamp_tax_pct/slippage_bps`）、`base`（撮合/持仓/资金）、
`walkforward{train_days,test_days,step_days}`（全部**按交易日计数**）、`fold_used`、`windows`、
`symbols{mode:"even_stride",n,reference_date}`、`prewarm_years`。

## 3. 5 个改动点怎么落地

1. **批量层强制结果契约**：`LIGHT_POLICY`（`batch_harness.py`）在每次 `service.run(...)` 显式传入
   `BacktestResultPolicy(include_curves=False, include_trades=False, include_per_symbol_stats=False,
   include_return_distribution=False, include_monte_carlo=False, include_benchmark=False)`。
   实测（`stats` 字典的键清单）：12 个 trial 的结果对象里 `equity_curve`/`trades`/`per_symbol_stats`/
   `return_distribution`/`benchmark`/`monte_carlo` **根本不存在**（不是空列表，是键缺失），
   34 个键全是标量与元数据，内存只随「当前这一份 prepared」增长。
2. **同切片共享装载**：一个 (策略, 窗口) 只调一次 `prepare_matrix_optimization(configs)`，
   `configs` 是**全部成本档**的回测配置——成本参数不在 `_matrix_prepare_signature` 里，所以 2 个成本档共用
   1 份 prepared，`prepare_ms` 按份数摊到每个 trial（registry 里 `shared_prepare.amortized_prepare_ms`）。
   批次开头调一次 `build_matrix_cache_profile` + `prewarm_matrix_cache` 预热锁矩阵，并断言预热起点覆盖
   「窗口起点 − 特征预热天数」，不覆盖就在日志里 WARN 并给出所需年份（避免"预热了但没用上"）。
3. **折边界只用真实交易日**：`repo.list_enriched_dates(start,end,asset_type)` →
   `generate_folds(..., trading_days=days)`，并逐个断言 4 个边界都在交易日集合内（`folds()` 里
   `AssertionError`），`step_days >= test_days` 在规格加载阶段就拒绝。自然日口径完全不用。
4. **指标口径 + 多重检验**：跨策略比较只取 `_calc_portfolio_stats_from_values` 产出的标量
   （`COMPARABLE_STATS`），逐笔近似的 `_calc_stats` 不参与。`stats_v2.deflated_sharpe_psr` 已接线：
   每个窗口内先算 `expected_max_sharpe(n_trials, 各试验夏普方差)` 作为 EM，再算 PSR/单侧 p，
   最后跨试验做 `bh_fdr_qvalues`。`n_trials` 口径 = 该窗口内成功试验数（策略×成本档），
   **不**把 IS/OOS/ALL 当独立试验重复计数。PSR 与 `stats_v2` 逐点比对，误差 >1e-9 直接 `AssertionError`。
5. **数据版本 + 证据**：整批前后各取一次 `engine.data_generation`，不一致即退出码 2；每份 prepared 记录
   `source_generation` 与内容指纹（矩阵：形状/轴端点/`close` 的 nansum/字段宽度/字节数 → blake2b；
   面板：形状/列名/`hash_rows` 和 → blake2b）。指纹同时写进每个 trial，任一数字都能反查到
   「哪一版数据 + 哪份矩阵 + 哪个成本档」。

## 4. 实测（2026-11-06 23:47–23:54，Asia/Shanghai）

规格 `specs/demo-2x2.json`：区间 2025-01-02..2026-11-06（446 个交易日），折 3 个（用 fold#0：
IS 2025-01-02..2026-01-13 / OOS 2026-01-14..2026-04-16 / ALL 全区间），策略
`first_limit_pullback_3f_runner_t74`、`first_board_chain_rebreak`，成本档 `zero`（全 0）与
`real`（佣金 2.5bp + 印花税 5bp 卖出 + 滑点 5bp），标的池 200 只等距抽样，`holding_days=5`/`max_positions=5`。

| 运行 | 预热 | prepare 合计 | run 合计 | 峰值内存 | 墙钟 | 缓存命中 | 退出码 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 23:47 冷缓存（首次建 220,637,952 B） | 20.45s | 5,132.4ms | 3,769.9ms | 标记点采样 988.7MB | 29.9s | 12/12 | 0 |
| 23:54 缓存已存在（**交付基准，代码最终版**） | 0.74s | 5,390.6ms | 3,812.6ms | OS peak_wset 316.4MB | 10.5s（进程外 13.7s） | 12/12 | 0 |

两次运行相隔 7 分钟、进程全新启动、缓存状态不同，12 个 trial 的收益/回撤/夏普/交易数**逐位相同**，
可以当作“同一数据世代下结果可复现”的实证。

对照（施工首轮，已删除该轮输出）：预热只给 `years=1`（覆盖 2023-10-04 起）而 T74 需要 2022-10-05 起，
结果首策略 6 个 trial 全部 `matrix_data_cache_hit=false`，prepare 合计 12,030.4ms、峰值 403.8MB——
这就是"预热没覆盖到等于没预热"的实测证据，也是现在加覆盖断言的原因。

12 个 trial 全部成功，结果（真实回测数字，**这些策略这两个区间都是亏的**）：

| trial | 策略 | 窗口 | 成本档 | 区间收益 | 最大回撤 | Sharpe | 交易数 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| t0001 | T74 3F 回踩 | IS | zero | -7.47% | -27.95% | -0.26 | 140 |
| t0002 | T74 3F 回踩 | IS | real | -10.76% | -29.63% | -0.42 | 141 |
| t0003 | T74 3F 回踩 | OOS | zero | -5.26% | -14.48% | -0.84 | 39 |
| t0004 | T74 3F 回踩 | OOS | real | -6.48% | -15.02% | -1.08 | 39 |
| t0005 | T74 3F 回踩 | ALL | zero | -19.81% | -39.49% | -0.41 | 267 |
| t0006 | T74 3F 回踩 | ALL | real | -25.83% | -42.64% | -0.59 | 269 |
| t0007 | 首板结构回攻 | IS | zero | -26.60% | -32.58% | -1.68 | 41 |
| t0008 | 首板结构回攻 | IS | real | -27.77% | -33.47% | -1.76 | 41 |
| t0009 | 首板结构回攻 | OOS | zero | -12.88% | -14.98% | -3.26 | 12 |
| t0010 | 首板结构回攻 | OOS | real | -13.26% | -15.34% | -3.36 | 12 |
| t0011 | 首板结构回攻 | ALL | zero | -45.32% | -47.43% | -1.74 | 87 |
| t0012 | 首板结构回攻 | ALL | real | -47.16% | -49.15% | -1.84 | 87 |

成本敏感度是这轮唯一稳定的信号：`zero → real` 在 T74/ALL 上吃掉约 6.0 个百分点，在首板/ALL 上约 1.8 个百分点。

多重检验：`n_trials=4`、EM 分别为 IS 0.842 / OOS 1.432 / ALL 0.789，12 个 trial 的 PSR 全为 0.0000、
BH q 全为 1.000——即在这 4 个决策单元的选择压力下，没有任何一个 Sharpe 能算显著。这正是底座要的效果：
它不会把"两个策略里挑一个不太差的"包装成结论。

## 5. 限制与未接入

- **跨策略共享同一份行情矩阵未实现**（只做到"预热 + 缓存命中 + 同策略多成本档共享"）。原因在
  `backend/app/backtest/strategy.py:1702` 与 `:1787`：`run` 校验
  `prepared.signature != self._matrix_prepare_signature(config)`，而 `_matrix_prepare_signature`
  （`:992`）把 `strategy_id` 算进签名，两处 `prepare_*`（`:1183`/`:1370`）也要求
  "optimizer trials must share strategy, universe, range and overrides"。**要跨策略共享必须改生产代码**，
  本轮按约束未动，方案见 §6。
- **panel 路径（`polars_expr`）未实测**：当前注册表里只有 2 条策略，后端都是 `matrix_native`，
  `prepare_panel_optimization` 分支写好了但没有任何策略能走到，属于"设计完成、未验证"。
- **`composite`/`minute_filter` 后端**走 `direct` 分支（每次独立 run，无共享装载），同样未实测。
- **PSR/DSR 的偏度/峰度按正态假设 (0,3) 代入**，因为轻量契约裁掉了净值曲线，拿不到真实高阶矩。
  registry 里每次 trial 的 `moment_source` 都标着 `assumed_normal(0,3)`；要精确值需要保留曲线
  （与"裁曲线"目标冲突），是明确的取舍而非疏漏。
- **标的池是吞吐量演示用的等距抽样**：200 只按代码排序等距取，且只包含参考日仍存续的标的，
  含存续偏差，**不能当作研究口径的股票池**。正式策略搜索要换成研究员给的池子并写进 spec。
- **预热按自然年对齐**（`formal_start = latest.year - years + 1`），粒度粗：本批 `years=3` 实际覆盖
  2021-10-03 起，比所需 2022-10-05 多一年（220MB 磁盘、20s 建缓存）。底座现在会算出所需年份并校验覆盖，
  但预热函数本身没有"按日期精确覆盖"的入口。
- **内存口径已修正**：早期版本只在标记点（prepare 前后、每个 trial 后）采样本进程 RSS，连续三次同规格运行分别报
  988.7 / 309.1 / 1056.9MB——差异来自采样点是否恰好压在 prepare 内部的瞬时尖峰上，不是真实的稳定占用。
  现改为以 Windows `peak_wset`（OS 记录的进程峰值工作集）为准，采样值只作为轨迹（`resource.marks`）。
  冷缓存那轮的 988.7MB 是旧口径，只能当参考。
- **冷/热对比不彻底**：两次运行之间没有清空 `D:\TSP\data\.backtest_matrix_cache`（那是全项目共享的缓存，
  删了会影响别人正在进行的工作），所以 23:54 那轮的 0.74s 是"缓存已存在"的真实数字，不是"清空后重建"的对照。
- **未做并发/多进程**：单进程顺序执行；`max_workers` 并行试算没接，所以本轮的耗时是串行口径。

## 6. 需要生产改动的部分（未改，仅提案）

要让「同切片 N 条策略只装载一次」成立，需要下列最小改动之一：

1. `backend/app/backtest/strategy.py:992` `_matrix_prepare_signature`：把 `strategy_id` 从签名里移出，
   改为单独的 `strategy_id` 字段在 `run` 里校验（`:1702`/`:1787` 两处比较随之拆分），
   并在 `:1202`/`:1385` 的"必须同策略"检查里加一条显式的"允许跨策略共享"开关参数。
2. 或者新增 `prepare_batch_optimization(configs_by_strategy)` → 用 `_merge_resolved_feature_plans`
   对多条策略的计划取并集装载一次矩阵，再为每条策略派生只读视图（`slice_market_data_matrix`）。

风险点：签名放宽后，`run` 里依赖 `prepared` 的掩码/`start_id/stop_id` 是**按首条策略**算的
（`prepare_matrix_optimization` 用 `configs[0]`），跨策略复用会把这些掩码错误地套到别的策略上，
所以第 1 条不够，必须走第 2 条派生视图。这也是本轮不擅自改生产代码的原因：改错了会静默污染所有回测数字。

## 7. 自检与静态检查

```
backend/.venv/Scripts/ruff.exe check research/strategy-harness-20261106/ --output-format concise
→ All checks passed!（整个目录，含 probe 脚本；用的是仓库自带 ruff 0.x + backend/pyproject.toml 配置）
backend/.venv/Scripts/python.exe research/strategy-harness-20261106/selftest.py → 退出码 0，8 项通过
（PSR 与 stats_v2 逐点一致、p 与 PSR 互补、EM 单调、BH q 单调/None 透传、
  折边界只在交易日且 IS/OOS 不重叠、轻量契约裁字段、optimizer_trial 保留 n_trades、规格校验）
```

注意：脚本必须用 `backend/.venv/Scripts/python.exe`（3.11 + polars/psutil）。直接用系统 Python 3.12
会 `ModuleNotFoundError: No module named 'polars'`，退出码 1——这不是脚本问题。

## 8. 边界

- 只新增 `research/strategy-harness-20261106/` 下的文件；`backend/`、`docs/`、`frontend/` 均未改动
  （`git status` 开工 71 行、收工 71 行，跟踪文件清单一致）。
- 未提交、未部署、未重启、未购买任何服务。
- 运行会往 `D:\TSP\data\backtest_runs\` 写一条 evidence 清单（与 app 同 `schema_version=1` 契约，
  `run_id` 为 16 位 hex），这是设计上的留档行为，不是源码改动。

## 9. done_when 逐条对照

| 要求 | 落点 | 证据 |
| --- | --- | --- |
| 实跑 ≥2 策略 × 2 成本档 | `specs/demo-2x2.json`（2 策略 × 2 档 × 3 窗口 = 12 trial） | `runs/demo-2x2-20261106T235432/run.log` 首行「策略 2 × 成本档 2 = 4 个决策单元」，末行「12 个 trial，失败 0」 |
| 命令与退出码 | `backend/.venv/Scripts/python.exe research/strategy-harness-20261106/batch_harness.py --spec research/strategy-harness-20261106/specs/demo-2x2.json` | 退出码 **0**；进程外墙钟 13.7s，内测 10.5s |
| 每次试验留痕（参数/成本档/panel 哈希/IS-OOS-ALL 指标） | `registry.json` / `registry.jsonl` 每个 trial 带 `params`、`overrides`、`cost`、`prepared_fingerprint.digest`、`window`、`metrics`、`significance` | `runs/demo-2x2-20261106T235432/registry.json`（52KB，12 条） |
| 运行日志 | `run.log`（逐 trial 一行：策略/窗口/档/收益/夏普/交易数/耗时） | 同目录 |
| 内存与耗时表现 | `resource.rss_peak_wset_mb` = 316.4MB；`sharing.prepare_ms_total` 5390.6ms / `run_ms_total` 3812.6ms | 见 §4 |
| 可复算 | 同一规格两次独立运行逐位相同（§4） | 12 trial × 10 指标 + 指纹 + PSR，差异 0 |
| 未接入/未验证部分 | §5 清单（跨策略共享、panel/direct 分支、高阶矩、股票池、并发） | — |
