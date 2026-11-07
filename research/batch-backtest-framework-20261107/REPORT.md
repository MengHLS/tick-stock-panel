> **迁移提示（2026-11-07 01:18）**：本文件是 v1 产物。其中 `n_trials=12` 的表述与“与单跑逐字段差异 0”的覆盖范围都已作废（字段已改为 `engine_execution_count` / `hypothesis_count` 双口径；v1 比较器跳过曲线与逐笔）。当前有效证据见 `REPORT-F1F3.md`，取代关系见 `MIGRATION-NOTE.md`。**正文一字未改。**

# 批量回测最小底座 — 交付与取证报告

- 仓库：`C:\work\sourcecode\tick-stock-panel`，分支 `dev` @ `848bd04b`
- 报告时间：2026-11-07 00:34 (+08:00)
- 本轮 batch_id：`55df8aec7ce9`；代码指纹（含 `run_batch.py` 自身）：`67afbcb7f5f0af187ed7a05cbe7597817e053b254b844ca4e3bc42429b2cf4d8`
- 范围：只新增 `research/batch-backtest-framework-20261107/` 内文件；`backend/` 生产源码**零改动**；未提交、未部署、未重启。

## 1. 结论

| 验收项 | 结果 | 证据 |
|---|---|---|
| `run_batch.py` 可执行 | exit 0，wall 67s | `out/registry.json`、`out/evidence/*.json` |
| 2 策略 × 1 参数组 | `first_board_chain_rebreak` / `first_limit_pullback_3f_runner_t74` 各 1 组，3 折 IS+OOS | `out/registry.json → runs[2]` |
| 与单跑逐字段一致性 | **0 结果差异**（2/2 组，`result_diffs: []`） | `out/compare_g*.json`、`out/compare_summary.json` |
| matrix_native + 共享矩阵连续回放 | `duplicate_dates=0`、`timeline_complete=true`（批量侧与生产侧各自都有） | 见 §5 |
| 共享装载证明 | `matrix_load_count=1`、`matrix_prepare_calls=12`（2 组 × 3 折 × 2 次） | `registry.totals`、`slice_load` |
| 静态检查 | `ruff check` 全通过（0 error）；`py_compile` OK | 本轮实跑 |

## 2. 文件清单（全部新增）

| 文件 | 行数 | 作用 |
|---|---|---|
| `run_batch.py` | 1,156 | 批量底座：一次装载 → 逐组逐折 IS/OOS → registry + evidence |
| `verify_batch.py` | 417 | 一致性验证：用生产 `WalkForwardService.run` 单跑同配置，逐字段比对 |
| `groups.json` | — | 2 组策略清单（单值网格） |
| `groups_g2.json` | — | 单组回归用清单 |
| `probe_shared_matrix.py` / `probe_symbol_axis.py` / `probe_is0.py` | 159 / 107 / 57 | 动工前的接口探针（装载耗时、标的轴、IS 契约差异） |
| `INTERFACE-MAP.md` | — | 接口盘点（22:52 版，行号已随他人改动过期，以本文与代码为准） |
| `out/registry.json` | — | 机器可读汇总（每次运行一个 batch） |
| `out/evidence/*.json` | — | 每组证据（2 份） |
| `out/runs/*.json` | — | 每组原始输出（OOS 曲线等） |
| `out/compare_*.json`、`compare_summary.json` | — | 一致性比对明细 |

## 3. 四个必做点怎么落地

1. **切片级共享装载**：`run_batch.py:302` 调一次 `build_matrix_cache_profile`（字段取所有待跑策略并集），`:349` 调一次 `engine.load_market_data_matrix_for_backtest` 得到**一个** `MarketDataMatrix`；之后每组每折 `:758` 走 `service.prepare_matrix_optimization([cfg], market_data_override=shared)`，内部 `slice_market_data_matrix` 返回只读视图，不复制数组。
   - 实测：`matrix_load_count=1`，`matrix_load_elapsed_s=1.523`，矩阵 250.5 MB / `[728, 5727]` / 窗口 2023-10-30 ~ 2026-10-30 / 缓存 `covering`。
   - 刻意**没有**把 `prewarm_matrix_cache` 当共享载体：它 load 完即 `del market`，只留磁盘 mmap，调用方拿不到对象，无法证明“一次装载”。
