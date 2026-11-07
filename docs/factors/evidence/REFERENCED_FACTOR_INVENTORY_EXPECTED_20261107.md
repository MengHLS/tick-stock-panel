# 引用因子盘存 · 独立期望表 v3.4（对齐契约 v0.6 §7.12）

> 本表是**因子工程师的独立期望**，供实现产物 `docs/architecture/evidence/referenced_factor_inventory.json` 做机械比对。
> 机器可读副本：`docs/factors/evidence/referenced_factor_inventory_expected_20261107.json`（99,935 B / 2959 行〔内容行；该文件末尾无换行符，`wc -l` 得 2958〕 / LF / sha256 `184dcdf9ef2a545ddd0fc942b6534797b102b9ff6e6cefa6a241b5dd7c5596af`）。**版本以 json `meta.version = "3.4"` 为准；本文与 json 同版。**
> 契约依据：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md`（162,361 B / 1,454 行 / raw sha256 `946a1d8675de6e4e945dc587f65b94ba0ce91922be338774b46b72022a616810`，17:16:36 冻结）§7.10.2、§7.12.2–§7.12.5、§7.10.3 N3/N4、F-A24、F-A34–F-A38。

## 0. 版本与改动

| # | 改动 | 依据 |
| --- | --- | --- |
| 1 | 79 条主记录 `both_collision` 恒 `false`、`verdict` 恒 `allow` | §7.10.2 字段表「主记录恒 false，伴生恒 true」；§7.12.2 |
| 2 | 14 条伴生单列 `companion_records[]`，取**因子侧视图**（`ref_namespace=factor`、`class=custom_dsl`、`resolved_id`=pack id） | §7.12.2 伴生固定取值；开发经理裁定 |
| 3 | 补 v0.6 必填字段：`ref_raw`（留前缀）/`ref_name`/`side`（只 L/R/F）/`side_key`/`record_kind`/`path_base` | §7.12.3 字段唯一写法表 |
| 4 | `summary` 用 `by_record_kind` / `by_verdict_sources` / `by_path_scope`，与 93 = 79 + 14 对平 | §7.12.5 |
| 5 | **v3.1：对重生成产物复检**，写入签认三元组 | §7.12.4 |
| 6 | **v3.2：`verifiable` 按 §7.8.3 改正** —— 79 条主记录由 `true` 改 `null`（base 类判 `n/a`）；产物原本就对，错在我上一版 | §7.8.3 表「base / virtual（catalog 77）→ `n/a`」 |
| 7 | **v3.3：重签到 18:05:22 现行字节**（186,343 B / `b661c8cd…`），digest 改为独立复算的 `aefdf528…`；登记表外差异 OD-1（14 条伴生 `note` 措辞） | §7.12.4；§7.10.2 未列 `note` |
| 8 | **v3.3：三个源数分定义** —— `scanned_sources` 67 / 去重文件 65 / `(path,id)` 对 73，差因不同 | §7.12.2 计数 |
| 9 | **v3.4：停止签认字节，改签三元组**（`canonical_digest` + `schema_version` + `scanned_sources`）；字节实例降为观测记录 `byte_instances_observed`（18:05:22 `b661c8cd…` / 19:23:57 `df5e1a63…`，同 digest），新增 `byte_sha_policy` | §7.12.4（旁挂 `.sha256` 只证「本次运行字节完整」） |
| 10 | **v3.4：本文与 json 同版** —— 本文抬头由 v3.3 改为 v3.4，机器可读副本指纹改记 json 的现行值，并明写「版本以 json `meta.version` 为准」 | 消除 md/json 版本错位（v3.3 抬头配 v3.4 json 曾并存一昼夜） |

## 1. 计数（22 条活配置）

| 项 | 值 |
| --- | ---: |
| 活配置源 | **22**（`custom_signal` 21 + `monitor_rule` 1） |
| 主记录 | **79** |
| 伴生记录 | **14** |
| 记录总数 | **93** |
| `by_verdict`（仅主记录）| `allow` **79** |
| `by_record_kind` | `primary` 79 / `companion` 14 |
| `by_namespace`（仅主记录）| `column` **79** |
| `by_class`（仅主记录）| `base` **79** |
| `by_path_scope`（仅主记录）| `history` 77 / `intraday` 2 |
| `by_verdict_sources` | `allow` **22**，shadow/block/unknown 各 0 |
| `path_scope=both` | **0** |
| `path_divergence=true` | **0** |
| 被 `FS01` 真拦 | **0** |

`side` 分布（93 条）：`R` 48（主 36 + 伴生 12）、`L` 43、`F` 2。带 `field:` 前缀的字面量：**36** 条（全在主记录、全在右值）。**契约 §7.12.1 写的「38 条」是错数，应为 36** —— 产物主记录的 `side=R` + `ref_raw` 带前缀也正好 36 条。

## 2. 逐源明细

| source | kind | path_scope | 主 | 伴生 | 计 | 引用名 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `boll_breakdown_lower` | custom_signal | history | 2 | 1 | 3 | close、boll_lower |
| `boll_breakout_upper` | custom_signal | history | 2 | 1 | 3 | close、boll_upper |
| `broken_limit_up` | custom_signal | history | 5 | 0 | 5 | raw_high、raw_close、limit_up_price |
| `limit_down` | custom_signal | history | 3 | 0 | 3 | raw_close、limit_down_price |
| `limit_down_recovery` | custom_signal | history | 7 | 0 | 7 | raw_low、raw_close、limit_down_price、close、open |
| `limit_up` | custom_signal | history | 3 | 0 | 3 | raw_close、limit_up_price |
| `ma10_breakdown` | custom_signal | history | 4 | 0 | 4 | close、ma10 |
| `ma10_breakout` | custom_signal | history | 4 | 0 | 4 | close、ma10 |
| `ma20_breakdown` | custom_signal | history | 4 | 2 | 6 | close、ma20 |
| `ma20_breakout` | custom_signal | history | 4 | 2 | 6 | close、ma20 |
| `ma5_breakdown` | custom_signal | history | 4 | 0 | 4 | close、ma5 |
| `ma5_breakout` | custom_signal | history | 4 | 0 | 4 | close、ma5 |
| `ma_dead_5_20` | custom_signal | history | 4 | 2 | 6 | ma5、ma20 |
| `ma_golden_20_60` | custom_signal | history | 4 | 4 | 8 | ma20、ma60 |
| `ma_golden_5_20` | custom_signal | history | 4 | 2 | 6 | ma5、ma20 |
| `macd_dead` | custom_signal | history | 4 | 0 | 4 | macd_dif、macd_dea |
| `macd_golden` | custom_signal | history | 4 | 0 | 4 | macd_dif、macd_dea |
| `n_day_high` | custom_signal | history | 2 | 0 | 2 | close、high_60d |
| `n_day_low` | custom_signal | history | 2 | 0 | 2 | close、low_60d |
| `new_height_3` | custom_signal | history | 6 | 0 | 6 | high |
| `volume_surge` | custom_signal | history | 1 | 0 | 1 | vol_ratio_5d |
| `lot_1a1aa285978_521c_p` | monitor_rule | intraday | 2 | 0 | 2 | close |

## 3. 字段写法（逐条已自检）

- `ref_raw` 保留 `field:` / `column:` / `signal:` 前缀（如 `field:ma60`）；`ref_name` 去前缀并 trim（如 `ma60`）。
- `side` 只允许 `L`（`conditions[].left`）/ `R`（`conditions[].right`）/ `F`（monitor 的 `conditions[].field`）；结构键只进 `side_key`，不参与判据与唯一键。
- `source_path` 相对 `data_root`、不带 `user_data/` 前缀，`path_base="data"`。
- `evidence` 严格 `path:line`，**不含 `#` 注释**。
- 唯一键 `(source_path, evidence, side, ref_name, record_kind)`：93 条 0 重复。
- 伴生与主记录共用同一元组，靠 `record_kind` 区分——冲突可见性从配对得来，不靠主记录上的布尔位。

