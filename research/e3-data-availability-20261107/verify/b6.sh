# 缺口段长分布（未清洗，权威口径；duckdb 版，复用上一段的 cal/grid/miss）
cd /c/work/sourcecode/tick-stock-panel && backend/.venv/Scripts/python.exe - <<'PY'
import duckdb
con = duckdb.connect(); con.execute("SET threads=8")
con.execute("CREATE VIEW k AS SELECT symbol, CAST(date AS DATE) d FROM read_parquet('D:/TSP/data/kline_daily/date=*/*.parquet', hive_partitioning=true, union_by_name=true)")
con.execute("CREATE TABLE cal AS SELECT d, row_number() OVER (ORDER BY d) di FROM (SELECT DISTINCT d FROM k)")
con.execute("CREATE TABLE ps AS SELECT symbol, min(d) fb, max(d) lb FROM k GROUP BY 1")
con.execute("CREATE TABLE grid AS SELECT p.symbol, c.d, c.di FROM ps p JOIN cal c ON c.d BETWEEN p.fb AND p.lb")
con.execute("CREATE TABLE miss AS SELECT g.* FROM grid g ANTI JOIN (SELECT DISTINCT symbol, d FROM k) x USING(symbol, d)")
con.execute("""CREATE TABLE runs AS
  WITH m AS (SELECT symbol, di, di - row_number() OVER (PARTITION BY symbol ORDER BY di) g FROM miss)
  SELECT symbol, count(*) "len", min(di) a, max(di) b FROM m GROUP BY symbol, g""")
print(con.execute('SELECT count(*), count(DISTINCT symbol), max("len") FROM runs').fetchone())
print(con.execute("""SELECT CASE WHEN "len"=1 THEN '1' WHEN "len"=2 THEN '2' WHEN "len"=3 THEN '3'
 WHEN "len"<=5 THEN '4-5' WHEN "len"<=10 THEN '6-10' WHEN "len"<=20 THEN '11-20'
 WHEN "len"<=60 THEN '21-60' WHEN "len"<=250 THEN '61-250' ELSE '>250' END b, count(*), sum("len")
 FROM runs GROUP BY 1 ORDER BY min("len")""").fetchall())
PY
# 实测输出: (4549, 2083, 589)
# [('1',2013,2013),('2',204,408),('3',170,510),('4-5',668,3233),('6-10',992,9157),
#  ('11-20',114,1794),('21-60',222,8243),('61-250',158,15403),('>250',8,2742)]
