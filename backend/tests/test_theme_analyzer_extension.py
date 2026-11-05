"""Theme analyzer store, computation, and API contracts."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.custom.theme_analyzer import router, store
from app.custom.theme_analyzer.service import ThemeAnalyzerService
from app.extensions.runtime import get_extension_runtime

START = date(2026, 1, 1)
DATES = [START + timedelta(days=index) for index in range(40)]
SYMBOL_A = "000001.SZ"
SYMBOL_B = "000002.SZ"


def _daily_rows() -> list[dict]:
    closes_a = [10.0] * 20 + [11.0, 12.0, 13.0] + [10.0] * 11 + [11.0, 12.0, 13.0] + [10.0] * 3
    rows: list[dict] = []
    for index, day in enumerate(DATES):
        for symbol, close in ((SYMBOL_A, closes_a[index]), (SYMBOL_B, 20.0)):
            rows.append({
                "symbol": symbol,
                "date": day,
                "open": close,
                "high": 14.0 if symbol == SYMBOL_A and index == 36 else close,
                "low": close * 0.98,
                "close": close,
                "volume": 1000.0 + index,
                "amount": (1000.0 + index) * close * 100.0,
            })
    return rows


def _event_rows(day: date) -> list[dict]:
    if day not in {DATES[20], DATES[21], DATES[36], DATES[38], DATES[39]}:
        return []

    def row(
        symbol: str,
        name: str,
        *,
        sealed: bool,
        consec: int,
        first_time: str,
        reason: str,
    ) -> dict:
        return {
            "trade_date": day.isoformat(),
            "symbol": symbol,
            "name": name,
            "in_limit_up_pool": 1 if sealed else 0,
            "in_limit_break_pool": 0 if sealed else 1,
            "continue_day_cnt": consec,
            "limit_up_reason": reason,
            "limit_up_time": first_time,
            "first_seal_time": first_time,
            "last_seal_time": first_time,
            "limit_up_pool_open_times": 0,
            "break_pool_open_times": 0,
            "seal_money": 1.2e8 if sealed else 0.0,
        }

    rows: list[dict] = []
    if day in {DATES[20], DATES[21], DATES[36], DATES[39]}:
        rows.append(row(
            SYMBOL_A,
            "甲股份",
            sealed=True,
            consec=1 if day != DATES[21] else 2,
            first_time="09:35",
            reason="测试+题材",
        ))
    if day == DATES[20]:
        rows.append(row(
            SYMBOL_B,
            "乙股份",
            sealed=False,
            consec=0,
            first_time="10:00",
            reason="测试炸板",
        ))
    elif day == DATES[21]:
        rows.append(row(
            SYMBOL_B,
            "乙股份",
            sealed=True,
            consec=2,
            first_time="09:20",
            reason="测试接力",
        ))
    elif day == DATES[36]:
        rows.append(row(
            SYMBOL_B,
            "乙股份",
            sealed=True,
            consec=1,
            first_time="09:50",
            reason="测试龙头峰值日",
        ))
    elif day == DATES[38]:
        rows.append(row(
            SYMBOL_B,
            "乙股份",
            sealed=True,
            consec=1,
            first_time="09:50",
            reason="测试补涨",
        ))
    elif day == DATES[39]:
        rows.append(row(
            SYMBOL_B,
            "乙股份",
            sealed=False,
            consec=0,
            first_time="10:00",
            reason="测试炸板",
        ))
    return rows


class FakeMarketData:
    def __init__(self, *, with_minute: bool = True) -> None:
        self.daily = pl.DataFrame(_daily_rows()).with_columns(pl.col("date").cast(pl.Date))
        self.with_minute = with_minute

    def get_instruments(self, asset_type: str = "stock") -> pl.DataFrame:
        assert asset_type == "stock"
        return pl.DataFrame({
            "symbol": [SYMBOL_A, SYMBOL_B],
            "name": ["甲阳股份", "乙洋股份"],
        })

    def get_historical_shares(self) -> pl.DataFrame:
        return pl.DataFrame()

    def get_daily_batch(
        self,
        symbols: list[str],
        start: date,
        end: date,
        columns: list[str] | None = None,
    ) -> pl.DataFrame:
        frame = self.daily.filter(
            pl.col("symbol").is_in(symbols)
            & (pl.col("date") >= start)
            & (pl.col("date") <= end)
        )
        previous_day = date(2026, 10, 30)
        if start <= previous_day <= end:
            frame = pl.concat([
                frame,
                pl.DataFrame({
                    "symbol": [SYMBOL_A, SYMBOL_B],
                    "date": [previous_day, previous_day],
                    "open": [10.0, 20.0],
                    "high": [10.0, 20.0],
                    "low": [10.0, 20.0],
                    "close": [10.0, 20.0],
                    "volume": [1.0, 1.0],
                    "amount": [1.0, 1.0],
                }).with_columns(pl.col("date").cast(pl.Date)),
            ], how="diagonal_relaxed")
        return frame.select(columns) if columns else frame

    def get_minute_batch(
        self,
        symbols: list[str],
        trade_date: date,
        asset_type: str = "stock",
    ) -> pl.DataFrame:
        del asset_type
        if not self.with_minute or trade_date != date(2026, 11, 2):
            return pl.DataFrame()
        rows: list[dict] = []
        for minute in range(5):
            stamp = datetime(2026, 11, 2, 9, 31 + minute)
            rows.append({
                "symbol": SYMBOL_A,
                "datetime": stamp,
                "close": 10.0 + minute * 0.1,
                "volume": 100.0,
                "amount": 1000.0,
            })
            rows.append({
                "symbol": SYMBOL_B,
                "datetime": stamp,
                "close": 20.0 - minute * 0.1,
                "volume": 200.0,
                "amount": 2000.0,
            })
        return pl.DataFrame(rows).filter(pl.col("symbol").is_in(symbols))

    def list_minute_dates(
        self,
        start: date,
        end: date,
        asset_type: str = "stock",
    ) -> list[date]:
        del asset_type
        target = date(2026, 11, 2)
        return [target] if self.with_minute and start <= target <= end else []

    def list_trading_dates(
        self,
        start: date,
        end: date,
        asset_type: str = "stock",
    ) -> list[date]:
        del asset_type
        return [day for day in DATES if start <= day <= end]

    def latest_daily_date(self) -> date | None:
        return DATES[-1]

    def get_st_history(self) -> pl.DataFrame:
        return pl.DataFrame()

    def get_adj_factors(self, day: date) -> pl.DataFrame:
        del day
        return pl.DataFrame()

    def read_dataset_partition(
        self,
        dataset: str,
        day: date,
        columns: list[str] | None = None,
        *,
        file_name: str = "part.parquet",
    ) -> pl.DataFrame:
        del file_name
        if dataset == "kline_index_daily":
            frame = pl.DataFrame({
                "symbol": ["399107.SZ"],
                "date": [day],
                "close": [100.0 + DATES.index(day) * 0.1],
            })
            return frame.select(columns) if columns else frame
        if dataset == "ext_data/limit_board_events/timeseries":
            return pl.DataFrame(_event_rows(day))
        return pl.DataFrame()

    def dataset_partition_dates(self, dataset: str, start: date, end: date) -> list[date]:
        if dataset == "kline_index_daily":
            return [day for day in DATES if start <= day <= end]
        if dataset == "ext_data/limit_board_events/timeseries":
            dates = [DATES[20], DATES[21], DATES[36], DATES[38], DATES[39]]
            return [day for day in dates if start <= day <= end]
        return []

    def dataset_partition_signature(self, dataset: str, suffix: str) -> str:
        del dataset, suffix
        return ""


def _theme() -> dict:
    return {
        "id": "test",
        "name": "测试主题",
        "symbols": [SYMBOL_A, SYMBOL_B],
    }


def test_store_crud_and_symbol_deduplication(tmp_path: Path) -> None:
    created = store.create_theme(
        tmp_path,
        name="测试主题",
        description="说明",
        symbols=[SYMBOL_A, SYMBOL_A.lower(), "bad"],
    )
    assert created["symbols"] == [SYMBOL_A]
    assert store.get_theme(tmp_path, created["id"]) is not None

    added = store.add_symbols(tmp_path, created["id"], [SYMBOL_B, SYMBOL_A])
    assert added is not None
    assert added["symbols"] == [SYMBOL_A, SYMBOL_B]

    updated, removed = store.remove_symbol(tmp_path, created["id"], SYMBOL_A)
    assert removed is True
    assert updated is not None and updated["symbols"] == [SYMBOL_B]
    assert store.delete_theme(tmp_path, created["id"]) is True
    assert store.delete_theme(tmp_path, created["id"]) is False


def test_seed_theme_is_created_once(tmp_path: Path) -> None:
    data = FakeMarketData()
    first = store.seed_default_theme(tmp_path, data)
    assert first is not None
    assert first["id"] == "yang"
    assert first["symbols"] == [SYMBOL_A, SYMBOL_B]
    assert store.seed_default_theme(tmp_path, data) is None


def test_analysis_window_returns_and_activity(tmp_path: Path) -> None:
    del tmp_path
    service = ThemeAnalyzerService(FakeMarketData())
    result = service.analyze(_theme(), start=DATES[0], end=DATES[-1])
    leader = next(row for row in result["leaders"] if row["symbol"] == SYMBOL_A)

    assert leader["max_ret_3"] == pytest.approx(0.3)
    assert leader["max_ret_3_date"] == DATES[22].isoformat()
    assert leader["max_ret_10"] == pytest.approx(0.3)
    assert leader["max_ret_10_date"] == DATES[22].isoformat()
    assert leader["max_ret_30"] == pytest.approx(0.3)
    assert leader["max_ret_30_date"] == DATES[36].isoformat()
    assert leader["max_high_ret_30"] == pytest.approx(0.4)
    assert leader["latest_ret_3"] == pytest.approx(10.0 / 13.0 - 1.0)
    assert leader["active_gt2"] >= 2
    assert leader["max_deviate"] is not None and leader["max_deviate"] > 0.02
    assert result["active_count"] == 2
    assert result["seal"]["sealed_count"] == 1
    assert result["seal"]["broken_count"] == 1
    assert result["seal"]["seal_rate"] == pytest.approx(0.5)


def test_limit_route_marks_start_switch_and_relay() -> None:
    service = ThemeAnalyzerService(FakeMarketData())
    result = service.analyze(_theme(), start=DATES[0], end=DATES[-1])
    route = result["limit_route"]
    rows = {row["symbol"]: row for row in route["rows"]}

    assert [row["symbol"] for row in route["rows"]] == [SYMBOL_A, SYMBOL_B]
    assert rows[SYMBOL_A]["first_date"] == DATES[20].isoformat()
    assert rows[SYMBOL_A]["first_seal_date"] == DATES[20].isoformat()
    assert rows[SYMBOL_A]["first_time"] == "09:35"
    assert rows[SYMBOL_B]["first_date"] == DATES[20].isoformat()
    assert rows[SYMBOL_B]["first_seal_date"] == DATES[21].isoformat()
    assert rows[SYMBOL_B]["first_time"] == "09:20"

    leaders = {item["date"]: item for item in route["daily_leaders"]}
    assert leaders[DATES[20].isoformat()]["symbol"] == SYMBOL_A
    assert leaders[DATES[21].isoformat()]["symbol"] == SYMBOL_B
    assert leaders[DATES[39].isoformat()]["symbol"] == SYMBOL_A

    switch_by_date = {item["date"]: item for item in route["switch_days"]}
    assert "启动" in switch_by_date[DATES[20].isoformat()]["label"]
    assert SYMBOL_B in switch_by_date[DATES[21].isoformat()]["minute_symbols"]
    assert "领涨切换" in switch_by_date[DATES[38].isoformat()]["label"]
    assert route["space_leader_symbol"] == SYMBOL_A
    assert route["space_leader_peak_date"] == DATES[36].isoformat()
    assert "龙头涨幅峰值" in switch_by_date[DATES[36].isoformat()]["label"]
    assert switch_by_date[DATES[38].isoformat()]["minute_symbols"][:2] == [SYMBOL_B, SYMBOL_A]
    assert all(row["total_lu"] > 0 for row in route["rows"])

    catch_up = [
        (row["symbol"], event)
        for row in route["rows"]
        for event in row["events"]
        if event["catch_up"]
    ]
    assert catch_up == []
    relay = [
        (row["symbol"], event)
        for row in route["rows"]
        for event in row["events"]
        if event["relay"]
    ]
    assert len(relay) == 1
    assert relay[0][0] == SYMBOL_B
    assert relay[0][1]["date"] == DATES[38].isoformat()


def test_limit_route_marks_new_starter_after_peak_as_catch_up() -> None:
    service = ThemeAnalyzerService(FakeMarketData())
    leaders = [
        {
            "symbol": SYMBOL_A, "name": "甲股份", "active": True,
            "max_ret_30": 0.3, "max_ret_30_date": DATES[36].isoformat(),
        },
        {
            "symbol": SYMBOL_B, "name": "乙股份", "active": True,
            "max_ret_30": 0.05, "max_ret_30_date": DATES[38].isoformat(),
        },
    ]
    events = pl.DataFrame([
        {
            "trade_date": DATES[20].isoformat(),
            "symbol": SYMBOL_A,
            "name": "甲股份",
            "in_limit_up_pool": 1,
            "in_limit_break_pool": 0,
            "continue_day_cnt": 1,
            "limit_up_reason": "测试",
            "first_seal_time": "09:35",
            "last_seal_time": "09:35",
            "limit_up_pool_open_times": 0,
            "break_pool_open_times": 0,
            "seal_money": 1.0,
        },
        {
            "trade_date": DATES[38].isoformat(),
            "symbol": SYMBOL_B,
            "name": "乙股份",
            "in_limit_up_pool": 1,
            "in_limit_break_pool": 0,
            "continue_day_cnt": 1,
            "limit_up_reason": "补涨",
            "first_seal_time": "09:50",
            "last_seal_time": "09:50",
            "limit_up_pool_open_times": 0,
            "break_pool_open_times": 0,
            "seal_money": 1.0,
        },
    ])
    route = service._limit_route(
        events,
        leaders,
        {SYMBOL_A: "甲股份", SYMBOL_B: "乙股份"},
        DATES,
        [],
        DATES,
    )
    rows = {row["symbol"]: row for row in route["rows"]}
    event = rows[SYMBOL_B]["events"][0]
    assert event["catch_up"] is True
    assert event["relay"] is False
    switch_day = next(item for item in route["switch_days"] if item["date"] == DATES[38].isoformat())
    assert "补涨 +1" in switch_day["label"]
    assert switch_day["sealed"][0]["catch_up"] is True


def test_limit_route_handles_missing_events_and_broken_only() -> None:
    service = ThemeAnalyzerService(FakeMarketData())
    leaders = [{
        "symbol": SYMBOL_A,
        "name": "甲股份",
        "active": True,
        "max_ret_30": 0.3,
        "max_ret_30_date": DATES[36].isoformat(),
    }]
    broken = pl.DataFrame([{
        **_event_rows(DATES[20])[0],
        "in_limit_up_pool": 0,
        "in_limit_break_pool": 1,
    }])
    for events in (pl.DataFrame(), broken):
        route = service._limit_route(events, leaders, {}, DATES, [])
        assert route["rows"] == []
        assert route["switch_days"] == []
        assert route["daily_leaders"] == []


def test_limit_route_keeps_broken_only_stocks_in_switch_day_comparisons() -> None:
    service = ThemeAnalyzerService(FakeMarketData())
    leaders = [{
        "symbol": SYMBOL_A, "name": "甲股份", "active": True,
        "max_ret_30": 0.3, "max_ret_30_date": DATES[36].isoformat(),
    }]
    route = service._limit_route(
        pl.DataFrame(_event_rows(DATES[20])),
        leaders,
        {SYMBOL_A: "甲股份", SYMBOL_B: "乙股份"},
        DATES,
        [DATES[20]],
    )
    assert [row["symbol"] for row in route["rows"]] == [SYMBOL_A]
    switch_day = route["switch_days"][0]
    assert switch_day["has_minute"] is True
    assert switch_day["broken"][0]["symbol"] == SYMBOL_B
    assert SYMBOL_B in switch_day["minute_symbols"]


def test_limit_route_recomputes_consecutive_boards_on_trading_days() -> None:
    service = ThemeAnalyzerService(FakeMarketData())
    leaders = [{
        "symbol": SYMBOL_A, "name": "甲股份", "active": True,
        "max_ret_30": 0.3, "max_ret_30_date": DATES[36].isoformat(),
    }]
    rows = []
    for day, cont in ((DATES[20], 1), (DATES[21], 2), (DATES[22], 1), (DATES[24], 1)):
        rows.append({
            "trade_date": day.isoformat(),
            "symbol": SYMBOL_A,
            "name": "甲股份",
            "in_limit_up_pool": 1,
            "in_limit_break_pool": 0,
            "continue_day_cnt": cont,
            "limit_up_reason": "测试",
            "first_seal_time": "09:30",
            "last_seal_time": "09:30",
            "limit_up_pool_open_times": 0,
            "break_pool_open_times": 0,
            "seal_money": 1.0,
        })
    route = service._limit_route(
        pl.DataFrame(rows), leaders, {SYMBOL_A: "甲股份"}, DATES, [], DATES,
    )
    events = route["rows"][0]["events"]
    assert [event["consec"] for event in events] == [1, 2, 3, 1]
    assert route["event_count"] == 4
    assert route["seal_count"] == 4


def test_empty_analysis_keeps_limit_route_contract() -> None:
    service = ThemeAnalyzerService(FakeMarketData())
    result = service.analyze({**_theme(), "symbols": []}, start=DATES[0], end=DATES[-1])
    assert result["limit_route"]["rows"] == []
    assert result["limit_route"]["switch_days"] == []
    assert result["minute_dates"] == []


def test_analysis_api_serializes_route_and_empty_theme(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_extension_runtime] = lambda: SimpleNamespace(
        data_dir=tmp_path, market_data=FakeMarketData(),
    )
    client = TestClient(app)
    theme = store.create_theme(tmp_path, name="主题", symbols=[SYMBOL_A, SYMBOL_B])
    response = client.get(
        f"/api/custom/theme-analyzer/themes/{theme['id']}/analysis",
        params={"start": DATES[0].isoformat(), "end": DATES[-1].isoformat()},
    )
    assert response.status_code == 200
    assert response.json()["limit_route"]["space_leader_symbol"] == SYMBOL_A
    assert response.json()["limit_route"]["switch_days"]
    empty_theme = store.create_theme(tmp_path, name="空主题", symbols=[])
    empty = client.get(f"/api/custom/theme-analyzer/themes/{empty_theme['id']}/analysis")
    assert empty.status_code == 200
    assert empty.json()["limit_route"]["rows"] == []


def test_minute_overlay_aligns_table_and_features() -> None:
    service = ThemeAnalyzerService(FakeMarketData())
    result = service.minute_overlay(
        _theme(),
        date(2026, 11, 2),
        [SYMBOL_A, SYMBOL_B],
    )
    assert result["status"] == "ok"
    assert result["times"] == ["09:31", "09:32", "09:33", "09:34", "09:35"]
    assert result["table"]["times"] == ["09:31", "09:35"]
    assert result["table"]["series"][SYMBOL_A][-1] == pytest.approx(4.0)
    assert result["features"][SYMBOL_A]["day"] == pytest.approx(4.0)
    assert result["features"][SYMBOL_A]["up_ratio"] == pytest.approx(100.0)
    assert result["missing"] == []


def test_minute_overlay_no_data() -> None:
    service = ThemeAnalyzerService(FakeMarketData(with_minute=False))
    result = service.minute_overlay(_theme(), date(2026, 11, 2), [SYMBOL_A])
    assert result["status"] == "no_data"
    assert result["missing"] == [SYMBOL_A]


def test_api_rejects_bad_symbol_and_missing_theme(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(router)
    runtime = SimpleNamespace(data_dir=tmp_path, market_data=FakeMarketData())
    app.dependency_overrides[get_extension_runtime] = lambda: runtime
    client = TestClient(app)

    response = client.post(
        "/api/custom/theme-analyzer/themes",
        json={"name": "测试", "symbols": ["bad-code"]},
    )
    assert response.status_code == 400

    missing = client.get("/api/custom/theme-analyzer/themes/not-found/analysis")
    assert missing.status_code == 404


def _linked_graph(tmp_path: Path) -> None:
    from app.custom.industry_chain.models import IndustryChainGraph
    from app.custom.industry_chain.store import save_graph

    save_graph(tmp_path, IndustryChainGraph.model_validate({
        "categories": [{"id": "cat", "name": "测试分类"}],
        "chains": [{"id": "chain", "category_id": "cat", "name": "测试产业链"}],
        "nodes": [
            {"id": "root", "chain_id": "chain", "name": "上游"},
            {"id": "child", "chain_id": "chain", "name": "子环节", "parent_id": "root"},
            {"id": "other", "chain_id": "chain", "name": "下游"},
        ],
        "stock_links": [
            {"id": "link-a", "node_id": "child", "symbol": SYMBOL_A, "reason_short": "测试上游关联股"},
            {"id": "link-b", "node_id": "other", "symbol": SYMBOL_B, "reason_short": "测试下游关联股"},
            {"id": "link-c", "node_id": "other", "symbol": SYMBOL_A, "reason_short": "测试重复关联股"},
        ],
    }))


def test_industry_source_dynamic_scope_manual_and_exclusions(tmp_path: Path) -> None:
    from app.custom.industry_chain.models import IndustryChainGraph
    from app.custom.industry_chain.store import load_graph, save_graph
    from app.custom.theme_analyzer.linking import resolve_theme

    _linked_graph(tmp_path)
    theme = store.create_theme(
        tmp_path, name="关联主题", symbols=[SYMBOL_B],
        industry_source={"chain_id": "chain", "node_ids": ["root"]},
    )
    resolved = resolve_theme(tmp_path, theme, strict=True)
    assert resolved["symbols"] == [SYMBOL_A, SYMBOL_B]
    assert resolved["inherited_symbols"] == [SYMBOL_A]
    assert resolved["stock_segments"][SYMBOL_A] == ["子环节"]
    assert store.get_theme(tmp_path, theme["id"])["symbols"] == [SYMBOL_B]

    theme, removed = store.remove_symbol(tmp_path, theme["id"], SYMBOL_A, inherited=True)
    assert removed
    assert resolve_theme(tmp_path, theme)["symbols"] == [SYMBOL_B]
    theme = store.add_symbols(tmp_path, theme["id"], [SYMBOL_A])
    assert theme["excluded_symbols"] == []

    graph = load_graph(tmp_path)
    graph = {**graph, "stock_links": [
        link for link in graph["stock_links"] if link["id"] != "link-a"
    ]}
    save_graph(tmp_path, IndustryChainGraph.model_validate(graph))
    theme = store.update_theme(tmp_path, theme["id"], symbols=[])
    assert resolve_theme(tmp_path, theme)["symbols"] == []
    theme = store.update_theme(tmp_path, theme["id"], industry_source={"chain_id": "chain", "node_ids": []})
    assert resolve_theme(tmp_path, theme)["symbols"] == [SYMBOL_A, SYMBOL_B]
    theme = store.update_theme(tmp_path, theme["id"], industry_source={})
    assert resolve_theme(tmp_path, theme)["symbols"] == []


def test_industry_source_api_and_missing_source_fail_closed(tmp_path: Path) -> None:
    from app.custom.industry_chain.models import IndustryChainGraph
    from app.custom.industry_chain.store import load_graph, save_graph

    _linked_graph(tmp_path)
    app = FastAPI()
    app.include_router(router)
    runtime = SimpleNamespace(data_dir=tmp_path, market_data=FakeMarketData())
    app.dependency_overrides[get_extension_runtime] = lambda: runtime
    client = TestClient(app)
    prefix = "/api/custom/theme-analyzer/themes"
    invalid = client.post(prefix, json={
        "name": "错误来源", "industry_source": {"chain_id": "missing"},
    })
    assert invalid.status_code == 400
    invalid_node = client.post(prefix, json={
        "name": "错误环节", "industry_source": {"chain_id": "chain", "node_ids": ["missing"]},
    })
    assert invalid_node.status_code == 400
    created = client.post(prefix, json={
        "name": "链主题", "industry_source": {"chain_id": "chain", "node_ids": ["root"]},
    })
    assert created.status_code == 200
    theme = created.json()
    assert theme["symbols"] == [SYMBOL_A]
    assert theme["manual_symbols"] == []
    url = f"{prefix}/{theme['id']}"
    assert client.get(f"{url}/analysis").json()["pool_count"] == 1
    minute = client.get(f"{url}/minute", params={"date": "2026-11-02", "symbols": SYMBOL_A})
    assert minute.status_code == 200
    assert minute.json()["missing"] == []
    excluded = client.delete(f"{url}/stocks/{SYMBOL_A}")
    assert excluded.json()["symbols"] == []
    assert excluded.json()["excluded_symbols"] == [SYMBOL_A]
    restored = client.post(f"{url}/stocks", json={"symbols": [SYMBOL_A]})
    assert restored.json()["symbols"] == [SYMBOL_A]
    assert restored.json()["excluded_symbols"] == []
    assert restored.json()["manual_symbols"] == []
    client.post(f"{url}/stocks", json={"symbols": [SYMBOL_B]})
    assert client.put(url, json={"name": "改名"}).json()["industry_source"]["chain_id"] == "chain"

    graph = load_graph(tmp_path)
    save_graph(tmp_path, IndustryChainGraph.model_validate({
        **graph, "stock_links": [], "nodes": [], "chains": [],
    }))
    listed = client.get(prefix)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["source_error"]
    assert client.get(f"{url}/analysis").status_code == 400
    assert client.get(f"{url}/minute", params={"date": "2026-11-02"}).status_code == 400
    detached = client.put(url, json={"industry_source": None})
    assert detached.status_code == 200
    assert detached.json()["industry_source"] is None
    assert detached.json()["symbols"] == [SYMBOL_B]

