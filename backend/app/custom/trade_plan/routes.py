"""交易计划 API：计划 CRUD、执行统计与 AI 复盘。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.services.ndjson_heartbeat import with_heartbeat

from . import ai, store
from .metrics import summarize, with_metrics
from .models import AnalyzeRequest, PlanInput, ReportInput


def _data_dir(request: Request) -> Path:
    return request.app.state.repo.store.data_dir


def _rows_and_stats(
    data_dir: Path,
    *,
    start: str | None = None,
    end: str | None = None,
    setup: str | None = None,
    status: str | None = None,
    query: str | None = None,
) -> tuple[list[dict], dict]:
    plans = store.list_plans(
        data_dir,
        start=start,
        end=end,
        setup=setup,
        status=status,
        query=query,
    )
    rows = [with_metrics(plan) for plan in plans]
    return rows, summarize(plans)


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/custom/trade-plan", tags=["custom-trade-plan"])

    @router.get("/plans")
    def list_plans(
        request: Request,
        start: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
        end: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
        setup: str | None = None,
        status: str | None = None,
        q: str | None = Query(default=None, max_length=80),
    ):
        rows, stats = _rows_and_stats(
            _data_dir(request), start=start, end=end, setup=setup, status=status, query=q
        )
        return {"plans": rows, "stats": stats}

    @router.post("/plans")
    def create_plan(request: Request, body: PlanInput):
        plan = body.model_dump(mode="json")
        saved = store.save_plan(_data_dir(request), plan)
        return {"plan": with_metrics(saved)}

    @router.put("/plans/{plan_id}")
    def update_plan(request: Request, plan_id: str, body: PlanInput):
        plan = body.model_dump(mode="json")
        try:
            saved = store.save_plan(_data_dir(request), plan, plan_id=plan_id)
        except KeyError as exc:
            raise HTTPException(404, "计划不存在") from exc
        return {"plan": with_metrics(saved)}

    @router.delete("/plans/{plan_id}")
    def delete_plan(request: Request, plan_id: str):
        if not store.delete_plan(_data_dir(request), plan_id):
            raise HTTPException(404, "计划不存在")
        return {"ok": True}

    @router.post("/analyze")
    async def analyze(request: Request, body: AnalyzeRequest):
        data_dir = _data_dir(request)
        plans = store.list_plans(
            data_dir,
            start=body.start.isoformat() if body.start else None,
            end=body.end.isoformat() if body.end else None,
        )
        if not plans:
            raise HTTPException(400, "所选区间暂无交易计划")
        # 最近 N 条：list_plans 已按计划日倒序，取前 N 后恢复时间顺序供模型阅读。
        rows = [with_metrics(plan) for plan in plans[: body.limit]]
        rows.reverse()
        stats = summarize(plans[: body.limit])

        async def stream_gen():
            async for chunk in with_heartbeat(ai.analyze_plans_stream(rows, stats, body.focus)):
                yield chunk + "\n"

        return StreamingResponse(
            stream_gen(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/reports")
    def list_reports(request: Request):
        return {"reports": store.list_reports(_data_dir(request))}

    @router.post("/reports")
    def save_report(request: Request, body: ReportInput):
        report = store.save_report(
            _data_dir(request),
            {
                "start": body.start,
                "end": body.end,
                "focus": body.focus,
                "content": body.content,
                "summary": body.summary,
                "stats": body.stats,
            },
        )
        return {"ok": True, "report": report}

    @router.delete("/reports/{report_id}")
    def delete_report(request: Request, report_id: str):
        if not store.delete_report(_data_dir(request), report_id):
            raise HTTPException(404, "报告不存在")
        return {"ok": True}

    return router
