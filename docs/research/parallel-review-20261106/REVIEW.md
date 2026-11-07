# 独立复盘快照与模拟成交对账

日期：2026-11-06。性质：研究交付，非线上接口契约。维护者：复盘工程师；模拟盘订单/台账字段变化时重跑定向测试。

## 结论与范围

已经新增并验证离线输入冻结、完整性校验、订单与模拟成交台账对账组件，以及调用该组件的独立命令行入口。没有修改生产 API、模拟账户、策略、回测、WFO、行情或信号生成模块。没有把模拟成交称为真实成交。

本次交付解决“导出内容变化后无法固定重算、委托状态和模拟成交记录缺少独立核验”的研究复盘缺口；未解决历史计划缺失。`ledger_consistent=true` 仅表示导出范围内数量和关联关系无已发现异常，`plan_reconciled` 始终为 false，不能把它解释为计划完整或资金账全部一致。

## 代码证据

- `backend/app/custom/paper_execution/service.py:335` 附近 `_event` 仅保存 at/symbol/side/reason/message/order_id，事件被裁剪至最近 100 条（349 行）；未保存请求数量和参考价格。
- 同文件 `_submit`（351—390 行）收到 `create_order` 的 error 时写无 order_id 的事件；预算不足一手（503—505 行）也写无 order_id 的事件。因此不能将所有无订单事件算作拒单，不能从这些历史事件恢复计划数量。
- `backend/app/custom/paper_execution/snapshot.py` 的 `make_snapshot` 冻结策略参数、资源指纹及配置，并非当次事件、订单、模拟成交和行情输入快照。本工具保留既有 revision/snapshot 原字段，没有另造策略配置解析器。
- `backend/app/strategy/paper.py:447` 订单状态为 pending/filled/cancelled/expired；704—723 行模拟成交含 order_id/symbol/asset_type/side/qty/price/fee/kind，先记台账再保存订单状态。新工具能发现导出时订单与台账不一致，但不能仅凭导出判定是并发读取还是持久化故障。
- `backend/app/api/market_recap.py` 当前负责市场分析、报告归档及相关市场信息；本次未扩展其接口。

以上是源码证据，不是针对用户真实账户的完整性结论。本轮未读取用户运行账户数据。

## 新增文件与行为

位于 `research/parallel-review-20261106/`：

- `review_reconciliation.py`：`capture` 深复制调用方导出的 JSON，拒绝非有限数，生成规范 JSON 的 SHA-256；`reconcile` 校验版本和指纹后重算。CLI 只读指定输入并向 stdout 输出 UTF-8 JSON，不自动写入数据目录。
- `test_review_reconciliation.py`：29 个定向用例，含真实子进程中文快照回归。
- `synthetic_input.json`：完全合成的单账户格式输入，不含用户账户数据。
- `synthetic_snapshot.json`：合成输入冻结产物。
- `verification.json`：实际命令、退出码、结果及组件指纹。

本报告为第六个新增文件。原有其他文件没有编辑；未清理他人已有改动。交付属于独立研究工具，尚未进入 L2 扩展注册或 L3 核心接线。

按 order_id 对账，不按证券代码猜测归属；保留委托状态和原因，分别报告累计模拟成交、filled 状态应有数量及差异。未知订单成交、重复成交行、证券/方向/资产类型不一致、事件关联缺失、超量或缺少模拟成交都明确报告。完全相同的重复成交行只累计一次，同时记异常。非 fill 台账事件不计作模拟成交。无订单历史事件输出 `unsubmitted_unknown`，计划数量为 null。

快照指纹覆盖调用方提供的全部原始字段，不包含自动生成时间。对象键顺序不影响指纹；列表顺序保留。哈希用于检查内容变化，不提供来源签名。版本 1 不做静默迁移。

## 实际验证

从项目根目录执行，使用项目现有 Python 环境，无安装依赖。选择直接调用现有解释器，避免包管理器在本轮受限目录写缓存。

| 命令（解释器为 `backend/.venv/Scripts/python.exe`） | 退出码 | 结果 |
| --- | --- | --- |
| `-B -m pytest --capture=sys -p no:cacheprovider --noconftest research/parallel-review-20261106/test_review_reconciliation.py -q` | 0 | 29 passed，0.42 秒；anyio 及 pytest_asyncio 有既有弃用提醒 |
| `-B -m ruff check --no-cache research/parallel-review-20261106` | 0 | All checks passed |
| `-B research/parallel-review-20261106/review_reconciliation.py capture research/parallel-review-20261106/synthetic_input.json` | 0 | UTF-8 中文不变，内容指纹如下 |
| `-B research/parallel-review-20261106/review_reconciliation.py replay research/parallel-review-20261106/synthetic_snapshot.json` | 0 | 100 股模拟成交，差异 0；无订单事件仍为未知，plan_reconciled=false |
| `git diff --check` | 2 | 既有 `backend/tests/test_industry_chain_extension.py:808` EOF 空行，未修改 |

