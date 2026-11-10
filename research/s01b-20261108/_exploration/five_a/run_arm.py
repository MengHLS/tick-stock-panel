"""⑤-a single-toggle decomposition runner (S01 / custom_mw7fvp17, production file).

One process = one arm. Every arm is the production strategy file run through the
same production pipeline as research/s01b-20261108/prod_run_s01b.py, with an
OPTIONAL in-memory injection of ``META.backtest_defaults``.

Design rules for this task:
  * baseline = production file as-is (NO injection) = the 208-trade default口径;
  * a single-toggle arm injects EXACTLY ONE key (execution_costs counts as one
    item = two sub-keys), so "only X is on" is provable from ``effective_config``;
  * the file on disk is never written;
  * ``effective_config`` records: the request config, the raw META payload, the
    normalized ExecutionPolicy, and the RESOLVED matcher config taken from
    ``result.provenance["execution"]`` (i.e. what the engine actually used, not
    what we asked for);
  * three parquet artifacts (trades / equity / drawdown) + their sha256.

Evidence ② (双价基) is produced by ``attach_dual_basis.py`` so it stays cheap and
re-runnable; this script only dumps the trades the engine recorded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
PROJECT = PARENT.parents[1]
DATA_ROOT = PARENT / "data_root"
os.environ["DATA_DIR"] = str(DATA_ROOT)
sys.path.insert(0, str(PROJECT / "backend"))

import polars as pl  # noqa: E402
from app.backtest.engine import BacktestEngine  # noqa: E402
from app.backtest.execution_policy import parse_backtest_defaults  # noqa: E402
from app.backtest.strategy import (  # noqa: E402
    StrategyBacktestConfig,
    StrategyBacktestService,
)
from app.config import settings  # noqa: E402
from app.strategy.engine import StrategyEngine  # noqa: E402
from app.tickflow.repository import DataStore, KlineRepository  # noqa: E402


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_service(strategy_dir: Path) -> StrategyBacktestService:
    store = DataStore(settings.data_dir)
    engine = BacktestEngine(KlineRepository(store))
    return StrategyBacktestService(engine, StrategyEngine(strategy_dirs=[strategy_dir]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy-id", default="custom_mw7fvp17")
    ap.add_argument("--strategies-dir", default=r"D:\TSP\data\strategies\custom")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--start", default="2019-07-01")
    ap.add_argument("--end", default="2026-10-30")
    ap.add_argument("--slippage-bps", type=float, default=10.0)
    ap.add_argument("--gross", action="store_true")
    ap.add_argument("--max-positions", type=int, default=5)
    ap.add_argument("--max-exposure-pct", type=float, default=0.6)
    ap.add_argument("--holding-days", type=int, default=60)
    ap.add_argument("--inject", default="", help='single-key json inline (avoid: Windows shells eat quotes)')
    ap.add_argument("--inject-file", default="", help="single-key json file (preferred, auditable)")
    args = ap.parse_args()

    assert Path(settings.data_dir) == DATA_ROOT, "data_dir is not the research root; refusing"
    outdir = HERE / args.tag
    outdir.mkdir(parents=True, exist_ok=True)

    if args.inject_file:
        injected = json.loads(Path(args.inject_file).read_text(encoding="utf-8"))
    elif args.inject:
        injected = json.loads(args.inject)
    else:
        injected = None
    if injected is not None and len(injected) > 2:
        raise SystemExit(f"single-toggle arm must not inject >2 keys: {injected}")

    service = build_service(Path(args.strategies_dir))
    s = service.strategy_engine.get(args.strategy_id)
    strat_path = Path(s.file_path)
    strat_bytes = strat_path.read_bytes()
    meta_defaults_before = s.meta.get("backtest_defaults")
    if injected is not None:
        s.meta["backtest_defaults"] = injected  # in-memory only, file untouched

    policy = parse_backtest_defaults(
        s.meta.get("backtest_defaults"), context=f"strategy {args.strategy_id}"
    )
    print(f"[strategy] id={s.meta['id']} name={s.meta['name']} backend={s.execution_backend}")
    print(f"[strategy] file={strat_path} size={len(strat_bytes)} sha256={hashlib.sha256(strat_bytes).hexdigest()}")
    print(f"[strategy] meta.backtest_defaults(before)={json.dumps(meta_defaults_before, ensure_ascii=False, default=str)}")
    print(f"[inject] <= {json.dumps(injected, ensure_ascii=False, default=str)}")
    print(f"[policy] {json.dumps(policy.engine_options(), ensure_ascii=False, default=str)}")

    gross = args.gross
    config = StrategyBacktestConfig(
        strategy_id=args.strategy_id,
        symbols=None,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        params={},
        overrides={},
        matching="open_t+1",
        commission_pct=0.0 if gross else 0.0003,
        stamp_tax_pct=0.0 if gross else 0.001,
        slippage_bps=0.0 if gross else float(args.slippage_bps),
        max_positions=args.max_positions,
        max_exposure_pct=args.max_exposure_pct,
        initial_capital=1_000_000.0,
        position_sizing="equal",
        mode="position",
        asset_type="stock",
        holding_days=args.holding_days,
        minute_fill=False,
        carry_state=None,
        carry_out=False,
    )
    t0 = time.perf_counter()
    result = service.run(config)
    elapsed = time.perf_counter() - t0

    trades = pl.DataFrame(result.trades) if result.trades else pl.DataFrame()
    equity = pl.DataFrame(result.equity_curve) if result.equity_curve else pl.DataFrame()
    drawdown = pl.DataFrame(result.drawdown_curve) if result.drawdown_curve else pl.DataFrame()
    files: dict[str, str] = {}
    for name, frame in (("trades", trades), ("equity", equity), ("drawdown", drawdown)):
        p = outdir / f"{name}.parquet"
        if not frame.is_empty():
            frame.write_parquet(p)
            files[f"{name}.parquet"] = sha256_file(p)

    provenance = result.provenance or {}
    effective_config = {
        "arm_tag": args.tag,
        "single_toggle_injected": injected,
        "request": result.config,
        "strategy_file": {
            "path": str(strat_path),
            "size": len(strat_bytes),
            "sha256": hashlib.sha256(strat_bytes).hexdigest(),
            "meta_backtest_defaults_on_disk": meta_defaults_before,
        },
        "strategy_meta_backtest_defaults_effective_raw": s.meta.get("backtest_defaults"),
        "execution_policy_normalized": {
            **asdict(policy),
            "engine_options": policy.engine_options(),
        },
        "resolved_matcher_config": provenance.get("execution"),
        "provenance_strategy_hash": provenance.get("strategy_hash"),
        "provenance_algorithm_version": provenance.get("algorithm_version"),
    }
    out = {
        "tag": args.tag,
        "strategy_id": args.strategy_id,
        "start": args.start,
        "end": args.end,
        "gross": gross,
        "slippage_bps": 0.0 if gross else args.slippage_bps,
        "commission_pct": 0.0 if gross else 0.0003,
        "stamp_tax_pct": 0.0 if gross else 0.001,
        "elapsed_s": round(elapsed, 1),
        "error": result.error,
        "stats": result.stats,
        "n_trades": len(trades),
        "n_equity": len(equity),
        "n_drawdown": len(drawdown),
        "run_id": result.run_id,
        "effective_config": effective_config,
        "artifacts_sha256": files,
    }
    (outdir / "result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    (outdir / "effective_config.json").write_text(
        json.dumps(effective_config, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8",
    )
    print(f"[run] error={result.error} trades={len(trades)} equity={len(equity)} "
          f"drawdown={len(drawdown)} elapsed={elapsed:.1f}s")
    if not trades.is_empty():
        print("[run] exit_reason:", trades.group_by("exit_reason").len().sort("exit_reason").to_dicts())
    for k in ("total_return", "annual_return", "max_drawdown", "sharpe", "n_trades",
              "completed_trade_count", "open_at_end_count", "avg_holding_days", "final_equity"):
        print(f"[stat] {k}={result.stats.get(k)}")
    ex = result.stats.get("execution") or {}
    print("[exec]", json.dumps({k: v for k, v in sorted(ex.items())}, ensure_ascii=False))
    return 0 if not result.error else 1


if __name__ == "__main__":
    sys.exit(main())
