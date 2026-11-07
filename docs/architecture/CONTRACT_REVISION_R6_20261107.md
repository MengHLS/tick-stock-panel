# 契约 v0.5 → v0.6 修订对照（R6，只追加）

生成时间：2026-11-07 17:15（Asia/Shanghai）· 系统架构师
底本：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md`（**一字未改**，138,729 B / 1,298 行 / 正文 `head -c 137598` → `082d26fa…af7fae` / 全文 `c7740508…0c4a21a`）
产物：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md`

**v0.4 仍是 `F-A5` 的绑定对象；v0.5 一字未改；v0.6 只追加，不改任何判据语义。**

## 1. 改了什么（6 处插入 / 3 处逐行替换 / 0 处删除）

| # | 位置 | 形式 | 内容 |
| --- | --- | --- | --- |
| 1 | §0 版本表（v0.5 行后）| 插 1 行 | v0.6 行，指向 R6 |
| 2 | §7.10.2 顶层字段表（`stale_count` 行后）| 插 1 行 | `canonical_digest` |
| 3 | §7.10.2 `schema_version` 行 | **替换 1 行** | `"1"` → `"2"` + v1 降级读法指引 |
| 4 | §7.10.2 `records[]` 表（`evidence` 行后）| 插 7 行 | `path_divergence`/`both_collision`（补表）+ `side`/`ref_name`/`record_kind`/`path_base`（新增）+ `side_key`（可选）|
| 5 | §7.10.3（N3 后）| 插 N4、N4.1–N4.4 | `path_scope` 只记真实求值路径；`both` 需两入口同时编译的证据；撤回期望表 7 条 `both` |
| 6 | §7.10.6 `F-A22` 行 | **替换 1 行** | 补 canonical digest 作比对基准，`.sha256` 降级 |
| 7 | §7.12（新节，§7.11.6 后）| 插整节 | 粒度、记录身份、canonical digest、`summary` 分层、v1 兼容、`F-A34`–`F-A39`、17:10 产物实测差距 |
| 8 | §9 表尾 | 插 2 行 | 清单 v2 状态；期望表 7 条改判 |
| 9 | footer | **替换 1 行** | v0.6 版本、正文 sha、四元组指引 |

机械验证（本机，`difflib.SequenceMatcher` 对 v0.5 与新文件逐行比对）：**replace 3 处（各 1 行）、insert 156 行、delete 0 行**。

未改面逐块相等（块 sha256 前 16 位）：§7.1 八行公式 `a8e88134f60b504c`、§7.9 `73e0ba549781b94f`、§7.11 `9aa94c74bd40a4d2`、§8 `d7434dbcf2aa9fd1`。

## 2. 五条派单逐条落点

### 2.1 字段表与 N3/F-A24 自相矛盾 → §7.10.2 补 3 行（并多拆出 1 个字段）

- 原状：字段表 15 项，无 `path_divergence`、无 `both_collision`；而 §7.10.3 N3 要求「标 `path_divergence=true`」、F-A24 要求「另出一条 `both_collision=true` 的伴生记录」。实施方只能超表，因子侧只能判超表 —— 两边都不算错。
- 实测：17:03 版 167 条、17:10 版 218 条，**每条都带**这两个键（17:10：`both_collision=true` 14 条、`path_divergence=true` 0 条）。
- 处置：补两行；补 `side`（`L`/`R`/`F`）。
- **但 `side` 撞名了，必须裁**：17:10 版把「槽位 + 字面前缀 + 结构键」全塞进 `side`，实测 **9 种取值**（`L` / `R:field` / `scoring` / `formula` / `fields.entry` / `fields.score` / `fields.exit` / `members` / `field`）。一个字段两种维度，既判不了左右值，也做不了唯一键。故 v0.6：`side` 收窄为三值（槽位），结构键移入新增的可选字段 `side_key`（只做人读、不入判据、不进唯一键）。这是本轮唯一一处**超出派单清单**的字段，理由是它不拆就会留下 §7.12 要消灭的同一类歧义。

### 2.2 `records[]` 粒度 → §7.12.2 写死「一出现一记录」

