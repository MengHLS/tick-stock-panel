from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import polars as pl

PROJECT = Path(r"C:\work\sourcecode\tick-stock-panel")
sys.path.insert(0, str(PROJECT / "backend"))

from app.config import settings  # noqa: E402
from app.extensions.adapters import FileMarketData  # noqa: E402
from app.tickflow.security_status import read_st_history  # noqa: E402

COLS = ["symbol", "date", "open", "high", "low", "close",
        "raw_close", "raw_high", "raw_low", "volume", "amount"]

m = FileMarketData(settings.data_dir)
frame = m.get_daily_batch([], date(2018, 1, 8), date(2026, 11, 6), COLS)
frame = frame.filter(
    pl.col("symbol").str.starts_with("60") | pl.col("symbol").str.starts_with("00")
).sort(["symbol", "date"])
print("panel rows", frame.height, "symbols", frame["symbol"].n_unique(),
      "dates", frame["date"].n_unique(), frame["date"].min(), frame["date"].max())

hist = read_st_history(settings.data_dir)
print("st rows", hist.height, "coverageEnd", hist["flag_date"].max())

inst = m.get_instruments()
print("instruments", inst.height)
ld = inst.select("symbol", pl.col("listing_date").str.to_date(strict=False).alias("listing_date"))
print("listing null", ld["listing_date"].null_count())

f = frame.with_columns(pl.col("date").cum_count().over("symbol").alias("obs_a"))

axis = frame["date"].unique().sort()
ax = pl.DataFrame({"date": axis}).with_row_index("ax_idx")
f = f.join(ld, on="symbol", how="left").join(ax, on="date", how="left")
f = f.with_columns(
    pl.coalesce(pl.col("listing_date").search_sorted(pl.col("date"), side="right"), 1).alias("_ld_pos")
)
f = f.with_columns((pl.col("ax_idx") - pl.col("_ld_pos") + 1).alias("obs_b"))

win = f.filter(pl.col("date").is_between(date(2019, 7, 1), date(2026, 10, 30)))
print("window rows", win.height)
d = win.select((pl.col("obs_a") - pl.col("obs_b")).abs().alias("diff"))
print("obs diff>0 rows", d.filter(pl.col("diff") > 0).height)
print(win.select(
    (pl.col("obs_a") >= 120).sum().alias("a_ge120"),
    (pl.col("obs_b") >= 120).sum().alias("b_ge120"),
))

w = f.filter(pl.col("date").is_between(date(2026, 10, 20), date(2026, 11, 6)))
per = w.group_by("date").agg(pl.len().alias("bars")).sort("date")
print(per)
print("window trading days", per.height, "total bars", per["bars"].sum())
