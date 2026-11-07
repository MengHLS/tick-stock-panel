# 命名面撞名条款（§7.17 草案，待 v0.12 并入）：`F-A43` / `F-A44` / `F-A45`

- 日期：2026-11-07（本机 22:5x 实测）
- 作者：系统架构师
- 状态：**已交付、未生效（条款草案，待 v0.12 并入）。** 本文件不在任何契约正文里；v0.11 正文除 §10.3 banner 外逐字节等于 v0.10，因此 `namespace` 入参**当前不存在**（`gate.py` 21:39 已落盘、纯新增、**生产侧 0 个调用点**），闸门对 19 个活配置名仍拦 4 个（§1.3 实测）。并入 v0.12 后才生效（并入点见 §6.4）。R11 §7 指向本文件。
- 对象：`backend/app/factors/gate.py#assert_factors_usable`（§7.7.2 / §7.16.3 的单一实现点）
- 边界：只出条款，不写实现（实现 → 系统开发工程师，验收 → 独立审核工程师）。未改 `backend/**`。

---

## 1. 事实（本机只读实测，可复跑）

取证脚本：`research/arch-build-20261107/probe_collision_20261107.py`（只读 `D:/TSP/data` 与契约产物，不写任何文件）。全部数字由 `backend/.venv/Scripts/python.exe` 跑出。

### 1.1 活配置的 19 个引用名（清单 `summary.live_config` 的 primary 层）

```
boll_lower  boll_upper  close      high       high_60d   limit_down_price
limit_up_price  low_60d  ma10      ma20       ma5        ma60
macd_dea    macd_dif    open       raw_close  raw_high   raw_low   vol_ratio_5d
```

清单分层：`records 93 = primary 79 + companion 14`，`sources 22`；19 个去重 id。

**19 名按盘上事实三分**（这张分解是后面所有判据的依据）：

| 类 | 数 | id | `RegistryFacts.kind` | `status` | `lang` |
| --- | --- | --- | --- | --- | --- |
| 撞名（spec 命中的 custom） | **4** | `boll_lower` `boll_upper` `ma20` `ma60` | `custom` | `None` | `dsl` |
| 列回落（无 spec 无定义，命中列全集） | 14 | `close` `high` `high_60d` `limit_down_price` `limit_up_price` `low_60d` `ma10` `ma5` `macd_dea` `macd_dif` `open` `raw_close` `raw_high` `raw_low` | `base` | `None` | `None` |
| 注册 base（有 spec，kind=base） | 1 | `vol_ratio_5d` | `base` | `None` | `dsl` |
| 合计 | **19** | | | | |

`lang=None` 正好标出「不是 spec、是靠列全集回落的」那 14 个 —— 这是区分两类 base 的唯一盘上特征。

### 1.2 两个集合的实际规模与包含关系

| 集合 | 规模 | 说明 |
| --- | --- | --- |
| `gate._column_universe()` | **68** | `dsl.BASE_COLUMNS`(9) ∪ `pipeline` 六个列集合 |
| `custom_signals.ALLOWED_FIELDS` | **54** | §7.10.3 N1 说的「基础指标列」 |
| `ALLOWED_FIELDS − _column_universe()` | **0** | **AF ⊆ U**：N1 的列面一个都没漏在闸门的列全集之外 |
| `_column_universe() − ALLOWED_FIELDS` | **14** | `_boll_std` `_daily_pct` `_ema12` `_ema26` `_kdj_hn` `_kdj_ln` `_tr` `_vol_ma5`（8 个 `_` 暂存列）+ `date` `float_shares` `name` `quote_ts` `symbol` `total_shares`（6 个身份/辅助列） |

**`U = AF ∪ 14` 是精确等式**（不是近似）。这条对条款的意义：面闭合判据用 `_column_universe()` 还是 `ALLOWED_FIELDS`，对 19 个活配置名**完全等价**（19/19 同时属于两者）；差异只在「那 14 个能不能被声明成列面」。见 §2.4。

