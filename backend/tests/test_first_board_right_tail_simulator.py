from __future__ import annotations

from datetime import date, datetime, time, timedelta

import polars as pl
import pytest

from scripts.first_board_right_tail_lab.contracts import (
    EventRecord,
    FillResult,
    TriggerCandidate,
)
from scripts.first_board_right_tail_lab.simulator import (
    SimulationConfig,
    execute_entry,
    simulate_event,
    simulate_event_attempts,
    simulate_exit,
)


def _candidate(order_time: datetime = datetime(2026, 1, 5, 9, 36)):
    signal_time = order_time - timedelta(minutes=1)
    return TriggerCandidate(
        event_id="000001.SZ:2026-01-02",
        symbol="000001.SZ",
        rule="B",
        bar_end=signal_time,
        signal_available_time=signal_time,
        order_time=order_time,
        signal_close_adj=10.0,
    )


def _bar(
    day: date,
    start_time: time,
    *,
    open_price: float,
    close_price: float | None = None,
    high_price: float | None = None,
    low_price: float | None = None,
    volume: float = 1_000.0,
    symbol: str = "000001.SZ",
) -> dict:
    close_price = open_price if close_price is None else close_price
    high_price = max(open_price, close_price) if high_price is None else high_price
    low_price = min(open_price, close_price) if low_price is None else low_price
    start = datetime.combine(day, start_time)
    end = start + timedelta(minutes=1)
    return {
        "symbol": symbol,
        "datetime": end,
        "bar_start": start,
        "bar_end": end,
        "volume": volume,
        "open_raw": open_price,
        "high_raw": high_price,
        "low_raw": low_price,
        "close_raw": close_price,
        "amount_raw": open_price * volume * 100.0,
        "open_adj": open_price,
        "high_adj": high_price,
        "low_adj": low_price,
        "close_adj": close_price,
        "amount_adj": open_price * volume * 100.0,
    }


def _context(
    day: date,
    *,
    raw_close: float = 10.0,
    limit_up_price: float = 11.0,
    limit_down_price: float = 9.0,
    tradable: bool = True,
    suspended: bool = False,
    delisted: bool = False,
    final_settlement_price: float | None = None,
) -> dict:
    return {
        "symbol": "000001.SZ",
        "date": day,
        "raw_close": raw_close,
        "limit_up_price": limit_up_price,
        "limit_down_price": limit_down_price,
        "tradable": tradable,
        "suspended": suspended,
        "st_flag": False,
        "delisted": delisted,
        "final_settlement_price": final_settlement_price,
    }


def _filled(
    *,
    fill_time: datetime = datetime(2026, 1, 5, 9, 36),
) -> FillResult:
    return FillResult(
        candidate_id="event:B:signal",
        event_id="000001.SZ:2026-01-02",
        symbol="000001.SZ",
        filled=True,
        fill_time=fill_time,
        fill_price_raw=10.0,
        entry_exec_adj=10.0,
        capacity_base_amount=5_000_000.0,
        quantity=1_800,
        entry_fee=5.0,
        entry_notional=18_000.0,
    )


def test_entry_fills_at_next_minute_bar_open():
    candidate = _candidate()
    bars = pl.DataFrame(
        [
            _bar(
                date(2026, 1, 5),
                time(9, 36),
                open_price=10.0,
                close_price=10.1,
                volume=100.0,
            )
        ]
    )
    context = pl.DataFrame([_context(date(2026, 1, 5))])

    fill = execute_entry(
        candidate,
        bars,
        context,
        SimulationConfig(),
        capacity_base_amount=5_000_000.0,
    )

    assert fill.filled
    assert fill.fill_time == datetime(2026, 1, 5, 9, 36)
    assert fill.fill_price_raw == pytest.approx(10.0 * 1.0005)
    assert fill.quantity == 1_700


def test_entry_rejects_limit_up_locked_bar():
    candidate = _candidate()
    bars = pl.DataFrame(
        [
            _bar(
                date(2026, 1, 5),
                time(9, 36),
                open_price=11.0,
                close_price=11.0,
                high_price=11.0,
                low_price=11.0,
            )
        ]
    )
    context = pl.DataFrame([_context(date(2026, 1, 5))])

    fill = execute_entry(
        candidate,
        bars,
        context,
        SimulationConfig(),
        capacity_base_amount=5_000_000.0,
    )

    assert not fill.filled
    assert fill.blocked_reason == "limit_up_locked"


