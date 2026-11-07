# C1 表结构与基本计数
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import duckdb
con = duckdb.connect()
print(con.execute("""SELECT count(*) n_rows, count(DISTINCT symbol) syms, count(DISTINCT flag_date) fdates,
  min(flag_date), max(flag_date), sum(CASE WHEN st_flag THEN 1 ELSE 0 END) n_true
  FROM read_parquet('D:/TSP/data/st_history/part.parquet')""").fetchall())
PY
# 实测输出: [(7758, 5817, 1436, 2019-01-01, 2026-10-29, 986)]
