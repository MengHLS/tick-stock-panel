"""Derive completed limit-board events from the local one-minute K store."""

from __future__ import annotations

import bisect
import re
from datetime import date, datetime, time
from pathlib import Path

import polars as pl

from app.data_providers.st_history import load_st_history
from app.market_time import CN_TZ, cn_now
from app.parquet import scan_daily_parquet, scan_parquet_compat
from app.price_limits import (
    GEM_REGISTRATION_DATE,
    LEGACY_MAIN_BOARD_ST_LIMIT,
    MAIN_BOARD_LIMIT,
    is_no_limit_day,
    parse_listing_date,
    polars_limit_price,
    polars_price_limit_pct,
)
from app.services.minute_adjust import minute_basis_is_raw

_SYMBOL = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")
_FULL_DAY_BARS = 241
_MINUTE_COLUMNS = ["symbol", "datetime", "open", "high", "low", "close", "amount"]


def list_minute_partitions(data_dir: Path, start: date, end: date) -> list[date]:
    """Return existing stock-minute partition dates in ascending order."""
    root = Path(data_dir) / "kline_minute"
    if not root.is_dir():
        return []
    dates = []
    for path in root.glob("date=*/part.parquet"):
        try:
            day = date.fromisoformat(path.parent.name[5:])
        except ValueError:
            continue
        if start <= day <= end:
            dates.append(day)
    return sorted(dates)


def _nearest_partition_date(root: Path, before: date) -> date | None:
    if not root.is_dir():
        return None
    dates = []
    for path in root.glob("date=*"):
        try:
            day = date.fromisoformat(path.name[5:])
        except ValueError:
            continue
        if day < before:
            dates.append(day)
    return max(dates, default=None)


def _read_daily_close(path: Path) -> pl.DataFrame:
    files = sorted(path.glob("*.parquet"))
    if not files:
        return pl.DataFrame(schema={"symbol": pl.String, "close": pl.Float64})
    return (
        scan_daily_parquet([str(file) for file in files])
        .select("symbol", "close")
        .collect()
        .unique(subset=["symbol"], keep="last")
    )


def _previous_closes(data_dir: Path, day: date) -> pl.DataFrame:
    """Load dated daily/minute closes so the newer usable source can win."""
    empty = pl.DataFrame(
        schema={
            "symbol": pl.String,
            "daily_prev_close": pl.Float64,
            "minute_prev_close": pl.Float64,
            "_daily_date": pl.Date,
            "_minute_date": pl.Date,
        }
    )
    daily_day = _nearest_partition_date(data_dir / "kline_daily", day)
    minute_day = _nearest_partition_date(data_dir / "kline_minute", day)
    if daily_day is not None:
        daily = (
            _read_daily_close(data_dir / "kline_daily" / f"date={daily_day}")
            .rename({"close": "daily_prev_close"})
            .with_columns(pl.lit(daily_day, dtype=pl.Date).alias("_daily_date"))
        )
    else:
        daily = empty.select("symbol", "daily_prev_close", "_daily_date")
    minute = empty.select("symbol", "minute_prev_close", "_minute_date")
    if minute_day is not None:
        path = data_dir / "kline_minute" / f"date={minute_day}" / "part.parquet"
        if path.exists():
            minute = (
                pl.scan_parquet(str(path))
                .select("symbol", "datetime", "close")
                .group_by("symbol")
                .agg(
                    pl.col("close").sort_by(pl.col("datetime")).last().alias("minute_prev_close"),
                    pl.col("datetime").max().alias("_last"),
                )
                .filter(pl.col("_last").dt.time() == time(15))
                .drop("_last")
                .collect()
                .with_columns(pl.lit(minute_day, dtype=pl.Date).alias("_minute_date"))
            )
    return daily.join(minute, on="symbol", how="full", coalesce=True)


def _load_instruments(data_dir: Path) -> pl.DataFrame:
    files = sorted((data_dir / "instruments").rglob("*.parquet"))
    if not files:
        return pl.DataFrame(schema={"symbol": pl.String, "listing_date": pl.String})
    frame = scan_parquet_compat([str(path) for path in files]).collect()
    if "listing_date" not in frame.columns:
        frame = frame.with_columns(pl.lit(None).cast(pl.String).alias("listing_date"))
    return frame.select(
        pl.col("symbol").cast(pl.String),
        pl.col("listing_date").cast(pl.String, strict=False),
    ).unique(subset=["symbol"], keep="last")


