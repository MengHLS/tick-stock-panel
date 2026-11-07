"""统一口径批量回测：全部策略 × 成本情景 × 连续账户，输出登记数据。

用法（项目根目录）：
    set PYTHONUTF8=1
    backend\\.venv\\Scripts\\python.exe research\\strategy-search-20261107\\scripts\\run_suite.py --only S01,S02
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import polars as pl

import common  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--slippage", default="10,30")
    ap.add_argument("--gross", action="store_true", help="零成本诊断情景（无费用/无滑点）")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    wanted = [s.strip() for s in args.only.split(",") if s.strip()]
    slips = [0.0] if args.gross else [float(s) for s in args.slippage.split(",") if s.strip()]

    m = common.open_market()
    panel = common.load_panel(m)
    prepared = common.build_signals(common.add_universe(common.add_indicators(panel)))
    ev = prepared.filter(prepared["date"] >= common.EVAL_START)
    meta = {
        "created_at": datetime.now().astimezone().isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=common.PROJECT,
                                        text=True).strip(),
        "panel_rows": panel.height, "panel_symbols": panel["symbol"].n_unique(),
        "panel_dates": panel["date"].n_unique(),
        "panel_hash": common.fingerprint(panel),
        "eval_start": str(common.EVAL_START), "eval_end": str(common.EVAL_END),
        "is_end": str(common.IS_END),
        "account": {k: v for k, v in common.ACCOUNT.items() if k != "slippage_scenarios"},
        "universe": common.UNIVERSE,
        "python": sys.version, "polars": pl.__version__,
    }

    registry_path = RESULTS / "registry.json"
    import json
    data = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    data.setdefault("meta", meta)
    data["meta"] = {**data["meta"], **meta}
    runs = data.setdefault("runs", {})

    for strat in common.STRATEGIES:
        if wanted and not any(strat.key.startswith(w) for w in wanted):
            continue
        for slip in slips:
            key = f"{strat.key}@{'gross' if args.gross else f'{slip:g}'}"
            if key in runs and runs[key].get("ok") and not args.force:
                print("skip", key, flush=True)
                continue
            print("run", key, flush=True)
            res = common.run_continuous(m, ev, strat, slip, gross=args.gross)
            payload = {
                "strategy": strat.key, "title": strat.title, "family": strat.family,
                "holding": strat.holding, "max_hold_days": strat.max_hold_days,
                "entry_col": strat.entry, "exit_col": strat.exit, "score_col": strat.score,
                "slippage_bps": slip, "gross": args.gross,
                "segments": res["segments"], "equity": res["equity"],
                "trades": res["trades"],
                "final_positions": res["final_positions"], "final_cash": res["final_cash"],
            }
            summary = {
                "strategy": strat.key, "title": strat.title, "family": strat.family,
                "slippage_bps": slip, "gross": args.gross, "ok": True,
                "signals": int(ev[strat.entry].sum()),
                "n_trades": len(res["trades"]),
                "final_positions": res["final_positions"],
                "segments": [
                    {"start": s["start"], "end": s["end"], "signals": s["signals"],
                     "total_return": s["stats"].get("total_return"),
                     "max_drawdown": s["stats"].get("max_drawdown"),
                     "n_trades": s["stats"].get("n_trades")}
                    for s in res["segments"]
                ],
            }
            spread: dict[str, np.ndarray] = {}
            for label, s, e in (("IS", common.EVAL_START, common.IS_END),
                                ("OOS", date(2023, 1, 3), common.EVAL_END),
                                ("ALL", common.EVAL_START, common.EVAL_END)):
                sm = common.summarize(res, s, e, label)
                spread[label] = sm.pop("returns")
                summary[label] = sm
            summary["execution"] = {
                k: sum((s["stats"].get("execution") or {}).get(k, 0) for s in res["segments"])
                for k in ("buy_limit_up", "buy_no_slot", "buy_suspended", "sell_limit_down",
                          "sell_suspended", "buy_same_day_reentry")
            }
            stem = f"{strat.key}_{'gross' if args.gross else f'{slip:g}'}"
            common.save_json(RESULTS / f"run_{stem}.json", payload)
            np.save(RESULTS / f"rets_{stem}.npy", spread["ALL"])
            runs[key] = summary
            common.save_json(registry_path, data)
            a = summary["ALL"]
            print(f"  {key}: ALL {a['total_return']:+.2%} CAGR {a['cagr']:+.2%} "
                  f"Sharpe {a['sharpe']} MDD {a['max_drawdown']:.2%} "
                  f"trades {a['n_closed_trades']}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