## 4. 与实现产物对账（盘上现行字节，2026-11-07T19:23:57 / 186,343 B / `df5e1a63…`；对账内容与 18:05:22 版相同，两版 `canonical_digest` 与 218 条记录一致）

产物：186,343 B / mtime 2026-11-07T18:05:22 / 全文 sha256 `b661c8cdfeee…` / `schema_version="2"` / 218 条 / 活配置 93（79 主 + 14 伴生）/ `stale_count=0` / `canonical_digest=aefdf528…`。

多重集键 `(source_path, evidence, side, ref_name, record_kind)`：

| 比较 | 结果 |
| --- | --- |
| 79 条主记录 | **完全相等**，缺 0、多 0 |
| 14 条伴生记录 | **完全相等**，缺 0、多 0 |
| v0.6 字段完整性 | 22 个字段在 218 条上**全部存在** |
| `side` 取值（218 条全量） | 只有 `L`/`R`/`F`（`L` 168、`R` 48、`F` 2）；活配置 93 条内为 `L` 43、`R` 48、`F` 2 |
| `evidence` 含 `#` | **0** 条 |
| `path_base` | `data` 117 / `repo` 101 |
| `summary` 三层键 | `live_config` / `all_records` / 顶层 v1 别名三键**齐全**，活配置计数与本表逐项相同 |

