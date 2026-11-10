"""E4 `month_end` / `week_end` 判据自跑 (契约 v0.7 §4.7; 派工书 B4, 2026-11-08 返工)。

**编号纪律**: 交付侧一律 `B1`…`B12` (**不带 `E4-` 前缀**); 契约侧一律 `E4-A1`…`E4-A6`,
只作对照列。两套号**互不重名**: 交付 `B*` / 契约 `E4-A*`。
上一轮判 FAIL 的根因是两套判据同号不同义 (交付自编 A1–A8 vs 契约 A1–A6); 本文件既不再出现
交付侧的 `A` 号, 也不再把契约侧写成 `B` 号 —— 上一版表头第一列误把契约侧写成 B 系（B1…B6）, 同号不同义
的坑原样留在表头里, 本版改为 `E4-A1`…`E4-A6`。
JSON 内 `checks` 的键与本表左列 (交付号) 一一对应, 无前缀后缀。

对照表 (契约号 ↔ 交付号):

| 契约判据 (v0.10 §5.6 :602-607) | 交付号 | 含义 |
|---|---|---|
| `E4-A1` | `B1`  | 日历来源与日期轴逐日一致 |
| `E4-A2` | `B2`  | 计数 88/376, 106/451, 末端 1 天 null |
| `E4-A3` | `B9`  | **分段一致**: 切 4 段分别算, 带尾并集 == 整段; 无尾反证 |
| `E4-A4` | `B10` | **节假日月**: 2024-02 春节五条事实 |
| `E4-A5` | `B11` | **与现网差异可解释**: 首日口径 vs 末日常口径, 交集为空, 逐月列出 |
| `E4-A6` | `B12` | **`week_rule` 入参**: `iso_year_week` / `dt_week` 显式二选一 |
| —       | `B3`  | 逐月样本 + 两条独立实现互证 |
| —       | `B4`  | ISO 周跨年探针 (2019-12-31 属 2020-W01) |
| —       | `B5`  | 日级一致性 (全帧物化) |
| —       | `B6`  | 帧起点 2018-01-08 与「只前置 120 根」退化 |
| —       | `B7`  | 静态禁用面 (不出现 data_integrity/_trading_calendar) |
| —       | `B8`  | 生产入口 + DSL 可引用 + 非掩码 |

只读: 不写库、不注册因子、不跑收益回测。

**证据冻结** (B4-D5): 本文件只写 `logs/run_<ts>.json`, 每条跑一个独立文件, **不再回写**
固定的 `logs/e4_verify.json` —— 那份证据在交付时冻结一次, 复跑不得覆盖它。
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, "backend")

import duckdb
import polars as pl

from app.config import settings
from app.custom.research_calendar_pack.calendar_axis import (
    CALENDAR_FACTOR_COLUMNS,
    DEFAULT_WEEK_RULE,
    FACTOR_COLUMN_MONTH_END,
    FACTOR_COLUMN_WEEK_END,
    FRAME_START,
    WEEK_RULE_DT,
    WEEK_RULE_ISO,
    WEEK_RULES,
    calendar_flags,
    load_trading_calendar,
)
from app.custom.research_universe_pack.universe import (
    FACTOR_COLUMN_IN_UNIVERSE,
    compute_in_universe,
)
from app.extensions.factors import FactorProviderContext, materialize_factor_columns
from app.factors.dsl import compile_formula

PANEL = "read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet')"
PANEL_END = date(2026, 11, 6)
EVAL_START, EVAL_END = date(2019, 7, 1), date(2026, 10, 30)
RESULT: dict[str, object] = {"checks": {}}


def check(name: str, ok: bool, **observed) -> None:
    RESULT["checks"][name] = {"verdict": "PASS" if ok else "FAIL", **observed}


def _sha(frame: pl.DataFrame, cols: list[str]) -> str:
    h = hashlib.sha256()
    for name in cols:
        s = frame[name]
        h.update(name.encode())
        h.update(str(s.dtype).encode())
        h.update(b"".join(b"\xff" if v is None else repr(v).encode() for v in s.to_list()))
    return h.hexdigest()


def load(start: date, end: date = PANEL_END) -> pl.DataFrame:
    con = duckdb.connect()
    con.sql("SET enable_progress_bar=false")
    con.sql("SET temp_directory='D:/TSP/duckdb_tmp'")
    con.sql("SET max_temp_directory_size='40GB'")
    con.sql(
        f"""create view bars as
  select symbol, date, volume, amount, raw_close, close from {PANEL}
  where (symbol like '60%' or symbol like '00%')
    and date between date '{start.isoformat()}' and date '{end.isoformat()}'"""
    )
    frame = con.sql("select * from bars order by symbol, date").pl()
    con.close()
    return frame


# ---------------------------------------------------------------- B1
print("[1] B1 日历来源一致性 (分区名 vs distinct date) ...", flush=True)
days = load_trading_calendar(settings.data_dir)
con = duckdb.connect()
con.sql("SET enable_progress_bar=false")
con.sql("SET temp_directory='D:/TSP/duckdb_tmp'")
con.sql("SET max_temp_directory_size='40GB'")
distinct = tuple(
    con.sql(
        f"""select distinct date from {PANEL}
        where (symbol like '60%' or symbol like '00%')
          and date between date '2018-01-08' and date '2026-11-06'
        order by date"""
    ).pl()["date"].to_list()
)
con.close()
check(
    "B1",
    tuple(days) == distinct,
    n_partition_dates=len(days),
    n_distinct_trade_date=len(distinct),
    only_in_partitions=sorted({d.isoformat() for d in days} - {d.isoformat() for d in distinct})[:5],
    only_in_distinct=sorted({d.isoformat() for d in distinct} - {d.isoformat() for d in days})[:5],
    first=days[0].isoformat(),
    last=days[-1].isoformat(),
)

# ---------------------------------------------------------------- B2
print("[2] B2 计数 ...", flush=True)
flags = calendar_flags(days)
in_window = [d for d in days if EVAL_START <= d <= EVAL_END]
month_window = [d for d in in_window if flags[d][0] == 1.0]
week_window = [d for d in in_window if flags[d][1] == 1.0]
month_all = sum(1 for m, _ in flags.values() if m == 1.0)
week_all = sum(1 for _, w in flags.values() if w == 1.0)
tail_null = [d.isoformat() for d, (m, _) in flags.items() if m is None]
check(
    "B2",
    len(month_window) == 88 and len(week_window) == 376 and month_all == 106
    and week_all == 451 and tail_null == ["2026-11-06"],
    window=[EVAL_START.isoformat(), EVAL_END.isoformat()],
    window_days=len(in_window),
    month_end_in_window=len(month_window),
    week_end_in_window=len(week_window),
    month_end_full_frame=month_all,
    week_end_full_frame=week_all,
    tail_null=tail_null,
)

# -------------------------------------------- [3] B3 逐月样本 + 两条实现互证
print("[3] B3 逐月样本 ...", flush=True)
# 独立复算 (第二条实现路径): 用 polars group_by 自己求「每月/每 ISO 周最后一个交易日」,
# 与 calendar_flags 的 python 循环逐日比对 —— 两条实现不一致就报错, 不是拿同一套算法自证。
cal = pl.DataFrame({"date": days}).with_columns(
    pl.col("date").dt.year().alias("y"),
    pl.col("date").dt.month().alias("m"),
    pl.col("date").dt.iso_year().alias("iy"),
    pl.col("date").dt.week().alias("iw"),
)
expect_month = set(
    cal.group_by(["y", "m"]).agg(pl.col("date").max()).get_column("date").to_list()
)
expect_week = set(
    cal.group_by(["iy", "iw"]).agg(pl.col("date").max()).get_column("date").to_list()
)
# 末端两条都要剔掉: 数据末端那天的月/周是否结束不可判 -> 两条实现都不该把它算成末值
expect_month.discard(PANEL_END)
expect_week.discard(PANEL_END)
got_month = {d for d, (m, _) in flags.items() if m == 1.0}
got_week = {d for d, (_, w) in flags.items() if w == 1.0}

samples = {}
for year, month in ((2018, 1), (2023, 6), (2026, 9)):
    rows = [
        {"date": d.isoformat(), "month_end": flags[d][0], "week_end": flags[d][1]}
        for d in days
        if d.year == year and d.month == month
    ]
    samples[f"{year}-{month:02d}"] = {
        "n_days": len(rows),
        "days_flagging_month_end": [r["date"] for r in rows if r["month_end"] == 1.0],
        "days_flagging_week_end": [r["date"] for r in rows if r["week_end"] == 1.0],
        "daily": rows,
    }
check(
    "B3",
    expect_month == got_month
    and expect_week == got_week
    and all(len(v["days_flagging_month_end"]) == 1 for v in samples.values()),
    samples=samples,
    tail_2026_11_06={"month_end": flags[PANEL_END][0], "week_end": flags[PANEL_END][1]},
    cross_check_month_diff=sorted(d.isoformat() for d in (expect_month ^ got_month)),
    cross_check_week_diff=sorted(d.isoformat() for d in (expect_week ^ got_week))[:10],
    cross_check_n_expect_month=len(expect_month),
    cross_check_n_got_month=len(got_month),
)

# ================================================ [9] B9 契约 E4-A3 分段一致
print("[9] B9 (契约 E4-A3) 分段一致: 带尾并集 == 整段; 无尾反证 ...", flush=True)


def _wk(dt):
    iso = dt.isocalendar()
    return (iso[0], iso[1])


def _seg_flags(seq, *, naivetail=False):
    """对一段子轴独立算 flags: 段内只看自己的「下一根」。"""
    out = {}
    for i, day in enumerate(seq):
        if i + 1 == len(seq):
            out[day] = (1.0, 1.0) if naivetail else (None, None)
            continue
        nxt = seq[i + 1]
        out[day] = (
            1.0 if (nxt.year, nxt.month) != (day.year, day.month) else 0.0,
            1.0 if _wk(nxt) != _wk(day) else 0.0,
        )
    return out


_win = [d for d in days if EVAL_START <= d <= EVAL_END]
_n = len(_win)
# 半开区间切分: 4 段恰好铺满窗口, 不重不漏
_cuts = [0, _n // 4, _n // 2, 3 * _n // 4, _n]
_whole_m = {d for d in _win if flags[d][0] == 1.0}
_whole_w = {d for d in _win if flags[d][1] == 1.0}

# --- 第一段: 带尾并集. 每段右端**多吃一根轴上的 bar**(仅供判定段末最后一日), 并集须与整段逐日相等
_seg_tail = []
for k in range(4):
    left = days.index(_win[_cuts[k]])
    last_in_seg = days.index(_win[_cuts[k + 1] - 1])
    right = min(last_in_seg + 1, len(days) - 1)
    _seg_tail.append(list(days[left:right + 1]))
_tail_m, _tail_w = set(), set()
for seg in _seg_tail:
    for day, (mf, wf) in _seg_flags(seg).items():
        if mf == 1.0:
            _tail_m.add(day)
        if wf == 1.0:
            _tail_w.add(day)

# --- 第二段: 无尾反证. 同样 4 段但不带尾, 段末无下一根 → 被错判成月末/周末
_seg_naive = [_win[_cuts[k]:_cuts[k + 1]] for k in range(4)]
_naive_m, _naive_w = set(), set()
for seg in _seg_naive:
    for day, (mf, wf) in _seg_flags(seg, naivetail=True).items():
        if mf == 1.0:
            _naive_m.add(day)
        if wf == 1.0:
            _naive_w.add(day)

_cut_rows = []
for k in range(1, 4):
    day = _win[_cuts[k]]
    prev = _win[_cuts[k] - 1]
    _cut_rows.append({
        "date": day.isoformat(),
        "month_end": flags[day][0],
        "week_end": flags[day][1],
        "in_middle_of_month": flags[day][0] == 0.0,
        "prev_bar": prev.isoformat(),
        "prev_bar_month_end": flags[prev][0],
        "prev_bar_week_end": flags[prev][1],
    })

_naive_extra_m = sorted(d.isoformat() for d in _naive_m - _whole_m)
_naive_extra_w = sorted(d.isoformat() for d in _naive_w - _whole_w)
_naive_missing_m = sorted(d.isoformat() for d in _whole_m - _naive_m)
_naive_missing_w = sorted(d.isoformat() for d in _whole_w - _naive_w)
#: 无尾反证多出的日子必须恰是三个月中切点的**前一根** (派工书第 3 条点名)
_EXPECT_NAIVE_EXTRA = ["2021-04-26", "2023-02-27", "2024-12-25"]
_cut_month_end_days = [r["date"] for r in _cut_rows if r["month_end"] == 1.0]

check(
    "B9",
    _tail_m == _whole_m and _tail_w == _whole_w
    and len(_whole_m) == 88 and len(_whole_w) == 376
    and len(_naive_m) == 91 and len(_naive_w) == 379
    and _naive_extra_m == _EXPECT_NAIVE_EXTRA and _naive_extra_w == _EXPECT_NAIVE_EXTRA
    and _naive_missing_m == [] and _naive_missing_w == []
    # 切点纪律: 月中切点的 month_end 必须是 0.0; 但 **2023-02-28 本身是月末**,
    # 不能把「切点日非调仓日」当通用规则套 (派工书第 3 条).
    and all(r["month_end"] == 0.0 for r in _cut_rows if r["in_middle_of_month"])
    and _cut_month_end_days == ["2023-02-28"],
    contract_ref="契约 E4-A3",
    eval_window=[EVAL_START.isoformat(), EVAL_END.isoformat()],
    n_bars=_n,
    cut_indices=_cuts,
    cut_rows=_cut_rows,
    cut_dates=[r["date"] for r in _cut_rows],
    cut_dates_that_are_month_end=_cut_month_end_days,
    tail_union={"month_end": len(_tail_m), "week_end": len(_tail_w)},
    whole={"month_end": len(_whole_m), "week_end": len(_whole_w)},
    tail_equals_whole={"month_end": _tail_m == _whole_m, "week_end": _tail_w == _whole_w},
    tail_missing={"month_end": sorted(d.isoformat() for d in _whole_m - _tail_m),
                  "week_end": sorted(d.isoformat() for d in _whole_w - _tail_w)},
    naive_union={"month_end": len(_naive_m), "week_end": len(_naive_w)},
    naive_extra={"month_end": _naive_extra_m, "week_end": _naive_extra_w},
    naive_missing={"month_end": _naive_missing_m, "week_end": _naive_missing_w},
    note=("带尾 = 每段右端多吃一根轴 bar, 并集与整段逐日相等 (88/376); 无尾 naive = 91/379, "
          "多出的恰是三个月中切点的前一根 2021-04-26 / 2023-02-27 / 2024-12-25"),
)


# =============================================== [10] B10 ≡ 契约 E4-A4 节假日月
print("[10] B10 (契约 E4-A4) 春节月 2024-02 ...", flush=True)
_feb = [d for d in days if d.year == 2024 and d.month == 2]
_feb_m = [d.isoformat() for d in _feb if flags[d][0] == 1.0]
_feb_w = [d.isoformat() for d in _feb if flags[d][1] == 1.0]
_probe = {}
for _s in ("2024-02-29", "2024-02-23", "2024-02-09", "2024-02-08", "2024-02-05"):
    _d = date.fromisoformat(_s)
    _on = _d in days
    _fl = flags.get(_d, (None, None))
    #: `is_rebalance` = 「该日是否为月末调仓日」的语义名（仓库里没有这个标识符，
    #: 这里按派工书用词显式给出，值恒等于 month_end 标志，不是另一套口径）。
    _probe[_s] = {
        "on_axis": _on,
        "month_end": _fl[0],
        "week_end": _fl[1],
        "is_rebalance": None if _fl[0] is None else (_fl[0] == 1.0),
    }
check(
    "B10",
    len(_feb) == 15
    and _feb_m == ["2024-02-29"]
    and _probe["2024-02-29"]["on_axis"] is True
    and _probe["2024-02-29"]["month_end"] == 1.0
    and _probe["2024-02-09"]["on_axis"] is False
    and _probe["2024-02-08"]["on_axis"] is True
    and _probe["2024-02-08"]["week_end"] == 1.0
    and _probe["2024-02-05"]["week_end"] == 0.0
    and _probe["2024-02-23"]["month_end"] == 0.0
    and _probe["2024-02-23"]["is_rebalance"] is False  # 派工书点名：必须显式断言 False
    and _probe["2024-02-29"]["is_rebalance"] is True
    and _probe["2024-02-23"]["week_end"] == 1.0,
    contract_ref="契约 E4-A4",
    n_trading_days_in_month=len(_feb),
    axis_2024_02=[d.isoformat() for d in _feb],
    month_end_in_month=_feb_m,
    week_end_in_month=_feb_w,
    probes=_probe,
    facts_checked=[
        "2024-02 轴上 15 个交易日",
        "02-29 在轴上且就是 month_end",
        "02-09(除夕) 不在轴",
        "节前最后交易日 02-08 是 week_end",
        "02-05 那周的 week_end = 02-08",
        "02-23 is_rebalance == False (卡「用节前最后一日当年月末」的错法)",
        "02-29 is_rebalance == True (与 month_end 同值, 同一口径的两个名字)",
    ],
)

# ---------------------------------------------------------------- B4
print("[4] B4 ISO 周跨年 ...", flush=True)
iso_key = lambda d: (d.isocalendar()[0], d.isocalendar()[1])  # noqa: E731
probe = {
    "2018-12-28": {"month_end": flags[date(2018, 12, 28)][0],
                   "week_end": flags[date(2018, 12, 28)][1],
                   "iso": list(iso_key(date(2018, 12, 28)))},
    "2019-01-02": {"month_end": flags[date(2019, 1, 2)][0],
                   "week_end": flags[date(2019, 1, 2)][1],
                   "iso": list(iso_key(date(2019, 1, 2)))},
    "2019-01-04": {"month_end": flags[date(2019, 1, 4)][0],
                   "week_end": flags[date(2019, 1, 4)][1],
                   "iso": list(iso_key(date(2019, 1, 4)))},
    # 真正的跨年样本: 2019-12-31 (周二) 已属 ISO 2020-W01, 不是 2019 的最后一个周末
    "2019-12-31": {"month_end": flags[date(2019, 12, 31)][0],
                   "week_end": flags[date(2019, 12, 31)][1],
                   "iso": list(iso_key(date(2019, 12, 31)))},
    "2020-01-03": {"month_end": flags[date(2020, 1, 3)][0],
                   "week_end": flags[date(2020, 1, 3)][1],
                   "iso": list(iso_key(date(2020, 1, 3)))},
}
# 反证: 把周键写成「自然年 + ISO 周号」(= 丢掉 iso 年) 会怎么错
# 这是最常见的错法: d.isocalendar().week 一位 + 自然年做分组键。
naive_last: dict[tuple[int, int], date] = {}
for d in days:
    naive_last[(d.year, d.isocalendar()[1])] = d        # days 已升序, 留下的是每组最后一天
naive_week_ends = set(naive_last.values())
iso_week_ends = {d for d in days if flags[d][1] == 1.0}
check(
    "B4",
    probe["2018-12-28"]["iso"] == [2018, 52] and probe["2018-12-28"]["week_end"] == 1.0
    and probe["2018-12-28"]["month_end"] == 1.0
    and probe["2019-01-02"]["iso"] == [2019, 1] and probe["2019-01-02"]["week_end"] == 0.0
    and probe["2019-01-04"]["iso"] == [2019, 1] and probe["2019-01-04"]["week_end"] == 1.0
    and probe["2019-12-31"]["iso"] == [2020, 1] and probe["2019-12-31"]["week_end"] == 0.0
    and probe["2020-01-03"]["iso"] == [2020, 1] and probe["2020-01-03"]["week_end"] == 1.0
    and bool(naive_week_ends ^ iso_week_ends),
    probe=probe,
    naive_week_end_count=len(naive_week_ends),
    iso_week_end_count=len(iso_week_ends),
    naive_minus_iso=sorted(d.isoformat() for d in naive_week_ends - iso_week_ends)[:12],
    iso_minus_naive=sorted(d.isoformat() for d in iso_week_ends - naive_week_ends)[:12],
    n_naive_minus_iso=len(naive_week_ends - iso_week_ends),
    n_iso_minus_naive=len(iso_week_ends - naive_week_ends),
)

# ---------------------------------------------------------------- B5
print("[5] B5 日级一致性 (全帧物化) ...", flush=True)
t0 = time.perf_counter()
frame = load(FRAME_START)
con = FactorProviderContext(data_dir=settings.data_dir)
prod = materialize_factor_columns(frame, frozenset(CALENDAR_FACTOR_COLUMNS), context=con)
lat = time.perf_counter() - t0
per_day = (
    prod.group_by("date")
    .agg(
        pl.col(FACTOR_COLUMN_MONTH_END).n_unique().alias("nm"),
        pl.col(FACTOR_COLUMN_WEEK_END).n_unique().alias("nw"),
    )
)
values = set()
for name in CALENDAR_FACTOR_COLUMNS:
    values |= set(v for v in prod[name].to_list() if v is not None)
null_days = (
    prod.filter(pl.col(FACTOR_COLUMN_MONTH_END).is_null())["date"].unique().sort().to_list()
)
per_day_month = (
    prod.filter(pl.col(FACTOR_COLUMN_MONTH_END) == 1.0)["date"].unique().sort().to_list()
)
check(
    "B5",
    prod.height == frame.height
    and int(per_day["nm"].max()) == 1 and int(per_day["nw"].max()) == 1
    and values <= {1.0, 0.0}
    and [d.isoformat() for d in null_days] == ["2026-11-06"]
    and len(per_day_month) == 106,
    rows=prod.height,
    frame_rows=frame.height,
    max_nunique_month=int(per_day["nm"].max()),
    max_nunique_week=int(per_day["nw"].max()),
    value_domain=sorted(values),
    null_dates=[d.isoformat() for d in null_days],
    days_flagging_month_end=len(per_day_month),
    frame_first_date=frame["date"].min().isoformat(),
    frame_last_date=frame["date"].max().isoformat(),
    month_end_sha=_sha(prod, [FACTOR_COLUMN_MONTH_END]),
    week_end_sha=_sha(prod, [FACTOR_COLUMN_WEEK_END]),
)

# 墙钟时间只打到 stdout, 不进证据文件: 否则两次跑 sha 不同, 证据不可复算
print(f"    B5 全帧物化耗时 {lat:.1f}s (不进 JSON)", flush=True)

# ---------------------------------------------------------------- B6
print("[6] B6 帧起点 2018-01-08 与「只前置 120 根」退化 ...", flush=True)
assert frame["date"].min() == FRAME_START
# 评测日必须落在 st_history 覆盖期内 (末端 2026-10-30 起全 null, 那是 E3 的已知行为)
eval_day = date(2026, 9, 30)
idx = days.index(eval_day)
warm_start = days[max(0, idx - 119)]        # 只前置 120 根交易日
truncated = load(warm_start)
from app.tickflow.security_status import read_st_history  # noqa: E402

history = read_st_history(settings.data_dir)


def pool_on(data: pl.DataFrame) -> dict[str, object]:
    computed = compute_in_universe(data, st_history=history)
    observed = computed.with_columns(
        pl.col("date").cum_count().over("symbol").alias("ob")
    )
    day_rows = observed.filter(pl.col("date") == eval_day)
    return {
        "rows_on_day": day_rows.height,
        "pool_on_day": int((day_rows[FACTOR_COLUMN_IN_UNIVERSE] == 1.0).sum()),
        "unknown_on_day": int(day_rows[FACTOR_COLUMN_IN_UNIVERSE].null_count()),
        "max_observed_bars": int(day_rows["ob"].max()),
        "symbols_meeting_120_bars": int((day_rows["ob"] >= 120).sum()),
    }


full_pool = pool_on(frame)
warm_pool = pool_on(truncated)
pct = (
    (warm_pool["pool_on_day"] - full_pool["pool_on_day"]) / full_pool["pool_on_day"] * 100
    if full_pool["pool_on_day"]
    else None
)
check(
    "B6",
    frame["date"].min() == FRAME_START
    and days[0] == FRAME_START
    and warm_pool["pool_on_day"] < full_pool["pool_on_day"],
    frame_start=frame["date"].min().isoformat(),
    calendar_start=days[0].isoformat(),
    warmup_start_used=warm_start.isoformat(),
    warmup_bars=120,
    eval_day=eval_day.isoformat(),
    full_frame=full_pool,
    warmup_only=warm_pool,
    pool_pct_change=round(pct, 3) if pct is not None else None,
)

# ---------------------------------------------------------------- B7
print("[7] B7 静态: 不用近一年+周一到周五回退 ...", flush=True)
pack_dir = Path("backend/app/custom/research_calendar_pack")
# 扫 AST 而不是扫文本: 文档字符串里「禁止使用 data_integrity._trading_calendar()」是说明,
# 只有真的 import 或真的调用才算违规。
FORBIDDEN_MODULES = ("data_integrity",)
FORBIDDEN_ATTRS = ("_trading_calendar",)
hits: list[dict[str, str]] = []
calls: list[str] = []
for path in sorted(pack_dir.glob("*.py")):
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)   # 语法自检: 静态扫描的文本就是会被导入的文本
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(mod in alias.name for mod in FORBIDDEN_MODULES):
                    hits.append({"file": path.name, "token": f"import {alias.name}"})
        elif isinstance(node, ast.ImportFrom):
            if node.module and any(mod in node.module for mod in FORBIDDEN_MODULES):
                hits.append({"file": path.name, "token": f"from {node.module}"})
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRS:
                hits.append({"file": path.name, "token": node.attr})
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_ATTRS:
                hits.append({"file": path.name, "token": node.id})
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name:
                calls.append(name)
check(
    "B7",
    not hits,
    forbidden_hits=hits,
    scanned=[p.name for p in sorted(pack_dir.glob("*.py"))],
    weekday_literals=[c for c in set(calls) if c in {"weekday", "isoweekday", "date_range"}],
    note="日历只来自 data_dir 的 date=* 分区; 不在代码里重算周末/节假日",
)

# ---------------------------------------------------------------- B8
print("[8] B8 生产入口 + DSL 可引用 ...", flush=True)
month_only = materialize_factor_columns(frame, frozenset({FACTOR_COLUMN_MONTH_END}), context=con)
compiled = compile_formula("month_end == 1")
ok_compile = compiled.ok
eval_ok = None
if ok_compile:
    out = compiled.frame_transform(month_only)
    out = month_only if out is None else out
    lhs = out.select(
        [
            pl.col("month_end").eq(1).alias("expr"),
            pl.col("month_end").eq(1.0).alias("manual"),
        ]
    )
    eval_ok = lhs["expr"].fill_null(True).equals(lhs["manual"].fill_null(True))
mask_reject = compile_formula("xs_mean(close, month_end)")
check(
    "B8",
    FACTOR_COLUMN_MONTH_END in month_only.columns
    and month_only.height == frame.height
    and ok_compile and bool(eval_ok)
    and [e.code for e in mask_reject.errors] == ["E017"],
    compile_ok=ok_compile,
    compile_errors=[(e.code, e.message) for e in compiled.errors],
    referenced=sorted(compiled.referenced_factors) if ok_compile else None,
    dependencies=sorted(compiled.dependencies) if ok_compile else None,
    expression_equals_manual=eval_ok,
    mask_reject_codes=[e.code for e in mask_reject.errors],
    note="month_end 不是掩码: 它只标日历, 不定义池; 用 xs_mean(close, month_end) 会被 E017 拒",
)

# ============================================= [11] B11 契约 E4-A5 与现网差异
print("[11] B11 (契约 E4-A5) 与现网首日口径差异 ...", flush=True)
# 现网口径: backend/app/backtest/factor.py `_calc_period_return` —— 每月**首个交易日**
# (monthly) / ISO 周**首个交易日** (weekly)。E4 是**末日**口径。
_net_m: dict[tuple[int, int], date] = {}
_net_w: dict[tuple[int, int], date] = {}
for _d in days:                      # days 已升序, setdefault 留下每组第一天
    _net_m.setdefault((_d.year, _d.month), _d)
    _net_w.setdefault(_wk(_d), _d)
_net_month = set(_net_m.values())
_net_week = set(_net_w.values())
_ev_net_m = {d for d in _net_month if EVAL_START <= d <= EVAL_END}
_ev_net_w = {d for d in _net_week if EVAL_START <= d <= EVAL_END}

# 交集在**月层面为空** (首日 != 末日), 在**周层面不空**: 该周只有一个交易日时
# 首日 == 末日。契约 v0.15 :606 写「两集合交集为空」在周层面按字面不成立 ——
# 实测恰有 5 个单交易日 ISO 周, 这不是缺陷, 是「一周只有一根 bar」的必然。
_inter_m = _whole_m & _ev_net_m
_inter_w = _whole_w & _ev_net_w
_win_week_bars: dict[tuple[int, int], int] = {}
for _d in _win:
    _win_week_bars[_wk(_d)] = _win_week_bars.get(_wk(_d), 0) + 1
_single_day_weeks = {d for d in _win if _win_week_bars[_wk(d)] == 1}

# 逐月列出差异: 每月 (契约 month_end, 现网首日)
_by_month = {}
for _d in _win:
    _key = f"{_d.year}-{_d.month:02d}"
    _slot = _by_month.setdefault(_key, {"contract_month_end": None, "live_first_day": None})
    if flags[_d][0] == 1.0:
        _slot["contract_month_end"] = _d.isoformat()
    if _d in _net_month:
        _slot["live_first_day"] = _d.isoformat()
_n_month_keys = len(_by_month)
_n_both = sum(1 for v in _by_month.values() if v["contract_month_end"] and v["live_first_day"])
# 现网 weekly 是「每周首日」, 契约是「每周末日」: 逐 ISO 周比较
_by_week = {}
for _d in _win:
    _k = _wk(_d)
    _slot = _by_week.setdefault(str(_k), {"contract_week_end": None, "live_first_day": None})
    if flags[_d][1] == 1.0:
        _slot["contract_week_end"] = _d.isoformat()
    if _d in _net_week:
        _slot["live_first_day"] = _d.isoformat()
_week_slot_both = sum(1 for v in _by_week.values() if v["contract_week_end"] and v["live_first_day"])

check(
    "B11",
    # 月层面: 交集为空、个数相等 (88/88)、逐月两口径都有值
    _inter_m == set()
    and len(_whole_m) == 88 and len(_ev_net_m) == 88
    and _n_month_keys == 88 and _n_both == 88
    # 周层面: 交集 == 恰「该周在窗内只有一根 bar」的集合 (实测 5 个), 且这些日都是 week_end
    and len(_whole_w) == 376 and len(_ev_net_w) == 376
    and _inter_w == _single_day_weeks and len(_inter_w) == 5
    and _inter_w <= _whole_w
    # 逐周两口径都有值, 且现网首日 != 契约周末日 (单日周除外)
    and len(_by_week) == 376 and _week_slot_both == 376
    and all(
        v["contract_week_end"] == v["live_first_day"] or v["contract_week_end"] is not None
        for v in _by_week.values()
    ),
    contract_ref="契约 E4-A5",
    live_source="backend/app/backtest/factor.py::_calc_period_return (monthly/weekly=每组首个交易日)",
    contract_month_end_count=len(_whole_m),
    live_first_day_count=len(_ev_net_m),
    intersection_month=len(_inter_m),
    contract_week_end_count=len(_whole_w),
    live_first_week_day_count=len(_ev_net_w),
    intersection_week=len(_inter_w),
    intersection_week_dates=sorted(d.isoformat() for d in _inter_w),
    single_day_week_dates=sorted(d.isoformat() for d in _single_day_weeks),
    contract_a5_intersection_empty_holds_month_only=True,
    explain=(
        "契约取每月/每周**最后**一个交易日, 现网 factor.py 取**第一**个。月层面: 每月 >=14 根 bar,"
        " 首日与末日必然不同 → 交集空, 个数相等 (88/88)。周层面: 交集**不空**, 恰是窗内只有"
        " 一根 bar 的 5 个 ISO 周 (该周首日即末日) —— 契约 v0.15 :606 「两集合交集为空」在周层面"
        " 按字面不成立, 按「单日周」修正后才成立。"
    ),
    per_month=_by_month,
    per_week_sample={k: _by_week[k] for k in list(_by_week)[:8]},
    n_months=_n_month_keys,
)


# ============================================ [12] B12 契约 E4-A6 week_rule 入参
print("[12] B12 (契约 E4-A6) week_rule 显式二选一 ...", flush=True)
# 两套口径必须分开记, 否则会像上一轮那样把两套数字混成一套:
#
#   (I) 实现口径 = `calendar_flags` 的判据: `week_end[d] == 1` iff 下一根 bar 的周键与本根
#       不同; 整轴最后一根 = None (无法判定)。这是**唯一正确**的日历定义 —— 一个「周」是
#       轴上连续的一段同键 bar, 不能跨着别的周合并。
#   (II) 分组末口径 = 按周键 groupby 取组内**最后一日**。派工书给的 452 / 451 / 3+2 全部
#       出自这一套。它与 (I) 不等价: `dt_week` 的 (2019,1) / (2024,1) / (2025,1) 三个键在
#       轴上有**两段不连续**的 run (12 月末 + 次年 1 月初), 分组末只留后一段的末日, 把前一段
#       的末日 (2019-01-04 / 2024-01-05 / 2025-01-03) 从周末集里**抹掉了** —— 这三日按
#       「下一根换键」是货真价实的周末日。故 (II) 是聚合错法, 只作复现用。
#
# 换算恒等式 (实测逐条相等, 见 recon_* 字段):
#   分组末(iso) == 实现(iso) ∪ {2026-11-06}          # 只差末端那根 null
#   分组末(dt)  == (实现(dt) − 3 个 1 月周末) ∪ {2026-11-06}
_iso_flags = calendar_flags(days, week_rule=WEEK_RULE_ISO)
_dt_flags = calendar_flags(days, week_rule=WEEK_RULE_DT)
_iso_we = {d for d, (_, w) in _iso_flags.items() if w == 1.0}
_dt_we = {d for d, (_, w) in _dt_flags.items() if w == 1.0}


def _group_last(_keyfn):
    _last = {}
    for _d in days:
        _last[_keyfn(_d)] = _d
    return set(_last.values())


_iso_gl = _group_last(lambda d: (d.isocalendar()[0], d.isocalendar()[1]))
_dt_gl = _group_last(lambda d: (d.year, d.isocalendar()[1]))
_TAIL = days[-1]
_ISO_JAN_WEEK_ENDS = {date(2019, 1, 4), date(2024, 1, 5), date(2025, 1, 3)}
_DT_DEC_YEAR_ENDS = {date(2019, 12, 31), date(2024, 12, 31)}

_ev_iso = {d for d in _iso_we if EVAL_START <= d <= EVAL_END}
_ev_dt = {d for d in _dt_we if EVAL_START <= d <= EVAL_END}
_ev_iso_gl = {d for d in _iso_gl if EVAL_START <= d <= EVAL_END}
_ev_dt_gl = {d for d in _dt_gl if EVAL_START <= d <= EVAL_END}
try:
    calendar_flags(days, week_rule="week_only")
    _bad_rejected = False
except ValueError:
    _bad_rejected = True
try:
    calendar_flags(days, week_rule=None)   # None 走缺省, 不回退到别的规则
    _none_ok = True
except ValueError:
    _none_ok = False
# month_end 不受 week_rule 影响
_month_same = all(_iso_flags[d][0] == _dt_flags[d][0] for d in days)
# 末端那根在两套口径里都没有 week_end (实现 = null; 分组末把它算进组里但那是末端误判)
_tail_impl = _iso_flags[_TAIL][1]

check(
    "B12",
    # (I) 实现口径: 整轴 451 / 453, 窗内 376 / 378
    len(_iso_we) == 451 and len(_dt_we) == 453
    and len(_ev_iso) == 376 and len(_ev_dt) == 378
    and _iso_we - _dt_we == set()
    and _dt_we - _iso_we == _DT_DEC_YEAR_ENDS
    # (II) 分组末口径 === 派工书那套数字: 整轴 452 / 451, 窗内 376 / 376, 差异 3+2
    and len(_iso_gl) == 452 and len(_dt_gl) == 451
    and len(_ev_iso_gl) == 376 and len(_ev_dt_gl) == 376
    and _ev_iso_gl != _ev_dt_gl                     # 窗内计数相同 -> 只能比集合
    and _iso_gl - _dt_gl == _ISO_JAN_WEEK_ENDS
    and _dt_gl - _iso_gl == _DT_DEC_YEAR_ENDS
    # 换算恒等式: 两套口径必须能互相推出, 差集只允许是「末端一根」与「3 个 1 月周末」
    and _iso_gl == _iso_we | {_TAIL}
    and _dt_gl == (_dt_we - _ISO_JAN_WEEK_ENDS) | {_TAIL}
    # 入参域: 域外 ValueError; None 走缺省; 末端 null
    and _bad_rejected and _none_ok and _tail_impl is None
    # month_end 与 week_rule 无关
    and _month_same,
    contract_ref="契约 E4-A6",
    week_rules=list(WEEK_RULES),
    default_week_rule=DEFAULT_WEEK_RULE,
    # (I) 实现口径
    impl_iso_week_end_full=len(_iso_we),
    impl_dt_week_end_full=len(_dt_we),
    impl_iso_week_end_window=len(_ev_iso),
    impl_dt_week_end_window=len(_ev_dt),
    impl_dt_minus_iso_full=sorted(d.isoformat() for d in _dt_we - _iso_we),
    impl_iso_minus_dt_full=sorted(d.isoformat() for d in _iso_we - _dt_we),
    # (II) 分组末口径 (派工书数字出处)
    grouplast_iso_week_end_full=len(_iso_gl),
    grouplast_dt_week_end_full=len(_dt_gl),
    grouplast_iso_week_end_window=len(_ev_iso_gl),
    grouplast_dt_week_end_window=len(_ev_dt_gl),
    grouplast_iso_minus_dt_full=sorted(d.isoformat() for d in _iso_gl - _dt_gl),
    grouplast_dt_minus_iso_full=sorted(d.isoformat() for d in _dt_gl - _iso_gl),
    grouplast_window_sets_equal=_ev_iso_gl == _ev_dt_gl,
    # 两套口径的换算
    recon_iso_grouplast_eq_impl_plus_tail=_iso_gl == _iso_we | {_TAIL},
    recon_dt_grouplast_eq_impl_minus_jan_plus_tail=(
        _dt_gl == (_dt_we - _ISO_JAN_WEEK_ENDS) | {_TAIL}
    ),
    tail_bar=_TAIL.isoformat(),
    tail_bar_impl_week_end=_tail_impl,
    bad_rule_rejected=_bad_rejected,
    none_falls_back_to_default=_none_ok,
    month_end_unaffected_by_week_rule=_month_same,
    note=(
        "派工书的 452/451 与 3+2 逐条复现, 出自「按周键取组内最后一日」口径; 实现用的是"
        "「下一根 bar 换周键」口径, 得 451/453 与 0+2。两者不等价的唯一来源: dt_week 的"
        "(2019,1)/(2024,1)/(2025,1) 在轴上有两段不连续 run, 分组末把前一段的末日"
        "2019-01-04/2024-01-05/2025-01-03 抹掉了 —— 那三日按下一根换键是真周末日。"
        "recon_* 两条恒等式把两套口径钉成可互推, 不再靠措辞。"
    ),
)

RESULT["environment"] = {
    "python": sys.version.split()[0],
    "polars": pl.__version__,
    "data_dir": str(settings.data_dir),
    "panel": PANEL,
    "frame_start": FRAME_START.isoformat(),
    "panel_end": PANEL_END.isoformat(),
}
RESULT["summary"] = {
    "PASS": sum(1 for v in RESULT["checks"].values() if v["verdict"] == "PASS"),
    "FAIL": sum(1 for v in RESULT["checks"].values() if v["verdict"] == "FAIL"),
    "total": len(RESULT["checks"]),
}
print(json.dumps(RESULT["summary"], ensure_ascii=False), flush=True)

_ts = time.strftime("%Y%m%dT%H%M%S")
out_path = Path(f"research/b4-calendar-20261107/logs/run_{_ts}.json")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(RESULT, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
print("written", out_path, out_path.stat().st_size, "bytes", flush=True)
sys.exit(0 if RESULT["summary"]["FAIL"] == 0 else 1)
