# E3 股票池掩码 · 四类信息（ST / 上市天数 / 停牌 / 退市）可得性取证

- 取证日期：2026-11-07
- 仓库：`C:\work\sourcecode\tick-stock-panel`（分支 `dev`，工作区有未提交改动，见下）
- 数据目录：`D:\TSP\data`
- 运行环境：`backend/.venv/Scripts/python.exe`（Python 3.11.15、polars 3.0.3、pyarrow 24.0.0、duckdb 1.5.3）
- 纪律：**只读**。本文件为新增；未修改任何既有文件、未写数据、未改代码、未提交、未部署、未重启服务、未购买数据。
- 判据来源：`docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107.md`（G1 交易日轴 / G2 as-of / G3 三态 / G4 keep / G8 fail-closed；§2 E3）
- 写作口径：**确证**＝本次实测复现的数字；**未知**＝本仓库内无证据可判，单独标注，不猜。

## 0. 结论速览（四字段各自独立，不合并）

| 字段 | 结论（三选一） | as-of（G2） | 三态（G3） | 一句话理由 |
| --- | --- | --- | --- | --- |
| **ST** | **可得（可真实现）**，附一条强制前置 | 满足：表是「生效日 + 布尔」的区间表，`join_asof(backward)` 即得 | 满足：2019 年前整段为 `null`（实测 755,758 格） | 有独立历史区间表 `st_history`，**不需要**靠证券简称推断；但数据末端 14 个交易日被截断（ST=True 计数 0），用于生产前必须先修或该段置 `null` |
| **上市天数** | **可得（可真实现）** | 满足：上市日是不变量 | 满足：仅 3 只空值 + 北交所 355 只无维表行为 `null` | `instruments.listing_date` 在 `60/00` 域（E3 默认板块）**3,385 只 100% 非空**，配合 G1 交易日轴可精确算「上市第 N 个交易日」；634/635 只 2018 年后新上市标的的 K 线首根＝上市日 |
| **停牌** | **可得（口径＝当日无 bar 行）** | 满足：当日有没有 bar 是当日事实 | 不适用：该口径只有两态（有/无行）；三态只出现在「归因」层 | 实测全库 `volume == 0` 的行数为 **0**，所以「停牌」与「当日无 bar 行」在本库等价，`bar_present` 覆盖 100%；但「停牌原因/预计复牌日/连续停牌天数」**不可得**，且 2018 有 2.88% 的日均缺行是数据洞，不能当停牌 |
| **退市** | **近似（approx，禁止用于策略判据）** | 不满足（无退市日可比对） | 只能给三态中最粗的一态：无 bar | 全库**无退市日/退市类型字段**，无退市数据源；只能从「最后一根 K 线」推。≥250 个交易日无行情的 209 只可视为已退市，但 <60 个交易日的 11 只无法区分停牌与退市 |

**对判据的直接影响（最重要的一条）**：契约 §2.2 的 E3 输入列只有 `raw_close`/`volume`/`amount`/`st_flag`/`bar_present`/`warmup`，**「停牌 / 退市 / 上市天数」不是显式输入列**，它们只是 `bar_present=False` 与 `observed_bars<120` 的隐式等价物（§2.3 已把「前置 bar<120」直接判为 `0.0`）。因此**E3 不是「因为缺停牌/退市标志位只能标 approx」**：三项支撑数据（ST 表、bar 存在性、raw_close）都在库内可直接算出。唯一真正的阻塞是 ST 表末端截断（见 §2.5），不是缺字段。

---

## 1. 数据布局事实（先确认前提，否则后面每条数字都不可复算）

| 项 | 实测 | 证据 |
| --- | --- | --- |
| 交易日分区数 | **2,141** 个 `date=YYYY-MM-DD` 目录，**无周末**，最大间隔 11 天（春节/国庆长假） | `ls /d/TSP/data/kline_daily | wc -l` |
| 区间 | **2018-01-08 .. 2026-11-06** | 同上 |
| 行数 / 标的数 | **9,780,842 行** / **5,813 只**（`(symbol,date)` 无重复） | §附录 C1 |
| 物理布局 | **两套**：2018-01-08..2018-11-30（219 天）为 85 个 `part-stream-*.parquet` 分片；2018-12-03..2026-11-06（1,922 天）为单 `part.parquet`。另 `date=2026-10-26` 只有 `part-stream-0.parquet` | §附录 C2 |
| schema 漂移 | 两种列集：1,912 个分区 `(symbol,date,open,high,low,close,volume,amount)`；**9 个分区（2026-10-27..2026-11-06）多一列 `quote_ts`**。`volume` 类型 **7 个分区为 int64、其余为 double**（2026-10-28 起） | §附录 C3 |
| 无成交行 | `volume == 0` 的行数 **0**；`volume`/`close` 空值 **0** | §附录 C1 |
| 不复权价 | `kline_daily` **没有** `raw_close`；`kline_daily_enriched` 有 `raw_close/raw_high/raw_low`，**2,141 分区 / 9,780,842 行 / 5,813 只、100% 非空**，其中 7,406,313 行 `close <> raw_close` | §附录 C4 |
| instruments 维表 | `D:\TSP\data\instruments\instruments.parquet`，**5,536 行 × 13 列，`type` 全为 `stock`，`as_of` 只有一个值 2026-11-05**（单期快照，无历史版本） | §附录 C5 |
| 板块分布（K 线域） | `60*` 1,793 / `00*` 1,592 / `30*` 1,452 / `68*` 621 / `92*.BJ` 355。**契约默认池 `60/00` 共 3,385 只** | §附录 C6 |
| 交易日轴自校验 | 若研究面板 1,779 个交易日止于数据末端，起点为 **2019-07-08**；该区间 `60/00` 日均 bar 数 **3,098.6**，与契约 §2.1 注 2 的 **3,095** 相差 3.6 只（0.1%），口径吻合 | §附录 C7 |

**踩坑提示（会直接影响 E1/E2/E3 两条路径的实现）**：直接用 `pl.scan_parquet("kline_daily/date=*/*.parquet")` 读全历史会**抛 `SchemaError`**（列集不一致）或 `data type mismatch for column volume`。必须 `extra_columns="ignore"` + `cast_options`/`union_by_name`。DuckDB 侧 `union_by_name=true` 即可。**系统侧若按 `part.parquet` 单文件 glob 读，会漏掉 2018 年那 219 天（220 个目录的 `part.parquet` 不存在）。**

