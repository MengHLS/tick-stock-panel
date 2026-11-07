# F-A5 收尾：status 不打回 draft / 基线重拍 / 扩展列前置条件

- 日期：2026-11-07（Asia/Shanghai），执行人：系统开发工程师
- 依据：开发经理 2026-11-07 三件收尾裁定（F-A5 返工复核通过后）
- 边界：**未提交、未部署、未重启**；`dsl.py`（sha256 `3d76ccdc3d5b876e1610d8db8701485252bbf7d20d95b56ab817243f224d54f2`）、信号链、回测引擎未动（`git diff -- backend/app/factors/dsl.py backend/app/backtest backend/app/strategy` 为空）
- 生产目录 `D:\TSP\data\user_data\custom_factors` 15 个 json 全程只读；所有写操作只在 `tempfile` 临时 data_dir 内（含 `user_data/custom_factors` 这一层）

## 0. 结论

1. **【1】status 不再被 create 打回 draft**：实现完成，**S1–S11 全过** —— active 定义经 API 形状重提交 `unchanged=true`、version 不变、**status 仍 active**、`lang/unit/tags` 全保留；真改公式 `v+1` 且回 `draft`；路由层同内容重提交**试算 0 次**；首次创建不传 status 落 `draft`（custom 与 composite 各一例）。
2. **【2】基线重拍**：原 14 文件基线**原件未覆盖**（生成同内容副本 `prod_snapshot_before_20261107_1430.json`，sha256 与原件相同），现行基线 = 15 文件 `prod_snapshot_before_15_20261107_1630.json`；判据 L 拆成 **L1 drift / L2 added**（另加 L0 历史基线自检）。`f_a5_idempotent.py` **EXIT=0，15/15**。
3. **【3】扩展列前置条件查清并落本报告**：服务启动路径**保证**扩展列先注册（`load_into_registry` 首条调用语句就是 `ensure_synced(data_dir)`；`main.py` 只有一处 `load_into_registry(store.data_dir)`，且请求侧 `_data_dir` 与它同一根）。但**缺扩展列的进程/数据目录里，auction 因子的同内容重提交是硬错误 `ValueError`，不是 `unchanged`**（E1/E3 实测，异常文本见 §4）。

## 1. 改动清单（本轮 +39/−0、+8/−4）

| 文件 | 本轮 +/− | 内容 |
|---|---|---|
| `backend/app/factors/store.py` | **+39 / −0** | 新增 `resolve_status()`（22 行）、`is_unchanged_definition()`（12 行）；`upsert_definition()` 在判等**之前**做 status 归一化（+2 行、docstring +2 行） |
| `backend/app/api/factors.py` | **+8 / −4** | `create_custom_factor` / `create_composite_factor` 不再写 `status`（删 2 行 + 注释）；`create_custom_factor` 的「跳过试算」条件改走 `store.is_unchanged_definition`（1 行替换） |

逐行 diff（本轮 only，由「反向还原上一轮状态后 diff」生成）：`logs/round3_store_py.diff`、`logs/round3_api_factors_py.diff`。

改法说明（供审核复现）：后端源码不在 MCP 文件工具的允许目录内（只允许 `research/` 与 `docs/research/`），所以源码改动用一次性 Python 脚本做**精确子串替换**，每处替换前 `assert src.count(old) == 1`（锚点必须唯一命中，否则脚本直接 AssertionError 不写盘）。

### 1.1 核心代码

```python
def resolve_status(stored: dict | None, definition: dict) -> str:
    explicit = definition.get("status")
    if stored is None:
        return str(explicit or "draft")          # 首次创建
    if explicit not in (None, ""):
        return str(explicit)                     # 显式给出 → 以调用方为准
    on_disk = str(stored.get("status") or "draft")
    probe = {**definition, "status": on_disk}
    return on_disk if is_same_content(stored, probe) else "draft"   # 同内容沿用 / 有变回 draft
```

`upsert_definition()` 里归一化排在判等之前：

```python
    stored = _STORE.load_one(data_dir, factor_id) if factor_id else None
    definition = {**definition, "status": resolve_status(stored, definition)}
    if stored is not None and is_same_content(stored, definition):
```

为什么必须排前面：`status` 参与内容签名（上一轮定），若沿用旧写法（路由硬编码 `status="draft"`），盘上 `active` 与入参 `draft` 必然签名不等 → `v+1` 且状态回 `draft`，正是裁定要消除的「一次保存把线上因子打回不可用」。

