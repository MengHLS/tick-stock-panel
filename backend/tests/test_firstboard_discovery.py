from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from app.backtest.stats_v2 import bh_fdr_qvalues
from app.custom.firstboard_discovery.discovery import score_factor, search_rules
from app.custom.firstboard_discovery.outcomes import build_event_samples
from app.custom.firstboard_discovery.service import (
    DiscoveryParams,
    FirstboardDiscoveryService,
)
from app.custom.firstboard_discovery.storage import FirstboardDiscoveryStore


def _panel(
    *,
    closes: list[float],
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    raw_opens: list[float] | None = None,
    raw_closes: list[float] | None = None,
    boards: list[int] | None = None,
    limit_prices: list[float | None] | None = None,
) -> pl.DataFrame:
    size = len(closes)
    start = date(2026, 1, 5)
    opens = opens or closes
    highs = highs or [max(open_price, close) for open_price, close in zip(opens, closes, strict=True)]
    lows = lows or [min(open_price, close) for open_price, close in zip(opens, closes, strict=True)]
    raw_opens = raw_opens or opens
    raw_closes = raw_closes or closes
    boards = boards or [0] * size
    return pl.DataFrame({
        "symbol": ["000001.SZ"] * size,
        "name": ["测试股"] * size,
        "date": [start + timedelta(days=index) for index in range(size)],
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "raw_open": raw_opens,
        "raw_close": raw_closes,
        "consecutive_limit_ups": boards,
        "limit_up_price": limit_prices or [None] * size,
    })


def _event(panel: pl.DataFrame, **kwargs) -> dict:
    events = build_event_samples(panel, **kwargs)
    assert events.height == 1
    return events.row(0, named=True)


def test_outcomes_use_next_open_and_twenty_observed_sessions() -> None:
    closes = [10.0] + [10.5] * 19 + [11.0]
    opens = [10.0] + [10.0] * 20
    highs = [10.1] + [10.5] * 19 + [12.0]
    lows = [9.9] + [10.0] * 19 + [9.5]
    panel = _panel(
        closes=closes,
        opens=opens,
        highs=highs,
        lows=lows,
        boards=[1] + [0] * 20,
    )

    row = _event(panel)

    assert row["entry_date"] == date(2026, 1, 6)
    assert row["entry_open"] == pytest.approx(10.0)
    assert row["sessions_observed"] == 20
    assert row["right_censored"] is False
    assert row["mfe_5d"] == pytest.approx(0.05)
    assert row["close_return_5d"] == pytest.approx(0.05)
    assert row["mae_5d"] == pytest.approx(0.0)
    assert row["mfe_10d"] == pytest.approx(0.05)
    assert row["close_return_10d"] == pytest.approx(0.05)
    assert row["mae_10d"] == pytest.approx(0.0)
    assert row["mfe_20d"] == pytest.approx(0.20)
    assert row["close_return_20d"] == pytest.approx(0.10)
    assert row["mae_20d"] == pytest.approx(-0.05)
    assert row["stop_touched"] is False
    assert row["strong"] is True


def test_right_censored_event_is_not_labeled() -> None:
    panel = _panel(closes=[10.0] * 10, boards=[1] + [0] * 9)

    row = _event(panel)

    assert row["sessions_observed"] == 9
    assert row["right_censored"] is True
    assert row["mfe_5d"] == pytest.approx(0.0)
    assert row["close_return_5d"] == pytest.approx(0.0)
    assert row["mae_5d"] == pytest.approx(0.0)
    assert row["mfe_10d"] is None
    assert row["close_return_10d"] is None
    assert row["mae_10d"] is None
    assert row["mfe_20d"] is None
    assert row["strong"] is None


def test_limit_locked_entry_is_excluded() -> None:
    panel = _panel(
        closes=[10.0] + [11.0] * 20,
        raw_opens=[10.0, 11.0] + [11.0] * 19,
        raw_closes=[10.0] + [11.0] * 20,
        boards=[1] + [0] * 20,
        limit_prices=[None, 11.0] + [None] * 19,
    )

    row = _event(panel)

    assert row["entry_limit_locked"] is True
    assert row["strong"] is None


