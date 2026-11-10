"""Stable provider contracts for stateful factor computations."""
from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import pkgutil
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

import polars as pl

from app.extensions.contracts import BACKEND_EXTENSION_API_VERSION

logger = logging.getLogger(__name__)

FactorProviderKind = Literal["frame", "sidecar"]


@dataclass(frozen=True)
class FactorProviderContext:
    """Inputs shared by frame and matrix factor materialization."""

    data_dir: Path | None = None
    expected_generation: str | None = None
    asset_type: str = "stock"
    require_complete: bool = True
    allow_tail_nulls: bool = False
    params: Mapping[str, Any] = field(default_factory=dict)


class FactorProvider(ABC):
    """Compute stateful factors outside the formula DSL dispatch."""

    api_version = BACKEND_EXTENSION_API_VERSION
    provider_id: str
    version: int = 1
    kind: FactorProviderKind = "frame"
    factor_ids: frozenset[str]
    factor_specs: tuple[Any, ...] = ()
    transient_errors: tuple[type[Exception], ...] = ()
    coverage_errors: tuple[type[Exception], ...] = ()

    @abstractmethod
    def dependencies(self, factor_id: str) -> frozenset[str]:
        """Return physical columns required for one factor."""
        raise NotImplementedError

    @abstractmethod
    def warmup_bars(self, factor_id: str) -> int:
        """Return the number of prior trading bars required."""
        raise NotImplementedError

    def null_policy(self, factor_id: str) -> Literal["keep", "drop_row"]:
        del factor_id
        return "keep"

    def params(self, factor_id: str) -> Mapping[str, Any]:
        """Return the provider's effective parameters for one factor."""
        del factor_id
        return {}

    def materialize_frame(
        self,
        frame: pl.DataFrame,
        names: frozenset[str],
        context: FactorProviderContext,
    ) -> pl.DataFrame:
        del names, context
        return frame

    def materialize_matrix(
        self,
        market: Any,
        names: frozenset[str],
        context: FactorProviderContext,
    ) -> Any:
        del names, context
        return market

    def materialize_matrix_field(self, market: Any, factor_id: str) -> Any:
        del market, factor_id
        return None

    def generation(self, context: FactorProviderContext) -> str | None:
        del context
        return None

    def rebuild_sidecar(
        self,
        context: FactorProviderContext,
        *,
        mode: Literal["full", "incremental"],
        target_dates: list[date] | None = None,
    ) -> int:
        del context, mode, target_dates
        return 0


_PROVIDERS: dict[str, FactorProvider] = {}
_FACTOR_OWNERS: dict[str, str] = {}
_PROVIDERS_READY = False
_DISCOVERY_IN_PROGRESS = False

#: 发现/装载的可查记录 (B0b-3): 计数、最后错误、包名。health 据此区分
#: 「未安装」(missing_package / packages_scanned == 0) 与「装载失败」(failed_*)。
_DISCOVERY: dict[str, Any] = {
    "attempts": 0,
    "failures": 0,
    "packages_scanned": 0,
    "modules_loaded": 0,
    "providers_registered": 0,
    "failed_modules": [],
    "failed_providers": [],
    "last_error": None,
    "last_failed": None,
    "missing_package": None,
}
_LOGGED_ERRORS: set[str] = set()


