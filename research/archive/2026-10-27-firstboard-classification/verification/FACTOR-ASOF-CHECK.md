# 因子快照时点·整表复算

生成时间：2026-10-28T17:19:48

- 事件：27，每事件两套快照（D−1 背景 / D 收盘）
- 比对字段：1404
- 数值不一致：0
- asof 日期不符：0

字段：`return_5/20/60/120/250`、`coverage_*`、`position_*`、`ma_bias_*`、`daily_return_std_*`、`volume_ratio_vs_prior5`。

未比对：`amount`（冻结行情文件无该列，无法仅凭冻结输入复现）。
