"""策略回测结果保存/历史/打开/删除的存储与 API 测试。"""
from __future__ import annotations

import json
import threading
import time
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.backtest import StrategyBacktestRequest, router
from app.backtest import result_store as store
from app.backtest.engine import BacktestEngine, MatcherConfig
from app.backtest.strategy import (
    PreparedMatrixBacktest,
    StrategyBacktestConfig,
    StrategyBacktestService,
)
from app.config import settings
from app.strategy.engine import StrategyEngine

STRATEGY_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "custom"
    / "first_board_event_chain"
    / "first_limit_pullback_3f_runner_t74.py"
)


def _result(run_id: str, *, error: str | None = None) -> dict:
    return {
        "run_id": run_id,
        "error": error,
        "config": {
            "strategy_id": "first_limit_pullback_3f_runner_t74",
            "start": "2025-01-02",
            "end": "2025-02-01",
            "mode": "position",
            "asset_type": "stock",
        },
        "stats": {
            "total_return": 0.331,
            "annual_return": 0.5,
            "max_drawdown": -0.1,
            "sharpe": 1.2,
            "win_rate": 0.55,
            "n_trades": 0,
        },
        "equity_curve": [{"date": "2025-01-02", "value": 100000.0}],
        "drawdown_curve": [{"date": "2025-01-02", "value": 0.0}],
        "benchmark_curve": [],
        "trades": [],
        "per_symbol_stats": [],
        "strategy_info": {
            "id": "first_limit_pullback_3f_runner_t74",
            "name": "首板3F回踩 · T74 Runner",
        },
        "provenance": {"algorithm_version": "strategy_backtest_v1"},
    }


@pytest.fixture(autouse=True)
def _clean_cache():
    store.clear_completed_runs()
    yield
    store.clear_completed_runs()


def test_completed_run_cache_expires_and_is_bounded() -> None:
    cache = store.CompletedRunCache(ttl_seconds=0.01, max_entries=2)
    assert cache.register(_result("r1")) == "r1"
    time.sleep(0.02)
    assert cache.get("r1") is None
    cache.register(_result("r2"))
    cache.register(_result("r3"))
    cache.register(_result("r4"))
    assert cache.get("r2") is None
    assert cache.get("r3") is not None
    assert cache.get("r4") is not None


def test_cache_byte_budget_is_hard_cap() -> None:
    cache = store.CompletedRunCache(
        ttl_seconds=60.0, max_entries=32, max_bytes=1000,
    )
    big = lambda run_id, pad: {"run_id": run_id, "pad": "x" * pad}  # noqa: E731
    assert cache.register(big("b1", 600)) == "b1"
    assert cache.register(big("b2", 600)) == "b2"
    # 条数远未到上限, 但累计字节超预算: 淘汰最旧的 b1, 累计始终 <= 1000。
    assert cache.get("b1") is None
    assert cache.get("b2") is not None
    assert cache._total_bytes <= 1000
    # 单条超过可保存上限: 不登记, 也不驱逐已有可用缓存。
    assert cache.register({"run_id": "b3", "pad": "x" * 5000}) is None
    assert cache.get("b3") is None
    assert cache.rejection_reason("b3") == store.RUN_REJECT_TOO_LARGE
    assert cache.get("b2") is not None
    cache.clear()
    assert cache.get("b2") is None
    assert cache.rejection_reason("b3") is None


def test_cache_rejects_unserializable_without_evicting() -> None:
    class _BadStr:
        def __str__(self) -> str:
            raise TypeError("cannot serialize")

    cache = store.CompletedRunCache(ttl_seconds=60.0)
    assert cache.register({"run_id": "keep", "pad": "ok"}) == "keep"
    assert cache.register({"run_id": "bad", "value": _BadStr()}) is None
    assert cache.get("bad") is None
    assert cache.rejection_reason("bad") == store.RUN_REJECT_UNSERIALIZABLE
    # 拒绝不驱逐已有有效缓存。
    assert cache.get("keep") is not None


