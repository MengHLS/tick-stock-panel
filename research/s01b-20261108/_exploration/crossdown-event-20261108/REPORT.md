# cross_down 事件式语义修正 — 独立改动集 · 验收报告

- 日期：2026-11-08（Asia/Shanghai，18:08–18:3x）
- 对象：`D:\TSP\data\strategies\custom\custom_mw7fvp17.py`（S01 原样：`META.id/name/description/tags` 全部不动）
- 改动集：**1 行**，把水平式卖点改成事件式（与引擎实际行为对齐）
- 结论：改动落地、A/B **逐字节 IDENTICAL**、边界专项**全窗 0 例分歧**、前端与装载复核通过
- 纪律：未提交、未部署、未重启；未碰 `backend/`、`dsl.py`、信号链、回测引擎核心、`store.py`、其它 11 条策略、`D:\TSP` 生产库 strategy row；上游研究侧 `REPORT.md`/`PREREG`/`metrics.json`/`report_metrics.py` 未改动

---

## 1. 改动集（唯一一处）

```diff
--- custom_mw7fvp17.py.before   (3449 B / 61c237c6…)
+++ custom_mw7fvp17.py.after    (3478 B / 85ae72a5…)
@@ -92,5 +92,5 @@
         prev_slow = np.asarray(valid_shift(slow, 1), dtype=np.float64)
         cross_up = (fast > slow) & (prev_fast <= prev_slow)
-        cross_down = fast < slow
+        cross_down = (fast < slow) & (prev_fast >= prev_slow)
         momentum = np.asarray(matrix_feature(market, "momentum_20d"), dtype=np.float64)
```

字节级证明（`byte_diff_proof.py`，退出码 **0**，产物 `results/byte_diff.txt` / `byte_diff.json`）：

| 判据 | 实测 |
|---|---|
| 行数 | 105 → 105（不变） |
| 变动行号（1-based） | **仅第 94 行** |
| diff 行对 | 1 removed + 1 added（= 1 个逻辑行） |
| 字节差 | +29 B（3449 → 3478） |
| 单行回改能否还原原字节 | **roundtrip_restores_pre_bytes = True** |
| BOM / CRLF | 无 BOM；CRLF 105 → 105 |
| VERDICT | **ONE_LINE_ONLY** |

`prev_fast` / `prev_slow` 两行**原本就在文件里**（第 91–92 行），无需新增，因此改动确实只有这一行。未加 `TRAILING_*`、未动 `STOP_LOSS=None` / `MAX_HOLD_DAYS=60`、未写 `backtest_defaults`（`backtest_defaults` 由运行期内存注入，磁盘上没有）。

### 文件前后（全串 sha256）

| 时点 | 路径 | size | sha256 |
|---|---|---|---|
| 改前 | `D:\TSP\data\strategies\custom\custom_mw7fvp17.py` | 3449 | `61c237c6cdb2a4391524c48982cd7529606f1ce9d6dabf235527ff702f94b2dd` |
| 改后 | 同上 | 3478 | `85ae72a5318523d1515903314a817ca5a75cd07b33790cefe0d7b5acea794a07` |

### 备份（`.bak_20261108` 未覆盖、未改动）

| 文件 | size | sha256 | mtime | 说明 |
|---|---|---|---|---|
| `custom_mw7fvp17.py.bak_20261108` | 3449 | `61c237c6…f94b2dd` | **2026-11-08 14:19:54** | 14:19:54 基线的唯一证据，原样保留（`bak_20261108_untouched = True`） |
| `custom_mw7fvp17.py.bak_crossdown_20261108` | 3449 | `61c237c6…f94b2dd` | 2026-11-08 18:08:34 | 本轮改动前副本，与上者逐字节相同 |
| `research/s01b-20261108/prod_file_snapshots/custom_mw7fvp17.py.pre_crossdown_3449B_61c237c6.py` | 3449 | `61c237c6…f94b2dd` | — | 研究侧改动前快照（byte_identical=True） |

---

## 2. 验收 ①：同管道同口径 A/B（改前 vs 改后）

管道与口径：生产装填（`StrategyEngine` 读 `D:\TSP\data\strategies\custom`）+ `StrategyBacktestService` 正式回测；2019-07-01…2026-10-30；10bp 滑点、佣金 3bp／印花税 10bp；1,000,000 元、最大 5 仓、60% 敞口、`matching=open_t+1`、等权、`holding_days=60`；S01 执行口径按**内存注入**（`entry_price_basis=raw` / `block_limit_open` / `finalize_open_at_end` / `min_commission=5` / `transfer_fee=2e-6`），磁盘文件不动。