2. **强制裁剪**：IS 直接调生产 `optimize()`（内部即 `optimizer_trial(objective)` 契约：`required_stats={objective, n_trades}`，无曲线/逐笔/分标的/MC/基准）；OOS 保留曲线与逐笔（连续账户回放的原料），每组结束 `curves.clear()/trades.clear()` 释放（`keep_raw=False`），峰值就落在这之前。evidence 里的 `policy` 现在是**真实对象 repr 现取**（本轮修掉了原先手写的描述串，那条串还把 `total_return`/`max_drawdown` 写进了 `required_stats`，与生产不符）。
3. **fold 只用交易日**：`repo.list_enriched_dates`（`:292`）→ `generate_folds(trading_days=252, test=63)`（`:295`）。本切片 463 个交易日 → 3 折，交叠窗口，测试段 2025-12-15~2026-03-23 / 2026-03-24~2026-06-25 / 2026-06-26~2026-09-22。没有任何自然日切分。
4. **绑定数据版本与代码指纹**：`data_generation.before/after/bound` 三值一致 `2b948c890e75472ab8317ca0ce40af77`（跑前跑后校验，不一致会失败）；`code.sha256` 覆盖 `engine.py / strategy.py / walkforward.py / matrix.py / optimizer.py / evidence.py / repository.py / run_batch.py` 八个文件，逐文件哈希也落在 evidence 里。`registry.runs[*]` 含 `run_id / strategy_id / params / data_generation / code_sha256 / elapsed_s / peak_rss_mb / n_trials / n_trials_cumulative`，`totals` 汇总 `n_trials=12`。

## 4. 实跑记录（本轮现跑，非历史日志）

命令 1（批量底座）：

```
backend/.venv/Scripts/python.exe research/batch-backtest-framework-20261107/run_batch.py \
  --groups research/batch-backtest-framework-20261107/groups.json \
  --start 2024-12-02 --end 2026-10-31 --train-days 252 --test-days 63 \
  --out research/batch-backtest-framework-20261107/out
```

`EXIT=0`，wall **67 s**，`totals.elapsed_s=64.3`，`totals.peak_rss_mb=740.2`，`n_trials=12`。

| run_id | 策略 | 参数 | IS trials | OOS 折 | 耗时 | 峰值 RSS | duplicate_dates | timeline_complete | OOS 复合收益 |
|---|---|---|---|---|---|---|---|---|---|
| `551c42e797f9` | `first_board_chain_rebreak` | `min_pullback_pct=5.0` | 6 | 3 | 13.52 s | 740.2 MB | 0 | true | -0.5658 |
| `25ca1af3104b` | `first_limit_pullback_3f_runner_t74` | `min_score_pct=55.0` | 6 | 3 | 48.90 s | 716.2 MB | 0 | true | -0.0072 |

（两个策略跑在**同一个进程、同一次矩阵装载**内；`n_trials_cumulative` 6 → 12 递增，说明计数跨组累加。）

命令 2（与单跑比对）：

```
backend/.venv/Scripts/python.exe research/batch-backtest-framework-20261107/verify_batch.py \
  --registry research/batch-backtest-framework-20261107/out/registry.json
```

`EXIT=0`，wall **70 s**。生产侧用 `WalkForwardService.run`（`continuous_account=True`）同配置单跑。

## 5. 一致性比对与 matrix_native 共享矩阵取证

