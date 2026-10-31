from datetime import date
from types import SimpleNamespace

import numpy as np
import polars as pl
import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.matrix import (
    MatrixPipelineConfig,
    MatrixStrategyPipeline,
    build_basic_filter_mask,
    build_market_data_matrix,
    make_signal_matrix,
)
from app.indicators.pipeline import compute_limit_signals
from app.services.screener import ScreenerService
from app.strategy.engine import StrategyDataContext, StrategyDef, StrategyEngine
from app.tickflow.repository import DataStore, KlineRepository


def _panel() -> pl.DataFrame:
    # Current names deliberately contradict the historical status.
    return pl.DataFrame({
        "symbol": ["000001.SZ", "000001.SZ", "000002.SZ", "000002.SZ"],
        "date": [date(2025, 1, 2), date(2025, 1, 3)] * 2,
        "name": ["ST Later", "ST Later", "Normal Now", "Normal Now"],
        "open": [10.0] * 4,
        "high": [10.2] * 4,
        "low": [9.8] * 4,
        "close": [10.0] * 4,
        "volume": [1000.0] * 4,
        "st_flag": [0.0, 1.0, 1.0, 0.0],
    })


def test_panel_historical_st_filter_uses_each_date_instead_of_current_name():
    panel = _panel()
    expr = StrategyEngine._basic_filter_expr(
        panel, {"exclude_st": True, "_historical": True}
    )
    assert panel.select(expr.alias("keep"))["keep"].to_list() == [
        True, False, False, True,
    ]


def test_matrix_historical_st_filter_uses_each_date_instead_of_current_name():
    market = build_market_data_matrix(_panel(), field_columns={"st_flag"})
    mask = build_basic_filter_mask(
        market, {"exclude_st": True, "_historical": True}
    )
    np.testing.assert_array_equal(mask, [[True, False], [False, True]])


def test_historical_st_filter_precedes_top_n_and_keeps_exit_signals():
    class Candidates:
        def compute_signals(self, market, params):
            return make_signal_matrix(
                market.shape,
                entry=np.ones(market.shape, dtype=np.uint8),
                exit=np.ones(market.shape, dtype=np.uint8),
                score=np.array([[0.9, 0.8], [0.9, 0.8]], dtype=np.float32),
            )

        def daily_candidate_limit(self, params):
            return 1

    market = build_market_data_matrix(_panel(), field_columns={"st_flag"})
    signals = MatrixStrategyPipeline().run(
        Candidates(), market, {},
        MatrixPipelineConfig(
            basic_filter={"exclude_st": True, "_historical": True},
            scoring={}, order_by="score", descending=True,
        ),
    )
    np.testing.assert_array_equal(signals.entry, [[1, 0], [0, 1]])
    np.testing.assert_array_equal(signals.exit, [[1, 1], [1, 1]])


@pytest.mark.parametrize("matrix", [False, True])
def test_historical_st_exclusion_rejects_missing_history(matrix):
    panel = _panel().drop("st_flag")
    config = {"exclude_st": True, "_historical": True}
    with pytest.raises(ValueError, match="ST"):
        if matrix:
            build_basic_filter_mask(build_market_data_matrix(panel), config)
        else:
            StrategyEngine._basic_filter_expr(panel, config)


def test_realtime_st_filter_still_uses_current_names():
    panel = _panel()
    expr = StrategyEngine._basic_filter_expr(panel, {"exclude_st": True})
    assert panel.select(expr.alias("keep"))["keep"].to_list() == [
        False, False, True, True,
    ]


