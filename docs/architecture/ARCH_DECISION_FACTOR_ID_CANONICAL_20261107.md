# 因子 id 唯一性裁定 —— canonical / alias、`strategy_usable` 与登记行（2026-11-07）

状态：**裁定生效**，对「策略规格 / 策略实现 / 台账引用」即时有效。
落笔范围：本文是**独立裁定文件**。契约 v0.3 冻结态（`docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`）**一字未动**；v0.4 草案 §7.8 已含同类裁定（canonical = `uf_*`/`cf_*`），本文与之一致，另更正其 §7.8.1 #6 的一处事实（4 组 → **8 组**，见 §4.2）。
作者：系统架构师。本文不含实现代码、不含收益数字、不下验收结论。

---

## 0. 一句话结论

- **同口径双 id 是 8 组，不是 4 组**。canonical（唯一 `strategy_usable`）= `uf_*`；研究原名（pack 裸 id）= **alias**，`strategy_usable = false`，策略规格与策略实现一律不得引用。
- `prior_amount_20` **不是**双 id（不存在 `uf_prior_amount_20`）。它是该口径唯一的 id，canonical = 研究原名，理由见 §2.3。
- 策略规格的写法（可直接抄）：S07 / S11 / S12 → `uf_vol60`；S03 / S08 → `uf_ma120`；S02 → `uf_prior_high_20` / `uf_prior_low_10`；S09 → `uf_prior_high_55` / `uf_prior_vol_20`；流动性门槛 → `prior_amount_20`。

---

## 1. 事实（2026-11-07 16:2x 本机实测）

### 1.1 双 id 是 8 组（不是 4 组）

pack（`backend/app/custom/research_factor_pack/factor_specs.py#_DEFINITIONS`）以研究原名注册 14 个 id；store 侧 `D:/TSP/data/user_data/custom_factors/` 有 15 个 JSON（14 个 `uf_*` + 1 个 `cf_*`）。两边 id 的**交集是 8 组**：

| # | 研究原名（pack，alias） | store id（canonical） | 公式文本 | 文本差异 |
| --- | --- | --- | --- | --- |
| 1 | `vol60` | `uf_vol60` | pack `ts_std((close - ts_delay(close, 1)) / ts_delay(close, 1), 60)` / store `ts_std(close / ts_delay(close, 1) - 1, 60)` | 不同，1 ULP（1.11e-16，4.6% 行） |
| 2 | `ma120` | `uf_ma120` | `ts_mean(close, 120)` | **逐字相同** |
| 3 | `ma200` | `uf_ma200` | `ts_mean(close, 200)` | **逐字相同** |
| 4 | `prior_high_20` | `uf_prior_high_20` | pack `ts_delay(ts_max(high, 20), 1)` / store `ts_max(ts_delay(high, 1), 20)` | 不同，结构等价（K1）；**V3 已完成**：`max_abs_diff = 0.0`、名次零换位（`F_CLASS_RANK_PARITY_20261107.json`） |
| 5 | `prior_high_55` | `uf_prior_high_55` | pack `ts_delay(ts_max(high, 55), 1)` / store `ts_max(ts_delay(high, 1), 55)` | 同上 |
| 6 | `prior_high_250` | `uf_prior_high_250` | pack `ts_delay(ts_max(high, 250), 1)` / store `ts_max(ts_delay(high, 1), 250)` | 同上 |
| 7 | `prior_low_10` | `uf_prior_low_10` | pack `ts_delay(ts_min(low, 10), 1)` / store `ts_min(ts_delay(low, 1), 10)` | 同上 |
| 8 | `prior_vol_20` | `uf_prior_vol_20` | pack `ts_delay(ts_mean(volume, 20), 1)` / store `ts_mean(ts_delay(volume, 1), 20)` | 同上 |
- **V3 对账已完成并通过**（2026-11-07 16:25，`docs/factors/evidence/F_CLASS_RANK_PARITY_20261107.json`，11,378 B / sha256 `3d8ab8780650a88c8e74db2d354c5da4012ab3ca3450d8e9e7a30d8737d47887`，脚本 `evidence/scripts/f_class_rank_parity.py`）：8 对全部 `pass_1e12`（`vol60` 差 `2.7755575615628914e-17`，其余 7 对 `0.0`）；末交易日三档截面（全市场各对 3,155–3,189 只有值 / 池内 1,716–1,723 只 / 20 只子样）`rank_change_max` 全 `0.0`、`n_swapped` 全 0、`tie_structure_changed` 全 false；250 个交易日逐日最大 `0.0`、有换位日 0。故上表第 4–8 行的「结构等价」**不再是待验项**，S02/S09 的数值基准已验。

