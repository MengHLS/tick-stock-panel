"""Maturity, purge, expanding folds and event-level ranking helpers."""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Sequence
from datetime import date

import numpy as np
import polars as pl

DEFAULT_FOLDS = (
    {
        "name": "2022",
        "test_start": date(2022, 1, 1),
        "test_end": date(2022, 12, 31),
    },
    {
        "name": "2023",
        "test_start": date(2023, 1, 1),
        "test_end": date(2023, 12, 31),
    },
    {
        "name": "2024",
        "test_start": date(2024, 1, 1),
        "test_end": date(2024, 12, 31),
    },
    {
        "name": "2025",
        "test_start": date(2025, 1, 1),
        "test_end": date(2025, 12, 31),
    },
    {
        "name": "2026",
        "test_start": date(2026, 1, 1),
        "test_end": date(2026, 9, 30),
    },
)


def _session_index(
    value: date,
    sessions: list[date],
) -> int | None:
    index = bisect_right(sessions, value) - 1
    return index if index >= 0 and sessions[index] == value else None


def _ready_date(
    value,
    sessions: list[date],
) -> date | None:
    if value is None:
        return None
    maturity = value.date() if hasattr(value, "date") else value
    index = _session_index(maturity, sessions)
    if index is None or index + 5 >= len(sessions):
        return None
    return sessions[index + 5]


def event_inverse_weights(samples: pl.DataFrame) -> pl.DataFrame:
    if samples.is_empty():
        return samples.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("sample_weight")
        )
    counts = samples.group_by("event_id").len(name="_event_decisions")
    return samples.join(counts, on="event_id", how="left").with_columns(
        (1.0 / pl.col("_event_decisions")).alias("sample_weight")
    ).drop("_event_decisions")


def assign_expanding_folds(
    samples: pl.DataFrame,
    sessions: Sequence[date],
    folds: Sequence[dict] = DEFAULT_FOLDS,
    purge_sessions: int = 30,
) -> pl.DataFrame:
    if purge_sessions < 0:
        raise ValueError("purge_sessions must be non-negative")
    if samples.is_empty():
        return samples
    required = {
        "decision_id",
        "event_id",
        "decision_date",
        "market_fillable",
        "label_maturity_time",
    }
    missing = required - set(samples.columns)
    if missing:
        raise ValueError(f"samples missing required columns: {sorted(missing)}")
    ordered_sessions = sorted(set(sessions))
    if not ordered_sessions:
        raise ValueError("sessions are required")

    prepared = samples.with_columns(
        pl.struct("decision_id", "label_maturity_time")
        .map_elements(
            lambda row: _ready_date(
                row["label_maturity_time"],
                ordered_sessions,
            ),
            return_dtype=pl.Date,
        )
        .alias("label_ready_date")
    )

    outputs: list[pl.DataFrame] = []
    for fold in folds:
        test_start = fold["test_start"]
        test_end = fold["test_end"]
        if test_start > test_end:
            raise ValueError("fold test range is invalid")
        test_start_index = bisect_right(ordered_sessions, test_start) - 1
        if (
            test_start_index < 0
            or ordered_sessions[test_start_index] != test_start
        ):
            test_start_index = bisect_right(ordered_sessions, test_start)
        purge_start_index = max(0, test_start_index - purge_sessions)

        event_state: dict[str, dict] = {}
        for row in prepared.iter_rows(named=True):
            decision_date = row["decision_date"]
            decision_index = _session_index(decision_date, ordered_sessions)
            if decision_index is None:
                continue
            state = event_state.setdefault(
                row["event_id"],
                {
                    "min_date": decision_date,
                    "max_date": decision_date,
                    "max_index": decision_index,
                    "mature": True,
                },
            )
            state["min_date"] = min(state["min_date"], decision_date)
            state["max_date"] = max(state["max_date"], decision_date)
            state["max_index"] = max(state["max_index"], decision_index)
            ready = row["label_ready_date"]
            ready_index = (
                _session_index(ready, ordered_sessions)
                if ready is not None
                else None
            )
            row_mature = (
                not row["market_fillable"]
                or (ready_index is not None and ready_index < test_start_index)
            )
            state["mature"] = state["mature"] and row_mature

        roles_by_event: dict[str, str] = {}
        for event_id, state in event_state.items():
            if state["min_date"] > test_end:
                role = "future"
            elif (
                state["min_date"] <= test_end
                and state["max_date"] >= test_start
            ):
                role = "validation"
            elif state["max_date"] < test_start:
                role = (
                    "train"
                    if state["max_index"] < purge_start_index
                    and state["mature"]
                    else "purged"
                )
            else:
                role = "future"
            roles_by_event[event_id] = role

        folded = prepared.with_columns(
            pl.lit(fold["name"]).alias("fold"),
            pl.col("event_id")
            .replace_strict(
                roles_by_event,
                default="future",
                return_dtype=pl.String,
            )
            .alias("role"),
        )
        folded = folded.with_columns(
            (
                1.0
                / pl.len().over(["fold", "role", "event_id"])
            ).alias("sample_weight")
        )
        outputs.append(folded)
    return pl.concat(outputs, how="diagonal_relaxed").sort(
        ["fold", "decision_date", "decision_id"]
    )


