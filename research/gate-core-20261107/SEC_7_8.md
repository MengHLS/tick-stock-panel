### 7.8 双 id、别名与「不可复算因子」的闸门契约（v0.4 新增；批二前置，不落地则闸门一上就误判）

本节回答三个问题：**同一口径两个 id 谁是 canonical、旧 id 被闸门怎么对待、没有 DSL 公式的因子怎么判**。

#### 7.8.1 事实（逐条实测；2026-11-07 16:10–16:25 本机复跑）

| # | 事实 | 依据（可复跑） |
| --- | --- | --- |
| 1 | `backend/app/custom/research_factor_pack/`（未跟踪，14:33–14:42）经 Provider 注册 **14 个研究原名 id，14/14 均可 `get_factor`**；不是「只注册 4 个、另 10 个未注册」 | `factor_provider.py:42-46`、`factor_specs.py:38-76`（`_DEFINITIONS` 14 条）、`:92-98`；运行时 dump：`ma20/ma60/boll_lower/boll_upper/sd20/prior_high_20/prior_low_10/prior_high_55/prior_vol_20/ma120/vol60/prior_high_250/prior_amount_20/ma200` 全部非 `None` |
| 2 | 这 14 个是 `kind="custom"` + `lang="dsl"` + `formula_text` = **DSL 原文**（非空、可编译），warmup 由 DSL 推导；`stability="stable"`、`version=1` | `factor_specs.py:78-87`、`:26`；实测 warmup 依次 21/61/21/21/21/21/11/56/21/121/61/251/21/201 |
| 3 | **`FactorSpec` 没有 `formula` 字段**（只有 `formula_text`）：`getattr(spec,"formula",None) is None` 是「字段不存在」，不是「公式为空」 | `registry.py:33-57`（21 字段）；`[a for a in dir(spec) if "form" in a]` → `["__format__","formula_text"]` |
| 4 | 真正「没有可编译公式」的是 `kind="composite"`：`formula_text` 是合成描述串 `"w*zscore(member) + …"`，**不可编译**（成员引用不走 DSL 语法） | `store.py:156-166`；`cf_auction_resonance` 实测 |
| 5 | `lang="python"`（T2）由 `compile_python_expression` 给出 **`dependencies` 与 `warmup_bars`**（`warmup=max(declared, compiled)`），所以「依赖推断不成立」不成立；缺的是**研究侧参考实现** | `store.py:74-100`；`py_expr.py:99-113` |
| 6 | 同口径双 id 已是事实，**8 组**（v0.4 自纠：本节初稿写「4 组且含 `prior_amount_20`」，与目录实测不符，逐文件读 `id` 后更正）：`ma120`/`ma200`/`vol60`/`prior_high_20`/`prior_high_250`/`prior_high_55`/`prior_low_10`/`prior_vol_20` 在 pack（研究原名）与 store（`uf_*`，14:30:24 落盘 `D:/TSP/data/user_data/custom_factors/`）各一份；**`prior_amount_20` 没有 `uf_` 对应件**，`uf_dist_prior_high_250` 没有 pack 对应件，二者各为单侧 | 目录 15 个 json（14 `uf_` + 1 `cf_`，逐个 `json.load` 读 `id`）；装载后 `all_factors()` 192→**207**；配对 = `[i for i in RESEARCH_BASELINE_FACTOR_IDS if "uf_"+i in store_ids]` → 8 项 |
| 7 | 8 组里**只有 2 组表达式完全相同**（`ma120`/`ma200`）。`vol60` 差 1 ULP：pack 用 `(close - ts_delay(close,1)) / ts_delay(close,1)`，store 用 `close / ts_delay(close,1) - 1`；另 5 组 `prior_*` 是**同窗口不同写法**：pack `ts_delay(ts_max(high,N),1)` vs store `ts_max(ts_delay(high,1),N)`——窗口同为 `[t-N, t-1]`，差异只在边缘 NaN 传播与 1 ULP | `factor_specs.py` 头注；`F_CLASS_PARITY_20261107.md:37` 记 1.11e-16 / 4.6% 行不等；逐文件读 `formula` 对照 |
| 8 | `status` 不进运行时对象，但 `to_spec` 把它**单向投影成 `stability`**：`active→stable`，`draft/watch/retired→experimental`（三态塌陷，`retired` 失去否决力） | `store.py:94`、`:110`、`:165`；实测 `get_factor("uf_vol60").stability == "experimental"`、`hasattr(...,"status") == False` |
| 9 | pack 的 14 个自报 `stability="stable"`，**没有经过任何 status 流程**（不来自 store、无 JSON 定义、无 `POST /custom`） | `factor_specs.py:26`、`:87` |
| 10 | 注册表规模两态实测：catalog **77** + pack **14** + `ext_*` **85** + 其它 Provider **16** = **192**（repo 的 `data/`，store 未装载）；装载 `D:/TSP/data` 的 **15** 个定义后 = **207**（与台账「206 条」差 1，因 `uf_dist_prior_high_250` 16:07 才落盘） | `len(all_factors())`；`load_into_registry(Path("D:/TSP/data"))` 返回 15 |
| 11 | pack 的 14 个 id 在 `factor_columns_view()` 中位于 catalog 之后（idx 86–99），**前 48 条顺序未变**（`mining_schedule` 取前 48，重排即回归） | `[r["id"] for r in factor_columns_view()].index("ma20") == 86`；catalog 长度 77 |
| 12 | 现存引用面（`D:/TSP/data/user_data` 98 个 json）：pack 原名命中 `preferences.json`（`ma20`/`ma60`/`boll_lower`）与 `custom_signals/ma_golden_20_60.json`（`ma20`/`ma60`）；`rsi_14` 的 15 次命中**全在** `firstboard_discovery/runs/*/report.json`（历史运行产物，非活配置） | 逐文件 `grep -l` 枚举 |