### 1.3 闸门今天的判定（`shadow=True`，不抛异常）

| 调用 | 结果 |
| --- | --- |
| `assert_factors_usable(19 名, "production")` | `ok=False`，**blocked = 4 条 FS01**：`boll_lower` `boll_upper` `ma20` `ma60`（`status` 均为 `null`） |
| `assert_factors_usable(19 名, "research")` | 同样 **4 条 FS01** |
| `assert_factors_usable(19 名, "research", allow_non_active=True)` | `ok=True`，`non_active = 那 4 名` |
| `assert_factors_usable(19 名, "diagnostic")` | `ok=True`，`non_active = 那 4 名` |
| `unknown` / `historical_only` | 全模式 `()` / `False` |

与 21:0x 的 B2 取证 `research/gate-core-20261107/EVIDENCE_gate_realdata.json` **逐项相同**（4 名、同码、同序），说明 22:5x 复跑没有漂移。

### 1.4 撞名的机械成因（读码，不是推演）

`gate.py:229–:233`（`RegistryFacts.facts`）：

```python
if spec is None and definition is None:
    if factor_id in _column_universe():
        return FactorFacts(factor_id=factor_id, registered=True, kind="base")
    return FactorFacts(factor_id=factor_id, registered=False)
kind = spec.kind if spec is not None else ...
```

**spec 存在时列分支永远不被求值** → 名字命中注册表就走因子面；`status=None` → `_judge` 按 `draft` 处理（`gate.py:344`）→ production 给 `FS01`（`:349`）。即：**闸门按名判，是 factor-first**。

### 1.5 现签名里没有承载位置

`inspect.signature` 实测（节选）：

```
(factor_ids, mode, *, allow_non_active=False, allow_retired=False,
 require_status=True, shadow=False, entry=None, facts=None) -> GateReport
has_namespace: False
```

`factor_ids` 只是一个扁平字符串集合 —— **闸门拿不到「这个引用来自列面还是因子面」这件事**，而这件事只有调用方知道（`custom_signals.py:103` 的 `allowed_fields()` 是 `ALLOWED_FIELDS | 因子 id | 字符串扩展字段` 的并集，集合语义本身不表达先后 —— §7.10.3 N1 自己已经指出这一点并要求「实现必须显式排序」）。

## 2. 裁定与条款正文

### 2.1 这不是契约空白，结论早就写好了，缺的是承载

| 已有条款 | 已经说了什么 | 缺什么 |
| --- | --- | --- |
| §7.10.3 **N2** | 「`namespace=column` 的引用**不得**因『名字恰好等于某因子 id』而判 status」，并点名 4 个冲突名 | 只在**清单生成器**一侧可执行；闸门没有入参，说不出「这条是 column」 |
| §7.10.6 **F-A24** | 4 处必须 `ref_namespace=column`，另出 `both_collision=true` 伴生记录 | 同上（判清单，不判闸门） |
| §7.10.6 **F-A29** | 「构造『因子 id 恰与基础列同名』的信号：`verdict` 必须 `allow`（column），运行结果与未接闸门时**逐位相同**」 | 同上 |
| §7.8.3 第一行 | base / virtual **不 gate** | 闸门只在「无 spec」时才把 id 当 base，有 spec 就不当 |

**所以本条款不新增裁定**，只做一件事：给 N2 的结论一个**可执行的入参**，让它在闸门里也能判。写法与 §7.16 开头那句「本节不新增裁定，只把……落到可测的输入输出上」同构。

### 2.2 裁定：命名面由**调用方声明**，闸门按面判定（派单二选一的 **(b)**）

```python
assert_factors_usable(
    factor_ids: Iterable[str] | str,
    mode: str,
    *,
    allow_non_active: bool = False,
    allow_retired: bool = False,
    require_status: bool = True,
    shadow: bool = False,
    entry: str | None = None,
    facts: FactsSource | None = None,
    namespace: str | Mapping[str, str] = "factor",   # ← 唯一新增；keyword-only、带缺省
) -> GateReport
```

