"""FactorProvider for the independently published linkage sidecar."""
from __future__ import annotations

from typing import Any, Literal

import polars as pl

from app.custom.cross_sectional_linkage import store as linkage_store
from app.custom.cross_sectional_linkage.compute import (
    DEVIATION_FACTOR_IDS,
    LINKAGE_FACTOR_IDS,
)
from app.extensions.factors import (
    FactorProvider,
    FactorProviderContext,
)

_WARMUP = {
    "deviate_3d": 4,
    "deviate_10d": 11,
    "deviate_30d": 31,
    "industry_relative_momentum_20d": 21,
    "industry_rank_momentum_20d": 21,
    "industry_corr_60d": 61,
    "industry_beta_60d": 61,
}


class CrossSectionalLinkageProvider(FactorProvider):
    provider_id = "official.cross-sectional-linkage"
    version = 1
    kind = "sidecar"
    factor_ids = frozenset(LINKAGE_FACTOR_IDS)
    transient_errors = (linkage_store.LinkageReadUnstableError,)
    coverage_errors = (linkage_store.LinkageCoverageError,)

    def dependencies(self, factor_id: str) -> frozenset[str]:
        del factor_id
        return frozenset()

    def warmup_bars(self, factor_id: str) -> int:
        return _WARMUP[factor_id]

    def generation(self, context: FactorProviderContext) -> str | None:
        if context.data_dir is None:
            return None
        return linkage_store.get_enriched_generation(context.data_dir, "linkage")

    def materialize_frame(
        self,
        frame: pl.DataFrame,
        names: frozenset[str],
        context: FactorProviderContext,
    ) -> pl.DataFrame:
        requested = frozenset(names) & LINKAGE_FACTOR_IDS
        if frame.is_empty() or not requested:
            return frame
        if context.data_dir is None:
            raise linkage_store.LinkageCoverageError(
                "联动因子需要稳定的数据目录 (data_dir)"
            )
        expected = context.expected_generation
        if expected is None:
            expected = self.generation(context)

        if not context.allow_tail_nulls or "date" not in frame.columns:
            return linkage_store.attach_linkage_columns(
                frame,
                requested,
                context.data_dir,
                expected_generation=expected,
                require_complete=context.require_complete,
            )

        deviation_names = requested & DEVIATION_FACTOR_IDS
        if not deviation_names:
            return linkage_store.attach_linkage_columns(
                frame,
                requested,
                context.data_dir,
                expected_generation=expected,
                require_complete=context.require_complete,
            )
        finalized = linkage_store.linkage_finalized_through(
            context.data_dir,
            expected_generation=expected,
        )
        indexed = frame.with_row_index("_linkage_row")
        covered = indexed.filter(pl.col("date") <= finalized)
        beyond = indexed.filter(pl.col("date") > finalized)
        industry_names = requested - deviation_names
        if industry_names and not beyond.is_empty():
            linkage_store.attach_linkage_columns(
                beyond,
                industry_names,
                context.data_dir,
                expected_generation=expected,
                require_complete=True,
            )
        if covered.is_empty():
            attached_covered = covered
        else:
            attached_covered = linkage_store.attach_linkage_columns(
                covered,
                requested,
                context.data_dir,
                expected_generation=expected,
                require_complete=True,
            )
        if not beyond.is_empty():
            beyond = beyond.with_columns([
                pl.lit(None, dtype=pl.Float64).alias(name)
                for name in requested
                if name not in beyond.columns
            ])
        return pl.concat(
            [attached_covered, beyond],
            how="diagonal_relaxed",
        ).sort("_linkage_row").drop("_linkage_row")

    def materialize_matrix(
        self,
        market: Any,
        names: frozenset[str],
        context: FactorProviderContext,
    ) -> Any:
        requested = frozenset(names) & LINKAGE_FACTOR_IDS
        if not requested:
            return market
        if context.data_dir is None:
            raise linkage_store.LinkageCoverageError(
                "联动因子需要稳定的数据目录 (data_dir)"
            )
        expected = context.expected_generation
        if expected is None:
            expected = self.generation(context)
        return linkage_store.attach_matrix_linkage_fields(
            market,
            context.data_dir,
            requested,
            expected_generation=expected,
        )

    def rebuild_sidecar(
        self,
        context: FactorProviderContext,
        *,
        mode: Literal["full", "incremental"],
        target_dates=None,
    ) -> int:
        if context.data_dir is None:
            raise ValueError("linkage sidecar requires data_dir")
        kwargs = {"mode": mode}
        if target_dates is not None:
            kwargs["target_dates"] = target_dates
        return linkage_store.rebuild_linkage_sidecar(context.data_dir, **kwargs)


PROVIDER = CrossSectionalLinkageProvider()
FACTOR_PROVIDERS = (PROVIDER,)
