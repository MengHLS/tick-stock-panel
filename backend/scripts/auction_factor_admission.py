"""D-1 factor admission for the auction-tail study.

The event table supplies date, symbol, gap bucket and D+3 net outcomes. This
script materialises eligible stable factors from the previous completed session,
then reports date-clustered rank-IC admission diagnostics. It never selects on
the validation or stress periods.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, timedelta
from pathlib import Path

import polars as pl

from app.backtest.factor import FactorBacktestService
from app.factors.registry import all_factors
from scripts.auction_high_open_study import PERIODS, _partitions, _unique, _write_json

KEYS = ["symbol", "date"]
TAIL_COLUMNS = (
    "tail_price_change",
    "last_imbalance",
    "last_minute_matched_growth",
    "post0920_matched_growth",
    "volume_vs_prev",
    "tail_strength_score",
)
PHYSICAL_COLUMNS = (
    "symbol", "date", "open", "high", "low", "close", "volume", "amount",
    "raw_close", "raw_high", "raw_low", "turnover_rate",
    "consecutive_limit_ups", "consecutive_limit_downs",
)


def candidate_factors() -> list:
    """Return stable, scale-free, non-PIT daily factors eligible for admission."""
    excluded = {"vwap_bias"}
    return [
        spec
        for spec in all_factors(asset_type="stock", stable_only=True)
        if spec.kind in {"base", "virtual"}
        and not spec.pit
        and spec.scale_free
        and spec.incremental_safe
        and not spec.id.startswith("ext_")
        and spec.group not in {"扩展数据", "财务"}
        and spec.id not in excluded
    ]


def shift_to_decision_day(
    panel: pl.DataFrame,
    factor_ids: list[str],
) -> pl.DataFrame:
    """Shift session-close factors by one symbol trading row (D-1 for D)."""
    available = [factor_id for factor_id in factor_ids if factor_id in panel.columns]
    if not available:
        return panel.select(*KEYS)
    return panel.sort(KEYS).select(
        *KEYS,
        *[
            pl.col(factor_id).shift(1).over("symbol").alias(f"factor__{factor_id}")
            for factor_id in available
        ],
    )


def _load_year_factors(
    data_dir: Path,
    keys: pl.DataFrame,
    factor_ids: list[str],
    year: int,
) -> tuple[pl.DataFrame, list[str]]:
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    files = _partitions(
        data_dir / "kline_daily_enriched",
        start - timedelta(days=550),
        end,
    )
    if not files:
        raise ValueError(f"No enriched partitions for factor year {year}")
    panel = _unique(
        pl.scan_parquet(files, hive_partitioning=False)
        .select(*PHYSICAL_COLUMNS)
        .collect(),
        KEYS,
    ).sort(KEYS)
    computed = FactorBacktestService._compute_missing_factors(
        panel,
        set(factor_ids),
        assume_sorted=True,
    )
    shifted = shift_to_decision_day(computed, factor_ids)
    available = [
        column.removeprefix("factor__")
        for column in shifted.columns
        if column.startswith("factor__")
    ]
    year_keys = keys.filter(pl.col("date").dt.year() == year)
    return shifted.join(year_keys, on=KEYS, how="semi"), available


def attach_previous_session_factors(
    data_dir: Path,
    events: pl.DataFrame,
) -> tuple[pl.DataFrame, dict]:
    factor_ids = [spec.id for spec in candidate_factors()]
    keys = events.select(*KEYS).unique().sort(KEYS)
    years = sorted(keys["date"].dt.year().unique().to_list())
    pieces: list[pl.DataFrame] = []
    available_by_year: dict[int, list[str]] = {}
    for year in years:
        piece, available = _load_year_factors(data_dir, keys, factor_ids, year)
        pieces.append(piece)
        available_by_year[year] = available
    if not pieces:
        raise ValueError("Event table has no factor-admission years")
    common = set.intersection(*(set(items) for items in available_by_year.values()))
    if not common:
        raise ValueError("No factors are available in every event year")
    columns = [f"factor__{factor_id}" for factor_id in sorted(common)]
    factors = pl.concat(
        [piece.select(*KEYS, *columns) for piece in pieces],
        how="diagonal_relaxed",
    )
    return events.join(factors, on=KEYS, how="left"), {
        "candidate_count": len(factor_ids),
        "available_count": len(common),
        "available_factor_ids": sorted(common),
        "available_by_year": available_by_year,
    }


def _rank_ic(frame: pl.DataFrame, column: str) -> tuple[float, float, float, int] | None:
    daily = (
        frame.select(
            "date",
            pl.when(pl.col(column).is_not_null() & pl.col(column).is_finite())
            .then(pl.col(column))
            .alias("_x"),
            pl.when(pl.col("_residual").is_not_null() & pl.col("_residual").is_finite())
            .then(pl.col("_residual"))
            .alias("_y"),
        )
        .drop_nulls(["_x", "_y"])
        .with_columns(
            pl.len().over("date").alias("_n"),
            pl.col("_x").rank("average").over("date").alias("_rx"),
            pl.col("_y").rank("average").over("date").alias("_ry"),
        )
        .filter(pl.col("_n") >= 8)
        .group_by("date")
        .agg(pl.corr("_rx", "_ry").alias("_ic"))
        .drop_nulls("_ic")
    )
    if daily.is_empty():
        return None
    ic = daily["_ic"]
    mean = float(ic.mean())
    std = float(ic.std(ddof=1)) if ic.len() > 1 else None
    icir = mean / std if std and std > 0 else None
    return mean, icir, float((ic > 0).mean()), int(ic.len())


def _factor_metrics(
    events: pl.DataFrame,
    column: str,
    start: date,
    end: date,
) -> dict:
    frame = events.filter(
        (pl.col("horizon") == 3)
        & pl.col("date").is_between(start, end)
        & (pl.col("entry_reason") == "ok")
        & (pl.col("exit_reason") == "ok")
        & pl.col("net_return").is_finite()
    )
    if frame.is_empty():
        return {"status": "no_data", "n": 0, "event_days": 0}
    groups = ["date", "gap_bucket"]
    frame = frame.with_columns(
        pl.col("net_return").median().over(groups).alias("_baseline"),
    ).with_columns(
        (pl.col("net_return") - pl.col("_baseline")).alias("_residual"),
    )
    coverage = float((frame[column].is_not_null() & frame[column].is_finite()).mean())
    result = _rank_ic(frame, column)
    if result is None:
        return {
            "status": "insufficient_cross_section",
            "n": frame.height,
            "event_days": frame["date"].n_unique(),
            "coverage": coverage,
        }
    mean_ic, icir, positive_day_rate, ic_days = result
    yearly = []
    for year in sorted(frame["date"].dt.year().unique().to_list()):
        sub = frame.filter(pl.col("date").dt.year() == year)
        yearly_result = _rank_ic(sub, column)
        yearly.append({
            "year": int(year),
            "mean_ic": yearly_result[0] if yearly_result else None,
            "ic_days": yearly_result[3] if yearly_result else 0,
        })
    return {
        "status": "ok",
        "n": frame.height,
        "event_days": frame["date"].n_unique(),
        "coverage": coverage,
        "mean_ic": mean_ic,
        "icir": icir,
        "positive_day_rate": positive_day_rate,
        "ic_days": ic_days,
        "direction": "high" if mean_ic > 0 else "low" if mean_ic < 0 else "none",
        "yearly": yearly,
    }


def build_admission(
    events: pl.DataFrame,
    factor_info: dict,
) -> dict:
    groups = {
        spec.id: spec.group
        for spec in candidate_factors()
    }
    factor_columns = [
        *[f"factor__{factor_id}" for factor_id in factor_info["available_factor_ids"]],
        *[column for column in TAIL_COLUMNS if column in events.columns],
    ]
    rows = []
    for column in factor_columns:
        factor_id = column.removeprefix("factor__")
        timing = "D_minus_1_close" if column.startswith("factor__") else "D_0925"
        metrics = {
            period: _factor_metrics(events, column, start, end)
            for period, start, end in PERIODS
            if start <= date(2026, 12, 31)
        }
        development = metrics.get("development") or {}
        admitted = (
            development.get("status") == "ok"
            and development.get("coverage", 0) >= 0.70
            and abs(development.get("mean_ic") or 0) >= 0.015
            and abs(development.get("icir") or 0) >= 0.10
        )
        rows.append({
            "factor_id": factor_id,
            "group": groups.get(factor_id, "竞价"),
            "timing": timing,
            "admission_stage1": admitted,
            "metrics": metrics,
        })
    rows.sort(
        key=lambda row: abs(
            (row["metrics"].get("development") or {}).get("mean_ic") or 0
        ),
        reverse=True,
    )
    return {
        "selection_rule": (
            "Development only: coverage>=0.70, abs(mean rank IC)>=0.015, "
            "abs(ICIR)>=0.10. Validation and stress are reported but never used "
            "to flip admission."
        ),
        "factor_info": factor_info,
        "factors": rows,
    }


def _flat_rows(admission: dict) -> list[dict]:
    rows = []
    for factor in admission["factors"]:
        base = {
            "factor_id": factor["factor_id"],
            "group": factor["group"],
            "timing": factor["timing"],
            "admission_stage1": factor["admission_stage1"],
        }
        for period, metrics in factor["metrics"].items():
            rows.append({
                **base,
                "period": period,
                **{key: value for key, value in metrics.items() if key != "yearly"},
            })
    return rows


def run_admission(data_dir: Path, events_path: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError("Use a NEW output directory; frozen runs are never overwritten")
    started = time.perf_counter()
    events = pl.read_parquet(events_path)
    events, factor_info = attach_previous_session_factors(data_dir, events)
    admission = build_admission(events, factor_info)
    admission["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    output.mkdir(parents=True)
    events.write_parquet(output / "events_with_factors.parquet", compression="zstd")
    _write_json(output / "factor_admission.json", admission)
    flat = _flat_rows(admission)
    if flat:
        pl.DataFrame(flat, infer_schema_length=None).write_csv(
            output / "factor_admission.csv",
        )
    else:
        (output / "factor_admission.csv").write_text(
            "factor_id,period,n,mean_ic\n",
            encoding="utf-8",
        )
    return admission


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = run_admission(args.data_dir, args.events, args.output)
    print(json.dumps({
        "event": "complete",
        "admitted": sum(row["admission_stage1"] for row in report["factors"]),
        "factors": len(report["factors"]),
        "elapsed_seconds": report["elapsed_seconds"],
    }), flush=True)


if __name__ == "__main__":
    main()