**字段级差异只剩一项（表外字段），且不违反契约**：

| 字段 | 本表 | 产物 | 条数 | 判读 |
| --- | --- | --- | --- | --- |
| `note` | 本表自撰措辞 | 实施方自撰措辞 | 14（仅伴生） | §7.10.2 字段表**未列 `note`**；两侧语义等价（均为「N2 同名冲突只登记、不参与放行」）。不进判据、不进唯一键、不进 allowlist，F-A34–A39 均不断言 → **非违约，不要求对齐** |
| `side_key` | `conditions[i].left` 等 | **与本表逐条相同** | 0 | **已关闭**：17:27:45 版此处 93 条全 `null`，现行版 93/93 全部填值，0 条剩余 null |

`note` 已登记为**表外差异 OD-1**（见 json `out_of_table_differences`），后续对账直接引用，不再当新发现重报。

**v3.2 已按契约改正一处我方错读（不是「两种写法都合法」）**：`verifiable`。§7.8.3 判定表写「base / virtual（catalog 77）→ `verifiable` = `n/a`」，`n/a` 在 JSON 落 `null`；故 79 条 `class=base` 主记录应为 `null`，产物全 `null` **是对的**，我 v3.1 写的 `true` 是错读，已改（伴生 `class=custom_dsl` 按同表取 `true`，与产物一致）。改后 79 条主记录 22 个字段**逐字段相等，含 `side_key`**。

另记一项加性字段：产物主记录多带一个 `note=null` 的键（204 条非活配置主记录带此键），§7.10.2 未列 `note`，F-A34–A39 均不断言。

### 三个「源数」不是一个数

| 数 | 值 | 定义 | 怎么算出来的 |
| --- | --- | ---: | --- |
| `scanned_sources` | **67** | 六个扫描函数**打开的文件数**之和（含产出 0 条记录的文件） | 21 + 1 + 4 + 15 + 25 + 1 |
| 去重 `source_path` | **65** | 218 条记录里不同的文件路径数 | 67 − 2 |
| `all_records.sources` | **73** | `(source_path, source_id)` 对数 | 65 + 8 |

- **67 − 65 = 2**：两个 `strategy_overrides/*.json` 被扫描但**零引用**（`scoring={}` 且 `overlay_filter=[]`）：`custom_khunter_limit_up_pullback.json`、`first_limit_pullback_3f_runner_t74.json`。
- **73 − 65 = 8**：`research/strategy-search-20261107/factor_map_v1.json` 一个文件装 9 个策略 id（S01…S11），1 个文件贡献 9 对。
- 一句话：67→65 的差是「扫描了但没产记录的空 override」，73→65 的差才是「一文件多 id 的 research 文件」。**两个差不是同一件事，别混用。**

