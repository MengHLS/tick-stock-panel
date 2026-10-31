"""Pre-registered D-day downside-probability model.

The model predicts whether the frozen D+5 net return will be at most -5%.
It is refit in each expanding walk-forward fold and filters the already-ranked
shortlist using a training-period probability quantile.
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
from scripts.auction_high_open_study import _write_json, summarize
from scripts.auction_multifactor_study import build_scores
from scripts.auction_portfolio_construction_study import (
    PORTFOLIO_DEFAULTS,
    _with_baseline,
    load_calendar,
    load_daily_closes,
    select_candidates,
    simulate_daily_mark_portfolio,
)
from scripts.auction_walkforward_study import (
    FOLDS,
    add_chosen_band_signal,
    admit_fold_factors,
    calibrate_band,
    chain_portfolio_curves,
    cluster_fold_factors,
    load_panel,
    mature_training_rows,
)

VERSION = "auction-downside-model-v1"
KEYS = ["symbol", "date"]
GROUPS = ["date", "gap_bucket"]
SEVERE_LOSS_THRESHOLD = -0.05
MAX_TRAIN_ROWS = 30_000
MIN_TRAIN_ROWS = 5_000
L2_ALPHA = 1.0
MAX_ITER = 20
MIN_TEST_AUC = 0.52
PRIMARY_VARIANT = "reject_top_50"
VARIANTS = {
    "baseline": None,
    "reject_top_30": 0.70,
    "reject_top_50": 0.50,
}
AUCTION_COLUMNS = [
    "opening_gap",
    "tail_price_change",
    "last_imbalance",
    "last_minute_matched_growth",
    "post0920_matched_growth",
    "volume_vs_prev",
    "last_unmatched_sell_shares",
    "c0924_unmatched_sell_shares",
    "last_age_ms",
    "c0924_age_ms",
    "population_sell_expansion",
]
AUCTION_RANK_COLUMNS = [
    "tail_price_change",
    "last_imbalance",
    "last_minute_matched_growth",
    "post0920_matched_growth",
    "volume_vs_prev",
]
DECISION_GATE = {
    "primary_variant": PRIMARY_VARIANT,
    "minimum_selected_events": 500,
    "maximum_mean_daily_candidates": 2.0,
    "minimum_mean_test_auc": MIN_TEST_AUC,
    "mean_net_return_positive": True,
    "incremental_ci_lower_positive": True,
    "portfolio_total_return_positive": True,
    "portfolio_max_drawdown_floor": -0.15,
    "no_stale_marks": True,
}


def _finite(column: str) -> pl.Expr:
    value = pl.col(column)
    return value.is_not_null() & value.is_finite()


def load_model_panel(
    events_path: Path,
    factor_admission_path: Path,
    d5_outcomes_path: Path,
) -> tuple[pl.DataFrame, list[str]]:
    panel, factor_ids = load_panel(events_path, factor_admission_path, d5_outcomes_path)
    auction = (
        pl.scan_parquet(events_path)
        .filter(
            (pl.col("horizon") == 3)
            & pl.col("gap_bucket").is_in(["2-4", "4-6", "6-8"])
            & pl.col("signal_eligible"),
        )
        .join(panel.lazy().select(KEYS), on=KEYS, how="semi")
        .select(*KEYS, *AUCTION_COLUMNS)
        .collect()
    )
    if auction.select(pl.struct(KEYS).is_duplicated().any()).item():
        raise ValueError("Duplicate D-day auction feature keys")
    panel = panel.join(auction, on=KEYS, how="left")
    if panel.filter(pl.col("opening_gap").is_null()).height:
        raise ValueError("Missing D-day auction features for model panel")
    rank_expressions = []
    for column in AUCTION_RANK_COLUMNS:
        value = pl.col(column)
        n = value.count().over(GROUPS)
        rank_expressions.append(
            pl.when(~_finite(column)).then(None)
            .when(n <= 1).then(0.5)
            .otherwise((value.rank("average").over(GROUPS) - 1) / (n - 1))
            .alias(f"auction_rank__{column}"),
        )
    sell_data_valid = (
        _finite("last_imbalance")
        & _finite("last_unmatched_sell_shares")
        & _finite("c0924_unmatched_sell_shares")
        & pl.col("last_age_ms").is_not_null()
        & (pl.col("last_age_ms") <= 30_000)
        & pl.col("c0924_age_ms").is_not_null()
        & (pl.col("c0924_age_ms") <= 30_000)
        & pl.col("population_sell_expansion").is_not_null()
        & (pl.col("population_sell_expansion") >= 4)
    ).fill_null(False)
    panel = panel.with_columns(rank_expressions).with_columns(
        (
            sell_data_valid
            & (pl.col("last_unmatched_sell_shares") > pl.col("c0924_unmatched_sell_shares"))
            & (pl.col("last_imbalance") < 0)
        ).alias("sell_expansion"),
        (pl.col("gap_bucket") == "4-6").cast(pl.Float64).alias("gap_4_6"),
        (pl.col("gap_bucket") == "6-8").cast(pl.Float64).alias("gap_6_8"),
    )
    return panel, factor_ids


def feature_columns(factor_ids: list[str]) -> list[str]:
    return [
        *[f"rank__{factor_id}" for factor_id in factor_ids],
        *[f"auction_rank__{column}" for column in AUCTION_RANK_COLUMNS],
        "opening_gap",
        "tail_strength_signal",
        "tail_strength_rank",
        "sell_expansion",
        "gap_4_6",
        "gap_6_8",
    ]


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -30, 30)))


def fit_logistic(
    frame: pl.DataFrame,
    features: list[str],
    *,
    alpha: float = L2_ALPHA,
    max_iter: int = MAX_ITER,
) -> dict:
    if frame.height < MIN_TRAIN_ROWS:
        raise ValueError(f"Need at least {MIN_TRAIN_ROWS} training rows")
    matrix = frame.select(features).to_numpy().astype(float, copy=True)
    target = frame["_severe_downside"].to_numpy().astype(float)
    medians = np.nanmedian(matrix, axis=0)
    medians = np.where(np.isfinite(medians), medians, 0.0)
    missing = np.isnan(matrix)
    matrix[missing] = np.take(medians, np.where(missing)[1])
    means = matrix.mean(axis=0)
    stds = matrix.std(axis=0)
    stds = np.where(stds > 1e-9, stds, 1.0)
    standardized = np.clip((matrix - means) / stds, -8, 8)
    design = np.column_stack([np.ones(len(standardized)), standardized])
    beta = np.zeros(design.shape[1], dtype=float)
    penalty = np.eye(design.shape[1], dtype=float)
    penalty[0, 0] = 0.0
    converged = False
    iterations = 0
    for _iterations in range(1, max_iter + 1):
        iterations = _iterations
        probability = _sigmoid(design @ beta)
        gradient = design.T @ (probability - target) / len(target)
        gradient += alpha * penalty @ beta
        weights = np.clip(probability * (1 - probability), 1e-6, None)
        hessian = design.T @ (weights[:, None] * design) / len(target)
        hessian += alpha * penalty + np.eye(design.shape[1]) * 1e-8
        step = np.linalg.solve(hessian, gradient)
        beta -= step
        if float(np.max(np.abs(step))) < 1e-6:
            converged = True
            break
    return {
        "features": features,
        "beta": beta,
        "medians": medians,
        "means": means,
        "stds": stds,
        "iterations": iterations,
        "converged": converged,
    }


def predict_logistic(frame: pl.DataFrame, model: dict) -> np.ndarray:
    matrix = frame.select(model["features"]).to_numpy().astype(float, copy=True)
    missing = np.isnan(matrix)
    matrix[missing] = np.take(model["medians"], np.where(missing)[1])
    standardized = np.clip(
        (matrix - model["means"]) / model["stds"],
        -8,
        8,
    )
    design = np.column_stack([np.ones(len(standardized)), standardized])
    return _sigmoid(design @ model["beta"])


def roc_auc(target: np.ndarray, probability: np.ndarray) -> float | None:
    positive = target.astype(bool)
    n_positive = int(positive.sum())
    n_negative = len(positive) - n_positive
    if not n_positive or not n_negative:
        return None
    ranks = (
        pl.DataFrame({"probability": probability})
        .select(pl.col("probability").rank("average"))
        .to_series()
        .to_numpy()
    )
    return float(
        (ranks[positive].sum() - n_positive * (n_positive + 1) / 2)
        / (n_positive * n_negative),
    )


def assign_fold(frame: pl.DataFrame) -> pl.DataFrame:
    pieces = []
    for fold in FOLDS:
        piece = frame.filter(
            pl.col("date").is_between(fold["test_start"], fold["test_end"]),
        ).with_columns(pl.lit(fold["name"]).alias("fold"))
        if not piece.is_empty():
            pieces.append(piece)
    assigned = pl.concat(pieces)
    if assigned.height != frame.height:
        raise ValueError("Selected rows fall outside configured walk-forward folds")
    return assigned


def load_selected_base(panel: pl.DataFrame, selected_path: Path) -> pl.DataFrame:
    selected = (
        pl.read_parquet(selected_path, columns=KEYS)
        .with_row_index("_selection_order")
    )
    base = (
        selected.join(panel, on=KEYS, how="left")
        .sort("_selection_order")
    )
    if base.filter(pl.col("net_return").is_null()).height:
        raise ValueError("Selected events missing from the model panel")
    return assign_fold(base)


def build_training_shortlist(
    panel: pl.DataFrame,
    factor_ids: list[str],
    fold: dict,
    *,
    seed: int,
) -> pl.DataFrame:
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
        seed=seed,
    )
    scored = build_scores(panel, representatives)
    chosen_band, _ = calibrate_band(
        scored,
        train_start=fold["train_start"],
        train_end=fold["train_end"],
        seed=seed,
    )
    scored = add_chosen_band_signal(scored, chosen_band)
    selected, _ = select_candidates(
        scored,
        start=fold["train_start"],
        end=fold["train_end"],
        contract={
            "signal_column": "_walkforward_signal",
            "score_column": "combined_rank",
            "selection": "bucket_quota",
        },
        max_new_per_day=PORTFOLIO_DEFAULTS["max_new_per_day"],
    )
    if selected.is_empty():
        raise ValueError(f"No training shortlist events for {fold['name']}")
    return selected


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
            (pl.col("net_return") <= SEVERE_LOSS_THRESHOLD).alias("_severe_downside"),
        )
        training = training.filter(
            pl.col("_severe_downside").is_not_null() & pl.col("net_return").is_finite(),
        )
        if training.height < MIN_TRAIN_ROWS:
            raise ValueError(f"Too few training rows in {fold['name']}: {training.height}")
        sampled = (
            training.sample(MAX_TRAIN_ROWS, seed=20261101 + fold_index)
            if training.height > MAX_TRAIN_ROWS
            else training
        )
        model = fit_logistic(sampled, features)
        train_probability = predict_logistic(training, model)
        test = panel.filter(
            pl.col("date").is_between(fold["test_start"], fold["test_end"])
            & pl.col("net_return").is_finite(),
        )
        test_probability = predict_logistic(test, model)
        train_target = training["_severe_downside"].to_numpy()
        test_target = (
            test["net_return"] <= SEVERE_LOSS_THRESHOLD
        ).to_numpy()
        training_shortlist = build_training_shortlist(
            panel,
            factor_ids,
            fold,
            seed=seed + fold_index,
        )
        training_shortlist_probability = predict_logistic(training_shortlist, model)
        thresholds = {
            variant: float(np.quantile(training_shortlist_probability, quantile))
            for variant, quantile in VARIANTS.items()
            if quantile is not None
        }
        fold_base = (
            base.filter(pl.col("fold") == fold["name"])
            .join(
                test.select(*KEYS, pl.Series("downside_probability", test_probability)),
                on=KEYS,
                how="left",
            )
            .sort("_selection_order")
        )
        if fold_base.filter(pl.col("downside_probability").is_null()).height:
            raise ValueError(f"Missing model predictions for {fold['name']}")
        for variant, quantile in VARIANTS.items():
            selected = (
                fold_base
                if quantile is None
                else fold_base.filter(
                    pl.col("downside_probability") <= thresholds[variant],
                )
            )
            variant_rows[variant].append(selected)
        metrics.append({
            "fold": fold["name"],
            "train_n": training.height,
            "train_sample_n": sampled.height,
            "train_severe_rate": float(train_target.mean()),
            "train_auc": roc_auc(train_target, train_probability),
            "train_shortlist_n": training_shortlist.height,
            "test_n": test.height,
            "test_severe_rate": float(test_target.mean()),
            "test_auc": roc_auc(test_target, test_probability),
            "threshold_keep_70": thresholds.get("reject_top_30"),
            "threshold_keep_50": thresholds.get("reject_top_50"),
            "iterations": model["iterations"],
            "converged": model["converged"],
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
    aucs = [row["test_auc"] for row in metrics if row["test_auc"] is not None]
    mean_auc = float(np.mean(aucs)) if aucs else 0.0
    checks = {
        "minimum_selected_events": selected_n >= DECISION_GATE["minimum_selected_events"],
        "mean_daily_candidates": (
            selected_n / session_count <= DECISION_GATE["maximum_mean_daily_candidates"]
        ),
        "mean_test_auc": mean_auc >= DECISION_GATE["minimum_mean_test_auc"],
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
        "mean_test_auc": mean_auc,
        "checks": checks,
        "passed": all(checks.values()),
    }


def write_results(path: Path, report: dict) -> None:
    lines = [
        "# D-day downside-probability model",
        "",
        f"Algorithm: `{VERSION}`.",
        "",
        "Target: D+5 net return at or below -5%.",
        "Thresholds use training-period probability quantiles only.",
        "",
        "| Fold | Train N | Test N | Test severe | Train AUC | Test AUC |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["model_metrics"]:
        lines.append(
            f"| {row['fold']} | {row['train_n']} | {row['test_n']} | "
            f"{row['test_severe_rate'] * 100:.2f}% | "
            f"{row['train_auc']:.3f} | {row['test_auc']:.3f} |",
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
    base = load_selected_base(panel, args.selected)
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
        "target": {
            "name": "severe_downside",
            "threshold": SEVERE_LOSS_THRESHOLD,
        },
        "model": {
            "type": "l2_logistic",
            "alpha": L2_ALPHA,
            "max_iter": MAX_ITER,
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
            "Thresholds use training-period predictions and are never tuned on test folds.",
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
    parser.add_argument("--selected", type=Path, required=True)
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
        "mean_test_auc": report["decision_gate"]["mean_test_auc"],
    }), flush=True)


if __name__ == "__main__":
    main()
