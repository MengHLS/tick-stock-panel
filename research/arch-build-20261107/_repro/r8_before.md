# 契约 v0.7 → v0.8 修订对照（R8：现状事实原位更正 + `notes` 出 digest）
生成时间：2026-11-07 19:35 之后（Asia/Shanghai）· 系统架构师
底本：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md`（**一字未改**，193,586 B / 1,696 行 / 全文 `5a87d4b090d996ab…f8723e8`，mtime 2026-11-07 18:03:23）
产物：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.8.md`

**性质：返工一处事实陈述，不是新工程。** 本版唯一的语义变更只有一条 —— `canonical_digest` 的载荷定义（`notes` 等出 digest，recipe 1 → recipe 2，见 §4），这是派单明确点名要架构侧裁定的判据变更。其余 7 处替换全是**现状事实**与代码对齐。**§7.1 八行公式、`ewm` 裁定语义、所有判据编号与语义一字未动。**

## 1. 八处逐行替换（逐字原文 / 改后；0 处删除）

机械验证（`difflib.SequenceMatcher`，行级）：**replace 7 处（各 1 行 → 1 行）、insert 1 行、delete 0 行**。

#### 第 1 处（原文 line 1）

原文：

```text
# 因子化引擎与生产侧执行器 —— 接口契约 v0.7（2026-11-07）
```

改后：

```text
# 因子化引擎与生产侧执行器 —— 接口契约 v0.8（2026-11-07）
```
#### 第 2 处（原文 line 402）

原文：

```text
- **纯新增算子**：`rank` / `zscore` / `winsorize` 签名与语义不变；`OPERATORS` 只增三个键。
```

改后：

```text
- **纯新增算子**：`rank` / `zscore` / `winsorize` 签名与语义不变；§3（E2）增三个键、§4（E1 `xs_mean`）再增一个，**本批合计四键**，`OPERATORS` 由 25 增至 **29**（现状见 §10.1：读取时刻 2026-11-07 19:35、`dsl.py` 36,785 B / sha `49f3a110…`）。
```
#### 第 3 处（原文 line 1577）

原文：

