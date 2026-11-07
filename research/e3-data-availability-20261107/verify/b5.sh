cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import duckdb
con = duckdb.connect(); con.execute("SET threads=4")
con.execute("CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet', hive_partitioning=true, union_by_name=true)")
con.execute("CREATE TABLE cal AS SELECT d, row_number() OVER (ORDER BY d) di FROM (SELECT DISTINCT d FROM k)")
con.execute("CREATE TABLE ps  AS SELECT symbol, min(d) fb, max(d) lb FROM k GROUP BY 1")
con.execute("CREATE TABLE grid AS SELECT p.symbol, c.d, c.di FROM ps p JOIN cal c ON c.d BETWEEN p.fb AND p.lb")
con.execute("CREATE TABLE miss AS SELECT g.* FROM grid g ANTI JOIN (SELECT DISTINCT symbol,d FROM k) x USING(symbol,d)")
print("cells", con.execute("SELECT count(*) FROM grid").fetchone(), "missing", con.execute("SELECT count(*) FROM miss").fetchone())
con.execute("CREATE TABLE cov AS SELECT d, count(*) a FROM grid GROUP BY 1")
con.execute("CREATE TABLE hav AS SELECT d, count(*) b FROM k GROUP BY 1")
con.execute("CREATE TABLE hole AS SELECT cov.d FROM cov LEFT JOIN hav USING(d) WHERE (cov.a-coalesce(hav.b,0))*1.0/cov.a > 0.01")
print("hole dates", con.execute("SELECT count(*) FROM hole").fetchone(),
      "miss on hole", con.execute("SELECT count(*) FROM miss JOIN hole USING(d)").fetchone())
PY
# 实测输出: cells (9824345,) missing (43503,) / hole dates (215,) miss on hole (22648,)
