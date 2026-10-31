"""Pre-registered D-1 market-return model for absolute auction exposure.

The target is the matured D+5 net return of all eligible main-board events in
each date and gap bucket. Only completed D-1 index data is used as input.
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
from scripts.auction_downside_model_study import (
    build_training_shortlist,
    load_model_panel,
)
from scripts.auction_high_open_study import (
    _partitions,
    _write_json,
    summarize,
)
from scripts.auction_portfolio_construction_study import (
    PORTFOLIO_DEFAULTS,
    _with_baseline,
    load_calendar,
    load_daily_closes,
    simulate_daily_mark_portfolio,
)
from scripts.auction_risk_budget_exposure_study import load_base
from scripts.auction_walkforward_study import (
    FOLDS,
    chain_portfolio_curves,
    mature_training_rows,
)

VERSION = "auction-market-return-model-v2"
KEYS = ["symbol", "date"]
GROUP_KEYS = ["date", "gap_bucket"]
MIN_TRAIN_ROWS = 300
RIDGE_ALPHA = 10.0
TARGET_CLIP_LOWER = -0.20
TARGET_CLIP_UPPER = 0.20
PRIMARY_VARIANT = "market_plus_alpha_gate"
VARIANTS = (
    "always_full",
    "trend_vol_gate",
    "market_positive_gate",
    "market_top50_gate",
    "market_plus_alpha_gate",
)
MARKET_FEATURES = [
    "market_ret_1",
    "market_ret_5",
    "market_ret_20",
    "market_ret_60",
    "market_ma5_bias",
    "market_ma20_bias",
    "market_ma60_bias",
    "market_vol_5",
    "market_vol_20",
    "market_vol_60",
    "market_drawdown_20",
    "market_drawdown_60",
    "market_volume_ratio_5_20",
    "market_amount_ratio_5_20",
    "market_up_days_20",
]
FEATURES = [*MARKET_FEATURES, "gap_4_6", "gap_6_8"]
DECISION_GATE = {
    "primary_variant": PRIMARY_VARIANT,
    "minimum_selected_events": 200,
    "maximum_mean_daily_candidates": 1.0,
    "mean_net_return_positive": True,
    "incremental_ci_lower_positive": True,
    "portfolio_total_return_positive": True,
    "portfolio_max_drawdown_floor": -0.15,
    "no_stale_marks": True,
}


def build_market_features(
    data_dir: Path,
    start: date,
    end: date,
) -> pl.DataFrame:
    files = _partitions(
        data_dir / "kline_index_daily",
        start - timedelta(days=400),
        end,
    )
    if not files:
        raise ValueError("No index sessions for market-return features")
    index = (
        pl.scan_parquet(files, hive_partitioning=False, extra_columns="ignore")
        .filter(pl.col("symbol") == "000001.SH")
        .select("date", "close", "volume", "amount")
        .collect()
        .sort("date")
    )
    if index["date"].is_duplicated().any():
        raise ValueError("Duplicate index dates")
    return compute_market_features(index)


def compute_market_features(index: pl.DataFrame) -> pl.DataFrame:
    computed = (
        index.sort("date")
        .with_columns(
            (pl.col("close") / pl.col("close").shift(1) - 1).alias("_ret_1"),
        )
        .with_columns(
            (pl.col("close") / pl.col("close").shift(5) - 1).alias("market_ret_5"),
            (pl.col("close") / pl.col("close").shift(20) - 1).alias("market_ret_20"),
            (pl.col("close") / pl.col("close").shift(60) - 1).alias("market_ret_60"),
            (pl.col("close") / pl.col("close").rolling_mean(5) - 1).alias(
                "market_ma5_bias",
            ),
            (pl.col("close") / pl.col("close").rolling_mean(20) - 1).alias(
                "market_ma20_bias",
            ),
            (pl.col("close") / pl.col("close").rolling_mean(60) - 1).alias(
                "market_ma60_bias",
            ),
            pl.col("_ret_1").rolling_std(5).alias("market_vol_5"),
            pl.col("_ret_1").rolling_std(20).alias("market_vol_20"),
            pl.col("_ret_1").rolling_std(60).alias("market_vol_60"),
            (
                pl.col("close") / pl.col("close").rolling_max(20) - 1
            ).alias("market_drawdown_20"),
            (
                pl.col("close") / pl.col("close").rolling_max(60) - 1
            ).alias("market_drawdown_60"),
            (
                pl.col("volume").rolling_mean(5)
                / pl.col("volume").rolling_mean(20)
            ).alias("market_volume_ratio_5_20"),
            (
                pl.col("amount").rolling_mean(5)
                / pl.col("amount").rolling_mean(20)
            ).alias("market_amount_ratio_5_20"),
            (pl.col("_ret_1") > 0)
            .cast(pl.Float64)
            .rolling_mean(20)
            .alias("market_up_days_20"),
        )
        .with_columns(
            pl.col("_ret_1").shift(1).alias("market_ret_1"),
            *[
                pl.col(feature).shift(1).alias(feature)
                for feature in MARKET_FEATURES
                if feature != "market_ret_1"
            ],
        )
        .select("date", *MARKET_FEATURES)
    )
    return computed


def build_market_targets(
    panel: pl.DataFrame,
    *,
    start: date,
    end: date,
    train_end: date | None = None,
) -> pl.DataFrame:
    resolved = panel.filter(
        pl.col("date").is_between(start, end)
        & (pl.col("entry_reason") == "ok")
        & (pl.col("exit_reason") == "ok")
        & pl.col("net_return").is_finite()
        & pl.col("exit_date").is_not_null(),
    )
    if train_end is not None:
        resolved = resolved.filter(pl.col("exit_date") <= train_end)
    targets = (
        resolved.group_by(GROUP_KEYS)
        .agg(
            pl.len().alias("market_event_n"),
            pl.col("net_return").mean().alias("market_target_return"),
        )
        .sort(GROUP_KEYS)
    )
    return targets.with_columns(
        (pl.col("gap_bucket") == "4-6").cast(pl.Float64).alias("gap_4_6"),
        (pl.col("gap_bucket") == "6-8").cast(pl.Float64).alias("gap_6_8"),
    )


def _prepare_design(
    frame: pl.DataFrame,
    *,
    medians: np.ndarray | None = None,
    means: np.ndarray | None = None,
    stds: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    matrix = frame.select(FEATURES).to_numpy().astype(float, copy=True)
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
    return (
        np.column_stack([np.ones(len(standardized)), standardized]),
        {
            "medians": medians,
            "means": means,
            "stds": stds,
        },
    )


def fit_market_ridge(frame: pl.DataFrame) -> dict:
    if frame.height < MIN_TRAIN_ROWS:
        raise ValueError(f"Need at least {MIN_TRAIN_ROWS} market rows")
    design, normalization = _prepare_design(frame)
    target = frame["_target_return"].to_numpy().astype(float)
    penalty = np.eye(design.shape[1], dtype=float)
    penalty[0, 0] = 0.0
    beta = np.linalg.solve(
        design.T @ design + RIDGE_ALPHA * penalty + np.eye(design.shape[1]) * 1e-8,
        design.T @ target,
    )
    return {
        "beta": beta,
        **normalization,
    }


def predict_market_ridge(frame: pl.DataFrame, model: dict) -> np.ndarray:
    design, _ = _prepare_design(
        frame,
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
    return float(
        np.corrcoef(
            pl.Series("value", target).rank("average").to_numpy(),
            pl.Series("value", prediction).rank("average").to_numpy(),
        )[0, 1],
    )


def estimate_training_alpha(
    panel: pl.DataFrame,
    factor_ids: list[str],
    fold: dict,
    *,
    seed: int,
) -> float:
    matured = mature_training_rows(
        panel,
        train_start=fold["train_start"],
        train_end=fold["train_end"],
    )
    shortlist = build_training_shortlist(
        panel,
        factor_ids,
        fold,
        seed=seed,
    )
    exact = _with_baseline(matured).join(
        shortlist.select(KEYS),
        on=KEYS,
        how="semi",
    )
    if exact.is_empty():
        raise ValueError(f"No matured training alpha rows for {fold['name']}")
    return float(exact["incremental_return"].mean())


def fit_fold_models(
    panel: pl.DataFrame,
    base: pl.DataFrame,
    market: pl.DataFrame,
    factor_ids: list[str],
    *,
    seed: int,
) -> tuple[dict[str, pl.DataFrame], list[dict], pl.DataFrame, list[dict]]:
    variant_rows = {variant: [] for variant in VARIANTS}
    metrics = []
    weight_rows = []
    prediction_rows = []
    for fold in FOLDS:
        training = (
            build_market_targets(
                panel,
                start=fold["train_start"],
                end=fold["train_end"],
                train_end=fold["train_end"],
            )
            .join(market, on="date", how="left")
            .with_columns(
                pl.col("market_target_return")
                .clip(TARGET_CLIP_LOWER, TARGET_CLIP_UPPER)
                .alias("_target_return"),
            )
        )
        test = build_market_targets(
            panel,
            start=fold["test_start"],
            end=fold["test_end"],
        ).join(market, on="date", how="left")
        if training.height < MIN_TRAIN_ROWS:
            raise ValueError(f"Too few market rows in {fold['name']}: {training.height}")
        if test.is_empty():
            raise ValueError(f"No market test rows in {fold['name']}")
        model = fit_market_ridge(training)
        train_prediction = predict_market_ridge(training, model)
        test_prediction = predict_market_ridge(test, model)
        training_threshold = float(np.quantile(train_prediction, 0.50))
        training_alpha = estimate_training_alpha(
            panel,
            factor_ids,
            fold,
            seed=seed,
        )
        test = test.with_columns(
            pl.Series("market_prediction", test_prediction),
        )
        fold_base = (
            base.filter(pl.col("fold") == fold["name"])
            .join(
                test.select(*GROUP_KEYS, "market_prediction"),
                on=GROUP_KEYS,
                how="left",
            )
            .sort(["fold", "_selection_order"])
        )
        if fold_base.filter(pl.col("market_prediction").is_null()).height:
            raise ValueError(f"Missing market predictions for {fold['name']}")
        variants = {
            "always_full": fold_base,
            "trend_vol_gate": fold_base.filter(
                pl.col("trend_gate") & pl.col("vol_gate"),
            ),
            "market_positive_gate": fold_base.filter(
                pl.col("market_prediction") > 0,
            ),
            "market_top50_gate": fold_base.filter(
                pl.col("market_prediction") >= training_threshold,
            ),
            "market_plus_alpha_gate": fold_base.filter(
                pl.col("market_prediction") + training_alpha > 0,
            ),
        }
        for variant, selected in variants.items():
            variant_rows[variant].append(selected)
        target = test["market_target_return"].to_numpy()
        metrics.append({
            "fold": fold["name"],
            "train_n": training.height,
            "test_n": test.height,
            "train_target_mean": float(training["_target_return"].mean()),
            "test_target_mean": float(test["market_target_return"].mean()),
            "train_ic": rank_correlation(
                training["_target_return"].to_numpy(),
                train_prediction,
            ),
            "test_ic": rank_correlation(target, test_prediction),
            "test_sign_accuracy": float(
                ((test_prediction > 0) == (target > 0)).mean(),
            ),
            "test_predicted_positive_share": float((test_prediction > 0).mean()),
            "training_top50_threshold": training_threshold,
            "training_selection_alpha": training_alpha,
        })
        for feature, coefficient in zip(FEATURES, model["beta"][1:], strict=True):
            weight_rows.append({
                "fold": fold["name"],
                "feature": feature,
                "coefficient": float(coefficient),
            })
        prediction_rows.extend({
            "fold": fold["name"],
            "date": row["date"],
            "gap_bucket": row["gap_bucket"],
            "market_target_return": row["market_target_return"],
            "market_prediction": row["market_prediction"],
        } for row in test.select(
            "date",
            "gap_bucket",
            "market_target_return",
            "market_prediction",
        ).to_dicts())
    variants = {
        variant: pl.concat(rows)
        for variant, rows in variant_rows.items()
    }
    return variants, metrics, pl.DataFrame(weight_rows), prediction_rows


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
    *,
    session_count: int,
) -> dict:
    selected_n = variants[PRIMARY_VARIANT].height
    event = next(row for row in events if row["variant"] == PRIMARY_VARIANT)
    interval = (event.get("cluster_bootstrap_95") or {}).get(
        "mean_incremental_return",
    )
    result = portfolio[PRIMARY_VARIANT]["oos"]
    checks = {
        "minimum_selected_events": selected_n >= DECISION_GATE["minimum_selected_events"],
        "mean_daily_candidates": (
            selected_n / session_count <= DECISION_GATE["maximum_mean_daily_candidates"]
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
        "checks": checks,
        "passed": all(checks.values()),
    }


def write_results(path: Path, report: dict) -> None:
    lines = [
        "# Market absolute-return gate",
        "",
        f"Algorithm: `{VERSION}`.",
        "",
        "The D+5 market baseline is predicted from completed D-1 index features.",
        "",
        "| Fold | Train | Test | Test mean | Test IC | Sign accuracy | Positive share |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["model_metrics"]:
        lines.append(
            f"| {row['fold']} | {row['train_n']} | {row['test_n']} | "
            f"{row['test_target_mean'] * 100:.3f}% | "
            f"{_format_optional(row['test_ic'])} | "
            f"{row['test_sign_accuracy'] * 100:.2f}% | "
            f"{row['test_predicted_positive_share'] * 100:.2f}% |",
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
    base = load_base(args.selected)
    start_date = min(panel["date"].min(), base["date"].min())
    end_date = max(panel["date"].max(), base["date"].max())
    market = build_market_features(args.data_dir, start_date, end_date)
    variants, metrics, weights, predictions = fit_fold_models(
        panel,
        base,
        market,
        factor_ids,
        seed=args.seed,
    )
    symbols = sorted(set(variants["always_full"]["symbol"].to_list()))
    calendar = load_calendar(
        args.data_dir,
        variants["always_full"]["date"].min(),
        variants["always_full"]["exit_date"].max(),
    )
    daily_closes = load_daily_closes(
        args.data_dir,
        symbols,
        variants["always_full"]["date"].min(),
        variants["always_full"]["exit_date"].max(),
    )
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
        session_count=session_count,
    )
    elapsed = round(time.perf_counter() - started, 3)
    report = {
        "version": VERSION,
        "primary_variant": PRIMARY_VARIANT,
        "variants": VARIANTS,
        "target": {
            "name": "d5_market_baseline_return",
            "clip_lower": TARGET_CLIP_LOWER,
            "clip_upper": TARGET_CLIP_UPPER,
        },
        "model": {
            "type": "ridge",
            "alpha": RIDGE_ALPHA,
            "features": FEATURES,
        },
        "model_metrics": metrics,
        "decision_gate": gate,
        "events": events,
        "portfolio": portfolio,
        "session_count": session_count,
        "portfolio_defaults": PORTFOLIO_DEFAULTS,
        "elapsed_seconds": elapsed,
        "warnings": [
            "Market targets use matured D+5 baseline returns only in training.",
            "All market features are shifted by one completed index session.",
            "The positive cutoff is fixed at zero and is not tuned on test folds.",
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
    pl.DataFrame(metrics, infer_schema_length=None).write_csv(
        args.output / "model_metrics.csv",
    )
    weights.write_csv(args.output / "weights.csv")
    pl.DataFrame(predictions, infer_schema_length=None).write_csv(
        args.output / "market_predictions.csv",
    )
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
    result = report["portfolio"][report["primary_variant"]]["oos"]
    print(json.dumps({
        "event": "complete",
        "primary": report["primary_variant"],
        "gate_passed": report["decision_gate"]["passed"],
        "portfolio_return": result["total_return"],
        "selected_n": event["selected_n"],
    }), flush=True)


if __name__ == "__main__":
    main()
