from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl
import pytest

from app.backtest.engine import MatcherConfig
from app.backtest.matrix import build_market_data_matrix, make_signal_matrix
from app.extensions import (
    BackendExtensionRegistrar,
    BackendExtensionRegistry,
    BacktestCostModel,
    CandidateFilter,
    CoreBacktestCostModel,
    MonitorConditionEvaluator,
    RiskPolicy,
    ScoringPolicy,
    StrategyProvider,
    register_strategy_extension,
    strategy_extension,
)
from app.extensions.strategies import (
    apply_candidate_filter,
    apply_risk_policy,
    build_strategy_policy_context,
)
from app.strategy.engine import (
    StrategyDataContext,
    StrategyDef,
    StrategyEngine,
)
from app.strategy.monitor import _build_condition_mask


@pytest.fixture(autouse=True)
def _isolate_strategy_extensions():
    from app.extensions import strategies

    saved = {kind: dict(items) for kind, items in strategies._KINDS.items()}
    providers_ready = strategies._PROVIDERS_READY
    try:
        yield
    finally:
        strategies._KINDS.clear()
        strategies._KINDS.update(
            {kind: dict(items) for kind, items in saved.items()}
        )
        strategies._PROVIDERS_READY = providers_ready


def _strategy(meta: dict) -> StrategyDef:
    return StrategyDef(
        meta={"asset_types": ["stock"], "timeframes": ["1d"], **meta},
        basic_filter={"enabled": False},
        entry_signals=[],
        exit_signals=[],
        stop_loss=None,
        trailing_stop=None,
        trailing_take_profit_activate=None,
        trailing_take_profit_drawdown=None,
        max_hold_days=None,
        filter_fn=lambda _frame, _params: pl.lit(True),
        filter_history_fn=None,
        lookback_days=1,
        source="custom",
    )


def test_candidate_scoring_and_risk_policies_are_consumed_by_engine() -> None:
    class _Candidate(CandidateFilter):
        def filter_candidates(self, frame, context):
            assert context.strategy_id == "test_strategy_extensions"
            return frame.filter(pl.col("symbol") != "skip")

    class _Risk(RiskPolicy):
        def filter_entries(self, frame, context):
            del context
            return frame.filter(pl.col("risk_ok"))

    class _Score(ScoringPolicy):
        def score(self, frame, context):
            del context
            return frame["close"] * 2

    for kind, impl_id, implementation in (
        ("candidate_filter", "test.candidate", _Candidate()),
        ("risk_policy", "test.risk", _Risk()),
        ("scoring_policy", "test.score", _Score()),
    ):
        register_strategy_extension(kind, impl_id, implementation)

    engine = StrategyEngine(strategy_dirs=[])
    strategy = _strategy({
        "id": "test_strategy_extensions",
        "candidate_filter": "test.candidate",
        "risk_policy": "test.risk",
        "scoring_policy": "test.score",
    })
    engine._strategies[strategy.meta["id"]] = strategy
    frame = pl.DataFrame({
        "symbol": ["keep", "skip", "risk_out"],
        "close": [10.0, 20.0, 30.0],
        "risk_ok": [True, True, False],
        "date": [date(2026, 1, 5)] * 3,
    })

    result = engine.run(
        strategy.meta["id"],
        StrategyDataContext(
            asset_type="stock",
            timeframe="1d",
            as_of=date(2026, 1, 5),
            current=frame,
        ),
    )

    assert [row["symbol"] for row in result.rows] == ["keep"]
    assert result.scores["keep"] == pytest.approx(20.0)


