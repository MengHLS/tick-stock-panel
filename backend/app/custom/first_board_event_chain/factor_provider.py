"""FactorProvider registration for first-board event-chain fields."""
from __future__ import annotations

from typing import Any

import polars as pl

from app.custom.first_board_event_chain.compute import (
    DEFAULT_LOOKBACK_BARS,
    EVENT_CHAIN_DEPENDENCIES,
    EVENT_CHAIN_FIELDS,
    compute_event_chain_outputs,
    materialize_event_chain_columns,
)
from app.extensions.factors import (
    FactorProvider,
    FactorProviderContext,
)


class FirstBoardEventChainProvider(FactorProvider):
    provider_id = "official.first-board-event-chain"
    version = 1
    kind = "frame"
    factor_ids = frozenset(EVENT_CHAIN_FIELDS)

    def dependencies(self, factor_id: str) -> frozenset[str]:
        del factor_id
        return EVENT_CHAIN_DEPENDENCIES

    def warmup_bars(self, factor_id: str) -> int:
        del factor_id
        return DEFAULT_LOOKBACK_BARS + 1

    def materialize_frame(
        self,
        frame: pl.DataFrame,
        names: frozenset[str],
        context: FactorProviderContext,
    ) -> pl.DataFrame:
        del context
        requested = [name for name in EVENT_CHAIN_FIELDS if name in names]
        return materialize_event_chain_columns(frame, requested)

    def materialize_matrix_field(self, market: Any, factor_id: str) -> Any:
        if factor_id not in EVENT_CHAIN_FIELDS:
            return None
        return compute_event_chain_outputs(
            market.open,
            market.high,
            market.low,
            market.close,
            market.field("consecutive_limit_ups"),
        )[factor_id]


PROVIDER = FirstBoardEventChainProvider()
FACTOR_PROVIDERS = (PROVIDER,)
