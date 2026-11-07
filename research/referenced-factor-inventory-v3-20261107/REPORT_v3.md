# 清单 v3：按契约 v0.6 §7.10.2 / §7.12 重生成（摘要可复算）

时间：2026-11-07 17:20–17:30（Asia/Shanghai）
角色：系统开发工程师（生成方；签认归因子工程师，验收归独立审核工程师）
范围：只改生成器 + 重生成产物。`backend/**` 源码零改动、活配置零改动、未提交、未部署、未重启。

---

## 0. 一句话结论

P1/P2/P3 三组问题全部落代码：`canonical_digest` 逐字按 §7.12.4 实现并可被契约里那段 bash 原样复算；
五个字面量字段（`ref_raw`/`ref_name`/`side`/`side_key`/`path_base`）与 `record_kind` 全部落位；
`summary` 分层且任一层 `by_verdict` 只覆盖 primary。**37 项自检 0 FAIL、EXIT=0**；
两次生成除 `generated_at` 外逐字节相同、digest 相同；`git status --porcelain` 前后逐行相同。

| # | 交付物 | 事实 |
|---|---|---|
| 1 | `backend/scripts/build_referenced_factor_inventory.py` | **60,990 B / 1,219 行**；`ruff` All checks passed；sha256 `582c9287fee90dbc0b3ced482d9ef04a8017304d059034d4028fc33919db1765` |
| 2 | `docs/architecture/evidence/referenced_factor_inventory.json` | **184,643 B / 218 记录**；sha256 `c5d8d22d36c994c018f9a46c9810e481bd9ac9a042ed54ac5fd05ad78488126f` |
| 3 | 同名 `.sha256` | `sha256sum -c` → `OK`（在该目录下执行） |
| ★ | `canonical_digest` | **`184e4728810248e7ede9247685705bca6b1fd614333d4ec67e668689a869e1b1`** |

---

## 1. P1：摘要不可复算 —— 真实原因（不圆）

我查到的不是「口径理解分歧」，是**四个相互独立的偏差**，其中任一个单独存在都会让值不同。用备份的 v2 生成器重放出 17:10 那版产物（`v2_replay.json`），逐组复算：

| 复算方式（作用在 v2 的同一份字节上） | 结果 |
|---|---|
| **v2 的写法**：剔 2 键（`generated_at`,`canonical_sha256`）+ `indent=2` + 末尾换行 + 不排 records | **`16fb5c30…0db07`**（= 我落盘的那个，逐位复现） |
| **§7.12.4 写法**：剔 4 键 + `sort_keys` 紧凑 + records 全序 | **`9d34fef7…1ced3b`**（= 你与架构师算的那个，逐位一致） |
| 剔 4 键 + 紧凑 + 排 records，但漏剔我自己的字段名 | `e6ef8e6f…c9a963` |
| 剔 4 键 + 紧凑，但不排 records | `c7efe649…18914e` |
| 剔 4 键 + 排 records，但 `indent=2` | `a3c67058…e489dfd` |

四处偏差逐条：

1. **剔除键集**：我只剔 `generated_at` 与自身，没剔 `repo_head` / `data_root`（契约要求剔）。
2. **序列化方式**：我用 `json.dumps(..., indent=2)` 再拼一个 `\n`（人类可读的产物格式），契约要 `separators=(',',':')` 的**紧凑**串。这两个串的 sha256 必然不同。
3. **records 未做全序**：契约要求 `records` 按每条记录自身的规范化 JSON 排序（与输入顺序无关），我直接按落盘顺序入串。
4. **字段名自指没被剔**：我把它叫 `canonical_sha256`，而契约的 DROP 只剔 `canonical_digest`。即便按 §7.12.4 剔 4 键，我那个 64 位十六进制字段仍留在串里 → 仍不等于 `9d34fef7`。

所以你用 6 种剔除键集 × 3 种排序 × 2 种 `ensure_ascii` 共 18 组都复现不出来：**没有一组同时改了「紧凑序列化 + 末尾无换行」**——那是我值差异的最大项，且它不在你的三个变量里。这是我的实现偏差，不是契约歧义。

**一处更正我上一轮的说法**：我上一条消息里说「契约 §7.12.4 里 `sort_keys` 处是脱敏占位」——**这是错的**。契约文件里 4 处 `sort_keys` 完好（我按字节数过：`sort_keys` 出现 4 次、`«` 出现 0 次），`«redacted 4 chars»` 是我这边命令输出对 `sort_keys=True` 这个串的遮蔽，我照着被遮蔽的回显写进了判断。契约文本没有缺陷，不用修契约。

