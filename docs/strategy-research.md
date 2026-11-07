# 策略研究：右尾路径与受控实验

`/strategy-research` 扩展把 T74 的右尾研究与临时脚本分开，保存可复核的基线、事件路径报告、实验对照和因子假设。它不修改策略、不重算历史收益，也不把事后右尾标签当成可交易信号。

## 基线来源

- 已保存的策略回测结果：`GET /api/backtest/strategy/results/{saved_id}` 的同一快照。
- research inbox 中的 JSON：`data/user_data/research/strategy_research/inbox/`。
- 基线记录策略/执行参数、初始资金、数据 generation、旧口径兼容参数数量（事件 allowlist、preClose 缺口、公司行为缺口）及最终统计。

当前基线若只保存实际成交交易，报告会明确标记“全部候选/排除样本不可用”。未买入候选必须另建样本池，不能与成交事件混算。

## 路径口径

- 固定从实际成交入场日开始，按本地可用交易日计窗口；默认 20 日，可配置。
- 未来空间使用复权 `high` 相对“实际成交价换算到复权口径”的收益。原始价成交需要在该入场日按 `adjusted_close / raw_close` 换算，不能直接跨公司行为比较 raw 高低价。
- 右尾标签与真实退出分离：`hit` 只表示窗口内曾达到阈值；`pnl_pct`、`exit_reason` 表示该政策实际兑现的结果。
- 输出到达目标前的最大不利波动、到达所需交易日、目标日同时触及止损的歧义标记，以及四类结果：无右尾止损、止损后才出现、先出现后止损、正常退出。
- 末端不足、停牌/缺行、入场日缺失和无法换算的入场价分别标记，不当作“没有右尾”。

路径报告不是组合收益。事件层统计不包含资金复用、最多 5 仓、每日计划上限、T+1 和费用；这些必须由核心回测结果验证。

## 实验与因子记录

- 两份路径报告的窗口与阈值一致时才能建立实验对照。
- 对照输出右尾保留、丢失、新增，止损数与实际兑现数的变化，并列出丢失/新增右尾事件。
- 因子记录固定用途（入场过滤、同日排序、持有/退出、仓位）、最早可知时点、方向和缺失政策；状态分为待验证、验证中、已采纳、已否决、无结论。
- 每轮实验应只改一个主要决策环节；失败实验保留，不因结果差自动更换分档或阈值。

## API

```text
GET    /api/custom/strategy-research/inbox
GET    /api/custom/strategy-research/reports
POST   /api/custom/strategy-research/reports
GET    /api/custom/strategy-research/reports/{report_id}
GET    /api/custom/strategy-research/reports/{report_id}/events
GET    /api/custom/strategy-research/experiments
POST   /api/custom/strategy-research/experiments
GET    /api/custom/strategy-research/experiments/{experiment_id}
GET    /api/custom/strategy-research/factors
POST   /api/custom/strategy-research/factors
GET    /api/custom/strategy-research/factors/{factor_id}
PUT    /api/custom/strategy-research/factors/{factor_id}
```

报告、实验和因子记录保存在 `data/user_data/research/strategy_research/`，写入采用临时文件 + 原子替换；损坏记录不会阻塞列表。

## 本地命令

```powershell
$env:PYTHONPATH='C:\work\sourcecode\tick-stock-panel\backend'
backend\.venv\Scripts\python.exe scripts\strategy_research.py import-baseline `
  .artifacts\331-parity-20261102\event_positions_rerun32.json `
  --name t74_331_parity_20261102.json
backend\.venv\Scripts\python.exe scripts\strategy_research.py report `
  --file t74_331_parity_20261102.json --horizon 20 --thresholds 0.2,0.3,0.5
```

受控退出变体通过核心回测服务运行，不会在扩展内另写撮合器：

```powershell
backend\.venv\Scripts\python.exe scripts\strategy_research.py run-variant `
  --file t74_331_parity_20261102.json --name t74_stop4_hold10.json `
  --stop-loss -0.04 --holding-days 10 --report
```

`run-variant` 会复用基线的参数、事件 allowlist、legacy 缺口和执行成本，只覆盖显式指定的止损、止盈、峰值回撤或持有期。完整运行可能持续数十秒到数分钟。

## 已观察基线

2026-11-06 已用 331 对拍最终结果生成 20 日路径报告；数值、数据 identity 和局限见 [T74 331% 基线右尾路径诊断](../research/first-board-t74-right-tail-20261106/RESULTS.md)。该结果只描述历史基线的路径结构，不构成未来收益承诺。
