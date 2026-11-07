# 每日复盘入口与自动化路径

## 1. 一条命令

```bash
# 在 research/trade-ledger-20261107 目录下
backend/.venv/Scripts/python.exe -m tsp_ledger.cli daily \
    --date 2026-11-06 \
    --file "D:\TSP\data\user_data\trade_ledger\inbox\Table_7010.csv" \
    --signals "D:\TSP\data\user_data\trade_ledger\inbox\signals_20261106.csv" \
    --out "D:\TSP\data\user_data\trade_ledger\daily"
```

- `--date` 必填，其他可省：不给 `--file` 就只用库里已有数据；不给 `--signals` 就对账表全为 `no_signal`。
- `--file` 可以每天给同一张**全量**交割单：导入是幂等的（按 发生日期+时间+成交编号 去重），
  重复导入 `rows_new = 0`，所以"每天重导一遍"是最稳的做法，不需要自己算增量。
- 也可以双击 `run_daily.cmd 2026-11-06`（同目录，自动用后端虚拟环境）。

Python 侧调用：

```python
from pathlib import Path
from tsp_ledger.cli import _derive_all, _ingest, _db, build_parser
from tsp_ledger.daily import daily_review

args = build_parser().parse_args(["daily", "--date", "2026-11-06"])
con = _db(args)            # 台账连接（默认 D:\TSP\data\user_data\trade_ledger\ledger.sqlite）
_ingest(con, ["<交割单.csv>"])
events, cal, prices, rts, daily, positions, detail, exposure, industry = _derive_all(con, args)
daily_review(events, rts, daily, positions, "2026-11-06", Path("<输出目录>"))
```

## 2. 产物（每个交易日一个目录）

| 文件 | 内容 |
| --- | --- |
| `events.csv` | 当日全部事件（含转账、利息、红利、新股入账） |
| `fills.csv` | 当日成交明细，费用四项拆分 + 含费净价 |
| `roundtrips.csv` | 当日平仓回合（FIFO，含 hold_td、flags） |
| `equity.csv` | 当日权益、现金、市值、净入金、累计盈亏、较前一日变化 |
| `positions.csv` | 当日日终持仓（代码 + 数量） |
| `reconcile.csv` | 与系统信号的对账表：实际列已填，计划列空，偏离列待决策侧填 |
| `summary.md` | 一页纸摘要（权益、成交、回合、对账行数） |

实测（2026-11-06）：2 笔成交、3 个平仓回合、已实现 152.80 元、费用 17.23 元、
权益 16,249.36（较前一日 −7,278.23，主因转出 14,500 元）、对账 2 行。

## 3. 对账表怎么用

`reconcile.csv` 是**空表**，系统只填实际成交一侧：

- `link_status = matched`：同日同码同向在信号文件里找到计划；
- `link_status = no_signal`：没有对应计划 —— 需要决策侧判断是"手工单"还是"信号漏记"；
- `deviation_type` / `deviation_reason` 由决策侧填写（枚举见 `FIELD_DICT.md` §7）。

反向的"有计划没成交"当前无法从交割单还原（没有委托流水），需要信号侧自己回报，
或后续接入券商委托查询。这是本工具已知缺口，不要在复盘结论里当成"没下单"。

## 4. 自动化两条路径

### 路径 A：券商导出目录监控（推荐，需要系统开发配合）

流程：券商客户端定时导出 → 监控目录出现新文件 → 自动 `import` + `daily` → 复盘包落到
`user_data/trade_ledger/daily/<date>/`。

需要满足：

1. 券商客户端支持**自动导出到固定目录**（或每天手动点一次"导出"，落到固定目录即可）；
2. 系统侧有一个调度入口。当前 `user_data/task_registry.json` 只有 `backtest` 类任务，
   要加 `ledger_daily` 这类任务需要系统开发工程师改后端（属于系统开发范围，不在本工具内）；
3. 触发时间放在**行情库当日分区就绪之后**（否则当日市值会退化为 `last_trade` 口径，
   `price_src` 列会标出来）；
4. 失败可见：导入失败要能报警（编码识别不了、缺列、未知交易类别），否则会静默缺数据。

监控目录建议：`D:\TSP\data\user_data\trade_ledger\inbox\`；处理完的文件移到 `inbox\done\`，
台账库里 `import_batch` 记录每次的文件 sha256，可反查"这份文件到底导没导过"。

目录已建好，现场长这样：

```
D:\TSP\data\user_data\trade_ledger\
  ledger.sqlite                      台账（已含 20261107 全量交割单）
  inbox\jiaogedan_full_20261107.csv   本次输入快照（sha256 ebebda13…a29a295）
  inbox\signals_template.csv        对账信号表模板（Table_7010.csv 只有实际成交）
  inbox\done\                        处理完的原始文件归档位
  exports\                          全量导出 + summary.json + verify_report.json
  daily\2026-11-06\                 每日复盘包
```

### 路径 B：手动导入（今天就能用，零系统改动）

每天收盘后：券商导出 → 存到 `inbox\` → 双击 `run_daily.cmd <日期>`。耗时约 10 秒
（1055 行全量导入 + 396 天派生 + 当日复盘包）。

两条路径不冲突：手动跑过的文件，自动化再跑一次也不会重复（幂等），`rows_new = 0`。

## 5. 常见失败与处理

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `无法识别交割单编码` | 文件被 Excel 另存成其他编码 | 用券商原始导出文件，不要用 Excel 中转 |
| `交割单缺少必要列` | 券商改了表头 | 把实际表头发给系统开发，扩 `HEADER_ALIASES` |
| 出现 `category = other` 的 warning | 新的交易类别 | 在 `CATEGORY` 里补映射，不要让它默默进"其他" |
| 某日 `mv` 明显异常 | 行情缺该日分区 | 看 `daily_position.price_src`，缺数据会标 `last_trade`/`missing` |
| 派生直接报错"行情价格为 0 条" | 用了没装 polars 的 python（如系统 python） | 改用 `backend/.venv/Scripts/python.exe`；确认 D:\TSP\data\kline_daily 存在 |
| 回合数比预期少 | 卖出无买入来源（如转债、老仓位） | 看 `flags = unmatched_sell`，不要当成丢数据 |

## 6. 可追溯性要求（复盘纪律）

- 每次导入的 `import_batch` 保留：文件名、sha256、编码、行数、新增/重复行数、日期区间、时间戳。
- 派生表可随时用同一批事件重建，重建结果应逐字段一致（`verify` 可验证）。
- 原始交割单不要改名覆盖；同一份文件重导是安全的，改内容重导会产生新 `event_uid`（成交编号变了），
  这在复盘里必须能看出来 —— 所以 `import_batch.file_sha256` 是核对的第一入口。