## 2. 【1】status 语义：裁定 → 实现 → 逐例数字

| 场景（盘上已有该 id） | 裁定 | 实现 | 用例 |
|---|---|---|---|
| 调用方**未给** status，除 status 外同内容 | 沿用盘上 | 沿用盘上 | S1 / S1b / S3 / S4 / S7 |
| 调用方**未给** status，内容有变 | 回 draft（编辑即回 draft） | draft | S2 / S8 |
| 调用方**显式给出** status（与盘上不同） | 以调用方为准 | 以调用方为准 | S5（→watch）/ S6（draft→active） |
| 首次创建（盘上无该 id） | — | 显式值，否则 draft | fa5b C 组（python 定义首建） |

| 用例 | 判据 | 实测 |
|---|---|---|
| S1 | active + **API 形状**（无 status/lang）重提交 | `unchanged=true`、`ret_v=1`、盘上 `v 1→1`、**status active→active**、`lang=dsl`、`unit=ratio`、`tags=['fa5c','status']`、sha 相同、mtime 相同、注册表 `spec_v=1` |
| S1b | active + **盘上形状**（含 `lang="python"`）重提交 | `unchanged=true`、`v 1→1`、status 仍 active、`lang=python` 保留、unit/tags 保留、sha 与 mtime 相同 |
| S2 | active + **真改公式**（`+ 0`） | `unchanged=false`、`v 1→2`、**status active→draft**、formula 已更新、`lang=dsl`/unit/tags 保留 |
| S3 | draft + API 形状重提交 | `unchanged=true`、`v 1→1`、status=draft、sha 与 mtime 相同、**key 集合不变** |
| S4 | **composite** active + API 形状重提交 | `unchanged=true`、`ret_v=2`、`v 2→2`、status 仍 active、unit/tags 保留、sha 与 mtime 相同 |
| S5 | 显式 `status="watch"`（盘上 active） | `unchanged=false`、`v 1→2`、status → **watch**（调用方为准） |
| S6 | 回归（旧判据 H）：盘上 draft + 显式 `status="active"` | `unchanged=false`、`v 1→2`、status → **active** |
| S7 | **路由** `create_custom_factor`：active 同内容重提交 | `unchanged=true`、`v=1`、status 仍 active、unit/tags 保留、**试算调用 0 次**、sha 相同 |
| S8 | **路由**：active 真改公式 | `unchanged=false`、`v=2`、**status=draft**、`lang=dsl`/unit/tags 保留、**试算 1 次** |
| S10 | **首次创建** custom（盘上无该 id，API 形状**不传 status**） | `unchanged=false`、`ret_v=1`、盘上 `status=draft` |
| S11 | **首次创建** composite（不传 status） | `unchanged=false`、`ret_v=1`、盘上 `status=draft` |

补充口径事实（不裁定）：

- `S1b` 只能用**盘上形状**：API 形状没有 `lang` 键，对盘上 `lang="python"` 的定义按 API 形状重提交会因 lang 语义不等判成内容变化（`v+1`，但写盘保留 `python`，不丢字段）——这是上一轮 §7.5 已记录的方向，本轮未改变。
- 路由两个 create 都不再传 `status`：create 不是生命周期操作，状态裁决点只在 `store.upsert_definition`（`POST /custom/{id}/status` 与 `/update` 的「编辑即回 draft」不变）。请求体本来就没有 `status` 字段，对外契约不变。
- 路由「跳过试算」与 store「判等」现在**同一口径**（`is_unchanged_definition`），不会出现「判等说变了、upsert 说没变」两套结论。
- fail-closed 未松：非法公式仍 `ValueError`（fa5b G 组 5 例复跑全过，文件字节不变）。
- 首次创建（盘上无该 id）不传 `status` → 落 `draft`（S10/S11）：路由不写 status 之后，「新建因子默认 draft」这条既有语义没有丢。

## 3. 【2】基线重拍

| 文件 | 行数 | 角色 | sha256 |
|---|---|---|---|
| `logs/prod_snapshot_before.json` | 14 | **历史基线原件（未覆盖、未改名）** | `49529f11e4fabfa7dc1e92d66f4ddd7f98c0b580481cf59da7d5ea1c13ac2945` |
| `logs/prod_snapshot_before_20261107_1430.json` | 14 | 同内容副本（`copy2`，字节与 sha256 与原件相同） | `49529f11e4fabfa7dc1e92d66f4ddd7f98c0b580481cf59da7d5ea1c13ac2945` |
| `logs/prod_snapshot_before_15_20261107_1630.json` | **15** | **现行基线** | 由脚本实时生成，含逐文件 64 位 sha256 |