实测方法（同一进程内先 Provider 惰性注册 pack，再逐个 `register_definition(json)`，**不写盘、不 load data_dir**）：8 对全部 **双双非 `None`**，`all_factors()` 192 → 201（5 个 `uf_auction_*` 因 `ext_*` 未同步报 `E001`，与本文无关；按 §7.8.1 #10 全量装载为 207）。

**两处既有记载要更正**：
- 契约 v0.4 草案 §7.8.1 #6 写「4 组：`vol60`/`ma120`/`ma200`/`prior_amount_20`」——**组数错**，且 `prior_amount_20` 不在其中（见 §1.2）。
- 台账 `F_CLASS_REGISTRATION_20261107.md` K8（**v4 16:20 起已移到 `:65`**；v3 及以前的写法是「**3 个裸 id / 4 项**」，**错**）当时只列 3 个裸 id（第 4 项 `prior_amount_20` 本就不是双 id，见 §1.2），漏了 `prior_high_20`/`prior_high_55`/`prior_high_250`/`prior_low_10`/`prior_vol_20` 五个同口径双 id——3 + 5 = 8。漏记的后果不是「多写两行」：S02/S09/S08 用的正是这几只，若 alias 未登记，实现侧按 pack 侧写法落库时**没有任何台账记录可比对**。K8 现文（`:65`）已按 8 组更正，本节保留作差异依据。

### 1.2 `prior_amount_20` 是单 id，不是双 id

- 磁盘 15 个 JSON 里**没有** `uf_prior_amount_20.json`；实测 `get_factor("uf_prior_amount_20") is None`。
- 它只有 pack 侧一个 id：`prior_amount_20`，公式 `ts_delay(ts_mean(amount, 20), 1)`，`warmup=21`，`unit=currency`，有 B0 逐位对账 `max_abs_diff = 0`（`docs/factors/REGISTRATION_B0_20261107.md:65`）。
- 因此 K8 / §7.8.1 #6 把它与另三个并列成「双 id」，是把「已注册但只有裸 id」误记成「双 id」。

### 1.3 6 组文本不同，且 pack 侧写法不等于契约 §7.1 原文

- 契约 §7.1 对 `prior_*` 的原文是 `ts_max(ts_delay(high, 1), N)`（store/台账侧），pack 侧是 `ts_delay(ts_max(high, N), 1)`。两者对 rolling max/min 的选择等价（不涉及算术，只换顺序与 null 起点，首根非空同为第 N+1 根），**文本不同，但等价性已由 V3 实测确认**（2026-11-07 16:25，`F_CLASS_RANK_PARITY_20261107.json`：5 组 `prior_*` 的 `max_abs_diff` 全 `0.0`、`n_nonzero` 全 0，末交易日三档截面与 250 日逐日名次换位全为 0）。
- 这意味着：**alias 指向 pack 实际上等于绕开 §7.1 原文**。这是把 canonical 定在 store 侧的又一条硬理由，不是风格偏好。

### 1.4 元数据与可用性两侧不对称（这条决定 canonical 选谁）

