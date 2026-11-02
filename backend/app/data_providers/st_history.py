"""Route effective-dated historical ST reads through the selected dataset provider."""
from __future__ import annotations

from pathlib import Path

import polars as pl

from app.data_providers import custom as custom_sources
from app.data_providers.registry import get_provider
from app.tickflow.security_status import normalize_st_history


def load_st_history(data_dir: str | Path) -> pl.DataFrame:
    """Read the configured ``st_history`` source without falling back silently."""
    from app.services import preferences

    provider_name = preferences.get_st_history_provider()
    if provider_name == "local_st_history":
        from app.data_providers.local_st_history import LocalStHistoryProvider

        provider = LocalStHistoryProvider(data_dir)
    elif custom_sources.is_custom_provider(provider_name):
        if not custom_sources.provider_has_dataset(provider_name, "st_history"):
            raise ValueError(f"数据源 {provider_name!r} 未声明 st_history 数据集")
        provider = custom_sources.get_provider(provider_name)
    else:
        provider = get_provider(provider_name)
    getter = getattr(provider, "get_st_history", None)
    if not callable(getter):
        raise ValueError(
            f"数据源 {provider_name!r} 不提供历史 ST 状态 (st_history)"
        )
    return normalize_st_history(getter())
