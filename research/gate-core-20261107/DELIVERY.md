# B2 闸门核心交付 —— `backend/app/factors/gate.py` + `backend/tests/test_factor_gate.py`

2026-11-07 21:4x。纯新增、未接线、未提交、未部署、未重启；`backend/app/backtest`、
`backend/app/strategy`、`api/factors.py`、`store.py`、`dsl.py` 全部未动。

## 0. 硬事实

| 项 | 值 |
|---|---|
| `backend/app/factors/gate.py` | 603 行 / 25,829 B / sha256 `39a9d9cf…a62375` / 新建 |
| `backend/tests/test_factor_gate.py` | 463 行 / 18,056 B / sha256 `84591d2a…a6974` / 新建，**56 passed / 0 failed** |
| `ruff check`（两文件） | All checks passed |
| `dsl.py` 改前 == 改后 | 36,785 B / `49f3a1106095ad0cf4a6c1cb8ccde42283957756f89ac1f226bf1624fea0c78b` / mtime `18:37:48` |
| `git status --porcelain -- backend` | 开工前 8 行 → 现在 10 行，只多 `?? gate.py` 与 `?? tests/test_factor_gate.py` |
| `D:\TSP\data\user_data\custom_factors` | 15 文件，取证前后签名（目录 mtime + 每文件 name/size/mtime_ns）**逐项相同** |

## 1. `GateReport` 字段（§7.7.2，契约 :909）

`ok: bool` / `blocked: tuple[(factor_id, status, code)]` / `non_active: tuple[str,…]` /
`unknown: tuple[str,…]` / `mode: str` / `historical_only: bool` —— **六个，名字与顺序逐字照抄，无增无减**
（`gate.py:80`；测试 `test_gate_report_has_exactly_the_six_contract_fields` 断言 `dataclasses.fields` 的名字序列）。
另有一个**方法**（不是字段）`GateReport.codes()`，只做错误码去重保序，供入口拼 400。

## 2. 判定矩阵逐格（实现：`gate.py:303 _judge` + `gate.py:435 assert_factors_usable`）

`kind ∈ {custom, composite}` 才判 status；`base`/`virtual` 与活配置里的管线列一律不 gate（§7.7.2 :919、§7.8.3 表第一行）。

| 事实 | production | research | diagnostic |
|---|---|---|---|
| `active` | 允许 | 允许 | 允许 |
| `watch` | 拒 `FS01` | 允许 + `non_active` | 允许 + `non_active` |
| `draft` | 拒 `FS01` | `allow_non_active=true` → 允许 + `non_active`；否则拒 `FS01` | 允许 + `non_active` |
| `retired` | 拒 `FS01` | `allow_retired=true` → 允许 + `non_active` + `historical_only=true`；否则拒 `FS01` | 允许 + `non_active`（`historical_only=false`） |
| 无 status（Provider 注册，现状 pack 14） | 按 `draft` → 拒 `FS01`（§7.8.4 末行） | 同 draft 行 | 允许 + `non_active` |
| 未登记 | 拒 `FS02` | 拒 `FS02` | 拒 `FS02`（§7.8.3 表末行无模式限定） |
| alias（可解析） | 拒 `FS03` | 允许 | 允许 |
| alias 成环 / 超 4 跳 / 目标未登记 | 拒 `FS06` | 拒 `FS06` | 允许（§7.8.4 矩阵末列） |
| `lang="python"` | 拒 `FS05` | 允许 | 允许 |
| base / virtual / 管线列 | 允许 | 允许 | 允许 |

14 个 status×mode 组合逐格断言在 `test_status_matrix_cells`（参数化），无 status / 未登记 /
base+virtual / python / alias / FS06 各有独立用例。`require_status=False` 时整段 `FS01` 不判（§7.16.3 签名）。

## 3. 每个错误码的判定依据

