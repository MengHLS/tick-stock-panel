# 契约修订对照 R5（v0.5 追认版）

- 版本：R5 · 2026-11-07 · 作者：系统架构师
- 对象：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md`（新建，138,729 B / 1,298 行）
- 基准：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md`（v0.4 冻结版，**本轮一字未改**）
- 边界：不写代码、不改因子定义与策略口径、不动 `backend/**`、不动 `docs/factors/**` 与 `docs/research/**`、不提交

---

## 0. 前置事实（本轮开工前后实测，全部可复跑）

| 项 | 实测值 | 命令/落点 |
| --- | --- | --- |
| v0.4 冻结对象 | 128,007 B / 1,226 行 / 正文 `head -c 127043` → `71708877…d16bc` / 全文 `5bd81a74…c5531` | 与冻结四元组逐字相同，**未被就地改写** |
| `store.py` | 19,502 B / 409 行 / 全文 `de77eae6…701199`；`git diff --numstat` = **+187/−1** | mtime 16:33:52，与 §7.4.1 快照同一文件 |
| `store.py` 的 `def load_one` | HEAD `65c6e42f` 命中 **0**；工作区命中 1（`:39`） | `git show HEAD:backend/app/factors/store.py \| grep -c 'def load_one'` → 0 |
| `_STORE.load_one` | 存在（`app/definitions.py:85`） | 故 v0.4 说它「语义不变」在语义上没错，但对象不存在 |
| `store.load_one` 调用点 | 唯一 1 处：`api/factors.py:360`（`create_custom_factor` 的判等预判） | `grep -rn` 全 `backend/app` |
| `api/factors.py` | 24,629 B / 564 行；`git diff --numstat` = **+14/−18** | — |
| `POST /composite` | 已改走 `store.upsert_definition`（`version: 1`、不写 `status`、无试算、不做 `is_unchanged_definition` 预判） | `git diff -U6 -- backend/app/api/factors.py` |
| `POST /custom` | 同上 + 试算前 `is_unchanged_definition` 预判（`:360-362`） | 同上 |
| `custom_factors` 现状 | 15/15 `draft`、**0 个 `active`** | `D:\TSP\data\user_data\custom_factors` |
| `f_class_registry.json` | 91,406 B（16:45，因子工程师正在写 v5）；8 只 F 类均 `draft` | `docs/factors/evidence/` |
| V3 证据可机读 | `F_CLASS_PARITY_20261107.json#/factor_parity/<id>/max_abs_diff`，8 个 `uf_*` 齐 | 这是 §7.11 的证据视图能「只聚合、不重算」的前提 |

**结论：v0.4 的 §7.4.3-1 与 §7.4.2 各有一处事实错误，不是口径错误。**
①`load_one` 被写成「既有函数语义不变」，但它在 HEAD 里不存在（本轮新增）；
②「允许的调用方变更（唯一一处）」只覆盖 `/custom`，而 `/composite` 已走同一入口。两处都属「允许面描述与代码不同步」，按 R5 追认修掉，**不动任何判据语义**。

---

## 1. §7.4.2 允许面补第 10 项：`load_one`（新增只读包装）

**原句**（v0.4 §7.4.3-1 第 1 条，隐含把它当既有函数）：

> 1. `save_one`（`:35`）/`load_one`（`:39`）/`delete_one`（`:44`）语义不变：原子覆盖写；单文件损坏返回 `None` 且不阻断启动。

**新句**（v0.5 §7.4.2 表第 10 行 + §7.4.3-1 补限定）：

> | `load_one(data_dir, factor_id)` | `:39` | **新增只读包装**（v0.5 补） | `return _STORE.load_one(data_dir, factor_id)`，5 行（含 docstring）；无写、无校验、无路径变更；不存在或损坏返回 `None`（与 `load_all` 同隔离口径）。**HEAD `65c6e42f` 中 `def load_one` 命中 0** —— 它是新增符号，不是「既有函数」 |
>
> 1. ……其中 **`load_one` 在 HEAD `65c6e42f` 中不存在**，属**新增只读包装**（已列入 §7.4.2 允许面）；本条对它只约束「语义等同 `_STORE.load_one`」：不得加写、不得加校验、不得改返回契约（`dict | None`）。

