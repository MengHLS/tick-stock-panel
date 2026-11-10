"""Provider 发现/装载的失败可见性与可重试性 (B0b-3)。

B2 结项的书面附条件: `app/extensions/factors.py#ensure_factor_providers` 旧实现
「先置 `_PROVIDERS_READY=True` 再去发现」+ 两处 `except Exception` 只 `logger.warning`,
一次瞬时失败就让该 provider 在进程内永久缺失且不可重试; 另一条 `if existing is provider:
return` 与「中途注册了一部分 spec」叠加后, 清旗也修不回来。

本文件把三条都做成可复跑的用例: ①失败不置位、下次调用重试; ②已注册的残留 spec 不阻挡
重新发现; ③`factor_provider_status()` 能区分「未安装」与「装载失败」。
"""
from __future__ import annotations

import importlib

import pytest

from app.extensions import factors as ext
from app.factors import registry

REAL_PROVIDER_COUNT = 6
PACK_MODULE = "app.custom.research_factor_pack.factor_provider"
PACK_PROVIDER_ID = "official.research-factor-pack-b0"


@pytest.fixture()
def fresh():
    """把注册表与发现状态恢复到「只装内置目录因子、从未发现」的干净点。"""
    saved_registry = dict(registry._REGISTRY)
    saved_state = (
        dict(ext._PROVIDERS),
        dict(ext._FACTOR_OWNERS),
        ext._PROVIDERS_READY,
        {k: (list(v) if isinstance(v, list) else v) for k, v in ext._DISCOVERY.items()},
        set(ext._LOGGED_ERRORS),
    )
    catalog_ids = {spec.id for spec in registry._CATALOG}
    for fid in [key for key in registry._REGISTRY if key not in catalog_ids]:
        registry._REGISTRY.pop(fid, None)
    ext._PROVIDERS.clear()
    ext._FACTOR_OWNERS.clear()
    ext._PROVIDERS_READY = False
    for key, value in ext._DISCOVERY.items():
        ext._DISCOVERY[key] = [] if isinstance(value, list) else (0 if isinstance(value, int) else None)
    ext._LOGGED_ERRORS.clear()
    yield ext
    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved_registry)
    providers, owners, ready, discovery, logged = saved_state
    ext._PROVIDERS.clear()
    ext._PROVIDERS.update(providers)
    ext._FACTOR_OWNERS.clear()
    ext._FACTOR_OWNERS.update(owners)
    ext._PROVIDERS_READY = ready
    ext._DISCOVERY.clear()
    ext._DISCOVERY.update(discovery)
    ext._LOGGED_ERRORS.clear()
    ext._LOGGED_ERRORS.update(logged)


def test_status_is_pending_before_the_first_attempt(fresh) -> None:
    status = fresh.factor_provider_status()
    assert status["state"] == "pending"
    assert status["attempts"] == 0
    assert status["ready"] is False


def test_successful_discovery_marks_ready_and_reports_loaded(fresh) -> None:
    fresh.ensure_factor_providers()
    status = fresh.factor_provider_status()
    assert status["state"] == "loaded"
    assert status["ready"] is True
    assert status["providers"] == sorted(fresh._PROVIDERS)
    assert len(status["providers"]) == REAL_PROVIDER_COUNT
    assert status["failed_modules"] == [] and status["failed_providers"] == []
    assert status["packages_scanned"] > 0


