# E3 `in_universe` 五字段数据可得性（收窄版，2026-11-07）

- 仓库 `C:\work\sourcecode\tick-stock-panel`；数据 `D:\TSP\data`；DuckDB 1.5.3 / polars 1.44.1 / Python 3.11.15
- 口径：面板 `60*/00*`（E3 默认板块），评估窗 **2019-07-01 .. 2026-10-30**；交易日轴 = `kline_daily` 全部 distinct `date` = **2,141 天（2018-01-08 .. 2026-11-06）**，窗内 **1,779 天**
- 面板规模：`kline_daily_enriched` 6,438,822 行 / 3,385 只；窗内 5,510,001 行
- 只读：未写数据、未建表、未改代码、未跑回测。工作区原有未提交改动未触碰（新增文件仅本文件、JSON、`research/e3-data-availability-20261107/probe5.py`）
- 机器证据：`docs/factors/evidence/e3_data_availability_20261107.json`（44 段，33,346 B，每段含 SQL 原文 + 结果 + 耗时）
- 本文件取代上一轮 558 行长版 `docs/factors/evidence/E3_DATA_AVAILABILITY_20261107.md`；两者冲突以本文件为准

## 结论表

| # | 字段 | 结论 | 依据表 / 列 | 覆盖 | 关键行数 |
| --- | --- | --- | --- | --- | --- |
| 1 | 停牌 | **可得**（口径＝当日无 bar 行） | `kline_daily_enriched`：整行存在性；`volume` | 2018-01-08..2026-11-06 | `volume=0` **0 行**；缺行 **13,881 标的日 / 1,218 只** |
| 2 | 涨跌停 | **可得**（限价可复算）；「是否真不可成交」仅一字板可得 | `price_limits` 现算 `limit_up_price/limit_down_price/price_limit_pct`，入参 `raw_close`+`st_flag`+`listing_date` | 全窗 | 涨停 114,461 / 跌停 46,606 标的日；`price_limit_pct` 空值 **0** |
| 3 | 退市日 | **不可得** | 无字段（`instruments` 13 列无 delist/status）、无数据源 | — | 只能事后代理：消失 195 只，其中 ≥250 交易日无行情 171 只 |
| 4 | 上市天数 | **可得** | `instruments.listing_date`（VARCHAR）+ 交易日轴 | 1990-12-01..2026-11-03 | 有 bar 的 3,385 只 **100% 非空**；`observed_bars≥120` 满足 5,428,988/5,510,001 = 98.5% |
| 5 | 当日 ST | **2026-10-19 及之前可得；2026-10-20..2026-11-06 不可得** | `st_history/part.parquet`：`symbol`/`flag_date`(生效日)/`st_flag` | 2019-01-01..2026-10-29 | 7,758 行 / 5,817 只；末端 ST=True 由 218 家突降 20 家 |

---

## 1. 停牌 —— 可得，口径＝当日无 bar 行

**实测**：全库 `volume == 0` 行数 **0**（窗内 5,510,001 行 + 2018 预热 928,821 行均 0）；`amount==0`、`volume`/`raw_close` 空值同为 **0**。因此本库「停牌」只表现为**当日没有 bar 行**：存续区间内缺行 **13,881 标的日 / 1,218 只**，占格数 0.251%。

按年缺行（占同年行数）：2019 642(0.096%)、2020 3,072(0.431%)、2021 2,479(0.331%)、2022 2,206(0.290%)、2023 1,089(0.141%)、2024 1,374(0.179%)、2025 1,759(0.228%)、2026 1,260(0.195%)。

缺口长度：1 日 1,423 段 / 2–5 日 537 / 6–20 日 535 / 21–60 日 78 / 61–120 日 0 / 121–250 日 5 / **>250 日 4 段（最长 589 日）**。

**近似方案与偏差**：若把「`volume=0`」当停牌判据 → 检出 **0** 个停牌标的日，**漏检 13,881 个（100% 漏检）**，不可用。反之若把所有缺行都当停牌 → 其中 **1,113 个（8.0%）落在 27 个采集洞日**（当日缺失率 >1%，单日最高 2.32%），这部分是采集缺陷，归因层应给 `null`，不应算作「停牌第 N 日」。对 E3 本身无影响：缺行 → `bar_present=False` → 按契约 §2.3 直接判 `0.0`。

