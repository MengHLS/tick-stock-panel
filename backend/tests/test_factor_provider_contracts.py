from __future__ import annotations

from datetime import date

import polars as pl

from app.custom.first_board_event_chain.compute import (
    EVENT_CHAIN_FIELDS,
    materialize_event_chain_columns,
)
from app.extensions.factors import (
    FactorProvider,
    FactorProviderContext,
    ensure_factor_providers,
    factor_provider_for,
    materialize_factor_columns,
    provider_factor_ids,
    register_factor_provider,
    sidecar_factor_ids,
    unregister_factor_provider,
)
from app.factors.registry import FactorSpec, get_factor


def _event_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": ["000001.SZ"] * 5,
            "date": [date(2026, 1, day) for day in range(1, 6)],
            "open": [10.0, 10.1, 10.2, 10.3, 10.4],
            "high": [10.2, 10.3, 10.4, 10.5, 10.6],
            "low": [9.9, 10.0, 10.1, 10.2, 10.3],
            "close": [10.1, 10.2, 10.0, 10.3, 10.5],
            "consecutive_limit_ups": [0, 1, 0, 0, 1],
        }
    )


def test_provider_discovery_routes_event_chain_and_linkage() -> None:
    ensure_factor_providers()

    assert "first_board_chain_stage" in provider_factor_ids(
        ["first_board_chain_stage"]
    )
    assert factor_provider_for("first_board_chain_stage").kind == "frame"
    assert "deviate_3d" in sidecar_factor_ids()
    assert factor_provider_for("deviate_3d").kind == "sidecar"


def test_generic_frame_materialization_matches_event_chain_kernel() -> None:
    frame = _event_frame()
    expected = materialize_event_chain_columns(frame, EVENT_CHAIN_FIELDS)

    actual = materialize_factor_columns(
        frame,
        EVENT_CHAIN_FIELDS,
        context=FactorProviderContext(data_dir=None),
    )

    assert actual.equals(expected)


def test_provider_specs_keep_factor_spec_as_metadata_catalog() -> None:
    spec = get_factor("first_board_chain_stage")
    assert spec is not None
    assert spec.kind == "virtual"
    assert spec.warmup_bars > 1


def test_register_factor_provider_registers_metadata_once() -> None:
    class _Provider(FactorProvider):
        provider_id = "test.factor-provider"
        version = 1
        factor_ids = frozenset({"test_provider_value"})
        factor_specs = (
            FactorSpec(
                id="test_provider_value",
                label="Provider test",
                group="test",
                formula_text="close / open",
            ),
        )

        def dependencies(self, factor_id: str) -> frozenset[str]:
            del factor_id
            return frozenset({"close", "open"})

        def warmup_bars(self, factor_id: str) -> int:
            del factor_id
            return 1

        def materialize_frame(
            self,
            frame: pl.DataFrame,
            names: frozenset[str],
            context: FactorProviderContext,
        ) -> pl.DataFrame:
            del context
            if not names:
                return frame
            return frame.with_columns(
                (pl.col("close") / pl.col("open")).alias("test_provider_value")
            )

    provider = _Provider()
    register_factor_provider(provider)
    try:
        assert factor_provider_for("test_provider_value") is provider
        assert provider.params("test_provider_value") == {}
        assert provider.null_policy("test_provider_value") == "keep"
        assert get_factor("test_provider_value") is not None
    finally:
        unregister_factor_provider(provider.provider_id)
