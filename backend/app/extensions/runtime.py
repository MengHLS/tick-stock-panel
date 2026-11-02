"""Controlled runtime capabilities for request-time backend extensions."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from fastapi import HTTPException, Request

from app.backtest.result_read import BacktestResultReadAdapter
from app.extensions.adapters import repository_read_adapters
from app.extensions.contracts import (
    BACKEND_EXTENSION_API_VERSION,
    BacktestResultRead,
    EnrichedPanelRead,
    MarketDataRead,
)

logger = logging.getLogger(__name__)


class AlertPublisher(Protocol):
    def publish(self, events: list[dict[str, Any]]) -> None: ...


class MonitorRuleSynchronizer(Protocol):
    def save_and_sync(self, rules: list[dict[str, Any]]) -> list[dict[str, Any]]: ...

    def sync_paper_watch(self) -> dict[str, Any]: ...


class StrategyRuntimeRead(Protocol):
    def get(self, strategy_id: str) -> Any: ...

    def run(self, *args: Any, **kwargs: Any) -> Any: ...


class ScreenerRuntimeRead(Protocol):
    def latest_date(self) -> date | None: ...

    def build_strategy_context(self, *args: Any, **kwargs: Any) -> Any: ...


class QuoteRuntimeRead(Protocol):
    def status(self) -> dict[str, Any]: ...

    def get_enriched_today(self) -> tuple[Any, date | None]: ...


@dataclass(frozen=True)
class ExtensionRuntime:
    api_version: int
    data_dir: Path
    repository: Any
    market_data: MarketDataRead
    enriched_panel: EnrichedPanelRead
    backtest_results: BacktestResultRead
    capabilities: Any
    strategy_engine: StrategyRuntimeRead | None
    screener: ScreenerRuntimeRead | None
    quote_service: QuoteRuntimeRead | None
    depth_service: Any
    financial_scheduler: Any
    alerts: AlertPublisher
    monitor_rules: MonitorRuleSynchronizer


class CoreAlertPublisher:
    def __init__(self, data_dir: Path, quote_service: Any) -> None:
        self._data_dir = Path(data_dir)
        self._quote_service = quote_service

    def publish(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        normalized = [
            {**dict(event), "strategy_id": event.get("strategy_id")}
            for event in events
        ]
        if self._quote_service is not None:
            self._quote_service.push_alerts(normalized)
            self._quote_service._maybe_send_system_notifications(normalized)
        try:
            from app.services import alert_store

            alert_store.append_many(self._data_dir, normalized)
        except Exception as exc:  # noqa: BLE001 - alert persistence is best effort
            logger.warning("扩展告警落盘失败: %s", exc)


class CoreMonitorRuleSynchronizer:
    def __init__(
        self,
        data_dir: Path,
        monitor_engine: Any,
        strategy_engine: Any,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._monitor_engine = monitor_engine
        self._strategy_engine = strategy_engine

    def save_and_sync(self, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from app.strategy import monitor_rules

        for rule in rules:
            existing = monitor_rules.load_one(self._data_dir, rule["id"])
            if existing and existing.get("created_at"):
                rule["created_at"] = existing["created_at"]
            monitor_rules.save_one(self._data_dir, rule)
        if self._monitor_engine is not None:
            self._monitor_engine.set_rules(
                monitor_rules.load_all(self._data_dir)
            )
        self.sync_paper_watch()
        return rules

    def sync_paper_watch(self) -> dict[str, Any]:
        if self._monitor_engine is None or self._strategy_engine is None:
            return {"watching": []}
        from app.strategy import paper_watch

        return paper_watch.sync(
            self._data_dir,
            self._monitor_engine,
            self._strategy_engine,
        )


def build_extension_runtime(
    *,
    data_dir: Path,
    repository: Any,
    capabilities: Any,
    strategy_engine: Any,
    screener: Any,
    quote_service: Any,
    monitor_engine: Any,
    depth_service: Any = None,
    financial_scheduler: Any = None,
) -> ExtensionRuntime:
    market_data, enriched_panel = repository_read_adapters(repository)
    return ExtensionRuntime(
        api_version=BACKEND_EXTENSION_API_VERSION,
        data_dir=Path(data_dir),
        repository=repository,
        market_data=market_data,
        enriched_panel=enriched_panel,
        backtest_results=BacktestResultReadAdapter(data_dir),
        capabilities=capabilities,
        strategy_engine=strategy_engine,
        screener=screener,
        quote_service=quote_service,
        depth_service=depth_service,
        financial_scheduler=financial_scheduler,
        alerts=CoreAlertPublisher(data_dir, quote_service),
        monitor_rules=CoreMonitorRuleSynchronizer(
            data_dir,
            monitor_engine,
            strategy_engine,
        ),
    )


def extension_runtime_from_app(app: Any) -> ExtensionRuntime:
    runtime = getattr(app.state, "extension_runtime", None)
    if runtime is not None:
        return runtime
    repository = getattr(app.state, "repo", None)
    if repository is None:
        raise RuntimeError("extension runtime requires the core repository")
    screener = getattr(app.state, "screener", None)
    if screener is None:
        from app.services.screener import ScreenerService

        screener = ScreenerService(repository)
    runtime = build_extension_runtime(
        data_dir=repository.store.data_dir,
        repository=repository,
        capabilities=getattr(app.state, "capabilities", None),
        strategy_engine=getattr(app.state, "strategy_engine", None),
        screener=screener,
        quote_service=getattr(app.state, "quote_service", None),
        monitor_engine=getattr(app.state, "monitor_engine", None),
        depth_service=getattr(app.state, "depth_service", None),
        financial_scheduler=getattr(app.state, "financial_scheduler", None),
    )
    app.state.extension_runtime = runtime
    return runtime


def get_extension_runtime(request: Request) -> ExtensionRuntime:
    try:
        return extension_runtime_from_app(request.app)
    except RuntimeError as exc:
        raise HTTPException(503, "扩展运行时尚未就绪") from exc
