# F 类表达式因子注册台账（8 只）—— 批一：只登记，不注册

状态：**台账 v5.11（2026-11-08 00:56 修订；v5.10 于 00:52、v5.9 于 00:40（含 00:46 的 §7.1 块哈希改绑）、v5.8 于 22:36、v5.6 于 19:21、v5.5 于 18:57、v5.4 于 17:36、v5.3 于 17:11、v5.2 于 16:57、v5.1 于 16:47、v5 于 16:40、v4 于 16:20、v3 于 16:14、v2 于 16:10、v1 于 14:37）**。本文件只登记台账与映射：不注册、不复算数值、不写实现。v1 的几处状态描述已按实测与裁定更正 —— ①8 只 `uf_*` **已由系统开发工程师落盘并注册**（2026-11-07T14:30:24 写入 `D:/TSP/data/user_data/custom_factors/`，启动期 `load_into_registry` 装载，§2.10）；②`prior_amount_20` **已以研究名 + pack provider 注册**（§4.1）；③**数值对账已由系统开发工程师完成、独立审核已复核**，证据在 `docs/factors/evidence/F_CLASS_PARITY_20261107.*`，本文只引用、不重算（§7）；④`dist_prior_high_250` **已由系统开发工程师以 `uf_dist_prior_high_250` 注册并逐位对账**（2026-11-07T16:07 落库、16:09 报告，`max_abs_diff = 0.0`，§4.2）；⑤`rsi_14_pct` 的「base 列」路线**实测不可行**（`max_abs_diff = 28.8984`，须改 `pipeline.py` Pass 5 三处，§4.3）；⑥**v4：同口径双 id 事实按裁定更正为 8 组**（含 `prior_amount_20` / `uf_dist_prior_high_250` 两条**单侧例外**；§1.2 K8 与新增 §2.1b 逐行给 `canonical_id` / `aliases[]` / `canonical_reason` / `replaced_by`）；⑦**v4：V3 补充对账落盘**（F-A3 全量 8 只 × 20 symbol × 近 250 交易日逐值 + 末交易日截面名次漂移），证据 `docs/factors/evidence/F_CLASS_RANK_PARITY_20261107.json`，8 对 `rank_change_max` 全 0（§7 第 17 行）；⑧**v5：`replaced_by` 写法统一** —— 已注册目标一律写 canonical id（`uf_prior_high_55` / `uf_prior_low_10` / `uf_dist_prior_high_250`），未注册目标 `rsi_14_pct` 改写 **`replaced_by = null`** + `replaced_by_declared_name` + `target_registered = false`；任何非 `uf_*`/`cf_*` 的研究原名不得留在 `replaced_by` 字段（§2.1b 读表须知 2）；⑨**v5.1：`replaces` 逆关系补齐** —— `uf_prior_low_10.replaces = ['low_60d']`（原为 `[]`，与 `low_60d.replaced_by = uf_prior_low_10` 不成逆），并把 §2.1b 第 5/7 行「本因子不取代别人」这条错述改为显式 `replaces`；8 条 `factors[]` 的 `replaces`/`replaced_by` 已逐条核为互为逆。⑩**v5.2：指纹口径与公式权威同时改绑** —— 行尾在 16:45:33、16:49:20 被第三方两次改写（内容一字未变），raw 字节 sha256 失效，故**指纹一律改记 LF 归一化 sha256**（§0.1）；自检脚本的公式权威由活契约改读**归档冻结副本** `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`（检查 4），并在 RESULT 前打印所校验三文件的 LF 归一化 sha256；`single_sided_exceptions[0]`（`prior_amount_20`）补 `replaces: []` 与第 10 行对齐。⑪**v5.4：[4] 指针改指 v0.6 + 两条裁定入账** —— ①自检 `[4]` 的 `contract2` 由 v0.5 改指 **v0.6**（R6 于 17:16:36 冻结的现行编号修订）；实测 §7.1 块在归档 v0.3 / v0.4 / v0.5 / v0.6 **四处逐字节相同**（原始 CRLF 2,541 字符 / `a8e88134…`；LF 归一化 2,514 / `6d3db013…`；去尾换行 2,513 / `e9ed2b10…`），改指针零结论翻转；②`meta.revision_note` 里过期的契约哈希（110,944 B / `6b8fb14c…`〔作废：中途态，盘上无对应文件，见 ⑫〕）改为三份契约逐份现行指纹（raw + LF 两种口径）；③登记本轮两条裁定：**(a) 伴生记录形态**（主 false/allow/column，伴生 true/exempt/factor，靠 `record_kind` 区分，契约 v0.6 §7.12.2）+ **(b) `path_scope=history` 由 N4 固化为代码事实**（§7.10.3，`custom_signals.py:646-647`），收回此前期望表的 `both`，见新增 §12。**因子数字、组数、公式、warmup 一律未动。**⑫**v5.5：三处口径收尾（不改结论、不改数字）** —— ①`110,944 B / 6b8fb14c…` 就地标**【作废：中途态，盘上无对应文件】**，并按「size + sha + 读取时刻」一起引（读取时刻 2026-11-07T18:23+0800；该刻盘上无此尺寸契约文件，同刻实数：未编号活暂存 128,007 B / raw `5bd81a74…`、v0.5 138,729 B / raw `c7740508…`、v0.6 162,361 B / raw `946a1d86…`）；同族另两个中途态 109,914 B / `5c1264…`、正文前缀 110,098 B / `11bfe51f…` 一并标注（JSON `meta.sources[0].hash_note_v3/v4/v5`）；②「`[4]` 绑的是哪一份」两处措辞统一为 **v0.6** —— JSON `meta.sources[0].binding` 与 `self_check.checks[3].rule` 原写「活修订 v0.5」，改为 v0.6，与脚本 `contract2` 行、`meta.contract_binding.bound[1]`、本节 §12.3 指同一对象；v0.5 仅留作非绑定旁证；③§7.1 块口径统一为**脚本实算值** 2,514 字符 / `6d3db013…`（LF 归一化含尾换行），2,513 / `e9ed2b10…` 降为同一块的另一种量法，2,541 / `a8e88134…` 只作团队通报值；④`side_key` **未涉及实质引用**：契约 v0.6 §7.10.2 定其为**可选、不参与判据**；v5.4 基线上本台账与 JSON 对该字段 0 次引用，故无需改口径；v5.5 起出现的字样（本台账 2 处 / JSON 3 处）全部是对「是否引用」的元陈述。

本文作者未改任何代码、未改 `backend/**`、未改 `docs/research/`、未改 `docs/architecture/`、未改 `research/*`、未改 `docs/factors/` 下他人文件。作者：因子工程师。日期：2026-11-07。

## 0.1 指纹（v5.2 口径：LF 归一化 sha256）

**口径**：把 CRLF 折叠成 LF 后对全文取 sha256。行尾被第三方改写时**这个值不变**（raw 字节 sha256 会变），因此在无 git 历史的目录里仍可复算。**行尾策略：`docs/factors/` 两个台账文件统一 LF。**

| 文件 | size | 行 | 行尾 | 文件 mtime（盘面） | LF 归一化 sha256（v5.9 实测） | raw 字节 sha256（同刻实测） |
| --- | --- | --- | --- | --- | --- | --- |
| `docs/factors/evidence/f_class_registry.json` | 163,451 B | 2758 | LF（CRLF 0） | 2026-11-08T00:54 | `18ccb5a531388b850c661f1fa05cd93d446cbf8ae1e7dcf605d3f2a21bedd56f` | `18ccb5a531388b850c661f1fa05cd93d446cbf8ae1e7dcf605d3f2a21bedd56f` |
| `docs/factors/evidence/scripts/check_f_class_ledger.py` | 33,261 B | 729 | LF（CRLF 0） | 2026-11-08T00:44:53 | `5a2460ab4ae6a060c7b7b6fe410b4566b7047c6c123fccdbc27963585164beae` | `5a2460ab4ae6a060c7b7b6fe410b4566b7047c6c123fccdbc27963585164beae` |
| `docs/factors/F_CLASS_REGISTRATION_20261107.md`（本文件） | 自指，不记 | — | LF（CRLF 0） | 自指，即本行写入时刻（v5.8） | 自指，不记：每次运行由自检脚本 BINDING 段打印 | 自指，不记（同上） |

**行数口径（v5.8 补；v5.11 数值同步为 163,451 B / 2758 个换行符）**：本表「行」= 文件内换行符（LF）个数（末行无换行符时不计入），与自检脚本 `BINDING` 段打印的 `lines` 同口径；registry 124,794 B 即 2,164 个换行符 = 2,165 个内容行（`wc -l` 同得 2,164，`splitlines()` 得 2,165）。

## 0.2 定稿声明（v5.5 起；v5.6 按本条另立版本）

**台账自 v5.5 起定稿，因子工程师此后不再改本文件与机器可读 registry。**

> **v5.6（2026-11-07 19:21）：按本条「另立版本号、重报三文件指纹」的例外程序执行一次** —— 开发经理 18:05 重生成引用因子盘存产物（186,343 B / `b661c8cd…`），因子工程师按契约 v0.6 §7.12.4 **独立复算** `canonical_digest = aefdf528…2d1a`（与产物字段逐位相同）后把期望表重签到现行字节（v3.2→v3.3），故 §12.1 末行的期望表指纹随之更新为 `97,062 B / 8366cdb2…`。**8 只因子公式、warmup、deps、双 id 三列、`replaced_by`、K10/K11/K12 与台账内任何数字/结论一律未动。** 机器可读版记在 JSON `v5_6_changes[0]`，`freeze_declaration.declared_at = 2026-11-07T19:21+0800`。

> **v5.7（2026-11-07 19:28）：按同一条例外程序再执行一次** —— 18:05 那份产物在 **19:23:57 又被重跑**：size 仍 186,343 B、`records` 仍 218、`canonical_digest` 仍 `aefdf528…2d1a`，只有 `generated_at` 变（全文 sha 由 `b661c8cd…` → `df5e1a63…`）。v5.6 把签名绑在 `b661c8cd…` 那份字节上，被一次「只改 `generated_at`」的重跑推翻 —— 这是**签错对象**（签了字节、没签契约规定的三元组），不是产物错。按契约 v0.6 §7.12.4（签认对象 = `canonical_digest` + `schema_version` + `scanned_sources`；旁挂 `.sha256` 只证「本次运行字节完整」）期望表升 **v3.4**：改为签三元组，字节哈希降为观测记录（`byte_instances_observed` 两条：18:05:22 `b661c8cd…`、19:23:57 `df5e1a63…`，两者同 digest），并写 `byte_sha_policy`。§12.1 末行的期望表指纹随之更新为 `99,935 B / 184dcdf9…`。**8 只因子公式、warmup、deps、双 id 三列、`replaced_by`、K10/K11/K12 与台账内任何数字/结论一律未动。**另：**19:37 按同一例外程序就地修正 freeze 状态格** —— registry `meta.freeze_declaration.status` 由 `FROZEN at v5.6` 改为 `FROZEN at v5.7`（与 `meta.version=5.7` 一致；`declared_at` / `revised_at` 同步为实际写入分钟 `2026-11-07T19:37+0800`）；registry 字节随之变化，§0.1 的 registry 指纹同步重测为 `56d30928…`（size 119,029 B / 行数 2088 / CRLF 0 三项不变）。**本轮只改这一格：8 只公式、warmup、deps、双 id 三列、`replaced_by`、K10/K11/K12、`signature_triple`（`aefdf528…2d1a` / `2` / `67`）一律未动。**

> **v5.8（2026-11-07 22:29）：记账修复，数字一律不动** —— 三处真缺陷：①自检 `REAL_EXIT=1 / RESULT: FAIL / RECORD MISMATCHES: 2`：脚本 21:34:11 那版已实现 `[10] freeze_declaration_version_agree` 与 `[11] md_fingerprint_matches_registry`，但 JSON `self_check.checks` 只登记 9 条 → 「按台账里写的数必须是跑出来的数」把我判 FAIL；这两条 violations 本身都是 0，坏的是登记。②签认三元组此前只以散文存在（`v5_6_changes.basis` / `v5_7_changes.basis` 的句子里），JSON 全树 walk `signature*` **0 命中** → 新增顶层结构化 `signature` 块（`canonical_digest` / `schema_version` / `scanned_sources` / `recipe` / `signed_at` / `signed_object` / `byte_instances_observed[]`），按 **recipe 1** 填 `aefdf528…2d1a` / `"2"` / `67`，**不预填 recipe 2 任何值**（产物无 `canonical_digest_recipe` 字段，且 R8 的 recipe 2 已被独立审核退回）。③期望表 md 仍 `v3.3`（正文写着「机器可读副本 97,062 B / 8366cdb2」）、json 已 `v3.4`（99,935 B / `184dcdf9…`），两边错位 → md 同步到 v3.4。**v5.7 名下已存在两种字节（19:37:46 与 19:37:15 之前那一版），同一版本号对应两种字节不可签，故 v5.7 的两个字节态均不得被引用**，一律以 v5.8 为准。**8 只公式、warmup、deps、shift、双 id 三列与 `alias_side`、`replaced_by` 四条、K1–K12 一律未动。**（同轮一处纯键名修订：签认块内说明键 `recipe_2_note` 改名为 `unspecified_value_note`，正文含义不变，只为避免机械 walk 把键名误读成「已填 recipe 2 的值」；registry 字节随之再变，§0.1 registry 行指纹同步重测为 124,794 B / 2164 行 / `9bfbb020…`，`canonical_digest` 仍 `aefdf528…2d1a` / `"2"` / `67`。）

> **v5.9（2026-11-08 00:40）：准入载体批，公式与数值一律不动** —— 本批四项：①8 只 `uf_*` 的盘上 `status` 由 `draft` 升 `active`（逐只带三条实测：V3 全量 `pass_1e12=true`、V3 末交易日全市场截面 `rank_change_max=0.0`、B0 保真 `max_abs_diff=0.0`）；②8 组双 id 的 alias 侧 `alias_of` / `strategy_usable=false` 载体核验（在 pack，不在盘上 JSON）；③`market_breadth` 与 6 个 pack 单侧件的登记缺口**如实记成缺口**，不用「近似因子」或伪造字段糊过去。**8 只公式、`warmup_bars`、`dependencies`、`shift`、双 id 三列、`replaced_by` 四条、K1–K12 一字未动**；`signature` 三元组（`aefdf528…2d1a` / `"2"` / `67`）不动。详见新增 §15。registry 字节随之变化，§0.1 registry 行指纹重测为 145,985 B / 2500 行 / `7029c912…`。④自检 `[4]` 与 `BINDING` 段的**判据对象由「版本文件全文」改为「§7.1 块哈希」**（断言＝两份块的 LF 归一化 2,514 字符 / `6d3db013…` 与原始 CRLF 2,541 字符 / `a8e88134…` 都必须等于登记常量，且两份块在两口径上彼此相等；契约版本号不再参与判定，读取来源改指 v0.12）——原因、口径与负样本见 §12.3。**除 `[4]` 的绑定对象外，其余 10 条判据、全部数字、公式、warmup、`signature` 块与 K1–K12 一字未动。**
> **v5.10（2026-11-08 00:52）：勘误批，公式与数值一律不动** —— 三处台账自洽缺陷，全部是 v5.9 留下的，逐条有实测：①**8 只的 `strategy_usable_note` 与同行 `status` 相反**（v5.9 残留「status 仍 draft / usable_now=false」，而同行已是 `status=active` / `usable_now=true`）→ 逐只改写为引用本行 `admission_evidence_v5_9` 的现行结论，并新增 `status_carrier` 记载体路径（`D:/TSP/data/user_data/custom_factors/uf_*.json#status`）与写入时刻 `2026-11-07T23:33:57`。②**§15.5 把 G5 写大了一格**：原文称「`compile_formula('market_breadth')` 要成立还需打通注册因子 id → DSL 标识符这一层」，并以 `compile_formula('uf_vol60')` 同样 `E001` 作对照 —— 该对照是**假象**：同一 venv 里先 `store.load_all` + `register_factor` 后，`compile_formula('uf_vol60')` → `ok=True` / `warmup_bars=61`，即 id→标识符解析本来就在（`backend/app/factors/dsl.py:676/690` 走 `get_factor`，启动期由 `backend/app/main.py:217-221` / `backend/backtest/worker.py:234-236` 的 `load_into_registry` 装载）→ G5 的验收④降为「登记即通过」。③**6 个 pack 单侧件「补 status 还是闸门豁免」原本没有落笔** → 明确裁定**不豁免**（`gate.py:74` `EXEMPT_KINDS={base,virtual}`；§7.8.4 末行「provider 注册且无 status 按 draft 处理」），也不鼓吹补 status（无合法载体），交 G4；逐条记在 registry 新增顶层 `admission_carrier_rulings`。**并发写入登记**：本轮与另一条会话（「台账 BINDING 改绑 §7.1 块哈希」）在 00:44–00:46 同时写过本文件与 registry —— 脚本 00:44:53 改写、registry 与 md 于 00:45–00:46 各写一次；本版把两侧改动合并后重报三文件指纹（registry `158,382 B / 093f44c9…`），并以本次自检 `RESULT: PASS` 为唯一有效签认。**8 只公式、`warmup_bars`、`dependencies`、`shift`、双 id 三列、`replaced_by` 四条、K1–K12、`signature` 三元组一律未动。** 详见新增 §15.7。

> **v5.11（2026-11-08 00:56）：证据出处批，公式与数值一律不动** —— 三处，全部只补「能不能被第三方复算」与「缺口门票」：①done_when ② 的闸门证据由临时 here-doc 换成仓库内可复跑脚本 `research/b0b-20261107/verify_fs03_realdisk.py`：**9/9 PASS**（`P0`–`P2` + `A1`–`A6`），日志 `research/b0b-20261107/logs/fs03_realdisk.json`（8,245 B / `1e00af39…1f7e` / 2026-11-08T00:51:05），其中 `A6.disk_status_snapshot_info` 记 8 只 `status=active`；②**done_when ③ 未达成，如实记为未达成**：`market_breadth` 仍 `E001`（`grep backend/app` 0 命中）、目录计数仍 **110**，原因不是缺证据而是**没有登记载体**（登记=新增 `FactorSpec`=`backend/app/**` 代码），按 G5+G6 给实现门票；③把「110 怎么数出来的、变 111 要动哪两行测试常量」落成整表（`backend/tests/test_factor_registry.py:289-290`）。**8 只公式、`warmup_bars`、`dependencies`、`shift`、双 id 三列、`replaced_by` 四条、K1–K12、`signature` 三元组一律未动。** 详见新增 §15.8；registry 指纹重测见 §0.1。

- **唯一例外**：第三方直写造成的字节修复。修复须另立版本号、重报三文件指纹，不得静默覆盖。
- **定稿失效条件**：再出现任何第三方直写（行尾改写、字段增删、`indent=2` 重排皆算），本定稿立即失效；须以该刻盘面字节重算指纹并重新签认，**不得沿用本条或 §0.1 的任何指纹**。
- **可验证判据**：本 registry 的 LF 归一化 sha256 必须等于 §0.1 表所列值；本 md 的自指值只以 `docs/factors/evidence/scripts/check_f_class_ledger.py` 的 `BINDING` 段实跑打印为准（自指不入文件，见 §0.1 末条）。机器可读版同一句话记在 `meta.freeze_declaration.text`，`declared_at = 2026-11-07T19:21+0800`（v5.6）。
- **范围**：只覆盖 F 类 8 只台账三文件（本文 + registry + 自检脚本）。`docs/architecture/**`、`backend/**`、`docs/research/**`、`research/**` 与 `docs/factors/` 下他人文件不在本声明内。

**绑定对象（与 JSON `meta.contract_binding` / `meta.sources[0].binding` / `self_check.checks[3].rule` 同一对象；**v5.9 起判据对象是 §7.1 块，不是任何版本文件的全文**）**：自检 `[4]` 双绑 **① 归档冻结副本** `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`（89,833 B / 914 行 / 全文 LF 归一化 `4105c08d…`，不可变权威）与 **② 一份现行修订** `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md`（269,092 B / 2,248 行 / 全文 raw `d7df40ff…`、LF 归一化 `aa3679c4…`），后者**只作读取来源，版本号不参与判定**。断言三条：每份的 §7.1 块在两套口径下都等于登记常量；两份块在两口径上彼此相等；8 只的 `formula_text` / `warmup_bars` / `dependencies` 与两份逐字一致。任一不成立即 FAIL，并打印两处块的两种 sha。

**§7.1 块哈希的两套口径（引用时必须写明是哪一套）**：①**LF 归一化**（`CRLF`→`LF`，含块尾换行）**2,514 字符 / `6d3db0139a45f54c…`** —— 自检脚本实算、**判定用值**；②**保留原始 CRLF**（不折行，含块尾换行）**2,541 字符 / `a8e88134f60b504c…`** —— 团队通报用值。两者差 27 字符 = 27 行各一个 `CR`，**块文本一字不差**；所以引用「§7.1 块哈希」而不写口径即为歧义：写 `6d3db013…` 要带「LF 归一化 / 2,514」，写 `a8e88134…` 要带「原始 CRLF / 2,541」。第三种量法 2,513 / `e9ed2b10…`（同一块去尾换行）是 v5.3 曾用值，现已不用。

**为什么把「版本全文」换成「§7.1 块」（v5.9）**：v5.4–v5.8 的双绑实际只覆盖**指针所指的那一版**（归档 v0.3 + v0.6）；指针停在哪一版，就只有那一版的 §7.1 进比对视野 —— v0.7–v0.12 里 §7.1 被改写或漂移，自检一句都不会说，这是**漏拦**。改绑块哈希后，块本身成为**登记常量**：任何被指向的文件都必须携带同一块，改一个数字即 FAIL 并打印两处哈希（负样本实测见 §12.3）。**未编号活暂存 `FACTOR_ENGINE_CONTRACTS_20261107.md` 仍不绑**：多路写入、无法归因，无法把一次绿跑归因到任何一版。

**复算**（任一文件）：`python -c "import hashlib,sys;b=open(sys.argv[1],'rb').read().replace(bytes([13,10]),bytes([10]));print(hashlib.sha256(b).hexdigest())" <file>`

