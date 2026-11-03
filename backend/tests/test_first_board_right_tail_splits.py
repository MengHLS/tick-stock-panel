from __future__ import annotations

from datetime import date, datetime, time, timedelta

import polars as pl
import pytest

from scripts.first_board_right_tail_lab.splits import (
    assign_expanding_folds,
    event_inverse_weights,
    event_top_decile_decisions,
    first_top_decile_decisions,
    freeze_top_decile_threshold,
)


def _sessions(count: int = 100) -> list[date]:
    start = date(2025, 1, 1)
    return [start + timedelta(days=index) for index in range(count)]


def _fold(sessions: list[date]) -> list[dict]:
    return [
        {
            "name": "custom",
            "test_start": sessions[50],
            "test_end": sessions[79],
        }
    ]


def _maturity(day: date) -> datetime:
    return datetime.combine(day, time(15, 0))


def test_fold_assignment_applies_maturity_and_exact_purge_boundary():
    sessions = _sessions()
    samples = pl.DataFrame(
        {
            "decision_id": ["train", "purged", "late_label", "valid", "future"],
            "event_id": ["e1", "e2", "e3", "e4", "e5"],
            "decision_date": [
                sessions[19],
                sessions[20],
                sessions[10],
                sessions[50],
                sessions[80],
            ],
            "signal_available_time": [
                datetime.combine(sessions[19], time(10, 0)),
                datetime.combine(sessions[20], time(10, 0)),
                datetime.combine(sessions[10], time(10, 0)),
                datetime.combine(sessions[50], time(10, 0)),
                datetime.combine(sessions[80], time(10, 0)),
            ],
            "label_maturity_time": [
                _maturity(sessions[39]),
                _maturity(sessions[40]),
                _maturity(sessions[49]),
                _maturity(sessions[69]),
                _maturity(sessions[99]),
            ],
            "market_fillable": [True, True, True, False, True],
        }
    )

    assigned = assign_expanding_folds(
        samples,
        sessions,
        folds=_fold(sessions),
        purge_sessions=30,
    )
    roles = dict(zip(assigned["decision_id"], assigned["role"], strict=True))

    assert roles == {
        "train": "train",
        "purged": "purged",
        "late_label": "purged",
        "valid": "validation",
        "future": "future",
    }
    assert assigned.filter(pl.col("decision_id") == "train")[
        "label_ready_date"
    ][0] == sessions[44]


def test_event_inverse_weights_normalize_each_event_to_one():
    samples = pl.DataFrame(
        {
            "decision_id": ["a", "b", "c"],
            "event_id": ["event-1", "event-1", "event-2"],
        }
    )

    weighted = event_inverse_weights(samples)

    assert weighted["sample_weight"].to_list() == [0.5, 0.5, 1.0]
    grouped = weighted.group_by("event_id").agg(
        pl.col("sample_weight").sum()
    )
    assert grouped["sample_weight"].to_list() == [1.0, 1.0]


def test_top_decile_threshold_uses_fillable_training_scores_only():
    train = pl.DataFrame(
        {
            "decision_id": [str(index) for index in range(11)],
            "market_fillable": [True] * 10 + [False],
            "score": [float(index) for index in range(10)] + [100.0],
        }
    )

    threshold = freeze_top_decile_threshold(train)

    assert threshold == pytest.approx(8.1)


def test_first_top_decile_keeps_earliest_decision_per_event():
    scored = pl.DataFrame(
        {
            "decision_id": ["e1-late", "e1-early", "e2", "unfilled"],
            "event_id": ["e1", "e1", "e2", "e3"],
            "signal_available_time": [
                datetime(2026, 1, 5, 10, 0),
                datetime(2026, 1, 5, 9, 45),
                datetime(2026, 1, 5, 9, 50),
                datetime(2026, 1, 5, 9, 40),
            ],
            "market_fillable": [True, True, True, False],
            "score": [9.0, 8.5, 8.2, 10.0],
        }
    )

    selected = first_top_decile_decisions(scored, 8.0)

    assert selected["decision_id"].to_list() == ["e1-early", "e2"]


def test_first_top_decile_rejects_non_finite_scores():
    scored = pl.DataFrame(
        {
            "decision_id": ["finite", "nan", "infinite"],
            "event_id": ["e1", "e2", "e3"],
            "signal_available_time": [
                datetime(2026, 1, 5, 9, 45),
                datetime(2026, 1, 5, 9, 50),
                datetime(2026, 1, 5, 9, 55),
            ],
            "market_fillable": [True, True, True],
            "score": [8.5, float("nan"), float("inf")],
        }
    )

    selected = first_top_decile_decisions(scored, 8.0)

    assert selected["decision_id"].to_list() == ["finite"]