def test_matrix_strategy_policies_are_consumed_by_engine() -> None:
    class _Candidate(CandidateFilter):
        def filter_candidates(self, frame, context):
            del context
            return frame.filter(pl.col("symbol") == "B")

    class _Risk(RiskPolicy):
        def filter_entries(self, frame, context):
            del context
            return frame.filter(pl.col("close") >= 11.0)

    class _Score(ScoringPolicy):
        def score(self, frame, context):
            del context
            return frame["close"] * 2

    class _Matrix:
        def required_fields(self):
            return frozenset({"open", "high", "low", "close", "volume"})

        def required_warmup_bars(self, params):
            del params
            return 1

        def compute_signals(self, market, params):
            del params
            return make_signal_matrix(
                market.shape,
                entry=np.ones(market.shape, dtype=np.uint8),
                score=np.ones(market.shape, dtype=np.float32),
            )

    for kind, impl_id, implementation in (
        ("candidate_filter", "test.matrix-candidate", _Candidate()),
        ("risk_policy", "test.matrix-risk", _Risk()),
        ("scoring_policy", "test.matrix-score", _Score()),
    ):
        register_strategy_extension(kind, impl_id, implementation)

    panel = pl.DataFrame([
        {
            "symbol": symbol,
            "date": date(2026, 1, day),
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000.0,
        }
        for day, close_a, close_b in (
            (1, 9.0, 10.0),
            (2, 10.0, 11.0),
            (3, 11.0, 12.0),
        )
        for symbol, close in (("A", close_a), ("B", close_b))
    ])
    strategy = StrategyDef(
        meta={
            "id": "test_matrix_extensions",
            "asset_types": ["stock"],
            "timeframes": ["1d"],
            "candidate_filter": "test.matrix-candidate",
            "risk_policy": "test.matrix-risk",
            "scoring_policy": "test.matrix-score",
        },
        basic_filter={"enabled": False},
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
        execution_backend="matrix_native",
        matrix_strategy=_Matrix(),
    )
    engine = StrategyEngine(strategy_dirs=[])
    engine._strategies[strategy.meta["id"]] = strategy

    result = engine.run(
        strategy.meta["id"],
        StrategyDataContext(
            asset_type="stock",
            timeframe="1d",
            as_of=date(2026, 1, 3),
            current=panel,
            history=panel,
            market=build_market_data_matrix(panel),
        ),
    )

    assert [row["symbol"] for row in result.rows] == ["B"]
    assert result.scores == {"B": pytest.approx(24.0)}


def test_scoring_policy_rejects_non_finite_scores() -> None:
    class _Score(ScoringPolicy):
        def score(self, frame, context):
            del context
            return pl.Series([float("nan")] * frame.height)

    register_strategy_extension("scoring_policy", "test.non-finite", _Score())
    engine = StrategyEngine(strategy_dirs=[])
    strategy = _strategy({
        "id": "test_non_finite_score",
        "scoring_policy": "test.non-finite",
    })
    engine._strategies[strategy.meta["id"]] = strategy

    with pytest.raises(ValueError, match="有限非空分值"):
        engine.run(
            strategy.meta["id"],
            StrategyDataContext(
                asset_type="stock",
                timeframe="1d",
                as_of=date(2026, 1, 5),
                current=pl.DataFrame({
                    "symbol": ["A"],
                    "close": [10.0],
                    "date": [date(2026, 1, 5)],
                }),
            ),
        )


def test_engine_rejects_in_place_candidate_mutation() -> None:
    class _Mutating(CandidateFilter):
        def filter_candidates(self, frame, context):
            del context
            frame.replace_column(
                frame.columns.index("close"),
                pl.Series("close", [999.0] * frame.height),
            )
            return frame

    register_strategy_extension("candidate_filter", "test.engine-in-place", _Mutating())
    engine = StrategyEngine(strategy_dirs=[])
    strategy = _strategy({
        "id": "test_engine_in_place",
        "candidate_filter": "test.engine-in-place",
    })
    engine._strategies[strategy.meta["id"]] = strategy

    with pytest.raises(ValueError, match="只能保留输入中的原始行"):
        engine.run(
            strategy.meta["id"],
            StrategyDataContext(
                asset_type="stock",
                timeframe="1d",
                as_of=date(2026, 1, 5),
                current=pl.DataFrame({
                    "symbol": ["A", "B"],
                    "close": [10.0, 20.0],
                    "date": [date(2026, 1, 5)] * 2,
                }),
            ),
        )


def test_engine_allows_null_candidate_rows() -> None:
    class _Identity(CandidateFilter):
        def filter_candidates(self, frame, context):
            del context
            return frame

    register_strategy_extension("candidate_filter", "test.engine-null", _Identity())
    engine = StrategyEngine(strategy_dirs=[])
    strategy = _strategy({
        "id": "test_engine_null",
        "candidate_filter": "test.engine-null",
    })
    engine._strategies[strategy.meta["id"]] = strategy

    result = engine.run(
        strategy.meta["id"],
        StrategyDataContext(
            asset_type="stock",
            timeframe="1d",
            as_of=date(2026, 1, 5),
            current=pl.DataFrame({
                "symbol": ["A", "B"],
                "close": [10.0, 20.0],
                "ma60": pl.Series([None, None], dtype=pl.Float64),
                "date": [date(2026, 1, 5)] * 2,
            }),
        ),
    )

    assert result.total == 2
    assert [row["symbol"] for row in result.rows] == ["A", "B"]


