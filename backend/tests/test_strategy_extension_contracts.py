from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from app.backtest.engine import MatcherConfig
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
