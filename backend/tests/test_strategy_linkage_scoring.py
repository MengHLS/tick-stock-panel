"""面板策略联动字段分类与加载测试。"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.strategy import ResolvedFeaturePlan, StrategyDependencyResolver
from app.enriched_generation import bump_enriched_generation
from app.custom.cross_sectional_linkage.compute import LINKAGE_FACTOR_IDS


@pytest.fixture(autouse=True)
def _migrated_signal_definitions(monkeypatch):
    from tests.signal_seeds import install_pipeline_caches

    install_pipeline_caches(monkeypatch)


def _write_linkage_sidecar(
    data_dir: Path,
    dates: list[date],
    symbols: tuple[str, ...],
    factor_name: str = "industry_relative_momentum_20d",
    value: float = 0.9,
) -> None:
    root = data_dir / "kline_daily_linkage"
    for day in dates:
        out = root / f"date={day.isoformat()}" / "part.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        pl.DataFrame([
            {"symbol": symbol, "date": day, factor_name: value}
            for symbol in symbols
        ]).write_parquet(out)
    (root / "manifest.json").write_text(
        json.dumps({
            "version": 1,
            "methodology_version": "linkage_v1",
            "factor_ids": sorted(LINKAGE_FACTOR_IDS),
            "min_peers": 10,
            "coverage_start": dates[0].isoformat(),
            "finalized_through": dates[-1].isoformat(),
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    bump_enriched_generation(data_dir, "linkage")


def test_resolver_classifies_linkage_outside_physical_base_columns() -> None:
    strategy = SimpleNamespace(
        execution_backend="polars_expr",
        required_features=frozenset({"industry_relative_momentum_20d"}),
        meta={"id": "panel_linkage"},
        filter_fn=lambda _df, _params: pl.lit(True),
        filter_history_fn=None,
        lookback_days=20,
    )

    plan = StrategyDependencyResolver().resolve(
        strategy,
        params={},
        basic_filter={},
        entry_signals=[],
        exit_signals=[],
    )

    assert plan.linkage_columns == frozenset({"industry_relative_momentum_20d"})
    assert "industry_relative_momentum_20d" not in plan.base_columns
    assert "industry_relative_momentum_20d" in plan.matrix_columns


def test_resolver_matrix_native_includes_linkage_columns() -> None:
    matrix_strategy = SimpleNamespace(
        required_fields=lambda: {"industry_beta_60d"},
        required_warmup_bars=lambda _params: 65,
    )
    strategy = SimpleNamespace(
        execution_backend="matrix_native",
        required_features=frozenset(),
        matrix_strategy=matrix_strategy,
        meta={"id": "matrix_linkage"},
        filter_fn=None,
        filter_history_fn=None,
        lookback_days=1,
    )

    plan = StrategyDependencyResolver().resolve(
        strategy,
        params={},
        basic_filter={},
        entry_signals=[],
        exit_signals=[],
    )

    assert plan.linkage_columns == frozenset({"industry_beta_60d"})
    assert "industry_beta_60d" not in plan.base_columns
    assert "industry_beta_60d" in plan.matrix_columns
    assert plan.warmup_bars >= 61


def test_load_panel_for_backtest_attaches_linkage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.factors import ext_factors

    monkeypatch.setattr(
        ext_factors,
        "attach_ext_columns",
        lambda frame, **_kwargs: frame,
    )
    start = date(2026, 2, 2)
    dates = [start, start + timedelta(days=1)]
    _write_linkage_sidecar(tmp_path, dates, ("600000.SH",))
    panel = pl.DataFrame([
        {
            "symbol": "600000.SH",
            "date": day,
            "open": 10.0,
            "high": 10.2,
            "low": 9.8,
            "close": 10.0,
            "volume": 1000.0,
        }
        for day in dates
    ])
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        get_instruments_asset=lambda _asset_type: pl.DataFrame(),
        get_historical_shares=lambda: pl.DataFrame(),
    )
    engine = BacktestEngine(repo)
    monkeypatch.setattr(
        engine,
        "load_panel",
        lambda _symbols, _start, _end, columns, asset_type, **_kwargs: panel.select(columns),
    )
    plan = ResolvedFeaturePlan(
        base_columns=frozenset({"symbol", "date", "open", "high", "low", "close", "volume"}),
        intermediate_columns=frozenset(),
        indicator_columns=frozenset(),
        signal_columns=frozenset(),
        matrix_columns=frozenset({"industry_relative_momentum_20d"}),
        instrument_columns=frozenset(),
        warmup_bars=61,
        linkage_columns=frozenset({"industry_relative_momentum_20d"}),
    )

    loaded = engine.load_panel_for_backtest(None, start, dates[-1], plan)

    assert loaded["industry_relative_momentum_20d"].to_list() == pytest.approx([0.9, 0.9])
