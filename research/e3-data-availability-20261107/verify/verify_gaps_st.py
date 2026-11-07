"""E3 取证：用 duckdb 复算「停牌缺口段长分布」与「ST as-of 三态」。

作用：替掉文档里两段跑不通的 polars 写法（polars 3.0.3 的 read_parquet 不接受
extra_columns，且多 schema 通配读会炸），改成与 §4.6 同一套 duckdb 视图。

只读：只建内存视图与临时表。
用法：
  backend/.venv/Scripts/python.exe research/e3-data-availability-20261107/verify/verify_gaps_st.py
"""
from __future__ import annotations

import duckdb

BARS = "D:/TSP/data/kline_daily/date=*/*.parquet"
STH = "D:/TSP/data/st_history/part.parquet"


def main() -> None:
    con = duckdb.connect()
    con.execute("SET threads=8")
    con.execute(
        "CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d "
        f"FROM read_parquet('{BARS}', hive_partitioning=true, union_by_name=true)"
    )
    con.execute(
        "CREATE VIEW st AS SELECT symbol, CAST(flag_date AS DATE) fd, st_flag "
        f"FROM read_parquet('{STH}')"
    )

    # ---- 1. 缺口段（首根..末根窗口内、当日无行）----
    con.execute("CREATE TABLE cal AS SELECT d, row_number() OVER (ORDER BY d) di "
                "FROM (SELECT DISTINCT d FROM k)")
    con.execute("CREATE TABLE ps AS SELECT symbol, min(d) fb, max(d) lb FROM k GROUP BY 1")
    con.execute("CREATE TABLE grid AS SELECT p.symbol, c.d, c.di FROM ps p JOIN cal c "
                "ON c.d BETWEEN p.fb AND p.lb")
    con.execute("CREATE TABLE miss AS SELECT g.* FROM grid g ANTI JOIN "
                "(SELECT DISTINCT symbol, d FROM k) x USING(symbol, d)")
    con.execute("""CREATE TABLE runs AS
        WITH m AS (SELECT symbol, di, di - row_number() OVER (PARTITION BY symbol ORDER BY di) g
                   FROM miss)
        SELECT symbol, count(*) len, min(di) a, max(di) b FROM m GROUP BY symbol, g""")
    print("cells/missing:", con.execute("SELECT (SELECT count(*) FROM grid), "
                                        "(SELECT count(*) FROM miss)").fetchone())
    print("runs/symbols/max_len:", con.execute(
        "SELECT count(*), count(DISTINCT symbol), max(len) FROM runs").fetchone())
    print("bucket len:", con.execute("""
        SELECT CASE WHEN "len"=1 THEN '1' WHEN "len"=2 THEN '2' WHEN "len"=3 THEN '3'
                    WHEN "len"<=5 THEN '4-5' WHEN "len"<=10 THEN '6-10'
                    WHEN "len"<=20 THEN '11-20' WHEN "len"<=60 THEN '21-60'
                    WHEN "len"<=250 THEN '61-250' ELSE '>250' END b,
               count(*) n, sum("len") n_days
        FROM runs GROUP BY 1 ORDER BY min("len")""").fetchall())
    print("top5:", con.execute(
        "SELECT r.symbol, r.\"len\", c1.d d0, c2.d d1 FROM runs r "
        "JOIN cal c1 ON c1.di=r.a JOIN cal c2 ON c2.di=r.b ORDER BY r.\"len\" DESC LIMIT 5"
    ).fetchall())

    # ---- 2. ST as-of：三态与逐年 ----
    con.execute("""CREATE TABLE sj AS
        SELECT k.symbol, k.d, s.st_flag
        FROM k ASOF LEFT JOIN st s ON k.symbol = s.symbol AND k.d >= s.fd""")
    print("cells/null:", con.execute("SELECT count(*), count(*) FILTER (WHERE st_flag IS NULL) "
                                     "FROM sj").fetchone())
    print("true cells:", con.execute("SELECT count(*) FILTER (WHERE st_flag) FROM sj").fetchone())
    print("by year:", con.execute("""
        SELECT year(d) y, count(*) n, count(*) FILTER (WHERE st_flag IS NULL) nul,
               count(*) FILTER (WHERE st_flag) tru
        FROM sj GROUP BY 1 ORDER BY 1""").fetchall())


if __name__ == "__main__":
    main()
