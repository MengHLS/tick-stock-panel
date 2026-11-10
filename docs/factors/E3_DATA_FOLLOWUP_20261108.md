# E3 数据跟进：`st_history` 2026-10-20 批量 False 的成因，与 7 条「缺数据环境」测试的真实前置

> 交付对象：开发经理 · 2026-11-08
> 结论口径：**A 定位到具体机制（不是「只有现象」）；B 的 7 条里 0 条由缺数据造成** —— 按 skip 标注会掩盖真问题。
> 边界遵守：未改 `backend/**`、未改 `docs/factors/**` 既有结论、未回填数据、未跑回测、未 commit。

## 0. 三行结论

1. **A 的成因**：`st_history` 是「源库 ST 区间 → 状态转换」的派生物（`manifest.sourceStIntervals: 1043`）。源库的 ST 区间由 BaoStock 逐日 `isST` 合并成串，而合并函数把 **`isST=null`（查不到/未观测）与 `isST=0` 同等处理，都会就地闭合区间**。因此「10-20 之后 ST 名单缺失」被落成「区间于 10-19 结束」→ 导出即在 10-20 写 198 行 False。**这属于「把查不到当 False 落库」，不是真实摘帽。**
2. **198 这个数字对上了**：`218 = 20 + 198`。其中 20 只是**行情序列已终止**的标的（最后一根 bar 在 2021-12-16…2024-08-14），序列终止后不再有观测，区间永不闭合，所以它们一直停在 `ST=True`；198 只是序列仍在延续的标的，一旦出现一次「非 1」观测就被闭合。该数字**不对应任何外部 ST 名单文件**，它就是「218 减去序列已终止者」的算术余数。
3. **B 的 7 条全不是缺数据**：把 `TSP_DATA_DIR=D:/TSP/data` 设成真数据目录后逐条重跑，**7 条仍然全红（0 条变绿）**。它们的真实前置是 4 条测试侧接口漂移 + 2 条策略选择面漂移 + 1 条实现缺口（矩阵路径无 `in_universe`）。用 skip 标注会把 7 个真问题一起掩盖。

---

## A｜`flag_date=2026-10-20` 一次性 198 行 `st_flag=False` 的成因

### A.1 先固定事实（本文所有数字的可复算出处见 §C）

| 项 | 实测值 |
| --- | --- |
| `D:/TSP/data/st_history/part.parquet` | 7,758 行 / 5,817 只 / 2019-01-01 … 2026-10-29 |
| `sha256` | `52227460a93417792fea6a59001950ce6f9ece15d04fc84c15c5e47819e4a990` |
| 行构成 | True 986 行 + False 6,772 行（= 7,758，自洽） |
| `manifest.source` | `research_security_status_history.statusType=ST` |
| `manifest.sourceDatabase` | `stock-limit-up-analyzer` |
| `manifest.sourceStIntervals` | **1,043 条源区间** → 7,758 行输出 |
| `manifest.generatedAt` | 2026-10-29T14:17:49Z |
| `manifest.absencePolicy` | `absence_of_ST_interval_is_non_ST` |
| `manifest.note` | `Transitions are derived from ST intervals; no current-name backfill.` |
| 10-20 事件 | as-of 10-19 `ST=True` = **218**；当日写 False = **198**；未闭合 = **20**；`218 = 20 + 198` |
| 契约表达 | `st_unknown_windows` 8 天（10-20…10-29）+ 末端不外推 6 天（10-30…11-06）= 14 个交易日 |

关键：**导出是「区间 → 转换」的纯派生**，`generatedAt` 已是 10-29。也就是说 10-20 那 198 行 False 在 10-29 那次导出时，**源库里的区间就已经是「于 10-19 结束」的状态**。所以问题不在导出脚本，在源库区间怎么变成「结束」的。

### A.2 机制：三条代码事实串成一条链

**① 源库的 ST 区间从哪来 —— BaoStock 逐日 `isST` 合并成串**

`stock-limit-up-analyzer/server/securityStatus/baostockStatus.ts:87`

```ts
const runs = mergeConsecutiveRuns(points, (p) => p.isST === 1);
```

**② 合并函数的「缺测」处理与其注释相反**

`同文件 :44-62`

```ts
for (const point of points) {
  if (predicate(point)) { current ? (current.to = point.date) : (current = {...}); }
  else { current = null; }        // ← 任何非 1（含 null）都把区间就地闭合
}
```

接口注释写的是「`null = 缺失，跳过`」（`:29-31`），但实现里**没有跳过分支**：`p.isST === 1` 对 `isST === null` 与 `isST === 0` 同样取 `false`，走的是同一个 `current = null`。

