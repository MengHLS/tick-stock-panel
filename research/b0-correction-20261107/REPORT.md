# B0 文档两处订正 + 6 条 catalog 断言 93→108

- 执行人：系统开发工程师（唯一实现者）
- 日期：2026-11-07 20:4x（本机时区 Asia/Shanghai）
- 派发：@开发经理 · assignment `ebd7f364-a01e-4385-81ba-4e1fefbf1082`
- 范围：**只做两件小事**。不接 B0b、不动 `matrix.py` / `registry.py` / `high_60d` / `low_60d`、不注册 `rsi_14_pct`、不跑回测、不提交、不部署。

## 0. 结论

| 项 | 结果 |
| --- | --- |
| 文档 `:12` 逐位相等 → pack 侧限定 | 已改，现 `:12` |
| 文档 `:219` 4.6% → 全帧/探针两口径 | 已改，现 `:219`（**4.6% 的归属与派发书不同，见 §2**） |
| 文档 `:221` 未做行补 4.6% 的其他出处 | 已补，现 `:221` |
| 6 条 red | 全部转为 PASS：**74 passed / 0 failed**（改前 6 failed / 68 passed，用例总数不变） |
| 断言删减 | **0 删**：两文件 `assert ` 计数改前改后均为 45 / 20；无 `skip` / `xfail` / `-k` |

`docs/factors/REGISTRATION_B0_20261107.md`：19,588 B / 282 行 / `aa283b15745d9e679a2276df4d3d6a24a10430c551ac150378eaa5e1c3bbeae6`（改前）
→ **20,873 B / 282 行 / `d474fcc8a31a595bfbc7bab438e1d3658483e3306af0adfa3b0380286cea802e`**（改后）

## 1. 文档三处改动（逐处 before → after）

### 1.1 `:12`（第 12 行）

改前：
> **14/14 注册完成，可被 DSL 直接引用，数值保真 `max_abs_diff = 0`（逐位相等），既有 178 个因子与内核零改动。**

改后（现 `:12`）：
> **14/14 注册完成，可被 DSL 直接引用；数值保真只在 pack 侧逐位（`max_abs_diff = 0`）；canonical `uf_vol60` 侧与 pack 差 1 ULP（1.11e-16，落在 §7.6 `F-A3` 的 `<1e-12` 内），全帧 77.06% 行不等（4,214,876 / 5,469,335，超 `1e-12` 行 0），不得写成「逐位相同」。既有 178 个因子与内核零改动。**

依据：`docs/factors/evidence/F_CLASS_PARITY_20261107.json#factor_parity.uf_vol60`（`n_both_nonnull=5,469,335`、`n_nonzero_diff=4,214,876`、`n_over_tol=0`、`max_abs_diff=1.1102230246251565e-16`、`tol=1e-12`）；契约 `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md:800` 的 `F-A3 = max_abs_diff < 1e-12`。**77.9% 是 60 只探针的分母（112,741），全帧是 77.06%；两个数分开写，避免再次混口径。**

### 1.2 `:219`（第 219 行，§4.1 表的「实测差异」行）

改前：
> … `max_abs_diff=1.11e-16`，4.6% 的行不等（60 只标的 116,287 行探针…）

改后（现 `:219`）：
> … `max_abs_diff=1.11e-16`，且差**全部为 1 ULP**。非零差行占比按两个口径分开记：**全帧** n=5,469,335 → **4,214,876 行 = 77.06%**、超 `1e-12` 的行 **0**（`evidence/F_CLASS_PARITY_20261107.json#factor_parity.uf_vol60`）；**60 只标的 / 112,741 可比行**探针 → **77.914%**，分母改 116,287 行则 75.538%（`B0_ACCEPTANCE_AND_V07_REVIEW_20261107.md` A5④ 表；本轮独立复算逐值相同，`research/b0-correction-20261107/logs/probe_4p6_attribution.json`）。**旧稿这里的「4.6% 行不等」是错的、已作废**：该数在任一 `vol60` 口径下都复现不出，也**不是**同一探针里 `ret1` 的比例（`ret1` 实测 93.685% = 108,887 / 116,227）——4.6% 与 `vol60`、`ret1` 都无关，是纯粹的错记，不得再引用。