#### 7.8.2 裁定 A：canonical = 台账 id（`uf_*` / `cf_*`），研究原名 = alias

三条机制性理由（不是偏好）：

1. **只有 store 侧 id 能带状态与版本**：`status`/`version`/`created_at` 活在 JSON 定义里；Provider 注册的 spec 没有这些字段，改口径在 Provider 侧只能改代码（版本 = 一次提交），无法逐因子审计、无法逐因子回滚。
2. **只有 store 侧 id 有命名空间约束**：`CUSTOM_ID_PATTERN = ^uf_[a-z0-9_]{1,40}$`（`store.py:22`）阻止与研究名、与内置 base 列名相撞；Provider 用任意 id（`factor_provider.py` 头注「任意 id + 元数据」），今天是「名字恰好不撞」，不是「不可能撞」。
3. **G7 可穷举版本化**：口径组合必须可穷举，前提是每个口径一条可版本化记录。

配套硬规则：
- **A-1** 每个口径**恰好一个** canonical；`docs/factors/` 台账逐行写 `canonical_id`、`aliases[]`、`superseded_by`、`canonical_reason`。若某行把 canonical 定为研究原名（非 `uf_*`），必须在该行写理由，且**仍只能有一个**。
- **A-2** alias 只能解析到 canonical，**不得各自持有一套实现**：alias 命中即返回 canonical 的列，数值归属 canonical。生产入口不允许别名（`FS03`），研究入口允许但记 `deprecated_alias_used`。
- **A-3** `FactorSpec` 新增 `alias_of: str | None = None`（P2，与 §7.7.2 的 `status` 同批）；解析规则写死：传递解析上限 **4 跳**、环检测、目标必须是已登记 spec，任一不满足 → `FS06`；解析结果写入策略元数据 `resolved_id`，同时保留 `submitted_id` 供审计。
- **A-4** **alias 生效的数值代价必须报**：`vol60`（pack）与 `uf_vol60` 差 1 ULP（1.11e-16，4.6% 行不等，`F_CLASS_PARITY_20261107.md:37`）。alias 解析到 canonical 后，原引用研究名的策略**必须重跑对账**：判据统一按 `F-A3` 的 `max_abs_diff < 1e-12`；`1.11e-16` / `2.22e-16` 只作实测记录（`uf_vol60` 1 ULP、非零行占比 4.6%），不得写成门槛（把某一次实测的 ULP 值当门槛，会让「同一公式换个求和顺序」的正确实现判失败，属凭空收紧）。非零行占比与 4.6% 同量级作为**辅助观察项**上报，不单独构成判据；超差即视为口径变更，按 G8 走变更流程，不得静默上线。
- **A-5** store 侧 6 个定义（`uf_auction_*` 5 个 + `cf_auction_resonance` 1 个）依赖 `ext_*` 拍卖列，**没有研究侧等价实现** → 走 §7.8.3 的 `reference_missing` 分支，**不得**用 `F-A3` 式逐值对账判它们不合格。

#### 7.8.3 裁定 B：闸门按「可复算性」分类，**不按 `kind`**

| 类 | 判定依据（机械可判） | 数值判据 | `verifiable` / `reference_missing` |
| --- | --- | --- | --- |
| base / virtual（catalog 77） | 不 gate（§7.7.2） | 台账 G1–G3 | `n/a` |
| custom-dsl（store `uf_*`、pack 14 个） | `compile_formula(spec.formula_text).ok == True`；`dependencies` 闭包必须落到 `BASE_COLUMNS` 或已物化 `ext_*` 列 | 同一实现两遍 `max_abs_diff == 0`；有研究参考的另加 `F-A3`/`F-A10` 式对账 | `true` / `false` |
| custom-python（`lang="python"`） | `compile_python_expression(spec.formula_text).ok`；`warmup_bars ≥ compiled.warmup_bars` | **没有 DSL 表达式 → 不能走 `compile_formula`、不能与研究对账**；只做「同输入两遍逐位一致」+ 声明测试向量 | `true` / **`true`** → `FS05` |
| composite（`cf_*`） | **不编译** `formula_text`（描述串）；判据 = 成员全部 `usable`（递归）+ 权重非零 + 无环 | 两遍一致；成员可复算性逐个继承 | `true` / `false` |
| 未登记 | — | — | 拒绝 `FS02` |

