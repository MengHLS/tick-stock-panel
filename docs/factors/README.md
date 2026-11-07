# 因子台账与规格（docs/factors）

本目录由因子工程师维护：只放**台账、口径决策、缺口规格**，不放实现代码。
系统代码实现一律在 `backend/app/**`，由系统开发工程师经系统开发流程落地。

> **风险（2026-11-07 由文档管理员登记）**：`docs/architecture/` 与 `docs/factors/` **都未入 git** —— `git ls-files docs/architecture docs/factors` 返回 **0 条**，`git status` 显示 `?? docs/architecture/`、`?? docs/factors/`。因此「谁在何时改了判据」**没有版本可回放**，只能靠本文《判据与台账指纹》一节的手抄留痕；任何审核绑定都必须能对上那组手抄值，对不上就是「不可绑定」，不得记 PASS。

| 文件 | 内容 | 状态 |
| --- | --- | --- |
| `FACTOR_REGISTRY_CORE_93_20261107.md` | 93 个核心已注册因子（id / 公式 / 口径 / warmup / 数据源 / 空值 / PIT） | v1，2026-11-07 盘点 |
| `STRATEGY_INPUT_FACTOR_MAP_20261107.md` | 12 条策略每个输入的来源映射与实测口径差异 | v1 |
| `FACTOR_GAP_SPEC_20261107.md` | 缺口规格：需求 / 口径定义 / 验收标准 / 影响面 / 量级 | **v1.1**（29,333 B / 304 行 / sha256 `7c93d4f2…` / mtime 16:07:28）：v1.1 只改 §3-E2 的验收判据（改用契约 v0.3 §3.4.1 `XS-A1`–`XS-A8`，研究侧选股数与 `jaccard` 降级为 `xs_rank_pct` 诊断值），其余各节未动；E2 已定接口与判据 ≠ 已实现/已验收，其余各项仍待排期 |
| `XS_RANK_POOL_SPEC_20261107.md` | 截面排名三口径可执行规格：`xs_rank_pool`（唯一策略可用）/ `xs_rank_market`（诊断）/ `xs_rank_pct`（历史与差异证明），五字段 + 验收判据 A1–A8/B1–B3/C1–C3 + 台账三条 + S06/S07/S10/S11/S12 的 id 对照 | **v1 生效 2026-11-07**（决定四） |
| `FACTOR_ENTRY_RULE_20261107.md` | 策略准入规约 v1：提交物＝「已注册因子 id + 参数 + 声明式执行约束」的 JSON；12 条策略逐条准入结论；批 A（14 个因子）注册批次建议 | **v1 生效 2026-11-07**（42,038 B；只做判定与批次建议，不含实现代码） |
| `F_CLASS_REGISTRATION_20261107.md` | F 类八只因子注册台账 v4：研究名↔`uf_` id 映射、口径主表、三条坑；§2.1b 新增 8 组同口径双 id 的 `canonical_id` / `aliases[]` / `superseded_by` / `canonical_reason` 四列（canonical 一律 `uf_*`，研究原名作 alias 且 `strategy_usable=false`；`prior_amount_20` 是**单 id 例外**，canonical = 研究原名，无 `uf_prior_amount_20`） | **v4**（**90,105 B / 597 行 / sha256 `561f66c5…`** / mtime 16:28:48）。文内自述「只登记、未写入运行库、未做数值对账」——**已被 2026-11-07 14:30 落盘推翻，原文保留**。**已入库**：8 个 `uf_*` 定义文件在 `D:/TSP/data/user_data/custom_factors`（14:30:24–14:30:26）；注册表是**进程内**的，须 `load_into_registry(Path(data_dir))` 后可见（`all_factors()` 192 → **207**；**必须传 `Path`，传 `str` 会 TypeError**；`app/main.py:221` 启动期调用）。未重启服务，故线上未生效。**数值对账已过独立审核**（F-A3 PASS，`research/independent-review-20261107/F_CLASS_AUDIT_20261107.md`，15:57:34）；**但 F-A5 独立审核判 FAIL**（16:10:38），见下《三条流程结论》3 |
| `REGISTRATION_B0_20261107.md` | 批 B0 交付：14 个研究基线因子注册（14/14 判据表） | 他人产物，仅登记不评价 |
| `evidence/f_class_registry.json` | 机器可读台账 v4：字段同表 + `self_check`（**9 项**）+ `id_canonical_ruling.dual_id_groups[]`（8 组 `alias_side`） | **89,781 B / 1,886 行 / sha256 `f91ed220…`** / mtime 16:28:01。可复算（`check_f_class_ledger.py` 校验；本人 16:33 复跑 exit 0、9/9 项 0 违例）。注：文件内钉住的契约指纹 `110,944 B / 6b8fb14c…` 已与磁盘现行不符，见《三条流程结论》1 附注 |
| `evidence/scripts/check_f_class_ledger.py` | 台账只读自检：解析契约 §7.1 做字符级比对，**11 项**检查（`[1]`–`[9]` 之后增 `freeze_declaration_version_agree` / `md_fingerprint_matches_registry`），双绑 v0.3 归档件 + v0.6 的 §7.1 块（两处同为 2,514 字符 / `6d3db013…`，`identical: True`），退出码 0/1 | **29,356 B / 661 行 / sha256 `3e4b677ee9a281ff3086847c6b62bf2f9b224f8c04c5e7cf23af36a0ead1d496` / mtime 21:34:11**（不是 16:26 那版 20,224 B / 9 项）。**本人 21:44 实跑：11 项逐项 `violations: 0`、`TOTAL VIOLATIONS: 0`，但 `RECORD MISMATCHES: 2`（`[10]`/`[11]` 尚未写进 JSON 的 `self_check` 块）、`RESULT: FAIL`、**exit 1**——属台账 v5.7→v5.8 写入中的**记录同步缺口**，不是判据不通过；判据本身 0 违例。**16:33 那次「9/9 PASS」已不代表当前状态，不得再引。**另：脚本只绑 v0.3+v0.6，对 v0.10 **无约束力**（我另查 v0.10 正文仍含 8 条 §7.1 公式原文，见《三条流程结论》1）。脚本只读，不写盘 |
| `evidence/F_CLASS_PARITY_20261107.md` / `.json` | 系统 DSL vs 研究 `add_indicators` 逐位对账（F-A3） | **独立审核已判 F-A3 PASS**（`research/independent-review-20261107/F_CLASS_AUDIT_20261107.md`，15:57:34：F-A1–F-A4、F-A6 通过，F-A5 FAIL 见《三条流程结论》3）：8/8 通过、7 只 `max_abs_diff=0.0`、`uf_vol60` 1 ULP。**本人未重跑**（会覆盖原件，见下行） |
| `evidence/scripts/f_class_parity.py` | 对账脚本（生成上一行的 `.json`；本人**未重跑**） | 复算须知：**运行会覆盖 `evidence/F_CLASS_PARITY_20261107.json`（脚本 L330-331 直接 `write_text`）**。该 json 是**当时的对账原件**（12,007 B / sha256 `e37071d1…` / mtime 15:25:43），**任何人重跑前必须先备份**，否则原件被这次运行替换，「当时的对账」就无从追溯 |
| `evidence/F_CLASS_RANK_PARITY_20261107.md` / `.json` | F 类 **V3 补充对账**：8 只 × 20 symbol × 近 250 交易日（2025-10-21~2026-10-30）逐值 + 末交易日截面名次漂移；20 只为 `in_universe` 1723 只按 symbol 升序**等距确定性**抽样 | md **6,047 B / 46 行 / `f56dcfa4…`**（16:25:35）、json **11,378 B / 431 行 / `3d8ab878…`**（16:25:21）。作者自报（16:24 实跑 16.8s）：**8 对全部 `<1e-12`**，7 只逐位 `0.0`，`uf_vol60` 子样 `2.78e-17`，名次漂移 **0**。**独立审核对这份 V3 证据尚未见裁定（待核）**——不得据此记 PASS |
| `evidence/scripts/f_class_rank_parity.py` | 生成上一行 `.json` 的对账脚本（研究侧只 `import common`，系统侧 `compile_formula().frame_transform()`） | **10,352 B / 229 行 / `79fcd61e…`**（16:24:58）。复算须知：脚本 docstring 写明**输出 `F_CLASS_RANK_PARITY_20261107.json`**，重跑前同样先备份 |
| `evidence/E3_DATA_AVAILABILITY_20261107.md` | 停牌 / ST / 退市 / 上市天数四项数据可得性取证（含 1 项阻塞：ST 表末端截断） | v1，含未修复缺陷。**实测口径细节（2026-11-07 复核）**：ST 被抹平的窗口按交易日算是**两段**，两种说法都对——① `st_history` 只覆盖到 2026-10-29，而 2026-10-20 起 **8 个交易日**（10-20..10-29）`st_flag` 被批量置 False（10-20 当日 198 行、全部 False；as-of 后 ST=True 家数 10-19 为 192 → 10-20 起为 0），属「有覆盖但值错」；② K 线轴到 2026-11-06，2026-10-30..11-06 **6 个交易日**在 `st_history` 中无任何记录，属「无覆盖」。合计 **14 个交易日**（8+6）不可用于 ST 判据 |
| `evidence/registration_b0_20261107.json` | B0 批量注册证据（由 `verify_b0.py` 生成） | 他人产物，仅登记不评价 |
| `evidence/xs_rank_family_specs_20261107.json` | 截面排名三口径的机器可读规格 | 随 `XS_RANK_POOL_SPEC_20261107.md` 生效 |
| `D:/TSP/data/user_data/custom_factors/uf_dist_prior_high_250.json`（**生产落盘，非本目录**） | 批二 A 因子定义：DSL `close / ts_delay(ts_max(high, 250), 1) - 1`，warmup 251，分母同权重口径、分母为 0/空时走 `_safe_div` → null | `version=1` / `status=draft`（**756 B / sha256 `7c8163e4…` / mtime 16:07:00**）。对账 **独立审核 PASS**（`research/independent-review-20261107/BATCH2_ABC_AUDIT_20261107.md`，16:29:27）：`max_abs_diff=0.0`、n=**5,332,523**、jaccard=**1.0000000000**、`den≤0` 共 **0** 行、落盘未经再改写 |
| `evidence/` | 机器可读证据（清单 CSV/JSON、口径对照、截面统计、映射 JSON） | 随脚本可复算 |

