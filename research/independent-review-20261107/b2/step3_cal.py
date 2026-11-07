"""独立复跑 #3: CAL-observed_bars 与 E3-A1 是否互斥 (口径 B 对池内家数的方向与量级)。"""
from __future__ import annotations
import json
from pathlib import Path
import duckdb

PANEL = "read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet')"
INSTR = "read_parquet('D:/TSP/data/instruments/instruments.parquet')"
con = duckdb.connect(); con.sql("SET enable_progress_bar=false")
con.sql("SET temp_directory='D:/TSP/duckdb_tmp'"); con.sql("SET max_temp_directory_size='40GB'")
con.sql(f"""create view bars as select symbol, date, volume, amount, raw_close from {PANEL}
  where (symbol like '60%' or symbol like '00%')
    and date between date '2018-01-08' and date '2026-11-06'""")
con.sql("""create view cal as select date, row_number() over (order by date) as idx
  from (select distinct date from bars)""")
con.sql(f"create view inst as select symbol, try_cast(listing_date as date) as ld from {INSTR}")
con.sql("""create view start_idx as
  select i.symbol, min(c.idx) as idx0 from inst i join cal c on c.date >= i.ld group by i.symbol""")
con.sql("""create view cmp as
  select b.symbol, b.date, c.idx as idx, s.idx0, c.idx - s.idx0 + 1 as b_days,
         row_number() over (partition by b.symbol order by b.date) as a_bars
  from bars b join cal c using(date) left join start_idx s using(symbol)""")
q = con.sql("""
  select
    count(*) as rows_all,
    sum(case when (a_bars>=120) <> (b_days>=120) then 1 else 0 end) as flip_all,
    sum(case when date between date '2019-07-01' and date '2026-10-30'
             and (a_bars>=120) <> (b_days>=120) then 1 else 0 end) as flip_eval,
    sum(case when date between date '2019-07-01' and date '2026-10-30'
             and (a_bars<120) and (b_days>=120) then 1 else 0 end) as eval_A_blocks_B_allows,
    sum(case when date between date '2019-07-01' and date '2026-10-30'
             and (a_bars>=120) and (b_days<120) then 1 else 0 end) as eval_B_blocks_A_allows
  from cmp""").pl()
print(q.rows(), flush=True)
# 逐日池内家数变化 (只改 observed_bars 口径, 其余条件不变会引入 ST/价格/成交额, 这里只看 >=120 的翻转)
d = con.sql("""
  select date,
         sum(case when (a_bars<120) and (b_days>=120) then 1 else 0 end) as added_by_B,
         sum(case when (a_bars>=120) and (b_days<120) then 1 else 0 end) as removed_by_B
  from cmp where date between date '2019-07-01' and date '2026-10-30'
  group by date having added_by_B > 0 or removed_by_B > 0 order by date""").pl()
print("days with flip:", d.height, "sum added", int(d["added_by_B"].sum()) if d.height else 0,
      "sum removed", int(d["removed_by_B"].sum()) if d.height else 0, flush=True)
print(d.head(10).rows(), flush=True)
con.close()
Path("research/independent-review-20261107/b2/step3.json").write_text(json.dumps({
  "rows_all": q.rows()[0][0], "flip_all": q.rows()[0][1], "flip_eval": q.rows()[0][2],
  "eval_A_blocks_B_allows": q.rows()[0][3], "eval_B_blocks_A_allows": q.rows()[0][4],
  "days_with_flip": d.height,
  "sum_added_by_B": int(d["added_by_B"].sum()) if d.height else 0,
  "sum_removed_by_B": int(d["removed_by_B"].sum()) if d.height else 0,
  "first_days": d.head(10).rows(),
}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
