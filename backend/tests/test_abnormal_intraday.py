"""异动监控聚合测试 (不依赖真实网络/enriched)。

覆盖: 信号命中过滤、counts 计数、优先级排序 (涨停 > 炸板 > …)、
多信号行、limit 截断、空快照、缺信号列的降级，以及名称从维表解析。
"""

from __future__ import annotations

from datetime import date

import polars as pl

from app.market_time import cn_today
from app.services import abnormal_moves
from app.services.abnormal_moves import build_intraday, build_overview


class _FakeRepo:
    def __init__(self, df: pl.DataFrame, names: dict[str, str] | None = None,
                 cache_date: date = date(2026, 8, 28)):
        self._df = df
        self._names = names or {}
        self._cache_date = cache_date

    def get_enriched_latest(self):
        return self._df, self._cache_date

    def get_name_map(self, symbols: list[str] | None = None) -> dict[str, str]:
        if symbols is None:
            return dict(self._names)
        return {s: self._names[s] for s in symbols if s in self._names}


def _df(rows: list[dict]) -> pl.DataFrame:
    cols = ["symbol", "name", "close", "change_pct", "amplitude", "vol_ratio_5d",
            "turnover_rate", "consecutive_limit_ups",
            "deviate_3d", "deviate_10d", "deviate_30d",
            "signal_limit_up", "signal_broken_limit_up", "signal_limit_down_recovery",
            "signal_limit_down", "signal_n_day_high", "signal_n_day_low",
            "signal_volume_surge"]
    base = {c: [] for c in cols}
    for r in rows:
        for c in cols:
            base[c].append(r.get(c))
    return pl.DataFrame(base)


def test_counts_filter_and_priority():
    repo = _FakeRepo(_df([
        {"symbol": "A1", "name": "甲", "close": 10.0, "change_pct": 0.1,
         "signal_limit_up": True, "signal_n_day_high": True},
        {"symbol": "B1", "name": "乙", "close": 5.0, "change_pct": -0.05,
         "signal_limit_down": True},
        {"symbol": "C1", "name": "丙", "close": 8.0, "change_pct": 0.02,
         "signal_volume_surge": True},
        {"symbol": "D1", "name": "丁", "close": 7.0, "change_pct": None},  # 无信号 → 不出现
    ]))
    out = build_intraday(repo)
    assert out["cache_date"] == "2026-08-28"
    assert out["counts"] == {"limit_up": 1, "broken": 0, "recovery": 0,
                             "limit_down": 1, "new_high": 1, "new_low": 0,
                             "volume_surge": 1}
    syms = [r["symbol"] for r in out["rows"]]
    assert syms == ["A1", "B1", "C1"]  # 优先级: 涨停 > 跌停 > 放量; 无信号被过滤
    assert out["rows"][0]["signals"] == ["limit_up", "new_high"]  # 多信号按优先级序


def test_limit_truncates():
    repo = _FakeRepo(_df([
        {"symbol": f"S{i}", "signal_volume_surge": True, "change_pct": 0.01} for i in range(10)
    ]))
    out = build_intraday(repo, limit=3)
    assert len(out["rows"]) == 3
    assert out["counts"]["volume_surge"] == 10  # counts 不受 limit 影响


def test_empty_snapshot():
    repo = _FakeRepo(pl.DataFrame({"symbol": [], "name": []}))
    out = build_intraday(repo)
    assert out["rows"] == [] and out["counts"] == {}


def test_missing_signal_columns_degrades():
    repo = _FakeRepo(pl.DataFrame({"symbol": ["A1"], "name": ["甲"]}))
    out = build_intraday(repo)
    assert out["rows"] == [] and out["counts"] == {}


def test_intraday_names_resolved_from_name_map_when_snapshot_omits_them():
    repo = _FakeRepo(
        _df([{"symbol": "A1", "name": None, "close": 10.0,
              "signal_limit_up": True}]),
        names={"A1": "甲股份"},
    )
    out = build_intraday(repo)
    assert out["rows"][0]["name"] == "甲股份"


def test_overview_names_resolved_from_name_map_when_snapshot_omits_them():
    abnormal_moves._hist_cache.clear()
    repo = _FakeRepo(
        _df([{"symbol": "600000.SH", "name": None, "close": 10.0,
              "change_pct": 0.0, "deviate_3d": 0.25,
              "deviate_10d": 0.0, "deviate_30d": 0.0}]),
        names={"600000.SH": "浦发银行"},
        cache_date=cn_today(),
    )
    try:
        out = build_overview(repo, min_closeness=0.0)
        assert out["rows"][0]["name"] == "浦发银行"
    finally:
        abnormal_moves._hist_cache.clear()
