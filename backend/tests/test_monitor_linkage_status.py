"""盘中监控的联动因子降级契约。"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from app.strategy import monitor_rules
from app.strategy.monitor import MonitorRuleEngine


def _industry_rule() -> dict:
    return monitor_rules.normalize({
        "id": "industry_monitor",
        "name": "行业联动监控",
        "type": "signal",
        "scope": "all",
        "conditions": [{
            "field": "industry_relative_momentum_20d",
            "op": ">",
            "value": 0.5,
        }],
    })


def test_monitor_rejects_industry_factor_as_intraday_condition() -> None:
    with pytest.raises(ValueError, match="daily_close_only"):
        monitor_rules.validate(_industry_rule())


def test_monitor_keeps_deviate_factor_intraday_compatibility() -> None:
    rule = monitor_rules.normalize({
        "id": "deviate_monitor",
        "name": "偏离监控",
        "type": "signal",
        "scope": "all",
        "conditions": [{
            "field": "deviate_10d",
            "op": ">",
            "value": 0.1,
        }],
    })

    monitor_rules.validate(rule)


def test_legacy_industry_rule_reports_serializable_degraded_reason() -> None:
    engine = MonitorRuleEngine()
    rule = _industry_rule()
    engine.set_rules([rule])
    frame = pl.DataFrame({
        "symbol": ["600000.SH"],
        "date": [date(2026, 3, 2)],
        "name": ["浦发银行"],
        "close": [10.0],
        "change_pct": [0.01],
    })

    events = engine.evaluate(frame)

    assert events == []
    assert engine.unavailable_reasons == {"industry_monitor": "daily_close_only"}
