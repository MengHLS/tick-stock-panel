# 策略准入规约（因子化）v1 — 2026-11-07

状态：**v1，可执行判定规约 + 12 条策略逐条准入结论 + S 级注册批次建议**。作者：因子工程师。
边界：本文件只做准入判定与批次建议；**不含实现代码、不改 `backend/app/**`、不含任何收益数字**。
上游依赖：`FACTOR_REGISTRY_CORE_93_20261107.md`（台账）、`STRATEGY_INPUT_FACTOR_MAP_20261107.md`（映射）、`FACTOR_GAP_SPEC_20261107.md`（缺口 v1）、`evidence/*.json`（机器证据）。
数字时点（2026-11-07 17:10）：§1、§2.6 的「178 个注册因子」是 14:17 的实测值；批 A 的 14 个已由 B0 当日注册，`all_factors()` 现为 **192**（`evidence/registration_b0_20261107.json#step5_idempotent.total_factors_after`；实现 `backend/app/custom/research_factor_pack/factor_specs.py`）。**判据类引用已就地改为 192**（§2.5 情形 11、§2.6 实测表、§5.3）；纯历史叙述保留 178 并标时点。

**修订记录（本文件 v1，2026-11-07 17:11）**：①§2.6 增「定义 2.6-1（`base` 两义：指标列 vs 基础因子）」并补「B0 后状态」；②§2.5 情形 11 / §2.6 实测表 / §5.3 的 178 就地改为 192（178 作时点值保留）；③§4.2 `vol60` 定义改写为与**研究侧**代码一致的减法式（研究 `COMMON:126` 用 `pct_change()`；旧手写 `close/ts_delay-1` 有 1 ULP 差，全帧 `max_abs_diff=1.1102e-16` / 非零差 4,214,876 行 / 超 1e-12 行 0，B0 减法式 `0.0`）。**（17:5x 再改）** 本条「逐位一致」只对研究侧成立，对 canonical `uf_vol60` 不成立，已按 ⑦ 改为容差口径；④§0-结论 2 / §5.4 / §6-2 的 X2 表述统一为「扩展包已实现（有条件生效）、核心默认路径无同一语义」，并更正数据根与实机证据（原「`data/user_data/extensions` 不存在」有误）；⑤§6-1 只登记「D4 已被独立审核占用」这一事实，不编号、不裁定。对应 GAP 侧：`FACTOR_GAP_SPEC_20261107.md` v1.2（§3-E2 把研究选股数降为旧口径诊断参照、旧集合 = 「全样本名次 ≤ `t×P`」∩ 池子）。**（17:26 补）** ⑥§8 末句由「建议下一份文件 `FACTOR_GAP_SPEC_v2`」改为**就地修订清单**（按开发经理指令：只改这两份已有文件，**不新增第三份文档**），并删除已结清的 X2 待办。**（17:5x 补，本轮）** ⑦§2.1 R1 改按 canonical id 判（`ID-CANON-1`：8 组双 id 只许 `uf_*`），判据集合分 import 态 192 / 启动态 207 两个时点；同段加 `vol60` 容差句（`uf_vol60` 与研究侧 `pct_change()` 是 `max_abs_diff=1.11e-16` 的容差等价，**不得写「逐位相同」**，判据只取 `F-A3` 的 `<1e-12`）；R3 与批 A1 验收的「逐位比对」同改按 `F-A3`。⑧§6-1 两条按裁改：`market_breadth` 掩码**已裁不立号**（`D4` 空号，`caliber-decisions §10.1`）；`in_universe` 的 ② 由「`COMMON:184` 把 null 折 False」改为**两处真实差异**（2a `:179` ST 宽容走 `treat_non_st`；2b `st_history` 于 `2026-10-20` 写 198 行 False 致 14 个交易日不可判），并更正「`:184` 是注释行」的记法——`:184` 实为 `fill_null(False)` 代码行、注释在 `:185`/`:192`。⑨四处原占位处已按裁清零（`:262` 汇总行、`:344` 判定行、§6-1、§8；行号为 17:11 版，现文见下 ⑫）。**（18:0x 补，本轮末）** ⑩ R1 补「机制未实现」事实：`alias_of` / `FS03` / `assert_factors_usable` / `strategy_usable` 在 `backend/app/**` 各命中 **0**、`FactorSpec` 无这三字段，故 canonical 判定现只能靠台账人工核对，不得写成「生产入口自动拒 alias」；⑪ §8 由两项改三项，第三项即该引擎缺口。

本文件确立的唯一新规则：

> **策略提交物 = 「已注册因子 id + 参数 + 声明式执行约束」的 JSON。**
> 任何需要新写代码（Python / polars / 自定义算子 / 策略内 `compute_signals`）才能表达的条件，一律判「缺能力」并退回，**不得用近似因子糊过去**。

---

## 0. 一页结论（先看这五条）

| # | 结论 | 证据 |
| --- | --- | --- |
| 1 | **12 条策略今天 0 条**能以「已注册因子 + 参数」完全确定；但最省的一步不是改引擎，而是**注册 14 个因子**（批 A）。 | §3.1、§4 |
| 2 | 批 A（14 个因子 = **10 个表达式 + 4 个直通**，其中 A1 的 9 个先做）落地后，**S01 / S02 / S05 / S09 的因子侧清零**，只剩 `in_universe`（E3）。持有期上限（X2）不是因子；扩展包已实现、但有条件生效，生产默认路径未启用（§5.4）。 | §4 批 A1/A2「解锁」列 |
| 3 | **在策略表达式里写不出**的只有 3 类：`month_end`/`week_end`（7 条，E4）、`rsi_14_pct`（S04）、`market_breadth`（S12）。但正解都不是加 DSL 算子——前两者补日历/基座列，`rsi_14_pct` 注册 base 因子；**唯一必须动算子层的只有 E2（掩码 `rank`）**。其余「缺」是未注册或口径未定，不是语言不足。 | §2.7 划界表；实测命令 §7 |
| 4 | 台账口径的「可直接复用」有 7 行其实**引用不到**：`ma20`/`ma60`/`boll_lower`/`boll_upper` 是指标层现成列，`sd20` 连指标列都没有（`capability.present_sd20=false`），以上都不在 178 个注册因子里（14:17 时点）→ DSL 编译直接 `E001 未知标识符`。**B0 已注册其中 5 个**（`ma20`/`ma60`/`boll_lower`/`boll_upper`/`sd20`，17:14 实测 `compile_formula` 均 `True []`），现仍为指标列的只剩 `high_60d`/`low_60d`/`vol_ma5`/`vol_ma10`。 | §2.6；`backend/app/factors/dsl.py:30-33,588` |
| 5 | 复核发现 7 处与起点事实不一致（§5）。影响排期的三条：**缺口是 19 项不是 20 项**；**X2 生产侧已由 `app/custom/paper_execution` 实现**；**X1 组合级轮动不是这 12 条策略复现的硬前置**。 | §5 |

---

## 1. 起点事实自核（对着 `evidence/*.json` 逐条复算）

| 起点事实（@开发经理 给的） | 我的复核 | 结论 |
| --- | --- | --- |
| `docs/factors/` 有 4 份文档 | `ls`：`FACTOR_GAP_SPEC_20261107.md` / `FACTOR_REGISTRY_CORE_93_20261107.md` / `README.md` / `STRATEGY_INPUT_FACTOR_MAP_20261107.md` | **复核一致**（4 份，不含本文件） |
| `evidence/` 5 份机器证据 | `compare_stats.json`(1331 行) / `factors_inventory.json`(3340) / `factors_inventory_core93_20261107.csv`(93 数据行) / `strategy_factor_map.json`(455) / `xs_rank_stats.json`(80) | **复核一致** |
| `FACTOR_GAP_SPEC` 共 **20 项** | 总表实测 **19 行**：D 3 + F 7 + E 4 + X 2 + G 3 = 19 | **不一致**：19 项，非 20（§5.1） |
| 12 条策略映射：可复用 16 / 口径不一致 6 / 系统缺失 23 | `strategy_factor_map.json#counts` = `{"可直接复用":16,"口径不一致":6,"系统缺失":23,"—":1}`，字面一致；但 `counts` 把 `sideways` 5 行并入：16 = 策略内 14 + 横向 2；23 = 策略内 20 + 横向 3（这 3 条与策略内条目重复）；另有 1 行标 `—` 非缺口（§5.2） | **数字一致，口径需注明** |
| `high_60d` 在 547 万行里 `close > high_60d` 一次都不成立 | `compare_stats.json#signals.s09_break_vs_high_60d`：`n=5470011, both_true=0, only_a=143747` | **复核一致** |
| S06/S07/S10/S11 选股 jaccard 0.319/0.178/0.298/0.049 | `xs_rank_stats.json#xs_rank.*.mean_jaccard` = 0.319454 / 0.177812 / 0.297662 / 0.048851 | **复核一致**（4 位小数） |
| 平均选股数 研究 55.5 vs 系统 307.2（S07） | `xs_rank.S07_vol60_le_0.10`：55.4886 / 307.2159 | **数字复核一致**（55.5 / 49.7 / 92.8 / 14.7 是旧口径诊断参照，不是靶值；口径见 GAP §3-E2） |
| market_breadth 0.5407 vs 0.4643，翻转 19.1%，月末 53.4% vs 34.1% | `xs_rank_stats.json#market_breadth`：0.5407417 / 0.4642690 / 0.1911186 / 0.5340909 / 0.3409091 | **复核一致** |
| `vol60` 年化后仍不可替代，平均绝对差 0.092；低波十分位 jaccard 0.136 | `pairs.vol60_ann_vs_annual_vol_20d.mean_abs_diff`=0.091912；`vol60_substitution.mean_jaccard`=0.135620 | **复核一致** |
| `rsi_14` 差 0.892 个 RSI 点 | `pairs.rsi14_vs_rsi_14.mean_abs_diff`=0.892244 | **复核一致** |
| `ma120` 站上占比 46.8%（交叉检查值） | `series.ma120_bias_ref.share_above`=0.468053 | **复核一致** |

