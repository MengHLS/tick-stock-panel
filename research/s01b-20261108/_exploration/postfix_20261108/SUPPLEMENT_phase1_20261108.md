# 阶段1 补充验证（只追加，不改动 REPORT_postfix_20261108.md 的任何原有数字）

生成时间：2026-11-08 22:01:26
引擎（本文所有实验同一份）：269,940 B / `4243fe97723dad20d01bd440783cf71ea6ef05c55a9ffd4652492031e40d8386`

## S1 新用例对旧引擎的 A/B（用例是否真的守得住缺陷）

做法：把 `baseline/engine_before.py`（268,800 B / `ecc3d826…`）临时覆盖到
`backend/app/backtest/engine.py`，跑新增的 8 个用例，`finally` 里恢复改后版本并按 sha256 校验恢复成功。
产物：`ab_old_engine_tests.txt`（17,908 B / `7522f988e9bbb571fbaa0eefb52a1e99e7a55ebcbabdc01a850ed0afeee2761c`）

结果（旧引擎）：**6 failed, 2 passed** ⇒ 新用例确实钉住缺陷，不是恒真断言。

```
FAILED backend\tests\backtest\test_end_settlement.py::test_t_eos_1_signal_latch_on_last_bar_is_settled
FAILED backend\tests\backtest\test_end_settlement.py::test_t_eos_2_pending_exit_is_settled_as_end
FAILED backend\tests\backtest\test_end_settlement.py::test_t_eos_3_last_bar_entry_settles_same_open_price
FAILED backend\tests\backtest\test_end_settlement.py::test_t_eos_4_blocked_sell_on_last_bar_is_marked
FAILED backend\tests\backtest\test_end_settlement.py::test_p3_risk_latch_on_entry_day_does_not_escape_settlement
FAILED backend\tests\backtest\test_end_settlement.py::test_p5_hold_policy_decision_on_last_bar_does_not_escape
6 failed, 2 passed in 4.67s
exit=1
```

两个在旧引擎下也通过的用例属设计如此，不是漏网：
- `test_t_eos_5_finalize_open_at_end_still_marks`：守的是 finalize 臂**不变**（S-8），旧引擎本来就对；
- `test_carry_out_segment_does_not_settle`：守的是 carry_out **不触发**（S-7），旧引擎同样不触发。

恢复校验：engine.py 回到 `4243fe97723dad20d01bd440783cf71ea6ef05c55a9ffd4652492031e40d8386`（same=True）。

## S2 `a0_10bp` 是**真重跑**，不是拷贝

`postfix_20261108/a0_10bp/` 的 `result.json` 与 `results/a0_10bp/result.json` **不同**
（`e7503e1b…` vs `b9dbf332…`，run_id `cf35b2e6b4` vs `d1487abc07`，elapsed 10.5s vs 44.1s），
而 `trades.parquet`（22,854 B / `639be869…`）与 `equity.parquet`（`1fa5003b…`）与改前**逐字节相同**，
`final_equity` 1,242,725.28、`open_at_end_count` 5、`execution` 13 键全部一致。
⇒ S-8 有实测证据（重跑后产物不变），不是「复制一份说它没变」。

更正 REPORT §1/§2 的一处措辞：`a0_10bp` 三个产物里**只有 trades + equity**——该臂目录历来无
`drawdown.parquet`，verify 的「字节不变 a0_10bp/drawdown.parquet」一项据此记 skip（不是漏检）。

## S3 一次偶发失败的处置记录（不隐瞒）

改后第一次全量复跑（本轮 22:0x）：**1 failed, 745 passed** ——
`test_worker_process.py::test_spawn_mining_writes_four_artifacts_and_returns_compact_summary`，
失败点是子进程退出码 `3221225477`（0xC0000005，原生访问冲突），不是任何断言逻辑。
判为环境偶发，依据三条：
1. 同一引擎字节在 21:43 的全量跑里通过（746 passed）；
2. 该用例单独跑通过（1 passed），该模块单独跑 13 passed；
3. 紧接着的第二次全量复跑 **746 passed, 0 failed**（159.88s）。
与本次改动的关系：改动是纯 Python 记账位置调整，不触碰线程/进程/原生缓冲；崩溃发生在 mining 子进程内。
本条作为「已知偶发」登记；未改该用例、未放宽任何断言。

## S4 本轮复跑的退出码

| 命令 | 结果 | 退出码 |
|---|---|---|
| `pytest backend/tests/backtest -q`（第二次复跑） | 746 passed, 13 warnings in 159.88s | 0 |
| `pytest backend/tests/test_risk_limits_scale.py -q` | 22 passed in 3.07s | 0 |
| `pytest test_end_settlement.py test_limit_down_close_exit.py test_continuous_account.py -q` | 39 passed in 4.51s | 0 |
| `pytest backend/tests/backtest -q`（第一次复跑，偶发） | 1 failed(0xC0000005), 745 passed | 1 |

（第二次复跑的原样末行：`1 failed, 745 passed, 13 warnings in 163.77s (0:02:43)`）

## S5 审计口径的独立复算（不经 verify 脚本）

直接从 parquet 读末行：六臂 `value == cash`、`positions == 0`、`exposure == 0.0000`，
与契约 C 值差 −0.01/0.00；`trades.parquet` 按 `(entry_date, symbol)` 排序后与 `five_a` 同名臂
**逐单元格相同**（208/208/208/208/208/198 行，22 列）。688143.SH 由 `pending_exit` 的伪盯市变为
`exit_reason="end"` / `open_at_end=False` / `exit_value=21,929.45` / `exit_date=2026-10-30`。

## S6 范围声明

本次改动集只动三处：`backend/app/backtest/engine.py`（+28/−24 行）、新增
`backend/tests/backtest/test_end_settlement.py`、修订 `backend/tests/backtest/test_limit_down_close_exit.py`
中的一个用例。`dsl.py`(36,785 B, 11-07 22:11)、`store.py`(21,104 B, 11-07 23:08)、信号链、其它策略文件、
生产库（`D:\TSP` 最近写入 15:53，早于本轮 21:25 窗口）均未触碰；未提交、未部署、未重启。
