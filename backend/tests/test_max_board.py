"""最高板接力派生口径。"""
from __future__ import annotations

from datetime import date

import polars as pl

from app.services.max_board import build_max_board_relay


def _dates() -> list[date]:
    return [date(2026, 1, i) for i in range(1, 7)]


def test_break_uses_next_trading_day_successor() -> None:
    d = _dates()
    df = pl.DataFrame([
        {"symbol": "A", "date": d[0], "boards": 5, "change_pct": 0.10, "close": 10.0},
        {"symbol": "B", "date": d[0], "boards": 3, "change_pct": 0.10, "close": 8.0},
        {"symbol": "A", "date": d[1], "boards": 0, "change_pct": -0.03, "close": 9.7},
        {"symbol": "B", "date": d[1], "boards": 4, "change_pct": 0.10, "close": 8.8},
        {"symbol": "B", "date": d[2], "boards": 5, "change_pct": 0.10, "close": 9.7},
    ])
    out = build_max_board_relay(
        df, d[:3], {"A": "甲", "B": "乙", "C": "丙"}, exclude_st=False,
    )

    assert [p["height"] for p in out["series"]] == [5, 4, 5]
    assert len(out["events"]) == 1
    event = out["events"][0]
    assert event["break_date"] == "2026-01-02"
    assert event["previous_height"] == 5
    assert event["previous_leaders"][0]["name"] == "甲"
    assert event["break_day"]["former_leaders"][0]["change_pct"] == -0.03
    assert event["successor"]["date"] == "2026-01-03"
    assert event["successor"]["leaders"][0]["name"] == "乙"
    assert event["status"] == "taken_over"
    assert event["height_gap"] == 0
    assert out["current"]["days_since_break"] == 1


def test_vacant_and_multiple_leaders_are_preserved() -> None:
    d = _dates()
    df = pl.DataFrame([
        {"symbol": "A", "date": d[0], "boards": 6, "change_pct": 0.10, "close": 10.0},
        {"symbol": "B", "date": d[0], "boards": 6, "change_pct": 0.10, "close": 11.0},
        {"symbol": "A", "date": d[1], "boards": 0, "change_pct": -0.02, "close": 9.8},
        {"symbol": "B", "date": d[1], "boards": 0, "change_pct": -0.04, "close": 10.6},
        {"symbol": "C", "date": d[1], "boards": 2, "change_pct": 0.10, "close": 5.0},
        {"symbol": "D", "date": d[2], "boards": 1, "change_pct": 0.10, "close": 3.0},
    ])
    out = build_max_board_relay(
        df, d[:3], {"A": "甲", "B": "乙", "C": "丙", "D": "丁"}, exclude_st=False,
    )

    event = out["events"][0]
    assert {s["name"] for s in event["previous_leaders"]} == {"甲", "乙"}
    assert event["break_day"]["height"] == 2
    assert event["successor"]["height"] == 1
    assert event["successor"]["leaders"][0]["name"] == "丁"
    assert event["status"] == "vacant"
    assert event["height_gap"] == 5


def test_context_day_allows_break_detection_at_window_start() -> None:
    d = _dates()
    df = pl.DataFrame([
        {"symbol": "A", "date": d[0], "boards": 4, "change_pct": 0.10, "close": 10.0},
        {"symbol": "B", "date": d[1], "boards": 3, "change_pct": 0.10, "close": 8.0},
        {"symbol": "C", "date": d[2], "boards": 4, "change_pct": 0.10, "close": 9.0},
    ])
    out = build_max_board_relay(
        df,
        d[1:3],
        {"A": "甲", "B": "乙", "C": "丙"},
        context_dates=d[:3],
        exclude_st=False,
    )
    assert [p["date"] for p in out["series"]] == ["2026-01-02", "2026-01-03"]
    assert out["events"][0]["break_date"] == "2026-01-02"
    assert out["events"][0]["successor"]["leaders"][0]["name"] == "丙"
