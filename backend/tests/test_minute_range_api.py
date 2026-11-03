"""多日分时 API 契约。"""

import asyncio
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl
import pytest
from fastapi import HTTPException

from app.api import kline as kline_api
from app.market_time import cn_today
from app.tickflow.repository import DataStore, KlineRepository


def _request(repo=None, capset=None):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                repo=repo or MagicMock(),
                capabilities=capset or MagicMock(),
            )
        )
    )


def test_minute_range_returns_latest_sessions_with_previous_closes():
    repo = MagicMock()
    repo.resolve_asset_type.return_value = "stock"
    # _get_stock_info 走 instruments 内存缓存 (不再走 execute_one DuckDB 查询)
    repo.get_instruments.return_value = pl.DataFrame({
        "symbol": ["600000.SH"],
        "name": ["浦发银行"],
        "total_shares": [1.0],
        "float_shares": [1.0],
    })
    repo.list_minute_dates.return_value = [
        date(2026, 8, 5),
        date(2026, 8, 6),
        date(2026, 8, 7),
    ]
    repo.get_minute_by_dates.return_value = pl.DataFrame({
        "symbol": ["600000.SH"] * 3,
        "datetime": [
            datetime(2026, 8, 5, 1, 30),
            datetime(2026, 8, 6, 1, 30),
            datetime(2026, 8, 7, 1, 30),
        ],
        "open": [10.0, 11.0, 12.0],
        "high": [10.2, 11.2, 12.2],
        "low": [9.8, 10.8, 11.8],
        "close": [10.1, 11.1, 12.1],
        "volume": [100.0, 110.0, 120.0],
        "amount": [101_000.0, 122_100.0, 145_200.0],
    })
    repo.list_enriched_dates.return_value = [
        date(2026, 8, 4),
        date(2026, 8, 5),
        date(2026, 8, 6),
        date(2026, 8, 7),
    ]
    repo.get_enriched_by_dates.return_value = pl.DataFrame({
        "date": [
            date(2026, 8, 4),
            date(2026, 8, 5),
            date(2026, 8, 6),
            date(2026, 8, 7),
        ],
        "close": [9.9, 10.1, 11.1, 12.1],
    })

    result = kline_api.get_minute_range(_request(repo), "600000.SH", 2)

    assert result["name"] == "浦发银行"
    assert result["requested_days"] == 2
    assert result["source"] == "local"
    assert [session["date"] for session in result["sessions"]] == [
        "2026-08-06",
        "2026-08-07",
    ]
    assert [session["prev_close"] for session in result["sessions"]] == [
        10.1,
        11.1,
    ]
    assert result["sessions"][0]["rows"][0]["close"] == 11.1
    repo.get_minute_range.assert_not_called()
    repo.get_minute_by_dates.assert_called_once_with(
        ["600000.SH"],
        [date(2026, 8, 6), date(2026, 8, 7)],
        asset_type="stock",
    )
    repo.get_daily_asset.assert_not_called()
    repo.get_enriched_by_dates.assert_called_once_with(
        ["600000.SH"],
        [date(2026, 8, 5), date(2026, 8, 6)],
        asset_type="stock",
        columns=["date", "close"],
    )


def test_minute_range_does_not_read_stock_store_for_index():
    repo = MagicMock()
    repo.resolve_asset_type.return_value = "index"
    repo.get_instruments_asset.return_value = pl.DataFrame()

    result = kline_api.get_minute_range(_request(repo), "000001.SH", 10)

    assert result["asset_type"] == "index"
    assert result["sessions"] == []
    repo.get_minute_range.assert_not_called()
    repo.get_minute_by_dates.assert_not_called()


def test_minute_by_dates_reads_date_partition_on_windows(tmp_path):
    day = date(2026, 8, 7)
    part = tmp_path / "kline_minute" / f"date={day.isoformat()}" / "part.parquet"
    part.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["600000.SH"],
        "datetime": [datetime(2026, 8, 7, 9, 30)],
        "open": [10.0],
        "high": [10.2],
        "low": [9.8],
        "close": [10.1],
        "volume": [100.0],
        "amount": [101_000.0],
    }).write_parquet(part)
    repo = KlineRepository(DataStore(tmp_path))

    result = repo.get_minute_by_dates(["600000.SH"], [day], asset_type="stock")

    assert result.height == 1
    assert result["symbol"].to_list() == ["600000.SH"]


