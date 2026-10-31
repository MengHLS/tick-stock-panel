"""Pre-registered D+5 holding-period and per-trade risk-budget study.

The 70%-90% score band and 2/2/1 gap-bucket quotas are frozen. This study adds
a D+5 exit outcome and a volatility-scaled position size.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl

from scripts.auction_high_open_study import (
    PERIODS,
    _daily_context,
    _first_bars,
    _write_json,
    evaluate_execution,
    summarize,
)
from scripts.auction_portfolio_construction_study import (
    BUCKET_QUOTAS,
    PORTFOLIO_DEFAULTS,
    _cost_factors,
    _with_baseline,
    load_calendar,
    load_daily_closes,
    select_candidates,
    simulate_daily_mark_portfolio,
)
from scripts.auction_tail_stability_study import (
    VARIANTS as STABILITY_VARIANTS,
)
from scripts.auction_tail_stability_study import (
    add_stability_signals,
    load_events,
)

VERSION = "auction-holding-risk-v1"
FROZEN_STUDY_VERSION = "auction-tail-stability-v1"
FROZEN_SELECTION = "band70_90_quota"
VARIANTS = {
    "d3_fixed": {"horizon": 3, "sizing": "fixed"},
    "d5_fixed": {"horizon": 5, "sizing": "fixed"},
    "d5_risk_budget": {"horizon": 5, "sizing": "risk_budget"},
}
PRIMARY_VARIANT = "d5_fixed"
RISK_BUDGET_PER_TRADE = 0.0025
RISK_SIGMA_MULTIPLIER = 2.0
MIN_POSITION_PCT = 0.01
MAX_POSITION_PCT = 0.05
DECISION_GATE = {
    "periods": ["validation", "retrospective_stress"],
    "selected_incremental_ci_lower_positive": True,
    "portfolio_total_return_positive": True,
    "portfolio_max_drawdown_floor": -0.15,
    "no_stale_marks": True,
}


def load_frozen_threshold(path: Path) -> float:
    study = json.loads((path / "study.json").read_text(encoding="utf-8"))
    if study.get("version") != FROZEN_STUDY_VERSION:
        raise ValueError("Unexpected frozen stability-study version")
    if study.get("decision_gate", {}).get("primary_variant") != FROZEN_SELECTION:
        raise ValueError("Frozen score-band selection mismatch")
    return float(study["vol_threshold"])


def prepare_scored_events(path: Path, vol_threshold: float) -> pl.DataFrame:
    events = load_events(path).with_columns(
        pl.lit(None, dtype=pl.Float64).alias("market_vol_20d"),
    )
    return add_stability_signals(events, vol_threshold=vol_threshold)


def _drop_exit_fields(frame: pl.DataFrame) -> pl.DataFrame:
    drop = [
        column for column in frame.columns
        if column.startswith("exit_")
        or column in {"entry_reason", "gross_return", "net_return", "horizon"}
    ]
    return frame.drop(drop)


def build_d5_outcomes(
    source_events: Path,
    keys: pl.DataFrame,
    *,
    data_dir: Path,
    minute_dir: Path,
    commission_bps: float,
    stamp_tax_bps: float,
    slippage_bps: float,
) -> tuple[pl.DataFrame, dict]:
    start = keys["date"].min()
    end = keys["date"].max()
    daily, sources, sessions = _daily_context(data_dir, start, end)
    session_map = pl.DataFrame({"date": sessions}).with_columns(
        pl.col("date").shift(-5).alias("exit_date"),
    )
    source = (
        pl.scan_parquet(source_events)
        .filter(pl.col("horizon") == 3)
        .join(keys.lazy(), on=["symbol", "date"], how="semi")
        .collect()
    )
    source = _drop_exit_fields(source).join(session_map, on="date", how="left")
    exit_daily = daily.select(
        "symbol",
        pl.col("date").alias("exit_date"),
        pl.col("scale").alias("exit_scale"),
        pl.col("open").alias("exit_daily_open"),
        pl.col("volume").alias("exit_daily_volume"),
        pl.col("prev_date").alias("exit_prev_date"),
        pl.col("expected_prev_date").alias("exit_expected_prev_date"),
        pl.col("limit_down").alias("exit_limit_down"),
        pl.col("st_flag").is_not_null().alias("exit_st_known"),
        pl.col("close").alias("exit_daily_close"),
    )
    needed = source.select(
        "symbol",
        pl.col("exit_date").alias("date"),
    ).drop_nulls().unique()
    bars, bar_sources = _first_bars(minute_dir, needed)
    sources.update(bar_sources)
    bars = bars.rename({
        "date": "exit_date",
        **{
            column: "exit_" + column
            for column in bars.columns
            if column not in {"symbol", "date"}
        },
    })
    events = source.join(exit_daily, on=["symbol", "exit_date"], how="left").join(
        bars,
        on=["symbol", "exit_date"],
        how="left",
    )
    events = evaluate_execution(
        events,
        commission_bps=commission_bps,
        stamp_tax_bps=stamp_tax_bps,
        slippage_bps=slippage_bps,
    ).with_columns(pl.lit(5).alias("horizon"))
    return events.select(
        "symbol",
        "date",
        "entry_reason",
        "exit_reason",
        "exit_date",
        "gross_return",
        "net_return",
        "horizon",
    ), sources


def attach_d5_outcomes(
    scored: pl.DataFrame,
    d5: pl.DataFrame,
) -> pl.DataFrame:
    base = scored.drop(
        "entry_reason",
        "exit_reason",
        "exit_date",
        "net_return",
    )
    return base.join(d5, on=["symbol", "date"], how="left")


def add_risk_budget_size(
    selected: pl.DataFrame,
    daily_closes: pl.DataFrame,
) -> pl.DataFrame:
    volatility = (
        daily_closes.sort(["symbol", "date"])
        .with_columns(
            (pl.col("close") / pl.col("close").shift(1).over("symbol") - 1)
            .alias("_return"),
        )
        .with_columns(
            pl.col("_return").rolling_std(20).over("symbol").alias("_vol20"),
        )
        .with_columns(
            pl.col("_vol20").shift(1).over("symbol").alias("stock_vol_20d"),
        )
        .select("symbol", "date", "stock_vol_20d")
    )
    selected = selected.join(volatility, on=["symbol", "date"], how="left")
    return selected.with_columns(
        pl.when(
            pl.col("stock_vol_20d").is_not_null()
            & pl.col("stock_vol_20d").is_finite()
            & (pl.col("stock_vol_20d") > 0),
        )
        .then(
            (
                RISK_BUDGET_PER_TRADE
                / (RISK_SIGMA_MULTIPLIER * pl.col("stock_vol_20d"))
            ).clip(MIN_POSITION_PCT, MAX_POSITION_PCT),
        )
        .otherwise(MAX_POSITION_PCT)
        .alias("position_pct"),
    )


def simulate_daily_mark_with_position_column(
    selected: pl.DataFrame,
    *,
    calendar: list[date],
    daily_closes: pl.DataFrame,
    start: date,
    end: date,
    parameters: dict | None = None,
) -> tuple[dict, list[dict], list[dict]]:
    params = {**PORTFOLIO_DEFAULTS, **(parameters or {})}
    buy_factor, sell_factor = _cost_factors(params)
    sessions = [day for day in calendar if start <= day <= end]
    session_set = set(sessions)
    selected_rows = selected.to_dicts()
    for row in selected_rows:
        if row["exit_date"] not in session_set:
            raise ValueError(f"Exit date outside calendar: {row['exit_date']}")
    by_date: dict[date, list[dict]] = {}
    for row in selected_rows:
        by_date.setdefault(row["date"], []).append(row)
    close_map = {
        (row["symbol"], row["date"]): float(row["close"])
        for row in daily_closes.to_dicts()
    }
    cash = float(params["initial_capital"])
    positions: list[dict] = []
    filled: list[dict] = []
    curve: list[dict] = []
    rejected = {"no_slot": 0, "cash": 0, "exposure": 0, "capacity": 0, "minimum": 0}
    stale_marks = 0
    max_positions_used = 0
    for day in sessions:
        remaining = []
        for position in positions:
            if position["exit_date"] == day:
                proceeds = position["allocated"] * (1 + position["net_return"])
                cash += proceeds
                position["realized_return"] = position["net_return"]
                filled.append(position)
            elif position["exit_date"] < day:
                raise AssertionError("Position missed its frozen exit date")
            else:
                remaining.append(position)
        positions = remaining
        marked_before = sum(position["mark_value"] for position in positions)
        equity_before = cash + marked_before
        for row in by_date.get(day, []):
            if len(positions) >= params["max_positions"]:
                rejected["no_slot"] += 1
                continue
            capacity = row["entry_vwap"] * row["entry_volume"] * params["capacity_pct"]
            if not np.isfinite(capacity) or capacity <= params["minimum_notional"]:
                rejected["capacity"] += 1
                continue
            exposure_room = max(
                0.0,
                equity_before * params["max_exposure_pct"] - marked_before,
            )
            position_pct = row.get("position_pct", params["position_pct"])
            if not np.isfinite(position_pct) or position_pct <= 0:
                position_pct = params["position_pct"]
            target = equity_before * min(position_pct, MAX_POSITION_PCT)
            allocation = min(target, capacity, cash, exposure_room)
            if allocation <= 0:
                rejected["exposure"] += 1
                continue
            if allocation < params["minimum_notional"]:
                rejected["cash" if cash < params["minimum_notional"] else "minimum"] += 1
                continue
            shares = allocation / (row["entry_vwap"] * buy_factor)
            cash -= allocation
            mark_value = shares * row["entry_vwap"] * sell_factor
            positions.append({
                **row,
                "allocated": allocation,
                "shares": shares,
                "mark_value": mark_value,
            })
            marked_before += mark_value
            equity_before = cash + marked_before
        marked_after = 0.0
        for position in positions:
            close = close_map.get((position["symbol"], day))
            if close is None or not np.isfinite(close) or close <= 0:
                stale_marks += 1
            else:
                position["mark_value"] = position["shares"] * close * sell_factor
            marked_after += position["mark_value"]
        equity = cash + marked_after
        max_positions_used = max(max_positions_used, len(positions))
        curve.append({
            "date": day.isoformat(),
            "cash": round(cash, 2),
            "market_value": round(marked_after, 2),
            "equity": round(equity, 2),
            "open_positions": len(positions),
            "exposure": marked_after / equity if equity > 0 else 0.0,
        })
    if positions:
        raise AssertionError("Portfolio retained open positions past the frozen period")
    equity_values = np.array(
        [params["initial_capital"], *[row["equity"] for row in curve]],
        dtype=float,
    )
    peaks = np.maximum.accumulate(equity_values)
    drawdown = equity_values / peaks - 1
    trade_returns = np.array([row["realized_return"] for row in filled], dtype=float)
    return ({
        "status": "ok" if filled else "no_filled_trades",
        **params,
        "candidate_n": selected.height,
        "filled_n": len(filled),
        "total_return": float(cash / params["initial_capital"] - 1),
        "final_equity": float(cash),
        "mean_trade_return": float(trade_returns.mean()) if trade_returns.size else None,
        "win_rate": float((trade_returns > 0).mean()) if trade_returns.size else None,
        "max_drawdown_mtm": float(drawdown.min()),
        "mean_exposure": float(np.mean([row["exposure"] for row in curve]))
        if curve else None,
        "max_positions_used": max_positions_used,
        "stale_marks": stale_marks,
        "rejected": rejected,
    }, filled, curve)


def decision_gate(selected_results: list[dict], portfolio: dict) -> dict:
    checks = {}
    for period in DECISION_GATE["periods"]:
        selected = next(
            row for row in selected_results
            if row["period"] == period and row["variant"] == PRIMARY_VARIANT
        )
        interval = (selected.get("cluster_bootstrap_95") or {}).get(
            "mean_incremental_return",
        )
        result = portfolio[PRIMARY_VARIANT][period]
        checks[period] = {
            "selected_incremental_ci_lower_positive": (
                interval is not None and interval[0] > 0
            ),
            "portfolio_total_return_positive": (
                result.get("total_return") is not None
                and result["total_return"] > 0
            ),
            "portfolio_max_drawdown_above_floor": (
                result.get("max_drawdown_mtm") is not None
                and result["max_drawdown_mtm"]
                >= DECISION_GATE["portfolio_max_drawdown_floor"]
            ),
            "no_stale_marks": result.get("stale_marks", 1) == 0,
        }
        checks[period]["passed"] = all(checks[period].values())
    return {
        "primary_variant": PRIMARY_VARIANT,
        "rules": DECISION_GATE,
        "periods": checks,
        "passed": all(row["passed"] for row in checks.values()),
    }


def write_results(path: Path, report: dict) -> None:
    lines = [
        "# Auction D+5 holding and risk-budget study",
        "",
        f"Algorithm: `{VERSION}`.",
        "",
        "| Period | Variant | Selected | Net | Delta | Delta 95% CI |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in report["selected_results"]:
        interval = (row.get("cluster_bootstrap_95") or {}).get(
            "mean_incremental_return",
        )
        interval_text = (
            f"{interval[0] * 100:.3f}% to {interval[1] * 100:.3f}%"
            if interval else "NA"
        )
        lines.append(
            f"| {row['period']} | {row['variant']} | {row['n']} | "
            f"{row['mean_net_return'] * 100:.3f}% | "
            f"{row['mean_incremental_return'] * 100:.3f}% | {interval_text} |",
        )
    lines.extend([
        "",
        "| Period | Variant | Filled | Turnover | Total | Max drawdown |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for variant, periods in report["portfolio"].items():
        for period, row in periods.items():
            lines.append(
                f"| {period} | {variant} | {row['filled_n']} | "
                f"{row['capital_turnover']:.2f}x | "
                f"{row['total_return'] * 100:.3f}% | "
                f"{row['max_drawdown_mtm'] * 100:.3f}% |",
            )
    lines.extend([
        "",
        f"Primary variant: `{report['decision_gate']['primary_variant']}`.",
        "",
        f"Passed: `{report['decision_gate']['passed']}`.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_study(args: argparse.Namespace) -> dict:
    if args.output.exists():
        raise FileExistsError("Use a NEW output directory; existing runs are never overwritten")
    if args.bootstrap_samples < 0:
        raise ValueError("bootstrap_samples must be non-negative")
    started = time.perf_counter()
    vol_threshold = load_frozen_threshold(args.frozen_study)
    scored = prepare_scored_events(args.events, vol_threshold)
    keys = scored.select("symbol", "date").unique()
    d5, sources = build_d5_outcomes(
        args.source_events,
        keys,
        data_dir=args.data_dir,
        minute_dir=args.minute_dir,
        commission_bps=PORTFOLIO_DEFAULTS["commission_bps"],
        stamp_tax_bps=PORTFOLIO_DEFAULTS["stamp_tax_bps"],
        slippage_bps=PORTFOLIO_DEFAULTS["slippage_bps"],
    )
    scored_d3 = scored
    scored_d5 = attach_d5_outcomes(scored, d5)
    selection_frame = {3: scored_d3, 5: scored_d5}
    contract = STABILITY_VARIANTS[FROZEN_SELECTION]
    selections: dict[str, dict[str, tuple[pl.DataFrame, int]]] = {}
    for period, start, end in PERIODS[:4]:
        selections[period] = {}
        for variant, spec in VARIANTS.items():
            frame = selection_frame[spec["horizon"]].filter(
                pl.col("date").is_between(start, end),
            )
            selected, candidate_n = select_candidates(
                frame,
                start=start,
                end=end,
                contract=contract,
                max_new_per_day=PORTFOLIO_DEFAULTS["max_new_per_day"],
            )
            selections[period][variant] = (selected, candidate_n)
    selected_results = []
    for period, start, end in PERIODS[:4]:
        for variant, spec in VARIANTS.items():
            frame = selection_frame[spec["horizon"]].filter(
                pl.col("date").is_between(start, end),
            )
            baseline = _with_baseline(frame)
            selected, candidate_n = selections[period][variant]
            exact = baseline.join(
                selected.select("symbol", "date"),
                on=["symbol", "date"],
                how="semi",
            )
            selected_results.append({
                "period": period,
                "variant": variant,
                "candidate_n": candidate_n,
                "selected_n": selected.height,
                **summarize(
                    exact,
                    bootstrap_samples=args.bootstrap_samples,
                    seed=args.seed,
                ),
            })
    selected_for_closes = pl.concat([
        selected.select("symbol", "date", "exit_date")
        for period_rows in selections.values()
        for selected, _ in period_rows.values()
    ])
    symbols = sorted(set(selected_for_closes["symbol"].to_list()))
    start_date = selected_for_closes["date"].min()
    end_date = selected_for_closes["exit_date"].max()
    calendar = load_calendar(args.data_dir, start_date, end_date)
    daily_closes = load_daily_closes(
        args.data_dir,
        symbols,
        start_date - timedelta(days=45),
        end_date,
    )
    portfolio: dict[str, dict] = {}
    trades = []
    curves = []
    for period, start, end in PERIODS[:4]:
        for variant, spec in VARIANTS.items():
            selected, _ = selections[period][variant]
            if spec["sizing"] == "risk_budget":
                selected = add_risk_budget_size(selected, daily_closes)
                summary, filled, curve = simulate_daily_mark_with_position_column(
                    selected,
                    calendar=calendar,
                    daily_closes=daily_closes,
                    start=start,
                    end=end,
                )
            else:
                summary, filled, curve = simulate_daily_mark_portfolio(
                    selected,
                    calendar=calendar,
                    daily_closes=daily_closes,
                    start=start,
                    end=end,
                )
            summary["capital_turnover"] = (
                sum(row["allocated"] for row in filled)
                / PORTFOLIO_DEFAULTS["initial_capital"]
            )
            portfolio.setdefault(variant, {})[period] = summary
            trades.extend({"period": period, "variant": variant, **row} for row in filled)
            curves.extend({"period": period, "variant": variant, **row} for row in curve)
    report = {
        "version": VERSION,
        "frozen_study_version": FROZEN_STUDY_VERSION,
        "frozen_selection": FROZEN_SELECTION,
        "risk_budget": {
            "per_trade": RISK_BUDGET_PER_TRADE,
            "sigma_multiplier": RISK_SIGMA_MULTIPLIER,
            "minimum_position_pct": MIN_POSITION_PCT,
            "maximum_position_pct": MAX_POSITION_PCT,
        },
        "bucket_quotas": BUCKET_QUOTAS,
        "portfolio_defaults": PORTFOLIO_DEFAULTS,
        "decision_gate": decision_gate(selected_results, portfolio),
        "selected_results": selected_results,
        "portfolio": portfolio,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "warnings": [
            "The score band, gap quotas and factor definitions are frozen.",
            "D+5 exits use the same exact 09:30-09:35 VWAP protocol.",
            "Risk-budget sizing uses only D-1 20-day stock volatility.",
            "Validation and stress results do not alter holding period or risk budget.",
        ],
    }
    args.output.mkdir(parents=True)
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    _write_json(args.output / "manifest.json", {
        "status": "running",
        "version": VERSION,
        "script_sha256": script_hash,
        "parameters": vars(args),
        "created_at": datetime.now().isoformat(),
    })
    _write_json(args.output / "study.json", report)
    flat_selected = [
        {
            "period": row["period"],
            "variant": row["variant"],
            "candidate_n": row["candidate_n"],
            "selected_n": row["selected_n"],
            **{
                key: (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                )
                for key, value in row.items()
                if key not in {"period", "variant", "candidate_n", "selected_n"}
            },
        }
        for row in selected_results
    ]
    pl.DataFrame(flat_selected, infer_schema_length=None).write_csv(
        args.output / "selected_results.csv",
    )
    flat_portfolio = [
        {
            "variant": variant,
            "period": period,
            **{
                key: (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                )
                for key, value in row.items()
            },
        }
        for variant, periods in portfolio.items()
        for period, row in periods.items()
    ]
    pl.DataFrame(flat_portfolio, infer_schema_length=None).write_csv(
        args.output / "portfolio.csv",
    )
    pl.DataFrame(trades, infer_schema_length=None).write_csv(args.output / "trades.csv")
    pl.DataFrame(curves, infer_schema_length=None).write_csv(args.output / "equity_curve.csv")
    d5.write_parquet(args.output / "d5_outcomes.parquet", compression="zstd")
    _write_json(args.output / "sources.json", sources)
    write_results(args.output / "RESULTS.md", report)
    _write_json(args.output / "manifest.json", {
        "status": "complete",
        "version": VERSION,
        "script_sha256": script_hash,
        "parameters": vars(args),
        "created_at": datetime.now().isoformat(),
        "elapsed_seconds": report["elapsed_seconds"],
    })
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--source-events", type=Path, required=True)
    parser.add_argument("--frozen-study", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--minute-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args()
    report = run_study(args)
    print(json.dumps({
        "event": "complete",
        "gate_passed": report["decision_gate"]["passed"],
        "elapsed_seconds": report["elapsed_seconds"],
    }), flush=True)


if __name__ == "__main__":
    main()
