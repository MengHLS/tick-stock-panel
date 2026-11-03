from __future__ import annotations

from datetime import date, datetime, time, timedelta

import polars as pl

from scripts.first_board_right_tail_lab.contracts import EventRecord
from scripts.first_board_right_tail_lab.triggers import (
    aggregate_five_minute,
    edge_is_new,
    iter_trigger_candidates,
)


def _event(
    *,
    event_date: date = date(2026, 1, 2),
    t_high_adj: float = 10.5,
) -> EventRecord:
    return EventRecord(
        event_id=f"000001.SZ:{event_date.isoformat()}",
        symbol="000001.SZ",
        event_date=event_date,
        t_high_raw=t_high_adj,
        t_high_adj=t_high_adj,
        t_close_raw=10.0,
        t_close_adj=10.0,
        price_limit_pct=0.10,
    )


def _minute_bars(
    day: date,
    closes: list[float],
    volumes: list[float] | None = None,
    *,
    start_time: time = time(9, 30),
    symbol: str = "000001.SZ",
) -> pl.DataFrame:
    volumes = volumes or [100.0] * len(closes)
    first_end = datetime.combine(day, start_time) + timedelta(minutes=1)
    bar_ends = [
        first_end + timedelta(minutes=index)
        for index in range(len(closes))
    ]
    return pl.DataFrame(
        {
            "symbol": [symbol] * len(closes),
            "datetime": bar_ends,
            "bar_start": [
                value - timedelta(minutes=1)
                for value in bar_ends
            ],
            "bar_end": bar_ends,
            "volume": volumes,
            "open_raw": closes,
            "high_raw": closes,
            "low_raw": closes,
            "close_raw": closes,
            "amount_raw": [
                close * volume * 100.0
                for close, volume in zip(closes, volumes, strict=True)
            ],
            "open_adj": closes,
            "high_adj": closes,
            "low_adj": closes,
            "close_adj": closes,
            "amount_adj": [
                close * volume * 100.0
                for close, volume in zip(closes, volumes, strict=True)
            ],
        }
    )


def test_edge_is_new_only_on_false_to_true_transition():
    assert edge_is_new(False, True)
    assert not edge_is_new(True, True)
    assert not edge_is_new(False, False)


def test_e0_only_triggers_t_plus_one_0935_and_orders_at_0936():
    event = _event()
    day_one = date(2026, 1, 5)
    day_two = date(2026, 1, 6)
    bars = pl.concat(
        [
            _minute_bars(day_one, [10.0] * 5),
            _minute_bars(day_two, [10.0] * 5),
        ]
    )

    candidates, unavailable = iter_trigger_candidates(
        event,
        bars,
        ("E0",),
    )

    assert not unavailable
    assert len(candidates) == 1
    assert candidates[0].bar_end == datetime(2026, 1, 5, 9, 35)
    assert candidates[0].order_time == datetime(2026, 1, 5, 9, 36)


def test_rule_a_requires_twenty_prior_bars_and_uses_one_edge():
    event = _event()
    day = date(2026, 1, 5)
    before_0950 = _minute_bars(
        day,
        [10.0] * 19 + [10.6],
        [100.0] * 19 + [300.0],
    )
    candidates, _ = iter_trigger_candidates(
        event,
        before_0950,
        ("A",),
    )
    assert not candidates

    active = _minute_bars(
        day,
        [10.0] * 20 + [10.6, 10.6],
        [100.0] * 20 + [300.0, 300.0],
    )
    candidates, _ = iter_trigger_candidates(event, active, ("A",))

    assert len(candidates) == 1
    assert candidates[0].rule == "A"
    assert candidates[0].bar_end == datetime(2026, 1, 5, 9, 51)
    assert candidates[0].order_time == datetime(2026, 1, 5, 9, 52)


