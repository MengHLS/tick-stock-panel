from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path

import polars as pl
import pytest

from app.custom.limit_board_events.minute_adapter import fetch_minute_limit_board_events
from app.market_time import CN_TZ

DAY = date(2026, 9, 1)
PREV_DAY = date(2026, 8, 31)
NOW = datetime(2026, 10, 30, 20, tzinfo=CN_TZ)


def _session_times(day: date) -> list[datetime]:
    morning = [
        datetime.combine(day, time(9, 30)) + timedelta(minutes=index) for index in range(121)
    ]
    afternoon = [
        datetime.combine(day, time(13)) + timedelta(minutes=index) for index in range(1, 121)
    ]
    return morning + afternoon


def _bars(
    symbol: str,
    day: date,
    *,
    close: float = 10.0,
    high: float | None = None,
    low: float | None = None,
    amount: float = 100.0,
    count: int = 241,
    overrides: dict[time, tuple[float, float, float]] | None = None,
) -> list[dict]:
    result = []
    for stamp in _session_times(day)[:count]:
        row_close, row_high, row_low = (overrides or {}).get(
            stamp.time(),
            (close, high if high is not None else close, low if low is not None else close),
        )
        result.append(
            {
                "symbol": symbol,
                "datetime": stamp,
                "open": row_close,
                "high": row_high,
                "low": row_low,
                "close": row_close,
                "volume": 1.0,
                "amount": amount,
            }
        )
    return result


def _seed_market(
    root: Path,
    bars: list[dict],
    *,
    symbols: list[str],
    day: date = DAY,
    prev_day: date = PREV_DAY,
    daily_day: date | None = None,
    prev_closes: dict[str, float] | None = None,
    prev_minute_closes: dict[str, float] | None = None,
    listing_dates: dict[str, str] | None = None,
    st_flags: dict[str, bool] | None = None,
    adj_ex_factors: dict[str, float] | None = None,
    instrument_symbols: list[str] | None = None,
) -> None:
    minute_part = root / "kline_minute" / f"date={day}" / "part.parquet"
    minute_part.parent.mkdir(parents=True)
    (root / "kline_minute" / ".raw_basis").touch()
    pl.DataFrame(bars).write_parquet(minute_part)

    minute_closes = prev_minute_closes or {symbol: 10.0 for symbol in symbols}
    prev_minute = root / "kline_minute" / f"date={prev_day}" / "part.parquet"
    prev_minute.parent.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": symbols,
            "datetime": [datetime.combine(prev_day, time(15))] * len(symbols),
            "open": [minute_closes[symbol] for symbol in symbols],
            "high": [minute_closes[symbol] for symbol in symbols],
            "low": [minute_closes[symbol] for symbol in symbols],
            "close": [minute_closes[symbol] for symbol in symbols],
            "volume": [1.0] * len(symbols),
            "amount": [100.0] * len(symbols),
        }
    ).write_parquet(prev_minute)

    closes = prev_closes or {symbol: 10.0 for symbol in symbols}
    daily = pl.DataFrame(
        {
            "symbol": symbols,
            "date": [daily_day or prev_day] * len(symbols),
            "open": [closes[symbol] for symbol in symbols],
            "high": [closes[symbol] for symbol in symbols],
            "low": [closes[symbol] for symbol in symbols],
            "close": [closes[symbol] for symbol in symbols],
            "volume": [1.0] * len(symbols),
            "amount": [100.0] * len(symbols),
        }
    )
    daily_date = daily_day or prev_day
    daily_path = root / "kline_daily" / f"date={daily_date}" / "part.parquet"
    daily_path.parent.mkdir(parents=True)
    daily.write_parquet(daily_path)
    current_daily = daily.with_columns(pl.lit(day).alias("date"))
    current_path = root / "kline_daily" / f"date={day}" / "part.parquet"
    current_path.parent.mkdir(parents=True)
    current_daily.write_parquet(current_path)

    dates = listing_dates or {symbol: "2010-01-01" for symbol in symbols}
    instruments = root / "instruments" / "instruments.parquet"
    instruments.parent.mkdir(parents=True)
    instrument_rows = symbols if instrument_symbols is None else instrument_symbols
    pl.DataFrame(
        {
            "symbol": instrument_rows,
            "name": instrument_rows,
            "listing_date": [dates[symbol] for symbol in instrument_rows],
        }
    ).write_parquet(instruments)

    flags = st_flags or {symbol: False for symbol in symbols}
    st_path = root / "st_history" / "part.parquet"
    st_path.parent.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": symbols,
            "flag_date": [date(2019, 1, 1)] * len(symbols),
            "st_flag": [flags[symbol] for symbol in symbols],
        }
    ).write_parquet(st_path)

    adj_path = root / "adj_factor" / "all.parquet"
    adj_path.parent.mkdir(parents=True)
    if adj_ex_factors:
        pl.DataFrame(
            {
                "symbol": list(adj_ex_factors),
                "trade_date": [day] * len(adj_ex_factors),
                "ex_factor": list(adj_ex_factors.values()),
            }
        ).write_parquet(adj_path)
    else:
        pl.DataFrame(
            schema={
                "symbol": pl.String,
                "trade_date": pl.Date,
                "ex_factor": pl.Float64,
            }
        ).write_parquet(adj_path)


