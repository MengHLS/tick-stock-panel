from __future__ import annotations

from datetime import date, datetime, time, timedelta

import polars as pl
import pytest

import scripts.first_board_right_tail_lab as lab
from scripts.first_board_right_tail_lab.contracts import (
    EventRecord,
    TriggerCandidate,
)
from scripts.first_board_right_tail_lab.dataset import (
    DecisionSample,
    build_decision_sample,
    decision_days_waited,
    decision_features,
    make_decision_id,
)
from scripts.first_board_right_tail_lab.labels import build_labels
from scripts.first_board_right_tail_lab.simulator import (
    SimulationConfig,
    execute_entry,
    pre_order_capacity_base,
    simulate_exit,
)


def _unfilled_sample() -> DecisionSample:
    signal_time = datetime(2026, 1, 5, 10, 1)
    return DecisionSample(
        decision_id=make_decision_id("000001.SZ:2026-01-02", "A", signal_time),
        event_id="000001.SZ:2026-01-02",
        candidate_id="candidate-a",
        symbol="000001.SZ",
        decision_date=date(2026, 1, 5),
        decision_time=signal_time,
        trigger_rule="A",
        trigger_bar_end=signal_time,
        signal_available_time=signal_time,
        days_waited=1,
        market_fillable=False,
        market_blocked_reason="limit_up_locked",
        label_observable=False,
        entry_exec_adj=None,
        mfe_touch_20d=None,
        mae_touch_20d=None,
        peak_day=None,
        stop_first=None,
        ordering_ambiguous=None,
        mfe_exec_20d=None,
        mae_exec_20d=None,
        exec_return=None,
        exit_status=None,
        label_maturity_time=None,
        features={
            "price_vs_t_high": 0.1,
            "factor__roe": None,
            "rule_a": 1.0,
        },
    )


def test_decision_id_is_stable_and_rule_specific():
    signal = datetime(2026, 1, 5, 10, 1)
    first = make_decision_id("event", "A", signal)

    assert first == "event:A:2026-01-05T10:01:00"
    assert first != make_decision_id("event", "B", signal)
    assert first != make_decision_id("event", "A", signal.replace(minute=2))


def test_flat_row_expands_features_without_filling_nulls():
    row = _unfilled_sample().to_flat_row()

    assert row["feature__price_vs_t_high"] == 0.1
    assert row["feature__factor__roe"] is None
    assert row["feature__rule_a"] == 1.0
    assert row["market_fillable"] is False
    assert row["market_blocked_reason"] == "limit_up_locked"
    assert row["mfe_touch_20d"] is None
    assert "features" not in row


def test_flat_row_is_deterministic_and_does_not_mutate_features():
    sample = _unfilled_sample()
    before = dict(sample.features)

    first = sample.to_flat_row()
    second = sample.to_flat_row()

    assert first == second
    assert sample.features == before
    assert list(first)[-3:] == [
        "feature__factor__roe",
        "feature__price_vs_t_high",
        "feature__rule_a",
    ]


def _event() -> EventRecord:
    return EventRecord(
        event_id="000001.SZ:2026-01-02",
        symbol="000001.SZ",
        event_date=date(2026, 1, 2),
        t_high_raw=10.5,
        t_high_adj=10.5,
        t_close_raw=10.0,
        t_close_adj=10.0,
        price_limit_pct=0.10,
    )


def _candidate(signal: datetime) -> TriggerCandidate:
    return TriggerCandidate(
        event_id="000001.SZ:2026-01-02",
        symbol="000001.SZ",
        rule="A",
        bar_end=signal,
        signal_available_time=signal,
        order_time=signal + timedelta(minutes=1),
        signal_close_adj=10.0,
    )


