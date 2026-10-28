from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl

from app.backtest.matrix import (
    build_market_data_matrix,
    build_market_matrix_from_signals,
    make_signal_matrix,
)
from scripts.first_board_entry_study import (
    apply_execution_caps,
    build_event_table,
    policy_mask,
)


def _market():
    rows = []
    for i in range(270):
        price = 10.0 + i * 0.01
        rows.append({
            "symbol": "000001.SZ",
            "date": date(2025, 1, 1) + timedelta(days=i),
            "open": price,
            "high": price + 0.2,
            "low": price - 0.2,
            "close": price,
            "volume": 1_000.0,
            "consecutive_limit_ups": 1 if i in (250, 260, 269) else 0,
        })
    return build_market_data_matrix(
        pl.DataFrame(rows), field_columns={"consecutive_limit_ups"},
    )


def test_event_features_do_not_change_when_future_prices_change():
    from dataclasses import replace

    market = _market()
    close = market.close.copy()
    high = market.high.copy()
    close[265:] *= 2
    high[265:] *= 2
    changed = replace(market, close=close, high=high)
    before = build_event_table(market).filter(pl.col("time_id") <= 260)
    after = build_event_table(changed).filter(pl.col("time_id") <= 260)
    assert before.equals(after)
    assert before["nearest_anchor_date"].to_list() == [None, "2025-09-08"]


def test_execution_gap_is_checked_after_signal_delay_and_never_changes_prices():
    panel = pl.DataFrame({
        "symbol": ["A"] * 4,
        "date": [date(2026, 1, 5) + timedelta(days=i) for i in range(4)],
        "open": [10.0, 10.6, 10.0, 10.3],
        "close": [10.0] * 4,
        "high": [10.0, 10.6, 10.0, 10.3],
        "low": [10.0] * 4,
        "volume": [1_000.0] * 4,
    })
    market = build_market_data_matrix(panel)
    signals = make_signal_matrix(
        market.shape, entry=np.array([[1], [0], [1], [0]], dtype=np.uint8),
    )
    matrix = build_market_matrix_from_signals(market, signals, entry_delay_bars=1)
    gated, ledger = apply_execution_caps(matrix, {}, max_gap=0.03)
    assert signals.entry[:, 0].tolist() == [1, 0, 1, 0]
    assert matrix.entry[:, 0].tolist() == [0, 1, 0, 1]
    assert gated.entry[:, 0].tolist() == [0, 0, 0, 1]
    np.testing.assert_equal(gated.open, matrix.open)
    assert ledger["before"] == ledger["accepted"] + ledger["rejected"]
    assert ledger["rejected_gap"] == 1
    assert not gated.entry.flags.writeable


def test_reference_cap_fails_closed_on_missing_reference():
    market = _market()
    entry = np.zeros(market.shape, dtype=np.uint8)
    entry[260] = 1
    matrix = build_market_matrix_from_signals(
        market, make_signal_matrix(market.shape, entry=entry), entry_delay_bars=1,
    )
    gated, ledger = apply_execution_caps(matrix, {}, max_above_reference=0.03)
    assert not gated.entry.any()
    assert ledger["rejected_reference"] == 1


def test_low_start_policy_does_not_require_a_prior_chain():
    events = pl.DataFrame({
        "stage": [0.0, 5.0, 5.0],
        "position_before": [0.2, 0.9, float("nan")],
        "ret20_before": [0.05, 0.4, 0.0],
        "anchor_distance": [float("nan"), 10.0, 10.0],
        "anchor_position_before": [float("nan"), 0.3, 0.3],
        "bias_ma20": [0.1, 0.4, 0.1],
        "above_P": [float("nan"), 0.02, 0.02],
        "pullback": [float("nan"), 0.1, 0.1],
    })
    assert policy_mask(events, "low_start").tolist() == [True, False, False]
    assert policy_mask(events, "strict_context").tolist() == [False, False, False]