**diff 级理由**：

```
+def load_one(data_dir: Path, factor_id: str) -> dict | None:
+    """按 id 读取单个定义; 不存在或损坏返回 None (与 load_all 同隔离口径)。"""
+    return _STORE.load_one(data_dir, factor_id)
```

- 函数体是**单条 `return`**：没有写路径、没有校验分支、没有拼接路径、没有新建目录。它只是把 `_STORE.load_one` 暴露给 API 层 —— 与既有 `load_all`/`save_one`/`delete_one` 三个薄包装同一形状。
- 位置：插在 `save_one` 与 `delete_one` 之间（`:39`），不改动任何既有函数体。
- 必要性：`create_custom_factor` 要做判等预判，必须按 id 单读。没有它就得用 `load_all` 全表扫（O(n) 且把全部文件读进来），在 15 个文件时无感，在 200+ 时是每次保存一遍全盘 I/O —— 而这正是 `F-A5` 想消除的「保存一次重算一次」的邻居问题。
- 不引入新语义：`_STORE.load_one`（`app/definitions.py:85`）本来就有「不存在或损坏 → `None`」的隔离口径，包装沿用。
- **为什么不做「按行号插在表首」**：v0.5 的硬要求是只追加、不改 v0.4 行序（便于逐行 diff 审）。该行追加在表末并标 `（v0.5 补）`，行号列因此非单调（`:39` 出现在 `:310` 之后），属可接受的代价。

---

## 2. §7.4.2 调用方变更由 1 处扩为 2 处：`POST /composite`

**原句**（v0.4）：

> **允许的调用方变更（唯一一处）**：`api/factors.py` 的 `POST /custom` 保存分支改为经 `upsert_definition` 落库，并在试算前用 `is_unchanged_definition` 预判（现 `:360-361`）。API 层不得新增其它 store 调用。

**新句**（v0.5）：

> **允许的调用方变更（2 处；v0.5 由 1 处扩为 2 处）**：①`POST /custom` ……（现 `:360-362`，行号仅参考，同 §7.4.1 口径）；②`POST /composite` 保存分支经 `upsert_definition` 落库（成员校验与环检不变；无试算，不需要预判）。两处共同的两项附带变更：**删除私有助手 `_next_version`**（版本号改由 `upsert_definition` 裁决，是幂等的必要部分）；**响应新增 `unchanged` 布尔**（纯增字段，既有消费方不破）。理由：`F-A5` 原文……**未限定端口**；只让 `/custom` 幂等会留下第二个「保存一次涨一版」的端口，与 §7.9.2 第 2 条直接冲突。

**为什么不回退 `/composite`（三条，逐条可查）**：

1. **F-A5 的原文本身没限定端口**：「同内容二次注册：`version` 不变、响应 `unchanged=true`、盘上文件字节与 mtime 均不变」。它的主语是「注册」，不是「`POST /custom`」。
2. **`/composite` 是同一条缺陷的第二个入口**：改前它同样 `_next_version()` +1 + `save_one` 整份覆盖 → 同内容重提交也涨版本、刷 mtime、让 `materialize_cache`（键含 `spec.version`）的该因子全部失效。留着就是「修了一半」。
3. **与 §7.9.2 第 2 条直接冲突**：§7.9.2 的理由是「`status` 的唯一写入口是 `/status` 端点 + 编辑即回 draft」；`/composite` 若继续硬编码 `status="draft"`，则一次 composite 保存会把线上 `active` 组合因子打回 `draft` —— 与 `/custom` 上刚刚禁掉的行为一模一样。

**两项附带变更，都有边界**：

- `_next_version`（私有助手，`api/factors.py`）**被删除**：它原本的职责（取盘上 `version`+1）现在由 `upsert_definition` 承担，留着就是两套版本裁决。它是**模块私有函数**（下划线命名、唯一调用点在这两个保存分支），不构成对外接口。
- 响应新增 `unchanged`：`{ok, id, version}` → `{ok, id, version, unchanged}`。**纯增字段**，JSON 消费方按名取值不受影响；未逐一核验前端读取路径（见 §6）。

