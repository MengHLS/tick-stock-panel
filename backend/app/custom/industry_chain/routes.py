"""HTTP surface for the industry-chain graph and analysis."""
from __future__ import annotations

import math
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.custom.industry_chain.models import IndustryChainGraphSave
from app.custom.industry_chain.service import analyze_graph
from app.custom.industry_chain.store import ConflictError, load_graph, save_graph
from app.extensions import ExtensionRuntime, get_extension_runtime
from app.market_time import cn_today


def build_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/custom/industry-chain",
        tags=["custom-industry-chain"],
    )

    @router.get("/graph")
    def get_graph(
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict:
        try:
            return _with_stock_names(runtime, load_graph(runtime.data_dir))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.put("/graph")
    def put_graph(
        payload: IndustryChainGraphSave,
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict:
        try:
            saved = save_graph(
                runtime.data_dir,
                payload.graph,
                expected_updated_at=payload.expected_updated_at,
            )
            return _with_stock_names(runtime, saved)
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/analysis")
    def get_analysis(
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
        chain_id: str = Query(..., min_length=1),
        node_id: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> dict:
        try:
            graph = load_graph(runtime.data_dir)
            names = runtime.analysis.names(
                sorted({link["symbol"] for link in graph["stock_links"]})
            )
            return analyze_graph(
                graph,
                chain_id=chain_id,
                node_id=node_id,
                start=start,
                end=end,
                market_data=runtime.market_data,
                name_for=lambda symbol: names.get(symbol),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/quotes")
    def get_quotes(
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict:
        """Latest cached day change for every stock in the graph.

        This reads the same enriched snapshot used by the watchlist and stock
        preview. It never calls a per-symbol history endpoint and never triggers
        an on-demand industry analysis. ``change_pct`` stays a decimal ratio
        (0.0366 means 3.66%), matching the enriched/watchlist contract.
        """
        try:
            graph = load_graph(runtime.data_dir)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        symbols = {link["symbol"] for link in graph["stock_links"]}
        service = runtime.quote_service
        if service is None:
            return _empty_quote_payload(available=False)

        frame, as_of = service.get_enriched_today()
        status = service.status()
        if frame is None or frame.is_empty() or "symbol" not in frame.columns:
            return _empty_quote_payload(
                available=True,
                as_of=as_of,
                status=status,
            )

        keep = [
            column
            for column in ("symbol", "close", "prev_close", "change_pct", "change_amount")
            if column in frame.columns
        ]
        if "symbol" not in keep:
            return _empty_quote_payload(
                available=True,
                as_of=as_of,
                status=status,
            )

        rows: dict[str, dict] = {}
        for row in frame.select(keep).unique(subset=["symbol"], keep="last").iter_rows(named=True):
            symbol = str(row.get("symbol") or "")
            if symbol not in symbols:
                continue
            rows[symbol] = {
                "symbol": symbol,
                "price": _finite_number(row.get("close")),
                "prev_close": _finite_number(row.get("prev_close")),
                "change_pct": _finite_number(row.get("change_pct")),
                "change_amount": _finite_number(row.get("change_amount")),
            }

        as_of_text = _iso_date(as_of)
        return {
            "available": True,
            "as_of": as_of_text,
            "is_today": as_of_text == cn_today().isoformat(),
            "last_fetch_ms": _finite_number(status.get("last_fetch_ms")),
            "status": _quote_status(status),
            "rows": [rows[symbol] for symbol in sorted(rows)],
        }

    return router


def _empty_quote_payload(
    *,
    available: bool,
    as_of: date | str | None = None,
    status: dict | None = None,
) -> dict:
    as_of_text = _iso_date(as_of)
    return {
        "available": available,
        "as_of": as_of_text,
        "is_today": as_of_text == cn_today().isoformat() if as_of_text else False,
        "last_fetch_ms": _finite_number((status or {}).get("last_fetch_ms")),
        "status": _quote_status(status or {}),
        "rows": [],
    }


def _quote_status(status: dict) -> dict:
    return {
        key: status.get(key)
        for key in ("enabled", "running", "paused", "market_phase", "final_sync_failed")
        if key in status
    }


def _iso_date(value: date | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text[:10] if text else None


def _finite_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _with_stock_names(runtime: ExtensionRuntime, graph: dict) -> dict:
    symbols = sorted({link["symbol"] for link in graph["stock_links"]})
    return {
        **graph,
        "stock_names": runtime.analysis.names(symbols) if symbols else {},
    }
