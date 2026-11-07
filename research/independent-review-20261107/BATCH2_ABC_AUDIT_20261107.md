# 批二 A/B/C 独立审核：`uf_dist_prior_high_250` 对账 · 契约 v0.4 自洽 · 存量 `draft` 盘点

审核人：独立审核工程师（不参与被审实现）
时间：2026-11-07 16:2x–16:5x（Asia/Shanghai）
仓库：`C:\work\sourcecode\tick-stock-panel`，分支 `dev`，`HEAD 65c6e42f`（2026-11-07 12:56:05 +0800，未提交改动照旧保留）
纪律：未提交、未部署、未重启服务；未写 `D:\TSP`（全程只读）；**未重跑 `f_class_parity.py`**（不覆盖他人证据）；未改他人文件。
本轮范围：只做 A/B/C 三项。**不判 F-A5、不判 `rsi_14`。**

---

## 0. 一句话结论

- **A（`uf_dist_prior_high_250` 对账）：PASS。** 自写脚本逐项复现被审方的四个数：`max_abs_diff = 0.0`、`n = 5,332,523`、`jaccard = 1.0000000000`、`den ≤ 0 = 0`；落盘文件 sha256 仍是 `7c8163e4…f5`、756 B、mtime 16:07:00，**未被再次改写**。
- **B（契约 v0.4）：条款自洽性基本通过，实现覆盖为零。** 归档副本逐字节等于冻结四元组；§7.1 八行公式与 v0.3 **逐字未变**；§7.4 与 §7.6 的 `F-A5` **文本矛盾已消除**（v0.4 显式替换「不动 store」并加了自洽条款）；但 §7.4 的「唯一允许的 store 改动面」与当前 `store.py` 实际 diff **已不对齐**（P2），且引用的行号全部过期。§7.7 的 `F-A7` **必然 FAIL**（`FactorSpec` 21 字段无 `status`、`gate.py` 不存在）；§7.8 的 `FS03`–`FS06` 与别名解析 **0 行实现，纯条款**。
- **C（存量 `draft` 盘点）：复核一致。** 15 个 json **全部 `draft`**、`active` 数 0。闸门若按 §7.7.2 矩阵直接上生产，**生产可用因子 = 0（store 0 + pack 0），会全站停产**；唯一不至于停产的原因是 §7.8.5 的过渡期条款——而该条款的前置产物 `referenced_factor_inventory` **目前不存在**。

---

## 1. 总表

| 判据 | 判定 | 命令 | 退出码 | 关键数字 |
|---|---|---|---:|---|
| A-1 数值对账 `max_abs_diff` | **PASS** | `backend/.venv/Scripts/python.exe -X utf8 research/independent-review-20261107/scripts/a_dist_prior_high_250_parity.py` | 0 | **0.0**；超 1e-12 = **0 行**；非零差 = **0 行** |
| A-2 `dist>=-0.03` jaccard | **PASS** | 同上 | 0 | **1.0000000000**（both 150,292 / sys_only 0 / res_only 0） |
| A-3 分母 ≤0 与空值 | **PASS** | 同上 | 0 | `den<0`=**0**、`den==0`=**0**、`den` 空=**177,478**（评估窗）/ **838,826**（全帧）；inf 两侧 **0** |
| A-4 首根非空 | **PASS** | 同上 | 0 | **2019-01-17**（两侧同）；逐 symbol 首根 bar 序号不一致 **0 / 3,326 只** |
| A-5 落盘未被再改写 | **PASS** | 同上（脚本内含前后快照） | 0 | sha256 `7c8163e4…404f5`、**756 B**、mtime **16:07:00**、v1，前后快照 `diff=[]` |
| B-1 归档副本是否逐字节保全 | **PASS** | `backend/.venv/Scripts/python.exe -X utf8 research/independent-review-20261107/scripts/bc_contract_and_inventory.py` | 0 | **89,833 B / 914 行 / `5eb97724…565903`**；正文前缀 `head -c 89350` = **`b082d902…9fbfef`** |
| B-2 §7.1 八行公式相对 v0.3 逐字未变 | **PASS** | 同上 | 0 | 整节 2,514 字符，sha256 两侧同为 **`6d3db013…b449d8`**；8 行逐字相同 |
| B-3a §7.4 与 §7.6 的 F-A5 是否仍矛盾 | **PASS（矛盾已消除）** | 同上 | 0 | §7.4 命中「替换 v0.3 的「不动 store」」+「不构成对 §7.4 的违例」；§7.6 命中「该实现属 §7.4 v0.4 允许面」 |
| B-3b 「唯一允许的改动面」与代码是否对齐 | **FAIL（P2）** | 同上 | 0 | 契约只许 3 个新函数；实际 `store.py` **+148/−1**，含 `load_one`(:39)、`register_definition`(:169 行为变更)、`_canonical`(:203)、`_merge_for_write`(:261)、`_GROUP_DEFAULT`(:200)；引用行号 207/234 已过期 |
| B-4 `F-A7` 在当前代码下是否必然 FAIL | **确证：必然 FAIL** | 同上 | 0 | `FactorSpec` **21 字段、无 `status`**（`hasattr=False`）；`backend/app/factors/gate.py` **不存在**；`backend/app` 全树 `FS01`–`FS06` / `alias_of` / `assert_factors_usable` / `GateReport` 命中 **0** |
| B-5 `FS03`–`FS06` 与别名解析是否有实现 | **未实现（仅条款）** | 同上 | 0 | 上述符号命中 **0**；`F-A14`–`F-A17` 全部不可判 |
| C-1 存量 `draft` 盘点复核 | **PASS（复核一致）** | 同上 | 0 | **15 个 json / 15 个 `draft` / `active`=0**；逐个 id 见 §4 |