def test_repository_history_aligns_transitions_without_future_backfill(tmp_path):
    from app.tickflow.security_status import attach_st_history

    root = tmp_path / "st_history"
    root.mkdir()
    pl.DataFrame({
        "symbol": ["000001.SZ"] * 3,
        "flag_date": [date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6)],
        "st_flag": [False, True, False],
    }).write_parquet(root / "part.parquet")
    store = DataStore(tmp_path)
    try:
        repo = KlineRepository(store)
        panel = pl.DataFrame({
            "symbol": ["000001.SZ"] * 5,
            "date": [date(2025, 1, day) for day in [1, 2, 3, 6, 7]],
        })
        actual = attach_st_history(panel, repo.get_st_history())
        assert actual["st_flag"].to_list() == [None, False, True, False, False]
        # A subsequent read sees the new normalized snapshot without clearing
        # the price-matrix cache or restarting the repository.
        pl.DataFrame({
            "symbol": ["000001.SZ"],
            "flag_date": [date(2025, 1, 2)],
            "st_flag": [True],
        }).write_parquet(root / "part.parquet")
        assert attach_st_history(panel, repo.get_st_history())["st_flag"].to_list() == [
            None, True, True, True, True,
        ]
    finally:
        store.db.close()


@pytest.mark.parametrize("matrix", [False, True])
def test_unknown_historical_st_status_is_excluded(matrix):
    panel = _panel().with_columns(
        pl.Series("st_flag", [None, 1.0, 1.0, 0.0], dtype=pl.Float64)
    )
    config = {"exclude_st": True, "_historical": True}
    if matrix:
        mask = build_basic_filter_mask(
            build_market_data_matrix(panel, field_columns={"st_flag"}), config
        )
        np.testing.assert_array_equal(mask, [[False, False], [False, True]])
    else:
        expr = StrategyEngine._basic_filter_expr(panel, config)
        assert panel.select(expr.alias("keep"))["keep"].to_list() == [
            False, False, False, True,
        ]


def test_backtest_loaders_attach_status_even_when_price_matrix_is_cached(tmp_path, monkeypatch):
    from app.backtest import engine as engine_module

    root = tmp_path / "st_history"
    root.mkdir()
    history = pl.DataFrame({
        "symbol": ["000001.SZ", "000002.SZ"],
        "flag_date": [date(2025, 1, 2)] * 2,
        "st_flag": [False, True],
    })
    history.write_parquet(root / "part.parquet")
    store = DataStore(tmp_path)
    try:
        repo = KlineRepository(store)
        engine = BacktestEngine(repo)
        monkeypatch.setattr(engine, "load_panel", lambda *a, **kw: _panel().drop("st_flag"))
        monkeypatch.setattr(engine, "data_generation_await", lambda *a, **kw: "test")
        monkeypatch.setattr(engine, "assert_data_generation", lambda *a, **kw: None)
        cached = build_market_data_matrix(_panel().drop("st_flag"))
        monkeypatch.setattr(
            engine_module, "load_market_data_matrix_from_parquet", lambda *a, **kw: cached
        )
        plan = SimpleNamespace(
            historical_st=True, execution_backend="matrix_native",
            base_columns=frozenset({"symbol", "date", "close"}),
            instrument_columns=frozenset(), matrix_columns=frozenset(),
            indicator_columns=frozenset(), signal_columns=frozenset(),
        )
        args = (None, date(2025, 1, 2), date(2025, 1, 3), plan)
        assert engine.load_panel_for_backtest(*args)["st_flag"].to_list() == [
            False, False, True, True,
        ]
        market = engine.load_market_data_matrix_for_backtest(*args)
        np.testing.assert_array_equal(market.field("st_flag"), [[0, 1], [0, 1]])
        history.with_columns((~pl.col("st_flag")).alias("st_flag")).write_parquet(
            root / "part.parquet"
        )
        updated = engine.load_market_data_matrix_for_backtest(*args)
        np.testing.assert_array_equal(updated.field("st_flag"), [[1, 0], [1, 0]])
        assert "st_flag" not in cached.fields
    finally:
        store.db.close()