def test_entry_rejects_zero_volume_fill_bar():
    candidate = _candidate()
    bars = pl.DataFrame(
        [
            _bar(
                date(2026, 1, 5),
                time(9, 36),
                open_price=10.0,
                volume=0.0,
            )
        ]
    )
    context = pl.DataFrame([_context(date(2026, 1, 5))])

    fill = execute_entry(
        candidate,
        bars,
        context,
        SimulationConfig(),
        capacity_base_amount=5_000_000.0,
    )

    assert not fill.filled
    assert fill.blocked_reason == "zero_volume"


def test_capacity_uses_pre_order_history_not_current_minute_volume():
    event = EventRecord(
        event_id="000001.SZ:2026-01-02",
        symbol="000001.SZ",
        event_date=date(2026, 1, 2),
        t_high_raw=10.5,
        t_high_adj=10.5,
        t_close_raw=10.0,
        t_close_adj=10.0,
        price_limit_pct=0.10,
    )
    prior = [
        _bar(
            date(2026, 1, 2),
            time(14, 40 + index),
            open_price=10.0,
            volume=100.0,
        )
        for index in range(20)
    ]
    fill_bar = _bar(
        date(2026, 1, 5),
        time(9, 36),
        open_price=10.0,
        volume=1_000_000.0,
    )
    context = pl.DataFrame([_context(date(2026, 1, 5))])

    fill, _ = simulate_event(
        event,
        [_candidate()],
        pl.DataFrame([*prior, fill_bar]),
        context,
        SimulationConfig(),
    )

    assert not fill.filled
    assert fill.blocked_reason == "capacity_exceeded"
    assert fill.capacity_base_amount == pytest.approx(100_000.0)


def test_buy_day_is_not_sellable_for_stop():
    fill = _filled()
    day = date(2026, 1, 5)
    bars = pl.DataFrame(
        [
            _bar(
                day,
                time(10, 0),
                open_price=9.0,
                close_price=9.0,
                high_price=9.0,
                low_price=9.0,
            )
        ]
    )
    context = pl.DataFrame([_context(day)])

    result = simulate_exit(fill, bars, context, SimulationConfig())

    assert result.fill_time is None
    assert result.status in {"pending_exit", "right_censored"}


def test_next_day_gap_below_stop_fills_at_open_with_slippage():
    fill = _filled()
    entry_day = date(2026, 1, 5)
    exit_day = date(2026, 1, 6)
    bars = pl.DataFrame(
        [
            _bar(
                exit_day,
                time(9, 30),
                open_price=9.2,
                close_price=9.1,
                high_price=9.3,
                low_price=9.0,
            )
        ]
    )
    context = pl.DataFrame(
        [_context(entry_day), _context(exit_day, raw_close=9.2)]
    )

    result = simulate_exit(fill, bars, context, SimulationConfig())

    assert result.status == "closed"
    assert result.fill_time == datetime(2026, 1, 6, 9, 30)
    assert result.fill_price_raw == pytest.approx(9.2 * 0.9995)
    assert result.net_return is not None and result.net_return < 0


def test_limit_down_lock_creates_pending_exit_then_fills_later():
    fill = _filled()
    entry_day = date(2026, 1, 5)
    locked_day = date(2026, 1, 6)
    sellable_day = date(2026, 1, 7)
    bars = pl.DataFrame(
        [
            _bar(
                locked_day,
                time(9, 30),
                open_price=9.0,
                close_price=9.0,
                high_price=9.0,
                low_price=9.0,
            ),
            _bar(
                sellable_day,
                time(9, 30),
                open_price=9.2,
                close_price=9.2,
            ),
        ]
    )
    context = pl.DataFrame(
        [
            _context(entry_day),
            _context(locked_day, raw_close=9.0, limit_down_price=9.0),
            _context(sellable_day, raw_close=9.2, limit_down_price=8.5),
        ]
    )

    result = simulate_exit(fill, bars, context, SimulationConfig())

    assert result.status == "closed"
    assert result.fill_time == datetime(2026, 1, 7, 9, 30)
    assert result.pending_days == 1


def test_day_19_1456_forces_exit_at_1457():
    fill = _filled()
    entry_day = date(2026, 1, 5)
    days = [entry_day + timedelta(days=index) for index in range(20)]
    bars = []
    for index, day in enumerate(days[1:], start=1):
        bars.append(
            _bar(
                day,
                time(9, 30),
                open_price=10.2,
                close_price=10.2,
            )
        )
        if index == 19:
            bars.append(
                _bar(
                    day,
                    time(14, 57),
                    open_price=10.2,
                    close_price=10.2,
                )
            )
    context = pl.DataFrame([_context(day, raw_close=10.2) for day in days])

    result = simulate_exit(
        fill,
        pl.DataFrame(bars),
        context,
        SimulationConfig(),
    )

    assert result.status == "closed"
    assert result.trigger_time == datetime.combine(days[19], time(14, 56))
    assert result.fill_time == datetime.combine(days[19], time(14, 57))
    assert result.reason == "forced_exit"


