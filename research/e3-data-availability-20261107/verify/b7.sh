cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import duckdb
con = duckdb.connect(); con.execute("SET threads=4")
con.execute("CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet', hive_partitioning=true, union_by_name=true)")
con.execute("CREATE VIEW ins AS SELECT symbol, name FROM read_parquet('D:/TSP/data/instruments/instruments.parquet')")
con.execute("CREATE TABLE cal AS SELECT d, row_number() OVER (ORDER BY d) di FROM (SELECT DISTINCT d FROM k)")
con.execute("CREATE TABLE ps AS SELECT symbol, max(d) lb FROM k GROUP BY 1")
print("gone:", con.execute("SELECT count(*) FROM ps WHERE lb < (SELECT max(d) FROM k)").fetchone())
print("buckets_by_missing_days:", con.execute("""SELECT CASE WHEN (SELECT max(di) FROM cal)-ci.di<5 THEN '<5'
 WHEN (SELECT max(di) FROM cal)-ci.di<20 THEN '5-19' WHEN (SELECT max(di) FROM cal)-ci.di<60 THEN '20-59'
 WHEN (SELECT max(di) FROM cal)-ci.di<120 THEN '60-119' WHEN (SELECT max(di) FROM cal)-ci.di<250 THEN '120-249'
 ELSE '>=250' END b, count(*) FROM ps JOIN cal ci ON ci.d=ps.lb WHERE ps.lb < (SELECT max(d) FROM k) GROUP BY 1""").fetchall())
print("instruments_without_bar:", con.execute("SELECT count(*) FROM ins ANTI JOIN ps USING(symbol)").fetchone())
print("name_contains_tui:", con.execute("SELECT count(*), count(*) FILTER (WHERE ps.symbol IS NOT NULL) FROM ins LEFT JOIN ps USING(symbol) WHERE name LIKE '%退%'").fetchone())
PY
# 实测输出: 241 ; <5:1 / 5-19:6 / 20-59:4 / 60-119:12 / 120-249:9 / >=250:209 ; 78 ; (155, 140)
