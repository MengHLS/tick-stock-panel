from __future__ import annotations

from app.backtest import result_store
from app.backtest.result_read import BacktestResultReadAdapter


def _result(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "config": {
            "strategy_id": "demo",
            "start": "2025-01-02",
            "end": "2025-01-31",
            "mode": "position",
            "asset_type": "stock",
        },
        "strategy_info": {"id": "demo", "name": "演示策略"},
        "provenance": {"algorithm_version": "strategy_backtest_v2"},
        "stats": {
            "total_return": 0.1,
            "annual_return": 0.2,
            "max_drawdown": -0.05,
            "sharpe": 1.2,
            "win_rate": 0.6,
            "n_trades": 3,
        },
        "equity_curve": [],
        "trades": [],
    }


def test_result_read_returns_saved_summary_and_deep_copied_detail(tmp_path) -> None:
    result_store.clear_completed_runs()
    result_store.register_completed_run(_result("run-result-read"))
    saved = result_store.save_completed_result(tmp_path, run_id="run-result-read")

    adapter = BacktestResultReadAdapter(tmp_path)
    listing = adapter.list_saved()

    assert listing["total"] == 1
    assert listing["items"][0]["saved_id"] == saved["saved_id"]
    detail = adapter.get_saved(saved["saved_id"])
    detail["result"]["stats"]["n_trades"] = 999
    assert adapter.get_saved(saved["saved_id"])["result"]["stats"]["n_trades"] == 3


def test_result_read_completed_run_is_a_snapshot(tmp_path) -> None:
    result_store.clear_completed_runs()
    result_store.register_completed_run(_result("run-result-copy"))

    adapter = BacktestResultReadAdapter(tmp_path)
    first = adapter.get_completed("run-result-copy")
    assert first is not None
    first["stats"]["n_trades"] = 999

    second = adapter.get_completed("run-result-copy")
    assert second is not None
    assert second["stats"]["n_trades"] == 3
    assert adapter.get_completed("missing") is None
