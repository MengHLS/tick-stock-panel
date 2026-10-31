from __future__ import annotations

from datetime import date, datetime

import httpx
import pytest

from app.market_time import CN_TZ
from app.plugins.fuyao.client import FuyaoClient, FuyaoError

DAY = date(2026, 9, 1)
DAY_MS = 1788192000000
READY_MS = int(datetime(2026, 10, 30, 20, tzinfo=CN_TZ).timestamp() * 1000)


def _payload(
    rows: list[dict],
    *,
    page: int = 1,
    pages: int = 1,
    total: int | None = None,
    size: int = 200,
    timestamp: int | None = READY_MS,
) -> dict:
    return {
        "code": 0,
        "data": {
            "timestamp": timestamp,
            "pagination": {
                "page": page,
                "pages": pages,
                "size": size,
                "total": len(rows) if total is None else total,
            },
            "item": rows,
        },
    }


def _client(handler) -> FuyaoClient:
    client = FuyaoClient("test-key")
    client._http.close()
    client._http = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://test",
        headers={"X-api-key": "test-key"},
    )
    return client


def test_merges_pools_without_inventing_missing_values():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["date_ms"] == str(DAY_MS)
        if request.url.path.endswith("limit-up-pool"):
            rows = [
                {
                    "thscode": "000001.SZ",
                    "name": "up",
                    "open_times": 2,
                    "limit_up_time": "09:34",
                    "continue_day_cnt": 1,
                    "seal_money": 123.5,
                    "max_seal_money": 456.0,
                },
                {
                    "thscode": "600000.SH",
                    "open_times": None,
                    "limit_up_time": "14:00",
                },
                {
                    "thscode": "600001.SH",
                    "open_times": 0,
                },
            ]
        else:
            rows = [
                {
                    "thscode": "000001.SZ",
                    "open_times": 3,
                    "first_seal_time": "09:32",
                    "last_seal_time": "10:15",
                    "turnover_ratio_pct": 8.1,
                    "turnover": 1_250_000_000,
                },
                {
                    "thscode": "300001.SZ",
                    "open_times": 1,
                },
            ]
        return httpx.Response(200, json=_payload(rows))

    client = _client(handler)
    try:
        from app.custom.limit_board_events.fuyao_adapter import fetch_limit_board_events

        rows = fetch_limit_board_events(client, DAY)
    finally:
        client.close()

    by_symbol = {row["symbol"]: row for row in rows}
    assert len(rows) == 4

    both = by_symbol["000001.SZ"]
    assert both["trade_date"] == DAY.isoformat()
    assert both["in_limit_up_pool"] == both["in_limit_break_pool"] == 1
    assert both["limit_up_pool_open_times"] == 2
    assert both["break_pool_open_times"] == 3
    assert both["limit_up_time"] == "09:34"
    assert both["limit_up_minute"] == 574
    assert both["first_seal_minute"] == 572
    assert both["last_seal_minute"] == 615
    assert both["turnover_ratio_pct"] == 8.1
    assert both["seal_money"] == 123.5
    assert both["turnover"] == 1_250_000_000.0
    assert both["observed_open"] == 1
    assert both["up_source_ready_at"].startswith("2026-10-30T20:00:00")

    assert by_symbol["600000.SH"]["in_limit_break_pool"] is None
    assert by_symbol["600000.SH"]["observed_open"] is None
    assert by_symbol["600001.SH"]["observed_open"] == 0
    assert by_symbol["300001.SZ"]["in_limit_up_pool"] is None


def test_reads_all_pages_and_supports_an_empty_other_pool():
    seen_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        if request.url.path.endswith("limit-break-pool"):
            return httpx.Response(200, json=_payload([], pages=0, size=2))
        seen_pages.append(page)
        rows = (
            [{"thscode": "000001.SZ"}, {"thscode": "600000.SH"}]
            if page == 1
            else [{"thscode": "300001.SZ"}]
        )
        return httpx.Response(
            200,
            json=_payload(rows, page=page, pages=2, total=3, size=2),
        )

    client = _client(handler)
    try:
        from app.custom.limit_board_events.fuyao_adapter import fetch_limit_board_events

        rows = fetch_limit_board_events(client, DAY, page_size=2)
    finally:
        client.close()

    assert len(rows) == 3
    assert seen_pages == [1, 2]


@pytest.mark.parametrize(
    "bad",
    [
        {"thscode": "invalid"},
        {"thscode": "000001.SZ", "open_times": -1},
        {"thscode": "000001.SZ", "open_times": 1.5},
        {"thscode": "000001.SZ", "open_times": True},
        {"thscode": "000001.SZ", "limit_up_time": "25:10"},
        {"thscode": "000001.SZ", "limit_up_time": "12:10"},
        {"thscode": "000001.SZ", "seal_money": "NaN"},
        {"thscode": "000001.SZ", "date": "2026-10-30"},
        {"thscode": "000001.SZ", "date_ms": READY_MS},
    ],
)
def test_rejects_malformed_pool_records(bad):
    client = _client(lambda request: httpx.Response(200, json=_payload([bad])))
    try:
        from app.custom.limit_board_events.fuyao_adapter import fetch_limit_board_events

        with pytest.raises((ValueError, FuyaoError)):
            fetch_limit_board_events(client, DAY)
    finally:
        client.close()


@pytest.mark.parametrize(
    "body",
    [
        {"code": 2003, "message": "permission denied", "data": None},
        {"code": 4001, "message": "rate limit", "data": None},
        {"code": 0, "data": {"item": []}},
        _payload([{"thscode": "000001.SZ"}], total=2),
        _payload([{"thscode": "000001.SZ"}], page=2),
        _payload([{"thscode": "000001.SZ"}, {"thscode": "000001.SZ"}]),
        _payload([{"thscode": "000001.SZ"}], pages=21, total=4200),
    ],
)
def test_rejects_failed_or_incomplete_pool_responses(body):
    client = _client(lambda request: httpx.Response(200, json=body))
    try:
        from app.custom.limit_board_events.fuyao_adapter import fetch_limit_board_events

        with pytest.raises((ValueError, FuyaoError)):
            fetch_limit_board_events(client, DAY)
    finally:
        client.close()


def test_http_rate_limit_is_not_treated_as_an_empty_pool():
    client = _client(lambda request: httpx.Response(429))
    try:
        from app.custom.limit_board_events.fuyao_adapter import fetch_limit_board_events

        with pytest.raises(FuyaoError, match="429"):
            fetch_limit_board_events(client, DAY)
    finally:
        client.close()


@pytest.mark.parametrize(
    "stamp",
    [
        None,
        0,
        int(datetime(2026, 9, 1, 10, tzinfo=CN_TZ).timestamp() * 1000),
        int(datetime(2026, 8, 31, 20, tzinfo=CN_TZ).timestamp() * 1000),
    ],
)
def test_rejects_unready_or_stale_pool_pages(stamp):
    def handler(request: httpx.Request) -> httpx.Response:
        body = _payload([{"thscode": "000001.SZ"}])
        if request.url.path.endswith("limit-break-pool"):
            body["data"]["timestamp"] = stamp
        return httpx.Response(200, json=body)

    client = _client(handler)
    try:
        from app.custom.limit_board_events.fuyao_adapter import fetch_limit_board_events

        with pytest.raises(ValueError, match="ready"):
            fetch_limit_board_events(client, DAY)
    finally:
        client.close()
