from __future__ import annotations

from datetime import date, datetime, time, timedelta

import polars as pl
import pytest

from scripts.first_board_right_tail_lab.contracts import (
    ExitResult,
    FillResult,
    LabelRecord,
)
from scripts.first_board_right_tail_lab.labels import (
    build_labels,
    classify_opportunity,
    utility,
)
from scripts.first_board_right_tail_lab.simulator import SimulationConfig


def _bar(
    day: date,
    start_time: time,
    *,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    volume: float = 1_000.0,
) -> dict:
    start = datetime.combine(day, start_time)
    end = start + timedelta(minutes=1)
    return {
        "symbol": "000001.SZ",
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


def _fill(fill_time: datetime = datetime(2026, 1, 5, 9, 36)) -> FillResult:
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


def _exit(
    *,
    status: str = "closed",
    reason: str = "stop_loss",
    fill_time: datetime | None = datetime(2026, 1, 6, 9, 30),
    net_return: float | None = -0.08,
) -> ExitResult:
    return ExitResult(
        status=status,
        reason=reason,
        trigger_time=fill_time,
        order_time=fill_time,
        fill_time=fill_time,
        fill_price_raw=9.2 if fill_time is not None else None,
        pending_days=0,
        quantity=1_800,
        exit_fee=10.0,
        net_return=net_return,
    )


def _sessions(
    start: date = date(2026, 1, 5),
    count: int = 21,
) -> list[date]:
    return [start + timedelta(days=index) for index in range(count)]


def test_touch_labels_ignore_pre_entry_prices_and_cap_at_day_19():
    days = _sessions()
    bars = [
        _bar(
            days[0],
            time(9, 30),
            open_price=20.0,
            high_price=100.0,
            low_price=1.0,
            close_price=20.0,
        ),
        _bar(
            days[0],
            time(9, 36),
            open_price=10.0,
            high_price=10.2,
            low_price=9.9,
            close_price=10.1,
        ),
    ]
    for day in days[1:19]:
        bars.append(
            _bar(
                day,
                time(9, 30),
                open_price=10.0,
                high_price=10.5,
                low_price=9.9,
                close_price=10.2,
            )
        )
    bars.append(
        _bar(
            days[19],
            time(9, 30),
            open_price=11.0,
            high_price=13.0,
            low_price=10.8,
            close_price=12.8,
        )
    )
    bars.append(
        _bar(
            days[20],
            time(9, 30),
            open_price=13.0,
            high_price=20.0,
            low_price=12.0,
            close_price=19.0,
        )
    )
    exit_result = _exit(
        reason="forced_exit",
        fill_time=datetime.combine(days[19], time(14, 57)),
        net_return=0.20,
    )

    label = build_labels(
        _fill(),
        exit_result,
        pl.DataFrame(bars),
        SimulationConfig(),
    )

    assert label.mfe_touch_20d == pytest.approx(0.30)
    assert label.mae_touch_20d == pytest.approx(-0.01)
    assert label.peak_day == 19
    assert not label.stop_first
    assert classify_opportunity(label) == 4


def test_same_minute_stop_and_high_is_conservatively_stop_first():
    days = _sessions(count=20)
    bars_data = [
        _bar(
            days[0],
            time(9, 36),
            open_price=10.0,
            high_price=10.0,
            low_price=9.9,
            close_price=10.0,
        ),
        _bar(
            days[1],
            time(9, 30),
            open_price=9.5,
            high_price=10.5,
            low_price=9.3,
            close_price=9.35,
        ),
    ]
    bars_data.extend(
        _bar(
            day,
            time(9, 30),
            open_price=10.0,
            high_price=10.0,
            low_price=9.9,
            close_price=10.0,
        )
        for day in days[2:]
    )
    bars = pl.DataFrame(bars_data)

    label = build_labels(
        _fill(),
        _exit(fill_time=datetime.combine(days[1], time(9, 30))),
        bars,
        SimulationConfig(),
    )

    assert label.stop_first
    assert label.ordering_ambiguous


def test_prices_after_exit_do_not_enter_executable_mfe():
    days = _sessions(count=20)
    bars_data = [
        _bar(
            days[0],
            time(9, 36),
            open_price=10.0,
            high_price=10.0,
            low_price=9.9,
            close_price=10.0,
        ),
        _bar(
            days[1],
            time(9, 30),
            open_price=9.5,
            high_price=9.6,
            low_price=9.3,
            close_price=9.3,
        ),
        _bar(
            days[2],
            time(9, 30),
            open_price=15.0,
            high_price=20.0,
            low_price=14.5,
            close_price=18.0,
        ),
    ]
    bars_data.extend(
        _bar(
            day,
            time(9, 30),
            open_price=10.0,
            high_price=10.2,
            low_price=9.9,
            close_price=10.0,
        )
        for day in days[3:]
    )
    bars = pl.DataFrame(bars_data)

    label = build_labels(
        _fill(),
        _exit(fill_time=datetime.combine(days[1], time(9, 30))),
        bars,
        SimulationConfig(),
    )

    assert label.mfe_touch_20d >= 1.0
    assert label.mfe_exec_20d == pytest.approx(-0.05)
    assert label.mfe_exec_20d != label.mfe_touch_20d


def test_pending_exit_after_label_window_is_right_censored():
    days = _sessions(count=20)
    bars = pl.DataFrame(
        [
            _bar(
                days[0],
                time(9, 36),
                open_price=10.0,
                high_price=10.1,
                low_price=9.9,
                close_price=10.0,
            ),
            *[
                _bar(
                    day,
                    time(9, 30),
                    open_price=10.0,
                    high_price=10.1,
                    low_price=9.9,
                    close_price=10.0,
                )
                for day in days[1:]
            ],
        ]
    )
    pending = _exit(
        status="pending_exit",
        reason="forced_exit",
        fill_time=None,
        net_return=None,
    )

    label = build_labels(_fill(), pending, bars, SimulationConfig())

    assert label.exit_status == "right_censored"
    assert label.exec_return is None
    assert label.mfe_exec_20d is None
    assert label.mae_exec_20d is None
    assert label.label_maturity_time == datetime.combine(days[19], time(15, 0))


def test_executable_labels_exclude_limit_down_locked_open():
    days = _sessions(count=20)
    bars_data = [
        _bar(
            days[0],
            time(9, 36),
            open_price=10.0,
            high_price=10.0,
            low_price=9.9,
            close_price=10.0,
        ),
        _bar(
            days[1],
            time(9, 30),
            open_price=8.0,
            high_price=8.0,
            low_price=8.0,
            close_price=8.0,
        ),
        _bar(
            days[1],
            time(10, 0),
            open_price=9.5,
            high_price=9.6,
            low_price=9.4,
            close_price=9.5,
        ),
    ]
    bars_data.extend(
        _bar(
            day,
            time(9, 30),
            open_price=10.0,
            high_price=10.0,
            low_price=9.9,
            close_price=10.0,
        )
        for day in days[2:]
    )
    context = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "date": day,
                "tradable": True,
                "suspended": False,
                "limit_down_price": (
                    8.0 if day == days[1] else 9.0
                ),
            }
            for day in days
        ]
    )

    label = build_labels(
        _fill(),
        _exit(fill_time=datetime.combine(days[1], time(10, 0))),
        pl.DataFrame(bars_data),
        SimulationConfig(),
        daily_context=context,
        trading_dates=days,
    )

    assert label.mae_exec_20d == pytest.approx(-0.05)


