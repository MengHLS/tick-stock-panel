"""Development-only multifactor ranking for the auction 2%-8% gap bucket.

The input event table already contains D-1 factors and frozen TailStrength
auction fields. This script ranks factors only within the same date and gap
bucket, admits and clusters them using development data only, then evaluates
the frozen composite on validation and retrospective stress periods.
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

from scripts.auction_high_open_study import (
    PERIODS,
    PORTFOLIO_DEFAULTS,
    _write_json,
    simulate_signal_portfolio,
    summarize,
)

VERSION = "auction-multifactor-v1"
KEYS = ["symbol", "date"]
GROUPS = ["date", "gap_bucket"]
MAIN_BUCKETS = ["2-4", "4-6", "6-8"]
SELECTION = {
    "scope": "development only",
    "minimum_coverage": 0.70,
    "minimum_abs_mean_ic": 0.015,
    "minimum_abs_icir": 0.10,
    "minimum_rank_ic_observations": 8,
    "minimum_dev_years": 2,
    "correlation_threshold": 0.80,
    "correlation_sample_rows": 250_000,
    "minimum_correlation_overlap": 5_000,
    "minimum_representative_coverage": 0.75,
    "top_quantile": 0.70,
    "tail_weight": 0.50,
}
VARIANTS = {
    "risk_composite_top30": {
        "signal_column": "_risk_signal",
        "score_column": "risk_rank",
    },
    "tail_plus_risk_intersection": {
        "signal_column": "_tail_risk_intersection",
        "score_column": "risk_rank",
    },
    "tail_plus_risk_blend_top30": {
        "signal_column": "_tail_risk_blend",
        "score_column": "combined_rank",
    },
    "tail_strength_v1": {
        "signal_column": "tail_strength_signal",
        "score_column": "tail_strength_score",
        "rank_column": "tail_strength_rank",
    },
}
PRIMARY_VARIANT = "tail_plus_risk_blend_top30"
DECISION_GATE = {
    "periods": ["validation", "retrospective_stress"],
    "mean_net_return_positive": True,
    "incremental_ci_lower_positive": True,
    "portfolio_total_return_positive": True,
    "portfolio_max_drawdown_floor": -0.15,
}


def _finite(column: str) -> pl.Expr:
    value = pl.col(column)
    return pl.when(value.is_not_null() & value.is_finite()).then(value).otherwise(None)


def load_factor_ids(admission_path: Path) -> tuple[list[str], dict[str, str]]:
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    factor_ids = admission["factor_info"]["available_factor_ids"]
    groups = {
        row["factor_id"]: row.get("group", "")
        for row in admission["factors"]
    }
    return factor_ids, groups


def load_events(events_path: Path, factor_ids: list[str]) -> pl.DataFrame:
    factor_columns = [f"factor__{factor_id}" for factor_id in factor_ids]
    required = [
        *KEYS,
        "gap_bucket",
        "horizon",
        "signal_eligible",
        "tail_strength_signal",
        "tail_strength_score",
        "tail_strength_rank",
        "entry_reason",
        "exit_reason",
        "entry_vwap",
        "entry_volume",
        "exit_date",
        "net_return",
        *factor_columns,
    ]
    frame = (
        pl.scan_parquet(events_path)
        .filter(
            (pl.col("horizon") == 3)
            & pl.col("gap_bucket").is_in(MAIN_BUCKETS)
            & pl.col("signal_eligible")
        )
        .select(required)
        .collect()
    )
    if frame.select(pl.struct(KEYS).is_duplicated().any()).item():
        raise ValueError("Duplicate event keys after 2%-8% filtering")
    return frame


def add_factor_ranks(frame: pl.DataFrame, factor_ids: list[str]) -> pl.DataFrame:
    normalized = frame.with_columns([
        _finite(f"factor__{factor_id}").alias(f"_value__{factor_id}")
        for factor_id in factor_ids
    ])
    expressions = []
    for factor_id in factor_ids:
        source = f"_value__{factor_id}"
        output = f"rank__{factor_id}"
        n = pl.col(source).count().over(GROUPS)
        expressions.append(
            pl.when(pl.col(source).is_null()).then(None)
            .when(n <= 1).then(0.5)
            .otherwise(
                (pl.col(source).rank("average").over(GROUPS) - 1) / (n - 1),
            )
            .alias(output),
        )
    temporary = [f"_value__{factor_id}" for factor_id in factor_ids]
    return normalized.with_columns(expressions).drop(temporary)


def _rank_ic(frame: pl.DataFrame, column: str) -> dict:
    source = _finite(column).alias("_x")
    residual = _finite("_residual").alias("_y")
    grouped = (
        frame.select("date", "gap_bucket", source, residual)
        .drop_nulls(["_x", "_y"])
        .with_columns(
            pl.len().over(GROUPS).alias("_n"),
            pl.col("_x").rank("average").over(GROUPS).alias("_rx"),
            pl.col("_y").rank("average").over(GROUPS).alias("_ry"),
        )
        .filter(pl.col("_n") >= SELECTION["minimum_rank_ic_observations"])
        .group_by(GROUPS)
        .agg(
            pl.len().alias("_group_n"),
            pl.corr("_rx", "_ry").alias("_ic"),
        )
        .drop_nulls("_ic")
        .filter(pl.col("_ic").is_finite())
    )
    if grouped.is_empty():
        return {
            "mean_ic": None,
            "icir": None,
            "positive_day_rate": None,
            "ic_days": 0,
            "event_days": 0,
            "groups": 0,
        }
    daily = (
        grouped.group_by("date")
        .agg(
            ((pl.col("_ic") * pl.col("_group_n")).sum() / pl.col("_group_n").sum())
            .alias("_ic"),
            pl.len().alias("_groups"),
        )
        .sort("date")
    )
    values = daily["_ic"]
    mean = float(values.mean())
    std = float(values.std(ddof=1)) if values.len() > 1 else None
    return {
        "mean_ic": mean,
        "icir": mean / std if std and std > 0 else None,
        "positive_day_rate": float((values > 0).mean()),
        "ic_days": int(values.len()),
        "event_days": int(daily.height),
        "groups": int(grouped.height),
    }


def factor_metrics(
    frame: pl.DataFrame,
    column: str,
    start: date,
    end: date,
) -> dict:
    period = frame.filter(pl.col("date").is_between(start, end))
    if period.is_empty():
        return {"status": "no_data", "n": 0, "event_days": 0}
    baseline = (
        period.select("date", "gap_bucket", column, "net_return")
        .with_columns(pl.col("net_return").median().over(GROUPS).alias("_baseline"))
        .with_columns((pl.col("net_return") - pl.col("_baseline")).alias("_residual"))
    )
    coverage = float(
        period.select(
            _finite(column).is_not_null().mean().alias("_coverage"),
        ).item(),
    )
    metrics = _rank_ic(baseline, column)
    yearly = []
    for year in sorted(period["date"].dt.year().unique().to_list()):
        year_frame = baseline.filter(pl.col("date").dt.year() == year)
        result = _rank_ic(year_frame, column)
        yearly.append({"year": int(year), **result})
    return {
        "status": "ok" if metrics["mean_ic"] is not None else "insufficient_cross_section",
        "n": period.height,
        "event_days": metrics["event_days"],
        "coverage": coverage,
        **metrics,
        "direction": (
            "high" if (metrics["mean_ic"] or 0) > 0
            else "low" if (metrics["mean_ic"] or 0) < 0
            else "none"
        ),
        "yearly": yearly,
    }


def admit_factors(
    frame: pl.DataFrame,
    factor_ids: list[str],
    factor_groups: dict[str, str],
) -> list[dict]:
    development = frame.filter(
        (pl.col("date").is_between(*PERIODS[0][1:]))
        & (pl.col("entry_reason") == "ok")
        & (pl.col("exit_reason") == "ok")
        & pl.col("net_return").is_finite()
    )
    admitted = []
    for factor_id in factor_ids:
        metrics = factor_metrics(
            development,
            f"rank__{factor_id}",
            PERIODS[0][1],
            PERIODS[0][2],
        )
        direction = metrics.get("direction")
        yearly_ic = [
            row["mean_ic"] for row in metrics.get("yearly", [])
            if row["mean_ic"] is not None
        ]
        same_sign = (
            len(yearly_ic) >= SELECTION["minimum_dev_years"]
            and all(
                (value > 0) == (direction == "high")
                for value in yearly_ic
            )
        )
        passed = (
            metrics["status"] == "ok"
            and metrics["coverage"] >= SELECTION["minimum_coverage"]
            and abs(metrics["mean_ic"] or 0) >= SELECTION["minimum_abs_mean_ic"]
            and abs(metrics["icir"] or 0) >= SELECTION["minimum_abs_icir"]
            and same_sign
        )
        admitted.append({
            "factor_id": factor_id,
            "group": factor_groups.get(factor_id, ""),
            "admitted": passed,
            "direction": direction,
            "sign": 1 if direction == "high" else -1 if direction == "low" else 0,
            "yearly_same_sign": same_sign,
            "metrics": metrics,
        })
    return admitted


def _correlation(
    matrix: np.ndarray,
    left: int,
    right: int,
) -> float | None:
    mask = np.isfinite(matrix[:, left]) & np.isfinite(matrix[:, right])
    if int(mask.sum()) < SELECTION["minimum_correlation_overlap"]:
        return None
    x = matrix[mask, left]
    y = matrix[mask, right]
    if float(x.std()) <= 0 or float(y.std()) <= 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def cluster_representatives(
    frame: pl.DataFrame,
    admitted: list[dict],
    *,
    seed: int,
) -> list[dict]:
    eligible = [row for row in admitted if row["admitted"]]
    if not eligible:
        raise ValueError("No factors passed development admission")
    sample = frame.filter(
        pl.col("date").is_between(*PERIODS[0][1:]),
    ).select([f"rank__{row['factor_id']}" for row in eligible])
    if sample.height > SELECTION["correlation_sample_rows"]:
        sample = sample.sample(
            SELECTION["correlation_sample_rows"],
            seed=seed,
        )
    matrix = sample.to_numpy().astype(float, copy=True)
    for index, row in enumerate(eligible):
        matrix[:, index] *= row["sign"]

    ordered = sorted(
        range(len(eligible)),
        key=lambda index: (
            -abs(eligible[index]["metrics"]["icir"] or 0),
            -abs(eligible[index]["metrics"]["mean_ic"] or 0),
            eligible[index]["factor_id"],
        ),
    )
    representatives: list[dict] = []
    for index in ordered:
        factor = eligible[index]
        best_cluster = None
        best_correlation = SELECTION["correlation_threshold"]
        for cluster_index, representative in enumerate(representatives):
            correlation = _correlation(matrix, representative["_matrix_index"], index)
            if correlation is not None and correlation >= best_correlation:
                best_correlation = correlation
                best_cluster = cluster_index
        if best_cluster is None:
            representatives.append({
                "factor_id": factor["factor_id"],
                "group": factor["group"],
                "direction": factor["direction"],
                "sign": factor["sign"],
                "metrics": factor["metrics"],
                "members": [factor["factor_id"]],
                "_matrix_index": index,
            })
        else:
            representatives[best_cluster]["members"].append(factor["factor_id"])
    for cluster in representatives:
        cluster["members"].sort()
        cluster.pop("_matrix_index")
    return representatives


def build_scores(frame: pl.DataFrame, representatives: list[dict]) -> pl.DataFrame:
    terms = []
    for cluster in representatives:
        terms.append(
            (_finite(f"rank__{cluster['factor_id']}") * cluster["sign"])
            .alias(f"_term__{cluster['factor_id']}"),
        )
    frame = frame.with_columns(terms)
    term_columns = [f"_term__{cluster['factor_id']}" for cluster in representatives]
    availability = pl.sum_horizontal(
        [pl.col(column).is_not_null().cast(pl.Int64) for column in term_columns],
    )
    frame = frame.with_columns(
        availability.alias("_risk_available"),
        (availability / len(term_columns)).alias("_risk_coverage"),
        pl.mean_horizontal(*[pl.col(column) for column in term_columns]).alias("risk_score"),
    )
    frame = frame.with_columns(
        pl.when(pl.col("_risk_coverage") < SELECTION["minimum_representative_coverage"])
        .then(None)
        .otherwise(pl.col("risk_score"))
        .alias("risk_score"),
    )
    n = pl.col("risk_score").count().over(GROUPS)
    frame = frame.with_columns(
        pl.when(pl.col("risk_score").is_null()).then(None)
        .when(n <= 1).then(0.5)
        .otherwise(
            (pl.col("risk_score").rank("average").over(GROUPS) - 1) / (n - 1),
        )
        .alias("risk_rank"),
    )
    combined = (
        SELECTION["tail_weight"] * pl.col("risk_rank")
        + (1 - SELECTION["tail_weight"]) * pl.col("tail_strength_rank")
    )
    frame = frame.with_columns(
        pl.when(
            pl.col("risk_rank").is_not_null()
            & pl.col("tail_strength_rank").is_not_null(),
        )
        .then(combined)
        .otherwise(None)
        .alias("combined_score"),
    )
    n = pl.col("combined_score").count().over(GROUPS)
    frame = frame.with_columns(
        pl.when(pl.col("combined_score").is_null()).then(None)
        .when(n <= 1).then(0.5)
        .otherwise(
            (pl.col("combined_score").rank("average").over(GROUPS) - 1) / (n - 1),
        )
        .alias("combined_rank"),
    )
    top = SELECTION["top_quantile"]
    return frame.with_columns(
        (
            (pl.col("_risk_coverage") >= SELECTION["minimum_representative_coverage"])
            & (pl.col("risk_rank") >= top)
        ).fill_null(False).alias("_risk_signal"),
        (
            pl.col("tail_strength_signal").fill_null(False)
            & (pl.col("risk_rank") >= top)
        ).fill_null(False).alias("_tail_risk_intersection"),
        (
            (pl.col("_risk_coverage") >= SELECTION["minimum_representative_coverage"])
            & pl.col("combined_rank").is_finite()
            & (pl.col("combined_rank") >= top)
        ).fill_null(False).alias("_tail_risk_blend"),
    ).drop(term_columns)


def _with_baseline(frame: pl.DataFrame) -> pl.DataFrame:
    resolved = frame.filter(
        (pl.col("entry_reason") == "ok")
        & (pl.col("exit_reason") == "ok")
        & pl.col("net_return").is_finite()
    )
    if resolved.is_empty():
        return resolved
    return resolved.with_columns(
        pl.col("net_return").mean().over(GROUPS).alias("_baseline"),
        (pl.col("net_return") > 0).mean().over(GROUPS).alias("_baseline_win"),
    ).with_columns(
        (pl.col("net_return") - pl.col("_baseline")).alias("incremental_return"),
        (
            (pl.col("net_return") > 0).cast(pl.Float64)
            - pl.col("_baseline_win")
        ).alias("win_increment"),
    )


def evaluate_variants(
    scored: pl.DataFrame,
    *,
    bootstrap_samples: int,
    seed: int,
) -> tuple[list[dict], dict]:
    results = []
    portfolio: dict[str, dict] = {}
    for period, start, end in PERIODS[:4]:
        period_frame = scored.filter(pl.col("date").is_between(start, end))
        if period_frame.is_empty():
            continue
        resolved = _with_baseline(period_frame)
        for variant, contract in VARIANTS.items():
            signal = pl.col(contract["signal_column"]).fill_null(False)
            scope = period_frame.filter(signal)
            selected = resolved.filter(signal)
            result = {
                "period": period,
                "variant": variant,
                "signal_n": scope.height,
                "entry_ok_n": scope.filter(pl.col("entry_reason") == "ok").height,
                "n": selected.height,
                "event_days": selected["date"].n_unique(),
                **summarize(
                    selected,
                    bootstrap_samples=bootstrap_samples,
                    seed=seed,
                ),
            }
            results.append(result)
            summary, _, _ = simulate_signal_portfolio(
                period_frame,
                start=start,
                end=end,
                signal_column=contract["signal_column"],
                score_column=contract["score_column"],
                rank_column=contract.get("rank_column"),
            )
            portfolio.setdefault(variant, {})[period] = summary
    return results, portfolio


def decision_gate(results: list[dict], portfolio: dict) -> dict:
    checks = {}
    for period in DECISION_GATE["periods"]:
        result = next(
            row for row in results
            if row["period"] == period and row["variant"] == PRIMARY_VARIANT
        )
        interval = result.get("cluster_bootstrap_95") or {}
        incremental = interval.get("mean_incremental_return")
        portfolio_result = portfolio[PRIMARY_VARIANT][period]
        checks[period] = {
            "mean_net_return_positive": (
                result.get("mean_net_return") is not None
                and result["mean_net_return"] > 0
            ),
            "incremental_ci_lower_positive": (
                incremental is not None and incremental[0] > 0
            ),
            "portfolio_total_return_positive": (
                portfolio_result.get("total_return") is not None
                and portfolio_result["total_return"] > 0
            ),
            "portfolio_max_drawdown_above_floor": (
                portfolio_result.get("max_drawdown_realized") is not None
                and portfolio_result["max_drawdown_realized"]
                >= DECISION_GATE["portfolio_max_drawdown_floor"]
            ),
        }
        checks[period]["passed"] = all(checks[period].values())
    return {
        "primary_variant": PRIMARY_VARIANT,
        "rules": DECISION_GATE,
        "periods": checks,
        "passed": all(row["passed"] for row in checks.values()),
    }


def _flatten_factors(factors: list[dict]) -> list[dict]:
    return [
        {
            "factor_id": factor["factor_id"],
            "group": factor["group"],
            "admitted": factor["admitted"],
            "direction": factor["direction"],
            "yearly_same_sign": factor["yearly_same_sign"],
            **{
                key: value
                for key, value in factor["metrics"].items()
                if key != "yearly"
            },
        }
        for factor in factors
    ]


def write_results(path: Path, report: dict) -> None:
    lines = [
        "# Auction multifactor study",
        "",
        f"Algorithm: `{VERSION}`.",
        "",
        "Scope: 2%-8% opening-gap bucket, D+3, development-only selection.",
        "",
        "## Representatives",
        "",
        "| Factor | Direction | Members | Dev IC | Dev ICIR |",
        "|---|---|---:|---:|---:|",
    ]
    for cluster in report["representatives"]:
        metrics = cluster["metrics"]
        lines.append(
            f"| `{cluster['factor_id']}` | {cluster['direction']} | "
            f"{len(cluster['members'])} | {metrics['mean_ic']:.4f} | "
            f"{metrics['icir']:.3f} |",
        )
    lines.extend([
        "",
        "## Variant results",
        "",
        "| Period | Variant | Signals | Resolved | Net | Delta | Delta 95% CI |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for row in report["results"]:
        interval = (
            (row.get("cluster_bootstrap_95") or {})
            .get("mean_incremental_return")
        )
        interval_text = (
            f"{interval[0] * 100:.3f}% to {interval[1] * 100:.3f}%"
            if interval else "NA"
        )
        lines.append(
            f"| {row['period']} | {row['variant']} | {row['signal_n']} | "
            f"{row['n']} | {row['mean_net_return'] * 100:.3f}% | "
            f"{row['mean_incremental_return'] * 100:.3f}% | "
            f"{interval_text} |",
        )
    lines.extend([
        "",
        "## Decision gate",
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
    factor_ids, factor_groups = load_factor_ids(args.admission)
    started = time.perf_counter()
    input_stats = {
        str(path): [path.stat().st_size, path.stat().st_mtime_ns]
        for path in (args.events, args.admission)
    }
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.mkdir(parents=True)
    _write_json(args.output / "manifest.json", {
        "status": "running",
        "version": VERSION,
        "script_sha256": script_hash,
        "parameters": vars(args),
        "selection": SELECTION,
        "variants": VARIANTS,
        "primary_variant": PRIMARY_VARIANT,
        "decision_gate": DECISION_GATE,
        "created_at": datetime.now().isoformat(),
    })

    frame = load_events(args.events, factor_ids)
    frame = add_factor_ranks(frame, factor_ids)
    admitted = admit_factors(frame, factor_ids, factor_groups)
    representatives = cluster_representatives(frame, admitted, seed=args.seed)
    scored = build_scores(frame, representatives)
    results, portfolio = evaluate_variants(
        scored,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    report = {
        "version": VERSION,
        "scope": {
            "gap_buckets": MAIN_BUCKETS,
            "horizon": 3,
            "event_rows": frame.height,
            "event_days": frame["date"].n_unique(),
        },
        "selection": SELECTION,
        "decision_gate": decision_gate(results, portfolio),
        "factor_count": len(factor_ids),
        "admitted_count": sum(row["admitted"] for row in admitted),
        "factors": admitted,
        "representatives": representatives,
        "results": results,
        "portfolio": portfolio,
        "portfolio_parameters": PORTFOLIO_DEFAULTS,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "warnings": [
            "Selection uses development data only; validation and stress do not alter factors or clusters.",
            "Factor admission is univariate and is not multiplicity-adjusted.",
            "Portfolio uses realised cash flows, not daily mark-to-market or the production execution engine.",
            "Classic single-factor tail scores are retained only through the frozen TailStrength interaction.",
        ],
    }
    for key, signature in input_stats.items():
        stat = Path(key).stat()
        if [stat.st_size, stat.st_mtime_ns] != signature:
            raise RuntimeError(f"Input changed during study: {key}")
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != script_hash:
        raise RuntimeError("Study source changed during execution")
    _write_json(args.output / "study.json", report)
    _write_json(args.output / "representatives.json", representatives)
    _write_json(args.output / "input_stats.json", input_stats)
    pl.DataFrame(_flatten_factors(admitted), infer_schema_length=None).write_csv(
        args.output / "factor_metrics.csv",
    )
    flat_results = []
    for row in results:
        interval = (
            (row.get("cluster_bootstrap_95") or {})
            .get("mean_incremental_return")
        )
        flat_results.append({
            **{key: value for key, value in row.items() if key != "cluster_bootstrap_95"},
            "delta_ci_low": interval[0] if interval else None,
            "delta_ci_high": interval[1] if interval else None,
        })
    if flat_results:
        pl.DataFrame(flat_results, infer_schema_length=None).write_csv(
            args.output / "variant_results.csv",
        )
    else:
        (args.output / "variant_results.csv").write_text(
            "period,variant,n\n",
            encoding="utf-8",
        )
    portfolio_rows = []
    for variant, periods in portfolio.items():
        for period, metrics in periods.items():
            portfolio_rows.append({
                "variant": variant,
                "period": period,
                **{
                    key: (
                        json.dumps(value, ensure_ascii=False)
                        if isinstance(value, (dict, list))
                        else value
                    )
                    for key, value in metrics.items()
                },
            })
    pl.DataFrame(portfolio_rows, infer_schema_length=None).write_csv(
        args.output / "portfolio.csv",
    )
    signal_output_columns = list(dict.fromkeys(
        contract["signal_column"] for contract in VARIANTS.values()
    ))
    scored.select(list(dict.fromkeys([
        *KEYS,
        "gap_bucket",
        "tail_strength_signal",
        "tail_strength_rank",
        "risk_score",
        "risk_rank",
        "_risk_coverage",
        "combined_score",
        "combined_rank",
        *signal_output_columns,
        "entry_reason",
        "exit_reason",
        "entry_vwap",
        "entry_volume",
        "exit_date",
        "net_return",
    ]))).write_parquet(args.output / "events_with_scores.parquet", compression="zstd")
    write_results(args.output / "RESULTS.md", report)
    manifest_path = args.output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _write_json(manifest_path, {
        **manifest,
        "status": "complete",
        "inputs_unchanged": True,
        "source_unchanged": True,
        "elapsed_seconds": report["elapsed_seconds"],
    })
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("events", "admission", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args()
    report = run_study(args)
    print(json.dumps({
        "event": "complete",
        "admitted": report["admitted_count"],
        "representatives": len(report["representatives"]),
        "gate_passed": report["decision_gate"]["passed"],
        "elapsed_seconds": report["elapsed_seconds"],
    }), flush=True)


if __name__ == "__main__":
    main()
