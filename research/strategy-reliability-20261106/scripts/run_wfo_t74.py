from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT / "backend"))

from app.backtest.engine import BacktestEngine  # noqa: E402
from app.backtest.optimizer import StrategyOptimizer  # noqa: E402
from app.backtest.strategy import StrategyBacktestService  # noqa: E402
from app.backtest.walkforward import WalkForwardConfig, WalkForwardService  # noqa: E402
from app.config import settings  # noqa: E402
from app.strategy import config as strategy_config  # noqa: E402
from app.strategy.engine import StrategyEngine  # noqa: E402
from app.tickflow.repository import DataStore, KlineRepository  # noqa: E402

PARITY = PROJECT / ".artifacts/331-parity-20261102"
OUTPUT = (
    PROJECT / "research/strategy-reliability-20261106/results/wfo-t74-baseline.json"
)


def load_params() -> dict:
    database = Path(
        r"D:\stock-limit-up-analyzer-data\dataset-snapshots\660001\dataset.sqlite"
    )
    with sqlite3.connect(database) as connection:
        allowlist = [
            str(row[0]) for row in connection.execute(
                "select eventId from event "
                "where tradeDate >= '2019-01-02' and tradeDate <= '2026-10-12'"
            )
        ]
    increments = json.loads(
        (PARITY / "increment_event_allowlist.json").read_text(encoding="utf-8")
    )
    params = {
        "_event_allowlist": sorted(set(allowlist) | {str(v) for v in increments}),
        "_legacy_preclose_gaps": json.loads(
            (PARITY / "legacy_preclose_gaps.json").read_text(encoding="utf-8")
        ),
        "_legacy_corporate_action_gaps": json.loads(
            (PARITY / "legacy_corporate_action_gaps.json").read_text(encoding="utf-8")
        ),
    }
    return params


def main() -> None:
    started = time.perf_counter()
    store = DataStore(settings.data_dir)
    engine = BacktestEngine(KlineRepository(store))
    strategy_engine = StrategyEngine(
        strategy_dirs=[
            PROJECT / "backend/app/strategy/research",
            settings.data_dir / "strategies/custom",
            settings.data_dir / "strategies/ai",
            settings.data_dir / "strategies/composite",
        ],
        override_loader=lambda sid: strategy_config.load_override(
            settings.data_dir, sid,
        ),
    )
    service = StrategyBacktestService(engine, strategy_engine)
    config = WalkForwardConfig(
        strategy_id="first_limit_pullback_3f_runner_t74",
        symbols=None,
        start=date(2024, 1, 1),
        end=date(2026, 10, 12),
        param_grid={
            "daily_candidates": [3],
            "min_score_pct": [55.0],
            "max_amplitude_pct": [14.0],
        },
        objective="sortino",
        train_days=252,
        test_days=63,
        step_days=63,
        min_trades_oos=10,
        base_params=load_params(),
        backtest_kwargs={
            "matching": "open_t+1",
            "commission_pct": 0.00025,
            "stamp_tax_pct": 0.0005,
            "slippage_bps": 5.0,
            "max_positions": 5,
            "max_exposure_pct": 1.0,
            "initial_capital": 100_000.0,
            "position_sizing": "score_tier",
            "mode": "position",
            "holding_days": 74,
        },
    )
    result = WalkForwardService(
        StrategyOptimizer(service, strategy_engine),
        service,
        strategy_engine,
    ).run(config)
    result["elapsed_seconds_total"] = round(time.perf_counter() - started, 2)
    result["strategy"] = "first_limit_pullback_3f_runner_t74"
    result["period"] = {"start": "2024-01-01", "end": "2026-10-12"}
    result["window_counts"] = {
        "train": 252,
        "test": 63,
        "step": 63,
        "basis": "actual_enriched_trading_days",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    store.db.close()
    print(OUTPUT)
    for fold in result["folds"]:
        print(
            fold["index"],
            fold["train_start"], fold["train_end"],
            fold["test_start"], fold["test_end"],
            fold["oos_stats"].get("total_return"),
            fold["oos_stats"].get("n_trades"),
            fold["statistically_insufficient"],
        )
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
