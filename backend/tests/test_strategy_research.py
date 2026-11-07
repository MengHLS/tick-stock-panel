from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.custom.strategy_research.baseline import load_baseline
from app.custom.strategy_research.experiments import create_experiment
from app.custom.strategy_research.path import PathConfig, build_path_report
from app.custom.strategy_research.routes import build_router
from app.custom.strategy_research.store import (
    ResearchStoreError,
    inbox_dir,
    list_reports,
    read_report,
    resolve_inbox_file,
    write_report,
)
from app.extensions import get_extension_runtime


def _baseline(**overrides) -> dict:
    value = {
        "baseline_id": "base_test",
        "label": "test baseline",
        "strategy_id": "first_limit_pullback_3f_runner_t74",
        "strategy_name": "T74",
        "start": "2024-01-01",
        "end": "2024-01-31",
        "trade_count": 1,
        "execution": {"entry_price_basis": "raw", "stop_loss_pct": -0.06},
        "data": {"generation": "gen-1"},
        "legacy_config": {},
    }
    value.update(overrides)
    return value


def _trade(
    *,
    symbol: str = "000001.SZ",
    entry_date: str = "2024-01-02",
    entry_price: float = 100.0,
    exit_date: str | None = "2024-01-04",
    exit_reason: str = "signal",
    pnl_pct: float = 0.03,
) -> dict:
    return {
        "symbol": symbol,
        "entry_date": entry_date,
        "entry_price": entry_price,
        "exit_date": exit_date,
        "exit_reason": exit_reason,
        "pnl_pct": pnl_pct,
        "pnl_amount": pnl_pct * 1000,
        "duration": 2,
        "open_at_end": False,
        "entry_score": 0.8,
    }


