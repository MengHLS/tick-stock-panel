from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

import app.custom.limit_board_events as extension
from app.api.ext_data import _read_ext_dataframe
from app.custom.limit_board_events import service
from app.extensions import BACKEND_EXTENSION_API_VERSION, ExtensionContext
from app.factors.ext_factors import attach_ext_columns, numeric_timeseries_ext_columns
from app.market_time import CN_TZ
from app.plugins.fuyao.client import FuyaoError
from app.services.ext_data import ExtConfigStore

DAY = date(2026, 9, 1)
NOW = datetime(2026, 10, 30, 20, tzinfo=CN_TZ)


def _row(day: date = DAY, **extra):
    config = service.limit_board_config()
    row = dict.fromkeys(field.name for field in config.fields)
    row.update(
        {
            "trade_date": day.isoformat(),
            "symbol": "000001.SZ",
            "name": "test",
            "in_limit_up_pool": 1,
            "limit_up_pool_open_times": 2,
            "observed_open": 1,
            "limit_up_time": "09:34",
            "limit_up_minute": 574,
            "seal_money": 123.5,
        }
    )
    row.update(extra)
    return row


def test_sync_is_visible_in_existing_api_and_factor_join(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "fetch_limit_board_events", lambda *args: [_row()])

    report = service.sync_limit_board_events(tmp_path, DAY, client=object(), now=NOW)

    assert report["status"] == "written"
    assert report["rows"] == 1
    config = ExtConfigStore(tmp_path).get(service.CONFIG_ID)
    assert config is not None
    assert config.mode == "timeseries"
    assert config.pull is None
    frame, active = _read_ext_dataframe(config, tmp_path, DAY.isoformat())
    assert active == DAY.isoformat()
    assert frame["limit_up_pool_open_times"].to_list() == [2]
    assert frame["first_seal_minute"].to_list() == [None]

    column = f"ext_{service.CONFIG_ID}_limit_up_minute"
    assert column in numeric_timeseries_ext_columns(tmp_path)
    base = pl.DataFrame(
        {
            "symbol": ["000001.SZ"] * 3,
            "date": [date(2026, 8, 31), DAY, date(2026, 9, 2)],
        }
    )
    result = attach_ext_columns(base, data_dir=tmp_path, include_snapshot=False)
    assert result[column].to_list() == [None, 574.0, None]


def test_repeat_sync_skips_existing_day_and_keeps_bytes(tmp_path, monkeypatch):
    calls: list[date] = []

    def fetch(client, day):
        calls.append(day)
        return [_row(day)]

    monkeypatch.setattr(service, "fetch_limit_board_events", fetch)
    service.sync_limit_board_events(tmp_path, DAY, client=object(), now=NOW)
    path = tmp_path / "ext_data" / service.CONFIG_ID / "timeseries" / f"date={DAY}" / "part.parquet"
    original = path.read_bytes()

    report = service.sync_limit_board_events(tmp_path, DAY, client=object(), now=NOW)

    assert report["status"] == "exists"
    assert path.read_bytes() == original
    assert calls == [DAY]


def test_empty_and_failed_fetches_do_not_create_partitions(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "fetch_limit_board_events", lambda *args: [])
    assert (
        service.sync_limit_board_events(tmp_path, DAY, client=object(), now=NOW)["status"]
        == "empty"
    )
    assert not list(tmp_path.rglob("*.parquet"))

    def fail(*args):
        raise FuyaoError("permission denied")

    monkeypatch.setattr(service, "fetch_limit_board_events", fail)
    with pytest.raises(FuyaoError):
        service.sync_limit_board_events(tmp_path, DAY, client=object(), now=NOW)
    assert not list(tmp_path.rglob("*.parquet"))


