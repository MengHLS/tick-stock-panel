# F1 / F3 修复与证据（批量回测比较器 v2）

范围：`research/batch-backtest-framework-20261107/`。未改 `backend/` 任何源码，未提交、未部署、未重启。
本文对应独立审核 `MATRIX-NATIVE-E2E-20261107.md` 的 F1（比较器漏比）与 F3（绑定不足），
以及“矩阵维度差异不能一律遥测忽略”。

## 1. 审核指出的原始缺陷（v1 的真实行为）

| 编号 | 缺陷 | v1 位置 | 后果 |
|---|---|---|---|
| F1-a | 全局 `SKIP_KEYS` 按**字段名**跳过 `total_return`、`continuous_account` | `archive/verify_batch_v1_as_delivered.py` | 段收益、累计收益、整条连续账户（曲线、逐笔、边界、不变量）**从未比对** |
| F1-b | 曲线与逐笔只比长度或完全不比 | 同上 | 改坏任意一个权益点/逐笔盈亏，v1 仍报 `result_diffs=0` |
| F1-c | 矩阵维度差异一律按遥测忽略 | 同上 | 列/时间轴差异无法解释也能通过 |
| F3 | 只绑定 `data_generation`，无代码/输入哈希，也无跑前跑后复核 | 同上 | 代码或 groups 变更后旧证据仍被当成有效 |

## 2. 修复实现

新比较器是**新增文件** `verify_batch_v2.py`（v1 `verify_batch.py` 原地未动，并另存一份到 `archive/`）。

| 项 | 实现 | 位置 |
|---|---|---|
| F1-1 精确路径豁免 | `EXEMPT_PATTERNS`/`DEVICE_PATTERNS`/`ANNOTATION_PATTERNS` 三张**路径**清单，逐段匹配（`*` 只匹配单段，`[*]` 只匹配同段下标）；不再有按字段名的全局跳过 | `verify_batch_v2.py` 路径分类段 |
| F1-2 完整曲线/逐笔 | 两侧用**同一个** `run_batch.canonical_hash` 算规范化摘要并比对（`equity_curve` / `trades` / `drawdown_curve`），摘要不等再做元素级定位 | `compare_continuous` |
| F1-3 必需字段缺失即失败 | `REQUIRED_ENTRY`(14) / `REQUIRED_ACCOUNT`(14) / `REQUIRED_PROD`(10)；生产侧有而批量侧无 → `missing_required` 直接计入结果差异；批量侧多出的键**必须**命中 `ANNOTATION_PATTERNS`，否则 `extra_in_batch` 也算差异 | `walk()`、`main()` |
| F1-4 分段与累计收益 | `oos_folds[*].oos_stats.total_return` 与 `account_total_return_cumulative` 逐折逐字段比对 | `compare_folds` |
| 矩阵维度 | 形状/字节数进 `DEVICE_PATTERNS`，但**必须**由 `build_axis_proof` 证明：生产侧真实装载轴 ⊇ 批量并集轴、批量侧独有证券在正式区间内 0 个可交易日、生产装载窗口被批量窗口覆盖、生产确实走共享矩阵；证明不成立即 `n_unproven_diffs>0` → 退出码 1 | `build_axis_proof` |
| F3 绑定 | `binding_snapshot()` 覆盖 8 个代码文件 sha256、`data_generation`、groups 文件 sha256、inputs（groups+策略定义+override）规范化哈希、`verify_batch_v2.py`/`run_batch.py` 自身 sha256；批次跑前/跑后各取一次，比较器再取一次，任一不一致即违规（fail-closed） | `binding_snapshot` / `check_registry_binding` |

计数口径（避免把局部次数写成全局 N）：
`engine_execution_count` = 引擎评估调用次数（IS 网格 trial + OOS 折回放），每组 6、合计 12；
`hypothesis_count` = 该组固定规则/参数假设数，每组 1、合计 2。两者都有 `*_cumulative`。

## 3. 产物三代并存（互不覆盖）

| 目录 | 内容 | 状态 |
|---|---|---|
| `out/` | v1 批次 + `verify_batch.py`（全局 SKIP_KEYS） | 保留，已作废 |
| `out_v2/` | 第一代 v2 批次（代码指纹 `28bddd65…`）+ `verify_v2/`（比较器把 timing 当结果差异，64 条 → 失败）+ `verify_v3/`（补精确路径后 0 条） | 保留，用于展示修复前后差异 |
| `out_v3/` | **最终**一代：批次 + `verify_v3/` + `mutation-report.json`（代码指纹 `1856c1a2…`） | 有效证据 |