## 5. 签认三元组（我自己复算，未采用实施方数值）

签认对象 = `canonical_digest` + `schema_version` + `scanned_sources`：

| 项 | 值 |
| --- | --- |
| 签认对象 | **三元组**（下三行）；不再签认某一份文件字节 —— 字节实例见 `byte_instances_observed`（18:05:22 `b661c8cd…` / 19:23:57 `df5e1a63…`，两者同 digest） |
| `canonical_digest` | `aefdf5283acfa8195fd3d9783984f076e62a9eeb8e1fb4816b0aadb21ab22d1a` |
| `schema_version` | `"2"` |
| `scanned_sources` | `67` |

**与产物字段逐位一致**（`agrees_with_artifact_field: true`）。四类扰动复核（对现行字节重跑）：扰动 `generated_at`/`repo_head`/`data_root`、`records` 倒序、`records` 随机重排（`random.seed(7)`）**均不变**；改一条主记录 `verdict` `allow`→`block` → `3b4e85e7…`（**必须变，确实变了**）。

**重签依据**：实施方 18:05 重生成产物，v0.6 可选字段 `side_key` 由 93 条全 `null` 变为 93/93 填值（主记录另带 `note=null`）；这些是记录内容，故 §7.12.4 必然给出不同 digest。

**我能证的与不能证的**：
- 能证：字节三量（size/mtime/全文 sha256）在盘上实测；digest 用 §7.12.4 配方复算，与产物字段逐位相同；四类扰动行为符合契约；79 主 × 22 字段逐字段相等。
- **不能证**：「digest 变化只由 `side_key` 引起」。我在现行字节上试了 8 种组合（`side_key` 置空 / 删除 × `note` 保留 / 删除），**无一复现 `184e4728…`**；被覆盖的旧字节已不存在（git 未跟踪、盘上无备份），该说法与证据一致但未经证明，故按「未证实」登记在 `resign_basis.not_verified_here`。

**历史（不签，留档）**：17:10:10 那版（152,826 B）无 `canonical_digest` 字段，自报 `canonical_sha256 = 16fb5c30…` —— 我用契约配方得 `9d34fef7…`，另测 80 种算法组合无一命中，故当时未签；17:27:45 那版（184,643 B / `c5d8d22d…`）digest `184e4728…` 当时复算一致、已签，现字节被覆盖，该值**作废而非有误**。两版字节均已不存在。

## 6. 未验证

1. `monitor_rule` 的 `path_scope=intraday` 按监控循环消费方式判定（v0.6 N4 同结论），本轮未跑盘中帧。
2. `stale_count=0` 为产物自报值，未独立重算 67 个源的 `source_sha256`。（`scanned_sources=67` 已于本轮独立重数，见第 4 节表。）
3. F-A22 幂等须再重生成一次才能验；F-A26 新鲜度与 `stale_count=0` 自洽，但未独立复核。
4. `by_namespace` / `by_class` / `by_path_scope` 只计主记录；§7.12.5 只对 `by_verdict` 明写「只按 primary」，其余三项口径待架构师确认。
5. 「`side_key` 是 digest 变化的唯一原因」未证实，见第 5 节。

## 7. 负样本（产物必须 0 条，F-A23）

- `user_data/preferences.json:197`、`:200` 的 `builtin:ma20`（展示列）
- `user_data/strategy_overrides/custom_mvoa5yy6.json:3` description 里的「MA20」（散文）

## 8. 排除在 22 之外

`strategy_overrides/custom_factor_first_board_chain_strict_rebreak.json`、`strategy_overrides/custom_mvoa5yy6.json` 只有 `basic_filter.enabled`、无顶层 `enabled`。其引用 `distance_to_high_60d` / `limit_up_count_20d` / `position_240d` 均 `kind=virtual`（不 gate），其余为信号 id → 0 拦截。
