"""HTTP surface for the T74 strategy research extension."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.extensions import ExtensionRuntime, get_extension_runtime

from .baseline import load_baseline
from .experiments import create_experiment, get_experiment
from .records import (
    create_factor,
    get_factor,
    get_factors,
    update_factor,
    validate_factor_key,
)
from .service import (
    create_path_report,
    filter_report_events,
    get_inbox,
    get_report,
    get_reports,
    report_summary,
)
from .store import (
    ResearchStoreError,
    list_experiments,
)


class BaselineSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["saved", "file"]
    saved_id: str | None = Field(default=None, max_length=80)
    file_name: str | None = Field(default=None, max_length=240)
    label: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_source(self):
        if self.kind == "saved" and not self.saved_id:
            raise ValueError("saved 来源需要 saved_id")
        if self.kind == "file" and not self.file_name:
            raise ValueError("file 来源需要 file_name")
        if self.kind == "saved" and self.file_name:
            raise ValueError("saved 来源不能同时指定 file_name")
        if self.kind == "file" and self.saved_id:
            raise ValueError("file 来源不能同时指定 saved_id")
        return self


class PathReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: BaselineSource
    horizon_sessions: int = Field(default=20, ge=1, le=250)
    thresholds: list[float] = Field(
        default_factory=lambda: [0.20, 0.30, 0.50],
        min_length=1,
        max_length=8,
    )
    label: str | None = Field(default=None, max_length=120)
    entry_price_basis: Literal["auto", "raw", "adjusted"] = "auto"

    @model_validator(mode="after")
    def validate_thresholds(self):
        if len(set(self.thresholds)) != len(self.thresholds):
            raise ValueError("thresholds 不能重复")
        if any(not 0 < value <= 10 for value in self.thresholds):
            raise ValueError("thresholds 必须在 (0, 10] 内")
        return self


class ExperimentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    hypothesis: str = Field(min_length=1, max_length=2000)
    changed_decision: Literal[
        "entry_filter",
        "candidate_rank",
        "hold_exit",
        "position",
    ]
    control_report_id: str = Field(min_length=1, max_length=40)
    variant_report_id: str = Field(min_length=1, max_length=40)
    factor_id: str | None = Field(default=None, max_length=40)
    conclusion: Literal["pending", "adopt", "reject", "inconclusive"] = "pending"
    notes: str | None = Field(default=None, max_length=4000)


class FactorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factor_key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    version: str | None = Field(default=None, max_length=80)
    purpose: Literal["entry_filter", "candidate_rank", "hold_exit", "position"]
    earliest_known_at: str = Field(min_length=1, max_length=200)
    direction: str = Field(min_length=1, max_length=300)
    missing_policy: str = Field(min_length=1, max_length=300)
    hypothesis: str = Field(min_length=1, max_length=2000)
    status: Literal[
        "proposed",
        "testing",
        "adopted",
        "rejected",
        "inconclusive",
    ] = "proposed"
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_key(self):
        validate_factor_key(self.factor_key)
        return self


class FactorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal[
        "proposed",
        "testing",
        "adopted",
        "rejected",
        "inconclusive",
    ] | None = None
    notes: str | None = Field(default=None, max_length=4000)
    evidence: str | None = Field(default=None, max_length=8000)


def build_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/custom/strategy-research",
        tags=["custom-strategy-research"],
    )

    def call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ResearchStoreError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ValueError, OSError, KeyError) as exc:
            raise HTTPException(409, "研究数据无法读取或保存，请检查输入与数据目录") from exc

    @router.get("/inbox")
    def inbox(
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict:
        return {"items": call(get_inbox, runtime.data_dir)}

    @router.get("/reports")
    def reports(
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
        limit: int = Query(50, ge=1, le=200),
    ) -> dict:
        return {"items": call(get_reports, runtime.data_dir, limit=limit)}

    @router.post("/reports")
    def create_report(
        payload: PathReportRequest,
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict:
        baseline = call(
            load_baseline,
            data_dir=runtime.data_dir,
            source_kind=payload.source.kind,
            saved_id=payload.source.saved_id,
            file_name=payload.source.file_name,
            label=payload.source.label,
            backtest_results=runtime.backtest_results,
        )
        report = call(
            create_path_report,
            data_dir=runtime.data_dir,
            market_data=runtime.market_data,
            baseline=baseline,
            horizon_sessions=payload.horizon_sessions,
            thresholds=payload.thresholds,
            label=payload.label,
            entry_price_basis=payload.entry_price_basis,
        )
        return {"report": report_summary(report)}

    @router.get("/reports/{report_id}")
    def report(
        report_id: str,
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict:
        return {"report": report_summary(call(get_report, runtime.data_dir, report_id))}

    @router.get("/reports/{report_id}/events")
    def report_events(
        report_id: str,
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
        threshold: float | None = Query(None),
        outcome: Literal[
            "all",
            "hit",
            "miss",
            "stop_before_hit",
            "hit_before_stop",
            "no_hit_stop",
            "same_day_ambiguous",
        ] = "all",
        q: str | None = Query(None, max_length=80),
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
    ) -> dict:
        report_data = call(get_report, runtime.data_dir, report_id)
        return call(
            filter_report_events,
            report_data,
            threshold=threshold,
            outcome=outcome,
            query=q,
            page=page,
            page_size=page_size,
        )

    @router.get("/experiments")
    def experiments(
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
        limit: int = Query(100, ge=1, le=500),
    ) -> dict:
        return {"items": call(list_experiments, runtime.data_dir, limit=limit)}

    @router.post("/experiments")
    def create_experiment_record(
        payload: ExperimentCreate,
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict:
        return {
            "experiment": call(
                create_experiment,
                runtime.data_dir,
                name=payload.name,
                hypothesis=payload.hypothesis,
                changed_decision=payload.changed_decision,
                control_report_id=payload.control_report_id,
                variant_report_id=payload.variant_report_id,
                factor_id=payload.factor_id,
                conclusion=payload.conclusion,
                notes=payload.notes,
            )
        }

    @router.get("/experiments/{experiment_id}")
    def experiment(
        experiment_id: str,
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict:
        return {"experiment": call(get_experiment, runtime.data_dir, experiment_id)}

    @router.get("/factors")
    def factors(
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
        limit: int = Query(200, ge=1, le=1000),
    ) -> dict:
        return {"items": call(get_factors, runtime.data_dir, limit=limit)}

    @router.post("/factors")
    def create_factor_record(
        payload: FactorCreate,
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict:
        return {
            "factor": call(
                create_factor,
                runtime.data_dir,
                factor_key=payload.factor_key,
                name=payload.name,
                version=payload.version,
                purpose=payload.purpose,
                earliest_known_at=payload.earliest_known_at,
                direction=payload.direction,
                missing_policy=payload.missing_policy,
                hypothesis=payload.hypothesis,
                status=payload.status,
                notes=payload.notes,
            )
        }

    @router.get("/factors/{factor_id}")
    def factor(
        factor_id: str,
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict:
        return {"factor": call(get_factor, runtime.data_dir, factor_id)}

    @router.put("/factors/{factor_id}")
    def update_factor_record(
        factor_id: str,
        payload: FactorUpdate,
        runtime: Annotated[ExtensionRuntime, Depends(get_extension_runtime)],
    ) -> dict:
        return {
            "factor": call(
                update_factor,
                runtime.data_dir,
                factor_id,
                status=payload.status,
                notes=payload.notes,
                evidence=payload.evidence,
            )
        }

    return router
