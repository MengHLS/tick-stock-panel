# 审核阻断项修复交付 (R1/R2/R3)

- 分支: `dev` @ `848bd04b` (未提交, 保留他人并行修改)
- 修复人: 系统开发工程师
- 对应审核报告: `research/independent-review-20261106/REVIEW.md`
- 复核方: 独立审核工程师

## 结论速览

| 编号 | 审核缺陷 | 当前状态 | 判定依据 |
|---|---|---|---|
| R1 | API 路由缺 `continuous_account` 参数, 请求 500/NameError | 已修复 | 真实路由 TestClient 请求 200 + `job` 事件, 参数被注入 worker 配置; `ruff` 无 F821 |
| R2 | 折边界结转 `entry_time_id=-1`, 持有延期用局部索引计日 | 已修复 | 审核复现脚本 full/split 均 `2025-01-08 time_exit`, 逐笔+费用+期末权益对齐 |
| R3 | 允许 `step > test`, 缺口日期持仓不回放 | 已改为拒绝并停止 | `step != test` + 连续账户 -> `ValueError`/400; 训练缺口处停止回放并写 `stopped_early` |

## R1 — API 参数与路由合同

改动 `backend/app/api/backtest.py`:

- `walkforward_stream` 新增 `min_trades_oos: int = 10` 与 `continuous_account: bool = True` 参数 (1372), 并真正传入 `WalkForwardConfig` (1517)。
- `_make_wf_job_key` 纳入 `min_trades_oos` 与 `continuous_account` (1349-1354): 两种口径不再共用同一个 job key (避免命中对方缓存结果)。
- 路由前置校验: `mode != "position"` 返回 400 (full 独立候选曲线不是账户净值); `min_trades_oos < 0` 返回 400; `continuous_account and step_days != test_days` 返回 400 (1415)。
- 删除 `optimize_robust_stream` 上误加的同名参数: 稳健优化器不支持跨折结转, 声明它会形成"传了不生效"的假接口。

测试: `tests/backtest/test_walkforward.py::test_walkforward_stream_injects_continuous_account_and_emits_done`
真实 FastAPI 路由 + TestClient 跑三种取值 (`缺省/true/false`), 断言能建立 SSE 流 (`job`/`done`), 且 worker 配置里的 `continuous_account` 与请求一致; 另有 `test_walkforward_stream_rejects_sparse_windows_for_continuous_account` 覆盖 400 分支。

## R2 — 结转持仓的持有年龄与延展判定

改动 `backend/app/backtest/engine.py`:

- 结转持仓不再用 `time_id - entry_time_id` 计日: 成交日写入 `hold_session_age=1` (3430, 3753), 每个交易日 `+1` (3848), 随 `PortfolioCarryState` 结转 (2687-2689 对旧快照按 `hold_days+1` 兜底)。
- 持有延期判定改用 `holding_day = pos["hold_session_age"]` (4175), 与折切分点无关。
- 延展判定需要的历史窗口随持仓结转: `hold_high_history` / `hold_close_history` 在结转时深拷贝 (2695-2699), 决策日落在折后首日时不会因为"本段没有历史"而退化成另一分支。
- 段末原始买点/卖点跨段保留为次日开盘挂单, 不因切分吞掉一天。

测试 (`tests/backtest/test_continuous_account.py`, 真实引擎 + 真实费用):

- `test_split_segments_equal_one_continuous_run`: 拆段合并后逐笔、现金、期末权益等于一次完整回放。
- `test_hold_extension_matches_full_run_with_fees_and_cash[4/5]`: 含佣金/印花税/滑点, 逐分对齐。
- `test_hold_extension_exit_matches_full_run_across_splits[3/4/5/6]`: 决策日落在任意一段都同日退出 (split=4 正是"决策日=折后首日"的边界)。
- `test_runner_extension_deadline_matches_full_run_across_splits[3/5/6]`: 延展到期日跨折不清零。
- `test_stop_loss_fires_on_same_session_after_carry[3/4/5]`: 结转持仓的风控线在同一交易日触发。

## R3 — 时间线连续性

改动 `backend/app/backtest/walkforward.py`:

