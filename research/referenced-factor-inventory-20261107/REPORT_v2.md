# referenced_factor_inventory 清单 v2 —— 逐出现粒度 + summary 分层 + canonical digest

- 日期：2026-11-07
- 实现：系统开发工程师（生成器唯一实现者）
- 输入：开发经理 v2 指令（四处改动）+ 契约 §7.10.2/§7.10.3（冻结）
- 范围：只改生成器与产物。**未改后端源码、未改活配置、未提交、未部署、未重启。**
- v1 报告仍在同目录 `REPORT.md`（未被覆盖）

## 1. 交付物

| # | 路径 | 事实 |
|---|---|---|
| 1 | `backend/scripts/build_referenced_factor_inventory.py` | 46,321 B / 976 行 / sha256 `47b2cf4e784de13846aa2e5b67c706e2c75820743f9f46660484e54f0cc63ad5`；`ruff check` All checks passed |
| 2 | `docs/architecture/evidence/referenced_factor_inventory.json` | 152,826 B / 218 记录 / sha256 `2b9bb771b495251e6239eab0b1baf2b02e1e6746c1f1077f43479ba5c0bbe8c1` |
| 3 | `docs/architecture/evidence/referenced_factor_inventory.json.sha256` | 99 B，内容即上列字节摘要（`sha256sum -c` 通过） |
| — | **新指标** `canonical_sha256` | `16fb5c30c63a64645606d6e82051a73866dfa450939f616334d194b72410db07`（两次生成相同，可作签认锚点） |

v1 → v2 脚本：36,946 B / 814 行 / sha `7cf587a8…b31d` → 46,321 B / 976 行 / sha `47b2cf4e…3ad5`（+162 行）。

## 2. 四处改动怎么落的

| # | 指令 | 实现 |
|---|---|---|
| 1 | 粒度改逐出现，加 `side` | `emit()` 收 `occurrences: [(side, 名字)]`，**不再按名字去重**；条件表达式由 `_condition_occurrences()` 产出 `L` / `R` / `R:field`；monitor 用 `field`；scoring 键 `scoring`；公式 `formula`；composite `members`；research `fields.<名>`。`side` 经 `evidence_for(side, raw)` 一路传到产物，是第 18 个字段 |
| 2 | 伴生记录按出现处 | 伴生记录与主记录**成对逐出现**产出（同一 `side`、同一行号，`both_collision=true`、`verdict=exempt`），`both_collision` 判定收紧为「名 ∈ `ALLOWED_FIELDS` ∧ 注册表 class ∈ {custom_dsl, custom_python, composite}」 |
| 3 | summary 分层 | `summary.live_config`（`source_enabled=true` 的 22 源，含 `by_source_verdict`）与 `summary.all_records`（全量，含 `by_source_kind`）分开；各层 `by_*` 只统计非伴生记录，另有 `judged_records` / `companion_records` 明示；顶层 `notes` 四条写清「伴生不参与放行」「L2 只读 live_config」 |
| 4 | canonical digest | 新函数 `canonical_digest()`：剔除 `generated_at` 与自身后 `json.dumps(..., sort_keys=True)` 取 sha256；写进顶层 `canonical_sha256`（第 3 个键）并在 stdout 打印 |

`LineIndex` 新增 `find_occ()`：JSON 无行号，按「同一 token 在本文件第 N 次出现 → 第 N 个匹配行」取证据行，取代原先的「首匹配」。**这是逐出现能给出不同 evidence 行号的前提**（见 §4 的 9/16、11/18、12/17）。

## 3. 两张计数表

### 3.1 源级（`summary.live_config`）

| 项 | 值 |
|---|---|
| 活配置源 | **22**（custom_signal 21 + monitor_rule 1） |
| 源级 verdict | **allow 22 / shadow 0 / block 0 / unknown 0** |
| 记录（含伴生） | **93** = 判定 79 + 伴生 14 |
| 判定记录 by_verdict | **allow 79** |
| 判定记录 by_namespace | column 79 |
| 判定记录 by_class | base 79 |
| path_scope | history 21 源 / intraday 1 源 |

22 源逐条：`broken_limit_up` 5、`limit_down_recovery` 7、`new_height_3` 6、`ma10_breakdown`/`ma10_breakout`/`ma20_breakdown`/`ma20_breakout`/`ma5_breakdown`/`ma5_breakout`/`ma_dead_5_20`/`ma_golden_20_60`/`ma_golden_5_20`/`macd_dead`/`macd_golden` 各 4、`limit_down`/`limit_up` 各 3、`boll_breakdown_lower`/`boll_breakout_upper`/`n_day_high`/`n_day_low` 各 2、`volume_surge` 1、`lot_1a1aa285978_521c_p` 2 = **79**。

