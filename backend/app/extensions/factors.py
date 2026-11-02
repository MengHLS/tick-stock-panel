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

    from app.factors.registry import register_factor

    for spec in provider.factor_specs:
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


def ensure_factor_providers() -> None:
    """Discover optional ``factor_provider`` modules under app.custom."""
    global _PROVIDERS_READY
    if _PROVIDERS_READY:
        return
    _PROVIDERS_READY = True
    try:
        package = importlib.import_module("app.custom")
    except ModuleNotFoundError:
        return
    discovered: list[FactorProvider] = []
    for item in pkgutil.iter_modules(package.__path__, f"{package.__name__}."):
        if not item.ispkg:
            continue
        module_name = f"{item.name}.factor_provider"
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                continue
            module = importlib.import_module(module_name)
            providers = getattr(module, "FACTOR_PROVIDERS", ())
            if not isinstance(providers, (tuple, list)):
                raise TypeError("FACTOR_PROVIDERS must be a tuple or list")
            for provider in providers:
                discovered.append(provider)
        except Exception as exc:  # noqa: BLE001 - isolate one optional provider
            logger.warning("factor provider load failed %s: %s", module_name, exc)
    for provider in sorted(
        discovered,
        key=lambda item: (item.kind != "frame", item.provider_id),
    ):
        try:
            register_factor_provider(provider)
        except Exception as exc:  # noqa: BLE001 - isolate one optional provider
            logger.warning(
                "factor provider registration failed %s: %s",
                provider.provider_id,
                exc,
            )


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
