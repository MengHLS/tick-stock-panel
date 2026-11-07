"""S07@10bp 原参数历史探索性复算 + 期末/跨段持仓可观测性补全（独立研究脚本）。

做什么
- 在冻结面板与冻结 `scripts/common.py` 上，用**与旧 36 次完全相同**的参数重放
  `S07_xs_lowvol_60d` @10bp（`common.year_segments` + `carry_in/carry_out=True`）。
- 唯一改动是**产物持久化**：把 `carry_state` 里引擎已经算出、但旧
  `common.run_continuous()` 丢弃的字段写下来（每段末持仓 lot、期末未平仓 lot、
  逐日现金/权益/持仓数）。
- 不改变信号列、宇宙、撮合、成本、时序；不新增 alpha 假设；不改 `common.py`。

用法（项目根目录）
    set PYTHONUTF8=1
    backend\\.venv\\Scripts\\python.exe research\\strategy-search-20261107\\obs-fix-20261107\\scripts\\replay_s07_obs.py --mode count
    backend\\.venv\\Scripts\\python.exe research\\strategy-search-20261107\\obs-fix-20261107\\scripts\\replay_s07_obs.py --mode full

退出码
    0 成功
    2 指纹不符（面板/common.py/引擎/协议/旧产物）
    3 复现断言失败（与旧产物的权益或交易不一致）
    4 输入缺失
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve()
PKG = HERE.parents[1]                    # obs-fix-20261107
STRATEGY_DIR = HERE.parents[2]           # strategy-search-20261107
PROJECT = HERE.parents[4]                # tick-stock-panel
RESULTS = PKG / "results"
SCRIPTS = STRATEGY_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import common
import polars as pl

STRATEGY_KEY = "S07_xs_lowvol_60d"
SLIPPAGE_BPS = 10.0
MODE_COUNT = "count"
MODE_FULL = "full"

# 冻结指纹（须与 FREEZE_OBSFIX.json 一致）
FROZEN_PANEL_HASH = "fda82b47b6d5b92e0cc4b6d481020ee9a5cb328b282645c647697927c0f6dfe3"
FROZEN_COMMON_SHA = "523986f1223fb3b44b0b26f02b491b5db96c7b291df9570e473ab18bd59cde09"

OLD_RUN = STRATEGY_DIR / "results" / f"run_{STRATEGY_KEY}_10.json"


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_freeze() -> dict:
    path = PKG / "FREEZE_OBSFIX.json"
    if not path.exists():
        raise SystemExit(4)
    return json.loads(path.read_text(encoding="utf-8"))


def check_fingerprints(freeze: dict) -> dict:
    """指纹不符即 exit 2；返回实测值，供产物记录。"""
    observed = {
        "common_py": sha256(SCRIPTS / "common.py"),
        "engine_py": sha256(PROJECT / "backend/app/backtest/engine.py"),
        "matrix_py": sha256(PROJECT / "backend/app/backtest/matrix.py"),
        "protocol": sha256(PKG / "PROTOCOL_OBSFIX_v1.md"),
        "old_run": sha256(OLD_RUN),
    }
    frozen = freeze["sha256"]
    bad = [k for k in ("common_py", "protocol", "old_run") if observed[k] != frozen.get(k)]
    if freeze.get("panel_hash") != FROZEN_PANEL_HASH:
        bad.append("panel_hash_in_freeze")
    if observed["common_py"] != FROZEN_COMMON_SHA:
        bad.append("common_py_vs_statrategy_freeze")
    for key in ("engine_py", "matrix_py"):
        if observed[key] != frozen.get(key):
            bad.append(key)
    if bad:
        print(json.dumps({"fingerprint_mismatch": bad}, ensure_ascii=False), flush=True)
        raise SystemExit(2)
    return observed


def lot_record(pos: dict) -> dict:
    """carry_state 的持仓 lot → 可持久化记录（原样保留，不改动任何数值）。"""
    return {
        "symbol": str(pos.get("symbol")),
        "shares": float(pos.get("shares") or 0.0),
        "lots": float(pos.get("lots") or 0.0),
        "entry_date": str(pos.get("entry_date")),
        "entry_signal_date": str(pos.get("entry_signal_date")),
        "entry_price": float(pos.get("entry_price") or 0.0),
        "entry_value": float(pos.get("entry_value") or 0.0),
        "position_pct": float(pos.get("position_pct") or 0.0),
        "entry_score": float(pos.get("entry_score") or 0.0),
        "hold_days": int(pos.get("hold_days") or 0),
        "hold_session_age": int(pos.get("hold_session_age") or 0),
        "blocked_exit_days": int(pos.get("blocked_exit_days") or 0),
        "cash_dividends": float(pos.get("cash_dividends") or 0.0),
        "pending_exit_reason": pos.get("pending_exit_reason"),
        "pending_exit_signal_date": pos.get("pending_exit_signal_date"),
        "price_basis": "raw",
        "open_at_end": True,
        "exit_date": None,
        "exit_price": None,
    }


def mark_lot(
    lot: dict, as_of: date, panel: pl.DataFrame, calendar: list[date],
) -> dict:
    """按引擎口径补估值：当日有效 raw_close → 否则段内/全样本最后有效 raw_close。

    引擎的 `last_close` 在每段 simulate 调用内重置；这里为「是否缺报价」判断，
    同时记录最后有效报价日与年龄，便于区分「当日有报价」与「沿用旧价」。
    """
    sym = lot["symbol"]
    rows = panel.filter((pl.col("symbol") == sym) & (pl.col("date") <= as_of)).select(
        "date", "raw_close"
    ).sort("date")
    if rows.height == 0:
        lot.update({
            "mark": None, "mark_date": None, "mark_source": "no_quote_fallback_entry",
            "quote_age_sessions": None,
            "market_value": lot["shares"] * lot["entry_price"],
            "market_value_basis": "entry_price_fallback",
        })
        return lot
    last = rows.tail(1).row(0, named=True)
    mark_date = last["date"]
    mark = float(last["raw_close"])
    same_day = mark_date == as_of
    if same_day:
        age = 0
        source = "same_day_close"
    else:
        age = sum(1 for d in calendar if mark_date < d <= as_of)
        source = "last_valid_close"
    lot.update({
        "mark": mark, "mark_date": str(mark_date), "mark_source": source,
        "quote_age_sessions": int(age),
        "market_value": lot["shares"] * mark,
        "market_value_basis": "raw_close",
    })
    return lot


def replay(m, ev, strat, detail: bool, panel: pl.DataFrame, calendar: list[date]) -> dict:
    cfg = common.make_config(SLIPPAGE_BPS, strat.max_hold_days, gross=False)
    carry = None
    equity: list[dict] = []
    trades: list[dict] = []
    segments: list[dict] = []
    for seg_start, seg_end in common.year_segments():
        seg = ev.filter(
            (pl.col("date") >= seg_start) & (pl.col("date") <= seg_end)
        ).sort(["date", "symbol"])
        if seg.is_empty():
            continue
        matrix = common.build_market_matrix(
            seg, seg[strat.entry], seg[strat.exit],
            entry_delay_bars=1, exit_delay_bars=1,
        )
        res = m.engine.simulate_market_matrix(
            matrix, cfg,
            options=common.SimulationOptions(
                include_monte_carlo=False, carry_in=carry, carry_out=True,
            ),
        )
        carry = res.carry_state
        equity.extend(res.equity_curve)
        trades.extend(asdict(t) for t in res.trades)
        record = {
            "start": str(seg_start), "end": str(seg_end),
            "signals": int(seg[strat.entry].sum()),
            "matrix_assets": len(matrix.symbols),
            "equity_days": len(res.equity_curve),
            "trades": len(res.trades),
            "stats": {
                k: v for k, v in res.stats.items()
                if not (str(k).endswith("_ms") or "bytes" in str(k) or "shape" in str(k))
            },
        }
        if detail:
            # 段末账户状态：这是旧链路丢掉的部分，逐字段保留，不做任何重算。
            record["carry_out"] = {
                "cash": float(carry.cash),
                "peak": float(carry.peak),
                "n_positions": len(carry.positions),
                "n_pending_buy_plans": len(carry.pending_buy_plans),
                "lots": [lot_record(p) for p in carry.positions],
                "last_close_held": {
                    str(p.get("symbol")): carry.last_close.get(str(p.get("symbol")))
                    for p in carry.positions
                },
            }
        segments.append(record)
    final_lots: list[dict] = []
    if detail and carry is not None and carry.positions:
        as_of = common.EVAL_END
        final_lots = [mark_lot(lot_record(p), as_of, panel, calendar) for p in carry.positions]
    return {
        "strategy": strat.key, "slippage_bps": SLIPPAGE_BPS, "gross": False,
        "mode": MODE_FULL if detail else MODE_COUNT,
        "signals": int(ev[strat.entry].sum()),
        "segments": segments, "equity": equity, "trades": trades,
        "final_cash": None if carry is None else float(carry.cash),
        "final_positions": 0 if carry is None else len(carry.positions),
        "final_open_lots": final_lots,
    }


def compare_to_old(result: dict) -> dict:
    """与旧 `results/run_S07_xs_lowvol_60d_10.json` 逐字段比较（只读）。"""
    old = json.loads(OLD_RUN.read_text(encoding="utf-8"))
    old_eq = [{k: r[k] for k in ("date", "value", "cash", "positions", "exposure")}
              for r in old["equity"]]
    new_eq = [{k: r[k] for k in ("date", "value", "cash", "positions", "exposure")}
              for r in result["equity"]]
    eq_diff = [
        {"i": i, "old": o, "new": n}
        for i, (o, n) in enumerate(zip(old_eq, new_eq, strict=False)) if o != n
    ]
    old_trades = old["trades"]
    new_trades = result["trades"]
    trade_diff_idx = [
        i for i, (o, n) in enumerate(zip(old_trades, new_trades, strict=False)) if o != n
    ]
    return {
        "old_run_sha256": sha256(OLD_RUN),
        "old_run_size": OLD_RUN.stat().st_size,
        "n_equity_old": len(old_eq), "n_equity_new": len(new_eq),
        "equity_identical": len(eq_diff) == 0 and len(old_eq) == len(new_eq),
        "n_equity_diff_rows": len(eq_diff),
        "first_equity_diffs": eq_diff[:5],
        "n_trades_old": len(old_trades), "n_trades_new": len(new_trades),
        "trades_identical": len(trade_diff_idx) == 0 and len(old_trades) == len(new_trades),
        "n_trade_diff_rows": len(trade_diff_idx),
        "first_trade_diff_idx": trade_diff_idx[:5],
        "final_cash_old": old.get("final_cash"), "final_cash_new": result["final_cash"],
        "final_cash_identical": old.get("final_cash") == result["final_cash"],
        "final_positions_old": old.get("final_positions"),
        "final_positions_new": result["final_positions"],
        "signal_column_unchanged": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=[MODE_COUNT, MODE_FULL], required=True)
    args = ap.parse_args()

    if not SCRIPTS.joinpath("common.py").exists() or not OLD_RUN.exists():
        print(json.dumps({"error": "missing input", "old_run": str(OLD_RUN)}), flush=True)
        raise SystemExit(4)
    freeze = load_freeze()
    observed = check_fingerprints(freeze)

    m = common.open_market()
    panel = common.load_panel(m)
    if common.fingerprint(panel) != FROZEN_PANEL_HASH:
        print(json.dumps({"error": "panel hash mismatch"}, ensure_ascii=False), flush=True)
        raise SystemExit(2)
    prepared = common.build_signals(common.add_universe(common.add_indicators(panel)))
    ev = prepared.filter(pl.col("date") >= common.EVAL_START)
    calendar = [d for d in panel["date"].unique().sort().to_list()]
    strat = next(s for s in common.STRATEGIES if s.key == STRATEGY_KEY)

    started = datetime.now().astimezone()
    detail = args.mode == MODE_FULL
    result = replay(m, ev, strat, detail, panel, calendar)
    comparison = compare_to_old(result)

    as_of = common.EVAL_END
    last_equity = result["equity"][-1] if result["equity"] else {}
    payload = {
        "schema": "wyckoff-obsfix-replay/1",
        "generated_at": started.isoformat(),
        "mode": args.mode,
        "nature": "exploratory re-execution of the same registered strategy; NOT confirmatory, NOT out-of-sample",
        "n_trials": 15, "new_alpha_hypotheses": 0,
        "strategy": {
            "key": strat.key, "title": strat.title, "family": strat.family,
            "entry_col": strat.entry, "exit_col": strat.exit, "score_col": strat.score,
            "max_hold_days": strat.max_hold_days, "holding": strat.holding,
            "slippage_bps": SLIPPAGE_BPS,
        },
        "frozen": {
            "panel_hash": FROZEN_PANEL_HASH,
            "common_sha256": observed["common_py"],
            "engine_sha256": observed["engine_py"],
            "matrix_sha256": observed["matrix_py"],
            "protocol_sha256": observed["protocol"],
            "engine_mtime": datetime.fromtimestamp(
                (PROJECT / "backend/app/backtest/engine.py").stat().st_mtime
            ).isoformat(),
            "old_run_mtime": datetime.fromtimestamp(OLD_RUN.stat().st_mtime).isoformat(),
        },
        "account": {k: v for k, v in common.ACCOUNT.items() if k != "slippage_scenarios"},
        "universe": common.UNIVERSE,
        "window": {"eval_start": str(common.EVAL_START), "eval_end": str(common.EVAL_END)},
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
        ).strip(),
        "signals": result["signals"],
        "segments": result["segments"],
        "equity": result["equity"],
        "trades": result["trades"],
        "n_trades": len(result["trades"]),
        "final_cash": result["final_cash"],
        "final_positions": result["final_positions"],
        "final_open_lots": result["final_open_lots"],
        "final_equity": {
            "reported_value": last_equity.get("value"),
            "reported_cash": last_equity.get("cash"),
            "reported_positions": last_equity.get("positions"),
            "as_of": str(as_of),
            "cash_plus_market_value": (
                None if not result["final_open_lots"] else
                float(result["final_cash"] or 0.0)
                + sum(lot["market_value"] for lot in result["final_open_lots"])
            ),
        },
        "comparison_to_old_run": comparison,
        "behavior_changed_vs_old_run": not (
            comparison["equity_identical"] and comparison["trades_identical"]
            and comparison["final_cash_identical"]
        ),
        "not_claimed": [
            "no profitability claim", "not out-of-sample", "E1 v3 FAIL preserved",
            "no threshold change", "no new alpha hypothesis",
        ],
    }
    common.save_json(RESULTS / f"replay_{STRATEGY_KEY}_10_{args.mode}.json", payload)
    print(json.dumps({
        "mode": args.mode,
        "n_trades": len(result["trades"]),
        "final_positions": result["final_positions"],
        "final_cash": result["final_cash"],
        "equity_identical_to_old": comparison["equity_identical"],
        "trades_identical_to_old": comparison["trades_identical"],
        "final_open_lots": len(result["final_open_lots"]),
        "elapsed_s": round((datetime.now().astimezone() - started).total_seconds(), 1),
    }, ensure_ascii=False), flush=True)
    if payload["behavior_changed_vs_old_run"]:
        print("BEHAVIOR_DRIFT vs old run artifact", flush=True)
        raise SystemExit(3)


if __name__ == "__main__":
    main()
