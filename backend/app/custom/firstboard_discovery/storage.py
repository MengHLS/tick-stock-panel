"""Persistent snapshots for first-board factor discovery."""
from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import threading
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import polars as pl

_RUN_ID = re.compile(r"^[0-9A-Za-z_-]{8,80}$")


class FirstboardDiscoveryStore:
    """Save reports and complete event rows under the user data directory."""

    def __init__(self, data_dir: Path) -> None:
        self.root = Path(data_dir) / "user_data" / "firstboard_discovery" / "runs"
        self._lock = threading.Lock()

    def save(self, report: dict[str, Any], events: list[dict[str, Any]]) -> tuple[str, str]:
        saved_at = datetime.now(UTC).isoformat(timespec="seconds")
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"{stamp}-{uuid.uuid4().hex[:10]}"
        saved_report = {**report, "run_id": run_id, "saved_at": saved_at}
        metadata = _metadata(saved_report, events)
        run_dir = self.root / run_id

        with self._lock:
            run_dir.mkdir(parents=True, exist_ok=False)
            try:
                _write_json_atomic(run_dir / "report.json", saved_report)
                _write_events_atomic(run_dir / "events.parquet", events)
                # Metadata is the completion marker used by list_runs().
                _write_json_atomic(run_dir / "metadata.json", metadata)
            except Exception:
                shutil.rmtree(run_dir, ignore_errors=True)
                raise
        return run_id, saved_at

    def list_runs(self) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for run_dir in self.root.iterdir():
            if not run_dir.is_dir() or not _valid_run_id(run_dir.name):
                continue
            path = run_dir / "metadata.json"
            if not path.is_file():
                continue
            try:
                rows.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        rows.sort(key=lambda item: str(item.get("saved_at") or ""), reverse=True)
        return rows

    def load_report(self, run_id: str) -> dict[str, Any]:
        path = self._run_dir(run_id) / "report.json"
        if not path.is_file():
            raise FileNotFoundError(run_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def load_events(self, run_id: str) -> list[dict[str, Any]]:
        run_dir = self._run_dir(run_id)
        parquet = run_dir / "events.parquet"
        if parquet.is_file():
            return pl.read_parquet(parquet).to_dicts()
        path = run_dir / "events.jsonl.gz"
        if not path.is_file():
            raise FileNotFoundError(run_id)
        rows: list[dict[str, Any]] = []
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    def load_event_page(
        self,
        run_id: str,
        *,
        rule_id: str | None,
        page: int,
        page_size: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        run_dir = self._run_dir(run_id)
        parquet = run_dir / "events.parquet"
        if parquet.is_file():
            frame = pl.scan_parquet(parquet)
            if rule_id:
                frame = frame.filter(pl.col("rule_ids").list.contains(rule_id))
            total = int(frame.select(pl.len()).collect().item())
            rows = (
                frame.slice((page - 1) * page_size, page_size)
                .collect()
                .to_dicts()
            )
            return total, rows
        rows = [
            row for row in self.load_events(run_id)
            if not rule_id or rule_id in row["rule_ids"]
        ]
        offset = (page - 1) * page_size
        return len(rows), rows[offset:offset + page_size]

    def _run_dir(self, run_id: str) -> Path:
        if not _valid_run_id(run_id):
            raise FileNotFoundError(run_id)
        return self.root / run_id


def _metadata(report: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    sample = report.get("sample") or {}
    split = report.get("split") or {}
    return {
        "run_id": report["run_id"],
        "saved_at": report["saved_at"],
        "algorithm_version": report.get("algorithm_version"),
        "generation": report.get("generation"),
        "params": report.get("params"),
        "sample_status": sample.get("status"),
        "total_events": sample.get("total_events", len(events)),
        "eligible_events": sample.get("eligible_events"),
        "event_count": len(events),
        "factor_count": len(report.get("factors") or []),
        "rule_count": len(report.get("rules") or []),
        "train_count": split.get("train_count"),
        "validation_count": split.get("validation_count"),
        "elapsed_ms": report.get("elapsed_ms"),
    }


def _valid_run_id(run_id: str) -> bool:
    return bool(_RUN_ID.fullmatch(run_id))


def _write_json_atomic(path: Path, payload: Any) -> None:
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                allow_nan=False,
                default=_json_default,
                separators=(",", ":"),
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _write_events_atomic(path: Path, events: list[dict[str, Any]]) -> None:
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp.parquet")
    try:
        frame = (
            pl.DataFrame(events, infer_schema_length=len(events))
            if events else pl.DataFrame(schema={"event_id": pl.Utf8})
        )
        frame.write_parquet(temp, compression="zstd")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")
