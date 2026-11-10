# S01b 双均线 20/60 · 结案索引

**结论：不通过（生产不采用）· 研究基准保留。** 2026-11-09 裁定。
正式记录见 [`docs/research/S01B_RULING_20261109.md`](../../docs/research/S01B_RULING_20261109.md)。

## 唯一基准（系统回测）

| 项 | 值 |
| --- | --- |
| 区间 | 2019-07-01 ~ 2026-10-30 |
| 笔数 | 199（completed 194 / open_at_end 5） |
| 总收益 | +24.27% |
| 年化 | +3.13% |
| 最大回撤 | −39.27% |
| 期末权益 | 1,242,725.28 |

口径：成本 10bp、入价基不复权、挡涨停开盘、期末强制平仓、最低佣金。
换区间即另一条结果，结论不得混用。

**复现条件（2026-11-09 实测修正，原文「点开直接跑即复现」不成立）：**
跑回测时必须同时给出以下 7 项请求级参数，否则得到的是另一组数（页面默认参数实测为 **414 笔 / −50.94%**）：
`start=2019-07-01`、`end=2026-10-30`、`max_positions=5`、`max_exposure_pct=0.6`、`holding_days=60`、`commission_pct=0.0003`、`stamp_tax_pct=0.001`、`slippage_bps=10`（另 `matching=open_t+1`、`mode=position`、`position_sizing=equal`、`initial_capital=1000000` 与默认一致）。
原因：策略文件的 `META.backtest_defaults` 只能承载执行口径字段（入价基、挡涨停、期末平仓、最低佣金等）；组合与成本参数写在里面**不会生效**——引擎解析后丢弃，`POST /api/backtest/strategy/run` 只从请求构造配置。该结构性问题已登记 `docs/document-management/ISSUES.md`，本轮不改代码。

**系统内已存记录（2026-11-09 20:03）**：`saved_id eaaf69683a248d06`，名称「S01b 双均线20/60 · 基准 2019-07-01~2026-10-30 · 199笔/+24.27%」。该记录把 199 笔逐笔、1779 点权益曲线、完整配置与策略文件指纹 `deb5eb59` 一起钉住，页面「策略回测 → 已保存结果」可直接打开复看，无需再手填参数。

## 生产文件改了哪一处

`D:\TSP\data\strategies\custom\custom_mw7fvp17.py`：3,478 → 3,793 字节，**+8 / −0 行**，只多 `META.backtest_defaults` 一块。
`STOP_LOSS = None`、`MAX_HOLD_DAYS = 60`、事件式 `cross_down` 均未动。
改后界面数字由 208 笔 / −51.47% 变为 199 笔 / +24.27%，与基准逐字段相同。

## 回滚点

`prod_file_snapshots/`
- `custom_mw7fvp17.py.prod_3478B_85ae72a5.py` — 改前，与当时线上逐字节相同
- `custom_mw7fvp17.py.prod_3793B_deb5eb59.py` — 改后，与现线上逐字节相同

逐版本说明见 [`ROLLBACK_NOTES_20261108.md`](ROLLBACK_NOTES_20261108.md)。

## 目录

| 路径 | 内容 |
| --- | --- |
| `REPORT.md` | 完整研究记录（含四臂分解与诊断） |
| `PREREG_S01B_20261108.md` | 预注册（事前写定的判据） |
| `metrics_table.md` / `metrics.json` | 关键数字 |
| `prod_file_snapshots/` | 生产文件各版本快照 = 回滚点 |
| `strategies/`、`strategies_gross/` | 回测所用策略副本 |
| `verify_list_result.json` | 信号清单校验结果 |
| `_exploration/` | 探索过程产物（四臂结果、诊断、交叉核对）。**不作验收依据**，见 DELIVERY_PROTOCOL 第〇节 |
| `_scripts/` | 探索脚本。仅用于研究，不进交付报告 |

## 相邻目录

- `../s01b-review-20261108/` — 独立审核（含 audit）
- `../s01-serial-20261108/` — 串行推进相关运行
- `../s01-caliber-gap-20261108/` — 口径差异记录

## 不再追的事（只登记）

见 `docs/document-management/ISSUES.md`：
- `risk_limits.py:55` 天数 `int()` 静默截断
- `backtest/strategy.py` 四个 override 读点无校验（`:1601 / :1621 / :1241 / :1422`）
