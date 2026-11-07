# 批量回测最小底座 — 施工日志

范围：只新增本目录文件；不改 `backend/` 生产源码；不提交/部署/重启。

## 设计决策（先定后写码）

- 切片级共享：一次 `build_matrix_cache_profile`（自带全策略并集字段）+ 一次
  `engine.load_market_data_matrix_for_backtest(...)` 得到**一个** `MarketDataMatrix`，
  之后每个策略/折用 `service.prepare_matrix_optimization([cfg], market_data_override=shared)`
  取只读时间视图（`slice_market_data_matrix` 返回视图，不复制数组）。
  不用 `prewarm_matrix_cache` 作为共享载体：它内部 load 完就 `del market`，
  只留磁盘 mmap，调用方拿不到对象；本底座保留对象以证明「一次装载」。
- fold 边界只走 `repo.list_enriched_dates` + `generate_folds(trading_days=...)`。
- 结果裁剪：IS 走生产 `optimize()`（内部 `optimizer_trial` 契约，无曲线/逐笔）；
  OOS 保留曲线（连续账户时间线必须）与逐笔，组结束后 `clear()` 释放。
- 连续账户：批量侧按结转语义回放，另用生产 `WalkForwardService.run(continuous_account=True)`
  做同配置独立单跑，逐字段比对（结果差异必须 0）。

## 进度

- [x] 读规范/git/接口（HEAD 848bd04b，已跟踪改动 41 项含 engine/strategy/walkforward）
- [x] 探针：共享矩阵装载耗时/内存（`probe_shared_matrix.py` 等）
- [x] run_batch.py（1,156 行）
- [x] 2 组实跑取证（exit 0 / 67 s / 峰值 740.2 MB / 12 trials）
- [x] 与单跑逐字段比对（`verify_batch.py` exit 0，2/2 组 `n_result_diffs=0`）
- [x] matrix_native 共享矩阵 + 连续回放留证（dup=0 / timeline_complete=true，批量侧与生产侧各自都有）
- [x] 收尾：`ruff` 0 error、`py_compile` OK；evidence 里的 policy 改为真实 repr 现取；
      清掉旧批次残留 evidence/runs；交付 `REPORT.md`

## 结论摘要

见 `REPORT.md`：底座可执行、可复现，与生产单跑**结果差异 0**；本轮 OOS 收益为负（-0.5658 / -0.0072），
底座只证明工程一致性，不证明任何策略有效。

---

## F1/F3 修复阶段（2026-11-07 01:0x–01:2x）

审核 `MATRIX-NATIVE-E2E-20261107.md` 的 F1（比较器漏比）/F3（绑定不足）处置：

- [x] 新增 `verify_batch_v2.py`（v1 `verify_batch.py` 原地不动，另存 `archive/`）：
      精确路径豁免、`canonical_hash` 全曲线/逐笔/回撤比对、必需字段缺失即失败、
      分段与累计收益逐折比对、`build_axis_proof` 取代“维度一律遥测忽略”、
      F3 绑定（8 文件 sha256 + 数据世代 + groups + inputs，跑前/跑后/比较时三处）。
- [x] 新增 `mutation_checks.py`：20 项单点变异全部检出；轴证明 1 正向 + 3 负向对照。
- [x] 修复自身缺陷：豁免规则原先按 `split(".")` 后整段比对，`[*]` 没吃掉下标段，
      导致 `timing_ms.*` 被算成结果差异（`out_v2/verify_v2` 的 64 条）。改为
      `_segment_match` 处理 `[*]` 后，同一 registry 复跑 `out_v2/verify_v3` 为 0 条。
- [x] 修复自身缺陷：轴证明探针原用合成观测对象，正向被判 false；改为读取实跑落下的
      真实 `production_load_axes`。首版失败报告保留为 `mutation-report.attempt1-axisprobe-failed.json`。
- [x] `run_batch.py` 顶部说明改为 `engine_execution_count` / `hypothesis_count` 双口径
      （原写 `n_trials`，会被读成“假设个数 N”）。此改动使代码指纹从 `28bddd65…` 变为 `1856c1a2…`，
      按 F3 规则必须重跑，故新增 `out_v3/` 一代证据，`out_v2/` 全部保留。
- [x] 最终实跑：`run_batch.py` exit 0（65.2 s，峰值 743.0 MB，装载 1 次，prepare 12 次）；
      `verify_batch_v2.py` exit 0（65.5 s，结果差异 0，曲线 189/325/189 哈希相同，binding ok）；
      `mutation_checks.py` exit 0（3.8 s，20/20 检出，轴证明通过）。
- [x] `ruff check` 0 error、`py_compile` OK；`backend/` 8 个绑定文件哈希与 registry 记录逐一相符
      （证明本次未改生产源码）。
- [x] 文档：`REPORT-F1F3.md`（修复与证据）、`MIGRATION-NOTE.md`（代际与撤回表述）；
      `REPORT.md` 仅顶部加 2 行迁移提示，去掉这 2 行后哈希与原文件完全一致（正文未改）。

残留限制（已知、未修）：

- `EXEMPT_PATTERNS` 里 `timing_ms.*` / `shared_prepare_timing_ms.*` 等是**容器前缀**豁免，
  若有人把结果字段挪进这些计时容器，会被一并豁免。容器命名即约束，未再加叶子名校验。
- 仅 2 组 × 1 参数组合；未覆盖前端/API、`--trim-oos` 模式、并行与多组内存压力。
