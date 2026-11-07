"""E4 `month_end` / `week_end` 判据自跑 (契约 v0.7 §4.7; 派工书 B4)。

判据:
  E4-A1 日历来源一致性: `date=*` 分区集合 == `select distinct date` (2,141 天, 逐日相等)
  E4-A2 计数: 评测窗 [2019-07-01, 2026-10-30] 内 month_end = 88 / week_end = 376;
         全帧 (2018-01-08..2026-11-06) = 106 / 451 + 1 天末端 null
  E4-A3 逐月样本: 抽 3 个月给出该月每个交易日的逐日值, 且数据末端 = null (不是 1)
  E4-A4 ISO 周跨年: 2018-12-28 / 2019-01-02 / 2019-01-04 三点 + 与「只用 week 一位」的差异条数
  E4-A5 日级一致性: 同一天所有 symbol 值相同; 值域 ⊆ {1.0, 0.0, None}; null 只在末端
  E4-A6 帧起点: 日历与帧都从 2018-01-08 起; 且「只前置 120 根」会让 in_universe 池子变小
  E4-A7 静态: 包内不出现 `data_integrity` / `_trading_calendar` (禁止近一年+周一到周五回退)
  E4-A8 生产入口: materialize_factor_columns 产出两列; DSL `month_end == 1` 编译+求值一致;
         且 month_end 不是掩码 (xs_mean(close, month_end) 必须被 E017 拒)

只读: 不写库、不注册因子、不跑收益回测。
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
    FACTOR_COLUMN_MONTH_END,
    FACTOR_COLUMN_WEEK_END,
    FRAME_START,
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


# ---------------------------------------------------------------- E4-A1
print("[1] E4-A1 日历来源一致性 (分区名 vs distinct date) ...", flush=True)
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
    "E4-A1",
    tuple(days) == distinct,
    n_partition_dates=len(days),
    n_distinct_trade_date=len(distinct),
    only_in_partitions=sorted({d.isoformat() for d in days} - {d.isoformat() for d in distinct})[:5],
    only_in_distinct=sorted({d.isoformat() for d in distinct} - {d.isoformat() for d in days})[:5],
    first=days[0].isoformat(),
    last=days[-1].isoformat(),
)

# ---------------------------------------------------------------- E4-A2
print("[2] E4-A2 计数 ...", flush=True)
flags = calendar_flags(days)
in_window = [d for d in days if EVAL_START <= d <= EVAL_END]
month_window = [d for d in in_window if flags[d][0] == 1.0]
week_window = [d for d in in_window if flags[d][1] == 1.0]
month_all = sum(1 for m, _ in flags.values() if m == 1.0)
week_all = sum(1 for _, w in flags.values() if w == 1.0)
tail_null = [d.isoformat() for d, (m, _) in flags.items() if m is None]
check(
    "E4-A2",
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

# ---------------------------------------------------------------- E4-A3
print("[3] E4-A3 逐月样本 ...", flush=True)
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
    "E4-A3",
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

# ---------------------------------------------------------------- E4-A4
print("[4] E4-A4 ISO 周跨年 ...", flush=True)
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
    "E4-A4",
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

# ---------------------------------------------------------------- E4-A5
print("[5] E4-A5 日级一致性 (全帧物化) ...", flush=True)
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
    "E4-A5",
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
print(f"    E4-A5 全帧物化耗时 {lat:.1f}s (不进 JSON)", flush=True)

# ---------------------------------------------------------------- E4-A6
print("[6] E4-A6 帧起点 2018-01-08 与「只前置 120 根」退化 ...", flush=True)
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
    "E4-A6",
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

# ---------------------------------------------------------------- E4-A7
print("[7] E4-A7 静态: 不用近一年+周一到周五回退 ...", flush=True)
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
    "E4-A7",
    not hits,
    forbidden_hits=hits,
    scanned=[p.name for p in sorted(pack_dir.glob("*.py"))],
    weekday_literals=[c for c in set(calls) if c in {"weekday", "isoweekday", "date_range"}],
    note="日历只来自 data_dir 的 date=* 分区; 不在代码里重算周末/节假日",
)

# ---------------------------------------------------------------- E4-A8
print("[8] E4-A8 生产入口 + DSL 可引用 ...", flush=True)
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
    "E4-A8",
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

out_path = Path("research/b4-calendar-20261107/logs/e4_verify.json")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(RESULT, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
print("written", out_path, out_path.stat().st_size, "bytes", flush=True)
sys.exit(0 if RESULT["summary"]["FAIL"] == 0 else 1)
