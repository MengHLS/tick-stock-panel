# F-A5 注册幂等：实现与验收（批一b）

日期：2026-11-07
范围：`backend/app/factors/store.py`（新增加 `backend/app/api/factors.py` 接线）
契约条目：因子引擎契约 §7.6 **F-A5** —— 同内容二次注册 ⇒ version 不变、`unchanged=true`、缓存不全表失效；内容有差异 ⇒ version+1 并走既有失效逻辑。
状态：**已实现并实测通过（13/13 判据，退出码 0）**；未提交、未部署、未重启。

---

## 0. 一句话结论

- 同内容二次注册现在是**真空操作**：version 不变、返回 `unchanged=true`、文件字节与 mtime 都不动（依赖目录指纹的缓存因此不会被全表失效）。
- 内容有任意差异（含 status 变化）⇒ version = 盘上版本 + 1，注册 + 原子覆盖写，`unchanged=false`。
- 生产目录 `D:\TSP\data\user_data\custom_factors` 下 14 个 json 的 version 与 sha256 **逐条完全未变**（含 8 个 `uf_*`），并与开工前基线一致。

---

## 1. 「内容等价」的比较口径（F-A5 判等定义）

判等实现：`store.content_signature()` → `json.dumps(_canonical(payload), sort_keys=True)`，`payload` = 定义去掉非内容字段后的全部字段。

**用黑名单而不是白名单**：白名单（只列 formula/label/...）会把将来新增的字段（如 `params`）静默漏判成"没变"；黑名单的失效方向是"当成变了"，只会多抬一版，不会漏抬。

| 字段 | 是否参与判等 | 理由 |
|---|---|---|
| `id` | 是 | 同时是查找键 |
| `kind` | 是 | custom / composite 决定编译路径 |
| `label` / `group` / `description` | 是 | 定义内容 |
| `formula` | 是 | 计算口径本体 |
| `lang` | 是 | dsl / python 决定编译器 |
| `warmup_bars` | 是 | python 表达式显式声明，影响预热 |
| `members` | 是 | 复合成员与权重；**键序无关**、**数值 1 与 1.0 等价**（走 float repr 归一） |
| `direction` | 是 | 方向语义 |
| `status` | 是 | 它决定注册表 `stability`（active→stable，其余→experimental），状态变化就是内容变化 |
| `version` | **否** | 由 store 裁决，调用方传入值只在「首次创建」时生效 |
| `created_at` / `updated_at` | **否** | 时间戳，二次注册必然不同 |
| 将来新增的任何字段 | 是（默认参与） | 黑名单口径的保守方向 |
| mtime / 文件大小 / 目录指纹 | **否** | 只用于缓存失效判定，绝不用来判等 |

数值/结构归一：`_canonical()` 把 dict 递归成 `k:` 前缀键、list 递归、bool → `true/false`、int/float → `n:` + `repr(float(v))`、None → `~null`、字符串 → `s:` + 原文；再 `sort_keys=True` 序列化。因此「键序不同」「1 vs 1.0」判等，而 `0.5` vs `0.6` 判不等。

---

## 2. 代码改动

`git diff --numstat -- backend`：

```
8       16      backend/app/api/factors.py
91      1       backend/app/factors/store.py
```

文件 sha256（改前 → 改后）：

| 文件 | before | after |
|---|---|---|
| `backend/app/factors/store.py` | `71306ce897b7a50b…` | `cdfbe483a2caa9b5…` |
| `backend/app/api/factors.py` | `01fda233819685ca…` | `731dc198c66a9683…` |

### 2.1 `store.py`（+91 / −1）

新增（全部在 `register_definition` 之后、`load_into_registry` 之前）：