def freeze_top_decile_threshold(
    train_scored: pl.DataFrame,
    score_column: str = "score",
) -> float:
    scores = (
        train_scored.filter(
            pl.col("market_fillable")
            & pl.col(score_column).is_not_null()
            & pl.col(score_column).is_finite()
        )[score_column]
        .cast(pl.Float64)
        .to_numpy()
    )
    if scores.size == 0:
        raise ValueError("no fillable training scores are available")
    return float(np.quantile(scores, 0.9, method="linear"))


def first_top_decile_decisions(
    scored: pl.DataFrame,
    threshold: float,
    score_column: str = "score",
    *,
    eligible: pl.Expr | None = None,
) -> pl.DataFrame:
    eligibility = (
        pl.col("market_fillable")
        if eligible is None
        else eligible
    )
    return (
        scored.filter(
            eligibility
            & pl.col(score_column).is_not_null()
            & pl.col(score_column).is_finite()
            & (pl.col(score_column) >= threshold)
        )
        .sort(["event_id", "signal_available_time", "decision_id"])
        .unique(
            subset=["event_id"],
            keep="first",
            maintain_order=True,
        )
        .sort(["signal_available_time", "event_id"])
    )


def event_top_decile_decisions(
    scored: pl.DataFrame,
    score_column: str = "score",
    *,
    event_fraction: float = 0.1,
) -> pl.DataFrame:
    """Select the validation event top fraction and its best decision."""
    if not 0 < event_fraction <= 1:
        raise ValueError("event_fraction must be in (0, 1]")
    required = {
        "decision_id",
        "event_id",
        "signal_available_time",
        score_column,
    }
    missing = required - set(scored.columns)
    if missing:
        raise ValueError(
            f"scored frame missing required columns: {sorted(missing)}"
        )
    finite = scored.filter(
        pl.col(score_column).is_not_null()
        & pl.col(score_column).is_finite()
    )
    empty = scored.head(0).with_columns(
        pl.lit(None, dtype=pl.UInt32).alias("event_top_decile_rank"),
        pl.lit(None, dtype=pl.Float64).alias("event_top_decile_score"),
        pl.lit(None, dtype=pl.Float64).alias("event_top_decile_cutoff"),
    )
    if finite.is_empty():
        return empty
    event_scores = finite.group_by("event_id").agg(
        pl.col(score_column).max().alias("_event_score")
    )
    top_count = max(
        1,
        math.ceil(event_scores.height * event_fraction),
    )
    selected_events = (
        event_scores.sort(
            ["_event_score", "event_id"],
            descending=[True, False],
        )
        .with_row_index("event_top_decile_rank", offset=1)
        .head(top_count)
    )
    cutoff = float(selected_events["_event_score"].min())
    return (
        finite.join(selected_events, on="event_id", how="inner")
        .sort(
            [
                "event_id",
                score_column,
                "signal_available_time",
                "decision_id",
            ],
            descending=[False, True, False, False],
        )
        .unique(
            subset=["event_id"],
            keep="first",
            maintain_order=True,
        )
        .with_columns(
            pl.col("_event_score").alias("event_top_decile_score"),
            pl.lit(cutoff).alias("event_top_decile_cutoff"),
        )
        .drop("_event_score")
        .sort(
            [
                "event_top_decile_rank",
                "signal_available_time",
                "event_id",
            ]
        )
    )
