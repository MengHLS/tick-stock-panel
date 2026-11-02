from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from scripts.first_board_right_tail_lab.contracts import (
    TriggerCandidate,
    make_event_id,
)


def test_trigger_candidate_requires_one_minute_execution_delay():
    signal_time = datetime(2026, 1, 5, 9, 35)
    with pytest.raises(ValueError, match="one-minute"):
        TriggerCandidate(
            event_id="000001.SZ:2026-01-02",
            symbol="000001.SZ",
            rule="B",
            bar_end=signal_time,
            signal_available_time=signal_time,
            order_time=signal_time,
            signal_close_adj=11.0,
        )


def test_trigger_candidate_accepts_0936_after_0935_signal():
    signal_time = datetime(2026, 1, 5, 9, 35)
    candidate = TriggerCandidate(
        event_id="000001.SZ:2026-01-02",
        symbol="000001.SZ",
        rule="B",
        bar_end=signal_time,
        signal_available_time=signal_time,
        order_time=signal_time + timedelta(minutes=1),
        signal_close_adj=11.0,
    )
    assert candidate.order_time == datetime(2026, 1, 5, 9, 36)


def test_event_id_is_stable():
    assert make_event_id("000001.SZ", date(2026, 1, 2)) == "000001.SZ:2026-01-02"
