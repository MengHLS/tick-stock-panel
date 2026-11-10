"""异动总览 API 筛选契约 — 参数在 limit 截断前生效。"""
from __future__ import annotations

from datetime import date

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.abnormal import router
from app.services.abnormal_moves import _hist_cache, _hist_cache_lock


class _FakeRepo:
    def __init__(self, df: pl.DataFrame) -> None:
        self._df = df

    def get_enriched_latest(self):
        return self._df, date(2026, 8, 19)

    def get_name_map(self, symbols=None):
        return {}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.repo = _FakeRepo(pl.DataFrame(
        {
            "symbol": ["920001.BJ", "600000.SH", "000001.SZ"],
            "name": ["北交股", "沪主板", "深主板"],
            "close": [10.0, 20.0, 30.0],
            "change_pct": [0.0, 0.0, 0.0],
            "deviate_3d": [0.05, 0.13, -0.10],
            "deviate_10d": [None, 0.10, 0.10],
            "deviate_30d": [2.50, 0.10, 0.10],
        }
    ))
    app.state.quote_service = None
    return TestClient(app)


def test_overview_api_filters_before_limit() -> None:
    with _hist_cache_lock:
        _hist_cache.clear()
    client = _client()

    body = client.get(
        "/api/abnormal/overview",
        params={"min_closeness": 0.5, "limit": 1, "board": "主板"},
    ).json()
    assert [r["symbol"] for r in body["rows"]] == ["600000.SH"]
    assert body["total"] == 2

    body = client.get(
        "/api/abnormal/overview",
        params={"min_closeness": 0.5, "limit": 1, "window": "3d", "direction": "down"},
    ).json()
    assert [r["symbol"] for r in body["rows"]] == ["000001.SZ"]


def test_overview_api_rejects_unknown_board() -> None:
    with _hist_cache_lock:
        _hist_cache.clear()
    resp = _client().get(
        "/api/abnormal/overview",
        params={"min_closeness": 0.5, "board": "不存在"},
    )
    assert resp.status_code == 422


def test_suppression_api_rejects_invalid_forward_days() -> None:
    resp = _client().get(
        "/api/abnormal/suppression",
        params={"symbol": "600000.SH", "forward_days": 11},
    )
    assert resp.status_code == 422
