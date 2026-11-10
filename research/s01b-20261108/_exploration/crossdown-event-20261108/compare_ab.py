"""Step 3: A/B comparison of the two production-pipeline runs (a0 = before, a1 = after).

Judged on:
  * trades: identical row count, identical column list (the engine's 22 columns),
    and cell-by-cell equality after a deterministic sort;
  * equity: identical row count and cell-by-cell equality;
  * stats block of result.json for the headline metrics.

Prints VERDICT and diff_columns. Exit 0 only when everything matches.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
KEY = ["symbol", "entry_date", "exit_date", "exit_reason", "pnl_pct", "shares"]
STAT_KEYS = ("total_return", "annual_return", "max_drawdown", "sharpe", "n_trades",
             "completed_trade_count", "open_at_end_count", "avg_holding_days",
             "avg_exposure", "max_exposure", "final_equity")


def load(tag: str, name: str) -> pl.DataFrame:
    p = RESULTS / tag / name
    if not p.exists():
        raise SystemExit(f"missing {p}")
    return pl.read_parquet(p)


def cell_diff(a: pl.DataFrame, b: pl.DataFrame, cols: list[str]) -> dict[str, int]:
    """Count differing cells per column (frames must share the same sorted row order)."""
    out: dict[str, int] = {}
    for c in cols:
        sa, sb = a[c], b[c]
        if sa.dtype != sb.dtype:
            out[c] = int(a.height)
            continue
        if sa.dtype == pl.Float64:
            neq = ~((sa == sb) | (sa.is_nan() & sb.is_nan()))
        else:
            neq = sa != sb
        n = int(neq.sum())
        if n:
            out[c] = n
    return out


def compare(a_tag: str, b_tag: str) -> dict:
    ta, tb = load(a_tag, "trades.parquet"), load(b_tag, "trades.parquet")
    ea, eb = load(a_tag, "equity.parquet"), load(b_tag, "equity.parquet")
    same_cols = list(ta.columns) == list(tb.columns)
    cols = [c for c in ta.columns if c in tb.columns]
    prova = ta.select(cols).sort(KEY)
    provb = tb.select(cols).sort(KEY)
    trades_equal = prova.equals(provb) if same_cols and ta.height == tb.height else False
    tdiff = {} if trades_equal else cell_diff(prova, provb, cols)

    ecols = [c for c in ea.columns if c in eb.columns]
    eq_equal = (list(ea.columns) == list(eb.columns) and ea.height == eb.height
                and ea.select(ecols).equals(eb.select(ecols)))
    ediff = {} if eq_equal else (
        cell_diff(ea.select(ecols), eb.select(ecols), ecols)
        if ea.height == eb.height and list(ea.columns) == list(eb.columns) else {"__shape__": 1}
    )

    sa = json.loads((RESULTS / a_tag / "result.json").read_text(encoding="utf-8"))["stats"]
    sb = json.loads((RESULTS / b_tag / "result.json").read_text(encoding="utf-8"))["stats"]
    sdiff = {k: {"a": sa.get(k), "b": sb.get(k)} for k in STAT_KEYS if sa.get(k) != sb.get(k)}

    return {
        "a": a_tag, "b": b_tag,
        "trades_rows": [ta.height, tb.height],
        "trades_columns": list(ta.columns),
        "trades_column_identical": same_cols,
        "trades_exact_equal": bool(trades_equal),
        "diff_columns": tdiff,
        "equity_rows": [ea.height, eb.height],
        "equity_columns": list(ea.columns),
        "equity_exact_equal": bool(eq_equal),
        "equity_diff_columns": ediff,
        "stats_diff": sdiff,
        "exit_reason_a": ta.group_by("exit_reason").len().sort("exit_reason").to_dicts(),
        "exit_reason_b": tb.group_by("exit_reason").len().sort("exit_reason").to_dicts(),
    }


def main() -> int:
    pairs = [("a0_10bp", "a1_10bp")]
    if (RESULTS / "c0_10bp").exists() and (RESULTS / "diag_a0arm").exists():
        # the injected production-file run must reproduce the S01b a0 research arm bit for bit
        pairs.append(("diag_a0arm", "c0_10bp"))
    if (RESULTS / "c0_10bp").exists() and (RESULTS / "c1_10bp").exists():
        pairs.append(("c0_10bp", "c1_10bp"))
    out = [compare(x, y) for x, y in pairs]
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    (RESULTS / "compare_ab.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    ok = all(o["trades_exact_equal"] and o["equity_exact_equal"] and o["trades_column_identical"]
             and not o["stats_diff"] for o in out)
    print("VERDICT:", "IDENTICAL" if ok else "DIFFERS")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
