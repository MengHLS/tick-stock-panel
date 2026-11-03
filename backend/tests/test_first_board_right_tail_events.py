from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from scripts.first_board_right_tail_lab.events import (
    build_first_board_events,
    is_main_board_symbol,
    sample_events_monthly,
)


def _sessions(count: int = 25) -> list[date]:
    start = date(2026, 1, 1)
    return [start + timedelta(days=index) for index in range(count)]


def _daily_rows(
    symbol: str,
    sessions: list[date],
    *,
    consecutive_limit_ups: int = 0,
) -> list[dict]:
    rows = []
    for index, session in enumerate(sessions):
        is_last = index == len(sessions) - 1
        close = 11.0 if is_last else 10.0
        high = 11.2 if is_last else 10.0
        low = 10.8 if is_last else 10.0
        rows.append(
            {
                "symbol": symbol,
                "date": session,
                "open": 10.0,
                "high": high,
                "low": low,
                "close": close,
                "raw_close": close,
                "raw_high": high,
                "raw_low": low,
                "volume": 1_000.0,
                "amount": 1_000_000.0,
                "consecutive_limit_ups": (
                    consecutive_limit_ups if is_last else 0
                ),
            }
        )
    return rows


def _build_inputs(
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, list[date], date]:
    sessions = _sessions(25)
    event_day = sessions[23]
    event_sessions = sessions[:24]
    daily = pl.DataFrame(
        _daily_rows(
            "000001.SZ",
            event_sessions,
            consecutive_limit_ups=1,
        )
        + _daily_rows(
            "000002.SZ",
            event_sessions,
            consecutive_limit_ups=1,
        )
        + _daily_rows(
            "300001.SZ",
            event_sessions,
            consecutive_limit_ups=1,
        )
        + _daily_rows(
            "000003.SZ",
            event_sessions,
            consecutive_limit_ups=2,
        )
        + _daily_rows(
            "000004.SZ",
            event_sessions,
            consecutive_limit_ups=1,
        )
    )
    instruments = pl.DataFrame(
        {
            "symbol": [
                "000001.SZ",
                "000002.SZ",
                "300001.SZ",
                "000003.SZ",
                "000004.SZ",
            ],
            "name": ["正常股", "正常股", "创业板股", "正常股", "新股"],
            "listing_date": [
                None,
                "2020-01-01",
                "2020-01-01",
                "2020-01-01",
                sessions[19].isoformat(),
            ],
        }
    )
    st_history = pl.DataFrame(
        {
            "symbol": [
                "000001.SZ",
                "000002.SZ",
                "300001.SZ",
                "000003.SZ",
                "000004.SZ",
            ],
            "flag_date": [date(2020, 1, 1)] * 5,
            "st_flag": [False, True, False, False, False],
        }
    )
    return daily, instruments, st_history, sessions, event_day


def test_main_board_symbol_requires_shanghai_shenzhen_60_or_00():
    assert is_main_board_symbol("600001.SH")
    assert is_main_board_symbol("000001.SZ")
    assert not is_main_board_symbol("300001.SZ")
    assert not is_main_board_symbol("688001.SH")
    assert not is_main_board_symbol("830001.BJ")


def test_build_events_keeps_first_board_and_audits_exclusions():
    daily, instruments, st_history, sessions, event_day = _build_inputs()

    events, exclusions = build_first_board_events(
        daily,
        instruments,
        st_history,
        sessions,
        sessions[0],
        event_day,
    )

    assert events.height == 1
    event = events.row(0, named=True)
    assert event["event_id"] == "000001.SZ:2026-01-24"
    assert event["symbol"] == "000001.SZ"
    assert event["event_date"] == event_day
    assert event["is_st_at_event"] is False
    assert event["listed_trading_days"] == 24
    assert event["listing_age_source"] == "observed_daily_bars"
    assert event["board"] == "main_board"
    assert event["price_limit_pct"] == 0.10
    assert event["t_close_adj"] == 11.0
    assert event["t_close_raw"] == 11.0

    reasons = {
        row["symbol"]: row["reason"]
        for row in exclusions.iter_rows(named=True)
    }
    assert reasons == {
        "000002.SZ": "historical_st",
        "300001.SZ": "non_main_board",
        "000003.SZ": "not_first_board",
        "000004.SZ": "insufficient_listing_history",
    }


def test_future_prices_do_not_change_event_fields():
    daily, instruments, st_history, sessions, event_day = _build_inputs()
    events_before, _ = build_first_board_events(
        daily,
        instruments,
        st_history,
        sessions,
        sessions[0],
        event_day,
    )
    future = daily.filter(pl.col("date") == sessions[23]).with_columns(
        pl.lit(99.0).alias("high"),
        pl.lit(99.0).alias("raw_high"),
        pl.lit(88.0).alias("close"),
        pl.lit(88.0).alias("raw_close"),
        pl.lit(sessions[24]).alias("date"),
        pl.lit(0, dtype=pl.Int64).alias("consecutive_limit_ups"),
    )
    events_after, _ = build_first_board_events(
        pl.concat([daily, future]),
        instruments,
        st_history,
        sessions,
        sessions[0],
        event_day,
    )

    assert events_after.equals(events_before)


def test_monthly_event_sampling_is_deterministic_and_balanced():
    events = pl.DataFrame(
        {
            "event_id": [f"event-{index:02d}" for index in range(12)],
            "event_date": [
                *[date(2026, 1, 5)] * 6,
                *[date(2026, 2, 5)] * 6,
            ],
            "symbol": [
                f"{index:06d}.SZ"
                for index in range(12)
            ],
        }
    )

    first = sample_events_monthly(
        events,
        2,
        seed=7,
    )
    second = sample_events_monthly(
        events,
        2,
        seed=7,
    )

    assert first.equals(second)
    assert first.height == 4
    assert first.group_by(
        pl.col("event_date").dt.strftime("%Y-%m")
    ).len()["len"].to_list() == [2, 2]
