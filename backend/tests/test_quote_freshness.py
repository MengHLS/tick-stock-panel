"""逐标的行情新鲜度: 陈旧/复权降级不得产生可执行买入信号。"""
from __future__ import annotations

from datetime import date, datetime

import polars as pl
import pytest

from app.market_time import CN_TZ
from app.services.quote_freshness import (
    REASON_ADJUSTMENT,
    REASON_FUTURE_TS,
    REASON_INVALID_TS,
    REASON_MISSING_TS,
    REASON_STALE,
    FreshnessPolicy,
    annotate_quote_freshness,
    fresh_rows,
    stale_rejections,
)
from app.strategy.monitor import MonitorRuleEngine

NOW_MS = 1_760_000_000_000.0


def _frame(**cols) -> pl.DataFrame:
    base = {"symbol": ["A.SH"], "close": [10.0], "signal_hit": [True]}
    base.update(cols)
    return pl.DataFrame(base)


def _annotate(frame, **kw):
    return annotate_quote_freshness(frame, now_ms=NOW_MS, **kw)


def test_fresh_row_is_executable():
    frame = _frame(quote_ts=[int(NOW_MS) - 30_000])
    annotated, summary = _annotate(frame)
    assert annotated["quote_fresh"].to_list() == [True]
    assert annotated["quote_stale_reason"].to_list() == [None]
    assert summary["fresh"] == 1 and summary["stale"] == 0


def test_old_quote_is_rejected_per_symbol_not_by_market_date():
    frame = _frame(
        symbol=["A.SH", "B.SH"],
        close=[10.0, 20.0],
        signal_hit=[True, True],
        quote_ts=[int(NOW_MS) - 10_000, int(NOW_MS) - 600_000],
    )
    annotated, summary = _annotate(frame)
    assert annotated["quote_fresh"].to_list() == [True, False]
    assert annotated["quote_stale_reason"].to_list() == [None, REASON_STALE]
    assert summary["fresh"] == 1 and summary["stale"] == 1
    assert summary["reasons"] == {REASON_STALE: 1}
    assert stale_rejections(annotated) == {"B.SH": REASON_STALE}


def test_missing_quote_ts_column_rejects_everything():
    annotated, summary = _annotate(_frame())
    assert annotated["quote_fresh"].to_list() == [False]
    assert annotated["quote_stale_reason"].to_list() == [REASON_MISSING_TS]
    assert summary["stale"] == 1


def test_null_or_future_timestamp_is_rejected():
    frame = _frame(
        symbol=["A.SH", "B.SH"],
        close=[10.0, 20.0],
        signal_hit=[True, True],
        quote_ts=[None, int(NOW_MS) + 600_000],
    )
    annotated, _ = _annotate(frame)
    assert annotated["quote_stale_reason"].to_list() == [
        REASON_INVALID_TS, REASON_FUTURE_TS,
    ]


def test_adjustment_failure_rejects_all_rows_even_when_quotes_are_fresh():
    frame = _frame(
        symbol=["A.SH", "B.SH"],
        close=[10.0, 20.0],
        signal_hit=[True, True],
        quote_ts=[int(NOW_MS) - 5_000, int(NOW_MS) - 5_000],
    )
    annotated, summary = _annotate(frame, adjustment_error="adj_factor unreadable")
    assert annotated["quote_fresh"].to_list() == [False, False]
    assert annotated["quote_stale_reason"].to_list() == [REASON_ADJUSTMENT] * 2
    assert summary["reasons"] == {REASON_ADJUSTMENT: 2}
    assert "adj_factor" in summary["adjustment_error"]


def test_max_age_is_configurable():
    frame = _frame(quote_ts=[int(NOW_MS) - 200_000])
    annotated, _ = annotate_quote_freshness(
        frame, now_ms=NOW_MS, policy=FreshnessPolicy(max_age_seconds=300),
    )
    assert annotated["quote_fresh"].to_list() == [True]


def test_fresh_rows_and_rejections_ignore_unannotated_frames():
    plain = _frame()
    assert fresh_rows(plain).height == 1
    assert stale_rejections(plain) == {}


def test_monitor_engine_does_not_fire_on_stale_symbol():
    engine = MonitorRuleEngine()
    engine.set_rules([{
        "id": "r1", "name": "命中", "type": "signal", "asset_type": "stock",
        "scope": "all", "logic": "or",
        "conditions": [{"field": "signal_hit", "op": "truth"}],
        "cooldown_seconds": 0, "enabled": True,
    }])
    frame = _frame(
        symbol=["A.SH", "B.SH"],
        close=[10.0, 20.0],
        signal_hit=[True, True],
        quote_ts=[int(NOW_MS) - 10_000, int(NOW_MS) - 600_000],
    )
    annotated, _ = _annotate(frame)
    events = engine.evaluate(annotated, asset_type="stock")
    assert [event["symbol"] for event in events] == ["A.SH"]
    report = engine.latest_quote_rejections("stock")
    assert report["rejected"] == 1
    assert report["samples"][0]["symbol"] == "B.SH"
    assert report["samples"][0]["reason"] == REASON_STALE


