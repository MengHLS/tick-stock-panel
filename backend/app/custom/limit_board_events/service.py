"""System-generated daily extension data for completed limit-board events."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time as time_module
from contextlib import contextmanager
from datetime import date, datetime, time
from functools import partial
from pathlib import Path

import polars as pl

from app.custom.limit_board_events.fuyao_adapter import fetch_limit_board_events
from app.custom.limit_board_events.minute_adapter import (
    fetch_minute_limit_board_events,
)
from app.market_time import CN_TZ, cn_now
from app.plugins.fuyao.client import FuyaoClient
from app.plugins.fuyao.provider import get_api_key
from app.services.ext_data import (
    ExtConfig,
    ExtConfigStore,
    ExtField,
    cast_df_to_schema,
    write_ext_parquet,
)
from app.services.fs_utils import atomic_write_text

logger = logging.getLogger(__name__)

CONFIG_ID = "limit_board_events"
AUTO_SYNC_START = time(15, 45)
_AUTO_SYNC_POLL_SECONDS = 60
_LOCK_TIMEOUT_SECONDS = 30.0
_LOCK_POLL_SECONDS = 0.05
_SEED_MARKER = ".limit_board_events_seeded"


class SyncCancelledError(RuntimeError):
    """Raised before a stopped scheduler can commit a fetched partition."""


def limit_board_config() -> ExtConfig:
    return ExtConfig(
        id=CONFIG_ID,
        label="涨停封板与炸板",
        mode="timeseries",
        description=(
            "支持扶摇双池盘后合并，或从本地分钟K还原分钟收盘封板/炸板事件；"
            "无法还原的字段保持未知。时间数值为北京时间距零点分钟数；金额单位元，"
            "换手率为百分数。仅用于 T 日盘后及以后。"
            "工作日盘后由系统自动生成；已有分区不覆盖。历史缺口使用 "
            "scripts.sync_limit_board_events 按日补录。"
        ),
        symbol_map={"type": "mapped", "col": "symbol"},
        fields=[
            ExtField("trade_date", "string", "交易日"),
            ExtField("symbol", "string", "标的代码"),
            ExtField("name", "string", "股票简称"),
            ExtField("in_limit_up_pool", "int", "涨停池收录（1或未知）"),
            ExtField("in_limit_break_pool", "int", "炸板池收录（1或未知）"),
            ExtField("observed_open", "int", "已观测开板（缺失为未知）"),
            ExtField("continue_day_cnt", "int", "连板计数"),
            ExtField("limit_up_reason", "string", "涨停原因"),
            ExtField("limit_up_time", "string", "涨停池时间（原始口径）"),
            ExtField("limit_up_minute", "int", "涨停池时间（距零点分钟）"),
            ExtField("first_seal_time", "string", "炸板池首次封板时间"),
            ExtField("first_seal_minute", "int", "首次封板（距零点分钟）"),
            ExtField("last_seal_time", "string", "炸板池最后封板时间"),
            ExtField("last_seal_minute", "int", "最后封板（距零点分钟）"),
            ExtField("limit_up_pool_open_times", "int", "涨停池开板次数"),
            ExtField("break_pool_open_times", "int", "炸板池开板次数"),
            ExtField("seal_money", "float", "封单额（元）"),
            ExtField("max_seal_money", "float", "峰值封单额（元）"),
            ExtField("turnover", "float", "炸板池成交额（元）"),
            ExtField("turnover_ratio_pct", "float", "炸板池换手率（%）"),
            ExtField("up_source_ready_at", "string", "涨停池数据就绪时刻"),
            ExtField("break_source_ready_at", "string", "炸板池数据就绪时刻"),
            ExtField("retrieved_at", "string", "实际获取时刻"),
        ],
    )


def ensure_limit_board_config(data_dir: Path) -> ExtConfig | None:
    """Create the derived table once without reviving a user-deleted config."""
    data_dir = Path(data_dir)
    store = ExtConfigStore(data_dir)
    config_path = data_dir / "ext_data" / CONFIG_ID / "config.json"
    marker = data_dir / "ext_data" / _SEED_MARKER
    config = store.get(CONFIG_ID)
    if config_path.exists() and config is None:
        raise ValueError("Existing extension config is unreadable; refusing to overwrite")
    if config is not None:
        if not marker.exists():
            atomic_write_text(marker, "")
        return config
    if marker.exists():
        return None
    config = limit_board_config()
    store.upsert(config)
    atomic_write_text(marker, "")
    return config


@contextmanager
def _commit_lock(data_dir: Path):
    """Kernel locks release on process exit; the tiny lock file stays in place."""
    path = data_dir / "ext_data" / ".limit_board_events.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            acquire = partial(msvcrt.locking, handle.fileno(), msvcrt.LK_NBLCK, 1)
            release = partial(msvcrt.locking, handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            acquire = partial(
                fcntl.flock,
                handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
            release = partial(fcntl.flock, handle.fileno(), fcntl.LOCK_UN)
        deadline = time_module.monotonic() + _LOCK_TIMEOUT_SECONDS
        while True:
            try:
                acquire()
                break
            except OSError as exc:
                if time_module.monotonic() >= deadline:
                    raise ValueError("Could not acquire import lock within 30 seconds") from exc
                time_module.sleep(_LOCK_POLL_SECONDS)
        try:
            yield
        finally:
            handle.seek(0)
            release()


def _existing_state(
    data_dir: Path,
    day: date,
    expected: ExtConfig,
) -> tuple[ExtConfig | None, dict | None]:
    store = ExtConfigStore(data_dir)
    config_path = data_dir / "ext_data" / CONFIG_ID / "config.json"
    config = store.get(CONFIG_ID)
    if config_path.exists() and config is None:
        raise ValueError("Existing extension config is unreadable; refusing to overwrite")
    if config is not None:
        actual_fields = [(field.name, field.dtype) for field in config.fields]
        wanted_fields = [(field.name, field.dtype) for field in expected.fields]
        if (
            config.mode != "timeseries"
            or config.market_level
            or config.pull
            or config.symbol_map != expected.symbol_map
            or config.code_map
            or actual_fields != wanted_fields
        ):
            raise ValueError("Existing extension config conflicts with the importer contract")

    partition = data_dir / "ext_data" / CONFIG_ID / "timeseries" / f"date={day}" / "part.parquet"
    if partition.exists():
        if config is None:
            raise ValueError("Existing data has no extension config")
        frame = pl.read_parquet(partition)
        expected_columns = {field.name for field in expected.fields}
        if (
            frame.is_empty()
            or not expected_columns.issubset(frame.columns)
            or frame["trade_date"].null_count()
            or frame["trade_date"].unique().to_list() != [day.isoformat()]
            or frame["symbol"].null_count()
            or frame["symbol"].n_unique() != frame.height
        ):
            raise ValueError("Existing partition is invalid; refusing to overwrite")
        return config, {"date": day.isoformat(), "status": "exists", "rows": frame.height}
    return config, None


def _check_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise SyncCancelledError("Limit board sync cancelled before commit")


def sync_limit_board_events(
    data_dir: Path,
    day: date,
    *,
    source: str = "fuyao",
    client: FuyaoClient | None = None,
    now: datetime | None = None,
    create_config: bool = True,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Generate one complete day; skip existing partitions without rewriting data."""
    if source not in {"fuyao", "minute"}:
        raise ValueError("source must be 'fuyao' or 'minute'")
    current = now or cn_now()
    if current.tzinfo is None:
        raise ValueError("now must have an explicit timezone")
    current = current.astimezone(CN_TZ)
    if day > current.date() or (day == current.date() and current.time() < time(15, 30)):
        raise ValueError("Only completed trading days (after 15:30 Beijing) may be imported")

    data_dir = Path(data_dir)
    expected = limit_board_config()
    _, existing = _existing_state(data_dir, day, expected)
    if existing:
        return {**existing, "source": source}
    _check_cancelled(cancel_event)
    if not create_config and ExtConfigStore(data_dir).get(CONFIG_ID) is None:
        return {
            "date": day.isoformat(),
            "status": "missing_config",
            "rows": 0,
            "source": source,
        }

    if source == "minute":
        try:
            rows = fetch_minute_limit_board_events(data_dir, day, now=current)
        except FileNotFoundError:
            return {
                "date": day.isoformat(),
                "status": "missing_source",
                "rows": 0,
                "source": source,
            }
    else:
        owned = client is None
        client_source = client if client is not None else FuyaoClient(get_api_key())
        try:
            rows = fetch_limit_board_events(client_source, day)
        finally:
            if owned:
                client_source.close()

    _check_cancelled(cancel_event)
    if not rows:
        return {
            "date": day.isoformat(),
            "status": "empty",
            "rows": 0,
            "source": source,
        }
    frame = cast_df_to_schema(
        pl.DataFrame(rows, infer_schema_length=None),
        expected.fields,
    )
    _check_cancelled(cancel_event)

    # Fetch outside the lock, then re-read state inside the same commit section
    # used by every importer process. Another import may have finished meanwhile.
    with _commit_lock(data_dir):
        _check_cancelled(cancel_event)
        config, existing = _existing_state(data_dir, day, expected)
        if existing:
            return {**existing, "source": source}
        if config is None:
            if not create_config:
                return {
                    "date": day.isoformat(),
                    "status": "missing_config",
                    "rows": 0,
                    "source": source,
                }
            ExtConfigStore(data_dir).upsert(expected)
            config = expected
        _check_cancelled(cancel_event)
        count = write_ext_parquet(frame, config, data_dir, snapshot_date=day)
    return {
        "date": day.isoformat(),
        "status": "written",
        "rows": count,
        "source": source,
    }


