"""CLI and artifacts for first-board right-tail model walkforward studies."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from .model import ModelConfig, feature_columns
from .report import (
    artifact_checks,
    sha256_file,
    write_json,
    write_parquet,
)
from .splits import DEFAULT_FOLDS
from .walkforward import run_model_walkforward


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_sessions(path: Path) -> list[date]:
    if not path.is_file():
        raise FileNotFoundError(f"trading sessions file not found: {path}")
    frame = pl.read_parquet(path)
    if "date" in frame.columns:
        column = "date"
    else:
        date_columns = [
            name
            for name, dtype in frame.schema.items()
            if dtype == pl.Date
        ]
        if len(date_columns) != 1:
            raise ValueError(
                "sessions parquet requires a date column"
            )
        column = date_columns[0]
    sessions = (
        frame[column]
        .drop_nulls()
        .unique()
        .sort()
        .to_list()
    )
    if not sessions:
        raise ValueError("trading sessions must not be empty")
    return sessions


def _resolve_sessions(
    decisions_path: Path,
    *,
    sessions: Sequence[date] | None,
    sessions_path: Path | None,
) -> tuple[list[date], str]:
    if sessions is not None:
        ordered = sorted(set(sessions))
        if not ordered:
            raise ValueError("trading sessions must not be empty")
        return ordered, "caller"
    if sessions_path is not None:
        return _read_sessions(sessions_path), sessions_path.name
    sibling_sessions = decisions_path.parent / "sessions.parquet"
    if sibling_sessions.is_file():
        return _read_sessions(sibling_sessions), sibling_sessions.name
    coverage = decisions_path.parent / "coverage.parquet"
    if coverage.is_file():
        frame = pl.read_parquet(coverage)
        if "date" not in frame.columns:
            raise ValueError("coverage parquet is missing date")
        return (
            frame["date"].drop_nulls().unique().sort().to_list(),
            coverage.name,
        )
    raise ValueError(
        "authoritative trading sessions are required; provide "
        "--sessions or retain sessions.parquet beside decisions.parquet"
    )


def _load_feature_contract(
    decisions_path: Path,
) -> dict[str, Any] | None:
    path = decisions_path.parent / "feature_contract.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _code_hash() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).resolve().parent
    for name in (
        "model.py",
        "model_study.py",
        "splits.py",
        "walkforward.py",
    ):
        digest.update(name.encode("utf-8"))
        digest.update((root / name).read_bytes())
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


def _write_results(path: Path, manifest: dict[str, Any]) -> None:
    stats = manifest["stats"]
    lines = [
        "# First-Board Right-Tail M2B Model",
        "",
        f"- Status: {manifest['status']}",
        f"- Feature count: {len(manifest['features'])}",
        f"- Folds with validation: {stats['folds']}",
        f"- Validation decisions: {stats['validation_decisions']}",
        f"- Validation events: {stats['validation_events']}",
        f"- Event top-decile events: {stats['top_events']}",
        (
            "- Frozen-threshold events: "
            f"{stats['frozen_threshold_events']}"
        ),
        f"- Constant fallback targets: {stats['constant_fallback_targets']}",
        "",
        (
            "Event top-decile selects ceil(10%) of unique validation "
            "events per fold. Frozen-threshold events are the first "
            "decision per event crossing the training-score q90."
        ),
        "",
        "Calibration and ranking are research outputs, not trading signals.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_model_study(
    decisions_path: Path,
    output: Path,
    config: ModelConfig,
    *,
    sessions: Sequence[date] | None = None,
    sessions_path: Path | None = None,
    folds: Sequence[dict] = DEFAULT_FOLDS,
    purge_sessions: int = 30,
) -> dict[str, Any]:
    """Run M2B in a new directory and preserve failed-run provenance."""
    decisions_path = Path(decisions_path)
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"output directory already exists: {output}")
    output.mkdir(parents=True, exist_ok=False)
    git_commit, worktree_dirty = _git_state()
    manifest: dict[str, Any] = {
        "status": "running",
        "started_at": _now(),
        "plan": "first-board-right-tail-m2b",
        "decisions_sha256": None,
        "sessions_source": None,
        "sessions_sha256": None,
        "feature_contract_sha256": None,
        "features": [],
        "feature_contract": None,
        "config": asdict(config),
        "folds": _serialize_folds(folds),
        "purge_sessions": purge_sessions,
        "code_sha256": _code_hash(),
        "git_commit": git_commit,
        "worktree_dirty": worktree_dirty,
        "calibration": [],
        "model_status": [],
    }
    write_json(output / "model_manifest.json", manifest)

    try:
        if not decisions_path.is_file():
            raise FileNotFoundError(
                f"decisions parquet not found: {decisions_path}"
            )
        decisions = pl.read_parquet(decisions_path)
        if decisions.is_empty():
            raise ValueError("decisions parquet must not be empty")
        feature_contract = _load_feature_contract(decisions_path)
        declared_features = (
            feature_contract.get("features")
            if feature_contract is not None
            else None
        )
        features = feature_columns(
            decisions,
            declared_features=declared_features,
        )
        if not features:
            raise ValueError(
                "at least one feature__* column is required"
            )
        resolved_sessions, sessions_source = _resolve_sessions(
            decisions_path,
            sessions=sessions,
            sessions_path=sessions_path,
        )
        manifest["decisions_sha256"] = sha256_file(decisions_path)
        manifest["sessions_source"] = sessions_source
        manifest["sessions_sha256"] = _sessions_sha256(resolved_sessions)
        manifest["features"] = features
        manifest["feature_contract"] = feature_contract
        contract_path = decisions_path.parent / "feature_contract.json"
        if contract_path.is_file():
            manifest["feature_contract_sha256"] = sha256_file(
                contract_path
            )

        result = run_model_walkforward(
            decisions,
            config,
            folds=folds,
            sessions=resolved_sessions,
            purge_sessions=purge_sessions,
        )
        write_parquet(
            result.predictions,
            output / "predictions.parquet",
        )
        write_parquet(
            result.folds,
            output / "fold_metrics.parquet",
        )
        write_parquet(
            result.top_decisions,
            output / "top_decile_events.parquet",
        )
        write_parquet(
            result.frozen_threshold_decisions,
            output / "frozen_threshold_events.parquet",
        )
        write_parquet(
            result.calibration,
            output / "calibration.parquet",
        )
        write_parquet(
            result.model_status,
            output / "model_status.parquet",
        )
        manifest["stats"] = {
            "decision_rows": decisions.height,
            "folds": result.folds.height,
            "validation_decisions": result.predictions.height,
            "validation_events": result.predictions[
                "event_id"
            ].n_unique(),
            "top_events": result.top_decisions.height,
            "frozen_threshold_events": (
                result.frozen_threshold_decisions.height
            ),
            "constant_fallback_targets": result.model_status.filter(
                pl.col("status").str.starts_with("constant_")
            ).height,
        }
        manifest["calibration"] = result.calibration.to_dicts()
        manifest["model_status"] = result.model_status.to_dicts()
        manifest["fold_metrics"] = result.folds.to_dicts()
        finished_at = _now()
        manifest["status"] = "complete"
        manifest["finished_at"] = finished_at
        _write_results(output / "RESULTS.md", manifest)
        manifest["checks"] = artifact_checks(output)
        write_json(output / "model_manifest.json", manifest)
        return manifest
    except Exception as exc:
        manifest.pop("finished_at", None)
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        if "stats" in manifest:
            with suppress(OSError):
                _write_results(output / "RESULTS.md", manifest)
        write_json(output / "model_manifest.json", manifest)
        raise


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the first-board right-tail M2B model study",
    )
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sessions", type=Path)
    parser.add_argument("--max-iter", type=int, default=150)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    manifest = run_model_study(
        args.decisions,
        args.output,
        ModelConfig(max_iter=args.max_iter),
        sessions_path=args.sessions,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
