# D-EOS 末日结算缺陷修复 · 阶段1 交付报告

- 契约：`docs/architecture/CONTRACT_END_SETTLEMENT_20261108.md`（v1.0，37,195 B / `c3c6501f…`）
- 引擎：`backend/app/backtest/engine.py` 268,800 B / `ecc3d826…` → **269,940 B / `4243fe97…`**（git `+28 / −24` 行，净 +4 行）
- git HEAD：`22ed822ac5a6`；口径决策 D-1：默认臂维持末日强制清算、价基不动

## 1 验收结论（本轮判据逐条）

- **五臂/六臂末值落 C 值 ±0.05**：是。全部 6 个命中臂 Δ ≤ 0.01 元（见 §2 表）。
- **三臂逐字节不变**：`only_finalize_open_at_end` / `only_exit_signal_requires_profit` / `a0_10bp` 的 trades+equity（+drawdown）parquet sha256 与改前**完全相同**。
- **测试全绿**：`pytest backend/tests/backtest` 738 passed, 13 warnings in 196.34s (0:03:16) → **746 passed, 13 warnings in 159.10s (0:02:39)**（+8 = 新增用例，0 failed）；`test_risk_limits_scale.py` 22 passed in 3.16s。
- **自检器**：`verify_postfix.py` → TOTAL 69  PASS 69  FAIL 0

## 2 逐臂末值：D（改前）→ C（改后应为）→ 实测

| 臂 | D 改前 | C 契约值 | 改后实测 | Δ vs C | 总收益 改前→改后 | 年化 改前→改后 | MDD 改前→改后 | 笔数 |
|---|---:|---:|---:|---:|---|---|---|---:|
| `base_nodefaults_10bp` | 485,293.78 | 483,571.23 | **483,571.22** | -0.01 | -51.47% → -51.64% | -9.73% → -9.78% | -71.95% → -71.95% | 208 |
| `only_trailing_peak_price_close` | 485,293.78 | 483,571.23 | **483,571.22** | -0.01 | -51.47% → -51.64% | -9.73% → -9.78% | -71.95% → -71.95% | 208 |
| `only_execution_costs` | 485,420.69 | 483,698.12 | **483,698.12** | +0.00 | -51.46% → -51.63% | -9.73% → -9.78% | -71.94% → -71.94% | 208 |
| `only_entry_price_basis_raw` | 434,710.53 | 432,987.98 | **432,987.97** | -0.01 | -56.53% → -56.70% | -11.13% → -11.18% | -74.31% → -74.41% | 208 |
| `base_nodefaults_gross` | 527,074.75 | 525,402.74 | **525,402.74** | +0.00 | -47.29% → -47.46% | -8.67% → -8.71% | -71.08% → -71.08% | 208 |
| `only_block_limit_open` | 1,121,259.36 | 1,117,814.25 | **1,117,814.25** | +0.00 | +12.13% → +11.78% | +1.63% → +1.59% | -40.12% → -40.12% | 198 |

**方向性说明**：本例末值一律下降，只因末日**收盘 118.26 > 开盘 109.90**；末日收盘 < 开盘时同一修复会让末值上升。不得把"修复使收益下降 0.17pp"写成通用结论（契约 §5.1）。

| 必须不变的臂 | 改前末值 | 改后末值 | trades sha256 相同 |
|---|---:|---:|---|
| `only_finalize_open_at_end` | 478,212.34 | **478,212.34** | 是（全部产物） |
| `only_exit_signal_requires_profit` | 673,798.76 | **673,798.76** | 是（全部产物） |
| `a0_10bp` | 1,242,725.28 | **1,242,725.28** | 是（全部产物） |

## 3 落了什么（4 个 hunk，全部在 `_simulate_portfolio_matrix`）

| # | 条款 | 落点 | 内容 |
|---|---|---|---|
| H1 | S-1 / S-7 / I3 | 末根 K 线持仓体顶部（原 `:4104` 之后、`:4105` 之前） | 新增 `end_settlement` 守卫（`time_id == time_count-1 and not carry_out and not finalize_open_at_end`），逐持仓调用 `_try_sell(..., "end", ...)`；成功即 SETTLED 并 `continue`。该位置在 P1~P6 六条早退分支之前，没有任何一条能绕过。 |
| H2 | S-2 | 原链底 `end` 分支（`:4245-4250`） | 改成 `elif end_settlement:`，保留 `reason="end"` 作防御性重复，并加 `_count("end_branch_reached_after_settlement")` 让"不该发生"在 `stats["execution"]` 可见（不用 assert：引擎不在生产路径抛断言）。本轮 8 臂该键均未出现。 |
| H3 | S-3 / S-8 | post-loop `elif config.finalize_open_at_end:`（`:4400`） | 改成单一 MARKED 记账号 `else:`；`finalize=True` 臂走的还是原代码，逐字节不变。 |
| H4 | S-3 / I1 | post-loop `else:`（`:4436-4453`） | **删除** `_sell`（缺陷主路径：结算发生在末行权益写入之后）。默认臂只剩 P6 遗留走 MARKED 记账。 |

未触碰（逐项用 `git diff` 核过 0 命中）：`_calc_portfolio_stats_from_values`（I4/S-9）、`exit_prices` 价基 `:2617-2621`（S-5）、`MatcherConfig.finalize_open_at_end` 默认值 `:261`（S-10）、`carry_out` 分支（S-7）、`simulate_portfolio_legacy`（X-1）、`dsl.py` / 信号链 / `store.py` / 策略文件 / 生产库。

