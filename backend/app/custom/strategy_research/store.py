"""Small, atomic JSON stores for research artifacts.

Research output lives under ``data/user_data/research/strategy_research`` and is
never written into the strategy or backtest result stores. A report directory is
only considered complete after its ``report.json`` has been atomically replaced.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_SUBDIR = Path("user_data") / "research" / "strategy_research"
INBOX_SUBDIR = "inbox"
REPORTS_SUBDIR = "reports"
EXPERIMENTS_SUBDIR = "experiments"
FACTORS_SUBDIR = "factors"
RESULTS_SUBDIR = "results"

_ID_RE = re.compile(r"^[a-z]{3}_[0-9a-f]{12}$")
_SAFE_FILE_RE = re.compile(r"^[\w.\- ()\u4e00-\u9fff]+\.json$", re.UNICODE)


class ResearchStoreError(ValueError):
    """A user-facing storage or validation failure."""


def research_root(data_dir: str | Path) -> Path:
    return Path(data_dir) / ROOT_SUBDIR


def inbox_dir(data_dir: str | Path) -> Path:
    path = research_root(data_dir) / INBOX_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def reports_dir(data_dir: str | Path) -> Path:
    path = research_root(data_dir) / REPORTS_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def experiments_dir(data_dir: str | Path) -> Path:
    path = research_root(data_dir) / EXPERIMENTS_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def factors_dir(data_dir: str | Path) -> Path:
    path = research_root(data_dir) / FACTORS_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def results_dir(data_dir: str | Path) -> Path:
    path = research_root(data_dir) / RESULTS_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def validate_id(value: str, prefix: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ResearchStoreError("无效的研究记录 ID")
    if not value.startswith(f"{prefix}_"):
        raise ResearchStoreError("无效的研究记录 ID")
    return value


def resolve_inbox_file(data_dir: str | Path, file_name: str) -> Path:
    if not isinstance(file_name, str) or not file_name.strip():
        raise ResearchStoreError("请选择 inbox 中的 JSON 基线文件")
    name = file_name.strip()
    if not _SAFE_FILE_RE.fullmatch(name) or "/" in name or "\\" in name:
        raise ResearchStoreError("基线文件名不合法")
    root = inbox_dir(data_dir).resolve()
    path = (root / name).resolve()
    if path.parent != root or not path.is_file():
        raise ResearchStoreError("基线文件不存在或不在 research inbox 中")
    return path


def list_inbox(data_dir: str | Path) -> list[dict[str, Any]]:
    root = inbox_dir(data_dir)
    items: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        if not path.is_file() or path.is_symlink():
            continue
        stat = path.stat()
        items.append(
            {
                "file_name": path.name,
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=UTC
                ).isoformat(timespec="seconds"),
            }
        )
    return items


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ResearchStoreError(f"无法读取研究文件: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ResearchStoreError(f"研究文件格式无效: {path.name}")
    return payload


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=".tmp-research-",
        suffix=".json",
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        with suppress(OSError):
            os.unlink(tmp_name)


def report_path(data_dir: str | Path, report_id: str) -> Path:
    validate_id(report_id, "rpt")
    root = reports_dir(data_dir).resolve()
    path = (root / report_id / "report.json").resolve()
    if path.parent.parent != root:
        raise ResearchStoreError("无效的研究报告 ID")
    return path


def write_report(data_dir: str | Path, report: dict[str, Any]) -> None:
    report_id = validate_id(str(report.get("report_id")), "rpt")
    write_json_atomic(report_path(data_dir, report_id), report)


def read_report(data_dir: str | Path, report_id: str) -> dict[str, Any]:
    return read_json(report_path(data_dir, report_id))


def list_reports(data_dir: str | Path, *, limit: int = 50) -> list[dict[str, Any]]:
    root = reports_dir(data_dir)
    items: list[dict[str, Any]] = []
    for path in root.glob("rpt_*/report.json"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            report = read_json(path)
            items.append(report)
        except ResearchStoreError:
            continue
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return items[: max(1, min(int(limit), 200))]


def experiment_path(data_dir: str | Path, experiment_id: str) -> Path:
    validate_id(experiment_id, "exp")
    root = experiments_dir(data_dir).resolve()
    path = (root / f"{experiment_id}.json").resolve()
    if path.parent != root:
        raise ResearchStoreError("无效的实验记录 ID")
    return path


def write_experiment(data_dir: str | Path, experiment: dict[str, Any]) -> None:
    experiment_id = validate_id(str(experiment.get("experiment_id")), "exp")
    write_json_atomic(experiment_path(data_dir, experiment_id), experiment)


def read_experiment(data_dir: str | Path, experiment_id: str) -> dict[str, Any]:
    return read_json(experiment_path(data_dir, experiment_id))


def list_experiments(
    data_dir: str | Path,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    root = experiments_dir(data_dir)
    items: list[dict[str, Any]] = []
    for path in root.glob("exp_*.json"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            items.append(read_json(path))
        except ResearchStoreError:
            continue
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return items[: max(1, min(int(limit), 500))]


def factor_path(data_dir: str | Path, factor_id: str) -> Path:
    validate_id(factor_id, "fac")
    root = factors_dir(data_dir).resolve()
    path = (root / f"{factor_id}.json").resolve()
    if path.parent != root:
        raise ResearchStoreError("无效的因子假设 ID")
    return path


def write_factor(data_dir: str | Path, factor: dict[str, Any]) -> None:
    factor_id = validate_id(str(factor.get("factor_id")), "fac")
    write_json_atomic(factor_path(data_dir, factor_id), factor)


def read_factor(data_dir: str | Path, factor_id: str) -> dict[str, Any]:
    return read_json(factor_path(data_dir, factor_id))


def list_factors(data_dir: str | Path, *, limit: int = 200) -> list[dict[str, Any]]:
    root = factors_dir(data_dir)
    items: list[dict[str, Any]] = []
    for path in root.glob("fac_*.json"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            items.append(read_json(path))
        except ResearchStoreError:
            continue
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return items[: max(1, min(int(limit), 1000))]
