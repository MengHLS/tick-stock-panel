"""Pre-registered D+5 expected-return model.

The model predicts the frozen D+5 net return and filters the canonical
downside-model shortlist using training-period prediction quantiles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import polars as pl

from scripts.auction_d_day_veto_study import _zero_portfolio_summary, flatten_csv_row
from scripts.auction_downside_model_study import (
    KEYS,
    assign_fold,
    build_training_shortlist,
    feature_columns,
    load_model_panel,
)
from scripts.auction_high_open_study import _write_json, summarize
from scripts.auction_portfolio_construction_study import (
    PORTFOLIO_DEFAULTS,
    _with_baseline,
    load_calendar,
    load_daily_closes,
    simulate_daily_mark_portfolio,
)
from scripts.auction_walkforward_study import (
    FOLDS,
    chain_portfolio_curves,
    mature_training_rows,
)

VERSION = "auction-expected-return-model-v1"
RIDGE_ALPHA = 25.0
MAX_TRAIN_ROWS = 30_000
MIN_TRAIN_ROWS = 5_000
TARGET_CLIP_LOWER = -0.20
TARGET_CLIP_UPPER = 0.20
PRIMARY_VARIANT = "keep_top_50"
VARIANTS = {
    "baseline": None,
    "keep_top_70": 0.30,
    "keep_top_50": 0.50,
    "keep_top_30": 0.70,
}
DECISION_GATE = {
    "primary_variant": PRIMARY_VARIANT,
    "minimum_selected_events": 500,
    "maximum_mean_daily_candidates": 2.0,
    "minimum_mean_test_ic": 0.01,
    "minimum_positive_ic_folds": 3,
    "mean_net_return_positive": True,
    "incremental_ci_lower_positive": True,
    "portfolio_total_return_positive": True,
    "portfolio_max_drawdown_floor": -0.15,
    "no_stale_marks": True,
}


def load_downside_base(
    panel: pl.DataFrame,
    selected_path: Path,
    *,
    downside_variant: str,
) -> pl.DataFrame:
    selected = (
        pl.read_parquet(selected_path, columns=[*KEYS, "variant"])
        .filter(pl.col("variant") == downside_variant)
        .select(KEYS)
        .with_row_index("_selection_order")
    )
    if selected.is_empty():
        raise ValueError(f"No events for downside variant {downside_variant}")
    if selected.select(pl.struct(KEYS).is_duplicated().any()).item():
        raise ValueError("Duplicate downside-model event keys")
    base = selected.join(panel, on=KEYS, how="left").sort("_selection_order")
    if base.filter(pl.col("net_return").is_null()).height:
        raise ValueError("Downside-model events missing from the model panel")
    return assign_fold(base)


def _prepare_design(
    frame: pl.DataFrame,
    features: list[str],
    *,
    medians: np.ndarray | None = None,
    means: np.ndarray | None = None,
    stds: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    matrix = frame.select(features).to_numpy().astype(float, copy=True)
    if medians is None:
        medians = np.nanmedian(matrix, axis=0)
        medians = np.where(np.isfinite(medians), medians, 0.0)
    missing = np.isnan(matrix)
    matrix[missing] = np.take(medians, np.where(missing)[1])
    if means is None:
        means = matrix.mean(axis=0)
    if stds is None:
        stds = matrix.std(axis=0)
        stds = np.where(stds > 1e-9, stds, 1.0)
    standardized = np.clip((matrix - means) / stds, -8, 8)
    design = np.column_stack([np.ones(len(standardized)), standardized])
    return design, {
        "medians": medians,
        "means": means,
        "stds": stds,
    }


def fit_ridge(
    frame: pl.DataFrame,
    features: list[str],
    *,
    alpha: float = RIDGE_ALPHA,
) -> dict:
    if frame.height < MIN_TRAIN_ROWS:
        raise ValueError(f"Need at least {MIN_TRAIN_ROWS} training rows")
    design, normalization = _prepare_design(frame, features)
    target = frame["_target_return"].to_numpy().astype(float)
    penalty = np.eye(design.shape[1], dtype=float)
    penalty[0, 0] = 0.0
    left = design.T @ design + alpha * penalty + np.eye(design.shape[1]) * 1e-8
    right = design.T @ target
    beta = np.linalg.solve(left, right)
    return {
        "features": features,
        "beta": beta,
        **normalization,
    }


def predict_ridge(frame: pl.DataFrame, model: dict) -> np.ndarray:
    design, _ = _prepare_design(
        frame,
        model["features"],
        medians=model["medians"],
        means=model["means"],
        stds=model["stds"],
    )
    return design @ model["beta"]


def rank_correlation(target: np.ndarray, prediction: np.ndarray) -> float | None:
    valid = np.isfinite(target) & np.isfinite(prediction)
    target = target[valid]
    prediction = prediction[valid]
    if len(target) < 3 or np.ptp(target) <= 0 or np.ptp(prediction) <= 0:
        return None
    target_rank = (
        pl.Series("value", target).rank("average").to_numpy()
    )
    prediction_rank = (
        pl.Series("value", prediction).rank("average").to_numpy()
    )
    return float(np.corrcoef(target_rank, prediction_rank)[0, 1])


def mean_daily_rank_ic(
    frame: pl.DataFrame,
    *,
    target_column: str,
    prediction_column: str,
) -> float | None:
    values = []
    sample = frame.select("date", target_column, prediction_column)
    for _key, group in sample.group_by("date", maintain_order=True):
        if group.height < 10:
            continue
        value = rank_correlation(
            group[target_column].to_numpy(),
            group[prediction_column].to_numpy(),
        )
        if value is not None:
            values.append(value)
    return float(np.mean(values)) if values else None


def prediction_thresholds(predictions: np.ndarray) -> dict[str, float]:
    return {
        variant: float(np.quantile(predictions, quantile))
        for variant, quantile in VARIANTS.items()
        if quantile is not None
    }


def fit_fold_models(
    panel: pl.DataFrame,
    base: pl.DataFrame,
    features: list[str],
    factor_ids: list[str],
    *,
    seed: int,
) -> tuple[dict[str, pl.DataFrame], list[dict], pl.DataFrame]:
    variant_rows = {variant: [] for variant in VARIANTS}
    metrics = []
    weight_rows = []
    for fold_index, fold in enumerate(FOLDS):
        training = mature_training_rows(
            panel,
            train_start=fold["train_start"],
            train_end=fold["train_end"],
        ).with_columns(
            pl.col("net_return")
            .clip(TARGET_CLIP_LOWER, TARGET_CLIP_UPPER)
            .alias("_target_return"),
        )
        if training.height < MIN_TRAIN_ROWS:
            raise ValueError(f"Too few training rows in {fold['name']}: {training.height}")
        sampled = (
            training.sample(MAX_TRAIN_ROWS, seed=20261101 + fold_index)
            if training.height > MAX_TRAIN_ROWS
            else training
        )
        model = fit_ridge(sampled, features)
        train_probability = predict_ridge(training, model)
        test = panel.filter(
            pl.col("date").is_between(fold["test_start"], fold["test_end"])
            & pl.col("net_return").is_finite(),
        )
        test = test.with_columns(
            pl.Series("expected_return", predict_ridge(test, model)),
        )
        train_target = training["_target_return"].to_numpy()
        test_target = test["net_return"].to_numpy()
        test_prediction = test["expected_return"].to_numpy()
        training_shortlist = build_training_shortlist(
            panel,
            factor_ids,
            fold,
            seed=seed + fold_index,
        )
        training_shortlist_prediction = predict_ridge(training_shortlist, model)
        thresholds = prediction_thresholds(training_shortlist_prediction)
        fold_base = (
            base.filter(pl.col("fold") == fold["name"])
            .join(
                test.select(*KEYS, "expected_return"),
                on=KEYS,
                how="left",
            )
            .sort("_selection_order")
        )
        if fold_base.filter(pl.col("expected_return").is_null()).height:
            raise ValueError(f"Missing expected-return predictions for {fold['name']}")
        for variant, quantile in VARIANTS.items():
            selected = (
                fold_base
                if quantile is None
                else fold_base.filter(
                    pl.col("expected_return") >= thresholds[variant],
                )
            )
            variant_rows[variant].append(selected)
        metrics.append({
            "fold": fold["name"],
            "train_n": training.height,
            "train_sample_n": sampled.height,
            "train_target_mean": float(train_target.mean()),
            "test_n": test.height,
            "test_target_mean": float(test_target.mean()),
            "train_ic": rank_correlation(train_target, train_probability),
            "test_ic": rank_correlation(test_target, test_prediction),
            "test_daily_ic": mean_daily_rank_ic(
                test,
                target_column="net_return",
                prediction_column="expected_return",
            ),
            "test_top20_minus_bottom20": _tail_spread(
                test,
                target_column="net_return",
                prediction_column="expected_return",
            ),
            "training_shortlist_n": training_shortlist.height,
            "threshold_keep_70": thresholds.get("keep_top_70"),
            "threshold_keep_50": thresholds.get("keep_top_50"),
            "threshold_keep_30": thresholds.get("keep_top_30"),
        })
        for feature, coefficient in zip(
            features,
            model["beta"][1:],
            strict=True,
        ):
            weight_rows.append({
                "fold": fold["name"],
                "feature": feature,
                "coefficient": float(coefficient),
            })
    variants = {
        variant: pl.concat(rows)
        for variant, rows in variant_rows.items()
    }
    return variants, metrics, pl.DataFrame(weight_rows)


def _tail_spread(
    frame: pl.DataFrame,
    *,
    target_column: str,
    prediction_column: str,
    quantile: float = 0.20,
) -> float | None:
    if frame.height < 20:
        return None
    lower = float(frame[prediction_column].quantile(quantile))
    upper = float(frame[prediction_column].quantile(1 - quantile))
    bottom = frame.filter(pl.col(prediction_column) <= lower)[target_column].mean()
    top = frame.filter(pl.col(prediction_column) >= upper)[target_column].mean()
    if bottom is None or top is None:
        return None
    return float(top - bottom)


def event_results(
    panel: pl.DataFrame,
    variants: dict[str, pl.DataFrame],
    *,
    bootstrap_samples: int,
    seed: int,
) -> list[dict]:
    oos = panel.filter(
        pl.col("date").is_between(FOLDS[0]["test_start"], FOLDS[-1]["test_end"]),
    )
    baseline = _with_baseline(oos)
    rows = []
    for variant, selected in variants.items():
        exact = baseline.join(selected.select(KEYS), on=KEYS, how="semi")
        rows.append({
            "variant": variant,
            "selected_n": selected.height,
            **summarize(
                exact,
                bootstrap_samples=bootstrap_samples,
                seed=seed,
            ),
        })
    return rows


def portfolio_results(
    variants: dict[str, pl.DataFrame],
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
            selected = variants[variant].filter(pl.col("fold") == fold["name"])
            if selected.is_empty():
                summary = _zero_portfolio_summary()
                filled = []
                curve = []
            else:
                summary, filled, curve = simulate_daily_mark_portfolio(
                    selected,
                    calendar=calendar,
                    daily_closes=daily_closes,
                    start=fold["test_start"],
                    end=fold["test_end"],
                )
            summary["candidate_n"] = selected.height
            portfolio[variant][fold["name"]] = summary
            trades[variant].extend({"fold": fold["name"], **row} for row in filled)
            curves[variant].extend({"fold": fold["name"], **row} for row in curve)
            fold_portfolios.append({
                "name": fold["name"],
                "portfolio": summary,
                "curve": curve,
            })
        chained = chain_portfolio_curves(fold_portfolios)
        portfolio[variant]["oos"] = {
            key: value for key, value in chained.items() if key != "curve"
        }
    return portfolio, trades, curves


def decision_gate(
    variants: dict[str, pl.DataFrame],
    events: list[dict],
    portfolio: dict[str, dict[str, dict]],
    metrics: list[dict],
    *,
    session_count: int,
) -> dict:
    event = next(row for row in events if row["variant"] == PRIMARY_VARIANT)
    interval = (event.get("cluster_bootstrap_95") or {}).get(
        "mean_incremental_return",
    )
    result = portfolio[PRIMARY_VARIANT]["oos"]
    selected_n = variants[PRIMARY_VARIANT].height
    ics = [row["test_ic"] for row in metrics if row["test_ic"] is not None]
    daily_ics = [
        row["test_daily_ic"]
        for row in metrics
        if row["test_daily_ic"] is not None
    ]
    mean_ic = float(np.mean(ics)) if ics else 0.0
    mean_daily_ic = float(np.mean(daily_ics)) if daily_ics else 0.0
    positive_ic_folds = sum(value > 0 for value in ics)
    checks = {
        "minimum_selected_events": selected_n >= DECISION_GATE["minimum_selected_events"],
        "mean_daily_candidates": (
            selected_n / session_count <= DECISION_GATE["maximum_mean_daily_candidates"]
        ),
        "mean_test_ic": mean_ic >= DECISION_GATE["minimum_mean_test_ic"],
        "positive_ic_folds": (
            positive_ic_folds >= DECISION_GATE["minimum_positive_ic_folds"]
        ),
        "mean_net_return_positive": (
            event.get("mean_net_return") is not None
            and event["mean_net_return"] > 0
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
        "mean_test_ic": mean_ic,
        "mean_test_daily_ic": mean_daily_ic,
        "positive_ic_folds": positive_ic_folds,
        "checks": checks,
        "passed": all(checks.values()),
    }


def write_results(path: Path, report: dict) -> None:
    lines = [
        "# D+5 expected-return model",
        "",
        f"Algorithm: `{VERSION}`.",
        "",
        "Target: clipped D+5 net return.",
        "Thresholds use training-period final-shortlist prediction quantiles.",
        "",
        "| Fold | Train N | Test N | Test IC | Daily IC | Top-bottom |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["model_metrics"]:
        lines.append(
            f"| {row['fold']} | {row['train_n']} | {row['test_n']} | "
            f"{_format_optional(row['test_ic'])} | "
            f"{_format_optional(row['test_daily_ic'])} | "
            f"{_format_optional(row['test_top20_minus_bottom20'])} |",
        )
    lines.extend([
        "",
        "| Variant | Selected | Mean/day | Net | Delta | Delta 95% CI |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    sessions = report["session_count"]
    for row in report["events"]:
        interval = (row.get("cluster_bootstrap_95") or {}).get(
            "mean_incremental_return",
        )
        interval_text = (
            f"{interval[0] * 100:.3f}% to {interval[1] * 100:.3f}%"
            if interval else "NA"
        )
        lines.append(
            f"| {row['variant']} | {row['selected_n']} | "
            f"{row['selected_n'] / sessions:.3f} | "
            f"{row['mean_net_return'] * 100:.3f}% | "
            f"{row['mean_incremental_return'] * 100:.3f}% | {interval_text} |",
        )
    lines.extend([
        "",
        "| Variant | Portfolio | Max drawdown | Filled | Stale marks |",
        "|---|---:|---:|---:|---:|",
    ])
    for variant in VARIANTS:
        row = report["portfolio"][variant]["oos"]
        lines.append(
            f"| {variant} | {row['total_return'] * 100:.3f}% | "
            f"{row['max_drawdown_mtm'] * 100:.3f}% | "
            f"{row['filled_n']} | {row['stale_marks']} |",
        )
    lines.extend([
        "",
        f"Primary variant: `{PRIMARY_VARIANT}`.",
        "",
        f"Gate passed: `{report['decision_gate']['passed']}`.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _format_optional(value: float | None) -> str:
    return "NA" if value is None else f"{value:.3f}"


def run_study(args: argparse.Namespace) -> dict:
    if args.output.exists():
        raise FileExistsError("Use a NEW output directory; existing runs are never overwritten")
    if args.bootstrap_samples < 0:
        raise ValueError("bootstrap_samples must be non-negative")
    started = time.perf_counter()
    panel, factor_ids = load_model_panel(
        args.events,
        args.factor_admission,
        args.d5_outcomes,
    )
    features = feature_columns(factor_ids)
    base = load_downside_base(
        panel,
        args.downside_selected,
        downside_variant=args.downside_variant,
    )
    variants, model_metrics, weights = fit_fold_models(
        panel,
        base,
        features,
        factor_ids,
        seed=args.seed,
    )
    baseline = variants["baseline"]
    symbols = sorted(set(baseline["symbol"].to_list()))
    start_date = baseline["date"].min()
    end_date = baseline["exit_date"].max()
    calendar = load_calendar(args.data_dir, start_date, end_date)
    daily_closes = load_daily_closes(args.data_dir, symbols, start_date, end_date)
    session_count = sum(
        fold["test_start"] <= day <= fold["test_end"]
        for fold in FOLDS
        for day in calendar
    )
    events = event_results(
        panel,
        variants,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    portfolio, trades, curves = portfolio_results(
        variants,
        calendar=calendar,
        daily_closes=daily_closes,
    )
    gate = decision_gate(
        variants,
        events,
        portfolio,
        model_metrics,
        session_count=session_count,
    )
    elapsed = round(time.perf_counter() - started, 3)
    report = {
        "version": VERSION,
        "primary_variant": PRIMARY_VARIANT,
        "variants": VARIANTS,
        "downside_variant": args.downside_variant,
        "target": {
            "name": "d5_net_return",
            "clip_lower": TARGET_CLIP_LOWER,
            "clip_upper": TARGET_CLIP_UPPER,
        },
        "model": {
            "type": "ridge",
            "alpha": RIDGE_ALPHA,
            "max_train_rows": MAX_TRAIN_ROWS,
            "feature_count": len(features),
        },
        "model_metrics": model_metrics,
        "decision_gate": gate,
        "events": events,
        "portfolio": portfolio,
        "session_count": session_count,
        "portfolio_defaults": PORTFOLIO_DEFAULTS,
        "elapsed_seconds": elapsed,
        "warnings": [
            "The model is refit only on labels matured before each test window.",
            "Thresholds use training-period final-shortlist predictions.",
            "Rejected candidates are not refilled from lower ranks.",
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
    pl.DataFrame(model_metrics, infer_schema_length=None).write_csv(
        args.output / "model_metrics.csv",
    )
    weights.write_csv(args.output / "weights.csv")
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
    pl.concat([
        frame.with_columns(pl.lit(variant).alias("variant"))
        for variant, frame in variants.items()
    ]).write_parquet(
        args.output / "selected_variants.parquet",
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
    parser.add_argument("--downside-selected", type=Path, required=True)
    parser.add_argument("--downside-variant", default="reject_top_50")
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--factor-admission", type=Path, required=True)
    parser.add_argument("--d5-outcomes", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args()
    report = run_study(args)
    event = next(
        row
        for row in report["events"]
        if row["variant"] == report["primary_variant"]
    )
    print(json.dumps({
        "event": "complete",
        "primary": report["primary_variant"],
        "gate_passed": report["decision_gate"]["passed"],
        "portfolio_return": report["portfolio"][report["primary_variant"]]["oos"][
            "total_return"
        ],
        "selected_n": event["selected_n"],
        "mean_test_ic": report["decision_gate"]["mean_test_ic"],
    }), flush=True)


if __name__ == "__main__":
    main()
