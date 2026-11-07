"""`observed_bars` 两种口径的差异量化 (交付文档用证据)。

口径 A (实现采用, = 研究侧 common.py:129): `date.cum_count().over("symbol")` —— 面板内 bar 累计行数。
口径 B (brief 字面): `instruments.listing_date` + 交易日轴计数 —— 上市以来第几个交易日。
契约 v0.7 §2.1 注 1 认定 A 与「以当日为末端的滚动可交易日计数 ≥120」在**前置 ≥120 根 warmup** 时等价,
并禁止用「上市日期 + 自然日 120」替代; §2.6 A1 的靶值是研究侧 1,779 天逐日 diff==0。
本脚本输出: 两口径判定的差异行数、差异按年分布、以及评估窗 (2019-07-01..2026-10-30) 内差异行数。
只读数据。
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "backend")

import duckdb

PANEL = "read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet')"
INSTR = "read_parquet('D:/TSP/data/instruments/instruments.parquet')"
START, END = date(2018, 1, 8), date(2026, 11, 6)
EVAL_START, EVAL_END = date(2019, 7, 1), date(2026, 10, 30)
RESULT: dict = {}
LOGS = Path("research/b2-engine-20261107/logs")

con = duckdb.connect()
con.sql("SET enable_progress_bar=false")
con.sql("SET temp_directory='D:/TSP/duckdb_tmp'")
con.sql("SET max_temp_directory_size='40GB'")

con.sql(
    "create view bars as select symbol, date from " + PANEL
    + " where (symbol like '60%' or symbol like '00%')"
    + " and date between date '" + str(START) + "' and date '" + str(END) + "'"
)
con.sql(
    "create view cal as select date, row_number() over (order by date) as idx "
    "from (select distinct date from bars) order by date"
)
con.sql(
    "create view inst as select symbol, try_cast(listing_date as date) as ld from " + INSTR
)
# 每题: 口径 A = 面板内累计 bar 数; 口径 B = 交易日轴从上市日(含)起算到当日的天数
con.sql(
    """
    create view start_idx as
    select i.symbol, min(c.idx) as idx0
    from inst i join cal c on c.date >= i.ld
    group by i.symbol
    """
)
con.sql(
    """
    create view cmp as
    select b.symbol, b.date, c.idx as idx, s.idx0,
           c.idx - s.idx0 + 1 as b_days,
           row_number() over (partition by b.symbol order by b.date) as a_bars
    from bars b
    join cal c on c.date = b.date
    left join start_idx s on s.symbol = b.symbol
    """
)
RESULT["rows"] = con.sql("select count(*) c from cmp").fetchone()[0]
RESULT["rows_missing_listing"] = con.sql(
    "select count(*) c from cmp where idx0 is null"
).fetchone()[0]
RESULT["rows_diff_ge120"] = con.sql(
    "select count(*) c from cmp where (a_bars >= 120) != (coalesce(b_days,0) >= 120)"
).fetchone()[0]
RESULT["rows_a_ge120_only"] = con.sql(
    "select count(*) c from cmp where (a_bars >= 120) and not (coalesce(b_days,0) >= 120)"
).fetchone()[0]
RESULT["rows_b_ge120_only"] = con.sql(
    "select count(*) c from cmp where not (a_bars >= 120) and coalesce(b_days,0) >= 120"
).fetchone()[0]
RESULT["diff_by_year"] = {
    str(r[0]): int(r[1])
    for r in con.sql(
        "select year(date) y, count(*) c from cmp "
        "where (a_bars >= 120) != (coalesce(b_days,0) >= 120) group by 1 order by 1"
    ).fetchall()
}
RESULT["diff_in_eval_window"] = con.sql(
    "select count(*) c from cmp where date between date '" + str(EVAL_START)
    + "' and date '" + str(EVAL_END) + "'"
    " and (a_bars >= 120) != (coalesce(b_days,0) >= 120)"
).fetchone()[0]
RESULT["rows_b_ge120_only_by_year"] = {
    str(r[0]): int(r[1])
    for r in con.sql(
        "select year(date) y, count(*) c from cmp "
        "where not (a_bars >= 120) and coalesce(b_days,0) >= 120 group by 1 order by 1"
    ).fetchall()
}
RESULT["rows_a_ge120_only_by_year"] = {
    str(r[0]): int(r[1])
    for r in con.sql(
        "select year(date) y, count(*) c from cmp "
        "where (a_bars >= 120) and not (coalesce(b_days,0) >= 120) group by 1 order by 1"
    ).fetchall()
}
RESULT["note"] = (
    "A>=120 而 B<120 = 面板起点截断(2018 上半年)或长期停牌缺口;"
    " B>=120 而 A<120 = 上市后停牌, bar 累计未到 120 但交易日已到"
)
print(json.dumps(RESULT, ensure_ascii=False, indent=1, default=str))
LOGS.mkdir(parents=True, exist_ok=True)
(LOGS / "observed_bars_calibers.json").write_text(
    json.dumps(RESULT, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
)