**对「`formula=None` 的 python 因子怎么判」的正面回答**：按 `lang` 分支，**不按「`formula` 是否为空」**（该字段不存在，见 7.8.1 #3）。python 因子的 `dependencies`/`warmup` 由 `compile_python_expression` 给出，`factor_columns_view()` 对所有 spec 一视同仁（`factor_columns_view()` 在 `registry.py:408`，行内只看 `id/label/group/formula_text`，`column_view()` 在 `:61`），所以「依赖推断与列视图不成立」不成立；真正不成立的是**「对研究参考实现复算 `max_abs_diff`」**——python 因子没有研究侧等价物，只能是 `reference_missing=true`，判据降级为「自洽双跑 + 测试向量」。现状**实测 0 个 python 因子**（`D:/TSP/data` 15 个定义的 `lang` 全为 `dsl` 或缺省），但分支必须写死：第一只 python 因子进线时，闸门不能靠「今天没有」来决定走哪条路。

#### 7.8.4 闸门模式位与新增错误码（续 §7.7.5）

`assert_factors_usable(factor_ids, mode, ...)` 的 `mode` 增加第三个取值 `diagnostic`（仅供诊断/差异证明路径），判定矩阵在 §7.7.2 的 `status` 维度上**叠加 `verifiable` 与「是否 alias」两个布尔维度**（不是新的状态机）：

| 情形 | `production` | `research` | `diagnostic` |
| --- | --- | --- | --- |
| canonical `active` + `verifiable=true` | 允许 | 允许 | 允许 |
| canonical `active` + `reference_missing=true` | **拒绝 `FS05`** | 允许，报告标 `reference_missing` | 允许 |
| 提交的是 alias（可解析） | **拒绝 `FS03`**（生产只认 canonical id） | 允许，标 `deprecated_alias_used` | 允许 |
| 同一策略内 alias 与 canonical 并存 | **拒绝 `FS04`** | **拒绝 `FS04`** | 允许（标 `dual_id`） |
| 两个 id 都自称 canonical / 台账未裁定 / 别名成环 | **拒绝 `FS06`** | **拒绝 `FS06`** | 允许（标 `ambiguous_canonical`） |
| Provider 注册且**无 `status`**（现状：pack 14 个） | **拒绝 `FS01`**（按 `draft` 处理） | 允许，标 `non_active` | 允许 |

| 码 | 含义 | 处置 |
| --- | --- | --- |
| `FS03` | 生产入口引用了 alias 而非 canonical | 400；`detail` 含 `submitted_id` / `resolved_id` |
| `FS04` | 同一策略混用同口径两个 id | 400；`detail` 含两个 id 与台账行号 |
| `FS05` | 无可复算参考实现且未声明测试向量 | 400；`detail` 含 `lang` 与 `reference_missing` |
| `FS06` | canonical 未裁定 / 冲突 / 别名成环（解析不可判定） | 400，fail-closed |

**硬规则：不得用 `stability` 反推 `active`。** `stability` 是 `status` 的单向投影（7.8.1 #8）。反向不成立：pack 的 14 个 `stability="stable"` 没有任何 status 支撑。若闸门拿 `stability` 判准入，这 14 个会被当成已验收放行进生产——**误放行比判死更危险**，也是本节最容易被实现者图省事做错的一处。

#### 7.8.5 过渡期（不做这一段，批二一上线就停产）

- 闸门对**新写入**的配置 fail-closed：`POST /api/strategy/config`、`PATCH`、X1 计划生成、`paper_auto` **新**规则装载。
- 对**存量**规则：加载时只告警，并在运行报告写 `degraded=true`，不阻断；存量清单（`referenced_factor_inventory`：文件 + 提交 id + `resolved_id` + 状态）由因子工程师在批二**前**产出，本契约只要求这份清单存在且机器可读。
- 存量清理完成后，由开发经理把 `enforce_existing=true` 打开，新旧一视同仁。
- 现状最小事实（7.8.1 #12）：活配置里 pack 原名的引用只有 2 个文件；`rsi_14` 的 15 次命中全在历史报告里 → D2「`rsi_14` 不得被策略引用」在活配置上目前 **0 违例**，但闸门必须能拦住**新写入**。

#### 7.8.6 验收判据（续 §7.6 编号）

| # | 判据 | 度量 |
| --- | --- | --- |
| F-A14 | 14 个 pack id 分类正确 | 逐一 `compile_formula(formula_text).ok == True`、`kind=="custom"`、`lang=="dsl"`、warmup = 21/61/21/21/21/21/11/56/21/121/61/251/21/201 |
| F-A15 | alias 解析 | 造 3 组（一跳、两跳、成环）：解析结果分别 = canonical / canonical / `FS06`；`resolved_id` 与 `submitted_id` 同时落库 |
| F-A16 | python 不误判 | 造一个 `lang="python"` 因子：闸门返回 `reference_missing=true`，`production` 给 `FS05`，且**不进入** `compile_formula` 分支 |
| F-A17 | 存量不阻断、新写入拦住 | 存量规则加载：计划/订单生成未被阻断且报告含 `degraded=true`；同内容的新写入被 `FS01`/`FS03` 拒绝 |

---
