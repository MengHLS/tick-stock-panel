from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from statistics import mean, stdev

import polars as pl
import pytest

from app.factors import ext_factors
from app.factors.registry import get_factor
from app.factors.store import load_into_registry, save_one
from app.services.ext_data import ExtConfig, ExtConfigStore, ExtField, _load_all_cache

PREOPEN_CONFIG = "auction_preopen"
RESULT_CONFIG = "auction_result"
SYMBOLS = ("000001.SZ", "000002.SZ", "600000.SH")


def _ext_configs(data_dir: Path) -> None:
    store = ExtConfigStore(data_dir)
    store.upsert(ExtConfig(
        id=PREOPEN_CONFIG,
        label="早盘竞价过程",
        mode="timeseries",
        fields=[
            ExtField("last_imbalance", "float"),
            ExtField("last_minute_matched_growth", "float"),
            ExtField("post0920_matched_growth", "float"),
        ],
    ))
    store.upsert(ExtConfig(
        id=RESULT_CONFIG,
        label="早盘竞价结果",
        mode="timeseries",
        fields=[ExtField("volume_shares", "float")],
    ))
    for offset in range(22):
        day = date(2024, 9, 2) + timedelta(days=offset)
        for config, values in (
            (PREOPEN_CONFIG, {}),
            (RESULT_CONFIG, {}),
        ):
            path = data_dir / "ext_data" / config / "timeseries" / f"date={day.isoformat()}"
            path.mkdir(parents=True)
            rows = []
            for index, symbol in enumerate(SYMBOLS):
                numbers = {
                    "last_imbalance": 0.3 + offset / 1000 + index * 0.1,
                    "last_minute_matched_growth": 0.4 + index * 0.1,
                    "post0920_matched_growth": 0.5 + index * 0.1,
                    "volume_shares": 200_000.0 + offset * 10_000 + index * 50_000,
                }
                rows.append({"symbol": symbol, **values, **numbers})
            pl.DataFrame(rows).write_parquet(path / "part.parquet")


def _panel() -> pl.DataFrame:
    start = date(2024, 9, 2)
    rows = []
    for offset in range(22):
        for index, symbol in enumerate(SYMBOLS):
            rows.append({
                "symbol": symbol,
                "date": start + timedelta(days=offset),
                "open": 10.0 + offset / 100 + index,
                "high": 10.2 + offset / 100 + index,
                "low": 9.9 + offset / 100 + index,
                "close": 10.1 + offset / 100 + index,
                "volume": 10_000.0 + offset * 500 + index * 1000,
                "amount": 101_000.0 + offset * 5_100 + index * 10_000,
                "turnover_rate": 1.0 + offset / 100 + index * 0.1,
            })
    return pl.DataFrame(rows)


@pytest.fixture(autouse=True)
def _clean_registry():
    from app.factors import registry

    # 本文件只测竞价包自己的动态注册。**入口先快照整表**：provider 装载包的因子
    # （B0 14 个 + in_universe + 竞价包）同样是 kind=custom，属于进程级注册状态，
    # 而 `extensions.factors._PROVIDERS_READY` 在首次发现后即为 True，被清掉后
    # `all_factors()` 不会重新发现 —— 不恢复就会把 110 变成 93（全量跑 10 红）。
    saved_registry = dict(registry._REGISTRY)

    def dynamic_ids():
        return [
            key for key, spec in registry._REGISTRY.items()
            if spec.kind in {"custom", "composite"} or key.startswith("ext_")
        ]

    for key in dynamic_ids():
        registry._REGISTRY.pop(key, None)
    _load_all_cache.clear()
    ext_factors._frame_cache.clear()
    ext_factors._sync_state = None
    yield
    for key in dynamic_ids():
        registry._REGISTRY.pop(key, None)
    # 恢复入口快照：只回滚本文件的增删，不把 provider 装载包留在被清空的状态。
    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved_registry)
    _load_all_cache.clear()
    ext_factors._frame_cache.clear()
    ext_factors._sync_state = None


def test_load_registry_syncs_extensions_before_formula_factors(tmp_path):
    _ext_configs(tmp_path)
    save_one(tmp_path, {
        "id": "uf_auction_imbalance_test",
        "kind": "custom",
        "version": 1,
        "label": "竞价失衡测试",
        "group": "竞价",
        "formula": "ext_auction_preopen_last_imbalance",
        "status": "draft",
        "direction": "none",
    })
    loaded = load_into_registry(tmp_path)
    assert "uf_auction_imbalance_test" in loaded
    assert get_factor("ext_auction_preopen_last_imbalance") is not None
    assert get_factor("uf_auction_imbalance_test") is not None


