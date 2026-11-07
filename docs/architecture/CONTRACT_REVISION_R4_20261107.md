# 契约修订对照 R4（v0.4 冻结版定稿）

> 对象：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md`
> 基线：v0.4 草案（16:33:03，111,368 B / 1,226 行 / `head -c 110416` → `f5375c01…`）
> 结果：v0.4 **冻结**（见 §7 四元组）
> 规则：逐条「原句 → 新句 → 依据 → 可复跑命令」。未列出的改动视为未发生。

---

## 0. 前置事实：这一轮为什么先修「引用口径」

`store.py` 在本轮被改写两次：

| 时间 | 字节 | 行 | `git diff --numstat` |
| --- | --- | --- | --- |
| 16:23:11 | 17,315 | — | `+148/−1` |
| **16:33:52** | **19,502** | **409** | **`+187/−1`** |

开发经理派单给的行号（`to_spec:52`、`register_definition:169`、`_canonical:203`、`content_signature:218`、`is_same_content:247`、`_merge_for_write:261`、`upsert_definition:276`、`load_into_registry:317`、`_validate_definition:354`）取自 16:23:11 版；16:33:52 版新增了 `resolve_status:276` 与 `is_unchanged_definition:298`，`upsert_definition` 顺延到 310，`load_into_registry` 顺延到 356。

**同一份契约若继续按行号写允许面，10 分钟内即过期两次**，审核无法据以判定越界（这正是上一轮 89,709→109,914→110,944 三次改写暴露的同一个问题）。因此 R4 的第一项改动不是内容，而是**引用口径**：允许面按符号定义，行号只作参考并锚定在一份声明了哈希的快照上。

同样，契约文件本身在本轮被改了 4 次（89,709 → 109,914 → 110,944 → 111,368 → 128,007 B）。为终止「审中改写」，本次给出四元组并声明冻结（§7）。

---

## 1. §7.4 整节重写（原句 → 新句）

**原句（v0.4 草案 §7.4 第 3–4 条）**

> **改动面（v0.4 更正，替换 v0.3 的「不动 store」）**：为落地 `F-A5`，**允许**在 `store.py` **新增幂等入口**——`content_signature(definition)` / `is_same_content(stored, incoming)` / `upsert_definition(data_dir, definition)` 三个纯新增函数（`store.py:207-257`），以及 `api/factors.py` 保存分支改为经 `upsert_definition` 落库（`api/factors.py:333-360`）。这是**唯一**允许的 store 改动面。

**新句（v0.4 冻结版 §7.4.2 / §7.4.3）**

> **允许面（函数级，唯一）**：`_NON_CONTENT_FIELDS`、`_GROUP_DEFAULT`（常量）、`_canonical(value)`、`content_signature(definition)`、`is_same_content(stored, incoming)`、`_merge_for_write(stored, definition)`、`resolve_status(stored, definition)`、`is_unchanged_definition(stored, definition)`、`upsert_definition(data_dir, definition)` 共 9 个符号；
> **允许的既有函数变更（唯一一处）**：`register_definition` 新增幂等跳过 `if get_factor(spec.id) == spec: return spec`，边界 = 只跳过「同 spec」、不吞错、不放宽校验；
> **允许的调用方变更（唯一一处）**：`api/factors.py` 的 `POST /custom` 经 `upsert_definition` 落库并用 `is_unchanged_definition` 预判；
> **禁止面 5 条**：`save_one`/`load_one`/`delete_one` 语义、`to_spec` 校验、`_STORE` 路径与 JSON 结构（含「不得新增落盘字段」）、幂等不得跳过校验、`load_into_registry`/`_validate_definition`/`_definition_dependencies` 不得改签名语义。

**依据**

1. 派单要求「允许面按实际改，不要留『契约说 3 个新函数、代码里有 5 处改动』这种自相矛盾」。实测新增函数为 5 个业务函数 + 2 个常量 + 1 个既有函数变更 + 1 个调用方变更，原句的「三个」已失真。
2. `register_definition` 的既有语义变更是真的：`store.py:177-178` 有 `if get_factor(spec.id) == spec: return spec`，且函数 docstring（`:170-175`）明写「同一个 spec 已注册时按幂等跳过（F-A5）」。原文只字未提，属漏登记。
3. 「只跳过同 spec」的边界是可验证的：`FactorSpec` 21 字段 `dataclasses.fields` 全等才走 early return，否则落到 `register_factor(spec)` 的版本门禁。

**可复跑**

```powershell
cd C:\work\sourcecode\tick-stock-panel
# 允许面符号是否都在
Select-String -Path backend/app/factors/store.py -Pattern '^(def |_NON_CONTENT_FIELDS|_GROUP_DEFAULT)' |
  ForEach-Object { "$($_.LineNumber)`t$($_.Line.Trim())" }
