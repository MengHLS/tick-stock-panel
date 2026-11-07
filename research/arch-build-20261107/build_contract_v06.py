# -*- coding: utf-8 -*-
"""构建 FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md = v0.5 逐字节为底 + R6 只追加。

断言驱动：任一断言失败即 raise，不落盘。
证据基准：2026-11-07 17:10:10 重生成的清单（schema_version="2"，218 条）。
"""
from __future__ import annotations

import difflib
import hashlib
import pathlib
import re

ROOT = pathlib.Path(r"C:\work\sourcecode\tick-stock-panel")
V05 = ROOT / "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md"
OUT = ROOT / "docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md"
R6 = ROOT / "docs/architecture/CONTRACT_REVISION_R6_20261107.md"

V05_SIZE, V05_LINES = 138729, 1298
V05_FULL = "c7740508c358a2c0748aa87fb14c60c8a37f6f721b3f917a7fff7b67c0c4a21a"
V05_BODY_SHA = "082d26fa15f477e4d719b9deb3272bc330b59ae94fcba4f8c0b9ed8342af7fae"
V05_BODY_BYTES = 137598

raw = V05.read_bytes()
assert len(raw) == V05_SIZE, f"v0.5 size {len(raw)}"
assert hashlib.sha256(raw).hexdigest() == V05_FULL, "v0.5 full sha"
assert hashlib.sha256(raw[:V05_BODY_BYTES]).hexdigest() == V05_BODY_SHA, "v0.5 body sha"

text = raw.decode("utf-8")
L = text.splitlines(keepends=True)
assert len(L) == V05_LINES
EOL = "\r\n"


def idx_unique(pred, name: str) -> int:
    hits = [i for i, s in enumerate(L) if pred(s)]
    assert len(hits) == 1, f"anchor {name}: {len(hits)} hits {hits[:5]}"
    return hits[0]


def blk(*lines: str) -> str:
    return "".join(s + EOL for s in lines)


i_stale = idx_unique(lambda s: s.startswith("| `stale_count` | int |"), "stale_count")
i_evid = idx_unique(lambda s: s.startswith("| `evidence` | str |"), "evidence")
i_n3 = idx_unique(lambda s: s.startswith("- **N3"), "N3")
i_fa22 = idx_unique(lambda s: s.startswith("| F-A22 |"), "F-A22")
i_schema = idx_unique(lambda s: s.startswith("| `schema_version` | str |"), "schema_version")
i_v05row = idx_unique(lambda s: s.startswith("| v0.5"), "v0.5 revision row")
i_7116 = idx_unique(lambda s: s.startswith("#### 7.11.6"), "7.11.6")

k = i_7116
while not L[k].strip() == "---":
    k += 1
    assert k < len(L), "no --- after 7.11.6"
i_sec712 = k

row_idx = [i for i, s in enumerate(L) if s.startswith("| ")]
i_sec9 = row_idx[-1] + 1
print("anchors ok; 7.12@", i_sec712 + 1, "sec9@", i_sec9 + 1)

# ---------------------------------------------------------------- 新内容
NEW_TOP_ROW = blk(
    "| `canonical_digest` | str | **v0.6 新增**。内容指纹：先剔除 `generated_at` / `repo_head` / `data_root` / `canonical_digest` 自身，再按 §7.12.4 规范化取 sha256。**签认、两份产物比对、闸门读取一律用它**；旁挂 `.sha256` 因含 `generated_at` 每次必变，只证明「本次运行字节完整」|"
)

NEW_REC_ROWS = blk(
    "| `path_divergence` | bool | **v0.6 补表**（实施已产出、v0.4/v0.5 表未列）。N3 两路径结论不一致时为 `true`；为 `true` 的条不得判 `allow` |",
    "| `both_collision` | bool | **v0.6 补表**（同上）。主记录恒 `false`，伴生记录恒 `true`（§7.12.2）|",
    "| `side` | `L` / `R` / `F` | **v0.6 新增·必填**。表达式槽位：`left` = `L`、`right` = `R`、monitor 规则的 `conditions[].field` = `F`。**只允许这三个值**；结构键路径（`scoring` / `fields.entry` / `members` / `formula` 等）不属于本字段，见 `side_key` |",
    "| `ref_name` | str | **v0.6 新增·必填**。归一化名：`ref_raw` 去掉 `field:` / `column:` / `signal:` 前缀并 trim。**allowlist 与闸门比对的键** |",
    "| `record_kind` | `primary` / `companion` | **v0.6 新增·必填**。`companion` = F-A24 的伴生记录；主/伴生共用同一 `(source_path, evidence, side, ref_name)` 元组，靠本字段区分 |",
    "| `side_key` | str / null | **v0.6 新增·可选**。引用所在的结构键路径（人读定位，如 `fields.entry`、`scoring`、`members`）。**不参与任何判据、不进 allowlist、不得用于唯一键** |",
    "| `path_base` | `repo` / `data` | **v0.6 新增·必填**。`source_path` 的基准：`repo` = 仓库根；`data` = `data_root` 下的相对路径（`data_root` 在仓库外，不能统一成仓库根；其值已含 `user_data`，故路径**不带** `user_data/` 前缀）|",
)

