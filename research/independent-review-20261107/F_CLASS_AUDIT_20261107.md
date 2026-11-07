# 批一 · F 类八只因子注册与对账 —— 独立审核报告

- 审核方：独立审核工程师（不参与实现，不修改被审文件）
- 审核时间：2026-11-07 15:38 – 16:00（Asia/Shanghai）
- 仓库：`C:\work\sourcecode\tick-stock-panel`，分支 `dev`，HEAD **`65c6e42f`**
- 判据文件快照：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md`，
  sha256 **`5eb9772411f723576b657f85af7c0aa26427137a41fb53b5774b935942565903`**，mtime **2026-11-07 15:51:09**
  （⚠ 该文件在本次审核过程中被改写了至少三次：15:35 → 15:45:52 → 15:51:09；且 `docs/architecture/` 未被 git 跟踪，无法用版本号固定判据。见缺陷 P1-2。）
- 数据目录 `D:\TSP\data` 全程**只读**：所有需要"重放写盘"的验证（F-A5）都在临时目录做，未改数据目录、未提交、未部署、未重启服务。

## 0. 判据总表

| 判据 | 判定 | 命令（实际执行） | 退出码 | 关键数字 |
| --- | --- | --- | ---: | --- |
| F-A1 八只可 `get_factor` | **PASS** | `cd backend && ./.venv/Scripts/python.exe` 内 `store.load_into_registry(Path(settings.data_dir))` → 逐只 `get_factor` | 0 | 载入 14 条自定义定义，8 只全部取到（`kind=custom`、`version=1`）；未载入时 8 只全 `None`（依赖启动加载，见 P3-1） |
| F-A2 warmup 一致 | **PASS** | 同上 | 0 | 61 / 121 / 201 / 21 / 56 / 251 / 11 / 21，8/8 逐一相等 |
| F-A2′ dependencies | **PASS** | 同上 | 0 | `{close} {close} {close} {high} {high} {high} {low} {volume}`，8/8 顺序与契约一致 |
| 公式逐字等于 §7.1 | **PASS** | 自写字符级比较脚本（读 `D:\TSP\data\user_data\custom_factors\uf_*.json` 的 `formula`） | 0 | 8/8 逐字相同（长度 42/19/19/29/29/30/28/32）；`prior_*` 5 只全部含 `ts_delay(...,1)` 且分别用 high/low；**无一只漏 shift** |
| F-A3 数值对账 | **PASS** | ① 审核方自有脚本 `scripts/independent_f_class_check.py`（不复用被审脚本）；② 复跑被审脚本 `docs/factors/evidence/scripts/f_class_parity.py` | 0 / 0 | 契约字面（20 symbol × 近 250 日）：`max_abs_diff` ≤ 2.78e-17，超 1e-12 行数 0，null 不一致 0；全评估窗 5,332,523–5,503,218 行，同结论；被审脚本复跑与原件**除 meta 两项（elapsed 26.5→20.3、generated_at）外逐字段完全相同** |
| F-A4 命名映射唯一 | **PASS**（台账内部） | `python docs/factors/evidence/scripts/check_f_class_ledger.py`；另自写 id 集合/一对一比较 | 0 | 自检 `TOTAL VIOLATIONS: 0` / `RESULT: PASS`；台账 md 16 行 = 2 张表 × 8，去重后研究名↔uf_ id **8 对一对一**；台账 json id 集合 == 8 只 F 类 id，无缺无重 |
| F-A5 幂等 | **FAIL** | ① `store.upsert_definition` 直接探针（临时目录）；② **复刻 `api/factors.py:338-350` 的 definition 形状**对真实 `uf_vol60.json` 副本做同内容二次注册 | 0 | 直接探针：二次注册 `version=1 unchanged=True`、文件字节与 mtime 均不变 ✔；**但 API 形状探针：`version 1→2`、`unchanged=False`、文件被重写**（8 只全中，根因 `lang` 键不对称） |
| F-A6 单位量级 | **PASS**（按现行 F-A6a/b/c） | 自有脚本复算 `vol60` 分布（系统 DSL 与研究列分别算，二者一致到 1e-17） | 0 | 2019-01-01 起：n=5,781,697，p01 **0.00907**∈(0,0.02) ✔、p50 **0.02486**∈[0.015,0.06] ✔、p99 **0.05490**<0.10 ✔；2019-07-01 起：5,469,335 / 0.00900 / 0.02471 / 0.05492 ✔ |
| F-A6 原字面区间（0.015–0.06「越界即 fail」） | **FAIL**（仅作对照） | 同上 | 0 | 越界行 **12.58%**（2019-01-01 起）/ **13.03%**（2019-07-01 起），n_outside=712,922 |
| E3 关键事实（ST 批量 False） | **确认** | 自有 duckdb 脚本 `scripts/verify_st_claims.py` + 独立 cell 级复算 | 0 | 2026-10-20 恰好 **198 行**全部 `st_flag=false`；as-of 全 symbol 家数 **218 → 20**；限定当日有 bar 的口径 **192 → 0**；与两方说法均吻合（分母不同） |
| 「已跟踪文件改动」声明 | **不成立** | `git status --porcelain`；`git diff --numstat -- backend docs` | 0 | 已跟踪改动 **7 个 M**：`backend/app/api/factors.py`(+8/−16)、`backend/app/factors/store.py`(**+91/−1**)，`research/strategy-search-20261107/` 下 5 个（+74/−14、+37/−37、+168/−16、+38/−38、+17/−6） |

**一句话结论：八只因子的口径、注册、数值对账、台账映射全部成立（F-A1–F-A4、F-A6 通过）；F-A5 判 FAIL —— 对"本批这 8 只盘上定义"同内容二次注册会把 version 从 1 抬到 2 并重写文件，正是该判据要防的"缓存全表失效"。另外发现判据文件在审核期间被就地改写、契约 §7.4 与实现正面冲突、以及同口径出现两个 id。**

---

## 1. F-A1 / F-A2：注册与元数据

命令（另起进程，不复用被审脚本）与完整输出：`artifacts/fa12_separate_process.txt`（退出码 0）

```
data_dir= D:\TSP\data
loaded_count= ['uf_auction_*…×5', 'uf_ma120', 'uf_ma200', 'uf_prior_high_20',
               'uf_prior_high_250', 'uf_prior_high_55', 'uf_prior_low_10',
               'uf_prior_vol_20', 'uf_vol60', 'cf_auction_resonance']