- `_NON_CONTENT_FIELDS = {"version","created_at","updated_at"}` —— 唯一不参与判等的字段集合。
- `_canonical()` / `content_signature()` / `is_same_content()` —— 判等的唯一口径（API 与 store 共用，不出现第二套比较逻辑）。
- `upsert_definition(data_dir, definition) -> {"ok","id","version","unchanged"}` —— 注册 + 保存的唯一入口：
  - 内容等价：`to_spec(盘上定义)` → 注册表缺该版本时按盘上版本补注册 → **不写盘** → 返回 `unchanged=true`；
  - 内容有差异：`version = max(盘上版本, 注册表版本) + 1`（防「版本未提升」误拒）→ 保留 `created_at`、刷新 `updated_at` → `to_spec` 校验 → `register_factor` → `_STORE.save_one`（原子写）→ 返回 `unchanged=false`。
- `load_one()` —— `JsonDefinitionStore.load_one` 的薄包装（API 需要按 id 取已存定义）。
- `register_definition()` 增加一行幂等跳过：`if get_factor(spec.id) == spec: return spec`。同一份盘上定义被二次加载（启动期重复 `load_into_registry`、worker 复用）不再打出「注册失败」告警，也不抬版本；**内容不同**仍走注册表的「版本未提升」拒绝（fail-closed 未放宽）。

> 第 5 条超出 brief 最小范围一句：它是「同内容二次注册」在启动期 load 路径上的同一症状（原来是告警 + 漏加载），补上后两条注册路径口径一致。不需要可单点回退，不影响 `upsert_definition`。

### 2.2 `api/factors.py`（+8 / −16）

- 删除 `_next_version()`：接线后成死代码（全仓仅原 L348/L379 两处调用点）。
- `POST /api/factors/custom`：`version` 固定 1 交给 `upsert_definition` 裁决；**内容与已存定义等价时跳过 `_trial_nonempty`（不重跑试算）**，直接返回 upsert 结果（新增 `unchanged` 键，向后兼容）。
- `POST /api/factors/composite`：同上，返回 upsert 结果。
- 未改动：`POST /custom/{id}/update`、`/status`、`/group`、`DELETE`、列表与试算端点。

### 2.3 边界遵守

- `dsl.py` 的 `OPERATORS/CROSS_OPERATORS`、信号链、回测引擎、`scoring.py`：`git status --porcelain` 对这四个文件为空（**未改**）。
- `docs/factors/` 台账与证据：未改。
- 未提交、未部署、未重启。生产目录只做 `listdir + read`。

---

## 3. 验收命令与退出码

```powershell
# 1) F-A5 判据（临时 data_dir，不碰生产目录）
cd C:\work\sourcecode\tick-stock-panel
backend\.venv\Scripts\python.exe -X utf8 research\factor-registration-20261107\f_a5_idempotent.py
# → 13/13 判据通过，EXIT=0（连续运行 3 次均 0，可重复）

# 2) 既有因子测试回归（与改动前对比）
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_factor_store.py tests/test_factor_registry.py `
  tests/test_factor_api.py tests/test_auction_factor_pack.py tests/test_factor_delete_fail_closed.py `
  tests/test_factor_materialize_cache.py tests/test_factor_py_expr.py -q
# 改后: 6 failed, 64 passed（EXIT=1）
# 改前（git checkout 掉这两个文件后同一命令）: 6 failed, 64 passed（EXIT=1）
# → 同一份 6 个失败，逐条相同，非本次改动引入

# 3) 静态检查
.\.venv\Scripts\python.exe -m ruff check app/factors/store.py app/api/factors.py
# → 1 error：BLE001 store.py:285（load_into_registry 既有 `except Exception`，HEAD 同处已存在），新增代码 0 条
```

### 3.1 13 条判据

