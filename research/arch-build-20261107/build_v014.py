# -*- coding: utf-8 -*-
"""v0.14 构建脚本（R14：三处判据可判定性收口）—— 可复跑。

底本 = docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.13.md（逐字节读入，带守卫断言）
输出 = docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.14.md

做法：底本 CRLF -> LF 工作副本；全部改动在 LF 面上做（每处断言命中次数 == 1，0 或 >1 即中止、不写文件）；
收尾整体 LF -> CRLF，再按本版正文字节重算 footer。不提交、不改 backend/**、不改 docs/factors/**。
"""
import difflib
import hashlib

SRC = 'docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.13.md'
DST = 'docs/architecture/FACTOR_ENGINE_CONTRACTS_20261108_v0.14.md'

CR = chr(13)
LF = chr(10)
CRLF = CR + LF

raw = open(SRC, 'rb').read()

# ---------- 底本守卫（三个常量任一不符即中止，不写文件） ----------
BASE_SHA = 'a1374eb5cc526e1117145076e9faaa556d4abe4c93962dbdfdd67cf35d5ffd82'
BASE_BYTES = 277296
BASE_BODY_SHA = '73901fd0faff9711c3ad5a00db2214c67b4306db98dc37591b1fc3519cd2031a'
BASE_BODY_BYTES = 275854
assert hashlib.sha256(raw).hexdigest() == BASE_SHA, '底本全文 sha256 不符，中止'
assert len(raw) == BASE_BYTES, '底本字节数不符：' + str(len(raw))
_bi = raw.rfind('本文件正文 sha256'.encode())
assert hashlib.sha256(raw[:_bi]).hexdigest() == BASE_BODY_SHA, '底本正文 sha256 不符，中止'
assert len(raw[:_bi]) == BASE_BODY_BYTES, '底本正文字节数不符'
assert raw.count((CR + LF).encode()) == raw.count(LF.encode()), '底本必须全 CRLF'

t = raw.decode('utf-8').replace(CR + LF, LF)
MARK = '本文件正文 sha256：'
_i = t.rfind(MARK)
assert _i > 0
t = t[:_i]

BASE_LF = t
EDITS = []


def sub(old, new, tag):
    """整串替换：命中次数必须 == 1。"""
    global t
    n = t.count(old)
    assert n == 1, '[' + tag + '] 命中 ' + str(n) + ' 次，中止'
    t = t.replace(old, new, 1)
    EDITS.append(tag)


def sub_line(prefix, new, tag):
    """整行前缀定位：命中行数必须 == 1；新句必须是单行。"""
    global t
    lines = t.split(LF)
    idx = [i for i, ln in enumerate(lines) if ln.startswith(prefix)]
    assert len(idx) == 1, '[' + tag + '] 行前缀命中 ' + str(len(idx)) + ' 行，中止'
    assert new.count(LF) == 0, '[' + tag + '] 新句必须是单行'
    lines[idx[0]] = new
    t = LF.join(lines)
    EDITS.append(tag)


# ================= R14-1 H1 =================
sub('# 因子化引擎与生产侧执行器 —— 接口契约 v0.13（2026-11-08）',
    '# 因子化引擎与生产侧执行器 —— 接口契约 v0.14（2026-11-08）',
    'R14-1 H1')

# ================= R14-4a §7.8.4 判定矩阵行 =================
sub_line('| 同一策略内 alias 与 canonical 并存 |',
         '| 同一策略内 alias 与 canonical 并存 | **拒绝 `FS04`**（载体见 §7.16.4：`detail.dual_ids`） '
         '| **拒绝 `FS04`**（同） | 允许；**不产生 `dual_id` 标记**（`GateReport` 六字段无此槽位，'
         'v0.14 裁定 (a)，见本节载体段） |',
         'R14-4a §7.8.4-matrix')

# ================= R14-4b §7.8.4 错误码表行 =================
sub_line('| `FS04` | 同一策略混用同口径两个 id |',
         '| `FS04` | 同一策略混用同口径两个 id | 400；`detail.dual_ids` 按输入顺序列全部并存 id'
         '（`detail` 共 8 键，§7.16.4）；`table_row` 为 `null`（§7.15.1 尚无机器可读副本） |',
         'R14-4b §7.8.4-errcode')

