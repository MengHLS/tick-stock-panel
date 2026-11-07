"""逐标的行情新鲜度: 陈旧/复权降级不得产生可执行买入信号。"""
from __future__ import annotations

import polars as pl

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