## 2. P1 验收：§7.12.4 那段代码原样执行

从契约文件里**逐字抽出**该代码块（`research/referenced-factor-inventory-v3-20261107/digest_7_12_4.sh`，11 行，未改一字），执行：

```bash
$ bash research/referenced-factor-inventory-v3-20261107/digest_7_12_4.sh
184e4728810248e7ede9247685705bca6b1fd614333d4ec67e668689a869e1b1
$ echo $?
0
```

落盘值：`184e4728810248e7ede9247685705bca6b1fd614333d4ec67e668689a869e1b1` → **逐位相同**。

另在生成器内放了**第二份独立实现**（`_independent_digest()`，逐字照抄该段），自检里交叉比对，避免「自己验自己」。

---

## 3. P2：五个字面量字段 + `record_kind`

`records[]` 现在 23 个字段（v0.6 表内 22 + `note`），顺序固定，越界 0 条。`ma_golden_20_60` 的 8 条（4 主 + 4 伴生）实物：

| record_kind | side | side_key | evidence | ref_raw | ref_name | namespace | class | verdict |
|---|---|---|---|---|---|---|---|---|
| primary | L | – | `custom_signals/ma_golden_20_60.json:9` | `ma20` | `ma20` | column | base | allow |
| companion | L | – | `custom_signals/ma_golden_20_60.json:9` | `ma20` | `ma20` | factor | custom_dsl | exempt |
| primary | R | – | `…:11` | **`field:ma60`** | `ma60` | column | base | allow |
| companion | R | – | `…:11` | `field:ma60` | `ma60` | factor | custom_dsl | exempt |
| primary | L | – | `…:16` | `ma20` | `ma20` | column | base | allow |
| companion | L | – | `…:16` | `ma20` | `ma20` | factor | custom_dsl | exempt |
| primary | R | – | `…:18` | **`field:ma60`** | `ma60` | column | base | allow |
| companion | R | – | `…:18` | `field:ma60` | `ma60` | factor | custom_dsl | exempt |

逐项计数：

- `ref_raw` 带前缀 **48 条**（全部 `field:`；v2 是 **0** 条），`ref_name` 去前缀错 **0** 条。
- `side` 取值 **{L: 168, R: 48, F: 2}** —— 只有三值（v2 有 9 种）。
- `side_key`：`null` 95 / `scoring` 78 / `formula` 16 / `members` 4 / `fields.entry` 10 / `fields.score` 9 / `fields.exit` 6。
- `evidence` 含 `#` **0 条**（v2 是 14 条）；注释移到 `note`，14 条伴生各一条，主记录恒 `null`。
- `record_kind`：`primary` 204 / `companion` 14（v2 是 218 条全 null）。
- `path_base`：`data` 117 / `repo` 101；`data` 侧不带 `user_data/` 前缀。
- 唯一键 `(source_path, evidence, side, ref_name, record_kind)`：218 条 / 去重 218 → **0 组重复**。

**一处契约留白，我按一句话默认并登记**：`side` 只能取 `L/R/F`，而 `scoring` / `formula` / `members` / `fields.<名>` 这类结构键引用没有表达式槽位。我把它们的 `side` 统一记 **`L`（被引用的值槽）**，结构路径进 `side_key`。改动面是 `emit()` 调用处的常量，架构师若给第四值或指定别的映射，改 6 处即可再生成，判定与计数不变（`side` 不参与分类、不参与 `verdict`、不参与 allowlist）。

---

## 4. P3：`summary` 分层（两层各自数值）