### 生产目录实况（2026-11-07 16:33 本人逐文件读取 `D:/TSP/data/user_data/custom_factors`）

- 共 **15 个 json**：`status` **全部 `draft`**，**`active` = 0**。
- `lang`：**9 个 `dsl`**（8 只 F 类 + `uf_dist_prior_high_250`），**6 个 auction 类缺 `lang` 键**（10-31 18:19:56 落盘，未被本轮覆盖）。
- 独立审核 C 项（16:29:27）提示：若按契约 §7.7.2 矩阵直接上闸门，**生产可用因子 = 0（store 0 + pack 0），会全站停产**；唯一缓冲是 §7.8.5 过渡期条款，其前置产物 `referenced_factor_inventory` **现已存在**（`docs/architecture/evidence/referenced_factor_inventory.json`：**186,343 B / 218 记录 / 全文 `df5e1a63…` / mtime 19:23:57**，本人 21:35 复算；`schema_version=2`、`canonical_digest=aefdf528…`、`scanned_sources=67`、`stale_count=0`；`live_config` 口径＝`source_enabled=true` 的 **22 源 / 93 记录 / allow 79 + companion 14**）。但**产物存在 ≠ 闸门可上线**：见 `docs/architecture/evidence/WORKTREE_SHIP_MANIFEST_20261107.md` 的《干净检出会缺哪些》——两个 pack 目录未入库，**干净检出时这 15 个因子（14 + `in_universe`）会整体消失**。

