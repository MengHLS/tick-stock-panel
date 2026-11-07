# F 类八只因子：系统 DSL 求值 vs 研究侧 `add_indicators` 逐位对账（F-A3）

生成：`docs/factors/evidence/scripts/f_class_parity.py`（本次运行 2026-11-07T14:36:40，耗时 26.5s，polars 1.44.1，HEAD `65c6e42f` @ `dev`）

**结论：8 只全部通过 F-A3。** 7 只 `max_abs_diff = 0.0`；`uf_vol60` 为 `1.11e-16`（1 ULP，超过 1e-12 的行数 0）；null 行两侧完全一致；每只每 symbol 的首根非空位置完全一致；5 条判定 jaccard 全部 `1.000`；注册 warmup 逐一吻合 61 / 121 / 201 / 21 / 56 / 251 / 11 / 21。

## 1. 口径与路径

| 项 | 取值 |
| --- | --- |
| 工作帧 | 研究侧 `common.open_market()` + `common.load_panel(WARMUP_START, EVAL_END)`，60/00 开头、含 ST 与涨跌停标记，`sort(symbol, date)`；只读 import，未改 `common.py` |
| 研究侧计算 | `common.add_indicators()`（列名 vol60/ma120/ma200/prior_high20/prior_high55/prior_high250/prior_low10/prior_vol20） |
| 系统侧计算 | `app.factors.dsl.compile_formula(公式原文).frame_transform(同一帧)` —— 与 `app/strategy/scoring.py:391` 生产物化路径同一函数；本脚本刻意不经 `materialize_cache`，避免向 data_dir 写缓存 parquet |
| 对比窗口 | 2019-07-01 ~ 2026-10-30 |
| 预热段 | 2018-01-08 ~ 2019-06-28（912,874 行） |
| 全帧 | 6,422,875 行 / 3,384 只，2018-01-08 ~ 2026-10-30 |
| 分块 / 抽样 | 无。单次全帧，无抽样、无分块、无按 symbol 分批 |
| 容差 | `1e-12`（契约 F-A3 原值，未放宽） |

复现：`cd <repo> && backend/.venv/Scripts/python.exe docs/factors/evidence/scripts/f_class_parity.py`（全量数值见同目录 `F_CLASS_PARITY_20261107.json`）

## 2. 逐只逐位对账（窗口内）

| 因子 id | 研究列 | n（两侧非空） | max_abs_diff | 超 1e-12 行数 | null 不一致行数 | 首根非空不一致 symbol | 首根非空日期（系统/研究） | warmup 注册/期望 | 判定 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| `uf_vol60` | `vol60` | 5,469,335 | 1.1102230246251565e-16 | 0 | 0 | 0 | 2018-04-11 / 2018-04-11 | 61 / 61 | PASS |
| `uf_ma120` | `ma120` | 5,428,988 | 0.0 | 0 | 0 | 0 | 2018-07-06 / 2018-07-06 | 121 / 121 | PASS |
| `uf_ma200` | `ma200` | 5,371,122 | 0.0 | 0 | 0 | 0 | 2018-11-05 / 2018-11-05 | 201 / 201 | PASS |
| `uf_prior_high_20` | `prior_high20` | 5,496,401 | 0.0 | 0 | 0 | 0 | 2018-02-05 / 2018-02-05 | 21 / 21 | PASS |
| `uf_prior_high_55` | `prior_high55` | 5,472,715 | 0.0 | 0 | 0 | 0 | 2018-04-02 / 2018-04-02 | 56 / 56 | PASS |
| `uf_prior_high_250` | `prior_high250` | 5,332,523 | 0.0 | 0 | 0 | 0 | 2019-01-17 / 2019-01-17 | 251 / 251 | PASS |
| `uf_prior_low_10` | `prior_low10` | 5,503,218 | 0.0 | 0 | 0 | 0 | 2018-01-22 / 2018-01-22 | 11 / 11 | PASS |
| `uf_prior_vol_20` | `prior_vol20` | 5,496,401 | 0.0 | 0 | 0 | 0 | 2018-02-05 / 2018-02-05 | 21 / 21 | PASS |

首根非空：按 symbol 内交易日序号（1-based）逐只比较，全帧 3,384 只中不一致 0 只；上表日期为全帧首个非空日（两侧同值，说明预热不多不少）。

`uf_vol60` 差异量级补充（如实报告，未做美化）：非零差行数 4,214,876，全部为 1 ULP，`max_abs_diff` = 1.1102230246251565e-16，非零行的最大相对差 4.370e-15。

F-A6 量级自检（`uf_vol60`）：系统侧 mean 0.0261 / p50 0.0247 / p01 0.0090 / p99 0.0549，落在契约 §7.6 F-A6 给的 0.015–0.06 区间；百分点口径会是 2.5 左右，因此单位为 ratio。

## 3. 判定一致率（口径决定 §1.7 第 2 条）

| 判定 | n | both_true | only_sys | only_res | jaccard | 研究侧触发率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| close_gt_prior_high_20 | 5,496,401 | 272,155 | 0 | 0 | 1.000000 | 4.952% |
| close_gt_prior_high_55 | 5,472,715 | 143,778 | 0 | 0 | 1.000000 | 2.627% |
| close_lt_prior_low_10 | 5,503,218 | 487,212 | 0 | 0 | 1.000000 | 8.853% |
| volume_gt_1p5_prior_vol_20 | 5,496,401 | 817,835 | 0 | 0 | 1.000000 | 14.879% |
| close_gt_ma200 | 5,371,122 | 2,567,466 | 0 | 0 | 1.000000 | 47.801% |

`close < prior_low_10` 研究侧触发率 8.853%，与 `caliber-decisions-20261107` §1.2 记载的 8.853% 一致（独立复算吻合）。