**③ 缺测确实会长成 `null`**

`scripts/backfillStatusLiquidity.ts:695`：`isST: num(row.isST)`；而 `num()`（`:180-184`）把 `null / undefined / ""` 统一转成 `null`。

于是链条是：**BaoStock 该股某日 `isST` 为空串或缺失 → `null` → 合并函数视为「非 ST」→ 把这段 ST 区间就地收在最后一个 `isST=1` 的日期**。10-20 之后该字段整体不可得（或被写成空串），全部 198 只的有序序列就在 10-19 处断掉，区间集体收于 10-19，导出即在 10-20 写 False。

### A.3 为什么是 218 拆成 20 + 198，而不是全闭

| 组 | 只数 | 最后一根 bar 区间 | 14 日窗口内有 bar 的标的日 | 导出末行 |
| --- | --- | --- | --- | --- |
| 未闭合（保留 `ST=True`） | **20** | 2021-12-16 … 2024-08-14 | **0** | True（开区间） |
| 闭合（写 `False`） | **198** | 2026-09-03 … 2026-11-06 | 2,709 | False |

两组在「最后一根 bar」上**完全不重叠，中间空 2 年**（2024-08-14 → 2026-09-03）。全库 5,817 只里只有 20 只末行为 True —— **正好就是这 20 只**。

例（`000005.SZ`）：全表仅两行 `('2019-01-01', False)`、`('2021-05-06', True)`，此后无任何记录；kline 最后一根 bar 是 2024-03-05。

解释：**闭合只在「观测到一次非 1」时触发**。序列已经终止的标的（退市/长期停牌）不会再有观测，区间永远开着；序列仍在延续的标的，一旦某天出现空/0 就被闭合。这是「闭合由观测驱动、缺测被当成非 ST」的直接可见后果。

### A.4 反证：这不是真实摘帽，是流水线产物

**（1）同形态事件在 2026-09-05 发生过一次，两天后完全回滚**

| 项 | 实测 |
| --- | --- |
| 2026-09-05 是星期几 | **Saturday（非交易日）** |
| as-of 09-04 `ST=True` | 213 |
| 09-05 写 False | **193** |
| 未闭合 | 20 |
| 算术 | **213 = 20 + 193** |
| 09-07 写 True | **200**，其中 **193 只正是 09-05 刚被置 False 的那批** |
| as-of 09-07 `ST=True` | 220 |

同一批 193 只，**周六被闭合、下周一被原样恢复**。真实摘帽不可能在非交易日发生，更不可能两天后回滚。这证明「区间被批量闭合」是重跑/重采产物。

**（2）10-20 那批「已摘帽」的标的，今天名字里还带 ST**

- 198 只中 **195 只**在 `instruments.as_of=2026-11-05` 的**当前名称仍含「ST」**；
- 只有 3 只不带：`002731.SZ`（萃华退，退市整理名）、`603517.SH`（绝味食品）、`603838.SH`（四通股份），窗口内分别 1 / 14 / 14 个 bar，合计 **29 个标的日（占 1.07%）** —— 这 3 只有可能是真实摘帽或退市，不影响结论。

195 只同时在「10-19 之前是 ST」和「11-05 名称仍是 ST」，中间只有那一次批量 False —— 不可能是真实状态变化。

**（3）异常度对比（按 `flag_date` 的 False 行数排序）**

| 排名 | flag_date | False 行数 | 说明 |
| --- | --- | --- | --- |
| — | 2019-01-01 | 3,560 | 口径基线：建表时「从首根 bar 起即非 ST」，不计入异常 |
| 1 | **2026-10-20** | **198** | 本文事件 |
| 2 | **2026-09-05** | **193** | 同形态，周六，已回滚 |
| 3 | 2020-07-27 | 31 | |
| 4 | 2019-07-22 | 25 | |

True 行数排名第一同样是 **2026-09-07 的 200 行**（第二名 2019-01-02 的 76 行）。两次事件的量级比历史任何一次大 4–6 倍，且成对出现（False 之后紧跟 True 回滚）。

### A.5 198 这个数字能不能与某个具体名单对上

**不能，也不需要。** 它不对应任何外部文件，而是两个彼此独立的条件的交集余数：

```
as-of 2026-10-19 的 ST 全集      218 只
  减去「行情序列已终止、不再有观测」  20 只
  ─────────────────────────────────────
  = 当日被写 False 的             198 只
```

