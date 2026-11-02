"""Small, versioned strategy extension contracts.

The interfaces only cover replaceable business decisions. Core trading
invariants (T+1, price limits, suspensions, board lots, cash and position
constraints) remain in the backtest engine.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping

import polars as pl

from app.extensions.contracts import BACKEND_EXTENSION_API_VERSION

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class StrategyPolicyContext:
    api_version: int = BACKEND_EXTENSION_API_VERSION
    asset_type: str = "stock"
    as_of: date | None = None
    strategy_id: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MonitorConditionContext:
    api_version: int = BACKEND_EXTENSION_API_VERSION
    asset_type: str = "stock"


class CandidateFilter(ABC):
    api_version = BACKEND_EXTENSION_API_VERSION

    @abstractmethod
    def filter_candidates(
        self,
        frame: pl.DataFrame,
        context: StrategyPolicyContext,
    ) -> pl.DataFrame:
        raise NotImplementedError


class ScoringPolicy(ABC):
    api_version = BACKEND_EXTENSION_API_VERSION

    @abstractmethod
    def score(
        self,
        frame: pl.DataFrame,
        context: StrategyPolicyContext,
    ) -> pl.Series:
        """Return one finite score per row; the caller renames it to ``score``."""
        raise NotImplementedError


class RiskPolicy(ABC):
    api_version = BACKEND_EXTENSION_API_VERSION

    @abstractmethod
    def filter_entries(
        self,
        frame: pl.DataFrame,
        context: StrategyPolicyContext,
    ) -> pl.DataFrame:
        raise NotImplementedError


class BacktestCostModel(ABC):
    api_version = BACKEND_EXTENSION_API_VERSION

    @abstractmethod
    def buy_cost_pct(self, config: Any) -> float:
        raise NotImplementedError

    @abstractmethod
    def sell_cost_pct(self, config: Any) -> float:
        raise NotImplementedError


class StrategyProvider(ABC):
    api_version = BACKEND_EXTENSION_API_VERSION

    @abstractmethod
    def strategy_definitions(self) -> tuple[Any, ...]:
        """Return StrategyDef-compatible objects; core validates duplicates."""
        raise NotImplementedError


class MonitorConditionEvaluator(ABC):
    api_version = BACKEND_EXTENSION_API_VERSION

    @abstractmethod
    def evaluate(
        self,
        frame: pl.DataFrame,
        condition: Mapping[str, Any],
        context: MonitorConditionContext,
    ) -> pl.Series:
        """Return one boolean value per frame row."""
        raise NotImplementedError


class IdentityCandidateFilter(CandidateFilter):
    def filter_candidates(
        self,
        frame: pl.DataFrame,
        context: StrategyPolicyContext,
    ) -> pl.DataFrame:
        del context
        return frame


class IdentityRiskPolicy(RiskPolicy):
    def filter_entries(
        self,
        frame: pl.DataFrame,
        context: StrategyPolicyContext,
    ) -> pl.DataFrame:
        del context
        return frame


class CoreBacktestCostModel(BacktestCostModel):
    """Explicit opt-in wrapper around the core MatcherConfig cost calculation."""

    def buy_cost_pct(self, config: Any) -> float:
        return config._core_buy_cost_pct()

    def sell_cost_pct(self, config: Any) -> float:
        return config._core_sell_cost_pct()


_KINDS: dict[str, dict[str, Any]] = {
    "candidate_filter": {},
    "scoring_policy": {},
    "risk_policy": {},
    "backtest_cost_model": {},
    "strategy_provider": {},
    "monitor_condition_evaluator": {},
}
_BASE_TYPES: dict[str, type] = {
    "candidate_filter": CandidateFilter,
    "scoring_policy": ScoringPolicy,
    "risk_policy": RiskPolicy,
    "backtest_cost_model": BacktestCostModel,
    "strategy_provider": StrategyProvider,
    "monitor_condition_evaluator": MonitorConditionEvaluator,
}
_PROVIDERS_READY = False


def validate_strategy_extension(
    kind: str,
    implementation_id: str,
    implementation: Any,
) -> str:
    if kind not in _KINDS:
        raise ValueError(f"unknown strategy extension kind: {kind}")
    impl_id = str(implementation_id).strip()
    if not impl_id:
        raise ValueError(f"{kind} requires a non-empty implementation id")
    expected = _BASE_TYPES[kind]
    if not isinstance(implementation, expected):
        raise TypeError(f"{kind} implementation must inherit {expected.__name__}")
    if implementation.api_version != BACKEND_EXTENSION_API_VERSION:
        raise ValueError(
            f"{kind} {impl_id!r} requires API v{implementation.api_version}; "
            f"current is v{BACKEND_EXTENSION_API_VERSION}"
        )
    existing = _KINDS[kind].get(impl_id)
    if existing is not None and existing is not implementation:
        raise ValueError(f"duplicate {kind} id: {impl_id}")
    return impl_id


def register_strategy_extension(kind: str, implementation_id: str, implementation: Any) -> None:
    impl_id = validate_strategy_extension(kind, implementation_id, implementation)
    _KINDS[kind][impl_id] = implementation


def strategy_extension(kind: str, implementation_id: str) -> Any | None:
    if kind not in _KINDS:
        raise ValueError(f"unknown strategy extension kind: {kind}")
    return _KINDS[kind].get(str(implementation_id))


def strategy_extensions(kind: str) -> tuple[Any, ...]:
    if kind not in _KINDS:
        raise ValueError(f"unknown strategy extension kind: {kind}")
    return tuple(_KINDS[kind].values())


def build_strategy_policy_context(
    *,
    asset_type: str,
    strategy_id: str | None,
    params: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    as_of: date | None = None,
) -> StrategyPolicyContext:
    return StrategyPolicyContext(
        asset_type=asset_type,
        as_of=as_of,
        strategy_id=strategy_id,
        params=dict(params or {}),
        metadata=dict(metadata or {}),
    )


def _resolve_policy(kind: str, implementation_id: str) -> Any:
    implementation = strategy_extension(kind, str(implementation_id))
    if implementation is None:
        raise ValueError(f"未注册的{kind}: {implementation_id}")
    return implementation


def _validate_filtered_frame(
    kind: str,
    implementation_id: str,
    source: pl.DataFrame,
    result: Any,
) -> pl.DataFrame:
    if not isinstance(result, pl.DataFrame):
        raise TypeError(f"{kind} {implementation_id} 必须返回 polars DataFrame")
    missing = set(source.columns) - set(result.columns)
    if missing:
        raise ValueError(
            f"{kind} {implementation_id} 必须保留输入列: {sorted(missing)}"
        )
    if result.height > source.height:
        raise ValueError(
            f"{kind} {implementation_id} 不能增加候选行: "
            f"{source.height} -> {result.height}"
        )
    return result


def apply_candidate_filter(
    frame: pl.DataFrame,
    implementation_id: str,
    context: StrategyPolicyContext,
) -> pl.DataFrame:
    implementation = _resolve_policy("candidate_filter", implementation_id)
    result = implementation.filter_candidates(frame, context)
    return _validate_filtered_frame(
        "candidate_filter",
        implementation_id,
        frame,
        result,
    )


def apply_risk_policy(
    frame: pl.DataFrame,
    implementation_id: str,
    context: StrategyPolicyContext,
) -> pl.DataFrame:
    implementation = _resolve_policy("risk_policy", implementation_id)
    result = implementation.filter_entries(frame, context)
    return _validate_filtered_frame(
        "risk_policy",
        implementation_id,
        frame,
        result,
    )


def apply_scoring_policy(
    frame: pl.DataFrame,
    implementation_id: str,
    context: StrategyPolicyContext,
) -> pl.Series:
    implementation = _resolve_policy("scoring_policy", implementation_id)
    result = implementation.score(frame, context)
    if not isinstance(result, pl.Series) or len(result) != frame.height:
        raise ValueError(
            f"scoring_policy {implementation_id} 必须返回与候选行数等长的 Series"
        )
    values = result.cast(pl.Float64, strict=False)
    if values.null_count() or not bool(values.is_finite().all()):
        raise ValueError(
            f"scoring_policy {implementation_id} 必须返回有限非空分值"
        )
    return values


def strategy_providers() -> tuple[StrategyProvider, ...]:
    global _PROVIDERS_READY
    if not _PROVIDERS_READY:
        _PROVIDERS_READY = True
        try:
            package = importlib.import_module("app.custom")
        except ModuleNotFoundError:
            package = None
        if package is not None:
            for item in pkgutil.iter_modules(
                package.__path__,
                f"{package.__name__}.",
            ):
                if not item.ispkg:
                    continue
                module_name = f"{item.name}.strategy_provider"
                try:
                    spec = importlib.util.find_spec(module_name)
                    if spec is None:
                        continue
                    module = importlib.import_module(module_name)
                    providers = getattr(module, "STRATEGY_PROVIDERS", ())
                    if not isinstance(providers, (tuple, list)):
                        raise TypeError("STRATEGY_PROVIDERS must be a tuple or list")
                    for provider in providers:
                        register_strategy_extension(
                            "strategy_provider",
                            str(module.__name__),
                            provider,
                        )
                except Exception as exc:  # noqa: BLE001 - isolate optional provider
                    logger.warning(
                        "strategy provider load failed %s: %s",
                        module_name,
                        exc,
                    )
    return tuple(
        item
        for item in _KINDS["strategy_provider"].values()
        if isinstance(item, StrategyProvider)
    )
