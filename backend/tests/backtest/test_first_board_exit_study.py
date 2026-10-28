from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl

from app.backtest.engine import BacktestEngine, MatcherConfig
from app.backtest.matrix import (
    build_market_data_matrix,
    build_market_matrix_from_signals,
    make_signal_matrix,
    slice_market_data_matrix,
    slice_signal_matrix,
)
from scripts.first_board_exit_study import (
    EXIT_PROTOCOLS,
    ExitProtocol,
    ma20_breakdown_signal,
    protocol_matcher,
    protocol_signals,
)


def test_ma20_breakdown_signal_requires_a_fresh_cross() -> None:
    close = np.array([[10.0], [10.0], [8.0], [7.0]])
    ma20 = np.array([[9.0], [9.0], [9.0], [8.0]])

    assert ma20_breakdown_signal(close, ma20)[:, 0].tolist() == [
        False,
        False,
        True,
        False,
    ]


def test_ma20_breakdown_signal_rejects_missing_previous_bar() -> None:
    close = np.array([[8.0], [7.0]])
    ma20 = np.array([[9.0], [8.0]])

    assert not ma20_breakdown_signal(close, ma20).any()


def test_exit_protocols_are_unique_and_independent() -> None:
    assert len({protocol.id for protocol in EXIT_PROTOCOLS}) == len(EXIT_PROTOCOLS)
    by_id = {protocol.id: protocol for protocol in EXIT_PROTOCOLS}
    assert by_id["baseline_8pct_30d"].stop_loss_pct == -0.08
    assert by_id["fixed_hold_5d"].max_hold_days == 5
    assert by_id["ma20_breakdown"].use_ma20_breakdown
    assert by_id["trailing_high_8pct"].trailing_stop_pct == 0.08
    assert (
        by_id["profit_protect_3pct_6pct"].trailing_take_profit_activate_pct
        == 0.03
    )


def test_protocol_matcher_maps_only_the_selected_exit_controls() -> None:
    base = MatcherConfig(
        matching="open_t+1",
        stop_loss_pct=-0.08,
        max_hold_days=30,
        max_positions=5,
    )
    protocol = ExitProtocol(
        id="trailing",
        description="test",
        trailing_stop_pct=0.08,
    )

    matcher = protocol_matcher(base, protocol)

    assert matcher.stop_loss_pct == -0.08
    assert matcher.max_hold_days == 30
    assert matcher.trailing_stop_pct == 0.08
    assert matcher.trailing_peak_price == "high"
    assert base.trailing_stop_pct is None


def test_structure_protocol_adds_ma20_exit_without_changing_entry() -> None:
    start = date(2026, 1, 5)
    panel = pl.DataFrame({
        "symbol": ["A"] * 4,
        "date": [start + timedelta(days=index) for index in range(4)],
        "open": [10.0, 10.0, 8.0, 7.0],
        "high": [10.0, 10.0, 8.0, 7.0],
        "low": [10.0, 10.0, 8.0, 7.0],
        "close": [10.0, 10.0, 8.0, 7.0],
        "volume": [1_000.0] * 4,
        "ma20": [9.0, 9.0, 9.0, 8.0],
    })
    market = build_market_data_matrix(panel, field_columns={"ma20"})
    entry = np.array([[1], [0], [0], [0]], dtype=np.uint8)
    entries = make_signal_matrix(
        market.shape,
        entry=entry,
        entry_signal_code=np.where(entry, 0, -1).astype(np.int16),
        entry_signal_ids=("entry",),
    )

    signals = protocol_signals(
        market,
        entries,
        next(
            protocol
            for protocol in EXIT_PROTOCOLS
            if protocol.id == "ma20_breakdown"
        ),
    )

    np.testing.assert_equal(signals.entry, entries.entry)
    assert signals.exit[:, 0].tolist() == [0, 0, 1, 0]
    assert signals.exit_signal_ids == ("signal_ma20_breakdown",)


def test_warmed_cross_sells_at_next_open_and_uses_no_future_close() -> None:
    from dataclasses import replace

    # There are enough warmed closes before the formal period starts.
    prices = [10.0] * 20 + [10.5, 10.5, 9.9, 12.0, 13.0]
    panel = pl.DataFrame({
        "symbol": ["A"] * len(prices),
        "date": [date(2026, 1, 1) + timedelta(days=i) for i in range(len(prices))],
        "open": prices,
        "high": prices,
        "low": prices,
        "close": prices,
        "volume": [1_000.0] * len(prices),
    })
    market = build_market_data_matrix(panel)
    entry = np.zeros(market.shape, dtype=np.uint8)
    entry[20, 0] = 1
    base = make_signal_matrix(market.shape, entry=entry)
    protocol = next(p for p in EXIT_PROTOCOLS if p.use_ma20_breakdown)
    signals = protocol_signals(market, base, protocol)
    altered_close = market.close.copy()
    altered_close[23:] *= 10
    altered = protocol_signals(replace(market, close=altered_close), base, protocol)
    np.testing.assert_array_equal(signals.exit[:23], altered.exit[:23])
    matrix = build_market_matrix_from_signals(
        slice_market_data_matrix(market, 20, 25),
        slice_signal_matrix(signals, 20, 25),
        entry_delay_bars=1, exit_delay_bars=1,
    )
    result = BacktestEngine(repo=None).simulate_market_matrix(
        matrix,
        protocol_matcher(
            MatcherConfig(
                matching="open_t+1", fees_pct=0.0, stamp_tax_pct=0.0,
                slippage_bps=0.0, max_positions=1,
            ),
            protocol,
        ),
    )
    trade = result.trades[0]
    assert trade.entry_date == market.timestamp_labels[21][:10]
    assert trade.exit_signal_date == market.timestamp_labels[22][:10]
    assert trade.exit_date == market.timestamp_labels[23][:10]
    assert trade.exit_reason == "signal"
    assert trade.exit_price == 12.0
