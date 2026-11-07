# referenced_factor_inventory v3.1 —— `side_key` 补齐（局部返工）

- 日期：2026-11-07 18:05（盘面 mtime）
- 来源：开发经理 17:55 派单（`assignment a3c2b273`），只修一处字段填充
- 范围：`backend/scripts/build_referenced_factor_inventory.py` 单文件；产物 `docs/architecture/evidence/referenced_factor_inventory.json` + `.sha256`
- 未动：`backend/app/**`、`docs/factors/**`、契约、判据口径、粒度、canonical 算法、唯一键、allowlist

---

## 0. 结论先说

| # | 项 | 结果 |
| --- | --- | --- |
| ① | 93 条活配置 `side_key` 全非 null、可追到源码结构 | **达成**：93/93 非 null；93 条由「回源取结构路径再取字面量」逐条验证，0 不一致 |
| ② | 与期望表 v3.2 逐字段比对 | 契约 §7.10.2 的 **22 个表内字段差异 0**；`side_key` 差异 **0/93**（相等）；唯一差异是表外附录字段 `note` 的措辞 14 条（语义等价） |
| ③ | 唯一键 0 重复 + F-A34–A39 / F-A22 / A26 / FS01 全 PASS | **40 项自检全 PASS、0 FAIL、exit 0**；唯一键 218/218 去重 |
| ④ | 新三元组 | `canonical_digest = aefdf5283acfa8195fd3d9783984f076e62a9eeb8e1fb4816b0aadb21ab22d1a` / `schema_version = "2"` / `scanned_sources = 67` |

新 digest 三元组（**签认对象**）：

```
canonical_digest : aefdf5283acfa8195fd3d9783984f076e62a9eeb8e1fb4816b0aadb21ab22d1a
schema_version   : 2
scanned_sources  : 67
```

旁挂 `.sha256`（**只证字节完整，不作签认对象**）：
`b661c8cdfeeef6c0be3c1078151936ed515c6ef6765bfc70b5629050e0d14df4  referenced_factor_inventory.json`

旧三元组（v3，已被本次覆盖）：`184e4728…e1b1` / `2` / `67`。digest 变了是**预期的内容变化**（`side_key` 从 null 变真实路径，95 条记录字段变化），不是算法变化 —— §7.12.4 实现一字未改，见 §5。

---

## 1. 改了什么（一处填充逻辑，不外溢）

`side_key` 的取值来源原本只有结构块槽位（`scoring` / `formula` / `members` / `fields.<名>`），条件表达式槽位一律传 `None`。本次把条件槽位的**真实结构路径**填上，值由扫描处的结构位置生成，不按名字猜：

| 扫描域 | 结构位置 | 生成方式 | 新增取值 |
| --- | --- | --- | --- |
| `custom_signal` | `conditions[i].left` / `conditions[i].right` | `enumerate` 数组下标 | 是 |
| `monitor_rule` | `conditions[i].field` | 同上 | 是 |
| `strategy_override` | `overlay_filter[i].left` / `overlay_filter[i].right` | 同上（容器名同为参数） | 是 |
| `strategy_config` | `scoring` | 原有，未改 | 否 |
| `custom_factor` | `formula` / `members` | 原有，未改 | 否 |
| `research_strategy` | `fields.<名>` | 原有，未改 | 否 |

下标口径：取**数组下标**而不是「第几条产出记录」。跳过的条件（非 dict、`op=truth` 的信号列、数字右值）不改变其它条件的下标 —— 这是 `new_height_3`（3 个条件同名 `high`、`conditions[1]` / `conditions[2]` 各自成条）能对齐的关键。

改动清单（`diff -u` 实测 11 个 hunk，+59/−18 行；文件 1,219 → 1,260 行；完整 diff 见 `diff_vs_v3.diff`）：

