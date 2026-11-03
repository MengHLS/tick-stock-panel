from __future__ import annotations

import types
from datetime import datetime

import polars as pl
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.extensions.contracts import (
    BACKEND_EXTENSION_API_VERSION,
    NotificationFormatContext,
    NotificationFormatter,
    QuoteUpdateContext,
    QuoteUpdateObserver,
)
from app.extensions.loader import configure_backend_extensions
from app.extensions.registry import BackendExtensionRegistrar, BackendExtensionRegistry
from app.services.quote_service import QuoteService


class PrefixFormatter(NotificationFormatter):
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def format_message(self, event: dict, context: NotificationFormatContext) -> str:
        assert context.api_version == BACKEND_EXTENSION_API_VERSION
        return f"{self.prefix}{event['message']}"


class BrokenFormatter(NotificationFormatter):
    def format_message(self, event: dict, context: NotificationFormatContext) -> str:
        del event, context
        raise RuntimeError("broken formatter")


class RecordingObserver(QuoteUpdateObserver):
    def __init__(self, symbols: set[str], events: list[dict] | None = None) -> None:
        self._symbols = frozenset(symbols)
        self.events = events or []
        self.contexts: list[QuoteUpdateContext] = []

    def watched_symbols(self) -> frozenset[str]:
        return self._symbols

    def on_quote_update(self, context: QuoteUpdateContext) -> list[dict]:
        self.contexts.append(context)
        return list(self.events)


class BrokenObserver(QuoteUpdateObserver):
    def watched_symbols(self) -> frozenset[str]:
        return frozenset({"000001.SZ"})

    def on_quote_update(self, context: QuoteUpdateContext) -> list[dict]:
        del context
        raise RuntimeError("broken observer")


def _registrar(extension_id: str = "company.test") -> BackendExtensionRegistrar:
    return BackendExtensionRegistrar(
        extension_id,
        api_version=BACKEND_EXTENSION_API_VERSION,
    )


def test_empty_registry_preserves_existing_notification_objects() -> None:
    registry = BackendExtensionRegistry()
    registry.freeze()
    service = QuoteService()
    service._app_state = types.SimpleNamespace(extension_registry=registry)
    events = [{"message": "原始消息", "source": "strategy"}]

    result = service._format_extension_notifications(events)

    assert result is events
    assert result[0] is events[0]


def test_notification_formatters_are_ordered_and_do_not_mutate_input() -> None:
    registry = BackendExtensionRegistry()
    registrar = _registrar()
    registrar.register_notification_formatter("company.second", PrefixFormatter("B"), order=20)
    registrar.register_notification_formatter("company.first", PrefixFormatter("A"), order=10)
    registry.register(registrar)
    registry.freeze()
    service = QuoteService()
    service._app_state = types.SimpleNamespace(extension_registry=registry)
    events = [{"message": "原始消息", "source": "strategy"}]

    result = service._format_extension_notifications(events)

    assert result == [{"message": "BA原始消息", "source": "strategy"}]
    assert events == [{"message": "原始消息", "source": "strategy"}]
    assert result is not events
    assert result[0] is not events[0]


def test_broken_formatter_keeps_previous_message_and_later_formatters_run() -> None:
    registry = BackendExtensionRegistry()
    registrar = _registrar()
    registrar.register_notification_formatter("company.first", PrefixFormatter("A"), order=10)
    registrar.register_notification_formatter("company.broken", BrokenFormatter(), order=20)
    registrar.register_notification_formatter("company.last", PrefixFormatter("B"), order=30)
    registry.register(registrar)
    registry.freeze()
    service = QuoteService()
    service._app_state = types.SimpleNamespace(extension_registry=registry)

    result = service._format_extension_notifications([{"message": "原始消息"}])

    assert result[0]["message"] == "BA原始消息"


def test_registry_rejects_version_mismatch_without_partial_registration() -> None:
    registry = BackendExtensionRegistry()
    registrar = BackendExtensionRegistrar("company.future", api_version=999)
    registrar.register_notification_formatter("company.future", PrefixFormatter("x"))

    with pytest.raises(ValueError, match="requires backend API"):
        registry.register(registrar)

    registry.freeze()
    assert not registry.has_customizations
    assert not registry.has_notification_formatters


def test_registry_is_frozen_after_startup() -> None:
    registry = BackendExtensionRegistry()
    registry.freeze()

    with pytest.raises(RuntimeError, match="frozen"):
        registry.register(_registrar())