**为什么换口径**：`docs/factors/` 未纳入版本控制，没有历史可复算；本 JSON 与本文行尾在 2026-11-07 **16:45:33**（JSON CRLF→LF，89,492 B）与 **16:49:20**（再次 LF，89,510 B）被第三方改写两次，raw 字节 sha256 在几分钟内连着失效，而内容一字未变。**文件不能记录自身的归一化 hash（自指）**：所以本 registry 的 hash 记在这张表里、本文自己的 hash 只由脚本打印，两边都不自记。

依据（全部只读）：

| # | 文件 | 用在本文哪一节 |
| --- | --- | --- |
| 1 | `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md` §1（G1–G8）、§7.1、§7.2、§7.3、§7.5、§7.6 | 公式原文（逐字）、字段规则、禁止事项、验收判据 F-A1~F-A6 |
| 2 | `docs/research/caliber-decisions-20261107.md` §1.1–§1.5、§2.1、§4.1、§4.2 | 口径决定 D1/D2/D3；**编号以本文件为准**（D1=prior_* 口径、D2=rsi_14 涨跌幅、D3 并入 §1.5） |
| 3 | `docs/factors/FACTOR_GAP_SPEC_20261107.md` §0、§2（F1–F7） | 缺口编号与影响面（**编号与上一份不同**，见 §1.1） |
| 4 | `research/strategy-search-20261107/scripts/common.py:119-141` | 研究侧权威实现（`add_indicators`） |
| 5 | `docs/factors/evidence/compare_stats.json` | 数值证据（n / corr / mean_abs_diff / 判定 jaccard） |
| 6 | `docs/factors/STRATEGY_INPUT_FACTOR_MAP_20261107.md` §2、§3、§4 | 服务策略与「还缺什么」 |

机器可读版：`docs/factors/evidence/f_class_registry.json`（一条一只，字段同 §2.1/§2.2，另有 `self_check` 段）。
自检脚本：`docs/factors/evidence/scripts/check_f_class_ledger.py`（只读，见 §6）。

---

## 0. 一句话结论与本批边界

**8 只全部可编译，`warmup_bars` 与 `dependencies` 逐只与契约 §7.1 吻合（编译层实测，见 §2.10）；注册这件事本身零引擎改动（契约 §7.2 结论）；但 8 只今天一条策略都解锁不了** —— 每只都还压着 E2/E3/E4/X1，以及**已注册但一策未解锁**的 `dist_prior_high_250`（16:07 以 `uf_dist_prior_high_250` 落库、逐位对账 `max_abs_diff = 0.0`，见 §4.2；逐只看 §2.3–§2.9 的「解锁还需」）。

本批做了什么、没做什么，分开写清（别把「登记」读成「注册」）：

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 台账 + 映射（本文 + JSON） | **已做** | 8 只，字段齐全，公式逐字取契约 §7.1 |
| 命名映射唯一自检 | **已做（真跑）** | 0 违例，见 §6 |
| `compile_formula` 实测 | **已做** | 8/8 `ok=True`，warmup 依次 61/121/201/21/56/251/11/21，deps 与契约一致 |
| 写入运行库（注册） | **已由系统开发工程师完成（本台账未走 POST API）** | 8 个 `uf_*.json` 于 2026-11-07T14:30:24 写入 `D:/TSP/data/user_data/custom_factors/`；启动期 `load_into_registry` 装载 15 条定义后 8/8 可取（注册表 **207** 条，实测 §2.10）。**运行中的服务未重启 → 线上进程未加载**（对账报告 §6 未验证项） |
| 批二 `uf_dist_prior_high_250`（不在本批 8 只内） | **已做（系统开发工程师 16:07；本台账未参与，只引用）** | 落库 version 1、`warmup=251`、deps `{close, high}`；vs 研究侧 `dist_52w_high` 逐位 **`max_abs_diff = 0.0`**（n = 5,332,523）、`dist >= -0.03` jaccard **1.000000**；详见 §4.2 |
| F-A3 / V3 数值对账 | **已做（系统开发工程师），本文只引用不复算** | 证据 `docs/factors/evidence/F_CLASS_PARITY_20261107.md`（运行于 14:36:40）：8/8 PASS、7 只 `max_abs_diff=0.0`、`uf_vol60` 1.11e-16（1 ULP，超 1e-12 行数 0）、null 与首根非空全一致、5 条判定 jaccard 1.000。独立审核 `research/independent-review-20261107/F_CLASS_AUDIT_20261107.md:19` 判 F-A3 **PASS**（自有脚本复算 `max_abs_diff ≤ 2.78e-17`）；同报告 `:21` 判 **F-A5 FAIL**（同内容二次注册 version 1→2） |
| F-A5 注册幂等 | **独立审核实测 FAIL（本人未复测）** | 同内容二次注册 version 1→2、文件被重写，8 只全中（`F_CLASS_AUDIT_20261107.md:21`，根因 `lang` 键不对称）；批二 `uf_dist_prior_high_250` 复跑 `unchanged=true`（单因子，不等于 F-A5 已修） |
| F-A6 单位量级 | **系统侧已测（`F_CLASS_PARITY` §2），判据口径待架构师收口** | 系统侧 `uf_vol60`：mean 0.0261 / p50 0.0247 / p01 0.0090 / p99 0.0549；研究侧 p10/p50/p90 = 0.01410/0.02471/0.03976。**逐值读契约字面区间 0.015–0.06 会误伤 p01（0.0090 < 0.015）**，故建议改分位数口径（独立审核 P1-2 已改写），见 §1.2 K4 |
| 改 `pipeline.py:189-190` 显示名 | **未做** | D1 §1.3 的配套强制动作，归系统开发工程师；本文只登记 |

---

## 1. 编号与来源对齐（先读，避免对接错项）

### 1.1 编号对照

| 本台账 | caliber-decisions（策略经理） | FACTOR_GAP_SPEC | 说明 |
| --- | --- | --- | --- |
| D1 | 决定 1（§1） | D1 | 同一项：此前高/低点口径 |
| D2 | 决定 2（§2） | D2（转达时曾写作 D3） | 同一项：`rsi_14` 涨跌幅口径。**以 gap spec 的 D2 为准** |
| D3 | 并入 §1.5「命名与台账规范」 | D3 | 同一项：`prior_*` 命名规范 |
| F-A1~F-A6 | — | §2 F1–F7 | 本批 8 只 = F-A1 的 8 个 id；F7（`prior_amount_20`）**不在本批**，见 §4 |

### 1.2 跨文档不一致（登记，不擅自裁定，也不"顺手对齐"）

| # | 不一致 | 事实 | 本文处理 |
| --- | --- | --- | --- |
| K1 | 同一 `prior_*` 两种写法 | 契约 §7.1：`ts_max(ts_delay(high, 1), 20)`；D1 §1.4 与 gap spec §2：`ts_delay(ts_max(high, 20), 1)` | **一律采用契约 §7.1 原文**。两者代数等价（shift 与 rolling_max/min 可交换；DSL `min_samples=n`，首根非空同为第 N+1 根），**但本批未做数值比对 → 登记为待 V3，不写「已证等价」**。实测两种写法 `compile_formula` 均 `ok=True`、`warmup=21`、`deps={high}` |
| K2 | `vol60` 写法 | 契约 §7.1：`ts_std(close / ts_delay(close, 1) - 1, 60)`；gap spec §2：`ts_std(change_pct, 60)`（称「等价，实测平均绝对差 0」） | **采用契约原文**（`deps` 只有 `{close}`，不依赖 `change_pct` 的路径相关单位） |
| K3 | 契约 §7.1 坑 3 的「大 100 倍」在因子路径上未被证实 | `*100` 只出现在 `backend/app/api/intraday.py:72`（分时展示）；因子/回测路径的 `change_pct` 是小数（`app/indicators/pipeline.py:156` 注释「日涨跌幅(小数, 如 0.05 = 5%)」、`:539` `close / shift(1) - 1`、`app/backtest/matrix.py:4264`）。实测与研究 `ret1` 的 `max_abs_diff=2.220446049250313e-16`、`mean_abs_diff=3.993677303356903e-17`（`compare_stats.json#pairs.ret1_vs_change_pct`，n=5,509,326） | **「同一名字有两条单位不同的计算路径」= 风险确证；「用 change_pct 得 100 倍」= 在本路径上未被证实**。台账按契约写法执行；此条供架构师修订 §7.1 措辞（本文不改契约） |
| K4 | F-A6 量级区间与研究侧分位数边界 | F-A6 写 `vol60` 典型值 0.015–0.06；研究侧 `p10=0.01409676135750348`（略低于 0.015）、`p50=0.02470624360457813`、`p90=0.03975800629232132`（`compare_stats.json#series.vol60_dist`） | 登记差异；建议 F-A6 改成**分位数口径**（如 p50 落在区间内、p90 < 0.1）。本批不改契约，待架构师裁定 |
| K5 | 调仓日依赖策略数 | `STRATEGY_INPUT_FACTOR_MAP` §S03 行写「12 条中 7 条（S03/S06/S07/S08/S10/S11/S12）」，§3 横向写「8/12 条依赖」，团队记忆也是 7 条 | 属 E4 契约范围，**不属本批**；只登记供核对，不裁定 |
| K6 | 既有证据文件编码 | `compare_stats.json#series.prior_low10_missing.note` 为乱码（GBK/UTF-8 混写），同文件其余字段正常 | 不改既有文件；引用该注文前需重生成 |
| K7 | `uf_vol60` 1 ULP 的根因归因 | 对账报告 §7 归因于「`_safe_div` 掩码除法改变内核路径」；**独立审核实测相反**：`DSL vs 普通除法 max_abs_diff=0.0`、`研究 pct_change vs 普通除法 = 1.1102230246251565e-16`（4,214,876 行），即**差异 100% 来自研究侧 `close.pct_change()`**（`research/independent-review-20261107/F_CLASS_AUDIT_20261107.md:84-95`、P3-3 `:237`、§9 第 9 行 `:252`；原始记录 `artifacts/fa3_vol60_ulp_rootcause.txt`） | 本文按审核实测表述：**与 `_safe_div` 无关，不保留该假设**。对账报告 §7 的措辞由系统开发工程师更正（本文不改他人文件） |
| K8 | 同口径双 id 共 **8 组**（v3 及以前写「3 个裸 id / 4 项」，**错**） | pack `backend/app/custom/research_factor_pack/factor_specs.py` 以裸 id 注册 **14** 个（`ma20`/`ma60`/`ma120`/`ma200`/`boll_lower`/`boll_upper`/`sd20`/`vol60`/`prior_high_20`/`prior_high_55`/`prior_high_250`/`prior_low_10`/`prior_vol_20`/`prior_amount_20`）；`D:/TSP/data/user_data/custom_factors/` 下 **15** 个 JSON（14 个 `uf_*` + 1 个 `cf_auction_resonance`，逐个 `json.load` 读 `id`）；**交集 8 组** = `ma120`/`ma200`/`vol60`/`prior_high_20`/`prior_high_55`/`prior_high_250`/`prior_low_10`/`prior_vol_20`。**两条单侧例外（都不是双 id）**：`prior_amount_20` 无 `uf_prior_amount_20` 对应件 → canonical 定为研究原名（§4.1）；`uf_dist_prior_high_250` 无 pack 对应件 → 单侧件，映射行见 §2.1b 第 10 行（§4.2）。 | **已裁定（`ID-CANON-1`，`docs/architecture/ARCH_DECISION_FACTOR_ID_CANONICAL_20261107.md`）**：canonical 一律 = store 侧 `uf_*`；pack 研究原名 = **alias**（`alias_of` + `strategy_usable = false`；生产入口 `FS03` 拒，研究/诊断入口允许并标 `deprecated_alias_used`）。**`replaced_by` 只表跨口径取代、严禁用于别名** —— v1–v3 本行「另一侧标 `replaced_by` 并策略禁用」是**错的写法**，v4 已改；逐行归属见 §2.1b |
| K9 | 台账 `label` 与磁盘定义 8/8 不同 | 例（实测 `D:/TSP/data/user_data/custom_factors/uf_vol60.json`）：磁盘 `60日收益波动率` vs 台账 `60日收益标准差（日频，未年化）`；`uf_prior_vol_20.json` 磁盘 `此前20日均量` vs 台账 `此前20日均量（不含当日）`。「含当日 / 不含当日 / 未年化」这些口径语义只活在台账（`F_CLASS_AUDIT_20261107.md` P2-4 `:226-228`） | **登记，不裁定**：建议以台账 label 覆盖磁盘定义（系统架构师定）。裁定前**语义以本台账为准**，前端 label 不作口径证据 |

---

## 2. 8 只台账

### 2.1 口径主表（一行一只）

`formula_text` 一律逐字取契约 §7.1，**不做改写、不做"顺手优化"**。`warmup_bars` 是 `compile_formula` 的推导值（契约 §7.2：DSL 路径由编译推导，手填无效），本文的值已实测复原。

| 研究名 | uf_ id | formula_text（契约 §7.1 原文） | warmup_bars | dependencies | semantics | shift | price_basis | unit | scale_free | strategy_usable | replaces / 被替换 | 服务策略 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vol60 | uf_vol60 | `ts_std(close / ts_delay(close, 1) - 1, 60)` | 61 | {close} | incl_today_close | 0 | close | ratio（无量纲小数） | true | true | 无跨口径取代；不可被 annual_vol_20d 替代（低波十分位 jaccard 0.136）。**裸 id `vol60` 是 alias（`alias_of = uf_vol60`），不是 `replaced_by`**（K8、§2.1b） | S07 核心；S11 排名项；S12 核心 |
| ma120 | uf_ma120 | `ts_mean(close, 120)` | 121 | {close} | incl_today_close | 0 | close | price（元） | false | true | 无跨口径取代；**裸 id `ma120` 是 alias（`alias_of = uf_ma120`），不是 `replaced_by`**（K8、§2.1b） | S03 趋势过滤；S08 趋势过滤 |
| ma200 | uf_ma200 | `ts_mean(close, 200)` | 201 | {close} | incl_today_close | 0 | close | price（元） | false | true | 无（无策略使用，P1 补台账）；**裸 id `ma200` 是 alias（`alias_of = uf_ma200`），不是 `replaced_by`**（K8、§2.1b） | 无 |
| prior_high_20 | uf_prior_high_20 | `ts_max(ts_delay(high, 1), 20)` | 21 | {high} | prior | 1 | high | price（元） | false | true | 无 | S02 入场 |
| prior_high_55 | uf_prior_high_55 | `ts_max(ts_delay(high, 1), 55)` | 56 | {high} | prior | 1 | high | price（元） | false | true | 取代 high_60d（即 high_60d 的 replaced_by = 本因子） | S09 入场 |
| prior_high_250 | uf_prior_high_250 | `ts_max(ts_delay(high, 1), 250)` | 251 | {high} | prior | 1 | high | price（元） | false | true | 无 | S08（间接：作 dist_prior_high_250 的分母） |
| prior_low_10 | uf_prior_low_10 | `ts_min(ts_delay(low, 1), 10)` | 11 | {low} | prior | 1 | low | price（元） | false | true | 取代 `low_60d`（即 `low_60d` 的 `replaced_by` = 本因子，降级替换、非同口径等价；§2.8） | S02 出场 |
| prior_vol_20 | uf_prior_vol_20 | `ts_mean(ts_delay(volume, 1), 20)` | 21 | {volume} | prior | 1 | volume | 未确证（股/手） | false | true | 无（vol_ma20 不存在） | S09 量能确认 |

两条读表须知：

1. `strategy_usable=true` 表示「这个口径本就是给策略用的」，**不等于现在可以引用**：8 只全部 `status=draft`（磁盘定义 `status=draft`）：**已落盘、启动期装载后 8/8 可取**，F-A3 已由系统开发工程师对账（§7，本台账不复算）；契约 §7.5 第 5 条禁止未过 V3 标 `active`，故仍是 `draft`。JSON 里另有 `usable_now=false` 明确这件事。
2. `scale_free` 有两层：`prior_vol_20` 本身带成交量量纲（`scale_free=false`），但在 S09 里用法是 `volume / prior_vol_20` 的比值，尺度自消（JSON 记 `scale_free_as_used=true`）。


### 2.1b 双 id 与别名归属（`canonical_id` / `aliases[]` / `superseded_by[]` / `canonical_reason` / `replaced_by`）

裁定：`ID-CANON-1`（`docs/architecture/ARCH_DECISION_FACTOR_ID_CANONICAL_20261107.md`）。**canonical 一律 = store 侧 `uf_*`；pack 研究原名 = alias**（写 `alias_of` + `strategy_usable = false`，生产入口 `FS03` 拒，研究/诊断入口允许并标 `deprecated_alias_used`）。**`replaced_by` 只表跨口径取代，严禁用于别名** —— 别名用 `alias_of`。

| # | `canonical_id` | `aliases[]`（pack 裸 id = 研究原名） | `superseded_by[]`（canonical 行） | alias 侧 `superseded_by[]` | `canonical_reason` | `replaced_by` | `alias_of` | alias 侧 `strategy_usable` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `uf_vol60` | [`vol60`] | `[]` | [`uf_vol60`] | store 侧有 status/version/命名空间，且其 `formula_text` 是契约 §7.1 原文（`ts_std(close / ts_delay(close, 1) - 1, 60)`）；pack 侧文本为 `ts_std((close - ts_delay(close, 1)) / ts_delay(close, 1), 60)`（数学等价、非逐字）→ 以 store 为 canonical，pack 文本留档不改 | 无 | `alias_of = uf_vol60` | `false` |
| 2 | `uf_ma120` | [`ma120`] | `[]` | [`uf_ma120`] | 两侧公式**逐字相同**（`ts_mean(close, 120)`）；store 侧有 status/version | 无 | `alias_of = uf_ma120` | `false` |
| 3 | `uf_ma200` | [`ma200`] | `[]` | [`uf_ma200`] | 两侧公式**逐字相同**（`ts_mean(close, 200)`）；store 侧有 status/version | 无 | `alias_of = uf_ma200` | `false` |
| 4 | `uf_prior_high_20` | [`prior_high_20`] | `[]` | [`uf_prior_high_20`] | store `ts_max(ts_delay(high, 1), 20)` 为契约 §7.1 原文；pack `ts_delay(ts_max(high, 20), 1)` 是 K1 的另一种写法（代数等价，本台账一律采用契约原文） | 无 | `alias_of = uf_prior_high_20` | `false` |
| 5 | `uf_prior_high_55` | [`prior_high_55`] | `[]` | [`uf_prior_high_55`] | 同上（窗口 55）；canonical 是 `high_60d.replaced_by` 的**目标**（跨口径取代，§2.6） | `[]`（无跨口径取代指向本因子）；**本因子 `replaces = ['high_60d']`**（§2.6） | `alias_of = uf_prior_high_55` | `false` |
| 6 | `uf_prior_high_250` | [`prior_high_250`] | `[]` | [`uf_prior_high_250`] | 同上（窗口 250） | 无 | `alias_of = uf_prior_high_250` | `false` |
| 7 | `uf_prior_low_10` | [`prior_low_10`] | `[]` | [`uf_prior_low_10`] | 同上（`ts_min(ts_delay(low, 1), 10)`）；canonical 是 `low_60d.replaced_by` 的**目标**（降级替换，§2.8） | `[]`（无跨口径取代指向本因子）；**本因子 `replaces = ['low_60d']`**（§2.8） | `alias_of = uf_prior_low_10` | `false` |
| 8 | `uf_prior_vol_20` | [`prior_vol_20`] | `[]` | [`uf_prior_vol_20`] | 同上（`ts_mean(ts_delay(volume, 1), 20)`） | 无 | `alias_of = uf_prior_vol_20` | `false` |
| 9 | `prior_amount_20`（**canonical = 研究原名**） | `[]` | `[]` | —（无 alias，本身即 canonical） | **单侧例外**：store 目录 15 个 JSON 逐个读 `id`，**无** `uf_prior_amount_20`；pack 侧已注册且逐位对账 `max_abs_diff = 0`（n = 5,496,401，§4.1）→ 架构裁定明文例外：「无 store 双胞胎，canonical 定为研究原名」 | 无 | —（本身即 canonical，不设 alias） | `true`（canonical 侧；pack 注册、`unit = CNY`、`shift = 1`，§4.1） |
| 10 | `uf_dist_prior_high_250` | `[]`（研究侧列名 `dist_52w_high` **不是**注册 id） | `[]` | —（无 alias，本身即 canonical） | **单侧例外**：pack 14 个 id **无**对应件；`common.py:157` 的 `dist_52w_high = close / prior_high250 - 1` 与落库公式 `close / ts_delay(ts_max(high, 250), 1) - 1` 同一物 —— **本台账 16:20 实测 `max_abs_diff = 0.0`、n = 5,584,049、非零差 0 行、null 不一致 0 行**（另见 §4.2 的 b2 报告 0.0 / n = 5,332,523，窗口不同） | 无（本因子是 `distance_to_high_240d.replaced_by` 的目标，跨口径，§4.2） | —（研究侧名称未注册，无需 alias 机制；**若将来注册，必须 `alias_of = uf_dist_prior_high_250`**） | `true`（canonical 侧；§4.2） |

读表须知（四条，防误用）：