- **位置参数一个不动**（`factor_ids, mode` 顺序与 §7.7.2 `:908` / §7.16.3 `:1634` 逐字相同），新参数**追加在最后**且 keyword-only ⇒ **按 §7.7.3 接线后的 6 个接入点（表 5 行；策略保存/更新占 `POST /config` 与 `PATCH /config` 两个路由）与 `backend/tests/test_factor_gate.py` 的 7 个调用行 0 改动**。一处必须说清的现状：今日 `backend/app` 内 `assert_factors_usable(` 的生产调用点为 **0**（`grep` 只命中 `gate.py:24` 文件头注释与 `:435` 的 `def`），闸门尚未接线 —— 本文件凡说「调用点」，一律指**按 §7.7.3 接线后的**接入点，不是盘上已有的调用。
- **默认 `"factor"` = 今日行为**（fail-closed 方向的缺省：不声明就按因子面判，宁可误拦不可漏放）。

### 2.3 语义（S1–S6，机械可判）

| 码 | 规则 |
| --- | --- |
| **S1** | `namespace="factor"`（含缺省）：逐 id 判定与今日**完全相同**，`blocked` 集合逐 id 相等 |
| **S2** | `namespace="column"`：该 id 按 §7.8.3 第一行 **base** 处理 —— 不判 `status`（无 FS01）、不判 alias（无 FS03/FS06）、不判 `lang`（无 FS05）；`non_active` 不记（status 不适用），`resolved` 仍取 `fact.factor_id`（不改 FS04 的现有行为） |
| **S3** | Mapping 形态：逐 id 取面；**缺键即 `ValueError`**（不静默补齐 —— continue 一个「忘了声明的列」就等于继续误拦 4 条）；多余键忽略（不影响任何判定） |
| **S4** | **面闭合**：`namespace="column"` 且 id ∉ `_column_universe()` → **`FS02`**（fail-closed；不静默 allow，也不退化成 FS01）。这条堵住了「把 draft 因子改名成列名来免检」的唯一入口 |
| **S5** | 取值域 `{"factor", "column"}`；域外（含 `"base"` / `"virtual"` / `"COLUMN"` / `None`）→ **`ValueError`**，不进 `blocked`。`base`/`virtual` 是 §7.8.3 的 **kind**，不是 namespace —— 允许传 kind 会让两面语义混成一锅 |
| **S6** | 非 column 面 id 的判定**完全不动**；`detail` 形状不动（§7.16.4 的键集合固定，S4 的区分靠 `message` 文本，不新增键） |

### 2.4 面闭合用哪个集合：`_column_universe()`（68），不用 `ALLOWED_FIELDS`（54）

理由三条：

1. **同源**：闸门今天判「未登记」用的就是这个集合（`gate.py:230`），再引入第二个集合就是两个口径；
2. **不放宽**：`U = AF ∪ 14` 是精确等式（§1.2），那 14 个本来就以 base 身份免 gate，S4 用 68 只是把「今天已经免检的」显式承认下来，**没有新增任何免检面**；
3. **可收窄**：日后若按 R10 §5 的建议把 `_` 暂存列与身份列移出（68 → 54），S4 自动跟着收窄，因为判据绑常量、不绑数字。

代价写明：`symbol` / `date` 这类身份列也能被声明成列面而免检 —— 与今天的行为一致，不是本条款引入的。

### 2.5 为什么否决 (a)「消费入口 column-first」

派单的 (a) 是「同名先按 column 判、不 gate」。它的实现只有一种写法：改 `RegistryFacts.facts` 的分支顺序（先查 `_column_universe()`，命中就返回 base）。三条代价：

