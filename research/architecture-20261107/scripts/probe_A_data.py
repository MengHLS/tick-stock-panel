"""只读数据可行性探针（A 部分）：实际读取 D:/TSP/data 的 enriched 日线面板。

只读，不写任何生产目录。输出 JSON 到 stdout。
运行: backend\\.venv\\Scripts\\python.exe research\\architecture-20261107\\scripts\\probe_A_data.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import polars as pl

DATA = Path(r"D:/TSP/data")
KLINE = DATA / "kline_daily_enriched"
COLS = [
    "symbol", "date", "open", "high", "low", "close",
    "raw_close", "raw_high", "raw_low", "volume", "amount", "turnover_rate",
]
EVAL_START = date(2019, 7, 1)
STALE_CUTOFF = date(2026, 9, 24)

out: dict = {}


def main() -> None:
    dates = sorted(p.name.split("=")[1] for p in KLINE.glob("date=*"))
    out["panel"] = {
        "dir": str(KLINE),
        "partitions": len(dates),
        "date_min": dates[0],
        "date_max": dates[-1],
        "columns": COLS,
        "raw_open_present_in_source": False,
    }

    frame = pl.scan_parquet(KLINE / "date=*" / "*.parquet").select(COLS).collect()
    out["panel"]["rows"] = frame.height
    out["panel"]["distinct_symbols"] = frame["symbol"].n_unique()
    out["panel"]["trading_days"] = frame["date"].n_unique()

    per_symbol = frame.group_by("symbol").agg(
        pl.len().alias("bars"),
        pl.col("date").min().alias("first"),
        pl.col("date").max().alias("last"),
        (pl.col("volume") <= 0).sum().alias("zero_vol_rows"),
        (pl.col("open") <= 0).sum().alias("zero_open_rows"),
        ((pl.col("close") - pl.col("raw_close")).abs() > 1e-9).sum().alias("adj_diff_rows"),
    )
    out["per_symbol"] = {
        "symbols": per_symbol.height,
        "bars_min": int(per_symbol["bars"].min()),
        "bars_median": float(per_symbol["bars"].median()),
        "bars_max": int(per_symbol["bars"].max()),
        "rows_with_zero_volume": int(per_symbol["zero_vol_rows"].sum()),
        "rows_with_zero_open": int(per_symbol["zero_open_rows"].sum()),
        "symbols_with_any_zero_volume_row": int((per_symbol["zero_vol_rows"] > 0).sum()),
        "symbols_never_differ_close_vs_raw": int((per_symbol["adj_diff_rows"] == 0).sum()),
    }

    stale = per_symbol.filter((pl.col("last") < STALE_CUTOFF) & (pl.col("bars") >= 120))
    out["stale"] = {
        "count_last_bar_before_20260924_bars_ge_120": stale.height,
        "last_bar_year_hist": {
            str(k): v
            for k, v in sorted(
                stale.with_columns(pl.col("last").dt.year().alias("y"))
                .group_by("y").agg(pl.len().alias("n")).iter_rows()
            )
        },
    }
    out["last_bar_year_all"] = {
        str(k): v
        for k, v in sorted(
            per_symbol.with_columns(pl.col("last").dt.year().alias("y"))
            .group_by("y").agg(pl.len().alias("n")).iter_rows()
        )
    }

    yearly = (
        frame.with_columns(pl.col("date").dt.year().alias("y"))
        .group_by("y").agg(pl.col("symbol").n_unique().alias("symbols")).sort("y")
    )
    out["symbols_per_year"] = {str(k): v for k, v in yearly.iter_rows()}
    s2019 = set(frame.filter(pl.col("date").dt.year() == 2019)["symbol"].unique().to_list())
    s2025 = set(frame.filter(pl.col("date").dt.year() == 2025)["symbol"].unique().to_list())
    out["present_2019_absent_2025"] = len(s2019 - s2025)
    s2026 = set(frame.filter(pl.col("date").dt.year() == 2026)["symbol"].unique().to_list())
    out["present_2019_absent_2026"] = len(s2019 - s2026)

    pre = frame.filter(pl.col("date") < EVAL_START).group_by("symbol").agg(pl.len().alias("pre_bars"))
    for n in (20, 60, 120, 250):
        out[f"symbols_pre_bars_ge_{n}"] = int((pre["pre_bars"] >= n).sum())
    out["symbols_in_panel"] = pre.height
    out["symbols_missing_from_prewindow"] = int(frame["symbol"].n_unique() - pre.height)

    all_dates = frame["date"].unique().sort().to_list()
    didx = {d: i for i, d in enumerate(all_dates)}
    spans = (
        frame.select("symbol", "date").unique()
        .group_by("symbol")
        .agg(pl.len().alias("rows"), pl.col("date").min().alias("first"), pl.col("date").max().alias("last"))
        .with_columns(
            pl.col("first").replace_strict(didx, return_dtype=pl.Int64).alias("i0"),
            pl.col("last").replace_strict(didx, return_dtype=pl.Int64).alias("i1"),
        )
        .with_columns(((pl.col("i1") - pl.col("i0") + 1) - pl.col("rows")).alias("gap"))
    )
    out["missing_rows_inside_span"] = {
        "symbols_with_gap": int((spans["gap"] > 0).sum()),
        "total_gap_days": int(spans["gap"].sum()),
        "max_gap_days_single_symbol": int(spans["gap"].max()),
        "symbols_gap_ge_20d": int((spans["gap"] >= 20).sum()),
    }

    inst = pl.read_parquet(DATA / "instruments" / "instruments.parquet")
    out["instruments"] = {
        "rows": inst.height,
        "columns": inst.columns,
        "lifecycle_columns": [c for c in inst.columns if any(k in c.lower() for k in ("delist", "list", "end", "status"))],
    }
    inst_syms = set(inst["symbol"].to_list())
    panel_syms = set(frame["symbol"].unique().to_list())
    out["instruments"]["panel_symbols_missing_from_instruments"] = len(panel_syms - inst_syms)
    out["instruments"]["instruments_symbols_without_panel_rows"] = len(inst_syms - panel_syms)
    main_board_panel = {s for s in panel_syms if s.startswith(("60", "00"))}
    out["instruments"]["main_board_panel_symbols"] = len(main_board_panel)
    out["instruments"]["main_board_symbols_missing_from_instruments"] = len(main_board_panel - inst_syms)

    adj = pl.read_parquet(DATA / "adj_factor" / "all.parquet")
    adj_syms = set(adj["symbol"].unique().to_list()) if "symbol" in adj.columns else set()
    out["adj_factor"] = {
        "rows": adj.height,
        "columns": adj.columns,
        "distinct_symbols": len(adj_syms),
        "date_min": str(adj["date"].min()) if "date" in adj.columns else None,
        "date_max": str(adj["date"].max()) if "date" in adj.columns else None,
        "main_board_symbols_without_adj_row": len(main_board_panel - adj_syms),
    }

    st = pl.read_parquet(DATA / "st_history" / "part.parquet")
    stinfo = {"rows": st.height, "columns": st.columns}
    if "symbol" in st.columns:
        stinfo["distinct_symbols"] = st["symbol"].n_unique()
    for cand in ("date", "trade_date"):
        if cand in st.columns:
            stinfo["date_min"] = str(st[cand].min())
            stinfo["date_max"] = str(st[cand].max())
            stinfo["distinct_dates"] = st[cand].n_unique()
    out["st_history"] = stinfo

    idx = pl.scan_parquet(
        DATA / "kline_index_daily" / "date=*" / "*.parquet", extra_columns="ignore"
    ).select(["symbol", "date", "close"]).collect()
    out["index_daily"] = {
        "rows": idx.height,
        "symbols": idx["symbol"].n_unique(),
        "date_min": str(idx["date"].min()),
        "date_max": str(idx["date"].max()),
        "symbol_sample": idx["symbol"].unique().sort().head(8).to_list(),
    }

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
