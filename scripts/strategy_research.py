"""Local CLI for importing a T74 baseline and generating path reports.

The API uses the same service module. This CLI exists so a large archived JSON
result can be moved into the research inbox and diagnosed without starting the
web app.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.custom.strategy_research.baseline import (  # noqa: E402
    baseline_from_result_payload,
    load_baseline,
)
from app.custom.strategy_research.service import (  # noqa: E402
    create_path_report,
    get_reports,
    report_summary,
)
from app.custom.strategy_research.store import (  # noqa: E402
    resolve_inbox_file,
    results_dir,
    write_json_atomic,
)
from app.extensions.adapters import FileMarketData  # noqa: E402


def _safe_name(value: str) -> str:
    name = Path(value).name.strip()
    if not name:
        raise SystemExit("基线文件名不能为空")
    if not name.lower().endswith(".json"):
        name = f"{name}.json"
    if name in {".", ".."} or "/" in name or "\\" in name:
        raise SystemExit("基线文件名不合法")
    return name


def import_baseline(args: argparse.Namespace) -> None:
    source = Path(args.path)
    if not source.is_file():
        raise SystemExit(f"找不到基线文件: {source}")
    target_name = _safe_name(args.name or source.name)
    target = settings.data_dir / "user_data" / "research" / "strategy_research" / "inbox" / target_name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not args.force:
        raise SystemExit(f"目标已存在，如需覆盖请加 --force: {target}")
    shutil.copyfile(source, target)
    print(json.dumps({"imported": str(target)}, ensure_ascii=False))


def create_report(args: argparse.Namespace) -> None:
    thresholds = [
        float(item.strip())
        for item in args.thresholds.split(",")
        if item.strip()
    ]
    baseline = load_baseline(
        data_dir=settings.data_dir,
        source_kind="file",
        saved_id=None,
        file_name=args.file,
        label=args.label,
    )
    report = create_path_report(
        data_dir=settings.data_dir,
        market_data=FileMarketData(settings.data_dir),
        baseline=baseline,
        horizon_sessions=args.horizon,
        thresholds=thresholds,
        label=args.label,
        entry_price_basis=args.basis,
    )
    print(json.dumps(report_summary(report), ensure_ascii=False, indent=2))


def run_variant(args: argparse.Namespace) -> None:
    source_path = resolve_inbox_file(settings.data_dir, args.file)
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    payload = raw.get("result") if isinstance(raw, dict) and isinstance(raw.get("result"), dict) else raw
    if not isinstance(payload, dict):
        raise SystemExit("基线文件不是可读取的回测结果")
    config = payload.get("config") or {}
    provenance = payload.get("provenance") or {}
    params = dict(provenance.get("params") or {})
    params.update(config.get("params") or {})
    overrides = dict(config.get("overrides") or {})
    execution = provenance.get("execution") or {}
    if execution.get("stop_loss_pct") is not None:
        overrides.setdefault("stop_loss", execution["stop_loss_pct"])
    if execution.get("take_profit_pct") is not None:
        overrides.setdefault("take_profit", execution["take_profit_pct"])
    if execution.get("trailing_take_profit_activate_pct") is not None:
        overrides.setdefault(
            "trailing_take_profit_activate",
            execution["trailing_take_profit_activate_pct"],
        )
    if execution.get("trailing_take_profit_drawdown_pct") is not None:
        overrides.setdefault(
            "trailing_take_profit_drawdown",
            execution["trailing_take_profit_drawdown_pct"],
        )
    if args.stop_loss is not None:
        overrides["stop_loss"] = args.stop_loss
    if args.take_profit is not None:
        overrides["take_profit"] = args.take_profit
    if args.trailing_activate is not None:
        overrides["trailing_take_profit_activate"] = args.trailing_activate
    if args.trailing_drawdown is not None:
        overrides["trailing_take_profit_drawdown"] = args.trailing_drawdown
    holding_days = args.holding_days or int(config.get("holding_days") or 5)
    overrides["max_hold_days"] = holding_days

    from app.backtest.engine import BacktestEngine
    from app.backtest.strategy import StrategyBacktestConfig, StrategyBacktestService
    from app.strategy.engine import StrategyEngine
    from app.tickflow.repository import DataStore, KlineRepository

    service = StrategyBacktestService(
        BacktestEngine(KlineRepository(DataStore(settings.data_dir))),
        StrategyEngine(strategy_dirs=[]),
    )
    result = service.run(
        StrategyBacktestConfig(
            strategy_id=str(config.get("strategy_id") or ""),
            symbols=None,
            start=date.fromisoformat(str(config["start"])[:10]),
            end=date.fromisoformat(str(config["end"])[:10]),
            params=params,
            overrides=overrides,
            entry_fill=config.get("entry_fill") or "open_t+1",
            exit_fill=config.get("exit_fill") or "open_t+1",
            fees_pct=float(config.get("fees_pct") or 0.0002),
            commission_pct=config.get("commission_pct"),
            stamp_tax_pct=config.get("stamp_tax_pct"),
            slippage_bps=float(config.get("slippage_bps") or 5.0),
            max_positions=int(config.get("max_positions") or 5),
            max_exposure_pct=float(config.get("max_exposure_pct") or 1.0),
            initial_capital=float(config.get("initial_capital") or 100000.0),
            position_sizing=config.get("position_sizing") or "equal",
            mode=config.get("mode") or "position",
            holding_days=holding_days,
        )
    )
    if result.error:
        raise SystemExit(result.error)
    output = {
        "error": None,
        "run_id": result.run_id,
        "stats": result.stats,
        "trades": result.trades,
        "equity_curve": result.equity_curve,
        "config": result.config,
        "provenance": result.provenance,
        "strategy_info": result.strategy_info,
    }
    name = _safe_name(args.name or f"variant_{date.today().isoformat()}")
    target = results_dir(settings.data_dir) / name
    if target.exists() and not args.force:
        raise SystemExit(f"结果文件已存在，如需覆盖请加 --force: {target}")
    write_json_atomic(target, output)
    print(
        json.dumps(
            {
                "result": str(target),
                "stats": {
                    key: result.stats.get(key)
                    for key in (
                        "total_return",
                        "max_drawdown",
                        "n_trades",
                        "completed_trade_count",
                        "open_at_end_count",
                        "final_equity",
                    )
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.report:
        identity = hashlib.sha256(
            json.dumps(output, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        baseline = baseline_from_result_payload(
            output,
            source={"kind": "variant", "file_name": name, "sha256": identity},
            label=args.report_label or name,
            identity_seed=f"variant:{identity}",
            default_label=name,
        )
        report = create_path_report(
            data_dir=settings.data_dir,
            market_data=FileMarketData(settings.data_dir),
            baseline=baseline,
            horizon_sessions=args.horizon,
            thresholds=[
                float(item.strip())
                for item in args.thresholds.split(",")
                if item.strip()
            ],
            label=args.report_label,
            entry_price_basis=args.basis,
        )
        print(json.dumps(report_summary(report), ensure_ascii=False, indent=2))


def list_reports(_: argparse.Namespace) -> None:
    print(
        json.dumps(
            get_reports(settings.data_dir),
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="T74 strategy research tools")
    sub = parser.add_subparsers(dest="command", required=True)

    import_parser = sub.add_parser("import-baseline", help="copy a result JSON into the research inbox")
    import_parser.add_argument("path")
    import_parser.add_argument("--name")
    import_parser.add_argument("--force", action="store_true")
    import_parser.set_defaults(func=import_baseline)

    report_parser = sub.add_parser("report", help="create a path-diagnostic report")
    report_parser.add_argument("--file", required=True, help="JSON filename in the research inbox")
    report_parser.add_argument("--horizon", type=int, default=20)
    report_parser.add_argument("--thresholds", default="0.2,0.3,0.5")
    report_parser.add_argument("--label")
    report_parser.add_argument("--basis", choices=["auto", "raw", "adjusted"], default="auto")
    report_parser.set_defaults(func=create_report)

    variant_parser = sub.add_parser(
        "run-variant",
        help="run a controlled T74 exit variant through the core backtest engine",
    )
    variant_parser.add_argument("--file", required=True, help="baseline JSON in the research inbox")
    variant_parser.add_argument("--name", required=True, help="result JSON filename")
    variant_parser.add_argument("--force", action="store_true")
    variant_parser.add_argument("--stop-loss", type=float)
    variant_parser.add_argument("--take-profit", type=float)
    variant_parser.add_argument("--trailing-activate", type=float)
    variant_parser.add_argument("--trailing-drawdown", type=float)
    variant_parser.add_argument("--holding-days", type=int)
    variant_parser.add_argument("--report", action="store_true")
    variant_parser.add_argument("--report-label")
    variant_parser.add_argument("--horizon", type=int, default=20)
    variant_parser.add_argument("--thresholds", default="0.2,0.3,0.5")
    variant_parser.add_argument("--basis", choices=["auto", "raw", "adjusted"], default="auto")
    variant_parser.set_defaults(func=run_variant)

    list_parser = sub.add_parser("list", help="list saved path reports")
    list_parser.set_defaults(func=list_reports)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