# ================= R14-4c §7.8.4 载体裁定段 =================
KEY7 = '`code` / `mode` / `submitted_id` / `resolved_id` / `canonical_id` / `table_row` / `message`'
CARRIER_784 = (
    '**`FS04` 的载体（v0.14 裁定 (a)：全文唯一读法）**：`FS04` 只经 `GateError.detail` 承载 —— '
    '§7.16.4 的固定 7 键（' + KEY7 + '）+ 唯一附加键 `dual_ids`（数组，按输入顺序列全部并存 id）。'
    '`GateReport` **不加字段**：六字段按 §7.7.2 逐字固定，加第七字段等于改判据面，**本版否决 (b)**。'
    '由此派生一条空值语义：`diagnostic` 模式虽然放行 `FS04`，但**不产生任何 `dual_id` 标记** —— '
    '该模式不抛 `GateError`（没有 `detail` 可带），`GateReport` 又无槽位，标记无处可落；'
    '这是显式声明，不是遗漏。' + LF * 2 +
    '**同类缺口登记（不在本版裁定）**：`deprecated_alias_used` / `reference_missing` / '
    '`ambiguous_canonical` 三类「标 X」同样在 `GateReport` 六字段里没有槽位，而 `F-A42-3` 明文要求 '
    '`research` 报告含 `deprecated_alias_used` —— 与 `FS04` 是同一类缺口。`F-A42` 已冻结，本版'
    '**一个字节不动**，故只登记、不裁（`CONTRACT-GAP 4`）；在任何后续版本裁定之前，**不得**据此判实现'
    '「不合格」，也不得据此判本契约自相矛盾。' + LF * 2
)
sub('**硬规则：不得用 `stability` 反推 `active`。**',
    CARRIER_784 + '**硬规则：不得用 `stability` 反推 `active`。**',
    'R14-4c §7.8.4-carrier')

# ================= R14-5 §7.16.4 载体条 =================
CARRIER_7164 = (
    '- **`dual_ids` 只在 `GateError.detail` 上（v0.14 裁定 (a)）**：`GateReport` 六字段（§7.7.2）里'
    '没有 `dual_id` 槽位，本版不新增；「本次判定涉及双 id」这一事实的唯一载体是 '
    '`GateError.detail.dual_ids`。`diagnostic` 模式不抛 `GateError`，故该模式下**无任何 `dual_id` '
    '标记**（与 §7.8.4 载体裁定同一条，两处不许有第二种读法）。' + LF
)
sub('- 状态码 **400**（与 §7.8.4 / §7.7.5 一致，不新造 422、不用 409）。',
    CARRIER_7164 + '- 状态码 **400**（与 §7.8.4 / §7.7.5 一致，不新造 422、不用 409）。',
    'R14-5 §7.16.4-carrier')

# ================= R14-6 §7.16.6 表行 =================
sub('**400 `FS04`** | 允许，标 `dual_id=true` | 同上 |',
    '**400 `FS04`** | 允许；**不标 `dual_id`**（`GateReport` 无槽位，见 §7.16.4 载体条） | 同上 |',
    'R14-6 §7.16.6-row')

# ================= R14-7 §7.17.4 C2 =================
sub('`diagnostic` → 允许并标 `dual_id=true`。',
    '`diagnostic` → 不抛 `GateError`、且**不产生 `dual_id` 标记**（`GateReport` 六字段无槽位，'
    '见 §7.8.4 载体裁定与 §7.16.4 载体条）。',
    'R14-7 C2')

# ================= R14-2 §7.17.2 零改动句 =================
sub_line('- **位置参数顺序与全部既有 keyword-only 参数的名字/缺省值一字不改**',
         '- **位置参数顺序与全部既有 keyword-only 参数的名字/缺省值一字不改** ⇒ 既有**调用点**零改动'
         '（调用点集合按验收当时 `grep -rn "assert_factors_usable" backend/` 的结果逐个核，本文不写死个数）。'
         '**测试文件不是「零改动」对象（v0.14 更正）**：§7.17.4 的 `C3` / `C4` 要求把旧的 `ValueError` / '
         '`NotImplementedError` 期望换成 `GateError` + `FS09` / `FS06`，实现方按 C 执行**必然**要动测试；'
         '因此对 `backend/tests/test_factor_gate.py` 的要求改为「**既有断言的判定强度不得放宽**」，'
         '机械判法见 `F-A45-2`（原「一个字不改」措辞不可判，已废止）。',
         'R14-2 §7.17.2-zerochange')