| 码 | 契约依据 | 实现 | 判定所需事实（盘上） |
|---|---|---|---|
| `FS01` | §7.7.2 矩阵 :914–:919；§7.8.4 末行（无 status 按 draft）；§7.8.4 末段（不得用 `stability` 反推） | `gate.py:342-365`；status 只读定义 JSON 的 `status`，**从不读 `spec.stability`**（`gate.py:256-266`） | `custom_factors/*.json` 的 `status`；无定义/无字段 → `None` → 按 draft |
| `FS02` | §7.7.5 :924；§7.8.3 表末行 | `gate.py:313-314`（`registered=False`）；`RegistryFacts` `gate.py:224-254` | registry 命中 ∪ store 定义命中 ∪ 管线列/指标列（见 §4 第 2 条） |
| `FS03` | §7.16.2 C1–C4 :1618–:1621（四条同时成立；C4 只在 production） | `gate.py:322-332`（`alias_of` 非空 + `mode=="production"`） | `alias_of`（spec 属性 → 定义 JSON 同名字段）；**F-A42-1 未落地，真实数据上该字段全为空** |
| `FS05` | §7.8.3 表第 3 行「custom-python … `reference_missing` → `FS05`」:1028 | `gate.py:367-369` | `lang == "python"`（盘上 15 个定义全 `dsl`，实测 0 例） |
| `FS06` | §7.8.2 A-3（4 跳上限 / 环检测 / 目标必须已登记）；§7.16.2「`FS06` 优先于 `FS03`」:1619 | `gate.py:268-293 resolve_alias` + `gate.py:325-330`、`gate.py:333-338` | `alias_of` 图；「台账不一致」一支见 `gate.py:590 check_ledger_consistency`（显式 `NotImplementedError`） |
| `FS04`（**未实现**） | §7.16.6 :1655「`FS04` 优先于 `FS03`」 | `gate.py:383 _guard_dual_id`：识别到同 canonical 双 id 就 `NotImplementedError`，**不静默放行** | 同上；本单派发书只列 5 个码，故不实现判定 |

`GateError.detail` 的键集合照 §7.16.4 示例（:1638–:1650）：`code` / `mode` / `submitted_id` /
`resolved_id` / `canonical_id` / `table_row` / `message`；`FS01` 另带 `status`（§7.7.5 :924 要求
detail 含 `factor_id`/`status`/`mode`——而 §7.16.4 的键集合里没有 `status`，见 §5 第 2 条）；
多条违规时另加 `violations`（§7.16.4 批量入口条款）。`table_row` 默认 `None`：§7.15.1 表格没有
机器可读副本（见 §5 第 1 条），注入时可用（`test_alias_table_row_is_carried_from_facts` 验到 1）。

## 4. 派单书与盘上事实不一致的两处（按实测报，不按派单书写）

1. **「22 条活配置 93 条记录 → 全 allow」不成立。** 实测 `summary.live_config` = 93 记录 / 22 源 /
   79 primary allow / 14 companion exempt；19 个去重 id 里 15 个是 base 或管线列（不 gate，全放行），
   另一 4 个 `ma20` / `ma60` / `boll_lower` / `boll_upper` 由 `research_factor_pack` 以
   `kind="custom"` 注册且**盘上无 status** → 按 §7.8.4 末行作 draft → production **FS01**。
   按 §7.15.1 第 9–12 行，这 4 个是**单侧件 canonical**（`alias_of` 必须 `None`、
   `strategy_usable=true`），所以它们将来也不会因别名被 `FS03` 拦；唯一缺口是它们没有
   `status`——`FS01` 是唯一拦点。这也是 §7.8.1 #12「活配置里 pack 原名的引用只有 2 个文件」
   的既有问题；`research`+
   `allow_non_active=true` 与 `diagnostic` 才全 allow（`non_active` 恰为这 4 个）。
   证据：`EVIDENCE_gate_realdata.json#live_config_production`。测试因此不断言「全 allow」，
   而断言「活配置 id 无一 FS02；被拦的必是 `kind ∈ {custom,composite}` 且 `status != active`；
   research(allow_non_active)/diagnostic 全 allow 且 `non_active` == 被拦集合」。
