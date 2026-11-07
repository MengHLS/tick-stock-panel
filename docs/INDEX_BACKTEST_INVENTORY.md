# 回测引擎 / 撮合成交模拟 / 结果存储 只读盘点

> 任务性质：只读盘点（不修改任何现有源码、不提交、不部署、不重启）。
> 生成时间：2026-11-06 22:48 (Asia/Shanghai)
> 生成人：系统开发工程师

## 步骤 1：仓库状态

| 项目 | 实测值 |
|---|---|
| 仓库路径 | `C:\work\sourcecode	ick-stock-panel`（存在） |
| 当前分支 | `dev` |
| HEAD 短哈希 | `848bd04b` |
| `git status --short` 输出行数 | **68 行** |
| 是否有未提交改动 | **有**：24 个已跟踪文件被修改，2 个已跟踪文件被删除（`backend/app/custom/industry_chain/service.py`、`frontend/src/custom/industry-chain/AnalysisPanel.tsx`），其余为未跟踪新文件 |

处置声明：本次**未**执行 `git reset` / `git stash` / `git checkout` / `git add` / `git commit`，工作区保持任务开始前的原样。

与回测相关的已修改文件（`git status --short` 实测）：
- `backend/app/api/backtest.py`
- `backend/app/backtest/engine.py`
- `backend/app/backtest/strategy.py`
- `backend/app/backtest/walkforward.py`
- `backend/tests/backtest/test_walkforward.py` 等测试文件

> 备注：仓库根存在一个异常命名的未跟踪文件（文件名形如 `=.5,sum(1 for r in rows if r.get(windows,{}).get(3d,{}).get(closeness,0)...`），系此前命令误写产物。本次仅记录，未删除（删除不属于本次授权的写操作）。

---
## 步骤 2：三块功能的文件定位（仅路径 + 行数，未读全文）

定位方式：`find backend/app -type f -name '*.py'` 目录列举 + 文件名/顶层定义 `grep -n` 定位；行数为 `wc -l` 实测值。

### 2.1 回测引擎（信号→持仓→净值的逐日主循环）

| 文件 | 行数 | 判定依据 |
|---|---|---|
| `backend/app/backtest/engine.py` | 5670 | 定义 `class BacktestEngine`（engine.py:652）、`MatcherConfig`（226）、`SimResult`（441）；主循环与撮合均在此文件 |
| `backend/app/backtest/matrix.py` | 4735 | 行情矩阵装载/对齐（engine.py 顶部 import `MarketMatrix`） |
| `backend/app/backtest/strategy.py` | 3909 | 策略协议与信号产出 |
| `backend/app/backtest/walkforward.py` | 890 | 滚动/前推编排，多次调用引擎 |
| `backend/app/backtest/worker.py` | 471 | 子进程执行单次回测 |

### 2.2 撮合 / 成交模拟

| 文件 | 行数 | 判定依据 |
|---|---|---|
| `backend/app/backtest/engine.py` | 5670 | 撮合主实现：`MatcherConfig`（226）、`ExecutionCostPolicy`（184）、`FullExecutionCapabilities`（357）、`TradeRecord`（412）、`_resolve_signal_id`（482）、`PanelCache`（525） |
| `backend/app/backtest/execution_policy.py` | 497 | 撮合参数解析/校验：`ExecutionPolicy`（64）、`parse_backtest_defaults`（102） |
| `backend/app/backtest/minute_replay.py` | 330 | 分钟级重放 |
| `backend/app/backtest/minute_trigger.py` | 68 | 分钟级触发 |
| `backend/app/backtest/position_policies.py` | 395 | 仓位/持仓政策 |
| `backend/app/backtest/position_sizing.py` | 195 | 头寸规模 |

### 2.3 结果存储

| 文件 | 行数 | 判定依据 |
|---|---|---|
| `backend/app/backtest/result_store.py` | 507 | `save_completed_result`（393）、`list_saved_results`（451）、`get_saved_result`（485）、`delete_saved_result`（499）、`CompletedRunCache`（105） |
| `backend/app/backtest/result_read.py` | 28 | 结果读取薄壳 |
| `backend/app/backtest/read.py` | 47 | 只读数据适配器 `BacktestReadAdapter`（10） |
| `backend/app/api/backtest.py` | 1594 | HTTP 层（含保存/列表/删除路由） |
| `backend/app/services/backtest.py` | 440 | 服务层编排 |