def test_future_rows_do_not_change_an_earlier_event() -> None:
    base = _panel(closes=[10.0] * 21, boards=[1] + [0] * 20)
    changed = base.with_columns(
        pl.when(pl.int_range(pl.len()) > 20)
        .then(pl.col("close") * 100)
        .otherwise(pl.col("close"))
        .alias("close")
    )

    before = build_event_samples(base)
    after = build_event_samples(changed)

    assert before.equals(after)


def test_scale_break_inside_outcome_window_is_flagged() -> None:
    panel = _panel(
        closes=[10.0] + [10.0] * 20,
        raw_closes=[10.0] * 10 + [20.0] * 11,
        boards=[1] + [0] * 20,
    )

    row = _event(panel)

    assert row["scale_break_suspected"] is True
    assert row["strong"] is None


def test_invalid_price_inside_twenty_day_window_is_accounted() -> None:
    panel = _panel(
        closes=[10.0] * 21,
        highs=[10.1] + [10.5] * 19 + [None],
        boards=[1] + [0] * 20,
    )

    row = _event(panel)

    assert row["right_censored"] is False
    assert row["outcome_unavailable"] is True
    assert row["mfe_20d"] is None
    assert row["strong"] is None


def test_score_factor_uses_rank_auc_direction_and_missing_values() -> None:
    perfect = score_factor(
        "f",
        "D_close",
        [1, 2, 3, 4],
        [False, False, True, True],
    )
    inverse = score_factor(
        "f",
        "D_close",
        [4, 3, 2, 1],
        [False, False, True, True],
    )
    with_missing = score_factor(
        "f",
        "D_close",
        [1, 2, None, 4],
        [False, False, True, True],
    )

    assert perfect.auc == pytest.approx(1.0)
    assert perfect.direction == "high"
    assert inverse.auc == pytest.approx(0.0)
    assert inverse.direction == "low"
    assert with_missing.coverage == pytest.approx(0.75)
    assert with_missing.train_count == 3


def test_bh_fdr_qvalues_ignores_missing_hypotheses() -> None:
    values = bh_fdr_qvalues([0.01, 0.04, None])

    assert values[0] == pytest.approx(0.02)
    assert values[1] == pytest.approx(0.04)
    assert values[2] is None


def _rule_events(
    *,
    train_count: int = 120,
    validation_count: int = 40,
) -> pl.DataFrame:
    total = train_count + validation_count
    values = [index / max(total - 1, 1) for index in range(total)]
    returns = [value - 0.5 for value in values]
    return pl.DataFrame({
        "date": [date(2026, 1, 1) + timedelta(days=index) for index in range(total)],
        "strong": [value >= 0.5 for value in values],
        "mfe_5d": [0.12 if value >= 0.5 else 0.03 for value in values],
        "close_return_5d": [0.04 if value >= 0.5 else -0.01 for value in values],
        "mae_5d": [-0.01] * total,
        "mfe_10d": [0.20 if value >= 0.5 else 0.04 for value in values],
        "close_return_10d": [0.06 if value >= 0.5 else -0.02 for value in values],
        "mae_10d": [-0.02] * total,
        "mfe_20d": [0.30 if value >= 0.5 else 0.05 for value in values],
        "close_return_20d": returns,
        "mae_20d": [-0.03] * total,
        "D_close__f_good": values,
    })


def test_rule_search_selects_on_training_dates_only() -> None:
    events = _rule_events()
    train_end = events["date"][119]
    original = search_rules(
        events,
        [("f_good", "D_close")],
        train_end=train_end,
        base_rate=0.5,
    )
    changed_validation = events.with_columns(
        pl.when(pl.int_range(pl.len()) >= 120)
        .then(1.0 - pl.col("D_close__f_good"))
        .otherwise(pl.col("D_close__f_good"))
        .alias("D_close__f_good")
    )
    after = search_rules(
        changed_validation,
        [("f_good", "D_close")],
        train_end=train_end,
        base_rate=0.5,
    )

    assert original
    assert original[0]["conditions"] == after[0]["conditions"]
    assert original[0]["train_strong_rate"] > 0.8
    assert "validation_strong_rate" in original[0]
    assert "lift" in original[0]
    assert "validation_lift" in original[0]
    assert "mean_mfe_5d" in original[0]
    assert "mean_close_return_10d" in original[0]
    assert "mean_mae_20d" in original[0]