### 判据与台账指纹（本人 `hashlib.sha256` / 逐字节复算；「读取时刻」= 本文件写入前最后一次读取；行数＝换行符个数，`wc -l` 口径）

| 文件 | 字节 | 行数 | 全文 sha256 | 读取时刻 | 备注 |
| --- | ---: | ---: | --- | --- | --- |
| `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.10.md` | **244,093** | **2,057** | `8a3115aaf0e8c5162e8b5aa15f70affd34e342e3288018dec412cd3e08b5a007` | 21:39:53（mtime） | **现行（v0.10，本周期终版）**。文内只自指正文：`head -c 242303` → `e47703f2da50837627013d67abb8eebda094a2314490e35884de26af2cc4b870`（**本人复算一致**）、行数 2,057；**全文指纹由我算（文内不自指）**＝左列。生成器 `research/arch-build-20261107/build_contract_v10.py`（21,820 B / 21:39:51）。**注意：@开发经理 的 brief 说「v0.9 现行」，v0.10 是 brief 之后 21:39:53 才落盘的**，见《三条流程结论》1。**本人 21:50 复现：把生成器的 `DST` 重定向到 `research/_repro/` 后运行，产出与盘上逐字节相同（`identical=True`，244,093 B / `8a3115aa…`）；v0.9 同法复现亦逐字节相同（228,478 B / `5d0abbb5…`）** |
| `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.9.md` | 228,478 | 1,957 | `5d0abbb59636ae9c38929ed04d35899b0a2b11727a99d2c2a84ef601bc8b4b0c` | 21:14:03（mtime） | **已被 v0.10 取代、保留不删**。正文前缀 `head -c 226428` = `d967d463…`（本人复算一致）；可复现：`research/arch-build-20261107/build_contract_v09.py` 把 `DST` 重定向到临时路径后实跑，逐字节相同（本人 21:31 实测 `identical=True`） |
| `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.8.md` | 206,608 | 1,792 | `2cf85ccbaaf1fed7e5316bf2c83c73b5193fc02f3aadf3b3e453600aabaedd2f` | 21:04:09（mtime） | **已被取代、保留不删**。正文前缀 `head -c 204939` = `18b769a4…`；钉住的副本 `research/arch-build-20261107/_base/v0.8_base_2cf85ccbaaf1.md` 与盘上**逐字节相同**（本人 21:31 / 21:45 两次实比 `True`） |
| `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.7.md` | 193,586 | 1,696 | `5a87d4b090d996abf28f45cce9f1b5bc6c97c7505371e512b12fe89c1f8723e8` | 18:03:23（mtime） | 18:03 快照，已被取代；其 `F-A30`–`F-A41` 判定对象不变 |
| `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md`（**未编号**） | 128,007 | 1,226 | `5bd81a7472f10509dd3b000cabcd7ccaa1c1d8faa3a8edd303120edd58ec5531` | 16:40:09（mtime） | **＝ v0.4，不是现行**（旧版本行曾把它误标为「当前版本、v0.4 草案」，已改正；**本文出现「现行」二字时，只指 `_v0.10.md`**）。它是 `F-A5` **重判的判据绑定对象**：独立审核 16:40:15 判 PASS 时引的正是本件的 §7.6 `F-A5` + §7.4 |
| `docs/architecture/CONTRACT_REVISION_R8_20261107.md` | 20,119 | 226 | `1da9c9182138c2eff5696d4811c9c8b1089fa7ee89bf6a814e93c83b9cf80174` | 21:04:09（mtime） | v0.7→v0.8 修订记录（R8）：7 处逐行替换 + 1 处插入、0 删除 |
| `docs/architecture/CONTRACT_REVISION_R9_20261107.md` | 24,466 | 302 | `09310c162fdbd567cc904a58a6ff1021ddda98fa31fc159ba7803790148542a2` | 21:39:09（mtime） | **现已存在**（brief 发出时尚缺，21:39:09 落盘）：v0.8→v0.9 修订对照，自述 9 个 hunk / insert 165 行 / replace 3 段 / delete 0 / numstat **+168 −3**，并自指 v0.9 的正文与全文指纹（与我复算一致） |
| `docs/architecture/CONTRACT_REVISION_R10_20261107.md` | — | — | — | — | **缺件（待补）**：本人 21:41 列 `docs/architecture/` 全目录**无此文件**；v0.9→v0.10 的修订记录截至本行写入时不存在（只有生成器 `build_contract_v10.py`）。**不得据「R10 缺失」推断 v0.10 未经验证，也不得据 v0.10 自述推断 R10 已出** |
| `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md` | 89,833 | 914 | `5eb9772411f723576b657f85af7c0aa26427137a41fb53b5774b935942565903` | 16:11:32（mtime） | v0.3 冻结归档件，**未动**；正文前缀 `head -c 89350` = `b082d902…` |
| `docs/factors/F_CLASS_REGISTRATION_20261107.md` | 90,105 | 597 | `561f66c5ef2402724c21701d0c3435284fd58a0b0d9ddf117749f42779137320` | 16:28:48（mtime） | 台账 v4 |
| `docs/factors/evidence/f_class_registry.json` | 89,781 | 1,886 | `f91ed220a90f294d04f5275dbcc57189eb8848e2780151ab65552e1578c9833b` | 16:28:01（mtime） | 机器可读台账 v4 |
| `docs/factors/evidence/scripts/check_f_class_ledger.py` | 29,356 | 661 | `3e4b677ee9a281ff3086847c6b62bf2f9b224f8c04c5e7cf23af36a0ead1d496` | 21:34:11（mtime） | 只读自检，**11 项**；本人 21:44 实跑：0 违例 / 2 record mismatch / `RESULT: FAIL` / exit 1（台账 v5.8 写入中，见上文第 18 行与下文《F 类台账与对账》） |
| `docs/factors/evidence/F_CLASS_PARITY_20261107.md` | 9,036 | 106 | `f3260f53ff77598efc42fa78e8690a390f02e4bf5110bc163a6551cf800cc1b1` | 14:37:18（mtime） | 对账结论（当时） |
| `docs/factors/evidence/F_CLASS_PARITY_20261107.json` | 12,007 | 397 | `e37071d11f270e40a8a3f182f679f477a99d82465384f9214205a167c96598da` | 15:25:43（mtime） | **证据原件，重跑会被覆盖** |
| `docs/factors/evidence/F_CLASS_RANK_PARITY_20261107.md` | 6,047 | 46 | `f56dcfa425af8d15bed2244850b086af4996faf5752c720ec1926f75acaaeeee` | 16:25:35（mtime） | V3 补充对账结论（作者自报） |
| `docs/factors/evidence/F_CLASS_RANK_PARITY_20261107.json` | 11,378 | 430 | `3d8ab8780650a88c8e74db2d354c5da4012ab3ca3450d8e9e7a30d8737d47887` | 16:25:21（mtime） | 逐对明细，重跑会被覆盖 |
| `docs/factors/evidence/scripts/f_class_rank_parity.py` | 10,352 | 229 | `79fcd61e658a89bfb83d7c638d40a9f4c87bd5c706ec69aa2abf88c5df5af0f0` | 16:24:58（mtime） | 只写上面那个 json |
| `docs/factors/evidence/E3_DATA_AVAILABILITY_20261107.md` | 48,555 | 558 | `719c78cb00679316f039d3962f4e2c42fdf9534ac6c5034490200e343af539a5` | 15:18:41（mtime） | 数据可得性取证 |
| `docs/factors/REGISTRATION_B0_20261107.md` | 20,873 | 282 | `d474fcc8a31a595bfbc7bab438e1d3658483e3306af0adfa3b0380286cea802e` | 20:53:26（mtime） | 注意在 `docs/factors/` 根目录，**不在** `evidence/` 下。**作者 20:53:26 更新过一版**（19,588 → 20,873 B，+1,285），旧指纹已不可复算 |
| `docs/factors/evidence/registration_b0_20261107.json` | 21,959 | 776 | `5873de40e438f0d0480e03fafb328ca605adade6257f32c42f95a67b8519f7f8` | 14:48:41（mtime） | B0 证据 |
| `docs/factors/evidence/xs_rank_family_specs_20261107.json` | 8,272 | 245 | `d72b296bd294bc48c961ea149cb3513415dac0ead654343f02a9c60fb85fa9fd` | 14:32:46（mtime） | 截面排名机器可读规格 |
| `D:/TSP/data/user_data/custom_factors/uf_dist_prior_high_250.json` | 756 | 13 | `7c8163e44571d95ebb88f54a38f971eae743485ceab0003cebd839270fe404f5` | 16:07:00（mtime） | 批二 A 落盘定义，v1 / draft |
| `backend/app/factors/store.py` | **19,502** | **409** | `de77eae6815adecd5e6f75a97329967752bd6b3fe52208a412a88c5641701199` | 16:33:52（mtime） | `git diff --numstat` = **+187/−1**；同一小时内两版（16:23:11 = 17,315 B / +148−1；16:33:52 = 19,502 B / +187−1），**仍在改动中** |