---

## 2. ST（风险警示）—— 结论：**可得（可真实现）**，附强制前置

### 2.1 字段是否存在、在哪、列名/单位、覆盖区间

| 项 | 实测 |
| --- | --- |
| 位置 | `D:\TSP\data\st_history\part.parquet`（21,452 B）+ 同目录 `manifest.json`（821 B） |
| 列 | `symbol`（str，如 `000004.SZ`）、`flag_date`（date，**生效日**）、`st_flag`（bool） |
| 单位 | 无；`st_flag=True` 表示从 `flag_date` 起为风险警示状态 |
| 覆盖 | **2019-01-01 .. 2026-10-29**（`flag_date` 取值域；manifest 声明 `coverageStart=2019-01-01`、`coverageEnd=2026-10-29`） |
| 来源（manifest 声明，未独立核实） | 源库 `stock-limit-up-analyzer` 的 `research_security_status_history.statusType=ST`；标识来自 `research_security_identifier_history.identifierType=primary`；`absencePolicy=absence_of_ST_interval_is_non_ST`；`sourceStIntervals=1043`、`outputRows=7758`、`unmappedStIntervals=0`、`conflicts=0`、`currentOnlyBaselines=4` |
| 读取/规范化实现 | `backend/app/tickflow/security_status.py#read_st_history`(L27) / `#normalize_st_history`(L37) / `#attach_st_history`(L64，`join_asof(strategy="backward", by="symbol")`) |
| 供给实现 | `backend/app/data_providers/local_st_history.py`（provider 名 `local_st_history`，`capabilities.st_history=True`）；`FileMarketData.get_st_history()` 在 `backend/app/extensions/adapters.py:382/96` |
| 研究侧是否在用 | 是：`research/strategy-search-20261107/scripts/common.py:37,87,101` |

### 2.2 覆盖率（实测数字）

| 指标 | 数字 |
| --- | --- |
| 行数 / 标的数 / 生效日数 | **7,758 / 5,817 / 1,436** |
| `st_flag` 取值 | True **986** 行、False **6,772** 行；空值 **0**；`(symbol,flag_date)` 重复 **0** |
| 曾经 ST 的标的 | **712 / 5,817**（12.2%）；每只的状态切换次数中位数 1、最大 9 |
| 基线行 | `2019-01-01` 一天写了 **3,569** 行（一次性基线），其中 True **11** 只 |
| 按年新增 ST 生效（`to_true`） | 2019 **170**、2020 102、2021 73、2022 55、2023 62、2024 92、2025 119、2026（至 10-29）**313** |
| 与 K 线标的对账 | K 线 5,813 只中 **5,811 只有 ST 记录**；缺 2 只：`001381.SZ`（首根 2026-11-03）、`920085.BJ`（首根 2026-11-06，均晚于该表生成日 2026-10-29） |
| as-of 合并到全部 K 线格 | 9,780,842 格中 `st_flag` 为 **True 276,079 格（2.82%）**、False 8,749,000 格、**null 755,763 格（7.73%）** |
| null 的构成 | **2018 年全部 755,758 格**（该年无 ST 表）+ 上表 2 只新股的 5 格 |
| 逐年 ST=True 格数 | 2019 20,553 / 2020 42,391 / 2021 45,152 / 2022 36,264 / 2023 29,179 / 2024 29,047 / 2025 37,400 / 2026 36,093 |
| 与当前简称对账 | `instruments` 现名含 `ST` 的 **295 只**（163 只 `*ST` + 132 只 `ST`）；而 `st_history` 最后一条记录为 True 的只有 **20 只** |

### 2.3 能否满足 as-of（G2）

**满足，且是结构性满足而不是巧合**：表只写「状态变化日」，不写区间起止，因此不存在「用未来才知道的区间终点去回填历史」的问题；`attach_st_history` 用 `join_asof(..., strategy="backward")`，T 日取值只可能是 `flag_date <= T` 的最后一条。

实测样例（`000004.SZ`，逐笔可复算，见 §2.7）：

```
flag_date   st_flag
2019-01-01   False      <- 基线
2022-05-06   True
2023-06-28   False
2025-04-30   True
2026-06-23   False
```

as-of 回放：2018-12-31 → `null`；2022-05-05 → `False`；2022-05-06 → `True`；2023-06-27 → `True`；2023-06-28 → `False`。（与「生效日当天即生效」一致：当日收盘后可知，符合 G2。）

**顺带确认**：库内已有实现明确拒绝「用当前名称过滤历史」——`security_status.py:21` 的 `MISSING_ST_HISTORY` 文案即「不能用当前名称过滤历史」。这与契约 §2.5 禁止事项 3 同向。

### 2.4 能否满足三态（G3）

**满足**。`st_history` 的 null 只有两种来源，都是「口径不可判定」，不会被静默折成 False：

| 场景 | 输出 | 具体例子 | 实测规模 |
| --- | --- | --- | --- |
| 该标的该日**早于其第一条 ST 记录** | `null` | 任一标的 2018 年内任一天（表从 2019-01-01 起） | **755,758 格** |
| 该标的**整只不在 ST 表内** | `null` | `001381.SZ`（2026-11-03 起）、`920085.BJ`（2026-11-06 起） | **5 格** |

`attach_matrix_st_history`（`security_status.py:85`）：`flags = np.full(shape, np.nan)`，`known = indices >= 0`，未命中保持 `nan`——矩阵路径同样保留三态。

注意：**三态的实现是对的，但 null 的语义边界需要写进契约**——「2019 年前=null」意味着任何回测区间若跨 2018，`universe_unknown_count` 会顶格（755,758），A4「逐日为 0 或可逐条归因」在这段无法满足「为 0」，只能「归因」。

### 2.5 硬缺陷：数据末端 14 个交易日的 ST 被整体截断（**必须先处理**）

实测每日 `ST=True` 只数（as-of 合并到当日有 bar 的标的）：

```
2026-10-16   194
2026-10-19   192      <- 最后一个非零日
2026-10-20     0      <- 断崖
2026-10-21     0
...
2026-11-06     0      <- 数据末端
```

