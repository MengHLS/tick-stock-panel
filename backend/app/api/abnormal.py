"""异动监控 API — 竞价/盘中/偏移三类异动。

- /intraday: 盘中量价信号聚合 (enriched 当日信号列, 零新增采集)
- /overview: 偏移异动边缘总览 (交易所异动规则口径的接近度)
- /suppression: 异动阈值反解的收盘价压制位 (今日/后续交易日)
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request

from app.services.abnormal_moves import (
    build_intraday,
    build_overview,
    build_suppression_schedule,
)

router = APIRouter(prefix="/api/abnormal", tags=["abnormal"])


@router.get("/intraday")
def abnormal_intraday(
    request: Request,
    limit: int = Query(500, ge=1, le=2000),
):
    """盘中异动: 涨停/炸板/跌停翘板/跌停/新高/新低/放量 信号命中行。"""
    repo = request.app.state.repo
    return build_intraday(repo, limit=limit)


@router.get("/overview")
def abnormal_overview(
    request: Request,
    min_closeness: float = Query(0.5, ge=0.0, le=1.0),
    limit: int = Query(200, ge=1, le=1000),
    window: Literal["3d", "10d", "30d"] | None = Query(None),
    direction: Literal["both", "up", "down"] = Query("both"),
    board: Literal["主板", "创业板", "科创板", "北交所"] | None = Query(None),
    boards: list[Literal["主板", "创业板", "科创板", "北交所"]] | None = Query(None),
    exclude_st: bool = Query(False),
    watchlist_only: bool = Query(False),
    q: str | None = Query(None, max_length=64),
):
    """异动边缘总览: 规则表 + 各窗口实时偏离 + 接近度排序。

    min_closeness: 0.5=观察 / 0.7=边缘 / 1.0=已触发。
    其余筛选在服务端先执行, 再按 limit 截断 —— 前端本地过滤不能只作用于
    接近度最高的前 N 行, 否则板块/窗口筛选会因截断而显示空列表。
    """
    repo = request.app.state.repo
    quote_service = getattr(request.app.state, "quote_service", None)
    symbols = None
    if watchlist_only:
        from app.services import watchlist
        symbols = {str(r.get("symbol")) for r in watchlist.list_symbols() if r.get("symbol")}
    return build_overview(
        repo,
        quote_service,
        min_closeness=min_closeness,
        limit=limit,
        window=window,
        direction=direction,
        board=board,
        boards=set(boards or []),
        exclude_st=exclude_st,
        symbols=symbols,
        query=q,
    )


@router.get("/suppression")
def abnormal_suppression(
    request: Request,
    symbol: str = Query(..., min_length=6, max_length=16),
    forward_days: int = Query(5, ge=0, le=10),
    window: Literal["3d", "10d", "30d"] | None = Query(None),
):
    """异动阈值价格压制: 指定窗口今日/后续交易日的收盘价上限与剩余空间。

    偏移异动的阈值本质上是价格上限; 把阈值反解成收盘价, 并随 N 日窗口
    逐日滚动, 供个股详情弹窗展示「后续上涨空间」。
    """
    repo = request.app.state.repo
    return build_suppression_schedule(
        repo,
        symbol=symbol,
        forward_days=forward_days,
        window=window,
    )