### 台账三文件指纹：本索引已过期 / 与台账 §0.1 冲突（本人 21:50–21:52 实测）

> 按 brief「台账那几行不要动」，本表上方台账两行与自检脚本行的**数字原样未改**，只在此标状态。**台账相关一律以 `docs/factors/F_CLASS_REGISTRATION_20261107.md` §0.1 为准。**

| 文件 | 本索引钉的（旧） | 盘上实测（2026-11-07 21:50–21:52） | 判定 |
| --- | --- | --- | --- |
| `docs/factors/F_CLASS_REGISTRATION_20261107.md` | 90,105 / 597 / `561f66c5…` / 16:28:48（记作 v4） | **115,537 / 685 / `9f7fc90f…` / 19:37:46**（文内自述 v5.7，19:28 修订） | **过期**：v4 那版字节在盘上已不存在 |
| `docs/factors/evidence/f_class_registry.json` | 89,781 / 1,886 / `f91ed220…` / 16:28:01（记作 v4） | **119,029 / 2,088 / `56d30928…` / 19:37:15**（`meta.version=5.7`） | **过期**，但与台账 §0.1 一致 |
| `docs/factors/evidence/scripts/check_f_class_ledger.py` | 29,356 / 661 / `3e4b677e…` / 21:34:11（本表上方已按盘上改过一次） | 同左 | **与台账 §0.1 冲突**：§0.1 钉 26,439 / 591 / `9a6fe146…` / 17:26:45，盘上已不是那份 |

