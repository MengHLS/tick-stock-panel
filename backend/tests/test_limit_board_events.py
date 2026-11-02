from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

import polars as pl
import pytest

import app.custom.limit_board_events as extension
from app.api.ext_data import _read_ext_dataframe
from app.custom.limit_board_events import service
from app.extensions import (
    BACKEND_EXTENSION_API_VERSION,
    BackendExtensionRegistrar,
    ExtensionContext,
)
from app.factors.ext_factors import attach_ext_columns, numeric_timeseries_ext_columns
from app.market_time import CN_TZ
from app.plugins.fuyao.client import FuyaoError
from app.services import ext_pull
from app.services.ext_data import ExtConfigStore, PullConfig

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
    assert config.pull is not None
    assert config.pull.url == service.LIMIT_BOARD_URL
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


def test_existing_config_is_migrated_to_shared_pull_scheduler(tmp_path):
    config = service.limit_board_config()
    config.pull = None
    ExtConfigStore(tmp_path).upsert(config)

    migrated = service.ensure_limit_board_config(tmp_path)

    assert migrated is not None
    assert migrated.pull is not None
    assert migrated.pull.url == service.LIMIT_BOARD_URL
    assert migrated.pull.time_window_start == "15:45"
    assert migrated.pull.time_window_end == "23:59"
    assert migrated.pull.schedule_trading_only is True


def test_existing_owned_pull_preserves_runtime_status(tmp_path):
    config = service.limit_board_config()
    assert config.pull is not None
    config.pull.last_run = "2026-10-30T07:45:00+00:00"
    config.pull.last_status = "success"
    config.pull.last_message = "1 rows @ 2026-10-30"
    config.pull.last_rows = 1
    config.pull.schedule_minutes = 17
    config.pull.time_window_start = "16:00"
    ExtConfigStore(tmp_path).upsert(config)

    migrated = service.ensure_limit_board_config(tmp_path)

    assert migrated is not None
    assert migrated.pull is not None
    assert migrated.pull.last_run == "2026-10-30T07:45:00+00:00"
    assert migrated.pull.last_status == "success"
    assert migrated.pull.last_message == "1 rows @ 2026-10-30"
    assert migrated.pull.last_rows == 1
    assert migrated.pull.schedule_minutes == 17
    assert migrated.pull.time_window_start == "16:00"


def test_user_custom_pull_is_not_overwritten(tmp_path):
    config = service.limit_board_config()
    config.pull = PullConfig(url="https://example.test/limit-board", enabled=False)
    ExtConfigStore(tmp_path).upsert(config)

    existing = service.ensure_limit_board_config(tmp_path)

    assert existing is not None
    assert existing.pull is not None
    assert existing.pull.url == "https://example.test/limit-board"
    with pytest.raises(ValueError, match="config"):
        service.sync_limit_board_events(tmp_path, DAY, client=object(), now=NOW)


@pytest.mark.asyncio
async def test_scheduled_handler_marks_written_day_and_skips_repeat(tmp_path, monkeypatch):
    calls: list[tuple] = []
    due = datetime(2026, 10, 30, 20, 0, tzinfo=CN_TZ)

    def sync(root, day, **kwargs):
        calls.append((root, day, kwargs))
        return {"date": day.isoformat(), "status": "written", "rows": 80}

    monkeypatch.setattr(service, "cn_now", lambda: due)
    monkeypatch.setattr(service, "sync_limit_board_events", sync)
    config = service.limit_board_config()

    assert await service.run_scheduled_limit_board(config, tmp_path, due.date()) == (
        80,
        due.date().isoformat(),
    )
    assert calls == [
        (
            tmp_path,
            due.date(),
            {"now": due, "create_config": False},
        )
    ]
    marker = service._completion_marker(tmp_path, due.date())
    assert marker.read_text(encoding="utf-8") == "written"

    assert await service.run_scheduled_limit_board(config, tmp_path, due.date()) == (
        0,
        due.date().isoformat(),
    )
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_rows"),
    [("exists", 12), ("empty", 0)],
)
async def test_scheduled_handler_treats_existing_and_empty_as_complete(
    tmp_path, monkeypatch, status, expected_rows
):
    monkeypatch.setattr(
        service,
        "sync_limit_board_events",
        lambda *args, **kwargs: {
            "date": DAY.isoformat(),
            "status": status,
            "rows": expected_rows,
        },
    )

    result = await service.run_scheduled_limit_board(
        service.limit_board_config(),
        tmp_path,
        DAY,
    )

    assert result == (expected_rows, DAY.isoformat())
    assert service._completion_marker(tmp_path, DAY).read_text(encoding="utf-8") == status


@pytest.mark.asyncio
async def test_scheduled_handler_does_not_mark_failed_or_missing_config(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        service,
        "sync_limit_board_events",
        lambda *args, **kwargs: {"status": "missing_config", "rows": 0},
    )
    assert await service.run_scheduled_limit_board(
        service.limit_board_config(),
        tmp_path,
        DAY,
    ) == (0, DAY.isoformat())
    assert not service._completion_marker(tmp_path, DAY).exists()

    def fail(*args, **kwargs):
        raise FuyaoError("429")

    monkeypatch.setattr(service, "sync_limit_board_events", fail)
    with pytest.raises(FuyaoError):
        await service.run_scheduled_limit_board(
            service.limit_board_config(),
            tmp_path,
            DAY,
        )
    assert not service._completion_marker(tmp_path, DAY).exists()


@pytest.mark.asyncio
async def test_builtin_dispatch_uses_limit_board_handler(tmp_path, monkeypatch):
    called: list[tuple] = []

    async def fake_handler(config, data_dir, target_date):
        called.append((config.id, data_dir, target_date))
        return 3, target_date.isoformat()

    monkeypatch.setitem(ext_pull._pull_handlers, service.CONFIG_ID, fake_handler)

    assert await ext_pull.fetch_and_ingest(
        service.limit_board_config(),
        tmp_path,
        DAY,
    ) == (3, DAY.isoformat())
    assert called == [(service.CONFIG_ID, tmp_path, DAY)]


def test_extension_setup_registers_shared_pull_handler():
    extension.setup(
        BackendExtensionRegistrar(
            extension.EXTENSION_ID,
            api_version=extension.EXTENSION_API_VERSION,
        )
    )

    assert ext_pull.has_pull_handler(service.CONFIG_ID)


def test_extension_startup_seeds_config_and_refreshes_shared_scheduler(
    tmp_path, monkeypatch
):
    calls: list[tuple] = []
    repository = object()
    monkeypatch.setattr(
        extension.service,
        "ensure_limit_board_config",
        lambda root: calls.append(("seed", root)),
    )
    monkeypatch.setattr(
        extension.pull_scheduler,
        "refresh",
        lambda root: calls.append(("refresh", root)),
    )

    extension.startup(
        ExtensionContext(
            api_version=BACKEND_EXTENSION_API_VERSION,
            data_dir=tmp_path,
            repository=repository,
        )
    )

    assert calls == [("seed", tmp_path), ("refresh", tmp_path)]


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