def register_factor_provider(provider: FactorProvider) -> None:
    """Register one provider and its FactorSpec metadata atomically."""
    if provider.api_version != BACKEND_EXTENSION_API_VERSION:
        raise ValueError(
            f"factor provider API v{provider.api_version} is unsupported; "
            f"current is v{BACKEND_EXTENSION_API_VERSION}"
        )
    provider_id = str(getattr(provider, "provider_id", "")).strip()
    if not provider_id:
        raise ValueError("factor provider requires provider_id")
    factor_ids = frozenset(str(item) for item in provider.factor_ids)
    if not factor_ids:
        raise ValueError(f"factor provider {provider_id} requires factor ids")
    if provider.kind not in {"frame", "sidecar"}:
        raise ValueError(
            f"factor provider {provider_id} has invalid kind {provider.kind!r}"
        )
    spec_ids = frozenset(str(spec.id) for spec in provider.factor_specs)
    if spec_ids and spec_ids != factor_ids:
        raise ValueError(
            f"factor provider {provider_id} specs do not match factor ids"
        )
    for factor_id in factor_ids:
        null_policy = provider.null_policy(factor_id)
        if null_policy not in {"keep", "drop_row"}:
            raise ValueError(
                f"factor provider {provider_id} has invalid null policy "
                f"{null_policy!r} for {factor_id}"
            )
        if not isinstance(provider.params(factor_id), Mapping):
            raise TypeError(
                f"factor provider {provider_id} params must be a mapping "
                f"for {factor_id}"
            )
    existing = _PROVIDERS.get(provider_id)
    if existing is provider:
        return
    if existing is not None:
        if existing.version >= provider.version:
            raise ValueError(
                f"factor provider {provider_id} version must increase"
            )
        if existing.factor_ids != factor_ids:
            raise ValueError(
                f"factor provider {provider_id} must keep a stable factor id set "
                "across versions"
            )
    for factor_id in factor_ids:
        owner = _FACTOR_OWNERS.get(factor_id)
        if owner is not None and owner != provider_id:
            raise ValueError(
                f"factor {factor_id} already owned by provider {owner}"
            )

    from app.factors.registry import peek_factor, register_factor

    for spec in provider.factor_specs:
        # 上一次注册在本 provider 中途抛错时, 已注册的 spec 会留在注册表里; 直接用
        # register_factor 会因「版本未提升」永远注册不上 (清旗也修不回来的那半条路径)。
        # 同内容就跳过, 内容变了才真注册 —— 让重试可收敛。
        if peek_factor(spec.id) == spec:
            continue
        register_factor(spec)
    _PROVIDERS[provider_id] = provider
    _FACTOR_OWNERS.update({factor_id: provider_id for factor_id in factor_ids})


def unregister_factor_provider(provider_id: str) -> None:
    """Remove a dynamically registered provider and its factor metadata."""
    provider = _PROVIDERS.pop(str(provider_id), None)
    if provider is None:
        return
    from app.factors.registry import unregister_factor

    for factor_id in provider.factor_ids:
        _FACTOR_OWNERS.pop(factor_id, None)
        unregister_factor(factor_id)


def _note_failure(kind: str, name: str, exc: BaseException) -> None:
    """记录一次装载失败 (计数 + 最后错误 + 包名), 同一条错误只告警一次。"""
    message = f"{type(exc).__name__}: {exc}"
    _DISCOVERY["last_error"] = message
    _DISCOVERY["last_failed"] = name
    bucket = _DISCOVERY["failed_modules" if kind == "module" else "failed_providers"]
    bucket.append({"name": name, "error": message})
    key = f"{kind}:{name}:{message}"
    if key not in _LOGGED_ERRORS:
        _LOGGED_ERRORS.add(key)
        logger.warning("factor provider %s load failed %s: %s", kind, name, exc)


def _discovery_guard(fn):
    def wrapper() -> None:
        global _DISCOVERY_IN_PROGRESS
        if _PROVIDERS_READY or _DISCOVERY_IN_PROGRESS:
            return
        _DISCOVERY_IN_PROGRESS = True
        try:
            fn()
        finally:
            _DISCOVERY_IN_PROGRESS = False

    return wrapper