`out_v2` 与 `out_v3` 的代码指纹不同，因为 `run_batch.py` 顶部说明改过（计数口径写清），
故 `out_v2` 的任何比对结论都不应引用为当前结论——这正是 F3 绑定要防的事。

## 4. 实跑取证（本轮现跑）

| # | 命令 | 退出码 | 墙钟 | 关键输出 |
|---|---|---|---|---|
| 1 | `run_batch.py --groups groups.json --start 2024-12-02 --end 2026-10-31 --train-days 252 --test-days 63 --out out_v3` | **0** | 65.2 s | `totals.elapsed_s=62.23`、`peak_rss_mb=743.0`、`matrix_load_count=1`、`matrix_prepare_calls=12`、`engine_execution_count=12`、`hypothesis_count=2` |
| 2 | `verify_batch_v2.py --registry out_v3/registry.json --out out_v3/verify_v3` | **0** | 65.5 s | `total_result_diffs=0`、`total_unproven_diffs=0`、`binding_ok=true`、`elapsed_s=62.59` |
| 3 | `mutation_checks.py --registry out_v3/registry.json --verify-dir out_v3/verify_v3` | **0** | 3.8 s | `baseline_clean=true`、`n_detected=20/20`、`axis_proof_ok=true` |

批次分组：

| run_id | 策略 | 参数 | engine_exec | hypothesis | OOS 逐笔 | OOS 复合收益 | 峰值 RSS | 耗时 |
|---|---|---|---|---|---|---|---|---|
| `8cb97cb0f49d` | `first_board_chain_rebreak` | `min_pullback_pct=5.0` | 6 | 1 | 325 | -0.5658 | 743.5 MB | 12.63 s |
| `4bb3183368ca` | `first_limit_pullback_3f_runner_t74` | `min_score_pct=55.0` | 6 | 1 | 246 | -0.0072 | 717.3 MB | 47.69 s |

## 5. 正向对照：批量 vs 生产单跑 = 0 差异（含完整曲线与逐笔）

生产侧用 `WalkForwardService.run(continuous_account=True)` 同配置独立单跑。

| 比对对象 | g1 生产 | g1 批量 | 一致 | 规范化 sha256 |
|---|---|---|---|---|
| `equity_curve` | 189 | 189 | ✅ | `95c21c7c09ffc728…` |
| `trades` | 325 | 325 | ✅ | `a0675bfd4d6093a8…` |
| `drawdown_curve` | 189 | 189 | ✅ | `0d5a5993539d9001…` |

| 比对对象 | g2 生产 | g2 批量 | 一致 | 规范化 sha256 |
|---|---|---|---|---|
| `equity_curve` | 189 | 189 | ✅ | `5bbad671ea2cab39…` |
| `trades` | 246 | 246 | ✅ | `58bc213564648a39…` |
| `drawdown_curve` | 189 | 189 | ✅ | `4e1af00877cd483b…` |

差异分类（两组合计）：结果差异 **0**、未证明差异 **0**、豁免 **135**（全部是 `*_ms` 计时字段，逐条落盘在 `exempt_diffs`）、
设备维度差异 **51**（`market_matrix_shape/bytes`、缓存字节数，由第 6 节的轴证明解释）。

审核要求的 matrix_native 共享矩阵留证：
`production_shared_market_data=true`、生产侧只装载 1 次 5727 列、窗口 `2023-10-30~2026-09-22` 被批量窗口 `2023-10-30~2026-10-30` 覆盖、
`n_batch_only_symbols=0`、`n_production_only_symbols=0`；批量侧 `duplicate_dates=0`、`timeline.complete=true`（3/3 折、189 交易日），生产侧同字段同为 `0 / true`。

## 6. 负向变异：20/20 全部被检出

`mutation_checks.py` 在**内存副本**上做单点破坏，不修改任何证据文件；未变异的原始对照仍为 `0` 差异。

