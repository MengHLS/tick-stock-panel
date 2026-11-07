"""Adapters from core repositories to stable extension read contracts."""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.extensions.contracts import EnrichedPanelRead, MarketDataRead


class RepositoryMarketData:
    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def get_instruments(self, asset_type: str = "stock") -> pl.DataFrame:
        return self._repository.get_instruments_asset(asset_type)

    def get_historical_shares(self) -> pl.DataFrame:
        return self._repository.get_historical_shares()

    def get_daily_batch(
        self,
        symbols: list[str],
        start: date,
        end: date,
        columns: list[str] | None = None,
    ) -> pl.DataFrame:
        return self._repository.get_daily_batch(symbols, start, end, columns=columns)

    def get_minute_batch(
        self,
        symbols: list[str],
        trade_date: date,
        asset_type: str = "stock",
    ) -> pl.DataFrame:
        return self._repository.get_minute_batch(
            symbols,
            trade_date,
            asset_type=asset_type,
        )

    def list_minute_dates(
        self,
        start: date,
        end: date,
        asset_type: str = "stock",
    ) -> list[date]:
        return self._repository.list_minute_dates(
            start,
            end,
            asset_type=asset_type,
        )

    def latest_minute_date(self, asset_type: str = "stock") -> date | None:
        if asset_type == "stock":
            getter = getattr(self._repository, "latest_minute_date_global", None)
            if callable(getter):
                return getter()
        dates = self._repository.list_minute_dates(
            date.min,
            date.max,
            asset_type=asset_type,
        )
        return max(dates, default=None)

    def earliest_minute_date(self, asset_type: str = "stock") -> date | None:
        if asset_type == "stock":
            getter = getattr(self._repository, "earliest_minute_date", None)
            if callable(getter):
                return getter()
        dates = self._repository.list_minute_dates(
            date.min,
            date.max,
            asset_type=asset_type,
        )
        return min(dates, default=None)

    def list_trading_dates(
        self,
        start: date,
        end: date,
        asset_type: str = "stock",
    ) -> list[date]:
        return self._repository.list_enriched_dates(
            start,
            end,
            asset_type=asset_type,
        )

    def latest_daily_date(self) -> date | None:
        return self._repository.latest_daily_date()

    def get_st_history(self) -> pl.DataFrame:
        return self._repository.get_st_history()

    def get_adj_factors(self, day: date) -> pl.DataFrame:
        return self._files().get_adj_factors(day)

    def _files(self) -> "FileMarketData":
        return FileMarketData(self._repository.store.data_dir)

    def read_dataset_partition(
        self,
        dataset: str,
        day: date,
        columns: list[str] | None = None,
        *,
        file_name: str = "part.parquet",
    ) -> pl.DataFrame:
        return self._files().read_dataset_partition(
            dataset,
            day,
            columns,
            file_name=file_name,
        )

    def dataset_partition_dates(
        self,
        dataset: str,
        start: date,
        end: date,
    ) -> list[date]:
        return self._files().dataset_partition_dates(dataset, start, end)

    def dataset_partition_signature(self, dataset: str, suffix: str) -> str:
        return self._files().dataset_partition_signature(dataset, suffix)


class RepositoryEnrichedPanel:
    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def latest(
        self,
        asset_type: str = "stock",
        *,
        symbols: list[str] | None = None,
        end: date | None = None,
        refresh: bool = True,
    ) -> tuple[pl.DataFrame, date | None]:
        if asset_type == "stock":
            frame, observed = self._repository.get_enriched_latest(
                symbols=symbols,
                end=end,
            )
        else:
            frame, observed = self._repository.get_enriched_latest_asset(
                asset_type,
                refresh=refresh,
            )
            if symbols is not None and "symbol" in frame.columns:
                frame = frame.filter(pl.col("symbol").is_in(symbols))
            if end is not None and "date" in frame.columns:
                frame = frame.filter(pl.col("date") <= end)
        return frame, observed

    def latest_date(self, asset_type: str = "stock") -> date | None:
        loader = getattr(self._repository, "latest_enriched_date", None)
        return loader(asset_type) if callable(loader) else None

    def range(
        self,
        start: date,
        end: date,
        symbols: list[str] | None = None,
        columns: list[str] | None = None,
    ) -> pl.DataFrame | None:
        return self._repository.get_enriched_range(
            start,
            end,
            symbols=symbols,
            columns=columns,
        )

    def data_generation(self, asset_type: str = "stock") -> str | None:
        return self._repository.get_matrix_data_generation(asset_type)


