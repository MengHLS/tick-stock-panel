"""Compatibility exports for the cross-sectional linkage provider."""
from app.custom.cross_sectional_linkage.compute import (
    DEVIATION_FACTOR_IDS,
    INDUSTRY_LINKAGE_FACTOR_IDS,
    LINKAGE_FACTOR_IDS,
    compute_linkage_fields,
    normalize_industry,
)

__all__ = [
    "DEVIATION_FACTOR_IDS",
    "INDUSTRY_LINKAGE_FACTOR_IDS",
    "LINKAGE_FACTOR_IDS",
    "compute_linkage_fields",
    "normalize_industry",
]
