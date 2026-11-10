# P0-X 交付：单 id 多码去重（gate.py）

日期 2026-11-08 · 系统开发工程师 · 未提交 / 未部署 / 未接线

## 1. 改了什么

| 文件 | 改动 | 位置 |
| --- | --- | --- |
| `backend/app/factors/gate.py` | 新增 `_CODE_PRIORITY`（FS04=0 > FS03=1 > FS06=2 > FS01=3 > FS05=4）；`assert_factors_usable` 的聚合处（`:688` `top_code = min(verdict.codes, key=...)`）对同一 `submitted_id` 只往 `blocked` 写最高优先级一码；`_detail` 的 `status` 追加键只跟最终 `code` 走（仅 FS01 有）；`violations` 仅当 `blocked` 含 **≥2 个不同 id** 时出现（`:725` `len({item_id ...}) > 1`） | `gate.py:72-78`（`_CODE_PRIORITY` 常量）、`gate.py:685-690`（聚合）、`gate.py:722-729`（violations 门槛） |
| `backend/tests/test_factor_gate.py` | 新增 2 条**真盘**回归用例（不用合成源）+ 7 组组合键真盘用例 | `:933` `test_real_disk_single_alias_id_reports_only_one_code_and_exactly_seven_keys`、`:963` `test_real_disk_single_status_missing_id_reports_fs01_with_exactly_eight_keys`、`:987` 批量 violations、`:1029` 起组合键区（`:1059` 组 1、`:1132` 组 7） |

未改：`_column_universe`、`EXEMPT_KINDS`、`namespace` 面、`default_facts_source`、任何策略侧代码。

> **diff 归因**：`git diff --stat backend/app/factors/gate.py` 显示 237 行，但本批（P0-X）只动上面两处：
> `:686-689`（聚合去重）与 `:722-725`（violations 门槛），共 2 hunk。其余 15 个 hunk
> （`namespace` §7.17、`default_facts_source`、`_column_verdict` 等）是前几批已交但**尚未提交**的累积改动，
> 不属于本批，也不在本批验收范围内。

## 2. done_when ① 实测

复跑脚本：`research/gate-dedup-20261108/verify_gate_dedup.py`
证据：`research/gate-dedup-20261108/logs/run_final_1.json` / `run_final_2.json`
（跑在 gate.py 最终版 mtime 05:00:09 之后；04:39 那对 `run_A.json`/`run_A2.json` 已被取代，保留不删）

```
sha256  476cd0e7d37990e6a4dafdd255d2ee028d87061cf04b7a24f24abd35bea797c3  5056 B  (两次连跑相同)
verdict PASS   6/6
```

| 判据 | 输入（真盘 `RegistryFacts(D:/TSP/data)`，`mode="production"`） | 实测 |
| --- | --- | --- |
| D1 | 单 `vol60` | `code=FS03`，`blocked=(('vol60',None,'FS03'),)` **长度 1**，`detail` **恰 7 键**（code/mode/submitted_id/resolved_id/canonical_id/table_row/message），`violations` 不出现、`status` 不出现 |
| D2 | 单 `ma20` | `code=FS01`，`blocked` 长度 1，`detail` **恰 8 键**（7 键 + `status`） |
| D3 | `uf_vol60` | `blocked=()` → 放行 |
| D4 | `vol60` + `ma20` 同批（两个**不同** id） | `violations` 出现，2 条：`vol60→FS03`、`ma20→FS01` |
| D5 | 优先级表 | `FS04 > FS03 > FS06 > FS01 > FS05` |
| D6 | 全程可达码 | `FS01/FS02/FS03/FS04/FS05/FS06/FS09` 都能被产出 |

## 3. 回归

```
backend/.venv/Scripts/python.exe -m pytest tests/test_factor_gate.py -q
→ 116 passed, 1 warning    (exit 0；连跑 3 次均 116)

backend/.venv/Scripts/python.exe -m pytest tests -k factor -q
→ 466 passed, 4769 deselected, 8 warnings in 90.06s    (exit 0, PYTEST_EXIT=0)

注：本报告初稿写 107 / 457 时，这 9 条真盘组合键用例（组 1–7 等）尚未写入；
107→116 的差量与 457→466 的差量同为 9，是同一批新增，不是回归。
```

两条真盘用例单独跑（确认未被 skip）：

```
pytest tests/test_factor_gate.py::test_real_disk_single_alias_id_reports_only_one_code_and_exactly_seven_keys \
       tests/test_factor_gate.py::test_real_disk_single_status_missing_id_reports_fs01_with_exactly_eight_keys -v -rs
→ 2 passed    （skip 条件为 D:/TSP/data 是否存在，本机命中，真跑）
```

## 4. 与契约的差异（不改契约，只登记）

契约 v0.15 §7.16.4 的组合键表缺「≥2 个不同 id 被拦但其中至少一个 id 多码」的行。实测形态：

| 场景 | detail 键数 | 键集合 |
| --- | --- | --- |
| 单 id 一码（FS03） | 7 | 基础 7 键 |
| 单 id 一码（FS01） | 8 | 7 + `status` |
| 单 id 多码（FS03 优先） | **7** | 基础 7 键（`status` 不出现，因最终 code 是 FS03） |
| ≥2 个**不同** id 被拦，均单码 | 8 | 7 + `violations` |
| ≥2 个不同 id，其中含 FS01 | 9 | 7 + `status` + `violations`（两键正交并存） |
| 触发 FS04（双 canonical） | 8 | 7 + `dual_ids`；`violations` 不出现（`_guard_dual_id` 在 violations 计算前抛） |

`status` 与 `violations` **正交**：前者跟最终 `code` 走，后者跟「≥2 个不同 id」走。已派架构师进 v0.16。

## 5. 非我方产物（只登记，未删、未认领）

| 路径 | 现状 | 归属 |
| --- | --- | --- |
| `nul` | **不存在**（`ls` 报 No such file） | 非我产物 |
| `backend/tests/test_zz_probe_tmp.py` | 源码**已不存在**，只剩 `backend/tests/__pycache__/test_zz_probe_tmp.cpython-311*.pyc` | 非我产物；不是我删的 |
| `.factor_engineer_batch/` | 存在，`snap_20261108/` 下 15 个 json 快照 | 非我产物 |

三项目前均未参与本批任何判据；`test_zz_probe_tmp.py` 源码不在盘上，所以不进 `pytest tests -k factor` 的采集。