1. §2.1 第 11 列 `strategy_usable` 描述的**始终是 canonical（`uf_*`）侧**；alias 侧（pack 裸 id）一律 `false`，**不得**用它写策略规格或实现代码。
2. `replaced_by` 在本台账只表**跨口径取代、不是别名**，**取值只有两种（v5 起统一）**：目标**已注册** → 写 **canonical id**（`uf_*` / `cf_*` 开头）；目标**未注册** → 写 **`null`**，原名放 `replaced_by_declared_name` 并置 `target_registered = false`。**任何研究原名都不得出现在 `replaced_by` 字段里。**JSON `replacement_rulings` 共 **4 条** —— `high_60d` → `uf_prior_high_55`（§2.6）、`low_60d` → `uf_prior_low_10`（§2.8）、`distance_to_high_240d` → `uf_dist_prior_high_250`（§4.2）、`rsi_14` → **`null`**（`replaced_by_declared_name = rsi_14_pct`、`target_registered = false`；§4.3，**目标尚未注册**）；`id_canonical_ruling.replaced_by_rulings_cross_caliber_only` 只列**目标已注册**的 3 条，二者不矛盾（差的那条 = `rsi_14_pct` 目标尚未注册，见 §4.3 与 JSON `known_doc_conflicts` 的 K12，K12 已在 v5 置「已关闭」）。§10 / §11 的历史行里出现的 `prior_high_55` 一类写法是 v5 之前的旧写法，**只作历史记录、不得当字段值引用**。**别名一律用 `alias_of`**，台账里任何「同一口径的另一个名字」都不得写成 `replaced_by`。
3. 机器可读版 `f_class_registry.json` 的 8 条 factor 记录已同步带 `canonical_id` / `aliases` / `superseded_by` / `canonical_reason` 四字段（另加 `alias_side_superseded_by` 便于消费方直读）；8 组的逐组行在 `id_canonical_ruling.dual_id_groups`（含 `alias_side`），两条单侧例外在 `id_canonical_ruling.single_sided_exceptions`；字段分工见 `column_semantics`。
4. **`superseded_by` 与 `replaced_by` 不是同义字段**（契约 §7.8.2 A-1 用前者，架构裁定 §2.2 台账规则用后者，本台账两者并存）：`superseded_by` 记「**同一口径内**这一行 id 让位给谁」——canonical 行恒 `[]`，alias 行 = `[canonical_id]`；`replaced_by` 记「**跨口径**被谁取代」，只有读表须知 2 的 3 处。把 alias 写进 `superseded_by` 以外的取代字段、或把跨口径取代写进 `aliases[]`，都算错。

### 2.2 治理字段（`FactorSpec` 逐字段，按契约 §7.2 的填写规则）

| 研究名 | uf_ id | label（≤32 字） | group | kind / lang | version · status | direction | null_policy | pit / pit_source | asset_types |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vol60 | uf_vol60 | 60日收益标准差（日频，未年化） | 研究补充 | custom / dsl | 1 · draft | none | keep | false / none | stock, etf |
| ma120 | uf_ma120 | 120日均线（含当日） | 研究补充 | custom / dsl | 1 · draft | none | keep | false / none | stock, etf |
| ma200 | uf_ma200 | 200日均线（含当日） | 研究补充 | custom / dsl | 1 · draft | none | keep | false / none | stock, etf |
| prior_high_20 | uf_prior_high_20 | 此前20日最高价（不含当日） | 研究补充 | custom / dsl | 1 · draft | none | keep | false / none | stock, etf |
| prior_high_55 | uf_prior_high_55 | 此前55日最高价（不含当日） | 研究补充 | custom / dsl | 1 · draft | none | keep | false / none | stock, etf |
| prior_high_250 | uf_prior_high_250 | 此前250日最高价（不含当日） | 研究补充 | custom / dsl | 1 · draft | none | keep | false / none | stock, etf |
| prior_low_10 | uf_prior_low_10 | 此前10日最低价（不含当日） | 研究补充 | custom / dsl | 1 · draft | none | keep | false / none | stock, etf |
| prior_vol_20 | uf_prior_vol_20 | 此前20日均量（不含当日） | 研究补充 | custom / dsl | 1 · draft | none | keep | false / none | stock, etf |

`direction` 全部 `none`：契约 §7.2 写死「未经检验一律 `none`」，本批没有任何 IC 检验，不得预填方向。
`group` 单列「研究补充」：契约 §7.2 要求，避免打乱既有前端分组顺序。
`unit` / `scale_free` / `asset_types` / `tags` 在 `store.to_spec` **不落盘**（契约 §7.2 已登记为 P2 缺口）——所以这几个字段只在本台账与 JSON 里成立，注册表里查不到，**禁止任何自动加权逻辑依赖它们**。

### 2.3 vol60 → uf_vol60

| 项 | 值 | 依据 |
| --- | --- | --- |
| 研究侧原文 | `pl.col("ret1").rolling_std(60).over("symbol").alias("vol60")`，`ret1 = pl.col("close").pct_change()` | `common.py:140`（`ret1` 在 `:126`） |
| 语义 | 含当日（窗口含 T 日 bar），日频、**未年化** | gap spec §F1；契约 §7.1 末注 |
| ddof | 研究侧 polars `rolling_std` 默认 ddof=1；DSL `ts_std` = `rolling_std(n, min_samples=n)`（`backend/app/factors/dsl.py:398-399`）→ **两侧默认一致** | 读码；数值对账未做 |
| 单位 | 无量纲小数；研究侧 p10/p50/p90 = 0.01410 / 0.02471 / 0.03976 | `compare_stats.json#series.vol60_dist` |
| 不可替代性 | 与 `annual_vol_20d`（20 日、年化）：corr 0.777195、spearman 0.788756、`mean_abs_diff` 0.372369、p95 0.729613（n=5,469,335）；把 vol60 年化后再比仍 `mean_abs_diff` 0.091912、p95 0.247047；低波十分位选股 jaccard **0.136** | `compare_stats.json#pairs.vol60_vs_annual_vol_20d`、`#pairs.vol60_ann_vs_annual_vol_20d`；jaccard 见 `STRATEGY_INPUT_FACTOR_MAP` §S07 |
| 服务策略与解锁 | S07（核心量）/ S11（`rk_vol60` 的被排序量）/ S12（核心量） | **还缺**：E2 掩码 `xs_rank`、E4 `month_end`、E3 `in_universe`、X1 生产侧执行器（S12 另缺 E1 `market_breadth`） |
| 年化口径 | 若要年化必须是**另一个 id**（如 `uf_vol60_ann`），禁止原地改公式 | 契约 §7.1 末注。注：DSL 无 `**`（实测 `ts_std(...) * 252 ** 0.5` 编译失败），年化只能写 `ts_std(...) * sqrt(252)`（实测可编译，warmup=61） |
| 保真 | **已对账（系统开发工程师，`F_CLASS_PARITY_20261107.md` §2），本台账不复算**：`max_abs_diff = 1.1102230246251565e-16`（1 ULP，超 1e-12 行数 **0**）、n = 5,469,335、null 不一致 0 行；独立审核判 F-A3 **PASS** | `docs/factors/evidence/F_CLASS_PARITY_20261107.*`；`research/independent-review-20261107/F_CLASS_AUDIT_20261107.md:19` |

### 2.4 ma120 / ma200 → uf_ma120 / uf_ma200

| 项 | ma120 | ma200 | 依据 |
| --- | --- | --- | --- |
| 研究侧原文 | `pl.col("close").rolling_mean(120)` | `pl.col("close").rolling_mean(200)` | `common.py:124`、`:125` |
| warmup | 121 | 201 | 编译实测 |
| 语义 | 含当日、前复权、`min_samples=N`（不足即 null，不填充） | 同左 | gap spec §F2/F3 |
| 交叉检查靶值 | `close > ma120` 站上占比应复现 **46.805%**（`compare_stats.json#series.ma120_bias_ref.share_above = 0.46805341010249374`） | ma200 参考值 0.48478402455295033（gap spec 未给靶值） | 研究侧实测，注册后用作交叉检查 |
| 服务策略 | S03（`close > ma120` 趋势过滤）、S08（过滤） | 无 | `STRATEGY_INPUT_FACTOR_MAP` §S03/§S08；gap spec §F3「暂无」 |
| 解锁还需 | S03: E4 `month_end`、E3、X1；S08: `dist_prior_high_250`（§4）、E4、E3、X1 | — | 同左 |
| 保真 | **已对账（系统开发工程师，`F_CLASS_PARITY_20261107.md` §2），本台账不复算**：两只均 `max_abs_diff = 0.0`（n = 5,428,988 / 5,371,122），null 与首根非空两侧全一致。注：v1 依据的 `compare_stats` 只有 `ma20`/`ma60` 的 0 差、**没有 ma120/ma200 条目** —— 那条旁证不能顺延，本行结论来自新的对账报告 | 同左（两只合并说明在 ma120 格） | `docs/factors/evidence/F_CLASS_PARITY_20261107.*` |

### 2.5 prior_high_20 → uf_prior_high_20

| 项 | 值 | 依据 |
| --- | --- | --- |
| 研究侧原文 | `pl.col("high").shift(1).rolling_max(20).over("symbol").alias("prior_high20")` | `common.py:131` |
| 语义 | 此前 20 根 bar 的最高价（**不含当日**）；比较值仍是当日收盘 | D1 §1.1 |
| 服务策略 | S02 入场 `close > prior_high_20` | `STRATEGY_INPUT_FACTOR_MAP` §S02 |
| 解锁还需 | E3 `in_universe`、X2 `max_hold_days`（S02 不需 E4/X1） | 同左 §3、§4 |
| 替换关系 | 无。**不是 `high_60d` 的替代品**（窗口 20 vs 60、价基 high vs close、含当日 vs 不含，三项全不同）；D1 §1.4 明示**不注册 `prior_high_60`** | D1 §1.4 |
| 保真 | **已对账（系统开发工程师），本台账不复算**：`max_abs_diff = 0.0`（n = 5,496,401）；S02 入场判定 `close > prior_high_20` jaccard **1.000000**（both_true 272,155，仅系统侧 0 / 仅研究侧 0，研究侧触发率 4.952%） | `F_CLASS_PARITY_20261107.md` §2 / §3 |

### 2.6 prior_high_55 → uf_prior_high_55

| 项 | 值 | 依据 |
| --- | --- | --- |
| 研究侧原文 | `pl.col("high").shift(1).rolling_max(55).over("symbol").alias("prior_high55")` | `common.py:132` |
| 服务策略 | S09 入场 `close > prior_high_55` | 同左 §S09 |
| 替换关系 | **`high_60d` 的 `replaced_by` = 本因子**（D1 §4.2 显式指定）。注意这是**降级替换**，不是同口径等价：两者突破判定 jaccard = **0.000**（§5） | D1 §4.2、§1.2 |
| 数值证据 | vs `high_60d`：corr 0.999642、`mean_abs_diff` 0.4230 元、判定 jaccard **0.000**、仅研究侧成立 143,747 行、仅系统侧成立 **0** 行（n=5,470,011） | `compare_stats.json#pairs.prior_high55_vs_high_60d`、`#signals.s09_break_vs_high_60d` |
| 解锁还需 | S09 另一条腿 `prior_vol_20` 在本批（同样已落盘、装载后可取）；E3 `in_universe`；生产侧 X1（若走生产链路） | 同左 §S09、§3 |
| 保真 | **已对账（系统开发工程师），本台账不复算**：`max_abs_diff = 0.0`（n = 5,472,715）；`close > prior_high_55` jaccard **1.000000**（both_true 143,778，仅系统侧 0 / 仅研究侧 0） | `F_CLASS_PARITY_20261107.md` §2 / §3 |

### 2.7 prior_high_250 → uf_prior_high_250

| 项 | 值 | 依据 |
| --- | --- | --- |
| 研究侧原文 | `pl.col("high").shift(1).rolling_max(250).over("symbol").alias("prior_high250")` | `common.py:133` |
| 服务策略 | S08，但**是间接的**：S08 的判据是 `dist_prior_high_250 = close / prior_high_250 - 1`（D1 §1.4），而 `dist_prior_high_250` **已以 `uf_dist_prior_high_250` 注册并对账 `max_abs_diff = 0.0`**（§4.2） | D1 §1.4、§4.2 |
| 替换关系 | 无。`distance_to_high_240d` 不能由本因子替代，也不能互相替代；后者的替补是 `dist_prior_high_250` | D1 §1.2 末段 |
| 参考数值（不是本因子的） | 近高点 3% 判定：`distance_to_high_240d` vs `dist_prior_high_250` jaccard **0.530**、仅系统侧成立 133,101 行、仅研究侧 0 行（n=5,332,523）；`mean_abs_diff` 0.027444 | `compare_stats.json#signals.near_high_3pct`、`#pairs.dist_52w_high_vs_distance_to_high_240d` |
| 解锁还需 | `dist_prior_high_250`、`uf_ma120`、E4、E3、X1 | 同左 §S08 |
| 保真 | **已对账（系统开发工程师），本台账不复算**：`max_abs_diff = 0.0`（n = 5,332,523）；首根非空 2019-01-17 两侧相同；同列作 §4.2 的分母时亦 `0.0` | `F_CLASS_PARITY_20261107.md` §2；`research/factor-registration-b2-20261107/REPORT_20261107.md` §2.2 |

### 2.8 prior_low_10 → uf_prior_low_10

| 项 | 值 | 依据 |
| --- | --- | --- |
| 研究侧原文 | `pl.col("low").shift(1).rolling_min(10).over("symbol").alias("prior_low10")` | `common.py:134` |
| 服务策略 | S02 出场 `close < prior_low_10` | 同左 §S02 |
| 替换关系 | **`low_60d.replaced_by = 本因子`（策略经理裁定，作用域仅限策略侧下破判据 / S02 出场）**。**逆关系（v5.1 补齐）：本因子 `replaces = ['low_60d']`**（JSON `factors[].replaces`；两侧必须互为逆，缺一侧按字符串反查会漏）。**这是降级替换，不是同口径等价**：窗口 10 vs 60、价基 `low` vs `close`、不含当日 vs 含当日。**不注册 `prior_low_60`**（研究侧无此需求 + 与 `low_60d` 近名混淆，拒 `prior_high_60` 的同一理由）；**展示侧不动**：`distance_from_low_60d` 继续用 `low_60d`（那里「含当日收盘最低」是正确用法） | `docs/research/caliber-decisions-20261107.md` §8.2；D1 §1.2 第 4 点 |
| 触发率（为什么要它） | 研究侧 `close < prior_low10` 触发率 **8.853%**；`close < low_60d` 触发率 **0.000%** → 用 `low_60d` 等于永不出场，S02 只能靠 60 日上限强平 | `compare_stats.json#series.prior_low10_missing`、D1 §1.2 第 4 点 |
| 解锁还需 | E3 `in_universe`、X2 `max_hold_days` | 同左 §3 |
| 保真 | **已对账（系统开发工程师），本台账不复算**：`max_abs_diff = 0.0`（n = 5,503,218）；`close < prior_low_10` jaccard **1.000000**（both_true 487,212，研究侧触发率 8.853%） | `F_CLASS_PARITY_20261107.md` §2 / §3 |

### 2.9 prior_vol_20 → uf_prior_vol_20

| 项 | 值 | 依据 |
| --- | --- | --- |
| 研究侧原文 | `pl.col("volume").shift(1).rolling_mean(20).over("symbol").alias("prior_vol20")` | `common.py:136` |
| 语义 | 此前 20 日均**量**（volume，不是波动率） | 契约 §7.1 坑 2 |
| 服务策略 | S09 量能确认 `volume > 1.5 × prior_vol_20` | 同左 §S09 |
| 替代品实测 | 用 `vol_ma10`（含当日、10 日）：corr 0.956243、`mean_abs_diff` 47,600.27、1.5 倍量判定 jaccard **0.601**（仅研究侧 269,878 / 仅系统侧 93,177，n=5,496,401）；用「含当日 20 日均量」：jaccard **0.490**（only_a 313,216 / only_b 212,735，n=5,496,401）；`vol_ma20` 系统不存在 | `compare_stats.json#pairs.prior_vol20_vs_vol_ma10`、`#signals.s09_vol_1p5_vs_ma10`、`#signals.s09_vol_1p5`、`#pairs.prior_vol20_vs_vol_ma20_incl_today` |
| 单位 | **未确证**（volume 是股还是手）。因为它只用比值（`volume / prior_vol_20`），单位自消，**不阻断 S09**；但台账 `unit` 只能写「未确证」 | — |
| 解锁还需 | E3 `in_universe`；生产侧 X1 | 同左 §3 |
| 保真 | **已对账（系统开发工程师），本台账不复算**：`max_abs_diff = 0.0`（n = 5,496,401）；`volume > 1.5 × prior_vol_20` jaccard **1.000000**（both_true 817,835，研究侧触发率 14.879%） | `F_CLASS_PARITY_20261107.md` §2 / §3 |

### 2.10 注册表两态、无冲突与编译实测（确证）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 注册表基数（**未 load 磁盘定义时**） | `cd backend && ./.venv/Scripts/python.exe -c "from app.factors.registry import all_factors; print(len(all_factors()))"` | **192 条**（实测 2026-11-07T16:07）= 178 条内置目录 + **14 条研究基线 pack**（`app/custom/research_factor_pack`，由 `_ensure_factor_providers()` 在 import 后自动注册，含裸 id `ma120`/`ma200`/`vol60`/`prior_amount_20` 等）。**此状态下 8 个 `uf_*` 必然 MISSING**（`get_factor` → `None`）—— registry 是**进程内注册表**，「只 import」不等于「已装载磁盘定义」 |
| 8 个 uf_ 是否已注册（**load 之后**） | `store.load_into_registry(settings.data_dir)` → 逐只 `get_factor` | **载入 15 条自定义定义（8 个 `uf_*` + `uf_dist_prior_high_250` + 5 个 `uf_auction_*` + `cf_auction_resonance`），注册表总数 **207** 条，8/8 全部可取**（16:12 实测；16:07 时点为 14 条 / 206，差的那条是 16:07 才落库的 `uf_dist_prior_high_250`）；warmup 61/121/201/21/56/251/11/21、deps 与契约 §7.1 逐一相同（实测 2026-11-07T16:07） |
| `uf_dist_prior_high_250` | 同上 | **已在册**（load 后可取：`lang=dsl`、`formula_text` = `close / ts_delay(ts_max(high, 250), 1) - 1`、`warmup=251`、deps `{close, high}`、`stability=experimental`，实测 16:12）；裸 id `dist_prior_high_250` 仍为 `None` |
| `prior_low_60` / `prior_high_60` / `rsi_14_pct` | 同上 | **三个 id 全部不在注册表**（`get_factor` → `None`，load 前后都是）；`rsi_14` 在册（价格差口径，策略禁用） |
| `high_60d` / `low_60d` 在不在注册表 | 同上 | **不在**（`get_factor('high_60d')` → `None`，load 前后都不在）；也不在 DSL `BASE_COLUMNS`（9 列：`amount`/`close`/`high`/`low`/`open`/`prev_close`/`raw_close`/`turnover_rate`/`volume`）→ **DSL 里写 `high_60d` 直接 `E001 未知标识符`**（实测）。它们只作为指标列存在于 `app/indicators/pipeline.py:451-454`（`close.rolling_max(60)`）与矩阵路径 |
| 8 条公式能否编译 | `compile_formula(<契约原文>)` | **8/8 `ok=True`**；warmup 依次 **61 / 121 / 201 / 21 / 56 / 251 / 11 / 21**；deps 依次 `{close}` / `{close}` / `{close}` / `{high}` / `{high}` / `{high}` / `{low}` / `{volume}`（与契约 §7.1 表逐一相同） |

**注册表语义（v2 更正，原来那句「`get_factor('uf_*')` 现返回 `None`」是未 load 的假象）**：`backend/app/factors/registry.py` 的注册表是**进程内**注册表。①只 import → `all_factors()` = **192**（178 内置 + 14 pack），8 个 `uf_*` 必然 `MISSING`；②调过 `load_into_registry(Path(data_dir))` → **207**（15 条磁盘定义），8/8 存在。生产启动流程 `app/main.py:221` 就会调它，所以「线上没有这些因子」只在「未重启的服务」这一种状态下成立。

**一个容易读错的地方（本批新增登记）**：`app/indicators/pipeline.py:2295-2301` 的 `min_history_bars` 里 `high_60d: 59`、`ma20: 19` 等，那是**实时增量路径「历史 K 线不足 N 根就置空」的阈值 = N−1**（含当日 bar 的约定），**不是** `warmup_bars`。本台账的 `warmup_bars` 是「首个非空输出所需前置 bar 数」，对 `prior_*` 等于 N+1。两个数不是同一个概念，别互相校验。

---

## 3. 契约 §7.1 的三条坑（逐条落地到本台账）

### 坑 1：`prior_*` 必须带 `ts_delay(...,1)`

- 事实：写成 `ts_max(high, 20)` 也编译通过、也 warmup=21（实测），但**含当日 bar**，与研究 `shift(1)` 差一根 K 线；对 `close > prior_high_20` 这类突破判据会在「创当日新高」时误触发。
- **本批新增的实测结论（比契约更进一步）**：`compile_formula('ts_max(high, 20)')` 与 `compile_formula('ts_max(ts_delay(high, 1), 20)')` 的 `warmup_bars` **同为 21**、`deps` **同为 `{high}`** —— 因为 DSL 的 warmup 是静态规则 `max(n+1)`（`backend/app/factors/dsl.py:610-612`）。**所以 warmup 一致、deps 一致，都不能证明口径对**；唯一能区分的是本台账的 `shift` / `semantics` 字段与 V3 数值对账。
- 落地：`uf_prior_high_20/55/250`、`uf_prior_low_10`、`uf_prior_vol_20` 五条 `shift=1`、`semantics=prior`，并由自检脚本强制（§6 检查 2）。

### 坑 2：`prior_vol_20` 的 "vol" = volume，不是波动率

- 事实：`ts_std(close / ts_delay(close, 1) - 1, 20)`（波动率写法）同样 `ok=True`、warmup 21，会得到一个**看似合理、无任何报错**的错因子。
- 落地：`uf_prior_vol_20` 的 `deps={volume}`、`price_basis=volume`。**`dependencies` 是唯一可机器校验的区分**（`{volume}` vs 波动率写法的 `{close}`），自检脚本检查 4 已把它与契约 §7.1 逐字对上。

### 坑 3：`vol60` 不要用 `change_pct`

- 事实：契约说单位不统一、会得到大 100 倍的数值。**本批实测：`*100` 只在分时展示路径（`app/api/intraday.py:72`）；因子/回测路径的 `change_pct` 是小数，与研究 `ret1` 的 `max_abs_diff=2.22e-16`**（§1.2 K3）。
- 落地：仍按契约采用 `ts_std(close / ts_delay(close, 1) - 1, 60)`（`deps` 只有 `{close}`，与任何路径的 `change_pct` 单位无关）；同时把「契约措辞过宽」登记为 K3 供修订。**风险是真的**（同一名字两条单位不同的路径），只是「后果」在本路径上未被证实。

---

## 4. 范围事实：本批 8 只之外的三项（状态已按裁定与实测更正）

