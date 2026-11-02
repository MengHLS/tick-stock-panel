"""Adapters from core repositories to stable extension read contracts."""
from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl

from app.extensions.contracts import EnrichedPanelRead, MarketDataRead


class RepositoryMarketData:
    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def get_instruments(self, asset_type: str = "stock") -> pl.DataFrame:
        return self._repository.get_instruments_asset(asset_type)

    def get_historical_shares(self) -> pl.DataFrame:
        return self._repository.get_historical_shares()

    def get_daily_batch(
        self,
        symbols: list[str],
        start: date,
        end: date,
        columns: list[str] | None = None,
    ) -> pl.DataFrame:
        return self._repository.get_daily_batch(symbols, start, end, columns=columns)

    def get_minute_batch(
        self,
        symbols: list[str],
        trade_date: date,
        asset_type: str = "stock",
    ) -> pl.DataFrame:
        return self._repository.get_minute_batch(
            symbols,
            trade_date,
            asset_type=asset_type,
        )

    def list_minute_dates(
        self,
        start: date,
        end: date,
        asset_type: str = "stock",
    ) -> list[date]:
        return self._repository.list_minute_dates(
            start,
            end,
            asset_type=asset_type,
        )

    def list_trading_dates(
        self,
        start: date,
        end: date,
        asset_type: str = "stock",
    ) -> list[date]:
        return self._repository.list_enriched_dates(
            start,
            end,
            asset_type=asset_type,
        )

    def latest_daily_date(self) -> date | None:
        return self._repository.latest_daily_date()

    def get_st_history(self) -> pl.DataFrame:
        return self._repository.get_st_history()


class RepositoryEnrichedPanel:
    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def latest(
        self,
        asset_type: str = "stock",
        *,
        symbols: list[str] | None = None,
        end: date | None = None,
        refresh: bool = True,
    ) -> tuple[pl.DataFrame, date | None]:
        if asset_type == "stock":
            frame, observed = self._repository.get_enriched_latest(
                symbols=symbols,
                end=end,
            )
        else:
            frame, observed = self._repository.get_enriched_latest_asset(
                asset_type,
                refresh=refresh,
            )
            if symbols is not None and "symbol" in frame.columns:
                frame = frame.filter(pl.col("symbol").is_in(symbols))
            if end is not None and "date" in frame.columns:
                frame = frame.filter(pl.col("date") <= end)
        return frame, observed

    def latest_date(self, asset_type: str = "stock") -> date | None:
        loader = getattr(self._repository, "latest_enriched_date", None)
        return loader(asset_type) if callable(loader) else None

    def range(
        self,
        start: date,
        end: date,
        symbols: list[str] | None = None,
        columns: list[str] | None = None,
    ) -> pl.DataFrame | None:
        return self._repository.get_enriched_range(
            start,
            end,
            symbols=symbols,
            columns=columns,
        )

    def data_generation(self, asset_type: str = "stock") -> str | None:
        return self._repository.get_matrix_data_generation(asset_type)


def repository_read_adapters(
    repository: Any,
) -> tuple[MarketDataRead, EnrichedPanelRead]:
    return RepositoryMarketData(repository), RepositoryEnrichedPanel(repository)