| 位置 | 改动 |
| --- | --- |
| 模块 docstring 的 `side_key` 条目 | 补全取值域（条件槽位四族），声明「由结构位置生成，不按名字猜」 |
| `_condition_occurrences()` | 新增必填 keyword `container` / `index`，产出 `f"{container}[{index}].left|right"` |
| `scan_custom_signals()` | `for cond in` → `for idx, cond in enumerate(...)`，传 `container="conditions"` |
| `scan_monitor_rules()` | 同上；`("F", field, None)` → `("F", field, f"conditions[{idx}].field")` |
| `scan_strategy_overrides()` | 同上，`container="overlay_filter"` |
| `emit()` docstring / `NOTES` | 结构键清单同步（人读说明，不参与判据） |
| 新增常量 `SIDE_KEY_RE` | `side_key` 合法形态正则：`conditions[\d+].(left|right|field)` / `overlay_filter[\d+].(left|right)` / `scoring` / `formula` / `members` / `fields.<名>` |
| `self_check()` F-A37 结构键条 | 白名单从「3 个字面量 + `fields.` 前缀」改为 `SIDE_KEY_RE.match()`（判据语义不变：结构键只许进 `side_key`，`side` 仍只 L/R/F） |
| `self_check()` 新增 3 条 | `F-A37 side_key 反例可失败`、`side_key 活配置全覆盖`、`side_key 全量全覆盖` |

**判据没有放宽**：白名单从白名单字面量换成白名单正则，是因为合法形态从 5 种变成 11 种；同时补了**反例条**（把 `field:ma20` / `ma20` / `L` / `conditions[x].left` / `conditions.left` / `scoring.extra` / `fields.` 七个非法形态喂进去，必须全被拒），证明这条不是恒真。原 37 项自检 → 40 项（只增不减，没有一条被删或改写语义）。

---

## 2. `side_key` 覆盖与分布

**活配置 93 条：非 null 93 / null 0**

| 条数 | `side_key` |
| --- | --- |
| 23 | `conditions[0].right` |
| 22 | `conditions[0].left` |
| 21 | `conditions[1].right` |
| 17 | `conditions[1].left` |
| 3 | `conditions[2].right` |
| 3 | `conditions[2].left` |
| 1 | `conditions[3].right` |
| 1 | `conditions[3].left` |
| 1 | `conditions[1].field` |
| 1 | `conditions[0].field` |

**全量 218 条：非 null 218 / null 0**（非活配置 125 条：`scoring` 78、`formula` 16、`fields.entry` 10、`fields.score` 9、`fields.exit` 6、`members` 4、`overlay_filter[0].left` 2）

要求 2 原本允许「非活配置能确定就填、不能确定保持 null 并说明原因」。实测**无判不出项**：这 125 条的结构位置在源码里都是确定的（`scoring` 是 META 字典键、`formula` 是 DSL 编译器给出的依赖名、`members` 是 composite 的键、`fields.<名>` 是 research `fields` 的子键、`overlay_filter[0].left` 是数组下标），所以全部填上而不是留空。null 计数 0，因此没有「判不出原因」需要交代。

---

## 3. 与期望表 v3.2 的逐字段比对

比对对象：`docs/factors/evidence/referenced_factor_inventory_expected_20261107.json`（v3.2 / `f21494f9…` / 79 主 + 14 伴生 = 93）。比对键 = `(source_path, evidence, side, ref_name, record_kind)`。

**多重集**：产物活配置 93 条 vs 期望 93 条 —— `artifact_only = 0`、`expected_only = 0`。

**契约 §7.10.2 表内 22 个字段**：0 个字段有差异。

```
契约表内字段 22 个: source_kind, source_path, source_id, source_sha256, source_enabled,
path_scope, ref_raw, ref_name, ref_namespace, resolved_id, class, verifiable, gate_mode,
verdict, code, evidence, both_collision, path_divergence, side, side_key, record_kind, path_base

共同键 93 条 → 22 表内字段差异汇总：0 个字段有差异
  → 除 side_key 外差异字段 0（side_key 本身也 0）
```

**`side_key` 侧差异：0 / 93 —— 相等，不是「迁就」。** 两边的 93 个值逐条相同。生成侧没有读期望表（`build_referenced_factor_inventory.py` 里没有任何对 `docs/factors/**` 的引用），见 §4 的独立回源验证。

**唯一差异：`note`（表外附录字段，14 条，全部是 `companion` 记录）**