| 维度 | pack（研究原名） | store（`uf_*`） |
| --- | --- | --- |
| `status`（draft/active/watch/retired） | **无**（`FactorSpec` 无此字段，pack 自报 `stability="stable"`，无任何 status 流程） | 有，活在 JSON；`to_spec` 投影为 `stability`（draft → `experimental`，实测） |
| `version` 逐因子递增 | 无（版本 = 一次提交，写死 `1`） | 有（`register_definition` 拒绝未提版本） |
| id 命名空间约束 | 无（任意 id，今天是「恰好不撞」） | 有，`CUSTOM_ID_PATTERN = ^uf_[a-z0-9_]{1,40}$`（`store.py:22`） |
| `unit` / `scale_free` | **有**（ratio / currency / count，实测正确） | **无**（`to_spec` 不落盘，实测 `unit == "none"`，§7.2 已登记 P2 缺口） |
| 进程内可用性 | 只要 import 注册表就有（惰性 Provider，实测 fresh 进程 192 条含 14 只） | 依赖 `load_into_registry(data_dir)`（`main.py:221`、`backend/app/backtest/worker.py:236`）；未装载时全部 `None` |

结论：**store 侧独有「状态 + 版本 + 命名空间」，pack 侧独有「unit/scale_free + 无 data_dir 依赖」**。把 canonical 放在 store 侧，必须同批把 `unit`/`scale_free` 落盘（§7.2 P2，与 §7.7.2 的 `status` 同批），否则 `uf_vol60` 在注册表里是 `unit="none"`，S07 的「ratio、未年化」语义只剩台账文字。

### 1.5 矩阵回测路径按**名字前缀**认因子，`uf_*` 目前过不去

`backend/app/backtest/matrix.py#matrix_feature`（`:4216-4226`）的支持判定是名字模式：`_MATRIX_COMPUTED_FEATURES` ∪ `ma{N}` / `ma{N}_bias` / `ema{N}` / `rsi_{N}` / `momentum_{N}d`；不在其中的抛 `unsupported matrix feature`（`:4226`、`:4557`）。已注册的 Provider id 走 `:4211-4215` 进 `_compute_matrix_feature`，但 research pack 只实现了 `materialize_frame`，`materialize_matrix*` 返回空 → 仍落入「不支持」。

后果：`ma120` 在矩阵路径可跑，**`uf_ma120` 会直接 raise**；`vol60` / `sd20` / `prior_*` 在矩阵路径本来就不支持（台账 §4.1、K13 已登记为缺能力项）。

**这不是 id 裁定能绕过的**：它和 K13 是同一处缺口——矩阵路径要能按「注册表里的因子 id」解析，而不是按名字前缀。裁定 canonical 不改这个事实，只是把「该补哪一处」定死（见 §5）。

---

## 2. 裁定

### 2.1 每个口径恰好一个 `strategy_usable` id

| 口径（研究名） | canonical（唯一 `strategy_usable = true`） | alias（`strategy_usable = false`，禁入策略） | 策略规格应写 |
| --- | --- | --- | --- |
| `vol60` | **`uf_vol60`** | `vol60` | S07 核心 / S11 排序量 / S12 核心 → `uf_vol60` |
| `ma120` | **`uf_ma120`** | `ma120` | S03 / S08 趋势过滤 → `uf_ma120` |
| `ma200` | **`uf_ma200`** | `ma200` | 无策略使用（P1 台账）→ `uf_ma200` |
| `prior_high_20` | **`uf_prior_high_20`** | `prior_high_20` | S02 入场 → `uf_prior_high_20` |
| `prior_high_55` | **`uf_prior_high_55`** | `prior_high_55` | S09 入场 → `uf_prior_high_55` |
| `prior_high_250` | **`uf_prior_high_250`** | `prior_high_250` | S08 间接（`dist_prior_high_250` 分母）→ `uf_prior_high_250` |
| `prior_low_10` | **`uf_prior_low_10`** | `prior_low_10` | S02 出场 → `uf_prior_low_10` |
| `prior_vol_20` | **`uf_prior_vol_20`** | `prior_vol_20` | S09 量能确认 → `uf_prior_vol_20` |
| `prior_amount_20` | **`prior_amount_20`**（例外，见 §2.3） | 无 | 12 条流动性门槛 → `prior_amount_20` |

### 2.2 另一侧（alias）的处置：标 alias、**不删**、策略禁用

**处置 = 标 `alias_of` + `strategy_usable = false`，保留 pack 注册，不从 pack 移除。**