原始输出：`artifacts/a_stdout.log`、`artifacts/bc_stdout.log`；机器结果：`artifacts/a_dist_prior_high_250_parity.json`、`artifacts/bc_results.json`。

---

## 2. A：`uf_dist_prior_high_250` vs 研究侧 `dist_52w_high`

### 2.1 我的做法（与被审方脚本无共用代码）

`scripts/a_dist_prior_high_250_parity.py`：

1. 研究侧**自己写**：`den = high.shift(1).rolling_max(250).over("symbol")`，`dist = close / den - 1`（polars 原生，不 import `common.add_indicators`）。
2. 系统侧**只用生产同一函数**：读**磁盘那份 json 的 `formula` 字段**（`close / ts_delay(ts_max(high, 250), 1) - 1`）→ `compile_formula(...).frame_transform(frame)`。
3. 分母单独物化一次（`ts_delay(ts_max(high, 250), 1)`），确证分母本身也逐位相同，而不只是最终值。
4. 数据经 `FileMarketData.get_daily_batch`，窗口 2018-01-08 ~ 2026-10-30，`60*`/`00*` 前缀（与研究侧同口径），`full join` 严格一对一对齐（`join_rows == frame_rows == 6,422,875`）。

编译结果：`ok=True`、`dependencies=['close','high']`、`warmup_bars=251`。

### 2.2 实测（评估窗 2019-07-01 ~ 2026-10-30，帧 5,510,001 行）

| 项 | 我实测 | 被审方自报 | 判定 |
|---|---|---|---|
| `max_abs_diff` | **0.0** | 0.0 | 一致 |
| 超 1e-12 行数 | **0** | 0 | 一致 |
| 非零差行数 | **0** | 0 | 一致 |
| n（两侧均非空） | **5,332,523** | 5,332,523 | 一致 |
| null 口径不一致 | **0** | 0 | 一致 |
| jaccard(`dist>=-0.03`) | **1.0000000000** | 1.000000 | 一致 |
| `both_true` | **150,292** | 150,292 | 一致 |
| `den<0` / `den==0` / `den` 空（评估窗） | **0 / 0 / 177,478** | 0 / 0 / 177,478 | 一致 |
| `den` 空（全帧） | **838,826** | 838,826 | 一致 |
| 首根非空日期 | **2019-01-17** | 2019-01-17 | 一致 |
| 全帧非空行 | **5,584,049** | 5,584,049 | 一致 |
| 逐 symbol 首根 bar 不一致 | **0 / 3,326 只** | 0（3,326 只） | 一致 |

模式补充：全帧 `max_abs_diff = 0.0`、超容差 0、`den` 最大绝对差 **0.0**、非零差 0 —— **分母与最终值都是逐位相等**，不是「1 ULP 内」的近似。

### 2.3 落盘状态（是否被再次改写）

