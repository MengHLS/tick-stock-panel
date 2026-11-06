from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import config as app_config
from app.api import auth as auth_api
from app.main import auth_middleware


@pytest.fixture(autouse=True)
def isolated_auth_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[ModuleType, Path]]:
    monkeypatch.setattr(app_config.settings, "data_dir", tmp_path)
    monkeypatch.setattr(app_config, "_ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(app_config.settings, "auth_password", "")
    from app.services import auth

    auth_path = tmp_path / "user_data" / "auth.json"
    auth._sessions.clear()
    auth._configured_cache = None
    yield auth, auth_path
    auth._sessions.clear()
    auth._configured_cache = None


def _app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(auth_middleware)
    app.include_router(auth_api.router)

    @app.get("/api/probe")
    async def probe() -> dict:
        return {"ok": True}

    return app


def test_corrupt_auth_store_is_not_treated_as_unconfigured(
    isolated_auth_store: tuple[ModuleType, Path],
) -> None:
    auth, auth_path = isolated_auth_store
    auth.set_password("existing-password")
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text("{broken", encoding="utf-8")
    auth._configured_cache = None

    with pytest.raises(auth.AuthStoreError):
        auth.is_configured()

    app_config.settings.auth_password = "env-replacement"
    assert auth.bootstrap_from_env() is False
    assert auth_path.read_text(encoding="utf-8") == "{broken"


def test_invalid_password_fields_fail_closed(
    isolated_auth_store: tuple[ModuleType, Path],
) -> None:
    auth, auth_path = isolated_auth_store
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text(
        json.dumps({"password_hash": 123, "password_salt": "abcd"}),
        encoding="utf-8",
    )
    auth._configured_cache = None

    with pytest.raises(auth.AuthStoreError):
        auth.is_configured()


def test_explicit_null_password_fields_fail_closed(
    isolated_auth_store: tuple[ModuleType, Path],
) -> None:
    auth, auth_path = isolated_auth_store
    auth.set_password("existing-password")
    data = json.loads(auth_path.read_text(encoding="utf-8"))
    data["password_hash"] = None
    data["password_salt"] = None
    auth_path.write_text(json.dumps(data), encoding="utf-8")
    auth._configured_cache = None

    with pytest.raises(auth.AuthStoreError):
        auth.is_configured()

    app_config.settings.auth_password = "env-replacement"
    assert auth.bootstrap_from_env() is False
    assert json.loads(auth_path.read_text(encoding="utf-8"))["password_hash"] is None


def test_single_password_field_fails_closed(
    isolated_auth_store: tuple[ModuleType, Path],
) -> None:
    auth, auth_path = isolated_auth_store
    auth.set_password("existing-password")
    data = json.loads(auth_path.read_text(encoding="utf-8"))
    del data["password_salt"]
    auth_path.write_text(json.dumps(data), encoding="utf-8")
    auth._configured_cache = None

    with pytest.raises(auth.AuthStoreError):
        auth.is_configured()


def test_sessions_only_store_remains_unconfigured(
    isolated_auth_store: tuple[ModuleType, Path],
) -> None:
    auth, auth_path = isolated_auth_store
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text(json.dumps({"sessions": {}}), encoding="utf-8")
    auth._configured_cache = None

    assert auth.is_configured() is False


def test_middleware_and_auth_api_fail_closed_on_corrupt_store(
    isolated_auth_store: tuple[ModuleType, Path],
) -> None:
    auth, auth_path = isolated_auth_store
    with TestClient(_app(), client=("127.0.0.1", 50000)) as client:
        assert client.get("/api/probe").status_code == 200

        auth.set_password("existing-password")
        assert client.get("/api/probe").status_code == 401

        auth_path.write_text("{broken", encoding="utf-8")
        auth._configured_cache = None

        response = client.get("/api/probe")
        assert response.status_code == 503
        assert response.json()["code"] == "AUTH_STORE_UNAVAILABLE"

        assert client.get("/api/auth/status").status_code == 503
        assert client.post(
            "/api/auth/login",
            json={"password": "existing-password"},
        ).status_code == 503
        assert client.post(
            "/api/auth/setup",
            json={"password": "replacement-password"},
        ).status_code == 503
        assert auth_path.read_text(encoding="utf-8") == "{broken"


def test_middleware_and_auth_api_fail_closed_on_null_password_fields(
    isolated_auth_store: tuple[ModuleType, Path],
) -> None:
    auth, auth_path = isolated_auth_store
    auth.set_password("existing-password")
    data = json.loads(auth_path.read_text(encoding="utf-8"))
    data["password_hash"] = None
    data["password_salt"] = None
    auth_path.write_text(json.dumps(data), encoding="utf-8")
    auth._configured_cache = None

    with TestClient(_app(), client=("127.0.0.1", 50000)) as client:
        response = client.get("/api/probe")
        assert response.status_code == 503
        assert response.json()["code"] == "AUTH_STORE_UNAVAILABLE"
        assert client.get("/api/auth/status").status_code == 503
        assert client.post(
            "/api/auth/login",
            json={"password": "existing-password"},
        ).status_code == 503
        assert client.post(
            "/api/auth/setup",
            json={"password": "replacement-password"},
        ).status_code == 503

    assert json.loads(auth_path.read_text(encoding="utf-8"))["password_hash"] is None