@_discovery_guard
def ensure_factor_providers() -> None:
    """Discover optional ``factor_provider`` modules under app.custom.

    B0b-3 契约 (旧实现的静默吞异常已修):

    * ``_PROVIDERS_READY`` 只在**发现循环全部成功**后置位; 任一步失败即保持/复位为
      False, 下一次调用重新尝试 (旧实现先置 True 再发现: 一次瞬时 import 失败 =
      进程内永久缺失, 且不可重试)。
    * 失败不打断其它 provider (一个坏包不影响其余), 但全部失败都留可查记录:
      计数 (``attempts`` / ``failures``)、最后错误 (``last_error``)、包名
      (``failed_modules`` / ``failed_providers``) —— 见 ``factor_provider_status()``。
    * 「未安装」与「装载失败」可区分: 前者 ``missing_package`` 非空或
      ``packages_scanned == 0``, 后者 ``failed_*`` 非空。
    """
    global _PROVIDERS_READY
    if _PROVIDERS_READY:
        return

    _DISCOVERY["attempts"] += 1
    _DISCOVERY["packages_scanned"] = 0
    _DISCOVERY["modules_loaded"] = 0
    _DISCOVERY["failed_modules"] = []
    _DISCOVERY["failed_providers"] = []
    _DISCOVERY["last_error"] = None
    _DISCOVERY["last_failed"] = None

    try:
        package = importlib.import_module("app.custom")
    except ModuleNotFoundError as exc:
        # 未安装: app.custom 包不存在。旗标保持 False, 下次调用重试 (装回来即可生效)。
        _DISCOVERY["missing_package"] = str(exc)
        _DISCOVERY["failures"] += 1
        _DISCOVERY["last_error"] = f"{type(exc).__name__}: {exc}"
        _DISCOVERY["last_failed"] = "app.custom"
        return
    _DISCOVERY["missing_package"] = None

    discovered: list[FactorProvider] = []
    for item in pkgutil.iter_modules(package.__path__, f"{package.__name__}."):
        if not item.ispkg:
            continue
        _DISCOVERY["packages_scanned"] += 1
        module_name = f"{item.name}.factor_provider"
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                continue
            module = importlib.import_module(module_name)
            providers = getattr(module, "FACTOR_PROVIDERS", ())
            if not isinstance(providers, (tuple, list)):
                raise TypeError("FACTOR_PROVIDERS must be a tuple or list")
            _DISCOVERY["modules_loaded"] += 1
            for provider in providers:
                discovered.append(provider)
        except Exception as exc:  # noqa: BLE001 - isolate one optional provider
            _note_failure("module", module_name, exc)

    for provider in sorted(
        discovered,
        key=lambda item: (item.kind != "frame", item.provider_id),
    ):
        try:
            register_factor_provider(provider)
        except Exception as exc:  # noqa: BLE001 - isolate one optional provider
            _note_failure("provider", str(getattr(provider, "provider_id", "?")), exc)

    if _DISCOVERY["failed_modules"] or _DISCOVERY["failed_providers"]:
        _DISCOVERY["failures"] += 1
        _PROVIDERS_READY = False
        return
    _DISCOVERY["providers_registered"] = len(_PROVIDERS)
    _PROVIDERS_READY = True


def factor_provider_status() -> dict[str, Any]:
    """因子 Provider 发现/装载的可查状态 (health 用; 只读, 不触发发现)。

    ``state`` 四态: ``pending`` (从未尝试) / ``not_installed`` (无 app.custom 或
    一个 provider 包都没有) / ``load_failed`` (有失败记录) / ``loaded``。
    """
    failed_modules = list(_DISCOVERY["failed_modules"])
    failed_providers = list(_DISCOVERY["failed_providers"])
    if _DISCOVERY["attempts"] == 0:
        state = "pending"
    elif _DISCOVERY["missing_package"] or (
        _DISCOVERY["packages_scanned"] == 0 and not _PROVIDERS_READY
    ):
        state = "not_installed"
    elif failed_modules or failed_providers or not _PROVIDERS_READY:
        state = "load_failed"
    else:
        state = "loaded"
    return {
        "state": state,
        "ready": _PROVIDERS_READY,
        "attempts": _DISCOVERY["attempts"],
        "failures": _DISCOVERY["failures"],
        "packages_scanned": _DISCOVERY["packages_scanned"],
        "modules_loaded": _DISCOVERY["modules_loaded"],
        "providers": sorted(_PROVIDERS),
        "factor_count": len(_FACTOR_OWNERS),
        "failed_modules": failed_modules,
        "failed_providers": failed_providers,
        "last_error": _DISCOVERY["last_error"],
        "last_failed": _DISCOVERY["last_failed"],
        "missing_package": _DISCOVERY["missing_package"],
    }


def factor_provider_for(factor_id: str) -> FactorProvider | None:
    ensure_factor_providers()
    owner = _FACTOR_OWNERS.get(str(factor_id))
    return _PROVIDERS.get(owner) if owner is not None else None


def provider_factor_ids(names: Any) -> frozenset[str]:
    ensure_factor_providers()
    return frozenset(str(name) for name in names if str(name) in _FACTOR_OWNERS)


def sidecar_factor_ids() -> frozenset[str]:
    ensure_factor_providers()
    return frozenset(
        factor_id
        for factor_id, provider_id in _FACTOR_OWNERS.items()
        if _PROVIDERS[provider_id].kind == "sidecar"
    )


def factor_provider_dependencies(names: Any) -> dict[str, frozenset[str]]:
    result: dict[str, frozenset[str]] = {}
    for name in provider_factor_ids(names):
        provider = factor_provider_for(name)
        if provider is not None:
            result[name] = provider.dependencies(name)
    return result