两臂各自打印**实际加载的文件**，防止两端比同一份代码：

| 臂 | 加载路径 | size | sha256 | `cross_down` 行 |
|---|---|---|---|---|
| A（改前） | `strategies_prepatch\custom\custom_mw7fvp17.py` | 3449 | `61c237c6…` | `cross_down = fast < slow` |
| B（改后） | `D:\TSP\data\strategies\custom\custom_mw7fvp17.py` | 3478 | `85ae72a5…` | `cross_down = (fast < slow) & (prev_fast >= prev_slow)` |

结果（`ab_crossdown_verify.py` 两臂退出码均 **0**，`error=None`）：

| 项 | 臂 A（改前） | 臂 B（改后） |
|---|---|---|
| 笔数 | **199** | **199** |
| equity 行 | 1779 | 1779 |
| total_return / annual_return | 0.2427 / 0.0313 | 0.2427 / 0.0313 |
| max_drawdown / sharpe | -0.3927 / 0.25 | -0.3927 / 0.25 |
| completed / open_at_end | 194 / 5 | 194 / 5 |
| avg_holding_days / final_equity | 45.3 / 1,242,725.28 | 45.3 / 1,242,725.28 |
| exit_reason | end 5 / max_hold 58 / signal 136 | end 5 / max_hold 58 / signal 136 |

逐单元格比对（`compare_exact.py vA_prepatch vB_postpatch`，退出码 **0**，产物 `results/compare_vA_prepatch_vs_vB_postpatch.json`）：

```
trades: rows=[199, 199] cols_identical=True diff_columns={} exact_equal=True parquet_bytes_identical=True
equity: rows=[1779, 1779] cols_identical=True diff_columns={} exact_equal=True parquet_bytes_identical=True
stats_diff={}
VERDICT: IDENTICAL
```

- trades **22 列**（symbol…open_at_end）逐单元格全等，`diff_columns = {}`
- equity **5 列**（date/value/cash/positions/exposure）逐单元格全等，`diff_columns = {}`
- 除 `timing_ms`（墙钟计时，非回测结果，已单列排除）外 `stats_diff = {}`
- 第二证人：两个 parquet **字节同 hash** — trades `639be869…`（22,854 B）、equity `1fa5003b…`（18,918 B）

### 旁证：另一执行口径（不注入 defaults，208 笔）也全等

`a0_10bp`（改前）vs `a1_10bp`（改后）：208/208 笔、22 列全等、equity 1779 行全等、两 parquet 字节同 hash（trades `d595d31c…`、equity `b0d16128…`）。另外 `diag_a0arm`（研究侧 s01b_a0 臂）与 `c0_10bp`（改前生产文件 + 注入 defaults）**199 笔逐笔全等**，说明"改前生产文件 = 研究 a0 臂"这条对齐成立。

> 研究侧 252 笔未复现，也不该复现：它需要新增自定义信号列（= 改信号链），按裁定仍然禁止，没有去做。生产路径笔数 **199**，与要求一致。

---

## 3. 验收 ②：边界专项（事件式 vs 水平式必然分歧的情形）

判据：全窗枚举"水平式 `cross_down`（`fast < slow`）为真、但该持仓当天无法出场（`blocked_exit_days>0` 或 `tradable=False` / `limit_down_locked`）"的情形；这类情形下水平式次日仍能出、事件式不能，两式**必然分歧**。

全窗统计（`boundary_crossdown.py`，生产目录，199 笔口径，退出码 **0**，产物 `results/boundary_crossdown_c199.json`）：

| 指标 | 值 |
|---|---|
| 窗口 / 交易日 / 标的 | 2019-03-04…2026-10-30 / 1,859 / 5,811 |
| 有特征单元格 | 8,522,133 |
| 水平式为真（`fast<slow`） | **4,524,733** |
| 事件式为真（`fast<slow & prev_fast>=prev_slow`） | **89,179** |
| 仅水平式为真（level-only） | **4,435,554**（占水平式 98.03%） |
| 持仓期内出现 level-only 日的笔数 | **136 / 199**（共 137 个 level-only 持仓日） |
| **闩锁日落在 event 日** | **136** |
| **闩锁日落在 level-only 日** | **0** |
| 有 blocked_exit 的笔数 | **1** |
| 与改后逐笔一致的笔数 | **199 / 199** |