def test_historical_status_drives_daily_five_percent_limit_rule():
    panel = pl.DataFrame({
        "symbol": ["600001.SH"] * 2,
        "date": [date(2025, 1, 2), date(2025, 1, 3)],
        "open": [10.0, 10.5],
        "high": [10.0, 10.5],
        "low": [10.0, 10.5],
        "close": [10.0, 10.5],
        "raw_close": [10.0, 10.5],
        "raw_high": [10.0, 10.5],
        "raw_low": [10.0, 10.5],
        "volume": [1000.0, 1000.0],
        "amount": [10_000.0, 10_500.0],
        "st_flag": [True, True],
    })
    result = compute_limit_signals(
        panel,
        pl.DataFrame({"symbol": ["600001.SH"], "name": ["正常股"]}),
        needed={"consecutive_limit_ups"},
    )
    # Effective limit prices carry the documented 0.005 tolerance.
    assert result["limit_up_price"][-1] == 10.495
    assert result["consecutive_limit_ups"][-1] == 1


def test_matrix_limit_lock_uses_historical_st_not_latest_name():
    from app.tickflow.security_status import attach_matrix_st_history

    panel = pl.DataFrame({
        "symbol": ["603429.SH", "603429.SH"],
        "name": ["*ST集友", "*ST集友"],
        "date": [date(2025, 1, 2), date(2025, 1, 3)],
        "open": [10.0, 10.5],
        "high": [10.0, 10.5],
        "low": [10.0, 10.5],
        "close": [10.0, 10.5],
        "raw_close": [10.0, 10.5],
        "volume": [1000.0, 1000.0],
    })
    market = build_market_data_matrix(
        panel,
        field_columns={"raw_close"},
    )
    not_st = pl.DataFrame({
        "symbol": ["603429.SH"],
        "flag_date": [date(2025, 1, 2)],
        "st_flag": [False],
    })
    historical_not_st = attach_matrix_st_history(market, not_st)
    assert historical_not_st.limit_up_locked[:, 0].tolist() == [0, 0]

    historical_st = attach_matrix_st_history(
        market,
        not_st.with_columns(pl.lit(True).alias("st_flag")),
    )
    assert historical_st.limit_up_locked[:, 0].tolist() == [0, 1]


def test_matrix_limit_lock_does_not_treat_ex_right_drop_as_limit_up():
    from app.tickflow.security_status import attach_matrix_st_history

    panel = pl.DataFrame({
        "symbol": ["603127.SH", "603127.SH"],
        "name": ["康龙化成", "康龙化成"],
        "date": [date(2019, 4, 9), date(2019, 4, 10)],
        "open": [12.35, 12.26],
        "high": [12.44, 12.89],
        "low": [12.18, 12.17],
        "close": [12.264, 12.433],
        "raw_close": [68.50, 49.38],
        "volume": [16933.0, 21227.0],
    })
    market = build_market_data_matrix(
        panel,
        field_columns={"raw_close"},
    )
    history = pl.DataFrame({
        "symbol": ["603127.SH"],
        "flag_date": [date(2019, 4, 9)],
        "st_flag": [False],
    })

    adjusted = attach_matrix_st_history(market, history)
    assert adjusted.limit_up_locked[:, 0].tolist() == [0, 0]


def _historical_engine(basic_filter=None, matrix_strategy=None) -> StrategyEngine:
    engine = StrategyEngine(strategy_dirs=[])
    engine._strategies = {
        "historical": StrategyDef(
            meta={
                "id": "historical",
                "asset_types": ["stock"],
                "timeframes": ["1d"],
                "scoring": {},
                "order_by": "close",
                "descending": True,
                "limit": 10,
            },
            basic_filter=basic_filter or {"exclude_st": True},
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
            required_features=frozenset({"close"}),
            execution_backend="matrix_native" if matrix_strategy else "polars_expr",
            matrix_strategy=matrix_strategy,
        )
    }
    return engine


