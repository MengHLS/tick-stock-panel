"""启动失败时已获取资源必须被清理, 且单个清理失败不阻断其余步骤。"""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import ClassVar

import pytest

import app.main as main_module


class _Harness:
    def __init__(self, monkeypatch, tmp_path):
        self.stops: dict[str, int] = {}
        self.phase: dict[str, str | None] = {"value": None}
        self.data_sync_pipeline_enabled = False
        phase = self.phase

        def record(name: str) -> None:
            self.stops[name] = self.stops.get(name, 0) + 1

        self.record = record

        class Repo:
            def __init__(self, store):
                self.store = store
                self.enriched_ready = False
                self._on_warmup_done = None
                self._on_refresh_done = None

            def refresh_cache(self, background=False):
                del background

            def refresh_extension_columns(self, *args, **kwargs):
                del args, kwargs

            def latest_enriched_date(self, asset_type="stock"):
                del asset_type
                return None

        class Manager:
            def __init__(self, data_dir, kind=None, store=None):
                del data_dir, store
                self.kind = kind or "mining"

            def recover_interrupted(self):
                return 0

            def shutdown(self):
                record(f"{self.kind}_manager")

        class Quote:
            def set_repo(self, repo):
                del repo

            def set_app_state(self, state):
                del state

            def boot_check(self):
                pass

            def stop(self):
                record("quote_service")

        class StrategyMonitor:
            def __init__(self):
                if phase["value"] == "quote":
                    raise RuntimeError("strategy monitor init failed")

        class Depth:
            def set_repo(self, repo):
                del repo

            def set_app_state(self, state):
                del state

            def boot_check(self, allow_network=False):
                del allow_network

            def start_polling(self):
                pass

            def stop_polling(self):
                record("depth_service")

        class Scheduler:
            def shutdown(self, wait=False):
                del wait
                record("scheduler")

        class MinuteRefresh:
            def __init__(self, repo):
                del repo

            def set_app_state(self, state):
                del state

            def start(self):
                return True

            def stop(self):
                record("minute_refresh")

        class WecomBot:
            def set_app_state(self, state):
                del state

            def boot_check(self):
                pass

            def stop(self):
                record("wecom_bot")

        class Watchdog:
            async def stop(self):
                record("watchdog")

        class Screener:
            def __init__(self, repo, asset_type="stock"):
                del repo, asset_type

            def _load_enriched_history(self, *args, **kwargs):
                del args, kwargs
                return None

        class StrategyEngine:
            def __init__(self, strategy_dirs=None, override_loader=None):
                del strategy_dirs, override_loader
                if phase["value"] == "strategy":
                    raise RuntimeError("strategy assembly failed")

            def list_strategies(self):
                return []

            def load_errors(self):
                return []

            def reload(self):
                pass

        class MonitorRuleEngine:
            rule_count = 0

            def set_strategy_engine(self, engine):
                del engine

            def set_data_dir(self, data_dir):
                del data_dir

            def set_sector_monitor_service(self, service):
                del service

            def set_history_loader(self, loader):
                del loader

            def set_history_loader_etf(self, loader):
                del loader

            def set_rules(self, rules):
                del rules

        class SectorMonitor:
            def __init__(self, repo):
                del repo

        class ExtensionRuntime:
            def shutdown_quote_observers(self):
                record("quote_observers")

        def pull_start(*args, **kwargs):
            del args, kwargs
            if phase["value"] == "pull":
                raise RuntimeError("pull scheduler start failed")

        monkeypatch.setattr(main_module, "DataStore", lambda: SimpleNamespace(data_dir=tmp_path))
        monkeypatch.setattr(main_module, "KlineRepository", Repo)
        monkeypatch.setattr("app.services.mining_manager.MiningJobManager", Manager)
        monkeypatch.setattr(main_module.settings, "backtest_matrix_disk_cache_enabled", False)
        monkeypatch.setattr(main_module.settings, "backtest_matrix_cache_prewarm", False)
        monkeypatch.setattr(main_module, "shutdown_delivery_executors", lambda: record("delivery_executors"))
        monkeypatch.setattr(main_module, "detect_capabilities", lambda: SimpleNamespace(all=lambda: []))
        monkeypatch.setattr("app.services.auth.bootstrap_from_env", lambda: None)
        monkeypatch.setattr("app.strategy.custom_signals.seed_if_empty", lambda _: 0)
        monkeypatch.setattr("app.factors.store.load_into_registry", lambda _: 0)
        monkeypatch.setattr(
            "app.services.preferences.get_data_sync_prefs",
            lambda: {
                "data_sync_pipeline_enabled": self.data_sync_pipeline_enabled,
                "data_sync_ext_pull_enabled": False,
            },
        )
        monkeypatch.setattr("app.data_providers.custom.load_all", lambda: None)
        monkeypatch.setattr("app.data_providers.custom.list_sources", lambda: [])
        monkeypatch.setattr("app.data_providers.capabilities.resolve_capability_sources", lambda: [])
        monkeypatch.setattr("app.extensions.packages.start_managed_extensions", lambda *a, **k: None)
        monkeypatch.setattr("app.services.upgrade_guard.UpgradeGuard", _UpgradeGuard)
        monkeypatch.setattr(main_module, "QuoteService", Quote)
        monkeypatch.setattr("app.strategy.monitor.StrategyMonitorService", StrategyMonitor)
        monkeypatch.setattr("app.services.depth_service.DepthService", Depth)
        monkeypatch.setattr("app.jobs.daily_pipeline.set_app_state", lambda _: None)
        monkeypatch.setattr(
            "app.jobs.daily_pipeline.start_scheduler",
            lambda *a, **k: Scheduler(),
        )
        monkeypatch.setattr("app.services.minute_refresh.MinuteRefreshService", MinuteRefresh)
        monkeypatch.setattr("app.services.wecom_bot_service.WecomBotService", WecomBot)
        monkeypatch.setattr(
            "app.services.ext_presets.ensure_builtin_presets",
            _noop_presets,
        )
        monkeypatch.setattr("app.services.ext_pull.pull_scheduler.start", pull_start)
        monkeypatch.setattr(
            "app.services.ext_pull.pull_scheduler.refresh",
            lambda *a, **k: None,
        )
        monkeypatch.setattr(
            "app.services.ext_pull.pull_scheduler.stop",
            lambda: record("pull_scheduler"),
        )
        monkeypatch.setattr(
            "app.services.financial_sync.financial_scheduler.start",
            lambda *a, **k: None,
        )
        monkeypatch.setattr(
            "app.services.financial_sync.financial_scheduler.stop",
            lambda: record("financial_scheduler"),
        )
        monkeypatch.setattr("app.watchdog.start_watchdog", lambda *a, **k: Watchdog())
        monkeypatch.setattr("app.services.screener.ScreenerService", Screener)
        monkeypatch.setattr("app.strategy.monitor.MonitorRuleEngine", MonitorRuleEngine)
        monkeypatch.setattr("app.services.sector_monitor.SectorMonitorService", SectorMonitor)
        monkeypatch.setattr(
            "app.strategy.monitor_rules.migrate_strategy_monitors",
            lambda *a, **k: None,
        )
        monkeypatch.setattr("app.strategy.monitor_rules.load_all", lambda _: [])
        monkeypatch.setattr(
            "app.strategy.paper_watch.sync",
            lambda *a, **k: {"watching": []},
        )
        monkeypatch.setattr(
            main_module,
            "build_extension_runtime",
            lambda **kwargs: ExtensionRuntime(),
        )
        monkeypatch.setattr(main_module, "start_backend_extensions", lambda *a, **k: None)
        monkeypatch.setattr("app.strategy.strategy_seeds.seed_missing_builtins", lambda _: 0)
        monkeypatch.setattr("app.strategy.config.load_override", lambda *a, **k: None)
        monkeypatch.setattr("app.strategy.engine.StrategyEngine", StrategyEngine)
        monkeypatch.setattr(
            "app.services.data_integrity.boot_integrity_check",
            lambda *a, **k: record("integrity_check"),
        )


