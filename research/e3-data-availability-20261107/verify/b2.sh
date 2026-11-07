# C2 as-of 合并到全部 K 线格 → 三态与逐年分布（duckdb ASOF 版；polars 版跑不通，原因见 §10）
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import duckdb
con = duckdb.connect(); con.execute("SET threads=8")
con.execute("CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet', hive_partitioning=true, union_by_name=true)")
con.execute("CREATE VIEW st AS SELECT symbol, CAST(flag_date AS DATE) fd, st_flag FROM read_parquet('D:/TSP/data/st_history/part.parquet')")
con.execute("CREATE TABLE sj AS SELECT k.symbol, k.d, s.st_flag FROM k ASOF LEFT JOIN st s ON k.symbol = s.symbol AND k.d >= s.fd")
print(con.execute("SELECT count(*), count(*) FILTER (WHERE st_flag IS NULL), count(*) FILTER (WHERE st_flag) FROM sj").fetchone())
print(con.execute("SELECT year(d), count(*), count(*) FILTER (WHERE st_flag IS NULL), count(*) FILTER (WHERE st_flag) FROM sj GROUP BY 1 ORDER BY 1").fetchall())
PY
# 实测输出: (9780842, 755763, 276079)
# [(2018, 755758, 755758, 0), (2019, 848337, 0, 20553), (2020, 949498, 0, 42391), (2021, 1072678, 0, 45152),
#  (2022, 1170796, 0, 36264), (2023, 1258250, 0, 29179), (2024, 1293409, 0, 29047), (2025, 1313507, 0, 37400),
#  (2026, 1118609, 5, 36093)]