输入内容 SHA-256：`087a9d8ebfd5d7fd034996abe82eb02e954aa37863b61a9aecfb247b9a46f96b`。

首次默认 pytest 捕获因临时目录不可写失败（退出 1）；首次 Ruff 因 `.ruff_cache` 不可写失败（退出 2）。随后关闭磁盘缓存、改用内存捕获成功，不把首次失败隐去。最初端到端检查还发现 Windows 默认重定向编码会改变中文；现已固定 CLI stdout/stderr 为 UTF-8，并加真实子进程回归用例。

CLI 正常退出 0，有对账异常退出 1，无法读取、无效 JSON、版本不支持或校验失败退出 2。权限失败与文件缺失用例通过模拟读异常覆盖；真实失败来自测试临时目录和检查缓存写入，不是对生产文件进行写权限探测。

覆盖：内容固定和隔离、参数改变指纹、快照篡改、未知版本、同证券不同订单、待成交/撤销/过期、台账缺失/超量/重复/孤立记录、关联字段不匹配、未知计划数量、非法数量、NaN、非成交台账事件、输入错误及 CLI 输出。未跑后端全套或前端构建，因为未改生产代码或前端。

## 接入与限制

已接入：研究 CLI 调用 capture/reconcile；合成文件经过真实命令行冻结与复算。

待接入：复盘专属导出调用方在服务锁和 PAPER_LOCK 允许的既有顺序内取得同一账户的一致性 binding/orders/fills，然后将导出内容传给本组件。当前组件不访问账户仓库、不重做行情采集、不注册 API，也不保证外部导出原子性。此项需要后续接线评审和服务/API测试，不能宣称线上已生效。

若要核对完整计划与拒单，还需未来执行记录明确保存稳定决策 ID、当次请求数量、参考价、输入日期/版本、明确 outcome 及可追溯拒单原因，并保留完整历史。现有历史缺失不能靠重跑当前策略补齐。本轮按并行边界未修改该执行写入链。

该工具只核对关联和股数，不验证价格/手续费/现金/持仓正确性，不计算回测收益，也不证明数据新鲜度、复权或信号可靠性。模拟盘当前为整单成交口径；若将来增加部分成交，必须升级状态契约和测试。不同账户合并前需调用方隔离，本版本不推断账户归属。

没有新增缓存、SSE 或前端查询，因此无缓存失效接线。未提交、部署、重启、购买或交易。回退仅需移除本次两个独立研究目录，无需迁移数据。

## 已读取范围与来源版本

读取项目规范 `AGENTS.md`、`CONTRIBUTING.md`、`docs/README.md`、`docs/secondary-development.md`；目标调用链包括上述三个模拟执行模块、`backend/app/api/market_recap.py` 和相关 `backend/tests/test_paper_execution_extension.py`；研究依据为 `docs/research/strategy-reliability-20261106/RESULTS.md`。较早一轮读过的完整过程见交接记录，本轮重新核查目标源码与 git 状态。

取证时源码 SHA-256：

- `backend/app/custom/paper_execution/service.py`：`53b413d79fcd73863d494ae7b466a7a4548b7ad1f118b770685dd13291ceb8c4`
- `backend/app/custom/paper_execution/snapshot.py`：`32d03d4f0c2a3ce254254755e6062f13290ef900bd91608804983c5707b2a472`
- `backend/app/strategy/paper.py`：`e76771fb8aeb0db1b2556592906faa8d2bd6a8f3dcc90a5219f4e7b8508a661d`
- 原研究 `RESULTS.md`：`1439a2465a8c5b5d5e88fd8dee5d2d45bc039ff91b53a8f5ac02030e7a929207`

本报告没有修改原研究结论；量化研究员负责的连续 WFO 和信号守卫核验仍以其独立证据为准。

最终核验时分支 `dev`，HEAD 为 `848bd04b7266f6645fabdfdc4b2c0cdf404eb643`，工作区另有他人未提交修改。六个新增文件均存在；逐文件 `git diff --check --no-index -- NUL <文件>` 无空白诊断输出，退出 1 表示新增内容存在差异。保存的合成快照与 capture 实际 stdout 经 JSON 解析后完全一致。目标模拟执行、模拟账务及大盘复盘 API 在最终限定范围 git status 中没有修改项；仅出现本次两个新增目录。
