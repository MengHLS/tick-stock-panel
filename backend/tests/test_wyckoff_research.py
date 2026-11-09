"""威科夫日线研究扩展：时间边界、失效独立性与缺数据 fail-closed 验收。"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.custom.wyckoff_research.routes import build_router
from app.custom.wyckoff_research.rules import UNFROZEN_DEMO_SPEC, compute_events
from app.custom.wyckoff_research.service import ResearchInputError, load_events
from app.custom.wyckoff_research.spec import SpecError, load_spec, spec_warnings
from app.extensions import get_extension_runtime

START = date(2026, 1, 5)


def _bar(index: int, *, low: float, high: float, close: float, volume: float) -> dict:
    return {
        "symbol": "000001.SZ",
        "date": START + timedelta(days=index),
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _series() -> list[dict]:
    """100 根日线：0..59 箱体（支撑 100 / 阻力 110）→ 60 下探弹簧 → 63 确认 → 70 破位失效。"""
    bars = [_bar(i, low=100.0, high=110.0, close=105.0, volume=1000.0) for i in range(60)]
    bars.append(_bar(60, low=98.0, high=102.0, close=101.0, volume=2000.0))
    for i in (61, 62, 63):
        bars.append(_bar(i, low=100.0, high=110.0, close=102.0, volume=1000.0))
    bars.append(_bar(64, low=99.0, high=103.0, close=101.0, volume=800.0))
    for i in range(65, 70):
        bars.append(_bar(i, low=100.0, high=110.0, close=103.0, volume=1000.0))
    bars.append(_bar(70, low=97.0, high=99.0, close=98.0, volume=1500.0))
    for i in range(71, 100):
        bars.append(_bar(i, low=99.0, high=105.0, close=102.0, volume=1000.0))
    return list(bars)


def _compute(rows: list[dict], as_of: date) -> dict:
    return compute_events(rows, symbol="000001.SZ", as_of=as_of, spec=UNFROZEN_DEMO_SPEC, data_generation="gen-1")


def _spring(result: dict) -> dict | None:
    return next((event for event in result["events"] if event["event_type"] == "Spring"), None)


class _Panel:
    def __init__(self, frame: pl.DataFrame | None, *, latest: date | None = None, generations: tuple[str | None, ...] = ("gen-1",)) -> None:
        self.frame = frame
        self.latest = latest
        self.generations = list(generations)
        self.calls: list[tuple[date, date]] = []

    def latest_date(self, asset_type: str = "stock") -> date | None:
        return self.latest

    def data_generation(self, asset_type: str = "stock") -> str | None:
        return self.generations.pop(0) if len(self.generations) > 1 else self.generations[0]

    def range(self, start, end, symbols=None, columns=None):
        self.calls.append((start, end))
        return self.frame


def _runtime(panel: _Panel, tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(data_dir=tmp_path, enriched_panel=panel)


def _frame(bars: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(bars)


def test_spring_marker_is_confirmation_day_not_pattern_day() -> None:
    bars = _series()
    result = _compute(bars, bars[-1]["date"])
    spring = _spring(result)
    assert spring is not None
    assert spring["pattern_date"] == bars[60]["date"].isoformat()
    assert spring["confirmed_at"] == bars[63]["date"].isoformat()
    assert spring["available_at"] == bars[63]["date"].isoformat()
    assert spring["available_at_basis"] == "daily_close"
    assert spring["status"] == "confirmed"
    assert spring["data_generation"] == "gen-1"


def test_candidate_before_confirmation_has_no_confirmed_at() -> None:
    bars = _series()
    truncated = [bar for bar in bars if bar["date"] <= bars[62]["date"]]
    result = _compute(truncated, bars[62]["date"])
    assert _spring(result) is None
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["event_type"] == "Spring"
    assert candidate["status"] == "candidate"
    assert candidate["confirmed_at"] is None
    assert candidate["pattern_date"] == bars[60]["date"].isoformat()


def test_future_rows_are_rejected_instead_of_silently_used() -> None:
    bars = _series()
    with pytest.raises(ValueError, match="as_of"):
        _compute(bars, bars[62]["date"])


def test_invalidation_is_separate_linked_event_and_does_not_rewrite_origin() -> None:
    bars = _series()
    result = _compute(bars, bars[-1]["date"])
    spring = _spring(result)
    invalidation = next(event for event in result["events"] if event["event_type"] == "失效")
    assert invalidation["linked_event_id"] == spring["event_id"]
    assert invalidation["confirmed_at"] == bars[70]["date"].isoformat()
    # 原事件的历史输出保持确认当时状态，只由关联失效事件推导页面显示
    assert spring["status"] == "confirmed"
    assert spring["confirmed_at"] == bars[63]["date"].isoformat()
    assert spring["invalidation_rule"].startswith("收盘跌破支撑")


def test_invalidation_threshold_freezes_at_pattern_levels() -> None:
    """确认后的箱体低点已被弹簧下探改写，失效阈值仍按形态当时的支撑 100 计算。"""
    bars = _series()
    result = _compute(bars, bars[-1]["date"])
    invalidation = next(event for event in result["events"] if event["event_type"] == "失效")
    assert invalidation["levels"]["support"] == 100.0
    assert invalidation["evidence"][0]["threshold"] == "< 99.2"


def test_no_invalidation_row_when_as_of_precedes_break_bar() -> None:
    bars = _series()
    truncated = [bar for bar in bars if bar["date"] <= bars[66]["date"]]
    result = _compute(truncated, bars[66]["date"])
    assert not [event for event in result["events"] if event["event_type"] == "失效"]
    assert _spring(result) is not None


def test_service_ready_payload(tmp_path: Path) -> None:
    bars = _series()
    panel = _Panel(_frame(bars), latest=bars[-1]["date"])
    # 窗口是观察区：弹簧在 60 号，故截止日取 75 号、窗口 30 才能覆盖它
    payload = load_events(
        _runtime(panel, tmp_path),
        symbol="000001.SZ",
        window_bars=30,
        as_of=bars[75]["date"],
        rule_version_expected=None,
    )
    assert payload["status"] == "ready"
    assert payload["asset_type"] == "stock"
    assert payload["timeframe"] == "1d"
    assert payload["as_of"] == bars[75]["date"].isoformat()
    assert payload["spec_status"] == "unfrozen_demo"
    assert payload["data_generation"] == "gen-1"
    assert payload["rule_version"].startswith("wyckoff-daily-")
    assert len(payload["params_hash"]) == 16
    assert any(event["event_type"] == "Spring" for event in payload["events"])
    # 有界读取：只按窗口+预热向前取，不扫描全历史
    start, end = panel.calls[0]
    assert end == bars[75]["date"]
    assert (end - start).days <= 1400


def test_service_default_as_of_and_out_of_window_pattern_ignored(tmp_path: Path) -> None:
    """默认截止最后一根已完成日线；弹簧落在 30 日窗口之外时不得输出。"""
    bars = _series()
    panel = _Panel(_frame(bars), latest=bars[-1]["date"])
    payload = load_events(_runtime(panel, tmp_path), symbol="000001.SZ", window_bars=30, as_of=None, rule_version_expected=None)
    assert payload["status"] == "ready"
    assert payload["as_of"] == bars[-1]["date"].isoformat()
    assert [event for event in payload["events"] if event["event_type"] == "Spring"] == []
    assert payload["observed_bars"] >= 90


def test_service_no_daily_and_insufficient_history(tmp_path: Path) -> None:
    panel = _Panel(pl.DataFrame(), latest=date(2026, 3, 1))
    payload = load_events(_runtime(panel, tmp_path), symbol="000001.SZ", window_bars=30, as_of=None, rule_version_expected=None)
    assert payload["status"] == "no_daily"
    assert payload["events"] == []

    bars = _series()[:40]
    panel2 = _Panel(_frame(bars), latest=bars[-1]["date"])
    payload2 = load_events(_runtime(panel2, tmp_path), symbol="000001.SZ", window_bars=120, as_of=None, rule_version_expected=None)
    assert payload2["status"] == "insufficient_data"
    assert payload2["observed_bars"] == 40
    assert payload2["required_bars"] == 150


def test_service_missing_volume_column_is_not_computable(tmp_path: Path) -> None:
    bars = _series()
    frame = _frame(bars).drop("volume")
    panel = _Panel(frame, latest=bars[-1]["date"])
    payload = load_events(_runtime(panel, tmp_path), symbol="000001.SZ", window_bars=30, as_of=None, rule_version_expected=None)
    assert payload["status"] == "not_computable"
    assert "volume" in payload["missing_columns"]
    assert payload["events"] == []


def test_service_rejects_future_as_of_and_bad_window(tmp_path: Path) -> None:
    bars = _series()
    panel = _Panel(_frame(bars), latest=bars[-1]["date"])
    runtime = _runtime(panel, tmp_path)
    with pytest.raises(ResearchInputError):
        load_events(runtime, symbol="000001.SZ", window_bars=30, as_of=bars[-1]["date"] + timedelta(days=5), rule_version_expected=None)
    with pytest.raises(ResearchInputError):
        load_events(runtime, symbol="000001.SZ", window_bars=29, as_of=None, rule_version_expected=None)
    with pytest.raises(ResearchInputError):
        load_events(runtime, symbol="000001", window_bars=30, as_of=None, rule_version_expected=None)


def test_service_detects_generation_change_during_read(tmp_path: Path) -> None:
    bars = _series()
    panel = _Panel(_frame(bars), latest=bars[-1]["date"], generations=("gen-1", "gen-2"))
    payload = load_events(_runtime(panel, tmp_path), symbol="000001.SZ", window_bars=30, as_of=None, rule_version_expected=None)
    assert payload["status"] == "generation_changed"
    assert payload["data_generation"] == "gen-1"
    assert payload["observed_generation"] == "gen-2"
    assert payload["events"] == []


def test_service_excludes_unfinished_bar_after_as_of(tmp_path: Path) -> None:
    bars = _series()
    panel = _Panel(_frame(bars), latest=date(2026, 12, 31))
    payload = load_events(
        _runtime(panel, tmp_path),
        symbol="000001.SZ",
        window_bars=30,
        as_of=bars[66]["date"],
        rule_version_expected=None,
    )
    assert payload["status"] == "ready"
    assert payload["as_of"] == bars[66]["date"].isoformat()
    events = payload["events"]
    assert all(event["confirmed_at"] is None or event["confirmed_at"] <= bars[66]["date"].isoformat() for event in events)
    assert not [event for event in events if event["event_type"] == "失效"]


def test_api_events_and_errors(tmp_path: Path) -> None:
    bars = _series()
    panel = _Panel(_frame(bars), latest=bars[-1]["date"])
    app = FastAPI()
    app.include_router(build_router())
    app.dependency_overrides[get_extension_runtime] = lambda: _runtime(panel, tmp_path)
    client = TestClient(app)

    ok = client.get(
        "/api/custom/wyckoff-research/events",
        params={"symbol": "000001.SZ", "window": 30, "as_of": _series()[75]["date"].isoformat()},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["status"] == "ready"
    assert body["symbol"] == "000001.SZ"
    assert body["events"]

    future = client.get(
        "/api/custom/wyckoff-research/events",
        params={"symbol": "000001.SZ", "window": 30, "as_of": "2099-01-01"},
    )
    assert future.status_code == 400

    too_small = client.get("/api/custom/wyckoff-research/events", params={"symbol": "000001.SZ", "window": 10})
    assert too_small.status_code == 422

    bad_version = client.get(
        "/api/custom/wyckoff-research/events",
        params={"symbol": "000001.SZ", "window": 30, "rule_version": "wyckoff-daily-frozen-9"},
    )
    assert bad_version.status_code == 400


def test_frozen_spec_overrides_demo_and_must_declare_version(tmp_path: Path) -> None:
    assert load_spec(tmp_path) == ({**UNFROZEN_DEMO_SPEC}, None)

    target = tmp_path / "user_data" / "wyckoff_research" / "spec.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    frozen = {
        "spec_status": "frozen",
        "rule_version": "wyckoff-daily-frozen-1",
        "warmup_bars": 30,
        "box_window": 30,
        "volume_window": 5,
        "events": {
            "Spring": {
                "phase": "吸筹区间",
                "confirm_bars": 3,
                "conditions": [{"name": "量比", "metric": "volume_ratio", "op": ">=", "threshold": 1.5, "window": 5}],
                "invalidation": None,
            }
        },
    }
    target.write_text(json.dumps(frozen, ensure_ascii=False), encoding="utf-8")
    spec, source = load_spec(tmp_path)
    assert source is not None and Path(source).exists()
    assert spec["rule_version"] == "wyckoff-daily-frozen-1"
    assert spec_warnings(spec) == []

    bad = dict(frozen)
    bad.pop("rule_version")
    target.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SpecError):
        load_spec(tmp_path)


def test_incomplete_spec_reports_missing_fields(tmp_path: Path) -> None:
    broken = dict(UNFROZEN_DEMO_SPEC)
    broken["events"] = {"Spring": {"phase": "吸筹区间", "conditions": []}}
    assert "events.Spring.conditions" in spec_warnings(broken)

    bars = _series()
    panel = _Panel(_frame(bars), latest=bars[-1]["date"])
    target = tmp_path / "user_data" / "wyckoff_research" / "spec.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({**broken, "spec_status": "frozen", "rule_version": "wyckoff-daily-broken-1"}, ensure_ascii=False),
        encoding="utf-8",
    )
    payload = load_events(_runtime(panel, tmp_path), symbol="000001.SZ", window_bars=30, as_of=None, rule_version_expected=None)
    assert payload["status"] == "spec_missing"
    assert "events.Spring.conditions" in payload["missing_fields"]