**一句话**：本批 8 只 = 契约 F-A1。另外三项各有归属、**都不是漏项**，但状态各不相同：`prior_amount_20` **已注册**（研究名 + pack provider）、`dist_prior_high_250` **已注册为 `uf_dist_prior_high_250` 并逐位对账 0.0**（但一策未解锁）、`rsi_14_pct` **押后到 E1/E2 之后，且 base 列路线实测须改 `pipeline.py`**（v1 把三项一律写成「本批未注册，批二/批三」、v2 把 `dist` 写成「尚未注册」、把 `rsi` 写成「零改动的排期项」，三处都已过期）。

| 因子 | 出处 | 实测状态（2026-11-07T16:07） | 归属 / 批次 | 阻断谁 | 关键口径 / 未知 |
| --- | --- | --- | --- | --- | --- |
| `prior_amount_20` | 策略经理 §1.4、gap spec §F7 | **已注册**（`get_factor` 返回 spec） | 注册已完成；剩余动作 = 台账 `unit` 补齐（本文已补） | 全部 12 条的股票池流动性门槛（`1e8`） | `unit = CNY（元，不缩放）`；**「amount 量纲未确证」缺口已关闭**（§4.1） |
| `dist_prior_high_250` | §1.4、§1.2 末段 | **已注册**（`uf_dist_prior_high_250`，16:07 落库；裸 id 仍为 `None`） | **批二：注册 + 逐位对账已完成**（`max_abs_diff = 0.0`，§4.2） | S08 的直接判据；**注册了也不解锁 S08**（还压 E2/E3/E4/X1） | 小数口径（−3% 写 `-0.03`）；分母 ≤0 或空 → 空，但实现只拦 `==0`（K10，§4.2） |
| `rsi_14_pct` | D2 §2.1 / §4.1（**不在** §1.4） | **未注册**（`get_factor` → `None`；`rsi_14` 在册） | **押后到 E1/E2 之后**；不扩 DSL 算子，但 base 列路线**实测不可行、须改 `pipeline.py` Pass 5 三处**（§4.3） | S04 全部（入场、出场、排序） | `al = 0` 必须按 IEEE 得 100，现 base 路径用 `1e-12` 近似；实测现成 `rsi_14` vs 研究 `max_abs_diff = 28.8984`（§4.3） |

### 4.1 `prior_amount_20`：已注册，`unit = CNY（元）`（v1 写「本批未注册」，此处更正）

**实测 spec**（`cd backend && ./.venv/Scripts/python.exe`，2026-11-07T16:07；命令见 §8 第 2 条）：

| 字段 | 实测值 |
| --- | --- |
| `id` | `prior_amount_20` |
| `kind` / `lang` | `custom` / `dsl` |
| `formula_text` | `ts_delay(ts_mean(amount, 20), 1)` |
| `dependencies` | `{amount}` |
| `warmup_bars` | `21` |
| `stability` | `stable` |
| `unit` / `scale_free` | `currency` / `false` |
| `group` / `version` | `研究补充` / `1` |

**载体与「是不是同一轨」**：由 `backend/app/custom/research_factor_pack/factor_provider.py`（`provider_id = official.research-factor-pack-b0`）在 `app/extensions/factors.py#ensure_factor_providers` 自动发现后注册，**不走 `POST /api/factors/custom`、不落 `custom_factors` 磁盘定义**，所以 `all_factors()` 未 load 磁盘时就有它（192 条，§2.10）。与 `uf_*`（磁盘 DSL 定义，启动期 `load_into_registry` 装载）的差别**只在注册方式，不在计算**：pack 的 `materialize_frame` 调 `compile_formula_cached(spec.formula_text)` + `frame_transform`，与 `app/strategy/scoring.py` 的物化路径是**同一条 DSL 计算链**，不是第二套 python 实现。

**一处必须更正的措辞（v1 与转达里的说法有误）**：`FactorSpec` **没有 `formula` 字段**（`backend/app/factors/registry.py:33-57`）。用 `getattr(spec, 'formula', None)` 读到的 `None` 是「属性不存在」的默认值，**不是**「该因子无公式」；实测该 spec 的 `formula_text` 就是 DSL 原文。**判断一个因子能否逐位复算，看 `lang` 与 `formula_text`，不看 `formula`。** 因此「以 python provider 注册、没有 DSL、因此不可逐位复算」这个描述**不成立**。

**可复算的证据**：B0 逐位对账 `max_abs_diff = 0`（n = 5,496,401，`docs/factors/REGISTRATION_B0_20261107.md:65`；脚本 `research/factor-registration-20261107/verify_b0.py`，直接成对比较、无缩放）。

**仍然是缺口的（不由本台账关闭）**：**矩阵回测路径不认它** —— `app/backtest/matrix.py#matrix_feature` 只认识 `ma*`/`boll_*` 这类内置特征，`sd20`/`prior_*`/`vol60`/`prior_amount_20` 的矩阵侧实现是缺能力项（`factor_provider.py` 文件头自述，明确「本包不在此处偷偷补一套 numpy 实现」）。要进矩阵回测需架构契约 + 开发实现。

**口径（策略经理 §8.1）**：单位 = **元（CNY，不缩放）**；表达式 `ts_delay(ts_mean(amount, 20), 1)`；`shift = 1`、`semantics = prior`、`warmup_bars = 21`；E3 股票池阈值写 **`1e8`**（元），**不得**写成「1 亿元」再换算。

**关闭的缺口：「amount 量纲未确证」** —— §8.1 三条互证：①研究侧原始列就是元（`research/strategy-search-20261107/scripts/common.py:66` 门槛 `1e8`、`:135` 直接 `amount.shift(1).rolling_mean(20)`；`/1e8` 只出现在比对脚本的派生列 `prior_amount20_yi`）；②系统侧基础列也是元（`docs/plugin-development.md:231`「`amount` 单位为元」；`amount_mean_20d` 的「亿元」来自 `scoring.py` 里显式 `amount/1e8`，那是**衍生字段**的单位）；③B0 `max_abs_diff = 0` 的成对比较无缩放，两侧单位不同时这个 0 不可能出现。原 `compare_stats.json#pairs.prior_amount20_yi_vs_amount_mean_20d`（`mean_abs_diff` 0.083458、1 亿门槛 jaccard 0.9770666）是**亿元派生量**的对比，不能当量纲证据，也不能当准入口径。

### 4.2 `dist_prior_high_250`：已注册为 `uf_dist_prior_high_250`，逐位对账 0.0（§8.3.1）

| 项 | 取值 |
| --- | --- |
| 口径 | `close / prior_high_250 - 1`，**小数、不是百分比**（S08 的 −3% 阈值写 **`-0.03`**） |
| 分子 / 分母 | 分子 = **当日 `close`**（前复权，与分母同一条复权序列）；分母 = **`prior_high_250`**（`high` 价基、`shift = 1`、不含当日）。两者同源，不跨复权序列、不另取 `raw_close` |
| 字段 | `semantics = dist_ratio`、`shift` 继承 `1`、`price_basis = high`（分母）、`warmup_bars = 251`、`strategy_usable = true`（服务 S08 排序与阈值） |
| 空值 | 分子或分母为空 → 空；**规格要求「分母 ≤ 0 或缺失 → 空」**，而实现 `_safe_div` 只拦 `denominator != 0`（`dsl.py:386-391`）、负数照算 —— 本因子分母恒 >0（实测 `den<0` 0 行）故无行差，口径收口见 K10。给 `null` 而非 `inf` 是策研明确接受的 |
| 批次理由 | 只依赖已注册的 `uf_prior_high_250`，纯表达式、不碰引擎，没有理由等 E 系列 |
| **不解锁 S08** | S08 还压 E2/E3/E4/X1；注册本因子只补上「直接判据」这一格 |
| 验收补充 | 除 `max_abs_diff = 0` 与 `dist >= -0.03` jaccard = 1.000 外，**报告必须给出「分母为 0 或 ≤ 0 的行数」**；该数不为 0 时不得声称逐位等价。**16:09 已满足**：`den<0` 0 行、`den==0` 0 行（见下表） |
| 顺带 | `distance_to_high_240d.replaced_by` → 本因子：台账侧已登记（本文 §5 / JSON `replacement_rulings`）；`FactorSpec` 无 `replaced_by` 字段，注册表侧无需代码动作（b2 报告 §2.3 末段明确未动 `docs/factors/`） |

**实测状态（2026-11-07T16:07 落库 / 16:09 报告）**：证据 `research/factor-registration-b2-20261107/REPORT_20261107.md` §2 与 `logs/dist_prior_high_250_evidence.json`；脚本 `dist_prior_high_250_parity.py`（11/11 判据、EXIT=0、单次全帧无抽样）。

| 项 | 实测值 |
| --- | --- |
| 落库 id / version | `uf_dist_prior_high_250` / **1**（`D:/TSP/data/user_data/custom_factors/uf_dist_prior_high_250.json`，756 B，sha256 `7c8163e44571d95ebb88f54a38f971eae743485ceab0003cebd839270fe404f5`） |
| 落库 formula | `close / ts_delay(ts_max(high, 250), 1) - 1`（K1 的另一种等价写法；与 `uf_prior_high_250` 用的 `ts_max(ts_delay(high, 1), 250)` 实测互相 `max_abs_diff = 0.0`；DSL 无因子间引用，分母只能内联、不能写 `uf_prior_high_250`） |
| 编译 | `ok=True`、`warmup_bars = 251`、`deps = {close, high}`、`stability = experimental`（实测 16:12） |
| 逐位对账 vs 研究侧 `dist_52w_high` | **`max_abs_diff = 0.0`**、n = **5,332,523**、超 1e-12 **0 行**、非零差 0 行 |
| `dist >= -0.03` 判定 | jaccard **1.000000**（both_true 150,292；仅系统侧 0 / 仅研究侧 0；两侧触发率同为 **2.8184%**） |
| 分母 ≤0 / 空 | 评估窗口 `den<0` **0** 行、`den==0` **0** 行、`den` 为空 177,478 行；全帧 `den≤0` **0**、为空 838,826；研究侧 inf **0** 行 → §4.2「验收补充」要求的分母异常行数已报，前置条件满足 |
| 首根与非空 | 首根非空 **2019-01-17**（两侧相同）；3,326 只逐 symbol 首根 bar 序号全部一致；null 口径仅一侧非空 **0** 行 |
| 幂等 | 二次提交同内容 `unchanged = true`、version 仍 1、14 个既有 json 逐字节未变（`changed_baseline_files = []`） |
| 仍不解锁 | S08 还压 E2/E3/E4/X1 —— 注册只补齐「直接判据」这一格 |
| 未验证 | 矩阵回测侧是否认 `dist_*`、HTTP 端到端、复权因子独立断言、**独立审核（批二尚未提交）**（b2 报告 §5 四条） |

**一处口径与实现的差异（K10，必须留痕）**：规格写「分母 ≤0 或空 → 空」，而 DSL `_safe_div` 的判据是 `denominator != 0`（`backend/app/factors/dsl.py:386-391`）——**只拦 `==0`，负数照算**。本因子分母是 250 日最高价、恒 >0（实测 `den<0` 0 行），所以两种写法在本因子上不产生任何行差，**可以**按规格声称逐位等价；但这句规格没有落地到实现，**换到可能出现负分母的因子必须重新验**，不得照抄本结论。

**注册元数据缺口**：落库 spec 的 `unit = none`、`scale_free = true` —— `store.to_spec` 不落 `unit`（契约 §7.2 已登记的 P2 缺口），所以本节的 `unit = ratio_dec` 只在台账/JSON 成立，**注册表里查不到**，任何自动加权逻辑不得依赖它。

**关于 `_safe_div` 的边界（与 §1.2 K7 的 1 ULP 不是同一件事）**：1 ULP 的差异已定因为「研究侧 `pct_change()` vs 普通除法」，**与 `_safe_div` 无关**（K7）。本节的 `_safe_div` 只讨论「分母为 0 时给 null 还是 inf」这一条**口径选择**，策研已接受 null。

### 4.3 `rsi_14_pct`：押后到 E1/E2 之后；不扩 DSL 算子，但 base 列须改 `pipeline.py`（现状实测不可用）

- **排期**：排在 E1/E2 之后，不与 E 系列抢工期（§8.3.2）。它是 P1，**单独不解锁任何策略**（S04 还压在 E2/E3/E4/X1 上），提前做只增加引擎风险。
- **路线（开发经理 16:03 转达的方向 + 系统开发工程师 16:09 可行性实测）**：**不扩 DSL 算子**这条成立，但**base 列不是零改动、现成的 `rsi_14` 列不可直接用** —— `app/indicators/pipeline.py:575-583` 已经用 `pl.col("_gain").ewm_mean(alpha=1/14, adjust=False).over("symbol")` 与 `_loss` 同款算出 `rsi_14`（价格差口径）；要产出 `rsi_14_pct` 必须在 `pipeline.py` Pass 5 改三处：① 价基 `close.diff()` → `close.pct_change()`；② 去掉 `al==0 → 1e-12` 护栏（改 `_safe_div` 的 null 或保留 inf→100，并把 NaN vs null 在契约定死）；③ 首根语义统一（现系统第 1 根给 0.0，研究第 1 根 NaN）。因此本因子**归「指标层引擎改动 + 排期决策」** —— 既不归「扩 DSL 算子」，也不归「纯排期」（DSL 侧无 ewm 算子这一事实仍成立，只是不必走那条路）。
- **口径与验收不变**（§8.3.2 / §2.5）：`max_abs_diff < 1e-10`；`RSI<30` 与 `RSI>55` **两侧** jaccard ≥ 0.999；均值 50.1866 ± 0.01；`p95_abs_diff ≤ 0.01`。
- **一处必须盯住的静默分叉**：`al = 0`（窗口内无下跌）时研究侧按 IEEE 得 **100**，而现 base 路径用 `.then(1e-12)` 近似（`app/indicators/pipeline.py:579-583`），**不是 IEEE 语义**。验收报告必须给出「`al = 0` 的行数」与「仅一侧为空的行数」，**并且必须写清空值口径**：`null` 口径实测 **0** 行、`NaN` 口径 **680** 行（研究 NaN / 系统 0.0），两个口径不能混着套一句「必须 = 0」；否则 `max_abs_diff < 1e-10` 会被这条近似悄悄放过。
- `rsi_14`（价格差）保留为独立 id、策略禁用；本项不改它的语义。

**实测（2026-11-07T16:09，`research/factor-registration-b2-20261107/REPORT_20261107.md` §3；脚本 `rsi14_base_column_probe.py`）**：判据 ①今天就没过 —— 现成 base 列不是「差一点」，是另一个口径。

| 项 | 实测值 | 对 §2.5 判据 |
| --- | --- | --- |
| 现成 `rsi_14` 列 vs 研究 `rsi14` | `max_abs_diff = 28.89841800839814`、n = 5,510,001、超 1e-10 **5,508,079** 行、超 1e-6 5,506,174 行、`mean_abs_diff = 0.8922` 个 RSI 点、p95 = 1.9672 | **不过** |
| `RSI < 30` / `RSI > 55` jaccard | **0.9484** / **0.8985**（`>55` 仅系统侧 0 行 = 价差口径系统性偏低的指纹，与 caliber §2.2 的 0.948 / 0.898 一致） | **不过**（要求 ≥0.999） |
| 根因分解（每次只换一个环节） | 价基换成 pct → 对研究 **0.0**；护栏项单独 **1.813e-06**；`ag=al=0` 分支 → 680 行 NaN 单侧；种子 / min_periods / 空值跳过 → **0.0**（不是根因） | 三处都要改 |
| `al = 0` 行 | 共 **2,871** 行：680 行 `ag=al=0`（研究 NaN / 系统 0.0）、2,191 行 `ag>0`（研究恰 100.0，系统 99.99999993~100-ε，`max_abs_diff_on_al0 = 1.64e-07`）；**null 口径单侧 0 行、NaN 口径单侧 680 行** | 验收须逐项报 |
| 结论 | 现成 `rsi_14` 就是 caliber §2.1 判「策略不得引用」的 `price_diff` 口径本体；换 pct 价基后逐位相等（含首根）→ 路线可行，但**必须先改 `pipeline.py` 再重跑**，属引擎（指标层）改动 | — |

一处待架构师裁定的语义（b2 报告 §3.5，只给事实不裁定）：系统 `rsi_14` 第 1 根即有有限值、研究第 1 根是 NaN，**两侧都不产生 373 根前导空值** ——「warmup 373」与「首根 ret1 起算」属契约层取舍。

任务书把三项并称「D1 §1.4」，按文件实际是「§1.4 两项 + D2 一项」，此处按文件登记（见 §1.1）。

---

## 5. `high_60d` / `low_60d` 与 `prior_high_*` 互引差异说明（D1 §1.5 强制项）

**两个数长得几乎一样，判据却完全不一样。这一节是为了防止下一个人再犯一次。**

| 项 | `high_60d`（保留，降级） | `prior_high_55`（本批注册） |
| --- | --- | --- |
| 实现 | `close.rolling_max(60)`（`app/indicators/pipeline.py:452`；矩阵路径 `app/backtest/matrix.py:4363-4366` 同口径） | `ts_max(ts_delay(high, 1), 55)` |
| 价基 | **收盘价** | **最高价**（复权） |
| 含当日 | **含**（`shift=0`，`semantics=incl_today_close`） | **不含**（`shift=1`，`semantics=prior`） |
| 窗口 | 60 | 55 |
| 用途 | 状态/展示（「近 60 日是否创新高」这类判断是**对的**：`market_overview_builder.py:502` 的新高统计就这么用） | 突破判据（`close > prior_high_55`） |
| 策略侧 | **禁用**（`strategy_usable=false`），任何入场/出场条件引用它，评审直接退回 | 可用（S09 入场） |
| 注册表状态 | 不在注册表、不在 DSL `BASE_COLUMNS` → DSL 引用即 E001（实测） | 已落库 `uf_prior_high_55.json`（14:30）；启动期 `load_into_registry` 后存在（207 条中，§2.10）；未 load 的进程里 `get_factor` → `None` |

**实测差异（同一份数据，2019-07-01~2026-10-30，3,384 只）：**

| 对比 | n | corr | 平均绝对差 | 突破判定 jaccard | 仅研究侧成立 | 仅系统侧成立 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `prior_high55` vs `high_60d`（收盘+含当日+60） | 5,470,011 | 0.999642 | 0.4230 元 | **0.000** | 143,747 | **0** |
| `prior_high55` vs `prior_high60`（收盘+shift1+60） | 5,307,478 | 0.999609 | 0.4361 元 | 0.504 | 3,893 | 130,975 |
| `prior_high55` vs `prior_high60`（**最高价**+shift1+60） | 5,307,478 | 0.999714 | **0.1301 元** | — | — | — |

出处：`compare_stats.json#pairs.prior_high55_vs_high_60d`、`#pairs.prior_high55_vs_prior_high60_C`、`#pairs.prior_high55_vs_prior_high60_H`、`#signals.s09_break_vs_high_60d`、`#signals.s09_break_vs_prior_high60_C`。

**三条读法（决定 1 的全部论证）：**

1. **「含当日」是决定性的**：`both_true=0`——5,470,011 行里一次都没同时成立。原因是结构性的：当日收盘不可能高于"含当日收盘的最大值"。**S09 用 `high_60d` 入场 → 恒不成立**。
2. **窗口不是真凶**：55→60 在最高价口径下平均只差 **0.1301 元**；价基从最高价换成收盘价要差 0.4361 元，判定一致率掉到 0.504。
3. **平均绝对差完全看不出这场灾难**：0.4230 元只占 2.62%，看起来"可接受"，但判定一致率是 **0**。→ **阈值型因子（突破/超买超卖/门槛）验收必须给 `max_abs_diff` + 判定 jaccard 两个数，corr 与平均绝对差只能作辅助**（D1 §3.4 升级为通用验收规范）。

**下破侧同理**：`close < low_60d` 触发率 **0.000%**，研究侧 `close < prior_low10` 触发率 **8.853%**（`compare_stats.json#series.prior_low10_missing`）——S02 的出场用 `low_60d` 等于永不出场。

**为什么保留而不改名**（D1 §1.3，三条理由原文要点）：同一个数两种用法对错相反（状态判断是对的）；改名要动 7 处以上引用（`app/api/watchlist.py:368`、`app/strategy/monitor.py:57`、`app/strategy/custom_signals.py:61`、`app/strategy/scoring.py:156-159`、`app/strategy/ai_generator.py:65`、`app/services/market_overview_builder.py:444/502-503`、`app/factors/registry.py:166-171` 的 `distance_to_high_60d` deps）外加前端字段名；误用通道已由评审门禁堵住。**错的是用途，不是这个数。**

**配套但本批未做的动作**（归属写明，别让下游以为已完成）：

| 动作 | 归属 | 状态 |
| --- | --- | --- |
| `pipeline.py:189-190` 显示名「60日最高价」→「60日最高收盘价（含当日）」、「60日最低价」→「60日最低收盘价（含当日）」 | 系统开发工程师（文档缺陷，不影响计算） | **未做**（本文实测确认现文案与实现不符：`:451-454` 用的是 `close`） |
| 台账给 `high_60d`/`low_60d` 补 `semantics=incl_today_close`、`price_basis=close`、`shift=0`、`strategy_usable=false`、`replaced_by`：`high_60d` → `prior_high_55`、`low_60d` → `prior_low_10`（**两者都是降级替换，非同口径等价**） | 因子工程师（`high_60d` 侧本文已给；`low_60d` 侧由策略经理 §8.2 裁定，见 §2.8） | **两格已裁定可填**（原「`low_60d` 待裁定」作废） |
| 种子策略 `app/strategy/seeds/breakout_new_high_60d.py:65` 的 `shift(1)` 补偿**保留** | 不改 | 保留（删掉会立刻变成「含当日突破」＝恒不成立） |

---

## 6. 自检：命令与实跑输出

脚本：`docs/factors/evidence/scripts/check_f_class_ledger.py`（只读；解析契约 §7.1 表格做逐字比对；退出码 0/1）。

```bash
cd C:\work\sourcecode\tick-stock-panel
python docs/factors/evidence/scripts/check_f_class_ledger.py
```