def _bars(rows: list[tuple[str, str, float, float, float, float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": [row[0] for row in rows],
            "date": [date.fromisoformat(row[1]) for row in rows],
            "open": [row[2] for row in rows],
            "high": [row[3] for row in rows],
            "low": [row[4] for row in rows],
            "close": [row[5] for row in rows],
            "raw_close": [row[6] for row in rows],
        }
    )


def _report(trades, bars, *, horizon: int = 20, thresholds=(0.2, 0.3)):
    return build_path_report(
        trades=tuple(trades),
        bars=bars,
        baseline=_baseline(),
        config=PathConfig(
            horizon_sessions=horizon,
            thresholds=thresholds,
            entry_price_basis="raw",
        ),
        latest_data_date=date(2024, 2, 1),
        data_identity={"date": "2024-02-01", "signature": "gen-1"},
    )


def test_path_report_marks_stop_before_first_target() -> None:
    bars = _bars(
        [
            ("000001.SZ", "2024-01-02", 100, 101, 94, 100, 100),
            ("000001.SZ", "2024-01-03", 99, 105, 95, 104, 104),
            ("000001.SZ", "2024-01-04", 104, 121, 96, 120, 120),
        ]
    )
    report = _report(
        [_trade(exit_date="2024-01-03", exit_reason="stop_loss", pnl_pct=-0.06)],
        bars,
        horizon=5,
    )
    event = report["events"][0]
    item = event["thresholds"][0]
    assert item["hit"] is True
    assert item["first_target_date"] == "2024-01-04"
    assert item["days_to_target"] == 3
    assert item["pre_target_adverse_excursion"] == pytest.approx(-0.06)
    assert item["tail_vs_exit"] == "stop_before_tail"
    summary = report["summary"]["by_threshold"][0]
    assert summary["hit_count"] == 1
    assert summary["stopped_before_hit_count"] == 1
    assert summary["hit_before_stop_count"] == 0


def test_path_report_marks_tail_before_stop() -> None:
    bars = _bars(
        [
            ("000001.SZ", "2024-01-02", 100, 101, 99, 100, 100),
            ("000001.SZ", "2024-01-03", 101, 125, 100, 124, 124),
            ("000001.SZ", "2024-01-04", 120, 121, 90, 92, 92),
        ]
    )
    report = _report(
        [_trade(exit_date="2024-01-04", exit_reason="stop_loss", pnl_pct=-0.06)],
        bars,
        horizon=5,
    )
    item = report["events"][0]["thresholds"][0]
    assert item["hit"] is True
    assert item["tail_vs_exit"] == "tail_before_stop"
    assert report["summary"]["by_threshold"][0]["hit_before_stop_count"] == 1


def test_path_report_flags_same_day_target_and_stop() -> None:
    bars = _bars([("000001.SZ", "2024-01-02", 100, 125, 93, 100, 100)])
    report = _report([_trade(exit_date="2024-01-02")], bars, horizon=5)
    item = report["events"][0]["thresholds"][0]
    assert item["hit"] is True
    assert item["target_day_also_stop"] is True
    assert report["summary"]["by_threshold"][0]["same_day_target_and_stop_count"] == 1


def test_path_report_converts_raw_entry_to_adjusted_basis() -> None:
    bars = _bars(
        [
                ("000001.SZ", "2024-01-02", 16.0, 17.0, 15.0, 16.0, 8.0),
            ("000001.SZ", "2024-01-03", 20, 24, 19, 23, 11.5),
        ]
    )
    report = _report([_trade(entry_price=10.0, exit_date="2024-01-03")], bars, horizon=5)
    event = report["events"][0]
    assert event["entry_price_adjusted"] == pytest.approx(20.0)
    assert event["max_favorable_excursion"] == pytest.approx(0.20)
    assert event["thresholds"][0]["hit"] is True


def test_path_report_separates_partial_and_missing_symbols() -> None:
    bars = _bars(
        [
            ("000001.SZ", "2024-01-02", 100, 101, 99, 100, 100),
            ("000001.SZ", "2024-01-03", 100, 102, 99, 101, 101),
        ]
    )
    trades = [
        _trade(symbol="000001.SZ"),
        _trade(symbol="000002.SZ", entry_date="2024-01-03"),
    ]
    report = _report(trades, bars, horizon=5)
    assert report["events"][0]["coverage_status"] == "partial"
    assert report["events"][1]["coverage_status"] == "missing_symbol"
    assert report["data_quality"]["partial_window_count"] == 1
    assert report["data_quality"]["missing_symbol_count"] == 1


def test_store_rejects_path_traversal_and_round_trips_report(tmp_path: Path) -> None:
    inbox = inbox_dir(tmp_path)
    (inbox / "baseline.json").write_text("{}", encoding="utf-8")
    assert resolve_inbox_file(tmp_path, "baseline.json").name == "baseline.json"
    with pytest.raises(ResearchStoreError):
        resolve_inbox_file(tmp_path, "../baseline.json")
    with pytest.raises(ResearchStoreError):
        resolve_inbox_file(tmp_path, "missing.json")

    report = {
        "report_id": "rpt_0123456789ab",
        "created_at": "2026-01-01T00:00:00+00:00",
        "label": "test",
        "baseline": {"baseline_id": "base_test"},
        "config": {"horizon_sessions": 20},
        "sample_ledger": {},
        "summary": {},
        "data_quality": {},
        "events": [],
    }
    write_report(tmp_path, report)
    assert read_report(tmp_path, report["report_id"])["label"] == "test"
    assert list_reports(tmp_path)[0]["report_id"] == report["report_id"]
    with pytest.raises(ResearchStoreError):
        read_report(tmp_path, "../escape")


def test_load_baseline_normalizes_artifact_result(tmp_path: Path) -> None:
    payload = {
        "error": None,
        "stats": {
            "initial_capital": 100000,
            "total_return": 3.3104,
            "completed_trade_count": 1,
        },
        "trades": [
            {
                "symbol": "000001.SZ",
                "entry_date": "2024-01-02",
                "entry_price": 100,
                "exit_date": "2024-01-04",
                "exit_reason": "signal",
                "pnl_pct": 0.03,
                "pnl_amount": 300,
                "duration": 2,
                "open_at_end": False,
            }
        ],
        "config": {
            "strategy_id": "first_limit_pullback_3f_runner_t74",
            "start": "2024-01-01",
            "end": "2024-01-31",
            "initial_capital": 100000,
            "params": {"_event_allowlist": ["000001.SZ@2024-01-02"]},
            "overrides": {"stop_loss": -0.06},
        },
        "provenance": {
            "execution": {"entry_price_basis": "raw", "stop_loss_pct": -0.06},
            "data": {"generation": "gen-1"},
        },
        "strategy_info": {"id": "first_limit_pullback_3f_runner_t74", "name": "T74"},
    }
    path = inbox_dir(tmp_path) / "t74.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    baseline = load_baseline(
        data_dir=tmp_path,
        source_kind="file",
        saved_id=None,
        file_name="t74.json",
        label="331 baseline",
    )
    assert baseline.label == "331 baseline"
    assert baseline.summary["trade_count"] == 1
    assert baseline.summary["execution"]["stop_loss_pct"] == -0.06
    assert baseline.summary["legacy_config"]["event_allowlist_count"] == 1
    assert baseline.trades[0]["symbol"] == "000001.SZ"


