"""4.6% vs 77.029% 分母是否不同？两口径各自复算。"""
from __future__ import annotations
import json, sys
from datetime import date
from pathlib import Path
PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(PROJECT / "backend"))
import polars as pl
from app.config import settings
from app.extensions.adapters import FileMarketData

BASE = ["symbol","date","open","high","low","close","volume","amount"]
OUT = {}
fm = FileMarketData(settings.data_dir)
syms = sorted(fm.list_symbols())
print("symbols:", len(syms))

def share(df, label):
    df = df.sort(["symbol","date"])
    prev = pl.col("close").shift(1).over("symbol")
    f1 = (pl.col("close") / prev - 1)
    sub_ = (pl.col("close") - prev) / prev
    df = df.with_columns([f1.alias("f1"), sub_.alias("f2")])
    df = df.with_columns((pl.col("f2") - pl.col("f1")).alias("diff"))
    v = df["diff"].drop_nulls()
    n = len(v); nz = int((v != 0).sum())
    mx = float(v.abs().max()) if n else 0.0
    print(f"{label}: n={n} nonzero={nz} share={100*nz/n if n else 0:.3f}% max={mx}")
    return dict(n=n, nonzero=nz, share=100*nz/n if n else 0.0, max=mx)

OUT["s60"] = share(fm.get_daily_batch(syms[:60], date(2015,1,1), date(2026,10,30), BASE), "60 symbols")
OUT["sall"] = share(fm.get_daily_batch(syms, date(2015,1,1), date(2026,10,30), BASE), "ALL symbols")
Path(__file__).with_suffix(".json").write_text(json.dumps(OUT, ensure_ascii=False, indent=2), encoding="utf-8")
