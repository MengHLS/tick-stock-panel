"""启动数据同步开关: 调度注册、扩展拉取、盘口补跑与时间接口保护。"""
from __future__ import annotations

from types import SimpleNamespace

from app.jobs import daily_pipeline
from app.services.depth_service import DepthService
from app.services.ext_pull import PullScheduler


def _patch_schedules(monkeypatch):
    from app.services import preferences

    monkeypatch.setattr(preferences, "get_pipeline_schedule", lambda: {"hour": 15, "minute": 35})
    monkeypatch.setattr(preferences, "get_instruments_schedule", lambda: {"hour": 9, "minute": 10})
    monkeypatch.setattr(preferences, "get_depth_finalize_time", lambda: {"hour": 15, "minute": 2})
    monkeypatch.setattr(
        preferences, "get_review_schedule",
        lambda: {"enabled": False, "hour": 16, "minute": 0},
    )
    monkeypatch.setattr(daily_pipeline.AsyncIOScheduler, "start", lambda self: None)


def test_data_jobs_are_not_registered_when_disabled(monkeypatch):
    _patch_schedules(monkeypatch)
    scheduler = daily_pipeline.start_scheduler(object(), object(), data_jobs_enabled=False)
    ids = {job.id for job in scheduler.get_jobs()}
    assert "pre_market_instruments" not in ids
    assert "daily_pipeline" not in ids
    assert "depth_finalize" not in ids
    assert "reprobe_capabilities" in ids


def test_data_jobs_are_registered_when_enabled(monkeypatch):
    _patch_schedules(monkeypatch)
    scheduler = daily_pipeline.start_scheduler(object(), object(), data_jobs_enabled=True)
    ids = {job.id for job in scheduler.get_jobs()}
    assert {"pre_market_instruments", "daily_pipeline", "depth_finalize"} <= ids
    assert "reprobe_capabilities" in ids


def test_pull_scheduler_refresh_is_noop_when_disabled(tmp_path):
    scheduler = PullScheduler()
    scheduler._enabled = False
    scheduler.refresh(tmp_path)
    assert scheduler._tasks == {}


def test_depth_boot_check_skips_network_when_disabled(monkeypatch):
    service = DepthService()
    monkeypatch.setattr(service, "_has_capability", lambda: True)
    monkeypatch.setattr(service, "_persisted_for_date", lambda _d: False)
    called: list[int] = []
    monkeypatch.setattr(service, "finalize", lambda: called.append(1))

    service.boot_check(allow_network=False)

    assert called == []


def test_depth_boot_check_restores_local_cache_without_network(monkeypatch):
    service = DepthService()
    monkeypatch.setattr(service, "_has_capability", lambda: True)
    monkeypatch.setattr(service, "_persisted_for_date", lambda _d: True)
    restored: list = []
    monkeypatch.setattr(service, "_restore_from_parquet", lambda d: restored.append(d))

    service.boot_check(allow_network=False)

    assert len(restored) == 1


def test_pipeline_schedule_update_tolerates_missing_job(monkeypatch):
    from app.api.settings import PipelineScheduleIn, update_pipeline_schedule
    from app.services import preferences

    monkeypatch.setattr(
        preferences, "set_pipeline_schedule",
        lambda hour, minute: {"hour": hour, "minute": minute},
    )

    class Scheduler:
        def get_job(self, _job_id):
            return None

        def reschedule_job(self, *_args, **_kwargs):
            raise AssertionError("job 未注册时不得调用 reschedule_job")

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(scheduler=Scheduler())),
    )
    assert update_pipeline_schedule(PipelineScheduleIn(hour=15, minute=40), request) == {
        "hour": 15,
        "minute": 40,
    }


def test_pipeline_schedule_update_reschedules_existing_job(monkeypatch):
    from app.api.settings import PipelineScheduleIn, update_pipeline_schedule
    from app.services import preferences

    monkeypatch.setattr(
        preferences, "set_pipeline_schedule",
        lambda hour, minute: {"hour": hour, "minute": minute},
    )
    calls: list[str] = []

    class Scheduler:
        def get_job(self, _job_id):
            return object()

        def reschedule_job(self, job_id, **_kwargs):
            calls.append(job_id)

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(scheduler=Scheduler())),
    )
    update_pipeline_schedule(PipelineScheduleIn(hour=15, minute=40), request)

    assert calls == ["daily_pipeline"]