**边界（写进允许面，实现方不得再扩）**：API 层只允许这两个保存分支调用 `upsert_definition`；`/status`、`/update`、`/delete`、`/group` 等分支**不得**改走它（`/status` 的语义见 §7.11.3：不抬版本、不写内容签名）。

---

## 3. §7.4.3-1 表述校正（见 §1 的新句）

只改「`load_one` 是什么」，不改「它不许做什么」。原本的三条禁止（不写、不校验、不改返回契约）在 v0.5 里显式写出，比 v0.4 的「语义不变」更严 —— 因为 v0.4 那句话在 HEAD 上无对象，等于**没有约束力**。

---

## 4. 新增 §7.11：`POST /custom/{id}/status` 的 V3 校验与排期

### 4.1 编号裁定：**不用 `F-A22`，用 `F-A30`–`F-A33`**

派单建议「并入 `F-A18`–`A21` 的 status 端点版，或新开 `F-A22`」。**`F-A22` 已被占用**：v0.4 §7.10.6 的 `F-A22` = 「清单幂等」（同输入连跑两次，除 `generated_at` 外逐字节相同）。若把端点校验叫 `F-A22`，独立审核按编号取判据会取到清单幂等。

故新开 **`F-A30`–`F-A33`**（接 §7.10.6 的 `F-A29`），放在新节 **§7.11.5**，与 §7.9.5（`F-A18`–`F-A21`，`/custom` 的 status 处置）**分节不合并**：`F-A18`–`F-A21` 管「create/update 怎么处置 status」，`F-A30`–`F-A33` 管「谁能把 status 设成 active」，两个对象不同，合并会让一组判据有两种失败原因。

### 4.2 错误码：**`FS07` 不是新码位**

`FS07` 在 v0.4 §7.10.2 的 `code` 枚举里已写成 `FS01`–`FS07`（清单每条引用可带的拒绝码），但 §7.7.5 / §7.8.4 只定义到 `FS06`。§7.11 只是**给已预留的 `FS07` 补定义**，不新增码位，也不改 §7.8.4 的表。

### 4.3 证据视图：为什么不塞进 store、也不塞进台账

- 不能进 store：§7.4.3 第 3 条明禁新增落盘字段（`needs_revalidation` 一类只能进日志）。`v3_passed` 同属此类。
- 不宜进台账：台账写权归因子工程师（团队记忆 2026-11-07 16:30 定），而 V3 的结论是**独立审核**签的（`F_CLASS_AUDIT_20261107.md:19` 判 `F-A3` PASS）。让台账承载「审核结论」会混淆两个写权主体。
- 故设**只读证据视图** `docs/factors/evidence/factor_v3_index.json`，角色三分：**生成 = 系统开发工程师**（纯聚合既有报告的 `max_abs_diff`，不重算、不裁口径）、**签认 = 独立审核工程师**（`signed_by`）、**消费 = 端点**（只读）。
- 成本：该文件不需要任何新测量 —— 8 个 `uf_*` 的 `max_abs_diff` 已在 `F_CLASS_PARITY_20261107.json` 里，生成是机械映射。这是它能排在闸门之前的原因。

### 4.4 排期裁定：**L1 之后、L2 之前**

| 选项 | 判定 | 理由 |
| --- | --- | --- |
| L0/L1 之前就接 | **不必** | L0 只生成清单、L1 只写影子报告，都不按 `active` 放行 → 弱激活不产生放行后果；提前接只是多一次改动窗口 |
| L1 之后、L2 之前 | **采用** | 见下 |
| L2 之后 | **否决** | L2 放行依据 = `allowlist ∪ active`（§7.10.4）。激活不受控 ⇒ 放行凭据可自造 ⇒ 「allowlist 只许缩小、不得手写」形同虚设 |

一句话：**L2 之前 `status` 只是标签，L2 之后 `status` 是凭据。标签可以宽，凭据必须上锁。**

零迁移风险的事实支撑：`custom_factors` 15/15 `draft`、0 `active`；8 只 F 类也是 `draft`。此刻上线校验，**没有任何 `active` 定义会被挡住或降级**。

