"""Backend extension registry with version checks and deterministic freezing."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Generic, TypeVar

from fastapi import APIRouter

from app.extensions.contracts import (
    BACKEND_EXTENSION_API_VERSION,
    DefaultNotificationFormatter,
    NotificationFormatter,
    QuoteUpdateObserver,
)
from app.extensions.strategies import (
    BacktestCostModel,
    CandidateFilter,
    MonitorConditionEvaluator,
    RiskPolicy,
    ScoringPolicy,
    StrategyProvider,
    register_strategy_extension,
    validate_strategy_extension,
)

_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
T = TypeVar("T")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegisteredImplementation(Generic[T]):
    extension_id: str
    implementation_id: str
    implementation: T
    order: int


class BackendExtensionRegistrar:
    """Staging area: a failed setup is discarded without partial registration."""

    def __init__(self, extension_id: str, *, api_version: int) -> None:
        self.extension_id = extension_id
        self.api_version = api_version
        self.routers: list[APIRouter] = []
        self.notification_formatters: list[tuple[str, NotificationFormatter, int]] = []
        self.quote_observers: list[tuple[str, QuoteUpdateObserver, int]] = []
        self.candidate_filters: list[tuple[str, CandidateFilter]] = []
        self.scoring_policies: list[tuple[str, ScoringPolicy]] = []
        self.risk_policies: list[tuple[str, RiskPolicy]] = []
        self.backtest_cost_models: list[tuple[str, BacktestCostModel]] = []
        self.strategy_providers: list[tuple[str, StrategyProvider]] = []
        self.monitor_condition_evaluators: list[tuple[str, MonitorConditionEvaluator]] = []

    def include_router(self, router: APIRouter) -> None:
        if not isinstance(router, APIRouter):
            raise TypeError("router must be fastapi.APIRouter")
        self.routers.append(router)

    def register_notification_formatter(
        self,
        implementation_id: str,
        formatter: NotificationFormatter,
        *,
        order: int = 100,
    ) -> None:
        self.notification_formatters.append((implementation_id, formatter, order))

    def register_quote_observer(
        self,
        implementation_id: str,
        observer: QuoteUpdateObserver,
        *,
        order: int = 100,
    ) -> None:
        self.quote_observers.append((implementation_id, observer, order))

    def register_candidate_filter(self, implementation_id: str, implementation: CandidateFilter) -> None:
        self.candidate_filters.append((implementation_id, implementation))

    def register_scoring_policy(self, implementation_id: str, implementation: ScoringPolicy) -> None:
        self.scoring_policies.append((implementation_id, implementation))

    def register_risk_policy(self, implementation_id: str, implementation: RiskPolicy) -> None:
        self.risk_policies.append((implementation_id, implementation))

    def register_backtest_cost_model(self, implementation_id: str, implementation: BacktestCostModel) -> None:
        self.backtest_cost_models.append((implementation_id, implementation))

    def register_strategy_provider(self, implementation_id: str, implementation: StrategyProvider) -> None:
        self.strategy_providers.append((implementation_id, implementation))

    def register_monitor_condition_evaluator(
        self,
        implementation_id: str,
        implementation: MonitorConditionEvaluator,
    ) -> None:
        self.monitor_condition_evaluators.append((implementation_id, implementation))


class BackendExtensionRegistry:
    def __init__(self) -> None:
        self._extension_ids: set[str] = set()
        self._notification_formatters: list[RegisteredImplementation[NotificationFormatter]] = []
        self._quote_observers: list[RegisteredImplementation[QuoteUpdateObserver]] = []
        self._frozen = False

    @property
    def frozen(self) -> bool:
        return self._frozen

    @property
    def has_customizations(self) -> bool:
        return bool(self._extension_ids)

    @property
    def has_notification_formatters(self) -> bool:
        return bool(self._notification_formatters)

    @property
    def has_quote_observers(self) -> bool:
        return bool(self._quote_observers)

    def extension_ids(self) -> frozenset[str]:
        return frozenset(self._extension_ids)

    def register(self, registrar: BackendExtensionRegistrar) -> None:
        """Validate a staged extension fully before mutating the registry."""
        self._ensure_mutable()
        extension_id = registrar.extension_id
        self._validate_id(extension_id, "extension_id")
        if registrar.api_version != BACKEND_EXTENSION_API_VERSION:
            raise ValueError(
                f"extension {extension_id!r} requires backend API v{registrar.api_version}; "
                f"current is v{BACKEND_EXTENSION_API_VERSION}"
            )
        if extension_id in self._extension_ids:
            raise ValueError(f"duplicate extension id: {extension_id}")

        known_ids = {item.implementation_id for item in self._notification_formatters}
        staged_ids: set[str] = set()
        staged: list[RegisteredImplementation[NotificationFormatter]] = []
        for implementation_id, formatter, order in registrar.notification_formatters:
            self._validate_id(implementation_id, "implementation_id")
            if not isinstance(formatter, NotificationFormatter):
                raise TypeError("formatter must inherit NotificationFormatter")
            if formatter.api_version != BACKEND_EXTENSION_API_VERSION:
                raise ValueError(
                    f"formatter {implementation_id!r} requires API v{formatter.api_version}; "
                    f"current is v{BACKEND_EXTENSION_API_VERSION}"
                )
            if implementation_id in known_ids or implementation_id in staged_ids:
                raise ValueError(f"duplicate notification formatter id: {implementation_id}")
            staged_ids.add(implementation_id)
            staged.append(
                RegisteredImplementation(extension_id, implementation_id, formatter, order)
            )

        known_observer_ids = {item.implementation_id for item in self._quote_observers}
        staged_observers: list[RegisteredImplementation[QuoteUpdateObserver]] = []
        for implementation_id, observer, order in registrar.quote_observers:
            self._validate_id(implementation_id, "implementation_id")
            if not isinstance(observer, QuoteUpdateObserver):
                raise TypeError("observer must inherit QuoteUpdateObserver")
            if observer.api_version != BACKEND_EXTENSION_API_VERSION:
                raise ValueError(
                    f"observer {implementation_id!r} requires API v{observer.api_version}; "
                    f"current is v{BACKEND_EXTENSION_API_VERSION}"
                )
            if implementation_id in known_observer_ids:
                raise ValueError(f"duplicate quote observer id: {implementation_id}")
            known_observer_ids.add(implementation_id)
            staged_observers.append(
                RegisteredImplementation(extension_id, implementation_id, observer, order)
            )

        strategy_staged = (
            ("candidate_filter", registrar.candidate_filters),
            ("scoring_policy", registrar.scoring_policies),
            ("risk_policy", registrar.risk_policies),
            ("backtest_cost_model", registrar.backtest_cost_models),
            ("strategy_provider", registrar.strategy_providers),
            (
                "monitor_condition_evaluator",
                registrar.monitor_condition_evaluators,
            ),
        )
        for kind, entries in strategy_staged:
            seen: set[str] = set()
            for implementation_id, implementation in entries:
                self._validate_id(implementation_id, "implementation_id")
                if implementation_id in seen:
                    raise ValueError(f"duplicate {kind} id: {implementation_id}")
                validate_strategy_extension(kind, implementation_id, implementation)
                seen.add(implementation_id)

        self._extension_ids.add(extension_id)
        self._notification_formatters.extend(staged)
        self._quote_observers.extend(staged_observers)
        for kind, entries in strategy_staged:
            for implementation_id, implementation in entries:
                register_strategy_extension(kind, implementation_id, implementation)

    def freeze(self) -> None:
        self._notification_formatters.sort(
            key=lambda item: (item.order, item.implementation_id)
        )
        self._quote_observers.sort(
            key=lambda item: (item.order, item.implementation_id)
        )
        self._frozen = True

    def notification_formatters(
        self,
    ) -> tuple[RegisteredImplementation[NotificationFormatter], ...]:
        if not self._frozen:
            raise RuntimeError("backend extension registry must be frozen before use")
        if not self._notification_formatters:
            return (
                RegisteredImplementation(
                    "core", "core.notification", DefaultNotificationFormatter(), 0,
                ),
            )
        return tuple(self._notification_formatters)

    def quote_observers(
        self,
    ) -> tuple[RegisteredImplementation[QuoteUpdateObserver], ...]:
        if not self._frozen:
            raise RuntimeError("backend extension registry must be frozen before use")
        return tuple(self._quote_observers)

    def shutdown_quote_observers(self) -> None:
        for registered in self._quote_observers:
            try:
                registered.implementation.shutdown()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "quote observer shutdown failed %s: %s",
                    registered.implementation_id,
                    exc,
                )

    def _ensure_mutable(self) -> None:
        if self._frozen:
            raise RuntimeError("backend extension registry is frozen")

    @staticmethod
    def _validate_id(value: str, label: str) -> None:
        if not isinstance(value, str) or not _ID_RE.fullmatch(value):
            raise ValueError(f"invalid {label}: {value!r}")