def test_minute_close_seal_creates_limit_up_row_and_leaves_unknown_fields_null(
    tmp_path: Path,
):
    symbol = "600000.SH"
    _seed_market(
        tmp_path,
        _bars(
            symbol,
            DAY,
            overrides={
                time(9, 45): (11.0, 11.0, 10.98),
            },
        ),
        symbols=[symbol],
    )
    # Replace the base bars with a sequence that remains sealed after 09:45.
    times = _session_times(DAY)
    sealed_at = times.index(datetime.combine(DAY, time(9, 45)))
    frame = pl.read_parquet(tmp_path / "kline_minute" / f"date={DAY}" / "part.parquet")
    frame = frame.with_columns(
        pl.when(pl.col("datetime") >= datetime.combine(DAY, time(9, 45)))
        .then(11.0)
        .otherwise(pl.col("close"))
        .alias("close"),
        pl.when(pl.col("datetime") >= datetime.combine(DAY, time(9, 45)))
        .then(11.0)
        .otherwise(pl.col("high"))
        .alias("high"),
        pl.when(pl.col("datetime") >= datetime.combine(DAY, time(9, 45)))
        .then(10.98)
        .otherwise(pl.col("low"))
        .alias("low"),
    )
    frame.write_parquet(tmp_path / "kline_minute" / f"date={DAY}" / "part.parquet")

    rows = fetch_minute_limit_board_events(tmp_path, DAY, now=NOW)

    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == symbol
    assert row["in_limit_up_pool"] == 1
    assert row["in_limit_break_pool"] is None
    assert row["observed_open"] == 0
    assert row["limit_up_time"] == "09:45"
    assert row["first_seal_time"] == "09:45"
    assert row["last_seal_time"] == "09:45"
    assert row["last_seal_minute"] == 585
    assert row["limit_up_minute"] == sealed_at + 9 * 60 + 30
    assert row["limit_up_pool_open_times"] == 0
    assert row["break_pool_open_times"] is None
    assert row["turnover"] == 24100.0
    assert row["name"] is None
    assert row["continue_day_cnt"] is None
    assert row["limit_up_reason"] is None
    assert row["seal_money"] is None
    assert row["max_seal_money"] is None
    assert row["turnover_ratio_pct"] is None
    assert row["up_source_ready_at"] is None
    assert row["break_source_ready_at"] is None


