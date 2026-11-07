"""Full-path stale-quote risk diagnostic over frozen strategy-search artifacts.

Read-only over frozen inputs:
  results/e1_v3/panel_input.arrow            (frozen panel, sha256 checked)
  results/run_S*.json                        (36 = 12 strategies x 3 cost scenarios)
  results/e1_v3/run_C00_A.json, run_C00_B.json

Writes only under results/path_risk/.

For every path it rebuilds daily holdings from the trade ledger plus the recorded
open positions, then measures per position-day whether the panel has a bar on that
date, how old the last available quote is, and how much equity sat on a carried
last price. Ex-post classifications (symbol never trades again; E1 S_stale list)
are kept strictly separate from what was knowable on the day.

Exit codes: 0 ok, 2 frozen panel hash mismatch, 3 missing inputs.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import platform
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
INPUTS_JSON = RES / "e1_v3" / "inputs.json"

SCHEMA = "path-risk-diagnostic/1"
CST = timezone(timedelta(hours=8))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_panel():
    df = pl.read_ipc(PANEL).select(["symbol", "date", "raw_close", "close", "volume"])
    symbols = df["symbol"].to_list()
    dates = [d.isoformat() for d in df["date"].to_list()]
    raw = df["raw_close"].to_list()
    adj = df["close"].to_list()
    vol = df["volume"].to_list()

    per_sym = defaultdict(list)
    for s, d, r, c, v in zip(symbols, dates, raw, adj, vol):
        per_sym[s].append((d, r, c, v))
    for s in per_sym:
        per_sym[s].sort()

    calendar = sorted({d for d in dates})
    return {
        "per_sym": per_sym,
        "dates": {s: [row[0] for row in rows] for s, rows in per_sym.items()},
        "calendar_index": {d: i for i, d in enumerate(calendar)},
        "calendar": calendar,
        "rows": df.height,
        "n_symbols": len(per_sym),
        "min_volume": min(vol),
        "zero_volume_rows": sum(1 for v in vol if v <= 0),
        "first_date": calendar[0],
        "last_date": calendar[-1],
    }


def quote_state(panel, symbol: str, date: str):
    """Return (bar_today, quote_age_days, mark_raw_close, mark_adj_close, last_bar_date)."""
    ds = panel["dates"].get(symbol)
    if not ds:
        return None
    i = bisect.bisect_right(ds, date)
    if i == 0:
        return {"bar_today": False, "quote_age": None, "mark_raw": None,
                "mark_adj": None, "last_bar": None}
    row = panel["per_sym"][symbol][i - 1]
    last_bar = row[0]
    age = panel["calendar_index"][date] - panel["calendar_index"][last_bar]
    return {"bar_today": last_bar == date, "quote_age": age, "mark_raw": row[1],
            "mark_adj": row[2], "last_bar": last_bar}


def symbol_last_bar(panel, symbol: str):
    ds = panel["dates"].get(symbol)
    return ds[-1] if ds else None


def build_holdings(equity, trades, open_positions, final_date):
    """date -> {symbol: shares}. Entry day inclusive, exit day exclusive."""
    hold = defaultdict(lambda: defaultdict(float))
    for t in trades:
        ed, xd = t["entry_date"], t["exit_date"]
        for row in equity:
            d = row["date"]
            if d >= ed and (xd is None or d < xd):
                hold[d][t["symbol"]] += float(t["shares"])
    for p in open_positions:
        ed = p["entry_date"]
        for row in equity:
            d = row["date"]
            if d >= ed:
                hold[d][p["symbol"]] += float(p["shares"])
    return hold


def open_positions_of(run: dict, kind: str):
    """Recorded still-open positions. S-suite artifacts do not persist symbols."""
    if kind == "S":
        return [], "not_persisted"
    pos = []
    if run.get("carry") and run["carry"].get("positions"):
        for p in run["carry"]["positions"]:
            pos.append({"symbol": p["symbol"], "shares": p["shares"],
                        "entry_date": p["entry_date"],
                        "blocked_exit_days": p.get("blocked_exit_days", 0),
                        "pending_exit_reason": p.get("pending_exit_reason")})
        return pos, "carry"
    for p in run.get("final_positions") or []:
        if isinstance(p, dict) and "symbol" in p:
            pos.append({"symbol": p["symbol"], "shares": p["shares"],
                        "entry_date": p.get("entry_date"), "blocked_exit_days": 0,
                        "pending_exit_reason": None})
    return pos, "final_positions"


def analyse_path(pid: str, kind: str, path: Path, panel, e1_stale: set) -> tuple[dict, list]:
    run = json.loads(path.read_text(encoding="utf-8"))
    equity = run["equity"]
    trades = run["trades"]
    final_date = equity[-1]["date"]
    opens, open_source = open_positions_of(run, kind)
    hold = build_holdings(equity, trades, opens, final_date)

    eq_value = {row["date"]: row["value"] for row in equity}

    rows = []
    unidentified_days = []
    unidentified_weight_days = 0.0
    reconcile = []
    for row in equity:
        d = row["date"]
        hv = hold.get(d, {})
        n_id = len(hv)
        n_rep = row["positions"]
        if n_id != n_rep:
            gap = max(0, n_rep - n_id)
            unidentified_days.append({
                "date": d, "reported_positions": n_rep, "identified": n_id,
                "unidentified_positions": gap,
                "equity": row["value"], "exposure_reported": row["exposure"],
            })
            if n_rep:
                # upper bound: unidentified slots carried their pro-rata share of expose
                unidentified_weight_days += row["exposure"] * (gap / n_rep)
        if n_id == n_rep and hv:
            mv = 0.0
            complete = True
            for sym, shares in hv.items():
                q = quote_state(panel, sym, d)
                if q is None or q["mark_raw"] is None:
                    complete = False
                    break
                mv += shares * q["mark_raw"]
            if complete:
                err = row["cash"] + mv - row["value"]
                mine = mv / row["value"] if row["value"] else None
                reconcile.append({"date": d, "err": err, "mine": mine,
                                  "exposure_reported": row["exposure"]})
        for sym, shares in hv.items():
            q = quote_state(panel, sym, d)
            if q is None:
                rows.append({"path": pid, "date": d, "symbol": sym, "shares": shares,
                             "known": False})
                continue
            val = shares * q["mark_raw"] if q["mark_raw"] is not None else None
            weight = val / eq_value[d] if val is not None else None
            rows.append({
                "path": pid, "date": d, "symbol": sym, "shares": shares, "known": True,
                "bar_today": q["bar_today"], "quote_age": q["quote_age"],
                "mark_raw": q["mark_raw"], "value": val, "weight": weight,
                "exposure_reported": row["exposure"],
                "last_bar": q["last_bar"],
                "ex_post_permanent": (symbol_last_bar(panel, sym) == q["last_bar"]),
                "e1_stale_symbol": sym in e1_stale,
            })

    known = [r for r in rows if r["known"]]
    stale = [r for r in known if r["quote_age"] is not None and r["quote_age"] >= 1]
    no_prior = [r for r in known if r["quote_age"] is None]

    n_days = len(equity)
    w_days_stale = sum(r["weight"] for r in stale if r["weight"] is not None)
    w_days_all = sum(r["weight"] for r in known if r["weight"] is not None)
    daily_stale = defaultdict(float)
    for r in stale:
        if r["weight"] is not None:
            daily_stale[r["date"]] += r["weight"]

    # consecutive stale episodes per (symbol, holding span)
    episodes = []
    by_sym = defaultdict(list)
    for r in sorted(known, key=lambda x: (x["symbol"], x["date"])):
        by_sym[r["symbol"]].append(r)
    for sym, rs in by_sym.items():
        cur = []
        for r in rs:
            if r["quote_age"] is not None and r["quote_age"] >= 1:
                cur.append(r)
            else:
                if cur:
                    episodes.append(_episode(panel, pid, sym, cur))
                cur = []
        if cur:
            episodes.append(_episode(panel, pid, sym, cur))
    episodes.sort(key=lambda e: (e["max_weight"] or 0) * e["days"], reverse=True)
    deferred = sum((e["last_weight"] or 0) * e["resume_gap_return"]
                   for e in episodes if e["resume_gap_return"] is not None)
    big_jumps = sum(1 for e in episodes
                    if e["resume_gap_return"] is not None and abs(e["resume_gap_return"]) >= 0.05)

    e1_rows = [r for r in known if r["e1_stale_symbol"]]
    e1_pit = [r for r in e1_rows if r["quote_age"] is not None and r["quote_age"] >= 1]
    e1_pit_resumed = [r for r in e1_pit if not r["ex_post_permanent"]]
    e1_pit_dead = [r for r in e1_pit if r["ex_post_permanent"]]

    blocked = defaultdict(int)
    for t in trades:
        blocked[t.get("blocked_exit_days", 0)] += 1
    exit_no_bar = 0
    entry_no_bar = 0
    ratios = []
    for t in trades:
        ds = panel["dates"].get(t["symbol"], [])
        if not ds:
            continue
        i = bisect.bisect_left(ds, t["exit_date"])
        if i >= len(ds) or ds[i] != t["exit_date"]:
            exit_no_bar += 1
        else:
            mark = panel["per_sym"][t["symbol"]][i][1]
            if mark:
                ratios.append(t["exit_price"] / mark)
        j = bisect.bisect_left(ds, t["entry_date"])
        if j >= len(ds) or ds[j] != t["entry_date"]:
            entry_no_bar += 1
    ratios.sort()

    def pct(seq, q):
        if not seq:
            return None
        return seq[min(len(seq) - 1, int(len(seq) * q))]

    all_ages = [r["quote_age"] for r in stale if r["quote_age"] is not None]
    rec = {
        "path_id": pid,
        "kind": kind,
        "input_file": str(path.relative_to(ROOT)),
        "input_sha256": sha256(path),
        "strategy": run.get("strategy"),
        "slippage_bps": run.get("slippage_bps"),
        "gross": run.get("gross"),
        "open_position_source": open_source,
        "window": {"start": equity[0]["date"], "end": final_date, "days": n_days},
        "final_equity": equity[-1]["value"],
        "final_positions_reported": equity[-1]["positions"],
        "trades": len(trades),
        "holdings": {
            "identified_position_days": len(known),
            "unidentified_position_days": sum(u["unidentified_positions"] for u in unidentified_days),
            "days_with_unidentified": len(unidentified_days),
            "max_unidentified_positions": max([u["unidentified_positions"] for u in unidentified_days], default=0),
            "unidentified_first_date": unidentified_days[0]["date"] if unidentified_days else None,
            "unidentified_last_date": unidentified_days[-1]["date"] if unidentified_days else None,
            "no_prior_bar_position_days": len(no_prior),
            "unidentified_weight_days_upper": round(unidentified_weight_days, 6),
            "unidentified_exposure_max_day": round(
                max([u["exposure_reported"] * (u["unidentified_positions"] / u["reported_positions"])
                     for u in unidentified_days if u["reported_positions"]], default=0.0), 6),
        },
        "valuation_reconciliation": {
            "days_checked": len(reconcile),
            "days_within_1_cny": sum(1 for r in reconcile if abs(r["err"]) <= 1.0),
            "days_over_1_cny": sum(1 for r in reconcile if abs(r["err"]) > 1.0),
            "max_abs_err_cny": round(max([abs(r["err"]) for r in reconcile], default=0.0), 4),
            "days_over_1_cny_dates": [r["date"] for r in reconcile if abs(r["err"]) > 1.0][:40],
            "max_exposure_diff_vs_reported": round(max(
                [abs((r["mine"] or 0) - (r["exposure_reported"] or 0)) for r in reconcile], default=0.0), 6),
        },
        "staleness": {
            "stale_position_days": len(stale),
            "stale_share_of_position_days": round(len(stale) / len(known), 6) if known else None,
            "distinct_symbols_stale": len({r["symbol"] for r in stale}),
            "max_quote_age_days": max(all_ages) if all_ages else 0,
            "median_quote_age_days": pct(sorted(all_ages), 0.5),
            "stale_weight_days": round(w_days_stale, 6),
            "total_weight_days": round(w_days_all, 6),
            "stale_weight_share": round(w_days_stale / w_days_all, 6) if w_days_all else None,
            "mean_daily_stale_weight": round(w_days_stale / n_days, 6),
            "max_daily_stale_weight": round(max(daily_stale.values()), 6) if daily_stale else 0.0,
            "max_daily_stale_weight_date": max(daily_stale, key=daily_stale.get) if daily_stale else None,
            "days_with_stale_weight": len(daily_stale),
            "no_bar_position_days": len(stale),
            "zero_volume_position_days": 0,
            "stale_episodes": len(episodes),
            "stale_episodes_with_abs_resume_jump_ge_5pct": big_jumps,
            "deferred_revaluation_weight_sum": round(deferred, 6),
        },
        "ex_post": {
            "held_symbols": len(by_sym),
            "held_symbols_e1_stale": len({r["symbol"] for r in e1_rows}),
            "e1_stale_position_days": len(e1_rows),
            "e1_stale_weight_days": round(sum(r["weight"] for r in e1_rows if r["weight"] is not None), 6),
            "e1_stale_pit_stale_days": len(e1_pit),
            "e1_stale_pit_stale_resumed_days": len(e1_pit_resumed),
            "e1_stale_pit_stale_never_resumed_days": len(e1_pit_dead),
            "never_resumed_position_days": sum(1 for r in stale if r["ex_post_permanent"]),
            "never_resumed_weight_days": round(
                sum(r["weight"] for r in stale if r["ex_post_permanent"] and r["weight"] is not None), 6),
            "resumed_position_days": sum(1 for r in stale if not r["ex_post_permanent"]),
        },
        "exit_side": {
            "closed_trades": len(trades),
            "blocked_exit_trades": sum(v for k, v in blocked.items() if k and k > 0),
            "blocked_exit_days_sum": sum(k * v for k, v in blocked.items() if k),
            "max_blocked_exit_days": max(blocked) if blocked else 0,
            "exit_date_without_bar": exit_no_bar,
            "entry_date_without_bar": entry_no_bar,
            "exit_price_over_last_raw_close_p05": round(pct(ratios, 0.05), 6) if ratios else None,
            "exit_price_over_last_raw_close_p50": round(pct(ratios, 0.5), 6) if ratios else None,
            "exit_price_over_last_raw_close_p95": round(pct(ratios, 0.95), 6) if ratios else None,
        },
        "top_stale_episodes": episodes[:5],
        "_all_stale_episodes": episodes,
    }
    return rec, rows


def _episode(panel, pid, sym, rs):
    weights = [r["weight"] for r in rs if r["weight"] is not None]
    end = rs[-1]["date"]
    last_mark = rs[-1]["mark_raw"]
    ds = panel["dates"].get(sym, [])
    i = bisect.bisect_right(ds, end)
    resume_date = ds[i] if i < len(ds) else None
    resume_price = panel["per_sym"][sym][i][1] if resume_date else None
    gap_ret = None
    if resume_price is not None and last_mark:
        gap_ret = round(resume_price / last_mark - 1.0, 6)
    return {
        "path": pid,
        "symbol": sym,
        "start": rs[0]["date"],
        "end": end,
        "days": len(rs),
        "max_quote_age": max(r["quote_age"] for r in rs),
        "max_weight": round(max(weights), 6) if weights else None,
        "last_weight": round(weights[-1], 6) if weights else None,
        "resume_date": resume_date,
        "resume_gap_return": gap_ret,
        "never_resumed": all(r["ex_post_permanent"] for r in rs),
        "e1_stale_symbol": rs[0]["e1_stale_symbol"],
    }


def main() -> int:
    if not PANEL.exists() or not INPUTS_JSON.exists():
        print("missing frozen panel or inputs.json", file=sys.stderr)
        return 3
    inputs = json.loads(INPUTS_JSON.read_text(encoding="utf-8"))
    panel_sha = sha256(PANEL)
    if panel_sha != inputs["panel_ipc_sha256"]:
        print(f"panel sha mismatch: {panel_sha} != {inputs['panel_ipc_sha256']}", file=sys.stderr)
        return 2

    e1_stale = set(inputs["stale_symbols"])
    panel = load_panel()

    paths = []
    for f in sorted(RES.glob("run_S*.json")):
        paths.append((f.stem, "S", f))
    for tag in ("A", "B"):
        f = RES / "e1_v3" / f"run_C00_{tag}.json"
        if not f.exists():
            print(f"missing {f}", file=sys.stderr)
            return 3
        paths.append((f"C00_{tag}", "C00", f))
    if not paths:
        print("no run artifacts", file=sys.stderr)
        return 3

    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    all_rows = []
    every_episode = []
    for pid, kind, f in paths:
        rec, rows = analyse_path(pid, kind, f, panel, e1_stale)
        every_episode.extend(rec.pop("_all_stale_episodes"))
        records.append(rec)
        all_rows.extend([{k: r.get(k) for k in
                          ("path", "date", "symbol", "shares", "bar_today", "quote_age",
                           "mark_raw", "value", "weight", "last_bar", "ex_post_permanent",
                           "e1_stale_symbol")} for r in rows])
        print(f"{pid}: pd={rec['holdings']['identified_position_days']} "
              f"stale={rec['staleness']['stale_position_days']} "
              f"maxw={rec['staleness']['max_daily_stale_weight']} "
              f"unid={rec['holdings']['unidentified_position_days']}")

    detail = pl.DataFrame(all_rows, infer_schema_length=10000)
    detail_path = OUT / "path_position_days.parquet"
    detail.write_parquet(detail_path)

    distinct_spans = {(e["symbol"], e["start"], e["end"]) for e in every_episode}
    distinct_big = {(e["symbol"], e["start"], e["end"]) for e in every_episode
                    if e["resume_gap_return"] is not None and abs(e["resume_gap_return"]) >= 0.05}

    def worst(key, reverse=True, n=5):
        ok = [r for r in records if key(r) is not None]
        ok.sort(key=key, reverse=reverse)
        return [{"path_id": r["path_id"], "value": key(r)} for r in ok[:n]]

    cross = {
        "n_paths": len(records),
        "n_S_paths": sum(1 for r in records if r["kind"] == "S"),
        "n_C00_paths": sum(1 for r in records if r["kind"] == "C00"),
        "total_position_days": sum(r["holdings"]["identified_position_days"] for r in records),
        "total_stale_position_days": sum(r["staleness"]["stale_position_days"] for r in records),
        "total_unidentified_position_days": sum(r["holdings"]["unidentified_position_days"] for r in records),
        "total_stale_weight_days": round(sum(r["staleness"]["stale_weight_days"] for r in records), 6),
        "total_unidentified_weight_days_upper": round(
            sum(r["holdings"]["unidentified_weight_days_upper"] for r in records), 6),
        "total_exits_without_bar": sum(r["exit_side"]["exit_date_without_bar"] for r in records),
        "total_entries_without_bar": sum(r["exit_side"]["entry_date_without_bar"] for r in records),
        "total_blocked_exit_trades": sum(r["exit_side"]["blocked_exit_trades"] for r in records),
        "total_never_resumed_position_days": sum(r["ex_post"]["never_resumed_position_days"] for r in records),
        "total_never_resumed_weight_days": round(
            sum(r["ex_post"]["never_resumed_weight_days"] for r in records), 6),
        "paths_with_any_stale": sum(1 for r in records if r["staleness"]["stale_position_days"] > 0),
        "paths_with_unidentified": sum(1 for r in records if r["holdings"]["days_with_unidentified"] > 0),
        "worst_by_max_daily_stale_weight":
            worst(lambda r: r["staleness"]["max_daily_stale_weight"]),
        "worst_by_stale_weight_days": worst(lambda r: r["staleness"]["stale_weight_days"]),
        "worst_by_stale_position_days": worst(lambda r: r["staleness"]["stale_position_days"]),
        "max_quote_age_overall": max(r["staleness"]["max_quote_age_days"] for r in records),
        "stale_episodes_raw": len(every_episode),
        "stale_episodes_distinct_symbol_span": len(distinct_spans),
        "stale_episodes_raw_with_abs_resume_jump_ge_5pct": sum(
            1 for e in every_episode
            if e["resume_gap_return"] is not None and abs(e["resume_gap_return"]) >= 0.05),
        "stale_episodes_distinct_with_abs_resume_jump_ge_5pct": len(distinct_big),
    }

    unknowns = [
        ("S-suite artifacts persist only a count of still-open positions, not their symbols: "
         "their last-N-day exposure cannot be attributed to a security."),
        ("The frozen panel contains no zero-volume bar rows (min volume = 1), so suspension, "
         "zero-volume days and delisting all appear identically as a missing bar; without an "
         "authoritative lifecycle table these three cannot be separated."),
        ("Per-day, per-position marks and per-day blocked-exit attempts were not saved by the "
         "runs; blocked_exit_days is a per-trade counter, not a daily log."),
        ("The panel has no delisting registry; 'never traded again inside the panel' is an "
         "ex-post observation, not a known status on the day."),
        ("Reconstructed weights use shares x last raw_close / reported equity; this reproduces "
         "reported equity within 1 CNY on most days but not on every path day."),
    ]

    payload = {
        "schema": SCHEMA,
        "generated_at": datetime.now(CST).isoformat(),
        "command": [sys.executable, str(Path(__file__).resolve())],
        "python": platform.python_version(),
        "polars": pl.__version__,
        "panel": {
            "path": str(PANEL.relative_to(ROOT)),
            "sha256": panel_sha,
            "rows": panel["rows"],
            "symbols": panel["n_symbols"],
            "first_date": panel["first_date"],
            "last_date": panel["last_date"],
            "min_volume": panel["min_volume"],
            "zero_volume_rows": panel["zero_volume_rows"],
            "calendar_days": len(panel["calendar"]),
        },
        "e1_stale_symbols": len(e1_stale),
        "e1_stale_cutoff_exclusive": inputs.get("stale_cutoff_exclusive"),
        "paths": records,
        "cross_path": cross,
        "detail_file": str(detail_path.relative_to(ROOT)),
        "detail_sha256": sha256(detail_path),
        "detail_rows": detail.height,
        "unknowns": unknowns,
        "no_new_alpha_hypotheses": True,
        "note": "Diagnostic only. No profitability claim, no threshold change, v3 E1 FAIL preserved.",
    }
    out_json = OUT / "path_risk.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_json} sha256={sha256(out_json)}")
    print(json.dumps(cross, ensure_ascii=False, indent=2)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