```json
"summary": {
  "live_config": {
    "sources": 22, "records": 93,
    "by_record_kind": {"primary": 79, "companion": 14},
    "by_verdict": {"allow": 79},                       // 只覆盖 primary
    "by_code": {"null": 79},
    "by_namespace": {"column": 79},
    "by_class": {"base": 79},
    "by_path_scope": {"history": 77, "intraday": 2},
    "by_verdict_sources": {"allow": 22}
  },
  "all_records": {
    "sources": 73, "records": 218,
    "by_record_kind": {"primary": 204, "companion": 14},
    "by_verdict": {"allow": 97, "exempt": 107},        // 只覆盖 primary
    "by_code": {"null": 204},
    "by_namespace": {"column": 97, "factor": 107},
    "by_class": {"base": 184, "custom_dsl": 4, "virtual": 16},
    "by_path_scope": {"history": 202, "intraday": 2},
    "by_source_kind": {"custom_factor": 20, "custom_signal": 91, "monitor_rule": 2,
                        "research_strategy": 25, "strategy_config": 76, "strategy_override": 4},
    "by_verdict_sources": {"allow": 37, "exempt": 36}
  },
  "by_verdict": {"allow": 97, "exempt": 107},          // v1 兼容别名 == all_records.by_verdict
  "by_code": {"null": 204},
  "by_namespace": {"column": 97, "factor": 107}
}
```

自洽：`sum(all_records.by_verdict) = 204 = by_record_kind.primary`；`sum(live_config.by_verdict) = 79 = 79`；
`summary.by_verdict == all_records.by_verdict`；`live_config.sources = 22`。
**反例已验证有区分力**：把 14 条伴生计入 `by_verdict` → 求和 218 ≠ 204，自检该项 FAIL。

## 5. 两张计数表

**源级**：`live_config` 22 源（`custom_signal` 21 + `monitor_rule` 1）→ 源级 `allow 22 / shadow 0 / block 0`。
`all_records` 73 源 → 源级 `allow 37 / exempt 36`。

**记录级（218 条）**：活配置 93 = 79 主 + 14 伴生；其余 125 条来自 5 类非活配置源（`strategy_config` 76、`research_strategy` 25、`custom_factor` 20、`strategy_override` 4，`monitor_rule` 2 已计入活配置）。

| 源类 | 记录 | 主 | 伴生 |
|---|---|---|---|
| custom_signal | 91 | 77 | 14 |
| monitor_rule | 2 | 2 | 0 |
| strategy_override | 4 | 4 | 0 |
| custom_factor | 20 | 20 | 0 |
| strategy_config | 76 | 76 | 0 |
| research_strategy | 25 | 25 | 0 |
| **合计** | **218** | **204** | **14** |

---

## 6. 六条判据逐条（+ F-A22 / F-A24 / FS01）

`python backend/scripts/build_referenced_factor_inventory.py` → **37 PASS / 0 FAIL / EXIT=0**。

| 判据 | 自检项 | 实测 |
|---|---|---|
| F-A34 粒度与唯一键 | 唯一键 / 93=79+14 / `ma_golden_20_60` | 218 条 0 重复；`ma_golden_20_60` 主 `(9,L,ma20)(11,R,field:ma60)(16,L,ma20)(18,R,field:ma60)` + 4 伴生 |
| F-A35 summary 分层 | 层内求和=primary / v1 别名等值 / live 22 源 / 反例可失败 | 204=204、79=79；别名 `{allow 97, exempt 107}` 等值；live 22；反例 218≠204 触发 |
| F-A36 digest | 外部复算 / 扰动不变 / 改 verdict 必变 | `184e4728…` 复算一致；改 3 键 + records 倒序不变；改 1 条 verdict 变 |
| F-A37 字面量与定位符 | 前缀 / side 三值 / evidence / 结构键 | 48 条带 `field:`、去前缀错 0；`{L,R,F}`；含 `#` 0 条；`side_key` 6 种取值且不在 `side` 里 |
| F-A38 path_scope 与 both | 取值域 / 21+1 / divergence / 7 源 | `{history, intraday}`、both 0；日线 21 源全 history、monitor 2 条全 intraday；`path_divergence` 0；7 条冲突源全 allow |
| F-A39 v1 兼容与降级 | v1 可读 / v1 不许 L2 / v2 缺字段拒绝 | `ref_name:=ref_raw`、`side:=null`、`record_kind:="primary"`；读 `"1"` 要求 L2 → `InventoryError`；`"2"` 缺字段 → 拒绝加载 |
| F-A22 幂等 | 字节 / digest | 两次生成（17:27:33 / 17:27:43）除 `generated_at` 逐字节相同，digest 同为 `184e4728…` |
| F-A24 冲突 | 4 名 column + 14 伴生 + 伴生形态 | column 主 14 / 伴生 14；伴生全 `class=custom_dsl` 且有 `resolved_id`、`note` 非空 |
| FS01 实拦 | 记录侧 / 通道反向 | 记录里 `code=FS01` **0 条**；反向：15 个 draft 定义逐个试探 → **15/15 block+FS01**；`ma20` 按 `both` → divergence=True、block |