实跑输出（**v5.9 修订后重跑，2026-11-08 00:44**；判据对象已由「版本全文」改为 **§7.1 块哈希**：归档 `archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md` 89,833 B / 914 行 + 现行读取来源 `FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md` 269,092 B / 2,248 行；两份 §7.1 块在两套口径下都等于登记常量 —— LF 归一化 2,514 字符 / `6d3db013…`（判定用值）、原始 CRLF 2,541 字符 / `a8e88134…`（通报用值）；契约版本号不参与判定。脚本先比块的两种 sha，再逐只比 formula/warmup/deps，任一不同即 FAIL 并打印两处 sha。输出为 ASCII，以便任何控制台编码都能读；`BINDING` 段含本文件自指哈希，按 §0.1 末条不抄进正文，改为实跑现打印）：

```text
F-class ledger self-check (read-only)
  registry : docs\factors\evidence\f_class_registry.json
  ledger   : docs\factors\F_CLASS_REGISTRATION_20261107.md
  contract : docs\architecture\archive\FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md  (frozen v0.3 archive, read-only)
  contract2: docs\architecture\FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md  (current revision, read source only)
  s7.1 binding: BLOCK hash, not the whole-file hash; version number not judged
  s7.1 archive LF/CRLF: 2514/2541 chars  sha256 6d3db013... / a8e88134...
  s7.1 contract LF/CRLF: 2514/2541 chars  sha256 6d3db013... / a8e88134...
  s7.1 registered: LF 2514 chars / 6d3db013...  CRLF 2541 chars / a8e88134...  (both must match)
  factors  : 8   contract rows parsed: 8 / 8

per-factor:
  uf_vol60             window=60   shift=0  warmup=61   min_warmup=-    formula=ts_std(close / ts_delay(close, 1) - 1, 60)
  uf_ma120             window=120  shift=0  warmup=121  min_warmup=-    formula=ts_mean(close, 120)
  uf_ma200             window=200  shift=0  warmup=201  min_warmup=-    formula=ts_mean(close, 200)
  uf_prior_high_20     window=20   shift=1  warmup=21   min_warmup=21   formula=ts_max(ts_delay(high, 1), 20)
  uf_prior_high_55     window=55   shift=1  warmup=56   min_warmup=56   formula=ts_max(ts_delay(high, 1), 55)
  uf_prior_high_250    window=250  shift=1  warmup=251  min_warmup=251  formula=ts_max(ts_delay(high, 1), 250)
  uf_prior_low_10      window=10   shift=1  warmup=11   min_warmup=11   formula=ts_min(ts_delay(low, 1), 10)
  uf_prior_vol_20      window=20   shift=1  warmup=21   min_warmup=21   formula=ts_mean(ts_delay(volume, 1), 20)

[1] research_name_id_bijection
    rule      : research_name <-> uf_ id is 1:1, ids match ^uf_[a-z0-9_]{1,40}$, no duplicates
    violations: 0
[2] prior_shift_and_warmup
    rule      : all prior_* have shift==1, semantics=='prior', warmup_bars >= N+1; non-prior rows have shift==0, semantics=='incl_today_close'
    violations: 0
[3] expected_id_set_and_warmup_order
    rule      : ids/set and warmup order equal 61/121/201/21/56/251/11/21 for the fixed 8 ids
    violations: 0
[4] formula_verbatim_vs_contract
    rule      : formula_text/warmup/deps are byte-identical to section 7.1 of BOTH bound contracts (frozen v0.3 archive + live numbered revision v0.6), and those two 7.1 blocks are identical; either differing -> FAIL, with both sha256 printed
    violations: 0
[5] md_ledger_consistency
    rule      : markdown ledger contains every id, every verbatim formula, and a row carrying the warmup
    violations: 0
[6] required_fields_present
    rule      : every row carries all ledger fields (research name, id, formula, warmup, deps, semantics, shift, price_basis, unit, scale_free, strategy_usable, replaces/replaced_by, canonical_id, aliases, superseded_by, canonical_reason, ...)
    violations: 0
[7] canonical_alias_rules
    rule      : canonical_id == own uf_ id; aliases[] non-empty and never shadow a canonical id; alias_of empty and superseded_by=[] on canonical rows; replaced_by never carries an alias (contract 7.8.2 A-1/A-2)
    violations: 0
[8] dual_id_group_coverage
    rule      : id_canonical_ruling.dual_id_groups covers exactly the 8 canonical ids, stays in sync with the factor rows, records alias_side (alias_of + strategy_usable=false + superseded_by=[canonical]), and keeps prior_amount_20 as the declared single-id exception
    violations: 0
[9] md_canonical_columns
    rule      : markdown ledger table carries canonical_id / aliases[] / superseded_by[] / alias_of / strategy_usable=false for every group plus the single-id exception (md <-> json sync)
    violations: 0
[10] freeze_declaration_version_agree
    rule      : freeze_declaration.status == 'FROZEN at v<version>' with <version> == meta.version, and the markdown status line (the line that starts with the status marker) names the same ledger version; any disagreement -> FAIL
    violations: 0
[11] md_fingerprint_matches_registry
    rule      : the sha256 listed for docs/factors/evidence/f_class_registry.json in markdown section 0.1 equals the LF-normalized sha256 computed from that file now; a stale fingerprint -> FAIL
    violations: 0

TOTAL VIOLATIONS: 0
RECORD MISMATCHES: 0
```

> **BINDING 段为何不抄进本文**：它打印 `ledger`（本文件）自己的 sha256 —— 抄进来必然在写盘的瞬间过期（自指）。每次运行现算现打印，口径见 §0.1；`registry` / `contract` / `contract2` 三行的当前值记在 §0.1 表里。

**v4 新增的三项检查防的是「只补台账、不补校验」**：7 `canonical_alias_rules` / 8 `dual_id_group_coverage` / 9 `md_canonical_columns`；同时把 `canonical_id` / `aliases` / `superseded_by` / `canonical_reason` 四列并入【6】必填字段 —— 只往 md/json 里填字段而不改必填清单，【6】会照旧 0 违例（假通过），这正是 v4 之前的状态。

11 项检查分别防什么：

| # | check id | 防的是什么 |
| --- | --- | --- |
| 1 | `research_name_id_bijection` | 同一口径起两个 id、两个研究名挤一个 id、id 不匹配 `^uf_[a-z0-9_]{1,40}$`（契约 §7.5 第 3 条） |
| 2 | `prior_shift_and_warmup` | D1 §1.5 与 D3 的硬要求：`prior_*` 的 `shift` 必须为 1、`warmup_bars ≥ N+1`；非 `prior_*` 必须 `shift=0` 且 `semantics=incl_today_close` |
| 3 | `expected_id_set_and_warmup_order` | 8 个 id 与 61/121/201/21/56/251/11/21 的顺序逐一相等（顺序错也报） |
| 4 | `formula_verbatim_vs_contract` | `formula_text` 与契约 §7.1 **字符级相同**，同时把 `warmup_bars`、`dependencies` 与契约表对账（防「顺手优化」和手填幻觉） |
| 5 | `md_ledger_consistency` | 本文正文与 JSON 不同步：id 缺失、公式被改、warmup 与本行不一致 |
| 6 | `required_fields_present` | 字段缺失/空串/空列表（含 `replaces`/`replaced_by`/`superseded_by` 为 null 这种「看起来有其实没有」），**现已覆盖 v4 的四列** |
| 7 | `canonical_alias_rules` | `canonical_id` 不是本行 `uf_` id；`aliases[]` 为空、与 canonical 同名、遮蔽别的 canonical id；canonical 行带了 `alias_of` 或非空 `superseded_by`；**把别名写进 `replaced_by`**（契约 §7.8.2 A-1/A-2） |
| 8 | `dual_id_group_coverage` | 8 组漏组/多组；`id_canonical_ruling.dual_id_groups` 与 factor 行不同步；`alias_side.strategy_usable` 不是严格 `false`；`alias_side.superseded_by` 不是 `[canonical]`；`prior_amount_20` 例外缺失，或冒出 `uf_prior_amount_20` |
| 9 | `md_canonical_columns` | md 表头缺列、某组没有唯一一行、行里缺别名/`alias_of = cid`/`strategy_usable=false`/`superseded_by=[cid]`、缺 `prior_amount_20` 单侧例外行（md ↔ json 同步） |
| 10 | `freeze_declaration_version_agree` | 冻结声明说「哪一版被冻结」这一格与 `meta.version` 脱钩、md 状态行版号与 json 版号不一致（v5.8 之前是真空：状态格停在 `FROZEN at v5.6` 而 `version=5.7`，全部 9 条判据照旧 0 违例） |
| 11 | `md_fingerprint_matches_registry` | §0.1 表里 registry 的 sha256 过期（registry 一改字节就变假，而冻结声明的可验证判据正是「registry 的 LF 归一化 sha256 == §0.1 表列值」，过期即令该判据为假而其余检查仍全绿） |


脚本还会把计算出的违例数与 JSON `self_check` 里登记的 `violations` 逐项比对，不一致就报 `RECORD MISMATCH` 并 FAIL——**台账里写的数必须是跑出来的数**。

---

## 7. 未知与未确证（清单，别读成"已对齐"）

**先更正 v1 的一处自相矛盾（文档管理员的缺陷清单条目 K2；与本文件 §1.2 的 K2「vol60 写法」不是同一条）**：v1 写「数值保真未确证、本文没有给任何 `max_abs_diff`」，但同目录 `F_CLASS_PARITY_20261107.md`（14:37:18 落盘、14:36:40 运行）**已经给出 8/8 通过**。正确表述是：**对账由系统开发工程师做，证据在本目录 `F_CLASS_PARITY_20261107.md` / `.json`；本台账不复算，只引用并标注独立审核状态。**

| # | 项 | 现状 / 影响 | 谁来做 |
| --- | --- | --- | --- |
| 1 | 8 只的数值保真（F-A3 / V3） | **已对账、已独立审核**：`F_CLASS_PARITY_20261107.md` 8/8 PASS；7 只 `max_abs_diff = 0.0`、`uf_vol60` = 1.1102230246251565e-16（1 ULP，超 1e-12 行数 **0**）；null 不一致 0、每只每 symbol 首根非空一致、5 条判定 jaccard 全 1.000。独立审核 `F_CLASS_AUDIT_20261107.md:19` 判 F-A3 **PASS**（自有脚本复算 `max_abs_diff ≤ 2.78e-17`）。**本台账不复算，只引用** | 系统开发工程师（对账）/ 独立审核工程师（复核）；本台账只引用 |
| 2 | `volume` 的单位（股 / 手） | 只影响 `unit` 字段写法，不影响 S09（比值单位自消） | 行情数据工程师 |
| 3 | ~~`amount` 的量纲（亿元 / 元）~~ | **已关闭**：两侧都是元，`unit = CNY（元，不缩放）`，E3 阈值 `1e8`（§8.1 三条互证，见 §4.1） | 已裁定 |
| 4 | 编译通过 ≠ 口径正确（warmup/deps 无法区分含不含当日，§3 坑 1） | 已由 F-A3 逐位对账 + 5 条判定 jaccard 覆盖；**但 F-A5 仍 FAIL**（同内容二次注册 version 1→2、文件被重写，`F_CLASS_AUDIT_20261107.md:21`） | 系统开发工程师修 F-A5 + 独立审核复验 |
| 5 | 注册幂等（F-A5） | 契约 §7.4 记现状不幂等；独立审核实测 **FAIL**（根因 `lang` 键不对称，8 只全中） | 系统开发工程师 |
| 6 | ~~`low_60d` 的 `replaced_by`~~ | **已裁定** = `prior_low_10`，**降级替换、非同口径等价**（窗口 10 vs 60、价基 low vs close、不含当日 vs 含当日）；不注册 `prior_low_60`；展示侧 `distance_from_low_60d` 不动（§8.2） | 已裁定（见 §2.8） |
| 7 | `uf_vol60` 的 1 ULP 根因 | **已定因**：`DSL vs 普通除法 = 0.0`，差异 100% 来自研究侧 `close.pct_change()`（4,214,876 行，1.11e-16）；**与 `_safe_div` 无关**（K7、审核 P3-3） | 已定因；对账报告 §7 措辞由系统开发工程师更正 |
| 8 | 同口径双 id 并存（K8） | **8 组**，不是 3 个裸 id：`ma120`/`ma200`/`vol60`/`prior_high_20`/`prior_high_55`/`prior_high_250`/`prior_low_10`/`prior_vol_20` 在 pack（研究原名）与 store（`uf_*`）各一份 → 契约 §7.5-3 的全局唯一性已破；另有两条**单侧件**（`prior_amount_20` 只有 pack、`uf_dist_prior_high_250` 只有 store，后者是 `distance_to_high_240d` 的取代目标）。**裁定已下（`ID-CANON-1`）**：canonical = `uf_*`，研究原名 = alias（`strategy_usable=false`，生产入口 `FS03` 拒；**用 `alias_of`，不得用 `replaced_by`**）。 | **已裁定**（系统架构师 `ARCH_DECISION_FACTOR_ID_CANONICAL_20261107.md`）；剩余动作 = 实现侧 `FS03` 强制 + 契约 v0.4 §7.8.1 #6 随 E2 批次合并修订 + 台账逐行四列（v4 已补，§2.1b） |
| 9 | 台账 `label` 与磁盘定义 8/8 不同（K9） | 「含当日 / 不含当日 / 未年化」这些口径语义只活在台账，前端展示可能与台账分叉 | 系统架构师（定「以台账为准」或覆盖磁盘） |
| 10 | F-A6 量级判据口径（K4） | 逐值判会误伤（p10 低于 0.015）；现行 F-A6a/b/c 判 PASS，原字面「0.015–0.06 越界即 fail」判 FAIL（12.58% 越界） | 系统架构师（已改写，见审核 P1-2） |
| 11 | 契约 §7.1 坑 3 的「大 100 倍」措辞（K3） | 不影响本批写法 | 系统架构师 |
| 12 | 两种 `prior_*` 写法的数值等价（K1） | 只影响文档统一；本台账用的契约写法已由 F-A3 逐位通过 | 系统架构师统一措辞 |
| 13 | **矩阵回测路径**不认 `sd20`/`prior_*`/`vol60`/`prior_amount_20` | 这些因子能进因子检验/评分，**不能进矩阵回测**（`app/backtest/matrix.py#matrix_feature` 只认 `ma*`/`boll_*`） | 需架构契约 + 系统开发工程师实现（能力缺口，§4.1） |
| 14 | `_safe_div` 只拦分母 `==0`、不拦负数（K10） | 规格写「分母 ≤0 → 空」，实现是 `denominator != 0`（`dsl.py:386-391`）。`dist_prior_high_250` 分母恒 >0（实测 `den<0` 0 行）→ 本因子无行差、可声称逐位等价；**换到可能负分母的因子必须重验** | 系统架构师（口径收口）/ 因子工程师（新因子登记时标注） |
| 15 | `rsi_14_pct` 走 base 列 ≠ 零改动（K11） | 现成 `rsi_14` 是价差口径本体：`max_abs_diff = 28.8984`、5,508,079 行超 1e-10、`RSI>55` jaccard 0.8985；换 pct 价基后 0.0 → 必须改 `pipeline.py` Pass 5 三处 | 系统开发工程师（指标层改动）+ 系统架构师（NaN vs null 定死） |
| 16 | 批二 `uf_dist_prior_high_250` **独立审核尚未做** | 对账 11/11 由系统开发工程师自测自报（`max_abs_diff = 0.0`），尚无第三方复核 | 独立审核工程师 |
| 17 | V3 的**名次漂移**缺口（1 ULP 过得了 1e-12，但可能改变近并列处的名次与 tie 组） | **已测、已关闭**：**8 对**（F-A3 全量；重点 6 对 = `vol60` + 5 个 `prior_*`，另含 `ma120`/`ma200`）在 20 symbol × 近 250 交易日（2025-10-21~2026-10-30）逐值 `max_abs_diff` = 2.78e-17（vol60，1 ULP 级）/ **0.0**（其余 7 只），全部 `< 1e-12`；**末交易日（2026-10-30）全截面 average 名次：`rank_change_max` = 0.0、被换位 0 只、tie 组数两侧相同**（`in_universe` 截面 1,716–1,723 只、20 只子样，亦全 0）；**250 个交易日逐日全截面复算：名次变化最大值 0.0、有换位的交易日 0 天**。证据 `docs/factors/evidence/F_CLASS_RANK_PARITY_20261107.json`（脚本 `docs/factors/evidence/scripts/f_class_rank_parity.py`，本台账 16:24 实跑、16.8s）。结论：`vol60` 的 1 ULP**不改变任何名次**，S02/S09 可拿 `uf_prior_*` 当验收基准 | 因子工程师（已测）；独立审核可复核 |

---

## 8. 复现命令

```bash
# 1) 8 只公式编译 + warmup/deps 实测（只读）
cd C:\work\sourcecode\tick-stock-panel\backend
.\.venv\Scripts\python.exe -c "from app.factors.dsl import compile_formula; [print(f, compile_formula(f).ok, compile_formula(f).warmup_bars, sorted(compile_formula(f).dependencies)) for f in ['ts_std(close / ts_delay(close, 1) - 1, 60)','ts_mean(close, 120)','ts_mean(close, 200)','ts_max(ts_delay(high, 1), 20)','ts_max(ts_delay(high, 1), 55)','ts_max(ts_delay(high, 1), 250)','ts_min(ts_delay(low, 1), 10)','ts_mean(ts_delay(volume, 1), 20)']]"

# 2) 注册表两态（只读）：未 load 磁盘定义 = 192；load 之后 = 207（15 条定义；8 个 uf_ 与 uf_dist_prior_high_250 全部可取）
.\.venv\Scripts\python.exe -c "from app.factors.registry import get_factor, all_factors; from app.config import settings; from app.factors.store import load_into_registry; print('before', len(all_factors())); print(load_into_registry(settings.data_dir)); print('after', len(all_factors()))"

# 2b) 单项核查（只读）：prior_amount_20 / dist_prior_high_250 / rsi_14_pct / low_60d 的状态
.\.venv\Scripts\python.exe -c "from app.factors.registry import get_factor; import dataclasses; [print(i, get_factor(i)) for i in ['prior_amount_20','dist_prior_high_250','prior_low_60','prior_high_60','rsi_14_pct','rsi_14','high_60d','low_60d']]"

# 2c) 批二单项（只读）：load 之后取 uf_dist_prior_high_250 的 spec
.\.venv\Scripts\python.exe -c "from app.factors.registry import get_factor; from app.config import settings; from app.factors.store import load_into_registry; load_into_registry(settings.data_dir); s=get_factor('uf_dist_prior_high_250'); print(s.id, s.lang, s.formula_text, s.warmup_bars, sorted(s.dependencies))"

# 3) 自检
cd C:\work\sourcecode\tick-stock-panel
python docs/factors/evidence/scripts/check_f_class_ledger.py

# 4) 数值证据（本条引用的数字都在这个文件里，未重算）
python -c "import json;d=json.load(open('docs/factors/evidence/compare_stats.json',encoding='utf-8'));print(d['signals']['s09_break_vs_high_60d'],d['pairs']['prior_high55_vs_prior_high60_H']['mean_abs_diff'],d['pairs']['ret1_vs_change_pct']['max_abs_diff'])"
```

---

## 9. 变更记录

