"""Two-sided tail factor test on the 331 first-board pullback pool.

Right tail: MFE >= 20% within 20 sessions from the next-day open.
Left tail: -6% stop touched, and MAE <= -10% within the same window.
Candidate features are known at the T close (3F score, amplitude, volume,
pullback) or at the T+1 auction (gap, imbalance, tail price change, auction
volume). Development (2020-2022) fits the deciles and the logistic models;
validation (2023-2024) and stress (2025-2026H1) only evaluate them.

Usage (from backend/):
    uv run python scripts/firstboard_tail_factor.py \
        --data-dir ../data --minute-dir /path/to/mint-5 \
        --reuse-dir ../.artifacts/firstboard_auction_tail \
        --output ../.artifacts/firstboard_tail_factor
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl
from firstboard_auction_tail_study import (
    SESSIONS,
    STOP,
    TAIL,
    aggregate,
    attach_features,
    bootstrap_diff,
    build_events,
)

VERSION = "firstboard-tail-factor-v2"
PERIODS = ("development", "validation", "stress", "extension")
TARGETS = {
    "right": "tail20",
    "left_stop": "stop6",
    "left_mae": "mae10",
}
FACTORS = (
    "score",
    "max_amplitude",
    "mean_amplitude",
    "volume_ratio",
    "pullback",
    "entry_open_gap",
    "last_imbalance",
    "last_minute_price_change",
    "last_minute_matched_growth",
    "vol_vs_prev",
    "tail_strength",
    "bar_ret",
)
AUCTION_FEATURES = (
    "entry_open_gap",
    "vol_vs_prev",
    "last_minute_price_change",
    "last_imbalance",
)
MODELS = {
    "amplitude": ("mean_amplitude",),
    "auction": AUCTION_FEATURES,
    "combined": ("mean_amplitude", *AUCTION_FEATURES),
}


def load_events(
    data_dir: Path,
    minute_dir: Path,
    reuse_dir: Path | None,
    output: Path,
    start_year: int,
    end_year: int,
) -> pl.DataFrame:
    """Reuse an existing event panel or rebuild it with the study helpers."""
    if reuse_dir is not None and (reuse_dir / "events_aggregated.parquet").exists():
        return pl.read_parquet(reuse_dir / "events_aggregated.parquet")
    output.mkdir(parents=True, exist_ok=True)
    events_path = output / "events.parquet"
    if events_path.exists():
        events = pl.read_parquet(events_path)
    else:
        events = build_events(data_dir, start_year, end_year)
        events.write_parquet(events_path)
    panel_path = output / "panel.parquet"
    if panel_path.exists():
        panel = pl.read_parquet(panel_path)
    else:
        panel = attach_features(data_dir, minute_dir, events, panel_path)
    return aggregate(panel)


def prepare(aggregated: pl.DataFrame) -> pl.DataFrame:
    """Build the executable pool with the within-day TailStrength ranks."""
    frame = aggregated.filter(
        pl.col("gap_ok")
        & pl.col("prev_change_ok")
        & pl.col("not_limit_open")
        & pl.col("mfe20").is_not_null()
        & (pl.col("k_max") >= SESSIONS)
        & (pl.col("has_result") == 1)
        & (pl.col("auction_open") > 0)
    ).with_columns(
        pl.col("tail20").cast(pl.Int8),
        pl.col("first_stop_k").is_not_null().cast(pl.Int8).alias("stop6"),
        (pl.col("mae20") <= -0.10).cast(pl.Int8).alias("mae10"),
        pl.len().over("signal_date").alias("day_n"),
    )
    ranked = frame.filter(pl.col("day_n") >= 4)
    ranks = []
    for feature, alias in (
        ("last_minute_price_change", "rank_price"),
        ("last_minute_matched_growth", "rank_growth"),
        ("last_imbalance", "rank_imbalance"),
    ):
        ranks.append(
            (pl.col(feature).rank(method="average").over("signal_date") / pl.col("day_n")).alias(
                alias
            )
        )
    ranked = ranked.with_columns(ranks)
    ranked = ranked.with_columns(
        ((pl.col("rank_price") + pl.col("rank_growth") + pl.col("rank_imbalance")) / 3.0).alias(
            "tail_strength"
        )
    )
    return frame.join(
        ranked.select("symbol", "signal_date", "tail_strength"),
        on=("symbol", "signal_date"),
        how="left",
    )


def _rankdata(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    starts = np.r_[True, sorted_values[1:] != sorted_values[:-1]]
    group = np.cumsum(starts) - 1
    counts = np.bincount(group)
    cumulative = np.cumsum(counts)
    average = (cumulative - counts + 1 + cumulative) / 2.0
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = average[group]
    return ranks


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx = _rankdata(x)
    ry = _rankdata(y)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    denom = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return float((rx * ry).sum() / denom) if denom > 0 else 0.0


def _auc(y: np.ndarray, score: np.ndarray) -> float:
    positives = int(y.sum())
    negatives = len(y) - positives
    if positives == 0 or negatives == 0:
        return 0.5
    ranks = _rankdata(score)
    return float(
        (ranks[y == 1].sum() - positives * (positives + 1) / 2.0) / (positives * negatives)
    )


def _day_slices(days: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
    unique, inverse = np.unique(days, return_inverse=True)
    order = np.argsort(inverse, kind="stable")
    bounds = np.searchsorted(inverse[order], np.arange(len(unique)))
    rows = [
        order[bounds[i] : (bounds[i + 1] if i + 1 < len(unique) else len(order))]
        for i in range(len(unique))
    ]
    return unique, rows


def _auc_ci(
    y: np.ndarray,
    score: np.ndarray,
    days: np.ndarray,
    samples: int,
    seed: int,
) -> tuple[float, float]:
    unique, rows = _day_slices(days)
    rng = np.random.default_rng(seed)
    values = np.empty(samples)
    for i in range(samples):
        draw = rng.integers(0, len(unique), len(unique))
        index = np.concatenate([rows[j] for j in draw])
        values[i] = _auc(y[index], score[index])
    low, high = np.percentile(values, [2.5, 97.5])
    return float(low), float(high)


def _auc_diff_ci(
    y: np.ndarray,
    score_a: np.ndarray,
    score_b: np.ndarray,
    days: np.ndarray,
    samples: int,
    seed: int,
) -> tuple[float, float, float]:
    unique, rows = _day_slices(days)
    rng = np.random.default_rng(seed)
    observed = _auc(y, score_a) - _auc(y, score_b)
    values = np.empty(samples)
    for i in range(samples):
        draw = rng.integers(0, len(unique), len(unique))
        index = np.concatenate([rows[j] for j in draw])
        values[i] = _auc(y[index], score_a[index]) - _auc(y[index], score_b[index])
    low, high = np.percentile(values, [2.5, 97.5])
    return float(observed), float(low), float(high)


def _fit_logistic(x: np.ndarray, y: np.ndarray, ridge: float = 1e-4, iterations: int = 50):
    design = np.column_stack([np.ones(len(x)), x])
    beta = np.zeros(design.shape[1])
    for _ in range(iterations):
        eta = np.clip(design @ beta, -30, 30)
        p = 1.0 / (1.0 + np.exp(-eta))
        weight = np.clip(p * (1.0 - p), 1e-8, None)
        gradient = design.T @ (y - p) - ridge * beta
        hessian = (design * weight[:, None]).T @ design + ridge * np.eye(design.shape[1])
        step = np.linalg.solve(hessian, gradient)
        beta += step
        if np.max(np.abs(step)) < 1e-9:
            break
    return beta


def _standardize(frame: pl.DataFrame, features: tuple[str, ...]):
    stats = {}
    for feature in features:
        values = frame[feature].to_numpy().astype(float)
        values = values[np.isfinite(values)]
        low, high = np.percentile(values, [1, 99])
        stats[feature] = {
            "mean": float(values.mean()),
            "std": float(values.std()) or 1.0,
            "low": float(low),
            "high": float(high),
        }
    return stats


def _matrix(frame: pl.DataFrame, features: tuple[str, ...], stats: dict) -> np.ndarray:
    columns = []
    for feature in features:
        st = stats[feature]
        values = frame[feature].to_numpy().astype(float)
        values = np.where(np.isfinite(values), values, st["mean"])
        values = np.clip(values, st["low"], st["high"])
        columns.append((values - st["mean"]) / st["std"])
    return np.column_stack(columns)


def univariate(frame: pl.DataFrame, target: str) -> list[dict]:
    development = frame.filter(pl.col("period") == "development")
    rows = []
    for factor in FACTORS:
        thresholds = np.percentile(
            development[factor].drop_nulls().to_numpy().astype(float), [10, 90]
        )
        for period in ("development", "validation", "stress"):
            sub = frame.filter((pl.col("period") == period) & pl.col(factor).is_not_null())
            if sub.height < 100:
                continue
            x = sub[factor].to_numpy().astype(float)
            y = sub[target].to_numpy().astype(int)
            rows.append(
                {
                    "target": target,
                    "factor": factor,
                    "period": period,
                    "n": sub.height,
                    "ic": _spearman(x, y),
                    "auc": _auc(y, x),
                    "rate_low": float(y[x <= thresholds[0]].mean()),
                    "rate_high": float(y[x >= thresholds[1]].mean()),
                    "n_low": int((x <= thresholds[0]).sum()),
                    "n_high": int((x >= thresholds[1]).sum()),
                }
            )
    return rows


def models(frame: pl.DataFrame, target: str, samples: int, seed: int) -> dict:
    development = frame.filter(pl.col("period") == "development")
    fitted: dict[str, tuple[dict, np.ndarray]] = {}
    results: dict[str, dict] = {}
    for name, features in MODELS.items():
        stats = _standardize(development, features)
        fit_rows = development.filter(
            pl.all_horizontal([pl.col(f).is_not_null() for f in features])
        )
        x_fit = _matrix(fit_rows, features, stats)
        y_fit = fit_rows[target].to_numpy().astype(int)
        beta = _fit_logistic(x_fit, y_fit)
        fitted[name] = (stats, beta)
        probability_fit = _predict(fit_rows, features, stats, beta)
        threshold = float(np.percentile(probability_fit, 0.90))
        model_result = {
            "features": list(features),
            "n_fit": fit_rows.height,
            "coefficients": {
                "(intercept)": float(beta[0]),
                **{
                    feature: float(value) for feature, value in zip(features, beta[1:], strict=True)
                },
            },
            "threshold_dev_p90": threshold,
            "periods": {},
        }
        for period in ("development", "validation", "stress"):
            sub = frame.filter(
                (pl.col("period") == period)
                & pl.all_horizontal([pl.col(f).is_not_null() for f in features])
            )
            if sub.height < 100:
                continue
            probability = _predict(sub, features, stats, beta)
            y = sub[target].to_numpy().astype(int)
            days = sub["date_str"].to_numpy()
            auc = _auc(y, probability)
            auc_low, auc_high = _auc_ci(y, probability, days, samples, seed)
            top = probability >= np.percentile(probability, 90)
            bottom = probability <= np.percentile(probability, 10)
            diff_top, top_low, top_high = bootstrap_diff(
                days, y.astype(float), top, samples=samples, seed=seed
            )
            diff_bottom, bottom_low, bottom_high = bootstrap_diff(
                days, y.astype(float), bottom, samples=samples, seed=seed
            )
            model_result["periods"][period] = {
                "n": sub.height,
                "auc": auc,
                "auc_low": auc_low,
                "auc_high": auc_high,
                "top": {
                    "n": int(top.sum()),
                    "rate": float(y[top].mean()) if top.any() else None,
                    "rest": float(y[~top].mean()) if (~top).any() else None,
                    "diff": diff_top,
                    "ci_low": top_low,
                    "ci_high": top_high,
                },
                "bottom": {
                    "n": int(bottom.sum()),
                    "rate": float(y[bottom].mean()) if bottom.any() else None,
                    "rest": float(y[~bottom].mean()) if (~bottom).any() else None,
                    "diff": diff_bottom,
                    "ci_low": bottom_low,
                    "ci_high": bottom_high,
                },
            }
        results[name] = model_result
    comparisons = {}
    for period in ("validation", "stress"):
        sub = frame.filter(
            (pl.col("period") == period)
            & pl.all_horizontal([pl.col(f).is_not_null() for f in MODELS["combined"]])
        )
        if sub.height < 100:
            continue
        y = sub[target].to_numpy().astype(int)
        days = sub["date_str"].to_numpy()
        probabilities = {
            name: _predict(sub, features, *fitted[name]) for name, features in MODELS.items()
        }
        for better, base in (
            ("combined", "amplitude"),
            ("combined", "auction"),
            ("amplitude", "auction"),
        ):
            observed, low, high = _auc_diff_ci(
                y, probabilities[better], probabilities[base], days, samples, seed
            )
            comparisons[f"{better}_vs_{base}_{period}"] = {
                "auc_diff": observed,
                "ci_low": low,
                "ci_high": high,
                "n": sub.height,
            }
    deciles = []
    for period in ("development", "validation", "stress"):
        sub = frame.filter(
            (pl.col("period") == period)
            & pl.all_horizontal([pl.col(f).is_not_null() for f in MODELS["combined"]])
        )
        if sub.height < 100:
            continue
        probability = _predict(sub, MODELS["combined"], *fitted["combined"])
        edges = np.percentile(probability, np.arange(10, 100, 10))
        bucket = 1 + np.searchsorted(edges, probability, side="right")
        y = sub[target].to_numpy().astype(float)
        for value in range(1, 11):
            mask = bucket == value
            if not mask.any():
                continue
            deciles.append(
                {
                    "period": period,
                    "decile": value,
                    "n": int(mask.sum()),
                    "predicted": float(probability[mask].mean()),
                    "observed": float(y[mask].mean()),
                }
            )
    return {
        "models": results,
        "comparisons": comparisons,
        "deciles": deciles,
    }


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -30, 30)))


def _predict(
    sub: pl.DataFrame, features: tuple[str, ...], stats: dict, beta: np.ndarray
) -> np.ndarray:
    x = _matrix(sub, features, stats)
    return _sigmoid(np.column_stack([np.ones(len(x)), x]) @ beta)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--minute-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-dir", type=Path, default=None)
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    aggregated = load_events(
        args.data_dir,
        args.minute_dir,
        args.reuse_dir,
        args.output,
        args.start_year,
        args.end_year,
    )
    frame = prepare(aggregated)
    results = {
        "version": VERSION,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "tail_threshold": TAIL,
        "stop_threshold": STOP,
        "sessions": SESSIONS,
        "sample": {
            "total": frame.height,
            "by_period": {
                row["period"]: row["len"]
                for row in frame.group_by("period").len().sort("period").to_dicts()
            },
            "left_tail_rates": {
                row["period"]: {"stop6": row["stop6"], "mae10": row["mae10"]}
                for row in (
                    frame.group_by("period")
                    .agg(
                        pl.col("stop6").mean().alias("stop6"),
                        pl.col("mae10").mean().alias("mae10"),
                    )
                    .sort("period")
                    .to_dicts()
                )
            },
        },
        "targets": {},
        "warnings": [
            "Conditional event study; tail probabilities are not tradable returns.",
            "Deciles and logistic coefficients are fitted on 2020-2022 only.",
            "Univariate IC/AUC are descriptive; only the model comparisons are inferential.",
            "2026-07 auction partitions are missing; extension is 2026-08/09 only.",
            "AUC/rate differences use day-clustered bootstrap intervals.",
        ],
    }
    for name, target in TARGETS.items():
        results["targets"][name] = {
            "label": target,
            "univariate": univariate(frame, target),
            **models(frame, target, args.bootstrap_samples, 20261101),
        }
    (args.output / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    for name, target in TARGETS.items():
        print(name, target)
        for model_name, model in results["targets"][name]["models"].items():
            for period, row in model["periods"].items():
                if period == "development":
                    continue
                print(
                    f"  {model_name:9s} {period:10s} auc={row['auc']:.3f} "
                    f"top={row['top']['rate']:.3f}/{row['top']['rest']:.3f} "
                    f"bottom={row['bottom']['rate']:.3f}/{row['bottom']['rest']:.3f}"
                )


if __name__ == "__main__":
    main()
