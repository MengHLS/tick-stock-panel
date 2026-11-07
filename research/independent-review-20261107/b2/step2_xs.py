"""独立复跑 #2: XS 语义负样本 + XS-B1 + rank 无掩码哈希不变 + W4 窗口 xs_rank_pool null。"""
from __future__ import annotations
import hashlib, importlib.util, json, sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, "backend")
import polars as pl
from app.factors import dsl

OUT = {}

def run(text, frame, col=None):
    c = dsl.compile_formula(text)
    if not c.ok:
        return None, [(e.code, e.message) for e in c.errors]
    o = c.frame_transform(frame)
    return (o[dsl.FACTOR_COLUMN].to_list() if o is not None else None), []

def fixture(closes, mask=None):
    n = len(closes)
    syms = [f"S{i+1:02d}" for i in range(n)]
    return pl.DataFrame({
        "symbol": syms, "date": [date(2024,1,2)]*n,
        "close": [float(x) for x in closes],
        "volume": [1000.0]*n, "amount": [1e9]*n, "raw_close": [float(x) for x in closes],
    })

# ---------- NEG-pool3of6: 6 行 3 只在池内, 池内名次 4/5/6 (交替)
f3 = fixture([1,7,2,8,3,9])
pool, e1 = run("xs_rank_pool(close, close > 5)", f3)
pct,  e2 = run("xs_rank_pct(close, close > 5)", f3)
mkt,  e3 = run("xs_rank_market(close)", f3)
OUT["NEG-pool3of6"] = {
    "pool": pool, "pct": pct, "errors": [e1,e2,e3],
    "pool_expect": [0.3333333333333333,0.6666666666666666,1.0],
    "pct_max": max([v for v in (pct or []) if v is not None], default=None),
    "pct_exceeds_1": any(v is not None and v > 1.0 for v in (pct or [])),
    "pool_le_1": all(v is None or v <= 1.0 for v in (pool or [])),
    "last3_pool": (pool or [])[1::2], "last3_pct": (pct or [])[1::2],
    "distinguishable": (pool or [])[1::2] != (pct or [])[1::2],
}

# ---------- NEG-pool1: 池内 1 只, 且全局名次第 1 -> 不可区分
f1 = fixture([1,2,3,4,5,9])
pool1, _ = run("xs_rank_pool(close, close > 5)", f1)
pct1,  _ = run("xs_rank_pct(close, close > 5)", f1)
mkt1,  _ = run("xs_rank_market(close)", f1)
OUT["NEG-pool1"] = {"pool": pool1, "pct": pct1, "market": mkt1,
                    "nonnull_pool": [v for v in pool1 if v is not None],
                    "nonnull_pct": [v for v in pct1 if v is not None],
                    "indistinguishable": [v for v in pool1 if v is not None] == [v for v in pct1 if v is not None]}

# ---------- 契约 §3.1 四行样例: pool={0.5,1.0} vs pct={0.5,1.5}
f4 = fixture([1,2,3,9])   # 4 行, 池内 2 只 (close>5 -> 只有 9), 另测:
# 需要池内 2 只且全局名次 1,3 -> 让池成员为 1 与 3:
f4 = fixture([1,9,3,8])
pool4,_ = run("xs_rank_pool(close, close > 5)", f4)
pct4,_  = run("xs_rank_pct(close, close > 5)", f4)
OUT["NEG-4rows"] = {"pool": pool4, "pct": pct4,
                    "pool_vals": sorted([v for v in pool4 if v is not None]),
                    "pct_vals": sorted([v for v in pct4 if v is not None])}

# ---------- XS-B1: xs_rank_market ≡ rank 逐位 (合成 + 真实样本)
f_b1 = fixture([3,1,4,1,5,9,2,6])
r_mkt,_ = run("xs_rank_market(close)", f_b1)
r_rank,_ = run("rank(close)", f_b1)
OUT["XS-B1_fixture"] = {"market": r_mkt, "rank": r_rank,
                        "bitwise_equal": r_mkt == r_rank,
                        "float_exact_equal": (
                            (pl.Series("m", r_mkt, dtype=pl.Float64)
                             .eq_missing(pl.Series("r", r_rank, dtype=pl.Float64))).all()
                            if r_mkt is not None else None)}