### 1.3 `:221`（第 221 行，§4.1 表的「未做」行）

在原有「没有改 `common.py`，没有改 §4.2 原文」后追加：同一错记 `4.6%` 另见 `FACTOR_ENGINE_CONTRACTS_20261107.md` §7.15 A-4、`ARCH_DECISION_FACTOR_ID_CANONICAL_20261107.md:116`、`F_CLASS_PARITY_20261107.md:37`、`FACTOR_ENTRY_RULE_20261107.md:376`（后者反过来引本文件 §4.1 作依据），**不是我的文件，未改，已报开发经理**。

行数与改前相同（282 行）：三处都是**行内替换**，没有增删行。

## 2. 关于「4.6% 属探针 ret1」——**复算不成立，我按实测写，未按派发书**

派发书要求写成「4.6% 属同一探针的 `ret1`」。我在**同一取数口径**（`probe_vol60.py`：symbol 排序前 60 只）上独立复算，四个数两两不等：

| 比较对象 | n_both | 不等行 | 占比 |
| --- | ---: | ---: | ---: |
| `ret1`：`pct_change()` vs `x/shift-1` | 116,227 | 108,887 | **93.685%** |
| `vol60`（减法式）vs `vol60`（除法式），分母 112,741 可比行 | 112,741 | 87,841 | **77.914%** |
| 同上，分母改 116,287 行 | 116,287 | 87,841 | 75.538% |
| `vol60` 全帧（分母 5,469,335） | 5,469,335 | 4,214,876 | **77.06%** |

前三行与本仓既有审核记录 `docs/architecture/B0_ACCEPTANCE_AND_V07_REVIEW_20261107.md:127-132` A5④ 表**逐值相同**（该表由独立审核侧给出，我没采信派发书、也没抄它的结论，是自己跑 `probe_4p6_attribution.py` 得到的同一组数）。**结论：4.6% 既不是 `vol60` 的比例，也不是 `ret1` 的比例（`ret1` 是 93.685%）；它是无来源的错记。** 因此我写的是「不可复现、与两者都无关」，没有写「属 ret1」——若按派发书写，等于把一个新错数留进结项记录。

脚本 `research/b0-correction-20261107/probe_4p6_attribution.py`，产物 `logs/probe_4p6_attribution.json`（`panel_rows=6,422,875`、`subset_rows=116,287`、`subset_symbols=60`）。

## 3. 测试订正（6 条 red）

### 3.1 逐条根因：全部是 93→108，无一条属于别的原因

| # | 用例 | 断言 | 改 | 为什么是这个值 |
| --- | --- | --- | --- | --- |
| 1 | `test_factor_registry.py::test_factor_columns_snapshot` | `FACTOR_COLUMNS == GOLDEN_COLUMNS` | golden 插入 15 条 | 目录多 15 项（B0 的 14 + B2 `in_universe`），位置在 `first_board_chain_seed_low_preserved` 之后、`deviate_3d` 之前（插入点 index 86） |
| 2 | `::test_catalog_counts_and_kinds` | `len(specs) == 93`、`len({id})== 93` | 108 | 93 + 15 |
| 3 | `::test_asset_type_filter` | `len(stock) == 93`、`len(etf) == 70` | 108 / 85 | 15 个新因子 stock+etf 双资产，故 etf 同步 +15 |
| 4 | `::test_factors_api_contract` | `len(factors) == 93` | 108 | 同上 |
| 5 | `::test_factors_api_asset_filter_and_validation` | `len(etf) == 70` | 85 | 同上 |
| 6 | `test_factor_store.py::test_custom_factor_definition_roundtrip` | `builtin_count = 93`、`len(columns)==93` | 108 / 108 | 同上（`builtin_count` 只用于切前缀与下标比较） |

其余同文件断言（`virtual == 61`、`pit == 7`、截面联动 id 集合、`FACTOR_COLUMNS[0]`、`>= 48`、非法资产 422…）**一个都没动**，且改后仍全绿——说明 15 个新条目全是 `kind=custom`、非 PIT、非截面联动组，目录前缀顺序未变。

