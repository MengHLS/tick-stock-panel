from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from app.custom.first_board_event_chain.compute import (
    EVENT_CHAIN_FIELDS,
    EventChainConfig,
    compute_event_chain_outputs,
    materialize_event_chain_columns,
)
from app.factors.registry import FactorSpec, register_factor, unregister_factor
from app.strategy.scoring import materialize_scoring_columns


def _panel(
    closes: list[float],
    *,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    opens: list[float] | None = None,
    boards: list[int] | None = None,
    symbol: str = "000001.SZ",
) -> pl.DataFrame:
    size = len(closes)
    start = date(2026, 1, 5)
    opens = opens or closes
    highs = highs or [max(open_price, close) for open_price, close in zip(opens, closes, strict=True)]
    lows = lows or [min(open_price, close) for open_price, close in zip(opens, closes, strict=True)]
    boards = boards or [0] * size
    return pl.DataFrame({
        "symbol": [symbol] * size,
        "date": [start + timedelta(days=index) for index in range(size)],
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "consecutive_limit_ups": boards,
    })


def _strict_rebreak_panel(*, symbol: str = "000001.SZ") -> pl.DataFrame:
    return _panel(
        closes=[10.0, 10.8, 11.7, 11.5, 10.9, 11.2, 12.1],
        highs=[10.2, 11.0, 12.0, 11.8, 11.3, 11.5, 12.2],
        lows=[9.8, 10.5, 11.2, 11.0, 10.5, 10.8, 11.9],
        boards=[1, 0, 0, 0, 0, 0, 1],
        symbol=symbol,
    )


def _row(frame: pl.DataFrame, index: int) -> dict:
    return frame.row(index, named=True)


def test_strict_first_close_rebreak_has_expected_structure_and_polars_matrix_parity() -> None:
    panel = _strict_rebreak_panel()
    materialized = materialize_event_chain_columns(panel, EVENT_CHAIN_FIELDS)
    row = _row(materialized, 6)

    assert row["first_board_chain_stage"] == 5
    assert row["first_board_chain_anchor_distance"] == 6
    assert row["first_board_chain_pullback_pct"] == pytest.approx(0.125)
    assert row["first_board_chain_target_above_reference_pct"] == pytest.approx(
        12.1 / 12.0 - 1.0
    )
    assert row["first_board_chain_strict_rebreak"] == 1
    assert row["first_board_chain_early_breakout"] == 0
    assert row["first_board_chain_recovered_not_breakout"] == 0
    assert row["first_board_chain_seed_close_preserved"] == 1
    assert row["first_board_chain_seed_low_preserved"] == 1

    outputs = compute_event_chain_outputs(
        panel["open"].to_numpy().reshape(-1, 1),
        panel["high"].to_numpy().reshape(-1, 1),
        panel["low"].to_numpy().reshape(-1, 1),
        panel["close"].to_numpy().reshape(-1, 1),
        panel["consecutive_limit_ups"].to_numpy().reshape(-1, 1),
        EventChainConfig(),
    )
    for name in EVENT_CHAIN_FIELDS:
        np.testing.assert_allclose(
            materialized[name].to_numpy(),
            outputs[name][:, 0],
            rtol=1e-6,
            atol=1e-6,
            equal_nan=True,
            err_msg=name,
        )


def test_shallow_pullback_is_not_a_valid_chain() -> None:
    panel = _panel(
        closes=[10.0, 11.8, 11.7, 12.1],
        highs=[10.2, 12.0, 11.9, 12.2],
        lows=[9.8, 11.6, 11.7, 11.9],
        boards=[1, 0, 0, 1],
    )
    row = _row(materialize_event_chain_columns(panel, EVENT_CHAIN_FIELDS), 3)

    assert row["first_board_chain_stage"] == 2
    assert row["first_board_chain_pullback_pct"] < EventChainConfig().min_pullback_pct
    assert row["first_board_chain_strict_rebreak"] == 0


def test_early_breakout_before_target_is_terminal() -> None:
    panel = _panel(
        closes=[10.0, 11.5, 11.9, 11.6, 12.0, 12.2],
        highs=[10.2, 11.8, 11.9, 11.7, 12.0, 12.3],
        lows=[9.8, 11.2, 11.5, 11.3, 11.7, 12.0],
        boards=[1, 0, 0, 0, 0, 1],
    )
    row = _row(materialize_event_chain_columns(panel, EVENT_CHAIN_FIELDS), 5)

    assert row["first_board_chain_stage"] == 4
    assert row["first_board_chain_early_breakout"] == 1
    assert row["first_board_chain_strict_rebreak"] == 0


