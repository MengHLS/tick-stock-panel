# 策略可靠性审计与候选验证

创建时间：2026-11-06T20:12:43+08:00。状态：连续账户 WFO 与逐标的行情守卫已实现并重算 T74；可靠高收益策略仍未建立。使用 bgx 5.1.0，默认标准深度，顺序执行，未创建分支、提交或部署。

本文件是本次研究资料索引和执行台账；长期结论见 [RESULTS.md](../../docs/research/strategy-reliability-20261106/RESULTS.md)。既有 BGX G01—G11 报告和本轮进入工作区前的修改均保留，本轮新增发现从 G12 起编号。

## 授权与实施台账

用户经当前任务授权项目检查、可逆修复和必要验证；不需要再次选定本轮实施范围。测试预算为受影响回测模块及复盘、盘中、市场阶段代表性链路，无全仓构建、部署或真实交易。

| 任务 | 独占范围/产物 | 验收与状态 |
| --- | --- | --- |
| T01 读取规范与现状 | 根规范、现有 BGX 报告、数据与核心调用链 | 已核查；已有工作区修改保留 |
| T02 修复 G12 | `backend/app/backtest/walkforward.py`、对应测试 | 新增 3 个用例先全部失败；修复后所在 136 项集合通过 |
| T03 固定候选检验 | 本目录 `scripts/`、本地 `results/` | 4 年 × 3 规则 × 2 成本共 24 组完成，全部亏损；源指纹、时序与截断核查通过 |
| T04 复盘/盘中/择时抽查 | 现有代表性测试、研究报告 | 第二组 110 passed / 1 xfailed；不是实盘或通知投递验收 |
| T05 WFO 账户聚合治理 | `walkforward.py`、API、WFO 页面、单元/ worker 回归 | 已实现并验证交易日切分、拒绝 full、保留低交易折、前端文案与构建 |
| T06 数据可靠性补齐 | 历史生命周期扫描、PIT 行业覆盖、扩展配置恢复 | 已修复可解析配置；已量化退市样本与 6 天行业 PIT；完整外部证券主数据仍缺 |
| T07 新确认实验 | 冻结规则和完整样本账 | 待实施；本次负结果不追调，不打开既有竞价锁箱 |
| T08 连续账户 WFO | `engine.py`、`strategy.py`、`walkforward.py`、API、WFO 页面、测试 | 已实现并验证：结转持仓/计划、空折平线、缺标的 fail-closed、失败即停；T74 连续 +23.08% vs 重置 +11.42% |
| T09 逐标的行情守卫 | `services/quote_freshness.py`、`quote_service.py`、`strategy/monitor.py`、测试 | 已实现并验证：陈旧/缺失/超前/复权降级拒绝并留痕；真实断流回放未做 |

T07 仍是未完成项。T06 的配置尾部已恢复，但历史成员完整性和 point-in-time 数据仍不足以做行业结论；本轮未用当前快照冒充历史行业。T07 需要新的未观察数据成熟；历史数据不能在被观察后重新变成独立样本外。T08 修的是账户口径，不消除 T74 的事后事件 allowlist 污染；T09 的 120 秒阈值尚未按供应商真实延迟分布标定。

T08 追加修正：末折 `carry_out=False` 不产出 carry 状态，旧报告把 `carried_out_positions` 写成 0，与汇总 5 笔未平仓矛盾。已改为末折取权益曲线末点持仓，并新增 `final_cash/final_positions/final_market_value`、`open_at_end_by_fold`、`trade_lifecycle` 与 6 项引擎不变量；`verify_continuous_account.py` 同步扩到 19 项独立核对。重跑后收益与逐折权益不变。

## 可复现入口

从项目根目录运行，使用现有 Python 环境，不安装依赖。数据位置由项目配置解析，报告不保存密钥或完整配置。

```powershell
$env:PYTHONUTF8='1'
$env:POLARS_MAX_THREADS='4'
backend\.venv\Scripts\python.exe research\strategy-reliability-20261106\scripts\validate_candidates.py `
  --years 2023,2024,2025,2026 `
  --output research\strategy-reliability-20261106\results\constrained-validation.json
backend\.venv\Scripts\python.exe research\strategy-reliability-20261106\scripts\audit_results.py
backend\.venv\Scripts\python.exe research\strategy-reliability-20261106\scripts\run_wfo_t74.py
backend\.venv\Scripts\python.exe research\strategy-reliability-20261106\scripts\run_wfo_t74_continuous.py
backend\.venv\Scripts\python.exe research\strategy-reliability-20261106\scripts\verify_continuous_account.py
```

运行会在本目录产生 JSON，调用现有数据读取接口及生产撮合器，不安装用户策略，不发通知，不下单。`DataStore` 初始化复用项目现有存储初始化逻辑；本次目标数据目录已存在。正式数据内容读取，研究结果写入独立目录。

## 本地产物

- `results/constrained-validation.json`：最终约束口径，24 组统计、年度基准、信号数量、交易摘样、输入与脚本指纹。
- `results/trades-<年>-<规则>-<滑点>.json`：24 份实际模拟交易记录。
- `results/audit-checks.json`：源指纹一致、4 个截断样本、24 组交易时序、公司行为覆盖及损坏配置诊断。
- `results/wfo-t74-baseline.json`：修复后 252/63/63 实际交易日 WFO，6 折，逐折收益、回撤、交易数、低交易标记与汇总。
- `results/wfo-t74-continuous.json`：连续账户回放（单账户单时间线，含折边界权益/持仓/计划）。
- `results/wfo-t74-reset.json`：同参数逐折重置对照（旧口径）。
- `results/wfo-t74-comparison.json`：两种口径的紧凑对照与逐折段收益。
- `results/validation.json`：首轮探索记录，**缺少显式涨幅限制比例列和最低佣金，不作为最终结论依据**。保留该记录用于说明口径修订，未伪装成独立重复实验。
- 根 `.artifacts/strategy-reliability-20261106-constrained.log`：最终运行输出；首轮日志为同名去掉 `-constrained` 的文件。

结果目录由本目录 `.gitignore` 排除，保护由本地用户行情衍生的交易明细。源码和结论可单独审查；没有提交任何文件。

## 回滚与生效

G12 的改动是测试闭区间终点减一天，以及重叠步长显式拒绝；回滚时需撤销该逻辑及对应测试，不能还原整个工作区。没有修改行情仓库、策略文件、缓存 schema 或数据库。

第二轮业务改动覆盖 WFO 日期轴、`full` fail-closed、低交易折保留、WFO API/前端合同和 WFO 页面。第三轮追加连续账户结转（`PortfolioCarryState`、`carry_in/carry_out`、段末计划/挂单）与逐标的行情守卫；回滚需同时撤销这些相关文件与测试，不能只改单个字段。旧保存结果不会被改写。

新研究脚本直接运行生效。正在运行的后端未重启；新的后端 WFO 逻辑、API 拒绝与前端文案需重启后端并重新构建前端后生效。用户真实页面操作、通知外发、发行包、生产部署均未验。