| 版本 | 日期 | 变更 | 作者 |
| --- | --- | --- | --- |
| v1 | 2026-11-07 14:37 | 初版：8 只台账 + 机器可读台账 + 自检脚本；三条坑落地；范围事实与跨文档不一致登记 | 因子工程师 |
| v2 | 2026-11-07 16:10 | 按策略经理 §8（v1.3）裁定与实测更正五处：①`prior_amount_20` 已注册（研究名 + pack provider，`lang=dsl`）/`unit=CNY`、量纲缺口关闭；②`low_60d.replaced_by = prior_low_10`（**降级替换**）；③`dist_prior_high_250` 批二立即可做、零引擎改动；④`rsi_14_pct` 押后 E1/E2、走 base 列路线、不再写「需扩算子」；⑤§7 自相矛盾修正（引用 `F_CLASS_PARITY_*` 而非声称「没有 `max_abs_diff`」）+ 注册表两态语义（192 / 206）+ 1 ULP 归因更正（`pct_change`，非 `_safe_div`）。另新增 K7–K9、矩阵回测路径缺口，自检重跑 0 违例 | 因子工程师 |
| v3 | 2026-11-07 16:14 | 批二交付后按实测再更正四处：①`dist_prior_high_250` **已注册**为 `uf_dist_prior_high_250`（16:07）并逐位对账 `max_abs_diff = 0.0`（n = 5,332,523，`dist>=-0.03` jaccard 1.000000）；②注册表两态 206 → **207**（15 条定义）；③`rsi_14_pct` 的 base 列路线**实测不可行**（`max_abs_diff = 28.8984`，须改 `pipeline.py` Pass 5 三处），改归「指标层引擎改动 + 排期」；④新增 K10（`_safe_div` 只拦 `==0`）、K11（base 列非零改动）与 3 条来源哈希更正（契约已推进到 v0.4）；⑤§2.3–§2.9 七处「保真 未做（V3）」与 §0「未注册」等 4 处残留状态同步改为现状（逐只 n 与判定 jaccard 引用对账报告）。自检对 v0.4 重跑仍 0 违例 | 因子工程师 |
| v4 | 2026-11-07 16:20 | ①**K8 双 id 事实改对**：3 个裸 id / 4 项 → **8 组**，并写明两条单侧例外（`prior_amount_20` 无 store 双胞胎、`uf_dist_prior_high_250` 无 pack 对应件）；②**新增 §2.1b**：8 组逐行 `canonical_id` / `aliases[]` / `canonical_reason` / `replaced_by` + 两条单侧例外行 + `alias_of` 与 alias 侧 `strategy_usable=false`；**把 v1–v3 K8 里「另一侧标 `replaced_by`」的错写法改成 `alias_of`**（`replaced_by` 只表跨口径取代，现存 3 处合法用法已逐条点名）；③§2.1 三格（`vol60`/`ma120`/`ma200` 的「replaces / 被替换」）改为「alias，不是 `replaced_by`」；④§5 风险表第 8 行与 §7 第 17 行同步；⑤**新增 V3 补充对账**（20 symbol × 近 250 交易日 + 末交易日名次漂移 + 250 日逐日名次），证据 `F_CLASS_RANK_PARITY_20261107.json`：8 对全部 `<1e-12`、`rank_change_max` 全 **0.0**、换位 0 只。未注册、未改 `backend/**`、未提交；⑥**补 `superseded_by` 一列**（§2.1b 新增两列：canonical 行 `superseded_by[]` 与 alias 侧 `superseded_by[]`；JSON 落在 `id_canonical_ruling.dual_id_groups[].superseded_by` 与 `.alias_side.superseded_by`，字段分工写进 `column_semantics`）；⑦**自检 6 项 → 9 项**（新增 7 `canonical_alias_rules` / 8 `dual_id_group_coverage` / 9 `md_canonical_columns`），并把四列并入【6】必填字段，对契约 110,944 B / `6b8fb14c…`〔【作废：中途态，盘上无对应文件】——该值非盘上任何契约文件，v5.5 已就地标注〕重跑 **9/9 项 0 违例、0 记录不符、exit 0** | 因子工程师 |
| v5 | 2026-11-07 16:40 | ①**`replaced_by` 写法统一**：`replacement_rulings` 3 条已注册目标改写 canonical id（`uf_prior_high_55` / `uf_prior_low_10` / `uf_dist_prior_high_250`，并置 `target_registered = true`）、`rsi_14` 那条改 `replaced_by = null` + `replaced_by_declared_name = rsi_14_pct` + `target_registered = false`（目标未注册，不得写成看似已注册的 id）；②`single_sided_exceptions` 第 10 行反向记录 `replaced_by: ["distance_to_high_240d"]` 改为 `replaced_by: []` + `replaces: ["distance_to_high_240d"]`；③§2.1b 读表须知 2 与两处 `column_semantics.replaced_by` 补取值规则（canonical id 或 `null`）；④JSON `known_doc_conflicts` K12 置「已关闭」；⑤本文件版本号与 §9 条数对齐（v4 → v5）；⑥§2.4「保真」行补一个分隔符（表格结构修复，不改数值）。**因子数字、双 id 组数（8 组 + 2 例外）、公式、warmup 一律未动** | 因子工程师（按策略经理 a32a46ae 裁定）|
| v5.1 | 2026-11-07 16:47 | **`replaces` 与 `replaced_by` 逆关系补齐（只改关系字段，数字零改动）**：①JSON `factors[6].replaces` `[]` → `['low_60d']`（`low_60d → uf_prior_low_10` 原只有 `replacement_rulings` 单向记录，按 `replaces` 反查会漏）；②8 条 `factors[]` 逐条核对 `replaces`/`replaced_by` 互为逆，全部成立（`uf_prior_high_55 = ['high_60d']`、`uf_prior_low_10 = ['low_60d']`、其余 6 条两侧皆空）；`uf_dist_prior_high_250` 不在 `factors[]`，逆关系由 `single_sided_exceptions[1].replaces = ['distance_to_high_240d']` 承担；③`rsi_14_pct` 未注册，无 `factors[]` 侧可承载，保持 `replaced_by = null`（§2.1b 读表须知 2）；④§2.1b 第 5/7 行 `replaced_by` 格原写「本因子不取代别人」与 JSON 矛盾（第 5 行在 v5 时已错），改为 `[]` + 显式 `replaces`；⑤§2.1 第 84 行与 §2.8 补 `replaces` 方向。**反向还原逐字节得回 v5 的 `e71270f1…`（CRLF）/ `d0351778…`（LF）**；9 项自检 0 违例、exit 0 | 因子工程师（按策略经理 99e753cf 裁定）|
| v5.2 | 2026-11-07 16:57 | **只改指纹口径与公式权威，台账数字零改动**：①**行尾统一 LF**（JSON 与本文；16:45:33、16:49:20 两次被第三方改写行尾，内容未变）；②**指纹改记 LF 归一化 sha256**（折叠 CRLF 后取 sha256），新增 §0.1 指纹表；JSON `meta.fingerprint` 记口径 / 复算命令 / 自指说明，`meta.sources[*].sha256` 全部按新口径重算并各附 `hash_note_v5`（3 条为纯口径切换、内容未变；2 条为其作者已更新文件；3 条 LF 文件原值不变）；③**公式权威改绑归档冻结副本** `archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`（89,833 B / 914 行 / LF 归一化 `4105c08d…`）——原绑的活文件已 128,007 B / 1,226 CRLF / raw `5bd81a74…`，同日多路重写（16:40:09 一次、16:50 又出 v0.5 草案），green 无法归因到某一版；④自检 `[4]` 改读该归档副本，并在 `RESULT` 前打印**所校验三文件的 LF 归一化 sha256**（BINDING 段）；⑤`single_sided_exceptions[0]`（`prior_amount_20`）补 `replaces: []`，与第 10 行结构一致。**9 项自检 0 违例、RECORD MISMATCHES 0、exit 0**；反向还原逐字节得回改前 `a53e32c7…`（JSON）与 `c5e4b597…`（本文） | 因子工程师（按策略经理 a1867b5d 裁定）|
| v5.3 | 2026-11-07 17:11 | **只改时间标注与自检绑定，台账数字零改动**：①v5.2 行的时间标注比盘面晚约 8 分钟（盘面 md mtime 16:57:47 / json 16:57:41），已改为真实时间 16:57；②自检 `[4]` 由「只绑归档 v0.3」改为**双绑**归档 v0.3 与活修订 v0.5，先比两份 §7.1 块 sha（当前同为 `e9ed2b10…`，2,513 字符）再逐只比公式，**任一不同即 FAIL 并打印两处 sha**（负样本已实测：把 v0.5 副本的 `ts_mean(close, 120)` 改成 `121` → [4] 违例 2 条、RESULT: FAIL、exit 1）；③`meta.contract_binding` 记双绑对象与「不绑未编号活文件」的理由；④§0.1 指纹表与 §6 实跑输出刷新。**因子数、公式、双 id 组数、warmup 一律未动** | 因子工程师（按开发经理派单）|
| v5.4 | 2026-11-07 17:36 | **只改绑定指针、口径文字与裁定登记，台账数字零改动**：①自检 `[4]` 的 `contract2` 由 v0.5 → **v0.6**；实测 §7.1 块在归档 v0.3 / v0.4 / v0.5 / v0.6 四处逐字节相同，三口径 2,541/`a8e88134…`、2,514/`6d3db013…`、2,513/`e9ed2b10…`，故零翻转；负样本（只改 v0.6 副本 `ts_mean(close, 120)`→`121`，归档不动）→ `[4]` 违例 2 条、打印 archive/live 两处 sha、RESULT FAIL、exit 1；②`meta.revision_note` 过期契约哈希（110,944 B / `6b8fb14c…`〔v5.5 标：作废·中途态，盘上无对应文件〕）改为三份契约现行指纹（raw + LF）；`meta.contract_binding` 记 v0.6 为绑定对象、v0.5 降为非绑定旁证；③登记两条裁定（伴生形态 / `path_scope=history`，见 §12）；④`meta.sources` 两条被其作者更新的文件重算哈希。**因子数、公式、双 id 组数、warmup 一律未动** | 因子工程师（按开发经理派单）|
| v5.5 | 2026-11-07 18:57 | **三处口径收尾，不改结论、不改数字**：①`110,944 B / 6b8fb14c…` 就地标【作废：中途态，盘上无对应文件】，并连 size + sha + 读取时刻一起引（读取时刻 2026-11-07T18:23+0800；全库无此尺寸契约文件）；同族中途态 109,914 B / `5c1264…`、正文前缀 110,098 B / `11bfe51f…` 一并标注；②JSON `meta.sources[0].binding` 与 `self_check.checks[3].rule` 的「活修订 v0.5」改为 **v0.6**，与脚本 `contract2` 行 / `meta.contract_binding.bound[1]` / 本文 §12.3 同一对象；v0.5 仅作非绑定旁证；③§7.1 块口径统一为脚本实算值 2,514 / `6d3db013…`（LF 含尾换行），2,513 / `e9ed2b10…` 与 2,541 / `a8e88134…` 降为同块异量法；④`side_key` 未涉及实质引用（契约 v0.6 §7.10.2：可选、不参与判据；v5.4 基线两文件 0 次实质引用，v5.5 起字样为元陈述）；⑤§0.1 指纹表与 JSON `self_check.generated_at` 刷新。**8 只公式、warmup、deps、双 id 三列、`replaced_by` 四条、K10/K11/K12 登记一律未动** | 因子工程师（按开发经理派单）|
| v5.6 | 2026-11-07 19:21 | **只更新期望表版本与指纹，台账数字零改动**：①§12.1 末行期望表指纹由 v3.2（`91,709 B / f21494f9…`）改为 **v3.3**（`97,062 B / 8366cdb2…`），并写明 v3.3 的重签对象（18:05:22 / 186,343 B / `b661c8cd…`）与独立复算值 `canonical_digest = aefdf528…2d1a`、表外差异 OD-1（14 条伴生 `note`，§7.10.2 未列该字段）；②依 §0.2 定稿声明另立版本号并重报三文件指纹。**8 只公式、warmup、deps、双 id 三列、`replaced_by`、K10/K11/K12 一律未动** | 因子工程师（按开发经理派单）|
| v5.7 | 2026-11-07 19:28 | **只改签认对象与指纹，台账数字零改动**：①产物在 19:23:57 重跑，只改 `generated_at`（186,343 B / `df5e1a63…`，`canonical_digest` 仍 `aefdf528…2d1a`）；②按契约 §7.12.4 把期望表 v3.3→**v3.4**，签认对象由「字节 sha256」改为「三元组」，字节实例降为观测记录（`byte_instances_observed`）；③§12.1 末行期望表指纹 v3.3（`97,062 B / 8366cdb2…`）→ **v3.4**（`99,935 B / 184dcdf9…`）；④依 §0.2 定稿声明另立版本号并重报三文件指纹。**8 只公式、warmup、deps、双 id 三列、`replaced_by`、K10/K11/K12 一律未动** | 因子工程师（按开发经理派单）|
| v5.8 | 2026-11-07 22:29 | **记账修复，数字一律不动**：①自检 `self_check.checks` 由 9 条补到 **11 条**（`[10] freeze_declaration_version_agree` / `[11] md_fingerprint_matches_registry` 按既有结构 id+rule+violations+violation_detail 登记，`check_count` 9→11，`total_violations` 保持 0）——此前脚本已实现、台账只登记 9 条，故 `RECORD MISMATCHES: 2`、`RESULT: FAIL`；②JSON 新增顶层结构化 **`signature`** 块（recipe 1：`aefdf528…2d1a` / `"2"` / `67`，本轮独立复算，非转抄产物字段），此前三元组只在散文里、walk `signature*` 0 命中；③期望表 md v3.3 → **v3.4** 同步（`99,935 B / 184dcdf9…`），消除 md/json 版本错位；④`meta.version` 5.7→**5.8**、`freeze_declaration.status` → `FROZEN at v5.8`，`revised_at`/`declared_at`/`self_check.generated_at` 取实际写入分钟；⑤§0.1 指纹表按实测重报 registry 与自检脚本两行。**8 只公式、warmup(61/121/201/21/56/251/11/21)、deps、shift、双 id 三列与 `alias_side`、`replaced_by` 四条、K1–K12 一律未动** | 因子工程师（按开发经理派单）|
| v5.9 | 2026-11-08 00:40 | **准入载体批（R12），公式与数值一律不动**：①8 只 `uf_*` 盘上 `status` 由 `draft` 升 `active`（逐只带三条实测：V3 全量 `pass_1e12=true`、V3 末交易日全市场截面 `rank_change_max=0.0`、B0 保真 `max_abs_diff=0.0`；写入时刻 2026-11-07T23:33:57，盘上 `version` 仍 1 —— 直写路径不经 upsert 的版本+1 分支，不回写、不伪造）；②8 组双 id 的 alias 侧 `alias_of` / `strategy_usable=false` **载体在 pack 不在盘上 JSON**（`backend/app/custom/research_factor_pack/factor_specs.py:71-79` + `_spec()`），盘上 15 个定义 JSON 含 `alias_of` 的 0/15 是**正确态**（canonical 行必须为 None，§7.16.5）；③`market_breadth` 与 6 个 pack 单侧件（`ma20`/`ma60`/`sd20`/`boll_lower`/`boll_upper`/`prior_amount_20`）的登记缺口**如实记成缺口**（G4/G5/G6），不用近似因子或伪造字段糊；④闸门 `mode=production` 实测：8 个 alias 全 `FS03`、8 只 canonical 全 PASS、6 个单侧件全 `FS01`、`market_breadth` `FS02`。**8 只公式、warmup、deps、shift、双 id 三列、`replaced_by` 四条、K1–K12、`signature` 三元组一律未动**；新增 §15 | 因子工程师（按开发经理派单）|
| v5.9（§7.1 改绑部分） | 2026-11-08 00:46 | **只改自检 `[4]` / `BINDING` 的绑定对象，数字与公式零改动**：①`[4]` 与 `BINDING` 段的判据对象由「版本文件全文」改为「§7.1 块」，登记常量两套口径（LF 归一化 2,514 / `6d3db013…`、原始 CRLF 2,541 / `a8e88134…`），读取来源 v0.6→**v0.12**，**版本号退出判据**；②删除 `CONTRACT_PREV`（v0.5 旁证），新增 `rel()`：绑定文件在仓库外时打印绝对路径并正常 FAIL，不再由 `relative_to` 抛异常；③负样本（v0.12 副本改 §7.1 一个窗口数字，长度不变）：`[4]` 违例 **5** / `RESULT: FAIL` / exit **1**，原版 PASS / exit 0；④§0.1 补两套口径与引用规则、指纹表脚本行重测为 33,261 B / 729 行 / `5a2460ab…`；§6 输出按 v5.9 实跑重抄。**8 只公式、`warmup_bars`、`dependencies`、shift、双 id 三列、`replaced_by` 四条、`signature` 块、K1–K12 一字未动** | 因子工程师（按开发经理派单）|
| v5.10 | 2026-11-08 00:52 | **勘误批（三处自洽缺陷 + 并发写入登记），公式与数值一律不动**：①8 只 `strategy_usable_note` 仍是「status 仍 draft / usable_now=false」的 v5.9 残留、与同行 `status=active` 相反 → 逐只改写并新增 `status_carrier`（载体路径 + 写入时刻 + 盘上 version）；②§15.5 把 G5 写大一格（称还需「注册因子 id → DSL 标识符」层，以 `uf_vol60` 也 `E001` 作对照）→ 该对照是没走启动期 `load_into_registry` 的假象，实测装载后 `compile_formula('uf_vol60')` `ok=True/warmup=61`，G5 验收④降为「登记即通过」；③6 个单侧件「补 status 还是豁免」明确裁定**不豁免**（`gate.py:74` `EXEMPT_KINDS` + §7.8.4 末行），交 G4；④**并发写入登记**：与另一条会话「台账 BINDING 改绑 §7.1 块哈希」在 00:44–00:46 同写三文件，本版合并后重报指纹，以本次 `RESULT: PASS` 为唯一有效签认。另修 §15.4 表格末行缺尾 `\|`。**8 只公式、warmup、deps、shift、双 id 三列、`replaced_by`、K1–K12、`signature` 未动** | 因子工程师（按开发经理派单）|

**本文件（v5.5）没做的事**：没注册/没注销任何因子、没写实现代码、没改引擎、没改 `backend/**`、没改 `docs/research/`、没改 `docs/architecture/`、没改 `research/*`、没改 `docs/factors/` 下他人文件、没提交、没部署、没重启服务。

---

## 10. v2 逐格改动与依据来源

每一格改动都标了依据来源，便于下一个人复核（三选一：**策略经理 §8** / **我的实测** / **独立审核报告**）。

| # | 位置 | 改前（v1 要点） | 改后（v2 要点） | 依据来源 |
| --- | --- | --- | --- | --- |
| 1 | 标题下状态行（:3） | 「未写入运行库、未做数值对账、未改任何既有文件」 | 8 只已由系统开发工程师落盘+注册；`prior_amount_20` 已注册；已对账并已独立复核；运行中的服务未重启 | **我的实测**（load 前后 192/206，16:07）+ 对账报告 §5/§6 + **独立审核** §9 第 1、6 行 |
| 2 | §0 表「写入运行库（注册）」 | 「未做；`get_factor('uf_vol60')` 返回 `None`」 | 「已由系统开发工程师完成（14:30:24 落盘），启动期装载后 8/8 可取；服务未重启」 | **我的实测**（`load_into_registry` 载入 14 条 → 206）+ **独立审核** §9 第 6 行 |
| 3 | §0 表「F-A3 / V3 数值对账」 | 「未做；本文不含任何新因子的保真结论」 | 引用 `F_CLASS_PARITY_20261107.md` 8/8 PASS、7 只 0.0、`uf_vol60` 1 ULP、超 1e-12 行数 0；标注独立审核 F-A3 PASS / F-A5 FAIL | 对账报告 `F_CLASS_PARITY_20261107.md` + **独立审核** `:19`、`:21` |
| 4 | §0「一句话」 | 「本批未注册的 `dist_prior_high_250`」 | 「尚未注册（批二立即可做、零引擎改动）」 | **策略经理 §8.3.1** |
| 5 | §1.2 新增 K7 | —（v1 无此条；对账报告 §7 归因 `_safe_div`） | 「差异 100% 来自研究侧 `pct_change()`，与 `_safe_div` 无关」 | **独立审核** §3.2 `:84-95`、P3-3 `:237`、§9 第 9 行 `:252` |
| 6 | §1.2 新增 K8 | —（v1 写「系统无 ma120」） | pack 以裸 id 注册 `ma120`/`ma200`/`vol60`/`prior_amount_20`，与 `uf_*` 同口径并存 → 唯一性已破，待架构师裁定 | **我的实测**（未 load 时 192 条已含裸 id；`get_factor('ma120')` 有 spec）+ **独立审核** P2-3 `:220-224` |
| 7 | §1.2 新增 K9 | —（v1 无此条） | 8/8 只磁盘 `label` 与台账不同（含当日/未年化等语义只在台账） | **我的实测**（读 `uf_vol60.json`/`uf_prior_vol_20.json` 的 `label`）+ **独立审核** P2-4 `:226-228` |
| 8 | §2.1 `ma120`/`ma200`/`vol60` 行「replaces / 被替换」格 | 「无（系统无 ma120）」等 | 「裸 id 已由 pack 同口径注册（K8）」 | **我的实测** + **独立审核** P2-3 |
| 9 | §2.1 `prior_low_10` 行 + §2.8「替换关系」格 | 「`low_60d` 的 `replaced_by` 未明列 / 未指定（候选，待确认）」 | 「`low_60d.replaced_by = prior_low_10`，**降级替换、非同口径等价**（10 vs 60、low vs close、不含当日 vs 含当日）；不注册 `prior_low_60`；展示侧不动」 | **策略经理 §8.2** |
| 10 | §2.10 表 + 新增「注册表语义」段 | 「8 个 id 与 8 个研究名在 178 条注册表中全部不存在」 | 「未 load = 192（178 内置 + 14 pack），8 只必然 MISSING；load 后 = 206，8/8 存在」 | **我的实测**（16:07，命令见 §8 第 2 条）+ **独立审核** P3-1 |
| 11 | §4 全节 | 三项一律「本批未注册」；`amount` 量纲「未确证」；`dist_prior_high_250` 附「`_safe_div` 要确认」；`rsi_14_pct`「需扩算子」 | `prior_amount_20` 已注册 + `unit=CNY`、缺口关闭；`dist_prior_high_250` 批二立即可做/小数/分母≤0或空→空/`_safe_div` 的 null 已接受/不解锁 S08；`rsi_14_pct` 押后 E1/E2 + base 列路线 + IEEE vs `1e-12` 分叉 | **策略经理 §8.1/§8.2/§8.3** + 开发经理 16:03 转达（base 列路线）+ **我的实测**（`registry.py:33-57` 无 `formula` 字段；`pipeline.py:566/575-583`；`factor_provider.py`） |
| 12 | §5「配套但本批未做的动作」表 `replaced_by` 行 | 「`low_60d` 待裁定 / 部分」 | 两格都可填：`high_60d`→`prior_high_55`、`low_60d`→`prior_low_10`，**均带降级标记** | **策略经理 §8.2** + D1 §4.2 |
| 13 | §6 自检输出 | v1 14:45 输出 | v2 2026-11-07T16:10 重跑输出（文件内容已变，`TOTAL VIOLATIONS: 0` / `RECORD MISMATCHES: 0` / `RESULT: PASS` / exit 0） | 本次运行（命令见 §6） |
| 14 | §7 全节 | 「数值保真未确证、本文没有给任何 `max_abs_diff`」；`amount` 量纲「阻断」；`low_60d`「只能写未指定」 | 开头显式更正该自相矛盾并改为「引用 `F_CLASS_PARITY_*` + 标注独立审核状态」；`amount` 项关闭；`low_60d` 项关闭；新增 1 ULP 定因、双 id、label、矩阵回测路径四项 | 对账报告 + **独立审核** + **策略经理 §8** |
| 15 | §8 复现命令 2 | 单态命令（只看未 load 的 178 条） | 两态命令（192 → 206）+ 单项核查命令（`prior_amount_20`/`dist_prior_high_250`/`rsi_14_pct`/`low_60d` 等） | **我的实测** |
| 16 | `docs/factors/evidence/f_class_registry.json` | v1 同款字段 | 同步以上全部项（`meta.version=2`、`registry_state_verified`、`prior_amount_20_registered_fact`、`dist_prior_high_250_spec`、`rsi_14_pct_plan`、`replacement_rulings`、K7–K9、`v2_changes`） | 同上 |
| 17 | 标题下状态行（:3） | v2 状态行 | v3 状态行 + ④`dist_prior_high_250` 已以 `uf_dist_prior_high_250` 注册并对账 0.0、⑤`rsi_14_pct` base 列路线实测不可行 | **我的实测**（16:12）+ **b2 报告**（系统开发工程师，§2/§3） |
| 18 | §0 一句话、§0 表 | 「尚未注册的 `dist_prior_high_250`」；`F-A5` 行「未测」 | dist 改「已注册但一策未解锁」；新增批二行（`max_abs_diff = 0.0`、jaccard 1.000000）；`F-A5` 改「独立审核实测 FAIL（本人未复测）」 | **我的实测** + **b2 报告** §2 + **独立审核** `:21` |
| 19 | §2.10 两处计数与 absent 行 | 载入 14 条 → **206**；「四个 id 全部不在注册表」 | 载入 15 条 → **207**；`uf_dist_prior_high_250` 已在册（并给 spec 摘要）、裸 id 仍 `None`；其余三个仍不在 | **我的实测**（`load_into_registry` 返回 15 个 id） |
| 20 | §4 引言 + §4 表（dist / rsi 两行） | dist「**未注册**」、rsi「走指标层 base 列、不扩 DSL 算子」 | dist「**已注册 + 逐位对账 0.0**、注册了也不解锁 S08」；rsi「不扩算子成立、但 base 列**实测不可行**、须改 `pipeline.py` Pass 5 三处」 | **我的实测** + **b2 报告** §2/§3 |
| 21 | §4.2 标题、新增「实测状态」表、顺带行 | 「批二立即可做、零引擎改动」；顺带「注册时把 `distance_to_high_240d.replaced_by` 指到本因子」 | 「**已注册为 `uf_dist_prior_high_250`，逐位对账 0.0**」+ 11 项实测表（含分母异常行数、首根、幂等、未验证四项）+ K10 + 注册元数据缺口；顺带改「台账侧已登记、`FactorSpec` 无 `replaced_by` 字段」 | **b2 报告** §2（系统开发工程师实测）+ **我的实测** 16:12 |
| 22 | §4.3 路线 bullet、新增「实测」表 | 「复用现成 base 列即可，因此归排期决策」 | 「不扩 DSL 算子成立，但须改 `pipeline.py` Pass 5 三处」→ 归「指标层引擎改动 + 排期」；附 `max_abs_diff = 28.8984`、jaccard 0.9484/0.8985、`al=0` 2,871 行、根因三分解、warmup 语义待裁定 | **b2 报告** §3（16:09 实测） |
| 23 | §5 表「注册表状态」行（`prior_high_55` 列） | 「本批未注册；`get_factor` 现返回 None」 | 「已落库 `uf_prior_high_55.json`（14:30）、load 后存在（207 条中）；**未 load 的进程里**是 `None`」 | **我的实测** + 本文 §2.10 |
| 24 | §7 新增 14 / 15 / 16 行 | —（v2 只到 13） | 14 = `_safe_div` 只拦 `==0`（K10）；15 = base 列非零改动（K11）；16 = 批二独立审核尚未做 | **b2 报告** §2.2/§3.4 + **我的实测** |
| 25 | §8 命令 2 注释、新增 2c；§6 输出头 | 「load 之后 = 206」、无批二命令；输出头写 v2（16:10） | 「load 之后 = 207（15 条定义）」+ 新增 2c 单项命令；输出头改为 v3、并注明**对契约 v0.4 重跑** | **我的实测** + 契约 v0.4（16:13:21，sha256 `5c1264…`） |
| 26 | `f_class_registry.json` → `meta.sources[*].sha256`（3 条） | 契约 `e272b357…`、caliber `096aca89…`、gap spec `cc27dfe3…` | 契约 `5c1264…`（v0.4）、caliber `d95551c1…`（15:27:40）、gap spec `7c93d4f2…`；并新增 b2 报告为来源 | **我的实测** sha256（16:12:54）：原记录是三份文件各自更新前的旧版 |
| 27 | `f_class_registry.json` 新增块 | — | `v3_changes`（V3-1…V3-8）、K10/K11、`registry_state_verified.after_load.count_history`（206→207）、`dist_prior_high_250_spec.parity`、`rsi_14_pct_plan.measured_now`、`meta.authority_revision_note`（契约 v0.3 冻结 → v0.4） | 同上 |