def test_minute_open_after_seal_creates_broken_board_row(tmp_path: Path):
    symbol = "000001.SZ"
    _seed_market(
        tmp_path,
        _bars(symbol, DAY, close=10.0),
        symbols=[symbol],
    )
    frame = pl.read_parquet(tmp_path / "kline_minute" / f"date={DAY}" / "part.parquet")
    frame = frame.with_columns(
        pl.when(pl.col("datetime") >= datetime.combine(DAY, time(9, 45)))
        .then(11.0)
        .otherwise(pl.col("close"))
        .alias("close"),
        pl.when(pl.col("datetime") >= datetime.combine(DAY, time(9, 45)))
        .then(11.0)
        .otherwise(pl.col("high"))
        .alias("high"),
        pl.when(pl.col("datetime") >= datetime.combine(DAY, time(10)))
        .then(10.6)
        .otherwise(pl.col("low"))
        .alias("low"),
    ).with_columns(
        pl.when(pl.col("datetime") >= datetime.combine(DAY, time(10)))
        .then(10.6)
        .otherwise(pl.col("close"))
        .alias("close"),
        pl.when(pl.col("datetime") >= datetime.combine(DAY, time(10)))
        .then(10.6)
        .otherwise(pl.col("high"))
        .alias("high"),
    )
    frame.write_parquet(tmp_path / "kline_minute" / f"date={DAY}" / "part.parquet")

    rows = fetch_minute_limit_board_events(tmp_path, DAY, now=NOW)

    assert len(rows) == 1
    row = rows[0]
    assert row["in_limit_up_pool"] is None
    assert row["in_limit_break_pool"] == 1
    assert row["observed_open"] == 1
    assert row["first_seal_time"] == "09:45"
    assert row["last_seal_time"] == "09:45"
    assert row["last_seal_minute"] == 585
    assert row["limit_up_pool_open_times"] is None
    assert row["break_pool_open_times"] == 1


@pytest.mark.parametrize(
    ("intervals", "expected_last", "expected_minute", "open_times", "final_sealed"),
    [
        ([(time(9, 45), time(10)), (time(14, 20), time(15, 1))], "14:20", 860, 1, True),
        ([(time(9, 45), time(10)), (time(14, 20), time(14, 40))], "14:20", 860, 2, False),
        ([(time(11, 25), time(15, 1))], "11:25", 685, 0, True),
        ([(time(9, 30), time(15, 1))], "09:30", 570, 0, True),
    ],
)
def test_last_seal_is_latest_seal_start(
    tmp_path: Path, intervals, expected_last, expected_minute, open_times, final_sealed,
):
    symbol = "600000.SH"
    overrides = {
        stamp.time(): (11.0, 11.0, 11.0)
        for stamp in _session_times(DAY)
        if any(start <= stamp.time() < end for start, end in intervals)
    }
    _seed_market(tmp_path, _bars(symbol, DAY, overrides=overrides), symbols=[symbol])

    rows = fetch_minute_limit_board_events(tmp_path, DAY, now=NOW)

    assert len(rows) == 1
    row = rows[0]
    assert row["last_seal_time"] == expected_last
    assert row["last_seal_minute"] == expected_minute
    assert row["observed_open"] == int(open_times > 0)
    assert row["in_limit_up_pool"] == (1 if final_sealed else None)
    assert row["in_limit_break_pool"] == (None if final_sealed else 1)
    count_field = "limit_up_pool_open_times" if final_sealed else "break_pool_open_times"
    assert row[count_field] == open_times


def test_minute_high_touch_without_close_seal_is_not_an_event(tmp_path: Path):
    symbol = "300001.SZ"
    bars = _bars(
        symbol,
        DAY,
        close=10.5,
        high=10.5,
        overrides={time(9, 45): (10.5, 12.5, 10.4)},
    )
    _seed_market(tmp_path, bars, symbols=[symbol])

    rows = fetch_minute_limit_board_events(tmp_path, DAY, now=NOW)

    assert rows == []