- 17:03 版差异：活配置 **53** 条 vs 期望表 **79** 条。根因两条：`_dedup()`（`:323-328`）+ `emit()` 的 `seen`（`:268-272`）按 (源, 原始串) 去重；`_condition_refs()` 把 `field:` 前缀剥掉（`:342-343`）。
- 写死：一条记录 = 一个结构化引用出现处，`left`/`right` 各一处，**不合并重复名**；伴生与主记录一一对应。
- 计数（本机实测，活配置 22 源）：主 **79** + 伴生 **14** = **93**；4 个冲突名逐出现展开 = `ma20` 10 + `ma60` 2 + `boll_lower` 1 + `boll_upper` 1。
- **17:10 版已按此口径重生成**：活配置 93 = 79 + 14、`both_collision` 14、`ma_golden_20_60` 出齐 `:9`/`:11`/`:16`/`:18` 四条主记录 —— 粒度这一项spec 与实现已对齐（其余字段仍有差距，见 §7.12.8）。
- 给的理由（写进契约）：`evidence` 是 `file:line`，**去重就是丢行号**，行号既是复现凭据，也是「同一名字两处、条件不同」的唯一区分手段。

### 2.3 旁挂 `.sha256` 不是稳定锚点 → §7.12.4 定义 canonical digest

- 实测（对 17:10 产物）：剔除 `generated_at`/`repo_head`/`data_root`/`canonical_digest` 四键、`records` 按自身规范化 JSON 全序排序后取 sha256 = `9d34fef7…ced3b`；扰动前三个字段与记录顺序**均不变**，改一条 `verdict` 变为 `faec112d…5c83b`。
- 处置：签认/比对/闸门读取一律用 canonical digest；`canonical_digest` 写入顶层但从自身计算中剔除；旁挂 `.sha256` 降级为「本次运行字节完整性」，禁止作签认对象与比对基准。
- 落点：`F-A22` 补 canonical digest；`F-A36` 为可判判据。
- 一处纠正：派单写「写进 F-A22/F-A25」，**F-A25 未动** —— F-A25 是「`verdict=unknown` 条数必须 0」，与摘要口径无关，把 digest 塞进去会让该判据有两种失败原因。digest 落在 `F-A22`（比对）+ 新增 `F-A36`（签认与读取）。

### 2.4 `path_scope` 裁定 → §7.10.3 新增 N4（含代码行）

- 代码事实（HEAD `65c6e42f`）：`custom_signals.py:646-647` 对 `timeframe != TIMEFRAME_INTRADAY` 直接 `continue`；`:717-719` 的 `_load_intraday` 只取 `intraday`；`definitions.py:234-235`、`services/resource_bundle.py:708` 同判据。
- 裁定：21 条日线信号 `path_scope=history`；1 条 monitor 规则 `intraday`（该规则**无 `timeframe` 字段**，执行入口是实时 enriched 快照：`strategy/monitor.py:659-663`、`services/quote_service.py:1359`）；`path_divergence` 全 `false`；7 条冲突源 `verdict=allow`。
- **根因已定位并写进 N4.3**：`kind` 与 `timeframe` 是两个字段 —— `kind ∈ {entry, exit, both}` 是进/出语义（`custom_signals.py:229`），`timeframe ∈ {daily, intraday}` 才是路径（`:231-233`）。实测 21 条信号 `kind` 为 `both` 20 / `exit` 1，`timeframe` **全部 `daily`**，`intraday` **0 条**。期望表的 `both` 是把 `kind:"both"` 读成了路径。
- `both` 何时才允许（N4.2）：同一 `source_path` 被 `build_expressions` 与 `build_intraday_expressions` **同时编译**、两次都返回非空表达式；当前 `both` 计数必须为 **0**（17:10 版实测 0，`history 216 / intraday 2`）。

### 2.5 `summary` 语义 → §7.12.5 分层

- 实测：17:03 版 `by_verdict {allow 63, exempt 104}` = 167 条六类源混算，读不出「闸门会拦谁」。
- 写死：`summary.live_config`（22 源，`by_verdict` 只按 primary 计）+ `summary.all_records`（全仓）+ 顶层 `by_verdict`/`by_code`/`by_namespace` 作为 **v1 兼容别名**（`F-A35` 断言等值）。
- L2 构建 allowlist **只许读 `live_config`**；`source_enabled=null` 的源不进该层（今日 `strategy_config`/`strategy_override`/`custom_factor`/`research_strategy` 全为 null，故 `live_config.sources=22`，17:10 版实测 22）。
- 17:10 版已分层但键名不同（`judged_records`/`companion_records`、`by_source_verdict`，缺 `by_path_scope`），差量记在 §7.12.8。

## 3. 对清单 v1 的向后兼容（逐条）

