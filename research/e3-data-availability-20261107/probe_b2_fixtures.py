"""E3 / B2 对账夹具（只读）——生成 docs/factors/evidence/e3_b2_fixtures_20261107.json

四段：st_unknown_window / delist_proxy / listing_date_parse / suspend_gap
不写库、不建表、不改数据、不改 backend/app/**。
用法:
    backend/.venv/Scripts/python.exe research/e3-data-availability-20261107/probe_b2_fixtures.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

import duckdb

PROJECT = Path(__file__).resolve().parents[2]
DATA = Path("D:/TSP/data")
OUT = PROJECT / "docs/factors/evidence/e3_b2_fixtures_20261107.json"

BARS = str(DATA / "kline_daily_enriched" / "date=*" / "*.parquet")
BARS_RAW = str(DATA / "kline_daily" / "date=*" / "*.parquet")
INST = str(DATA / "instruments" / "instruments.parquet")
STH = str(DATA / "st_history" / "part.parquet")

EVAL_START = date(2019, 7, 1)
EVAL_END = date(2026, 10, 30)
PANEL = "(symbol like '60%' or symbol like '00%')"
ST_UNK_START, ST_UNK_END = date(2026, 10, 20), date(2026, 11, 6)  # 契约 8 日窗口 + 后续至数据末


def q(con, sql):
    """执行并把结果转成 json 友好的 records。"""
    t0 = time.time()
    df = con.sql(sql).df()
    rows = json.loads(df.to_json(orient="records", date_format="iso"))
    secs = round(time.time() - t0, 2)
    print(f"  [{secs}s, {len(rows)} rows]")
    return " ".join(sql.split()), rows


def build_views(con):
    con.sql(f"""
        create or replace view bars as
        select symbol, date, open, high, low, close, raw_close, raw_high, raw_low,
               volume, amount, turnover_rate
        from read_parquet('{BARS}') where {PANEL}
    """)
    con.sql(f"create or replace view axis as select distinct date from read_parquet('{BARS_RAW}') order by date")
    con.sql(f"create or replace view inst as select * from read_parquet('{INST}')")
    con.sql(f"""create or replace view sth as
        select symbol, cast(flag_date as date) as flag_date, st_flag from read_parquet('{STH}')""")
    con.sql("""create or replace view gap as
        with s as (select symbol, min(date) f, max(date) l from bars
                   where date between date '2019-07-01' and date '2026-10-30' group by 1)
        select s.symbol, a.date from s join axis a on a.date between s.f and s.l
        where a.date between date '2019-07-01' and date '2026-10-30'
          and not exists (select 1 from bars b where b.symbol = s.symbol and b.date = a.date)""")


# ---------------- 1. ST 不可判定窗口逐日 ----------------
def sec_st(con):
    sql, rows = q(con, f"""
        with d as (select date from axis where date between date '{ST_UNK_START}' and date '{ST_UNK_END}'),
             cur as (
                select d.date, s.symbol, s.st_flag,
                       row_number() over (partition by d.date, s.symbol order by s.flag_date desc) rn
                from d left join sth s on s.flag_date <= d.date
             ),
             cur_eff as (select date, symbol, st_flag from cur where rn = 1),
             pnl as (select distinct symbol from bars),
             bpd as (select date, count(*) n_bars from bars
                     where date between date '{ST_UNK_START}' and date '{ST_UNK_END}' group by 1),
             ev as (select flag_date,
                           count(*) filter (where st_flag) n_true,
                           count(*) filter (where not st_flag) n_false
                    from sth where flag_date between date '{ST_UNK_START}' and date '{ST_UNK_END}' group by 1),
             a_all as (select date, count(*) filter (where st_flag) n_true_all,
                              count(*) filter (where st_flag is null) n_null_all from cur_eff group by 1),
             a_pnl as (select a.date, count(*) filter (where a.st_flag) n_true_pnl
                       from cur_eff a join pnl using (symbol) group by 1)
        select d.date,
               coalesce(p.n_true_pnl, 0) as st_true_count_panel,
               coalesce(x.n_true_all, 0) as st_true_count_all_symbols,
               coalesce(x.n_null_all, 0) as st_null_all_symbols,
               coalesce(b.n_bars, 0) as bar_rows,
               coalesce(e.n_true, 0) as st_events_true,
               coalesce(e.n_false, 0) as st_events_false
        from d
        left join a_all x using (date)
        left join a_pnl p using (date)
        left join bpd b using (date)
        left join ev e on e.flag_date = d.date
        order by d.date
    """)
    tot_sql, tot = q(con, f"""
        select count(*) n_days,
               count(*) filter (where st_events_true = 0 and st_events_false = 0) n_days_no_event,
               sum(bar_rows) sum_bar_rows,
               min(st_true_count_panel) min_st_true_panel, max(st_true_count_panel) max_st_true_panel,
               (select count(*) from sth where flag_date between date '{ST_UNK_START}' and date '{ST_UNK_END}' and st_flag) win_true_events,
               (select count(*) from sth where flag_date between date '{ST_UNK_START}' and date '{ST_UNK_END}' and not st_flag) win_false_events,
               (select count(*) from sth where flag_date = date '2026-10-20' and not st_flag) bulk_false_on_1020
        from ({sql}) t
    """)
    return {
        "sql": [sql, tot_sql],
        "result": {"rows": rows, "totals": tot[0]},
        "notes": [
            "口径：st_true_count_panel = 面板 60*/00* 内、as-of（flag_date<=当日最后一条）st_flag=True 的家数；"
            "st_true_count_all_symbols 是 st_history 全表 as-of 家数（文档 218/20 用此口径）。",
            "st_events_true / st_events_false = st_history 中 flag_date 恰好等于当日的行数，按 st_flag 分列；两者皆 0 表示当日无任何 ST 状态变更事件。",
            "2026-10-20 起 st_true_count_panel 由 218 骤降，因为当日一次性写入 198 行 st_flag=False（见 totals.bulk_false_on_1020）。",
            "契约 8 日窗口 = 2026-10-20..2026-10-29；本段延伸到 2026-11-06（数据末交易日），供 B2 覆盖全不可判定段。",
        ],
    }


# ---------------- 2. 退市代理 ----------------
def sec_delist(con):
    sql_gone, gone = q(con, f"""
        with idx as (select date, row_number() over (order by date) i from axis),
             lb as (select symbol, max(date) last_bar from bars group by 1
                    having max(date) < (select max(date) from axis)),
             j as (select lb.symbol, lb.last_bar, x.i last_i, (select max(i) from idx) max_i
                   from lb join idx x on x.date = lb.last_bar)
        select symbol, last_bar,
               (max_i - last_i) as missing_trading_days,
               (last_bar > date '{EVAL_END}') as last_bar_after_eval_end,
               case when (max_i - last_i) < 5 then '<5' when (max_i - last_i) < 20 then '5-19'
                    when (max_i - last_i) < 60 then '20-59' when (max_i - last_i) < 120 then '60-119'
                    when (max_i - last_i) < 250 then '120-249' else '>=250' end as bucket
        from j order by last_bar, symbol
    """)
    sql_stats, stats = q(con, f"""
        with idx as (select date, row_number() over (order by date) i from axis),
             lb as (select symbol, max(date) last_bar from bars group by 1
                    having max(date) < (select max(date) from axis)),
             j as (select lb.symbol, lb.last_bar, x.i last_i, (select max(i) from idx) max_i
                   from lb join idx x on x.date = lb.last_bar)
        select count(*) n_symbols, count(distinct symbol) n_symbols_d,
               count(*) filter (where max_i - last_i >= 250) n_ge250,
               count(*) filter (where max_i - last_i < 60) n_lt60,
               count(*) filter (where last_bar <= date '{EVAL_END}') n_last_bar_within_eval,
               count(*) filter (where last_bar > date '{EVAL_END}') n_last_bar_after_eval,
               min(last_bar) first_last_bar, max(last_bar) last_last_bar
        from j
    """)
    sql_year, by_year = q(con, f"""
        with lb as (select symbol, max(date) last_bar from bars group by 1)
        select year(last_bar) y, count(*) n_symbols from lb
        where last_bar < (select max(date) from axis) group by 1 order by 1
    """)
    # >250 日后复牌段（窗内中途缺口，标的后来有 bar）
    sql_resume, resume = q(con, f"""
        with idx as (select date, row_number() over (order by date) i from axis
                     where date between date '{EVAL_START}' and date '{EVAL_END}'),
             gi as (select g.symbol, g.date, idx.i from gap g join idx using (date)),
             r as (select symbol, date, i, i - row_number() over (partition by symbol order by date) grp from gi),
             runs as (select symbol, grp, count(*) len, min(date) start_date, max(date) end_date
                      from r group by 1,2 having count(*) > 250),
             later as (select rs.*, (select count(*) from bars b where b.symbol = rs.symbol and b.date > rs.end_date) bars_after
                       from runs rs)
        select symbol, len as gap_trading_days, start_date, end_date, bars_after,
               (bars_after > 0) as resumed
        from later order by len desc
    """)
    _, resume_tot = q(con, """
        with idx as (select date, row_number() over (order by date) i from axis
                     where date between date '2019-07-01' and date '2026-10-30'),
             gi as (select g.symbol, g.date, idx.i from gap g join idx using (date)),
             r as (select symbol, date, i, i - row_number() over (partition by symbol order by date) grp from gi),
             runs as (select symbol, grp, count(*) len, min(date) s, max(date) e from r group by 1,2 having count(*) > 250)
        select count(*) n_segments, count(distinct symbol) n_symbols, sum(len) sum_symbol_days, max(len) max_len
        from runs
    """)
    gone_syms = {r["symbol"] for r in gone}
    overlap = sorted(gone_syms & {r["symbol"] for r in resume})
    return {
        "sql": [sql_gone, sql_stats, sql_year, sql_resume],
        "result": {
            "stats": stats[0],
            "by_last_bar_year": by_year,
            "disappeared": gone,
            "resume_after_gt250": {"stats": resume_tot[0], "segments": resume},
            "disappeared_and_resumed_overlap": overlap,
        },
        "notes": [
            "disappeared = 面板内最后有 bar 日早于交易日轴末日（2026-11-06）的标的；missing_trading_days = 该日到最后交易日的交易日数，即此前连续无 bar 的交易日数。",
            "stats.n_last_bar_within_eval = 最后有 bar 日在评估窗内（<=2026-10-30）的只数 = 194；n_last_bar_after_eval = 1 只（最后 bar 2026-11-02，晚于评估窗）= 194+1 = 195。17:27 文档「窗内消失 195 只」按数据末端（2026-11-06）口径，与本次 195 一致；若按评估窗末端 2026-10-30 严格算为 194。",
            ">=250 档不能当退市：resume_after_gt250.segments 里的标的在长缺口后都复牌（bars_after>0），会被误判为已退市。",
            "disappeared_and_resumed_overlap 中的标的（002711.SZ bars_after=30、600891.SH bars_after=30）既在 195 只消失清单里，又有 >250 交易日的中途缺口：它们的复牌只持续 30 根 bar 就再次消失。对这两只，「无行情时长」既不能解释早期缺口（实际是停牌），也无法单独确定末期是否退市 → 末期状态应为 null。",
            "库内无退市日/退市类型字段（instruments 13 列按名匹配 delist/status 为 0），本段只是事后代理，不构成时点正确的退市判定。",
        ],
    }


# ---------------- 3. listing_date 解析样例 ----------------
def sec_listing(con):
    sql, rows = q(con, f"""
        with p as (
            select i.symbol,
                   i.listing_date as raw_listing_date,
                   try_cast(substr(i.listing_date, 1, 10) as date) as parsed_listing_date
            from inst i where i.symbol like '60%' or i.symbol like '00%'
        ),
        ob as (
            select b.symbol,
                   count(*) filter (where b.date <= date '{EVAL_END}') as observed_bars_at_window_end,
                   min(b.date) as first_bar
            from bars b group by 1
        ),
        j as (
            select p.symbol, p.raw_listing_date, p.parsed_listing_date, ob.first_bar,
                   ob.observed_bars_at_window_end,
                   (select count(*) from axis a
                     where a.date > p.parsed_listing_date and a.date <= date '{EVAL_END}')
                     as trading_days_listed_to_window_end
            from p join ob using (symbol)
        ),
        pick as (
            (select symbol, 1 as grp from j order by parsed_listing_date desc nulls last, symbol limit 5)
            union all
            (select symbol, 2 as grp from j where parsed_listing_date < date '2018-01-08'
             order by parsed_listing_date asc nulls first, symbol limit 5)
            union all
            (select '603056.SH' as symbol, 3 as grp)
            union all
            (select symbol, 4 as grp from j
             where observed_bars_at_window_end between 110 and 130 and parsed_listing_date >= date '2018-01-08'
             order by observed_bars_at_window_end, symbol limit 9)
            union all
            (select symbol, 5 as grp from j
             where parsed_listing_date >= date '2018-01-08' and parsed_listing_date < date '2019-07-01'
               and symbol <> '603056.SH'
             order by parsed_listing_date, symbol limit 5)
        ),
        pick2 as (select symbol, min(grp) as grp from pick group by 1)
        select j.*, (j.observed_bars_at_window_end >= 120) as ge_120_observed_bars,
               (j.trading_days_listed_to_window_end >= 120) as ge_120_calendar_trading_days,
               (j.parsed_listing_date < date '2018-01-08') as listed_before_panel_start,
               (j.first_bar > j.parsed_listing_date) as first_bar_lags_listing,
               case pick2.grp when 1 then 'newest_listing' when 2 then 'oldest_pre_panel'
                    when 3 then 'first_bar_lag_example' when 4 then 'observed_bars_near_120'
                    else 'listed_between_panel_and_eval' end as sample_class
        from j join pick2 using (symbol)
        order by pick2.grp, j.parsed_listing_date desc nulls last, j.symbol
    """)
    sql_cov, cov = q(con, """
        select count(*) n_inst_rows,
               count(listing_date) n_listing_nonnull,
               count(*) filter (where try_cast(substr(listing_date,1,10) as date) is null) n_parse_fail,
               min(listing_date) raw_min, max(listing_date) raw_max
        from inst
    """)
    sql_bj, bj = q(con, f"""
        with allbar as (select distinct symbol from read_parquet('{BARS_RAW}'))
        select (select count(*) from allbar where symbol like '%.BJ') n_bj_with_bars,
               (select count(*) from inst where symbol like '%.BJ') n_bj_instruments_rows,
               (select count(distinct symbol) from bars) n_panel_symbols,
               (select count(*) from (select distinct b.symbol from bars b
                    left join inst i using (symbol) where i.listing_date is null)) n_panel_no_listing_date
    """)
    sql_ob, ob120 = q(con, f"""
        with j as (
            select b.symbol, b.date,
                   count(*) over (partition by b.symbol order by b.date
                                  rows between unbounded preceding and current row) ob
            from bars b
        )
        select count(*) n_symbol_days,
               count(*) filter (where ob >= 120) n_ge120,
               round(100.0 * count(*) filter (where ob >= 120) / count(*), 3) pct_ge120
        from j where date between date '{EVAL_START}' and date '{EVAL_END}'
    """)
    return {
        "sql": [sql, sql_cov, sql_bj, sql_ob],
        "result": {
            "sample_rows": rows,
            "parse_coverage": cov[0],
            "bj_and_missing": bj[0],
            "observed_bars_ge120": ob120[0],
        },
        "notes": [
            "listing_date 在维表里是 VARCHAR('YYYY-MM-DD')，必须先解析；解析失败行数见 parse_coverage.n_parse_fail。",
            "sample_rows 按五类分层抽样共 20 行无重复：newest_listing（最近上市 5）/ oldest_pre_panel（上市日早于面板起点 2018-01-08，5）/ first_bar_lag_example（603056.SH，首根晚 651 天）/ observed_bars_near_120（observed_bars 110..130且上市晚于面板起点，4）/ listed_between_panel_and_eval（上市在 2018-01-08..2019-07-01 之间，5）。",
            "listed_before_panel_start=true 的标的，库内 bar 被面板起点 2018-01-08 截断，observed_bars 会系统偏小；首根 bar 不等于上市日。",
            ".BJ（北交所）标的：bj_and_missing.n_bj_with_bars 有 K 线，但 n_bj_instruments_rows=0，维表无行 → 无 listing_date，无法算上市天数；它们不在 60/00 面板内。",
        ],
    }


# ---------------- 4. 停牌缺口 / 采集洞 ----------------
def sec_gap(con):
    sql_year, by_year = q(con, f"""
        with yb as (select year(date) y, count(*) n_rows from bars group by 1),
             yg as (select year(date) y, count(*) n_missing, count(distinct symbol) n_symbols
                    from gap group by 1)
        select yg.y as year, yg.n_missing, yg.n_symbols, yb.n_rows,
               round(100.0 * yg.n_missing / yb.n_rows, 3) pct_of_year_rows
        from yg join yb using (y) order by 1
    """)
    sql_tot, tot = q(con, f"""
        select count(*) n_missing_symbol_days, count(distinct symbol) n_symbols,
               (select count(*) from bars where date between date '{EVAL_START}' and date '{EVAL_END}') n_rows_eval,
               (select count(*) from gap) n_gap
        from gap
    """)
    sql_hole, holes = q(con, f"""
        with d as (select date, count(*) n_bars from bars
                   where date between date '{EVAL_START}' and date '{EVAL_END}' group by 1),
             g as (select date, count(*) n_gap from gap group by 1),
             ratio as (select d.date, coalesce(g.n_gap, 0) n_gap, d.n_bars,
                              1.0 * coalesce(g.n_gap, 0) / (d.n_bars + coalesce(g.n_gap, 0)) miss_ratio
                       from d left join g using (date))
        select date, n_bars, n_gap, round(miss_ratio, 5) miss_ratio
        from ratio where miss_ratio > 0.01 order by date
    """)
    sql_hole_tot, hole_tot = q(con, f"""
        with d as (select date, count(*) n_bars from bars
                   where date between date '{EVAL_START}' and date '{EVAL_END}' group by 1),
             g as (select date, count(*) n_gap from gap group by 1),
             ratio as (select d.date, coalesce(g.n_gap, 0) n_gap, d.n_bars,
                              1.0 * coalesce(g.n_gap, 0) / (d.n_bars + coalesce(g.n_gap, 0)) miss_ratio
                       from d left join g using (date)),
             hole as (select date from ratio where miss_ratio > 0.01)
        select (select count(*) from hole) n_hole_dates,
               (select count(*) from gap g join hole h using (date)) n_gap_on_hole,
               round(100.0 * (select count(*) from gap g join hole h using (date))
                     / (select count(*) from gap), 1) pct_gap_on_hole,
               (select max(miss_ratio) from ratio) max_daily_miss_ratio,
               (select count(*) from gap g anti join hole h using (date)) n_gap_attributable_to_suspension
    """)
    sql_runs, runs = q(con, f"""
        with idx as (select date, row_number() over (order by date) i from axis
                     where date between date '{EVAL_START}' and date '{EVAL_END}'),
             gi as (select g.symbol, g.date, idx.i from gap g join idx using (date)),
             r as (select symbol, date, i, i - row_number() over (partition by symbol order by date) grp from gi),
             runs as (select symbol, grp, count(*) len from r group by 1,2)
        select case when len = 1 then '1' when len <= 5 then '2-5' when len <= 20 then '6-20'
                    when len <= 60 then '21-60' when len <= 120 then '61-120'
                    when len <= 250 then '121-250' else '>250' end as bucket,
               count(*) n_runs, sum(len) n_symbol_days, max(len) max_len
        from runs group by 1 order by min(len)
    """)
    sql_vol0, vol0 = q(con, f"""
        select count(*) n_rows,
               count(*) filter (where volume = 0) n_volume_zero,
               count(*) filter (where amount = 0) n_amount_zero,
               count(*) filter (where volume is null) n_volume_null
        from bars where date between date '{EVAL_START}' and date '{EVAL_END}'
    """)
    return {
        "sql": [sql_tot, sql_year, sql_runs, sql_hole_tot, sql_hole, sql_vol0],
        "result": {
            "totals": tot[0],
            "by_year": by_year,
            "gap_runs": runs,
            "hole_summary": hole_tot[0],
            "hole_dates": holes,
            "volume_zero": vol0[0],
        },
        "notes": [
            "停牌口径 = 当日无 bar 行（symbol 存续区间内的交易日缺行）。volume=0 在全库 0 行，不能用 volume=0 判停牌。",
            "采集洞判据：当日 缺行数/(有行+缺行) > 1%。落在这些日期上的缺行属采集缺陷，归因层应给 null，不能算「停牌第 N 日」。",
            "hole_summary.n_gap_attributable_to_suspension = 13,881 - 1,113 = 12,768 格，这是「可能属停牌或退市」的格数上限（仍含长停/退市不可分辨部分）。",
            "gap_runs 给出缺口长度分布；121-250 档 5 段与 >250 档 4 段不可与退市区分，B2 不得据其判退市。",
        ],
    }


def main() -> int:
    con = duckdb.connect()
    con.execute("SET threads=4")
    con.execute("SET enable_progress_bar=false")
    print("DuckDB", duckdb.__version__, "polars", __import__("polars").__version__)
    build_views(con)

    print("\n[1/4] st_unknown_window")
    s1 = sec_st(con)
    print("[2/4] delist_proxy")
    s2 = sec_delist(con)
    print("[3/4] listing_date_parse")
    s3 = sec_listing(con)
    print("[4/4] suspend_gap")
    s4 = sec_gap(con)

    doc = {
        "meta": {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "generator": "research/e3-data-availability-20261107/probe_b2_fixtures.py",
            "purpose": "E3 in_universe / B2 实现与审核对账夹具",
            "project": str(PROJECT),
            "data_root": str(DATA),
            "duckdb_version": duckdb.__version__,
            "eval_window": [str(EVAL_START), str(EVAL_END)],
            "panel": "60*/00* on kline_daily_enriched",
            "trading_axis": "distinct date from kline_daily (2018-01-08..2026-11-06, 2141 days)",
            "doc_baseline": "docs/factors/E3_DATA_AVAILABILITY_20261107.md (17:27 snapshot)",
            "read_only": True,
        },
        "st_unknown_window": s1,
        "delist_proxy": s2,
        "listing_date_parse": s3,
        "suspend_gap": s4,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(doc, ensure_ascii=False, indent=1, default=str)
    OUT.write_text(txt, encoding="utf-8")
    blob = OUT.read_bytes()
    print(f"\nwrote {OUT}")
    print("bytes", len(blob), "lines", blob.count(b'\n') + 1)
    print("sha256", hashlib.sha256(blob).hexdigest())
    json.loads(OUT.read_text(encoding="utf-8"))
    print("json.load OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