def test_save_reports_too_large_and_unserializable_distinctly(
    tmp_path: Path,
) -> None:
    class _BadStr:
        def __str__(self) -> str:
            raise TypeError("cannot serialize")

    store.register_completed_run({"run_id": "big", "pad": "x" * (70 * 1024 * 1024)})
    with pytest.raises(store.SavedResultLimitExceededError) as too_large:
        store.save_completed_result(tmp_path, run_id="big")
    assert "过大" in str(too_large.value)

    store.register_completed_run({"run_id": "bad", "value": _BadStr()})
    with pytest.raises(store.RunResultNotSavableError) as not_savable:
        store.save_completed_result(tmp_path, run_id="bad")
    assert "无法序列化" in str(not_savable.value)

    # 未登记过任何东西仍是“过期”语义, 不误报为过大。
    with pytest.raises(store.RunResultExpiredError):
        store.save_completed_result(tmp_path, run_id="never")


def test_cache_skips_error_and_missing_run_id() -> None:
    cache = store.CompletedRunCache()
    assert cache.register(_result("bad", error="cancelled")) is None
    assert cache.register({"config": {}}) is None
    assert cache.register("not-a-dict") is None  # type: ignore[arg-type]


def test_save_requires_completed_run(tmp_path: Path) -> None:
    with pytest.raises(store.RunResultExpiredError):
        store.save_completed_result(tmp_path, run_id="missing")
    store.register_completed_run(_result("expired", error="回测已取消"))
    with pytest.raises(store.RunResultExpiredError):
        store.save_completed_result(tmp_path, run_id="expired")


def test_save_list_open_delete_and_idempotent(tmp_path: Path) -> None:
    store.register_completed_run(_result("run-1"))
    summary = store.save_completed_result(tmp_path, run_id="run-1", name="  331 首板  ")
    assert summary["saved_id"]
    assert summary["name"] == "331 首板"
    assert summary["total_return"] == 0.331
    assert summary["n_trades"] == 0
    assert summary["strategy_name"] == "首板3F回踩 · T74 Runner"

    again = store.save_completed_result(tmp_path, run_id="run-1", name="改名无效")
    assert again["saved_id"] == summary["saved_id"]
    assert again["name"] == "331 首板"

    store.register_completed_run(_result("run-2"))
    second = store.save_completed_result(tmp_path, run_id="run-2")
    assert second["saved_id"] != summary["saved_id"]

    listing = store.list_saved_results(tmp_path, page=1, page_size=1)
    assert listing["total"] == 2
    assert listing["has_more"] is True
    assert len(listing["items"]) == 1
    assert listing["skipped"] == 0

    record = store.get_saved_result(tmp_path, summary["saved_id"])
    assert record["schema_version"] == store.SCHEMA_VERSION
    assert record["run_id"] == "run-1"
    assert record["result"]["stats"]["total_return"] == 0.331
    assert record["provenance"]["algorithm_version"] == "strategy_backtest_v1"

    store.delete_saved_result(tmp_path, summary["saved_id"])
    with pytest.raises(store.SavedResultNotFoundError):
        store.get_saved_result(tmp_path, summary["saved_id"])
    # 另一条记录不受影响
    assert store.list_saved_results(tmp_path)["total"] == 1


