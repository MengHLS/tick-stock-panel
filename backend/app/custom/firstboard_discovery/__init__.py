"""First-board factor discovery extension."""
from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.custom.firstboard_discovery.service import DiscoveryParams, FirstboardDiscoveryService
from app.custom.firstboard_discovery.storage import FirstboardDiscoveryStore
from app.enriched_generation import EnrichedGenerationUnavailableError
from app.extensions import (
    BACKEND_EXTENSION_API_VERSION,
    BackendExtensionRegistrar,
    ExtensionContext,
)

EXTENSION_ID = "official.firstboard-discovery"
EXTENSION_API_VERSION = BACKEND_EXTENSION_API_VERSION
_service: FirstboardDiscoveryService | None = None


def startup(context: ExtensionContext) -> None:
    global _service
    _service = FirstboardDiscoveryService(
        context.repository,
        storage=FirstboardDiscoveryStore(context.data_dir),
    )


def setup(registrar: BackendExtensionRegistrar) -> None:
    router = APIRouter(prefix="/api/custom/firstboard-discovery", tags=["firstboard-discovery"])

    @router.get("/report")
    def report(
        start: date,
        end: date,
        snapshot_mode: Literal["D_minus_1", "D_close", "both"] = "both",
        horizon: int = 20,
        strong_threshold: float = 0.20,
    ) -> dict:
        return _call("report", start, end, snapshot_mode, horizon, strong_threshold)

    @router.get("/events")
    def events(
        start: date,
        end: date,
        snapshot_mode: Literal["D_minus_1", "D_close", "both"] = "both",
        horizon: int = 20,
        strong_threshold: float = 0.20,
        page: int = Query(1, ge=1),
        page_size: int = Query(100, ge=1, le=200),
        rule_id: str | None = Query(None, max_length=64),
    ) -> dict:
        return _call(
            "events", start, end, snapshot_mode, horizon, strong_threshold,
            page=page, page_size=page_size, rule_id=rule_id,
        )

    @router.get("/runs")
    def runs() -> dict:
        if _service is None:
            raise HTTPException(503, "首板因子区分扩展尚未初始化")
        return {"items": _service.list_runs()}

    @router.get("/runs/{run_id}/report")
    def saved_report(run_id: str) -> dict:
        if _service is None:
            raise HTTPException(503, "首板因子区分扩展尚未初始化")
        try:
            return _service.saved_report(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "保存的训练结果不存在") from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(500, "读取保存结果失败，请检查数据目录权限") from exc

    @router.get("/runs/{run_id}/events")
    def saved_events(
        run_id: str,
        page: int = Query(1, ge=1),
        page_size: int = Query(100, ge=1, le=200),
        rule_id: str | None = Query(None, max_length=64),
    ) -> dict:
        if _service is None:
            raise HTTPException(503, "首板因子区分扩展尚未初始化")
        try:
            return _service.saved_events(
                run_id, page=page, page_size=page_size, rule_id=rule_id,
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, "保存的训练结果不存在") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(500, "读取保存结果失败，请检查数据目录权限") from exc

    registrar.include_router(router)


def _call(method, start, end, snapshot_mode, horizon, strong_threshold, **kwargs) -> dict:
    if _service is None:
        raise HTTPException(503, "首板因子区分扩展尚未初始化")
    try:
        params = DiscoveryParams(start, end, horizon, strong_threshold, snapshot_mode)
        return getattr(_service, method)(params, **kwargs)
    except EnrichedGenerationUnavailableError as exc:
        raise HTTPException(409, "行情数据版本已变化，请等待更新完成后重新发现") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