- 「v5.8 写入中」的盘面证据只有一处：自检脚本 21:34:11 已改写（661 行、11 项检查）；**台账正文与 registry 仍停在 v5.7（19:37）**，registry 的 `self_check` 段仍只记 **9 项** —— 三者不同步，故 §0.1 现有一行失去有效绑定。
- 本人 21:51 实跑 `backend/.venv/Scripts/python.exe docs/factors/evidence/scripts/check_f_class_ledger.py`：**exit 1**、`TOTAL VIOLATIONS: 0`、`RECORD MISMATCHES: 2`（`freeze_declaration_version_agree`、`md_fingerprint_matches_registry` 两条新检查未写进 JSON `self_check`）、`RESULT: FAIL`。脚本 `BINDING` 段实打印：registry `56d30928…` / 119,029 B / 2,088 行、台账 `9f7fc90f…` / 115,537 B / 685 行，与盘上一致；v0.3 归档 `4105c08d…` 与 v0.6 `a8334fea…` 两处 §7.1 块同为 2,514 字符。
- **结论（文档层面）**：① 台账 §0.1 的「自检脚本」一行在作者按 §0.2 例外程序重签前**不得作准**；② 任何人不得以本索引上方台账两行的旧数字做判定；③ 台账当前状态是 **FAIL（2 条 record mismatch）**，不得记 PASS。

