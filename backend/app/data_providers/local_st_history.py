"""Built-in provider for the normalized local historical ST dataset."""
from __future__ import annotations

from pathlib import Path

import polars as pl

from app.config import settings
from app.data_providers.base import ProviderCapabilities
from app.tickflow.security_status import normalize_st_history, read_st_history


class LocalStHistoryProvider:
    name = "local_st_history"
    capabilities = ProviderCapabilities(st_history=True)

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self._data_dir = Path(data_dir) if data_dir is not None else settings.data_dir

    def get_st_history(
        self,
        symbols: list[str] | None = None,
    ) -> pl.DataFrame:
        history = read_st_history(self._data_dir)
        if symbols is not None:
            history = history.filter(pl.col("symbol").is_in(symbols))
        return normalize_st_history(history)
