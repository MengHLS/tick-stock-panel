"""HTTP surface for the trade-analysis extension."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Annotated, Any

import polars as pl
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.extensions import ExtensionRuntime, get_extension_runtime

from . import store
from .importer import ImportError as StatementImportError
from .importer import parse_statement
from .roundtrips import ANALYSIS_VERSION, analyze_trade, compute_roundtrips, normalize_bars

MAX_IMPORT_BYTES = 20 * 1024 * 1024


class NoteRequest(BaseModel):
    note: str = Field(default="", max_length=4000)
    tags: list[str] = Field(default_factory=list)


def _bars(runtime: ExtensionRuntime, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
    try:
        frame = runtime.analysis.daily(symbol, start, end)
    except Exception:  # noqa: BLE001 - market data is optional for basic review
        return []
    if frame is None or frame.is_empty():
        return []
    return normalize_bars(frame)


def _ensure_analysis(
    runtime: ExtensionRuntime,
    trades: list[dict[str, Any]],
    *,
    force: bool = False,
) -> dict[str, dict[str, Any]]:
    cached = {} if force else {
        key: value
        for key, value in store.get_analysis(runtime.data_dir).items()
        if value.get("_version") == ANALYSIS_VERSION
    }
    missing = [
        trade for trade in trades
        if force or trade["trade_key"] not in cached
    ]
    if not missing:
        return cached

    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in missing:
        by_symbol[trade["symbol"]].append(trade)
    computed: dict[str, dict[str, Any]] = {}
    all_rows = [item for rows in by_symbol.values() for item in rows]
    start = min(date.fromisoformat(item["open_date"]) for item in all_rows) - timedelta(days=45)
    end = max(date.fromisoformat(item["close_date"]) for item in all_rows) + timedelta(days=40)
    bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
    try:
        frame = runtime.market_data.get_daily_batch(
            list(by_symbol),
            start,
            end,
            columns=["symbol", "date", "open", "high", "low", "close"],
        )
        if frame is not None and not frame.is_empty() and "symbol" in frame.columns:
            for symbol in by_symbol:
                part = frame.filter(pl.col("symbol") == symbol)
                bars_by_symbol[symbol] = normalize_bars(part)
    except Exception:  # noqa: BLE001 - fall back to per-symbol reads
        bars_by_symbol = {}

    for symbol, rows in by_symbol.items():
        bars = bars_by_symbol.get(symbol)
        if bars is None:
            open_days = [date.fromisoformat(item["open_date"]) for item in rows]
            close_days = [date.fromisoformat(item["close_date"]) for item in rows]
            bars = _bars(
                runtime,
                symbol,
                min(open_days) - timedelta(days=45),
                max(close_days) + timedelta(days=40),
            )
        for trade in rows:
            computed[trade["trade_key"]] = analyze_trade(trade, bars)
    store.save_analysis(runtime.data_dir, computed, ANALYSIS_VERSION)
    cached.update(computed)
    return cached


def _with_meta(
    trades: list[dict[str, Any]],
    analysis: dict[str, dict[str, Any]],
    notes: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for trade in trades:
        review = analysis.get(trade["trade_key"], {})
        note = notes.get(trade["trade_key"], {})
        result.append({
            **trade,
            **{key: value for key, value in review.items() if not key.startswith("_")},
            "note": note.get("note", ""),
            "user_tags": note.get("tags", []),
            "patterns": note.get("tags", []),
            "note_updated_at": note.get("updated_at"),
        })
    return result


def _summary(rows: list[dict[str, Any]], fills: list[dict[str, Any]], open_lots: list[dict[str, Any]]) -> dict[str, Any]:
    pnls = [float(item["pnl"]) for item in rows]
    rets = [float(item["ret"]) for item in rows if item.get("ret") is not None]
    wins = [item for item in rows if float(item["pnl"]) > 0]
    losses = [item for item in rows if float(item["pnl"]) < 0]
    gross_win = sum(float(item["pnl"]) for item in wins)
    gross_loss = abs(sum(float(item["pnl"]) for item in losses))
    total_pnl = sum(pnls)
    average_win = gross_win / len(wins) if wins else None
    average_loss = -gross_loss / len(losses) if losses else None
    total_fees = sum(float(item["fees"]) for item in rows)
    hold_days = [float(item["hold_days"]) for item in rows]

    ordered = sorted(rows, key=lambda item: (item["close_date"], item["close_time"]))
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    curve: list[dict[str, Any]] = []
    for item in ordered:
        cumulative += float(item["pnl"])
        peak = max(peak, cumulative)
        max_drawdown = min(max_drawdown, cumulative - peak)
        curve.append({
            "date": item["close_date"],
            "pnl": float(item["pnl"]),
            "cum_pnl": cumulative,
        })

    grouped: dict[str, dict[str, Any]] = {}
    for item in rows:
        entry = grouped.setdefault(item["symbol"], {
            "symbol": item["symbol"],
            "name": item["name"],
            "trades": 0,
            "wins": 0,
            "pnl": 0.0,
            "return_sum": 0.0,
            "return_count": 0,
            "last_close": item["close_date"],
        })
        entry["trades"] += 1
        entry["pnl"] += float(item["pnl"])
        if float(item["pnl"]) > 0:
            entry["wins"] += 1
        if item.get("ret") is not None:
            entry["return_sum"] += float(item["ret"])
            entry["return_count"] += 1
        entry["last_close"] = max(entry["last_close"], item["close_date"])
        if item["name"]:
            entry["name"] = item["name"]
    symbols = []
    for entry in grouped.values():
        symbols.append({
            **entry,
            "win_rate": entry["wins"] / entry["trades"] if entry["trades"] else None,
            "avg_ret": entry["return_sum"] / entry["return_count"] if entry["return_count"] else None,
        })
    symbols.sort(key=lambda item: abs(item["pnl"]), reverse=True)

    return {
        "fills": len(fills),
        "trades": len(rows),
        "open_positions": len(open_lots),
        "total_pnl": total_pnl,
        "win_rate": len(wins) / len(rows) if rows else None,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else None,
        "payoff": average_win / abs(average_loss) if average_win and average_loss else None,
        "avg_win": average_win,
        "avg_loss": average_loss,
        "avg_ret": sum(rets) / len(rets) if rets else None,
        "avg_hold_days": sum(hold_days) / len(hold_days) if hold_days else None,
        "total_fees": total_fees,
        "max_drawdown": max_drawdown,
        "first_date": min((item["trade_date"] for item in fills), default=None),
        "last_date": max((item["trade_date"] for item in fills), default=None),
        "curve": curve,
        "symbols": symbols,
        "positions": open_lots,
    }


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/custom/trade-analysis", tags=["trade-analysis"])

    @router.get("/overview")
    def overview(
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
        include_trades: Annotated[bool, Query()] = False,
    ) -> dict[str, Any]:
        fills = store.list_fills(runtime.data_dir)
        trades, open_lots = compute_roundtrips(fills)
        analysis = _ensure_analysis(runtime, trades)
        notes = store.get_notes(runtime.data_dir)
        data = _summary(trades, fills, open_lots)
        meta = store.get_meta(runtime.data_dir)
        data["last_import_at"] = meta.get("last_import_at")
        if include_trades:
            data["trade_rows"] = _with_meta(trades, analysis, notes)
        return data

    @router.get("/trades")
    def list_trades(
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
        symbol: Annotated[str | None, Query()] = None,
        result: Annotated[str | None, Query(pattern="^(win|loss)$")] = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    ) -> dict[str, Any]:
        fills = store.list_fills(runtime.data_dir)
        trades, _ = compute_roundtrips(fills)
        filtered = trades
        if symbol:
            filtered = [item for item in filtered if symbol.upper() in item["symbol"] or symbol in item["name"]]
        if result == "win":
            filtered = [item for item in filtered if float(item["pnl"]) > 0]
        elif result == "loss":
            filtered = [item for item in filtered if float(item["pnl"]) < 0]
        analysis = _ensure_analysis(runtime, filtered)
        notes = store.get_notes(runtime.data_dir)
        return {
            "total": len(filtered),
            "trades": _with_meta(filtered[:limit], analysis, notes),
        }

    @router.get("/trades/{trade_key}")
    def trade_detail(
        trade_key: str,
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict[str, Any]:
        fills = store.list_fills(runtime.data_dir)
        trades, _ = compute_roundtrips(fills)
        trade = next((item for item in trades if item["trade_key"] == trade_key), None)
        if trade is None:
            raise HTTPException(404, "交易不存在")
        analysis = _ensure_analysis(runtime, [trade])
        notes = store.get_notes(runtime.data_dir)
        return _with_meta([trade], analysis, notes)[0]

    @router.put("/trades/{trade_key}/note")
    def update_note(
        trade_key: str,
        payload: NoteRequest,
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict[str, Any]:
        fills = store.list_fills(runtime.data_dir)
        trades, _ = compute_roundtrips(fills)
        if not any(item["trade_key"] == trade_key for item in trades):
            raise HTTPException(404, "交易不存在")
        return store.save_note(
            runtime.data_dir,
            trade_key,
            note=payload.note,
            tags=payload.tags,
        )

    @router.post("/import")
    async def import_statement(
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
        file: Annotated[UploadFile, File()],
    ) -> dict[str, Any]:
        raw = await file.read(MAX_IMPORT_BYTES + 1)
        if len(raw) > MAX_IMPORT_BYTES:
            raise HTTPException(400, "对账单超过 20MB")
        try:
            rows = parse_statement(raw, source_file=file.filename or "")
        except StatementImportError as exc:
            raise HTTPException(400, str(exc)) from exc
        inserted, duplicates = store.insert_fills(runtime.data_dir, rows)
        fills = store.list_fills(runtime.data_dir)
        trades, open_lots = compute_roundtrips(fills)
        analysis = _ensure_analysis(runtime, trades)
        return {
            "inserted": inserted,
            "duplicates": duplicates,
            "trades": len(trades),
            "open_positions": len(open_lots),
            "analyzed": len(analysis),
        }

    @router.post("/reanalyze")
    def reanalyze(
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict[str, Any]:
        fills = store.list_fills(runtime.data_dir)
        trades, _ = compute_roundtrips(fills)
        store.clear_analysis(runtime.data_dir)
        analysis = _ensure_analysis(runtime, trades, force=True)
        return {"trades": len(trades), "analyzed": len(analysis)}

    return router