| 侧 | 内容 |
| --- | --- |
| 期望表 | `同名既解析为基础列、又是一个 kind=custom 的 pack 因子 id（N2 冲突）；本记录只让冲突逐出现可见，不参与 allowlist、不参与放行判定` |
| 产物 | `N2 伴生记录: 同名字面量同时命中 ALLOWED_FIELDS 与因子注册表, 按 N1 基础列优先, 伴生仅登记冲突, 不参与放行` |

两侧都非空（14/14），语义一致（都是「N2 冲突只登记、不参与放行」），措辞不同。`note` 不在契约 §7.10.2 的 22 字段表内（是「表外唯一附录字段」，v3 报告已登记），**不参与任何判据、不进 canonical 之外的可判字段集**——注意它**在** canonical digest 覆盖范围内，所以措辞差异会让两边 digest 不同；这是两边各自签认自己的产物、不互为签认对象时的正常状态。**未改 `note` 措辞**：改措辞等于向期望表抄文本，属口径迁就；本单只授权填 `side_key`。

---

## 4. `side_key` 真的来自源码结构（不是抄期望表）

两道独立验证，都不复用生成器的解析函数：

**4.1 回源取字面量**（`trace_side_key.py`）
把每个 `side_key` 用正则解析成「dict 键 / 数组下标」，再到源 JSON 上**真取一次**，取到的字面量必须等于该条记录的 `ref_raw`：

```
活配置 93 条：回源比对 93 条（custom_signal + monitor_rule），跳过 0 条
不一致 0 条

期望表 v3.2 同样回源：比对 93 条，不一致 0 条
```

即期望表给的路径在源里同样能取到对应字面量 —— 两边的路径不是「文本巧合相同」，而是**指向同一处结构位置**。对期望表只做核对，不据以填值。

**4.2 判不出项**：0 条（§2）。

---

## 5. `side_key` 不参与判据 / 不进 allowlist / 不进唯一键（实测，不靠注释）

`check_sidekey_nonfunctional.py`：

| 检查 | 结果 |
| --- | --- |
| 唯一键（契约 F-A34 键 = path+evidence+side+ref_name+record_kind，不含 `side_key`） | 218 条 / 去重 218 条 → 重复 **0** |
| 把全部 `side_key` 改写成别的合法值 → `verdict` / `code` / `ref_namespace` / `class` / `resolved_id` | **全等**（逐条） |
| 同上改写后唯一键集合 | **相同** |
| 与 v3 产物（`side_key` 全 null）比唯一键集合 | **相同** |
| 与 v3 产物比逐字段变化 | **只有 `side_key`：95 条** |
| 与 v3 产物比 `summary` | **相同** |
| 与 v3 产物比 `stale_count` | 0 → 0 |

「95 条」= 全量 218 里有 95 条在 v3 是 `null`（93 活配置 + 2 条 `strategy_override` 的 `overlay_filter`），其余 123 条 v3 已有结构键值。活配置面 93 条全部从 null → 真实路径。

`backend/app/**` 里 `side_key` 消费方：**0 处**（`grep -rn "side_key" backend/app frontend/src` 无命中），所以本次改动对运行时零影响。

---

## 6. 自检全项（40 项 / exit 0）

命令：

```
backend\.venv\Scripts\python.exe backend\scripts\build_referenced_factor_inventory.py --data-dir D:/TSP/data
→ EXIT=0
```