**未被改动、按你实测保持的六条**：活配置 93 = 79 主 + 14 伴生；79 主全 `verdict=allow` / `namespace=column`；14 伴生全 `exempt`；22 源；FS01 实拦 0；`path_divergence` 全 false。

**额外一条证据（F-A36 的强形态）**：17:27 那次我把 `_sort_key` 改成「主记录排在伴生之前」，`records` 落盘顺序整体变了、`generated_at` 也变了，而 **digest 仍是 `184e4728…`** —— 说明它确实与记录顺序、与运行时刻无关。

---

## 7. 「只多了这三样」+ `backend/**` 零改动

- `git status --porcelain` 生成前后 **逐行相同**（`diff` 空，文件 `git_status_before_v3.txt` / `git_status_after_v3.txt`）。
- `find backend -name "*.py" -newermt "2026-11-07 17:20"` → **单命中新脚本** `backend/scripts/build_referenced_factor_inventory.py`（17:27）。
- `api/factors.py`(16:33:57, 24,629 B) / `factors/store.py`(16:33:52, 19,502 B) mtime 未变 —— F-A5 批次留下的改动，本批未碰。
- 未提交、未部署、未重启。

## 8. 两处口径事实（我核到的，与你派单文字不一致，按盘上事实报）

1. **`all_records.by_verdict` 是 107 不是 121**。我在重生成前读 17:10 那版：`{allow 97, exempt 107}`，合计 204 = primary 条数；`121 = 107 + 14` 是把伴生**第二次**加进去。§7.12.8 表里也是 107。所以那一层当时就已经只覆盖 primary 了，缺的是键名与顶层别名，不是口径。
2. **`done_when` 第 4 条写的「74 主/14 伴生」= 79 主**。「74」与你同段「必须保持不动」里的 79、与实测 79（`custom_signal` 77 + `monitor_rule` 2）都对不上，我按 79 出。

---

## 9. 待架构师追认（我没扩权）

1. 结构键引用的 `side` 取值（我取 `L`，见 §3 末）。
2. `note` 字段：v0.6 表内没有，是你上一轮要求「注释搬到单独字段」的落地；位置在 `RECORD_FIELDS` 末位。
3. `normalize_inventory()` 与 `InventoryError` 落在**生成器内**（`gate.py` 尚不存在）：F-A39 的 v1 降级读法与「读 `"1"` 要 L2/L3 就拒绝」目前只有这一份实现，接线时 `gate.py` 应复用它而不是另写一份。

## 10. 未验证

- `gate.py` 未实现，「L2 allowlist 只读 `live_config`」目前靠结构与 `notes` 约定，非运行时强制。
- `custom_factor` 的公式依赖与 `research_strategy` 的 `referenced_factors` 本身是集合，这两类按「每名一处」而非真·逐出现（今日 20 + 25 条）。
- 同一 token 若在同一行出现两次会共用一个行号（当前 0 例）。
- `notes` 文本参与 digest（契约只剔 4 键），改一句话即换 digest——签认时要连同 notes 一起冻。
- 旁挂 `.sha256` 只对应本次字节，不能作签认对象（已按你的裁定执行）。

## 11. 复现命令与产物位置

```bash
# 生成（两次，验证幂等）
python backend/scripts/build_referenced_factor_inventory.py
python backend/scripts/build_referenced_factor_inventory.py --quiet
# 摘要外部复算（逐字取自契约 §7.12.4）
bash research/referenced-factor-inventory-v3-20261107/digest_7_12_4.sh
# 侧车（在该目录下执行）
cd docs/architecture/evidence && sha256sum -c referenced_factor_inventory.json.sha256
```

证据目录 `research/referenced-factor-inventory-v3-20261107/`：
`run_v3_1.txt`–`run_v3_4.txt`（四次运行自检）、`digest_7_12_4.sh` + `digest_output.txt`、
`v2_replay.json`（v2 字节复现，用于 P1 归因）、`final_run_a.json`（两次生成的一致性对照）、
`git_status_before_v3.txt` / `git_status_after_v3.txt`、`build_referenced_factor_inventory.v2.bak.py`（v2 备份）、
`patch_v3.py`（22 段锚点替换，每段断言锚点唯一）。
