# ROLLBACK_NOTES_20261108 — 生产策略文件回滚成基线（只追加记录）

- 任务来源：@开发经理 转交（策略经理裁定「回滚成基线——生产目录只放通过验收的策略」）
- 回滚时间：2026-11-08 17:59:44 – 18:01:33（Asia/Shanghai，China Standard Time；归档复制 17:59:44，整文件还原 18:00:1x，复核脚本 18:00:55，目录终态清单 18:01:33）
- 执行者：系统开发工程师
- 纪律：未提交、未部署、未重启；未改 `backend/`（`risk_limits.py` 三个改动集保持原状）、未碰其它策略、未碰 `dsl.py`/信号链/回测引擎核心/`store.py`、未写 `D:\TSP` 生产库 strategy row。

## 1. 动作 1 · 归档变体（字节级复制，未覆盖任何已有快照）

| 项 | 值 |
| --- | --- |
| 源（回滚前生产文件） | `D:\TSP\data\strategies\custom\custom_mw7fvp17.py` |
| 源 size / sha256 | 5510 B / `918254f0e2bec567a9f3c593db258e4fd8fc54e24e111c2ef16e7bfdda5b2153` |
| 归档目标 | `research/s01b-20261108/prod_file_snapshots/custom_mw7fvp17.py.variant_5510B_918254f0.py` |
| 归档 size / sha256 | 5510 B / `918254f0e2bec567a9f3c593db258e4fd8fc54e24e111c2ef16e7bfdda5b2153` |
| 复制后校验 | `MATCH=True`，`sha_ok_918254f0=True`（与源逐字节相同） |
| 目标是否已存在 | 否（同名不存在，未启用时间后缀，未覆盖任何文件） |

`prod_file_snapshots/` 现有三个文件（彼此独立，均未被覆盖）：

| 文件 | size | sha256 |
| --- | --- | --- |
| `custom_mw7fvp17.py.pre_note_5392B_4118aa61.py` | 5392 | `4118aa6165d1416efbaa44fb6507ad27f73646a90347c61beae7140fa7954c51` |
| `custom_mw7fvp17.py.step1_4472B_2cc00778` | 4472 | `2cc007785170843ebff01a3693b6f2fac4efe051d21bb498c897983a5f2fc364` |
| `custom_mw7fvp17.py.variant_5510B_918254f0.py`（本轮新增） | 5510 | `918254f0e2bec567a9f3c593db258e4fd8fc54e24e111c2ef16e7bfdda5b2153` |

## 2. 动作 2 · 整文件还原基线（用 `.bak_20261108` 整文件覆盖，无手工编辑、无逐行 patch）

复制方式：`[System.IO.File]::Copy($bak, $prod, $true)`（字节级，PowerShell 未做任何文本解码/编码转换）。

| 项 | 回滚前 | 回滚后 |
| --- | --- | --- |
| 生产文件 size | 5510 B | **3449 B** |
| 生产文件 sha256（全串） | `918254f0e2bec567a9f3c593db258e4fd8fc54e24e111c2ef16e7bfdda5b2153` | **`61c237c6cdb2a4391524c48982cd7529606f1ce9d6dabf235527ff702f94b2dd`** |
| `.bak_20261108` size | 3449 B | 3449 B（未改动） |
| `.bak_20261108` sha256 | `61c237c6cdb2a4391524c48982cd7529606f1ce9d6dabf235527ff702f94b2dd` | `61c237c6cdb2a4391524c48982cd7529606f1ce9d6dabf235527ff702f94b2dd` |

断言实测：

```
RESTORED size = 3449
RESTORED sha256(full) = 61C237C6CDB2A4391524C48982CD7529606F1CE9D6DABF235527FF702F94B2DD
assert size==3449 : True
assert sha==61c237c6cdb2a4391524c48982cd7529606f1ce9d6dabf235527ff702f94b2dd : True
bak before: size=3449 sha=61C237C6CDB2A4391524C48982CD7529606F1CE9D6DABF235527FF702F94B2DD
bak after : size=3449 sha=61C237C6CDB2A4391524C48982CD7529606F1CE9D6DABF235527FF702F94B2DD
assert bak unchanged : True
```