| 项 | 值 |
|---|---|
| 路径 | `D:\TSP\data\user_data\custom_factors\uf_dist_prior_high_250.json` |
| 大小 | **756 B** |
| sha256 | **`7c8163e44571d95ebb88f54a38f971eae743485ceab0003cebd839270fe404f5`** |
| mtime | **2026-11-07 16:07:00** |
| version / status / lang | **1 / `draft` / `dsl`** |
| 我的脚本跑前跑后 | **完全相同**（`prod_diff_files = []`，15 个文件前后逐字节一致） |

结论：**自 16:07 落盘后未被再次改写**。同目录另 14 个文件 sha256 前 16 位与批二报告 §2.3 表中「后」值**14/14 全部相同**（我逐个 64 位复算比对，`mismatch=[]`），说明那 14 个此后也无漂移。

---

## 3. B：契约 v0.4 完整性与自洽

现行文件：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md`，**110,944 B / 1,050 行 / sha256 `6b8fb14c8b6dff19092151d526ca32f2191b2f5f77ca741d043443a36bff7895`**，mtime 16:18:58。与派发书给的 `6b8fb14c…` 一致。

### 3.1 B-1 归档副本是否逐字节等于原审核绑定对象 → PASS

| 项 | 契约冻结四元组 | 我实测 | 结果 |
|---|---|---|---|
| 字节数 | 89,833 | **89,833** | ✅ |
| 行数 | 914 | **914** | ✅ |
| 全文 sha256 | `5eb9772411f723576b657f85af7c0aa26427137a41fb53b5774b935942565903` | **同** | ✅ |
| 正文前缀 `head -c 89350` sha256 | `b082d902e08df2dc902f97d694dcd2e1ae96d93bd79485a66647470915f9bfef` | **同** | ✅ |

**能证与不能证**：能证「归档副本 == 当初冻结并绑定的那个对象」（四元组逐位命中）。**不能证**「被覆盖前的活文件当时就是这个内容」——原文件已被覆盖，且 `docs/architecture/` 未入 git（`?? docs/architecture/`），没有版本库可回放。这一点属**未知**，不是 PASS 的一部分。

### 3.2 B-2 §7.1 八行公式 → PASS（逐字未变）

- 整节 `### 7.1` 到 `### 7.2` 之间：2,514 字符，v0.3 与 v0.4 **sha256 同为 `6d3db0139a45f54c9e7399e19239929b21d0c37f660ceafaf52f707835b449d8`**，逐字 `IDENTICAL: True`。
- 8 行公式行（`| \`...\` | ts_... |`）逐行相同：`vol60 / ma120 / ma200 / prior_high_20 / prior_high_55 / prior_high_250 / prior_low_10 / prior_vol_20` = 61/121/201/21/56/251/11/21，deps = `{close}×3 {high}×3 {low} {volume}`。
- 5 只 `prior_*` 全部含 `ts_delay(...,1)` 且用 `high`/`low`/`volume`——**批一最大的坑在 v0.4 里没有被改坏**。

### 3.3 B-3a §7.4 与 §7.6 的 F-A5 是否还矛盾 → 条文层面：不再矛盾

| 位置 | 现在写的是 | 结论 |
|---|---|---|
| §7.4 第 3 条 | 「**改动面（v0.4 更正，替换 v0.3 的「不动 store」）**」+ 允许三个新函数 + `api/factors.py` 保存分支 | 禁令已被显式撤回 |
| §7.4 末条 | 「§7.6 `F-A5` 描述的这份实现**属于本节允许面**，不构成对 §7.4 的违例；反之，§7.4 也不得以「不动 store」为由判它越界。v0.3 的这两句互相打架，v0.4 修掉。」 | 自洽条款已写入 |
| §7.6 `F-A5` | 「**该实现属 §7.4 v0.4 允许面**（`upsert_definition`/`content_signature`），不构成对「不动 store」的例外。」 | 同向 |

我上一轮报的「§7.4 明文不动 store，实际 `store.py` +91/−1」这条**矛盾在文本上已被 v0.4 修掉**。

### 3.4 B-3b 但「唯一允许的改动面」与当前代码已不对齐 → FAIL（P2，非本条原问，但必须报）

契约 §7.4 把允许面**穷举**为：`content_signature` / `is_same_content` / `upsert_definition` 三个纯新增函数（引 `store.py:207-257`）+ `api/factors.py` 保存分支（引 `:333-360`）。实测现状：

