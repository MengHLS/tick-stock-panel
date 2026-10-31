"""Evaluate frozen first-board rules without reselecting thresholds."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from app.custom.firstboard_discovery.discovery import score_factor

RULE_SPECS = (
    {
        "id": "fbr_8ec1acf01a4c",
        "factor_id": "boll_width",
        "snapshot": "D_minus_1",
        "threshold": 0.41986322631304357,
    },
    {
        "id": "fbr_1dceb235c44f",
        "factor_id": "boll_width",
        "snapshot": "D_close",
        "threshold": 0.4548727152548999,
    },
)
SAME_FAMILY = (
    ("boll_width", "D_minus_1"),
    ("boll_width", "D_close"),
    ("atr_pct", "D_minus_1"),
    ("atr_pct", "D_close"),
    ("annual_vol_20d", "D_minus_1"),
    ("annual_vol_20d", "D_close"),
    ("amplitude_trend_20_60", "D_minus_1"),
    ("amplitude_trend_20_60", "D_close"),
)
HORIZONS = (5, 10, 20)


def evaluate_rule(
    events: pl.DataFrame,
    rule: dict[str, Any],
    *,
    validation_start: date,
    validation_end: date,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    column = f"{rule['snapshot']}__{rule['factor_id']}"
    validation = events.filter(
        pl.col("date").is_between(validation_start, validation_end)
        & pl.col("strong").is_not_null(),
    )
    evaluated = validation.with_columns(
        (
            pl.col(column).is_not_null()
            & pl.col(column).is_finite()
            & (pl.col(column) >= rule["threshold"])
        ).alias("_hit"),
        pl.col("strong").cast(pl.Int64).alias("_strong"),
    ).with_columns(pl.col("_hit").cast(pl.Int64).alias("_hit_int"))
    daily = evaluated.group_by("date").agg(
        pl.len().alias("n"),
        pl.col("_strong").sum().alias("strong_n"),
        pl.col("_hit_int").sum().alias("hit_n"),
        (pl.col("_hit_int") * pl.col("_strong")).sum().alias("hit_strong_n"),
        *[
            pl.when(pl.col("_hit")).then(pl.col(f"{metric}_{horizon}d"))
            .otherwise(None).sum().alias(f"{metric}_{horizon}d_sum")
            for metric in ("mfe", "close_return", "mae")
            for horizon in HORIZONS
        ],
        *[
            pl.when(pl.col("_hit")).then(pl.col(f"{metric}_{horizon}d").is_not_null())
            .otherwise(False).sum().alias(f"{metric}_{horizon}d_n")
            for metric in ("mfe", "close_return", "mae")
            for horizon in HORIZONS
        ],
    ).sort("date")

    columns = {
        name: daily[name].to_numpy().astype(float)
        for name in daily.columns
        if name != "date"
    }
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, daily.height, size=(bootstrap_samples, daily.height))

    def point_metrics(counts: dict[str, np.ndarray]) -> dict[str, float | None]:
        n = float(counts["n"].sum())
        strong_n = float(counts["strong_n"].sum())
        hit_n = float(counts["hit_n"].sum())
        hit_strong_n = float(counts["hit_strong_n"].sum())
        base = strong_n / n if n else None
        rate = hit_strong_n / hit_n if hit_n else None
        return {
            "n": n,
            "hit_n": hit_n,
            "coverage": hit_n / n if n else None,
            "base_strong_rate": base,
            "hit_strong_rate": rate,
            "lift": rate / base if rate is not None and base else None,
            "rate_difference": rate - base if rate is not None and base is not None else None,
            **{
                f"mean_{metric}_{horizon}d": (
                    float(counts[f"{metric}_{horizon}d_sum"].sum())
                    / float(counts[f"{metric}_{horizon}d_n"].sum())
                    if counts[f"{metric}_{horizon}d_n"].sum()
                    else None
                )
                for metric in ("mfe", "close_return", "mae")
                for horizon in HORIZONS
            },
        }

    point = point_metrics(columns)
    base_metrics = {
        f"mean_{metric}_{horizon}d": _mean(evaluated, f"{metric}_{horizon}d")
        for metric in ("mfe", "close_return", "mae")
        for horizon in HORIZONS
    }
    point["incremental_vs_base"] = {
        name: (
            point[name] - value
            if point.get(name) is not None and value is not None
            else None
        )
        for name, value in base_metrics.items()
    }
    point["base"] = base_metrics
    sampled = {
        name: values[indices].sum(axis=1)
        for name, values in columns.items()
    }
    sampled_n = sampled["n"]
    sampled_base = np.divide(
        sampled["strong_n"], sampled_n,
        out=np.full_like(sampled_n, np.nan), where=sampled_n > 0,
    )
    sampled_rate = np.divide(
        sampled["hit_strong_n"], sampled["hit_n"],
        out=np.full_like(sampled_n, np.nan), where=sampled["hit_n"] > 0,
    )
    bootstrap = {
        "hit_strong_rate": _interval(sampled_rate),
        "lift": _interval(np.divide(
            sampled_rate, sampled_base,
            out=np.full_like(sampled_rate, np.nan), where=sampled_base > 0,
        )),
        "rate_difference": _interval(sampled_rate - sampled_base),
        **{
            f"mean_{metric}_{horizon}d": _interval(np.divide(
                sampled[f"{metric}_{horizon}d_sum"],
                sampled[f"{metric}_{horizon}d_n"],
                out=np.full_like(sampled_n, np.nan),
                where=sampled[f"{metric}_{horizon}d_n"] > 0,
            ))
            for metric in ("mfe", "close_return", "mae")
            for horizon in HORIZONS
        },
    }

    yearly = []
    for year in sorted(evaluated["date"].dt.year().unique().to_list()):
        frame = evaluated.filter(pl.col("date").dt.year() == year)
        hits = frame.filter(pl.col("_hit"))
        yearly.append({
            "year": int(year),
            "n": frame.height,
            "hit_n": hits.height,
            "base_strong_rate": _ratio(frame),
            "hit_strong_rate": _ratio(hits),
            "lift": _safe_lift(_ratio(hits), _ratio(frame)),
            "mean_mfe_20d": _mean(hits, "mfe_20d"),
            "mean_close_return_20d": _mean(hits, "close_return_20d"),
            "mean_mae_20d": _mean(hits, "mae_20d"),
        })

    sensitivity = []
    for multiplier in (0.9, 0.95, 1.0, 1.05, 1.1):
        threshold = float(rule["threshold"]) * multiplier
        hits = evaluated.filter(
            pl.col(column).is_not_null()
            & pl.col(column).is_finite()
            & (pl.col(column) >= threshold)
        )
        sensitivity.append({
            "threshold_multiplier": multiplier,
            "threshold": threshold,
            "hit_n": hits.height,
            "hit_strong_rate": _ratio(hits),
            "lift": _safe_lift(_ratio(hits), _ratio(evaluated)),
        })

    return {
        "rule": rule,
        "validation_start": validation_start.isoformat(),
        "validation_end": validation_end.isoformat(),
        "event_days": daily.height,
        "bootstrap_samples": bootstrap_samples,
        "point": point,
        "cluster_bootstrap_95": bootstrap,
        "yearly": yearly,
        "threshold_sensitivity": sensitivity,
    }


def same_family_scores(
    events: pl.DataFrame,
    *,
    validation_start: date,
    validation_end: date,
) -> list[dict[str, Any]]:
    validation = events.filter(
        pl.col("date").is_between(validation_start, validation_end)
        & pl.col("strong").is_not_null(),
    )
    labels = validation["strong"].to_list()
    rows = []
    for factor_id, snapshot in SAME_FAMILY:
        column = f"{snapshot}__{factor_id}"
        score = score_factor(factor_id, snapshot, validation[column].to_list(), labels)
        rows.append({
            "factor_id": factor_id,
            "snapshot": snapshot,
            "auc": score.auc,
            "coverage": score.coverage,
            "n": score.train_count,
        })
    return rows


def _ratio(frame: pl.DataFrame) -> float | None:
    values = frame["strong"].drop_nulls().cast(pl.Float64)
    return float(values.mean()) if values.len() else None


def _mean(frame: pl.DataFrame, column: str) -> float | None:
    values = frame[column].drop_nulls()
    return float(values.mean()) if values.len() else None


def _safe_lift(rate: float | None, base: float | None) -> float | None:
    return rate / base if rate is not None and base not in (None, 0) else None


def _interval(values: np.ndarray) -> list[float] | None:
    finite = values[np.isfinite(values)]
    if not finite.size:
        return None
    low, high = np.quantile(finite, [0.025, 0.975])
    return [float(low), float(high)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20261030)
    parser.add_argument("--evaluation-start", type=date.fromisoformat)
    parser.add_argument("--evaluation-end", type=date.fromisoformat)
    args = parser.parse_args()

    report = json.loads((args.run_dir / "report.json").read_text(encoding="utf-8"))
    events = pl.read_parquet(args.run_dir / "events.parquet")
    validation_start = (
        args.evaluation_start
        or date.fromisoformat(report["split"]["validation_start"])
    )
    validation_end = (
        args.evaluation_end
        or date.fromisoformat(report["split"]["validation_end"])
    )
    payload = {
        "source_run_id": report["run_id"],
        "source_algorithm_version": report["algorithm_version"],
        "source_generation": report["generation"],
        "validation_start": validation_start.isoformat(),
        "validation_end": validation_end.isoformat(),
        "bootstrap_unit": "event_date",
        "bootstrap_samples": args.bootstrap_samples,
        "seed": args.seed,
        "frozen_rules": [
            evaluate_rule(
                events,
                rule,
                validation_start=validation_start,
                validation_end=validation_end,
                bootstrap_samples=args.bootstrap_samples,
                seed=args.seed + index,
            )
            for index, rule in enumerate(RULE_SPECS)
        ],
        "same_family": same_family_scores(
            events,
            validation_start=validation_start,
            validation_end=validation_end,
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
