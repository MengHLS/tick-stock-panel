"""Step 4 (acceptance ②): boundary study for the cross_down event-vs-level semantics.

Question: inside the full window, are there cases where the LEVEL form (`cross_down = fast < slow`)
is true while the held position could NOT exit that day (limit-down / suspension, i.e.
blocked_exit_days > 0 or an equivalent flag), and where the EVENT form
(`(fast < slow) & (prev_fast >= prev_slow)`) is already false?

Method (all numbers come from the real production pipeline; nothing hand-rolled for execution):
  1. Run the production strategy once with an evidence hook that keeps the MarketDataMatrix and
     the SignalMatrix the engine actually consumed (same hook signature as
     backend/app/backtest/evidence.py: check_matrix(market, signals, evaluate)).
  2. Rebuild both semantics from the same features (ma20/ma60 via matrix_feature + valid_shift)
     and prove which one reproduces signals.exit -> that is what the file computes.
  3. Count level-only cells (level true, event false) over the loaded window.
  4. For every a0 (before) trade: locate the latched exit_signal_date, classify whether that day
     is an event day or a level-only day, count level-only days inside the holding window, and
     pull the matching a1 (after) trade to show the two runs agree trade by trade.
  5. For trades whose exit was blocked (blocked_exit_days > 0) dump a day-by-day grid:
     date / level / event / tradable / limit_down_locked over [entry_date, exit_date].
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
PROJECT = PARENT.parents[1]
DATA_ROOT = PARENT / "data_root"
os.environ["DATA_DIR"] = str(DATA_ROOT)
sys.path.insert(0, str(PROJECT / "backend"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402
from app.backtest.engine import BacktestEngine  # noqa: E402
from app.backtest.matrix import matrix_feature, valid_shift  # noqa: E402
from app.backtest.strategy import (  # noqa: E402
    StrategyBacktestConfig,
    StrategyBacktestService,
)
from app.config import settings  # noqa: E402
from app.strategy.engine import StrategyEngine  # noqa: E402
from app.tickflow.repository import DataStore, KlineRepository  # noqa: E402

RESULTS = HERE / "results"


class MatrixCapture:
    """evidence hook: keep matrix + signals, no-op everything else."""

    def __init__(self) -> None:
        self.market = None
        self.signals = None

    def check_matrix(self, market, signals, evaluate=None) -> None:
        self.market = market
        self.signals = signals

    def check_panel(self, baseline, evaluate=None) -> None:
        return None

    def record_frame(self, name, frame) -> None:
        return None

    def __getattr__(self, item):
        def _noop(*args, **kwargs):
            return None
        return _noop


def run_capture(strategy_dir: str, inject: dict | None = None) -> MatrixCapture:
    service = StrategyBacktestService(
        BacktestEngine(KlineRepository(DataStore(settings.data_dir))),
        StrategyEngine(strategy_dirs=[Path(strategy_dir)]),
    )
    if inject:
        # in-memory only: reproduce the S01 execution caliber (199-trade reference)
        service.strategy_engine.get("custom_mw7fvp17").meta["backtest_defaults"] = inject
        print(f"[inject] backtest_defaults <- {json.dumps(inject, ensure_ascii=False)}")
    cap = MatrixCapture()
    cfg = StrategyBacktestConfig(
        strategy_id="custom_mw7fvp17", symbols=None,
        start=date(2019, 7, 1), end=date(2026, 10, 30),
        params={}, overrides={}, matching="open_t+1",
        commission_pct=0.0003, stamp_tax_pct=0.001, slippage_bps=10.0,
        max_positions=5, max_exposure_pct=0.6, initial_capital=1_000_000.0,
        position_sizing="equal", mode="position", asset_type="stock",
        holding_days=60, minute_fill=False, carry_state=None, carry_out=False,
    )
    result = service.run(cfg, evidence=cap)
    print(f"[capture] error={result.error} trades={len(result.trades or [])} "
          f"market={cap.market is not None} signals={cap.signals is not None}")
    if cap.market is None or cap.signals is None:
        raise SystemExit("evidence hook did not deliver the matrices")
    return cap


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategies-dir", default=r"D:\TSP\data\strategies\custom")
    ap.add_argument("--out-tag", default="")
    ap.add_argument("--trade-a", default="a0_10bp")
    ap.add_argument("--trade-b", default="a1_10bp")
    ap.add_argument("--inject-defaults", default="")
    args = ap.parse_args()
    inject = json.loads(Path(args.inject_defaults).read_text(encoding="utf-8")) if args.inject_defaults else None
    cap = run_capture(args.strategies_dir, inject)
    market, signals = cap.market, cap.signals
    labels = [str(x)[:10] for x in market.timestamp_labels]
    print(f"[matrix] shape={market.shape} first={labels[0]} last={labels[-1]}")

    fast = np.asarray(matrix_feature(market, "ma20"), dtype=np.float64)
    slow = np.asarray(matrix_feature(market, "ma60"), dtype=np.float64)
    prev_fast = np.asarray(valid_shift(fast, 1), dtype=np.float64)
    prev_slow = np.asarray(valid_shift(slow, 1), dtype=np.float64)
    finite = np.isfinite(fast) & np.isfinite(slow) & np.isfinite(prev_fast) & np.isfinite(prev_slow)
    # level form = the exact pre-patch expression `fast < slow` (NaN comparisons are False,
    # so no finiteness gate is needed; prev_* are NOT part of it)
    with np.errstate(invalid="ignore"):
        level = (fast < slow)
        event = (fast < slow) & (prev_fast >= prev_slow)
    level_only = level & ~event

    exit_mat = np.asarray(signals.exit).astype(bool)

    def _shift(mask: np.ndarray) -> np.ndarray:
        out = np.zeros_like(mask, dtype=bool)
        out[1:] = mask[:-1]
        return out

    matches = {
        "event_raw": bool(np.array_equal(exit_mat, event)),
        "event_shifted": bool(np.array_equal(exit_mat, _shift(event))),
        "level_raw": bool(np.array_equal(exit_mat, level)),
        "level_shifted": bool(np.array_equal(exit_mat, _shift(level))),
    }
    print("[emit] signals.exit matches:", json.dumps(matches))

    tradable = np.asarray(market.tradable)
    limit_dn = (np.asarray(market.limit_down_locked)
                if getattr(market, "limit_down_locked", None) is not None
                else np.zeros(market.shape, dtype=bool))

    t0 = pl.read_parquet(RESULTS / args.trade_a / "trades.parquet")  # level semantics (before)
    t1 = pl.read_parquet(RESULTS / args.trade_b / "trades.parquet")  # event semantics (after)
    idx = {lab: i for i, lab in enumerate(labels)}
    asset = {s: j for j, s in enumerate(market.symbols)}

    cols = ["symbol", "entry_date", "exit_date", "exit_reason", "exit_signal_date",
            "blocked_exit_days", "duration", "pnl_pct", "entry_price", "exit_price"]
    a0 = [r for r in t0.select(cols).iter_rows(named=True)]
    a1 = [r for r in t1.select(cols).iter_rows(named=True)]
    grid = {(r["symbol"], r["entry_date"], r["exit_date"], r["exit_reason"]): r for r in a1}

    per_trade, blocked_rows, details = [], [], []
    level_only_inside = 0
    latch_on_event_day = 0
    latch_on_level_only_day = 0
    for row in a0:
        j = asset.get(row["symbol"])
        a, b = idx.get(row["entry_date"]), idx.get(row["exit_date"])
        if j is None or a is None or b is None:
            continue
        lo_only = level_only[a:b + 1, j]
        n_lo = int(lo_only.sum())
        level_only_inside += n_lo
        sig_i = idx.get(row["exit_signal_date"]) if row["exit_signal_date"] else None
        latch_kind = None
        if sig_i is not None:
            if bool(event[sig_i, j]):
                latch_kind = "event_day"
                latch_on_event_day += 1
            elif bool(level_only[sig_i, j]):
                latch_kind = "level_only_day"
                latch_on_level_only_day += 1
            else:
                latch_kind = "neither"
        other = grid.get((row["symbol"], row["entry_date"], row["exit_date"], row["exit_reason"]))
        rec = {
            "symbol": row["symbol"], "entry_date": row["entry_date"],
            "exit_signal_date": row["exit_signal_date"], "exit_date": row["exit_date"],
            "exit_reason": row["exit_reason"], "latch_day_kind": latch_kind,
            "blocked_exit_days": int(row["blocked_exit_days"] or 0),
            "duration": row["duration"], "pnl_pct": row["pnl_pct"],
            "level_only_days_in_holding": n_lo,
            "level_only_days_on_blocked_or_untradable": int(
                (lo_only & (~tradable[a:b + 1, j] | limit_dn[a:b + 1, j])).sum()),
            "same_as_a1": bool(other is not None
                               and other["exit_date"] == row["exit_date"]
                               and other["exit_signal_date"] == row["exit_signal_date"]
                               and other["duration"] == row["duration"]
                               and other["pnl_pct"] == row["pnl_pct"]
                               and other["exit_price"] == row["exit_price"]),
        }
        per_trade.append(rec)
        if rec["blocked_exit_days"] > 0:
            blocked_rows.append(rec)
            day_rows = []
            for t in range(a, b + 1):
                day_rows.append({
                    "date": labels[t], "level_true": bool(level[t, j]),
                    "event_true": bool(event[t, j]), "level_only": bool(level_only[t, j]),
                    "tradable": bool(tradable[t, j]), "limit_down_locked": bool(limit_dn[t, j]),
                })
            details.append({"trade": {k: rec[k] for k in
                                      ("symbol", "entry_date", "exit_signal_date", "exit_date",
                                       "blocked_exit_days", "duration", "pnl_pct")},
                            "days": day_rows})

    levels = {
        "window": [labels[0], labels[-1]],
        "n_dates": len(labels), "n_assets": market.shape[1],
        "cells_with_features": int(finite.sum()),
        "cells_level_true": int(level.sum()),
        "cells_event_true": int(event.sum()),
        "cells_level_only": int(level_only.sum()),
        "level_only_share_of_level_true": round(int(level_only.sum()) / max(int(level.sum()), 1), 4),
        "signals_exit_matches": matches,
        "signal_exit_true_cells": int(exit_mat.sum()),
        "n_trades": len(per_trade),
        "level_only_days_inside_holdings": int(level_only_inside),
        "trades_with_level_only_days_in_holding": int(sum(
            1 for r in per_trade if r["level_only_days_in_holding"] > 0)),
        "latch_on_event_day": latch_on_event_day,
        "latch_on_level_only_day": latch_on_level_only_day,
        "n_trades_with_blocked_exit": len(blocked_rows),
        "n_trades_identical_to_a1": int(sum(1 for r in per_trade if r["same_as_a1"])),
    }
    print("[cells]", json.dumps(levels, ensure_ascii=False, indent=1))

    (RESULTS / f"boundary_crossdown{args.out_tag}.json").write_text(json.dumps(
        {"levels": levels, "blocked_trades": blocked_rows, "blocked_day_grids": details},
        ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    lines = ["| # | symbol | entry | exit_signal_date | exit_date | latch day kind | blocked_exit_days "
             "| duration | pnl_pct | level-only days in holding | level-only days on blocked/untradable | a1 identical |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(blocked_rows, 1):
        lines.append(
            f"| {i} | {r['symbol']} | {r['entry_date']} | {r['exit_signal_date']} | {r['exit_date']} "
            f"| {r['latch_day_kind']} | {r['blocked_exit_days']} | {r['duration']} "
            f"| {r['pnl_pct']:.4f} | {r['level_only_days_in_holding']} "
            f"| {r['level_only_days_on_blocked_or_untradable']} | {r['same_as_a1']} |")
    table = "\n".join(lines)
    print(table)

    detail_lines = []
    for d in details:
        t = d["trade"]
        detail_lines.append(f"\n### {t['symbol']} {t['entry_date']} → {t['exit_date']} "
                            f"(blocked_exit_days={t['blocked_exit_days']})\n")
        detail_lines.append("| date | level_true | event_true | level_only | tradable | limit_down_locked |")
        detail_lines.append("|---|---|---|---|---|---|")
        for day in d["days"]:
            detail_lines.append(f"| {day['date']} | {day['level_true']} | {day['event_true']} "
                                f"| {day['level_only']} | {day['tradable']} | {day['limit_down_locked']} |")
    (RESULTS / f"boundary_blocked_table{args.out_tag}.md").write_text(
        table + "\n" + "\n".join(detail_lines) + "\n", encoding="utf-8")

    ok = matches["event_raw"] and all(r["same_as_a1"] for r in per_trade)
    print(f"[verdict] blocked_cases={len(blocked_rows)} "
          f"all_trades_identical_under_event_form={all(r['same_as_a1'] for r in per_trade)}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
