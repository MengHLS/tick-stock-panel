# 文档入口与维护规则

本目录只放**长期需要维护的知识**。任务计划、进度记录、测试输出和一次性研究过程不默认进入 `docs/`。

## 新增文档前先判断

1. 这个问题是否已有权威文档？有则更新原文，不新建平行说明。
2. 这份内容三个月后还会有人查阅或修改吗？不会则写进提交说明或 PR，不写入仓库。
3. 它描述的是“现在是什么”，还是“当时准备怎么做”？后者属于计划，不是契约。
4. 作者和更新时机是否明确？没有维护者的文档不应新增。

## 文档状态

| 状态 | 含义 |
| --- | --- |
| **现行** | 描述当前行为，代码变化时必须同步更新 |
| **设计提案** | 方案或取舍记录，不保证已实现；不得当作 API 契约 |
| **历史计划** | 已完成或已放弃的实施计划，只保留决策价值；任务结束后应合并或删除 |
| **研究材料** | 数据、脚本、实验报告；不是产品文档，需注明数据版本与局限 |

发生冲突时，**以代码、测试和《功能手册》为准**，不以计划文档为准。

## 现行文档

| 文档 | 用途 |
| --- | --- |
| [features.md](features.md) | 功能手册，面向使用者；含截面联动因子口径、产业链分类依据及图谱兼容规则 |
| [configuration.md](configuration.md) | `.env` 配置项与优先级 |
| [deployment.md](deployment.md) | Docker / 本机 / 桌面部署 |
| [deploy-password.md](deploy-password.md) | 公网访问密码 |
| [strategy.md](strategy.md) | 策略编写与参数 |
| [strategy-iteration.md](strategy-iteration.md) | AI 策略迭代流程 |
| [backtest-evidence.md](backtest-evidence.md) | 正式回测的未来数据检查、版本指纹与证据接口 |
| [mining.md](mining.md) | 因子与策略挖掘 |
| [market-phase.md](market-phase.md) | 市场阶段与主线识别 |
| [custom-data-source.md](custom-data-source.md) | 自定义数据源契约 |
| [plugin-development.md](plugin-development.md) | 数据源插件开发 |
| [external-data-source-packages.md](external-data-source-packages.md) | 外部数据源 Provider 安装、更新与能力切换 |
| [extension-packages.md](extension-packages.md) | 统一导入与后端/前后端扩展包契约 |
| [page-sdk.md](page-sdk.md) | 页面插件 SDK |
| [secondary-development.md](secondary-development.md) | 二次开发边界与扩展点 |
| [historical-st-filter.md](historical-st-filter.md) | 本地历史 ST 过滤修复说明 |
| [examples/custom-data-source/](examples/custom-data-source/) | 自定义数据源联调示例 |

`CONTRIBUTING.md` 与 `AGENTS.md` 在仓库根目录，是贡献、审查和 AI 开发的最高优先级入口。

## 设计与计划文档

这些文档记录方案和取舍，**不保证与当前实现一致**。实现变化时优先更新现行文档，不要求逐份回填计划。

| 文档 | 状态 |
| --- | --- |
| [factor-system-design.md](factor-system-design.md) | 设计提案 |
| [factor-platform-plan.md](factor-platform-plan.md) | 设计/实施计划 |
| [open-platform-plan.md](open-platform-plan.md) | 设计/实施计划 |
| [paper-trading-plan.md](paper-trading-plan.md) | 设计/实施计划 |
| [robust-optimizer-plan.md](robust-optimizer-plan.md) | 设计/实施计划 |
| [auto-strategy-lab-plan.md](auto-strategy-lab-plan.md) | 设计/实施计划 |
| [ext-architecture-plan.md](ext-architecture-plan.md) | 架构路线 |
| [backend-data-performance-plan.md](backend-data-performance-plan.md) | 性能专项计划 |
| [tickflow-pro-phase1-probe.md](tickflow-pro-phase1-probe.md) | 专项探针记录 |
| [tickflow-pro-shared-rate-limit.md](tickflow-pro-shared-rate-limit.md) | 限频专项说明 |
| [superpowers/specs/2026-10-29-firstboard-factor-discovery-design.md](superpowers/specs/2026-10-29-firstboard-factor-discovery-design.md) | 设计提案（是否已实施未逐项核实） |
| [superpowers/specs/2026-11-01-cross-sectional-linkage-factors-design.md](superpowers/specs/2026-11-01-cross-sectional-linkage-factors-design.md) | 历史计划（已实现，现行口径见 [features.md](features.md)） |

## 本地研究与过程文档

| 位置 | 性质 | 处理方式 |
| --- | --- | --- |
| [docs/research/](research/README.md) 结论报告 | 历史研究结论 | 保留结论与数据版本说明；不再追加过程记录 |
| [`../research/archive/2026-10-27-firstboard-classification/`](../research/archive/2026-10-27-firstboard-classification/README.md) | 研究工作区，含脚本、CSV、大 HTML | 已按历史快照迁出 `docs/` 并封存；不是维护型文档 |
| [research/firstboard-confirmatory-20261030/](research/firstboard-confirmatory-20261030/RESULTS.md)、[research/firstboard-negative-20261030/](research/firstboard-negative-20261030/RESULTS.md) | 进行中研究 | 研究结束后只保留 `RESULTS.md` 与必要数据清单 |
| [superpowers/specs/](superpowers/specs/) | 设计提案与历史计划 | 只保留可定位到具体文件的条目；完成或失效后合并或删除 |

2026-10-29 的实施阶段计划文件已删除，设计稿仍保留于上表；历史版本由 Git 保留。

`superpowers/` 下未找到 2026-10-30 的计划或规格文件；相关首板确认协议来源待核实，不推断为已完成或已废弃。

## 命名与位置

- 本地长期文档统一放 `docs/local/<topic>.md`，不要复制整份上游文档另起一套。
- 研究结论放 `docs/research/<topic>-<YYYYMMDD>/RESULTS.md` 并在 [research/README.md](research/README.md) 登记；脚本、CSV、图表和大 HTML 放仓库根目录 `research/`，不要放进 `docs/`。
- 不按“设计 / 计划 / 实现 / 总结”给同一个需求连续新增四份文件。
- 上游已有的文档尽量沿用原位置；不要为了整齐搬动上游目录，避免升级时产生无意义的合并冲突。

## 任务结束时的清理

- 计划中的有效约束合并进现行文档。
- 已完成的计划、临时分析、验证流水账删除；历史版本由 Git 保留。
- 未提交的研究材料先确认归属，不直接清理。
- 新增或修改现行文档后，更新本索引。