class _StaticFilter(CandidateFilter):
    def __init__(self, result: pl.DataFrame) -> None:
        self._result = result

    def filter_candidates(self, frame, context):
        del frame, context
        return self._result


class _InPlaceMutator(CandidateFilter, RiskPolicy):
    def __init__(self, column: str, value) -> None:
        self.column = column
        self.value = value

    def _mutate(self, frame: pl.DataFrame) -> pl.DataFrame:
        frame.replace_column(
            frame.columns.index(self.column),
            pl.Series(self.column, [self.value] * frame.height),
        )
        return frame

    def filter_candidates(self, frame, context):
        del context
        return self._mutate(frame)

    def filter_entries(self, frame, context):
        del context
        return self._mutate(frame)


@pytest.mark.parametrize(
    "kind,column,value",
    [
        ("candidate_filter", "close", 999.0),
        ("candidate_filter", "symbol", "OUTSIDE"),
        ("risk_policy", "close", 999.0),
        ("risk_policy", "symbol", "OUTSIDE"),
    ],
    ids=[
        "candidate-value",
        "candidate-symbol",
        "risk-value",
        "risk-symbol",
    ],
)
def test_filters_reject_in_place_mutation(kind: str, column: str, value) -> None:
    implementation_id = f"test.in-place-{kind}-{column}"
    register_strategy_extension(kind, implementation_id, _InPlaceMutator(column, value))
    source = pl.DataFrame({"symbol": ["A", "B"], "close": [10.0, 20.0]})
    expected = source[column].to_list()
    apply = apply_candidate_filter if kind == "candidate_filter" else apply_risk_policy

    with pytest.raises(ValueError, match="只能保留输入中的原始行"):
        apply(
            source,
            implementation_id,
            build_strategy_policy_context(asset_type="stock", strategy_id="test"),
        )

    assert source[column].to_list() == expected


@pytest.mark.parametrize(
    "result",
    [
        pl.DataFrame({"symbol": ["A", "A"], "close": [10.0, 10.0]}),
        pl.DataFrame({"symbol": ["A", "B"], "close": [10.0, 99.0]}),
        pl.DataFrame({"symbol": ["OUTSIDE", "B"], "close": [1.0, 20.0]}),
    ],
    ids=["duplicate", "rewritten-value", "outside-input"],
)
def test_candidate_filter_rejects_rows_not_preserved_from_input(
    result: pl.DataFrame,
) -> None:
    register_strategy_extension("candidate_filter", "test.bad-rows", _StaticFilter(result))
    source = pl.DataFrame({"symbol": ["A", "B"], "close": [10.0, 20.0]})

    with pytest.raises(ValueError, match="只能保留输入中的原始行"):
        apply_candidate_filter(
            source,
            "test.bad-rows",
            build_strategy_policy_context(asset_type="stock", strategy_id="test"),
        )


def test_candidate_filter_allows_reordered_subset_from_input() -> None:
    source = pl.DataFrame({"symbol": ["A", "B", "C"], "close": [10.0, 20.0, 30.0]})
    register_strategy_extension(
        "candidate_filter",
        "test.reordered-subset",
        _StaticFilter(source.filter(pl.col("symbol") != "B").sort("symbol", descending=True)),
    )

    result = apply_candidate_filter(
        source,
        "test.reordered-subset",
        build_strategy_policy_context(asset_type="stock", strategy_id="test"),
    )

    assert result["symbol"].to_list() == ["C", "A"]


@pytest.mark.parametrize(
    "nulls",
    [[None, 19.0], [None, None]],
    ids=["partial-null", "all-null"],
)
def test_candidate_filter_allows_null_rows(nulls: list[float | None]) -> None:
    source = pl.DataFrame({
        "symbol": ["A", "B"],
        "close": [10.0, 20.0],
        "ma60": pl.Series(nulls, dtype=pl.Float64),
    })
    register_strategy_extension(
        "candidate_filter",
        "test.null-rows",
        _StaticFilter(source),
    )

    result = apply_candidate_filter(
        source,
        "test.null-rows",
        build_strategy_policy_context(asset_type="stock", strategy_id="test"),
    )

    assert result.equals(source)