1. **全局且不可关闭**：任何一个名叫 `ma20` 的 draft 因子从此在**任何入口**都不可 gate，且没有任何提示。因子面的 FS01 对这类名字永久失效。
2. **把「谁在用」压成「名字巧合」**：`namespace=column` 的正确依据是**引用来自列面**（`field:X` 命中 `ALLOWED_FIELDS`），不是**名字恰好也叫列**。两者在 4 个冲突名上重合，在其他名字上不重合。今天重合，明天有人造一个 `ma20` = 「20 日均线的变化率」，它会静默继承列的免检身份 —— 而 §7.8.4 的硬规则正是「误放行比判死更危险」。
3. **判据不可分**：`F-A29` 要求「同名因子 id 的信号 → verdict 必须 allow」，§7.8.4 要求「Provider 注册无 status → FS01」。column-first 让同一次调用两条都「成立」，实际靠的是分支顺序 —— 那不是判据，是巧合。

而 (b) 的代价也是真的，写在这里：§7.7.3 的 6 个接入点必须逐个传 `namespace`，**漏传不报错**，只会回到 fail-closed 的因子面 → 那 4 条重新出现。这不是缺陷，是**可探测性**：L1 影子里「block 集合逐 id 相等」（§7.10.4）会立刻把漏传变成一条可指认的差异。反过来，column-first 的漏配是**静默的**（7 条信号恒 `null`、不报错、不告警，§7.10.5 已写明）。

## 3. 判据（新编号，`F-A43` 起；不重号）

编号核对：v0.10 全文 `F-A1`–`F-A42` **42 个唯一号全部占用**（含 `F-A42-1…6` 子号），故从 `F-A43` 起。

### 3.1 `F-A43` 命名面入参存在且 fail-closed

| # | 判据 | 度量 |
| --- | --- | --- |
| `F-A43-1` | 签名 | `inspect.signature` 逐参数断言：前两参数仍是 `factor_ids, mode`（POSITIONAL_OR_KEYWORD，无缺省），`namespace` 是 **KEYWORD_ONLY** 且缺省 `"factor"`；原有 6 个 keyword-only 参数名与缺省值一字不改 |
| `F-A43-2` | 取值域 | 传 `"base"` / `"virtual"` / `"COLUMN"` / `None` 各一次 → **`ValueError`**，且 `GateReport` 不产生、`blocked` 不进 |
| `F-A43-3` | Mapping 覆盖 | `namespace={}` 与 19 名一起传 → `ValueError`（缺 19 键）；少 1 键 → `ValueError`；多 1 个无关键 → 正常返回，结论与不多时相同 |
| `F-A43-4` | 面闭合 | `namespace="column"` 传 `uf_vol60`（已登记因子、不在列全集）→ **`FS02`**；传 `close`（列全集内）→ 不拦 |

### 3.2 `F-A44` 撞名在闸门上双面可判（本条核心）

**样本定义（派单的「19 名正样本、4 名负样本」在这里被解释成两面，理由见 §3.4）**

| # | 判据 | 度量 |
| --- | --- | --- |
| `F-A44-1` | **正样本：19 名全过** | `assert_factors_usable(19 名, "production", namespace="column")` → `ok=True`、`blocked=()`、`non_active=()`、`unknown=()`、`mode="production"` |
| `F-A44-2` | **负样本：4 名仍拒** | 同 4 名，`namespace="factor"`（缺省）`mode="production"` → `blocked` 逐条为 `(id, None, "FS01")`，集合恰为 `{boll_lower, boll_upper, ma20, ma60}`；`research` 同 4 条 `FS01` |
| `F-A44-3` | 边界不变：另外 15 名 | 15 名的 `blocked` / `non_active` / `unknown` 与接线前逐 id 相同（14 个仍靠列回落、`vol_ratio_5d` 仍是注册 base）；**本次改动只应改变这 4 个 id 的结论，多改一个即失败** |
| `F-A44-4` | 数值不变 | 7 条活信号（`boll_breakdown_lower`、`boll_breakout_upper`、`ma20_breakdown`、`ma20_breakout`、`ma_dead_5_20`、`ma_golden_20_60`、`ma_golden_5_20`）运行结果与未接闸门时 **`max_abs_diff == 0`**（与 `F-A29` 同口径，不另立门槛） |