- 2026-10-20 当天有 **198 行** `st_flag=False` 的写入，把 192 只的 ST 区间一次性全部关闭；此后至数据末端 **14 个交易日 ST=True 恒为 0**。
- 这与 `instruments` 的当前简称直接矛盾：现名含 `ST` 的 295 只里，**195 只**的最后一条记录日期正是 **2026-10-20**（`st_flag=False`）。
- 另有两次批量写入：**2026-09-05（周六，非交易日）193 行 False**、**2026-09-07 202 行（200 只为 True）**——即 193 只被写了「False 两天又 True」的回跳；2026-09-07 当天 ST=True 只数通关 198 只。二者与「ST 状态在 9 月批量新增 200 只、10 月 20 日批量摘帽」这一现实解释不吻合（A 股 ST 摘帽是逐家公告，且发生在年报/半年报后）。
- **成因未知**：本仓库内没有源库 `stock-limit-up-analyzer` 的原始区间表，无法判定这是源端批量重灌、区间被截断，还是本项目写入时按快照日闭合。**不做猜测。**

**后果（对 E3 是可量化的）**：若 E3 直接用 `st_flag` 且 `st_flag_missing_policy="unknown"`，则 2026-10-20 起这 14 个交易日里，约 **192 只 ST 标的会被判为「非 ST 在池」**，占契约 A1 日均池 1,429 只的 **约 13%**。若 A1 的对账窗口确为 1,779 日且止于数据末端（起点 2019-07-08），这 14 天必然 `diff != 0`。

### 2.6 结论（ST）

**可得（可真实现）**。理由：这是一张真正的「生效日 + 布尔」历史区间表（7,758 行 / 5,817 只 / 1,436 个生效日，无重复无空值），`join_asof(backward)` 即天然满足 G2，2019 年前整段为 `null` 使 G3 成立；**它不需要、也不应该退回「按简称判定」**。

三条必须随结论一起交付的前置条件：

1. **末端截断**（2026-10-20..2026-11-06，14 个交易日，ST=True 恒 0）必须修复，或该区间在 E3 输出 `null`（不得输出 `0.0`）。修复动作属数据侧/系统开发，不属本次取证。
2. **2018 年（755,758 格）只能为 `null`**，任何「2018 年 ST=False」的写法都是把未知折成 False，违反 G3。
3. **2026-09-05 / 2026-09-07 的 193 只回跳行**需与源端确认；若确认为脏数据，应递增 `universe_version` 并重算缓存（契约 G7）。

### 2.7 可复算命令（ST）

```bash
# C1 表结构与基本计数
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import duckdb
con = duckdb.connect()
print(con.execute("""SELECT count(*) rows, count(DISTINCT symbol) syms, count(DISTINCT flag_date) fdates,
  min(flag_date), max(flag_date), sum(CASE WHEN st_flag THEN 1 ELSE 0 END) n_true
  FROM read_parquet('D:/TSP/data/st_history/part.parquet')""").fetchall())
PY
# 实测输出: [(7758, 5817, 1436, 2019-01-01, 2026-10-29, 986)]
```

```bash
# C2 as-of 合并到全部 K 线格 → 三态与逐年分布
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import polars as pl
D=r"D:\TSP\data"
k = pl.read_parquet(D+r"\kline_daily\date=*\*.parquet", hive_partitioning=True, extra_columns="ignore",
                    columns=["symbol","date"]).with_columns(pl.col("date").cast(pl.Date))
st = pl.read_parquet(D+r"\st_history\part.parquet").with_columns(pl.col("flag_date").cast(pl.Date)).sort(["symbol","flag_date"])
j = k.sort("date").join_asof(st, left_on="date", right_on="flag_date", by="symbol",
                             strategy="backward", check_sortedness=False)
print(j.height, j["st_flag"].is_null().sum())
print(j.with_columns(pl.col("date").dt.year().alias("y")).group_by("y").agg(
    pl.len(), pl.col("st_flag").is_null().sum().alias("null"), (pl.col("st_flag")==True).sum().alias("true")).sort("y"))
PY
# 实测输出: 9780842 755763
# 2018: 755758 格 / null 755758 / true 0 ; 2019..2025: null=0 ; 2026: null=5
```

```bash
# C3 末端断崖（证据最强的一条）
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import duckdb
con = duckdb.connect()
con.execute("CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet', hive_partitioning=true, union_by_name=true)")
con.execute("CREATE VIEW st AS SELECT symbol, CAST(flag_date AS DATE) fd, st_flag FROM read_parquet('D:/TSP/data/st_history/part.parquet')")
q = """WITH dd AS (SELECT DISTINCT d FROM k WHERE d >= DATE '2026-10-15')
SELECT dd.d, count(*) bars, count(*) FILTER (WHERE s.st_flag) st_true FROM dd JOIN k ON k.d=dd.d
JOIN LATERAL (SELECT st_flag FROM st WHERE st.symbol=k.symbol AND st.fd<=dd.d ORDER BY fd DESC LIMIT 1) s ON TRUE
GROUP BY 1 ORDER BY 1"""
print(con.execute(q).fetchall())
PY
# 实测输出: 2026-10-19 → 192 ; 2026-10-20..2026-11-06 → 全部 0
```

---

## 3. 上市天数 —— 结论：**可得（可真实现）**

### 3.1 字段是否存在、在哪、列名/单位、覆盖区间

| 项 | 实测 |
| --- | --- |
| 位置 | `D:\TSP\data\instruments\instruments.parquet` |
| 列 | `listing_date`（**字符串** `'YYYY-MM-DD'`，不是 date 类型；比较前必须解析，库内已有 `app/price_limits.py#parse_listing_date:105` 做这件事） |
| 单位 | 自然日期的上市首日 |
| 取值域 | 1990-12-01 .. 2026-11-03 |
| 快照性 | `as_of` **单值 2026-11-05**（单期快照）。上市日是不变量，用单期快照不构成前视；但「快照里存在该行」本身是未来信息，必须靠 `listing_date > T` 把它挡掉 |

### 3.2 覆盖率（实测数字）