## 4 测试

| 文件 | 角色 | 用例 | sha256 |
|---|---|---|---|
| `backend/tests/backtest/test_end_settlement.py` | 新增 8 个 | T-EOS-1~5 + P3 + P5 + carry_out 反例 | `20b82bd1…` |
| `backend/tests/backtest/test_limit_down_close_exit.py` | 修订 1 个 | `test_stuck_position_at_window_end_is_recorded_portfolio_mode` 改为 MARKED 口径 | `e9f682f2…` |

逃逸路径覆盖：P1 末日建仓 → T-EOS-3；P2 pending → T-EOS-2；P3 risk 闸门 → `test_p3_*`；P4 信号闩锁 → T-EOS-1；P5 延展到期 → `test_p5_*`；P6 末日不可成交 → T-EOS-4；`carry_out` 不触发 → `test_carry_out_segment_does_not_settle`；finalize 臂不变 → T-EOS-5。

## 5 两处必须点名的偏差

1. **既有用例按缺陷行为断言，已随契约修订 1 条**（契约 §6 R-1 的 (a) 类）：`test_limit_down_close_exit.py::test_stuck_position_at_window_end_is_recorded_portfolio_mode` 原断言 `exit_reason == "signal"`（期末不可成交却以封板价"成交"、并保留递延原因）—— 正是 §1.3 P6 / §7.1 A-R5 描述的缺陷行为。改后按 I3 断言 MARKED（`exit_reason="end"`、`open_at_end=True`、`pnl_amount=0`、市值留末行、现金不含）。同用例里的 matrix↔legacy 逐字段 parity 断言同时失效：legacy 是同型缺陷 **X-1**，本次按契约不动 ⇒ 已把"两路径分道"显式写成断言，而不是删掉。
2. **T-EOS-3 的 `duration` 与契约文本不符，按引擎现值断言 `duration == 1`**：契约写 `duration==0`，但 matrix_native 的 `hold_days` 在成交日初值为 1（`:3427`），legacy 路径才是 0（`:3751`/`:5118`）。该字段本次未改语义（改前改后同为 1），故以引擎现值为准。

另：P1（末日建仓）在 matrix 路径只有一个入口 —— `plan_at_signal_close` 的"收盘计划 → 次日开盘成交"（`pending_buy_plans` 在 `:3945-3948` 无条件执行）；开盘阶段的 `_process_entries` 在末根被 `:3996` 的 `time_id < time_count - 1` 挡住。两个 P1 用例按此构造。

## 6 缺陷 B 的暴露面（契约 §8.2 要求显式承认）

修 A 不改末日价基（SETTLED 仍取该臂 `exit_fill` 的末根价 = 末日**开盘**），所以缺陷 B 原样保留并**从 4 笔扩到 5 笔**：688143.SH 由"账面按收盘、成交按开盘"的伪盯市，变成与其余 4 只一样的"末日开盘清算"。这是本次改动集必须显式认下的代价，不作"顺带改善"表述。

## 7 复现（一条命令 / 每步 < 5 分钟）

```
cd C:\work\sourcecode\tick-stock-panel
backend\.venv\Scripts\python.exe research\s01b-20261108\postfix_20261108\verify_postfix.py   # 69 项判据，exit 0
```

重跑单臂（新目录，不覆盖 `five_a` / `results`）：

```
cd research\s01b-20261108\postfix_20261108
..\..\..\backend\.venv\Scripts\python.exe run_arm_postfix.py --tag base_nodefaults_10bp
..\..\..\backend\.venv\Scripts\python.exe run_arm_postfix.py --tag only_entry_price_basis_raw --inject-file ..\five_a\inject\only_entry_price_basis_raw.json
```

回滚：`baseline/engine_before.py` 即改前逐字节快照（268,800 B / `ecc3d826…`）；`engine_diff.patch` 为完整 diff，反向应用即回滚。

## 8 上游未动 / 未验证

| 文件 | 字节 | sha256 | 与改前 |
|---|---:|---|---|
| `research/s01b-20261108/REPORT.md` | 52,097 | `e60cd0b857f40fb227dad704e62c6d132fbba9e5107f1c53ba3870c436d7ca9b` | 未变（`e60cd0b8…`） |
| `research/s01b-20261108/metrics_table.md` | 2,738 | `d025d8ce96f98cc2a204d6a60c82b693306cdb15d0f597b6627d0070a915cf3a` | 未变（`d025d8ce…`） |

未做/未验证：

- **阶段2 的 8 臂全量重跑**未做（本轮按派单只跑 6 个命中臂 + 3 个不变臂 = 9 次运行，未跑 `a0_*` 其余 12 个臂与 30bp/gross 变体）。
- **X-1 / X-2 未修**：`simulate_portfolio_legacy` 仍是同型缺陷且不认该开关，本轮只在上面的用例里显式登记两路径分道。
- **报表换数未做**：`REPORT.md` 的 8 臂表仍按 D 口径，等研究侧一次性换数（契约 §5.3 / X-5）。
- 未提交、未部署、未重启服务、未写生产库 strategy row。

## 9 补充验证（只追加，不改上文任何数字）
见同目录 `SUPPLEMENT_phase1_20261108.md`：新用例对旧引擎 A/B（6/8 失败，证明用例钉住缺陷）、`a0_10bp` 真重跑证据与一处措辞更正（该臂无 drawdown 产物）、一次子进程 0xC0000005 偶发失败的处置记录、本轮四次复跑的退出码、不经 verify 脚本的独立复算。