class _FakeMarketData:
    def latest_daily_date(self):
        return date(2024, 2, 1)

    def get_daily_batch(self, symbols, start, end, columns=None):
        assert "000001.SZ" in symbols
        return _bars(
            [
                ("000001.SZ", "2024-01-02", 100, 101, 94, 100, 100),
                ("000001.SZ", "2024-01-03", 99, 100, 95, 96, 96),
                ("000001.SZ", "2024-01-04", 96, 126, 95, 125, 125),
            ]
        )

    def dataset_partition_signature(self, dataset, suffix):
        return "gen-1"


def _api_app(tmp_path: Path) -> TestClient:
    runtime = SimpleNamespace(
        data_dir=tmp_path,
        market_data=_FakeMarketData(),
        backtest_results=None,
    )
    app = FastAPI()
    app.include_router(build_router())
    app.dependency_overrides[get_extension_runtime] = lambda: runtime
    return TestClient(app)


def test_api_creates_lists_and_filters_path_report(tmp_path: Path) -> None:
    payload = {
        "error": None,
        "stats": {"initial_capital": 100000},
        "trades": [
            {
                "symbol": "000001.SZ",
                "entry_date": "2024-01-02",
                "entry_price": 100,
                "exit_date": "2024-01-03",
                "exit_reason": "stop_loss",
                "pnl_pct": -0.06,
                "pnl_amount": -60,
                "duration": 1,
                "open_at_end": False,
            }
        ],
        "config": {
            "strategy_id": "first_limit_pullback_3f_runner_t74",
            "start": "2024-01-01",
            "end": "2024-01-31",
            "initial_capital": 100000,
            "params": {},
            "overrides": {"stop_loss": -0.06},
        },
        "provenance": {"execution": {"entry_price_basis": "raw"}},
    }
    (inbox_dir(tmp_path) / "t74.json").write_text(json.dumps(payload), encoding="utf-8")
    client = _api_app(tmp_path)

    response = client.post(
        "/api/custom/strategy-research/reports",
        json={
            "source": {"kind": "file", "file_name": "t74.json"},
            "horizon_sessions": 20,
            "thresholds": [0.2],
        },
    )
    assert response.status_code == 200, response.text
    report_id = response.json()["report"]["report_id"]
    assert response.json()["report"]["summary"]["by_threshold"][0]["hit_count"] == 1

    listings = client.get("/api/custom/strategy-research/reports").json()["items"]
    assert listings[0]["report_id"] == report_id
    events = client.get(
        f"/api/custom/strategy-research/reports/{report_id}/events",
        params={"threshold": 0.2, "outcome": "stop_before_hit"},
    ).json()
    assert events["total"] == 1
    assert events["items"][0]["thresholds"][0]["tail_vs_exit"] == "stop_before_tail"

    invalid = client.post(
        "/api/custom/strategy-research/reports",
        json={
            "source": {"kind": "file", "file_name": "t74.json"},
            "thresholds": [-0.1],
        },
    )
    assert invalid.status_code == 422