| 指标 | 数字 |
| --- | --- |
| 全表非空率 | **5,533 / 5,536 = 99.95%**；空值 3 只：`600849.SH`、`002525.SZ`、`300060.SZ`（三者都在「无任何 K 线」的 78 只内） |
| **`60/00` 域（E3 默认池）** | **3,385 只，`listing_date` 100% 非空（0 缺失）** |
| 北交所 | K 线有 **355 只 `92*.BJ`**，`instruments` 内 `.BJ` 行数 **0** → 355 只**没有任何上市日** |
| 2018-01-08 后上市（`60/00`） | 635 只，其中 **634 只 K 线首根 = 上市日**（逐位相等）；1 只晚：`603056.SH`（上市 2018-01-16，首根 2019-10-29，晚 651 天） |
| 2018-01-08 后上市（全板块） | 1,996 只，**1,994 只 K 线首根 = 上市日**；2 只晚（`603056.SH`、`300742.SZ`，两者首根都是 2019-10-29） |
| 2018-01-08 前上市（`60/00`） | 2,750 只，**2,422 只首根 = 2018-01-08**；**328 只首根晚于数据起点** —— 这一段「首根≠上市日」，**bar 序号不能当上市天数** |
| `day_rank` 精度 | 2018 年后新上市标的里 **1,994 / 1,996 = 99.9%** 满足「首根＝上市日」，即 `day_rank` 与「上市第 N 个交易日」逐位一致 |

### 3.3 能否满足 as-of（G2）

**满足**。上市日是发行人的不变量，一经确定不随 T 变化；用 `listing_date` 计算 `T - listing_date` 或「上市第 N 个交易日」只用到 `listing_date` 与 `flag_date<=T` 的交易日历，不含 T 之后任何信息。

唯一需要注意的**前视陷阱**：`instruments` 是单期快照，包含 2020 年才上市的行。若实现时以「在 instruments 里」当作「当时在市」，就会前视；必须显式用 `listing_date`（以及 §5 的最后一条 bar）裁剪。

### 3.4 能否满足三态（G3）

**满足，且 null 有明确边界**：

| 场景 | 输出 | 例子 | 规模 |
| --- | --- | --- | --- |
| `listing_date` 为空 | `null` | `600849.SH` / `002525.SZ` / `300060.SZ` | 3 只（均不在 `60/00` 域内的在市标的） |
| 该标的完全不在 `instruments` | `null` | 全部 355 只 `92*.BJ` | 355 只 |
| `listing_date > T`（尚未上市） | 应给 `False`（确定不在池），**不是 null** | 如 2024-01-01 的 2026-11-03 上市标的 | — |

库内已有一处按三态写的先例可参照：`backend/app/custom/limit_board_events/minute_adapter.py:158-160`，`listing is None or listing > day` → `return None`（三态），不是 False。

### 3.5 结论（上市天数）

**可得（可真实现）**。理由：E3 的默认板块 `60/00` 里 `listing_date` **100% 非空、无需推断**，且 99.9% 的新上市标的 K 线首根等于上市日（两条独立路径互相验证）；as-of 只依赖不变量；三态边界清晰（3 只 + 355 只北交所）。

两条限定：
1. **不要用 bar 序号当上市天数**。2,750 只 2018 年前上市的标的中 328 只首根晚于 2018-01-08，这些标的的 `day_rank` 会系统性小于真实上市交易日数；且 2018 年有 2.88% 的日均缺行（§4.2），bar 计数会继续偏低。**唯一正确口径：`listing_date` + G1 交易日轴计数。**
2. 若池定义从 `60/00` 扩到含北交所（`92*`），上市天数**立刻变为不可得**（355 只无维表行）；届时应 `null` 而不是用首根 K 线顶替（首根 2020-07-27 的 29 只北交所标的是精选层首日，不是上市日）。

### 3.6 可复算命令（上市天数）

```bash
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import duckdb
con = duckdb.connect()
con.execute("CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet', hive_partitioning=true, union_by_name=true)")
con.execute("CREATE VIEW ins AS SELECT symbol, CAST(substr(listing_date,1,10) AS DATE) ld FROM read_parquet('D:/TSP/data/instruments/instruments.parquet')")
con.execute("CREATE TABLE ps AS SELECT symbol, min(d) fb FROM k GROUP BY 1")
print("60/00 域:", con.execute("SELECT count(*), count(ld) FROM ps LEFT JOIN ins USING(symbol) WHERE symbol LIKE '60%' OR symbol LIKE '00%'").fetchall())
print("2018 后上市, 首根=上市日:", con.execute("SELECT count(*), count(*) FILTER (WHERE ps.fb=ins.ld) FROM ps JOIN ins USING(symbol) WHERE (symbol LIKE '60%' OR symbol LIKE '00%') AND ins.ld>=DATE '2018-01-08'").fetchall())
print("2018 前上市, 首根=2018-01-08:", con.execute("SELECT count(*), count(*) FILTER (WHERE ps.fb=DATE '2018-01-08') FROM ps JOIN ins USING(symbol) WHERE (symbol LIKE '60%' OR symbol LIKE '00%') AND ins.ld<DATE '2018-01-08'").fetchall())
print("BJ in instruments:", con.execute("SELECT count(*) FROM ins WHERE symbol LIKE '%.BJ'").fetchall())
print("K 线 BJ:", con.execute("SELECT count(*) FROM ps WHERE symbol LIKE '%.BJ'").fetchall())
print("listing_date 空值:", con.execute("SELECT count(*) FROM ins WHERE ld IS NULL").fetchall())
PY
# 实测输出: (3385, 3385) / (635, 634) / (2750, 2422) / 0 / 355 / 3
```

---

## 4. 停牌 —— 结论：**可得（口径＝当日无 bar 行）**

### 4.1 字段是否存在、在哪、列名/单位、覆盖区间

**没有「停牌标志位」这个字段**，但有一个等价、且更原子的事实：**该 (symbol, date) 在当日分区里有没有行**。

| 项 | 实测 |
| --- | --- |
| 位置 | `D:\TSP\data\kline_daily\date=YYYY-MM-DD\*.parquet`（2,141 个日分区） |
| 现有语义实现 | `backend/app/backtest/engine.py:2105`（另一处 `:4685`）`_is_suspended(idx)`：bar 全非有限价 → 停牌；或 `volume<=0` 且 O=H=L=C（一字无量）→ 停牌。回测计数键 `buy_suspended` / `sell_suspended`（`:1561,1648`） |
| 为什么等价 | 实测全库 **`volume==0` 的行数为 0**（`volume` 也无空值），所以「有行无成交」这一支在 K 线路径上根本不会触发；「停牌」在数据上的唯一表现就是**当天没有该标的的行** |

### 4.2 覆盖率（实测数字）

