"""归因：REGISTRATION_B0 §4.1 里那个 4.6% 到底属于 vol60 还是 ret1。

在 probe_vol60.py 同一子集（symbol 排序前 60 只）上，分别量：
  ret1 : close.pct_change()  vs  close/close.shift(1)-1
  vol60: ret1_pct.rolling_std(60)  vs  ret1_div.rolling_std(60)
各报：两侧非 null 行数 n、非零差行数、占比、超 1e-12 行数。
"""
import sys, json
from pathlib import Path

PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(PROJECT / "backend"))
sys.path.insert(0, str(PROJECT / "research" / "strategy-search-20261107" / "scripts"))
import common
import polars as pl

out = {"probe": "first 60 symbols by sorted symbol, same subset as probe_vol60.py"}
m = common.open_market()
f = common.load_panel(m)
out["panel_rows"] = f.height
syms = f["symbol"].unique().sort().to_list()[:60]
part = f.filter(pl.col("symbol").is_in(syms)).sort(["symbol", "date"])
out["subset_rows"] = part.height
out["subset_symbols"] = len(syms)

p = part.select(["symbol", "date", "close"]).with_columns([
    pl.col("close").pct_change().over("symbol").alias("ret1_pct"),
    (pl.col("close") / pl.col("close").shift(1).over("symbol") - 1).alias("ret1_div"),
])
p = p.with_columns([
    pl.col("ret1_pct").rolling_std(60).over("symbol").alias("vol60_pct"),
    pl.col("ret1_div").rolling_std(60).over("symbol").alias("vol60_div"),
])

def stat(a, b):
    d = (pl.col(a).cast(pl.Float64) - pl.col(b).cast(pl.Float64)).abs()
    both = pl.col(a).is_not_null() & pl.col(b).is_not_null()
    n = int(p.filter(both).height)
    nz = int(p.filter(both & (d > 0)).height)
    over = int(p.filter(both & (d > 1e-12)).height)
    mx = float(p.filter(both).select(d.max()).item() or 0.0)
    return {"n_both_nonnull": n, "n_nonzero_diff": nz,
            "pct_nonzero": round(100.0 * nz / n, 4) if n else None,
            "n_over_1e-12": over, "max_abs_diff": mx}

out["ret1"] = stat("ret1_pct", "ret1_div")
out["vol60"] = stat("vol60_pct", "vol60_div")
print(json.dumps(out, ensure_ascii=False, indent=2))
Path(PROJECT / "research/b2-engine-20261107/logs/probe_4p6_attribution.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
