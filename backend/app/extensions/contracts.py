"""Stable, small-grained contracts for in-repository secondary development."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

import polars as pl

BACKEND_EXTENSION_API_VERSION = 1


class RepositoryAccess(Protocol):
    """Read-oriented repository surface exposed to backend extensions."""

    def get_name_map(self, symbols: list[str] | None = None) -> dict[str, str]: ...


class MarketDataRead(Protocol):
    """Stable daily/minute metadata and price reads for extensions."""

    def get_instruments(self, asset_type: str = "stock") -> pl.DataFrame: ...

    def get_historical_shares(self) -> pl.DataFrame: ...

    def get_daily_batch(
        self,
        symbols: list[str],
        start: date,
        end: date,
        columns: list[str] | None = None,
    ) -> pl.DataFrame: ...

    def get_minute_batch(
        self,
        symbols: list[str],
        trade_date: date,
        asset_type: str = "stock",
    ) -> pl.DataFrame: ...

    def list_minute_dates(
        self,
        start: date,
        end: date,
        asset_type: str = "stock",
    ) -> list[date]: ...

    def list_trading_dates(
        self,
        start: date,
        end: date,
        asset_type: str = "stock",
    ) -> list[date]: ...

    def latest_daily_date(self) -> date | None: ...

    def get_st_history(self) -> pl.DataFrame: ...


class EnrichedPanelRead(Protocol):
    """Stable generation-aware enriched panel reads for extensions."""

    def latest(
        self,
        asset_type: str = "stock",
        *,
        symbols: list[str] | None = None,
        end: date | None = None,
        refresh: bool = True,
    ) -> tuple[pl.DataFrame, date | None]: ...

    def latest_date(self, asset_type: str = "stock") -> date | None: ...

    def range(
        self,
        start: date,
        end: date,
        symbols: list[str] | None = None,
        columns: list[str] | None = None,
    ) -> pl.DataFrame | None: ...

    def data_generation(self, asset_type: str = "stock") -> str | None: ...


class BacktestRead(Protocol):
    """Read-only backtest panel access without exposing the engine class."""

    def data_generation(self, asset_type: str = "stock") -> str | None: ...

    def data_generation_await(
        self,
        asset_type: str = "stock",
        *,
        timeout_s: float = 300.0,
    ) -> str | None: ...

    def load_panel(
        self,
        symbols: list[str] | None,
        start: date,
        end: date,
        columns: list[str] | None = None,
        asset_type: str = "stock",
        *,
        expected_generation: str | None = None,
    ) -> pl.DataFrame: ...


class BacktestResultRead(Protocol):
    """Read completed runs and immutable saved result snapshots."""

    def list_saved(self, page: int = 1, page_size: int = 20) -> dict: ...

    def get_saved(self, saved_id: str) -> dict: ...

    def get_completed(self, run_id: str) -> dict | None: ...


@dataclass(frozen=True)
class ExtensionContext:
    api_version: int
    data_dir: Path
    repository: RepositoryAccess
    market_data: MarketDataRead | None = None
    enriched_panel: EnrichedPanelRead | None = None
    backtest_read: BacktestRead | None = None
    backtest_results: BacktestResultRead | None = None


@dataclass(frozen=True)
class NotificationFormatContext:
    api_version: int


class NotificationFormatter(ABC):
    """Customize notification copy without changing the event schema or semantics."""

    api_version = BACKEND_EXTENSION_API_VERSION

    @abstractmethod
    def format_message(
        self,
        event: dict[str, Any],
        context: NotificationFormatContext,
    ) -> str:
        """Return notification copy. The input event must not be mutated."""
        raise NotImplementedError


class DefaultNotificationFormatter(NotificationFormatter):
    def format_message(
        self,
        event: dict[str, Any],
        context: NotificationFormatContext,
    ) -> str:
        del context
        return str(event.get("message") or "")


@dataclass(frozen=True)
class QuoteUpdateContext:
    """A small, point-in-time quote snapshot for an extension observer."""

    api_version: int
    observed_at: datetime
    quotes: tuple[Mapping[str, Any], ...]


class QuoteUpdateObserver(ABC):
    """Observe realtime quote rounds without owning the quote service lifecycle."""

    api_version = BACKEND_EXTENSION_API_VERSION

    def watched_symbols(self) -> frozenset[str]:
        """Return the symbols this observer needs. Empty disables the callback."""
        return frozenset()

    @abstractmethod
    def on_quote_update(self, context: QuoteUpdateContext) -> list[dict[str, Any]]:
        """Return zero or more standard alert-event dictionaries."""
        raise NotImplementedError

    def shutdown(self) -> None:
        """Release optional resources. Called during application shutdown."""
        return None
