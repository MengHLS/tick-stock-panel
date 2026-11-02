"""Versioned strategy backtest defaults.

The parser here only owns the strategy-declared execution defaults. Core
matching rules (T+1, limit locks, board lots, suspensions, cash and position
constraints) remain enforced by :class:`app.backtest.engine.MatcherConfig` and
the simulation engine.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from app.backtest.engine import ExecutionCostPolicy, HoldExtensionPolicy

BACKTEST_DEFAULTS_SCHEMA_KEY = "schema_version"
BACKTEST_DEFAULTS_SCHEMA_VERSION = 1

_KNOWN_FIELDS = frozenset({
    BACKTEST_DEFAULTS_SCHEMA_KEY,
    "initial_capital",
    "max_positions",
    "max_exposure_pct",
    "commission_pct",
    "stamp_tax_pct",
    "slippage_bps",
    "fees_pct",
    "mode",
    "holding_days",
    "asset_type",
    "minute_fill",
    "regime_filter",
    "matching",
    "entry_fill",
    "exit_fill",
    "position_sizing",
    "position_policy",
    "position_policy_params",
    "score_tiers",
    "entry_open_gap_range",
    "entry_prev_day_change_range",
    "trailing_peak_price",
    "exit_signal_requires_profit",
    "hold_extension",
    "execution_costs",
    "plan_at_signal_close",
    "max_daily_entries",
    "entry_price_basis",
    "block_limit_open",
})

_POSITION_SIZING = frozenset({"equal", "score_weight", "score_tier", "policy"})
_MATCHING = frozenset({"close_t", "open_t+1"})
_EXIT_FILL = frozenset({"close_t", "open_t+1", "signal_next_minute"})


class BacktestDefaultsError(ValueError):
    """Strategy ``backtest_defaults`` is malformed or unsupported."""


@dataclass(frozen=True)
class ExecutionPolicy:
    """Normalized execution rules read from ``META.backtest_defaults``."""

    schema_version: int
    legacy: bool
    score_tiers: tuple[tuple[float, float], ...] | None = None
    entry_open_gap_range: tuple[float, float] | None = None
    entry_prev_day_change_range: tuple[float, float] | None = None
    trailing_peak_price: Literal["high", "close"] = "high"
    exit_signal_requires_profit: bool = False
    hold_extension_policy: HoldExtensionPolicy | None = None
    execution_costs: ExecutionCostPolicy | None = None
    plan_at_signal_close: bool = False
    max_daily_entries: int | None = None
    entry_price_basis: Literal["adjusted", "raw"] = "adjusted"
    block_limit_open: bool = False

    def engine_options(self) -> dict[str, object]:
        """Return the subset consumed by ``MatcherConfig``."""
        return {
            "score_tiers": self.score_tiers,
            "entry_open_gap_range": self.entry_open_gap_range,
            "entry_prev_day_change_range": self.entry_prev_day_change_range,
            "trailing_peak_price": self.trailing_peak_price,
            "exit_signal_requires_profit": self.exit_signal_requires_profit,
            "hold_extension_policy": self.hold_extension_policy,
            "execution_costs": self.execution_costs,
            "plan_at_signal_close": self.plan_at_signal_close,
            "max_daily_entries": self.max_daily_entries,
            "entry_price_basis": self.entry_price_basis,
            "block_limit_open": self.block_limit_open,
        }


def parse_backtest_defaults(raw: object, *, context: str = "strategy") -> ExecutionPolicy:
    """Parse legacy unversioned or v1 strategy backtest defaults.

    A missing ``schema_version`` is the legacy format and is interpreted as v1
    without rewriting strategy files. Unknown versions and unknown fields in a
    versioned payload fail closed. Legacy unknown fields remain ignored so old
    strategy files continue to load.
    """
    if raw is None:
        payload: dict = {}
        legacy = True
    elif isinstance(raw, dict):
        payload = dict(raw)
        legacy = BACKTEST_DEFAULTS_SCHEMA_KEY not in payload
    else:
        raise BacktestDefaultsError(
            f"{context} backtest_defaults must be an object"
        )

    schema_version = _schema_version(payload, legacy=legacy, context=context)
    unknown = sorted(set(payload) - _KNOWN_FIELDS)
    if unknown and not legacy:
        raise BacktestDefaultsError(
            f"{context} backtest_defaults v{schema_version} has unknown fields: "
            + ", ".join(unknown)
        )

    _validate_base_fields(payload, context=context)
    score_tiers = _score_tiers(payload.get("score_tiers"), context=context)
    hold_policy = _hold_policy(payload.get("hold_extension"), context=context)
    execution_costs = _execution_costs(
        payload.get("execution_costs"), context=context
    )
    trailing_peak = _choice(
        payload.get("trailing_peak_price", "high"),
        {"high", "close"},
        "trailing_peak_price",
        context,
    )
    entry_price_basis = _choice(
        payload.get("entry_price_basis", "adjusted"),
        {"adjusted", "raw"},
        "entry_price_basis",
        context,
    )
    max_daily_entries = _optional_int(
        payload.get("max_daily_entries"), "max_daily_entries", context,
        minimum=1,
    )
    entry_fill = _optional_choice(
        payload.get("entry_fill"), _MATCHING, "entry_fill", context
    )
    matching = _optional_choice(
        payload.get("matching"), _MATCHING, "matching", context
    )
    _optional_choice(
        payload.get("exit_fill"), _EXIT_FILL, "exit_fill", context
    )
    plan_at_signal_close = _bool(
        payload.get("plan_at_signal_close", False),
        "plan_at_signal_close",
        context,
    )
    effective_entry_fill = entry_fill or matching
    if plan_at_signal_close and effective_entry_fill not in (None, "open_t+1"):
        raise BacktestDefaultsError(
            f"{context} backtest_defaults: plan_at_signal_close requires "
            "next-open entries"
        )
    if matching and entry_fill and matching != entry_fill:
        # The explicit fields win, matching is retained only as a legacy
        # fallback. A disagreement is valid, so no migration is required.
        pass

    return ExecutionPolicy(
        schema_version=schema_version,
        legacy=legacy,
        score_tiers=score_tiers,
        entry_open_gap_range=_range(
            payload.get("entry_open_gap_range"),
            "entry_open_gap_range",
            context,
        ),
        entry_prev_day_change_range=_range(
            payload.get("entry_prev_day_change_range"),
            "entry_prev_day_change_range",
            context,
        ),
        trailing_peak_price=trailing_peak,  # type: ignore[arg-type]
        exit_signal_requires_profit=_bool(
            payload.get("exit_signal_requires_profit", False),
            "exit_signal_requires_profit",
            context,
        ),
        hold_extension_policy=hold_policy,
        execution_costs=execution_costs,
        plan_at_signal_close=plan_at_signal_close,
        max_daily_entries=max_daily_entries,
        entry_price_basis=entry_price_basis,  # type: ignore[arg-type]
        block_limit_open=_bool(
            payload.get("block_limit_open", False),
            "block_limit_open",
            context,
        ),
    )


def _schema_version(payload: dict, *, legacy: bool, context: str) -> int:
    if legacy:
        return BACKTEST_DEFAULTS_SCHEMA_VERSION
    raw = payload[BACKTEST_DEFAULTS_SCHEMA_KEY]
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise BacktestDefaultsError(
            f"{context} backtest_defaults schema_version must be an integer"
        )
    if raw != BACKTEST_DEFAULTS_SCHEMA_VERSION:
        raise BacktestDefaultsError(
            f"{context} backtest_defaults schema_version {raw} is not supported; "
            f"expected {BACKTEST_DEFAULTS_SCHEMA_VERSION}"
        )
    return raw


def _validate_base_fields(payload: dict, *, context: str) -> None:
    for key in ("initial_capital", "max_exposure_pct"):
        value = _optional_float(payload.get(key), key, context)
        if value is not None and value <= 0:
            raise BacktestDefaultsError(
                f"{context} backtest_defaults.{key} must be positive"
            )
    if payload.get("max_positions") is not None:
        _int(payload["max_positions"], "max_positions", context, minimum=1)
    if payload.get("holding_days") is not None:
        _int(payload["holding_days"], "holding_days", context, minimum=1)
    for key in ("commission_pct", "stamp_tax_pct", "slippage_bps", "fees_pct"):
        value = _optional_float(payload.get(key), key, context)
        if value is not None and value < 0:
            raise BacktestDefaultsError(
                f"{context} backtest_defaults.{key} must be non-negative"
            )
    for key, allowed in (
        ("mode", {"position", "full"}),
        ("asset_type", {"stock", "etf"}),
        ("position_sizing", _POSITION_SIZING),
    ):
        _optional_choice(payload.get(key), allowed, key, context)
    if payload.get("minute_fill") is not None:
        _bool(payload["minute_fill"], "minute_fill", context)
    for key in ("position_policy",):
        value = payload.get(key)
        if value is not None and not isinstance(value, str):
            raise BacktestDefaultsError(
                f"{context} backtest_defaults.{key} must be a string"
            )
    for key in ("position_policy_params", "regime_filter"):
        value = payload.get(key)
        if value is not None and not isinstance(value, dict):
            raise BacktestDefaultsError(
                f"{context} backtest_defaults.{key} must be an object"
            )


def _score_tiers(raw: object, *, context: str) -> tuple[tuple[float, float], ...] | None:
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)):
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.score_tiers must be a list"
        )
    tiers: list[tuple[float, float]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise BacktestDefaultsError(
                f"{context} backtest_defaults.score_tiers[{index}] must be a pair"
            )
        minimum = _float(
            item[0], f"score_tiers[{index}][0]", context
        )
        fraction = _float(item[1], f"score_tiers[{index}][1]", context)
        if not 0.0 <= fraction <= 1.0:
            raise BacktestDefaultsError(
                f"{context} backtest_defaults.score_tiers[{index}] fraction "
                "must be between 0 and 1"
            )
        tiers.append((minimum, fraction))
    return tuple(sorted(tiers, key=lambda value: value[0])) if tiers else None


def _hold_policy(raw: object, *, context: str) -> HoldExtensionPolicy | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.hold_extension must be an object"
        )
    unknown = sorted(set(raw) - {
        "decision_days",
        "strong_hold_days",
        "strong_hold_min_return",
        "runner_new_high_days",
        "runner_extend_days",
    })
    if unknown:
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.hold_extension has unknown fields: "
            + ", ".join(unknown)
        )
    try:
        return HoldExtensionPolicy(
            decision_days=_int(
                raw.get("decision_days", 5), "hold_extension.decision_days",
                context, minimum=2,
            ),
            strong_hold_days=_int(
                raw.get("strong_hold_days", 10), "hold_extension.strong_hold_days",
                context, minimum=1,
            ),
            strong_hold_min_return=_float(
                raw.get("strong_hold_min_return", 0.03),
                "hold_extension.strong_hold_min_return",
                context,
            ),
            runner_new_high_days=_int(
                raw.get("runner_new_high_days", 3),
                "hold_extension.runner_new_high_days",
                context,
                minimum=1,
            ),
            runner_extend_days=_int(
                raw.get("runner_extend_days", 74),
                "hold_extension.runner_extend_days",
                context,
                minimum=1,
            ),
        )
    except ValueError as exc:
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.hold_extension is invalid: {exc}"
        ) from exc


def _execution_costs(raw: object, *, context: str) -> ExecutionCostPolicy | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.execution_costs must be an object"
        )
    unknown = sorted(set(raw) - {
        "min_commission",
        "transfer_fee_pct",
        "buy_slippage_tiers",
        "price_decimals",
    })
    if unknown:
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.execution_costs has unknown fields: "
            + ", ".join(unknown)
        )
    tiers = raw.get("buy_slippage_tiers", [])
    if not isinstance(tiers, (list, tuple)):
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.execution_costs.buy_slippage_tiers "
            "must be a list"
        )
    parsed_tiers: list[tuple[float, float]] = []
    for index, item in enumerate(tiers):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise BacktestDefaultsError(
                f"{context} execution_costs.buy_slippage_tiers[{index}] "
                "must be a pair"
            )
        parsed_tiers.append((
            _float(item[0], f"buy_slippage_tiers[{index}][0]", context),
            _float(item[1], f"buy_slippage_tiers[{index}][1]", context),
        ))
    try:
        return ExecutionCostPolicy(
            min_commission=_float(
                raw.get("min_commission", 0.0),
                "execution_costs.min_commission",
                context,
            ),
            transfer_fee_pct=_float(
                raw.get("transfer_fee_pct", 0.0),
                "execution_costs.transfer_fee_pct",
                context,
            ),
            buy_slippage_tiers=tuple(parsed_tiers),
            price_decimals=_int(
                raw.get("price_decimals", 4),
                "execution_costs.price_decimals",
                context,
                minimum=0,
            ),
        )
    except ValueError as exc:
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.execution_costs is invalid: {exc}"
        ) from exc


def _range(raw: object, name: str, context: str) -> tuple[float, float] | None:
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.{name} must be a pair"
        )
    low = _float(raw[0], name, context)
    high = _float(raw[1], name, context)
    if low > high:
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.{name} lower bound must not exceed "
            "upper bound"
        )
    return low, high


def _float(raw: object, name: str, context: str) -> float:
    if raw is None or raw == "" or isinstance(raw, bool):
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.{name} must be a finite number"
        )
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.{name} must be a finite number"
        ) from exc
    if not math.isfinite(value):
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.{name} must be a finite number"
        )
    return value


def _optional_float(raw: object, name: str, context: str) -> float | None:
    return None if raw is None else _float(raw, name, context)


def _int(raw: object, name: str, context: str, *, minimum: int) -> int:
    if isinstance(raw, bool):
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.{name} must be an integer"
        )
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.{name} must be an integer"
        ) from exc
    if value < minimum:
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.{name} must be at least {minimum}"
        )
    return value


def _optional_int(
    raw: object, name: str, context: str, *, minimum: int,
) -> int | None:
    return None if raw is None else _int(raw, name, context, minimum=minimum)


def _bool(raw: object, name: str, context: str) -> bool:
    if not isinstance(raw, bool):
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.{name} must be true or false"
        )
    return raw


def _choice(raw: object, allowed: set[str], name: str, context: str) -> str:
    if not isinstance(raw, str) or raw not in allowed:
        raise BacktestDefaultsError(
            f"{context} backtest_defaults.{name} must be one of "
            f"{sorted(allowed)}"
        )
    return raw


def _optional_choice(
    raw: object, allowed: set[str], name: str, context: str,
) -> str | None:
    return None if raw is None else _choice(raw, allowed, name, context)
