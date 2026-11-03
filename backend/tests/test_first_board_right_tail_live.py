from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.custom.first_board_right_tail as extension
from app.custom.first_board_right_tail.screening import screen_first_boards
from app.custom.first_board_right_tail.service import FirstBoardRightTailService
from app.custom.first_board_right_tail.storage import FirstBoardRightTailStore
from app.custom.first_board_right_tail.triggers import (
    TriggerSignal,
    aggregate_five_minutes,
    evaluate_intraday_rules,
)
from app.extensions import BACKEND_EXTENSION_API_VERSION
from app.extensions.registry import BackendExtensionRegistrar


def _daily_rows(
    symbol: str,
    *,
    sessions: int = 24,
    event_close: float = 11.0,
    event_high: float = 11.0,
) -> list[dict]:
    start = date(2026, 9, 1)
    rows: list[dict] = []
    for index in range(sessions):
        day = start + timedelta(days=index)
        close = 10.0
        if index == sessions - 2:
            close = 10.0
        if index == sessions - 1:
            close = event_close
        rows.append(
            {
                "symbol": symbol,
                "date": day,
                "open": close,
                "high": event_high if index == sessions - 1 else close,
                "low": close,
                "close": close,
                "raw_close": close,
                "raw_high": event_high if index == sessions - 1 else close,
                "raw_low": close,
                "volume": 1000.0,
                "amount": 1_000_000.0,
            }
        )
    return rows


def _instruments(*symbols: str) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": list(symbols),
            "name": ["测试股" for _ in symbols],
            "listing_date": ["2020-01-01" for _ in symbols],
        }
    )


def _st(*symbols: str, flag: bool = False) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": list(symbols),
            "flag_date": [date(2020, 1, 1) for _ in symbols],
            "st_flag": [flag for _ in symbols],
        }
    )


def _minute_frame(symbol: str, closes: list[float], volumes: list[float] | None = None) -> pl.DataFrame:
    start = datetime.combine(date(2026, 11, 2), time(9, 30))
    volumes = volumes or [100.0 for _ in closes]
    rows = []
    for index, close in enumerate(closes, start=1):
        rows.append(
            {
                "symbol": symbol,
                "datetime": start + timedelta(minutes=index),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": volumes[index - 1],
                "amount": close * volumes[index - 1] * 100,
            }
        )
    return pl.DataFrame(rows)


def test_screening_recomputes_limit_up_and_ignores_stale_consecutive_column() -> None:
    daily = pl.DataFrame(
        _daily_rows("000001.SZ")
        + _daily_rows("000002.SZ", event_close=10.5)
        + _daily_rows("000003.SZ")
    ).with_columns(
        pl.when(pl.col("symbol") == "000002.SZ")
        .then(pl.lit(1, dtype=pl.UInt32))
        .otherwise(pl.lit(0, dtype=pl.UInt32))
        .alias("consecutive_limit_ups")
    )
    result = screen_first_boards(
        daily,
        _instruments("000001.SZ", "000002.SZ", "000003.SZ"),
        pl.concat([_st("000001.SZ", "000002.SZ"), _st("000003.SZ", flag=True)]),
        as_of=date(2026, 9, 24),
    )

    assert [row["symbol"] for row in result["candidates"]] == ["000001.SZ"]
    assert result["candidates"][0]["limit_up_price"] == 11.0
    assert result["excluded"]["stale_consecutive_not_recomputed"] == 1
    assert result["excluded"]["historical_st"] == 1


def test_screening_fails_closed_when_st_status_is_unknown() -> None:
    result = screen_first_boards(
        pl.DataFrame(_daily_rows("000001.SZ")),
        _instruments("000001.SZ"),
        _st("600000.SH"),
        as_of=date(2026, 9, 24),
    )

    assert result["candidates"] == []
    assert result["excluded"]["unknown_historical_st"] == 1