还原后源码内容抽查（UTF-8 解码读回，非编辑）：

```
EXECUTION_BACKEND = "matrix_native"
STOP_LOSS = None
MAX_HOLD_DAYS = 60
REQUIRED_FEATURES = ["close", "ma20", "ma60"]
      "name": "双均线 20/60 金叉",
      "tags": ["趋势", "双均线", "S01"],
```

即：无 `TRAILING_STOP` / `TRAILING_TAKE_PROFIT_ACTIVATE` / `TRAILING_TAKE_PROFIT_DRAWDOWN` 三个变体常量，无 `backtest_defaults` 段，无 `S01b` 字样，`STOP_LOSS` 回到 `None`、`MAX_HOLD_DAYS` 回到 60。

## 3. 动作 3 · 前端列表与生产装载复核（只读，未启动/未重启服务）

脚本：`research/s01b-20261108/_verify_rollback.py`（本轮新增，只读；目录列表与 `backend/app/main.py` 一致：research + custom + ai + composite），
结果：`research/s01b-20261108/rollback_verify_result.json`（4,449 B，18:00:55），退出码 **0**，13 项判据全 True。

`list_strategies(include_research=False)` → **5 条**，含 `custom_mw7fvp17`：

| id | name | tags |
| --- | --- | --- |
| `custom_factor_first_board_chain_strict_rebreak` | 事件链首次收盘突破排名策略 | factor, auto-generated |
| `custom_khunter_limit_up_pullback` | 涨停回马枪 | 涨停, 回调, 回马枪, 实验 |
| `custom_mvoa5yy6` | 首板前次结构 + 当前确认方式 | 自定义, 矩阵, 均线, 量比, 乖离率, 相对位置, 高开过滤 |
| `custom_mw7fvp17` | **双均线 20/60 金叉** | **趋势, 双均线, S01** |
| `first_limit_pullback_3f_runner_t74` | 首板3F回踩 · T74 Runner | 首板, 回踩, 3F, T74, 实验 |

`custom_mw7fvp17` 的 `backtest_defaults` = `{}`（null），变体 5 项口径
（`trailing_peak_price` / `entry_price_basis` / `block_limit_open` / `finalize_open_at_end` / `execution_costs`）全部不存在；
该条目 JSON 全文不含这 5 个键名（`item_json_no_variant_key = true`）。

生产装载（4 个目录合并）：`engine_loaded_count = 10`，`load_errors = []`（0 条）：

```
ai_26a1525f69, ai_75a67366, ai_b8183b64,
custom_factor_first_board_chain_strict_rebreak, custom_khunter_limit_up_pullback,
custom_mvoa5yy6, custom_mw7fvp17, factor_rank_research,
first_board_chain_rebreak, first_limit_pullback_3f_runner_t74
```

判据全表（`rollback_verify_result.json.checks`，全 True，退出码 0）：

```
prod_size_3449 true | prod_sha_61c237c6 true | prod_bytes_equal_bak true
list_count_5 true | target_present true
name_equals_baseline true | name_no_S01b true
tags_equals_baseline true | tags_no_S01b true
backtest_defaults_absent true | item_json_no_variant_key true
loaded_10 true | load_errors_0 true
```

## 4. 动作 4 · 生产目录终态清单（`D:\TSP\data\strategies\custom`，18:01:33）