```text
| E2 截面排名族（`xs_rank_pool` / `xs_rank_market` / `xs_rank_pct`） | **改引擎（扩算子）** | `app/factors/dsl.py#OPERATORS` + `CROSS_OPERATORS` + 编译/求值分支；`_compiled_payload` 的 `cross_sectional` 已有字段可直接复用 | 纯新增三个算子键，`rank`/`zscore`/`winsorize` 不变；需新增错误码 `E017`；`xs_rank_market` 登记为 `rank` 的数值别名（不重复计数） |
```

改后：

```text
| E2 截面排名族（`xs_rank_pool` / `xs_rank_market` / `xs_rank_pct`） | **改引擎（扩算子）** | `app/factors/dsl.py#OPERATORS` + `CROSS_OPERATORS` + 编译/求值分支；`_compiled_payload` 的 `cross_sectional` 已有字段可直接复用 | 纯新增三个算子键（**本节只数 E2 的三个**）；与 §4（E1）`xs_mean` 合计 **四** 键，`OPERATORS` 25 → **29**（§10.1）。`rank`/`zscore`/`winsorize` 不变；需新增错误码 `E017`（**已落地**，实测 `xs_rank_pool(close, 1)` → `E017`）；`xs_rank_market` **按独立键实现并计数**（`len(OPERATORS)==29` 已含它），原「不重复计数」口径作废 |
```
#### 第 4 处（原文 line 1582）

原文：

```text
| D2 `rsi_14_pct`（Wilder 平滑、涨跌幅口径） | **新增模块（新增 base 列；不改 DSL 算子层）** | `registry.py#_CATALOG`（`:83`）新增 `_base("rsi_14_pct", …)`；`indicators/pipeline.py` 新增一列（`ewm_mean(alpha=1/14, adjust=False)`，与 `:576-577` 同法）；`backtest/matrix.py#_MATRIX_COMPUTED_FEATURES` + `#_compute_matrix_feature` 新增分支 | `dsl.py#OPERATORS` 实测 **25** 个键（`len(OPERATORS)==25`；因子工程师文档写「26」，差 1 属计数差异），**无 `ewm`/`ewma`/`wilders`**；但 `ewm_mean` 在指标层已用于 `rsi_6/14/24`（`pipeline.py:576-577`）与 `atr_14`（`:503`）→ 不必扩算子。**不新增错误码**；若强行扩算子则需 `E018`（`E017` 已被 E2 掩码占用）。落点裁定与被否决方案见 §8.1 |
```

改后：

```text
| D2 `rsi_14_pct`（Wilder 平滑、涨跌幅口径） | **新增模块（新增 base 列；不改 DSL 算子层）** | `registry.py#_CATALOG`（`:83`）新增 `_base("rsi_14_pct", …)`；`indicators/pipeline.py` 新增一列（`ewm_mean(alpha=1/14, adjust=False)`，与 `:576-577` 同法）；`backtest/matrix.py#_MATRIX_COMPUTED_FEATURES` + `#_compute_matrix_feature` 新增分支 | `dsl.py#OPERATORS` 实测 **29** 个键（`len(OPERATORS)==29`；读取时刻 2026-11-07 19:35，锚点 `dsl.py` 36,785 B / sha `49f3a110…`；= 原 25 键 + §3（E2）三键 + §4（E1）`xs_mean`），**无 `ewm`/`ewma`/`wilders`**；但 `ewm_mean` 在指标层已用于 `rsi_6/14/24`（`pipeline.py:576-577`）与 `atr_14`（`:503`）→ 不必扩算子。**不新增错误码**；若强行扩算子则需 `E018`（`E017` 已被 E2 掩码占用）。落点裁定与被否决方案见 §8.1 |
```
#### 第 5 处（原文 line 1583）

原文：

```text
| **`ewm` / Wilder 平滑算子**（引擎能力缺口，v0.3 登记） | **不改引擎：否决扩算子** | 不落 `app/factors/dsl.py#OPERATORS`（保持 **25** 键，`TS_OPERATORS` 13 / `CROSS_OPERATORS` 3 不变）；策略侧仍不能用 DSL 写 `ewm(...)`，编译期按未知算子返回 **`E002`**（判据 F-A13）；若日后改判为扩算子，则需 `TS_OPERATORS` 13→14 + 新错误码 **`E018`**（`E017` 已被 E2 掩码占用）+ 面板/矩阵两条求值路径逐位一致 | 派单把它登记为「引擎能力缺口（改引擎）」，架构裁定为**不扩**：Wilder 平滑在指标层已存在（`pipeline.py:576-577`、`:503`），`rsi_14_pct` 改走 base 列（§8.1）。故本条的真实改动性质是「新增 base 列」，不是「改算子层」；`E018` 仅预留给「改判后」的场景，**当前没有任何代码路径会返回它** |
```

改后：

```text
| **`ewm` / Wilder 平滑算子**（引擎能力缺口，v0.3 登记） | **不改引擎：否决扩算子** | 不落 `app/factors/dsl.py#OPERATORS`（**不改动现状 = 29 键**：25 + §3（E2）三键 + §4（E1）`xs_mean`；`TS_OPERATORS` 13 / `CROSS_OPERATORS` 3 亦均未变，见 §10.1）；策略侧仍不能用 DSL 写 `ewm(...)`，编译期按未知算子返回 **`E002`**（判据 F-A13）；若日后改判为扩算子，则需 `TS_OPERATORS` 13→14 + 新错误码 **`E018`**（`E017` 已被 E2 掩码占用）+ 面板/矩阵两条求值路径逐位一致 | 派单把它登记为「引擎能力缺口（改引擎）」，架构裁定为**不扩**：Wilder 平滑在指标层已存在（`pipeline.py:576-577`、`:503`），`rsi_14_pct` 改走 base 列（§8.1）。故本条的真实改动性质是「新增 base 列」，不是「改算子层」；`E018` 仅预留给「改判后」的场景，**当前没有任何代码路径会返回它** |
```
#### 第 6 处（原文 line 1592）

原文：

```text
- `app/factors/dsl.py#OPERATORS` 现有 **25** 个键（`len(OPERATORS)==25`；`TS_OPERATORS` 13、`CROSS_OPERATORS` 3），**无 `ewm`/`ewma`/`wilders` 类算子**；`ts_mean` 是等权滑动均值，**不能**表达 Wilder 递推。（因子工程师 `F_CLASS_REGISTRATION_20261107.md:224` 写「OPERATORS 26 个」，与实测差 1，属计数差异；结论相同：没有 ewm。）
```

改后：

```text
- `app/factors/dsl.py#OPERATORS` 现有 **29** 个键（`len(OPERATORS)==29`；读取时刻 2026-11-07 19:35、`dsl.py` 36,785 B / sha `49f3a110…`；`TS_OPERATORS` 13、`CROSS_OPERATORS` 3），**无 `ewm`/`ewma`/`wilders` 类算子**；`ts_mean` 是等权滑动均值，**不能**表达 Wilder 递推。（旧读数 25、以及因子工程师文档「26」与实测的差 1，均属 2026-11-07 18:03 前的计数；已在 §10.1 统一更正，结论不变：没有 ewm。）
```
#### 第 7 处（原文 line 1653）

原文：

```text
| 扩 DSL 算子 `ewm(x, alpha)` | `OPERATORS` 25→26、`TS_OPERATORS` 13→14；新增 `alpha∈(0,1)`/`span≥1` 常量校验（复用 `E003`/`E004`）；warmup 推导；`_rolling_apply` 与矩阵逐元素两条求值路径都要验逐位一致；与 `E009`（截面算子不得嵌入时序窗口）的交互要重验；错误码需 `E018`（`E017` 已被 E2 掩码占用） | 只为 1 个**已定死** `alpha=1/14` 的因子扩语言；扩完策略侧即获得「任意 alpha」的自由度，台账无法穷举口径组合，违反 G7 可穷举版本化 |
```

改后：

```text
| 扩 DSL 算子 `ewm(x, alpha)` | `OPERATORS` **29→30**、`TS_OPERATORS` 13→14；新增 `alpha∈(0,1)`/`span≥1` 常量校验（复用 `E003`/`E004`）；warmup 推导；`_rolling_apply` 与矩阵逐元素两条求值路径都要验逐位一致；与 `E009`（截面算子不得嵌入时序窗口）的交互要重验；错误码需 `E018`（`E017` 已被 E2 掩码占用） | 只为 1 个**已定死** `alpha=1/14` 的因子扩语言；扩完策略侧即获得「任意 alpha」的自由度，台账无法穷举口径组合，违反 G7 可穷举版本化 |
```
#### 第 8 处（原文 line 1792）

原文：

```text
本文件正文 sha256：`73e15ddc4d8e4a780d02f72cd4e06342834e28fbc77c284b34476e91f8efd6d0`（校验：`head -c 191933 "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md" | sha256sum`）· 正文 `191933 B` · 行数 `1696` · 版本 **v0.7（2026-11-07 R7 裁定，未冻结）**· 冻结四元组（size / lines / body-prefix / full sha）见 `docs/architecture/CONTRACT_REVISION_R7_20261107.md` §7（不写进正文，避免自指）· 生成 2026-11-07 v0.7 = **v0.6 逐字节为底** + R7：§1 新增 `G2.1` / 新增 §7.13 矩阵路径能力清单与准入前置 / 新增 §7.14 `F-A11` 分层判据 / **本批并入四处**：标题版本号 v0.5→v0.7 / 新增 §4.6.1 并改写 `B1`、`B2` / `§2.6 A7` 重写 + 注 2b（14 天）/ 新增 §7.15 canonical id 表 / §8.1 `F-A11` 行替换 / 修订记录与 §9 各 +1 行 · **v0.4（`FACTOR_ENGINE_CONTRACTS_20261107.md`，128,007 B / 1,226 行 / 正文 `head -c 127043` → `71708877…d16bc` / 全文 `5bd81a74…c5531`）仍为 `F-A5` 绑定对象；v0.5（138,729 B / 1,298 行 / 正文 `head -c 137598` → `082d26fa…af7fae` / 全文 `c7740508…c4a21a`）为 `F-A30`–`F-A33` 绑定对象；v0.6（162,361 B / 1,454 行 / 正文 `head -c 160819` → `e3a4db17…2576ec` / 全文 `946a1d86…616810`）为清单 v2（`F-A34`–`F-A39`）绑定对象，自 v0.7 落盘起降为**历史版本**（文件保留、不删，引用状态改「已被 v0.7 取代」，其 `F-A34`–`F-A39` 判定对象不变）** · v0.3 冻结态（89,833 B / 914 行 / 全文 `5eb97724…565903`）逐字节归档于 `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`
```

改后：

```text