@pytest.mark.parametrize(
    ("day", "now"),
    [
        (date(2026, 10, 31), NOW),
        (date(2026, 10, 30), datetime(2026, 10, 30, 15, 29, tzinfo=CN_TZ)),
    ],
)
def test_only_completed_days_can_be_written(tmp_path, day, now):
    with pytest.raises(ValueError, match="completed"):
        service.sync_limit_board_events(tmp_path, day, client=object(), now=now)
    assert not list(tmp_path.rglob("*.parquet"))


def test_existing_user_config_is_preserved_and_schema_conflict_is_rejected(tmp_path, monkeypatch):
    config = service.limit_board_config()
    config.label = "custom label"
    store = ExtConfigStore(tmp_path)
    store.upsert(config)
    path = tmp_path / "ext_data" / config.id / "config.json"
    before = path.read_bytes()
    monkeypatch.setattr(service, "fetch_limit_board_events", lambda *args: [_row()])

    service.sync_limit_board_events(tmp_path, DAY, client=object(), now=NOW)

    assert path.read_bytes() == before
    config.fields = config.fields[:1]
    store.upsert(config)
    with pytest.raises(ValueError, match="config"):
        service.sync_limit_board_events(tmp_path, date(2026, 9, 2), client=object(), now=NOW)


def test_builtin_config_is_seeded_once_and_never_resurrected(tmp_path):
    seeded = service.ensure_limit_board_config(tmp_path)

    assert seeded is not None
    assert seeded.id == service.CONFIG_ID
    marker = tmp_path / "ext_data" / ".limit_board_events_seeded"
    assert marker.exists()
    assert ExtConfigStore(tmp_path).delete(service.CONFIG_ID)

    assert service.ensure_limit_board_config(tmp_path) is None


def test_seeding_refuses_to_overwrite_an_unreadable_existing_config(tmp_path):
    path = tmp_path / "ext_data" / service.CONFIG_ID / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text("{bad", encoding="utf-8")

    with pytest.raises(ValueError, match="unreadable"):
        service.ensure_limit_board_config(tmp_path)


def test_auto_sync_never_resurrects_a_deleted_config(tmp_path, monkeypatch):
    service.ensure_limit_board_config(tmp_path)
    assert ExtConfigStore(tmp_path).delete(service.CONFIG_ID)
    monkeypatch.setattr(
        service,
        "fetch_limit_board_events",
        lambda *args: pytest.fail("deleted config must not reach the network"),
    )

    result = service.sync_limit_board_events(
        tmp_path,
        DAY,
        client=object(),
        now=NOW,
        create_config=False,
    )

    assert result["status"] == "missing_config"
    assert ExtConfigStore(tmp_path).get(service.CONFIG_ID) is None


def test_owned_client_is_closed_when_fetch_fails(tmp_path, monkeypatch):
    closed: list[int] = []

    class FakeClient:
        def close(self):
            closed.append(1)

    monkeypatch.setattr(service, "get_api_key", lambda: "test-key")
    monkeypatch.setattr(service, "FuyaoClient", lambda key: FakeClient())
    monkeypatch.setattr(
        service,
        "fetch_limit_board_events",
        lambda *args: (_ for _ in ()).throw(FuyaoError("failed")),
    )

    with pytest.raises(FuyaoError):
        service.sync_limit_board_events(tmp_path, DAY, now=NOW)

    assert closed == [1]


def test_minute_source_uses_local_adapter_without_creating_fuyao_client(tmp_path, monkeypatch):
    calls: list[tuple[Path, date, datetime | None]] = []

    def fetch(root, day, *, now=None):
        calls.append((root, day, now))
        return [_row(day)]

    monkeypatch.setattr(service, "fetch_minute_limit_board_events", fetch)
    monkeypatch.setattr(
        service,
        "FuyaoClient",
        lambda *args, **kwargs: pytest.fail("minute source must not create a Fuyao client"),
    )

    report = service.sync_limit_board_events(
        tmp_path,
        DAY,
        source="minute",
        now=NOW,
    )

    assert report["status"] == "written"
    assert report["source"] == "minute"
    assert calls == [(tmp_path, DAY, NOW)]


