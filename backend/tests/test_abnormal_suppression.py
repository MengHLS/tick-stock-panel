"""异动阈值价格压制测算 — 滚动窗口、正负方向与边界。"""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.abnormal import router
from app.indicators.pipeline import _benchmark_cache
from app.services.abnormal_moves import (
    _hist_cache,
    _hist_cache_lock,
    build_suppression_schedule,
)


def _write_index_daily(tmp_path, rows: list[tuple[str, date, float]]) -> None:
    df = pl.DataFrame({
        "symbol": [r[0] for r in rows],
        "date": [r[1] for r in rows],
        "close": [r[2] for r in rows],
    })
    for day in sorted({r[1] for r in rows}):
        target = tmp_path / "kline_index_daily" / f"date={day.isoformat()}"
        target.mkdir(parents=True, exist_ok=True)
        df.filter(pl.col("date") == day).write_parquet(target / "part.parquet")


class _FakeRepo:
    def __init__(self, latest: pl.DataFrame, daily: pl.DataFrame, data_dir, cache_date: date) -> None:
        self._latest = latest
        self._daily = daily
        self._cache_date = cache_date
        self.store = SimpleNamespace(data_dir=data_dir)

    def get_enriched_latest(self):
        return self._latest, self._cache_date

    def get_name_map(self, symbols=None):
        return {}

    def get_daily(self, symbol, start, end, columns=None):
        return self._daily.filter(
            (pl.col("date") >= start) & (pl.col("date") <= end)
        )


def _clear_caches() -> None:
    with _hist_cache_lock:
        _hist_cache.clear()
    _benchmark_cache.clear()


def _build_repo(tmp_path, closes: list[float], deviate_30d: float):
    days = [date(2026, 9, 1) + timedelta(days=i) for i in range(len(closes))]
    _write_index_daily(
        tmp_path,
        [("399107.SZ", day, 100.0) for day in days],
    )
    latest = pl.DataFrame({
        "symbol": ["002242.SZ"],
        "name": ["九阳股份"],
        "close": [closes[-1]],
        "deviate_3d": [None],
        "deviate_10d": [None],
        "deviate_30d": [deviate_30d],
    })
    daily = pl.DataFrame({"symbol": ["002242.SZ"] * len(days), "date": days, "close": closes})
    return _FakeRepo(latest, daily, tmp_path, days[-1])


def test_suppression_30d_rolls_base_forward(tmp_path) -> None:
    _clear_caches()
    closes = [20.0] * 40
    closes[9] = 10.0   # 今日 30 日窗口基准
    closes[10] = 12.0  # 明日窗口基准
    closes[11] = 11.0  # 后日窗口基准
    closes[-1] = 20.0

    body = build_suppression_schedule(
        _build_repo(tmp_path, closes, deviate_30d=1.0),
        symbol="002242.SZ",
    )

    window = body["windows"]["30d"]
    assert window["direction"] == "up"
    assert window["threshold"] == 2.0
    assert window["days"][0]["cap"] == 30.0
    assert window["days"][0]["room_pct"] == 0.5
    assert window["days"][1]["cap"] == 36.0
    assert window["days"][1]["room_pct"] == 0.8
    assert window["days"][2]["cap"] == 33.0
    assert window["days"][2]["room_pct"] == 0.65
    assert body["nearest"]["window"] == "30d"


def test_suppression_negative_direction_returns_floor(tmp_path) -> None:
    _clear_caches()
    closes = [20.0] * 40
    closes[9] = 20.0
    closes[-1] = 10.0

    body = build_suppression_schedule(
        _build_repo(tmp_path, closes, deviate_30d=-0.5),
        symbol="002242.SZ",
    )

    window = body["windows"]["30d"]
    assert window["direction"] == "down"
    assert window["threshold"] == 0.7
    assert window["days"][0]["cap"] == 6.0
    assert window["days"][0]["room_pct"] == -0.4


def test_suppression_insufficient_history(tmp_path) -> None:
    _clear_caches()
    days = [date(2026, 9, 1) + timedelta(days=i) for i in range(5)]
    _write_index_daily(tmp_path, [("399107.SZ", day, 100.0) for day in days])
    latest = pl.DataFrame({
        "symbol": ["002242.SZ"],
        "name": ["九阳股份"],
        "close": [20.0],
        "deviate_30d": [1.0],
    })
    daily = pl.DataFrame({"symbol": ["002242.SZ"] * len(days), "date": days, "close": [10.0] * len(days)})
    repo = _FakeRepo(latest, daily, tmp_path, days[-1])

    body = build_suppression_schedule(repo, symbol="002242.SZ")
    assert body["reason"] == "insufficient_history"


def test_suppression_short_history_keeps_available_window(tmp_path) -> None:
    _clear_caches()
    days = [date(2026, 9, 1) + timedelta(days=i) for i in range(15)]
    _write_index_daily(tmp_path, [("399107.SZ", day, 100.0) for day in days])
    closes = [10.0] * len(days)
    closes[-1] = 12.0
    latest = pl.DataFrame({
        "symbol": ["002242.SZ"],
        "name": ["九阳股份"],
        "close": [12.0],
        "deviate_3d": [None],
        "deviate_10d": [0.2],
        "deviate_30d": [None],
    })
    daily = pl.DataFrame({"symbol": ["002242.SZ"] * len(days), "date": days, "close": closes})
    repo = _FakeRepo(latest, daily, tmp_path, days[-1])

    body = build_suppression_schedule(repo, symbol="002242.SZ")
    assert "10d" in body["windows"]
    assert "30d" not in body["windows"]
    assert body["windows"]["10d"]["days"][0]["cap"] == 20.0


def test_suppression_missing_symbol(tmp_path) -> None:
    _clear_caches()
    latest = pl.DataFrame({"symbol": ["600000.SH"], "close": [10.0], "deviate_30d": [0.1]})
    repo = _FakeRepo(latest, pl.DataFrame(), tmp_path, date(2026, 9, 5))
    body = build_suppression_schedule(repo, symbol="002242.SZ")
    assert body["reason"] == "no_snapshot"


def test_suppression_api_happy_path(tmp_path) -> None:
    _clear_caches()
    closes = [20.0] * 40
    closes[9] = 10.0
    closes[10] = 12.0
    closes[-1] = 20.0
    repo = _build_repo(tmp_path, closes, deviate_30d=1.0)

    app = FastAPI()
    app.include_router(router)
    app.state.repo = repo
    client = TestClient(app)

    resp = client.get(
        "/api/abnormal/suppression",
        params={"symbol": "002242.SZ", "forward_days": 2},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["windows"]["30d"]["days"][1]["cap"] == 36.0
