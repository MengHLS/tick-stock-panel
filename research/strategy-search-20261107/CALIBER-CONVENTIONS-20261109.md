# 计法口径登记（2026-11-09）：S01b 裁定 §5 的三条计法进台账

来源：策略经理 2026-11-09 裁定 —— 全文 `docs/research/S01B_RULING_20261109.md` §5，口径摘要 `docs/research/caliber-decisions-20261107.md` §23.5（v1.17）。由因子研究员按裁定落入台账。

本文件只记**计法**与**台账改动证据**。本轮**不新增登记、不动任何数值**：`global_N_lower_bound` 仍 19、`global_hypotheses` 仍 16、`global_N_exact` 仍 `null`。

## 1. 三条计法（自下一次对账起生效）

| id | 对象 | 计法 | 理由 |
|---|---|---|---|
| C-01 | ⑤-a 七单臂 + `base_nodefaults_gross` | **N +0（口径诊断）** | 量的是「生产文件未声明 `META.backtest_defaults`」时逐项开关/口径的移动，不是策略参数试验，不构成新的搜索宽度 |
| C-02 | `a2h`（peak=high） | **N +0（臂 2 的口径对照）** | 峰值口径对照，不是新增策略参数格；已在 `registrations[0].not_counted` 的「a2h 峰值口径对照」内 |
| C-03 | `block_limit_open=True` 若日后从「必写口径」升格为「策略选择」 | **须另立预注册 +1 格** | 升格即改变搜索对象（由补声明变为选参数）；不得援引「⑤-a 已测过」，也不得由 C-01 的 N +0 反推该格免计 |

边界（同轮裁定）：止损 −8% 的扩档（−15% / −20%）**不追加** ⇒ 本轮无新试验、N 增量 0。重开条件见 §23.4（仅当入场被改判「保留在研」时：只两档、只 10bp、只 MH60 无移动止盈、新预注册、一次定生死、N +2 格）。

口径冲突时的优先级：`caliber-decisions-20261107.md` §23 > 本文件；本文件 > 台账块的措辞（台账块指向 §23）。

## 2. 台账改动（唯一改动）

文件：`research/strategy-search-20261107/GLOBAL_LEDGER_v3.json`

新增**一个顶层块** `caliber_conventions`（插在 `policy` 与 `global_N_lower_bound_history` 之间），内容即上表三条 + `numbers_unchanged` 三格 + 生效方式 + 冲突规则。**纯追加**：无删除行、无既有字段改写。

未改：

- `global_N_lower_bound` = 19（`global_N_lower_bound_history` 仍 `[15, 19]`）
- `global_hypotheses` = `before 15 / delta 1 / after 16`（未动）
- `global_N_exact` = `null`（未动）
- `registrations[0]`（`S01b_ma_cross_20_60_risk_exit`）：`n_trials_delta 4`、`15→19`、`counted_configs` 四条、`not_counted` 五条，逐字未动
- `results/registry.json`：**整文件未动**（哈希不变）。全球计法属全局台账，不在批量局部 registry 里重复登记

## 3. 哈希（下游按此比对）

| 文件 | 改前 sha256 | 改后 sha256 |
|---|---|---|
| `GLOBAL_LEDGER_v3.json` | `18dd8e8a01206b98a98c7199366c4dacf8301780302b32aa3ff1081156349bdc`（= §21.4 记录值） | `9c0e3b4fc2ac4fd8d2672dde2bf48ee78c0d29ef144928f041b40509e3742a93` |
| `results/registry.json` | `ae7c99dcb0e8f780baaca16fbeb9a9df04d1707ab7240ebce9edfa73c498e93f` | 同左（未改） |

## 4. 核对（已实跑）

```bash
cd /c/work/sourcecode/tick-stock-panel && python -c "
import json,hashlib
p='research/strategy-search-20261107/GLOBAL_LEDGER_v3.json'
raw=open(p,'rb').read(); d=json.loads(raw.decode('utf-8'))
print(len(d), d['global_N_lower_bound'], d['global_N_exact'], d['global_hypotheses']['after'],
      [h['value'] for h in d['global_N_lower_bound_history']],
      [(r['id'],r['counting']) for r in d['caliber_conventions']['rules']],
      d['registrations'][0]['n_trials_delta'], d['registrations'][0]['n_trials_after'],
      hashlib.sha256(raw).hexdigest())"
```

实跑输出（UTF-8 终端）：`18 19 None 16 [15, 19] [('C-01','N +0（口径诊断）'),('C-02','N +0（臂 2 的口径对照）'),('C-03','须另立预注册 +1 格')] 4 19 9c0e3b4f…`

只增不改的证据：`git diff -U0 -- research/strategy-search-20261107/GLOBAL_LEDGER_v3.json | grep '^-[^-]'` 只列出两条，均属 11-08 17:25 那次 +4（`global_N_lower_bound: 15` → 19、`policy` 行补逗号），**本次编辑产生 0 条删除行**。

## 5. 未确证 / 没做

- 未确证：⑤-a 七单臂与 `base_nodefaults_gross` 的**读数**（+18.85pp / −8.67% 等）——本文件只登记计法，数值出自 `S01B_RULING_20261109.md` 与 `five_a/` 报告，我未重跑。
- 未做：未跑回测、未改策略文件与 `backend/`、未改 `results/registry.json`、未提交。台账改动只此一块。