def test_custom_factor_referencing_extension_materializes_transitively(tmp_path, monkeypatch):
    from app import config as app_config
    from app.backtest.factor import FactorBacktestService

    monkeypatch.setattr(app_config.settings, "data_dir", tmp_path)
    _ext_configs(tmp_path)
    load_into_registry(tmp_path)
    save_one(tmp_path, {
        "id": "uf_auction_imbalance_test",
        "kind": "custom",
        "version": 1,
        "label": "竞价失衡测试",
        "group": "竞价",
        "formula": "ext_auction_preopen_last_imbalance",
        "status": "draft",
        "direction": "none",
    })
    load_into_registry(tmp_path)
    out = FactorBacktestService._compute_missing_factors(
        _panel(), {"uf_auction_imbalance_test"}, assume_sorted=True
    )
    values = out.filter(pl.col("symbol") == "000001.SZ")[
        "uf_auction_imbalance_test"
    ]
    assert values[0] == pytest.approx(0.3)
    assert values[1] == pytest.approx(0.301)


def test_auction_factor_pack_is_idempotent_and_registers_composite(tmp_path):
    from scripts.install_auction_factor_pack import COMPOSITE_ID, FACTOR_IDS, install

    _ext_configs(tmp_path)
    first = install(tmp_path)
    assert first["created"] == len(FACTOR_IDS) + 1
    assert set(FACTOR_IDS) | {COMPOSITE_ID} <= {
        item.id for item in (get_factor(name) for name in (*FACTOR_IDS, COMPOSITE_ID))
        if item is not None
    }
    second = install(tmp_path)
    assert second["created"] == 0
    assert second["unchanged"] == len(FACTOR_IDS) + 1
    composite = get_factor(COMPOSITE_ID)
    assert composite is not None and composite.kind == "composite"
    assert composite.components == (
        ("uf_auction_tail_imbalance", 0.35),
        ("uf_auction_post0920_match_growth", -0.3),
        ("uf_auction_volume_vs_prev", -0.2),
        ("uf_auction_volume_surprise", -0.15),
    )
    assert get_factor("uf_auction_tail_imbalance").direction == "high"
    assert get_factor("uf_auction_post0920_match_growth").direction == "low"


def test_all_pack_formulas_have_non_null_output_on_real_fixture(tmp_path, monkeypatch):
    from app import config as app_config
    from app.backtest.factor import FactorBacktestService
    from scripts.install_auction_factor_pack import FACTOR_IDS, install

    monkeypatch.setattr(app_config.settings, "data_dir", tmp_path)
    _ext_configs(tmp_path)
    install(tmp_path)
    panel = _panel()
    for name in FACTOR_IDS:
        out = FactorBacktestService._compute_missing_factors(
            panel, {name}, assume_sorted=True
        )
        assert out[name].is_not_null().sum() > 0, name


def test_composite_materializes_custom_members_that_use_extensions(tmp_path, monkeypatch):
    from app import config as app_config
    from app.backtest.factor import FactorBacktestService
    from scripts.install_auction_factor_pack import COMPOSITE_ID, install

    monkeypatch.setattr(app_config.settings, "data_dir", tmp_path)
    _ext_configs(tmp_path)
    install(tmp_path)
    out = FactorBacktestService._compute_missing_factors(
        _panel(), {COMPOSITE_ID}, assume_sorted=True
    )
    assert COMPOSITE_ID in out.columns
    assert out[COMPOSITE_ID].is_not_null().sum() > 0


def test_composite_scheme_materializes_through_strategy_scoring_path(tmp_path, monkeypatch):
    from app import config as app_config
    from app.strategy.scoring import materialize_scoring_columns
    from scripts.install_auction_factor_pack import COMPOSITE_ID, install

    monkeypatch.setattr(app_config.settings, "data_dir", tmp_path)
    _ext_configs(tmp_path)
    install(tmp_path)
    panel = ext_factors.attach_ext_columns(
        _panel(), include_snapshot=False, data_dir=tmp_path
    )
    out = materialize_scoring_columns(panel, [COMPOSITE_ID])
    assert COMPOSITE_ID in out.columns
    assert out[COMPOSITE_ID].is_not_null().sum() > 0
    latest = out.filter(pl.col("date") == out["date"].max()).sort("symbol")
    weights = {
        "uf_auction_tail_imbalance": 0.35,
        "uf_auction_post0920_match_growth": -0.30,
        "uf_auction_volume_vs_prev": -0.20,
        "uf_auction_volume_surprise": -0.15,
    }
    expected = [0.0] * latest.height
    for name, weight in weights.items():
        values = latest[name].to_list()
        average = mean(values)
        spread = stdev(values)
        for index, value in enumerate(values):
            expected[index] += weight * (value - average) / spread
    assert latest[COMPOSITE_ID].to_list() == pytest.approx(expected)
