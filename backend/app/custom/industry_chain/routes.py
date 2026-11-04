"""HTTP surface for the industry-chain graph and analysis."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.custom.industry_chain.models import IndustryChainGraphSave
from app.custom.industry_chain.service import analyze_graph
from app.custom.industry_chain.store import ConflictError, load_graph, save_graph
from app.extensions import ExtensionRuntime, get_extension_runtime


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

    return router


def _with_stock_names(runtime: ExtensionRuntime, graph: dict) -> dict:
    symbols = sorted({link["symbol"] for link in graph["stock_links"]})
    return {
        **graph,
        "stock_names": runtime.analysis.names(symbols) if symbols else {},
    }
