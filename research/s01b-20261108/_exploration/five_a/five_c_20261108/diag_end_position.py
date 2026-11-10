"""⑤-c 诊断 1：期末 1,722.56 缺口成因（只读，不写引擎、不改结果目录）。

生产矩阵路径（``simulate_market_matrix``）里的 ``_try_sell`` / ``_sell`` /
``_mark_pending`` 用的是 ``(time_id, position_id)`` 寻址；``sys.settrace`` 的
global 钩子只在 'call' 事件被调用，参数必须在 ``_global`` 里当场快照。

全量落 ``trace_end_position.json``，离线分析用 ``analyze_end_position.py``。
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[3]
DATA_ROOT = HERE.parents[1] / "data_root"
os.environ["DATA_DIR"] = str(DATA_ROOT)
sys.path.insert(0, str(PROJECT / "backend"))

from app.backtest.engine import BacktestEngine  # noqa: E402
from app.backtest.strategy import (  # noqa: E402
    StrategyBacktestConfig,
    StrategyBacktestService,
)
from app.config import settings  # noqa: E402
from app.strategy.engine import StrategyEngine  # noqa: E402
from app.tickflow.repository import DataStore, KlineRepository  # noqa: E402

WATCH = {
    "_try_sell",
    "_mark_pending",
    "_sell",
    "_process_entries",
    "_plan_buys",
    "_buy_planned",
    "_exit_signal_at",
}
LOG: list[dict] = []
ENGINE_FILE = str(PROJECT / "backend" / "app" / "backtest" / "engine.py")


def _plain(val):  # noqa: ANN001
    if isinstance(val, (int, float, str, bool)) or val is None:
        return val
    if hasattr(val, "item"):
        try:
            return val.item()
        except Exception:  # noqa: BLE001
            return str(val)
    return str(val)


def _snapshot(frame) -> dict:  # noqa: ANN001
    loc = frame.f_locals
    name = frame.f_code.co_name
    rec: dict = {"fn": name, "line": frame.f_code.co_firstlineno}
    for key in ("time_id", "position_id", "asset_id", "date_text", "reason",
                "signal_date", "blocked", "override", "exit_price_override"):
        if key in loc:
            rec[key] = _plain(loc[key])
    if "matrix" in loc and "asset_id" in rec:
        try:
            rec["symbol"] = str(loc["matrix"].symbols[int(rec["asset_id"])])
        except Exception:  # noqa: BLE001
            pass
    positions = loc.get("positions")
    if isinstance(positions, dict):
        rec["n_positions"] = len(positions)
        rec["cash"] = _plain(loc.get("cash"))
        rec["positions"] = {
            str(pid): {
                "sym": (
                    str(loc["matrix"].symbols[int(pos["asset_id"])])
                    if "matrix" in loc and "asset_id" in pos else None
                ),
                "entry_date": pos.get("entry_date"),
                "shares": _plain(pos.get("shares")),
                "pending": pos.get("pending_exit_reason"),
                "blocked_days": _plain(pos.get("blocked_exit_days")),
            }
            for pid, pos in positions.items()
        }
    return rec


def _global(frame, event, arg):  # noqa: ANN001
    if event == "call":
        code = frame.f_code
        if code.co_filename == ENGINE_FILE and code.co_name in WATCH:
            LOG.append(_snapshot(frame))
            return _local
    return None


def _local(frame, event, arg):  # noqa: ANN001
    if event == "return":
        LOG.append({"fn": frame.f_code.co_name + "_return", "value": _plain(arg),
                    "line": frame.f_code.co_firstlineno,
                    "time_id": _plain(frame.f_locals.get("time_id")),
                    "asset_id": _plain(frame.f_locals.get("asset_id"))})
    elif event == "exception":
        LOG.append({"fn": frame.f_code.co_name, "exc": repr(arg[1])})
    return _local


def main() -> int:
    service = StrategyBacktestService(
        BacktestEngine(KlineRepository(DataStore(settings.data_dir))),
        StrategyEngine(strategy_dirs=[Path(r"D:\TSP\data\strategies\custom")]),
    )
    cfg = StrategyBacktestConfig(
        strategy_id="custom_mw7fvp17",
        symbols=None,
        start=date(2019, 7, 1),
        end=date(2026, 10, 30),
        params={},
        overrides={},
        matching="open_t+1",
        commission_pct=0.0003,
        stamp_tax_pct=0.001,
        slippage_bps=10.0,
        max_positions=5,
        max_exposure_pct=0.6,
        initial_capital=1_000_000.0,
        position_sizing="equal",
        mode="position",
        asset_type="stock",
        holding_days=60,
        minute_fill=False,
        carry_state=None,
        carry_out=False,
    )
    t0 = time.perf_counter()
    sys.settrace(_global)
    try:
        result = service.run(cfg)
    finally:
        sys.settrace(None)
    elapsed = time.perf_counter() - t0
    print(f"[run] trades={len(result.trades)} elapsed={elapsed:.1f}s error={result.error}")

    out = HERE / "trace_end_position.json"
    tail = [e for e in LOG if (e.get("time_id") in (1777, 1778)) or e.get("fn") in (
        "_sell", "_mark_pending")]
    out.write_text(json.dumps(tail, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"[trace] events={len(LOG)} kept={len(tail)} -> {out}")

    for t in result.trades:
        rec = dict(t) if not isinstance(t, dict) else t
        if rec.get("symbol") == "688143.SH":
            print("[trade]", json.dumps(rec, ensure_ascii=False, default=str))
    print("[equity last]", result.equity_curve[-1])
    print("[equity prev]", result.equity_curve[-2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
