# B0b-1 + B0b-3 + research 入库 — 交付报告

提交：`0542bef4`（B0b-1 + B0b-3）、`6eda98bb`（research 入库）。分支 `dev`，**未 push**。
基线：`200238ec`（排期 v7）。

---

## 一、B0b-1 闸门载体（只补载体，生产调用点仍 0）

### 改了什么

| 文件 | 改动 |
|---|---|
| `backend/app/factors/registry.py` | `FactorSpec` 增第 22 字段 `alias_of: str \| None = None`、第 23 字段 `strategy_usable: bool = True`，加 `is_alias()`；新增 `peek_factor()`（只查不触发发现，供重试收敛用） |
| `backend/app/factors/store.py` | 新增 `_admission_fields()`；`to_spec()` 三条分支（custom / frame / composite）全部透传 `alias_of` / `strategy_usable` |
| `backend/app/custom/research_factor_pack/factor_specs.py` | 新增 `_ALIAS_OF` 表（§7.15.1 第 1–8 行逐行照抄，8 条），`_spec()` 写入两字段 |
| `backend/app/factors/gate.py` | `GATED_KINDS` 白名单 → `EXEMPT_KINDS = {base, virtual}` 黑名单语义；`_guard_dual_id` 改抛 `GateError(FS04)` 且排到 FS03 之前；`RegistryFacts` 直接读 `spec.alias_of` / `spec.strategy_usable`（定义 JSON 作兜底） |

### 判据实测

**①真盘 8 组双 id 各出 FS03、8 只 canonical 不出**

脚本 `research/b0b-20261107/verify_fs03_realdisk.py`（**exit 0**，9/9 PASS；其中 A6 是信息项），证据 `logs/fs03_realdisk.json` 8,245 B / `1e00af393632f488935e16ec99777199a7e3fe562fdc9d2822e901b1d3791f7e`，连跑两次逐字节相同：

| alias | canonical | spec.alias_of | strategy_usable | production codes |
|---|---|---|---|---|
| vol60 | uf_vol60 | uf_vol60 | False | `['FS03','FS01']` |
| ma120 | uf_ma120 | uf_ma120 | False | `['FS03','FS01']` |
| ma200 | uf_ma200 | uf_ma200 | False | `['FS03','FS01']` |
| prior_high_20 | uf_prior_high_20 | uf_prior_high_20 | False | `['FS03','FS01']` |
| prior_high_55 | uf_prior_high_55 | uf_prior_high_55 | False | `['FS03','FS01']` |
| prior_high_250 | uf_prior_high_250 | uf_prior_high_250 | False | `['FS03','FS01']` |
| prior_low_10 | uf_prior_low_10 | uf_prior_low_10 | False | `['FS03','FS01']` |
| prior_vol_20 | uf_prior_vol_20 | uf_prior_vol_20 | False | `['FS03','FS01']` |

8 只 canonical 全部 `alias_of=None`、**codes 里没有 FS03**，本判据（A2）成立。

**canonical 侧的 FS01 随真盘 `status` 变化，与本批代码无关。** 提交时的证据里它们是 `['FS01']`（15 个定义 status 全 `draft`）；23:33:57 这 8 个 `uf_*.json` 被**外部**改成 `status="active"`（`created_at` 仍 14:30:24、`updated_at` 刷新为 23:33:57，文件 mtime 同一秒），复跑后 codes 变 `[]`。已核过三点：验证脚本本身不写盘（连跑两次文件 mtime/sha 不变）、`test_factor_gate`+`store`+`api`+`provider_discovery`+`resource_bundle` 五件套跑 162 passed 期间真盘 15 个文件 sha 与 mtime **零变化**、`load_into_registry` 与 `ensure_synced` 都只读。为免后来的读方对不上数字，新增信息项 `A6.disk_status_snapshot_info`（ok 恒 true，不设阈值）把当时 8 个 status 写进证据。

关键前置：真盘 `D:/TSP/data/user_data/custom_factors/*.json` 15 个文件**没有一个** `alias_of` 键（`A5` 判据），所以 FS03 只可能来自本批新增的 pack 载体 —— 不是巧合。

诊断模式对照（`A3`）：8 个 alias 在 `diagnostic` 下**全部不拒**（§7.8.4），证明 FS03 只在 production 生效。

**②gate 套件 ≥56 passed 且新增真盘用例**