- 台账写法：canonical 行写 `aliases = ["vol60"]`、`canonical_reason = "store 侧有 status/version/命名空间约束；文本遵循契约 §7.1 原文"`；alias 侧等价标记 `alias_of = "uf_vol60"`、`strategy_usable = false`。
- **不要用 `replaced_by` 表示别名**。台账机器可读版 `docs/factors/evidence/f_class_registry.json` 里 `replaced_by` 键共 **27** 处（2026-11-07 16:4x 逐键递归遍历实测）：**6** 个非空 id 值（全是 canonical `uf_*`——`uf_prior_high_55` / `uf_prior_low_10` / `uf_dist_prior_high_250`，各在 `replacement_rulings` 与 `id_canonical_ruling.replaced_by_rulings_cross_caliber_only` 出现一次）+ **19** 处空值（18 个 `[]` + 1 个 `null`；那个 `null` 是 `replacement_rulings[3]` 即 `rsi_14` 的未注册目标，按台账 v5 规则**有意**写 `null`，见 §4.2 第二处）+ **2** 处是 `column_semantics` 里的**文本定义**（`id_canonical_ruling.column_semantics.replaced_by` 与 `column_semantics_v4.replaced_by`，讲取值规则，不是字段值）。27 = 6 + 19 + 2，三类不得混算。语义是「**跨口径**取代」（如 `low_60d` → `uf_prior_low_10`，降级替换、窗口 10 vs 60、数值不同）；把同口径等值别名也写进 `replaced_by` 会让「取代」与「别名」混为一谈，实现侧无法判断该不该重跑对账（A-4）。别名归 `alias_of` / `aliases[]`，取代归 `replaced_by`（台账读表须知 2 / 4，`F_CLASS_REGISTRATION_20261107.md:113`、`:115`）。
- 生产入口拒绝 alias（`FS03`）；研究/诊断入口允许，但报告标 `deprecated_alias_used`（与 §7.8.4 一致）。
- alias 命中即返回 canonical 的列，数值归属 canonical；**alias 不得各自持一套实现**（§7.8.2 A-2）。现状 pack 侧确实持有自己的 DSL 文本（这是既成事实，不是本次能消除的），处置 = pack 文本只作**研究复算对照物**（`diagnostic` 模式），不进生产求值路径。

**为什么选择「标 alias」而不是「从 pack 移除这 8 只」**（四个理由，任一单独就不足以定，合起来才定）：

1. pack 同时是 `ma20` / `ma60` / `boll_lower` / `boll_upper` / `sd20` / `prior_amount_20` 的**唯一登记源**；移除 8 只不改任何结论，却要改动 `RESEARCH_BASELINE_FACTOR_IDS`（14 → 6）并重跑 B0 基线（192 条口径与 `factor_columns_view()` 顺序均被测过）。
2. 移除**不解决** §1.5 的矩阵缺口；`uf_ma120` 照样过不去矩阵路径。
3. B0 逐位对账证据（`max_abs_diff = 0`）绑在 14 只上，删 id 会让该证据失去可比对象。
4. 移除不可逆，且属因子注册动作，应走因子工程师的台账流程，不由一次 id 裁定顺手做。

### 2.3 `prior_amount_20` 的例外：canonical = 研究原名（须写明理由）

它没有 store 双胞胎，因此不存在「两个 id 都自称 canonical」的歧义；而定 canonical 的机制性理由（状态/版本/命名空间）今天在它身上**没有对应物可换**：登记一个 `uf_prior_amount_20` 反而会立刻制造一对新的双 id。

- 裁定：`prior_amount_20` 行 `canonical_id = "prior_amount_20"`、`aliases = []`、`canonical_reason = "无 store 双胞胎；pack 是唯一载体；已有 B0 max_abs_diff = 0；登记 uf_prior_amount_20 会立即制造新双 id"`。
- 若日后确实要迁到 store：**必须同一次**把本行 canonical 改判为 `uf_prior_amount_20` 并完成引用迁移，不得两个 id 并存（§7.8.2 A-1「仍只能有一个」）。
- 已知代价（不影响本次裁定，但要记）：该 id 无 `status`，生产闸门按 `draft` 处理（`FS01`）；也无 `version` 逐因子递增。

