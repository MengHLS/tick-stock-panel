# -*- coding: utf-8 -*-
"""构建 docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md。

v0.5 = v0.4 逐字节为底 + R5 只追加：
  1) 版本行 v0.4 -> v0.5
  2) 修订记录 +1 行
  3) §7.4.2 允许面 +1 行（load_one，新增只读包装）
  4) §7.4.2 调用方变更 1 处 -> 2 处（+ POST /composite）
  5) §7.4.3-1 表述校正（HEAD 无 load_one）
  6) 新增 §7.11（F-A30-F-A33、FS07、factor_v3_index、排期）
  7) §9 增补 v0.5 绑定行 + 绑定声明段
  8) footer 重算

正文前缀口径（与 v0.4 一致）：cut = 末个 b'---\\r\\n\\r\\n' 的起点 + 5，
即「文件到 footer 前那行 ---\\r\\n 为止」。v0.4 实测 cut = 127043。
"""
import hashlib

SRC = 'docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md'
DST = 'docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md'
EOL = '\r\n'

V04_SHA = '5bd81a7472f10509dd3b000cabcd7ccaa1c1d8faa3a8edd303120edd58ec5531'
V04_SIZE = 128007
V04_LINES = 1226

raw = open(SRC, 'rb').read()
assert hashlib.sha256(raw).hexdigest() == V04_SHA, 'SRC is not frozen v0.4'
assert len(raw) == V04_SIZE
L = raw.decode('utf-8').split(EOL)
assert len(L) == V04_LINES + 1, len(L)

# ---- 定位断言（任何一条不符即不落盘）----
assert L[0] == '# 因子化引擎与生产侧执行器 —— 接口契约 v0.4（2026-11-07）', L[0]
assert L[21].startswith('| v0.4（冻结） | 2026-11-07 | **R4（冻结版定稿）**'), L[21][:60]
assert L[22] == '', repr(L[22])
assert L[769].startswith('| `upsert_definition(data_dir, definition)` | `:310`'), L[769]
assert L[770] == '', repr(L[770])
assert L[773].startswith('**允许的调用方变更（唯一一处）**'), L[773]
assert L[777].startswith('1. `save_one`（`:35`）/`load_one`（`:39`）/`delete_one`'), L[777]
assert L[1104] == '', repr(L[1104])
assert L[1105] == '---', repr(L[1105])
assert L[1106] == '', repr(L[1106])
assert L[1107].startswith('## 8. 改动性质总表'), L[1107]
assert L[1207].startswith('| E1/E2/E3/E4/X1/F 契约 |'), L[1207][:40]
assert L[1208].startswith('| `max_hold_days` 生产侧（X2） |'), L[1208][:40]
assert L[1220] == '', repr(L[1220])
assert L[1221].startswith('**本契约不包含**'), L[1221][:40]
assert L[1225].startswith('本文件正文 sha256：`717088773de7'), L[1225][:60]
assert L[1226] == '', repr(L[1226])

# ---- 文本块 ----
ROW_REV = (
    '| v0.5（追认） | 2026-11-07 | **R5（只追加，不改 v0.4 正文语义）**：①§7.4.2 允许面补 2 项 —— '
    '新增只读包装 `load_one`（HEAD `65c6e42f` 中 `def load_one` 命中 0，v0.4 §7.4.3-1 把它写成「语义不变」是事实错误）；'
    '调用方变更由 1 处扩为 2 处（`POST /custom` + `POST /composite`，并按 `F-A5` 未限定端口说明为何 `/composite` 不回退）；'
    '②新增 **§7.11** `POST /custom/{id}/status` 的 V3 校验（证据视图 `factor_v3_index.json`、`FS07`、`F-A30`–`F-A33`、'
    '排在 L1 之后 L2 之前），收口 §7.9.4 末条「尚未闭环」；③§9 增补 v0.5 绑定行与绑定声明。'
    '**v0.4 仍为 `F-A5` 的绑定对象；v0.5 只追认允许面，不改判据语义**。逐条原句/新句/依据见 '
    '`docs/architecture/CONTRACT_REVISION_R5_20261107.md` | 开发经理 v0.4 验收后派单 + 架构师本机实测（`git diff`、HEAD 符号表）|'
)

