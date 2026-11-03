"""Research orchestration and CLI for the first-board right-tail study."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from .contracts import ALL_RULES, EventRecord, RuleUnavailable, TriggerCandidate
from .data import (
    MarketDataSource,
    RepositoryDataSource,
    build_event_factor_frame,
    enrich_daily_factors,
    validate_minute_layout,
)
from .dataset import build_decision_sample
from .events import build_first_board_events, sample_events_monthly
from .exit_variants import ExitVariant, parse_exit_variants
from .labels import build_labels
from .report import (
    artifact_checks,
    sha256_file,
    write_json,
    write_parquet,
    write_results,
)
from .simulator import (
    SimulationConfig,
    simulate_event_attempts,
    simulate_exit,
)
from .triggers import iter_trigger_candidates


@dataclass(frozen=True)
class StudyConfig:
    start: date
    end: date
    rules: Sequence[str] = ("E0",)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    max_future_sessions: int = 29
    auction_dir: Path | None = None
    max_events_per_month: int | None = None
    event_sample_seed: int = 20261102
    exit_variants: Sequence[ExitVariant] = ()

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError("start must not be later than end")
        unknown = set(self.rules) - set(ALL_RULES)
        if unknown:
            raise ValueError(f"unknown trigger rules: {sorted(unknown)}")
        if self.max_future_sessions < 20:
            raise ValueError("at least 20 future sessions are required for labels")
        if (
            self.max_events_per_month is not None
            and self.max_events_per_month < 1
        ):
            raise ValueError("max_events_per_month must be positive")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _code_hash() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).resolve().parent
    for path in sorted(root.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _git_state() -> tuple[str | None, bool]:
    root = Path(__file__).resolve().parents[3]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        return commit or None, bool(status.strip())
    except (OSError, subprocess.CalledProcessError):
        return None, False


def _input_hash(
    config: StudyConfig,
    generation: str,
    event_ids: list[str],
    auction_sha256: str | None = None,
    minute_input_sha256: str | None = None,
) -> str:
    payload = {
        "start": config.start.isoformat(),
        "end": config.end.isoformat(),
        "rules": list(config.rules),
        "simulation": asdict(config.simulation),
        "exit_variants": [
            asdict(variant) for variant in config.exit_variants
        ],
        "generation": generation,
        "event_ids": sorted(event_ids),
        "auction_sha256": auction_sha256,
        "minute_input_sha256": minute_input_sha256,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_auction_table(path: Path) -> tuple[pl.DataFrame, str]:
    files = sorted(path.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(
            f"auction directory contains no parquet files: {path}"
        )
    table = pl.concat(
        [pl.read_parquet(file) for file in files],
        how="diagonal_relaxed",
    )
    required = {
        "symbol",
        "date",
        "opening_gap",
        "volume_ratio",
    }
    missing = required - set(table.columns)
    if missing:
        raise ValueError(
            f"auction table missing required columns: {sorted(missing)}"
        )
    if "auction_price_adj" not in table.columns:
        raise ValueError("auction table requires auction_price_adj")
    table = table.with_columns(
        pl.col("symbol").cast(pl.String),
        pl.col("date").cast(pl.Date, strict=False),
    )
    if table.select("symbol", "date").is_duplicated().any():
        raise ValueError("auction table contains duplicate symbol/date rows")
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.name.encode("utf-8"))
        digest.update(sha256_file(file).encode("ascii"))
    return table, digest.hexdigest()


def _auction_record(
    table: pl.DataFrame,
    symbol: str,
    decision_date: date,
) -> dict[str, Any] | None:
    rows = table.filter(
        (pl.col("symbol") == symbol)
        & (pl.col("date") == decision_date)
    )
    return rows.row(0, named=True) if rows.height == 1 else None


def _event_record(row: dict[str, Any]) -> EventRecord:
    return EventRecord(
        event_id=row["event_id"],
        symbol=row["symbol"],
        event_date=row["event_date"],
        t_high_raw=float(row["t_high_raw"]),
        t_high_adj=float(row["t_high_adj"]),
        t_close_raw=float(row["t_close_raw"]),
        t_close_adj=float(row["t_close_adj"]),
        price_limit_pct=(
            float(row["price_limit_pct"])
            if row.get("price_limit_pct") is not None
            else None
        ),
        is_st_at_event=bool(row["is_st_at_event"]),
        listing_age_source=str(row["listing_age_source"]),
    )


def _daily_context(
    daily: pl.DataFrame,
    symbol: str,
    dates: list[date],
    *,
    is_st: bool,
) -> pl.DataFrame:
    missing_limits = {
        "limit_up_price",
        "limit_down_price",
    } - set(daily.columns)
    if missing_limits:
        raise ValueError(
            "daily data missing authoritative limit columns: "
            f"{sorted(missing_limits)}"
        )
    symbol_daily = (
        daily.filter(pl.col("symbol") == symbol)
        .sort("date")
    )
    rows_by_date = {
        row["date"]: row
        for row in symbol_daily.iter_rows(named=True)
    }
    rows: list[dict[str, Any]] = []
    for day in dates:
        source = rows_by_date.get(day)
        limit_up = (
            source["limit_up_price"] if source is not None else None
        )
        limit_down = (
            source["limit_down_price"] if source is not None else None
        )
        volume = source["volume"] if source is not None else None
        raw_close = source["raw_close"] if source is not None else None
        tradable = bool(
            source is not None
            and volume is not None
            and volume > 0
            and raw_close is not None
            and raw_close > 0
        )
        rows.append(
            {
                "symbol": symbol,
                "date": day,
                "raw_close": raw_close,
                "limit_up_price": limit_up,
                "limit_down_price": limit_down,
                "tradable": tradable,
                "suspended": not tradable,
                "status_known": source is not None,
                "st_flag": is_st,
                "delisted": bool(
                    source is not None
                    and source.get("delisted", False)
                ),
                "final_settlement_price": (
                    source.get("final_settlement_price")
                    if source is not None
                    else None
                ),
            }
        )
    return pl.DataFrame(rows)


def _trigger_rows(
    candidates: list[TriggerCandidate],
    unavailable: list[RuleUnavailable],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        rows.append(
            {
                "record_type": "candidate",
                "candidate_id": candidate.candidate_id,
                "event_id": candidate.event_id,
                "symbol": candidate.symbol,
                "rule": candidate.rule,
                "bar_end": candidate.bar_end,
                "signal_available_time": candidate.signal_available_time,
                "order_time": candidate.order_time,
                "signal_close_adj": candidate.signal_close_adj,
                "reason": None,
                "observed_at": None,
            }
        )
    for item in unavailable:
        rows.append(
            {
                "record_type": "unavailable",
                "candidate_id": None,
                "event_id": item.event_id,
                "symbol": None,
                "rule": item.rule,
                "bar_end": None,
                "signal_available_time": None,
                "order_time": None,
                "signal_close_adj": None,
                "reason": item.reason,
                "observed_at": item.observed_at,
            }
        )
    return rows


def _frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def _prepare_feature_contract(
    decisions: pl.DataFrame,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    actual = sorted(
        column
        for column in decisions.columns
        if column.startswith("feature__")
    )
    dropped = [
        column
        for column in actual
        if decisions.height
        and decisions[column].null_count() == decisions.height
    ]
    prepared = decisions.drop(dropped) if dropped else decisions
    dropped_set = set(dropped)
    features = [
        column
        for column in actual
        if column not in dropped_set
    ]
    non_numeric = [
        column
        for column in features
        if not prepared.schema[column].is_numeric()
    ]
    if non_numeric:
        raise ValueError(
            f"feature columns must be numeric: {non_numeric}"
        )
    coverage = {
        column: (
            1.0
            - prepared[column].null_count() / prepared.height
            if prepared.height
            else 0.0
        )
        for column in features
    }
    return prepared, {
        "version": "m2a-v2-daily-factors",
        "cutoff": (
            "event T close for daily factors; "
            "bar_end <= signal_available_time for intraday"
        ),
        "null_rule": "preserve_null_no_imputation",
        "features": features,
        "factor_coverage": coverage,
        "dropped_all_null": dropped,
    }


def _summary_row(
    event: EventRecord,
    *,
    event_dropped: bool,
    drop_reason: str | None,
    trigger_count: int,
    first_filled_candidate_id: str | None,
    blocked: FillBlockedView | None,
    exit_status: str | None,
    label_status: str | None,
) -> dict[str, Any]:
    blocked_counts = (
        dict(blocked.counts) if blocked is not None else {}
    )
    return {
        "event_id": event.event_id,
        "symbol": event.symbol,
        "event_date": event.event_date,
        "event_dropped": event_dropped,
        "drop_reason": drop_reason,
        "trigger_count": trigger_count,
        "first_filled_candidate_id": first_filled_candidate_id,
        "fill_blocked_counts": json.dumps(
            blocked_counts,
            sort_keys=True,
        ),
        "exit_status": exit_status,
        "label_status": label_status,
    }


@dataclass
class FillBlockedView:
    counts: Counter[str] = field(default_factory=Counter)


def run_study(
    data_source: MarketDataSource,
    config: StudyConfig,
    output: Path,
) -> dict[str, Any]:
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"output directory already exists: {output}")
    output.mkdir(parents=True, exist_ok=False)
    git_commit, worktree_dirty = _git_state()
    manifest: dict[str, Any] = {
        "status": "running",
        "started_at": _now(),
        "plan": "first-board-right-tail-m2a",
        "config": {
            "start": config.start.isoformat(),
            "end": config.end.isoformat(),
            "rules": list(config.rules),
            "simulation": asdict(config.simulation),
            "max_future_sessions": config.max_future_sessions,
            "auction_dir": (
                str(config.auction_dir)
                if config.auction_dir is not None
                else None
            ),
            "max_events_per_month": config.max_events_per_month,
            "event_sample_seed": config.event_sample_seed,
            "exit_variants": [
                asdict(variant) for variant in config.exit_variants
            ],
        },
        "data_generation": None,
        "code_sha256": _code_hash(),
        "git_commit": git_commit,
        "worktree_dirty": worktree_dirty,
    }
    write_json(output / "manifest.json", manifest)

    try:
        generation = data_source.data_generation()
        manifest["data_generation"] = generation
        auction_table: pl.DataFrame | None = None
        auction_sha256: str | None = None
        if config.auction_dir is not None:
            auction_table, auction_sha256 = _load_auction_table(
                config.auction_dir
            )
        history_start = config.start - timedelta(days=90)
        horizon_end = config.end + timedelta(days=90)
        sessions = data_source.trading_dates(history_start, horizon_end)
        if not sessions:
            raise ValueError("no trading sessions in requested range")
        daily = data_source.daily_batch(
            data_source.universe_symbols(history_start, config.end),
            sessions[0],
            sessions[-1],
        )
        if (
            not any(
                column.startswith(("daily__", "linkage__"))
                for column in daily.columns
            )
            or not any(
                column.startswith("market__")
                for column in daily.columns
            )
        ):
            daily = enrich_daily_factors(daily)
        events, exclusions = build_first_board_events(
            daily,
            data_source.instruments(),
            data_source.st_history(),
            sessions,
            config.start,
            config.end,
        )
        event_universe_count = events.height
        events = sample_events_monthly(
            events,
            config.max_events_per_month,
            seed=config.event_sample_seed,
        )
        event_factors = build_event_factor_frame(daily, events)
        factor_columns = [
            column
            for column in event_factors.columns
            if column.startswith(("daily__", "linkage__", "market__"))
        ]
        event_factor_lookup = {
            row["event_id"]: {
                column: row[column]
                for column in factor_columns
            }
            for row in event_factors.iter_rows(named=True)
        }
        manifest["auction_sha256"] = auction_sha256

        session_index = {day: index for index, day in enumerate(sessions)}
        minute_hasher = hashlib.sha256()
        coverage_frames: list[pl.DataFrame] = []
        trigger_rows: list[dict[str, Any]] = []
        order_rows: list[dict[str, Any]] = []
        label_rows: list[dict[str, Any]] = []
        decision_rows: list[dict[str, Any]] = []
        exit_variant_rows: list[dict[str, Any]] = []
        summary_rows: list[dict[str, Any]] = []
        coverage_incomplete_events = 0

        for row in events.iter_rows(named=True):
            event = _event_record(row)
            event_index = session_index.get(event.event_date)
            if event_index is None:
                raise ValueError("event date is missing from trading sessions")
            future_dates = sessions[
                event_index + 1:
                event_index + 1 + config.max_future_sessions
            ]
            needed_dates = [event.event_date, *future_dates]
            bars = data_source.minute_batch(
                [event.symbol],
                needed_dates,
            )
            minute_hasher.update(event.event_id.encode("utf-8"))
            if not bars.is_empty():
                minute_hasher.update(
                    bars.sort(["symbol", "bar_end"])
                    .write_csv()
                    .encode("utf-8")
                )
            context = _daily_context(
                daily,
                event.symbol,
                needed_dates,
                is_st=event.is_st_at_event,
            )
            expected_pairs = {
                (event.symbol, day) for day in needed_dates
            }
            coverage = validate_minute_layout(bars, expected_pairs).with_columns(
                pl.lit(event.event_id).alias("event_id")
            )
            suspended_pairs = {
                (event.symbol, row["date"])
                for row in context.filter(
                    pl.col("status_known")
                    & pl.col("suspended")
                ).iter_rows(named=True)
            }
            suspended_frame = pl.DataFrame(
                {
                    "symbol": [pair[0] for pair in suspended_pairs],
                    "date": [pair[1] for pair in suspended_pairs],
                    "_authoritative_suspended": [
                        True for _ in suspended_pairs
                    ],
                }
            )
            if suspended_frame.height:
                coverage = (
                    coverage.join(
                        suspended_frame,
                        on=["symbol", "date"],
                        how="left",
                    )
                    .with_columns(
                        pl.when(
                            (pl.col("status") == "missing")
                            & pl.col("_authoritative_suspended").fill_null(False)
                        )
                        .then(pl.lit("suspended"))
                        .otherwise(pl.col("status"))
                        .alias("status")
                    )
                    .drop("_authoritative_suspended")
                )
            coverage_frames.append(coverage)
            if (
                coverage.height != len(expected_pairs)
                or coverage.filter(
                    ~pl.col("status").is_in(["complete", "suspended"])
                ).height
            ):
                coverage_incomplete_events += 1
                summary_rows.append(
                    _summary_row(
                        event,
                        event_dropped=True,
                        drop_reason="coverage_incomplete",
                        trigger_count=0,
                        first_filled_candidate_id=None,
                        blocked=None,
                        exit_status=None,
                        label_status="unobservable",
                    )
                )
                continue
            if len(future_dates) < 20:
                summary_rows.append(
                    _summary_row(
                        event,
                        event_dropped=True,
                        drop_reason="insufficient_label_horizon",
                        trigger_count=0,
                        first_filled_candidate_id=None,
                        blocked=None,
                        exit_status=None,
                        label_status="right_censored",
                    )
                )
                continue

            candidates, unavailable = iter_trigger_candidates(
                event,
                bars,
                config.rules,
                auction=(
                    _auction_record(
                        auction_table,
                        event.symbol,
                        future_dates[0],
                    )
                    if auction_table is not None and future_dates
                    else None
                ),
            )
            trigger_rows.extend(_trigger_rows(candidates, unavailable))
            if not candidates:
                summary_rows.append(
                    _summary_row(
                        event,
                        event_dropped=True,
                        drop_reason="no_trigger",
                        trigger_count=0,
                        first_filled_candidate_id=None,
                        blocked=None,
                        exit_status=None,
                        label_status="not_triggered",
                    )
                )
                continue

            fill, exit_result, attempts = simulate_event_attempts(
                event,
                candidates,
                bars,
                context,
                config.simulation,
            )
            for attempt in attempts:
                order_row = asdict(attempt)
                order_row["candidate_id"] = attempt.candidate_id
                order_rows.append(order_row)
            attempted_ids = {
                attempt.candidate_id for attempt in attempts
            }
            for candidate in candidates:
                if candidate.candidate_id not in attempted_ids:
                    continue
                decision_rows.append(
                    build_decision_sample(
                        event,
                        candidate,
                        bars,
                        context,
                        sessions,
                        config.simulation,
                        daily_factors=event_factor_lookup.get(
                            event.event_id
                        ),
                    ).to_flat_row()
                )
            blocked = FillBlockedView(
                Counter(
                    attempt.blocked_reason or "unknown_fill_block"
                    for attempt in attempts
                    if not attempt.filled
                )
            )
            if not fill.filled:
                summary_rows.append(
                    _summary_row(
                        event,
                        event_dropped=True,
                        drop_reason="fill_blocked",
                        trigger_count=len(candidates),
                        first_filled_candidate_id=None,
                        blocked=blocked,
                        exit_status=None,
                        label_status="not_filled",
                    )
                )
                continue
            if exit_result is None:
                raise ValueError("filled event has no exit result")
            for variant in config.exit_variants:
                variant_exit = simulate_exit(
                    fill,
                    bars,
                    context,
                    variant.simulation_config(config.simulation),
                )
                exit_variant_rows.append(
                    {
                        "event_id": event.event_id,
                        "candidate_id": fill.candidate_id,
                        "symbol": fill.symbol,
                        "variant": variant.name,
                        "stop_loss_pct": variant.stop_loss_pct,
                        "max_holding_days": variant.max_holding_days,
                        "entry_time": fill.fill_time,
                        "entry_exec_adj": fill.entry_exec_adj,
                        "status": variant_exit.status,
                        "reason": variant_exit.reason,
                        "trigger_time": variant_exit.trigger_time,
                        "order_time": variant_exit.order_time,
                        "exit_time": variant_exit.fill_time,
                        "exit_price_raw": variant_exit.fill_price_raw,
                        "pending_days": variant_exit.pending_days,
                        "net_return": variant_exit.net_return,
                        "quantity": variant_exit.quantity,
                    }
                )
            available_label_sessions = [
                value
                for value in sessions
                if value >= fill.fill_time.date()
            ]
            if len(available_label_sessions) < 20:
                summary_rows.append(
                    _summary_row(
                        event,
                        event_dropped=False,
                        drop_reason=None,
                        trigger_count=len(candidates),
                        first_filled_candidate_id=fill.candidate_id,
                        blocked=blocked,
                        exit_status=exit_result.status,
                        label_status="right_censored",
                    )
                )
                continue
            label = build_labels(
                fill,
                exit_result,
                bars,
                config.simulation,
                daily_context=context,
                trading_dates=needed_dates,
            )
            label_rows.append(asdict(label))
            summary_rows.append(
                _summary_row(
                    event,
                    event_dropped=False,
                    drop_reason=None,
                    trigger_count=len(candidates),
                    first_filled_candidate_id=fill.candidate_id,
                    blocked=blocked,
                    exit_status=exit_result.status,
                    label_status=label.exit_status,
                )
            )

        coverage_frame = (
            pl.concat(coverage_frames, how="diagonal")
            if coverage_frames
            else pl.DataFrame()
        )
        minute_input_sha256 = minute_hasher.hexdigest()
        manifest["minute_input_sha256"] = minute_input_sha256
        manifest["input_sha256"] = _input_hash(
            config,
            generation,
            events["event_id"].to_list(),
            auction_sha256,
            minute_input_sha256,
        )
        if coverage_frame.is_empty():
            manifest["coverage_by_month"] = []
        else:
            manifest["coverage_by_month"] = (
                coverage_frame.with_columns(
                    pl.col("date").dt.year().alias("year"),
                    pl.col("date").dt.month().alias("month"),
                )
                .group_by(["year", "month", "status"])
                .len(name="rows")
                .sort(["year", "month", "status"])
                .to_dicts()
            )
        triggers_frame = _frame(trigger_rows)
        orders_frame = _frame(order_rows)
        labels_frame = _frame(label_rows)
        decisions_frame = _frame(decision_rows)
        summary_frame = _frame(summary_rows)
        exit_variants_frame = (
            pl.DataFrame(exit_variant_rows)
            if exit_variant_rows
            else pl.DataFrame(
                schema={
                    "event_id": pl.String,
                    "candidate_id": pl.String,
                    "symbol": pl.String,
                    "variant": pl.String,
                    "stop_loss_pct": pl.Float64,
                    "max_holding_days": pl.Int64,
                    "entry_time": pl.Datetime,
                    "entry_exec_adj": pl.Float64,
                    "status": pl.String,
                    "reason": pl.String,
                    "trigger_time": pl.Datetime,
                    "order_time": pl.Datetime,
                    "exit_time": pl.Datetime,
                    "exit_price_raw": pl.Float64,
                    "pending_days": pl.Int64,
                    "net_return": pl.Float64,
                    "quantity": pl.Int64,
                }
            )
        )

        write_parquet(events, output / "events.parquet")
        write_parquet(exclusions, output / "exclusions.parquet")
        write_parquet(coverage_frame, output / "coverage.parquet")
        write_parquet(
            pl.DataFrame({"date": sessions}),
            output / "sessions.parquet",
        )
        write_parquet(triggers_frame, output / "triggers.parquet")
        write_parquet(orders_frame, output / "orders.parquet")
        write_parquet(labels_frame, output / "labels.parquet")
        write_parquet(
            exit_variants_frame,
            output / "exit_variants.parquet",
        )
        decisions_output, feature_contract = _prepare_feature_contract(
            decisions_frame
        )
        write_parquet(decisions_output, output / "decisions.parquet")
        write_parquet(summary_frame, output / "event_summary.parquet")
        write_json(output / "feature_contract.json", feature_contract)

        candidate_count = sum(
            trigger_row["record_type"] == "candidate"
            for trigger_row in trigger_rows
        )
        manifest["stats"] = {
            "sessions": len(sessions),
            "events": events.height,
            "event_universe": event_universe_count,
            "event_sample_seed": config.event_sample_seed,
            "max_events_per_month": config.max_events_per_month,
            "exclusions": exclusions.height,
            "trigger_candidates": candidate_count,
            "rule_unavailable": len(trigger_rows) - candidate_count,
            "filled_events": sum(
                row["first_filled_candidate_id"] is not None
                for row in summary_rows
            ),
            "labels": labels_frame.height,
            "decision_count": decisions_frame.height,
            "feature_count": len(feature_contract["features"]),
            "dropped_all_null_features": feature_contract[
                "dropped_all_null"
            ],
            "market_fillable_count": (
                decisions_frame.filter(pl.col("market_fillable")).height
                if decisions_frame.height
                else 0
            ),
            "label_observable_count": (
                decisions_frame.filter(pl.col("label_observable")).height
                if decisions_frame.height
                else 0
            ),
            "exit_variant_rows": exit_variants_frame.height,
            "coverage_incomplete_events": coverage_incomplete_events,
        }
        finished_at = _now()
        reported_manifest = {
            **manifest,
            "status": "complete",
            "finished_at": finished_at,
        }
        write_results(output / "RESULTS.md", reported_manifest)
        manifest["checks"] = artifact_checks(output)
        manifest["status"] = "complete"
        manifest["finished_at"] = finished_at
        write_json(output / "manifest.json", manifest)
        return manifest
    except Exception as exc:
        manifest.pop("finished_at", None)
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        write_json(output / "manifest.json", manifest)
        raise


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the first-board right-tail research study",
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rules", default="E0")
    parser.add_argument("--auction-dir", type=Path)
    parser.add_argument("--max-events-per-month", type=int)
    parser.add_argument(
        "--event-sample-seed",
        type=int,
        default=20261102,
    )
    parser.add_argument(
        "--with-model",
        action="store_true",
        help="run the optional M2B model stage in <output>/model",
    )
    parser.add_argument(
        "--exit-variants",
        default="",
        help=(
            "comma-separated exit variants; use baseline,time10,"
            "tight4_time10,wide8_time20"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    config = StudyConfig(
        start=args.start,
        end=args.end,
        rules=tuple(
            value.strip()
            for value in args.rules.split(",")
            if value.strip()
        ),
        auction_dir=args.auction_dir,
        max_events_per_month=args.max_events_per_month,
        event_sample_seed=args.event_sample_seed,
        exit_variants=(
            parse_exit_variants(args.exit_variants)
            if args.exit_variants
            else ()
        ),
    )
    manifest = run_study(
        RepositoryDataSource(args.data_dir),
        config,
        args.output,
    )
    if args.with_model:
        try:
            from .model import ModelConfig
            from .model_study import run_model_study

            manifest["model"] = run_model_study(
                args.output / "decisions.parquet",
                args.output / "model",
                ModelConfig(),
                sessions_path=args.output / "sessions.parquet",
            )
        except Exception as exc:
            manifest["model"] = {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
            write_json(args.output / "manifest.json", manifest)
            raise
        write_json(args.output / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
