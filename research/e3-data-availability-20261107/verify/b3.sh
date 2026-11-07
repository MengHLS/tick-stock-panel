# C3 末端断崖（证据最强的一条）
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import duckdb
con = duckdb.connect()
con.execute("CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet', hive_partitioning=true, union_by_name=true)")
con.execute("CREATE VIEW st AS SELECT symbol, CAST(flag_date AS DATE) fd, st_flag FROM read_parquet('D:/TSP/data/st_history/part.parquet')")
q = """WITH dd AS (SELECT DISTINCT d FROM k WHERE d >= DATE '2026-10-15')
SELECT dd.d, count(*) bars, count(*) FILTER (WHERE s.st_flag) st_true FROM dd JOIN k ON k.d=dd.d
JOIN LATERAL (SELECT st_flag FROM st WHERE st.symbol=k.symbol AND st.fd<=dd.d ORDER BY fd DESC LIMIT 1) s ON TRUE
GROUP BY 1 ORDER BY 1"""
print(con.execute(q).fetchall())
PY
# 实测输出: 2026-10-19 → 192 ; 2026-10-20..2026-11-06 → 全部 0