class _UpgradeGuard:
    def __init__(self, data_dir):
        del data_dir

    def start_background_scan(self):
        pass


async def _noop_presets(_data_dir) -> None:
    return None


class _FakeTimer:
    instances: ClassVar[list[_FakeTimer]]

    def __init__(self, interval, function, args=None, kwargs=None):
        self.interval = interval
        self.function = function
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.daemon = False
        self.started = False
        self.cancelled = False
        _FakeTimer.instances.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.function(*self.args, **self.kwargs)


def _install_fake_timers(monkeypatch):
    _FakeTimer.instances = []
    monkeypatch.setattr(threading, "Timer", _FakeTimer)
    return _FakeTimer.instances


@pytest.mark.parametrize(
    "phase,expected",
    [
        (
            "quote",
            {"mining_manager", "guardian_manager", "quote_service", "delivery_executors"},
        ),
        (
            "pull",
            {
                "mining_manager",
                "guardian_manager",
                "quote_service",
                "depth_service",
                "scheduler",
                "minute_refresh",
                "wecom_bot",
                "delivery_executors",
            },
        ),
        (
            "strategy",
            {
                "mining_manager",
                "guardian_manager",
                "quote_service",
                "depth_service",
                "scheduler",
                "minute_refresh",
                "wecom_bot",
                "pull_scheduler",
                "financial_scheduler",
                "watchdog",
                "delivery_executors",
            },
        ),
    ],
)
def test_startup_failure_stops_only_acquired_resources(monkeypatch, tmp_path, phase, expected):
    harness = _Harness(monkeypatch, tmp_path)
    harness.phase["value"] = phase
    app = SimpleNamespace(state=SimpleNamespace(mining_lock_acquired=True))

    async def exercise():
        async with main_module._application_lifespan(app):
            pytest.fail("startup should fail before serving requests")

    with pytest.raises(RuntimeError):
        asyncio.run(exercise())

    assert set(harness.stops) == expected, harness.stops
    assert all(count == 1 for count in harness.stops.values())


