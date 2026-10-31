"""Pre-registered risk-budget and market-exposure study.

Signal selection is frozen at the D+5 expected-return primary shortlist.
Only position sizing and market-state exposure are changed.
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

from scripts.auction_d_day_veto_study import _zero_portfolio_summary, flatten_csv_row
from scripts.auction_high_open_study import _write_json, main_board_symbol, summarize
from scripts.auction_holding_period_risk_study import (
    MAX_POSITION_PCT,
    MIN_POSITION_PCT,
    RISK_BUDGET_PER_TRADE,
    RISK_SIGMA_MULTIPLIER,
    add_risk_budget_size,
    simulate_daily_mark_with_position_column,
)
from scripts.auction_portfolio_construction_study import (
    PORTFOLIO_DEFAULTS,
    _with_baseline,
    load_calendar,
    load_daily_closes,
)
from scripts.auction_walkforward_study import FOLDS, chain_portfolio_curves

VERSION = "auction-risk-budget-exposure-v1"
KEYS = ["symbol", "date"]
BASE_VARIANT = "always_full"
PRIMARY_VARIANT = "regime_scaled"
VARIANTS = (
    BASE_VARIANT,
    "cash_gate",
    "regime_scaled",
    "vol_risk_budget",
    "regime_vol_budget",
)
REGIME_MULTIPLIERS = {
    "risk_on": 1.0,
    "mixed": 0.5,
    "risk_off": 0.0,
}
DECISION_GATE = {
    "primary_variant": PRIMARY_VARIANT,
    "minimum_signal_events": 500,
    "minimum_filled_events": 500,
    "incremental_ci_lower_positive": True,
    "portfolio_total_return_positive": True,
    "portfolio_max_drawdown_floor": -0.15,
    "no_stale_marks": True,
}


def load_base(selected_path: Path) -> pl.DataFrame:
    selected = (
        pl.read_parquet(selected_path)
        .filter(pl.col("variant") == "expected_return_top_50")
        .drop("variant")
    )
    if selected.is_empty():
        raise ValueError("No expected_return_top_50 events for allocation study")
    if selected.select(pl.struct(KEYS).is_duplicated().any()).item():
        raise ValueError("Duplicate expected-return event keys")
    required = {"trend_gate", "vol_gate", "fold", "_selection_order"}
    missing = required.difference(selected.columns)
    if missing:
        raise ValueError(f"Missing allocation-study columns: {sorted(missing)}")
    return selected.sort(["fold", "_selection_order"])


def load_event_panel(events_path: Path, d5_outcomes_path: Path) -> pl.DataFrame:
    events = pl.read_parquet(
        events_path,
        columns=[
            "symbol",
            "date",
            "gap_bucket",
            "horizon",
            "signal_eligible",
        ],
    ).filter(
        (pl.col("horizon") == 3)
        & pl.col("gap_bucket").is_in(["2-4", "4-6", "6-8"])
        & pl.col("signal_eligible"),
        main_board_symbol(),
    )
    d5 = pl.read_parquet(
        d5_outcomes_path,
        columns=[
            "symbol",
            "date",
            "entry_reason",
            "exit_reason",
            "exit_date",
            "net_return",
            "horizon",
        ],
    ).filter(pl.col("horizon") == 5).drop("horizon")
    panel = events.join(d5, on=KEYS, how="left")
    if panel.select(pl.struct(KEYS).is_duplicated().any()).item():
        raise ValueError("Duplicate D+5 event keys for allocation study")
    return panel


def add_market_regime(frame: pl.DataFrame) -> pl.DataFrame:
    regime = (
        pl.when(pl.col("trend_gate") & pl.col("vol_gate"))
        .then(pl.lit("risk_on"))
        .when(pl.col("trend_gate") | pl.col("vol_gate"))
        .then(pl.lit("mixed"))
        .otherwise(pl.lit("risk_off"))
    )
    multiplier = (
        pl.when(pl.col("trend_gate") & pl.col("vol_gate"))
        .then(pl.lit(REGIME_MULTIPLIERS["risk_on"]))
        .when(pl.col("trend_gate") | pl.col("vol_gate"))
        .then(pl.lit(REGIME_MULTIPLIERS["mixed"]))
        .otherwise(pl.lit(REGIME_MULTIPLIERS["risk_off"]))
    )
    return frame.with_columns(
        regime.alias("market_regime"),
        multiplier.alias("market_size_multiplier"),
    )


def prepare_portfolio_input(
    frame: pl.DataFrame,
    variant: str,
    *,
    daily_closes: pl.DataFrame,
) -> tuple[pl.DataFrame, int]:
    signal_n = frame.height
    if variant == BASE_VARIANT:
        return frame.with_columns(
            pl.lit(PORTFOLIO_DEFAULTS["position_pct"]).alias("position_pct"),
        ), signal_n
    if variant == "cash_gate":
        return (
            frame.filter(pl.col("trend_gate") & pl.col("vol_gate"))
            .with_columns(
                pl.lit(PORTFOLIO_DEFAULTS["position_pct"]).alias("position_pct"),
            ),
            signal_n,
        )
    if variant == "vol_risk_budget":
        return add_risk_budget_size(frame, daily_closes), signal_n
    if variant == "regime_scaled":
        scaled = (
            add_market_regime(frame)
            .with_columns(
                (
                    PORTFOLIO_DEFAULTS["position_pct"]
                    * pl.col("market_size_multiplier")
                ).alias("position_pct"),
            )
            .filter(pl.col("position_pct") > 0)
        )
        return scaled, signal_n
    if variant == "regime_vol_budget":
        sized = add_risk_budget_size(frame, daily_closes)
        scaled = (
            add_market_regime(sized)
            .with_columns(
                (
                    pl.col("position_pct")
                    * pl.col("market_size_multiplier")
                ).alias("position_pct"),
            )
            .filter(pl.col("position_pct") > 0)
        )
        return scaled, signal_n
    raise ValueError(f"Unknown allocation variant: {variant}")


def event_results(
    panel: pl.DataFrame,
    base: pl.DataFrame,
    *,
    bootstrap_samples: int,
    seed: int,
) -> list[dict]:
    oos = panel.filter(
        pl.col("date").is_between(FOLDS[0]["test_start"], FOLDS[-1]["test_end"]),
    )
    baseline = _with_baseline(oos)
    selections = {
        BASE_VARIANT: base,
        "cash_gate": base.filter(pl.col("trend_gate") & pl.col("vol_gate")),
        "regime_scaled": base,
        "vol_risk_budget": base,
        "regime_vol_budget": base,
    }
    return [
        {
            "variant": variant,
            "selected_n": selected.height,
            **summarize(
                baseline.join(selected.select(KEYS), on=KEYS, how="semi"),
                bootstrap_samples=bootstrap_samples,
                seed=seed,
            ),
        }
        for variant, selected in selections.items()
    ]


def portfolio_results(
    base: pl.DataFrame,
    *,
    calendar: list[date],
    daily_closes: pl.DataFrame,
) -> tuple[dict[str, dict[str, dict]], dict[str, list[dict]], dict[str, list[dict]]]:
    portfolio: dict[str, dict[str, dict]] = {}
    trades: dict[str, list[dict]] = {}
    curves: dict[str, list[dict]] = {}
    for variant in VARIANTS:
        fold_portfolios = []
        trades[variant] = []
        curves[variant] = []
        portfolio[variant] = {}
        for fold in FOLDS:
            fold_frame = base.filter(pl.col("fold") == fold["name"])
            selected, signal_n = prepare_portfolio_input(
                fold_frame,
                variant,
                daily_closes=daily_closes,
            )
            if selected.is_empty():
                summary = _zero_portfolio_summary()
                filled = []
                curve = []
            else:
                summary, filled, curve = simulate_daily_mark_with_position_column(
                    selected,
                    calendar=calendar,
                    daily_closes=daily_closes,
                    start=fold["test_start"],
                    end=fold["test_end"],
                )
            summary["signal_n"] = signal_n
            summary["funded_candidate_n"] = selected.height
            summary["capital_turnover"] = (
                sum(row["allocated"] for row in filled)
                / PORTFOLIO_DEFAULTS["initial_capital"]
            )
            summary["mean_position_pct"] = (
                float(np.mean([row["position_pct"] for row in filled]))
                if filled
                else None
            )
            portfolio[variant][fold["name"]] = summary
            trades[variant].extend({"fold": fold["name"], **row} for row in filled)
            curves[variant].extend({"fold": fold["name"], **row} for row in curve)
            fold_portfolios.append({
                "name": fold["name"],
                "portfolio": summary,
                "curve": curve,
            })
        chained = chain_portfolio_curves(fold_portfolios)
        all_exposures = [
            row["exposure"]
            for fold in fold_portfolios
            for row in fold["curve"]
        ]
        chained["signal_n"] = sum(
            portfolio[variant][fold["name"]]["signal_n"]
            for fold in FOLDS
        )
        chained["funded_candidate_n"] = sum(
            portfolio[variant][fold["name"]]["funded_candidate_n"]
            for fold in FOLDS
        )
        chained["capital_turnover"] = sum(
            portfolio[variant][fold["name"]]["capital_turnover"]
            for fold in FOLDS
        )
        chained["mean_exposure"] = (
            float(np.mean(all_exposures)) if all_exposures else None
        )
        chained["mean_position_pct"] = float(np.mean([
            portfolio[variant][fold["name"]]["mean_position_pct"]
            for fold in FOLDS
            if portfolio[variant][fold["name"]]["mean_position_pct"] is not None
        ])) if any(
            portfolio[variant][fold["name"]]["mean_position_pct"] is not None
            for fold in FOLDS
        ) else None
        portfolio[variant]["oos"] = chained
    return portfolio, trades, curves


def decision_gate(
    events: list[dict],
    portfolio: dict[str, dict[str, dict]],
) -> dict:
    event = next(row for row in events if row["variant"] == PRIMARY_VARIANT)
    interval = (event.get("cluster_bootstrap_95") or {}).get(
        "mean_incremental_return",
    )
    result = portfolio[PRIMARY_VARIANT]["oos"]
    checks = {
        "minimum_signal_events": (
            event["selected_n"] >= DECISION_GATE["minimum_signal_events"]
        ),
        "minimum_filled_events": (
            result["filled_n"] >= DECISION_GATE["minimum_filled_events"]
        ),
        "incremental_ci_lower_positive": interval is not None and interval[0] > 0,
        "portfolio_total_return_positive": result["total_return"] > 0,
        "portfolio_max_drawdown_above_floor": (
            result["max_drawdown_mtm"] >= DECISION_GATE["portfolio_max_drawdown_floor"]
        ),
        "no_stale_marks": result["stale_marks"] == 0,
    }
    return {
        "rules": DECISION_GATE,
        "checks": checks,
        "passed": all(checks.values()),
    }


def write_results(path: Path, report: dict) -> None:
    lines = [
        "# Risk-budget and market-exposure study",
        "",
        f"Algorithm: `{VERSION}`.",
        "",
        "Signal selection is frozen. Only position sizing and market exposure change.",
        "",
        "| Variant | Signals | Funded | Filled | Turnover | Portfolio | Max drawdown | Mean exposure |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for variant in VARIANTS:
        row = report["portfolio"][variant]["oos"]
        lines.append(
            f"| {variant} | {row['signal_n']} | {row['funded_candidate_n']} | "
            f"{row['filled_n']} | {row['capital_turnover']:.2f}x | "
            f"{row['total_return'] * 100:.3f}% | "
            f"{row['max_drawdown_mtm'] * 100:.3f}% | "
            f"{row['mean_exposure'] * 100:.3f}% |",
        )
    lines.extend([
        "",
        "| Variant | Signal net | Signal delta | Delta 95% CI |",
        "|---|---:|---:|---:|",
    ])
    for row in report["events"]:
        interval = (row.get("cluster_bootstrap_95") or {}).get(
            "mean_incremental_return",
        )
        interval_text = (
            f"{interval[0] * 100:.3f}% to {interval[1] * 100:.3f}%"
            if interval else "NA"
        )
        lines.append(
            f"| {row['variant']} | {row['mean_net_return'] * 100:.3f}% | "
            f"{row['mean_incremental_return'] * 100:.3f}% | {interval_text} |",
        )
    lines.extend([
        "",
        f"Primary variant: `{PRIMARY_VARIANT}`.",
        "",
        f"Gate passed: `{report['decision_gate']['passed']}`.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_study(args: argparse.Namespace) -> dict:
    if args.output.exists():
        raise FileExistsError("Use a NEW output directory; existing runs are never overwritten")
    if args.bootstrap_samples < 0:
        raise ValueError("bootstrap_samples must be non-negative")
    started = time.perf_counter()
    base = load_base(args.selected)
    panel = load_event_panel(
        args.events,
        args.d5_outcomes,
    )
    start_date = base["date"].min()
    end_date = base["exit_date"].max()
    calendar = load_calendar(args.data_dir, start_date, end_date)
    daily_closes = load_daily_closes(
        args.data_dir,
        sorted(set(base["symbol"].to_list())),
        start_date - timedelta(days=45),
        end_date,
    )
    events = event_results(
        panel,
        base,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    portfolio, trades, curves = portfolio_results(
        base,
        calendar=calendar,
        daily_closes=daily_closes,
    )
    gate = decision_gate(events, portfolio)
    elapsed = round(time.perf_counter() - started, 3)
    report = {
        "version": VERSION,
        "base_variant": BASE_VARIANT,
        "primary_variant": PRIMARY_VARIANT,
        "variants": VARIANTS,
        "regime_multipliers": REGIME_MULTIPLIERS,
        "risk_budget": {
            "per_trade": RISK_BUDGET_PER_TRADE,
            "sigma_multiplier": RISK_SIGMA_MULTIPLIER,
            "minimum_position_pct": MIN_POSITION_PCT,
            "maximum_position_pct": MAX_POSITION_PCT,
        },
        "decision_gate": gate,
        "events": events,
        "portfolio": portfolio,
        "portfolio_defaults": PORTFOLIO_DEFAULTS,
        "elapsed_seconds": elapsed,
        "warnings": [
            "Signal selection and D+5 outcomes are frozen.",
            "Market exposure uses the already-defined D-1 trend and volatility gates.",
            "The stock risk budget uses only D-1 20-day completed volatility.",
            "No multiplier or risk-budget parameter was tuned on validation results.",
            "This remains quasi-out-of-sample because the historical period was previously observed.",
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

    pl.DataFrame(
        [flatten_csv_row(row) for row in events],
        infer_schema_length=None,
    ).write_csv(args.output / "events.csv")
    portfolio_rows = [
        flatten_csv_row({"variant": variant, "fold": fold, **row})
        for variant, folds in portfolio.items()
        for fold, row in folds.items()
    ]
    pl.DataFrame(portfolio_rows, infer_schema_length=None).write_csv(
        args.output / "portfolio.csv",
    )
    trade_rows = [
        flatten_csv_row({"variant": variant, **row})
        for variant, rows in trades.items()
        for row in rows
    ]
    pl.DataFrame(trade_rows, infer_schema_length=None).write_csv(
        args.output / "trades.csv",
    )
    curve_rows = [
        flatten_csv_row({"variant": variant, **row})
        for variant, rows in curves.items()
        for row in rows
    ]
    pl.DataFrame(curve_rows, infer_schema_length=None).write_csv(
        args.output / "equity_curve.csv",
    )
    base.write_parquet(
        args.output / "signal_events.parquet",
        compression="zstd",
    )
    write_results(args.output / "RESULTS.md", report)
    _write_json(args.output / "manifest.json", {
        "status": "complete",
        "version": VERSION,
        "script_sha256": script_hash,
        "parameters": vars(args),
        "created_at": datetime.now().isoformat(),
        "elapsed_seconds": elapsed,
    })
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--d5-outcomes", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args()
    report = run_study(args)
    result = report["portfolio"][report["primary_variant"]]["oos"]
    print(json.dumps({
        "event": "complete",
        "primary": report["primary_variant"],
        "gate_passed": report["decision_gate"]["passed"],
        "portfolio_return": result["total_return"],
        "filled_n": result["filled_n"],
    }), flush=True)


if __name__ == "__main__":
    main()