```bash
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe -c "
import duckdb; c=duckdb.connect(); c.sql('SET enable_progress_bar=false')
P=\"read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet')\"
c.sql(f\"create view bars as select * from {P} where symbol like '60%' or symbol like '00%'\")
print('rows_in_window:', c.sql(\"select count(*) from bars where date between '2019-07-01' and '2026-10-30'\").fetchall())
print('vol0:', c.sql(\"select count(*) filter(where volume=0) from bars where date between '2019-07-01' and '2026-10-30'\").fetchall())
c.sql(\"create view ax as select distinct date from read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet')\")
print('gap:', c.sql(\"\"\"with s as (select symbol,min(date) f,max(date) l from bars where date between '2019-07-01' and '2026-10-30' group by 1),
 g as (select s.symbol, a.date from s join ax a on a.date between s.f and s.l where not exists (select 1 from bars b where b.symbol=s.symbol and b.date=a.date))
 select count(*), count(distinct symbol) from g\"\"\").fetchall())"
# 实测输出: rows_in_window 5,510,001 / vol0 0 / gap (13,881, 1,218)
```

## 2. 涨跌停 —— 可得（限价可复算），成交性仅一字板可得

**库里没有现成列**：`kline_daily_enriched` 15 列（`symbol,date,open,high,low,close,volume,amount,raw_close,raw_high,raw_low,turnover_rate,consecutive_limit_ups,consecutive_limit_downs,quote_ts`）**无** `limit_up_price`/`price_limit_pct`；`instruments.limit_up/limit_down` 两列 **5,536 行全空**、`as_of` 单值 2026-11-05。限价必须用既有实现现算：`backend/app/price_limits.py` + `backend/app/indicators/pipeline.py#compute_limit_signals`（入参：昨收 `raw_close`、`st_flag`、`listing_date`/`day_rank`）。

**实测（窗内）**：`price_limit_pct` 空值 **0**；`limit_up_price` 空值 3,932（= 每只首根 bar 无昨收 + 无涨跌幅限制日）。涨停 **114,461** 标的日、跌停 **46,606**；其中**一字板涨停 11,513**（`raw_high==raw_low`，确定不可成交）、非一字涨停 102,948（日内有价差，不可成交性需分钟线）、全日一价但非涨跌停 92、`raw_high` 超涨停价 0.006 以上仅 20 行（口径噪声）。

**ST 的 5% 与其他档位如何区分**（`price_limit_pct × st_flag`，行数）：`st_flag=false, 0.10` 5,035,778 + 241,794（2026-07-06 后）；`st_flag=true, 0.05` 222,293；`st_flag=true, 0.10` 10,136（2026-07-06 后 ST 档改为 10%）。**20%/30% 档 0 行**（创业板/科创板不在 `60/00` 池）。即：档位由 `st_flag` + 板块 + 日期决定，**ST 的 5% 与普通 10% 可由 `st_flag` 精确区分**，不需要从价格反推。

**T+1 开盘可成交性**：涨停日次日开盘即达涨停价 **7,894** 标的日（已剔除次日除权行；不剔除为 7,916，差 22 行 = 0.28%）。偏差来源：`raw_open` **不在库内**，只能用前复权 `open` 比原始限价，除权日错配；剔除后 22 行即误差上限。

```bash
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe research/e3-data-availability-20261107/probe5.py 2>&1 | grep -E "涨停|跌停|price_limit_pct"
# 输出（节选）: 判为涨停的标的日 114461 / 判为跌停的标的日 46606 / 涨停且 raw_high==raw_low 11513
#              price_limit_pct 为 null 的标的日 0 / 涨停日次日开盘即涨停（剔除除权行） 7894
# 全量 13 项见 JSON F2_1..F2_13；整脚本约 2 分钟
```

## 3. 退市日 —— 不可得