> 复核方法：只读 JSON + 只读 import 注册表与 DSL 编译器（命令见 §7），未改任何文件。

---

## 2. 策略准入规约

### 2.1 三条硬规则

| 规则 | 内容 | 判定手段（机械） |
| --- | --- | --- |
| **R1 引用闭合** | 提交物里出现的每个因子 `ref` 必须是「**canonical** 已注册因子 id」或「基础列」，不接受 alias、不接受「系统里有这个词」 | **以 canonical id 为准**（`ID-CANON-1`，`docs/architecture/ARCH_DECISION_FACTOR_ID_CANONICAL_20261107.md` §2.1）：8 组双 id 只能写 `uf_*`（`uf_vol60`/`uf_ma120`/`uf_ma200`/`uf_prior_high_20`/`uf_prior_high_55`/`uf_prior_high_250`/`uf_prior_low_10`/`uf_prior_vol_20`），pack 侧裸 id 是 alias（`alias_of` + `strategy_usable=false`，只作研究对照、生产入口 `FS03` 拒）；6 个单 id（`ma20`/`ma60`/`sd20`/`boll_lower`/`boll_upper`/`prior_amount_20`）本身就是 canonical。**这条裁定目前只存在于文档与台账，机制未实现**：契约 v0.6 `:1020` 明写 `alias_of` / `FS03` / `assert_factors_usable` 在 `backend/app/**` 命中 **0**；本轮实测注册表 `FactorSpec` 的 21 个字段里**没有** `alias_of` / `canonical_id` / `strategy_usable`（`get_factor("vol60")` 三者全 `<absent>`）。故 R1 的 canonical 判定**现在只能靠人/台账核对**（`docs/factors/evidence/f_class_registry.json#id_canonical_ruling`，`ID-CANON-1`），不能写成「生产入口会自动拒 alias」；机制落地属引擎缺口（E 类），不在本文权限内。**判据集合要分两个时点、两时点都报数，但闸门只按 ② 判**（两时点都过是不可能的：①里 8 个 canonical 根本不存在）：①**import 态** `all_factors()` = **192**（pack 14 + 既有；8 个 canonical **0/8**、8 个 alias **8/8**、6 个单 id canonical **6/6**）——此态只能做「alias 是否混入」的负向检查，不能做 canonical 闭合判；②**启动态** `load_into_registry(D:\TSP\data)` 后 = **207**（+14 `uf_*` +1 `cf_*`）——8 个 canonical **8/8** 到位，**R1 闭合判只在此时点成立**。（实测命令见 §7.1b。）此外 `BASE_COLUMNS` 9 列恒可引用 |
| **R2 零代码** | 条件只能写成因子表达式（注册因子 + 25 个 DSL 算子，实测 `len(OPERATORS)=25`），不得附 Python/polars 片段、不得要求新增算子 | `compile_formula(expr).ok`；`E001`=引用不闭合，`E002`=算子不存在 |
| **R3 语义显式** | 每个因子必须声明 `shift` / `includes_today` / `price_basis` / `window` / `unit` / `warmup`；每个执行约束（调仓日、持有期、容量、成交价、涨跌停）必须显式，不得默认 | 台账字段齐备 + 与研究侧定义按契约 `F-A3` 比对（`max_abs_diff < 1e-12`，另报 `n` / `jaccard`） |

**核心判据**：只靠「已注册因子 + 参数」是否足以**完全确定**这条策略（入场、出场、排序、选股集合、调仓日、持有期、容量、成交价）。任何一项确定不了 → 不准入。

**R1 的数值伴随条件（`vol60`）**：canonical `uf_vol60`（store 侧，`ts_std(close / ts_delay(close, 1) - 1, 60)`）与研究侧 `COMMON:126` 的 `pct_change()` 是**容差等价、不是逐位等价**——`max_abs_diff=1.1102e-16`、非零差 4,214,876/5,469,335 行、超 1e-12 行 **0**（`evidence/F_CLASS_PARITY_20261107.json#factor_parity.uf_vol60`）。故引用 canonical 时判据只能写 `max_abs_diff < 1e-12`（`F-A3`），**不得写「逐位相同」**，也不得把 `1.11e-16` 当门槛。另注：研究侧 `pct_change()` 与减法式 `(x - x.shift(1)) / x.shift(1)` 实测**逐位相同**（8 值探针 `max_abs_diff=0.0`），所以 §4.2 的减法式只对「研究侧」成立，对 canonical 不成立。

### 2.2 最小提交物 JSON（`factor-strategy/1.0`）

```json
{
  "schema_version": "factor-strategy/1.0",
  "strategy_id": "S02_donchian_20_10",
  "title": "唐奇安 20 日突破 / 10 日退出",
  "version": "v1",
  "frozen_at": "2026-11-07",
  "research_spec": {
    "path": "research/strategy-search-20261107/scripts/common.py",
    "lines": "229-231,296-297",
    "frozen": true
  },
  "universe": {
    "mask_ref": "factor:in_universe",
    "mask_params": {},
    "null_handling": "fill_false"
  },
  "factors": [
    {"ref": "factor:prior_high_20", "alias": "ph20", "params": {}},
    {"ref": "factor:prior_low_10",  "alias": "pl10", "params": {}},
    {"ref": "factor:momentum_20d",  "alias": "ret20", "params": {}}
  ],
  "conditions": {
    "entry": {"expr": "close > ph20", "lang": "factor_dsl"},
    "exit":  {"expr": "close < pl10", "lang": "factor_dsl"},
    "score": {"expr": "ret20", "order": "desc"}
  },
  "selection": {
    "mode": "per_symbol_gate",
    "rank_ref": null,
    "threshold": null,
    "capacity": "max_positions"
  },
  "rebalance": {"calendar_ref": null},
  "holding": {"max_hold_days": 60, "exit_priority": ["signal", "risk", "max_hold", "end"]},
  "execution": {
    "entry_price": "next_open",
    "price_basis": "raw",
    "block_limit_open": true,
    "max_positions": 10,
    "max_exposure_pct": 1.0,
    "costs_ref": "account:default"
  },
  "risk": {"stop_loss": null, "trailing_stop": null},
  "evidence": {
    "numeric_fidelity": [
      {"factor": "prior_high_20", "max_abs_diff": null, "n": null, "jaccard": null,
       "status": "pending_registration"}
    ]
  },
  "admission": {
    "verdict": "缺因子",
    "gap_refs": ["F4", "F5", "D1", "D3", "E3"],
    "decided_by": "因子工程师",
    "decided_at": "2026-11-07"
  }
}
```

**字段规约**

