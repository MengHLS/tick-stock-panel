"""Basis-sensitivity check: adjusted vs raw prices over a window with an ex-rights date.

This is NOT a leakage test.  An ex-rights date inside the window removes a price
gap in the adjusted series, so P/L/depth/距离 legitimately differ between the
adjusted and the raw basis.  The point is to measure how large that difference
is and to show why the classification must run on one fixed, disclosed basis.

Run from the repository root:
    cd backend && uv run --frozen python \
        ../docs/research/firstboard-classification-draft-20261027/verification/check_dividend_basis.py
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
DATA = r"D:/TSP/data/kline_daily_enriched"
OUT = HERE / "dividend-basis-check.json"
WINDOW_BARS = 250
END_DATE = "2026-10-23"


def partitions(start: str, end: str) -> list[str]:
    if not os.path.isdir(DATA):
        raise SystemExit(f"data directory not found: {DATA}")
    names = sorted(
        name for name in os.listdir(DATA)
        if "=" in name and start <= name.split("=")[1] <= end
    )
    files = [f"{DATA}/{name}/part.parquet" for name in names]
    return [path for path in files if os.path.exists(path)]


def label(h: list[float], l: list[float], c: list[float]) -> dict[str, float | None]:
    peak = max(h)
    peak_i = h.index(peak)
    depth_low = min(l[peak_i:])
    return {
        "P": peak,
        "P_date_index": peak_i,
        "L": depth_low,
        "depth": (peak - depth_low) / peak if peak else None,
        "distance_to_P": c[-1] / peak - 1.0 if peak else None,
    }


def main() -> int:
    con = duckdb.connect()
    files = partitions("2023-06-01", END_DATE)
    sample = con.execute(
        "select symbol,date,high,low,close,raw_high,raw_low,raw_close "
        "from read_parquet(?) where date between DATE '2024-01-01' and ?::DATE "
        "and abs(close - raw_close) > 1e-6 limit 1",
        [files, END_DATE],
    ).df()
    if sample.empty:
        raise SystemExit("no symbol with adjusted != raw found in window")
    symbol = sample["symbol"].iloc[0]

    frame = con.execute(
        "select date,high,low,close,raw_high,raw_low,raw_close from read_parquet(?) "
        "where symbol = ? and date <= ?::DATE order by date",
        [files, symbol, END_DATE],
    ).df()
    frame = frame.tail(WINDOW_BARS)
    dates = [str(value)[:10] for value in frame["date"]]
    ratio = [float(c) / float(r) for c, r in zip(frame["close"], frame["raw_close"])]
    ex_dates = [dates[i] for i in range(1, len(ratio)) if abs(ratio[i] - ratio[i - 1]) > 1e-9]

    adjusted = label([float(x) for x in frame["high"]],
                     [float(x) for x in frame["low"]],
                     [float(x) for x in frame["close"]])
    raw = label([float(x) for x in frame["raw_high"]],
                [float(x) for x in frame["raw_low"]],
                [float(x) for x in frame["raw_close"]])

    result = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "purpose": "basis sensitivity, not leakage",
        "symbol": symbol,
        "window": {"bars": WINDOW_BARS, "start": dates[0], "end": dates[-1]},
        "ex_rights_dates_in_window": ex_dates,
        "adjusted": adjusted,
        "raw": raw,
        "delta": {
            "depth_pp": None if adjusted["depth"] is None or raw["depth"] is None
            else (adjusted["depth"] - raw["depth"]) * 100,
            "distance_to_P_pp": None if adjusted["distance_to_P"] is None
            else (adjusted["distance_to_P"] - raw["distance_to_P"]) * 100,
        },
        "note": (
            "窗口内含除权时，复权序列抹掉价格缺口，P/L/距离与原始价不同属正常，"
            "不得据两口径结果不同判为未来数据泄漏；要求分类在单一已披露基准上计算。"
        ),
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