| # | 改动 | v1 产物影响 | 结论 |
| --- | --- | --- | --- |
| 1 | 补 `path_divergence`/`both_collision`，新增 `side`/`ref_name`/`record_kind`/`path_base`（+可选 `side_key`）| 前两项 v1 已产出；四项新增缺失 | 前两项**兼容**；四项**不兼容** → v1 限 L0/L1 |
| 2 | 粒度一出现一记录 | 53 条 ≠ 93 条 | **计数不兼容，判词语义兼容**（折叠后 verdict 逐 id 相等）|
| 3 | `canonical_digest` | v1 无字段 | **不兼容（新增必填）**；可用同一 recipe 对 v1 外部计算，故签认可先做一次；L2 起必须 `"2"` |
| 4 | `path_scope=history` | v1 已是 `history 166 / intraday 1` | **完全兼容**；撤回的是期望表口径 |
| 5 | `summary` 分层 | v1 扁平键保留为别名 | **完全兼容** |

## 4. 可复跑命令

```bash
cd /c/work/sourcecode/tick-stock-panel
F=docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md
wc -c -l "$F"
head -c 160819 "$F" | sha256sum
sha256sum "$F"
python research/arch-build-20261107/build_contract_v06.py   # 重建 + 全部断言
```

v0.5 未动（复核）：`wc -c -l` → `138729 1298`；`sha256sum` → `c7740508…0c4a21a`；`head -c 137598 | sha256sum` → `082d26fa…af7fae`。
v0.4 未动（复核）：`128007 1226`；`5bd81a74…c5531`。

## 5. 未确证（不圆）

- `F-A34`–`F-A39` **未做验收**（验收归独立审核工程师）。§7.12.8 只登记实测到的差距，不构成 PASS/FAIL。
- `93 = 79 + 14` 的 79 与 14 是逐出现**手工数**出来并与 17:10 产物的 `live_config` 对上（`records 93`、`both_collision 14`），不是跑生成器复算得出。
- N4.4 的「历史路径基础列缺失 → `materialize_factor_columns` 补同名因子」只读了代码注释与调用点（`custom_signals.py:95`、`indicators/pipeline.py:684`），**未实跑缺列帧**，也未验证补算值与基础列逐位相同。
- N4.1 中 `strategy_config`/`strategy_override` → `history` 是按「矩阵策略在历史面板上求值」推断；这两类源里 `gate_mode` 有 `production`/`research`，未逐个入口核对其求值帧。
- v1 → v2 的「折叠后 verdict 逐 id 相等」是**断言**，未对 167 条实算比较。
- 17:03 版已被覆盖，其 `canonical_digest`（`0830d913…`）不再可复算，故未写进正文，只在此登记。

## 6. 绑定声明

- `v0.4`（`FACTOR_ENGINE_CONTRACTS_20261107.md`）仍是 `F-A5` 的绑定对象（= 独立审核 16:41 判 PASS 时的对象），其四元组不因 v0.5 / v0.6 失效。
- `v0.5`（`FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md`）只追认 §7.4 允许面 + 新增 §7.11，未改判据语义；本版一字未改。
- `v0.6` 生效后：§7.10.2 字段表、§7.10.3 N4、§7.12 与 `F-A34`–`F-A39` 以 v0.6 四元组为锚；`F-A5` 与 §7.4 仍按 v0.4 判、§7.11 仍按 v0.5 判。

## 7. 与 v0.5 的关系

v0.6 = v0.5 **逐字节为底** + 6 处插入（合计 156 行）+ 3 处逐行替换 + 0 处删除；`delete = 0` 由 `difflib` 实测。v0.5 只追认允许面，v0.6 只补清单规格 —— 两版都没有改任何判据的语义。

## 8. 冻结四元组（v0.6）

| 项 | 值 |
| --- | --- |
| size | `162361` B |
| lines | `1454` |
| body-prefix | `head -c 160819` → `e3a4db17095d7e7f4461a2491f036b818225831b10e98f22242b6a3a0f2576ec` |
| full sha256 | `946a1d8675de6e4e945dc587f65b94ba0ce91922be338774b46b72022a616810` |

正文前缀口径与前几版一致：取末个「`---` 行 + 其后空行」的结束位置（即该处 + 5 字节，只含 `---` 行本身），footer 不计入正文，避免自指。本对照表自身的四元组不在此登记（自指无解），按 `wc -c -l` / `sha256sum` 现场取。

## 9. 边界

`docs/factors/**`、`docs/research/**`、`backend/**` 一字未改（只读引用）；v0.5、v0.4 未改；未 add、未提交、未部署；`gate.py` 未创建。`docs/architecture/evidence/referenced_factor_inventory.json` 是系统开发工程师 17:10:10 的产物，本轮只读、未改。