`tests/test_factor_gate.py`：**62 passed**（原 56 + 6 条新用例）。
| 新增用例 | 判据 |
|---|---|
| `test_factor_spec_has_the_two_admission_fields_as_22nd_and_23rd` | 两字段位次 |
| `test_store_reads_alias_of_and_strategy_usable_from_disk_json` | 从盘上 JSON 读入 |
| `test_gate_uses_a_blacklist_so_unknown_kinds_are_gated` | 黑名单语义（新 kind 默认受约束） |
| `test_fs04_raises_gate_error_and_wins_over_fs03` | FS04 抛 GateError + 优先于 FS03 |
| `test_real_disk_eight_alias_ids_are_rejected_and_canonicals_pass` | **真盘**，8+8 |
| `test_real_disk_six_single_sided_pack_factors_are_not_aliases` | **真盘**，6 个 pack 单侧件不得成 alias |

**③构造导入失败后清旗可恢复，20 次连跑稳定**

`tests/test_factor_provider_discovery.py` **7 passed**；20 连跑（含 `test_resource_bundle.py` 的 2 条预热回归）**20/20 全 `9 passed`**，无一次抖动。

---

## 二、B0b-3 Provider 静默吞异常

### 改了什么

| 位置 | 改动 |
|---|---|
| `extensions/factors.py:106+` | 新增 `_DISCOVERY` 记录块（attempts / failures / packages_scanned / modules_loaded / providers_registered / failed_modules / failed_providers / last_error / last_failed / missing_package）与 `_LOGGED_ERRORS`（同一条错误只告警一次） |
| `:202` | 新增 `_note_failure(kind, name, exc)`：计数 + 最后错误 + 包名 |
| `:207` `ensure_factor_providers()` | **旗标改为循环全成功后才置位**，任一失败则 `_PROVIDERS_READY = False` 并 return（下次调用重试）；每次尝试重置计数 |
| `:220` `register_factor_provider` | 注册每个 spec 前用 `peek_factor` 判同内容 → 跳过；解决「中途抛错留下残留 spec，重试因版本未提升永远失败」那半条路径 |
| `:284` | 新增 `factor_provider_status()`：四态 `pending` / `not_installed` / `load_failed` / `loaded` |
| `extensions/__init__.py` | 导出 `factor_provider_status` |
| `api/routes.py` `/health` | 增 `factor_providers` 键（只读快照，不触发发现） |

### 判据实测

**未安装 vs 装载失败可区分**（`test_state_distinguishes_not_installed_from_load_failed`）：
- `app.custom` 缺失 → `state == "not_installed"`，`missing_package` 非空
- 包在但 import 抛错 → `state == "load_failed"`，`failed_modules` 含包名

**瞬时失败可重试**（`test_transient_module_failure_keeps_the_flag_clear_and_retries`）：第一次 `import` 抛 `RuntimeError` → 旗标 False、`state=load_failed`、`last_failed` = 包名；**第二次调用真的重试**并成功，`state=loaded`。旧实现在这里永久缺失。

**残留 spec 不阻挡重试**（`test_already_registered_specs_do_not_block_rediscovery`）：手工 `register_factor` 一条残留 → 重新发现仍 `_PROVIDERS_READY is True` 且 14 条全在。

**`:732` 预热有测试保护**：删掉 `backend/app/services/resource_bundle.py:732`（`registry.all_factors()`）后

```
FAILED tests/test_resource_bundle.py::test_preview_compile_sees_ext_columns_registered_by_the_warmup
FAILED tests/test_resource_bundle.py::test_preview_signal_whitelist_sees_ext_columns_registered_by_the_warmup
2 failed, 69 deselected
```

还原后 `2 passed`，`git status` 对该文件为空（字节级还原）。

---

## 三、research 入库

| 项 | 值 |
|---|---|
| `.gitignore` 新增 | `research/**/*.arrow`、`*.parquet`、`*.sqlite`、`*.sqlite3`、`*.db`、`*.pkl` |
| 排除量 | 7 文件 / **415.1 MB**（`panel_input.arrow` 242.6 MB、`bars_feat.parquet` 165.5 MB、`path_position_days.parquet` 3.3 MB、`ledger.sqlite` ×4 各 0.9 MB） |
| 入库量 | **635 文件 / 14.8 MB** |
| `common.py` | `git ls-files research/strategy-search-20261107/scripts/common.py` → 非空（在 `200238ec` 时就已跟踪，本次一并带上其改动） |
| `registry.json` | 同上，随 `6eda98bb` 入库 |
| 排除的个人文件 | `research/_intake/modes.jpg`（Android 设备截图 1440×3200，888 KB）已从索引退出，文件留在盘上 |