| 字段 | 必填 | 取值 / 枚举 | 谁填 | 说明 |
| --- | --- | --- | --- | --- |
| `strategy_id` / `version` | 是 | 与策略库一致 | 研究侧 | `version` 变更须重新准入 |
| `research_spec.path` + `lines` | 是 | 文件路径 + 行号区间 | 研究侧 | 冻结口径的**唯一**依据，防止口头口径 |
| `universe.mask_ref` | 是 | `factor:<id>` 或 `null` | 因子工程师 | `null` 时必须写 `reason`，且该策略只能判「近似」 |
| `factors[].ref` | 是 | **已注册因子 id** | 因子工程师 | 不接受 `ma20` 这类指标列（§2.6） |
| `conditions.entry` / `.exit` | 是 | factor_dsl 表达式 | 研究侧起草 + 因子工程师验 | `exit` 可为 `null`（仅靠持有期/调仓退出），但必须声明 `holding` |
| `conditions.score` | 是 | 表达式 + `order` | 研究侧 | 无排序需求时写 `{"expr": null, "order": null}` |
| `selection.mode` | 是 | `per_symbol_gate` / `cross_section_rank` / `top_n` | 因子工程师 | `cross_section_rank` 必须配 `rank_ref` |
| `rebalance.calendar_ref` | 条件必填 | `factor:month_end` / `factor:week_end` / `null` | 因子工程师 | 研究侧按日历调仓则**不得**为 `null` |
| `holding.max_hold_days` | 是 | 正整数 / `null` | 研究侧 | 与 `research_spec` 一致 |
| `execution.*` | 是 | 见枚举 | 研究侧 + 复盘 | 与 `MatcherConfig` 语义对齐 |
| `evidence.numeric_fidelity[]` | 是 | `max_abs_diff` / `n` / `jaccard` | 因子工程师 | 空值=未验收，**不得**填 0 冒充 |
| `admission.verdict` | 是 | 见 §2.4 | 因子工程师 | 终判，不可由研究侧自填 |

### 2.3 判定算法（六步，fail-closed）

```text
1 引用闭合：每个 factors[].ref ∈ 192 注册因子（B0 后；判据不锁 178）；每个 expr 的每个标识符 ∈ (192 ∪ 9 基础列)。
     失败 → 「缺因子」，写明缺哪个 id。
2 语法闭合：compile_formula(expr).ok == True。
     E001(未知标识符) → 回 1；E002(算子不存在) → 「缺引擎能力」。
3 语义保真：每个 ref 有实测 max_abs_diff / n / jaccard；无证据或超阈值 →
     「需口径决策」；用近似因子替代 → 直接退回。
4 掩码闭合：研究口径为「池内排名」的 rank/zscore，必须带 mask_ref；
     否则 → 「缺引擎能力」(E2)。
5 执行闭合：rebalance / holding / selection / execution 五项齐全且与 research_spec 一致。
     缺调仓日 → E4；缺持有期 → X2；缺截面选股/容量 → X1。
6 终判：verdict = 最高优先级的阻塞项（缺引擎能力 > 缺因子 > 需口径决策），
     同时列全部 gap_refs；任一步 fail → 不准入，不得「先上线再补」。
```

### 2.4 判定枚举

| verdict | 含义 | 处置 |
| --- | --- | --- |
| `可表达` | 六步全过 | 进策略库，走回测/影子 |
| `缺因子` | 引用了不存在或未注册的因子 | 并入注册批次（S 级优先） |
| `缺引擎能力` | 语言层无法表达（算子/掩码/聚合/日历） | 写缺口规格 → 架构契约 → 实现 → 独立审核 |
| `需口径决策` | 系统有近义因子但口径不同，或研究侧定义未冻结 | 出决策记录（D 项），**拍板前不准入** |
| `退回（不可表达）` | 见 §2.5 | 退研究侧，不排期 |

### 2.5 直接判「不可表达、退回」的 12 种情形

| # | 情形 | 判据 | 典型 |
| --- | --- | --- | --- |
| 1 | 附代码 / 伪代码作为条件 | 提交物含 Python、polars 链、`compute_signals` | 研究侧现有 12 条策略的 `.py` 形态本身**不能**作为提交物 |
| 2 | 引用未注册标识符 | `E001` | `ma20`、`boll_lower`、`high_60d`、`vol_ma10` |
| 3 | 要求新算子 | `E002` 或 `OPERATORS` 里没有 | `ewm_mean`（Wilder RSI）、任何 `ffill/bfill` |
| 4 | 要求按日全市场聚合 | DSL 只有逐行算子 + 截面 rank/zscore/winsorize | `market_breadth` |
| 5 | 要求日历函数 | DSL 无日期函数 | `month_end`、`week_end`、交易日序号 |
| 6 | 要求掩码截面排名而 rank 无掩码参数 | `dsl.py:506-508` 分母 = 全样本非空数 | `rk_ret5`、`rk_vol60` |
| 7 | 用近似因子顶替 | 无 `max_abs_diff=0` 证据，或 jaccard < 1 | 用 `high_60d` 顶 `prior_high55`（jaccard 0.000） |
| 8 | 无冻结口径出处 | `research_spec.path` 缺失、或 `frozen != true`、或无行号区间 | 只给一句「月度低波」而不给 `common.py` 行号 |
| 9 | 执行约束缺项且未声明默认 | 调仓日 / 持有期 / 成交价 / 容量 / 成本任一为空且无 `reason` | 写「月度调仓」但 `rebalance.calendar_ref = null` |
| 10 | `universe.mask_ref` 为 `null` 且无 `reason` | 同上 | 口头「剔除 ST」但提交物无掩码引用 |
| 11 | 拿**指标列名**冒充因子 id | 不在 **192** 注册因子 ∪ 9 个基础列（`dsl.py:30-33,588`；192 = 14:17 的 178 + B0 批 A 14） | `ma20`、`boll_lower`、`high_60d`（§2.6 的 7 行） |
| 12 | 要求改**既有**因子语义 | 提交物要求「把 `high_60d` 改成 high 价 / 改成此前」 | D1 的旧路径；正解是新增 `prior_*`（批 A），**既有因子一律不动** |

### 2.6 地基问题：台账「可直接复用」的 7 行，在 DSL 里引用不到

实测（`backend/.venv/Scripts/python.exe`，只读 import，命令见 §7）：

| 事实 | 实测值 | 来源 |
| --- | --- | --- |
| 注册因子总数 | **178**（14:17 实测）→ **192**（17:10 复核，+14 = B0 批 A） | `all_factors()` → `len=178`（14:17）；B0 登记后 `total_factors_after=192`（`evidence/registration_b0_20261107.json#step5_idempotent`）；`backend/app/factors/registry.py:384` |
| DSL 基础列 | **9**：`open high low close volume amount turnover_rate prev_close raw_close` | `backend/app/factors/dsl.py:30-33` |
| DSL 算子 | **25**（13 时序 + 3 截面 + 9 逐元素），**无 `ewm`、无日期函数、无按日聚合** | `backend/app/factors/dsl.py:43-70`；`compile_formula('ewm_mean(close,14)')` → `E002 未知函数` |
| `ma20`/`ma60`/`boll_lower`/`boll_upper`/`high_60d`/`low_60d`/`vol_ma5`/`vol_ma10` | **14:17 时既不在 178，也不在 9 个基础列**（`ma20`/`ma60`/`boll_lower`/`boll_upper`/`sd20` 已由 B0 注册，见下方「B0 后状态」） → 当时 `compile_formula('ma20 > ma60')` 返回 `E001 未知标识符: ma20`、`: ma60` | `dsl.py:588-589` |
| `sd20` | 连指标列都不是：`capability.present_sd20 = false`；等于 `(boll_upper-boll_lower)/4`（`pairs.sd20_vs_implied_sd.max_abs_diff = 0`，n=5,497,082） | `evidence/compare_stats.json#capability`、`#pairs` |

**受影响的行（7 行）**：S01[`ma20`,`ma60`]、S03[`ma20`/`ma60`]、S05[`bb_lower`/`bb_upper`、`sd20`、`ma20`]、S09[`ma20` 出场]。

**根因是术语两义**（定义见下；本节起一律按此用词，映射表与台账撞名时以本定义为准）：

**定义 2.6-1（`base` 两义：指标列 vs 基础因子）**

| 术语 | 唯一合法用法 | 判据（可机器判） | 不得写成 |
| --- | --- | --- | --- |
| **指标列**（indicator column） | 「`compute_indicators` 输出的现成列」 | 在 `capability.compute_indicators_columns`（28 列）里，且**不在** `all_factors()` 的 id 集合里 | `base` / 「基础因子」 |
| **基础因子**（`kind='base'`） | 「注册表里 `kind='base'` 的**可引用因子 id**」 | 在 `all_factors()` 里、注册表 `kind` 字段 = `base`，且 `compile_formula(名字)` 能解析 | 「指标列」/「现成列」 |

算子化判据：一个名字若 `compile_formula(名字)` 返回 `E001 未知标识符`，就**不是**因子 id —— 它要么是指标列、要么根本不存在，两种都不可引用。实测：`capability.compute_indicators_columns` 列出 28 列，`ma20`/`ma60`/`boll_lower`/`boll_upper`/`high_60d`/`low_60d`/`vol_ma5`/`vol_ma10`/`rsi_14` 都真实存在，但只有 `rsi_14` 与 `momentum_*` 进了注册表。历史成因：映射表把前者写成 `base`，与注册表的 `kind='base'` 撞名；本文一律按本定义区分。另注：「可引用 id」不止 `kind='base'`——实测 `all_factors()` 192 = `base` 117 + `virtual` 61 + `custom` 14（`backend/.venv/Scripts/python.exe` 只读 import，2026-11-07 17:10），B0 新注册的 14 个是 `custom`。本定义只划「列 vs id」，不按 `kind` 分档。

