# matrix_native 共享矩阵独立端到端复验（2026-11-07）

结论：本次固定两组、三折、全市场切片的共享矩阵与连续账户结果一致性**通过**，补齐上一轮明确未覆盖的端到端项。通用验证器的充分性**不通过**，全局研究假设计数**未闭合**。本结论不构成策略盈利性或总体研究验收通过。

审核人员：独立审核工程师。只新增本报告及 `matrix-e2e-20261107/` 下审核脚本、日志和证据；未修改被审核实现，未提交、部署、重启或真实交易。开工先读取根 AGENTS、CONTRIBUTING、docs/README、secondary-development，并检查 git 状态；现场大量并行未提交修改予以保留，未触碰 parallel-data-20261106 或 parallel-review-20261106。

## 1. 实跑、命令及退出码

以下命令均在 `C:\work\sourcecode\tick-stock-panel` 执行，解释器为 `backend/.venv/Scripts/python.exe`。所有路径相对该根目录。

| 独立执行 | 命令（解释器后参数） | 退出码及证据 |
|---|---|---|
| 原批量脚本，两组、保留原始逐笔与曲线 | `research/batch-backtest-framework-20261107/run_batch.py --groups research/batch-backtest-framework-20261107/groups.json --start 2024-12-02 --end 2026-10-31 --train-days 252 --test-days 63 --keep-raw --out research/independent-review-20261106/matrix-e2e-20261107/out` | **0**；65.69 秒；`batch-exit.json`、`batch.log` |
| 原比较器 + 独立捕获生产完整输出、证券轴及运行前后指纹 | `research/independent-review-20261106/matrix-e2e-20261107/verify_independent.py` | **0**；生产比较约64.91秒；`verify-exit.json`、`verify.log`、`out/compare_summary.json` |
| 独立完整字段、权益、逐笔、收益与哈希检查 | `research/independent-review-20261106/matrix-e2e-20261107/independent_checks.py` | **0**；`independent-checks.json`、`independent-checks.log` |
| 独立拦截真实矩阵装载和 prepare 调用，再跑相同两组 | `research/independent-review-20261106/matrix-e2e-20261107/observe_shared.py` | **0**；`shared-observation.json`、`shared.log`、`instrumented-out/registry.json` |
| 独立定位预热掩码差异 | `research/independent-review-20261106/matrix-e2e-20261107/check_axes.py` | 正常完成并生成 `mask-difference.json`、`axes.log`；未单独落进程退出码，不将其写作额外退出码证据 |

独立检查第一遍曾退出1，原因是审核脚本误把未平仓记录 `pnl_amount=0` 当作全部权益盈亏。保留 `independent-checks-first-pass.log`。修正审核公式为“初始资金 + 已实现净盈亏 + 未平仓市值减入场成本”后退出0；没有改实现。两组对账尾差分别 +0.01 元和 -0.01 元，属于逐笔金额保留两位的舍入差。没有将该失败当成生产缺陷。

## 2. 本次通过范围与证据

输入：原两组 `first_board_chain_rebreak(min_pullback_pct=5)`、`first_limit_pullback_3f_runner_t74(min_score_pct=55)`；position 模式，初始资金100万元，train=252、test=step=63，目标 sortino，min_trades_oos=10，stock，全市场。实际公共 OOS 为2025-12-15至2026-09-22；输入 end=2026-10-31，最后不足完整测试折的日期没有被冒充 OOS。各折边界与生产入口逐项一致。

真实装载拦截观测：装载函数仅调用 **1次**，矩阵 `[728,5727]`；prepare调用 **12次**，全部指向同一个 override 对象，12次 close 数组均与共享矩阵共享内存且只读。不是仅采信 `matrix_load_count=1` 硬编码字段。源码对照：`run_batch.py:349` 装载，`:705` IS优化，`:758` 附近 OOS准备；`matrix.py:2770-2807` 时间切片保留证券轴、共享底层数组并设只读。

| 项 | g1 | g2 |
|---|---:|---:|
| 独立完整权益曲线逐字段一致 | 189/189点 | 189/189点 |
| 独立完整逐笔逐字段一致（包括成本后的入场/退出金额和净盈亏） | 325/325笔 | 246/246笔 |
| 期末权益 | 434227.12元 | 992786.95元 |
| 期末持仓 | 0 | 9 |
| 已完成/未平仓交易 | 325/0 | 237/9 |
| duplicate_dates | 0 | 0 |
| timeline.complete / missing_dates | true / 0 | true / 0 |
| 账户stats、完整boundaries、final_cash、final_positions | 全等 | 全等 |
| 各折 total_return、account_total_return_cumulative（原验证器跳过） | 独立补查全等 | 独立补查全等 |
| 完整权益与逐笔SHA256 | 与批量摘要一致 | 与批量摘要一致 |