NEW_N4 = blk(
    "",
    "- **N4（v0.6 裁定：`path_scope` 只记真实求值路径，`both` 需编译证据）**：`path_scope` 由「该 source 实际被哪条编译入口编译」决定，不由 `kind` 或任何声明决定。代码事实（HEAD `65c6e42f`）：`custom_signals.py:646-647` 的 `build_intraday_expressions` 对 `sig.get(\"timeframe\") != TIMEFRAME_INTRADAY` 直接 `continue`；`custom_signals.py:717-719` 的 `_load_intraday` 也只取 `timeframe == intraday`；`definitions.py:234-235` 与 `services/resource_bundle.py:708` 同样按 `timeframe == TIMEFRAME_INTRADAY` 分支。故 **`timeframe=daily` 的 source 只走历史路径**（`build_expressions` / `compute_signals`），盘中单日快照根本轮不到它 —— `materialize_factor_columns` 那条「同名因子补算」对它们不可达。",
    "- **N4.1 取值判据（按 source_kind）**：`custom_signal` → 按 `timeframe`：`daily` → `history`、`intraday` → `intraday`；`monitor_rule` → `intraday`（该规则**没有 `timeframe` 字段**，执行入口是实时 enriched 快照：`strategy/monitor.py:659-663` 的 `evaluate(df…)` 与其 docstring「df: 实时 enriched 数据」，调用方 `services/quote_service.py:1359`）；`custom_factor` / `research_strategy` / `strategy_config` / `strategy_override` → `history`。",
    "- **N4.2 `both` 只在一种情形允许**：同一 `source_path` 真的被 `build_expressions` 与 `build_intraday_expressions` **同时编译**（可判：两次编译都返回含该 source 的非空表达式）。除此之外 `both` 一律不得出现；当前 **`both` 计数必须为 0**（生成器已自检「path_scope 无悬空 both」，取值集合 ⊆ `{history, intraday}`）。",
    "- **N4.3 一处已撤回的误读（事实）**：`kind` 与 `timeframe` 是不同字段 —— `kind ∈ {entry, exit, both}` 是「进/出/两者」（`custom_signals.py:229` 校验），`timeframe ∈ {daily, intraday}` 才是路径（`:231-233` 校验）。21 条活信号里 `kind` 为 `both` 20 条、`exit` 1 条，`timeframe` **全部 `daily`**，`intraday` **0 条**（本机 17:08 实测）。故 F-A24 的 7 条冲突源 `path_scope=history`、`path_divergence=false`、`verdict=allow`，与 §7.10.5「按 N1/N2 被 `FS01` 拦的 = 0 条」一致。研究侧期望表把这 7 条记成 `path_scope=both` / `path_divergence=true` / `verdict=shadow`，是把 `kind:\"both\"` 读成了路径 —— **该 7 条按本裁定改判**；期望表在 `docs/factors/evidence/`，写权归因子工程师，本契约不改其文件。",
    "- **N4.4 一处不构成 `path_divergence` 的分叉（登记）**：历史路径上基础列缺失时，`materialize_factor_columns` 会补同名因子（`custom_signals.py:95` 注释、`indicators/pipeline.py:684` 调用）。这改变的是「值由谁算」，不改变 N1 的命名空间（`field:X` 命中 `ALLOWED_FIELDS` 仍是 `column`），故**不记 `path_divergence`**；若实测同一帧上两者数值不等，属另一类问题，记入 §9。本轮未实跑。",
)

NEW_FA22 = (
    "| F-A22 | 清单幂等 | 同输入连跑两次，除 `generated_at` 外逐字节相同；且两次 `canonical_digest` 必须相等。签认与比对一律用 canonical digest —— 旁挂 `.sha256` 取全文哈希、含 `generated_at`，每次重跑必变，只证明本次运行字节完整，不得作比对基准（§7.12.4）|"
    + EOL
)

NEW_SCHEMA = (
    "| `schema_version` | str | `\"2\"`（v0.6 起）。读到 `\"1\"` 的降级读取规则见 §7.12.6；`\"1\"` 只许用于 L0/L1 |"
    + EOL
)

