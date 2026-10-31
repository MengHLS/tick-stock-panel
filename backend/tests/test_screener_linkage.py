"""Screener / StrategyEngine 联动字段装配测试。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from app.enriched_generation import bump_enriched_generation
from app.factors.linkage import LINKAGE_FACTOR_IDS
from app.strategy.engine import (
    StrategyDataContext,
    StrategyDef,
    StrategyEngine,
)


@pytest.fixture(autouse=True)
def _migrated_signal_definitions(monkeypatch):
    from tests.signal_seeds import install_pipeline_caches

    install_pipeline_caches(monkeypatch)


def _write_linkage_sidecar(
    data_dir: Path,
    dates: list[date],
    symbols: tuple[str, ...],
    value: float = 0.9,
    factor_name: str = "industry_relative_momentum_20d",
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


def _strategy(
    *,
    matrix: bool = False,
    factor_name: str = "industry_relative_momentum_20d",
) -> StrategyDef:
    matrix_strategy = None
    if matrix:
        from types import SimpleNamespace

        matrix_strategy = SimpleNamespace(
            required_fields=lambda: {factor_name},
            required_warmup_bars=lambda _params: 20,
        )
    return StrategyDef(
        meta={
            "id": "linkage_matrix" if matrix else "linkage_panel",
            "asset_types": ["stock"],
            "timeframes": ["1d"],
        },
        basic_filter={},
        entry_signals=[],
        exit_signals=[],
        stop_loss=None,
        trailing_stop=None,
        trailing_take_profit_activate=None,
        trailing_take_profit_drawdown=None,
        max_hold_days=None,
        filter_fn=None if matrix else (
            lambda _df, _params: pl.col(factor_name) > 0.5
        ),
        filter_history_fn=None,
        lookback_days=20,
        source="custom",
        required_features=frozenset({factor_name}),
        execution_backend="matrix_native" if matrix else "polars_expr",
        matrix_strategy=matrix_strategy,
    )


def _context(dates: list[date]) -> StrategyDataContext:
    frame = pl.DataFrame([
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
    return StrategyDataContext(
        asset_type="stock",
        timeframe="1d",
        as_of=dates[-1],
        current=frame.filter(pl.col("date") == dates[-1]),
        history=frame,
    )


def test_run_all_panel_strategy_reads_linkage_before_filter(tmp_path: Path) -> None:
    dates = [date(2026, 3, 2), date(2026, 3, 3)]
    _write_linkage_sidecar(tmp_path, dates, ("600000.SH",))
    custom_dir = tmp_path / "strategies" / "custom"
    custom_dir.mkdir(parents=True)
    engine = StrategyEngine(strategy_dirs=[custom_dir])
    strategy = _strategy()
    engine._strategies = {strategy.meta["id"]: strategy}

    results = engine.run_all(
        _context(dates),
        strategy_ids=[strategy.meta["id"]],
        parallel=False,
    )

    assert results[strategy.meta["id"]].total == 1


def test_matrix_native_shared_matrix_receives_linkage_field(tmp_path: Path) -> None:
    dates = [date(2026, 3, 2), date(2026, 3, 3)]
    _write_linkage_sidecar(tmp_path, dates, ("600000.SH",))
    custom_dir = tmp_path / "strategies" / "custom"
    custom_dir.mkdir(parents=True)
    engine = StrategyEngine(strategy_dirs=[custom_dir])
    strategy = _strategy(matrix=True)
    engine._strategies = {strategy.meta["id"]: strategy}
    context = _context(dates)

    prepared = engine._attach_context_linkage(
        context,
        [(strategy.meta["id"], strategy)],
        {},
        {},
    )
    market = engine.build_shared_matrix(
        prepared,
        [(strategy.meta["id"], strategy)],
        {},
        {},
    )

    assert market is not None
    assert "industry_relative_momentum_20d" in market.fields


def test_live_deviate_keeps_realtime_current_value(tmp_path: Path) -> None:
    finalized = date(2026, 3, 2)
    live_day = date(2026, 3, 3)
    factor = "deviate_3d"
    _write_linkage_sidecar(
        tmp_path,
        [finalized],
        ("600000.SH",),
        value=0.35,
        factor_name=factor,
    )
    custom_dir = tmp_path / "strategies" / "custom"
    custom_dir.mkdir(parents=True)
    engine = StrategyEngine(strategy_dirs=[custom_dir])
    strategy = _strategy(factor_name=factor)
    engine._strategies = {strategy.meta["id"]: strategy}
    context = _context([finalized, live_day])
    context = StrategyDataContext(
        asset_type=context.asset_type,
        timeframe=context.timeframe,
        as_of=live_day,
        current=context.current.with_columns(pl.lit(0.42).alias(factor)),
        history=context.history.with_columns(
            pl.when(pl.col("date") == finalized)
            .then(pl.lit(0.35))
            .otherwise(pl.lit(0.42))
            .alias(factor)
        ),
    )

    attached = engine._attach_context_linkage(
        context,
        [(strategy.meta["id"], strategy)],
        {},
        {},
    )

    assert attached.history is not None
    assert attached.current is not None
    history = attached.history.sort("date")
    assert history[factor].to_list() == pytest.approx([0.35, 0.42])
    assert attached.current[factor].to_list() == pytest.approx([0.42])
