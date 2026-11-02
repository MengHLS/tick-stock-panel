"""First-board event selection with explicit exclusion auditing."""

from __future__ import annotations

import random
from bisect import bisect_left, bisect_right
from datetime import date

import polars as pl

from app.price_limits import MAIN_BOARD_LIMIT, parse_listing_date

_EVENT_SCHEMA = {
    "event_id": pl.String,
    "symbol": pl.String,
    "event_date": pl.Date,
    "t_close_raw": pl.Float64,
    "t_close_adj": pl.Float64,
    "t_high_raw": pl.Float64,
    "t_high_adj": pl.Float64,
    "t_low_raw": pl.Float64,
    "t_low_adj": pl.Float64,
    "consecutive_limit_ups": pl.Int64,
    "is_st_at_event": pl.Boolean,
    "listed_trading_days": pl.Int64,
    "board": pl.String,
    "price_limit_rule": pl.String,
    "price_limit_pct": pl.Float64,
    "listing_age_source": pl.String,
}

_EXCLUSION_SCHEMA = {
    "event_id": pl.String,
    "symbol": pl.String,
    "event_date": pl.Date,
    "reason": pl.String,
    "detail": pl.String,
}

_REQUIRED_DAILY_COLUMNS = {
    "symbol",
    "date",
    "high",
    "low",
    "close",
    "raw_high",
    "raw_low",
    "raw_close",
    "consecutive_limit_ups",
}


def is_main_board_symbol(symbol: str) -> bool:
    value = str(symbol).upper()
    return value.endswith((".SH", ".SZ")) and value.startswith(("60", "00"))


def _event_id() -> pl.Expr:
    return pl.concat_str(
        pl.col("symbol"),
        pl.lit(":"),
        pl.col("date").cast(pl.String),
    )


def _exclusion_rows(
    frame: pl.DataFrame,
    reason: str,
    detail: str,
) -> pl.DataFrame:
    if frame.is_empty():
        return pl.DataFrame(schema=_EXCLUSION_SCHEMA)
    return frame.select(
        _event_id().alias("event_id"),
        pl.col("symbol"),
        pl.col("date").alias("event_date"),
        pl.lit(reason).alias("reason"),
        pl.lit(detail).alias("detail"),
    )


def _positive_price(column: str) -> pl.Expr:
    value = pl.col(column).cast(pl.Float64, strict=False)
    return value.is_not_null() & value.is_finite() & (value > 0)


def _observed_listing_age(daily: pl.DataFrame) -> pl.DataFrame:
    return (
        daily.select("symbol", "date")
        .unique()
        .sort(["symbol", "date"])
        .with_columns(
            pl.col("date")
            .cum_count()
            .over("symbol")
            .cast(pl.Int64)
            .alias("_observed_listing_age")
        )
    )


def _instrument_listing_dates(
    instruments: pl.DataFrame,
) -> dict[str, date]:
    if instruments.is_empty() or "symbol" not in instruments.columns:
        return {}
    if "listing_date" not in instruments.columns:
        return {}
    out: dict[str, date] = {}
    for symbol, raw in instruments.select(
        "symbol",
        "listing_date",
    ).iter_rows():
        if not symbol or symbol in out:
            continue
        parsed = parse_listing_date(raw)
        if parsed is not None:
            out[str(symbol)] = parsed
    return out


def _listing_ages(
    frame: pl.DataFrame,
    sessions: list[date],
    listing_dates: dict[str, date],
) -> tuple[list[int], list[str]]:
    ages: list[int] = []
    sources: list[str] = []
    for row in frame.select(
        "symbol",
        "date",
        "_observed_listing_age",
    ).iter_rows(named=True):
        event_date = row["date"]
        listing_date = listing_dates.get(row["symbol"])
        if listing_date is None:
            ages.append(int(row["_observed_listing_age"] or 0))
            sources.append("observed_daily_bars")
            continue
        age = bisect_right(sessions, event_date) - bisect_left(
            sessions,
            listing_date,
        )
        ages.append(max(age, 0))
        sources.append("instrument_listing_date")
    return ages, sources