# 真实样本: 最近 80 个交易日
import duckdb
con = duckdb.connect(); con.sql("SET enable_progress_bar=false")
real = con.sql("""
  select symbol, date, close, volume, amount, raw_close
  from read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet')
  where (symbol like '60%' or symbol like '00%')
    and date >= (select max(date) - interval 120 day from read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet'))
  order by symbol, date
""").pl()
con.close()
real = real.with_columns(pl.col("date").cast(pl.Date))
print("real rows", real.height, real["date"].n_unique(), flush=True)
mr,_ = run("xs_rank_market(close)", real)
rr,_ = run("rank(close)", real)
OUT["XS-B1_real"] = {"rows": real.height, "dates": real["date"].n_unique(),
    "bitwise_equal": mr == rr,
    "n_diff": sum(1 for a,b in zip(mr,rr) if a != b),
    "max_abs_diff": max([abs(a-b) for a,b in zip(mr,rr) if a is not None and b is not None], default=None),
    "nulls_market": sum(1 for a in mr if a is None), "nulls_rank": sum(1 for b in rr if b is None)}

# ---------- rank 无掩码输出: HEAD 版 dsl vs 现版, 逐位
src_old = Path("research/independent-review-20261107/b2/dsl_head.py")
import subprocess
src_old.write_text(subprocess.run(["git","show","HEAD:backend/app/factors/dsl.py"],
                                  capture_output=True, text=True, encoding="utf-8").stdout, encoding="utf-8")
spec = importlib.util.spec_from_file_location("dsl_head", src_old)
old = importlib.util.module_from_spec(spec); sys.modules["dsl_head"]=old; spec.loader.exec_module(old)
OUT["old_dsl_loaded"] = hasattr(old, "compile_formula")
for formula in ("rank(close)", "rank(amount)", "zscore(close)"):
    co = old.compile_formula(formula); cn = dsl.compile_formula(formula)
    oo = co.frame_transform(real)[old.FACTOR_COLUMN].to_list() if co.ok else None
    on = cn.frame_transform(real)[dsl.FACTOR_COLUMN].to_list() if cn.ok else None
    h = lambda v: hashlib.sha256(repr(v).encode()).hexdigest()[:16]
    OUT.setdefault("rank_unchanged", {})[formula] = {
        "old_ok": co.ok, "new_ok": cn.ok, "bitwise_equal": oo == on,
        "hash_old": h(oo), "hash_new": h(on),
        "n_diff": None if oo is None or on is None else sum(1 for a,b in zip(oo,on) if a!=b)}

# ---------- W4: 窗口内 xs_rank_pool(vol60, in_universe) 全 null
from app.config import settings
from app.tickflow.security_status import read_st_history
from app.custom.research_universe_pack.universe import compute_in_universe
import duckdb as d2
c2 = d2.connect(); c2.sql("SET enable_progress_bar=false")
wf = c2.sql("""
  select symbol, date, close, volume, amount, raw_close
  from read_parquet('D:/TSP/data/kline_daily_enriched/date=*/*.parquet')
  where (symbol like '60%' or symbol like '00%') and date >= date '2026-06-01'
  order by symbol, date""").pl()
c2.close()
wf = wf.with_columns(pl.col("date").cast(pl.Date)).sort(["symbol","date"])
wf = wf.with_columns(pl.col("close").pct_change().over("symbol").alias("ret1"))
wf = wf.with_columns(pl.col("ret1").rolling_std(60).over("symbol").alias("vol60"))
h = read_st_history(settings.data_dir)
wf = compute_in_universe(wf, st_history=h)
win = wf.filter(pl.col("date") >= pl.lit(date(2026,10,20)))
out_win = dsl.compile_formula("xs_rank_pool(vol60, in_universe)")
ow = out_win.frame_transform(win) if out_win.ok else None
OUT["W4_window"] = {"compiled": out_win.ok,
    "rows": win.height, "days": win["date"].n_unique(),
    "nonnull": 0 if ow is None else sum(1 for v in ow[dsl.FACTOR_COLUMN].to_list() if v is not None),
    "in_universe_nonnull": int(win.filter(pl.col("in_universe").is_not_null()).height)}
# 窗口外健康日对照
day = wf.filter(pl.col("date") == pl.lit(date(2026,9,30)))
od = out_win.frame_transform(day) if out_win.ok else None
vals = [v for v in (od[dsl.FACTOR_COLUMN].to_list() if od is not None else []) if v is not None]
OUT["W4_normal_day"] = {"rows": day.height, "nonnull": len(vals),
    "min": min(vals) if vals else None, "max": max(vals) if vals else None,
    "pool_member_rows": int(day.filter(pl.col("in_universe")==1.0).height),
    "out_of_pool_nonnull": int(day.with_columns(od[dsl.FACTOR_COLUMN].alias("v")).filter(
        (pl.col("in_universe")!=1.0) & pl.col("v").is_not_null()).height)}

Path("research/independent-review-20261107/b2/step2.json").write_text(
    json.dumps(OUT, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
