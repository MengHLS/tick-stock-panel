"""Contracts for the auction factor-admission research helper."""

from datetime import date, timedelta

import polars as pl
import pytest

from scripts import auction_factor_admission as admission


def test_candidate_factors_are_stable_scale_free_and_not_pit():
    factors = admission.candidate_factors()
    assert factors
    assert all(spec.stability == "stable" for spec in factors)
    assert all(spec.scale_free for spec in factors)
    assert all(not spec.pit for spec in factors)
    assert all(not spec.id.startswith("ext_") for spec in factors)
    assert "vwap_bias" not in {spec.id for spec in factors}


def test_previous_close_factor_shifts_within_symbol_only():
    frame = pl.DataFrame({
        "symbol": ["600000.SH", "600000.SH", "000001.SZ", "000001.SZ"],
        "date": [
            date(2024, 9, 2), date(2024, 9, 3),
            date(2024, 9, 2), date(2024, 9, 3),
        ],
        "momentum_5d": [0.1, 0.2, 0.3, 0.4],
    })
    shifted = admission.shift_to_decision_day(frame, ["momentum_5d"])
    values = shifted.sort(["symbol", "date"])["factor__momentum_5d"].to_list()
    assert values == [None, 0.3, None, 0.1]


def test_rank_ic_is_null_safe_and_uses_same_day_gap_residual():
    rows = []
    start = date(2021, 1, 4)
    for day_index in range(12):
        for asset in range(10):
            rows.append({
                "symbol": f"6000{asset:02d}.SH",
                "date": start + timedelta(days=day_index),
                "gap_bucket": "2-4",
                "horizon": 3,
                "entry_reason": "ok",
                "exit_reason": "ok",
                "net_return": asset / 1000,
                "factor__signal": float(asset) if day_index % 3 else None,
            })
    metrics = admission._factor_metrics(
        pl.DataFrame(rows),
        "factor__signal",
        date(2021, 1, 1),
        date(2021, 12, 31),
    )
    assert metrics["status"] == "ok"
    assert metrics["coverage"] == pytest.approx(2 / 3)
    assert metrics["mean_ic"] == pytest.approx(1.0)
    assert metrics["direction"] == "high"
    assert metrics["event_days"] == 12
    assert metrics["ic_days"] == 8