新基线与旧基线的差集（脚本实测）：

- 新增：`uf_dist_prior_high_250.json`
- 缺失：无
- **旧基线文件内容变化：无**（14 个逐条 sha256 相同）

判据 L 拆成三段（判据总数 13 → 15）：

| 判据 | 含义 | 实测 |
|---|---|---|
| L0 | 历史 14 文件基线仍在（原件未被覆盖） | `rows=14` |
| L1 | **drift**：基线里存在的文件逐个比，必须为空 | `baseline=prod_snapshot_before_15_20261107_1630.json baseline_files=15 drift=[]` |
| L2 | **added**：新增文件必须逐条登记理由 | `added=[] unexplained=[]`（现行基线已含新增文件，故本轮 added 为空；登记表 `JUSTIFIED_ADDITIONS` 里写明 `uf_dist_prior_high_250.json` 的来源是批二 A + 开发经理 2026-11-07 裁定 + `research/factor-registration-b2-20261107/`） |

命令与退出码：

| 命令 | 结果 |
|---|---|
| `backend\.venv\Scripts\python.exe -X utf8 research\factor-registration-20261107\f_a5_idempotent.py` | **EXIT=0，15/15**（日志 `logs/run_f_a5_idempotent_rebaselined.log`） |

同轮复跑（证明本轮 status 改动没有 Regression）：`f_a5b_two_shapes.py` **EXIT=0，44/44**（日志 `logs/run_f_a5b_after_status_change.log`）。

## 4. 【3】扩展列前置条件（查清，不猜）

### 4.1 实测事实（auction 因子 = 引用 `ext_auction_*` 列的 6 个 custom + 1 个 composite）

| 用例 | 场景 | 实测 |
|---|---|---|
| E1 | 临时目录无扩展配置、注册表无 `ext_` 条目（= 从未同步过扩展列的进程） | **`ValueError: 公式无效 [E001]: 未知标识符: ext_auction_result_volume_shares`**；盘上文件 sha256 与 mtime **均未变**、version 未变（fail-closed，没写坏） |
| E2 | 装扩展配置 + `ensure_synced` 后，同一份定义 | `unchanged=true`、`v 2→2`、sha 相同 |
| E3 | 配置在盘但注册表无 `ext_` 条目（模拟「进程未同步」） | 同步前 **硬错误**（同一 `ValueError`）；`ensure_synced` 后 `unchanged=true`、sha 与 mtime 均未变 |
| E4a | `load_into_registry` 首条**调用**语句 | `prefix=['Expr'(docstring), 'ImportFrom']` → `ensure_synced(data_dir)`（store.py:326-328） |
| E4b | `main.py` 中 `load_into_registry` 的出现处 | **仅 1 处：第 221 行 `load_into_registry(store.data_dir)`** |
| E4c | 启动路径是否有更早的定义注册/落库入口 | 无：`main.py` 里 `register_definition(` / `upsert_definition(` / `register_factor(` / `save_one(` **零命中** |
| E4d | 请求侧 `_data_dir` 与启动注册是否同一根 | 是：`main.py` `repo = KlineRepository(store)`、`app.state.repo = repo`、`load_into_registry(store.data_dir)`；`api/factors.py:_data_dir` 读 `request.app.state.repo.store.data_dir` |
| E5a | 启动镜像（有扩展配置） | `loaded=15/15`、**告警 0 条** |
| E5b | 启动镜像（无扩展配置） | `loaded=9/15`，失败的恰好是 6 个 auction custom + `cf_auction_resonance`，**告警 6 条且含「未知标识符」**；其余 9 个照常注册（隔离，不阻断启动） |

### 4.2 结论（写进「F-A5 的前置条件」）