def test_missing_minute_partition_is_not_a_completed_empty_day(tmp_path, monkeypatch):
    monkeypatch.setattr(
        service,
        "fetch_minute_limit_board_events",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("missing")),
    )

    report = service.sync_limit_board_events(
        tmp_path,
        DAY,
        source="minute",
        now=NOW,
    )

    assert report == {
        "date": DAY.isoformat(),
        "status": "missing_source",
        "rows": 0,
        "source": "minute",
    }
    assert not list(tmp_path.rglob("*.parquet"))


def test_partition_created_during_fetch_is_not_overwritten(tmp_path, monkeypatch):
    original: list[bytes] = []

    def fetch(*args):
        config = service.limit_board_config()
        ExtConfigStore(tmp_path).upsert(config)
        frame = service.cast_df_to_schema(
            pl.DataFrame([_row(limit_up_pool_open_times=9)]),
            config.fields,
        )
        service.write_ext_parquet(frame, config, tmp_path, snapshot_date=DAY)
        original.append(next(tmp_path.rglob("part.parquet")).read_bytes())
        return [_row(limit_up_pool_open_times=2)]

    monkeypatch.setattr(service, "fetch_limit_board_events", fetch)

    report = service.sync_limit_board_events(tmp_path, DAY, client=object(), now=NOW)

    assert report["status"] == "exists"
    assert next(tmp_path.rglob("part.parquet")).read_bytes() == original[0]