佐证：198 只中 **194 只**在 10-20 当天有 bar、**195 只**在 14 日窗口内有 bar；余下 3 只（`000016.SZ` \*ST康佳A、`002717.SZ` \*ST岭南、`688496.SH` \*ST清越）窗口内已无 bar，但序列一直延续到 10-20 之前（最后 bar 均晚于 2026-09-03），仍在「有观测」一侧。20 只保留组窗口内 **0 个**标的日、最后 bar ≤ 2024-08-14。分界不是「当天有没有 bar」，而是「序列是否已经终止」。

### A.6 可修性判断

| 路径 | 可行性 | 代价 / 风险 | 结论 |
| --- | --- | --- | --- |
| **① 源侧重采**（对 198 只重跑 `backfillStatusLiquidity`，补齐 10-20…11-06 的 `isST`） | **可行，且是唯一根治** | 需 BaoStock 在线、逐股 198 次请求；且**必须先修 `mergeConsecutiveRuns` 的 null 语义**，否则重采一次再断供就再闭合一次 | 建议与 ② 合并执行 |
| **② 改合并函数**：`isST === null` 不参与闭合（保留区间不等、只标记缺测），即落实注释里写的「跳过」 | 可行，改动局部（1 个函数 + 单测） | 属 `backend` 之外的源仓库，需走系统开发流程 | **建议同步排期**，否则 ① 白做 |
| **③ 换源**（改为公告/权威 ST 名单） | 长期正解 | 需要新数据源与合同；当前无 | 不在本批范围 |
| **④ 生产侧继续按 null** | 已完成（契约 `st_unknown_windows`） | 无新风险，但 ST 相关因子在 14 日内不可判 | **建议作为唯一短期口径** |

**四项合起来的建议**：短期维持 ④（现状即正确降级）；中期做 ②（改 null 语义）+ ①（重采并重导出）；③ 另立项。**不建议**只做 ①，因为源端缺测语义不改，下一次断供会重演同一事故。

另有一条独立风险：`part.parquet` 的 `max(flag_date)=2026-10-29`，而行情已到 2026-11-06 → **`st_history` 自身已停更 6 个交易日**。无论是否回填，这个停更都必须先解决，否则 10-30 之后同样是 null。

### A.7 回填影响评估（供决定，未执行任何回填）

窗口：`2026-10-20 … 2026-11-06`，共 **14 个交易日**。

| 指标 | 数值 |
| --- | --- |
| 全市场有 bar 的标的日 | 77,974 |
| 198 只在该窗口有 bar 的标的日 | **2,709** |
| ├ 其中当前名称仍含 ST（195 只） | **2,680** |
| └ 名称不符（3 只） | 29 |
| 20 只未闭合组在该窗口有 bar 的标的日 | **0** |
| 每日 `ST=True` 家数：现状 | **20**（14 日恒定） |
| 每日 `ST=True` 家数：回填后 | **218**（14 日恒定，回到 10-19 水平） |
| **会被 `in_universe` 从「可交易」改为「排除」的标的日** | **2,680** |

即：回填会让 **2,680 个标的日**（占窗口全市场标的日的 3.44%）从「可交易」变为「排除」。规模可控、方向明确（这些标的客观上仍带 ST）。逐日数值见证据 JSON 的 `A_window_and_backfill_impact.per_day`。

---

## B｜7 条「缺数据环境」失败的真实前置

### B.0 判据的第一次反证：真数据目录下 0 条变绿

在干净检出 `286c1c86` 的 `backend` 下逐条单跑，两套环境各跑一遍：

| 环境 | 7 条结果 |
| --- | --- |
| 无 `TSP_DATA_DIR`（原判定环境） | 7 条全红 |
| `TSP_DATA_DIR=D:/TSP/data`（真数据） | **7 条全红，0 条变绿** |

**「缺数据环境」这个分类不成立**：把真实数据目录指给它们，一条都没通过。

### B.1 逐条表