def _load_adj_factors(data_dir: Path, day: date) -> pl.DataFrame:
    files = sorted((data_dir / "adj_factor").rglob("*.parquet"))
    if not files:
        return pl.DataFrame(
            schema={
                "symbol": pl.String,
                "ex_factor": pl.Float64,
                "_has_adj_factor": pl.Boolean,
            }
        )
    return (
        pl.scan_parquet([str(path) for path in files])
        .filter(pl.col("trade_date") == day)
        .select(
            "symbol",
            "ex_factor",
            pl.lit(True).alias("_has_adj_factor"),
        )
        .collect()
        .unique(subset=["symbol"], keep="last")
    )


def _no_limit_days(
    frame: pl.DataFrame,
    day: date,
    minute_dates: list[date],
) -> list[bool | None]:
    current_index = bisect.bisect_left(minute_dates, day)
    result = []
    for symbol, raw_listing in zip(
        frame["symbol"].to_list(),
        frame["listing_date"].to_list(),
        strict=True,
    ):
        listing = parse_listing_date(raw_listing)
        if listing is None or listing > day:
            result.append(None)
            continue
        first_index = bisect.bisect_left(minute_dates, listing)
        rank = current_index - first_index + 1 if first_index <= current_index else None
        result.append(is_no_limit_day(symbol, listing, day, day_rank=rank))
    return result


def _validate_bars(frame: pl.DataFrame, day: date) -> None:
    if frame.is_empty():
        return
    bad_symbol = (
        frame["symbol"].null_count()
        or frame.filter(~pl.col("symbol").str.contains(_SYMBOL.pattern)).height
    )
    if bad_symbol:
        raise ValueError("Minute partition contains an invalid symbol")
    if frame.select(
        pl.col("datetime").is_null().any()
        | (pl.col("datetime").dt.date() != day).any()
        | pl.col("high").is_null().any()
        | pl.col("low").is_null().any()
        | pl.col("close").is_null().any()
        | pl.col("amount").is_null().any()
        | (pl.col("high") <= 0).any()
        | (pl.col("low") <= 0).any()
        | (pl.col("close") <= 0).any()
        | (pl.col("amount") < 0).any()
        | ~pl.col("high").is_finite().all()
        | ~pl.col("low").is_finite().all()
        | ~pl.col("close").is_finite().all()
        | ~pl.col("amount").is_finite().all()
        | (pl.col("high") < pl.col("low")).any()
        | (pl.col("high") < pl.col("close")).any()
        | (pl.col("low") > pl.col("close")).any()
        | (
            (pl.col("datetime").dt.time() < time(9, 30))
            | (pl.col("datetime").dt.time() > time(15))
            | (
                (pl.col("datetime").dt.time() > time(11, 30))
                & (pl.col("datetime").dt.time() < time(13, 1))
            )
        ).any()
    ).item():
        raise ValueError("Minute partition contains invalid bars")
    if frame.select(pl.struct("symbol", "datetime").is_duplicated().any()).item():
        raise ValueError("Minute partition contains duplicate symbol/datetime rows")


def _normalize_minute_sessions(frame: pl.DataFrame, day: date) -> pl.DataFrame:
    """Select complete sessions and normalize TdxQuant's 240-bar layout.

    TdxQuant returns 09:31-15:00. Its 09:31 bar includes the opening-auction
    price in ``open`` and the auction turnover in the bar totals. Add an
    in-memory 09:30 sentinel with that price and zero incremental turnover so
    seal state is exact without double-counting amount. The stored partition
    remains unchanged.
    """
    endpoints = frame.group_by("symbol").agg(
        pl.col("datetime").n_unique().alias("_bars"),
        pl.col("datetime").min().alias("_first"),
        pl.col("datetime").max().alias("_last"),
    )
    full = endpoints.filter(
        (pl.col("_bars") == _FULL_DAY_BARS)
        & (pl.col("_first") == datetime.combine(day, time(9, 30)))
        & (pl.col("_last") == datetime.combine(day, time(15)))
    ).select("symbol")
    tdx = endpoints.filter(
        (pl.col("_bars") == _FULL_DAY_BARS - 1)
        & (pl.col("_first") == datetime.combine(day, time(9, 31)))
        & (pl.col("_last") == datetime.combine(day, time(15)))
    ).select("symbol")

    full_bars = frame.join(full, on="symbol", how="inner")
    tdx_bars = frame.join(tdx, on="symbol", how="inner")
    first_open = (
        tdx_bars.filter(pl.col("datetime") == datetime.combine(day, time(9, 31)))
        .select(
            "symbol",
            pl.col("open").alias("_auction_open"),
        )
        .filter(
            pl.col("_auction_open").is_not_null()
            & (pl.col("_auction_open") > 0)
            & pl.col("_auction_open").is_finite()
        )
    )
    tdx_bars = tdx_bars.join(first_open, on="symbol", how="inner")
    synthetic = first_open.select(
        "symbol",
        pl.lit(datetime.combine(day, time(9, 30))).alias("datetime"),
        pl.col("_auction_open").alias("open"),
        pl.col("_auction_open").alias("high"),
        pl.col("_auction_open").alias("low"),
        pl.col("_auction_open").alias("close"),
        pl.lit(0.0).alias("amount"),
    )
    tdx_bars = tdx_bars.drop("_auction_open")
    return pl.concat([full_bars, tdx_bars, synthetic], how="diagonal_relaxed")