def test_commit_lock_waits_for_other_process_and_releases_after_error(tmp_path):
    code = (
        "import sys\n"
        "from pathlib import Path\n"
        "from app.custom.limit_board_events.service import _commit_lock\n"
        "Path(sys.argv[2]).write_text('started', encoding='utf-8')\n"
        "try:\n"
        "    with _commit_lock(Path(sys.argv[1])): pass\n"
        "except Exception:\n"
        "    sys.exit(23)\n"
    )
    marker = tmp_path / "child-started"
    try:
        with service._commit_lock(tmp_path):
            child = subprocess.Popen(
                [sys.executable, "-c", code, str(tmp_path), str(marker)],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert marker.exists()
            time.sleep(0.2)
            assert child.returncode is None
            raise RuntimeError("test cleanup")
    except RuntimeError:
        pass

    stdout, stderr = child.communicate(timeout=20)
    assert child.returncode == 0, stderr or stdout
    with service._commit_lock(tmp_path):
        pass


def _parallel_sync_code() -> str:
    return """
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

from app.custom.limit_board_events import service
from app.market_time import CN_TZ

root = Path(sys.argv[1])
config = service.limit_board_config()
row = dict.fromkeys(field.name for field in config.fields)
row.update({
    "trade_date": "2026-09-01",
    "symbol": "000001.SZ",
    "name": "test",
    "in_limit_up_pool": 1,
    "observed_open": 1,
})
service.fetch_limit_board_events = lambda client, day: [row]
real_write = service.write_ext_parquet

def slow_write(*args, **kwargs):
    time.sleep(0.5)
    return real_write(*args, **kwargs)

service.write_ext_parquet = slow_write
result = service.sync_limit_board_events(
    root,
    date(2026, 9, 1),
    client=object(),
    now=datetime(2026, 10, 30, 20, 0, tzinfo=CN_TZ),
    create_config=True,
)
print(json.dumps(result))
"""


def test_two_processes_import_same_day_once(tmp_path):
    env = os.environ.copy()
    env.pop("DATA_DIR", None)
    env["PYTHONIOENCODING"] = "utf-8"
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", _parallel_sync_code(), str(tmp_path)],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    results = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, stderr or stdout
        results.append(json.loads(stdout.strip().splitlines()[-1]))

    assert sorted(result["status"] for result in results) == ["exists", "written"]
    partition = (
        tmp_path / "ext_data" / service.CONFIG_ID / "timeseries" / f"date={DAY}" / "part.parquet"
    )
    assert pl.read_parquet(partition).height == 1


def test_cancelled_fetch_cannot_commit_after_stop(tmp_path, monkeypatch):
    service.ensure_limit_board_config(tmp_path)
    started = threading.Event()
    release = threading.Event()
    cancel = threading.Event()
    outcome: list[Exception] = []

    def fetch(*args):
        started.set()
        assert release.wait(5)
        return [_row()]

    def run():
        try:
            service.sync_limit_board_events(
                tmp_path,
                DAY,
                client=object(),
                now=NOW,
                create_config=False,
                cancel_event=cancel,
            )
        except Exception as exc:  # noqa: BLE001 - captures the expected boundary
            outcome.append(exc)

    monkeypatch.setattr(service, "fetch_limit_board_events", fetch)
    thread = threading.Thread(target=run)
    thread.start()
    assert started.wait(5)
    cancel.set()
    release.set()
    thread.join(5)

    assert not thread.is_alive()
    assert len(outcome) == 1
    assert isinstance(outcome[0], service.SyncCancelledError)
    assert not list(tmp_path.rglob("*.parquet"))


@pytest.mark.asyncio
async def test_scheduler_generates_once_after_close_and_catches_up(tmp_path, monkeypatch):
    calls = []

    def sync(root, day, *, now=None, **kwargs):
        calls.append((root, day, now))
        return {"date": day.isoformat(), "status": "written", "rows": 80}

    monkeypatch.setattr(service, "sync_limit_board_events", sync)
    scheduler = service.LimitBoardEventScheduler()
    scheduler._data_dir = tmp_path
    scheduler._enabled = True

    early = datetime(2026, 10, 30, 15, 44, tzinfo=CN_TZ)
    assert (await scheduler.run_once(early))["status"] == "not_due"
    assert calls == []

    due = datetime(2026, 10, 30, 20, 0, tzinfo=CN_TZ)
    result = await scheduler.run_once(due)
    assert result["status"] == "written"
    assert calls == [(tmp_path, date(2026, 10, 30), due)]
    assert (await scheduler.run_once(due + timedelta(minutes=1)))["status"] == "done"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_scheduler_retries_failures_but_not_empty_completed_days(tmp_path, monkeypatch):
    outcomes = [
        FuyaoError("429"),
        {"date": "2026-10-30", "status": "empty", "rows": 0},
    ]
    calls: list[int] = []

    def sync(*args, **kwargs):
        calls.append(1)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(service, "sync_limit_board_events", sync)
    scheduler = service.LimitBoardEventScheduler()
    scheduler._data_dir = tmp_path
    scheduler._enabled = True
    now = datetime(2026, 10, 30, 20, 0, tzinfo=CN_TZ)

    assert (await scheduler.run_once(now))["status"] == "error"
    assert (await scheduler.run_once(now))["status"] == "empty"
    assert (await scheduler.run_once(now))["status"] == "done"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_empty_completion_marker_survives_scheduler_restart(tmp_path, monkeypatch):
    calls: list[int] = []

    def sync(*args, **kwargs):
        calls.append(1)
        return {"date": "2026-10-30", "status": "empty", "rows": 0}

    monkeypatch.setattr(service, "sync_limit_board_events", sync)
    now = datetime(2026, 10, 30, 20, 0, tzinfo=CN_TZ)
    first = service.LimitBoardEventScheduler()
    first._data_dir = tmp_path
    first._enabled = True
    assert (await first.run_once(now))["status"] == "empty"

    restarted = service.LimitBoardEventScheduler()
    restarted._data_dir = tmp_path
    restarted._enabled = True
    assert (await restarted.run_once(now))["status"] == "done"
    assert calls == [1]


@pytest.mark.asyncio
async def test_scheduler_clears_repository_cache_after_write(tmp_path, monkeypatch):
    cleared: list[int] = []

    class Repository:
        def clear_cache(self):
            cleared.append(1)

    monkeypatch.setattr(
        service,
        "sync_limit_board_events",
        lambda *args, **kwargs: {
            "date": "2026-10-30",
            "status": "written",
            "rows": 80,
        },
    )
    scheduler = service.LimitBoardEventScheduler()
    scheduler._data_dir = tmp_path
    scheduler._enabled = True
    scheduler._repository = Repository()

    await scheduler.run_once(datetime(2026, 10, 30, 20, 0, tzinfo=CN_TZ))

    assert cleared == [1]


@pytest.mark.asyncio
async def test_scheduler_skips_weekends_and_disabled_mode(tmp_path, monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(
        service,
        "sync_limit_board_events",
        lambda *args, **kwargs: calls.append(1),
    )
    scheduler = service.LimitBoardEventScheduler()
    scheduler._data_dir = tmp_path
    scheduler._enabled = True

    weekend = datetime(2026, 10, 31, 20, 0, tzinfo=CN_TZ)
    assert (await scheduler.run_once(weekend))["status"] == "not_due"
    scheduler._enabled = False
    weekday = datetime(2026, 10, 30, 20, 0, tzinfo=CN_TZ)
    assert (await scheduler.run_once(weekday))["status"] == "disabled"
    assert calls == []


@pytest.mark.asyncio
async def test_scheduler_start_and_stop_manage_background_task(tmp_path, monkeypatch):
    blocker = asyncio.Event()

    async def wait_forever(_self):
        await blocker.wait()

    monkeypatch.setattr(service.LimitBoardEventScheduler, "_run_loop", wait_forever)
    scheduler = service.LimitBoardEventScheduler()
    scheduler.start(tmp_path, enabled=True)
    assert scheduler._task is not None
    await asyncio.sleep(0)
    scheduler.stop()
    assert scheduler._task is None
    scheduler.start(tmp_path, enabled=False)
    assert scheduler._task is None


@pytest.mark.asyncio
async def test_scheduler_restart_does_not_clear_old_cancel_signal(tmp_path, monkeypatch):
    blocker = asyncio.Event()

    async def wait_forever(_self):
        await blocker.wait()

    monkeypatch.setattr(service.LimitBoardEventScheduler, "_run_loop", wait_forever)
    scheduler = service.LimitBoardEventScheduler()
    scheduler.start(tmp_path, enabled=True)
    old_event = scheduler._cancel_event
    await asyncio.sleep(0)

    scheduler.start(tmp_path, enabled=True)

    assert old_event.is_set()
    assert scheduler._cancel_event is not old_event
    scheduler.stop()


@pytest.mark.asyncio
async def test_loop_cancellation_blocks_late_commit(monkeypatch):
    blocker = asyncio.Event()

    async def wait_forever(_self):
        await blocker.wait()

    monkeypatch.setattr(service.LimitBoardEventScheduler, "run_once", wait_forever)
    scheduler = service.LimitBoardEventScheduler()
    scheduler._running = True
    task = asyncio.create_task(scheduler._run_loop())
    await asyncio.sleep(0)

    task.cancel()
    await task

    assert scheduler._cancel_event.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_extension_startup_seeds_config_and_starts_scheduler(tmp_path, monkeypatch, enabled):
    calls: list[tuple] = []
    repository = object()
    monkeypatch.setattr(
        service,
        "ensure_limit_board_config",
        lambda root: calls.append(("seed", root)),
    )
    monkeypatch.setattr(
        service.limit_board_scheduler,
        "start",
        lambda root, *, enabled, repository: calls.append(("start", root, enabled, repository)),
    )
    monkeypatch.setattr(
        extension.preferences,
        "get_data_sync_prefs",
        lambda: {"data_sync_ext_pull_enabled": enabled},
    )

    extension.startup(
        ExtensionContext(
            api_version=BACKEND_EXTENSION_API_VERSION,
            data_dir=tmp_path,
            repository=repository,
        )
    )

    assert calls == [
        ("seed", tmp_path),
        ("start", tmp_path, enabled, repository),
    ]


def test_cli_uses_target_directory_for_credentials_and_stops_on_failure(
    tmp_path, monkeypatch, capsys
):
    from scripts import sync_limit_board_events as script

    monkeypatch.setattr(script.settings, "data_dir", tmp_path / "default")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sync",
            "--data-dir",
            str(tmp_path / "target"),
            "--start",
            "2026-09-01",
            "--end",
            "2026-09-03",
            "--source",
            "fuyao",
        ],
    )
    calls: list[date] = []

    def sync(root, day, **kwargs):
        assert script.settings.data_dir == root == tmp_path / "target"
        assert kwargs["create_config"] is False
        calls.append(day)
        if day == date(2026, 9, 2):
            raise FuyaoError("HTTP 429")
        return {"date": day.isoformat(), "status": "written", "rows": 1}

    monkeypatch.setattr(script, "sync_limit_board_events", sync)

    assert script.main() == 1
    assert calls == [DAY, date(2026, 9, 2)]
    assert '"status": "error"' in capsys.readouterr().out