| # | test id | 依赖（真实前置） | 实测错误 / 抛出点 | 本机 `D:/TSP/data` 缺什么 | 补齐路径 |
| --- | --- | --- | --- | --- | --- |
| 1 | `tests/test_assistant_actions.py::test_check_data_coverage_reports_gaps` | `ToolContext.analysis` 适配器 | `ValueError: 行情分析服务未就绪` @ `app/custom/assistant/tools.py:287` | **什么都不缺**（数据由测试在 tmp_path 造） | 测试侧：`ToolContext.build(data_dir=..., repo=<stub>)`，stub 只提供 `.store.data_dir` |
| 2 | `…::test_check_data_coverage_fresh_data_has_few_issues` | 同上 | 同上 | 同上 | 同上 |
| 3 | `…::test_check_data_coverage_weekend_with_friday_data_has_no_lag_issue` | 同上 | 同上 | 同上 | 同上 |
| 4 | `…::test_check_data_coverage_symbol_lagging` | 同上（`daily_missing` 依赖 `dataset_dates` 非空） | `assert False is True` @ `tests/test_assistant_actions.py:406` | 同上 | 同上（该测试已有 `_StubRepo`，但缺 `.store.data_dir`） |
| 5 | `tests/test_strategy_run_all_parallel.py::test_parallel_run_all_matches_sequential_results` | `run_all` 默认选中的策略集 | `ValueError: selected strategies require history data` @ `app/strategy/engine.py:1475` | **什么都不缺**（策略代码在 tmp_path） | 测试侧：显式传 `strategy_ids=[cheap_a, cheap_b, cheap_c]`，或给 `context` 一个 history stub |
| 6 | `…::test_parallel_run_all_preserves_failure_semantics` | 同上 | `AssertionError: Regex pattern did not match` @ `tests/test_strategy_run_all_parallel.py:111` | 同上 | 同上（第 5 条修好后此条随之通过） |
| 7 | `tests/backtest/test_matrix_strategy.py::test_research_factor_catalog_matches_matrix_features` | panel 需有 `raw_close` 列 | `ValueError: in_universe 缺少必需列: ['raw_close']` @ `app/custom/research_universe_pack/universe.py:111` | **缺的是列，不是数据集** | **实现侧**：矩阵路径补 `in_universe`（契约已列 B0b）+ 提供 `raw_close`；补数据无用 |

### B.2 三条根因归纳

**根因 1（4 条 assistant）：实现比测试新 7 天，读覆盖率的入口从 `data_dir` 挪到了适配器。**

- `tests/test_assistant_actions.py` 最后修改 **2026-10-29**
- `backend/app/custom/assistant/tools.py` 最后修改 **2026-11-05**：`_check_data_coverage` 在 `:1050` 新增 `analysis = _require_analysis(ctx)`，数据集日期改由 `analysis.dataset_dates(...)` 提供
- `backend/app/extensions/adapters.py` 最后修改 **2026-11-07**：`RepositoryAnalysis.dataset_dates`（`:310-327`）**经 `repo.store.data_dir` 目录列举**取日期
- 而 `ToolContext.build`（`tools.py:184`）只在传入 `repo` 或 `quote_service` 时才构造 `analysis`

测试写于 10-29，用的是「只给 `data_dir` 就够」的旧契约。第 4 条虽然给了 `_StubRepo`，但它的接口是旧的（`resolve_asset_type` / `get_daily_asset`），没有 `.store.data_dir` → `dataset_dates` 返回 `[]` → `daily_missing` 恒为 `False`（`:1022` 要求 `global_daily_latest` 非空）。

**反证已做**：`research/e3-data-availability-20261107/probe_b_fixtures.py` 用 12 行 stub repo（只挂一个 `.store.data_dir`），在 `tmp_path` 上让 `_check_data_coverage` 通过全部断言，**不需要任何真实数据、不需要起服务**：

```
analysis is None when repo/quote_service absent -> '行情分析服务未就绪, 请确认后端已完成启动。'
  daily_present = True
  daily_latest = 2026-11-01
  enriched_present = False
  has_lag_issue = True
  has_enriched_issue = True
  has_financial_issue = True
FIXTURE REPRODUCES TEST ASSERTIONS: True
```

**根因 2（2 条 parallel）：`run_all` 不传 `strategy_ids` 时，选中面含需要 history 的后端。**

- `engine.py:1475`：`if history_strats and shared_history is None: raise ValueError(...)`；`history_strats` 判据是 `strategy.filter_history_fn` 或 `execution_backend in ("matrix_native", "minute_filter")`（`:1467-1472`）
- 测试的 `_FILTER_TEMPLATE`（`tests/test_strategy_run_all_parallel.py:18-31`）只有 `META` 四字段、没有 `execution_backend`；默认值虽是 `polars_expr`（`engine.py:212`，不需 history），但 `run_all(context, parallel=...)` **不传 `strategy_ids`**，选中面大于这 3 个模板策略
- **反证已做**：显式传入这 3 个 polars 策略时，串行与并行命中数 **24 / 19 / 14 完全一致** —— 并行逻辑本身无问题，失败来自选择面
- 第 6 条的 `regex did not match`（`tests:111` 期望 `injected strategy failure`）是次生现象：`:1475` 先抛了 `require history data`，根本没走到注入失败

**根因 3（1 条 matrix）：缺的是 `raw_close` 列，且矩阵路径本就没有 `in_universe`。**

