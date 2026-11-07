# 策略批量评估工程底座 — 进度记录

## 步骤 1（只读盘查）
- 项目路径：C:\work\sourcecode\tick-stock-panel，分支 dev。
- git 状态：有大量未提交修改（backend/app/backtest/{engine,strategy,walkforward}.py 等）与未跟踪目录（parallel-*、program-planning、document-management、research/wyckoff-*）。
- 已存在未跟踪的 `backend/app/custom/strategy_research/` + `scripts/strategy_research.py`（T74 基线/路径诊断/受控变体），属研究诊断用途，不含多策略参数扫描。
- 结论：需要新增独立批跑模块，不修改既有页面/API 行为，不碰他人目录。

## 步骤 2（现有回测基建盘点）
- `backend/app/backtest/engine.py`：`MatcherConfig` 已含成本口径（fees_pct/commission_pct/stamp_tax_pct/slippage_bps/execution_costs），且矩阵与面板两条撮合路径已统一处理停牌不可成交、涨停买不到/跌停卖不出（buy_suspended / buy_limit_up / sell_suspended / sell_limit_down 计入 execution_stats）。
- `backend/app/backtest/strategy.py`：`StrategyBacktestConfig` → `StrategyBacktestService.run()`；`provenance` 已记录 app_version、策略定义 sha256、有效执行参数、data generation（装载窗口内前后校验一致才绑定）。
- `backend/app/backtest/optimizer.py`：`OptimizeConfig` + `StrategyOptimizer.optimize()` 已支持单策略参数网格并行 + 共享矩阵。
- `backend/app/backtest/robust_optimizer.py` / `walkforward.py`：分段稳健优化与滚动样本外。均只接受单策略 config。
- `strategy/engine.py`：`StrategyEngine(strategy_dirs=...)` + `list_strategies(include_research=True)` / `resolve_params()` 提供注册表与参数元数据。
- 结论：撮合与成本无需重写；缺的是「多策略 × 多参数组」统一编排 + 统一成本假设的单一来源 + 全量试验台账（含数据版本）+ as-of 校验。

## 步骤 3（5 个改动点落地 — 新增独立脚本）
- 只新增 `research/strategy-harness-20261106/`，未改 `backend/`。
- 点 1 结果契约：`LIGHT_POLICY` 强制传入 `service.run`；实测 `stats` 里无曲线的 6 个键（键缺失，不是空值）。
- 点 2 共享装载：`prepare_matrix_optimization(configs=[全部成本档])` 每 (策略,窗口) 只做一次；批次头 `build_matrix_cache_profile` + `prewarm_matrix_cache`，并断言预热起点覆盖「窗口起点 − 预热天数」，不覆盖就 WARN 并给出所需年份。
- 点 3 折边界：`list_enriched_dates` + `generate_folds(trading_days=days)`，4 个边界逐个断言在交易日集合内。
- 点 4 指标与多重检验：只取组合账户口径 `COMPARABLE_STATS`；`deflated_sharpe_psr` 接线，`expected_max_sharpe(n_trials, 方差)` 作 EM，再 `bh_fdr_qvalues`；PSR 与 `stats_v2` 不一致即 AssertionError。
- 点 5 留痕：`data_generation` 前后校验 + 每份 prepared 内容指纹（矩阵/面板两种），逐 trial 写入 registry 与 evidence。

## 步骤 4（实跑 2 策略 × 2 成本档）
- 规格 `specs/demo-2x2.json`：2025-01-02..2026-11-06（446 交易日），fold#0，IS/OOS/ALL 三窗口 = 12 个 trial。
- 冷缓存首轮 29.9s（预热 20.45s，需建 220,637,952 B）；缓存已存在 10.5s（预热 0.74s）。
- 12/12 成功、退出码 0、`data_generation` 前后一致。

## 步骤 5（质量门）
- `ruff check research/strategy-harness-20261106/` → All checks passed（首轮 19 处违规已修）。
- `selftest.py` → 退出码 0，8 项通过。注意必须用 `backend/.venv/Scripts/python.exe`（系统 3.12 无 polars）。

## 步骤 6（内存口径修正）
- 发现标记点采样不稳定：同规格三次运行分别 988.7 / 309.1 / 1056.9MB。
- 改为 OS `peak_wset` 为准 + 采样轨迹并存；最终版实测 316.4MB。

## 步骤 7（可复现性对照）
- 23:47 与 23:54 两次独立进程、缓存状态不同：12 个 trial × 10 个指标 + 指纹 + PSR 逐位相同（差异 0）。
- 清理：删除 3 个中间试验目录及其 `D:\TSP\data\backtest_runs` 证据记录，只保留冷/热两次；他人 3 条证据记录未动。