def test_after_1456_stop_is_deferred_to_next_day():
    fill = _filled()
    entry_day = date(2026, 1, 5)
    signal_day = date(2026, 1, 6)
    next_day = date(2026, 1, 7)
    bars = pl.DataFrame(
        [
            _bar(
                signal_day,
                time(14, 56),
                open_price=9.6,
                close_price=9.3,
            ),
            _bar(
                next_day,
                time(9, 30),
                open_price=9.35,
                close_price=9.35,
            ),
        ]
    )
    context = pl.DataFrame(
        [
            _context(entry_day),
            _context(signal_day, raw_close=9.3),
            _context(next_day, raw_close=9.35),
        ]
    )

    result = simulate_exit(fill, bars, context, SimulationConfig())

    assert result.status == "closed"
    assert result.fill_time == datetime(2026, 1, 7, 9, 30)
    assert result.trigger_time == datetime(2026, 1, 6, 14, 57)


def test_delisting_without_settlement_is_right_censored():
    fill = _filled()
    entry_day = date(2026, 1, 5)
    delist_day = date(2026, 1, 6)
    bars = pl.DataFrame(
        [_bar(entry_day, time(9, 31), open_price=10.0, close_price=10.0)]
    )
    context = pl.DataFrame(
        [
            _context(entry_day),
            _context(delist_day, delisted=True),
        ]
    )

    result = simulate_exit(fill, bars, context, SimulationConfig())

    assert result.status == "right_censored_delisting"


def test_stamp_duty_uses_historical_rate():
    entry_day = date(2023, 1, 5)
    fill = _filled(
        fill_time=datetime(2023, 1, 5, 9, 36),
    )

    def run(exit_day: date):
        bars = pl.DataFrame(
            [
                _bar(
                    exit_day,
                    time(9, 30),
                    open_price=9.2,
                    close_price=9.1,
                    high_price=9.3,
                    low_price=9.0,
                )
            ]
        )
        context = pl.DataFrame(
            [
                _context(entry_day),
                _context(exit_day, raw_close=9.2),
            ]
        )
        return simulate_exit(fill, bars, context, SimulationConfig())

    legacy = run(date(2023, 8, 25))
    current = run(date(2023, 8, 28))

    assert legacy.exit_fee is not None
    assert current.exit_fee is not None
    assert legacy.exit_fee > current.exit_fee


def test_blocked_attempts_are_preserved_when_later_candidate_fills():
    event = EventRecord(
        event_id="000001.SZ:2026-01-02",
        symbol="000001.SZ",
        event_date=date(2026, 1, 2),
        t_high_raw=10.5,
        t_high_adj=10.5,
        t_close_raw=10.0,
        t_close_adj=10.0,
        price_limit_pct=0.10,
    )
    day = date(2026, 1, 5)
    first = _candidate(datetime(2026, 1, 5, 9, 36))
    second = TriggerCandidate(
        event_id=first.event_id,
        symbol=first.symbol,
        rule="A",
        bar_end=datetime(2026, 1, 5, 10, 1),
        signal_available_time=datetime(2026, 1, 5, 10, 1),
        order_time=datetime(2026, 1, 5, 10, 2),
        signal_close_adj=10.6,
    )
    prior = [
        _bar(
            date(2026, 1, 2),
            time(14, 40 + index),
            open_price=10.0,
            volume=10_000.0,
        )
        for index in range(20)
    ]
    locked = _bar(
        day,
        time(9, 36),
        open_price=11.0,
        close_price=11.0,
        high_price=11.0,
        low_price=11.0,
    )
    later = _bar(
        day,
        time(10, 2),
        open_price=10.0,
        close_price=10.0,
    )
    context = pl.DataFrame([_context(day)])

    fill, _, attempts = simulate_event_attempts(
        event,
        [first, second],
        pl.DataFrame([*prior, locked, later]),
        context,
        SimulationConfig(),
    )

    assert fill.filled
    assert fill.candidate_id == second.candidate_id
    assert len(attempts) == 2
    assert attempts[0].blocked_reason == "limit_up_locked"
    assert attempts[1].filled
