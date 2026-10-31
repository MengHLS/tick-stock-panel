"""Live Eastmoney opening-auction observations and final-result publication."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import threading
import time as time_module
from contextlib import contextmanager
from datetime import date, datetime, time
from functools import partial
from pathlib import Path

import polars as pl

from app.custom.eastmoney_auction.client import (
    EastmoneyAuctionClient,
    MarketRow,
    MarketSnapshot,
)
from app.market_time import CN_TZ, cn_now
from app.services import trading_day
from app.services.ext_data import (
    ExtConfig,
    ExtConfigStore,
    ExtField,
    PullConfig,
    write_ext_parquet,
)
from app.services.fs_utils import atomic_write_text

logger = logging.getLogger(__name__)

PREOPEN_CONFIG = "auction_preopen_live"
RESULT_CONFIG = "auction_result_live"
SEED_MARKER = ".eastmoney_auction_live_seeded"
SOURCE = "eastmoney.clist"
FINAL_SAMPLE_SIZE = 20
_PROCESS_INTERVAL_SECONDS = 45
_LOCK_TIMEOUT_SECONDS = 30.0
_LOCK_POLL_SECONDS = 0.05


class SyncCancelledError(RuntimeError):
    """Raised before a stopped scheduler can commit an auction observation."""


class AuctionVerificationError(RuntimeError):
    """The batch snapshot did not agree with independent per-symbol trends."""


def preopen_config() -> ExtConfig:
    return ExtConfig(
        id=PREOPEN_CONFIG,
        label="集合竞价过程（东财实时）",
        mode="timeseries",
        description=(
            "东方财富全市场 clist 快照，覆盖 09:15-09:25。"
            "observed_at 是本轮完整分页抓取的完成时间，不是供应商时间。"
            "累计量沿用东财手口径；未匹配量未提供，不能从累计量反推。"
        ),
        symbol_map={"type": "mapped", "col": "symbol"},
        pull=PullConfig(time_field="observed_at", enabled=False),
        fields=[
            ExtField("symbol", "string", "标的代码"),
            ExtField("name", "string", "股票简称"),
            ExtField("reference_price", "float", "虚拟撮合参考价（元）"),
            ExtField("cumulative_volume_lots", "float", "累计匹配量（手，东财口径）"),
            ExtField("cumulative_amount", "float", "累计匹配额（元）"),
            ExtField("prev_close", "float", "昨收价（元）"),
            ExtField("change_pct", "float", "参考价相对昨收（小数）"),
            ExtField("observed_at", "string", "完整采集完成时间（北京时间）"),
            ExtField("source", "string", "数据源"),
        ],
    )


def result_config() -> ExtConfig:
    return ExtConfig(
        id=RESULT_CONFIG,
        label="集合竞价结果（东财实时）",
        mode="timeseries",
        description=(
            "09:26 窗口抓取，09:25 最终开盘集合竞价结果。"
            "批量快照必须通过至少 20 只个股的单标的 stock/get 价格/金额校验后才会发布；"
            "成交量按东财手数乘 100 转为股，金额始终使用东财原始元值。"
        ),
        symbol_map={"type": "mapped", "col": "symbol"},
        fields=[
            ExtField("symbol", "string", "标的代码"),
            ExtField("name", "string", "股票简称"),
            ExtField("auction_open", "float", "09:25 竞价成交价（元）"),
            ExtField("prev_close", "float", "昨收价（元）"),
            ExtField("volume_lots", "float", "竞价成交量（手）"),
            ExtField("volume_shares", "float", "竞价成交量（股=手×100）"),
            ExtField("amount", "float", "竞价成交额（元）"),
            ExtField("opening_gap", "float", "竞价涨幅（小数）"),
            ExtField("has_result", "int", "有效竞价结果（1 或 0）"),
            ExtField("observed_at", "string", "完整采集完成时间（北京时间）"),
            ExtField("source", "string", "数据源"),
        ],
    )


_BUILDERS = {
    PREOPEN_CONFIG: preopen_config,
    RESULT_CONFIG: result_config,
}


def _config_path(data_dir: Path, config_id: str) -> Path:
    return data_dir / "ext_data" / config_id / "config.json"


def ensure_auction_configs(data_dir: Path) -> dict[str, ExtConfig | None]:
    """Seed extension tables once; a user deletion is never undone."""
    data_dir = Path(data_dir)
    store = ExtConfigStore(data_dir)
    marker = data_dir / "ext_data" / SEED_MARKER
    existing: dict[str, ExtConfig | None] = {}
    for config_id in _BUILDERS:
        config_path = _config_path(data_dir, config_id)
        config = store.get(config_id)
        if config_path.exists() and config is None:
            raise ValueError(f"Existing extension config is unreadable: {config_id}")
        existing[config_id] = config

    if marker.exists():
        return existing

    for config_id, builder in _BUILDERS.items():
        if existing[config_id] is None:
            config = builder()
            store.upsert(config)
            existing[config_id] = config
    marker.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(marker, "")
    return existing


def _expected_fields(config: ExtConfig) -> list[tuple[str, str]]:
    builder = _BUILDERS.get(config.id)
    if builder is None:
        raise ValueError(f"Unknown auction config: {config.id}")
    return [(field.name, field.dtype) for field in builder().fields]


def _assert_config_contract(config: ExtConfig) -> None:
    expected = _BUILDERS[config.id]()
    actual_fields = [(field.name, field.dtype) for field in config.fields]
    if (
        config.mode != "timeseries"
        or config.market_level
        or config.symbol_map != expected.symbol_map
        or actual_fields != _expected_fields(config)
        or (config.pull.time_field if config.pull else None)
        != (expected.pull.time_field if expected.pull else None)
    ):
        raise ValueError(f"Existing extension config conflicts: {config.id}")


def _required_configs(
    data_dir: Path,
    *,
    create_config: bool,
) -> tuple[ExtConfig, ExtConfig] | None:
    if create_config:
        ensure_auction_configs(data_dir)
    store = ExtConfigStore(data_dir)
    preopen = store.get(PREOPEN_CONFIG)
    result = store.get(RESULT_CONFIG)
    if preopen is None or result is None:
        return None
    _assert_config_contract(preopen)
    _assert_config_contract(result)
    return preopen, result


@contextmanager
def _commit_lock(data_dir: Path):
    path = data_dir / "ext_data" / ".eastmoney_auction.lock"
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
                    raise ValueError(
                        "Could not acquire auction import lock within 30 seconds"
                    ) from exc
                time_module.sleep(_LOCK_POLL_SECONDS)
        try:
            yield
        finally:
            handle.seek(0)
            release()


def _check_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise SyncCancelledError("Auction sync cancelled before commit")


def _aware_now(now: datetime | None) -> datetime:
    current = now or cn_now()
    if current.tzinfo is None:
        raise ValueError("now must have an explicit timezone")
    return current.astimezone(CN_TZ)


def _clock_time(value: datetime) -> time:
    return value.astimezone(CN_TZ).time().replace(tzinfo=None)


def _safe_number(value: float | None, *, minimum: float | None = None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    if minimum is not None and value < minimum:
        return None
    return value


def local_stock_symbols(data_dir: Path) -> list[str]:
    """Read the existing SH/SZ stock universe without triggering a network sync."""
    paths = sorted((Path(data_dir) / "instruments").glob("*.parquet"))
    if not paths:
        return []
    try:
        frame = pl.read_parquet(paths[-1], columns=["symbol"])
    except Exception as exc:  # malformed local metadata fails closed
        raise ValueError(f"Could not read local stock universe: {exc}") from exc
    return sorted(
        {
            str(symbol)
            for symbol in frame["symbol"].to_list()
            if isinstance(symbol, str)
            and len(symbol) == 9
            and symbol[-3] == "."
            and symbol[-2:] in {"SH", "SZ"}
            and symbol[:6].isdigit()
            and _is_a_share_stock(symbol)
        }
    )


def _is_a_share_stock(symbol: str) -> bool:
    code, exchange = symbol.split(".", 1)
    if exchange == "SH":
        return code.startswith(("600", "601", "603", "605", "688", "689"))
    return code.startswith(("000", "001", "002", "003", "300", "301", "302"))


def build_preopen_frame(snapshot: MarketSnapshot) -> pl.DataFrame:
    observed_at = snapshot.observed_at.astimezone(CN_TZ).isoformat()
    rows = []
    for row in snapshot.rows:
        price = _safe_number(row.reference_price, minimum=0)
        prev_close = _safe_number(row.prev_close, minimum=0)
        change_pct = (
            price / prev_close - 1
            if price is not None and prev_close is not None and price > 0 and prev_close > 0
            else None
        )
        rows.append(
            {
                "symbol": row.symbol,
                "name": row.name,
                "reference_price": price,
                "cumulative_volume_lots": _safe_number(
                    row.cumulative_volume_lots, minimum=0
                ),
                "cumulative_amount": _safe_number(row.cumulative_amount, minimum=0),
                "prev_close": prev_close,
                "change_pct": change_pct,
                "observed_at": observed_at,
                "source": SOURCE,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def _valid_final(row: MarketRow) -> tuple[float, float, float, float, float] | None:
    price = _safe_number(row.auction_open, minimum=0)
    prev_close = _safe_number(row.prev_close, minimum=0)
    volume = _safe_number(row.cumulative_volume_lots, minimum=0)
    amount = _safe_number(row.cumulative_amount, minimum=0)
    if (
        price is None
        or prev_close is None
        or volume is None
        or amount is None
        or price <= 0
        or prev_close <= 0
        or amount <= 0
    ):
        return None
    return price, prev_close, volume, amount, price / prev_close - 1


def build_result_frame(snapshot: MarketSnapshot) -> pl.DataFrame:
    observed_at = snapshot.observed_at.astimezone(CN_TZ).isoformat()
    rows = []
    for row in snapshot.rows:
        final = _valid_final(row)
        if final is None:
            rows.append(
                {
                    "symbol": row.symbol,
                    "name": row.name,
                    "auction_open": None,
                    "prev_close": _safe_number(row.prev_close, minimum=0),
                    "volume_lots": None,
                    "volume_shares": None,
                    "amount": None,
                    "opening_gap": None,
                    "has_result": 0,
                    "observed_at": observed_at,
                    "source": SOURCE,
                }
            )
            continue
        price, prev_close, volume, amount, opening_gap = final
        rows.append(
            {
                "symbol": row.symbol,
                "name": row.name,
                "auction_open": price,
                "prev_close": prev_close,
                "volume_lots": volume,
                "volume_shares": volume * 100,
                "amount": amount,
                "opening_gap": opening_gap,
                "has_result": 1,
                "observed_at": observed_at,
                "source": SOURCE,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def _verify_final_snapshot(
    client,
    snapshot: MarketSnapshot,
    expected_date: date,
    sample_size: int,
) -> int:
    if sample_size <= 0:
        raise ValueError("verify_sample_size must be positive")
    candidates = sorted(
        [
            row
            for row in snapshot.rows
            if _valid_final(row) is not None
        ],
        key=lambda row: row.cumulative_amount or 0,
        reverse=True,
    )[:sample_size]
    if len(candidates) < sample_size:
        raise AuctionVerificationError(
            f"verification sample incomplete: {len(candidates)}/{sample_size}"
        )

    mismatches: list[str] = []
    for index, row in enumerate(candidates):
        if index:
            time_module.sleep(0.05)
        try:
            final = client.fetch_auction_final(row.symbol, expected_date)
        except Exception as exc:  # noqa: BLE001 - any verification failure blocks publication
            mismatches.append(f"{row.symbol}: {exc}")
            continue
        assert row.auction_open is not None
        assert row.cumulative_amount is not None
        assert row.prev_close is not None
        if (
            abs(final.auction_open - row.auction_open) > 0.0001
            or abs(final.amount - row.cumulative_amount) > 0.5
            or abs(final.prev_close - row.prev_close) > 0.001
        ):
            mismatches.append(
                f"{row.symbol}: batch={row.auction_open}/{row.cumulative_amount}, "
                f"trends={final.auction_open}/{final.amount}"
            )
    if mismatches:
        raise AuctionVerificationError(
            "final auction verification failed: " + "; ".join(mismatches[:5])
        )
    return len(candidates)


def _owned_client(client):
    if client is not None:
        return client, False
    return EastmoneyAuctionClient(), True


def sync_preopen_snapshot(
    data_dir: Path,
    *,
    client=None,
    now: datetime | None = None,
    create_config: bool = True,
    cancel_event: threading.Event | None = None,
    symbols: list[str] | None = None,
) -> dict:
    """Fetch one full-market process snapshot before the 09:25 final match."""
    current = _aware_now(now)
    if current.weekday() >= 5 or trading_day.is_trading_day(current) is False:
        return {"status": "holiday", "rows": 0}
    if not (time(9, 15) <= _clock_time(current) < time(9, 25)):
        return {"status": "outside_window", "rows": 0}

    data_dir = Path(data_dir)
    configs = _required_configs(data_dir, create_config=create_config)
    if configs is None:
        return {"status": "missing_config", "rows": 0}
    preopen, _ = configs
    _check_cancelled(cancel_event)
    stock_symbols = list(symbols) if symbols is not None else local_stock_symbols(data_dir)
    if not stock_symbols:
        return {"status": "missing_universe", "rows": 0}

    source, owned = _owned_client(client)
    try:
        if not source.verify_session(current.date()):
            return {"status": "not_trading", "rows": 0}
        snapshot = source.fetch_market_snapshot(
            symbols=stock_symbols,
            cancel_event=cancel_event,
        )
    finally:
        if owned:
            source.close()

    if snapshot.observed_at.astimezone(CN_TZ).date() != current.date():
        return {"status": "not_trading", "rows": 0}
    if _clock_time(snapshot.observed_at) >= time(9, 25):
        return {"status": "late", "rows": 0}
    _check_cancelled(cancel_event)
    frame = build_preopen_frame(snapshot)

    with _commit_lock(data_dir):
        _check_cancelled(cancel_event)
        current_config = ExtConfigStore(data_dir).get(PREOPEN_CONFIG)
        if current_config is None:
            return {"status": "missing_config", "rows": 0}
        _assert_config_contract(current_config)
        count = write_ext_parquet(
            frame,
            preopen,
            data_dir,
            snapshot_date=current.date(),
        )
    return {
        "status": "written",
        "rows": count,
        "observed_at": snapshot.observed_at.isoformat(),
    }


def sync_final_results(
    data_dir: Path,
    *,
    client=None,
    now: datetime | None = None,
    create_config: bool = True,
    cancel_event: threading.Event | None = None,
    verify_sample_size: int = FINAL_SAMPLE_SIZE,
    symbols: list[str] | None = None,
) -> dict:
    """Publish final auction results only inside the verified 09:26 batch window."""
    current = _aware_now(now)
    if current.weekday() >= 5 or trading_day.is_trading_day(current) is False:
        return {"status": "holiday", "rows": 0}
    if not (time(9, 26, 5) <= _clock_time(current) < time(9, 30)):
        return {"status": "outside_window", "rows": 0}

    data_dir = Path(data_dir)
    configs = _required_configs(data_dir, create_config=create_config)
    if configs is None:
        return {"status": "missing_config", "rows": 0}
    _, result = configs
    _check_cancelled(cancel_event)
    stock_symbols = list(symbols) if symbols is not None else local_stock_symbols(data_dir)
    if not stock_symbols:
        return {"status": "missing_universe", "rows": 0}

    source, owned = _owned_client(client)
    try:
        if not source.verify_session(current.date()):
            return {"status": "not_trading", "rows": 0}
        snapshot = source.fetch_market_snapshot(
            symbols=stock_symbols,
            cancel_event=cancel_event,
        )
        if snapshot.observed_at.astimezone(CN_TZ).date() != current.date():
            return {"status": "not_trading", "rows": 0}
        if not (time(9, 26) <= _clock_time(snapshot.observed_at) < time(9, 30)):
            return {"status": "outside_window", "rows": 0}
        _check_cancelled(cancel_event)
        verified = _verify_final_snapshot(
            source,
            snapshot,
            current.date(),
            verify_sample_size,
        )
    finally:
        if owned:
            source.close()

    _check_cancelled(cancel_event)
    frame = build_result_frame(snapshot)
    with _commit_lock(data_dir):
        _check_cancelled(cancel_event)
        current_config = ExtConfigStore(data_dir).get(RESULT_CONFIG)
        if current_config is None:
            return {"status": "missing_config", "rows": 0}
        _assert_config_contract(current_config)
        count = write_ext_parquet(
            frame,
            result,
            data_dir,
            snapshot_date=current.date(),
        )
    return {
        "status": "written",
        "rows": count,
        "verified": verified,
        "observed_at": snapshot.observed_at.isoformat(),
    }


def _completion_marker(data_dir: Path, day: date) -> Path:
    return data_dir / "ext_data" / RESULT_CONFIG / ".auto_completed" / day.isoformat()


class EastmoneyAuctionScheduler:
    """Collect process snapshots every 45s, then publish one verified final result."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        self._enabled = False
        self._data_dir: Path | None = None
        self._repository = None
        self._cancel_event = threading.Event()
        self._last_process_at: datetime | None = None
        self._last_final_at: datetime | None = None
        self._final_day: date | None = None

    def start(self, data_dir: Path, *, enabled: bool = True, repository=None) -> None:
        self.stop()
        self._data_dir = Path(data_dir)
        self._repository = repository
        self._enabled = bool(enabled)
        self._cancel_event = threading.Event()
        self._last_process_at = None
        self._last_final_at = None
        self._final_day = None
        if not self._enabled:
            logger.info("EastmoneyAuctionScheduler initialized (disabled)")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("EastmoneyAuctionScheduler started")

    def stop(self) -> None:
        self._running = False
        self._enabled = False
        self._cancel_event.set()
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _run_loop(self) -> None:
        try:
            while self._running:
                await self.run_once()
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            self._running = False
            self._cancel_event.set()

    async def run_once(self, now: datetime | None = None) -> dict:
        if not self._enabled or self._data_dir is None:
            return {"status": "disabled"}
        current = _aware_now(now)
        if current.weekday() >= 5 or trading_day.is_trading_day(current) is False:
            return {"status": "not_due"}

        clock = _clock_time(current)
        final_phase = False
        if time(9, 15) <= clock < time(9, 25):
            if (
                self._last_process_at is not None
                and (current - self._last_process_at).total_seconds()
                < _PROCESS_INTERVAL_SECONDS
            ):
                return {"status": "not_due"}
            self._last_process_at = current
            operation = partial(
                sync_preopen_snapshot,
                self._data_dir,
                now=current,
                create_config=False,
                cancel_event=self._cancel_event,
            )
        elif time(9, 26, 5) <= clock < time(9, 30):
            final_phase = True
            marker = _completion_marker(self._data_dir, current.date())
            if self._final_day == current.date() or marker.exists():
                self._final_day = current.date()
                return {"status": "done", "date": current.date().isoformat()}
            if (
                self._last_final_at is not None
                and (current - self._last_final_at).total_seconds() < 15
            ):
                return {"status": "not_due"}
            self._last_final_at = current
            operation = partial(
                sync_final_results,
                self._data_dir,
                now=current,
                create_config=False,
                cancel_event=self._cancel_event,
            )
        else:
            return {"status": "not_due"}

        try:
            result = await asyncio.to_thread(operation)
        except SyncCancelledError:
            return {"status": "cancelled"}
        except Exception as exc:  # noqa: BLE001 - scheduler must keep retrying
            if self._cancel_event.is_set():
                return {"status": "cancelled"}
            logger.warning("Eastmoney auction sync failed: %s", exc)
            return {"status": "error", "message": str(exc)}

        if result.get("status") in {"written", "exists"}:
            clear_cache = getattr(self._repository, "clear_cache", None)
            if callable(clear_cache):
                try:
                    clear_cache()
                except Exception as exc:  # noqa: BLE001 - retry before marking final done
                    return {"status": "error", "message": f"cache invalidation: {exc}"}

        if final_phase and result.get("status") in {
            "written",
            "exists",
            "missing_config",
        }:
            marker = _completion_marker(self._data_dir, current.date())
            marker.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(marker, str(result.get("status")))
            self._final_day = current.date()
        return result


auction_scheduler = EastmoneyAuctionScheduler()
