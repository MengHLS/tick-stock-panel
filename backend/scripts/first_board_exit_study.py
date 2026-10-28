"""Two-dimensional first-board entry and exit study using the production matcher.

Run from backend with --data-dir, --task-id and a new --output directory.
The study freezes two entry definitions and compares preregistered exits.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import time
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from app.backtest.engine import (
    BacktestEngine,
    MatcherConfig,
    SimulationOptions,
)
from app.backtest.matrix import (
    MarketDataMatrix,
    MatrixPipelineConfig,
    SignalMatrix,
    build_basic_filter_mask,
    build_market_matrix_from_signals,
    build_matrix_score,
    make_signal_matrix,
    matrix_feature,
    slice_market_data_matrix,
    slice_signal_matrix,
    valid_shift,
)
from app.backtest.strategy import (
    StrategyBacktestService,
    StrategyDependencyResolver,
)
from app.strategy.scoring import effective_scoring, effective_scoring_directions
from app.tickflow.repository import DataStore, KlineRepository
from scripts.first_board_entry_study import (
    _load_source,
    apply_execution_caps,
    build_event_table,
    clean_json,
    event_signals,
    policy_mask,
    write_json,
)

ENTRY_POLICIES = {
    "strict_combined": (
        "Stage 5, recent anchor, pre-signal position<=0.6, ret20<=20%, "
        "MA20 bias<=15%, close/P-1<=3%"
    ),
    "low_start": "Any first board, pre-signal position<=0.4, ret20<=10%",
}


@dataclass(frozen=True)
class ExitProtocol:
    id: str
    description: str
    stop_loss_pct: float | None = -0.08
    max_hold_days: int | None = 30
    trailing_stop_pct: float | None = None
    trailing_take_profit_activate_pct: float | None = None
    trailing_take_profit_drawdown_pct: float | None = None
    use_ma20_breakdown: bool = False


EXIT_PROTOCOLS = (
    ExitProtocol(
        id="baseline_8pct_30d",
        description="Baseline: -8% stop and 30 holding days",
    ),
    ExitProtocol(
        id="fixed_hold_5d",
        description="Time exit: -8% stop and 5 holding days",
        max_hold_days=5,
    ),
    ExitProtocol(
        id="fixed_hold_10d",
        description="Time exit: -8% stop and 10 holding days",
        max_hold_days=10,
    ),
    ExitProtocol(
        id="ma20_breakdown",
        description=(
            "Trend-failure proxy: close crosses below MA20, next-open exit, "
            "-8% stop and 30 holding days"
        ),
        use_ma20_breakdown=True,
    ),
    ExitProtocol(
        id="trailing_high_8pct",
        description=(
            "Trailing exit: 8% below recorded high, -8% stop and 30 holding days"
        ),
        trailing_stop_pct=0.08,
    ),
    ExitProtocol(
        id="profit_protect_3pct_6pct",
        description=(
            "Profit protection: after +3% peak, exit 6% below peak, "
            "-8% stop and 30 holding days"
        ),
        trailing_take_profit_activate_pct=0.03,
        trailing_take_profit_drawdown_pct=0.06,
    ),
)

EXECUTION_NAME = "gap3"
MAX_ENTRY_GAP = 0.03


def periods_for(start: date, end: date) -> list[tuple[str, date, date]]:
    if start >= date(2023, 12, 31) or end < date(2025, 1, 1):
        raise ValueError("The registered study periods require 2023..2025 coverage")
    return [
        ("full", start, end),
        ("development", start, date(2023, 12, 31)),
        ("validation_2024", date(2024, 1, 1), date(2024, 12, 31)),
        ("retrospective_2025_2026", date(2025, 1, 1), end),
    ]


def ma20_breakdown_signal(
    close: np.ndarray,
    ma20: np.ndarray,
    valid: np.ndarray | None = None,
) -> np.ndarray:
    """Return the first close below MA20 after a close at or above it."""
    close = np.asarray(close, dtype=float)
    ma20 = np.asarray(ma20, dtype=float)
    if close.ndim != 2 or close.shape != ma20.shape:
        raise ValueError("close and ma20 must have the same 2D shape")
    if valid is None:
        valid = np.isfinite(close) & np.isfinite(ma20)
    else:
        valid = np.asarray(valid, dtype=bool) & np.isfinite(close) & np.isfinite(ma20)
    previous_close = valid_shift(close, 1, valid)
    previous_ma20 = valid_shift(ma20, 1, valid)
    return (
        valid
        & (close < ma20)
        & (previous_close >= previous_ma20)
        & np.isfinite(previous_close)
        & np.isfinite(previous_ma20)
    )


def protocol_signals(
    market: MarketDataMatrix,
    entry_signals: SignalMatrix,
    protocol: ExitProtocol,
) -> SignalMatrix:
    if protocol.use_ma20_breakdown:
        ma20 = matrix_feature(market, "ma20")
        exit_ = ma20_breakdown_signal(
            market.close,
            ma20,
            np.isfinite(market.close) & np.isfinite(ma20),
        )
        exit_ids = ("signal_ma20_breakdown",)
    else:
        exit_ = np.zeros(market.shape, dtype=bool)
        exit_ids = ()
    exit_codes = np.where(exit_, 0, -1).astype(np.int16)
    return make_signal_matrix(
        market.shape,
        entry=entry_signals.entry,
        exit=exit_.astype(np.uint8),
        score=entry_signals.score,
        entry_signal_code=entry_signals.entry_signal_code,
        exit_signal_code=exit_codes,
        entry_signal_ids=entry_signals.entry_signal_ids,
        exit_signal_ids=exit_ids,
    )


def protocol_matcher(
    base: MatcherConfig,
    protocol: ExitProtocol,
) -> MatcherConfig:
    return replace(
        base,
        stop_loss_pct=protocol.stop_loss_pct,
        max_hold_days=protocol.max_hold_days,
        trailing_stop_pct=protocol.trailing_stop_pct,
        trailing_take_profit_activate_pct=(
            protocol.trailing_take_profit_activate_pct
        ),
        trailing_take_profit_drawdown_pct=(
            protocol.trailing_take_profit_drawdown_pct
        ),
        trailing_peak_price="high",
        exit_signal_requires_profit=False,
        hold_extension_policy=None,
    )


def entry_signal_matrix(
    market: MarketDataMatrix,
    events: pl.DataFrame,
    pipeline_config: MatrixPipelineConfig,
    entry_name: str,
    top_rank: int,
) -> tuple[SignalMatrix, np.ndarray]:
    raw_mask = policy_mask(events, entry_name)
    filtered = raw_mask & events["basic_eligible"].to_numpy()
    signals = event_signals(market, events, filtered, top_rank)
    score = build_matrix_score(
        market,
        signals.entry.astype(bool),
        pipeline_config.scoring,
        pipeline_config.order_by,
        pipeline_config.descending,
        fallback=signals.score,
        directions=pipeline_config.scoring_directions,
    )
    return (
        make_signal_matrix(
            market.shape,
            entry=signals.entry,
            score=score,
            entry_signal_code=signals.entry_signal_code,
            entry_signal_ids=signals.entry_signal_ids,
        ),
        raw_mask,
    )


def _rate(trades: list[dict[str, Any]], reason: str) -> float | None:
    if not trades:
        return None
    return sum(trade["exit_reason"] == reason for trade in trades) / len(trades)


def _distribution(values: list[Any]) -> dict[str, float | int | None]:
    numbers = np.array(
        [value for value in values if value is not None and np.isfinite(value)],
        dtype=float,
    )
    if not numbers.size:
        return {"n": 0, "median": None, "q25": None, "q75": None}
    return {
        "n": int(numbers.size),
        "median": float(np.median(numbers)),
        "q25": float(np.quantile(numbers, 0.25)),
        "q75": float(np.quantile(numbers, 0.75)),
    }


def summarize_run(
    entry_name: str,
    protocol: ExitProtocol,
    period_name: str,
    period_start: date,
    period_end: date,
    ledger: dict[str, int],
    stats: dict[str, Any],
    trades: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
) -> dict[str, Any]:
    pnl_amounts = np.array(
        [float(trade["pnl_amount"]) for trade in trades],
        dtype=float,
    )
    gross_profit = float(pnl_amounts[pnl_amounts > 0].sum()) if trades else 0.0
    gross_loss = float(-pnl_amounts[pnl_amounts < 0].sum()) if trades else 0.0
    return {
        "entry": entry_name,
        "exit_protocol": protocol.id,
        "period": period_name,
        "start": str(period_start),
        "end": str(period_end),
        **ledger,
        **{
            key: stats.get(key)
            for key in (
                "total_return",
                "annual_return",
                "max_drawdown",
                "sharpe",
                "n_trades",
                "win_rate",
                "profit_factor",
                "pending_exit_positions",
            )
        },
        "closed_trades": len(trades),
        "stop_loss_rate": _rate(trades, "stop_loss"),
        "signal_exit_rate": _rate(trades, "signal"),
        "trailing_stop_rate": _rate(trades, "trailing_stop"),
        "trailing_take_profit_rate": _rate(trades, "trailing_take_profit"),
        "max_hold_rate": _rate(trades, "max_hold"),
        "end_rate": _rate(trades, "end"),
        "avg_trade_return": (
            float(np.mean([trade["pnl_pct"] for trade in trades]))
            if trades
            else None
        ),
        "median_trade_return": (
            float(np.median([trade["pnl_pct"] for trade in trades]))
            if trades
            else None
        ),
        "gross_profit_loss_ratio": (
            gross_profit / gross_loss if gross_loss > 0 else None
        ),
        "total_pnl_amount": float(pnl_amounts.sum()) if trades else 0.0,
        "avg_duration": (
            float(np.mean([trade["duration"] for trade in trades]))
            if trades
            else None
        ),
        "median_duration": (
            float(np.median([trade["duration"] for trade in trades]))
            if trades
            else None
        ),
        "median_position_before": _distribution(
            [audit["position_before"] for audit in audits]
        )["median"],
        "median_ret20": _distribution(
            [audit["ret20_signal"] for audit in audits]
        )["median"],
        "median_entry_gap": _distribution(
            [audit["entry_gap"] for audit in audits]
        )["median"],
        "median_distance_to_L": _distribution(
            [audit["distance_to_L"] for audit in audits]
        )["median"],
        "mean_exposure": (
            float(np.mean([point["exposure"] for point in equity_curve]))
            if equity_curve else None
        ),
        "invested_session_fraction": (
            float(np.mean([point["positions"] > 0 for point in equity_curve]))
            if equity_curve else None
        ),
    }


def _source_hashes(strategy_path: Path) -> dict[str, str]:
    backend = Path(__file__).resolve().parents[1]
    files = [
        Path(__file__).resolve(),
        backend / "scripts/first_board_entry_study.py",
        strategy_path,
        backend / "app/factors/event_chain.py",
        backend / "app/strategy/research/factor_rank_research.py",
        backend / "app/strategy/scoring.py",
        backend / "app/backtest/matrix.py",
        backend / "app/backtest/strategy.py",
        backend / "app/backtest/engine.py",
    ]
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
    }


def assert_reference_run(
    reference: dict[str, Any],
    trades: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
    ledger: dict[str, int],
) -> None:
    if reference["trades"] != trades or reference["equity_curve"] != equity_curve:
        raise AssertionError("Baseline trades/equity do not reproduce the certified entry study")
    if any(reference["summary"][key] != value for key, value in ledger.items()):
        raise AssertionError("Baseline admission ledger differs from the certified entry study")


def run_study(
    data_dir: Path, task_id: str, output: Path, entry_study: Path,
) -> None:
    if output.exists():
        raise FileExistsError("Use a new output directory; frozen runs are never overwritten")
    item, query, overrides, strategy, params, basic, base_matcher = _load_source(
        data_dir,
        task_id,
    )
    reference_manifest = json.loads(
        (entry_study / "manifest.json").read_text(encoding="utf-8"),
    )
    reference_checks = reference_manifest.get("checks", {})
    if not reference_manifest.get("finished_at") or not all(
        reference_checks.get(key) is True
        for key in (
            "generation_unchanged", "source_unchanged",
            "all_trades_matched", "entry_cap_conservation",
        )
    ):
        raise ValueError("The reference entry study is not certified")
    if reference_manifest["source_config"] != query:
        raise ValueError("Source configuration differs from the reference entry study")
    start = date.fromisoformat(query["start"])
    end = date.fromisoformat(query["end"])
    periods = periods_for(start, end)
    top_rank = int(params["top_rank"])
    hashes = _source_hashes(strategy.file_path)

    output.mkdir(parents=True)
    (output / "runs").mkdir()
    (output / "source_strategy.py").write_text(
        strategy.file_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    manifest: dict[str, Any] = {
        "study": "first_board_entry_exit_v1",
        "created_at": datetime.now().isoformat(),
        "source_task": item,
        "source_config": query,
        "source_hashes": hashes,
        "entries": ENTRY_POLICIES,
        "exit_protocols": [asdict(protocol) for protocol in EXIT_PROTOCOLS],
        "execution": {
            "id": EXECUTION_NAME,
            "max_gap": MAX_ENTRY_GAP,
            "description": "Reject actual T+1 open more than 3% above T close",
        },
        "periods": periods,
        "base_matcher": asdict(base_matcher),
        "basic_filter": basic,
        "params": params,
        "reference_entry_study": str(entry_study),
        "reference_manifest_sha256": hashlib.sha256(
            (entry_study / "manifest.json").read_bytes(),
        ).hexdigest(),
        "selection": (
            "No best variant is selected automatically; every entry x exit x period "
            "row is reported"
        ),
        "validation": (
            "Temporal retrospective comparison, not pristine out-of-sample validation"
        ),
        "tie_order": "Stable asset-axis order retained for the daily top-rank cap",
        "outer_scoring": (
            "The source scoring and direction remain common; ranking exits are not used"
        ),
        "universe_limitations": (
            "Historical survivorship, ST status and share-capital accuracy are not "
            "independently certified"
        ),
        "exit_semantics": (
            "All exits keep the -8% emergency stop; max_hold uses production elapsed "
            "holding sessions (entry day excluded). Peaks use previously recorded highs. "
            "MA20 crossing is a trend-failure proxy, not a per-entry P/L structural exit. "
            "A +3% activation with 6% drawdown can still close at a loss. Production "
            "risk-before-signal/max-hold priority is retained; daily bars do not resolve "
            "intraday price ordering."
        ),
    }
    write_json(output / "manifest.json", manifest)
    print("FROZEN " + str(output / "manifest.json"), flush=True)

    engine = BacktestEngine(KlineRepository(DataStore(data_dir)))
    generation = engine.data_generation()
    if generation != reference_manifest["generation"]:
        raise ValueError("Data generation differs from the certified entry study")
    plan = StrategyDependencyResolver().resolve(
        strategy,
        params=params,
        basic_filter=basic,
        entry_signals=strategy.entry_signals,
        exit_signals=strategy.exit_signals,
        overrides=overrides,
    )
    market = engine.load_market_data_matrix_for_backtest(
        None,
        start - timedelta(days=520),
        end,
        plan,
        expected_generation=generation,
    )
    manifest["generation"] = generation
    manifest["matrix_shape"] = market.shape
    manifest["matrix_nbytes"] = market.nbytes
    write_json(output / "manifest.json", manifest)
    print(f"LOADED {market.shape} {market.nbytes / 2**20:.0f} MiB", flush=True)

    events = build_event_table(market)
    basic_mask = build_basic_filter_mask(market, basic)
    overlay_mask = np.ones(market.shape, dtype=bool)
    if overrides.get("overlay_filter"):
        overlay_mask, overlay_error = StrategyBacktestService._overlay_matrix_mask(
            market,
            overrides["overlay_filter"],
        )
        if overlay_error is not None:
            raise ValueError(overlay_error)
    times = events["time_id"].to_numpy()
    assets = events["asset_id"].to_numpy()
    events = events.with_columns(
        pl.Series(
            "basic_eligible",
            (basic_mask & overlay_mask)[times, assets],
        )
    )
    events.write_parquet(output / "events.parquet")
    events.write_csv(output / "events.csv")
    del basic_mask, overlay_mask

    pipeline_config = MatrixPipelineConfig(
        basic_filter=basic,
        scoring=effective_scoring(strategy.meta.get("scoring"), overrides),
        order_by=strategy.meta.get("order_by"),
        descending=True,
        scoring_directions=effective_scoring_directions(overrides),
    )
    formal_events = (
        (events["date"] >= str(start)) & (events["date"] <= str(end))
    ).to_numpy()
    event_lookup = {
        (row["symbol"], row["date"]): row for row in events.to_dicts()
    }

    rows: list[dict[str, Any]] = []
    candidate_counts: list[dict[str, Any]] = []
    all_trade_audits: list[dict[str, Any]] = []
    entry_signals: dict[str, SignalMatrix] = {}
    baseline_trades: dict[tuple[str, str], dict[tuple[str, str], dict]] = {}
    baseline_checks: list[str] = []
    for entry_name, description in ENTRY_POLICIES.items():
        signals, raw_mask = entry_signal_matrix(
            market,
            events,
            pipeline_config,
            entry_name,
            top_rank,
        )
        entry_signals[entry_name] = signals
        eligible = events["basic_eligible"].to_numpy()
        candidate_counts.append({
            "entry": entry_name,
            "description": description,
            "raw_events": int((raw_mask & formal_events).sum()),
            "basic_eligible": int(
                (raw_mask & formal_events & eligible).sum()
            ),
            "signals_after_daily_limit": int(
                signals.entry[times[formal_events], assets[formal_events]].sum()
            ),
        })

    for entry_name in ENTRY_POLICIES:
        base_signals = entry_signals[entry_name]
        for period_name, period_start, period_end in periods:
            ids = [
                index
                for index, label in enumerate(market.timestamp_labels)
                if str(period_start) <= label[:10] <= str(period_end)
            ]
            if not ids:
                raise ValueError(f"No market rows for period {period_name}")
            start_id, stop_id = ids[0], ids[-1] + 1
            sub_market = slice_market_data_matrix(market, start_id, stop_id)
            for protocol in EXIT_PROTOCOLS:
                # Calculate the indicator and crossing on warmed full history,
                # then slice before delaying: no pre-period signal is filled.
                signals = slice_signal_matrix(
                    protocol_signals(market, base_signals, protocol),
                    start_id, stop_id,
                )
                matrix = build_market_matrix_from_signals(
                    sub_market,
                    signals,
                    entry_delay_bars=1,
                    exit_delay_bars=1,
                )
                gated, ledger = apply_execution_caps(
                    matrix,
                    {},
                    max_gap=MAX_ENTRY_GAP,
                )
                matcher = protocol_matcher(base_matcher, protocol)
                result = engine.simulate_market_matrix(
                    gated,
                    matcher,
                    options=SimulationOptions(
                        include_monte_carlo=False,
                        include_per_symbol_stats=False,
                        include_return_distribution=False,
                    ),
                )
                trades = [asdict(trade) for trade in result.trades]
                if protocol.id == "baseline_8pct_30d":
                    reference_file = (
                        entry_study / "runs"
                        / f"{entry_name}__gap3__{period_name}.json"
                    )
                    reference = json.loads(reference_file.read_text(encoding="utf-8"))
                    assert_reference_run(reference, trades, result.equity_curve, ledger)
                    baseline_checks.append(f"{entry_name}__{period_name}")
                    baseline_trades[entry_name, period_name] = {
                        (trade["symbol"], trade["entry_signal_date"]): trade
                        for trade in trades
                    }
                audits: list[dict[str, Any]] = []
                for trade in trades:
                    event = event_lookup.get(
                        (trade["symbol"], trade["entry_signal_date"])
                    )
                    if event is None:
                        raise AssertionError(
                            "Executed trade has no frozen signal-day descriptor"
                        )
                    asset = market.symbols.index(trade["symbol"])
                    entry_time = market.timestamp_labels.index(trade["entry_date"])
                    entry_open = float(market.open[entry_time, asset])
                    audit = {
                        "entry": entry_name,
                        "exit_protocol": protocol.id,
                        "period": period_name,
                        **trade,
                        **{
                            key: event[key]
                            for key in (
                                "nearest_anchor_date",
                                "nearest_stage",
                                "anchor_date",
                                "P",
                                "P_date",
                                "L",
                                "L_date",
                                "recursion_steps",
                                "stage",
                                "anchor_distance",
                                "above_P",
                                "pullback",
                                "position_before",
                                "position_signal",
                                "ret20_signal",
                                "bias_ma20",
                            )
                        },
                        "entry_gap": entry_open / event["close"] - 1,
                        "entry_above_P": (
                            entry_open / event["P"] - 1
                            if np.isfinite(event["P"])
                            else None
                        ),
                        "distance_to_L": (
                            1 - event["L"] / entry_open
                            if np.isfinite(event["L"])
                            else None
                        ),
                    }
                    audits.append(audit)
                all_trade_audits.extend(audits)
                summary = summarize_run(
                    entry_name,
                    protocol,
                    period_name,
                    period_start,
                    period_end,
                    ledger,
                    result.stats,
                    trades,
                    audits,
                    result.equity_curve,
                )
                original = baseline_trades[entry_name, period_name]
                current = {
                    (trade["symbol"], trade["entry_signal_date"]): trade
                    for trade in trades
                }
                common = original.keys() & current.keys()
                summary.update({
                    "shared_baseline_entries": len(common),
                    "new_entries_vs_baseline": len(current.keys() - original.keys()),
                    "omitted_baseline_entries": len(original.keys() - current.keys()),
                    "mean_return_delta_shared_entries": (
                        float(np.mean([
                            current[key]["pnl_pct"] - original[key]["pnl_pct"]
                            for key in common
                        ])) if common else None
                    ),
                })
                rows.append(clean_json(summary))
                key = f"{entry_name}__{protocol.id}__{period_name}"
                write_json(
                    output / "runs" / f"{key}.json",
                    {
                        "summary": summary,
                        "stats": result.stats,
                        "trades": trades,
                        "equity_curve": result.equity_curve,
                    },
                )
                write_json(output / "results.json", rows)
                print(
                    json.dumps(clean_json(summary), ensure_ascii=True),
                    flush=True,
                )
                del signals, matrix, gated, result
            del sub_market
            gc.collect()

    engine.assert_data_generation("stock", generation)
    if hashes != _source_hashes(strategy.file_path):
        raise RuntimeError(
            "Source code changed during the study; results are not certified"
        )
    if len(rows) != 48 or len(baseline_checks) != 8:
        raise AssertionError("Incomplete trial matrix or baseline reproduction")

    pl.DataFrame(rows, infer_schema_length=None).write_csv(output / "results.csv")
    pl.DataFrame(candidate_counts).write_csv(output / "candidate_counts.csv")
    pl.DataFrame(
        all_trade_audits,
        infer_schema_length=None,
    ).write_csv(output / "trades.csv")
    manifest["finished_at"] = datetime.now().isoformat()
    manifest["checks"] = {
        "generation_unchanged": True,
        "source_unchanged": True,
        "trial_rows": len(rows),
        "all_trades_matched": True,
        "entry_cap_conservation": all(
            row["before"] == row["accepted"] + row["rejected"] for row in rows
        ),
        "trade_rows": len(all_trade_audits),
        "reference_baselines_reproduced": baseline_checks,
    }
    write_json(output / "manifest.json", manifest)
    print("COMPLETE " + str(output), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--entry-study", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    run_study(args.data_dir, args.task_id, args.output, args.entry_study)
    print(f"ELAPSED {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