```
 1 [PASS] F-A22 幂等(字节): 两次生成除 generated_at 外逐字节相同
 2 [PASS] F-A22 幂等(digest): canonical_digest=aefdf528…2d1a
 3 [PASS] F-A36 外部复算: §7.12.4 复算=aefdf528…2d1a
 4 [PASS] F-A36 扰动不变: 改 generated_at/repo_head/data_root + records 倒序 → digest 不变
 5 [PASS] F-A36 改 verdict 必变: 改 1 条 primary 的 verdict → digest 变化
 6 [PASS] §7.10.2 字段: 23 字段 / 218 条，越界 0 条
 7 [PASS] F-A34 唯一键: 218 条 / 去重 218 条（键 = path+evidence+side+ref_name+record_kind）
 8 [PASS] F-A34 活配置 93=79+14: live records=93 by_record_kind={'companion': 14, 'primary': 79}
 9 [PASS] F-A34 ma_golden_20_60 4 主 + 4 伴生: 主=[(9,'L','ma20'),(11,'R','field:ma60'),(16,'L','ma20'),(18,'R','field:ma60')] / 伴生=4
10 [PASS] F-A35 层内求和=primary: all 204==204 / live 79==79
11 [PASS] F-A35 v1 别名等值: summary.by_verdict={'allow': 97, 'exempt': 107} == all_records.by_verdict
12 [PASS] F-A35 live 22 源: live sources=22（期望 22）
13 [PASS] F-A35 反例可失败: 把伴生 14 条计入 → 求和 218 ≠ primary 204
14 [PASS] F-A37 ref_raw 保留前缀: 带前缀 48 条（field:），ref_name 去前缀错 0 条
15 [PASS] F-A37 side 三值: 取值集合 ['F', 'L', 'R']
16 [PASS] F-A37 evidence 可解析: 含 # 或不可解析 0 条（正则 `path:line` / `path:start-end`）
17 [PASS] F-A37 结构键只进 side_key: side_key 取值 ['conditions[0].field', 'conditions[0].left', 'conditions[0].right', 'conditions[1].field', 'conditions[1].left', 'conditions[1].right', 'conditions[2].left', 'conditions[2].right', 'conditions[3].left', 'conditions[3].right', 'fields.entry', 'fields.exit', 'fields.score', 'formula', 'members', 'overlay_filter[0].left', 'scoring']
18 [PASS] F-A37 side_key 反例可失败: 7 个非法形态被放行 0 个 []
19 [PASS] side_key 活配置全覆盖: 活配置 93 条 / null 0 条
20 [PASS] side_key 全量全覆盖: 218 条 / null 0 条
21 [PASS] F-A38 path_scope ⊆ {history,intraday}: 取值集合 ['history', 'intraday']，both 计数 0
22 [PASS] F-A38 21 日线 history + 1 monitor intraday: 日线源 21 / monitor 记录 2
23 [PASS] F-A38 path_divergence 0: 0 条
24 [PASS] F-A38 7 条冲突源 allow: 7 源 / verdict ['allow']
25 [PASS] F-A39 v1 降级可读: ref_name:=ref_raw / side:=null / record_kind:="primary"
26 [PASS] F-A39 v1 不许 L2/L3: 读 "1" 却要求 L2 → 拒绝启动
27 [PASS] F-A39 v2 缺字段拒绝加载: "2" 且缺新增字段 → 拒绝加载
28 [PASS] F-A25 无 unknown: verdict=unknown 0 条
29 [PASS] F-A26 新鲜度: stale_count 复算=0 / 记录值=0
30 [PASS] 源级 22 allow / 0 shadow / 0 block: by_verdict_sources={'allow': 22}
31 [PASS] 活配置 by_verdict 全 allow: live.by_verdict={'allow': 79}
32 [PASS] 全量记录数: records=218（期望 218）
33 [PASS] summary 结构: summary 键=['all_records', 'by_code', 'by_namespace', 'by_verdict', 'live_config']
34 [PASS] F-A24 冲突必报: column 主 14 / 伴生 14（期望各 14），伴生形态=factor 视图(class=custom_dsl)
35 [PASS] F-A23 不 grep: 散文/展示列误计 0 条
36 [PASS] 7 条冲突信号=column: 判错 0 条 []
37 [PASS] 2 virtual 不拦: virtual 记录 2 条，判错 0 条
38 [PASS] FS01 实拦: 0 条
39 [PASS] N3 通道可触发: ma20 按 both 解析 → divergence=True, verdict=block
40 [PASS] FS01 通道可触发: 试探 15 个 draft 定义，判 block+FS01 15 个
```

`PASS 40 / FAIL 0 / exit 0`。完整输出：`run_final.log`。

---

## 7. canonical digest 独立复算（§7.12.4 原样，不用产物里的函数）