| 组 | 结果差异 | telemetry 差异（allowlist 内） | 批量 final_equity | 生产 final_equity | 生产 shared_market_data |
|---|---|---|---|---|---|
| `g1_first_board_chain_rebreak` | **0** | 18 | 434,227.12 | 434,227.12 | true |
| `g2_first_limit_pullback_3f_runner_t74` | **0** | 21 | 992,786.95 | 992,786.95 | true |

- `result_diffs: []` —— 逐折 IS 分数、OOS 统计、账户终值全等，**不是四舍五入巧合**（终值到分完全一致）。
- 39 条 telemetry 差异全部落在 8 个 allowlist 键：`market_matrix_bytes`、`market_matrix_shape`、`matrix_compute_cache`（各类 `compute_ms/fingerprint_ms`）、`matrix_data_cache_hit/status`、`panel_rows/columns`、`shared_market_data_bytes`。它们是装载形态与计时，不是策略结果。
- 其中一处值得记录：g2 `market_matrix_shape[1]` 批量 5727 vs 生产 5666。共享 profile 取的是多策略**字段并集**，矩阵更宽；策略只读自己声明的列，结果不受影响。这是共享的固有形态差异，登记为已知差异而不是“归零”。
- **matrix_native 共享矩阵 + 连续回放**（独立审核指出的缺口）：
  - 批量侧 `continuous_account.duplicate_dates=0`，`timeline.complete=true`，`n_missing_dates=0`，`n_folds_replayed=3/3`，回放区间 2025-12-15~2026-09-22（189 交易日，`covers_planned_span=true`），`stopped_early=null`；
  - 生产侧同字段 `duplicate_dates=0`、`timeline_complete=true`、`shared_market_data=true`（即生产这次也是在共享基础矩阵下回放）；
  - `run_batch.py` 在 `:626` 硬性拒绝 `execution_backend != "matrix_native"` 的策略，所以这两组证据确实走的是 matrix_native 路径。
- 复现性：本轮之前同参数连跑两次（22:58 / 00:22 批次）结果完全一致（325 / 246 笔 OOS，-0.5658 / -0.0072），本次第三次仍一致。

## 6. 明确「不做」的部分

| 能力 | 状态 | 原因 |
|---|---|---|
| 跨策略统一评分/排序层（把不同策略放到同一标尺排序选优） | **不做** | 生产侧没有这个抽象，各策略 `objective` 与样本分布不可直接横比；臆造一个排序层会让“最优策略”结论不可检验。当前只按组各自输出 `oos_objective`。 |
| 参数扫描（每组 >1 个参数组合） | **不支持**，直接报错 | 底座定位是“一次装载、多策略多折”；参数搜索走生产 optimizer。强行扫描会让 IS 契约与生产不一致，比对无法归零。 |
| `--trim-oos` 下的连续账户 | 不可用 | 曲线被裁后无法重建时间线，evidence 显式写 `enabled=false` 及原因。 |
| 并行 / 多进程 / 断点续跑 | 不做 | 要求单进程最小底座；并行会破坏“一次装载”的内存核算。 |
| 跨机器缓存复用 | 不做 | 缓存路径 `D:\TSP\data\.backtest_matrix_cache\v5-37c5e608...`，与数据生成版本绑定。 |

## 7. 复现与失效条件

- 复现：上面两条命令即可，冷/热缓存都已验证（热缓存 64~70 s）。
- **证据有效期绑定代码哈希**：`engine.py`/`strategy.py`/`walkforward.py` 目前仍是他人的未提交改动（`git status` 41 项已跟踪改动 + 本目录）。本轮证据对应 `engine.py ecc3d82…`、`strategy.py c3bfb25…`、`walkforward.py c9506b1…`。这些文件再被别人改，本报告比对结论即失效，必须重跑 `run_batch.py` + `verify_batch.py`。
- 未验证：扩展策略数（10+ 组）的内存压力、`--trim-oos` 组合、前端/API 侧、以及任何策略的盈利性（本次 OOS 收益为负，底座只证明工程一致性，不证明策略有效）。