SEC712 = blk(
    "### 7.12 清单 v2 规格：粒度、记录身份、canonical digest、`summary` 分层与 v1 兼容（v0.6 追认）",
    "",
    "#### 7.12.1 问题（事实，2026-11-07 16:58–17:12 本机实测）",
    "",
    "盘上同时存在两份同名产物，谁也判不了谁：",
    "",
    "- **实施产物** `docs/architecture/evidence/referenced_factor_inventory.json`：17:03 版为 `schema_version=\"1\"`、`records` **167** 条，其中 `source_enabled=true` **53** 条、`both_collision=true` **8** 条、`path_divergence=true` **0** 条，`summary` 扁平 `by_verdict {allow 63, exempt 104}`。**该版已于 17:10:10 被重生成覆盖**（现状见下一条），其字节不再存在。",
    "- **实施产物现状**（17:10:10，152,826 B，全文 sha256 `2b9bb771…e8c1`）：`schema_version=\"2\"`、`records` **218** 条、`source_enabled=true` **93** 条（= 主 79 + 伴生 14）、`both_collision=true` **14** 条、`path_divergence=true` **0** 条；`summary` 已分层（`live_config` / `all_records`）。粒度这一项已按逐出现对齐（§7.12.2 的口径即由此确定），但字段与定位符仍有差距，见 §7.12.8。",
    "- **研究侧期望表** `docs/factors/evidence/referenced_factor_inventory_expected_20261107.json`（16:58，`kind=\"expected_table_not_artifact\"`）：`records` **79** 条，只覆盖 22 条活配置。",
    "",
    "17:03 那版「两份产物不可机械比对」的根因三处，均可定位到代码：",
    "",
    "1. **去重粒度**：`backend/scripts/build_referenced_factor_inventory.py` 的 `_dedup()`（`:323-328`）与 `emit()` 的 `seen` 集合（`:268-272`）按「同一 source + 同一原始串」去重。`ma_golden_20_60.json` 有两条条件（`:9` 的 `ma20`/`field:ma60`、`:16` 的 `ma20`/`field:ma60`），17:03 版只留前一对（`:9`/`:11`），后一对丢弃。",
    "2. **字面量被改写**：`_condition_refs()` 把 `field:` 前缀剥掉（`:342-343`），落成 `ref_raw=\"ma60\"`；期望表保留字面量 `field:ma60`（79 条中 38 条带前缀）。`ref_raw` 的含义两边不同 —— **17:10 版仍未改**（键里带 `field:` 的 `ref_raw` 为 **0** 条，前缀被搬进 `side` 写成 `\"R:field\"`）。",
    "3. **路径基准混用**：`source_path` 同时出现仓库内相对路径（`backend/app/strategy/seeds/…`、`research/strategy-search-20261107/…`）与 `data_root` 相对路径（`custom_signals/…`）。v0.4 写的是「相对仓库根或 data_root」，两个基准共存，消费方无法判定。",
    "",
    "后果不是好看的差别，而是**不可机械比对**：4 个冲突名在 17:03 版共 16 条记录（8 个 (源,名) 组合 × 主/伴生）、在期望侧 14 条；数字接近但定义不同，任何逐条 diff 都以失败告终，`F-A22`（幂等）与 `F-A24`（冲突必须报）的计数也不可比。",
    "",
    "#### 7.12.2 口径：一条记录 = 一个结构化引用出现处",
    "",
    "- **计数单位**：`left` 与 `right` 各算一处；monitor 规则的 `conditions[].field` 各算一处；`field:` / `column:` 前缀不改变计数（它只是字面量的一部分）。",
    "- **不合并重复名**：同一 source 内同一名字出现 n 次 = n 条**主记录**。理由：`evidence` 是 `file:line`，去重就是**丢行号**；行号既是审核复现的唯一凭据，也是「同一名字两处、条件不同」的唯一区分手段。",
    "- **伴生记录与主记录一一对应**：`both_collision` 名在第 k 个出现处 → 主记录 1 条 + 伴生 1 条。故 `records` 总数 = 主记录数 + 伴生记录数。",
    "- **唯一键**：`(source_path, evidence, side, ref_name, record_kind)` 在一个产物内必须唯一；重复即生成失败（不是警告）。",
    "- **今日实测计数**（活配置 22 源 = `custom_signal` 21 + `monitor_rule` 1）：主记录 **79**（`custom_signal` 77 + `monitor_rule` 2）+ 伴生 **14** = **93**。伴生 14 = 4 个冲突名逐出现展开：`ma20` 10 + `ma60` 2 + `boll_lower` 1 + `boll_upper` 1。17:10 产物已实测出 **93 = 79 + 14**，与本口径一致。",
    "- **三个版本的对照**：17:03 版 53 条 / 伴生 8 条（8 是「(源,名) 组合」不是「出现处」）；17:10 版 93 条 / 伴生 14 条（口径已对齐）；期望表 79 条（只数主记录）。**只有 17:10 版与期望表的差是可解释的（79 = 主记录）**。",
    "- **`evidence` 严格可解析**：`path:line`，跨行写 `path:start-end`，**不得夹注释**。反例（17:03 与 17:10 版均有）：`custom_signals/ma_golden_20_60.json:9  # N2 伴生记录: 同名基础列优先, 不参与放行` —— 定位符被注释污染，任何按 `:` 切分的消费方都会错。实测 17:10 版仍有 **14 条** `evidence` 含 `#`。",
    "- **伴生记录固定取值**：`record_kind=companion`、`both_collision=true`、`verdict=exempt`、`code=null`；**不参与** allowlist、不参与放行判定、不计入任何层的 `by_verdict`（§7.12.5）。",
    "",
    "#### 7.12.3 五个字面量字段的唯一写法",
    "",
    "| 字段 | 定义 | 反例（17:10 产物）| 正确写法 |",
    "| --- | --- | --- | --- |",
    "| `ref_raw` | 配置文件里的**字面量**，保留 `field:` / `column:` / `signal:` 前缀 | `ma60`（前缀被搬进 `side`）| `field:ma60` |",
    "| `ref_name` | 归一化名：去前缀 + trim | （缺字段）| `ma60` |",
    "| `side` | 表达式槽位，只允许 `L` / `R` / `F` | `R:field`、`scoring`、`fields.entry`、`members`、`formula`（实测 9 种取值）| `R` |",
    "| `side_key` | 结构键路径（人读定位，可选，不判）| （现占用 `side`）| `fields.entry` |",
    "| `path_base` | 路径基准 | （缺字段，路径混用）| `data` + `custom_signals/ma_golden_20_60.json` |",
    "",
    "monitor 规则的 `side`：引用写在 `conditions[].field`（`monitor_rules/lot_1a1aa285978_521c_p.json:11-14` 两条 `close`），按 `F` 计，仍**逐条** —— 两条 `close` = 2 条记录，与实测 `monitor_rule` 主记录 = 2、`path_scope=intraday` 记录 = 2 一致。",
    "",
    "**为什么把「槽位」与「结构键」拆成两个字段**：17:10 版把两者塞进一个 `side`，实测 9 种取值 —— `L` / `R:field` 是槽位+前缀，`scoring` / `formula` / `fields.entry` / `fields.score` / `fields.exit` / `members` / `field` 是结构键。一个字段两种维度，就没法机械判「左值还是右值」，也没法做唯一键。拆开后：`side` 三值可判、`side_key` 只做人读。",
    "",
    "#### 7.12.4 canonical digest（唯一签认对象，可复算）",
    "",
    "定义（缺一项都不是同一口径）：",
    "",
    "1. 取产物 JSON 对象，**剔除** `generated_at`、`repo_head`、`data_root`、`canonical_digest` 四个键（前三个与内容无关或与机器相关，第四个是自指）。",
    "2. `records` 按每条记录自身的规范化 JSON 排序（`rk(x) = json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(\",\", \":\"))`），得到与输入顺序无关的全序。",
    "3. 余下对象整体 `json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(\",\", \":\"))`，UTF-8 编码后取 sha256。",
    "",
    "复算命令（逐字执行；`ensure_ascii=True` 或默认分隔符会得到另一个稳定值，不是同一口径）：",
    "",
    "```bash",
    "python - <<'PY'",
    "import json, hashlib",
    "p = 'docs/architecture/evidence/referenced_factor_inventory.json'",
    "DROP = {'generated_at', 'repo_head', 'data_root', 'canonical_digest'}",
    "rk = lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'))",
    "d = json.load(open(p, encoding='utf-8'))",
    "q = {k: v for k, v in d.items() if k not in DROP}",
    "q['records'] = sorted(q.get('records', []), key=rk)",
    "blob = json.dumps(q, ensure_ascii=False, sort_keys=True, separators=(',', ':'))",
    "print(hashlib.sha256(blob.encode('utf-8')).hexdigest())",
    "PY",
    "```",
    "",
    "稳定性实测（对 **17:10:10 产物**跑上式，四类扰动）：",
    "",
    "| 扰动 | canonical digest |",
    "| --- | --- |",
    "| 原样 | `9d34fef766da94f6a87ef5ed0b40863209f013a1a0390c47491e6766dc1ced3b` |",
    "| 改 `generated_at` / `repo_head` / `data_root` | **不变** |",
    "| `records` 整体倒序 | **不变** |",
    "| `records` 随机重排（`random.seed(7)`）| **不变** |",
    "| 改任意一条 `verdict`（`allow`→`block`）| `faec112db19ffc9e7383f4fda912f46eccd579463f4f7275f5c5df9be2f6c83b` |",
    "",
    "配套三条硬规则：",
    "",
    "- `canonical_digest` **写入产物顶层**，但计算时剔除自身（否则自指无解）；校验方重算后与落盘值比对，不等即 fail-closed。",
    "- **旁挂 `.sha256` 降级为「本次运行字节完整性」**：它取全文哈希，含 `generated_at`，重跑一次必变（开发经理实测重跑得到 `6f528bcb…`，按原字节还原后侧车须手写回 `3c9a186a…` 才与文件一致；17:10 版侧车与字节一致，为 `2b9bb771…`）。**不得作签认对象、不得作 `F-A22` 比对基准、闸门不得读它**。",
    "- 签认对象 = `canonical_digest` + `schema_version` + `scanned_sources` 三元组；因子工程师签这三个值即可，不必签文件字节。",
    "",
    "#### 7.12.5 `summary` 必须分层",
    "",
    "v0.4 的 `summary` 扁平（`by_verdict` / `by_code` / `by_namespace`），覆盖**全仓六类源**。17:03 版实测 `by_verdict {allow 63, exempt 104}` = **167 条混算**，读者从中读不出「闸门会拦谁」—— L2 要的是活配置的判词。",
    "",
    "规定结构（两层 + v1 兼容别名）：",
    "",
    "| 层 | 键 | 含义 |",
    "| --- | --- | --- |",
    "| `summary.live_config` | `sources` / `unique_sources` / `records` / `by_verdict` / `by_record_kind` / `by_namespace` / `by_class` / `by_path_scope` / `by_verdict_sources` | 只统计 `source_enabled=true` 的源；`by_verdict` **只按 `record_kind=primary` 计数**；`by_verdict_sources` = 每源取最坏 verdict（`block` > `shadow` > `allow`）|",
    "| `summary.all_records` | `records` / `by_verdict` / `by_code` / `by_namespace` / `by_class` / `by_path_scope` / `by_record_kind` | 全仓六类源；`by_verdict` 同样只按 primary 计数，伴生只计入 `by_record_kind.companion` |",
    "| `summary.by_verdict` / `by_code` / `by_namespace`（顶层）| 同 v1 | **v1 兼容别名**，值与 `summary.all_records` 对应项相等（`F-A35` 断言）|",
    "",
    "三条使用规则：",
    "",
    "- **L2 构建 allowlist 只许读 `summary.live_config`**，并按逐记录条件 `source_enabled=true AND record_kind=primary` 复算；读 `all_records` 或顶层别名建名单 = 违规（会混进研究侧与种子策略的条目）。",
    "- `source_enabled` 为 `null` 的源（该源无顶层开关字段）**不进** `live_config`，只在 `all_records`。今天六类源里 `strategy_config` / `strategy_override` / `custom_factor` / `research_strategy` 全为 `null`，故 `live_config.sources = 22`（17:10 版实测 22，一致）。",
    "- 伴生记录在任何层的 `by_verdict` 里都不出现，只在 `by_record_kind.companion` 计数 —— 这是「伴生不参与放行」的机械保证。",
    "",
    "#### 7.12.6 对清单 v1 是否向后兼容（逐条，五项）",
    "",
    "| # | v0.6 的改动 | 对 `schema_version=\"1\"` 产物 | 结论 |",
    "| --- | --- | --- | --- |",
    "| 1 | 字段表补 `path_divergence` / `both_collision`，新增 `side` / `ref_name` / `record_kind` / `path_base`（+ 可选 `side_key`）| 前两项 v1 **已实际产出**（实施超表），契约只是追平，读取无影响；`side` / `ref_name` / `record_kind` / `path_base` v1 均缺失 | **格式兼容（前两项）/ 不兼容（四项新增）**：v1 只能在 L0/L1 用，L2 起必须 `\"2\"` |",
    "| 2 | 粒度改为一出现一记录 | v1 是「(源,名) 去重」，同一 22 源 53 条 ≠ 93 条 | **计数不兼容，判词语义兼容**：v1 按 `(source_id, ref_name)` 折叠后 `verdict` 与 v2 逐 id 相等（可机械验证）。不翻转任何放行结论，只影响可追溯性 |",
    "| 3 | 新增 `canonical_digest` | v1 无此字段 | **不兼容（新增必填）**。迁移不是重算：v1 可用同一 recipe 从外部算出，故签认可对 v1 先做一次；闸门读顶层字段时读不到 → L2 起必须 `\"2\"` |",
    "| 4 | `path_scope` 裁定为 `history`（N4）| v1 产物已是 `history 166 / intraday 1`（17:10 版 `216 / 2`），无 `both` | **完全兼容（格式与取值）**。要撤回的是研究侧期望表的 `both`/`shadow`，那是口径文件不是产物（N4.3）|",
    "| 5 | `summary` 分层 | v1 扁平键仍在，语义 = `all_records` | **完全兼容**：顶层三键保留为别名（`F-A35` 断言等值），新增两层不删旧键 |",
    "",
    "一句话：**格式上 v1 缺 `side` / `ref_name` / `record_kind` / `path_base` / `canonical_digest` 与分层 `summary`；语义上一条结论都不翻转。** 重生成一次即可，不需要改判据、不需要重跑任何数值。",
    "",
    "#### 7.12.7 判据（续 §7.10.6 / §7.11.5 编号，接 `F-A33`）",
    "",
    "| # | 判据 | 度量 |",
    "| --- | --- | --- |",
    "| F-A34 | 粒度与唯一键 | `ma_golden_20_60.json` 必须出 **4 条主记录**（`ma20`@`:9` `L`、`field:ma60`@`:11` `R`、`ma20`@`:16` `L`、`field:ma60`@`:18` `R`）；全产物无 `(source_path, evidence, side, ref_name, record_kind)` 重复；活配置 `records = 93 = 79 主 + 14 伴生` |",
    "| F-A35 | `summary` 分层自洽 | `sum(all_records.by_verdict) == all_records.by_record_kind.primary`；`live_config` 同式；`summary.by_verdict == all_records.by_verdict`（别名等值）；`live_config.sources == 22`。反例必须失败：把伴生计入任一层 `by_verdict` 时不通过 |",
    "| F-A36 | canonical digest 可复算且稳定 | 按 §7.12.4 代码复算 == 落盘 `canonical_digest`；扰动 `generated_at`/`repo_head`/`data_root` 与记录顺序后不变；改任一 `verdict` 必变；把旁挂 `.sha256` 当签认对象时不通过 |",
    "| F-A37 | 字面量与定位符 | `ref_raw` 保留前缀（`:11` 必须 `field:ma60`）、`ref_name=ma60`；`side ∈ {L,R,F}` 且必填；`evidence` 可按 `path:line` 解析、不含 `#`；结构键只许进 `side_key` |",
    "| F-A38 | `path_scope` 与 `both` | 取值集合 ⊆ `{history, intraday}`（今日 `both` 计数 **0**）；21 条日线信号全 `history`、1 条 monitor 规则 `intraday`；`path_divergence=true` 计数 **0**；7 条冲突源 `verdict=allow` |",
    "| F-A39 | v1 兼容与降级边界 | `schema_version=\"1\"`：可读（`ref_name:=ref_raw`、`side:=null`、`record_kind:=primary`）、只许 L0/L1；读 `\"1\"` 却要求 L2/L3 → 拒绝启动。`\"2\"` 且缺任一新增字段 → 拒绝加载 |",
    "",
    "#### 7.12.8 对 17:10 产物的实测差距（只报事实，不判验收）",
    "",
    "实施侧 17:10:10 已重生成，六条判据的现状实测如下。**本表不是验收结论**（验收归独立审核工程师），只标出还差什么：",
    "",
    "| 判据 | 17:10 产物实测 | 差什么 |",
    "| --- | --- | --- |",
    "| F-A34 粒度与唯一键 | 218 条；活配置 93 = 79 主 + 14 伴生；`ma_golden_20_60` 4 主 + 4 伴生（`:9`/`:11`/`:16`/`:18`）；`(source_path, evidence, side, ref_raw)` 无重复（0 组）| **字段级已达标**；缺 `ref_name` / `record_kind`，故唯一键与 `by_record_kind` 只能用代理量 |",
    "| F-A35 summary 分层 | `live_config.by_verdict {allow 79}`（只含主记录）；`all_records.by_verdict {allow 97, exempt 107}`；`live_config.sources 22` | **大体达标**；键名不同：用 `judged_records` / `companion_records` 而非 `by_record_kind`，用 `by_source_verdict` 而非 `by_verdict_sources`，且缺 `by_path_scope`；顶层 v1 别名三键缺失 |",
    "| F-A36 canonical digest | 无 `canonical_digest` 字段；旁挂 `.sha256` = 全文 `2b9bb771…` | **未达标**：须新增字段（值可按 §7.12.4 外部算出为 `9d34fef7…`）|",
    "| F-A37 字面量与定位符 | `ref_raw` 带前缀 **0** 条；`side` 有 **9** 种取值（`L`/`R:field`/`scoring`/`formula`/`fields.entry`/`fields.score`/`fields.exit`/`members`/`field`）；`evidence` 含 `#` **14** 条 | **未达标**：前缀须回 `ref_raw`、`side` 须收窄为三值、结构键移 `side_key`、伴生 `evidence` 去注释 |",
    "| F-A38 path_scope 与 both | `history 216` / `intraday 2`；`both` 0；`path_divergence` 0；活配置 `verdict` 全 `allow`（79）| **已达标**（实测）|",
    "| F-A39 v1 兼容 | 产物已是 `\"2\"` | **未验证**：`\"1\"` 的降级读法与「读 `\"1\"` 却要求 L2/L3 拒绝启动」无实现 |",
    "",
    "本轮只给规格。重生成、字段补齐、`summary` 键名、`canonical_digest` = 系统开发工程师；期望表 `both`/`shadow` 改判与 `side` 补列 = 因子工程师（`docs/factors/` 写权归其）；契约文本 = 本文件。`gate.py` 未实现，`F-A34`–`F-A39` 除上表实测项外**均未实跑**。",
    "",
)