---
## 步骤 3：入口文件对外接口签名与关键配置项

> 提取方式：`ast` 解析取 `def`/`class` 的 `lineno` 与签名（未读实现体），行号为实测。

### 3.1 `backend/app/backtest/engine.py`（回测引擎 + 撮合，5670 行）

#### 类 `BacktestEngine`（engine.py:652）

| 行号 | 签名 |
|---|---|
| 655 | `__init__(self, repo: KlineRepository) -> None` |
| 662 | `data_generation(self, asset_type: str = 'stock') -> str \| None` |
| 671 | `data_generation_await(self, asset_type: str = 'stock', *, cancel_event: threading.Event \| None = None, timeout_s: float = _GENERATION_WAIT_TIMEOUT_S) -> str \| None` |
| 694 | `assert_data_generation(self, asset_type: str, expected: str \| None) -> None` |
| 718 | `load_panel(self, symbols, start: date, end: date, columns=None, asset_type='stock', *, expected_generation=None) -> pl.DataFrame` |
| 763 | `load_panel_for_backtest(self, symbols, start, end, feature_plan, asset_type='stock', *, _linkage_generation=None, _linkage_retry=0, evidence=None) -> pl.DataFrame` |
| 954 | `load_market_data_matrix_for_backtest(self, symbols, start, end, feature_plan, asset_type='stock', *, cache_profile=None, coverage_start=None, coverage_end=None, expected_generation=None, cancel_event=None) -> MarketDataMatrix` |
| 1225 | `simulate(self, panel: pl.DataFrame, entries, exits, config: MatcherConfig, entry_signal_ids=None, exit_signal_ids=None) -> SimResult` |
| 1362 | `simulate_independent_candidates(self, panel, entries, exits, config: MatcherConfig, progress_cb=None, cancel_event=None, entry_signal_ids=None, exit_signal_ids=None) -> SimResult` |
| 1923 | `simulate_independent_market_matrix(self, matrix: MarketMatrix, raw_candidates: int, config: MatcherConfig, progress_cb=None, cancel_event=None, options: SimulationOptions \| None = None) -> SimResult` |
| 1938 | `simulate_independent_candidates_legacy(self, panel, entries, exits, config: MatcherConfig, ...) -> SimResult` |
| 2514 | `simulate_portfolio(self, panel, entries, exits, config: MatcherConfig, progress_cb=None, cancel_event=None, entry_signal_ids=None, exit_signal_ids=None) -> SimResult` |
| 2543 | `simulate_market_matrix(self, matrix: MarketMatrix, config: MatcherConfig, progress_cb=None, cancel_event=None, options: SimulationOptions \| None = None) -> SimResult` |
| 4484 | `simulate_portfolio_legacy(self, panel, entries, exits, config: MatcherConfig, ...) -> SimResult` |
| 5330 | `_calc_stats(trades: list[TradeRecord], initial_capital: float, start: date, end: date, *, include_monte_carlo: bool = True) -> dict` |
| 5444 | `_calc_independent_candidate_result(trades, n_candidates: int, execution_stats: dict[str, int], *, options=None) -> SimResult` |
| 5227 | `_build_curves(trades: list[TradeRecord], all_dates: np.ndarray, initial_capital: float) -> tuple[list[dict], list[dict]]` |
| 2372 | `_resolve_minute_fill(minute_arr: np.ndarray, ref_price: float \| None, side: str) -> float \| None` |
| 2429 | `_resolve_minute_exit_trigger(minute_arr: np.ndarray, ref_price: float \| None) -> float \| None` |

#### 数据结构（engine.py）

