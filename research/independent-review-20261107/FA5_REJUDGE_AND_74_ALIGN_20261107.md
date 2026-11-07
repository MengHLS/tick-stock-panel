# F-A5 重判 与 §7.4「允许改动面」对齐 — 独立审核报告

- 日期：2026-11-07（审核窗口 16:32–16:47 Asia/Shanghai）
- 审核方：独立审核工程师（未参与实现；全部脚本自写，零复用被审方脚本）
- 被审对象：`backend/app/factors/store.py`、`backend/app/api/factors.py`（工作区未提交）
- 判据绑定：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md` §7.6 `F-A5` + §7.4
- 自写脚本：`research/independent-review-20261107/scripts/fa5_v3_independent.py`
  （25,692 B / sha256 `6d64ed29fa431a19d8994b88c7df410494a26e799f3f69a2138f98f8ef7aa04d`）
- 原始输出：`artifacts/fa5v3_stdout.txt`（13,861 B / 81 行 / `3524132f…d8cf7`）、
  `artifacts/fa5v3_stderr.txt`（0 B，空）、`artifacts/fa5v3_results.json`（22,442 B / `e24a4999…e157`）
- 命令与退出码：
  ```
  cd backend
  .venv/Scripts/python.exe ../research/independent-review-20261107/scripts/fa5_v3_independent.py
  → EXIT=0（64 例：59 PASS / 0 FAIL / 1 DEFECT / 3 OBSERVE / 1 info）
  ```

---

## 0 绑定版本（先读这一段：实现方在审核期间改了两版，且改在我读取的当下）

| 文件 | mtime | 大小 | 行数 | sha256（全文） |
|---|---|---:|---:|---|
| `backend/app/factors/store.py` | **2026-11-07 16:33:52** | 19,502 B | 409 | `de77eae6815adecd5e6f75a97329967752bd6b3fe52208a412a88c5641701199` |
| `backend/app/api/factors.py` | **2026-11-07 16:33:57** | 24,629 B | 564 | `b17228b3dcdfab26be21057c262ce43919a8f2d0904adf6addfb43d13e274ac0` |

`git diff --numstat -- backend`（16:45 实测）= `14 18 backend/app/api/factors.py`、**`187 1 backend/app/factors/store.py`**。

**版本漂移链（我的实测，不是转述）**：

| 时刻 | store.py | api/factors.py | 说明 |
|---|---|---|---|
| 15:35:28 | （上一轮我判 FAIL 的那版） | 15:35:28 | 上轮 F-A5 = FAIL 的绑定对象 |
| 16:23:11 | 17,315 B / `177ccae2…` / `+148/−1` | 15:35:28 | 派发书写的就是这一版 |
| **16:33:52 / 16:33:57** | **19,502 B / `de77eae6…` / `+187/−1`** | **24,629 B / `b17228b3…` / `+14/−18`** | **本报告唯一绑定对象** |

16:23 → 16:33 的实质变化（我逐行读过两个快照）：
1. 新增 `resolve_status()`（`store.py:276`）与 `is_unchanged_definition()`（`store.py:298`）；
2. `upsert_definition` 在**判等之前**先做 status 归一化（`store.py:331-333`）；
3. `create_*` 路由**删掉了硬编码 `"status": "draft"`**（`api/factors.py:349-351`、`:383-384`），改为由 store 裁决。

这一改正好改掉了我上一轮判 FAIL 的同一条链的末端。我开工时读到的是 16:23:11 版，读到一半文件变成 16:33:52 版——**以下所有数字均来自 16:33:52/16:33:57 版**；脚本 T9 在跑前跑后各取一次两文件的 `mtime_ns + sha256`，结果完全相同（`PASS`），证明这 6.0 秒的取证没有跨版本。

---

## 1 F-A5 单一结论：**PASS**

判据原句（§7.6）：同内容二次注册 → `version` 不变、响应 `unchanged=true`、盘上文件字节与 mtime 均不变（→ 目录指纹不变 → 依赖指纹的缓存不全表失效）。

| 判据 | 结论 | 依据（脚本用例） | 关键数字 |
|---|---|---|---|
| 1 两形状 × 15 落盘定义 | **PASS** | `T1_*`（30 例）+ `T2_api_*`（15 例） | 45/45 `unchanged=true`、`version_in==version_out`、`sha256` 同、`mtime_ns` 同、`lang` 保留 |
| 2 `lang="python"` 同内容重提交 | **PASS** | `T3_python_same` | 首建 `unchanged=false v1` → 二次 `unchanged=true v1`、字节+mtime 不变、`lang=python`、`warmup_bars=80` |
| 3 反向对照（真改一字符） | **PASS** | `T4_reverse_formula`、`T4b_extra_fields_kept` | `unchanged=false`、`v1→2`、字节与 mtime 均变、`lang=dsl` 保留；`unit/tags/scale_free/note` 全保留 |
| 4 status 语义（draft→active 视为内容变化） | **PASS** | `T5_draft_to_active`、`T6_create_shape_vs_active` | `draft→active` = 变化、`v2`、盘上 `active`、注册表 `stability=stable`；再提交 `unchanged=true v2`；create 形状重提交 active → `unchanged=true v2`、**盘上仍 active** |
| 5 无 `ext_auction_*` 的进程 | **PASS（fail-closed 正确）** | `T7_bare_env_auction` | 抛 `ValueError`（`E001 未知标识符: ext_auction_preopen_last_imbalance`），文件字节+mtime 未变（`bytes_same=true`） |

**判等是对称的**（brief 明确要求）：`T2b_symmetry` 对 15 个 id 各做三向比较——`content_signature(盘上)==content_signature(API)`、`is_same_content(盘上,API)`、`is_same_content(API,盘上)`——**15/15 三向全等，`asymmetric=[]`**。`T2b_neg` 再验：任一侧改 `description`，两个方向都判不等（`leaked=[]`）。判定函数本身是纯函数、无状态、方向无关，这一点在 16:33 版成立。

**上一轮的失败机理已不成立**：16:33 版的 `content_signature`（`store.py:218-244`）投影的是 `to_spec()` 的语义结果（`lang` 缺省按 dsl 补齐、`warmup_bars` 取编译器推导值、`dependencies` 取编译依赖、`components` 取成员与权重），而不是原始键集；盘上多一个 `lang` 不再必然判"变了"。这就是我上轮判 FAIL 的根因，已消除。

---

## 2 逐例证据

### 2.1 判据 1 — 盘上形状 × 15 × 两态（30 例全 PASS）

两态定义：`minus_target` = 注册表里已加载其余 14 个、独缺目标（模拟"注册表状态落后"）；`preloaded` = 15 个全部已注册（模拟"启动期已加载后的二次提交"）。

| id | 盘上版本 | 返回版本 | `unchanged` | 字节同 | mtime 同 | `lang` 前后 | 两态 |
|---|---:|---:|---|---|---|---|---|
| uf_vol60 | 1 | 1 | true | ✔ | ✔ | dsl / dsl | PASS·PASS |
| uf_ma120 | 1 | 1 | true | ✔ | ✔ | dsl / dsl | PASS·PASS |
| uf_ma200 | 1 | 1 | true | ✔ | ✔ | dsl / dsl | PASS·PASS |
| uf_prior_high_20 | 1 | 1 | true | ✔ | ✔ | dsl / dsl | PASS·PASS |
| uf_prior_high_55 | 1 | 1 | true | ✔ | ✔ | dsl / dsl | PASS·PASS |
| uf_prior_high_250 | 1 | 1 | true | ✔ | ✔ | dsl / dsl | PASS·PASS |
| uf_prior_low_10 | 1 | 1 | true | ✔ | ✔ | dsl / dsl | PASS·PASS |
| uf_prior_vol_20 | 1 | 1 | true | ✔ | ✔ | dsl / dsl | PASS·PASS |
| uf_dist_prior_high_250 | 1 | 1 | true | ✔ | ✔ | dsl / dsl | PASS·PASS |
| uf_auction_tail_imbalance | 2 | 2 | true | ✔ | ✔ | 无键 / 无键 | PASS·PASS |
| uf_auction_tail_match_growth | 2 | 2 | true | ✔ | ✔ | 无键 / 无键 | PASS·PASS |
| uf_auction_post0920_match_growth | 2 | 2 | true | ✔ | ✔ | 无键 / 无键 | PASS·PASS |
| uf_auction_volume_surprise | 2 | 2 | true | ✔ | ✔ | 无键 / 无键 | PASS·PASS |
| uf_auction_volume_vs_prev | 2 | 2 | true | ✔ | ✔ | 无键 / 无键 | PASS·PASS |
| cf_auction_resonance | 2 | 2 | true | ✔ | ✔ | 无键 / 无键 | PASS·PASS |

分数：`T1_minus_target_*` 15/15 PASS，`T1_preloaded_*` 15/15 PASS。
（6 个 auction 定义的盘上 JSON **本来就没有 `lang` 键**——所以"lang 保留"对它们是 `null==null`，我按原值比对，没有伪造。）

### 2.2 判据 1 — API 形状 × 15（15 例全 PASS）

API 形状不是我凭空写的：脚本 `T2c_shape_binding` 用 **AST 从 `api/factors.py` 里提取 `create_custom_factor` / `create_composite_factor` 的 `definition` 字典键集**，与我构造的形状逐键比对，结果完全一致：

- 路由侧自定义键：`created_at, description, direction, formula, group, id, kind, label, updated_at, version`（**无 `lang`、无 `status`**）
- 路由侧复合键：`created_at, description, direction, group, id, kind, label, members, updated_at, version`
- 我的构造：同上逐项相同（`T2c_shape_binding = PASS`）

| id | 返回版本 | `unchanged` | 字节同 | mtime 同 | `lang` 落盘后 | 键数增删 |
|---|---:|---|---|---|---|---:|
| uf_vol60 | 1 | true | ✔ | ✔ | dsl | 0 |
| uf_ma120 / ma200 | 1 | true | ✔ | ✔ | dsl | 0 |
| uf_prior_high_20 / 55 / 250 | 1 | true | ✔ | ✔ | dsl | 0 |
| uf_prior_low_10 / uf_prior_vol_20 | 1 | true | ✔ | ✔ | dsl | 0 |
| uf_dist_prior_high_250 | 1 | true | ✔ | ✔ | dsl | 0 |
| uf_auction_*（5 个） | 2 | true | ✔ | ✔ | 无键 | 0 |
| cf_auction_resonance | 2 | true | ✔ | ✔ | 无键 | 0 |

`len_diff = 0` 全部：盘上文件键数在幂等提交后完全不变——**没有被 `_merge_for_write` 塞进 `lang`/`status` 之类的新键**，也没有丢键。

### 2.3 判据 2 — `lang="python"`（`T3_python_same = PASS`）

定义（在**临时目录**新建，非生产）：`uf_py_probe`、`lang=python`、`warmup_bars=80`（声明值 > 推断值 61）、`unit=none`、`tags=["audit","py"]`、公式 `(ctx.col("close") / ctx.col("close").shift(1) - 1).rolling_std(60)`。

| 步骤 | `unchanged` | version | 字节 | mtime | 盘上 lang | 盘上 warmup |
|---|---|---:|---|---|---|---:|
| 首次落库 | false | 1 | 写入 | 写入 | python | 80 |
| 同内容二次提交 | **true** | **1** | **不变** | **不变** | **python** | **80** |

不抛异常、`unchanged=true`、`lang` 仍为 python —— 判据 2 的字面要求成立。

### 2.4 判据 3 — 反向对照（`T4` / `T4b` = PASS）

`T4_reverse_formula`：`uf_vol60` 公式 `ts_std(..., 60)` → `..., 61)`：`unchanged=false`、`version 1→2`、文件 `sha256` 变、`mtime_ns` 变、盘上 `formula` 为新值、`lang` 仍为 `dsl`。→ 说明幂等不是"恒等幂等"。

`T4b_extra_fields_kept`：在临时目录建一个带非 API 字段的定义（`unit=pct`、`tags=["audit"]`、`scale_free=true`、`note="自定义附加键"`），再真改公式：`unchanged=false`、`version 1→2`，且 `unit/tags/scale_free/note/lang` **全部仍在**（`kept=true`）。→ 这正是 `_merge_for_write`（`store.py:261-273`）要保证的行为，实测成立。

### 2.5 判据 4 — status 语义（`T5` / `T6` = PASS，`T6b` = OBSERVE）

`T5_draft_to_active`：盘上 `draft v1`，提交同内容 + `status="active"` →

| 量 | 值 |
|---|---|
| `unchanged` | **false**（status 参与签名，故视为内容变化） |
| version | **1 → 2** |
| 盘上 status | **active** |
| 注册表 `stability` | **stable**（`to_spec` 的 active→stable 投影） |
| 再提交同一 active 定义 | `unchanged=true`、version 仍 2、盘上仍 active |

`T6_create_shape_vs_active`（brief 点名要独立确认的那一条）：盘上 `active v2`，提交 **16:33:57 版 create 路由构造的形状（无 status 键、无 lang）** →

| 量 | 值 |
|---|---|
| `unchanged` | **true** |
| version | **2（不变）** |
| 盘上 status | **active（未被降级）** |
| 盘上 lang | **dsl（保留）** |
| 字节 / mtime | 不变 |

→ **这条现在 PASS。** 我上一轮判 FAIL 的正是同一场景（旧版 create 路由硬编码 `status="draft"`，撞上 status 参与签名 → 判"变了" → `v+1` + 落盘 draft）。16:33 版用 `resolve_status()` 在判等前归一化 + 路由不再自带 status，把它关掉了。

`T6b_old_shape_explicit_draft`（OBSERVE）：如果调用方**显式**带 `status="draft"` 提交同一个 active 定义 → `unchanged=false`、`version 2→3`、盘上 **status 回落到 draft**。见缺陷 **D-3**。

### 2.6 判据 5 — 无扩展列进程（`T7_bare_env_auction = PASS`，fail-closed 正确）

独立子进程，`DATA_DIR` 指向一个**没有 `ext_data` 目录**的临时 data_dir，`ensure_synced(root)` 之后：

| 观测量 | 实测 |
|---|---|
| 残留 `ext_auction_*` 注册数 | **0** |
| `get_factor("ext_auction_preopen_last_imbalance")` | **None** |
| `upsert_definition(uf_auction_tail_imbalance 同内容)` | **抛 `ValueError`** |
| 异常文本 | `公式无效 [E001]: 未知标识符: ext_auction_preopen_last_imbalance` |
| 盘上文件 sha256 / mtime | **未变** |

**定性：这不是缺陷，是 fail-closed 的正确行为。** 理由：
1. `is_same_content` 两侧任一投影失败即返回 `False`（`store.py:247-258`），判等**从不替校验放行**；
2. 随后 `to_spec(updated)`（`store.py:350`）在写盘前抛出，**没有写**——拒绝而不是静默返回 `unchanged=true`；
3. 生产路径上 `load_into_registry` 第一步就是 `ensure_synced(data_dir)`（`store.py:363-366`），所以真实启动不会落到这个态；我按生产口径复跑 `load_into_registry(Path("D:/TSP/data"))`（只读）= **15/15 全部注册、`all_factors()=207`、15/15 的路由预判 `is_unchanged_definition` 全为 True**。

它真正的风险不在 F-A5 判据内，而在"幂等性依赖进程环境"这一点上——见 **D-4**。

### 2.7 §7.4 四条禁止项复核

| 禁止项 | 结论 | 证据 |
|---|---|---|
| ① 不得改 `save_one`/`load_one`/`delete_one` 既有语义 | **PASS** | `backend/app/definitions.py` 未被修改（`git status --porcelain backend/app/definitions.py` 为空），`save_one` 仍是 `atomic_write_text` 整份覆盖（`definitions.py:95-99`） |
| ② 不得放宽 `to_spec` 任何校验 | **PASS** | `git diff` 的三个 hunk 分别只落在 `import json`、`load_one` 新增、`register_definition`+新增块；`to_spec`（`:52-167`）函数体**零改动**。`T10_registry_gate`：同内容重复 `register_definition` 不报错且 version 仍 1；内容变而版本未提 → 仍抛 `factor id 已注册且版本未提升: uf_vol60` |
| ③ 不得改 `_STORE` 路径与 JSON 结构 | **PASS** | 路径仍 `user_data/custom_factors`（`store.py:27`）；15 例 API 形状提交后盘上键数 `len_diff=0` |
| ④ `unchanged=true` 分支仍须先走 `to_spec(stored)`，不得静默成功 | **PASS** | `store.py:334` 确为 `spec = to_spec(stored)`；`T11_illegal_disk`：盘上 `label=""` 的非法定义 + 同内容提交 → 抛 `ValueError: label 不能为空`，文件字节未变 |

---

## 3 缺陷清单（F-A5 判据外的残留，按严重度）

### D-1（P2）`lang="python"` 定义没有对应的 API 形状 → 跨形状判等不闭合

- 现象（`T3b_api_shape_python = DEFECT`）：盘上 `lang=python` 的定义，用 **create 路由形状（无 `lang`）** 重提交同内容 → `unchanged=false`、`version 1→2`。
- 根因（`T3b2_probe` 实测）：API 形状缺 `lang`，`to_spec` 按缺省 `dsl` 走，`compile_formula` 对 python 源码报 **`E014: 语法错误: 无法识别的字符 '.'`** → `is_same_content` 返回 `False` → 判"变了"。
- 端到端后果分两种，都要说清：
  - 走 store 直调：会 `v+1` 并覆盖写（`lang` 因 `_merge_for_write` 保住 python，语义没坏，但版本空转 + 缓存全表失效 —— 正是 F-A5 要消除的代价）。
  - 走真实路由：`create_custom_factor` 的预判 `is_unchanged_definition` 返回 False → 落到 `_trial_nonempty(request, req.formula)`（`api/factors.py:284-288`，内部**只用 `compile_formula`**，不认 `lang`）→ **400 + E014**。即"python 因子无法通过保存接口重存"，是 fail-closed 拒绝，**不是静默写坏**。
- 影响面：当前 15 个落盘定义**没有一个**是 `lang=python`（逐个数过键），所以 F-A5 的判据覆盖范围内不受影响；但 §7.8 已把 `lang="python"` 分支写进契约，这条路一旦启用就会踩到。
- 要求：`CustomFactorCreateRequest` 增 `lang` 字段并把 `_trial_nonempty` 改成按 `lang` 分派；或契约明文规定 python 类定义不属 F-A5 覆盖范围。

### D-2（P2）声明式 `warmup_bars` 只在盘上一侧，缺省即抬版本

`T3c_python_warmup_omitted`：API 形状 + 显式 `lang=python`、但**省略 `warmup_bars`**（盘上声明 80，编译推断 61）→ `unchanged=false`、`version 2→3`，盘上 `warmup_bars` 仍是 80、`lang` 仍 python。
根因：`content_signature` 取的是 `spec.warmup_bars`（= `max(declared, inferred)`，`store.py:98`、`:112`），两侧一个 80 一个 61；而写盘时 `_merge_for_write` 又保留了盘上的 80 —— 于是"判断说变了、写下去一模一样、只为版本号"。与 D-1 同一根因（API 形状字段集窄于盘上形状）。

### D-3（P2）显式 `status` 仍可把 active 静默打回 draft（闸门上线后等于停产）

`T6b_old_shape_explicit_draft`：盘上 `active v2`，提交同内容但显式 `status="draft"` → `unchanged=false`、`version 2→3`、盘上 **status=draft**。
`resolve_status`（`store.py:276-296`）的规则是"调用方显式给出 status 则以调用方为准"，这是**有意设计**；但后果在 §7.7 闸门（`FS01` 只认 `active`）上线后会被放大：任何带 `status` 的重提交 = 该因子立刻不可用。
风险边界（我 grep 过整仓）：当前树内**没有任何调用方**给 `upsert_definition` 传 `status`（`grep -rn '"status"' backend/app/api/factors.py` 只剩 `:427` 编辑回 draft、`:525` 状态端点；后者走 `save_one` 不经 `upsert_definition`）。所以这是"对外接口的残余风险"，不是现存 bug。
要求：要么 `upsert_definition` 直接丢弃入参 `status`（生命周期只走 `/status` 端点），要么在契约里写死"create 路径 status 恒由 store 裁决"。

### D-4（P3，但请留意）`load_into_registry(data_dir)` 对扩展列注册有破坏性副作用

实测：`load_into_registry(<无 ext_data 的 temp data_dir>)` → 内部 `ensure_synced(root)` 把 **85 个 `ext_*` 全部注销**、且不重注册 → 6 个 auction 因子当轮注册失败，只成功 **9/15**（`custom factor 注册失败 … E001`）。
同一函数传生产 data_dir → **15/15 成功**。
所以：只要有人在**非生产 data_dir**（测试、研究目录、第二份数据）上跑一次启动期加载，进程内所有扩展因子会消失，直到下一次对正确 data_dir 的 `ensure_synced`。单机单 data_dir 的当前部署踩不到；多 data_dir / 并行测试会。
定性：不是 F-A5 判据内的问题（判据 5 的 fail-closed 是对的），是 `ensure_synced` 的"以注册表为权威做增删"设计在跨目录时的副作用，登记待架构裁定。

### D-5（P2，上轮已提、未修）`update_custom_factor` 仍恒 `+1`

`api/factors.py:426`：`"version": int(target.get("version",1)) + 1`，无论内容是否变化。同内容"编辑保存"仍抬版本 → 与 F-A5 的意图相反，但**不在 F-A5 的三条靶值里**（判据只覆盖"二次注册"路径）。本条维持上一轮结论，仍未修。

---

## 4 §7.4「唯一允许的改动面」与实际代码的对齐

### 4.1 契约怎么写

§7.4（契约 16:18 版第 748 行）明文：**允许** `store.py` 新增 `content_signature` / `is_same_content` / `upsert_definition` **三个纯新增函数**（契约标 `store.py:207-257`），以及 `api/factors.py` **保存分支改为经 `upsert_definition` 落库**（契约标 `api/factors.py:333-360`）；"这是**唯一**允许的 store 改动面"。

### 4.2 实际改了什么（16:33:52 / 16:33:57 版，函数级）

| # | 位置 | 函数/对象 | 在允许面内？ | 风险定性 |
|---|---|---|---|---|
| 1 | `store.py:39` | `load_one()` 新增公开包装 | **超出** | 低。纯委托 `_STORE.load_one`，不改语义；但它是新增的对外 API，契约未列 |
| 2 | `store.py:169-196` | `register_definition()` **语义变更**：新增 `if get_factor(spec.id) == spec: return spec` | **超出** | 中。全局改变"重复注册"行为：启动二次加载不再告警/不再抛错。`T10_registry_gate` 证明版本门禁未削弱（内容变未提版本仍拒绝）；风险在"内容相同但期望重新注册副作用"的调用方（当前无） |
| 3 | `store.py:199-200` | `_NON_CONTENT_FIELDS`、`_GROUP_DEFAULT` 常量 | 超出（新增私有常量） | 低 |
| 4 | `store.py:203-215` | `_canonical()` 规范化 | 超出 | 低。`1` 与 `1.0` 等价、`bool` 与字符串 `"true"` 可区分；大整数走 float 会丢精度，因子字段用不到 |
| 5 | `store.py:218-244` | `content_signature()` | **允许** | — |
| 6 | `store.py:247-258` | `is_same_content()` | **允许** | — |
| 7 | `store.py:261-273` | `_merge_for_write()` | **超出** | **中**。它改的是**写盘内容**的构造规则（由"入参整份覆盖"改为"以盘上为底、只覆盖显式字段"）。§7.4 ① 禁"改既有写盘语义"，`save_one` 本身没改，但 create/upsert 路径写下去的 JSON 组成变了。行为上正确（保 `lang/unit/tags`），但属契约未授权的语义变更，**需契约追认** |
| 8 | `store.py:276-296` | `resolve_status()` | **超出** | **中**。新增了一条 status 裁决规则，改变 create 路径的生命周期语义（盘上沿用 / 内容变回 draft / 显式优先）。见 D-3 |
| 9 | `store.py:298-308` | `is_unchanged_definition()` | **超出** | 中。路由侧的"第二套判等入口"；实现上确实复用 `is_same_content`（同口径，未分叉），但契约只授权了一个落库入口，没有这个预判出口 |
| 10 | `store.py:310-354` | `upsert_definition()` | **允许** | — |
| 11 | `api/factors.py:284`（HEAD 侧） | `_next_version()` **删除** | **超出** | 中。版本裁决权从路由迁到 store；行为改善（不再每次 +1），但契约的允许面只写了"经 upsert_definition 落库" |
| 12 | `api/factors.py:334-368` | `create_custom_factor()` 保存分支 | **允许**（骨架）/ 内含 3 处超出：`"version": 1` 硬编码、删 `"status"` 键、新增 `is_unchanged_definition` 预判 | 中 |
| 13 | `api/factors.py:370-397` | `create_composite_factor()` | 同上 | 中 |
| 14 | `api/factors.py:402-435` | `update_custom_factor()` **未改**，仍恒 `+1` | 面外（未动） | 见 D-5 |

**对齐结论：不对齐。** 允许面写的是"3 个纯新增函数 + 1 处落库接线"，实际是 **store.py `+187/−1`、api/factors.py `+14/−18`**，函数级超出 **6 项 store（#1/#2/#3/#4/#7/#8/#9 中的 6 个独立对象）+ 4 项 api**。其中 #2、#7、#8、#9 是**语义级**超出（不是纯新增），必须由契约追认或由实现方回退到允许面内。F-A5 判据本身不因越界而失败（越界的实现是对的），但**契约与代码已经不同源**。

### 4.3 契约里的行号引用已过期

- 契约写 `store.py:207-257`（三个函数）→ 实测 `content_signature` 在 **218**、`is_same_content` 在 **247**、`upsert_definition` 在 **310**，跨度 **218–354**。
- 契约写 `api/factors.py:333-360` → 实测 `create_custom_factor` 在 **334–368**，`create_composite_factor` 在 **370–397**。
- 契约 §7.6 `F-A5` 里还残留"实现现状（2026-11-07 15:44 复核）… mtime 15:35:28"→ 现 **16:33:52**。
（P3 文档问题，但审核绑定会因此错版本，建议架构师随下一次修订改掉。）

---

## 5 纪律与生产目录

- **生产目录只读**：`D:\TSP\data\user_data\custom_factors` 15 个文件，跑前跑后 `sha256 + size + mtime_ns` 三项全同，脚本 `T8_prod_unchanged = PASS`（`n=15, drift=[]`）。
  跑前/跑后 sha256 前 20 位（15 个）：`70d20540a7f384a7e6f0`、`840c65e4cfa7d0b07d50`、`1bdc6e8d288f8fcce170`、`6c8f04a6c525e7c9ffd6`、`19957bcd78d9e5dc031e`、`8dc6abc6a45155dfb163`、`7c8163e44571d95ebb88`、`3ddb904acc7277d4195e`、`cf96176f8458dca2827e`、`e3070878b5472b1aab4f`、`9f95286b8f97ab4047ff`、`1f0ce5c6d8365da34a3d`、`e5885f47f4356043d7ec`、`fa8667bc5e6f61323f33`、`c9041ba4930ac9c2ece1`。
  mtime 也全同（6 个 auction = 2026-10-31 18:19:56；`uf_dist_prior_high_250` = 16:07:00.278；其余 14:30:24–26）。
- **未重跑 `f_class_parity.py`**，未触碰任何他人证据 json。
- **未写 `D:\TSP`**：所有写操作落在 `tempfile.mkdtemp` 下（`fa5v3_*`）。唯一对生产目录的调用是 `load_into_registry(Path("D:/TSP/data"))` 与 `ensure_synced(Path("D:/TSP/data"))`，两者只读 + 只改内存注册表。
- 未改他人文件、未提交、未部署、未重启任何服务。
- 本轮新增仅：`scripts/fa5_v3_independent.py` + `artifacts/fa5v3_{stdout,stderr}.txt` + `artifacts/fa5v3_results.json` + 本报告。

---

## 6 未验证（明确列出，别当成已证）

1. **真实 HTTP 往返**：本机无后端服务在跑，我调的是 `store` 函数与源码 AST 提取的形状，**没有**发过真实 `POST /api/factors/custom`。路由内部的 `_trial_nonempty` 分支（依赖真实历史数据与 engine）未跑。
2. **前端"保存"按钮实际发送的字段**：D-1/D-3 的端到端触发条件是按后端代码推断的，未在 UI 上点过。
3. **缓存是否真的"全表失效"**：`materialize_cache` / 目录指纹的端到端后果未观测，只有代码路径推断（version 参与缓存键）。
4. `update_factor_status` / `update_factor_group` 的幂等性（它们不抬版本，但走 `unregister + register_definition`），本轮只读代码，未实测。
5. `composite` 经 create 路由时的试算差异（复合路由不试算）未验。
6. 16:23 版与 16:33 版之间是否还有第三处静默改动：我只比对了 `git diff`（相对 HEAD）与两版文本差异，没有中间态快照可比。
7. `f_class_parity.py` 相关证据（按 brief 禁止重跑）——本轮 A 项不涉及。