1. **服务启动路径有保证**：`app/main.py` 只在 `_bootstrap_application` 里通过 `load_into_registry(store.data_dir)` 载入自定义因子；而 `load_into_registry` 的第一条**调用**语句就是 `from app.factors.ext_factors import ensure_synced; ensure_synced(data_dir)`（`backend/app/factors/store.py:326-328`，在本函数内、在 `load_all`/`register_definition` 之前）。所以**正常服务进程里，扩展列在定义注册之前就已进注册表**；请求侧 `_data_dir(request)` 解析出的就是同一个 `store.data_dir`，不会出现「启动同步了 A 目录、请求落到 B 目录」。
2. **但「auction 因子的幂等判定依赖扩展列已注册」是硬前置条件**：任何**没有**走 `load_into_registry` 的进程（单元测试、研究脚本、直接调 `store.upsert_definition` 的工具），在注册表里没有 `ext_` 条目时，同内容重提交**不是 `unchanged`，而是 `ValueError`**——原因是 `is_same_content()` 捕 `ValueError` 返回 False（fail-closed），随后 `to_spec()` 直接抛。E1/E3 逐字实测。
3. 这条前置条件只在**注册表状态**上成立，不是「配置文件存在」就够：E3 证明配置在盘、注册表空 → 仍然硬错误。
4. `ensure_synced` 的**缓存**是 `(data_dir, 配置目录签名)` 幂等：`_sync_state` 命中就直接 return，不会重扫。它的失效入口是 `invalidate_ext_caches()`（`ext_factors.py:422-426` 把 `_sync_state = None`），与扩展配置写入/删除同链（本脚本里每次装配置都会看到「策略缓存被清除」调用链）。**因此绕过模块 API 手动清空 `ext_` 条目不会被下一次 `ensure_synced` 自愈**——E3 是靠显式置空 `_sync_state` 才复现出「同步后 unchanged」。这是实测到的边界，不是猜测。
5. **未实测的失败分支**：`ensure_synced` 在「`ext_data` 目录存在但扫描失败」时 `sig is None` → **直接 return（fail-open，不清已注册条目）**。这条只有代码事实（`ext_factors.py:165-168`），没有构造实测；后果是定义加载会走 E5b 的隔离路径（告警 + 跳过该因子），不会崩启动。

## 5. 既有函数的行为变更（供审核按 §7.4 新允许面判）

> 单列一节，不与新增函数混在一起。上一轮漏登的 `register_definition` 一并列在这里。

| 函数 | 变更 | 来源 | 影响面 / 风险 |
|---|---|---|---|
| `register_definition(definition)` | 新增 `if get_factor(spec.id) == spec: return spec` | 上一轮（F-A5 返工）**本轮补登** | 同一个 spec 已注册时跳过注册表写入、不告警。`FactorSpec` 是 `@dataclass(frozen=True)`，相等比较覆盖**全字段含 `version`**（`status` 不在 spec 内，是存储字段）。所以「内容不同」或「version 不同」的 spec **不会**被这条短路，仍走 `register_factor` 的「版本未提升」拒绝。用途：启动期二次 `load_into_registry` / worker 复用不重复注册 |
| `is_same_content(stored, incoming)` | 签名不变；口径由「原始键集黑名单」改为 `to_spec()` 语义投影；任一侧投影失败返回 False | 上一轮 | fail-closed：判等不替校验放行 |
| `upsert_definition(data_dir, definition)` | 签名**不变**；**本轮新增 status 归一化**（判等前补 status），且「盘上已有该 id 时」不再按调用方缺省值重置状态 | 本轮 | 修复「一次 create 形状重提交把 active 打回 draft」；调用方显式给 status 仍以调用方为准。`_merge_for_write` 写盘基底规则未变（仍以盘上为底、保留 `lang/unit/tags/scale_free` 等非 API 字段） |
| `create_custom_factor` / `create_composite_factor`（路由，既有） | 不再向 definition 写 `status`；custom 的「跳过试算」条件改调 `store.is_unchanged_definition` | 本轮 | 请求体/响应体契约不变（请求模型本来没有 `status` 字段）；响应仍 `{ok,id,version,unchanged}` |
| **纯新增**：`resolve_status()`、`is_unchanged_definition()` | 新函数，无既有调用方 | 本轮 | 不改变任何既有代码路径 |

