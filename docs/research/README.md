# 研究材料索引

本目录只保留研究结论和可复现入口。原始数据、脚本、CSV 和大型 HTML 属于研究产物，统一放在仓库根目录的 [`research/`](../../research/README.md)，不进入 `docs/`。

## 结论报告

| 目录 | 主题 |
| --- | --- |
| [strategy-reliability-20261106/](strategy-reliability-20261106/RESULTS.md) | WFO 交易日/账户口径修复、T74 331% 来源核查与动量/突破/择时负结果 |
| [khunter-feasibility-20261105/](khunter-feasibility-20261105/RESULTS.md) | KHunter 策略源码、接入可行性与指标方向隔离验证 |
| [first-board-entry-study-20261026/](first-board-entry-study-20261026/REPORT.md) | 首板事件链入场研究 |
| [first-board-entry-exit-study-20261026/](first-board-entry-exit-study-20261026/REPORT.md) | 入场 × 退出二维研究 |
| [first-board-rationing-study-20261026/](first-board-rationing-study-20261026/REPORT.md) | 首板候选配给研究 |
| [firstboard-confirmatory-20261030/](firstboard-confirmatory-20261030/RESULTS.md) | 首板布林带宽规则确认性研究（进行中） |
| [firstboard-negative-20261030/](firstboard-negative-20261030/RESULTS.md) | 首板早损否决研究（进行中） |
| [auction-tail-strength-20261031/](auction-tail-strength-20261031/RESULTS.md) | 竞价尾端强势与多因子准入研究 |
| [auction-multifactor-20261101/](auction-multifactor-20261101/RESULTS.md) | 竞价多因子排序与组合门槛研究 |
| [auction-portfolio-construction-20261101/](auction-portfolio-construction-20261101/RESULTS.md) | 竞价信号组合构建与逐日盯市研究 |
| [auction-tail-stability-20261101/](auction-tail-stability-20261101/RESULTS.md) | 竞价分数尾部稳定性研究 |
| [auction-tail-loss-attribution-20261101/](auction-tail-loss-attribution-20261101/RESULTS.md) | 竞价 70%～90% 分数带损失归因 |
| [auction-holding-risk-20261101/](auction-holding-risk-20261101/RESULTS.md) | 竞价信号 D+5 持有期与风险预算研究 |
| [auction-d5-loss-attribution-20261101/](auction-d5-loss-attribution-20261101/RESULTS.md) | 竞价 D+5 主模型损失归因 |
| [auction-walkforward-20261101/](auction-walkforward-20261101/RESULTS.md) | 竞价多因子严格扩展窗口验证（准样本外） |
| [auction-d-day-veto-20261101/](auction-d-day-veto-20261101/RESULTS.md) | 竞价 D 日负面否决与最终名单压缩 |
| [auction-market-gate-20261101/](auction-market-gate-20261101/RESULTS.md) | 竞价信号 D-1 市场风险闸门 |
| [auction-path-stop-20261101/](auction-path-stop-20261101/RESULTS.md) | 竞价信号收盘确认与次日开盘止损 |
| [auction-downside-model-20261101/](auction-downside-model-20261101/RESULTS.md) | 竞价 D 日独立下行收益模型 |
| [auction-expected-return-model-20261101/](auction-expected-return-model-20261101/RESULTS.md) | 竞价 D+5 条件收益幅度模型 |
| [auction-return-market-combo-20261101/](auction-return-market-combo-20261101/RESULTS.md) | 竞价收益名单与 D-1 市场闸门组合 |
| [auction-risk-budget-exposure-20261101/](auction-risk-budget-exposure-20261101/RESULTS.md) | 竞价 D+5 风险预算与市场暴露缩放 |
| [auction-market-return-model-20261101/](auction-market-return-model-20261101/RESULTS.md) | 竞价 D+5 市场绝对收益模型 |
| [auction-lockbox-20261101/](auction-lockbox-20261101/PROTOCOL.md) | 竞价 D+5 前瞻锁箱协议（等待数据） |
| [first-board-right-tail-20261102/](first-board-right-tail-20261102/RESULTS.md) | 首板右尾 v2/v3 动态入场、早盘与市场特征、事件级两阶段及退出变体 pilot（No-Go） |
| [first-board-t74-right-tail-20261106/](first-board-t74-right-tail-20261106/RESULTS.md) | T74 331% 基线 20 日右尾路径与止损先后诊断 |
| [factor-audit-20261107/](factor-audit-20261107/FACTOR_GAP_SPEC_20261107.md) | 因子缺口规格 v1：因子清单与策略-因子映射、横截面分位统计 |
| [parallel-data-20261106/](parallel-data-20261106/DATA_QUALITY.md) | 历史行情与证券数据质量审计（独立交付，全程只读） |
| [parallel-review-20261106/](parallel-review-20261106/REVIEW.md) | 独立复盘快照与模拟成交对账 |

## 顶层文件

| 文件 | 说明 |
| --- | --- |
| [S01B_RULING_20261109.md](S01B_RULING_20261109.md) | S01b 裁定书：五条待裁定项一次结清 |
| [DELIVERY_PROTOCOL_20261109.md](DELIVERY_PROTOCOL_20261109.md) | 交付流程（2026-11-09 修订，含只用系统回测修订） |
| [caliber-decisions-20261107.md](caliber-decisions-20261107.md) | 口径决定记录：此前高/低点与 RSI（v1.1，含 E2 掩码截面排名） |
| [AUDIT_R2_20261107.md](AUDIT_R2_20261107.md) | 独立审核第二轮：B2 新证据复审、Provider 静默吞异常定级、v0.10 复审、gate.py 定性 |
| [AUDIT_R3_20261107.md](AUDIT_R3_20261107.md) | 独立审核第三轮：B4 调仓日轴抽验、三笔提交边界、验收判据、撞名 400 风险 |
| [AUDIT_R4_20261107.md](AUDIT_R4_20261107.md) | 独立审核第四轮：v0.12 签发意见、全量 49 红归因、B4 判据正文 |
| [CLEANUP_20261109.md](CLEANUP_20261109.md) | 整理记录（一次性）：S01b 过程产物清理 |

## 已迁出的研究档案

[`research/archive/2026-10-27-firstboard-classification/`](../../research/archive/2026-10-27-firstboard-classification/README.md) 包含首板分类研究的过程文件、复现脚本和冻结产物。该目录按历史快照整体迁移，文件内容未改写；其中的冻结清单仍记录迁移前的 `docs/research/...` 路径，作为当时快照的一部分。

研究结论必须注明数据版本、样本范围和局限；不要把历史研究结果表述为当前策略或未来收益保证。
