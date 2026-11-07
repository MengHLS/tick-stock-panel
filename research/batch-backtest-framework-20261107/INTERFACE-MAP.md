# 批量策略评估 — 可复用接口地图

- 仓库：`C:\work\sourcecode\tick-stock-panel`（分支 `dev`，HEAD `848bd04b`）
- 生成时间：2026-11-06 22:5x（Asia/Shanghai）
- 依据：只读源码；行号为当前工作区（含未提交修改）实际行号，于 2026-11-06 22:5x 逐行 re-grep 校验，未运行任何回测
- ⚠ 并发提醒：调查期间 `backend/app/backtest/engine.py` 被其他成员修改过（mtime 22:47:36，文件从 268,504 → 268,802 字节），本表行号已按修改后版本校正；开工前请重新 `grep -n` 核对，不要直接复用本表行号做 patch
- 口径说明：路径均相对仓库根；「可直接复用」= 无需改源码即可调用；「需适配」= 能力存在但入口/前置条件/私有性使其不能直接用于批量编排

## 1. 接口表

| 能力名 | 函数/类名 | 文件路径:行号 | 入参 | 返回 | 是否可直接复用或需适配 |
|---|---|---|---|---|---|
| 单策略回测入口（服务层，正式路径） | `StrategyBacktestService.run` | `backend/app/backtest/strategy.py:1504` | `config: StrategyBacktestConfig`；`progress_cb: Callable[[dict], None] \| None`；`cancel_event: threading.Event \| None`；`prepared: PreparedMatrixBacktest \| None`；`result_policy: BacktestResultPolicy \| None`；`prepared_panel: PreparedPanelBacktest \| None`；`evidence=None` | `StrategyBacktestResult`（`stats`/`equity_curve`/`drawdown_curve`/`trades`/`per_symbol_stats`/`provenance`/`carry_state`/`error`） | 可直接复用（需自建 `BacktestEngine(repo)` 与 `StrategyEngine`，参考 `backend/app/backtest/worker.py:246`） |
| 单策略回测配置对象 | `StrategyBacktestConfig` | `backend/app/backtest/strategy.py:709` | 字段：`strategy_id`、`symbols`、`start`、`end`、`params`、`overrides`、`matching`/`entry_fill`/`exit_fill`、`fees_pct`/`commission_pct`/`stamp_tax_pct`/`slippage_bps`、`max_positions`、`max_exposure_pct`、`initial_capital`、`position_sizing`、`position_policy(_params)`、`mode`、`asset_type`、`holding_days`、`minute_fill`、`regime_filter`、`carry_state`、`carry_out` | 配置实例 | 可直接复用 |
| 单策略回测入口（HTTP） | `strategy_run`（`POST /api/backtest/strategy/run`） | `backend/app/api/backtest.py:413` | `StrategyBacktestRequest`（同配置字段 + `request`） | 结果 dict（已 `_stamp_daily_data`） | 需适配：批量不宜走 HTTP（请求级限流、job 互斥、cookie 鉴权），应直调服务层 |
| 回测进程隔离封装 | `make_worker_task` / `run_worker_task` | `backend/app/backtest/worker.py:171` / `:336` | `(kind: str, data_dir: Path, config)` / `(task: dict)` | 可序列化 task dict / 结果 dict | 可直接复用（批量需要每任务独立进程；但它是「单任务一进程」，批量编排需外层调度） |
| 交易日历（生产口径） | `KlineRepository.list_enriched_dates` | `backend/app/tickflow/repository.py:2587` | `(start: date, end: date, asset_type: str = "stock")` | `list[date]`（有完整 enriched 分区的市场日） | 可直接复用；这是 WFO 生产路径唯一使用的历史交易日来源 |
| 交易日解析（WFO 内部） | `WalkForwardService._resolve_trading_days` | `backend/app/backtest/walkforward.py:270` | `cfg: WalkForwardConfig` | `list[date]`（`cfg.trading_days` 优先，否则 `repo.list_enriched_dates`） | 需适配：私有方法；批量应复制其逻辑或外部先算好 `trading_days` 传入 |
| 「今天是否交易日」探针 | `is_trading_day` | `backend/app/services/trading_day.py:112` | `now: datetime \| None = None` | `bool \| None`（None=未知） | 不可直接复用：只判断当天（周末直判 + fuyao/tickflow 探测），不能给出历史区间交易日 |
| 独立交易日历表/查询接口 | 未找到 | — | — | — | 未找到：仓库没有 calendar 表或 `get_trade_dates()` 类接口；历史交易日只能由 enriched 分区反推（`list_enriched_dates`）或 fuyao 插件 `backend/app/plugins/fuyao/client.py:232 trading_days()` |
| 行情面板装载（enriched，带缓存/世代校验） | `BacktestEngine.load_panel` | `backend/app/backtest/engine.py:718` | `(symbols: list[str] \| None, start: date, end: date, columns: list[str] \| None = None, asset_type: str = "stock", *, expected_generation: str \| None = None)` | `pl.DataFrame` | 可直接复用（`PanelCache` 跨调用生效；批量同参可命中缓存） |
| 回测特征面板装载（按依赖裁剪） | `BacktestEngine.load_panel_for_backtest` | `backend/app/backtest/engine.py:763` | `(symbols, start, end, feature_plan, asset_type="stock", *, _linkage_generation=None, _linkage_retry=0, evidence=None)` | `pl.DataFrame`（含策略所需特征列） | 可直接复用 |
| 单股日 K 读取 | `KlineRepository.get_daily` | `backend/app/tickflow/repository.py:1919` | `(symbol: str, start: date, end: date, columns: list[str] \| None = None)` | `pl.DataFrame` | 可直接复用（列下推快路径；缺列回退完整 enriched 计算） |
| 多股日 K 读取 | `KlineRepository.get_daily_batch` | `backend/app/tickflow/repository.py:1991` | `(symbols: list[str], start: date, end: date, columns: list[str] \| None = None)` | `pl.DataFrame` | 可直接复用 |
| enriched 区间读取（缓存） | `KlineRepository.get_enriched_range` | `backend/app/tickflow/repository.py:1701` | `(start: date, end: date, symbols: list[str] \| None = None, columns: list[str] \| None = None)` | `pl.DataFrame \| None`（缓存不覆盖时 None） | 需适配：None 必须回退到 `get_daily_batch`/逐日读取，批量不能把 None 当空结果 |
| enriched 按日期精确读取 | `KlineRepository.get_enriched_by_dates` | `backend/app/tickflow/repository.py:2037` | `(symbols: list[str], dates: list[date], asset_type: str = "stock", columns: list[str] \| None = None)` | `pl.DataFrame` | 可直接复用（适合按 fold 测试区间取数，避免全历史扫描） |
| 最新日 enriched（缓存） | `KlineRepository.get_enriched_latest` | `backend/app/tickflow/repository.py:1628` | `(*, symbols=None, end=None)` | `(pl.DataFrame, date \| None)`；预热期返回空表 | 需适配：批量历史评估不应依赖「最新日」缓存 |
| 分钟 K 读取（精确成交用） | `KlineRepository.get_minute` | `backend/app/tickflow/repository.py:2175` | `(symbol: str, trade_date: date, asset_type: str = "stock")` | `pl.DataFrame` | 需适配：仅 `minute_fill=True` 时需要，且按资产类型路由分区 |
| 复权因子读取（严格） | `load_adj_factors_strict` | `backend/app/indicators/price_quality.py:35` | `(factor_path: str \| Path, *, symbols: list[str] \| None = None)` | `pl.DataFrame`（`symbol, trade_date, ex_factor`；缺失即抛 `FactorDataError`） | 可直接复用 |
| 前复权计算 | `_apply_adj_factor` | `backend/app/indicators/pipeline.py:251` | `(raw: pl.DataFrame, factors: pl.DataFrame)` | 前复权 `pl.DataFrame` | 可直接复用，但只用于原始 K 线：enriched 的 `close` 已是前复权（`raw_close` 为原始价），重复应用会二次复权 |
| 复权因子视图（DuckDB） | `adj_factor` view 注册 | `backend/app/tickflow/repository.py:304` | SQL：`SELECT * FROM read_parquet('{data_dir}/adj_factor/**/*.parquet', union_by_name=true)` | `symbol, trade_date, ex_factor` 行集 | 可直接复用（经 `repo.execute_all`）；无 Python 级封装 |
| 按 (symbol, date) 查复权因子的仓库方法 | 未找到 | — | — | — | 未找到：只能用 `adj_factor` 视图自写 SQL 或 `load_adj_factors_strict` 读 parquet |
| 撮合配置（成本/成交口径/风控） | `MatcherConfig` | `backend/app/backtest/engine.py:226` | 字段：`matching`/`entry_fill`/`exit_fill`、`fees_pct`、`commission_pct`、`stamp_tax_pct`、`slippage_bps`、`stop_loss_pct`/`take_profit_pct`/`trailing_*`、`max_hold_days`、`max_positions`、`max_exposure_pct`、`initial_capital`、`position_sizing`、`entry_*_range`、`block_limit_open`、`execution_costs`、`cost_model`、`minute_fill`、`asset_type` 等 | 配置实例（`__post_init__` 校验并解析 entry/exit 口径） | 可直接复用 |
| 现金费用与滑点策略 | `ExecutionCostPolicy` | `backend/app/backtest/engine.py:184` | `min_commission`、`transfer_fee_pct`、`buy_slippage_tiers: tuple[tuple[amount, bps], ...]`、`price_decimals`；方法 `fees(gross, commission_pct, stamp_pct)`、`fill_price(price, side, base_bps, amount=None)` | `fees()→float`；`fill_price()→float`（四舍五入到 `price_decimals`） | 可直接复用 |
| 双边成本率 | `MatcherConfig.buy_cost_pct` / `sell_cost_pct` | `backend/app/backtest/engine.py:327` / `:332` | `self`（已解析成本字段） | `float`（买=佣金+滑点；卖=佣金+印花税+滑点；`cost_model` 存在时委派） | 可直接复用 |
| 策略默认执行参数解析 | `ExecutionPolicy` / `parse_backtest_defaults` | `backend/app/backtest/execution_policy.py:64` / `:102` | `(raw: object, *, context: str = "strategy")` | `ExecutionPolicy`（`engine_options()` 生成引擎参数） | 可直接复用：批量应通过它解析策略 META 默认值，避免自行复制字段映射 |
| 自定义成本模型注入 | `MatcherConfig.cost_model` | `backend/app/backtest/engine.py:266` | 任意实现 `buy_cost_pct(cfg)` / `sell_cost_pct(cfg)` 的对象 | 成本率 float | 需适配：无正式 Protocol/文档契约，批量首版只用内置字段，不引入自定义成本模型 |
| 底层逐 symbol 撮合 | `BacktestEngine.simulate` | `backend/app/backtest/engine.py:1225` | `(panel: pl.DataFrame, entries: pl.Series \| None, exits: pl.Series \| None, config: MatcherConfig, entry_signal_ids=None, exit_signal_ids=None)` | `SimResult` | 可直接复用（纯 NumPy 状态机）；不含组合资金约束 |
| 组合账户撮合 | `BacktestEngine.simulate_portfolio` / `_simulate_portfolio_matrix` | `backend/app/backtest/engine.py:2514` / `:2578` | `(panel, entries, exits, config, ...)` / `(market_data: MarketDataMatrix, masks/positions..., config)` | `SimResult` | 需适配：需先构建 `MarketDataMatrix`（`load_market_data_matrix_for_backtest`，`engine.py:954`） |
| 涨跌停判定价与连板 | `compute_limit_signals` | `backend/app/indicators/pipeline.py:725` | `(df: pl.DataFrame, instruments: pl.DataFrame, needed: set[str] \| None = None, historical_shares: pl.DataFrame \| None = None)` | `pl.DataFrame` 追加 `limit_up_price`/`limit_down_price`/`consecutive_limit_ups`/`consecutive_limit_downs` 及引用的 `signal_limit_*` | 可直接复用（输入须含 `symbol,date,raw_close,raw_high,raw_low,open,high,low,close,change_pct,vol_ratio_5d`） |
| 当日涨跌停/连板（增量） | `_compute_limit_signals_today` | `backend/app/indicators/pipeline.py:2381` | `(df: pl.DataFrame, instruments: pl.DataFrame)` | 当日行 `pl.DataFrame` | 不可直接复用：仅当日增量路径，不可用于历史批量 |
| 停牌/不可交易判定 | `_tradable_matrix` | `backend/app/backtest/matrix.py:3111` | `(open_, high, low, close, volume)` numpy 矩阵 | `np.ndarray[bool]`（无有效价/量即不可交易） | 可直接复用（矩阵级；批量若用面板撮合则由 `MatrixBuilder` 内部调用） |
| 涨跌停锁定矩阵 | `_bool_matrix(panel, "signal_limit_up"/"signal_limit_down")` | `backend/app/backtest/matrix.py:626` / `:627` | 面板 + 列名 + shape + 索引映射 | `limit_up_locked` / `limit_down_locked` bool 矩阵 | 需适配：要求面板已含 `signal_limit_*` 列（策略特征计划里显式请求才会算，见 `strategy.py:424`/`:433`） |
| 撮合侧涨跌停/停牌拒单 | 内嵌闭包（`_one_price_limit` / 买入卖出拒单分支） | `backend/app/backtest/engine.py:1625`（闭包定义）、`:1648`、`:1673`、`:1684`、`:1691` | 闭包捕获 `matrix` / `config` | `(bool, reason_code)`，计入 `buy_suspended`/`buy_limit_up`/`sell_suspended`/`sell_limit_down` 计数 | 需适配：无公开函数；批量只能通过 `MatcherConfig.block_limit_open`（`engine.py:259`）与结果里的拒单计数观察 |
| 开盘涨停门控开关 | `MatcherConfig.block_limit_open` | `backend/app/backtest/engine.py:259` | `bool`（默认 False） | — | 可直接复用 |
| 滚动窗口切分 | `generate_folds` | `backend/app/backtest/walkforward.py:32` | `(start: date, end: date, train_days: int, test_days: int, step_days: int, trading_days: Sequence[date] \| None = None)` | `list[Fold]`（闭区间，训练/测试严格错开） | 可直接复用（必须传 `trading_days` 才是交易日口径） |
| WFO 配置 | `WalkForwardConfig` | `backend/app/backtest/walkforward.py:191` | `strategy_id`、`symbols`、`start`、`end`、`param_grid`、`objective="sortino"`、`train_days=252`、`test_days=63`、`step_days=63`、`direction`、`min_trades_oos=10`、`max_workers=4`、`base_params`、`overrides`、`backtest_kwargs`、`matrix_cache_max_mb`、`trading_days`、`continuous_account=True` | 配置实例 | 可直接复用 |
| WFO 驱动 | `WalkForwardService.run` | `backend/app/backtest/walkforward.py:673` | `(cfg: WalkForwardConfig, progress_cb=None, cancel_event=None)` | `dict`（逐折记录 + 聚合 OOS） | 可直接复用；硬约束：只支持 `mode="position"`；`continuous_account=True` 时要求 `step_days == test_days` |
| OOS 聚合 | `aggregate_oos` | `backend/app/backtest/walkforward.py:109` | `(fold_records: list[dict], objective: str, direction: str = "max")` | `dict`（聚合指标） | 可直接复用 |
| 参数网格展开 | `expand_param_grid` / `count_combinations` | `backend/app/backtest/optimizer.py:125` / `:116` | `(params_meta: list[dict], param_grid: dict)` | `list[dict]` / `int` | 可直接复用（用于批量前预估组合数、拒绝超大网格） |
| 单策略参数寻优 | `StrategyOptimizer.optimize` | `backend/app/backtest/optimizer.py:211` | `(cfg: OptimizeConfig, progress_cb=None, cancel_event=None, *, rss_sampler=None, prepared_market_data=None)` | `dict`（组合结果 + 最优参数） | 可直接复用（单进程内遍历；批量多策略需外层并行） |
| 组合账户指标（正式口径） | `BacktestEngine._calc_portfolio_stats_from_values` | `backend/app/backtest/engine.py:5589` | `(equity_values: list[float], exposure_values: list[float], trades: list[TradeRecord], initial_capital: float, *, include_monte_carlo: bool = True)` | `dict`：`total_return`/`annual_return`/`max_drawdown`/`sharpe`/`sortino`/`calmar`/`win_rate`/`profit_factor`/`n_trades`/`completed_trade_count`/`open_at_end_count`/`final_equity`/`avg_exposure` 等 | 可直接复用（策略回测实际采用的账户口径） |
| 逐笔近似指标（旧口径） | `BacktestEngine._calc_stats` | `backend/app/backtest/engine.py:5330` | `(trades, initial_capital, start, end, *, include_monte_carlo=True)` | `dict`（同名字段，但收益/夏普按逐笔复乘近似） | 不可直接复用：与组合口径同名不同义，批量混用会导致跨策略不可比 |
| 结果裁剪契约 | `BacktestResultPolicy` | `backend/app/backtest/strategy.py:796` | `required_stats`、`include_monte_carlo`、`include_curves`、`include_trades`、`include_per_symbol_stats`、`include_return_distribution`、`include_benchmark`、`include_strategy_info`；类方法 `optimizer_trial(objective)` | 策略实例（`select_stats()` / `simulation_options()`） | 可直接复用（批量必须用它裁掉曲线/逐笔，否则内存与落盘量不可控） |
| 多重检验校正 | `stats_v2.newey_west_t` / `bh_fdr_qvalues` | `backend/app/backtest/stats_v2.py:27` / `:67` | `(values, lag)` / `(pvalues: list[float \| None])` | `tuple[float,float,float] \| None` / `list[float \| None]` | 可直接复用（目前仅因子回测使用：`backend/app/backtest/factor.py:415`、`:459`） |
| 通缩夏普（DSR） | `stats_v2.deflated_sharpe_psr` / `expected_max_sharpe` | `backend/app/backtest/stats_v2.py:128` / `:119` | `(sharpe: float, n_obs: int, skewness: float \| None = None, kurtosis: float \| None = None, expected_max_sharpe: float = 0.0)` / `(n_trials: int, variance_sharpes: float)` | `float \| None`（PSR/DSR 概率） / `float`（EM） | 需适配：函数存在但未接入策略/WFO 结果（全仓仅 `factor.py` 引用 `stats_v2` 的其他函数） |
| 未来函数审计 | `evidence.audit_frame` / `audit_matrix` / `save_evidence` / `EvidenceRecorder` | `backend/app/backtest/evidence.py:256` / `:154` / `:313` / `:412` | `(frame, time_col, cutoff, compare?)` / `(market, cutoff, ...)` / `(data_dir, evidence: dict)` / 记录器 | 审计 dict（扰动 cutoff 后对比）/ 证据文件 | 可直接复用（批量产出必须带 `evidence`，用于证明无未来信息） |
| 结果登记与保存 | `register_completed_run` / `CompletedRunCache` / `result_store` API | `backend/app/backtest/result_store.py:209` / `:105`；`backend/app/api/backtest.py:515` | `(result)` / 保存请求 | `run_id` / 保存结果 | 需适配：面向单次 API 运行的内存缓存与用户保存，不是批量实验归档；批量应自建 run 目录 |
| 批量多策略编排器 | 未找到 | — | — | — | 未找到：仓库只有因子批量（`FactorBacktestService.run_batch`，`backend/app/api/backtest.py:218` 调用），没有多策略批量评估/排名入口 |
| 跨策略统一评分与排序 | 未找到 | — | — | — | 未找到：WFO 只聚合单策略折内结果（`aggregate_oos`），无跨策略可比评分层 |

