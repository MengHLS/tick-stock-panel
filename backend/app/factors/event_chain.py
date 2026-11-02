"""Compatibility exports for the first-board event-chain provider.

New dispatch code must use ``app.extensions.factors``. This module remains for
existing research, strategy, and test imports during migration.
"""
from app.custom.first_board_event_chain.compute import (
    DEFAULT_EVENT_CHAIN_CONFIG,
    DEFAULT_LOOKBACK_BARS,
    DEFAULT_MIN_PULLBACK_PCT,
    EVENT_CHAIN_DEPENDENCIES,
    EVENT_CHAIN_FIELD_SET,
    EVENT_CHAIN_FIELDS,
    EVENT_CHAIN_STAGE_EARLY_BREAKOUT,
    EVENT_CHAIN_STAGE_INCOMPLETE,
    EVENT_CHAIN_STAGE_LABELS,
    EVENT_CHAIN_STAGE_NO_ANCHOR,
    EVENT_CHAIN_STAGE_RECOVERED_NOT_BREAKOUT,
    EVENT_CHAIN_STAGE_SHALLOW_PULLBACK,
    EVENT_CHAIN_STAGE_STRICT_REBREAK,
    EventChainConfig,
    _evaluate_anchor,
    compute_event_chain_outputs,
    is_event_chain_factor,
    materialize_event_chain_columns,
)

__all__ = [
    "DEFAULT_EVENT_CHAIN_CONFIG",
    "DEFAULT_LOOKBACK_BARS",
    "DEFAULT_MIN_PULLBACK_PCT",
    "EVENT_CHAIN_DEPENDENCIES",
    "EVENT_CHAIN_FIELD_SET",
    "EVENT_CHAIN_FIELDS",
    "EVENT_CHAIN_STAGE_EARLY_BREAKOUT",
    "EVENT_CHAIN_STAGE_INCOMPLETE",
    "EVENT_CHAIN_STAGE_LABELS",
    "EVENT_CHAIN_STAGE_NO_ANCHOR",
    "EVENT_CHAIN_STAGE_RECOVERED_NOT_BREAKOUT",
    "EVENT_CHAIN_STAGE_SHALLOW_PULLBACK",
    "EVENT_CHAIN_STAGE_STRICT_REBREAK",
    "EventChainConfig",
    "compute_event_chain_outputs",
    "is_event_chain_factor",
    "materialize_event_chain_columns",
]