ROW_LOAD_ONE = (
    '| `load_one(data_dir, factor_id)` | `:39` | **新增只读包装**（v0.5 补） | '
    '`return _STORE.load_one(data_dir, factor_id)`，5 行（含 docstring）；无写、无校验、无路径变更；'
    '不存在或损坏返回 `None`（与 `load_all` 同隔离口径）。**HEAD `65c6e42f` 中 `def load_one` 命中 0** —— '
    '它是新增符号，不是「既有函数」 |'
)

NEW_774 = (
    '**允许的调用方变更（2 处；v0.5 由 1 处扩为 2 处）**：①`POST /custom` 保存分支经 `upsert_definition` 落库，'
    '并在试算前用 `is_unchanged_definition` 预判（现 `:360-362`，行号仅参考，同 §7.4.1 口径）；'
    '②`POST /composite` 保存分支经 `upsert_definition` 落库（成员校验与环检不变；无试算，不需要预判）。'
    '两处共同的两项附带变更：**删除私有助手 `_next_version`**（版本号改由 `upsert_definition` 裁决，是幂等的必要部分）；'
    '**响应新增 `unchanged` 布尔**（纯增字段，既有消费方不破）。理由：`F-A5` 原文「同内容二次注册：`version` 不变、'
    '响应 `unchanged=true`、盘上文件字节与 mtime 均不变」**未限定端口**；只让 `/custom` 幂等会留下第二个'
    '「保存一次涨一版」的端口，与 §7.9.2 第 2 条直接冲突。API 层不得新增其它 store 调用。'
)

NEW_778 = (
    '1. `save_one`（`:35`）/`load_one`（`:39`）/`delete_one`（`:44`）语义不变：原子覆盖写；单文件损坏返回 `None` 且不阻断启动。'
    '其中 **`load_one` 在 HEAD `65c6e42f` 中不存在**，属**新增只读包装**（已列入 §7.4.2 允许面）；'
    '本条对它只约束「语义等同 `_STORE.load_one`」：不得加写、不得加校验、不得改返回契约（`dict | None`）。'
)

