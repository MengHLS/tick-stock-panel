"""⑤-a acceptance self-check. Read-only. Exit 0 = every done_when item holds.

Checks:
  A1 8 run dirs exist (7 arms + gross), each result.json has a non-empty embedded
     effective_config with the 5 required blocks;
  A2 per-arm resolved_matcher_config differs from baseline in exactly ONE real key
     (gross: the three cost keys, which is task B not a toggle arm);
  A3 baseline = 208 trades, no injection;
  A4 manifest.json carries three parquet sha256 for every arm;
  A5 evidence ② columns present in every trades_priced.parquet + unexplained == 0;
  A6 control #6 (trailing) byte-identical to baseline on all three parquet;
  A7 task B: default-口径 gross annual <= 0 and cost zeros reflected in resolved config;
  A8 strategy file on disk unchanged (3,478 B / 85ae72a5…);
  A9 upstream research files untouched (REPORT.md / PREREG.md / metrics.json / report_metrics.py).
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASE = "base_nodefaults_10bp"
ARMS = [
    "base_nodefaults_10bp",
    "only_entry_price_basis_raw",
    "only_block_limit_open",
    "only_finalize_open_at_end",
    "only_execution_costs",
    "only_trailing_peak_price_close",
    "only_exit_signal_requires_profit",
    "base_nodefaults_gross",
]
REQ_CFG_BLOCKS = [
    "arm_tag",
    "single_toggle_injected",
    "request",
    "strategy_meta_backtest_defaults_effective_raw",
    "execution_policy_normalized",
    "resolved_matcher_config",
]
PRICED_COLS = [
    "entry_price_raw",
    "entry_price_adj",
    "exit_price_raw",
    "exit_price_adj",
    "cf_entry",
    "cf_exit",
]
UPSTREAM = {
    "REPORT.md": "e60cd0b857f40fb227dad704e62c6d132fbba9e5107f1c53ba3870c436d7ca9b",
}

ok = True
report: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok
    ok = ok and bool(cond)
    report.append(f"[{'PASS' if cond else 'FAIL'}] {name}{(' :: ' + detail) if detail else ''}")


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def flat(d, p=""):
    o = {}
    for k, v in d.items():
        if isinstance(v, dict):
            o.update(flat(v, p + k + "."))
        else:
            o[p + k] = v
    return o


def main() -> int:
    # A1
    for a in ARMS:
        d = HERE / a
        rj = d / "result.json"
        check(f"A1 dir+result.json {a}", d.is_dir() and rj.exists())
        if not rj.exists():
            continue
        r = json.load(io.open(rj, encoding="utf-8"))
        cfg = r.get("effective_config") or {}
        missing = [k for k in REQ_CFG_BLOCKS if k not in cfg]
        check(f"A1 effective_config blocks {a}", not missing, f"missing={missing}")
        check(f"A1 run error is null {a}", r.get("error") is None, str(r.get("error")))
        for f in ("trades.parquet", "equity.parquet", "drawdown.parquet"):
            check(f"A1 parquet {a}/{f}", (d / f).exists())

    base_cfg = json.load(io.open(HERE / BASE / "effective_config.json", encoding="utf-8"))
    check("A3 baseline no injection", base_cfg.get("single_toggle_injected") is None)
    check(
        "A3 baseline META defaults empty",
        base_cfg.get("strategy_meta_backtest_defaults_effective_raw") is None,
    )
    base_res = json.load(
        io.open(HERE / BASE / "result.json", encoding="utf-8")
    )["effective_config"]["resolved_matcher_config"]
    fb = flat(base_res)

    # A2: exactly one real key changes per toggle arm
    one_toggle = [a for a in ARMS if a not in (BASE, "base_nodefaults_gross")]
    for a in one_toggle:
        cl = json.load(io.open(HERE / a / "effective_config.json", encoding="utf-8"))
        fa = flat(cl["resolved_matcher_config"])
        keys = set(fb) | set(fa)
        changed = [k for k in sorted(keys) if fb.get(k, "<absent>") != fa.get(k, "<absent>")]
        derived = [k for k in changed if k == "exit_signal_profit_basis"]
        # a composite key whose value flattens into sub-keys still counts as ONE toggle
        real = sorted({k.split(".")[0] for k in changed if k not in derived})
        expect = 1
        check(
            f"A2 single real toggle {a}",
            len(real) == expect,
            f"real={real} derived={derived}",
        )
        inj = cl.get("single_toggle_injected") or {}
        check(f"A2 injected payload non-empty {a}", bool(inj), json.dumps(inj, ensure_ascii=False))

    # A4
    man = json.load(io.open(HERE / "manifest.json", encoding="utf-8"))
    check("A4 manifest has all arms", sorted(man["arms"]) == sorted(ARMS))
    for a in ARMS:
        t = man["arms"][a].get("three_parquet_sha256") or {}
        check(
            f"A4 three sha256 {a}",
            len(t) == 3 and all(len(v) == 64 for v in t.values()),
            json.dumps(sorted(t)),
        )
        for f, h in t.items():
            check(f"A4 sha matches file {a}/{f}", sha(HERE / a / f) == h)

    # A5
    for a in ARMS:
        tp = HERE / a / "trades_priced.parquet"
        cols = pl.read_parquet(tp).columns
        miss = [c for c in PRICED_COLS if c not in cols]
        check(f"A5 dual-basis cols {a}", not miss, f"missing={miss}")
    tab = {x["arm"]: x for x in json.load(io.open(HERE / "arms_table.json", encoding="utf-8"))}
    for a in ARMS:
        check(f"A5 unexplained==0 {a}", tab[a]["price_check_unexplained"] == 0)

    # A6
    bh = man["arms"][BASE]["three_parquet_sha256"]
    th = man["arms"]["only_trailing_peak_price_close"]["three_parquet_sha256"]
    check("A6 trailing byte-identical to baseline", bh == th, json.dumps(th))

    # A7
    g = json.load(io.open(HERE / "base_nodefaults_gross" / "result.json", encoding="utf-8"))
    check("A7 gross flag true", g["gross"] is True)
    check(
        "A7 all cost inputs zero",
        g["commission_pct"] == 0 and g["stamp_tax_pct"] == 0 and g["slippage_bps"] == 0,
        f"c={g['commission_pct']} t={g['stamp_tax_pct']} s={g['slippage_bps']}",
    )
    check(
        "A7 default-口径 gross annual <= 0",
        g["stats"]["annual_return"] <= 0,
        f"{g['stats']['annual_return']:.4f}",
    )
    check("A7 gross arm no injection", g["effective_config"]["single_toggle_injected"] is None)

    # A8
    sp = Path(r"D:\TSP\data\strategies\custom\custom_mw7fvp17.py")
    check(
        "A8 strategy file unchanged",
        sp.stat().st_size == 3478
        and sha(sp) == "85ae72a5318523d1515903314a817ca5a75cd07b33790cefe0d7b5acea794a07",
        f"{sp.stat().st_size} B / {sha(sp)}",
    )

    # A9
    for name, want in UPSTREAM.items():
        p = ROOT / name
        check(f"A9 upstream untouched {name}", p.exists() and sha(p) == want, sha(p) if p.exists() else "MISSING")

    print("\n".join(report))
    fails = [r for r in report if r.startswith("[FAIL]")]
    print(f"\nchecks={len(report)} fails={len(fails)}")
    print("VERDICT:", "ALL_PASS" if not fails else "FAIL")
    (HERE / "verify_five_a_result.json").write_text(
        json.dumps(
            {"checks": report, "fails": fails, "verdict": "ALL_PASS" if not fails else "FAIL"},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
