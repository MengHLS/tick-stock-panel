"""扩展数据卡片的「最新」时间必须是北京墙钟, 不随服务端时区漂移。

latest_sync_date 由 parquet 的 mtime 格式化而来, 前端 ExtDataStatCard 原样
展示这串裸时间。用宿主机时钟格式化, 容器默认 UTC 时同一次同步在卡片上显示
成 8 小时前, 而同一页拉取面板里的 pull.last_run(带时区的 ISO, 前端按浏览器
时区渲染)显示的是正确时间 —— 一个页面两个时间对不上。
"""
from __future__ import annotations

import os
import types
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ext_data import _latest_sync_date, router
from app.market_time import CN_TZ
from app.services.ext_data import ExtConfig, ExtConfigStore, ExtField

# 固定 epoch 秒 = 北京时间 2026-09-04 22:13:20
_MTIME = 1_788_531_200


def _beijing(fmt: str) -> str:
    return datetime.fromtimestamp(_MTIME, tz=CN_TZ).strftime(fmt)


def _touch(path, mtime: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    os.utime(path, (mtime, mtime))


@pytest.fixture
def snapshot_config():
    return types.SimpleNamespace(id="ext_gn_ths", mode="snapshot")


@pytest.fixture
def timeseries_config():
    return types.SimpleNamespace(id="ext_ts_demo", mode="timeseries")


def test_snapshot_latest_sync_is_beijing_wall_clock(tmp_path, snapshot_config):
    _touch(tmp_path / "ext_data" / snapshot_config.id / "part.parquet", _MTIME)

    got = _latest_sync_date(snapshot_config, tmp_path)

    assert got == _beijing("%Y-%m-%d %H:%M:%S")


def test_timeseries_latest_sync_is_beijing_wall_clock(tmp_path, timeseries_config):
    base = tmp_path / "ext_data" / timeseries_config.id / "timeseries"
    _touch(base / "date=2026-09-03" / "part.parquet", _MTIME - 86400)
    _touch(base / "date=2026-09-04" / "part.parquet", _MTIME)

    got = _latest_sync_date(timeseries_config, tmp_path)

    assert got == f"2026-09-04 {_beijing('%H:%M:%S')}"


@pytest.mark.parametrize("legacy", [False, True])
def test_timeseries_latest_date_does_not_regress_after_backfill(
    tmp_path, timeseries_config, legacy,
):
    base = (
        tmp_path / "kline_ext"
        if legacy
        else tmp_path / "ext_data" / timeseries_config.id / "timeseries"
    )
    _touch(base / "date=2026-09-04" / "part.parquet", _MTIME)
    _touch(base / "date=2019-01-02" / "part.parquet", _MTIME + 86400 + 60)
    (base / "date=2026-09-07").mkdir()

    got = _latest_sync_date(timeseries_config, tmp_path)

    assert got == f"2026-09-04 {_beijing('%H:%M:%S')}"


def test_latest_sync_uses_newest_file_within_latest_partition(tmp_path, timeseries_config):
    base = tmp_path / "ext_data" / timeseries_config.id / "timeseries"
    _touch(base / "date=2026-09-04" / "part.parquet", _MTIME - 60)
    _touch(base / "date=2026-09-04" / "extra.parquet", _MTIME)
    _touch(base / "date=2026-09-03" / "part.parquet", _MTIME + 120)

    assert _latest_sync_date(timeseries_config, tmp_path) == (
        f"2026-09-04 {_beijing('%H:%M:%S')}"
    )


def test_list_configs_latest_matches_data_range_after_backfill(tmp_path):
    config = ExtConfig(
        id="limit_board_events",
        label="Limit board events",
        mode="timeseries",
        fields=[ExtField("symbol", "string")],
    )
    ExtConfigStore(tmp_path).upsert(config)
    base = tmp_path / "ext_data" / config.id / "timeseries"
    _touch(base / "date=2026-09-04" / "part.parquet", _MTIME)
    _touch(base / "date=2019-01-02" / "part.parquet", _MTIME + 86400 + 60)
    app = FastAPI()
    app.state.repo = types.SimpleNamespace(store=types.SimpleNamespace(data_dir=tmp_path))
    app.include_router(router)

    with TestClient(app) as client:
        response = client.get("/api/ext-data")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["latest_sync_date"] == f"2026-09-04 {_beijing('%H:%M:%S')}"
    assert item["date_range"] == ["2019-01-02", "2026-09-04"]


def test_latest_sync_is_none_without_any_data(tmp_path, snapshot_config):
    assert _latest_sync_date(snapshot_config, tmp_path) is None