### 4.5 一处事实校正（不改判据）

§7.7.6 第 1 条说「改状态会抬版本」。实测 `update_factor_status` 走 `target["status"]=...` → `unregister_factor` → `register_definition(target)` → `save_one`：`version` **不变**、`updated_at` 与 mtime 变。「抬版本」只适用于经 `upsert_definition` 的路径（显式带 `status` 的提交）。§7.7.6 的两条硬要求（数值逐位相同、`status` 变更不得改变计算）**不变**。

---

## 5. §9 与版本表

- 版本行：`v0.4` → `v0.5`
- 修订记录：+1 行（`v0.5（追认）`）
- §9 表：+1 行「版本与绑定（v0.5 追认）」
- §9 表后：+「**v0.4 → v0.5 绑定声明**」一段
- footer：按 v0.5 重算（正文 `137598 B` / 行数 `1298` / 正文 sha / v0.4 四元组回指）

---

## 6. 本轮未做与未确证（不圆）

| 项 | 状态 |
| --- | --- |
| 写代码 / 改 `backend/**` | 未做。`gate.py`、`factor_v3_index` 生成脚本、`FS07`、`alias_of` 全部未实现 |
| `F-A30`–`F-A33` | 未跑。属实现方与审核方；本轮只给判据与排期 |
| `update_factor_status` 的幂等改动 | 只是契约要求（§7.11.3），**代码未动**；现实现每次都刷 `updated_at` 与 mtime |
| `unchanged` 响应字段的消费方 | 「纯增字段不破」按 JSON 语义推断，**未逐一核验**前端/脚本读取路径 |
| `store.py` 那 1 行删除 | 仍未逐行审（R4 §10 已登记），留独立审核按 §7.4.3 判 |
| `f_class_registry.json` | 16:45 仍在被因子工程师改（89,781 → 91,406 B 两次）→ 本轮只读引用，未以其为判据 |
| `factor_v3_index.json` | **不存在**。§7.11 只定义它的字段与角色，未落盘任何样例 |

---

## 7. 复现命令（四元组 / 差异 / 分区哈希）

**四元组（bash，Git Bash 可跑）**

```bash
cd /c/work/sourcecode/tick-stock-panel
F=docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md
wc -c -l "$F"                      # 1298 138729
head -c 137598 "$F" | sha256sum    # 082d26fa…af7fae
sha256sum "$F"                     # c7740508…0c4a21a
```

**正文前缀口径**（两版一致，可复算、不自指）：

```python
b = open(F,'rb').read()
cut = b.rfind(b'---\r\n\r\n') + 5      # v0.5: 137598  v0.4: 127043
hashlib.sha256(b[:cut]).hexdigest()    # 正文 sha
```

**v0.4 ↔ v0.5 差异**（本轮全部改动就这 4 行替换 + 76 行新增）：

```bash
git diff --no-index --numstat \
  docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md \
  docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md
# 76  4
git diff --no-index -U0 docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md \
  docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md | grep '^-' | grep -v '^---'
# 仅 4 行：版本行 / 调用方变更 / §7.4.3-1 / footer
```

**未改面分区哈希**（逐块 `sha256` 相等，本机已跑，2026-11-07 16:56）：

| 分区 | 字符数 | 块 sha256（前 16）| 相同 |
| --- | ---: | --- | --- |
| §2–§6 | 32,688 | `161e4f2ad5a95103` | ✅ |
| §7.1 | 2,541 | `a8e88134f60b504c` | ✅ |
| §7.2–7.4.1 | 3,187 | `6a070a795fa7f4da` | ✅ |
| §7.5 | 703 | `a2187060fde3f015` | ✅ |
| §7.6–§7.8 | 15,170 | `dc0643eaea64eba1` | ✅ |
| §7.9 | 2,514 | `1bf204f09a987f64` | ✅ |
| §7.10 | 5,716 | `35f00167279cf5e2` | ✅ |
| §8 | 8,579 | `cb843c0d29cad6e5` | ✅ |

> §7.1 八行公式的 `2,541` 字符与 `a8e88134…` 也是 v0.3 归档 → v0.4 时用过的同一口径（当时报 2,514 的是 §7.9，两处不要混）。