| 28 | §2.3–§2.9 七处「保真」行、§0 表「写入运行库」/「F-A6 单位量级」两行、§2.1 读表须知 1、§2.6「解锁还需」行、§2.7「服务策略」行 | 「**未做**（V3）。本文不含 `max_abs_diff`」等 7 处；「注册表 206 条」；「未注册、V3 未过」；「`prior_vol_20` 同样未注册」；「`dist_prior_high_250` 本批未注册」 | 七处改为引用 `F_CLASS_PARITY_20261107.md` §2/§3 的逐只 `max_abs_diff`、n 与判定 jaccard（vol60 1 ULP；ma120/ma200/prior_high_20/55/250/low_10/vol_20 均 0.0）+ 标注「本台账不复算」；206→207；后三处按注册现状改写；F-A6 由「系统侧未测」改为给出系统侧 mean/p50/p01/p99（并指出字面区间会误伤 p01） | 对账报告（系统开发工程师）+ **独立审核** `:19` + **我的实测** 16:12 |
**没有改动的格子**：8 只的 `formula_text` / `window` / `warmup_bars` / `dependencies` / `semantics` / `shift` / `price_basis` / `unit`（除台账 §4 新增项）/ `scale_free` / `direction` / `status` / `version` —— 与契约 §7.1 逐字一致，`check_f_class_ledger.py` 的检查 3、4、5 会继续强校验。

---

## 11. v4 逐格改动与依据来源（`superseded_by` 那一次）

每一格都标了依据来源（**契约 §7.8.2 A-1/A-2** / **架构裁定 `ID-CANON-1`** / **我的实测** / **检查实跑**）。v1–v3 的逐格记录在 §10，不重复。

| # | 位置 | v4 之前 | v4 之后 | 依据来源 |
| --- | --- | --- | --- | --- |
| 1 | §2.1b 标题与表头 | `canonical_id` / `aliases[]` / `canonical_reason` / `replaced_by` / `alias_of` / alias 侧 `strategy_usable` | 加两列：`superseded_by[]`（canonical 行，恒 `[]`）与「alias 侧 `superseded_by[]`」（= `[canonical_id]`）；10 行（8 组 + 2 条单侧例外）全部填 | **契约 §7.8.2 A-1**（台账逐行写 `canonical_id` / `aliases[]` / `superseded_by` / `canonical_reason`）；**架构裁定 §2.2**（`replaced_by` 只表跨口径） |
| 2 | §2.1b 读表须知 | 3 条 | 4 条：新增第 4 条「`superseded_by` 与 `replaced_by` 不是同义字段」并写明两侧取值规则；第 3 条改「四字段 + `alias_side_superseded_by` + `column_semantics`」 | 同上（防下游把两个字段混用） |
| 3 | §2.1b 的 `alias_of` 列（8 行） | `vol60` → `uf_vol60` | `alias_of = uf_vol60` | **检查实跑**：原写法人看得懂但机器校验不到字段名，检查 9 需要逐行可判；语义未变 |
| 4 | §6 输出块与检查表 | 6 项输出（v3，2026-11-07T16:15） | **9 项真实输出**（16:28，原样粘贴）+ 「v4 新增三项防什么」+ 9 行检查表 | **检查实跑**（`python docs/factors/evidence/scripts/check_f_class_ledger.py`，exit 0） |
| 5 | §9 变更记录 v4 行 | ①–⑤ | 追加 ⑥（`superseded_by` 一列）、⑦（自检 6 → 9 项并把四列并入必填） | 本次 |
| 6 | `evidence/f_class_registry.json` 的 8 条 factor 行 | `canonical_id` / `aliases` / `canonical_reason`（`canonical_reason` 为各口径具体理由） | 增 `superseded_by`（`[]`）、`alias_of`（`null`）、`alias_side_superseded_by`（`[canonical_id]`）、`canonical_column_note` | **契约 A-1/A-2** + 我的实测（8 组配对） |
| 7 | `id_canonical_ruling.dual_id_groups[]`（8 条） | `n` / `canonical_id` / `alias` / `alias_of` / `alias_strategy_usable` / `canonical_reason` / `replaced_by` | 增 `aliases` / `superseded_by` / `alias_side`（含 `strategy_usable=false`、`superseded_by=[canonical]`）；单侧例外也补 `superseded_by: []` | 同上 |
| 8 | `id_canonical_ruling.column_semantics`（新） | —（只有散落在文字里的说明） | 五字段逐一写死语义 + 「字段名来自两处规范」的说明 | **契约 A-1** + **架构裁定 §2.2** |
| 9 | `prior_amount_20_registered_fact` | 只有 `id` / `registered` … | 增 `canonical_id = prior_amount_20`、`aliases = []`、`superseded_by = []`、`canonical_reason`（裁定原文）、`canonical_exception` | **架构裁定 §2.3**（例外必须写理由） |
| 10 | `v4_changes` | V4-1…V4-5 | 增 V4-6（`superseded_by` + 必填字段覆盖） | 本次 |
| 11 | `self_check` | 6 项 | 9 项（新增 7/8/9 的 rule 与 `violations: 0`）+ `note_v4`；【6】rule 文案补四列 | **检查实跑** |
| 12 | `check_f_class_ledger.py` | 6 项；`REQUIRED_FIELDS` 无 id 唯一性四列 | `REQUIRED_FIELDS` 加 `canonical_id` / `aliases` / `superseded_by` / `canonical_reason`；空列表校验加 `aliases`、null 校验加 `superseded_by`；新增检查 7/8/9 | **契约 A-1/A-2**（缺这层校验，【6】会假通过） |
| 13 | `known_doc_conflicts`（JSON）新增 K12 | — | 登记「`replaced_by` 条数 3 vs 4」：`replacement_rulings` 4 条（含 `rsi_14` → `rsi_14_pct`，目标未注册），`replaced_by_rulings_cross_caliber_only` 3 条；**md §1.2 表只到 K9，K10–K12 只记在 JSON，md 正文按 K 号引用时须写「JSON K12」**，避免悬空引用 | 我的实测（逐条数 `replacement_rulings[*].subject`）+ §4.3 |

**没有改动的格子**：8 只的 `formula_text` / `window` / `warmup_bars` / `dependencies` / `semantics` / `shift` / `price_basis` / `unit` / `scale_free` / `direction` / `status` / `version` 一字未动（检查 3/4/5 继续强校验）；契约 §7.1 八行未变；未触 `backend/**`、`docs/research/`、`docs/architecture/`、`research/*`、`docs/factors/` 下他人文件；未提交、未重启服务。

---

## 12. v5.4 登记：两条裁定 + 绑定指针（依据逐条给出）

本段只登记**别人的裁定与我的实测**，不新增裁定。两条都直接影响引用因子盘存的判词，故入账。

### 12.1 裁定 (a)：伴生记录形态

**规定**（契约 v0.6 §7.10.2 字段表 L1066）：`both_collision` —— 主记录恒 `false`，伴生记录恒 `true`（§7.12.2）。
**固定取值**（§7.12.2）：`record_kind=companion`、`both_collision=true`、`verdict=exempt`、`code=null`；**不参与** allowlist、不参与放行判定、不计入任何层的 `by_verdict`。
**形态**（开发经理本轮裁定）：伴生记录取**因子侧视图** —— `ref_namespace=factor`、`class=custom_dsl`、`resolved_id` = 对应 pack 因子 id，并带 `note` 说明「同名基础列优先、不参与放行」；不复制主记录的 column 视图。主记录保持 `ref_namespace=column` / `class=base` / `verdict=allow` / `both_collision=false`。

**我的实测**（22 条活配置，独立重扫 `data_root`）：主记录 **79** + 伴生 **14** = **93**。伴生逐出现展开：`ma20` 10 + `ma60` 2 + `boll_lower` 1 + `boll_upper` 1。主/伴生共用 `(source_path, evidence, side, ref_name)` 元组，**靠 `record_kind` 区分**——冲突可见性从配对得来，不靠主记录上的布尔位。
期望表落盘：`docs/factors/evidence/referenced_factor_inventory_expected_20261107.json`（**v3.4**，99,935 B / 2958 行 / LF / `184dcdf9…`）。v3.2 按 §7.8.3 把主记录 `verifiable` 由 `true` 改 `null`；v3.3 重签到 18:05:22 现行产物（186,343 B / `b661c8cd…`），`canonical_digest` = 独立复算 `aefdf528…2d1a`，并登记表外差异 OD-1（14 条伴生 `note` 措辞，§7.10.2 未列该字段 → 不参与判据、不进唯一键、不进 allowlist）。【v5.5 内注：该行 v3.2 指纹 `91,709 B / f21494f9…` 已被 v3.3 覆盖，属期望表自身版本演进，非台账数字变动】

### 12.2 裁定 (b)：`path_scope=history` 是代码事实，不是推断

**代码依据**（契约 v0.6 §7.10.3 **N4**）：`backend/app/strategy/custom_signals.py:646-647` —— `build_intraday_expressions` 里 `if sig.get("enabled") is False or sig.get("timeframe") != TIMEFRAME_INTRADAY: continue`。日线信号**根本不进盘中帧**，`materialize_factor_columns` 的同名因子补算对它们不可达。
**因此**：21 条日线源 `path_scope=history`、1 条 `monitor_rule` = `intraday`、`both` 计数 **0**、`path_divergence` 全 `false`；7 条冲突源 `verdict=allow`；契约 §7.10.5「按 N1/N2 被 `FS01` 拦的 = 0 条」与之自洽。
**撤回**：我在 v2 期望表里把 `kind:"both"` 读成求值路径、给了 7 条 `shadow` 与 `path_scope=both`，那是**推断**，现已按 N4 全部撤回（`shadow` 0 条、`both` 0 条）。`both` 只允许在同一 source 真的被两条路径编译时出现。
**代价**：若实现违反 N2（把 `allowed_fields()` 的因子并集当因子引用）→ 未物化 → 缺列优雅降级 → 这 7 条信号恒 `null`，依赖它们的 entry/exit 永不触发，**不报错不告警**（静默停机，比 400 更危险）。

### 12.3 绑定指针与 §7.1 块口径

自检 `[4]` 的 `contract2` 由 v0.5 改指 **v0.6**（R6 于 2026-11-07T17:16:36 冻结）。实测 §7.1 块在**归档 v0.3 / v0.4 / v0.5 / v0.6 四处逐字节相同**，只是行尾与边界口径不同：

| 口径 | 字符数 | sha256 |
| --- | ---: | --- |
| 原始 CRLF，含尾换行（团队通报用值） | 2,541 | `a8e88134f60b504c…` |
| LF 归一化，含尾换行（脚本实算值） | 2,514 | `6d3db0139a45f54c…` |
| LF 归一化，去尾换行（v5.3 曾用值） | 2,513 | `e9ed2b10618ef4cf…` |

同一块文本的三种量法，**不是三个不同的块**。改指针零结论翻转；v0.5 降为**非绑定旁证**，只用于打印「块未漂移」。

**v5.5 口径统一**：JSON 侧 `meta.sources[0].binding` 与 `self_check.checks[3].rule` 原仍写「活修订 v0.5」，与脚本 `contract2` 行、`meta.contract_binding.bound[1]` 不一致；现已一并改为 **v0.6**，并把该两处引用的块指纹由 2,513 / `e9ed2b10…` 改为脚本实算口径 2,514 / `6d3db013…`。**v0.5 只在 `meta.contract_binding.non_binding_evidence` 出现**，作用仅是「块未漂移」旁证，不参与判据。
**负样本**（只改 v0.6 副本的 `ts_mean(close, 120)` → `121`，归档不动）：`[4]` 违例 **2** 条、打印 `archive 6d3db013… vs live 6b7273cc…`、`RESULT: FAIL`、exit **1**。

**v5.9 改绑（判据对象：版本文件全文 → §7.1 块；其余 10 条判据、全部数字与公式不动）**：v5.4–v5.8 的双绑只覆盖「指针所指的那一版」；指针停在 v0.6 期间，v0.7–v0.12 的 §7.1 有没有被改写根本不进比对视野。v5.9 起：判定对象＝§7.1 块；登记常量两套口径（LF 归一化 2,514 字符 / `6d3db013…`；原始 CRLF 2,541 字符 / `a8e88134…`）；两份绑定文件（归档 v0.3 + 现行修订 v0.12，仅作读取来源）每份都必须两口径等于常量，且两份块彼此相等；**契约版本号不再是判据输入**，换版不翻转结论。脚本里 `CONTRACT_PREV`（v0.5 旁证打印）随之删除，v0.5 / v0.6 降为 JSON `meta.contract_binding.non_binding_evidence` 的历史旁证。另修一处只在异常路径暴露的缺陷：原写 `blk["path"].relative_to(REPO)`，绑定文件位于仓库外时抛 `ValueError`（负样本会变成 traceback、拿不到判定），改为 `rel()` —— 仓库外打印绝对路径并正常 FAIL，判据对象与阈值不变。
**v5.9 负样本（本轮实跑，不碰仓库文件）**：把 v0.12 复制到 `C:/Users/A/AppData/Local/Temp/fa72/neg/contract_v0.12_mutated.md`，只把 §7.1 里 `ts_mean(close, 120)` 的窗口 `120` 改成 `121`（长度不变：副本仍 269,092 B，块仍 2,514 / 2,541 字符，**只动 sha**），再把脚本的 `CONTRACT_LIVE` 指向该副本跑 → `[4]` **违例 5 条**（LF 块 `6b7273cc…` ≠ 常量；CRLF 块 `e309b0ed…` ≠ 常量；两份块 LF 不同；两份块 CRLF 不同；`ma120` 的 `formula_text` 不同）、`RESULT: FAIL`、exit **1**；同一命令跑原版 → 违例 0 / `RESULT: PASS` / exit 0。**拦住它的确实是块哈希，不是文件长度、也不是版本号。**

### 12.4 本轮发现的一处契约文本错数（不改判据，只报）

契约 v0.6 §7.12.1 写「期望表保留字面量 `field:ma60`（79 条中 **38 条**带前缀）」。
**实测是 36 条**：22 条活配置里带 `field:` 前缀的字面量恰好 36 条（全部在右值）；产物 17:10 版的活配置**主记录** `side=R:field` 也正好 **36** 条（另 12 条属伴生记录，合计 48）。
判据不受影响：F-A37 只断言 `ma_golden_20_60.json:11` 必须是 `field:ma60`，不依赖这个总数。**建议把 §7.12.1 的 38 改为 36**（契约文本不归我改）。

---
## 15. 准入载体批（v5.9，2026-11-08）：status / alias_of / market_breadth

本节只登记**载体事实**，不改任何公式、`warmup_bars`、`dependencies`、`shift`、双 id 三列与 `replaced_by`。

### 15.1 改前 / 改后逐 id 对照（8 只 canonical）

改前基线：全部 `status=draft`（契约 v0.12 §7.15.3 于 2026-11-07 17:4x 实测「15 个盘上文件都是 `"status": "draft"`」）。改后：`status=active`，且每只都带自己的三条实测，无一只靠「批量写 active」放行。

| # | 研究名 | canonical id | 改前 status | 改后 status | 改后 `alias_of` | 改后 `strategy_usable` | V3 `max_abs_diff`（n_both_nonnull） | V3 末交易日全市场 `rank_change_max` | B0 保真 `max_abs_diff` | production 闸门 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `vol60` | `uf_vol60` | `draft` | `active` | `null` | `true` | `1.1102230246251565e-16`（5,469,335） | `0.0` | `0.0` | PASS（0 码） |
| 2 | `ma120` | `uf_ma120` | `draft` | `active` | `null` | `true` | `0.0`（5,428,988） | `0.0` | `0.0` | PASS |
| 3 | `ma200` | `uf_ma200` | `draft` | `active` | `null` | `true` | `0.0`（5,371,122） | `0.0` | `0.0` | PASS |
| 4 | `prior_high_20` | `uf_prior_high_20` | `draft` | `active` | `null` | `true` | `0.0`（5,496,401） | `0.0` | `0.0` | PASS |
| 5 | `prior_high_55` | `uf_prior_high_55` | `draft` | `active` | `null` | `true` | `0.0`（5,472,715） | `0.0` | `0.0` | PASS |
| 6 | `prior_high_250` | `uf_prior_high_250` | `draft` | `active` | `null` | `true` | `0.0`（5,332,523） | `0.0` | `0.0` | PASS |
| 7 | `prior_low_10` | `uf_prior_low_10` | `draft` | `active` | `null` | `true` | `0.0`（5,503,218） | `0.0` | `0.0` | PASS |
| 8 | `prior_vol_20` | `uf_prior_vol_20` | `draft` | `active` | `null` | `true` | `0.0`（5,496,401） | `0.0` | `0.0` | PASS |

证据出处（逐条可复算，本文只引用不重算）：

| 列 | 文件 | JSON 路径 |
| --- | --- | --- |
| V3 `max_abs_diff` / `n_both_nonnull` | `docs/factors/evidence/F_CLASS_PARITY_20261107.json` | `#factor_parity.<canonical id>`（`tol=1e-12`、`n_over_tol=0` 全部 8/8） |
| V3 截面 `rank_change_max` | `docs/factors/evidence/F_CLASS_RANK_PARITY_20261107.json` | `#pairs.<research name>.rank_last_day_full_market.rank_change_max` |
| B0 保真 | `docs/factors/evidence/registration_b0_20261107.json` | `#fidelity.per_factor.<research name>.max_abs_diff` |
| 闸门实测 | 本文 §15.3 的命令 | `assert_factors_usable([id], mode="production", facts=RegistryFacts(data_dir=settings.data_dir))` |

**`vol60` 的单列说明**：V3 全量 `max_abs_diff = 1.11e-16`（4,214,876 行非零、`n_over_tol = 0`），按 §7.15.2 的口径记为「`max_abs_diff < 1e-12` 判过」，**不得**写成「逐位相同」。其余 7 只实测 `0.0`，可写「逐位相同」。

**为什么不用 B2 的 E1/E2/E3 判据做依据**：E1/E2/E3 是 `market_breadth`、`xs_rank_*`、`in_universe` 三类载体的判据（`docs/factors/B2_IMPLEMENTATION_20261107.md` §2–§4），**不覆盖** F 类 8 只表达式因子。这 8 只的适配证据只能是 V3 全量 + V3 截面名次 + B0 保真这三份。

### 15.2 alias 侧 `alias_of` 的载体在 pack，不在盘上 JSON

| # | alias（研究原名） | `alias_of` | `strategy_usable` | 载体 | 盘上 JSON |
| --- | --- | --- | --- | --- | --- |
| 1 | `vol60` | `uf_vol60` | `false` | pack | 无（也不需要） |
| 2 | `ma120` | `uf_ma120` | `false` | pack | 无 |
| 3 | `ma200` | `uf_ma200` | `false` | pack | 无 |
| 4 | `prior_high_20` | `uf_prior_high_20` | `false` | pack | 无 |
| 5 | `prior_high_55` | `uf_prior_high_55` | `false` | pack | 无 |
| 6 | `prior_high_250` | `uf_prior_high_250` | `false` | pack | 无 |
| 7 | `prior_low_10` | `uf_prior_low_10` | `false` | pack | 无 |
| 8 | `prior_vol_20` | `uf_prior_vol_20` | `false` | pack | 无 |

