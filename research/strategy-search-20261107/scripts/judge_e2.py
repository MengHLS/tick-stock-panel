#!/usr/bin/env python
"""E2 判定器：10bp 净 Sharpe + 单边年换手。

只读已有产物（results/registry.json + results/run_*.json），不跑任何回测。
规格见 E1_E2_SPEC.md A.2。

用法：
    python scripts/judge_e2.py                # 默认 scenario=10
    python scripts/judge_e2.py --scenario 30
    python scripts/judge_e2.py --out results/e2_judgement.json

退出码：0 = 至少一条 PASS；2 = 无 PASS（判定完成）；1 = 输入错误。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

MIN_SHARPE = 0.50
WARN_SHARPE = 0.30
MAX_TURNOVER = 30.0
EVAL_START = "2019-07-01"
EVAL_END = "2026-10-30"
T1_END = "2022-12-30"
T2_START = "2023-01-03"


def _stats(values: list[float]) -> dict:
    if len(values) < 3:
        return {"sharpe": None, "cagr": None, "max_drawdown": None, "n_days": len(values)}
    rets = [values[i] / values[i - 1] - 1.0 for i in range(1, len(values))]
    n = len(rets)
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / (n - 1)
    sd = math.sqrt(var) if var > 0 else 0.0
    sharpe = (mean / sd * math.sqrt(252.0)) if sd > 0 else 0.0
    years = n / 252.0
    total = values[-1] / values[0] - 1.0
    cagr = (values[-1] / values[0]) ** (1.0 / years) - 1.0 if years > 0 and values[0] > 0 else 0.0
    peak = values[0]
    mdd = 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, v / peak - 1.0)
    return {"sharpe": sharpe, "cagr": cagr, "total_return": total,
            "max_drawdown": mdd, "n_days": n}


def _window(equity: list[dict], start: str, end: str) -> list[float]:
    return [float(r["value"]) for r in equity if start <= str(r["date"]) <= end]


def judge_one(run_path: Path, entry: dict, scenario: int) -> dict:
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    equity = payload["equity"]
    trades = payload["trades"]

    all_vals = _window(equity, EVAL_START, EVAL_END)
    t2_vals = _window(equity, T2_START, EVAL_END)
    all_s = _stats(all_vals)
    t2_s = _stats(t2_vals)

    years = max(all_s["n_days"] / 252.0, 1e-9)
    mean_eq = sum(all_vals) / len(all_vals) if all_vals else 0.0
    buys = sum(float(t["entry_value"]) for t in trades)
    sells = sum(float(t["exit_value"]) for t in trades)
    turnover = ((buys + sells) / 2.0 / mean_eq / years) if mean_eq > 0 else float("nan")

    reg_all = entry.get("ALL", {})
    reg_t2 = entry.get("OOS", {})
    gross_traded = reg_all.get("gross_traded_over_initial")
    initial = float(equity[0]["value"]) if equity else 0.0
    cross = None
    if gross_traded and initial > 0:
        my_gross = (buys + sells) / initial
        cross = my_gross / float(gross_traded)

    checks = {
        "t2_sharpe_gt_min": (t2_s["sharpe"] or 0.0) > MIN_SHARPE,
        "all_sharpe_gt_min": (all_s["sharpe"] or 0.0) > MIN_SHARPE,
        "turnover_lt_max": bool(turnover == turnover and turnover < MAX_TURNOVER),
    }
    reasons: list[str] = []
    if not checks["t2_sharpe_gt_min"]:
        reasons.append(f"T2 sharpe {t2_s['sharpe']:.3f} <= {MIN_SHARPE}")
    if not checks["all_sharpe_gt_min"]:
        reasons.append(f"ALL sharpe {all_s['sharpe']:.3f} <= {MIN_SHARPE}")
    if not checks["turnover_lt_max"]:
        reasons.append(f"one-way annual turnover {turnover:.1f}x >= {MAX_TURNOVER}")

    if all(checks.values()):
        verdict = "PASS"
    else:
        both_above_warn = ((t2_s["sharpe"] or 0) > WARN_SHARPE) and ((all_s["sharpe"] or 0) > WARN_SHARPE)
        one_above = checks["t2_sharpe_gt_min"] != checks["all_sharpe_gt_min"]
        if both_above_warn and one_above and checks["turnover_lt_max"]:
            verdict = "WARN"
            reasons.append("only one of T2/ALL clears the 0.50 line")
        else:
            verdict = "FAIL"

    mismatch = bool(cross is not None and abs(cross - 1.0) > 0.02)
    if mismatch:
        reasons.append(f"DATA_MISMATCH: gross_traded cross-check ratio {cross:.4f}")

    return {
        "strategy": entry.get("strategy"),
        "scenario_bps": scenario,
        "all": {"sharpe": all_s["sharpe"], "sharpe_registry": reg_all.get("sharpe"),
                "cagr": all_s["cagr"], "max_drawdown": all_s["max_drawdown"],
                "n_days": all_s["n_days"]},
        "t2": {"sharpe": t2_s["sharpe"], "sharpe_registry": reg_t2.get("sharpe"),
               "cagr": t2_s["cagr"], "max_drawdown": t2_s["max_drawdown"],
               "n_days": t2_s["n_days"]},
        "turnover": {"annual_one_way": turnover if turnover == turnover else None,
                     "years": years, "mean_equity": mean_eq,
                     "gross_traded_over_initial": gross_traded,
                     "cross_check_ratio": cross},
        "checks": checks,
        "data_mismatch": mismatch,
        "verdict": verdict,
        "reasons": reasons,
    }


def main() -> int:
    here = Path(__file__).resolve().parent
    root = here.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(root))
    ap.add_argument("--scenario", type=int, default=10, choices=[10, 30])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    root = Path(args.root)
    reg_path = root / "results" / "registry.json"
    if not reg_path.exists():
        print(f"ERROR registry not found: {reg_path}")
        return 1
    registry = json.loads(reg_path.read_text(encoding="utf-8"))
    runs = registry.get("runs", {})

    results = []
    for key, entry in sorted(runs.items()):
        if not key.endswith(f"@{args.scenario}"):
            continue
        if entry.get("slippage_bps") != float(args.scenario):
            continue
        strategy = entry.get("strategy") or key.split("@")[0]
        run_path = root / "results" / f"run_{strategy}_{args.scenario}.json"
        if not run_path.exists():
            print(f"ERROR run detail missing: {run_path}")
            return 1
        results.append(judge_one(run_path, entry, args.scenario))

    if not results:
        print(f"ERROR no runs for scenario {args.scenario}")
        return 1

    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for r in results:
        counts[r["verdict"]] += 1
    exit_code = 0 if counts["PASS"] else 2

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "registry": str(reg_path),
        "criteria": {"min_sharpe": MIN_SHARPE, "warn_sharpe": WARN_SHARPE,
                     "max_turnover": MAX_TURNOVER, "scenario_bps": args.scenario,
                     "rf": 0.0, "annualization": 252},
        "spec": "E1_E2_SPEC.md A.2",
        "results": results,
        "summary": {"n_strategies": len(results), "n_pass": counts["PASS"],
                    "n_warn": counts["WARN"], "n_fail": counts["FAIL"],
                    "any_data_mismatch": any(r["data_mismatch"] for r in results)},
        "exit_code": exit_code,
    }

    out = Path(args.out) if args.out else root / "results" / "e2_judgement.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'strategy':28s} {'ALL':>7s} {'T2':>7s} {'TO':>6s}  verdict")
    for r in results:
        a = r["all"]["sharpe"]
        t = r["t2"]["sharpe"]
        to = r["turnover"]["annual_one_way"]
        print(f"{r['strategy']:28s} {a:7.3f} {t:7.3f} {to:6.2f}  {r['verdict']}")
    print(f"\nPASS={counts['PASS']} WARN={counts['WARN']} FAIL={counts['FAIL']}  exit={exit_code}")
    print(f"written: {out}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
