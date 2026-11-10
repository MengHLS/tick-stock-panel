"""D-EOS 阶段1 验收器：五臂落 C 值 ±0.05 / 三臂 parquet 同 sha / 前 1778 行逐格不变。

判据全部来自契约 R-3：
  1. `equity.parquet` 前 1778 行逐单元格相同，仅末行 value/cash/positions/exposure 变；
  2. `trades.parquet` **按 (entry_date, symbol) 排序后**逐单元格相同（值集不变，
     末笔 end 会提前到该股在列表中的位置 ⇒ 不能用 parquet 字节相等作判据）；
  3. 6 臂末值 = 契约 §5.1 的 C 列（±0.05）；2 臂 + a0 逐字节不变；
  4. `drawdown.parquet` 只允许末行变（raw 臂末行即谷底）。
另加：`stats["execution"]` 字典逐键比对（只允许 P6 相关键变化），末行 positions/
exposure/cash 的终态断言（I3）。

用法：backend\.venv\Scripts\python.exe research\s01b-20261108\postfix_20261108\verify_postfix.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
PROJECT = PARENT.parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

import polars as pl  # noqa: E402
from app.backtest.engine import BacktestEngine, MatcherConfig  # noqa: E402,F401

FIVE_A = PARENT / "five_a"
RESULTS = PARENT / "results"

# 契约 §5.1：D（改前末值）→ C（改后应为的末值）
EXPECT = {
    "base_nodefaults_10bp":            (485_293.78, 483_571.23),
    "only_trailing_peak_price_close":  (485_293.78, 483_571.23),
    "only_execution_costs":            (485_420.69, 483_698.12),
    "only_entry_price_basis_raw":      (434_710.53, 432_987.98),
    "base_nodefaults_gross":           (527_074.75, 525_402.74),
    "only_block_limit_open":         (1_121_259.36, 1_117_814.25),
}
# 契约 §5.2：必须逐字节不变
IDENTICAL = {
    "only_finalize_open_at_end":       (FIVE_A / "only_finalize_open_at_end", 478_212.34),
    "only_exit_signal_requires_profit": (FIVE_A / "only_exit_signal_requires_profit", 673_798.76),
    "a0_10bp":                        (RESULTS / "a0_10bp", 1_242_725.28),
}
BASELINE_DIR = {**{arm: FIVE_A / arm for arm in EXPECT}, **{a: v[0] for a, v in IDENTICAL.items()}}
TOL = 0.05

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  |  {detail}" if detail else ""))


def load(result_dir: Path) -> dict:
    out = {"result": json.loads((result_dir / "result.json").read_text(encoding="utf-8"))}
    for name in ("trades", "equity", "drawdown"):
        p = result_dir / f"{name}.parquet"
        out[name] = pl.read_parquet(p) if p.exists() else None
    return out


def frames_equal(a: pl.DataFrame, b: pl.DataFrame) -> bool:
    if a is None or b is None:
        return a is b
    if a.shape != b.shape or a.columns != b.columns:
        return False
    for col in a.columns:
        sa, sb = a[col], b[col]
        if sa.dtype != sb.dtype:
            return False
        if sa.dtype in (pl.Float32, pl.Float64):
            if not (sa.fill_nan(-1e300) - sb.fill_nan(-1e300)).abs().max() <= 1e-9:
                return False
        elif not (sa == sb).all():
            return False
    return True


def main() -> int:
    # ---------- 1. C 值 + 末行终态 ----------
    table = []
    for arm, (d_value, c_value) in EXPECT.items():
        new = load(HERE / arm)
        final = float(new["result"]["stats"]["final_equity"])
        diff = final - c_value
        check(f"C值 {arm}={final:.2f} 期望{c_value:.2f}",
              abs(diff) <= TOL, f"Δ={diff:+.2f} (容差±{TOL})")
        row = new["equity"].row(-1, named=True)
        check(f"末行终态 {arm} positions=0/cash=value",
              row["positions"] == 0 and abs(row["value"] - row["cash"]) < 0.011,
              f"positions={row['positions']} value={row['value']} cash={row['cash']} exposure={row['exposure']}")
        table.append({
            "arm": arm, "D": d_value, "C": c_value, "after": final, "delta_vs_C": round(diff, 2),
            "total_return_before": None, "total_return_after": new["result"]["stats"].get("total_return"),
            "mdd_after": new["result"]["stats"].get("max_drawdown"),
            "n_trades": new["result"]["stats"].get("n_trades"),
            "open_at_end_count": new["result"]["stats"].get("open_at_end_count"),
            "pending_exit_positions": new["result"]["stats"].get("pending_exit_positions"),
        })

    # ---------- 2. 三臂逐字节不变 ----------
    for arm, (base_dir, expect_final) in IDENTICAL.items():
        old, new = load(base_dir), load(HERE / arm)
        for name in ("trades", "equity", "drawdown"):
            p_old = base_dir / f"{name}.parquet"
            p_new = HERE / arm / f"{name}.parquet"
            if not p_old.exists() or not p_new.exists():
                check(f"字节不变 {arm}/{name}.parquet", (not p_old.exists()) and (not p_new.exists()),
                      f"skip: exists_old={p_old.exists()} exists_new={p_new.exists()}")
                continue
            sha_old = p_old.read_bytes()
            sha_new = p_new.read_bytes()
            check(f"字节不变 {arm}/{name}.parquet",
                  sha_old == sha_new,
                  f"bytes={len(sha_new)} equal={sha_old == sha_new}")
        final = float(new["result"]["stats"]["final_equity"])
        check(f"末值不变 {arm}={final:.2f}", abs(final - expect_final) <= TOL, f"expect {expect_final:.2f}")
        oe = (old["result"]["stats"].get("execution") or {})
        ne = (new["result"]["stats"].get("execution") or {})
        check(f"execution 不变 {arm}", oe == ne, f"diff_keys={sorted(k for k in set(oe) | set(ne) if oe.get(k) != ne.get(k))}")

    # ---------- 3. 改动臂：前 1778 行 + trades 排序后逐格 ----------
    for arm in EXPECT:
        old_dir, new_dir = BASELINE_DIR[arm], HERE / arm
        old, new = load(old_dir), load(new_dir)
        oe, ne = old["equity"], new["equity"]
        check(f"equity 行数不变 {arm}", oe.height == ne.height, f"{oe.height} -> {ne.height}")
        head_ok = frames_equal(oe.head(oe.height - 1), ne.head(ne.height - 1))
        check(f"equity 前 {oe.height - 1} 行逐格相同 {arm}", head_ok,
              "" if head_ok else "前段有差异")
        last_old = oe.row(-1, named=True)
        last_new = ne.row(-1, named=True)
        check(f"equity 末行日期不变 {arm}", last_old["date"] == last_new["date"],
              f"{last_old['date']} == {last_new['date']}")

        ot, nt = old["trades"], new["trades"]
        sort_keys = [c for c in ("entry_date", "symbol", "entry_signal_date", "exit_date") if c in ot.columns]
        ot_s = ot.sort(sort_keys)
        nt_s = nt.sort(sort_keys)
        trade_ok = frames_equal(ot_s, nt_s)
        check(f"trades 排序后逐格相同 {arm}", trade_ok,
              "" if trade_ok else f"shape {ot_s.shape} vs {nt_s.shape}")

        od, nd = old["drawdown"], new["drawdown"]
        dd_ok = frames_equal(od.head(od.height - 1), nd.head(nd.height - 1))
        dd_last_changed = not frames_equal(od.tail(1), nd.tail(1))
        check(f"drawdown 仅末行可变 {arm}", dd_ok, f"last_row_changed={dd_last_changed}")

        oe_x, ne_x = (old["result"]["stats"].get("execution") or {}), (new["result"]["stats"].get("execution") or {})
        diff_keys = sorted(k for k in set(oe_x) | set(ne_x) if oe_x.get(k) != ne_x.get(k))
        check(f"execution 只允许 P6 键变化 {arm}",
              all(k in {"pending_exit", "sell_suspended", "sell_limit_down"} for k in diff_keys),
              f"diff_keys={diff_keys}")

    # ---------- 4. 末行终态 vs 交易闭环 ----------
    for arm in EXPECT:
        new = load(HERE / arm)
        stats = new["result"]["stats"]
        check(f"closed 口径 {arm}: completed==n_trades==open_at_end+completed",
              stats.get("completed_trade_count") == stats.get("n_trades"),
              f"n_trades={stats.get('n_trades')} completed={stats.get('completed_trade_count')} open_at_end={stats.get('open_at_end_count')}")

    failed = [r for r in results if not r[1]]
    print()
    print(f"TOTAL {len(results)}  PASS {len(results) - len(failed)}  FAIL {len(failed)}")
    (HERE / "verify_postfix_result.txt").write_text(
        "\n".join(f"{'PASS' if ok else 'FAIL'} {name}" + (f"  |  {detail}" if detail else "")
                  for name, ok, detail in results)
        + f"\n\nTOTAL {len(results)}  PASS {len(results) - len(failed)}  FAIL {len(failed)}\n",
        encoding="utf-8",
    )
    (HERE / "arms_after.json").write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