def test_concurrent_save_same_run_creates_single_record(tmp_path: Path) -> None:
    store.register_completed_run(_result("dup-run"))
    results: list[dict] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def _save() -> None:
        barrier.wait()
        try:
            results.append(store.save_completed_result(tmp_path, run_id="dup-run"))
        except BaseException as exc:  # noqa: BLE001 - 测试内收集所有异常
            errors.append(exc)

    threads = [threading.Thread(target=_save) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len({item["saved_id"] for item in results}) == 1
    assert len(list(store.results_dir(tmp_path).glob("*.json"))) == 1
    assert store.list_saved_results(tmp_path)["total"] == 1


def test_concurrent_save_respects_total_limit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(store, "MAX_SAVED_RECORDS", 2)
    run_ids = [f"limit-{index}" for index in range(4)]
    for run_id in run_ids:
        store.register_completed_run(_result(run_id))
    saved: list[dict] = []
    limited: list[BaseException] = []
    barrier = threading.Barrier(len(run_ids))

    def _save(run_id: str) -> None:
        barrier.wait()
        try:
            saved.append(store.save_completed_result(tmp_path, run_id=run_id))
        except BaseException as exc:  # noqa: BLE001 - 测试内收集所有异常
            limited.append(exc)

    threads = [
        threading.Thread(target=_save, args=(run_id,)) for run_id in run_ids
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(saved) == 2
    assert len(limited) == 2
    assert all(isinstance(exc, store.SavedResultLimitExceededError) for exc in limited)
    assert len(list(store.results_dir(tmp_path).glob("*.json"))) == 2


def test_completed_at_is_registration_time_not_save_time(
    tmp_path: Path, monkeypatch,
) -> None:
    store.register_completed_run(_result("stamped"))
    completed = store.get_completed_run("stamped")["completed_at"]
    assert completed
    monkeypatch.setattr(store, "_now_iso", lambda: "2030-01-01T00:00:00+00:00")
    summary = store.save_completed_result(tmp_path, run_id="stamped")
    assert summary["completed_at"] == completed
    assert summary["saved_at"] == "2030-01-01T00:00:00+00:00"
    record = store.get_saved_result(tmp_path, summary["saved_id"])
    assert record["completed_at"] == completed
    assert record["result"]["completed_at"] == completed


def test_corrupt_and_unknown_schema_are_isolated(tmp_path: Path) -> None:
    store.register_completed_run(_result("good"))
    summary = store.save_completed_result(tmp_path, run_id="good")
    directory = store.results_dir(tmp_path)

    (directory / "0123456789abcdef.json").write_text("not json", encoding="utf-8")
    unknown = {
        "schema_version": 99,
        "saved_id": "fedcba9876543210",
        "run_id": "future",
        "result": {},
    }
    (directory / "fedcba9876543210.json").write_text(
        json.dumps(unknown), encoding="utf-8",
    )

    listing = store.list_saved_results(tmp_path)
    assert listing["total"] == 1
    assert listing["items"][0]["saved_id"] == summary["saved_id"]
    assert listing["skipped"] == 2

    with pytest.raises(store.SavedResultCorruptError):
        store.get_saved_result(tmp_path, "0123456789abcdef")
    with pytest.raises(store.UnsupportedResultSchemaError):
        store.get_saved_result(tmp_path, "fedcba9876543210")


def test_invalid_saved_id_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(store.InvalidSavedIdError):
        store.get_saved_result(tmp_path, "../strategy")
    with pytest.raises(store.InvalidSavedIdError):
        store.delete_saved_result(tmp_path, "not-a-valid-id")


def test_record_limit_exceeded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(store, "MAX_SAVED_RECORDS", 1)
    store.register_completed_run(_result("run-1"))
    store.save_completed_result(tmp_path, run_id="run-1")
    store.register_completed_run(_result("run-2"))
    with pytest.raises(store.SavedResultLimitExceededError):
        store.save_completed_result(tmp_path, run_id="run-2")


def test_atomic_write_failure_leaves_nothing(tmp_path: Path, monkeypatch) -> None:
    def _boom(src, dst):
        raise OSError("disk full")

    # 落盘走硬链接 create-if-absent; 任何一步失败都不能留下半成品或临时文件。
    monkeypatch.setattr(store.os, "link", _boom)
    store.register_completed_run(_result("run-1"))
    with pytest.raises(OSError):
        store.save_completed_result(tmp_path, run_id="run-1")
    assert store.list_saved_results(tmp_path)["total"] == 0
    leftover = list(store.results_dir(tmp_path).glob(".tmp-result-*"))
    assert leftover == []


def test_provenance_snapshot_and_config_asset_type() -> None:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    service = StrategyBacktestService(
        BacktestEngine(repo=None), StrategyEngine(strategy_dirs=[]),  # type: ignore[arg-type]
    )
    config = StrategyBacktestConfig(
        strategy_id=strategy.meta["id"],
        symbols=None,
        start=date(2025, 1, 2),
        end=date(2025, 2, 1),
        mode="position",
    )
    matcher = MatcherConfig(
        matching="open_t+1",
        position_sizing="score_tier",
        score_tiers=((0.0, 0.0), (0.55, 0.2)),
        plan_at_signal_close=True,
        exit_signal_requires_profit=True,
        max_daily_entries=2,
        entry_price_basis="raw",
        block_limit_open=True,
    )
    provenance = service._build_run_provenance(
        strategy, config, {}, matcher, {},
    )
    assert provenance["strategy"]["id"] == strategy.meta["id"]
    assert len(provenance["strategy"]["definition_sha256"]) == 64
    assert provenance["execution"]["position_sizing"] == "score_tier"
    assert provenance["execution"]["plan_at_signal_close"] is True
    assert provenance["execution"]["exit_signal_requires_profit"] is True
    assert provenance["execution"]["entry_price_basis"] == "raw"
    assert provenance["execution"]["entry_fill"] == "open_t+1"
    assert provenance["execution"]["exit_fill"] == "open_t+1"
    assert provenance["data"]["frozen"] is False
    assert provenance["data"]["generation"] is None
    assert "file_path" not in json.dumps(provenance)
    dumped = StrategyBacktestService._config_to_dict(config)
    assert dumped["asset_type"] == "stock"


def _provenance_with_repo(
    repo,
    *,
    matcher: MatcherConfig | None = None,
    data_generation: str | None = None,
    generation_source: str | None = None,
) -> dict:
    strategy = StrategyEngine._load_file(STRATEGY_PATH)
    service = StrategyBacktestService(
        BacktestEngine(repo=repo), StrategyEngine(strategy_dirs=[]),  # type: ignore[arg-type]
    )
    config = StrategyBacktestConfig(
        strategy_id=strategy.meta["id"],
        symbols=None,
        start=date(2025, 1, 2),
        end=date(2025, 2, 1),
        mode="position",
    )
    return service._build_run_provenance(
        strategy, config, {}, matcher or MatcherConfig(), {},
        data_generation=data_generation,
        generation_source=generation_source,
    )


class _FakeRepo:
    def __init__(self, generation) -> None:
        self._generation = generation
        self.calls: list[str] = []

    def get_matrix_data_generation(self, asset_type: str = "stock") -> str:
        self.calls.append(asset_type)
        if isinstance(self._generation, BaseException):
            raise self._generation
        return self._generation


class _FakeEngineForGeneration:
    """只实现 generation 采集接口, 用于验证绑定/失败语义。"""

    def __init__(self, value) -> None:
        self._value = value
        self.calls: list[str] = []

    def data_generation(self, asset_type: str = "stock"):
        self.calls.append(asset_type)
        if isinstance(self._value, BaseException):
            raise self._value
        return self._value


def _service_with_engine(engine) -> StrategyBacktestService:
    return StrategyBacktestService(
        engine, StrategyEngine(strategy_dirs=[]),  # type: ignore[arg-type]
    )


def test_provenance_uses_bound_generation_and_never_rereads() -> None:
    # 传进来的必须是装载窗口内绑定好的版本; provenance 不得再读 engine 的新版本。
    repo = _FakeRepo("gen-B-newer")
    provenance = _provenance_with_repo(
        repo,
        matcher=MatcherConfig(
            stop_loss_pct=-0.06,
            take_profit_pct=0.2,
            trailing_stop_pct=0.05,
            trailing_take_profit_activate_pct=0.1,
            trailing_take_profit_drawdown_pct=0.03,
            max_hold_days=74,
        ),
        data_generation="gen-A-loaded",
        generation_source="matrix",
    )
    assert repo.calls == []  # 组装 provenance 时绝不重读 generation
    assert provenance["data"]["generation"] == "gen-A-loaded"
    assert provenance["data"]["generation_source"] == "matrix"
    execution = provenance["execution"]
    assert execution["stop_loss_pct"] == -0.06
    assert execution["take_profit_pct"] == 0.2
    assert execution["trailing_stop_pct"] == 0.05
    assert execution["trailing_take_profit_activate_pct"] == 0.1
    assert execution["trailing_take_profit_drawdown_pct"] == 0.03
    assert execution["max_hold_days"] == 74


def test_provenance_generation_is_null_when_not_bound() -> None:
    provenance = _provenance_with_repo(_FakeRepo("gen-B"))
    assert provenance["data"]["generation"] is None
    assert provenance["data"]["generation_source"] is None
    assert provenance["data"]["frozen"] is False


def test_resolve_bound_generation_requires_stable_versions() -> None:
    resolve = StrategyBacktestService._resolve_bound_generation
    assert resolve("A", "A") == "A"
    assert resolve("A", "B") is None   # 装载后环境变 B: 无法证明读到的是 A
    assert resolve(None, "B") is None  # 装载前拿不到: 无法证明
    assert resolve("A", None) is None
    assert resolve(None, None) is None


def test_capture_generation_handles_success_and_failure() -> None:
    ok = _service_with_engine(_FakeEngineForGeneration("gen-1"))
    assert ok._capture_generation("stock", None) == "gen-1"
    assert ok.engine.calls == ["stock"]

    broken = _service_with_engine(_FakeEngineForGeneration(RuntimeError("io")))
    assert broken._capture_generation("stock", None) is None

    no_api = _service_with_engine(object())
    assert no_api._capture_generation("stock", None) is None


def test_prepared_matrix_binds_its_own_generation_not_current() -> None:
    # prepared 是较早准备的数据: 记录/使用它自己的版本 A, 即使当前环境已是 B。
    prepared = PreparedMatrixBacktest(
        signature=(),
        market_data=None,  # type: ignore[arg-type]
        feature_width=0,
        load_start=date(2025, 1, 2),
        load_end=date(2025, 2, 1),
        sim_end=date(2025, 2, 1),
        entry_time_mask=None,  # type: ignore[arg-type]
        exit_time_mask=None,  # type: ignore[arg-type]
        start_id=0,
        stop_id=0,
        reference_price=None,
        prepare_timing_ms={},
        compute_cache=None,  # type: ignore[arg-type]
        source_generation="gen-A-prepared",
    )
    provenance = _provenance_with_repo(
        _FakeRepo("gen-B-current"),
        data_generation=prepared.source_generation,
        generation_source="matrix",
    )
    assert provenance["data"]["generation"] == "gen-A-prepared"
    assert provenance["data"]["generation_source"] == "matrix"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_api_registers_completed_result_for_later_save(client: TestClient) -> None:
    from app.api.backtest import _register_completed_strategy_result

    _register_completed_strategy_result(_result("run-x"))
    assert store.get_completed_run("run-x") is not None
    _register_completed_strategy_result(_result("failed", error="cancelled"))
    assert store.get_completed_run("failed") is None


def test_api_save_list_open_delete(client: TestClient) -> None:
    store.register_completed_run(_result("run-1"))

    saved = client.post(
        "/api/backtest/strategy/results",
        json={"run_id": "run-1", "name": "331 回测"},
    )
    assert saved.status_code == 200, saved.text
    saved_body = saved.json()
    assert saved_body["saved_id"]
    assert saved_body["total_return"] == 0.331

    listing = client.get("/api/backtest/strategy/results", params={"page": 1, "page_size": 20})
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["saved_id"] == saved_body["saved_id"]

    opened = client.get(f"/api/backtest/strategy/results/{saved_body['saved_id']}")
    assert opened.status_code == 200
    payload = opened.json()
    assert payload["schema_version"] == 1
    assert payload["run_id"] == "run-1"
    assert payload["result"]["stats"]["total_return"] == 0.331

    deleted = client.delete(f"/api/backtest/strategy/results/{saved_body['saved_id']}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    assert client.get(
        f"/api/backtest/strategy/results/{saved_body['saved_id']}"
    ).status_code == 404


def test_api_save_expired_and_invalid_id(client: TestClient) -> None:
    expired = client.post(
        "/api/backtest/strategy/results", json={"run_id": "never-ran"},
    )
    assert expired.status_code == 410
    assert "已过期或未完成" in expired.json()["detail"]
    assert client.get("/api/backtest/strategy/results/bad-id").status_code == 400


def test_api_save_reports_too_large_and_unserializable_as_409(
    client: TestClient, monkeypatch,
) -> None:
    class _BadStr:
        def __str__(self) -> str:
            raise TypeError("cannot serialize")

    # 用小预算缓存模拟超单条拒绝, 不影响真实常量。
    monkeypatch.setattr(
        store, "_CACHE", store.CompletedRunCache(ttl_seconds=60.0, max_entry_bytes=1000),
    )
    store.register_completed_run({"run_id": "big", "pad": "x" * 5000})
    too_large = client.post(
        "/api/backtest/strategy/results", json={"run_id": "big"},
    )
    assert too_large.status_code == 409
    assert "过大" in too_large.json()["detail"]

    store.register_completed_run({"run_id": "bad", "value": _BadStr()})
    bad = client.post("/api/backtest/strategy/results", json={"run_id": "bad"})
    assert bad.status_code == 409
    assert "无法序列化" in bad.json()["detail"]


def test_api_open_snapshot_does_not_run_backtest(
    client: TestClient, monkeypatch,
) -> None:
    store.register_completed_run(_result("run-1"))
    saved_id = client.post(
        "/api/backtest/strategy/results", json={"run_id": "run-1"},
    ).json()["saved_id"]

    def _fail(*args, **kwargs):
        raise AssertionError("打开历史结果不得触发回测")

    monkeypatch.setattr(StrategyBacktestService, "run", _fail)
    opened = client.get(f"/api/backtest/strategy/results/{saved_id}")
    assert opened.status_code == 200


# ── 成交口径默认与请求解析 (架构增量契约) ──────────────────────────

def _install_fake_worker(monkeypatch, result: dict) -> dict:
    captured: dict = {}

    def _make(kind, data_dir, config):
        captured["config"] = config
        return {"kind": kind, "config": {}}

    monkeypatch.setattr("app.backtest.worker.make_worker_task", _make)
    monkeypatch.setattr("app.backtest.worker.run_worker_task", lambda *a, **k: result)
    return captured


def test_backtest_config_resolves_fill_defaults() -> None:
    base = dict(
        strategy_id="x",
        symbols=None,
        start=date(2025, 1, 2),
        end=date(2025, 2, 1),
    )
    omitted = StrategyBacktestConfig(**base)
    assert omitted.matching == "open_t+1"
    assert omitted.entry_fill == "open_t+1"
    assert omitted.exit_fill == "open_t+1"
    assert StrategyBacktestService._config_to_dict(omitted)["entry_fill"] == "open_t+1"

    legacy = StrategyBacktestConfig(**base, matching="close_t")
    assert legacy.entry_fill == "close_t"
    assert legacy.exit_fill == "close_t"

    explicit = StrategyBacktestConfig(**base, entry_fill="close_t")
    assert explicit.entry_fill == "close_t"
    assert explicit.exit_fill == "open_t+1"
    dumped = StrategyBacktestService._config_to_dict(explicit)
    assert dumped["entry_fill"] == "close_t"
    assert dumped["exit_fill"] == "open_t+1"


def test_request_model_defaults_are_next_open() -> None:
    req = StrategyBacktestRequest(strategy_id="x")
    assert req.matching == "open_t+1"
    assert req.entry_fill is None
    assert req.exit_fill is None


def test_plan_at_signal_close_rejects_close_entry_fill() -> None:
    with pytest.raises(ValueError, match="next-open"):
        MatcherConfig(entry_fill="close_t", plan_at_signal_close=True)


def test_post_omitted_fills_default_next_open_and_register(client, monkeypatch) -> None:
    captured = _install_fake_worker(monkeypatch, _result("post-run"))
    response = client.post(
        "/api/backtest/strategy/run",
        json={
            "strategy_id": "first_limit_pullback_3f_runner_t74",
            "start": "2025-01-02",
            "end": "2025-02-01",
        },
    )
    assert response.status_code == 200, response.text
    config = captured["config"]
    assert config.entry_fill == "open_t+1"
    assert config.exit_fill == "open_t+1"
    assert store.get_completed_run("post-run") is not None
    saved = client.post(
        "/api/backtest/strategy/results", json={"run_id": "post-run"},
    )
    assert saved.status_code == 200


def test_post_legacy_matching_and_explicit_single_fill(client, monkeypatch) -> None:
    captured = _install_fake_worker(monkeypatch, _result("post-legacy"))
    response = client.post(
        "/api/backtest/strategy/run",
        json={
            "strategy_id": "x",
            "start": "2025-01-02",
            "end": "2025-02-01",
            "matching": "close_t",
        },
    )
    assert response.status_code == 200
    assert captured["config"].entry_fill == "close_t"
    assert captured["config"].exit_fill == "close_t"

    captured = _install_fake_worker(monkeypatch, _result("post-explicit"))
    response = client.post(
        "/api/backtest/strategy/run",
        json={
            "strategy_id": "x",
            "start": "2025-01-02",
            "end": "2025-02-01",
            "entry_fill": "close_t",
        },
    )
    assert response.status_code == 200
    assert captured["config"].entry_fill == "close_t"
    assert captured["config"].exit_fill == "open_t+1"


def test_sse_omitted_fills_default_next_open_and_register(client, monkeypatch) -> None:
    captured = _install_fake_worker(monkeypatch, _result("sse-run"))
    response = client.get(
        "/api/backtest/strategy/stream",
        params={
            "strategy_id": "first_limit_pullback_3f_runner_t74",
            "start": "2025-01-02",
            "end": "2025-02-01",
        },
    )
    assert response.status_code == 200, response.text
    assert "event: done" in response.text
    config = captured["config"]
    assert config.entry_fill == "open_t+1"
    assert config.exit_fill == "open_t+1"
    assert store.get_completed_run("sse-run") is not None