def test_transient_module_failure_keeps_the_flag_clear_and_retries(fresh, monkeypatch) -> None:
    """旧实现在这里永久缺失: 旗标先置 True, 之后再也不会重试。"""
    state = {"attempts": 0}
    real_import = importlib.import_module

    def flaky(name, *args, **kwargs):
        if name == PACK_MODULE:
            state["attempts"] += 1
            if state["attempts"] == 1:
                raise RuntimeError("transient import failure")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(ext.importlib, "import_module", flaky)

    fresh.ensure_factor_providers()
    assert fresh._PROVIDERS_READY is False
    status = fresh.factor_provider_status()
    assert status["state"] == "load_failed"
    assert status["last_failed"] == PACK_MODULE
    assert [item["name"] for item in status["failed_modules"]] == [PACK_MODULE]
    assert "transient import failure" in status["last_error"]
    assert status["failures"] >= 1
    assert PACK_PROVIDER_ID not in fresh._PROVIDERS

    # 第二次调用必须真的重试 (而不是因为旗标已置位直接返回)。
    fresh.ensure_factor_providers()
    assert fresh._PROVIDERS_READY is True
    assert PACK_PROVIDER_ID in fresh._PROVIDERS
    assert fresh.factor_provider_status()["state"] == "loaded"


def test_provider_registration_failure_is_isolated_and_recorded(fresh, monkeypatch) -> None:
    real = fresh.register_factor_provider
    state = {"attempts": 0}

    def flaky(provider):
        if provider.provider_id == PACK_PROVIDER_ID:
            state["attempts"] += 1
            if state["attempts"] == 1:
                raise RuntimeError("registration blew up")
        return real(provider)

    monkeypatch.setattr(fresh, "register_factor_provider", flaky)

    fresh.ensure_factor_providers()
    status = fresh.factor_provider_status()
    assert fresh._PROVIDERS_READY is False
    assert status["state"] == "load_failed"
    assert [item["name"] for item in status["failed_providers"]] == [PACK_PROVIDER_ID]
    # 失败只隔离在这一个 provider 上: 其余照常注册。
    assert PACK_PROVIDER_ID not in fresh._PROVIDERS
    assert len(fresh._PROVIDERS) == REAL_PROVIDER_COUNT - 1


def test_already_registered_specs_do_not_block_rediscovery(fresh) -> None:
    """中途注册失败留下的残留 spec: 重试不得因「版本未提升」永远失败。"""
    from app.custom.research_factor_pack.factor_specs import RESEARCH_BASELINE_FACTOR_SPECS

    leftover = RESEARCH_BASELINE_FACTOR_SPECS[0]
    registry.register_factor(leftover)  # 模拟上一次在 provider 内中途抛错后的残留
    assert registry.peek_factor(leftover.id) is leftover

    fresh.ensure_factor_providers()
    assert fresh._PROVIDERS_READY is True
    assert PACK_PROVIDER_ID in fresh._PROVIDERS
    for spec in RESEARCH_BASELINE_FACTOR_SPECS:
        assert registry.peek_factor(spec.id) is not None


def test_state_distinguishes_not_installed_from_load_failed(fresh, monkeypatch) -> None:
    real_import = importlib.import_module  # 先抓住真身: 下面 patch 的是同一个模块属性

    def missing(name, *args, **kwargs):
        if name == "app.custom":
            raise ModuleNotFoundError("No module named 'app.custom'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(ext.importlib, "import_module", missing)
    fresh.ensure_factor_providers()
    not_installed = fresh.factor_provider_status()
    assert not_installed["state"] == "not_installed"
    assert not_installed["ready"] is False
    assert "app.custom" in str(not_installed["missing_package"])

    monkeypatch.undo()

    def boom(name, *args, **kwargs):
        if name == PACK_MODULE:
            raise ValueError("broken package")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(ext.importlib, "import_module", boom)
    fresh.ensure_factor_providers()
    load_failed = fresh.factor_provider_status()
    assert load_failed["state"] == "load_failed"
    assert load_failed["state"] != not_installed["state"]


def test_health_endpoint_carries_the_provider_state() -> None:
    from app.api.routes import health

    payload = health()
    assert payload["status"] == "ok"
    providers = payload["factor_providers"]
    assert set(providers) >= {
        "state",
        "ready",
        "attempts",
        "failures",
        "providers",
        "failed_modules",
        "failed_providers",
        "last_error",
    }
    assert providers["state"] in {"pending", "not_installed", "load_failed", "loaded"}
