"""Walkforward study for event-level first-board admission and returns."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from .event_policy import (
    EventPolicyConfig,
    build_event_samples,
    fit_event_policy,
    predict_event_policy,
    select_event_candidates,
)
from .report import sha256_file, write_json, write_parquet
from .splits import DEFAULT_FOLDS, assign_expanding_folds


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_sessions(path: Path) -> list[date]:
    frame = pl.read_parquet(path)
    if "date" not in frame.columns:
        raise ValueError("sessions parquet requires date")
    sessions = frame["date"].drop_nulls().unique().sort().to_list()
    if not sessions:
        raise ValueError("sessions must not be empty")
    return sessions


def _resolve_sessions(
    decisions_path: Path,
    sessions_path: Path | None,
) -> tuple[list[date], str]:
    if sessions_path is not None:
        return _read_sessions(sessions_path), sessions_path.name
    sibling = decisions_path.parent / "sessions.parquet"
    if sibling.is_file():
        return _read_sessions(sibling), sibling.name
    raise ValueError(
        "sessions.parquet is required beside decisions.parquet "
        "unless --sessions is provided"
    )


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


def _code_hash() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).resolve().parent
    for name in (
        "event_policy.py",
        "event_policy_study.py",
        "splits.py",
    ):
        digest.update(name.encode("utf-8"))
        digest.update((root / name).read_bytes())
    return digest.hexdigest()


def _sessions_sha256(sessions: Sequence[date]) -> str:
    payload = "\n".join(value.isoformat() for value in sessions)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _serialize_folds(folds: Sequence[dict]) -> list[dict[str, str]]:
    return [
        {
            "name": str(fold["name"]),
            "test_start": fold["test_start"].isoformat(),
            "test_end": fold["test_end"].isoformat(),
        }
        for fold in folds
    ]


def _rate(frame: pl.DataFrame, predicate: pl.Expr) -> float | None:
    if frame.is_empty():
        return None
    values = frame.select(
        pl.when(predicate)
        .then(1.0)
        .otherwise(0.0)
        .alias("_value")
    )["_value"].drop_nulls()
    return float(values.mean()) if values.len() else None


def _mean(frame: pl.DataFrame, column: str) -> float | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    values = frame[column].cast(pl.Float64)
    values = values.filter(values.is_not_null() & values.is_finite())
    return float(values.mean()) if values.len() else None


def _fold_metrics(
    fold: str,
    validation: pl.DataFrame,
    gated: pl.DataFrame,
    selected: pl.DataFrame,
) -> dict[str, Any]:
    observable = selected.filter(
        pl.col("market_fillable").fill_null(False)
        & pl.col("label_observable").fill_null(False)
    )
    return {
        "fold": fold,
        "validation_events": validation.height,
        "fill_gate_events": gated.height,
        "selected_events": selected.height,
        "selected_actual_fill_rate": _rate(
            selected,
            pl.col("market_fillable").fill_null(False),
        ),
        "selected_stop_first_rate": _rate(
            observable,
            pl.col("stop_first") == 1,
        ),
        "selected_mfe30_rate": _rate(
            observable,
            pl.col("mfe_touch_20d") >= 0.30,
        ),
        "selected_mfe50_rate": _rate(
            observable,
            pl.col("mfe_touch_20d") >= 0.50,
        ),
        "selected_mean_policy_net_return": _mean(
            selected,
            "policy_net_return",
        ),
        "selected_mean_exec_return": _mean(
            observable,
            "exec_return",
        ),
    }


def _write_results(path: Path, manifest: dict[str, Any]) -> None:
    stats = manifest["stats"]

    def metric(value: float | None, precision: int) -> str:
        return "n/a" if value is None else f"{value:.{precision}f}"

    lines = [
        "# First-Board Event Policy",
        "",
        f"- Status: {manifest['status']}",
        f"- Features: {stats['features']}",
        f"- Validation events: {stats['validation_events']}",
        f"- Selected events: {stats['selected_events']}",
        f"- Selected labels: {stats['selected_labels']}",
        f"- Selected fill rate: "
        f"{metric(stats['selected_fill_rate'], 4)}",
        f"- Selected mean policy return: "
        f"{metric(stats['selected_mean_policy_net_return'], 6)}",
        "",
        "Admission uses T-day factors only. Execution is the first actual "
        "A/B/C fill; selection is research output, not a trading signal.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _artifact_checks(output: Path) -> dict[str, str]:
    return {
        path.name: sha256_file(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "event_policy_manifest.json"
    }


def run_event_policy_study(
    decisions_path: Path,
    output: Path,
    config: EventPolicyConfig,
    *,
    sessions_path: Path | None = None,
    sessions: Sequence[date] | None = None,
    folds: Sequence[dict] = DEFAULT_FOLDS,
    purge_sessions: int = 30,
) -> dict[str, Any]:
    decisions_path = Path(decisions_path)
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"output directory already exists: {output}")
    output.mkdir(parents=True, exist_ok=False)
    git_commit, worktree_dirty = _git_state()
    manifest: dict[str, Any] = {
        "status": "running",
        "started_at": _now(),
        "plan": "first-board-event-policy-v1",
        "decisions_sha256": None,
        "sessions_source": None,
        "sessions_sha256": None,
        "config": asdict(config),
        "folds": _serialize_folds(folds),
        "purge_sessions": purge_sessions,
        "code_sha256": _code_hash(),
        "git_commit": git_commit,
        "worktree_dirty": worktree_dirty,
    }
    write_json(output / "event_policy_manifest.json", manifest)

    try:
        if not decisions_path.is_file():
            raise FileNotFoundError(
                f"decisions parquet not found: {decisions_path}"
            )
        decisions = pl.read_parquet(decisions_path)
        if sessions is None:
            resolved_sessions, sessions_source = _resolve_sessions(
                decisions_path,
                sessions_path,
            )
        else:
            resolved_sessions = sorted(set(sessions))
            sessions_source = "caller"
        if not resolved_sessions:
            raise ValueError("sessions must not be empty")
        events = build_event_samples(decisions)
        unobservable_fill = events.filter(
            pl.col("market_fillable")
            & (
                ~pl.col("label_observable").fill_null(False)
                | pl.col("policy_net_return").is_null()
            )
        )
        if unobservable_fill.height:
            events = events.join(
                unobservable_fill.select("event_id"),
                on="event_id",
                how="anti",
            )
        folded = assign_expanding_folds(
            events,
            resolved_sessions,
            folds=folds,
            purge_sessions=purge_sessions,
        )
        prediction_frames: list[pl.DataFrame] = []
        selected_frames: list[pl.DataFrame] = []
        calibration_frames: list[pl.DataFrame] = []
        status_frames: list[pl.DataFrame] = []
        metric_rows: list[dict[str, Any]] = []
        feature_counts: list[int] = []

        outcome_columns = [
            "event_id",
            "market_fillable",
            "label_observable",
            "stop_first",
            "mfe_touch_20d",
            "mae_touch_20d",
            "peak_day",
            "exec_return",
            "exit_status",
            "trigger_rule",
            "fill_decision_id",
            "label_maturity_time",
            "policy_net_return",
        ]
        for fold in folds:
            name = str(fold["name"])
            fold_rows = folded.filter(pl.col("fold") == name)
            train = fold_rows.filter(pl.col("role") == "train")
            validation = fold_rows.filter(pl.col("role") == "validation")
            if validation.is_empty():
                continue
            if train.is_empty():
                raise ValueError(
                    f"fold {name} has validation events but no training events"
                )
            bundle = fit_event_policy(train, config)
            feature_counts.append(len(bundle.feature_names))
            validation_predicted = predict_event_policy(
                validation,
                bundle,
            ).join(
                validation.select(outcome_columns),
                on="event_id",
                how="left",
            )
            validation_gated = validation_predicted.filter(
                pl.col("prob_fill") >= bundle.fill_threshold
            )
            selected = select_event_candidates(
                validation_predicted,
                fill_threshold=bundle.fill_threshold,
                event_fraction=config.event_budget_fraction,
                max_per_day=config.max_entries_per_day,
            ).with_columns(pl.lit(True).alias("selected"))
            selected_ids = selected.select(
                "event_id",
                pl.lit(True).alias("selected"),
            )
            validation_output = validation_predicted.join(
                selected_ids,
                on="event_id",
                how="left",
            ).with_columns(
                pl.col("selected").fill_null(False)
            )
            prediction_frames.append(validation_output)
            selected_frames.append(selected)
            calibration = bundle.calibration
            calibration_frames.append(
                pl.DataFrame(
                    [
                        {
                            "fold": name,
                            "method": (
                                calibration.method
                                if calibration is not None
                                else "raw"
                            ),
                            "raw_brier": (
                                calibration.raw_brier
                                if calibration is not None
                                else None
                            ),
                            "calibrated_brier": (
                                calibration.calibrated_brier
                                if calibration is not None
                                else None
                            ),
                            "sample_count": (
                                calibration.sample_count
                                if calibration is not None
                                else 0
                            ),
                            "fill_threshold": bundle.fill_threshold,
                        }
                    ]
                )
            )
            status_frames.append(
                pl.DataFrame(
                    [
                        {
                            "fold": name,
                            "target": target,
                            "status": status,
                        }
                        for target, status in bundle.statuses.items()
                    ]
                )
            )
            metric_rows.append(
                _fold_metrics(
                    name,
                    validation,
                    validation_gated,
                    selected,
                )
            )

        if not prediction_frames:
            raise ValueError("no fold has validation events")
        if len(set(feature_counts)) != 1:
            raise ValueError(
                "event feature count changed across folds"
            )
        predictions = pl.concat(
            prediction_frames,
            how="diagonal_relaxed",
        ).sort(["fold", "decision_date", "event_id"])
        selected_events = pl.concat(
            selected_frames,
            how="diagonal_relaxed",
        ).sort(["fold", "decision_date", "selected_rank"])
        calibration_frame = pl.concat(
            calibration_frames,
            how="diagonal_relaxed",
        ).sort("fold")
        model_status = pl.concat(
            status_frames,
            how="diagonal_relaxed",
        ).sort(["fold", "target"])
        fold_metrics = pl.DataFrame(metric_rows).sort("fold")
        write_parquet(folded, output / "event_samples.parquet")
        write_parquet(predictions, output / "predictions.parquet")
        write_parquet(selected_events, output / "selected_events.parquet")
        write_parquet(fold_metrics, output / "fold_metrics.parquet")
        write_parquet(calibration_frame, output / "calibration.parquet")
        write_parquet(model_status, output / "model_status.parquet")
        selected_labels = selected_events.filter(
            pl.col("market_fillable")
            & pl.col("label_observable")
        ).height
        manifest["stats"] = {
            "event_rows": events.height,
            "fold_roles": folded.height,
            "features": feature_counts[0],
            "unobservable_fill_events": unobservable_fill.height,
            "validation_events": predictions.height,
            "selected_events": selected_events.height,
            "selected_labels": selected_labels,
            "selected_fill_rate": _rate(
                selected_events,
                pl.col("market_fillable").fill_null(False),
            ),
            "selected_mean_policy_net_return": _mean(
                selected_events,
                "policy_net_return",
            ),
        }
        manifest["decisions_sha256"] = sha256_file(decisions_path)
        manifest["sessions_source"] = sessions_source
        manifest["sessions_sha256"] = _sessions_sha256(resolved_sessions)
        manifest["calibration"] = calibration_frame.to_dicts()
        manifest["model_status"] = model_status.to_dicts()
        manifest["fold_metrics"] = fold_metrics.to_dicts()
        manifest["status"] = "complete"
        manifest["finished_at"] = _now()
        _write_results(output / "RESULTS.md", manifest)
        manifest["checks"] = _artifact_checks(output)
        write_json(
            output / "event_policy_manifest.json",
            manifest,
        )
        return manifest
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        manifest.pop("finished_at", None)
        write_json(
            output / "event_policy_manifest.json",
            manifest,
        )
        raise


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the first-board event-level policy study",
    )
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--sessions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-iter", type=int, default=150)
    parser.add_argument("--fill-gate-fraction", type=float, default=0.3)
    parser.add_argument("--event-budget-fraction", type=float, default=0.1)
    parser.add_argument("--max-entries-per-day", type=int, default=2)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    manifest = run_event_policy_study(
        args.decisions,
        args.output,
        EventPolicyConfig(
            max_iter=args.max_iter,
            fill_gate_fraction=args.fill_gate_fraction,
            event_budget_fraction=args.event_budget_fraction,
            max_entries_per_day=args.max_entries_per_day,
        ),
        sessions_path=args.sessions,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
