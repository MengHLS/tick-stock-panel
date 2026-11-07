cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import duckdb
con = duckdb.connect()
con.execute("CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet', hive_partitioning=true, union_by_name=true)")
con.execute("CREATE VIEW ins AS SELECT symbol, CAST(substr(listing_date,1,10) AS DATE) ld FROM read_parquet('D:/TSP/data/instruments/instruments.parquet')")
con.execute("CREATE TABLE ps AS SELECT symbol, min(d) fb FROM k GROUP BY 1")
print("60/00 universe:", con.execute("SELECT count(*), count(ld) FROM ps LEFT JOIN ins USING(symbol) WHERE symbol LIKE '60%' OR symbol LIKE '00%'").fetchall())
print("listed_after_2018_first_bar_eq_listing:", con.execute("SELECT count(*), count(*) FILTER (WHERE ps.fb=ins.ld) FROM ps JOIN ins USING(symbol) WHERE (symbol LIKE '60%' OR symbol LIKE '00%') AND ins.ld>=DATE '2018-01-08'").fetchall())
print("listed_before_2018_first_bar_eq_panel_start:", con.execute("SELECT count(*), count(*) FILTER (WHERE ps.fb=DATE '2018-01-08') FROM ps JOIN ins USING(symbol) WHERE (symbol LIKE '60%' OR symbol LIKE '00%') AND ins.ld<DATE '2018-01-08'").fetchall())
print("BJ in instruments:", con.execute("SELECT count(*) FROM ins WHERE symbol LIKE '%.BJ'").fetchall())
print("kline_BJ:", con.execute("SELECT count(*) FROM ps WHERE symbol LIKE '%.BJ'").fetchall())
print("listing_date_null:", con.execute("SELECT count(*) FROM ins WHERE ld IS NULL").fetchall())
PY
# 实测输出: (3385, 3385) / (635, 634) / (2750, 2422) / 0 / 355 / 3