**后果（14:17 判定，B0 后已关闭）**：这 7 行当时不是「可直接复用」，而是「**数值保真已证、因子未注册**」。好消息是修复成本极低——`pairs.ma20_research_vs_system` / `ma60_…` / `bb_lower_vs_boll_lower` / `bb_upper_vs_boll_upper` 的 `max_abs_diff` 全为 **0.0**，注册即保真。**注册动作优先于任何引擎改动**。

**B0 后状态（2026-11-07 17:10 复核）**：本节 8 个 id（`ma20`/`ma60`/`boll_lower`/`boll_upper`/`sd20` 及批 A 其余）**已全部注册**——`evidence/registration_b0_20261107.json#step5_idempotent.versions_after` 逐名 = 1、`total_factors_after = 192`；`compile_formula` 不再返回 `E001`。本节因此降级为「术语定义 + 判据来源」，登记动作已由 B0 完成；**不得**再按「未注册」重跑一遍，也不得据此新增因子 id 或改动既有语义。

### 2.7 划界：什么算「缺因子」，什么算「缺引擎能力」

这条界必须写死，否则一切都会被推成「缺引擎能力」，排期会假性膨胀。

| 类别 | 判据 | 代价 | 走哪条流程 | 本文件的例子 |
| --- | --- | --- | --- | --- |
| **表达式因子** | 可由 9 个基础列 + 25 个算子组合，窗口/shift 为常量，**参数化维度 = 1** | S | 因子注册（本文件出定义 → 系统开发工程师实现） | `sd20`、`prior_high_20`、`vol60`、`ma120` |
| **直通因子** | 指标层已经算好，只需暴露为可引用 id | S | 同上（无新算法） | `ma20`、`ma60`、`boll_lower`、`boll_upper` |
| **基座因子** | 需指标层/扩展层计算：`st_flag` 接入、交易日计数、全市场按日聚合 | M | 同上 | `in_universe`（E3） |
| **引擎能力** | 需要策略侧**参数化**（`rank(x, mask)`：x 与 mask 都由策略给），或涉及**执行时序**（组合级调仓、容量、持有期） | M–L | 缺口规格 → 架构契约 → 实现 → 独立审核 | E2 掩码 `rank`、X1 执行器 |
| **口径决策** | 系统有近义量但定义不同，或研究侧定义未冻结 | S（无代码） | 决策记录（D 项）；**拍板前不准入** | D1、D2、D3 |

一句话判据：**参数化维度 = 1 → 因子；≥ 2 或涉及时序 → 引擎能力。**

两个派生结论（会直接改排期，见 §5）：

1. **E4（`month_end`/`week_end`）不是算子问题**。它是「按交易日历算出的日级布尔」，口径唯一、无策略参数。难点只在因子框架是否接受「日级」列（跨 symbol 广播），属 S–M 实现细节，不是新 DSL 算子。回测侧 `backend/app/backtest/factor.py:54`（`rebalance: Literal["daily","weekly","monthly"]`）与 `:1121-1164`（真实调仓日推算）**已经实现**，所以 E4 只挡「因子化准入」与「生产侧一致」，不挡回测复现。
2. **`rsi_14_pct` 不需要新算子**。DSL 没有 `ewm`（`E002`），但它口径唯一（Wilder，alpha=1/14），注册成 base 因子即可，不必让策略侧写 `ewm`。§2.5 情形 3/4/5 说的是「**在 `conditions.expr` 里直接写**就退回」——正确路径是提因子注册需求，不是把算子塞进策略。

---

## 3. 12 条策略逐条准入

### 3.0 证据路径缩写（全部为绝对路径）

| 缩写 | 绝对路径 |
| --- | --- |
| `MAP` | `C:/work/sourcecode/tick-stock-panel/docs/factors/evidence/strategy_factor_map.json` |
| `CMP` | `C:/work/sourcecode/tick-stock-panel/docs/factors/evidence/compare_stats.json` |
| `XS` | `C:/work/sourcecode/tick-stock-panel/docs/factors/evidence/xs_rank_stats.json` |
| `REG` | `C:/work/sourcecode/tick-stock-panel/backend/app/factors/registry.py` |
| `DSL` | `C:/work/sourcecode/tick-stock-panel/backend/app/factors/dsl.py` |
| `COMMON` | `C:/work/sourcecode/tick-stock-panel/research/strategy-search-20261107/scripts/common.py` |
| `SPEC` | `C:/work/sourcecode/tick-stock-panel/docs/factors/FACTOR_GAP_SPEC_20261107.md` |

### 3.1 汇总表（`E3 in_universe` 对 12 条全命中，单列为「共性」，不参与判定）

| # | 策略 | 判定 | 阻塞·因子（GAP） | 阻塞·引擎能力（GAP） | 阻塞·口径（D） | 共性 |
| --- | --- | --- | --- | --- | --- | --- |
| S01 | 双均线 20/60 | **缺因子** | `ma20`,`ma60`（直通，A1） | —（持有期=执行参数） | — | E3 |
| S02 | 唐奇安 20/10 | **缺因子** | `prior_high_20`(F4), `prior_low_10`(F5) | — | D1, D3 | E3 |
| S03 | 60 日时序动量·月末 | **缺引擎能力** | `ma120`(F2, A2) | E4 `month_end` | — | E3 |
| S04 | RSI(14) 超卖反转 | **需口径决策** | `rsi_14_pct`（D2 后转缺因子） | — | **D2** | E3 |
| S05 | 布林(20,2) 下轨反转 | **缺因子** | `sd20`,`boll_lower`,`boll_upper`,`ma20`（A1） | — | — | E3 |
| S06 | 5 日反转·周度 | **缺引擎能力** | — | E2 `rank(x,mask)`, E4 `week_end` | — | E3 |
| S07 | 60 日低波·月度 | **缺引擎能力** | `vol60`(F1, A2) | E2, E4 | — | E3 |
| S08 | 52 周新高·月度 | **缺引擎能力** | `prior_high_250`(F4), `ma120`(F2) | E4 | D3 | E3 |
| S09 | 55 日新高+1.5×量 | **缺因子** | `prior_high_55`(F4), `prior_vol_20`(F6), `ma20`（A1） | — | D1, D3 | E3 |
| S10 | 20 日反转·月度 | **缺引擎能力** | — | E2, E4 | — | E3 |
| S11 | 低波+反转复合 | **缺引擎能力** | `vol60`(F1) | E2, E4 | — | E3 |
| S12 | 低波+市场宽度 | **缺引擎能力** | `uf_vol60`(F1) | E1 `market_breadth`, E2, E4, X1（上生产） | **已裁：不立号**（`D4` 空号；唯一出处 = 契约 §4 掩码口径 + `caliber-decisions §10.1`） | E3 |

**合计：可表达 0 / 缺因子 4（S01,S02,S05,S09）/ 缺引擎能力 7（S03,S06,S07,S08,S10,S11,S12）/ 需口径决策 1（S04）。**

> 读法：判定列写的是「除 E3 外，这条策略自己最靠前的阻塞项」。E3 修好后，上表就是干净的分批依据。

### 3.2 逐条判定

#### S01 双均线 20/60 — **缺因子**
- 研究定义：`COMMON:222-227` 入场 `u & (ma20>ma60) & (ma20.shift(1)<=ma60.shift(1))`；出场 `ma20<ma60`；打分 `ret20`。`COMMON:284-285` `max_hold_days=60`。
- 系统对照：`MAP#strategies[0].items[0,1].system_ref` 写「`ma20`（base，含当日）」，实测不在 178（14:17 时点，`DSL:588` → `E001 未知标识符: ma20`；B0 已注册 `ma20`，17:14 实测 `True []`）。`momentum_20d` 已注册，`CMP#pairs.ret20_vs_momentum_20d.max_abs_diff=0`（n=5,496,401）。
- 可表达性：`ts_mean(close,20) > ts_mean(close,60) and ts_delay(ts_mean(close,20),1) <= ts_delay(ts_mean(close,60),1)` → 实测 `compile_formula.ok=True`。**不需新引擎**。
- 数值保真：`CMP#pairs.ma20_research_vs_system.max_abs_diff=0`（n=5,497,082）、`ma60_research_vs_system.max_abs_diff=0`（n=5,470,011）。
- 解锁：A1 的 `ma20`,`ma60` + E3。持有期 60 走 `holding.max_hold_days`（执行参数，不是因子）。

