"""大表视图按需绑定 — 启动不再被 union_by_name 的逐文件 schema 绑定阻塞。

回归 (2026-10-31 用户反馈): 分钟数据导入后前端连不上后端。实测启动卡在
DataStore._register_views: kline_daily 39098 个 + kline_minute 2367 个
parquet 文件, union_by_name 绑定要逐个打开文件读 schema, 冷缓存下日线
130s、分钟 97s, 整次启动超过 20 分钟; uvicorn 在此期间未监听端口。
修复: 大表视图延后到首次查询时绑定 (CatalogException → bind_missing_view
→ 重试一次), 启动只绑定小视图。
"""
from __future__ import annotations

import datetime as dt
import threading

import duckdb
import polars as pl
import pytest

from app.tickflow.repository import DataStore, KlineRepository


def _write_minute_part(data_dir, day: str = "2026-10-30") -> None:
    d = data_dir / "kline_minute" / f"date={day}"
    d.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({
        "symbol": ["600000.SH"],
        "datetime": [dt.datetime(2026, 10, 30, 9, 31)],
        "open": [10.0], "high": [10.1], "low": [9.9], "close": [10.0],
        "volume": [100.0], "amount": [1e4],
    }).write_parquet(d / "part.parquet")


def _repo(tmp_path) -> KlineRepository:
    return KlineRepository(DataStore(tmp_path))


def test_large_views_deferred_at_startup_then_bound_on_first_query(tmp_path):
    _write_minute_part(tmp_path)
    store = DataStore(tmp_path)
    assert "kline_minute" in store._deferred_views  # 启动不绑定大表视图

    repo = KlineRepository(store)
    assert repo.execute_one("SELECT count(*) FROM kline_minute")[0] == 1
    assert "kline_minute" not in store._deferred_views  # 首次查询后已绑定


def test_small_views_bound_synchronously(tmp_path):
    """维表等小视图启动即可用, 不依赖按需绑定路径。"""
    inst = tmp_path / "instruments"
    inst.mkdir(parents=True)
    pl.DataFrame({"symbol": ["600000.SH"], "name": ["浦发银行"]}).write_parquet(
        inst / "part.parquet"
    )
    repo = _repo(tmp_path)
    assert repo.execute_one("SELECT count(*) FROM instruments")[0] == 1


def test_unified_view_binds_only_its_dependencies(tmp_path):
    """查 kline_minute_all 只绑定分钟基视图, 不牵连日线/指标。"""
    _write_minute_part(tmp_path)
    store = DataStore(tmp_path)
    repo = KlineRepository(store)

    assert repo.execute_one("SELECT count(*) FROM kline_minute_all")[0] == 1
    assert "kline_minute" not in store._deferred_views
    assert "kline_daily" in store._deferred_views  # 未牵连绑定


def test_unknown_table_still_fails_closed(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(duckdb.CatalogException):
        repo.execute_one("SELECT * FROM no_such_table")
    with pytest.raises(duckdb.CatalogException):
        repo.execute_all("SELECT * FROM no_such_table")


def test_concurrent_first_queries_share_one_bind(tmp_path):
    _write_minute_part(tmp_path)
    repo = _repo(tmp_path)
    results: list[int] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def query() -> None:
        try:
            row = repo.execute_one("SELECT count(*) FROM kline_minute")
            with lock:
                results.append(row[0])
        except BaseException as exc:  # noqa: BLE001 — 收集后断言
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=query) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors
    assert results == [1] * 8


def test_explicit_refresh_cancels_deferred_binding(tmp_path):
    """refresh_view 已绑定后, 首查不应再绑定一次。"""
    _write_minute_part(tmp_path)
    store = DataStore(tmp_path)
    repo = KlineRepository(store)
    assert repo.refresh_view("kline_minute", f"{store.data_dir.as_posix()}/kline_minute/**/*.parquet")
    assert "kline_minute" not in store._deferred_views
    assert repo.execute_one("SELECT count(*) FROM kline_minute")[0] == 1
