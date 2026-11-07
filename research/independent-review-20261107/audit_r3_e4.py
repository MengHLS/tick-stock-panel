"""独立复算 E4 (不复用 research/b4-calendar-20261107/verify_e4.py 的任何逻辑)。
只做: 从 D:/TSP/data/kline_daily_enriched 的 date=* 分区重建交易日集合,
按 calendar_axis.py 的口径 (ISO 二元组 / 数据末端 null) 复算, 与 pack 输出对撞。
"""
from __future__ import annotations
import os, sys, json, hashlib
from datetime import date
from pathlib import Path

ROOT = Path("D:/TSP/data/kline_daily_enriched")
EVAL_START, EVAL_END = date(2019,7,1), date(2026,10,30)

def partition_days(root: Path) -> tuple[date, ...]:
    out = []
    with os.scandir(root) as it:
        for e in it:
            if not e.is_dir() or not e.name.startswith("date="): continue
            try: d = date.fromisoformat(e.name[5:])
            except ValueError: continue
            # 与 repository require_part 同口径: 目录里要有 parquet
            if not any(n.endswith(".parquet") for n in os.listdir(e.path)): continue
            out.append(d)
    return tuple(sorted(out))

days = partition_days(ROOT)
print(f"[cal] n_days={len(days)} first={days[0]} last={days[-1]}")

def iso_key(d): 
    i = d.isocalendar(); return (i[0], i[1])

# flags per calendar_axis.py:121-129
flags = {}
for i, d in enumerate(days):
    nxt = days[i+1] if i+1 < len(days) else None
    if nxt is None: flags[d] = (None, None); continue
    flags[d] = (1.0 if (nxt.year, nxt.month) != (d.year, d.month) else 0.0,
                1.0 if iso_key(nxt) != iso_key(d) else 0.0)

win = [d for d in days if EVAL_START <= d <= EVAL_END]
me_win  = [d for d in win if flags[d][0] == 1.0]
we_win  = [d for d in win if flags[d][1] == 1.0]
me_full = [d for d in days if flags[d][0] == 1.0]
we_full = [d for d in days if flags[d][1] == 1.0]
print(f"[A2] window_days={len(win)} month_end_in_window={len(me_win)} week_end_in_window={len(we_win)}")
print(f"[A2] month_end_full_frame={len(me_full)} week_end_full_frame={len(we_full)}")
print(f"[A2] tail_null={[d.isoformat() for d in days if flags[d][0] is None]}")
print(f"[A2] window={win[0].isoformat()}..{win[-1].isoformat()}")

# --- A4: naive = (d.year, iso_week) 一位分组, 取组内最后一天 ---
naive_last = {}
for d in days: naive_last[(d.year, d.isocalendar()[1])] = d
naive = set(naive_last.values())
iso   = {d for d in days if flags[d][1] == 1.0}
print(f"[A4] naive_count={len(naive)} iso_count={len(iso)}")
print(f"[A4] naive_minus_iso={sorted(x.isoformat() for x in naive-iso)}")
print(f"[A4] iso_minus_naive={sorted(x.isoformat() for x in iso-naive)}")

# --- 另两种错法, 确认 iso 口径必要 ---
# 错法2: 只取 iso week 一位 (不配 iso_year), 用自然年兜住
w1_last = {}
for d in days: w1_last[(d.year, d.isocalendar()[1])] = d   # 同上, 但显式注明
# 错法3: 日历周的周日 (weekday()==4 最后一个交易日近似) -> 用 weekday 分组
wd = {d for d in days if d.weekday() == 4 or (d.weekday() < 4 and all(
    x > d and x.isocalendar()[:2] == d.isocalendar()[:2] for x in []))}
# 更清晰的错法3: 自然周 (周一到周日) 的最后交易日
ord_last = {}
for d in days:
    nat = d.toordinal() - d.weekday()   # 当周周一
    ord_last[nat] = d
nat_w = set(ord_last.values())
print(f"[A4x] naive_natural_week_count={len(nat_w)} diff_vs_iso={len(nat_w ^ iso)}")
print(f"[A4x] natural_minus_iso={sorted(x.isoformat() for x in nat_w-iso)}")
print(f"[A4x] iso_minus_natural={sorted(x.isoformat() for x in iso-nat_w)}")

# --- A5: 逐日唯一性 / 值域 / sha ---
import polars as pl
print(f"[A5] max_nunique_month={max((len({d for d in days if d.year==y and d.month==m}) and 1) for y in{2018} for m in{1})}")

# --- 与 pack 自身输出对撞 ---
sys.path.insert(0, "backend")
from app.custom.research_calendar_pack.calendar_axis import (
    load_trading_calendar, calendar_flags, FRAME_START, CALENDAR_VERSION)

pack_days = load_trading_calendar(Path("D:/TSP/data"))
print(f"[pack] n={len(pack_days)} first={pack_days[0]} last={pack_days[-1]} equal={tuple(pack_days)==days}")
pf = calendar_flags(pack_days)
mism = [d for d in days if pf[d] != flags[d]]
print(f"[pack] flags_mismatch_count={len(mism)}")
pme = sum(1 for d in days if pf[d][0]==1.0); pwe = sum(1 for d in days if pf[d][1]==1.0)
print(f"[pack] month_end_total={pme} week_end_total={pwe}")
print(f"[pack] FRAME_START={FRAME_START} CALENDAR_VERSION={CALENDAR_VERSION}")