2. **`fs02` 面比契约字面宽。** §7.7.2 只写「registry 与 custom store 都没有」，若照字面，
   19 个活配置 id 里有 14 个（`close`/`raw_high`/`ma5`/`macd_dif`/`limit_up_price`…）会被 `FS02` 拦，
   等价于闸门一上线现有策略全停。实现把这批 id 归为 `kind="base"`（§7.8.3 表第一行「base 不 gate」），
   集合取自 `dsl.BASE_COLUMNS` ∪ `pipeline.{INDICATOR_COLUMNS, ENRICHED_COLUMNS,
   ENRICHED_STORAGE_COLS, LIMIT_SIGNAL_OUTPUTS, _ALL_INDICATOR_COLS, _LIMIT_PRICE_COLUMNS}`（68 个名字，
   不写死任何 id，`gate.py:162 _column_universe`）。**这条归类要架构师确认**。

## 5. 契约含糊 / 自相矛盾（列给你，我没有自己补）

1. **§7.15.1 canonical 表没有机器可读副本** → `FS03` 的 `table_row` 与 §7.16.5「表与定义不一致报
   `FS06`」都无法从盘上事实判定；§7.16.5 又禁止二次登记，所以我没有造副本，`check_ledger_consistency`
   显式 `NotImplementedError`。F-A42-2 的 `table_row=1/2` 断言在没有台账文件前不可能通过。
2. **`FS01` 的 detail 键集合两处不一致**：§7.7.5 要求含 `factor_id`/`status`/`mode`，§7.16.4 的固定
   键集合只有 `submitted_id` 且无 `status`（§7.16.4 自称「FS03 与 FS04/FS06 共用」，未覆盖 FS01）。
   我按「基础 7 键 + FS01 追加 `status`」实现，`factor_id` 用 `submitted_id` 承载。
3. **`GateReport` 六字段 vs §7.8.4 的四条标记**：research/diagnostic 要「标 `deprecated_alias_used` /
   `reference_missing` / `dual_id` / `ambiguous_canonical`」，六字段里没有承载位置。我没有扩字段，
   这四条标记当前**只存在于我脑子里和这份报告里**，落点待裁定。
4. **`mode` 的取值**：§7.7.2/§7.8.4 只有三值，派单书给了第四个 `none`。我实现为「不判定」。
   `production`/`research` 之外的 `diagnostic` 对 `retired` 是否置 `historical_only` 契约没写，我取
   「只有 research+`allow_retired` 置 true」。
5. **`shadow` / `entry` 两个参数契约里没有**：`shadow` 按派单书实现（只出报告不抛）；`entry` 保留
   契约的位置参数顺序、作可选关键字、只挂 `GateError.entry`，不进 `detail`。
6. **`FS01` 与 `FS05` 同时成立时谁先报**：契约只在 `FS03`×`FS04`（:1655）、`FS03`×`FS06`（:1619）、
   `FS03`×`FS10`（§7.16.3 #4）给了优先级，status 与 python 之间没给。我按 `FS06 > FS03 > FS01 > FS05`
   排列，多条违规全部记入 `blocked`。

## 6. 测试归属（派单书第二问，如实回答）

**是我改的，而且改动后 11 分钟就与 20:37 冻结的证据冲突，这一点我不圆。**

- `backend/tests/test_factor_registry.py` `+22/−6`、`backend/tests/test_factor_store.py` `+3/−3`，
  两个文件 mtime 都是 **20:48:59**。改动内容：`GOLDEN_COLUMNS` 追加 15 条（B0 的 14 个研究基线 +
  `in_universe`，含 1 行注释），计数 `93 → 108`（5 处，其中 `70 → 85` 一处），`test_factor_store`
  的 `builtin_count` 两处 `93 → 108`。