```
## 2. numstat 与结构

| 项 | 值 |
| --- | --- |
| 底本 | 193,586 B / 1,696 行 |
| 产物 | **205966 B / 1792 行** |
| 行级 opcodes | replace 7 段 / 被替换旧行合计 8 · insert 1 · delete **0**（difflib 把 footer 与前文并成 1 个 replace 块 = 对齐副作用，非内容变化；§1 逐行 old/new 为准） |
| 插入明细 | §10 整节 95 行（首空 + 分隔线 + 正文 + 尾空）+ §9 表 1 行 = **96** 行 |
| 新增章节 | §10（§10.1 算子数现状 / §10.2 八处一览 / §10.3 `notes` 裁定 / §10.4 v0.7 冻结 / §10.5 未动面哈希 / §10.6 影响与未确证） |

## 3. 算子数：实测（本机，读取时刻 2026-11-07 19:35）

锚点 `backend/app/factors/dsl.py`：**36785 B / 850 行 / sha256 `49f3a1106095ad0cf4a6c1cb8ccde42283957756f89ac1f226bf1624fea0c78b` / mtime 2026-11-07 18:37:48**。

| 项 | 实测 |
| --- | --- |
| `len(OPERATORS)` | **29** |
| `len(TS_OPERATORS)` | **13** |
| `len(CROSS_OPERATORS)` | **3**（['rank', 'winsorize', 'zscore']） |
| `XS_OPERATORS` | ['xs_mean', 'xs_rank_pct', 'xs_rank_pool'] |
| 四键可编译 | [True, True, True, True] |
| 四键 `cross_sectional` | [True, True, True, True] |
| `ewm(close,14)` | ['E002'] |
| `xs_rank_pool(close, 1)` | ['E017'] |

**时间线（这是本轮的根因，不是「写错」）**：v0.7 落盘于 18:03:23，当时工作树 `dsl.py` 与 `HEAD` 一致、`len(OPERATORS)==25`，读数**当时成立**；`git diff --numstat backend/app/factors/dsl.py` → `+108/−12`，四键与 `E017` 于 **18:37:48** 落地，该读数自此静默过期。缺陷类别是「现状实测未带读取时刻与文件 sha」，已用 §10.1 的规则治类。

命令：

```bash
cd /c/work/sourcecode/tick-stock-panel
wc -c -l backend/app/factors/dsl.py && sha256sum backend/app/factors/dsl.py
backend/.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'backend'); from app.factors import dsl as m; print(len(m.OPERATORS), len(m.TS_OPERATORS), len(m.CROSS_OPERATORS)); print([m.compile_formula(t).ok for t in ('xs_rank_pool(close, close>0)','xs_rank_market(close)','xs_rank_pct(close, close>0)','xs_mean(close, close>0)')]); print([e.code for e in m.compile_formula('ewm(close,14)').errors])"
```

## 4. `notes` 是否进 digest —— 裁定：**不进**（recipe 1 → recipe 2）

锚点产物：`docs/architecture/evidence/referenced_factor_inventory.json` **186343 B** / 全文 `df5e1a63e98f8834e95517bbdde556a2550bb901d865ba09c1ac7f4040b32e49` / `records` 218 / `generated_at` `2026-11-07T19:23:55+08:00` / `schema_version` `2` / `scanned_sources` 67。

落盘 `canonical_digest` = `aefdf5283acfa8195fd3d9783984f076e62a9eeb8e1fb4816b0aadb21ab22d1a`；按 §7.12.4 原文（recipe 1）复算 = `aefdf5283acfa8195fd3d9783984f076e62a9eeb8e1fb4816b0aadb21ab22d1a` → **逐位相等**；按 recipe 2 复算 = `d87fef1413c0b6c1754b455a63bb31e36a4ec23359d7690a653218be9b7a44d6`。

| 扰动 | recipe 1 | recipe 2 |
| --- | --- | --- |
| 原样 | `aefdf5283acfa8195fd3d9783984f076e62a9eeb8e1fb4816b0aadb21ab22d1a` | `d87fef1413c0b6c1754b455a63bb31e36a4ec23359d7690a653218be9b7a44d6` |
| `notes` 每条尾加 1 个空格 | `ba414786544e21f4ff5c1b57d82f0da0bb1c8e1b573ff3db20810ed78987a1d8`（**变**） | `d87fef1413c0b6c1754b455a63bb31e36a4ec23359d7690a653218be9b7a44d6`（不变） |
| 改 `summary.live_config.records` | `6c33d2db7c182d0ea3e925111f36242958495c7822614c1c0bc3bac20aab6f25`（变） | `d87fef1413c0b6c1754b455a63bb31e36a4ec23359d7690a653218be9b7a44d6`（不变） |
| `records` 随机重排（`seed=7`） | `aefdf5283acfa8195fd3d9783984f076e62a9eeb8e1fb4816b0aadb21ab22d1a`（不变） | `d87fef1413c0b6c1754b455a63bb31e36a4ec23359d7690a653218be9b7a44d6`（不变） |
| 改 1 条 `verdict`（`allow`→`block`） | `3b4e85e7806abc09b7a6e21b7c9222da414b070b5bef750166b977cc3c0c46d3`（变） | `6e6d6cdeca136cf68842a6975a6b990599b66da393d216adbe22ac23a839bd73`（**变**） |

**结论**：签认对象只绑定被判事实。`notes`（6 条散文）/ `summary` / `stale_count` 不进载荷；`records` 与 `verdict` 必须进（改了必变，实测）。recipe 1 保留为历史定义、已公布值不失效；新增 `canonical_digest_recipe`，签认升为四元组 `(recipe, digest, schema_version, scanned_sources)`；跨 recipe 报「不可比」，L2 起必须 `"2"`。

## 5. 未动面：逐块逐字节相等（不是仅哈希相等）

| 块 | CRLF 字符数 | CRLF sha16 | LF 字符数 | LF sha16 |
| --- | --- | --- | --- | --- |
| `## 6. X1 生产侧组合级调仓执行器` | 24 | `9385b506831fa9bc` | 22 | `079c3760f91e0c59` |
| `## 7. F 类表达式因子注册入口` | 29 | `25d3e2b4e5f845b5` | 27 | `3461d805252f10cf` |
| `### 7.1 实测结论` | 2541 | `a8e88134f60b504c` | 2514 | `6d3db0139a45f54c` |
| `### 7.9 `POST /custom` 对既有定义` | 57 | `73e0ba549781b94f` | 55 | `2b1f13ef5c95f5e5` |
| `### 7.11 `POST /custom/{id}/` | 142 | `9aa94c74bd40a4d2` | 138 | `c9dd4c0203c2fc0a` |
| `### 7.12 清单 v2 规格：粒度、记录身份、ca` | 75 | `b89c673c6b263669` | 73 | `fde733bf3cabadfe` |
| `### 7.13 矩阵回测路径的能力清单与准入前置` | 3964 | `c580720a1b31d925` | 3900 | `328d64faa756cbaa` |
| `### 7.14 `F-A11` 裁定：分层判据` | 3908 | `f3571417ee0e1033` | 3842 | `1bbc5bd02e2f7fae` |
| `### 7.15 canonical id 表` | 4153 | `1862a3282f9fa740` | 4103 | `6fb89b219b5374d5` |