def test_screening_uses_tolerance_for_exact_cent_limit_prices() -> None:
    stale_chain = _daily_rows("000004.SZ")
    for row, close in zip(stale_chain[-3:], [12.38, 13.62, 14.98], strict=True):
        row.update(
            {
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "raw_close": close,
                "raw_high": close,
                "raw_low": close,
            }
        )
    result = screen_first_boards(
        pl.DataFrame(stale_chain),
        _instruments("000004.SZ"),
        _st("000004.SZ"),
        as_of=date(2026, 9, 24),
    )

    assert result["candidates"] == []
    assert result["excluded"]["not_first_board"] == 1


def test_five_minute_aggregation_uses_bar_end_timestamps() -> None:
    frame = _minute_frame("000001.SZ", [10 + index / 100 for index in range(5)])
    five = aggregate_five_minutes(frame)

    assert five.height == 1
    assert five["datetime"][0] == datetime(2026, 11, 2, 9, 35)
    assert five["close"][0] == 10.04


def test_rule_a_requires_twenty_prior_bars_and_does_not_repeat_while_active() -> None:
    event = {
        "symbol": "000001.SZ",
        "event_date": date(2026, 10, 30),
        "t_high_adj": 10.50,
        "t_close_adj": 10.0,
    }
    closes = [10.0] * 20 + [10.6, 10.7]
    volumes = [100.0] * 20 + [300.0, 300.0]
    signals = evaluate_intraday_rules(event, _minute_frame("000001.SZ", closes, volumes))

    rule_a = [signal for signal in signals if signal.rule == "A"]
    assert len(rule_a) == 1
    assert rule_a[0].signal_time == datetime(2026, 11, 2, 9, 51)
    assert rule_a[0].order_time == datetime(2026, 11, 2, 9, 52)


def test_rule_b_requires_two_five_minute_closes_above_rising_vwap() -> None:
    event = {
        "symbol": "000001.SZ",
        "event_date": date(2026, 10, 30),
        "t_high_adj": 20.0,
        "t_close_adj": 10.0,
    }
    closes = [10.0] * 5 + [10.2] * 10
    signals = evaluate_intraday_rules(event, _minute_frame("000001.SZ", closes))

    rule_b = [signal for signal in signals if signal.rule == "B"]
    assert len(rule_b) == 1
    assert rule_b[0].signal_time == datetime(2026, 11, 2, 9, 45)
    assert rule_b[0].order_time == datetime(2026, 11, 2, 9, 46)


def test_rule_c_requires_retake_of_five_minute_ma5() -> None:
    event = {
        "symbol": "000001.SZ",
        "event_date": date(2026, 10, 30),
        "t_high_adj": 20.0,
        "t_close_adj": 10.0,
    }
    closes = (
        [10.0] * 5
        + [9.9] * 5
        + [9.8] * 5
        + [9.7] * 5
        + [9.6] * 5
        + [10.3] * 5
    )
    signals = evaluate_intraday_rules(event, _minute_frame("000001.SZ", closes))

    rule_c = [signal for signal in signals if signal.rule == "C"]
    assert rule_c
    assert rule_c[0].signal_time == datetime(2026, 11, 2, 10, 0)
    assert rule_c[0].order_time == datetime(2026, 11, 2, 10, 1)


def test_rule_d_requires_auction_confirmation_and_t_plus_one() -> None:
    event = {
        "symbol": "000001.SZ",
        "event_date": date(2026, 10, 30),
        "t_high_adj": 20.0,
        "t_close_adj": 10.0,
    }
    frame = _minute_frame("000001.SZ", [10.1] * 5)
    signals = evaluate_intraday_rules(
        event,
        frame,
        auction={"opening_gap": 0.02, "volume_ratio": 1.5, "auction_price": 10.0},
        decision_day=1,
    )

    rule_d = [signal for signal in signals if signal.rule == "D"]
    assert len(rule_d) == 1
    assert rule_d[0].signal_time == datetime(2026, 11, 2, 9, 35)
    assert rule_d[0].order_time == datetime(2026, 11, 2, 9, 36)

    later = evaluate_intraday_rules(
        event,
        frame,
        auction={"opening_gap": 0.02, "volume_ratio": 1.5, "auction_price": 10.0},
        decision_day=2,
    )
    assert not [signal for signal in later if signal.rule == "D"]


