"""Atomic persistence for the live first-board observation pool."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def empty_state() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": None,
        "data_as_of": None,
        "events": [],
        "runtime": {},
    }


class FirstBoardRightTailStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "user_data" / "first_board_right_tail" / "state.json"
        self._lock = threading.Lock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return empty_state()
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"首板观察池状态读取失败: {exc}") from exc
            if not isinstance(payload, dict) or payload.get("version") != 1:
                raise ValueError("首板观察池状态版本不受支持")
            if not isinstance(payload.get("events"), list):
                raise ValueError("首板观察池 events 必须是数组")
            return deepcopy(payload)

    def save(self, payload: dict[str, Any]) -> None:
        clean = deepcopy(payload)
        clean["version"] = 1
        clean["updated_at"] = datetime.now(UTC).isoformat()
        encoded = json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path: str | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=".state-",
                    suffix=".tmp",
                    delete=False,
                ) as handle:
                    temp_path = handle.name
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, self.path)
            finally:
                if temp_path:
                    Path(temp_path).unlink(missing_ok=True)