- **为什么在证据冻结之后改**：我是被派单改的——因子目录从 93 变 108（B0/B2 的 15 个 pack 因子）后，
  「目录 == 93」的硬编码就是失效写法，我先按 108 更新基线，再在 20:48:59 落盘；
  `research/b2-engine-20261107/EVIDENCE_20261107.json`（20:37 冻结）里「本批未改任何测试」这句
  在**它自己的时间点上是真的**，到 20:48:59 就不再为真。**那份证据那句话现在是失效的**，
  需要你决定是订正还是重冻结——我不去改别人的冻结件。
- **改时是否意识到「测试押 108 而两个 pack 目录未入库（`??`）」会让干净检出 6 红**：
  **没有明确写下这个依赖**，这是我这边的欠账。而且今天实测**比干净检出更糟**：
  在本机（pack 目录在盘）跑**全量** `pytest tests -k factor` 同样出现这 6 红，报错是
  `assert 93 == 108`（测试押 108、注册表只给 93）与 `('uf_test_rev' in [...] and 93 >= 108)`——
  即**同进程里前面的用例把 provider 注册态清掉了**，隔离跑那 12 个文件时 130 全过。
  两个后果：① 这 6 红是**顺序依赖**的历史缺陷，不是我这单引入的（改动前后同一份 8 条失败清单）；
  ② 押 108 在当前工作树里**两种情形都会红**（干净检出 + 全量混跑）。
  另外派单书写「失败项 golden 93 vs 107」不准确：实测失败文本是 `assert 93 == 108`。

## 7. 回归基线（同一命令，改动前后各一次）

| 命令 | 改动前 | 改动后 | 差异 |
|---|---|---|---|
| `pytest tests/test_factor_*.py`（12 个既有文件，不含新文件） | 130 passed / 0 failed | 130 passed / 0 failed | 逐条相同 |
| `pytest tests/test_factor_gate.py`（新文件） | — | 56 passed / 0 failed | 新增 |
| `pytest tests -k factor`（全量筛） | 8 failed / 335 passed | 8 failed / 391 passed | 失败清单 8 条逐条相同，通过数 +56（新文件） |

派单书写的「改前 6 failed / 91 passed」在今日工作树上复现不出：那 6 条（`test_factor_registry` ×5 +
`test_factor_store` ×1）在 12 文件隔离跑里是绿的，只有全量混跑才红。两种口径我都留了日志
（`baseline_after_12.txt` / `baseline_after_kfactor.txt`）。

## 8. 只读取证（`verify_gate.py` → `EVIDENCE_gate_realdata.json`）

- `D:\TSP` 现有 15 个定义：`status` 全 `draft`、`kind` = 14 `custom` + 1 `composite`、`lang` 全 `dsl`；
  production **15/15 FS01**；research 默认 15 FS01；research+`allow_non_active` 全允许（`non_active` 15 个）。
- 活配置 allowlist：93 记录 / 22 源 / 79 primary / 14 companion / 19 个去重 id；production 拦 4 个
  （`boll_lower`/`boll_upper`/`ma20`/`ma60`，全 `FS01`），其余 15 个放行。
- 取证前后 `D:\TSP` 目录签名逐项相同（`store_untouched: true`）；`dsl.py` 前后同哈希同 mtime。

## 9. 未验证 / 待追认

- **未接线**：§7.7.3 / §7.16.3 的 9 个调用点全部未改，`assert_factors_usable` 目前零生产调用方；
  接线与 `FS10` / `FS04` / `FS07` 的顺序关系没验。
- **`alias_of` 与 `strategy_usable` 未落地**（F-A42-1 是 P2 的事）：真实数据上 `FS03` 触发面为 0，
  当前生产拦截面只靠 `FS01`（pack 4/14 个无 status）。F-A42-2/3/4/5 都不能在真实入口上验。
- **`table_row` 恒 `None`**、`check_ledger_consistency` 恒 `NotImplementedError`，原因见 §5 第 1 条。
- `_column_universe` 里两个下划线常量（`_ALL_INDICATOR_COLS`、`_LIMIT_PRICE_COLUMNS`）是私有名，
  只作并集补充，用 `getattr` 兜底；若上游改名不会静默漏列（会退回 `FS02` 并被 `test_live_config_ids_…`
  抓到）。
