"""Diagnose why control arm `only_exit_signal_requires_profit` is NOT inert.

The brief expected arms 5/6 (trailing_peak_price / exit_signal_requires_profit) to be
inert, and said: if they move the numbers, stop and report rather than guess. This
script produces the deterministic explanation instead of a guess — it does NOT change
any arm.

Mechanism under test (engine.py:2865-2875, `_exit_signal_profit_armed`):
    gate_ok = max(close[t] for t in holding) > pos["risk_entry_price"]
so a *signal* exit is allowed only after the holding's close has once exceeded the
entry price. Cross-checks:
  H1: in the baseline arm, exactly the signal-exit trades with gate_ok == False are the
      trades that lose their `signal` exit in arm 6 (they must fall back to max_hold/end).
  H2: any baseline trade with gate_ok == True keeps a `signal` exit in arm 6.
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
ENRICHED = Path(r"D:\TSP\data\kline_daily_enriched")
BASE = "base_nodefaults_10bp"
ARM = "only_exit_signal_requires_profit"


def main() -> int:
    base = pl.read_parquet(HERE / BASE / "trades_priced.parquet")
    arm = pl.read_parquet(HERE / ARM / "trades_priced.parquet")

    symbols = sorted(set(base["symbol"].to_list()))
    lo = base["entry_date"].min()
    hi = base["exit_date"].max()
    frames = []
    for d in sorted(p.name for p in ENRICHED.iterdir() if p.is_dir()):
        day = d.split("=", 1)[1]
        if not (lo <= day <= hi):
            continue
        p = ENRICHED / d / "part.parquet"
        if not p.exists():
            continue
        frames.append(
            pl.read_parquet(p, columns=["symbol", "date", "close"]).filter(
                pl.col("symbol").is_in(symbols)
            )
        )
    px = (
        pl.concat(frames)
        .with_columns(pl.col("date").cast(pl.Utf8))
        .sort(["symbol", "date"])
    )
    print(f"[panel] rows={px.height} symbols={len(symbols)} span={lo}..{hi}")

    rows = []
    for t in base.iter_rows(named=True):
        s = px.filter(
            (pl.col("symbol") == t["symbol"])
            & (pl.col("date") >= t["entry_date"])
            & (pl.col("date") <= t["exit_date"])
        )
        peak = s["close"].max() if s.height else None
        rows.append(
            {
                "symbol": t["symbol"],
                "entry_date": t["entry_date"],
                "exit_date": t["exit_date"],
                "exit_reason_base": t["exit_reason"],
                "pnl_pct_base": t["pnl_pct"],
                "entry_price": t["entry_price"],
                "pnl_amount": t["pnl_amount"],
                "peak_close": peak,
                # gate uses close prices and the adjusted entry price (adjusted basis,
                # no corporate-action restatement on this arm)
                "gate_ok": bool(peak is not None and peak > t["entry_price"]),
            }
        )
    gate = pl.DataFrame(rows).join(
        arm.select(
            pl.col("symbol"),
            pl.col("entry_date"),
            pl.col("exit_reason").alias("exit_reason_arm6"),
            pl.col("exit_date").alias("exit_date_arm6"),
            pl.col("pnl_pct").alias("pnl_pct_arm6"),
            pl.col("pnl_amount").alias("pnl_amount_arm6"),
        ),
        on=["symbol", "entry_date"],
        how="left",
    )

    sig = gate.filter(pl.col("exit_reason_base") == "signal")
    print(f"[base] trades={gate.height} signal_exits={sig.height}")
    print(f"[base] signal exits with gate_ok=False: {sig.filter(~pl.col('gate_ok')).height}")
    print(f"[base] signal exits with gate_ok=True : {sig.filter(pl.col('gate_ok')).height}")

    blocked = gate.filter((pl.col("exit_reason_base") == "signal") & (~pl.col("gate_ok")))
    print("\n[blocked signal exits] exit_reason in arm6:")
    print(blocked.group_by("exit_reason_arm6").len().sort("exit_reason_arm6").to_dicts())

    kept = gate.filter((pl.col("exit_reason_base") == "signal") & pl.col("gate_ok"))
    print("[kept signal exits] exit_reason in arm6:")
    print(kept.group_by("exit_reason_arm6").len().sort("exit_reason_arm6").to_dicts())

    h1_bad = blocked.filter(pl.col("exit_reason_arm6") == "signal").height
    h2_bad = kept.filter(pl.col("exit_reason_arm6") != "signal").height
    missing = blocked.filter(pl.col("exit_reason_arm6").is_null()).height
    print(f"\nH1 violations (blocked signal exit still 'signal' in arm6) = {h1_bad}")
    print(f"H2 violations (gate-passing signal exit changed reason)   = {h2_bad}")
    print(f"blocked trades absent from arm6                            = {missing}")

    other = gate.filter(pl.col("exit_reason_base") != "signal")
    print(f"[info] non-signal baseline exits unchanged: "
          f"{other.filter(pl.col('exit_reason_base') == pl.col('exit_reason_arm6')).height}/{other.height}")

    out = {
        "mechanism": "engine.py:2865-2875 _exit_signal_profit_armed: gate = max(close over holding) > risk_entry_price",
        "base_signal_exits": sig.height,
        "blocked_signal_exits_gate_false": blocked.height,
        "gate_true_signal_exits": kept.height,
        "blocked_exit_reason_in_arm6": dict(
            blocked.group_by("exit_reason_arm6").len().sort("exit_reason_arm6").iter_rows()
        ),
        "gate_true_exit_reason_in_arm6": dict(
            kept.group_by("exit_reason_arm6").len().sort("exit_reason_arm6").iter_rows()
        ),
        "H1_violations": h1_bad,
        "H2_violations": h2_bad,
        "blocked_absent_from_arm6": missing,
        "blocked_pnl_amount_base": round(float(blocked["pnl_amount"].sum()), 2),
        "blocked_pnl_amount_arm6": round(float(blocked["pnl_amount_arm6"].sum()), 2),
        "blocked_delta_pnl_amount": round(
            float((blocked["pnl_amount_arm6"] - blocked["pnl_amount"]).sum()), 2
        ),
        "blocked_rows_sample": blocked.head(10).to_dicts(),
    }
    (HERE / "control7_diagnosis.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    print("\nwrote control7_diagnosis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
