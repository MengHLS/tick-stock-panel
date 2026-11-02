"""Stable, small-grained contracts for in-repository secondary development."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

BACKEND_EXTENSION_API_VERSION = 1


class RepositoryAccess(Protocol):
    """Read-oriented repository surface exposed to backend extensions."""

    def get_name_map(self, symbols: list[str] | None = None) -> dict[str, str]: ...


@dataclass(frozen=True)
class ExtensionContext:
    api_version: int
    data_dir: Path
    repository: RepositoryAccess


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