| 类 | 行号 | 关键字段（实测） |
|---|---|---|
| `HoldExtensionPolicy` | 163 | `decision_days=5`、`strong_hold_days=10`、`strong_hold_min_return=0.03`、`runner_new_high_days=3`、`runner_extend_days=74` |
| `ExecutionCostPolicy` | 184 | `min_commission=0.0`、`transfer_fee_pct=0.0`、`buy_slippage_tiers=()`、`price_decimals=4`；方法 `fees(gross, commission_pct, stamp_pct=0.0) -> float`（205）、`fill_price(price, side, base_bps, amount=None) -> float`（211） |
| `MatcherConfig` | 226 | `matching='close_t'`、`entry_fill`、`exit_fill`（含 `signal_next_minute`）、`fees_pct=0.0002`、`commission_pct`、`stamp_tax_pct`、`slippage_bps=5.0`、`stop_loss_pct`、`take_profit_pct`、`trailing_stop_pct`、`trailing_take_profit_activate_pct`、`trailing_take_profit_drawdown_pct`、`max_hold_days`、`max_positions=10`、`max_exposure_pct=1.0`、`score_min`/`score_max`、`initial_capital=1000000.0`、`position_sizing='equal'`、`score_tiers`、`entry_open_gap_range`、`entry_prev_day_change_range`、`trailing_peak_price='high'`、`exit_signal_requires_profit=False`、`hold_extension_policy`、`max_daily_entries`、`plan_at_signal_close=False`、`entry_price_basis='adjusted'`、`block_limit_open=False`、`allow_same_asset_positions=False`、`finalize_open_at_end=False`、`corporate_action_unavailable`、`execution_costs`、`cost_model`、`position_policy_compute`、`position_policy_params`、`minute_fill=False`、`asset_type='stock'` |
| `FullExecutionCapabilities` | 357 | 与 `MatcherConfig` 同名的 11 项能力白名单（`exit_signal_requires_profit` 至 `finalize_open_at_end`）；`validate_full_execution_support(config: MatcherConfig) -> None`（404）拒绝不支持组合 |
| `TradeRecord` | 412 | `symbol`、`entry_date`、`exit_date`、`entry_price`、`exit_price`、`pnl_pct`、`duration`、`exit_reason`、`name`、`shares`、`lots`、`position_pct`、`entry_value`、`exit_value`、`pnl_amount`、`entry_score`、`entry_signal_date`、`exit_signal_date`、`blocked_exit_days`、`open_at_end`、`entry_signal_id`、`exit_signal_id`（**无费用/滑点字段**） |
| `SimResult` | 441 | `equity_curve`、`drawdown_curve`、`trades`、`per_symbol_stats`、`stats`、`carry_state`（**无 run_id/config/provenance**） |
| `PortfolioCarryState` | 452 | `cash`、`peak`、`positions`、`pending_buy_plans`、`last_close` |
| `SimulationOptions` | 468 | `include_monte_carlo=True`、`include_curves=True`、`include_trades=True`、`include_per_symbol_stats=True`、`include_return_distribution=True`、`carry_in`、`carry_out=False` |

### 3.2 `backend/app/backtest/execution_policy.py`（撮合参数解析，497 行）

| 行号 | 接口 / 配置 |
|---|---|
| 64 | `class ExecutionPolicy`：`schema_version`、`legacy`、`score_tiers`、`entry_open_gap_range`、`entry_prev_day_change_range`、`trailing_peak_price='high'`、`exit_signal_requires_profit=False`、`hold_extension_policy`、`execution_costs`、`plan_at_signal_close=False`、`max_daily_entries`、`entry_price_basis='adjusted'`、`block_limit_open=False`、`allow_same_asset_positions=False`、`finalize_open_at_end=False` |
| 102 | `parse_backtest_defaults(raw: object, *, context: str = 'strategy') -> ExecutionPolicy` |
| 59 | `class BacktestDefaultsError(ValueError)` |
| 219 | `_schema_version(payload: dict, *, legacy: bool, context: str) -> int` |
| 235 | `_validate_base_fields(payload: dict, *, context: str) -> None` |

### 3.3 `backend/app/backtest/result_store.py`（结果存储，507 行）