唯一有 blocked_exit 的那笔（网格见 `results/boundary_blocked_table_c199.md`）：

| symbol | entry | exit_signal_date | exit_date | 闩锁日类型 | blocked_exit_days | duration | pnl_pct | 持仓内 level-only 日 | 落在不可卖日的 level-only 日 |
|---|---|---|---|---|---|---|---|---|---|
| 603580.SH | 2024-03-20 | 2024-06-06 | 2024-06-11 | event_day | 1 | 53 | -0.3798 | 2 | 0 |

判读：该笔 06-06 两式**同时为真**（事件日），06-07/06-11 之间的不可卖日之前信号已经闩锁；06-11 的 level-only 日发生在已挂单、且当天即为成交日之后，不构成分歧。**全窗 0 例"首个触发日不可卖、且此后只有水平式为真"的情形。**

### 为什么必然是 0 例（代码 + 数据双证，不是巧合）

1. **语义关系**：事件式 = 水平式的上升沿，因此两式的**首个为真日恒相同**（事件式 ⊆ 水平式，且首次出现位置一致）。
2. **引擎按首次触发日闩锁**：`backend/app/backtest/engine.py:2855 _exit_signal_at()` 用 `matrix.source_exit` 在**信号日 T** 判卖点；命中后 `:4165` 写 `pos["next_open_exit_reason"]="signal"` 并 `continue`，次日开盘执行（`:3945 _try_sell(...)`）；若当日不可卖则 `:4376` 写 `pending_exit_reason`，之后 `:4144 if pos.get("pending_exit_reason"): … continue` 不再重新判信号。即：**一旦闩锁，后续 level-only 日不会再触发第二次卖点**。
3. **数据证**：改前抓到的 `signals.exit` 与"水平式"逐单元格**全等**（4,524,733 / 4,524,733，`level_raw=True`）；改后与"事件式"**全等**（89,179 / 89,179，`event_raw=True`）。即补丁确实生效，而两式在这个引擎里行为等价。
   - 改前抓取（`strategies_prepatch` 目录，退出码 2 = 脚本内 `ok` 判据要求 `event_raw` 且逐笔一致，改前本就是 level 式，属**预期**失败）：`logs/boundary_c199_prepatch.log`，产物 `results/boundary_crossdown_c199_prepatch.json`
   - 改后抓取（生产目录，退出码 0）：`logs/boundary_c199.log`

---

## 4. 验收 ③：前端与装载复核（只读，未启动/重启服务）

`verify_list_crossdown.py`（退出码 **0**，产物 `verify_list_crossdown_result.json`，日志 `logs/verify_list_final.log`）：

| 判据 | 实测 |
|---|---|
| `list_strategies(include_research=False)` 条数 | **5**（含 `custom_mw7fvp17`） |
| `name` | **双均线 20/60 金叉** |
| `tags` | **["趋势","双均线","S01"]** |
| `backtest_defaults` | **{}**（`backtest_defaults_empty=True`） |
| `description` | 基线原文 |
| 生产装载 | **10 条**，`load_errors = []` |
| VERDICT | **FRONTEND_OK** |

---

## 5. 生产目录终态（`results/prod_dir_state.json`，退出码 0，VERDICT OK）

| 文件 | size | sha256 |
|---|---|---|
| `.seeded_v1` | 24 | `85d51c292ad2b4eb47a5bcf35696794cf21c9c3f2f307c365ccd6e10aab5d1c0` |
| `custom_factor_first_board_chain_strict_rebreak.py` | 1394 | `7fc46deb96b14f6c84aa172969471277007cc8a8398e43b024f446f18781d8cc` |
| `custom_khunter_limit_up_pullback.py` | 12122 | `684f5e82a7eff380ce58cd4d927aa80e925726f5f8170b4f57a2bc464ce3a4e5` |
| `custom_mvoa5yy6.py` | 10741 | `36b6bf61829d6fbd71cd48df7ea82dbab1c470c01c683fb76eb2f512fbc79be2` |
| `custom_mvoa5yy6.py.bak-20261026-gap-filter` | 10578 | `c03c962cad5aa4b0ea654f49b256f5d9b5f05ed4ddd2fda903c3f10e20669b63` |
| **`custom_mw7fvp17.py`** | **3478** | **`85ae72a5318523d1515903314a817ca5a75cd07b33790cefe0d7b5acea794a07`** |
| `custom_mw7fvp17.py.bak_20261108` | 3449 | `61c237c6cdb2a4391524c48982cd7529606f1ce9d6dabf235527ff702f94b2dd`（mtime 14:19:54） |
| `custom_mw7fvp17.py.bak_crossdown_20261108` | 3449 | `61c237c6cdb2a4391524c48982cd7529606f1ce9d6dabf235527ff702f94b2dd` |

