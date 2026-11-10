"""最高板接力 API — 高度走势、断板事件与次日接替者。"""
from __future__ import annotations

import threading
import time
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request

from app.services import max_board as max_board_service
from app.services import preferences

router = APIRouter(prefix="/api/max-board", tags=["max-board"])

_CACHE_TTL = 30.0
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def invalidate_max_board_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _names_by_symbol(repo) -> dict[str, str]:
    instruments = repo.get_instruments()
    if instruments.is_empty() or "symbol" not in instruments.columns:
        return {}
    columns = [c for c in ("symbol", "name") if c in instruments.columns]
    if "name" not in columns:
        return {}
    return {
        str(symbol): str(name)
        for symbol, name in instruments.select(columns).iter_rows()
        if symbol is not None and name is not None
    }


@router.get("/relay")
def max_board_relay(
    request: Request,
    days: Annotated[int, Query(ge=10, le=250)] = 60,
    as_of: Annotated[date | None, Query()] = None,
):
    """市场最高板高度序列与断板接力事件。"""
    repo = request.app.state.repo
    latest = as_of or repo.latest_enriched_date("stock")
    if latest is None:
        return {
            "as_of": None,
            "range": {"start": None, "end": None, "days": days},
            "series": [],
            "events": [],
            "current": None,
            "total": 0,
            "exclude_st": preferences.get_sentiment_exclude_st(),
        }

    cache_key = f"{latest.isoformat()}|{days}"
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached is not None and now - cached[0] < _CACHE_TTL:
            return cached[1]

    scan_start = latest - timedelta(days=max(days * 2 + 20, 60))
    all_dates = repo.list_enriched_dates(scan_start, latest, "stock")
    if as_of is not None:
        all_dates = [d for d in all_dates if d <= as_of]
    if not all_dates:
        return {
            "as_of": None,
            "range": {"start": None, "end": None, "days": days},
            "series": [],
            "events": [],
            "current": None,
            "total": 0,
            "exclude_st": preferences.get_sentiment_exclude_st(),
        }

    last_index = len(all_dates) - 1
    series_start = max(0, last_index - days + 1)
    context_start = max(0, series_start - 1)
    context_end = min(last_index + 1, len(all_dates) - 1)
    series_dates = all_dates[series_start:last_index + 1]
    context_dates = all_dates[context_start:context_end + 1]

    frame = max_board_service.load_board_frame(repo, context_dates[0], context_dates[-1])
    exclude_st = preferences.get_sentiment_exclude_st()
    payload = max_board_service.build_max_board_relay(
        frame,
        series_dates,
        _names_by_symbol(repo),
        context_dates=context_dates,
        exclude_st=exclude_st,
        data_dir=repo.store.data_dir,
    )
    payload.update({
        "as_of": series_dates[-1].isoformat(),
        "range": {
            "start": series_dates[0].isoformat(),
            "end": series_dates[-1].isoformat(),
            "days": len(series_dates),
        },
        "total": len(payload.get("events", [])),
    })

    with _CACHE_LOCK:
        _CACHE[cache_key] = (now, payload)
    return payload