def test_cli_does_not_resurrect_deleted_config(tmp_path, monkeypatch, capsys):
    from scripts import sync_limit_board_events as script

    service.ensure_limit_board_config(tmp_path)
    store = ExtConfigStore(tmp_path)
    assert store.delete(service.CONFIG_ID)
    monkeypatch.setattr(
        service,
        "fetch_limit_board_events",
        lambda *args: pytest.fail("deleted config must not reach the network"),
    )
    monkeypatch.setattr(script.settings, "data_dir", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sync",
            "--data-dir",
            str(tmp_path),
            "--start",
            DAY.isoformat(),
            "--source",
            "fuyao",
        ],
    )

    assert script.main() == 0
    assert store.get(service.CONFIG_ID) is None
    assert '"status": "missing_config"' in capsys.readouterr().out


def test_cli_minute_source_walks_local_partitions_newest_first(tmp_path, monkeypatch, capsys):
    from scripts import sync_limit_board_events as script

    dates = [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)]
    captured: list[date] = []
    range_args: list[tuple[Path, date, date]] = []

    def list_partitions(root, start, end):
        range_args.append((root, start, end))
        return dates

    def sync(root, day, **kwargs):
        assert kwargs["create_config"] is False
        assert kwargs["source"] == "minute"
        captured.append(day)
        return {"date": day.isoformat(), "status": "written", "rows": 1, "source": "minute"}

    monkeypatch.setattr(script, "list_minute_partitions", list_partitions)
    monkeypatch.setattr(script, "sync_limit_board_events", sync)
    monkeypatch.setattr(script.settings, "data_dir", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sync",
            "--data-dir",
            str(tmp_path),
            "--end",
            "2026-09-03",
        ],
    )

    assert script.main() == 0
    assert range_args == [(tmp_path, date(2019, 1, 1), date(2026, 9, 3))]
    assert captured == list(reversed(dates))
    output = capsys.readouterr().out
    assert output.count('"status": "written"') == 3


def test_cli_minute_default_end_skips_unfinished_current_day(tmp_path, monkeypatch, capsys):
    from scripts import sync_limit_board_events as script

    for day in (date(2026, 9, 2), date(2026, 9, 3)):
        path = tmp_path / "kline_minute" / f"date={day}" / "part.parquet"
        path.parent.mkdir(parents=True)
        path.touch()
    captured: list[date] = []

    def sync(root, day, **kwargs):
        captured.append(day)
        return {"date": day.isoformat(), "status": "written", "rows": 1, "source": "minute"}

    monkeypatch.setattr(
        script,
        "cn_now",
        lambda: datetime(2026, 9, 3, 10, 0, tzinfo=CN_TZ),
    )
    monkeypatch.setattr(script, "sync_limit_board_events", sync)
    monkeypatch.setattr(script.settings, "data_dir", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["sync", "--data-dir", str(tmp_path), "--source", "minute"],
    )

    assert script.main() == 0
    assert captured == [date(2026, 9, 2)]
    assert '"status": "written"' in capsys.readouterr().out