g2期末未平仓市值898041.00元，现金94745.95元，相加等于992786.95元。未把未平仓标记当作真实卖出。

成本配置来自观测的真实 StrategyBacktestConfig：`fees_pct=0.0002, commission_pct=None, stamp_tax_pct=None, slippage_bps=5.0`，其余默认撮合参数以及完整config repr已保存在 `shared-observation.json`。本次证明两条执行路径采用相同默认口径并产生完全相同的逐笔成本结果；没有额外证明该默认成本覆盖所有现实券商费用或压力情景。

## 3. 39项差异逐类解释

本次独立复跑同样得到 **result_diffs=0、telemetry_diffs=39（18+21）**。原始交付和本次报告均保留逐条值。

| 差异类别 | g1 | g2 | 解释 |
|---|---:|---:|---|
| fingerprint_ms、compute_ms | 15 | 3 | 18项为墙钟测量差 |
| shared_market_data_bytes | 3 | 3 | 时间范围/字段并集/证券轴导致内存体积不同 |
| market_matrix_bytes | 0 | 3 | g2每折多61证券列导致多318969字节 |
| market_matrix_shape[1] | 0 | 3 | g2为5727对5666，是真实轴差异，不是时延 |
| compute_cache current_bytes、computed_bytes、peak_bytes | 0 | 9 | g2缓存布尔阵列按证券列数分配，故体积不同 |
| 总数 | 18 | 21 | 合计39，其中18项时延、21项维度/内存资源差异 |

实测证券与时间轴（`axis-comparison.json`）：

- 批量并集窗口2023-10-30至2026-10-30，728日、5727证券。
- 生产g1窗口2023-10-30至2026-09-22，706日、5727证券。
- 生产g2窗口2024-08-05至2026-09-22，519日、5666证券。
- 61个批量侧独有证券逐个登记在证据；它们在生产g2日期集合内，以及正式IS/OOS（2024-12-02至2026-09-22）均 **0个可交易日**。不存在生产独有证券。并集装载起点受g1更长预热影响，时间切片不会缩证券轴，因此多出历史证券列。
- 对公共证券/公共日期，open/high/low/close/volume/tradable及公共字段逐值一致（NaN等价）；g1涨跌停掩码亦全等。g2涨停掩码55单元、跌停掩码42单元不同，日期分别限于2024-08-05/07/08/12和2024-08-05/06，均在正式训练起点之前，符合更短预热起点缺少前收历史的差异。正式IS/OOS掩码差异为0（`mask-difference.json`）。

因此**不能声称物理矩阵同证券轴、同历史窗口**；本次能确认的是相同正式评估时间与参数、相同有效可交易宇宙，以及该样本IS分数/OOS完整交易和权益一致。该结论不得自动外推到依赖截面排名、全轴分母或不同预热的其他策略。

## 4. 审核发现

### F1 — P1：通用验证器可对损坏权益/逐笔/收益给出零结果差异

精确位置：`research/batch-backtest-framework-20261107/verify_batch.py:48-62, 87-104, 192-254, 375-377`。

复现：读取本次真实生产输出的副本，将第一笔 `pnl_amount +=999`、第一权益点 `value +=999`、账户stats.total_return及第一折oos_stats.total_return设为999，再调用原 `compare_entry`。两组均从0结果差异变为**仍为0**。变异仅发生在审核进程内存，没有改证据源/生产文件；结果在 `independent-checks.json → groups[*].blindspot_mutation`。

原因：SKIP_KEYS按字段名在任意深度跳过 total_return 和 continuous_account；比较器没有计算生产完整曲线/逐笔摘要去比批量的SHA256，虽然注释声称单独逐字段比对。只比生命周期计数、末值和部分stats，无法发现内部点或逐笔损坏。

修复建议：按精确路径管理豁免；明确归一化段收益与累计收益后比较；直接核对完整权益/逐笔或规范化哈希，至少加入损坏一个权益点/交易金额/收益字段必失败的针对性校验；缺失required字段应失败。将形状/证券轴豁免改为有可交易域证明的显式报告。

本次固定样本已由审核侧额外比较原始数据消除实际一致性疑点；但**原验证器不能单独作为之后的完整一致性放行依据**。

### F2 — P2：局部运行计数不等于研究假设N，全局账未闭合

精确位置：`run_batch.py:678-710, 768-769, 937-938, 1139-1143`；`strategy-search-20261107/FREEZE.json:n_trials`；`PROTOCOL.md:107-127`；`scripts/run_suite.py:40-59, 61-70, 109-110`。

