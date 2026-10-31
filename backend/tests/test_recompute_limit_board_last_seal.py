"""Regression tests for the targeted last-seal historical recompute."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from app.custom.limit_board_events import service
from app.services.ext_data import ExtConfigStore
from scripts import recompute_limit_board_last_seal as script

DAY = date(2026, 9, 1)
FUYAO_DAY = date(2026, 9, 2)


def _partition(data_dir: Path, day: date) -> Path:
    return (
        data_dir / "ext_data" / service.CONFIG_ID / "timeseries"
        / f"date={day}" / "part.parquet"
    )


def _write_partition(
    data_dir: Path,
    day: date,
    *,
    symbol: str = "000001.SZ",
    fuyao: bool = False,
) -> Path:
    service.ensure_limit_board_config(data_dir)
    config = ExtConfigStore(data_dir).get(service.CONFIG_ID)
    assert config is not None
    row = dict.fromkeys(field.name for field in config.fields)
    row.update({
        "trade_date": day.isoformat(),
        "symbol": symbol,
        "in_limit_up_pool": 1,
        "observed_open": 0,
        "limit_up_time": "09:45",
        "limit_up_minute": 585,
        "first_seal_time": "09:45",
        "first_seal_minute": 585,
        "last_seal_time": "15:00",
        "last_seal_minute": 900,
        "limit_up_pool_open_times": 0,
        "turnover": 123.0,
        "retrieved_at": "2026-09-01T20:00:00+08:00",
    })
    if fuyao:
        row["up_source_ready_at"] = "2026-09-01T15:45:00+08:00"
        row["last_seal_time"] = "10:15"
        row["last_seal_minute"] = 615
    path = _partition(data_dir, day)
    path.parent.mkdir(parents=True)
    pl.DataFrame([row], infer_schema_length=None).write_parquet(path)
    return path


def _fresh_row(day: date, *, symbol: str = "000001.SZ") -> dict:
    config = service.limit_board_config()
    row = dict.fromkeys(field.name for field in config.fields)
    row.update({
        "trade_date": day.isoformat(),
        "symbol": symbol,
        "in_limit_up_pool": 1,
        "observed_open": 0,
        "limit_up_time": "09:45",
        "limit_up_minute": 585,
        "first_seal_time": "09:45",
        "first_seal_minute": 585,
        "last_seal_time": "09:45",
        "last_seal_minute": 585,
        "limit_up_pool_open_times": 0,
        "turnover": 999.0,
        "retrieved_at": "2026-10-31T12:00:00+08:00",
    })
    return row


def test_recompute_updates_only_last_seal_on_minute_partition(
    tmp_path, monkeypatch,
) -> None:
    path = _write_partition(tmp_path, DAY)
    calls: list[date] = []

    def fetch(root, day, *, now=None):
        calls.append(day)
        return [_fresh_row(day)]

    monkeypatch.setattr(script, "fetch_minute_limit_board_events", fetch)

    results = script.recompute_range(tmp_path, [DAY], workers=1)
    frame = pl.read_parquet(path)

    assert results[0]["status"] == "updated"
    assert results[0]["rows_changed"] == 1
    assert calls == [DAY]
    assert frame["last_seal_time"].to_list() == ["09:45"]
    assert frame["last_seal_minute"].to_list() == [585]
    assert frame["first_seal_minute"].to_list() == [585]
    assert frame["turnover"].to_list() == [123.0]
    assert frame["retrieved_at"].to_list() == ["2026-09-01T20:00:00+08:00"]


def test_recompute_skips_fuyao_partition_without_reading_minutes(
    tmp_path, monkeypatch,
) -> None:
    path = _write_partition(tmp_path, FUYAO_DAY, fuyao=True)
    original = path.read_bytes()
    monkeypatch.setattr(
        script,
        "fetch_minute_limit_board_events",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Fuyao partition must not be recomputed from minutes")
        ),
    )

    results = script.recompute_range(tmp_path, [FUYAO_DAY], workers=1)

    assert results[0]["status"] == "skipped_fuyao"
    assert path.read_bytes() == original


def test_recompute_dry_run_does_not_write(tmp_path, monkeypatch) -> None:
    path = _write_partition(tmp_path, DAY)
    original = path.read_bytes()
    monkeypatch.setattr(
        script,
        "fetch_minute_limit_board_events",
        lambda root, day, *, now=None: [_fresh_row(day)],
    )

    results = script.recompute_range(tmp_path, [DAY], workers=1, dry_run=True)

    assert results[0]["status"] == "would_update"
    assert results[0]["rows_changed"] == 1
    assert path.read_bytes() == original


def test_recompute_refuses_event_membership_change(tmp_path, monkeypatch) -> None:
    path = _write_partition(tmp_path, DAY)
    original = path.read_bytes()
    monkeypatch.setattr(
        script,
        "fetch_minute_limit_board_events",
        lambda root, day, *, now=None: [_fresh_row(day, symbol="000002.SZ")],
    )

    results = script.recompute_range(tmp_path, [DAY], workers=1)

    assert results[0]["status"] == "error"
    assert "event membership" in results[0]["message"]
    assert path.read_bytes() == original


def test_recompute_is_idempotent_after_corrected_values(tmp_path, monkeypatch) -> None:
    path = _write_partition(tmp_path, DAY)
    monkeypatch.setattr(
        script,
        "fetch_minute_limit_board_events",
        lambda root, day, *, now=None: [_fresh_row(day)],
    )
    script.recompute_range(tmp_path, [DAY], workers=2)

    results = script.recompute_range(tmp_path, [DAY], workers=2)

    assert results[0]["status"] == "unchanged"
    assert results[0]["rows_changed"] == 0
    assert pl.read_parquet(path)["last_seal_minute"].to_list() == [585]