def _bars(
    *,
    rows: int = 30,
    future: bool = False,
) -> pl.DataFrame:
    day = date(2026, 1, 5)
    first_end = datetime.combine(day, time(9, 31))
    values = []
    for index in range(rows):
        bar_end = first_end + timedelta(minutes=index)
        close = 10.0 + index * 0.01
        values.append(
            {
                "symbol": "000001.SZ",
                "datetime": bar_end,
                "bar_start": bar_end - timedelta(minutes=1),
                "bar_end": bar_end,
                "volume": 100.0,
                "open_raw": close,
                "high_raw": close,
                "low_raw": close,
                "close_raw": close,
                "amount_raw": close * 100.0 * 100.0,
                "open_adj": close,
                "high_adj": close,
                "low_adj": close,
                "close_adj": close,
                "amount_adj": close * 100.0 * 100.0,
            }
        )
    if future:
        future_end = first_end + timedelta(minutes=rows)
        values.append(
            {
                "symbol": "000001.SZ",
                "datetime": future_end,
                "bar_start": future_end - timedelta(minutes=1),
                "bar_end": future_end,
                "volume": 1_000_000.0,
                "open_raw": 20.0,
                "high_raw": 20.0,
                "low_raw": 20.0,
                "close_raw": 20.0,
                "amount_raw": 20.0 * 1_000_000.0 * 100.0,
                "open_adj": 20.0,
                "high_adj": 20.0,
                "low_adj": 20.0,
                "close_adj": 20.0,
                "amount_adj": 20.0 * 1_000_000.0 * 100.0,
            }
        )
    return pl.DataFrame(values)


def test_features_ignore_bars_after_signal_time():
    signal = datetime(2026, 1, 5, 10, 0)
    candidate = _candidate(signal)

    before = decision_features(_event(), candidate, _bars())
    after = decision_features(_event(), candidate, _bars(future=True))

    assert before == after


def test_vwap_ma5_and_day_waited_use_completed_history():
    signal = datetime(2026, 1, 5, 9, 55)
    candidate = _candidate(signal)
    features = decision_features(
        _event(),
        candidate,
        _bars(rows=25),
        daily_factors={
            "roe": None,
            "momentum": 0.2,
            "daily__volume": 2500.0,
        },
    )

    assert features["price_vs_t_high"] == pytest.approx(
        10.24 / 10.5 - 1
    )
    assert features["price_vs_vwap"] == pytest.approx(
        10.24 / (sum(10 + i * 0.01 for i in range(25)) / 25) - 1
    )
    assert features["price_vs_5m_ma5"] is not None
    assert features["volume_ratio_20"] == pytest.approx(1.0)
    assert features["minutes_since_open"] == 25
    assert features["rule_a"] == 1.0
    assert features["rule_b"] == 0.0
    assert features["factor__roe"] is None
    assert features["factor__momentum"] == 0.2
    assert features["opening_gap"] == pytest.approx(0.0)
    assert features["first5_return_vs_t_close"] == pytest.approx(0.004)
    assert features["first5_high_vs_t_high"] == pytest.approx(
        10.04 / 10.5 - 1
    )
    assert features["first5_low_vs_t_close"] == pytest.approx(0.0)
    assert features["first5_range_pct"] == pytest.approx(0.004)
    assert features["first5_volume_share_t"] == pytest.approx(0.2)
    assert features["minutes_above_vwap_ratio"] == pytest.approx(1.0)
    assert features["locked_minute_ratio"] == pytest.approx(0.0)
    assert features["current_vs_first5_high"] == pytest.approx(
        10.24 / 10.04 - 1
    )
    assert features["volume_growth_last5_vs_first5"] == pytest.approx(1.0)
    assert decision_days_waited(
        _event(),
        candidate,
        [
            date(2026, 1, 2),
            date(2026, 1, 5),
            date(2026, 1, 6),
        ],
    ) == 1


def test_ma5_is_null_before_five_completed_five_minute_bars():
    signal = datetime(2026, 1, 5, 9, 50)
    features = decision_features(
        _event(),
        _candidate(signal),
        _bars(rows=20),
    )

    assert features["price_vs_5m_ma5"] is None


def _bar(
    day: date,
    start_time: time,
    *,
    open_price: float,
    volume: float = 10_000.0,
    high_price: float | None = None,
    low_price: float | None = None,
    close_price: float | None = None,
) -> dict:
    start = datetime.combine(day, start_time)
    end = start + timedelta(minutes=1)
    close_price = open_price if close_price is None else close_price
    high_price = max(open_price, close_price) if high_price is None else high_price
    low_price = min(open_price, close_price) if low_price is None else low_price
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