def test_aggregate_five_minute_uses_complete_groups_and_bar_end_time():
    day = date(2026, 1, 5)
    bars = _minute_bars(day, [10.0, 10.1, 10.2, 10.3, 10.4, 10.5])

    five = aggregate_five_minute(bars)

    assert five.height == 1
    assert five["bar_end"][0] == datetime(2026, 1, 5, 9, 35)
    assert five["close_adj"][0] == 10.4
    assert five["volume"][0] == 500.0


def test_rule_b_requires_two_closes_above_rising_vwap():
    event = _event(t_high_adj=20.0)
    day = date(2026, 1, 5)
    bars = _minute_bars(day, [10.0] * 5 + [10.2] * 10)

    candidates, _ = iter_trigger_candidates(event, bars, ("B",))

    assert len(candidates) == 1
    assert candidates[0].bar_end == datetime(2026, 1, 5, 9, 45)
    assert candidates[0].order_time == datetime(2026, 1, 5, 9, 46)


def test_rule_c_requires_retake_of_five_minute_ma5():
    event = _event(t_high_adj=20.0)
    day = date(2026, 1, 5)
    bars = _minute_bars(
        day,
        (
            [10.0] * 5
            + [9.9] * 5
            + [9.8] * 5
            + [9.7] * 5
            + [9.6] * 5
            + [10.3] * 5
        ),
    )

    candidates, _ = iter_trigger_candidates(event, bars, ("C",))

    assert len(candidates) == 1
    assert candidates[0].bar_end == datetime(2026, 1, 5, 10, 0)
    assert candidates[0].order_time == datetime(2026, 1, 5, 10, 1)


def test_rule_d_only_uses_t_plus_one_auction_confirmation():
    event = _event()
    day_one = date(2026, 1, 5)
    day_two = date(2026, 1, 6)
    bars = pl.concat(
        [
            _minute_bars(day_one, [10.1] * 5),
            _minute_bars(day_two, [10.1] * 5),
        ]
    )
    auction = {
        "opening_gap": 0.02,
        "volume_ratio": 1.5,
        "auction_price_adj": 10.0,
    }

    candidates, unavailable = iter_trigger_candidates(
        event,
        bars,
        ("D",),
        auction=auction,
    )

    assert not unavailable
    assert len(candidates) == 1
    assert candidates[0].bar_end == datetime(2026, 1, 5, 9, 35)
    assert candidates[0].order_time == datetime(2026, 1, 5, 9, 36)


def test_no_new_candidate_after_1456():
    event = _event(t_high_adj=10.5)
    day = date(2026, 1, 5)
    bars = _minute_bars(
        day,
        [10.0] * 20 + [10.6],
        [100.0] * 20 + [300.0],
        start_time=time(14, 36),
    )

    candidates, _ = iter_trigger_candidates(event, bars, ("A",))

    assert not candidates


def test_missing_auction_data_marks_rule_d_unavailable():
    event = _event()
    bars = _minute_bars(date(2026, 1, 5), [10.1] * 5)

    candidates, unavailable = iter_trigger_candidates(event, bars, ("D",))

    assert not candidates
    assert len(unavailable) == 1
    assert unavailable[0].rule == "D"
    assert unavailable[0].reason == "auction_unavailable"


def test_incomplete_auction_data_marks_rule_d_unavailable():
    event = _event()
    bars = _minute_bars(date(2026, 1, 5), [10.1] * 5)

    candidates, unavailable = iter_trigger_candidates(
        event,
        bars,
        ("D",),
        auction={"opening_gap": 0.02},
    )

    assert not candidates
    assert len(unavailable) == 1
    assert unavailable[0].reason == "auction_unavailable"


def test_raw_only_auction_price_is_not_mixed_with_adjusted_minutes():
    event = _event()
    bars = _minute_bars(date(2026, 1, 5), [10.1] * 5)

    candidates, unavailable = iter_trigger_candidates(
        event,
        bars,
        ("D",),
        auction={
            "opening_gap": 0.02,
            "volume_ratio": 1.5,
            "auction_price": 10.0,
        },
    )

    assert not candidates
    assert len(unavailable) == 1
    assert unavailable[0].reason == "auction_unavailable"
