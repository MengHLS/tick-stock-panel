"""ETF 监控轮与股票轮/指数轮同口径: 快照日期不是当日时不评估。

_evaluate_monitors 的节假日与陈旧数据兜底靠「快照日期 = 当日」新鲜度判据
(股票轮 stock_ready、指数轮 index_date == cn_today()), ETF 轮只看缓存是否为空。
但 ETF 缓存并不只由 ETF 实时落盘焐热: 自选页/ETF 策略/ETF K 线等以 refresh=True
调 get_enriched_latest_asset("etf") 会把磁盘上最新一日 (上一交易日) 读进缓存。
ETF 实时拉取默认关闭 (realtime_pull_etf=False), 工作日休市时实时快照也不落盘,
这两种情况下 ETF 规则每轮都拿上一交易日的数据当作今天评估并推送告警。
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
import time

import polars as pl

from app.services.quote_service import QuoteService
from app.strategy.monitor import MonitorRuleEngine

TODAY = date(2026, 9, 18)
YESTERDAY = date(2026, 9, 17)


class _Repo:
    def __init__(self, etf_date: date) -> None:
        self.etf_date = etf_date
        self.store = SimpleNamespace(data_dir=None)

    def get_name_map(self, symbols=None):
        return {"510300.SH": "沪深300ETF"}

    def get_enriched_latest_asset(self, asset_type, refresh=True):
        if asset_type != "etf":
            return pl.DataFrame(), None
        return (
            pl.DataFrame({"symbol": ["510300.SH"], "date": [self.etf_date],
                          "close": [4.2], "change_pct": [0.012],
                          "quote_ts": [int(time.time() * 1000)]}),
            self.etf_date,
        )


def _run(etf_date: date, quote_age_ms: int | None = None) -> list[dict]:
    engine = MonitorRuleEngine()
    engine.set_rules([{
        "id": "etf_px", "name": "ETF 价格提醒", "type": "price", "asset_type": "etf",
        "scope": "symbols", "symbols": ["510300.SH"], "logic": "and",
        "conditions": [{"field": "close", "op": ">=", "value": 4.0}],
        "cooldown_seconds": 0, "enabled": True,
    }])
    svc = QuoteService.__new__(QuoteService)
    svc._repo = (
        _RepoOld(etf_date, quote_age_ms) if quote_age_ms is not None else _Repo(etf_date)
    )
    svc._app_state = SimpleNamespace(monitor_engine=engine, repo=svc._repo)
    broadcast: list[dict] = []
    with (
        patch.object(QuoteService, "_is_continuous_trading", return_value=True),
        patch.object(QuoteService, "get_enriched_today", return_value=(pl.DataFrame(), None)),
        patch.object(QuoteService, "_inject_intraday_signals", side_effect=lambda df, e, at: df),
        patch.object(QuoteService, "_enrich_alerts_ext", lambda self, alerts: None),
        patch.object(QuoteService, "_broadcast_alerts", lambda self, alerts: broadcast.extend(alerts)),
        patch.object(QuoteService, "_maybe_send_system_notifications", lambda self, alerts: None),
        patch.object(QuoteService, "_maybe_send_webhook", lambda self, events, engine: None),
        patch("app.services.alert_store.append_many", lambda *a, **k: None),
        patch("app.services.quote_service.cn_today", return_value=TODAY),
    ):
        svc._evaluate_monitors(pl.DataFrame(), None)
    return broadcast


def test_stale_etf_snapshot_is_not_evaluated():
    """ETF 缓存是上一交易日 (无当日实时落盘): 不评估, 不推送。"""
    assert _run(YESTERDAY) == []


def test_today_etf_snapshot_still_triggers():
    """ETF 缓存为当日实时快照: 照常评估 (回归确认守卫不误伤)。"""
    alerts = _run(TODAY)
    assert [a["rule_id"] for a in alerts] == ["etf_px"]
    assert alerts[0]["symbol"] == "510300.SH"


def test_today_snapshot_with_old_quote_ts_is_not_executable():
    """快照日期是当日, 但该标的行情时间已过期: 不能按旧价触发买入告警。"""
    alerts = _run(TODAY, quote_age_ms=600_000)
    assert alerts == []


class _RepoOld:
    """日期为当日, 但 quote_ts 停在 10 分钟前。"""

    def __init__(self, day: date, age_ms: int) -> None:
        self.day = day
        self.age_ms = age_ms
        self.store = SimpleNamespace(data_dir=None)

    def get_name_map(self, symbols=None):
        return {"510300.SH": "沪深300ETF"}

    def get_enriched_latest_asset(self, asset_type, refresh=True):
        if asset_type != "etf":
            return pl.DataFrame(), None
        return (
            pl.DataFrame({"symbol": ["510300.SH"], "date": [self.day],
                          "close": [4.2], "change_pct": [0.012],
                          "quote_ts": [int(time.time() * 1000) - self.age_ms]}),
            self.day,
        )