| 指标 | 数字 |
| --- | --- |
| 观测窗口格数（`first_bar..last_bar` 内） | **9,824,345** |
| 窗口内缺行 | **43,503 格（0.44%）** |
| 缺口段数 / 涉及标的 | **4,549 段 / 2,083 只**（占 5,813 只的 35.8%） |
| 缺口长度分布（段数） | 1 日 **2,013**（44.3%）、2 日 204、3 日 170、4–5 日 668、6–10 日 **992**（21.8%）、11–20 日 114、21–60 日 222、61–250 日 **158**、>250 日 **8**；最长 **589 个交易日**（`000670.SZ`，2020-03-20..2022-08-19） |
| 最长 5 段 | `000670.SZ` 589、`000995.SZ` 399、`600610.SH` 316、`002323.SZ` 314、`000792.SZ` 311 |
| **数据洞污染** | 215 个交易日「当日缺行比例 >1%」；**43,503 格中有 22,648 格（52.1%）落在这些日子上** → 这部分是采集洞，不是停牌 |
| 逐年日均缺行率 | **2018 年 2.88%**（最大 5.44%，如 2018-06-19 当天 178/3270 只缺行）；2019 0.32%、2020 0.43%、2021 0.28%、2022 0.24%、2023 0.14%、2024 0.14%、2025 0.23%、2026 0.18% |
| 2018 年缺口归属 | 该年缺行 **22,297 格，其中 21,658 格（97.1%）落在数据洞日期上** |
| 清洗后（2019 起、剔除洞日期） | **20,216 格 / 3,488 段 / 1,749 只**；段长：1 日 1,680、2 日 166、3 日 142、4–5 日 528、6–10 日 796、11–20 日 51、21–60 日 104、61–250 日 21 |

> 说明：清洗口径会**截断**长缺口（被剔除的洞日期把长缺口切段），所以上表「61–250 日 21 段」是**下界**；真实长缺口以未清洗表的 158 段（61–250 日）为准。

### 4.3 能否满足 as-of（G2）

**满足**。「当天有没有这根 bar」是当日收盘即成立的事实，不依赖未来数据；`bar_present` 不需要任何 join、不需要 ST 表、不需要维表，覆盖 100%（每个 K 线格只有 True/False 两种，且有 9,780,842 个 True 与 43,503 个窗口内 False 可核）。

### 4.4 能否满足三态（G3）

**这一项要分清两层**：

| 层 | 三态 | 说明 |
| --- | --- | --- |
| 「当日有无成交」 | **只有两态** | 有行=True、无行=False，都是观测事实，没有第三种可能；不需要 null |
| 「无行」的**归因**（停牌 / 未上市 / 已退市 / 数据洞） | **需要三态，且有的只能给 null** | ① 未上市：`listing_date > T` → False（确定）；② 已退市：见 §5，只能 approx；③ **数据洞**：无法与停牌区分 → 应给 `null`。实测已知的洞：2018 年 21,658 格 + 215 个洞日期上的 22,648 格 |

**给契约的具体建议（只是证据推论，不构成口径决策）**：E3 里 `bar_present=False` 应一律按契约 §2.3 判 `0.0`（当日无成交，确定不在池），**不需要**在 E3 内部区分「停牌」与「数据洞」；但若另建「停牌」因子（例如「连续停牌天数」），**2018 年必须给 null，2019 年起的 1 日缺口也应给 null 而不是 1**，因为 1 日缺口里可能混着采集洞（未清洗口径下 1 日段占 44.3%，清洗后仍占 48%）。

### 4.5 结论（停牌）

**可得（口径＝当日无 bar 行）**。理由：本库 `volume==0` 的行数为 0，使「停牌」与「当日无行」两种口径完全等价，而 `bar_present` 是观测事实、覆盖 100%、天然 as-of；库内已有同义实现（`engine.py#_is_suspended`）可对齐。

三条限定：
1. **不可得的部分**：停牌原因、预计复牌日、连续停牌天数、盘中临时停牌——库里没有任何字段；只有「当日无成交」这一原子事实。
2. **2018 年不可用于停牌统计**：日均缺行 2.88%，缺口 97.1% 落在数据洞日期上。
3. **52.1% 的缺口格落在采集洞上**，任何「停牌天数」口径都必须先剔除洞日期或按日期级阈值标记，否则会把数据缺陷算成停牌。

### 4.6 可复算命令（停牌）

```bash
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import duckdb
con = duckdb.connect(); con.execute("SET threads=4")
con.execute("CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet', hive_partitioning=true, union_by_name=true)")
con.execute("CREATE TABLE cal AS SELECT d, row_number() OVER (ORDER BY d) di FROM (SELECT DISTINCT d FROM k)")
con.execute("CREATE TABLE ps  AS SELECT symbol, min(d) fb, max(d) lb FROM k GROUP BY 1")
con.execute("CREATE TABLE grid AS SELECT p.symbol, c.d, c.di FROM ps p JOIN cal c ON c.d BETWEEN p.fb AND p.lb")
con.execute("CREATE TABLE miss AS SELECT g.* FROM grid g ANTI JOIN (SELECT DISTINCT symbol,d FROM k) x USING(symbol,d)")
print("cells", con.execute("SELECT count(*) FROM grid").fetchone(), "missing", con.execute("SELECT count(*) FROM miss").fetchone())
con.execute("CREATE TABLE cov AS SELECT d, count(*) a FROM grid GROUP BY 1")
con.execute("CREATE TABLE hav AS SELECT d, count(*) b FROM k GROUP BY 1")
con.execute("CREATE TABLE hole AS SELECT cov.d FROM cov LEFT JOIN hav USING(d) WHERE (cov.a-coalesce(hav.b,0))*1.0/cov.a > 0.01")
print("hole dates", con.execute("SELECT count(*) FROM hole").fetchone(),
      "miss on hole", con.execute("SELECT count(*) FROM miss JOIN hole USING(d)").fetchone())
PY
# 实测输出: cells (9824345,) missing (43503,) / hole dates (215,) miss on hole (22648,)
```