# ================= R14-3 F-A45-2 =================
FA452 = (
    '| `F-A45-2` | 既有断言的判定强度不放宽（**取代**原「现有测试零改动 / 一个字不改」） | '
    '四项**全过**才算过；基线锚 = `HEAD:backend/tests/test_factor_gate.py`（提交 `286c1c86` / '
    '24,708 B / sha256 `fc675edfecf9442f5dcdffc9a47bf50d0f9d137cb019bd153fd4e72e131dda57`）：'
    '①**删除的断言行 == 0**（`git diff -U0` 中 `^-` 开头且匹配 `^[ \\t]+assert ` 的行数）；'
    '②**断言条数不减**（`grep -cE \'^[ \\t]+assert \'` ≥ **129**）；'
    '③**无 `skip` / `xfail`**（`@pytest.mark.skip` 与 `@pytest.mark.xfail` 命中 **0 / 0**；'
    '`@pytest.mark.skipif` 只许用于「本机缺外部数据目录」这一前置、`reason` 必含 `本机无`，'
    '基线 **2** 条，新增须逐条列出）；'
    '④**无 `==` → `>=`**（`assert` 行内 `>=` 出现次数 == **1**，且不得由 `==` 改写而来）。'
    '允许的差异**只有一类**：把旧异常类型替换为 §7.17.4 指定的新类型'
    '（`pytest.raises(ValueError)` / `pytest.raises(NotImplementedError)` → '
    '`pytest.raises(gate.GateError)`），**每处逐条列出**（文件:行 + 旧类型 → 新类型 + 新增断言）；'
    '`gate.load_live_config_allowlist` 的 `ValueError` **不在** `C1` 出口范围'
    '（它不经 `assert_factors_usable`），保持原样 |'
)
sub_line('| `F-A45-2` | 现有测试零改动 |', FA452, 'R14-3 F-A45-2')

# ================= R14-8 F-A47-1 =================
FA471 = (
    '| `F-A47-1` | `FS04` 走 400（**接线后生效**；接线前按 `F-A47-1a`，见 §7.17.8） | '
    '同一策略同时提交 `vol60` + `uf_vol60`，`production` 与 `research` 各一次 → HTTP **400**、'
    '`detail.code=="FS04"`、`detail` 键集 **逐键按序等于** §7.16.4 固定 7 键 + 唯一附加键 '
    '`dual_ids`（共 **8**）、`detail.dual_ids == ["vol60","uf_vol60"]`（输入顺序）、'
    '`detail.table_row is None`；`diagnostic` → 200、`ok=True`、`GateReport` 仍六字段、'
    '**不产生任何 `dual_id` 标记**（§7.8.4 载体裁定） |'
)
sub_line('| `F-A47-1` | `FS04` 走 400 |', FA471, 'R14-8 F-A47-1')

# ================= R14-9 F-A47-3 =================
FA473 = (
    '| `F-A47-3` | 不洗错（**接线后生效**；接线前按 `F-A47-3a`，见 §7.17.8） | '
    '往闸门内注入一个 `RuntimeError` → HTTP **500**（不是 400）；只有 `GateError` 被映射成 400 |'
)
sub_line('| `F-A47-3` | 不洗错 |', FA473, 'R14-9 F-A47-3')

