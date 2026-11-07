"""E3 `in_universe` 数据可得性探针（只读）。

只读 DuckDB/parquet 与正式读接口；不写库、不改因子定义、不跑策略收益回测。
每个小节把 SQL 原文与结果一起写入 evidence JSON，供 docs/factors 引用。

用法:
    backend/.venv/Scripts/python.exe research/e3-data-availability-20261107/e3_probe.py --only A,F1
    (不带 --only 跑全部)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import duckdb
import polars as pl

PROJECT = Path(__file__).resolve().parents[2]
DATA = Path("D:/TSP/data")
OUT = Path(__file__).resolve().parent / "e3_raw.json"

BARS = str(DATA / "kline_daily_enriched" / "date=*" / "*.parquet")
BARS_RAW = str(DATA / "kline_daily" / "date=*" / "*.parquet")
INST = str(DATA / "instruments" / "instruments.parquet")
STH = str(DATA / "st_history" / "part.parquet")

EVAL_START = date(2019, 7, 1)
EVAL_END = date(2026, 10, 30)
PANEL = "(symbol like '60%' or symbol like '00%')"

RECORD: dict[str, dict] = {}


def run(con: duckdb.DuckDBPyConnection, key: str, sql: str, note: str = "") -> dict:
    """执行一条 SQL，记录原文与结果。"""
    t0 = time.time()
    df = con.sql(sql).df()
    payload = {
        "kind": "sql",
        "sql": " ".join(sql.split()),
        "note": note,
        "seconds": round(time.time() - t0, 2),
        "rows": int(len(df)),
        "result": json.loads(df.to_json(orient="records", date_format="iso")),
    }
    print(f"\n--- {key} ({payload['seconds']}s, {len(df)} rows) ---")
    print(df.to_string(max_rows=60))
    return payload


def section_A(con: duckdb.DuckDBPyConnection) -> None:
    con.sql(f"""
        create or replace view bars as
        select symbol, date, open, high, low, close, raw_close, raw_high, raw_low,
               volume, amount
        from read_parquet('{BARS}')
        where {PANEL}
    """)
    con.sql(f"""
        create or replace view axis as
        select distinct date from read_parquet('{BARS_RAW}')
        order by date
    """)
    con.sql(f"""
        create or replace view instruments as
        select * from read_parquet('{INST}')
    """)
    con.sql(f"""
        create or replace view sth as
        select symbol, cast(flag_date as date) as flag_date, st_flag
        from read_parquet('{STH}')
    """)
    q = {}
    q["A1_axis"] = run(con, "A1 交易日轴（全市场 K 线 distinct date）", f"""
        select count(*) n_trading_days, min(date) first_day, max(date) last_day,
               count(*) filter (where date between '{EVAL_START}' and '{EVAL_END}') n_eval_days
        from axis
    """)
    q["A2_panel_shape"] = run(con, "A2 面板规模（60*/00*）", f"""
        select count(*) n_rows, count(distinct symbol) n_symbols,
               min(date) first_bar, max(date) last_bar,
               (select count(*) from axis a where a.date between '{EVAL_START}' and '{EVAL_END}') n_eval_days,
               count(*) filter (where date between '{EVAL_START}' and '{EVAL_END}') n_eval_rows
        from bars
    """)
    q["A3_partition_completeness"] = run(con, "A3 分区完整性（每个交易日是否有分区）", f"""
        with p as (
            select distinct date from read_parquet('{BARS_RAW}')
        )
        select (select count(*) from axis) n_axis,
               (select count(*) from p) n_partitions,
               (select count(*) from axis a anti join p on p.date = a.date) n_axis_without_partition
    """)
    q["A4_daily_floor"] = run(con, "A4 每日标的最大/最小覆盖", f"""
        select min(n) min_symbols_per_day, max(n) max_symbols_per_day,
               avg(n)::decimal(10,1) avg_symbols_per_day
        from (select date, count(*) n from bars group by date)
    """)
    RECORD["A_surface"] = q


def section_F1(con: duckdb.DuckDBPyConnection) -> None:
    q = {}
    q["F1_1_zero_volume"] = run(con, "F1-1 volume=0 / 空值行（全区间与评估区间）", f"""
        select
          case when date between '{EVAL_START}' and '{EVAL_END}' then 'eval' else 'warmup' end win,
          count(*) n_rows,
          count(*) filter (where volume is null) n_volume_null,
          count(*) filter (where volume = 0) n_volume_zero,
          count(*) filter (where amount is null) n_amount_null,
          count(*) filter (where amount is not null and amount <= 0) n_amount_nonpos,
          count(*) filter (where volume = 0 and coalesce(amount,0) = 0) n_vol0_amt0,
          count(*) filter (where raw_close is null) n_raw_close_null,
          count(*) filter (where raw_close is not null and raw_close <= 0) n_raw_close_nonpos,
          count(*) filter (where open is null or high is null or low is null) n_ohlc_null
        from bars group by 1 order by 1
    """)
    q["F1_2_zero_volume_by_year"] = run(con, "F1-2 volume=0 按年", """
        select year(date) y, count(*) n_rows,
               count(*) filter (where volume = 0) n_zero,
               round(100.0 * count(*) filter (where volume = 0) / count(*), 4) pct_zero,
               count(distinct symbol) filter (where volume = 0) n_symbols_zero
        from bars group by 1 order by 1
    """)
    q["F1_3_zero_volume_flat"] = run(con, "F1-3 volume=0 行的价格是否全天一价", """
        select count(*) n_zero_volume,
               count(*) filter (where open = high and high = low and low = close) n_flat_ohlc,
               count(*) filter (where amount is not null and amount > 0) n_with_amount
        from bars where volume = 0
    """)
    q["F1_4_zero_volume_dates"] = run(con, "F1-4 volume=0 最集中的 10 个交易日", """
        select date, count(*) n_symbols from bars where volume = 0
        group by 1 order by 2 desc limit 10
    """)
    # 观测期内断档（有 bar 的生命期内缺行）= 停牌候选
    con.sql(f"""
        create or replace view gap as
        with ax as (select distinct date from bars where date between '{EVAL_START}' and '{EVAL_END}'),
        life as (select symbol, min(date) f, max(date) l from bars group by symbol),
        grid as (select life.symbol, ax.date from life join ax on ax.date between life.f and life.l)
        select g.symbol, g.date from grid g
        anti join bars b on b.symbol = g.symbol and b.date = g.date
    """)
    q["F1_5_gap_total"] = run(con, "F1-5 评估区间内断档（有 bar 生命期内缺行）", f"""
        select count(*) n_missing_symbol_days, count(distinct symbol) n_symbols,
          (select count(*) from bars where date between '{EVAL_START}' and '{EVAL_END}') n_rows_eval
        from gap
    """)
    q["F1_6_gap_runs"] = run(con, "F1-6 断档连续长度分布（按交易日序号切岛）", """
        with idx as (select date, row_number() over (order by date) i from axis
                     where date between '2019-07-01' and '2026-10-30'),
        gi as (select g.symbol, g.date, idx.i from gap g join idx using (date)),
        r as (select symbol, date, i,
                     i - row_number() over (partition by symbol order by date) as grp
              from gi),
        runs as (select symbol, grp, count(*) len, min(date) s, max(date) e
                 from r group by 1,2)
        select case when len = 1 then '1'
                    when len <= 5 then '2-5'
                    when len <= 20 then '6-20'
                    when len <= 60 then '21-60'
                    when len <= 120 then '61-120'
                    when len <= 250 then '121-250'
                    else '>250' end bucket,
               count(*) n_runs, sum(len) n_symbol_days, max(len) max_len
        from runs group by 1
        order by min(len)
    """)
    q["F1_6b_top_gaps"] = run(con, "F1-6b 最大 15 段停牌", """
        with idx as (select date, row_number() over (order by date) i from axis
                     where date between '2019-07-01' and '2026-10-30'),
        gi as (select g.symbol, g.date, idx.i from gap g join idx using (date)),
        r as (select symbol, date, i,
                     i - row_number() over (partition by symbol order by date) as grp
              from gi),
        runs as (select symbol, grp, count(*) len, min(date) s, max(date) e
                 from r group by 1,2)
        select symbol, s gap_start, e gap_end, len trading_days_missing
        from runs order by len desc limit 15
    """)
    q["F1_7_gap_by_year"] = run(con, "F1-7 断档按年（判断是真实停牌还是早年数据缺口）", """
        with yb as (select year(date) y, count(*) n_rows from bars group by 1),
        yg as (select year(date) y, count(*) n_missing, count(distinct symbol) n_symbols
               from gap group by 1)
        select yg.y, yg.n_missing, yg.n_symbols, yb.n_rows,
               round(100.0*yg.n_missing/yb.n_rows, 3) pct_of_year_rows
        from yg join yb using (y) order by 1
    """)
    q["F1_8_gap_vs_zero_volume"] = run(con, "F1-8 断档日 vs volume=0 日（口径互斥性）", f"""
        select (select count(*) from gap) n_gap_days,
               (select count(*) from bars where volume = 0 and date between '{EVAL_START}' and '{EVAL_END}') n_zero_volume_rows,
               (select count(*) from gap g join bars b on b.symbol=g.symbol and b.date=g.date) n_overlap
    """)
    q["F1_9_pre_post_life"] = run(con, "F1-9 生命期外（首 bar 前 / 末 bar 后）的标的日", f"""
        with ax as (select distinct date from bars where date between '{EVAL_START}' and '{EVAL_END}'),
        life as (select symbol, min(date) f, max(date) l from bars group by symbol)
        select count(*) filter (where ax.date < life.f) n_before_first_bar,
               count(*) filter (where ax.date > life.l) n_after_last_bar,
               count(*) filter (where ax.date > life.l and life.l < date '2026-09-30') n_after_last_bar_early
        from life cross join ax
    """)
    q["F1_10_gap_full_range"] = run(con, "F1-10 全区间（2018-01-08 起）断档标的日", """
        with ax as (select distinct date from bars),
        life as (select symbol, min(date) f, max(date) l from bars group by symbol),
        grid as (select life.symbol, ax.date from life join ax on ax.date between life.f and life.l)
        select count(*) n_missing_full_range, count(distinct symbol) n_symbols,
               round(100.0*count(*)/(select count(*) from bars), 3) pct_of_all_rows
        from grid g anti join bars b on b.symbol=g.symbol and b.date=g.date
    """)
    RECORD["F1_suspension"] = q


def section_F4(con: duckdb.DuckDBPyConnection) -> None:
    q = {}
    q["F4_1_listing_coverage"] = run(con, "F4-1 instruments.listing_date 覆盖", f"""
        select count(*) n_instruments,
               count(*) filter (where listing_date is null or trim(listing_date) = '') n_null,
               count(*) filter (where listing_date is not null and trim(listing_date) <> ''
                                and try_cast(listing_date as date) is null) n_unparsable,
               min(try_cast(listing_date as date)) min_listing,
               max(try_cast(listing_date as date)) max_listing,
               max(as_of) snapshot_as_of
        from instruments
    """)
    q["F4_2_panel_coverage"] = run(con, "F4-2 面板标的的 listing_date 覆盖", f"""
        with sym as (select distinct symbol from bars),
        i as (select symbol, try_cast(listing_date as date) ld from instruments)
        select count(*) n_panel_symbols,
               count(*) filter (where i.symbol is null) n_not_in_instruments,
               count(*) filter (where i.symbol is not null and i.ld is null) n_listing_null,
               count(*) filter (where i.ld > '{EVAL_END}') n_listing_after_eval_end,
               count(*) filter (where i.ld < '2018-01-08') n_listing_before_panel_start
        from sym left join i using (symbol)
    """)
    q["F4_3_first_bar_lag"] = run(con, "F4-3 首个 bar 相对上市日的滞后（区分面板起点与真实缺口）", f"""
        with f as (select symbol, min(date) first_bar from bars group by symbol),
        i as (select symbol, try_cast(listing_date as date) ld from instruments)
        select count(*) filter (where i.ld is not null and f.first_bar = '2018-01-08' and i.ld < '2018-01-08') n_truncated_by_panel_start,
               count(*) filter (where i.ld is not null and f.first_bar > '2018-01-08'
                                and date_diff('day', i.ld, f.first_bar) > 10) n_late_first_bar,
               count(*) filter (where i.ld is null) n_no_listing_date
        from f left join i using (symbol)
    """)
    q["F4_3b_late_first_bar_split"] = run(con, "F4-3b 首个 bar 晚于上市日的两类拆分", f"""
        with f as (select symbol, min(date) first_bar from bars group by symbol),
        i as (select symbol, try_cast(listing_date as date) ld from instruments)
        select case when i.ld >= '2018-01-08' then 'listed_after_panel_start' else 'listed_before_panel_start' end grp,
               count(*) n_symbols,
               count(*) filter (where date_diff('day', i.ld, f.first_bar) > 10) n_late_first_bar,
               max(date_diff('day', i.ld, f.first_bar)) max_lag_days
        from f join i using (symbol)
        group by 1 order by 1
    """)
    q["F4_4_observed_bars_120"] = run(con, "F4-4 第 120 根 bar 发生日，与「上市日起第 120 个交易日」的偏差", f"""
        with idx as (select date, row_number() over (order by date) i from axis),
        b as (select symbol, date, row_number() over (partition by symbol order by date) ob
              from bars),
        obs as (select symbol, min(date) d_obs120 from b where ob = 120 group by symbol),
        oidx as (select obs.symbol, idx.i obs_idx from obs join idx on idx.date = obs.d_obs120),
        i as (select symbol, try_cast(listing_date as date) ld from instruments),
        lidx as (select i.symbol, min(x.i) li_idx from i join idx x on x.date >= i.ld group by 1)
        select count(*) n_symbols_with_lag,
               round(avg(oidx.obs_idx - lidx.li_idx - 119), 2) mean_lag_trading_days,
               median(oidx.obs_idx - lidx.li_idx - 119) median_lag,
               max(oidx.obs_idx - lidx.li_idx - 119) max_lag,
               count(*) filter (where oidx.obs_idx - lidx.li_idx - 119 > 0) n_lag_positive,
               count(*) filter (where oidx.obs_idx - lidx.li_idx - 119 < 0) n_lag_negative
        from obs join oidx using (symbol) join lidx using (symbol)
    """)
    q["F4_5_universe_disagreement"] = run(con, "F4-5 「第 120 根 bar」与「上市起第 120 交易日」入池判定不同的标的日", f"""
        with idx as (select date, row_number() over (order by date) i from axis),
        b as (select symbol, date, row_number() over (partition by symbol order by date) ob
              from bars),
        i as (select symbol, try_cast(listing_date as date) ld from instruments),
        lidx as (select i.symbol, min(x.i) li_idx from i join idx x on x.date >= i.ld group by 1),
        j as (select b.symbol, b.date, b.ob, idx.i bi, lidx.li_idx
              from b join idx using (date) join lidx using (symbol))
        select count(*) n_symbol_days,
               count(*) filter (where date between '{EVAL_START}' and '{EVAL_END}') n_eval_symbol_days,
               count(*) filter (where date < '{EVAL_START}') n_warmup_symbol_days,
               count(*) filter (where (ob >= 120) <> (bi - li_idx + 1 >= 120)) n_disagree,
               count(*) filter (where (ob >= 120) <> (bi - li_idx + 1 >= 120)
                                and date between '{EVAL_START}' and '{EVAL_END}') n_disagree_eval,
               count(distinct symbol) filter (where (ob >= 120) <> (bi - li_idx + 1 >= 120)) n_disagree_symbols
        from j
    """)
    q["F4_6_ob120_date_max"] = run(con, "F4-6 预上市标的达到 120 根 bar 的最晚日期（面板起点影响上限）", """
        with b as (select symbol, date, row_number() over (partition by symbol order by date) ob
                   from bars),
        i as (select symbol, try_cast(listing_date as date) ld from instruments)
        select max(b.date) latest_120th_bar, min(b.date) earliest_120th_bar
        from b join i using (symbol)
        where b.ob = 120 and i.ld < '2018-01-08'
    """)
    RECORD["F4_listing"] = q


def section_F5(con: duckdb.DuckDBPyConnection) -> None:
    q = {}
    q["F5_1_st_shape"] = run(con, "F5-1 st_history 规模", """
        select count(*) n_rows, count(distinct symbol) n_symbols,
               min(flag_date) min_flag_date, max(flag_date) max_flag_date,
               count(*) filter (where st_flag) n_true, count(*) filter (where not st_flag) n_false,
               count(distinct symbol) filter (where st_flag) n_symbols_ever_st
        from sth
    """)
    q["F5_2_st_by_year"] = run(con, "F5-2 按年覆盖", """
        select year(flag_date) y, count(*) n_rows, count(*) filter (where st_flag) n_st_true,
               count(distinct symbol) n_symbols
        from sth group by 1 order by 1
    """)
    q["F5_3_panel_uncovered"] = run(con, "F5-3 面板标的未进入 st_history 的规模", f"""
        with sym as (select distinct symbol from bars),
        cov as (select distinct symbol from sth)
        select count(*) n_panel_symbols,
               count(*) filter (where cov.symbol is null) n_symbols_no_st_row,
               (select count(*) from bars b join sym s using(symbol)
                left join cov c using(symbol)
                where c.symbol is null and b.date between '{EVAL_START}' and '{EVAL_END}') n_eval_symbol_days_null
        from sym left join cov using (symbol)
    """)
    q["F5_4_asof_null_days"] = run(con, "F5-4 as-of 合并后在评估区间仍为 null 的标的日", f"""
        with b as (select symbol, date from bars where date between '{EVAL_START}' and '{EVAL_END}')
        select count(*) n_rows,
               count(*) filter (where s.st_flag is null) n_null_flag,
               round(100.0*count(*) filter (where s.st_flag is null)/count(*), 4) pct_null
        from b asof left join sth s on b.symbol = s.symbol and b.date >= s.flag_date
    """)
    q["F5_5_asof_by_year"] = run(con, "F5-5 as-of 后按年：null 率与 ST 标的日", f"""
        with b as (select symbol, date from bars)
        select year(b.date) y, count(*) n_rows,
               count(*) filter (where s.st_flag is null) n_null,
               count(*) filter (where s.st_flag) n_st_true,
               round(100.0*count(*) filter (where s.st_flag)/count(*), 3) pct_st
        from b asof left join sth s on b.symbol = s.symbol and b.date >= s.flag_date
        group by 1 order by 1
    """)
    q["F5_6_pit_vs_current"] = run(con, "F5-6 时点性检验：历史 ST 与当前名称的交叉表", f"""
        with last_flag as (
            select b.symbol, b.date, s.st_flag
            from (select symbol, max(date) as date from bars group by symbol) b
            asof left join sth s on b.symbol = s.symbol and b.date >= s.flag_date),
        ever_st as (select distinct symbol from sth where st_flag),
        cur as (select symbol, upper(name) like '%ST%' as name_has_st
                from (select *, row_number() over (partition by symbol order by as_of desc) rn
                      from instruments) where rn = 1)
        select
          count(*) n_symbols,
          count(*) filter (where lf.st_flag and cur.name_has_st) n_st_flag_and_name_st,
          count(*) filter (where lf.st_flag and not cur.name_has_st) n_st_flag_name_clean,
          count(*) filter (where not lf.st_flag and cur.name_has_st) n_name_st_flag_false,
          count(*) filter (where lf.st_flag is null and cur.name_has_st) n_name_st_flag_null,
          count(*) filter (where lf.st_flag is null) n_flag_null,
          count(*) filter (where es.symbol is not null and not lf.st_flag) n_ever_st_but_clean_now
        from last_flag lf join cur using (symbol)
        left join ever_st es using (symbol)
    """)
    q["F5_7_alters"] = run(con, "F5-7 状态序列完整性：冗余行与交替检查", """
        with s as (select symbol, flag_date, st_flag,
                          lag(st_flag) over (partition by symbol order by flag_date) prev
                   from sth)
        select count(*) n_rows, count(*) filter (where prev is not null) n_transitions,
               count(*) filter (where prev is not null and prev = st_flag) n_redundant_same_value,
               count(*) filter (where prev is null and not st_flag) n_first_row_false
        from s
    """)
    q["F5_8_non_trading_flag_dates"] = run(con, "F5-8 flag_date 是否落在非交易日", """
        select count(*) n_flag_rows,
               count(*) filter (where a.date is null) n_on_non_trading_day,
               round(100.0*count(*) filter (where a.date is null)/count(*), 2) pct
        from sth s left join (select distinct date from axis) a on a.date = s.flag_date
    """)
    q["F5_9_st_episodes"] = run(con, "F5-9 ST 区间长度分布（交易日）", """
        with s as (select symbol, flag_date, st_flag,
                          lead(flag_date) over (partition by symbol order by flag_date) nxt
                   from sth)
        select case when nxt is null then 'open-ended (to 2026-10-29)'
                    when date_diff('day', flag_date, nxt) <= 7 then '<=7d'
                    when date_diff('day', flag_date, nxt) <= 60 then '8-60d'
                    when date_diff('day', flag_date, nxt) <= 365 then '61-365d'
                    else '>365d' end bucket,
               count(*) n_episodes
        from s where st_flag group by 1 order by 1
    """)
    RECORD["F5_st"] = q


def section_F2(con: duckdb.DuckDBPyConnection) -> None:
    """复算研究路径 load_panel 的涨跌停判定价（不写库、不回测）。"""
    sys.path.insert(0, str(PROJECT / "backend"))
    from app.indicators.pipeline import compute_limit_signals
    from app.price_limits import polars_price_limit_pct
    from app.tickflow.security_status import attach_st_history

    col = ["symbol", "date", "open", "high", "low", "close", "raw_close",
           "raw_high", "raw_low", "volume", "amount"]
    t0 = time.time()
    df = pl.read_parquet(BARS, columns=col)
    df = df.filter(
        (pl.col("symbol").str.starts_with("60") | pl.col("symbol").str.starts_with("00"))
        & (pl.col("date") <= EVAL_END)
    ).sort(["symbol", "date"])
    inst = pl.read_parquet(INST)
    sth = pl.read_parquet(STH)
    df = attach_st_history(df, sth)
    df = compute_limit_signals(df, inst, needed={"limit_up_price", "limit_down_price"})
    df = df.with_columns(
        polars_price_limit_pct(pl.col("symbol"), pl.col("date"), pl.col("st_flag"))
        .alias("price_limit_pct"),
        (pl.col("raw_close") >= pl.col("limit_up_price")).fill_null(False).alias("up"),
        (pl.col("raw_close") <= pl.col("limit_down_price")).fill_null(False).alias("dn"),
        # 用前复权 close 计算日收益（除权日不会出现机械跳空）；raw_close 口径另记为 adj 变化行
        (pl.col("close") / pl.col("close").shift(1).over("symbol") - 1).alias("ret"),
        ((pl.col("close") / pl.col("raw_close"))
         != (pl.col("close").shift(1).over("symbol") / pl.col("raw_close").shift(1).over("symbol"))
        ).fill_null(False).alias("adj_changed"),
    ).with_columns(
        ((pl.col("open") == pl.col("high")) & (pl.col("high") == pl.col("low"))
         & (pl.col("low") == pl.col("close"))).alias("flat"),
        (pl.col("raw_high") == pl.col("raw_low")).alias("rawflat"),
    )
    load_s = round(time.time() - t0, 1)

    def agg(name: str, expr: pl.Expr | None = None, note: str = "") -> dict:
        sub = df if expr is None else df.filter(expr)
        return {"id": name, "note": note, "n_rows": int(len(sub))}

    def one(name: str, expr: pl.Expr | int, note: str = "") -> dict:
        val = df.select(expr).item() if isinstance(expr, pl.Expr) else expr
        return {"id": name, "note": note, "n_rows": int(val)}

    res = [
        one("F2-0 面板行数（60*/00*，≤2026-10-30）", pl.len(), f"载入耗时 {load_s}s"),
        one("F2-1 limit_up_price 为 null 的行", pl.col("limit_up_price").is_null().sum(),
            "= 每只标的首根 bar（无昨收）+ 交易所无涨跌幅限制日"),
        one("F2-2 limit_down_price 为 null 的行", pl.col("limit_down_price").is_null().sum()),
        one("F2-3 price_limit_pct 为 null 的行", pl.col("price_limit_pct").is_null().sum()),
        one("F2-4 判为涨停的标的日", pl.col("up").sum()),
        one("F2-5 判为跌停的标的日", pl.col("dn").sum()),
        one("F2-6 涨停且 raw_high==raw_low（全日一价，确定不可成交）",
            (pl.col("up") & pl.col("rawflat")).sum()),
        one("F2-7 跌停且 raw_high==raw_low", (pl.col("dn") & pl.col("rawflat")).sum()),
        one("F2-8 涨停但日内有价格变动（需 raw_open/分钟线定可成交性）",
            (pl.col("up") & ~pl.col("rawflat")).sum()),
        one("F2-9 全日一价但既非涨停也非跌停（冻结/停牌形态）",
            (pl.col("rawflat") & ~pl.col("up") & ~pl.col("dn")).sum()),
        one("F2-10 raw_high 高于涨停价 0.006 以上（口径异常）",
            (pl.col("raw_high") > pl.col("limit_up_price") + 0.006).fill_null(False).sum()),
        one("F2-11 raw_low 低于跌停价 0.006 以下（口径异常）",
            (pl.col("raw_low") < pl.col("limit_down_price") - 0.006).fill_null(False).sum()),
        one("F2-12 面板内出现 20%/30% 档的行", (pl.col("price_limit_pct") >= 0.19).sum()),
        one("F2-13 数据集中 raw_open 列数（0=缺）", int("raw_open" in df.columns)),
        one("F2-13b 复权因子变化日（除权除息，限价需特判）", pl.col("adj_changed").sum()),
    ]

    pct_tab = (
        df.group_by(["st_flag", "price_limit_pct", (pl.col("date") >= date(2026, 7, 6)).alias("after_2026_07_06")])
        .agg(pl.len().alias("n_rows"))
        .sort(["st_flag", "price_limit_pct", "after_2026_07_06"])
    )
    pct_rows = json.loads(json.dumps(pct_tab.to_dicts(), default=str))

    # 实测涨跌幅是否被对应档位约束住
    emp = (
        df.filter(pl.col("ret").is_not_null())
        .with_columns(pl.col("ret").abs().alias("abs_ret"))
        .group_by(["st_flag", "price_limit_pct", (pl.col("date") >= date(2026, 7, 6)).alias("after")])
        .agg(
            pl.len().alias("n"),
            pl.col("abs_ret").max().alias("max_abs_ret"),
            (pl.col("abs_ret") > pl.col("price_limit_pct") + 0.005).sum().alias("n_beyond_limit"),
        )
        .sort(["st_flag", "price_limit_pct", "after"])
    )
    emp_rows = json.loads(json.dumps(emp.to_dicts(), default=str))

    # 入场（T+1 开盘）是否被一字板拦住
    nxt = (
        df.select("symbol", "date", "raw_close", "limit_up_price", "rawflat", "up")
        .with_columns(pl.col("date").shift(-1).over("symbol").alias("nd"),
                      pl.col("raw_close").shift(-1).over("symbol").alias("nraw"),
                      pl.col("limit_up_price").shift(-1).over("symbol").alias("nlup"),
                      pl.col("rawflat").shift(-1).over("symbol").alias("nflat"))
        .filter(pl.col("up"))
    )
    next_stats = {
        "id": "F2-14 涨停信号日的次日状态（T+1 开盘买入的可成交性）",
        "n_signal_days": int(len(nxt)),
        "n_next_bar_missing": int(nxt["nd"].is_null().sum()),
        "n_next_bar_one_price": int(nxt["nflat"].sum()),
        "n_next_bar_at_limit": int((nxt["nraw"] >= nxt["nlup"]).fill_null(False).sum()),
        "n_next_bar_missing_or_one_price": int((nxt["nd"].is_null() | nxt["nflat"]).sum()),
    }

    RECORD["F2_limit"] = {
        "metrics": res,
        "price_limit_pct_crosstab": pct_rows,
        "empirical_ret_vs_limit": emp_rows,
        "next_day_entry": next_stats,
    }
    for r in res:
        print(f"{r['id']:<52} {r['n_rows']:>10}")
    print("\nprice_limit_pct 交叉表:")
    print(pct_tab)
    print("\n实测 |ret| 与档位:")
    print(emp)
    print("\n次日入场:", next_stats)


def section_F3(con: duckdb.DuckDBPyConnection) -> None:
    q = {}
    q["F3_1_instruments_schema"] = run(con, "F3-1 instruments 维表字段（找退市日）", f"""
        describe select * from read_parquet('{INST}')
    """)
    # 其它维表是否含退市字段（目录为空则跳过）
    ext = []
    for sub in sorted(DATA.glob("instruments*")):
        files = list(sub.rglob("*.parquet"))
        cols = sorted(pl.read_parquet_schema(files[0]).keys()) if files else []
        ext.append({"id": f"F3-2 {sub.name}", "table": sub.name,
                    "n_files": len(files), "columns": cols})
    RECORD["F3_2_schemas"] = ext
    for row in ext:
        print(f"{row['table']:<20} files={row['n_files']:<3} cols={row['columns']}")
    q["F3_3_symbols_outside_instruments"] = run(con, "F3-3 有 K 线但不在维表的标的（退市候选）", f"""
        with s as (select symbol, min(date) f, max(date) l, count(*) n from bars group by symbol)
        select count(*) n_symbols_total,
               count(*) filter (where i.symbol is null) n_absent_from_instruments,
               count(*) filter (where i.symbol is not null) n_present
        from s left join instruments i using (symbol)
    """)
    q["F3_4_absent_by_last_bar_year"] = run(con, "F3-4 维表外标的按最后一根 bar 年份", f"""
        with s as (select symbol, min(date) f, max(date) l from bars group by symbol)
        select year(s.l) last_bar_year, count(*) n_symbols,
               count(*) filter (where s.l >= '{EVAL_START}') n_last_bar_after_eval_start
        from s left join instruments i using (symbol)
        where i.symbol is null group by 1 order by 1
    """)
    q["F3_5_absent_recent_bars"] = run(con, "F3-5 维表外但仍在交易的标的（证明「不在维表≠已退市」）", f"""
        with s as (select symbol, max(date) l from bars group by symbol)
        select count(*) n_absent_with_bar_after_2026_10,
               count(*) filter (where s.l = (select max(date) from bars)) n_absent_with_bar_on_last_day
        from s left join instruments i using (symbol)
        where i.symbol is null and s.l > '2026-10-01'
    """)
    q["F3_6_present_but_stale"] = run(con, "F3-6 在维表但 K 线已停更的标的", f"""
        with s as (select symbol, max(date) l from bars group by symbol)
        select count(*) n_stale,
               count(*) filter (where s.l < '2025-10-30') n_stale_over_1y,
               min(s.l) earliest_last_bar
        from s join instruments i using (symbol)
        where s.l < '2026-10-30'
    """)
    q["F3_7_delist_proxy"] = run(con, "F3-7 近似退市：最后 bar 早于 2026-10-30 且距今 ≥250 交易日", """
        with idx as (select date, row_number() over (order by date) i from axis),
        last_i as (select i from idx where date = '2026-10-30'),
        s as (select symbol, max(date) l from bars group by symbol),
        j as (select s.symbol, s.l, idx.i li, last_i.i lmax
              from s join idx on idx.date = s.l cross join last_i
              where s.l < date '2026-10-30')
        select count(*) n_symbols_last_bar_before_2026_10_30,
               count(*) filter (where lmax - li >= 250) n_ge_250_trading_days,
               count(*) filter (where lmax - li >= 120) n_ge_120_trading_days
        from j
    """)
    q["F3_8_resumed_after_long_gap"] = run(con, "F3-8 长期断档后又复牌（用断档当退市会误判）", """
        with idx as (select date, row_number() over (order by date) i from axis),
        bb as (select bars.symbol, bars.date, idx.i as ix from bars join idx using (date)),
        r as (select symbol, date, ix, ix - row_number() over (partition by symbol order by date) grp from bb),
        runs as (select symbol, grp, count(*) n_bars, min(ix) s, max(ix) e from r group by 1,2),
        seq as (select symbol, grp, s, e, lag(e) over (partition by symbol order by s) prev_e from runs),
        gaps as (select symbol, prev_e + 1 gap_start, s - 1 gap_end, s - 1 - prev_e len from seq where prev_e is not null)
        select count(*) n_gaps_ge_120,
               count(*) filter (where len >= 250) n_gaps_ge_250
        from gaps where len >= 120
    """)
    q["F3_9_stale_st_cross"] = run(con, "F3-9 已停更标的的 ST 状态（无法区分退市与长期停牌）", """
        with idx as (select date, row_number() over (order by date) i from axis),
        s as (select symbol, max(date) l from bars group by symbol),
        last_i as (select i from idx where date = '2026-10-30'),
        j as (select s.symbol, s.l, last_i.i - idx.i lag_i
              from s join idx on idx.date = s.l cross join last_i),
        lf as (select j.symbol, j.l, j.lag_i, st.st_flag
               from j asof left join sth st on j.symbol = st.symbol and j.l >= st.flag_date)
        select count(*) n_stopped_all,
               count(*) filter (where lag_i >= 250) n_stopped_ge_250,
               count(*) filter (where lag_i >= 250 and st_flag) n_ge_250_st_true,
               count(*) filter (where lag_i >= 250 and not coalesce(st_flag, false)) n_ge_250_not_st
        from lf where lag_i >= 1
    """)
    q["F3_10_stale_samples"] = run(con, "F3-10 停更最久的 10 只标的", """
        select symbol, l last_bar,
               (select count(*) from bars b where b.symbol = s.symbol) n_bars
        from (select symbol, max(date) l from bars group by symbol) s
        order by l limit 10
    """)
    q["F3_11_first_bar_waves"] = run(con, "F3-11 首 bar 日期尖峰（退市/停牌股历史被截断的位置）", """
        with s as (select symbol, min(date) f, max(date) l, count(*) nb from bars group by symbol)
        select s.f first_bar, count(*) n_symbols,
          count(*) filter (where s.l = date '2026-11-06') n_still_active,
          count(*) filter (where s.l < date '2026-10-30') n_stopped,
          count(*) filter (where i.ld < date '2018-01-08') n_listed_before_panel
        from s left join (select symbol, cast(listing_date as date) ld from instruments) i using(symbol)
        where s.f > date '2018-01-09' group by 1 order by 2 desc limit 6
    """)
    q["F3_12_truncated_start_effect"] = run(con, "F3-12 首 bar 被截断导致的「bar 数不足」标的日", """
        with b as (select symbol, date, row_number() over (partition by symbol order by date) ob from bars),
        s as (select symbol, min(date) f from bars group by symbol),
        i as (select symbol, cast(listing_date as date) ld from instruments)
        select count(*) n_symbol_days_ob_lt_120, count(distinct b.symbol) n_symbols
        from b join s using(symbol) join i using(symbol)
        where s.f in (date '2019-10-29', date '2018-12-03') and i.ld < s.f and b.ob < 120
          and b.date between date '2019-07-01' and date '2026-10-30'
    """)
    RECORD["F3_delisting"] = q


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = {s.strip().upper() for s in args.only.split(",") if s.strip()}

    con = duckdb.connect()
    con.sql("set threads to 8")
    sections = {"A": section_A, "F1": section_F1, "F2": section_F2, "F3": section_F3,
                "F4": section_F4, "F5": section_F5}

    # A 建视图，必须先跑；其统计量本身也要记
    sections["A"](con)
    for name, fn in sections.items():
        if name == "A":
            continue
        if only and name not in only:
            continue
        fn(con)

    if OUT.exists() and only:
        merged = json.loads(OUT.read_text(encoding="utf-8"))
        merged.update(RECORD)
        RECORD.clear()
        RECORD.update(merged)
    OUT.write_text(json.dumps(RECORD, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten {OUT}")


if __name__ == "__main__":
    main()
