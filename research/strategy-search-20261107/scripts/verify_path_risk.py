"""Independent re-derivation of results/path_risk/path_risk.json.

Deliberately different implementation from path_risk_diagnostic.py:
  * holdings rebuilt with index arithmetic on the equity calendar instead of
    per-day string comparisons;
  * quote state derived from a (symbol, date) set + per-symbol sorted bar list
    scanned forwards, not bisect;
  * aggregates recomputed from results/path_risk/path_position_days.parquet
    group-bys and compared against the summary JSON.

Exit 0 only if every check passes. Writes results/path_risk/path_risk_verification.json.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

ROOT = Path(r"C:\work\sourcecode\tick-stock-panel")
RS = ROOT / "research" / "strategy-search-20261107"
RES = RS / "results"
OUT = RES / "path_risk"
PANEL = RES / "e1_v3" / "panel_input.arrow"
CST = timezone(timedelta(hours=8))
TOL = 1e-6


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    summary = json.loads((OUT / "path_risk.json").read_text(encoding="utf-8"))
    detail = pl.read_parquet(OUT / "path_position_days.parquet")
    inputs = json.loads((RES / "e1_v3" / "inputs.json").read_text(encoding="utf-8"))
    e1_stale = set(inputs["stale_symbols"])
    checks: dict[str, bool] = {}
    notes: list[str] = []

    checks["panel_hash_matches_summary"] = sha256(PANEL) == summary["panel"]["sha256"]
    checks["panel_hash_matches_e1_inputs"] = sha256(PANEL) == inputs["panel_ipc_sha256"]
    checks["detail_hash_matches_summary"] = sha256(OUT / "path_position_days.parquet") == summary["detail_sha256"]
    checks["detail_row_count"] = detail.height == summary["detail_rows"]

    pan = pl.read_ipc(PANEL).select(["symbol", "date"]).with_columns(
        pl.col("date").dt.strftime("%Y-%m-%d").alias("d"))
    bar_set = set(zip(pan["symbol"].to_list(), pan["d"].to_list()))
    bars_by_symbol = defaultdict(list)
    for s, d in zip(pan["symbol"].to_list(), pan["d"].to_list()):
        bars_by_symbol[s].append(d)
    for s in bars_by_symbol:
        bars_by_symbol[s].sort()

    # detail-side aggregates
    g = detail.group_by("path").agg([
        pl.len().alias("rows"),
        pl.col("quote_age").is_not_null().sum().alias("known"),
        (pl.col("quote_age") >= 1).sum().alias("stale"),
        pl.col("weight").filter(pl.col("quote_age") >= 1).sum().alias("stale_wd"),
        (pl.col("e1_stale_symbol")).sum().alias("e1pd"),
        ((pl.col("quote_age") >= 1) & pl.col("ex_post_permanent")).sum().alias("dead_pd"),
    ])
    dmap = {r["path"]: r for r in g.iter_rows(named=True)}

    mismatches = []
    for rec in summary["paths"]:
        pid = rec["path_id"]
        path = ROOT / rec["input_file"]
        if sha256(path) != rec["input_sha256"]:
            mismatches.append((pid, "input_sha", None))
        run = json.loads(path.read_text(encoding="utf-8"))
        eq = run["equity"]
        cal = [r["date"] for r in eq]
        pos = {d: i for i, d in enumerate(cal)}

        # holdings by index arithmetic
        spans = []
        for t in run["trades"]:
            i0 = pos[t["entry_date"]]
            i1 = pos[t["exit_date"]] if t["exit_date"] else len(cal)
            spans.append((t["symbol"], float(t["shares"]), i0, i1))
        opens = []
        if rec["kind"] == "C00":
            for p in run["carry"]["positions"]:
                opens.append((p["symbol"], float(p["shares"]), pos[p["entry_date"]], len(cal)))
        spans.extend(opens)

        hold = defaultdict(lambda: defaultdict(float))
        for sym, sh, i0, i1 in spans:
            for i in range(i0, i1):
                hold[i][sym] += sh

        stale_days = 0
        known_days = 0
        dead_pd = 0
        e1_pd = 0
        unid = 0
        cursor = {s: 0 for s in bars_by_symbol}
        for i, row in enumerate(eq):
            hv = hold.get(i, {})
            d = row["date"]
            unid += max(0, row["positions"] - len(hv))
            for sym, sh in hv.items():
                ds = bars_by_symbol.get(sym, [])
                if not ds:
                    continue
                c = cursor[sym]
                while c < len(ds) and ds[c] < d:
                    c += 1
                cursor[sym] = c
                if c < len(ds) and ds[c] == d:
                    known_days += 1          # fresh bar today
                    continue
                if c == 0:
                    continue                 # no prior bar at all -> unknown mark
                known_days += 1
                stale_days += 1              # carried last quote
                if sym in e1_stale:
                    e1_pd += 1
                if ds[-1] <= ds[c - 1]:      # ex post: never traded again after that bar
                    dead_pd += 1

        # recompute weights from detail rows (independent of summary)
        dr = dmap[pid]
        mism = []
        if stale_days != rec["staleness"]["stale_position_days"]:
            mism.append(("stale_position_days", stale_days, rec["staleness"]["stale_position_days"]))
        if known_days != rec["holdings"]["identified_position_days"]:
            mism.append(("identified_position_days", known_days, rec["holdings"]["identified_position_days"]))
        if unid != rec["holdings"]["unidentified_position_days"]:
            mism.append(("unidentified_position_days", unid, rec["holdings"]["unidentified_position_days"]))
        if dead_pd != rec["ex_post"]["never_resumed_position_days"]:
            mism.append(("never_resumed_position_days", dead_pd, rec["ex_post"]["never_resumed_position_days"]))
        if e1_pd != rec["ex_post"]["e1_stale_pit_stale_days"]:
            mism.append(("e1_stale_pit_stale_days", e1_pd, rec["ex_post"]["e1_stale_pit_stale_days"]))
        # detail-side
        if int(dr["stale"]) != rec["staleness"]["stale_position_days"]:
            mism.append(("detail_stale", int(dr["stale"]), rec["staleness"]["stale_position_days"]))
        if abs(float(dr["stale_wd"]) - rec["staleness"]["stale_weight_days"]) > 1e-4:
            mism.append(("detail_stale_weight_days", float(dr["stale_wd"]), rec["staleness"]["stale_weight_days"]))
        if int(dr["dead_pd"]) != rec["ex_post"]["never_resumed_position_days"]:
            mism.append(("detail_dead", int(dr["dead_pd"]), rec["ex_post"]["never_resumed_position_days"]))
        # exits without bar
        exits_no_bar = 0
        for t in run["trades"]:
            if (t["symbol"], t["exit_date"]) not in bar_set:
                exits_no_bar += 1
        if exits_no_bar != rec["exit_side"]["exit_date_without_bar"]:
            mism.append(("exit_date_without_bar", exits_no_bar, rec["exit_side"]["exit_date_without_bar"]))
        if mism:
            mismatches.append((pid, "field_mismatch", mism))

    checks["per_path_recompute_matches"] = not mismatches
    if mismatches:
        notes.append(f"mismatches: {json.dumps(mismatches[:5], ensure_ascii=False)}")

    # cross-path totals recomputed from parts
    tot_stale = sum(r["staleness"]["stale_position_days"] for r in summary["paths"])
    tot_pd = sum(r["holdings"]["identified_position_days"] for r in summary["paths"])
    checks["cross_total_stale"] = tot_stale == summary["cross_path"]["total_stale_position_days"]
    checks["cross_total_pd"] = tot_pd == summary["cross_path"]["total_position_days"]
    checks["cross_total_exits_without_bar"] = (
        sum(r["exit_side"]["exit_date_without_bar"] for r in summary["paths"])
        == summary["cross_path"]["total_exits_without_bar"])
    checks["c00_b_holds_no_e1_stale_symbol"] = all(
        r["ex_post"]["held_symbols_e1_stale"] == 0
        for r in summary["paths"] if r["path_id"] == "C00_B")
    checks["c00_a_holds_e1_stale_symbols"] = any(
        r["ex_post"]["held_symbols_e1_stale"] > 0
        for r in summary["paths"] if r["path_id"] == "C00_A")

    # v3 evidence untouched
    execution = json.loads((RES / "e1_v3" / "execution.json").read_text(encoding="utf-8"))
    checks["v3_outputs_unchanged"] = all(
        sha256(RES / "e1_v3" / name) == digest
        for name, digest in execution["outputs"].items())
    protocol = RS / "PROTOCOL.md"
    checks["protocol_present"] = protocol.exists()

    verdict = all(checks.values())
    payload = {
        "generated_at": datetime.now(CST).isoformat(),
        "verdict": "PASS" if verdict else "FAIL",
        "checks": checks,
        "n_checks": len(checks),
        "n_paths_checked": len(summary["paths"]),
        "notes": notes,
        "summary_sha256": sha256(OUT / "path_risk.json"),
        "detail_sha256": sha256(OUT / "path_position_days.parquet"),
        "no_new_alpha_hypotheses": True,
    }
    (OUT / "path_risk_verification.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["checks"], ensure_ascii=False, indent=1))
    print("verdict", payload["verdict"], "checks", payload["n_checks"])
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