def factor_provider_warmup(names: Any) -> int:
    return max(
        (
            provider.warmup_bars(name)
            for name in provider_factor_ids(names)
            if (provider := factor_provider_for(name)) is not None
        ),
        default=1,
    )


def factor_provider_contract_signature(
    names: Any,
    *,
    asset_type: str = "stock",
) -> dict[str, Any]:
    """Return the effective provider/version/params contract for cache keys."""
    result: dict[str, Any] = {}
    for name in sorted(provider_factor_ids(names)):
        provider = factor_provider_for(name)
        if provider is None:
            continue
        result[name] = {
            "provider_id": provider.provider_id,
            "version": int(provider.version),
            "kind": provider.kind,
            "asset_type": asset_type,
            "params": json.loads(
                json.dumps(
                    dict(provider.params(name)),
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
            ),
        }
    return result


def materialize_factor_columns(
    frame: pl.DataFrame,
    names: Any,
    *,
    context: FactorProviderContext,
) -> pl.DataFrame:
    grouped: dict[str, set[str]] = {}
    for name in provider_factor_ids(names):
        provider = factor_provider_for(name)
        if name in frame.columns and provider is not None and provider.kind != "sidecar":
            continue
        if provider is not None:
            grouped.setdefault(provider.provider_id, set()).add(name)
    for provider_id, requested in grouped.items():
        provider = _PROVIDERS[provider_id]
        frame = provider.materialize_frame(
            frame,
            frozenset(requested),
            context,
        )
        drop_columns = [
            name
            for name in sorted(requested)
            if provider.null_policy(name) == "drop_row"
            and name in frame.columns
        ]
        if drop_columns:
            frame = frame.filter(
                pl.all_horizontal(
                    [pl.col(name).is_not_null() for name in drop_columns]
                )
            )
    return frame


def materialize_factor_matrix(
    market: Any,
    names: Any,
    *,
    context: FactorProviderContext,
) -> Any:
    grouped: dict[str, set[str]] = {}
    for name in provider_factor_ids(names):
        provider = factor_provider_for(name)
        if provider is not None:
            grouped.setdefault(provider.provider_id, set()).add(name)
    for provider_id, requested in grouped.items():
        provider = _PROVIDERS[provider_id]
        if any(provider.null_policy(name) == "drop_row" for name in requested):
            raise ValueError(
                f"factor provider {provider_id} requests drop_row null policy, "
                "which cannot be represented in matrix materialization"
            )
        market = provider.materialize_matrix(
            market,
            frozenset(requested),
            context,
        )
    return market


def materialize_matrix_factor_field(
    market: Any,
    factor_id: str,
) -> Any:
    provider = factor_provider_for(factor_id)
    return (
        provider.materialize_matrix_field(market, factor_id)
        if provider is not None else None
    )


def factor_provider_generation(
    names: Any,
    *,
    data_dir: Path | None,
    asset_type: str = "stock",
) -> str | None:
    providers = {
        provider.provider_id: provider
        for name in provider_factor_ids(names)
        if (provider := factor_provider_for(name)) is not None
        and provider.kind == "sidecar"
    }
    if len(providers) > 1:
        raise ValueError("one factor request cannot span multiple sidecar providers")
    if not providers:
        return None
    provider = next(iter(providers.values()))
    return provider.generation(
        FactorProviderContext(data_dir=data_dir, asset_type=asset_type)
    )


def is_transient_factor_provider_error(exc: Exception) -> bool:
    ensure_factor_providers()
    return any(
        isinstance(exc, provider.transient_errors)
        for provider in _PROVIDERS.values()
        if provider.transient_errors
    )


def is_coverage_factor_provider_error(exc: Exception) -> bool:
    ensure_factor_providers()
    return any(
        isinstance(exc, provider.coverage_errors)
        for provider in _PROVIDERS.values()
        if provider.coverage_errors
    )


def rebuild_factor_sidecars(
    *,
    data_dir: Path,
    mode: Literal["full", "incremental"],
    target_dates: list[date] | None = None,
) -> int:
    ensure_factor_providers()
    written = 0
    for provider in _PROVIDERS.values():
        if provider.kind != "sidecar":
            continue
        written += provider.rebuild_sidecar(
            FactorProviderContext(data_dir=data_dir),
            mode=mode,
            target_dates=target_dates,
        )
    return written
