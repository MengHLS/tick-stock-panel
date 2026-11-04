"""Versioned JSON storage for user-edited industry-chain graphs."""
from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.custom.industry_chain.defaults import build_default_graph
from app.custom.industry_chain.models import IndustryChainGraph, validate_graph
from app.services.fs_utils import atomic_write_text

_LOCK = threading.RLock()
_CACHE: dict[Path, tuple[tuple[int, int] | None, dict[str, Any]]] = {}


def graph_path(data_dir: Path) -> Path:
    return Path(data_dir) / "user_data" / "industry_chain" / "graph.json"


def load_graph(data_dir: Path) -> dict[str, Any]:
    path = graph_path(data_dir)
    with _LOCK:
        if not path.exists():
            return save_graph(data_dir, build_default_graph(), expected_updated_at=None)
        signature = _signature(path)
        cached = _CACHE.get(path)
        if cached and cached[0] == signature:
            return cached[1]
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            graph = validate_graph(IndustryChainGraph.model_validate(raw))
        except Exception as exc:
            raise ValueError(f"产业链图谱文件无法读取: {path}: {exc}") from exc
        result = graph.model_dump()
        _CACHE[path] = (signature, result)
        return result


def save_graph(
    data_dir: Path,
    graph: IndustryChainGraph,
    *,
    expected_updated_at: str | None = None,
) -> dict[str, Any]:
    path = graph_path(data_dir)
    with _LOCK:
        if path.exists() and expected_updated_at is not None:
            current = json.loads(path.read_text(encoding="utf-8"))
            if str(current.get("updated_at") or "") != expected_updated_at:
                raise ConflictError("图谱已被其他窗口修改，请刷新后重试")

        validated = validate_graph(graph)
        updated = validated.model_copy(
            update={"updated_at": datetime.now(UTC).isoformat()}
        )
        payload = updated.model_dump()
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        _CACHE[path] = (_signature(path), payload)
        return payload


class ConflictError(RuntimeError):
    pass


def _signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return None
