"""Pre-registered portfolio-construction study for auction multifactor signals.

The signal set is frozen by the multifactor study. This script only changes
portfolio construction: global top-N versus fixed gap-bucket quotas, plus a
daily mark-to-market simulator with T+1, capacity and exposure constraints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import polars as pl

from scripts.auction_high_open_study import PERIODS, _partitions, _write_json, summarize

VERSION = "auction-portfolio-construction-v1"
GAP_BUCKETS = ["2-4", "4-6", "6-8"]
BUCKET_QUOTAS = {"2-4": 2, "4-6": 2, "6-8": 1}
PORTFOLIO_DEFAULTS = {
    "initial_capital": 1_000_000.0,
    "position_pct": 0.05,
    "max_positions": 10,
    "max_new_per_day": 5,
    "max_exposure_pct": 0.50,
    "capacity_pct": 0.01,
    "minimum_notional": 1_000.0,
    "commission_bps": 3.0,
    "stamp_tax_bps": 10.0,
    "slippage_bps": 5.0,
}
VARIANTS = {
    "global_blend_top5": {
        "signal_column": "_tail_risk_blend",
        "score_column": "combined_rank",
        "selection": "global",
    },
    "balanced_blend_221": {
        "signal_column": "_tail_risk_blend",
        "score_column": "combined_rank",
        "selection": "bucket_quota",
    },
    "balanced_intersection_221": {
        "signal_column": "_tail_risk_intersection",
        "score_column": "risk_rank",
        "selection": "bucket_quota",
    },
}
PRIMARY_VARIANT = "balanced_blend_221"
DECISION_GATE = {
    "periods": ["validation", "retrospective_stress"],
    "selected_incremental_ci_lower_positive": True,
    "portfolio_total_return_positive": True,
    "portfolio_max_drawdown_floor": -0.15,
}


def _finite(column: str) -> pl.Expr:
    value = pl.col(column)
    return pl.when(value.is_not_null() & value.is_finite()).then(value).otherwise(None)


def load_events(path: Path) -> pl.DataFrame:
    required = [
        "symbol",
        "date",
        "gap_bucket",
        "tail_strength_signal",
        "tail_strength_rank",
        "risk_rank",
        "_risk_coverage",
        "combined_rank",
        "_risk_signal",
        "_tail_risk_intersection",
        "_tail_risk_blend",
        "entry_reason",
        "exit_reason",
        "entry_vwap",
        "entry_volume",
        "exit_date",
        "net_return",
    ]
    frame = pl.read_parquet(path, columns=required).filter(
        pl.col("gap_bucket").is_in(GAP_BUCKETS),
    )
    if frame.select(pl.struct(["symbol", "date"]).is_duplicated().any()).item():
        raise ValueError("Duplicate signal keys")
    return frame


def load_calendar(data_dir: Path, start: date, end: date) -> list[date]:
    files = _partitions(data_dir / "kline_index_daily", start, end)
    if not files:
        raise ValueError("No index sessions in requested portfolio window")
    calendar = (
        pl.scan_parquet(files, hive_partitioning=False)
        .filter(pl.col("symbol") == "000001.SH")
        .select("date")
        .unique()
        .sort("date")
        .collect()["date"]
        .to_list()
    )
    if not calendar:
        raise ValueError("Index calendar is empty")
    return calendar


def load_daily_closes(
    data_dir: Path,
    symbols: list[str],
    start: date,
    end: date,
) -> pl.DataFrame:
    files = _partitions(data_dir / "kline_daily", start, end)
    if not files:
        raise ValueError("No daily closes in requested portfolio window")
    return (
        pl.scan_parquet(files, hive_partitioning=False)
        .filter(pl.col("symbol").is_in(symbols))
        .select("symbol", "date", "close")
        .collect()
        .filter(pl.col("close").is_not_null() & pl.col("close").is_finite())
        .sort(["symbol", "date"])
    )


def _sort_candidates(frame: pl.DataFrame, contract: dict) -> pl.DataFrame:
    return frame.sort(
        ["date", contract["score_column"], "symbol"],
        descending=[False, True, False],
    )


def select_candidates(
    frame: pl.DataFrame,
    *,
    start: date,
    end: date,
    contract: dict,
    max_new_per_day: int,
) -> tuple[pl.DataFrame, int]:
    candidate = frame.filter(
        pl.col("date").is_between(start, end)
        & pl.col("exit_date").is_not_null()
        & (pl.col("exit_date") > pl.col("date"))
        & (pl.col("exit_date") <= end)
        & pl.col(contract["signal_column"]).fill_null(False)
        & pl.col(contract["score_column"]).is_finite()
        & (pl.col("entry_reason") == "ok")
        & (pl.col("exit_reason") == "ok")
        & pl.col("net_return").is_finite()
    )
    candidate_n = candidate.height
    if candidate.is_empty():
        return candidate, 0
    if contract["selection"] == "global":
        selected = _sort_candidates(candidate, contract).group_by(
            "date",
            maintain_order=True,
        ).head(max_new_per_day)
    elif contract["selection"] == "bucket_quota":
        pieces = []
        for bucket, quota in BUCKET_QUOTAS.items():
            sub = candidate.filter(pl.col("gap_bucket") == bucket)
            if sub.is_empty():
                continue
            pieces.append(
                _sort_candidates(sub, contract).group_by(
                    "date",
                    maintain_order=True,
                ).head(quota),
            )
        selected = pl.concat(pieces, how="diagonal_relaxed") if pieces else candidate.head(0)
    else:
        raise ValueError(f"Unknown selection: {contract['selection']}")
    return _sort_candidates(selected, contract), candidate_n


def _with_baseline(frame: pl.DataFrame) -> pl.DataFrame:
    resolved = frame.filter(
        (pl.col("entry_reason") == "ok")
        & (pl.col("exit_reason") == "ok")
        & pl.col("net_return").is_finite()
    )
    if resolved.is_empty():
        return resolved
    return resolved.with_columns(
        pl.col("net_return").mean().over(["date", "gap_bucket"]).alias("_baseline"),
        (pl.col("net_return") > 0)
        .mean()
        .over(["date", "gap_bucket"])
        .alias("_baseline_win"),
    ).with_columns(
        (pl.col("net_return") - pl.col("_baseline")).alias("incremental_return"),
        (
            (pl.col("net_return") > 0).cast(pl.Float64)
            - pl.col("_baseline_win")
        ).alias("win_increment"),
    )


def _cost_factors(parameters: dict) -> tuple[float, float]:
    commission = parameters["commission_bps"] / 10_000
    stamp_tax = parameters["stamp_tax_bps"] / 10_000
    slippage = parameters["slippage_bps"] / 10_000
    buy = (1 + slippage) * (1 + commission)
    sell = (1 - slippage) * (1 - commission - stamp_tax)
    return buy, sell


def simulate_daily_mark_portfolio(
    selected: pl.DataFrame,
    *,
    calendar: list[date],
    daily_closes: pl.DataFrame,
    start: date,
    end: date,
    parameters: dict | None = None,
) -> tuple[dict, list[dict], list[dict]]:
    params = {**PORTFOLIO_DEFAULTS, **(parameters or {})}
    if params["initial_capital"] <= 0:
        raise ValueError("initial_capital must be positive")
    if not 0 < params["position_pct"] <= 1:
        raise ValueError("position_pct must be in (0, 1]")
    if params["max_positions"] < 1 or params["max_new_per_day"] < 1:
        raise ValueError("Portfolio limits must be positive")
    if not 0 < params["max_exposure_pct"] <= 1:
        raise ValueError("max_exposure_pct must be in (0, 1]")
    if not 0 < params["capacity_pct"] <= 1:
        raise ValueError("capacity_pct must be in (0, 1]")
    buy_factor, sell_factor = _cost_factors(params)
    sessions = [day for day in calendar if start <= day <= end]
    if not sessions:
        raise ValueError("Portfolio period has no sessions")
    session_set = set(sessions)
    selected_rows = selected.to_dicts()
    for row in selected_rows:
        if row["exit_date"] not in session_set:
            raise ValueError(
                f"Exit date is outside the independent calendar: "
                f"{row['symbol']} {row['exit_date']}",
            )
    by_date: dict[date, list[dict]] = {}
    for row in selected_rows:
        by_date.setdefault(row["date"], []).append(row)
    close_map = {
        (row["symbol"], row["date"]): float(row["close"])
        for row in daily_closes.to_dicts()
    }

    cash = float(params["initial_capital"])
    positions: list[dict] = []
    filled: list[dict] = []
    curve: list[dict] = []
    rejected = {"no_slot": 0, "cash": 0, "exposure": 0, "capacity": 0, "minimum": 0}
    stale_marks = 0
    max_positions_used = 0

    for day in sessions:
        remaining = []
        for position in positions:
            if position["exit_date"] == day:
                proceeds = position["allocated"] * (1 + position["net_return"])
                cash += proceeds
                position["realized_return"] = position["net_return"]
                filled.append(position)
            elif position["exit_date"] < day:
                raise AssertionError("A position was not exited on its frozen date")
            else:
                remaining.append(position)
        positions = remaining

        marked_before = sum(position["mark_value"] for position in positions)
        equity_before = cash + marked_before
        for row in by_date.get(day, []):
            if len(positions) >= params["max_positions"]:
                rejected["no_slot"] += 1
                continue
            capacity = row["entry_vwap"] * row["entry_volume"]
            capacity *= params["capacity_pct"]
            if not np.isfinite(capacity) or capacity <= params["minimum_notional"]:
                rejected["capacity"] += 1
                continue
            exposure_room = max(
                0.0,
                equity_before * params["max_exposure_pct"] - marked_before,
            )
            target = equity_before * params["position_pct"]
            allocation = min(target, capacity, cash, exposure_room)
            if allocation <= 0:
                rejected["exposure"] += 1
                continue
            if allocation < params["minimum_notional"]:
                rejected["cash" if cash < params["minimum_notional"] else "minimum"] += 1
                continue
            shares = allocation / (row["entry_vwap"] * buy_factor)
            cash -= allocation
            mark_value = shares * row["entry_vwap"] * sell_factor
            positions.append({
                **row,
                "allocated": allocation,
                "shares": shares,
                "mark_value": mark_value,
            })
            marked_before += mark_value
            equity_before = cash + marked_before

        marked_after = 0.0
        for position in positions:
            close = close_map.get((position["symbol"], day))
            if close is None or not np.isfinite(close) or close <= 0:
                stale_marks += 1
            else:
                position["mark_value"] = position["shares"] * close * sell_factor
            marked_after += position["mark_value"]
        equity = cash + marked_after
        max_positions_used = max(max_positions_used, len(positions))
        curve.append({
            "date": day.isoformat(),
            "cash": round(cash, 2),
            "market_value": round(marked_after, 2),
            "equity": round(equity, 2),
            "open_positions": len(positions),
            "exposure": marked_after / equity if equity > 0 else 0.0,
        })

    if positions:
        raise AssertionError("Portfolio retained positions past the frozen period")
    equity_values = np.array(
        [params["initial_capital"], *[row["equity"] for row in curve]],
        dtype=float,
    )
    peaks = np.maximum.accumulate(equity_values)
    drawdown = equity_values / peaks - 1
    trade_returns = np.array(
        [row["realized_return"] for row in filled],
        dtype=float,
    )
    summary = {
        "status": "ok" if filled else "no_filled_trades",
        **params,
        "candidate_n": selected.height,
        "filled_n": len(filled),
        "total_return": float(cash / params["initial_capital"] - 1),
        "final_equity": float(cash),
        "mean_trade_return": float(trade_returns.mean()) if trade_returns.size else None,
        "win_rate": float((trade_returns > 0).mean()) if trade_returns.size else None,
        "max_drawdown_mtm": float(drawdown.min()) if drawdown.size else None,
        "mean_exposure": float(np.mean([row["exposure"] for row in curve]))
        if curve else None,
        "max_positions_used": max_positions_used,
        "stale_marks": stale_marks,
        "rejected": rejected,
    }
    return summary, filled, curve


def score_decile_diagnostics(events: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for period, start, end in PERIODS[:4]:
        resolved = _with_baseline(events.filter(pl.col("date").is_between(start, end)))
        resolved = resolved.filter(pl.col("combined_rank").is_finite())
        if resolved.is_empty():
            continue
        resolved = resolved.with_columns(
            (pl.col("combined_rank").clip(0, 1) * 10)
            .floor()
            .clip(0, 9)
            .cast(pl.Int64)
            .alias("score_decile"),
        )
        for scope in ["all", *GAP_BUCKETS]:
            frame = (
                resolved
                if scope == "all"
                else resolved.filter(pl.col("gap_bucket") == scope)
            )
            if frame.is_empty():
                continue
            grouped = frame.group_by("score_decile").agg(
                pl.len().alias("n"),
                pl.col("date").n_unique().alias("event_days"),
                pl.col("net_return").mean().alias("mean_net_return"),
                pl.col("incremental_return").mean().alias("mean_incremental_return"),
                (pl.col("net_return") > 0).mean().alias("win_rate"),
            ).sort("score_decile")
            rows.extend({"period": period, "scope": scope, **row} for row in grouped.to_dicts())
    return pl.DataFrame(rows)


def decision_gate(selected_results: list[dict], portfolio: dict) -> dict:
    checks = {}
    for period in DECISION_GATE["periods"]:
        selected = next(
            row for row in selected_results
            if row["period"] == period and row["variant"] == PRIMARY_VARIANT
        )
        interval = (selected.get("cluster_bootstrap_95") or {}).get(
            "mean_incremental_return",
        )
        result = portfolio[PRIMARY_VARIANT][period]
        checks[period] = {
            "selected_incremental_ci_lower_positive": (
                interval is not None and interval[0] > 0
            ),
            "portfolio_total_return_positive": (
                result.get("total_return") is not None
                and result["total_return"] > 0
            ),
            "portfolio_max_drawdown_above_floor": (
                result.get("max_drawdown_mtm") is not None
                and result["max_drawdown_mtm"]
                >= DECISION_GATE["portfolio_max_drawdown_floor"]
            ),
            "no_stale_marks": result.get("stale_marks", 1) == 0,
        }
        checks[period]["passed"] = all(checks[period].values())
    return {
        "primary_variant": PRIMARY_VARIANT,
        "rules": DECISION_GATE,
        "periods": checks,
        "passed": all(row["passed"] for row in checks.values()),
    }


def write_results(path: Path, report: dict) -> None:
    lines = [
        "# Auction portfolio-construction study",
        "",
        f"Algorithm: `{VERSION}`.",
        "",
        "Scope: frozen 2%-8% signals, D+3, daily mark-to-market.",
        "",
        "## Selected event results",
        "",
        "| Period | Variant | Selected | Net | Delta | Delta 95% CI |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in report["selected_results"]:
        interval = (row.get("cluster_bootstrap_95") or {}).get(
            "mean_incremental_return",
        )
        interval_text = (
            f"{interval[0] * 100:.3f}% to {interval[1] * 100:.3f}%"
            if interval else "NA"
        )
        lines.append(
            f"| {row['period']} | {row['variant']} | {row['n']} | "
            f"{row['mean_net_return'] * 100:.3f}% | "
            f"{row['mean_incremental_return'] * 100:.3f}% | {interval_text} |",
        )
    lines.extend([
        "",
        "## Daily mark-to-market portfolio",
        "",
        "| Period | Variant | Filled | Total | Mean trade | Max drawdown | Mean exposure |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for variant, periods in report["portfolio"].items():
        for period, row in periods.items():
            lines.append(
                f"| {period} | {variant} | {row['filled_n']} | "
                f"{row['total_return'] * 100:.3f}% | "
                f"{row['mean_trade_return'] * 100:.3f}% | "
                f"{row['max_drawdown_mtm'] * 100:.3f}% | "
                f"{row['mean_exposure'] * 100:.3f}% |",
            )
    lines.extend([
        "",
        "## Decision gate",
        "",
        f"Primary variant: `{report['decision_gate']['primary_variant']}`.",
        "",
        f"Passed: `{report['decision_gate']['passed']}`.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_study(args: argparse.Namespace) -> dict:
    if args.output.exists():
        raise FileExistsError("Use a NEW output directory; existing runs are never overwritten")
    if args.bootstrap_samples < 0:
        raise ValueError("bootstrap_samples must be non-negative")
    started = time.perf_counter()
    event_stat = [args.events.stat().st_size, args.events.stat().st_mtime_ns]
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.mkdir(parents=True)
    _write_json(args.output / "manifest.json", {
        "status": "running",
        "version": VERSION,
        "script_sha256": script_hash,
        "parameters": vars(args),
        "portfolio_defaults": PORTFOLIO_DEFAULTS,
        "bucket_quotas": BUCKET_QUOTAS,
        "variants": VARIANTS,
        "primary_variant": PRIMARY_VARIANT,
        "decision_gate": DECISION_GATE,
        "created_at": datetime.now().isoformat(),
    })
    events = load_events(args.events)
    selections: dict[str, dict[str, tuple[pl.DataFrame, int]]] = {}
    selected_results = []
    selected_rows_for_closes = []
    for period, start, end in PERIODS[:4]:
        period_frame = events.filter(pl.col("date").is_between(start, end))
        baseline = _with_baseline(period_frame)
        selections[period] = {}
        for variant, contract in VARIANTS.items():
            selected, candidate_n = select_candidates(
                period_frame,
                start=start,
                end=end,
                contract=contract,
                max_new_per_day=PORTFOLIO_DEFAULTS["max_new_per_day"],
            )
            selections[period][variant] = (selected, candidate_n)
            selected_rows_for_closes.append(selected.select("symbol", "date", "exit_date"))
            exact = baseline.join(
                selected.select("symbol", "date"),
                on=["symbol", "date"],
                how="semi",
            )
            selected_results.append({
                "period": period,
                "variant": variant,
                "candidate_n": candidate_n,
                "selected_n": selected.height,
                **summarize(
                    exact,
                    bootstrap_samples=args.bootstrap_samples,
                    seed=args.seed,
                ),
            })
    symbols = sorted(set(pl.concat(selected_rows_for_closes)["symbol"].to_list()))
    start_date = min(
        row["date"].min()
        for period_rows in selections.values()
        for row, _ in period_rows.values()
        if not row.is_empty()
    )
    end_date = max(
        row["exit_date"].max()
        for period_rows in selections.values()
        for row, _ in period_rows.values()
        if not row.is_empty()
    )
    calendar = load_calendar(args.data_dir, start_date, end_date)
    daily_closes = load_daily_closes(args.data_dir, symbols, start_date, end_date)
    portfolio: dict[str, dict] = {}
    trades: list[dict] = []
    curves: list[dict] = []
    for period, start, end in PERIODS[:4]:
        for variant in VARIANTS:
            selected, _ = selections[period][variant]
            summary, filled, curve = simulate_daily_mark_portfolio(
                selected,
                calendar=calendar,
                daily_closes=daily_closes,
                start=start,
                end=end,
            )
            portfolio.setdefault(variant, {})[period] = summary
            trades.extend({"period": period, "variant": variant, **row} for row in filled)
            curves.extend({"period": period, "variant": variant, **row} for row in curve)
    deciles = score_decile_diagnostics(events)
    report = {
        "version": VERSION,
        "scope": {
            "gap_buckets": GAP_BUCKETS,
            "horizon": 3,
            "event_rows": events.height,
            "event_days": events["date"].n_unique(),
        },
        "bucket_quotas": BUCKET_QUOTAS,
        "variants": VARIANTS,
        "portfolio_defaults": PORTFOLIO_DEFAULTS,
        "decision_gate": decision_gate(selected_results, portfolio),
        "selected_results": selected_results,
        "portfolio": portfolio,
        "score_decile_rows": deciles.height,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "warnings": [
            "Signal scores and variant definitions are frozen from the multifactor study.",
            "Validation and stress results do not alter quotas, position sizing or score definitions.",
            "Daily marks use raw daily closes and estimated liquidation costs.",
            "D+3 exits are fixed at the observed 09:30-09:35 VWAP.",
        ],
    }
    if [args.events.stat().st_size, args.events.stat().st_mtime_ns] != event_stat:
        raise RuntimeError("Input event table changed during study")
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != script_hash:
        raise RuntimeError("Study source changed during execution")
    _write_json(args.output / "study.json", report)
    _write_json(args.output / "manifest.json", {
        **json.loads((args.output / "manifest.json").read_text(encoding="utf-8")),
        "status": "complete",
        "inputs_unchanged": True,
        "source_unchanged": True,
        "elapsed_seconds": report["elapsed_seconds"],
    })
    flat_selected = [
        {
            **{
                key: (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                )
                for key, value in row.items()
            },
        }
        for row in selected_results
    ]
    pl.DataFrame(flat_selected, infer_schema_length=None).write_csv(
        args.output / "selected_results.csv",
    )
    flat_portfolio = [
        {
            "variant": variant,
            "period": period,
            **{
                key: (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                )
                for key, value in row.items()
            },
        }
        for variant, periods in portfolio.items()
        for period, row in periods.items()
    ]
    pl.DataFrame(flat_portfolio, infer_schema_length=None).write_csv(
        args.output / "portfolio.csv",
    )
    deciles.write_csv(args.output / "score_deciles.csv")
    pl.DataFrame(trades, infer_schema_length=None).write_csv(args.output / "trades.csv")
    pl.DataFrame(curves, infer_schema_length=None).write_csv(args.output / "equity_curve.csv")
    write_results(args.output / "RESULTS.md", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args()
    report = run_study(args)
    print(json.dumps({
        "event": "complete",
        "gate_passed": report["decision_gate"]["passed"],
        "elapsed_seconds": report["elapsed_seconds"],
    }), flush=True)


if __name__ == "__main__":
    main()
