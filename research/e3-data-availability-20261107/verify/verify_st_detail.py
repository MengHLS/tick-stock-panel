"""E3 取证：ST 表细节 + §1 布局数字复核（只读）。"""
import duckdb

BARS = "D:/TSP/data/kline_daily/date=*/*.parquet"
ENR = "D:/TSP/data/kline_daily_enriched/date=*/*.parquet"
STH = "D:/TSP/data/st_history/part.parquet"
INS = "D:/TSP/data/instruments/instruments.parquet"

con = duckdb.connect(); con.execute("SET threads=8")
con.execute(f"CREATE VIEW st AS SELECT symbol, CAST(flag_date AS DATE) fd, st_flag FROM read_parquet('{STH}')")
con.execute(f"CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('{BARS}', hive_partitioning=true, union_by_name=true)")
con.execute(f"CREATE VIEW ins AS SELECT * FROM read_parquet('{INS}')")

print("ever_st / switches:", con.execute("""
  with s as (select symbol, count(*) n, sum(case when st_flag then 1 else 0 end) t from st group by 1)
  select count(*) filter (where t>0), count(*) from s""").fetchone(),
  con.execute("select median(n), max(n) from (select symbol,count(*) n from st group by 1)").fetchone())
print("baseline 2019-01-01:", con.execute(
  "select count(*), count(*) filter (where st_flag) from st where fd=DATE '2019-01-01'").fetchone())
print("to_true by year:", con.execute("""
  with x as (select symbol, fd, st_flag, lag(st_flag) over (partition by symbol order by fd) p from st)
  select year(fd), count(*) filter (where st_flag and (p is null or p=false)) from x group by 1 order by 1""").fetchall())
print("klines syms w/o st row:", con.execute("""
  select count(*) filter (where s.symbol is null), list(k2.symbol) filter (where s.symbol is null)
  from (select distinct symbol from k) k2 left join (select distinct symbol from st) s using(symbol)""").fetchone())
print("mass flips:", con.execute("""
  select fd, st_flag, count(*) n from st group by 1,2 having count(*)>=70 order by n desc limit 8""").fetchall())
print("names st/tui:", con.execute(
  "select count(*), count(*) filter (where name like '%ST%'), count(*) filter (where name like '%退%') from ins").fetchone())
print("last-record-2026-10-20 & 现名含ST:", con.execute("""
  with lr as (select symbol, max(fd) m from st group by 1)
  select count(*) filter (where m=DATE '2026-10-20') ,
         count(*) filter (where m=DATE '2026-10-20' and ins.name like '%ST%')
  from lr join ins using(symbol)""").fetchone())
print("60/00 eval avg bars:", con.execute("""
  select round(avg(n),1) from (select d, count(*) n from k
   where (symbol like '60%' or symbol like '00%') and d between DATE '2019-07-08' and DATE '2026-11-06'
   group by 1)""").fetchone())
print("boards:", con.execute("""
  select case when symbol like '%.BJ' then '92' else substr(symbol,1,2) end b, count(distinct symbol)
  from k group by 1 order by 2 desc""").fetchall())
print("enriched:", con.execute(f"""
  select count(*), count(distinct symbol), count(*) filter (where raw_close is null),
         count(*) filter (where close <> raw_close),
         (select count(distinct date) from read_parquet('{ENR}', hive_partitioning=true, union_by_name=true))
  from read_parquet('{ENR}', hive_partitioning=true, union_by_name=true)""").fetchone())
print("instruments:", con.execute("select count(*), count(distinct as_of), min(as_of), max(as_of), count(distinct type) from ins").fetchone())
print("bar<end & st at last bar:", con.execute("""
  with cal as (select d, row_number() over (order by d) di from (select distinct d from k)),
       mx as (select max(di) m from cal),
       ps as (select symbol, max(d) lb from k group by 1),
       j as (select p.symbol, m.m - c.di gap from ps p join cal c on c.d=p.lb cross join mx m where p.lb < (select max(d) from k))
  select count(*), count(*) filter (where gap>=250), count(*) filter (where gap<60) from j""").fetchone())
print("gap>=250 st at last bar:", con.execute("""
  with cal as (select d, row_number() over (order by d) di from (select distinct d from k)),
       mx as (select max(di) m from cal),
       ps as (select symbol, max(d) lb from k group by 1),
       j as (select p.symbol, p.lb, m.m - c.di gap from ps p join cal c on c.d=p.lb cross join mx m where p.lb < (select max(d) from k)),
       lastst as (select j.symbol, s.st_flag from j asof left join st s on j.symbol=s.symbol and j.lb>=s.fd)
  select count(*) filter (where gap>=250 and st_flag), count(*) filter (where gap>=250 and st_flag=false),
         count(*) filter (where gap<60 and st_flag), count(*) filter (where gap<60 and st_flag=false) from lastst""").fetchone())