### 2.4 引用 canonical 之后的数值验收口径

- `uf_vol60` 与研究侧 `close.pct_change()` 的差是 **1 ULP**：`max_abs_diff = 1.1102230246251565e-16`，4.6% 行非零（`F_CLASS_PARITY_20261107.md:37`；根因 100% 在研究侧 `pct_change`，与 `_safe_div` 无关，K7）。**S07/S11/S12 的靶值判据统一按契约 `F-A3` 的 `max_abs_diff < 1e-12`；`1.11e-16` / `2.22e-16` 只作实测记录（`uf_vol60` 1 ULP、非零行占比 4.6%），不得写成门槛**——把某一次实测的 ULP 值当门槛，会让「同一公式换个求和顺序」的正确实现判失败，属凭空收紧。`0` 同样是 alias（pack 文本）的值，也不得按 `0` 验收（那等于要求实现改用 alias）。
- **同一个 `uf_vol60` 有两个差数，不是矛盾**：`F_CLASS_PARITY_20261107.md:37` 记 `1.11e-16`（研究侧走 `close.pct_change()`），V3 记 `2.7755575615628914e-17`（研究侧走 `research/strategy-search-20261107/scripts/common.py` 的 `add_indicators`）。研究路径不同 → 除法与求和的结合顺序不同 → 差不同；两个数都远低于 `1e-12`，都只作**实测记录**。判据只有一条：`max_abs_diff < 1e-12`，不随证据文件而变。
- 5 组 `prior_*`：文本 `ts_delay(ts_max(·), 1)` vs `ts_max(ts_delay(·, 1), N)` 的等价性**已由 V3 实测确认，不再只是结构论证**（2026-11-07 16:25，`F_CLASS_RANK_PARITY_20261107.json`，含 `vol60` 在内 8/8 `pass_1e12`；5 组 `prior_*` 的 `max_abs_diff` 均为 `0.0`、`n_nonzero` 均为 0）。两项判据（`max_abs_diff < 1e-12` + 「逐日首根非空位置一致」）中，**`max_abs_diff < 1e-12` 已满足**；引用该等价性时直接引证据文件名与 `generated_at`，不必自行重算——但**不得只写「V3 已过」**：V3 是带时间戳的报告，不是常真属性。**一处覆盖缺口（不影响本次结论，需补）**：该 JSON 未单列「首根非空位置」字段，`n` 是两侧同为非空的交集行数（各对 4,764–5,000，随回看窗口变化），首根对齐由 `max_abs_diff = 0.0` 与名次零换位**间接覆盖**；要让这一子判据自身可验收，需在 V3 脚本里加一列。
- `ma120` / `ma200`：文本逐字相同，判据是 `max_abs_diff = 0`（可逐位），但 `compare_stats.json` 里没有它们的条目，**不得用 ma20/ma60 的 0 差顺延**（§2.4 台账已写明）。

### 2.5 `label` 以台账为准（K9 的处置）

磁盘 JSON 的 `label` 与台账 8/8 不同（如 `uf_vol60.json` = 「60日收益波动率」vs 台账「60日收益标准差（日频，未年化）」）。裁定：**以台账 label 为准并覆盖磁盘 JSON**；「含当日 / 不含当日 / 未年化」这些口径语义只活在台账，前端 label 不作口径证据。这是登记字段，不涉及公式与版本（覆盖 label 不触发 `version` 提升）。

---

## 3. 登记行（可引用；随 E2 实现批次合并生效）

引用时写「见 `ID-CANON-1`」即可。