`verify_independent.py`（`DROP` 四键、`records` 按每条自身规范化 JSON 全序、`ensure_ascii=False + sort_keys + separators=(',',':')` + sha256）：

```
落盘 canonical_digest : aefdf5283acfa8195fd3d9783984f076e62a9eeb8e1fb4816b0aadb21ab22d1a
独立复算(契约原样)     : aefdf5283acfa8195fd3d9783984f076e62a9eeb8e1fb4816b0aadb21ab22d1a
一致                   : True
扰动(生成时刻/head/数据根) → 不变: True
扰动(records 倒序)         → 不变: True
扰动(records 随机重排)     → 不变: True      # 固定种子 20261107
扰动(改 1 条 verdict)      → 必变: True
扰动(side_key 全置 null)   → 必变: True      # 证明 side_key 确实在覆盖范围内
```

最后一条同时说明：digest 从 `184e4728…` 变到 `aefdf528…` 是**内容变化**（`side_key` 进了 digest），算法没变、剔除键没变、全序规则没变。

---

## 8. 幂等与产物写入

| 检查 | 结果 |
| --- | --- |
| `--out` 重跑到别处，除 `generated_at` 外逐字节相同 | **是**（`generated_at 2026-11-07T18:05:19+08:00` vs `18:07:37`） |
| 两次 `canonical_digest` | 相同 `aefdf528…` |
| 原产物字节 sha | `b661c8cd…4df4` |
| 侧车内容 | `b661c8cd…4df4  referenced_factor_inventory.json`（一致） |
| 原产物与侧车是否被第二次运行改写 | 未改写（第二次写 `research/.../run_second.json`） |

产物：`186,343 B` / `5,549` 行（v3 为 `184,643 B`，增量来自 95 条 `side_key` 值）。

---

## 9. 边界核对

| 边界 | 结果 |
| --- | --- |
| 不改 `backend/app/**` | **未改**。`api/factors.py` mtime `16:33:57`、`factors/store.py` mtime `16:33:52`、`strategy/custom_signals.py` mtime `10-29 12:27` —— 全部早于本单开工（18:00），且 `git status --porcelain backend/app/` 仍是开工前那三项（两个 `M` + 一个 `??`），无新增 |
| 只改 `backend/scripts/build_referenced_factor_inventory.py` | **是**。该文件 `??`（未跟踪），sha `a3a250d2d929545ee2a490a763d6c392c38cf7276e3dd1ac65f6fe097746a7d6`（v3 为 `582c9287…1765`），`diff -u` 实测 **+59/−18 行 / 11 hunk**（1,219 → 1,260 行） |
| 不碰 `docs/factors/**` | **未碰**。期望表 v3.2 mtime `17:34:47`、契约 v0.6 mtime `17:16:36`，均未变；`build_referenced_factor_inventory.py` 内无任何 `docs/factors` 引用（生成侧不读期望表） |
| 不改契约 | **未改**。v0.6 mtime `17:16:36`、v0.7 mtime `18:03:23`，均早于本单开工（18:00）或未被本单触碰；两版的 `### 7.12 ` 区段逐字节相同（各 `10,822` 字符 / sha256 `3bab45ec211e8674…`），本单未在任一版本里留下字符 |
| 不提交 / 不部署 / 不重启 | **未做**（本单目录与其下文件在 `git status --porcelain` 里仍是 `??` 未跟踪，未 stage、未 commit） |
| 不覆盖 `research/referenced-factor-inventory-v3-20261107/` 旧报告 | **未覆盖**。目录 17 个文件 mtime 全部停在 `17:25`–`17:28`（本单开工 18:00 之前），`REPORT_v3.md` 未变；新报告另开本目录 `REPORT_v3_1.md`；改动前源码快照放在本目录 `build_referenced_factor_inventory.v3.bak.py`（`582c9287…`） |

`git status --porcelain` 四拍对照（集合差，逐行）：`git_status_before_v3_1.txt`（36 行，18:00 开工前）→ `git_status_after_v3_1.txt`（37 行，18:14）→ `git_status_final_v3_1.txt`（33 行，18:16 定稿）→ `git_status_final2_v3_1.txt`（34 行，18:26 收尾）。