| 契约声明 | 实际 |
|---|---|
| `store.py` 仅 3 个新函数 | `git diff --numstat` = **`store.py +148/−1`**；新增符号还包括 **`load_one`(:39)**、**`_canonical`(:203)**、**`_GROUP_DEFAULT`(:200)**、**`_merge_for_write`(:261)** |
| 纯新增 | **`register_definition`(:169) 有行为变更**：新增 `if get_factor(spec.id) == spec: return spec`（改的是**启动期装载路径**） |
| `content_signature` 在 `:207-257` | 实际 **`:218`**（`is_same_content` **:247**、`upsert_definition` **:276**、`load_into_registry` **:317**） |
| 「unchanged 分支仍须先走 `to_spec(stored)`」引 `store.py:234-239` | 实际在 **`:289-294`**；`:234-239` 现在是 `content_signature` 的投影字典 |
| `api/factors.py:333-360` | **准确**（`@router.post("/custom")` 在 :333，分支到 :361） |

另：`store.py` 当前 **17,315 B、mtime 16:23:11**（我上一轮审的是 15:35:28、`+91/−1` 那版）。契约 §7.6 的 `F-A5` 行里「mtime 15:35:28」这句**已过期**。（`store.py` 又在我审核期间被改过，属事实记录；本轮不据此判 F-A5。）

判定：**条文矛盾消除 = PASS；改动面穷举与行号 = FAIL(P2)**。要求：架构师更新 §7.4 的允许面清单到当前 diff，或实现方把 `load_one` / `register_definition` 变更登记为「允许面扩充」并说明理由；行号一并校正。

### 3.5 B-4 `F-A7` 在当前代码下是否必然 FAIL → 必然 FAIL（确证）

| 断言 | 实测 |
|---|---|
| `FactorSpec` 仍无 `status` 字段 | **确证**：21 个字段（`id/label/group/formula_text/kind/version/dependencies/direction/unit/warmup_bars/pit/pit_source/asset_types/incremental_safe/scale_free/null_policy/stability/intraday_monitor_safe/tags/lang/components`），**无 `status`** |
| `getattr(spec,"status",None)` | `uf_vol60` → **False**（`hasattr`），`ma20`(pack) → **False** |
| `backend/app/factors/gate.py` 是否存在 | **不存在**（目录只有 `__init__.py / dsl.py / ext_factors.py / materialize_cache.py / py_expr.py / registry.py / store.py`） |
| `assert_factors_usable` / `GateReport` | `backend/app` 全树命中 **0** |

→ `F-A7`（「`get_factor("<uf_*>").status` 返回四个合法值之一」）**在任何实现下都不可能通过**；`F-A8`/`F-A9` 依赖的闸门不存在，**不可判**。这不是实现的缺陷，是**条款先行、实现为零**的状态，应如实登记为「未实现」，不得记「待验」。

### 3.6 B-5 §7.8 的 `FS03`–`FS06` 与别名解析 → 未实现（仅条款）

`backend/app` 全树符号扫描（区分大小写，纯文本存在性）：

| 符号 | 命中文件数 |
|---|---:|
| `assert_factors_usable` | **0** |
| `GateReport` | **0** |
| `alias_of` | **0** |
| `superseded_by` | **0** |
| `FS01` / `FS02` / `FS03` / `FS04` / `FS05` / `FS06` | **各 0** |
| `deprecated_alias_used` / `resolved_id` | **各 0** |

→ §7.8.2 的 A-3（`FactorSpec.alias_of` + 4 跳解析 + 环检测）、§7.8.4 的三个新错误码、§7.8.6 的 `F-A14`–`F-A17`：**全部是条款，零实现**。

顺带核了 §7.8.1 的事实表（这些是 v0.4 引用的「实测」，值得确认没被写歪）：

