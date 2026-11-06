"""Generic name-theme analyzer with user-managed stock pools."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.extensions import (
    BACKEND_EXTENSION_API_VERSION,
    BackendExtensionRegistrar,
    ExtensionContext,
    ExtensionRuntime,
    get_extension_runtime,
)

from . import store
from .linking import resolve_theme
from .models import StockAddRequest, ThemeCreate, ThemeUpdate
from .service import MINUTE_SAMPLE_LIMIT, ThemeAnalyzerService

EXTENSION_ID = "local.theme-analyzer"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION

router = APIRouter(prefix="/api/custom/theme-analyzer", tags=["theme-analyzer"])


def setup(registrar: BackendExtensionRegistrar) -> None:
    registrar.include_router(router)


def startup(context: ExtensionContext) -> None:
    if context.market_data is not None:
        store.seed_default_theme(context.data_dir, context.market_data)


@router.get("/themes")
def list_themes(
    runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
) -> dict[str, Any]:
    return {"items": [resolve_theme(runtime.data_dir, theme) for theme in store.list_themes(runtime.data_dir)]}


@router.post("/themes")
def create_theme(
    payload: ThemeCreate,
    runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
) -> dict[str, Any]:
    service = ThemeAnalyzerService(runtime.market_data, data_dir=runtime.data_dir)
    try:
        symbols = service.validate_symbols(payload.symbols)
        source = payload.industry_source.model_dump() if payload.industry_source else {}
        resolve_theme(runtime.data_dir, {"symbols": symbols, "industry_source": source}, strict=True)
        theme = store.create_theme(
            runtime.data_dir,
            name=payload.name,
            description=payload.description,
            color=payload.color,
            symbols=symbols,
            industry_source=source,
        )
        return resolve_theme(runtime.data_dir, theme)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.put("/themes/{theme_id}")
def update_theme(
    theme_id: str,
    payload: ThemeUpdate,
    runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
) -> dict[str, Any]:
    symbols = payload.symbols
    if symbols is not None:
        try:
            symbols = ThemeAnalyzerService(
                runtime.market_data, data_dir=runtime.data_dir,
            ).validate_symbols(symbols)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    current = store.get_theme(runtime.data_dir, theme_id)
    if current is None:
        raise HTTPException(404, "主题不存在")
    source = (
        payload.industry_source.model_dump() if payload.industry_source else {}
    ) if "industry_source" in payload.model_fields_set else None
    try:
        resolve_theme(runtime.data_dir, {
            **current,
            "symbols": symbols if symbols is not None else current["symbols"],
            "industry_source": source if source is not None else current.get("industry_source"),
        }, strict=True)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    theme = store.update_theme(
        runtime.data_dir,
        theme_id,
        name=payload.name,
        description=payload.description,
        color=payload.color,
        symbols=symbols,
        industry_source=source,
    )
    if theme is None:
        raise HTTPException(404, "主题不存在")
    return resolve_theme(runtime.data_dir, theme)


@router.delete("/themes/{theme_id}")
def delete_theme(
    theme_id: str,
    runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
) -> dict[str, Any]:
    if not store.delete_theme(runtime.data_dir, theme_id):
        raise HTTPException(404, "主题不存在")
    return {"ok": True}


@router.post("/themes/{theme_id}/stocks")
def add_stocks(
    theme_id: str,
    payload: StockAddRequest,
    runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
) -> dict[str, Any]:
    try:
        symbols = ThemeAnalyzerService(
            runtime.market_data, data_dir=runtime.data_dir,
        ).validate_symbols(payload.symbols)
        current = store.get_theme(runtime.data_dir, theme_id)
        inherited: list[str] = []
        if current is not None:
            resolved = resolve_theme(runtime.data_dir, {
                **current, "symbols": list(dict.fromkeys([*current["symbols"], *symbols])),
                "excluded_symbols": [item for item in current.get("excluded_symbols", []) if item not in symbols],
            }, strict=True)
            inherited = resolved["inherited_symbols"]
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    theme = store.add_symbols(runtime.data_dir, theme_id, symbols, inherited_symbols=inherited)
    if theme is None:
        raise HTTPException(404, "主题不存在")
    return resolve_theme(runtime.data_dir, theme)


@router.delete("/themes/{theme_id}/stocks/{symbol}")
def remove_stock(
    theme_id: str,
    symbol: str,
    runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
) -> dict[str, Any]:
    current = store.get_theme(runtime.data_dir, theme_id)
    if current is None:
        raise HTTPException(404, "主题不存在")
    resolved = resolve_theme(runtime.data_dir, current)
    if symbol.upper() not in resolved["symbols"]:
        raise HTTPException(404, "股票不在该主题中")
    theme, removed = store.remove_symbol(
        runtime.data_dir, theme_id, symbol,
        inherited=symbol.upper() in resolved["inherited_symbols"],
    )
    if theme is None:
        raise HTTPException(404, "主题不存在")
    if not removed:
        raise HTTPException(404, "股票不在该主题中")
    return resolve_theme(runtime.data_dir, theme)


@router.get("/themes/{theme_id}/analysis")
def analyze_theme(
    theme_id: str,
    runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    start: Annotated[date | None, Query()] = None,
    end: Annotated[date | None, Query()] = None,
    mainboard_only: Annotated[bool, Query()] = True,
) -> dict[str, Any]:
    theme = store.get_theme(runtime.data_dir, theme_id)
    if theme is None:
        raise HTTPException(404, "主题不存在")
    try:
        theme = resolve_theme(runtime.data_dir, theme, strict=True)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if start and end and start > end:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    return ThemeAnalyzerService(runtime.market_data, data_dir=runtime.data_dir).analyze(
        theme,
        start=start,
        end=end,
        mainboard_only=mainboard_only,
    )


@router.get("/themes/{theme_id}/minute")
def minute_overlay(
    theme_id: str,
    trade_date: Annotated[date, Query(alias="date")],
    runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    symbols: Annotated[str | None, Query()] = None,
    mainboard_only: Annotated[bool, Query()] = True,
) -> dict[str, Any]:
    theme = store.get_theme(runtime.data_dir, theme_id)
    if theme is None:
        raise HTTPException(404, "主题不存在")
    try:
        theme = resolve_theme(runtime.data_dir, theme, strict=True)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    selected = [
        item.strip()
        for item in (symbols or "").split(",")
        if item.strip()
    ]
    if len(selected) > MINUTE_SAMPLE_LIMIT:
        raise HTTPException(400, f"分钟叠加最多选择 {MINUTE_SAMPLE_LIMIT} 只股票")
    return ThemeAnalyzerService(runtime.market_data, data_dir=runtime.data_dir).minute_overlay(
        theme,
        trade_date,
        selected,
        mainboard_only=mainboard_only,
    )

