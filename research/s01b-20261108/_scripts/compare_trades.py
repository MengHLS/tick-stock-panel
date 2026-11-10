"""逐笔比对两个回测结果 (results/<tag>/trades.parquet)。

判据: 笔数相同 + 按 (symbol, entry_date, exit_date, exit_reason, pnl_pct) 排序后
逐行全等 (含 entry_price/exit_price/pnl_amount/shares)。用于:
  - cross_down 语义修正的前后等价性 (a0 vs a0ev, a3 vs a3ev)
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
KEY = ["symbol", "entry_date", "exit_date", "exit_reason", "pnl_pct"]


def load(tag: str) -> pl.DataFrame:
    p = HERE / "results" / tag / "trades.parquet"
    if not p.exists():
        raise SystemExit(f"missing {p}")
    return pl.read_parquet(p)


def compare(tag_a: str, tag_b: str) -> dict:
    a, b = load(tag_a), load(tag_b)
    cols = [c for c in a.columns if c in b.columns]
    a2 = a.select(cols).sort(KEY)
    b2 = b.select(cols).sort(KEY)
    equal = a2.equals(b2)
    diff = {}
    if not equal and a2.height == b2.height:
        d = a2.select([
            pl.col(c).cast(pl.Utf8).alias(c) if a2.schema[c] == pl.Utf8 else pl.col(c).cast(pl.Float64).alias(c)
            for c in cols
        ]).hstack(pl.Series("_row", range(a2.height)))
        d2 = b2.select([
            pl.col(c).cast(pl.Utf8).alias(c) if b2.schema[c] == pl.Utf8 else pl.col(c).cast(pl.Float64).alias(c)
            for c in cols
        ]).hstack(pl.Series("_row", range(b2.height)))
        joined = d.join(d2, on="_row", how="inner", suffix="_b")
        for c in cols:
            n = int((joined[c] != joined[f"{c}_b"]).sum())
            if n:
                diff[c] = n
    return {
        "a": tag_a,
        "b": tag_b,
        "rows_a": a.height,
        "rows_b": b.height,
        "same_row_count": a.height == b.height,
        "exact_equal": bool(equal),
        "diff_columns": diff,
        "exit_reason_a": a.group_by("exit_reason").len().sort("exit_reason").to_dicts(),
        "exit_reason_b": b.group_by("exit_reason").len().sort("exit_reason").to_dicts(),
    }


if __name__ == "__main__":
    pairs = [("a0_10bp", "a0ev_10bp"), ("a3_10bp", "a3ev_10bp")]
    out = [compare(x, y) for x, y in pairs]
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    (HERE / "results" / "compare_cross_down.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    ok = all(o["exact_equal"] for o in out)
    print("VERDICT:", "IDENTICAL" if ok else "DIFFERS")
    raise SystemExit(0 if ok else 2)
