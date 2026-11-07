"""独立验证 OBSFIX 复算产物（不信任产物里的任何 checks 字段，全部从原始账重算）。

检查项见 `PROTOCOL_OBSFIX_v1.md` §4（V1–V12）。

用法（项目根目录）
    set PYTHONUTF8=1
    backend\\.venv\\Scripts\\python.exe research\\strategy-search-20261107\\obs-fix-20261107\\scripts\\verify_obsfix.py

退出码
    0 全部通过
    2 指纹或旧件被改动
    3 行为变更或对账失败
    4 输入缺失
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from bisect import bisect_right
from pathlib import Path

HERE = Path(__file__).resolve()
PKG = HERE.parents[1]
STRATEGY_DIR = HERE.parents[2]
PROJECT = HERE.parents[4]
RESULTS = PKG / "results"
SCRIPTS = STRATEGY_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import common
import polars as pl

RKEY = "S07_xs_lowvol_60d"
TOL_CNY = 1.0


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def load(path: Path) -> dict:
    if not path.exists():
        print(json.dumps({"error": f"missing {path}"}, ensure_ascii=False), flush=True)
        raise SystemExit(4)
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    freeze = load(PKG / "FREEZE_OBSFIX.json")
    count = load(RESULTS / f"replay_{RKEY}_10_count.json")
    full = load(RESULTS / f"replay_{RKEY}_10_full.json")
    ledger = load(PKG / "LEDGER_OBSFIX.json")
    old = load(STRATEGY_DIR / "results" / f"run_{RKEY}_10.json")

    checks: dict[str, dict] = {}

    # ---------------- V1 输入指纹
    obs = {
        "replay_script": sha256(PKG / "scripts" / "replay_s07_obs.py"),
        "verify_script": sha256(PKG / "scripts" / "verify_obsfix.py"),
        "common_py": sha256(SCRIPTS / "common.py"),
        "engine_py": sha256(PROJECT / "backend/app/backtest/engine.py"),
        "matrix_py": sha256(PROJECT / "backend/app/backtest/matrix.py"),
        "protocol": sha256(PKG / "PROTOCOL_OBSFIX_v1.md"),
        "old_run": sha256(STRATEGY_DIR / "results" / f"run_{RKEY}_10.json"),
    }
    mism = [k for k, v in freeze["sha256"].items() if obs.get(k) != v]
    checks["V1_input_fingerprints"] = {"ok": not mism, "mismatch": mism, "observed": obs}

    # ---------------- V2 旧件未被改动
    downgraded = [
        {"path": p, "expected": h, "observed": sha256(PKG.parent / p)}
        for p, h in freeze["legacy_artifacts"].items()
        if sha256(PKG.parent / p) != h
    ]
    checks["V2_legacy_untouched"] = {"ok": not downgraded, "changed": downgraded}

    # ---------------- V3 count vs full（同一引擎，行为等价性）
    def eq_rows(rows: list[dict]) -> list[dict]:
        return [{k: r.get(k) for k in ("date", "value", "cash", "positions", "exposure")}
                for r in rows]

    def total_signals(doc: dict) -> int:
        if "signals" in doc:
            return int(doc["signals"])
        return sum(int(s["signals"]) for s in doc["segments"])

    v3 = {
        "equity_identical": eq_rows(count["equity"]) == eq_rows(full["equity"]),
        "trades_identical": count["trades"] == full["trades"],
        "signals_identical": total_signals(count) == total_signals(full),
        "final_cash_identical": count["final_cash"] == full["final_cash"],
        "final_positions_identical": count["final_positions"] == full["final_positions"],
    }
    v3["ok"] = all(v3.values())
    checks["V3_count_vs_full_equivalence"] = v3

    # ---------------- V4 与旧产物复现
    old_eq = eq_rows(old["equity"])
    full_eq = eq_rows(full["equity"])
    eq_diff = [i for i, (a, b) in enumerate(zip(old_eq, full_eq, strict=False)) if a != b]
    tr_diff = [i for i, (a, b) in enumerate(zip(old["trades"], full["trades"], strict=False))
               if a != b]
    v4 = {
        "n_equity_old": len(old_eq), "n_equity_full": len(full_eq),
        "n_equity_diff": len(eq_diff), "first_equity_diff_idx": eq_diff[:5],
        "n_trades_old": len(old["trades"]), "n_trades_full": len(full["trades"]),
        "n_trade_diff": len(tr_diff), "first_trade_diff_idx": tr_diff[:5],
        "final_cash_old": old.get("final_cash"), "final_cash_full": full["final_cash"],
        "final_positions_old": old.get("final_positions"),
        "final_positions_full": full["final_positions"],
    }
    v4["ok"] = (
        len(eq_diff) == 0 and len(old_eq) == len(full_eq)
        and len(tr_diff) == 0 and len(old["trades"]) == len(full["trades"])
        and old.get("final_cash") == full["final_cash"]
        and old.get("final_positions") == full["final_positions"]
    )
    checks["V4_reproduction_vs_old_run"] = v4

    # ---------------- 逐日重建（V5/V6/V8 的公共底座）
    m = common.open_market()
    panel = common.load_panel(m)
    panel_hash = common.fingerprint(panel)
    symbols = {t["symbol"] for t in full["trades"]} | {
        lot["symbol"] for lot in full["final_open_lots"]
    }
    sub = (
        panel.filter(pl.col("symbol").is_in(sorted(symbols)))
        .select("symbol", "date", "raw_close")
        .sort(["symbol", "date"])
    )
    series: dict[str, tuple[list[str], list[float]]] = {}
    for sym, frame in sub.group_by("symbol", maintain_order=True):
        key = sym[0] if isinstance(sym, tuple) else sym
        dates = [str(d) for d in frame["date"].to_list()]
        closes = [float(c) if c is not None else float("nan")
                  for c in frame["raw_close"].to_list()]
        series[str(key)] = (dates, closes)

    eq_dates = [str(r["date"]) for r in full["equity"]]
    seg_bounds: list[tuple[str, str]] = [
        (str(s["start"]), str(s["end"])) for s in full["segments"]
    ]

    def segment_of(d: str) -> tuple[str, str]:
        for start, end in seg_bounds:
            if start <= d <= end:
                return start, end
        raise ValueError(d)

    # 持仓：交易流水 entry<=d<exit，加上期末未平仓 lot（entry<=d<=eval_end）
    holdings: dict[str, list[tuple[str, float, float]]] = {d: [] for d in eq_dates}
    for t in full["trades"]:
        entry, exit_ = str(t["entry_date"]), str(t["exit_date"])
        for d in eq_dates:
            if entry <= d < exit_:
                holdings[d].append((t["symbol"], float(t["shares"]),
                                    float(t["entry_price"])))
    for lot in full["final_open_lots"]:
        entry = str(lot["entry_date"])
        for d in eq_dates:
            if entry <= d <= str(common.EVAL_END):
                holdings[d].append((lot["symbol"], float(lot["shares"]),
                                    float(lot["entry_price"])))

    def mark(sym: str, d: str, seg_start: str) -> tuple[float, str]:
        dates, closes = series[sym]
        i = bisect_right(dates, d) - 1
        if i >= 0 and dates[i] == d:
            return closes[i], "same_day_close"
        # 引擎每段重置 last_close：只允许回退到本段内最后有效报价
        j = i
        while j >= 0 and dates[j] >= seg_start:
            if not math.isnan(closes[j]):
                return closes[j], "segment_last_close"
            j -= 1
        return float("nan"), "none"

    day_rows: list[dict] = []
    diff_rows: list[dict] = []
    pos_count_mismatch: list[dict] = []
    for row, d in zip(full["equity"], eq_dates, strict=True):
        seg_start, _ = segment_of(d)
        mv = 0.0
        unknown_marks = 0
        for sym, shares, entry_price in holdings[d]:
            price, src = mark(sym, d, seg_start)
            if src == "none" or math.isnan(price) or price <= 0:
                price = entry_price   # 引擎口径：无有效价时用 entry_price
                unknown_marks += 1
            mv += shares * price
        cash = float(row["cash"])
        recomputed = cash + mv
        diff = recomputed - float(row["value"])
        day_rows.append({
            "date": d, "positions": len(holdings[d]),
            "reported_positions": int(row["positions"]),
            "cash": cash, "market_value": mv, "recomputed": recomputed,
            "reported_value": float(row["value"]), "diff_cny": diff,
            "entry_price_fallbacks": unknown_marks,
        })
        if abs(diff) > TOL_CNY:
            diff_rows.append({
                "date": d, "diff_cny": round(diff, 2),
                "pct_of_equity": round(diff / float(row["value"]) * 100, 4),
                "positions": len(holdings[d]),
            })
        if len(holdings[d]) != int(row["positions"]):
            pos_count_mismatch.append({
                "date": d, "rebuilt": len(holdings[d]),
                "reported": int(row["positions"]),
            })

    n_days = len(day_rows)
    checks["V5_daily_reconciliation"] = {
        "days_checked": n_days,
        "days_within_1cny": n_days - len(diff_rows),
        "days_over_1cny": len(diff_rows),
        "share_within": round((n_days - len(diff_rows)) / n_days, 4) if n_days else None,
        "max_abs_diff_cny": round(max((abs(r["diff_cny"]) for r in diff_rows), default=0.0), 2),
        "worst_5": sorted(diff_rows, key=lambda r: -abs(r["diff_cny"]))[:5],
        "unexplained": "残差原因 UNKNOWN（候选：公司行动改股数/分红现金、复权因子版本、段内 last_close 回退），未修补",
        "ok": n_days > 0 and (n_days - len(diff_rows)) / n_days >= 0.98,
    }

    # ---------------- V6 段末股份守恒（构成严格、股数差异单列）
    v6_rows: list[dict] = []
    for seg in full["segments"]:
        carry = seg.get("carry_out")
        if not carry:
            continue
        end = str(seg["end"])
        rebuilt: dict[str, float] = {}
        for t in full["trades"]:
            if str(t["entry_date"]) <= end < str(t["exit_date"]):
                rebuilt[t["symbol"]] = rebuilt.get(t["symbol"], 0.0) + float(t["shares"])
        for lot in full["final_open_lots"]:
            if str(lot["entry_date"]) <= end <= str(common.EVAL_END):
                rebuilt[lot["symbol"]] = rebuilt.get(lot["symbol"], 0.0) + float(lot["shares"])
        carried = {lot["symbol"]: float(lot["shares"]) for lot in carry["lots"]}
        set_ok = set(rebuilt) == set(carried)
        share_gap = {s: round(rebuilt[s] - carried[s], 4) for s in carried
                     if s in rebuilt and abs(rebuilt[s] - carried[s]) > 0.5}
        v6_rows.append({
            "segment_end": end, "n_carried": len(carried), "n_rebuilt": len(rebuilt),
            "symbol_set_identical": set_ok,
            "share_mismatch": share_gap,
        })
    checks["V6_segment_share_conservation"] = {
        "segments": v6_rows,
        "all_symbol_sets_identical": all(r["symbol_set_identical"] for r in v6_rows),
        "share_mismatch_total": sum(len(r["share_mismatch"]) for r in v6_rows),
        "note": "股数差异若出现，候选原因含公司行动改股数（引擎在 raw 基准下会调整 shares），未在此归因",
        "ok": all(r["symbol_set_identical"] for r in v6_rows) and bool(v6_rows),
    }

    # ---------------- V7 期末 lot 完整性 / 不伪造卖出
    last_row = full["equity"][-1]
    lots = full["final_open_lots"]
    summary_mv = sum(lot["market_value"] for lot in lots)
    v7 = {
        "n_final_open_lots": len(lots),
        "final_positions_reported": full["final_positions"],
        "count_matches": len(lots) == full["final_positions"],
        "final_cash": full["final_cash"],
        "cash_plus_mv": float(full["final_cash"] or 0.0) + summary_mv,
        "last_equity_value": float(last_row["value"]),
        "residual_cny": round(float(full["final_cash"] or 0.0) + summary_mv
                              - float(last_row["value"]), 2),
        "trades_with_exit_reason_end": sum(1 for t in full["trades"]
                                           if t.get("exit_reason") == "end"),
        "trades_open_at_end": sum(1 for t in full["trades"] if t.get("open_at_end")),
        "symbols": [lot["symbol"] for lot in lots],
    }
    v7["ok"] = (
        v7["count_matches"] and v7["trades_with_exit_reason_end"] == 0
        and v7["trades_open_at_end"] == 0
        and abs(v7["residual_cny"]) <= TOL_CNY
    )
    checks["V7_final_lots"] = v7

    # ---------------- V8 不可归属持仓日归零
    checks["V8_attributable_position_days"] = {
        "days_checked": n_days,
        "days_with_count_mismatch": len(pos_count_mismatch),
        "worst": pos_count_mismatch[:5],
        "old_artifact_unidentified_days_this_path": 85,
        "note": "85 = PATH_RISK 中 run_S07_xs_lowvol_60d_10 的 holdings.unidentified_position_days",
        "ok": len(pos_count_mismatch) == 0,
    }

    # ---------------- V9 估值基准可追溯
    allowed = {"same_day_close", "last_valid_close", "no_quote_fallback_entry"}
    srcs = [lot["mark_source"] for lot in lots]
    age_ok = True
    for lot in lots:
        if lot["mark_source"] == "same_day_close" and lot["quote_age_sessions"] != 0:
            age_ok = False
        if lot["mark_source"] == "last_valid_close" and not (lot["quote_age_sessions"] or 0) >= 1:
            age_ok = False
    checks["V9_mark_provenance"] = {
        "lot_count": len(lots),
        "mark_source_counts": {s: srcs.count(s) for s in sorted(set(srcs))},
        "all_sources_allowed": set(srcs) <= allowed,
        "sum_of_sources_equals_lots": len(srcs) == len(lots),
        "age_consistent": age_ok,
        "price_basis_all_raw": all(lot["price_basis"] == "raw" for lot in lots),
        "ok": set(srcs) <= allowed and age_ok and all(
            lot["price_basis"] == "raw" for lot in lots),
    }

    # ---------------- V10 未识别项显式化
    unknowns = [
        "残差日的具体原因（公司行动/复权版本/股本/段内回退）未区分",
        "面板无零量行，缺报价 ≠ 停牌 ≠ 退市；无生命周期表",
        "盘中可成交性、竞价排队、T+1 现实约束未测",
        "旧 S07@10 产物生成时（23:19:26）的 engine.py 哈希未记录，无法证明与本次同引擎",
    ]
    checks["V10_unknowns_declared"] = {"unknowns": unknowns, "ok": len(unknowns) >= 3}

    # ---------------- V11 计数纪律
    checks["V11_trial_accounting"] = {
        "n_trials_after": ledger.get("n_trials_after"),
        "new_alpha_hypotheses": ledger.get("new_alpha_hypotheses"),
        "nature": ledger.get("nature"),
        "ok": ledger.get("n_trials_after") == 15 and ledger.get("new_alpha_hypotheses") == 0,
    }

    # ---------------- V12 不越界（git status 与冻结时一致）
    status_now = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=PROJECT, text=True, encoding="utf-8",
        errors="replace",
    )
    status_norm = "\n".join(
        sorted(line for line in status_now.splitlines() if "obs-fix-20261107" not in line)
    )
    status_hash = hashlib.sha256(status_norm.encode("utf-8")).hexdigest()
    checks["V12_scope"] = {
        "git_status_hash_excluding_obsfix": status_hash,
        "expected": freeze.get("git_status_hash_excluding_obsfix"),
        "ok": status_hash == freeze.get("git_status_hash_excluding_obsfix"),
        "panel_hash": panel_hash,
        "panel_hash_expected": freeze.get("panel_hash"),
    }

    failed = [k for k, v in checks.items() if not v.get("ok")]
    verdict = "PASS" if not failed else "FAIL"
    payload = {
        "schema": "obsfix-verification/1",
        "verdict": verdict,
        "failed_checks": failed,
        "checks": checks,
        "engine_sha256": obs["engine_py"],
        "generated_by": "verify_obsfix.py (independent recomputation from raw artifacts)",
    }
    (RESULTS / "verification.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "verdict": verdict, "failed": failed,
        "days_checked": n_days, "days_over_1cny": len(diff_rows),
        "share_within": checks["V5_daily_reconciliation"]["share_within"],
        "final_lots": len(lots), "final_residual_cny": v7["residual_cny"],
    }, ensure_ascii=False), flush=True)
    if failed:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