```bash
# 缺口段长分布（未清洗，权威口径）
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import polars as pl
D=r"D:\TSP\data"
k = pl.read_parquet(D+r"\kline_daily\date=*\*.parquet", hive_partitioning=True, extra_columns="ignore",
                    columns=["symbol","date"]).with_columns(pl.col("date").cast(pl.Date))
ps = k.group_by("symbol").agg(pl.col("date").min().alias("fb"), pl.col("date").max().alias("lb"))
cal = pl.DataFrame({"date": sorted(k["date"].unique().to_list())}).with_row_index("di")
grid = ps.join(cal, how="cross").filter((pl.col("date")>=pl.col("fb")) & (pl.col("date")<=pl.col("lb"))).select("symbol","date","di")
miss = grid.join(k.unique(), on=["symbol","date"], how="anti").sort(["symbol","date"])
m = miss.join(cal, on="date").with_columns(pl.int_range(pl.len()).over("symbol").alias("c")).with_columns((pl.col("di")-pl.col("c")).alias("g"))
runs = m.group_by(["symbol","g"]).agg(pl.len().alias("len"), pl.col("date").min().alias("s"), pl.col("date").max().alias("e"))
print(runs.height, runs["len"].max())
print(runs.with_columns(pl.when(pl.col("len")==1).then(1).when(pl.col("len")==2).then(2).when(pl.col("len")==3).then(3)
      .when(pl.col("len")<=5).then(5).when(pl.col("len")<=10).then(10).when(pl.col("len")<=20).then(20)
      .when(pl.col("len")<=60).then(60).when(pl.col("len")<=250).then(250).otherwise(9999).alias("bucket"))
      .group_by("bucket").agg(pl.len().alias("runs"), pl.col("len").sum().alias("days")).sort("bucket"))
PY
# 实测输出: 4549 段, 最长 589; 1日 2013 / 2日 204 / 3日 170 / 4-5 668 / 6-10 992 / 11-20 114 / 21-60 222 / 61-250 158 / >250 8
```

---

## 5. 退市 —— 结论：**近似（approx，禁止用于策略判据）**

### 5.1 字段是否存在、在哪、列名/单位、覆盖区间

**不存在。** 逐项确认（都是「找过且没有」，不是「没找」）：

| 检查项 | 结果 |
| --- | --- |
| `instruments` 13 列 | `symbol,name,code,exchange,region,type,listing_date,total_shares,float_shares,tick_size,limit_up,limit_down,as_of` —— **无 `delisting_date` / `delist_date` / `status` / `is_active`**；`limit_up/limit_down` 全列为空 |
| 数据目录 | `D:\TSP\data` 下无任何退市相关目录（`data_sources`、`instruments_ext` 均为空目录）；`pools` 为空目录 |
| 代码 | `grep -rn "delist\|退市" backend/app --include=*.py` 仅 6 处命中，**全部是注释或启发式**：`custom/industry_chain/routes.py:178`（「非空快照里缺失即视为退市」）、`jobs/daily_pipeline.py:392,398`（注释提到「需带退市判定」）、`services/dragon_tiger.py:102,192`（B 股/退市整理期 thscode 为 null）、`tickflow/repository.py:2845`（注释：日K回补保留历史退市标的） |
| 可用的观测事实 | ① 该标的**最后一根 K 线**；② 该标的**是否完全没有任何 K 线** |

### 5.2 覆盖率（实测数字）

| 指标 | 数字 |
| --- | --- |
| 最后一根 bar 早于数据末端（2026-11-06） | **241 只**（`60/00` 域 195 只） |
| 按最后 bar 年份 | 2019 **5**、2020 18、2021 19、2022 **42**、2023 **48**、2024 **49**、2025 30、2026 30 |
| 按「已消失多少个交易日」 | <5 日 1 只、5–19 日 6 只、20–59 日 4 只、60–119 日 12 只、120–249 日 9 只、**≥250 日 209 只** |
| 近 12 个月消失 | 2026-10 6 只、09 4、07 4、06 8、04 4、01 3、2025-12 1…（**这些是「不再有行情」，不等于已退市**） |
| 消失时是否 ST | ≥250 日的 209 只中，最后一条 bar 上 `st_flag=True` 的 **70 只（33.5%）**、False 139 只；<60 日的 11 只中 True 1 只、False 10 只 |
| 维表里有、但一辈子没有 K 线 | **78 只**（`60*` 54、`00*` 21、`30*` 3），上市日区间 1990-12-19..2014-07-08；其中现名含 `ST` 24 只、含「退」15 只 —— 说明 `instruments` **保留了一批退市壳**，「在 instruments 里」≠「在市」 |
| 现名含「退」 | **155 只**；有 K 线 140 只、完全无 K 线 15 只；**仍在数据末端交易 0 只** |

### 5.3 能否满足 as-of（G2）

**不满足**。原因不是「会不会前视」，而是**没有可比对的事实**：既没有退市日，也没有退市公告日，只有「最后一根 bar」。而「最后一根 bar」只有在**事后**才知道它是最后一根——在 T 日无法区分「今天停牌」与「明天退市」。任何把「T 日之后还有没有 bar」写进 T 日判据的实现，都是**前视**。

因此：`退市` 作为**因子**必须标 `approx`，且按 G8 / 契约 §2.5 只能做「事后统计」用途，不得进入策略判据。

### 5.4 能否满足三态（G3）

**不能完整满足，只能给最粗的一态**：

| 场景 | 能给的输出 | 例子 |
| --- | --- | --- |
| 已消失 ≥250 个交易日 | 事后可判「已退市」（近似 True） | 209 只 |
| 消失 <60 个交易日 | **只能给 `null`**（停牌 or 退市，无法区分） | 11 只：`002623.SZ`(4 日)、`000831.SZ`(5)、`002129.SZ`(5)、`688121.SH`(7)、`301139.SZ`(10)、`002731.SZ`(10)、`002717.SZ`(19)、`601059.SH`(33)、`601198.SH`(33)、`688496.SH`(35)、`000016.SZ`(40) |
| 一辈子没有 K 线 | 事后可判「早于 2018-01-08 已退市」 | 78 只 |
| 退市整理期（摘牌前约 30 个交易日） | **`null`**（无字段、无历史简称） | — |

补充一条**反向证据**，说明「现名含退」不能当日判据：155 只现名含「退」的标的里 **140 只还有 K 线、0 只在数据末端仍在交易**——现名反映的是「最后一次抓取时的名称」，用它做历史判据会同时前视和误判（契约 §2.5 禁止事项 3 已禁止）。

### 5.5 结论（退市）