def test_cleanup_continues_after_one_action_fails():
    calls: list[str] = []
    scope = main_module._CleanupScope()
    scope.add("watchdog", lambda: calls.append("watchdog"))
    scope.add("mining_manager", lambda: calls.append("mining"))
    scope.add(
        "quote_service",
        lambda: (_ for _ in ()).throw(RuntimeError("quote stop failed")),
    )
    scope.add("delivery_executors", lambda: calls.append("delivery"))
    scope.add("not_registered", lambda: calls.append("unexpected"))

    asyncio.run(scope.close())
    asyncio.run(scope.close())

    assert calls == ["watchdog", "mining", "delivery"]


def test_startup_failure_cancels_integrity_timer(monkeypatch, tmp_path):
    harness = _Harness(monkeypatch, tmp_path)
    harness.data_sync_pipeline_enabled = True
    harness.phase["value"] = "strategy"
    timers = _install_fake_timers(monkeypatch)
    app = SimpleNamespace(state=SimpleNamespace(mining_lock_acquired=True))

    async def exercise():
        async with main_module._application_lifespan(app):
            pytest.fail("startup should fail before serving requests")

    with pytest.raises(RuntimeError):
        asyncio.run(exercise())

    assert len(timers) == 1
    assert timers[0].started and timers[0].cancelled
    timers[0].fire()
    assert "integrity_check" not in harness.stops


def test_normal_exit_cancels_integrity_timer(monkeypatch, tmp_path):
    harness = _Harness(monkeypatch, tmp_path)
    harness.data_sync_pipeline_enabled = True
    timers = _install_fake_timers(monkeypatch)
    app = SimpleNamespace(
        state=SimpleNamespace(
            mining_lock_acquired=True,
            extension_registry=SimpleNamespace(shutdown_quote_observers=lambda: None),
        )
    )

    async def exercise():
        async with main_module._application_lifespan(app):
            assert len(timers) == 1
            assert timers[0].started and not timers[0].cancelled

    asyncio.run(exercise())

    assert timers[0].cancelled
    timers[0].fire()
    assert "integrity_check" not in harness.stops


def test_disabled_data_sync_does_not_start_integrity_timer(monkeypatch, tmp_path):
    harness = _Harness(monkeypatch, tmp_path)
    harness.phase["value"] = "strategy"
    timers = _install_fake_timers(monkeypatch)
    app = SimpleNamespace(state=SimpleNamespace(mining_lock_acquired=True))

    async def exercise():
        async with main_module._application_lifespan(app):
            pytest.fail("startup should fail before serving requests")

    with pytest.raises(RuntimeError):
        asyncio.run(exercise())

    assert timers == []
    assert "integrity_check" not in harness.stops