## 三个必须先知道的结论

1. 注册表实际是 **178** 个因子（base 117 / virtual 61）；本台账的 **93** = 178 − 85 个 `ext_*` 扩展数据因子。财务 PIT 是 **7** 个（另有 `turnover_rate` 依赖历史时点流通股本）。
2. 12 条策略里，纯量价中间量（`momentum_*`、`ma20/ma60`、`boll_*`、`change_pct`）与系统**逐位相同**，可直接复用；卡住的是 `vol60`、`ma120`、`prior_high*/prior_low*/prior_vol20`、掩码截面排名、`market_breadth`、调仓日与组合级执行器。
3. `high_60d` 是「收盘价 + 含当日 + 60」，**不能**当「此前 55 日最高价」用：`close > high_60d` 在 547 万行里一次都不成立。`low_60d` 同理。

## 复算

```bash
cd C:/work/sourcecode/tick-stock-panel/backend
./.venv/Scripts/python.exe ../docs/research/factor-audit-20261107/scripts/build_inventory.py
./.venv/Scripts/python.exe ../docs/research/factor-audit-20261107/scripts/render_inventory_md.py
./.venv/Scripts/python.exe ../docs/research/factor-audit-20261107/scripts/audit_compare.py
./.venv/Scripts/python.exe ../docs/research/factor-audit-20261107/scripts/audit_xs_rank.py
./.venv/Scripts/python.exe ../docs/research/factor-audit-20261107/scripts/build_strategy_map.py
```

脚本全部只读行情库、只写 `docs/` 下的新文件，不改引擎、信号链与注册表。

