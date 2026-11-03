"""Standard-data adapters and canonical minute-bar normalization."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, time
from pathlib import Path
from typing import Protocol

import polars as pl

from app.price_limits import polars_limit_price
from app.services.minute_adjust import compute_ratio_pairs, minute_basis_is_raw
from app.tickflow.repository import DataStore, KlineRepository

MINUTE_COLUMNS = [
    "symbol",
    "datetime",
    "bar_start",
    "bar_end",
    "volume",
    "open_raw",
    "high_raw",
    "low_raw",
    "close_raw",
    "amount_raw",
    "open_adj",
    "high_adj",
    "low_adj",
    "close_adj",
    "amount_adj",
]

DAILY_COLUMNS = [
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "raw_close",
    "raw_high",
    "raw_low",
    "limit_up_price",
    "limit_down_price",
    "consecutive_limit_ups",
]

_MINUTE_PRICE_COLUMNS = ("open", "high", "low", "close", "amount")
_EXPECTED_SESSION_BAR_ENDS = frozenset(
    [
        *(time(hour, minute) for hour in (9, 10) for minute in range(60)
          if not (hour == 9 and minute < 31)),
        *(time(11, minute) for minute in range(31)),
        *(time(13, minute) for minute in range(1, 60)),
        *(time(14, minute) for minute in range(60)),
        time(15, 0),
    ]
)
_DAILY_REQUIRED = {
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "raw_close",
    "raw_high",
    "raw_low",
    "consecutive_limit_ups",
}


class MarketDataSource(Protocol):
    def trading_dates(self, start: date, end: date) -> list[date]: ...

    def instruments(self) -> pl.DataFrame: ...

    def st_history(self) -> pl.DataFrame: ...

    def universe_symbols(self, start: date, end: date) -> list[str]: ...

    def daily_batch(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pl.DataFrame: ...

    def minute_batch(
        self,
        symbols: list[str],
        dates: list[date],
    ) -> pl.DataFrame: ...

    def data_generation(self) -> str: ...


def _empty_minute_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "symbol": pl.String,
            "datetime": pl.Datetime,
            "bar_start": pl.Datetime,
            "bar_end": pl.Datetime,
            "volume": pl.Float64,
            "open_raw": pl.Float64,
            "high_raw": pl.Float64,
            "low_raw": pl.Float64,
            "close_raw": pl.Float64,
            "amount_raw": pl.Float64,
            "open_adj": pl.Float64,
            "high_adj": pl.Float64,
            "low_adj": pl.Float64,
            "close_adj": pl.Float64,
            "amount_adj": pl.Float64,
        }
    )


def canonicalize_minute_bars(
    frame: pl.DataFrame,
    ratios: pl.DataFrame,
) -> pl.DataFrame:
    """Map repository-adjusted minute prices back to paired raw/adj prices.

    Repository minute reads are adjusted projections. The stored raw price is
    recovered by dividing that projection by the per-symbol/day ratio.
    """
    if frame.is_empty():
        return _empty_minute_frame()

    required = {
        "symbol",
        "datetime",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            f"minute frame missing required columns: {sorted(missing)}"
        )
    if not {"symbol", "_d", "_ratio"}.issubset(ratios.columns):
        raise ValueError("ratios must contain symbol, _d and _ratio")

    datetime_dtype = frame.schema["datetime"]
    if (
        isinstance(datetime_dtype, pl.Datetime)
        and datetime_dtype.time_zone is not None
    ):
        raise ValueError("minute datetime must be naive Beijing wall-clock time")

    ratio_counts = ratios.group_by(["symbol", "_d"]).len()
    if ratio_counts.filter(pl.col("len") > 1).height:
        raise ValueError("ratios must be unique by symbol and date")
    clean_ratios = ratios.select(
        "symbol",
        pl.col("_d").cast(pl.Date),
        pl.col("_ratio").cast(pl.Float64),
    )

    joined = frame.with_columns(
        pl.col("datetime").alias("bar_end"),
        (pl.col("datetime") - pl.duration(minutes=1)).alias("bar_start"),
        pl.col("datetime").dt.date().alias("_d"),
    ).join(clean_ratios, on=["symbol", "_d"], how="left")
    if joined.filter(
        pl.col("_ratio").is_not_null()
        & pl.col("_ratio").is_finite()
        & (pl.col("_ratio") > 0)
    ).height != frame.height:
        raise ValueError("missing or invalid adjustment ratio for minute bar")

    canonical = (
        joined.filter(
            pl.col("_ratio").is_not_null()
            & pl.col("_ratio").is_finite()
            & (pl.col("_ratio") > 0)
            & pl.col("bar_end").dt.time().is_in(
                list(_EXPECTED_SESSION_BAR_ENDS)
            )
        )
        .with_columns(
            [
                pl.col(name).alias(f"{name}_adj")
                for name in _MINUTE_PRICE_COLUMNS
            ]
        )
        .with_columns(
            [
                (pl.col(f"{name}_adj") / pl.col("_ratio")).alias(
                    f"{name}_raw"
                )
                for name in _MINUTE_PRICE_COLUMNS
            ]
        )
    )
    return canonical.select(MINUTE_COLUMNS).sort(["symbol", "bar_end"])


def canonicalize_raw_minute_bars(
    frame: pl.DataFrame,
    ratios: pl.DataFrame,
) -> pl.DataFrame:
    """Build paired raw/adjusted bars from raw date partitions."""
    if frame.is_empty():
        return _empty_minute_frame()

    required = {
        "symbol",
        "datetime",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            f"raw minute frame missing required columns: {sorted(missing)}"
        )
    if not {"symbol", "_d", "_ratio"}.issubset(ratios.columns):
        raise ValueError("ratios must contain symbol, _d and _ratio")

    ratio_counts = ratios.group_by(["symbol", "_d"]).len()
    if ratio_counts.filter(pl.col("len") > 1).height:
        raise ValueError("ratios must be unique by symbol and date")
    clean_ratios = ratios.select(
        "symbol",
        pl.col("_d").cast(pl.Date),
        pl.col("_ratio").cast(pl.Float64),
    )
    joined = frame.with_columns(
        pl.col("datetime").alias("bar_end"),
        (pl.col("datetime") - pl.duration(minutes=1)).alias("bar_start"),
        pl.col("datetime").dt.date().alias("_d"),
        pl.col("open").alias("open_raw"),
        pl.col("high").alias("high_raw"),
        pl.col("low").alias("low_raw"),
        pl.col("close").alias("close_raw"),
        pl.col("amount").alias("amount_raw"),
    ).join(clean_ratios, on=["symbol", "_d"], how="left")
    if joined.filter(
        pl.col("_ratio").is_not_null()
        & pl.col("_ratio").is_finite()
        & (pl.col("_ratio") > 0)
    ).height != frame.height:
        raise ValueError("missing or invalid adjustment ratio for minute bar")
    canonical = (
        joined.filter(
            pl.col("_ratio").is_not_null()
            & pl.col("_ratio").is_finite()
            & (pl.col("_ratio") > 0)
            & pl.col("bar_end").dt.time().is_in(
                list(_EXPECTED_SESSION_BAR_ENDS)
            )
        ).with_columns(
            (pl.col("open_raw") * pl.col("_ratio")).alias("open_adj"),
            (pl.col("high_raw") * pl.col("_ratio")).alias("high_adj"),
            (pl.col("low_raw") * pl.col("_ratio")).alias("low_adj"),
            (pl.col("close_raw") * pl.col("_ratio")).alias("close_adj"),
            (pl.col("amount_raw") * pl.col("_ratio")).alias("amount_adj"),
        )
    )
    return canonical.select(MINUTE_COLUMNS).sort(["symbol", "bar_end"])


def prepare_daily_context(daily: pl.DataFrame) -> pl.DataFrame:
    """Validate daily rows and derive main-board limit prices."""
    missing = _DAILY_REQUIRED - set(daily.columns)
    if missing:
        raise ValueError(
            f"daily data missing required columns: {sorted(missing)}"
        )
    if daily.select("symbol", "date").is_duplicated().any():
        raise ValueError("daily data contains duplicate symbol/date rows")
    previous = pl.col("raw_close").shift(1).over("symbol")
    return daily.sort(["symbol", "date"]).with_columns(
        polars_limit_price(
            previous,
            pl.lit(0.10),
            up=True,
        ).alias("limit_up_price"),
        polars_limit_price(
            previous,
            pl.lit(0.10),
            up=False,
        ).alias("limit_down_price"),
    )


def enrich_daily_factors(daily: pl.DataFrame) -> pl.DataFrame:
    """Add point-in-time T-day features from the standard daily panel."""
    missing = {
        "symbol",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "raw_close",
        "raw_high",
        "raw_low",
    } - set(daily.columns)
    if missing:
        raise ValueError(
            f"daily data missing factor inputs: {sorted(missing)}"
        )
    frame = daily.sort(["symbol", "date"])
    previous_close = pl.col("raw_close").shift(1).over("symbol")
    ret_1d = pl.col("close") / pl.col("close").shift(1).over("symbol") - 1.0
    expressions = {
        "daily__ret_1d": ret_1d,
        "daily__ret_3d": (
            pl.col("close") / pl.col("close").shift(3).over("symbol") - 1.0
        ),
        "daily__ret_5d": (
            pl.col("close") / pl.col("close").shift(5).over("symbol") - 1.0
        ),
        "daily__ret_10d": (
            pl.col("close") / pl.col("close").shift(10).over("symbol") - 1.0
        ),
        "daily__ret_20d": (
            pl.col("close") / pl.col("close").shift(20).over("symbol") - 1.0
        ),
        "daily__ret_60d": (
            pl.col("close") / pl.col("close").shift(60).over("symbol") - 1.0
        ),
        "daily__close_ma5_ratio": (
            pl.col("close")
            / pl.col("close")
            .rolling_mean(5, min_samples=5)
            .over("symbol")
            - 1.0
        ),
        "daily__close_ma10_ratio": (
            pl.col("close")
            / pl.col("close")
            .rolling_mean(10, min_samples=10)
            .over("symbol")
            - 1.0
        ),
        "daily__close_ma20_ratio": (
            pl.col("close")
            / pl.col("close")
            .rolling_mean(20, min_samples=20)
            .over("symbol")
            - 1.0
        ),
        "daily__close_ma60_ratio": (
            pl.col("close")
            / pl.col("close")
            .rolling_mean(60, min_samples=60)
            .over("symbol")
            - 1.0
        ),
        "daily__volatility_20": (
            ret_1d.rolling_std(20, min_samples=20).over("symbol")
        ),
        "daily__range_pct": (
            (pl.col("raw_high") - pl.col("raw_low")) / previous_close
        ),
        "daily__close_location": (
            (pl.col("raw_close") - pl.col("raw_low"))
            / (pl.col("raw_high") - pl.col("raw_low"))
        ),
        "daily__volume_ratio_5_20": (
            pl.col("volume")
            .rolling_mean(5, min_samples=5)
            .over("symbol")
            / pl.col("volume")
            .rolling_mean(20, min_samples=20)
            .over("symbol")
        ),
        "daily__amount_log": pl.col("amount").log1p(),
        "daily__volume": pl.col("volume").cast(pl.Float64),
        "daily__price_position_60": (
            (pl.col("raw_close") - pl.col("raw_low").rolling_min(60).over("symbol"))
            / (
                pl.col("raw_high").rolling_max(60).over("symbol")
                - pl.col("raw_low").rolling_min(60).over("symbol")
            )
        ),
        "daily__drawdown_60": (
            pl.col("raw_close")
            / pl.col("raw_high").rolling_max(60).over("symbol")
            - 1.0
        ),
    }
    if "turnover_rate" in frame.columns:
        expressions["daily__turnover_rate"] = pl.col(
            "turnover_rate"
        ).cast(pl.Float64)
    enriched = frame.with_columns(
        [
            expression.alias(name)
            for name, expression in expressions.items()
        ]
    )
    enriched = enriched.with_columns(
        [
            pl.when(value.is_not_null() & value.is_finite())
            .then(value)
            .otherwise(None)
            .alias(name)
            for name in expressions
            for value in [pl.col(name)]
        ]
    )
    market_expressions = {
        "market__median_ret_1d": (
            pl.col("daily__ret_1d").median().over("date")
        ),
        "market__median_ret_20d": (
            pl.col("daily__ret_20d").median().over("date")
        ),
        "market__up_ratio": (
            (pl.col("daily__ret_1d") > 0).mean().over("date")
        ),
        "market__above_ma20_ratio": (
            (pl.col("daily__close_ma20_ratio") > 0).mean().over("date")
        ),
        "market__return_dispersion": (
            pl.col("daily__ret_1d").std().over("date")
        ),
    }
    if {
        "raw_close",
        "limit_up_price",
        "limit_down_price",
    }.issubset(enriched.columns):
        market_expressions.update(
            {
                "market__limit_up_ratio": (
                    (
                        pl.col("raw_close")
                        >= pl.col("limit_up_price") - 0.005
                    )
                    .mean()
                    .over("date")
                ),
                "market__limit_down_ratio": (
                    (
                        pl.col("raw_close")
                        <= pl.col("limit_down_price") + 0.005
                    )
                    .mean()
                    .over("date")
                ),
            }
        )
    return enriched.with_columns(
        [
            expression.alias(name)
            for name, expression in market_expressions.items()
        ]
    )


def build_event_factor_frame(
    daily: pl.DataFrame,
    events: pl.DataFrame,
) -> pl.DataFrame:
    """Join T-day factors to events without using future daily rows."""
    factor_columns = [
        column
        for column in daily.columns
        if column.startswith(("daily__", "linkage__", "market__"))
    ]
    if not factor_columns:
        raise ValueError("daily factor columns are required")
    event_keys = events.select("event_id", "symbol", "event_date")
    joined = event_keys.join(
        daily.select(
            "symbol",
            pl.col("date").alias("event_date"),
            *factor_columns,
        ),
        on=["symbol", "event_date"],
        how="left",
        validate="1:1",
    )
    if joined.height != events.height:
        raise ValueError("event factor join changed event count")
    return joined


def validate_minute_layout(
    frame: pl.DataFrame,
    expected_pairs: set[tuple[str, date]],
) -> pl.DataFrame:
    """Report complete, partial and missing minute partitions without filling."""
    schema = {
        "date": pl.Date,
        "symbol": pl.String,
        "expected_bars": pl.Int64,
        "actual_bars": pl.Int64,
        "status": pl.String,
        "missing_first": pl.Boolean,
        "missing_last": pl.Boolean,
    }
    if not expected_pairs:
        return pl.DataFrame(schema=schema)

    if frame.is_empty():
        actual = pl.DataFrame(
            schema={
                "symbol": pl.String,
                "date": pl.Date,
                "actual_bars": pl.Int64,
                "actual_rows": pl.Int64,
                "first_bar": pl.Time,
                "last_bar": pl.Time,
                "_bar_times": pl.List(pl.Time),
            }
        )
    else:
        required = {"symbol", "bar_end"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(
                f"canonical minute frame missing columns: {sorted(missing)}"
            )
        actual = (
            frame.with_columns(
                pl.col("bar_end").dt.date().alias("date"),
                pl.col("bar_end").dt.time().alias("_bar_time"),
            )
            .group_by(["symbol", "date"])
            .agg(
                pl.col("_bar_time").n_unique().cast(pl.Int64).alias("actual_bars"),
                pl.len().cast(pl.Int64).alias("actual_rows"),
                pl.col("_bar_time").min().alias("first_bar"),
                pl.col("_bar_time").max().alias("last_bar"),
                pl.col("_bar_time").alias("_bar_times"),
            )
        )

    expected = pl.DataFrame(
        {
            "symbol": [symbol for symbol, _ in sorted(expected_pairs)],
            "date": [day for _, day in sorted(expected_pairs)],
        },
        schema={"symbol": pl.String, "date": pl.Date},
    )
    joined = (
        expected.join(actual, on=["symbol", "date"], how="left")
        .with_columns(
            pl.lit(len(_EXPECTED_SESSION_BAR_ENDS), dtype=pl.Int64).alias(
                "expected_bars"
            ),
            pl.col("actual_bars").fill_null(0),
            pl.col("actual_rows").fill_null(0),
        )
    )
    rows: list[dict[str, object]] = []
    expected_slots = set(_EXPECTED_SESSION_BAR_ENDS)
    for row in joined.iter_rows(named=True):
        bar_times = row["_bar_times"] or []
        observed = set(bar_times)
        missing_slots = expected_slots - observed
        extra_slots = observed - expected_slots
        if row["actual_rows"] == 0:
            status = "missing"
        elif row["actual_rows"] != len(observed) or extra_slots:
            status = "invalid"
        elif not missing_slots:
            status = "complete"
        else:
            status = "partial"
        rows.append(
            {
                "date": row["date"],
                "symbol": row["symbol"],
                "expected_bars": row["expected_bars"],
                "actual_bars": row["actual_bars"],
                "status": status,
                "missing_first": time(9, 31) in missing_slots,
                "missing_last": time(15, 0) in missing_slots,
            }
        )
    return pl.DataFrame(rows, schema=schema).sort(["date", "symbol"])


class RepositoryDataSource:
    """Read-only standard data source backed by DataStore and KlineRepository."""

    def __init__(
        self,
        data_dir: Path,
        *,
        minute_cache_days: int = 40,
    ) -> None:
        if minute_cache_days < 1:
            raise ValueError("minute_cache_days must be positive")
        self.data_dir = Path(data_dir)
        self.store = DataStore(self.data_dir)
        self.repo = KlineRepository(self.store)
        self.minute_cache_days = minute_cache_days
        self._minute_cache: OrderedDict[
            date,
            tuple[pl.DataFrame, dict[str, tuple[int, int]]],
        ] = OrderedDict()

    def trading_dates(self, start: date, end: date) -> list[date]:
        return self.repo.list_enriched_dates(start, end, asset_type="stock")

    def instruments(self) -> pl.DataFrame:
        return self.repo.get_instruments()

    def st_history(self) -> pl.DataFrame:
        return self.repo.get_st_history()

    def universe_symbols(self, start: date, end: date) -> list[str]:
        rows = self.repo.execute_all(
            """
            SELECT DISTINCT symbol
            FROM kline_daily
            WHERE date >= ? AND date <= ?
            ORDER BY symbol
            """,
            [start, end],
        )
        return [str(row[0]) for row in rows if row and row[0]]

    def daily_batch(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pl.DataFrame:
        daily = self.repo.get_daily_batch(
            symbols,
            start,
            end,
            columns=DAILY_COLUMNS,
        )
        if _DAILY_REQUIRED - set(daily.columns):
            daily = self.repo._scan_daily_batch(
                symbols,
                start,
                end,
                None,
            )
        daily = prepare_daily_context(daily)
        daily = enrich_daily_factors(daily)
        linkage = self._linkage_batch(symbols, start, end)
        if linkage.is_empty():
            return daily
        return daily.join(
            linkage,
            on=["symbol", "date"],
            how="left",
        )

    def _linkage_batch(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> pl.DataFrame:
        root = self.data_dir / "kline_daily_linkage"
        if not root.is_dir():
            return pl.DataFrame(
                schema={"symbol": pl.String, "date": pl.Date}
            )
        files = [
            str(path)
            for path in sorted(root.glob("date=*/*.parquet"))
            if start <= date.fromisoformat(path.parent.name[5:]) <= end
        ]
        if not files:
            return pl.DataFrame(
                schema={"symbol": pl.String, "date": pl.Date}
            )
        frame = pl.read_parquet(files)
        if not {"symbol", "date"}.issubset(frame.columns):
            raise ValueError("linkage factors require symbol and date")
        frame = frame.filter(
            pl.col("symbol").is_in(symbols)
            & pl.col("date").is_between(start, end)
        )
        rename = {
            column: f"linkage__{column}"
            for column in frame.columns
            if column not in {"symbol", "date"}
        }
        return frame.rename(rename)

    def minute_batch(
        self,
        symbols: list[str],
        dates: list[date],
    ) -> pl.DataFrame:
        if not minute_basis_is_raw(self.data_dir):
            raise RuntimeError(
                "raw minute basis is required before first-board research"
            )
        if not symbols or not dates:
            return _empty_minute_frame()
        frames: list[pl.DataFrame] = []
        for day in sorted(set(dates)):
            partition = self._minute_partition(day)
            if partition is None:
                continue
            frame, spans = partition
            for symbol in sorted(set(symbols)):
                span = spans.get(symbol)
                if span is not None:
                    frames.append(frame.slice(span[0], span[1] - span[0]))
        if not frames:
            return _empty_minute_frame()
        raw = pl.concat(frames, how="vertical_relaxed")
        ratios = compute_ratio_pairs(
            raw,
            self.data_dir,
            asset_type="stock",
        )
        return canonicalize_raw_minute_bars(raw, ratios)

    def _minute_partition(
        self,
        day: date,
    ) -> tuple[pl.DataFrame, dict[str, tuple[int, int]]] | None:
        cached = self._minute_cache.get(day)
        if cached is not None:
            self._minute_cache.move_to_end(day)
            return cached
        path = (
            self.data_dir
            / "kline_minute"
            / f"date={day.isoformat()}"
            / "part.parquet"
        )
        if not path.is_file():
            return None
        frame = pl.read_parquet(path).sort(["symbol", "datetime"])
        if frame.is_empty():
            return None
        missing = {
            "symbol",
            "datetime",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
        } - set(frame.columns)
        if missing:
            raise ValueError(
                f"minute partition missing columns: {sorted(missing)}"
            )
        bounds = (
            frame.with_row_index("_row")
            .group_by("symbol")
            .agg(
                pl.col("_row").min().alias("_start"),
                (pl.col("_row").max() + 1).alias("_end"),
            )
        )
        spans = {
            row["symbol"]: (int(row["_start"]), int(row["_end"]))
            for row in bounds.iter_rows(named=True)
        }
        entry = (frame, spans)
        self._minute_cache[day] = entry
        while len(self._minute_cache) > self.minute_cache_days:
            self._minute_cache.popitem(last=False)
        return entry

    def data_generation(self) -> str:
        return self.repo.get_matrix_data_generation("stock")