def test_quote_observers_are_ordered_and_only_receive_watched_symbols() -> None:
    registry = BackendExtensionRegistry()
    registrar = _registrar()
    first = RecordingObserver({"000001.SZ"})
    second = RecordingObserver({"600000.SH"})
    registrar.register_quote_observer("company.second", second, order=20)
    registrar.register_quote_observer("company.first", first, order=10)
    registry.register(registrar)
    registry.freeze()
    service = QuoteService()
    service._app_state = types.SimpleNamespace(extension_registry=registry)
    frame = pl.DataFrame(
        {
            "symbol": ["000001.SZ", "600000.SH", "000002.SZ"],
            "name": ["A", "B", "C"],
            "close": [10.0, 20.0, 30.0],
            "raw_close": [10.0, 20.0, 30.0],
            "change_pct": [0.01, 0.02, 0.03],
        }
    )

    events = service._evaluate_extension_observers(
        frame,
        observed_at=datetime.fromisoformat("2026-11-02T09:31:00+08:00"),
    )

    assert events == []
    assert [registration.implementation_id for registration in registry.quote_observers()] == [
        "company.first",
        "company.second",
    ]
    assert [row["symbol"] for row in first.contexts[0].quotes] == ["000001.SZ"]
    assert [row["symbol"] for row in second.contexts[0].quotes] == ["600000.SH"]


def test_quote_observer_failure_is_isolated_and_does_not_drop_other_events() -> None:
    registry = BackendExtensionRegistry()
    registrar = _registrar()
    registrar.register_quote_observer("company.broken", BrokenObserver(), order=10)
    registrar.register_quote_observer(
        "company.valid",
        RecordingObserver(
            {"000001.SZ"},
            events=[
                {
                    "source": "first_board_right_tail",
                    "type": "buy_trigger",
                    "symbol": "000001.SZ",
                    "name": "A",
                    "message": "测试触发",
                    "price": 10.0,
                    "change_pct": 0.01,
                    "signals": [],
                    "severity": "warn",
                    "conditions": [],
                    "logic": "and",
                }
            ],
        ),
        order=20,
    )
    registry.register(registrar)
    registry.freeze()
    service = QuoteService()
    service._app_state = types.SimpleNamespace(extension_registry=registry)
    frame = pl.DataFrame(
        {
            "symbol": ["000001.SZ"],
            "name": ["A"],
            "close": [10.0],
            "raw_close": [10.0],
            "change_pct": [0.01],
        }
    )

    events = service._evaluate_extension_observers(
        frame,
        observed_at=datetime.fromisoformat("2026-11-02T09:31:00+08:00"),
    )

    assert len(events) == 1
    assert events[0]["message"] == "测试触发"


def test_quote_observer_version_mismatch_rejects_whole_extension() -> None:
    registry = BackendExtensionRegistry()
    registrar = _registrar()
    observer = RecordingObserver(set())
    observer.api_version = 999
    registrar.register_quote_observer("company.future", observer)

    with pytest.raises(ValueError, match="requires API"):
        registry.register(registrar)

    registry.freeze()
    assert not registry.has_customizations
    assert registry.quote_observers() == ()


def test_loader_isolates_failed_setup_and_registers_valid_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = types.ModuleType("app.custom.broken")
    broken.EXTENSION_ID = "company.broken"
    broken.EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION

    def broken_setup(registrar: BackendExtensionRegistrar) -> None:
        registrar.register_notification_formatter("company.partial", PrefixFormatter("x"))
        raise RuntimeError("setup failed")

    broken.setup = broken_setup

    valid = types.ModuleType("app.custom.valid")
    valid.EXTENSION_ID = "company.valid"
    valid.EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION

    def valid_setup(registrar: BackendExtensionRegistrar) -> None:
        router = APIRouter(prefix="/api/custom/valid")

        @router.get("/status")
        def status() -> dict:
            return {"status": "ok"}

        registrar.include_router(router)

    valid.setup = valid_setup
    modules = {broken.__name__: broken, valid.__name__: valid}

    monkeypatch.setattr(
        "app.extensions.loader._custom_module_names",
        lambda: [broken.__name__, valid.__name__],
    )
    monkeypatch.setattr(
        "app.extensions.loader.importlib.import_module",
        lambda name: modules[name],
    )
    app = FastAPI()

    registry, errors = configure_backend_extensions(app)

    assert registry.frozen
    assert registry.extension_ids() == frozenset({"company.valid"})
    assert len(errors) == 1
    assert errors[0].module == broken.__name__
    client = TestClient(app)
    response = client.get("/api/custom/valid/status")
    assert response.status_code == 200