**开工前 → 18:16 定稿，只有 5 行变化，全部不是本单造成的：**

```
+ ?? research/b2-engine-20261107/            # 另一条并行工作线在建（18:10:03），未触碰
- ?? research/tmp_cb.txt                     # 他人临时文件，已被其作者删除
- ?? research/tmp_check_before.txt           # 同上
- ?? research/tmp_meta_revision_note.txt     # 同上
- ?? research/tmp_sc.txt                     # 同上
```

**18:16 → 18:26 收尾，只多 1 行，也不是本单造成的：**

```
+  M backend/app/factors/dsl.py              # mtime 18:24:44，+19/−1 行，新增 xs_rank_pool/xs_rank_market/xs_rank_pct/xs_mean 算子与 E017 —— 另一条并行线（B2 引擎）在改，build_referenced_factor_inventory.py 无一处引用它之外的东西
```

这一行值得单列，因为它落在 `backend/app/**` 而我被禁止改它。**不是我改的**：我的生成器全程只读 `app.factors.dsl.compile_formula`（`build_referenced_factor_inventory.py:230/589`），从未写过任何 `backend/app` 文件；本单唯一写过的文件是 `backend/scripts/build_referenced_factor_inventory.py`（mtime `18:04:30`）。为排除它对产物的影响，我在这行出现**之后**又跑了一遍生成器：**40 PASS / 0 FAIL / EXIT=0，canonical 仍 `aefdf528…`，除 `generated_at` 外 payload 逐字节相同**（`run_after_dsl_change.json` / `.log`）。

`backend/app/` 在 18:00 与 18:16 两拍完全一致，仍是开工前那三项（`M api/factors.py`、`M factors/store.py`、`?? custom/research_factor_pack/`），**没有本单造成的任何改动**；`backend/scripts/build_referenced_factor_inventory.py` 仍是 `??`（未跟踪）。本单新增的只有 `research/referenced-factor-inventory-v3-1-20261107/` 一个目录。

---

## 10. 留给签认方的两个解释项（不在本单范围）

1. **`note` 措辞两侧不同**（14 条 companion）。`note` 是表外附录字段，两侧语义等价、文本不同。若要求两边文本也逐字节一致，需要一个裁定：谁来对齐、以谁为准 —— 本单只授权填 `side_key`，未动它。
2. **`side_key` 的取值域在契约里是开放的**（§7.10.2 只写「如 `fields.entry`、`scoring`、`members`」，未穷举）。本次把条件槽位四族（`conditions[i].left|right|field`、`overlay_filter[i].left|right`）纳入，是「结构路径」的自然延伸，也已写进生成器 docstring 与 `NOTES`；若架构师要收窄/改名（如改成 `conditions.0.left` 或 `conditions[1].right@field:ma60`），改动面仍是 `_condition_occurrences()` 一处 + `SIDE_KEY_RE` 一条。

---

## 11. 产物与证据清单

目录 `research/referenced-factor-inventory-v3-1-20261107/`：