SEC_711 = r'''### 7.11 `POST /custom/{id}/status` 的 V3 校验与排期（v0.5 追认；收口 §7.9.4 末条「尚未闭环」）

行号口径同 §7.4.1：对 `api/factors.py` 与 `store.py` 一律按符号引用，行号仅作参考。

#### 7.11.1 问题（事实，2026-11-07 16:42–16:45 本机复核）

- 端点 `POST /api/factors/custom/{factor_id}/status`（`update_factor_status`）接受 `draft|active|watch|retired` 四态（`FactorStatusRequest.status` 正则），**只做存在性检查（404）与 `register_definition` 的 schema 校验，不校验任何 V3 证据**：任一 store 定义都能被直接标成 `active`。
- 因此 §7.5-5「禁止给未通过 V3 的因子标 `active`」仍是**人工纪律**，不是代码约束；§7.7 的闸门保证「标了 `active` 之后谁还能用」，**不保证「谁能标 `active`」**。
- 后果不是理论问题：§7.10.4 的 **L2 放行依据 = `allowlist ∪ active`**。L2 一旦开启，`status=active` 本身就是**放行凭据**；激活不受控等于把门锁装在内侧 —— 调一次 status 端点即可绕过「allowlist 只许缩小」。
- 现状规模（本机实测）：`D:\TSP\data\user_data\custom_factors` **15/15 全为 `draft`、0 个 `active`**；`docs/factors/evidence/f_class_registry.json` 的 8 只 F 类同为 `draft`。故本节校验**今天上线零迁移风险**（没有 `active` 会被挡住或降级）。

#### 7.11.2 裁定：V3 是激活的唯一附加条件，证据必须是落盘物、不进 store

- **允许激活当且仅当**：`v3_status = pass` ∧ `max_abs_diff < 1e-12`（沿用 §7.6 `F-A3` 容差；**不是** `0`，也不是某次实测的 1 ULP）∧ `signed_by` 非空 ∧ 未过期。其余一律 `400 FS07`，盘上 `status` 不变。
- **不得新增落盘字段**：§7.4.3 第 3 条禁止给 store JSON 加字段，`v3_passed` 一类标记**不得**写进 `user_data/custom_factors/*.json`。证据只能来自只读落盘物。
- **证据视图（唯一）**：`docs/factors/evidence/factor_v3_index.json`，`schema = "factor_v3_index/1"`。字段级定义（顶层 4 + `records[]` 8）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema` | str | 固定 `factor_v3_index/1`；不匹配即 fail-closed |
| `generated_at` | ISO8601 | 生成时间 |
| `sources[]` | array | `{path, sha256, covers[]}`：每条来源报告（如 `F_CLASS_PARITY_20261107.json`）的路径、哈希、覆盖的 id |
| `records[]` | array | 逐因子记录，主键 `factor_id` |
| `records[].factor_id` | str | canonical id（`uf_*` / `cf_*`）|
| `records[].v3_status` | enum | `pass` / `fail` / `missing` |
| `records[].criterion` | str | 固定 `F-A3` |
| `records[].max_abs_diff` | float/null | 实测值；`v3_status=pass` 时必须非空且 `< 1e-12` |
| `records[].tolerance` | float | 固定 `1e-12`（不得写成 0，也不得写成 1.11e-16）|
| `records[].report_path` / `report_sha256` | str | 原始报告路径与字节哈希 |
| `records[].evidence` | str | `file:jsonpointer`，如 `docs/factors/evidence/F_CLASS_PARITY_20261107.json:#/factor_parity/uf_vol60` |
| `records[].signed_by` / `signed_at` / `expires_on` | str/null | 签认人（独立审核）、签认时间、失效日；`expires_on` 为空表示不过期 |

- **生成与签认分离**（角色分工同 §7.10.2）：生成 = **系统开发工程师**（纯聚合：从既有报告的 `factor_parity[].max_abs_diff` 取数，**不重算、不裁口径**）；签认 `signed_by` = **独立审核工程师**（`F-A3` 的 PASS 结论已在 `research/independent-review-20261107/F_CLASS_AUDIT_20261107.md`）；消费 = 端点（只读）。**因子工程师不经手该文件**（其写权在台账）。
- **fail-closed 三条**：索引缺失或不可解析 → 一律 `FS07`（不得因「读不到证据」而放行）；`v3_status=missing` 与 `fail` 同待遇；`expires_on` 过期视同 `missing`。
- **只读与缓存**：启动时读一次，索引 `sha256` 变化即重载；请求路径**不得**重新聚合。

#### 7.11.3 降级不设闸、激活幂等（方向性）

- `draft`/`watch`/`retired` 任意互转、以及从 `active` 降到任一态：**不看 V3，一律 200**。激活是唯一需要证据的方向；给降级加闸会在事故时挡住止损动作。
- **幂等**：`status` 已是目标态时重复提交 → `200`、响应 `unchanged=true`、**不写盘**（文件字节与 mtime 均不变）。现实现每次都 `unregister_factor` → `register_definition` → `save_one`，会刷 `updated_at` 与 mtime；本条与该端点的 V3 校验**并入同一处改动**，不单独排期。

#### 7.11.4 排期：**L1 之后、L2 之前**（L2 的进入条件追加一条）

- **不能排在 L2 之后**：L2 的放行凭据是 `allowlist ∪ active`（§7.10.4）。激活不受控 = 凭据可自造，与「allowlist 只许缩小、不得手写」直接冲突。
- **不必排在 L0/L1 之前**：L0 只生成清单、L1 只写影子报告，都不按 `active` 放行，此时弱激活**不产生放行后果**；提前接只是多一次无收益的改动窗口。
- **与清单的关系**：互不依赖（清单管「谁被引用」，本节管「谁能标 `active`」），可并行开发；**但 L2 启动前两者都必须通过**。
- 本条为 §7.10.4 `L2` 行的**追加**进入条件（不改该表原文）：`L2 进入条件 = L1 过 + allowlist 已签认 + F-A30–F-A32 通过`。

#### 7.11.5 判据（续 §7.6 编号，接 §7.10.6 的 `F-A29`）

| # | 判据 | 度量 |
| --- | --- | --- |
| F-A30 | 未过 V3 不得激活 | 对 `v3_status ∈ {fail, missing}` 或索引无记录的 id 提交 `{status:"active"}`：`400`、`detail.code="FS07"`、盘上 `status` 不变、文件字节与 mtime 均不变 |
| F-A31 | 降级与三态不受限 | `draft`/`watch`/`retired` 任意互转、`active`→任一态：`200`；把索引整体删掉后重跑本行仍 `200`（降级不因证据缺失被挡）|
| F-A32 | 索引 fail-closed | 删除索引后重试 `F-A30` 第一例：仍 `400 FS07`；启动日志含 1 条 `v3_index_unavailable`；损坏 JSON 与缺失同待遇 |
| F-A33 | 排期可验证 | L2 生效期在 `active` 定义上重放 `F-A30` 第一例：仍 `400`；L2 启动配置若缺 `F-A30`–`F-A32` 的通过记录，`gate` 拒绝以 L2 启动 |

**错误码**：`FS07` = 「未通过 V3 对账即要求标 `active`」，`400`，`detail` 含 `factor_id` / `requested_status` / `v3_status` / `evidence`。`FS07` 在 §7.10.2 的 `code` 枚举里已预留（`FS01`–`FS07`），本节只是给它定义，不新增码位。

**范围**：仅 store 定义（`kind=custom|composite`）。pack 14 个与 `kind=virtual` 无盘上定义，本端点对其仍返回 `404`（现状不变），其准入按 §7.8.4 走。

#### 7.11.6 一处事实校正（不改判据）

- §7.7.6 第 1 条说「改状态会抬版本」。实测：`update_factor_status` 走 `target["status"]=...` → `unregister_factor` → `register_definition(target)` → `save_one`，`version` **不变**、`updated_at` 与 mtime 变；该路径**不触发** `materialize_cache` 键变化（键含 `spec.version`）。「抬版本」只适用于经 `upsert_definition` 的路径（显式带 `status` 的提交）。§7.7.6 的两条硬要求不变：数值逐位相同、`status` 变更不得改变计算结果。'''.split('\n')