- 载体位置：`backend/app/custom/research_factor_pack/factor_specs.py:71-79`（`_ALIAS_OF` 8 条，逐行照抄契约 §7.15.1 第 1–8 行）+ `:106-107`（`_spec()` 把 `alias_of` 与 `strategy_usable` 写进 `FactorSpec`）。字段名与 `backend/app/factors/registry.py:61-65` 一致，未自造字段。
- **为什么不能写盘上 JSON**：`backend/app/factors/store.py:17` `CUSTOM_ID_PATTERN = re.compile(r"^uf_[a-z0-9_]{1,40}$")`，`store.to_spec()`（`store.py:73-85`）对不匹配的 id 直接 `ValueError`。8 个研究原名都不带 `uf_` 前缀，写进去既不能注册也不合法。契约 §7.15.1「载体」列本身就写着「store（canonical）+ pack（alias）」。
- **「盘上 15 个定义 JSON 含 `alias_of` 的 0/15」不是缺陷**：这 15 个文件全是 canonical 侧（8 个 `uf_*` + `uf_dist_prior_high_250` + 5 个 `uf_auction_*`）加 `cf_auction_resonance`；按 §7.16.5，canonical 行的 `alias_of` **必须**为 `None`。0/15 是正确态。

### 15.3 闸门实测（done_when ②）

```bash
cd C:/work/sourcecode/tick-stock-panel/backend
./.venv/Scripts/python.exe - <<'EOF'
import sys; sys.path.insert(0,'.')
from app.config import settings
from app.factors.gate import assert_factors_usable, GateError, RegistryFacts
F = RegistryFacts(data_dir=settings.data_dir)
for i in ["vol60","ma120","ma200","prior_high_20","prior_low_10","prior_high_55","prior_vol_20","prior_high_250",
          "uf_vol60","uf_ma120","uf_ma200","uf_prior_high_20","uf_prior_low_10","uf_prior_high_55","uf_prior_vol_20","uf_prior_high_250"]:
    try: assert_factors_usable([i], mode="production", facts=F); print(i, "PASS")
    except GateError as e: print(i, e.code)
EOF
```

实测结果（2026-11-08 00:29）：

| 组 | 结果 |
| --- | --- |
| 8 个 alias（`vol60`/`ma120`/`ma200`/`prior_high_20`/`prior_low_10`/`prior_high_55`/`prior_vol_20`/`prior_high_250`） | **8/8 `FS03`**，`message` = 「生产入口不允许 alias，请改用 canonical id `uf_*`」 |
| 8 只 canonical（`uf_*`） | **8/8 PASS（0 码）** |
| 16 个 id 一次送入 | `FS04`（`ma120`/`uf_ma120` 混用同口径两 id）— §7.16.6 的设计行为，不是缺陷 |

**一个必须写清的读法**：只用 `RegistryFacts()`（不传 `data_dir`）时，8 只 canonical 与 `market_breadth` 全报 **`FS02`（未登记）**——那是「闸门没接盘上定义」的读法，与 `status` 无关。本批所有结论一律用 `RegistryFacts(data_dir=settings.data_dir)`（`settings.data_dir = D:\TSP\data`）。

**v5.11 起改引仓库内可复跑脚本（上面那段 here-doc 只作口径说明保留）**：`research/b0b-20261107/verify_fs03_realdisk.py` 把同一条判据做成落盘产物——

```bash
cd C:/work/sourcecode/tick-stock-panel/backend
PYTHONUTF8=1 ./.venv/Scripts/python.exe ../research/b0b-20261107/verify_fs03_realdisk.py
```

2026-11-08T00:51 实跑 **9/9 PASS / 0 FAIL**，日志 `research/b0b-20261107/logs/fs03_realdisk.json`（8,245 B / `1e00af393632f488…1f7e`）：

| 检查项 | 它证的是什么 | 结果 |
| --- | --- | --- |
| `P0.alias_table_matches` | pack 的 `_ALIAS_OF` 与 §7.15.1 第 1–8 行逐对相同（不是第二份权威） | PASS |
| `P1.providers_ready` | 5 个 pack 装载就绪（`factor_count=33`） | PASS |
| `P2.canonical_on_disk` | 8 只 canonical 的定义 JSON 都在盘上 | PASS |
| `A1.eight_aliases_all_FS03` | 8/8 alias `error_code=FS03`（`failing: []`） | PASS |
| `A2.eight_canonicals_no_FS03` | 8/8 canonical 不含 FS03（`failing: []`） | PASS |
| `A3.diagnostic_does_not_reject_alias` | diagnostic 模式不拦 alias（8 个 `None`） | PASS |
| `A4.spec_carrier` | `FactorSpec.alias_of` 载体真进了对象（逐只打印） | PASS |
| `A5.disk_json_has_no_alias_of` | 15 个盘上 JSON 全无 `alias_of`（canonical 的正确态） | PASS |
| `A6.disk_status_snapshot_info` | 8 只盘上 `status=active` 的快照（本批写入后的现状） | PASS |

**读这 8 个 alias 的 `blocked_codes` 要注意**：它们同时带 `FS03` 与 `FS01`。`FS03` 是契约 §7.16.2 C2 的 alias 判据（生产入口不许用 alias，改用 `uf_*`）；`FS01` 是 alias 自身的 pack `FactorSpec` 没有 `status` 载体（同 G4 的根因）。**判据只认 `error_code == FS03`**，`FS01` 不构成新缺口。


### 15.4 仍然被拒的 7 个 id（如实记缺口，不糊）

| id | 码 | `detail.status` | 载体 | 缺什么 |
| --- | --- | --- | --- | --- |
| `ma20` | `FS01` | `None` | pack（唯一载体） | 该 id 没有 `status` 载体：pack provider 注册的 `FactorSpec` 数据类无 `status` 字段；store 的 id 正则不收非 `uf_` 前缀，盘上 JSON 无法承载 |
| `ma60` | `FS01` | `None` | pack | 同上 |
| `sd20` | `FS01` | `None` | pack | 同上 |
| `boll_lower` | `FS01` | `None` | pack | 同上 |
| `boll_upper` | `FS01` | `None` | pack | 同上 |
| `prior_amount_20` | `FS01` | `None` | pack | 同上；且 §7.15.1 第 14 行明令不得新建 `uf_prior_amount_20`，不能靠「建双胞胎」绕 |
| `market_breadth` | `FS02` | `None` | 无 | 登记面为零：`grep -rn "market_breadth" backend/app --include=*.py` **0 命中**、`all_factors()` 无此 id；store 走不通（id 正则），pack 走通需要新增 `FactorSpec`（即 `backend/app/**` 代码） | |

**这两类缺口都不是「写个近似因子」「把 status 硬写进没人读的 JSON」能解决的**，按缺口规格交开发经理排期：`docs/factors/FACTOR_GAP_SPEC_20261107.md` §9（G4 / G5 / G6）。

#### 15.4.1 二选一的裁定（补 v5.9 未落笔的那一步，v5.10）

派单要求「6 个单侧 id 要么补 `status`，要么在台账里明确写『由闸门豁免，依据 X』，二者选一」。**裁定：不豁免，也不补 status —— 两条都做不到，交 G4。** 逐条依据（全部实测/读代码，非推理）：

| 选项 | 能不能做 | 依据 |
| --- | --- | --- |
| 闸门豁免（按 id 名单开小门） | **不能，且不允许** | 闸门的豁免集是 `EXEMPT_KINDS = frozenset({"base","virtual"})`（`backend/app/factors/gate.py:74`），黑名单语义：其余 kind 一律进判定；这 6 只 `kind=custom`。§7.8.4 末行明令「Provider 注册且无 `status` 的按 `draft` 处理」——**漏填必须失败**。按 id 名单豁免会直接把「策略只经因子表达」这条规则的执行点打开一个后门，且无任何契约条款可引。 |
| 补 `status`（盘上 JSON） | **不能** | 盘上 `status` 只能由 store 承载：`CUSTOM_ID_PATTERN = ^uf_[a-z0-9_]{1,40}$`（`backend/app/factors/store.py:17`）+ `to_spec()` 抛 `ValueError`；这 6 个 id 不带 `uf_`，**没有合法载体**。 |
| 补 `status`（建 `uf_` 双胞胎） | **不能** | pack provider 注册的 `FactorSpec` 数据类无 `status` 字段（`backend/app/factors/registry.py`）；且 §7.15.1 第 14 行明令不得新建 `uf_prior_amount_20`；建双胞胎还会把「同口径两 id」的 FS04 混用问题引进来。 |

**结论**：这 6 只在 `production` 今天是 `FS01`（`detail.status=None`），这是**设计行为，不是放行缺口**；解除必须走 G4（`status` 进 `FactorSpec` / provider 注册路径显式给值，量级 S，须走契约→实现→独立审核）。机器可读版：registry 顶层 `admission_carrier_rulings.ruling_single_sided_6`。

### 15.5 目录计数口径（done_when ③ 的一半）

| 口径 | 值 | 怎么算的 |
| --- | --- | --- |
| 现盘进程内 `all_factors()` | **195** | `_CATALOG` 77 + provider 33 + 其它动态注册 85；本机 5 个 pack 全装（`factor_provider_status()`：`packages_scanned=14`、`modules_loaded=5`、`factor_count=33`） |
| pytest 快照口径（`backend/tests/test_factor_registry.py:289`） | **110** | `_CATALOG`(77) + provider 的 33 = 110；实测 `pytest tests/test_factor_registry.py::test_catalog_counts_and_kinds` **1 passed** |
| 本批之后 | **仍 110** | `market_breadth` **未登记**，因此没有 110→111。要变 111 必须新增一个 `FactorSpec`，属实现工作（G5） |

`compile_formula` 面（**v5.10 更正，v5.9 此处写错了一格**）：`compile_formula("market_breadth")` 现在返回 `E001 未知标识符: market_breadth`，原因只有一个 —— 它**未登记**。v5.9 原文接着写「已注册的因子 id 本来也不是 DSL 标识符（对照 `compile_formula("uf_vol60")` 同样 `E001`），所以要成立还得打通『注册因子 id → DSL 标识符』这一层」，**该对照是假象**：它只在没有启动期装载的裸进程里成立。

实测（同一 venv，`backend/.venv/Scripts/python.exe`，2026-11-08 00:47）：

| 步骤 | `compile_formula("uf_vol60")` | 说明 |
| --- | --- | --- |
| 裸进程（未装载 store） | `ok=False` / `E001` | `get_factor("uf_vol60")` 为 `None` —— 只是没装载，不是解析层缺失 |
| `store.load_all(settings.data_dir)` + 逐条 `register_factor(store.to_spec(d))`（15 条里 9 条可注册，其余 6 条因依赖 `ext_*` 未装载而跳过） | `ok=True` / `warmup_bars=61` | 装载后同一表达式立即通过 |

读代码同样成立：`backend/app/factors/dsl.py:676` / `:690` 对每个标识符先查 `BASE_COLUMNS`、再 `get_factor(name)`；启动期由 `backend/app/main.py:217-221`（`store.load_into_registry`）与 `backend/backtest/worker.py:234-236` 把盘上 `uf_*` 装进注册表。**所以「注册因子 id → DSL 标识符」这一层本来就存在，不需要新建。**

**对 G5 的影响（把缺口写小，不是放水）**：`market_breadth` 一旦成为 `FactorSpec`（并随启动期进入注册表），`compile_formula("market_breadth")` 会自动通过；G5 的验收④由「额外打通标识符解析层」降为「登记即通过」。派单 done_when ③ 里「可 `compile_formula("market_breadth")` 通过」这一条**今天仍不成立**，唯一原因仍是**未登记**。

与此同时仍成立的是：它的**口径表达式**今天就能编译 —— `compile_formula("xs_mean(close > ma60, in_universe)")` → `ok=True`、`warmup_bars=120`，与 E1 声明的 120 一致。

### 15.6 本批没做的事

- 没有改 `backend/**`、没有改任何公式/`warmup_bars`/`dependencies`/`shift`、没有提交、没有部署。
- 没有为 6 个 pack 单侧件伪造盘上定义（会因为 id 正则失败并污染启动期装载日志）。
- 没有为 `market_breadth` 造 `semantics` / `cross_sectional` 字段：`backend/app/factors/registry.py:33-68` 的 `FactorSpec` 字段表里**没有**这两个字段，写了也没有读者（G6）。
- `xs_mean` 的「按日聚合、按标的广播」语义本身已实现（B2 §3 表格：池外行同值广播、池内无有效样本 → null），缺的是**登记**与**语义字段载体**，不是计算能力。

### 15.7 v5.10 勘误记录与并发写入登记

**三处勘误**（逐条见 §0.2 的 v5.10 段与 registry 顶层 `v5_10_changes`）：①8 只 `strategy_usable_note` 与同行 `status` 相反 → 改写并新增 `status_carrier`；②§15.5 的 G5 口径写大一格 → 已改正（标识符解析层本来就存在）；③6 个单侧件的「豁免 or 补 status」二选一未落笔 → §15.4.1 明确裁定「都不行，交 G4」。

**并发写入登记（必须记，不遮）**：本文件与 registry 在 2026-11-08 00:44–00:46 被**两条会话同时写入** —— 另一条会话在做「台账 BINDING 改绑 §7.1 块哈希」（脚本 `check_f_class_ledger.py` 00:44:53 改写、md 00:46:14 写入），本条会话在做「准入载体批勘误」（registry 00:45:29 写入）。后果是**混合态**：registry 的 `meta.version=5.10` 与 md 状态行的 `v5.9` 一度不一致，自检因此报 `TOTAL VIOLATIONS: 2 / RESULT: FAIL`（`[10]` 版本不符、`[11]` §0.1 指纹过期）。

**处置**：以「后写者合并前写者」的方式收口 —— 本版把两侧改动合并到同一份 md + registry 上，重报三文件指纹（registry `158,382 B / 093f44c9…`；脚本 `33,261 B / 5a2460ab…`），并以本次自检 `RESULT: PASS` 为唯一有效签认；`v5.9` 与 `v5.10` 两次写的内容都在盘上，没有一方被静默覆盖。

**这条为什么值得写进台账**：§0.2 的定稿声明把「第三方直写」列为定稿失效条件，而本次不是第三方 —— 是**同一角色的两条会话**。若不加约束，两条会话各自 `read → 改 → write` 会互相覆盖，而 `[11]` 只能发现「指纹过期」，发现不了「某一段结论被对方版覆盖」。建议：`docs/factors/` 三文件同一时刻只允许一条会话持有写权（派单或串行化），本条作为机制缺口的证据。

**本节没做的事**：没有改 `backend/**`、没有改盘上因子定义、没有提交、没有部署；`signature` 三元组未动。

## 16. done_when ③ 的现状与 market_breadth 实现门票（v5.11）

派单 done_when ③ 是三格：「`compile_formula("market_breadth")` 通过」「目录计数 110 → 111 并说明口径」「台账 md + registry 自检 exit 0」。**第一、二格本批未达成，第三格达成**。以下每一格都给实测，不写推断。

### 16.1 三格现状

| done_when ③ | 现状 | 实测 |
| --- | --- | --- |
| `compile_formula("market_breadth")` 通过 | **未达成** | `E001 未知标识符: market_breadth`；`grep -rn "market_breadth" backend/app --include=*.py` → **0 命中**；`all_factors()` 无此 id |
| 目录计数 110 → 111 并说明口径 | **未达成，仍是 110** | `pytest tests/test_factor_registry.py::test_catalog_counts_and_kinds` → 1 passed（`len(specs) == 110`、id 唯一 110、virtual 61、pit 7 全过） |
| 台账两文件自检 exit 0 | **达成** | `docs/factors/evidence/scripts/check_f_class_ledger.py` → `TOTAL VIOLATIONS: 0` / `RECORD MISMATCHES: 0` / `RESULT: PASS` / exit 0（11 项全登记） |

### 16.2 110 这个数怎么来的（口径，逐项可复算）

| 组成 | 数量 | 出处 |
| --- | --- | --- |
| `_CATALOG`（代码内建的 base + virtual） | 77 | `backend/app/factors/registry.py` 的 `_CATALOG` 常量 |
| provider（5 个 pack 装载后贡献） | 33 | `factor_provider_status()`：`packages_scanned=14` / `modules_loaded=5` / `factor_count=33`；含 8 个 alias 与 6 个单侧件 |
| **合计（pytest 快照口径）** | **110** | `backend/tests/test_factor_registry.py:289` `assert len(specs) == 110` |

**两个数不许互相「更正」**：进程内 `all_factors()` 另有 85 只动态注册（撞名条款 F-A44 的那批等），裸进程读数是 **195**；**110 是 pytest 快照口径**（77+33），不是 195。§15.5 已记过这条，此处再钉一次，因为 G5 的验收要拿 110/111 说话。

### 16.3 为什么我做不到把 110 变 111（不是时间问题，是没有载体）

登记 = 新增一个 `FactorSpec`。三条落点，逐条实测：

| 落点 | 能不能用 | 依据 |
| --- | --- | --- |
| `_CATALOG` 硬编码 | 不能（不是我的活） | `backend/app/factors/registry.py`，属 `backend/app/**`；本角色不写实现代码 |
| provider / pack 的 `factor_specs.py` | 不能（同上） | `backend/app/extensions/factors.py#ensure_factor_providers` 只发现 `app.custom` 下的 Python 包；pack 是 `backend/app/custom/research_factor_pack/factor_specs.py` |
| store 盘上定义 JSON | **不能（载体本身不允许）** | `CUSTOM_ID_PATTERN = ^uf_[a-z0-9_]{1,40}$`（`store.py:17`）+ `to_spec()` `ValueError`；实测 `to_spec({"id":"market_breadth",…})` → `ValueError: id 必须匹配 ^uf_[a-z0-9_]{1,40}$` |

**所以这一步只能由系统开发工程师实现，我出的是实现门票。** 这也是 BOTH「策略必须经因子表达」与「因子工程师不写实现代码」两条规则的交叉点：**登记面归我判定，实现面归开发。**

### 16.4 实现门票（G5）：登记参数逐项照抄策略经理裁定，不许改口径

| 字段 | 值 | 说明 |
| --- | --- | --- |
| `id` | `market_breadth` | 单侧，**不建 `uf_market_breadth` 双胞胎**（理由同 `prior_amount_20`；若出现双胞胎，§7.16.6 的 FS04 会把同口径两 id 判为混用） |
| `formula_text` | `xs_mean(close > ma60, in_universe)` | 今日即可编译：`compile_formula` → `ok=True`、`warmup_bars=120` |
| `semantics` | `market_aggregate_daily` | **今日无字段载体**（G6）：`FactorSpec` 23 项字段里没有 `semantics` |
| `cross_sectional` | `true` | 同上（G6）：无 `cross_sectional` 字段 |
| `warmup_bars` | `120` | 与 E1 声明一致 |
| `dependencies` | `{close, ma60, in_universe}` | `ma60` / `in_universe` 均在 pack 侧已注册 |
| `strategy_usable` | `true` | 单侧件，不是 alias |
| 强制约束 | **禁止对其再做任何截面算子或排名** | 否则按标的广播后重复计数，约 3,000 倍 |

### 16.5 实现完成后的验收（5 条，可机械判定）

1. `get_factor("market_breadth")` 非空，且 `warmup_bars == 120`、`dependencies == frozenset({"close","ma60","in_universe"})`。
2. `compile_formula("market_breadth")` → `ok=True`（登记即通过，**不需要**额外打通「id → DSL 标识符」层，见 §15.5 的 v5.10 更正）。
3. `assert_factors_usable(["market_breadth"], mode="production", facts=RegistryFacts(settings.data_dir))` → **0 码**（不得是 FS01/FS02）。
4. `pytest tests/test_factor_registry.py::test_catalog_counts_and_kinds` → 111；**必须同步改** `backend/tests/test_factor_registry.py:289`（`len(specs) == 110`）与 `:290`（`len({spec.id for spec in specs}) == 110`）两个常量，否则测试红。若 `market_breadth` 进 provider，还要看 `factor_provider_status()["factor_count"]` 从 33 变 34 会不会撞别的常量 —— 实现时须**全量跑** `tests/`。
5. 既有判据不动：`research/b0b-20261107/verify_fs03_realdisk.py` 仍 **9/9 PASS**（8 个 alias 出 FS03、8 只 canonical 不出）。

### 16.6 连带风险（实现时必须在同批想清，不许留给「以后再补」）

- **`semantics` / `cross_sectional` 今天没有消费者**（G6，P2/M）。若只求 §16.5 的 1–4 成立，**不必**等 G6 —— 登记与语义字段可以两步走。但「禁止再套截面算子」这条约束若只写在 `formula_text` / `label` 里，是没有消费者的文字：闸门拦不住 `xs_rank(market_breadth)` 这类再聚合。**我的口径：可以两步走，但登记那一行必须写明「该约束尚未被执行」，不许当已落实。**
- **「按日聚合、按标的广播」的语义本身已实现**（B2 §3：池外行同值广播、池内无有效样本 → null），缺的是登记与语义字段载体，**不是计算能力**。这条别写反。
- `market_breadth` 若走 pack，会出现在 `factor_provider_status()` 的 33 里；若走 `_CATALOG`，则 77 变 78。**两条路都改 110→111，但改的测试不一样**：走 `_CATALOG` 要一并看 `test_catalog_counts_and_kinds` 里 `virtual == 61` / `pit == 7` 是否受影响（`market_breadth` 不是 virtual、不是 pit，故这两条应不变，但要实跑证明）。

### 16.7 本节没做的事

没有改 `backend/**`、没有改盘上因子定义、没有为 `market_breadth` 造任何 JSON 或装饰字段、没有提交、没有部署；`signature` 三元组未动。**没有用「近似因子」代替 `market_breadth`**：全市场宽度是跨标的聚合，任何单标的滚动计数（如 `limit_up_count_20d`）都不可替代（§3 E1 已论证）。