class RepositoryAnalysis:
    """Adapter for assistant/research reads; repository stays internal to core."""

    def __init__(
        self,
        repository: Any = None,
        quote_service: Any = None,
        depth_service: Any = None,
    ) -> None:
        self._repository = repository
        self._quote_service = quote_service
        self._depth_service = depth_service

    def quotes(self, symbols: list[str]) -> pl.DataFrame:
        frames: list[pl.DataFrame] = []
        if self._quote_service is not None:
            frame = self._quote_service.get_quotes_compat()
            if frame is not None and not frame.is_empty() and "symbol" in frame.columns:
                frames.append(frame.filter(pl.col("symbol").is_in(symbols)))
        found = set(frames[0]["symbol"].to_list()) if frames else set()
        missing = [symbol for symbol in symbols if symbol not in found]
        if missing and self._repository is not None:
            by_asset: dict[str, list[str]] = {}
            for symbol in missing:
                asset_type = self.asset_type(symbol)
                if asset_type != "stock":
                    by_asset.setdefault(asset_type, []).append(symbol)
            for asset_type, members in by_asset.items():
                frame, _ = self._repository.get_enriched_latest_asset(asset_type)
                if (
                    frame is None
                    or frame.is_empty()
                    or "symbol" not in frame.columns
                ):
                    continue
                frames.append(frame.filter(pl.col("symbol").is_in(members)))
        return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()

    def names(self, symbols: list[str]) -> dict[str, str]:
        if self._repository is None:
            return {}
        return self._repository.get_name_map(symbols)

    def asset_type(self, symbol: str) -> str:
        if self._repository is None:
            return "stock"
        return str(self._repository.resolve_asset_type(symbol))

    def enriched_latest(
        self,
        asset_type: str = "stock",
        *,
        refresh: bool = True,
    ) -> tuple[pl.DataFrame, date | None]:
        if self._repository is None:
            return pl.DataFrame(), None
        if asset_type == "stock":
            return self._repository.get_enriched_latest()
        return self._repository.get_enriched_latest_asset(
            asset_type,
            refresh=refresh,
        )

    def daily(self, symbol: str, start: date, end: date) -> pl.DataFrame:
        if self._repository is None:
            return pl.DataFrame()
        return self._repository.get_daily_asset(
            self.asset_type(symbol),
            symbol,
            start,
            end,
        )

    def latest_intraday(
        self,
        symbol: str,
        fallback_date: date | None = None,
    ) -> tuple[pl.DataFrame, date | None]:
        from app.market_time import cn_today

        if self._repository is None:
            return pl.DataFrame(), None
        asset_type = self.asset_type(symbol)
        _, trade_date = self._repository.get_enriched_latest_asset(
            asset_type,
            refresh=False,
        )
        trade_date = trade_date or fallback_date or cn_today()
        return (
            self._repository.get_minute(symbol, trade_date, asset_type),
            trade_date,
        )

    def index_quotes(self) -> pl.DataFrame:
        if self._quote_service is None:
            return pl.DataFrame()
        return self._quote_service.get_index_quotes()

    def listing_dates(self) -> dict[str, date]:
        if self._repository is None:
            return {}
        instruments = self._repository.get_instruments_asset("stock")
        if (
            instruments is None
            or instruments.is_empty()
            or "symbol" not in instruments.columns
            or "listing_date" not in instruments.columns
        ):
            return {}
        result: dict[str, date] = {}
        for row in instruments.drop_nulls(subset=["listing_date"]).iter_rows(
            named=True
        ):
            raw = row.get("listing_date")
            parsed: date | None = None
            if isinstance(raw, datetime):
                parsed = raw.date()
            elif isinstance(raw, date):
                parsed = raw
            elif isinstance(raw, str) and len(raw) >= 10:
                try:
                    parsed = date.fromisoformat(raw[:10])
                except ValueError:
                    parsed = None
            if parsed is not None:
                result[str(row["symbol"])] = parsed
        return result

    def dataset_dates(self, dataset: str) -> list[str]:
        if self._repository is None:
            return []
        data_dir = getattr(
            getattr(self._repository, "store", None),
            "data_dir",
            None,
        )
        if data_dir is None:
            return []
        root = data_dir / dataset
        if not root.exists():
            return []
        return sorted(
            item.name[5:]
            for item in root.iterdir()
            if item.is_dir() and item.name.startswith("date=")
        )

    def market_overview(self) -> dict[str, Any]:
        from app.services.market_overview_builder import build_market_overview

        return build_market_overview(
            self._repository,
            quote_service=self._quote_service,
            depth_service=self._depth_service,
        )

    def sector_rotation(self, kind: str, top: int) -> dict[str, Any]:
        from app.services.sector_rotation import build_sector_rotation

        return build_sector_rotation(self._repository, kind=kind, top=top)

    def abnormal_moves(self, kind: str, limit: int) -> dict[str, Any]:
        from app.services.abnormal_moves import build_intraday, build_overview

        if kind == "intraday":
            return build_intraday(self._repository, limit=limit)
        return build_overview(
            self._repository,
            self._quote_service,
            limit=limit,
        )

    async def trigger_pipeline(self, capabilities: Any) -> dict[str, Any]:
        from app.api.pipeline import trigger_pipeline_job

        return await trigger_pipeline_job(
            self._repository,
            capabilities,
            self._quote_service,
        )

    async def trigger_minute_extend(
        self,
        capabilities: Any,
        days: int,
    ) -> dict[str, Any]:
        from app.api.kline import trigger_minute_sync

        return await trigger_minute_sync(
            self._repository,
            capabilities,
            override_days=days,
            extend_flag=True,
        )

    def invalidate_cache(self) -> None:
        if self._repository is not None:
            self._repository.clear_cache()


