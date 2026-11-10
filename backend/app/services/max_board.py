"""市场最高板接力 — 从 enriched 连板列派生高度走势与断板后接替者。"""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl

from app.parquet import scan_enriched_parquet
from app.polars_guard import guarded_collect
from app.tickflow.repository import enriched_dirname

_READ_COLUMNS = [
    "symbol",
    "date",
    "close",
    "raw_close",
    "amount",
    "turnover_rate",
    "consecutive_limit_ups",
]


def _finite_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def load_board_frame(repo, start: date, end: date) -> pl.DataFrame:
    """读取最高板计算所需的窄表；历史缓存缺失时回退到 parquet 扫描。"""
    df = repo.get_enriched_range(start, end, columns=_READ_COLUMNS)
    if df is not None and not df.is_empty():
        return df

    root = repo.store.data_dir / enriched_dirname("stock")
    glob = str(root / "**" / "*.parquet")
    schema = scan_enriched_parquet(glob).collect_schema().names()
    columns = [c for c in _READ_COLUMNS if c in schema]
    if not {"symbol", "date", "consecutive_limit_ups"}.issubset(columns):
        return pl.DataFrame()
    lf = (
        scan_enriched_parquet(glob)
        .filter((pl.col("date") >= start) & (pl.col("date") <= end))
        .select(columns)
        .sort(["symbol", "date"])
    )
    return guarded_collect(lf, priority="interactive")


def _with_daily_change(df: pl.DataFrame) -> pl.DataFrame:
    """补算不复权日涨跌幅；enriched 原始分区没有 change_pct 存储列。"""
    if df.is_empty():
        return df
    if "consecutive_limit_ups" in df.columns:
        board_expr = pl.col("consecutive_limit_ups")
    elif "boards" in df.columns:
        board_expr = pl.col("boards")
    else:
        return df
    if "raw_close" in df.columns:
        price = pl.coalesce([pl.col("raw_close"), pl.col("close")])
        prev = price.shift(1).over("symbol")
        change_expr = (
            pl.when(prev.is_not_null() & (prev != 0))
            .then(price / prev - 1)
            .otherwise(None)
            .alias("change_pct")
        )
    else:
        change_expr = (
            pl.col("change_pct") if "change_pct" in df.columns else pl.lit(None).alias("change_pct")
        )
    return (
        df.sort(["symbol", "date"])
        .with_columns(
            change_expr,
            board_expr.fill_null(0).cast(pl.Int32).alias("boards"),
        )
    )


def _stock_row(row: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "")
    return {
        "symbol": symbol,
        "name": names.get(symbol) or symbol,
        "boards": int(row.get("boards") or 0),
        "change_pct": _finite_or_none(row.get("change_pct")),
        "close": _finite_or_none(row.get("close")),
    }


def build_max_board_relay(
    df: pl.DataFrame,
    dates: list[date],
    names: dict[str, str],
    *,
    context_dates: list[date] | None = None,
    exclude_st: bool = True,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """构造高度序列与断板事件。断板 = 当日最高板高度低于前一交易日。"""
    requested_dates = dates
    scan_dates = context_dates or dates
    if df.is_empty() or not requested_dates:
        return {"series": [], "events": [], "current": None, "exclude_st": exclude_st}

    frame = _with_daily_change(df)
    if exclude_st and data_dir is not None:
        from app.services.market_mainline import load_risk_warning_symbols

        st_symbols = load_risk_warning_symbols(data_dir)
        if st_symbols:
            frame = frame.filter(~pl.col("symbol").is_in(sorted(st_symbols)))

    if frame.is_empty():
        return {"series": [], "events": [], "current": None, "exclude_st": exclude_st}

    heights = (
        frame.group_by("date")
        .agg(pl.col("boards").max().alias("height"))
        .sort("date")
    )
    height_by_date = {
        row["date"]: int(row["height"] or 0)
        for row in heights.iter_rows(named=True)
    }
    leaders = (
        frame.join(heights, on="date", how="inner")
        .filter((pl.col("boards") == pl.col("height")) & (pl.col("height") > 0))
        .sort(["date", "boards", "symbol"], descending=[False, True, False])
    )
    leaders_by_date: dict[date, list[dict[str, Any]]] = {}
    for row in leaders.iter_rows(named=True):
        leaders_by_date.setdefault(row["date"], []).append(_stock_row(row, names))

    row_by_symbol_date = {
        (row["symbol"], row["date"]): row
        for row in frame.iter_rows(named=True)
    }

    series = [
        {
            "date": day.isoformat(),
            "height": height_by_date.get(day, 0),
            "leaders": leaders_by_date.get(day, []),
        }
        for day in requested_dates
    ]

    requested = set(requested_dates)
    events = []
    for i in range(1, len(scan_dates)):
        prev_day, day = scan_dates[i - 1], scan_dates[i]
        if day not in requested:
            continue
        prev_height = height_by_date.get(prev_day, 0)
        height = height_by_date.get(day, 0)
        if prev_height < 2 or height >= prev_height:
            continue

        previous_leaders = leaders_by_date.get(prev_day, [])
        former_leaders = []
        for leader in previous_leaders:
            row = row_by_symbol_date.get((leader["symbol"], day))
            former_leaders.append({
                **leader,
                "change_pct": _finite_or_none(row.get("change_pct")) if row else None,
            })

        next_day = scan_dates[i + 1] if i + 1 < len(scan_dates) else None
        successor_height = height_by_date.get(next_day, 0) if next_day else None
        successor_leaders = leaders_by_date.get(next_day, []) if next_day else []
        if next_day is None:
            status = "pending"
            successor = None
        elif successor_height is None or successor_height <= 1 or not successor_leaders:
            status = "vacant"
            successor = {
                "date": next_day.isoformat(),
                "height": int(successor_height or 0),
                "leaders": successor_leaders,
            }
        else:
            status = "taken_over"
            successor = {
                "date": next_day.isoformat(),
                "height": int(successor_height),
                "leaders": successor_leaders,
            }

        events.append({
            "id": day.isoformat(),
            "break_date": day.isoformat(),
            "previous_date": prev_day.isoformat(),
            "previous_height": prev_height,
            "previous_leaders": previous_leaders,
            "break_day": {
                "date": day.isoformat(),
                "height": height,
                "leaders": leaders_by_date.get(day, []),
                "former_leaders": former_leaders,
            },
            "successor": successor,
            "status": status,
            "height_gap": prev_height - (successor_height if successor_height is not None else height),
        })

    current = None
    if series:
        last = series[-1]
        last_date = requested_dates[-1]
        last_index = scan_dates.index(last_date) if last_date in scan_dates else len(scan_dates) - 1
        prev_height = height_by_date.get(scan_dates[last_index - 1], 0) if last_index >= 1 else last["height"]
        last_event = next((e for e in reversed(events) if e["break_date"] <= last["date"]), None)
        days_since_break = None
        if last_event:
            break_index = next(
                (i for i, d in enumerate(scan_dates) if d.isoformat() == last_event["break_date"]),
                None,
            )
            if break_index is not None:
                days_since_break = last_index - break_index
        current = {
            **last,
            "date": last_date.isoformat(),
            "delta_height": last["height"] - prev_height,
            "last_break_date": last_event["break_date"] if last_event else None,
            "days_since_break": days_since_break,
            "last_event": last_event,
        }

    return {
        "series": series,
        "events": events,
        "current": current,
        "exclude_st": exclude_st,
    }
