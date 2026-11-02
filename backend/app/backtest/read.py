"""Read-only backtest data access exposed to backend extensions."""
from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl


class BacktestReadAdapter:
    def __init__(self, repository: Any) -> None:
        from app.backtest.engine import BacktestEngine

        self._engine = BacktestEngine(repository)

    def data_generation(self, asset_type: str = "stock") -> str | None:
        return self._engine.data_generation(asset_type)

    def data_generation_await(
        self,
        asset_type: str = "stock",
        *,
        timeout_s: float = 300.0,
    ) -> str | None:
        return self._engine.data_generation_await(
            asset_type,
            timeout_s=timeout_s,
        )

    def load_panel(
        self,
        symbols: list[str] | None,
        start: date,
        end: date,
        columns: list[str] | None = None,
        asset_type: str = "stock",
        *,
        expected_generation: str | None = None,
    ) -> pl.DataFrame:
        return self._engine.load_panel(
            symbols,
            start,
            end,
            columns=columns,
            asset_type=asset_type,
            expected_generation=expected_generation,
        )