def _completion_marker(data_dir: Path, day: date) -> Path:
    return data_dir / "ext_data" / CONFIG_ID / ".auto_completed" / day.isoformat()


class LimitBoardEventScheduler:
    """Generate each completed weekday once, including a startup catch-up."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        self._enabled = False
        self._data_dir: Path | None = None
        self._repository = None
        self._completed_day: date | None = None
        self._error_logged_day: date | None = None
        self._cancel_event = threading.Event()

    def start(
        self,
        data_dir: Path,
        *,
        enabled: bool = True,
        repository=None,
    ) -> None:
        self.stop()
        self._data_dir = Path(data_dir)
        self._repository = repository
        self._enabled = bool(enabled)
        self._cancel_event = threading.Event()
        self._completed_day = None
        self._error_logged_day = None
        if not self._enabled:
            logger.info("LimitBoardEventScheduler initialized (auto-schedule disabled)")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("LimitBoardEventScheduler started (auto-schedule enabled)")

    def stop(self) -> None:
        self._running = False
        self._enabled = False
        self._cancel_event.set()
        if self._task is not None:
            self._task.cancel()
            self._task = None
        logger.info("LimitBoardEventScheduler stopped")

    async def _run_loop(self) -> None:
        try:
            while self._running:
                await self.run_once()
                await asyncio.sleep(_AUTO_SYNC_POLL_SECONDS)
        except asyncio.CancelledError:
            self._running = False
            self._cancel_event.set()

    async def run_once(self, now: datetime | None = None) -> dict:
        if not self._enabled or self._data_dir is None:
            return {"status": "disabled"}
        current = now or cn_now()
        if current.tzinfo is None:
            raise ValueError("now must have an explicit timezone")
        current = current.astimezone(CN_TZ)
        if current.weekday() >= 5 or current.time() < AUTO_SYNC_START:
            return {"status": "not_due"}
        day = current.date()
        if self._completed_day == day:
            return {"status": "done"}
        if _completion_marker(self._data_dir, day).exists():
            self._completed_day = day
            return {"status": "done", "date": day.isoformat()}
        try:
            result = await asyncio.to_thread(
                sync_limit_board_events,
                self._data_dir,
                day,
                now=current,
                create_config=False,
                cancel_event=self._cancel_event,
            )
        except SyncCancelledError:
            return {"status": "cancelled"}
        except Exception as exc:  # noqa: BLE001 - scheduler must keep retrying
            if self._error_logged_day != day:
                logger.warning(
                    "LimitBoardEventScheduler sync failed for %s: %s",
                    day,
                    exc,
                )
                self._error_logged_day = day
            return {"status": "error", "message": str(exc)}

        if result.get("status") in {"written", "exists"}:
            clear_cache = getattr(self._repository, "clear_cache", None)
            if callable(clear_cache):
                try:
                    clear_cache()
                except Exception as exc:  # noqa: BLE001 - retry before marking done
                    logger.warning(
                        "LimitBoardEventScheduler cache invalidation failed for %s: %s",
                        day,
                        exc,
                    )
                    return {
                        "status": "error",
                        "message": f"cache invalidation: {exc}",
                    }

        if result.get("status") in {"written", "exists", "empty"}:
            marker = _completion_marker(self._data_dir, day)
            try:
                marker.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(marker, result["status"])
            except OSError as exc:
                logger.warning(
                    "LimitBoardEventScheduler completion marker failed for %s: %s",
                    day,
                    exc,
                )
                return {"status": "error", "message": f"completion marker: {exc}"}
            self._completed_day = day
            logger.info("LimitBoardEventScheduler completed %s: %s", day, result)
        elif result.get("status") == "missing_config":
            self._completed_day = day
            logger.info(
                "LimitBoardEventScheduler skipped %s: extension table was deleted",
                day,
            )
        return result


limit_board_scheduler = LimitBoardEventScheduler()
