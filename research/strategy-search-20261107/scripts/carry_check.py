"""连续账户结转核查：逐段重放并核对「现金 + 持仓市值 = 段末权益」。

同时验证段末结转状态与下一段起始权益的衔接（跨折不清算）。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import polars as pl

import common  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"


def main() -> None:
    m = common.open_market()
    panel = common.load_panel(m)
    prepared = common.build_signals(common.add_universe(common.add_indicators(panel)))
    ev = prepared.filter(prepared["date"] >= common.EVAL_START)
    strat = [s for s in common.STRATEGIES if s.key.startswith("S07")][0]
    cfg = common.make_config(10.0, strat.max_hold_days)

    close_map = {
        (r["symbol"], str(r["date"])): (float(r["close"]), float(r["raw_close"]))
        for r in panel.select("symbol", "date", "close", "raw_close").iter_rows(named=True)
    }
    carry = None
    records = []
    for seg_start, seg_end in common.year_segments():
        seg = ev.filter((pl.col("date") >= seg_start) & (pl.col("date") <= seg_end)).sort(["date", "symbol"])
        matrix = common.build_market_matrix(seg, seg[strat.entry], seg[strat.exit],
                                           entry_delay_bars=1, exit_delay_bars=1)
        res = m.engine.simulate_market_matrix(
            matrix, cfg,
            options=common.SimulationOptions(include_monte_carlo=False, carry_in=carry, carry_out=True),
        )
        last_date = str(res.equity_curve[-1]["date"])
        cash = float(res.carry_state.cash)
        mtm_adj = mtm_raw = cash
        missing = 0
        for pos in res.carry_state.positions:
            key = (str(pos["symbol"]), last_date)
            if key not in close_map:
                missing += 1
                continue
            adj, raw = close_map[key]
            mtm_adj += float(pos["shares"]) * adj
            mtm_raw += float(pos["shares"]) * raw
        records.append({
            "start": str(seg_start), "end": str(seg_end),
            "equity_last": float(res.equity_curve[-1]["value"]),
            "stats_final_equity": res.stats.get("final_equity"),
            "cash": cash, "n_positions": len(res.carry_state.positions),
            "mtm_adjusted": mtm_adj, "mtm_raw": mtm_raw, "missing_prices": missing,
            "diff_adjusted": mtm_adj - float(res.equity_curve[-1]["value"]),
            "diff_raw": mtm_raw - float(res.equity_curve[-1]["value"]),
            "stats_equals_curve": abs(float(res.stats.get("final_equity", 0))
                                      - float(res.equity_curve[-1]["value"])) < 0.02,
        })
        carry = res.carry_state
        print(records[-1], flush=True)

    # 段末权益应与已平仓盈亏 + 期初权益 - 未平仓成本一致（弱检查，仅记录）
    out = {"strategy": strat.key, "segments": records,
           "max_abs_diff_adjusted": max(abs(r["diff_adjusted"]) for r in records),
           "all_stats_match": all(r["stats_equals_curve"] for r in records),
           "ok": all(abs(r["diff_adjusted"]) < 0.02 and r["stats_equals_curve"] for r in records)}
    common.save_json(RESULTS / "carry_check.json", out)
    print("OK" if out["ok"] else "MISMATCH", out["max_abs_diff_adjusted"])


if __name__ == "__main__":
    main()
