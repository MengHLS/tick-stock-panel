"""Reproducible first-board entry study using the production matrix matcher.

Run from backend with --data-dir, --task-id and a new --output directory.
No strategy files, overrides, providers or price partitions are modified.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import time
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import numpy as np
import polars as pl

from app.backtest.engine import BacktestEngine, MatcherConfig, SimulationOptions
from app.backtest.matrix import (
    MarketDataMatrix,
    MarketMatrix,
    MatrixPipelineConfig,
    MatrixStrategyPipeline,
    SignalMatrix,
    build_market_matrix_from_signals,
    make_signal_matrix,
    matrix_feature,
    slice_market_data_matrix,
    slice_signal_matrix,
    valid_rolling_max,
    valid_rolling_min,
    valid_shift,
)
from app.backtest.strategy import StrategyBacktestService, StrategyDependencyResolver
from app.custom.first_board_event_chain.compute import (
    DEFAULT_EVENT_CHAIN_CONFIG,
    _evaluate_anchor,
    compute_event_chain_outputs,
)
from app.strategy.engine import StrategyEngine
from app.strategy.scoring import effective_scoring, effective_scoring_directions
from app.tickflow.repository import DataStore, KlineRepository

POLICIES = {
    "legacy_rank": "Original generated ranking strategy, including rank exits",
    "same_entries_fixed_exit": "Original entries, remove ranking exits",
    "strict_event": "Stage 5 directly; no rank threshold; common fixed exits",
    "strict_recent": "Stage 5 and anchor distance <=30 sessions",
    "strict_context": "Stage 5, pre-signal position240 <=0.6, pre-signal ret20 <=20%",
    "strict_not_extended": "Stage 5, signal close/MA20-1 <=15%, close/P-1 <=3%",
    "strict_combined": "Recent + context + not-extended restrictions",
    "low_start": "Any first board, pre-signal position240 <=0.4, ret20 <=10%",
    "reattack": (
        "Stage 3/5, anchor<=30, anchor pre-position<=0.6, target pre-position<=0.6, "
        "ret20<=20%, bias<=15%, -10%<=close/P-1<=3%, 5%<=pullback<=20%"
    ),
    "high_breakout": "Stage 5 with pre-signal position240 >=0.8; descriptive contrast",
}
EXECUTIONS = {
    "unrestricted": {"max_gap": None, "max_above_reference": None},
    "gap3": {"max_gap": 0.03, "max_above_reference": None},
    "gap3_reference3": {"max_gap": 0.03, "max_above_reference": 0.03},
}


def clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, (date, datetime, Path)):
        return str(value)
    if isinstance(value, np.generic):
        return clean_json(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(clean_json(value), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def build_event_table(market: MarketDataMatrix) -> pl.DataFrame:
    """Sparse event descriptors, including nearest and selected anchor audits."""
    consecutive = market.field("consecutive_limit_ups")
    pieces = []
    for asset in range(market.shape[1]):
        indices = np.flatnonzero(consecutive[:, asset] == 1)
        if not indices.size:
            continue
        arrays = [
            x[:, asset:asset + 1]
            for x in (market.open, market.high, market.low, market.close, consecutive)
        ]
        result = compute_event_chain_outputs(*arrays)
        close = market.close[:, asset]
        high = market.high[:, asset]
        low = market.low[:, asset]
        price_valid = np.logical_and.reduce([
            np.isfinite(x[:, asset]) & (x[:, asset] > 0)
            for x in (market.open, market.high, market.low, market.close)
        ])
        records = []
        for event_number, target in enumerate(indices):
            row: dict[str, Any] = {
                "time_id": int(target), "asset_id": asset,
                "symbol": market.symbols[asset], "date": market.timestamp_labels[target][:10],
                "close": float(close[target]),
                "stage": float(result["first_board_chain_stage"][target, 0]),
                "anchor_distance": float(result["first_board_chain_anchor_distance"][target, 0]),
                "pullback": float(result["first_board_chain_pullback_pct"][target, 0]),
                "above_P": float(result["first_board_chain_target_above_reference_pct"][target, 0]),
                "nearest_anchor_date": None, "nearest_stage": None,
                "anchor_date": None, "P_date": None, "L_date": None,
                "first_break_date": None, "recursion_steps": None,
                "P": float("nan"), "L": float("nan"),
            }
            if event_number:
                nearest = int(indices[event_number - 1])
                row["nearest_anchor_date"] = market.timestamp_labels[nearest][:10]
                nearest_state = _evaluate_anchor(
                    nearest, int(target), high, low, close, price_valid,
                    DEFAULT_EVENT_CHAIN_CONFIG,
                )
                row["nearest_stage"] = nearest_state.stage
            distance = row["anchor_distance"]
            if np.isfinite(distance):
                anchor = int(target - distance)
                row["anchor_date"] = market.timestamp_labels[anchor][:10]
                row["recursion_steps"] = int(
                    np.searchsorted(indices, target) - np.searchsorted(indices, anchor),
                )
                if np.isfinite(row["above_P"]):
                    row["P"] = float(close[target] / (1 + row["above_P"]))
                    row["L"] = row["P"] * (1 - row["pullback"])
                    falls = np.flatnonzero(close[anchor + 1:target] < close[anchor:target - 1])
                    if falls.size:
                        fall = int(anchor + 1 + falls[0])
                        peak = anchor + int(np.argmax(high[anchor:fall]))
                        trough = fall + int(np.argmin(low[fall:target]))
                        row["P_date"] = market.timestamp_labels[peak][:10]
                        row["L_date"] = market.timestamp_labels[trough][:10]
                        crossed = np.flatnonzero(close[fall:target + 1] > row["P"] + 1e-5)
                        if crossed.size:
                            row["first_break_date"] = market.timestamp_labels[fall + crossed[0]][:10]
            records.append(row)
        pieces.append(pl.DataFrame(records, infer_schema_length=None))
    if not pieces:
        raise ValueError("No first-board observations available")
    events = pl.concat(pieces, how="diagonal_relaxed").sort(["time_id", "asset_id"])
    times = events["time_id"].to_numpy()
    assets = events["asset_id"].to_numpy()
    valid = np.isfinite(market.close)

    def sample(values):
        return values[times, assets].astype(np.float64)

    # Every feature used for selection ends at T or earlier. T+1 open only
    # enters apply_execution_caps after the ordinary entry delay.
    prior_high = valid_shift(valid_rolling_max(market.close, valid, 240), 1, valid)
    prior_low = valid_shift(valid_rolling_min(market.close, valid, 240), 1, valid)
    prior_close = valid_shift(market.close, 1, valid)
    denominator = prior_high - prior_low
    position_before = np.full(market.shape, np.nan, dtype=np.float32)
    np.divide(prior_close - prior_low, denominator, out=position_before, where=denominator > 0)
    pos_signal = (sample(market.close) - sample(prior_low)) / sample(denominator)
    anchor_position = np.full(events.height, np.nan)
    distances = events["anchor_distance"].to_numpy()
    known = np.isfinite(distances)
    anchor_rows = times[known] - distances[known].astype(int)
    anchor_position[known] = position_before[anchor_rows, assets[known]]
    features = {
        "position_before": sample(position_before),
        "position_signal": pos_signal,
        "anchor_position_before": anchor_position,
        "distance_high240": sample(market.close) / sample(prior_high) - 1,
        "bias_ma20": sample(market.close) / sample(matrix_feature(market, "ma20")) - 1,
        "ret20_before": sample(valid_shift(matrix_feature(market, "momentum_20d"), 1, valid)),
        "ret20_signal": sample(matrix_feature(market, "momentum_20d")),
        "ret60_signal": sample(matrix_feature(market, "momentum_60d")),
    }
    return events.with_columns([
        pl.Series(name, values).fill_nan(None) for name, values in features.items()
    ])


def policy_mask(events: pl.DataFrame, name: str) -> np.ndarray:
    def values(column):
        return events[column].cast(pl.Float64).to_numpy()

    stage = values("stage")
    strict = stage == 5
    recent = values("anchor_distance") <= 30
    context = (values("position_before") <= 0.6) & (values("ret20_before") <= 0.2)
    extended = (values("bias_ma20") <= 0.15) & (values("above_P") <= 0.03)
    policies = {
        "strict_event": strict,
        "strict_recent": strict & recent,
        "strict_context": strict & context,
        "strict_not_extended": strict & extended,
        "strict_combined": strict & recent & context & extended,
        "low_start": (values("position_before") <= 0.4) & (values("ret20_before") <= 0.1),
        "reattack": (
            np.isin(stage, (3, 5)) & recent & context & extended
            & (values("anchor_position_before") <= 0.6)
            & (values("above_P") >= -0.1)
            & (values("pullback") >= 0.05) & (values("pullback") <= 0.2)
        ),
        "high_breakout": strict & (values("position_before") >= 0.8),
    }
    if name not in policies:
        raise ValueError(f"Unknown entry policy: {name}")
    return policies[name]


def apply_execution_caps(
    matrix: MarketMatrix,
    references: dict[tuple[int, int], float],
    *,
    max_gap: float | None = None,
    max_above_reference: float | None = None,
) -> tuple[MarketMatrix, dict[str, int]]:
    """Reject at the actual next open; never move that open into the T signal."""
    times, assets = np.nonzero(matrix.entry)
    signal_times = matrix.entry_signal_time[times, assets]
    opens = matrix.open[times, assets]
    closes = matrix.close[signal_times, assets]
    invalid = (signal_times < 0) | ~np.isfinite(opens) | (opens <= 0)
    invalid |= ~np.isfinite(closes) | (closes <= 0)
    gap_bad = np.zeros(times.size, dtype=bool)
    ref_bad = np.zeros(times.size, dtype=bool)
    tolerance = 1e-6
    if max_gap is not None:
        gap_bad = invalid | (opens / closes - 1 > max_gap + tolerance)
    if max_above_reference is not None:
        refs = np.array([
            references.get((int(t), int(a)), np.nan)
            for t, a in zip(signal_times, assets, strict=True)
        ])
        ref_bad = ~np.isfinite(refs) | (refs <= 0)
        ref_bad |= opens / refs - 1 > max_above_reference + tolerance
    rejected = invalid | gap_bad | ref_bad
    ledger = {
        "before": int(times.size), "accepted": int((~rejected).sum()),
        "rejected": int(rejected.sum()), "rejected_gap": int(gap_bad.sum()),
        "rejected_reference": int(ref_bad.sum()), "invalid": int(invalid.sum()),
    }
    if not rejected.any():
        return matrix, ledger
    entry = matrix.entry.copy()
    codes = matrix.entry_signal_code.copy()
    entry[times[rejected], assets[rejected]] = 0
    codes[times[rejected], assets[rejected]] = -1
    entry.flags.writeable = False
    codes.flags.writeable = False
    return replace(matrix, entry=entry, entry_signal_code=codes), ledger


def event_signals(
    market: MarketDataMatrix, events: pl.DataFrame, mask: np.ndarray, top_rank: int,
) -> SignalMatrix:
    entry = np.zeros(market.shape, dtype=np.uint8)
    # Stable asset-axis tie order is retained; this is not an alpha ranking.
    counts: dict[int, int] = {}
    for row in events.filter(pl.Series(mask)).select("time_id", "asset_id").iter_rows():
        t, a = row
        if counts.get(t, 0) < top_rank:
            entry[t, a] = 1
            counts[t] = counts.get(t, 0) + 1
    return make_signal_matrix(
        market.shape, entry=entry, score=entry.astype(np.float32) * 100,
        entry_signal_code=np.where(entry, 0, -1).astype(np.int16),
        entry_signal_ids=("signal_first_board_study",),
    )


def _distribution(values) -> dict[str, Any]:
    numbers = np.array([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    if not numbers.size:
        return {"n": 0, "median": None, "q25": None, "q75": None}
    return {
        "n": numbers.size, "median": np.median(numbers),
        "q25": np.quantile(numbers, 0.25), "q75": np.quantile(numbers, 0.75),
    }


def _source_hashes(strategy_path: Path) -> dict[str, str]:
    backend = Path(__file__).resolve().parents[1]
    files = [
        Path(__file__).resolve(), strategy_path,
        backend / "app/factors/event_chain.py",
        backend / "app/strategy/research/factor_rank_research.py",
        backend / "app/backtest/matrix.py",
        backend / "app/backtest/engine.py",
    ]
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def _load_source(data_dir: Path, task_id: str):
    registry = json.loads((data_dir / "user_data/task_registry.json").read_text(encoding="utf-8"))
    item = next(x for x in registry["items"] if x["id"] == task_id)
    query = dict(parse_qsl(item["payload"]["qs"]))
    if query.get("mode") != "position" or query.get("minute_fill") != "false":
        raise ValueError("This study requires position mode and daily fills")
    if query.get("entry_fill") != "open_t+1" or query.get("exit_fill") != "open_t+1":
        raise ValueError("This study requires next-open entry and signal exit")
    overrides = json.loads(query.get("overrides") or "{}")
    if query.get("regime_filter"):
        raise ValueError("This study does not vary market-regime selection")
    strategy = StrategyEngine._load_file(
        data_dir / "strategies/custom" / f"{query['strategy_id']}.py",
    )
    params = {p["id"]: p["default"] for p in strategy.meta["params"]}
    params.update(json.loads(query.get("params") or "{}"))
    basic = StrategyBacktestService._effective_basic_filter(strategy, overrides)
    matcher = MatcherConfig(
        matching="open_t+1",
        commission_pct=float(query["commission_pct"]),
        stamp_tax_pct=float(query["stamp_tax_pct"]),
        slippage_bps=float(query["slippage_bps"]),
        stop_loss_pct=overrides.get("stop_loss", strategy.stop_loss),
        take_profit_pct=overrides.get("take_profit"),
        trailing_stop_pct=overrides.get("trailing_stop"),
        trailing_take_profit_activate_pct=overrides.get("trailing_take_profit_activate"),
        trailing_take_profit_drawdown_pct=overrides.get("trailing_take_profit_drawdown"),
        max_hold_days=overrides.get("max_hold_days", strategy.max_hold_days),
        max_positions=int(query["max_positions"]),
        max_exposure_pct=float(query["max_exposure_pct"]),
        initial_capital=float(query["initial_capital"]),
        position_sizing=query["position_sizing"],
    )
    return item, query, overrides, strategy, params, basic, matcher


def run_study(data_dir: Path, task_id: str, output: Path) -> None:
    if output.exists():
        raise FileExistsError("Use a new output directory; frozen runs are never overwritten")
    item, query, overrides, strategy, params, basic, matcher = _load_source(data_dir, task_id)
    start, end = date.fromisoformat(query["start"]), date.fromisoformat(query["end"])
    periods = [
        ("full", start, end),
        ("development", start, date(2023, 12, 31)),
        ("validation_2024", date(2024, 1, 1), date(2024, 12, 31)),
        ("retrospective_2025_2026", date(2025, 1, 1), end),
    ]
    if start >= date(2023, 12, 31) or end < date(2025, 1, 1):
        raise ValueError("The registered study periods require 2023..2025 coverage")
    hashes = _source_hashes(strategy.file_path)
    output.mkdir(parents=True)
    (output / "runs").mkdir()
    (output / "source_strategy.py").write_text(
        strategy.file_path.read_text(encoding="utf-8"), encoding="utf-8",
    )
    manifest = {
        "study": "first_board_entry_v1", "created_at": datetime.now().isoformat(),
        "source_task": item, "source_config": query, "source_hashes": hashes,
        "policies": POLICIES, "executions": EXECUTIONS, "periods": periods,
        "matcher": asdict(matcher), "basic_filter": basic, "params": params,
        "selection": "No best variant is selected automatically; all preregistered rows are reported",
        "validation": (
            "Temporal retrospective comparison, not pristine out-of-sample validation: "
            "2021..2026 aggregate results were already inspected before this study."
        ),
        "units": "Returns/ratios are decimal; position uses 240 observed closes",
        "exit_control": "All new policies retain baseline risk and max hold; ranking exits removed",
        "tie_order": "Stable asset-axis order retained; no proven candidate ranking",
        "outer_scoring": "Existing source scoring/directions and overlays remain common to all policies",
        "universe_limitations": (
            "Same current instrument name/share/listing data and available historical universe as "
            "the existing platform; historical survivorship/ST/share accuracy is not independently certified"
        ),
    }
    write_json(output / "manifest.json", manifest)
    print("FROZEN " + str(output / "manifest.json"), flush=True)
    engine = BacktestEngine(KlineRepository(DataStore(data_dir)))
    generation = engine.data_generation()
    plan = StrategyDependencyResolver().resolve(
        strategy, params=params, basic_filter=basic, entry_signals=strategy.entry_signals,
        exit_signals=strategy.exit_signals, overrides=overrides,
    )
    market = engine.load_market_data_matrix_for_backtest(
        None, start - timedelta(days=520), end, plan,
        expected_generation=generation,
    )
    manifest["generation"] = generation
    manifest["matrix_shape"] = market.shape
    manifest["matrix_nbytes"] = market.nbytes
    write_json(output / "manifest.json", manifest)
    print(f"LOADED {market.shape} {market.nbytes / 2**20:.0f} MiB", flush=True)
    events = build_event_table(market)
    events.write_parquet(output / "events.parquet")
    from app.backtest.matrix import build_basic_filter_mask

    basic_mask = build_basic_filter_mask(market, basic)
    overlay_mask = np.ones(market.shape, dtype=bool)
    if overrides.get("overlay_filter"):
        overlay_mask, overlay_error = StrategyBacktestService._overlay_matrix_mask(
            market, overrides["overlay_filter"],
        )
        if overlay_error is not None:
            raise ValueError(overlay_error)
    times, assets = events["time_id"].to_numpy(), events["asset_id"].to_numpy()
    events = events.with_columns(
        pl.Series("basic_eligible", (basic_mask & overlay_mask)[times, assets]),
    )
    del basic_mask
    pipeline = MatrixStrategyPipeline()
    pipeline_config = MatrixPipelineConfig(
        basic_filter=basic, scoring=effective_scoring(strategy.meta.get("scoring"), overrides),
        order_by=strategy.meta.get("order_by"), descending=True,
        scoring_directions=effective_scoring_directions(overrides),
    )
    legacy = pipeline.run(strategy.matrix_strategy, market, params, pipeline_config)
    legacy = make_signal_matrix(
        market.shape, entry=(legacy.entry & overlay_mask).astype(np.uint8),
        exit=legacy.exit, score=legacy.score,
        entry_signal_code=legacy.entry_signal_code, exit_signal_code=legacy.exit_signal_code,
        entry_signal_ids=legacy.entry_signal_ids, exit_signal_ids=legacy.exit_signal_ids,
    )
    del overlay_mask
    events = events.with_columns(
        pl.Series("legacy_entry", legacy.entry[times, assets].astype(bool)),
        pl.Series("legacy_score", legacy.score[times, assets]),
    )
    events.write_parquet(output / "events.parquet")
    events.write_csv(output / "events.csv")
    event_lookup = {(r["symbol"], r["date"]): r for r in events.to_dicts()}
    formal_events = (
        (events["date"] >= str(start)) & (events["date"] <= str(end))
    ).to_numpy()
    references = {
        (r["time_id"], r["asset_id"]): r["P"]
        for r in events.select("time_id", "asset_id", "P").to_dicts()
        if r["P"] is not None and np.isfinite(r["P"])
    }
    rows, group_counts = [], []
    all_event_audits = []
    for name, description in POLICIES.items():
        if name == "legacy_rank":
            signals = legacy
            before = events["legacy_entry"].to_numpy()
        elif name == "same_entries_fixed_exit":
            signals = make_signal_matrix(
                market.shape, entry=legacy.entry, score=legacy.score,
                entry_signal_code=legacy.entry_signal_code,
                entry_signal_ids=legacy.entry_signal_ids,
            )
            before = events["legacy_entry"].to_numpy()
        else:
            before = policy_mask(events, name)
            filtered = before & events["basic_eligible"].to_numpy()
            signals = event_signals(market, events, filtered, int(params["top_rank"]))
            # Retain the source's ordinary outer scoring so position allocation
            # is not changed together with the entry definition.
            from app.backtest.matrix import build_matrix_score

            score = build_matrix_score(
                market, signals.entry.astype(bool), pipeline_config.scoring,
                pipeline_config.order_by, pipeline_config.descending,
                fallback=signals.score, directions=pipeline_config.scoring_directions,
            )
            signals = make_signal_matrix(
                market.shape, entry=signals.entry, score=score,
                entry_signal_code=signals.entry_signal_code,
                entry_signal_ids=signals.entry_signal_ids,
            )
        group_counts.append({
            "policy": name, "description": description,
            "raw_events": int((before & formal_events).sum()),
            "basic_eligible": int(
                (before & formal_events & events["basic_eligible"].to_numpy()).sum(),
            ),
            "signals_after_daily_limit": int(
                signals.entry[times[formal_events], assets[formal_events]].sum(),
            ),
        })
        executions = (
            ["unrestricted"] if name == "legacy_rank"
            else ["unrestricted", "gap3"] if name == "low_start"
            else list(EXECUTIONS)
        )
        for period_name, period_start, period_end in periods:
            ids = [
                i for i, label in enumerate(market.timestamp_labels)
                if str(period_start) <= label[:10] <= str(period_end)
            ]
            a, b = ids[0], ids[-1] + 1
            sub_market = slice_market_data_matrix(market, a, b)
            sub_signals = slice_signal_matrix(signals, a, b)
            # Daily shift happens only inside this period: no pre-period entries,
            # no new signals filled beyond the study period boundary.
            matrix = build_market_matrix_from_signals(
                sub_market, sub_signals, entry_delay_bars=1, exit_delay_bars=1,
            )
            sub_refs = {(t - a, asset): p for (t, asset), p in references.items() if a <= t < b}
            for execution in executions:
                gated, ledger = apply_execution_caps(matrix, sub_refs, **EXECUTIONS[execution])
                result = engine.simulate_market_matrix(
                    gated, matcher,
                    options=SimulationOptions(
                        include_monte_carlo=False, include_per_symbol_stats=False,
                        include_return_distribution=False,
                    ),
                )
                trades = [asdict(t) for t in result.trades]
                audits = []
                for trade in trades:
                    event = event_lookup.get((trade["symbol"], trade["entry_signal_date"]))
                    if event is None:
                        raise AssertionError("Executed trade has no frozen signal-day descriptor")
                    record = {
                        "policy": name, "period": period_name, "execution": execution, **trade,
                        **{k: event[k] for k in (
                            "nearest_anchor_date", "nearest_stage", "anchor_date",
                            "P", "P_date", "L", "L_date", "recursion_steps", "stage",
                            "anchor_distance", "above_P", "pullback", "position_before",
                            "position_signal", "ret20_signal", "bias_ma20",
                        )},
                    }
                    asset = market.symbols.index(trade["symbol"])
                    entry_time = market.timestamp_labels.index(trade["entry_date"])
                    entry_open = float(market.open[entry_time, asset])
                    record["entry_gap"] = entry_open / event["close"] - 1
                    record["entry_above_P"] = (
                        entry_open / event["P"] - 1 if np.isfinite(event["P"]) else None
                    )
                    record["distance_to_L"] = (
                        1 - event["L"] / entry_open if np.isfinite(event["L"]) else None
                    )
                    audits.append(record)
                all_event_audits.extend(audits)
                key = f"{name}__{execution}__{period_name}"
                stats = result.stats
                summary = {
                    "policy": name, "execution": execution, "period": period_name,
                    "start": str(period_start), "end": str(period_end), **ledger,
                    **{k: stats.get(k) for k in (
                        "total_return", "annual_return", "max_drawdown", "sharpe", "n_trades",
                        "win_rate", "profit_factor", "pending_exit_positions",
                    )},
                    "closed_trades": len(trades),
                    "stop_loss_rate": (
                        sum(t["exit_reason"] == "stop_loss" for t in trades) / len(trades)
                        if trades else None
                    ),
                    "avg_trade_return": float(np.mean([t["pnl_pct"] for t in trades])) if trades else None,
                    "median_trade_return": float(np.median([t["pnl_pct"] for t in trades])) if trades else None,
                    "avg_duration": float(np.mean([t["duration"] for t in trades])) if trades else None,
                    "median_position_before": _distribution([r["position_before"] for r in audits])["median"],
                    "median_bias_ma20": _distribution([r["bias_ma20"] for r in audits])["median"],
                    "median_ret20": _distribution([r["ret20_signal"] for r in audits])["median"],
                    "median_entry_gap": _distribution([r["entry_gap"] for r in audits])["median"],
                    "median_distance_to_L": _distribution([r["distance_to_L"] for r in audits])["median"],
                }
                rows.append(clean_json(summary))
                write_json(output / "runs" / f"{key}.json", {
                    "summary": summary, "stats": stats, "trades": trades,
                    "equity_curve": result.equity_curve,
                })
                write_json(output / "results.json", rows)
                print(json.dumps(clean_json(summary), ensure_ascii=True), flush=True)
                del gated, result
            del matrix, sub_market, sub_signals
        if name != "legacy_rank":
            del signals
        gc.collect()
    engine.assert_data_generation("stock", generation)
    if hashes != _source_hashes(strategy.file_path):
        raise RuntimeError("Source code changed during the study; results are not certified")
    pl.DataFrame(rows, infer_schema_length=None).write_csv(output / "results.csv")
    pl.DataFrame(group_counts).write_csv(output / "candidate_counts.csv")
    pl.DataFrame(all_event_audits, infer_schema_length=None).write_csv(output / "trades.csv")
    stage_counts = events.group_by("stage").agg(pl.len().alias("count")).sort("stage")
    stage_counts.write_csv(output / "stage_counts.csv")
    manifest["finished_at"] = datetime.now().isoformat()
    manifest["checks"] = {
        "generation_unchanged": True, "source_unchanged": True,
        "trial_rows": len(rows), "all_trades_matched": True,
        "entry_cap_conservation": all(r["before"] == r["accepted"] + r["rejected"] for r in rows),
    }
    write_json(output / "manifest.json", manifest)
    print("COMPLETE " + str(output), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    run_study(args.data_dir, args.task_id, args.output)
    print(f"ELAPSED {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