**近似（approx，禁止用于策略判据）**。理由：全库无退市字段、无退市数据源，唯一可用信号是「最后一根 K 线」，而它在 T 日不可知（事后才知道），既不能满足 G2，也不能给全三态；能可靠给出的只有「该标的已连续 ≥250 个交易日无行情」（209 只）这一事后陈述。

对 E3 的实际影响（重要，避免过度阻塞）：**E3 不需要退市字段**。已退市标的当日无 bar → `bar_present=False` → 按契约 §2.3 直接 `0.0`，池判定正确。真正拿不到的是「退市日 / 退市整理期」这类判据（例如「摘牌前 30 日禁止买入」），那类需求应单列缺口，不能靠 K 线尾部反推。

### 5.6 可复算命令（退市）

```bash
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import duckdb
con = duckdb.connect(); con.execute("SET threads=4")
con.execute("CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet', hive_partitioning=true, union_by_name=true)")
con.execute("CREATE VIEW ins AS SELECT symbol, name FROM read_parquet('D:/TSP/data/instruments/instruments.parquet')")
con.execute("CREATE TABLE cal AS SELECT d, row_number() OVER (ORDER BY d) di FROM (SELECT DISTINCT d FROM k)")
con.execute("CREATE TABLE ps AS SELECT symbol, max(d) lb FROM k GROUP BY 1")
print("消失:", con.execute("SELECT count(*) FROM ps WHERE lb < (SELECT max(d) FROM k)").fetchone())
print("按缺口交易日分桶:", con.execute("""SELECT CASE WHEN (SELECT max(di) FROM cal)-ci.di<5 THEN '<5'
 WHEN (SELECT max(di) FROM cal)-ci.di<20 THEN '5-19' WHEN (SELECT max(di) FROM cal)-ci.di<60 THEN '20-59'
 WHEN (SELECT max(di) FROM cal)-ci.di<120 THEN '60-119' WHEN (SELECT max(di) FROM cal)-ci.di<250 THEN '120-249'
 ELSE '>=250' END b, count(*) FROM ps JOIN cal ci ON ci.d=ps.lb WHERE ps.lb < (SELECT max(d) FROM k) GROUP BY 1""").fetchall())
print("维表有/无 K 线:", con.execute("SELECT count(*) FROM ins ANTI JOIN ps USING(symbol)").fetchone())
print("现名含退:", con.execute("SELECT count(*), count(*) FILTER (WHERE ps.symbol IS NOT NULL) FROM ins LEFT JOIN ps USING(symbol) WHERE name LIKE '%退%'").fetchone())
PY
# 实测输出: 241 ; <5:1 / 5-19:6 / 20-59:4 / 60-119:12 / 120-249:9 / >=250:209 ; 78 ; (155, 140)
```

```bash
# 逐条确认「没有退市字段」
grep -rn "delist\|退市" backend/app --include=*.py
```

---

## 6. 对任务书三条线索的复核（哪条对、哪条错、正确位置在哪）

### 6.1 线索一（ST）——**方向对，但结论反了：库里有历史 ST 表，不需要按简称判定**

| 任务书写法 | 复核结果 |
| --- | --- |
| `backend/app/services/abnormal_moves.py:90 附近 is_st_name`，按证券简称判定 | **存在且行号准确**（`:90-91`，`"ST" in name.upper()`）。但它是**异常波动规则的展示标记**，不是池判据；同文件 `:94-103` 明确注释「主板风险警示股票 2026-07-06 起与普通股票同标准…st 仅为展示标记」。**不能拿它当 E3 的 ST 来源。** |
| `app/tickflow/security_status.py#attach_st_history` | **准确**（`:64`；配套 `read_st_history:27`、`normalize_st_history:37`、`attach_matrix_st_history:85`） |
| `FileMarketData.get_st_history()`，`research/.../common.py` 在用 | **准确，但类位置需修正**：`FileMarketData` 定义在 **`backend/app/extensions/adapters.py:382`**（`:96` 是 `get_st_history`）；实际数据源是 `backend/app/data_providers/local_st_history.py` + `D:\TSP\data\st_history`。研究侧确实在用（`common.py:37,87,101`）。 |
| （隐含）「ST 只能靠简称判」 | **错**。`D:\TSP\data\st_history\part.parquet` 是独立的「生效日 + 布尔」区间表，2019-01-01 起、5,817 只、7,758 行。ST 是四个字段里**唯一有真正 as-of 历史表的**。 |

### 6.2 线索二（上市日）——**函数关系搞错了，而且不必从 K 线推断**

| 任务书写法 | 复核结果 |
| --- | --- |
| `backend/app/price_limits.py` 的 `day_rank`（上市首日=1）可从日K序号推断 | **`day_rank` 不是一个函数**，它是 `is_no_limit_day(...)` 的**可选入参**（`price_limits.py:119-137`，签名 `day_rank: int | None = None`），语义是「该 symbol 日K按日期升序的序号」。真正**计算** `day_rank` 的地方是：`backend/app/indicators/pipeline.py:911`（`pl.col("date").rank("ordinal").over("symbol")`）与 `backend/app/custom/limit_board_events/minute_adapter.py:152-164`（按分钟轴 `bisect` 算 rank，且上市日未知时 `return None`）。 |
| （隐含）上市日要从 K 线首根推 | **不必要**：`instruments.listing_date` 在 `60/00` 域 100% 非空（§3.2）。反过来，**从 K 线首根推只对 1,994/1,996 只新上市标的成立，对 2,750 只 2018 年前上市的标的会低估**（328 只首根晚于数据起点）。 |

### 6.3 线索三（停牌/退市）——**大体正确，但要补一条：停牌已有语义实现，退市是真的空白**

| 任务书写法 | 复核结果 |
| --- | --- |
| 停牌无现成标志位，只能从「当天有没有行情行」推断 | **正确**（且进一步确认：`volume==0` 的行数为 0，两种口径等价）。**补充**：库内已有同义实现 `backend/app/backtest/engine.py:2105 / :4685 _is_suspended`，E3 应与它对齐而不是新写一套。 |
| 退市只能从「最后一条行情」推断 | **正确，且比任务书更严重**：不仅没有标志位，`instruments` 里还留着 **78 只完全无 K 线的退市壳**，所以「在 instruments 里」不能当作在市；同时「现名含退」的 155 只里有 140 只仍有 K 线、0 只仍在末端交易，用现名判退市会同时前视和误判。 |