def test_rule_search_rejects_insufficient_training_support() -> None:
    too_small = _rule_events(train_count=20, validation_count=40)

    assert search_rules(
        too_small,
        [("f_good", "D_close")],
        train_end=too_small["date"][19],
        base_rate=0.5,
    ) == []


def test_rule_search_marks_sparse_validation_without_reselecting() -> None:
    too_few_validation = _rule_events(train_count=120, validation_count=10)

    rules = search_rules(
        too_few_validation,
        [("f_good", "D_close")],
        train_end=too_few_validation["date"][119],
        base_rate=0.5,
    )

    assert rules
    assert all(rule["validation_eligible"] is False for rule in rules)


class _FakeEngine:
    def __init__(self, panel: pl.DataFrame, generation: str = "gen-1") -> None:
        self.panel = panel
        self.generation = generation
        self.load_calls = 0

    def data_generation(self, asset_type: str = "stock") -> str:
        assert asset_type == "stock"
        return self.generation

    def load_panel(self, *_args, **_kwargs) -> pl.DataFrame:
        self.load_calls += 1
        return self.panel


class _FakeRepository:
    def get_instruments_asset(self, asset_type: str = "stock") -> pl.DataFrame:
        assert asset_type == "stock"
        return pl.DataFrame()

    def get_historical_shares(self) -> None:
        return None


class _TestDiscoveryService(FirstboardDiscoveryService):
    def _candidate_factor_columns(self, snapshot_mode: str) -> list[tuple[str, str]]:
        del snapshot_mode
        return [("momentum_5d", "D_close")]

    def _materialize_factors(
        self,
        panel: pl.DataFrame,
        factor_ids: set[str],
    ) -> pl.DataFrame:
        assert factor_ids == {"momentum_5d"}
        return panel

    def _attach_limit_prices(self, panel: pl.DataFrame) -> pl.DataFrame:
        return panel


def _sample_accounting_panel() -> pl.DataFrame:
    size = 24
    start = date(2026, 1, 5)
    boards = [0] * size
    for index in (0, 1, 2, 3, 23):
        boards[index] = 1
    return pl.DataFrame({
        "symbol": ["000001.SZ"] * size,
        "name": ["测试股"] * size,
        "date": [start + timedelta(days=index) for index in range(size)],
        "open": [10.0] * size,
        "high": [10.5] * size,
        "low": [9.8] * size,
        "close": [10.0] * size,
        "raw_open": [10.0] * size,
        "raw_close": [10.0] * size,
        "consecutive_limit_ups": boards,
        "momentum_5d": [index / size for index in range(size)],
    })


def test_report_excludes_ineligible_events_and_returns_sample_accounting() -> None:
    panel = _sample_accounting_panel()
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    params = DiscoveryParams(
        start=panel["date"][0],
        end=panel["date"][-1],
        snapshot_mode="D_close",
    )

    report = service.report(params)

    assert report["sample"]["total_events"] == 5
    assert report["sample"]["eligible_events"] == 4
    assert report["sample"]["excluded"]["right_censored"] == 1
    assert report["split"]["train_end"] < report["split"]["validation_start"]
    assert report["sample"]["status"] == "insufficient_sample"


def _discoverable_panel(event_count: int = 600) -> pl.DataFrame:
    rows: list[dict] = []
    start = date(2025, 1, 1)
    for index in range(event_count):
        symbol = f"{index:06d}.SZ"
        event_date = start + timedelta(days=index)
        strong = index % 10 >= 5
        for offset in range(21):
            rows.append({
                "symbol": symbol,
                "name": f"样本{index}",
                "date": event_date + timedelta(days=offset),
                "open": 10.0,
                "high": 10.5 if offset == 0 else (12.0 if strong else 10.2),
                "low": 9.8,
                "close": 10.0 if offset == 0 else (11.0 if strong else 10.0),
                "raw_open": 10.0,
                "raw_close": 10.0 if offset == 0 else (11.0 if strong else 10.0),
                "consecutive_limit_ups": 1 if offset == 0 else 0,
                "momentum_5d": (index % 10) / 9,
            })
    return pl.DataFrame(rows)