# ================= R14-10 新增 §7.17.8 =================
SEC7178 = (
    '#### 7.17.8 「接线后生效」与接线前的替代判据（v0.14 新增；`F-A47-1a` / `F-A47-3a`）' + LF * 2 +
    '`F-A47-1` 与 `F-A47-3` 的度量是 **HTTP 状态码**，而 `backend/app/**` 里目前**没有** '
    '`GateError → 400` 的映射：`grep -rn "assert_factors_usable" backend/app --include=*.py` 只命中 '
    '`factors/gate.py` 的 `def`（`:560`）与两行注释（`:5` / `:27`），**调用方 0**；'
    '`grep -rn "except GateError" backend/app --include=*.py` **0 命中**；`main.py` 的 6 个 '
    '`exception_handler` 里没有 `GateError`（`WorkBusyError` / `HeavyJobLimitTimeoutError` / '
    '`CapabilityDenied` / `DataSyncDisabledError` / `DailyIntegrityError` / `ProviderRequestError`）。'
    '因此这两条在接线前**无论怎么做都不可测** —— 这不是实现缺陷，是度量对象还不存在。' + LF * 2 +
    '处理办法：两条各标「接线后生效」，并各给一条**只依赖闸门层**的替代判据，编号带 `a` 后缀'
    '（`F-A47-1a` / `F-A47-3a`），与母条同源、不新增裁定、不改任何阈值。' + LF * 2 +
    '| # | 生效时点 | 判据 | 度量（可机械判） |' + LF +
    '| --- | --- | --- | --- |' + LF +
    '| `F-A47-1a` | **接线前即可判** | 闸门层 `FS04` 的 `detail` 正确 | '
    '用 `MappingFacts` 注入两个 id（`vol60`：`registered=True` / `kind="custom"` / `status="active"` / '
    '`alias_of="uf_vol60"` / `lang="dsl"` / `strategy_usable=False`；`uf_vol60`：同前但 '
    '`alias_of=None` / `strategy_usable=True`），`production` 与 `research` 各调一次 '
    '`assert_factors_usable(["vol60","uf_vol60"], mode, facts=…)` → 均抛 `GateError`、`code=="FS04"`、'
    '`list(detail)` 逐键按序 == 固定 7 键 + `dual_ids`（共 8）、`detail["dual_ids"] == '
    '["vol60","uf_vol60"]`、`detail["table_row"] is None`；`diagnostic` → 不抛、`report.ok is True`、'
    '`len(dataclasses.fields(GateReport)) == 6` |' + LF +
    '| `F-A47-3a` | **接线前即可判** | 闸门层不洗错、映射层尚不存在 | '
    '①`grep -cE "except (Exception|BaseException)" backend/app/factors/gate.py` == **0**；'
    '②注入一个 `facts` 源抛 `RuntimeError`（`class Boom: def facts(self, fid): raise RuntimeError("boom")`），'
    '`assert_factors_usable(["x"], "production", facts=Boom())` → 逃出的异常**类型仍是 `RuntimeError`**'
    '（不是 `GateError`，即闸门没把它包成 400 的形状）；③`grep -rc "except GateError" backend/app '
    '--include=*.py` 全 **0** —— 映射层未接线，故 400 / 500 的分派在接线前**不可测**，'
    '这一条是**事实登记**，不是对实现的要求 |' + LF * 2 +
    '**实测锚（2026-11-08 02:2x，`backend/.venv/Scripts/python.exe`，可复跑 '
    '`research/arch-build-20261107/verify_v014.py` C 段）**：`F-A47-1a` 的 `production` 与 `research` '
    '两次调用各得 `FS04` / 8 键 `code,mode,submitted_id,resolved_id,canonical_id,table_row,message,'
    'dual_ids` / `["vol60","uf_vol60"]` / `table_row=None`；`diagnostic` 得 `ok=True`、字段名 '
    '`ok,blocked,non_active,unknown,mode,historical_only`（六）；`F-A47-3a` ②得 `RuntimeError: boom`'
    '（原样逃出，未被包成 `GateError`）。' + LF * 2 +
    '**「接线后生效」的含义（判分规则，避免重复计分）**：只有当 API 层 `GateError → 400` 映射存在、'
    '且 `backend/app/**` 至少有一个真实调用方时，母条才可判。在那之前，验收记录只写 '
    '`F-A47-1a` / `F-A47-3a` 的结论，**不得**把母条记为「部分不可验」—— 母条的度量对象尚不存在，'
    '记「未生效」即可；同一个未接线状态被计分两次，是判据设计的缺陷，不是实现的缺陷。' + LF * 2
)
sub('## 8. 改动性质总表（改引擎 / 新增模块 / 现有已够）',
    SEC7178 + '## 8. 改动性质总表（改引擎 / 新增模块 / 现有已够）',
    'R14-10 §7.17.8')

