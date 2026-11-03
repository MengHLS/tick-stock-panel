"""Finite-lookback first-board event-chain factors.

The chain is deliberately separate from the formula DSL: selecting a prior
first board and deciding whether to recurse to an older anchor is a stateful
cross-event operation. Polars and the NumPy matrix both adapt into the same
per-symbol kernel implemented here.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Any

import numpy as np
import polars as pl

DEFAULT_LOOKBACK_BARS = 250
DEFAULT_MIN_PULLBACK_PCT = 0.05

EVENT_CHAIN_STAGE_NO_ANCHOR = 0
EVENT_CHAIN_STAGE_INCOMPLETE = 1
EVENT_CHAIN_STAGE_SHALLOW_PULLBACK = 2
EVENT_CHAIN_STAGE_RECOVERED_NOT_BREAKOUT = 3
EVENT_CHAIN_STAGE_EARLY_BREAKOUT = 4
EVENT_CHAIN_STAGE_STRICT_REBREAK = 5

EVENT_CHAIN_STAGE_LABELS: dict[int, str] = {
    EVENT_CHAIN_STAGE_NO_ANCHOR: "无前次首板",
    EVENT_CHAIN_STAGE_INCOMPLETE: "结构不完整",
    EVENT_CHAIN_STAGE_SHALLOW_PULLBACK: "回调太浅",
    EVENT_CHAIN_STAGE_RECOVERED_NOT_BREAKOUT: "回攻未过前高",
    EVENT_CHAIN_STAGE_EARLY_BREAKOUT: "目标前已突破",
    EVENT_CHAIN_STAGE_STRICT_REBREAK: "首次收盘突破",
}

EVENT_CHAIN_FIELDS: tuple[str, ...] = (
    "first_board_chain_stage",
    "first_board_chain_anchor_distance",
    "first_board_chain_pullback_pct",
    "first_board_chain_target_above_reference_pct",
    "first_board_chain_strict_rebreak",
    "first_board_chain_early_breakout",
    "first_board_chain_recovered_not_breakout",
    "first_board_chain_seed_close_preserved",
    "first_board_chain_seed_low_preserved",
)
EVENT_CHAIN_FIELD_SET = frozenset(EVENT_CHAIN_FIELDS)
EVENT_CHAIN_DEPENDENCIES = frozenset({
    "open",
    "high",
    "low",
    "close",
    "consecutive_limit_ups",
})


@dataclass(frozen=True)
class EventChainConfig:
    lookback_bars: int = DEFAULT_LOOKBACK_BARS
    min_pullback_pct: float = DEFAULT_MIN_PULLBACK_PCT
    require_new_high_after_anchor: bool = True

    def __post_init__(self) -> None:
        if not 1 <= int(self.lookback_bars) <= 512:
            raise ValueError("event-chain lookback_bars must be between 1 and 512")
        if not 0.0 <= float(self.min_pullback_pct) < 1.0:
            raise ValueError("event-chain min_pullback_pct must be in [0, 1)")


DEFAULT_EVENT_CHAIN_CONFIG = EventChainConfig()


def is_event_chain_factor(name: str) -> bool:
    return name in EVENT_CHAIN_FIELD_SET


@dataclass(frozen=True)
class _Candidate:
    stage: int
    anchor_index: int
    terminal: bool
    missing: bool = False
    pullback_pct: float | None = None
    target_above_reference_pct: float | None = None
    seed_close_preserved: bool = False
    seed_low_preserved: bool = False


def compute_event_chain_outputs(
    open_values: np.ndarray,
    high_values: np.ndarray,
    low_values: np.ndarray,
    close_values: np.ndarray,
    consecutive_limit_ups: np.ndarray,
    config: EventChainConfig | None = None,
) -> dict[str, np.ndarray]:
    """Compute all event-chain fields on a ``time x asset`` array."""
    cfg = config or DEFAULT_EVENT_CHAIN_CONFIG
    open_array = np.asarray(open_values, dtype=np.float64)
    high_array = np.asarray(high_values, dtype=np.float64)
    low_array = np.asarray(low_values, dtype=np.float64)
    close_array = np.asarray(close_values, dtype=np.float64)
    consecutive = np.asarray(consecutive_limit_ups, dtype=np.float64)
    shape = close_array.shape
    if close_array.ndim != 2:
        raise ValueError("event-chain inputs must be two-dimensional")
    if any(
        array.shape != shape
        for array in (open_array, high_array, low_array, consecutive)
    ):
        raise ValueError("event-chain input shapes do not match")

    outputs = {
        name: np.full(shape, np.nan, dtype=np.float32)
        for name in EVENT_CHAIN_FIELDS
    }
    price_valid = (
        np.isfinite(open_array)
        & np.isfinite(high_array)
        & np.isfinite(low_array)
        & np.isfinite(close_array)
        & (open_array > 0)
        & (high_array > 0)
        & (low_array > 0)
        & (close_array > 0)
    )
    first_board = np.isfinite(consecutive) & (consecutive == 1.0)

    for asset_id in range(shape[1]):
        anchor_indices = np.flatnonzero(first_board[:, asset_id])
        target_indices = anchor_indices
        for target_index in target_indices:
            _compute_target(
                outputs,
                asset_id,
                int(target_index),
                anchor_indices,
                open_array[:, asset_id],
                high_array[:, asset_id],
                low_array[:, asset_id],
                close_array[:, asset_id],
                price_valid[:, asset_id],
                cfg,
            )
    return outputs


def _compute_target(
    outputs: dict[str, np.ndarray],
    asset_id: int,
    target_index: int,
    anchor_indices: np.ndarray,
    open_values: np.ndarray,
    high_values: np.ndarray,
    low_values: np.ndarray,
    close_values: np.ndarray,
    price_valid: np.ndarray,
    config: EventChainConfig,
) -> None:
    del open_values
    if not price_valid[target_index]:
        _write_candidate(outputs, asset_id, target_index, _Candidate(
            stage=EVENT_CHAIN_STAGE_INCOMPLETE,
            anchor_index=-1,
            terminal=True,
            missing=True,
        ))
        return

    lower_bound = target_index - int(config.lookback_bars)
    candidate_start = int(np.searchsorted(anchor_indices, lower_bound, side="left"))
    candidate_stop = int(np.searchsorted(anchor_indices, target_index, side="left"))
    candidates = anchor_indices[candidate_start:candidate_stop]
    if candidates.size == 0:
        _write_candidate(outputs, asset_id, target_index, _Candidate(
            stage=EVENT_CHAIN_STAGE_NO_ANCHOR,
            anchor_index=-1,
            terminal=True,
        ))
        return

    nearest: _Candidate | None = None
    for anchor_index_value in candidates[::-1]:
        candidate = _evaluate_anchor(
            int(anchor_index_value),
            target_index,
            high_values,
            low_values,
            close_values,
            price_valid,
            config,
        )
        if nearest is None:
            nearest = candidate
        if candidate.missing or candidate.terminal:
            _write_candidate(outputs, asset_id, target_index, candidate)
            return
    assert nearest is not None
    _write_candidate(outputs, asset_id, target_index, nearest)


def _evaluate_anchor(
    anchor_index: int,
    target_index: int,
    high_values: np.ndarray,
    low_values: np.ndarray,
    close_values: np.ndarray,
    price_valid: np.ndarray,
    config: EventChainConfig,
) -> _Candidate:
    if not price_valid[anchor_index:target_index + 1].all():
        return _Candidate(
            stage=EVENT_CHAIN_STAGE_INCOMPLETE,
            anchor_index=anchor_index,
            terminal=True,
            missing=True,
        )

    reference_high = float(high_values[anchor_index])
    pullback_index: int | None = None
    for index in range(anchor_index + 1, target_index):
        if close_values[index] < close_values[index - 1]:
            pullback_index = index
            break
        reference_high = max(reference_high, float(high_values[index]))

    if pullback_index is None:
        return _Candidate(
            stage=EVENT_CHAIN_STAGE_INCOMPLETE,
            anchor_index=anchor_index,
            terminal=False,
        )

    anchor_high = float(high_values[anchor_index])
    if config.require_new_high_after_anchor and reference_high <= anchor_high:
        return _Candidate(
            stage=EVENT_CHAIN_STAGE_INCOMPLETE,
            anchor_index=anchor_index,
            terminal=False,
        )

    pullback_low = float(np.min(low_values[pullback_index:target_index]))
    pullback_pct = 1.0 - pullback_low / reference_high
    target_above_reference_pct = float(close_values[target_index]) / reference_high - 1.0
    seed_close_preserved = pullback_low >= float(close_values[anchor_index])
    seed_low_preserved = pullback_low >= float(low_values[anchor_index])

    earlier_breakout = bool(
        np.any(close_values[pullback_index:target_index] > reference_high)
    )
    if earlier_breakout:
        return _Candidate(
            stage=EVENT_CHAIN_STAGE_EARLY_BREAKOUT,
            anchor_index=anchor_index,
            terminal=True,
            pullback_pct=pullback_pct,
            target_above_reference_pct=target_above_reference_pct,
            seed_close_preserved=seed_close_preserved,
            seed_low_preserved=seed_low_preserved,
        )

    if pullback_pct < float(config.min_pullback_pct):
        return _Candidate(
            stage=EVENT_CHAIN_STAGE_SHALLOW_PULLBACK,
            anchor_index=anchor_index,
            terminal=False,
            pullback_pct=pullback_pct,
            target_above_reference_pct=target_above_reference_pct,
            seed_close_preserved=seed_close_preserved,
            seed_low_preserved=seed_low_preserved,
        )

    stage = (
        EVENT_CHAIN_STAGE_STRICT_REBREAK
        if float(close_values[target_index]) > reference_high
        else EVENT_CHAIN_STAGE_RECOVERED_NOT_BREAKOUT
    )
    return _Candidate(
        stage=stage,
        anchor_index=anchor_index,
        terminal=True,
        pullback_pct=pullback_pct,
        target_above_reference_pct=target_above_reference_pct,
        seed_close_preserved=seed_close_preserved,
        seed_low_preserved=seed_low_preserved,
    )


def _write_candidate(
    outputs: dict[str, np.ndarray],
    asset_id: int,
    target_index: int,
    candidate: _Candidate,
) -> None:
    outputs["first_board_chain_stage"][target_index, asset_id] = candidate.stage
    if candidate.anchor_index >= 0:
        outputs["first_board_chain_anchor_distance"][target_index, asset_id] = (
            target_index - candidate.anchor_index
        )
    if candidate.pullback_pct is not None:
        outputs["first_board_chain_pullback_pct"][target_index, asset_id] = (
            candidate.pullback_pct
        )
    if candidate.target_above_reference_pct is not None:
        outputs["first_board_chain_target_above_reference_pct"][
            target_index,
            asset_id,
        ] = candidate.target_above_reference_pct

    outputs["first_board_chain_strict_rebreak"][target_index, asset_id] = (
        1.0 if candidate.stage == EVENT_CHAIN_STAGE_STRICT_REBREAK else 0.0
    )
    outputs["first_board_chain_early_breakout"][target_index, asset_id] = (
        1.0 if candidate.stage == EVENT_CHAIN_STAGE_EARLY_BREAKOUT else 0.0
    )
    outputs["first_board_chain_recovered_not_breakout"][target_index, asset_id] = (
        1.0 if candidate.stage == EVENT_CHAIN_STAGE_RECOVERED_NOT_BREAKOUT else 0.0
    )
    outputs["first_board_chain_seed_close_preserved"][target_index, asset_id] = (
        1.0 if candidate.seed_close_preserved else 0.0
    )
    outputs["first_board_chain_seed_low_preserved"][target_index, asset_id] = (
        1.0 if candidate.seed_low_preserved else 0.0
    )


def materialize_event_chain_columns(
    frame: pl.DataFrame,
    names: Any,
    *,
    config: EventChainConfig | None = None,
) -> pl.DataFrame:
    """Add requested event-chain columns without changing row order."""
    requested = [
        str(name)
        for name in dict.fromkeys(names)
        if str(name) in EVENT_CHAIN_FIELD_SET and str(name) not in frame.columns
    ]
    if not requested or not EVENT_CHAIN_DEPENDENCIES.issubset(frame.columns):
        return frame

    ordered = frame.with_row_index("__event_chain_row").sort(["symbol", "date"])
    symbols = ordered["symbol"].cast(pl.Utf8).to_list()
    if not symbols:
        return frame

    outputs = {
        name: np.full(ordered.height, np.nan, dtype=np.float32)
        for name in EVENT_CHAIN_FIELDS
    }
    starts = [0]
    for index in range(1, len(symbols)):
        if symbols[index] != symbols[index - 1]:
            starts.append(index)
    starts.append(len(symbols))

    for start, stop in pairwise(starts):
        group = ordered[start:stop]
        group_outputs = compute_event_chain_outputs(
            group["open"].to_numpy().reshape(-1, 1),
            group["high"].to_numpy().reshape(-1, 1),
            group["low"].to_numpy().reshape(-1, 1),
            group["close"].to_numpy().reshape(-1, 1),
            group["consecutive_limit_ups"].to_numpy().reshape(-1, 1),
            config,
        )
        for name in EVENT_CHAIN_FIELDS:
            outputs[name][start:stop] = group_outputs[name][:, 0]

    materialized = ordered.with_columns([
        pl.Series(name, outputs[name])
        for name in requested
    ])
    return (
        materialized.sort("__event_chain_row")
        .drop("__event_chain_row")
    )