| 文件 | size (B) | sha256 |
| --- | --- | --- |
| `.seeded_v1` | 24 | `85d51c292ad2b4eb47a5bcf35696794cf21c9c3f2f307c365ccd6e10aab5d1c0` |
| `custom_factor_first_board_chain_strict_rebreak.py` | 1394 | `7fc46deb96b14f6c84aa172969471277007cc8a8398e43b024f446f18781d8cc` |
| `custom_khunter_limit_up_pullback.py` | 12122 | `684f5e82a7eff380ce58cd4d927aa80e925726f5f8170b4f57a2bc464ce3a4e5` |
| `custom_mvoa5yy6.py` | 10741 | `36b6bf61829d6fbd71cd48df7ea82dbab1c470c01c683fb76eb2f512fbc79be2` |
| `custom_mvoa5yy6.py.bak-20261026-gap-filter` | 10578 | `c03c962cad5aa4b0ea654f49b256f5d9b5f05ed4ddd2fda903c3f10e20669b63` |
| **`custom_mw7fvp17.py`** | **3449** | **`61c237c6cdb2a4391524c48982cd7529606f1ce9d6dabf235527ff702f94b2dd`** |
| `custom_mw7fvp17.py.bak_20261108` | 3449 | `61c237c6cdb2a4391524c48982cd7529606f1ce9d6dabf235527ff702f94b2dd` |

- 目标文件与 `.bak_20261108` **逐字节相同**（`prod_bytes_equal_bak = true`，sha 全串一致）。
- 中间件断言：`bad_count = 0`——目录内**无** `.step1` / `.py.tmp` / `.py.variant` / `.tmp` / `.new` 任何文件。
- 文件数 7，全部为本轮之前既有的 6 个 + 目标文件；除「目标文件被整文件覆盖」与「`.bak_20261108` 未动」外**未新增任何文件**。
- 唯一子目录 `__pycache__/`（Python 字节码缓存，非策略文件）：本轮只读复核用 `backend/.venv`（CPython 3.11）加载时，`custom_mw7fvp17.cpython-311.pyc` 因源文件 size/mtime 变化被自动重编译（5,006 B，18:00:33），内容对应基线源码；未手工写入、不属于本轮新增的中间件。

## 5. 研究侧文件未被改动（本轮前后同值）

| 文件 | size | sha256 |
| --- | --- | --- |
| `REPORT.md` | 52,097 | `e60cd0b857f40fb227dad704e62c6d132fbba9e5107f1c53ba3870c436d7ca9b` |
| `PREREG_S01B_20261108.md` | 4,446 | `2343971950eb41728cfbbdfdde2b23414ff8a009b82692427f78eb4a02d233ca` |
| `metrics.json` | 13,937 | `282e090c5915a354a41e0a51590b8eedb604d96f7953d6418c57fd1a071d0247` |
| `report_metrics.py` | 7,970 | `38a67c9fb87eed55cbeb8e0f3440947693f1585cab6d47a0bb2901c2c233f75c` |
| `metrics_table.md` | 2,738 | `d025d8ce96f98cc2a204d6a60c82b693306cdb15d0f597b6627d0070a915cf3a` |

本记录为新增文件（`ROLLBACK_NOTES_20261108.md`），`REPORT.md` 未追加、未改动。

## 6. 复现说明

变体复现 = 从归档快照复制回生产文件并保持 META，四臂按 PREREG 重建约半天。

即：`research/s01b-20261108/prod_file_snapshots/custom_mw7fvp17.py.variant_5510B_918254f0.py`
→ 覆盖 `D:\TSP\data\strategies\custom\custom_mw7fvp17.py`（sha 应回到 `918254f0…`），
四臂（a0/a1/a2/a3 + a4/a2h 等按 `PREREG_S01B_20261108.md`）重跑约半天。

## 7. 未做 / 待确认

- 未提交 git（`research/` 在仓库内，当前为未跟踪新增 `?? research/s01b-20261108/`；本记录与脚本均未 `git add`、未 commit）。
- 未部署、未重启服务；服务若在运行且已缓存模块，需按运维流程重启才会加载基线代码（本轮按纪律未做）。
- 未写 `D:\TSP` 生产库 strategy row（列表来自文件扫描，不依赖 DB 行）。
- 判死结论（F1+F4 成立）与四臂数字均未改动，研究价值仍见 `REPORT.md`。
