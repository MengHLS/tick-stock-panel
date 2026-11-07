"""E3：消失标的的最后一条 bar 上的 ST 状态（只读）。"""
import duckdb
con = duckdb.connect(); con.execute("SET threads=8")
con.execute("CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet', hive_partitioning=true, union_by_name=true)")
con.execute("CREATE VIEW st AS SELECT symbol, CAST(flag_date AS DATE) fd, st_flag FROM read_parquet('D:/TSP/data/st_history/part.parquet')")
con.execute("""CREATE TABLE j AS
 with cal as (select d, row_number() over (order by d) di from (select distinct d from k)),
      mx as (select max(di) m from cal),
      ps as (select symbol, max(d) lb from k group by 1)
 select p.symbol, p.lb, m.m - c.di gap from ps p join cal c on c.d = p.lb cross join mx m
 where p.lb < (select max(d) from k)""")
con.execute("""CREATE TABLE lj AS
 select j.symbol, j.gap, s.st_flag from j asof left join st s on j.symbol = s.symbol and j.lb >= s.fd""")
print("total/ge250/lt60:", con.execute("select count(*), count(*) filter (where gap>=250), count(*) filter (where gap<60) from j").fetchone())
print("ge250 st:", con.execute("select count(*) filter (where st_flag), count(*) filter (where st_flag=false) from lj where gap>=250").fetchone())
print("lt60 st:", con.execute("select count(*) filter (where st_flag), count(*) filter (where st_flag=false) from lj where gap<60").fetchone())
print("baseline true 2019-01-01:", con.execute("select count(*), count(distinct symbol) from st where fd=DATE '2019-01-01' and st_flag").fetchone())
print("last bar year:", con.execute("select year(lb), count(*), sum(x) from (select p.symbol, max(d) lb, count(*) x from k p group by 1) where lb < (select max(d) from k) group by 1 order by 1").fetchall())