| 编号 | 登记内容 | 生效方式 | 落点 |
| --- | --- | --- | --- |
| **`ID-CANON-1`** | 同口径双 id 共 **8 组**，canonical 一律为 store 侧 `uf_*`（`uf_vol60`/`uf_ma120`/`uf_ma200`/`uf_prior_high_20`/`uf_prior_high_55`/`uf_prior_high_250`/`uf_prior_low_10`/`uf_prior_vol_20`），pack 侧研究原名为 alias（`alias_of` + `strategy_usable=false`，生产入口 `FS03`）；`prior_amount_20` 无 store 双胞胎，canonical 例外定为研究原名并写明理由；台账逐行补 `canonical_id` / `aliases[]` / `replaced_by` / `canonical_reason` 四列，`replaced_by` 只表跨口径取代、不表别名 | **即时生效于策略规格与策略实现**；契约正文的对应条款（v0.4 §7.8.1 #6 的「4 组」→「8 组」、`prior_amount_20` 移出双 id 行）**随 E2 实现批次合并修订**，不与本次裁定的生效时间绑定 | 本文 §2；台账 `docs/factors/F_CLASS_REGISTRATION_20261107.md` §2.1；契约 v0.4 §7.8 |

---

## 4. 落笔方式：冻结正文未动

### 4.1 契约 v0.3 冻结态

`docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`：**89,833 B / 914 行 / 全文 `5eb9772411f723576b657f85af7c0aa26427137a41fb53b5774b935942565903` / `head -c 89350` = `b082d902e08df2dc902f97d694dcd2e1ae96d93bd79485a66647470915f9bfef`**（归档 mtime 16:11:32，本轮复算一致）。**本文未写、未改该文件。**

### 4.2 v0.4 草案（已存在，未冻结）的冻结批合并项（两处）

事实：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md` 已是 **v0.4 草案**（16:13:21 起），§7.8.2 裁定 A 已写定 canonical = `uf_*`/`cf_*`，与本文一致——所以「今天不升 v0.4」已被现实越过（不是本文所为）。该文件在本文写完后继续被另一路改写：**16:40:09 已变为 128,007 B / 1,226 行**（本文 16:33 报的 111,368 B / `f5375c01…` 只存活 7 分钟），故本节自 v1.3 起**不再对该文件做任何指纹绑定**（见本节末「绑定纪律」）。**为避免与并发写入互相覆盖（今天已发生 6 次），本文不修改该文件。**

冻结前必须完成的更正（`§7.8.1 #6`，一字不差的替换）：

- 现文：`同口径双 id 已是事实，**4 组**：`vol60`/`ma120`/`ma200`/`prior_amount_20` 在 pack（研究原名）与 store（`uf_*`，14:30:24 落盘 …）各一份`
- 改为：`同口径双 id 已是事实，**8 组**：`vol60`/`ma120`/`ma200`/`prior_high_20`/`prior_high_55`/`prior_high_250`/`prior_low_10`/`prior_vol_20` 在 pack（研究原名）与 store（`uf_*`）各一份；`prior_amount_20` 不是双 id——无 `uf_prior_amount_20`，它只有 pack 侧一个 id`
- 同段证据列补：`逐对 get_factor 双双非 None（8/8）；get_factor("uf_prior_amount_20") is None`**该条已闭环**：v0.4 现文 `:892` 已写「8 组…（v0.4 自纠：本节初稿写「4 组且含 `prior_amount_20`」，与目录实测不符，逐文件读 `id` 后更正）」。上列替换文保留作变更依据，不必再改。

**第二处（2026-11-07 16:4x 新增，随冻结批合并；现在不要改契约）**