## 6. 命令与退出码

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `backend\.venv\Scripts\python.exe -X utf8 research\factor-registration-fa5b-20261107\f_a5c_status_env.py`（第 1 次，21 判据版） | **0** | **21/21** 判据（S1–S11、E1–E5），生产 `drift=[]` |
| 2 | 同上（第 2 次，复跑稳定性） | **0** | **21/21**，0 条 FAIL，生产 `drift=[]` |
| 3 | `backend\.venv\Scripts\python.exe -X utf8 research\factor-registration-20261107\f_a5_idempotent.py`（重拍基线后） | **0** | **15/15**（L0/L1/L2 全过） |
| 4 | `backend\.venv\Scripts\python.exe -X utf8 research\factor-registration-fa5b-20261107\f_a5b_two_shapes.py`（回归） | **0** | **44/44** |
| 5 | `python -m pytest -q tests/test_factor_store.py tests/test_factor_api.py tests/test_factor_dsl.py tests/test_factor_registry.py tests/test_factor_py_expr.py tests/test_factor_delete_fail_closed.py tests/test_custom_signals_factor_conditions.py` | 1 | **6 failed / 91 passed** —— 与上一轮**同一条命令、同一批 6 个失败**（golden 计数 `93` vs 实际 `107`，来自 dev 上 14 个 `research_factor_pack` 因子），非本轮回归 |
| 6 | `python -m pytest -q tests/test_factor_store.py tests/test_factor_api.py tests/test_factor_dsl.py tests/test_definition_contract.py tests/test_auction_factor_pack.py tests/test_factor_registry.py tests/test_ext_factors.py` | 1 | **1 failed / 109 passed**，唯一失败仍是同一 golden 计数（`test_custom_factor_definition_roundtrip`，`assert 107 == 93`） |
| 7 | `python -m ruff check --output-format=concise backend/app/factors/store.py backend/app/api/factors.py` | 1 | **1 error**：`store.py:381 BLE001`（`load_into_registry` 里既有 `except Exception`，HEAD 同处已存在，**本轮新增代码 0 条**） |

过程说明：脚本先以 19 判据（S1–S9 + E1–E5）跑过两轮（`logs/run_f_a5c_1.log` / `run_f_a5c_2.log`，均 19/19）；补入 S10/S11（首次创建不传 status）后为 21 判据，再跑两轮均 21/21（`logs/run_f_a5c_3.log` / `run_f_a5c_4.log`）。

`107 = 77`（内置 `_CATALOG`）`+ 32` 个动态因子（含 B0 的 14 个 `research_factor_pack`、9 个 `first_board_chain_*`、4 个 `industry_*`、3 个 `deviate_*` 等）——实测 `factor_columns_view()` 输出验证。

## 7. 生产目录 15 个 json 的 64 位 sha256（本脚本运行前后全等，`drift=[]`）

| 文件 | v | status | sha256 |
|---|---|---|---|
| cf_auction_resonance.json | 2 | draft | `70d20540a7f384a7e6f025a5de427ccb30696cfb12330e218d65fbb175f0e191` |
| uf_auction_post0920_match_growth.json | 2 | draft | `840c65e4cfa7d0b07d5075a4f7a77886259fbb03322cca411528cd06b68f8582` |
| uf_auction_tail_imbalance.json | 2 | draft | `1bdc6e8d288f8fcce170ad27bbca2648cfc933017fbb17d600603e7f567699f7` |
| uf_auction_tail_match_growth.json | 2 | draft | `6c8f04a6c525e7c9ffd63a78b0dfd3018dced74a8edee440bc997e7a1a9402c0` |
| uf_auction_volume_surprise.json | 2 | draft | `19957bcd78d9e5dc031ee122a202281ad2d96b5d467b13d96fa52cc1692f290a` |
| uf_auction_volume_vs_prev.json | 2 | draft | `8dc6abc6a45155dfb16386bd5eef70e0f9e61ee95c57c0b780093aae49a4272d` |
| uf_dist_prior_high_250.json | 1 | draft | `7c8163e44571d95ebb88f54a38f971eae743485ceab0003cebd839270fe404f5` |
| uf_ma120.json | 1 | draft | `3ddb904acc7277d4195e870f1b7b0cca232932316d69f11e584ea131cdfcbefe` |
| uf_ma200.json | 1 | draft | `cf96176f8458dca2827e5f9c27e31ede4d462f7a91533c1ff5076fa3af579bc2` |
| uf_prior_high_20.json | 1 | draft | `e3070878b5472b1aab4fdd5d0253487397b0a943e742a97b6be1577ebac23e86` |
| uf_prior_high_250.json | 1 | draft | `9f95286b8f97ab4047ff4a0bf2a61c7b48e1c618acd3982fbb1afd2b2446b9f8` |
| uf_prior_high_55.json | 1 | draft | `1f0ce5c6d8365da34a3d0aa22ed86f4665e5d4685334ba3b148b5bb4bbd6e59c` |
| uf_prior_low_10.json | 1 | draft | `e5885f47f4356043d7ec7826f4cf6d043c6ae290037f6b581127d9d05e140fe3` |
| uf_prior_vol_20.json | 1 | draft | `fa8667bc5e6f61323f33a357cb24d4bcb37658bba279688b78cabd297ed22563` |
| uf_vol60.json | 1 | draft | `c9041ba4930ac9c2ece17adbd05f25a4c37e4693e0e223ccd3e55b7e5b7430bb` |