- 连续账户要求 `step_days == test_days`, 否则直接拒绝 (705-712, 同时 API 1415 提前 400): 跳窗留下的交易日里, 持仓的止损/持有期/现金变化无法补算, 拼出来的"连续账户"不是账户净值。稀疏窗口只能在 `continuous_account=False` 下用于逐折复利诊断 (`return_kind=compounded_fold_returns_not_continuous_account`)。
- 即使窗口参数合法, 回放前仍按交易日历核对各折测试窗首尾是否相接; 中间折训练失败/无数据导致断档时, 回放到断档前即停止, 记 `stopped_early` 与 `missing_dates` (402-430, 533-545), 不跳过去接着拼。
- 头部缺口: 前几折未产出参数/行情时, 显式说明账户不是从区间起点开始。
- 自洽性检查补两条, 让"计数都对但时间线漏日子"不再全绿 (607-642):
  - `timeline_covers_trading_days`: 回放区间内每个交易日都必须出现在权益曲线上;
  - `timeline_complete`: 无缺口且未提前停止 —— 只有它为 True 时, 其余代数自洽项才能当作连续账户证据。

测试 (`tests/backtest/test_walkforward.py`):

- `test_continuous_account_rejects_sparse_windows_before_running`: 拒绝且不启动任何折。
- `test_sparse_windows_still_allowed_when_continuous_account_disabled`: 关闭后不被误杀。
- `test_continuous_account_stops_at_training_gap_instead_of_skipping_days`: 断档处停, `missing_dates` 精确列出未回放交易日。
- `test_continuous_account_reports_timeline_stopped_before_planned_end` / `..._reports_head_gap_when_early_folds_fail`: 提前收尾与头部缺口都进报告。
- `test_final_open_positions_come_from_last_fold_not_missing_carry_state`: 末折 `carry_out=False` 不产出 carry 状态时, 期末持仓取权益曲线末点, 不再报 0 持仓。

## 前端

`frontend/src/lib/walkforwardTask.ts` / `frontend/src/pages/backtest/StrategyWalkForward.tsx`:

- 类型补 `continuous_account`、`return_kind`、`window_basis`、`min_trades_oos` 等新字段; 折预览显示交易日数。
- 移除"全量独立"模式选择 (后端已拒绝), 增加 OOS 最少交易数输入。
- 汇总区分"连续账户收益"(单账户单时间线) 与"逐折收益拼接 (诊断, 非账户净值)", 并显示 `stopped_early`。
- `step != test` 时前端直接拦住并说明原因, 不发注定被拒的请求。

## 本次实跑结果

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端回归 | `pytest tests/backtest -q` | 732 passed |
| 定向 | `pytest tests/backtest/test_walkforward.py tests/backtest/test_continuous_account.py tests/test_backtest_stream_date_guard.py -q` | 93 passed, 6 skipped |
| 其他相关 | `pytest tests/test_auction_walkforward_study.py tests/test_backtest_stream_date_guard.py -q` | 27 passed, 6 skipped |
| Lint | `ruff check app/api/backtest.py app/backtest/{engine,strategy,walkforward}.py` | 无 F821/F811/E9; 余下为文件既有风格项 (BLE001/E402/RUF023 等), 与 `HEAD` 同源 |
| 前端类型 | `tsc -b` | exit 0 |
| 审核复现 | `.venv/Scripts/python.exe .tmp-review/review_repro.py` | R1 `200 event: job`; R2 full 与 split 同为 `2025-01-08 time_exit`; R3 `ValueError: step_days 必须等于 test_days` |

说明: 复现脚本以裸脚本方式启动 worker 进程会触发 multiprocessing spawn 失败 (`bootstrapping phase`), 那是脚本运行方式的限制, 不是路由缺陷; R1 的正式证据是上表的 pytest 路由用例。

## 未接入 / 限制

- 未提交、未合并、未部署; 分支仍是 `dev` 工作区, 共存的 industry_chain / quote_service / strategy_research 等改动均未触碰。
- 连续账户口径只在 `mode=position` 下成立; `full` 模式仍可单独跑, 但不参与滚动账户汇总。
- 前端本地未安装 `eslint` 可执行文件 (`node_modules/.bin/eslint` 不存在), 因此未跑 ESLint; 仅做了 `tsc -b` 类型检查。
- 缺口目前是"停止 + 报告", 尚未实现"沿用上一折参数逐日补回放"的备选口径。
- 文档 (`docs/backtest-evidence.md` 等) 未由我改动, 如需把新口径写进产品文档请指派文档管理员。

## 复验建议