- **冲突**：活契约 v0.4 草案 `:1138`（16:40:09 态；行号会漂，按下列原文字串定位）在 `rsi_14_pct` 条的落点第 4 项写：「D2 已定 `rsi_14` 不得被策略引用，`replaced_by` **反向指向 `rsi_14_pct`**」。
- **台账 v5 规则**（`F_CLASS_REGISTRATION_20261107.md:113`，读表须知 2）：「目标**未注册** → 写 `null`，原名放 `replaced_by_declared_name` 并置 `target_registered = false`；**任何研究原名都不得出现在 `replaced_by` 字段里**。」`rsi_14_pct` 至今未注册（`app/factors/registry.py#_CATALOG` 无此 base 列），所以 `rsi_14.replaced_by` 只能是 `null`。机器可读版已经是这个形状：`docs/factors/evidence/f_class_registry.json#replacement_rulings[3]` = `replaced_by: null` / `replaced_by_declared_name: "rsi_14_pct"` / `target_registered: false`。
- **裁定：以台账 v5 规则为准。** 三条依据都不是「谁先写」：①台账是因子登记的唯一权威源（§5），契约登记口径、不登记因子；②v5 规则已在机器可读版落盘并进自检项，契约那句只是正文里的一句描述，无落盘形态、无自检；③契约 `:1138` 的写法要求实现侧把 `replaced_by` 认作「可指向未注册 id」，与契约自己 `:251`「终态，`replaced_by = null`」的写法不自洽。
- **契约那句随冻结批改写为**：`D2 已定 rsi_14 不得被策略引用；rsi_14_pct 未注册期间 rsi_14.replaced_by = null，原名记 replaced_by_declared_name = "rsi_14_pct"、target_registered = false；rsi_14_pct 注册后改为反向指向 canonical id rsi_14_pct`。
- **为什么不能只当措辞差异拖到以后**：这是**匹配语义**差异。实现侧若按字符串匹配 `replaced_by` 找被取代者，契约要求它认一个未注册 id，台账要求它认 `null` + 旁字段——同一件事两种读法，`FS05` / `FS06` 的判据无法唯一化，`rsi_14` 这条链路会「静默不连」：不报错，也不生效。所以登记进冻结批，不登记为「以后再说」。
- **现在不改契约**：理由同本节开头（并发写入，今日已 6 次互相覆盖；改它会把审核绑定再次打散）。落点记在此处，冻结批一次改完。

**绑定纪律（自 v1.3 起，本文件与后续交付一律照此）**

- 活契约 `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md` 有多个写入方，**不再对它做指纹 / 字节数 / 行数绑定**：本文 16:33 报的 111,368 B / 1,050 行 / `f5375c01…` / `0604bf2d…` 在 16:40:09 即失效（现 128,007 B / 1,226 行）。给 7 分钟寿命的指纹做验收锚点，等于没有锚点。
- 必须绑定时**一律只认归档副本** `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`：89,833 B / 914 行 / 全文 `5eb9772411f723576b657f85af7c0aa26427137a41fb53b5774b935942565903` / `head -c 89350` = `b082d902e08df2dc902f97d694dcd2e1ae96d93bd79485a66647470915f9bfef`。
- 也**不追活契约的版本号**：v0.4 → v0.5 何时升由契约流程定；本文只登记「冻结批要改哪几句」，不跟它比版本。
- **`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md` 是草案，不作任何验收依据**：138,729 B，由 `research/arch-build-20261107/build_contract_v05.py` 从活 v0.4 自动生成（16:50:09 首生成，16:52 又被重生成一次，故连它也不绑指纹）。验收一律只认归档副本 `archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`。今天活契约先被改到 128,007 B、又冒出 v0.5 生成脚本，**版本号已不是沟通锚**：谈口径指归档副本行号，谈新条款写「文件名 + 原文字串」，不要写「v0.4 / v0.5 第 N 行」。

### 4.3 别人的文件，本文不改（列出，避免悬空）

- 台账 `docs/factors/F_CLASS_REGISTRATION_20261107.md`：K8 行（**`:65`**，v4 16:20 起）已按 8 组更正；§2.1 表与 §2.1b 的四列（`canonical_id` / `aliases[]` / `superseded_by` / `canonical_reason`）已由因子工程师在 v4 落盘，v5（16:40）统一了 `replaced_by` 写法。**本项已闭环**，此处只作差异记录，无需再改——留一行是因为删掉会让 §1 的「漏记」论述失去落点。
- `DELIVERY_SCHEDULE_20261107.md:51`（B2 仍写「E2 `xs_rank_pct` + 契约 §3.4 R1–R8 选股数 55.5/49.7/92.8/14.7」）与 `:73`（「`xs_rank_in_pool` 只登记不实现」）仍与契约 v0.3+ 相反（开发经理）。

---

## 5. 写权边界（2026-11-07 16:30 追加，即时生效）

本节不属 id 裁定，是同日并发写冲突的处置；记在同一份决定文件里，避免悬空。

