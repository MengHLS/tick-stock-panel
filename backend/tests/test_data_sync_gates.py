"""手动数据同步入口的开关门控。

自动调度按启动快照注册；手动入口按当前偏好立即 fail-closed。
"""
from __future__ import annotations

import pytest

from app.services import preferences
from app.services.data_sync_gate import DataSyncDisabledError, ensure_enabled
from app.services.financial_sync import FinancialScheduler


def _set_all(enabled: bool) -> dict[str, bool]:
    return {
        "data_sync_pipeline_enabled": enabled,
        "data_sync_ext_pull_enabled": enabled,
        "data_sync_financial_enabled": enabled,
    }


@pytest.mark.parametrize("kind", ["pipeline", "ext_pull", "financial"])
def test_gate_raises_when_disabled(monkeypatch, kind):
    monkeypatch.setattr(preferences, "get_data_sync_prefs", lambda: _set_all(False))
    with pytest.raises(DataSyncDisabledError):
        ensure_enabled(kind)


@pytest.mark.parametrize("kind", ["pipeline", "ext_pull", "financial"])
def test_gate_allows_when_enabled(monkeypatch, kind):
    monkeypatch.setattr(preferences, "get_data_sync_prefs", lambda: _set_all(True))
    ensure_enabled(kind)


async def test_pull_run_is_blocked_before_touching_request(monkeypatch):
    from app.api.ext_data import run_pull

    monkeypatch.setattr(preferences, "get_data_sync_prefs", lambda: _set_all(False))
    with pytest.raises(DataSyncDisabledError):
        await run_pull(None, "ext_demo")


async def test_backfill_is_blocked_before_touching_request(monkeypatch):
    from app.api.ext_data import backfill_history_ep

    monkeypatch.setattr(preferences, "get_data_sync_prefs", lambda: _set_all(False))
    with pytest.raises(DataSyncDisabledError):
        await backfill_history_ep(None, "ext_demo", start="2026-01-01", end="2026-01-02")


async def test_pipeline_trigger_is_blocked(monkeypatch):
    from app.api.pipeline import trigger_pipeline_job

    monkeypatch.setattr(preferences, "get_data_sync_prefs", lambda: _set_all(False))
    with pytest.raises(DataSyncDisabledError):
        await trigger_pipeline_job(None, None)


def test_financial_trigger_is_blocked(monkeypatch):
    monkeypatch.setattr(preferences, "get_data_sync_prefs", lambda: _set_all(False))
    scheduler = FinancialScheduler()
    with pytest.raises(DataSyncDisabledError):
        scheduler.trigger()
