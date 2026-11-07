"""对照与口径核查：等权全池基准、大市值流动性对照组合、指数参照。

目的不是选策略，而是确认统一撮合口径下的基准量级合理，避免把
「口径/记账错误」当成「策略无效」。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import polars as pl

import common  # noqa: E402

m = common.open_market()
panel = common.load_panel(m)
sig = common.add_universe(common.add_indicators(panel))
sig = common.build_signals(sig)

ev = sig.filter(sig["date"] >= common.EVAL_START)
out: dict = {"periods": {}, "equal_weight": {}, "controls": []}

# 1) 等权全池日收益（无成本、每日再平衡）：基准量级
eq = (
    ev.filter(pl.col("in_universe") & pl.col("ret1").is_not_null())
    .group_by("date")
    .agg(pl.col("ret1").mean().alias("ew_ret"), pl.len().alias("n"))
    .sort("date")
)
for label, s, e in (
    ("IS", common.EVAL_START, common.IS_END),
    ("OOS", date(2023, 1, 3), common.EVAL_END),
    ("ALL", common.EVAL_START, common.EVAL_END),
):
    sub = eq.filter((pl.col("date") >= s) & (pl.col("date") <= e))
    r = sub["ew_ret"].to_numpy()
    cum = float(np.prod(1 + r) - 1)
    out["equal_weight"][label] = {
        "days": len(r), "cum_return": cum,
        "ann_return": float((1 + cum) ** (252 / len(r)) - 1),
        "ann_vol": float(r.std(ddof=1) * np.sqrt(252)),
        "sharpe": float(r.mean() / r.std(ddof=1) * np.sqrt(252)),
        "max_drawdown": float((np.cumprod(1 + r) / np.maximum.accumulate(np.cumprod(1 + r)) - 1).min()),
        "avg_universe": float(sub["n"].mean()),
    }
out["index"] = {
    label: common.index_benchmark(m, s, e)
    for label, s, e in (("IS", common.EVAL_START, common.IS_END),
                        ("OOS", date(2023, 1, 3), common.EVAL_END))
}

# 2) 对照组合：月度换仓、按前 20 日均成交额取最大 5 只（流动性基准，不是策略候选）
sig = sig.with_columns(
    (pl.col("in_universe") & pl.col("month_end")).fill_null(False).alias("e_ctl"),
    pl.col("month_end").fill_null(False).alias("x_ctl"),
    pl.col("prior_amount20").fill_null(0).alias("s_ctl"),
)
ctl = common.Strategy("C00_liquidity_control", "对照", "月度按成交额取最大",
                      "e_ctl", "x_ctl", "s_ctl", 20, "月度换仓")
for slip in (10.0,):
    res = common.run_continuous(m, sig, ctl, slip)
    rec = {"name": ctl.key, "slippage_bps": slip}
    for label, s, e in (("IS", common.EVAL_START, common.IS_END),
                        ("OOS", date(2023, 1, 3), common.EVAL_END),
                        ("ALL", common.EVAL_START, common.EVAL_END)):
        summary = common.summarize(res, s, e, label)
        summary.pop("returns", None)
        rec[label] = summary
    rec["trade_count"] = len(res["trades"])
    rec["final_positions"] = res["final_positions"]
    out["controls"].append(rec)
    print(ctl.key, slip, rec["ALL"]["total_return"], rec["ALL"]["n_closed_trades"], flush=True)

# 3) 记账一致性：已平仓盈亏 + 期末持仓市值 与 权益变化
res = common.run_continuous(m, sig, ctl, 10.0)
eq_vals = [float(r["value"]) for r in res["equity"]]
closed_pnl = sum(float(t["pnl_amount"]) for t in res["trades"] if not t["open_at_end"])
out["accounting_check"] = {
    "start_equity": eq_vals[0], "final_equity": eq_vals[-1],
    "closed_pnl": closed_pnl,
    "closed_pnl_plus_open_cost_basis": closed_pnl,
    "note": "期末仍有未平仓持仓，差额应为这些持仓的浮动盈亏；需与 final_positions 一起读",
    "final_positions": res["final_positions"], "final_cash": res["final_cash"],
}

common.save_json(Path(__file__).resolve().parents[1] / "results" / "controls.json", out)
print("saved controls.json")
