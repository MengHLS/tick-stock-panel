"""Contracts for the close-confirmed path-stop study."""

from datetime import date, timedelta

import polars as pl
import pytest

from scripts import auction_path_stop_study as study


def _sessions() -> list[date]:
    start = date(2024, 1, 2)
    return [start + timedelta(days=index) for index in range(6)]


def _daily(
    sessions: list[date],
    *,
    closes: list[float],
    opens: list[float],
) -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": ["600001.SH"] * len(sessions),
        "date": sessions,
        "open": opens,
        "close": closes,
    })


def _selected(sessions: list[date]) -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": ["600001.SH"],
        "date": [sessions[0]],
        "exit_date": [sessions[-1]],
        "entry_vwap": [10.0],
        "net_return": [0.05],
    })


def test_close_breach_exits_at_next_session_open():
    sessions = _sessions()
    daily = _daily(
        sessions,
        opens=[10.0, 10.0, 8.8, 9.0, 9.0, 9.0],
        closes=[10.0, 9.0, 9.0, 9.0, 9.0, 9.0],
    )
    selected, prices, excluded = study.prepare_path_universe(
        _selected(sessions),
        sessions=sessions,
        daily=daily,
    )
    result = study.apply_stop_variant(
        selected,
        sessions=sessions,
        prices=prices,
        stop_pct=0.08,
        commission_bps=3,
        stamp_tax_bps=10,
        slippage_bps=5,
    )

    row = result.row(0, named=True)
    expected = 8.8 / 10.0
    expected *= (1 - 0.0005) * (1 - 0.0003 - 0.001)
    expected /= (1 + 0.0005) * (1 + 0.0003)
    assert excluded == 0
    assert row["stop_triggered"] is True
    assert row["path_exit_date"] == sessions[2]
    assert row["path_net_return"] == pytest.approx(expected - 1)


def test_entry_day_close_cannot_trigger_due_to_t_plus_one():
    sessions = _sessions()
    daily = _daily(
        sessions,
        opens=[10.0] * len(sessions),
        closes=[5.0, 10.0, 10.0, 10.0, 10.0, 10.0],
    )
    selected, prices, _ = study.prepare_path_universe(
        _selected(sessions),
        sessions=sessions,
        daily=daily,
    )
    result = study.apply_stop_variant(
        selected,
        sessions=sessions,
        prices=prices,
        stop_pct=0.08,
        commission_bps=3,
        stamp_tax_bps=10,
        slippage_bps=5,
    )

    row = result.row(0, named=True)
    assert row["stop_triggered"] is False
    assert row["path_exit_date"] == sessions[-1]
    assert row["path_net_return"] == 0.05
    assert result.schema["stop_trigger_date"] == pl.Date
    assert result.schema["stop_exit_price"] == pl.Float64


def test_incomplete_daily_path_is_excluded_from_all_variants():
    sessions = _sessions()
    daily = _daily(
        sessions,
        opens=[10.0] * len(sessions),
        closes=[10.0] * len(sessions),
    ).filter(pl.col("date") != sessions[3])

    selected, _, excluded = study.prepare_path_universe(
        _selected(sessions),
        sessions=sessions,
        daily=daily,
    )

    assert selected.is_empty()
    assert excluded == 1


def test_event_results_use_path_return_instead_of_scheduled_return():
    panel = pl.DataFrame({
        "symbol": ["600001.SH", "600002.SH"],
        "date": [date(2024, 1, 2), date(2024, 1, 2)],
        "gap_bucket": ["2-4", "2-4"],
        "entry_reason": ["ok", "ok"],
        "exit_reason": ["ok", "ok"],
        "net_return": [0.01, 0.03],
    })
    selected = pl.DataFrame({
        "symbol": ["600001.SH"],
        "date": [date(2024, 1, 2)],
        "path_net_return": [0.05],
        "stop_triggered": [True],
    })

    result = study.event_results(
        panel,
        {"baseline": selected},
        bootstrap_samples=0,
        seed=1,
    )

    assert result[0]["mean_net_return"] == pytest.approx(0.05)