**逐项确认「没有」**：`instruments` 13 列 `symbol,name,code,exchange,region,type,listing_date,total_shares,float_shares,tick_size,limit_up,limit_down,as_of`，按名匹配 delist/status 列 **0 个**；`D:\TSP\data` 下无退市目录（`data_sources`、`instruments_ext`、`pools` 皆空）。无退市日、无退市公告日、无退市类型。

**唯一代理＝最后一根 bar**（事后信息）：评估窗内不再有行情的 **195 只**（最后 bar 年份 2019:5、2020:12、2021:18、2022:34、2023:37、2024:43、2025:24、2026:22）。按缺失交易日分档：<5 日 1、5–19 日 4、20–59 日 3、60–119 日 10、120–249 日 6、**≥250 日 171**。另：维表里有、K 线一根都没有 **78 只**（`60/00` 75 只）；北交所 355 只有 K 线、维表 **0 行**。

**「≥250 日无行情＝退市」不成立**：窗内有 **4 段 >250 交易日的中途缺口后来复牌** — `000670.SZ` 589 日（2020-03-20..2022-08-19）、`000792.SZ` 311、`002711.SZ` 263、`600891.SH` 255。且 <60 日消失的 8 只无法区分停牌/退市。现名含「退」155 只里 140 只仍有 bar、**0 只**在数据末端交易 → 名字是抓取时的名称，不是时点状态，不能当日判据。

**偏差量级**：用「≥250 交易日无行情」当退市 → 会把上述 4 只复牌标的在停牌期间误判为已退市（4 段 / 1,418 标的日），并对 8 只 <60 日消失标的给不出结论（应 `null`）。**替代方案**：接入退市公告或交易所摘牌名单（本仓库无该数据源，本次未购买、未联网）；代价＝1 个外部数据依赖 + 需要历史时点版本，不是代码改动。

```bash
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe -c "
import duckdb; c=duckdb.connect(); c.sql('SET enable_progress_bar=false')
print(c.sql(\"select count(*) filter (where lower(column_name) like '%delist%') from (describe select * from read_parquet('D:/TSP/data/instruments/instruments.parquet'))\").fetchall())
print(c.sql(\"\"\"with k as (select symbol,max(date) lb from read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet',hive_partitioning=true,union_by_name=true) where symbol like '60%' or symbol like '00%' group by 1)
 select year(lb) y, count(*) from k where lb<(select max(lb) from k) group by 1 order by 1\"\"\").fetchall())"
# 实测输出: (0,) / [(2019,5),(2020,12),(2021,18),(2022,34),(2023,37),(2024,43),(2025,24),(2026,22)]
```

## 4. 上市天数 —— 可得

`instruments.listing_date` 类型 **VARCHAR**（`'YYYY-MM-DD'`，比较前需解析）：全表 5,536 行、非空 5,533（3 只空）；`60/00` 域 3,460 只中 3,458 非空，缺的 2 只都是无 K 线的壳。**E3 实际用到的 3,385 只（有 bar）100% 非空**，取值域 1990-12-01..2026-11-03。

**`observed_bars>=120` 可算**，且必须用「`listing_date` + 交易日轴计数」，不能用自然日差、也不能用 bar 序号：
- 窗内符号日 5,510,001，其中 `observed_bars≥120` **5,428,988（98.5%）**；
- 换用「上市自然日差≥120」会**多纳入 38,627 标的日（0.70%）**、少纳入 **0** 标的日 —— 这 38,627 是缺行/首根偏晚导致 bar 数不足、但日历上已「够老」的样本；
- 首根 bar ＝ 上市日：2018-01-08 后上市 635 只中 **634** 只逐位相等，1 只（`603056.SH`）首根晚 651 天；
- 2018 年前上市的 2,750 只首根全被面板起点截断（首根＝2018-01-08 或更晚），**bar 序号不能当上市交易日数**。