def test_incomplete_minute_day_is_not_classified(tmp_path: Path):
    symbol = "000002.SZ"
    bars = _bars(symbol, DAY, count=200)
    _seed_market(tmp_path, bars, symbols=[symbol])
    frame = pl.read_parquet(tmp_path / "kline_minute" / f"date={DAY}" / "part.parquet")
    frame = frame.with_columns(
        pl.when(pl.col("datetime") >= datetime.combine(DAY, time(9, 45)))
        .then(11.0)
        .otherwise(pl.col("close"))
        .alias("close"),
        pl.when(pl.col("datetime") >= datetime.combine(DAY, time(9, 45)))
        .then(11.0)
        .otherwise(pl.col("high"))
        .alias("high"),
    )
    frame.write_parquet(tmp_path / "kline_minute" / f"date={DAY}" / "part.parquet")

    rows = fetch_minute_limit_board_events(tmp_path, DAY, now=NOW)

    assert rows == []


def test_tdx_240_bar_day_gets_an_in_memory_opening_sentinel(tmp_path: Path):
    symbol = "600007.SH"
    bars = _bars(symbol, DAY, close=10.5, count=241)[1:]
    bars[0].update(
        open=11.0,
        high=11.0,
        low=10.5,
        close=10.5,
    )
    _seed_market(tmp_path, bars, symbols=[symbol])

    rows = fetch_minute_limit_board_events(tmp_path, DAY, now=NOW)

    assert len(rows) == 1
    row = rows[0]
    assert row["in_limit_up_pool"] is None
    assert row["in_limit_break_pool"] == 1
    assert row["observed_open"] == 1
    assert row["first_seal_time"] == "09:30"
    assert row["last_seal_time"] == "09:30"
    assert row["turnover"] == 24000.0
    stored = pl.read_parquet(tmp_path / "kline_minute" / f"date={DAY}" / "part.parquet")
    assert stored.height == 240
    assert stored["datetime"].min() == datetime.combine(DAY, time(9, 31))


def test_ex_rights_reference_price_uses_ex_factor_without_optional_detail_columns(
    tmp_path: Path,
):
    symbol = "600001.SH"
    _seed_market(
        tmp_path,
        _bars(symbol, DAY, close=5.5, high=5.5),
        symbols=[symbol],
        prev_closes={symbol: 10.0},
        adj_ex_factors={symbol: 2.0},
    )

    rows = fetch_minute_limit_board_events(tmp_path, DAY, now=NOW)

    assert len(rows) == 1
    assert rows[0]["in_limit_up_pool"] == 1


def test_non_finite_minute_value_rejects_the_partition(tmp_path: Path):
    symbol = "600002.SH"
    _seed_market(tmp_path, _bars(symbol, DAY), symbols=[symbol])
    path = tmp_path / "kline_minute" / f"date={DAY}" / "part.parquet"
    frame = pl.read_parquet(path).with_columns(
        pl.when(pl.int_range(pl.len()) == 10)
        .then(float("nan"))
        .otherwise(pl.col("amount"))
        .alias("amount")
    )
    frame.write_parquet(path)

    with pytest.raises(ValueError, match="invalid bars"):
        fetch_minute_limit_board_events(tmp_path, DAY, now=NOW)


def test_no_limit_window_ipo_is_not_classified_as_a_limit_board(tmp_path: Path):
    symbol = "300001.SZ"
    _seed_market(
        tmp_path,
        _bars(symbol, DAY, close=12.0),
        symbols=[symbol],
        prev_closes={symbol: 10.0},
        listing_dates={symbol: PREV_DAY.isoformat()},
    )

    rows = fetch_minute_limit_board_events(tmp_path, DAY, now=NOW)

    assert rows == []


def test_unknown_main_board_st_status_fails_closed(tmp_path: Path):
    symbol = "600003.SH"
    _seed_market(tmp_path, _bars(symbol, DAY, close=11.0), symbols=[symbol])
    st_path = tmp_path / "st_history" / "part.parquet"
    pl.DataFrame(
        schema={
            "symbol": pl.String,
            "flag_date": pl.Date,
            "st_flag": pl.Boolean,
        }
    ).write_parquet(st_path)

    rows = fetch_minute_limit_board_events(tmp_path, DAY, now=NOW)

    assert rows == []


