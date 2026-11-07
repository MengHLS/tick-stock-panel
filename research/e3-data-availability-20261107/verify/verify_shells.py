"""E3：维表里「有行无 K 线」的壳、现名含退、近 12 个月消失、空上市日（只读）。"""
import duckdb
con = duckdb.connect(); con.execute("SET threads=8")
con.execute("CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet', hive_partitioning=true, union_by_name=true)")
con.execute("CREATE VIEW ins AS SELECT symbol, name, CAST(substr(listing_date,1,10) AS DATE) ld FROM read_parquet('D:/TSP/data/instruments/instruments.parquet')")
con.execute("CREATE TABLE ps AS SELECT symbol, max(d) lb FROM k GROUP BY 1")
print("no-bar shells:", con.execute("""
 select count(*), count(*) filter (where symbol like '60%'), count(*) filter (where symbol like '00%'),
        count(*) filter (where symbol like '30%'), min(ld), max(ld),
        count(*) filter (where name like '%ST%'), count(*) filter (where name like '%退%')
 from ins anti join ps using(symbol)""").fetchone())
print("blank listing:", con.execute("select symbol, name, ld from ins where ld is null").fetchall())
print("last 12m by month:", con.execute("""
 select strftime(lb,'%Y-%m') m, count(*) from ps where lb < (select max(d) from k) and lb >= DATE '2025-11-01'
 group by 1 order by 1 desc""").fetchall())
print("tui still trading:", con.execute("""
 select count(*), count(*) filter (where ps.symbol is not null),
        count(*) filter (where ps.lb = (select max(d) from k))
 from ins left join ps using(symbol) where name like '%退%'""").fetchone())
