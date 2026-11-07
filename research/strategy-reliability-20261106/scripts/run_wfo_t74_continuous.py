"""T74 固定参数 WFO: 连续账户 vs 逐折独立账户 (同成本、同宇宙、同参数)。

只做对照, 不调参、不改成本。输出两份 JSON + 一份对比摘要。
"""
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
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "results"


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
    return {
        "_event_allowlist": sorted(set(allowlist) | {str(v) for v in increments}),
        "_legacy_preclose_gaps": json.loads(
            (PARITY / "legacy_preclose_gaps.json").read_text(encoding="utf-8")
        ),
        "_legacy_corporate_action_gaps": json.loads(
            (PARITY / "legacy_corporate_action_gaps.json").read_text(encoding="utf-8")
        ),
    }


def build_service() -> tuple[WalkForwardService, DataStore]:
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
    return (
        WalkForwardService(
            StrategyOptimizer(service, strategy_engine),
            service,
            strategy_engine,
        ),
        store,
    )


def build_config(base_params: dict, *, continuous: bool) -> WalkForwardConfig:
    return WalkForwardConfig(
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
        base_params=base_params,
        continuous_account=continuous,
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


def _run(base_params: dict, *, continuous: bool) -> dict:
    service, store = build_service()
    config = build_config(base_params, continuous=continuous)
    started = time.perf_counter()
    try:
        result = service.run(config)
    finally:
        store.db.close()
    result["elapsed_seconds_total"] = round(time.perf_counter() - started, 2)
    result["strategy"] = config.strategy_id
    result["period"] = {"start": "2024-01-01", "end": "2026-10-12"}
    result["window_counts"] = {
        "train": 252, "test": 63, "step": 63,
        "basis": "actual_enriched_trading_days",
    }
    result["continuous_account_requested"] = continuous
    return result


def _write(name: str, payload: dict) -> None:
    (OUTPUT_DIR / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    params = load_params()
    continuous = _run(params, continuous=True)
    reset = _run(params, continuous=False)
    _write("wfo-t74-continuous.json", continuous)
    _write("wfo-t74-reset.json", reset)
    report = {
        "continuous": continuous.get("summary", {}).get("continuous_account"),
        "reset_summary": {
            key: reset.get("summary", {}).get(key)
            for key in (
                "compounded_oos_return",
                "return_kind",
                "avg_is_objective",
                "avg_oos_objective",
                "degradation",
                "consistency",
            )
        },
        "continuous_fold_returns": [
            {
                "index": fold["index"],
                "test_start": fold["test_start"],
                "test_end": fold["test_end"],
                "segment_return": fold["oos_stats"]["total_return"],
                "carried_in_positions": fold.get("carried_in_positions"),
                "carried_out_positions": fold.get("carried_out_positions"),
                "n_trades": fold["oos_stats"].get("n_trades"),
            }
            for fold in continuous.get("folds", [])
        ],
        "elapsed_seconds": {
            "continuous": continuous.get("elapsed_seconds_total"),
            "reset": reset.get("elapsed_seconds_total"),
        },
    }
    _write("wfo-t74-comparison.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