#### S02 唐奇安 20/10 — **缺因子**
- 研究定义：`COMMON:229-231` 入场 `u & close>prior_high20`；出场 `close<prior_low10`；打分 `ret20`。`COMMON:131,134`：`prior_high20 = high.shift(1).rolling_max(20)`、`prior_low10 = low.shift(1).rolling_min(10)` —— **high/low 价 + 严格此前**。
- 系统对照：`CMP#capability.present_prior_high55=false`、`present_prior_low10=false`。最近量 `high_60d = close.rolling_max(60)`（收盘价、含当日、60）——`CMP#pairs.prior_high55_vs_high_60d.max_abs_diff=219.29`、`jaccard=0.0`；`CMP#signals.s09_break_vs_high_60d.both_true=0`（n=5,470,011）。
- 可表达性：`close > ts_delay(ts_max(high,20),1)`、`close < ts_delay(ts_min(low,10),1)` → 均 `ok=True`。
- 判定：缺因子（F4/F5）+ 需口径决策 **D1/D3**（`prior_*` 族命名与「此前」定义先定；**不得改 `high_60d` 既有语义**）。
- 解锁：A1 + D1/D3 + E3。

#### S03 60 日时序动量·月末 — **缺引擎能力**
- 研究定义：`COMMON:233-237` 入场 `u & month_end & ret60>0 & close>ma120 & ma20>ma60`；出场 `month_end & (ret60<=0 | close<ma120)`；打分 `ret60`。`COMMON:288-289` hold 60。
- 系统对照：`ret60`=`momentum_60d` 已注册（`CMP#pairs.ret60_vs_momentum_60d.max_abs_diff=0`，n=5,469,335）；`ma120` 缺（`capability.present_ma120=false`）；`month_end` 缺（`MAP#strategies[2].items[3].system_ref=\"**无**\"`）。
- 可表达性：`ts_mean(close,120)`、`ts_mean(close,20)>ts_mean(close,60)` 均 `ok=True`；`month_end` 在表达式内 → `E001`（日历）。
- 判定：缺引擎能力（E4，S–M：日级列广播）+ 缺因子（F2，A2）。
- 注：回测侧 `backend/app/backtest/factor.py:54` 已有 `rebalance="monthly"`，`:1121-1164` 有真实调仓日 → 本条「回测可复现、因子化不可准入」。

#### S04 RSI(14) 超卖反转 — **需口径决策**
- 研究定义：`COMMON:239-241` 入场 `u & rsi14<30`；出场 `rsi14>55`；打分 `-rsi14`。`COMMON:141-150`：`ret1 = pct_change`，涨/跌分量 `ewm(alpha=1/14, adjust=False)`（Wilder）。
- 系统对照：`rsi_14` 已注册但口径不同（gains/losses 取 `close.diff()` 绝对价差、零损失 1e-12 护栏）→ `CMP#pairs.rsi14_vs_rsi_14.mean_abs_diff=0.892244`、`max_abs_diff=28.8984`（n=5,509,321）。0.89 点在 30/55 阈值附近足以翻边，**近似不可接受**。
- 引擎：DSL 无 `ewm`（`E002`），但不必加算子——注册 `rsi_14_pct`（base 因子，M）即可。
- 判定：**D2 先拍板**，之后转「缺因子」。
- 空值：`CMP#capability.rsi14_null_rows=0`、`rsi14_nonfinite_or_null_rows=680`、`rsi14_finite_rows=5509321`（空值策略须随 D2 一并定）。

#### S05 布林(20,2) 下轨反转 — **缺因子**
- 研究定义：`COMMON:243-246` 入场 `u & sd20>0 & close<bb_lower`；出场 `close>ma20`；打分 `-bb_z`。`COMMON:152-156`：`sd20=close.rolling_std(20)`、`bb_lower=ma20-2*sd20`、`bb_z=(close-ma20)/sd20`。
- 系统对照：`boll_lower`/`boll_upper` 指标列存在但未注册（`E001`）；`sd20` **连指标列都没有**（`present_sd20=false`）；`boll_position` 已注册。
- 可表达性：`ts_std(close,20)`、`close < ts_mean(close,20) - 2*ts_std(close,20)` → 均 `ok=True`；`bb_z = 4*boll_position-2`（`CMP#pairs.bb_z_vs_4x_boll_position_minus_2.max_abs_diff=0`）。
- 数值保真：`bb_lower_vs_boll_lower=0`、`bb_upper_vs_boll_upper=0`、`sd20_vs_implied_sd=0`（均 n=5,497,082）。
- 解锁：A1 的 `sd20`,`boll_lower`,`boll_upper`,`ma20`。

#### S06 5 日反转·周度 — **缺引擎能力**
- 研究定义：`COMMON:248-250` 入场 `u & week_end & rk_ret5<=0.05`；出场 `lit(False)`（只靠再平衡/持有期退）；打分 `-ret5`。`COMMON:193-201`：`rk_* = rank(average).over(date) / in_universe.sum().over(date)` —— **分母是池内家数**。
- 系统对照：`DSL:506-508` `rank(x) = x.rank(method="average").over("date") / x.count().over("date")` —— 分母是**当日非空数**，无掩码参数。
- 实测后果：`XS#xs_rank.S06_ret5_le_0.05`：`mean_jaccard=0.3195`、`mean_sel_research=49.7181` vs `mean_sel_system=154.3059`、`mean_system_denominator=3095.3511` vs `mean_universe_size=1428.9495`、`mean_recall_of_research=1.0`（系统集合严格包含研究集合）。
- 判定：缺引擎能力（**E2** 掩码 rank + **E4** `week_end`）。

#### S07 60 日低波·月度 — **缺引擎能力**
- 研究定义：`COMMON:252-254` 入场 `u & month_end & rk_vol60<=0.10`；打分 `-vol60`。`COMMON:140`：`vol60 = ret1.rolling_std(60)`（日频、**未年化**）。
- 系统对照：`present_vol60=false`。最近量 `annual_vol_20d` 不可替代：`CMP#pairs.vol60_ann_vs_annual_vol_20d.mean_abs_diff=0.091912`（已年化后仍差）、`XS#vol60_substitution.mean_jaccard=0.135620`。
- 可表达性：`ts_std((close - ts_delay(close,1)) / ts_delay(close,1), 60)` → `ok=True`（A2 注册；B0 实现即此写法）。
- 实测后果：`XS#xs_rank.S07_vol60_le_0.10`：`mean_jaccard=0.1778`、`55.4886` vs `307.2159`。
- 判定：缺引擎能力（E2, E4）+ 缺因子（F1 → A2）。

#### S08 52 周新高·月度 — **缺引擎能力**
- 研究定义：`COMMON:256-259` 入场 `u & month_end & dist_52w_high>=-0.03 & close>ma120`；打分 `dist_52w_high`。`COMMON:157`：`dist_52w_high = close/prior_high250 - 1`（250 日、high 价、此前）。
- 系统对照：`distance_to_high_240d`（240、**收盘价**、含当日）→ `CMP#pairs.dist_52w_high_vs_distance_to_high_240d.mean_abs_diff=0.027444`（2.7 个百分点）；`CMP#signals.near_high_3pct`：`both_true=150292`、`only_b=133101`、`jaccard=0.5303` —— 用 240 日口径会多选 **88%**。
- 判定：缺引擎能力（E4）+ 缺因子（F4 的 `prior_high_250`、F2 的 `ma120`，均 A2）+ D3。

#### S09 55 日新高+1.5 倍量 — **缺因子**
- 研究定义：`COMMON:261-264` 入场 `u & close>prior_high55 & volume>1.5*prior_vol20`；出场 `close<ma20`；打分 `ret60`。`COMMON:132,136`：`prior_high55 = high.shift(1).rolling_max(55)`、`prior_vol20 = volume.shift(1).rolling_mean(20)`。
- 系统对照：缺 `prior_high55`/`prior_vol20`/`vol_ma20`；`present_prior_vol20=false`；`vol_ma5`/`vol_ma10` 是含当日指标列且未注册。
- 三个近似全部实测否决：`CMP#pairs.prior_high55_vs_high_60d.jaccard=0.0`（`signals.s09_break_vs_high_60d.both_true=0`，n=5,470,011）；`prior_vol20_vs_vol_ma20_incl_today.mean_abs_diff=7289.373933`；`prior_vol20_vs_vol_ma10.mean_abs_diff=47600.271462` → 最终 `signals.s09_vol_1p5.jaccard=0.489651`。
- 可表达性：`close > ts_delay(ts_max(high,55),1) and volume > 1.5*ts_delay(ts_mean(volume,20),1)` → `ok=True`。
- 判定：缺因子（A1 的 `prior_high_55`,`prior_vol_20`,`ma20`）+ D1/D3。