NEW_V06_ROW = blk(
    "| v0.6（追认） | 2026-11-07 | **R6（只追加，不改 v0.5 正文语义）**：①§7.10.2 字段表补 `path_divergence`/`both_collision`（实施已产出、表未列），新增 `side`/`ref_name`/`record_kind`/`path_base` 与可选 `side_key`，顶层加 `canonical_digest`，`schema_version` 升 `\"2\"`；②§7.10.3 新增 **N4**：`path_scope` 只记真实求值路径（`custom_signals.py:646-647`），`both` 需两入口同时编译的证据，撤回期望表把 `kind:\"both\"` 读成路径的 7 条；③新增 **§7.12** 清单 v2 规格（一出现一记录、伴生一一对应、槽位与结构键拆分、canonical digest、`summary` 分层、v1 兼容逐条、17:10 产物实测差距）+ `F-A34`–`F-A39`。**v0.4 仍为 `F-A5` 绑定对象；v0.5 不改** | 开发经理 v0.5 验收后派单（五条本机实测）+ 架构师本机复算（16:58–17:15）|"
)

NEW_SEC9 = blk(
    "| **清单 v2（v0.6 追认）** | 规格见 §7.12 + §7.10.2 字段表 + §7.10.3 N4 + `F-A34`–`F-A39`。盘上产物已由系统开发工程师于 **17:10:10 重生成**（`schema_version=\"2\"`、218 条、活配置 93 = 79 + 14、`summary` 已分层），粒度与 `path_scope` 两项实测达标；仍缺 `ref_name`/`record_kind`/`path_base`/`canonical_digest`，`side` 仍是 9 种取值的结构键、`ref_raw` 前缀被剥、伴生 `evidence` 夹注释（§7.12.8）。**L2 起不得读 v1** |",
    "| **研究侧期望表 7 条 `both`（v0.6 改判）** | 按 N4.3：7 条冲突源 `path_scope=history`、`path_divergence=false`、`verdict=allow`。期望表在 `docs/factors/evidence/`，写权归因子工程师；本契约只给判据、不改其文件 |",
)

