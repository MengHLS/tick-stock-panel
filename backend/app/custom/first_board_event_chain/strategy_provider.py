"""Discover optional first-board research strategies."""
from __future__ import annotations

from pathlib import Path

from app.extensions.strategies import StrategyProvider


class FirstBoardEventChainStrategyProvider(StrategyProvider):
    provider_id = "official.first-board-event-chain.strategies"

    def strategy_definitions(self):
        from app.strategy.engine import StrategyEngine

        paths = (
            Path(__file__).with_name("strategy_rebreak.py"),
            Path(__file__).with_name("first_limit_pullback_3f_runner_t74.py"),
        )
        return tuple(StrategyEngine._load_file(path) for path in paths)


PROVIDER = FirstBoardEventChainStrategyProvider()
STRATEGY_PROVIDERS = (PROVIDER,)