### 3.3 `F-A45` 缺省即今日（不回归）

| # | 判据 | 度量 |
| --- | --- | --- |
| `F-A45-1` | 不传 `namespace` | 19 名 `production` → `blocked` 集合 == §1.3 实测的 4 名；`research` / `research+allow_non_active` / `diagnostic` 三组的 `ok`、`non_active`、`unknown` 逐项等于 §1.3 表 |
| `F-A45-2` | 现有测试 0 改动 | `backend/tests/test_factor_gate.py` 一个字不改，全部通过（今日 `test_factor_gate.py` 7 个调用行均不传新参数；`backend/app` 侧 0 个生产调用点，无回归面） |

### 3.4 关于「19 正 / 4 负」的一处消歧（必须写，否则要求自相矛盾）

派单写「19 名做正样本、4 名做负样本」，但 **4 ⊂ 19** —— 若「正样本」指「必须通过」、「负样本」指「必须被拒」，同一个名字就要同时通过与被拒，除非**两面分开**。故本条款按下列唯一自洽读法落地：

- **正样本** = 19 名在 **column 面**（`namespace="column"`）必须全过（`F-A44-1`）；
- **负样本** = 同 4 名在 **factor 面**（缺省 `namespace="factor"`）必须仍拒（`F-A44-2`）。

两种读法若真有分歧（例如「负样本」原意是「4 名必须在某处被显式标记」），替代实现是给 `GateReport` 加撞名可见性字段 —— **本条款不做**，因为 `GateReport` 的六字段在 §7.7.2 `:909` 是写死的，扩字段属于另一条判据变更；撞名的可见性已由 `F-A24` 的 `both_collision=true` 伴生记录承担。

## 4. 对派单四个必答项的逐条回答

### 4.1 函数签名是否变？→ **变**（尾部追加 1 个 keyword-only 带缺省参数）

- 变的部分：`namespace: str | Mapping[str, str] = "factor"`，追加在 `facts` 之后。
- 不变的部分：位置参数顺序、全部既有 keyword-only 参数名/缺省/语义。
- 兼容性：按 §7.7.3 接线后的 6 个接入点（表 5 行，策略保存/更新占 2 个路由）与 `test_factor_gate.py` 的 7 个调用行零改动。今日生产侧 0 个调用点，所以「现有调用点被破坏」这一风险当前为空集。

### 4.2 §7.4 允许面是否扩大？→ **不扩大**（这条要更正一处常见误读）

§7.4 是**幂等与 store 改动面**，它约束的是 `store.py`：§7.4.2 允许面表列的 11 个符号（`_NON_CONTENT_FIELDS`、`_GROUP_DEFAULT`、`_canonical`、`content_signature`、`is_same_content`、`_merge_for_write`、`resolve_status`、`is_unchanged_definition`、`upsert_definition`、`load_one`、以及 `register_definition` 的幂等跳过）**全部在 `store.py` 内**；§7.4.3 的五条未改面同样只谈 `store.py`。**`gate.py` 不在 §7.4 的任何一张表里** —— 它是 §7.7.2 要求的**新增模块**，改动面由 §7.7.2 / §7.16.3 管。

所以 `namespace` 入参**不触碰 §7.4 允许面**，谈不上扩大。真正需要改的是两处**签名复述句**：

| 条款 | 现文（v0.11 行号） | v0.12 应补 |
| --- | --- | --- |
| §7.7.2 `:908` | ``新增 `app/factors/gate.py#assert_factors_usable(factor_ids, mode, *, allow_non_active=False, allow_retired=False) -> GateReport` `` | 句尾加「（v0.12 追加 keyword-only `namespace: str \| Mapping[str, str] = "factor"`，见 §7.17）」 |
| §7.16.3 `:1634` | `` `assert_factors_usable(factor_ids, mode, *, require_status=True)` 是 §7.7.5 / §7.8.4 已定的入口签名，本节不改其语义 `` | 同上加一句；「不改其语义」对新参数不适用，须明写「新参数不改变任何既有 id 在缺省面的结论」 |

