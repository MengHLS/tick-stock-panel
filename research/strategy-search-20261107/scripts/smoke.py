"""冒烟测试：数据加载、指标、信号分布与单段撮合速度。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

t0 = time.time()
m = common.open_market()
print("open_market", round(time.time() - t0, 1), "s", flush=True)

t0 = time.time()
panel = common.load_panel(m)
print("load_panel rows", panel.height, "symbols", panel["symbol"].n_unique(),
      "dates", panel["date"].n_unique(), round(time.time() - t0, 1), "s", flush=True)

t0 = time.time()
ind = common.add_indicators(panel)
print("indicators", round(time.time() - t0, 1), "s", flush=True)

t0 = time.time()
sig = common.add_universe(ind)
print("universe", round(time.time() - t0, 1), "s", flush=True)

t0 = time.time()
sig = common.build_signals(sig)
print("signals", round(time.time() - t0, 1), "s", flush=True)

ev = sig.filter(pl_date := (common.EVAL_START.isoformat() <= sig["date"].cast(str))
                if False else True)
ev = sig.filter(sig["date"] >= common.EVAL_START)
print("eval rows", ev.height)
print("universe per day (median)",
      float(ev.group_by("date").agg(common.pl.col("in_universe").sum().alias("n"))["n"].median()))
for s in common.STRATEGIES:
    n = int(ev[s.entry].sum())
    x = int(ev[s.exit].sum())
    print(f"{s.key:26s} entry={n:7d} exit={x:7d}", flush=True)

# 单段速度测试：2024 年，布林带策略，10bp
strat = [s for s in common.STRATEGIES if s.key.startswith("S05")][0]
cfg = common.make_config(10.0, strat.max_hold_days)
from datetime import date
seg = ev.filter((ev["date"] >= date(2024, 1, 1)) & (ev["date"] <= date(2024, 12, 31))).sort(["date", "symbol"])
t0 = time.time()
matrix = common.build_market_matrix(seg, seg[strat.entry], seg[strat.exit],
                                   entry_delay_bars=1, exit_delay_bars=1)
t1 = time.time()
res = m.engine.simulate_market_matrix(
    matrix, cfg, options=common.SimulationOptions(include_monte_carlo=False, carry_out=True))
t2 = time.time()
print("matrix", round(t1 - t0, 1), "s sim", round(t2 - t1, 1), "s",
      "total_return", res.stats["total_return"], "trades", len(res.trades),
      "carry", res.carry_state is not None, flush=True)
print("slippage-free sanity: signals", int(seg[strat.entry].sum()))