def test_late_closed_exit_is_right_censored_after_settlement_buffer():
    days = _sessions(count=26)
    bars_data = [
        _bar(
            days[0],
            time(9, 36),
            open_price=10.0,
            high_price=10.0,
            low_price=9.9,
            close_price=10.0,
        )
    ]
    bars_data.extend(
        _bar(
            day,
            time(9, 30),
            open_price=10.0,
            high_price=10.0,
            low_price=9.9,
            close_price=10.0,
        )
        for day in days[1:]
    )
    exit_time = datetime.combine(days[25], time(9, 30))

    label = build_labels(
        _fill(),
        _exit(fill_time=exit_time, net_return=0.05),
        pl.DataFrame(bars_data),
        SimulationConfig(),
        trading_dates=days,
    )

    assert label.exit_status == "right_censored"
    assert label.exec_return is None


@pytest.mark.parametrize(
    ("stop_first", "mfe", "peak_day", "expected"),
    [
        (True, 0.50, 1, 0),
        (False, 0.30, 10, 3),
        (False, 0.30, 11, 4),
        (False, 0.10, 19, 2),
        (False, 0.099, 1, 1),
        (False, 0.299, 1, 2),
    ],
)
def test_five_class_boundaries(stop_first, mfe, peak_day, expected):
    label = LabelRecord(
        event_id="event",
        candidate_id="candidate",
        entry_exec_adj=10.0,
        mfe_touch_20d=mfe,
        mae_touch_20d=-0.05,
        peak_day=peak_day,
        stop_first=stop_first,
        ordering_ambiguous=False,
        mfe_exec_20d=0.0,
        mae_exec_20d=-0.05,
        exec_return=0.0,
        exit_status="closed",
        label_maturity_time=None,
    )

    assert classify_opportunity(label) == expected


def test_utility_penalizes_late_peaks_but_never_rewards_stop_first():
    early = LabelRecord(
        event_id="event",
        candidate_id="early",
        entry_exec_adj=10.0,
        mfe_touch_20d=0.3,
        mae_touch_20d=-0.05,
        peak_day=5,
        stop_first=False,
        ordering_ambiguous=False,
        mfe_exec_20d=None,
        mae_exec_20d=None,
        exec_return=None,
        exit_status="closed",
        label_maturity_time=None,
    )
    late = LabelRecord(
        event_id="event",
        candidate_id="late",
        entry_exec_adj=10.0,
        mfe_touch_20d=0.3,
        mae_touch_20d=-0.05,
        peak_day=15,
        stop_first=False,
        ordering_ambiguous=False,
        mfe_exec_20d=None,
        mae_exec_20d=None,
        exec_return=None,
        exit_status="closed",
        label_maturity_time=None,
    )
    stopped = LabelRecord(
        event_id="event",
        candidate_id="stopped",
        entry_exec_adj=10.0,
        mfe_touch_20d=1.0,
        mae_touch_20d=-0.06,
        peak_day=1,
        stop_first=True,
        ordering_ambiguous=False,
        mfe_exec_20d=None,
        mae_exec_20d=None,
        exec_return=None,
        exit_status="closed",
        label_maturity_time=None,
    )

    assert utility(early) == pytest.approx(0.3)
    assert utility(late) == pytest.approx(0.3 * 0.36787944117)
    assert utility(stopped) == 0.0