**golden 插入的正确性验证**（不靠肉眼）：把 15 个新 id 从现目录视图中滤掉后与旧 `GOLDEN_COLUMNS` 比，**完全相等（93 == 93）**；即改动只可能是「插入 15 条」，不存在既有条目的改写或移位。脚本输出 `filtered==golden: True 93 93`。

### 3.2 改动量（`git diff --numstat`，只列本批两个文件）

```
22  6   backend/tests/test_factor_registry.py
3   3   backend/tests/test_factor_store.py
```

- 22 = 15 条 golden + 1 行批次注释 + 6 处数字（每处 1 增 1 删）
- 3 = 3 处数字/注释（`builtin_count` 与两处 `== 93`，其中一处带注释同步）
- 45 assert → 45 assert、20 assert → 20 assert：**没删断言**

### 3.3 跑分（改后，`backend/.venv` 自带 pytest 9.2.0）

| 文件 | 结果 |
| --- | --- |
| `test_factor_dsl.py` | 34 passed |
| `test_factor_registry.py` | 11 passed |
| `test_factor_api.py` | 15 passed |
| `test_factor_store.py` | 7 passed |
| `test_factor_provider_contracts.py` | 7 passed |
| **5 文件合并** | **74 passed / 0 failed**（改前同一条命令：6 failed / 68 passed，总数同为 74） |

另跑同族其余 7 个 `test_factor_*.py`（attribution / delete_fail_closed / expansion / library_v2 / materialize_cache / py_expr / snapshot_retry）：**56 passed / 0 failed**，确认没有第二条同根因的硬编码 93。

日志：`logs/pytest_5files.log`。

## 4. 过程中出现的一次非 93→108 红（107，未复现，已定位机制，**未改代码**）

20:52 前后有一次 5 文件合并跑出 **6 failed / 68 passed**，但失败值是 **107 / 84**（比 108/85 少 1），缺的是 `in_universe`——不是计数口径问题。随后 11 次重跑（5 文件合并 6 次、`test_factor_store.py` 单跑 5 次）全部 74 / 7 passed，未再出现。

机制（读码 + 确定性复现，**属既有缺陷，不在本批改动面内**）：

- `app/extensions/factors.py:184-222` 的 `ensure_factor_providers()` 在发现分包**之前**就置 `_PROVIDERS_READY = True`，且对每个 provider 的 import/注册都 `except Exception` 只记 warning。任何一次瞬时失败（import 竞态、`.pyc` 写锁、并发进程争用）都会让该包**永久**缺失，且不可重试。
- 同一函数的另一个确定性分支：若进程内**第一次**触碰注册表发生在 `registry.isolated_registry()` 预览上下文里，provider 因子会注册进预览快照后被丢弃，`_PROVIDERS_READY` 仍为 True。实测：`inside isolated: 108 / in_universe True` → `after exit: 77 / in_universe False`。
- 当时同仓确有并发活动：`backend/.venv` 下 20:43:29 起了 uvicorn 服务（pid 39068/49124），20:57 有 `research/arch-build-20261107/build_contract_v08.py` 在跑。**竞态来源未证实**，只记录为最可能的解释。

处置：**没改**（不在本批范围，且属「发现成功前就置 ready + 吞异常」的行为变更，应由契约/审核侧定）。已在本报告留档，建议另开一条修：把 `_PROVIDERS_READY = True` 移到发现成功之后、失败不永久锁定。**如果审核把「74 passed」当稳定结论，请连同这条一起看。**

## 5. 未做 / 未验证

- 未接 B0b（矩阵 8 因子、canonical 元数据补齐）、未动 `matrix.py` / `registry.py` / `high_60d` / `low_60d`、未注册 `rsi_14_pct`。
- 未改 `docs/factors/README.md:50` 的旧指纹（19,588 B / `aa283b15…`）——该文件由因子工程师维护，不是我的文件；新指纹见本报告 §0，请其或文档管理员刷新。`docs/INDEX_20261107.md:101` 已是新值（20,821 B / `03700438…`，那是我 20:49 写入后的版本；此后我又改了 `:219` 的脚本路径，现值为 20,873 B / `d474fcc8a31a595b…`，**INDEX 也需要再刷一次**）。
- 4.6% 的四处外部出处未改（不是我的文件），只在 `:221` 留了指路。
- 未提交、未部署、未重启服务。