无 `.step1` / `.py.tmp` / `.variant` / `.new` 中间件；除目标文件被改写与本轮新增的两个备份外，未新增/改动任何文件（`__pycache__/` 内 `.pyc` 因源文件变化由导入机制自动重编译，非手工写入）。

---

## 6. 命令与退出码

| # | 命令 | 退出码 | 产物 |
|---|---|---|---|
| 1 | `python _backup.py`（上一轮 18:08） | 0 | `logs/backup.log`（BACKUP_OK，两份备份均 byte_identical=True） |
| 2 | `python _apply_patch.py` | 0 | `logs/apply_patch.log`（PATCH_OK，roundtrip=True） |
| 3 | `python ab_crossdown_verify.py --strategies-dir strategies_prepatch\custom --tag vA_prepatch` | 0 | `results/vA_prepatch/`、`logs/ab_vA.log` |
| 4 | `python ab_crossdown_verify.py --strategies-dir D:\TSP\data\strategies\custom --tag vB_postpatch` | 0 | `results/vB_postpatch/`、`logs/ab_vB.log` |
| 5 | `python compare_exact.py vA_prepatch vB_postpatch` | 0 | `results/compare_vA_prepatch_vs_vB_postpatch.json`（VERDICT IDENTICAL） |
| 6 | `python byte_diff_proof.py` | 0 | `results/byte_diff.txt`、`results/byte_diff.json`（ONE_LINE_ONLY） |
| 7 | `python boundary_crossdown.py --strategies-dir D:\TSP\data\strategies\custom --trade-a c0_10bp --trade-b c1_10bp --inject-defaults s01_defaults.json --out-tag _c199` | 0 | `results/boundary_crossdown_c199.json`、`boundary_blocked_table_c199.md` |
| 8 | 同 7，`--strategies-dir strategies_prepatch\custom --out-tag _c199_prepatch` | 2（**预期**：改前是 level 式，脚本 `ok` 要求 `event_raw`） | `results/boundary_crossdown_c199_prepatch.json` |
| 9 | `python verify_list_crossdown.py` | 0 | `verify_list_crossdown_result.json`（FRONTEND_OK） |
| 10 | `python _prod_dir_state.py` | 0 | `results/prod_dir_state.json`（OK） |

解释器：`backend\.venv\Scripts\python.exe`（默认 `python` 无 polars，已改用它）。

---

## 7. 结论与留给下游的判断

- **改动成立**：只改 1 行，字节级可证（第 94 行，+29 B，回改即还原）。
- **结果不动**：同管道同口径 199 笔，trades 22 列 / equity 5 列逐单元格全等，parquet 字节同 hash，`VERDICT: IDENTICAL`。另一口径（208 笔）同样全等。
- **为什么不动**：引擎在信号日 T 判卖点、命中即闩锁到次日开盘执行，且事件式与水平式的首个为真日恒相同 ⇒ 两者在本引擎下**行为等价**；边界专项全窗 **0 例分歧**（136 笔持仓内出现 level-only 日，闩锁日 136/136 落在 event 日）。
- **这条改动的价值不在收益，而在表述**：改后策略文件 `signal.exit` 与引擎实际消费的卖点逐单元格一致（89,179/89,179），不再出现"文件写着 450 万格卖点、引擎只认 8.9 万格上升沿"的口径错觉。
- **未做/未验证**：未提交（`research/s01b-20261108/crossdown-event-20261108/` 为未跟踪目录）；未部署、未重启——若服务已在运行且已缓存该策略模块，需按运维流程重启才加载新文件；未写 `D:\TSP` 生产库 strategy row；研究侧 252 笔未复现（需改信号链，禁止）。