| 文件 | 说明 |
| --- | --- |
| `REPORT_v3_1.md` | 本报告 |
| `patch_v3_1.py` | 打补丁脚本（10 处精确替换，每处断言命中 1 次，命中数≠1 即中止） |
| `run_a.json` / `run_b.json` / `run_second.json` | 三次 `--out` 重跑产物（+ `.sha256`） |
| `run_final.log` | **正式落盘那次**的完整输出（40 PASS / exit 0） |
| `run_b.log` | 加自检后的首次全量输出 |
| `verify_independent.py` | §7.12.4 独立复算 + 五类扰动 |
| `trace_side_key.py` | 回源取字面量（产物 93 条 + 期望表 93 条） |
| `check_sidekey_nonfunctional.py` | 证明 `side_key` 不参与判据 / 不进唯一键 |
| `compare_expected_v3_2.py` / `compare_v3_2.log` | 与期望表 v3.2 的 23 字段全量比对（含 `note`） |
| `compare_contract_fields.py` / `.log` | 只比契约 22 表内字段（`note` 单列）|
| `final_run_v3_prev.json` | 改动前的 v3 产物快照（`c5d8d22d…`），用于逐字段回滚比对 |
| `build_referenced_factor_inventory.v3.bak.py` | 改动前源码快照（`582c9287…`），与现版 `diff` 即本单全部改动 |
| `git_status_before_v3_1.txt` / `git_status_after_v3_1.txt` / `git_status_final_v3_1.txt` / `git_status_final2_v3_1.txt` | 四拍 `git status --porcelain`（开工前 / 首轮末 / 定稿 / 收尾） |
| `run_after_dsl_change.json` / `.log` | 并行线改 `dsl.py` 之后的重跑（40 PASS / exit 0，canonical 与 payload 均不变） |
| `compare_final_utf8.py` / `.log` | 与期望表 v3.2 的 UTF-8 可读全量比对（表内 22 字段 + 表外全部） |
| `verify_live_set.py` | 证明「活配置 93 条」= 期望表那 22 个源上的全部记录（79 主 + 14 伴生），不是别处凑出来的 93 |
| `run_finalcheck.json` / `.log` | 报告定稿后的自检重跑（40 PASS / exit 0，独立输出，不覆盖正式产物） |
| `patch_report_round2.py` | 本报告第 9 节与第 12 节的补充脚本（2 处精确替换，断言命中 1 次） |

改动前源码快照在本目录：`build_referenced_factor_inventory.v3.bak.py`（`582c9287…`）。

---

## 12. 报告定稿后的二次复核（同一份落盘产物，未重生成）

本单在写报告之后又把六项独立证据全部重跑一遍，产物与侧车**未被改写**（`referenced_factor_inventory.json` mtime 仍是 `18:05:22` / sha 仍 `b661c8cd…4df4`）：

| 复核 | 命令（`backend\.venv\Scripts\python.exe`） | 结果 |
| --- | --- | --- |
| 自检全项 | `backend/scripts/build_referenced_factor_inventory.py --data-dir D:/TSP/data --out research/.../run_finalcheck.json --quiet` | **40 PASS / 0 FAIL / EXIT=0**（`run_finalcheck.log`）；新跑出的 canonical 与落盘相同 `aefdf528…` |
| §7.12.4 独立复算 | `verify_independent.py` | 一致 `True`；五类扰动行为全符合；EXIT=0 |
| 回源取字面量 | `trace_side_key.py` | 产物 93 条 / 期望表 93 条，不一致 **0**；EXIT=0 |
| `side_key` 非功能性 | `check_sidekey_nonfunctional.py` | 唯一键 218/218 去重 0 重复；改写 `side_key` 后判据字段全等、唯一键集合相同；与 v3 比只 `side_key` 95 条变；EXIT=0 |
| 与期望表 v3.2 比对 | `compare_final_utf8.py` | 表内 22 字段差异 **0**（`side_key` 0/93）；表外仅 `note` 14 条措辞；`side_key` 逐条相等 `True` |
| 并行线改动后复跑 | `build_referenced_factor_inventory.py --out run_after_dsl_change.json --quiet` | `backend/app/factors/dsl.py` 在被另一条线改动之后重跑：**40 PASS / 0 FAIL / EXIT=0**，canonical 仍 `aefdf528…`，除 `generated_at` 外 payload 逐字节相同 |
| 活配置集合界定 | `verify_live_set.py` | 期望表 22 个源在产物里的记录恰为 93 条（79 `primary` + 14 `companion`），与 `summary.live_config.records` 相等；期望表 22 源全部落在产物里，缺 0 |

`compare_final_utf8.py` 是重写过的比对脚本（原 `compare_expected_v3_2.py` 在中文 Windows 控制台输出被 GBK 截断，日志 `compare_v3_2.log` 里中文是乱码）：新脚本 `sys.stdout.reconfigure(encoding='utf-8')`，并把「字段缺失」与「值为 null」统一按 `None` 比较，输出 `compare_final_utf8.log`。结论与首轮一致，只是可读。

