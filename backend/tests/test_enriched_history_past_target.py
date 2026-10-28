"""get_enriched_history 对历史日期也必须按「目标日及之前」的交易日计数取窗口。

策略页可以选历史日期 (DatePicker), run_all / 单策略运行都会以 as_of 调
_load_enriched_history(as_of, required_history_bars)。缓存命中路径
(repo.get_enriched_history) 从整份缓存的交易日序列取最后 N+1 个交易日作起点,
缓存里晚于 as_of 的交易日也被算进去: as_of 越早窗口越短, 早于 N 个交易日时
直接是空窗口。慢路径只读 date <= as_of, 本来就是按目标日计数的。
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from app.services import screener as screener_module
from app.services.screener import ScreenerService
from app.tickflow.repository import DataStore, KlineRepository

LOOKBACK = 20


def _trading_days(n: int = 220) -> list[date]:
    days: list[date] = []
    d = date(2025, 11, 3)
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def _cache(days: list[date]) -> pl.DataFrame:
    rows = []
    for symbol, phase in (("600001.SH", 0.0), ("000002.SZ", 1.0)):
        for i, day in enumerate(days):
            rows.append((symbol, day, round(10 + math.sin(i * 0.2 + phase), 2)))
    return pl.DataFrame(rows, schema=["symbol", "date", "close"], orient="row").sort(["symbol", "date"])


def _repo(tmp_path: Path, cache: pl.DataFrame) -> KlineRepository:
    repo = KlineRepository(DataStore(tmp_path))
    repo._enriched_history_cache = cache
    return repo


@pytest.mark.parametrize("back", [0, 1, 5, 15], ids=["latest", "back1", "back5", "back15"])
def test_history_window_counts_trading_days_up_to_target(tmp_path, back):
    days = _trading_days()
    target = days[-1 - back]
    out = _repo(tmp_path, _cache(days)).get_enriched_history(target, LOOKBACK)

    assert out is not None
    want = [d for d in days if d <= target][-(LOOKBACK + 1):]
    assert out["date"].unique().sort().to_list() == want


def test_screener_history_does_not_depend_on_later_cached_days(tmp_path):
    """同一个 as_of, 缓存是否已包含更晚的交易日不应改变策略拿到的历史窗口。"""
    days = _trading_days()
    as_of = days[-6]
    full = _cache(days)
    upto = full.filter(pl.col("date") <= as_of)

    with_later = ScreenerService(_repo(tmp_path / "a", full))._load_enriched_history(as_of, LOOKBACK)
    without_later = ScreenerService(_repo(tmp_path / "b", upto))._load_enriched_history(as_of, LOOKBACK)

    assert without_later["date"].n_unique() == LOOKBACK + 1
    assert with_later["date"].n_unique() == without_later["date"].n_unique()
    assert with_later.sort(["symbol", "date"]).equals(without_later.sort(["symbol", "date"]))


@pytest.mark.parametrize("asset_type", ["stock", "etf"])
@pytest.mark.parametrize("lookback", [20, 126])
def test_history_fallback_preserves_requested_trading_window(
    tmp_path, monkeypatch, asset_type, lookback,
):
    monkeypatch.setattr(screener_module, "_history_cache", {})
    repo = _repo(tmp_path, pl.DataFrame())
    svc = ScreenerService(repo, asset_type=asset_type)
    target = date(2026, 10, 26)
    # Synthetic closures leave fewer than 120 sessions in the last 180 calendar days.
    days = [
        target - timedelta(days=offset)
        for offset in range(400, -6, -1)
        if (target - timedelta(days=offset)).weekday() < 5
        and not (
            date(2026, 5, 1) <= target - timedelta(days=offset) <= date(2026, 5, 7)
            or date(2026, 10, 1) <= target - timedelta(days=offset) <= date(2026, 10, 9)
        )
    ]
    rows = [
        {
            "symbol": "600001.SH" if asset_type == "stock" else "510300.SH",
            "date": day,
            "open": 10.0 + i * 0.01,
            "high": 10.2 + i * 0.01,
            "low": 9.8 + i * 0.01,
            "close": 10.1 + i * 0.01,
            "volume": 10000.0 + i,
            "amount": 100000.0 + i,
        }
        for i, day in enumerate(days)
    ]
    root = tmp_path / svc._enriched_dirname
    root.mkdir(exist_ok=True)
    pl.DataFrame(rows).write_parquet(root / "history.parquet")

    out = svc._load_enriched_history(target, lookback)

    want = [day for day in days if day <= target][-(lookback + 1):]
    assert out["date"].unique().sort().to_list() == want
    if lookback >= 120:
        assert out["close"].rolling_max(window_size=120)[-1] is not None
    assert svc._load_enriched_history(target, lookback).equals(out)


def test_history_fallback_returns_empty_without_local_data(tmp_path, monkeypatch):
    monkeypatch.setattr(screener_module, "_history_cache", {})
    svc = ScreenerService(_repo(tmp_path, pl.DataFrame()))

    assert svc._load_enriched_history(date(2026, 10, 26), 126).is_empty()
