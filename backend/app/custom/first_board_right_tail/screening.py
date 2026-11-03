"""Recompute first-board events from raw prices and historical status."""
from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl

from app.price_limits import polars_limit_price

_REQUIRED_DAILY = {
    "symbol",
    "date",
    "raw_close",
    "raw_high",
    "raw_low",
    "close",
    "high",
}


def is_main_board_symbol(symbol: str) -> bool:
    return symbol.endswith((".SH", ".SZ")) and symbol.startswith(("60", "00"))


def _empty_result(as_of: date, reason: str | None = None) -> dict[str, Any]:
    excluded = {reason: 0} if reason else {}
    return {
        "as_of": as_of.isoformat(),
        "event_date": None,
        "candidates": [],
        "excluded": excluded,
    }


def screen_first_boards(
    daily: pl.DataFrame,
    instruments: pl.DataFrame,
    st_history: pl.DataFrame,
    *,
    as_of: date,
) -> dict[str, Any]:
    """Return main-board first-board candidates for the newest date <= as_of.

    `consecutive_limit_ups` is deliberately not trusted. A candidate must be
    limit-up on the event date and not limit-up on the immediately prior local
    trading bar, using the exchange half-up 10% price rule on raw closes.
    """
    if daily.is_empty() or not _REQUIRED_DAILY.issubset(daily.columns):
        return _empty_result(as_of, "daily_data_unavailable")

    frame = (
        daily.filter(pl.col("date") <= as_of)
        .filter(
            pl.col("symbol").str.starts_with("60")
            | pl.col("symbol").str.starts_with("00")
        )
        .sort(["symbol", "date"])
    )
    if frame.is_empty():
        return _empty_result(as_of, "main_board_data_unavailable")
    event_date = frame["date"].max()
    frame = frame.with_columns(
        pl.when(pl.col("raw_close").is_not_null() & (pl.col("raw_close") > 0))
        .then(
            polars_limit_price(
                pl.col("raw_close").shift(1).over("symbol"),
                pl.lit(0.10),
                up=True,
            )
        )
        .otherwise(None)
        .alias("limit_up_price")
    ).with_columns(
        pl.when(pl.col("limit_up_price").is_not_null())
        # The limit helper returns the exchange price, while source floats can
        # land one ulp below an exact cent value.
        .then(pl.col("raw_close") >= pl.col("limit_up_price") - 1e-6)
        .otherwise(False)
        .alias("_is_limit_up")
    )
    frame = frame.with_columns(
        pl.col("_is_limit_up").shift(1).over("symbol").fill_null(False).alias("_prev_limit_up"),
        (pl.int_range(pl.len()).over("symbol") + 1).alias("_bar_count"),
    )

    if st_history.is_empty():
        frame = frame.with_columns(pl.lit(None, dtype=pl.Boolean).alias("st_flag"))
    else:
        frame = frame.sort("date").join_asof(
            st_history.sort("flag_date"),
            left_on="date",
            right_on="flag_date",
            by="symbol",
            strategy="backward",
            check_sortedness=False,
        )

    event_rows = frame.filter(pl.col("date") == event_date)
    info = instruments.select(
        [
            column
            for column in ("symbol", "name", "listing_date")
            if column in instruments.columns
        ]
    ).unique("symbol")
    event_rows = event_rows.join(info, on="symbol", how="left")

    excluded: dict[str, int] = {}

    def exclude(key: str) -> None:
        excluded[key] = excluded.get(key, 0) + 1

    candidates: list[dict[str, Any]] = []
    for row in event_rows.iter_rows(named=True):
        if row.get("raw_close") is None or row.get("raw_high") is None:
            exclude("raw_price_unavailable")
            continue
        if row.get("st_flag") is None:
            exclude("unknown_historical_st")
            continue
        if bool(row["st_flag"]) or "ST" in str(row.get("name") or "").upper():
            exclude("historical_st")
            continue
        if int(row.get("_bar_count") or 0) < 20:
            exclude("insufficient_listing_history")
            continue
        is_limit = bool(row.get("_is_limit_up"))
        if not is_limit:
            if int(row.get("consecutive_limit_ups") or 0) == 1:
                exclude("stale_consecutive_not_recomputed")
            else:
                exclude("not_limit_up_at_close")
            continue
        if bool(row.get("_prev_limit_up")):
            exclude("not_first_board")
            continue
        raw_close = float(row["raw_close"])
        raw_high = float(row["raw_high"])
        adj_close = float(row["close"])
        if raw_close <= 0 or raw_high <= 0 or adj_close <= 0:
            exclude("invalid_price_scale")
            continue
        ratio = adj_close / raw_close
        candidates.append(
            {
                "event_id": f"{row['symbol']}:{event_date.isoformat()}",
                "symbol": str(row["symbol"]),
                "name": row.get("name"),
                "event_date": event_date.isoformat(),
                "t_close_raw": raw_close,
                "t_close_adj": adj_close,
                "t_high_raw": raw_high,
                "t_high_adj": raw_high * ratio,
                "limit_up_price": round(float(row["limit_up_price"]), 2),
                "listing_days": int(row.get("_bar_count") or 0),
                "st_flag": False,
            }
        )

    return {
        "as_of": as_of.isoformat(),
        "event_date": event_date.isoformat(),
        "candidates": candidates,
        "excluded": excluded,
    }
