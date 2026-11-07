# 独立审核：工作区现行字节（F-A43 落地 + 两处真红 + `_clean_registry`）

- 审核时间：2026-11-08 01:28–02:0x（Asia/Shanghai）
- 仓库：`C:/work/sourcecode/tick-stock-panel`，`HEAD = 286c1c862631042a2e9a43c57e9762c122e21f7f`
- 判据：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md`（269,092 B / 2,248 行，盘上 `d7df40ff…` 口径未变）
- 方式：只读审核。没改任何被审核文件、没提交、没部署、没重启；自建探针与临时 worktree 都在 `C:/Users/A/tsp_audit_20261108/` 下。

## 0. 结论摘要

| # | 事项 | 判定 |
|---|---|---|
| 1 | 439 passed / 0 failed 是否真、是否靠放宽 | **PASS（结果真）**：439/0/exit 0 原命令复现；断言层零放宽（0 skip/xfail、0 处 `==`→`>=`、0 条断言删除、`110` 断言全在）。**但**「红转绿」10 条中 8 条靠修测试顺序污染、2 条靠 schema+夹具，且 `test_matrix_strategy` 把被比较集合从 103 名缩到 86 名（见 §4） |
| 2 | `F-A43`–`F-A47` 逐条 | A43 **PASS** / A44 **PASS** / A45 **按字面 FAIL（条款自相矛盾，非实现缺陷）** / A46 **PASS** / A47 **部分**（A47-2 PASS，A47-4 不可判，A47-1/A47-3 的 HTTP 层不存在） |
| 3 | 两处真红修复 | #2（`max_length`）**PASS**；#1（`test_matrix_strategy`）**FAIL —— 是绕开，不是修好，且误排除 4 名** |
| 4 | `_clean_registry` 修法 | **有保留 PASS**：方向正确（只修本文件 teardown），但不是「只回滚本文件增删」，而是**整表静默回滚**，会掩盖本文件内的注册表变更；不能掩盖别人的泄漏（已实测） |

**两句准确措辞**：
- **「全量 `-k factor` 现在能不能宣称 0 红」→ 能，但只在这一条命令上成立**：439 passed / 0 failed / exit 0 原生复现；同一命令在 HEAD 上是 10 failed / 402 passed / exit 1。这不等于「因子面没有残留状态泄漏」——另有 5 条 110 断言对注册表前置破坏仍全红（§5.3）。
- **「干净检出能不能宣称全绿」→ 不能**。干净检出（HEAD 286c1c86）在因子面就有 10 红，全量本身也仍带我上轮实测的 49 红基线；本轮工作区只动了 5 个文件，无法覆盖那 49 条。**且 `docs/architecture/evidence/referenced_factor_inventory.json` 已入库、工作区无改动** —— 任务书里「仍未入库」的前提已失效（`git ls-files` 命中，`git diff HEAD -- <file>` 为空，最后修改提交 `484f81f3`）。

## 1. 锚点核对（全部命中）

| 文件 | 实测 | 任务书锚点 | 结论 |
|---|---|---|---|
| `backend/app/factors/gate.py` | 32,611 B / 758 行 / `6b59f7990ba5b336` / 00:38:09 | 同 | MATCH |
| `backend/tests/test_factor_gate.py` | 39,708 B / 924 行 / `08d46aac2026173f` / 00:50:19 | 同 | MATCH |
| `backend/app/api/backtest.py` | 64,729 B / 1,598 行 / `cebd2dbffdf4a4bf` / 00:38:50 | 同 | MATCH |

`git status --porcelain -- backend` 实测 **6 行**（任务书 5 行）：

```
 M backend/app/api/backtest.py
 M backend/app/factors/gate.py
 M backend/tests/backtest/test_matrix_strategy.py
 M backend/tests/test_auction_factor_pack.py
 M backend/tests/test_factor_gate.py
