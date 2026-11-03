"""Read-only completed and saved backtest results for extensions."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from app.backtest import result_store


class BacktestResultReadAdapter:
    """Stable adapter over the core result cache and immutable saved snapshots."""

    def __init__(self, data_dir: str | Path) -> None:
        self._data_dir = Path(data_dir)

    def list_saved(self, page: int = 1, page_size: int = 20) -> dict:
        return result_store.list_saved_results(
            self._data_dir,
            page=page,
            page_size=page_size,
        )

    def get_saved(self, saved_id: str) -> dict:
        return deepcopy(result_store.get_saved_result(self._data_dir, saved_id))

    def get_completed(self, run_id: str) -> dict | None:
        result = result_store.get_completed_run(run_id)
        return None if result is None else deepcopy(result)
