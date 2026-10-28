from __future__ import annotations

import numpy as np

from scripts.first_board_rationing_study import (
    ADMISSION_PROFILES,
    apply_cooldown,
    limit_top_rank,
)


def test_limit_top_rank_orders_by_score_and_preserves_asset_ties() -> None:
    eligible = np.array([
        [True, True, True, True],
        [True, True, False, False],
    ])
    score = np.array([
        [80.0, 90.0, 90.0, 70.0],
        [50.0, 50.0, 99.0, 99.0],
    ], dtype=np.float32)

    selected = limit_top_rank(eligible, score, 2)

    assert selected.tolist() == [
        [False, True, True, False],
        [True, True, False, False],
    ]


def test_cooldown_blocks_reentry_and_only_selected_signal_renews_it() -> None:
    selected = np.zeros((8, 1), dtype=bool)
    selected[[0, 3, 6], 0] = True

    cooled = apply_cooldown(selected, 5)

    assert cooled[:, 0].tolist() == [
        True,
        False,
        False,
        False,
        False,
        False,
        True,
        False,
    ]


def test_zero_cooldown_is_a_value_copy() -> None:
    selected = np.array([[True], [False]])

    cooled = apply_cooldown(selected, 0)

    np.testing.assert_array_equal(cooled, selected)
    cooled[0, 0] = False
    assert selected[0, 0]


def test_admission_profiles_are_unique_and_expected() -> None:
    by_id = {profile.id: profile for profile in ADMISSION_PROFILES}

    assert len(by_id) == len(ADMISSION_PROFILES)
    assert by_id["asset_top20"].mode == "asset"
    assert by_id["score_top20"].top_k == 20
    assert by_id["score_top5"].top_k == 5
    assert by_id["score_top3"].top_k == 3
    assert by_id["score_top1"].top_k == 1
    assert by_id["score_top5_cooldown5"].cooldown_bars == 5