?? backend/MagicMock/            <-- 多出来的一行，测试残留产物（01:23 创建）
```

`backend/MagicMock/mock.app.state.repo.store.data_dir` 是一个**被创建出来的空目录树**：某条测试把 `MagicMock` 当路径传给了 `mkdir`，于是在仓库根写进了盘。属测试卫生缺陷（P3），不影响判据，但应在收口时清掉并补 `.gitignore`。

`git status --porcelain -- docs/architecture` 实测 8 行（5 M + 3 ??：`CONTRACT_REVISION_R12_20261107.md`、`..._v0.12.md`、`..._v0.13.md`）；`referenced_factor_inventory.json` **不在其中**（已入库、字节与 HEAD 相同）。

## 2. 命令与退出码实测

| 命令 | 实测 | 退出码 | 用时 |
|---|---|---|---|
| `cd backend && pytest tests -q -k factor`（工作区） | **439 passed, 4767 deselected**，8 warnings | **0** | 107.84 s（01:30:26→01:32:17） |
| 同上，在 HEAD 286c1c86 的干净 worktree | **10 failed, 402 passed, 4767 deselected** | **1** | 62.46 s |
| `pytest tests/test_factor_gate.py tests/test_auction_factor_pack.py tests/test_factor_registry.py tests/test_factor_store.py -q` | **113 passed** | **0** | 52.55 s |
| 两条真红单跑（`test_matrix_strategy::test_research_factor_catalog_matches_matrix_features` + `test_research_api::test_factor_batch_request_accepts_full_research_catalog`） | **2 passed** | **0** | 6.19 s |

**「隔离 4 文件 141 passed」复现不出来**：最自然的这 4 个文件实测 113。逐文件收集数：`test_factor_gate.py` 89、`test_auction_factor_pack.py` 6、`test_factor_registry.py` 11、`test_factor_store.py` 7 ＝ 113；加上 `test_research_api.py`(4) 或 `test_matrix_strategy.py`(30) 也凑不出 141（117 / 143 / 136 / 147）。**141 属未复现项**，请实现方给出确切的 4 个文件清单与命令。

HEAD 的 10 红名单与本轮完全一致，且分成两类：
- 真红 2 条：`test_matrix_strategy::test_research_factor_catalog_matches_matrix_features`、`test_research_api::test_factor_batch_request_accepts_full_research_catalog`
- 顺序污染 8 条：`test_factor_gate.py` 2 条（`test_real_disk_eight_alias_ids_...`、`test_real_disk_six_single_sided_pack_factors_are_not_aliases`）、`test_factor_registry.py` 5 条、`test_factor_store.py` 1 条

## 3. 「439 是否靠放宽」——`git diff` 逐处判定

改动规模：`backtest.py` 1/1、`gate.py` 144/21、`test_matrix_strategy.py` 36/2、`test_auction_factor_pack.py` 9/0、`test_factor_gate.py` 306/3。全仓只有这 5 个文件被动，`conftest.py` / `pytest.ini` / `pyproject.toml` **零改动**（没有全局 `filterwarnings`、没有 `--ignore`、没有 `-p no:randomly` 之外的花样）。

| 位置 | 改动 | 判定 |
|---|---|---|
| `backend/app/api/backtest.py:205` | `max_length=96` → `200`（注释 86→110） | **合法**。同一文件其余 `min_length`/`max_length` 一个没动（整个 diff 只有这一行），`min_length=1` 保留，`factor_names` 无其他约束被松 |
| `gate.py` 全量 | 新增 `namespace`（keyword-only，尾部追加）、`_namespace_faces`、`_column_verdict`、`_invalid_argument`；`ValueError`→`FS09`；`NotImplementedError`→`FS06`；`GateError.report` 允许 `None` | **合法**，均为 §7.17.3/§7.17.4 明文要求（C1–C5） |
| `test_factor_gate.py:391-400` | `pytest.raises(ValueError)` → `pytest.raises(GateError)` + `code=="FS09"` + `submitted_id=="mode"` | **合法修法、且更强**：契约 C4 明改语义；断言由「异常类型」升级为「类型+错误码+detail 键」（原断言只有类型）。但**字面违反 `F-A45-2`（该文件一字不改）** —— 条款冲突，见 §7 |
| `test_factor_gate.py:410-420` | `test_..._is_explicitly_not_implemented` 改名 + `NotImplementedError` → `GateError(FS06)` + `set(detail)==FS03_DETAIL_KEYS` + `report is None` | **同上：合法且更强**，同样字面违反 `F-A45-2` |
| `test_factor_gate.py:637-924`（新增 288 行） | F-A43–A47 逐条判据 | **未见放宽**：无 `skip`/`xfail`/`pytest.mark.skipif`；`==` 全保留；`len(untouched)==15`、`len(fallback)==14`、`len(exempt)==15` 都是等号；`NAMESPACE_NEGATIVE_IDS` 反向断言「4 名仍在活配置里」；有一处 `set(NAMESPACE_NEGATIVE_IDS) <= set(ids)` 是子集断言（用来钉「仍存在」，不是放宽结论） |
| `test_auction_factor_pack.py:78-105` | fixture 入口快照 + 出口 `clear()+update()` | **见 §5**：不是断言放宽，是状态修复；有掩盖风险 |
| `test_matrix_strategy.py:128-132` + `:165-194` | 新增 `_matrix_path_unsupported`，把「矩阵路径没实现」的 id 从对比集里剔掉 | **实质放宽（唯一一处）**：被比较集合 103 → **86**，且其中 4 名是误排除，见 §4 |

全局扫描（`git diff | grep '^+'`）：`skip|xfail|pytest.mark` 只命中 2 处 `pytest.mark.parametrize`（正常参数化）；`>=`/`<=` 零命中；`110` 只出现在注释里，`test_factor_registry.py:289/290/329/377`、`test_factor_store.py:88` 的 `== 110` **一个字没动**；`len(specs)==110` 未被改小。

## 4. 真红 #1 的修法：把 `in_universe` 排除掉 = 绕开

`test_matrix_strategy.py:131-132` 现在算的是：

```python
catalog_ids = {item["id"] for item in FACTOR_COLUMNS}          # 110
factor_names = catalog_ids - LINKAGE_FACTOR_IDS - _matrix_path_unsupported(catalog_ids)
```

`_matrix_path_unsupported`（`:165-194`）按「alias」+「provider 未覆写 `materialize_matrix*`」两类剔除。我独立复算（同一 110 个 id，同一探测条件）：

- alias 8 个：`ma120, ma200, prior_high_20, prior_high_250, prior_high_55, prior_low_10, prior_vol_20, vol60`
- provider-frame-only 9 个：`boll_lower, boll_upper, in_universe, ma20, ma60, month_end, prior_amount_20, sd20, week_end`
- 合计剔除 17，**被逐值对比的只剩 86 名**（110 − 7 linkage − 17）。

**其中 4 名是误排除**。我用**这条测试自己的夹具**（同一段 120×2 合成面板、同一 `build_market_data_matrix(..., field_columns={amount,turnover_rate,consecutive_limit_ups})`）直接调 `matrix_feature`：

```
in_universe        ValueError: unsupported matrix feature: in_universe
ma20               OK  (120,2)  nan=38
ma60               OK  (120,2)  nan=118
boll_lower         OK  (120,2)  nan=38
boll_upper         OK  (120,2)  nan=38
sd20               ValueError: unsupported matrix feature: sd20
prior_amount_20    ValueError: unsupported matrix feature: prior_amount_20
month_end          ValueError: unsupported matrix feature: month_end
week_end           ValueError: unsupported matrix feature: week_end
```

`ma20`/`ma60`/`boll_lower`/`boll_upper` 的矩阵路径**是通的**（走 `matrix_feature` 的通用 `ma<digits>` / 计算特征分支），它们此前一直在对比集里。把它们剔除，等于让这条测试**从此不再覆盖 4 个撞名因子**——正好是 `F-A44` 讨论的同一批 id。另外 5 名（`in_universe`、`sd20`、`prior_amount_20`、`month_end`、`week_end`）确实抛 `unsupported matrix feature`，剔除有依据。

对 `in_universe` 还需记一笔：HEAD 上那条红的原始报错是 `in_universe 缺少必需列 ['raw_close']`（`app/custom/research_universe_pack/universe.py:111`，frame 路径 fail-closed），**不是** `unsupported`。所以「补 `raw_close`/`st_history` 让 frame 路径算出来」这条路走不通：算出来以后 `matrix_feature` 会抛 `unsupported`，测试照样红。真实结论是**目录里有 110 名、矩阵路径只支持其中一部分**这一个能力缺口，原测试正是把它顶成红的那根针；现在的修法把这根针拔了（`_matrix_path_unsupported` 的 docstring 还写着「走到 `_compute_matrix_feature` 末尾必抛 unsupported」，对 `ma20/ma60/boll_lower/boll_upper` 这 4 名是**事实错误**）。

判定：**#1 FAIL —— 绕开，且附带误排除 4 名**。合规做法（择一，由架构师裁定）：把「矩阵路径不支持」的 id 数量与名单**显式断言在测试里**（例如 `assert len(unsupported)