def _context(days: list[date]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "date": day,
                "raw_close": 10.0,
                "limit_up_price": 11.0,
                "limit_down_price": 9.0,
                "tradable": True,
                "suspended": False,
                "st_flag": False,
            }
            for day in days
        ]
    )


def _decision_fixture(*, locked_fill: bool = False):
    event = _event()
    fill_day = date(2026, 1, 5)
    label_days = [fill_day + timedelta(days=index) for index in range(20)]
    sessions = [event.event_date, *label_days]
    prior = [
        _bar(
            event.event_date,
            time(14, 40 + index),
            open_price=10.0,
        )
        for index in range(20)
    ]
    fill_rows = [
        _bar(
            fill_day,
            time(9, 30 + index),
            open_price=10.0,
        )
        for index in range(1, 6)
    ]
    fill_rows.append(
        _bar(
            fill_day,
            time(9, 36),
            open_price=11.0 if locked_fill else 10.0,
            high_price=11.0 if locked_fill else 10.1,
            low_price=11.0 if locked_fill else 9.9,
            close_price=11.0 if locked_fill else 10.0,
        )
    )
    for day in label_days[1:]:
        fill_rows.append(
            _bar(
                day,
                time(9, 30),
                open_price=9.0 if day == label_days[1] else 10.0,
                high_price=9.1 if day == label_days[1] else 10.1,
                low_price=9.0 if day == label_days[1] else 9.9,
                close_price=9.0 if day == label_days[1] else 10.0,
            )
        )
    candidate = TriggerCandidate(
        event_id=event.event_id,
        symbol=event.symbol,
        rule="E0",
        bar_end=datetime.combine(fill_day, time(9, 35)),
        signal_available_time=datetime.combine(fill_day, time(9, 35)),
        order_time=datetime.combine(fill_day, time(9, 36)),
        signal_close_adj=10.0,
    )
    return (
        event,
        candidate,
        pl.DataFrame([*prior, *fill_rows]).sort("bar_start"),
        _context(label_days),
        sessions,
    )


def test_build_decision_sample_matches_existing_simulator_and_labels():
    event, candidate, bars, context, sessions = _decision_fixture()
    config = SimulationConfig()
    capacity = pre_order_capacity_base(
        bars,
        candidate.order_time,
        candidate.symbol,
    )
    fill = execute_entry(
        candidate,
        bars,
        context,
        config,
        capacity_base_amount=capacity,
    )
    exit_result = simulate_exit(fill, bars, context, config)
    label = build_labels(
        fill,
        exit_result,
        bars,
        config,
        daily_context=context,
        trading_dates=sessions,
    )

    sample = build_decision_sample(
        event,
        candidate,
        bars,
        context,
        sessions,
        config,
        daily_factors={"roe": 0.1},
    )

    assert sample.market_fillable
    assert sample.label_observable
    assert sample.entry_exec_adj == fill.entry_exec_adj
    assert sample.mfe_exec_20d == label.mfe_exec_20d
    assert sample.exec_return == label.exec_return
    assert sample.features["factor__roe"] == 0.1


def test_unfilled_decision_keeps_sample_without_labels():
    event, candidate, bars, context, sessions = _decision_fixture(
        locked_fill=True
    )

    sample = build_decision_sample(
        event,
        candidate,
        bars,
        context,
        sessions,
        SimulationConfig(),
    )

    assert not sample.market_fillable
    assert sample.market_blocked_reason == "limit_up_locked"
    assert not sample.label_observable
    assert sample.mfe_touch_20d is None


def test_filled_late_candidate_with_short_horizon_is_not_label_observable():
    event, candidate, bars, context, sessions = _decision_fixture()
    short_sessions = [
        session
        for session in sessions
        if session <= sessions[-16]
    ]

    sample = build_decision_sample(
        event,
        candidate,
        bars,
        context,
        short_sessions,
        SimulationConfig(),
    )

    assert sample.market_fillable
    assert not sample.label_observable
    assert sample.exit_status == "insufficient_label_horizon"
    assert sample.mfe_touch_20d is None


def test_m2a_stable_contracts_are_exported():
    assert lab.DecisionSample is DecisionSample
    assert callable(lab.make_decision_id)
    assert lab.DEFAULT_FOLDS