### F 类台账与对账（2026-11-07 补）

```bash
cd C:/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe docs/factors/evidence/scripts/check_f_class_ledger.py
```

`check_f_class_ledger.py` 只读，退出码 0 = 全项通过。**脚本现在是 11 项**（29,356 B / 661 行 / `3e4b677e…` / mtime 21:34:11），双绑 **v0.3 归档件 + v0.6** 的 §7.1（两处 2,514 字符 / `6d3db013…` / `identical: True`；原始 CRLF 口径 2,541 / `a8e88134…`；不含尾换行 2,513 / `e9ed2b10…`）。**本人 21:44 对盘上现状实跑：11 项逐项 `violations: 0`、`TOTAL VIOLATIONS: 0`，`RECORD MISMATCHES: 2`（`[10]`/`[11]` 未写进 JSON `self_check`）、`RESULT: FAIL`、**exit 1**。这是台账 v5.7→v5.8 写入中的记录同步缺口，不是判据不通过。**16:33 那次「9/9 PASS」已不代表现在的状态，任何人不得再引它作为当前结论。**

**复算陷阱**：`docs/factors/evidence/scripts/f_class_parity.py` 运行会**覆盖** `docs/factors/evidence/F_CLASS_PARITY_20261107.json`（脚本 L330-331 直接 `write_text`）。动它之前先备份原件，否则证据 JSON 被这次运行替换，失去「当时的对账原件」意义。

### 三条流程结论（2026-11-07 定；违反任一条则该轮审核结论不作数）

1. **判据文件在审核过程中被改写 ⇒ 该轮审核绑定作废。** 本轮契约在审核期间被连番改写：89,709 B（中途态，弃用）→ 109,914 B（`5c12645a…`）→ 110,944 B（`6b8fb14c…`）→ 111,370 B（`776d8eed…`，16:32:12）→ 111,368 B（`0604bf2d…`，16:33:03）→ `..._v0.5.md` 138,729 B（16:52:31）→ `..._v0.6.md` 162,361 B（17:16:36）→ `..._v0.7.md` 193,586 B（18:03:23）→ `..._v0.8.md` 206,608 B（21:04:09）→ `..._v0.9.md` 228,478 B（21:14:03）→ **`..._v0.10.md` 244,093 B / `8a3115aa…` / 21:39:53（现行，本周期终版）**；未编号的 `FACTOR_ENGINE_CONTRACTS_20261107.md` 停在 v0.4（128,007 B / `5bd81a74…` / 16:40:09），**它不是现行**。**本轮我亲自观测到的最短间隔只有 50 秒**（R9 修订记录 21:39:09 → v0.10 21:39:53 → `gate.py` 21:40:12）。**规则：任何引用契约的 PASS/FAIL 必须同时写死「size + 全文 sha256 + 读取时间」三者**；缺任一项，结论只能记「不可绑定」。
   - **附注（文档层面，不改台账正文）**：台账早期版本与 `docs/architecture/CONTRACT_REVISION_R3_20261107.md`（22,451 B，16:19:05）里钉的契约指纹是 `110,944 B / 6b8fb14c…`，**早已与磁盘不符**（现行 `v0.10 = 244,093 B / 8a3115aa…`）。台账 v5.5 起已把这条 110,944 / 6b8fb14c 标为「作废」，改为**双绑 v0.3 归档件 + v0.6**（自检脚本 `[4]` 实打印：v0.3 `4105c08d…`、v0.6 `a8334fea…`，两处 §7.1 块同为 2,514 字符 / `6d3db013…`）。按结论 1，`CONTRACT_REVISION_R3` 里那处旧钉仍由作者重钉，本文只登记状态。**本表上方台账两行（`F_CLASS_REGISTRATION` / `f_class_registry.json`）的指纹是 v4 时的值，未随本次改动更新——台账正在写 v5.8，其指纹以台账文件 §0.1 为准。**