- `in_universe` 必需列 `['amount','date','raw_close','symbol','volume']`，而 **`raw_close` 不是注册因子**（`FACTOR_COLUMNS` 无此 id），物化链不会产出它
- 即便补上该列，矩阵路径仍无实现：`app/backtest/matrix.py:4226` `raise ValueError("unsupported matrix feature")`；`research_universe_pack/factor_provider.py:9` 明确写「把矩阵侧 `in_universe` 列为 B0b 另批，本批不动矩阵路径」
- **反证已做**：把 `in_universe` 这类 provider 因子排除后，同一条测试的 77 个矩阵原生因子 **77 PASS / 0 FAIL**
- 因此**不是缺数据，是实现缺口**；按「缺数据 → skip」标注会把 B0b 永久掩盖（`docs/architecture/B2_ACCEPTANCE_20261107.md:200` 已记录该测试在 `all_on` 仍红并掩盖 8 个 B0 id）

### B.3 该不该 skip

**不该。** 正确处置：

| 组 | 处置 | 归属 |
| --- | --- | --- |
| 4 条 assistant | 改测试：`ToolContext.build(..., repo=<stub 带 .store.data_dir>)` | 测试侧，半天 |
| 2 条 parallel | 改测试：`run_all(..., strategy_ids=[3 个模板 id])` | 测试侧，半小时 |
| 1 条 matrix | **保持红**，挂到 B0b 实现项；不得 skip | 实现侧（系统开发工程师） |

---

## C 可复跑命令与文件

| 文件 | 内容 |
| --- | --- |
| `research/e3-data-availability-20261107/probe_a_st_origin.py` | A 全部数字（区间 → 事件 → 窗口 → 回填影响），重算并写 JSON |
| `research/e3-data-availability-20261107/probe_b_tests.py` | B 的 7 条在两套环境下逐条复跑（参数 `clean` / `data`） |
| `research/e3-data-availability-20261107/probe_b_fixtures.py` | B 根因 1 的最小 fixture 反证（stub repo 即通过断言） |
| `docs/factors/evidence/e3_followup_a_st_origin_20261108.json` | A 证据（含逐日 ST 家数与回填前后对比） |
| `docs/factors/evidence/e3_followup_b_tests_20261108.json` | B 证据（7 条 × 两套环境 × 错误原文 × 抛出点） |

```bash
cd C:/work/sourcecode/tick-stock-panel
PY=backend/.venv/Scripts/python.exe
$PY research/e3-data-availability-20261107/probe_a_st_origin.py     # → A 证据 JSON
$PY research/e3-data-availability-20261107/probe_b_fixtures.py      # → 根因 1 的 stub 反证
$PY research/e3-data-availability-20261107/probe_b_tests.py clean   # → 无 TSP_DATA_DIR，7 条全红
$PY research/e3-data-availability-20261107/probe_b_tests.py data    # → TSP_DATA_DIR=D:/TSP/data，仍 7 条全红
```

---

## D 未证 / 未做

**未证（本机无此证据源，不做推断填补）**

1. **198 只对应标的在 10-20 之后的 `isST` 究竟是空串、缺失，还是真为 0** —— 源库 `research_security_status_history` 在 `stock-limit-up-analyzer` 的数据库里，本机无该库、也无法调 BaoStock 在线接口。**已确证链条两端**（合并函数把 null 当非 ST；结果与真实名称矛盾），中间那一次调用未见原始返回。
2. **20 只未闭合标的在源库里的区间 `effectiveTo` 是否为 NULL** —— 由导出末行为 True 反推应当如此，但未读到源库行。
3. `st_history` 的 writer 脚本不在 `tick-stock-panel` 与 `stock-limit-up-analyzer` 任一仓库内，未能读到其日期算术（尤其 `flag_date` 为何会落在周六 09-05）。

**未做（按任务边界）**

- 未改 `backend/**`、未改 `docs/factors/**` 既有结论、未回填 `st_history`、未跑回测、未 commit、未改契约。
- 未对 20 只未闭合标的做「是否真退市」判断 —— 那是 E3 已冻结的「退市日不可得」口径，本批不重开。

---

## E 需要开发经理裁定的两件事

1. **A 的修法**：是否采纳「短期维持 null（④）+ 同步排期改 `mergeConsecutiveRuns` 的 null 语义（②）并重采重导出（①）」。只做 ① 会复发 —— 源端缺测语义不改，下次断供照样闭合。
2. **`st_history` 自身停更 6 个交易日**（`max(flag_date)=2026-10-29` vs 行情到 2026-11-06）是否单独立项。它与 10-20 事件是两个独立缺口：回填 10-20 那批并不能补上 10-30…11-06。
