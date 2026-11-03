"""Stable data contracts shared by the first-board research stages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

CONTROL_RULE = "E0"
TRIGGER_RULES: tuple[str, ...] = ("A", "B", "C", "D")
ALL_RULES = (CONTROL_RULE, *TRIGGER_RULES)


def _require_naive_datetime(value: datetime, field: str) -> None:
    if value.tzinfo is not None and value.utcoffset() is not None:
        raise ValueError(f"{field} must be a naive Beijing wall-clock datetime")


def make_event_id(symbol: str, event_date: date) -> str:
    return f"{symbol}:{event_date.isoformat()}"


def make_candidate_id(
    event_id: str,
    rule: str,
    signal_available_time: datetime,
) -> str:
    return f"{event_id}:{rule}:{signal_available_time.isoformat()}"


@dataclass(frozen=True)
class EventRecord:
    event_id: str
    symbol: str
    event_date: date
    t_high_raw: float
    t_high_adj: float
    t_close_raw: float
    t_close_adj: float
    price_limit_pct: float | None
    is_st_at_event: bool = False
    listing_age_source: str = "instrument"

    def __post_init__(self) -> None:
        if not self.event_id or not self.symbol:
            raise ValueError("event_id and symbol are required")
        for field in ("t_high_raw", "t_high_adj", "t_close_raw", "t_close_adj"):
            value = float(getattr(self, field))
            if not (value > 0 and value == value and abs(value) != float("inf")):
                raise ValueError(f"{field} must be a positive finite price")


@dataclass(frozen=True)
class TriggerCandidate:
    event_id: str
    symbol: str
    rule: str
    bar_end: datetime
    signal_available_time: datetime
    order_time: datetime
    signal_close_adj: float

    def __post_init__(self) -> None:
        if self.rule not in ALL_RULES:
            raise ValueError(f"unknown trigger rule: {self.rule}")
        if not self.event_id or not self.symbol:
            raise ValueError("event_id and symbol are required")
        _require_naive_datetime(self.bar_end, "bar_end")
        _require_naive_datetime(self.signal_available_time, "signal_available_time")
        _require_naive_datetime(self.order_time, "order_time")
        if self.signal_available_time != self.bar_end:
            raise ValueError("signal_available_time must equal the completed bar_end")
        if self.order_time < self.signal_available_time + timedelta(minutes=1):
            raise ValueError("order_time must enforce the one-minute execution delay")
        if not (self.signal_close_adj > 0):
            raise ValueError("signal_close_adj must be positive")

    @property
    def candidate_id(self) -> str:
        return make_candidate_id(
            self.event_id,
            self.rule,
            self.signal_available_time,
        )


@dataclass(frozen=True)
class FillResult:
    candidate_id: str
    event_id: str
    symbol: str
    filled: bool
    fill_time: datetime | None = None
    fill_price_raw: float | None = None
    entry_exec_adj: float | None = None
    capacity_base_amount: float | None = None
    blocked_reason: str | None = None
    quantity: int = 0
    entry_fee: float = 0.0
    entry_notional: float = 0.0

    def __post_init__(self) -> None:
        if self.fill_time is not None:
            _require_naive_datetime(self.fill_time, "fill_time")
        if self.filled:
            if self.fill_time is None or self.fill_price_raw is None:
                raise ValueError("filled result requires fill_time and fill_price_raw")
            if not (self.fill_price_raw > 0 and self.entry_exec_adj > 0):
                raise ValueError("filled result requires positive raw and adjusted prices")
        elif self.blocked_reason is None:
            raise ValueError("unfilled result requires blocked_reason")


@dataclass(frozen=True)
class ExitResult:
    status: str
    reason: str | None
    trigger_time: datetime | None
    order_time: datetime | None
    fill_time: datetime | None
    fill_price_raw: float | None
    pending_days: int = 0
    quantity: int = 0
    exit_fee: float = 0.0
    net_return: float | None = None

    def __post_init__(self) -> None:
        if self.status not in {
            "closed",
            "pending_exit",
            "right_censored",
            "right_censored_delisting",
            "delisted",
        }:
            raise ValueError(f"unknown exit status: {self.status}")
        for field in ("trigger_time", "order_time", "fill_time"):
            value = getattr(self, field)
            if value is not None:
                _require_naive_datetime(value, field)
        if self.pending_days < 0:
            raise ValueError("pending_days must be non-negative")
        if self.status == "closed":
            if self.fill_time is None or self.fill_price_raw is None:
                raise ValueError("closed exit requires fill_time and fill_price_raw")
        elif self.fill_price_raw is not None and not (self.fill_price_raw > 0):
            raise ValueError("fill_price_raw must be positive when provided")


@dataclass(frozen=True)
class LabelRecord:
    event_id: str
    candidate_id: str
    entry_exec_adj: float
    mfe_touch_20d: float
    mae_touch_20d: float
    peak_day: int
    stop_first: bool
    ordering_ambiguous: bool
    mfe_exec_20d: float | None
    mae_exec_20d: float | None
    exec_return: float | None
    exit_status: str
    label_maturity_time: datetime | None

    def __post_init__(self) -> None:
        if not 0 <= self.peak_day < 20:
            raise ValueError("peak_day must be within the 20-session label window")
        if self.label_maturity_time is not None:
            _require_naive_datetime(self.label_maturity_time, "label_maturity_time")


@dataclass(frozen=True)
class RuleUnavailable:
    event_id: str
    rule: str
    reason: str
    observed_at: datetime

    def __post_init__(self) -> None:
        if self.rule not in ALL_RULES:
            raise ValueError(f"unknown rule: {self.rule}")
        _require_naive_datetime(self.observed_at, "observed_at")
