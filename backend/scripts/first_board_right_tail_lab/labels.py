"""Opportunity and executable labels for first-board events."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time
from math import exp

import polars as pl

from .contracts import ExitResult, FillResult, LabelRecord
from .simulator import SimulationConfig

_STOP_REASONS = {"stop_loss", "stop_after_cutoff"}

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


def _prepare_bars(fill: FillResult, bars: pl.DataFrame) -> pl.DataFrame:
    missing = _BAR_COLUMNS - set(bars.columns)
    if missing:
        raise ValueError(
            f"minute bars missing required columns: {sorted(missing)}"
        )
    prepared = bars.filter(pl.col("symbol") == fill.symbol)
    if prepared.is_empty():
        return prepared
    return (
        prepared.filter(pl.col("bar_end") > fill.fill_time)
        .with_columns(pl.col("bar_start").dt.date().alias("_label_date"))
        .sort(["bar_start", "bar_end"])
    )


def _label_dates(
    fill: FillResult,
    prepared: pl.DataFrame,
    trading_dates: Sequence[date] | None,
) -> list[date]:
    entry_day = fill.fill_time.date()
    if trading_dates is not None:
        return [
            value
            for value in sorted(set(trading_dates))
            if value >= entry_day
        ][:20]
    return [
        value
        for value in prepared.filter(
            pl.col("_label_date") >= entry_day
        )["_label_date"]
        .unique()
        .sort()
        .to_list()[:20]
    ]


def _finite_positive(column: str) -> pl.Expr:
    value = pl.col(column)
    return value.is_not_null() & value.is_finite() & (value > 0)


def _sellable_path(
    path: pl.DataFrame,
    symbol: str,
    entry_time: datetime,
    exit_time: datetime,
    daily_context: pl.DataFrame | None,
) -> pl.DataFrame:
    if daily_context is not None and not daily_context.is_empty():
        context_columns = [
            column
            for column in ("tradable", "suspended", "limit_down_price")
            if column in daily_context.columns
        ]
        context = (
            daily_context.filter(pl.col("symbol") == symbol)
            .select("date", *context_columns)
        )
        if context_columns:
            path = (
                path.with_columns(
                    pl.col("bar_start").dt.date().alias("date")
                )
                .drop(
                    [
                        column
                        for column in context_columns
                        if column in path.columns
                    ]
                )
                .join(context, on="date", how="left")
            )
    eligible = path.filter(
        (pl.col("bar_start") >= entry_time)
        & (pl.col("bar_start").dt.date() > entry_time.date())
        & (pl.col("bar_start") <= exit_time)
        & _finite_positive("open_adj")
        & (pl.col("volume") > 0)
    )
    if "tradable" in eligible.columns:
        eligible = eligible.filter(pl.col("tradable").fill_null(False))
    if "suspended" in eligible.columns:
        eligible = eligible.filter(~pl.col("suspended").fill_null(False))
    if "limit_down_price" in eligible.columns:
        locked = (
            ((pl.col("high_raw") - pl.col("low_raw")).abs() <= 0.005)
            & (
                pl.col("high_raw")
                <= pl.col("limit_down_price") + 0.005
            )
        )
        eligible = eligible.filter(~locked.fill_null(False))
    return eligible


def _first_peak(
    window: pl.DataFrame,
    label_dates: list[date],
) -> tuple[float, int, datetime, datetime]:
    max_high = float(window["high_adj"].max())
    matching = (
        window.filter(
            (pl.col("high_adj") - max_high).abs() <= 1e-10
        )
        .sort("bar_end")
        .head(1)
        .row(0, named=True)
    )
    peak_date = matching["bar_start"].date()
    return (
        max_high,
        label_dates.index(peak_date),
        matching["bar_start"],
        matching["bar_end"],
    )


def build_labels(
    fill: FillResult,
    exit_result: ExitResult,
    bars: pl.DataFrame,
    config: SimulationConfig,
    *,
    daily_context: pl.DataFrame | None = None,
    trading_dates: Sequence[date] | None = None,
) -> LabelRecord:
    """Build 20-session touch labels and realized-execution labels."""
    if not fill.filled or fill.fill_time is None or fill.entry_exec_adj is None:
        raise ValueError("build_labels requires a filled entry")
    prepared = _prepare_bars(fill, bars)
    label_dates = _label_dates(fill, prepared, trading_dates)
    if not label_dates:
        raise ValueError("no minute bars are available after entry")
    if len(label_dates) < 20:
        raise ValueError("fewer than 20 label sessions are available")
    calendar = (
        [
            value
            for value in sorted(set(trading_dates))
            if value >= fill.fill_time.date()
        ]
        if trading_dates is not None
        else [
            value
            for value in prepared["_label_date"].unique().sort().to_list()
            if value >= fill.fill_time.date()
        ]
    )

    window = prepared.filter(
        pl.col("_label_date").is_in(label_dates)
        & _finite_positive("high_adj")
        & _finite_positive("low_adj")
    )
    if window.is_empty():
        raise ValueError("no valid high/low path in the label window")

    max_high, peak_day, peak_bar_start, peak_bar_end = _first_peak(
        window,
        label_dates,
    )
    min_low = float(window["low_adj"].min())
    entry_price = float(fill.entry_exec_adj)
    mfe_touch = max_high / entry_price - 1.0
    mae_touch = min_low / entry_price - 1.0

    ordering_ambiguous = False
    stop_first = False
    stop_fill = exit_result.fill_time
    if (
        stop_fill is not None
        and exit_result.status == "closed"
        and exit_result.reason in _STOP_REASONS
    ):
        same_peak_bar = peak_bar_start <= stop_fill < peak_bar_end
        if same_peak_bar:
            ordering_ambiguous = True
            stop_first = True
        elif stop_fill < peak_bar_end:
            stop_first = True

    exit_status = exit_result.status
    exit_day = (
        exit_result.fill_time.date()
        if exit_result.fill_time is not None
        else None
    )
    within_settlement_window = bool(
        exit_day is not None
        and exit_day in calendar
        and calendar.index(exit_day) <= 24
    )
    executable_ready = (
        exit_status in {"closed", "delisted"}
        and exit_result.fill_time is not None
        and exit_result.net_return is not None
        and within_settlement_window
    )
    mfe_exec: float | None = None
    mae_exec: float | None = None
    exec_return: float | None = None
    if executable_ready:
        executable_path = _sellable_path(
            window,
            fill.symbol,
            fill.fill_time,
            exit_result.fill_time,
            daily_context,
        )
        if not executable_path.is_empty():
            mfe_exec = (
                float(executable_path["open_adj"].max()) / entry_price - 1.0
            )
            mae_exec = (
                float(executable_path["open_adj"].min()) / entry_price - 1.0
            )
        exec_return = float(exit_result.net_return)
    elif exit_status in {"pending_exit", "right_censored"} or (
        exit_status in {"closed", "delisted"}
        and not within_settlement_window
    ):
        exit_status = "right_censored"

    maturity_time = datetime.combine(label_dates[-1], time(15, 0))
    return LabelRecord(
        event_id=fill.event_id,
        candidate_id=fill.candidate_id,
        entry_exec_adj=entry_price,
        mfe_touch_20d=mfe_touch,
        mae_touch_20d=mae_touch,
        peak_day=peak_day,
        stop_first=stop_first,
        ordering_ambiguous=ordering_ambiguous,
        mfe_exec_20d=mfe_exec,
        mae_exec_20d=mae_exec,
        exec_return=exec_return,
        exit_status=exit_status,
        label_maturity_time=maturity_time,
    )


def classify_opportunity(label: LabelRecord) -> int:
    if label.stop_first:
        return 0
    if label.mfe_touch_20d >= 0.30 and label.peak_day <= 10:
        return 3
    if label.mfe_touch_20d >= 0.30:
        return 4
    if label.mfe_touch_20d >= 0.10:
        return 2
    return 1


def utility(label: LabelRecord) -> float:
    if label.stop_first:
        return 0.0
    decay = exp(-max(0, label.peak_day - 5) / 10.0)
    return label.mfe_touch_20d * decay