数据层改动：**零**。`FactorSpec` 21 字段不变，不需要新字段承载 namespace（它是一次调用的入参，不是因子的属性）。

### 4.3 新断言编号 → `F-A43` / `F-A44` / `F-A45`（含 `-1…-4` 子号，见 §3）

不重号理由：`F-A1`–`F-A42` 在 v0.10 全部占用（实测 42 个唯一号）；本条款不修改任何既有编号，`F-A29` / `F-A24` / `F-A42-6` 保持原义。

### 4.4 验收样本 → 19 名正样本 + 4 名负样本（见 §3.2 / §3.4）

样本来源是**盘上实测的 19 名**，不是构造的：`probe_collision_20261107.py` 每次跑都从 `summary.live_config` 的 primary 层重新取，并把「4 名拦住」作为自断言。样本会随活配置变化 —— 验收时应重跑取证脚本取当时的 19 名，**不要把手抄的 19 个名字写进测试常量**（活配置一改，测试就变成在验历史）。

## 5. 与既有条款的关系（一处对 N1 字面的收窄解释，明写）

§7.10.3 **N1** 原文有一句：「命中 → `namespace=column`，**不进入因子闸门**」。本条款让 column 面的 id **进入**闸门（然后直接 allow），与这句字面不同，理由三条：

1. **分类逻辑不该复制到每个入口**。§7.7.2 的裁定是「闸门放在消费入口、单一实现、禁止各入口各写一遍」。让调用方先过滤掉列、只把因子丢进闸门，等于把「什么算列」这条判定复制到 6 个接入点 —— 与「单一实现」直接冲突。
2. **拆成两次调用会断掉 FS04**。§7.16.6 的 `FS04`（同一策略内 alias 与 canonical 并存）必须看**整组** id。先按面拆成两次调用，跨面的双 id 就再也检不出来。
3. **「进入但不判」与「不进入」在结论上等价，在可观测性上更好**：闸门可以如实报告「这个 id 我按列面放过了」，而「根本没进来」在报告里什么都不留。

因此本条款把 N1 的落点写成两段：**解析（谁算列）归消费侧**（N1 原文照旧，`custom_signals.allowed_fields()` 的并集必须显式排序）；**判定（按面给结论）归闸门**（本节新增的 `namespace`）。N1 的结论不变，只是把它拆成「谁决定」与「谁执行」。

`F-A24` / `F-A29` 不需要改：前者判清单的 `ref_namespace`，后者判数值不变，两者都仍然成立且现在**第一次可以在闸门层被执行**。

## 6. 实现与接线约束（给系统开发工程师）

### 6.1 改动面（只此三处）

| 文件 | 改动 | 限制 |
| --- | --- | --- |
| `backend/app/factors/gate.py` | `assert_factors_usable` 加 `namespace` 参数；新增面解析（S1–S5）；`_judge` 增加「面」入参或在调用前短路为 base | 不改 `GateReport` 六字段；不改 `FS01`–`FS06`/`FS10` 任何码的含义；不改 `_column_universe()` 的内容 |
| `backend/app/strategy/custom_signals.py` | 解析 `field:X` 时**先列后因子**（N1 的显式排序），把逐 id 的 `namespace` 传给闸门 | 不改 `ALLOWED_FIELDS` 本身；不改 `materialize_factor_columns` 的补算行为 |
| 6 个接入点（§7.7.3 表 5 行；策略保存/更新占 2 个路由） | 传 `namespace` | `mode` 一个都不改；`shadow` 在 L1 期间保持 True |

### 6.2 不许做的四件事