| # | 判据 | 结果 |
|---|---|---|
| A | 首次注册：version=1、`unchanged=false`、文件落盘 | PASS |
| B | 同内容二次注册（时间戳/传入 version 均不同）：version 不变、`unchanged=true`、**sha256 与 mtime 都不变**、目录指纹不变、注册表仍 1 | PASS |
| C | 注册表被清空后同内容再注册（模拟重启顺序）：补注册、version 仍 1、文件不动 | PASS |
| D | 改一个字符（formula）：`unchanged=false`、version 2、sha256 变、目录指纹变、盘上与注册表都是 2 | PASS |
| E | 改回历史内容（≠盘上内容）：继续抬到 version 3，不回退 | PASS |
| F | 只 `touch()` 改 mtime、字节不变：仍判等价、version 不变、mtime 未被写回 | PASS（证明判等不看 mtime） |
| G | 复合成员字典键序不同：判等价、version 不变、文件不动 | PASS |
| H | 权重 `1`(int) 与 `1.0`(float)：判等价 | PASS |
| I | `status: draft → active`：判为内容变化、version+1、盘上 status 已更新 | PASS（status 参与判等） |
| J | API 层 `create_custom_factor` 同内容二次调用：第二次 `unchanged=true`、version 1、文件不变、**试算只跑 1 次** | PASS |
| M | 启动期连续两次 `load_into_registry`：两次返回同一批 id、0 条告警、版本不变 | PASS |
| K | 生产目录本脚本运行前后 14 个文件 version/sha256/字节全等 | PASS |
| L | 生产目录与开工前基线（`logs/prod_snapshot_before.json`）一致：0 drift、0 新增 | PASS |

证据文件：`research/factor-registration-20261107/logs/f_a5_evidence.json`。
脚本：`research/factor-registration-20261107/f_a5_idempotent.py`（临时目录 `fa5tmp_*` 建在脚本同级，结束时删除；运行后目录内无残留）。

---

## 4. 生产目录 `D:\TSP\data\user_data\custom_factors` 前后对照（14 个文件）

基线 = 开工前（改代码之前）快照 `logs/prod_snapshot_before.json`；后 = 全部实测结束后 `logs/prod_snapshot_after.json`。`identical=True`。

| 文件 | version 前 → 后 | sha256 前 12 位 → 后 12 位 | 结论 |
|---|---|---|---|
| cf_auction_resonance.json | 2 → 2 | `70d20540a7f3` → `70d20540a7f3` | 不变 |
| uf_auction_post0920_match_growth.json | 2 → 2 | `840c65e4cfa7` → `840c65e4cfa7` | 不变 |
| uf_auction_tail_imbalance.json | 2 → 2 | `1bdc6e8d288f` → `1bdc6e8d288f` | 不变 |
| uf_auction_tail_match_growth.json | 2 → 2 | `6c8f04a6c525` → `6c8f04a6c525` | 不变 |
| uf_auction_volume_surprise.json | 2 → 2 | `19957bcd78d9` → `19957bcd78d9` | 不变 |
| uf_auction_volume_vs_prev.json | 2 → 2 | `8dc6abc6a451` → `8dc6abc6a451` | 不变 |
| uf_ma120.json | 1 → 1 | `3ddb904acc72` → `3ddb904acc72` | 不变 |
| uf_ma200.json | 1 → 1 | `cf96176f8458` → `cf96176f8458` | 不变 |
| uf_prior_high_20.json | 1 → 1 | `e3070878b547` → `e3070878b547` | 不变 |
| uf_prior_high_250.json | 1 → 1 | `9f95286b8f97` → `9f95286b8f97` | 不变 |
| uf_prior_high_55.json | 1 → 1 | `1f0ce5c6d836` → `1f0ce5c6d836` | 不变 |
| uf_prior_low_10.json | 1 → 1 | `e5885f47f435` → `e5885f47f435` | 不变 |
| uf_prior_vol_20.json | 1 → 1 | `fa8667bc5e6f` → `fa8667bc5e6f` | 不变 |
| uf_vol60.json | 1 → 1 | `c9041ba4930a` → `c9041ba4930a` | 不变 |

（完整 64 位 sha256 见两个 snapshot json。）

---

## 5. 回归基线（改动前 vs 改动后）

| 项 | 改动前 | 改动后 |
|---|---|---|
| 7 个因子测试文件 | 6 failed / 64 passed | 6 failed / 64 passed |
| 失败用例 | `test_custom_factor_definition_roundtrip`、`test_factor_columns_snapshot`、`test_catalog_counts_and_kinds`、`test_asset_type_filter`、`test_factors_api_contract`、`test_factors_api_asset_filter_and_validation` | 完全相同 |