## 4. 行数口径核对（任务书 6,422,875 行 vs caliber §1.2 的 5,470,011~5,510,001）

| 口径 | 实测值 |
| --- | ---: |
| 全帧（2018-01-08 ~ 2026-10-30，含预热段） | 6,422,875 行 / 3,384 只 |
| 预热段（2018-01-08 ~ 2019-06-28） | 912,874 行 |
| 评估窗口（2019-07-01 ~ 2026-10-30） | 5,510,001 行 / 3,384 只 / 1,779 个交易日 |
| 评估窗口内 in_universe（研究侧门槛：observed_bars≥120、非 ST、raw_close≥3、prior_amount20≥1e8、volume>0） | 2,543,484 行（46.16%） |

结论：**6,422,875 与 5,510,001 是同一工作帧的两种口径**，差额 5,510,001 行 = 预热段行数（6,422,875 − 912,874 = 5,510,001，逐行核对相等）。caliber §1.2 的 5,470,011~5,510,001 是**各因子/各对比两侧均非空的有效行数**（长窗口因子预热更长，有效行更少；本报告各只 n 落在 5,332,523~5,503,218），**不是**股票池或 ST 过滤造成的——in_universe 只有 46.16%，与本批 n 不在同一量级。任务书的 3,384 只与实测一致。

## 5. 注册与落盘清单（`D:/TSP/data/user_data/custom_factors`）

| 文件 | 状态 | sha256（前 12 位） |
| --- | --- | --- |
| `cf_auction_resonance.json` | 未改动（注册前后 sha256 相同） | `70d20540a7f3` |
| `uf_auction_post0920_match_growth.json` | 未改动（注册前后 sha256 相同） | `840c65e4cfa7` |
| `uf_auction_tail_imbalance.json` | 未改动（注册前后 sha256 相同） | `1bdc6e8d288f` |
| `uf_auction_tail_match_growth.json` | 未改动（注册前后 sha256 相同） | `6c8f04a6c525` |
| `uf_auction_volume_surprise.json` | 未改动（注册前后 sha256 相同） | `19957bcd78d9` |
| `uf_auction_volume_vs_prev.json` | 未改动（注册前后 sha256 相同） | `8dc6abc6a451` |
| `uf_vol60.json` | 新增 | `c9041ba4930a` |
| `uf_ma120.json` | 新增 | `3ddb904acc72` |
| `uf_ma200.json` | 新增 | `cf96176f8458` |
| `uf_prior_high_20.json` | 新增 | `e3070878b547` |
| `uf_prior_high_55.json` | 新增 | `1f0ce5c6d836` |
| `uf_prior_high_250.json` | 新增 | `9f95286b8f97` |
| `uf_prior_low_10.json` | 新增 | `e5885f47f435` |
| `uf_prior_vol_20.json` | 新增 | `fa8667bc5e6f` |

注册链路：`store.to_spec(definition)` → `store.register_definition()`（= `to_spec` → `register_factor`） → `store.save_one()`；`warmup_bars` / `dependencies` 全部由 DSL 编译推导，未手填。`kind=custom`、`lang=dsl`、`version=1`、`group=研究补充`、`direction=none`、`status=draft`（契约 §7.5-5：未过 F-A3 不得标 active；本批只给证据，不改状态）。

注册后一致性校验：另起进程执行 `store.load_into_registry(data_dir)`（与启动期加载同一函数）后逐只 `get_factor`，8 只全部取到，warmup 61/121/201/21/56/251/11/21 逐个吻合，依赖分别 {close}/{close}/{close}/{high}/{high}/{high}/{low}/{volume}。

## 6. 实测 / 未验证

**实测（本报告数值全部来自本次运行）**

- 8 只因子系统 DSL 与研究 `add_indicators` 的逐值对账（n、max_abs_diff、超容差行数、null 不一致、首根非空）。
- 5 条判定 jaccard（含 `close < prior_low_10` 触发率 8.853% 与 caliber §1.2 记载吻合）。
- 行数与股票数口径（6,422,875 / 912,874 / 5,510,001 / 3,384 / in_universe 2,543,484）。
- 8 个 uf_*.json 落盘、`load_into_registry` + `get_factor` 可取、warmup 与契约逐一吻合。

**未验证（不得据此声称已生效）**

- **运行中的服务是否已加载新因子**：本批未重启、未部署。收尾时 `127.0.0.1:8000` 无监听，因此「线上已加载」既未验证也不存在；新因子只在下次启动时由 `load_into_registry` 装载。
- 前端因子下拉/因子研究页对 `group=研究补充` 的展示与排序。
- 回测/信号链端到端引用 `uf_*`（策略侧接入不在本批范围）。
- `unit` / `scale_free` / `asset_types` / `tags` 未落盘（`to_spec` 不读这些字段，契约 §7.2 已登记为 P2 扩参缺口）；本批未改引擎，故 `uf_vol60` 的 ratio 量纲与 `uf_prior_high_*` 的价格量纲在注册表内不可区分，需台账登记。

## 7. 根因假设（`uf_vol60` 的 1 ULP）

研究侧 `ret1 = close.pct_change()`；系统侧为 `close / ts_delay(close, 1) - 1`，其中除法走 `dsl.py:386` 的 `_safe_div`（`when(分母非空且非0).then(a/b).otherwise(None)` 的掩码除法）。两者数学等价，但掩码除法与 `pct_change` kernel 的浮点执行路径不同（分母校验改变内核选择/SIMD 路径），结果相差 1 ULP。**未放宽容差**：判据仍为 `1e-12`，超限行数 0；不存在口径差（null 位置一致、首根非空一致、判定 jaccard 为 1）。