#### S10 20 日反转·月度 — **缺引擎能力**
- 研究定义：`COMMON:266-268` 入场 `u & month_end & rk_ret20<=0.10`；打分 `-ret20`（`momentum_20d` 已注册且 `max_abs_diff=0`）。
- 实测后果：`XS#xs_rank.S10_ret20_le_0.10`：`mean_jaccard=0.2977`、`92.75` vs `308.75`、`denominator=3091.6705` vs `universe=1429.7386`。
- 判定：缺引擎能力（E2, E4）。因子侧无缺口。

#### S11 低波+20 日反转复合 — **缺引擎能力**
- 研究定义：`COMMON:270-273` 入场 `u & month_end & rk_vol60<=0.30 & rk_ret20<=0.30`；打分 `-(rk_vol60 + rk_ret20)`。
- 系统对照：`rank()` 存在故语法可写，但共用同一个无掩码分母 → 复合后误差放大。`XS#xs_rank.S11_both_le_0.30`：`mean_jaccard=0.048851`、`14.6932` vs `207.2159`（**12 条中最差**）。
- 判定：缺引擎能力（E2, E4）+ 缺因子（F1 → A2）。排序键 `-(rk_a+rk_b)` 依赖 E2 的同一口径，E2 落地后即可表达，无需额外能力。

#### S12 低波+市场宽度 — **缺引擎能力**
- 研究定义：`COMMON:275-278` 入场 `u & month_end & rk_vol60<=0.10 & market_breadth>=0.5`。`COMMON:185-191`：`market_breadth` = 当日 `in_universe & ma60 非空` 中 `close>ma60` 的比例。
- 系统对照：无按日全市场聚合（`capability.present_market_breadth=false`）；无掩码 rank；无 `vol60`。
- 口径（**已裁，不再需要决策**）：`XS#market_breadth`：`mean_research=0.5407417` vs `mean_unmasked=0.4642690`、`share_days_threshold_flip=0.1911186`、`share_month_ends_research_ge_0p5=0.5340909` vs `share_month_ends_unmasked_ge_0p5=0.3409091`。策略经理 2026-11-07 17:16 判定**不立号**（`docs/research/caliber-decisions-20261107.md` §10.1 决定五）：现行口径 = 契约 §4 唯一，无掩码版按 §4.5-4 明令 `approx=true` 且策略拒用 → **不再立 D 号，`D4` 保持空号**；本文只引用、不重述（重述即双源）。**两个数别混用**（§10.2）：`0.4642690` 是「全样本 ∩ `ma60` 非空」，**不是**「池内、`ma60` 缺失记 0」（那版未实测、量级未知，不得引用）。
- 判定：缺引擎能力（E1, E2, E4）+ 缺因子（F1, → `uf_vol60`）+ 上生产另需 X1；口径**已裁、不占号**（§6-1）。
- 附：生产侧 `backend/app/custom/paper_execution/README.md`「执行契约」明写「暂不支持…市场环境过滤」→ 本条上生产还需 X1。

---

## 4. S 级因子注册批次建议（供排期）

### 4.1 批 A1 — 9 个，S 级，先做；解锁 S01/S02/S05/S09 的因子侧

| # | 因子 id | 类型 | 可执行定义 | 保真证据（`CMP`） | 解锁 |
| --- | --- | --- | --- | --- | --- |
| 1 | `ma20` | 直通 | 指标层已算 `close.rolling_mean(20)` | `#pairs.ma20_research_vs_system.max_abs_diff=0`（n=5,497,082） | S01,S03,S05,S09 |
| 2 | `ma60` | 直通 | 指标层已算 `close.rolling_mean(60)` | `#pairs.ma60_research_vs_system.max_abs_diff=0`（n=5,470,011） | S01,S03 |
| 3 | `boll_lower` | 直通 | 指标层已算 `ma20-2*sd20` | `#pairs.bb_lower_vs_boll_lower=0` | S05 |
| 4 | `boll_upper` | 直通 | 指标层已算 `ma20+2*sd20` | `#pairs.bb_upper_vs_boll_upper=0` | S05 |
| 5 | `sd20` | 表达式 | `ts_std(close,20)` | `#pairs.sd20_vs_implied_sd=0` | S05 |
| 6 | `prior_high_20` | 表达式 | `ts_delay(ts_max(high,20),1)` | 无近似可替：`prior_high55_vs_high_60d.jaccard=0.0` | S02 |
| 7 | `prior_low_10` | 表达式 | `ts_delay(ts_min(low,10),1)` | `#capability.present_prior_low10=false` | S02 |
| 8 | `prior_high_55` | 表达式 | `ts_delay(ts_max(high,55),1)` | vs `high_60d`：`max_abs_diff=219.29`、`jaccard=0.0` | S09 |
| 9 | `prior_vol_20` | 表达式 | `ts_delay(ts_mean(volume,20),1)` | vs 含当日 `vol_ma20`：`mean_abs_diff=7289.37` | S09 |

- 9 个定义**全部 `compile_formula(...).ok=True`**（实测，命令见 §7.2）→ 零引擎改动。
- 口径来源：`COMMON:122-136`（`rolling_mean` / `high.shift(1).rolling_max` / `low.shift(1).rolling_min` / `volume.shift(1).rolling_mean`），与 D3 冻结的 `prior_*` 语义族一致；**命名定稿前不得动 `high_60d`/`low_60d` 既有语义**。
- 验收判据（每因子）：`max_abs_diff = 0` 且 `n > 5.4e6`；`prior_*` 另加「与 `COMMON` 按 `F-A3` 比对（5 组 `prior_*` 实测 `max_abs_diff` 全 `0.0`，`F_CLASS_RANK_PARITY_20261107.json`）」+「与 `high_60d` 的 jaccard 必须 < 1（证明不是同一条因子改名）」。

### 4.2 批 A2 — 5 个，S 级；为 S03/S07/S08/S11/S12 与股票池预备

| # | 因子 id | 类型 | 可执行定义 | 说明 | 解锁 |
| --- | --- | --- | --- | --- | --- |
| 10 | `ma120` | 表达式 | `ts_mean(close,120)` | `#capability.present_ma120=false` | S03,S08 |
| 11 | `vol60` | 表达式 | `ts_std((close - ts_delay(close, 1)) / ts_delay(close, 1), 60)` | 日频**未年化**；写法与**研究侧**代码逐位一致（`COMMON:126` 的 `pct_change()` 实测与减法式逐位相同：8 值探针 `max_abs_diff=0.0`）；但 canonical `uf_vol60`（store 侧）用的是**除法式** `ts_std(close / ts_delay(close, 1) - 1, 60)`，与本式是**容差等价、不是逐位等价**。旧手写 `close/ts_delay-1` 与研究侧是 1 ULP 差：全帧对账 `max_abs_diff=1.1102e-16`、`n=5,469,335`、非零差 4,214,876 行且**全部为 1 ULP**、超 1e-12 的行 0（`evidence/F_CLASS_PARITY_20261107.json#factor_parity.uf_vol60`；60 只标的、116,287 行探针里 4.6% 行不等，见 `REGISTRATION_B0_20261107.md` §4.1）；B0 减法式 `max_abs_diff=0.0`、`n=5,469,335`（`evidence/registration_b0_20261107.json#fidelity.per_factor.vol60`））；`annual_vol_20d` 不可替（`mean_abs_diff=0.091912`，`jaccard=0.1356`） | S07,S11,S12 |
| 12 | `prior_high_250` | 表达式 | `ts_delay(ts_max(high,250),1)` | `distance_to_high_240d` 口径不同（`mean_abs_diff=0.027444`） | S08 |
| 13 | `prior_amount_20` | 表达式 | `ts_delay(ts_mean(amount,20),1)` | 股票池门槛（`COMMON:181`：`prior_amount20>=1e8`） | E3 |
| 14 | `ma200` | 表达式 | `ts_mean(close,200)` | F3 备用，暂无策略引用 | — |

**批 A 合计 14 个**（10 表达式 + 4 直通），与 §0 结论 1 一致。

### 4.3 其余批次（非 S 级）