失败原因是内置因子目录计数 84 ≠ 断言里的 93（环境/既有基线偏差，与 F-A5 无关），**改动前后逐条一致**，本次未引入新失败。

---

## 6. 未覆盖 / 未知（明确划界）

1. **`POST /custom/{id}/update`（编辑端点）同内容重提交仍会 version+1**。它的既有语义是「编辑即新版本」，本次按 brief 只做「注册」短路，未纳入。是否也做幂等，需开发经理排期定（若要做，把 `target` 交给 `upsert_definition` 即可，判等口径已就位）。
2. **`/status`、`/group`**：走 `unregister + register`，版本本来就不变，但会重写文件（`updated_at` 变化）⇒ 目录指纹变。属元数据变更，F-A5 未要求，保持原样。
3. **HTTP 层未跑 TestClient 端到端**：`/custom` 的保存前试算需要真实行情；本次用「直接调用路由函数 + 桩 request（data_dir 指向临时目录）+ 打桩 `_trial_nonempty`」验证了处理函数与返回体（判据 J），**JSON 序列化层与前端未验证**（返回体只新增 `unchanged` 键，向后兼容）。
4. **「缓存不全表失效」是链路推断**：`store` 不写盘 ⇒ `JsonDefinitionStore.fingerprint`（文件名 + mtime_ns 签名）不变 ⇒ `screener_work.hard_identity` 不变（代码链已逐行核对，判据 B/D 实测指纹相等/变化）。未跑一次完整 screener 缓存命中实验。
5. 未验证并发场景（两个请求同时注册同一 id）：`upsert_definition` 无文件锁，与既有 `save_one` 同级别（无锁）。这是既有架构约束（`definitions.py` 注释明示锁在 P2 物化阶段才叠加），非本次引入。

---

## 7. 事实问答：`status` 为 None 是否参与运行时拦截

**结论：目前 `status` 不构成任何运行时拦截。**

核对结果：

- `FactorSpec`（`registry.py`）**没有 `status` 字段**，只有 `stability`。`get_factor()` 返回 `FactorSpec`，所以「status 为 None」实际是 `GET /api/factors` 列表里的字段：`status_by_id` 从盘上定义取，内置因子没有盘上定义 ⇒ `None`（`api/factors.py:31-53`）。
- 唯一映射：`store.to_spec()` 里 `stability = "stable" if status == "active" else "experimental"`（store.py:94/110/165）。
- `stability` 的消费者只有两处：`api/factors.py` 列表展示，`registry.all_factors(stable_only=True)` 过滤；后者仅被 `services/tool_catalog.py:293`（AI 工具目录的 `stable_only` 查询参数）使用。
- 评分 / 回测 / 信号编译 / 执行链**不读** `status` 或 `stability`（全仓 grep：`stability` 只出现在 `api/factors.py`、`registry.py`、`tool_catalog.py`；`"status"` 在 `strategy/`、`backtest/` 的命中全是模拟账户/委托单状态，与因子无关）。
- `load_into_registry` 不按 status 过滤：draft 因子照常注册、照常可算。删除路径用的是引用检查（`_find_references`），不看 status。

因此「把 status 做成闸门」是**新增行为**，不是修 bug；归属开发经理排期，本线程未改。

---

## 8. 复跑清单

| 文件 | 用途 |
|---|---|
| `research/factor-registration-20261107/f_a5_idempotent.py` | F-A5 13 条判据脚本（临时目录，退出码 0/1） |
| `research/factor-registration-20261107/logs/f_a5_evidence.json` | 最后一次运行的判据与生产目录快照 |
| `research/factor-registration-20261107/logs/prod_snapshot_before.json` | 开工前生产目录快照（改造前采集） |
| `research/factor-registration-20261107/logs/prod_snapshot_after.json` | 全部实测结束后生产目录快照 |

已存在的他人文件（`verify_b0.py`、`probe_vol60.py`、`demo_refs.py`、`logs/*.log`）未改动、未覆盖。