# ---------------------------------------------------------------- 组装
out: list[str] = []
i = 0
while i < len(L):
    if i == i_v05row:
        out.extend([L[i], NEW_V06_ROW])
    elif i == i_schema:
        out.append(NEW_SCHEMA)
    elif i == i_stale:
        out.extend([L[i], NEW_TOP_ROW])
    elif i == i_evid:
        out.extend([L[i], NEW_REC_ROWS])
    elif i == i_n3:
        out.extend([L[i], NEW_N4])
    elif i == i_fa22:
        out.append(NEW_FA22)
    elif i == i_sec712:
        out.extend([SEC712, L[i]])
    elif i == i_sec9:
        out.extend([NEW_SEC9, L[i]])
    elif i == len(L) - 1:
        out.append("@@FOOTER@@\n")
    else:
        out.append(L[i])
    i += 1

body = "".join(out)
assert "@@FOOTER@@" in body
body = body.replace("@@FOOTER@@\n", "")

body_raw = body.encode("utf-8")
cut = body_raw.rfind(b"---\r\n\r\n") + 5
assert cut > 0
body_prefix = body_raw[:cut]
assert body_prefix.endswith(b"---\r\n")
tail_raw = body_raw[cut:]
assert tail_raw == b"\r\n", repr(tail_raw)
body_sha = hashlib.sha256(body_prefix).hexdigest()
total_lines = body_prefix.decode("utf-8").count("\r\n") + 2