### 6.4 追加纠正（任务书未提，但影响「E3 是真实现还是 approx」的判定）

| # | 事实 | 影响 |
| --- | --- | --- |
| A | 契约 §2.2 的 E3 输入列**只有** `raw_close`/`volume`/`amount`/`st_flag`/`bar_present`/`warmup`；「停牌/退市/上市天数」**不是显式输入列** | 「四类信息是否可得」不能直接换算成「E3 能不能真实现」。按契约原文，E3 只需要 st_flag + bar_present + warmup，**三项都在库内可直接算出** → E3 可判 **真实现（非 approx）**，前置只有 ST 末端修复 |
| B | `kline_daily` **没有 `raw_close`**，`raw_close` 只在 `kline_daily_enriched`（100% 非空；7,406,313 / 9,780,842 行 `close <> raw_close`） | 契约 §2.5 禁止用 `close` 判价格门槛。取值必须走 enriched 或矩阵的 `raw_close` 字段，不要从 `kline_daily.close` 顶替 |
| C | `kline_daily` 有**两套物理布局**（2018 年 85 分片 / 2019 起单文件）+ **9 天 schema 漂移**（`quote_ts`、`volume` int64） | 任何按 `date=*/part.parquet` 的读法会**静默漏掉 2018 年 219 天**；`pl.scan_parquet` 会直接抛 `SchemaError`。矩阵/面板两条路径的 loader 都需要 `union_by_name` / `extra_columns="ignore"` |
| D | `instruments` 是**单期快照**（`as_of` 只有一个值 2026-11-05），且 `type` 全为 `stock`（无 ETF/指数） | E3 的 `asset_types={"stock"}` 约束在当前维表下恒成立、不可测；若将来扩 ETF，需另建维表 |

---

## 7. 对 E3 验收判据的影响（只列受影响项）

| 判据 | 是否受影响 | 依据 |
| --- | --- | --- |
| A1 对账日均 1,429、逐日 `diff==0` | **受影响，且很可能失败**：1,779 个交易日若止于 2026-11-06，则末端 **14 个交易日**落在 ST 截断区，每日约多 192 只 ST 进池（≈日均 1,429 的 13%） | §2.5；§1 交易日轴自校验 |
| A2 池内标的 bar 覆盖率 100% | 不受影响（`bar_present` 覆盖 100%，`volume==0` 行为 0） | §4.2 |
| A4 `universe_unknown_count` 逐日为 0 或可归因 | **部分受影响**：2019-07-08 起的窗口内 null 来源只有 2 只新股（5 格）；若窗口前推至 2018，则 755,758 格 null 只能「归因」不能「为 0」 | §2.4 |
| A6 时间不可逆（无前视） | ST 路径成立（`join_asof(backward)`）；上市天数路径成立（不变量）；**退市路径不成立**（最后一根 bar 事后可知，禁止进判据） | §2.3 / §3.3 / §5.3 |

---

## 8. 未验证 / 未知（明确不猜的部分）

1. `st_history` 的源库 `stock-limit-up-analyzer` 原始区间定义：是否含 `*ST`、**退市整理期是否置 False**、2026-09-05 / 09-07 / 10-20 三次批量写入的成因 —— **本仓库内无证据**。间接观察：≥250 日消失的 209 只里只有 70 只在最后一条 bar 上是 ST，**可能**说明退市整理期不置 ST，但这只是推断，未核实。
2. 2018 年日均 2.88% 缺行的根因（采集缺口 vs 源缺失）—— 未知；只能确认缺口集中在特定日期（215 个洞日期，单日最高 5.44%）。
3. `instruments` 保留的 78 只退市壳是否应清理；`listing_date` 全表 3 个空值（`600849.SH` / `002525.SZ` / `300060.SZ`）中后两只疑似「IPO 未上市」，均未核实。
4. 交易日轴未与交易所官方日历逐日核对；只验证了「无周末、最长间隔 11 天、1,779 日窗口与契约一致、`60/00` 日均 3,098.6 对契约 3,095」。
5. 本次取证未做任何口径决策（用不用 ST、闸值、板块范围），也未触达策略、信号、因子定义与回测引擎。

## 9. git 状态（取证前）

```
?? docs/architecture/
?? docs/factors/
?? docs/research/caliber-decisions-20261107.md
?? docs/research/factor-audit-20261107/
?? research/jiaogedan-review-20261107/
?? research/strategy-search-20261107/FACTOR_MAP_v1.md
?? research/strategy-search-20261107/RULE-CHANGE-20261107.md
?? research/strategy-search-20261107/factor_map_v1.json
?? research/strategy-search-20261107/scripts/factor_map_build.py
?? research/trade-ledger-20261107/
```

本文件是本轮唯一新增；以上未提交改动一律未触碰。

---

## 附录：数字索引（便于抽查）

| 编号 | 位置 | 实测输出摘要 |
| --- | --- | --- |
| C1 | §2.7 | `7758 / 5817 / 1436 / 2019-01-01 / 2026-10-29 / 986` |
| C2 | §2.7 | `9780842 755763`；2018 全 null、2019–2025 null=0、2026 null=5 |
| C3 | §2.7 | 2026-10-19 → 192；2026-10-20 起全 0 |
| C4 | §1 / §6.4B | enriched 2,141 分区 / 9,780,842 行 / `raw_close` 0 空 / 7,406,313 行 `close<>raw_close` |
| C5 | §1 | instruments 5,536 行、`as_of` 唯一值 2026-11-05、`type` 全 stock |
| C6 | §1 | `60`:1793 / `00`:1592 / `30`:1452 / `68`:621 / `92`:355 |
| C7 | §1 | 1,779 日窗口起点 2019-07-08；同区间 `60/00` 日均 3,098.6 |
| C8 | §3.6 | `(3385,3385) / (635,634) / (2750,2422) / 0 / 355 / 3` |
| C9 | §4.6 | `cells 9824345 / missing 43503 / hole 215 / on_hole 22648` |
| C10 | §4.6 | `4549 段 / 最长 589 / 长度分布见 §4.2` |
| C11 | §5.6 | `241 / 分桶 / 78 / (155,140)` |

取证脚本落在仓库外的临时目录 `C:\Users\A\AppData\Local\Temp\e3probe\`（`s1.py`..`s18.py`、`q1.py`..`q14.py`），**未写入仓库**；文中每条结论下方已给出可直接粘贴运行的等价命令。