| 批次 | 内容 | GAP | 代价 | 解锁 | 关键证据 |
| --- | --- | --- | --- | --- | --- |
| **B** | `in_universe` 基座因子：`observed_bars>=120 & ~st_flag & raw_close>=3 & prior_amount20>=1e8 & volume>0` | E3 | M | 12/12（准入必需） | `COMMON:177-184`；`#sideways[0]` jaccard 0.977 |
| **C** | 日历列 `month_end`/`week_end`（按交易日轴，日级广播） | E4 | S–M | S03,S06,S07,S08,S10,S11,S12 | `COMMON:159-171`；`factor.py:54,1121-1164` 回测侧已有 |
| **D** | `rank(x, mask)` 掩码截面 | E2 | M | S06,S07,S10,S11,S12 | `dsl.py:506-508`；`XS` 分母 3095 vs 池 1429 |
| **E** | `market_breadth`（掩码口径） | E1 | M | S12 | `COMMON:185-191`；`XS#market_breadth` |
| **F** | 生产侧组合级调仓/容量/排序 | X1 | L | 6 条截面策略上生产 | `paper_execution/README.md`「逐股 hits」 |
| **D0** | D1/D2/D3 已关闭决策 ＋ 口径项（`market_breadth` 掩码**已裁不立号**，唯一出处 = 契约 §4 + `caliber-decisions §10.1`；`in_universe` 两处真实差异只登记、不占号） | D | S（无代码） | S02,S09,S04,S08,S12 | 本文 §3.2、§6-1 |

### 4.4 解锁阶梯（建议排期）

| 阶段 | 完成项 | 累计可准入 | 本阶段新增 |
| --- | --- | --- | --- |
| **P1** | A1 + B（E3） | 4 | S01、S02、S05、S09 |
| **P2** | + D0 决策 + A2 + C（E4） | 6 | S03、S08 |
| **P3** | + D（E2） | 10 | S06、S07、S10、S11 |
| **P4** | + E（E1） | 11 | S12 |
| **P5** | + D2 决策 → 注册 `rsi_14_pct` | 12 | S04 |
| **P6** | + F（X1） | 12 条上生产 | —（回测复现已完成，不再依赖 X1） |

> 排期建议一句话：**先把 14 个因子注册（A1+A2）**，因为它们是 S 级、零引擎风险、且已有 `max_abs_diff=0` 的保真证据；引擎能力（E2/E1）和已关闭的 D1–D3 决策并行推进（口径项已裁：`market_breadth` 不立号、`D4` 空号；`in_universe` 2a/2b 只登记不占号，见 §6-1），不要串行堵在 P1 前面。

---

## 5. 与起点事实不一致的 7 处（对着证据逐条）

| # | 起点事实 | 实测 | 对排期的影响 |
| --- | --- | --- | --- |
| 5.1 | `FACTOR_GAP_SPEC` 共 **20 项** | `SPEC:15-33` 总表实测 **19 行** = D3 + F7 + E4 + X2 + G3 | 排期按 19 项；「20」进不了验收 |
| 5.2 | 系统缺失 **23** | `MAP#counts` 把 `sideways` 5 行并入：策略内 **20** + 横向 **3**（`in_universe`、`月末/周末调仓日`、`max_hold_days`，**全部与策略内条目重复**）；横向另有 2 行「可直接复用」（执行价、涨跌停不可买）；`S07` 另有 1 行标 `—` 非缺口。去重后 distinct 系统缺失 = **20 行**，且 `month_end` 一条在 6 条策略里重复计数 | 23 不能当工作量；真实问题种类远少于 23 |
| 5.3 | 台账 16 行「可直接复用」 | 其中 **7 行**引用的 id 在 14:17 时不在 178 注册因子内（`ma20`/`ma60`/`boll_lower`/`boll_upper`/`sd20`）→ 当时 `E001`（§2.6）；**B0 后已注册、此条关闭** | 这 7 行要先补注册，不是零成本 |
| 5.4 | X2「生产侧无」，影响 S01–S06 | **扩展包已实现（有条件生效）、核心默认路径无同一语义**：实现在 `backend/app/custom/paper_execution/service.py:404-408,418-421`（`hold_days >= overrides["max_hold_days"]` → `reason="max_hold"` 强平），由该模块 router 的 lifespan 起后台线程（`routes.py:56-58,93-94,111`）；该模块**随默认应用启动自动发现并挂载**（`main.py:838` → `extensions/loader.py:28-49` → `custom/paper_execution/__init__.py:5,12`），所以「未启用」指**没有满足条件的绑定账户时线程空转、且 `app/strategy/paper_auto.py` 无该语义**，不是「未安装」。实机更正（17:12）：数据根是 `D:\TSP\data`（**不是**仓库内 `data/`，据 `evidence/registration_b0_20261107.json#data_dir`），其 `user_data/extensions/paper_execution/runner.sqlite` **存在但 0 字节**（旁有 512 B `runner.sqlite-journal`，mtime 2026-11-06 12:15）→ 读不出任何绑定数据。回测不走它（`backend/app/backtest/**` 无 `paper_execution` 引用）。另：`COMMON:284-308` 显示 12 条**全部**有 `max_hold_days`（5/10/20/60 日），不是只有 S01–S06 | 不判「关闭」：X2 维持 P1（契约 `:40`,`:1209` 明写不在引擎契约内、另立），表述统一为「有条件生效」；要关必须另做「核心路径是否也需要」的裁定 |
| 5.5 | X1 是 S06–S12 的前置 | 12 条全部是 **gate + score**（`COMMON:218-280`），无显式 `top_n`；回测侧 `factor.py` 已有 `rebalance` 与 `max_positions`。4 条逐股 gate 策略（S01/S02/S05/S09）复现**不需要** X1 | X1 不得挡 P1；它只挡「截面策略上生产」 |
| 5.6 | E4 是 P0 引擎缺口 | 回测侧**已有**：`factor.py:54`（`daily/weekly/monthly`）+ `:1121-1164`（真实调仓日）。缺的只是「因子化表达」与「生产侧一致」 | E4 可从 P0 降到 P2，代价按 S–M 估（日级列广播，非新算子） |
| 5.7 | S04 两行标「仅缺因子」 | `MAP#strategies[3].items[0,1]` 的 `verdict` 是「口径不一致」，`path` 却写「仅缺因子」——真正阻塞是 **D2 口径**；同理 S02/S09 的 `prior_*` 命名要先过 D1/D3 | S04 在 D2 拍板前不能排实现；`缺因子` 与 `需口径决策` 必须在台账分列 |

---

## 6. 本轮未确认（明确标为未知，不做推断）

1. **口径项：一项已裁、一项改按事实登记——都不占号。**
   - ① `market_breadth` 掩码口径：**已裁，不立号（`D4` 空号）**。策略经理 2026-11-07 17:16（`docs/research/caliber-decisions-20261107.md` §10.1 决定五）三条理由：口径已唯一（契约 §4.1 / §4.2 / §4.4 / §4.6 四处写死）、另两个候选口径已被点名禁掉、再加一个 D 号就是双源。**唯一出处 = 契约 §4 掩码口径 + `caliber-decisions §10.1`，本文只引用不重述。**
   - ② `in_universe` 的两处真实差异（**不是**「`COMMON:184` 把 null 折 False」这一条）——**只登记，不占号，不裁定**：
     - **2a ST 宽容**：`common.py:179` 写 `pl.col("st_flag").fill_null(False) == False`，缺失 ST 按「非 ST」处理；契约判 `null`（v0.6 `:141`），并注明「研究侧的 `fill_null(False)` 是宽容处理，系统生产口径不沿用」，对账走 `st_flag_missing_policy="treat_non_st"`（v0.6 `:123`、`:142`）。这是**已参数化的已知差异**，不是缺陷。
     - **2b ST 表末端截断**：`st_history` 在 `2026-10-20` 一次性写入 **198 行 `st_flag=False`**，此后到 `2026-10-29` 只有 4 条 False、**0 条 True**（本机实测 `D:\TSP\data\st_history\part.parquet`：`flag_date==2026-10-20` 共 198 行 / True 0；`>2026-10-20` 共 4 行 / True 0；`max(flag_date)=2026-10-29`），导致 `2026-10-20`…`2026-11-06` 共 **14 个交易日** ST 不可判（`docs/factors/evidence/E3_DATA_AVAILABILITY_20261107.md` §2.5，独立复算见 `research/independent-review-20261107/F_CLASS_AUDIT_20261107.md:189`）。契约用 `st_unknown_windows`（v0.6 `:124`、`:143`）把这 8 天强制置 `null`，末端超 `coverageEnd` 同理（`:144`）——**修数据属行情数据侧，改 `common.py` 属改口径，都不在本文件权限内**。
   - **`COMMON:184` 不是口径项，这句话先前记错了，按代码更正**：`:184` 是 `f = frame.with_columns(base.fill_null(False).alias("in_universe"))`（**代码，不是注释**；`:185` 才是注释「市场宽度：…」，`:192` 是「截面排名：…」）。它兜的是 `observed_bars` / `raw_close` / `prior_amount20` / `volume` 比较后残余的 null，而那几列契约本来就要 `0.0`（v0.6 `:138`–`:140`，原文注明「与研究 `fill_null(False)` 一致」）→ **与契约同值，既非口径项也非缺陷**（与 `caliber-decisions` §10.3 决定六一致）。到 `:184` 时 `st_flag` 项已由 `:179` 处理完。
   - **同一个编号不得给两件事**：`D4` 此前被独立审核占用（`docs/architecture/CONTRACT_REVIEW_20261107.md:138`、`:61`），现按 `caliber-decisions §10.1` 保持**空号**。本文对 2a / 2b 均不占号。