footer = (
    "本文件正文 sha256：`" + body_sha + "`（校验：`head -c " + str(cut)
    + " \"docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.6.md\" | sha256sum`）· 正文 `"
    + str(cut) + " B` · 行数 `" + str(total_lines) + "` · 版本 **v0.6（2026-11-07 追认，未冻结）**· 冻结四元组（size / lines / body-prefix / full sha）见 `docs/architecture/CONTRACT_REVISION_R6_20261107.md` §8（不写进正文，避免自指）· 生成 2026-11-07 v0.6 = v0.5 逐字节为底 + R6 只追加：§7.10.2 字段表 +8 行（`path_divergence`/`both_collision` 补表，`side`/`ref_name`/`record_kind`/`path_base` 新增，`side_key` 可选，`canonical_digest` 顶层）/ §7.10.3 新增 N4（`path_scope` 只记真实路径，`both` 需编译证据）/ 新增 §7.12（粒度、记录身份、槽位与结构键拆分、canonical digest、`summary` 分层、v1 兼容、17:10 产物实测差距）+ `F-A34`–`F-A39` / `F-A22` 补 canonical digest / §9 增补两行 · **v0.4 = `FACTOR_ENGINE_CONTRACTS_20261107.md`（128,007 B / 1,226 行 / 正文 `head -c 127043` → `71708877…d16bc` / 全文 `5bd81a74…c5531`）仍为 `F-A5` 的绑定对象；v0.5 = `FACTOR_ENGINE_CONTRACTS_20261107_v0.5.md`（138,729 B / 1,298 行 / 正文 `head -c 137598` → `082d26fa…af7fae` / 全文 `c7740508…0c4a21a`）一字未改；v0.6 只追加，不改判据语义** · v0.3 冻结态（89,833 B / 914 行 / 全文 `5eb97724…565903`）逐字节归档于 `docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md`"
    + EOL
)
final_raw = body_prefix + tail_raw + footer.encode("utf-8")
full_sha = hashlib.sha256(final_raw).hexdigest()
size = len(final_raw)
lines = final_raw.decode("utf-8").count("\r\n")