def build_first_board_events(
    daily: pl.DataFrame,
    instruments: pl.DataFrame,
    st_history: pl.DataFrame,
    sessions: list[date],
    start: date,
    end: date,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Build first-board events and retain every rejected event candidate."""
    if start > end:
        raise ValueError("start must not be later than end")
    missing = _REQUIRED_DAILY_COLUMNS - set(daily.columns)
    if daily.is_empty() or missing:
        if daily.is_empty():
            return (
                pl.DataFrame(schema=_EVENT_SCHEMA),
                pl.DataFrame(schema=_EXCLUSION_SCHEMA),
            )
        raise ValueError(f"daily missing required columns: {sorted(missing)}")

    trading_sessions = sorted(set(sessions))
    if not trading_sessions:
        raise ValueError("trading sessions are required")

    candidates = (
        daily.with_columns(
            pl.col("date").cast(pl.Date, strict=False),
            pl.col("consecutive_limit_ups")
            .cast(pl.Int64, strict=False)
            .alias("consecutive_limit_ups"),
        )
        .filter(
            (pl.col("date") >= start)
            & (pl.col("date") <= end)
            & pl.col("consecutive_limit_ups").is_not_null()
            & (pl.col("consecutive_limit_ups") >= 1)
        )
    )
    if candidates.select("symbol", "date").is_duplicated().any():
        raise ValueError("daily contains duplicate symbol/date event candidates")

    exclusion_parts: list[pl.DataFrame] = []
    non_main = candidates.filter(
        ~pl.col("symbol").map_elements(
            is_main_board_symbol,
            return_dtype=pl.Boolean,
        )
    )
    exclusion_parts.append(
        _exclusion_rows(
            non_main,
            "non_main_board",
            "symbol is not a Shanghai/Shenzhen 60/00 main-board stock",
        )
    )
    remaining = candidates.filter(
        pl.col("symbol").map_elements(
            is_main_board_symbol,
            return_dtype=pl.Boolean,
        )
    )

    history = pl.DataFrame()
    if not st_history.is_empty():
        missing_st = {"symbol", "flag_date", "st_flag"} - set(st_history.columns)
        if missing_st:
            raise ValueError(
                f"st_history missing required columns: {sorted(missing_st)}"
            )
        history = st_history.select(
            "symbol",
            pl.col("flag_date").cast(pl.Date, strict=False),
            pl.col("st_flag").cast(pl.Boolean, strict=False),
        )
        if history.select("symbol", "flag_date").is_duplicated().any():
            raise ValueError("st_history contains duplicate effective dates")
        history = history.sort(["symbol", "flag_date"])

    if remaining.height:
        remaining = remaining.sort("date")
        if history.is_empty():
            remaining = remaining.with_columns(
                pl.lit(None, dtype=pl.Boolean).alias("st_flag")
            )
        else:
            remaining = remaining.join_asof(
                history,
                left_on="date",
                right_on="flag_date",
                by="symbol",
                strategy="backward",
                check_sortedness=False,
            )
        historical_st = remaining.filter(pl.col("st_flag").fill_null(False))
        exclusion_parts.append(
            _exclusion_rows(
                historical_st,
                "historical_st",
                "security was risk-warning status on the event date",
            )
        )
        unknown_st = remaining.filter(pl.col("st_flag").is_null())
        exclusion_parts.append(
            _exclusion_rows(
                unknown_st,
                "unknown_historical_st",
                "no effective-dated ST status is available at the event date",
            )
        )
        remaining = remaining.filter(pl.col("st_flag") == False)  # noqa: E712

    if remaining.height:
        observed_age = _observed_listing_age(daily)
        remaining = remaining.join(
            observed_age,
            on=["symbol", "date"],
            how="left",
        ).sort(["date", "symbol"])
        listing_dates = _instrument_listing_dates(instruments)
        ages, sources = _listing_ages(
            remaining,
            trading_sessions,
            listing_dates,
        )
        remaining = remaining.with_columns(
            pl.Series("listed_trading_days", ages, dtype=pl.Int64),
            pl.Series("listing_age_source", sources, dtype=pl.String),
        )
        insufficient = remaining.filter(pl.col("listed_trading_days") < 20)
        exclusion_parts.append(
            _exclusion_rows(
                insufficient,
                "insufficient_listing_history",
                "fewer than 20 trading sessions are observable since listing",
            )
        )
        remaining = remaining.filter(pl.col("listed_trading_days") >= 20)

    if remaining.height:
        not_first = remaining.filter(pl.col("consecutive_limit_ups") != 1)
        exclusion_parts.append(
            _exclusion_rows(
                not_first,
                "not_first_board",
                "consecutive_limit_ups is not equal to one",
            )
        )
        remaining = remaining.filter(pl.col("consecutive_limit_ups") == 1)

    if remaining.height:
        complete_prices = (
            _positive_price("close")
            & _positive_price("high")
            & _positive_price("low")
            & _positive_price("raw_close")
            & _positive_price("raw_high")
            & _positive_price("raw_low")
        )
        incomplete = remaining.filter(~complete_prices)
        exclusion_parts.append(
            _exclusion_rows(
                incomplete,
                "incomplete_price_mapping",
                "raw and adjusted event OHLC values are not all positive",
            )
        )
        remaining = remaining.filter(complete_prices)

    events = remaining.select(
        _event_id().alias("event_id"),
        pl.col("symbol"),
        pl.col("date").alias("event_date"),
        pl.col("raw_close").alias("t_close_raw"),
        pl.col("close").alias("t_close_adj"),
        pl.col("raw_high").alias("t_high_raw"),
        pl.col("high").alias("t_high_adj"),
        pl.col("raw_low").alias("t_low_raw"),
        pl.col("low").alias("t_low_adj"),
        pl.col("consecutive_limit_ups"),
        pl.col("st_flag").alias("is_st_at_event"),
        pl.col("listed_trading_days"),
        pl.lit("main_board").alias("board"),
        pl.lit("main_board_10pct").alias("price_limit_rule"),
        pl.lit(MAIN_BOARD_LIMIT, dtype=pl.Float64).alias("price_limit_pct"),
        pl.col("listing_age_source"),
    ).sort(["event_date", "symbol"])

    exclusions = (
        pl.concat(exclusion_parts, how="vertical")
        if exclusion_parts
        else pl.DataFrame(schema=_EXCLUSION_SCHEMA)
    ).sort(["event_date", "symbol", "reason"])
    return events, exclusions


def sample_events_monthly(
    events: pl.DataFrame,
    max_per_month: int | None,
    *,
    seed: int,
) -> pl.DataFrame:
    """Select a deterministic event-level sample for bounded pilot runs."""
    if max_per_month is None or events.is_empty():
        return events
    if max_per_month < 1:
        raise ValueError("max_per_month must be positive")
    grouped = (
        events.with_columns(
            pl.col("event_date")
            .dt.strftime("%Y-%m")
            .alias("_month")
        )
        .group_by("_month", maintain_order=True)
        .agg(pl.col("event_id").sort().alias("_event_ids"))
        .sort("_month")
    )
    rng = random.Random(seed)
    selected: list[str] = []
    for row in grouped.iter_rows(named=True):
        event_ids = row["_event_ids"]
        if len(event_ids) <= max_per_month:
            selected.extend(event_ids)
        else:
            selected.extend(
                sorted(rng.sample(event_ids, max_per_month))
            )
    return events.filter(
        pl.col("event_id").is_in(selected)
    ).sort(["event_date", "symbol"])
