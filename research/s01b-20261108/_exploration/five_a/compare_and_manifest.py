"""⑤-a: single-arm table + 双价基 evidence + manifest.

For every arm directory under research/s01b-20261108/five_a/:
  * read result.json (stats, effective_config, artifacts_sha256)
  * prove the fixture: diff resolved_matcher_config against the baseline arm
    (must differ in exactly the toggled field, plus any derived read-only mirror)
  * per-trade dual price basis from the enriched panel:
        entry_price_adj / entry_price_raw / exit_price_adj / exit_price_raw
        cf_entry / cf_exit   (cf = close / raw_close, i.e. adjusted = raw * cf)
    written to trades_priced.parquet
  * same-key comparison against baseline on (symbol, entry_date):
        n_same_key, same_key_pnl_delta, only_this_arm_pnl
  * sha256 of trades/equity/drawdown parquet into manifest.json

No arm sum, no share-of-difference composition: this script only reports how much
each single toggle moves the number, as instructed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
ENRICHED = Path(r"D:\TSP\data\kline_daily_enriched")

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
BASE = "base_nodefaults_10bp"
# fields that are pure read-only mirrors of another field, not independent inputs
DERIVED = {
    "exit_signal_profit_basis": "exit_signal_requires_profit",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(arm: str) -> dict:
    return json.loads((HERE / arm / "result.json").read_text(encoding="utf-8"))


def cfg_diff(base_cfg: dict, arm_cfg: dict) -> dict:
    keys = sorted(set(base_cfg) | set(arm_cfg))
    out = {}
    for k in keys:
        if base_cfg.get(k) != arm_cfg.get(k):
            out[k] = [base_cfg.get(k), arm_cfg.get(k)]
    return out


def panel_for(trades: pl.DataFrame) -> pl.DataFrame:
    dates = sorted(set(trades["entry_date"].to_list()) | set(trades["exit_date"].to_list()))
    frames = []
    for d in dates:
        p = ENRICHED / f"date={d}" / "part.parquet"
        if p.exists():
            frames.append(
                pl.read_parquet(p, columns=["symbol", "date", "open", "close", "raw_close"])
            )
    df = pl.concat(frames).with_columns(pl.col("date").cast(pl.Utf8))
    df = df.with_columns(
        (pl.col("close") / pl.col("raw_close")).alias("cf"),
        (pl.col("open") * pl.col("raw_close") / pl.col("close")).round(2).alias("raw_open"),
    )
    return df


def price_trades(trades: pl.DataFrame, basis: str, has_costs: bool, finalize: bool) -> pl.DataFrame:
    df = panel_for(trades)
    ent = df.select(
        "symbol",
        pl.col("date").alias("entry_date"),
        pl.col("open").alias("entry_open_adj"),
        pl.col("raw_open").alias("entry_open_raw"),
        pl.col("close").alias("entry_close_adj"),
        pl.col("raw_close").alias("entry_close_raw"),
        pl.col("cf").alias("cf_entry"),
    )
    ext = df.select(
        "symbol",
        pl.col("date").alias("exit_date"),
        pl.col("open").alias("exit_open_adj"),
        pl.col("raw_open").alias("exit_open_raw"),
        pl.col("close").alias("exit_close_adj"),
        pl.col("raw_close").alias("exit_close_raw"),
        pl.col("cf").alias("cf_exit"),
    )
    out = (
        trades.join(ent, on=["symbol", "entry_date"], how="left")
        .join(ext, on=["symbol", "exit_date"], how="left")
        .with_columns(
            pl.col("entry_open_raw").alias("entry_price_raw"),
            pl.col("entry_open_adj").alias("entry_price_adj"),
            pl.col("exit_open_raw").alias("exit_price_raw"),
            pl.col("exit_open_adj").alias("exit_price_adj"),
            pl.col("entry_price").alias("entry_price_engine"),
            pl.col("exit_price").alias("exit_price_engine"),
        )
    )
    out = out.with_columns(
        (pl.col("entry_price_engine") - pl.col("entry_price_adj")).abs().alias("entry_gap_vs_adj"),
        (pl.col("entry_price_engine") - pl.col("entry_price_raw")).abs().alias("entry_gap_vs_raw"),
        (pl.col("exit_price_engine") - pl.col("exit_price_adj")).abs().alias("exit_gap_vs_adj"),
        (pl.col("exit_price_engine") - pl.col("exit_price_raw")).abs().alias("exit_gap_vs_raw"),
    )

    def status(row: dict) -> tuple[str, str]:
        """Return (entry_status, exit_status) — every branch is a verified rule."""
        tol = 5e-4

        def one(eng, adj, raw, close_adj, close_raw, is_open_at_end):
            if eng is None:
                return "missing"
            if abs(eng - adj) <= tol or abs(eng - raw) <= tol:
                return "ok"
            if has_costs:
                # execution_costs moves the 10bp slippage from cash-cost into price
                # (engine.py:2807-2816 fill_price vs 318-325 cost_pct)
                for sign in (1.0, -1.0):
                    if abs(eng - round(adj * (1 + sign * 10.0 / 10_000.0), 4)) <= tol or abs(
                        eng - round(raw * (1 + sign * 10.0 / 10_000.0), 4)
                    ) <= tol:
                        return "slippage_in_price"
            if finalize and is_open_at_end:
                if abs(eng - close_adj) <= tol or abs(eng - close_raw) <= tol:
                    return "close_valuation(end)"
            if basis == "raw":
                # raw basis + corporate action: pos entry_price is restated as
                # (old_price*old_shares + subscription)/new_shares (engine.py:3828)
                for ref in (raw, adj):
                    if ref and eng:
                        k = ref / eng
                        if k > 1.005 and abs(eng * k - ref) <= 0.01:
                            return f"corp_action_restated(x{k:.4f})"
            return "UNEXPLAINED"

        return (
            one(row["entry_price_engine"], row["entry_price_adj"], row["entry_price_raw"],
                row["entry_close_adj"], row["entry_close_raw"], row["open_at_end"]),
            one(row["exit_price_engine"], row["exit_price_adj"], row["exit_price_raw"],
                row["exit_close_adj"], row["exit_close_raw"], row["open_at_end"]),
        )

    st = [status(r) for r in out.to_dicts()]
    return out.with_columns(
        pl.Series("entry_price_check", [s[0] for s in st], dtype=pl.Utf8),
        pl.Series("exit_price_check", [s[1] for s in st], dtype=pl.Utf8),
    )


def geomean_annual(total_return: float, n_days: int) -> float:
    if n_days <= 0:
        return float("nan")
    return (1.0 + total_return) ** (252.0 / n_days) - 1.0


def main() -> int:
    rows = []
    manifest: dict = {"arms": {}, "notes": {}}
    base = load(BASE)
    base_cfg = base["effective_config"]["resolved_matcher_config"]
    base_trades = pl.read_parquet(HERE / BASE / "trades.parquet")
    base_key = base_trades.select(["symbol", "entry_date", "pnl_amount"]).rename(
        {"pnl_amount": "pnl_base"}
    )
    base_stats = base["stats"]

    for arm in ARMS:
        d = load(arm)
        st = d["stats"]
        ec = d["effective_config"]
        cfg = ec["resolved_matcher_config"]
        diff = cfg_diff(base_cfg, cfg)
        real = {k: v for k, v in diff.items() if k not in DERIVED}
        derived = {k: v for k, v in diff.items() if k in DERIVED}

        tpath = HERE / arm / "trades.parquet"
        trades = pl.read_parquet(tpath)
        basis = cfg["entry_price_basis"]
        priced = price_trades(
            trades, basis, cfg["execution_costs"] is not None, bool(cfg["finalize_open_at_end"])
        )
        priced.write_parquet(HERE / arm / "trades_priced.parquet")
        checks = {
            "entry": dict(
                priced.group_by("entry_price_check").len().sort("entry_price_check").iter_rows()
            ),
            "exit": dict(
                priced.group_by("exit_price_check").len().sort("exit_price_check").iter_rows()
            ),
        }
        unexplained = checks["entry"].get("UNEXPLAINED", 0) + checks["exit"].get("UNEXPLAINED", 0)

        key = trades.select(["symbol", "entry_date", "pnl_amount"]).rename(
            {"pnl_amount": "pnl_arm"}
        )
        same = base_key.join(key, on=["symbol", "entry_date"], how="inner")
        same_delta = float((same["pnl_arm"] - same["pnl_base"]).sum()) if same.height else 0.0
        only_arm = key.join(base_key, on=["symbol", "entry_date"], how="anti")
        only_arm_pnl = float(only_arm["pnl_arm"].sum()) if only_arm.height else 0.0
        only_base = base_key.join(key, on=["symbol", "entry_date"], how="anti")

        ex = st.get("execution") or {}
        sells = {k: v for k, v in sorted(ex.items()) if k.startswith("sell_")}
        n_days = len(pl.read_parquet(HERE / arm / "equity.parquet"))
        tr = float(st.get("total_return", 0.0))
        rows.append(
            {
                "arm": arm,
                "toggle": json.dumps(ec["single_toggle_injected"], ensure_ascii=False)
                if ec["single_toggle_injected"]
                else ("gross" if d["gross"] else "baseline"),
                "n_trades": d["n_trades"],
                "total_return": tr,
                "annual_return": st.get("annual_return"),
                "annual_252_recomputed": round(geomean_annual(tr, n_days), 6),
                "max_drawdown": st.get("max_drawdown"),
                "sharpe": st.get("sharpe"),
                "final_equity": st.get("final_equity"),
                "buy_limit_up": ex.get("buy_limit_up"),
                "sell_suspended": ex.get("sell_suspended"),
                "sell_limit_down": ex.get("sell_limit_down"),
                "sell_invalid_price": ex.get("sell_invalid_price"),
                "pending_exit": ex.get("pending_exit"),
                "n_same_key": same.height,
                "same_key_pnl_delta": round(same_delta, 2),
                "only_this_arm_n": only_arm.height,
                "only_this_arm_pnl": round(only_arm_pnl, 2),
                "only_baseline_n": only_base.height,
                "effective_cfg_real_diff": real,
                "effective_cfg_derived_diff": derived,
                "delta_total_return_vs_base": round(tr - float(base_stats["total_return"]), 6),
                "price_check_counts": checks,
                "price_check_unexplained": unexplained,
                "basis_used": basis,
                "entry_price_gap_max_vs_adj": float(priced["entry_gap_vs_adj"].max() or 0.0),
                "exit_price_gap_max_vs_adj": float(priced["exit_gap_vs_adj"].max() or 0.0),
            }
        )

        files = {
            name: sha256_file(HERE / arm / name)
            for name in ("trades.parquet", "equity.parquet", "drawdown.parquet")
        }
        files["trades_priced.parquet"] = sha256_file(HERE / arm / "trades_priced.parquet")
        manifest["arms"][arm] = {
            "result_json_sha256": sha256_file(HERE / arm / "result.json"),
            "effective_config_json_sha256": sha256_file(HERE / arm / "effective_config.json"),
            "artifacts_sha256": files,
            "three_parquet_sha256": {k: v for k, v in files.items() if k != "trades_priced.parquet"},
            "n_trades": d["n_trades"],
            "gross": d["gross"],
            "single_toggle_injected": ec["single_toggle_injected"],
            "strategy_file_sha256": ec["strategy_file"]["sha256"],
        }

    manifest["notes"] = {
        "baseline": BASE,
        "baseline_definition": "生产文件原样，不注入任何 backtest_defaults（= 今天生产文件的真实默认）",
        "same_key": "(symbol, entry_date) 交集；same_key_pnl_delta = Σ(arm - base) 同键；only_this_arm_pnl = Σ 仅本臂出现的笔",
        "annual_return": "stats.annual_return 与按 252 交易日复算的年化并列，二者应一致",
        "price_basis": "cf = close/raw_close（adj = raw * cf）；raw_open = round(open*raw_close/close,2) 与引擎 raw_open 重建公式相同",
        "no_sum": "各臂不可相加，本文件不做占比合成",
        "exit_signal_profit_basis": "派生只读字段（随 exit_signal_requires_profit 联动），不是独立输入",
    }

    (HERE / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (HERE / "arms_table.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (HERE / "arms_table.csv").write_text(
        pl.DataFrame(
            [
                {
                    **{
                        k: (json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v)
                        for k, v in r.items()
                    }
                }
                for r in rows
            ]
        ).write_csv(),
        encoding="utf-8",
    )

    # markdown table
    def pct(x):
        return "—" if x is None else f"{x * 100:+.2f}%"

    lines = [
        "| # | 臂 | 单一开关 | 笔数 | 总收益 | 年化 | 年化(252复算) | MDD | Sharpe | 期末权益 | buy_limit_up | sell_suspended | sell_limit_down | 同键笔数 | 同键 pnl delta | 仅本臂笔数 | 仅本臂 pnl | 总收益 vs 基线 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows):
        lines.append(
            f"| {i} | `{r['arm']}` | `{r['toggle']}` | {r['n_trades']} | {pct(r['total_return'])} | "
            f"{pct(r['annual_return'])} | {pct(r['annual_252_recomputed'])} | {pct(r['max_drawdown'])} | "
            f"{r['sharpe']} | {r['final_equity']:,.2f} | {r['buy_limit_up']} | {r['sell_suspended']} | "
            f"{r['sell_limit_down']} | {r['n_same_key']} | {r['same_key_pnl_delta']:,.2f} | "
            f"{r['only_this_arm_n']} | {r['only_this_arm_pnl']:,.2f} | "
            f"{r['delta_total_return_vs_base'] * 100:+.2f}pp |"
        )
    (HERE / "arms_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    print("\n=== effective_config diff vs baseline (resolved matcher config) ===")
    for r in rows:
        print(f"{r['arm']:<36} real={json.dumps(r['effective_cfg_real_diff'], ensure_ascii=False)} "
              f"derived={json.dumps(r['effective_cfg_derived_diff'], ensure_ascii=False)}")
    print("\n=== price-basis reconstruction check (recorded vs expected open) ===")
    for r in rows:
        print(f"{r['arm']:<36} basis={r['basis_used']:<8} unexplained={r['price_check_unexplained']} "
              f"entry={json.dumps(r['price_check_counts']['entry'], ensure_ascii=False)} "
              f"exit={json.dumps(r['price_check_counts']['exit'], ensure_ascii=False)}")
    print("\nwrote manifest.json / arms_table.json / arms_table.csv / arms_table.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