def test_event_top_decile_selects_best_decision_from_exact_event_fraction():
    scored = pl.DataFrame(
        {
            "decision_id": [
                *[f"event-{index}" for index in range(9)],
                "event-9-early",
                "event-9-best",
            ],
            "event_id": [
                *[f"event-{index}" for index in range(9)],
                "event-9",
                "event-9",
            ],
            "signal_available_time": [
                *[
                    datetime(2026, 1, 5, 9, 40 + index)
                    for index in range(9)
                ],
                datetime(2026, 1, 5, 9, 50),
                datetime(2026, 1, 5, 9, 55),
            ],
            "score": [
                *[float(index) for index in range(9)],
                8.0,
                10.0,
            ],
        }
    )

    selected = event_top_decile_decisions(scored)

    assert selected["decision_id"].to_list() == ["event-9-best"]
    assert selected["event_top_decile_rank"].to_list() == [1]
    assert selected["event_top_decile_score"].to_list() == [10.0]
    assert selected["event_top_decile_cutoff"].to_list() == [10.0]


def test_event_top_decile_uses_ceiling_and_ignores_non_finite_scores():
    event_count = 11
    scored = pl.DataFrame(
        {
            "decision_id": [f"finite-{index}" for index in range(event_count)]
            + ["nan", "infinite"],
            "event_id": [f"event-{index}" for index in range(event_count)]
            + ["nan-event", "infinite-event"],
            "signal_available_time": [
                datetime(2026, 1, 5, 9, 40)
                for _ in range(event_count + 2)
            ],
            "score": [
                *[float(index) for index in range(event_count)],
                float("nan"),
                float("inf"),
            ],
        }
    )

    selected = event_top_decile_decisions(scored)

    assert selected["event_id"].to_list() == ["event-10", "event-9"]
    assert selected["event_top_decile_rank"].to_list() == [1, 2]
    assert selected["event_top_decile_cutoff"].to_list() == [9.0, 9.0]


@pytest.mark.parametrize("fraction", [0.0, -0.1, 1.1])
def test_event_top_decile_rejects_invalid_fraction(fraction: float):
    scored = pl.DataFrame(
        {
            "decision_id": ["event-1"],
            "event_id": ["event-1"],
            "signal_available_time": [datetime(2026, 1, 5, 9, 40)],
            "score": [1.0],
        }
    )

    with pytest.raises(ValueError, match="event_fraction"):
        event_top_decile_decisions(scored, event_fraction=fraction)


def test_event_crossing_test_boundary_stays_entirely_in_validation():
    sessions = _sessions()
    samples = pl.DataFrame(
        {
            "decision_id": ["before", "inside"],
            "event_id": ["crossing", "crossing"],
            "decision_date": [sessions[49], sessions[50]],
            "signal_available_time": [
                datetime.combine(sessions[49], time(10, 0)),
                datetime.combine(sessions[50], time(10, 0)),
            ],
            "label_maturity_time": [
                _maturity(sessions[69]),
                _maturity(sessions[70]),
            ],
            "market_fillable": [True, True],
        }
    )

    assigned = assign_expanding_folds(
        samples,
        sessions,
        folds=_fold(sessions),
        purge_sessions=30,
    )

    assert assigned["role"].unique().to_list() == ["validation"]
    assert assigned["sample_weight"].to_list() == [0.5, 0.5]


def test_event_with_any_purged_decision_is_purged_atomically():
    sessions = _sessions()
    samples = pl.DataFrame(
        {
            "decision_id": ["before-purge", "inside-purge"],
            "event_id": ["event", "event"],
            "decision_date": [sessions[19], sessions[20]],
            "signal_available_time": [
                datetime.combine(sessions[19], time(10, 0)),
                datetime.combine(sessions[20], time(10, 0)),
            ],
            "label_maturity_time": [
                _maturity(sessions[39]),
                _maturity(sessions[40]),
            ],
            "market_fillable": [True, True],
        }
    )

    assigned = assign_expanding_folds(
        samples,
        sessions,
        folds=_fold(sessions),
        purge_sessions=30,
    )

    assert assigned["role"].unique().to_list() == ["purged"]