§7.1 与 v0.6、v0.7、v0.8 三处**同块**：CRLF `2541`/`a8e88134f60b504c`，LF `2514`/`6d3db0139a45f54c`（与派单口径 `2,514`/`6d3db013…` = **LF 归一**一致；`a8e88134…` = **CRLF 保留**）。

**全章节审计**（机器比对，非目测）：v0.7 共 **115** 个二至四级小节，其中 **111 个逐字节相等**、**4 个改动**、另新增 **7** 个（§10 及其 6 个子节）。改动集合经断言等于预期集合 `{§3.5, §8, §8.1, §9}` —— 多一个就会抛断言、不落盘。

| 改动小节 | v0.7 字符 / sha8 | v0.8 字符 / sha8 | 原因 |
| --- | --- | --- | --- |
| `### 3.5 对现有调用方的兼容性` | 489 / `fe1fde91` | 610 / `4ad4dd2b` | §3.5 四键 / 29 |
| `## 8. 改动性质总表` | 2471 / `d7434dbc` | 2746 / `770627d1` | §8 E2 落点行 |
| `### 8.1 `rsi_14_pct`` | 6230 / `c3959c70` | 6283 / `fb5acd57` | §8.1 三处（D2 / `ewm` 否决 / 裁定段） |
| `## 9. 未覆盖与依赖` | 4525 / `59931211` | 3797 / `036f97b7` | §9 加 1 行 |