# ---------------------------------------------------------------- 校验
new_txt = final_raw.decode("utf-8")
sm = difflib.SequenceMatcher(None, L, new_txt.splitlines(keepends=True), autojunk=False)
reps, ins, dele = [], 0, 0
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag == "replace":
        reps.append((i1 + 1, i2 - i1, j2 - j1))
    elif tag == "insert":
        ins += j2 - j1
    elif tag == "delete":
        dele += i2 - i1
print("opcodes: replace", reps, "| inserted", ins, "| deleted", dele)
assert dele == 0, f"deleted {dele} lines"
assert len(reps) == 3, f"expected 3 replaced lines, got {len(reps)}"
for (ln, ni, nj) in reps:
    assert ni == 1 and nj == 1, f"replace at line {ln}: {ni}->{nj}"


def sections(t: str) -> dict[str, str]:
    outd: dict[str, list[str]] = {}
    cur = None
    for s in t.splitlines(keepends=True):
        if re.match(r"^(#{2,4}) .+?\r?$", s):
            cur = s.strip()
            outd[cur] = []
        if cur is not None:
            outd[cur].append(s)
    return {k: "".join(v) for k, v in outd.items()}


o_sec, n_sec = sections(text), sections(new_txt)
for key in list(o_sec):
    if key.startswith("### 7.1 ") or key.startswith("### 7.9 ") or key.startswith("### 7.11 ") or key.startswith("## 8. "):
        assert o_sec[key] == n_sec[key], f"section changed: {key}"
        print("  unchanged", key[:26], len(o_sec[key]), hashlib.sha256(o_sec[key].encode()).hexdigest()[:16])