未做反向剔除：42 个 `rets_*.npy`（各 14 KB）与 `path_position_days.parquet`（3.3 MB）在本次规则之前就已入库，剔除会改写历史提交引用的路径。

---

## 四、改了哪些文件（本批）

**`0542bef4`**（11 文件，+692/−30）

| 文件 | 字节 / sha16 / 行 |
|---|---|
| `backend/app/factors/registry.py` | 20,916 / `03c780be42145517` / 457 |
| `backend/app/factors/store.py` | 21,104 / `f6f3ffa82758e25a` / 437 |
| `backend/app/factors/gate.py` | 27,570 / `39068c37a5832125` / 635 |
| `backend/app/extensions/factors.py` | 18,514 / `588159e97f9c6e2e` / 523 |
| `backend/app/extensions/__init__.py` | 3,804 / `3f1e7aa44a1b0bbb` / 132 |
| `backend/app/api/routes.py` | 3,825 / `5d2c448d3f01b16b` / 108 |
| `backend/app/custom/research_factor_pack/factor_specs.py` | 5,284 / `a7e71b399b72dc7c` / 121 |
| `backend/tests/test_factor_gate.py` | 25,329 / `de1dbb986ec1baa1` / 621 |
| `backend/tests/test_factor_provider_discovery.py` | 7,759 / `2041d7a1848adf86` / 192 |
| `backend/tests/test_resource_bundle.py` | 39,241 / `8c2fd51ce28a249f` / 778 |
| `.gitignore` | 3,239 / `b4693ebd7b90b89c` / 133 |

**`6eda98bb`**（635 文件，+221,859/−111，全部在 `research/`）

**新增证据**：`research/b0b-20261107/verify_fs03_realdisk.py`（7,488 B / `8ef326137c607395` / 163 行）+ `logs/fs03_realdisk.json`（8,245 B / `1e00af39…`，9 项）、`logs/fs03_realdisk_stdout.txt`（1,725 B / `f2ac7206…`）、`logs/pytest_all_8files.txt`（1,538 B / `8a4dcf405f10d18c`）、`logs/pytest_gate.txt`（1,374 B / `b257ded349c11e55`）、`logs/pytest_discovery.txt`（1,373 B / `237706ec447c8e52`）、`logs/rerun20.txt`、`logs/negative_remove_732.txt`

---

## 五、仍未实跑 / 未做

1. **生产调用点仍 0**：`assert_factors_usable(` 在 `backend/app/` 里除 `gate.py` 自身 docstring 外没有调用点。接线会 FS03 拒 alias，会打断仍写 `vol60` 等的策略规格 —— 按派单要求等策略侧 id 迁移清单。
2. **`alias_of` 只有 8 条**：§7.15.1 第 9–14 行是 pack 单侧件，`alias_of` 必须为 None（`test_real_disk_six_single_sided_pack_factors_are_not_aliases` 已判）。其余 `uf_` 因子无 alias，闸门对它们的 alias 判定面仍是 0。
3. **`strategy_usable` 没接过任何策略准入**：字段与读写就位，但没有调用方读它（接线随上一条）。
4. **`/health` 的 `factor_providers` 未在真实服务进程里看过**：只在 `test_health_endpoint_carries_the_provider_state` 里调了 `health()` 函数，没起服务、没 curl。
5. **矩阵路径 `month_end`/`week_end`** 仍不可物化（归 B0b-2，未动 `matrix.py`）。
6. **`docs/` 未提交**：`docs/architecture/` 下 5 个 `M` 与 2 个 `??`（含 `FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md`）不是我本批改的，留给文档侧。
7. **S09 registry 数字不可复现**：`common.py` + `registry.json` 已入库给出 git 锚，但我没有重跑 S09 三档 —— 重算本身属研究侧。
8. **真盘 8 个 `uf_*.json` 的 `status` 被外部改成 `active`**（23:33:57，非我改动，已实证脚本与测试都不写盘）。副作用是 `test_real_disk_eight_alias_ids_are_rejected_and_canonicals_pass` 里「research 放行要带 `allow_non_active=True`」那句注释的前提变了：现在不带该参数也放行。用例本身仍绿，但注释已过期，需下一批顺手订正。
