import sys, json
sys.path.insert(0, "backend")
import duckdb

c = duckdb.connect()
c.sql("SET enable_progress_bar=false")
bars = "read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet')"
c.sql(f"create view b as select symbol, date, volume, amount, raw_close from {bars} where symbol like '60%' or symbol like '00%'")
c.sql("create view ax as select distinct date from read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet')")

# research observed_bars = cum_count over symbol within loaded panel (panel starts 2018-01-08)
c.sql("create view cum as select symbol, date, row_number() over (partition by symbol order by date) as observed_bars from b")

# trading-days-since-listing (using instruments.listing_date + trading axis)
c.sql("""create view inst as
  select symbol, try_cast(listing_date as date) ld
  from read_parquet('D:/TSP/data/instruments/instruments.parquet')""")
c.sql("""create view tdsl as
  select c.symbol, c.date, c.observed_bars,
         (select count(*) from ax where ax.date between i.ld and c.date) as tdays
  from cum c left join inst i using(symbol)
  where c.date between date '2019-07-01' and date '2026-10-30'""")

print("window rows:", c.sql("select count(*) from tdsl").fetchone())
print("listing_date null:", c.sql("select count(*) from tdsl where tdays is null").fetchone())
print("cum>=120:", c.sql("select count(*) from tdsl where observed_bars>=120").fetchone())
print("tdays>=120:", c.sql("select count(*) from tdsl where tdays>=120").fetchone())
print("disagree rows:", c.sql("select count(*) from tdsl where (observed_bars>=120) <> (tdays>=120)").fetchone())
print("disagree syms:", c.sql("select count(distinct symbol) from tdsl where (observed_bars>=120) <> (tdays>=120)").fetchone())
print("--- sample disagreements ---")
for r in c.sql("""select symbol, date, observed_bars, tdays from tdsl
                  where (observed_bars>=120) <> (tdays>=120) order by symbol, date limit 10""").fetchall():
    print(r)
# where does tdays come from when listing before 2018
print("--- axis range ---", c.sql("select min(date), max(date), count(*) from ax").fetchone())