ROW_S9 = (
    '| **版本与绑定（v0.5 追认）** | 现行 **v0.5**（本文件）：v0.4 = `FACTOR_ENGINE_CONTRACTS_20261107.md`'
    '（128,007 B / 1,226 行 / 正文 `head -c 127043` → `71708877…d16bc` / 全文 `5bd81a74…c5531`），'
    '**仍是 `F-A5`（及 §7.9 / §7.10 判据）的绑定对象**；v0.5 只追认 §7.4.2 允许面（+`load_one`、+`POST /composite` 调用方）'
    '并新增 §7.11，**不改任何判据语义** |'
)

DECL_S9 = (
    '**v0.4 → v0.5 绑定声明**：`v0.4`（`FACTOR_ENGINE_CONTRACTS_20261107.md`，128,007 B / 全文 `5bd81a74…c5531`）'
    '仍为 `F-A5` 的**绑定对象**，其四元组不因本版失效；`v0.5`（本文件）**只追认允许面**（§7.4.2 的 2 项）'
    '并新增 §7.11，**不改判据语义**。`v0.5` 生效后由独立审核按 `v0.5` 重判 §7.4（允许面）；'
    '`F-A5` 的数字锚点仍取 `v0.4` 四元组。逐条对照见 `docs/architecture/CONTRACT_REVISION_R5_20261107.md` §9。'
)

