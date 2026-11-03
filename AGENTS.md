# AI 开发入口

修改、调试或审查本仓库前，必须完整阅读并遵循根目录的 [`CONTRIBUTING.md`](CONTRIBUTING.md)。其中定义了项目架构、数据契约、数据源插件化、缓存与性能要求、测试矩阵以及 PR 复审和合并标准。

涉及代码二次开发、前端插槽、后端可替换策略、扩展注册或上游升级兼容时，还必须阅读 [`docs/secondary-development.md`](docs/secondary-development.md)。该文档区分当前已实现能力与目标扩展契约；不得根据设计示例虚构尚不存在的 API。

同时遵守以下规则：

- 先理解调用链和现有测试，再进行修改。
- 保持实现简单、改动范围最小，不处理无关问题。
- 新增或整理文档前先阅读 [`docs/README.md`](docs/README.md)：默认更新现有权威文档，不把任务计划、进度和总结写入 `docs/`。
- 不覆盖工作区已有修改，不虚构测试或审查结果。
- 以实际验证结果作为完成标准。

## GitHub Issue 操作约束

- 本仓库的 GitHub Issue 创建、修改和评论只允许针对 `MengHLS/tick-stock-panel`。
- 禁止对 `shy3130/tick-stock-panel` 或任何 upstream remote 执行 Issue 写操作。
- 创建 Issue 必须使用 `scripts/github_issue_guard.py`；该脚本固定目标仓库，并在写入前后校验目标与返回归属。
- 任何目标仓库、remote 或返回 URL 校验失败都必须 fail-closed，不得改用网页或其他命令绕过。
