"""Activation and peak drawdown are independent risk thresholds."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.strategy import StrategyBacktestConfig, StrategyBacktestService
from app.strategy.engine import StrategyEngine

REPO_ROOT = Path(__file__).resolve().parents[3]


def _service() -> StrategyBacktestService:
    return StrategyBacktestService(
        BacktestEngine(repo=None),
        StrategyEngine(strategy_dirs=[REPO_ROOT / "backend" / "tests" / "fixtures" / "strategies"]),
    )


def _config(activate, drawdown) -> StrategyBacktestConfig:
    return StrategyBacktestConfig(
        strategy_id="macd_golden",
        symbols=None,
        start=date(2024, 1, 1),
        end=date(2024, 3, 1),
        overrides={
            "trailing_take_profit_activate": activate,
            "trailing_take_profit_drawdown": drawdown,
        },
    )


@pytest.mark.parametrize(("activate", "drawdown"), [(0.03, 0.08), (0.05, 0.10), (0.10, 0.05)])
def test_independent_thresholds_pass_validation(monkeypatch, activate, drawdown):
    service = _service()

    class DataLoadReachedError(Exception):
        pass

    def load(*args, **kwargs):
        raise DataLoadReachedError

    monkeypatch.setattr(service.engine, "load_panel_for_backtest", load)
    monkeypatch.setattr(service.engine, "load_market_data_matrix_for_backtest", load)
    with pytest.raises(DataLoadReachedError):
        service.run(_config(activate, drawdown))


def test_drawdown_not_greater_than_activate_passes_validation():
    """回撤 ≤ 激活 → 校验放行(后续数据阶段是否失败与本回归点无关)。"""
    outcome = ""
    try:
        outcome = _service().run(_config(0.10, 0.05)).error or ""
    except Exception as exc:  # noqa: BLE001 — repo=None, 数据阶段异常在所难免
        outcome = str(exc)
    assert "移动止盈回撤" not in outcome
