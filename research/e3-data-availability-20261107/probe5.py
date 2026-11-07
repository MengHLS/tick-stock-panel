"""E3 `in_universe` 五字段可得性取证（只读，收窄版）。

产出唯一机器证据：docs/factors/evidence/e3_data_availability_20261107.json
不写库、不建表、不改数据、不改代码、不跑回测。

用法:
    backend/.venv/Scripts/python.exe research/e3-data-availability-20261107/probe5.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import duckdb
import polars as pl

PROJECT = Path(__file__).resolve().parents[2]
DATA = Path("D:/TSP/data")
OUT = PROJECT / "docs/factors/evidence/e3_data_availability_20261107.json"

BARS = str(DATA / "kline_daily_enriched" / "date=*" / "*.parquet")
BARS_RAW = str(DATA / "kline_daily" / "date=*" / "*.parquet")
INST = str(DATA / "instruments" / "instruments.parquet")
STH = str(DATA / "st_history" / "part.parquet")

EVAL_START = date(2019, 7, 1)
EVAL_END = date(2026, 10, 30)
PANEL = "(symbol like '60%' or symbol like '00%')"
ST_WINDOW = (date(2026, 10, 20), date(2026, 10, 29))

R: dict[str, dict] = {}


def rec(con: duckdb.DuckDBPyConnection, key: str, sql: str, note: str = "") -> dict:
    t0 = time.time()
    df = con.sql(sql).df()
    payload = {
        "sql": " ".join(sql.split()),
        "note": note,
        "seconds": round(time.time() - t0, 2),
        "rows": int(len(df)),
        "result": json.loads(df.to_json(orient="records", date_format="iso")),
    }
    R[key] = payload
    print(f"\n--- {key} ({payload['seconds']}s, {len(df)} rows) ---")
    print(df.to_string(max_rows=40))
    return payload


def meta(con: duckdb.DuckDBPyConnection) -> None:
    con.sql(f"""
        create or replace view bars as
        select symbol, date, open, high, low, close, raw_close, raw_high, raw_low,
               volume, amount, turnover_rate, consecutive_limit_ups, consecutive_limit_downs
        from read_parquet('{BARS}')
        where {PANEL}
    """)
    con.sql(f"create or replace view axis as select distinct date from read_parquet('{BARS_RAW}') order by date")
    con.sql(f"create or replace view inst as select * from read_parquet('{INST}')")
    con.sql(f"""
        create or replace view sth as
        select symbol, cast(flag_date as date) as flag_date, st_flag from read_parquet('{STH}')
    """)
    rec(con, "M1_axis", f"""
        select count(*) n_trading_days, min(date) first_day, max(date) last_day,
               count(*) filter (where date between '{EVAL_START}' and '{EVAL_END}') n_eval_days
        from axis
    """, "交易日轴 = kline_daily 全部 distinct date，不读 app/services/data_integrity.py 的近似日历")
    rec(con, "M2_panel", f"""
        select count(*) n_rows, count(distinct symbol) n_symbols, min(date) first_bar, max(date) last_bar,
               count(*) filter (where date between '{EVAL_START}' and '{EVAL_END}') n_eval_rows
        from bars
    """, "面板 = 60*/00*（E3 默认板块），源 kline_daily_enriched")
    rec(con, "M3_schema_enriched", f"""
        select column_name, column_type from (describe select * from read_parquet('{BARS}'))
    """, "enriched 实际列集：无 limit_up_price / price_limit_pct 列，涨跌停必须现算")


def f1_suspension(con: duckdb.DuckDBPyConnection) -> None:
    rec(con, "F1_1_zero_volume", f"""
        select case when date between '{EVAL_START}' and '{EVAL_END}' then 'eval' else 'warmup' end win,
               count(*) n_rows,
               count(*) filter (where volume = 0) n_volume_zero,
               count(*) filter (where volume is null) n_volume_null,
               count(*) filter (where amount = 0) n_amount_zero,
               count(*) filter (where raw_close is null) n_raw_close_null
        from bars group by 1 order by 1
    """, "口径A：停牌=volume=0")
    con.sql(f"""
        create or replace view gap as
        with s as (
            select symbol, min(date) f, max(date) l from bars
            where date between '{EVAL_START}' and '{EVAL_END}' group by 1
        )
        select s.symbol, a.date
        from s join axis a on a.date between s.f and s.l
        where a.date between '{EVAL_START}' and '{EVAL_END}'
          and not exists (select 1 from bars b where b.symbol = s.symbol and b.date = a.date)
    """)
    rec(con, "F1_2_gap_total", f"""
        select count(*) n_missing_symbol_days, count(distinct symbol) n_symbols,
               (select count(*) from bars where date between '{EVAL_START}' and '{EVAL_END}') n_rows_eval,
               round(100.0 * count(*) / (
                   (select count(*) from bars where date between '{EVAL_START}' and '{EVAL_END}')
                   + count(*)), 3) pct_of_cells
        from gap
    """, "口径B：停牌=当日无 bar 行（symbol 存续区间内的 axis 日缺行）；分母=有行+缺行")
    rec(con, "F1_3_gap_by_year", f"""
        with yb as (select year(date) y, count(*) n_rows from bars group by 1),
             yg as (select year(date) y, count(*) n_missing, count(distinct symbol) n_symbols from gap group by 1)
        select yg.y, yg.n_missing, yg.n_symbols, yb.n_rows,
               round(100.0*yg.n_missing/yb.n_rows, 3) pct_of_year_rows
        from yg join yb using (y) order by 1
    """, "缺行按年，与同年行数比，用于判断采集洞年份")
    rec(con, "F1_4_gap_runs", f"""
        with idx as (select date, row_number() over (order by date) i from axis
                     where date between '{EVAL_START}' and '{EVAL_END}'),
             gi as (select g.symbol, g.date, idx.i from gap g join idx using (date)),
             r as (select symbol, date, i, i - row_number() over (partition by symbol order by date) grp from gi),
             runs as (select symbol, grp, count(*) len from r group by 1,2)
        select case when len = 1 then '1' when len <= 5 then '2-5' when len <= 20 then '6-20'
                    when len <= 60 then '21-60' when len <= 120 then '61-120'
                    when len <= 250 then '121-250' else '>250' end bucket,
               count(*) n_runs, sum(len) n_symbol_days, max(len) max_len
        from runs group by 1 order by min(len)
    """, "缺口长度分布：>250 段即「长停或退市」的不可分辨区")
    rec(con, "F1_5_hole_dates", f"""
        with d as (select date, count(*) n_bars from bars
                   where date between '{EVAL_START}' and '{EVAL_END}' group by 1),
             g as (select date, count(*) n_gap from gap group by 1),
             ratio as (select d.date, coalesce(g.n_gap,0) n_gap, d.n_bars,
                              1.0 * coalesce(g.n_gap,0) / (d.n_bars + coalesce(g.n_gap,0)) miss_ratio
                       from d left join g using (date)),
             hole as (select date from ratio where miss_ratio > 0.01)
        select (select count(*) from hole) n_hole_dates,
               (select count(*) from ratio where miss_ratio > 0.01) n_hole_days,
               (select count(*) from gap g join hole h on h.date = g.date) n_gap_on_hole,
               round(100.0 * (select count(*) from gap g join hole h on h.date = g.date)
                     / (select count(*) from gap), 1) pct_gap_on_hole,
               (select max(miss_ratio) from ratio) max_daily_miss_ratio
    """, "采集洞判据：当日「缺行 /(有行+缺行) > 1%」；落在洞日上的缺行是采集缺陷，不能当停牌")


def f2_limit(con: duckdb.DuckDBPyConnection) -> None:
    sys.path.insert(0, str(PROJECT / "backend"))
    from app.indicators.pipeline import compute_limit_signals
    from app.price_limits import polars_price_limit_pct
    from app.tickflow.security_status import attach_st_history

    col = ["symbol", "date", "open", "high", "low", "close", "raw_close", "raw_high", "raw_low",
           "volume", "amount"]
    t0 = time.time()
    df = pl.read_parquet(BARS, columns=col).filter(
        (pl.col("symbol").str.starts_with("60") | pl.col("symbol").str.starts_with("00"))
        & (pl.col("date") <= EVAL_END)
        & (pl.col("date") >= EVAL_START)
    ).sort(["symbol", "date"])
    df = attach_st_history(df, pl.read_parquet(STH))
    df = compute_limit_signals(df, pl.read_parquet(INST), needed={"limit_up_price", "limit_down_price"})
    df = df.with_columns(
        polars_price_limit_pct(pl.col("symbol"), pl.col("date"), pl.col("st_flag")).alias("price_limit_pct"),
        (pl.col("raw_close") >= pl.col("limit_up_price")).fill_null(False).alias("up"),
        (pl.col("raw_close") <= pl.col("limit_down_price")).fill_null(False).alias("dn"),
        (pl.col("close") / pl.col("close").shift(1).over("symbol") - 1).alias("ret"),
    ).with_columns(
        (pl.col("raw_high") == pl.col("raw_low")).alias("rawflat"),
    )
    R["F2_load"] = {"note": f"polars 载入+算限价 {round(time.time()-t0,1)}s",
                    "rows": 1, "result": [{"n_rows": int(df.height)}]}

    def one(key: str, name: str, expr, note: str = "") -> None:
        val = df.select(expr).item() if isinstance(expr, pl.Expr) else expr
        R[key] = {"note": note, "rows": 1, "result": [{"id": name, "n": int(val)}]}
        print(f"{name:<46} {int(val):>9}")

    one("F2_1_null_limit_up", "limit_up_price 为 null 的标的日", pl.col("limit_up_price").is_null().sum(),
        "= 每只首根 bar（无昨收）+ 无涨跌幅限制日（新股/复牌）")
    one("F2_2_null_pct", "price_limit_pct 为 null 的标的日", pl.col("price_limit_pct").is_null().sum())
    one("F2_3_up", "判为涨停的标的日", pl.col("up").sum(), "raw_close >= limit_up_price")
    one("F2_4_dn", "判为跌停的标的日", pl.col("dn").sum())
    one("F2_5_up_flat", "涨停且 raw_high==raw_low（一字板，确定不可成交）",
        (pl.col("up") & pl.col("rawflat")).sum())
    one("F2_6_up_notflat", "涨停但日内有价格变动（不可成交性需分钟线）",
        (pl.col("up") & ~pl.col("rawflat")).sum())
    one("F2_7_flat_notlimit", "全日一价但非涨跌停（停牌/冻结形态）",
        (pl.col("rawflat") & ~pl.col("up") & ~pl.col("dn")).sum())
    one("F2_8_beyond_up", "raw_high 超涨停价 0.006 以上（口径异常）",
        (pl.col("raw_high") > pl.col("limit_up_price") + 0.006).fill_null(False).sum())

    pct = (df.group_by(["st_flag", "price_limit_pct", (pl.col("date") >= date(2026, 7, 6)).alias("after_2026_07_06")])
             .agg(pl.len().alias("n_rows")).sort(["st_flag", "price_limit_pct", "after_2026_07_06"]))
    R["F2_9_pct_crosstab"] = {"note": "price_limit_pct × st_flag × 2026-07-06 之后；ST 档位是否真的 5%",
                              "rows": int(pct.height), "result": json.loads(json.dumps(pct.to_dicts(), default=str))}
    print(pct)

    limit_rows = df.filter(pl.col("up") | pl.col("dn"))
    # 除权日会把前复权 open 与原始限价错配，先标出 adj 变化行再排除
    df2 = df.with_columns((pl.col("close") / pl.col("raw_close")).alias("f")).with_columns(
        (pl.col("f") != pl.col("f").shift(1).over("symbol")).fill_null(False).alias("exdiv")
    )
    nxt = (df2.select("symbol", "date", "up", "open", "limit_up_price", "exdiv")
           .with_columns(pl.col("date").shift(-1).over("symbol").alias("nd"),
                         pl.col("open").shift(-1).over("symbol").alias("nopen"),
                         pl.col("limit_up_price").shift(-1).over("symbol").alias("nlup"),
                         pl.col("exdiv").shift(-1).over("symbol").alias("nexdiv"))
           .filter(pl.col("up")))
    clean = nxt.filter(~pl.col("nexdiv").fill_null(False))
    one("F2_13_up_next_open_at_limit_clean", "涨停日次日开盘即涨停（已剔除次日除权行）",
        (clean["nopen"] >= clean["nlup"]).fill_null(False).sum(),
        f"干净行 {clean.height}，剔除除权行 {nxt.height - clean.height}")
    one("F2_10_limit_rows", "涨跌停总标的日", int(limit_rows.height))
    one("F2_12_up_next_open_at_limit", "涨停日次日开盘价即达涨停价（T+1 开盘买不到，含除权日）",
        (nxt["nopen"] >= nxt["nlup"]).fill_null(False).sum(),
        "raw_open 不在 enriched 里，用前复权 open 近似")


def f3_delisting(con: duckdb.DuckDBPyConnection) -> None:
    rec(con, "F3_1_no_delist_column", f"""
        select count(*) filter (where lower(column_name) like '%delist%') n_delist_cols,
               count(*) filter (where lower(column_name) in ('status','is_active','list_status')) n_status_cols,
               string_agg(column_name, ',') filter (where true) all_cols
        from (describe select * from inst)
    """, "instruments 13 列里按名字找退市/状态列")
    rec(con, "F3_2_limit_cols_empty", """
        select count(*) n_rows, count(limit_up) n_limit_up_nonnull, count(limit_down) n_limit_down_nonnull,
               min(as_of) as_of_min, max(as_of) as_of_max
        from inst
    """, "instruments.limit_up/limit_down 是否可用于涨跌停（应为全空 + 单期快照）")
    rec(con, "F3_3_last_bar_year", f"""
        with lb as (select symbol, max(date) last_bar from bars group by 1)
        select year(last_bar) y, count(*) n_symbols
        from lb where last_bar < (select max(date) from bars) group by 1 order by 1
    """, "无退市字段时的唯一代理：最后一根 bar 所在年（事后信息）")
    rec(con, "F3_4_gone_buckets", f"""
        with lb as (select symbol, max(date) last_bar from bars group by 1),
             cal as (select date, row_number() over (order by date) di from axis),
             j as (select lb.symbol, (select max(di) from cal) - c.di missing_days
                   from lb join cal c on c.date = lb.last_bar
                   where lb.last_bar < (select max(date) from bars))
        select case when missing_days < 5 then '<5' when missing_days < 20 then '5-19'
                    when missing_days < 60 then '20-59' when missing_days < 120 then '60-119'
                    when missing_days < 250 then '120-249' else '>=250' end bucket,
               count(*) n_symbols
        from j group by 1 order by min(missing_days)
    """, "「已消失」按缺失交易日数分档；<60 日无法区分停牌与退市")
    rec(con, "F3_5_instruments_no_bar", f"""
        with allbar as (select distinct symbol from read_parquet('{BARS_RAW}'))
        select count(*) n_ins_no_bar, count(*) filter (where symbol like '60%' or symbol like '00%') n_panel
        from inst anti join allbar using (symbol)
    """, "维表里有、K 线里一根都没有（多为退市壳）")
    rec(con, "F3_6_bj_no_instruments", f"""
        with allbar as (select distinct symbol from read_parquet('{BARS_RAW}'))
        select (select count(*) from allbar where symbol like '%.BJ') n_bj_bars,
               (select count(*) from inst where symbol like '%.BJ') n_bj_inst,
               (select count(*) from allbar) n_symbols_all_boards
    """, "北交所有 K 线无维表行 → 上市日/退市日均不可得")
    rec(con, "F3_7_resume_after_gap", f"""
        with idx as (select date, row_number() over (order by date) i from axis
                     where date between '{EVAL_START}' and '{EVAL_END}'),
             gi as (select g.symbol, g.date, idx.i from gap g join idx using (date)),
             r as (select symbol, date, i, i - row_number() over (partition by symbol order by date) grp from gi),
             runs as (select symbol, grp, count(*) len, min(date) s, max(date) e from r group by symbol, grp having count(*) > 250)
        select count(*) n_runs_gt250, count(distinct symbol) n_symbols, max(len) max_len
        from runs
    """, ">250 交易日缺口里后来是否复牌（证伪「无行情=退市」的充分性）")
    rec(con, "F3_8_resume_samples", f"""
        with idx as (select date, row_number() over (order by date) i from axis
                     where date between '{EVAL_START}' and '{EVAL_END}'),
             gi as (select g.symbol, g.date, idx.i from gap g join idx using (date)),
             r as (select symbol, date, i, i - row_number() over (partition by symbol order by date) grp from gi),
             runs as (select symbol, grp, count(*) len, min(date) s, max(date) e from r group by symbol, grp having count(*) > 250)
        select symbol, len, s, e from runs order by len desc limit 10
    """, "最长的几段缺口（这些标的后来都复牌了，因此「长期无行情」不等于退市）")
    rec(con, "F3_9_name_tui_still_trading", f"""
        with lb as (select symbol, max(date) last_bar from read_parquet('{BARS_RAW}') group by 1)
        select count(*) n_name_has_tui,
               count(*) filter (where lb.symbol is not null) n_has_bar,
               count(*) filter (where lb.last_bar >= date '2026-10-30') n_trading_at_tail
        from inst i left join lb using (symbol)
        where i.name like '%退%'
    """, "现名含「退」的证券是否仍在数据末端交易（名字不是历史状态，不能当日判据）")


def f4_listing(con: duckdb.DuckDBPyConnection) -> None:
    rec(con, "F4_1_listing_coverage", """
        select count(*) n_inst, count(listing_date) n_listing_nonnull,
               count(*) filter (where symbol like '60%' or symbol like '00%') n_panel,
               count(listing_date) filter (where symbol like '60%' or symbol like '00%') n_panel_nonnull,
               min(listing_date) ld_min, max(listing_date) ld_max
        from inst
    """, "listing_date 是 VARCHAR；60/00 域非空率")
    rec(con, "F4_1b_listing_panel_with_bars", f"""
        with ps as (select distinct symbol from bars)
        select count(*) n_panel_with_bar, count(i.listing_date) n_listing_nonnull
        from ps left join inst i using (symbol)
    """, "有 K 线的 60/00 标的的 listing_date 非空率（E3 实际用到的那部分）")
    rec(con, "F4_2_first_bar_eq_listing", f"""
        with ps as (select symbol, min(date) fb from bars group by 1)
        select case when cast(substr(i.listing_date,1,10) as date) >= date '2018-01-08'
                    then 'listed_after_panel_start' else 'listed_before_panel_start' end grp,
               count(*) n_symbols, count(*) filter (where ps.fb = cast(substr(i.listing_date,1,10) as date)) n_first_bar_eq_listing
        from ps join inst i using (symbol) where {PANEL} group by 1
    """, "首根 bar 是否等于上市日：决定「bar 序号能否当上市天数」")
    rec(con, "F4_3_ob120_deviation", f"""
        with j as (
            select b.symbol, b.date,
                   count(*) over (partition by b.symbol order by b.date rows between unbounded preceding and current row) ob,
                   cast(substr(i.listing_date,1,10) as date) ld
            from bars b join inst i using (symbol)
        ), e as (select * from j where date between '{EVAL_START}' and '{EVAL_END}')
        select count(*) n_symbol_days,
               count(*) filter (where ob >= 120) n_ob120,
               count(*) filter (where ob < 120 and date_diff('day', ld, date) >= 120) n_naive_calendar_would_include,
               count(*) filter (where ob >= 120 and date_diff('day', ld, date) < 120) n_ob120_but_calendar_lt120,
               count(*) filter (where ld is null) n_listing_null
        from e
    """, "observed_bars（自首根 bar 累计）>=120 与「自然日差>=120」的偏差标的日数；ob 从每只首根 bar 起算")
    rec(con, "F4_5_first_bar_lag", f"""
        with ps as (select symbol, min(date) fb from bars group by 1)
        select count(*) n_listed_after_panel_start,
               count(*) filter (where ps.fb > cast(substr(i.listing_date,1,10) as date)) n_first_bar_later_than_listing,
               max(date_diff('day', cast(substr(i.listing_date,1,10) as date), ps.fb)) max_lag_days
        from ps join inst i using (symbol)
        where {PANEL} and cast(substr(i.listing_date,1,10) as date) >= date '2018-01-08'
    """, "只看数据起点之后上市的标的：首根 bar 是否晚于上市日（2018 年前上市的会被面板起点截断，不计入）")
    rec(con, "F4_4_warmup_effect", f"""
        with ps as (select symbol, min(date) fb from bars group by 1)
        select count(*) filter (where fb > date '2019-07-01') n_listed_inside_eval,
               count(*) filter (where cast(substr(i.listing_date,1,10) as date) > date '2019-07-01') n_listing_inside_eval
        from ps join inst i using (symbol) where {PANEL}
    """, "评估窗内新上市标的数：其 observed_bars 自动 <120，需要 listing_date 才能区分「新股」与「缺数据」")


def f5_st(con: duckdb.DuckDBPyConnection) -> None:
    rec(con, "F5_1_st_shape", """
        select count(*) n_rows, count(distinct symbol) n_symbols,
               min(flag_date) first_flag, max(flag_date) last_flag,
               count(*) filter (where st_flag) n_true, count(*) filter (where not st_flag) n_false
        from sth
    """, "D:/TSP/data/st_history/part.parquet：symbol/flag_date(生效日)/st_flag")
    rec(con, "F5_2_st_episodes_by_year", """
        select year(flag_date) y, count(*) n_flags, count(distinct symbol) n_symbols,
               count(*) filter (where st_flag) n_enter, count(*) filter (where not st_flag) n_exit
        from sth group by 1 order by 1
    """, "每年 ST 进出事件数；2026 年是否异常少")
    rec(con, "F5_3_st_asof_window", f"""
        with d as (select date from axis where date between date '2026-10-12' and date '2026-11-06'),
             latest as (
                select d.date, s.symbol, s.st_flag,
                       row_number() over (partition by d.date, s.symbol order by s.flag_date desc) rn
                from d left join sth s on s.flag_date <= d.date
             ),
             cur as (select date, symbol, st_flag from latest where rn = 1),
             bars_per_day as (select date, count(*) n_active from bars where date between date '2026-10-12' and date '2026-11-06' group by 1)
        select d.date, coalesce(b.n_active,0) n_bars_panel,
               count(*) filter (where cur.st_flag) n_st_true,
               count(*) filter (where cur.st_flag is null) n_st_null,
               count(*) filter (where cur.st_flag is false) n_st_false
        from d
        left join cur on cur.date = d.date
        left join bars_per_day b on b.date = d.date
        group by 1,2 order by 1
    """, "as-of 口径逐日 ST 家数（含 2026-10-20..10-29 八日窗口）")
    rec(con, "F5_4_st_window_8d", f"""
        with d as (select date from axis where date between '{ST_WINDOW[0]}' and '{ST_WINDOW[1]}'),
             cur as (
                select d.date, count(*) filter (where s.st_flag) n_st_true, count(*) n_symbols
                from d left join sth s on s.flag_date = d.date group by 1
             )
        select (select count(*) from d) n_days,
               (select count(*) from sth where flag_date between '{ST_WINDOW[0]}' and '{ST_WINDOW[1]}') n_st_flags_in_window,
               (select count(*) from sth where flag_date <= '{ST_WINDOW[1]}' and st_flag) n_st_true_cum
    """, "窗口内是否有任何 ST 状态变更事件（=0 说明该段无法反映真实 ST 变动）")
    rec(con, "F5_5_st_coverage", f"""
        with ps as (select distinct symbol from bars where {PANEL}),
             sts as (select distinct symbol from sth)
        select (select count(*) from ps) n_panel_symbols,
               (select count(*) from ps join sts using (symbol)) n_panel_symbols_in_st,
               (select count(*) from sts) n_st_symbols,
               (select min(flag_date) from sth) st_first_flag,
               (select max(flag_date) from sth) st_last_flag
    """, "面板标的中有 ST 历史行的比例（无行=从未 ST，非缺失）")
    rec(con, "F5_7_st_window_events", f"""
        select flag_date, st_flag, count(*) n_rows, count(distinct symbol) n_symbols
        from sth where flag_date between date '2026-10-15' and date '2026-10-30'
        group by 1,2 order by 1,2
    """, "2026-10-20 前后 ST 状态变更事件：一次性把大批准 ST 置 False（=末端截断）")
    rec(con, "F5_8_st_dropped_by_truncation", f"""
        with before as (
            select count(*) n from (
                select symbol, arg_max(st_flag, flag_date) f from sth
                where flag_date <= date '2026-10-19' group by 1) where f
        ),
        after as (
            select count(*) n from (
                select symbol, arg_max(st_flag, flag_date) f from sth
                where flag_date <= date '2026-10-29' group by 1) where f
        )
        select (select n from before) n_st_true_on_1019, (select n from after) n_st_true_on_1029,
               (select n from before) - (select n from after) n_dropped
    """, "截断造成的 ST=True 家数下降（可用于估偏差量级）")
    rec(con, "F5_6_st_pre2019", """
        select min(flag_date) first_flag, (select count(*) from sth where flag_date < date '2019-01-01') n_pre_2019
        from sth
    """, "2019 年前的 ST 记录：0 条 → 2019-07-01 之前必须给 null")


def main() -> int:
    con = duckdb.connect()
    con.execute("SET threads=4")
    print("DuckDB", duckdb.__version__, "polars", pl.__version__)
    meta(con)
    f1_suspension(con)
    f2_limit(con)
    f3_delisting(con)
    f4_listing(con)
    f5_st(con)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "script": "research/e3-data-availability-20261107/probe5.py",
        "data_roots": {"bars": BARS, "axis": BARS_RAW, "instruments": INST, "st_history": STH},
        "eval_window": [str(EVAL_START), str(EVAL_END)],
        "panel": PANEL,
        "env": {"python": sys.version.split()[0], "duckdb": duckdb.__version__, "polars": pl.__version__},
        "sections": R,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nWROTE {OUT} ({OUT.stat().st_size} B, {len(R)} sections)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
