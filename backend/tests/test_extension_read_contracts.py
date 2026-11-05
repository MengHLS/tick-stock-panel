from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import polars as pl
from fastapi import FastAPI

from app.extensions.adapters import repository_read_adapters
from app.extensions.loader import current_extension_context
from app.extensions.runtime import build_extension_runtime, extension_runtime_from_app


class _Repository:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.store = SimpleNamespace(data_dir=Path("."))

    def get_instruments_asset(self, asset_type: str) -> pl.DataFrame:
        self.calls.append(("instruments", asset_type))
        return pl.DataFrame({"symbol": ["000001.SZ"]})

    def get_historical_shares(self) -> pl.DataFrame:
        self.calls.append(("shares",))
        return pl.DataFrame({"symbol": ["000001.SZ"]})

    def get_daily_batch(self, symbols, start, end, columns=None):
        self.calls.append(("daily", symbols, start, end, columns))
        return pl.DataFrame({"symbol": symbols, "date": [start]})

    def get_minute_batch(self, symbols, trade_date, asset_type="stock"):
        self.calls.append(("minute", symbols, trade_date, asset_type))
        return pl.DataFrame({"symbol": symbols})

    def list_minute_dates(self, start, end, asset_type="stock"):
        self.calls.append(("minute_dates", start, end, asset_type))
        return [start]

    def latest_minute_date_global(self):
        self.calls.append(("latest_minute",))
        return date(2026, 11, 2)

    def earliest_minute_date(self):
        self.calls.append(("earliest_minute",))
        return date(2026, 10, 1)

    def list_enriched_dates(self, start, end, asset_type="stock"):
        self.calls.append(("trading_dates", start, end, asset_type))
        return [end]

    def latest_daily_date(self):
        self.calls.append(("latest_daily",))
        return date(2026, 11, 1)

    def get_st_history(self):
        self.calls.append(("st",))
        return pl.DataFrame({"symbol": ["000001.SZ"]})

    def get_enriched_latest(self, *, symbols=None, end=None):
        self.calls.append(("enriched_latest", symbols, end))
        return pl.DataFrame({"symbol": ["000001.SZ"]}), date(2026, 11, 2)

    def get_enriched_range(self, start, end, symbols=None, columns=None):
        self.calls.append(("enriched_range", start, end, symbols, columns))
        return pl.DataFrame({"symbol": symbols or []})

    def latest_enriched_date(self, asset_type="stock"):
        self.calls.append(("enriched_date", asset_type))
        return date(2026, 11, 2)

    def get_matrix_data_generation(self, asset_type="stock"):
        self.calls.append(("generation", asset_type))
        return "generation-1"


def test_repository_adapters_expose_stable_market_and_enriched_reads() -> None:
    repository = _Repository()
    market_data, enriched_panel = repository_read_adapters(repository)
    day = date(2026, 11, 2)

    assert market_data.get_instruments("stock").height == 1
    assert market_data.get_historical_shares().height == 1
    assert market_data.get_daily_batch(
        ["000001.SZ"], day, day, columns=["close"]
    ).height == 1
    assert market_data.get_minute_batch(["000001.SZ"], day).height == 1
    assert market_data.list_minute_dates(day, day) == [day]
    assert market_data.latest_minute_date("stock") == date(2026, 11, 2)
    assert market_data.earliest_minute_date("stock") == date(2026, 10, 1)
    assert market_data.list_trading_dates(day, day) == [day]
    assert market_data.latest_daily_date() == date(2026, 11, 1)
    assert market_data.get_st_history().height == 1

    frame, observed = enriched_panel.latest(
        "stock",
        symbols=["000001.SZ"],
        end=day,
    )
    assert frame.height == 1
    assert observed == day
    assert enriched_panel.latest_date("stock") == day
    assert enriched_panel.range(day, day, ["000001.SZ"], ["close"]).height == 1
    assert enriched_panel.data_generation("stock") == "generation-1"
    assert ("daily", ["000001.SZ"], day, day, ["close"]) in repository.calls


def test_current_extension_context_injects_read_contracts() -> None:
    context = current_extension_context(
        data_dir=Path("."),
        repository=_Repository(),
    )

    assert context.market_data is not None
    assert context.enriched_panel is not None
    assert context.backtest_read is not None


def test_runtime_publishes_alerts_without_exposing_quote_service(monkeypatch) -> None:
    calls: list[tuple] = []
    depth_service = object()
    financial_scheduler = object()

    class Quotes:
        def push_alerts(self, events):
            calls.append(("push", events))

        def _maybe_send_system_notifications(self, events):
            calls.append(("notify", events))

    from app.services import alert_store

    monkeypatch.setattr(
        alert_store,
        "append_many",
        lambda data_dir, events: calls.append(("append", data_dir, events)),
    )
    runtime = build_extension_runtime(
        data_dir=Path("data"),
        repository=_Repository(),
        capabilities={},
        strategy_engine=object(),
        screener=object(),
        quote_service=Quotes(),
        monitor_engine=object(),
        depth_service=depth_service,
        financial_scheduler=financial_scheduler,
    )

    assert runtime.analysis is not None
    assert not hasattr(runtime, "repository")
    assert not hasattr(runtime, "depth_service")
    assert runtime.financial_scheduler is financial_scheduler
    runtime.alerts.publish([{"type": "buy_trigger", "message": "trigger"}])

    assert calls[0][0] == "push"
    assert calls[0][1][0]["strategy_id"] is None
    assert calls[1][0] == "notify"
    assert calls[2][0] == "append"


def test_runtime_fallback_is_built_from_app_state_once() -> None:
    app = FastAPI()
    app.state.repo = _Repository()
    app.state.capabilities = {}
    app.state.strategy_engine = object()
    app.state.screener = object()
    app.state.quote_service = None
    app.state.monitor_engine = object()

    runtime = extension_runtime_from_app(app)

    assert runtime is extension_runtime_from_app(app)
    assert app.state.extension_runtime is runtime
