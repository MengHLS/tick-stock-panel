"""Acceptance ① comparison: cell-by-cell equality of two production-pipeline runs.

Emits VERDICT + diff_columns for trades (all 22 columns) and equity (all 5 columns),
plus a byte-level sha256 of the two parquet files as a second, independent witness.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
RES = HERE / "results"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cmp_frames(tag_a: str, tag_b: str, name: str) -> dict:
    pa, pb = RES / tag_a / f"{name}.parquet", RES / tag_b / f"{name}.parquet"
    fa, fb = pl.read_parquet(pa), pl.read_parquet(pb)
    out = {
        "frame": name,
        "rows": [fa.height, fb.height],
        "columns": [fa.columns, fb.columns],
        "columns_identical": fa.columns == fb.columns,
        "dtypes_identical": fa.dtypes == fb.dtypes,
        "parquet_sha256": [sha(pa), sha(pb)],
        "parquet_bytes_identical": sha(pa) == sha(pb),
        "diff_columns": {},
    }
    if fa.columns == fb.columns:
        for c in fa.columns:
            if fa[c].dtype != fb[c].dtype:
                out["diff_columns"][c] = "dtype_mismatch"
                continue
            if fa[c].dtype in (pl.Float32, pl.Float64):
                diff = ((fa[c] - fb[c]).abs() > 0).sum()
            else:
                diff = (fa[c] != fb[c]).sum()
            if diff:
                out["diff_columns"][c] = int(diff)
    out["exact_equal"] = out["columns_identical"] and not out["diff_columns"] and fa.height == fb.height
    return out


def main() -> int:
    tag_a, tag_b = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("vA_prepatch", "vB_postpatch")
    rep = {"a": tag_a, "b": tag_b}
    rep["trades"] = cmp_frames(tag_a, tag_b, "trades")
    rep["equity"] = cmp_frames(tag_a, tag_b, "equity")
    sa = json.loads((RES / tag_a / "result.json").read_text(encoding="utf-8"))
    sb = json.loads((RES / tag_b / "result.json").read_text(encoding="utf-8"))
    # timing_ms is wall-clock instrumentation, not a backtest result: reported separately
    keys = (set(sa["stats"]) | set(sb["stats"])) - {"timing_ms"}
    rep["stats_diff"] = {k: [sa["stats"].get(k), sb["stats"].get(k)]
                         for k in sorted(keys) if sa["stats"].get(k) != sb["stats"].get(k)}
    rep["timing_ms"] = [sa["stats"].get("timing_ms"), sb["stats"].get("timing_ms")]
    rep["file_sha256"] = [sa["strategy_file_sha256"], sb["strategy_file_sha256"]]
    rep["cross_down_line"] = [sa["cross_down_line"], sb["cross_down_line"]]

    print(json.dumps(rep, ensure_ascii=False, indent=1))
    tr, eq = rep["trades"], rep["equity"]
    print(f"trades: rows={tr['rows']} cols_identical={tr['columns_identical']} "
          f"diff_columns={json.dumps(tr['diff_columns'])} exact_equal={tr['exact_equal']} "
          f"parquet_bytes_identical={tr['parquet_bytes_identical']}")
    print(f"equity: rows={eq['rows']} cols_identical={eq['columns_identical']} "
          f"diff_columns={json.dumps(eq['diff_columns'])} exact_equal={eq['exact_equal']} "
          f"parquet_bytes_identical={eq['parquet_bytes_identical']}")
    print(f"stats_diff={json.dumps(rep['stats_diff'])}")
    ok = tr["exact_equal"] and eq["exact_equal"] and not rep["stats_diff"]
    print("VERDICT: IDENTICAL" if ok else "VERDICT: DIFFERENT")
    (RES / f"compare_{tag_a}_vs_{tag_b}.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