def _event(
    event_id: str,
    *,
    hit: bool,
    exit_reason: str = "signal",
    pnl_pct: float = 0.1,
) -> dict:
    return {
        "event_id": event_id,
        "symbol": event_id.split("@")[0],
        "entry_date": event_id.split("@")[1],
        "exit_date": "2024-01-10",
        "exit_reason": exit_reason,
        "pnl_pct": pnl_pct,
        "coverage_status": "complete",
        "thresholds": [
            {
                "threshold": 0.2,
                "hit": hit,
                "actual_realized": pnl_pct >= 0.2,
                "tail_vs_exit": "no_tail" if not hit else "tail_before_exit",
            }
        ],
    }


def test_experiment_compares_lost_and_gained_tail_events(tmp_path: Path) -> None:
    control = {
        "report_id": "rpt_000000000001",
        "created_at": "2026-01-01T00:00:00+00:00",
        "label": "control",
        "baseline": {"baseline_id": "base_control", "start": "2024-01-01", "end": "2024-02-01"},
        "config": {"horizon_sessions": 20, "thresholds": [0.2]},
        "summary": {"event_count": 2, "exit_reasons": {"signal": 1, "stop_loss": 1}},
        "events": [
            _event("000001.SZ@2024-01-02", hit=True),
            _event("000002.SZ@2024-01-03", hit=False, exit_reason="stop_loss", pnl_pct=-0.06),
        ],
    }
    variant = {
        "report_id": "rpt_000000000002",
        "created_at": "2026-01-01T00:00:00+00:00",
        "label": "variant",
        "baseline": {"baseline_id": "base_variant", "start": "2024-01-01", "end": "2024-02-01"},
        "config": {"horizon_sessions": 20, "thresholds": [0.2]},
        "summary": {"event_count": 2, "exit_reasons": {"stop_loss": 1, "signal": 1}},
        "events": [
            _event("000001.SZ@2024-01-02", hit=False, exit_reason="stop_loss", pnl_pct=-0.06),
            _event("000002.SZ@2024-01-03", hit=True),
        ],
    }
    write_report(tmp_path, control)
    write_report(tmp_path, variant)
    experiment = create_experiment(
        tmp_path,
        name="stop test",
        hypothesis="tighter stop keeps tails",
        changed_decision="hold_exit",
        control_report_id=control["report_id"],
        variant_report_id=variant["report_id"],
        factor_id=None,
        conclusion="inconclusive",
        notes=None,
    )
    row = experiment["comparison"]["by_threshold"][0]
    assert row["lost_tail_count"] == 1
    assert row["gained_tail_count"] == 1
    assert row["tail_retention_rate"] == 0.0
    assert row["control_stop_loss_count"] == 1
    assert row["variant_stop_loss_count"] == 1


def test_factor_hypothesis_ledger_api(tmp_path: Path) -> None:
    client = _api_app(tmp_path)
    created = client.post(
        "/api/custom/strategy-research/factors",
        json={
            "factor_key": "linkage_industry_strength",
            "name": "行业联动强度",
            "version": "v1",
            "purpose": "candidate_rank",
            "earliest_known_at": "T日收盘后",
            "direction": "越强越可能保留右尾",
            "missing_policy": "缺失不参与排序",
            "hypothesis": "只改变同日候选排序，不改变退出规则。",
            "status": "testing",
        },
    )
    assert created.status_code == 200, created.text
    factor_id = created.json()["factor"]["factor_id"]
    updated = client.put(
        f"/api/custom/strategy-research/factors/{factor_id}",
        json={"status": "rejected", "evidence": "two seeds failed"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["factor"]["status"] == "rejected"
    listed = client.get("/api/custom/strategy-research/factors").json()["items"]
    assert listed[0]["factor_key"] == "linkage_industry_strength"
