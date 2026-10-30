"""数据同步与调度开关的偏好契约。

锁住: 默认 true、缺失/非法值回退 true、独立保存不覆盖其它键、
GET/PUT 端点可见且可回显。
"""
from __future__ import annotations

import json

import pytest

from app.services import preferences


@pytest.fixture()
def prefs_file(tmp_path, monkeypatch):
    target = tmp_path / "user_data" / "preferences.json"
    target.parent.mkdir(parents=True)
    monkeypatch.setattr(preferences, "_path", lambda: target)
    preferences._invalidate_cache()
    yield target
    preferences._invalidate_cache()


def test_defaults_are_enabled(prefs_file):
    assert preferences.get_data_sync_prefs() == {
        "data_sync_pipeline_enabled": True,
        "data_sync_ext_pull_enabled": True,
        "data_sync_financial_enabled": True,
    }


def test_explicit_false_roundtrip(prefs_file):
    saved = preferences.set_data_sync_prefs({
        "data_sync_pipeline_enabled": False,
        "data_sync_ext_pull_enabled": True,
        "data_sync_financial_enabled": False,
    })
    assert saved["data_sync_pipeline_enabled"] is False
    assert saved["data_sync_ext_pull_enabled"] is True
    assert saved["data_sync_financial_enabled"] is False


@pytest.mark.parametrize("invalid", ["false", 0, None, [], {}])
def test_invalid_values_fall_back_to_enabled(prefs_file, invalid):
    prefs_file.write_text(
        '{"data_sync_pipeline_enabled": ' + json.dumps(invalid) + "}",
        encoding="utf-8",
    )
    preferences._invalidate_cache()
    assert preferences.get_data_sync_prefs()["data_sync_pipeline_enabled"] is True


def test_save_preserves_other_preferences(prefs_file):
    preferences.save({"screener_auto_run": False})
    preferences.set_data_sync_prefs({"data_sync_ext_pull_enabled": False})
    data = preferences.load()
    assert data["screener_auto_run"] is False
    assert data["data_sync_ext_pull_enabled"] is False


def test_rejects_unknown_key_and_non_bool(prefs_file):
    with pytest.raises(ValueError):
        preferences.set_data_sync_prefs({"unknown": True})
    with pytest.raises(ValueError):
        preferences.set_data_sync_prefs({"data_sync_pipeline_enabled": "false"})


def test_get_preferences_exposes_switches(prefs_file):
    from app.api.settings import get_preferences

    preferences.set_data_sync_prefs({"data_sync_pipeline_enabled": False})
    payload = get_preferences()
    assert payload["data_sync_pipeline_enabled"] is False
    assert payload["data_sync_ext_pull_enabled"] is True
    assert payload["data_sync_financial_enabled"] is True


def test_put_endpoint_persists_and_requires_restart(prefs_file):
    from app.api.settings import DataSyncPrefsIn, update_data_sync_prefs

    result = update_data_sync_prefs(DataSyncPrefsIn(
        pipeline_enabled=False,
        ext_pull_enabled=True,
        financial_enabled=False,
    ))
    assert result["data_sync_pipeline_enabled"] is False
    assert result["data_sync_financial_enabled"] is False
    assert result["restart_required"] is True
    assert preferences.get_data_sync_prefs()["data_sync_pipeline_enabled"] is False