**构建脚本**（可重跑，任一断言不符即不落盘）：`research/arch-build-20261107/build_contract_v05.py`

---

## 9. 冻结四元组（v0.5）与 v0.4 → v0.5 逐条对照

### 9.1 四元组（本机复算，`wc` / `head -c` / `sha256sum` 原生工具）

| 项 | **v0.5（本文件所对应）** | v0.4（**仍为 `F-A5` 绑定对象**） |
| --- | --- | --- |
| 路径 | `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md` | `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md` |
| 总字节 | **138,729 B** | 128,007 B |
| 行数 | **1,298** | 1,226 |
| 正文前缀 | `head -c 137598` → **`082d26fa15f477e4d719b9deb3272bc330b59ae94fcba4f8c0b9ed8342af7fae`** | `head -c 127043` → `717088773de71f2f2ac4fee302729f38fc1fde4d54b68f86415a094fdc7d16bc` |
| 全文 | **`c7740508c358a2c0748aa87fb14c60c8a37f6f721b3f917a7fff7b67c0c4a21a`** | `5bd81a7472f10509dd3b000cabcd7ccaa1c1d8faa3a8edd303120edd58ec5531` |

### 9.2 v0.4 → v0.5 逐条对照

| # | v0.4 位置 | v0.5 处 | 变更性质 | 依据 |
| --- | --- | --- | --- | --- |
| 1 | §7.4.2 表 9 行 | +第 10 行 `load_one`（标 `v0.5 补`）| **允许面扩大** | HEAD `65c6e42f` 无此函数（§0）|
| 2 | §7.4.2「允许的调用方变更（唯一一处）」 | 改「2 处」：+`POST /composite`、+`_next_version` 删除、+`unchanged` 响应 | **允许面扩大** | `F-A5` 未限定端口（§2）|
| 3 | §7.4.3-1 第 1 条 | 同句补「`load_one` 属新增只读包装」+ 三条明禁 | **表述校正，不改判据** | HEAD 实测 0 命中（§1/§3）|
| 4 | §7.9.4 末条「尚未闭环」（仅登记，无编号）| 新增 **§7.11**（7.11.1–7.11.6）：`FS07`、`factor_v3_index.json`、`F-A30`–`F-A33`、排期 L1→L2、§7.7.6 事实校正 | **新增条款** | §7.9.4 原文（§4）|
| 5 | §9 表 20 行 | +1 行「版本与绑定（v0.5 追认）」+ 绑定声明段 | 登记 | 本轮要求 |
| 6 | 版本行 / 修订记录 3 行 / footer | v0.5（+1 行修订记录）| 版本登记 | — |
| 7 | §2–§6、§7.1、§7.2–7.4.1、§7.5、§7.6–§7.8、§7.9、§7.10、§8 | **逐字未变**（分区 sha 相同）| **零变更** | §7 分区哈希表 |

**合计**：替换 4 行（版本行 / §7.4.2 调用方 / §7.4.3-1 / footer）+ 新增 76 行；删除 0 行（除那 4 行的原句）。`git diff --no-index --numstat` → `76  4`。

### 9.3 绑定声明

**`v0.4`（`FACTOR_ENGINE_CONTRACTS_20261107.md`，128,007 B / 1,226 行 / 正文 `head -c 127043` → `71708877…d16bc` / 全文 `5bd81a74…c5531`）仍为 `F-A5` 的绑定对象，其四元组不因本版失效。**

**`v0.5` 只追认允许面（§7.4.2 的 2 项）并新增 §7.11，不改判据语义。**

- `v0.5` 生效后，由独立审核按 `v0.5` **重判 §7.4**（允许面：10 个新增符号 + 1 处既有变更 + 2 处调用方 + 5 条禁止面）。
- `F-A5` 的数值锚点仍取 `v0.4` 四元组；`F-A30`–`F-A33` 自 v0.5 起以 `v0.5` 四元组为锚点。
- 规则不变：**审核判据文件在审核过程中被改写，该轮审核绑定作废**。v0.5 自本文件定稿起不再就地改写，任何改动须升版并重算四元组。