| §7.8.1 # | 契约说 | 我实测 | 结果 |
|---|---|---|---|
| 1 / 2 | pack 14 个 id 全可 `get_factor`，`kind=custom`、`lang=dsl`、warmup 21/61/21/21/21/21/11/56/21/121/61/251/21/201 | **14/14 命中**，逐值相同；`formula_text` 非空可编译 | ✅ |
| 6 | 同口径双 id **8 组**；`prior_amount_20` 与 `uf_dist_prior_high_250` 各为单侧 | 目录 **15 个 json（14 `uf_` + 1 `cf_`）**；8 组配对成立；`prior_amount_20` 无 `uf_` 件、`uf_dist_prior_high_250` 无 pack 件 | ✅ |
| 10 | `all_factors()` 192 →（装载 15 条）207 | **192 → 207**，`load_into_registry` 返回 **15** 个 id | ✅ |
| 7 | pack `prior_*` 用 `ts_delay(ts_max(high,N),1)` | 实测 pack `prior_high_20 = ts_delay(ts_max(high, 20), 1)`（同型） | ✅ |
| 12 | 「pack 原名命中 `preferences.json`（`ma20`/`ma60`/`boll_lower`）与 `custom_signals/ma_golden_20_60.json`（`ma20`/`ma60`）」 | `preferences.json` 命中 **4** 个（多 `boll_upper`），且全部是 **`builtin:ma20` 这类 watchlist 列 + `source.key`**，不是策略因子引用；`ma_golden_20_60.json` 命中 `ma20` + `field:ma60`，且 **`enabled: true`** | ⚠️ 数量与**性质**都写偏（见 §5 不一致清单第 6 条） |

---

## 4. C：存量 `draft` 盘点（独立复核）

