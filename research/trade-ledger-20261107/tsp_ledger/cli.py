"""命令行入口。

    python -m tsp_ledger.cli import  <交割单.csv> [--db ...] [--data-root ...]
    python -m tsp_ledger.cli derive  [--out ...] [--compat]
    python -m tsp_ledger.cli daily   --date 2026-11-06 [--file 交割单.csv] [--signals 信号.csv]
    python -m tsp_ledger.cli verify  --baseline <data 目录> [--compat]
    python -m tsp_ledger.cli stats
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from . import analytics, export, store, verify
from .daily import daily_review
from .derive import bond_cost_map, build_daily, build_roundtrips
from .parse import read_jiaogedan
from .prices import load_calendar, load_prices

OPENING_CASH = 0.02
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "out"


def _db(args) -> Path:
    return Path(args.db) if args.db else store.ledger_path(args.data_root)


def _ingest(con: sqlite3.Connection, files: list[str]) -> list[dict]:
    out = []
    for f in files:
        res = read_jiaogedan(f)
        info = store.import_events(
            con, res.events, Path(f), res.encoding, res.total_rows, res.skipped_rows
        )
        info["warnings"] = res.warnings[:10]
        out.append(info)
    return out


def _derive_all(con: sqlite3.Connection, args):
    events = store.load_events(con)
    if not events:
        raise SystemExit("台账为空：先执行 import")
    cal = load_calendar()
    codes = {e.code for e in events if e.code}
    prices = load_prices(codes, min(e.trade_date for e in events), max(e.trade_date for e in events))
    cov = prices.coverage()
    if not cov["codes"] and not getattr(args, "allow_no_prices", False):
        raise SystemExit(
            "行情价格为 0 条：派生会把所有持仓市值算成 0，权益与盈亏全错。\n"
            "请用后端虚拟环境跑（backend/.venv/Scripts/python.exe，带 polars），"
            "或确认 D:\\TSP\\data\\kline_daily 存在；确实要无行情派生时加 --allow-no-prices。"
        )
    bond_cost = bond_cost_map(events)
    rts = build_roundtrips(
        events,
        cal,
        bond_cost=None if args.no_bond_cost else bond_cost,
        compat_newbond=getattr(args, "compat", False),
    )
    daily, positions, detail = build_daily(events, cal, prices, opening_cash=args.opening_cash)
    industry = analytics.load_industry_map()
    exposure = analytics.build_exposure(detail, industry)
    return events, cal, prices, rts, daily, positions, detail, exposure, industry


def cmd_import(args):
    con = store.connect(_db(args))
    info = _ingest(con, args.files)
    print(json.dumps({"db": str(_db(args)), "batches": info}, ensure_ascii=False, indent=2))


def cmd_derive(args):
    con = store.connect(_db(args))
    events, cal, prices, rts, daily, positions, detail, exposure, industry = _derive_all(con, args)
    batch = store.latest_batch(con)
    store.replace_derived(con, batch, rts, daily, detail, exposure_rows=exposure)
    out = Path(args.out)
    stats = {
        "trades": export.write_trades_clean(events, out / "trades_clean.csv"),
        "events": export.write_events(events, out / "events.csv"),
        "roundtrips": export.write_roundtrips(rts, out / "roundtrips.csv"),
        "daily_equity": export.write_daily_equity(daily, out / "daily_equity.csv"),
        "daily_positions": export.write_daily_positions(positions, out / "daily_positions.csv"),
        "exposure": export.write_exposure(exposure, out / "exposure.csv"),
        "industry_exposure": export.write_industry_exposure(
            analytics.industry_exposure(exposure), out / "industry_exposure.csv"
        ),
    }
    perf = analytics.performance(rts, cal.span(min(e.trade_date for e in events), max(e.trade_date for e in events)), daily, events)
    diag = {"prices": prices.coverage(), "opening_cash": args.opening_cash,
            "bond_cost_codes": sorted(bond_cost_map(events)) if not args.no_bond_cost else []}
    export.dump_json({"batch_id": batch, "outputs": stats, "performance": perf, **diag}, out / "summary.json")
    print(json.dumps({"batch_id": batch, "outputs": stats, "performance": perf, **diag}, ensure_ascii=False, indent=2))


def cmd_daily(args):
    con = store.connect(_db(args))
    if args.file:
        _ingest(con, [args.file])
    events, cal, prices, rts, daily, positions, detail, exposure, industry = _derive_all(con, args)
    res = daily_review(
        events, rts, daily, positions, args.date, Path(args.out),
        signals_path=Path(args.signals) if args.signals else None,
    )
    res["prices"] = prices.coverage()
    print(json.dumps(res, ensure_ascii=False, indent=2))


def cmd_verify(args):
    con = store.connect(_db(args))
    events, cal, prices, rts, daily, positions, detail, exposure, industry = _derive_all(con, args)
    report = verify.compare_all(events, rts, daily, positions, Path(args.baseline))
    if args.out:
        export.dump_json(report, Path(args.out) / "verify_report.json")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def cmd_stats(args):
    con = store.connect(_db(args))
    events, cal, prices, rts, daily, positions, detail, exposure, industry = _derive_all(con, args)
    span = cal.span(min(e.trade_date for e in events), max(e.trade_date for e in events))
    perf = analytics.performance(rts, span, daily, events)
    bridge = analytics.pnl_bridge(rts, daily, events, detail)
    print(json.dumps({"performance": perf, "bridge": bridge}, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tsp_ledger", description="交割单导入与复盘派生")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", help="SQLite 台账路径，默认 <data-root>/user_data/trade_ledger/ledger.sqlite")
    common.add_argument("--data-root", default=str(store.DEFAULT_DATA_ROOT), help="系统 data 目录，默认 D:\\TSP\\data")
    common.add_argument("--opening-cash", type=float, default=OPENING_CASH, help="期初现金，默认 0.02（按首日权益反推）")
    common.add_argument("--no-bond-cost", action="store_true", help="不把配售缴款成本挂到转债（复刻临时口径的 12 笔未配对）")
    common.add_argument("--compat", action="store_true", help="兼容口径：把新股入账当 0 价卖出，复刻 447 回合")
    common.add_argument("--allow-no-prices", action="store_true", help="允许行情价格为空仍派生（默认直接报错，防止市值被算成 0）")

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("import", help="导入交割单（幂等）", parents=[common])
    sp.add_argument("files", nargs="+")
    sp.set_defaults(func=cmd_import)

    sp = sub.add_parser("derive", help="重建派生表并导出 CSV", parents=[common])
    sp.add_argument("--out", default=str(DEFAULT_OUT))
    sp.set_defaults(func=cmd_derive)

    sp = sub.add_parser("daily", help="生成某交易日的复盘包", parents=[common])
    sp.add_argument("--date", required=True)
    sp.add_argument("--file", help="当日/最新交割单，给了就先导入")
    sp.add_argument("--signals", help="系统信号/计划 CSV（date,time,code,side,qty,px,signal_id）")
    sp.add_argument("--out", default=str(DEFAULT_OUT / "daily"))
    sp.set_defaults(func=cmd_daily)

    sp = sub.add_parser("verify", help="与临时基准目录比对", parents=[common])
    sp.add_argument("--baseline", required=True)
    sp.add_argument("--out")
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser("stats", help="打印区间绩效与桥接表", parents=[common])
    sp.set_defaults(func=cmd_stats)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
