"""核对连续账户 WFO 结果的自洽性, 不重新回测。

检查的是账户链条本身 (权益衔接、折边界持仓、复利一致性), 不能证明策略有效。
"""
from __future__ import annotations

import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"


def _load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def main() -> int:
    comparison = _load("wfo-t74-comparison.json")
    continuous = _load("wfo-t74-continuous.json")
    reset = _load("wfo-t74-reset.json")
    account = continuous["summary"]["continuous_account"]
    stats = account["stats"]
    boundaries = account["boundaries"]

    checks: dict[str, object] = {}
    chain_ok = all(
        abs(boundaries[i]["equity_start"] - boundaries[i - 1]["equity_end"]) < 0.01
        for i in range(1, len(boundaries))
    )
    checks["equity_chain_continuous"] = chain_ok
    checks["first_fold_starts_at_initial_capital"] = (
        abs(boundaries[0]["equity_start"] - stats["initial_capital"]) < 0.01
    )
    checks["final_equity_matches_last_boundary"] = (
        abs(stats["final_equity"] - boundaries[-1]["equity_end"]) < 0.01
    )
    compounded = 1.0
    for item in boundaries:
        compounded *= 1.0 + item["segment_return"]
    checks["compounded_segments_match_total"] = (
        abs(compounded - 1.0 - stats["total_return"]) < 5e-4
    )
    checks["no_duplicate_dates"] = account["duplicate_dates"] == 0
    checks["no_early_stop"] = account["stopped_early"] is None
    carry_chain_ok = all(
        boundaries[i]["carried_in_positions"] == boundaries[i - 1]["carried_out_positions"]
        for i in range(1, len(boundaries))
    )
    checks["carried_positions_chain"] = carry_chain_ok
    checks["some_boundaries_carry_positions"] = sum(
        1 for item in boundaries if item["carried_in_positions"] > 0
    ) > 0
    # 期末头寸独立核对: 现金 + 持仓市值 = 权益, 且未平仓交易数 = 实际持仓数。
    final_cash = float(account.get("final_cash") or 0.0)
    final_positions = int(account.get("final_positions") or 0)
    final_market_value = float(account.get("final_market_value") or 0.0)
    checks["final_cash_plus_market_value_equals_equity"] = (
        abs(final_cash + final_market_value - stats["final_equity"]) < 0.01
    )
    checks["final_positions_match_open_at_end"] = (
        final_positions == int(stats["open_at_end_count"])
    )
    checks["last_boundary_positions_match_final"] = (
        boundaries[-1]["carried_out_positions"] == final_positions
    )
    checks["trade_counts_add_up"] = (
        int(stats["completed_trade_count"]) + int(stats["open_at_end_count"])
        == int(stats["n_trades"])
    )
    checks["fold_trade_counts_add_up"] = (
        sum(item["n_trades"] for item in account["open_at_end_by_fold"])
        == int(stats["n_trades"])
    )
    checks["open_trades_only_from_last_fold"] = (
        sum(item["open_at_end"] for item in account["open_at_end_by_fold"])
        == int(stats["open_at_end_count"])
        and all(item["open_at_end"] == 0 for item in account["open_at_end_by_fold"][:-1])
    )
    checks["no_duplicate_trade_records"] = (
        int(account["trade_lifecycle"]["duplicate_trade_records"]) == 0
    )
    checks["engine_invariants_all_true"] = all(account["invariants"].values())
    checks["reset_has_no_continuous_account"] = reset.get("continuous_account") is None
    checks["reset_return_kind_is_diagnostic"] = (
        reset["summary"]["return_kind"]
        == "compounded_fold_returns_not_continuous_account"
    )
    checks["continuous_return_differs_from_reset"] = (
        abs(
            stats["total_return"]
            - reset["summary"]["compounded_oos_return"]
        ) > 1e-6
    )
    checks["continuous_total_trades"] = stats["n_trades"]
    checks["reset_total_trades"] = sum(
        fold["oos_stats"]["n_trades"] for fold in reset["folds"]
    )
    checks["final_cash"] = final_cash
    checks["final_positions"] = final_positions
    checks["final_market_value"] = final_market_value
    checks["final_equity"] = stats["final_equity"]
    checks["open_at_end_by_fold"] = account["open_at_end_by_fold"]
    checks["trade_lifecycle"] = account["trade_lifecycle"]
    checks["boundaries"] = [
        {
            "index": item["index"],
            "equity": [item["equity_start"], item["equity_end"]],
            "segment_return": item["segment_return"],
            "carried_in": item["carried_in_positions"],
            "carried_out": item["carried_out_positions"],
        }
        for item in boundaries
    ]
    checks["continuous_total_return"] = stats["total_return"]
    checks["reset_compounded_return"] = comparison["reset_summary"]["compounded_oos_return"]
    passed = all(
        value is True
        for key, value in checks.items()
        if isinstance(value, bool)
    )
    checks["passed"] = passed
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