def test_candidate_filter_allows_empty_result() -> None:
    source = pl.DataFrame({"symbol": ["A", "B"], "close": [10.0, 20.0]})
    register_strategy_extension(
        "candidate_filter",
        "test.empty-result",
        _StaticFilter(source.head(0)),
    )

    result = apply_candidate_filter(
        source,
        "test.empty-result",
        build_strategy_policy_context(asset_type="stock", strategy_id="test"),
    )

    assert result.height == 0


def test_candidate_filter_rejects_null_value_rewrite() -> None:
    source = pl.DataFrame({
        "symbol": ["A", "B"],
        "close": [10.0, 20.0],
        "ma60": [None, 19.0],
    })
    register_strategy_extension(
        "candidate_filter",
        "test.null-rewrite",
        _StaticFilter(source.with_columns(pl.lit(1.0).alias("ma60"))),
    )

    with pytest.raises(ValueError, match="只能保留输入中的原始行"):
        apply_candidate_filter(
            source,
            "test.null-rewrite",
            build_strategy_policy_context(asset_type="stock", strategy_id="test"),
        )


def test_risk_policy_rejects_duplicated_input_rows() -> None:
    source = pl.DataFrame({"symbol": ["A", "B"], "close": [10.0, 20.0]})

    class _Risk(RiskPolicy):
        def filter_entries(self, frame, context):
            del frame, context
            return pl.concat([source.head(1), source.head(1)])

    register_strategy_extension("risk_policy", "test.duplicate-risk", _Risk())

    with pytest.raises(ValueError, match="只能保留输入中的原始行"):
        apply_risk_policy(
            source,
            "test.duplicate-risk",
            build_strategy_policy_context(asset_type="stock", strategy_id="test"),
        )


def test_backtest_cost_model_is_delegated() -> None:
    class _Cost(BacktestCostModel):
        def buy_cost_pct(self, config):
            del config
            return 0.01

        def sell_cost_pct(self, config):
            del config
            return 0.02

    model = _Cost()
    assert MatcherConfig(cost_model=model).buy_cost_pct() == pytest.approx(0.01)
    assert MatcherConfig(cost_model=model).sell_cost_pct() == pytest.approx(0.02)
    core = MatcherConfig(commission_pct=0.001, stamp_tax_pct=0.002, slippage_bps=3)
    wrapper = CoreBacktestCostModel()
    assert wrapper.buy_cost_pct(core) == pytest.approx(core._core_buy_cost_pct())
    assert wrapper.sell_cost_pct(core) == pytest.approx(core._core_sell_cost_pct())


def test_strategy_provider_is_discovered_at_engine_reload() -> None:
    class _Provider(StrategyProvider):
        def strategy_definitions(self):
            return (_strategy({"id": "test_provider_strategy"}),)

    register_strategy_extension(
        "strategy_provider",
        "test.provider",
        _Provider(),
    )

    engine = StrategyEngine(strategy_dirs=[])

    assert engine.has("test_provider_strategy")


def test_monitor_condition_evaluator_participates_in_mask() -> None:
    class _Evaluator(MonitorConditionEvaluator):
        def evaluate(self, frame, condition, context):
            assert context.api_version == 1
            return frame["close"] > float(condition["threshold"])

    register_strategy_extension(
        "monitor_condition_evaluator",
        "test.monitor",
        _Evaluator(),
    )
    frame = pl.DataFrame({
        "symbol": ["a", "b"],
        "close": [9.0, 11.0],
    })

    result = _build_condition_mask(
        frame,
        [{"evaluator": "test.monitor", "threshold": 10.0}],
        "and",
    )

    assert result["symbol"].to_list() == ["b"]


def test_registrar_rejects_incompatible_policy_version_atomically() -> None:
    class _BadFilter(CandidateFilter):
        api_version = 999

        def filter_candidates(self, frame, context):
            del context
            return frame

    registry = BackendExtensionRegistry()
    registrar = BackendExtensionRegistrar("test.policy-version", api_version=1)
    registrar.register_candidate_filter("test.bad-version", _BadFilter())

    with pytest.raises(ValueError, match="API v999"):
        registry.register(registrar)

    assert strategy_extension("candidate_filter", "test.bad-version") is None