# ================= R14-11 新增 §14 =================
SEC14 = '''## 14. 本版改动说明（v0.14 / R14：三处判据可判定性收口）

**本版 = v0.13 逐字节为底 + 下列 12 处正文改动 + 新增本节（合计 13 处）+ footer 由本版正文字节重算。** 开发经理 2026-11-08 01:4x 派单（R14）三项：①`F-A45-2` 与 `C3`/`C4` 互斥；②`FS04` 无载体；③`F-A47-1`/`F-A47-3` 接线前不可验。**不新增准入裁定、不改任何阈值、不动 `§7.1` 一个字节、`F-A1`–`F-A42` 逐行未动。**

| # | 位置（v0.13 行号） | 原句 | 新句（要点） | 可机械判的验收形态 |
| --- | --- | --- | --- | --- |
| R14-1 | H1 `:1` | `… 接口契约 v0.13（2026-11-08）` | `… 接口契约 v0.14（2026-11-08）` | `head -1` 等于新标题 |
| R14-2 | §7.17.2 `:1769` | 「… ⇒ 既有调用点与 `backend/tests/test_factor_gate.py` **零改动**」 | 签名不变 ⇒ **调用点**零改动；测试文件**不是零改动对象**，改为「判定强度不得放宽」（原「一个字不改」不可判，已废止） | `F-A45-2` 四项全过 |
| R14-3 | `F-A45-2` `:1847` | 「现有测试零改动 / 一个字不改，全部通过」 | 「既有断言的判定强度不放宽」：删除断言行 == 0、条数 ≥ 129、无 `skip`/`xfail`、`assert` 行内 `>=` 不增；允许把旧异常类型换成 §7.17.4 指定的新类型，逐条列出 | 见本节「`F-A45-2` 四项判法」 |
| R14-4 | §7.8.4 判定矩阵 `:1020` | 「允许（标 `dual_id`）」 | 「允许；**不产生** `dual_id` 标记」（六字段无槽位，裁定 (a)） | `F-A47-1a` 的 `diagnostic` 分支 |
| R14-5 | §7.8.4 错误码表 `:1027` | 「`detail` 含两个 id 与**台账行号**」 | 「`detail.dual_ids` 按输入顺序、共 8 键；`table_row` 为 `null`」 | `F-A47-1a` 的 `list(detail)` 与 `detail["table_row"]` |
| R14-6 | §7.8.4 错误码表后（`硬规则` 段之前） | （无） | 新增「`FS04` 的载体」裁定段：只走 `GateError.detail`，`GateReport` 不加第七字段；`diagnostic` 不产生标记；同类缺口（`deprecated_alias_used` 等）只登记不裁 | `verify_v014.py` D 段 |
| R14-7 | §7.16.4 `- 状态码 **400**` 之前 `:1662` | （无） | 新增载体条：`dual_ids` 只在 `GateError.detail` 上，`GateReport` 无槽位；并写明「两处不许有第二种读法」 | 同上 |
| R14-8 | §7.16.6 表 `:1681` | 「允许，标 `dual_id=true`」 | 「允许；**不标** `dual_id`」 | `F-A47-1a` 的 `diagnostic` 分支 |
| R14-9 | §7.17.4 `C2` `:1809` | 「`diagnostic` → 允许并标 `dual_id=true`」 | 「不抛 `GateError`、且不产生 `dual_id` 标记」 | 同上 |
| R14-10 | `F-A47-1` `:1862` | 度量含「`diagnostic` → 200 且标 `dual_id=true`」 | 标「**接线后生效**」+ 键集改为「固定 7 键 + `dual_ids` 逐键按序共 8」+ `diagnostic` 不标 | `F-A47-1a`（接线前）/ 母条（接线后） |
| R14-11 | `F-A47-3` `:1864` | 无生效时点标记 | 标「**接线后生效**」，接线前按 `F-A47-3a` | `F-A47-3a` |
| R14-12 | 新增 `§7.17.8`（`## 8.` 前） | （无） | `F-A47-1a` / `F-A47-3a` 两条接线前判据 + 接线前事实锚（app 下调用方 0、`except GateError` 0、`exception_handler` 无 `GateError`）+ 不重复计分规则 | `verify_v014.py` C 段全 PASS |

**三项裁定与理由（逐项）**

1. **`F-A45-2` 必须废，不是收紧措辞**：它与 `C3`/`C4` **逻辑互斥** —— `C4` 要求把 `mode` 域外的 `ValueError` 换成 `FS09`（`GateError`），而当时唯一的域外 `mode` 用例正押着 `pytest.raises(ValueError)`；实现方按 `C` 做就对不上 `F-A45-2`，按 `F-A45-2` 做就违反 `C`。两条判据不能同时成立时，**判据本身作废**，不能要求实现方二选一。替代形态的四个量都可从 `git diff` 与 `grep` 直接算出，不依赖人工判断。
2. **`FS04` 载体选 (a)，否决 (b)**：`GateReport` 六字段是 §7.7.2 逐字抄下来的判据面（`ok` / `blocked` / `non_active` / `unknown` / `mode` / `historical_only`），加第七字段等于改判据面，而 `FS04` 的信息量在 `detail.dual_ids` 里已经够（数组 + 输入顺序）。代价写明：`diagnostic` 模式**没有任何 `dual_id` 标记** —— 该模式不抛 `GateError`，`GateReport` 又无槽位。这是本裁定的直接代价，故在 §7.8.4 / §7.16.4 / §7.16.6 / `C2` **四处同步写死**，不许留两种读法。
3. **`F-A47-1` / `F-A47-3` 标「接线后生效」并给 `a` 后缀替代判据**：两条的度量是 HTTP 状态码，而映射层不存在（`backend/app/**` 里 `assert_factors_usable` 调用方 0、`except GateError` 0、`main.py` 六个 `exception_handler` 无 `GateError`）。接线前可验的只有闸门层 `detail` 的正确性（`F-A47-1a`）与「闸门不洗错 + 映射层不存在」这一事实（`F-A47-3a`）。**不新增裁定、不改阈值**，只把「已成立的事实」与「尚未存在的对象」分开计分。

**`F-A45-2` 的四项判法（可复跑；基线锚 = `HEAD:backend/tests/test_factor_gate.py`，提交 `286c1c86` / 24,708 B / sha256 `fc675edf…`）**

| 项 | 判法 | 基线实测 | 派单前工作区实测 |
| --- | --- | --- | --- |
| ① 删除断言行 | `git diff -U0` 中 `^-` 且匹配 `^[ \\t]+assert ` 的行数 | — | **0** |
| ② 断言条数 | `grep -cE '^[ \\t]+assert '` | **129** | **222**（≥ 129） |
| ③ `skip` / `xfail` | `@pytest.mark.skip` / `@pytest.mark.xfail` 命中数 | **0 / 0**（`skipif` 2） | **0 / 0**（`skipif` 5，新增 3 条 reason 均含「本机无 `D:/TSP/data`」） |
| ④ `assert` 行内 `>=` | 出现次数 | **1** | **1** |

允许的差异**只有一类**：旧异常类型 → §7.17.4 指定的新类型。基线里共 3 处非 `GateError` 的 `pytest.raises`，逐条列明：

| 基线位置（`HEAD`） | 旧类型 | 新类型 | 依据 |
| --- | --- | --- | --- |
| `test_unknown_mode_is_rejected`（`:390-392`） | `ValueError` | `gate.GateError`（`code=="FS09"`、`detail["submitted_id"]=="mode"`） | §7.17.4 `C4` |
| `test_ledger_consistency_check_is_explicitly_not_implemented`（`:402-404`） | `NotImplementedError` | `gate.GateError`（`code=="FS06"`），用例名同步改 | §7.17.4 `C3` |
| `test_live_config_allowlist_fails_closed_on_summary_mismatch`（`:446-448`） | `ValueError` | **保持原样** | 不经 `assert_factors_usable`，不在 `C1` 出口范围 |

实现方须在验收记录里逐条列出**实际**替换处（文件:行 + 旧类型 → 新类型 + 新增断言），并附上表的四项实测；只列「改了测试」不算。

**未动项（硬约束）**

| 项 | 断言 | 实测 |
| --- | --- | --- |
| `§7.1` 八行公式 | LF 归一 `2,514` 字符 / `6d3db0139a45f54c`；CRLF 保留 `2,541` 字符 / `a8e88134f60b504c` | 与 v0.13 **逐字节相等**（`verify_v014.py` B1–B3） |
| `F-A1`–`F-A42` | 判据行逐行未动 | 54 条判据行逐行相等（E1）；未新增 `F-A1`–`F-A42` 号（E2） |
| 判据阈值 | 零改动 | 同上 |
| `backend/**`、`docs/factors/**` | 一个字节不改 | 未写入、未提交 |

**版本关系**：v0.13 保持原字节、不删不改，作为「被退回稿」保留；v0.12（更早的被退回稿）、v0.11（未签发）、v0.10 及更早逐字节保留。本版只收口 R14 三项，**不含**任何新裁定。

'''
TAIL = '---' + LF + LF
assert t.endswith(TAIL), '正文必须以 --- 空行结尾'
t = t[:-len(TAIL)] + SEC14 + TAIL
EDITS.append('R14-12 §14')