| 行号 | 接口 |
|---|---|
| 393 | `save_completed_result(data_dir, *, run_id: str, name: str \| None = None) -> dict` |
| 451 | `list_saved_results(data_dir, *, page: int = 1, page_size: int = 20) -> dict` |
| 485 | `get_saved_result(data_dir, saved_id: str) -> dict` |
| 499 | `delete_saved_result(data_dir, saved_id: str) -> None` |
| 209 | `register_completed_run(result: Any) -> str \| None` |
| 227 | `get_completed_run(run_id: str) -> dict \| None` |
| 231 | `get_run_rejection(run_id: str) -> str \| None` |
| 236 | `clear_completed_runs() -> None` |
| 240 | `results_dir(data_dir: str \| Path) -> Path` |
| 255 | `summarize_record(record: dict) -> dict` |
| 105 | `class CompletedRunCache`：`__init__(*, ttl_seconds, max_entries, max_bytes, max_entry_bytes)`；`register(result)`（125）、`rejection_reason(run_id)`（158）、`get(run_id)`（165）、`clear()`（175） |
| 326 | `_build_record(result: dict, *, saved_id: str, name: str \| None) -> dict` |
| 357 | `_atomic_create(path: Path, payload: dict) -> bool`（临时文件 + fsync + `os.link` create-if-absent） |
| 58/62/66/70/74/78/82/86 | 异常类：`ResultStoreError`、`RunResultExpiredError`、`RunResultNotSavableError`、`SavedResultNotFoundError`、`SavedResultCorruptError`、`UnsupportedResultSchemaError`、`SavedResultLimitExceededError`、`InvalidSavedIdError` |

### 3.4 衔接层（为步骤 4 的调用链取证）

| 位置 | 接口 |
|---|---|
| `backend/app/backtest/strategy.py:709` | `class StrategyBacktestConfig`：`strategy_id`、`symbols`、`start`、`end`、`params`、`overrides`、`matching='open_t+1'`、`entry_fill`、`exit_fill`、`fees_pct=0.0002`、`commission_pct`、`stamp_tax_pct`、`slippage_bps=5.0`、`max_positions=10`、`max_exposure_pct=1.0`、`initial_capital=1000000.0`、`position_sizing='equal'`、`position_policy`、`position_policy_params`、`mode='position'/'full'`、`asset_type='stock'`、`holding_days=5`、`minute_fill=False`、`regime_filter`、`carry_state`、`carry_out=False` |
| `backend/app/backtest/strategy.py:775` | `class StrategyBacktestResult`：`run_id`、`config`、`stats`、`equity_curve`、`drawdown_curve`、`benchmark_curve`、`trades`、`per_symbol_stats`、`strategy_info`、`factor_attribution`、`elapsed_ms`、`error`、`provenance`、`evidence`、`carry_state` |
| `backend/app/backtest/strategy.py:982` | `StrategyBacktestService.__init__(engine: BacktestEngine, strategy_engine: StrategyEngine)`；`run_with_evidence(config, progress_cb=None, cancel_event=None) -> StrategyBacktestResult`（1470）；`run(...) -> StrategyBacktestResult`（1504）；`prepare_matrix_optimization(configs, *, matrix_cache_max_bytes=512MiB, market_data_override=None) -> PreparedMatrixBacktest`（1183） |
| `backend/app/backtest/strategy.py:3636` | `_trade_to_dict(t) -> dict`（21 个字段，无费用字段） |
| `backend/app/backtest/strategy.py:3662` | `_build_run_provenance(...) -> dict`：`algorithm_version='strategy_backtest_v2'`、`app_version`、`strategy{...}`、`run{...}`、`params`、`filters`、`scoring`、`execution{...}`、`data{frozen=False, generation, generation_source, coverage, note}`（3774-3788） |
| `backend/app/backtest/worker.py:171/336/215` | `make_worker_task(kind, data_dir: Path, config) -> dict[str, Any]`、`run_worker_task(task, progress_cb=None, cancel_event=None) -> dict[str, Any]`、`_worker_entry(...)`；`asdict(service.run_with_evidence(...))`（worker.py:254） |
| `backend/app/api/backtest.py:412/514/527/540/551` | `POST /strategy/run`、`POST /strategy/results`、`GET /strategy/results`、`GET /strategy/results/{saved_id}`、`DELETE /strategy/results/{saved_id}` |

---

## 步骤 4：三块之间的调用关系与缺失契约

> 下列“事实”均来自上文的 `grep -n` / 定向 `sed -n` 读取；未读到的部分明确写“未知”。