```bash
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe -c "
import duckdb; c=duckdb.connect(); c.sql('SET enable_progress_bar=false')
print(c.sql(\"\"\"with b as (select symbol from read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet') where symbol like '60%' or symbol like '00%'),
 i as (select symbol, listing_date ld from read_parquet('D:/TSP/data/instruments/instruments.parquet'))
 select count(*), count(ld) from (select distinct symbol from b) s left join i using(symbol)\"\"\").fetchall())"
# 输出: (3385, 3385) —— 有 bar 的 60/00 标的上市日 100% 非空
```

## 5. 当日 ST 标记 —— 2026-10-19 及之前可得，之后不可得

**表**：`D:\TSP\data\st_history\part.parquet`，列 `symbol` / `flag_date`（**生效日**，date）/ `st_flag`（bool）。**7,758 行 / 5,817 只 / 2019-01-01..2026-10-29**，其中 True 986 行、False 6,772 行。as-of 读法 `join_asof(strategy="backward", by="symbol")`（`backend/app/tickflow/security_status.py#attach_st_history`）。面板 3,385 只中 **3,384** 只有 ST 历史行（无行＝从未 ST，非缺失）；2019 年前 **0 条** → 评估窗内无 null 段。

**时点正确性：是（表是生效日区间表，不是当前简称）**，但**末端被截断**，这是本次唯一的硬缺陷：

| 交易日 | 面板 bar 数 | as-of ST=True 家数 | ST=False 家数 |
| --- | --- | --- | --- |
| 2026-10-15 | 3,189 | **218** | 5,594 |
| 2026-10-16 | 3,190 | **218** | 5,595 |
| 2026-10-19 | 3,187 | **218** | 5,595 |
| **2026-10-20** | 3,191 | **20** | 5,793 |
| 2026-10-29 | 3,189 | **20** | 5,797 |
| 2026-11-06 | 3,190 | **20** | 5,797 |

截断机制：`flag_date=2026-10-20` 一次性写入 **198 行 `st_flag=False`（198 只）**，此后到 2026-10-29 只有 4 条 False 事件、**0 条 True**。ST=True 家数因此由 218 突降 20（**掉 198 只**）并持续到最后交易日 2026-11-06（共 14 个交易日）。

**对契约 8 日窗口（2026-10-20..2026-10-29）的判定：不可得。** 该窗口内 `st_flag=True` 记录 **0 条**、`False` 202 条，无法反映真实 ST 变动；`2026-10-20..2026-11-06` 共 14 个交易日都应输出 `null`。**本证据支持契约「该 8 日 `count(in_universe ∈ {0.0,1.0})` 必须为 0」的断言**；若实现按现有数据直接算，会把 198 只真实 ST 标的错判为非 ST（当日 `in_universe` 由 0.0 变 1.0），偏差 198 只/日 × 14 日 = 2,772 标的日。

```bash
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe -c "
import duckdb; c=duckdb.connect(); c.sql('SET enable_progress_bar=false')
c.sql(\"create view sth as select symbol, cast(flag_date as date) fd, st_flag from read_parquet('D:/TSP/data/st_history/part.parquet')\")
print(c.sql(\"select fd, st_flag, count(*) from sth where fd between date '2026-10-15' and date '2026-10-30' group by 1,2 order by 1,2\").df().to_string())"
# 实测输出: 10-15 两条 False / 10-16 一条 False / 10-20 198 条 False / 10-21、10-22、10-23、10-29 各 1 条 False；无任何 True
```

## 未验证 / 未知（不猜）

1. 「停牌」的官方原因、预计复牌日、连续停牌天数：**不可得**（库内无字段），本次未验证替代来源。
2. 非一字涨停当日是否真的买不到：**未验证**（需分钟线或逐笔，本次未读分钟数据）。
3. `000670.SZ` 等 4 段 >250 日缺口的真实原因（重大事项停牌 / 数据缺失）：**未知**。
4. ST 表在 2026-10-20 被截断的**原因**（源库抓取失败 / 状态源变更）：**未知**，只能确认现象与规模。
5. 北交所 355 只的上市日与退市日：**不可得**（`instruments` 无 `.BJ` 行），本次未寻找其他维表。
6. 本文件全部数字为 2026-11-07 单次快照；数据目录继续更新后，`2026-10-30` 之后的统计需重跑 `probe5.py`。