def _historical_context(panel: pl.DataFrame, *, matrix: bool) -> StrategyDataContext:
    as_of = date(2025, 1, 2)
    history = pl.DataFrame({
        "symbol": ["A", "B"],
        "flag_date": [as_of, as_of],
        "st_flag": [False, True],
    })
    return StrategyDataContext(
        asset_type="stock",
        timeframe="1d",
        as_of=as_of,
        current=panel.filter(pl.col("date") == as_of),
        history=panel if matrix else None,
        st_history=history,
        historical_st=True,
    )


def test_historical_strategy_scan_uses_effective_status_in_polars_path():
    as_of = date(2025, 1, 2)
    panel = pl.DataFrame({
        "symbol": ["A", "B"],
        "name": ["ST Later", "Normal Now"],
        "date": [as_of, as_of],
        "close": [10.0, 20.0],
    })
    result = _historical_engine().run(
        "historical", _historical_context(panel, matrix=False)
    )
    assert [row["symbol"] for row in result.rows] == ["A"]


def test_historical_strategy_scan_uses_effective_status_in_matrix_path():
    class Always:
        def required_fields(self):
            return frozenset({"close"})

        def required_warmup_bars(self, params):
            return 1

        def compute_signals(self, market, params):
            return make_signal_matrix(
                market.shape,
                entry=np.ones(market.shape, dtype=np.uint8),
                score=np.ones(market.shape, dtype=np.float32),
            )

    as_of = date(2025, 1, 2)
    panel = pl.DataFrame({
        "symbol": ["A", "B"],
        "name": ["ST Later", "Normal Now"],
        "date": [as_of, as_of],
        "open": [10.0, 20.0],
        "high": [10.0, 20.0],
        "low": [10.0, 20.0],
        "close": [10.0, 20.0],
        "volume": [1000.0, 1000.0],
    })
    engine = _historical_engine(matrix_strategy=Always())
    context = _historical_context(panel, matrix=True)
    shared = engine.build_shared_matrix(
        context, [("historical", engine.get("historical"))]
    )
    assert shared is not None and "st_flag" in shared.fields
    context.market = shared
    result = engine.run("historical", context)
    assert [row["symbol"] for row in result.rows] == ["A"]


def test_historical_screener_context_loads_effective_status(monkeypatch):
    as_of = date(2025, 1, 2)
    history = pl.DataFrame({
        "symbol": ["A", "B"],
        "flag_date": [as_of, as_of],
        "st_flag": [False, True],
    })
    panel = pl.DataFrame({
        "symbol": ["A", "B"],
        "name": ["ST Later", "Normal Now"],
        "date": [as_of, as_of],
        "close": [10.0, 20.0],
    })
    repo = SimpleNamespace(
        get_st_history=lambda: history,
        get_matrix_data_generation=lambda asset_type: "test-generation",
    )
    service = ScreenerService(repo, asset_type="stock")  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_load_enriched_for_date", lambda _: panel)
    engine = _historical_engine()
    context = service.build_strategy_context(
        engine, as_of, ["historical"], overrides_map={}
    )
    assert context.historical_st is True
    assert context.st_history is not None
    assert context.current["st_flag"].to_list() == [False, True]


def test_historical_minute_scan_rejects_st_exclusion_instead_of_using_names():
    engine = _historical_engine()
    strategy = engine.get("historical")
    strategy.execution_backend = "minute_filter"
    strategy.meta["timeframes"] = ["1m"]
    strategy.filter_minute_history_fn = lambda frame, params: frame
    as_of = date(2025, 1, 2)
    context = StrategyDataContext(
        asset_type="stock",
        timeframe="1m",
        as_of=as_of,
        current=pl.DataFrame({
            "symbol": ["A"], "date": [as_of], "name": ["ST Later"],
            "close": [10.0],
        }),
        history=pl.DataFrame({
            "symbol": ["A"], "datetime": [as_of], "close": [10.0],
        }),
        st_history=pl.DataFrame({
            "symbol": ["A"], "flag_date": [as_of], "st_flag": [True],
        }),
        historical_st=True,
    )
    with pytest.raises(ValueError, match="历史分钟"):
        engine.run("historical", context)