class FileMarketData:
    """Storage-backed MarketDataRead for extension jobs that only receive data_dir."""

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)

    def get_instruments(self, asset_type: str = "stock") -> pl.DataFrame:
        root = self.data_dir / (
            "instruments" if asset_type == "stock" else f"instruments_{asset_type}"
        )
        files = sorted(root.rglob("*.parquet")) if root.exists() else []
        return pl.read_parquet([str(path) for path in files]) if files else pl.DataFrame()

    def get_historical_shares(self) -> pl.DataFrame:
        # The file-only adapter is used by event jobs that never request shares.
        return pl.DataFrame()

    def get_daily_batch(
        self,
        symbols: list[str],
        start: date,
        end: date,
        columns: list[str] | None = None,
    ) -> pl.DataFrame:
        # The runtime MarketDataRead adapter reads the enriched daily panel
        # (adjusted OHLC plus raw_close). Keep the file-only adapter on the same
        # contract so extension jobs do not silently switch to unadjusted bars.
        dataset = "kline_daily_enriched"
        frames: list[pl.DataFrame] = []
        for day in self.dataset_partition_dates(dataset, start, end):
            path = self.data_dir / dataset / f"date={day.isoformat()}" / "part.parquet"
            if not path.is_file():
                continue
            selected = columns
            if columns:
                available = set(pl.scan_parquet(path).collect_schema().names())
                selected = [name for name in columns if name in available]
            frames.append(pl.read_parquet(path, columns=selected))
        if not frames:
            return pl.DataFrame()
        frame = pl.concat(frames, how="diagonal_relaxed")
        return frame.filter(pl.col("symbol").is_in(symbols)) if symbols else frame

    def get_minute_batch(
        self,
        symbols: list[str],
        trade_date: date,
        asset_type: str = "stock",
    ) -> pl.DataFrame:
        dataset = "kline_minute" if asset_type == "stock" else f"kline_{asset_type}_minute"
        frame = self.read_dataset_partition(dataset, trade_date)
        return frame.filter(pl.col("symbol").is_in(symbols)) if symbols else frame

    def list_minute_dates(
        self,
        start: date,
        end: date,
        asset_type: str = "stock",
    ) -> list[date]:
        dataset = "kline_minute" if asset_type == "stock" else f"kline_{asset_type}_minute"
        return self.dataset_partition_dates(dataset, start, end)

    def latest_minute_date(self, asset_type: str = "stock") -> date | None:
        dates = self.list_minute_dates(date.min, date.max, asset_type)
        return dates[-1] if dates else None

    def earliest_minute_date(self, asset_type: str = "stock") -> date | None:
        dates = self.list_minute_dates(date.min, date.max, asset_type)
        return dates[0] if dates else None

    def list_trading_dates(
        self,
        start: date,
        end: date,
        asset_type: str = "stock",
    ) -> list[date]:
        dataset = (
            "kline_daily_enriched"
            if asset_type == "stock"
            else f"kline_{asset_type}_daily_enriched"
        )
        return self.dataset_partition_dates(dataset, start, end)

    def latest_daily_date(self) -> date | None:
        dates = self.dataset_partition_dates(
            "kline_daily_enriched",
            date.min,
            date.max,
        )
        return dates[-1] if dates else None

    def get_st_history(self) -> pl.DataFrame:
        from app.data_providers.st_history import load_st_history

        return load_st_history(self.data_dir)

    def get_adj_factors(self, day: date) -> pl.DataFrame:
        root = self.data_dir / "adj_factor"
        files = sorted(root.rglob("*.parquet")) if root.exists() else []
        if not files:
            return pl.DataFrame()
        return pl.scan_parquet([str(path) for path in files]).filter(
            pl.col("trade_date") == day
        ).collect()

    def read_dataset_partition(
        self,
        dataset: str,
        day: date,
        columns: list[str] | None = None,
        *,
        file_name: str = "part.parquet",
    ) -> pl.DataFrame:
        path = self.data_dir / dataset / f"date={day.isoformat()}" / file_name
        if not path.exists():
            return pl.DataFrame()
        return pl.read_parquet(path, columns=columns)

    def dataset_partition_dates(
        self,
        dataset: str,
        start: date,
        end: date,
    ) -> list[date]:
        root = self.data_dir / dataset
        if not root.exists():
            return []
        result: list[date] = []
        for item in root.glob("date=*"):
            if not item.is_dir():
                continue
            try:
                day = date.fromisoformat(item.name[5:])
            except ValueError:
                continue
            if start <= day <= end:
                result.append(day)
        return sorted(set(result))

    def dataset_partition_signature(self, dataset: str, suffix: str) -> str:
        part_dir = self.data_dir / dataset / suffix
        digest = hashlib.sha256()
        for path in sorted(part_dir.glob("*.parquet")):
            stat = path.stat()
            digest.update(path.name.encode("utf-8"))
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(str(stat.st_mtime_ns).encode("ascii"))
        return digest.hexdigest()


def market_data_from_data_dir(data_dir: Path | str) -> MarketDataRead:
    return FileMarketData(data_dir)


def repository_read_adapters(
    repository: Any,
) -> tuple[MarketDataRead, EnrichedPanelRead]:
    return RepositoryMarketData(repository), RepositoryEnrichedPanel(repository)