# 快照一致性
(Get-Item backend/app/factors/store.py).Length                      # 19,502
(Get-FileHash backend/app/factors/store.py -Algorithm SHA256).Hash   # DE77EAE6…701199
git diff --numstat -- backend/app/factors/store.py                   # 187  1
```

---

## 2. §7.4.1 新增：引用口径（按符号，不按行号）

**原句**：无（v0.4 草案全节按行号引用）。

**新句**

> 对 `store.py` 的引用**一律按符号**，行号只作参考、**不作判据**。审核判据 = 符号存在性 + `git diff` 的 hunk 归属。快照：19,502 B / 409 行 / sha256 `de77eae6…701199`，mtime 2026-11-07 16:33:52。

**依据**：§0 的两次改写事实。副产物：§7.6 `F-A5` 与 §9 两处遗留的 `store.py:207-257` 一并改为符号定位（见 §3、§8）。

---

## 3. §7.6 `F-A5` 行：过期路径与 mtime 校正

**原句**

> 工作区已有**未提交**实现 `backend/app/factors/store.py:207-257`（`content_signature` / `is_same_content` / `upsert_definition`）+ `backend/app/api/factors.py:333-360`；……`git status` 显示两文件为 `M`，mtime 15:35:28。

**新句**

> 工作区已有**未提交**实现 `store.py` 的 `content_signature`/`is_same_content`/`resolve_status`/`is_unchanged_definition`/`upsert_definition`（符号定位，见 §7.4.1）+ `api/factors.py` 的 `POST /custom`（`:333-366`）；……mtime 16:33:52。

**依据**：函数已增至 5 个（新增 `resolve_status`、`is_unchanged_definition`）；`api/factors.py` 的 create 分支现为 `:333-366`（含 `is_unchanged_definition` 预判与 `upsert_definition` 调用）。

**可复跑**：`git status --porcelain -- backend/app` → `M backend/app/api/factors.py`、`M backend/app/factors/store.py`。

---

## 4. §7.7.2 判定矩阵：`base` 行扩为 `base ∪ virtual`

**原句**

> | `kind == "base"` | 不适用（base 无 status；其准入由台账 G1–G3 承担） | 同左 |

**新句**

> | `kind` ∈ {`base`, `virtual`} | 不适用（两者都无 `status`；准入由台账 G1–G3 与代码审核承担，见 §7.8.3） | 同左 |

**依据**：§7.8.3 已把 `base / virtual（catalog 77）` 判为「不 gate」，§7.7.2 只提 `base` 会与之一致性缺口。实测 `all_factors()` = 192 = `base` 117 + `virtual` 61 + `custom` 14；活策略 `custom_factor_first_board_chain_strict_rebreak` 引用 `distance_to_high_60d`（`kind=virtual`），`custom_mvoa5yy6` 引用 `limit_up_count_20d`（`kind=virtual`）——若把 virtual 当 `draft`，会误拦 2 个活策略。

**可复跑**

```powershell
cd C:\work\sourcecode\tick-stock-panel\backend
.\.venv\Scripts\python.exe -c "import sys;sys.path.insert(0,'.');import collections;from app.factors.registry import all_factors;print(collections.Counter(s.kind for s in all_factors()))"
```
（输出 `{'base': 117, 'virtual': 61, 'custom': 14}`）

---

## 5. §7.7.6 行号校正

**原句**

> 当前内容签名把 `status` 计入（`store.py:183-191` 节注释；`_NON_CONTENT_FIELDS` 定义在 `:189`，只排除 `version/created_at/updated_at`）

**新句**

> 当前内容签名把 `status` 计入（`store.py:183-198` 节注释；`_NON_CONTENT_FIELDS` 定义在 `:199`，只排除 `version/created_at/updated_at`）

**依据**：16:33:52 版 `_NON_CONTENT_FIELDS` 在 `:199`，注释块 `:183-198`。

---

## 6. 新增 §7.9：`POST /custom` 对既有定义的 `status` 处置

**原句**：无（v0.4 草案无此条；`api` 侧行为未在契约里约束）。

**新句（摘要）**

> **裁定：保留盘上 `status`；只有「内容变化」才回 `draft`。**
> `resolve_status` 唯一四分支：R1 盘上无 → `draft`（忽略入参）；R2 盘上有且显式给 → 以入参为准（API 不可达）；R3 盘上有、未给、除 status 外等价 → **沿用盘上**、版本不变、`unchanged=true`、不写盘；R4 盘上有、未给、内容有变化 → **`draft`**、版本 +1。
> 硬规则：**判等前必须先归一化 status**，否则每个 `active` 定义都被判成「变了」；`updated_at` 不参与判等，R3 不写盘 → 字节与 mtime 都不变（这是 `F-A5` 判据成立的前提）。
> 新增判据 `F-A18`–`F-A21`。

**依据（逐条实测）**

1. `content_signature` 投影里含 `"status": str(definition.get("status","draft"))`（`store.py:233`）；`_NON_CONTENT_FIELDS` 只排除 `version/created_at/updated_at`（`:199`）。
2. 若 create 硬编码 `status="draft"`：盘上 `active` → 入参 `draft` → 签名不等 → 判为内容变化 → 版本 +1、落盘 `draft`。**闸门上线后即一次隐形停机**（该因子在 `production` 立刻 `FS01`），并触发该因子缓存重算。
3. 与既有编辑语义一致：`POST /custom/{id}/update` 在公式变化时置 `status="draft"`、仅改名称/分组时保留（`api/factors.py:427`）。R4 分支与之同一条规则，两端口不得有两种语义。
4. R2 在 API 上不可达：`CustomFactorCreateRequest`（`api/factors.py:236-242`）**无 `status` 字段**，Pydantic 丢弃未知字段。根因不是入参带 status，而是判等忘归一化。
5. 尚未闭环（已在契约里写明，不圆）：`POST /custom/{id}/status` 接受任意四态（`:511`），**无 V3 校验** → §7.5-5 目前是人工纪律，不是代码约束。

**可复跑**

```powershell
cd C:\work\sourcecode\tick-stock-panel
Select-String -Path backend/app/factors/store.py -Pattern 'def resolve_status|def is_unchanged_definition|"status": str' | ForEach-Object { "$($_.LineNumber)`t$($_.Line.Trim())" }
Select-String -Path backend/app/api/factors.py -Pattern 'class CustomFactorCreateRequest' -Context 0,7
```

---

## 7. 新增 §7.10：`referenced_factor_inventory` 先行 + L0–L3 分级放行

**原句（§7.8.5）**

> 存量清单（`referenced_factor_inventory`：文件 + 提交 id + `resolved_id` + 状态）由因子工程师在批二**前**产出，本契约只要求这份清单存在且机器可读。

**新句（§7.10.2）**

> 路径 `docs/architecture/evidence/referenced_factor_inventory.json` + 同名 `.sha256`；生成脚本 `backend/scripts/build_referenced_factor_inventory.py`；**生成 = 系统开发工程师（唯一实现者）；签认 = 因子工程师（口径归属）；消费 = 闸门（只读）**。字段级定义：顶层 8 项 + `records[]` 17 项（`ref_namespace` / `verdict` / `class` / `gate_mode` / `path_scope` / `evidence` 等）。**它是闸门实现的第一个交付，必须先于 `assert_factors_usable` 接线。** 判据 `F-A22`–`F-A29`。

**新句（§7.10.3 命名空间优先级，本次新增的裁定）**

> **N1**：`field:X` 先查 `ALLOWED_FIELDS`，命中即 `column`，**不进闸门**；仅当不在基础列集合时回落 `factors.registry`。现实现是并集（`custom_signals.py:92-103`），集合语义不表达优先级，实现须显式排序。
> **N2**：`namespace=column` 不得因「名字恰等于某因子 id」而判 status。四个冲突名：`ma20`/`ma60`/`boll_lower`/`boll_upper`。
> **N3**：登记一处真实分叉 —— 历史路径基础列存在 → `column`；盘中快照无滚动窗口 → 同名基础列缺失 → `materialize_factor_columns` 补算同名因子（`custom_signals.py:106-134`）→ 同一信号两路径 `namespace` 可能不同，须按 `path_scope` 逐路径记录，不一致标 `path_divergence=true` 且不得判 `allow`。

**依据（逐条实测，16:30–16:36）**

1. `gate.py` 不存在；`alias_of`/`FS03`/`assert_factors_usable` 在 `backend/app/**` 命中 0。
2. `custom_factors` 15/15 `draft`、`active = 0`；pack 14 个 `kind="custom"` 无 status（`hasattr(spec,"status") == False`）。
3. `referenced_factor_inventory` 全仓 4 处 = 契约 1 + 独立审核报告 3（`BATCH2_ABC_AUDIT_20261107.md:15,215,217`），**0 产物**。
4. 冲突名的实测来源：`ALLOWED_FIELDS` 含 `ma5..ma60`/`boll_upper`/`boll_lower`（`custom_signals.py:41-67`）；pack `_DEFINITIONS` 含 `ma20`/`ma60`/`boll_lower`/`boll_upper`（`factor_specs.py:29-64`）。
5. `enabled=true` 活配置 = 22 = `custom_signals` 21 + `monitor_rules` 1；另 2 个 `strategy_overrides` 只在 `basic_filter.enabled` 为 true，非顶层开关。
6. 按 N1/N2 被 `FS01` 拦的 = **0 条**；若违反 N2 会误拦 **7 条**：`boll_breakdown_lower`、`boll_breakout_upper`、`ma20_breakdown`、`ma20_breakout`、`ma_dead_5_20`、`ma_golden_20_60`、`ma_golden_5_20`；后果是**静默停机**（缺列优雅降级跳过，`custom_signals.py:95-97`）而非 400。

**可复跑**

```powershell
# 冲突名：既在 ALLOWED_FIELDS 又是 pack 因子 id
cd C:\work\sourcecode\tick-stock-panel\backend
.\.venv\Scripts\python.exe -c "import sys;sys.path.insert(0,'.');from app.strategy.custom_signals import ALLOWED_FIELDS;from app.factors.registry import all_factors;print(sorted(ALLOWED_FIELDS & {s.id for s in all_factors() if s.kind=='custom'}))"
# 应为 ['boll_lower','boll_upper','ma20','ma60']

# 22 条 enabled
Get-ChildItem 'D:\TSP\data\user_data' -Recurse -Filter *.json | ForEach-Object {
  $t=Get-Content $_.FullName -Raw -Encoding UTF8
  if($t -match '"enabled"\s*:\s*true'){ $_.FullName.Replace('D:\TSP\data\user_data\','') }
}
```

---

## 8. §9 与版本表

| 位置 | 原句 | 新句 |
| --- | --- | --- |
| §9 第 1 行 | 本文件 **v0.4（草案，未冻结）** | 本文件 **v0.4（2026-11-07 已冻结）** |
| §9 `F-A5` 行 | 工作区有未提交实现（`store.py:207-257`），HEAD 无 | 工作区有未提交实现（`store.py` 按符号定位，见 §7.4.2；HEAD 无） |
| 版本表 | 无「冻结」行 | 新增 `| v0.4（冻结） | 2026-11-07 | R4：§7.4 函数级允许面 / §7.9 status 处置 / §7.10 清单先行 + 分级放行 |` |

---

## 9. 冻结四元组（以 `head -c` 可复算）

| 项 | 值 |
| --- | --- |
| 总字节数 | **128,007 B** |
| 总行数 | **1,226 行**（正文 1,225 + footer 1） |
| 正文前缀 | `head -c 127043` → **`717088773de71f2f2ac4fee302729f38fc1fde4d54b68f86415a094fdc7d16bc`** |
| 全文 | **`5bd81a7472f10509dd3b000cabcd7ccaa1c1d8faa3a8edd303120edd58ec5531`** |

复算命令：

```powershell
cd C:\work\sourcecode\tick-stock-panel
$f='docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md'
$b=[IO.File]::ReadAllBytes((Resolve-Path $f))
"bytes = $($b.Length)"                                                    # 128034
"lines = $(([IO.File]::ReadAllLines((Resolve-Path $f),[Text.Encoding]::UTF8)).Count)"   # 1226
"body  = $([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($b[0..127042])).Replace('-','').ToLower())"
"full  = $([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($b)).Replace('-','').ToLower())"
```

bash 等价（Git Bash / WSL）：

```bash
head -c 127043 docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md | sha256sum
sha256sum docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md
wc -c -l docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md
```

**冻结声明**：自本版定稿起（2026-11-07）v0.4 不再改动。此后任何修改须升版 v0.5、重算四元组并新出一份 R5 对照。**审核判据文件在审核过程中被改写，该轮审核绑定作废** —— 本文件即为此规则的执行对象。

---

## 10. 本轮未做与未确证（不圆）

| 项 | 状态 |
| --- | --- |
| 写代码 | 未做。`gate.py`、`alias_of`、`FS03`–`FS07`、`referenced_factor_inventory` 脚本全部未实现 |
| `docs/factors/**`、`docs/research/**`、`backend/**` | 一字未改（只读引用） |
| 7 条信号的误拦后果 | 「静默停机」是按 `custom_signals.py:95-97` 的降级路径推断，**未实跑验证**（需构造缺列帧） |
| N3 的路径分叉 | 代码路径已读，**盘中路径未实跑** |
| `resolve_status` 四分支 | 代码已读，**未跑单测**；`F-A18`–`F-A21` 属实现方与审核方 |
| pack 14 个的逐值对账 | 未跑（沿用 §7.8 的 `F-A13`/`F-A14` 归属） |
| 15 个 `custom_factors` 是否被活配置引用 | 本机扫描 0 命中；`research/**` 的策略定义未逐一展开 |
| `store.py` 那 1 行删除 | 未逐行审，留独立审核按 §7.4.3 判 |