def test_load_auction_uses_legacy_history_to_bootstrap_volume_ratio(tmp_path: Path) -> None:
    service = FirstBoardRightTailService(MagicMock(), tmp_path)
    target = date(2026, 11, 2)
    live = tmp_path / "ext_data" / "auction_result_live" / "timeseries"
    legacy = tmp_path / "ext_data" / "auction_result" / "timeseries"
    live_part = live / f"date={target.isoformat()}" / "part.parquet"
    live_part.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "auction_open": [10.2],
        "opening_gap": [0.02],
        "volume_shares": [1_500_000],
        "has_result": [1],
    }).write_parquet(live_part)

    for offset in range(1, 6):
        day = target - timedelta(days=offset)
        part = legacy / f"date={day.isoformat()}" / "part.parquet"
        part.parent.mkdir(parents=True)
        pl.DataFrame({
            "symbol": ["000001.SZ"],
            "volume_shares": [1_000_000],
        }).write_parquet(part)

    result = service._load_auction(target)

    assert result["000001.SZ"]["auction_price"] == 10.2
    assert result["000001.SZ"]["volume_ratio"] == pytest.approx(1.5)


def test_no_new_trigger_after_1456() -> None:
    event = {
        "symbol": "000001.SZ",
        "event_date": date(2026, 10, 30),
        "t_high_adj": 10.5,
        "t_close_adj": 10.0,
    }
    # Twenty prior bars end at 14:56; the breakout bar itself ends at 14:57.
    start = datetime(2026, 11, 2, 14, 37)
    rows = []
    for index, close in enumerate([10.0] * 20 + [10.6]):
        rows.append(
            {
                "symbol": "000001.SZ",
                "datetime": start + timedelta(minutes=index),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 300.0,
                "amount": close * 300.0 * 100,
            }
        )
    signals = evaluate_intraday_rules(event, pl.DataFrame(rows))

    assert not [signal for signal in signals if signal.rule == "A"]


def test_trigger_signal_always_orders_after_signal() -> None:
    signal = TriggerSignal(
        rule="A",
        signal_time=datetime(2026, 11, 2, 9, 51),
        order_time=datetime(2026, 11, 2, 9, 52),
        price_adj=10.6,
        reason="测试",
    )
    assert signal.order_time > signal.signal_time


class FakeRepository:
    def __init__(self, daily: pl.DataFrame, minute: pl.DataFrame | None = None) -> None:
        self.daily = daily
        self.minute = minute if minute is not None else pl.DataFrame()
        self.instruments = _instruments("000001.SZ")
        self.st_history = _st("000001.SZ")

    def get_instruments_asset(self, asset_type: str) -> pl.DataFrame:
        assert asset_type == "stock"
        return self.instruments

    def get_st_history(self) -> pl.DataFrame:
        return self.st_history

    def enriched_latest_date(self, asset_type: str = "stock") -> date:
        del asset_type
        return self.daily["date"].max()

    def get_daily_batch(
        self,
        symbols: list[str],
        start: date,
        end: date,
        columns: list[str] | None = None,
    ) -> pl.DataFrame:
        del columns
        return self.daily.filter(
            pl.col("symbol").is_in(symbols)
            & (pl.col("date") >= start)
            & (pl.col("date") <= end)
        )

    def list_minute_dates(self, start: date, end: date, asset_type: str = "stock") -> list[date]:
        del start, end, asset_type
        return sorted(set(self.minute["datetime"].dt.date().to_list())) if not self.minute.is_empty() else []

    def get_minute_batch(
        self,
        symbols: list[str],
        trade_date: date,
        asset_type: str = "stock",
    ) -> pl.DataFrame:
        del asset_type
        if self.minute.is_empty():
            return pl.DataFrame()
        return self.minute.filter(
            pl.col("symbol").is_in(symbols)
            & (pl.col("datetime").dt.date() == trade_date)
        )

    def get_enriched_latest(self) -> tuple[pl.DataFrame, date]:
        return pl.DataFrame(
            {
                "symbol": ["000001.SZ"],
                "name": ["测试股"],
                "close": [10.6],
                "raw_close": [10.6],
                "change_pct": [0.06],
            }
        ), date(2026, 11, 2)