# ---- 应用（自下而上，索引不漂移）----
L2 = list(L)
L2[0] = L2[0].replace('v0.4（2026-11-07）', 'v0.5（2026-11-07）')
assert L2[0].endswith('v0.5（2026-11-07）'), L2[0]

edits = [
    (1221, [DECL_S9, '']),
    (1208, [ROW_S9]),
    (1105, ['---', ''] + SEC_711 + ['']),
    (770, [ROW_LOAD_ONE]),
    (22, [ROW_REV]),
]
L2[773] = NEW_774
L2[777] = NEW_778
for idx, payload in edits:
    L2[idx:idx] = payload

# ---- footer 重算 ----
tmp = EOL.join(L2).encode('utf-8')
cut = tmp.rfind(b'---\r\n\r\n') + 5
assert cut > 0
body_sha = hashlib.sha256(tmp[:cut]).hexdigest()
lines_final = EOL.join(L2).count(EOL)

FOOTER = (
    '本文件正文 sha256：`%s`（校验：`head -c %d "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md" | sha256sum`）'
    '· 正文 `%d B` · 行数 `%d` · 版本 **v0.5（2026-11-07 追认，未冻结）**· 冻结四元组（size / lines / body-prefix / full sha）'
    '见 `docs/architecture/CONTRACT_REVISION_R5_20261107.md` §9（不写进正文，避免自指）· 生成 2026-11-07 v0.5 = v0.4 逐字节为底 +'
    ' R5 只追加：§7.4.2 允许面 +2 项（`load_one`、`POST /composite` 调用方）/ 新增 §7.11 `status` 端点的 V3 校验'
    '（`FS07`、`F-A30`–`F-A33`、`factor_v3_index.json`，排在 L1 之后 L2 之前）/ §9 增补绑定行 ·'
    ' **v0.4 = `FACTOR_ENGINE_CONTRACTS_20261107.md`（128,007 B / 1,226 行 / 正文 `head -c 127043` → `71708877…d16bc` /'
    ' 全文 `5bd81a74…c5531`）仍为 `F-A5` 的绑定对象；v0.5 只追认允许面，不改判据语义** ·'
    ' v0.3 冻结态（89,833 B / 914 行 / 全文 `5eb97724…565903`）逐字节归档于'
    ' `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`'
) % (body_sha, cut, cut, lines_final)

assert L2[-2].startswith('本文件正文 sha256：`'), L2[-2][:40]
L2[-2] = FOOTER

out = EOL.join(L2).encode('utf-8')
assert out.count(b'\r\n') == lines_final, (out.count(b'\r\n'), lines_final)
final_cut = out.rfind(b'---\r\n\r\n') + 5
assert final_cut == cut, (final_cut, cut)
assert hashlib.sha256(out[:cut]).hexdigest() == body_sha

# 未改面逐字校验
def block(text, a, b):
    return text[text.index(a):text.index(b)]

old_text = raw.decode('utf-8')
new_text = out.decode('utf-8')
assert block(old_text, '### 7.1 ', '### 7.2 ') == block(new_text, '### 7.1 ', '### 7.2 '), '7.1 changed'
assert block(old_text, '### 7.5 ', '### 7.6 ') == block(new_text, '### 7.5 ', '### 7.6 '), '7.5 changed'
assert block(old_text, '### 7.9 ', '### 7.10 ') == block(new_text, '### 7.9 ', '### 7.10 '), '7.9 changed'
assert block(old_text, '### 7.10 ', '## 8. ') == block(new_text, '### 7.10 ', '### 7.11 '), '7.10 changed'
assert block(old_text, '## 2. E3', '## 7. F 类') == block(new_text, '## 2. E3', '## 7. F 类'), '2-6 changed'
assert block(old_text, '## 8. ', '## 9. ') == block(new_text, '## 8. ', '## 9. '), '8 changed'

open(DST, 'wb').write(out)

print('OK ->', DST)
print('size', len(out))
print('lines', out.count(b'\r\n'))
print('cut', cut)
print('body', body_sha)
print('full', hashlib.sha256(out).hexdigest())