底座每组3次IS+3次OOS=6，跨两组6→12是 **12次引擎评估调用/2条固定规则参数组**，不是12个独立假设。三折不增加固定假设个数。本审核重跑及生产对照也不新增假设。REPORT原表“IS trials=6”与源码实际3 IS+3 OOS不一致，建议更名为engine evaluations并拆分计数。

研究FREEZE的15=12条S01-S12+T03三条规则（momentum、breakout_volume、breakout_volume_market），36条情景行=12×3成本轴；不是36个假设。T03的4年×3规则×2成本=24次运行，也不能再加24。同一固定规则的年度分段、成本压力、回归和审计重放应去重；若按最佳成本情景/参数选优，另计选择机会。

现有可枚举规则族至少 **17**：协议认可的15，加未在这15名称中列出的first_board_chain_rebreak及first_limit_pullback_3f_runner_t74两规则族。后者历史回放已经发生，本次审计不重复加2。**17只是项目范围的可识别下限，精确全局N未知**：T74等生产策略历史参数/规则修订、其他目录探索和情景间选择记录无共享身份台账，不能证明完全去重或穷尽。当前研究registry.meta中 `n_trials` 实际缺失，而协议要求该字段单调；FREEZE15不能被称作全项目累计。

建议独立记录 hypothesis_id、父规则、规则/参数/宇宙/成本/择优决定、首次观测、执行run_id关联与去重理由，分开保存hypothesis_N及engine_execution_count。补齐全局账以前不允许用局部12或FREEZE15宣称全局多重检验已校正。证据 `trial-accounting.json`。

### F3 — P2：比较入口没有强制校验旧证据的代码/数据世代

精确位置：`verify_batch.py:298-305, 317-341`；`run_batch.py:347-373, 1022, 1050-1052`。

原verify读取registry后直接用当前运行环境，没有核对registry.code与实际SHA256，也没有验证本次生产运行data_generation等于registry.bound。run_batch的before/after发生在矩阵装载前后，不是覆盖整个batch完成时段。故命令exit0本身不能证明跨时间复验的环境绑定。

本次审核额外保存生产比较前后完整指纹和世代，并核对每个文件与registry和evidence对应；此次均一致，消除了本次风险。建议比较器入口与结束时fail-closed核对完整代码哈希和数据generation，并将策略定义/override/配置、groups以及verify自身纳入可复现证据。没有在本轮实现修复。

## 5. 指纹与数据版本

本次registry、两份evidence、原交付及磁盘八文件逐项匹配，整体code.sha256为 `67afbcb7f5f0af187ed7a05cbe7597817e053b254b844ca4e3bc42429b2cf4d8`。

| 文件 | SHA256 |
|---|---|
| engine.py | ecc3d8261c5605edd877f5a48863cb239700486a9167de610ea0db82ec184cbe |
| strategy.py | c3bfb254969efcc6f756a2b248056f2c592e098883be02b78b41b47c1e12a23d |
| walkforward.py | c9506b15d5f1704f44138488a39cd6d976b2ff3961c4abd2ca6ddf90db1cd0ef |

其余matrix/optimizer/evidence/repository/run_batch完整哈希见 `independent-checks.json → hashes`，不是只核前三文件前缀。批量registry及每组evidence均绑定before=after=bound=`2b948c890e75472ab8317ca0ce40af77`；生产比较前后同值、代码前后全等。策略结果也与原交付相同。

研究员正在并行更新E1：现读PROTOCOL已标v3，并明说保留旧FREEZE及另做FREEZE_v3_E1。旧FREEZE对当前PROTOCOL/E1_E2_SPEC哈希不匹配是可见版本边界，不把它误称新的冻结通过；此处只对账旧FREEZE15的含义，不代替研究员E1验收。

## 6. 已验证及未验证

已验证：固定两组全部三折IS分数、OOS逐笔/权益/成本结果一致；真实单次共享装载、只读内存视图；连续账户无重复日期、完整189日时间线；未平仓期末估值及现金权益对账；完整代码与数据版本现场一致；39差异可解释；验证器盲点可复现；运行计数与假设计数已区分。

未验证：其他策略、参数扫描、截面排序对全轴差异的敏感性、10+组内存、trim_oos、前端/API、冷缓存、行情正确性、研究E1/E2有效性、现实盈利性；全项目历史假设精确N仍未知。两组该OOS收益分别-56.58%和-0.72%，不能作为稳定盈利证据。

交付判定：**matrix_native共享矩阵端到端缺口已补齐并通过本样本；验证器充分性不通过（F1）；全局N不得标已对账完成（F2）。** 正式实现修复应由系统开发工程师承担，本文不修改被审核生产代码。
