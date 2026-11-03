"""Minute-level entry and fixed-stop exit simulation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import floor, isfinite
from statistics import median

import polars as pl

from .contracts import EventRecord, ExitResult, FillResult, TriggerCandidate

_PRICE_TOLERANCE = 0.005
_STOP_LAST_DECISION_TIME = time(14, 56)
_FORCED_EXIT_ORDER_TIME = time(14, 57)
_STAMP_DUTY_CHANGE_DATE = date(2023, 8, 28)

_DAILY_CONTEXT_COLUMNS = {
    "symbol",
    "date",
    "raw_close",
    "limit_up_price",
    "limit_down_price",
    "tradable",
    "suspended",
    "st_flag",
}

_BAR_COLUMNS = {
    "symbol",
    "bar_start",
    "bar_end",
    "volume",
    "open_raw",
    "high_raw",
    "low_raw",
    "close_raw",
    "amount_raw",
    "open_adj",
    "high_adj",
    "low_adj",
    "close_adj",
    "amount_adj",
}


@dataclass(frozen=True)
class SimulationConfig:
    target_notional: float = 18_000.0
    lot_size: int = 100
    commission_bps: float = 2.5
    min_commission: float = 5.0
    stamp_duty_bps: float | None = None
    slippage_bps: float = 5.0
    stop_loss_pct: float = 0.06
    max_holding_days: int = 20
    capacity_fraction: float = 0.01

    def __post_init__(self) -> None:
        if self.target_notional <= 0:
            raise ValueError("target_notional must be positive")
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
        if self.max_holding_days <= 0:
            raise ValueError("max_holding_days must be positive")
        for name in (
            "commission_bps",
            "min_commission",
            "slippage_bps",
            "capacity_fraction",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if not 0 < self.stop_loss_pct < 1:
            raise ValueError("stop_loss_pct must be between zero and one")
        if self.stamp_duty_bps is not None and self.stamp_duty_bps < 0:
            raise ValueError("stamp_duty_bps must be non-negative")


def _context_map(daily_context: pl.DataFrame) -> dict[date, dict]:
    if daily_context.is_empty():
        return {}
    missing = _DAILY_CONTEXT_COLUMNS - set(daily_context.columns)
    if missing:
        raise ValueError(
            f"daily_context missing required columns: {sorted(missing)}"
        )
    if daily_context.select("date").is_duplicated().any():
        raise ValueError("daily_context must be unique by date")
    return {
        row["date"]: row
        for row in daily_context.sort("date").iter_rows(named=True)
    }


def _prepare_bars(symbol: str, bars: pl.DataFrame) -> pl.DataFrame:
    if bars.is_empty():
        return bars
    missing = _BAR_COLUMNS - set(bars.columns)
    if missing:
        raise ValueError(
            f"minute bars missing required columns: {sorted(missing)}"
        )
    return bars.filter(pl.col("symbol") == symbol).sort("bar_start")


def _day_ratio(bars: pl.DataFrame) -> float | None:
    ratios: list[float] = []
    for raw_column, adj_column in (
        ("open_raw", "open_adj"),
        ("high_raw", "high_adj"),
        ("low_raw", "low_adj"),
        ("close_raw", "close_adj"),
    ):
        for raw, adj in bars.select(raw_column, adj_column).iter_rows():
            if (
                raw is not None
                and adj is not None
                and raw > 0
                and adj > 0
                and isfinite(raw)
                and isfinite(adj)
            ):
                ratios.append(float(adj) / float(raw))
    if not ratios:
        return None
    ratio = float(median(ratios))
    return ratio if ratio > 0 and isfinite(ratio) else None


def _blocked(
    candidate: TriggerCandidate,
    reason: str,
    capacity_base_amount: float | None,
) -> FillResult:
    return FillResult(
        candidate_id=candidate.candidate_id,
        event_id=candidate.event_id,
        symbol=candidate.symbol,
        filled=False,
        capacity_base_amount=capacity_base_amount,
        blocked_reason=reason,
    )


def _is_locked(bar: dict, price: float | None, *, upper: bool) -> bool:
    if price is None:
        return False
    high = bar["high_raw"]
    low = bar["low_raw"]
    if high is None or low is None:
        return False
    locked_range = float(high) - float(low) <= _PRICE_TOLERANCE
    if not locked_range:
        return False
    if upper:
        return float(low) >= float(price) - _PRICE_TOLERANCE
    return float(high) <= float(price) + _PRICE_TOLERANCE


def _first_fill_bar(
    bars: pl.DataFrame,
    order_time: datetime,
    symbol: str,
) -> pl.DataFrame:
    day_end = datetime.combine(order_time.date(), time()) + timedelta(days=1)
    return bars.filter(
        (pl.col("symbol") == symbol)
        & (pl.col("bar_start") >= order_time)
        & (pl.col("bar_start") < day_end)
    ).sort("bar_start").head(1)


def execute_entry(
    candidate: TriggerCandidate,
    bars: pl.DataFrame,
    daily_context: pl.DataFrame,
    config: SimulationConfig,
    *,
    capacity_base_amount: float | None,
) -> FillResult:
    """Fill at the first minute bar opening at or after the order time."""
    prepared = _prepare_bars(candidate.symbol, bars)
    contexts = _context_map(daily_context)
    context = contexts.get(candidate.order_time.date())
    base = (
        float(capacity_base_amount)
        if capacity_base_amount is not None
        else None
    )
    if base is None or base <= 0:
        return _blocked(candidate, "capacity_history_missing", base)
    if context is None:
        return _blocked(candidate, "daily_context_missing", base)
    if bool(context["suspended"]):
        return _blocked(candidate, "suspended", base)
    if not bool(context["tradable"]):
        return _blocked(candidate, "not_tradable", base)

    fill_bars = _first_fill_bar(
        prepared,
        candidate.order_time,
        candidate.symbol,
    )
    if fill_bars.is_empty():
        return _blocked(candidate, "missing_fill_bar", base)
    bar = fill_bars.row(0, named=True)
    open_price = bar["open_raw"]
    volume = bar["volume"]
    if open_price is None or not isfinite(open_price) or open_price <= 0:
        return _blocked(candidate, "invalid_fill_price", base)
    if volume is None or volume <= 0:
        return _blocked(candidate, "zero_volume", base)
    if _is_locked(bar, context["limit_up_price"], upper=True):
        return _blocked(candidate, "limit_up_locked", base)

    day_bars = prepared.filter(
        pl.col("bar_start").dt.date() == candidate.order_time.date()
    )
    ratio = _day_ratio(day_bars)
    if ratio is None:
        return _blocked(candidate, "missing_adjustment_ratio", base)

    fill_price = float(open_price) * (1.0 + config.slippage_bps / 10_000.0)
    lot_cost = fill_price * config.lot_size
    quantity = floor(config.target_notional / lot_cost) * config.lot_size
    if quantity <= 0:
        return _blocked(candidate, "below_one_lot", base)
    notional = quantity * fill_price
    if notional > base * config.capacity_fraction:
        return _blocked(candidate, "capacity_exceeded", base)
    fee = max(
        config.min_commission,
        notional * config.commission_bps / 10_000.0,
    )
    return FillResult(
        candidate_id=candidate.candidate_id,
        event_id=candidate.event_id,
        symbol=candidate.symbol,
        filled=True,
        fill_time=bar["bar_start"],
        fill_price_raw=fill_price,
        entry_exec_adj=fill_price * ratio,
        capacity_base_amount=base,
        quantity=quantity,
        entry_fee=fee,
        entry_notional=notional,
    )


def _context_sellable(context: dict, bar: dict) -> bool:
    if bool(context["suspended"]) or not bool(context["tradable"]):
        return False
    if bar["volume"] is None or bar["volume"] <= 0:
        return False
    if _is_locked(bar, context["limit_down_price"], upper=False):
        return False
    open_price = bar["open_raw"]
    return (
        open_price is not None
        and isfinite(open_price)
        and open_price > 0
    )


def _close_exit(
    fill: FillResult,
    config: SimulationConfig,
    *,
    status: str,
    reason: str,
    trigger_time: datetime | None,
    order_time: datetime | None,
    fill_time: datetime,
    raw_price: float,
    pending_days: int,
) -> ExitResult:
    proceeds = raw_price * fill.quantity
    stamp_duty_bps = (
        config.stamp_duty_bps
        if config.stamp_duty_bps is not None
        else (
            5.0
            if fill_time.date() >= _STAMP_DUTY_CHANGE_DATE
            else 10.0
        )
    )
    fee = (
        max(
            config.min_commission,
            proceeds * config.commission_bps / 10_000.0,
        )
        + proceeds * stamp_duty_bps / 10_000.0
    )
    capital = fill.entry_notional + fill.entry_fee
    net_return = (
        (proceeds - fee - capital) / capital
        if capital > 0
        else None
    )
    return ExitResult(
        status=status,
        reason=reason,
        trigger_time=trigger_time,
        order_time=order_time,
        fill_time=fill_time,
        fill_price_raw=raw_price,
        pending_days=pending_days,
        quantity=fill.quantity,
        exit_fee=fee,
        net_return=net_return,
    )


def _pending_exit(
    *,
    reason: str,
    trigger_time: datetime | None,
    order_time: datetime | None,
    pending_days: int,
) -> ExitResult:
    return ExitResult(
        status="pending_exit",
        reason=reason,
        trigger_time=trigger_time,
        order_time=order_time,
        fill_time=None,
        fill_price_raw=None,
        pending_days=pending_days,
    )


def _first_sellable(bars: pl.DataFrame, context: dict) -> dict | None:
    for row in bars.iter_rows(named=True):
        if _context_sellable(context, row):
            return row
    return None


def _fallback_right_censored(
    trigger_time: datetime | None,
    order_time: datetime | None,
    pending_days: int,
) -> ExitResult:
    return ExitResult(
        status="right_censored",
        reason="no_exit_before_data_end",
        trigger_time=trigger_time,
        order_time=order_time,
        fill_time=None,
        fill_price_raw=None,
        pending_days=pending_days,
    )


def simulate_exit(
    fill: FillResult,
    bars: pl.DataFrame,
    daily_context: pl.DataFrame,
    config: SimulationConfig,
) -> ExitResult:
    """Apply T+1, gap-aware stop-loss and a 20-session forced exit."""
    if not fill.filled or fill.fill_time is None or fill.quantity <= 0:
        raise ValueError("simulate_exit requires a filled entry with quantity")

    prepared = _prepare_bars(fill.symbol, bars)
    contexts = _context_map(daily_context)
    entry_day = fill.fill_time.date()
    bar_days = set(
        prepared.filter(
            pl.col("bar_start").dt.date() >= entry_day
        )["bar_start"]
        .dt.date()
        .to_list()
    )
    all_days = sorted(
        day
        for day in set(contexts) | bar_days
        if day >= entry_day
    )
    day_index = {day: index for index, day in enumerate(all_days)}

    pending_reason: str | None = None
    pending_trigger: datetime | None = None
    pending_order: datetime | None = None
    pending_days = 0

    for day in all_days:
        context = contexts.get(day)
        day_bars = prepared.filter(pl.col("bar_start").dt.date() == day)
        if context is not None and bool(context.get("delisted", False)):
            settlement = context.get("final_settlement_price")
            if (
                settlement is not None
                and isfinite(settlement)
                and settlement > 0
            ):
                settled_at = datetime.combine(day, time(15, 0))
                return _close_exit(
                    fill,
                    config,
                    status="delisted",
                    reason="delisted",
                    trigger_time=settled_at,
                    order_time=settled_at,
                    fill_time=settled_at,
                    raw_price=float(settlement),
                    pending_days=pending_days,
                )
            return ExitResult(
                status="right_censored_delisting",
                reason="delisting_without_settlement",
                trigger_time=pending_trigger,
                order_time=pending_order,
                fill_time=None,
                fill_price_raw=None,
                pending_days=pending_days,
            )
        if context is None:
            raise ValueError(f"daily_context missing for {day}")

        if pending_reason is not None:
            order_bar = _first_sellable(day_bars, context)
            if order_bar is not None:
                return _close_exit(
                    fill,
                    config,
                    status="closed",
                    reason=pending_reason or "pending_exit",
                    trigger_time=pending_trigger,
                    order_time=order_bar["bar_start"],
                    fill_time=order_bar["bar_start"],
                    raw_price=(
                        float(order_bar["open_raw"])
                        * (1.0 - config.slippage_bps / 10_000.0)
                    ),
                    pending_days=pending_days,
                )
            pending_days += 1
            continue

        hold_index = day_index[day]
        if hold_index == 0:
            continue
        if day_bars.is_empty():
            continue

        if hold_index >= config.max_holding_days - 1:
            trigger_time = datetime.combine(
                day,
                _STOP_LAST_DECISION_TIME,
            )
            order_time = datetime.combine(day, _FORCED_EXIT_ORDER_TIME)
            order_bar_frame = day_bars.filter(
                pl.col("bar_start") >= order_time
            ).head(1)
            if order_bar_frame.is_empty():
                pending_reason = "forced_exit"
                pending_trigger = trigger_time
                pending_order = order_time
                pending_days = 1
                continue
            order_bar = order_bar_frame.row(0, named=True)
            if _context_sellable(context, order_bar):
                return _close_exit(
                    fill,
                    config,
                    status="closed",
                    reason="forced_exit",
                    trigger_time=trigger_time,
                    order_time=order_bar["bar_start"],
                    fill_time=order_bar["bar_start"],
                    raw_price=(
                        float(order_bar["open_raw"])
                        * (1.0 - config.slippage_bps / 10_000.0)
                    ),
                    pending_days=pending_days,
                )
            pending_reason = "forced_exit"
            pending_trigger = trigger_time
            pending_order = order_time
            pending_days = 1
            continue

        ratio = _day_ratio(day_bars)
        if ratio is None:
            raise ValueError(f"missing adjustment ratio for {day}")
        stop_price_raw = (
            fill.entry_exec_adj
            * (1.0 - config.stop_loss_pct)
            / ratio
        )

        first_bar = day_bars.row(0, named=True)
        if (
            first_bar["open_raw"] is not None
            and first_bar["open_raw"] <= stop_price_raw
        ):
            trigger_time = first_bar["bar_start"]
            if _context_sellable(context, first_bar):
                return _close_exit(
                    fill,
                    config,
                    status="closed",
                    reason="stop_loss",
                    trigger_time=trigger_time,
                    order_time=first_bar["bar_start"],
                    fill_time=first_bar["bar_start"],
                    raw_price=(
                        float(first_bar["open_raw"])
                        * (1.0 - config.slippage_bps / 10_000.0)
                    ),
                    pending_days=pending_days,
                )
            pending_reason = "stop_loss"
            pending_trigger = trigger_time
            pending_order = first_bar["bar_start"]
            pending_days = 1
            continue

        triggered = False
        for bar in day_bars.iter_rows(named=True):
            close = bar["close_raw"]
            if close is None or close > stop_price_raw:
                continue
            trigger_time = bar["bar_end"]
            if trigger_time.time() > _STOP_LAST_DECISION_TIME:
                pending_reason = "stop_after_cutoff"
                pending_trigger = trigger_time
                pending_order = None
                pending_days = 1
                triggered = True
                break
            later = day_bars.filter(
                pl.col("bar_start") >= trigger_time
            ).head(1)
            if later.is_empty():
                pending_reason = "stop_loss"
                pending_trigger = trigger_time
                pending_order = None
                pending_days = 1
                triggered = True
                break
            order_bar = later.row(0, named=True)
            if _context_sellable(context, order_bar):
                return _close_exit(
                    fill,
                    config,
                    status="closed",
                    reason="stop_loss",
                    trigger_time=trigger_time,
                    order_time=order_bar["bar_start"],
                    fill_time=order_bar["bar_start"],
                    raw_price=(
                        float(order_bar["open_raw"])
                        * (1.0 - config.slippage_bps / 10_000.0)
                    ),
                    pending_days=pending_days,
                )
            pending_reason = "stop_loss"
            pending_trigger = trigger_time
            pending_order = order_bar["bar_start"]
            pending_days = 1
            triggered = True
            break
        if triggered:
            continue

    if pending_reason is not None:
        return _pending_exit(
            reason=pending_reason,
            trigger_time=pending_trigger,
            order_time=pending_order,
            pending_days=pending_days,
        )
    return _fallback_right_censored(None, None, pending_days)


def pre_order_capacity_base(
    bars: pl.DataFrame,
    order_time: datetime,
    symbol: str,
) -> float:
    history = (
        bars.filter(
            (pl.col("symbol") == symbol)
            & (pl.col("bar_end") < order_time)
        )
        .sort("bar_end")
        .tail(20)
    )
    if history.height < 20:
        return 0.0
    amounts = [
        float(value)
        for value in history["amount_raw"].to_list()
        if value is not None and value >= 0
    ]
    return sum(amounts) / len(amounts) if len(amounts) == 20 else 0.0


def simulate_event_attempts(
    event: EventRecord,
    candidates: list[TriggerCandidate],
    bars: pl.DataFrame,
    daily_context: pl.DataFrame,
    config: SimulationConfig,
) -> tuple[FillResult, ExitResult | None, list[FillResult]]:
    """Execute the first fillable candidate and retain every fill attempt."""
    if not candidates:
        raise ValueError("at least one trigger candidate is required")
    attempts: list[FillResult] = []
    for candidate in sorted(
        candidates,
        key=lambda value: value.signal_available_time,
    ):
        if candidate.event_id != event.event_id:
            raise ValueError("candidate event_id does not match event")
        capacity_base = pre_order_capacity_base(
            bars,
            candidate.order_time,
            candidate.symbol,
        )
        fill = execute_entry(
            candidate,
            bars,
            daily_context,
            config,
            capacity_base_amount=capacity_base,
        )
        attempts.append(fill)
        if fill.filled:
            return (
                fill,
                simulate_exit(fill, bars, daily_context, config),
                attempts,
            )
    return attempts[-1], None, attempts


def simulate_event(
    event: EventRecord,
    candidates: list[TriggerCandidate],
    bars: pl.DataFrame,
    daily_context: pl.DataFrame,
    config: SimulationConfig,
) -> tuple[FillResult, ExitResult | None]:
    fill, exit_result, _ = simulate_event_attempts(
        event,
        candidates,
        bars,
        daily_context,
        config,
    )
    return fill, exit_result