## 2. 接入批量评估的 5 个最小改动点

1. **批量编排层直接调用 `StrategyBacktestService.run`，并强制传 `BacktestResultPolicy`** — 默认返回完整 `equity_curve`/`trades`/`per_symbol_stats`，几十个策略×十年区间会把内存与落盘量放大到不可用；策略对象必须同时裁掉曲线与逐笔，只保留 `required_stats`。
2. **同一数据切片的策略共享一次装载与一次矩阵构建** — 每个策略独立装载 enriched 面板是 10–60 秒级开销，批量 N 策略就是 N 倍；需复用 `load_panel_for_backtest` 结果、`build_matrix_cache_profile`（`strategy.py:447`）/`prewarm_matrix_cache`（`strategy.py:536`），并把 `prepared`/`prepared_panel` 传入 `run`。
3. **交易日与 fold 边界只走 `list_enriched_dates` + `generate_folds(..., trading_days=...)`** — 不传 `trading_days` 时 `generate_folds` 退化为自然日口径（`walkforward.py:32` 注释明确），折边界会落在周末/节假日，跨策略与跨批次结果不可比。
4. **指标口径收敛到组合账户正式实现，并补多重检验** — 只允许 `_calc_portfolio_stats_from_values`（`engine.py:5589`）产出批量比较指标，禁用逐笔近似的 `_calc_stats`（`engine.py:5330`）；同时接入 `stats_v2.deflated_sharpe_psr`（当前未接入任何策略结果），否则「试了很多策略挑最好的」这一选择偏差会被当成超额收益。
5. **每次批量运行绑定数据版本并落证据** — 用 `engine.data_generation()` / `load_panel(..., expected_generation=...)`、`evidence.save_evidence`（`evidence.py:313`）与 `audit_frame`/`audit_matrix`（`:256`/`:154`）固定数据世代并证明无未来信息；否则盘中 enriched 刷新后，同一策略重跑会得到不同结果，批量结论无法复现。

## 3. 限制与未接入

- 本文件为**只读代码调查**：未改动任何源码，未新增框架代码，未运行任何回测或测试。
- 行号对应当前工作区（含未提交修改）；`engine.py` 在本次调查期间被他人在 22:47:36 修改过（+298 字节），若上游继续改动这些文件，行号需重新核对。
- 本次调查只新增了 `research/batch-backtest-framework-20261107/` 一个未跟踪目录；`git status` 的已跟踪文件清单与开始时一致（详见回复中的命令与退出码）。
- 上述「可直接复用」仅表示调用签名可用，**未验证**在大批量、多进程、长区间下的实际稳定性与内存表现。
- 未找到项已按调查结论标注，未作推测：独立交易日历表、按 (symbol,date) 的复权因子仓库方法、批量多策略编排器、跨策略统一评分层。
- `backend/app/custom/strategy_research/` 与 `scripts/strategy_research.py` 是既有研究实验/路径报告扩展（未提交），不是批量回测编排器，未纳入本表作为复用入口。