# ---------- 逐行 numstat（LF 行面上算） ----------
base_lines = BASE_LF.split(LF)
new_lines = t.split(LF)
sm = difflib.SequenceMatcher(None, base_lines, new_lines, autojunk=False)
ins = rep = dele = 0
net = 0
replaced_pairs = []
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag == 'insert':
        ins += j2 - j1
        net += j2 - j1
    elif tag == 'delete':
        dele += i2 - i1
        net -= i2 - i1
    elif tag == 'replace':
        # numstat 口径：一对 replace 计 max(旧,新) 行；净变化按 (新-旧) 累加
        rep += max(i2 - i1, j2 - j1)
        net += (j2 - j1) - (i2 - i1)
        replaced_pairs.append((i2 - i1, j2 - j1))
print('numstat (base -> new, LF 行面):')
print('  base lines', len(base_lines), '| new lines', len(new_lines),
      '| delta', len(new_lines) - len(base_lines))
print('  insert', ins, '| replace', rep, '| delete', dele)
print('  replace 明细 (旧行数 -> 新行数):', replaced_pairs)
assert net == len(new_lines) - len(base_lines), 'numstat 自洽校验失败' + str(net)
assert sum(a for a, _b in replaced_pairs) == rep == sum(b for _a, b in replaced_pairs), 'replace 逐对不自洽'