1. 直接跑 `.tmp-review/review_repro.py`, 确认 R2 两条日期相同、R3 抛 `ValueError`。
2. 跑 `pytest tests/backtest/test_continuous_account.py -q` 看分段等价与止损同日用例。
3. 用 `train_days=1, test_days=3, step_days=3` 构造真实 WFO, 检查 `summary.continuous_account.invariants.timeline_complete` 为 True 且 `stopped_early` 为 null; 再把 `step_days` 改成 4, 应得到 400。

---

## 复验记录（系统开发工程师本轮实测）

环境：`dev` @ `848bd04b` 工作区（含全部未提交并行修改，未整理、未提交、未部署）。
解释器：`backend/.venv/Scripts/python.exe`。时间：2026-11-06 23:50 前后（北京时间）。

| 检查 | 命令 | 实测结果 |
|---|---|---|
| Lint（审核用的 F821 口径） | `ruff check --select F821,F811,E9 app/api/backtest.py app/backtest/{engine,walkforward,strategy}.py` | `All checks passed!`，退出码 0（R1 的两处 F821 已消失） |
| 后端回测全量 | `pytest tests/backtest -q` | **733 passed**，157.20s，退出码 0（上文 732 为上一轮数字，本轮多 1 项） |
| 定向（含新增用例） | `pytest tests/backtest/test_walkforward.py tests/backtest/test_continuous_account.py tests/test_backtest_stream_date_guard.py -q` | **94 passed, 6 skipped**，退出码 0 |
| 审核原样复现脚本（步进=4） | `.tmp-review/review_repro.py` | R1 `continuous parameter declared: True` / `200 event: job`；R2 `full` 与 `split` 均 `2025-01-03` 入场、**`2025-01-08` time_exit、duration 5**；R3 抛 `ValueError: 连续账户要求样本外区间逐日衔接…`（按设计拒绝，故脚本以退出码 1 结束，非缺陷） |
| R3 数值对照（本轮新增脚本） | `.tmp-review/verify_r3.py` | 见下 |
| 前端类型 | `frontend/node_modules/.bin/tsc -b` | 退出码 0 |

### R3 数值对照（同一受控样本：8 个交易日，01-06 价格 5，其余 10，stop_loss_pct=0.1）

```
FULL  最终权益 95490.55，成交 [(2025-01-06, stop_loss)]

WFO train=1 test=3 step=4  ->  REJECTED（ValueError，未启动任何折）
WFO train=1 test=3 step=3  ->  测试窗 [[01-03,01-05],[01-06,01-08]]
                              权益曲线 01-03/01-04/01-05/01-06/01-07/01-08（逐日连续）
                              最终权益 95490.55（== 完整回放）
                              成交 [(2025-01-06, stop_loss)]（缺口日前置发生，未再漏）
                              stopped_early = null，timeline_gap = null
                              invariants 八项全 true（含 timeline_covers_trading_days、
                              timeline_complete）
```

结论：审核 R3 的失真数值（99993.70 冒充连续账户）在当前代码中已不可达——步进不等于测试窗直接被拒；步进等于测试窗时，账户逐日覆盖且与完整回放同额同笔。

## 仍未覆盖 / 限制（诚实清单）

- 未提交、未合并、未部署、未重启服务；`industry_chain`、`quote_service`、`strategy_research`、各 `research/*` 并行成果未触碰。
- R3 目前是「拒绝 + 停止 + 报告」策略：仍**未实现**「步进>测试窗时沿用上一折参数逐日补回放」，也**未实现**训练失败缺口内的逐日补算；缺口语义仍需产品口径确认（沿用哪一折参数、是否允许）。
- 连续账户口径只在 `mode=position` 生效；`full` 模式可单独跑但不参与账户汇总。
- 未跑全后端 `pytest tests`（只跑了 `tests/backtest` 与两个相关文件），未跑真数据多年 WFO、性能/内存基准、前端 `pnpm build`、浏览器联调。
- 未跑 ESLint：本地 `frontend/node_modules/.bin/eslint` 不存在；只做了 `tsc -b`。
- 本报告不构成发布、合并或交易许可；R1/R2/R3 是否解除阻断由独立审核工程师复验裁定。

### 证据脚本位置

- `research/independent-review-20261106/verify-scripts/review_repro.py`：审核报告第 5 节代码原样副本（步进=4 时以 R3 `ValueError` 结束）。
- `research/independent-review-20261106/verify-scripts/verify_r3.py`：本轮新增的 R3 数值对照（步进=4 拒绝、步进=3 与完整回放逐日同额同笔）。

复跑方式：`cd backend && .venv/Scripts/python.exe ../research/independent-review-20261106/verify-scripts/verify_r3.py`