def test_forward_adjusted_minute_basis_is_rejected(tmp_path: Path):
    symbol = "600004.SH"
    _seed_market(tmp_path, _bars(symbol, DAY, close=11.0), symbols=[symbol])
    (tmp_path / "kline_minute" / ".raw_basis").unlink()

    with pytest.raises(ValueError, match="raw basis"):
        fetch_minute_limit_board_events(tmp_path, DAY, now=NOW)


def test_pre_reform_chinext_uses_ten_percent_limit(tmp_path: Path):
    symbol = "300001.SZ"
    day = date(2019, 6, 3)
    prev_day = date(2019, 5, 31)
    _seed_market(
        tmp_path,
        _bars(symbol, day, close=11.0),
        symbols=[symbol],
        day=day,
        prev_day=prev_day,
        prev_closes={symbol: 10.0},
    )

    rows = fetch_minute_limit_board_events(tmp_path, day, now=NOW)

    assert len(rows) == 1
    assert rows[0]["in_limit_up_pool"] == 1


def test_pre_reform_chinext_st_uses_five_percent_limit(tmp_path: Path):
    symbol = "300001.SZ"
    day = date(2019, 6, 3)
    prev_day = date(2019, 5, 31)
    _seed_market(
        tmp_path,
        _bars(symbol, day, close=10.5),
        symbols=[symbol],
        day=day,
        prev_day=prev_day,
        prev_closes={symbol: 10.0},
        st_flags={symbol: True},
    )

    rows = fetch_minute_limit_board_events(tmp_path, day, now=NOW)

    assert len(rows) == 1
    assert rows[0]["in_limit_up_pool"] == 1


def test_chinext_reform_day_uses_twenty_percent_limit(tmp_path: Path):
    symbol = "300001.SZ"
    day = date(2020, 8, 24)
    prev_day = date(2020, 8, 21)
    _seed_market(
        tmp_path,
        _bars(symbol, day, close=11.0),
        symbols=[symbol],
        day=day,
        prev_day=prev_day,
        prev_closes={symbol: 10.0},
    )

    rows = fetch_minute_limit_board_events(tmp_path, day, now=NOW)

    assert rows == []


def test_missing_final_minutes_cannot_claim_a_close_seal(tmp_path: Path):
    symbol = "600005.SH"
    _seed_market(tmp_path, _bars(symbol, DAY, close=11.0), symbols=[symbol])
    path = tmp_path / "kline_minute" / f"date={DAY}" / "part.parquet"
    frame = pl.read_parquet(path).filter(pl.col("datetime") < datetime.combine(DAY, time(14, 56)))
    assert frame.height == 236
    frame.write_parquet(path)

    rows = fetch_minute_limit_board_events(tmp_path, DAY, now=NOW)

    assert rows == []


def test_newer_minute_previous_close_wins_over_stale_daily_close(tmp_path: Path):
    symbol = "600006.SH"
    _seed_market(
        tmp_path,
        _bars(symbol, DAY, close=11.0),
        symbols=[symbol],
        daily_day=date(2026, 8, 28),
        prev_closes={symbol: 10.0},
        prev_minute_closes={symbol: 12.0},
    )

    rows = fetch_minute_limit_board_events(tmp_path, DAY, now=NOW)

    assert rows == []


def test_unknown_listing_date_fails_closed(tmp_path: Path):
    symbol = "688001.SH"
    _seed_market(
        tmp_path,
        _bars(symbol, DAY, close=12.0),
        symbols=[symbol],
        prev_closes={symbol: 10.0},
        instrument_symbols=[],
    )

    rows = fetch_minute_limit_board_events(tmp_path, DAY, now=NOW)

    assert rows == []