# 收尾：整体 LF -> CRLF
t = t.replace(LF, CR + LF)
body = t.encode('utf-8')
h = hashlib.sha256(body).hexdigest()
nbytes = len(body)
nlines = body.count((CR + LF).encode())

FOOTER = (
    '本文件正文 sha256：`{h}`（校验：`head -c {n} "{dst}" | sha256sum`；正文 = 全文去掉最后一行 footer，以换行结尾）'
    '· 正文 `{n} B` · 全文 `{tot}` 行（正文 `{b}` + footer 1）'
    '· 版本 **v0.14（2026-11-08 R14：三处判据可判定性收口 —— `F-A45-2` 由不可判的「现有测试零改动」改为'
    '「判定强度不放宽」四项可机械判（删除断言行 0 / 条数不减 129 / 无 skip·xfail / `assert` 行内 `>=` 不增）；'
    '`FS04` 载体按裁定 (a) 写死为 `GateError.detail`（`GateReport` 不加第七字段，`diagnostic` 不产生标记），'
    '并在 §7.8.4 / §7.16.4 / §7.16.6 / §7.17.4 `C2` 四处同步；`F-A47-1` / `F-A47-3` 标「接线后生效」'
    '并新增 §7.17.8 的 `F-A47-1a` / `F-A47-3a` 接线前判据；判据阈值零改动）**'
    '· 生成：**v0.13 逐字节为底**（277,296 B / 2,295 行 / 全文 `a1374eb5…5d5ffd82` / '
    '正文 `73901fd0…9cd2031a`）+ 13 处改动（H1 / §7.8.4 判定矩阵 / §7.8.4 错误码表 / §7.8.4 载体段 / '
    '§7.16.4 载体条 / §7.16.6 表行 / `C2` / §7.17.2 / `F-A45-2` / `F-A47-1` / `F-A47-3` / '
    '新增 §7.17.8 / 新增 §14）+ 本 footer 由正文字节重算'
    '· v0.14 为现行版；v0.13、v0.12（两份被退回稿）、v0.11（未签发）、v0.10 及更早逐字节保留不删'
    '· `§7.1` 八行公式**十二份全同（v0.3–v0.14，含本版）**：LF `2,514` / `6d3db0139a45f54c`、'
    'CRLF `2,541` / `a8e88134f60b504c`（台账 v5.11 `[4]` 绑块哈希，版本号不参与判定）'
    '· `F-A1`–`F-A42` 一字未动；新增判据仅 `F-A43`–`F-A47`（v0.12 带入）及其接线前形态 '
    '`F-A47-1a` / `F-A47-3a`（本版新增，与母条同源、不构成新裁定）；新增错误码仅 `FS09`（占空位）'
).format(h=h, n=nbytes, dst=DST, tot=nlines + 1, b=nlines)

out = body + FOOTER.encode('utf-8') + (CR + LF).encode()
open(DST, 'wb').write(out)
print()
print('WROTE', DST)
print('body bytes', nbytes, '| body lines', nlines, '| total lines', nlines + 1)
print('body sha256', h)
print('full sha256 ', hashlib.sha256(out).hexdigest())
print('file bytes', len(out))
print('edits', len(EDITS), EDITS)