OUT.write_bytes(final_raw)
print("WROTE", OUT.name, size, "B /", lines, "lines / body", cut, body_sha[:16], "/ full", full_sha[:16])

r6 = f"""# 契约 v0.5 → v0.6 修订对照（R6，只追加）

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

机械验证（本机，`difflib.SequenceMatcher` 对 v0.5 与新文件逐行比对）：**replace 3 处（各 1 行）、insert {ins} 行、delete 0 行**。

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
- **根因已定位并写进 N4.3**：`kind` 与 `timeframe` 是两个字段 —— `kind ∈ {{entry, exit, both}}` 是进/出语义（`custom_signals.py:229`），`timeframe ∈ {{daily, intraday}}` 才是路径（`:231-233`）。实测 21 条信号 `kind` 为 `both` 20 / `exit` 1，`timeframe` **全部 `daily`**，`intraday` **0 条**。期望表的 `both` 是把 `kind:"both"` 读成了路径。
- `both` 何时才允许（N4.2）：同一 `source_path` 被 `build_expressions` 与 `build_intraday_expressions` **同时编译**、两次都返回非空表达式；当前 `both` 计数必须为 **0**（17:10 版实测 0，`history 216 / intraday 2`）。

### 2.5 `summary` 语义 → §7.12.5 分层

- 实测：17:03 版 `by_verdict {{allow 63, exempt 104}}` = 167 条六类源混算，读不出「闸门会拦谁」。
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
head -c {cut} "$F" | sha256sum
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

v0.6 = v0.5 **逐字节为底** + 6 处插入（合计 {ins} 行）+ 3 处逐行替换 + 0 处删除；`delete = 0` 由 `difflib` 实测。v0.5 只追认允许面，v0.6 只补清单规格 —— 两版都没有改任何判据的语义。

## 8. 冻结四元组（v0.6）

| 项 | 值 |
| --- | --- |
| size | `{size}` B |
| lines | `{lines}` |
| body-prefix | `head -c {cut}` → `{body_sha}` |
| full sha256 | `{full_sha}` |

正文前缀口径与前几版一致：取末个「`---` 行 + 其后空行」的结束位置（即该处 + 5 字节，只含 `---` 行本身），footer 不计入正文，避免自指。本对照表自身的四元组不在此登记（自指无解），按 `wc -c -l` / `sha256sum` 现场取。

## 9. 边界

`docs/factors/**`、`docs/research/**`、`backend/**` 一字未改（只读引用）；v0.5、v0.4 未改；未 add、未提交、未部署；`gate.py` 未创建。`docs/architecture/evidence/referenced_factor_inventory.json` 是系统开发工程师 17:10:10 的产物，本轮只读、未改。
"""

R6.write_text(r6, encoding="utf-8", newline="\n")
print("WROTE", R6.name, len(r6.encode("utf-8")), "bytes")
