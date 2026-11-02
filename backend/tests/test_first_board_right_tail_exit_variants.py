from __future__ import annotations

import pytest

from scripts.first_board_right_tail_lab.exit_variants import (
    DEFAULT_EXIT_VARIANTS,
    ExitVariant,
    parse_exit_variants,
)
from scripts.first_board_right_tail_lab.simulator import SimulationConfig


def test_default_exit_variants_keep_cost_model_and_change_exit_policy():
    base = SimulationConfig(
        target_notional=20_000.0,
        commission_bps=3.0,
    )

    configs = [
        variant.simulation_config(base)
        for variant in DEFAULT_EXIT_VARIANTS
    ]

    assert configs[0].stop_loss_pct == pytest.approx(0.06)
    assert configs[0].max_holding_days == 20
    assert {config.target_notional for config in configs} == {20_000.0}
    assert {config.commission_bps for config in configs} == {3.0}
    assert len({variant.name for variant in DEFAULT_EXIT_VARIANTS}) == len(
        DEFAULT_EXIT_VARIANTS
    )


def test_parse_exit_variants_accepts_default_names_and_rejects_unknown():
    parsed = parse_exit_variants("baseline,time10,tight4_time10")

    assert [variant.name for variant in parsed] == [
        "baseline",
        "time10",
        "tight4_time10",
    ]
    with pytest.raises(ValueError, match="unknown exit variants"):
        parse_exit_variants("baseline,unknown")


def test_exit_variant_validates_policy():
    with pytest.raises(ValueError, match="stop_loss_pct"):
        ExitVariant("bad", stop_loss_pct=0.0, max_holding_days=10)
    with pytest.raises(ValueError, match="max_holding_days"):
        ExitVariant("bad", stop_loss_pct=0.06, max_holding_days=0)