def test_events_endpoint_paginates_and_filters_by_rule() -> None:
    panel = _discoverable_panel()
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    params = DiscoveryParams(
        start=panel["date"].min(),
        end=panel["date"].max(),
        snapshot_mode="D_close",
    )

    report = service.report(params)
    assert report["rules"]
    rule_id = report["rules"][0]["id"]
    payload = service.events(params, rule_id=rule_id, page=1, page_size=2)

    assert payload["page_size"] == 2
    assert len(payload["rows"]) == 2
    assert payload["total"] >= 2
    assert all(rule_id in row["rule_ids"] for row in payload["rows"])
    assert "mfe_5d" in payload["rows"][0]
    assert "close_return_10d" in payload["rows"][0]
    assert "mae_20d" in payload["rows"][0]


def test_training_snapshot_is_persisted_and_reopenable(tmp_path) -> None:
    panel = _sample_accounting_panel()
    store = FirstboardDiscoveryStore(tmp_path)
    service = _TestDiscoveryService(
        _FakeRepository(), engine=_FakeEngine(panel), storage=store,
    )
    params = DiscoveryParams(
        start=panel["date"][0],
        end=panel["date"][-1],
        snapshot_mode="D_close",
    )

    report = service.report(params)
    run_id = report["run_id"]
    assert run_id
    assert report["saved_at"]

    reopened = FirstboardDiscoveryService(
        _FakeRepository(), engine=_FakeEngine(panel.head(0)), storage=store,
    )
    runs = reopened.list_runs()
    assert runs[0]["run_id"] == run_id
    assert runs[0]["event_count"] == report["sample"]["total_events"]
    assert reopened.saved_report(run_id)["sample"] == report["sample"]
    events = reopened.saved_events(run_id, page_size=200)
    assert events["total"] == report["sample"]["total_events"]
    assert len(events["rows"]) == events["total"]


def test_store_infers_late_float_columns_across_all_event_rows(tmp_path) -> None:
    store = FirstboardDiscoveryStore(tmp_path)
    report = {
        "algorithm_version": "test", "generation": "gen", "params": {},
        "sample": {"status": "ok"}, "split": {}, "factors": [], "rules": [],
        "elapsed_ms": 1.0,
    }
    events = [
        {"event_id": "a", "mfe_5d": None},
        {"event_id": "b", "mfe_5d": 0.08},
    ]

    run_id, _ = store.save(report, events)
    loaded = store.load_events(run_id)

    assert loaded[0]["mfe_5d"] is None
    assert loaded[1]["mfe_5d"] == pytest.approx(0.08)


def test_service_rejects_data_generation_change() -> None:
    panel = _sample_accounting_panel()
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    params = DiscoveryParams(
        start=panel["date"][0],
        end=panel["date"][-1],
        snapshot_mode="D_close",
    )

    def changed(generation: str) -> None:
        raise RuntimeError("generation changed") from None

    service._assert_generation = changed  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="generation changed"):
        service.report(params)


