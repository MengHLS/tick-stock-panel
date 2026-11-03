"""Live first-board right-tail observation extension."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.custom.first_board_right_tail.service import (
    FirstBoardRightTailService,
    build_simple_monitor_rules,
)
from app.extensions import (
    BACKEND_EXTENSION_API_VERSION,
    BackendExtensionRegistrar,
    ExtensionContext,
    ExtensionRuntime,
    QuoteUpdateContext,
    QuoteUpdateObserver,
    get_extension_runtime,
)

EXTENSION_ID = "official.first-board-right-tail"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION

_service: FirstBoardRightTailService | None = None


class ImportRequest(BaseModel):
    event_date: date | None = None


class _Observer(QuoteUpdateObserver):
    def watched_symbols(self) -> frozenset[str]:
        return _service.watched_symbols() if _service is not None else frozenset()

    def on_quote_update(self, context: QuoteUpdateContext) -> list[dict[str, Any]]:
        if _service is None:
            return []
        return _service.on_quote_update(context.observed_at, context.quotes)


_OBSERVER = _Observer()


def startup(context: ExtensionContext) -> None:
    global _service
    _service = FirstBoardRightTailService(
        None,
        context.data_dir,
        market_data=context.market_data,
        enriched_panel=context.enriched_panel,
    )


def setup(registrar: BackendExtensionRegistrar) -> None:
    router = APIRouter(prefix="/api/custom/first-board-right-tail", tags=["first-board-right-tail"])

    @router.get("/overview")
    def overview() -> dict[str, Any]:
        return _require_service().overview()

    @router.post("/import-latest")
    def import_latest(req: ImportRequest | None = None) -> dict[str, Any]:
        try:
            return _require_service().import_latest(req.event_date if req else None)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/evaluate")
    def evaluate(
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict[str, Any]:
        events = _require_service().evaluate_now()
        runtime.alerts.publish(events)
        return {"ok": True, "events": events, "count": len(events)}

    @router.post("/simple-monitor-rules")
    def simple_monitor_rules(
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict[str, Any]:
        service = _require_service()
        events = [
            event for event in service.load_state().get("events", [])
            if event.get("status") in {"WATCH", "BUY_PENDING"}
        ]
        rules = build_simple_monitor_rules(events)
        if not rules:
            raise HTTPException(400, "观察池为空，请先导入最新首板")
        from app.services.kline_sync import intraday_monitor_support

        support = intraday_monitor_support(runtime.capabilities)
        if not support["available"]:
            raise HTTPException(403, str(support["reason"]))
        if len(events) > int(support["max_symbols"]):
            raise HTTPException(
                400,
                f"当前分时能力最多监听 {support['max_symbols']} 只，观察池已有 {len(events)} 只",
            )
        runtime.monitor_rules.save_and_sync(rules)
        return {"ok": True, "rules": rules}

    @router.post("/events/{event_id}/reset")
    def reset_event(event_id: str) -> dict[str, Any]:
        if not _require_service().reset_event(event_id):
            raise HTTPException(404, "观察事件不存在")
        return {"ok": True}

    @router.delete("/events/{event_id}")
    def remove_event(event_id: str) -> dict[str, Any]:
        if not _require_service().remove_event(event_id):
            raise HTTPException(404, "观察事件不存在")
        return {"ok": True}

    registrar.include_router(router)
    registrar.register_quote_observer("official.first-board-right-tail.live", _OBSERVER)


def _require_service() -> FirstBoardRightTailService:
    if _service is None:
        raise HTTPException(503, "首板右尾观察服务尚未初始化")
    return _service
