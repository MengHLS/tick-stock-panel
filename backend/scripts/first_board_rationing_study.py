"""First-board candidate rationing study using the production matrix matcher.

Run from backend with --data-dir, --task-id, --exit-study and a new --output.
The study freezes the low-start entry and compares admission policies.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import numpy as np
import polars as pl

from app.backtest.engine import BacktestEngine, SimulationOptions
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
from scripts.first_board_exit_study import (
    EXIT_PROTOCOLS,
    ExitProtocol,
    protocol_matcher,
    protocol_signals,
    summarize_run,
)

ENTRY_NAME = "low_start"
ENTRY_DESCRIPTION = "Any first board, pre-signal position<=0.4, ret20<=10%"
EXIT_NAMES = ("baseline_8pct_30d", "trailing_high_8pct")
EXECUTION_NAME = "gap3"
MAX_ENTRY_GAP = 0.03


@dataclass(frozen=True)
class AdmissionProfile:
    id: str
    description: str
    mode: Literal["asset", "score"]
    top_k: int
    cooldown_bars: int = 0


ADMISSION_PROFILES = (
    AdmissionProfile(
        id="asset_top20",
        description="Control: first 20 eligible assets by stable asset-axis order",
        mode="asset",
        top_k=20,
    ),
    AdmissionProfile(
        id="score_top20",
        description="Top 20 eligible assets by source score",
        mode="score",
        top_k=20,
    ),
    AdmissionProfile(
        id="score_top5",
        description="Top 5 eligible assets by source score",
        mode="score",
        top_k=5,
    ),
    AdmissionProfile(
        id="score_top3",
        description="Top 3 eligible assets by source score",
        mode="score",
        top_k=3,
    ),
    AdmissionProfile(
        id="score_top1",
        description="Top eligible asset by source score",
        mode="score",
        top_k=1,
    ),
    AdmissionProfile(
        id="score_top5_cooldown5",
        description=(
            "Top 5 by source score, suppressing the same asset for the next "
            "five sessions after a selected signal"
        ),
        mode="score",
        top_k=5,
        cooldown_bars=5,
    ),
)


def limit_top_rank(
    eligible: np.ndarray,
    score: np.ndarray,
    top_k: int,
) -> np.ndarray:
    """Select the highest scores per day, preserving asset order on exact ties."""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    if eligible.shape != score.shape:
        raise ValueError("eligible and score must have the same shape")
    selected = np.zeros(eligible.shape, dtype=bool)
    for time_id in range(eligible.shape[0]):
        asset_ids = np.flatnonzero(eligible[time_id])
        if asset_ids.size <= top_k:
            selected[time_id, asset_ids] = True
            continue
        order = np.argsort(
            -score[time_id, asset_ids],
            kind="stable",
        )[:top_k]
        selected[time_id, asset_ids[order]] = True
    return selected


def apply_cooldown(
    selected: np.ndarray,
    cooldown_bars: int,
) -> np.ndarray:
    """Suppress repeated same-asset signals within the stated session window."""
    if cooldown_bars < 0:
        raise ValueError("cooldown_bars must not be negative")
    if cooldown_bars == 0:
        return selected.copy()
    result = np.zeros(selected.shape, dtype=bool)
    last_signal = np.full(selected.shape[1], -cooldown_bars - 1, dtype=np.int64)
    for time_id in range(selected.shape[0]):
        for asset_id in np.flatnonzero(selected[time_id]):
            if time_id - last_signal[asset_id] <= cooldown_bars:
                continue
            result[time_id, asset_id] = True
            last_signal[asset_id] = time_id
    return result


def scoring_candidate_mask(
    market: MarketDataMatrix,
    candidates: np.ndarray,
    scoring: dict[str, float],
) -> np.ndarray:
    """Exclude candidates whose scoring inputs are not observable."""
    result = candidates.copy()
    for name in scoring:
        result &= np.isfinite(matrix_feature(market, name))
    return result


def allocation_signal_matrix(
    market: MarketDataMatrix,
    selected: np.ndarray,
    pipeline_config: MatrixPipelineConfig,
) -> SignalMatrix:
    score = build_matrix_score(
        market,
        selected,
        pipeline_config.scoring,
        pipeline_config.order_by,
        pipeline_config.descending,
        fallback=np.zeros(market.shape, dtype=np.float32),
        directions=pipeline_config.scoring_directions,
    )
    return make_signal_matrix(
        market.shape,
        entry=selected.astype(np.uint8),
        score=score,
        entry_signal_code=np.where(selected, 0, -1).astype(np.int16),
        entry_signal_ids=("signal_low_start_rationed",),
    )


def build_admission_signals(
    market: MarketDataMatrix,
    events: pl.DataFrame,
    pipeline_config: MatrixPipelineConfig,
    profile: AdmissionProfile,
) -> tuple[SignalMatrix, np.ndarray, dict[str, int]]:
    raw_mask = policy_mask(events, ENTRY_NAME)
    eligible_events = raw_mask & events["basic_eligible"].to_numpy()
    times = events["time_id"].to_numpy()
    assets = events["asset_id"].to_numpy()

    if profile.mode == "asset":
        signals = event_signals(market, events, eligible_events, profile.top_k)
        score = build_matrix_score(
            market,
            signals.entry.astype(bool),
            pipeline_config.scoring,
            pipeline_config.order_by,
            pipeline_config.descending,
            fallback=signals.score,
            directions=pipeline_config.scoring_directions,
        )
        signals = make_signal_matrix(
            market.shape,
            entry=signals.entry,
            score=score,
            entry_signal_code=signals.entry_signal_code,
            entry_signal_ids=signals.entry_signal_ids,
        )
        return signals, raw_mask, {
            "rank_eligible": int(eligible_events.sum()),
            "cooldown_suppressed": 0,
        }

    candidates = np.zeros(market.shape, dtype=bool)
    candidates[times[eligible_events], assets[eligible_events]] = True
    rank_eligible = scoring_candidate_mask(
        market,
        candidates,
        pipeline_config.scoring,
    )
    rank_score = build_matrix_score(
        market,
        rank_eligible,
        pipeline_config.scoring,
        pipeline_config.order_by,
        pipeline_config.descending,
        fallback=np.zeros(market.shape, dtype=np.float32),
        directions=pipeline_config.scoring_directions,
    )
    limited = limit_top_rank(rank_eligible, rank_score, profile.top_k)
    selected = apply_cooldown(limited, profile.cooldown_bars)
    return (
        allocation_signal_matrix(market, selected, pipeline_config),
        raw_mask,
        {
            "rank_eligible": int(rank_eligible.sum()),
            "cooldown_suppressed": int(limited.sum() - selected.sum()),
        },
    )


def _source_hashes(strategy_path: Path) -> dict[str, str]:
    backend = Path(__file__).resolve().parents[1]
    files = [
        Path(__file__).resolve(),
        backend / "scripts/first_board_entry_study.py",
        backend / "scripts/first_board_exit_study.py",
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


def _reference_manifest(exit_study: Path) -> dict[str, Any]:
    manifest = json.loads(
        (exit_study / "manifest.json").read_text(encoding="utf-8"),
    )
    checks = manifest.get("checks", {})
    if not manifest.get("finished_at") or not all(
        checks.get(key) is True
        for key in (
            "generation_unchanged",
            "source_unchanged",
            "all_trades_matched",
            "entry_cap_conservation",
        )
    ):
        raise ValueError("The reference exit study is not certified")
    return manifest


def _reference_run(
    exit_study: Path,
    protocol: ExitProtocol,
    period_name: str,
) -> dict[str, Any]:
    path = (
        exit_study
        / "runs"
        / f"low_start__{protocol.id}__{period_name}.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def assert_reference_run(
    reference: dict[str, Any],
    trades: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
    ledger: dict[str, int],
) -> None:
    if reference["trades"] != trades or reference["equity_curve"] != equity_curve:
        raise AssertionError(
            "Control admission does not reproduce the certified exit study"
        )
    for key, value in ledger.items():
        if reference["summary"][key] != value:
            raise AssertionError(
                f"Control admission ledger differs at {key}"
            )


def _daily_selection_rows(
    market: MarketDataMatrix,
    selected: np.ndarray,
    profile: AdmissionProfile,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    rows = []
    for time_id, label in enumerate(market.timestamp_labels):
        day = label[:10]
        if not str(start) <= day <= str(end):
            continue
        count = int(selected[time_id].sum())
        if count:
            rows.append({"profile": profile.id, "date": day, "count": count})
    return rows


def run_study(
    data_dir: Path,
    task_id: str,
    output: Path,
    exit_study: Path,
) -> None:
    if output.exists():
        raise FileExistsError("Use a new output directory; frozen runs are never overwritten")
    (
        item,
        query,
        overrides,
        strategy,
        params,
        basic,
        base_matcher,
    ) = _load_source(data_dir, task_id)
    reference_manifest = _reference_manifest(exit_study)
    if reference_manifest["source_config"] != query:
        raise ValueError("Source configuration differs from the reference exit study")
    start = date.fromisoformat(query["start"])
    end = date.fromisoformat(query["end"])
    periods = [
        ("full", start, end),
        ("development", start, date(2023, 12, 31)),
        ("validation_2024", date(2024, 1, 1), date(2024, 12, 31)),
        ("retrospective_2025_2026", date(2025, 1, 1), end),
    ]
    hashes = _source_hashes(strategy.file_path)

    output.mkdir(parents=True)
    (output / "runs").mkdir()
    (output / "source_strategy.py").write_text(
        strategy.file_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    manifest: dict[str, Any] = {
        "study": "first_board_rationing_v1",
        "created_at": datetime.now().isoformat(),
        "source_task": item,
        "source_config": query,
        "source_hashes": hashes,
        "entry": ENTRY_NAME,
        "entry_description": ENTRY_DESCRIPTION,
        "admission_profiles": [
            asdict(profile) for profile in ADMISSION_PROFILES
        ],
        "exit_protocols": [
            asdict(protocol)
            for protocol in EXIT_PROTOCOLS
            if protocol.id in EXIT_NAMES
        ],
        "execution": {
            "id": EXECUTION_NAME,
            "max_gap": MAX_ENTRY_GAP,
        },
        "periods": periods,
        "params": params,
        "basic_filter": basic,
        "reference_exit_study": str(exit_study),
        "reference_manifest_sha256": hashlib.sha256(
            (exit_study / "manifest.json").read_bytes(),
        ).hexdigest(),
        "selection": (
            "No best variant is selected automatically; all admission x exit x "
            "period rows are reported"
        ),
        "ranking": (
            "Score-ranked profiles require every scoring input to be finite. "
            "Asset-axis control retains the prior study's behavior. Exact score "
            "ties preserve stable asset-axis order."
        ),
        "cooldown": (
            "A selected same-asset signal suppresses later signals within the next "
            "five sessions; suppressed signals do not renew the cooldown."
        ),
        "validation": (
            "Temporal retrospective comparison, not pristine out-of-sample validation"
        ),
        "universe_limitations": (
            "Historical survivorship, ST status and share-capital accuracy are not "
            "independently certified"
        ),
    }
    write_json(output / "manifest.json", manifest)
    print("FROZEN " + str(output / "manifest.json"), flush=True)

    engine = BacktestEngine(KlineRepository(DataStore(data_dir)))
    generation = engine.data_generation()
    if generation != reference_manifest["generation"]:
        raise ValueError("Data generation differs from the reference exit study")
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
    protocols = {
        protocol.id: protocol
        for protocol in EXIT_PROTOCOLS
        if protocol.id in EXIT_NAMES
    }

    signals_by_profile: dict[str, SignalMatrix] = {}
    raw_masks: dict[str, np.ndarray] = {}
    profile_stats: list[dict[str, Any]] = []
    daily_counts: list[dict[str, Any]] = []
    for profile in ADMISSION_PROFILES:
        signals, raw_mask, audit = build_admission_signals(
            market,
            events,
            pipeline_config,
            profile,
        )
        signals_by_profile[profile.id] = signals
        raw_masks[profile.id] = raw_mask
        daily_counts.extend(
            _daily_selection_rows(
                market,
                signals.entry.astype(bool),
                profile,
                start,
                end,
            )
        )
        profile_stats.append({
            "profile": profile.id,
            "description": profile.description,
            **audit,
            "selected_signals": int(
                signals.entry[times[formal_events], assets[formal_events]].sum()
            ),
        })

    rows: list[dict[str, Any]] = []
    all_trade_audits: list[dict[str, Any]] = []
    control_runs: dict[
        tuple[str, str], dict[tuple[str, str], dict[str, Any]]
    ] = {}
    reference_checks: list[str] = []

    for profile in ADMISSION_PROFILES:
        base_signals = signals_by_profile[profile.id]
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
            for protocol_name in EXIT_NAMES:
                protocol = protocols[protocol_name]
                signals = slice_signal_matrix(
                    protocol_signals(market, base_signals, protocol),
                    start_id,
                    stop_id,
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
                result = engine.simulate_market_matrix(
                    gated,
                    protocol_matcher(base_matcher, protocol),
                    options=SimulationOptions(
                        include_monte_carlo=False,
                        include_per_symbol_stats=False,
                        include_return_distribution=False,
                    ),
                )
                trades = [asdict(trade) for trade in result.trades]
                if profile.id == "asset_top20":
                    reference = _reference_run(exit_study, protocol, period_name)
                    assert_reference_run(
                        reference,
                        trades,
                        result.equity_curve,
                        ledger,
                    )
                    reference_checks.append(f"{protocol.id}__{period_name}")
                    control_runs[protocol.id, period_name] = {
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
                    audits.append({
                        "admission": profile.id,
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
                    })
                all_trade_audits.extend(audits)

                summary = summarize_run(
                    profile.id,
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
                control = control_runs[protocol.id, period_name]
                current = {
                    (trade["symbol"], trade["entry_signal_date"]): trade
                    for trade in trades
                }
                common = control.keys() & current.keys()
                summary.update({
                    "shared_control_entries": len(common),
                    "new_entries_vs_control": len(current.keys() - control.keys()),
                    "omitted_control_entries": len(control.keys() - current.keys()),
                    "mean_return_delta_shared_entries": (
                        float(np.mean([
                            current[key]["pnl_pct"] - control[key]["pnl_pct"]
                            for key in common
                        ])) if common else None
                    ),
                })
                rows.append(clean_json(summary))
                key = f"{profile.id}__{protocol.id}__{period_name}"
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
    expected_rows = len(ADMISSION_PROFILES) * len(EXIT_NAMES) * len(periods)
    if len(rows) != expected_rows or len(reference_checks) != 8:
        raise AssertionError("Incomplete trial matrix or control reproduction")

    pl.DataFrame(rows, infer_schema_length=None).write_csv(output / "results.csv")
    pl.DataFrame(profile_stats).write_csv(output / "profile_counts.csv")
    pl.DataFrame(daily_counts).write_csv(output / "daily_selection_counts.csv")
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
        "reference_controls_reproduced": reference_checks,
    }
    write_json(output / "manifest.json", manifest)
    print("COMPLETE " + str(output), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--exit-study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    run_study(
        args.data_dir,
        args.task_id,
        args.output,
        args.exit_study,
    )
    print(f"ELAPSED {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