def test_api_routes_validate_parameters_and_return_reports(monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.custom.firstboard_discovery as extension
    from app.extensions import BackendExtensionRegistrar

    panel = _sample_accounting_panel()
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    monkeypatch.setattr(extension, "_service", service, raising=False)
    registrar = BackendExtensionRegistrar("official.firstboard-discovery", api_version=1)
    extension.setup(registrar)
    app = FastAPI()
    for router in registrar.routers:
        app.include_router(router)
    client = TestClient(app)
    query = {"start": "2026-01-05", "end": "2026-01-28", "snapshot_mode": "D_close"}
    report = client.get("/api/custom/firstboard-discovery/report", params=query)
    assert report.status_code == 200
    assert report.json()["sample"]["eligible_events"] == 4
    assert client.get(
        "/api/custom/firstboard-discovery/report",
        params={**query, "start": "2026-02-01"},
    ).status_code == 400
    assert client.get(
        "/api/custom/firstboard-discovery/events",
        params={**query, "page_size": 201},
    ).status_code == 422
    monkeypatch.setattr(extension, "_service", None)
    assert client.get(
        "/api/custom/firstboard-discovery/report", params=query,
    ).status_code == 503


def test_saved_result_api_routes_list_and_reopen_runs(monkeypatch, tmp_path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.custom.firstboard_discovery as extension
    from app.extensions import BackendExtensionRegistrar

    panel = _sample_accounting_panel()
    service = _TestDiscoveryService(
        _FakeRepository(),
        engine=_FakeEngine(panel),
        storage=FirstboardDiscoveryStore(tmp_path),
    )
    monkeypatch.setattr(extension, "_service", service, raising=False)
    registrar = BackendExtensionRegistrar("official.firstboard-discovery", api_version=1)
    extension.setup(registrar)
    app = FastAPI()
    for router in registrar.routers:
        app.include_router(router)
    client = TestClient(app)
    query = {"start": "2026-01-05", "end": "2026-01-28", "snapshot_mode": "D_close"}

    report = client.get("/api/custom/firstboard-discovery/report", params=query).json()
    run_id = report["run_id"]
    listed = client.get("/api/custom/firstboard-discovery/runs")
    reopened = client.get(f"/api/custom/firstboard-discovery/runs/{run_id}/report")
    events = client.get(
        f"/api/custom/firstboard-discovery/runs/{run_id}/events",
        params={"page_size": 200},
    )

    assert listed.status_code == 200
    assert listed.json()["items"][0]["run_id"] == run_id
    assert reopened.status_code == 200
    assert reopened.json()["run_id"] == run_id
    assert events.status_code == 200
    assert events.json()["total"] == report["sample"]["total_events"]
    assert client.get(
        "/api/custom/firstboard-discovery/runs/not-a-real-run/report",
    ).status_code == 404


def test_training_outcomes_end_strictly_before_validation() -> None:
    panel = _discoverable_panel()
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    params = DiscoveryParams(start=panel["date"].min(), end=panel["date"].max())
    report = service.report(params)
    rows = service.events(params, page_size=200)["rows"]
    validation_start = date.fromisoformat(str(report["split"]["validation_start"]))
    assert report["split"]["purged_count"] > 0
    assert all(row["outcome_end"] < validation_start for row in rows if row["split"] == "train")


def test_stock_suspension_does_not_move_t_plus_one_to_a_later_session() -> None:
    a = _panel(closes=[10.] * 23, boards=[1] + [0] * 22)
    b = a.with_columns(pl.lit("000002.SZ").alias("symbol"), pl.lit(0, dtype=pl.Int64).alias("consecutive_limit_ups"))
    a = a.filter(pl.col("date") != date(2026, 1, 6))
    row = build_event_samples(pl.concat([a, b])).row(0, named=True)
    assert row["entry_unavailable"] is True
    assert row["strong"] is None


def test_missing_symbol_days_are_reported_as_outcome_unavailable() -> None:
    complete = _panel(closes=[10.] * 21, boards=[0] * 21)
    event_symbol = _panel(closes=[10.] * 21, boards=[1] + [0] * 20).head(11)
    other_symbol = complete.with_columns(
        pl.lit("000002.SZ").alias("symbol"),
    )

    row = build_event_samples(pl.concat([event_symbol, other_symbol])).row(0, named=True)

    assert row["right_censored"] is False
    assert row["entry_unavailable"] is False
    assert row["outcome_unavailable"] is True
    assert row["mfe_20d"] is None
    assert row["strong"] is None


def test_tercile_rules_partition_finite_values_without_overlap() -> None:
    from app.custom.firstboard_discovery.discovery import _candidate_mask

    events = pl.DataFrame({"v": [0., 1., 2., 3., None, float("nan")]})
    groups = [
        _candidate_mask(events, [("v", "bucket", (1., 2., bucket))])["v"].to_list()
        for bucket in range(3)
    ]
    assert groups == [[0.], [1.], [2., 3.]]


def test_event_response_contains_no_nan_for_missing_factor_values() -> None:
    import json

    panel = _sample_accounting_panel().with_columns(
        pl.lit(float("nan")).alias("momentum_5d"),
    )
    service = _TestDiscoveryService(_FakeRepository(), engine=_FakeEngine(panel))
    params = DiscoveryParams(start=panel["date"].min(), end=panel["date"].max())
    payload = service.events(params)
    assert payload["rows"][0]["D_close__momentum_5d"] is None
    json.dumps(payload, default=str, allow_nan=False)
