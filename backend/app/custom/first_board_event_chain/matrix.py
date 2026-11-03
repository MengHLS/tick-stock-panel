"""Matrix adapter for first-board event-chain strategies."""
from __future__ import annotations

import numpy as np

from app.backtest.matrix import MarketDataMatrix
from app.custom.first_board_event_chain.compute import (
    DEFAULT_LOOKBACK_BARS,
    DEFAULT_MIN_PULLBACK_PCT,
    EventChainConfig,
    compute_event_chain_outputs,
)


def compute_matrix_event_chain(
    market: MarketDataMatrix,
    *,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
    min_pullback_pct: float = DEFAULT_MIN_PULLBACK_PCT,
    require_new_high_after_anchor: bool = True,
) -> dict[str, np.ndarray]:
    """Compute all event-chain fields from the shared matrix kernel."""
    return compute_event_chain_outputs(
        market.open,
        market.high,
        market.low,
        market.close,
        market.field("consecutive_limit_ups"),
        EventChainConfig(
            lookback_bars=lookback_bars,
            min_pullback_pct=min_pullback_pct,
            require_new_high_after_anchor=require_new_high_after_anchor,
        ),
    )