def test_enriched_by_dates_reads_date_partition_on_windows(tmp_path):
    day = date(2026, 8, 7)
    part = tmp_path / "kline_daily_enriched" / f"date={day.isoformat()}" / "part.parquet"
    part.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["600000.SH"],
        "date": [day],
        "close": [10.1],
    }).write_parquet(part)
    repo = KlineRepository(DataStore(tmp_path))

    result = repo.get_enriched_by_dates(
        ["600000.SH"], [day], asset_type="stock", columns=["date", "close"],
    )

    assert result.to_dicts() == [{"date": day, "close": 10.1}]


def test_enriched_dates_refresh_after_partition_becomes_complete(tmp_path):
    root = tmp_path / "kline_daily_enriched"
    partition = root / "date=2026-08-07"
    partition.mkdir(parents=True)
    repo = KlineRepository(DataStore(tmp_path))

    assert repo.list_enriched_dates(
        date(2026, 8, 1), date(2026, 8, 31), asset_type="stock",
    ) == []

    pl.DataFrame({
        "symbol": ["600000.SH"],
        "date": [date(2026, 8, 7)],
        "close": [10.1],
    }).write_parquet(partition / "part.parquet")

    assert repo.list_enriched_dates(
        date(2026, 8, 1), date(2026, 8, 31), asset_type="stock",
    ) == [date(2026, 8, 7)]


def test_minute_dates_cache_tracks_new_partition_directory(tmp_path):
    first = tmp_path / "kline_minute" / "date=2026-08-06"
    second = tmp_path / "kline_minute" / "date=2026-08-07"
    first.mkdir(parents=True)
    repo = KlineRepository(DataStore(tmp_path))

    assert repo.list_minute_dates(
        date(2026, 8, 1), date(2026, 8, 31), asset_type="stock",
    ) == [date(2026, 8, 6)]

    second.mkdir()

    assert repo.list_minute_dates(
        date(2026, 8, 1), date(2026, 8, 31), asset_type="stock",
    ) == [date(2026, 8, 6), date(2026, 8, 7)]


def test_latest_minute_date_uses_recent_partition_without_duckdb(tmp_path, monkeypatch):
    day = cn_today()
    part = tmp_path / "kline_minute" / f"date={day.isoformat()}" / "part.parquet"
    part.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["600000.SH"],
        "datetime": [datetime(day.year, day.month, day.day, 9, 30)],
        "close": [10.1],
    }).write_parquet(part)
    repo = KlineRepository(DataStore(tmp_path))
    monkeypatch.setattr(
        repo,
        "execute_one",
        lambda *args, **kwargs: pytest.fail("近期 date= 分区存在时不应扫描 DuckDB 全历史视图"),
    )

    assert repo.latest_minute_date("600000.SH", asset_type="stock") == day


def test_sync_minute_single_uses_requested_days(monkeypatch):
    repo = MagicMock()
    repo.resolve_asset_type.return_value = "stock"
    capset = MagicMock()
    sync = MagicMock(return_value=2400)
    refresh = MagicMock()
    monkeypatch.setattr(kline_api, "_minute_allowed", lambda _: True)
    monkeypatch.setattr(kline_api.kline_sync, "sync_and_persist_minute", sync)
    monkeypatch.setattr("app.jobs.daily_pipeline._refresh_single_view", refresh)

    result = asyncio.run(kline_api.sync_minute_single(
        _request(repo, capset),
        {"symbol": "600000.SH", "days": 10},
    ))

    assert result["rows"] == 2400
    sync.assert_called_once_with(["600000.SH"], repo, capset, days=10, force_full_days=True)
    refresh.assert_called_once_with(repo, "kline_minute")


def test_sync_minute_single_rejects_invalid_days():
    with pytest.raises(HTTPException, match="days 必须在 1 到 30 之间"):
        asyncio.run(kline_api.sync_minute_single(
            _request(),
            {"symbol": "600000.SH", "days": 0},
        ))
