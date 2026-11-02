from __future__ import annotations

from dataclasses import asdict

import pytest

from app.backtest.execution_policy import (
    BACKTEST_DEFAULTS_SCHEMA_VERSION,
    BacktestDefaultsError,
    parse_backtest_defaults,
)


def _versioned(**overrides):
    payload = {
        "schema_version": BACKTEST_DEFAULTS_SCHEMA_VERSION,
        "entry_fill": "open_t+1",
        "exit_fill": "open_t+1",
        "plan_at_signal_close": True,
        "max_daily_entries": 2,
        "entry_price_basis": "raw",
        "trailing_peak_price": "close",
        "score_tiers": [[0.0, 0.0], [0.55, 0.2]],
        "entry_open_gap_range": [-0.04, 0.04],
        "entry_prev_day_change_range": [-0.05, 0.05],
        "execution_costs": {
            "min_commission": 5.0,
            "transfer_fee_pct": 0.00001,
            "buy_slippage_tiers": [[500_000_000.0, 10.0]],
        },
        "hold_extension": {
            "decision_days": 5,
            "strong_hold_days": 10,
            "strong_hold_min_return": 0.03,
            "runner_new_high_days": 3,
            "runner_extend_days": 74,
        },
    }
    payload.update(overrides)
    return payload


def test_missing_schema_version_is_legacy_v1_and_idempotent() -> None:
    raw = {
        "entry_fill": "open_t+1",
        "plan_at_signal_close": True,
        "max_daily_entries": 2,
        "score_tiers": [[0.0, 0.0], [0.55, 0.2]],
    }

    policy = parse_backtest_defaults(raw)
    repeated = parse_backtest_defaults(raw)

    assert policy.legacy is True
    assert policy.schema_version == BACKTEST_DEFAULTS_SCHEMA_VERSION
    assert policy.engine_options() == repeated.engine_options()
    assert policy.entry_open_gap_range is None
    assert policy.score_tiers == ((0.0, 0.0), (0.55, 0.2))


def test_v1_parses_execution_contract_without_changing_core_rules() -> None:
    policy = parse_backtest_defaults(_versioned())

    assert policy.legacy is False
    assert policy.score_tiers == ((0.0, 0.0), (0.55, 0.2))
    assert policy.entry_open_gap_range == (-0.04, 0.04)
    assert policy.entry_prev_day_change_range == (-0.05, 0.05)
    assert policy.trailing_peak_price == "close"
    assert policy.plan_at_signal_close is True
    assert policy.max_daily_entries == 2
    assert policy.entry_price_basis == "raw"
    assert policy.execution_costs is not None
    assert policy.execution_costs.buy_slippage_tiers == ((500_000_000.0, 10.0),)
    assert policy.hold_extension_policy is not None
    assert policy.hold_extension_policy.runner_extend_days == 74


def test_engine_options_are_a_copy_not_the_frozen_policy_state() -> None:
    policy = parse_backtest_defaults(_versioned())
    options = policy.engine_options()
    options["max_daily_entries"] = 99

    assert policy.max_daily_entries == 2
    assert asdict(policy)["max_daily_entries"] == 2


@pytest.mark.parametrize("version", [0, 2, True, "1"])
def test_unknown_or_invalid_schema_version_fails_closed(version) -> None:
    with pytest.raises(BacktestDefaultsError, match="schema_version"):
        parse_backtest_defaults(_versioned(schema_version=version))


def test_versioned_unknown_field_fails_closed() -> None:
    with pytest.raises(BacktestDefaultsError, match="unknown fields: typo_field"):
        parse_backtest_defaults(_versioned(typo_field=1))


def test_legacy_unknown_field_remains_readable() -> None:
    policy = parse_backtest_defaults({"legacy_extension": True})
    assert policy.legacy is True


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"plan_at_signal_close": True, "entry_fill": "close_t"}, "next-open"),
        ({"max_daily_entries": 0}, "max_daily_entries"),
        ({"entry_open_gap_range": [0.2, -0.2]}, "lower bound"),
        ({"entry_prev_day_change_range": [-0.1]}, "must be a pair"),
        ({"trailing_peak_price": "open"}, "trailing_peak_price"),
        ({"entry_price_basis": "close"}, "entry_price_basis"),
        ({"exit_signal_requires_profit": 1}, "true or false"),
        ({"score_tiers": [[0.0, 0.5], [0.5, 1.5]]}, "between 0 and 1"),
        (
            {"execution_costs": {"min_commission": -1}},
            "execution_costs",
        ),
        (
            {"execution_costs": {"buy_slippage_tiers": [[0.0, 10.0]]}},
            "execution_costs",
        ),
        (
            {"hold_extension": {"decision_days": 5, "strong_hold_days": 4}},
            "hold_extension",
        ),
    ],
)
def test_invalid_execution_defaults_fail_closed(patch, message: str) -> None:
    with pytest.raises(BacktestDefaultsError, match=message):
        parse_backtest_defaults(_versioned(**patch))


def test_first_limit_pullback_strategy_declares_v1() -> None:
    from pathlib import Path

    from app.strategy.engine import StrategyEngine

    path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "strategy"
        / "research"
        / "first_limit_pullback_3f_runner_t74.py"
    )
    strategy = StrategyEngine._load_file(path)
    defaults = strategy.meta["backtest_defaults"]
    assert defaults["schema_version"] == BACKTEST_DEFAULTS_SCHEMA_VERSION
    assert parse_backtest_defaults(defaults).legacy is False