### 4.1 现有调用链（实测行号）

1. `backend/app/api/backtest.py:412` `POST /strategy/run`（函数体 413-467）
   → 构造 `StrategyBacktestConfig`（433-458）
   → `make_worker_task("backtest", data_dir, cfg)`（459）
   → `run_worker_task(task)`（465）
2. `backend/app/backtest/worker.py:336` `run_worker_task` → `_worker_entry`（215）
   → `StrategyBacktestService(BacktestEngine(repo), strategy_engine)`（246）
   → `asdict(service.run_with_evidence(...))`（254）— **此处才把 dataclass 转 dict**
3. `backend/app/backtest/strategy.py:1470` `run_with_evidence` → `run`（1504）
   → `engine.simulate_independent_market_matrix(...)`（2296，`mode == "full"`）
   → `engine.simulate_market_matrix(...)`（2305，其余模式）
   → 分钟路径：`engine.simulate_*_market_matrix`（2682 / 2691，位于 `_run_minute_backtest` 2427-2799）
4. 引擎返回 `SimResult`（engine.py:441）→ 被包装为 `StrategyBacktestResult`（strategy.py:775，含 `run_id`/`config`/`strategy_info`/`provenance`）
   → 逐笔经 `_trade_to_dict`（3636）转 dict；配置溯源经 `_build_run_provenance`（3662）生成
5. 回到 API：`_register_completed_strategy_result(result)`（api/backtest.py:466，函数定义 402-409）
   → `register_completed_run(result)`（result_store.py:209）
   → `_CACHE.register(stored)`（206 模块级单例；`completed_at` 在 222 用 `setdefault` 固定）
6. 保存：`POST /strategy/results`（api/backtest.py:514）
   → `save_completed_result(data_dir, run_id=..., name=...)`（result_store.py:393）
   → `_find_by_run_id` 幂等查重（418-420）→ `get_completed_run(run_id)`（421，读内存缓存）
   → `_build_record`（440，定义 326）→ `_atomic_create`（441，定义 357，写 JSON 到 `results_dir`，定义 240）
7. 读取 / 删除：`GET /strategy/results`（527）→ `list_saved_results`（451）；`GET /strategy/results/{saved_id}`（540）→ `get_saved_result`（485）；`DELETE`（551）→ `delete_saved_result`（499）
8. 只读旁路：`backend/app/backtest/result_read.py:17` → `list_saved_results`；`:24` → `get_saved_result`（供扩展读取，不参与写入）

### 4.2 缺失契约（只列实际观察到的缺口）

| # | 缺口 | 证据（路径:行号） | 影响 |
|---|---|---|---|
| C1 | `SimResult` 不含 `run_id` / `config` / `strategy_info` / `provenance` / `completed_at`，无法直接落盘 | `backend/app/backtest/engine.py:441-449`；`backend/app/backtest/result_store.py:215-224`（登记要求 dict 且 `run_id` 非空） | 直接调用引擎的调用方（含未来批量回测）必须自行补齐这 5 类字段，否则结果无法保存 |
| C2 | 逐笔成交记录无费用/滑点字段 | `engine.py:412-439`（TradeRecord 字段清单）、`engine.py:205-209`（费用算法）、`engine.py:2825`（`policy.fees(...)` 唯一调用点）、`strategy.py:3636-3660`（`_trade_to_dict` 21 字段无 fee/slippage） | 费用只并入现金/成交价，结果中无法按笔复核成本，研究侧无法做成本归因 |
| C3 | `run_id → 完整结果` 的暂存只在进程内存，且有界 | `result_store.py:206`（`_CACHE = CompletedRunCache()`）、`105-124`（TTL / 条数 / 字节上限）、`408-411` 与 `422-434`（取不到即抛 `RunResultExpiredError`） | 进程重启或缓存淘汰后，已完成的 run 不能再保存，只报“已过期”；缺持久化暂存契约 |
| C4 | 登记失败是静默的（返回 `None`，不抛错） | `result_store.py:125-132`（非 dict / 有 `error` / 无 `run_id` 直接 return None）、`api/backtest.py:402-409`（捕获异常只记日志） | 传错类型或字段缺失时无人感知，用户只在“保存”时看到 410 |
| C5 | 存储记录 `meta` 只有 6 个固定字段，数据版本不强制 | `result_store.py:344-351`；数据版本仅 `strategy.py:3774-3788` 的 `provenance.data.generation`（允许 null，`frozen=False`） | 存储层不能强制“同名结果可对比”：文件层面看不出数据版本是否一致 |
| C6 | 同一撮合语义三处定义，且存在反向依赖 | `engine.py:226`（MatcherConfig）、`engine.py:357`（FullExecutionCapabilities）、`execution_policy.py:64`（ExecutionPolicy）；`execution_policy.py:14` 从 `engine` 导入 `ExecutionCostPolicy`/`HoldExtensionPolicy` | 新增撮合项需同步改三处，漏改会被 `validate_full_execution_support`（engine.py:404）拒绝或静默不生效 |
| C7 | 其它产结果路径的落盘方式 | `walkforward.py`、`matrix.py`、`mining_runtime.py` 本轮**未读** | **未知**：是否各自另行落盘、是否复用 `result_store`，未核实 |