2. **`docs/architecture/` 与 `docs/factors/` 都未入 git**，判据变更**无版本可回放**（见文首风险段）。因此「归档副本 == 冻结四元组」只能证明副本自身；**不能**证明被覆盖前的活文件当时就是那个内容 —— 这一点属**未知**，不得并入 PASS。
3. **F-A5（同内容二次注册幂等）：16:10:38 判 FAIL，16:40:15 重判 PASS——绑定对象必须一起引。** 链条：独立审核 16:10:38 判 **FAIL**（盘上形状 8/8 `unchanged=True`；**API 形状 8/8 `unchanged=False`、version 1→2、文件被重写、`lang` 丢失**）→ 实现方改 `store.py`（16:23:11，+148/−1；16:33:52 再改，+187/−1）→ **独立审核 16:40:15 重判 PASS**（`research/independent-review-20261107/FA5_REJUDGE_AND_74_ALIGN_20261107.md`，25,115 B / 277 行 / `cdb62ecd…`；判据绑定 **v0.4 未编号契约** `128,007 B / 5bd81a74…`，实测对象 `store.py` 16:33:52 / `api/factors.py` 16:33:57，`mtime_ns + sha256` 全同；5 条子项全 PASS，`T2b_symmetry` 15/15 对称）。**引用规则：写 PASS 必须连「16:40:15 + v0.4 指纹 + 被实测的两个文件指纹」一起写**；只写「F-A5 PASS」＝不可绑定。

### 双 id 与 `status` 闸门：实现已落地（21:40）、未经独立审核（本人 21:46 全树实测 `backend/app/**`）
- **`backend/app/factors/gate.py` 现已存在**：**25,829 B / 602 行 / `39a9d9cf…` / mtime 21:40:12**（上一版本文写「不存在」时是 16:33，之后已落盘）。`FS01`–`FS06` / `assert_factors_usable` / `GateReport` / `alias_of` 在文件内均可命中（逐词计数：`FS01` 11 / `FS02` 7 / `FS03` 8 / `FS04` 6 / `FS05` 4 / `FS06` 17）；`superseded_by` 仍为 **0**。
- 但**不得记 PASS**：① 独立审核对该文件**没有任何裁定**（`research/independent-review-20261107/` 下无闸门审核件；该目录里唯一提到 `gate.py` 的是 R8 digest 裁定，与本模块无关）；② 文件自述有 **5 条 CONTRACT-GAP**（`mode="none"` 让空串通过、`shadow` 语义契约未写、`entry` 位置参数与 §7.7.2 签名不符、`GateReport` 缺 §7.8.4 的四类诊断字段、`FS02` 的「未登记」口径没算 custom store）；③ 配套 `backend/tests/test_factor_gate.py`（18,056 B / 463 行 / `84591d2a…` / 21:40:32）我也**没跑**。
- 台账里 `canonical_id` / `aliases[]` / `superseded_by` / `canonical_reason` 四列是否**真的进入生产入口**，取决于 gate 是否被接线：`gate.py` 目前只是**未被调用的新模块**：`backend/app/**` 全树**没有任何** `from app.factors.gate import` 或 `factors.gate` 引用（逐文件搜过；`main.py` 里的 `gate` 是 token-network 校验，`mining.py` 里的是选股闸门，均无关）——**接线与否属未验**，不要按「已上线」理解。
- `store.py` 已从 v0.3 的「不动 store」改为允许面（`load_one` / `register_definition` / `_canonical` / `_merge_for_write` / `_GROUP_DEFAULT`）；契约 §7.4 的允许面清单与行号（v0.4 引 207/234；**v0.9 起该表已扩**，我实测 v0.9 的 §7.4 块比 v0.4 新增 `load_one` 行、行号改为 `:360-362`）——独立审核 B-3b 的 FAIL（P2）**是否已随 §7.4 扩充消除，未见裁定 → 待核**。

## 文档写法约定（2026-11-07 定）

- 文档里的命令与路径**一律用正斜杠**（`C:/work/...`、`../docs/...`），禁止直接粘贴 Windows 反斜杠路径。
- 确实必须出现反斜杠时，整条命令放进围栏代码块并用单引号包裹（如 `'..\docs\...'`），写入后再用 `grep -P "[\x07\x08\x0b\x0c\x00]" file.md`（或 `sed -n l file.md`）自检，确认没有控制字符。
- 原因：反斜杠在写入/转义链上会被当成转义符，`\t`/`\b`/`\f`/`\r`/`\a` 会落成 TAB/BS/FF/CR/BEL，命令逐行复制即失效，复现链中断。本节因 `## 复算` 代码块事故（2026-11-07 修复）而定。
