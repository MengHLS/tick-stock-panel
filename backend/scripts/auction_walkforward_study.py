"""Expanding-window walk-forward validation for the auction D+5 model.

Each fold fits factor admission, directions, correlation clusters and score
bands strictly on earlier data, then evaluates the immediately following year.
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

from scripts.auction_high_open_study import _write_json, main_board_symbol, summarize
from scripts.auction_multifactor_study import (
    SELECTION,
    _correlation,
    add_factor_ranks,
    build_scores,
    factor_metrics,
    load_factor_ids,
)
from scripts.auction_portfolio_construction_study import (
    PORTFOLIO_DEFAULTS,
    _with_baseline,
    load_calendar,
    load_daily_closes,
    select_candidates,
    simulate_daily_mark_portfolio,
)

VERSION = "auction-walkforward-v2"
FOLDS = [
    {
        "name": "test_2022",
        "train_start": date(2020, 1, 2),
        "train_end": date(2021, 12, 31),
        "test_start": date(2022, 1, 1),
        "test_end": date(2022, 12, 31),
    },
    {
        "name": "test_2023",
        "train_start": date(2020, 1, 2),
        "train_end": date(2022, 12, 31),
        "test_start": date(2023, 1, 1),
        "test_end": date(2023, 12, 31),
    },
    {
        "name": "test_2024",
        "train_start": date(2020, 1, 2),
        "train_end": date(2023, 12, 31),
        "test_start": date(2024, 1, 1),
        "test_end": date(2024, 12, 31),
    },
    {
        "name": "test_2025",
        "train_start": date(2020, 1, 2),
        "train_end": date(2024, 12, 31),
        "test_start": date(2025, 1, 1),
        "test_end": date(2025, 12, 31),
    },
    {
        "name": "test_2026",
        "train_start": date(2020, 1, 2),
        "train_end": date(2025, 12, 31),
        "test_start": date(2026, 1, 1),
        "test_end": date(2026, 8, 31),
    },
]
BAND_CANDIDATES = [
    {"name": "70_100", "lower": 0.70, "upper": 1.00},
    {"name": "70_90", "lower": 0.70, "upper": 0.90},
    {"name": "75_90", "lower": 0.75, "upper": 0.90},
]
MIN_CALIBRATION_EVENTS = 100
DECISION_GATE = {
    "walkforward_incremental_ci_lower_positive": True,
    "walkforward_total_return_positive": True,
    "walkforward_max_drawdown_floor": -0.15,
    "no_stale_marks": True,
}


def validate_folds(folds: list[dict] | None = None) -> None:
    folds = FOLDS if folds is None else folds
    if not folds:
        raise ValueError("At least one walk-forward fold is required")
    first_train_start = folds[0]["train_start"]
    previous_end = None
    previous_train_end = None
    for fold in folds:
        if fold["train_start"] > fold["train_end"]:
            raise ValueError("Fold train range is invalid")
        if fold["train_end"] >= fold["test_start"]:
            raise ValueError("Fold test window overlaps training")
        if fold["test_start"] > fold["test_end"]:
            raise ValueError("Fold test range is invalid")
        if fold["test_start"] != fold["train_end"] + timedelta(days=1):
            raise ValueError("Fold test window must immediately follow training")
        if fold["train_start"] != first_train_start:
            raise ValueError("Walk-forward folds must use an expanding training window")
        if previous_end and fold["test_start"] <= previous_end:
            raise ValueError("Test folds overlap")
        if previous_train_end is not None and fold["train_end"] != previous_end:
            raise ValueError("Each fold must extend training through the prior test window")
        previous_end = fold["test_end"]
        previous_train_end = fold["train_end"]


def load_panel(
    events_path: Path,
    factor_admission_path: Path,
    d5_outcomes_path: Path,
) -> tuple[pl.DataFrame, list[str]]:
    factor_ids, _ = load_factor_ids(factor_admission_path)
    factor_columns = [f"factor__{factor_id}" for factor_id in factor_ids]
    selected = [
        "symbol",
        "date",
        "gap_bucket",
        "entry_vwap",
        "entry_volume",
        "tail_strength_signal",
        "tail_strength_rank",
        *factor_columns,
    ]
    events = (
        pl.scan_parquet(events_path)
        .filter(
            (pl.col("horizon") == 3)
            & pl.col("gap_bucket").is_in(["2-4", "4-6", "6-8"])
            & pl.col("signal_eligible"),
            main_board_symbol(),
        )
        .select(selected)
        .collect()
    )
    d5 = pl.read_parquet(d5_outcomes_path).select(
        "symbol",
        "date",
        "entry_reason",
        "exit_reason",
        "exit_date",
        "gross_return",
        "net_return",
        "horizon",
    ).filter(pl.col("horizon") == 5).drop("horizon")
    panel = events.join(d5, on=["symbol", "date"], how="left")
    if panel.select(pl.struct(["symbol", "date"]).is_duplicated().any()).item():
        raise ValueError("Duplicate D+5 panel keys")
    panel = add_factor_ranks(panel, factor_ids).drop(factor_columns)
    return panel, factor_ids


def mature_training_rows(
    panel: pl.DataFrame,
    *,
    train_start: date,
    train_end: date,
) -> pl.DataFrame:
    """Keep only resolved training labels that matured before the test window."""
    return panel.filter(
        pl.col("date").is_between(train_start, train_end)
        & pl.col("exit_date").is_not_null()
        & (pl.col("exit_date") <= train_end)
        & (pl.col("entry_reason") == "ok")
        & (pl.col("exit_reason") == "ok")
        & pl.col("net_return").is_finite(),
    )


def admit_fold_factors(
    panel: pl.DataFrame,
    factor_ids: list[str],
    *,
    train_start: date,
    train_end: date,
) -> list[dict]:
    training = mature_training_rows(
        panel,
        train_start=train_start,
        train_end=train_end,
    )
    admitted = []
    for factor_id in factor_ids:
        metrics = factor_metrics(
            training,
            f"rank__{factor_id}",
            train_start,
            train_end,
        )
        direction = metrics.get("direction")
        yearly_ic = [
            row["mean_ic"] for row in metrics.get("yearly", [])
            if row["mean_ic"] is not None
        ]
        same_sign = (
            len(yearly_ic) >= SELECTION["minimum_dev_years"]
            and all((value > 0) == (direction == "high") for value in yearly_ic)
        )
        factor = {
            "factor_id": factor_id,
            "direction": direction,
            "sign": 1 if direction == "high" else -1 if direction == "low" else 0,
            "metrics": metrics,
            "admitted": (
                metrics["status"] == "ok"
                and metrics["coverage"] >= SELECTION["minimum_coverage"]
                and abs(metrics["mean_ic"] or 0) >= SELECTION["minimum_abs_mean_ic"]
                and abs(metrics["icir"] or 0) >= SELECTION["minimum_abs_icir"]
                and same_sign
            ),
        }
        admitted.append(factor)
    return admitted


def cluster_fold_factors(
    panel: pl.DataFrame,
    factors: list[dict],
    *,
    train_start: date,
    train_end: date,
    seed: int,
) -> list[dict]:
    eligible = [factor for factor in factors if factor["admitted"]]
    if not eligible:
        raise ValueError("No factors passed fold admission")
    sample = panel.filter(
        pl.col("date").is_between(train_start, train_end),
    ).select([f"rank__{factor['factor_id']}" for factor in eligible])
    if sample.height > SELECTION["correlation_sample_rows"]:
        sample = sample.sample(SELECTION["correlation_sample_rows"], seed=seed)
    matrix = sample.to_numpy().astype(float, copy=True)
    for index, factor in enumerate(eligible):
        matrix[:, index] *= factor["sign"]
    order = sorted(
        range(len(eligible)),
        key=lambda index: (
            -abs(eligible[index]["metrics"]["icir"] or 0),
            -abs(eligible[index]["metrics"]["mean_ic"] or 0),
            eligible[index]["factor_id"],
        ),
    )
    representatives: list[dict] = []
    for index in order:
        factor = eligible[index]
        best_cluster = None
        best_corr = SELECTION["correlation_threshold"]
        for cluster_index, representative in enumerate(representatives):
            corr = _correlation(matrix, representative["_matrix_index"], index)
            if corr is not None and corr >= best_corr:
                best_corr = corr
                best_cluster = cluster_index
        if best_cluster is None:
            representatives.append({
                "factor_id": factor["factor_id"],
                "direction": factor["direction"],
                "sign": factor["sign"],
                "metrics": factor["metrics"],
                "members": [factor["factor_id"]],
                "_matrix_index": index,
            })
        else:
            representatives[best_cluster]["members"].append(factor["factor_id"])
    for representative in representatives:
        representative["members"].sort()
        representative.pop("_matrix_index")
    return representatives


def calibrate_band(
    scored: pl.DataFrame,
    *,
    train_start: date,
    train_end: date,
    seed: int,
) -> tuple[dict, list[dict]]:
    training = scored.filter(pl.col("date").is_between(train_start, train_end))
    baseline = _with_baseline(mature_training_rows(
        scored,
        train_start=train_start,
        train_end=train_end,
    ))
    if baseline.is_empty():
        raise ValueError("No matured training labels are available for calibration")
    rows = []
    for index, band in enumerate(BAND_CANDIDATES):
        signal_column = f"_band_candidate_{index}"
        frame = training.with_columns(
            (
                (pl.col("combined_rank") >= band["lower"])
                & (pl.col("combined_rank") < band["upper"])
            ).fill_null(False).alias(signal_column),
        )
        contract = {
            "signal_column": signal_column,
            "score_column": "combined_rank",
            "selection": "bucket_quota",
        }
        selected, candidate_n = select_candidates(
            frame,
            start=train_start,
            end=train_end,
            contract=contract,
            max_new_per_day=PORTFOLIO_DEFAULTS["max_new_per_day"],
        )
        exact = baseline.join(
            selected.select("symbol", "date"),
            on=["symbol", "date"],
            how="semi",
        )
        summary = summarize(exact, bootstrap_samples=200, seed=seed)
        rows.append({
            **band,
            "candidate_n": candidate_n,
            "selected_n": selected.height,
            "mean_net_return": summary.get("mean_net_return"),
            "mean_incremental_return": summary.get("mean_incremental_return"),
            "cluster_bootstrap_95": summary.get("cluster_bootstrap_95"),
        })
    eligible = [row for row in rows if row["selected_n"] >= MIN_CALIBRATION_EVENTS]
    if not eligible:
        raise ValueError("No score band has enough training events")
    chosen = max(
        eligible,
        key=lambda row: (row["mean_incremental_return"] or -1e9, row["selected_n"]),
    )
    return chosen, rows


def add_chosen_band_signal(
    scored: pl.DataFrame,
    band: dict,
) -> pl.DataFrame:
    return scored.with_columns(
        (
            (pl.col("combined_rank") >= band["lower"])
            & (pl.col("combined_rank") < band["upper"])
        ).fill_null(False).alias("_walkforward_signal"),
    )


def chain_portfolio_curves(
    fold_portfolios: list[dict],
) -> dict:
    initial = PORTFOLIO_DEFAULTS["initial_capital"]
    base = 1.0
    values = [initial]
    rows = []
    total_trades = 0
    stale = 0
    for fold in fold_portfolios:
        summary = fold["portfolio"]
        for curve in fold["curve"]:
            values.append(base * curve["equity"])
            rows.append({
                "fold": fold["name"],
                "date": curve["date"],
                "equity": base * curve["equity"],
            })
        base *= 1 + summary["total_return"]
        total_trades += summary["filled_n"]
        stale += summary["stale_marks"]
    equity = np.asarray(values, dtype=float)
    drawdown = equity / np.maximum.accumulate(equity) - 1
    return {
        "total_return": base - 1,
        "filled_n": total_trades,
        "max_drawdown_mtm": float(drawdown.min()),
        "stale_marks": stale,
        "curve": rows,
    }


def write_results(path: Path, report: dict) -> None:
    lines = [
        "# Auction walk-forward study",
        "",
        f"Algorithm: `{VERSION}`.",
        "",
        "| Fold | Test period | Band | Admitted | Reps | Test net | Test delta | Portfolio | Max DD |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for fold in report["folds"]:
        event = fold["event"]
        portfolio = fold["portfolio"]
        lines.append(
            f"| {fold['name']} | {fold['test_start']} to {fold['test_end']} | "
            f"{fold['chosen_band']['name']} | {fold['admitted_factors']} | "
            f"{len(fold['representatives'])} | "
            f"{event['mean_net_return'] * 100:.3f}% | "
            f"{event['mean_incremental_return'] * 100:.3f}% | "
            f"{portfolio['total_return'] * 100:.3f}% | "
            f"{portfolio['max_drawdown_mtm'] * 100:.3f}% |",
        )
    lines.extend([
        "",
        "## Pooled out-of-sample",
        "",
        f"Event delta: `{report['oos_event']['mean_incremental_return'] * 100:.3f}%`.",
        "",
        f"Chained portfolio return: `{report['oos_portfolio']['total_return'] * 100:.3f}%`.",
        "",
        f"Chained max drawdown: `{report['oos_portfolio']['max_drawdown_mtm'] * 100:.3f}%`.",
        "",
        f"Gate passed: `{report['decision_gate']['passed']}`.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_study(args: argparse.Namespace) -> dict:
    if args.output.exists():
        raise FileExistsError("Use a NEW output directory; existing runs are never overwritten")
    validate_folds()
    started = time.perf_counter()
    panel, factor_ids = load_panel(
        args.events,
        args.factor_admission,
        args.d5_outcomes,
    )
    fold_outputs = []
    selected_for_closes = []
    for fold_index, fold in enumerate(FOLDS):
        admitted = admit_fold_factors(
            panel,
            factor_ids,
            train_start=fold["train_start"],
            train_end=fold["train_end"],
        )
        representatives = cluster_fold_factors(
            panel,
            admitted,
            train_start=fold["train_start"],
            train_end=fold["train_end"],
            seed=args.seed + fold_index,
        )
        scored = build_scores(panel, representatives)
        chosen_band, calibration = calibrate_band(
            scored,
            train_start=fold["train_start"],
            train_end=fold["train_end"],
            seed=args.seed + fold_index,
        )
        scored = add_chosen_band_signal(scored, chosen_band)
        contract = {
            "signal_column": "_walkforward_signal",
            "score_column": "combined_rank",
            "selection": "bucket_quota",
        }
        test_frame = scored.filter(
            pl.col("date").is_between(fold["test_start"], fold["test_end"]),
        )
        selected, candidate_n = select_candidates(
            test_frame,
            start=fold["test_start"],
            end=fold["test_end"],
            contract=contract,
            max_new_per_day=PORTFOLIO_DEFAULTS["max_new_per_day"],
        )
        if selected.is_empty():
            raise ValueError(f"{fold['name']} produced no selected events")
        selected_for_closes.append(selected.select("symbol", "date", "exit_date"))
        baseline = _with_baseline(test_frame)
        exact = baseline.join(
            selected.select("symbol", "date"),
            on=["symbol", "date"],
            how="semi",
        )
        event_summary = summarize(
            exact,
            bootstrap_samples=args.bootstrap_samples,
            seed=args.seed + fold_index,
        )
        fold_outputs.append({
            "name": fold["name"],
            "train_start": fold["train_start"],
            "train_end": fold["train_end"],
            "test_start": fold["test_start"],
            "test_end": fold["test_end"],
            "admitted_factors": sum(row["admitted"] for row in admitted),
            "representatives": representatives,
            "band_calibration": calibration,
            "chosen_band": chosen_band,
            "candidate_n": candidate_n,
            "selected_n": selected.height,
            "event": event_summary,
            "selected": selected,
            "test_frame": test_frame,
        })
    all_selected = pl.concat([row["selected"] for row in fold_outputs])
    symbols = sorted(set(all_selected["symbol"].to_list()))
    start_date = all_selected["date"].min()
    end_date = all_selected["exit_date"].max()
    calendar = load_calendar(args.data_dir, start_date, end_date)
    daily_closes = load_daily_closes(args.data_dir, symbols, start_date, end_date)
    oos_event_frames = []
    for fold in fold_outputs:
        summary, filled, curve = simulate_daily_mark_portfolio(
            fold["selected"],
            calendar=calendar,
            daily_closes=daily_closes,
            start=fold["test_start"],
            end=fold["test_end"],
        )
        fold["portfolio"] = summary
        fold["trades"] = filled
        fold["curve"] = curve
        oos_event_frames.append(
            _with_baseline(fold["test_frame"]).join(
                fold["selected"].select("symbol", "date"),
                on=["symbol", "date"],
                how="semi",
            ),
        )
    oos_events = pl.concat(oos_event_frames)
    oos_event = summarize(
        oos_events,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    oos_portfolio = chain_portfolio_curves(fold_outputs)
    decision = {
        "rules": DECISION_GATE,
        "incremental_ci_lower_positive": (
            oos_event["cluster_bootstrap_95"]["mean_incremental_return"][0] > 0
        ),
        "total_return_positive": oos_portfolio["total_return"] > 0,
        "max_drawdown_above_floor": (
            oos_portfolio["max_drawdown_mtm"]
            >= DECISION_GATE["walkforward_max_drawdown_floor"]
        ),
        "no_stale_marks": oos_portfolio["stale_marks"] == 0,
    }
    decision["passed"] = all(
        value for key, value in decision.items() if key != "rules"
    )
    report = {
        "version": VERSION,
        "folds_definition": [
            {
                key: value.isoformat() if isinstance(value, date) else value
                for key, value in fold.items()
            }
            for fold in FOLDS
        ],
        "selection": {
            "band_candidates": BAND_CANDIDATES,
            "minimum_calibration_events": MIN_CALIBRATION_EVENTS,
            "factor_admission": SELECTION,
            "portfolio_defaults": PORTFOLIO_DEFAULTS,
        },
        "folds": [
            {
                key: value
                for key, value in fold.items()
                if key not in {"curve", "selected", "test_frame", "trades"}
            }
            for fold in fold_outputs
        ],
        "oos_event": oos_event,
        "oos_portfolio": {
            key: value for key, value in oos_portfolio.items() if key != "curve"
        },
        "decision_gate": decision,
        "factor_count": len(factor_ids),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "warnings": [
            "All factor selection, directions, clusters and score bands use only the fold training window.",
            "Factor and band labels must have a D+5 exit no later than the training-window end.",
            "Test folds are strictly later than their training windows.",
            "This remains quasi-out-of-sample because the full historical period was previously observed.",
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
    fold_rows = [
        {
            "fold": fold["name"],
            "test_start": fold["test_start"],
            "test_end": fold["test_end"],
            "band": fold["chosen_band"]["name"],
            "admitted_factors": fold["admitted_factors"],
            "representatives": len(fold["representatives"]),
            "selected_n": fold["selected_n"],
            "event_net": fold["event"]["mean_net_return"],
            "event_delta": fold["event"]["mean_incremental_return"],
            "portfolio_return": fold["portfolio"]["total_return"],
            "portfolio_drawdown": fold["portfolio"]["max_drawdown_mtm"],
            "filled_n": fold["portfolio"]["filled_n"],
        }
        for fold in fold_outputs
    ]
    pl.DataFrame(fold_rows, infer_schema_length=None).write_csv(
        args.output / "folds.csv",
    )
    trade_rows = [
        {"fold": fold["name"], **trade}
        for fold in fold_outputs
        for trade in fold["trades"]
    ]
    pl.DataFrame(trade_rows, infer_schema_length=None).write_csv(
        args.output / "trades.csv",
    )
    curve_rows = [
        {"fold": fold["name"], **curve}
        for fold in fold_outputs
        for curve in fold["curve"]
    ]
    pl.DataFrame(curve_rows, infer_schema_length=None).write_csv(
        args.output / "equity_curve.csv",
    )
    all_selected.write_parquet(
        args.output / "oos_selected.parquet",
        compression="zstd",
    )
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
    parser.add_argument("--factor-admission", type=Path, required=True)
    parser.add_argument("--d5-outcomes", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args()
    report = run_study(args)
    print(json.dumps({
        "event": "complete",
        "oos_return": report["oos_portfolio"]["total_return"],
        "gate_passed": report["decision_gate"]["passed"],
        "elapsed_seconds": report["elapsed_seconds"],
    }), flush=True)


if __name__ == "__main__":
    main()