---
## 步骤 5：下一步建议的 3 个最小改动点

> 仅建议，本轮**未改动任何源码**。

| # | 改动点 | 最小实施范围 | 对应缺口 | 为什么算“最小” |
|---|---|---|---|---|
| M1 | 逐笔成本落库 | `engine.py:412`（`TradeRecord` 增 `fee_amount`、`slippage_bps_effective`，默认 0.0，保持字段顺序在末尾）+ `engine.py:2825` 处把已算出的费用写入该笔 + `strategy.py:3636`（`_trade_to_dict` 增同名字段） | C2 | 纯增字段、不改撮合与净值算法；既有读端忽略新键，属向后兼容 |
| M2 | 登记失败显式化 | `result_store.py:125-132`：非 dict / `run_id` 缺失时抛出已有 `RunResultNotSavableError`（而非 `return None`）；`api/backtest.py:402-409` 保持捕获但记录原因 | C4、C3 的可观测面 | 只改返回值语义与日志，不动缓存结构与保存流程；需同步 2 个既有测试断言 |
| M3 | 存储层固定数据版本字段 | `result_store.py:344-351` 的 `meta` 增 `data_generation`（从 `result["provenance"]["data"]["generation"]` 取值，缺失写 `null`） | C5 | 只加一个只读派生字段，不改 `result` 主体、不改 schema 版本号；缺失即 null 不报错 |

不建议在本轮做（超出最小范围）：把 C3 的内存缓存换成持久化暂存（涉及文件布局与清理策略）、把 C6 的三处配置收敛成单一来源（涉及策略元数据兼容）。

## 附：本次盘点的方法与限制

- 使用的命令均为只读：`git rev-parse`、`git status --short`、`find`、`wc -l`、`grep -n`、`sed -n`、`python -c/ast` 解析。
- 未执行：`git reset` / `git stash` / `git checkout` / `git add` / `git commit`；未运行测试、未启动服务、未改任何 `.py` 文件。
- 行号基于当前工作区（含未提交修改），HEAD 为 `848bd04b`；若他人随后改动上述文件，行号需重新核对。
- `matrix.py`（4735 行）、`mining_runtime.py`（1853 行）、`walkforward.py`（890 行）的落盘行为未读，结论为“未知”，未做推测。

## 附二：盘点期间的并发变更（如实记录）

- 盘点开始时 `git status --short` 为 **68 行**；结束时为 **70 行**，新增两项：
  1. 本文件 `docs/INDEX_BACKTEST_INVENTORY.md`（本次交付，唯一由本人新增的文件）；
  2. `research/batch-backtest-framework-20261107/`（**非本人创建**，同一工作区其他任务并行产出）。
- `find -newermt '-15 minutes'` 显示 `backend/app/api/backtest.py`、`backend/app/backtest/engine.py`、`backend/tests/backtest/test_walkforward.py`、`backend/tests/backtest/test_worker_process.py` 等在盘点窗口内仍被其他任务改动 → **本文行号可能随后漂移**，引用前请以 `grep -n` 复核。
- 本人未修改、未回滚上述任何他人文件。