**给签认方的一条事实**（不在本单范围，但会影响签认）：期望表 v3.2 里的 `signature_triple` 仍指向 `2026-11-07T17:27:45 (184,643 B)` 那批字节的 `184e4728…`；那批字节已被本次产物覆盖（现 `186,343 B` / `aefdf528…`）。按期望表自己写的 `scope_note`（「Any regeneration changes records and therefore the digest; re-sign after each run.」），**需要因子工程师对新字节重签**，本单不代签、不代改 `docs/factors/**`。

---

## 13. 终验（交付前最后一拍，本次新增）

本节是报告定稿后的**最后一次全量重跑**，正式产物与侧车**未被改写**（mtime 仍 `18:05:22`、sha 仍 `b661c8cd…4df4`）。

| 复核 | 命令 | 结果 |
| --- | --- | --- |
| 自检全项 | `build_referenced_factor_inventory.py --data-dir D:/TSP/data --out research/.../run_turnend.json --quiet` | **`PASS` 40 行 / `FAIL` 0 行 / `EXIT=0`**（`run_turnend.log`） |
| §7.12.4 独立复算 + 五类扰动 | `verify_independent.py` | 落盘 == 独立复算 `aefdf528…2d1a`，一致 `True`；扰动四条不变、两条必变，全 True；**EXIT=0** |
| 回源取字面量 | `trace_side_key.py` | 活配置 93 条比对 93 条、跳过 0、不一致 **0**；期望表 93 条回源不一致 **0**；**EXIT=0** |
| `side_key` 非功能性 | `check_sidekey_nonfunctional.py` | 唯一键 218/218 去重、重复 **0**；改写 `side_key` 后判据字段全等 `True`、唯一键集合相同 `True`；与 v3 比仅 `side_key` 95 条变、`summary` 相同；**EXIT=0** |
| 与期望表 v3.2 比对 | `compare_final_utf8.py` | 多重集 `artifact_only 0 / expected_only 0`；**契约表内 22 字段差异 `NONE（0）`**，其中 `side_key` 差异 **0/93**；表外仅 `note` 14 条措辞；**EXIT=0** |
| 活配置集合界定 | `verify_live_set.py` | 期望 22 源全部落在产物里（缺 0）；这 22 源上的记录恰 **93 = 79 primary + 14 companion**，与 `summary.live_config.records` 相等；**EXIT=0** |

产物与侧车（收尾拍实测）：

```
sha256   b661c8cdfeeef6c0be3c1078151936ed515c6ef6765bfc70b5629050e0d14df4  docs/architecture/evidence/referenced_factor_inventory.json
侧车     b661c8cdfeeef6c0be3c1078151936ed515c6ef6765bfc70b5629050e0d14df4  referenced_factor_inventory.json
mtime    2026-11-07 18:05:22（生成后未被任何一次复核改写）
体积     186,343 B / 218 条 / side_key null 0 条（provisional 与全量都是 0）
canonical aefdf5283acfa8195fd3d9783984f076e62a9eeb8e1fb4816b0aadb21ab22d1a
```

`git status --porcelain` **第五拍**（`git_status_turnend_v3_1.txt`，37 行）与 18:26 收尾拍（34 行）比，只多 3 行，全部是**独立审核工程师**正在写的临时文件，不是本单：

```
+ ?? research/independent-review-20261106/_b0dump.txt    # mtime 18:25:29
+ ?? research/independent-review-20261106/_v07snip.txt   # mtime 18:26:20
+ ?? research/independent-review-20261106/_v07tail.txt   # mtime 18:27:11
```

`build_referenced_factor_inventory.py` 对这三个路径零引用（`grep` 命中 0），本单唯一写入的文件仍是生成器（mtime `18:04:30`，sha `a3a250d2…a7d6`，1,260 行）。

**边界收尾复核**：`backend/app/api/factors.py`（16:33:57）、`backend/app/factors/store.py`（16:33:52）、`backend/app/factors/dsl.py`（18:24:44，并行线 B2 引擎所改）、期望表 v3.2（17:34:47）、契约 v0.6（17:16:36）、旧报告 `REPORT_v3.md`（17:28:33）—— 全部早于本单最后一次写文件（18:04:30）或为他人并行改动，本单未触碰。
