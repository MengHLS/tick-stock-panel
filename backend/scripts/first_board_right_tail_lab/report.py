"""Artifact writers for first-board right-tail research runs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import polars as pl


def write_json(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_suffix(f"{path.suffix}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    temp.replace(path)


def write_parquet(frame: pl.DataFrame, path: Path) -> None:
    temp = path.with_suffix(f"{path.suffix}.tmp")
    frame.write_parquet(temp)
    temp.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_checks(output: Path) -> dict[str, str]:
    return {
        path.name: sha256_file(path)
        for path in sorted(output.iterdir())
        if path.is_file() and not path.name.endswith("manifest.json")
    }


def write_results(
    path: Path,
    manifest: dict[str, Any],
) -> None:
    stats = manifest["stats"]
    lines = [
        "# First-Board Right-Tail Study",
        "",
        f"- Status: {manifest['status']}",
        f"- Data generation: `{manifest['data_generation']}`",
        f"- Trading sessions: {stats['sessions']}",
        f"- Events: {stats['events']}",
        f"- Exclusions: {stats['exclusions']}",
        f"- Trigger candidates: {stats['trigger_candidates']}",
        f"- Rule unavailable records: {stats['rule_unavailable']}",
        f"- Filled events: {stats['filled_events']}",
        f"- Completed labels: {stats['labels']}",
        f"- Decision samples: {stats.get('decision_count', 0)}",
        f"- Market-fillable decisions: {stats.get('market_fillable_count', 0)}",
        f"- Exit variant rows: {stats.get('exit_variant_rows', 0)}",
        f"- Coverage incomplete events: {stats['coverage_incomplete_events']}",
        "",
        "This report is a research artifact, not a live-trading result.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