def test_monitor_engine_reports_adjustment_rejection_for_every_symbol():
    engine = MonitorRuleEngine()
    engine.set_rules([{
        "id": "r1", "name": "命中", "type": "signal", "asset_type": "stock",
        "scope": "all", "logic": "or",
        "conditions": [{"field": "signal_hit", "op": "truth"}],
        "cooldown_seconds": 0, "enabled": True,
    }])
    annotated, _ = _annotate(
        _frame(quote_ts=[int(NOW_MS) - 1_000]),
        adjustment_error="adj_factor unreadable",
    )
    assert engine.evaluate(annotated, asset_type="stock") == []
    report = engine.latest_quote_rejections("stock")
    assert report["reasons"] == {REASON_ADJUSTMENT: 1}
def _row(day="2026-11-06", time="10:00:00"):
    stamp = int(datetime.fromisoformat(f"{day}T{time}").replace(tzinfo=CN_TZ).timestamp() * 1000)
    return {"symbol": "000985.SH", "date": day, "close": 100., "quote_ts": stamp}


@pytest.fixture
def context():
    from app.services.quote_freshness import QuoteFreshness

    return QuoteFreshness(now=datetime(2026, 11, 6, 10, 0, 10, tzinfo=CN_TZ), trading=True)


def test_each_symbol_uses_own_date_not_shared_asset_date(context):
    assert context.describe(_row())["state"] == "live"
    old = context.describe(_row("2026-11-05"))
    assert old["state"] == "stale"
    assert old["data_date"] == "2026-11-05"


def test_intraday_outage_is_delayed_but_value_is_preserved(context):
    row = _row(time="09:55:00")
    status = context.describe(row)
    assert status["state"] == "delayed"
    assert status["quote_ts"] == row["quote_ts"]
    assert row["close"] == 100.


def test_daily_preparation_and_unknown_timestamp_are_never_live(context):
    assert context.describe({**_row(), "prepared_daily": True})["state"] == "historical"
    assert context.describe({"date": "2026-11-06", "close": 100.})["state"] == "unknown"
    assert context.describe({"symbol": "000985.SH"})["state"] == "missing"


@pytest.mark.parametrize("now,trading", [
    (datetime(2026, 11, 7, 10, tzinfo=CN_TZ), False),
    (datetime(2026, 11, 6, 8, tzinfo=CN_TZ), True),
    (datetime(2026, 10, 1, 10, tzinfo=CN_TZ), False),
])
def test_weekend_preopen_and_holiday_do_not_claim_last_close_is_stale(now, trading):
    from app.services.quote_freshness import QuoteFreshness

    row = _row("2026-09-30") if now.month == 10 else _row("2026-11-05")
    assert QuoteFreshness(now=now, trading=trading).describe(row)["state"] == "historical"


def test_lunch_and_after_close_compare_to_session_boundary():
    from app.services.quote_freshness import QuoteFreshness

    lunch = QuoteFreshness(now=datetime(2026, 11, 6, 12, 20, tzinfo=CN_TZ), trading=True)
    assert lunch.describe(_row(time="11:30:00"))["state"] == "historical"
    assert lunch.describe(_row(time="11:00:00"))["state"] == "delayed"
    closed = QuoteFreshness(now=datetime(2026, 11, 6, 17, tzinfo=CN_TZ), trading=True)
    assert closed.describe(_row(time="15:00:00"))["state"] == "historical"
    assert closed.describe(_row("2026-11-05"))["state"] == "stale"


def test_future_or_invalid_timestamp_is_not_live(context):
    assert context.describe(_row(time="15:00:00"))["state"] == "unknown"
    for value in [float("nan"), float("inf"), -1, "invalid"]:
        assert context.describe({**_row(), "quote_ts": value})["state"] == "unknown"


def test_old_timestamp_is_not_hidden_by_current_partition_date(context):
    old = _row("2026-11-05")
    assert context.describe({**old, "date": date(2026, 11, 6)})["state"] == "stale"


@pytest.mark.parametrize("asset,symbol", [("stock", "600519.SH"), ("etf", "159558.SZ"), ("index", "000985.SH")])
def test_restarted_cache_preserves_each_asset_quote_timestamp(tmp_path, asset, symbol):
    import polars as pl

    from app.tickflow.repository import DataStore, KlineRepository

    repo = KlineRepository(DataStore(tmp_path))
    rows = pl.DataFrame([{**_row(), "symbol": symbol, "date": date(2026, 11, 6),
                          "open": 100., "high": 101., "low": 99., "volume": 100., "amount": 10000.}])
    repo.append_enriched_asset(asset, rows)
    # A new repository must recover provenance from existing compatible Parquets.
    restarted = KlineRepository(DataStore(tmp_path))
    frame, day = restarted.get_enriched_latest_asset(asset)
    assert day == date(2026, 11, 6)
    assert "quote_ts" in frame.columns
    assert frame["quote_ts"][0] == rows["quote_ts"][0]
