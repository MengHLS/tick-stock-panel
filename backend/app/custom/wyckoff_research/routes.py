"""HTTP 表面：只读事件查询，不写入任何状态。"""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.extensions import ExtensionRuntime, get_extension_runtime

from .service import MAX_WINDOW_BARS, ResearchInputError, load_events
from .spec import SpecError


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/custom/wyckoff-research", tags=["wyckoff-research"])

    @router.get("/events")
    def events(
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
        symbol: Annotated[str, Query(min_length=6, max_length=16, description="带市场后缀的代码")],
        as_of: Annotated[date | None, Query(description="截止交易日，默认最后一根已完成日线")] = None,
        window: Annotated[int, Query(ge=30, le=MAX_WINDOW_BARS, description="窗口交易日数")] = 120,
        rule_version: Annotated[str | None, Query(max_length=64, description="期望规则版本")] = None,
    ) -> dict:
        try:
            return load_events(
                runtime,
                symbol=symbol.upper(),
                window_bars=window,
                as_of=as_of,
                rule_version_expected=rule_version,
            )
        except ResearchInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SpecError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return router