### 3.2 记录级（`summary.all_records`）

| 源类 | v1 | v2 | 差 |
|---|---|---|---|
| custom_signal | 52（44+8 伴生） | **91**（77+14 伴生） | 逐出现 |
| monitor_rule | 1 | **2** | 同名 `close` 两次 |
| strategy_override | 4 | **4** | 键唯一，无变化 |
| custom_factor | 20 | **20** | 公式依赖是集合 |
| strategy_config | 76 | **76** | scoring 键唯一 |
| research_strategy | 14 | **25** | 逐 `fields.<名>` 出现 |
| **合计** | **167** | **218** | +51 |

全量：`by_verdict` allow 97 / exempt 107；`by_namespace` column 97 / factor 107；`by_class` base 184 / custom_dsl 4 / virtual 16；`unknown 0`、`block 0`、`stale_count 0`。`side` 分布：`L` 45、`R:field` 48、`field` 2、`scoring` 78、`formula` 16、`members` 4、`fields.entry` 10、`fields.exit` 6、`fields.score` 9。

## 4. 验收逐条（命令 + 退出码）

| # | 要求 | 命令 | 退出码 | 结果 |
|---|---|---|---|---|
| ① | 两次生成除 `generated_at` 外逐字节相同 + canonical 相同 | 生成器跑 2 次（17:09:52 / 17:10:08），`diff run1.json 产出` | 0 / 0 | **只有第 3 行 `generated_at` 不同**（差异行 2 行）；`canonical_sha256` 两次均 `16fb5c30…0db07`；字节摘要 8a6d13a1…（run1） vs 2b9bb771…（run2），符合 F-A22 |
| ② | 22 源 / 79 记录 / 源级 22 allow 0 shadow 0 block | 产物 `summary.live_config` | — | **22 / 79 / 22-0-0**（自检项「活配置源数」「活配置 79 条判定」「源级 22 allow / 0 shadow / 0 block」全 PASS） |
| ③ | 7 条冲突源仍 column、伴生 14 条 | 产物 `records` | — | **column 侧 14 条 / 伴生 14 条**，`F-A24 冲突必报` PASS；7 条信号全部 `namespace=column` |
| ④ | FS01 实拦 0 | `summary` + 逐条 `code` | — | **0**（`code=FS01` 0 条；`verdict=block` 0 条） |
| ⑤ | 反向对照仍能触发 | 自检内建 2 项 | — | `ma20` 按 `both` 解析 → `divergence=true`、`verdict=block`；15 个 draft 定义逐个当因子试探 → **15/15 `block`+`FS01`** |
| ⑥ | stale 复算 0 | `recompute_stale()` | — | **0**（`stale_count` 记录值 0、复算 0） |
| ⑦ | `git status` 前后逐行相同、`backend/**` 零改动 | `git status --porcelain` 前后快照 diff | — | **逐行相同**（`diff` 空）；`backend/app/api/factors.py`(16:33:57) 与 `store.py`(16:33:52) mtime 仍是 F-A5 批次，本批未碰 |

自检 **20 项全 PASS、EXIT=0**（v1 是 13 项）：F-A22 幂等、canonical 稳定、§7.10.2 字段、**逐出现唯一**、F-A25 无 unknown、F-A26 新鲜度、活配置源数、活配置 79 条判定、活配置 14 条伴生、源级 22 allow、全量记录数、**summary 自洽**、F-A24 冲突必报、F-A23 不 grep、7 条冲突信号=column、2 virtual 不拦、FS01 实拦、path_scope 无悬空 both、N3 通道可触发、FS01 通道可触发。

运行日志：`logs/run_v2_1.txt`、`logs/diff_run1_run2.txt`、`logs/git_status_before_v2.txt` / `_after_v2.txt`、`logs/run1.json`（第 1 次产物副本）。

## 5. 口径漂移对照（v1 复算，不是估计）

用备份的 v1 脚本（`backup_v1_build_referenced_factor_inventory.py`）重放到 `logs/v1_replay.json`：**167 条、`by_verdict` allow 63 / exempt 104**，与 v1 原交付逐项相同（复现成功）。

逐键比对 (源, 名字, 是否伴生)：

