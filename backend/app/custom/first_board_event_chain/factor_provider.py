"""FactorProvider registration for first-board event-chain fields."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import polars as pl

from app.custom.first_board_event_chain.compute import (
    DEFAULT_LOOKBACK_BARS,
    DEFAULT_MIN_PULLBACK_PCT,
    EVENT_CHAIN_DEPENDENCIES,
    EVENT_CHAIN_FIELDS,
    EventChainConfig,
    compute_event_chain_outputs,
    materialize_event_chain_columns,
)
from app.custom.first_board_event_chain.factor_specs import EVENT_CHAIN_FACTOR_SPECS
from app.extensions.factors import (
    FactorProvider,
    FactorProviderContext,
)


class FirstBoardEventChainProvider(FactorProvider):
    provider_id = "official.first-board-event-chain"
    version = 1
    kind = "frame"
    factor_ids = frozenset(EVENT_CHAIN_FIELDS)
    factor_specs = EVENT_CHAIN_FACTOR_SPECS

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
        return self._matrix_outputs(market, context=None)[factor_id]

    def materialize_matrix(
        self,
        market: Any,
        names: frozenset[str],
        context: FactorProviderContext,
    ) -> Any:
        outputs = self._matrix_outputs(market, context=context)
        requested = {
            name: outputs[name]
            for name in names
            if name in outputs
        }
        if not requested:
            return market
        return replace(market, fields={**market.fields, **requested})

    def _matrix_outputs(
        self,
        market: Any,
        *,
        context: FactorProviderContext | None,
    ) -> dict[str, Any]:
        params = context.params if context is not None else {}
        return compute_event_chain_outputs(
            market.open,
            market.high,
            market.low,
            market.close,
            market.field("consecutive_limit_ups"),
            EventChainConfig(
                lookback_bars=int(
                    params.get("lookback_bars", DEFAULT_LOOKBACK_BARS)
                ),
                min_pullback_pct=float(
                    params.get("min_pullback_pct", DEFAULT_MIN_PULLBACK_PCT)
                ),
                require_new_high_after_anchor=bool(
                    params.get("require_new_high_after_anchor", True)
                ),
            ),
        )


PROVIDER = FirstBoardEventChainProvider()
FACTOR_PROVIDERS = (PROVIDER,)