## 6. v0.7 的冻结状态（明确回答）

| 问题 | 回答 |
| --- | --- |
| v0.7 是否升 v0.8 | **是**。不原地改 v0.7：它已于 18:03 流通（193,586 B / `5a87d4b0…`），原地改会造成「同一路径同版本号两种字节」 |
| v0.7 当前冻结状态 | **冻结为 2026-11-07 18:03 快照**：文件保留、不删、不再写入、四元组固定；引用状态「已被 v0.8 取代」；`F-A30`–`F-A41` 判定对象不变 |
| v0.8 是否操作版 | **是**。此后「现状」一律以 §10.1 为准 |
| v0.6 / v0.5 / v0.4 | v0.6 不更正（历史读数，其「25 键」不得再作基线）；v0.5、v0.4 一字未改，`F-A5` 锚点仍 v0.4 |

## 7. 四元组（v0.8，原生工具复算）

```bash
cd /c/work/sourcecode/tick-stock-panel
F=docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.8.md
wc -c -l "$F"                       # 1792 205966
head -c 204297 "$F" | sha256sum         # f866e73185a784df67e965d1e53b55b2412f2ca933ccc28f401e91796327f846
sha256sum "$F"                      # 9151e39def8100cb1ef56881bec0b663ac3af15e8f726bb1c896e20acaa8a2cc
```

