"""Matrix-native linkage fields: stable sidecar injection and cache behavior."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import polars as pl
import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.matrix import MatrixCacheProfile
from app.enriched_generation import bump_enriched_generation
from app.factors.linkage import LINKAGE_FACTOR_IDS
from app.factors.linkage_store import LinkageCoverageError, LinkageReadUnstableError
from app.strategy.engine import StrategyDataContext, StrategyDef, StrategyEngine
from app.tickflow.repository import DataStore, KlineRepository


@pytest.fixture(autouse=True)
def _migrated_signal_definitions(monkeypatch):
    from tests.signal_seeds import install_pipeline_caches

    install_pipeline_caches(monkeypatch)


DATES = [
    date(2026, 4, 1),
    date(2026, 4, 2),
    date(2026, 4, 3),
    date(2026, 4, 7),
]
SYMBOLS = ("600001.SH", "600002.SH")
LINKAGE = "industry_relative_momentum_20d"


def _write_enriched(data_dir: Path) -> None:
    for offset, day in enumerate(DATES):
        rows = []
        for asset_id, symbol in enumerate(SYMBOLS):
            close = 10.0 + offset + asset_id * 0.5
            rows.append({
                "symbol": symbol,
                "date": day,
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 1000.0,
                "amount": close * 10000.0,
                "turnover_rate": 1.0 + asset_id,
                "raw_close": close,
            })
        part = data_dir / "kline_daily_enriched" / f"date={day.isoformat()}"
        part.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(rows).write_parquet(part / "part.parquet")

    instruments = data_dir / "instruments"
    instruments.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({
        "symbol": SYMBOLS,
        "name": ["甲", "乙"],
        "total_shares": [1e9, 1e9],
        "float_shares": [1e9, 1e9],
    }).write_parquet(instruments / "part.parquet")


def _write_linkage(
    data_dir: Path,
    values: dict[tuple[str, date], float],
    *,
    finalized_through: date = DATES[-1],
) -> None:
    root = data_dir / "kline_daily_linkage"
    for day in DATES:
        part = root / f"date={day.isoformat()}"
        part.mkdir(parents=True, exist_ok=True)
        pl.DataFrame([
            {
                "symbol": symbol,
                "date": day,
                LINKAGE: values[(symbol, day)],
            }
            for symbol in SYMBOLS
        ]).write_parquet(part / "part.parquet")
    (root / "manifest.json").write_text(
        json.dumps({
            "version": 1,
            "methodology_version": "linkage_v1",
            "factor_ids": sorted(LINKAGE_FACTOR_IDS),
            "min_peers": 10,
            "coverage_start": DATES[0].isoformat(),
            "finalized_through": finalized_through.isoformat(),
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    bump_enriched_generation(data_dir, "linkage")


def _plan() -> SimpleNamespace:
    return SimpleNamespace(
        execution_backend="matrix_native",
        base_columns=frozenset({"turnover_rate"}),
        instrument_columns=frozenset({"name"}),
        matrix_columns=frozenset({LINKAGE}),
        linkage_columns=frozenset({LINKAGE}),
        fundamental_columns=frozenset(),
        historical_st=False,
    )


def _engine(data_dir: Path) -> BacktestEngine:
    return BacktestEngine(KlineRepository(DataStore(data_dir)))


def _load(engine: BacktestEngine):
    profile = MatrixCacheProfile(
        field_columns=frozenset({"turnover_rate", "name", LINKAGE}),
        warmup_bars=1,
        forward_bars=1,
    )
    return engine.load_market_data_matrix_for_backtest(
        None,
        DATES[0],
        DATES[-1],
        _plan(),
        cache_profile=profile,
    )


def _values(value: float) -> dict[tuple[str, date], float]:
    return {
        (symbol, day): value + asset_id * 0.1
        for day in DATES
        for asset_id, symbol in enumerate(SYMBOLS)
    }


@pytest.fixture()
def matrix_data(tmp_path: Path) -> Path:
    _write_enriched(tmp_path)
    _write_linkage(tmp_path, _values(0.2))
    return tmp_path


def test_matrix_load_injects_linkage_without_putting_it_in_base_cache(
    matrix_data: Path,
) -> None:
    engine = _engine(matrix_data)

    first = _load(engine)
    repeated = _load(engine)

    assert first.cache_status == "built"
    assert repeated.cache_status == "exact"
    assert repeated.cache_path == first.cache_path
    assert first.cache_path is not None
    manifest = json.loads(
        (Path(first.cache_path) / "manifest.json").read_text(encoding="utf-8")
    )
    assert LINKAGE not in manifest["cache_field_columns"]
    assert LINKAGE not in manifest["fields"]

    array = np.asarray(first.fields[LINKAGE])
    assert array.shape == (len(DATES), len(SYMBOLS))
    assert array[0, 0] == pytest.approx(0.2)
    assert array[-1, 1] == pytest.approx(0.3)
    assert not array.flags.writeable

    _write_linkage(matrix_data, _values(0.8))
    refreshed = _load(engine)

    assert refreshed.cache_status == "exact"
    assert refreshed.cache_path == first.cache_path
    assert np.asarray(refreshed.fields[LINKAGE])[0, 0] == pytest.approx(0.8)


def test_matrix_load_fails_closed_when_linkage_coverage_is_short(
    matrix_data: Path,
) -> None:
    _write_linkage(
        matrix_data,
        _values(0.2),
        finalized_through=DATES[-2],
    )

    with pytest.raises(LinkageCoverageError, match="覆盖不足"):
        _load(_engine(matrix_data))


def test_matrix_load_rejects_missing_symbol_rows(matrix_data: Path) -> None:
    partition = (
        matrix_data
        / "kline_daily_linkage"
        / f"date={DATES[-1].isoformat()}"
        / "part.parquet"
    )
    manifest = json.loads(
        (matrix_data / "kline_daily_linkage" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    partition = partition.with_name(
        manifest.get("partitions", {}).get(DATES[-1].isoformat(), "part.parquet")
    )
    pl.read_parquet(partition).filter(
        pl.col("symbol") == SYMBOLS[0]
    ).write_parquet(partition)

    with pytest.raises(LinkageCoverageError, match="缺标的"):
        _load(_engine(matrix_data))


def test_matrix_load_rebuilds_base_matrix_when_linkage_generation_changes(
    matrix_data: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.backtest import engine as engine_module
    from app.factors import linkage_store

    _load(_engine(matrix_data))
    engine = _engine(matrix_data)
    load_calls = 0
    original_load = engine_module.load_market_data_matrix_from_parquet
    original_attach = linkage_store.attach_matrix_linkage_fields
    attach_calls = 0

    def counted_load(*args, **kwargs):
        nonlocal load_calls
        load_calls += 1
        return original_load(*args, **kwargs)

    def racing_attach(*args, **kwargs):
        nonlocal attach_calls
        attach_calls += 1
        if attach_calls == 1:
            _write_linkage(matrix_data, _values(0.9))
        return original_attach(*args, **kwargs)

    monkeypatch.setattr(
        engine_module,
        "load_market_data_matrix_from_parquet",
        counted_load,
    )
    monkeypatch.setattr(
        linkage_store,
        "attach_matrix_linkage_fields",
        racing_attach,
    )

    market = _load(engine)

    assert attach_calls == 2
    assert load_calls == 2
    assert np.asarray(market.fields[LINKAGE])[0, 0] == pytest.approx(0.9)


def _context(days: list[date]) -> StrategyDataContext:
    frame = pl.DataFrame([
        {
            "symbol": symbol,
            "date": day,
            "open": 10.0,
            "high": 10.2,
            "low": 9.8,
            "close": 10.0,
            "volume": 1000.0,
        }
        for day in days
        for symbol in SYMBOLS
    ])
    return StrategyDataContext(
        asset_type="stock",
        timeframe="1d",
        as_of=days[-1],
        current=frame.filter(pl.col("date") == days[-1]),
        history=frame,
    )


def _strategy() -> StrategyDef:
    matrix_strategy = SimpleNamespace(
        required_fields=lambda: {LINKAGE},
        required_warmup_bars=lambda _params: 1,
    )
    return StrategyDef(
        meta={
            "id": "linkage_live_matrix",
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
        filter_fn=None,
        filter_history_fn=None,
        lookback_days=1,
        source="custom",
        required_features=frozenset({LINKAGE}),
        execution_backend="matrix_native",
        matrix_strategy=matrix_strategy,
    )


def test_realtime_matrix_attaches_and_invalidates_linkage(
    matrix_data: Path,
) -> None:
    custom_dir = matrix_data / "strategies" / "custom"
    custom_dir.mkdir(parents=True)
    engine = StrategyEngine(strategy_dirs=[custom_dir])
    strategy = _strategy()
    engine._strategies = {strategy.meta["id"]: strategy}
    context = _context(DATES[-2:])

    first = engine.prepare_realtime_matrix(
        context,
        [strategy.meta["id"]],
    )
    assert first is not None
    assert np.asarray(first.fields[LINKAGE])[-1, 0] == pytest.approx(0.2)

    _write_linkage(matrix_data, _values(1.2))
    second = engine.prepare_realtime_matrix(
        context,
        [strategy.meta["id"]],
    )

    assert second is not None
    assert np.asarray(second.fields[LINKAGE])[-1, 0] == pytest.approx(1.2)


def test_context_linkage_refreshes_preattached_stale_columns(
    matrix_data: Path,
) -> None:
    custom_dir = matrix_data / "strategies" / "custom"
    custom_dir.mkdir(parents=True)
    engine = StrategyEngine(strategy_dirs=[custom_dir])
    strategy = _strategy()
    engine._strategies = {strategy.meta["id"]: strategy}
    context = _context(DATES[-2:])
    context = StrategyDataContext(
        asset_type=context.asset_type,
        timeframe=context.timeframe,
        as_of=context.as_of,
        current=context.current.with_columns(pl.lit(9.9).alias(LINKAGE)),
        history=context.history.with_columns(pl.lit(9.9).alias(LINKAGE)),
    )

    refreshed = engine._attach_context_linkage(
        context,
        [(strategy.meta["id"], strategy)],
        {},
        {},
    )

    assert refreshed.history is not None
    assert refreshed.history[LINKAGE].unique().to_list() == pytest.approx([0.2, 0.3])


def test_linkage_instability_type_is_public() -> None:
    assert issubclass(LinkageReadUnstableError, RuntimeError)
