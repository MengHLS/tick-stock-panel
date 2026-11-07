# -*- coding: utf-8 -*-
"""v0.12 = v0.11 逐字节为底 + §7.17 一节 + 两处签名复述句 + H1 + footer 重算。

底本钉哈希（v0.11 曾被并行流程原位改写成两组字节，故只认哈希）：
    245,364 B / 2,061 行 / 全文 c2eec518d6bae2c2ac483a8a6524d7c28ec6048f339c723c1e68c9ebc0c3c58d

footer 自洽：正文 = footer 之前的前缀（以换行结尾），footer 里的 sha 与长度都由这段前缀复算，
因此 head -c <正文长度> v0.12 | sha256sum == footer 里的值（固定点，可复跑同字节）。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

D = Path("C:/work/sourcecode/tick-stock-panel/docs/architecture")
SRC = D / "FACTOR_ENGINE_CONTRACTS_20261107_v0.11.md"
DST = Path("C:/work/sourcecode/tick-stock-panel/research/arch-build-20261107/_repro_r12/out_v12.md")

BASE_SHA = "c2eec518d6bae2c2ac483a8a6524d7c28ec6048f339c723c1e68c9ebc0c3c58d"
BASE_SIZE = 245364
BASE_LINES = 2061

H1_OLD = "# 因子化引擎与生产侧执行器 —— 接口契约 v0.11（2026-11-07）"
H1_NEW = "# 因子化引擎与生产侧执行器 —— 接口契约 v0.12（2026-11-07）"

SIG908_OLD = (
    "**闸门层（单一实现，禁止各入口各写一遍）**：新增 "
    "`app/factors/gate.py#assert_factors_usable(factor_ids, mode, *, "
    "allow_non_active=False, allow_retired=False) -> GateReport`。"
)
SIG908_NEW = SIG908_OLD + (
    "（**v0.12 追加**在尾部追加一个 keyword-only 参数 "
    "`namespace: str | Mapping[str, str] = \"factor\"`，缺省即今日行为，"
    "见 §7.17.2；既有参数名、顺序、缺省值一个不改。）"
)

SIG1634_OLD = (
    "`assert_factors_usable(factor_ids, mode, *, require_status=True)` 是 "
    "§7.7.5 / §7.8.4 已定的入口签名，本节不改其语义，只固定调用点；"
    "`mode` 三值 `production` / `research` / `diagnostic` 的含义见 §7.8.4 矩阵。"
)
SIG1634_NEW = SIG1634_OLD + (
    "（**v0.12 追加**：签名尾部追加 keyword-only `namespace`，缺省 `\"factor\"`；"
    "「本节不改其语义」只约束**既有**参数，新参数不改变任何既有 id 在缺省面上的结论，"
    "见 §7.17.2 S1。）"
)

BLOCK = '''
### 7.17 命名面、`kind` 豁免集与闸门错误面（v0.12 新增；`F-A43`–`F-A47`）

**本节不新增任何准入裁定，只做三件事**：给 §7.10.3 N2「`namespace=column` 的引用不得因『名字恰好等于某因子 id』而被判 status」一个**可执行的入参**；把 `kind` 的**豁免集**从实现里的判据白名单纠回 §7.8.3 第一行的「仅 `base` / `virtual`」；把闸门下**所有**失败分支收成 `GateError` 一条出口（HTTP 400 + `detail`），消灭「接线后变 500」这一类。写法与 §7.16 开头同构：本节只把已经写在别处的结论落到可测的输入输出上。**判据阈值一个不动；`F-A1`–`F-A42` 一字不改。**

#### 7.17.1 事实（盘上只读实测，2026-11-07 22:5x，可复跑 `research/arch-build-20261107/probe_collision_20261107.py`）

**（1）活配置的 19 个引用名**（清单 `summary.live_config` 的 primary 层；`records 93 = primary 79 + companion 14`，`sources 22`，去重 id 19）按盘上事实三分（口径注意：清单**顶层** `records` 是 **218** —— 那是全部记录，不是这里的分层；两套数不得混引）：

| 类 | 数 | id | `RegistryFacts.kind` | `status` | `lang` |
| --- | --- | --- | --- | --- | --- |
| 撞名（`spec` 命中的 custom） | **4** | `boll_lower` `boll_upper` `ma20` `ma60` | `custom` | `None` | `dsl` |
| 列回落（无 spec 无定义，命中列全集） | 14 | `close` `high` `high_60d` `limit_down_price` `limit_up_price` `low_60d` `ma10` `ma5` `macd_dea` `macd_dif` `open` `raw_close` `raw_high` `raw_low` | `base` | `None` | `None` |
| 注册 base（有 spec，kind=base） | 1 | `vol_ratio_5d` | `base` | `None` | `dsl` |
| 合计 | **19** | | | | |

`lang=None` 正好标出「不是 spec、靠列全集回落的」那 14 个 —— 这是区分两类 base 的唯一盘上特征。

**清单侧已经先判过了**：同一份产物的 `summary.live_config` 里 `by_namespace` = **`column` 79/79**、`by_class` 全 `base`、`by_verdict` 全 `allow`。也就是说 §7.10.3 N2 的结论**早就在清单生成器一侧生效**，目前缺的只是闸门那一侧没有承载位置（见（4））。这是条款 A 的依据：它**不新增裁定**，只把已有结论接到执行点。

**（2）三个集合的实际规模与包含关系**

| 集合 | 规模 | 说明 |
| --- | --- | --- |
| `gate._column_universe()` | **68** | `dsl.BASE_COLUMNS`(9) ∪ `pipeline` 六个列集合 |
| `custom_signals.ALLOWED_FIELDS` | **54** | §7.10.3 N1 说的「基础指标列」 |
| `ALLOWED_FIELDS − _column_universe()` | **0** | **AF ⊆ U** |
| `_column_universe() − ALLOWED_FIELDS` | **14** | 8 个 `_` 暂存列（`_boll_std` `_daily_pct` `_ema12` `_ema26` `_kdj_hn` `_kdj_ln` `_tr` `_vol_ma5`）+ 6 个身份/辅助列（`date` `float_shares` `name` `quote_ts` `symbol` `total_shares`） |

**`U = AF ∪ 14` 是精确等式**（不是近似）。对 19 个活配置名的意义：面闭合判据用 `_column_universe()` 还是 `ALLOWED_FIELDS`，对这 19 名**完全等价**（19/19 同时属于两者），差异只在「那 14 个能不能被声明成列面」（见 7.17.2 S4 与 2.4 段的取舍）。

**（3）闸门今天的判定（`shadow=True`，不抛异常）**

| 调用 | 结果 |
| --- | --- |
| `assert_factors_usable(19 名, "production")` | `ok=False`，`blocked` = **4 条 `FS01`**：`boll_lower` `boll_upper` `ma20` `ma60`（`status` 均为 `null`） |
| `assert_factors_usable(19 名, "research")` | 同样 **4 条 `FS01`** |
| `assert_factors_usable(19 名, "research", allow_non_active=True)` | `ok=True`，`non_active` = 那 4 名 |
| `assert_factors_usable(19 名, "diagnostic")` | `ok=True`，`non_active` = 那 4 名 |

与 21:0x 的 B2 取证 `research/gate-core-20261107/EVIDENCE_gate_realdata.json` 逐项相同（4 名、同码、同序）⇒ 22:5x 复跑无漂移。

**（4）现签名里没有承载位置**：`inspect.signature` 实测 8 个参数（`factor_ids, mode` + 6 个 keyword-only），**没有** `namespace`。而「这个引用来自列面还是因子面」只有调用方知道 —— `custom_signals.allowed_fields()` 返回的是 `ALLOWED_FIELDS | 因子 id | 字符串扩展字段` 的**并集**，集合语义本身不表达先后；§7.10.3 N1 自己已经指出这一点并要求「实现必须显式排序」。

**（5）`kind` 的豁免集是白名单，不是豁免集（条款 B 的事实；取证于 22:5x）**

- 取证时（22:5x）的盘面：`gate.py` 顶部常量 `GATED_KINDS: frozenset[str] = frozenset({"custom", "composite"})`，`_judge` 内一行 `if fact.kind not in GATED_KINDS: return _Verdict((), False, False, fact.factor_id)`。这行是**判据白名单**——只有列进去的两种 `kind` 才判，**其余一律免检**。
- 契约要的是**豁免集**：§7.7.2 末行 + §7.8.3 第一行「`base` / `virtual` 不 gate」。两个集合的差 = 一切既不是 `custom`/`composite`、也不该被豁免的 `kind` ⇒ **静默免检**。
- 可复现（`MappingFacts` 注入；同一 `vol60`、`alias_of="uf_vol60"`）：注成 `kind="custom"` → `production` 得 `FS03`；注成 `kind="frame"` → `[]`（空 verdict，直接放行）。`FactorFacts.kind` 的缺省值是 `None`，而 `None not in {"custom","composite"}` 恒真 ⇒ **缺省即免检**。
- `kind` 的合法域实测：`FactorSpec.kind` ∈ {`base`, `virtual`, `custom`, `composite`}（`registry.py` 造 `virtual`/`base`；`store.py` 造 `custom`/`composite`，并对域外值抛 `ValueError`）。`frame` / `sidecar` 是 **`FactorProviderKind`**（`extensions/factors.py` 的 `Literal["frame","sidecar"]` 与单独校验），**不进入** `FactorSpec.kind`。所以「`kind="frame"` 进闸门」只能来自注入的 `FactsSource`（`MappingFacts`）或日后新增的 kind —— 但**白名单不因「今天没有」而成立**（与 §7.8.3 对 python 因子分支的要求同构：分支必须写死，不能靠盘上恰好没有）。
- **盘面推进（在本版落盘前已发生，必须登记）**：`2026-11-07 23:08:35` 的 `gate.py` 已出现 `EXEMPT_KINDS: frozenset[str] = frozenset({"base", "virtual"})` 与 `if fact.kind in EXEMPT_KINDS:` —— 即**条款 B 的方向已被实现侧先行采用**。因此本条款**不引用任何 `gate.py` 行号作判据锚点**：锚点是**符号名**（`EXEMPT_KINDS`）与**代码文本**（`in` / `not in`），行号随实现推进而变；`F-A46-1`…`F-A46-4` 全部按**行为**判，不按行号判。

**（6）闸门错误面的现状（条款 C 的事实；取证 22:5x，盘面推进 23:08:35）**

- 取证时（22:5x）：`_guard_dual_id` 对 `FS04` 抛 **`NotImplementedError`**；`check_ledger_consistency` 对 `FS06` 的台账分支也抛 **`NotImplementedError`**。
- **盘面推进**：`23:08:35` 的 `gate.py` 里 `_guard_dual_id(resolved, *, mode, report, entry=None, shadow=False)` 已改成**抛 `GateError(code="FS04")`**（`detail` 照 §7.16.4，另给 `dual_ids`）—— 即 C2 的方向已被实现侧先行采用；**仍抛 `NotImplementedError` 的只剩 `check_ledger_consistency` 一处**（C3 未落地）。
- **真正的缺口没变**：`backend/app/**` 里 `GateError` 除 `factors/gate.py` 外 **0 命中**；`main.py` 现有 6 个 `exception_handler` 里**没有一个接 `GateError`** ⇒ 接线后 `GateError` 与 `NotImplementedError` **都会落到框架默认的 500**，§7.16.6 要求的「400 `FS04`」在真实 HTTP 上仍不会出现。这正是 C6 要补的那一处。
- `GateError.__init__(code, detail, report, entry=None)` 的 `report` 是**必填**位置参数；入参非法时没有 `GateReport` 可传，这也是今天入参错误只能靠 `ValueError` 逃出去的原因（C5）。

#### 7.17.2 条款 A：命名面由**调用方声明**，闸门按面判定（`namespace`）

签名（唯一新增；追加在最后、keyword-only、带缺省）：

```python
assert_factors_usable(
    factor_ids, mode, *,
    allow_non_active=False, allow_retired=False,
    require_status=True, shadow=False, entry=None, facts=None,
    namespace: str | Mapping[str, str] = "factor",   # v0.12 唯一新增
) -> GateReport
```

- **位置参数顺序与全部既有 keyword-only 参数的名字/缺省值一字不改** ⇒ 既有调用点与 `backend/tests/test_factor_gate.py` **零改动**（调用点集合按验收当时 `grep -rn "assert_factors_usable" backend/` 的结果逐个核，本文不写死个数）。
- **缺省 `"factor"` = 今日行为**（fail-closed 方向：不声明就按因子面判，宁可误拦不可漏放）。

| 码 | 规则（机械可判） |
| --- | --- |
| **S1** | `namespace="factor"`（含缺省）：逐 id 判定与今日**完全相同**，`blocked` 集合逐 id 相等 |
| **S2** | `namespace="column"`：该 id 按 §7.8.3 第一行 **base** 处理 —— 不判 `status`（无 `FS01`）、不判 alias（无 `FS03`/`FS06`）、不判 `lang`（无 `FS05`）；`non_active` 不记；`resolved` 仍取 `fact.factor_id` |
| **S3** | Mapping 形态：逐 id 取面；**缺键即报错**（S5 的 `FS09`，不静默补齐 —— 漏一个「忘了声明的列」就等于继续误拦 4 条）；多余键忽略 |
| **S4** | **面闭合**：`namespace="column"` 且 id ∉ `_column_universe()` → **`FS02`**（fail-closed；不静默 allow、不退化成 `FS01`）。这条堵住「把 draft 因子改名成列名来免检」的唯一入口 |
| **S5** | 取值域 `{"factor", "column"}`；域外（含 `"base"` / `"virtual"` / `"COLUMN"` / `None`）→ `FS09`（入参非法，见 7.17.4 C4），不进 `blocked`。`base`/`virtual` 是 §7.8.3 的 **kind**，不是 namespace —— 允许传 kind 会让两面语义混成一锅 |
| **S6** | 非 column 面 id 的判定完全不动；`detail` 键集合不动（§7.16.4 固定，S4 与 S5 的区分靠 `code` 与 `message`，不新增键） |

**面闭合用 `_column_universe()`（68），不用 `ALLOWED_FIELDS`（54）**，三条理由：① 同源 —— 闸门 `RegistryFacts.facts` 判「未登记」用的就是这个集合（`if factor_id in _column_universe()` 那一支；盘面 `23:08:35` 在 `:235`），再引入第二个就是两个口径；② 不放宽 —— `U = AF ∪ 14` 是精确等式，那 14 个本来就以 base 身份免 gate，用 68 只是把**今天已经免检的**显式承认下来，没有新增任何免检面；③ 可收窄 —— 日后若把 `_` 暂存列与身份列移出（68 → 54），S4 自动跟着收窄，因为判据绑常量、不绑数字。代价写明：`symbol` / `date` 这类身份列也能被声明成列面而免检 —— 与今天的行为一致，不是本条款引入的。

**为什么否决「消费入口 column-first」**（同名先按列判、不进闸门）：实现只有一种写法 —— 改 `RegistryFacts.facts` 的分支顺序。三条代价：① **全局且不可关闭** —— 任何名叫 `ma20` 的 draft 因子从此在任何入口都不可 gate，且没有任何提示；② **把「谁在用」压成「名字巧合」** —— `namespace=column` 的正确依据是**引用来自列面**（`field:X` 命中 `ALLOWED_FIELDS`），不是**名字恰好也叫列**；今天两者在 4 个冲突名上重合，明天有人造一只 `ma20` = 「20 日均线变化率」就会静默继承列的免检身份；③ **判据不可分** —— `F-A29` 要求「同名因子 id 的信号 verdict 必须 allow」，§7.8.4 要求「Provider 注册无 status → `FS01`」，column-first 让两条同时「成立」，靠的是分支顺序而不是判据。而本条款的代价也写明：调用点必须逐个传 `namespace`，**漏传不报错**，只会回到 fail-closed 的因子面（4 条重新出现）—— 这不是缺陷，是**可探测性**（L1 影子「block 集合逐 id 相等」会立刻把漏传变成一条可指认的差异）。

#### 7.17.3 条款 B：`kind` 用**豁免集**，不用判据白名单

```python
EXEMPT_KINDS: frozenset[str] = frozenset({"base", "virtual"})   # §7.8.3 第一行，闭合
...
if fact.kind in EXEMPT_KINDS:          # 只有这两个免检
    return _Verdict((), False, False, fact.factor_id)
# 其余一律进入判定：custom / composite / None / frame / sidecar / 任何未知 kind
```

| 码 | 规则 |
| --- | --- |
| **K1** | 豁免集 = {`base`, `virtual`} 且**闭合**：任何**新增** kind 默认被判定，不需要改代码；要豁免必须同时改 §7.8.3 与这个常量（只改一处即被 `F-A46-3` 抓到） |
| **K2** | `kind is None` **不得**免检：它表示「没读到 kind」这一**事实缺失**，按 `custom` 判（`status` 空 ⇒ `FS01`），不是按 `base` 免检 |
| **K3** | 域外 kind（`frame` / `sidecar` / `custom_python` / 拼写错）按 `custom` 判，**不**抛 `ValueError`。理由：抛错会跳过 `FS01`/`FS03` 判定，把一个「可疑的 kind」变成「没判过就放行」；按 `custom` 判才 fail-closed（provider 注册件 `status` 为空 ⇒ `FS01`） |
| **K4** | 不得用 `class`（§7.12 表的 `base`/`virtual`/`custom_dsl`/`custom_python`/`composite`/`unregistered`）替代 `kind` 判豁免，反之亦然 —— 两者是两根轴 |

**代价**：改名或新增 kind 的实现若忘了同步 §7.8.3，会被**误拦**（fail-closed 的一侧）；这是可接受的代价，与 §7.8.4「误放行比判死更危险」同向。

#### 7.17.4 条款 C：闸门内失败一律 `GateError` → HTTP **400** + `detail`

| 码 | 规则 |
| --- | --- |
| **C1** | **出口唯一**：闸门对外只抛 `GateError`。`NotImplementedError` / `AssertionError` / `KeyError` / `ValueError` **不得**逃出 `assert_factors_usable` |
| **C2** | `FS04` 按 §7.16.6 **实现**：`production` / `research` → `GateError(code="FS04")` → 400；`detail` = §7.16.4 的 6 键 + **唯一授权附加键 `detail.dual_ids`**（数组，按输入顺序列全部指向同一 canonical 的 submitted id）；`submitted_id` 取输入顺序的第一条，`resolved_id` = `canonical_id` = 共同 canonical，`table_row` 为 **`null`**（§7.15.1 尚无机器可读副本，待 C3 落地后填行号）；`diagnostic` → 允许并标 `dual_id=true`。**仍抛 `NotImplementedError` 即为不合格**（盘面 `23:08:35` 已按本条改成 `GateError`） |
| **C3** | 台账不可判（`check_ledger_consistency`）→ `GateError(code="FS06")`，**不得**静默返回「一致」、也不得抛 `NotImplementedError`（**本条截至 `23:08:35` 仍未落地**） |
| **C4** | 入参非法（`mode` 域外、`namespace` 域外或 Mapping 缺键、`status` 域外）→ `GateError(code="FS09")`。`FS09` 是 `FS01`–`FS10` 之间**唯一空位**（`FS01`–`FS08`、`FS10` 已占），本条只占用它、**不改任何既有码的含义**；`detail` 六键照 §7.16.4，`submitted_id` = 违规**参数名**（如 `"namespace"` / `"mode"`），`resolved_id` / `canonical_id` / `table_row` = `null` |
| **C5** | `GateError.report` 放开为 `GateReport \| None = None`（入参非法时无报告可传；对外形状只是 `detail`，`report` 仅供调试携带） |
| **C6** | **映射精确**：API 层只把 `GateError` 映射成 400；其它异常保持 500。**禁止** `except Exception: return 400` —— 那会把编程错误洗成客户端错误 |
| **C7** | `detail` 键集合 = §7.16.4 的 6 键 + **唯一被授权的附加键 `dual_ids`**（仅 `FS04`）。理由：`violations` 的每项是 `{submitted_id, code}`（语义是「多条违规」），而 FS04 是「一条违规涉多个 id」，复用 `violations` 会把两种语义混成一个；因此新增一个数组键、只许这一个。`FS09` **不加**任何附加键（靠 `code` 与 `message` 区分） |

#### 7.17.5 判据（新号 `F-A43`–`F-A47`；`F-A1`–`F-A42` 一字不改）

编号核对：v0.11 全文 `F-A1`–`F-A42` 共 **42 个唯一号全部占用**（含 `F-A42-1…6` 子号），故新号自 `F-A43` 起；本节不修改任何既有编号，`F-A24` / `F-A29` / `F-A42-6` 保持原义。

**`F-A43` 命名面入参存在且 fail-closed**

| # | 判据 | 度量 |
| --- | --- | --- |
| `F-A43-1` | 签名 | `inspect.signature` 逐参数断言：前两参数仍是 `factor_ids, mode`（`POSITIONAL_OR_KEYWORD`、无缺省），`namespace` 是 **`KEYWORD_ONLY`** 且缺省 `"factor"`；原有 6 个 keyword-only 参数名与缺省值一字不改 |
| `F-A43-2` | 取值域 | 传 `"base"` / `"virtual"` / `"COLUMN"` / `None` 各一次 → `FS09`（`GateError`，`detail.code=="FS09"`），`blocked` 不进 |
| `F-A43-3` | Mapping 覆盖 | `namespace={}` 与 19 名一起传 → `FS09`（缺键）；少 1 键 → 同；多 1 个无关键 → 正常返回，结论与不多时相同 |
| `F-A43-4` | 面闭合 | `namespace="column"` 传已登记因子（如 `uf_vol60`，不在列全集）→ `FS02`；传 `close`（列全集内）→ 不拦 |

**`F-A44` 撞名在闸门上双面可判（本条核心）**

| # | 判据 | 度量 |
| --- | --- | --- |
| `F-A44-1` | 正样本：19 名在列面全过 | `assert_factors_usable(19 名, "production", namespace="column")` → `ok=True`、`blocked=()`、`non_active=()`、`unknown=()`、`mode="production"` |
| `F-A44-2` | 负样本：同 4 名在因子面仍拒 | 同 4 名，`namespace="factor"`（缺省）`mode="production"` → `blocked` 逐条为 `(id, None, "FS01")`，集合恰为 `{boll_lower, boll_upper, ma20, ma60}`；`research` 同 4 条 `FS01` |
| `F-A44-3` | 边界不变：另外 15 名 | 15 名的 `blocked` / `non_active` / `unknown` 与接线前逐 id 相同（14 个仍靠列回落、`vol_ratio_5d` 仍是注册 base）；**本次改动只应改变这 4 个 id 的结论，多改一个即失败** |
| `F-A44-4` | 数值不变 | 7 条活信号（`boll_breakdown_lower`、`boll_breakout_upper`、`ma20_breakdown`、`ma20_breakout`、`ma_dead_5_20`、`ma_golden_20_60`、`ma_golden_5_20`）与未接闸门时 `max_abs_diff == 0`（与 `F-A29` 同口径，不另立门槛） |

样本来源是**盘上实测的 19 名**，不是构造的：验收时应**重跑取证脚本取当时的 19 名**，不要把手抄的 19 个名字写进测试常量（活配置一改，测试就变成在验历史）。

**`F-A45` 缺省即今日（不回归）**

| # | 判据 | 度量 |
| --- | --- | --- |
| `F-A45-1` | 不传 `namespace` | 19 名 `production` → `blocked` 集合 == 7.17.1(3) 实测的 4 名；`research` / `research+allow_non_active` / `diagnostic` 三组的 `ok`、`non_active`、`unknown` 逐项相等 |
| `F-A45-2` | 现有测试零改动 | `backend/tests/test_factor_gate.py` 一个字不改，全部通过 |

**`F-A46` `kind` 豁免集闭合**

| # | 判据 | 度量 |
| --- | --- | --- |
| `F-A46-1` | 同一 id 换 kind 结论不变 | 同一 `vol60`（`alias_of="uf_vol60"`）分别注成 `kind ∈ {custom, composite, frame, sidecar, None, "weird"}`，`production` 六次都必须报**同一个** `FS03`；今日 `frame`/`sidecar`/`None` 得 `[]`，即为负样本 |
| `F-A46-2` | 缺省 kind 不漏 | `FactorFacts(registered=True)`（`kind` 取缺省 `None`）→ `production` 得 `FS01`，**不是**放行 |
| `F-A46-3` | 两处同步 | `EXEMPT_KINDS` 与 §7.8.3 第一行的豁免集合相等（`EXEMPT_KINDS == {"base","virtual"}`）；只改一处即失败 |
| `F-A46-4` | 不误伤 | `base` / `virtual` 两类 id（含 `vol_ratio_5d` 与 14 个列回落名）在 `production` 仍 `blocked=()`、`non_active=()` —— 豁免集收窄**不得**把这两类拖进判定 |

**`F-A47` 错误面唯一且是 400**

| # | 判据 | 度量 |
| --- | --- | --- |
| `F-A47-1` | `FS04` 走 400 | 同一策略同时提交 `vol60` + `uf_vol60`，`production` 与 `research` 各一次 → HTTP **400**、`detail.code=="FS04"`、`detail.dual_ids` 的集合 == `{vol60, uf_vol60}`（按输入顺序）、`detail.table_row is None`；`diagnostic` → 200 且标 `dual_id=true` |
| `F-A47-2` | 无 `NotImplementedError` | `grep -c "raise NotImplementedError" backend/app/factors/gate.py` == 0（按**代码文本**数，不按行号；今日为 1，在 `check_ledger_consistency`）；`_guard_dual_id` 与 `check_ledger_consistency` 的失败分支均抛 `GateError` |
| `F-A47-3` | 不洗错 | 往闸门内注入一个 `RuntimeError` → HTTP **500**（不是 400）；只有 `GateError` 被映射成 400 |
| `F-A47-4` | `FS09` 形状 | 传 `namespace="COLUMN"` → 400、`detail` 键集合 == §7.16.4 的 6 键、`submitted_id=="namespace"`、`table_row is None` |

#### 7.17.6 实现与接线约束（给系统开发工程师；本节只出条款，不写实现）

**改动面（只此三处）**

| 文件 | 改动 | 限制 |
| --- | --- | --- |
| `backend/app/factors/gate.py` | ① `assert_factors_usable` 加 `namespace`（S1–S5）；② `GATED_KINDS` → `EXEMPT_KINDS` 并反转判支（K1–K4）；③ `_guard_dual_id` / `check_ledger_consistency` 改抛 `GateError`；④ `GateError.report` 允许 `None` | 不改 `GateReport` 六字段；不改 `FS01`–`FS06`/`FS10` 任何码含义；不改 `_column_universe()` 的内容 |
| 消费侧（`custom_signals`）+ 既有调用点 | 解析 `field:X` 时**先列后因子**（N1 的显式排序），把逐 id 的 `namespace` 传给闸门；L1 期间 `shadow=True` 不变 | 不改 `ALLOWED_FIELDS` 本身；不改 `materialize_factor_columns` 的补算行为；`mode` 一个都不改 |
| API 层 | 注册 `GateError → 400`（`detail = exc.to_detail()`） | **只**接 `GateError`；不得接 `Exception` |

**不许做的四件事**：① 不许把 `namespace` 做成全局开关或环境变量（面是每次调用的事实，不是部署配置）；② 不许在 `RegistryFacts.facts` 里按名字改分支顺序（那就是被否决的 column-first）；③ 不许让 `namespace="column"` 对未登记名字静默 allow（S4 必须是 `FS02`）；④ 不许用 `stability` / `kind` / `class` 反推面或反推豁免（§7.8.4 的硬规则同样适用于面）。

**L1 影子的验收信号**：接线后先跑 L1（只报告不阻断），预期 `block` 集合从 **4 → 0**（19 名全部按列面放行）。若仍是 4 条，第一嫌疑是调用点漏传 `namespace`（本条已把这条设计成可探测），不是条款失效。

#### 7.17.7 与 §7.10.3 N1 的关系（一处字面收窄，明写）

N1 原文有一句：「命中 → `namespace=column`，**不进入因子闸门**」。本条款让 column 面的 id **进入**闸门（然后直接 allow），与这句字面不同，理由三条：① **分类逻辑不该复制到每个入口** —— §7.7.2 的裁定是「闸门放在消费入口、单一实现、禁止各入口各写一遍」，让调用方先过滤掉列、只把因子丢进闸门，等于把「什么算列」复制到每个入口；② **拆成两次调用会断掉 `FS04`** —— `FS04` 必须看**整组** id，先按面拆成两次，跨面的双 id 就再也检不出来；③ **「进入但不判」与「不进入」在结论上等价，在可观测性上更好** —— 闸门可以如实报告「这个 id 我按列面放过了」，而「根本没进来」在报告里什么都不留。

因此 N1 的落点拆成两段：**解析（谁算列）归消费侧**（原文照旧）；**判定（按面给结论）归闸门**（本节的 `namespace`）。N1 的结论不变。`F-A24`（判清单的 `ref_namespace`）与 `F-A29`（判数值不变）都不需要改，两者仍然成立，且现在**第一次可以在闸门层被执行**。
'''


def main() -> None:
    raw = SRC.read_bytes()
    assert len(raw) == BASE_SIZE, f"底本字节 {len(raw)} != {BASE_SIZE}"
    sha = hashlib.sha256(raw).hexdigest()
    assert sha == BASE_SHA, f"底本 sha {sha} != {BASE_SHA}（v0.11 被改写，拒绝构建）"

    text = raw.decode("utf-8")
    # 底本是 CRLF（2061 CR / 2061 LF）：整族 v0.3–v0.11 都是 CRLF，产物必须同构
    assert text.count("\r\n") == BASE_LINES, f"CRLF 行数 {text.count(chr(13)+chr(10))} != {BASE_LINES}"
    assert text.replace("\r\n", "").count("\r") == 0, "存在孤立 CR"
    lines = text.split("\r\n")
    assert lines[-1] == "", "底本未以换行结尾"
    body_all = lines[:-1]
    assert len(body_all) == BASE_LINES, f"行数 {len(body_all)} != {BASE_LINES}"

    # --- 锚点校验（1-based） ---
    assert body_all[0] == H1_OLD, body_all[0][:80]
    assert body_all[907] == SIG908_OLD, body_all[907][:60]
    assert body_all[1633] == SIG1634_OLD, body_all[1633][:60]
    assert body_all[1684].startswith("| F-A42-6 |"), body_all[1684][:40]
    assert body_all[1685] == "", "1686 行不是空行"
    assert body_all[1686].startswith("## 8. 改动性质总表"), body_all[1686][:40]
    footer_old = body_all[-1]
    assert footer_old.startswith("本文件正文 sha256："), footer_old[:40]

    # --- 四处替换 ---
    out = list(body_all[:-1])          # 去掉旧 footer
    out[0] = H1_NEW
    out[907] = SIG908_NEW
    out[1633] = SIG1634_NEW

    block_lines = BLOCK.strip("\n").split("\n")
    assert all("'''" not in ln for ln in block_lines)
    # 插到 F-A42-6 之后；原 1686 的空行继续充当 §7.17 与 ## 8. 之间的分隔
    insert_at = 1685                    # 0-based：1685 行之后
    new_lines = out[:insert_at] + [""] + block_lines + out[insert_at:]
    assert new_lines[1684].startswith("| F-A42-6 |")
    assert new_lines[1685] == ""
    assert new_lines[1686].startswith("### 7.17 ")
    assert new_lines[1686 + len(block_lines) - 1] == block_lines[-1]
    assert new_lines[1686 + len(block_lines)] == ""
    assert new_lines[1687 + len(block_lines)].startswith("## 8. ")

    # --- body / footer 固定点 ---
    body_text = "\r\n".join(new_lines) + "\r\n"
    body_bytes = body_text.encode("utf-8")
    body_len = len(body_bytes)
    body_sha = hashlib.sha256(body_bytes).hexdigest()
    total_lines = len(new_lines) + 1

    footer = (
        f"本文件正文 sha256：`{body_sha}`"
        f"（校验：`head -c {body_len} \"docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md\" | sha256sum`；"
        f"正文 = 全文去掉最后一行 footer，以换行结尾）· 正文 `{body_len} B` · 全文 `{total_lines}` 行"
        f"（正文 `{len(new_lines)}` + footer 1）· 版本 **v0.12（2026-11-07 R12：§7.17 命名面 / `kind` 豁免集 / 门内错误面三条一次并入 + §7.7.2 与 §7.16.3 两处签名复述句 + 版本簿记；判据阈值零改动）**"
        f"· 生成：**v0.11 逐字节为底**（245,364 B / 2,061 行 / 全文 `c2eec518…c3c58d`）+ 4 个 hunk"
        f"（H1 / §7.7.2 `:908` 签名复述句 / §7.16.3 `:1634` 签名复述句 / §7.17 新增一节）+ 本 footer 由正文字节重算"
        f"· **v0.11 未签发**：同一路径曾出现两组不相容字节、且其自身 footer 仍写着 v0.10 的正文哈希与行数；v0.11 只保留为历史、**不参与任何判据绑定**"
        f"· v0.10（244,093 B / 2,057 行 / 正文 `head -c 242303` → `e47703f2…` / 全文 `8a3115aa…`）是 v0.12 之前唯一有效候选，**其 PASS 不外推到本版**"
        f"· v0.9（228,478 B / 正文 `d967d463…`）、v0.8（206,608 B / `2cf85ccb…`）、v0.7（193,586 B / `5a87d4b0…`）、v0.6（162,361 B / `946a1d86…`）、v0.5 / v0.4 保留不删；v0.3 冻结态（89,833 B / 914 行 / `5eb97724…`）逐字节归档于 `archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`"
        f"· **v0.12 为本周期终版：此后只走冻结评审，不再追加版本**"
        f"· §10.3 停用（R10）banner 原文保留在 §10.3 标题下三行（`⛔` / 唯一定义 / 依据），与本版零改动（v0.11 带入、未动一字）"
        f"· 本节新增判据 `F-A43`–`F-A47`（含子号），`F-A1`–`F-A42` 一字未动；新增错误码仅 `FS09`（占空位），既有码含义不变"
    )
    assert "\n" not in footer and "\r" not in footer

    full = body_text + footer + "\r\n"
    data = full.encode("utf-8")

    # footer 自洽复算：head -c body_len == body_text
    assert data[:body_len] == body_bytes
    assert hashlib.sha256(data[:body_len]).hexdigest() == body_sha
    assert data[body_len:].decode("utf-8") == footer + "\r\n"

    DST.write_bytes(data)

    print(f"size={len(data)}")
    print(f"lines={len(data.decode('utf-8').split(chr(13)+chr(10))) - 1}")
    print(f"body_len={body_len}")
    print(f"body_sha={body_sha}")
    print(f"full_sha={hashlib.sha256(data).hexdigest()}")
    print(f"grep_7_17={full.count('### 7.17 ')}")
    print(f"grep_10_3_disabled={full.count('停用')}")


if __name__ == "__main__":
    main()