| 项 | 值 |
| --- | --- |
| size | **205966 B** |
| 行数 | **1792** |
| 正文前缀 | `head -c 204297` → **`f866e73185a784df67e965d1e53b55b2412f2ca933ccc28f401e91796327f846`** |
| 全文 | **`9151e39def8100cb1ef56881bec0b663ac3af15e8f726bb1c896e20acaa8a2cc`** |
| 读取/落盘时刻 | 2026-11-07 19:55:54（Asia/Shanghai） |

## 8. 未确证（不圆）

- `E1/E2` 实现与 §3/§4 判据的逐条一致 **未验**（归独立审核）；`xs_rank_market` 与 `rank` 的数值等价 **未逐位验**。
- `E009`（截面算子不得嵌入时序窗口）对四个新键只读了分支（`dsl.py:738`），**未构造嵌入用例实跑**。
- §10.1 的 29/13/3 是**导入模块**实测，**未穷举**其他算子白名单（如矩阵路径 `_MATRIX_COMPUTED_FEATURES`）。
- recipe 2 只在本机对**单个产物**验证过；未验证其他产物（期望表 `referenced_factor_inventory_expected_20261107.json`）的情况。
- 本轮**未**改 `backend/**`、`docs/factors/**`、`docs/research/**`；未 add、未提交、未部署；`gate.py` 未创建。
