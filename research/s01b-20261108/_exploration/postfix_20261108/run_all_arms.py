"""S01b 阶段2：把 research/s01b-20261108/results/ 下全部臂在当前引擎上按原参数重跑。

与 prod_run_s01b.py 逐字段同一策略入口 / 同一 StrategyBacktestConfig 口径：
  StrategyBacktestService + StrategyEngine(strategy_dirs=<臂所属目录>)
  1,000,000 / 5 仓 / 60% 敞口 / open_t+1 / 等权 / holding_days=60
  佣金 3bp（双边）+ 印花 10bp（卖出）+ 滑点 10 或 30bp；--gross 全归零
  entry_price_basis / block_limit_open / finalize_open_at_end / execution_costs
  全部由策略文件 META.backtest_defaults 声明（不做任何注入）

与 prod_run_s01b 的两处差别（只为证据，不改结果）：
  * 多写 drawdown.parquet（phase-1 runner 已有此产物，便于三产物 sha 对照）
  * result.json 里多记 engine sha / strategy 文件 sha / 逐产物 sha / effective_config

臂表来源：= results/<tag>/result.json 里记录的 strategy_id / gross / slippage_bps /
commission_pct / stamp_tax_pct / start / end，逐臂原样抄入，不新造臂。
`prod_file_10bp` 原跑的是 17:0x 的生产文件（5,510 B / 918254f0，四臂口径变体），
该文件已被回滚，故从 prod_file_snapshots/ 归档快照还原到本目录 _inputs/ 下再跑，
不读写 D:\TSP。

用法:
  python run_all_arms.py --only a0_10bp,a0_30bp
  python run_all_arms.py                      # 全部 18 臂，已存在则跳过
  python run_all_arms.py --outdir-root <dir> --force   # 第二遍确定性校验用
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
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

ENGINE_PY = PROJECT / "backend" / "app" / "backtest" / "engine.py"
PROD_VARIANT = PARENT / "prod_file_snapshots" / "custom_mw7fvp17.py.variant_5510B_918254f0.py"
PROD_VARIANT_SHA = "918254f0e2bec567"

DIR_MAIN = PARENT / "strategies" / "custom"
DIR_GROSS = PARENT / "strategies_gross" / "custom"
DIR_PROD = HERE / "_inputs" / "prod_variant_5510B"

# tag, strategy_id, 策略目录, slippage_bps, gross, start, end
ARMS = [
    ("a0_10bp", "s01b_a0", DIR_MAIN, 10.0, False, "2019-07-01", "2026-10-30"),
    ("a0_30bp", "s01b_a0", DIR_MAIN, 30.0, False, "2019-07-01", "2026-10-30"),
    ("a0_gross", "s01b_a0", DIR_GROSS, 0.0, True, "2019-07-01", "2026-10-30"),
    ("a1_10bp", "s01b_a1", DIR_MAIN, 10.0, False, "2019-07-01", "2026-10-30"),
    ("a1_30bp", "s01b_a1", DIR_MAIN, 30.0, False, "2019-07-01", "2026-10-30"),
    ("a1_gross", "s01b_a1", DIR_GROSS, 0.0, True, "2019-07-01", "2026-10-30"),
    ("a2_10bp", "s01b_a2", DIR_MAIN, 10.0, False, "2019-07-01", "2026-10-30"),
    ("a2_30bp", "s01b_a2", DIR_MAIN, 30.0, False, "2019-07-01", "2026-10-30"),
    ("a2_gross", "s01b_a2", DIR_GROSS, 0.0, True, "2019-07-01", "2026-10-30"),
    ("a3_10bp", "s01b_a3", DIR_MAIN, 10.0, False, "2019-07-01", "2026-10-30"),
    ("a3_30bp", "s01b_a3", DIR_MAIN, 30.0, False, "2019-07-01", "2026-10-30"),
    ("a3_gross", "s01b_a3", DIR_GROSS, 0.0, True, "2019-07-01", "2026-10-30"),
    ("a2h_10bp", "s01b_a2h", DIR_MAIN, 10.0, False, "2019-07-01", "2026-10-30"),
    ("a4_10bp", "s01b_a4", DIR_MAIN, 10.0, False, "2019-07-01", "2026-10-30"),
    ("a0ev_10bp", "s01b_a0ev", DIR_MAIN, 10.0, False, "2019-07-01", "2026-10-30"),
    ("a3ev_10bp", "s01b_a3ev", DIR_MAIN, 10.0, False, "2019-07-01", "2026-10-30"),
    ("prod_file_10bp", "custom_mw7fvp17", DIR_PROD, 10.0, False, "2019-07-01", "2026-10-30"),
    ("smoke_a0", "s01b_a0", DIR_MAIN, 10.0, False, "2023-01-01", "2023-03-31"),
]
ARM_BY_TAG = {a[0]: a for a in ARMS}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_prod_variant() -> dict:
    """把归档快照还原成 _inputs/prod_variant_5510B/custom_mw7fvp17.py（只读用途）。"""
    DIR_PROD.mkdir(parents=True, exist_ok=True)
    dst = DIR_PROD / "custom_mw7fvp17.py"
    raw = PROD_VARIANT.read_bytes()
    if not dst.exists() or dst.read_bytes() != raw:
        dst.write_bytes(raw)
    sha = hashlib.sha256(dst.read_bytes()).hexdigest()
    if not sha.startswith(PROD_VARIANT_SHA):
        raise SystemExit(f"prod variant sha mismatch: {sha} != {PROD_VARIANT_SHA}*")
    return {"path": str(dst), "size": len(raw), "sha256": sha,
            "restored_from": str(PROD_VARIANT)}


def build_service(strategy_dir: Path) -> StrategyBacktestService:
    store = DataStore(settings.data_dir)
    engine = BacktestEngine(KlineRepository(store))
    return StrategyBacktestService(engine, StrategyEngine(strategy_dirs=[Path(strategy_dir)]))


def run_arm(tag: str, outroot: Path) -> dict:
    _, sid, sdir, slip, gross, start, end = ARM_BY_TAG[tag]
    outdir = outroot / tag
    outdir.mkdir(parents=True, exist_ok=True)
    service = build_service(sdir)
    s = service.strategy_engine.get(sid)
    strat_path = Path(s.file_path)
    strat_bytes = strat_path.read_bytes()
    policy = parse_backtest_defaults(
        s.meta.get("backtest_defaults"), context=f"strategy {sid}"
    )

    config = StrategyBacktestConfig(
        strategy_id=sid,
        symbols=None,
        start=date.fromisoformat(start),
        end=date.fromisoformat(end),
        params={},
        overrides={},
        matching="open_t+1",
        commission_pct=0.0 if gross else 0.0003,
        stamp_tax_pct=0.0 if gross else 0.001,
        slippage_bps=0.0 if gross else float(slip),
        max_positions=5,
        max_exposure_pct=0.6,
        initial_capital=1_000_000.0,
        position_sizing="equal",
        mode="position",
        asset_type="stock",
        holding_days=60,
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
        if p.exists():
            p.unlink()
        if not frame.is_empty():
            frame.write_parquet(p)
            files[f"{name}.parquet"] = sha256_file(p)

    effective_config = {
        "arm_tag": tag,
        "request": {
            "strategy_id": sid, "start": start, "end": end, "gross": gross,
            "slippage_bps": 0.0 if gross else slip,
            "commission_pct": 0.0 if gross else 0.0003,
            "stamp_tax_pct": 0.0 if gross else 0.001,
            "max_positions": 5, "max_exposure_pct": 0.6,
            "initial_capital": 1_000_000.0, "holding_days": 60,
            "matching": "open_t+1", "position_sizing": "equal", "mode": "position",
        },
        "strategy_file": {
            "path": str(strat_path),
            "size": len(strat_bytes),
            "sha256": hashlib.sha256(strat_bytes).hexdigest(),
            "meta_backtest_defaults": s.meta.get("backtest_defaults"),
        },
        "execution_policy_normalized": {
            "engine_options": policy.engine_options(),
        },
        "resolved_matcher_config": (result.provenance or {}).get("execution"),
        "engine_sha256": sha256_file(ENGINE_PY),
    }
    out = {
        "tag": tag,
        "strategy_id": sid,
        "start": start,
        "end": end,
        "gross": gross,
        "slippage_bps": 0.0 if gross else slip,
        "commission_pct": 0.0 if gross else 0.0003,
        "stamp_tax_pct": 0.0 if gross else 0.001,
        "elapsed_s": round(elapsed, 1),
        "error": result.error,
        "stats": result.stats,
        "n_trades": len(trades),
        "n_equity": len(equity),
        "n_drawdown": len(drawdown),
        "run_id": result.run_id,
        "engine_sha256": sha256_file(ENGINE_PY),
        "artifacts_sha256": files,
        "effective_config": effective_config,
    }
    (outdir / "result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    (outdir / "effective_config.json").write_text(
        json.dumps(effective_config, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8",
    )
    st = result.stats
    print(f"[arm] {tag:<15} sid={sid:<14} trades={len(trades):<5} "
          f"final={st.get('final_equity'):.2f} tot={st.get('total_return'):+.4f} "
          f"ann={st.get('annual_return'):+.4f} mdd={st.get('max_drawdown'):+.4f} "
          f"oae={st.get('open_at_end_count')} err={result.error} {elapsed:.1f}s",
          flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="逗号分隔的 tag 列表")
    ap.add_argument("--outdir-root", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--skip-existing", action="store_true", default=True)
    args = ap.parse_args()

    assert Path(settings.data_dir) == DATA_ROOT, "data_dir 不是研究侧独立根，拒绝运行"
    outroot = Path(args.outdir_root) if args.outdir_root else (HERE / "results_all")
    outroot.mkdir(parents=True, exist_ok=True)
    tags = [t.strip() for t in args.only.split(",") if t.strip()] or [a[0] for a in ARMS]
    bad = [t for t in tags if t not in ARM_BY_TAG]
    if bad:
        raise SystemExit(f"unknown tags: {bad}")

    engine_sha = sha256_file(ENGINE_PY)
    print(f"[env] engine.py size={ENGINE_PY.stat().st_size} sha256={engine_sha}", flush=True)
    print(f"[env] outroot={outroot}", flush=True)
    prod_info = ensure_prod_variant()
    print(f"[env] prod variant restored: {prod_info['size']}B sha256={prod_info['sha256']}",
          flush=True)

    ran, skipped, failed = [], [], []
    for tag in tags:
        if not args.force and (outroot / tag / "result.json").exists():
            skipped.append(tag)
            print(f"[skip] {tag} (result.json exists)", flush=True)
            continue
        try:
            out = run_arm(tag, outroot)
        except Exception as exc:  # noqa: BLE001
            failed.append((tag, repr(exc)))
            print(f"[FAIL] {tag}: {exc!r}", flush=True)
            continue
        if out.get("error"):
            failed.append((tag, out["error"]))
        else:
            ran.append(tag)
    print(f"[done] ran={len(ran)} skipped={len(skipped)} failed={len(failed)}", flush=True)
    if failed:
        for t, e in failed:
            print(f"[failed] {t}: {e}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
