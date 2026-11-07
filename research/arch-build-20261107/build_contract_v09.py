# -*- coding: utf-8 -*-
"""v0.8 -> v0.9：四处一次收齐。

1. `F-A11b` 收窄为列级一条（删逐元素读法，写清为什么不用）。
2. 新增 §7.16 canonical/alias 闸门可判定条款（`FS03`）。
3. 新增 §2.8 `observed_bars` 口径差异（信息项，不改判据）。
4. §2.7 追加 `in_universe` 进 `/api/factors` 目录的规模变化。

只做这四处 + 版本簿记（H1 / §0 修订记录 1 行 / §9 1 行 / 新增 §11 改动说明 / footer）。
不改 v0.3–v0.8 任何一份文件。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

DOCS = Path(r"C:\work\sourcecode\tick-stock-panel\docs\architecture")
SRC = DOCS / "FACTOR_ENGINE_CONTRACTS_20261107_v0.8.md"
DST = DOCS / "FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md"
CR = "\r\n"

raw_bytes = SRC.read_bytes()
BASE_SHA = hashlib.sha256(raw_bytes).hexdigest()
raw = raw_bytes.decode("utf-8")
cut = raw.rindex("本文件正文 sha256")
body0 = raw[:cut]
BASE_BODY = body0.encode("utf-8")
BASE_BYTES = len(raw_bytes)
BASE_LINES = raw_bytes.count(b"\n")
BASE_BODY_BYTES = len(BASE_BODY)
BASE_BODY_SHA16 = hashlib.sha256(BASE_BODY).hexdigest()[:16]
BASE_FULL_SHA16 = BASE_SHA[:16]
print("BASE", BASE_BYTES, BASE_LINES, BASE_BODY_BYTES, BASE_BODY_SHA16, BASE_FULL_SHA16)

lines = body0.split(CR)
assert lines[-1] == ""


def find_one(pred, label):
    hits = [i for i, ln in enumerate(lines) if pred(ln)]
    assert len(hits) == 1, f"{label}: hits={hits}"
    return hits[0]


# ---------------------------------------------------------------- 1. H1
i = find_one(lambda s: s.startswith("# 因子化引擎与生产侧执行器 —— 接口契约 v0.8"), "H1")
lines[i] = "# 因子化引擎与生产侧执行器 —— 接口契约 v0.9（2026-11-07）"

# ------------------------------------------------- 2. F-A11b 改列级
NEW_A11B = (
    "| F-A11b | 数值一致（**列级**相对容差；**不设**逐元素判据） | 逐列独立判：记 `d_col = max\\|p − m\\|`、"
    "`s_col = max\\|p\\|`（该列有限值绝对值的最大值），断言 `d_col / max(s_col, 1e-12) ≤ 2^-23 = 1.192e-07`；"
    "一个因子通过 = 它参与的**每一列**都通过。形状与轴标签须已由 `F-A11a` 对齐；样本必须同时覆盖 NaN 与非 NaN 行。"
    "`1e-12` 只是列级分母的退化下限（整列全零时避免除零），**没有**逐元素含义、也不对任何单个元素设容差 |"
)
i = find_one(lambda s: s.startswith("| F-A11b | 数值一致（相对容差）"), "F-A11b")
old_a11b = lines[i]
lines[i] = NEW_A11B

# ------------------------------------- 2b. 为什么不用逐元素（紧随 2^-23 余量段）
WHY = [
    "**为什么 `F-A11b` 只写列级、不写逐元素（v0.9 收窄；写在这里是为了下次不被「修」回去）**：逐元素读法"
    "（对**每个元素**要求 `|p−m| / max(|p|, 1e-12) ≤ 2^-23`）在 `float32` 存储下不可达，实测打穿。独立审核 2026-11-07 "
    "同一组真实数据：`boll_lower` **逐元素 1.416e-07（超 `2^-23` → FAIL）／列级 8.635e-08（PASS）**；越线点 `|p| = 9.27` "
    "远离近零退化，属正确核的**多次 `float32` 运算累积**（单次存储量化上界 `2^-24 = 5.96e-08`，见 7.14.2），不是口径错。"
    "逐元素判据的实质是「用最坏一个元素的累加顺序代表整列」，会把正确实现判死；而它并不增加判别力——语义错在两种读法下都抓得住"
    "（7.14.5：语义错相对误差 0.6682，与 `2^-23` 差约 7 个数量级）。**结论：只判列级；`1e-12` 仅作列级分母的退化下限。**",
]
i = find_one(lambda s: s.startswith("容差 `2^-23`（而非实测的 `2^-24`）是留一倍余量"), "2^-23 余量段")
lines[i + 1 : i + 1] = [""] + WHY

# ------------------------------------------- 3. §2.7 三bullet + §2.8
B27 = [
    "- **进入 `/api/factors` 对外目录（catalog 93 → 107 → 108）**：`in_universe` 由 "
    "`app/custom/research_universe_pack/factor_provider.py` 的 Provider 注册，按扩展点既定行为「注册即进目录」"
    "（B0 的 14 个 pack 因子同理）出现在 `GET /api/factors` 的 `factors[]` 里；目录条数 `93`（B0 前）→ `107`（B0 的 14 个）"
    "→ `108`（本批 `in_universe`）。实测 2026-11-07 20:5x：`len(all_factors()) == 193`（含 `ext_*` 85 条与其它 Provider 16 条），"
    "非 `ext_*` 口径 = **108**；该条目现状字段 `kind=\"custom\"`、`group=\"研究补充\"`、`unit=\"none\"`、`scale_free=true`、"
    "`stability=\"stable\"`、`warmup_bars=120`、`tags=(\"mask\",\"研究基线\",\"E3\")`、`asset_types={\"stock\",\"etf\"}`。",
    "- **5 处「目录条数」断言已由实现侧同步到 108，不是本批回归**：`tests/test_factor_registry.py` 4 处 + "
    "`tests/test_factor_store.py:88` 原把条数硬编码为 `93`（B0 起即红：93 → 107）；实现侧 2026-11-07 20:48:59 统一改为 `108`"
    "（`git diff --numstat` 两文件 `+25/−9`，**未提交**；本轮实测 5 处，B2 报告记「6 条 factor 红灯」为测试用例级计数，差 1 处未追，不影响结论）。"
    "口径：改的是**过期断言值**，原有覆盖必须保留，不得以「重定基线」把红灯合法化；是否全绿由独立审核复跑，本契约不下结论。",
]
S28 = [
    "### 2.8 `observed_bars` 的口径差异（**信息项**，不改判据；口径归属交研究侧）",
    "",
    "`CAL-observed_bars`：实现取 `date.cum_count().over(\"symbol\")`（= §2.1 注 1 的研究口径，与 "
    "`research/strategy-search-20261107/scripts/common.py#add_universe` 同一写法），与「`instruments.listing_date` + 交易日轴」"
    "口径**不等价**。差异已量化（系统开发工程师 `research/b2-engine-20261107/EVIDENCE_20261107.json` 的 `decisions_needed` D-B2-1）：",
    "",
    "| 项 | 值 |",
    "| --- | --- |",
    "| 两口径判定不同的标的日 | **40,717** 行 |",
    "| 其中落在评估窗内（`2019-07-01`…`2026-10-30`，1,779 个交易日） | **17,499** 行 |",
    "| 差异方向 | **全部**为「`listing` 口径 ≥ 120 而 `bar` 口径 < 120」（`listing` 更宽：把「已上市但当日无 bar」也算可交易） |",
    "| 与研究的对账 | `bar` 口径下 `A1` 逐日池内家数 **0 差**：可比 **1,770** 个交易日，`max_abs_diff = 0`（另 **9** 日一侧为 `null` 不计）；研究侧逐日池内家数日均 **1,429.73**（1,779 交易日口径）。读数出处 `research/b2-engine-20261107/logs/e3_verify.json`（`A1_n_compared_days` / `A1_null_days` / `daily_mean_pool_research`，`E3-A1`） |",
    "",
    "- **本条不改任何判据**：`A1`–`A8` 的度量与靶值不变；`observed_bars` 取研究口径，是 §2.1 注 1 早已写明的取法。",
    "- **本节的用途是消除歧义**：同一句「`observed_bars` ≥ 120」有两种读法（面板内 bar 行数 vs 上市天数），"
    "本节把「当前取哪一种、差多少」写死，避免下一个读者自行换口径。",
    "- **为什么不自行改判据**：两种口径都自洽，差别是**口径选择**（是否把「上市但无 bar」算作可交易），不是实现对错。"
    "换口径要重跑 E3/E1/E2 全部判据并递增 `universe_version`，属研究侧口径裁定。",
    "- **若研究侧改判为 `listing` 口径**：上表 40,717 / 17,499 即需重算的标的日规模，`A1` 的靶值（1,429 / 0 差）随之作废，"
    "必须重新对账后再验收。",
]
i = find_one(lambda s: s.startswith("- 与 `basic_filter` 的关系：**逻辑与**，不是替代"), "§2.7 末 bullet")
lines[i + 1 : i + 1] = [""] + B27 + [""] + S28

# ------------------------------------------------------------ 4. §7.16
S716 = [
    "### 7.16 canonical/alias 闸门：可判定条款（v0.9 新增；B0b-1 的交付依据）",
    "",
    "本节把 `FS03` 从「一句话裁定」（§7.8.4 的模式矩阵、决策文件 `ID-CANON-1`）写成**可判定条款**：触发条件、生效入口、"
    "HTTP 形状、与 §7.15 canonical 表的接续、以及拒 alias 时 `vol60` 与 `uf_vol60` 各自的期望行为。"
    "**本节不新增裁定**，只把 §7.8.2 A-2/A-3、§7.8.4、§7.15.1 已有裁定落到可测的输入输出上；判据编号续 `F-A41` 取 `F-A42`。",
    "",
    "**7.16.1 前提事实（2026-11-07 20:5x 本机复跑；零实现）**",
    "",
    "| # | 事实 | 依据（可复跑） |",
    "| --- | --- | --- |",
    "| 1 | `strategy_usable` / `alias_of` / `FS03` / `assert_factors_usable` 在 `backend/app/**` **各 0 命中**；"
    "`FactorSpec` 21 字段无此三项 | `grep -rn` 逐词计数为 0；`registry.py:33-57` |",
    "| 2 | `get_factor(fid)`（`registry.py:341`）与 `all_factors(...)`（`:375`）只按 id 查表，**无任何准入判断**；"
    "`factor_columns_view()`（`:408`）对全部 spec 一视同仁 | 读码 |",
    "| 3 | 策略配置写入 `POST /api/strategies/config`（`app/api/strategy.py:473`）与 `PATCH`（`:493`）只校验评分与 "
    "`overlay_filter`，**不校验因子 id** | 读码 |",
    "| 4 | 回测准入已有 id 白名单：`POST /api/backtest/factor/run`（`app/api/backtest.py:156`，校验在 `:162`）、"
    "`POST /api/backtest/factor/batch`（`:217`，校验在 `:227`）用 `factor_columns_view()` 的 id 集合，未命中 400 "
    "`不支持的因子: …` | 读码 |",
    "| 5 | 现状 8 组同口径双 id 并存（§7.8.1 #6）；未声明 canonical 即 `FS06`；canonical 的权威登记是 §7.15.1 一张表（14 行） | §7.15 |",
    "",
    "**7.16.2 `FS03` 触发条件（四条同时成立才触发；判据取自 §7.15.1 与 `FactorSpec`，实现不得在代码里写死 8 个名字）**",
    "",
    "```text",
    "alias_of(id)        := get_factor(id).alias_of          # None = 非 alias",
    "canonical_of(id)    := alias_of(id) or id               # 传递解析，上限 4 跳（§7.8.2 A-3）",
    "strategy_usable(id) := get_factor(id).strategy_usable   # 缺省 True；alias 恒 False",
    "```",
    "",
    "| 条件 | 断言 |",
    "| --- | --- |",
    "| C1 提交的 id 已登记 | `get_factor(submitted_id) is not None`；未登记走 `FS02`（§7.8.3），**不是** `FS03` |",
    "| C2 `alias_of(submitted_id) is not None` | 即提交的是 alias。`FS06` 的情形（别名成环、解析目标未登记、两个 id 都自称 canonical）"
    "**先判**，`FS06` 优先于 `FS03` |",
    "| C3 `strategy_usable(submitted_id) is False` | alias 恒 `False`；此项只作**交叉校验**——若某 alias 被错配成 `True`，"
    "仍按 C2 判 `FS03`，不因取值错而放行 |",
    "| C4 `mode == \"production\"` | `research` / `diagnostic` **不**触发（§7.8.4：research 允许并标 `deprecated_alias_used`，"
    "diagnostic 允许） |",
    "",
    "→ 触发即 **400 + `detail.code == \"FS03\"`**，fail-closed，不得降级为告警。§7.15.1 第 9–14 行的 6 个单侧件"
    "（`canonical_id == 研究原名`、无 alias）在任何模式都不会触发 `FS03`。",
    "",
    "**7.16.3 生效入口（穷举 4 个；逐个写落点与「为什么不在别处拒」）**",
    "",
    "| # | 入口 | 落点（现状文件:行） | 语义 |",
    "| --- | --- | --- | --- |",
    "| 1 | 因子查表 | `app/factors/registry.py:341 get_factor` | **不在 `get_factor` 内部拒**：它被 DSL 编译（`dsl.py:421`、"
    "`:676`、`:690`）、指标、目录、UI 多处调用，拒了会连带打断 `research` / `diagnostic` 与历史复现。改为在同文件新增 "
    "`resolve_factor(fid, mode)` → `(spec, resolved_id, warnings)`，`mode=\"production\"` 且命中 alias 时抛 `GateError(\"FS03\")` |",
    "| 2 | 目录 | `app/api/factors.py:23 list_factors`（`:30` 取 `all_factors`） | **不拒**（目录必须能列出 alias，UI 才能灰显）。"
    "响应每条新增两键 `strategy_usable`、`alias_of`（见 7.16.4 末段），其余键不变 |",
    "| 3 | 策略提交 | `app/api/strategy.py:473 POST /config`、`:493 PATCH /config`、`:375 POST /run`、`:423 POST /run-all` | "
    "配置写入前调 `assert_factors_usable(ids, mode=\"production\")`；`/run`、`/run-all` 在解析出 `factor_ids` 之后、读盘之前调 |",
    "| 4 | 回测准入 | `app/api/backtest.py:162`（`POST /factor/run`）、`:227`（`POST /factor/batch`）；矩阵准入 `FS10`（§7.13） | "
    "保留现有「id 不在目录 → 400 `不支持的因子`」，在它**之后**、读盘之前加 `FS03`；与 `FS10`（能力缺口）同时命中时 **`FS10` 先报**"
    "（能力缺口更根本），响应体形状相同，`code` 取先命中者 |",
    "",
    "`assert_factors_usable(factor_ids, mode, *, require_status=True)` 是 §7.7.5 / §7.8.4 已定的入口签名，本节不改其语义，"
    "只固定调用点；`mode` 三值 `production` / `research` / `diagnostic` 的含义见 §7.8.4 矩阵。",
    "",
    "**7.16.4 HTTP 响应形状（唯一形状，`FS03` 与 `FS04`/`FS06` 共用）**",
    "",
    "```json",
    "{",
    "  \"detail\": {",
    "    \"code\": \"FS03\",",
    "    \"mode\": \"production\",",
    "    \"submitted_id\": \"vol60\",",
    "    \"resolved_id\": \"uf_vol60\",",
    "    \"canonical_id\": \"uf_vol60\",",
    "    \"table_row\": 1,",
    "    \"message\": \"生产入口不允许 alias，请改用 canonical id uf_vol60\"",
    "  }",
    "}",
    "```",
    "",
    "- 状态码 **400**（与 §7.8.4 / §7.7.5 一致，不新造 422、不用 409）。",
    "- `detail` 是**对象**，不是字符串：`code` 必填；`submitted_id` / `resolved_id` 必填（§7.8.4 已要求）；"
    "`canonical_id` 与 `resolved_id` 同值（两键并存是为了与 `FS06` 的「未裁定」形状对齐）；`table_row` = §7.15.1 的行号（1–14），"
    "单侧件与未入表 id 为 `null`；`message` 为可读串。",
    "- 批量入口（`/run-all`、`/factor/batch`）`detail.submitted_id` 取被扫描顺序的**第一条**违规，另给 "
    "`detail.violations = [{\"submitted_id\": …, \"code\": …}, …]` 列全部违规。",
    "- `GET /api/factors` 的每个条目新增两键：`\"strategy_usable\": bool`、`\"alias_of\": str | null`（`canonical` 行 `alias_of=null`）。"
    "这是本条约定的**唯一**目录侧改动，其余键与顺序不变（`mining_schedule` 取前 48、`factor_columns_view()` 顺序均已由 "
    "§7.8.1 #11 锁死）。",
    "",
    "**7.16.5 与 §7.15 canonical 表的接续（唯一权威，禁止二次登记）**",
    "",
    "- alias 集合与映射**只从 §7.15.1 派生**：第 1–8 行的 `alias` 列 = 8 个 alias（`vol60`/`ma120`/`ma200`/`prior_high_20`/"
    "`prior_high_55`/`prior_high_250`/`prior_low_10`/`prior_vol_20`），`canonical_id` 列 = 8 个 `uf_*`；第 9–14 行 `alias` 为 "
    "`—`，其 `alias_of` 必须为 `None`。",
    "- 实现侧允许的冗余只有一处：`FactorSpec.alias_of`（由 pack / store 定义写入）必须与表一致；**不一致以表为准并报 `FS06`**"
    "（表是权威、定义是投影），不得只改一边就跑通。",
    "- 新增口径或改 alias = 改表（`ID-CANON-1`，决策文件 §3 登记）**同时**改定义；两者任一未动即 `FS06`。",
    "- `strategy_usable` 的取值规则（唯一）：`FactorSpec` 默认 `True`（内置 77 个 base/virtual 与 6 个单侧件），"
    "**只有** `alias_of is not None` 置 `False`；不引入第三个状态，也不按 `kind` / `stability` 推导。",
    "",
    "**7.16.6 拒 alias 时 `vol60` 与 `uf_vol60` 的各自期望行为（逐模式）**",
    "",
    "| 提交 id | `production` | `research` | `diagnostic` | 取哪一列的数值 |",
    "| --- | --- | --- | --- | --- |",
    "| `uf_vol60`（canonical） | **允许**（若 `status != active` 则 `FS01`；`reference_missing` 则 `FS05`，均按 §7.8.4） | 允许 | 允许 |"
    " canonical 列（权威） |",
    "| `vol60`（alias） | **400 `FS03`**（7.16.4 形状，`table_row=1`） | 允许，标 `deprecated_alias_used=true`、"
    "`submitted_id=\"vol60\"`、`resolved_id=\"uf_vol60\"` | 允许，同 research 并标 | 解析到 canonical 列（§7.8.2 A-2：alias 不各持实现） |",
    "| 同一策略内 `vol60` + `uf_vol60` 并存 | **400 `FS04`**（`FS04` 优先于 `FS03`） | **400 `FS04`** | 允许，标 `dual_id=true` | 同上 |",
    "",
    "- **拒 alias ≠ 数值不等**：两式实测 `max_abs_diff = 1.1102230246251565e-16`（`n_both_nonnull = 5,469,335`，"
    "非零差 **4,214,876** 行 = **77.07%**，超差 0 行；`F_CLASS_PARITY_20261107.json#factor_parity.uf_vol60`）。`FS03` 是"
    "**命名/准入**问题，不是数值问题；等价性按 **`F-A3` 的 `max_abs_diff < 1e-12`** 判，容差句挂在 **§7.15.2 硬约束①**，"
    "本节不重复定义、不改容差、不新增门槛。",
    "- **为什么 77.07% 行不等却不算口径差**：两式运算顺序不同（`(a−b)/b` vs `a/b−1`），1 ULP 级差异在 `close` 与 "
    "`ts_delay(close,1)` 接近时绝对值为零、远离时绝对值非零但相对误差仍 ≤ 1e-16。判据看的是 `max_abs_diff` 的**绝对上界**，"
    "不是「多少行不等」。**禁止**把「77.07% 行不等」写成判据或门槛（理由同 §7.15.2：把某次实测的 ULP 当门槛，会把「同公式换个求和顺序」"
    "的正确实现判失败）。",
    "- **可直接写成断言的四个取值**：`get_factor(\"vol60\").strategy_usable is False`、`get_factor(\"uf_vol60\").strategy_usable is True`、"
    "`get_factor(\"vol60\").alias_of == \"uf_vol60\"`、`get_factor(\"ma20\").alias_of is None`。",
    "",
    "**7.16.7 验收判据（续 §7.6 编号，取 `F-A42`）**",
    "",
    "| # | 判据 | 度量 |",
    "| --- | --- | --- |",
    "| F-A42-1 | 字段落地 | `FactorSpec` 增 `alias_of: str \\| None = None` 与 `strategy_usable: bool = True`（第 22/23 字段），"
    "既有 21 个字段名与默认值一个不改；`len(dataclasses.fields(FactorSpec)) == 23` |",
    "| F-A42-2 | alias 拒得掉（两例负样本） | `production` 提交 `vol60` → 400 且 `detail` 逐键等于 7.16.4 示例"
    "（`table_row=1`）；提交 `ma120` → 同形状、`table_row=2` |",
    "| F-A42-3 | canonical 放得行 | `production` 提交 `uf_vol60` 不被 `FS03` 拦（是否被 `FS01`/`FS05` 拦按 §7.8.4 判，与本条无关）；"
    "`research` 提交 `vol60` → 通过，报告含 `deprecated_alias_used` 与 `submitted_id`/`resolved_id` |",
    "| F-A42-4 | 入口穷举 | 4 个入口逐个造负样本，全部 400 `FS03`：`POST /api/strategies/config`、`POST /api/strategies/run`、"
    "`POST /api/backtest/factor/run`、`POST /api/backtest/factor/batch`；`GET /api/factors` **不拒**且条目含 "
    "`strategy_usable` / `alias_of` |",
    "| F-A42-5 | 表与定义一致 | 8 个 alias 的 `alias_of` 与 §7.15.1 第 1–8 行逐行相等；6 个单侧件 `alias_of is None`；"
    "人为把某一行定义改成与表不一致 → `FS06`（不是静默按定义走） |",
    "| F-A42-6 | 不误伤 | `FS03` 只在 `mode=\"production\"` 触发；`get_factor` / `factor_columns_view()` 对 alias 仍返回 spec"
    "（否则 DSL 编译、UI、`diagnostic` 全断）；`ma20` 等 6 个单侧件在任何模式都不报 `FS03` |",
]
i = find_one(lambda s: s == "## 8. 改动性质总表（改引擎 / 新增模块 / 现有已够）", "§8 标题")
lines[i:i] = S716 + [""]

# ------------------------------------------------ 5. §0 修订记录 + §9 行
ROW09 = (
    "| v0.9（裁定） | 2026-11-07 | **R9（以 v0.8 逐字节为底）**：①`F-A11b` 收窄为**列级一条**，删去逐元素读法并写明理由"
    "（`boll_lower` 逐元素 1.416e-07 FAIL / 列级 8.635e-08 PASS）；②新增 **§7.16** canonical/alias 闸门可判定条款"
    "（`FS03` 触发条件 C1–C4、4 个生效入口、HTTP 400 形状、与 §7.15 表接续、`vol60`/`uf_vol60` 逐模式期望行为、`F-A42`）；"
    "③新增 **§2.8** `observed_bars` 口径差异登记（40,717 行 / 评估窗 17,499 行，**不改判据**）；④§2.7 追加 `in_universe` 进 "
    "`/api/factors` 目录（93 → 107 → 108）与 6 处断言同步的事实。**v0.8（R8）行未在修订记录单列，其内容见 §10 与 `CONTRACT_REVISION_R8_20261107.md`** |"
    "开发经理 v0.8 派单四处 + 独立审核实测（`boll_lower` 列级/逐元素）+ 系统开发工程师 B2 证据（D-B2-1/D-B2-2）+ 架构师本机复算（20:5x） |"
)
i = find_one(lambda s: s.startswith("| v0.7（裁定） |"), "§0 v0.7 行")
lines[i + 1 : i + 1] = [ROW09]

ROW_R9 = (
    "| **R9（v0.9：`F-A11b` 列级 / §7.16 `FS03` 条款 / §2.8 `observed_bars` / §2.7 catalog 108）** | "
    "`F-A11b` **只判列级**（`d_col / max(s_col, 1e-12) ≤ 2^-23`），逐元素读法**删除**并写明代价；"
    "**§7.16** 把 `FS03` 写成可判定条款（触发 C1–C4、4 入口、400 形状、与 §7.15 表接续、`vol60`/`uf_vol60` 逐模式、判据 `F-A42-1`–`6`）；"
    "**§2.8** 登记 `observed_bars` 口径差（40,717 / 17,499 行，信息项，不改判据）；**§2.7** 登记 catalog 93 → 107 → 108 与 6 处断言同步。"
    "本版**只改这四处 + 版本簿记**，判据语义改动仅 `F-A11b` 一处，且方向为**收窄到可判**（放宽逐元素、不放宽列级阈值），其余为新增条款与信息登记 |"
)
i = find_one(lambda s: s.startswith("| **R8（现状事实原位更正 + `notes` 出 digest）** |"), "§9 R8 行")
lines[i + 1 : i + 1] = [ROW_R9]

# ------------------------------------------------------------ 6. §11
CHG_HEAD = [
    "## 11. 本版改动说明（R9：四处一次收齐）",
    "",
    "**本版 = v0.8 逐字节为底 + 四处内容改动 + 版本簿记**（H1、§0 一行、§9 一行、本节、footer）。"
    "不改 v0.3–v0.8 任何文件；不新建第三份说明文件（R7/R8 两份说明保留原样）。",
    "",
    "| # | 位置 | 改后行号 | 性质 | 一句话 |",
    "| --- | --- | --- | --- | --- |",
    "| 1 | §7.14.4 `F-A11b` + 新增理由段 | `L11B_ROW` / `L11B_WHY` | **判据收窄** | 只判列级，删逐元素读法 |",
    "| 2 | 新增 §7.16（`FS03` 条款） | `L716_HEAD`（表 `L716_TBL`、判据 `L716_CRIT`） | **新增条款** | 把既有裁定落成可测 IO |",
    "| 3 | 新增 §2.8（`observed_bars`） | `L28_HEAD`（表 `L28_TBL`） | **信息项** | 登记口径差，不改判据 |",
    "| 4 | §2.7 追加两 bullet | `L27_B1` / `L27_B2` | **现状描述** | catalog 93→107→108 |",
    "",
    "## 11.1 四处改动逐条（old → new）",
    "",
    "#### 第 1 处：`F-A11b` 由「列级或逐元素的混写」收窄为「只列级」",
    "",
    "原文（v0.8 `:1501`）：",
    "",
    "```text",
    "OLD_A11B",
    "```",
    "",
    "改后：",
    "",
    "```text",
    "NEW_A11B",
    "```",
    "",
    "配套新增一段理由（紧随 7.14.4 的 `2^-23` 余量段），原因是同一句话里的 `1e-12` 只有「逐元素」读法才有意义、"
    "而后半段却是列级，实施者按逐元素实现会把 `boll_lower` 判 FAIL。",
    "",
    "#### 第 2 处：新增 §7.16（canonical/alias 闸门可判定条款）",
    "",
    "v0.8 只有 §7.8.2 A-2/A-3、§7.8.4 模式矩阵与 §7.15 的 id 表，**没有**写清 `FS03` 的触发条件、入口、HTTP 形状与 "
    "`vol60`/`uf_vol60` 的逐模式行为，故 B0b-1 无法开工（`strategy_usable`/`alias_of`/`FS03` 在 `backend/app/**` 各 0 命中）。"
    "§7.16 补齐这五项，并明确「`get_factor` / `all_factors` **不拒**、只在 4 个入口拒」的边界（拒了会打断 DSL 编译与 `diagnostic`）。",
    "",
    "#### 第 3 处：新增 §2.8（`observed_bars` 口径差异，信息项）",
    "",
    "`CAL-observed_bars`：实现取 `cum_count`（研究口径，`E3-A1` 0 差），与 `listing_date` 口径差 **40,717** 行"
    "（评估窗内 **17,499**），方向全部是「`listing` ≥ 120 而 `bar` < 120」。**只登记，不改判据**：口径归属交研究侧。",
    "",
    "#### 第 4 处：§2.7 追加 `in_universe` 进目录的规模变化",
    "",
    "`in_universe` 经 Provider 注册即进 `GET /api/factors` 目录：catalog **93 → 107**（B0 的 14 个）→ **108**（本批）。"
    "5 处「条数 == 93」的断言（registry 4 + store 1）已由实现侧 20:48:59 同步为 108（未提交），本节写明「这是过期断言更新，不是回归」。",
    "",
    "## 11.2 与 v0.8 的关系、以及为什么这次叫 v0.9",
    "",
    "- v0.8（R8，`__B8B__ B / __B8L__ 行 / 正文 `head -c __B8BB__` → `__B8BS16__…` / 全文 `__B8FS16__…`）已于 20:39 落盘并对外引用"
    "（`DELIVERY_SCHEDULE` 与 R8 说明）。该文件自 20:39 落盘后于本日被并行流程**多次原位改写**"
    "（`xs_rank_market` 两层澄清、footer 簿记、§10 行等，至少四组不同字节），而版本号不变；",
    "本版底本 = `__B8FS16__…`（即下面四元组那一组字节；构建脚本在构建期间断言该哈希不变，故底本可按哈希复现）。"
    "**本版不覆盖 v0.8**：同一路径同一版本号本日已出现多组字节，再改会让已流通的哈希失效。",
    "故本版取 `v0.9`，v0.8 保留不删、只把引用状态改「已被 v0.9 取代」。",
    "- **v0.6 仍是清单 v2（`F-A34`–`F-A39`）的绑定对象**，v0.5 是 `F-A30`–`F-A33`、v0.4 是 `F-A5`，均不变。",
    "- **本版无新增判据编号冲突**：`F-A42` 为新增；`F-A11a`/`c`/`d` 与 `F-A10` 一字未动。",
]
S11 = []
for ln in CHG_HEAD:
    S11.append(ln)
i = find_one(lambda s: s == "## 10. 现状事实更正与签认口径（v0.8 新增，R8）", "§10 标题")
# §11 放在 §10 之后（即 §10 全部内容之后、footer 之前）：先定位正文末尾
last = find_one(lambda s: s == "---", "尾部分隔线") if False else None
# 正文末尾结构：... §10.6 列表 -> '' -> '---' -> '' -> footer
tail_idx = None
for j in range(len(lines) - 1, -1, -1):
    if lines[j].strip() == "---":
        tail_idx = j
        break
assert tail_idx is not None
lines[tail_idx:tail_idx] = S11 + [""]

# ------------------------------------------------- 7. 占位符回填（行号）
TEXT = CR.join(lines)
assert TEXT.count("OLD_A11B") == 1 and TEXT.count("NEW_A11B") == 1
TEXT = TEXT.replace("OLD_A11B", old_a11b).replace("NEW_A11B", NEW_A11B)


def lineno_of(text: str, needle: str) -> int:
    idx = text.index(needle)
    return text.count(CR, 0, idx) + 1


for _round in range(4):
    L = TEXT.split(CR)
    nums = {
        "L11B_ROW": lineno_of(TEXT, "| F-A11b | 数值一致（**列级**"),
        "L11B_WHY": lineno_of(TEXT, "**为什么 `F-A11b` 只写列级"),
        "L716_HEAD": lineno_of(TEXT, "### 7.16 canonical/alias 闸门"),
        "L716_TBL": lineno_of(TEXT, "**7.16.6 拒 alias 时"),
        "L716_CRIT": lineno_of(TEXT, "**7.16.7 验收判据"),
        "L28_HEAD": lineno_of(TEXT, "### 2.8 `observed_bars` 的口径差异"),
        "L28_TBL": lineno_of(TEXT, "| 两口径判定不同的标的日 |"),
        "L27_B1": lineno_of(TEXT, "- **进入 `/api/factors` 对外目录"),
        "L27_B2": lineno_of(TEXT, "- **5 处「目录条数」断言"),
    }
    changed = False
    for i, ln in enumerate(L):
        new = ln
        for k, v in nums.items():
            if "`" + k + "`" in new:
                new = new.replace("`" + k + "`", "`:{}`".format(v))
        if new != ln:
            L[i] = new
            changed = True
    if not changed:
        break
    TEXT = CR.join(L)

# 回填后复核：行号未变
for k, v in nums.items():
    assert "`" + k + "`" not in TEXT, k
assert lineno_of(TEXT, "| F-A11b | 数值一致（**列级**") == nums["L11B_ROW"]

TEXT = (TEXT.replace("\\`", "`")
             .replace("__B8B__", format(BASE_BYTES, ",")).replace("__B8L__", format(BASE_LINES, ","))
             .replace("__B8BB__", format(BASE_BODY_BYTES, ",")).replace("__B8BS16__", BASE_BODY_SHA16)
             .replace("__B8FS16__", BASE_FULL_SHA16))
assert "__B8" not in TEXT

# ------------------------------------------------------------ 8. footer
body = TEXT
nbytes = len(body.encode("utf-8"))
sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
nlines = body.count(CR) + 1

FOOTER = (
    "本文件正文 sha256：`{sha}`（校验：`head -c {n} \"docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md\" | sha256sum`）"
    "· 正文 `{n} B` · 行数 `{lines}` · 版本 **v0.9（2026-11-07 R9：`F-A11b` 列级 + `FS03` 可判定条款 + `observed_bars` 信息项 + "
    "catalog 108，操作版）**· 全文 sha256 与 `numstat` 见交付说明（本文件不自指，四元组由 `research/arch-build-20261107/build_contract_v09.py` 复算）**· 生成 2026-11-07 v0.9 = **v0.8 逐字节为底** + R9 四处（`F-A11b` 1 行替换 + 1 段理由、"
    "§7.16 新增、§2.8 新增、§2.7 2 bullet）+ 版本簿记（H1 / §0 1 行 / §9 1 行 / §11 新增 / 本 footer），**判据语义仅 `F-A11b` 一处改动且为收窄**"
    "· **v0.8（{b8} B / {l8} 行 / 正文 `head -c {b8b}` → `{b8bs}…` / 全文 `{b8fs}…`）为 2026-11-07 20:39 落盘后经并行流程多次原位改写后的字节（版本号未变），**本版以其为冻结参照 —— 只认哈希不认时刻**，已被本版取代、文件保留不删**"
    "· v0.7（193,586 B / 1,696 行 / 全文 `5a87d4b090d996ab…fe89c1f8723e8`）为 18:03 快照、降为历史版本，其 `F-A30`–`F-A41` 判定对象不变"
    "· v0.6（162,361 B / 1,454 行 / 正文 `head -c 160819` → `e3a4db17…2576ec` / 全文 `946a1d86…616810`）为清单 v2（`F-A34`–`F-A39`）绑定对象、其判定对象不变"
    "· v0.5（138,729 B / 1,298 行 / 正文 `head -c 137598` → `082d26fa…af7fae` / 全文 `c7740508…c4a21a`）为 `F-A30`–`F-A33` 绑定对象"
    "· v0.4（`FACTOR_ENGINE_CONTRACTS_20261107.md`，128,007 B / 1,226 行 / 正文 `head -c 127043` → `71708877…d16bc` / 全文 `5bd81a74…c5531`）仍为 `F-A5` 绑定对象"
    "· v0.3 冻结态（89,833 B / 914 行 / 全文 `5eb97724…565903`）逐字节归档于 `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`"
    "· **本版为本周期最后一次版本变更：此后不再追加版本，进入冻结评审**"
)
footer = FOOTER.format(
    sha=sha, n=nbytes, lines=nlines,
    b8=format(BASE_BYTES, ","), l8=format(BASE_LINES, ","), b8b=format(BASE_BODY_BYTES, ","),
    b8bs=BASE_BODY_SHA16, b8fs=BASE_FULL_SHA16,
) + CR

out = body + footer
DST.write_bytes(out.encode("utf-8"))

full = hashlib.sha256(out.encode("utf-8")).hexdigest()
print("SRC_BYTES", len(raw.encode("utf-8")))
print("DST_BYTES", len(out.encode("utf-8")))
print("LINES", out.count("\n"))
print("BODY_BYTES", nbytes)
print("BODY_SHA12", sha[:12])
print("FULL_SHA12", full[:12])
print("S11_LINES", len(S11))
assert hashlib.sha256(SRC.read_bytes()).hexdigest() == BASE_SHA, "v0.8 changed during build"
print("BASE_STABLE", BASE_SHA[:16])