def fetch_minute_limit_board_events(
    data_dir: Path,
    day: date,
    *,
    now: datetime | None = None,
) -> list[dict]:
    """Return minute-observed seals and breaks for one completed trading day.

    A row requires at least one minute whose close is at the effective limit
    price. Merely touching the limit with a bar high is not a seal.
    """
    data_dir = Path(data_dir)
    current = now or cn_now()
    if current.tzinfo is None:
        raise ValueError("now must have an explicit timezone")
    current = current.astimezone(CN_TZ)
    path = data_dir / "kline_minute" / f"date={day}" / "part.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    if not minute_basis_is_raw(data_dir):
        raise ValueError("Minute data must use the raw basis for limit-board detection")
    bars = pl.read_parquet(path, columns=_MINUTE_COLUMNS)
    if bars.is_empty():
        return []
    _validate_bars(bars, day)
    bars = _normalize_minute_sessions(bars, day)

    endpoint = (
        bars.group_by("symbol")
        .agg(
            pl.col("datetime").n_unique().alias("_bars"),
            pl.col("datetime").min().alias("_first"),
            pl.col("datetime").max().alias("_last"),
        )
        .filter(
            (pl.col("_bars") == _FULL_DAY_BARS)
            & (pl.col("_first") == datetime.combine(day, time(9, 30)))
            & (pl.col("_last") == datetime.combine(day, time(15)))
        )
        .select("symbol")
    )
    bars = bars.join(endpoint, on="symbol", how="inner")
    if bars.is_empty():
        return []

    minute_dates = list_minute_partitions(data_dir, date.min, day)
    instruments = _load_instruments(data_dir)
    history = load_st_history(data_dir).sort(["symbol", "flag_date"])
    previous = _previous_closes(data_dir, day)
    adj = _load_adj_factors(data_dir, day)

    base = (
        bars.select("symbol")
        .unique()
        .join(instruments, on="symbol", how="left")
        .join(previous, on="symbol", how="left")
        .join(adj, on="symbol", how="left")
        .with_columns(
            pl.lit(day, dtype=pl.Date).alias("_trade_date"),
        )
        .sort(["symbol", "_trade_date"])
    )
    if history.is_empty():
        base = base.with_columns(pl.lit(None).cast(pl.Boolean).alias("st_flag"))
    else:
        base = base.join_asof(
            history,
            left_on="_trade_date",
            right_on="flag_date",
            by="symbol",
            strategy="backward",
            check_sortedness=False,
        )

    is_growth_or_star = (
        pl.col("symbol").str.starts_with("300")
        | pl.col("symbol").str.starts_with("301")
        | pl.col("symbol").str.starts_with("302")
        | pl.col("symbol").str.starts_with("688")
        | pl.col("symbol").str.starts_with("689")
    )
    is_gem = (
        pl.col("symbol").str.starts_with("300")
        | pl.col("symbol").str.starts_with("301")
        | pl.col("symbol").str.starts_with("302")
    )
    is_main_board = ~is_growth_or_star & ~pl.col("symbol").str.ends_with(".BJ")
    pre_reform_gem = is_gem & (pl.col("_trade_date") < GEM_REGISTRATION_DATE)
    st_required = is_main_board | pre_reform_gem
    daily_ok = (
        pl.col("daily_prev_close").is_not_null()
        & (pl.col("daily_prev_close") > 0)
        & pl.col("daily_prev_close").is_finite()
        & pl.col("_daily_date").is_not_null()
    )
    minute_ok = (
        pl.col("minute_prev_close").is_not_null()
        & (pl.col("minute_prev_close") > 0)
        & pl.col("minute_prev_close").is_finite()
        & pl.col("_minute_date").is_not_null()
    )
    prefer_minute = minute_ok & (~daily_ok | (pl.col("_minute_date") > pl.col("_daily_date")))
    previous_raw = (
        pl.when(prefer_minute)
        .then(pl.col("minute_prev_close"))
        .otherwise(pl.col("daily_prev_close"))
    )
    has_adj = pl.col("_has_adj_factor").fill_null(False)
    valid_ex_factor = (
        pl.col("ex_factor").is_not_null()
        & (pl.col("ex_factor") > 0)
        & pl.col("ex_factor").is_finite()
    )
    base = (
        base.with_columns(
            pl.when(st_required & pl.col("st_flag").is_null())
            .then(False)
            .otherwise(True)
            .alias("_st_known"),
            pl.Series(
                "_no_limit",
                _no_limit_days(base, day, minute_dates),
                dtype=pl.Boolean,
            ),
            previous_raw.alias("_prev_raw_close"),
            has_adj.alias("_has_adj_factor"),
            valid_ex_factor.alias("_valid_ex_factor"),
        )
        .with_columns(
            pl.when(has_adj & valid_ex_factor)
            .then(pl.col("_prev_raw_close") / pl.col("ex_factor"))
            .otherwise(pl.col("_prev_raw_close"))
            .alias("_reference_close")
        )
        .with_columns(
            pl.when(pre_reform_gem & pl.col("st_flag").fill_null(False))
            .then(LEGACY_MAIN_BOARD_ST_LIMIT)
            .when(pre_reform_gem)
            .then(MAIN_BOARD_LIMIT)
            .otherwise(
                polars_price_limit_pct(
                    pl.col("symbol"),
                    pl.col("_trade_date"),
                    pl.col("st_flag").fill_null(False),
                )
            )
            .alias("_limit_pct")
        )
        .with_columns(
            polars_limit_price(
                pl.col("_reference_close"),
                pl.col("_limit_pct"),
                up=True,
            ).alias("_limit_up_price")
        )
        .filter(
            pl.col("_st_known")
            & pl.col("_no_limit").is_not_null()
            & ~pl.col("_no_limit")
            & ~(pl.col("_has_adj_factor") & ~pl.col("_valid_ex_factor"))
            & pl.col("_reference_close").is_not_null()
            & (pl.col("_reference_close") > 0)
            & pl.col("_reference_close").is_finite()
        )
        .with_columns((pl.col("_limit_up_price") - 0.005).alias("_threshold"))
    )
    if base.is_empty():
        return []

    states = (
        bars.join(base.select("symbol", "_threshold"), on="symbol", how="inner")
        .sort(["symbol", "datetime"])
        .with_columns((pl.col("close") >= pl.col("_threshold")).alias("_sealed"))
        .with_columns(
            pl.col("_sealed").shift(1, fill_value=False).over("symbol").alias("_was_sealed")
        )
        .with_columns(
            (pl.col("_was_sealed") & ~pl.col("_sealed")).alias("_open_event"),
            (pl.col("_sealed") & ~pl.col("_was_sealed")).alias("_seal_event"),
        )
    )
    events = (
        states.group_by("symbol")
        .agg(
            pl.col("_sealed").any().alias("_ever_sealed"),
            pl.col("_sealed").sort_by(pl.col("datetime")).last().alias("_final_sealed"),
            pl.col("datetime").filter(pl.col("_sealed")).min().alias("_first_seal"),
            pl.col("datetime").filter(pl.col("_seal_event")).max().alias("_last_seal"),
            pl.col("_open_event").sum().cast(pl.Int64).alias("_open_times"),
            pl.col("amount").sum().alias("_turnover"),
        )
        .filter(pl.col("_ever_sealed"))
        .sort("symbol")
    )
    retrieved_at = current.isoformat()
    result = []
    for row in events.iter_rows(named=True):
        first_seal: datetime = row["_first_seal"]
        last_seal: datetime = row["_last_seal"]
        open_times = int(row["_open_times"] or 0)
        final_sealed = bool(row["_final_sealed"])
        result.append(
            {
                "trade_date": day.isoformat(),
                "symbol": row["symbol"],
                "name": None,
                "in_limit_up_pool": 1 if final_sealed else None,
                "in_limit_break_pool": None if final_sealed else 1,
                "observed_open": 1 if open_times > 0 else 0,
                "continue_day_cnt": None,
                "limit_up_reason": None,
                "limit_up_time": first_seal.strftime("%H:%M"),
                "limit_up_minute": first_seal.hour * 60 + first_seal.minute,
                "first_seal_time": first_seal.strftime("%H:%M"),
                "first_seal_minute": first_seal.hour * 60 + first_seal.minute,
                "last_seal_time": last_seal.strftime("%H:%M"),
                "last_seal_minute": last_seal.hour * 60 + last_seal.minute,
                "limit_up_pool_open_times": open_times if final_sealed else None,
                "break_pool_open_times": None if final_sealed else open_times,
                "seal_money": None,
                "max_seal_money": None,
                "turnover": float(row["_turnover"]),
                "turnover_ratio_pct": None,
                "up_source_ready_at": None,
                "break_source_ready_at": None,
                "retrieved_at": retrieved_at,
            }
        )
    return result