uf_vol60  warmup=61  exp=61  deps=['close']   version=1 kind=custom
…（8 只全部 warmup_ok=True deps_ok=True）
F_A1_A2_ALL_OK= True
```

补充事实（判据解释）：在**未调用** `load_into_registry` 的进程里，8 只全部 `get_factor → None`；注册表在 import 阶段只有 192 条（含 `research_factor_pack` 提供的裸 id，见 P2-3）。也就是说 F-A1 的成立条件是"启动加载已执行"，这符合生产路径（`app/main.py` 启动期加载），但判据措辞未写，见 P3-1。

## 2. 公式逐字比对（本批最大的坑：`prior_*` 缺 `ts_delay`）

`artifacts/fa_formula_and_disk.txt`（退出码 0）。从契约 §7.1 表格用正则抽出 8 行 `formula_text`，与磁盘 json 的 `formula` 做**字符级**比较：

| id | 长度（磁盘/契约） | 逐字相同 | 含 `ts_delay` | 用列 |
| --- | --- | :-: | :-: | --- |
| uf_vol60 | 42 / 42 | ✔ | ✔（close） | close |
| uf_ma120 | 19 / 19 | ✔ | — | close |
| uf_ma200 | 19 / 19 | ✔ | — | close |
| uf_prior_high_20 | 29 / 29 | ✔ | ✔(high,1) | high |
| uf_prior_high_55 | 29 / 29 | ✔ | ✔(high,1) | high |
| uf_prior_high_250 | 30 / 30 | ✔ | ✔(high,1) | high |
| uf_prior_low_10 | 28 / 28 | ✔ | ✔(low,1) | low |
| uf_prior_vol_20 | 32 / 32 | ✔ | ✔(volume,1) | volume |

同时验证 §7.5-4：8 个 json 里 `warmup_bars`、`dependencies` 字段**均不存在**（未手填）；§7.5-5：8 只 `status` 全为 `draft`（未在过 V3 前标 active）。

## 3. F-A3：数值对账（审核方自有实现 + 复跑被审脚本）

### 3.1 自有实现（不复用被审脚本）

`scripts/independent_f_class_check.py` → `artifacts/independent_f_class_check.json`（退出码 0，耗时 20.23s，polars 1.44.1）。
研究侧只 `import` `common.open_market/load_panel/add_indicators`（未改其文件）；系统侧 `compile_formula(契约原文).frame_transform(同一帧)`；**整帧变换（含预热段）后**再切评估窗口（否则每 symbol 首 N 根会被误判为空）。

| id | sample 20×250：n / max_abs_diff / 超容差 / null 不一致 | 全评估窗：n / max_abs_diff / 超容差 / null 不一致 |
| --- | --- | --- |
| uf_vol60 | 4,398 / 2.7755575615628914e-17 / 0 / 0 | 5,469,335 / 1.1102230246251565e-16 / 0 / 0 |
| uf_ma120 | 4,339 / 0.0 / 0 / 0 | 5,428,988 / 0.0 / 0 / 0 |
| uf_ma200 | 4,259 / 0.0 / 0 / 0 | 5,371,122 / 0.0 / 0 / 0 |
| uf_prior_high_20 | 4,438 / 0.0 / 0 / 0 | 5,496,401 / 0.0 / 0 / 0 |
| uf_prior_high_55 | 4,403 / 0.0 / 0 / 0 | 5,472,715 / 0.0 / 0 / 0 |
| uf_prior_high_250 | 4,239 / 0.0 / 0 / 0 | 5,332,523 / 0.0 / 0 / 0 |
| uf_prior_low_10 | 4,448 / 0.0 / 0 / 0 | 5,503,218 / 0.0 / 0 / 0 |
| uf_prior_vol_20 | 4,438 / 0.0 / 0 / 0 | 5,496,401 / 0.0 / 0 / 0 |

工作帧：6,422,875 行 / 3,384 只 / 2018-01-08–2026-10-30；评估窗 5,510,001 行 / 1,779 个交易日。

### 3.2 uf_vol60 的 1.11e-16 是浮点路径差，不是口径差（独立定因）

`artifacts/fa3_vol60_ulp_rootcause.txt`（退出码 0，2019-07-01–2026-10-30）：

```
研究(vol60: pct_change) vs polars 除法 : max_abs_diff=1.1102230246251565e-16  nonzero=4,214,876  n=5,469,335
研究(vol60) vs DSL(ts_std(close/ts_delay-1,60)) : max=1.1102230246251565e-16  nonzero=4,214,876
polars 除法 vs DSL : max=0.0  nonzero=0
```

**结论：系统 DSL 与"普通除法"逐位相同（0.0）；差异 100% 来自研究侧 `ret1 = close.pct_change()` 与 `close/close.shift(1)-1` 的浮点路径。** 相对差上限 4.37e-15，超 1e-12 行数 0，null 位置与首根非空一致 → **可接受的浮点路径差异，不是口径差**，不阻断。
（被审报告 §7 把这归因于"`_safe_div` 掩码除法改变内核选择" —— 方向对一半：实测 `_safe_div` 与普通除法差 0.0，见 P3-3。）

### 3.3 复跑被审脚本（先备份 → 跑 → 比对 → 还原）

```
cp -p docs/.../F_CLASS_PARITY_20261107.json artifacts/F_CLASS_PARITY_20261107.orig.json   # sha e37071d1…
backend/.venv/Scripts/python.exe docs/factors/evidence/scripts/f_class_parity.py           # exit 0，20.3s
cp -p artifacts/F_CLASS_PARITY_20261107.orig.json docs/.../F_CLASS_PARITY_20261107.json     # 还原
sha256sum docs/.../F_CLASS_PARITY_20261107.json → e37071d1…（与原件一致）
```

结构化比对（`artifacts/parity_compare.txt`）：`N_DIFFS=2`，仅 `meta/elapsed_seconds`（26.5→20.3）与 `meta/generated_at`（14:36:40→15:53:03）；`factor_parity` 8 只的全部标量、`judgment_jaccard` 5 条、`row_counts`、`row_count_note` **逐字段相同**。该脚本不写 `data_dir`（只在 `:270` 读 `load_all`、`:279` 调 `to_spec`），复跑无副作用。

## 4. F-A4：台账与映射

- 自检脚本 `docs/factors/evidence/scripts/check_f_class_ledger.py` → `artifacts/ledger_check_rerun.txt`：**退出码 0**，6 组规则 `violations: 0`，`RECORD MISMATCHES: 0`，`RESULT: PASS`。
- 审核方独立复核（`artifacts/fa4_ledger_map.txt`，退出码 0）：
  - 台账 json `factors[8].id` = 8 只 F 类 id；`research_name` 与 `id` 各 8 个、均无重复 → **一对一成立**。
  - 台账 md 中 `研究名 | uf_ id` 行共 16 行，来自 §1 与 §2 两张表，各 8 行且两表相同 → 去重后 8 对，与 json 集合相等。
  - 台账 json 的 `formula_text` 与磁盘 `formula` **8/8 逐字相同**。
- 关于"台账 id 集合 == 磁盘 8 个 `uf_*.json`"这一前提：**不成立**。磁盘现有 **13** 个 `uf_*.json`，多出的 5 个是 `uf_auction_*`（mtime 2026-10-31，非本批）。本批 8 只与被审台账**无多无缺**，但"磁盘上正好 8 个"的事实描述是错的（P3-2）。

## 5. F-A5：幂等 —— 判 FAIL（本批最重要的缺陷）

### 5.1 代码现状（与"HEAD 无实现"一致）

- 工作区实现：`backend/app/factors/store.py:189`（`_NON_CONTENT_FIELDS`）、`:192-204`（`_canonical`）、`:207-215`（`content_signature`）、`:217-219`（`is_same_content`）、`:222-257`（`upsert_definition`）；调用方 `backend/app/api/factors.py:333-362`（`:341` version 固定 1 交给 store 裁决、`:356-358` 同内容则跳过 `_trial_nonempty`、`:360` 返回含 `unchanged` 的 dict）。
- `git show HEAD:backend/app/factors/store.py | grep -c "unchanged\|upsert_definition"` → **0**（HEAD 无此实现）；`git grep -n unchanged -- backend/app` 命中 `store.py:226/229/239/257` —— 注意 **`git grep` 默认搜的是工作区已跟踪文件，不是 HEAD**，不能拿它证明"HEAD 已有"。
- 缓存侧机制成立：`materialize_cache.py:125` 的键为 `f"{factor_id}|v{version}|{formula_text}|rows=…"` + 依赖列 digest，`scoring.py:376-379` 传 `spec.version` → version 不变则键不变。（未做端到端缓存命中率实测。）

### 5.2 探针一（干净路径）：通过

`artifacts/fa5_idempotency_probe.txt`（退出码 0，临时目录）：

```
r1 {'version': 1, 'unchanged': False}
r2 {'version': 1, 'unchanged': True}   bytes_equal True  mtime_equal True  registry_version 1
内容改变   → {'version': 2, 'unchanged': False}  bytes_changed True  mtime_changed True
再改 status → {'version': 3, 'unchanged': False}
```

即：**同一进程按同一形状写出去的定义，二次注册确实幂等**。若只看这一步，F-A5 成立。

### 5.3 探针二（真实受审对象）：不通过

把真实的 `D:/TSP/data/user_data/custom_factors/uf_vol60.json` **复制到临时目录**（未动数据目录），然后**逐字复刻** `api/factors.py:338-350` 构造的 definition（该请求模型 `CustomFactorCreateRequest`（`:236-242`）**没有 `lang` 字段**）做同内容二次注册：

```
stored_keys  [created_at, description, direction, formula, group, id, kind, label, lang, status, updated_at, version]
api_def_keys [created_at, description, direction, formula, group, id, kind, label,        status, updated_at, version]
same_content_raw False
repeat_POST_result {'ok': True, 'id': 'uf_vol60', 'version': 2, 'unchanged': False}
version_after 2   bytes_changed_vs_seed True
第三次同请求   {'version': 2, 'unchanged': True}      ← 此时盘上定义已被改写成"无 lang"，之后才幂等
```

**根因**：`content_signature`（`store.py:207-215`）比较除 `version/created_at/updated_at` 外的**全部键**；本批 8 个 json 是经 `store.register_definition` + `save_one` 写入的，**含 `lang:"dsl"`**；而 API 构造的 definition **不含 `lang`**（模型无此字段，`to_spec` 只是 `:72` 读默认值，`save_one`（`:35-36`）原样落盘不补字段）→ 键集不同 → 判为"内容变了"。

**影响**：本批 8 只中任一只被"同内容再 POST 一次"，version 1→2、文件被重写、`materialize_cache` 键（含 `v{version}`）整体换命名空间 → 正是契约 §7.4 要防的"整表重算"。而且该文件从此少一个 `lang` 键（语义等价，但定义文本被静默改写）。这不是"本批未涉及"的边缘情况，而是**受审 8 只的当前落盘形态**。

判据对照：F-A5 要求"同内容二次注册：version 不变、`unchanged=true`、盘上文件字节与 mtime 均不变" → **FAIL**（在真实定义上不成立）。

## 6. F-A6：单位量级（给结论与理由，不改契约）

自有复算（`artifacts/fa6_distribution_windows.txt`、`fa6_windows.json`，退出码 0；系统 DSL 与研究 `vol60` 两条路径分别算，二者差 ≤1e-17，互为交叉校验）：

| 评估域（`60*`/`00*`，非空，ddof=1） | n | mean | p01 | p50 | p99 | 落在 0.015–0.06 之外 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2019-01-01 – 2026-10-30（契约字面域） | 5,781,697 | 0.026182 | 0.009071 | 0.024858 | 0.054896 | **12.58%** |
| 2019-07-01 – 2026-10-30（被审记录值所用域） | 5,469,335 | 0.026068 | 0.009003 | 0.024706 | 0.054919 | **13.03%** |

**判定：PASS**，理由是三条区分力判据全部满足，而不是"看着像小数"：
1. **F-A6a**：p50 = 0.0249/0.0247 ∈ [0.015, 0.06] ✔；
2. **F-A6b**：p99 = 0.0549 < 0.10 ✔；
3. **F-A6c**：p01 = 0.0091/0.0090 ∈ (0, 0.02) ✔；
4. 交叉口径排除：百分点口径 p50≈2.5（越上界 ~40 倍）、方差口径 p50≈0.0006（越下界 ~25 倍）、年化口径 p50≈0.39（越上界 ~6 倍），三者都会被本判据拒掉 → 判据有区分力。

**同时明确对照结论（不改契约，只给审核意见）**：按**原始字面**「典型值 0.015–0.06，越界即 fail」判，本批 **FAIL** —— 12.58%（712,922 行）合法地落在区间外，主要集中在 p01–p10 一段（低波标的）。契约已在 2026-11-07 15:35–15:51 之间把该条改写为 A6a/b/c 并自述"原字面会误判"；我按**改写后**的现行文本判 PASS，并把"判据改写发生在审核过程中"单列为 P1-2。

## 7. E3 关键事实独立复算（只核关键事实）

`scripts/verify_st_claims.py` → `artifacts/st_claims.json`、`st_claims.log`（退出码 0）；cell 级复算 `artifacts/e3_cells.txt`；抽查 `artifacts/e3_spotchecks.txt`。

| E3 的说法 | 我的实测 | 结论 |
| --- | --- | --- |
| `st_history` 7,758 行 / 5,817 只 / 1,436 个 `flag_date` / 2019-01-01–2026-10-29 / True 986 / 空值 0 / 重复 0 | 完全一致 | **确认** |
| 2026-10-20 有 198 行批量 `st_flag=False` | `GROUP BY` 结果：2026-10-20 = 198 行，全 False（前后各日仅 1–2 行） | **确认** |
| as-of ST 家数 2026-10-19 由 192 掉到 0（当日有 bar 口径） | 10-19 = **192**、10-20 起 = **0**，持续到 2026-11-06（共 **14** 个交易日） | **确认** |
| （开发经理口径：218 → 20） | as-of 全部 ST 表 symbol（不要求当日有 bar）：10-19 = **218** → 10-20 = **20** | **确认**，与 E3 的 192→0 是**分母不同**，不是矛盾 |
| 9,780,842 格中 True 276,079（2.82%）、null 755,763（7.73%） | 完全一致；2018 年 755,758 格全 null；逐年 True 20,553/42,391/45,152/36,264/29,179/29,047/37,400/36,093 | **确认** |
| 2026-09-05 193 行 False、2026-09-07 202 行（200 True） | 193 / 202（200 True + 2 False） | **确认** |
| K 线缺 ST 记录的 2 只 = 001381.SZ、920085.BJ | ANTI JOIN 结果正是这 2 只 | **确认** |
| 2,141 个分区、5,813 只、`volume==0` 行数 0、close/volume 空值 0、instruments 5,536 行、现名含 ST 295 只（163 `*ST` + 132 `ST`） | 全部一致 | **确认** |

即：E3 关于"ST 表末端被 2026-10-20 的 198 行批量 False 截断、此后 14 个交易日 ST=True 恒为 0"的核心事实，**独立复算全部成立**。

## 8. 缺陷清单

### P1（阻断，必须修）

**P1-1 F-A5 键集不对称 → 本批 8 只同内容二次注册仍抬版本、仍重写文件**
- 位置：`backend/app/factors/store.py:207-215`（`content_signature` 全键比较）、`backend/app/factors/store.py:35-36`（`save_one` 原样落盘）、`backend/app/factors/store.py:72`（`lang` 仅读取默认值）、`backend/app/api/factors.py:236-242`（请求模型无 `lang`）、`:338-350`（构造的 definition 无 `lang`）。
- 复现：`artifacts/fa5_api_path_probe.txt`（临时目录，不动数据目录）→ `version 1→2`、`unchanged=False`、文件字节变化。
- 影响面：`uf_vol60/uf_ma120/uf_ma200/uf_prior_*` 全部 8 只（磁盘 json 8/8 含 `lang`）。任何"重放同一注册请求"的运维/迁移动作都会静默抬版本并使 `materialize_cache` 键整体换命名空间（`materialize_cache.py:125`、`scoring.py:376-379`）。
- 修复要求（由实现方决定做法，审核只给判据）：同内容二次注册在**含/不含 `lang` 的等价定义**上都必须 `version` 不变 + `unchanged=true` + 文件字节与 mtime 不变；修复后需给出覆盖"API 形状 vs 落盘形状"两种来源的回归证据。

**P1-2 判据文件在审核过程中被就地改写，且不受版本控制**
- `docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md` mtime 依次为 **15:35:28 → 15:45:52 → 15:51:09**（本次审核 15:38 开始）；`git status` 显示 `?? docs/architecture/`（整目录未跟踪），无 git 历史可回溯。
- 具体改动：§7.6 F-A6 由"典型值 0.015–0.06，越界即 fail"改为 F-A6a/b/c 三条；F-A5 行的"实现现状"注记在 15:44 又被改写一次（HEAD `96ba73d0` → `65c6e42f`，`store.py:209-250` → `207-257`，`api:333-362` → `333-360`）。
- 风险：验收判据在实现交付后、审核进行中被改写，等于"按结果改判据"；且审核方无法用版本号锚定判据（本报告只能以 sha256 `5eb97724…`（15:51:09）为快照）。
- 要求：判据冻结后再验收；契约入 git（至少提交一次基线），后续变更走评审并保留 diff。

### P2（须在批一收口前处理或明确挂账）

**P2-1 §7.4 与实现正面冲突（契约内部自相矛盾）**
- §7.4（`:746`）明文："改动点仅在 `api/factors.py` 保存分支，**不动 `registry`/`dsl`/`store`**"。
- 实际改动：`backend/app/factors/store.py` **+91/−1**（新增 `content_signature`/`is_same_content`/`upsert_definition`）；而 §7.6 F-A5 行又把 `store.py:207-257` 描述为现实现 → 同一份契约里"禁止"与"已发生"并存。
- 需架构师裁定：是放宽 §7.4，还是要求把逻辑收回 `api/factors.py`。（此条属契约裁定，不由审核方改。）

**P2-2 台账正文与事实不符（时间序过期，非造假）**
- `docs/factors/F_CLASS_REGISTRATION_20261107.md:3`："只登记台账与映射。**未写入运行库**（未调用 `POST /api/factors/custom`）、**未做数值对账**、**未改任何代码**、未改任何既有文件"。
- 实测：8 个 `uf_*.json` 于 **2026-11-07 14:30:24–26** 已写入 `D:\TSP\data\user_data\custom_factors\`（`created_at` 同为 14:30:24），早于台账定稿（md mtime 14:37:20）；同批已交付逐位对账报告；`backend/` 两个已跟踪文件在 15:35:28 被改（+99/−17）。
- 另 `:32`"现 `get_factor('uf_vol60')` 返回 `None`（实测）"只在不执行 `load_into_registry` 的进程成立，生产启动后不成立。
- 要求：台账状态行按当前事实重写（"已落盘 8 个定义、未走 POST API"，并写明谁在何时写入），避免后续按台账误判"未注册"。

**P2-3 同口径双 id 并存（契约 §7.5-3）**
- `backend/app/custom/research_factor_pack/factor_specs.py:53,55,63` 以裸 id 注册 `ma120`/`vol60`/`ma200`；`backend/app/factors/registry.py:342` 的 `_ensure_factor_providers()` 使它们在 import 后自动进注册表（实测：未 load 磁盘时注册表已有 192 条，含这 3 个）。与 `uf_ma120`/`uf_vol60`/`uf_ma200` 同口径，其中 `ma120`/`ma200` 的公式文本**逐字相同**（`ts_mean(close, 120/200)`），`vol60` 仅数学等价、文本不同（`(close-delay)/delay` vs `close/delay-1`）。
- 由此 `docs/factors/F_CLASS_REGISTRATION_20261107.md:73` 的"无（系统无 ma120）"在当前代码状态下已不成立（该 pack 的 specs 于 14:42 落盘，晚于台账 14:37）。
- 影响：F-A4 判据本身（台账内部一对一）仍成立，但**全局唯一性已被打破**，且未来策略若一用 `ma120` 一用 `uf_ma120` 即违反 §7.5-3。
- 要求：由架构师/因子工程师指定唯一 id（`uf_*` 与否），另一侧标 `replaced_by` 并禁用于策略。

**P2-4 台账登记的 label 与磁盘实际 label 8/8 不同，且磁盘版丢失语义**
- 例：台账 `60日收益标准差（日频，未年化）` vs 磁盘 `60日收益波动率`；台账 `120日均线（含当日）` vs 磁盘 `120日均价`；台账 `此前20日均量（不含当日）` vs 磁盘 `此前20日均量`。
- 台账 `f_class_registry.json` 的 `label` 与磁盘定义不一致 → 前端展示与台账语义分叉，且"含当日/未年化/不含当日"这些**口径关键语义**只活在台账里。要求：以台账 label 覆盖磁盘定义（或明确"label 仅展示、语义以台账为准"并写入契约）。

**P2-5 F-A6 记录值的评估域与判据声明不符**
- §7.6 F-A6a 写"`2019-01-01` 起"，但"开发经理复算 n=5,469,335"对应的实际域是 **2019-07-01 起**（我用同一工作帧、同口径复算 2019-07-01 起得到 n=5,469,335，2019-01-01 起得到 5,781,697）。数值本身可复现（p01/p50/p99 完全一致），但"n="与"起止"标注不自洽，后续按 n 反查口径会误判。

### P3（记录，不阻断）

**P3-1** F-A1 判据未声明"需先执行启动加载"。实测未 load 时 8 只全 `None`、load 后 8/8 可取。建议判据补一句"（启动期 `load_into_registry` 之后）"。
**P3-2** 任务前提"磁盘上 8 个 `uf_*.json`"不成立：实际 13 个（多 5 个 `uf_auction_*`，2026-10-31）。F 类 8 只无多无缺，但事实描述需更正。
**P3-3** 被审报告 §7 的 1 ULP 根因归因需更正：实测 DSL 与普通除法差 **0.0**，差异全部来自研究侧 `pct_change()`。
**P3-4** 被审报告"5 条判定 jaccard 全部 1.000"我未单独复算；由逐值对账（超 1e-12 行数 0、null 一致）可推出，除"阈值恰好落在 1 ULP 内"的极端巧合外无风险。

## 9. 不一致清单（报告值 / 实测值 / 差异原因）

| # | 报告中的说法（出处） | 实测值 | 差异原因 |
| --- | --- | --- | --- |
| 1 | "未改任何代码、未改任何既有文件"（`F_CLASS_REGISTRATION_20261107.md:3`） | `backend/app/api/factors.py` +8/−16、`backend/app/factors/store.py` +91/−1 已是 `M`（mtime 15:35:28）；另有 `research/strategy-search-20261107/` 下 5 个 `M` | 台账 14:37 定稿，早于 15:35 的代码改动 → **陈述在其后失效**；改动者不在本批 4 份产物内留痕（契约 §7.6 是唯一记载） |
| 2 | "工作区未提交改动"快照只列 2 个 `M`（`E3_DATA_AVAILABILITY_20261107.md:490-509`，快照 15:05） | 当前 **7 个 M**（5 research + 2 backend） | 15:05 之后才出现的并行改动；E3 的 15:05 快照在当时准确，**现已过期**（E3 自身 `:513` 已声明"快照之后的变化不属本次取证"） |
| 3 | "as-of ST 家数 192 → 0"（E3 §2.5） | 当日有 bar 口径 192 → 0 ✔；全部 symbol 口径 **218 → 20** ✔ | **不是矛盾**：分母不同（前者只算当日有 K 线 bar 的标的）。开发经理引用的 218/20 与我的复算一致 |
| 4 | "开发经理复算 n=5,469,335，p01 0.0090 / p50 0.0247 / p99 0.0549"（§7.6 F-A6 记录值） | 逐位复现：2019-07-01 起 n=5,469,335、0.009003 / 0.024706 / 0.054919 | 数值**可复现**；但契约 F-A6a 写的是"2019-01-01 起"，两处域不一致（P2-5） |
| 5 | "架构师独立复算 raw close、2019-01-01–2026-10-29、n=5,639,581，mean 0.026555 / p01 0.009244 / p50 0.025096 / p99 0.056152"（§7.6 F-A6 记录值） | raw close、2019-01-01–2026-10-29、同口径：**n=5,778,514**，mean 0.026519 / p01 0.009266 / p50 0.025059 / p99 0.056067 | 分位数与均值吻合到 1e-4 量级（口径一致），但 **n 差 138,933 行（−2.4%）**，其额外过滤条件不明 → **差异原因未知**，不猜 |
| 6 | "现 `get_factor('uf_vol60')` 返回 `None`（实测）"（台账 `:32`） | 未 load 时 `None`；`load_into_registry` 后返回 `version=1` 的 spec | 进程状态不同；生产启动即加载 → 该句只对裸 import 成立 |
| 7 | "磁盘 8 个 `uf_*.json`"（任务前提 / 台账口径） | 13 个（8 F 类 + 5 `uf_auction_*`） | 统计口径未排除既有定义 |
| 8 | "系统无 ma120"（台账 `:73`） | 注册表已有裸 id `ma120`（`ts_mean(close, 120)`，与 `uf_ma120` 同文本），`vol60`/`ma200` 同 | pack 的 `factor_specs.py` 于 **14:42** 落盘，晚于台账 14:37 |
| 9 | "1 ULP 源于 `_safe_div` 掩码除法与 `pct_change` 的内核路径差"（对账报告 §7） | DSL vs 普通除法 **0.0**；研究 `pct_change` vs 普通除法 1.11e-16（4,214,876 行） | 归因方向需收窄：差异全部在研究侧 `pct_change`，与 `_safe_div` 无关 |
| 10 | "重复 POST 同内容 → unchanged=true、version 不变"（§7.6 F-A5 靶值，隐含已满足） | **对真实 8 只定义不成立**：version 1→2、文件被重写 | `lang` 键不对称（P1-1） |

## 10. 未验证 / 超出本次范围

- **运行中的服务是否加载了新因子**：未重启、未部署，未核；`127.0.0.1:8000` 未探测（本批不允许重启服务）。
- **前端展示**：`group=研究补充` 的分组顺序与下拉项未核。
- **端到端缓存命中率**：F-A5 的"缓存不全表失效"由 `materialize_cache.py:125` 的键构成推出，未做命中率实测。
- **策略侧引用 `uf_*`**：不在本批范围。
- **`unit`/`scale_free`/`asset_types`/`tags` 未落盘**：与 §7.2 已登记的 P2 扩参缺口一致，本次未复验其下游影响。
- **E3 全篇**：按要求只核关键事实（ST 截断链路 + 表格规模），其余章节（上市天数、停牌、退市）未复算。

## 11. 结论与放行意见

1. **八只因子的"口径正确性"可以放行**：公式逐字等于契约 §7.1、`prior_*` 全部带 `ts_delay(...,1)`、warmup/deps 8/8 吻合、逐值对账 0 超差、台账映射一对一、量级判据三条全过。
2. **不能整体签 PASS**：F-A5 在受审的 8 只上判 **FAIL**（P1-1，可复现），且判据文件在审核期间被改写、未入版本控制（P1-2）。
3. 建议放行顺序：先修 P1-1（并给出"API 形状 vs 落盘形状"两种来源的回归证据）→ 契约冻结并入库（P1-2）→ 处理 P2-1/P2-3 的裁定与唯一 id 收敛 → 再复跑本报告 §0 的六项命令做回归。
4. 本报告未修改任何被审文件；`docs/factors/evidence/F_CLASS_PARITY_20261107.json` 在复跑后已按原件还原（sha256 `e37071d1…` 与复跑前一致）。

---

## 附录：可复跑产物

| 文件 | 内容 | 退出码 |
| --- | --- | ---: |
| `scripts/independent_f_class_check.py` → `artifacts/independent_f_class_check.json` | F-A3 审核方自有对账（20×250 切片 + 全窗 + vol60 分布） | 0 |
| `scripts/verify_st_claims.py` → `artifacts/st_claims.json` / `.log` | E3 ST 表结构与 as-of 家数，两种分母 | 0 |
| `artifacts/fa12_separate_process.txt` | F-A1/F-A2 另起进程逐只核 warmup/deps | 0 |
| `artifacts/fa_formula_and_disk.txt` | 契约 §7.1 vs 磁盘 formula 字符级比较 | 0 |
| `artifacts/fa3_vol60_ulp_rootcause.txt` | 1 ULP 定因（pct_change vs 除法 vs DSL） | 0 |
| `artifacts/parity_rerun.log`、`F_CLASS_PARITY_RERUN.json`、`parity_compare.txt`、`F_CLASS_PARITY_20261107.orig.json` | 复跑被审脚本 + 与原件结构化比对 + 原件备份 | 0 |
| `artifacts/fa4_ledger_map.txt`、`ledger_check_rerun.txt` | F-A4 台账自检与独立映射复核 | 0 |
| `artifacts/fa5_idempotency_probe.txt`、`fa5_api_path_probe.txt`、`fa5_worktree_diff.patch` | F-A5 两条路径探针 + 工作区 diff | 0 |
| `artifacts/fa6_distribution_windows.txt`、`fa6_windows.json`、`fa6_rawclose_probe.txt` | F-A6 两个评估域 + raw close 探针 | 0 / 0 / 1（后者第二段因列名写错中断，所需数字已输出） |
| `artifacts/e3_cells.txt`、`e3_spotchecks.txt` | E3 cell 级复算与抽查 | 0 |
| `artifacts/repo_state_at_report.txt`、`contract_7_4_to_7_6_snapshot.txt` | 报告时点仓库状态 + 契约 §7.4–§7.6 快照 | 0 |
| `artifacts/handoff_work.txt` | 上一轮（被打断）工作日志的抽取，便于追溯 | — |