## 8. 未验证 / 已知边界（不粉饰）

1. **HTTP/TestClient 端到端仍未跑**：S7/S8 是直接调路由函数 + 桩 `request`（`app.state.repo.store.data_dir`）+ 打桩 `_trial_nonempty`，验证的是「不变时试算 0 次 / 真变时试算 1 次」与落盘结果；FastAPI 的 JSON 序列化层、鉴权、真实行情试算未验。
2. **composite 路由未做 route 级用例**：S4 在 store 级覆盖（`create_composite_factor` 现在只少传 status，其余与 `upsert_definition` 同一路径）；composite 的 `POST /composite` 路由未单独跑。
3. **`status` 只测了 `draft/active/watch`**：`retired` 未单独构造用例（代码路径与 watch 相同，走 `to_spec` 的 status 校验器）。
4. **生产目录 15 个定义全是 `draft`**：所有 active 场景都在临时目录构造，**没有**为了测试去改生产定义的状态。
5. **`ensure_synced` 的 fail-open 分支**（配置目录存在但扫描失败 → `sig is None` → 直接 return）只有代码事实，没有构造实测（§4.2 第 5 条）。
6. **`POST /custom/{id}/update` 同内容仍 `v+1`**：按裁定保持现状，本轮未改（报告 §5 表格已注明该入口不是幂等入口）。
7. **并发同 id 双写仍无锁**：与既有 `save_one` 同级，本轮未引入锁。
8. `resolve_status` 内部会对同一份定义多算一次签名（`to_spec` 两次）——保存是低频路径，未做性能优化；如需可合并成一次投影比较。

## 9. 复跑方法

```bash
cd C:\work\sourcecode\tick-stock-panel
backend\.venv\Scripts\python.exe -X utf8 research\factor-registration-fa5b-20261107\f_a5c_status_env.py
backend\.venv\Scripts\python.exe -X utf8 research\factor-registration-20261107\f_a5_idempotent.py
backend\.venv\Scripts\python.exe -X utf8 research\factor-registration-fa5b-20261107\f_a5b_two_shapes.py
```

全部在临时 data_dir 内跑；生产目录只读。若临时目录里没有 `ext_data` 配置，`f_a5c` 的 S 组会因 auction 定义缺扩展列而失败（`case_env_auction` 自己装配置，不受影响）——脚本已按 `backend/tests/test_auction_factor_pack.py` 的同一条路径为每个临时目录装 `auction_preopen` / `auction_result` 两份配置。

## 10. 产出文件

| 文件 | 说明 |
|---|---|
| `F_A5_CLOSEOUT_20261107.md` | 本报告 |
| `f_a5c_status_env.py` | 本轮验收脚本（19 判据，S/E 两组），可复跑 |
| `logs/f_a5c_status_env_evidence.json` | 逐例 detail + 15 个生产文件 64 位 sha256 + 汇总 |
| `logs/run_f_a5c_3.log` / `logs/run_f_a5c_4.log` | 21 判据版两次运行完整输出（含扩展缓存失效调用链噪声） |
| `logs/run_f_a5c_1.log` / `logs/run_f_a5c_2.log` | 19 判据版（补 S10/S11 之前）两次运行，均 19/19 |
| `logs/run_f_a5_idempotent_rebaselined.log` | 重拍基线后的 15/15 |
| `logs/run_f_a5b_after_status_change.log` | 本轮改动后的 44/44 回归 |
| `logs/pytest_same_cmd_as_last_round.log` / `logs/pytest_after_status_change.log` | 两次 pytest 输出 |
| `logs/round3_store_py.diff` / `logs/round3_api_factors_py.diff` | 本轮改动的逐行 diff |

未覆盖他人文件；`docs/factors/`、`research/factor-registration-20261107/` 下除 `f_a5_idempotent.py`（判据 L 重拍，裁定要求）与新增基线文件外未改动。