def test_latest_incomplete_anchor_recurses_to_older_valid_structure() -> None:
    panel = _panel(
        closes=[10.0, 10.8, 11.8, 10.9, 11.0, 10.95, 10.98, 12.2],
        highs=[10.2, 11.0, 12.0, 11.0, 11.1, 11.0, 11.0, 12.3],
        lows=[9.8, 10.5, 11.2, 10.8, 10.9, 10.6, 10.6, 12.0],
        boards=[1, 0, 0, 1, 0, 0, 0, 1],
    )
    row = _row(materialize_event_chain_columns(panel, EVENT_CHAIN_FIELDS), 7)

    assert row["first_board_chain_stage"] == 5
    assert row["first_board_chain_anchor_distance"] == 7
    assert row["first_board_chain_strict_rebreak"] == 1


def test_recursion_stops_on_early_breakout_instead_of_skipping_it() -> None:
    panel = _panel(
        closes=[10.0, 10.8, 11.8, 10.9, 11.0, 10.95, 11.2, 12.2],
        highs=[10.2, 11.0, 12.0, 11.0, 11.1, 11.0, 11.3, 12.3],
        lows=[9.8, 10.5, 11.2, 10.8, 10.9, 10.6, 11.0, 12.0],
        boards=[1, 0, 0, 1, 0, 0, 0, 1],
    )
    row = _row(materialize_event_chain_columns(panel, EVENT_CHAIN_FIELDS), 7)

    assert row["first_board_chain_stage"] == 4
    assert row["first_board_chain_anchor_distance"] == 4
    assert row["first_board_chain_early_breakout"] == 1


def test_lookback_boundary_and_non_first_board_values() -> None:
    panel = _strict_rebreak_panel()
    included = materialize_event_chain_columns(
        panel,
        EVENT_CHAIN_FIELDS,
        config=EventChainConfig(lookback_bars=6),
    )
    excluded = materialize_event_chain_columns(
        panel,
        EVENT_CHAIN_FIELDS,
        config=EventChainConfig(lookback_bars=5),
    )
    non_target = materialize_event_chain_columns(
        panel.with_columns(pl.lit(2).alias("consecutive_limit_ups")),
        EVENT_CHAIN_FIELDS,
    )

    assert _row(included, 6)["first_board_chain_stage"] == 5
    assert _row(excluded, 6)["first_board_chain_stage"] == 0
    assert non_target["first_board_chain_stage"].is_nan().all()


def test_missing_price_fails_closed_without_using_future_rows() -> None:
    panel = _strict_rebreak_panel().with_columns(
        pl.when(pl.int_range(pl.len()) == 4)
        .then(None)
        .otherwise(pl.col("low"))
        .alias("low")
    )
    materialized = materialize_event_chain_columns(panel, EVENT_CHAIN_FIELDS)
    row = _row(materialized, 6)

    assert row["first_board_chain_stage"] == 1
    assert row["first_board_chain_strict_rebreak"] == 0
    assert np.isnan(row["first_board_chain_pullback_pct"])

    original = _strict_rebreak_panel()
    changed_future = original.with_columns(
        pl.when(pl.int_range(pl.len()) > 6)
        .then(pl.col("close") * 100)
        .otherwise(pl.col("close"))
        .alias("close")
    )
    before = materialize_event_chain_columns(original, EVENT_CHAIN_FIELDS)
    after = materialize_event_chain_columns(changed_future, EVENT_CHAIN_FIELDS)
    for name in EVENT_CHAIN_FIELDS:
        assert before[name][6] == after[name][6]


def test_non_positive_price_fails_closed() -> None:
    panel = _strict_rebreak_panel().with_columns(
        pl.when(pl.int_range(pl.len()) == 4)
        .then(0.0)
        .otherwise(pl.col("low"))
        .alias("low")
    )
    row = _row(materialize_event_chain_columns(panel, EVENT_CHAIN_FIELDS), 6)

    assert row["first_board_chain_stage"] == 1
    assert row["first_board_chain_strict_rebreak"] == 0


def test_polars_materialization_preserves_input_row_order() -> None:
    panel = pl.concat([
        _strict_rebreak_panel(),
        _strict_rebreak_panel(symbol="600000.SH"),
    ]).reverse()
    materialized = materialize_event_chain_columns(panel, EVENT_CHAIN_FIELDS)

    assert materialized.select("symbol", "date").equals(panel.select("symbol", "date"))
    target = materialized.filter(
        (pl.col("symbol") == "000001.SZ")
        & (pl.col("date") == date(2026, 1, 11))
    ).row(0, named=True)
    assert target["first_board_chain_stage"] == 5


def test_custom_formula_can_reference_event_chain_factor() -> None:
    factor_id = "__test_first_board_chain_signal"
    register_factor(FactorSpec(
        id=factor_id,
        label="测试事件链信号",
        group="测试",
        formula_text="if_else(first_board_chain_stage >= 5, 1, 0)",
        kind="custom",
        warmup_bars=251,
    ))
    try:
        materialized = materialize_scoring_columns(
            _strict_rebreak_panel(),
            [factor_id],
        )
        assert materialized["first_board_chain_stage"][6] == 5
        assert materialized[factor_id][6] == 1
    finally:
        unregister_factor(factor_id)