`D:\TSP\data\user_data\custom_factors\`，**15 个 json**，逐个 `json.load` 读 `id/kind/status/version/lang`，并算 sha256/字节/mtime：

| # | id | kind | status | version | lang | 字节 | sha256(前 16) |
|---|---|---|---|---:|---|---:|---|
| 1 | `cf_auction_resonance` | composite | **draft** | 2 | `null` | 638 | `70d20540a7f384a7` |
| 2 | `uf_auction_post0920_match_growth` | custom | **draft** | 2 | `null` | 461 | `840c65e4cfa7d0b0` |
| 3 | `uf_auction_tail_imbalance` | custom | **draft** | 2 | `null` | 503 | `1bdc6e8d288f8fcc` |
| 4 | `uf_auction_tail_match_growth` | custom | **draft** | 2 | `null` | 438 | `6c8f04a6c525e7c9` |
| 5 | `uf_auction_volume_surprise` | custom | **draft** | 2 | `null` | 469 | `19957bcd78d9e5dc` |
| 6 | `uf_auction_volume_vs_prev` | custom | **draft** | 2 | `null` | 500 | `8dc6abc6a45155df` |
| 7 | `uf_dist_prior_high_250` | custom | **draft** | 1 | dsl | 756 | `7c8163e44571d95e` |
| 8 | `uf_ma120` | custom | **draft** | 1 | dsl | 368 | `3ddb904acc7277d4` |
| 9 | `uf_ma200` | custom | **draft** | 1 | dsl | 368 | `cf96176f8458dca2` |
| 10 | `uf_prior_high_20` | custom | **draft** | 1 | dsl | 490 | `e3070878b5472b1a` |
| 11 | `uf_prior_high_250` | custom | **draft** | 1 | dsl | 438 | `9f95286b8f97ab40` |
| 12 | `uf_prior_high_55` | custom | **draft** | 1 | dsl | 434 | `1f0ce5c6d8365da3` |
| 13 | `uf_prior_low_10` | custom | **draft** | 1 | dsl | 432 | `e5885f47f4356043` |
| 14 | `uf_prior_vol_20` | custom | **draft** | 1 | dsl | 472 | `fa8667bc5e6f6132` |
| 15 | `uf_vol60` | custom | **draft** | 1 | dsl | 545 | `c9041ba4930ac9c2` |

统计：`status` 分布 = **{draft: 15}**、`active` = **0**；`kind` = 14 custom + 1 composite；`lang` = 9 `dsl` + 6 `null`。
另：`grep -rl '"status": *"active"' D:\TSP\data\user_data` = **0 个文件**（不只是这个目录）。

与开发经理给的口径对照：**15 个 / 全 `draft` / 6 个 auction / 8 个批一 `uf_*` / 1 个 `uf_dist_prior_high_250`** —— **一致**。
补充两点（清单里该有、派发书未提）：① 6 个 auction 文件 `lang` 键**缺失**（走后端 API 形状存盘）、`version=2`；其余 9 个 `lang="dsl"`、`version=1`。② `uf_dist_prior_high_250` 是本目录唯一 16:07 之后的写入。

### 4.1 「闸门一上线会不会全站停产」——我的判定：会

| 口径 | 可用数 |
|---|---:|
| store 侧 `active` | **0 / 15** |
| pack 侧 14 个 Provider 注册因子 | `FactorSpec` 无 `status` → §7.8.4 按 `draft` 处理 → **0 / 14** |
| **生产可用合计** | **0** |

具体触发链（不是推演，是逐条对上契约）：

1. §7.7.2 矩阵：`production` 模式只允许 `active`，`draft` → `FS01` 拒绝。
2. §7.7.3 把 `production` 挂在 **X1 `build_target_portfolio`** 与 **`paper_auto.on_rule_events`**：这两处只要引用一个因子，就整计划不生成/规则装载失败。
3. §7.8.4 明确「Provider 注册且无 `status`（现状：pack 14 个）→ `production` 拒绝 `FS01`（按 `draft` 处理）」。pack 恰好是**当前唯一被活配置引用**的那批：`custom_signals/ma_golden_20_60.json` **`enabled: true`**，`left: "ma20"`、`right: "field:ma60"` —— `ma20`/`ma60` 现在解析到的就是 pack 的 `kind=custom`、`stability=stable`、**无 status** 那两个。
4. 因此：**闸门按 §7.7.2/§7.8.4 原样上线 = 该 enabled 信号被 `FS01` 拦，生产链断。**

唯一缓冲是 §7.8.5 过渡期（存量只告警 + 报告写 `degraded=true`，不阻断），但它有前置条件：**「存量清单（`referenced_factor_inventory`）由因子工程师在批二**前**产出，本契约只要求这份清单存在且机器可读」**。实测：`referenced_factor_inventory` 这个词在整个仓库里**只出现在契约自己那一段**（`grep -rl` 命中 1 个文件 = 契约 md），**没有任何产物**。

→ 结论：**当前状态下闸门不能上线**。要么先产出 `referenced_factor_inventory` 并把 §7.8.5 过渡期与闸门同批实现，要么先给存量因子走完 status 流程（15 个 store 定义 + 14 个 pack id）。在两者都缺的情况下上线，就是全站停产。

---

## 5. 不一致清单（报告值 / 实测值）

| # | 来源 | 报告值 | 我的实测值 | 差异原因 |
|---|---|---|---|---|
| 1 | 批二报告 §2.2 ② | `dist>=-0.03` 触发率「两侧同为 **2.8184%**」 | 同一天数字：**2.8184% 的分母是非空行**（150,292/5,332,523）；按评估窗**全部行**是 **2.7276%**（150,292/5,510,001）；全帧全部行 **2.4563%** | **非矛盾**，是分母选择未标注。jaccard 本身两侧都是 1.0，结论不受影响。建议报告把分母写死 |
| 2 | 批二报告 §2.1 | 「二次提交同一内容：`unchanged=true`、`version` 仍为 1、字节与 sha256 不变」 | 我无法确认这句对应**哪一版代码**：`store.py` 现在是 17,315 B / mtime **16:23:11** / `+148/−1`，而我上一轮审的是 15:35:28 / `+91/−1` 版（那版 `content_signature` 用原始键集，API 形状 8/8 判「变了」） | **未知**（本轮不判 F-A5；但报告未标代码版本，属可追溯性缺口） |
| 3 | 契约 §7.6 `F-A5` 行 | 实现现状「mtime **15:35:28**」 | 现 `store.py` mtime **16:23:11**、17,315 B | 契约「现实现」描述**已过期** |
| 4 | 契约 §7.4 | 三函数在 `store.py:**207-257**`；unchanged 分支校验在 `:234-239` | 实际 `content_signature:218`、`is_same_content:247`、`upsert_definition:276`；unchanged 分支校验在 `:289-294` | **行号过期**（`:234-239` 现在是投影字典，不是校验分支） |
| 5 | 契约 §7.4 | 「这是**唯一**允许的 store 改动面」（三个新函数） | `store.py **+148/−1**`，另有 `load_one`(:39) 新增、`register_definition`(:169) **行为变更**、`_canonical`(:203)、`_GROUP_DEFAULT`(:200)、`_merge_for_write`(:261) | **契约穷举清单与代码不对齐**（P2）；`register_definition` 的变更落在**启动期装载路径**上，影响面比「保存入口」大 |
| 6 | 契约 §7.8.1 #12 | pack 原名命中 `preferences.json` 的 `ma20`/`ma60`/`boll_lower` | 实际命中 **4** 个（多 **`boll_upper`**），且全部是 `id: "builtin:ma20"` + `source.key: "ma20"` 的 **watchlist 列**，不是策略因子引用 | **数量漏 1、性质写偏**（把 UI 列写成因子引用）。这不改变 §7.8.5「活配置引用面很小」的结论，但会误导「哪些入口需要先接闸门」 |
| 7 | 批二报告 §2.3 | 14 个 json「不变」，逐个 16 位 sha256 | 我 64 位逐个复算：**14/14 前 16 位与报告「后」值相同**，`mismatch=[]` | **一致**（不是我发现的差异，记录以证明当前盘面 == 他们跑完那一刻） |
| 8 | 批二报告 §2.1 | 「旧版文件从未被任何进程加载消费」 | — | **未知**：进程历史不可回溯，我既不能证实也不能否证 |

---

## 6. 未验证 / 未知（不猜）

1. **归档副本与原活文件的逐字节同一性**：只能证「副本 == 冻结四元组」，不能证「被覆盖前的活文件当时是什么」——`docs/architecture/` 未入 git，无历史可回放。
2. **批二报告 §2.1 的 `unchanged=true` 对应哪版 `store.py`**：代码 16:23 又被改过，报告未标版本；本轮按指示不判 F-A5。
3. **服务与线上注册表状态**：未重启、未探测端口、未发 HTTP 请求；`all_factors()` 的 192/207 是**进程内**测量，不代表线上进程。
4. **闸门上线后的真实停产范围**：闸门代码不存在，只能按契约矩阵推导；未做端到端（无可运行实现）。
5. **前端/API 层对 `draft` 因子的展示与保存字段**：未触及。
6. `uf_dist_prior_high_250` 的**生产消费侧**（策略/回测里真正引用它）未验证——本轮只验「注册 + 数值对账」。

---

## 6.5 审核期间工作区漂移（事实记录，不是我造成的）

派发书（16:21）称 `store.py` = **+91/−1、mtime 15:35:28**。我第一次读代码时（16:23 之后）已是：

| 项 | 派发书 | 我实测（16:23:11 之后） |
|---|---|---|
| `store.py` | `+91/−1`、15:35:28 | **`+148/−1`、17,315 B、mtime 16:23:11** |
| `api/factors.py` | `+8/−16`、15:35:28 | `+8/−16`、mtime 15:35:28（未变） |

另：`research/factor-registration-b2-20261107/` 与 `research/factor-registration-fa5b-20261107/` 两个未跟踪目录在我审核开始前后出现（前者含我本轮 A 项的被审报告，后者像 F-A5 返工交付）。`git status --porcelain` 条目数 23 → 24，增量是 `?? research/factor-registration-fa5b-20261107/`，**不是我写的**（我本轮只写本目录下的新文件）。

含义：**B-3b 的对齐判定绑定「16:23:11 那一刻的 `store.py`」**。F-A5 返工版（fa5b）若再改 `store.py`，§7.4 的行号与允许面须按新版本重新校。

## 7. 本轮我写了什么 / 没动什么

新增文件（全部在 `research/independent-review-20261107/`，均为新文件）：

| 文件 | 用途 |
|---|---|
| `scripts/a_dist_prior_high_250_parity.py` | A 项对账（自写，不复用被审脚本） |
| `scripts/bc_contract_and_inventory.py` | B+C 项：契约四元组/§7.1 逐字/§7.4 自洽/`F-A7` 探测/§7.8 符号扫描/192-207/15 个 json 盘点 |
| `artifacts/a_stdout.log`、`artifacts/a_dist_prior_high_250_parity.json` | A 项原始输出与机器结果（含跑前跑后目录快照） |
| `artifacts/bc_stdout.log`、`artifacts/bc_results.json` | B/C 项原始输出与机器结果 |
| `BATCH2_ABC_AUDIT_20261107.md` | 本报告 |

未做：未提交、未部署、未重启；**未写 `D:\TSP`**（两个脚本零写调用，A 脚本内含前后 sha256 对照证明 `prod_diff_files=[]`）；**未重跑 `f_class_parity.py`**（未触碰 `evidence/F_CLASS_PARITY_20261107.json`）；未改任何他人文件；未判 F-A5、未判 `rsi_14`。