| 变异 | 目标 | 检出 |
|---|---|---|
| `curve_point_value` | 第 1 个权益点 `value += 999` | ✅ `equity_curve` 摘要不等 |
| `curve_point_cash` | 第 6 点 `cash += 0.01` | ✅ |
| `curve_point_date` | 第 4 点日期改动 | ✅ |
| `curve_length` | 曲线少一个点 | ✅ |
| `trade_pnl_amount` | 首笔 `pnl_amount += 999` | ✅ `trades` 摘要不等 |
| `trade_entry_value` | 首笔 `entry_value += 0.01` | ✅ |
| `fold_total_return` | 第 1 折 `oos_stats.total_return=999` | ✅ 逐折比到 `-0.2306 vs 999.0` |
| `fold_account_cumulative_return` | 第 2 折累计收益=999 | ✅ 比到 `-0.3483 vs 999.0` |
| `account_stats_return` | 账户收益=999 | ✅ |
| `summary_field` | `summary.n_folds +1` | ✅ |
| `delete_prod_required` | 生产侧缺 `final_equity` | ✅ `extra_in_batch` |
| `delete_prod_curve` | 生产侧缺 `drawdown_curve` | ✅ `missing_required` |
| `delete_entry_required` | 批量侧缺 `trades_sha256` | ✅ 2 条（摘要 + 原列表） |
| `delete_entry_fold_stat` | 批量侧折缺 `n_trades` | ✅ |
| `boundary_equity` | 首个折边界 `equity_end=1.0` | ✅ |
| `duplicate_dates` | 改成 3 | ✅ 数值 + 不变量双报 |
| `timeline_incomplete` | `timeline.complete=false` | ✅ |
| `code_sha256` | 改 registry 代码指纹 | ✅ 绑定违规（fail-closed） |
| `data_generation` | 改数据世代 | ✅ 绑定违规 |
| `groups_input_hash` | 改 groups 清单哈希 | ✅ 绑定违规 |

轴证明本身的正负对照（同一份真实观测上做三处单点破坏）：

| 方向 | 构造 | 结果 |
|---|---|---|
| 正向（真实） | 实跑记录的装载轴与窗口 | `proven=true` |
| 负向 1 | 摘掉 `000001.SZ`（463 个可交易日）→ 成为批量侧独有 | `proven=false` ✅ 被拒 |
| 负向 2 | 生产装载窗口改为 `1990-01-01~1991-01-01` | `proven=false` ✅ 被拒 |
| 负向 3 | 声称 `shared_market_data=false` | `proven=false` ✅ 被拒 |

（首次运行的探针用合成观测对象，正向被判 `false`，已改为读取真实装载轴；那次失败报告保留在
`out_v2/verify_v3/mutation-report.attempt1-axisprobe-failed.json`，不覆盖、不删除。）

## 7. 未覆盖范围（明确不做）

- 只验证 2 个策略 × 1 个参数组 × 1 个成本档，未做参数扫描、未做多组内存压力测试（10+ 组）。
- 未覆盖前端/API 侧的批量回测入口。
- `--trim-oos` 下无曲线/逐笔，连续账户不可重建，此模式不在本次证据范围。
- 未做并行/多进程/断点续跑；未做跨机器缓存复用。
- 本次只证明**工程一致性**（批量底座与生产单跑等价），不证明任何策略盈利；两个 OOS 收益均为负。

## 8. 复验命令

```bash
cd <repo>
backend/.venv/Scripts/python.exe research/batch-backtest-framework-20261107/run_batch.py \
  --groups research/batch-backtest-framework-20261107/groups.json \
  --start 2024-12-02 --end 2026-10-31 --train-days 252 --test-days 63 \
  --out research/batch-backtest-framework-20261107/out_v3
backend/.venv/Scripts/python.exe research/batch-backtest-framework-20261107/verify_batch_v2.py \
  --registry research/batch-backtest-framework-20261107/out_v3/registry.json \
  --out research/batch-backtest-framework-20261107/out_v3/verify_v3
backend/.venv/Scripts/python.exe research/batch-backtest-framework-20261107/mutation_checks.py \
  --registry research/batch-backtest-framework-20261107/out_v3/registry.json \
  --verify-dir research/batch-backtest-framework-20261107/out_v3/verify_v3
```

退出码期望：`0 / 0 / 0`。若 `engine.py`、`strategy.py`、`walkforward.py` 或 `run_batch.py` 再被改动，
绑定检查会先失败（`binding_ok=false`），必须先重跑批次再比，不能沿用本文件结论。