def test_store_rejects_corrupt_state_without_overwriting(tmp_path: Path) -> None:
    store = FirstBoardRightTailStore(tmp_path)
    path = tmp_path / "user_data" / "first_board_right_tail" / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text("{bad json", encoding="utf-8")

    try:
        store.load()
    except ValueError:
        pass
    else:
        raise AssertionError("corrupt state must fail closed")

    assert path.read_text(encoding="utf-8") == "{bad json"


def test_service_imports_and_fills_only_once_on_next_minute(tmp_path: Path) -> None:
    daily = pl.DataFrame(_daily_rows("000001.SZ", event_high=10.5))
    start = datetime(2026, 11, 2, 9, 30)
    rows = []
    closes = [10.0] * 20 + [10.6, 10.55]
    volumes = [2_000.0] * 20 + [6_000.0, 2_000.0]
    for index, (close, volume) in enumerate(zip(closes, volumes, strict=True), start=1):
        rows.append(
            {
                "symbol": "000001.SZ",
                "datetime": start + timedelta(minutes=index),
                "open": 10.55 if index == 22 else close,
                "high": close,
                "low": close,
                "close": close,
                "volume": volume,
                "amount": close * volume * 100,
            }
        )
    minute = pl.DataFrame(rows)
    repo = FakeRepository(daily, minute)
    service = FirstBoardRightTailService(repo, tmp_path)

    imported = service.import_latest(as_of=date(2026, 9, 24))
    assert imported["imported"] == 1
    events = service.on_quote_update(
        datetime.fromisoformat("2026-11-02T09:52:30+08:00"),
        [
            {
                "symbol": "000001.SZ",
                "name": "测试股",
                "close": 10.55,
                "raw_close": 10.55,
                "change_pct": 0.055,
            }
        ],
    )

    assert [event["type"] for event in events] == ["buy_trigger", "buy_fill"]
    state = service.load_state()
    event = state["events"][0]
    assert event["status"] == "FILLED"
    assert event["entry_price_raw"] == 10.55
    assert event["trigger_rule"] == "A"
    assert event["fill_time"] == "2026-11-02T09:52:00"

    assert service.on_quote_update(
        datetime.fromisoformat("2026-11-02T09:53:30+08:00"),
        [
            {
                "symbol": "000001.SZ",
                "name": "测试股",
                "close": 10.55,
                "raw_close": 10.55,
                "change_pct": 0.055,
            }
        ],
    ) == []


def test_simple_monitor_rules_reuse_supported_intraday_signals() -> None:
    from app.custom.first_board_right_tail.service import build_simple_monitor_rules

    rules = build_simple_monitor_rules(
        [
            {"symbol": "000001.SZ", "name": "A"},
            {"symbol": "600000.SH", "name": "B"},
        ]
    )

    assert [rule["id"] for rule in rules] == [
        "frt_simple_cross_prev_close",
        "frt_simple_cross_vwap",
    ]
    assert rules[0]["conditions"][0]["field"] == "signal_intraday_zero_cross_up"
    assert rules[1]["conditions"][0]["field"] == "signal_intraday_avg_cross_up"
    assert rules[0]["scope"] == "symbols"
    assert rules[0]["symbols"] == ["000001.SZ", "600000.SH"]


def test_extension_route_and_observer_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeService:
        def overview(self) -> dict:
            return {"summary": {"total": 3}, "events": []}

    app = FastAPI()
    registrar = BackendExtensionRegistrar(
        extension.EXTENSION_ID,
        api_version=BACKEND_EXTENSION_API_VERSION,
    )
    extension.setup(registrar)
    for router in registrar.routers:
        app.include_router(router)
    monkeypatch.setattr(extension, "_service", FakeService())

    response = TestClient(app).get("/api/custom/first-board-right-tail/overview")

    assert response.status_code == 200
    assert response.json()["summary"]["total"] == 3
    assert [item[0] for item in registrar.quote_observers] == [
        "official.first-board-right-tail.live"
    ]