- **`docs/factors/F_CLASS_REGISTRATION_20261107.md`（F 类台账）的唯一写权归因子工程师。** 依据：同一时段两次读数 89,381 B / 519 行 → 90,105 B / 597 行（16:2x），说明存在多个写入方；台账是因子登记的唯一权威源，多写会直接破坏 `canonical_id` / `aliases[]` 的可追溯性。
- **其他任何人（含系统架构师、策略经理、开发经理、独立审核）对该文件只读。** 有意见以 **diff 建议**提交因子工程师：`文件:行号` + 原文 + 建议文 + 理由；由因子工程师落盘，建议方不直接改该文件。
- 本文件（`docs/architecture/ARCH_DECISION_*.md`）与 `docs/architecture/FACTOR_ENGINE_CONTRACTS_*.md` 不在此限：前者由系统架构师写；后者按契约流程由系统架构师写，其它方以修订建议提交。
- `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`（v0.3 冻结副本）是审核绑定对象，**任何人不写**；要改口径只能升新版本，不能回改归档。
- 台账仍缺的四列（`canonical_id` / `aliases[]` / `superseded_by` / `canonical_reason`）与 §2.1 的 5 行补登，由因子工程师按本文 §2.1 / §2.3 落笔；本文只给规则，不代写台账。

---

## 6. 未验证 / 不在本文范围

- **本文未重算 V3，结论引证据文件**：V3 已由因子工程师于 2026-11-07 16:25 跑完并通过（`docs/factors/evidence/F_CLASS_RANK_PARITY_20261107.json`，11,378 B / sha256 `3d8ab8780650a88c8e74db2d354c5da4012ab3ca3450d8e9e7a30d8737d47887`，`generated_at = 2026-11-07T16:25:05`，脚本 `evidence/scripts/f_class_rank_parity.py`，`git_head 65c6e42f`，polars 1.44.1）。因此 `uf_vol60` 的 1 ULP 与 5 组 `prior_*` 的等价性**不再是「待验」**——S02/S09 的数值基准已验。**本文没做的是「运行」**：上述数值本文一个也没有重跑；证据由因子工程师产出，判断归审核。
- **未实测 8 只在矩阵路径的行为**：§1.5 是读码 + 一处事实（`uf_*` 不在 Provider id 集合内 → 名称模式不匹配 → raise）。矩阵路径要能解析 canonical id，属 K13 缺能力项，需架构契约 + 实现，本文只把缺口定位到「按名字前缀 vs 按注册表」这一处。
- **未注册任何因子、未改任何代码、未提交、未部署、未跑回测**。
- 依赖项（不属本文）：`unit`/`scale_free` 落盘（§7.2 P2）、`status` 进 `FactorSpec` 与 `assert_factors_usable`（§7.7）、`alias_of` 字段与别名解析（§7.8.2 A-3）、矩阵路径按注册表解析（K13）。这些不落地时，本文的 alias 规则只能靠文档纪律执行，生产入口不会真的拦住裸 id。

---

本文正文 sha256：`069c710f4809be96c3fdbb2ce2a56dbbb3f96c570bec23744393a829cdb26beb`（校验：`head -c 27137 "docs/architecture/ARCH_DECISION_FACTOR_ID_CANONICAL_20261107.md" | sha256sum`）· 行数 197 · 版本 v1.4 · 生成 2026-11-07 16:30（Asia/Shanghai）· 修订 2026-11-07 16:55（Asia/Shanghai）· v1.4（R4：§1.1 表第 4 行与表下注、§1.2、§2.4、§6 末条四处 V3 待验标注已改为已完成并指向 `F_CLASS_RANK_PARITY_20261107.json`（8/8 `pass_1e12`、名次零换位）；§2.4 新增「`uf_vol60` 两份证据两个差数」说明（`1.11e-16` 走 `pct_change`、`2.7755575615628914e-17` 走 `add_indicators`），判据仍只有 1e-12；§4.2「绑定纪律」增第 4 条：`…_v0.5.md` 草案不作验收依据、版本号不作沟通锚；v1.3 的 §1.1 8 组 / §2.2 `replaced_by` 27 = 6 + 19 + 2 / §4.2 两处冻结批合并项不变）