| 项 | 结果 |
|---|---|
| v1 唯一键 / v2 唯一键 | 160 / **160** |
| 仅 v1 有（丢失） | **0** |
| 仅 v2 有（凭空新增） | **0** |
| 同名同源判定不一致（namespace/class/verdict/code/path_scope） | **0** |

即：**218 条只是把 160 个键里的 51 处重复出现铺开，没有任何一条判定改变。**

## 6. 与因子工程师独立期望表（`docs/factors/evidence/referenced_factor_inventory_expected_20261107.json`）的机械比对

该表本轮由因子工程师独立产出（其 `meta.independence` 声明未读我的产物与判据逻辑），我把 `role` 映射成 `side`（`left→L`、`right_field→R:field`、`field→field`）后逐出现比对：

| 项 | 结果 |
|---|---|
| 期望出现处 / 我的 live 判定记录 | 79 键 / 79 键（另有 14 条伴生） |
| 键集合差异（源 + side + 名字 + 行号） | **只它有用 0、只我有 0** |
| 行号 | 全部一致，含 `new_height_3` 的 `high` 三条 7/9、14/16、21/23 |
| 分歧 | **14 处冲突出现处的记录形态**：我 = column/`both_collision=false`/`allow` **+** factor/`both_collision=true`/`exempt` 两条；它 = 一条 column/`both_collision=true`/`exempt` |

它自己的 `summary.total_records_if_companions_are_separate` 写的正是 **93**，与我的层内 93 条同量。**对闸门行为无差别**（exempt 与 allow 都不阻断，源级 22 allow 两边相同），差别只在「exempt 标记落在哪一条记录上」。开发经理本轮指令的原话是「7 条冲突源 `allow` 成立」，我按此实现主记录 `allow`、伴生记录 `exempt`。

## 7. 本批写过的路径（供「只多了这三样」核对）

我的写盘只有 6 个路径：3 个交付物 + `research/referenced-factor-inventory-20261107/{REPORT_v2.md, patch_v2.py, backup_v1_…py, logs/*}`。`backend/scripts/__pycache__/`、`backend/.ruff_cache/` 是 `py_compile` / `ruff` 的副产物（已被 git 忽略，`git status` 无变化）。

同窗口（17:05 之后）`docs/factors/` 与 `.artifacts/` 下另有文件被写，**不是我**（`docs/factors/FACTOR_ENTRY_RULE_20261107.md`、`FACTOR_GAP_SPEC_20261107.md`、`evidence/*`、`.artifacts/_refs_v2.json` 等，属其他 bot 并行工作）；`git status` 前后逐行相同，因为这些都是未跟踪目录/既有未提交改动。

## 8. 待架构师 v0.6 定（我没有自行扩权）

1. **`side` 字段**：契约 §7.10.2 未列，我放在 `records[]` 第 18 位（契约 15 + `both_collision` + `path_divergence` + `side`）。名字与位置需确认。
2. **`summary` 两层结构与字段名**（`live_config` / `all_records` / `judged_records` / `companion_records` / `by_source_verdict` / `by_source_kind`）。
3. **`canonical_sha256` 字段名与算法**（剔除 `generated_at` + 自身、`sort_keys=True`、缩进 2）。旁挂 `.sha256` 仍是字节摘要，随 `generated_at` 变。
4. **`schema_version` 由 `"1"` 升 `"2"`**：记录字段增减、`summary` 换形，故如实升级。
5. **14 处冲突出现处的记录形态**（`allow` 主 + `exempt` 伴生 vs 单条 `exempt`）：与因子工程师期望表的分歧点，二者闸门行为等价。
6. **`verdict` 取值域**是否接受 `exempt`（§7.10.2 未列取值域）。

## 9. 未验证

- HTTP/TestClient 端到端未跑（本批未改后端，无接口面变化）。
- L2 allowlist 的实际读取代码尚不存在（闸门未接线），「只读 `live_config` 层」目前是产物结构 + 顶层 `notes` 的约定，不是运行时强制。
- `research/strategy-search-20261107/factor_map_v1.json` 的 `fields.*.referenced_factors` 是编译器输出的集合，本身无「出现次数」信息：这一类按「每名一处」处理（25 条），不是真·逐出现。
- 公式依赖（custom_factor 20 条）同理：`compile_formula` 返回 `referenced_factors` / `dependencies` 两个集合，重叠名已合并，无法还原出现次数。
- 若将来出现「同一 token 在同一行出现两次」，两条记录会给出同一 evidence 行号（当前数据 0 例）。
- canonical 摘要对 `notes` 文本敏感：改一句话就会换值（可接受，`notes` 属产物内容而非元数据）。
