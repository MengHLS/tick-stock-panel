# 迁移说明（旧产物如何被取代）

旧证据不覆盖、不删除：`out/`、`out_v2/`、`archive/` 原样保留。本文件说明哪些旧结论作废、由谁取代。
当前有效证据：`out_v3/`（见 `REPORT-F1F3.md`）。

## 1. 文件代际

| 文件 | 角色 | 状态 |
|---|---|---|
| `run_batch.py` | 批量底座（当前版本） | 有效；顶部说明已改为 `engine_execution_count` / `hypothesis_count` 双口径 |
| `verify_batch.py` | v1 比较器（全局 `SKIP_KEYS`） | **作废**，原地保留；同内容另存 `archive/verify_batch_v1_as_delivered.py` |
| `verify_batch_v2.py` | v2 比较器（F1/F3 修复） | 有效 |
| `mutation_checks.py` | 负向变异 + 轴证明正负对照 | 有效 |
| `groups.json` / `groups_g2.json` | 策略清单（每组单参数组合） | 有效 |
| `probe_*.py` | 装载/轴探针（只读） | 保留，非交付路径 |
| `REPORT.md` | v1 报告 | **部分作废**（见第 3 节），顶部已加迁移提示 |
| `REPORT-F1F3.md` | F1/F3 修复与证据 | 有效 |
| `WORKLOG.md` | 施工日志（v1 阶段） | 历史记录 |

## 2. 证据目录

| 目录 | 代码指纹 | 比较器 | 结论 | 状态 |
|---|---|---|---|---|
| `out/` | 早期 | `verify_batch.py`（v1） | `result_diffs=0` | **作废**：v1 跳过 `total_return`/`continuous_account`，曲线与逐笔从未比对 |
| `out_v2/verify_v2/` | `28bddd65…` | `verify_batch_v2.py`（EXEMPT 修正前） | `result_diffs=64` | **作废**：比较器缺陷（计时字段被当成结果差异），非底座缺陷 |
| `out_v2/verify_v3/` | `28bddd65…` | `verify_batch_v2.py`（修正后） | `result_diffs=0` | 保留作修复前后对照；**不应单独引用**（代码指纹已过期） |
| `out_v3/` | `1856c1a2…` | `verify_batch_v2.py` + `mutation_checks.py` | `0` 差异、20/20 变异检出、轴证明通过 | **当前有效** |

`out_v2 → out_v3` 代码指纹变化的原因：`run_batch.py` 顶部说明改写（把 `n_trials` 改为双口径表述）。
按 F3 绑定规则，代码哈希一变，旧批次结论即失效，因此重跑了一整代，而不是复用 `out_v2`。

## 3. 撤回/修正的具体表述

1. **`REPORT.md` §4 的 `n_trials=12`、`n_trials_cumulative 6→12` 作废。**
   registry v2 没有 `n_trials` 字段。正确口径：`engine_execution_count` 每组 6、合计 12（引擎评估调用次数，
   含 IS 网格 trial 与 OOS 折回放）；`hypothesis_count` 每组 1、合计 2。**12 不是假设个数 N**。
2. **`REPORT.md` 的“与单跑逐字段差异 0”不能理解为覆盖曲线/逐笔。**
   当时用的是 v1 比较器；现在的 0 差异是 `verify_batch_v2.py` 在完整曲线（189/189）、完整逐笔（325/325、246/246）
   与全部连续账户字段上得出的，并对 20 种单点变异做了检出验证。
3. **`out_v2/verify_v2` 的 64 条差异不要当成底座 bug 修。**
   那是路径分类缺陷：`oos_folds[*]` 的段匹配没把下标段算进去，导致 `*_ms` 计时字段落进结果差异。
   修法是把豁免改为精确路径匹配（`timing_ms.*` 等），而不是放宽比对。
4. **`mutation_checks.py` 首版轴证明探针用合成观测对象，正向被判 false。**
   已改为读取比较器实跑落下的真实装载轴；那次失败报告保留在
   `out_v2/verify_v3/mutation-report.attempt1-axisprobe-failed.json`。

## 4. `REPORT.md` 的改动（透明记录）

只在文件顶部插入一行迁移提示（指向 `REPORT-F1F3.md` 与本文件），**正文一字未改**。

| 阶段 | SHA-256 |
|---|---|
| 改动前 | `985caf05597e24ef9379d05b4f68056b4a25e2771ff42d5ab7229ba542ce1bc7` |
| 改动后 | `69332ae28728c0f22e1110582c4d360b1ef161ae0dfa8d71075f98295c631f04` |

验证方式（可自行复核）：把当前 `REPORT.md` 的前两行（提示行 + 空行）去掉后取 SHA-256，
结果应等于上表的“改动前”哈希。实测已相等，即正文（含所有数字与命令）一字未改。

## 5. 复验入口

见 `REPORT-F1F3.md` 第 8 节，三条命令，期望退出码 `0 / 0 / 0`。
