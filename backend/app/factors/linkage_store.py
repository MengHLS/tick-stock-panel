"""Compatibility exports for the cross-sectional linkage sidecar provider."""
from app.custom.cross_sectional_linkage.store import (
    LinkageCoverageError,
    LinkageReadUnstableError,
    attach_linkage_columns,
    attach_matrix_linkage_fields,
    finalized_trading_dates,
    get_enriched_generation,
    linkage_finalized_through,
    rebuild_linkage_sidecar,
    stable_linkage_read,
)

__all__ = [
    "LinkageCoverageError",
    "LinkageReadUnstableError",
    "attach_linkage_columns",
    "attach_matrix_linkage_fields",
    "finalized_trading_dates",
    "get_enriched_generation",
    "linkage_finalized_through",
    "rebuild_linkage_sidecar",
    "stable_linkage_read",
]