1. 不许把 `namespace` 做成**全局开关**或环境变量 —— 面是每次调用的事实，不是部署配置。
2. 不许在 `RegistryFacts.facts` 里按名字改分支顺序（那就是 §2.5 的 (a)）。
3. 不许让 `namespace="column"` 对未登记名字**静默 allow**（S4 必须是 `FS02`）。
4. 不许用 `stability` / `kind` 反推面（§7.8.4 的硬规则同样适用于面）。

### 6.3 L1 影子的验收信号

接线后先跑 L1（只报告不阻断），预期：`block` 集合从 4 条降到 **0 条**（19 名全部按列面放行）。若仍是 4 条，第一嫌疑是调用点漏传 `namespace`（§2.5 已把这条设计成可探测），不是条款失效。

### 6.4 并入点（v0.12）

- 位置：v0.11 的 §7.16.7 判据表末行 `:1685` 之后、`## 8. 改动性质总表`（`:1687`）之前，新增 `### 7.17`。
- v0.12 = v0.11 + §7.17 一节 + §7.7.2 / §7.16.3 两处签名复述句各加一句 + footer 版本簿记。**除此之外不动任何字节。**

## 7. 未确证 / 未做

**未确证**

- 「19 名在 column 面全过」是**按实现逻辑推出来的**，不是跑出来的：今天的 `gate.py` 没有 `namespace` 入参，无法执行这个调用。能跑的是它的等价物（`shadow=True` + 把 4 名从输入集合里剔除，得到 `ok=True`），但**剔除不等于声明** —— `F-A44-1` 必须等实现落地才算实测。
- `custom_signals` 那一侧「先列后因子」我**只读了 `allowed_fields()` 的并集事实（`:103`），没有读遍 6 个接入点**的表达式构造路径，所以「解析侧要改哪几行」本文件不写死。
- 7 条活信号的 `max_abs_diff == 0`（`F-A44-4`）本轮**未实跑**，它是接线后的验收项，不是今天的实测。
- 「4 名在 pack 里 `status=None`」是从 `RegistryFacts` 读出来的；**pack 的 JSON 文件本体我没有逐个打开核对**（`D:/TSP/data` 是可写数据目录，我只读）。

**未做**

- 未改 `gate.py`、未改 `custom_signals.py`、未改任何测试（实现排系统开发工程师）。
- 未改 v0.10 / v0.11 任何字节（`namespace` 条款不在 v0.11 里）。
- 未提交、未部署。

## 8. 一句话

**拦的不是 4 个名字，是「闸门不知道这条引用来自哪个面」。** 补一个 keyword-only、带缺省、fail-closed 的 `namespace` 入参，4 名在列面全过、在因子面仍拒，15 名一个不动，`F-A43`–`F-A45` 把这三件事分别钉住。

## 9. 本文件自身

- 路径：`docs/architecture/CLAUSE_NAMESPACE_COLLISION_20261107.md`（R11 §7 与 §9 转交栏指向此文件名）。
- 性质：**条款草案，不参与任何判据绑定**；并入 v0.12 的 §7.17 之后才成为契约文本。在此之前，按 `F-A43`–`F-A45` 判实现，判到的是「未实现」而非「不合规」。
- 四元组（size / 行 / 全文 sha256）**不由本文件自指**，见交付回执；复算口径与 R10 §1.2 / R11 §2 相同（`sha256` 全文，行数按 `\n` 计数）。
- 取证脚本：`research/arch-build-20261107/probe_collision_20261107.py`（只读，不写盘；把「4 名被拦」作为自断言，失败即退出非 0）。
- 复核记录（2026-11-07 23:1x，架构师本机重跑）：`records 93 = primary 79 + companion 14`、`sources 22`、19 个去重 id；`_column_universe()` = **68**（`BASE_COLUMNS` 9）；`ALLOWED_FIELDS` = **54**；`production` / `research` 各拦 **4**（`boll_lower` `boll_upper` `ma20` `ma60`，全 `FS01`）；`research+allow_non_active` 与 `diagnostic` 均 `ok=True`、`non_active=4`；`inspect.signature` 无 `namespace`。
