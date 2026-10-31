"""Auction tail-strength event study; raw prices, exact 09:30 five-minute VWAP.

Run from backend with --data-dir, --auction-dir (processed_v1),
--minute-dir (mint-5), --start, --end and a NEW --output directory.
The report contains both conditional event returns and a bounded shared-capital
portfolio simulation. The latter uses realised cash flows rather than daily
mark-to-market, so it is an allocation check, not a full production backtest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

if __name__ == "__main__":
    os.environ.setdefault("POLARS_MAX_THREADS", "4")

import numpy as np
import polars as pl

from app.market_time import CN_TZ
from app.price_limits import GEM_REGISTRATION_DATE, polars_limit_price, polars_price_limit_pct
from app.tickflow.security_status import attach_st_history, read_st_history

VERSION = "auction-tail-strength-v1"
KEYS = ["symbol", "date"]
RESULT_SCHEMA = {
    "symbol": pl.String, "date": pl.Date, "opening_gap": pl.Float64,
    "prev_close": pl.Float64, "auction_open": pl.Float64,
    "has_result": pl.Int64, "result_time": pl.Int64, "volume_shares": pl.Int64,
}
PREOPEN_SCHEMA = {
    "symbol": pl.String, "date": pl.Date, "c0924_ref_price": pl.Float64,
    "last_ref_price": pl.Float64, "c0924_matched_shares": pl.Int64,
    "last_matched_shares": pl.Int64, "last_imbalance": pl.Float64,
    "last_unmatched_buy_shares": pl.Int64, "c0924_unmatched_buy_shares": pl.Int64,
    "last_minute_matched_growth": pl.Float64,
    "post0920_matched_growth": pl.Float64, "last_time": pl.Int64,
    "last_age_ms": pl.Int64, "c0920_age_ms": pl.Int64, "c0924_age_ms": pl.Int64,
    "last_unmatched_sell_shares": pl.Int64,
    "c0924_unmatched_sell_shares": pl.Int64,
}
FACTORS = (
    "tail_price_change", "last_imbalance", "last_minute_matched_growth",
    "post0920_matched_growth", "volume_vs_prev",
)
TAIL_FACTORS = (
    "tail_price_change", "last_minute_matched_growth", "last_imbalance",
)
PERIODS = (
    ("development", date(2020, 1, 2), date(2022, 12, 31)),
    ("validation", date(2023, 1, 3), date(2024, 12, 31)),
    ("retrospective_stress", date(2025, 1, 2), date(2026, 6, 30)),
    ("retrospective_extension", date(2026, 7, 1), date(2026, 9, 30)),
    ("prospective", date(2026, 10, 1), date(2099, 12, 31)),
)
MODE2B_RULE = {
    "id": "M2B_tail_strength_low_volume",
    "research_status": "post_hoc_frozen_after_v6_full_run",
    "gap": "[0.02, 0.08)",
    "last_minute_matched_growth_rank_min": 0.75,
    "volume_vs_prev_rank_max_exclusive": 0.75,
    "minimum_population": 4,
    "exit": "third_trading_session_0930_0935_vwap",
}
TAIL_STRENGTH_RULE = {
    "id": "TailStrength_v1",
    "research_status": "preregistered_after_development_analysis",
    "gap": "[0.00, 0.08)",
    "tail_factors": list(TAIL_FACTORS),
    "tail_strength_rank_min": 0.70,
    "volume_vs_prev_rank_max_exclusive": 0.75,
    "tail_price_min_exclusive": 0.0,
    "minimum_population": 4,
    "last_observation_range": "09:24:00.000-09:24:59.999",
    "maximum_snapshot_age_ms": 30000,
    "boards": "SH/SZ main board; exclude 300/301/688/689 and BJ",
}


def gap_bucket() -> pl.Expr:
    gap = pl.col("opening_gap")
    return (
        pl.when(~gap.is_finite().fill_null(False)).then(None)
        .when(gap < 0.00).then(None)
        .when(gap < 0.02).then(pl.lit("0-2"))
        .when(gap < 0.04).then(pl.lit("2-4"))
        .when(gap < 0.06).then(pl.lit("4-6"))
        .when(gap < 0.08).then(pl.lit("6-8"))
        .otherwise(pl.lit("8+")).alias("gap_bucket")
    )


def main_board_symbol() -> pl.Expr:
    """Keep SH/SZ main-board stocks; exclude GEM, STAR and Beijing."""
    symbol = pl.col("symbol")
    return (
        symbol.str.contains(r"^\d{6}\.(SH|SZ)$").fill_null(False)
        & ~symbol.str.starts_with("30").fill_null(False)
        & ~symbol.str.starts_with("688").fill_null(False)
        & ~symbol.str.starts_with("689").fill_null(False)
    )


def _positive(name: str) -> pl.Expr:
    return (pl.col(name).is_finite() & (pl.col(name) > 0)).fill_null(False)


def _unique(frame: pl.DataFrame, keys: list[str]) -> pl.DataFrame:
    if frame.select(pl.struct(keys).is_duplicated().any()).item():
        raise ValueError(f"Duplicate observations: {keys}")
    return frame


def normalize_first_bars(frame: pl.DataFrame) -> pl.DataFrame:
    wall = (
        pl.col("ts").cast(pl.Datetime("ms")).dt.replace_time_zone("UTC")
        .dt.convert_time_zone("Asia/Shanghai")
    )
    frame = frame.filter(((pl.col("ts") + 28_800_000) % 86_400_000) == 34_200_000)
    frame = frame.with_columns(
        wall.dt.date().alias("date"),
        pl.col("symbol").str.replace(r"\.XSHG$", ".SH")
        .str.replace(r"\.XSHE$", ".SZ").str.replace(r"\.XBSE$", ".BJ"),
    )
    frame = _unique(frame, KEYS)
    if frame.filter(~pl.col("symbol").str.contains(r"^\d{6}\.(SH|SZ|BJ)$")).height:
        raise ValueError("Unknown minute symbol format")
    return frame.select(
        *KEYS, "open", "high", "low", "close", "volume",
        pl.when(_positive("volume") & _positive("amount"))
        .then(pl.col("amount") / pl.col("volume")).alias("vwap"),
    )


def _valid_bar(prefix: str) -> pl.Expr:
    return (
        pl.all_horizontal([_positive(prefix + name) for name in (
            "open", "low", "high", "vwap", "volume",
        )])
        & (pl.col(prefix + "high") >= pl.col(prefix + "low"))
        & (pl.col(prefix + "open") >= pl.col(prefix + "low") - 0.011)
        & (pl.col(prefix + "open") <= pl.col(prefix + "high") + 0.011)
        & (pl.col(prefix + "vwap") >= pl.col(prefix + "low") - 0.011)
        & (pl.col(prefix + "vwap") <= pl.col(prefix + "high") + 0.011)
    ).fill_null(False)


def evaluate_execution(
    events: pl.DataFrame, *, commission_bps: float = 3,
    stamp_tax_bps: float = 10, slippage_bps: float = 5,
) -> pl.DataFrame:
    for value in (commission_bps, stamp_tax_bps, slippage_bps):
        if not np.isfinite(value) or not 0 <= value < 1000:
            raise ValueError("Costs must be finite bps in [0, 1000)")
    previous_known = (
        pl.col("prev_boards").is_not_null()
        & (pl.col("prev_date") == pl.col("expected_prev_date"))
    ).fill_null(False)
    entry = (
        pl.when(~previous_known).then(pl.lit("previous_day_unknown"))
        .when(pl.col("prev_boards") == 1).then(pl.lit("previous_first_board"))
        .when(
            (pl.col("has_result") != 1).fill_null(True)
            | ~pl.col("result_time").is_between(92500000, 92959999).fill_null(False)
        ).then(pl.lit("auction_result_unavailable_before_open"))
        .when(pl.col("st_flag").is_null()).then(pl.lit("historical_status_unknown"))
        .when(pl.col("listing_date").is_null()).then(pl.lit("listing_date_unknown"))
        .when(~_positive("limit_up")).then(pl.lit("entry_price_limit_unknown"))
        # Leave IPO-specific fills outside this ordinary-stock study.
        .when(pl.col("sessions_since_listing").is_between(0, 19))
        .then(pl.lit("recent_listing"))
        .when(~_valid_bar("entry_")).then(pl.lit("missing_or_invalid_first_bar"))
        .when(
            ((pl.col("entry_open") - pl.col("auction_open")).abs() > 0.011)
            | ((pl.col("entry_open") - pl.col("daily_open")).abs() > 0.011)
            | ~_positive("daily_open") | ~_positive("auction_open")
        ).then(pl.lit("price_basis_mismatch"))
        .when(pl.col("entry_low") >= pl.col("limit_up") - 0.005)
        .then(pl.lit("entry_limit_locked"))
        .otherwise(pl.lit("ok")).alias("entry_reason")
    )
    exit_reason = (
        pl.when(pl.col("exit_date").is_null()).then(pl.lit("right_censored"))
        .when(pl.col("exit_date") <= pl.col("date")).then(pl.lit("t_plus_one_required"))
        .when(~pl.col("exit_st_known").fill_null(False))
        .then(pl.lit("exit_historical_status_unknown"))
        .when(
            pl.col("exit_prev_date").is_null()
            | pl.col("exit_expected_prev_date").is_null()
            | (pl.col("exit_prev_date") != pl.col("exit_expected_prev_date"))
        )
        .then(pl.lit("exit_previous_session_unknown"))
        .when(~_positive("exit_limit_down")).then(pl.lit("exit_price_limit_unknown"))
        .when(~_positive("exit_daily_volume")).then(pl.lit("exit_daily_volume_unavailable"))
        .when(~_valid_bar("exit_")).then(pl.lit("missing_or_invalid_exit_bar"))
        .when(
            ~_positive("entry_scale") | ~_positive("exit_scale")
            | ((pl.col("exit_scale") / pl.col("entry_scale") - 1).abs() > 1e-6)
        ).then(pl.lit("corporate_action_or_basis_change"))
        .when(
            ~_positive("exit_daily_open")
            | ((pl.col("exit_open") - pl.col("exit_daily_open")).abs() > 0.011)
        ).then(pl.lit("exit_price_basis_mismatch"))
        .when(pl.col("exit_high") <= pl.col("exit_limit_down") + 0.005)
        .then(pl.lit("exit_limit_locked"))
        .otherwise(pl.lit("ok")).alias("exit_reason")
    )
    frame = events.with_columns(entry, exit_reason)
    valid = (pl.col("entry_reason") == "ok") & (pl.col("exit_reason") == "ok")
    ratio = pl.col("exit_vwap") / pl.col("entry_vwap")
    buy_cost = (1 + slippage_bps / 10000) * (1 + commission_bps / 10000)
    sell_cost = (1 - slippage_bps / 10000) * (
        1 - (commission_bps + stamp_tax_bps) / 10000
    )
    return frame.with_columns(
        pl.when(valid).then(ratio - 1).alias("gross_return"),
        pl.when(valid).then(ratio * sell_cost / buy_cost - 1).alias("net_return"),
    )


def rank_signals(frame: pl.DataFrame) -> pl.DataFrame:
    """Rank before observing exits; ties are neutral and missing stays missing."""
    groups = ["date", "gap_bucket"]
    for column in (
        "last_unmatched_sell_shares", "c0924_unmatched_sell_shares",
        "last_age_ms", "c0924_age_ms",
    ):
        if column not in frame.columns:
            frame = frame.with_columns(
                pl.lit(None, dtype=pl.Int64).alias(column),
            )
    frame = frame.with_columns([
        pl.when(pl.col(c).is_finite()).then(pl.col(c)).alias(c) for c in FACTORS
    ])
    ranks = []
    for c in FACTORS:
        n = pl.col(c).count().over(groups)
        ranks.append(
            pl.when(pl.col(c).is_null()).then(None)
            .when(n <= 1).then(0.5)
            .otherwise((pl.col(c).rank("average").over(groups) - 1) / (n - 1))
            .alias("rank_" + c)
        )
    frame = frame.with_columns(
        *ranks, pl.len().over(groups).alias("signal_group_n"),
        *[pl.col(c).count().over(groups).alias("population_" + c) for c in FACTORS],
        (
            pl.col("last_unmatched_sell_shares").is_not_null()
            & pl.col("c0924_unmatched_sell_shares").is_not_null()
            & (pl.col("last_age_ms") <= 30000)
            & (pl.col("c0924_age_ms") <= 30000)
        ).fill_null(False).cast(pl.Int64).sum().over(groups).alias(
            "population_sell_expansion",
        ),
    ).with_columns((
        0.5 * pl.col("rank_last_imbalance")
        - 0.25 * pl.col("rank_post0920_matched_growth")
        - 0.25 * pl.col("rank_volume_vs_prev")
    ).alias("combo_score"), pl.mean_horizontal(
        *[pl.col("rank_" + c) for c in TAIL_FACTORS],
    ).alias("tail_strength_score"))
    n = pl.col("combo_score").count().over(groups)
    tail_n = pl.col("tail_strength_score").count().over(groups)
    frame = frame.with_columns(
        n.alias("combo_population"),
        pl.when(pl.col("combo_score").is_null()).then(None)
        .when(n <= 1).then(0.5)
        .otherwise((pl.col("combo_score").rank("average").over(groups) - 1) / (n - 1))
        .alias("combo_rank"),
        tail_n.alias("tail_strength_population"),
        pl.when(pl.col("tail_strength_score").is_null()).then(None)
        .when(tail_n <= 1).then(0.5)
        .otherwise(
            (pl.col("tail_strength_score").rank("average").over(groups) - 1)
            / (tail_n - 1),
        ).alias("tail_strength_rank"),
    )
    return frame.with_columns(
        (
            (pl.col("tail_strength_rank") >= TAIL_STRENGTH_RULE["tail_strength_rank_min"])
            & (
                pl.col("rank_volume_vs_prev")
                < TAIL_STRENGTH_RULE["volume_vs_prev_rank_max_exclusive"]
            )
            & (
                pl.col("tail_price_change")
                > TAIL_STRENGTH_RULE["tail_price_min_exclusive"]
            )
            & (
                pl.col("tail_strength_population")
                >= TAIL_STRENGTH_RULE["minimum_population"]
            )
            & (
                pl.col("population_volume_vs_prev")
                >= TAIL_STRENGTH_RULE["minimum_population"]
            )
        ).fill_null(False).alias("tail_strength_signal"),
    )


def freeze_signals(frame: pl.DataFrame) -> pl.DataFrame:
    """Freeze the candidate universe before looking at any D continuous bar."""
    known_previous = (
        pl.col("prev_boards").is_not_null()
        & (pl.col("prev_date") == pl.col("expected_prev_date"))
    )
    eligible = (
        main_board_symbol()
        & known_previous & (pl.col("prev_boards") != 1)
        & (pl.col("has_result") == 1)
        & pl.col("result_time").is_between(92500000, 92959999)
        & pl.col("st_flag").is_not_null()
        & pl.col("listing_date").is_not_null()
        & (
            pl.col("sessions_since_listing").is_null()
            | ~pl.col("sessions_since_listing").is_between(0, 19)
        )
        & (pl.col("listing_date") < pl.col("date"))
        & _positive("limit_up") & _positive("auction_open")
    ).fill_null(False)
    frame = frame.with_columns(
        main_board_symbol().alias("board_allowed"),
        eligible.alias("signal_eligible"),
    )
    ranked = rank_signals(frame.filter(pl.col("signal_eligible")))
    rank_cols = [
        *["rank_" + c for c in FACTORS],
        *["population_" + c for c in FACTORS],
        "population_sell_expansion", "signal_group_n",
        "combo_score", "combo_rank", "combo_population",
        "tail_strength_score", "tail_strength_rank",
        "tail_strength_population", "tail_strength_signal",
    ]
    return frame.join(ranked.select(*KEYS, *rank_cols), on=KEYS, how="left")


def attach_baseline(events: pl.DataFrame, *, eligible: pl.Expr) -> pl.DataFrame:
    """Use the identical complete-case factor universe for the comparison."""
    frame = events.filter(eligible & pl.col("net_return").is_finite())
    groups = ["date", "gap_bucket"]
    return frame.with_columns(
        pl.col("net_return").mean().over(groups).alias("baseline_return"),
        (pl.col("net_return") > 0).mean().over(groups).alias("baseline_win_rate"),
    ).with_columns(
        (pl.col("net_return") - pl.col("baseline_return")).alias("incremental_return"),
        ((pl.col("net_return") > 0).cast(pl.Float64) - pl.col("baseline_win_rate"))
        .alias("win_increment"),
    )


def _interval(values: np.ndarray) -> list[float] | None:
    values = values[np.isfinite(values)]
    return np.quantile(values, [0.025, 0.975]).tolist() if len(values) else None


def summarize(
    events: pl.DataFrame, *, bootstrap_samples: int = 1000, seed: int = 20261031,
) -> dict:
    frame = events.filter(pl.col("net_return").is_finite())
    if frame.is_empty():
        return {"n": 0, "event_days": 0, "mean_net_return": None}
    daily = frame.group_by("date").agg(
        pl.len().alias("n"),
        *[pl.col(c).sum().alias(c) for c in (
            "net_return", "incremental_return", "win_increment",
        )],
        (pl.col("net_return") > 0).sum().alias("wins"),
    ).sort("date")
    rng = np.random.default_rng(seed)
    intervals = {}
    # Same resampled date weights for all metrics, bounded temporary memory.
    samples = {c: [] for c in (
        "mean_net_return", "mean_incremental_return", "win_rate_increment",
    )}
    for offset in range(0, bootstrap_samples, 128):
        ids = rng.integers(0, daily.height, size=(
            min(128, bootstrap_samples - offset), daily.height,
        ))
        denominator = daily["n"].to_numpy()[ids].sum(axis=1)
        for output, column in zip(samples, (
            "net_return", "incremental_return", "win_increment",
        ), strict=True):
            samples[output].extend(
                (daily[column].to_numpy()[ids].sum(axis=1) / denominator).tolist(),
            )
    for name, values in samples.items():
        interval = _interval(np.asarray(values))
        intervals[name] = [round(v, 12) for v in interval] if interval else None
    return {
        "n": frame.height, "event_days": daily.height,
        "mean_net_return": frame["net_return"].mean(),
        "median_net_return": frame["net_return"].median(),
        "win_rate": (frame["net_return"] > 0).mean(),
        "mean_incremental_return": frame["incremental_return"].mean(),
        "win_rate_increment": frame["win_increment"].mean(),
        "cluster_bootstrap_95": intervals,
        "interval_status": "ok" if daily.height >= 30 else "insufficient_event_days",
    }


PORTFOLIO_DEFAULTS = {
    "initial_capital": 1_000_000.0,
    "position_pct": 0.05,
    "max_positions": 10,
    "max_new_per_day": 5,
    "max_exposure_pct": 0.50,
    "capacity_pct": 0.01,
    "minimum_notional": 1_000.0,
}


def simulate_signal_portfolio(
    events: pl.DataFrame,
    *,
    start: date,
    end: date,
    signal_column: str,
    score_column: str,
    rank_column: str | None = None,
    initial_capital: float = PORTFOLIO_DEFAULTS["initial_capital"],
    position_pct: float = PORTFOLIO_DEFAULTS["position_pct"],
    max_positions: int = PORTFOLIO_DEFAULTS["max_positions"],
    max_new_per_day: int = PORTFOLIO_DEFAULTS["max_new_per_day"],
    max_exposure_pct: float = PORTFOLIO_DEFAULTS["max_exposure_pct"],
    capacity_pct: float = PORTFOLIO_DEFAULTS["capacity_pct"],
    minimum_notional: float = PORTFOLIO_DEFAULTS["minimum_notional"],
) -> tuple[dict, list[dict], list[dict]]:
    """Allocate shared capital to a frozen D+3 signal.

    This intentionally uses realised cash flows only. It checks slot, cash and
    five-minute-capacity interactions without fabricating daily marks for open
    positions; the production Strategy Core remains the final portfolio gate.
    """
    if initial_capital <= 0 or not 0 < position_pct <= 1:
        raise ValueError("Invalid portfolio capital or position size")
    if max_positions < 1 or max_new_per_day < 1:
        raise ValueError("Portfolio slots must be positive")
    if not 0 < max_exposure_pct <= 1 or not 0 < capacity_pct <= 1:
        raise ValueError("Exposure and capacity must be in (0, 1]")
    for column in (signal_column, score_column, rank_column):
        if column and column not in events.columns:
            raise ValueError(f"Missing portfolio column: {column}")
    sort_columns = ["date", score_column]
    descending = [False, True]
    if rank_column:
        sort_columns.append(rank_column)
        descending.append(True)
    sort_columns.append("symbol")
    descending.append(False)
    frame = events.filter(
        (pl.col("horizon") == 3)
        & pl.col("date").is_between(start, end)
        & pl.col("exit_date").is_not_null()
        & (pl.col("exit_date") <= end)
        & pl.col("signal_eligible")
        & pl.col(signal_column).fill_null(False)
        & pl.col(score_column).is_finite()
        & (pl.col("entry_reason") == "ok")
        & (pl.col("exit_reason") == "ok")
        & pl.col("net_return").is_finite()
    ).sort(sort_columns, descending=descending)
    if frame.is_empty():
        return ({
            "status": "no_signals",
            **PORTFOLIO_DEFAULTS,
            "n_trades": 0,
            "total_return": None,
            "max_drawdown": None,
        }, [], [])

    by_date: dict[date, list[dict]] = {}
    for row in frame.to_dicts():
        by_date.setdefault(row["date"], []).append(row)
    calendar = sorted({
        *by_date,
        *(row["exit_date"] for row in frame.to_dicts()),
    })

    cash = float(initial_capital)
    committed = 0.0
    open_positions: list[dict] = []
    selected: list[dict] = []
    equity_curve: list[dict] = []
    rejected = {
        "no_slot": 0,
        "cash": 0,
        "exposure": 0,
        "capacity": 0,
        "minimum_notional": 0,
        "daily_limit": 0,
    }

    for day in calendar:
        still_open: list[dict] = []
        for position in open_positions:
            if position["exit_date"] <= day:
                cash += position["allocated"] * (1 + position["net_return"])
                committed -= position["allocated"]
            else:
                still_open.append(position)
        open_positions = still_open

        equity_before = cash + committed
        candidates = by_date.get(day, [])
        entered_today = 0
        for row in candidates:
            if entered_today >= max_new_per_day:
                rejected["daily_limit"] += len(candidates) - entered_today
                break
            if len(open_positions) >= max_positions:
                rejected["no_slot"] += len(candidates) - entered_today
                break
            equity_before = cash + committed
            capacity = row["entry_vwap"] * row["entry_volume"]
            capacity = capacity * capacity_pct if np.isfinite(capacity) and capacity > 0 else 0.0
            exposure_room = max(0.0, equity_before * max_exposure_pct - committed)
            target = equity_before * position_pct
            allocation = min(target, capacity, cash, exposure_room)
            if exposure_room <= 0 and allocation <= 0:
                rejected["exposure"] += len(candidates) - entered_today
                break
            if capacity <= minimum_notional:
                rejected["capacity"] += 1
                continue
            if allocation < minimum_notional:
                key = "cash" if cash < minimum_notional else "minimum_notional"
                rejected[key] += 1
                continue
            cash -= allocation
            committed += allocation
            position = {
                **row,
                "allocated": allocation,
                "entry_capacity": capacity,
                "entry_notional": row["entry_vwap"] * row["entry_volume"],
            }
            open_positions.append(position)
            selected.append(position)
            entered_today += 1
        equity_curve.append({
            "date": day.isoformat(),
            "cash": round(cash, 2),
            "committed": round(committed, 2),
            "equity_cost_basis": round(cash + committed, 2),
            "open_positions": len(open_positions),
            "exposure": committed / (cash + committed) if cash + committed > 0 else 0.0,
        })

    # The period filter guarantees all selected exits occurred by end.
    if open_positions:
        raise AssertionError("Portfolio retained positions past the frozen period")
    closed = selected
    returns = np.array([row["net_return"] for row in closed], dtype=float)
    equity = np.array([row["equity_cost_basis"] for row in equity_curve], dtype=float)
    running_peak = np.maximum.accumulate(equity) if equity.size else equity
    drawdown = equity / running_peak - 1 if equity.size else equity
    return ({
        "status": "ok",
        "initial_capital": initial_capital,
        "position_pct": position_pct,
        "max_positions": max_positions,
        "max_new_per_day": max_new_per_day,
        "max_exposure_pct": max_exposure_pct,
        "capacity_pct": capacity_pct,
        "candidate_n": frame.height,
        "n_trades": len(closed),
        "total_return": float(cash / initial_capital - 1),
        "final_equity": float(cash),
        "mean_trade_return": float(returns.mean()) if returns.size else None,
        "median_trade_return": float(np.median(returns)) if returns.size else None,
        "win_rate": float((returns > 0).mean()) if returns.size else None,
        "max_drawdown_realized": float(drawdown.min()) if drawdown.size else None,
        "mean_exposure": float(np.mean([row["exposure"] for row in equity_curve]))
        if equity_curve else None,
        "rejected": rejected,
        "limitations": [
            "Open positions use cost basis, not daily mark-to-market.",
            "Capacity is 1% of the observed 09:30-09:35 amount.",
            "This is not the production T+1/limit/tax engine.",
        ],
    }, selected, equity_curve)


def simulate_tail_portfolio(
    events: pl.DataFrame,
    *,
    start: date,
    end: date,
    initial_capital: float = PORTFOLIO_DEFAULTS["initial_capital"],
    position_pct: float = PORTFOLIO_DEFAULTS["position_pct"],
    max_positions: int = PORTFOLIO_DEFAULTS["max_positions"],
    max_new_per_day: int = PORTFOLIO_DEFAULTS["max_new_per_day"],
    max_exposure_pct: float = PORTFOLIO_DEFAULTS["max_exposure_pct"],
    capacity_pct: float = PORTFOLIO_DEFAULTS["capacity_pct"],
    minimum_notional: float = PORTFOLIO_DEFAULTS["minimum_notional"],
) -> tuple[dict, list[dict], list[dict]]:
    """Preserve the frozen TailStrength portfolio contract."""
    return simulate_signal_portfolio(
        events,
        start=start,
        end=end,
        signal_column="tail_strength_signal",
        score_column="tail_strength_score",
        rank_column="tail_strength_rank",
        initial_capital=initial_capital,
        position_pct=position_pct,
        max_positions=max_positions,
        max_new_per_day=max_new_per_day,
        max_exposure_pct=max_exposure_pct,
        capacity_pct=capacity_pct,
        minimum_notional=minimum_notional,
    )


def _partitions(root: Path, start: date, end: date) -> list[Path]:
    return sorted(
        p for p in root.glob("date=*/part.parquet")
        if start.isoformat() <= p.parent.name[5:] <= end.isoformat()
    )


def _read(paths: list[Path], columns: list[str]) -> pl.DataFrame:
    if not paths:
        raise ValueError("No input partitions in requested window")
    return pl.scan_parquet(paths, hive_partitioning=False).select(columns).collect()


def _read_or_empty(paths: list[Path], schema: dict) -> pl.DataFrame:
    return _read(paths, list(schema)) if paths else pl.DataFrame(schema=schema)


def _daily_context(
    data_dir: Path, start: date, end: date,
) -> tuple[pl.DataFrame, dict, list[date]]:
    files = _partitions(data_dir / "kline_daily", start - timedelta(days=120),
                        end + timedelta(days=30))
    daily = _unique(_read(files, [*KEYS, "open", "high", "low", "close", "volume"]), KEYS)
    enriched_files = [
        data_dir / "kline_daily_enriched" / p.parent.name / p.name for p in files
    ]
    enriched_files = [p for p in enriched_files if p.exists()]
    enriched = _unique(_read(enriched_files, [
        *KEYS, "close", "raw_close", "consecutive_limit_ups",
    ]), KEYS).rename({"close": "adj_close", "raw_close": "enriched_raw_close"})
    instruments_path = data_dir / "instruments" / "instruments.parquet"
    instruments = pl.read_parquet(instruments_path, columns=["symbol", "listing_date"])
    instruments = _unique(instruments, ["symbol"]).with_columns(
        pl.col("listing_date").cast(pl.String).str.to_date(strict=False),
    )
    history = read_st_history(data_dir)
    daily = daily.join(enriched, on=KEYS, how="left").join(
        instruments, on="symbol", how="left",
    ).sort(KEYS)
    raw_mismatch = daily.filter(
        pl.col("close").is_null() | ~pl.col("close").is_finite()
        | (pl.col("close") <= 0)
        | pl.col("enriched_raw_close").is_null()
        | ~pl.col("enriched_raw_close").is_finite()
        | (pl.col("enriched_raw_close") <= 0)
        | ((pl.col("close") - pl.col("enriched_raw_close")).abs() > 0.011),
    )
    if raw_mismatch.height:
        raise ValueError(f"Daily/enriched raw close mismatch: {raw_mismatch.height} rows")
    daily = attach_st_history(daily, history).with_columns(
        (pl.col("adj_close") / pl.col("enriched_raw_close")).alias("scale"),
        pl.col("date").shift(1).over("symbol").alias("prev_date"),
        pl.col("consecutive_limit_ups").shift(1).over("symbol").alias("prev_boards"),
        (pl.col("volume").shift(1).over("symbol") * 100).alias("prev_volume_shares"),
        pl.col("close").shift(1).over("symbol").alias("prev_raw_close"),
    )
    # Dated ST flags and the pre-reform GEM override match the existing adapter.
    pct = polars_price_limit_pct(pl.col("symbol"), pl.col("date"), pl.col("st_flag"))
    pre_gem = pl.col("symbol").str.starts_with("30") & (
        pl.col("date") < GEM_REGISTRATION_DATE
    )
    pct = pl.when(pre_gem).then(
        pl.when(pl.col("st_flag")).then(0.05).otherwise(0.10),
    ).otherwise(pct)
    daily = daily.with_columns(pct.alias("limit_pct"))
    daily = daily.with_columns(
        polars_limit_price(pl.col("prev_raw_close"), pl.col("limit_pct"), up=True)
        .alias("limit_up"),
        polars_limit_price(pl.col("prev_raw_close"), pl.col("limit_pct"), up=False)
        .alias("limit_down"),
    )
    # An independent broad index anchors sessions even when STOCK partitions
    # are absent. Never derive horizons from the possibly incomplete stock data.
    calendar_files = _partitions(
        data_dir / "kline_index_daily", start - timedelta(days=120), end + timedelta(days=30),
    )
    index_days = _read(calendar_files, KEYS).filter(pl.col("symbol") == "000001.SH")
    sessions = sorted(index_days["date"].unique().to_list())
    if not sessions or set(daily["date"].to_list()) - set(sessions):
        raise ValueError("Independent index-session calendar missing stock trading dates")
    session_frame = pl.DataFrame({
        "date": sessions, "session_no": list(range(len(sessions))),
    })
    daily = daily.join(session_frame, on="date", how="left").join(
        session_frame.select(
            pl.col("date").alias("listing_date"),
            pl.col("session_no").alias("listing_session_no"),
        ), on="listing_date", how="left",
    ).with_columns(
        (pl.col("session_no") - pl.col("listing_session_no")).alias(
            "sessions_since_listing",
        ),
    )
    calendar = pl.DataFrame({
        "date": sessions,
        "expected_prev_date": [None, *sessions[:-1]],
        "next_date": [*sessions[1:], None],
        "third_date": [*sessions[3:], *([None] * min(3, len(sessions)))],
    })
    sources = {
        str(p): [p.stat().st_size, p.stat().st_mtime_ns]
        for p in [*files, *enriched_files, *calendar_files, instruments_path,
                  *sorted((data_dir / "st_history").rglob("*.parquet"))]
    }
    daily = daily.join(calendar, on="date", how="left").with_columns(
        pl.when(pl.col("next_date") > pl.col("date")).then(pl.col("next_date")),
        pl.when(pl.col("third_date") > pl.col("next_date")).then(pl.col("third_date")),
    )
    return daily, sources, sessions


def _first_bars(
    minute_dir: Path, needed: pl.DataFrame,
) -> tuple[pl.DataFrame, dict]:
    if needed.is_empty():
        return pl.DataFrame(schema={
            "symbol": pl.String, "date": pl.Date,
            **dict.fromkeys(("open", "high", "low", "close", "volume", "vwap"), pl.Float64),
        }), {}
    start, end = needed["date"].min(), needed["date"].max()
    lower = int(datetime.combine(start, datetime.min.time(), tzinfo=CN_TZ).timestamp() * 1000)
    upper = int(datetime.combine(
        end + timedelta(days=1), datetime.min.time(), tzinfo=CN_TZ,
    ).timestamp() * 1000)
    files = sorted(
        p for p in minute_dir.glob("*.parquet")
        if p.stem[:4].isdigit() and start.year <= int(p.stem[:4]) <= end.year
    )
    pieces, sources = [], {}
    for path in files:
        before = path.stat()
        # Push predicates and projection into each source file independently.
        source = pl.scan_parquet(path).filter(
            (pl.col("ts") >= lower) & (pl.col("ts") < upper),
            ((pl.col("ts") + 28_800_000) % 86_400_000) == 34_200_000,
        ).select(["ts", "symbol", "open", "high", "low", "close", "volume", "amount"])
        source = source.with_columns(
            pl.col("ts").cast(pl.Datetime("ms")).dt.replace_time_zone("UTC")
            .dt.convert_time_zone("Asia/Shanghai").dt.date().alias("date"),
            pl.col("symbol").str.replace(r"\.XSHG$", ".SH")
            .str.replace(r"\.XSHE$", ".SZ").str.replace(r"\.XBSE$", ".BJ"),
        ).join(needed.unique(KEYS).lazy(), on=KEYS, how="semi")
        normalized = normalize_first_bars(source.collect(engine="streaming"))
        pieces.append(normalized)
        sources[str(path)] = [before.st_size, before.st_mtime_ns]
    if not pieces:
        raise ValueError("No five-minute source files")
    return _unique(pl.concat(pieces), KEYS), sources


def build_year(
    data_dir: Path, auction_dir: Path, minute_dir: Path, start: date, end: date,
    *, commission_bps: float, stamp_tax_bps: float, slippage_bps: float,
    allow_missing_auction: bool = False,
) -> tuple[pl.DataFrame, dict, dict[str, list[str]]]:
    daily, sources, sessions = _daily_context(data_dir, start, end)
    expected = [day for day in sessions if start <= day <= end]
    if not expected:
        raise ValueError("Requested window has no independently stored index sessions")
    result_files = _partitions(auction_dir / "result", start, end)
    pre_files = _partitions(auction_dir / "preopen", start, end)
    result_dates = {date.fromisoformat(p.parent.name[5:]) for p in result_files}
    preopen_dates = {date.fromisoformat(p.parent.name[5:]) for p in pre_files}
    missing = sorted(set(expected) - result_dates)
    missing_preopen = sorted(set(expected) - preopen_dates)
    if (missing or missing_preopen) and not allow_missing_auction:
        raise ValueError(
            "Auction partitions incomplete; "
            f"result_missing={len(missing)} preopen_missing={len(missing_preopen)} "
            f"first={(missing or missing_preopen)[:1]!s}",
        )
    results = _unique(_read_or_empty(result_files, RESULT_SCHEMA), KEYS).with_columns(
        gap_bucket(),
    ).filter(pl.col("gap_bucket").is_not_null())
    pre = _unique(_read_or_empty(pre_files, PREOPEN_SCHEMA), KEYS)
    for p in [*result_files, *pre_files]:
        sources[str(p)] = [p.stat().st_size, p.stat().st_mtime_ns]
    events = results.join(pre, on=KEYS, how="left").join(
        daily.select(
            *KEYS, pl.col("open").alias("daily_open"),
            pl.col("volume").alias("daily_volume"), "prev_date", "prev_boards",
            "expected_prev_date", "prev_volume_shares", "next_date", "third_date",
            "st_flag", "listing_date", "sessions_since_listing", "limit_pct",
            pl.col("scale").alias("entry_scale"),
        ), on=KEYS, how="left",
    ).with_columns(
        # The auction feed's official reference already reflects ex-rights.
        polars_limit_price(pl.col("prev_close"), pl.col("limit_pct"), up=True)
        .alias("limit_up"),
        pl.when(_positive("prev_volume_shares"))
        .then(pl.col("volume_shares") / pl.col("prev_volume_shares")).alias("volume_vs_prev"),
    )
    # Quality gates use only auction observations; no future exit drives ranks.
    fresh = (
        pl.col("last_time").is_between(92400000, 92459999)
        & (pl.col("last_age_ms") <= 30000)
    ).fill_null(False)
    events = events.with_columns(
        pl.when(
            fresh
            & (pl.col("c0924_age_ms") <= 30000)
            & _positive("c0924_ref_price")
            & _positive("last_ref_price")
        ).then(
            pl.col("last_ref_price") / pl.col("c0924_ref_price") - 1,
        ).alias("tail_price_change"),
        pl.when(fresh).then(pl.col("last_imbalance")).alias("last_imbalance"),
        pl.when(fresh & (pl.col("c0920_age_ms") <= 30000))
        .then(pl.col("post0920_matched_growth")).alias("post0920_matched_growth"),
        pl.when(fresh & (pl.col("c0924_age_ms") <= 30000))
        .then(pl.col("last_minute_matched_growth")).alias("last_minute_matched_growth"),
    )
    events = freeze_signals(events)
    # Freeze signals first; continuous-session data only affects fills.
    signal_events = events.filter(pl.col("signal_eligible"))
    needed = pl.concat([
        signal_events.select(*KEYS),
        *[
            signal_events.select("symbol", pl.col(c).alias("date"))
            for c in ("next_date", "third_date")
        ],
    ]).drop_nulls()
    bars, bar_sources = _first_bars(minute_dir, needed)
    sources.update(bar_sources)
    events = events.join(
        bars.rename({c: "entry_" + c for c in bars.columns if c not in KEYS}),
        on=KEYS, how="left",
    )
    pieces = []
    for horizon, exit_column in ((1, "next_date"), (3, "third_date")):
        exit_daily = daily.select(
            "symbol", pl.col("date").alias("exit_date"),
            pl.col("scale").alias("exit_scale"),
            pl.col("open").alias("exit_daily_open"),
            pl.col("volume").alias("exit_daily_volume"),
            pl.col("prev_date").alias("exit_prev_date"),
            pl.col("expected_prev_date").alias("exit_expected_prev_date"),
            pl.col("limit_down").alias("exit_limit_down"),
            pl.col("st_flag").is_not_null().alias("exit_st_known"),
            pl.col("close").alias("exit_daily_close"),
        )
        piece = events.with_columns(
            pl.col(exit_column).cast(pl.Date).alias("exit_date"),
        ).join(
            exit_daily, on=["symbol", "exit_date"], how="left",
        ).join(
            bars.rename({
                "date": "exit_date",
                **{c: "exit_" + c for c in bars.columns if c not in KEYS},
            }), on=["symbol", "exit_date"], how="left",
        )
        piece = evaluate_execution(
            piece, commission_bps=commission_bps,
            stamp_tax_bps=stamp_tax_bps, slippage_bps=slippage_bps,
        ).with_columns(pl.lit(horizon).alias("horizon"))
        pieces.append(piece)
    coverage_gap = {
        "result": [day.isoformat() for day in missing],
        "preopen": [day.isoformat() for day in missing_preopen],
    }
    return pl.concat(pieces, how="diagonal_relaxed"), sources, coverage_gap


def build_report(events: pl.DataFrame, *, bootstrap_samples: int, seed: int) -> dict:
    rows = []
    main_next = events.filter(
        (pl.col("horizon") == 1) & (pl.col("gap_bucket") != "8+"),
    )
    for period, start, end in PERIODS:
        period_events = events.filter(pl.col("date").is_between(start, end))
        if period_events.is_empty():
            continue
        for horizon in (1, 3):
            horizon_events = period_events.filter(pl.col("horizon") == horizon)
            frame = horizon_events.filter(
                pl.col("exit_date").is_null() | (pl.col("exit_date") <= end),
            )
            for bucket in (
                "main_0_8", "0-2", "main_2_8", "2-4", "4-6", "6-8", "8+",
            ):
                bucket_mask = {
                    "main_0_8": pl.col("gap_bucket") != "8+",
                    "main_2_8": pl.col("gap_bucket").is_in(["2-4", "4-6", "6-8"]),
                }.get(bucket, pl.col("gap_bucket") == bucket)
                signal_scope = horizon_events.filter(bucket_mask)
                sub = frame.filter(bucket_mask)
                if signal_scope.is_empty():
                    continue
                variants = [("B0_all", pl.lit(True), pl.lit(True))]
                for factor in FACTORS:
                    eligible = pl.col(factor).is_finite() & (pl.col("population_" + factor) >= 4)
                    for label, condition in (
                        ("low", pl.col("rank_" + factor) <= 0.25),
                        ("middle", pl.col("rank_" + factor).is_between(0.25, 0.75, closed="none")),
                        ("high", pl.col("rank_" + factor) >= 0.75),
                    ):
                        variants.append((factor + "__" + label, eligible, condition))
                combo_ok = pl.col("combo_score").is_finite() & (pl.col("combo_population") >= 4)
                volume_ok = (
                    pl.col("rank_volume_vs_prev").is_finite()
                    & (pl.col("population_volume_vs_prev") >= 4)
                )
                sell_ok = (
                    pl.col("last_imbalance").is_finite()
                    & (pl.col("population_sell_expansion") >= 4)
                    & pl.col("last_unmatched_sell_shares").is_finite()
                    & pl.col("c0924_unmatched_sell_shares").is_finite()
                    & (pl.col("last_age_ms") <= 30000)
                    & (pl.col("c0924_age_ms") <= 30000)
                )
                variants.extend([
                    ("B1_combo_coverage_baseline", combo_ok, pl.lit(True)),
                    ("B2_buy_not_crowded", combo_ok, pl.col("combo_rank") >= 0.75),
                    ("B3_volume_risk", volume_ok, pl.col("rank_volume_vs_prev") >= 0.9),
                    ("B3_sell_expansion", sell_ok,
                     (pl.col("last_unmatched_sell_shares") > pl.col("c0924_unmatched_sell_shares"))
                     & (pl.col("last_imbalance") < 0)),
                ])
                if horizon == 3:
                    tail_ok = (
                        pl.col("tail_strength_score").is_finite()
                        & (
                            pl.col("tail_strength_population")
                            >= TAIL_STRENGTH_RULE["minimum_population"]
                        )
                        & (
                            pl.col("population_volume_vs_prev")
                            >= TAIL_STRENGTH_RULE["minimum_population"]
                        )
                    )
                    variants.append((
                        TAIL_STRENGTH_RULE["id"], tail_ok,
                        pl.col("tail_strength_signal"),
                    ))
                    mode2b_ok = (
                        pl.col("rank_last_minute_matched_growth").is_finite()
                        & pl.col("rank_volume_vs_prev").is_finite()
                        & (
                            pl.col("population_last_minute_matched_growth")
                            >= MODE2B_RULE["minimum_population"]
                        )
                        & (
                            pl.col("population_volume_vs_prev")
                            >= MODE2B_RULE["minimum_population"]
                        )
                    )
                    variants.append((
                        MODE2B_RULE["id"], mode2b_ok,
                        (
                            pl.col("rank_last_minute_matched_growth")
                            >= MODE2B_RULE["last_minute_matched_growth_rank_min"]
                        )
                        & (
                            pl.col("rank_volume_vs_prev")
                            < MODE2B_RULE["volume_vs_prev_rank_max_exclusive"]
                        ),
                    ))
                for variant, eligible, condition in variants:
                    selected = (
                        attach_baseline(sub, eligible=eligible).filter(condition)
                        if not sub.is_empty() else sub
                    )
                    signal_n = signal_scope.filter(
                        eligible & condition & pl.col("signal_eligible"),
                    ).height
                    entry_ok_n = signal_scope.filter(
                        eligible & condition & (pl.col("entry_reason") == "ok"),
                    ).height
                    resolved_entry_n = sub.filter(
                        eligible & condition & (pl.col("entry_reason") == "ok"),
                    ).height
                    row = {
                        "period": period, "horizon": horizon, "gap_bucket": bucket,
                        "variant": variant,
                        "signal_n": signal_n,
                        "entry_ok_n": entry_ok_n,
                        "period_boundary_censored_n": max(0, entry_ok_n - resolved_entry_n),
                        **summarize(selected, bootstrap_samples=bootstrap_samples, seed=seed),
                        "yearly": [],
                    }
                    for year in sorted(selected["date"].dt.year().unique().to_list()):
                        row["yearly"].append({
                            "year": year,
                            **summarize(
                                selected.filter(pl.col("date").dt.year() == year),
                                bootstrap_samples=0, seed=seed,
                            ),
                        })
                    rows.append(row)
    return {
        "version": VERSION, "bootstrap_unit": "event_date",
        "bootstrap_samples": bootstrap_samples, "seed": seed,
        "selection": "Fixed weights and bins; no automatic best-variant selection",
        "frozen_candidates": [TAIL_STRENGTH_RULE, MODE2B_RULE],
        "weights": {
            "tail_strength_score": "equal mean of percentile ranks for "
            "tail_price_change, last_minute_matched_growth and last_imbalance",
            "tail_crowding_filter": "rank_volume_vs_prev < 0.75",
            "legacy_combo": {
                "last_imbalance": 0.5,
                "post0920_matched_growth": -0.25,
                "volume_vs_prev": -0.25,
            },
        },
        "warnings": [
            "Event rows are conditional observations; the separate portfolio block is a "
            "bounded realised-cash allocation check, not a daily mark-to-market backtest.",
            "2025-2026 already informed earlier factor screening; retrospective only.",
            "VWAP is an execution proxy; queue priority and capacity are not modeled.",
            "Unfillable/missing exits remain unresolved; reported returns condition on resolved exits.",
            "Corporate-action intervals excluded; no dividend or split return reconstruction.",
            "8+ is descriptive only. Multiple comparisons are not multiplicity-adjusted.",
            "Date clusters preserve same-day dependence, not serial dependence between dates.",
            "Historical universe and cached D-1 first-board counts are not independently certified.",
            "Session calendar is the independently stored 000001.SH index history; its completeness is assumed.",
            "M2B is post-hoc frozen from the inspected v6 study and is not independent out-of-sample evidence.",
            "TailStrength_v1 ranks within the same date and gap bucket; opening gap itself is not a strength signal.",
            "GEM and STAR boards are excluded; Beijing listings are outside the current source contract.",
        ],
        "coverage": {
            "event_rows": events.height,
            "unique_events": events.select(KEYS).unique().height,
            "main_0_8": {
                "event_rows": main_next.height,
                "unique_events": main_next.select(KEYS).unique().height,
                "signal_candidates": main_next.filter(pl.col("signal_eligible"))
                .select(KEYS).unique().height,
                "entry_executable": main_next.filter(pl.col("entry_reason") == "ok")
                .select(KEYS).unique().height,
                "resolved_next_day": main_next.filter(pl.col("net_return").is_finite())
                .select(KEYS).unique().height,
            },
            "main_2_8": {
                "event_rows": main_next.filter(pl.col("gap_bucket") != "0-2").height,
                "unique_events": main_next.filter(pl.col("gap_bucket") != "0-2")
                .select(KEYS).unique().height,
                "signal_candidates": main_next.filter(
                    (pl.col("gap_bucket") != "0-2") & pl.col("signal_eligible"),
                )
                .select(KEYS).unique().height,
                "entry_executable": main_next.filter(
                    (pl.col("gap_bucket") != "0-2")
                    & (pl.col("entry_reason") == "ok"),
                ).select(KEYS).unique().height,
                "resolved_next_day": main_next.filter(
                    (pl.col("gap_bucket") != "0-2") & pl.col("net_return").is_finite(),
                )
                .select(KEYS).unique().height,
            },
            "entry_reasons": events.filter(pl.col("horizon") == 1)
            .group_by("entry_reason").len().to_dicts(),
            "exit_reasons": events.filter(pl.col("entry_reason") == "ok")
            .group_by("horizon", "exit_reason").len().sort("horizon", "exit_reason").to_dicts(),
            "by_year": events.filter(pl.col("horizon") == 1).group_by(
                pl.col("date").dt.year().alias("year"),
            ).agg(pl.len().alias("n"), (pl.col("entry_reason") == "ok").sum().alias("entry_ok"))
            .sort("year").to_dicts(),
        },
        "results": rows,
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(
        payload, ensure_ascii=False, indent=2, allow_nan=False, default=str,
    ), encoding="utf-8")


def write_summary(path: Path, report: dict) -> None:
    lines = [
        "# Auction tail-strength event study", "",
        f"Algorithm: {VERSION}. Elapsed: {report['elapsed_seconds']} seconds.", "",
        "Entry: D 09:30-09:35 VWAP. Exits: D+1/D+3 09:30-09:35 VWAP.",
        "Returns include the fixed costs in manifest.json. Ranks freeze before continuous trading.",
        "Main sample: 0% <= auction gap < 8%. Opening gap is a bucket, not the strength signal.",
        "GEM and STAR boards are excluded. Delta uses matched date/gap/coverage baselines.", "",
        "| Period | Exit | Variant | Signals | Filled | Censored | Resolved | Mean net | Win rate | Delta | Delta 95% CI |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["results"]:
        if row["gap_bucket"] != "main_0_8" or row["variant"] not in (
            "B0_all", "B1_combo_coverage_baseline",
            TAIL_STRENGTH_RULE["id"],
            MODE2B_RULE["id"],
        ):
            continue
        def pct(value):
            return f"{value * 100:.3f}%" if value is not None else "NA"
        interval = row.get("cluster_bootstrap_95", {}).get("mean_incremental_return")
        ci = " to ".join(map(pct, interval)) if interval else "NA"
        lines.append(
            f"| {row['period']} | D+{row['horizon']} | {row['variant']} | "
            f"{row['signal_n']} | {row['entry_ok_n']} | "
            f"{row['period_boundary_censored_n']} | {row['n']} | "
            f"{pct(row.get('mean_net_return'))} | {pct(row.get('win_rate'))} | "
            f"{pct(row.get('mean_incremental_return'))} | {ci} |",
        )
    lines.extend([
        "", "## Portfolio check", "",
        "TailStrength_v1, D+3, equal 5% targets, max 10 positions, "
        "max 5 entries/day, 50% exposure cap, 1% five-minute participation.", "",
        "| Period | Trades | Total return | Mean trade | Win rate | "
        "Max realised drawdown | Mean exposure |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for period, row in (report.get("portfolio") or {}).items():
        def pct(value):
            return f"{value * 100:.3f}%" if value is not None else "NA"
        lines.append(
            f"| {period} | {row.get('n_trades', 0)} | "
            f"{pct(row.get('total_return'))} | "
            f"{pct(row.get('mean_trade_return'))} | "
            f"{pct(row.get('win_rate'))} | "
            f"{pct(row.get('max_drawdown_realized'))} | "
            f"{pct(row.get('mean_exposure'))} |",
        )
    lines.extend(["", "## Coverage", "", "```json",
                  json.dumps(report["coverage"], indent=2), "```", "", "## Limits", ""])
    lines.extend("- " + warning for warning in report["warnings"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_study(args: argparse.Namespace) -> dict:
    if args.output.exists():
        raise FileExistsError("Use a NEW output directory; existing runs are never overwritten")
    if args.start > args.end or args.bootstrap_samples < 0:
        raise ValueError("Invalid date range or bootstrap count")
    for cost in (args.commission_bps, args.stamp_tax_bps, args.slippage_bps):
        if not np.isfinite(cost) or not 0 <= cost < 1000:
            raise ValueError("Invalid cost in bps")
    started = time.perf_counter()
    args.output.mkdir(parents=True)
    sources, pieces = {}, []
    auction_gaps = {"result": [], "preopen": []}
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    _write_json(args.output / "manifest.json", {
        "status": "running", "version": VERSION, "script_sha256": script_hash,
        "parameters": vars(args), "created_at": datetime.now().isoformat(),
        "execution": "D 09:30-09:35 VWAP to D+1/D+3 09:30-09:35 VWAP; shares/CNY/raw",
        "signal": (
            "Auction result observed before 09:30; TailStrength compares 09:24 "
            "to the final pre-09:25 snapshot within date and gap bucket"
        ),
        "universe": "SH/SZ main board; exclude 300/301/688/689 and BJ",
        "portfolio_defaults": PORTFOLIO_DEFAULTS,
        "costs": "Fixed bilateral commission and slippage; fixed sell stamp tax (not historical schedule)",
    })
    for year in range(args.start.year, args.end.year + 1):
        start, end = max(args.start, date(year, 1, 1)), min(args.end, date(year, 12, 31))
        frame, inputs, gaps = build_year(
            args.data_dir, args.auction_dir, args.minute_dir, start, end,
            commission_bps=args.commission_bps, stamp_tax_bps=args.stamp_tax_bps,
            slippage_bps=args.slippage_bps,
            allow_missing_auction=args.allow_missing_auction_days,
        )
        for name in auction_gaps:
            auction_gaps[name].extend(gaps[name])
        for key, signature in inputs.items():
            if key in sources and sources[key] != signature:
                raise RuntimeError(f"Input changed during study: {key}")
        sources.update(inputs)
        frame.write_parquet(args.output / f"events_{year}.parquet", compression="zstd")
        pieces.append(frame)
        print(json.dumps({
            "event": "year_complete", "year": year, "rows": frame.height,
            "elapsed_seconds": round(time.perf_counter() - started, 2),
        }), flush=True)
    events = pl.concat(pieces, how="diagonal_relaxed")
    events.write_parquet(args.output / "events.parquet", compression="zstd")
    report = build_report(events, bootstrap_samples=args.bootstrap_samples, seed=args.seed)
    portfolio: dict[str, dict] = {}
    selected_rows: list[dict] = []
    curve_rows: list[dict] = []
    for period, period_start, period_end in PERIODS:
        summary, selected, curve = simulate_tail_portfolio(
            events,
            start=period_start,
            end=min(period_end, args.end),
        )
        portfolio[period] = summary
        selected_rows.extend({"period": period, **row} for row in selected)
        curve_rows.extend({"period": period, **row} for row in curve)
    report["portfolio"] = portfolio
    report["coverage"]["auction_gaps"] = auction_gaps
    report["elapsed_seconds"] = round(time.perf_counter() - started, 2)
    report["parameters"] = vars(args)
    report["source_auction_dates"] = sorted({
        Path(p).parent.name[5:] for p in sources if "/result/" in p.replace("\\", "/")
    })
    for key, signature in sources.items():
        stat = Path(key).stat()
        if [stat.st_size, stat.st_mtime_ns] != signature:
            raise RuntimeError(f"Input changed during study: {key}")
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != script_hash:
        raise RuntimeError("Study source changed during execution")
    _write_json(args.output / "study.json", report)
    write_summary(args.output / "RESULTS.md", report)
    flat = [
        {k: v for k, v in row.items() if k not in ("yearly", "cluster_bootstrap_95")}
        for row in report["results"]
    ]
    if flat:
        pl.DataFrame(flat).write_csv(args.output / "results.csv")
    else:
        (args.output / "results.csv").write_text("period,horizon,variant,n\n", encoding="utf-8")
    if selected_rows:
        pl.DataFrame(selected_rows, infer_schema_length=None).write_csv(
            args.output / "portfolio_trades.csv",
        )
    else:
        (args.output / "portfolio_trades.csv").write_text(
            "period,symbol,date\n",
            encoding="utf-8",
        )
    if curve_rows:
        pl.DataFrame(curve_rows).write_csv(args.output / "portfolio_equity.csv")
    else:
        (args.output / "portfolio_equity.csv").write_text(
            "period,date,equity_cost_basis\n",
            encoding="utf-8",
        )
    _write_json(args.output / "sources.json", sources)
    manifest_path = args.output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _write_json(manifest_path, {
        **manifest, "status": "complete", "elapsed_seconds": report["elapsed_seconds"],
        "inputs_unchanged": True, "source_unchanged": True,
    })
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data-dir", "auction-dir", "minute-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2020, 1, 2))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2024, 12, 31))
    parser.add_argument("--commission-bps", type=float, default=3)
    parser.add_argument("--stamp-tax-bps", type=float, default=10)
    parser.add_argument("--slippage-bps", type=float, default=5)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261031)
    parser.add_argument("--allow-missing-auction-days", action="store_true")
    args = parser.parse_args()
    result = run_study(args)
    print(json.dumps({
        "event": "complete", "elapsed_seconds": result["elapsed_seconds"],
        "coverage": result["coverage"],
    }), flush=True)


if __name__ == "__main__":
    main()