2. **X2 的落地范围未定**：已实测扩展包 `app/custom/paper_execution` 实现了 `max_hold_days`，且**随默认应用启动自动挂载**（`main.py:838`；`__init__.py:5,12`；`routes.py:111` 的 lifespan）；**未验证**的是「是否存在已启用且 `overrides` 含 `max_hold_days` 的绑定账户」（本机 `D:\TSP\data\user_data\extensions\paper_execution\runner.sqlite` 为 **0 字节**，读不出绑定）与「核心路径 `app/strategy/paper_auto.py` 是否也需要同一语义」。这两点决定 X2 是「补核心路径」还是「只做绑定核验」，都不改「不判关闭」。**（更正：原写「本机 `data/user_data/extensions` 不存在」有误——那是仓库内目录，数据根为 `D:\TSP\data`。）**
3. **日级因子能否被承载**：`month_end` 是无 symbol 维度的日级列，注册表对这类因子的支持本轮未读透；若不支持，E4 代价从 S 升到 M。**这条直接影响 P2 工期。**
4. **`ext_*` 未审计**：192 个因子里 85 个 `ext_*` 扩展数据因子未审计（G2；85 是按 178 时点的 `ext_*` 计数、B0 未改动 `ext_*`）；本文只覆盖 core 93 与 12 条策略实际引用到的 id。
5. **本轮没有任何回测运行**，未产出收益/风险数字；§1 全部数字是对既有 `evidence/*.json` 的复算，§2.6 的 178→192 / 9 / 25 是对注册表与 DSL 的实测（192 为 17:14 复跑值，命令见 §7.1）。

---

## 7. 复核命令（只读、可重放）

全部在 `C:/work/sourcecode/tick-stock-panel` 下执行；Python 用 `backend/.venv`（3.11，含 polars）。

**7.1 注册因子数 / 基础列数 / 算子数**

```bash
cd backend && ./.venv/Scripts/python.exe -c "from app.factors.registry import all_factors; from app.factors import dsl; print(len(all_factors()), len(dsl.BASE_COLUMNS), len(dsl.OPERATORS))"
```

期望输出（2026-11-07 17:14 实测）：`192 9 25`（B0 注册 14 个批 A 因子后由 `178 9 25` 变为 `192 9 25`）

**7.1b 两个时点（R1 判据集合，2026-11-07 17:4x 实测）**——`192` 里 **8 个 canonical 一个都没有**，canonical 要装载 store 才出现：

```bash
cd backend && ./.venv/Scripts/python.exe -c "import pathlib;from app.factors.registry import all_factors;f=lambda: sorted(x.id for x in all_factors());print('import',len(f()),'uf',sum(i.startswith('uf_') for i in f()));import app.factors.store as st;st.load_into_registry(pathlib.Path(r'D:\\TSP\\data'));print('loaded',len(f()),'uf',sum(i.startswith('uf_') for i in f()))"
```

实测输出：`import 192 uf 0` / `loaded 207 uf 14`。逐项：8 个 alias（`vol60` 等裸 id）在 192 里 **8/8 在**；8 个 canonical（`uf_*`）在 192 里 **0/8 在**、装载后 **8/8 在**；6 个单 id canonical（`ma20`/`ma60`/`sd20`/`boll_lower`/`boll_upper`/`prior_amount_20`）在 192 里 **6/6 在**。（`load_into_registry` 需 `pathlib.Path`，直接传 str 会 `TypeError`。）

**7.2 可表达性实测（批 A1/A2 的定义 + 近似因子 + 缺口因子）**

```bash
cd backend && PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -c "from app.factors import dsl; [print(repr(e), dsl.compile_formula(e).ok, [x.code for x in (dsl.compile_formula(e).errors or [])]) for e in ['ts_mean(close,20) > ts_mean(close,60)','close > ts_delay(ts_max(high,20),1)','close < ts_delay(ts_min(low,10),1)','close < ts_mean(close,20) - 2*ts_std(close,20)','close > ts_delay(ts_max(high,55),1) and volume > 1.5*ts_delay(ts_mean(volume,20),1)','ts_std((close - ts_delay(close,1)) / ts_delay(close,1), 60)','ma20 > ma60','close > high_60d','ewm_mean(close,14)','month_end','market_breadth','in_universe']]"
```

期望（2026-11-07 17:14 实测）：前 6 条 `True []`；**`'ma20 > ma60'` 现在是 `True []`**（B0 前为 `False ['E001','E001']`，保留该历史值只用于识别回退）；`'close > high_60d'` `False ['E001']`（`high_60d` 仍未注册，属 §2.6 的「指标列」）；`'ewm_mean(close,14)'` `False ['E002']`；`'month_end'`/`'market_breadth'`/`'in_universe'` `False ['E001']`。

**7.3 映射表计数复核（策略内 vs 横向 `sideways`）**

```bash
PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe -c "import json,collections; d=json.load(open('docs/factors/evidence/strategy_factor_map.json',encoding='utf-8')); c=collections.Counter(); [c.update(i['verdict'] for i in s['items']) for s in d['strategies']]; print('策略内',dict(c),'行数',sum(len(s['items']) for s in d['strategies'])); print('横向',dict(collections.Counter(x['verdict'] for x in d['sideways'])),len(d['sideways']))"
```

期望：`策略内 {'可直接复用': 14, '系统缺失': 20, '口径不一致': 6, '—': 1} 行数 41`；`横向 {'系统缺失': 3, '可直接复用': 2} 5`。

**7.4 缺口规格总表行数**

```bash
PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe -c "L=open('docs/factors/FACTOR_GAP_SPEC_20261107.md',encoding='utf-8').read().splitlines(); print(sum(1 for l in L if l[:3] in ('| D','| F','| E','| X','| G') and l[3:4].isdigit()))"
```

期望输出：`19`

**7.5 关键证据字段**

```bash
PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe -c "import json; c=json.load(open('docs/factors/evidence/compare_stats.json',encoding='utf-8')); x=json.load(open('docs/factors/evidence/xs_rank_stats.json',encoding='utf-8')); print(c['signals']['s09_break_vs_high_60d']); print(c['capability']['present_vol60'], c['capability']['present_ma120'], c['capability']['present_sd20'], c['capability']['present_market_breadth']); print(x['xs_rank']['S11_both_le_0.30']['mean_jaccard']); print(x['market_breadth']['share_days_threshold_flip'])"
```

期望：`{'n': 5470011, 'both_true': 0, 'only_a': 143747, ...}`；`False False False False`；`0.048851...`；`0.1911186...`。

**7.6 研究侧定义行号（人工核对用）**

```bash
PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe -c "L=open('research/strategy-search-20261107/scripts/common.py',encoding='utf-8').read().splitlines(); [print(i,l) for i,l in enumerate(L,1) if 118<=i<=145 or 175<=i<=202]"
```

---

## 8. 本文件的效力边界

**本文件不构成实现授权。** 批 A 的 14 个因子定义与 §4.3 的引擎能力，均须按「缺口规格 → 架构契约 → 系统开发工程师实现 → 独立审核」推进：本文件只提供**可执行定义与验收判据**，不提供实现，也不改 `backend/app/**`。因子登记完成的标志是独立审核复核 `max_abs_diff = 0` 且 `n` 达标，不是本文落盘。

**后续仍开、但一律就地改本文件与 `FACTOR_GAP_SPEC_20261107.md`（不新开文档）的三项**：① E4 是否降级；② 14 个已注册因子的逐条规格（公式 / 价基 / 窗口 / shift / warmup / 空值 / PIT / 覆盖度 / 版本，canonical 名按 §2.1 写）；③ **canonical/alias 机制未实现**（`ID-CANON-1` 只落在文档与 `evidence/f_class_registry.json`；`alias_of` / `FS03` / `assert_factors_usable` / `strategy_usable` 在 `backend/app/**` 各命中 **0**，`FactorSpec` 无这三个字段）→ 这是引擎缺口，需按系统开发流程立项，**不属因子侧可自行补齐**。**已结清、不得再列为待办**：口径项编号（`market_breadth` 掩码**已裁不立号**，`D4` 空号，唯一出处 = 契约 §4 + `caliber-decisions §10.1`；`in_universe` 2a/2b 只登记不占号，见 §6-1）、X2 表述（已统一为「扩展包已实现、生产默认路径未启用」，见 §5.4 / §6-2）、E2 旧口径靶值（已在 GAP v1.2 §3-E2 降为诊断参照）。
